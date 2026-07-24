# RQ3 v5 — Trigger Composition Evaluation

**Status**: 🔵 Designed · **Date**: 2026-07-24
**Depends on**: [Divergence calibration](calibration_plan.md) (✅ complete — [`calibration_results_v2.md`](calibration_results_v2.md))
**Canonical RQ doc**: [`rq3_v2.md`](../../../../research_questions/rq3/rq3_v2.md)
**Canonical setup**: [`rq3_setup_v2.md`](../../../../research_questions/rq3/rq3_setup_v2.md) (outdated on storage weights — use this plan)
**Graph spec**: [`rq3_v2.md`](../../../../research_questions/rq3/rq3_v2.md) §6 — G1–G8 + G1b + G5b (10 graphs)

---

## 1. Intent

Evaluate whether varying only the four score-weight coefficients — with all
floors, spans, thresholds, window sizes, cooldowns, and adaptive escalation
parameters held identical — produces measurable differences in detection
behaviour and user-visible service quality.

Single question: **does trigger composition matter?**

The experiment compares three modes:

| Mode | Compute (W_CPU/W_T_PROC) | Storage (W_STORAGE_CPU/W_T_DB) | Encodes |
|---|---|---|---|
| `degradation_score` | 0.40 / 0.60 | 0.20 / 0.80 | Cross-signal confirmation (system default) |
| `cpu_only` | 1.00 / 0.00 | 1.00 / 0.00 | Industry default (CPU alone) |
| `latency_only` | 0.00 / 1.00 | 0.00 / 1.00 | User-experience dimension (latency alone) |

---

## 2. Hypothesis / Expected Outcome

**Compute tier — three-way divergence**: cpu_only produces the most spawns
(highest scores, CPU dominates), latency_only produces the fewest (T_proc
rarely crosses floor=25ms at this workload), degradation_score sits between
them. Both signals are independently meaningful at 0.25 CPUs.

**Storage tier — partial separation**: degradation_score at calibrated
0.20/0.80 (18 spawns) sits between cpu_only (22–24, CPU-dominated) and
latency_only (15–17, T_db-only). The CPU signal is real but weak at 0.08
CPUs — T_db is the primary driver. This bounds the trigger composition
space: only the compute tier has two independently meaningful signals.

**Composite = fewest FPs + equivalent detection**: degradation_score
produces the fewest baseline false positives (both signals must spike
simultaneously) without sacrificing stress detection or throughput.

**Any outcome is informative** (§4.3 of rq3_v2.md):
- All modes identical → composition doesn't matter; detection isn't the bottleneck
- cpu_only more FPs → CPU carries noise that latency cross-validation filters
- latency_only more FPs → latency carries noise that CPU cross-validation filters
- Extra spawns, same throughput → **waste** (composite filtering is valuable)
- Extra spawns, more throughput → **under-detection** (composite misses overload)

---

## 3. RQ Linkage

| SQ | Question | Primary metrics | Graphs |
|---|---|---|---|
| SQ3a | Do different compositions produce different FP rates during baseline? | M1 | G1, G1b |
| SQ3b | Do different compositions produce different detection sensitivity? | M2, M3, M4 | G2, G3 |
| SQ3c | Do detection differences produce measurable service-quality differences? | M5, M6, M7 | G4, G5, G5b, G6, G7 |

Supports thesis RQ3 (Detection link) — the third pillar of the
detection→delivery→action chain. See full measurement framework in
[`rq3_v2.md` §5](../../../../research_questions/rq3/rq3_v2.md).

---

## 4. Independent Variable & Held-Constant Set

### 4.1 Independent Variable

**Four weight coefficients** — the only things that differ across the 9 runs:

| Variable | degradation_score | cpu_only | latency_only |
|---|---|---|---|
| `SCALEUP_W_CPU` | 0.40 | 1.00 | 0.00 |
| `SCALEUP_W_T_PROC` | 0.60 | 0.00 | 1.00 |
| `SCALEUP_W_STORAGE_CPU` | 0.20 | 1.00 | 0.00 |
| `SCALEUP_W_T_DB` | 0.80 | 0.00 | 1.00 |

> Storage weights calibrated from 0.60/0.40 → 0.20/0.80 via storage CPU
> weight probe ([`calibration_results_v2.md`](calibration_results_v2.md) §6).
> At 0.08 CPUs, storage CPU at 0.60 dominated T_db (24 spawns = cpu_only
> territory). At 0.20, CPU is a real secondary signal that does not dominate.

### 4.2 Held Constant (Identical Across All 9 Runs)

| Parameter | Value | Why fixed |
|---|---|---|
| **Scoring floors, spans, thresholds** | See §4.3 | All modes evaluated under identical detection thresholds |
| **Phases** | `testing/phases.json` (canonical, 7 phases, 1,440 s) | Same workload as RQ1/RQ2 — cross-RQ comparability |
| **Resource limits** | STORAGE_CPUS=0.08, EDGE_CPUS=0.25, WAN_RTT_MS=185 | G0-v6 validated — produces clear pre→post improvement for both tiers. EDGE_CPUS=0.25 is the definitive value (confirmed by G0-v6 validation; the `rq3_setup_v2.md` "TBD" marker is stale). |
| **Client count** | CLIENTS=96 (48/LAN) | RQ1 v8 golden; matches RQ1/RQ2 |
| **Telemetry delivery** | Push (ZMQ, window-close) | Held constant — RQ1's domain; eliminates monitoring blind spot |
| **Routing policy** | Warm lease (`topology_lifecycle`) | Held constant — RQ2's domain; eliminates LB discovery gap |
| **Seeds** | RANDOM_SEED=42, DATA_SEED=42 | Deterministic workload across runs |
| **Tier 1 selective sync** | SS_ENABLED=1 | Fixed — exercises Tier 1 pool; identical for all modes |
| **Persistent reserve** | STORAGE_PERSISTENT_RESERVE_ENABLED=1 | Fixed — reserve spawns excluded from M1 (baseline FP) counts |
| **Scale-down** | COOLDOWN=180s, REQUIRED=9, WINDOW=12 | RQ1 v8 golden; identical for all modes |
| **Max dynamic nodes** | COMPUTE=12, STORAGE=8 | RQ1 v8 golden |
| **CURL_MAX_TIME** | 30 s | Hard client timeout |
| **Fault plan** | None | Synthetic failure not in scope |

### 4.3 Scoring Parameters (All Modes — Identical)

All values from `current_state_integrated.env` (G0-v6 validated) and confirmed
in divergence calibration.

| Parameter | Value | Role |
|---|---|---|
| `SCALEUP_CPU_FLOOR` | 10 | Below-floor CPU → zero CPU component |
| `SCALEUP_CPU_SPAN` | 40 | Wide span prevents score saturation |
| `SCALEUP_T_PROC_FLOOR` | 25 ms | Above healthy edge latency (~5–15 ms) |
| `SCALEUP_T_PROC_SPAN` | 80 | Code default |
| `SCALEUP_COMPUTE_BASE_THRESHOLD` | 0.18 | Lowered to compensate for wide CPU span |
| `SCALEUP_COMPUTE_THRESHOLD_INCREMENT` | 0.10 | Adaptive escalation |
| `SCALEUP_COMPUTE_MAX_THRESHOLD` | 0.85 | Ceiling |
| `SCALEUP_WINDOW_SIZE` | 5 | Telemetry windows evaluated |
| `SCALEUP_REQUIRED` | 3 | 3 of 5 must breach |
| `SCALEUP_COMPUTE_COOLDOWN_S` | 45 | Grace period per spawn |
| `SCALEUP_COMPUTE_PEER_RELIEF` | 0.03 | Score reduction per peer node |
| `SCALEUP_COMPUTE_PEER_HEALTH_THRESHOLD` | 0.35 | Peer considered healthy below this |
| `SCALEUP_STORAGE_CPU_FLOOR` | 1.5 | Matches tight CPU limits |
| `SCALEUP_STORAGE_CPU_SPAN` | 5 | Narrow span for constrained CPU range |
| `SCALEUP_T_DB_FLOOR` | 60 ms | Storage latency elevates earlier at 0.08 CPUs |
| `SCALEUP_T_DB_SPAN` | 250 ms | Narrower T_db range at this CPU level |
| `SCALEUP_STORAGE_BASE_THRESHOLD` | 0.35 | G0-v6 validated — storage scoring loop closes |
| `SCALEUP_STORAGE_THRESHOLD_INCREMENT` | 0.10 | Adaptive escalation |
| `SCALEUP_STORAGE_MAX_THRESHOLD` | 0.55 | Ceiling |
| `SCALEUP_STORAGE_WINDOW_SIZE` | 5 | Default |
| `SCALEUP_STORAGE_REQUIRED` | 2 | 2 of 5 must breach (faster than compute's 3/5) |
| `SCALEUP_STORAGE_COOLDOWN_S` | 120 | Default |
| `SCALEDOWN_COMPUTE_COOLDOWN_S` | 180 | Keeps nodes alive through phase transitions |
| `SCALE_DOWN_COMPUTE_REQUIRED` | 9 | Strong evidence of sustained low load |
| `SCALE_DOWN_COMPUTE_WINDOW_SIZE` | 12 | Default |
| `SCALEDOWN_STORAGE_COOLDOWN_S` | 120 | Default |
| `SCALE_DOWN_STORAGE_WINDOW_SIZE` | 12 | Default |
| `SCALE_DOWN_STORAGE_REQUIRED` | 7 | Default |
| `TELEMETRY_TIMEOUT_WINDOWS` | 18 | ~180 s without telemetry → node marked dead |
| `NODE_BIRTH_GRACE_S` | 60 | Skip dead-node detection for first 60 s |

---

## 5. Run Matrix

3 modes × 3 replicates = 9 runs. Grouped by mode for operational efficiency.

| # | Label | Mode | Env Override File | Compute W | Storage W |
|---|-------|------|-------------------|-----------|-----------|
| DS1 | `rq3_v5_ds_1` | degradation_score | `rq3_v2_degradation_score.env` | 0.40/0.60 | 0.20/0.80 |
| DS2 | `rq3_v5_ds_2` | degradation_score | `rq3_v2_degradation_score.env` | 0.40/0.60 | 0.20/0.80 |
| DS3 | `rq3_v5_ds_3` | degradation_score | `rq3_v2_degradation_score.env` | 0.40/0.60 | 0.20/0.80 |
| CO1 | `rq3_v5_cpu_1` | cpu_only | `rq3_v2_cpu_only.env` | 1.00/0.00 | 1.00/0.00 |
| CO2 | `rq3_v5_cpu_2` | cpu_only | `rq3_v2_cpu_only.env` | 1.00/0.00 | 1.00/0.00 |
| CO3 | `rq3_v5_cpu_3` | cpu_only | `rq3_v2_cpu_only.env` | 1.00/0.00 | 1.00/0.00 |
| LO1 | `rq3_v5_lat_1` | latency_only | `rq3_v2_latency_only.env` | 0.00/1.00 | 0.00/1.00 |
| LO2 | `rq3_v5_lat_2` | latency_only | `rq3_v2_latency_only.env` | 0.00/1.00 | 0.00/1.00 |
| LO3 | `rq3_v5_lat_3` | latency_only | `rq3_v2_latency_only.env` | 0.00/1.00 | 0.00/1.00 |

> **Label convention**: This plan uses `rq3_v5_*` labels (v5 evaluation). The
> `rq3_setup_v2.md` §10 declares `rq3_v2_*` — that doc predates the calibration
> and uses outdated storage weights. This plan's v5 labels are authoritative.

**Run order**: DS1→DS2→DS3, then CO1→CO2→CO3, then LO1→LO2→LO3.
Grouped by mode for env-file efficiency (no switching between runs of same
mode).

**Between every run**: full cleanup on VM + VM reboot (`sudo shutdown -r now`).
No shared state.

**Total wall-clock estimate**: 9 × (~24 min run + ~5 min cleanup/reboot) ≈
**4.4 hours**.

---

## 6. Run Configuration

### 6.1 Prerequisites (Verified Before First Run)

- [ ] Cloud VM reachable at `ssh cloud-vm`
- [ ] `sudo -n` working (passwordless sudo)
- [ ] Mean-only latency signal deployed in `scaling_policy.py`:
  ```python
  # compute_latency_signal() returns ds.avg_time_proc_ms
  # storage_latency_signal() returns ds.avg_time_db_ms
  ```
- [ ] Three env override files synced to cloud VM:
  - `source/scripts/testing/controller_env_overrides/rq3_v2_degradation_score.env`
  - `source/scripts/testing/controller_env_overrides/rq3_v2_cpu_only.env`
  - `source/scripts/testing/controller_env_overrides/rq3_v2_latency_only.env`
- [ ] Canonical `phases.json` is at `source/scripts/testing/phases.json`
- [ ] Docker images built with mean-only latency signal:
  ```bash
  ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && sudo -n make -C source/scripts build_images"
  ```
  Only needed once if images already contain the mean-only change.

### 6.2 Per-Run Launch (Concrete Invocation)

All 9 runs use the same base command. Only `RUN_LABEL` and
`OSKEN_ENV_OVERRIDE_FILE` change per run.

**Per-run launch** (from local, ssh into cloud-vm):

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  sudo -n STORAGE_CPUS=0.08 EDGE_CPUS=0.25 WAN_RTT_MS=185 RANDOM_SEED=42 \
    make -C source/scripts setup_network create_clients setup_test_data run_experiment \
    OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/<ENV_FILE> \
    RUN_LABEL=<LABEL> \
    PHASES_CONFIG=testing/phases.json \
    CLIENTS=48 CONTENT_ITEMS=6000 USERS=100 \
    DATA_SEED=42 CURL_MAX_TIME=30 \
    SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1 \
    2>&1" | tee logs/rq3_v5_<LABEL>.log; echo "EXIT: $?" | tee -a logs/rq3_v5_<LABEL>.log
```

> **Why the env vars are on the `sudo` line**: `STORAGE_CPUS`, `EDGE_CPUS`,
> `WAN_RTT_MS`, and `RANDOM_SEED` must be environment variables, not Make
> variables. Make does not export Make variables to the recipe environment
> by default. Placing them after `sudo -n` as `VAR=val` makes them visible
> to `build_network_setup.sh` (which reads `${STORAGE_CPUS:-0.15}` etc.) and
> `run_experiment.sh` (which reads `${RANDOM_SEED:-}`). `DATA_SEED` IS a
> Make variable (used by `setup_test_data` targets), so it stays in the
> `make` argument list.
>
> **Why `SKIP_*=1`**: The Make target chain `setup_network create_clients
> setup_test_data` already builds the network, creates clients, seeds MongoDB,
> and exports the workload snapshot. `run_experiment` with `SKIP_*=1` only
> runs the traffic generator and post-processing — no double execution. After
> a reboot, the Make targets recreate everything from scratch, so skipping
> the internal steps is correct.

#### Per-Run Substitutions

| Run | `<ENV_FILE>` | `<LABEL>` |
|---|---|---|
| DS1 | `rq3_v2_degradation_score.env` | `rq3_v5_ds_1` |
| DS2 | `rq3_v2_degradation_score.env` | `rq3_v5_ds_2` |
| DS3 | `rq3_v2_degradation_score.env` | `rq3_v5_ds_3` |
| CO1 | `rq3_v2_cpu_only.env` | `rq3_v5_cpu_1` |
| CO2 | `rq3_v2_cpu_only.env` | `rq3_v5_cpu_2` |
| CO3 | `rq3_v2_cpu_only.env` | `rq3_v5_cpu_3` |
| LO1 | `rq3_v2_latency_only.env` | `rq3_v5_lat_1` |
| LO2 | `rq3_v2_latency_only.env` | `rq3_v5_lat_2` |
| LO3 | `rq3_v2_latency_only.env` | `rq3_v5_lat_3` |

### 6.3 No Fault Plan

`--fault-plan` is **omitted**. Synthetic failure injection is not in scope
for RQ3 — the experiment measures detection behaviour under normal workload
transitions only.

### 6.4 Between-Run Procedure

```bash
# 1. Copy run folder from cloud-vm to local
#    Run folders are at source/scripts/testing/metrics/<timestamp>_<label>/
RUN_DIR=$(ssh cloud-vm "ls -dt ~/efficient-storage-in-edge-scenarios/source/scripts/testing/metrics/*_<LABEL>/ | head -1")
scp -r cloud-vm:"$RUN_DIR" \
    docs/operation/testing/experiment/rq3_evaluation/v5/metrics/

# 2. Cleanup metrics and Docker artifacts on VM
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  sudo -n rm -rf source/scripts/testing/metrics/* && \
  sudo -n make -C source/scripts cleanup_metrics"

# 3. Reboot VM
ssh cloud-vm "sudo shutdown -r now"

# 4. Wait for VM to come back (60–120 s typical)
until ssh -o ConnectTimeout=5 -o BatchMode=yes cloud-vm echo ok 2>/dev/null; do
  echo "Waiting for cloud-vm..."
  sleep 10
done
echo "cloud-vm is back."

# 5. Proceed to next run
```

---

## 7. Focus & Evidence

### 7.1 Primary Evidence — Detection Quality (M1–M4)

| Metric | Artifact | How extracted | Maps to graph |
|---|---|---|---|
| M1 — Baseline FP spawns | `elasticity_events.csv` | `grep -c 'scale-up.*triggered'` during `baseline` phase rows. Exclude `standby_storage: spawning reserve`. | G1, G1b |
| M2 — Stress spawn count | `elasticity_events.csv` | Spawns per stress phase (`storage_storm`, `tier1_hotspot`, `reverse_hotspot`, `compute_spike`), per tier. | G2 |
| M3 — Time-to-first-spawn | `elasticity_events.csv` | `first_spawn_ts − phase_start_ts` per stress phase, per mode. | G3 |
| M4 — Missed detections | `elasticity_events.csv` + `per_node_stats.csv` | Stress phases where per-node mean CPU AND per-node mean latency exceed thresholds but <1 spawn. Uses mean latency (not p95) because the controller's trigger evaluates mean latency — a missed detection is when the trigger should have fired based on the same signal it uses. | — |

### 7.2 Primary Evidence — Service Quality (M5–M7)

| Metric | Artifact | How extracted | Maps to graph |
|---|---|---|---|
| M5 — Per-phase latency | `client_requests.csv` | `metrics_stats.py` p50/p95/p99 per phase per mode. Disaggregated by phase type. | G4, G5, G5b |
| M6 — Timeout rate | `client_requests.csv` | Per-phase timeout rate (latency ≥ 29.9 s). | G6 |
| M7 — Throughput | `client_requests.csv` | Completed requests per stress phase per mode. | G7 |

### 7.3 Diagnostic Evidence

| Evidence | Artifact | Purpose |
|---|---|---|
| Score component decomposition | `policy_state.csv` | Reconstruct CPU and latency score components per window. Used for G8 (illustrative: one median replicate per mode). |
| Controller tracebacks | `controller_lan1.log`, `controller_lan2.log` | C1 gate — zero tracebacks required. |
| Phase completion | `current_phase.txt` | C1 gate — must reach `idle`. |
| Pre→post improvement | `per_node_stats.csv` | C8 — CPU and latency reduction from first-N to last-N rows of stress phases. |
| Container lifecycle | `container_events.csv` | Supplementary — spawn/stop timing for Tier 1 selective-sync anchors. |
| Resource balance | `resource_stats.csv` | Supplementary — CPU/RAM distribution across nodes. |

### 7.4 Expected Graph Outputs (10 Graphs)

| # | Graph | Domain | Type | Source artifact |
|---|---|---|---|---|
| G1 | Baseline FP Spawns by Mode | Detection | Grouped bar (SEM + scatter) | `elasticity_events.csv` |
| G1b | FP Spawn Score Components | Detection | 2D scatter (CPU vs latency components) | `policy_state.csv` |
| G2 | Stress Spawn Count by Mode & Phase | Detection | Grouped bar (SEM + scatter) | `elasticity_events.csv` |
| G3 | TTFS Distribution by Mode & Phase | Detection | Box plot + per-event scatter | `elasticity_events.csv` |
| G4 | Per-Phase p50 Latency by Mode | Service Quality | Grouped bar (SEM + scatter) | `client_requests.csv` |
| G5 | Baseline p50 Latency by Mode | Service Quality | Grouped bar (SEM + scatter) | `client_requests.csv` |
| G5b | Latency by Phase Type | Service Quality | Grouped bar (SEM + scatter) | `client_requests.csv` |
| G6 | Timeout Rate by Mode & Phase | Service Quality | Grouped bar (SEM + scatter) | `client_requests.csv` |
| G7 | Throughput by Mode & Stress Phase | Service Quality | Grouped bar (SEM + scatter) | `client_requests.csv` |
| G8 | Score Component Decomposition | Diagnostic | 3-panel line chart (one per mode, median replicate) | `policy_state.csv` |

Graph spec details in [`rq3_v2.md` §6](../../../../research_questions/rq3/rq3_v2.md).

---

## 8. Metrics & Success Criteria

| # | Criterion | Maps to | Pass condition | Artifact |
|---|---|---|---|---|
| C1 | Run completion | — | All 9 runs reach `idle`, zero controller tracebacks in all 18 logs (9 runs × 2 LANs). **Retry policy**: If a run fails (traceback, crash, or doesn't reach idle), retry once with the same label. If the retry also fails, abort the campaign and diagnose before continuing. A single failed run with a different label (e.g., `rq3_v5_ds_2_retry`) is acceptable and must be documented in the analysis. | `current_phase.txt`, `controller_lan*.log` |
| C2 | Within-mode consistency | M1–M7 | n=3 replicates per mode show consistent spawn counts and latency profiles (qualitative: no single replicate is an outlier by >2× the other two) | All artifacts |
| C3 | Baseline FP separation | M1, G1 | At least one pairwise comparison shows distinguishable FP spawn counts between modes (non-overlapping SEM bars) | `elasticity_events.csv` |
| C4 | Stress detection separation | M2, M3, G2, G3 | At least one pairwise comparison shows distinguishable spawn counts OR TTFS distributions | `elasticity_events.csv` |
| C5 | Missed detection asymmetry | M4 | At least one mode misses ≥1 detection that another mode catches, OR all modes detect equally (valid bounding result) | `elasticity_events.csv` + `per_node_stats.csv` |
| C6 | Service quality separation | M5, G4 | At least one pairwise comparison shows distinguishable per-phase latency (non-overlapping SEM bars in at least one phase) | `client_requests.csv` |
| C7 | Throughput-waste relationship | M7, G7 | If spawn counts differ between modes, throughput either differs (under-detection) or does not (waste). Both outcomes are informative — criterion passes if the relationship is measurable. | `client_requests.csv` |
| C8 | Scaling prerequisite | §3.6 of rq3_v2.md | Pre-scale→post-scale improvement in CPU and latency confirmed for degradation_score mode at the G0-v6 resource configuration (≥15pp CPU drop, latency reduction visible) | `per_node_stats.csv` |

---

## 9. Checkpoints (In-Run — Runner May Observe, Not Act)

| # | When | What to check | Question |
|---|---|---|---|
| CP1 | After `baseline` phase (~60 s) | `grep -c 'Traceback' controller_lan1.log controller_lan2.log` | Zero tracebacks? If not, abort run. |
| CP2 | Mid `storage_storm` (~180 s) | `docker ps -q | wc -l` shows container count rising | Are spawns occurring? Sanity check that the mode is not inert. If a mode produces 0 spawns by mid-storage_storm, note it (do not abort — any outcome is informative per §2). |
| CP3 | After `compute_spike` (~18 min) | `grep -c 'scale-up.*triggered' controller_lan*.log` | Spawn counts in expected ballpark? Post-calibration expected ranges: DS compute ~5 (C-W20 anchor, n=1), DS storage ~18; CO compute 13–19, CO storage 22–24; LO compute ~3, LO storage 15–17. Large deviations (>3× expected) may indicate configuration error. Note: DS compute n=1 at calibrated weights — true range unknown; flag deviations for the analyst. |
| CP4 | End of run | `cat current_phase.txt` shows `idle` | Run completed normally? |
| CP5 | Before reboot | `ls source/scripts/testing/metrics/<run_folder>/` has all 12 standard artifacts | All post-processing scripts ran? |

---

## 10. Validity Threats & Limitations

| # | Threat | Mitigation |
|---|---|---|
| V1 | **Single workload family** — content-discovery only. Results may not generalize to IoT ingestion or other workload shapes. | Acknowledged as scope limitation. The thesis evaluates one representative stateful edge service. |
| V2 | **n=3 replicates** — SEM bars with n=3 are wide. Small-N limits statistical power for formal tests. | SEM + scatter dots show per-replicate spread. Qualitative consistency check (C2) rather than formal t-tests. |
| V3 | **Mean-only latency signal** — excludes p95 from trigger input. The composite mode might behave differently with percentile inputs. | The mean-only choice is justified (timeout-censored p95 contamination) and documented in `rq3_setup_v2.md` §7.1. |
| V4 | **latency_only variance** — calibration showed 350% D3 score spread for latency_only (0.024 vs 0.108). This mode may be sensitive to run-to-run workload alignment. | n=3 provides a third replicate to narrow the variance estimate. Flagged in analysis. |
| V5 | **Storage CPU weight at n=1** — the 0.20 weight was calibrated from a single complete run (C-W20, 18 storage spawns) and one partial run (C-W20_R, stalled). The true mean storage spawn count at this weight is uncertain. | The n=3 degradation_score replicates in the evaluation will provide the first robust estimate of storage spawn count at 0.20/0.80. If the true mean is outside the 15–24 range, update the thesis narrative. |
| V6 | **No scale-down analysis** — the experiment evaluates detection and service quality but does not analyze scale-down behaviour differences between modes. | Deferred to future work. Scale-down parameters are held constant. |
| V7 | **Weight sensitivity unexplored** — only three points in the weight space (0/0.4/1.0 for CPU, 0/0.6/1.0 for latency). The shape of the detection surface between these points is unknown. | The three modes are the logical extremes + the system default. Weight sweeps deferred to future work. |
| V8 | **Resource env vars passed via sudo** — `STORAGE_CPUS`, `EDGE_CPUS`, and `WAN_RTT_MS` must be environment variables (consumed by `build_network_setup.sh`), not Make variables. `RANDOM_SEED` must be an environment variable (consumed by `run_experiment.sh`). The launch command in §6.2 places them after `sudo -n` as `VAR=val`, which makes them visible to both scripts. | Runner must verify with `docker inspect` after `setup_network` that containers have the correct `--cpus` values and WAN emulation. Runner must verify the `--random-seed` flag appears in the traffic-generator log. |

---

## 11. Artifact Contract

### 11.1 Standard Run-Folder Artifacts (Per `testing_overview.md`)

| # | Artifact | Present? |
|---|---|---|
| 1 | `client_requests.csv` | ✅ |
| 2 | `resource_stats.csv` | ✅ |
| 3 | `resource_stats_debug.csv` | ✅ |
| 4 | `policy_state.csv` | ✅ |
| 5 | `per_node_stats.csv` | ✅ |
| 6 | `container_events.csv` | ✅ |
| 7 | `elasticity_events.csv` | ✅ |
| 8 | `controller_lan1.log` | ✅ |
| 9 | `controller_lan2.log` | ✅ |
| 10 | `controller_env_snapshot.env` | ✅ |
| 11 | `phases_snapshot.json` | ✅ |
| 12 | `service_logs/` | ✅ |

### 11.2 Experiment-Specific Artifacts

| Artifact | Location | Purpose |
|---|---|---|
| Local run logs | `docs/operation/testing/experiment/rq3_evaluation/v5/logs/rq3_v5_<LABEL>.log` | Tee'd ssh output — preserves launch timestamp, any ssh errors, and run exit code |
| Run folders | `docs/operation/testing/experiment/rq3_evaluation/v5/metrics/<run_folder>/` | Copied from cloud-vm after each run |
| Analysis outputs | `docs/operation/testing/experiment/rq3_evaluation/v5/analysis/` | 10 graphs (G1–G8 + G1b + G5b) + `rq3_eval_v5_findings.md` |

### 11.3 Prerequisite: Verify Artifact Generation

Before the campaign, run a single smoke-test run (any mode, e.g., DS1 with
`RUN_LABEL=rq3_v5_smoke`) and verify ALL 12 artifacts are present in the
run folder, with particular attention to:
- `per_node_stats.csv` — needed for C8 (pre→post improvement) and M4
- `policy_state.csv` — needed for G8 (score component decomposition)
- `controller_env_snapshot.env` — needed to confirm thresholds were applied

### 11.4 Post-Evaluation

After all 9 runs are copied locally, the **Edge Experiment Analyzer** agent
produces:

1. **10 graphs** per the graph spec in `rq3_v2.md` §6, with n=3 per mode error bars
2. **`rq3_eval_v5_findings.md`** — structured findings against C1–C8, per-mode summaries, and thesis narrative alignment
3. **Cross-RQ comparison** — M2, M5, M7 values against RQ1 and RQ2 baseline numbers for the detection→delivery→action chain narrative

---

## References

- [RQ3 v2 — Trigger Composition Characterization](../../../../research_questions/rq3/rq3_v2.md) — measurement framework, M1–M7, G1–G8, C1–C8
- [RQ3 v2 — Experiment Setup Declaration](../../../../research_questions/rq3/rq3_setup_v2.md) — canonical phases, resource limits, scoring parameters (outdated storage weights: use this plan's 0.20/0.80)
- [Divergence Calibration Results](calibration_results_v2.md) — G0-v6 threshold confirmation, storage CPU weight probe, D1–D3 divergence checks
- [Divergence Calibration Plan](calibration_plan.md) — superseded by results
- [Testing Overview](../../testing_overview.md) — standard artifact contract, golden config
- [RQ3 env override — degradation_score](../../../../source/scripts/testing/controller_env_overrides/rq3_v2_degradation_score.env)
- [RQ3 env override — cpu_only](../../../../source/scripts/testing/controller_env_overrides/rq3_v2_cpu_only.env)
- [RQ3 env override — latency_only](../../../../source/scripts/testing/controller_env_overrides/rq3_v2_latency_only.env)
