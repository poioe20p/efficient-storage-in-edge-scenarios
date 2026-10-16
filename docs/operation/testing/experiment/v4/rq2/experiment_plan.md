# RQ2 v4 — Campaign Experiment Plan (P4.1)

> **Status:** 2026-10-12 · 📋 **FROZEN 2026-10-12 (R1–R16 approved, D15)** — executed in full: 89 campaign folders, 84 valid / 5 excluded; results in [`results.md`](results.md).
> **Parent:** [`rq2v4_plan.md`](rq2v4_plan.md) (Phase 4, P4.1 requirement list) · **Decision log:** [`preparation.md`](preparation.md) (D1–D14, cited by ID) · **Executed path:** Phases 1–3 of `rq2v4_plan.md`.
> **Grounding:** [`rq2v4_p3_00_levers.md`](rq2v4_p3_00_levers.md) §3/§6–§7 (mixed seat, D13/D14, stor-mixed finding) · [`rq2v4_p2_08_band_floor.md`](rq2v4_p2_08_band_floor.md) §6 (D12) · [`rq2v4_p2_02_knee_calibration.md`](rq2v4_p2_02_knee_calibration.md) §2/§6 (seat runs) · [`rq2v4_p2_01_hash_kind.md`](rq2v4_p2_01_hash_kind.md) (hash mechanics) · [`rq2v4_p1_05_verification.md`](rq2v4_p1_05_verification.md) (F2 protocol, P4 pins).
> **This file is the execution contract for the Edge Experiment Runner (P5) and the gate contract for the Edge Experiment Analyzer (P6).** Where it conflicts with any other v4/rq2 artifact, this file wins.

---

## 1. Objective

One question: **does scaling the tier the demand actually presses on recover service, while scaling the wrong tier fails to help — reproduced across three demand regimes?** Operationally: execute the 3-regime × 4-mode matrix on the repaired, hash-capable platform and certify, per cell, the pre-registered direction of [`preparation.md`](preparation.md) §1 — aligned arms relieve (D12 compute / D14 storage), mis-aligned arms and the no-action comparator do not. 84 core runs (7 seeds per cell, D5) + spares, analyzed per run and per cell.

**Primary evidence focus:** client latency per kind (`client_requests.csv`) for service outcomes; per-window/per-node CPU (D12 compute leg, D14 storage leg) for relief; controller decision rows for engagement (M1/M2) and specificity. Resource fleet stats and controller logs are secondary context.

## 2. Motivation & Hypothesis

### 2.1 What was implemented before this campaign (all verified — no work pending)

| Phase | Change | Verified by |
| --- | --- | --- |
| P1 | Liveness/cull fix: heartbeat-backed presence, no absence evidence from empty windows, no zero-latency poisoning | `rq2v4_p1_05_verification.md` battery — zero culls/removals/poisoning |
| P2.1 | Hashing request kind `GET /compute/hash` (D3), `HASH_WORK_FACTOR` default 25000 | `rq2v4_p2_01_hash_kind.md` — selftest green; image `12c9ef0dc4b7` |
| P2.6/P2.8 | Backend-selection spread: ε-band (`EPS` 0.03) + band floor (`MIN_BAND` 4, D11) — breaks the one-hot funnel | `rq2v4_p2_08_band_floor.md` §6 — mechanism gates pass, steady-state relief, **seat frozen (D12)** |
| P3 | Mixed regime seat frozen (D13): R_m 1.15, mix 0.205/0.795, edge 0.15, member 0.05; pilots `mx_both`/`mx_comp`/`mx_stor`; **D14** storage-relief re-anchor | `rq2v4_p3_00_levers.md` §6–§7 |

### 2.2 Hypothesis (pre-registered, per cell)

| Regime ↓ / Mode → | `both` (D2: "compute and storage scaling") | `comp` | `stor` | `none` |
| --- | --- | --- | --- | --- |
| **cb** compute-bound | compute relief ✓ | compute relief ✓ | compute: **no relief** ✗ (specificity) | stays locked ✗ (comparator) |
| **mx** mixed | both tiers relief ✓ (D12 + D14) | compute ✓ / storage **unrelieved** ✗ | compute **unrelieved** ✗ / storage **measured, not assumed** ✗ (P3 pilot: not relieved — a reportable outcome, not a gate failure) | locks both tiers ✗ (comparator) |
| **db** data-bound | storage relief ✓ (D14); compute-side engagement **descriptive** (may or may not fire at EDGE 1.20 — C13 fire point ≈22 %, db edge budget ≈21–25 %) | storage **unrelieved** ✗ (wrong-action arm); compute-side engagement **descriptive** | storage relief ✓ (D14) | storage pressed ✗ (comparator) |

Every ✓ is a benefit claim that must reproduce across 7 replicates (gates G1/G2); every ✗ is a pre-registered no-benefit direction judged on its own claimed direction via gate G3 (magnitudes defined there). Special case: the `stor`@mx storage ✗ is **measured, not assumed** — its D14 metric is reported descriptively and never gated (D14). Single runs — including the n=1 P2/P3 pilots — are **not evidence**; cells rest on 7 replicates (D5, `testing_requirements.md` cross-cutting principle; the doc's "RQ2 n=6" example is stale against D5's seven — this plan pins 7, exceeding the n≥2 floor).

### 2.3 Independent variable & held constants

**Single independent variable:** the scaling-mode capability ablation (which tier the controller is permitted to scale) — env deltas `rq2v4_mode_*` (D1). **Blocking variable:** demand regime (cb/mx/db), fixed within each 4-run block. Each run changes only the mode at a fixed regime/seed.

**Held constants (pinned here):**

| Knob | Value | Source |
| --- | --- | --- |
| `HASH_WORK_FACTOR` | **25000** (image default; pinned by caller export for D3 provenance) | `edge_server_config.HASH_WORK_FACTOR_DEFAULT` |
| Spread knobs | `BACKEND_SELECTION_SPREAD_EPS=0.03`, `BACKEND_SELECTION_SPREAD_MIN_BAND=4` | canonical `current_state_integrated.env` |
| Clients | `CLIENTS=24` per lane (launcher default) | `rq2v4_launch_run.sh` |
| Open-loop driver | `CURL_MAX_TIME=300`, `INFLIGHT_WINDOW=1024`, `DRAIN_S=30`, `CONTENT_ITEMS=3000`, `USERS=100`, `DATA_SEED=42`, `WAN_RTT_MS=185`, `OVERLOAD_MIN_REQUESTS=60` | launcher fixed knobs |
| Data path | `EDGE_MONGO_READ_PREFERENCE=secondaryPreferred`, `EDGE_MONGO_MAX_POOL_SIZE=6`, `VIP_DATA_PER_CONNECTION_FLOWS=1`, `EDGE_FLOW_ISOLATION=1` | launcher fixed knobs |
| Mode caps (the ablation itself, D1) | `both` 6/6 · `comp` 6/0 · `stor` 0/6 · `none` 0/0; `comp` **and** `none` additionally `STORAGE_PERSISTENT_RESERVE_ENABLED=0` (C16, §3.1); `SS_ENABLED=0` in all four (D8) | `rq2v4_mode_*.env` |
| `TELEMETRY_SOURCE` | **proposed pin: `zmq`** (controller default; what P2/P3 actually ran) — R1 below | `rq2v4_p1_05_verification.md` §5.3 |
| `SCALEUP_POLICY` | **proposed pin: `dual`** (campaign default; P3 §4: "pilots: campaign policy (default `dual`; P4 pins it)") — R2 below | `rq2v4_p3_00_levers.md` §4 |
| Seeds | **42, 43, 44, 45, 46, 47, 48** (7 per cell; D5, RQ1's seven) | §3 |
| Window | 10 s telemetry decision window everywhere | P2/P3 convention |
| F2 quiescence | No host-side heavy commands during episodes; evidence collection only between runs | `rq2v4_p1_05_verification.md` §5 |
| Pool caveat | All v4 runs use pool **6** (launcher-pinned); v3 db cells were pool **12** → recorded caveat, see §7 Q3/Q7 | `rq2v4_p3_00_levers.md` §5 item 7 |

**Recorded comparability caveat (D13):** mixed runs at `STORAGE_CPUS=0.05`, data-bound runs at `0.15` — the two regimes' storage presses are quota-relative and **not load-comparable**; cross-regime storage-CPU numbers must not be pooled. Per-regime quotas follow the v3 precedent; the caveat is a limitation of the design, stated, not hidden. **Pending-confirmation rows in this table:** `TELEMETRY_SOURCE`/`SCALEUP_POLICY` (R1/R2), Seeds (R6), Pool caveat (R8), F2-quiescence status (R15) — all resolve via the Ready-for-review list; the remaining rows are pinned by this plan. **Input-number IDs (C1–C16) cite the P3 constants table [`rq2v4_p3_00_levers.md` §1](rq2v4_p3_00_levers.md).**

## 3. Run Matrix

### 3.1 Treatments (per cell)

| Regime | Episode (edited into canonical `phases.json`, §4.2) | `EDGE_CPUS` | `STORAGE_CPUS` | Mode envs |
| --- | --- | --- | --- | --- |
| **cb** compute-bound (frozen seat, D12) | 600 s, rate **0.23** rps/client (≈5.5 rps/lane), mix `{hash_challenge: 1.0}` | **0.15** | **0.15** *(launcher default; the P2 seat artifacts record only the edge quota, so this pin's calibration basis is unverifiable — but the storage signal is inert under a hash-only mix. Assumption flagged, R5)* | `rq2v4_mode_{both,comp,stor,none}.env` |
| **mx** mixed (**FROZEN** seat, D13) | 600 s, rate **1.15** (≈5.66 hash + 21.9 lookup rps/lane), mix `{hash_challenge: 0.205, content_lookup: 0.795}` | **0.15** | **0.05** | same |
| **db** data-bound (**v3 shape carried, NOT re-calibrated in v4** — flagged, Q3) | v3 `phases_rq2_data_bound.json` shape: 480 s, rate **5.0**, mix `{content_lookup: 0.9, feed_ranking: 0.1}` | **1.20** | **0.15** | same |

Mode capability ablation (D1/D8): `both` caps 6/6 · `comp` caps 6/0 + `STORAGE_PERSISTENT_RESERVE_ENABLED=0` · `stor` caps 0/6 · `none` caps 0/0 + reserve off. All four: `SS_ENABLED=0`.

### 3.2 Blocks, seeds, counterbalanced order

- **Block = 4 runs** (one regime: `both` + `comp` + `stor` + `none`, sharing one seed) — the `none` run of each block doubles as that seed's press witness (MC1).
- **21 blocks = 84 runs** (7 blocks per regime).
- **Regime-major order cb → mx → db** (minimises `phases.json` edits to 3 — P4.1 mandate). Regime order is fixed; mode order is counterbalanced within blocks by the Latin-square row of the block's seed:

| Seed | Mode order within the block |
| --- | --- |
| 42 | both → comp → stor → none |
| 43 | comp → stor → none → both |
| 44 | stor → none → both → comp |
| 45 | none → both → comp → stor |
| 46 | both → comp → stor → none |
| 47 | comp → stor → none → both |
| 48 | stor → none → both → comp |

Recorded residual: 7 blocks is not a multiple of 4, so first-position counts across modes are 2/2/2/1 (R14). Seed 42 is the calibration seed: cb and mx cells at seed 42 repeat the frozen P2/P3 seat/pilot runs (`comp_h023`, `stor_h023`, `mx_both`/`mx_comp`/`mx_stor`); the db regime has no P2/P3 counterpart (carried v3 shape, Q3), and `none`@cb at 0.23 is new (P2's `none` ran at 0.20). **Block order within a regime is seed-rotated per regime** to decorrelate seed position from time-of-day: cb = 42…48; mx = 45, 46, 47, 48, 42, 43, 44; db = 43, 44, 45, 46, 47, 48, 42.

### 3.3 Run budget & wall time

| Item | Count | Time |
| --- | --- | --- |
| Core matrix (21 blocks) | 84 | cb/mx ≈27 min/run (1620 s shape + ≈5 min setup/teardown); db ≈20 min/run (930 s shape + setup) ⇒ 28×27 + 28×27 + 28×20 ≈ **34.5 h** |
| Spares (replacement budget) | ≤14 (~17 %) | ≈6 h (14 × ≈25 min, mixed shapes) |
| Regime switching (2 `phases.json` edits + preflight checks) + P5.1 preflight | — | ≈2 h |
| **Total** | ≤98 | **≈42–45 VM-hours, ≈7–8 days at 3 blocks/day (≈12 runs/day; core 84 runs ≈7 days, spares add up to ≈1 day)** |

## 4. Run Configuration

### 4.1 Config mechanics, file by file

| File | Role | Campaign treatment |
| --- | --- | --- |
| `../../../../../../source/scripts/testing/phases.json` | **Single canonical workload file** — the three regimes are workloads, not variants | **Edited in place per regime** (§4.2), regime-major ordering (3 edits total); restored after the campaign (P3 precedent); **no copies, no variants under `docs/`** (P4.1) |
| `../../../../../../source/scripts/testing/controller_env_overrides/current_state_integrated.env` | Canonical override (signals, thresholds, spread pins, `TELEMETRY_TIMEOUT_S=600`) | **Not edited by the campaign** |
| `../../../../../../source/scripts/testing/controller_env_overrides/rq2v4_mode_both.env` / `_comp.env` / `_stor.env` / `_none.env` | Mode deltas (caps, reserve, `SS_ENABLED`; created in P1.2) | One merged per run, selected by the launcher `<mode>` argument |
| `../../../../../../source/scripts/testing/controller_env_overrides/rq2v4_p4_pins.env` | **Proposed new 2-key delta** — `SCALEUP_POLICY=dual` + `TELEMETRY_SOURCE=zmq` | Merged on **every** campaign run via the launcher's `extra_env_file` argument. **Does not exist yet → prerequisite (Appendix A), blocker if absent at P5.1 (R3).** Values match today's defaults — pinning is provenance, not behavior change |
| `../../../../../../source/scripts/testing/controller_env_overrides/rq2v4_p3_scalepolicy_ba.env` | P3 instrumentation delta (`SCALEUP_POLICY=bottleneck_aware` → 20-column per-tier decision rows) | **NOT merged in the 84 campaign runs** — with `dual` everywhere, per-window per-tier scores for every run come from the post-run `policy_state.csv` reconstruction (§6.1), so the BA delta buys nothing in-campaign. Reserved for author-signed diagnostic re-runs only — a contingency, never a default (R2) |
| `../../../../../../source/scripts/testing/rq2v4_launch_run.sh` | Launcher: merges canonical + mode + extra envs into one temp override; lifts `TELEMETRY_SOURCE`/`POLL_INTERVAL_S`/`HASH_WORK_FACTOR`; runs the make pipeline | Unchanged; invoked as in §4.3 |

**Provenance of the launch knobs (D3 — exact carrier per knob):**
- `HASH_WORK_FACTOR=25000` is injected by the launcher into the merged override (`HASH_ENV`), so it **is** captured in `controller_env_snapshot.env`.
- `EDGE_CPUS` / `STORAGE_CPUS` travel as **make command-line variables** consumed by `build_network_setup.sh` (docker `-e`, lines 496–497/517–518) and are **not written into any run artifact**. Their provenance chain is: run label → regime code → §3.1 quota table, plus a mandatory per-run `edge_cpus`/`storage_cpus` entry in the campaign status CSV `rq2v4_run_status.csv` (Appendix A/D), checked against §3.1 at P5.1 preflight. In-run verification is via the **controller containers** — `build_network_setup.sh` passes `-e EDGE_CPUS`/`-e STORAGE_CPUS` to `osken`/`osken_2` (the edge containers receive the quota as `--cpus=` only, no env var), so `docker exec <osken-container> printenv EDGE_CPUS` is the forensic witness for incident runs. The launcher always passes both vars explicitly, so `build_network_setup.sh`'s own 0.30/0.15 defaults never apply.
- `TELEMETRY_SOURCE` / `SCALEUP_POLICY` ride the `rq2v4_p4_pins.env` extra file → captured in the snapshot.

### 4.2 `phases.json` per regime (exact edits)

Common rule: **`service_pressure` is stripped from all non-episode phases** (not a v4 stressor — `rq2v4_p2_01_hash_kind.md` P2.4), mix renormalised 12:5 → `{"content_lookup": 0.706, "feed_ranking": 0.294}`; non-episode phases stay ≤2.4 rps/lane — off-press by construction (P3 §3). Assumption flagged (R6).

| Phase | **cb** | **mx** | **db (v3 shape carried)** |
| --- | --- | --- | --- |
| baseline | 60 s, rate 1.0, frac 0.1 | 60 s, rate 1.0, frac 0.1 | **30 s**, rate 1.0, frac 0.1 |
| episode | 600 s (`compute_plateau` renamed `hash_episode`), rate **0.23**, `{hash_challenge: 1.0}` | 600 s (`compute_plateau` renamed `mixed_episode`), rate **1.15**, `{hash_challenge: 0.205, content_lookup: 0.795}` | **480 s**, rate **5.0**, `{content_lookup: 0.9, feed_ranking: 0.1}` |
| recovery_gap | 120 s, rate 0.5, frac 0.05 | 120 s, rate 0.5, frac 0.05 | **60 s**, rate 0.5, frac 0.05 |
| demand_drop | 420 s, rate 1.0, frac 0.1 | 420 s, rate 1.0, frac 0.1 | **360 s**, rate 1.0, frac 0.1 |
| idle_tail | 420 s, rate 0.05 | 420 s, rate 0.05 | **omitted** (v3 db file was 4-phase — carried) |

Every run folder keeps `phases_snapshot.json` automatically (`run_experiment.sh` copies `PHASES_CONFIG`). **db exactness:** the db column reproduces the v3 `phases_rq2_data_bound.json` phase array (4 phases, episode `"hotspot_direction": ""` included) — that file is the **authoritative shape reference for the canonical edit**, not a run variant — with one stated modification: the §4.2 common rule applied to its non-episode mixes (the v3 file still carries `service_pressure 0.15` there). **P5.1 preflight verifies the canonical `phases.json` matches the intended regime JSON before each run**; the per-run `phases_snapshot.json` is checked post-run for equality (D3).

### 4.3 Launch commands (per run)

Launcher shape (P4.1): `bash source/scripts/testing/rq2v4_launch_run.sh <mode> <label> <seed> [extra_env_file ...]`, on `cloud-vm-rq2` from `~/efficient-storage-in-edge-scenarios`. Run folder: `<ts>_rq2v4_<mode>_<regime>_<seed>` (analyzers glob by name).

```bash
# common pins for every run
export HASH_WORK_FACTOR=25000

# --- compute-bound (cb) block, seed <S>, modes in Latin-square order ---
export EDGE_CPUS=0.15 STORAGE_CPUS=0.15
bash source/scripts/testing/rq2v4_launch_run.sh both rq2v4_both_cb_<S> <S> \
  source/scripts/testing/controller_env_overrides/rq2v4_p4_pins.env
bash source/scripts/testing/rq2v4_launch_run.sh comp rq2v4_comp_cb_<S> <S> \
  source/scripts/testing/controller_env_overrides/rq2v4_p4_pins.env
bash source/scripts/testing/rq2v4_launch_run.sh stor rq2v4_stor_cb_<S> <S> \
  source/scripts/testing/controller_env_overrides/rq2v4_p4_pins.env
bash source/scripts/testing/rq2v4_launch_run.sh none rq2v4_none_cb_<S> <S> \
  source/scripts/testing/controller_env_overrides/rq2v4_p4_pins.env

# --- mixed (mx) block: same four commands with EDGE_CPUS=0.15 STORAGE_CPUS=0.05, labels _mx_ ---
export EDGE_CPUS=0.15 STORAGE_CPUS=0.05
# (both/comp/stor/none, labels rq2v4_<mode>_mx_<S>)

# --- data-bound (db) block: EDGE_CPUS=1.20 STORAGE_CPUS=0.15, labels _db_ ---
export EDGE_CPUS=1.20 STORAGE_CPUS=0.15
# (both/comp/stor/none, labels rq2v4_<mode>_db_<S>)
```

Per block: edit `phases.json` (only at regime changes), run the four modes in the block's Latin-square order, then hand the run folders to analysis before the next block. Host quiescence (F2): no scans/greps/artifact collects while an episode runs; collection strictly between runs.

## 5. Measurements & Success Criteria

Definitions carried from P2/P3: "window" = 10 s telemetry window; "episode windows" = windows fully inside the episode phase; percentile legs exclude phantom rows (status `000` / beyond ceiling); hash-kind legs filter `client_requests.csv` to `hash_challenge` rows; "serving/busiest-member per-window CPU" = per-node window stats of the serving storage primary pre-add / busiest pre-add member post-add (P1.4 §4 serving-unit scoping); compute relief window (D12) = **post-engagement steady state: first post-add selection burst logged with `band ≥ 4` (`spread band=` controller-log line; the floor is a minimum, so wider bands also anchor) → episode end** (minimum 10 windows; fewer → judge on available windows and flag); storage post-ready window (D14) = **first in-episode storage activation + 120 s → episode end**, where the activation is the earliest of the `reserve_activate,storage_lanN` decision row timestamp or the `[reserve] activated` log line (both expected; either anchors) — minimum 10 windows; fewer → judge on available windows and flag. Anchoring at the decision row is conservative: it includes the activation lag inside the +120 s offset (P3 pilots: +10/+21 s); a run whose row-to-line gap exceeds 120 s is flagged.

**Anchor-absence rule (applies to every relief gate):** if a run's relief anchor never occurs — no `band ≥ 4` burst in `both`/`comp` @ cb/mx, or no storage activation (neither the `reserve_activate` row nor the `[reserve] activated` line) in `both`/`stor` @ db/mx — the relief gate is **not evaluable**; the run is re-read as an engagement failure (MC2), excluded as invalid, and the regime escalates (§5.5).

### 5.1 Manipulation checks (inclusion criteria)

**Evaluation scope:** MC1 (press) and MC4 (margin) are **block-level** checks evaluated on the block's `none` run — the `none` run is the press witness; if it fails, all four runs of the block are excluded from evidence and the regime escalates. MC2/MC3/MC5 are **per-run** checks.

| # | Check | Runs | Criterion (both lanes unless noted) |
| --- | --- | --- | --- |
| MC1 | **Press** (V1) | `none` only (block-level) | cb/mx: hash-kind p95 ≥ 1 s in ≥ 80 % of episode windows — the lock's primary signal (P2.3). Hash completion is **reported, not gated**: the P2.3 ladder reading straddles the original "< ~95 %" clause (94.9/95.4 % per lane), so completion is advisory (expected ≈95 %; a reading above ≈97 % is flagged for review). mx additionally: member CPU mean ≥ 33 % over episode windows **and** storage score above threshold (`storage_above_threshold=true` in `policy_state.csv`) in ≥ 40 % of episode rows — the P3 leg-(iii) persistence, read from the reconstructed policy state. db: member CPU mean ≥ **50 %** over episode windows (carried-v3 floor below the 66–74 % v3 state — the re-calibration question, Q3) |
| MC2 | **Engagement** (M1), per cell | all | `both`@cb: ≥1 `scale_up,ComputeAlert` row per lane; storage engagements **0** (inert by construction — not a failure). `comp`@cb: ≥1 ComputeAlert per lane. `both`@mx: ≥1 ComputeAlert per lane **and** ≥1 storage engagement per lane (`reserve_activate,storage_lanN` row or `[reserve] activated` line). `both`@db: ≥1 storage engagement per lane (**required** — the cell's claim is storage relief, G2); ≥1 ComputeAlert per lane **descriptive** (recorded, not required — the compute side is pre-registered descriptive in §2.2). `comp`@mx: ≥1 ComputeAlert per lane, **0** storage engagements. `comp`@db: storage engagements **0** (reserve off); compute-side engagement **descriptive** (may or may not fire at the C13 ≈22 % boundary at EDGE 1.20) — its adds, if any, must still meet MC5/M2. `stor`@mx / `stor`@db: ≥1 storage engagement per lane, **0** ComputeAlert rows, 0 compute spawns. `stor`@cb: 0 compute ops; 0 storage engagements (inert). `none`: **0** elasticity ops of any kind |
| MC3 | **Specificity** | mis-aligned cells | `stor`@cb: hash lock persists (p95 ≥ 1 s in ≥ 80 % windows), 0 compute spawns. `comp`@db: 0 storage engagements, member CPU mean ≥ 50 % in ≥ 60 % episode windows (persistence leg — plan-defined adaptation; v3 cf_db precedent 57.8/58.0 % mean). `stor`@mx: 0 ComputeAlert rows/spawns, hash p95 ≥ 1 s in ≥ 90 % episode windows (P3 pilot leg). `comp`@mx: 0 storage engagements, member CPU ≥ 33 % in ≥ 60 % episode windows (P3 pilot leg) |
| MC4 | **Margin** | `none` (block-level) | press holds through the whole episode — the MC1 criterion met in **both halves** of the episode (no drift) |
| MC5 | **Liveness contract** | all | 0 `triggering removal` lines for added units during episode + margin; every added unit keeps receiving assignments (P1.4 gates (a)/(b)/(e)) |

### 5.2 Outcome gates (aligned and comparator cells)

| # | Gate | Cells | Threshold (both lanes) |
| --- | --- | --- | --- |
| G1 | **Compute relief (D12)** | `both`/`comp` @ cb/mx | hash-kind p95 **< 1 s in ≥ 80 % of post-steady windows** (first `band ≥ 4` burst → end). **Time-to-relief endpoint (D12, one definition):** first `scale_up,ComputeAlert` row → first subsequent episode window with hash p95 < 1 s, per lane; median across replicates reported; the steady-state start (first `band ≥ 4` burst) is also recorded |
| G2 | **Storage relief (D14)** | `both`/`stor` @ **db**, `both` @ **mx** | busiest pre-add member's per-window CPU **< 0.75 × its own pre-add peak in ≥ 80 % of post-ready windows**. **Activated-member read shares reported descriptively, never gated** (sampled counters ≈1 sample/window). **Storage time-to-relief endpoint:** first post-ready window meeting the criterion, reported as offset from activation+120 s (0 = met immediately) and as absolute offset from the activation timestamp |
| G3 | **No-benefit directions** | comparators + mis-aligned arms | judged on own claimed direction with **explicit magnitudes**: `none`@all = MC1+MC4 hold and 0 ops (MC2). `stor`@cb compute = MC3 (lock persists ≥80 % windows, 0 compute spawns). `comp`@db storage = MC3 (0 engagements + member ≥50 % in ≥60 % windows). `stor`@mx compute = MC3 (0 alerts + hash p95 ≥1 s in ≥90 % windows). `comp`@mx storage = MC3 (0 engagements + member ≥33 % in ≥60 % windows). **`stor`@mx storage side: measured, not assumed** — the D14 metric is computed and reported descriptively; partial/no relief is a pre-registered reportable outcome (P3 §7 finding), not a gate failure |
| G4 | **Health ceiling** | cells pre-registered to recover: `both`@cb/mx/db, `comp`@cb/mx, `stor`@db | timeout ≤ **5 %** per run (v3 precedent). All other cells — `none`, `stor`@cb, `comp`@db, `stor`@mx — are **exempt**; no-collapse ceiling is explicitly NOT a gate (`testing_requirements.md`) |

### 5.3 Cell-level verdicts (campaign evidence, P6)

For each benefit claim (✓ in §2.2) the per-replicate metric is the **relief-window share** (G1: % of post-steady windows with hash p95 < 1 s; G2: % of post-ready windows with busiest-member CPU < 0.75× own-peak). The cell passes iff **≥ 6/7 replicates individually meet the per-run G1/G2 threshold** (replicate floor); the median of the per-replicate shares is reported (at n=7 the floor implies the median — it is kept as a reporting statistic, not a second gate). **Reduced-n rule:** replacements restore n=7 whenever budget allows (§5.5); n<7 occurs only when a cell's ≤2-replacement cap is exhausted or the author withholds replacement after an MC escalation. For n=6 the floor is ≥5/6; for n≤5 the cell is **evidence-limited** and escalates to the author (no silent pass). The reduced-n path is a **stated departure from D5's seven**, recorded with the reason in `rq2v4_cell_stats.csv` — never silent. Secondary ratio metrics (e.g. storage CPU post/pre per replicate) are reported as medians of per-replicate ratios with a **95 % CI (percentile bootstrap, v3 convention)**. Direction must be consistent across replicates. Single runs — including the P2/P3 pilots — are never evidence.

### 5.4 Base-requirements floor (applies to every run)

| Req | Checked by (evidence artifact) | Plan-defined magnitude |
| --- | --- | --- |
| **B1** compute benefit | `client_requests.csv` hash-kind windows + selection log | G1: ≥80 % post-steady windows p95 < 1 s, both lanes |
| **B2** storage benefit | `per_node_stats.csv` per-window CPU + activation rows | G2: <0.75× own-peak in ≥80 % post-ready windows, both lanes (gated for `stor`@db, `both`@db/mx; **descriptive for `stor`@mx**) |
| **M1** scale-up fires | controller logs (`[scale-up] compute fired`, `[scale-up] storage fired`, `reserve_activate` rows) | per MC2's cell table: required engagements ≥1 per lane; descriptive cells recorded (not demanded); `none` = 0. **Scale-down is recorded, not gated** in v4 (the claim is scale-up relief; `demand_drop`/`idle_tail` reclaim is descriptive) — stated so the analyzer does not demand the base doc's bidirectional clause |
| **M2** capacity usable | `per_node_stats.csv` request_count / sampled read counters | each added/activated node serves ≥1 request |
| **V1** bottleneck evidenced | MC1 (resource stats + client CSVs) | cb/mx: hash-kind lock (MC1); mx: member ≥33 % + storage score persistence; db: member ≥50 % (edge/member CPU read as context, not a separate gate) |
| **I1** enough demand | `client_requests.csv` | ≥ **N completed** requests per LAN in the episode: cb ≥ **2000** hash; mx ≥ **2000** hash + **5000** lookup; db ≥ **5000** |
| **I2** outcome classes | `client_requests.csv` `status` | timeout distinct class, never merged into failure; denominators offered/completed/timeout/canceled consistent |
| **D1** data path clean | `client_requests.csv` error rows | **0×** `NotPrimary`/`NotPrimaryOrSecondary` (no release-mechanism exception pre-registered — `RELEASE_MECHANISM=off`) |
| **D2** no mid-run crash | `container_events.csv`, controller logs | 0 controller restarts, 0 edge/storage container crashes/OOM |
| **D3** provenance | run folder | `phases_snapshot.json` + `controller_env_snapshot.env` present and matching the intended regime config |
| **F1** telemetry continuity (flag) | `resource_stats_debug.csv` | ≤2 consecutive empty episode windows (P1.4 gate (d), episode-scoped) |
| **F2** LAN symmetry (flag) | `client_requests.csv` | episode p95 ratio between LANs ≤ **3×** (base bound); ratio reported every run |

### 5.5 Run screening, exclusion & replacement policy

**Invalid-run criteria** — items (i)–(iv) and (vi): exclude + replace a slot; item (v) MC failures: **escalate, do not auto-rerun** (the author decides on replacement): (i) D2 violation (restart/crash/OOM); (ii) D3 snapshot missing or wrong; (iii) F2-attributed host-interference burst (latency storm with quota-unsaturated units + clean LAN peers + a campaign-log host-activity incident — the P1.4 fingerprint) → a harness/host defect, not a platform result; (iv) harness/driver failure (non-zero exit not explained by the platform); (v) MC failure — **escalate, do not auto-rerun** (see below); (vi) relief gate not evaluable (anchor never occurred, §5) → treated as engagement failure (MC2), excluded, escalate.

**Replacement budget:** ≤14 spares (~17 %), **author sign-off required beyond 14**. Per-cell cap **≤2 replacements**; if a regime accumulates **>4 replacements → stop that regime and escalate** (the two rules coexist: the per-regime rule triggers escalation before per-cell caps could exhaust the budget). A replacement re-uses the **same seed** with label `rq2v4_<mode>_<regime>_<seed>_r1` (analyzers glob `*_rq2v4_<mode>_<regime>_<seed>*`); the invalid original folder stays on disk and is marked `excluded` with its cause in the campaign status CSV — **the status CSV is the only authoritative list of which folders count** (Appendix D).

**Escalation rules:** an MC1 press failure in a `none` cell (a seed can't be pressed) → stop that regime, diagnose, escalate to the author (press re-anchor / re-calibration — the db carry is the known candidate). A systematic engagement failure in `both`/`stor` mx cells → re-read the P3 stor-mixed finding before concluding; `stor`@mx storage non-relief is **expected**, not a defect.

## 6. Analysis Approach & Handoff

### 6.1 Per run (after each block)

1. `python -m source.scripts.testing.analysis.cli_simple_run --run-dir <dir>` — latency/failure/active-node overview.
2. Verify `elasticity_events.csv` and `policy_state.csv` exist in the run folder (`run_experiment.sh` Step 8 generates both automatically; they are non-fatal, so a completed run can miss them). If missing/corrupt, re-run both tools in Step-8 order — `parse_elasticity_logs.py` first, then `reconstruct_policy_state.py` (it consumes `elasticity_events.csv`), with the same arguments `run_experiment.sh` uses (Step 8). `policy_state.csv` carries the per-window per-tier scores every gate reads — policy-independent.
3. Screen §5.5 criteria; update `rq2v4_run_status.csv` (per-run row: label, mode, regime, seed, block, ts, edge_cpus, storage_cpus, validity, exclusion_cause — the column set of Appendix A item 8); write `run_summary.md` under `<run_dir>/analysis/` per the analyzer workflow (verdicts MC1–MC5, G1–G4, base-floor table).

### 6.2 Campaign rollup (P6)

- Cell statistics from the 7 per-run gate metrics → `rq2v4_cell_stats.csv`; adapt `analysis/rq2/campaign_analysis.py` (v3 CLI shape `--run label:mode:path`) and `cli_simple_compare.py` into `rq2v4` variants as needed (P6.1).
- Figures: relief per regime (D12/D14 legs), latency per regime/kind, engagement timelines, cross-mode comparisons per the repository graph skill; archived under `docs/operation/testing/experiment/v4/rq2/graphs/<ts>/`.
- Deliverables synced back to the repo: `results.md`, `post_run_analysis.md`, `rq2v4_cell_stats.csv`, `rq2v4_run_status.csv`, figures; then the dossier update (`tese/research_questions/rq2/` — P6.3, including the v3-era ba-relief 9/10 → 8/10 note fix).

### 6.3 Retention & sync

- **VM (`cloud-vm-rq2`):** full retention of all 98 run folders + controller logs until P6 completes; **slim-archive only after analysis** (P5.2, the Part D lesson). Controller logs retained on the VM indefinitely (v3 precedent). Disk-headroom check at P5.1 for the whole campaign.
- **Repo:** only the P6 deliverables above (no run folders, no controller logs, no `phases.json` variants — P4.1).

## 7. Open questions for the author

1. **Q1 — TELEMETRY_SOURCE pin:** plan proposes `zmq` (controller default; what the battery, P2 and P3 actually ran). Divergence recorded: the v3 RQ2 era ran `event_preserving`. Confirm `zmq` or name the alternative before P5.
2. **Q2 — SCALEUP_POLICY pin:** plan proposes `dual` everywhere. Per-window per-tier scores (`compute_score`/`storage_score` + thresholds) are available for **every** campaign run via the post-run `policy_state.csv` reconstruction, so the P3 BA delta (20-column decision rows) buys nothing in-campaign and stays reserved for diagnostic re-runs. Confirm the `dual`-everywhere pin.
3. **Q3 — data-bound re-calibration:** the db regime is the **v3 shape carried** (rate 5.0, lookup 0.9, `EDGE_CPUS` 1.20, member 0.15, v3 pool 12) — **not re-calibrated on the repaired platform** at v4's pool 6 (launcher-pinned; v3 read-spread evidence is pool-12-era). Recommend authorizing a **2-run db re-anchor preflight before P5** (`none_db` + `stor_db`, seed 42, §3.1 db config): it doubles as the db press witness at the carried shape. Without it, a db MC1 failure mid-campaign costs regime time. The preflight would need to be added to the P5.1 preflight list.
4. **Q4 — cb `STORAGE_CPUS`:** plan pins **0.15** (launcher default; what P2 seat runs used; the value is inert under a hash-only mix). Alternative: v3-precedent 0.08. Confirm inert-0.15 is acceptable for the 3×3 (it is the most faithful to the calibration era).
5. **Q5 — seed list:** confirm **42–48** (42 = calibration seed; 43–48 spread the demand stream). Any seed change re-derives §3.2's block table.
6. **Q6 — non-episode mix strip:** confirm stripping `service_pressure` from non-episode phases and renormalising to `{content_lookup: 0.706, feed_ranking: 0.294}` in all three regimes (P4.1 authorised P4 to decide; P3 calibration left those phases untouched).
7. **Q7 — db pool:** confirm running db cells at launcher-default pool **6** (no launcher change) with the D14 read shares descriptive, or mandate pool 12 (requires a launcher edit + re-validation — a P5.1 blocker).
8. **Q8 — 5 % timeout ceiling** applies only to pre-registered-recovery cells (§5.2 G4); comparator cells are exempt. Confirm.
9. **Q9 — `stor`@mx storage expectation:** confirm the pre-registered wording "measured, not assumed — partial or no relief is a reportable outcome" (P3 §7), so the analyzer does not read an unrelieved `stor`@mx cell as a gate failure.
10. **Q10 — quota comparability caveat:** confirm recording the mixed@0.05 vs data-bound@0.15 non-comparability (§2.3, D13) as a stated limitation rather than re-seating either regime.
11. **Q11 — instrumentation (P3 finding):** per-read/per-connection storage-member attribution **does not exist** in run artifacts (see Appendix E). Plan proposes **no new instrumentation for P5** (D14's CPU leg carries the storage gates; shares stay descriptive) and parking attribution work post-campaign. If the author wants attribution in-run, that is a P4/P5 blocker and must be designed and implemented before P5.1 — say so now.
12. **Q12 — time-to-relief endpoint:** confirm the plan-defined endpoint (§5.2 G1/G2: first add/activation → first qualifying window) as the D12/D14 recorded measurement.
13. **Q13 — block counterbalance residual:** confirm the Latin-square rows of §3.2 (first-position 2/2/2/1), the per-regime seed rotation, and the fixed regime order cb → mx → db.
14. **Q14 — F2 confirmation status:** `rq2v4_p1_05_verification.md` §5.2 required one F2 confirmation during P2 calibration ("if present → reopen as a platform finding before P4"); the P2/P3 records state quiescence held in all episodes but carry no formal verdict. Confirm the F2 confirmation is discharged, or carry a dedicated check into P5.1 (first block + host-sampler review).
15. **Q15 — block-level manipulation checks:** the parent P4.1 wording says "manipulation checks as per-run inclusion criteria", while §5.1 makes MC1 (press) and MC4 (margin) **block-level**, evaluated on the `none` run — on the grounds that press/margin are properties of the workload shape, identical across the block's four runs, and the `none` run is the only artifact that evidences them cleanly. Confirm the deviation (or demand per-run checks, which changes the inclusion mechanics).

## Ready for review

Decide the following — P4.2 auto-review already ran (3 rounds, all 🔴/🟡 findings fixed); P4.3 approval follows and the plan freezes on R1–R16 sign-off:

- **R1** Approve `TELEMETRY_SOURCE=zmq` pin (Q1).
- **R2** Approve `SCALEUP_POLICY=dual` everywhere; BA delta diagnostic-only (Q2).
- **R3** Sanction creating `source/scripts/testing/controller_env_overrides/rq2v4_p4_pins.env` (2 keys) at P5.1 preflight — **blocker until created**.
- **R4** Approve the db re-anchor preflight (Q3) or accept the db carry as-is.
- **R5** Confirm cb `STORAGE_CPUS=0.15` inert (Q4).
- **R6** Confirm seeds 42–48 (Q5).
- **R7** Confirm non-episode mix strip (Q6).
- **R8** Confirm pool 6 for db (Q7).
- **R9** Confirm 5 % ceiling scope (Q8).
- **R10** Confirm `stor`@mx "measured, not assumed" wording (Q9).
- **R11** Confirm the quota comparability caveat stands recorded (Q10).
- **R12** Confirm instrumentation is parked, not a P5 blocker (Q11).
- **R13** Confirm time-to-relief endpoint definition (Q12).
- **R14** Confirm block ordering rows + per-regime seed rotation + fixed regime order (Q13).
- **R15** Confirm F2 confirmation status (Q14).
- **R16** Confirm block-level MC1/MC4 vs the P4.1 per-run wording (Q15).

**P4.3 — SIGNED OFF 2026-10-12 (author): R1–R16 approved as recommended.**
Recorded deviations: **R4** db re-anchor preflight **approved** (2 runs at
P5.1, seed 42: `none` + `stor`); **R12** instrumentation parked
(post-campaign; D14 CPU leg carries the storage gates); **R15** F2
confirmation carried into P5.1 (host sampler at 1 Hz + first-block
review). The plan freezes with this sign-off.

## Appendix

### A. Prerequisites (P5.1 preflight checklist)

1. `rq2v4_p4_pins.env` exists (R3) with exactly `SCALEUP_POLICY=dual` and `TELEMETRY_SOURCE=zmq`.
2. Image/config hashes recorded: edge image `12c9ef0dc4b7` (hash kind), `local_state_server` image id, VM checkout HEAD; lockstep asserted (P1.3 precedent).
3. Canonical `phases.json` at the regime-1 (cb) state; P5.1 verifies the canonical file matches the intended regime JSON before each run and that `phases_snapshot.json` equals it post-run (D3).
4. Disk-headroom check for ≈98 run folders full retention; `sudo -n` verified non-interactive.
5. Host sampler `source/scripts/testing/rq2v4_p1_04_host_sampler.py` running at 1 Hz for every run (F2 attribution aid).
6. Launcher dry-run (label validation, merge output inspection) before the first block.
7. (Conditional on R4) db re-anchor preflight pair executed and verdicts recorded.
8. Campaign status CSV `rq2v4_run_status.csv` created (columns: label, mode, regime, seed, block, ts, edge_cpus, storage_cpus, validity, exclusion_cause).

### B. Checkpoints (read-only, between runs)

| Trigger | Check | Answers |
| --- | --- | --- |
| Episode start + ~3 min | `none`: lock appearing (p95 rising ≥1 s); telemetry windows continuous | MC1/MC4 early signal, F1 |
| First expected add window | engagement rows in controller logs; spawn counts per mode | MC2/MC3 early signal |
| Episode end | 0 `triggering removal` lines; completion/timeout classes present | MC5, I2 |
| Between runs | `phases_snapshot.json` + `controller_env_snapshot.env` present in the run folder | D3 |
| Each regime's first completed block | **Author directive (D16): block-1 ordering gate** — the aligned mode(s) (`both` ≈ the regime-aligned single) must beat `none` ≈ the misaligned single on episode completion + p50; for db additionally the edge must be well below the member (no compute-side impedance of the storage press). Violation → stop + report | cb seed-42 ✓ 2026-10-13 (`both`/`comp` 100 % @ 0.16–0.21 s vs `stor`/`none` 98.7/96.1 % @ 2.2–2.6 s); **mx seed-45 ✓ 2026-10-13** (`both`/`comp` 99.2/98.8 % @ 0.009–0.010 s vs `stor`/`none` 75.7/71.7 % @ 9.2–10.0 s); **db preflight ⚠ — `stor` ≈ `none` (91.3/93.5 %; edge 39 % vs member 68–74 %) — read-only investigation scheduled before the db blocks** |

### C. Validity threats & limitations

- **db regime carried, not re-calibrated** (Q3): the v3 bind numbers (66–74 % member CPU, pool-12 read spread) may not transfer to the repaired platform at pool 6; MC1's 50 % floor is a conservative carrier, not a measured v4 knee.
- **Read-path pinning (D18, [`rq2v4_p5_02_read_path_pinning.md`](rq2v4_p5_02_read_path_pinning.md)):** storage reads move only through newly born connections; with a fixed edge set, members admitted mid-press receive no reads — `stor`@db and `stor`@mx cells are expected to show no storage relief (measured, explained, not a gate failure). `both` storage relief is downstream of the compute spawn (new edge pools).
- **Quota comparability (D13):** mixed@0.05 vs data-bound@0.15 storage presses are quota-relative and must not be pooled cross-regime.
- **`stor`@mx storage arm:** P3 n=1 pilot showed no relief; the 7-replicate cell may confirm, contradict, or split — all are reportable.
- **Read-share evidence is sampled** (≈1 sample/window) and descriptive only (D14).
- **Single-host testbed:** F2 host-interference is mitigated by the quiescence protocol and the host sampler, not eliminated; F2 confirmation status is an open author item (Q14).
- **Counterbalance residual:** mode first-position counts are 2/2/2/1 (7 blocks ≠ multiple of 4); within-regime seed order is rotated per regime (§3.2) to decorrelate seed position from time-of-day.
- **Sequential regime-shift variant (D7) is out of scope** and is never a fallback for a failed mixed cell (P3 gate).

### D. Artifact contract

Standard run-folder layout per [`../../../analysis_toolchain.md`](../../../analysis_toolchain.md): `client_requests.csv`, `resource_stats.csv` (+`_debug`), `per_node_stats.csv`, `policy_state.csv`, `container_events.csv`, `elasticity_events.csv`, `run_status.json`, `controller_lan1.log`/`controller_lan2.log`, `service_logs/`, `controller_env_snapshot.env`, `phases_snapshot.json`, `analysis/` (populated per §6.1). Reconstruction tooling lives in `source/scripts/tools/` (`parse_elasticity_logs.py`, `reconstruct_policy_state.py`). Campaign-specific evidence: selection-log lines `spread band=`/`floor=` (D12 window start), `[scale-up] compute fired` / `[scale-up] storage fired` / `action_type=scale_up, action=ComputeAlert` / `reserve_activate,storage_lanN` / `[reserve] activated` (M1/G1/G2 anchors), `triggering removal` (MC5), host sampler CSV, and the campaign status CSV `rq2v4_run_status.csv` (the authoritative per-run validity/exclusion record — §5.5, §6.1).

### E. Instrumentation note (P3 finding — carried, not designed)

The P3 `mx_stor` finding established that **run artifacts carry no per-read / per-connection storage-member attribution**: connections and read shares diverge across modes, and why reads moved under `mx_both` but not `mx_stor` is unestablished ([`rq2v4_p3_00_levers.md`](rq2v4_p3_00_levers.md) §7). This plan does **not** invent instrumentation that does not exist: D14 gates storage relief on the robust CPU leg, and read shares are reported descriptively from the existing sampled counters. Adding member attribution in the read/flow-install path is a parked post-campaign item — see Q11/R12; it is a P4/P5 blocker only if the author orders it.

## Changelog

| Date | Change | Rationale |
| --- | --- | --- |
| 2026-10-12 | Authored P4.1 plan (84-run matrix, gates, mechanics, open questions); auto-review rounds 1–3 — all critical/warning findings fixed; freezing pending R1–R16 sign-off | P4.1/P4.2 of `rq2v4_plan.md` |
| 2026-10-13 | Author directive D16: first-block ordering gate per regime + db edge-headroom check; db preflight pair recorded (`stor` ≈ `none`, edge 39 % vs member 68–74 % ⇒ not edge-impeding); read-only investigation scheduled before the db blocks | author request (2026-10-13) |
