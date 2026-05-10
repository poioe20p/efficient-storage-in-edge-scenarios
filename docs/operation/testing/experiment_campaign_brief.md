# Experiment Campaign Brief

Use this file as the durable working context for successive experiment runs in
this repository.

- Update it before launching a new run when the objective, run delta, or
  allowed edit scope changes.
- Update it after each completed run summary.
- Do not edit it during an active run unless you are recording a stop or
  restart decision after the run has already been halted.
- Unless requested otherwise, after every completed cloud run use the
  `metrics-run-summary` skill for the created metrics folder, summarize
  remotely when controller logs are no longer needed, then copy the remaining
  run folder back to the local host.

## Campaign

- Name: Elasticity ablation batch 4 cloud run
- Status: in_progress
- Objective: Validate the Tier 1 selective-sync bring-up repair on
  `cloud-vm`, then run the Batch 4 matrix from
  `docs/operation/testing/elasticity_ablation_batch4_plan.md` with compute
  elasticity disabled and higher Tier 2 storage ceilings.
- Hypothesis: Once the Tier 1 wrapper defect is removed, `B4-C1` should bring
  Tier 1 up cleanly again, `B4-C2s4` should improve stressed phases over the
  no-scale control, `B4-C3s4` should become the best balanced combined-policy
  run, and `B4-C3s5` may add more lifecycle churn than end-to-end benefit.
- Primary decision question: After the Tier 1 repair, how much benefit comes
  from raising `MAX_DYNAMIC_STORAGE` to `4` or `5` under the current
  long-cycle workload?

## Remote Execution Context

- VM entry: `ssh cloud-vm`
- VM repo path: `~/efficient-storage-in-edge-scenarios`
- Default experiment entrypoint: `sudo -n make setup_network create_clients
  setup_test_data run_experiment RUN_LABEL=<batch4_label> SKIP_CLIENTS=1
  SKIP_SEED=1 SKIP_SNAPSHOT=1`
- Sudo mode: `sudo -n` is required for autonomous execution; treat any
  interactive password prompt as a cloud-host configuration failure.
- Per-run config application: update only `source/scripts/osken-controller.env`
  on the VM between runs to set `SS_ENABLED`, `MAX_DYNAMIC_STORAGE`, and
  `MAX_DYNAMIC_COMPUTE`.
- Planned run labels: `batch4_c0`, `batch4_c1`, `batch4_c2s4`,
  `batch4_c3s4`, `batch4_c3s5`.
- Validation sequencing assumption: the first full `batch4_c1` run serves as
  both the Tier 1 validation gate and the matrix `B4-C1` run unless launch or
  artifact issues require a rerun.
- Artifact policy: after each completed run, summarize and trim the run folder
  on the VM when controller logs are no longer needed, copy the remaining
  artifacts back locally, verify the copy, and then remove the remote folder.

## Metric Lens

- Primary metrics: per-phase failures and p95 latency from the generated
  request CSVs; Tier 1 lifecycle truth from `coord_state_owner_lan` on the
  retained Batch 4 artifacts and from `tier1_lifecycle_active_count` on any
  reruns collected after the observability fix; `tier1_active_count` as
  supply/freshness telemetry; and `storage_count` / `server_count` trends in
  `resource_stats.csv`; controller log evidence around
  `SelectiveSyncAlert`, `node_add`, coordinator activation, manifest
  broadcast, and Tier 2 lifecycle activity.
- Secondary metrics: `container_events.csv` lifecycle changes;
  `per_node_stats.csv` when present; `current_phase.txt` during live
  monitoring.
- Required reference runs: Batch 3 `C0-C3`, especially
  `20260503_185809_batch3_c0` as the fresh no-scale cloud control,
  `20260503_192822_batch3_c1` as the pre-fix Tier 1 baseline,
  `20260503_195831_batch3_c2` as the clean Tier 2 cloud reference, and
  `20260503_202818_batch3_c3` as the pre-fix combined-path reference.
- Interpretation rule: treat the Tier 1 repair as valid only if the old
  `Permission denied` boundary on `add_network_node.sh` disappears and at
  least one selective node reaches a stable active state; for batch-level
  comparisons, interpret failure rate together with request volume, latency,
  scale counts, and raw controller evidence.

## Allowed Between-Run Edit Scope

- Allowed during this campaign: only `source/scripts/osken-controller.env` on
  the VM between runs, plus local documentation updates for the campaign brief
  and later Batch 4 result notes after runs complete.
- Forbidden during this campaign: code changes, edits outside the controller
  env file on the VM, and edits to active run artifacts while a run is in
  progress.
- Validation used before each run: confirm the three knob values in the remote
  controller env snapshot before launch.

## Live Checkpoint Plan

- Monitoring control rule: once a run has clearly reached traffic generation,
  treat the terminal completion notification for the launched experiment
  command as the authoritative completion signal. Avoid repeated mid-run
  polling unless a declared checkpoint question requires a read-only check.

| Trigger | Question | Data Sources | Continue If | Stop Or Restart If | Notes |
| ------- | -------- | ------------ | ----------- | ------------------ | ----- |
| Pre-run prerequisites | Did the remote env edit and combined launch complete cleanly for the intended Batch 4 setting? | Terminal output, remote `osken-controller.env`, new metrics folder creation | The remote knob values match the intended config and traffic generation begins | Any prerequisite or launch stage fails before traffic starts | Applied for each Batch 4 run |
| Tier 1 bring-up window | For `batch4_c1`, does selective sync attach cleanly and reach active state without the old wrapper failure? | Terminal output, `controller_lan1.log`, `controller_lan2.log`, `resource_stats.csv`, `container_events.csv` | The old `Permission denied` signature is absent and at least one selective node reaches stable active state | The wrapper failure returns or Tier 1 fails before producing useful evidence | Read-only observation unless the run has already clearly failed |
| First hotspot window | Does the active configuration still produce useful evidence and, when applicable, does Tier 2 activate at the higher ceiling? | `current_phase.txt`, `resource_stats.csv`, `container_events.csv`, controller logs | Requests are still flowing and the run progresses through the hotspot phases | The run is clearly dead before the hotspot phases complete | Read-only observation only |
| reverse_hotspot to demand_drop | Does the active configuration stabilize, degrade, or collapse in the late workload path? | Same sources plus terminal output | The run remains collectible to completion | The run is clearly unrecoverable and no new evidence will be produced | No automatic restart is planned |

## Successive Runs

| Planned Label | Intended Delta | Command Or Config Change | Primary Metrics To Inspect | Result Run ID | Verdict | Next Action |
| ------------- | -------------- | ------------------------ | -------------------------- | ------------- | ------- | ----------- |
| batch4_c1 | `SS_ENABLED=1`, `MAX_DYNAMIC_STORAGE=0`, `MAX_DYNAMIC_COMPUTE=0` | Update remote `osken-controller.env`, then launch with `RUN_LABEL=batch4_c1` | Tier 1 attach logs, coordinator activation, manifest broadcast, lifecycle truth (`coord_state_owner_lan`; `tier1_lifecycle_active_count` on reruns), `tier1_active_count` supply telemetry, cleanup completeness | `20260504_114144_batch4_c1` | Tier 1 gate passed with telemetry and cleanup caveats | Keep as the post-fix Tier 1 reference and launch `batch4_c0` next |
| batch4_c0 | `SS_ENABLED=0`, `MAX_DYNAMIC_STORAGE=0`, `MAX_DYNAMIC_COMPUTE=0` | Update remote `osken-controller.env`, then launch with `RUN_LABEL=batch4_c0` | Fresh no-scale failures by phase, p95 latency, no-scale control after the Tier 1 fix | `20260504_150216_batch4_c0` | Clean no-scale control; worse than `B4-C1` and fully static as intended | Launch `batch4_c2s4` next |
| batch4_c2s4 | `SS_ENABLED=0`, `MAX_DYNAMIC_STORAGE=4`, `MAX_DYNAMIC_COMPUTE=0` | Update remote `osken-controller.env`, then launch with `RUN_LABEL=batch4_c2s4` | Tier 2 activation frequency, `storage_count`, failures and latency in hotspot phases | `20260504_155204_batch4_c2s4` | Real Tier 2 scale-out, but worse overall than both Batch 4 baselines and ends with incomplete cleanup | Launch `batch4_c3s4` next |
| batch4_c3s4 | `SS_ENABLED=1`, `MAX_DYNAMIC_STORAGE=4`, `MAX_DYNAMIC_COMPUTE=0` | Update remote `osken-controller.env`, then launch with `RUN_LABEL=batch4_c3s4` | Combined Tier 1 plus Tier 2 stability, hotspot behavior, lifecycle churn | `20260505_074954_batch4_c3s4` | Both Tier 1 and Tier 2 worked and improved on `B4-C2s4`, but the run is still worse overall than the no-scale control and keeps telemetry plus cleanup caveats | Launch `batch4_c3s5` next |
| batch4_c3s5 | `SS_ENABLED=1`, `MAX_DYNAMIC_STORAGE=5`, `MAX_DYNAMIC_COMPUTE=0` | Update remote `osken-controller.env`, then launch with `RUN_LABEL=batch4_c3s5` | Ceiling behavior, additional storage churn, late-phase service quality | `20260505_151638_batch4_c3s5` | Best storage-enabled Batch 4 result: beats `B4-C3s4`, `B4-C0`, and `B4-C2s4`, but still carries Tier 1 telemetry and Tier 2 cleanup caveats | Batch 4 matrix complete; compare final references |

## Stop And Restart Policy

- Automatic stop allowed during this campaign: no, except for a clearly failed
  pre-traffic launch or a run that has already died before producing useful
  workload evidence.
- Automatic restart allowed during this campaign: no.
- Escalation threshold for this campaign: preserve passive monitoring unless
  the run is clearly unrecoverable and continuing would add no useful
  evidence.
- Recovery plan for this campaign: preserve partial artifacts, record the
  failure mode, and relaunch only if the issue is infrastructure or shell
  level rather than behavioral.

## Cross-Run Notes

- Batch 3 confirmed that the cloud-only path did not change the overall
  mechanism ordering: `C2` remained the clean Tier 2 reference and compute
  elasticity stayed dormant.
- Batch 4 starts from the retained Batch 3 Tier 1 defect evidence in
  `20260503_174814_cloud_snapshot_env`, where the selective wrapper hit
  `Permission denied` on `add_network_node.sh` before the shared attach logic
  ran.
- The Tier 2 storage path was not blocked by that defect because it already
  invoked the shared attach script through `/bin/bash`.
- `batch4_c1` removed the original Tier 1 wrapper confounder: selective nodes
  on both LANs attached through `/bin/bash`, reached `state=DONE`, became
  `ACTIVE`, and drained cleanly.
- `batch4_c1` still left two independent caveats for the rest of Batch 4:
  the legacy supply-side `tier1_active_count` stayed at `0` in
  `resource_stats.csv` even though coordinator state reached `ACTIVE`, and the
  controller kept issuing `/forwarder_config` reconfigure attempts after Tier
  1 cleanup.
- `batch4_c0` completed as the fresh post-fix no-scale control with no Tier 1,
  no Tier 2, and no compute elasticity activity in either
  `container_events.csv` or the controller logs.
- Relative to `batch4_c1`, `batch4_c0` was clearly worse overall
  (`21.09%` failures versus `16.65%`) and especially worse in
  `cross_region_hotspot` and `reverse_hotspot`, so the repaired Tier 1 path
  remains a meaningful positive reference despite its telemetry caveats.
- `batch4_c2s4` confirmed that the higher Tier 2 ceiling is live on
  `cloud-vm`: dynamic storage containers appeared on both LANs, `storage_count`
  reached `4.0`, and neither Tier 1 nor compute elasticity activated.
- `batch4_c2s4` is not a net improvement run. It completed with `22.92%`
  failures (`8,705 / 37,974`), which is worse than both `batch4_c0` and
  `batch4_c1` even though `local_moderate`, `cross_region_hotspot`,
  `reverse_hotspot`, and `demand_drop` each improved on the no-scale control.
- The new Batch 4 Tier 2 caveat is cleanup quality rather than bring-up:
  `edge_storage_lan2_dyn2` hit a controller-side scale-down failure,
  `edge_storage_lan1_dyn2` never drained before the run ended, and the final
  `idle` snapshot still retained `edge_storage_lan1_dyn2`,
  `edge_storage_lan1_dyn6`, and `edge_storage_lan2_dyn2`.
- `batch4_c3s4` is the first combined-policy proof point: both repaired Tier 1
  and higher-ceiling Tier 2 activity appear in the same run, with `2`
  selective nodes reaching `[tier1] ACTIVE` and `9` distinct dynamic storage
  nodes appearing.
- `batch4_c3s4` improves on `batch4_c2s4` but still does not beat the fresh
  no-scale control overall. It finishes at `21.82%` failures
  (`8,771 / 40,199`), below `batch4_c2s4` but above `batch4_c0`.
- The first `batch4_c3s5` launch attempt (`20260505_114215_batch4_c3s5`)
  stalled in `cross_region_hotspot` after the SSH-bound launch path died.
  Treat that folder as transport-failure evidence only, not as a performance
  result for the ceiling-5 comparison.
- The successful `batch4_c3s5` relaunch (`20260505_151638_batch4_c3s5`) is the
  best storage-enabled Batch 4 result so far. It finishes at `20.68%`
  failures (`7,895 / 38,183`), improving on `batch4_c3s4`, `batch4_c0`, and
  `batch4_c2s4`, though it still trails the Tier 1-only reference
  `batch4_c1`.
- `batch4_c3s5` reaches `storage_count=5` with `10` distinct dynamic storage
  containers and again exercises Tier 1 on both LANs.
- The persistent Tier 1 telemetry caveat remains active in the combined run:
  the retained Batch 4 `resource_stats.csv` still reports
  `tier1_active_count=0` even though both LAN controllers log `[tier1] ACTIVE`;
  treat that field as supply telemetry rather than lifecycle truth. Future
  reruns should use `tier1_lifecycle_active_count`.
- The post-cleanup Tier 1 reconfigure caveat also remains: after
  `sel_sync_lan1_dyn3` is removed, controller work continues and logs
  `/forwarder_config` timeouts and `EHOSTUNREACH` against the removed node.
- Tier 2 cleanup is better than in `batch4_c2s4` but not complete:
  `edge_storage_lan2_dyn3` and `edge_storage_lan2_dyn4` remain in the final
  `idle` snapshot.
- Tier 2 cleanup remains incomplete at the ceiling-5 setting as well:
  `edge_storage_lan2_dyn2`, `edge_storage_lan2_dyn3`, `edge_storage_lan1_dyn3`,
  and `edge_storage_lan1_dyn5` remain unremoved at run end, and controller
  logs show `scale_down_data FAILED` for `edge_storage_lan1_dyn3`,
  `edge_storage_lan2_dyn3`, and `edge_storage_lan2_dyn2`.
- Relative to the pre-fix Batch 3 `C1` reference, `batch4_c1` improved overall
  failure rate and reduced `reverse_hotspot` failures, so the remaining issues
  are no longer explained by the wrapper defect.
- Compute remains intentionally disabled for every Batch 4 run.
- Local copy-back status before Batch 4: verified locally for all Batch 3 run
  folders.
- Remote retention status before Batch 4: remote Batch 3 folders removed after
  local copy verification.
- Current Batch 4 remote retention caveat: the cloud host allows the
  `sudo -n make ... run_experiment` path but rejects direct `sudo -n rm`, so
  completed Batch 4 run folders currently remain on the VM after verified local
  copy-back. This does not block the campaign because the metrics filesystem
  still has about `63G` free.

## Next Run Checklist

1. Treat `batch4_c1` as the best pure Tier 1 Batch 4 reference and
  `batch4_c3s5` as the best storage-enabled combined Batch 4 reference.
2. Exclude `20260505_114215_batch4_c3s5` from performance comparisons because
  it is a transport-failure partial run, not a completed workload result.
3. Carry the persistent Tier 1 telemetry blind spot and the post-cleanup
  reconfigure noise into the next investigation slice.
4. Carry the unresolved Tier 2 cleanup debt at both ceilings `4` and `5` into
  the next storage-focused debugging slice.
5. Keep remote retention caveats documented: the cloud sudo policy still blocks
  direct cleanup even after verified local copy-back.
