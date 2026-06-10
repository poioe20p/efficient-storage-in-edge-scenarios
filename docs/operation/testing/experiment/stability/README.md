# Stability Evaluation

This folder holds the experiment plans that together form the complete
stability evaluation for the architecture. Every mechanism has been
validated in isolation, every fix has been confirmed, and the integrated
configuration has been tuned through six major iterations. The final gate
is the **golden configuration stability pair** — the definitive reference
point before new features are added.

## Status Summary (2026-06-09)

| Experiment | Status | Key result |
|---|---|---|
| [current_state_long_cycle](current_state_long_cycle/experiment_plan.md) | ⚠️ v5.6 — Run A 2.2%, Run B 21.3% (WAN asymmetry, now fixed) | Iterated v1→v5.6; all root causes identified and fixed |
| [conntrack_routing](conntrack_routing/experiment_plan.md) | ✅ Validated | Compute 56–65% → 1.4%. Zero epoch rotations. |
| [wan_http0_root_cause](wan_http0_root_cause/experiment_plan.md) | ✅ Fix confirmed | Cross-LAN veth TX queue. R2: **0.05% at CLIENTS=8**. |
| [recovery_removal_validation](recovery_removal_validation/experiment_plan.md) | ✅ Validated | All 8 criteria passed. |
| [storage_reserve_validation](storage_reserve_validation/experiment_plan.md) | ✅ Liveness passed | Heartbeat stable, no cleanup loops. |
| [storage_reserve_use_validation](storage_reserve_use_validation/experiment_plan.md) | ✅ `reserve-used` | Activated reserve carries VIP_DATA traffic. |
| [storage_reserve_threshold_sweep](storage_reserve_threshold_sweep/experiment_plan.md) | ✅ Boundary found | $0.12 < \tau \leq 0.15$. t12 chosen. |
| [storage_reserve_load_sweep](storage_reserve_load_sweep/experiment_plan.md) | ⚠️ No acceptable candidate | c08 stable at t12 but waiting-only. c10 activates but overloads. |
| [tier1_activation](tier1_activation/experiment_plan.md) | ✅ PASSED | DB-latency 84.5ms → 3.58ms. Clean drain both directions. |
| **[golden_config_stability](golden_config_stability/experiment_plan.md)** | ⚠️ Executed — excessive variance (1.6%–11.8%) | 5 runs, 2/5 SIGSEGV. Two bugs fixed. Variance blocks gate. See [results.md](golden_config_stability/results.md). |
| **[variance_reduction](variance_reduction/experiment_plan.md)** | ✅ **Fix verified — `SCALEDOWN_COMPUTE_COOLDOWN_S=180`** | 4 runs. Root cause: 120s cooldown too short for storage→compute phase transition. Fix: 180s cooldown. Compute phases now 0.04–0.63%. Overall 0.23%. See [results.md](variance_reduction/results.md). |

## Experiment Family

### Infrastructure & Correctness (run once, already validated)

These experiments validated fixes and removals that are now part of the
deployed system. They do not need to be re-run unless the relevant code changes.

- [conntrack_routing/experiment_plan.md](conntrack_routing/experiment_plan.md) — OVS conntrack VIP_DATA routing eliminates stale-rule → AutoReconnect → epoch-rotation cascade.
- [wan_http0_root_cause/experiment_plan.md](wan_http0_root_cause/experiment_plan.md) — Cross-LAN veth TX queue depth fix (`txqueuelen=10000`). 426× improvement over v5.6 B.
- [recovery_removal_validation/experiment_plan.md](recovery_removal_validation/experiment_plan.md) — Recovery VIP infrastructure removed. All 8 log-absence criteria passed.

### Mechanism Validation (run when the mechanism changes)

- [tier1_activation/experiment_plan.md](tier1_activation/experiment_plan.md) — Tier 1 selective-sync lifecycle under a dedicated bidirectional hotspot workload.
- [storage_reserve_validation/experiment_plan.md](storage_reserve_validation/experiment_plan.md) — Tier 2 persistent reserve liveness gate.
- [storage_reserve_use_validation/experiment_plan.md](storage_reserve_use_validation/experiment_plan.md) — Proves activated reserve carries VIP_DATA traffic (usability gate).

### Tuning Sweeps (already executed; re-run only if workload shape changes)

- [storage_reserve_threshold_sweep/experiment_plan.md](storage_reserve_threshold_sweep/experiment_plan.md) — Coarse threshold tuning across t10/t12/t15. Activation boundary found. t12 chosen.
- [storage_reserve_load_sweep/experiment_plan.md](storage_reserve_load_sweep/experiment_plan.md) — Coarse load tuning across c08/c10. c08 stable at t12; capacity ceiling identified.

### Integrated Baseline (iterated; superseded by golden_config_stability)

- [current_state_long_cycle/experiment_plan.md](current_state_long_cycle/experiment_plan.md) — Integrated baseline v1→v5.6. All root causes identified and fixed across the campaign.

### Final Gate (run before any new feature or mechanism)

- **[golden_config_stability/experiment_plan.md](golden_config_stability/experiment_plan.md)** — Definitive stability pair. All fixes + integrated config + canonical workload. Two runs (A/B). Marks the golden configuration values. **This is the only experiment that must pass before new development begins.**

## Quick Start — Running the Final Gate

```bash
# Run A
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  RUN_LABEL=golden_config_a \
  PHASES_CONFIG=testing/phases.json \
  CLIENTS=8 DEVICES=600 NODES=100 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1

# Run B (only after A artifacts saved and no code/env/image changes)
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  RUN_LABEL=golden_config_b \
  PHASES_CONFIG=testing/phases.json \
  CLIENTS=8 DEVICES=600 NODES=100 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
```

See the [golden config plan](golden_config_stability/experiment_plan.md) for
full success criteria, checkpoints, and the marked configuration values.
