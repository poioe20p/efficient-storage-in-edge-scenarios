# Experiment Plan — RQ2 Routing-Awareness Coordination Gap (Rerun)

**Status**: Designed · **Date**: 2026-07-19
**Replaces**: Original RQ2 run (2026-07-06) — invalidated by CPU_SPAN=5 scoring bug
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

**This is a rerun.** The original RQ2 campaign (2026-07-06) ran with the
compute scoring function saturated (SCALEUP_CPU_SPAN=5 vs corrected 40),
causing uncontrolled server spawning that distorted traffic volumes, latency
magnitudes, and within-mode variance. The ordinal findings (lifecycle fastest
TTFT, slowstart best latency) are mechanistically sound but must be
re-measured under corrected scoring.

---

## 2. Hypothesis / Expected Outcome

### 2.1 Awareness Timing (coordination gap)

| Metric | Expected ranking | Mechanism |
|---|---|---|
| **TTFT** | lifecycle < host < slowstart | Warm lease at t=0; round-robin counter-dependent; invisible until discovery |
| **Initial load share** | lifecycle > slowstart > host | Priority routing; graduated ramp; round-robin ~1/N fair share |
| **Coordination-gap penalty** | ≥ 20 s TTFT(slowstart − lifecycle) | Extra telemetry window a separated LB waits |

### 2.2 Readiness Timing

| Mode | Traffic starts | Backend warm | Mismatch | Expected non-stress p50 |
|---|---|---|---|---|
| host | t≈0 s | t≈5–10 s | 5–10 s | Elevated |
| slowstart | t≈10 s | t≈5–10 s | ~0 s | Best |
| lifecycle | t≈0 s | t≈2–3 s | ~2 s | Close to slowstart |

### 2.3 Service Quality

- Non-stress phases: host p50 elevated vs slowstart/lifecycle
- Stress phases: all modes converge (MongoDB I/O dominates)
- p95: indistinguishable across modes (storage-bound)
- Failure rate: 0% at CLIENTS=32

### 2.4 Expected vs Original Run

| Original finding | Expected after CPU_SPAN fix |
|---|---|
| Host TTFT range 0–251 s | Narrower — saturated spawning amplified variance |
| Host initial share ~30% | Similar — 1/N is mechanically determined |
| Slowstart 71s, Lifecycle 40s TTFT | Ordinal preserved; magnitudes may shift |
| Host p50 200ms vs 7ms non-stress | Direction preserved; magnitudes recalibrated |
| All p95 indistinguishable | Confirmed — storage-bound |

---

## 3. RQ Linkage

| RQ element | This experiment |
|---|---|
| Independent variable | BACKEND_SELECTION_POLICY (host / slowstart / lifecycle) |
| Dependent variables | TTFT, initial load share, per-phase p50/p95/p99, readiness mismatch |
| Held constant | Workload, corrected scoring, push telemetry, topology, WSM weights |

---

## 4. Independent Variable & Held-Constant Set

### Independent Variable

| Mode | When routing becomes aware | Mechanism | Encodes |
|---|---|---|---|
| topology_host | Immediately — unknown stats → 0.0, round-robin distributes evenly | No ramp, no warm lease, no readiness concept | No integration between provisioner and LB |
| topology_slowstart | At discovery (first telemetry, 0–10 s post-spawn) | Invisible (penalty 1.0) until discovery, then graduated ramp | Separated architecture — Wang et al. spawn-to-LB-inclusion delay |
| topology_lifecycle | At spawn time (atomic with pool registration) | Warm lease with bounded priority window (45 s) | Unified architecture — zero coordination gap |

### Held Constant

| Parameter | Value |
|---|---|
| Workload | phases_rq2.json (9-phase, two-cycle, rate=4.0, all-local) |
| CLIENTS | 32 (64 total) |
| CONTENT_ITEMS | 6000 |
| RANDOM_SEED | 42 |
| STORAGE_CPUS | 0.10 |
| EDGE_CPUS | 0.30 |
| WAN_RTT_MS | 50 |
| VIP_HARD_TIMEOUT | 60 s |
| Scoring thresholds | current_state_integrated.env (SCALEUP_CPU_SPAN=40 — **corrected**) |
| Telemetry | Push (ZMQ, window-close) |
| SS_ENABLED | 0 |
| WSM weights | Defaults (identical across modes) |
| Warm-lease TTLs | Server 45 s, Storage 30 s |
| cross_region_ratio | 0.0 (all phases) |

**Critical**: SCALEUP_CPU_SPAN=40 prevents the scoring saturation that invalidated the original run.

---

## 5. Run Matrix

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

Total: 9 runs. Run labels use v2 prefix. Group by mode. Between every run: cleanup + reboot.

**Prerequisite**: Update all three RQ2 env override files with corrected scoring values from current_state_integrated.env (SCALEUP_CPU_SPAN=40, SCALEUP_CPU_FLOOR=10, SCALEUP_T_PROC_FLOOR=25, SCALEUP_W_CPU=0.60, SCALEUP_W_T_PROC=0.40).

---

## 6. Run Configuration

### topology_host (Runs 1–3)

```bash
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/rq2_topology_host.env \
  RUN_LABEL=rq2_v2_th_1 \
  PHASES_CONFIG=testing/phases_override/phases_rq2.json \
  WAN_RTT_MS=50 CLIENTS=32 CONTENT_ITEMS=6000 STORAGE_CPUS=0.10 RANDOM_SEED=42 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
```

Repeat for rq2_v2_th_2, rq2_v2_th_3.

### topology_slowstart (Runs 4–6)

```bash
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/rq2_topology_slowstart.env \
  RUN_LABEL=rq2_v2_ss_1 \
  PHASES_CONFIG=testing/phases_override/phases_rq2.json \
  WAN_RTT_MS=50 CLIENTS=32 CONTENT_ITEMS=6000 STORAGE_CPUS=0.10 RANDOM_SEED=42 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
```

Repeat for rq2_v2_ss_2, rq2_v2_ss_3.

### topology_lifecycle (Runs 7–9)

```bash
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/rq2_topology_lifecycle.env \
  RUN_LABEL=rq2_v2_tl_1 \
  PHASES_CONFIG=testing/phases_override/phases_rq2.json \
  WAN_RTT_MS=50 CLIENTS=32 CONTENT_ITEMS=6000 STORAGE_CPUS=0.10 RANDOM_SEED=42 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
```

Repeat for rq2_v2_tl_2, rq2_v2_tl_3.

- phases: testing/phases_override/phases_rq2.json (9-phase, two-cycle, rate=4.0, all-local)
- fault-plan: omitted
- SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1: suppress duplicate steps inside run_experiment.sh
- Images: no rebuild required

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
| 9 | demand_drop | 300 s | 1.0 | Final drain |

Total: 1740 s (29 min).

### Between-Run Protocol

1. Verify run folder contains all artifacts
2. source/scripts/cleanup.sh (~30 s)
3. Reboot cloud VM (~2–3 min)
4. Verify Docker + OVS ready (retry up to 3x at 30 s intervals)

Apply between every run.

---

## 7. Focus & Evidence

### Primary

controller_lan*.log + per_node_stats.csv → cli_rq2_redistribution.py outputs:
- rq2_redistribution_profile.csv (per-event, per-window load share)
- rq2_redistribution_summary.csv (TTFT, initial share)
- rq2_redistribution_aggregates.csv (per-mode statistics)

### Secondary

- client_requests.csv → per-phase, per-LAN p50/p95/p99 (stress vs non-stress)
- container_events.csv → verify no sel_sync_ containers
- elasticity_events.csv → cross-reference spawn events
- controller_env_snapshot.env → verify BACKEND_SELECTION_POLICY, SCALEUP_CPU_SPAN=40, SS_ENABLED=0

---

## 8. Metrics & Success Criteria

### 8.1 Traffic Allocation (Primary)

| ID | Criterion | Expected |
|---|---|---|
| C1 | Lifecycle fastest TTFT | lifecycle < host < slowstart |
| C2 | Coordination-gap penalty | TTFT(slowstart − lifecycle) ≥ 20 s |
| C3 | Lifecycle highest initial share | lifecycle > slowstart > host |

### 8.2 Service Quality (Secondary)

| ID | Criterion | Expected |
|---|---|---|
| C4 | Host elevated non-stress p50 | host > slowstart ≈ lifecycle |
| C5 | All modes converge in stress | host ≈ slowstart ≈ lifecycle |
| C6 | p95 indistinguishable | All modes within 10% |
| C7 | Zero failures | ≤ 0.1% |

### 8.3 Readiness Alignment (Secondary)

| ID | Criterion | Expected |
|---|---|---|
| C8 | Host largest mismatch | host > lifecycle > slowstart |
| C9 | Slowstart near-zero mismatch | slowstart ≈ 0 s |

### 8.4 Sanity Checks

| ID | Check | Artifact | Expectation |
|---|---|---|---|
| S1 | Corrected scoring | controller_env_snapshot.env | SCALEUP_CPU_SPAN=40 |
| S2 | Policy applied | controller_env_snapshot.env | BACKEND_SELECTION_POLICY matches label |
| S3 | No Tier 1 | container_events.csv | Zero sel_sync_ containers |
| S4 | Scale-ups occurred | elasticity_events.csv | ≥ 6 per run |
| S5 | Controlled spawn count | elasticity_events.csv | IQR < 50% of median within mode |

---

## 9. Checkpoints

| # | Trigger | Question | Action |
|---|---|---|---|
| CP0 | After rq2_v2_th_1 | ≥ 6 unique spawn events + SCALEUP_CPU_SPAN=40 confirmed? | Gate: abort if not. Verify env override. |
| CP1 | After first mode's 3 reps | TTFT/initial share consistent (IQR < 50% median)? | Consider 4th rep if variance extreme. |
| CP2 | After second mode's 3 reps | Modes differ visibly? | Continue to lifecycle regardless. |
| CP3 | End of campaign | Correct scoring + policy confirmed for all 9 runs? | Cross-check env snapshots. |

---

## 10. Validity Threats

| Threat | Mitigation |
|---|---|
| Corrected scoring changes spawn count | Fewer spawns → fewer events. ~24 events/mode still sufficient for median/IQR. S5 verifies consistency. |
| Ordinal findings may not replicate | Mechanisms are routing-level, independent of scoring. Ordinal ranking should hold. |
| Host within-mode variance may persist | Round-robin tie-breaking is inherently timing-dependent. Persistence confirms genuine property, not scoring artifact. |
| SS_ENABLED=0 not representative | Acknowledged. Tier 1 disabled to isolate routing mechanism. |
| Three replicates, small effects | Large effects (share, host p50) conclusive at n=3. p95 differences honestly reported as null. |

---

## 11. Artifact Contract

Standard run-folder layout per testing_overview.md:

```
metrics/<timestamp>_<label>/
  client_requests.csv
  controller_lan1.log / controller_lan2.log
  per_node_stats.csv
  resource_stats.csv / resource_stats_debug.csv
  container_events.csv
  elasticity_events.csv
  node_lifecycle_timings.csv
  phases_snapshot.json
  controller_env_snapshot.env
  current_phase.txt
  service_logs/
  analysis/
    rq2_redistribution_profile.csv
    rq2_redistribution_summary.csv
    rq2_redistribution_aggregates.csv
    rq2_cumulative_load.csv
    rq2_transition_quality.csv
```

Campaign aggregate:
```
metrics/_rq2_v2_campaign_analysis/
  campaign_summary.csv
  graphs/
    graph1_initial_share.png
    graph2_ttft.png
    graph3_latency_percentiles.png
    graph3b_p95_stress_vs_nonstress.png
    graph4_cumulative_load.png
    graph5_coordination_gap.png
```

---

## 12. References

- RQ2 definition: docs/research_questions/rq2.md
- Original results: results.md (for comparison against rerun)
- Scoring config: source/sdn_controller/scaling_config.py
- VIP routing selection: source/sdn_controller/_vip_routing/selection.py
- Analysis CLI: source/scripts/testing/analysis/rq2/cli_rq2_redistribution.py
