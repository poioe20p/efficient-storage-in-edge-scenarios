# RQ2 Series-D — Storage-Bind Probe Plan

**Date**: 2026-08-06 · **Status**: 📋 Planned (NOT started) · **Host**: `cloud-vm-rq2`
**Parent**: [`experiment_plan.md`](experiment_plan.md) Changelog 2026-08-06 · [`recalibration_probe_plan.md`](recalibration_probe_plan.md) §8
**Why**: the Series-C db episode at `STORAGE_CPUS=0.15` leaves the storage tier at 30–50 % CPU — storage scale-up fires but produces **no visible relief** (db ~2 ms before and after spawn). For a solid thesis, *every* scale-up must show at least one measurable benefit (CPU / RAM / latency), as compute already does in the cb episode (CPU −18/−27 pts, proc_ms −85 %). This probe makes **storage the saturation bottleneck** in the db episode so that storage scale-up demonstrably relieves it — the missing H1-db / H2 wrong-action evidence — then the campaign re-runs.

## 1. Objective

Find and lock a db-episode config where **the storage tier is the binding constraint**, so that:
- **(H) aligned-arm health** — `sf_db` with storage scale-up serves the episode with `timeout ≤ 5 %`;
- **(M) mechanism exercise** — storage scale-up fires to budget and the storage tier is *actually pressured* (storage CPU near/at ceiling, db_ms degraded) **before** it scales;
- **(R) visible relief** — after storage scale-up, db_ms drops back toward baseline and/or per-node storage CPU drops (the measurable benefit);
- **(W) wrong-action cost** — `cf_db` (fixed_compute_first) scaling compute does **not** relieve storage (db_ms stays degraded, compute budget wasted).

Design rule (mirrors RQ1's compute-saturation design, `v2/rq1/experiment_plan.md` LOCKED-CONFIG: `EDGE_CPUS=0.25 STORAGE_CPUS=0.08`, gate `rq1_g2_rate12_mix_ec25` PASS): **make the target tier the saturation bottleneck at the chosen rate; then its scale-up provably benefits.**

## 2. Method — single-variable axis

**db cells (`cf_db`, `sf_db`, `ba_db`): `STORAGE_CPUS` 0.15 → 0.08.** Everything else held fixed:

| Held fixed (unchanged from Series C) | Value |
|---|---|
| `EDGE_CPUS` (db cells) | 0.30 |
| `EDGE_MONGO_MAX_POOL_SIZE` | 12 |
| episode rate (`data_bound_episode`) | 1.5 (72 req/s) |
| episode mix | lookup 0.4 / update 0.3 / aggregate 0.25 / feed 0.05 (95 % DB-bound) |
| `WAN_RTT_MS`, `CURL_MAX_TIME`, open-loop knobs, readiness gate, env files | unchanged |

**Why it should saturate (grounded in the C-series evidence):** at storage 0.08 + pool 12 + 72 req/s, the C1 probe showed storage **pegged at 100 % CPU / db 11 s** — the only reason C1 collapsed was the **edge co-choke at 0.15**. With edge now at **0.30** (healthy ~40–50 % at 72 req/s, C4), storage 0.08 should become the **sole** bottleneck: db_ms degrades → storage scale-up (reads spread across replicas via `secondaryPreferred`) relieves it.

**⚠ D1 result (2026-08-07) — FAIL, axis invalidated, revised to D1′.**

`rq2_probe_d1_sf_db` @ storage 0.08 with the **write-heavy** mix (update 0.3) → timeout **28.30 %**, db_ms **~6.2 s** (3000× baseline), and storage scale-up to 5 nodes produced **no relief** (db stayed ~6 s). Root cause (diagnostic): the **MongoDB primary is CPU-starved at 0.08, and 30 % of the mix is `content_update` (writes) — writes are primary-only**, so secondaryPreferred read scale-out cannot relieve the primary-bound write queue (secondaries were healthy/in-sync, repl lag ≤333 ms). The planned fallbacks (rate 2.0 / storage 0.05) would worsen the same per-op/write starvation and cannot produce a scale-out-relievable state.

**Revised D1′ axis (single-variable from D1 — mix only):** make the db episode **read-dominated** so the pressure is on the read path, which secondaryPreferred scale-out CAN relieve: `content_update` 0.3 → **0**, rebalanced to `content_lookup` 0.55 / `content_aggregate` 0.3 / `feed_ranking` 0.15 (100 % DB-read-bound; applied in-place to `phases_rq2_data_bound.json` 2026-08-07). Storage 0.08, edge 0.30, pool 12, rate 1.5 unchanged.

## 3. Runs

| Run | Cell | Policy | `STORAGE_CPUS` | Mix | Purpose |
|---|---|---|---|---|---|
| D1′ | `sf_db` | `fixed_storage_first` (aligned) | 0.08 | read-only (update→0) | Primary: storage read-saturates; storage scale-up → visible relief; health ≤ 5 % |
| D2 | `cf_db` | `fixed_compute_first` (mis-aligned) | 0.08 | read-only | Wrong-action contrast: compute scaled, storage stays degraded → no relief + budget wasted |
| D3 | `ba_db` | `bottleneck_aware` | 0.08 | read-only | Classifies storage → scales storage → relief + classification agreement |

Labels: `rq2_probe_d1r_sf_db`, `rq2_probe_d2_cf_db`, `rq2_probe_d3_ba_db`.
Episode phase (auto-detected or passed): `data_bound_episode`.

## 4. Gates (after each run — reviewed conclusion required, no next run before the gate closes)

| Gate | Question | Pass criteria | Decision if PASS | Decision if FAIL |
|---|---|---|---|---|
| G-D1 (mechanism) | Is storage the binding constraint (read path)? | storage CPU (median) near/at ceiling (~≥85 %) or db_ms degraded ≥10× baseline **before** first storage spawn; edge CPU < ~85 % (not a co-choke); storage spawns in-episode | next run (D2) | D1 failed (write-primary binding, 28.3 %); if D1′ fails to relieve → storage 0.08 is per-op-starved even for reads → raise storage to 0.10–0.12 (new single-variable axis) or accept the honest no-benefit framing |
| G-D2 (relief / H1) | Does storage scale-up produce a visible benefit? | `sf_db`: db_ms drops after spawn (toward baseline) and/or per-node storage CPU drops; episode timeout ≤ 5 % | next run (D3) | recalibrate; do NOT lock |
| G-D3 (wrong action / H2) | Does the wrong action cost? | `cf_db`: storage stays pegged, db_ms stays degraded (no relief) despite compute spawns (budget wasted, 4/LAN) | lock config → re-run campaign | revisit design |
| G-D4 (classification / H3) | Does `ba` classify the episode? | `ba_db`: `bottleneck_class=storage` in db episode (agreement reported, honest) | lock config → re-run campaign | report as soft |

**Block-1 guardrail still applies** to the re-run (aligned-cell episode timeout ≤ 5 %).

## 5. Between-run edit scope (the ONLY edits allowed during the probe)

| File | Edit | When |
|---|---|---|
| launch command / `run_rq2_campaign.py` CELLS (db cells) | `STORAGE_CPUS` 0.15 → 0.08 | once, before D1 (execution prep) |
| `phases_rq2_data_bound.json` | `data_bound_episode` mix: update 0.3 → 0, lookup 0.55 / aggregate 0.3 / feed 0.15 | **DONE 2026-08-07** (read-dominated D1′; single-variable from D1) |
| `phases_rq2_data_bound.json` | `data_bound_episode.rate_per_client` (1.5 → 2.0) | only if a rate fallback is gated in |

No other config/code edits during the probe. Each run captures its own `phases_snapshot.json` / `controller_env_snapshot.env`.

## 6. Launch command (per probe run, on `cloud-vm-rq2`)

```bash
ssh cloud-vm-rq2 "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n STORAGE_CPUS=0.08 EDGE_CPUS=0.30 WAN_RTT_MS=185 RANDOM_SEED=42 \
    EDGE_MONGO_READ_PREFERENCE=secondaryPreferred EDGE_MONGO_MAX_POOL_SIZE=12 \
    VIP_DATA_PER_CONNECTION_FLOWS=1 \
    make -C source/scripts setup_network create_clients setup_test_data run_experiment \
    OSKEN_ENV_OVERRIDE_FILE=../../rq2_env/rq2_<arm>.env \
    RUN_LABEL=<label> PHASES_CONFIG=testing/phases_override/phases_rq2_data_bound.json \
    CLIENTS=24 CONTENT_ITEMS=3000 USERS=100 DATA_SEED=42 CURL_MAX_TIME=300 \
    TRAFFIC_DRIVER_MODE=open_loop INFLIGHT_WINDOW=1024 DRAIN_S=30 \
    SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1 > /tmp/<label>.log 2>&1 &"
```

Arm envs: D1 `rq2_storage_first.env`, D2 `rq2_compute_first.env`, D3 `rq2_bottleneck_aware.env` (already staged at `~/rq2_env/`).

## 7. Gate evidence record (filled as the probe runs)

| Gate | Run | storage cpu (med) | db_ms before → after spawn | edge cpu (med) | timeout % | spawns | Verdict | Reviewer |
|---|---|---|---|---|---|---|---|---|
| G-D1 | `rq2_probe_d1_sf_db` (write-heavy mix) | 39–54 % (max 100 %) | 2 → 6177 (no relief) | 15–32 % | **28.30 %** | 7 (to 5 nodes) | ❌ **FAIL — write-primary binding** | — |
| G-D1′/G-D2 | `rq2_probe_d1r_sf_db` (read-only mix) | 33–51 % (max 100 %) | 582/1684 → 5216/1726 (no relief) | 11–13 % | **78.20 %** | 3 (to 2–3 nodes) | ❌ **FAIL — storage 0.08 is per-op-CPU-starved even for pure reads; scale-out cannot relieve (repl lag 0, edge idle)** | — |
| G-D3 | `rq2_probe_d2_cf_db` | | | | | | | |
| G-D4 | `rq2_probe_d3_ba_db` | | | | | | | |

## 8. Lock + re-run (after all gates PASS)

1. Lock db `STORAGE_CPUS=0.08` in `run_matrix.md` §4 (per-cell table + note) and in `tools/run_rq2_campaign.py` CELLS (db cells); lock the **read-dominated db mix** (update→0) in `run_matrix.md` §4 + `analysis_focus.md` (episode definition).
2. Re-run the **full 36-run campaign** (`counterbalance_order_v2.csv`) under the final config — uniform, single counterbalanced order — as the primary dataset.
3. Standard post-campaign analysis (campaign analyzer, cross-mode graphs, `results.md` timeline, `post_run_analysis.md`).

## 9. Changelog

| Date | Change | Rationale |
|------|--------|-----------|
| 2026-08-06 | Probe plan created after the campaign was aborted at run 13 (12/36) because db storage scale-up showed no visible relief at storage 0.15 | Solid-thesis requirement: storage scale-up must show at least one measurable benefit; mirror RQ1's saturation-bottleneck design |
| 2026-08-07 | **D1 FAIL (28.3 % timeout, no relief)** — storage 0.08 + write-heavy mix: MongoDB primary CPU-starved at 0.08, 30 % writes are primary-only → read scale-out cannot relieve the write queue | Axis invalidated; revised to D1′: read-dominated mix |
| 2026-08-07 | **D1′ FAIL (78.2 % timeout, no relief)** — storage 0.08 per-op-CPU-starved even for pure reads (repl lag 0, edge idle); adding equally-starved replicas cannot reduce per-op latency | Storage 0.08 is a dead end; next axis D1″: read mix + storage 0.15 |
| 2026-08-07 | **D1″ — healthy (0.03 %) but storage never binds** (38 % CPU at ~133 ops/s); no relief to demonstrate | Point reads too cheap at 0.15; storage capacity ≫ edge throughput |
| 2026-08-07 | **D1a FAIL (71.5 %)** — agg-heavy (scan 0.7): full-collection scan ~18 s at 0.15 CPU → open-loop/edge collapse before storage loads (storage CPU 10–40 %); scale-out undone | Scans are pool/pipeline-bound, not storage-CPU-relievable |
| 2026-08-07 | **D1p FAIL (28.8 %)** — lookup-heavy @ rate 3.5 (168 req/s, ~320 ops/s): edge-bound (single 0.30-CPU server); storage CPU only 24 % | Point-read storage capacity ~1300 ops/s ≫ edge throughput → storage can never bind |
| 2026-08-07 | **Probe CLOSED — negative result.** Storage scale-up cannot produce a visible CPU/RAM/latency benefit in this platform (see §10) | RQ2 evidence set scoped to compute relief + classification + action selection + cost side; thesis framing decision required |

## 10. ⛔ Conclusion — probe CLOSED with a negative result (2026-08-07)

**Storage scale-up cannot be made to produce a visible service-quality benefit (CPU/RAM/latency) in this platform.** Five runs span the entire sensible design space; each fails for a distinct, architectural reason:

| Run | Config | Outcome | Failure mode |
|---|---|---|---|
| D1 | storage 0.08, write mix, rate 1.5 | 28.3 % timeout, no relief | MongoDB **per-op CPU starvation** at 0.08; writes primary-only → read scale-out can't relieve |
| D1′ | storage 0.08, read mix, rate 1.5 | 78.2 % timeout, no relief | per-op starvation even for pure reads (repl lag 0, edge idle) |
| D1″ | storage 0.15, read mix, rate 1.5 | 0.03 % timeout — healthy | storage at only 38 % CPU — **never binds** |
| D1a | storage 0.15, agg-heavy (scan 0.7) | 71.5 % timeout, no relief | full-collection scan ~18 s at 0.15 CPU → open-loop/edge collapse **before storage is loaded** (storage CPU ~10–40 %) |
| D1p | storage 0.15, lookup-heavy, rate 3.5 (168 req/s, ~320 ops/s) | 28.8 % timeout | **edge-bound** (single 0.30-CPU server); storage CPU only 24 % — point-read capacity ~1300 ops/s ≫ edge throughput |

**Root cause (architectural):** the edge serving path (1× 0.30-CPU server, pool 12) is the binding constraint at any rate the open-loop driver sustains, while MongoDB point-read capacity at 0.15 CPU (~1300 ops/s) is ~4× that — so storage never becomes the throughput bottleneck. Forcing storage to bind (0.08 CPU, or heavy scans) triggers per-op CPU starvation or pipeline collapse that secondaryPreferred replica scale-out cannot relieve (replicas share the same sub-core quota; heavy ops are primary/lease-bound). **Compute scale-up relieves because edge requests are cheap and adding servers adds total CPU; the storage tier has no analogous relievable-pressure regime in this configuration.**

**Implication for RQ2:** the storage-side scale-up *benefit* (latency/CPU relief) cannot be demonstrated in this platform. RQ2's defensible evidence set is: compute scale-up relief (proven), bottleneck-aware **classification** (ba_db 88.9 % agreement, re-gate), correct **action selection** per episode, and the **cost side** (node-minutes, budget waste — mis-aligned arms). The db episode demonstrates that the controller correctly *selects and exercises* storage scale-out as a capacity/headroom mechanism, whose latency benefit the serving-path constraint prevents observing. **The thesis must either (a) frame RQ2's service-quality claim on the compute episode + mechanism/cost across both, documenting the storage-relief limit honestly, or (b) drop the db-episode latency-relief claim and scope conclusions accordingly.**

## 11. 🔄 Series W — write-clog pathway (REOPENED 2026-08-07)

**Hypothesis (user-proposed, distinct from all D-series axes):** the primary becomes the binding constraint on **writes** (single-writer), while **reads** (secondaryPreferred) spread to replicas. Storage scale-up then **moves reads off the primary** → primary CPU + write-latency relief = the visible benefit. **Untested**: D1 (the only write-heavy run) was at the starved 0.08 quota; no write-heavy run was ever done at adequate 0.15 CPU.

**Grounding (measured vs assumed):**
- Measured: storage 0.15 adequate (0.08 starves); storage 0.15 capacity ≈ 200–300 ops/s; edge 0.30 chokes by ~168 req/s (D1p); read-spread ≈ 30 % of storage requests reached secondaries (D1a per-node).
- Assumed (resolved by W1's per-node readout): write cost ≈ 2–3× read cost; read cost ≈ 1 ms; spread fraction holds for a write mix.

**Matrix (all: storage 0.15, edge 0.30, pool 12, secondaryPreferred, open-loop, readiness gate):**

| V | update | lookup | rate | writes/s | reads/s | Purpose |
|---|---|---|---|---|---|---|
| W1 | 0.30 | 0.70 | 2.5 (120) | 36 | 84 | Primary: clog + relief; resolves write-cost + spread |
| W2 | 0.45 | 0.55 | 2.5 | 54 | 66 | If W1 not clogged (writes cheaper) → push write share |
| W3 | 0.30 | 0.70 | 3.0 (144) | 43 | 101 | If W1 clogged but relief small → more reads |
| W1b | 0.30 | 0.70 | 2.0 | 29 | 67 | Fallback if edge chokes at rate 2.5 |

**Gates (per run):**
- **G-W1 (clog):** primary storage CPU ≥ ~90 % before first storage spawn (writes are the binding path).
- **G-W2 (spread):** secondary share of storage requests (per-node) — determines relief ceiling.
- **G-W3 (relief):** after storage scale-up, primary CPU drops AND `avg_time_db_write_ms` drops; aligned `sf_db` health ≤ 5 %.
- **G-W4 (classification, later):** `ba_db` at the locked config.

**Decision logic:** run W1 → read primary CPU (write cost) + secondary share (spread) → pick W2 or W3 → on SUCCESS lock config → D2 (`cf_db`) + D3 (`ba_db`) at the locked config → re-run campaign. If W1 shows spread ≈ 0 (reads never leave the primary) → the write-clog mechanism is dead → revert to §10 honest framing.

### W1 result (2026-08-07) — ❌ write-clog hypothesis REFUTED

`rq2_probe_w1_sf_db` (update 0.3 / lookup 0.7 @ rate 2.5 = 120 req/s): **timeout 0.01 % (health PASS)**, db_ms 1.7 ms, **storage CPU only 37 %**, **storage_fired = 0, 0 spawns**. The primary never approached clogging: 36 writes/s + 84 reads/s → 37 % CPU ⇒ **write cost ≈ read cost (~1 ms)** — the 2–3× write-cost assumption was wrong, and MongoDB writes (light upserts) are cheap at 0.15 CPU. The controller never even selected storage, so there was no relief to observe. W2/W3 are pointless (more writes at update=1 op/req would *lower* total ops/s; more reads → rate hits the edge co-choke zone from D1p).

**Why this closes the pathway:** with write cost ≈ read cost, the primary clogs only at ~320 ops/s ≈ 100 % of 0.15 CPU — which requires ~160 req/s of pure-lookup (2 ops/req), precisely the edge's co-choke zone (D1p: edge-bound at 168 req/s). Storage and edge capacities are **matched by platform design**, so storage can never bind cleanly below the edge's limit. Combined with the 5 D-series runs, **7 runs across every load axis (CPU quota, mix ×5, rate) confirm: storage scale-up cannot produce a visible CPU/RAM/latency benefit in this platform.** Final position = §10 honest framing (compute relief + mechanism/cost; storage documented as a capacity/headroom mechanism).

## 12. 🔄 Series S — serving-path upgrade (REOPENED 2026-08-07, user direction)

**Hypothesis (user-proposed):** make the **compute/serving resources** strong enough that storage becomes the binding constraint (mirror of the cb episode, where the weak edge makes compute bind). Raise `EDGE_CPUS` 0.30 → 0.60, keep storage 0.15, push lookup-heavy reads.

**S1 result (`rq2_probe_s1_sf_db`, edge 0.60, lookup 0.9/feed 0.1 @ rate 3.5 = 168 req/s ≈ 319 ops/s):** timeout **0.03 % (health PASS)**, db_ms 3.3 ms, **storage CPU only 31 %** — storage still never bound despite the stronger edge. Reads were verified to reach MongoDB (`cached_collection` is a fail-open passthrough; no Tier 1 manifest in the env snapshot). **The decisive number:** 319 ops/s → 31 % ⇒ storage 0.15 point-read capacity ≈ **1000 ops/s** — **~3× the edge's reach** (edge 0.60 ≈ 270 req/s × 2 ops ≈ 540 ops/s; even a full-core edge ~450 req/s ≈ 900 ops/s is a co-choke knife-edge, not a clean binding).

**Definitive root cause (now from 9 runs):** the storage tier's point-op capacity is ~3× the serving path's maximum reach; writes are cheap (~1 ms, ≈ reads, primary-bound); and the only storage-CPU-heavy op (full-collection aggregation) is so slow at 0.15 CPU (~18 s/scan) that it collapses the open-loop pipeline before scale-out can relieve. **Every axis — storage CPU quota (0.08/0.12/0.15), edge CPU (0.30/0.60), rate (1.5–3.5), and 6 mix variants — lands in either "storage has ≫ headroom" or "pipeline collapse".** Storage scale-up's benefit is not observable in this platform, by construction. This is a legitimate, evidence-backed **platform finding** (storage scale-out = throughput/headroom mechanism; its latency/CPU benefit is masked by the serving path's ~3× smaller reach).
