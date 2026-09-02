# Experiment Plan — research_q3: Surplus-Capacity Release Mechanisms

**Date**: 2026-09-02 · **Status**: 📋 Planned

## 1. Objective

Compare three structural surplus-capacity release mechanisms on the
cross-layer edge platform:

- **immediate** — release ASAP: teardown without drain and without
  `rs.remove` confirmation;
- **drained** — incumbent graceful release (drain + `rs.remove`
  confirmation);
- **stabilized** — compute-side 480 s quarantine with recall (released
  capacity is retained in the pool and can be recalled by an
  overload-recall signal); storage follows drained.

**off** = the un-instrumented control (incumbent release path, no release
log). All four arms run under the RQ3 flow-isolation harness
(`VIP_FLOW_ISOLATION=1`, `VIP_SERVER_PER_CONNECTION_FLOWS=1`,
`EDGE_FLOW_ISOLATION=1`) because default per-client flows would turn
immediate teardown into a 60 s flow-pinning artifact.

## 2. Motivation & Hypothesis

The controller-side release machinery (`source/sdn_controller/release_gate.py`,
`release_log.py`, `RELEASE_MECHANISM` knob) now supports three structural
release paths. Which one wins is an empirical question: the fastest release
may be the least safe, and the safest may hold surplus capacity longest.
Pre-registered per-arm directions:

| Arm | Direction |
| --- | --- |
| `immediate` | **fastest release**, **worst release safety** |
| `drained` | confirmation-latency cost, clean RS |
| `stabilized` (compute) | **zero re-entry action on recall** (capacity retained in pool), **highest hold cost** |
| `off` | un-instrumented control |

Storage contrast is single-axis immediate-vs-drained: the stabilized arm's
storage tier follows drained, so any storage-tier difference isolates the
drain/`rs.remove` confirmation path.

Single independent variable: `RELEASE_MECHANISM`. Held constant: workload
(canonical `phases.json`), thresholds/cooldowns/caps
(`current_state_integrated.env` + arm pins), WAN profile, routing policy,
telemetry mode, schema, window sizes, `RANDOM_SEED=42`.

## 3. Run Matrix

28 runs + 1 calibration: 4 arms × n=6 (seed 42) + n=1 seed-43 sensitivity
replicate per arm. Labels `research_q3_{o,i,d,s}1..6` (seed 42),
`research_q3_{o,i,d,s}x1` (seed 43), calibration `research_q3_cal_s1`.
Counterbalanced blocks: B1 `o1 i1 d1 s1 o2 i2 d2`, B2 `s2 o3 i3 d3 s3 o4 i4`,
B3 `d4 s4 o5 i5 d5 s5 o6`, B4 `i6 d6 s6 ox1 ix1 dx1 sx1`.

| # | Label | Arm | Purpose |
| --- | --- | --- | --- |
| B1 | `research_q3_o1` | off | Un-instrumented control |
| B1 | `research_q3_i1` | immediate | Fast release, worst safety |
| B1 | `research_q3_d1` | drained | Graceful release, clean RS |
| B1 | `research_q3_s1` | stabilized | Quarantine + recall |
| B1 | `research_q3_o2` | off | replicate |
| B1 | `research_q3_i2` | immediate | replicate |
| B1 | `research_q3_d2` | drained | replicate |
| B2 | `research_q3_s2` | stabilized | replicate |
| B2 | `research_q3_o3` | off | replicate |
| B2 | `research_q3_i3` | immediate | replicate |
| B2 | `research_q3_d3` | drained | replicate |
| B2 | `research_q3_s3` | stabilized | replicate |
| B2 | `research_q3_o4` | off | replicate |
| B2 | `research_q3_i4` | immediate | replicate |
| B3 | `research_q3_d4` | drained | replicate |
| B3 | `research_q3_s4` | stabilized | replicate |
| B3 | `research_q3_o5` | off | replicate |
| B3 | `research_q3_i5` | immediate | replicate |
| B3 | `research_q3_d5` | drained | replicate |
| B3 | `research_q3_s5` | stabilized | replicate |
| B3 | `research_q3_o6` | off | replicate |
| B4 | `research_q3_i6` | immediate | replicate |
| B4 | `research_q3_d6` | drained | replicate |
| B4 | `research_q3_s6` | stabilized | replicate |
| B4 | `research_q3_ox1` | off | seed-43 sensitivity |
| B4 | `research_q3_ix1` | immediate | seed-43 sensitivity |
| B4 | `research_q3_dx1` | drained | seed-43 sensitivity |
| B4 | `research_q3_sx1` | stabilized | seed-43 sensitivity |

n=6 is the baseline (RQ2 precedent), not an escalation target: n is not a
cost constraint. Direction inconsistency across replicates triggers a
**diagnosed** cause + extension, never a blind rerun. A replicate is replaced
when `recall_missed` occurs in ≥2 of the 6 stabilized runs. The staged
preflight with per-stage checkpoints is specified in
[`preflight_campaign.md`](preflight_campaign.md); checkpoint outcomes go to
[`preflight_log.md`](preflight_log.md).

## 4. Run Configuration

Per run (run on the cloud VM; `rq3stor_launch_run.sh` precedent):

```bash
bash source/scripts/testing/research_q3_launch_run.sh arm_<x>.env research_q3_<x>N 42
```

`<x>` ∈ {o=off, i=immediate, d=drained, s=stabilized}, `N` ∈ {1..6} plus the
`x1` seed-43 replicate (`... research_q3_<x>x1 43`). Arm env files live under
`docs/operation/testing/experiment/research_q3/env/` and pin only the
research_q3-relevant knobs; the base override
`source/scripts/testing/controller_env_overrides/current_state_integrated.env`
supplies everything else.

Preflight before the campaign (staged gates + checkpoints —
[`preflight_campaign.md`](preflight_campaign.md)):

```bash
bash source/scripts/testing/rq3rel_p0_preflight.sh
```

The preflight includes one full-length stabilized calibration run
(`research_q3_cal_s1`, seed 42), excluded from campaign analysis.

## 5. Measurements & Success Criteria

- **C1. Release speed** — time from scale-down decision to capacity
  released (release-log timestamps).
- **C2. Release safety** — attributed `NotPrimary`/`NotPrimaryOrSecondary`
  rows in the pre-registered windows `[release_begin − 30 s,
  release_end + 90 s]` per the mechanism exception in
  `testing_requirements.md`; rows outside attribution windows must stay 0×.
  Eviction accounting: `C2_evict_nonok = 0` expected for every arm (a non-ok
  eviction flags the replicate); `C2_evict_overlap` is informative;
  `C2_ghosts = 0` expected for `drained`/`stabilized` at probe time and
  informative for `immediate` (the ghost window is its storage-side cost).
- **C3. Hold/drop container-seconds** — surplus capacity retained during
  `hold` and `demand_drop`.
- **C4. Re-entry time + spawns in `return_storm`** — how quickly recalled
  or re-scaled capacity serves demand when the storm returns, and how many
  spawns it costs.
- **C5. Churn** — total release + spawn cycles across the run (container
  lifecycle events).

Pre-registered timing expectations:

| Arm | Timing expectation |
| --- | --- |
| storage `immediate` | release ≈ `hold`/`demand_drop` start + 80–100 s |
| compute `immediate` | release ≈ last-scale-up + 270 s |
| compute `drained` | release ≈ last-scale-up + 330 s |
| `stabilized` cycle 1 | quarantine ≈ `hold` + 210–270 s; recalled ≈ `return_storm` + 20–30 s |
| `stabilized` cycle 2 | quarantine ≈ `demand_drop` + 140 s; finalize ≈ `demand_drop` + 620 s; worst case `demand_drop` + 800 s (< 900 s) |

Finalization may slip by up to one housekeeping tick plus a 0–30 s is_busy
drift; the pre-registered finalize ≈ drop+620 s is the nominal bound and the
analyzer reports actuals.

## 6. Analysis Approach

- `cli_release_compare.py` across the 12 run dirs (per-arm release speed,
  safety, hold cost, re-entry, churn → `release_compare_table.csv`,
  `release_safety_report.csv`, comparison PNG).
- Per-run artifacts consumed: `release_log_lan{1,2}.csv` (release events,
  join key `(network_id, container)`), `rs_evict_logs_lan{1,2}/` (eviction
  outcomes + `eviction_overlap` flags), `rs_status_*.json` (ghost count;
  written automatically per run by `rq3rel_p4_rs_probe.py` invoked from
  `run_experiment.sh`), `decision_log_lan{1,2}.csv`, `container_events.csv`,
  `client_requests.csv`, `phases_snapshot.json`.
- `rq3rel_p4_rs_probe.py` per run (one post-run replica-set status snapshot
  per run folder, `rs_status_*.json`) — `run_experiment.sh` invokes it
  automatically, so no separate operator step is needed.
- Gates per `docs/operation/testing/testing_requirements.md`:
  - **M1** — for stabilized-compute, M1 = cycle-2 finalization
    (pre-registered);
  - **M2** — excluding never-activated reserves / Tier-1 selective anchors;
  - **V1** — intended bottleneck evidenced;
  - **I1** — N=500 per LAN in `storm_mixed`;
  - **D1** — with the mechanism-exception amendment;
  - **D2**, **D3** — as defined.

## Appendix

### C. Validity Threats & Limitations

- Arms are non-factorial (mechanism regimes differ structurally).
- Stabilized is compute-only; its storage tier follows drained.
- "immediate" retains ~10 s docker-stop SIGTERM grace.
- Recall benefit is conditional on demand returning within the window.
- `off` is not RQ1/RQ2-comparable (isolation harness).
- Ghost-window duration is inferred from the post-run probe + eviction logs.
- Both LANs run the same arm per run (cross-run counterbalance + fixed seed).
- Single two-cycle recede-hold-return workload (`hold` 600 s = recall
  cycle; `demand_drop` 900 s = finalization cycle).
- The preflight cannot exercise the full timeline; the full-length
  stabilized calibration run (`research_q3_cal_s1`) covers it.

## Changelog

| Date       | Change       | Rationale |
|------------|--------------|-----------|
| 2026-09-02 | initial plan | —         |
