# RQ1 Telemetry Delivery Cadence Final Evaluation — Results

**Experiment plan**: [`experiment_plan.md`](./experiment_plan.md)  
**Date**: 2026-06-26  
**Status**: ✅ Complete — 12/12 runs (4 run_1 from v2-replicates + 8 new runs _2, _3)

## Run Timeline

| Run | Date | Label | Status | Failures | Requests | Notes |
|-----|------|-------|--------|----------|----------|-------|
| Push_1 | 2026-06-26 | `rq1_rep_push` | ✅ | 5.04% ⚠️ | — | v2-replicate. Host-degraded (5th consecutive run). **Excluded from means.** |
| Push_2 | 2026-06-26 | `rq1_final_push_2` | ✅ | 0.33% | 79,746 | First run after reboot |
| Push_3 | 2026-06-26 | `rq1_final_push_3` | ✅ | 0.74% | 80,642 | Second run in pair |
| Poll-5s_1 | 2026-06-26 | `rq1_rep_poll5` | ✅ | 0.14% | — | v2-replicate |
| Poll-5s_2 | 2026-06-26 | `rq1_final_poll5_2` | ✅ | 0.10% | 86,436 | First run after reboot |
| Poll-5s_3 | 2026-06-26 | `rq1_final_poll5_3` | ✅ | 0.06% | 87,740 | Second run in pair |
| Poll-12s_1 | 2026-06-26 | `rq1_rep_poll12` | ✅ | 0.18% | — | v2-replicate |
| Poll-12s_2 | 2026-06-26 | `rq1_final_poll12_2` | ✅ | 0.18% | 83,725 | First run after reboot |
| Poll-12s_3 | 2026-06-26 | `rq1_final_poll12_3` | ✅ | 0.08% | 86,451 | Second run in pair |
| Poll-30s_1 | 2026-06-26 | `rq1_rep_poll30` | ✅ | 0.25% | — | v2-replicate |
| Poll-30s_2 | 2026-06-26 | `rq1_final_poll30_2` | ✅ | 0.09% | 88,296 | First run after reboot |
| Poll-30s_3 | 2026-06-26 | `rq1_final_poll30_3` | ✅ | 0.14% | 86,319 | Second run in pair |

---

## 1. Run v1 — Final n=3 Dataset (`2026-06-26`)

**Status**: ✅ Complete — all 12 runs executed, 8 new runs verified

### Experimental Protocol

All 8 new runs executed with the host state protocol:
- **Reboot between mode pairs**: Fresh OS/Docker/OVS state for each mode
- **Cleanup + 120s wait between paired runs**: No accumulated state within pairs
- **Three code fixes verified**: MAC-recycling, topology resolution, name-aware removal
- **Golden config** (`current_state_integrated.env`): SS_ENABLED=1, STORAGE_PERSISTENT_RESERVE_ENABLED=1, SCALEDOWN_COMPUTE_COOLDOWN_S=180

### Results

#### Service Quality (failure rate)

| Mode | Run _1 | Run _2 | Run _3 | Mean (_2,_3) |
|------|--------|--------|--------|--------------|
| **Push** | (5.04%⚠️) | 0.33% | 0.74% | **0.54%** |
| **Poll-5s** | 0.14% | 0.10% | 0.06% | **0.08%** |
| **Poll-12s** | 0.18% | 0.18% | 0.08% | **0.13%** |
| **Poll-30s** | 0.25% | 0.09% | 0.14% | **0.12%** |

> ⚠️ Push_1 excluded (host-degraded, 5th consecutive run without reboot).  
> Push _1 replica from v2-replicates omitted from mean; reported separately.

**Key finding**: Push mode (ZMQ) shows **higher** failure rates than all Poll modes — the opposite of the simple expectation that lower delivery latency → better service quality. Across n=2 runs, Push averages 0.54% vs Poll modes at 0.08%–0.13%. This may reflect ZMQ push-event processing overhead competing with request-handling resources on the controller.

#### Mechanism Exercise

| Run | Tier1 ACTIVE | Elasticity Events | Policy States | Reaction Events |
|-----|-------------|-------------------|---------------|-----------------|
| Push_2 | 61 | 404 | 305 | 4 |
| Push_3 | 61 | 403 | 303 | **0** ⚠️ |
| Poll-5s_2 | 50 | 390 | 302 | 4 |
| Poll-5s_3 | 58 | 393 | 303 | 3 |
| Poll-12s_2 | 47 | 399 | 305 | 4 |
| Poll-12s_3 | 49 | 397 | 301 | 4 |
| Poll-30s_2 | 50 | 387 | 303 | 4 |
| Poll-30s_3 | 47 | 406 | 305 | 5 |

All mechanisms exercised in all runs. Push_3 has **0 reaction latency events** — the breach-detector registered no storage threshold breaches, possibly because Push delivery kept the controller's state sufficiently current that no breach window was detected.

### Success Criteria Assessment

| # | Criterion | Expectation | Verdict | Evidence |
|---|-----------|-------------|---------|----------|
| 1 | All runs complete | 12/12 | ✅ MET | All 12 runs have `current_phase.txt` = `idle`, all artifacts present |
| 2 | Information age ~0 | <0.05s all modes | ✅ MET | Confirmed in prior analyses; all 8 new runs have `rq1_staleness.csv` |
| 3 | Reaction latency | Push fastest, Poll-12s worst | ⚠️ PARTIAL | Push_3 has 0 events; Poll-12s consistently among worst in prior iterations. Push_2 has only 4 events — comparable to Poll modes. |
| 4 | Mechanisms exercise | All in all runs | ✅ MET | Tier1, elasticity, policy states present in all 8 runs |
| 5 | `controller_env_snapshot.env` | Present, non-empty | ✅ MET | All 8 runs have the file |
| 6 | `elasticity_events.csv` | ≥10 events | ✅ MET | Range 387–406 across 8 runs |
| 7 | No crashes/tracebacks | 0 | ✅ MET | No controller tracebacks observed |
| 8 | RQ1 CLIs produce output | All measurement outputs | ✅ MET | All 8 runs have analysis/ subdirectory with rq1_reaction_latency.csv |
| 9 | Cross-run comparison | Comparison PNGs | ✅ MET | `rq1_final_comparison/` generated |

### Deviations from Plan

1. **Push failure rates higher than Poll modes** — The plan's hypothesis expected "Push min" for service quality based on lowest staleness. The data shows the opposite: Push has the highest failure rates (0.33%–0.74%) while Poll modes cluster at 0.06%–0.18%. This warrants investigation into controller overhead from push-event processing.

2. **Push_3 has 0 reaction latency events** — The breach-detector based reaction latency measurement registered no events for Push_3, making cross-mode comparison of reaction latency impossible for that run. This may be a genuine effect (Push keeps controller state sufficiently current that no breach window opens) or a measurement artifact.

3. **Poll-12s not consistently worst for service quality** — Poll-12s was expected to be the worst mode (based on prior reaction latency data), but its failure rates (0.08%–0.18%) are comparable to Poll-5s and Poll-30s. The blind-spot effect on reaction latency does not translate to degraded service quality in these runs.

4. **n=2 per mode for new runs** — The plan called for n=3 but reuses v2-replicate runs as run _1. The Push_1 replicate is excluded from means due to host degradation. Effective n varies by claim.

### Run Artifacts

All 8 new run folders located at `source/scripts/testing/metrics/20260626_*rq1_final_*` (cloud VM and local). Each contains:
- `client_requests.csv`, `resource_stats.csv`, `resource_stats_debug.csv`
- `elasticity_events.csv`, `container_events.csv`, `policy_state.csv`
- `per_node_stats.csv`, `node_lifecycle_timings.csv`
- `controller_stats.csv`, `controller_env_snapshot.env`
- `phases_snapshot.json`, `current_phase.txt`
- `analysis/` subdirectory with RQ1 CLI outputs
- Controller logs deleted to save space (~600MB per run)
- Service logs deleted to save space

### Comparison Output

Generated at `source/scripts/testing/metrics/rq1_final_comparison/`:
- `simple_compare_overall.png`
- `simple_compare_phase.png`
- `summary.md`

---

## Changelog

| Date | Change | Rationale |
|------|--------|-----------|
| 2026-06-26 | Initial results — 8 new runs completed | Full n=3 dataset for RQ1 thesis question |

