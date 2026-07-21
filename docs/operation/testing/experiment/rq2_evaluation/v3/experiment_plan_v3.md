# Experiment Plan v3 — RQ2 Routing-Awareness Coordination Gap (v7-Aligned)

**Status**: Designed · **Date**: 2026-07-21
**Replaces**: [v2](../v2/experiment_plan_v2.md) (config not aligned with RQ1 v7 golden baseline)
**Predecessor**: Original RQ2 run (2026-07-06) — invalidated by aggressive compute scoring (CPU_SPAN=10 default)
**Implementation**: [`source/sdn_controller/_vip_routing/selection.py`](../../../../source/sdn_controller/_vip_routing/selection.py)
**Analysis CLI**: [`source/scripts/testing/analysis/rq2/cli_rq2_redistribution.py`](../../../../source/scripts/testing/analysis/rq2/cli_rq2_redistribution.py)

---

## 1. Intent

Evaluate whether the **coordination gap in the routing plane** — the delay
between backend spawn and routing-plane awareness — measurably affects load
redistribution quality. Three policy modes isolate different awareness
timings. The experiment also characterises a second dimension — **backend
readiness** — by measuring the mismatch between traffic arrival and warm-up.

The single question: **Does spawn-time routing awareness produce faster load
redistribution than discovery-time awareness, and does either beat no
integration at all?**

**This is a rerun.** The original RQ2 campaign ran with aggressive compute
scoring (CPU_FLOOR=3, CPU_SPAN=10 default). v3 uses the **RQ1 v7 golden
configuration** — fully corrected scoring (CPU_SPAN=40, CPU_FLOOR=10,
STORAGE_BASE_THRESHOLD=0.35), CLIENTS=96, STORAGE_CPUS=0.08 — ensuring
cross-RQ comparability. The only v7 mechanism NOT carried over is the
`EDGE_MAX_CONCURRENT` semaphore (RQ2 does not need it).

---

## 2. Hypothesis / Expected Outcome

### 2.1 Awareness Timing (coordination gap)

| Metric | Expected ranking | Mechanism |
|---|---|---|
| **TTFT** | lifecycle < host < slowstart | Warm lease at t=0; round-robin counter-dependent; invisible until discovery |
| **Initial load share** | lifecycle > slowstart > host | Priority routing; graduated ramp; round-robin ~1/N fair share |
| **Coordination-gap penalty** | TTFT(slowstart) − TTFT(lifecycle) ≥ 20 s | Extra telemetry window a separated LB waits |

### 2.2 Readiness Timing

| Mode | Traffic starts | Backend warm | Mismatch | Expected non-stress p50 |
|---|---|---|---|---|
| host | t≈0 s | t≈5–10 s | 5–10 s | Elevated (>>7 ms) |
| slowstart | t≈10 s | t≈5–10 s | ~0 s | Lowest (~7 ms) |
| lifecycle | t≈0 s | t≈2–3 s | ~2 s | Near slowstart (~7 ms) |

### 2.3 Service Quality

- **Non-stress phases (baseline, cooldowns, demand_drop)**: host p50 elevated
  vs slowstart/lifecycle. Slowstart and lifecycle indistinguishable.
- **Stress phases (storage_storm, compute_spike)**: all modes converge
  (MongoDB I/O dominates); p50 within 3× of each other per phase.
- **p95 latency**: all modes within 15% of each other, per phase.
- **Failure rate**: ≤ 0.1% across all modes.

---

## 3. RQ Linkage

| RQ element | This experiment |
|---|---|
| Independent variable | `BACKEND_SELECTION_POLICY` (host / slowstart / lifecycle) |
| Dependent variables | TTFT, initial load share, per-phase p50/p95/p99, readiness mismatch |
| Held constant | RQ1 v7 golden config: workload, compute scoring, storage scoring, push telemetry, topology, WSM weights |

Thesis RQ2: *How does the timing of routing-plane awareness relative to
backend spawn affect load redistribution quality during scale-up events?*

---

## 4. Independent Variable & Held-Constant Set

### Independent Variable

| Mode | When routing becomes aware | Mechanism | Encodes |
|---|---|---|---|
| `topology_host` | Immediately — unknown stats → 0.0, round-robin distributes evenly | No ramp, no warm lease, no readiness concept | No integration between provisioner and LB |
| `topology_slowstart` | At discovery (first telemetry, 0–10 s post-spawn) | Invisible (penalty 1.0) until discovery, then graduated ramp | Separated architecture — Wang et al. spawn-to-LB-inclusion delay |
| `topology_lifecycle` | At spawn time (atomic with pool registration) | Warm lease with bounded priority window (45 s) | Unified architecture — zero coordination gap |

### Held Constant

| Parameter | Value | Source |
|---|---|---|
| Workload | `phases_rq2.json` (9-phase, two-cycle, rate=4.0, all-local) | `PHASES_CONFIG` |
| **CLIENTS** | **96** (192 total across both LANs) | RQ1 v7 golden |
| CONTENT_ITEMS | 6000 | make var |
| RANDOM_SEED | 42 | make var |
| **STORAGE_CPUS** | **0.08** | RQ1 v7 golden |
| EDGE_CPUS | 0.30 | default |
| **WAN_RTT_MS** | **185** | RQ1 v7 golden |
| CURL_MAX_TIME | 30 | RQ1 v7 golden |
| **MAX_DYNAMIC_COMPUTE** | **12** | RQ1 v7 golden |
| **MAX_DYNAMIC_STORAGE** | **8** | RQ1 v7 golden |
| **SCALEUP_STORAGE_BASE_THRESHOLD** | **0.35** | RQ1 v7 golden (RQ3-validated) |
| **SCALEUP_COMPUTE_BASE_THRESHOLD** | **0.18** | RQ1 v7 golden |
| Compute scoring | CPU_FLOOR=10, CPU_SPAN=40, T_PROC_FLOOR=25, W_CPU=0.60, W_T_PROC=0.40 | RQ1 v7 golden |
| Storage scoring | W_STORAGE_CPU=0, W_T_DB=1.0, STORAGE_CPU_FLOOR=1.5, STORAGE_CPU_SPAN=5, T_DB_FLOOR=60, T_DB_SPAN=250, STORAGE_REQUIRED=2, STORAGE_WINDOW_SIZE=5 | RQ1 v7 golden |
| Scale-down | COMPUTE_COOLDOWN_S=180, COMPUTE_REQUIRED=9, STORAGE_COOLDOWN_S=120 | RQ1 v7 golden |
| Telemetry | Push (ZMQ, window-close) | Controller default |
| **SS_ENABLED** | **0** | RQ2-specific (no Tier 1 pool contamination) |
| VIP_HARD_TIMEOUT | 60 s | RQ1 v7 golden |
| STORAGE_PERSISTENT_RESERVE_ENABLED | 1 | RQ1 v7 golden |
| WSM weights | Defaults (identical across modes) | `osken-controller.env` |
| Warm-lease TTLs | Server 45 s, Storage 30 s | `scaling_config.py` defaults |
| cross_region_ratio | 0.0 (all phases) | `phases_rq2.json` |

**Bold** = changed from v2 to align with RQ1 v7 golden.

---

## 5. Prerequisites

### 5.1 Env Override Files

Three new env override files must be created for v3. Each mirrors
`current_state_integrated.env` (the RQ1 v7 golden config) with exactly
two overrides:

| Override | Value | Reason |
|---|---|---|
| `SS_ENABLED` | `0` | RQ2 must exclude Tier 1 selective sync |
| `BACKEND_SELECTION_POLICY` | `topology_host` / `topology_slowstart` / `topology_lifecycle` | RQ2 independent variable |

**Files to create** (in `source/scripts/testing/controller_env_overrides/`):

| File | BACKEND_SELECTION_POLICY |
|---|---|
| `rq2_v3_topology_host.env` | `topology_host` |
| `rq2_v3_topology_slowstart.env` | `topology_slowstart` |
| `rq2_v3_topology_lifecycle.env` | `topology_lifecycle` |

Each file must contain the exact golden values:

```
STORAGE_PERSISTENT_RESERVE_ENABLED=1
SS_ENABLED=0
MAX_DYNAMIC_STORAGE=8
MAX_DYNAMIC_COMPUTE=12
SCALEUP_STORAGE_BASE_THRESHOLD=0.35
SCALEUP_COMPUTE_BASE_THRESHOLD=0.18
SCALEUP_CPU_FLOOR=10
SCALEUP_CPU_SPAN=40
SCALEUP_T_PROC_FLOOR=25
SCALEUP_W_CPU=0.60
SCALEUP_W_T_PROC=0.40
SCALEDOWN_COMPUTE_COOLDOWN_S=180
SCALE_DOWN_COMPUTE_REQUIRED=9
SCALEUP_W_STORAGE_CPU=0
SCALEUP_W_T_DB=1.0
SCALEUP_STORAGE_CPU_FLOOR=1.5
SCALEUP_STORAGE_CPU_SPAN=5
SCALEUP_T_DB_FLOOR=60
SCALEUP_T_DB_SPAN=250
SCALEUP_STORAGE_REQUIRED=2
SCALEUP_STORAGE_WINDOW_SIZE=5
SCALEUP_STORAGE_COOLDOWN_S=120
VIP_HARD_TIMEOUT=60
BACKEND_SELECTION_POLICY=<mode>
```

### 5.2 Verification (CP-1 gate)

```bash
for f in rq2_v3_topology_host.env rq2_v3_topology_slowstart.env rq2_v3_topology_lifecycle.env; do
  echo "=== $f ==="
  grep -E "MAX_DYNAMIC|SCALEUP_|SCALEDOWN|SS_ENABLED|BACKEND_SELECTION|VIP_HARD|STORAGE_PERSISTENT" \
    "testing/controller_env_overrides/$f" | sort
done
```

Expected (diff should be empty against golden except for SS_ENABLED=0 and BACKEND_SELECTION_POLICY):

```
BACKEND_SELECTION_POLICY=topology_<mode>
MAX_DYNAMIC_COMPUTE=12
MAX_DYNAMIC_STORAGE=8
SCALEUP_COMPUTE_BASE_THRESHOLD=0.18
SCALEUP_CPU_FLOOR=10
SCALEUP_CPU_SPAN=40
SCALEUP_STORAGE_BASE_THRESHOLD=0.35
SCALEUP_STORAGE_CPU_FLOOR=1.5
SCALEUP_STORAGE_CPU_SPAN=5
SCALEUP_STORAGE_COOLDOWN_S=120
SCALEUP_STORAGE_REQUIRED=2
SCALEUP_STORAGE_WINDOW_SIZE=5
SCALEUP_T_DB_FLOOR=60
SCALEUP_T_DB_SPAN=250
SCALEUP_T_PROC_FLOOR=25
SCALEUP_W_CPU=0.60
SCALEUP_W_STORAGE_CPU=0
SCALEUP_W_T_DB=1.0
SCALEUP_W_T_PROC=0.40
SCALEDOWN_COMPUTE_COOLDOWN_S=180
SCALE_DOWN_COMPUTE_REQUIRED=9
SS_ENABLED=0
STORAGE_PERSISTENT_RESERVE_ENABLED=1
VIP_HARD_TIMEOUT=60
```

**Gate**: if any file differs, do not proceed. Fix and re-verify.

### 5.3 Phases File

`phases_rq2.json` is at `source/scripts/testing/phases_override/phases_rq2.json`.
It is a 9-phase, two-cycle, all-local workload (cross_region_ratio=0.0 for all
phases, rate=4.0 for stress phases). No changes needed — this is the RQ2-tailored
workload and is held constant across all runs.

### 5.4 Images

No Docker image rebuild required. The `EDGE_MAX_CONCURRENT` semaphore from
RQ1 v7 Test B is **not** enabled for RQ2.

---

## 6. Run Matrix

| # | Label | Env Override | Policy |
|---|---|---|---|
| 1 | `rq2_v3_th_1` | `rq2_v3_topology_host.env` | `topology_host` |
| 2 | `rq2_v3_th_2` | `rq2_v3_topology_host.env` | `topology_host` |
| 3 | `rq2_v3_th_3` | `rq2_v3_topology_host.env` | `topology_host` |
| 4 | `rq2_v3_ss_1` | `rq2_v3_topology_slowstart.env` | `topology_slowstart` |
| 5 | `rq2_v3_ss_2` | `rq2_v3_topology_slowstart.env` | `topology_slowstart` |
| 6 | `rq2_v3_ss_3` | `rq2_v3_topology_slowstart.env` | `topology_slowstart` |
| 7 | `rq2_v3_tl_1` | `rq2_v3_topology_lifecycle.env` | `topology_lifecycle` |
| 8 | `rq2_v3_tl_2` | `rq2_v3_topology_lifecycle.env` | `topology_lifecycle` |
| 9 | `rq2_v3_tl_3` | `rq2_v3_topology_lifecycle.env` | `topology_lifecycle` |

**Total**: 9 runs (3 modes × 3 replicates). `v3` prefix distinguishes from
original `rq2_th_1` and v2 `rq2_v2_th_1` labels.

**Run order**: Group by mode — all TH, then all SS, then all TL. Between
every run: cleanup + reboot (see §8).

### Phase Table (`phases_rq2.json`)

| # | Phase | Duration | Rate | Stress |
|---|---|---|---|---|
| 1 | baseline | 60 s | 1.0 | Control |
| 2 | storage_storm | 240 s | 4.0 | Storage |
| 3 | cooldown_1 | 180 s | 1.0 | Drain |
| 4 | compute_spike | 180 s | 4.0 | Compute |
| 5 | cooldown_2 | 180 s | 1.0 | Drain |
| 6 | storage_storm_2 | 240 s | 4.0 | Storage |
| 7 | cooldown_3 | 180 s | 1.0 | Drain |
| 8 | compute_spike_2 | 180 s | 4.0 | Compute |
| 9 | demand_drop | 300 s | 1.0 | Final drain |

Total: 1740 s (**29 min**). All phases: `cross_region_ratio=0.0`.

---

## 7. Run Configuration

### topology_host (Runs 1–3)

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=rq2_v3_th_1 \
  PHASES_CONFIG=testing/phases_override/phases_rq2.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/rq2_v3_topology_host.env \
  WAN_RTT_MS=185 CLIENTS=96 CONTENT_ITEMS=6000 STORAGE_CPUS=0.08 EDGE_CPUS=0.30 \
  CURL_MAX_TIME=30 RANDOM_SEED=42 \
  > /tmp/rq2_v3_th_1.log 2>&1 &"
```

Repeat for `rq2_v3_th_2`, `rq2_v3_th_3`.

### topology_slowstart (Runs 4–6)

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=rq2_v3_ss_1 \
  PHASES_CONFIG=testing/phases_override/phases_rq2.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/rq2_v3_topology_slowstart.env \
  WAN_RTT_MS=185 CLIENTS=96 CONTENT_ITEMS=6000 STORAGE_CPUS=0.08 EDGE_CPUS=0.30 \
  CURL_MAX_TIME=30 RANDOM_SEED=42 \
  > /tmp/rq2_v3_ss_1.log 2>&1 &"
```

Repeat for `rq2_v3_ss_2`, `rq2_v3_ss_3`.

### topology_lifecycle (Runs 7–9)

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=rq2_v3_tl_1 \
  PHASES_CONFIG=testing/phases_override/phases_rq2.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/rq2_v3_topology_lifecycle.env \
  WAN_RTT_MS=185 CLIENTS=96 CONTENT_ITEMS=6000 STORAGE_CPUS=0.08 EDGE_CPUS=0.30 \
  CURL_MAX_TIME=30 RANDOM_SEED=42 \
  > /tmp/rq2_v3_tl_1.log 2>&1 &"
```

Repeat for `rq2_v3_tl_2`, `rq2_v3_tl_3`.

- `--fault-plan`: omitted.
- No `SKIP_CLIENTS`/`SKIP_SEED`/`SKIP_SNAPSHOT` — full setup per run.
- `EDGE_MAX_CONCURRENT`: not set (no concurrency limit).

---

## 8. Between-Run Protocol

Apply **between every run** (not just between modes):

1. Verify run folder contains all standard artifacts.
2. `source/scripts/cleanup.sh` (~30 s).
3. Reboot cloud VM (~2–3 min).
4. Verify Docker daemon running (`docker info` succeeds).
5. Verify OVS bridges clear (`ovs-vsctl show` shows no stale bridges).
6. Retry steps 4–5 up to 3 times at 30 s intervals. **If still failing after
   3 retries, abort the campaign and investigate.** Do not proceed with
   degraded infrastructure.

---

## 9. Focus & Evidence

### Primary

`controller_lan*.log` + `per_node_stats.csv` → `cli_rq2_redistribution.py`:

```bash
python3 -m source.scripts.testing.analysis.rq2.cli_rq2_redistribution \
  <run_folder>
```

Run per-folder after each run completes. Outputs per run:
- `analysis/rq2_redistribution_profile.csv` — per-event, per-window load share
- `analysis/rq2_redistribution_summary.csv` — per-event TTFT, initial share
- `analysis/rq2_redistribution_aggregates.csv` — per-mode aggregate stats

After all 9 runs, aggregate across the campaign with:
```bash
python3 -m source.scripts.testing.analysis.rq2.campaign_analysis \
  <run_folder_1> <run_folder_2> ... <run_folder_9>
```

### Secondary

- `client_requests.csv` → per-phase, per-LAN p50/p95/p99 via `metrics_stats.py`
- `container_events.csv` → verify no `sel_sync_` containers (`SS_ENABLED=0`)
- `elasticity_events.csv` → cross-reference spawn events
- `controller_env_snapshot.env` → verify `BACKEND_SELECTION_POLICY`,
  `SCALEUP_CPU_SPAN=40`, `SS_ENABLED=0`, `MAX_DYNAMIC_COMPUTE=12`
- `phases_snapshot.json` → verify correct phases file

---

## 10. Metrics & Success Criteria

### 10.1 Traffic Allocation (Primary)

| ID | Criterion | Operational definition | Expected |
|---|---|---|---|
| C1 | Lifecycle fastest TTFT | Per-mode median TTFT across all compute spawn events, all reps | lifecycle < host < slowstart |
| C2 | Coordination-gap penalty | TTFT_median(slowstart) − TTFT_median(lifecycle) | ≥ 20 s |
| C3 | Lifecycle highest initial share | Per-mode mean initial share across all compute spawn events | lifecycle > slowstart > host |

### 10.2 Service Quality (Secondary)

| ID | Criterion | Operational definition | Expected |
|---|---|---|---|
| C4 | Host elevated non-stress p50 | Per-mode p50 latency for baseline+cooldowns+demand_drop phases, LAN1, all reps | host > slowstart AND host > lifecycle; slowstart vs lifecycle within 20% |
| C5 | All modes converge in stress | Per-mode p50 for storage_storm+compute_spike phases, any LAN | max(host,slowstart,lifecycle) / min(host,slowstart,lifecycle) ≤ 3.0 |
| C6 | p95 within 15% across modes | Per-mode p95 per phase, all LANs | max/min ratio ≤ 1.15 for each phase independently |
| C7 | Zero failures | HTTP status ≠ 200 count / total requests, per mode | ≤ 0.1% |

### 10.3 Readiness Alignment (Secondary)

| ID | Criterion | Operational definition | Expected |
|---|---|---|---|
| C8 | Host largest mismatch | Per-mode: (first telemetry window end) − (spawn_done_ts) | host > lifecycle > slowstart |
| C9 | Slowstart near-zero mismatch | slowstart mismatch value | ≤ 10 s (one telemetry window) |

Mismatch = `window_end_ts − spawn_done_ts` where `window_end_ts` is the
closing boundary of the first telemetry window in which the backend appears
with `request_count > 0`.

### 10.4 Sanity Checks

| ID | Check | Artifact | Expectation |
|---|---|---|---|
| S1 | Golden scoring applied | `controller_env_snapshot.env` | `SCALEUP_CPU_SPAN=40`, `SCALEUP_CPU_FLOOR=10`, `SCALEUP_STORAGE_BASE_THRESHOLD=0.35`, `MAX_DYNAMIC_COMPUTE=12` |
| S2 | Policy applied | `controller_env_snapshot.env` | `BACKEND_SELECTION_POLICY` matches label |
| S3 | No Tier 1 | `container_events.csv` | Zero `sel_sync_` containers |
| S4 | Scale-ups occurred | `elasticity_events.csv` | ≥ 2 unique `spawn_done` events per run |
| S5 | Spawn count consistent | `elasticity_events.csv` | IQR of spawn count within mode < 50% of mode median |

**S4 note**: At CLIENTS=96 with corrected scoring, spawn counts will be lower
than the original run's 222–301 events (which fired on every minor CPU bump).
≥ 2 per run yields ≥ 6 per mode across 3 reps — sufficient for median/IQR of
TTFT and initial share. The v7 experience (4 spawns/run at rate=2.0
compute_spike) suggests RQ2's rate=4.0 at CLIENTS=96 should produce more.

---

## 11. Checkpoints

| # | Trigger | Question | Action |
|---|---|---|---|
| **CP-1** | Before ANY run | Do all three RQ2 v3 env override files match golden + RQ2 overrides? Run verification from §5.2. | **Gate: if any file differs, fix it and re-verify. Do NOT launch any run until CP-1 passes.** |
| CP0 | After `rq2_v3_th_1` | ≥ 2 unique spawn_done events? `SCALEUP_CPU_SPAN=40` confirmed in `controller_env_snapshot.env`? | Gate: if spawns < 2, assess whether CLIENTS=96 needs adjustment (unlikely). If scoring wrong, abort and fix env files. |
| CP1 | After first mode's 3 reps | TTFT and initial share consistent across replicates? (IQR < 50% of median for both metrics) | If variance extreme: check for external noise. Consider 4th replicate. |
| CP2 | After second mode's 3 reps | Do TTFT and initial share differ visibly between modes? | Qualitative check. Continue to lifecycle regardless. |
| CP3 | End of campaign | Golden scoring + policy confirmed for all 9 `controller_env_snapshot.env` files? | Cross-check. Flag any deviation. |

---

## 12. Failure Recovery

1. Note failure: run label, elapsed time, last phase, errors from controller logs.
2. Run cleanup + reboot as usual.
3. Retry with identical `RUN_LABEL` (new timestamp → new folder). Mark failed
   folder with `FAILED_` prefix or delete.
4. If same run fails twice: skip it. Collect 2 reps for that mode.
5. If a mode loses >1 rep: flag as under-sampled in analysis.
6. If Docker/OVS fails to recover after 3 retries (§8 step 6): **abort
   campaign** and investigate host state.

---

## 13. Validity Threats & Limitations

| Threat | Mitigation |
|---|---|
| **CLIENTS=96 may overwhelm with rate=4.0** | 96 clients × 4.0 rps = 384 req/s per LAN. Original RQ2 at CLIENTS=48 failed LAN2 under broken scoring. With corrected scoring (CPU_SPAN=40), fewer spawns but each spawn is meaningfully driven by real load. If runs fail: reduce CLIENTS to 48 — but document as a deviation from golden. |
| **Corrected scoring reduces spawn count below useful threshold** | S4 gates at ≥ 2 per run. If all modes fail S4, workload needs recalibration. Unlikely given v7 produced 4 spawns at rate=2.0 — RQ2's rate=4.0 should produce more. |
| **Ordinal findings may not replicate** | Routing mechanisms (warm lease, discovery gap, round-robin) are independent of scoring. Ordinal ranking should hold. Magnitudes may shift with CLIENTS=96. |
| **Host within-mode variance** | Round-robin tie-breaking is inherently timing-dependent. If variance persists with corrected scoring, confirms it is a genuine property, not a scoring artifact. |
| **SS_ENABLED=0 not representative of production** | Acknowledged. Tier 1 disabled to isolate routing mechanism. Production would have SS_ENABLED=1, which RQ1 already evaluates. |
| **Three replicates may miss small effects** | Large effects (share, host p50) conclusive at n=3. p95 differences honestly reported as null. |
| **Env override files silently diverge from golden** | CP-1 gatekeeps. `controller_env_snapshot` captured per run as audit trail. |
| **WAN_RTT_MS=185 with all-local traffic** | WAN_RTT affects storage sync between LANs but not request latency (cross_region_ratio=0.0). Held constant — does not confound mode comparisons. |

---

## 14. Artifact Contract

Standard run-folder layout per `testing_overview.md`. Analysis outputs
generated by `cli_rq2_redistribution.py` per run, then aggregated across
the campaign via `campaign_analysis`.

Post-analysis cleanup: remove transient `client_requests.csv` and
`controller_lan*.log` files after the run summary is produced, per the
`metrics-run-summary` skill workflow.

---

## 15. References

- RQ2 definition: [`docs/research_questions/rq2.md`](../../../../research_questions/rq2.md)
- RQ1 v7 plan (golden config source): [`docs/operation/testing/experiment/rq1_thesis_final/v7/experiment_plan_v7.md`](../../rq1_thesis_final/v7/experiment_plan_v7.md)
- Golden env: [`source/scripts/testing/controller_env_overrides/current_state_integrated.env`](../../../../source/scripts/testing/controller_env_overrides/current_state_integrated.env)
- Phases: [`source/scripts/testing/phases_override/phases_rq2.json`](../../../../source/scripts/testing/phases_override/phases_rq2.json)
- VIP routing selection: [`source/sdn_controller/_vip_routing/selection.py`](../../../../source/sdn_controller/_vip_routing/selection.py)
- Original results (invalidated scoring): [`../v1/results.md`](../v1/results.md)
- v2 plan (superseded): [`../v2/experiment_plan_v2.md`](../v2/experiment_plan_v2.md)
