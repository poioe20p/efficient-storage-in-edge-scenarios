# Control Group Retune — Scale-vs-No-Scale Re-validation

**Status:** 🔵 Ready to run · **Date:** 2026-08-01 · **Category:** stability / control group
**Related:** [`../control_group.md`](../control_group.md) (generic RQ1/RQ2/RQ3 control reference), [`../post_implementation_verification/results.md`](../post_implementation_verification/results.md) (Runs 7–12)

---

## 1. Problem being fixed

The verification control-group pair (`v1g_plateau_*`) exposed two behaviors that are **not acceptable for an edge storage scenario** (evidence in `source/scripts/testing/metrics/20260801_122656_v1g_plateau_scalable/`):

1. **Storage grows too large.** The stepwise persistent-reserve chain activates a pre-warmed standby **every ~130 s** (cadence = `SCALEUP_STORAGE_COOLDOWN_S=120`) while storage stays hot during the sustained plateau, walking up to the **`MAX_DYNAMIC_STORAGE=8`** cap → **8 active storage nodes/LAN (16 total)**. Compute reached 7/LAN under `MAX_DYNAMIC_COMPUTE=12`. Expected: **≤ ~3 additional servers/LAN**.
2. **Zero storage scale-down completes in-window.** Storage scale-down used code defaults (`SCALEDOWN_STORAGE_COOLDOWN_S=120` + 9 of 15 windows below `TAU_DB_DOWN_MS=150`), and reserve replenishment kept **adding nodes during `recovery_gap` and `demand_drop`**, each add resetting the 120 s cooldown. The first `scale_down,storage` fired at t≈1309 s — **~70 s after the final snapshot (t=1140)** — so no storage node was ever reclaimed within the measured run.

Root cause is **config/policy**, not a code bug: the stepwise growth is by design (`storage_persistent_reserve` plan: *activate reserve → prepare next → activate next when ready*), but the verification caps (8/12) and conservative storage scale-down do not match the intended edge scenario. The RQ3 v7 calibration that *does* reclaim nodes uses 30 s cooldown + 3/5 windows + a 420 s `demand_drop`, targeting **≤1–2 dynamic nodes/LAN after `demand_drop`**.

## 2. Fix (config-only — no code change)

| Knob | Before (verification) | After (retune) |
|---|---|---|
| `MAX_DYNAMIC_STORAGE` | 8 | **3** (active; reserve standby not counted) |
| `MAX_DYNAMIC_COMPUTE` | 12 | **3** |
| `SCALEDOWN_STORAGE_COOLDOWN_S` | 120 (default) | **30** |
| `SCALE_DOWN_STORAGE_WINDOW_SIZE` | 15 (default) | **5** |
| `SCALE_DOWN_STORAGE_REQUIRED` | 9 (default) | **3** |
| `demand_drop` duration (phase file) | 300 s | **420 s** |
| `compute_plateau` rate | 6.0 → 5.0 (locked) | **5.0 (unchanged)** |

- **Scalable arm** = edit `source/scripts/testing/controller_env_overrides/current_state_integrated.env` **in place** (canonical override per repo rule): caps 3/3 + fast storage scale-down added. Historical run folders keep their own `controller_env_snapshot.env`, so v1e–v1g evidence is preserved.
- **No-scale arm** = `ablation_noscale.env` **unchanged** (`MAX_DYNAMIC_*=0`, reserve off, `SS_ENABLED=1`).
- **Phase file** = edit `phases_stress_plateau.json` **in place**: `demand_drop` 300 → 420 s (rate already 5.0). No duplicate phase file created.

**Why this works:** the 3/LAN cap bounds growth; the 30 s cooldown + 3/5 windows ≈ 80 s per removal (back-to-back via reserve-floor decoupling when >2 dynamic nodes); the 420 s `demand_drop` gives ~4–5 removal cycles (RQ3 v7 precedent). The reserve still maintains exactly 1 standby/LAN (not counted toward the cap) and remains exercisable.

## 3. Run matrix

Two runs, both with `PHASES_CONFIG=testing/phases_override/phases_stress_plateau.json` (rate 5.0, demand_drop 420 s):

| Run label | Env override | Arm |
|---|---|---|
| `cgr_scalable` | `testing/controller_env_overrides/current_state_integrated.env` (retuned) | scalable |
| `cgr_noscale` | `testing/controller_env_overrides/ablation_noscale.env` | no-scale (control) |

Shared (unchanged): `CLIENTS=24  CONTENT_ITEMS=3000  USERS=100  DATA_SEED=42  CURL_MAX_TIME=30`; hardware `STORAGE_CPUS=0.08  EDGE_CPUS=0.15  WAN_RTT_MS=185  RANDOM_SEED=42`.

Launch: `make -C source/scripts setup_network create_clients setup_test_data run_experiment` with the two override/phase variables above and `RUN_LABEL=cgr_*`. Monitor via `tools/watch_run.py --host cloud-vm --run-label cgr_*` until both exit 0.

## 4. Success criteria (gates)

| Gate | Criterion | Evidence |
|---|---|---|
| G1 | Both runs complete exit 0 | run_status / `.run_completed` |
| G2 | Peak active dynamic storage ≤ 3 per LAN (scalable) | `container_events.csv`: non-reserve storage adds ≤ 3/LAN |
| G3 | **≥ 1 storage node removed in-window** after `demand_drop` (scalable) | `container_events.csv` `removed` events before final snapshot; `decision_log` `scale_down,storage` before capture end |
| G4 | Reserve still exercised: ≥ 1 activation/LAN (scalable) | `decision_log` `reserve_activate` ≥ 1/LAN |
| G5 | Scalable benefit preserved vs no-scale: scalable error% ≤ ~3% (rate 5.0) and p50/DB-latency better than no-scale | Service-quality metrics |
| G6 | Compute ≤ 3/LAN and compute scale-down still completes in-window | `container_events.csv` compute adds ≤ 3/LAN, removals in-window |

## 5. Locked values (control group, after this passes)

- Plateau `rate_per_client` = **5.0**
- Caps = **3 active dynamic/LAN** (compute + storage), reserve standby extra
- Storage scale-down = **30 s cooldown + 3/5 windows**
- `demand_drop` = **420 s**

## 6. Post-run deliverables

1. Per-run analysis + `run_summary.md` (metrics-run-summary workflow).
2. Update [`../control_group.md`](../control_group.md) §2/§3/§5/§7 with validated numbers (rate 5.0 tables, caps, scale-down).
3. Append a Judgment finding + timeline row to [`../post_implementation_verification/results.md`](../post_implementation_verification/results.md).
4. Archive graphs to `docs/operation/testing/experiment/v2/control_group_retune/graphs/<run_timestamp>/`.
5. If a gate fails → tune further (e.g., `MAX_DYNAMIC_STORAGE=4`, or treat reserve replenishment during low-load phases as a code change).

## 7. Risks / watch items

- At rate 5.0 with only 3 compute nodes/LAN, per-node compute CPU may be higher than at 6.0/8-node config — watch for error% and the 30 s tail.
- If the reserve keeps replenishing into `demand_drop`, even 30 s cooldown may stretch the first removal — G3 is the arbiter.
- No-scale arm timing changes (420 s demand_drop) affect only duration, not the static behavior.

---

## Changelog
| Date | Change | Rationale |
|---|---|---|
| 2026-08-01 | Plan created for control-group retune (caps 3/3, fast storage scale-down, demand_drop 420 s, rate 5.0) | Verification v1g showed 8 storage/LAN with zero in-window scale-down — unacceptable for the edge scenario; retune to match ≤3/LAN + reclaim after demand_drop |
