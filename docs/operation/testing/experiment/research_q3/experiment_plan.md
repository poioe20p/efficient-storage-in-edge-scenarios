# Experiment Plan — research_q3: Eager vs Stabilized Surplus-Capacity Release

**Date**: 2026-09-03 · **Status**: 📋 Planned (merged design v2)

## 1. Objective

**RQ3 — Under recurrent demand in a stateful edge service, how do eager and
stabilized scale-down policies for surplus compute and storage capacity
affect resource occupancy during demand valleys, avoidable lifecycle
churn, and the recovery time and transient service quality observed when
demand returns?**

The experiment compares three structural release policies plus a control,
with a return-timing axis, on the cross-layer edge platform:

- **off** — un-instrumented control (incumbent release path, no release
  log);
- **drained** — **eager-safe** release: on scale-down, drain the container,
  await confirmed `rs.remove`, then terminate promptly;
- **stabilized** — **retention with recall**: on scale-down, hold the
  surplus for H = 480 s — compute is quarantined (registered, non-serving),
  storage is retained (still running + syncing, removed from `VIP_DATA`);
  an overload-recall signal re-admits either tier; on horizon expiry both
  tiers follow the safe (drained) termination path;
- **immediate** — **safety-boundary ablation**, reported separately:
  teardown without drain and without `rs.remove` confirmation. This arm
  bounds the safety cost of skipping the drain/confirmation steps, not a
  candidate policy.

All four arms run under the RQ3 flow-isolation harness
(`VIP_FLOW_ISOLATION=1`, `VIP_SERVER_PER_CONNECTION_FLOWS=1`,
`EDGE_FLOW_ISOLATION=1`) because default per-client flows would turn
immediate teardown into a 60 s flow-pinning artifact.

## 2. Motivation & Hypothesis

The controller-side release machinery (`source/sdn_controller/release_gate.py`,
`release_log.py`, `RELEASE_MECHANISM` knob) now supports all three structural
release paths **on both tiers**: stabilized storage retention (quarantined
from `VIP_DATA` but kept syncing, with overload recall and H-horizon
finalization) is implemented in `main_n1.py`/`main_n2.py` alongside the
proven compute quarantine. Which policy wins is an empirical question: the
fastest release may be the least safe, and the safest may hold surplus
capacity longest. Pre-registered per-arm directions:

| Arm | Direction |
| --- | --- |
| `immediate` | **fastest release**, **worst release safety** (ablation only) |
| `drained` | confirmation-latency cost, clean RS |
| `stabilized` (both tiers) | **zero re-entry action on recall** (capacity retained; a recall at a scale-up site substitutes the capacity add — no new node, no tier budget), **highest hold cost** |
| `off` | un-instrumented control |

Independent variables: `RELEASE_MECHANISM` and the return timing of the
demand valley (edited in-place in the canonical `phases.json` between
blocks — see §3). Held constant: workload otherwise (canonical
`phases.json`), thresholds/cooldowns/caps (`current_state_integrated.env`
+ arm pins), WAN profile, routing policy, telemetry mode, schema, window
sizes, `RANDOM_SEED=42`. The compute-bound workload regime is **deferred**
and pre-registered as a future campaign (see Appendix A).

## 3. Run Matrix

**Cells**: 4 arms × 2 return timings = 8 cells × n=4 = **32 runs + 1
calibration** (33 launches, ≈ 22 h at ~40 min/run).

- **early** return: `hold = 480 s` (return_storm unchanged).
- **late** return: `hold = 900 s` (return_storm unchanged).

The `hold` duration is edited **in-place** in the canonical
`source/scripts/testing/phases.json` between blocks: the canonical file
currently pins `hold = 600 s`; before B1 edit it to **480 s** (early cells)
and after B4 to **900 s** (late cells). Each run folder captures
`phases_snapshot.json` as provenance. No duplicate phase files are created.

Timing math (H = 480 s; compute onsets from calibration v4, storage
retention onsets projected — validated in the new preflight):

| Cell | Compute | Storage |
| --- | --- | --- |
| early (hold=480) | quarantine ≈ hold+221 s; expiry hold+701 s > return → **recall fires** | retention ≈ hold+121 s; expiry hold+601 s > return → **recall fires** |
| late (hold=900) | quarantine ≈ hold+221 s; expiry hold+701 s < return → **finalizes; re-spawn measured** | retention ≈ hold+121 s; expiry hold+601 s < return → **finalizes; re-spawn measured** |

Labels: `research_q3_{o,d,s,i}{e,l}1..4` (arm × timing × replicate) plus
calibration `research_q3_cal_s1` (stabilized, early). Counterbalanced
blocks of 4, arm order rotated per block:

| Block | Runs | Timing |
| --- | --- | --- |
| B1 | `oe1 de1 se1 ie1` | early |
| B2 | `de2 se2 ie2 oe2` | early |
| B3 | `se3 ie3 oe3 de3` | early |
| B4 | `ie4 oe4 de4 se4` | early |
| B5 | `ol1 sl1 dl1 il1` | late |
| B6 | `dl2 il2 sl2 ol2` | late |
| B7 | `sl3 ol3 il3 dl3` | late |
| B8 | `il4 dl4 ol4 sl4` | late |

n=4 is the baseline (RQ2 precedent for cost/run ≈ 40 min), not an
escalation target: n is not a cost constraint. Direction inconsistency
across replicates triggers a **diagnosed** cause + extension, never a
blind rerun. The staged preflight with per-stage checkpoints is specified
in [`preflight_campaign.md`](preflight_campaign.md); checkpoint outcomes
go to [`preflight_log.md`](preflight_log.md).

## 4. Run Configuration

Per run (run on the cloud VM; `rq3stor_launch_run.sh` precedent):

```bash
bash source/scripts/testing/research_q3_launch_run.sh arm_<x>.env research_q3_<x><e|l>N 42
```

`<x>` ∈ {o=off, i=immediate, d=drained, s=stabilized}, timing ∈ {e=early,
l=late}, `N` ∈ {1..4}. Arm env files live under
`docs/operation/testing/experiment/research_q3/env/` and pin only the
research_q3-relevant knobs; the base override
`source/scripts/testing/controller_env_overrides/current_state_integrated.env`
supplies everything else.

Between-block delta (approved edit scope): edit the `hold` duration of the
**canonical** `source/scripts/testing/phases.json` — **600 → 480 s before
B1** (early cells) and **480 → 900 s after B4** (late cells). Every run
folder captures `phases_snapshot.json` as provenance; no variant phase
files are created. After the campaign the canonical file stays at the last
used value (late); the plan documents the edits.

Preflight before the campaign (staged gates + checkpoints —
[`preflight_campaign.md`](preflight_campaign.md)):

```bash
bash source/scripts/testing/rq3rel_p0_preflight.sh
```

The preflight includes one full-length stabilized calibration run
(`research_q3_cal_s1`, seed 42, early timing), excluded from campaign
analysis.

## 5. Measurements & Success Criteria

All C1–C5 metrics are reported **per tier (compute / storage)**, never
pooled across tiers, and per arm × timing cell.

- **C1. Release speed** — time from scale-down decision to capacity
  released (release-log timestamps), per tier.
- **C2. Release safety** — attributed `NotPrimary`/`NotPrimaryOrSecondary`
  rows in the pre-registered windows `[release_begin − 30 s,
  release_end + 90 s]` per the mechanism exception in
  `testing_requirements.md`; rows outside attribution windows must stay 0×.
  Eviction accounting: `C2_evict_nonok = 0` expected for every arm (a non-ok
  eviction flags the replicate); `C2_evict_overlap` is informative;
  `C2_ghosts = 0` expected for `drained`/`stabilized` at probe time and
  informative for `immediate` (the ghost window is its storage-side cost).
- **C3. Hold/drop container-seconds** — surplus capacity retained during
  `hold` and `demand_drop`, per tier.
- **C4. Re-entry time + spawns in `return_storm`** — how quickly recalled
  or re-scaled capacity serves demand when the storm returns, and how many
  spawns it costs, per tier.
- **C5. Churn** — total release + spawn cycles across the run (container
  lifecycle events), per tier.

Pre-registered timing expectations (H = 480 s; compute onsets from
calibration v4, storage retention onsets projected — to be validated in
the new preflight):

| Arm × timing | Timing expectation |
| --- | --- |
| stabilized early — compute | quarantine ≈ `hold` + 210–270 s; expiry `hold`+701 s > return → **recall ≈ return + 20–60 s** |
| stabilized early — storage | retention ≈ `hold` + 121 s (projected); expiry `hold`+601 s > return → **recall ≈ return + 20–60 s** |
| stabilized late — compute | quarantine ≈ `hold` + 210–270 s; expiry `hold`+701 s < return → **finalize ≈ quarantine + 480–520 s; re-spawn measured** |
| stabilized late — storage | retention ≈ `hold` + 121 s (projected); expiry `hold`+601 s < return → **finalize ≈ retention + 480–520 s; re-spawn measured** |
| storage `immediate` | release ≈ `hold`/`demand_drop` start + 80–100 s |
| compute `immediate` | release ≈ last-scale-up + 270 s |
| compute `drained` | release ≈ last-scale-up + 330 s |
| `stabilized` cycle 2 | quarantine ≈ `demand_drop` + 140 s; finalize ≈ `demand_drop` + 620 s; worst case `demand_drop` + 800 s (< 900 s) |

Finalization may slip by up to one housekeeping tick plus is_busy
deferrals (the tick skips while an elasticity operation is busy); the
pre-registered finalize ≈ drop+620 s is the nominal bound and the analyzer
reports actuals. Cycle-2 **storage** retention finalize additionally
requires the storage gate to be re-armed by a storage scale-up at
`return_storm` (reserve activation or DataAlert): after a finalize the gate
holds DORMANT until the next storage scale-up ends the suppression — this
is a documented contingency of the mechanism, not a run failure.

## 6. Analysis Approach

- `cli_release_compare.py` across the 32 campaign run dirs (+1
  calibration) — per-arm × per-tier release speed, safety, hold cost,
  re-entry, churn → `release_compare_table.csv`,
  `release_safety_report.csv`, comparison PNG.
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
    (pre-registered); for stabilized-storage, M1 = the late-cell
    retention finalization (pre-registered);
  - **M2** — excluding never-activated reserves / Tier-1 selective anchors;
  - **V1** — intended bottleneck evidenced;
  - **I1** — N=500 per LAN in `storm_mixed`;
  - **D1** — with the mechanism-exception amendment;
  - **D2**, **D3** — as defined.

## Appendix

### A. Deferred regime (pre-registered)

The compute-bound workload regime (low storage pressure, compute-bound
bottleneck, distinct thresholds) is out of scope for this campaign. It is
pre-registered as a follow-up with the same arm × timing structure; no
conclusions about compute-bound behavior will be drawn from the storage-
bound cells of this campaign.

### C. Validity Threats & Limitations

- Arms are non-factorial (mechanism regimes differ structurally).
- The `immediate` arm is a safety-boundary ablation, reported separately
  from the policy comparison (drained vs stabilized).
- "immediate" retains ~10 s docker-stop SIGTERM grace.
- Recall benefit is conditional on demand returning within the horizon
  (early cells exercise recall; late cells exercise finalize + re-spawn).
- `off` is not RQ1/RQ2-comparable (isolation harness).
- Ghost-window duration is inferred from the post-run probe + eviction logs.
- Both LANs run the same arm per run (cross-run counterbalance + fixed seed).
- Single two-cycle recede-hold-return workload per cell (`hold` 480 s =
  recall cell, `hold` 900 s = finalization cell; `demand_drop` 900 s =
  cycle-2 finalization).
- The preflight cannot exercise the full timeline; the full-length
  stabilized calibration run (`research_q3_cal_s1`, early) covers it.

## Changelog

| Date       | Change       | Rationale |
|------------|--------------|-----------|
| 2026-09-02 | initial plan | —         |
| 2026-09-03 | merged design v2: RQ3 wording, eager-safe vs retention arms, immediate as ablation, return-timing axis (hold 480/900), tier-stratified C1–C5, n=4 per cell | user-approved stronger RQ3 framing |
