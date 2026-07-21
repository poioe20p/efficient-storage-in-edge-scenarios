# Experiment Plan — RQ3 Golden-Config Baseline (G0-v3)

**Date**: 2026-07-18 · **Status**: 🔄 Reconfigured · **Supersedes**: G0 v2 (20260718) · **Depends on**: [rq3_preparation.md](./rq3_preparation.md)

**Purpose**: Validate the storage latency-only scoring change (W_STORAGE_CPU=0, W_T_DB=1.0) at the same tightened config (STORAGE_CPUS=0.08, EDGE_CPUS=0.25, WAN=185ms, CLIENTS=48). Storage CPU is I/O-bound at 0.08 CPUs — the v2 data proved CPU is decoupled from storage performance. This run confirms latency-only storage scoring produces cleaner dynamic range (0.00→1.00 vs v2's 0.60→1.00) without regressing scaling effectiveness.

---

## 0. Prerequisites

Before launching any run, confirm:

| # | Check | How |
|---|-------|-----|
| P1 | Mean-only latency signals deployed | `grep 'return ds.avg_time_proc_ms' source/sdn_controller/scaling_policy.py` returns the line |
| P2 | `p95_time_proc_ms` in DomainSummary (monitoring only) | `grep 'p95_time_proc_ms' source/sdn_controller/telemetry/models.py` returns the field |
| P3 | Aggregator computes p95_time_proc (monitoring only) | `grep 'p95_time_proc' source/docker/local_state_server/aggregator.py` returns both the computation and zero-init |
| P4 | Docker images rebuilt | `sudo -n bash source/scripts/build_images.sh` completed without error on cloud VM |
| P5 | Cloud VM has latest source | `git push && ssh cloud-vm 'cd ~/efficient-storage-in-edge-scenarios && git pull'` |
| P6 | No orphan containers from prior runs | `docker ps -a --format '{{.Names}}' | grep -qE 'edge_|storage_|sel_sync' && echo 'ORPHANS DETECTED' || echo 'Clean'` |
| P7 | Env override has v3 thresholds | `grep 'SCALEUP_W_STORAGE_CPU=0' source/scripts/testing/controller_env_overrides/current_state_integrated.env` returns the line |
| P8 | Storage scale-down is latency-only | `grep 'below = ds.avg_time_db_ms' source/sdn_controller/scaling_policy.py` returns the line (no CPU condition) |

---

## 1. Intent

Before RQ3 can compare trigger compositions (degradation_score vs cpu_only vs latency_only), two things must be established:

1. **Scaling produces a visible within-phase improvement.** When a scale-up fires during a stress phase, the pre-scale → post-scale CPU drop must be ≥15pp and latency must drop ≥50% within the same phase.
2. **The mean-only latency signal produces meaningful degradation scores.** With p95 excluded (timeout-censored p95 is misleading — it measures the timeout, not the system), the degradation score must respond to actual workload stress.

This experiment runs **one workload** with elasticity ON, using mean-only latency signals for both tiers. Tier 1 selective sync is ON. The OFF run is dropped — within-phase pre/post analysis replaces cross-run ON/OFF comparison.

---

## 2. Hypothesis / Expected Outcome

| # | Claim | Rationale |
|---|-------|-----------|
| H1 | Storage CPU drops ≥15pp within `storage_storm` after scale-up fires | Tighter CPU (0.08 vs 0.10) + lower WAN (185ms vs 260ms) increases pre-scale CPU; scaling distributes load |
| H2 | Compute CPU drops ≥15pp within `compute_spike` after scale-up fires | Tighter CPU (0.25 vs 0.30) + redesigned phase (0.5 r/s, 80/20 mix) balances stress with manageable latency |
| H3 | Post-scale compute_spike median latency ≤1,500ms | Phase redesign reduces feed_ranking from 96/s to 19.2/s; scaling further distributes load |
| H4 | Mean-only signal produces meaningful score dynamic range | Without p95 contamination (timeout-censored at 30s), scores should track actual workload stress — low in baseline, high in stress phases |

---

## 3. RQ Linkage

| Thesis element | This experiment's role |
|---------------|----------------------|
| **RQ3**: How does degradation-score composition affect detection? | Prerequisite — establishes that scaling is necessary and provides calibration data for the trigger parameters used in the 9-run RQ3 matrix. |
| Independent variable (RQ3) | Trigger composition (cpu_only / latency_only / degradation_score) — **not varied here**. This run uses degradation_score with mean-only signals and recalibrated thresholds. |
| Dependent variables (RQ3) | Scale-up timing, false-positive rate, latency distribution — measured here as baselines. |

---

## 4. Independent Variable & Held-Constant Set

### Analysis Approach: Within-Phase Pre/Post Scale-Up

Instead of comparing ON vs OFF runs, this experiment measures improvement **within a single run**: for each scale-up event during a stress phase, compare CPU and latency in windows before the trigger vs windows after the new node joins. The `policy_state.csv` provides per-window `dynamic_compute_count` and `dynamic_storage_count` — increments mark scale-up events.

### Held Constant

| Parameter | Value | Notes |
|-----------|-------|-------|
| `STORAGE_CPUS` | **0.08** | Tightened from 0.10 — pushes storage CPU higher in stress |
| `EDGE_CPUS` | **0.25** | Tightened from 0.30 — pushes edge CPU higher in stress |
| `STORAGE_MEMORY` | 512m | Unchanged |
| `EDGE_MEMORY` | 256m | Unchanged |
| `WAN_RTT_MS` | **185** | Reduced from 260 — less I/O-wait, better CPU signal |
| `CLIENTS` | 48 | Unchanged |
| `CONTENT_ITEMS` | 6000 | Unchanged |
| `USERS` | 100 | Unchanged |
| `VIP_HARD_TIMEOUT` | 60 | Unchanged |
| `SS_ENABLED` | 1 | Tier 1 ON |
| `RANDOM_SEED` | 42 | Unchanged |
| Latency signal (both tiers) | **Mean only** (`avg_time_proc_ms`, `avg_time_db_ms`) | p95 excluded — timeout-censored p95 is misleading |
| Storage scoring | **Latency-only** (`W_STORAGE_CPU=0`, `W_T_DB=1.0`) | CPU is I/O-bound at 0.08 — proven decoupled from storage performance in v2 |
| compute_spike phase | **0.5 r/s, 80% feed_ranking + 20% content_lookup** | Redesigned from 2 r/s 100% feed_ranking |
| Controller env override | `current_state_integrated.env` | Updated with latency-only storage (W_STORAGE_CPU=0, τ_storage=0.18) |
| Trigger mode | degradation_score (composite for compute, latency-only for storage) | Compute: W_CPU=0.60/W_T_PROC=0.40. Storage: W_T_DB=1.0 |

---

## 5. Run Matrix

| # | Label | Purpose |
|---|-------|---------|
| **G0-v3** | `rq3_g0_v3` | Re-run of v2 with storage latency-only scoring (W_STORAGE_CPU=0, W_T_DB=1.0). Same workload, same topology. Expect cleaner storage score dynamic range (0.00→1.00 vs v2's 0.60→1.00). |

## 6. Run Configuration

### 6.1 G0-v3 — Elasticity ON, Storage Latency-Only

```bash
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  RUN_LABEL=rq3_g0_v3 \
  PHASES_CONFIG=testing/phases.json \
  WAN_RTT_MS=185 CLIENTS=48 CONTENT_ITEMS=6000 USERS=100 \
  STORAGE_CPUS=0.08 EDGE_CPUS=0.25 \
  STORAGE_MEMORY=512m EDGE_MEMORY=256m \
  RANDOM_SEED=42 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
```

**v3 changes from v2**: Storage scoring changed from composite (0.60×CPU + 0.40×T_db) to latency-only (1.0×T_db). Storage scale-down now triggers on T_db alone (CPU condition removed). All other parameters identical to v2.

### 6.2 Cleanup

```bash
sudo -n bash source/scripts/cleanup.sh
docker ps -a --format '{{.Names}}' | grep -qE 'edge_|storage_|sel_sync' && echo 'ORPHANS DETECTED' || echo 'Clean'
```

---

## 7. Focus & Evidence

### Primary Evidence

| Artifact | What It Shows |
|----------|--------------|
| `resource_stats.csv` | Per-window CPU for storage and edge. Aligned with `policy_state.csv` to identify pre/post scale-up windows. |
| `policy_state.csv` | Per-window `dynamic_compute_count` and `dynamic_storage_count` — increments mark scale-up events. `compute_score` and `storage_score` — degradation score values. |
| `client_requests.csv` | End-to-end latency per phase. Filtered by timestamp to match pre/post scale-up windows. |

### Secondary Evidence

| Artifact | What It Shows |
|----------|--------------|
| `controller_lan1.log` / `controller_lan2.log` | `[scale-up]` log lines with timestamps — precise trigger times for aligning pre/post windows. |
| `container_events.csv` | Spawn/join timestamps — confirms when new nodes actually came online (not just when trigger fired). |
| `elasticity_events.csv` | node_add_timing, node_online — node lifecycle for measuring scale-up latency. |
| `per_node_stats.csv` | Per-node CPU — confirms load distribution across nodes post-scale. |

### What to Measure (Within-Phase Pre/Post)

| Measurement | Method |
|------------|--------|
| Storage CPU drop | Compare mean `avg_storage_cpu_percent` in N windows before vs after `dynamic_storage_count` increments during `storage_storm` |
| Compute CPU drop | Compare mean `average_cpu_percent` in N windows before vs after `dynamic_compute_count` increments during `compute_spike` |
| Latency reduction | Compare median `latency_s` in pre vs post windows |
| Scale-up latency | Time from `[scale-up]` log line to `node_online` event in `elasticity_events.csv` |
| Score behavior | `compute_score` and `storage_score` values in pre vs post windows |

---

## 8. Metrics & Success Criteria

### 8.1 Scaling Prerequisite (Go/No-Go for RQ3)

| # | Metric | Target | Measurement |
|---|--------|--------|-------------|
| S1 | Within-phase storage CPU drop in `storage_storm` | **≥15pp** | Mean `avg_storage_cpu_percent` in N windows pre-scale vs N windows post-scale |
| S2 | Within-phase compute CPU drop in `compute_spike` | **≥15pp** | Mean `average_cpu_percent` in N windows pre-scale vs N windows post-scale |
| S3 | Post-scale compute_spike median latency | **≤1,500ms** | Median `latency_s` in post-scale windows of `compute_spike` |
| S4 | System stability | No OOM kills, success ≥85% | All phases |
| S5 | Scale-up actually fires in both stress phases | ≥1 storage scale-up in `storage_storm`, ≥1 compute scale-up in `compute_spike` | `policy_state.csv` `dynamic_*_count` increments |

### 8.2 Decision Tree

| Condition | Action |
|-----------|--------|
| S1 AND S2 ≥ 15pp, S3 ≤ 1,500ms, S5 met | ✅ **Proceed.** Config is viable. Proceed to RQ3 9-run matrix. |
| S1 OR S2 < 15pp but ≥ 10pp | ⚠️ **Marginal.** Consider further CPU tightening or rate increase. |
| S1 OR S2 < 10pp | ❌ **Insufficient.** Not enough pre-scale stress. Increase compute_spike rate or tighten CPUs further. |
| S3 > 1,500ms | ⚠️ **compute_spike still too aggressive.** Reduce rate to 0.35 r/s or increase content_lookup filler. |
| S5 fails (no scale-up triggered) | ⚠️ **Thresholds too high or load too low.** Lower τ_base or increase compute_spike rate. |

---

## 9. Checkpoints (In-Run Observations)

The runner may observe but not modify. All checkpoints are read-only.

| # | Trigger | What to Check | Question |
|---|---------|--------------|----------|
| CP1 | G0-v2 T+60s (end of baseline) | `docker stats --no-stream` — edge and storage CPU | Establish baseline CPU ranges at new config. Storage ~20–28%, edge ~10–18% expected given 10% client fraction. If edge CPU > 40% in baseline, abort: the tightened config is too constrained for baseline traffic. |
| CP2 | G0-v2 T+120s (early storage_storm) | `docker stats --no-stream` — storage CPU | Is storage CPU climbing toward saturation? At 0.08 CPUs with 90% cross-region ratio, expect significant stress. |
| CP3 | G0-v2 T+480s (early compute_spike) | Controller log for `[scale-up] compute triggered` | Did compute scale-up fire within the first 60s of compute_spike? At 0.5 r/s, the stress builds slower than v1's 2 r/s. |
| CP4 | G0-v2 T+600s (mid compute_spike) | `docker stats --no-stream` — edge CPU distribution | Is load distributed across nodes? If only static node shows CPU and dyn nodes are idle, VIP routing may not be steering traffic correctly. |
| CP5 | G0-v2 T+300s (mid storage_storm) | Controller log for `[scale-up] storage triggered` | Did storage scale-up fire? If not, thresholds may be too high for the new mean-only signal with tighter CPUs. |
| CP6 | G0-v2 T+900s (mid compute_spike) | Controller log for `[scale-up] compute triggered` | Did compute scale-up fire? If not, 0.5 r/s may be too mild — increase to 0.75 r/s for v2b. |
| CP7 | Any phase | Controller log for tracebacks or `ERROR` | Abort if controller crashes. |

---

## 10. Validity Threats & Limitations

| Threat | Mitigation |
|--------|-----------|
| **Single seed (42)** | Accepted. Calibration run; different-seed verification (G3) after threshold finalization. |
| **Mean-only signal may be less sensitive to tail latency** | p95 is still collected in telemetry for monitoring. The degradation score focuses on sustained stress (mean), not transient spikes. This is consistent with literature standard — all reviewed autoscaling papers use mean for triggers. |
| **0.5 r/s may not trigger scaling** | Iterative calibration: if S5 fails, increase to 0.75 r/s and re-run. |
| **WAN=185ms may reduce cross-region stress** | The 185ms penalty is still meaningful (Tier 1 benefit should be visible). v6 at 160ms showed good dynamics. |

---

## 11. Artifact Contract

### Expected Run-Folder Contents

Standard layout per `docs/operation/testing/testing_overview.md`:

```
source/scripts/testing/metrics/<timestamp>_rq3_g0_v2/
  client_requests.csv
  resource_stats.csv
  per_node_stats.csv
  container_events.csv
  elasticity_events.csv
  controller_stats.csv
  controller_lan1.log
  controller_lan2.log
  phases_snapshot.json
  controller_env_snapshot.env
  service_logs/
  run_summary.md                    ← to be written by analyst
```

### Post-Run Outputs

| Output | Author | Purpose |
|--------|--------|---------|
| `run_summary.md` | Analyst (Edge Experiment Analyzer) | Per-run analysis: within-phase pre/post scale-up CPU/latency improvement, signal behavior |
| Updated `rq3_preparation.md` §2.3, §6 | Analyst | Fill in actual CPU/latency values from G0-v2 data |
| Threshold calibration plan (G1–G3) | Designer | Derived from G0-v2 floor/span measurements |

---

## A. Quick-Reference: Commands

### Deploy code to cloud VM

```bash
git add -A && git commit -m "G0-v2: mean-only latency signals, tighter CPUs, 185ms WAN, compute_spike redesign"
git push
ssh cloud-vm 'cd ~/efficient-storage-in-edge-scenarios && git pull'
```

### Rebuild images on cloud VM

```bash
ssh cloud-vm 'cd ~/efficient-storage-in-edge-scenarios && sudo -n bash source/scripts/build_images.sh'
```

### Run G0-v2

```bash
ssh cloud-vm
cd ~/efficient-storage-in-edge-scenarios
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  RUN_LABEL=rq3_g0_v2 \
  PHASES_CONFIG=testing/phases.json \
  WAN_RTT_MS=185 CLIENTS=48 CONTENT_ITEMS=6000 USERS=100 \
  STORAGE_CPUS=0.08 EDGE_CPUS=0.25 \
  STORAGE_MEMORY=512m EDGE_MEMORY=256m \
  RANDOM_SEED=42 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
```

### Verify threshold overrides on cloud VM

```bash
ssh cloud-vm 'cd ~/efficient-storage-in-edge-scenarios && grep -E "SCALEUP_W_CPU|SCALEUP_W_T_PROC|SCALEUP_T_PROC_FLOOR|SCALEUP_COMPUTE_BASE_THRESHOLD" source/scripts/testing/controller_env_overrides/current_state_integrated.env'
# Expected:
#   SCALEUP_COMPUTE_BASE_THRESHOLD=0.18
#   SCALEUP_T_PROC_FLOOR=25
#   SCALEUP_W_CPU=0.60
#   SCALEUP_W_T_PROC=0.40
```

### Cleanup

```bash
sudo -n bash source/scripts/cleanup.sh
```
