# Experiment Plan v2 — RQ2 Routing-Awareness Coordination Gap (Rerun)

**Status**: Designed · **Date**: 2026-07-19
**Replaces**: Original RQ2 run (2026-07-06) — invalidated by aggressive compute scoring
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

**This is a rerun.** The original RQ2 campaign (2026-07-06) ran with a
corrected-but-still-aggressive compute scoring function (SCALEUP_CPU_FLOOR=3,
SCALEUP_CPU_SPAN=10 default, SCALEUP_T_PROC_FLOOR=15), producing more spawn
events than intended and distorting traffic volumes, latency magnitudes, and
within-mode variance. The ordinal findings (lifecycle fastest TTFT, slowstart
best latency) are mechanistically sound but must be re-measured under the
fully corrected scoring (SCALEUP_CPU_FLOOR=10, SCALEUP_CPU_SPAN=40,
SCALEUP_T_PROC_FLOOR=25, SCALEUP_W_CPU=0.60, SCALEUP_W_T_PROC=0.40).

---

## 2. Hypothesis / Expected Outcome

### 2.1 Awareness Timing (coordination gap)

| Metric | Expected ranking | Mechanism |
|---|---|---|
| **TTFT** | lifecycle < host < slowstart | Warm lease at t=0; round-robin counter-dependent; invisible until discovery |
| **Initial load share** | lifecycle > slowstart > host | Priority routing; graduated ramp; round-robin ~1/N fair share |
| **Coordination-gap penalty** | TTFT(slowstart) - TTFT(lifecycle) >= 20 s | Extra telemetry window a separated LB waits |

### 2.2 Readiness Timing

| Mode | Traffic starts | Backend warm | Mismatch | Expected non-stress p50 |
|---|---|---|---|---|
| host | t~0 s | t~5-10 s | 5-10 s | Elevated (>>7 ms) |
| slowstart | t~10 s | t~5-10 s | ~0 s | Lowest (~7 ms) |
| lifecycle | t~0 s | t~2-3 s | ~2 s | Near slowstart (~7 ms) |

### 2.3 Service Quality

- **Non-stress phases (baseline, cooldown, demand_drop)**: host p50 elevated
  vs slowstart/lifecycle. Slowstart and lifecycle indistinguishable.
- **Stress phases (storage_storm, compute_spike)**: all modes converge
  (MongoDB I/O dominates); p50 within 2x of each other per phase.
- **p95 latency**: all modes within 15% of each other, per phase.
- **Failure rate**: <= 0.1% across all modes (30 s client timeout ceiling).

---

## 3. RQ Linkage

| RQ element | This experiment |
|---|---|
| Independent variable | BACKEND_SELECTION_POLICY (host / slowstart / lifecycle) |
| Dependent variables | TTFT, initial load share, per-phase p50/p95/p99, readiness mismatch |
| Held constant | Workload, fully corrected compute and storage scoring, push telemetry, topology, WSM weights |

---

## 4. Independent Variable & Held-Constant Set

### Independent Variable

| Mode | When routing becomes aware | Mechanism | Encodes |
|---|---|---|---|
| topology_host | Immediately — unknown stats -> 0.0, round-robin distributes evenly | No ramp, no warm lease, no readiness concept | No integration between provisioner and LB |
| topology_slowstart | At discovery (first telemetry, 0-10 s post-spawn) | Invisible (penalty 1.0) until discovery, then graduated ramp | Separated architecture — Wang et al. spawn-to-LB-inclusion delay |
| topology_lifecycle | At spawn time (atomic with pool registration) | Warm lease with bounded priority window (45 s) | Unified architecture — zero coordination gap |

### Held Constant

| Parameter | Value | Where set |
|---|---|---|
| Workload | phases_rq2.json (9-phase, two-cycle, rate=4.0, all-local) | PHASES_CONFIG |
| CLIENTS | 32 (64 total across both LANs) | make var |
| CONTENT_ITEMS | 6000 | make var |
| RANDOM_SEED | 42 | make var |
| STORAGE_CPUS | 0.10 | make var |
| EDGE_CPUS | 0.30 | make var |
| WAN_RTT_MS | 50 | make var |
| VIP_HARD_TIMEOUT | 60 s | env override |
| **Compute scoring** (corrected) | SCALEUP_CPU_FLOOR=10, SCALEUP_CPU_SPAN=40, SCALEUP_T_PROC_FLOOR=25, SCALEUP_W_CPU=0.60, SCALEUP_W_T_PROC=0.40, SCALEUP_T_PROC_SPAN=80 (default) | env override |
| **Storage scoring** (corrected, latency-only) | SCALEUP_W_STORAGE_CPU=0, SCALEUP_W_T_DB=1.0, SCALEUP_STORAGE_BASE_THRESHOLD=0.18, SCALEUP_STORAGE_CPU_FLOOR=1.5, SCALEUP_STORAGE_CPU_SPAN=5, SCALEUP_T_DB_FLOOR=60, SCALEUP_T_DB_SPAN=250 | env override |
| **Scaling caps** | MAX_DYNAMIC_COMPUTE=6, MAX_DYNAMIC_STORAGE=5 | env override |
| **Cooldowns** | SCALEDOWN_COMPUTE_COOLDOWN_S=180, SCALE_DOWN_COMPUTE_REQUIRED=9, SCALEUP_STORAGE_COOLDOWN_S=120 | env override |
| Telemetry | Push (ZMQ, window-close) | Controller default |
| SS_ENABLED | 0 | env override |
| WSM weights | Defaults (identical across modes) | osken-controller.env |
| Warm-lease TTLs | Server 45 s, Storage 30 s | scaling_config.py defaults |
| cross_region_ratio | 0.0 (all phases) | phases_rq2.json |

---

## 5. Prerequisite: Fix the RQ2 Env Override Files

**This section is the single most important step in the entire experiment.**
The three RQ2 env override files currently contain aggressive compute scoring
values from the original run. They must be updated **before any run is
launched**. There is a pre-flight checkpoint (CP-1) that gatekeeps this.

### 5.1 Exact changes required

For ALL THREE files (`rq2_topology_host.env`, `rq2_topology_slowstart.env`,
`rq2_topology_lifecycle.env`):

| Line | Action |
|---|---|
| `SCALEUP_CPU_FLOOR=3` | **Change to `SCALEUP_CPU_FLOOR=10`** |
| `SCALEUP_T_PROC_FLOOR=15` | **Change to `SCALEUP_T_PROC_FLOOR=25`** |
| (missing) | **Add `SCALEUP_CPU_SPAN=40`** |
| (missing) | **Add `SCALEUP_W_CPU=0.60`** |
| (missing) | **Add `SCALEUP_W_T_PROC=0.40`** |
| `SCALEUP_W_STORAGE_CPU=0.60` | **Change to `SCALEUP_W_STORAGE_CPU=0`** |
| `SCALEUP_W_T_DB=0.40` | **Change to `SCALEUP_W_T_DB=1.0`** |
| `SCALEUP_STORAGE_BASE_THRESHOLD=0.12` | **Change to `SCALEUP_STORAGE_BASE_THRESHOLD=0.18`** |

**Do NOT change any other lines.** The scaling caps, cooldowns,
BACKEND_SELECTION_POLICY, and SS_ENABLED=0 must remain as-is.

### 5.2 Verification command (run before CP-1)

```bash
for f in rq2_topology_host.env rq2_topology_slowstart.env rq2_topology_lifecycle.env; do
  echo "=== $f ==="
  grep -E "SCALEUP_CPU_FLOOR|SCALEUP_CPU_SPAN|SCALEUP_T_PROC_FLOOR|SCALEUP_W_CPU|SCALEUP_W_T_PROC|SCALEUP_W_STORAGE_CPU|SCALEUP_W_T_DB|SCALEUP_STORAGE_BASE_THRESHOLD" \
    "testing/controller_env_overrides/$f"
done
```

Expected output for each file:
```
SCALEUP_CPU_FLOOR=10
SCALEUP_CPU_SPAN=40
SCALEUP_T_PROC_FLOOR=25
SCALEUP_W_CPU=0.60
SCALEUP_W_T_PROC=0.40
SCALEUP_W_STORAGE_CPU=0
SCALEUP_W_T_DB=1.0
SCALEUP_STORAGE_BASE_THRESHOLD=0.18
```

If any file differs, **do not proceed**. Fix the file and re-verify.

---

## 6. Run Matrix

| # | Label | Env Override | Policy |
|---|---|---|---|
| 1 | rq2_v2_th_1 | rq2_topology_host.env | topology_host |
| 2 | rq2_v2_th_2 | rq2_topology_host.env | topology_host |
| 3 | rq2_v2_th_3 | rq2_topology_host.env | topology_host |
| 4 | rq2_v2_ss_1 | rq2_topology_slowstart.env | topology_slowstart |
| 5 | rq2_v2_ss_2 | rq2_topology_slowstart.env | topology_slowstart |
| 6 | rq2_v2_ss_3 | rq2_topology_slowstart.env | topology_slowstart |
| 7 | rq2_v2_tl_1 | rq2_topology_lifecycle.env | topology_lifecycle |
| 8 | rq2_v2_tl_2 | rq2_topology_lifecycle.env | topology_lifecycle |
| 9 | rq2_v2_tl_3 | rq2_topology_lifecycle.env | topology_lifecycle |

**Total**: 9 runs (3 modes x 3 replicates). `v2` prefix distinguishes from
original `rq2_th_1` etc. labels.

**Run order**: Group by mode — all TH, then all SS, then all TL.
Between every run: cleanup + reboot (see §8).

---

## 7. Run Configuration

### topology_host (Runs 1-3)

```bash
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/rq2_topology_host.env \
  RUN_LABEL=rq2_v2_th_1 \
  PHASES_CONFIG=testing/phases_override/phases_rq2.json \
  WAN_RTT_MS=50 CLIENTS=32 CONTENT_ITEMS=6000 EDGE_CPUS=0.30 STORAGE_CPUS=0.10 RANDOM_SEED=42 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
```

Repeat for `rq2_v2_th_2`, `rq2_v2_th_3`.

### topology_slowstart (Runs 4-6)

```bash
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/rq2_topology_slowstart.env \
  RUN_LABEL=rq2_v2_ss_1 \
  PHASES_CONFIG=testing/phases_override/phases_rq2.json \
  WAN_RTT_MS=50 CLIENTS=32 CONTENT_ITEMS=6000 EDGE_CPUS=0.30 STORAGE_CPUS=0.10 RANDOM_SEED=42 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
```

Repeat for `rq2_v2_ss_2`, `rq2_v2_ss_3`.

### topology_lifecycle (Runs 7-9)

```bash
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/rq2_topology_lifecycle.env \
  RUN_LABEL=rq2_v2_tl_1 \
  PHASES_CONFIG=testing/phases_override/phases_rq2.json \
  WAN_RTT_MS=50 CLIENTS=32 CONTENT_ITEMS=6000 EDGE_CPUS=0.30 STORAGE_CPUS=0.10 RANDOM_SEED=42 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
```

Repeat for `rq2_v2_tl_2`, `rq2_v2_tl_3`.

- All runs use `phases_rq2.json` (9-phase, two-cycle, rate=4.0, all-local).
- `--fault-plan`: omitted.
- `SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1`: suppress duplicate steps
  inside `run_experiment.sh`; `create_clients` and `setup_test_data` Makefile
  targets still execute.
- Images: no rebuild required.

### Phase Table

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
| 9 | demand_drop | 300 s | 1.0 | Final drain (extended to observe full scale-down) |

Total: 1740 s (29 min).

---

## 8. Between-Run Protocol

Apply **between every run** (not just between modes):

1. Verify run folder contains all standard artifacts.
2. `source/scripts/cleanup.sh` (~30 s).
3. Reboot cloud VM (~2-3 min).
4. Verify Docker daemon running (`docker info` succeeds).
5. Verify OVS bridges clear (`ovs-vsctl show` shows no stale bridges).
6. Retry steps 4-5 up to 3 times at 30 s intervals. **If still failing after
   3 retries, abort the campaign and investigate.** Do not proceed with
   degraded infrastructure.

---

## 9. Focus & Evidence

### Primary

`controller_lan*.log` + `per_node_stats.csv` -> `cli_rq2_redistribution.py`:

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

- `client_requests.csv` -> per-phase, per-LAN p50/p95/p99
- `container_events.csv` -> verify no `sel_sync_` containers (SS_ENABLED=0)
- `elasticity_events.csv` -> cross-reference spawn events
- `controller_env_snapshot.env` -> verify BACKEND_SELECTION_POLICY,
  SCALEUP_CPU_SPAN=40, SS_ENABLED=0
- `phases_snapshot.json` -> verify correct phases file

---

## 10. Metrics & Success Criteria

### 10.1 Traffic Allocation (Primary)

| ID | Criterion | Operational definition | Expected |
|---|---|---|---|
| C1 | Lifecycle fastest TTFT | Per-mode median TTFT across all compute spawn events, all reps | lifecycle < host < slowstart |
| C2 | Coordination-gap penalty | TTFT_median(slowstart) - TTFT_median(lifecycle) | >= 20 s |
| C3 | Lifecycle highest initial share | Per-mode mean initial share across all compute spawn events | lifecycle > slowstart > host |

### 10.2 Service Quality (Secondary)

| ID | Criterion | Operational definition | Expected |
|---|---|---|---|
| C4 | Host elevated non-stress p50 | Per-mode p50 latency for baseline+cooldown+demand_drop phases, lan1, all reps | host > slowstart AND host > lifecycle; slowstart vs lifecycle within 20% |
| C5 | All modes converge in stress | Per-mode p50 for storage_storm+compute_spike phases, any LAN | max(host,slowstart,lifecycle) / min(host,slowstart,lifecycle) <= 3.0 |
| C6 | p95 within 15% across modes | Per-mode p95 per phase, all LANs | max/max ratio <= 1.15 for each phase independently |
| C7 | Zero failures | HTTP status != 200 count / total requests, per mode | <= 0.1% |

**C5 rationale**: In the original run, stress-phase p50 ranged from ~200ms
to ~600ms across modes — a 3x spread. The <= 3.0 threshold requires the
rerun to not exceed that spread. If corrected scoring produces cleaner
convergence, the ratio will be much lower.

**C6 rationale**: The original run showed p95 ~2500ms across all modes —
well within 15%. This criterion verifies that storage-bound tail latency
remains mode-independent.

### 10.3 Readiness Alignment (Secondary)

| ID | Criterion | Operational definition | Expected |
|---|---|---|---|
| C8 | Host largest mismatch | Per-mode: (first telemetry window end) - (spawn_done_ts). Approximates traffic-arrival-to-warm-up gap via the telemetry window cadence. | host > lifecycle > slowstart |
| C9 | Slowstart near-zero mismatch | slowstart mismatch value | <= 10 s (one telemetry window) |

**C8/C9 measurement procedure**: For each spawn event, `mismatch =
window_end_ts - spawn_done_ts` where `window_end_ts` is the closing boundary
of the first telemetry window in which the backend appears with
`request_count > 0`. This uses the telemetry window cadence (~10 s) as the
natural resolution of the readiness measurement. Small mismatch = traffic
arrived in or near the first window after spawn.

### 10.4 Sanity Checks

| ID | Check | Artifact | Expectation |
|---|---|---|---|
| S1 | Corrected scoring applied | controller_env_snapshot.env | SCALEUP_CPU_SPAN=40, SCALEUP_CPU_FLOOR=10 |
| S2 | Policy applied | controller_env_snapshot.env | BACKEND_SELECTION_POLICY matches label |
| S3 | No Tier 1 | container_events.csv | Zero sel_sync_ containers |
| S4 | Scale-ups occurred | elasticity_events.csv | >= 4 unique spawn_done events per run |
| S5 | Spawn count consistent | elasticity_events.csv | IQR of spawn count within mode < 50% of mode median |

**S4 note on reduced spawn count**: Corrected scoring (higher floor, wider
span) will produce FEWER spawn events than the original run (which had
222-301 events due to aggressive scoring). >= 4 per run yields >= 12 per
mode across 3 reps — sufficient for median/IQR of TTFT and initial share.

---

## 11. Checkpoints

| # | Trigger | Question | Action |
|---|---|---|---|
| **CP-1** | **Before ANY run** | **Do all three RQ2 env override files contain the exact corrected compute scoring values?** Run verification command from §5.2. | **Gate: if any file differs, fix it and re-verify. Do NOT launch any run until CP-1 passes.** |
| CP0 | After rq2_v2_th_1 | >= 4 unique spawn_done events? SCALEUP_CPU_SPAN=40 confirmed in controller_env_snapshot.env? | Gate: if spawns < 4, assess whether CLIENTS=32 needs adjustment. If CPU_SPAN != 40, the prerequisite was missed — abort and fix env files. |
| CP1 | After first mode's 3 reps | TTFT and initial share consistent across replicates? (IQR < 50% of median for both metrics) | If variance extreme: check for external noise. Consider 4th replicate. |
| CP2 | After second mode's 3 reps | Do TTFT and initial share differ visibly between modes? | Qualitative check. Continue to lifecycle regardless — full dataset needed for conclusion. |
| CP3 | End of campaign | Correct scoring + policy confirmed for all 9 controller_env_snapshot.env files? | Cross-check. Flag any deviation. |

---

## 12. Failure Recovery

1. Note failure: run label, elapsed time, last phase, errors from controller logs.
2. Run cleanup + reboot as usual.
3. Retry with identical RUN_LABEL (new timestamp -> new folder). Mark failed
   folder with `FAILED_` prefix or delete.
4. If same run fails twice: skip it. Collect 2 reps for that mode.
5. If a mode loses >1 rep: flag as under-sampled in analysis.
6. If Docker/OVS fails to recover after 3 retries (§8 step 6): **abort
   campaign** and investigate host state.

---

## 13. Validity Threats

| Threat | Mitigation |
|---|---|
| **Corrected scoring reduces spawn count below useful threshold** | S4 gates at >= 4 per run. If all modes fail S4, workload needs recalibration (increase rate_per_client or lower thresholds). Unlikely given original spawned 222+ events under more aggressive scoring. |
| **Ordinal findings may not replicate** | Routing mechanisms (warm lease, discovery gap, round-robin) are independent of scoring. Ordinal ranking should hold. Magnitudes may shift. |
| **Host within-mode variance may persist** | Round-robin tie-breaking is inherently timing-dependent. If variance persists with corrected scoring, confirms it is a genuine property, not a scoring artifact. |
| **SS_ENABLED=0 not representative** | Acknowledged. Tier 1 disabled to isolate routing mechanism. |
| **Three replicates may miss small effects** | Large effects (share, host p50) conclusive at n=3. p95 differences honestly reported as null. |
| **Env override files silently diverge from plan** | CP-1 gatekeeps. Controller_env_snapshot captured per run as audit trail. |
| **WAN_RTT_MS=50 differs from golden config (260ms)** | Intentional: 50ms is the RQ2 canonical WAN setting from the original run, reducing cross-LAN noise. Held constant across all modes. |

---

## 14. Artifact Contract

Standard run-folder layout per `testing_overview.md`. Analysis outputs
generated by `cli_rq2_redistribution.py` per run, then aggregated across
the campaign.

---

## 15. References

- RQ2 definition: `docs/research_questions/rq2.md`
- Original results: `results.md` (for comparison)
- Scoring config: `source/sdn_controller/scaling_config.py`
- VIP routing selection: `source/sdn_controller/_vip_routing/selection.py`
- VIP routing config: `source/sdn_controller/_vip_routing/config.py`
- Analysis CLI: `source/scripts/testing/analysis/rq2/cli_rq2_redistribution.py`
