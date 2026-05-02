# Plan: Elasticity Ablation Matrix for Tier 1, Tier 2, and Compute

## Objective

Define a controlled experiment matrix that verifies which mechanisms are
actually improving end-to-end behavior in the current platform:

1. Tier 1 selective sync
2. Tier 2 storage elasticity
3. Compute elasticity
4. The current warm-adjacent data path behavior

The goal is not to change the workload or the analysis toolchain. The goal is
to run the existing standard experiment repeatedly with different controller
configurations, then compare the resulting run folders using the existing
metrics and analysis commands.

---

## Problem Statement

The recent runs show two different regimes:

- One run exhibited severe baseline degradation, multi-second `T_db`, and poor
  client outcomes.
- Two later runs were mostly healthy, showed clean Tier 1 behavior, and did not
  require compute elasticity.

That leaves four unresolved questions:

1. Is Tier 1 the main reason the healthier runs stayed stable?
2. Does Tier 2 storage scale-out actually improve service quality, or does it
   mainly add churn while `T_db_write` remains high?
3. Is compute elasticity materially useful under the standard nine-phase
   workload, or mostly dormant?
4. Can any observed improvement be attributed to the current warm-related
   mechanisms, or only to Tier 1 and general routing behavior?

The most defensible way to answer those questions is a controlled ablation
matrix: keep the same workload, the same WAN profile, and the same experiment
runner, but vary the controller behavior per run.

---

## Approaches Considered

| Approach | Description | Pros | Cons | Effort | Risk | Edge Impact |
| --- | --- | --- | --- | --- | --- | --- |
| A | Single-run deep diagnosis. Reproduce one bad run and inspect logs manually. | Fastest to start; useful for defect hunting | Weak at causal attribution; cannot separate Tier 1 vs Tier 2 vs compute effects | Low | Medium | No runtime changes |
| B | Controlled ablation matrix using the existing experiment harness and env variants | Strong causal comparison; uses current tooling and workflow; directly answers thesis-level questions | Requires multiple runs; warm behavior is only partially isolated in the first pass | Medium | Low | No code-path changes beyond chosen configs |
| C | Add new instrumentation first, then run a smaller matrix | Best attribution quality, especially for warm behavior and activation timing | Slower path to evidence; risks delaying clear conclusions already available via current artifacts | Medium to High | Medium | Adds engineering work before validation |

**Recommended: Approach B.**

The first completed five-run comparison batch is recorded in
[`../testing/elasticity_ablation_batch1_results.md`](../testing/elasticity_ablation_batch1_results.md).
Treat that file as the Batch 1 evidence record if later reruns are added.

Approved Batch 2 rerun note: the next comparison batch keeps the same
9-phase structure but uses a long-cycle extension of the workload timings.
The goal is to give Tier 2 enough time to trigger, reach `SECONDARY`, and
still be observed under active hotspot load, while also leaving
`demand_drop` long enough to expose cooldown-gated scale-down.

The current repository already has the right execution and analysis surfaces:

- [run_experiment.sh](../../../source/scripts/testing/run_experiment.sh)
- [build_network_setup.sh](../../../source/scripts/build_network_setup.sh)
- [osken-controller.env](../../../source/scripts/osken-controller.env)
- [metrics_stats.py](../../../source/scripts/tools/metrics_stats.py)
- [cli_overview.py](../../../source/scripts/testing/analysis/cli_overview.py)
- [cli_scale_down.py](../../../source/scripts/testing/analysis/cli_scale_down.py)
- [cli_tdb_drivers.py](../../../source/scripts/testing/analysis/cli_tdb_drivers.py)
- [cli_cpu_drivers.py](../../../source/scripts/testing/analysis/cli_cpu_drivers.py)

That makes the best next step a comparative run program, not another round of
speculative implementation.

---

## Constraints

- Keep the workload definition unchanged within a batch. Batch 1 uses the
  shorter standard nine-phase run captured in
  [elasticity_ablation_batch1_results.md](../testing/elasticity_ablation_batch1_results.md);
  the approved Batch 2 rerun uses the long-cycle schedule documented in
  [testing_workloads.md](../testing/testing_workloads.md) and
  [testing_overview.md](../testing/testing_overview.md).
- Keep the WAN profile fixed via [wan.env](../../../source/scripts/wan.env)
  during the first comparison batch.
- Change only controller behavior between runs.
- Use the existing logging and metrics artifacts already produced by
  [run_experiment.sh](../../../source/scripts/testing/run_experiment.sh).
- Treat warm-volume snapshot as out of scope for this plan because it is still
  planned rather than implemented in
  [elasticity_overview.md](../elasticy_manager/elasticity_overview.md).

---

## Existing Evidence to Reuse

The current system already emits enough artifacts to support a meaningful
comparison:

- `resource_stats.csv` and `container_events.csv` from
  [run_experiment.sh](../../../source/scripts/testing/run_experiment.sh)
- controller log capture (`controller_lan1.log`, `controller_lan2.log`)
- Tier 1 state and promotion behavior through the existing telemetry and
  coordinator-state path described in
  [selective_sync_overview.md](../selective_sync/selective_sync_overview.md)
- storage promotion on `SECONDARY` through
  [control_events.py](../../../source/sdn_controller/control_events.py)
- node-add timing logs through the elasticity managers and node managers

The storage activation chain can therefore be reconstructed from existing
artifacts:

1. `DataAlert` emitted
2. storage spawn started
3. container created / running
4. `rs_secondary_ready` received or telemetry fallback sees `SECONDARY`
5. storage backend added to the VIP pool
6. subsequent phase windows reflect any latency change

This means the first-pass experiment matrix does not need new instrumentation.

---

## Experiment Matrix

Use the single shared controller env file
[osken-controller.env](../../../source/scripts/osken-controller.env) and edit
it in place between configurations, changing only the listed knobs.

### Configuration Set

| Config ID | Purpose | `SS_ENABLED` | `MAX_DYNAMIC_STORAGE` | `MAX_DYNAMIC_COMPUTE` | What it isolates |
| --- | --- | ---: | ---: | ---: | --- |
| C0 | No-scale control | `0` | `0` | `0` | Baseline service quality without elasticity |
| C1 | Tier 1 only | `1` | `0` | `0` | Selective-sync benefit by itself |
| C2 | Tier 2 only | `0` | `1` | `0` | Full-replica storage scale-out by itself |
| C3 | Tier 1 + Tier 2 | `1` | `1` | `0` | Whether Tier 2 adds value beyond Tier 1 |
| C4 | Full current policy | `1` | `1` | `1` | Whether compute elasticity matters under the standard workload |

### Replication Count

| Config ID | Minimum runs | Rationale |
| --- | ---: | --- |
| C0 | 2 | Establish stable no-scale reference |
| C1 | 2 | Confirm Tier 1 behavior is repeatable |
| C2 | 2 | Confirm whether Tier 2 consistently helps or hurts |
| C3 | 2 | Compare combined behavior against C1 and C2 |
| C4 | 1 | Only needed if compute relevance remains unclear |

If any configuration shows strong run-to-run variance, increase it to 3 runs
before interpreting its effect.

---

## Why This Matrix

This matrix answers the main questions in the smallest useful set of runs:

- `C0 -> C1` isolates the net benefit of Tier 1.
- `C0 -> C2` isolates the net benefit or harm of Tier 2.
- `C1 -> C3` tests whether Tier 2 adds value once Tier 1 already exists.
- `C3 -> C4` tests whether compute elasticity is actually needed.

This is stronger than comparing arbitrary healthy and unhealthy runs, because
the workload and WAN conditions stay fixed while the controller behavior is
systematically varied.

---

## Warm-Feature Interpretation Boundary

This plan intentionally treats the warm question as secondary in the first
batch.

### What can be inferred in this batch

- Whether the current overall system behavior is healthier when Tier 1 is
  enabled
- Whether Tier 2 scale-out improves latency or only adds lifecycle churn
- Whether the current data-path refresh behavior appears compatible with a
  healthy run

### What cannot be proven cleanly in this batch

- A direct causal contribution from bounded VIP warm leases alone
- A direct causal contribution from warm-volume snapshot, because it is not yet
  implemented

If the first matrix still leaves the warm question unresolved, the follow-up
plan should add an explicit warm-ablation toggle and rerun only the Tier 2
relevant configurations.

---

## Execution Procedure

### 1. Update the canonical controller env

Use the single controller env file already consumed by
[build_network_setup.sh](../../../source/scripts/build_network_setup.sh):

- [osken-controller.env](../../../source/scripts/osken-controller.env)

For each configuration in the ablation matrix, edit only the comparison knobs
in that file before rebuilding the environment. Start the rerun batch with
`C0` by setting `SS_ENABLED=0`, `MAX_DYNAMIC_STORAGE=0`, and
`MAX_DYNAMIC_COMPUTE=0`.

### 2. Keep WAN fixed

Use the same WAN profile for the entire batch via
[wan.env](../../../source/scripts/wan.env), preferably the existing `metro`
profile. Do not mix WAN changes with controller ablations in the same batch.

### 3. Build the environment for each configuration

Example shape:

```bash
WAN_ENV_FILE=source/scripts/wan.env \
bash source/scripts/build_network_setup.sh
```

### 4. Run the standard experiment

Use the same runner and workload for every configuration:

```bash
bash source/scripts/testing/run_experiment.sh --run-label c0
```

This produces a labeled run folder under `source/scripts/testing/metrics/`,
using the pattern `<timestamp>_<config-id>` such as `20260501_153012_c0`.
The run folder should also contain a snapshot of the exact
`osken-controller.env` contents used for that execution.

### 5. Generate analysis outputs for each run

Run the same post-processing sequence for every run:

```bash
python source/scripts/tools/metrics_stats.py "source/scripts/testing/metrics/<run_id>" --by-phase --by-lan --by-endpoint
python source/scripts/tools/metrics_stats.py -r "source/scripts/testing/metrics/<run_id>/resource_stats.csv" --by-phase --by-network
python -m source.scripts.testing.analysis.cli_overview --run-dir "source/scripts/testing/metrics/<run_id>"
python -m source.scripts.testing.analysis.cli_scale_down --run-dir "source/scripts/testing/metrics/<run_id>"
python -m source.scripts.testing.analysis.cli_tdb_drivers --run-dir "source/scripts/testing/metrics/<run_id>"
python -m source.scripts.testing.analysis.cli_cpu_drivers --run-dir "source/scripts/testing/metrics/<run_id>"
```

### 6. Record results in a comparison table

For each run, record:

- run id
- configuration id
- whether baseline was healthy
- total request outcomes (`200`, `503`, `0`)
- phase p95 values
- whether Tier 1 promoted
- whether Tier 2 storage scaled out
- whether compute scaled out
- final container cleanliness
- `T_db_write ~ storage_count` coefficient sign and magnitude

---

## Comparison Rubric

Apply the same interpretation rules to every run.

### Primary Questions

1. Is `baseline` already unhealthy?
2. Does Tier 1 reduce failures or hotspot latency relative to no-scale?
3. Does Tier 2 improve hotspot phases, or does it leave `T_db` behavior the
   same or worse?
4. Does the combined policy outperform Tier 1 alone?
5. Does compute elasticity trigger, and if so does it materially improve late
   compute phases?

### Evidence Buckets

#### Traffic health

- phase mean latency
- phase p95 latency
- total failures
- whether failures cluster only late, or are already present in `baseline`

#### Resource shape

- median `time_proc`
- median `time_db`
- `server_count`
- `storage_count`
- whether CPU is actually the bottleneck

#### Elasticity lifecycle

- alert submitted
- container spawned
- node reaches `SECONDARY` or `ACTIVE`
- added to VIP pool or manifest becomes active
- cleanup succeeds or leaves residual containers

#### Regression signal

- sign of `b_storage_count` from
  [cli_tdb_drivers.py](../../../source/scripts/testing/analysis/cli_tdb_drivers.py)
- whether additional storage correlates with lower or higher write latency

---

## Expected Outcomes and Decision Rules

### Outcome A: Tier 1 only is clearly better than no-scale

Interpretation:

- Tier 1 is already delivering practical value for the standard workload.

Action:

- Keep Tier 1 as the preferred cross-region read relief path.

### Outcome B: Tier 2 only is no better than no-scale, or worsens `T_db_write`

Interpretation:

- Tier 2 storage scale-out is not currently solving the main latency problem.

Action:

- Make Tier 2 more conservative before investing in more aggressive storage
  elasticity.

### Outcome C: Tier 1 + Tier 2 is not better than Tier 1 only

Interpretation:

- Tier 2 is adding churn without clear service-quality benefit under the
  standard workload.

Action:

- Prefer Tier 1-first operation and treat Tier 2 as a narrower fallback.

### Outcome D: Full policy is not better than Tier 1 + Tier 2

Interpretation:

- Compute elasticity is mostly dormant or unnecessary under this workload.

Action:

- De-prioritize compute tuning for this experiment line.

### Outcome E: Healthy runs still show unresolved warm ambiguity

Interpretation:

- The first matrix answered the main tier questions but not the warm one.

Action:

- Create a follow-up warm-ablation plan with an explicit warm toggle instead of
  inferring warm behavior from aggregate results.

---

## File Map

### Existing files used by this plan

- [build_network_setup.sh](../../../source/scripts/build_network_setup.sh)
- [osken-controller.env](../../../source/scripts/osken-controller.env)
- [wan.env](../../../source/scripts/wan.env)
- [run_experiment.sh](../../../source/scripts/testing/run_experiment.sh)
- [metrics_stats.py](../../../source/scripts/tools/metrics_stats.py)
- [cli_overview.py](../../../source/scripts/testing/analysis/cli_overview.py)
- [cli_scale_down.py](../../../source/scripts/testing/analysis/cli_scale_down.py)
- [cli_tdb_drivers.py](../../../source/scripts/testing/analysis/cli_tdb_drivers.py)
- [cli_cpu_drivers.py](../../../source/scripts/testing/analysis/cli_cpu_drivers.py)
- [selective_sync_overview.md](../selective_sync/selective_sync_overview.md)

### New artifacts expected when this plan is executed

- multiple run folders under `source/scripts/testing/metrics/`
- a comparison summary document under `docs/operation/testing/`

---

## Dependencies

- The current standard workload and run harness must remain available.
- The analysis package under
  [source/scripts/testing/analysis/](../../../source/scripts/testing/analysis/)
  must remain runnable.
- The controller env file override path in
  [build_network_setup.sh](../../../source/scripts/build_network_setup.sh)
  must be used consistently per configuration.

No new runtime packages are required for the first batch beyond what the
existing analysis commands already use.

---

## Verification

### Per-run verification

For each run, confirm:

1. the configuration id is recorded alongside the run id
2. the run folder contains controller logs, `resource_stats.csv`, and
   `container_events.csv`
3. the analysis commands complete and produce `analysis/summary.md`

### Per-configuration verification

For each configuration family, confirm:

1. at least the minimum run count has been completed
2. the runs are similar enough to support a conclusion, or else the family is
   repeated

### Batch verification

The batch is complete only when it can answer, with direct comparisons:

1. whether Tier 1 improves the standard workload
2. whether Tier 2 improves or worsens DB-heavy behavior
3. whether compute elasticity matters under the standard workload
4. whether the warm question still requires a dedicated ablation follow-up

---

## Documentation Updates After Execution

Once the matrix has been run and interpreted, update:

- [testing_overview.md](../testing/testing_overview.md)
  Add the standard ablation protocol and comparison methodology.
- [selective_sync_overview.md](../selective_sync/selective_sync_overview.md)
  Record the measured Tier 1 benefit or limitations.
- [vip_warm_start_and_vip_data_refresh_plan.md](../vip_routing/implementation/vip_warm_start_and_vip_data_refresh_plan.md)
  Clarify whether warm behavior was only indirectly supported, or whether a
  dedicated warm-ablation step is still required.

---

## Out of Scope

- changing the workload phases themselves
- changing WAN latency during the first comparison batch
- adding new controller or telemetry instrumentation before the first matrix
- implementing warm-volume snapshot
- claiming a direct warm-lease benefit without a dedicated warm toggle
