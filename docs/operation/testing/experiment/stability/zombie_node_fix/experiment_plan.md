# Experiment Plan — Zombie Node Fix Verification

**Status**: Planned — not yet run.
**Date**: 2026-06-10.
**Depends on**: [variance_reduction](../variance_reduction/experiment_plan.md) — inherits configuration values and the 180s compute scale-down cooldown.

## Intent

Evaluate the `effective_mac`/`effective_ip` fallback fix applied to all four node-spawn handlers (`_handle_compute`, `_handle_data`, `_handle_prepare_standby_storage`, `_handle_selective_sync`) in `elasticity.py`. The fix ensures that when script output parsing fails to return a MAC or IP, the allocator's deterministic values are used instead — preventing nodes from becoming untracked zombies that can never be scaled down.

Answers one question: **after a workload that exercises all elasticity paths, does an extended idle period trigger scale-down of ALL dynamic nodes with zero zombies remaining?**

## Hypothesis / Expected Outcome

If the fix works, a post-experiment idle period of 6 minutes will result in zero dynamic compute containers, zero Tier 1 containers, and at most 1 storage reserve per LAN. No container will be stuck in the "running but untracked" zombie state observed in `variance_reduction_b` (MAC `00:00:00:00:01:07`).

## Independent Variable & Held-Constant Set

- **Independent variable**: the `effective_mac`/`effective_ip` fallback fix (present vs absent — single run with fix applied).
- **Held constant**: all configuration from `variance_reduction` including `SCALEDOWN_COMPUTE_COOLDOWN_S=180`.

### Configuration

All values from [`current_state_integrated.env`](../../../../../../source/scripts/testing/controller_env_overrides/current_state_integrated.env):

- `CLIENTS=8`, `DEVICES=600`, `NODES=100`
- `STORAGE_PERSISTENT_RESERVE_ENABLED=1`, `SS_ENABLED=1`
- `MAX_DYNAMIC_COMPUTE=6`, `MAX_DYNAMIC_STORAGE=5`
- `SCALEUP_STORAGE_BASE_THRESHOLD=0.12`, `SCALEUP_COMPUTE_BASE_THRESHOLD=0.20`
- `SCALEDOWN_COMPUTE_COOLDOWN_S=180`
- Docker images rebuilt with the fixed `elasticity.py`

## Run Matrix

| Run label             | Phase file                            | Fix applied? | Reboot before? |
| --------------------- | ------------------------------------- | ------------ | -------------- |
| `zombie_fix_verify` | `testing/phases.json` | Yes          | Yes            |

Single run is sufficient — we're verifying a deterministic fix, not measuring variance.

## Run Configuration

```bash
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  RUN_LABEL=zombie_fix_verify \
  PHASES_CONFIG=testing/phases.json \
  CLIENTS=8 DEVICES=600 NODES=100 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
```

**Images must be rebuilt** — the fix is in `elasticity.py` which runs inside the `osken-controller` container. Rebuild with:

```bash
sudo -n make -C source/scripts build
```

Or rebuild just the controller image if a targeted build target exists.

## Phases (`phases.json`)

~15 min total, exercises all elasticity paths, ends with 6 min idle for scale-down:

| # | Phase                | Duration | Rate/client | Cross-region | Purpose                                   |
| - | -------------------- | -------- | :---------: | :----------: | ----------------------------------------- |
| 1 | baseline             | 30s      |     1.0     |      0%      | Warm up                                   |
| 2 | storage_stress       | 120s     |     5.0     |     75%     | Trigger storage elasticity + Tier 1       |
| 3 | cross_region_hotspot | 120s     |     6.0     |     95%     | Sustained storage/Tier 1 load             |
| 4 | compute_ramp         | 90s      |     5.0     |      5%      | Trigger compute elasticity                |
| 5 | compute_spike        | 120s     |     7.0     |      5%      | Peak compute load                         |
| 6 | sustained_plateau    | 60s      |     5.0     |      5%      | Moderate compute                          |
| 7 | demand_drop          | 360s     |     1.0     |      0%      | **Idle — scale-down verification** |

Total: 900s (15 min). Mix ratios match the standard `phases.json` for each phase type.

## Focus & Evidence

**Primary**: `docker ps` output and controller logs AFTER the experiment completes — specifically after a 10+ minute post-experiment observation period (DO NOT run `make cleanup`).

**Secondary**: `client_requests.csv`, `container_events.csv`, `elasticity_events.csv`.

### Post-Experiment Verification (manual, on cloud VM)

1. Wait 10+ minutes after experiment ends (traffic generator exits)
2. Run `docker ps | grep -E 'edge_server_lan|edge_storage_lan|sel_sync'`
3. Expected: zero `edge_server_lan*` containers, zero `sel_sync*` containers, at most 1 `edge_storage_lan*` per LAN (the reserve)
4. Run `docker logs osken | grep -E '\[registry\] tracking|\[registry\] removed|zombie|no graceful candidate'`
5. Verify every dynamic node that was spawned also has a corresponding removal log
6. Verify NO "no graceful candidate is eligible" messages during the idle period

## Metrics & Success Criteria

| Metric                                                   | Target                        | How to check                                            |
| -------------------------------------------------------- | ----------------------------- | ------------------------------------------------------- |
| Dynamic compute nodes after idle                         | **0**                   | `docker ps                                              |
| Tier 1 nodes after idle                                  | **0**                   | `docker ps                                              |
| Dynamic storage nodes after idle                         | **≤2** (1 reserve/LAN) | `docker ps                                              |
| Zombie nodes (running but not in `_dynamic_node_macs`) | **0**                   | Controller log: every spawn has a corresponding removal |
| "no graceful candidate" during idle                      | **0 occurrences**       | `docker logs osken                                      |
| Overall failure rate                                     | **≤3%**                | `client_requests.csv` analysis                        |

## Checkpoints

| When                                  | What to check                                      | Action                                                     |
| ------------------------------------- | -------------------------------------------------- | ---------------------------------------------------------- |
| After phase 5 (`compute_spike`)     | At least 3 dynamic compute containers running      | If none, compute elasticity didn't trigger — config issue |
| After phase 6 (`sustained_plateau`) | At least 1 Tier 1 container created during the run | Verify `sel_sync_*` in container events                  |
| 5 min after experiment end            | Scale-down actively removing nodes                 | `docker logs osken                                         |
| 10 min after experiment end           | All dynamic nodes gone                             | `docker ps` verification per success criteria            |

## Validity Threats & Limitations

- **Single run**: a clean run proves the fix works for this specific scenario, but doesn't guarantee it works under all timing conditions. A 3-run confirmation could follow if this passes.
- **Controller image rebuild**: the fix is in Python code inside the `osken-controller` image. If the image isn't rebuilt, the old code runs and the experiment is invalid.
- **Idle period duration**: 6 min of idle in the phase file + additional post-experiment observation. If scale-down is slower than expected (large window sizes, cooldowns), some nodes may still be draining. The post-experiment observation period accounts for this.

## Artifact Contract

Standard run folder under `source/scripts/testing/metrics/<timestamp>_zombie_fix_verify/`.

**DO NOT run `make cleanup` after the experiment.** The post-experiment observation requires live containers and controller logs.

## Changelog

| Date       | Change                                                                                                                                                                | Rationale                                                                                                      |
| ---------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| 2026-06-10 | Initial plan created. Shortened phases (15 min) with 6 min idle tail to verify scale-down of all dynamic nodes after `effective_mac`/`effective_ip` fallback fix. | [variance_reduction results](../variance_reduction/results.md) — zombie node (dyn6) discovered after experiment. |

<!-- end -->
