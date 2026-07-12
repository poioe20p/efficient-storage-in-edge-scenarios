# Experiment Plan — RQ2 Routing-Awareness Coordination Gap

**Status**: 📋 Designed · **Date**: 2026-07-05
**Implementation**: [`source/sdn_controller/_vip_routing/selection.py`](../../../../source/sdn_controller/_vip_routing/selection.py) (policy-mode gating, warm leases, slowstart penalty)
**Analysis CLI**: [`source/scripts/testing/analysis/rq2/cli_rq2_redistribution.py`](../../../../source/scripts/testing/analysis/rq2/cli_rq2_redistribution.py)

---

## 1. Intent

Evaluate whether the **coordination gap in the routing plane** — the delay between backend spawn (by the elasticity manager) and routing-plane awareness of the new backend — measurably affects load redistribution quality. Three policy modes isolate different awareness timings, holding scaling, telemetry, infrastructure, and workload constant.

The single question: **Does spawn-time routing awareness (`topology_lifecycle`) produce faster and smoother load redistribution than discovery-time awareness (`topology_slowstart`) or no ramp-up (`topology_host`)?**

---

## 2. Hypothesis / Expected Outcome

If the coordination gap is measurable:

1. **Redistribution time ranking**: `topology_lifecycle` < `topology_host` < `topology_slowstart`.
   - `topology_lifecycle`: warm lease from t=0 → traffic reaches backend in 5–15 s.
   - `topology_host`: cold-start herd (unknown stats → 0.0, wins every WSM round) → traffic reaches backend in 5–10 s but with overshoot (new backend grabs all traffic, potentially overwhelming it).
   - `topology_slowstart`: invisible until discovery (0–10 s) + graduated penalty ramp (30–45 s) → traffic reaches equilibrium in 20–50 s.

2. **Coordination-gap penalty**: `redistribution_time(slowstart) − redistribution_time(lifecycle) ≥ 20 s` — the time the separated-LB model loses waiting for telemetry to discover the backend.

3. **Transition smoothness**: `topology_host` shows higher per-backend load variance during transition windows (thundering herd); `topology_lifecycle` and `topology_slowstart` show controlled, monotonic ramps.

4. **Per-phase latency**: During `storage_storm` and `compute_spike` phases, p95 latency is lowest under `topology_lifecycle` (traffic reaches new backends fastest, relieving overloaded ones). `topology_host` may show latency spikes if cold backends are overwhelmed.

If the coordination gap is **not** measurable (all three modes redistribute equally fast), the finding is that the gap exists on paper but is inconsequential at this scale — still a valid thesis result.

---

## 3. RQ Linkage

**Thesis RQ2** ([`docs/research_questions/rq2.md`](../../../research_questions/rq2.md)):
> How does the timing of routing-plane awareness relative to backend spawn — at spawn time (warm lease, in-process) versus at discovery time (slow-start ramp, simulating a separated LB) versus no ramp-up — affect load redistribution quality during scale-up events in a stateful edge system?

| RQ element | This experiment |
|---|---|
| Independent variable | `BACKEND_SELECTION_POLICY` (topology_host / topology_slowstart / topology_lifecycle) |
| Dependent variable | Redistribution time (spawn_done → equilibrium load share) |
| Held constant | Workload, scaling thresholds, telemetry mode (push), topology, WSM weights, Tier 1 disabled |

Integrates with RQ3: RQ3 provisions backends (scale-up decisions); RQ2 determines how fast those backends receive traffic after provisioning.

---

## 4. Independent Variable & Held-Constant Set

### Independent Variable

`BACKEND_SELECTION_POLICY` with three levels:

| Mode | When routing becomes aware | Mechanism | Encodes |
|---|---|---|---|
| `topology_host` | Immediately (unknown → 0.0, best-case) | No ramp, no warm lease — cold-start WSM herd | HAProxy leastconn, no slow-start |
| `topology_slowstart` | At discovery (first telemetry window, 0–10 s post-spawn) | Invisible (penalty 1.0) until discovery, then linear decay over TTL | Separated LB with coordination delay |
| `topology_lifecycle` | At spawn time (atomic with pool registration) | Warm lease with bounded priority window (30–45 s) | Unified controller, zero coordination gap |

### Held Constant

| Parameter | Value | Rationale |
|---|---|---|
| Workload | `phases_override/phases_rq2.json` | Two-cycle scale-up workout, all-local, rate=4.0 |
| `CLIENTS` | **32** | Calibrated 2026-07-06 via [`calibration_plan.md`](./calibration_plan.md); 32 clients per LAN = **64 total**. topology_host fails at 48 (34% LAN2 herd-overload failure). At 32 all three modes survive ≥97.5%, herd behavior is measurable but not catastrophic. |
| `CONTENT_ITEMS` | 6000 | Canonical dataset cardinality |
| `USERS` | 100 | Canonical |
| `RANDOM_SEED` | **42** | Fixed seed for comparable replicates — identical request sequence across all 9 runs. Without this, run A might randomly draw more writes than run B, confounding mode comparison. |
| `STORAGE_CPUS` | 0.10 | Canonical storage calibration; sets `--cpus` on storage containers via `build_network_1.sh:117` |
| `EDGE_CPUS` | **0.30** (default) | Golden config; sets `--cpus` on edge server containers via `build_network_1.sh` / `build_network_2.sh`. Not passed explicitly — the default `${EDGE_CPUS:-0.30}` matches the golden config. |
| `WAN_RTT_MS` | 50 | Background inter-LAN communication; no client-traffic latency noise |
| `VIP_HARD_TIMEOUT` | 60 s | Golden config |
| Scaling thresholds & cooldowns | `current_state_integrated.env` values (unchanged) | Golden config bundle |
| Telemetry mode | Push (ZMQ, window-close) | RQ1's optimal — eliminates monitoring blind spot |
| `SS_ENABLED` | 0 | No Tier 1 anchors to contaminate VIP pools |
| WSM weights | Defaults in `_vip_routing/config.py` | Identical across modes |
| Warm-lease TTLs | Server 45 s, Storage 30 s (defaults) | Identical across modes; slowstart reuses same TTLs for clean comparison |
| Topology | Two-LAN, containerized services | Standard experiment topology |
| `cross_region_ratio` | 0.0 (all phases) | No cross-region client traffic — clean latency signal |

---

## 5. Run Matrix

| # | Label | Env Override | Policy |
|---|---|---|---|
| 1 | `rq2_th_1` | `rq2_topology_host.env` | topology_host |
| 2 | `rq2_th_2` | `rq2_topology_host.env` | topology_host |
| 3 | `rq2_th_3` | `rq2_topology_host.env` | topology_host |
| 4 | `rq2_ss_1` | `rq2_topology_slowstart.env` | topology_slowstart |
| 5 | `rq2_ss_2` | `rq2_topology_slowstart.env` | topology_slowstart |
| 6 | `rq2_ss_3` | `rq2_topology_slowstart.env` | topology_slowstart |
| 7 | `rq2_tl_1` | `rq2_topology_lifecycle.env` | topology_lifecycle |
| 8 | `rq2_tl_2` | `rq2_topology_lifecycle.env` | topology_lifecycle |
| 9 | `rq2_tl_3` | `rq2_topology_lifecycle.env` | topology_lifecycle |

**Total: 9 runs** (3 modes × 3 replicates). **~29 min/run** + **~5 min between-run overhead** (cleanup + reboot + verification) → **~34 min/run cycle** → **~5 h campaign** (plus initial setup). `RANDOM_SEED=42` ensures identical request sequence across all 9 runs for comparable replicates.

**Run order**: Group by mode — all TH reps, then all SS reps, then all TL reps — so the operator changes the env override file once per mode, not per run. Within a mode, order doesn't matter.

**Expected scale-up events per run** (~12): 2 storage scale-ups per `storage_storm` phase × 2 cycles = 4 storage events; 4 compute scale-ups per `compute_spike` phase × 2 cycles = 8 compute events.

---

## 6. Run Configuration

All runs share the same base invocation; only `OSKEN_ENV_OVERRIDE_FILE` and `RUN_LABEL` change.

### topology_host (Runs 1–3)

```bash
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/rq2_topology_host.env \
  RUN_LABEL=rq2_th_1 \
  PHASES_CONFIG=testing/phases_override/phases_rq2.json \
  WAN_RTT_MS=50 CLIENTS=32 CONTENT_ITEMS=6000 USERS=100 STORAGE_CPUS=0.10 RANDOM_SEED=42 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1

# Repeat with RUN_LABEL=rq2_th_2, rq2_th_3
```

### topology_slowstart (Runs 4–6)

```bash
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/rq2_topology_slowstart.env \
  RUN_LABEL=rq2_ss_1 \
  PHASES_CONFIG=testing/phases_override/phases_rq2.json \
  WAN_RTT_MS=50 CLIENTS=32 CONTENT_ITEMS=6000 USERS=100 STORAGE_CPUS=0.10 RANDOM_SEED=42 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1

# Repeat with RUN_LABEL=rq2_ss_2, rq2_ss_3
```

### topology_lifecycle (Runs 7–9)

```bash
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/rq2_topology_lifecycle.env \
  RUN_LABEL=rq2_tl_1 \
  PHASES_CONFIG=testing/phases_override/phases_rq2.json \
  WAN_RTT_MS=50 CLIENTS=32 CONTENT_ITEMS=6000 USERS=100 STORAGE_CPUS=0.10 RANDOM_SEED=42 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1

# Repeat with RUN_LABEL=rq2_tl_2, rq2_tl_3
```

- `--phases-config`: `testing/phases_override/phases_rq2.json` — 9-phase, two-cycle scale-up workout, all-local, rate=4.0 (see phase table below).
- `--fault-plan`: **omitted** — no synthetic failure injection.
- `--clients-per-lan`: 32 (passed straight through from `CLIENTS=32`; the Makefile does NOT halve it — 32 clients per LAN = **64 total**).
- Controller env: the per-mode override file (e.g. `rq2_topology_host.env`) contains **both** the golden-config scaling values from [`current_state_integrated.env`](../../../../source/scripts/testing/controller_env_overrides/current_state_integrated.env) and the RQ2-specific overrides (`BACKEND_SELECTION_POLICY`, `SS_ENABLED=0`). See the env override files for the full variable list. No separate `OSKEN_ENV_FILE` base is needed — the override is self-contained.
- Images: no rebuild required. Policy gating and warm-lease mechanisms are already deployed in the controller volume mount.
- **`WAN_RTT_MS`, `STORAGE_CPUS`, and `RANDOM_SEED`** are shell environment variables. `WAN_RTT_MS` is consumed by `wan.env` / `inject_wan_latency.sh`. `STORAGE_CPUS` sets `--cpus` on storage containers via `build_network_1.sh:117` and `build_network_2.sh:117`. `RANDOM_SEED` is passed through to `traffic_generator.py` for reproducible request sequences. They are NOT Makefile variables — they must be set on the `make` command line (where `make` passes them through to the shell) or exported in the shell environment before invoking `make`. The values in the launch commands below rely on command-line passthrough.
- **`SKIP_CLIENTS=1`, `SKIP_SEED=1`, `SKIP_SNAPSHOT=1`** only suppress the corresponding steps **inside `run_experiment.sh`**. The Makefile targets `create_clients` and `setup_test_data` (invoked in the same command) always execute regardless of these flags. This is correct — clients and seed data must be recreated after each reboot.

### RQ2 Phase Table

| # | Phase name | Duration | Rate/client | Cross-region | Dominant stress |
|---|---|---|---|---|---|
| 1 | `baseline` | 60 s | 1.0 | 0% | Tier 0 control |
| 2 | `storage_storm` | 240 s | 4.0 | 0% | Storage write/aggregation amplification |
| 3 | `cooldown_1` | 180 s | 1.0 | 0% | Drain and scale-down observation |
| 4 | `compute_spike` | 180 s | 4.0 | 0% | Feed-ranking compute pressure |
| 5 | `cooldown_2` | 180 s | 1.0 | 0% | Drain and scale-down observation |
| 6 | `storage_storm_2` | 240 s | 4.0 | 0% | Second storage cycle |
| 7 | `cooldown_3` | 180 s | 1.0 | 0% | Drain and scale-down observation |
| 8 | `compute_spike_2` | 180 s | 4.0 | 0% | Second compute cycle |
| 9 | `demand_drop` | 300 s | 1.0 | 0% | Final drain to idle |

**Total duration**: 1740 s (29 min). Analysis must aggregate across both cycles — `storage_storm` + `storage_storm_2`, `compute_spike` + `compute_spike_2`.

### Between-Run Protocol

1. After each run completes, verify the run folder contains all 12 standard artifacts (see §12).
2. Run `source/scripts/cleanup.sh` to remove containers, networks, and dangling Docker resources from the previous run (~30 s).
3. Reboot the cloud VM to eliminate memory-accumulation confounds (~2–3 min).
4. After reboot, verify Docker daemon is running (`docker info` succeeds) and OVS bridges are clear (`ovs-vsctl show` shows no stale bridges). Retry up to 3 times at 30 s intervals if Docker is not ready. If Docker fails to start after 3 retries, abort the campaign and investigate.

Apply this protocol between **every** run — not just between modes. A clean slate per run prevents cross-run contamination of container state, OVS flow tables, and kernel memory.

---

## 7. Focus & Evidence

### Primary Evidence

**Controller logs + per_node_stats.csv**: The redistribution curve lives at the intersection of these two artifacts:
- `controller_lan1.log` / `controller_lan2.log` → parsed by `cli_rq2_redistribution.py` to extract `ElasticityEvent` markers (spawn_done timestamps, backend MACs, container roles)
- `per_node_stats.csv` → per-window request counts per backend, used to track load share evolution after spawn

The CLI outputs five analysis files:
- `rq2_redistribution_profile.csv` — per-event, per-window load share evolution
- `rq2_redistribution_summary.csv` — per-event redistribution time, overshoot, plateau share
- `rq2_redistribution_aggregates.csv` — per-mode, per-role (compute/storage) aggregate statistics
- `rq2_cumulative_load.csv` — cumulative traffic share over time per event
- `rq2_transition_quality.csv` — per-backend load variance during transition windows

### Secondary Evidence

- **`client_requests.csv`** — per-phase, per-LAN, per-endpoint p95/p99 latency and failure rate during `storage_storm` and `compute_spike` phases. A mode with faster redistribution should show lower latency during transition windows.
- **`container_events.csv`** — cross-reference spawn timestamps against controller-log events; verify no sel_sync_ containers appear (SS_ENABLED=0).
- **`elasticity_events.csv`** — pre-parsed scale-up/down events; cross-reference against the CLI's own event extraction.
- **`controller_env_snapshot.env`** — verify `BACKEND_SELECTION_POLICY` and `SS_ENABLED=0` took effect.
- **`phases_snapshot.json`** — verify the correct phases file was used.

### Primary vs Secondary

**Primary focus**: `controller_lan*.log` + `per_node_stats.csv` → redistribution curves. This IS the answer.

**Secondary**: `client_requests.csv` → service-quality impact. This contextualizes whether faster redistribution matters to users.

---

## 8. Metrics & Success Criteria

### 8.1 Redistribution Time (Primary)

```
redistribution_time = t_backend_reaches_equilibrium − spawn_done_ts
```

Where equilibrium = per-backend mean load share ±10%, sustained for ≥3 consecutive telemetry windows.

| Criterion | Measurement | Threshold |
|---|---|---|
| **C1 — Lifecycle fastest** | Median redistribution time per mode, compute tier | `lifecycle_median < host_median < slowstart_median` |
| **C2 — Coordination gap** | `slowstart_median − lifecycle_median`, compute tier | ≥ 20 s (the discovery + ramp penalty) |
| **C3 — Storage gap** | `slowstart_median − lifecycle_median`, storage tier | ≥ 15 s (storage TTL is 30 s vs 45 s for compute) |
| **C4 — Host overshoot** | Max single-window load share for new backend, compute tier | `host_max_share > lifecycle_max_share` (herd vs controlled) |

Compute per-mode using all events across the 3 replicates. Report median ± IQR.

### 8.2 Transition Smoothness (Secondary)

| Criterion | Measurement | Threshold |
|---|---|---|
| **C5 — Load variance** | Per-backend request-count coefficient of variation during first 60 s post-spawn | `host_CV > lifecycle_CV` and `host_CV > slowstart_CV` |

### 8.3 Service Quality (Secondary)

| Criterion | Measurement | Threshold |
|---|---|---|
| **C6 — Latency during scale-up phases** | p95 latency, `storage_storm` + `compute_spike` phases, per-mode aggregate | `lifecycle_p95 ≤ host_p95 ≤ slowstart_p95` |
| **C7 — Failure rate** | Overall HTTP failure fraction | ≤ 5% (all-local, no WAN client traffic — should be very low) |

### 8.4 Sanity Checks

| Check | Artifact | Expectation |
|---|---|---|
| **S1 — Policy applied** | `controller_env_snapshot.env` | `BACKEND_SELECTION_POLICY` matches run label |
| **S2 — No Tier 1** | `container_events.csv` | Zero `sel_sync_` containers |
| **S3 — Scale-ups occurred** | `elasticity_events.csv` | ≥ 8 scale-up events per run |
| **S4 — No cross-region traffic** | `client_requests.csv` phase column | No phase shows cross-region latency pattern |

---

## 9. Checkpoints

| # | Trigger | Question | Action |
|---|---|---|---|
| **CP0** | **Before full campaign — after first run (`rq2_th_1`)** | **Did ≥ 8 unique scale-up decisions fire?** Count distinct `spawn_done` events in `elasticity_events.csv` (not `grep -c` log lines — a single scale-up produces dozens of log lines). Calibration C3 at CLIENTS=32 already confirmed ≥8 unique decisions with 998 scale-up log lines. | **Gate: if < 8 unique spawn_done events, do NOT proceed to remaining 8 runs. Check `controller_env_snapshot.env` for correct `SCALEUP_COMPUTE_BASE_THRESHOLD` (should be 0.20). If thresholds not met: lower to 0.15, or increase `rate_per_client` from 4.0 to 6.0 in phases file. Re-run rq2_th_1 and re-check. Calibration data makes failure unlikely — C3 already passed this gate.** |
| CP1 | After first mode's 3 reps | Are redistribution times consistent across replicates (IQR < 50% of median)? | If variance is extreme: check for external noise (host CPU steal, Docker pull in background). Consider adding a 4th replicate. |
| CP2 | After second mode's 3 reps | Do redistribution curves differ visibly between modes so far? | Qualitative check — if topology_host and topology_slowstart look identical, the coordination gap may be too small to measure. Continue to topology_lifecycle regardless; the full dataset is needed for a conclusive answer. |
| CP3 | End of campaign | Does `controller_env_snapshot.env` confirm all 3 modes? | Cross-check `BACKEND_SELECTION_POLICY` and `SS_ENABLED` per run. Also verify golden config scaling values are present (not defaults). |

---

## 10. Failure Recovery

If a run fails mid-experiment (crash, hang, timeout):

1. **Note the failure**: record the run label, elapsed time, last phase active, and any error messages from `controller_lan*.log`.
2. **Run cleanup**: `source/scripts/cleanup.sh` and reboot as usual.
3. **Retry the same run**: re-launch with the identical `RUN_LABEL` (the timestamp will differ, creating a new run folder). Mark the failed run folder with a `FAILED_` prefix or delete it.
4. **If the same run fails twice**: skip it. Collect 2 replicates instead of 3 for that mode. Note the reduction in the analysis.
5. **If a mode loses >1 replicate**: the mode is under-sampled. The analysis agent will flag this and report results with a reduced-confidence caveat.

Do NOT re-run a failed run more than twice — debugging a systemic failure mid-campaign wastes time better spent on the remaining modes.

---

## 11. Validity Threats & Limitations

| Threat | Mitigation |
|---|---|
| **Low event count per mode** | 3 replicates × ~12 events/run = ~36 events/mode. Sufficient for median/IQR comparison. |
| **SS_ENABLED=0 not representative** | Acknowledged. Tier 1 is disabled to prevent pool contamination. RQ2 measures the routing mechanism, not Tier 1 interaction. A follow-up interaction experiment (RQ2 × Tier 1) is possible but not this plan. |
| **All-local workload not representative** | Acknowledged. Cross-region traffic is stripped to eliminate WAN latency as a noise source. The routing mechanism operates identically on local vs cross-region traffic — the WSM cost function is agnostic to request origin. |
| **rate=4.0 matches canonical rate** | Confirmed: `phases_rq2.json` uses rate=4.0 for `storage_storm`, `compute_spike`, and their second-cycle counterparts. RQ2's all-local workload uses the same rate as the canonical phases — no departure. |
| **Run-order effects** | Grouped by mode (all TH → all SS → all TL). Within a mode, order is arbitrary. VM reboot between modes eliminates cross-contamination. |
| **Warm-lease and slowstart share TTL** | Both use the same TTL (45 s server, 30 s storage) but differ in start time (spawn vs discovery). This is by design — it makes the comparison cleaner. |
| **Single workload shape** | Only one application (content-discovery). Results may not generalize to different workload profiles. |

---

## 12. Artifact Contract

### Standard Run Artifacts (per `testing_overview.md`)

| # | Artifact | Used by |
|---|---|---|
| 1 | `client_requests.csv` | §8.3 service-quality metrics |
| 2 | `resource_stats.csv` | Sanity checks |
| 3 | `resource_stats_debug.csv` | Diagnostic (if needed) |
| 4 | `policy_state.csv` | Diagnostic (if needed) |
| 5 | `per_node_stats.csv` | §8.1 redistribution curves (**primary**) |
| 6 | `container_events.csv` | §8.4 sanity checks, event isolation |
| 7 | `elasticity_events.csv` | Cross-reference scale-up events |
| 8 | `controller_lan1.log` | Event extraction for redistribution timing (**primary**) |
| 9 | `controller_lan2.log` | Event extraction for redistribution timing (**primary**) |
| 10 | `controller_env_snapshot.env` | §8.4 policy verification |
| 11 | `phases_snapshot.json` | Phase configuration verification |
| 12 | `service_logs/` | Diagnostic (if needed) |

### Experiment-Specific Analysis Outputs

**CSV data files** — generated by `cli_rq2_redistribution.py` per run, stored in the run folder under `analysis/rq2/`:

| File | Content |
|---|---|
| `rq2_redistribution_profile.csv` | Per-event, per-window load share evolution |
| `rq2_redistribution_summary.csv` | Per-event redistribution time, overshoot, plateau share |
| `rq2_redistribution_aggregates.csv` | Per-mode, per-role aggregate statistics |
| `rq2_cumulative_load.csv` | Cumulative traffic share over time per event |
| `rq2_transition_quality.csv` | Per-backend load variance during transition windows |

**Graph outputs** — generated by the analysis agent from the CSVs above, stored in `docs/operation/testing/experiment/rq2_evaluation/`:

| Graph | Source data | What it shows |
|---|---|---|
| `graph1_redistribution_profile.png` | `rq2_redistribution_profile.csv` (all runs) | Load share vs. time since spawn, per mode, per role |
| `graph2_redistribution_summary.png` | `rq2_redistribution_summary.csv` (all runs) | Per-event redistribution time boxplots, per mode, per role |
| `graph3_transition_quality.png` | `rq2_transition_quality.csv` (all runs) | Per-mode p95 latency and failure rate during transition windows |
| `graph4_cumulative_load.png` | `rq2_cumulative_load.csv` (all runs) | Cumulative load fraction over time, per mode |
| `graph5_coordination_gap.png` | `rq2_redistribution_summary.csv` (all runs) | `slowstart_median − lifecycle_median` redistribution time, per role |

### Cross-Run Aggregation

After all 9 runs complete, run `cli_rq2_redistribution.py` on each run folder to produce per-run CSVs. Then aggregate per-run `rq2_redistribution_aggregates.csv` files into a campaign-level comparison. Generate all 5 graphs from the combined CSV data and store them in this experiment folder (`docs/operation/testing/experiment/rq2_evaluation/`). The analysis agent (`Edge Experiment Analyzer`) is responsible for the aggregation and graph generation steps.

---

## References

- **RQ2 definition**: [`docs/research_questions/rq2.md`](../../../research_questions/rq2.md)
- **Thesis map**: [`tese/miscelineous/system_to_thesis_map_rq_v2.md`](../../../../tese/miscelineous/system_to_thesis_map_rq_v2.md)
- **Backend selection & warm leases**: [`docs/operation/vip_routing/vip_routing_backend_selection_and_warm_leases.md`](../../vip_routing/vip_routing_backend_selection_and_warm_leases.md)
- **VIP routing overview**: [`docs/operation/vip_routing/vip_routing_overview.md`](../../vip_routing/vip_routing_overview.md)
- **Testing overview**: [`docs/operation/testing/testing_overview.md`](../../testing_overview.md)
- **Golden config**: [`docs/operation/testing/golden_config.md`](../../golden_config.md)
- **Analysis CLI**: [`source/scripts/testing/analysis/rq2/cli_rq2_redistribution.py`](../../../../source/scripts/testing/analysis/rq2/cli_rq2_redistribution.py)
- **Policy implementation**: [`source/sdn_controller/_vip_routing/selection.py`](../../../../source/sdn_controller/_vip_routing/selection.py)
- **Phase file**: [`source/scripts/testing/phases_override/phases_rq2.json`](../../../../source/scripts/testing/phases_override/phases_rq2.json)
- **Env overrides**:
  - [`rq2_topology_host.env`](../../../../source/scripts/testing/controller_env_overrides/rq2_topology_host.env)
  - [`rq2_topology_slowstart.env`](../../../../source/scripts/testing/controller_env_overrides/rq2_topology_slowstart.env)
  - [`rq2_topology_lifecycle.env`](../../../../source/scripts/testing/controller_env_overrides/rq2_topology_lifecycle.env)
