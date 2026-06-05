# Stability Evaluation

This folder holds the experiment plans that together form the current
stability evaluation for the architecture.

Latest analyzed results:

- [storage_reserve_validation/results.md](storage_reserve_validation/results.md) — `storage_reserve_smoke` passed the reserve-liveness gate; activation remained untested.
- [tier1_activation/results.md](tier1_activation/results.md) — **PASSED.** Authoritative runs `20260604_204334` (control, SS_ENABLED=0) and `20260604_205108` (enabled, SS_ENABLED=1) with Tier 2 fully isolated. Tier 1 activated and drained cleanly in both directions; the first-direction DB-latency comparison shows Tier 1 eliminating the cross-region penalty (84.5 ms → 3.58 ms).

In this repository, `stability` means validation-first work for the
current system, plus a small number of reserve-specific tuning follow-ups.
These plans answer:

1. Does the unchanged baseline stay bounded under the standard long-cycle workload?
2. When one mechanism is exercised directly, does it behave correctly without destabilizing the run?
3. After reserve is already proved usable, which coarse operating point should later campaigns keep?

Experiments in this family:

- [current_state_long_cycle/experiment_plan.md](current_state_long_cycle/experiment_plan.md) — baseline repeatability under the standard long-cycle workload.
- [tier1_activation/experiment_plan.md](tier1_activation/experiment_plan.md) — selective-sync activation, service effect, and clean drain under a dedicated Tier 1 hotspot workload.
- [tier1_activation/results.md](tier1_activation/results.md) — analyzed June 4 Tier 1 outcome, including the enabled-run verdict and the control-run caveat.
- [storage_reserve_validation/experiment_plan.md](storage_reserve_validation/experiment_plan.md) — persistent Tier 2 reserve liveness gate after the heartbeat fix.
- [storage_reserve_validation/results.md](storage_reserve_validation/results.md) — analyzed June 4 reserve-liveness gate result.
- [storage_reserve_threshold_sweep/experiment_plan.md](storage_reserve_threshold_sweep/experiment_plan.md) — coarse post-usability threshold tuning across three candidate trigger settings.
- [storage_reserve_load_sweep/experiment_plan.md](storage_reserve_load_sweep/experiment_plan.md) — coarse post-usability load tuning across three candidate client counts.
- [storage_reserve_use_validation/experiment_plan.md](storage_reserve_use_validation/experiment_plan.md) — targeted proof that an activated reserve actually carries `VIP_DATA` traffic after a forced connection-refresh window.

Use this family in two stages.

Stage 1: always run the baseline first.

1. [current_state_long_cycle/experiment_plan.md](current_state_long_cycle/experiment_plan.md)

Stage 2: run the mechanism validation plan first, then optional reserve tuning only after reserve use is proved.

1. [tier1_activation/experiment_plan.md](tier1_activation/experiment_plan.md) only if you are validating Tier 1 selective-sync
2. [storage_reserve_validation/experiment_plan.md](storage_reserve_validation/experiment_plan.md) first if you are validating the storage persistent-reserve path at all
3. [storage_reserve_use_validation/experiment_plan.md](storage_reserve_use_validation/experiment_plan.md) after the liveness gate if the question is whether the promoted reserve actually becomes request-visible capacity
4. [storage_reserve_threshold_sweep/experiment_plan.md](storage_reserve_threshold_sweep/experiment_plan.md) only after use validation reaches `reserve-used`, if the question is threshold tuning
5. [storage_reserve_load_sweep/experiment_plan.md](storage_reserve_load_sweep/experiment_plan.md) only after use validation reaches `reserve-used`, if the question is offered-load tuning

For the storage-reserve work discussed in this repository, the intended order is:

1. [current_state_long_cycle/experiment_plan.md](current_state_long_cycle/experiment_plan.md)
2. [storage_reserve_validation/experiment_plan.md](storage_reserve_validation/experiment_plan.md)
3. [storage_reserve_use_validation/experiment_plan.md](storage_reserve_use_validation/experiment_plan.md)
4. [storage_reserve_threshold_sweep/experiment_plan.md](storage_reserve_threshold_sweep/experiment_plan.md) only if threshold tuning is needed
5. [storage_reserve_load_sweep/experiment_plan.md](storage_reserve_load_sweep/experiment_plan.md) only if offered-load tuning is needed

Do not run the Tier 1 plan as part of the storage-reserve sequence unless you are explicitly validating selective-sync in a separate campaign.

If the campaign goal is to gate selective-sync behind reserve liveness, the allowed order is:

1. [storage_reserve_validation/experiment_plan.md](storage_reserve_validation/experiment_plan.md)
2. [tier1_activation/experiment_plan.md](tier1_activation/experiment_plan.md) only if the reserve-validation success criteria are met

Use validation stays separate from the two tuning sweeps. It proves request-visible reserve use. The threshold sweep then varies `SCALEUP_STORAGE_BASE_THRESHOLD` only, and the load sweep varies offered load only. Each remains single-variable, but the tuning work now happens only after usability is already established.
