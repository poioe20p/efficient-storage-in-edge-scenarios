# Experiment Plans

This folder holds the operator-facing experiment plans used by the experiment
runner.

Current evaluation families:

- [stability/README.md](stability/README.md) — validation-first family for the current implemented architecture, with small reserve-specific tuning follow-ups after usability is already proved.
- [rq1_evaluation/experiment_plan.md](rq1_evaluation/experiment_plan.md) — full RQ1 telemetry delivery cadence evaluation. Push vs. poll at three intervals, measuring decision staleness, reaction latency, transient service quality, and control-plane overhead. Requires the golden config and the fixed `consumed_at` collector.

What `stability` means here:

- It is not a generic label for every experiment.
- It is the family for implementation-validation runs on the current system.
- The first step is always the unchanged baseline run.
- After that baseline, run the mechanism validation plan you need.
- The reserve threshold/load sweeps are optional post-validation tuning passes, not the first proof that reserve works.

Selection rule:

- If you are validating the general current code baseline only, run [stability/current_state_long_cycle/experiment_plan.md](stability/current_state_long_cycle/experiment_plan.md).
- If you are validating Tier 1 selective-sync behavior, run the baseline first and then [stability/tier1_activation/experiment_plan.md](stability/tier1_activation/experiment_plan.md).
- If you are validating storage-reserve liveness only, run the baseline first and then [stability/storage_reserve_validation/experiment_plan.md](stability/storage_reserve_validation/experiment_plan.md).
- If you are validating that an activated reserve actually carries `VIP_DATA` traffic, run the baseline first, then [stability/storage_reserve_validation/experiment_plan.md](stability/storage_reserve_validation/experiment_plan.md), then [stability/storage_reserve_use_validation/experiment_plan.md](stability/storage_reserve_use_validation/experiment_plan.md).
- If you are tuning the reserve activation threshold after reserve use is already proved, run the baseline first, then [stability/storage_reserve_validation/experiment_plan.md](stability/storage_reserve_validation/experiment_plan.md), then [stability/storage_reserve_use_validation/experiment_plan.md](stability/storage_reserve_use_validation/experiment_plan.md), and only then [stability/storage_reserve_threshold_sweep/experiment_plan.md](stability/storage_reserve_threshold_sweep/experiment_plan.md).
- If you are tuning the lightest reproducible offered load after reserve use is already proved, run the baseline first, then [stability/storage_reserve_validation/experiment_plan.md](stability/storage_reserve_validation/experiment_plan.md), then [stability/storage_reserve_use_validation/experiment_plan.md](stability/storage_reserve_use_validation/experiment_plan.md), and only then [stability/storage_reserve_load_sweep/experiment_plan.md](stability/storage_reserve_load_sweep/experiment_plan.md).

For the storage-reserve path specifically, the intended order is:

1. [stability/current_state_long_cycle/experiment_plan.md](stability/current_state_long_cycle/experiment_plan.md)
2. [stability/storage_reserve_validation/experiment_plan.md](stability/storage_reserve_validation/experiment_plan.md) — run the liveness gate first
3. [stability/storage_reserve_use_validation/experiment_plan.md](stability/storage_reserve_use_validation/experiment_plan.md) — confirm that activation becomes request-visible reserve use
4. [stability/storage_reserve_threshold_sweep/experiment_plan.md](stability/storage_reserve_threshold_sweep/experiment_plan.md) — optional coarse threshold tuning after reserve use is proved
5. [stability/storage_reserve_load_sweep/experiment_plan.md](stability/storage_reserve_load_sweep/experiment_plan.md) — optional coarse load tuning after reserve use is proved

Use validation stays separate because it proves reserve usability. The threshold and load sweeps stay separate because their independent variables differ, and both are now explicitly post-usability tuning passes rather than first-line validation.
