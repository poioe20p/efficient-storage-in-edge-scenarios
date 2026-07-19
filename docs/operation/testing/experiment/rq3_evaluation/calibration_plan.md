# Phase 1a — Resource Constraint Tightening

**Date**: 2026-07-13
**Status**: 📋 Designed
**Depends on**: Step 1 code fixes (applied 2026-07-13 — all CPU/memory limits env-driven)
**Purpose**: Find the `STORAGE_CPUS` and `EDGE_CPUS` combination that produces ~60% CPU utilisation during stress phases, creating a meaningful overload signal for the RQ3 trigger-quality comparison.

---

## 1. Intent

Before RQ3 can compare trigger modes (degradation_score vs cpu_only vs latency_only), the system must experience **real overload** — CPU must reach levels where the trigger clearly fires and the three modes can diverge. The golden config's resource limits (`STORAGE_CPUS=0.10`, `EDGE_CPUS=0.30`) produce CPU utilisation too low for a meaningful comparison (storage ~20–40%, edge ~2–8%).

This calibration progressively tightens Docker CPU limits until both storage and edge containers reach ~60% CPU during their respective stress phases (`storage_storm` pre-scale window for storage, `compute_spike` for edge). The winner is the tightest config where the controller still successfully scales and recovers.

System degradation (up to ~35% failure rate pre-scale) is acceptable — it proves the overload exists and gives the controller something to fix.

---

## 2. Hypothesis / Expected Outcome

1. **As CPU limits tighten, stress-phase utilisation rises monotonically.** The relationship is roughly inverse-linear: halving `--cpus` roughly doubles CPU% until the container hits its functional floor (MongoDB WiredTiger, Flask+Gunicorn baseline overhead).
2. **Storage CPU will saturate before edge CPU.** Storage containers run MongoDB — CPU-intensive under write/aggregation load at 90% cross-region. Edge containers run Flask + Gunicorn — mostly I/O-bound waiting on MongoDB responses. Storage will reach 60% at a less aggressive tightening than edge.
3. **Below some floor, containers will fail.** MongoDB needs a minimum CPU budget for WiredTiger cache management, replication heartbeats, and RS consensus. Flask+Gunicorn needs CPU for request parsing and HTTP framing. The calibration will find the floor without crossing it.
4. **The winning config will be asymmetric.** Storage may need `STORAGE_CPUS=0.04` to reach 60% while edge may need `EDGE_CPUS=0.06` to reach the same level — or vice versa. Independent axes let us tune each tier separately.

---

## 3. Independent Variable & Held-Constant Set

### Independent Variables

| Variable         | C0 (golden) | Range        | Controls                                                     |
| ---------------- | ----------- | ------------ | ------------------------------------------------------------ |
| `STORAGE_CPUS` | 0.10        | 0.10 → 0.02 | CPU allocation for all storage containers (static + dynamic) |
| `EDGE_CPUS`    | 0.30        | 0.30 → 0.03 | CPU allocation for all edge containers (static + dynamic)    |

### Held Constant

| Parameter                              | Value                            | Rationale                                                |
| -------------------------------------- | -------------------------------- | -------------------------------------------------------- |
| `WAN_RTT_MS`                         | 260                              | Golden config — cross-region penalty visible            |
| `CLIENTS`                            | 48                               | Golden config — storage and Tier 1 stress               |
| `CONTENT_ITEMS`                      | 6000                             | Golden config — dataset cardinality                     |
| `USERS`                              | 100                              | Golden config                                            |
| `RANDOM_SEED`                        | 42                               | Reproducible request sequence                            |
| `STORAGE_MEMORY`                     | 512m                             | Golden config — unchanged                               |
| `EDGE_MEMORY`                        | 256m                             | Golden config — unchanged                               |
| `SS_ENABLED`                         | 1                                | Golden config — Tier 1 selective sync active            |
| `STORAGE_PERSISTENT_RESERVE_ENABLED` | 1                                | Golden config — storage reserve enabled                 |
| `VIP_HARD_TIMEOUT`                   | 60                               | Golden config                                            |
| Controller env override                | `current_state_integrated.env` | Golden config — unchanged trigger thresholds            |
| Phases file                            | `phases.json`                  | Canonical 7-phase workload                               |
| `BACKEND_SELECTION_POLICY`           | `topology_lifecycle` (default) | System baseline                                          |
| `MAX_DYNAMIC_STORAGE`                | 5                                | Code default — max storage nodes                        |
| `MAX_DYNAMIC_COMPUTE`                | 6                                | Code default — max compute nodes                        |
| `SCALEUP_COMPUTE_COOLDOWN_S`         | 45                               | Code default — prevents rapid successive compute spawns |
| `SCALEUP_STORAGE_COOLDOWN_S`         | 120                              | Code default — prevents rapid successive storage spawns |

---

## 4. Run Matrix

| #            | Label                   | `STORAGE_CPUS` | `EDGE_CPUS`  | Expected Storage CPU (pre-scale) | Expected Edge CPU (pre-scale) | Rationale                                                         |
| ------------ | ----------------------- | ---------------- | -------------- | -------------------------------- | ----------------------------- | ----------------------------------------------------------------- |
| **C0** | `cal_c0_golden`       | 0.10             | 0.30           | 20–46%                          | 2–8%                         | Golden baseline — measure current levels                         |
| **C1** | `cal_c1_stor_006`     | **0.06**   | 0.30           | 35–60%                          | 2–8%                         | Tighten storage only — test if storage reaches 60% alone         |
| **C2** | `cal_c2_edge_008`     | 0.10             | **0.08** | 20–46%                          | 8–25%                        | Tighten edge only — test if edge reaches meaningful levels alone |
| **C3** | `cal_c3_both_mod`     | **0.06**   | **0.08** | 35–60%                          | 8–25%                        | First combined tightening                                         |
| **C4** | `cal_c4_both_tight`   | **0.04**   | **0.06** | 50–75%                          | 10–35%                       | Aggressive both tiers                                             |
| **C5** | `cal_c5_both_vtight`  | **0.03**   | **0.04** | 60–85%                          | 15–50%                       | Very aggressive — may hit stability limits                       |
| **C6** | `cal_c6_edge_heavier` | **0.04**   | **0.03** | 50–75%                          | 20–60%                       | Invert edge/storage ratio — if C4/C5 edge still low at 0.06/0.04 |

**Run order**: C0 → C1 → C2 → C3 → C4 → C5. Run C6 only if edge CPU remains <40% after C5.

**Early termination**: Stop if a config causes static node OOM kill or controller traceback. The previous config is the winner.

**Per-run duration**: ~24 min (7-phase workload) + ~5 min between-run overhead (cleanup + reboot) → **~29 min/run**. Full matrix: **~3 h** (7 runs max).

---

## 5. Run Configuration

All runs use the canonical launch command with resource overrides:

```bash
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  RUN_LABEL=<label> \
  PHASES_CONFIG=testing/phases.json \
  WAN_RTT_MS=260 CLIENTS=48 CONTENT_ITEMS=6000 USERS=100 \
  STORAGE_CPUS=<value> EDGE_CPUS=<value> \
  STORAGE_MEMORY=512m EDGE_MEMORY=256m \
  RANDOM_SEED=42 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
```

| Run | `RUN_LABEL`           | `STORAGE_CPUS` | `EDGE_CPUS` |
| --- | ----------------------- | ---------------- | ------------- |
| C0  | `cal_c0_golden`       | 0.10             | 0.30          |
| C1  | `cal_c1_stor_006`     | 0.06             | 0.30          |
| C2  | `cal_c2_edge_008`     | 0.10             | 0.08          |
| C3  | `cal_c3_both_mod`     | 0.06             | 0.08          |
| C4  | `cal_c4_both_tight`   | 0.04             | 0.06          |
| C5  | `cal_c5_both_vtight`  | 0.03             | 0.04          |
| C6  | `cal_c6_edge_heavier` | 0.04             | 0.03          |

**Images**: No rebuild needed — CPU/memory limits are Docker runtime flags, not image properties.

**Between-run protocol**: `cleanup.sh -r` (containers + volumes) + VM reboot. Same as RQ1 v3 / RQ2.

> **⚠ Resource variable provenance**: `STORAGE_CPUS`, `EDGE_CPUS`, `STORAGE_MEMORY`, and `EDGE_MEMORY` are passed as `-e` Docker flags at launch, NOT written into the controller env override file. They will **not** appear in `controller_env_snapshot.env`. The `RUN_LABEL` convention (e.g., `cal_c3_both_mod`) encodes the resource values implicitly, but the runner should also append the resource vars to a `resource_config.env` file in the run folder after each run for explicit traceability.

---

## 6. Focus & Evidence

### Primary Evidence

| Artifact               | What to measure                                                              | Purpose                         |
| ---------------------- | ---------------------------------------------------------------------------- | ------------------------------- |
| `resource_stats.csv` | `avg_storage_cpu_percent` during `storage_storm` (first 60s, pre-scale)  | Storage CPU under stress        |
| `resource_stats.csv` | `average_cpu_percent` during `compute_spike` (first 60s, pre-scale)      | Edge CPU under stress           |
| `resource_stats.csv` | `avg_storage_cpu_percent` during `storage_storm` (t ≥ 180s, post-scale) | Storage CPU drop after scale-up |
| `resource_stats.csv` | `average_cpu_percent` during `compute_spike` (t ≥ 120s, post-scale)     | Edge CPU drop after scale-up    |

### Secondary Evidence

| Artifact                                          | What to check                               | Purpose                              |
| ------------------------------------------------- | ------------------------------------------- | ------------------------------------ |
| `container_events.csv`                          | `event=added` during stress phases        | Confirm scale-up fired               |
| `elasticity_events.csv`                         | ComputeAlert / DataAlert timestamps         | Confirm controller detected overload |
| `controller_lan1.log` / `controller_lan2.log` | Tracebacks, OOM markers, scale-up decisions | Stability check                      |
| `client_requests.csv`                           | Success rate, timeout rate                  | Acceptable degradation ceiling       |

### Measurement Protocol (per run)

1. **Pre-scale storage CPU**: Mean of `avg_storage_cpu_percent` for rows where `phase=storage_storm AND relative_time ≤ 60s`.
2. **Post-scale storage CPU**: Mean of `avg_storage_cpu_percent` for rows where `phase=storage_storm AND relative_time ≥ 180s` (last 60s of the 240s phase, after spawn has completed).
3. **Storage CPU drop**: pre-scale − post-scale. Target: visible drop (any magnitude — proves scale-up relieved pressure).
4. **Pre-scale edge CPU**: Mean of `average_cpu_percent` for rows where `phase=compute_spike AND relative_time ≤ 60s`.
5. **Post-scale edge CPU**: Mean of `average_cpu_percent` for rows where `phase=compute_spike AND relative_time ≥ 120s` (last 60s of the 180s phase, after spawn has completed).

> **Note on post-scale CPU aggregation**: `resource_stats.csv` averages across ALL nodes of a tier. After a scale-up, the new (low-CPU) node pulls the mean down even if the static node is still saturated. This compositional drop is acceptable — it still proves scale-up distributed load. If `per_node_stats.csv` is available, cross-check per-node CPU to confirm genuine relief on the static node.

> **Window rationale**: Storage cooldown 120s + `REQUIRED=2` → earliest trigger T+140s + 30–90s spawn (docker run + RS join + data sync) → earliest ready T+170–230s, so ≥180s is the safe lower bound for post-scale measurement. Compute cooldown 45s + `REQUIRED=3` → earliest trigger T+65–75s (3 of first 3–4 windows after cooldown) + 30–60s spawn → earliest ready T+95–135s, so ≥120s is the safe lower bound. The 60s pre-scale / last-60s post-scale windows cover both tiers safely.

---

## 7. Success Criteria

### Per-Run Gate

| # | Metric                                        | Target                                                                                |
| - | --------------------------------------------- | ------------------------------------------------------------------------------------- |
| 1 | System liveness                               | No static node OOM kills; controller traceback-free                                   |
| 2 | Pre-scale storage CPU during`storage_storm` | Recorded — compare across runs                                                       |
| 3 | Pre-scale edge CPU during`compute_spike`    | Recorded — compare across runs                                                       |
| 4 | Scale-up fires                                | ≥1 storage spawn during`storage_storm`; ≥1 compute spawn during `compute_spike` |
| 5 | Post-scale CPU drops                          | Any visible drop — proves scale-up relieved pressure                                 |

### Winner Selection

The **winning config** is the tightest (lowest C-number) that satisfies:

1. **Both tiers reach ≥60% CPU** during their stress phases (pre-scale window), **OR** if no config reaches 60%, the one with the highest CPU
2. **Scale-up fires** for both tiers
3. **System remains alive** — no static node OOM, no controller traceback
4. **Dynamic node failures acceptable** — up to ~35% overall failure rate proves overload exists

**Tie-break**: If two configs both reach ≥60% for both tiers, choose the tighter one (lower CPU allocation — more resource-efficient). If neither tier reaches 60% in any config, the calibration has failed — edge and storage workloads may not be CPU-bound. In that case, reassess whether memory (rather than CPU) is the bottleneck and whether RQ3 should target memory pressure instead.

---

## 8. Validity Threats

| Threat                                                                                                                                                                                                                                                                             | Mitigation                                                                                                                                                                                                                                                                                                                                                           |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **CPU may not be the bottleneck for edge servers.** Flask+Gunicorn serving cached Tier 1 reads may be entirely I/O-bound waiting on MongoDB. Edge CPU may never reach 60% regardless of constraint tightening.                                                               | The independent`STORAGE_CPUS` and `EDGE_CPUS` axes let us find each tier's limit independently. If edge CPU stays low even at `EDGE_CPUS=0.03`, edge is I/O-bound — the trigger comparison shifts to storage-only, and RQ3's edge-compute trigger question becomes "does trigger composition matter when the service is I/O-bound?" — still a valid finding. |
| **MongoDB may hit a functional CPU floor.** Below some `STORAGE_CPUS` threshold, WiredTiger cache eviction, replication heartbeats, and RS consensus may fail, causing OOM or replica-set instability.                                                                     | C5 (0.03) is the lower bound. If it fails, C4 (0.04) is the floor. The calibration naturally discovers the floor.                                                                                                                                                                                                                                                    |
| **Single replicate per config.** n=1 per CPU combination — cannot estimate within-config variance.                                                                                                                                                                          | This is a calibration, not an evaluation. The goal is binary: find the config that reaches ≥60% CPU. If a config is borderline (58–62%), re-run once to confirm. The RQ3 evaluation itself uses n=3 replicates per trigger mode.                                                                                                                                   |
| **Cooldown interference.** `SCALEUP_STORAGE_COOLDOWN_S=120` means a storage spawn during `tier1_hotspot` could suppress the `reverse_hotspot` spawn.                                                                                                                   | Acceptable — the calibration's goal is to see ANY scale-up during stress and ANY CPU drop post-scale. The specific spawn count is not being evaluated.                                                                                                                                                                                                              |
| **RANDOM_SEED=42 may produce an atypical request sequence for this specific calibration.** Different CPU limits change container startup timing, which changes when requests hit warmed vs cold backends.                                                                    | The seed ensures the request TYPE sequence is identical. Timing variation is inherent to the system. If a run's result is surprising (e.g., CPU lower than expected), re-run once before concluding.                                                                                                                                                                 |
| **reverse_hotspot compute cooldown bleed.** `reverse_hotspot` (95% cross-region, 5 req/s, 180s) runs immediately before `compute_spike`. If it triggers compute scale-up, the 45s cooldown could bleed into `compute_spike`, suppressing the intended compute trigger. | The 300s`inter_hotspot_cooldown` likely drains all dynamic compute nodes before `reverse_hotspot` starts, making a new spawn in `reverse_hotspot` unlikely. Monitor `container_events.csv` to confirm no bleed.                                                                                                                                              |
| **Baseline warm-up artifacts.** `baseline` phase is only 60s at 1 req/s — MongoDB WiredTiger cache and RS heartbeats may still be stabilizing. The first 60s of `storage_storm` (pre-scale window) may include warm-up artifacts.                                       | C0's golden-config measurements should be compared against known golden baselines. If C0 shows unexpectedly low CPU, extend baseline to 120s via a`phases_override` file for subsequent runs.                                                                                                                                                                      |

---

## 9. Artifact Contract

Standard run-folder layout per `docs/operation/testing/testing_overview.md`:

```
metrics/<batch>/<timestamp>_<label>/
├── client_requests.csv
├── resource_stats.csv
├── container_events.csv
├── elasticity_events.csv
├── controller_lan1.log
├── controller_lan2.log
├── controller_env_snapshot.env
├── phases_snapshot.json
└── ...
```

**Post-calibration deliverable**: Updated `golden_config.md` with the winning `STORAGE_CPUS` and `EDGE_CPUS` values, plus a short rationale. No `analysis/` outputs expected from the calibration itself — raw CSV inspection suffices.

---

## 10. After Calibration

Once the winning resource config is identified:

1. **Update `golden_config.md`** — record the new `STORAGE_CPUS` and `EDGE_CPUS` values
2. **Verify with one full run** — confirm the winning config is reproducible
3. **Proceed to Phase 1b** (weight recalibration) — only if the degradation score misbehaves under the new constraints (fires too early, too late, or not at all)
4. **Proceed to RQ3 evaluation** — 9 runs (3 modes × 3 replicates) with the calibrated resource config

---

## Related Documents

| Document                                                                                                       | Purpose                                       |
| -------------------------------------------------------------------------------------------------------------- | --------------------------------------------- |
| [`golden_config.md`](../../golden_config.md)                                                                  | Current golden config baseline                |
| [`mechanism_necessity/v5_calibration`](../../stability/mechanism_necessity/experiment_plan_v5_calibration.md) | Prior resource calibration pattern            |
| [`rq3.md`](../../../../research_questions/rq3.md)                                                             | RQ3 research question this calibration serves |
| [`scaling_config.py`](../../../../source/sdn_controller/scaling_config.py)                                    | Trigger weight/threshold configuration        |
| [`scaling_policy.py`](../../../../source/sdn_controller/scaling_policy.py)                                    | Degradation score implementation              |

---

# Phase 1b — Threshold Recalibration

**Status**: ❌ Failed — see Phase 1c · **Date**: 2026-07-13
**Depends on**: Phase 1a winner (C4: `STORAGE_CPUS=0.04`, `EDGE_CPUS=0.06`)
**Purpose**: Raise trigger thresholds so the degradation score does not fire during baseline but still fires during stress phases, given the elevated CPU floor at C4 resource constraints.

> ⚠️ **Outcome (2026-07-13)**: T0–T3 all produced 4 baseline false positives (2 compute + 2 storage spawns during `baseline`). Root cause: at C4, the CPU components of both scores saturate during baseline (compute CPU floor=3→saturates at 13%; storage floor=1.5→saturates at 6.5%). The latency component alone cannot discriminate baseline from stress with sufficient margin. Threshold-only adjustment is insufficient — floors must also be raised. **Superseded by Phase 1c.**

---

## 1. Intent

At C4 resource constraints, CPU utilisation is elevated across ALL phases — including `baseline` (1 req/s, 0% cross-region). The CPU components of both degradation scores **saturate** during baseline:

| Tier    | CPU floor | CPU span | Saturates at | Baseline CPU (C4) | CPU component (baseline) |
| ------- | --------- | -------- | ------------ | ----------------- | ------------------------ |
| Compute | 3%        | 10       | ≥13%        | 40–50%¹           | **0.40** (maxed)   |
| Storage | 1.5%      | 5        | ≥6.5%       | 40–51%¹           | **0.60** (maxed)   |

> ¹ Measured from T0 golden-threshold run at C4 resources (`20260713_141638_cal_c4_both_tight`). Confirmed across T0–T3 runs.

With the golden thresholds (compute 0.20, storage 0.12), the score crosses threshold during baseline on CPU alone — false positives. The latency component (`T_proc`, `T_db`) is the only differentiator between baseline and stress, since CPU saturates in both.

This calibration raises the thresholds to sit **above** the CPU-only baseline score but **below** the CPU+latency stress score. This makes the latency component essential for detection — precisely the condition RQ3 needs to compare degradation_score vs cpu_only vs latency_only.

---

## 2. Independent Variable & Held-Constant Set

### Independent Variables

| Variable                           | Golden | Range        | Controls                  |
| ---------------------------------- | ------ | ------------ | ------------------------- |
| `SCALEUP_COMPUTE_BASE_THRESHOLD` | 0.20   | 0.20 → 0.60 | Compute trigger threshold |
| `SCALEUP_STORAGE_BASE_THRESHOLD` | 0.12   | 0.12 → 0.80 | Storage trigger threshold |

All other thresholds, weights, floors, and spans remain at golden values. Only the base thresholds change.

**Adaptive increment (unchanged)** ⚠️ note different formulas per tier:

- **Compute**: flat **0.10 per spawn**, additive (base + count × 0.10), capped at `SCALEUP_COMPUTE_MAX_THRESHOLD` (0.85).
- **Storage**: **diminishing** per spawn — increment sequence is 0.10, 0.05, 0.05, … (formula: `max(0.10 × 0.5ⁱ, 0.05)` for the i-th dynamic node). Caps at `SCALEUP_STORAGE_MAX_THRESHOLD`.

### Required Companion Overrides

> ⚠️ **CRITICAL**: The code default for `SCALEUP_STORAGE_MAX_THRESHOLD` is **0.55** (see `scaling_config.py`). All storage thresholds in T1–T4 (0.65–0.80) **exceed this cap** and would be silently clamped to 0.55 regardless of the `SCALEUP_STORAGE_BASE_THRESHOLD` setting. Each per-run override file **MUST** also set `SCALEUP_STORAGE_MAX_THRESHOLD` to at least the target threshold (or a fixed high value like **0.90**) so the base threshold actually takes effect.

| Variable                          | Code Default | Required Override               | Reason                                             |
| --------------------------------- | ------------ | ------------------------------- | -------------------------------------------------- |
| `SCALEUP_STORAGE_MAX_THRESHOLD` | 0.55         | **0.90** (for all T1–T4) | Prevents silent clamping of raised base thresholds |

### Held Constant

| Parameter                                 | Value                                                                                                               | Rationale                                                                    |
| ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| `STORAGE_CPUS`                          | **0.04**                                                                                                      | Phase 1a winner                                                              |
| `EDGE_CPUS`                             | **0.06**                                                                                                      | Phase 1a winner                                                              |
| `STORAGE_MEMORY`                        | 512m                                                                                                                | Golden config                                                                |
| `EDGE_MEMORY`                           | 256m                                                                                                                | Golden config                                                                |
| All trigger weights                       | Golden (`SCALEUP_W_CPU=0.40`, `SCALEUP_W_T_PROC=0.60`, `SCALEUP_W_STORAGE_CPU=0.60`, `SCALEUP_W_T_DB=0.40`) | Unchanged                                                                    |
| All floors/spans                          | Golden                                                                                                              | Unchanged                                                                    |
| All cooldowns                             | Golden                                                                                                              | Unchanged                                                                    |
| `SCALEUP_COMPUTE_MAX_THRESHOLD`         | **0.85** (code default)                                                                                       | Compute adaptive cap — unchanged                                            |
| `SCALEUP_COMPUTE_THRESHOLD_INCREMENT`   | **0.10** (code default)                                                                                       | Flat add-per-spawn — unchanged                                              |
| `SCALEUP_STORAGE_THRESHOLD_INCREMENT`   | **0.10** (code default)                                                                                       | Base of diminishing sequence — unchanged                                    |
| `SCALEUP_STORAGE_MIN_INCREMENT`         | **0.05** (code default)                                                                                       | Floor of diminishing sequence — unchanged                                   |
| `SCALEUP_COMPUTE_PEER_RELIEF`           | **0.03** (code default)                                                                                       | Peer-to-peer relief — unchanged                                             |
| `SCALEUP_COMPUTE_PEER_HEALTH_THRESHOLD` | **0.35** (code default)                                                                                       | Peer health threshold — unchanged                                           |
| `SCALEUP_STORAGE_MAX_THRESHOLD`         | **NOT held constant**                                                                                         | ⚠️ Must be raised to 0.90 per run (see Required Companion Overrides above) |
| Workload, topology, scale                 | Same as Phase 1a                                                                                                    | `WAN_RTT_MS=260`, `CLIENTS=48`, `RANDOM_SEED=42`, etc.                 |

### Score Math (Reference)

**Compute**: `score = 0.40 × sat((CPU% − 3)/10) + 0.60 × sat((T_proc_ms − 15)/80)`

- CPU component: 0.40 at ≥13% CPU (which is ALL phases at C4)
- Latency component: 0 at ≤15ms, ramps to 0.60 at ≥95ms
- Baseline expected score: **~0.40** (CPU maxed, latency near floor)
- Stress expected score: **0.44–0.66** (CPU maxed + latency 20–50ms)

**Storage**: `score = 0.60 × sat((CPU% − 1.5)/5) + 0.40 × sat((T_db_ms − 60)/250)`

- CPU component: 0.60 at ≥6.5% CPU (which is ALL phases at C4)
- Latency component: 0 at ≤60ms, ramps to 0.40 at ≥310ms
- Baseline expected score: **~0.60** (CPU maxed, T_db near floor)
- Stress expected score: **0.66–1.00** (CPU maxed + T_db 100–2000ms)

### Threshold Headroom (C4 Resources)

> The baseline-stress score margins are razor-thin. This table shows exactly what T_proc / T_db values would cause false positives at each threshold level, giving the operator actionable awareness of how tight the margins are.

**Compute** (baseline score ≈ 0.40, CPU-saturated at 0.40):

| Threshold | Headroom | T_proc that causes FP during baseline |
| --------- | -------- | ------------------------------------- |
| T1 = 0.45 | 0.05     | ≥ ~22 ms                             |
| T2 = 0.50 | 0.10     | ≥ ~28 ms                             |
| T3 = 0.55 | 0.15     | ≥ ~35 ms                             |
| T4 = 0.60 | 0.20     | ≥ ~42 ms                             |

**Storage** (baseline score ≈ 0.60, CPU-saturated at 0.60):

| Threshold | Headroom | T_db that causes FP during baseline |
| --------- | -------- | ----------------------------------- |
| T1 = 0.65 | 0.05     | ≥ ~91 ms                           |
| T2 = 0.70 | 0.10     | ≥ ~122 ms                          |
| T3 = 0.75 | 0.15     | ≥ ~154 ms                          |
| T4 = 0.80 | 0.20     | ≥ ~185 ms                          |

---

## 3. Run Matrix

| #            | Label                    | Compute Threshold | Storage Threshold | `SCALEUP_STORAGE_MAX_THRESHOLD` | Expected Baseline                                                                      | Expected Stress                       |
| ------------ | ------------------------ | ----------------- | ----------------- | --------------------------------- | -------------------------------------------------------------------------------------- | ------------------------------------- |
| **T0** | `cal_t0_golden_thresh` | 0.20 (golden)     | 0.12 (golden)     | 0.55 (code default)               | ❌ FP (score 0.40/0.60 > thresholds)                                                   | ✅ Triggers                           |
| **T1** | `cal_t1_moderate`      | **0.45**    | **0.65**    | **0.90**                    | ⚠️ Borderline (compute at 0.45 could FP if T_proc spikes; storage at 0.65 likely OK) | ✅ Triggers                           |
| **T2** | `cal_t2_sweet`         | **0.50**    | **0.70**    | **0.90**                    | ✅ No FP (both above CPU-only baseline)                                                | ✅ Triggers (latency pushes over)     |
| **T3** | `cal_t3_conservative`  | **0.55**    | **0.75**    | **0.90**                    | ✅ No FP                                                                               | ⚠️ May miss if latency is low       |
| **T4** | `cal_t4_aggressive`    | **0.60**    | **0.80**    | **0.90**                    | ✅ No FP                                                                               | ❌ Likely misses (needs high latency) |

**Run order**: T0 → T1 → T2. Continue to T3/T4 only if T2 produces zero false positives and correct stress triggering.

**Early termination**: Stop at the first config that satisfies all success criteria. If T1 already works (no baseline FP + stress triggers), T1 wins — no need for T2.

**Per-run duration**: ~24 min + ~5 min overhead → **~29 min/run**. Full matrix: **~2.5 h** (5 runs max).

---

## 4. Run Configuration

Same as Phase 1a but with threshold overrides in `current_state_integrated.env`. Since thresholds are in the env override file, each run needs a **temporary env override** or an **additional override file**.

**Option A — Temporary env override files**: Create per-run override files under `testing/controller_env_overrides/`:

- `rq3_cal_t1.env` → golden config + `SCALEUP_COMPUTE_BASE_THRESHOLD=0.45` + `SCALEUP_STORAGE_BASE_THRESHOLD=0.65` + `SCALEUP_STORAGE_MAX_THRESHOLD=0.90`
- `rq3_cal_t2.env` → golden config + `SCALEUP_COMPUTE_BASE_THRESHOLD=0.50` + `SCALEUP_STORAGE_BASE_THRESHOLD=0.70` + `SCALEUP_STORAGE_MAX_THRESHOLD=0.90`
- etc.

**Option B — Edit `current_state_integrated.env` in place** between runs. Simpler but loses provenance.

**Recommendation**: Use temporary override files (Option A) so each run's `controller_env_snapshot.env` captures the exact thresholds used.

### Per-Run Env Override File Content

Each override file is a **copy** of `current_state_integrated.env` with exactly **three** lines replaced (base thresholds + storage max cap). T0 uses `current_state_integrated.env` directly — no override file needed.

**`rq3_cal_t1.env`** (T1 — moderate):

```bash
# Phase 1b threshold calibration — T1 moderate
# Derived from current_state_integrated.env
# (all golden config values copied below, only threshold lines changed)
STORAGE_PERSISTENT_RESERVE_ENABLED=1
SS_ENABLED=1
MAX_DYNAMIC_STORAGE=5
MAX_DYNAMIC_COMPUTE=6
SCALEUP_STORAGE_BASE_THRESHOLD=0.65
SCALEUP_STORAGE_MAX_THRESHOLD=0.90
SCALEUP_COMPUTE_BASE_THRESHOLD=0.45
SCALEUP_CPU_FLOOR=3
SCALEUP_T_PROC_FLOOR=15
SCALEDOWN_COMPUTE_COOLDOWN_S=180
SCALE_DOWN_COMPUTE_REQUIRED=9
SCALEUP_W_STORAGE_CPU=0.60
SCALEUP_W_T_DB=0.40
SCALEUP_STORAGE_CPU_FLOOR=1.5
SCALEUP_STORAGE_CPU_SPAN=5
SCALEUP_T_DB_FLOOR=60
SCALEUP_T_DB_SPAN=250
SCALEUP_STORAGE_REQUIRED=2
SCALEUP_STORAGE_WINDOW_SIZE=5
SCALEUP_STORAGE_COOLDOWN_S=120
VIP_HARD_TIMEOUT=60
```

**`rq3_cal_t2.env`** — same as T1 but `SCALEUP_COMPUTE_BASE_THRESHOLD=0.50` and `SCALEUP_STORAGE_BASE_THRESHOLD=0.70`.

**`rq3_cal_t3.env`** — same as T1 but `SCALEUP_COMPUTE_BASE_THRESHOLD=0.55` and `SCALEUP_STORAGE_BASE_THRESHOLD=0.75`.

**`rq3_cal_t4.env`** — same as T1 but `SCALEUP_COMPUTE_BASE_THRESHOLD=0.60` and `SCALEUP_STORAGE_BASE_THRESHOLD=0.80`.

All T1–T4 files set `SCALEUP_STORAGE_MAX_THRESHOLD=0.90`.

### Launch Command (per run)

```bash
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/rq3_cal_t<N>.env \
  RUN_LABEL=cal_t<N>_<descriptor> \
  PHASES_CONFIG=testing/phases.json \
  WAN_RTT_MS=260 CLIENTS=48 CONTENT_ITEMS=6000 USERS=100 \
  STORAGE_CPUS=0.04 EDGE_CPUS=0.06 \
  STORAGE_MEMORY=512m EDGE_MEMORY=256m \
  RANDOM_SEED=42 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
```

---

## 5. Focus & Evidence

### Primary Evidence

| Artifact                 | What to measure                                                                      | Purpose                                                    |
| ------------------------ | ------------------------------------------------------------------------------------ | ---------------------------------------------------------- |
| `container_events.csv` | `event=added` during `baseline`                                                  | **False positive check** — should be **zero** |
| `container_events.csv` | `event=added` during `storage_storm`                                             | **Storage trigger check** — should be ≥1           |
| `container_events.csv` | `event=added` during `compute_spike`                                             | **Compute trigger check** — should be ≥1           |
| `resource_stats.csv`   | `avg_storage_cpu_percent`, `avg_time_db_ms` during `storage_storm` (first 60s) | Verify storage score exceeds threshold                     |
| `resource_stats.csv`   | `average_cpu_percent`, `avg_time_proc_ms` during `compute_spike` (first 60s)   | Verify compute score exceeds threshold                     |

### Secondary Evidence

| Artifact                                          | What to check                       | Purpose                                    |
| ------------------------------------------------- | ----------------------------------- | ------------------------------------------ |
| `elasticity_events.csv`                         | ComputeAlert / DataAlert timestamps | Cross-check spawn timing against telemetry |
| `controller_lan1.log` / `controller_lan2.log` | Scale-up decision log lines         | Verify score vs threshold at decision time |

---

## 6. Success Criteria

### Per-Run Gate

| # | Metric                                 | Target                                      |
| - | -------------------------------------- | ------------------------------------------- |
| 1 | Compute spawns during`baseline`      | **0** (no false positives)            |
| 2 | Storage spawns during`baseline`      | **0** (no false positives)            |
| 3 | Compute spawns during`compute_spike` | **≥1** (detection works)             |
| 4 | Storage spawns during`storage_storm` | **≥1** (detection works)             |
| 5 | System liveness                        | No static node OOM, no controller traceback |

### Winner Selection

The **winning config** is the one with the **highest thresholds** (most conservative) that satisfies all five per-run gates. Higher thresholds are better because they:

- Maximise separation between baseline and stress scores
- Make the latency component more load-bearing for detection
- Create a stronger contrast for RQ3's cpu_only vs degradation_score comparison

**Tie-break**: If two configs both pass, choose the higher thresholds. If no config passes (all either false-positive or miss stress), the thresholds need floor/span adjustment — not just threshold tuning — which is out of scope for Phase 1b and would require a follow-up calibration.

---

## 7. Validity Threats

> ⚠️ **All Phase 1a validity threats also apply to Phase 1b**: single replicate, cooldown interference, `RANDOM_SEED=42`, baseline warm-up artifacts, and `reverse_hotspot` compute cooldown bleed. See the Phase 1a Validity Threats section (Section 8) for details.

| Threat                                                                                                                                                                                                                                                               | Mitigation                                                                                                                                                                                                                                                                                                                          |
| -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Storage max threshold cap (0.55) silently clamps thresholds.** If `SCALEUP_STORAGE_MAX_THRESHOLD` is not raised alongside `SCALEUP_STORAGE_BASE_THRESHOLD`, all storage thresholds >0.55 are no-ops — the effective threshold stays at 0.55 regardless. | The per-run override files raise`SCALEUP_STORAGE_MAX_THRESHOLD` to 0.90 for all T1–T4 runs. The operator must verify the env snapshot in each run folder to confirm the override took effect.                                                                                                                                    |
| **T_proc / T_db may be near floor during stress at C4 resources.** If latency stays low even during stress (e.g., Tier 1 caching absorbs cross-region reads), the latency component may not push the score above the raised threshold.                         | This would mean the degradation score is indistinguishable from CPU-only at C4 resources — which is a valid finding for RQ3 (trigger composition doesn't matter when latency is masked by caching). If T2 fails because stress latency is too low, reconsider whether the workload needs adjustment to expose I/O-bound behaviour. |
| **Adaptive threshold (0.10 increment per spawn) may suppress subsequent spawns.** If the first spawn raises the effective threshold above the stress score, later spawns are suppressed.                                                                       | This is correct behaviour — the adaptive mechanism prevents spawn storms. The per-run gate only requires ≥1 spawn, not sustained spawning.                                                                                                                                                                                        |
| **The latency-only baseline (compute threshold at 0.55) may be impossible to satisfy.** If T_proc barely exceeds 15ms during compute_spike, the score may never reach 0.55.                                                                                    | This is acceptable — the winner is the highest threshold that still triggers. If that's T1 (0.45/0.65), the calibration succeeded at a lower but still meaningful threshold.                                                                                                                                                       |

---

## 8. After Phase 1b

Phase 1b is **closed — failed**. Proceed to Phase 1c.

---

# Phase 1c — Floor & Workload Recalibration

**Status**: ✅ Complete · **Date**: 2026-07-13 → 2026-07-15
**Depends on**: Phase 1a winner (C4), Phase 1b failure analysis
**Final results**: See [`calibration_results.md`](calibration_results.md)
**Winner config**: `source/scripts/testing/controller_env_overrides/rq3_cal_c3b.env`
**Purpose**: Fix the two root causes that made Phase 1b insufficient:

1. **Storage CPU floors too low** (1.5%): baseline CPU (~50%) saturates the CPU score component, leaving zero headroom for thresholds to discriminate
2. **Compute phase doesn't stress edge CPU**: `feed_ranking` at 65% × 4 req/s produces *less* edge CPU than baseline (61% bas → 47% stress) because edge servers become I/O-wait-bound waiting on MongoDB at STORAGE_CPUS=0.04

---

## 1. Intent

Phase 1c fixes root causes instead of working around them:

| Problem | Fix | Mechanism |
|---|---|---|
| Storage floors too low | Raise `SCALEUP_STORAGE_CPU_FLOOR` + widen `SCALEUP_STORAGE_CPU_SPAN` | Baseline CPU produces partial (not saturated) score, creating threshold headroom |
| Compute phase inverts edge CPU | Redesign `compute_spike` + increase `FEED_INTEGRITY_WORK_FACTOR` | 100% `feed_ranking` at 0% cross-region with 2.5× heavier SHA-256 hashing → edge CPU dominates over I/O wait |
| Baseline edge CPU too high (61%) | Reduce `client_fraction` 0.5→0.10 | Fewer requests during baseline lowers edge CPU to ~31%, creating separation from stress |

### The Compute Fix in Detail

`feed_ranking` at C4 with cross-region reads is I/O-wait-bound: edge servers spend CPU budget queuing for MongoDB responses. Two changes break this dependency:

1. **`cross_region_ratio=0.0`**: all candidate reads are local — MongoDB responds fast even at 0.04 CPUs
2. **`FEED_INTEGRITY_WORK_FACTOR=500`** (default 200): 2.5× more SHA-256 iterations per request — edge CPU work per request increases proportionally while MongoDB work stays constant

Combined with halved request rate (`rate_per_client=2.0` vs 4.0) to avoid oversaturating, the edge becomes compute-bound instead of I/O-bound.

---

## 2. Independent Variables

### Part A — Compute Workload

| Variable | Default | Range | Rationale |
|---|---|---|---|
| `FEED_INTEGRITY_WORK_FACTOR` | 200 | 200 → 800 | Controls edge CPU per `feed_ranking` request |
| Baseline `client_fraction` | 0.10 | Fixed | Set in `phases.json` — Part A winner, targets ~31% baseline edge CPU |
| `compute_spike` mix | 100% `feed_ranking` | Fixed | Set in `phases.json` |
| `compute_spike` `rate_per_client` | 2.0 | Fixed | Set in `phases.json` |
| `compute_spike` `cross_region_ratio` | 0.0 | Fixed | Set in `phases.json` |

### Part B — Storage Floors

| Variable | Golden | Range | Rationale |
|---|---|---|---|
| `SCALEUP_STORAGE_CPU_FLOOR` | 1.5 | 30 → 45 | Raise so baseline CPU (~50%) produces partial score |
| `SCALEUP_STORAGE_CPU_SPAN` | 5 | 15 → 25 | Widen so saturation is gradual |
| `SCALEUP_COMPUTE_CPU_FLOOR` | 3 | TBD after Part A | Raise once baseline edge CPU is known |

### Held Constant

| Parameter | Value |
|---|---|
| C4 resources | `STORAGE_CPUS=0.04`, `EDGE_CPUS=0.06` |
| Controller thresholds | Golden (`COMPUTE_BASE=0.20`, `STORAGE_BASE=0.12`) during measurement; only adjusted in Part C |
| All other golden config | As Phase 1a |
| Phases file | `phases.json` (already edited with baseline `client_fraction=0.10` + `compute_spike` 100% `feed_ranking`) |

---

## 3. Phase & Code Changes (Pre-requisites)

Already applied:

> ⚠️ **Workload change note**: These `phases.json` edits change the workload for ALL phases, not just `compute_spike`. Phase 1a's C4 results were measured under the previous workload (`client_fraction=0.5`, original `compute_spike` mix). Part A **W0 serves as the new C4 baseline** under the modified workload — do not compare W0 results against Phase 1a C4.

> ⚠️ **Canonical file contamination**: After Phase 1c completes, restore `phases.json` to its pre-Phase 1c state to avoid affecting other experiments.

### `phases.json`
- `baseline.client_fraction`: **0.5 → 0.10**
- `compute_spike`: **100% `feed_ranking`**, `rate_per_client=2.0`, `cross_region_ratio=0.0`, duration 180s unchanged

### `build_network_1.sh` & `build_network_2.sh`
- Added `-e FEED_INTEGRITY_WORK_FACTOR=${FEED_INTEGRITY_WORK_FACTOR:-200}` to `edge_server` containers

### How to pass `FEED_INTEGRITY_WORK_FACTOR`

The env var flows from the `make` command line → build script → Docker `-e` flag → edge_server container. Add it to the launch command:

```bash
FEED_INTEGRITY_WORK_FACTOR=500
```

No image rebuild needed — the env var is read at container start by `edge_server_config.py`.

> ℹ️ **WORK_FACTOR provenance**: `FEED_INTEGRITY_WORK_FACTOR` has no automatic capture in run artifacts (unlike `STORAGE_CPUS`/`EDGE_CPUS` which appear in `resource_config.env`). The `RUN_LABEL` encodes it (e.g., `cal_c4_wf500`). The operator should append `FEED_INTEGRITY_WORK_FACTOR=<value>` to `resource_config.env` after each run for explicit traceability.

---

## 4. Run Matrix

### Part A — Compute Phase Validation ✅ COMPLETE

Verify the redesigned `compute_spike` produces correct edge CPU separation. **No floor or threshold changes** — golden defaults throughout.

> **Outcome (2026-07-14)**: WORK_FACTOR=200 with baseline `client_fraction=0.10` achieves 31.2% baseline / 65.5% stress edge CPU — a 34pp gap. W1/W2 (WORK_FACTOR 500/800) are **skipped** — separation is already excellent without increased work factor.

| # | Label | `client_fraction` | Baseline Edge CPU | Compute Spike Edge CPU | Gap | Gate |
|---|---|---|---|---|---|---|
| **W0** | `cal_c4_wf200` | 0.25 | 57.9% | 71.4% | +13pp | ❌ Bas too high |
| **W0.15** | `cal_c4_wf200_f015` | 0.15 | 46.1% | 60.4% | +14pp | ❌ Bas too high |
| **W0.10** | `cal_c4_wf200_f010` | **0.10** | **31.2%** | **65.5%** | **+34pp** | ✅ |

**Run order**: W0 → W0.15 → W0.10. W0.10 was the first config where baseline edge CPU fell within the 30–40% target.

**Winner**: `client_fraction=0.10`, `FEED_INTEGRITY_WORK_FACTOR=200` (default). No work factor increase needed.

### Part B — Storage Floor Calibration ❌ FAILED (no candidate passed)

Using the winning WORK_FACTOR from Part A, calibrate storage CPU floors. **Controller thresholds disabled at 0.90** during measurement to prevent spawns.

> **Outcome (2026-07-14)**: No floor/span combination achieved baseline storage score < 0.35. Even F3 (floor=40, span=25) scored 0.443 — the T_db component alone contributes ~0.25 because baseline T_db (~165–217ms) exceeds the golden T_db floor of 60ms. **CPU floor alone cannot fix this; T_db floor must also be raised.**

| # | Label | Floor | Span | Bas CPU | Bas T_db | Bas Score | Stress Score | <0.35? |
|---|---|---|---|---|---|---|---|---|
| **F0** | `cal_c4_f0` | 1.5 | 5 | 46.6% | 165ms | 0.710 | 1.000 | ❌ |
| **F1** | `cal_c4_f1` | 30 | 15 | 48.5% | 165ms | 0.709 | 1.000 | ❌ |
| **F2** | `cal_c4_f2` | 35 | 20 | 46.1% | 216ms | 0.428 | 1.000 | ❌ |
| **F3** | `cal_c4_f3` | 40 | 25 | 48.0% | 217ms | 0.443 | 1.000 | ❌ |

**Root cause**: `SCALEUP_T_DB_FLOOR=60` was calibrated for golden config where baseline T_db was ~10ms. At C4 resources, baseline T_db is 165–217ms — 3× higher. The T_db component `0.40 × sat((T_db−60)/250)` produces ~0.25 contribution at baseline regardless of CPU floor. **Fix in Part C**: raise T_db floor to 120ms alongside CPU floor to 40.

### Part C — Combined Floor & Threshold (3 runs)

#### C1 Results (Measurement Run)

> **Completed 2026-07-14** · `20260714_153648_cal_c4_c1` · 17 spawns, full workload completed.

**Actual baseline metrics** (from `resource_stats.csv`, per-network):

| Network | edge_cpu | T_proc | stor_cpu | T_db |
|---------|----------|--------|----------|------|
| lan1 (active) | 52.7% | 46.3ms | 49.0% | 406ms |
| lan2 | 27.2% | 4.2ms | 48.5% | 37ms |
| Combined | 40.0% | 25.2ms | 48.8% | 222ms |

> ⚠️ **lan1 asymmetry**: The lan1 edge_server handles aggregator duties — its baseline CPU oscillates 22–95% with T_proc spikes to 100ms. lan2 edge_server is relatively idle (27% CPU, 4ms T_proc). The lan1 edge_server is the binding constraint for compute floors.

**Why C1 spawned 17 containers** (even at 0.90 thresholds):
- The C1 floors (CPU_FLOOR=25/SPAN=40, T_PROC_FLOOR=15) were derived from incorrect W0.10 baseline (31.2% — averaged both lans with flawed filter). Actual lan1 baseline is 52.7%.
- `T_PROC_SPAN=80` (code default) was used since C1 didn't set it explicitly. The C1 plan assumed span=80 which happened to match the default.
- With CPU_FLOOR=25 and lan1 CPU=52.7%: `0.40×sat((52.7−25)/40) = 0.277` (already partial). With T_proc at 46.3ms: `0.60×sat((46.3−15)/80) = 0.235`. Total = 0.512.
- Combined CPU+T_proc spikes (CPU≥95%, T_proc≥100ms) push score to 0.40+0.60=1.00, crossing even 0.90.

**Stress metrics** (pre-spawn windows):
- Storage storm: stor_cpu=71.3%, T_db=4908ms
- Compute spike: edge_cpu=67.9%, T_proc=222ms

#### Revised Derived Values (C1-calibrated)

**Compute** (based on C1 lan1 baseline 52.7%/46.3ms; stress 67.9%/222ms):
- `SCALEUP_CPU_FLOOR = 45` → lan1 baseline: `0.40 × sat((52.7−45)/30) = 0.103`
- `SCALEUP_CPU_SPAN = 30` → stress: `0.40 × sat((67.9−45)/30) = 0.305`
- `SCALEUP_T_PROC_FLOOR = 40` → lan1 baseline: `0.60 × sat((46.3−40)/80) = 0.047`
- `SCALEUP_T_PROC_SPAN = 80` ← **must be explicit** (code default is 80, matches plan assumption; set explicitly to avoid silent drift)
- Compute baseline score (lan1 avg): `0.103 + 0.047 = 0.150`
- Compute baseline score (combined avg): `0 + 0 = 0.000` (both components below floor)
- Compute stress score: `0.305 + 0.60 × sat((222−40)/80) = 0.305 + 0.600 = 0.905`
- Gap: 0.755 (lan1) to 0.905 (combined)

**Storage** (based on C1 baseline 48.8%/222ms; stress 71.3%/4908ms):
- `SCALEUP_STORAGE_CPU_FLOOR = 40` (unchanged)
- `SCALEUP_STORAGE_CPU_SPAN = 25` (unchanged)
- `SCALEUP_T_DB_FLOOR = 200` ← **raised from 120** because lan1 baseline T_db reaches 406ms. At floor=120: `0.40×sat((406−120)/250)=0.458` → combined storage score would be 0.669. At floor=200: `0.40×sat((406−200)/250)=0.330`.
- `SCALEUP_T_DB_SPAN = 250` (unchanged)
- Storage baseline score (lan1 avg T_db=406ms): `0.216 + 0.40 × sat((406−200)/250) = 0.216 + 0.330 = 0.546` ⚠️
- Storage baseline score (lan1 window-level worst: T_db≥450ms observed in C1 policy_state): `0.216 + 0.40 × 1.0 = 0.616` ❌
- Storage baseline score (combined avg): `0.211 + 0.40 × sat((222−200)/250) = 0.211 + 0.035 = 0.246`
- Storage stress score: `0.60 + 0.40 = 1.000`
- Gap: 0.384 (window-level worst) to 0.754 (combined)

> ⚠️ **Storage window-level spikes**: C1 policy_state showed individual 5s windows where T_db≥450ms during baseline (equivalent score ~0.616 with T_DB_FLOOR=200). This exceeds 0.55. However, `SCALEUP_STORAGE_REQUIRED=2` means 2-of-5 windows must cross threshold to trigger — a single spike window won't cause an FP. If TWO consecutive windows both spike (e.g., T_db≥450ms in back-to-back 5s windows), that's 2-of-5 and WOULD trigger. This is a narrow risk accepted at C4 resource constraints.

#### Threshold Placement

Thresholds at **0.55** for both tiers:

| Tier | Baseline (lan1 avg) | Baseline (window spike) | Stress | Margin (avg→threshold) |
|------|---------------------|-------------------------|--------|------------------------|
| Compute | 0.150 | 0.850¹ | 0.905² | +0.400 |
| Storage | 0.546 | 0.616³ | 1.000 | −0.004 |

> ¹ Compute window spike requires simultaneous CPU≥95% AND T_proc≥100ms in the same 5s window. Not observed coinciding in C1. Even if triggered, `REQUIRED=3` means 3-of-5 windows needed — a single spike won't trigger.
> ² Compute stress score (0.905) exceeds `SCALEUP_COMPUTE_MAX_THRESHOLD=0.90` — after 4 spawns the adaptive cap is reached, and further spawns would require score > 0.90. At 0.905, exactly 4 compute spawns fire then stop. Acceptable.
> ³ Storage window spike score assumes T_db≥450ms in a specific 5s window (observed in C1 policy_state). `REQUIRED=2` mitigates — a single window above 0.55 won't trigger unless a second window also crosses.

- `SCALEUP_COMPUTE_BASE_THRESHOLD = 0.55`
- `SCALEUP_STORAGE_BASE_THRESHOLD = 0.55`
- `SCALEUP_COMPUTE_MAX_THRESHOLD = 0.90`
- `SCALEUP_STORAGE_MAX_THRESHOLD = 0.90`

#### Runs

| # | Label | Status | Changes |
|---|---|---|---|
| **C1** | `cal_c4_c1_floors` | ✅ Done | Initial floors (CPU=25/40, T_PROC=15/80code, T_DB=120/250). 17 spawns — floors too low. Used for measurement. Only T_PROC_SPAN left at code default (80); other 3 spans set explicitly. |
| **C2** | `cal_c4_c2_revised` | ✅ Done | Revised floors (CPU=45/30, T_PROC=40/80, T_DB=200). Thresholds at 0.55. 23 spawns. **2 baseline FPs**: storage reserve spawn (persistent reserve, not score-based) + compute FP (lan1 CPU=72.5%, T_proc=101ms → score 0.83 > 0.55). |
| **C3** | `cal_c4_c3_raised` | 📋 Next | **Raised compute floors** (CPU=70/20, T_PROC=80/80) + **disable persistent reserve** (`STORAGE_PERSISTENT_RESERVE_ENABLED=0`). Storage floors unchanged from C2. Thresholds at 0.55. |

#### C2 Post-Mortem

Controller logs revealed the true baseline lan1 metrics that C2's average-based calibration missed:

| Metric | C2 Plan Assumed | C2 Actual (lan1) |
|--------|----------------|-------------------|
| Baseline edge CPU | 52.7% (avg) | **72.5%** (5s window peak) |
| Baseline T_proc | 46.3ms (avg) | **101.1ms** (5s window peak) |

The 5-second sampling windows capture peaks far above the phase-level average. The C2 floors (CPU=45, T_PROC=40) were calibrated against averages, not peaks.

Additionally, the persistent reserve mechanism (`STORAGE_PERSISTENT_RESERVE_ENABLED=1`) auto-spawns storage nodes independently of the degradation score — the first "FP" at t=37s was a reserve spawn, not a threshold crossing. Disabling it for C3 isolates the degradation score as the sole trigger mechanism.

#### C3 Score Predictions

| Scenario | CPU | T_proc | CPU comp | T_proc comp | Total |
|----------|-----|--------|----------|-------------|-------|
| Baseline (C2 trigger) | 72.5% | 101ms | `0.40×sat((72.5−70)/20)=0.050` | `0.60×sat((101−80)/80)=0.158` | **0.208** |
| Baseline (worst spike) | 82% | 120ms | `0.40×sat((82−70)/20)=0.240` | `0.60×sat((120−80)/80)=0.300` | **0.540** |
| Stress (C2 compute_spike) | 83.6% | 181ms | `0.40×sat((83.6−70)/20)=0.272` | `0.60×sat((181−80)/80)=0.600` | **0.872** |

> Baseline 0.21 < 0.55 ✅. Stress 0.87 > 0.55 ✅. Worst spike 0.54 < 0.55 ✅ (and `REQUIRED=3` prevents single-window triggers).

| **C3** | `cal_c4_c3_raised` | 📋 Next | **Raised compute floors** (CPU=70/20, T_PROC=80/80) + **disable persistent reserve** (`STORAGE_PERSISTENT_RESERVE_ENABLED=0`). Storage floors unchanged from C2. Thresholds at 0.55. |

---

## 5. Run Configuration

All runs use C4 resources. WORK_FACTOR is a `make` variable, floors/thresholds go in the controller env override.

### Part A Launch

```bash
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  RUN_LABEL=cal_c4_wf<N> \
  PHASES_CONFIG=testing/phases.json \
  WAN_RTT_MS=260 CLIENTS=48 CONTENT_ITEMS=6000 USERS=100 \
  STORAGE_CPUS=0.04 EDGE_CPUS=0.06 \
  STORAGE_MEMORY=512m EDGE_MEMORY=256m \
  FEED_INTEGRITY_WORK_FACTOR=<N> \
  RANDOM_SEED=42 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
```

### Part B Launch

Create per-run env override files under `testing/controller_env_overrides/`. **All files set `SCALEUP_STORAGE_BASE_THRESHOLD=0.90` and `SCALEUP_COMPUTE_BASE_THRESHOLD=0.90`** (effectively disabled — no spawns during measurement; see contamination note in Section 4) plus floor/span values:

- `rq3_cal_f0.env` → golden config + `SCALEUP_STORAGE_CPU_FLOOR=1.5` + `SCALEUP_STORAGE_CPU_SPAN=5` + thresholds at 0.90
- `rq3_cal_f1.env` → golden config + `SCALEUP_STORAGE_CPU_FLOOR=30` + `SCALEUP_STORAGE_CPU_SPAN=15` + thresholds at 0.90
- `rq3_cal_f2.env` → golden config + `SCALEUP_STORAGE_CPU_FLOOR=35` + `SCALEUP_STORAGE_CPU_SPAN=20` + thresholds at 0.90
- `rq3_cal_f3.env` → golden config + `SCALEUP_STORAGE_CPU_FLOOR=40` + `SCALEUP_STORAGE_CPU_SPAN=25` + thresholds at 0.90

```bash
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/rq3_cal_f<N>.env \
  RUN_LABEL=cal_c4_f<N> \
  PHASES_CONFIG=testing/phases.json \
  WAN_RTT_MS=260 CLIENTS=48 CONTENT_ITEMS=6000 USERS=100 \
  STORAGE_CPUS=0.04 EDGE_CPUS=0.06 \
  STORAGE_MEMORY=512m EDGE_MEMORY=256m \
  FEED_INTEGRITY_WORK_FACTOR=<winner_from_part_A> \
  RANDOM_SEED=42 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
```

**Part C**: Create env override files under `testing/controller_env_overrides/`:

- `rq3_cal_c1.env` — floors only, thresholds at 0.90. **Must include all golden config vars** (see Phase 1b convention):
  ```
  STORAGE_PERSISTENT_RESERVE_ENABLED=1
  SS_ENABLED=1
  MAX_DYNAMIC_STORAGE=5
  MAX_DYNAMIC_COMPUTE=6
  SCALEUP_CPU_FLOOR=25
  SCALEUP_CPU_SPAN=40
  SCALEUP_T_PROC_FLOOR=15
  SCALEDOWN_COMPUTE_COOLDOWN_S=180
  SCALE_DOWN_COMPUTE_REQUIRED=9
  SCALEUP_W_STORAGE_CPU=0.60
  SCALEUP_W_T_DB=0.40
  SCALEUP_STORAGE_CPU_FLOOR=40
  SCALEUP_STORAGE_CPU_SPAN=25
  SCALEUP_T_DB_FLOOR=120
  SCALEUP_T_DB_SPAN=250
  SCALEUP_STORAGE_REQUIRED=2
  SCALEUP_STORAGE_WINDOW_SIZE=5
  SCALEUP_STORAGE_COOLDOWN_S=120
  SCALEUP_COMPUTE_BASE_THRESHOLD=0.90
  SCALEUP_COMPUTE_MAX_THRESHOLD=0.90
  SCALEUP_STORAGE_BASE_THRESHOLD=0.90
  SCALEUP_STORAGE_MAX_THRESHOLD=0.90
  VIP_HARD_TIMEOUT=60
  ```
- `rq3_cal_c2.env` — revised floors + thresholds at 0.55:
  ```
  STORAGE_PERSISTENT_RESERVE_ENABLED=1
  SS_ENABLED=1
  MAX_DYNAMIC_STORAGE=5
  MAX_DYNAMIC_COMPUTE=6
  SCALEUP_CPU_FLOOR=45
  SCALEUP_CPU_SPAN=30
  SCALEUP_T_PROC_FLOOR=40
  SCALEUP_T_PROC_SPAN=80
  SCALEDOWN_COMPUTE_COOLDOWN_S=180
  SCALE_DOWN_COMPUTE_REQUIRED=9
  SCALEUP_W_STORAGE_CPU=0.60
  SCALEUP_W_T_DB=0.40
  SCALEUP_STORAGE_CPU_FLOOR=40
  SCALEUP_STORAGE_CPU_SPAN=25
  SCALEUP_T_DB_FLOOR=200
  SCALEUP_T_DB_SPAN=250
  SCALEUP_STORAGE_REQUIRED=2
  SCALEUP_STORAGE_WINDOW_SIZE=5
  SCALEUP_STORAGE_COOLDOWN_S=120
  SCALEUP_COMPUTE_BASE_THRESHOLD=0.55
  SCALEUP_COMPUTE_MAX_THRESHOLD=0.90
  SCALEUP_STORAGE_BASE_THRESHOLD=0.55
  SCALEUP_STORAGE_MAX_THRESHOLD=0.90
  VIP_HARD_TIMEOUT=60
  ```
- `rq3_cal_c3.env` — identical to C2 (C3 is a replicate of C2 with `RANDOM_SEED=99`)

Launch for C1:
```bash
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/rq3_cal_c1.env \
  RUN_LABEL=cal_c4_c1 PHASES_CONFIG=testing/phases.json \
  WAN_RTT_MS=260 CLIENTS=48 CONTENT_ITEMS=6000 USERS=100 \
  STORAGE_CPUS=0.04 EDGE_CPUS=0.06 \
  STORAGE_MEMORY=512m EDGE_MEMORY=256m \
  FEED_INTEGRITY_WORK_FACTOR=200 \
  RANDOM_SEED=42 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
```

Launch for C2 (C3: change `RUN_LABEL=cal_c4_c3`, `OSKEN_ENV_OVERRIDE_FILE=.../rq3_cal_c2.env`, `RANDOM_SEED=99`):
```bash
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/rq3_cal_c2.env \
  RUN_LABEL=cal_c4_c2 PHASES_CONFIG=testing/phases.json \
  WAN_RTT_MS=260 CLIENTS=48 CONTENT_ITEMS=6000 USERS=100 \
  STORAGE_CPUS=0.04 EDGE_CPUS=0.06 \
  STORAGE_MEMORY=512m EDGE_MEMORY=256m \
  FEED_INTEGRITY_WORK_FACTOR=200 \
  RANDOM_SEED=42 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
```

---

## 6. Focus & Evidence

### Part A — Primary

| Artifact | What to measure | Purpose |
|---|---|---|
| `resource_stats.csv` | `average_cpu_percent` during `baseline` (0–60s) | Verify baseline edge CPU ~35% |
| `resource_stats.csv` | `average_cpu_percent` during `compute_spike` (0–60s) | Verify stress edge CPU ≥ 55% |
| `resource_stats.csv` | `avg_time_proc_ms` during `compute_spike` (0–60s) | Confirm edge is compute-bound (high T_proc) |

### Part B — Primary

| Artifact | What to measure | Purpose |
|---|---|---|
| `resource_stats.csv` | `avg_storage_cpu_percent` during `baseline` (0–60s) | Baseline storage CPU |
| `resource_stats.csv` | `avg_storage_cpu_percent` during `storage_storm` (0–60s) | Stress storage CPU |
| `container_events.csv` | `event=added` during `baseline` | **Must be zero** (no FP) |
| `container_events.csv` | `event=added` during `storage_storm` | **Must be ≥1** (triggers) |

### Secondary (all parts)

| Artifact | What to check |
|---|---|
| `elasticity_events.csv` | Alert timestamps vs phase boundaries |
| `controller_lan1.log` | Score values at decision time, tracebacks |
| `client_requests.csv` | Success rate, failure rate |

---

## 7. Success Criteria

### Part A Gate

| # | Metric | Target | Actual (W0.10) |
|---|---|---|---|
| 1 | Baseline edge CPU | ~30–40% (expected; values outside trigger `client_fraction` reassessment) | **31.2%** ✅ |
| 2 | `compute_spike` edge CPU (pre-scale, 0–60s) | ≥ 55% | **65.5%** ✅ |
| 3 | Edge CPU direction | `compute_spike` > `baseline` (no inversion) | **65.5% > 31.2%** ✅ |

### Part B Gate

| # | Metric | Target | Actual (all F0–F3) |
|---|---|---|---|
| 1 | Storage spawns during `baseline` | **0** | 0 ✅ (thresholds at 0.90) |
| 2 | Storage spawns during `storage_storm` | **≥ 1** | ≥1 ✅ |
| 3 | Baseline storage score < 0.35 AND stress > 0.50 | Gap ≥ 0.15 | ❌ **No candidate passed** (F3=0.443) |

**Result**: CPU floor alone insufficient — T_db floor must also be raised (see Part C).

### Part C Gate

**C1 actuals**:

| # | Metric | Target | C1 Actual |
|---|---|---|---|
| 1 | Compute spawns during `baseline` | **0** | ❌ 1 (lan1 FP at t=31s, cs=0.400) |
| 2 | Compute spawns during `compute_spike` | **≥ 1** | ✅ 6 compute spawns |
| 3 | Storage spawns during `baseline` | **0** | ✅ 0 |
| 4 | Storage spawns during `storage_storm` | **≥ 1** | ✅ 5 storage spawns |
| 5 | Measured scores match predicted | Within ±0.10 | ❌ Baseline edge CPU was 52.7% (lan1), not 31.2% — floors recalibrated for C2 |

**C2/C3 Gate**:

| # | Metric | Target |
|---|---|---|
| 1 | Compute spawns during `baseline` | **0** (accept rare combined CPU+T_proc spike FPs as C4 artifact) |
| 2 | Compute spawns during `compute_spike` | **≥ 1** |
| 3 | Storage spawns during `baseline` | **0** (accept rare T_db spike FPs as C4 artifact; lan1 worst score 0.546 is 0.004 below threshold) |
| 4 | Storage spawns during `storage_storm` | **≥ 1** |
| 5 | System liveness | No static node OOM, controller traceback-free |
---

## 8. Validity Threats

| Threat | Mitigation |
|---|---|
| **WORK_FACTOR=500 may not create enough edge CPU.** Edge CPU may still be I/O-bound at extreme constraints. | W2 (800) provides overshoot. If even W2 fails, edge is fundamentally I/O-bound at C4 — a valid finding. |
| **Reducing baseline `client_fraction` may reduce storage baseline CPU too much.** | Acceptable — the calibration only needs *relative* separation. If storage baseline CPU drops below 30%, raise client_fraction slightly. |
| **`FEED_INTEGRITY_WORK_FACTOR` only affects dynamic containers.** New containers get the env var; static containers retain their launch-time value. | A full cleanup+rebuild between W0→W1→W2 ensures all containers use the new value. Document in between-run protocol. |
| **Storage floor raising may make storage score too insensitive.** At floor=40, a 10% CPU increase (50→60%) changes the CPU component by only 0.24. | The latency component provides additional signal. If floor overshoots, back down to F1 or F2. **Secondary check**: If stress storage T_db < 100ms, the latency component is suppressed; consider reducing `SCALEUP_T_DB_FLOOR`. |
| **All Phase 1a/1b validity threats still apply.** | Single replicate, cooldown interference, `RANDOM_SEED=42`, warm-up artifacts. Same mitigations. |

---

## 9. After Phase 1c

1. **Update `current_state_integrated.env`** with winning floors, spans, and thresholds
2. **Update `golden_config.md`** with the full RQ3 calibrated config (C4 resources + calibrated floors + thresholds)
3. **Proceed to RQ3 evaluation** — 9 runs (3 modes × 3 replicates)
4. **Create RQ3 mode-specific env files** *(out of scope for this calibration; to be designed in the RQ3 experiment plan)*: `rq3_degradation_score.env`, `rq3_cpu_only.env`, `rq3_latency_only.env`

---

## Related Documents

| Document | Purpose |
|---|---|
| [`golden_config.md`](../../golden_config.md) | Golden config (C4 section added) |
| [`rq3.md`](../../../../research_questions/rq3.md) | RQ3 this calibration serves |
| [`scaling_config.py`](../../../../source/sdn_controller/scaling_config.py) | Trigger config (all vars env-driven) |
| [`edge_server_config.py`](../../../../source/docker/edge_server/source/edge_server_config.py) | `FEED_INTEGRITY_WORK_FACTOR` env read |
| [`build_network_1.sh`](../../../../source/scripts/network/build_network_1.sh) | Edge server Docker launch (LAN1) |
| [`build_network_2.sh`](../../../../source/scripts/network/build_network_2.sh) | Edge server Docker launch (LAN2) |
| [`phases.json`](../../../../source/scripts/testing/phases.json) | Canonical phases (edited for Phase 1c) |
