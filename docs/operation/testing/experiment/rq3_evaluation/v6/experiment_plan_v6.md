# RQ3 v6 — Trigger Composition Evaluation

**Status**: 🔵 Designed · **Date**: 2026-07-28 · **Supersedes**: [v5](../v5/experiment_plan_v5.md)
**Depends on**: [Divergence calibration](../v5/calibration_results_v2.md) (✅ complete — 8 runs)
**Canonical RQ doc**: [`rq3_v6.md`](../../../../research_questions/rq3/rq3_v6.md)
**Setup reference**: [`rq3_setup_v6.md`](../../../../research_questions/rq3/rq3_setup_v6.md) — definitive parameter declaration
**Graph spec**: [`rq3_v6.md`](../../../../research_questions/rq3/rq3_v6.md) §6 — G1–G8 + G1b + G5b + G7b + G9–G12 (16 graphs)
**Graph generation skill**: [`.github/skills/rq3-cross-mode-comparison/SKILL.md`](../../../../.github/skills/rq3-cross-mode-comparison/SKILL.md) (note: skill uses v5 paths — update for v6 before running)

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
| `degradation_score` | 0.40 / 0.60 | **0.20 / 0.80** | Cross-signal confirmation (system default) |
| `cpu_only` | 1.00 / 0.00 | 1.00 / 0.00 | Industry default (CPU alone) |
| `latency_only` | 0.00 / 1.00 | 0.00 / 1.00 | User-experience dimension (latency alone) |

> **Storage weights**: Calibrated from 0.60/0.40 → 0.20/0.80 via storage CPU
> weight probe ([`calibration_results_v2.md`](../v5/calibration_results_v2.md) §6).
> `rq3_v2.md` §3.3 and `rq3_setup_v2.md` §3.1/§4.1 still show 0.60/0.40 —
> those docs are stale. This plan's 0.20/0.80 is authoritative.

---

## 2. Hypothesis / Expected Outcome

**Compute tier — three-way divergence**: cpu_only produces the most spawns
(highest scores, CPU dominates), latency_only produces the fewest (T_proc
rarely crosses floor=25ms at this workload), degradation_score sits between
them. Both signals are independently meaningful at 0.25 CPUs.

**Storage tier — partial separation**: degradation_score at calibrated
0.20/0.80 (~18 spawns) sits between cpu_only (22–24, CPU-dominated) and
latency_only (15–17, T_db-only). The CPU signal is real but weak at 0.08
CPUs — T_db is the primary driver. This bounds the trigger composition
space: only the compute tier has two independently meaningful signals.

**Composite = fewest FPs + equivalent detection**: degradation_score
produces the fewest baseline false positives (both signals must spike
simultaneously) without sacrificing stress detection or throughput.

**Any outcome is informative** (`rq3_v2.md` §4.3):
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
detection→delivery→action chain. Full measurement framework in
[`rq3_v2.md` §5](../../../../research_questions/rq3/rq3_v2.md).

---

## 4. Independent Variable & Held-Constant Set

### 4.1 Independent Variable

**Four weight coefficients** — the only things that differ across the 9 runs:

| Variable | degradation_score | cpu_only | latency_only |
|---|---|---|---|
| `SCALEUP_W_CPU` | 0.40 | 1.00 | 0.00 |
| `SCALEUP_W_T_PROC` | 0.60 | 0.00 | 1.00 |
| `SCALEUP_W_STORAGE_CPU` | **0.20** | 1.00 | 0.00 |
| `SCALEUP_W_T_DB` | **0.80** | 0.00 | 1.00 |

> Env override files are named `rq3_v2_*.env` because they were authored for
> the rq3_v2.md measurement framework. The "v2" refers to the RQ doc version,
> not the experiment version. The files are correct for v6.

### 4.2 Held Constant (Identical Across All 9 Runs)

| Parameter | Value | Why fixed |
|---|---|---|
| **Scoring floors, spans, thresholds** | See §4.3 | All modes evaluated under identical detection thresholds |
| **Phases** | `testing/phases_override/phases_rq1_7phase.json` (7 phases, 1,440 s) | Same workload the calibration used; has `compute_spike` for pure compute isolation. See §4.4 for phase details. |
| **Resource limits** | STORAGE_CPUS=0.08, EDGE_CPUS=0.25, WAN_RTT_MS=185 | G0-v6 validated. EDGE_CPUS=0.25 is definitive. |
| **Client count** | CLIENTS=96 (48/LAN) | RQ1 v8 golden; matches RQ1/RQ2 |
| **Telemetry delivery** | Push (ZMQ, window-close) | Held constant — RQ1's domain; eliminates monitoring blind spot |
| **Routing policy** | Warm lease (`topology_lifecycle`) | Held constant — RQ2's domain; eliminates LB discovery gap |
| **Seeds** | RANDOM_SEED=42, DATA_SEED=42 | Deterministic workload across runs |
| **Tier 1 selective sync** | SS_ENABLED=1 | Fixed — exercises Tier 1 pool; identical for all modes |
| **Persistent reserve** | STORAGE_PERSISTENT_RESERVE_ENABLED=1 | Fixed — reserve spawns excluded from M1 (baseline FP) counts |
| **Latency signal** | Mean-only (`avg_time_proc_ms`, `avg_time_db_ms`) | Code path in `scaling_policy.py`; avoids timeout-censored p95 contamination |
| **VIP routing** | `BACKEND_SELECTION_POLICY=topology_lifecycle`, `VIP_HARD_TIMEOUT=60` | RQ2's domain; warm lease at spawn time |
| **Scale-down** | COOLDOWN=180s, REQUIRED=9, WINDOW=12 | RQ1 v8 golden; identical for all modes |
| **Max dynamic nodes** | COMPUTE=12, STORAGE=8 | RQ1 v8 golden |
| **CURL_MAX_TIME** | 30 s | Hard client timeout |
| **Fault plan** | None | Synthetic failure not in scope |

### 4.3 Scoring Parameters (All Modes — Identical)

All values from `current_state_integrated.env` (G0-v6 validated), confirmed
in divergence calibration ([`calibration_results_v2.md`](../v5/calibration_results_v2.md)).

**Compute:**
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

**Storage:**
| Parameter | Value | Role |
|---|---|---|
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

**Scale-down / lifecycle:**
| Parameter | Value | Role |
|---|---|---|
| `SCALEDOWN_COMPUTE_COOLDOWN_S` | 180 | Keeps nodes alive through phase transitions |
| `SCALE_DOWN_COMPUTE_REQUIRED` | 9 | Strong evidence of sustained low load |
| `SCALE_DOWN_COMPUTE_WINDOW_SIZE` | 12 | Default |
| `SCALEDOWN_STORAGE_COOLDOWN_S` | 120 | Default |
| `SCALE_DOWN_STORAGE_WINDOW_SIZE` | 12 | Default |
| `SCALE_DOWN_STORAGE_REQUIRED` | 7 | Default |
| `TELEMETRY_TIMEOUT_WINDOWS` | 18 | ~180 s without telemetry → node marked dead |
| `NODE_BIRTH_GRACE_S` | 60 | Skip dead-node detection for first 60 s |

### 4.4 Phase Details — `phases_rq1_7phase.json`

| # | Phase | Duration | Rate/client | Cross-region | Client frac | Dominant mix |
|---|-------|----------|-------------|--------------|-------------|-------------|
| 1 | `baseline` | 60 s | 1.0 | 0% | 50% | 60% lookup, 25% ranking, 15% pressure |
| 2 | `storage_storm` | 240 s | 4.0 | 90% | 100% | 35% lookup, 30% update, 20% aggregate, 10% ranking, 5% pressure |
| 3 | `tier1_hotspot` | 180 s | 5.0 | 95% | 100% | 80% lookup — Tier 1 selective-sync stress |
| 4 | `inter_hotspot_cooldown` | 300 s | 1.0 | 0% | 10% | baseline mix — drain before reverse hotspot |
| 5 | `reverse_hotspot` | 180 s | 5.0 | 95% | 100% | 80% lookup — hotspot direction reversed |
| 6 | `compute_spike` | 180 s | 4.0 | 5% | 100% | 65% feed_ranking, 20% lookup, 15% pressure — compute-bound |
| 7 | `demand_drop` | 300 s | 1.0 | 0% | 10% | baseline mix — extended drain for scale-down |

> **compute_spike mix note**: The actual JSON uses `{content_lookup: 0.20,
> feed_ranking: 0.65, service_pressure: 0.15}` — not 100% service_pressure as
> `rq3_setup_v2.md` §1 states. Feed_ranking is the dominant operation at 65%,
> which is CPU-intensive (ranking computation). The 5% cross-region ratio is
> near-zero, keeping storage I/O minimal. This is a realistic compute-heavy
> workload. The calibration's D3 divergence check used this exact mix and
> produced clear three-way separation.

**Why no cleanup gaps**: Unlike RQ1 (which needs gaps to isolate detection
speed between phases), RQ3 evaluates detection *composition*. Nodes may
persist across phases — cooldowns are sufficient. The `inter_hotspot_cooldown`
(300s) is the only drain phase between the two hotspot phases; `demand_drop`
(300s) is the final drain.

**Phase type grouping** (for G5b — Latency by Phase Type):

| Group | Phases | Dominant latency factor |
|---|---|---|
| **Baseline** | baseline | Routing quality — only phase guaranteed to start quiescent |
| **Storage stress** | storage_storm, tier1_hotspot, reverse_hotspot | Storage I/O (content_update, content_aggregate, cross-region MongoDB reads) |
| **Compute stress** | compute_spike | CPU saturation (feed_ranking, service_pressure) |
| **Post-stress** | inter_hotspot_cooldown, demand_drop | Mixed — residual effects from preceding stress phase |

---

## 5. Run Matrix

3 modes × 3 replicates = 9 runs. Grouped by mode for operational efficiency.

| # | Label | Mode | Env Override File |
|---|-------|------|-------------------|
| DS1 | `rq3_v6_ds_1` | degradation_score | `rq3_v2_degradation_score.env` |
| DS2 | `rq3_v6_ds_2` | degradation_score | `rq3_v2_degradation_score.env` |
| DS3 | `rq3_v6_ds_3` | degradation_score | `rq3_v2_degradation_score.env` |
| CO1 | `rq3_v6_cpu_1` | cpu_only | `rq3_v2_cpu_only.env` |
| CO2 | `rq3_v6_cpu_2` | cpu_only | `rq3_v2_cpu_only.env` |
| CO3 | `rq3_v6_cpu_3` | cpu_only | `rq3_v2_cpu_only.env` |
| LO1 | `rq3_v6_lat_1` | latency_only | `rq3_v2_latency_only.env` |
| LO2 | `rq3_v6_lat_2` | latency_only | `rq3_v2_latency_only.env` |
| LO3 | `rq3_v6_lat_3` | latency_only | `rq3_v2_latency_only.env` |

> **Env file naming**: `rq3_v2_*.env` refers to the RQ3 v2 measurement
> framework doc — not the experiment version. These are the correct files.

**Run order**: DS1→DS2→DS3, then CO1→CO2→CO3, then LO1→LO2→LO3.
Grouped by mode for env-file efficiency (no switching between runs of same
mode).

**Between every run**: full cleanup on VM + VM reboot (`sudo shutdown -r now`).
No shared state.

**Total wall-clock estimate**: 9 × (~24 min run + ~5 min cleanup/reboot) ≈
**4.4 hours**.

---

## 6. Run Configuration

### 6.0 Pre-Flight Smoke Test (Mandatory — Before the 9-Run Matrix)

A single short smoke-test run MUST pass before the campaign begins. This
verifies the end-to-end pipeline: mean-only latency signal, env override
application, artifact generation, and resource configuration.

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  sudo -n STORAGE_CPUS=0.08 EDGE_CPUS=0.25 WAN_RTT_MS=185 RANDOM_SEED=42 \
    make -C source/scripts setup_network create_clients setup_test_data run_experiment \
    OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/rq3_v2_degradation_score.env \
    RUN_LABEL=rq3_v6_smoke \
    PHASES_CONFIG=testing/phases_override/phases_rq1_7phase.json \
    CLIENTS=48 CONTENT_ITEMS=6000 USERS=100 \
    DATA_SEED=42 CURL_MAX_TIME=30 \
    SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1 \
    2>&1" | tee docs/operation/testing/experiment/rq3_evaluation/v6/logs/rq3_v6_smoke.log

# Capture actual exit code — PIPESTATUS[0] is ssh's exit code, not tee's
echo "EXIT: ${PIPESTATUS[0]}" | tee -a docs/operation/testing/experiment/rq3_evaluation/v6/logs/rq3_v6_smoke.log
```

> **Pipe exit code**: `$?` after `| tee` captures tee's exit code (always 0).
> `${PIPESTATUS[0]}` captures ssh/make's actual exit code. If the experiment
> crashes, this will be non-zero.

**Smoke-test verification checklist:**

- [ ] Run reaches `demand_drop` (final phase) — traffic generator exits normally
- [ ] Zero controller tracebacks (`grep -c Traceback controller_lan*.log` returns 0 for both)
- [ ] All 12 standard artifacts present (see §11.1)
- [ ] `controller_env_snapshot.env` confirms weights: `SCALEUP_W_CPU=0.40`, `SCALEUP_W_T_PROC=0.60`, `SCALEUP_W_STORAGE_CPU=0.20`, `SCALEUP_W_T_DB=0.80`
- [ ] Resource limits verified. On cloud VM:
  ```bash
  docker inspect $(docker ps -q --filter name=edge_server) --format '{{.Name}}: {{.HostConfig.NanoCpus}}'
  # Expected: edge_server_lan1: 250000000 (0.25 CPUs), edge_storage_server_lan1: 80000000 (0.08 CPUs)
  ```
- [ ] WAN emulation active. On cloud VM, check the router container:
  ```bash
  docker exec ubuntu-nat-router tc qdisc show dev eth0 | grep delay
  # Expected: delay 92.5ms (185ms RTT = 92.5ms each direction)
  ```
- [ ] `--random-seed 42` appears in traffic-generator output (search log for `random-seed`)
- [ ] `per_node_stats.csv` is non-empty and has columns: `cpu_perc`, `avg_time_proc_ms`, `avg_time_db_ms`
- [ ] `policy_state.csv` is non-empty and has `compute_score`/`storage_score` columns
- [ ] Spawn events appear in `elasticity_events.csv` during stress phases
- [ ] Copy smoke-test run folder locally:
  ```bash
  RUN_DIR=$(ssh cloud-vm "ls -dt ~/efficient-storage-in-edge-scenarios/source/scripts/testing/metrics/*rq3_v6_smoke*/ | head -1")
  scp -r cloud-vm:"$RUN_DIR" docs/operation/testing/experiment/rq3_evaluation/v6/metrics/
  ```

**If smoke test fails**: diagnose and fix before proceeding. Common failure
modes: mean-only latency signal not deployed → rebuild images; wrong CPU limits
→ check `sudo -n` env var propagation; missing artifacts → check post-processing
scripts ran.

### 6.1 Prerequisites (Verified Before First Run)

- [ ] Cloud VM reachable at `ssh cloud-vm`
- [ ] `sudo -n` working (passwordless sudo)
- [ ] **Mean-only latency signal deployed** in `scaling_policy.py`:
  ```python
  @staticmethod
  def compute_latency_signal(ds: DomainSummary) -> float:
      """Mean proc latency — avoids timeout-censored p95 contamination."""
      return ds.avg_time_proc_ms

  @staticmethod
  def storage_latency_signal(ds: DomainSummary) -> float:
      """Mean DB latency — avoids timeout-censored p95 contamination."""
      return ds.avg_time_db_ms
  ```
  Verify on VM: `ssh cloud-vm "grep -E 'def compute_latency_signal|def storage_latency_signal' ~/efficient-storage-in-edge-scenarios/source/sdn_controller/scaling_policy.py"`
- [ ] Three env override files synced to cloud VM (contents verified against §4.1 and §4.3):
  - `source/scripts/testing/controller_env_overrides/rq3_v2_degradation_score.env`
  - `source/scripts/testing/controller_env_overrides/rq3_v2_cpu_only.env`
  - `source/scripts/testing/controller_env_overrides/rq3_v2_latency_only.env`
- [ ] `phases_rq1_7phase.json` is at `source/scripts/testing/phases_override/phases_rq1_7phase.json`
- [ ] Docker images rebuilt with mean-only latency signal:
  ```bash
  ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && sudo -n make -C source/scripts build_images"
  ```
- [ ] Smoke test passed (see §6.0)

### 6.2 Per-Run Launch (Concrete Invocation)

All 9 runs use the same base command. Only `RUN_LABEL` and
`OSKEN_ENV_OVERRIDE_FILE` change per run.

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  sudo -n STORAGE_CPUS=0.08 EDGE_CPUS=0.25 WAN_RTT_MS=185 RANDOM_SEED=42 \
    make -C source/scripts setup_network create_clients setup_test_data run_experiment \
    OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/<ENV_FILE> \
    RUN_LABEL=<LABEL> \
    PHASES_CONFIG=testing/phases_override/phases_rq1_7phase.json \
    CLIENTS=48 CONTENT_ITEMS=6000 USERS=100 \
    DATA_SEED=42 CURL_MAX_TIME=30 \
    SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1 \
    2>&1" | tee docs/operation/testing/experiment/rq3_evaluation/v6/logs/rq3_v6_<LABEL>.log

echo "EXIT: ${PIPESTATUS[0]}" | tee -a docs/operation/testing/experiment/rq3_evaluation/v6/logs/rq3_v6_<LABEL>.log
```

> **Env vars on `sudo` line**: `STORAGE_CPUS`, `EDGE_CPUS`, `WAN_RTT_MS`,
> and `RANDOM_SEED` are placed after `sudo -n` as `VAR=val`, making them
> environment variables visible to `build_network_setup.sh` and
> `run_experiment.sh`. Make does not export Make variables to the recipe
> environment. `DATA_SEED` IS a Make variable (used by `setup_test_data`
> targets), so it stays in the `make` argument list.
>
> **`SKIP_*=1`**: The Make target chain `setup_network create_clients
> setup_test_data` builds the network, creates clients, seeds MongoDB, and
> exports the snapshot. `run_experiment` with `SKIP_*=1` only runs the
> traffic generator and post-processing. After a reboot, the Make targets
> recreate everything from scratch — no double execution.

#### Per-Run Substitutions

| Run | `<ENV_FILE>` | `<LABEL>` |
|---|---|---|
| DS1 | `rq3_v2_degradation_score.env` | `rq3_v6_ds_1` |
| DS2 | `rq3_v2_degradation_score.env` | `rq3_v6_ds_2` |
| DS3 | `rq3_v2_degradation_score.env` | `rq3_v6_ds_3` |
| CO1 | `rq3_v2_cpu_only.env` | `rq3_v6_cpu_1` |
| CO2 | `rq3_v2_cpu_only.env` | `rq3_v6_cpu_2` |
| CO3 | `rq3_v2_cpu_only.env` | `rq3_v6_cpu_3` |
| LO1 | `rq3_v2_latency_only.env` | `rq3_v6_lat_1` |
| LO2 | `rq3_v2_latency_only.env` | `rq3_v6_lat_2` |
| LO3 | `rq3_v2_latency_only.env` | `rq3_v6_lat_3` |

### 6.3 No Fault Plan

`--fault-plan` is **omitted**. Synthetic failure injection is not in scope.

### 6.4 Between-Run Procedure

```bash
# 1. Copy run folder from cloud-vm to local
#    Run folders are at source/scripts/testing/metrics/<timestamp>_<label>/
RUN_DIR=$(ssh cloud-vm "ls -dt ~/efficient-storage-in-edge-scenarios/source/scripts/testing/metrics/*_<LABEL>/ | head -1")
scp -r cloud-vm:"$RUN_DIR" \
    docs/operation/testing/experiment/rq3_evaluation/v6/metrics/

# 2. Cleanup Docker artifacts and metrics on VM
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
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

> **If the VM does not return within 5 minutes**: the reboot may have hung
> (kernel panic, fsck, hypervisor issue). Contact the VM administrator.
> Mark the current run's status in the campaign log.

---

## 7. Focus & Evidence

### 7.1 Primary Evidence — Detection Quality (M1–M4)

| Metric | Artifact | How extracted | Maps to graph |
|---|---|---|---|
| M1 — Baseline FP spawns | `elasticity_events.csv` | Score-triggered spawns during `baseline` phase. Exclude `standby_storage: spawning reserve`. | G1, G1b |
| M2 — Stress spawn count | `elasticity_events.csv` | Spawns per stress phase (`storage_storm`, `tier1_hotspot`, `reverse_hotspot`, `compute_spike`), per tier. | G2 |
| M3 — Time-to-first-spawn | `elasticity_events.csv` | `first_spawn_ts − phase_start_ts` per stress phase, per mode. | G3 |
| M4 — Missed detections | `elasticity_events.csv` + `per_node_stats.csv` | Stress phases where per-node mean CPU AND per-node mean latency exceed thresholds but <1 spawn. Uses mean latency (not p95) — must match the controller's actual trigger signal. | — |

### 7.2 Primary Evidence — Service Quality (M5–M7)

| Metric | Artifact | How extracted | Maps to graph |
|---|---|---|---|
| M5 — Per-phase latency | `client_requests.csv` | p50/p95/p99 per phase per mode. Disaggregated by phase type (baseline, storage-stress, compute-stress, post-stress). | G4, G5, G5b |
| M6 — Timeout rate | `client_requests.csv` | Per-phase timeout rate (latency ≥ 29.9 s). | G6 |
| M7 — Throughput | `client_requests.csv` | Completed requests per stress phase per mode. | G7 |

### 7.3 Diagnostic Evidence

| Evidence | Artifact | Purpose |
|---|---|---|
| Score component decomposition | `policy_state.csv` | Reconstruct CPU and latency score components per window. Used for G8 (illustrative: median replicate per mode by total spawn count). |
| Controller tracebacks | `controller_lan1.log`, `controller_lan2.log` | C1 gate — zero tracebacks required. |
| Phase completion | `current_phase.txt` | C1 gate — traffic generator must exit normally after `demand_drop` (final phase). The run completes when the traffic generator finishes, not when it reaches a specific phase name. |
| Pre→post improvement | `per_node_stats.csv` | C8 — CPU and latency reduction from first-N to last-N rows of stress phases. |
| Container lifecycle | `container_events.csv` | Supplementary — spawn/stop timing. |
| Resource balance | `resource_stats.csv` | Supplementary — CPU/RAM distribution across nodes. |

### 7.4 Expected Graph Outputs (10 Graphs)

Generated by `campaign_analysis.py` (see `.github/skills/rq3-cross-mode-comparison/SKILL.md`
for full spec — note: update v5 paths to v6 before running):

| # | Graph | File | Domain | Type | Source artifact |
|---|---|---|---|---|---|
| G1 | Baseline FP Spawns by Mode | `g1_baseline_fp_spawns.png` | Detection | Grouped bar (SEM + scatter) | `elasticity_events.csv` |
| G1b | FP Spawn Score Components | `g1b_fp_score_components.png` | Detection | 2D scatter (CPU vs latency) | `policy_state.csv` |
| G2 | Stress Spawn Count by Mode & Phase | `g2_stress_spawn_count.png` | Detection | Grouped bar (SEM + scatter) | `elasticity_events.csv` |
| G3 | TTFS Distribution by Mode & Phase | `g3_ttfs_distribution.png` | Detection | Box plot + per-event scatter | `elasticity_events.csv` |
| G4 | Per-Phase p50 Latency by Mode | `g4_per_phase_p50.png` | Service Quality | Grouped bar (SEM + scatter) | `client_requests.csv` |
| G5 | Baseline p50 Latency by Mode | `g5_baseline_p50.png` | Service Quality | Grouped bar (SEM + scatter) | `client_requests.csv` |
| G5b | Latency by Phase Type | `g5b_phase_type_p50.png` | Service Quality | Grouped bar (SEM + scatter) | `client_requests.csv` |
| G6 | Timeout Rate by Mode & Phase | `g6_timeout_rate.png` | Service Quality | Grouped bar (SEM + scatter) | `client_requests.csv` |
| G7 | Throughput by Mode & Stress Phase | `g7_throughput.png` | Service Quality | Grouped bar (SEM + scatter) | `client_requests.csv` |
| G8 | Score Component Decomposition | `g8_score_components.png` | Diagnostic | 3-panel line chart | `policy_state.csv` |

### Extended Graphs — Provisioning Efficiency & Node Overhead

| # | Graph | File | Domain | Type | Source artifact |
|---|---|---|---|---|---|
| G7b | Throughput-per-Resource by Mode | `g7b_throughput_per_resource.png` | Efficiency | Grouped bar (SEM + scatter) | `client_requests.csv` + `elasticity_events.csv` |
| G9 | Cumulative Resource-Time by Mode & Tier | `g9_resource_time.png` | Efficiency | Grouped bar (SEM + scatter) | `elasticity_events.csv` + `container_events.csv` |
| G10 | Dynamic Node Count Over Time | `g10_node_count_timeline.png` | Overhead | 3-panel line chart | `elasticity_events.csv` |
| G10b | Peak & Mean Node Count | `g10b_peak_mean_nodes.png` | Overhead | Grouped bar (SEM + scatter) | `elasticity_events.csv` |
| G11 | Cross-Tier Spawn Contamination | `g11_cross_tier.png` | Diagnostic | Grouped bar (SEM + scatter) | `elasticity_events.csv` |
| G12 | Node Lifetime Distribution | `g12_node_lifetimes.png` | Diagnostic | Box plot + per-event scatter | `container_events.csv` |

---

## 8. Metrics & Success Criteria

| # | Criterion | Maps to | Pass condition | Artifact |
|---|---|---|---|---|
| C1 | Run completion | — | All 9 runs reach `idle`, zero controller tracebacks in all 18 logs (9 runs × 2 LANs). **Retry policy**: If a run fails (traceback, crash, or doesn't reach idle), retry once with the same label. If the retry also fails, abort the campaign and diagnose. A single failed run with a different label (e.g., `rq3_v6_ds_2_retry`) is acceptable and must be documented. | `current_phase.txt`, `controller_lan*.log` |
| C2 | Within-mode consistency | M1–M7 | n=3 replicates per mode show consistent spawn counts and latency profiles (qualitative: no single replicate is an outlier by >2× the other two) | All artifacts |
| C3 | Baseline FP separation | M1, G1 | At least one pairwise comparison shows distinguishable FP spawn counts between modes (non-overlapping SEM bars) | `elasticity_events.csv` |
| C4 | Stress detection separation | M2, M3, G2, G3 | At least one pairwise comparison shows distinguishable spawn counts OR TTFS distributions | `elasticity_events.csv` |
| C5 | Missed detection asymmetry | M4 | At least one mode misses ≥1 detection that another mode catches, OR all modes detect equally (valid bounding result) | `elasticity_events.csv` + `per_node_stats.csv` |
| C6 | Service quality separation | M5, G4 | At least one pairwise comparison shows distinguishable per-phase latency (non-overlapping SEM bars in at least one phase) | `client_requests.csv` |
| C7 | Throughput-waste relationship | M7, G7 | If spawn counts differ between modes, throughput either differs (under-detection) or does not (waste). Both outcomes are informative — criterion passes if the relationship is measurable. | `client_requests.csv` |
| C8 | Scaling prerequisite | rq3_v2.md §3.6 | Pre-scale→post-scale improvement in CPU and latency confirmed for degradation_score mode at G0-v6 resource configuration (≥15pp CPU drop, latency reduction visible) | `per_node_stats.csv` || C9 | Efficiency separation | M8, G7b, G9 | At least one pairwise comparison shows distinguishable resource-time product between modes | `elasticity_events.csv` + `container_events.csv` |
| C10 | Cross-tier contamination | M9, G11 | cpu_only shows measurably higher cross-tier contamination than degradation_score | `elasticity_events.csv` |
| C11 | Score correlation | M10 | degradation_score shows r > 0.4 between CPU and latency components during stress phases | `policy_state.csv` |
---

## 9. Checkpoints (In-Run — Runner May Observe, Not Act)

| # | When | What to check | Question |
|---|---|---|---|
| CP1 | After `baseline` phase (~60 s) | `grep -c 'Traceback' controller_lan1.log controller_lan2.log` | Zero tracebacks? If not, abort run (retry per C1 policy). |
| CP2 | Mid `storage_storm` (~180 s) | `docker ps -q \| wc -l` shows container count rising | Are spawns occurring? If 0 spawns by mid-storage_storm, note it — any outcome is informative (§2). |
| CP3 | After `compute_spike` (~18 min) | `grep -c 'scale-up.*triggered' controller_lan*.log` | Spawn counts in expected ballpark? Post-calibration expectations: DS compute ~5 (C-W20 anchor), DS storage ~18 (C-W20 anchor); CO compute 13–19, CO storage 22–24; LO compute ~3, LO storage 15–17. **Note**: Both DS compute and DS storage are anchored to n=1 at calibrated weights — true ranges unknown. >3× deviations from these anchors flag for analyst. |
| CP4 | End of run | Traffic generator exits (log shows completion). `grep -c 'Traceback' controller_lan*.log` still zero. | Run completed normally? |
| CP5 | Before reboot | All 12 standard artifacts present in run folder | Post-processing scripts ran? See §11.1. |

---

## 10. Validity Threats & Limitations

| # | Threat | Mitigation |
|---|---|---|
| V1 | **Single workload family** — content-discovery only. Results may not generalize. | Scope limitation. The thesis evaluates one representative stateful edge service. |
| V2 | **n=3 replicates** — SEM bars with n=3 are wide. Small-N limits statistical power. | SEM + scatter dots show per-replicate spread. Qualitative consistency check (C2) rather than formal t-tests. |
| V3 | **Mean-only latency signal** — excludes p95 from trigger input. | Justified (timeout-censored p95 contamination). Documented in `rq3_setup_v2.md` §7.1. |
| V4 | **latency_only variance** — calibration showed 350% D3 score spread (0.024 vs 0.108). This mode may be sensitive to run-to-run workload alignment. | n=3 provides a third replicate to narrow the estimate. Flagged in analysis. |
| V5 | **Storage CPU weight at n=1** — 0.20 calibrated from one complete run (C-W20, 18 storage spawns) + one partial (C-W20_R, stalled). True mean uncertain. DS compute spawn count also at n=1 (C-W20, 5 spawns). | The n=3 degradation_score replicates provide the first robust estimate of both DS compute and DS storage spawn counts at 0.20/0.80. If true means are outside expected ranges, update thesis narrative. |
| V6 | **No scale-down analysis** — evaluates detection and service quality, not scale-down differences. | Deferred. Scale-down parameters held constant. |
| V7 | **Weight sensitivity unexplored** — only three points (0/0.4/1.0 CPU, 0/0.6/1.0 latency). | Logical extremes + system default. Weight sweeps deferred. |
| V8 | **Resource env vars via sudo** — `STORAGE_CPUS`, `EDGE_CPUS`, `WAN_RTT_MS`, `RANDOM_SEED` must be environment variables, not Make variables. Launch command places them after `sudo -n` as `VAR=val`. | Smoke test (§6.0) verifies correct resource limits via `docker inspect` and `--random-seed` in traffic log. |

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
| Local run logs | `docs/operation/testing/experiment/rq3_evaluation/v6/logs/rq3_v6_<LABEL>.log` | Tee'd ssh output — launch timestamp, errors, exit code |
| Smoke-test log | `docs/operation/testing/experiment/rq3_evaluation/v6/logs/rq3_v6_smoke.log` | Pre-flight verification record |
| Run folders | `docs/operation/testing/experiment/rq3_evaluation/v6/metrics/<run_folder>/` | Copied from cloud-vm after each run |
| Analysis outputs | `docs/operation/testing/experiment/rq3_evaluation/v6/analysis/` | 16 graphs (G1–G8 + G1b + G5b + G7b + G9–G12) + `rq3_eval_v6_findings.md` |

### 11.3 Post-Evaluation

After all 9 runs are copied locally, the **Edge Experiment Analyzer** agent
produces:

1. **16 graphs** via `campaign_analysis.py` per `.github/skills/rq3-cross-mode-comparison/SKILL.md` (update v5 → v6 paths, add G7b–G12), with n=3 per mode error bars
2. **`rq3_eval_v6_findings.md`** — structured findings against C1–C8, per-mode summaries, thesis narrative alignment
3. **Cross-RQ comparison** — M2, M5, M7 values against RQ1 and RQ2 baselines for the detection→delivery→action chain narrative

---

## References

- [RQ3 v6 — Trigger Composition Characterization](../../../../research_questions/rq3/rq3_v6.md) — measurement framework, M1–M7, G1–G8, C1–C8
- [RQ3 v6 — Experiment Setup Declaration](../../../../research_questions/rq3/rq3_setup_v6.md) — definitive parameter reference
- [RQ3 v6 — Theory Predictions](../../../../research_questions/rq3/rq3_theory_prediction_v6.md) — formalised predictions
- [Divergence Calibration Results](../v5/calibration_results_v2.md) — G0-v6 threshold confirmation, storage CPU weight probe (0.20)
- [Divergence Calibration Plan](../v5/calibration_plan.md) — superseded by results
- [RQ3 Cross-Mode Comparison Skill](../../../../.github/skills/rq3-cross-mode-comparison/SKILL.md) — graph generation workflow (update v5→v6 paths)
- [Testing Overview](../../testing_overview.md) — standard artifact contract, golden config
- [RQ3 env override — degradation_score](../../../../source/scripts/testing/controller_env_overrides/rq3_v2_degradation_score.env)
- [RQ3 env override — cpu_only](../../../../source/scripts/testing/controller_env_overrides/rq3_v2_cpu_only.env)
- [RQ3 env override — latency_only](../../../../source/scripts/testing/controller_env_overrides/rq3_v2_latency_only.env)
- [Phases file](../../../../source/scripts/testing/phases_override/phases_rq1_7phase.json) — 7-phase workload with `compute_spike`
