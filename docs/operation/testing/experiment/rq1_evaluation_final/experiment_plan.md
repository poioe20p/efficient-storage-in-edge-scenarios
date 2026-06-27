# Experiment Plan — RQ1 Telemetry Delivery Cadence Final Evaluation

**Status**: 🔵 Designed · **Date**: 2026-06-26
**Supersedes**: [`rq1_evaluation`](../rq1_evaluation/experiment_plan.md) v1, v2, v2-replicates

## Intent

Produce a **clean, bug-free, n=3 dataset** for the RQ1 thesis question:

> How does telemetry delivery cadence affect controller decision staleness,
> reaction latency, and transient service quality during demand shifts in a
> stateful edge system?

All prior RQ1 data was collected with one or more known bugs:
- **v1** (2026-06-21): MAC-recycling bug (reserve broken), Tier 1 regression
- **v2** (2026-06-25): Topology resolution regression (Tier 1 unidirectional)

The v2-replicate (2026-06-26, 1 run per mode) was the first bug-free dataset
but the Push replicate was host-degraded (5th consecutive run, 5.04% failure).
This experiment produces **three clean runs per mode** with controlled host
state — the definitive RQ1 dataset for the thesis.

## Hypothesis / Expected Outcome

Same as the original RQ1 plan with one modification based on 12-run evidence:

1. **Information age ~0 for all modes** — robustly confirmed (12/12 runs).
   Not expected to change.

2. **Reaction latency increases with polling interval** — the direction is
   confirmed but the ordering is non-monotonic. Poll-12s is consistently the
   worst case across v1, v2, and replicates. Expected to hold.

3. **Service quality effects are dominated by run-to-run variance** — the
   v2 monotonic degradation pattern (0.14%→0.29%→1.20%→1.70%) was a single-run
   artifact. With n=3 clean runs per mode, we can estimate the true mean and
   variance for the first time.

4. **All four mechanisms exercise** — bidirectional Tier 1, reserve activation,
   compute elasticity, and conntrack routing all confirmed working. Expected
   in all runs.

## RQ Linkage

Primary evidence for RQ1 (Information Acquisition pillar) in thesis Chapter 5.
This dataset supersedes v1, v2, and v2-replicates for any claim that depends
on service quality or mechanism exercise. Information age and overhead claims
are already robust from prior datasets.

## Independent Variable & Held-Constant Set

| Parameter | Value | Source |
|---|---|---|
| Phase file | `testing/phases.json` | 10-phase integrated workload (~25 min) |
| Controller env | `current_state_integrated.env` | Golden config |
| `CLIENTS` | 8 | Standard |
| `DEVICES` | 600 | Standard |
| `NODES` | 100 | Standard |
| Images | Current HEAD | Must include all three fixes |
| `WAN_RTT_MS` | 10 | Default metro |
| `SS_ENABLED` | 1 | Required |
| `STORAGE_PERSISTENT_RESERVE_ENABLED` | 1 | Required |

### Code Fixes (All Verified)

| Fix | File | Verification |
|-----|------|-------------|
| MAC-recycling (reserve) | `node_registry.py` B1+B2, `elasticity.py` B1 | 7 `[reserve] activated` in fix-verification; 5–8 per run in replicates |
| Topology resolution (Tier 1 bidirectional) | `topology.py` `resolve_peer_primary()` two-step | 0 "no primary known" in smoke test + all 4 replicates |
| Name-aware removal guard | `node_registry.py` `sync()` | 1 stale-removal guard trigger in fix-verification |

## Run Matrix

| Mode | `TELEMETRY_SOURCE` | `POLL_INTERVAL_S` | Runs | Labels |
|------|---------------------|-------------------|------|--------|
| **Push** | `zmq` | — | 3 | `rq1_final_push_1`, `_2`, `_3` |
| **Poll-5s** | `poll` | `5` | 3 | `rq1_final_poll5_1`, `_2`, `_3` |
| **Poll-12s** | `poll` | `12` | 3 | `rq1_final_poll12_1`, `_2`, `_3` |
| **Poll-30s** | `poll` | `30` | 3 | `rq1_final_poll30_1`, `_2`, `_3` |

**Existing data reused**: The v2-replicate runs (2026-06-26 `rq1_rep_*`) serve
as run `_1` for each mode. Two additional runs per mode are needed.

**Total new runs**: 8 (2 per mode × 4 modes)

**Run order**: Push_2 → Push_3 → Poll-5s_2 → Poll-5s_3 → Poll-12s_2 →
Poll-12s_3 → Poll-30s_2 → Poll-30s_3

## Host State Protocol

Each mode PAIR (e.g., Push_2 + Push_3) starts with a **clean host**:

```
REBOOT cloud-vm
  → Push_2  (run 1 after reboot — cleanest state)
  → cleanup + wait 120s
  → Push_3  (run 2 after reboot — acceptable state)
REBOOT cloud-vm
  → Poll-5s_2
  → cleanup + wait 120s
  → Poll-5s_3
REBOOT cloud-vm
  ... etc.
```

**Rationale**: The v2-replicate Push (5th consecutive run, 5.04% failure)
demonstrated that host state accumulation degrades the first mode tested
after 4 prior runs. Rebooting between modes ensures each mode pair starts
fresh. Two runs per reboot is acceptable — the second run may show minor
degradation but the evidence across 12 prior runs suggests it's the 4th+
consecutive run where degradation becomes severe.

### Between-run cleanup

```bash
# After each run completes and post-run workflow finishes:
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && make -C source/scripts cleanup 2>&1"
# Wait 120s for kernel/OVS/Docker state to settle
sleep 120
```

### Pre-launch Checklist (Per Mode Pair)

- [ ] Cloud VM rebooted (`ssh cloud-vm "sudo reboot"`; wait for SSH to come back)
- [ ] All three fixes verified on cloud VM
- [ ] `phases.json` is canonical 10-phase workload
- [ ] `current_state_integrated.env` is golden config
- [ ] `sudo -n` working
- [ ] No residual Docker containers or OVS bridges

## Run Configuration

### Push (runs _2, _3)

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=rq1_final_push_2 \
  PHASES_CONFIG=testing/phases.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  CLIENTS=8 DEVICES=600 NODES=100 \
  2>&1"
```

### Poll-5s (runs _2, _3)

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=rq1_final_poll5_2 \
  PHASES_CONFIG=testing/phases.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  CLIENTS=8 DEVICES=600 NODES=100 \
  TELEMETRY_SOURCE=poll POLL_INTERVAL_S=5 \
  2>&1"
```

### Poll-12s (runs _2, _3)

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=rq1_final_poll12_2 \
  PHASES_CONFIG=testing/phases.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  CLIENTS=8 DEVICES=600 NODES=100 \
  TELEMETRY_SOURCE=poll POLL_INTERVAL_S=12 \
  2>&1"
```

### Poll-30s (runs _2, _3)

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=rq1_final_poll30_2 \
  PHASES_CONFIG=testing/phases.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  CLIENTS=8 DEVICES=600 NODES=100 \
  TELEMETRY_SOURCE=poll POLL_INTERVAL_S=30 \
  2>&1"
```

## Metrics & Success Criteria

| # | Criterion | How checked | Expectation |
|---|---|---|---|
| 1 | All 12 runs complete | `current_phase.txt` = `idle` | 12/12 |
| 2 | Information age ~0 | `rq1_staleness_per_phase.csv` max < 0.05s | All modes |
| 3 | Reaction latency | `rq1_reaction_latency.csv` | Push min < Poll-12s worst; Poll-12s consistently worst case |
| 4 | All mechanisms exercise | Controller logs + `resource_stats.csv` | Reserve, Tier 1 (bidirectional), compute, conntrack in all runs |
| 5 | `controller_env_snapshot.env` | File exists, non-empty | All runs |
| 6 | `elasticity_events.csv` | File exists, ≥10 events | All runs |
| 7 | No crashes/tracebacks | Controller logs | 0 across all runs |
| 8 | All RQ1 CLIs produce output | CLI exit codes | All measurement outputs |
| 9 | Cross-run comparison | `cli_simple_compare` | 3-mode comparison PNGs |

**Service quality**: The primary metric is overall failure rate per run.
With n=3 per mode, compute mean and 95% CI for each mode. The thesis can
report whether modes are distinguishable within confidence intervals.

## Post-Run Workflow (Per Run)

Standard: chown → 6 analysis CLIs → delete controller logs → copy back.

After all 12 runs: combined cross-run comparison across all 3 runs per mode.

## Validity Threats

1. **Host state within a mode pair** — the second run in a pair may have
   slightly degraded host state. Mitigation: reboot between modes, cleanup
   between runs. The first run in each pair is the cleanest.

2. **Single-run variance** — with n=3, means are estimable but confidence
   intervals will be wide. This is acknowledged; the thesis should report
   means with CIs, not claim statistical significance.

3. **Run order confound** — Push always runs first (cleanest host). If Push
   consistently shows lower failure rates, it may be host-state, not cadence.
   Mitigation: Push's advantage from clean host state actually works AGAINST
   the thesis claim (Push should be best). If Push shows HIGHER failure than
   Poll modes despite cleanest host, that strengthens the thesis.

## Dataset Integration

| Dataset | Runs | Use for |
|---------|------|---------|
| v1 (2026-06-21) | 4 | Information age, overhead, reaction latency mechanism |
| v2 (2026-06-25) | 4 | Reserve activation baseline, reaction latency |
| v2-replicates (2026-06-26) | 4 | **Run _1 for each mode** in final dataset |
| **Final (this plan)** | **8** | **Complete n=3 per mode** |

After final runs complete, the `rq1_evaluation_final` dataset is the
**primary evidence for service quality and mechanism exercise claims**.
v1 and v2 are retained as supporting evidence for information age,
overhead, and reaction latency mechanism.

---

## Changelog

| Date | Change | Rationale |
|------|--------|-----------|
| 2026-06-26 | Initial plan — definitive RQ1 dataset with n=3 per mode, controlled host state, all fixes applied | Supersedes all prior RQ1 datasets for service quality claims |
