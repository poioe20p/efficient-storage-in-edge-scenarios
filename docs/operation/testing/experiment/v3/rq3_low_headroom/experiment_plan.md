# RQ3 Low-Headroom Extension - Experiment Plan

**Status:** PREPARATION IMPLEMENTED - no run launched. **Metric-contract
amendment applied 2026-09-06 (Option 1: plateau-eligible anchor, see §3.1).**

**Parent evidence:** [RQ3 v3 Compute Saturation Campaign](../rq3/experiment_plan.md)
and [its results](../rq3/results.md). This is a new regime-specific follow-up;
its runs are never appended to the August n=7/arm campaign.

## 1. Objective and Scope

RQ3 already establishes a direct-versus-discovery readiness-admission delay,
resource relief, and a null gap-window consequence at the original P4 regime.
This extension tests whether the consequence becomes visible when incumbent
compute capacity has little remaining slack.

The main system variable is uniform `EDGE_CPUS`, applied to static incumbents
and dynamic compute nodes. Workload, rate, thresholds, caps, routing, flow
isolation, storage settings, and readiness code remain frozen.

Included:

- `EDGE_CPUS=0.12` and `0.10` capacity screens;
- one locked quota for four direct/discovery outcome runs;
- two direct event-source-absence runs using the existing fallback path.

Excluded: selective notification loss, release/drain symmetry, storage
readiness, and any thesis claim from calibration or preflight alone.

## 2. Frozen Runtime

- Full tag commit: `rq3-sat-preflight-20260808` ->
  `55c22fbf3a5ab907ce90601fb31dea82ad705e2c`.
- Controller state: `d26709935c72795bcf6d744c5b3b839aeb77f559`; its
  `source/sdn_controller/` tree is byte-identical to the tag.
- Exact retained `edge_server` image prefix: `638e3efdcdc5`.
- `local_state_server` is rebuilt from the tag source under a unique frozen
  image tag because the September campaign changed the host-global image.
- The run uses a detached worktree. The user's current checkout, including its
  dirty canonical `phases.json`, is never modified.
- The historical P4 profile is materialized into the detached worktree's sole
  canonical `source/scripts/testing/phases.json`; no phase variant is created.

P4 values are: 24 clients/LAN, 1.5 requests/s/client, 600 s
`compute_plateau`, `service_pressure=1.0`, `MAX_DYNAMIC_COMPUTE=12`, flow
isolation, `EDGE_MONGO_MAX_POOL_SIZE=6`, `EDGE_CPUS=0.15` for the bridge.

## 3. Primary Metric Contract

True readiness is the passive timestamp in the dynamic edge service log line
containing `app ready: MongoDB ping`. Requests are assigned by `sent_at` and
filtered to `compute_plateau` and the request's `client_lan`.

The primary anchor is the **first plateau-eligible dynamic backend per LAN**
(see §3.1), not the globally first true-ready backend. For run `r` and LAN `l`:

```text
pre  = [anchor_true_ready - 7 s, anchor_true_ready)
post = [anchor_true_ready, anchor_true_ready + 7 s)
L[r,l] = successful_p95(post) - successful_p95(pre)
R[r] = (L[r,1] + L[r,2]) / 2
D[seed] = R[discovery,seed] - R[direct,seed]
```

Successful p95 uses completed HTTP 2xx requests only; each window additionally
requires at least 100 completed 2xx observations (the 100 completed-or-timeout
floor remains, and an all-completed p95 is reported as supporting data).
Timeout rate is `timeout/(completed+timeout)`; failure rate is completed
non-2xx divided by completed; canceled/dropped remain driver outcomes.
Later admissions are supporting data, not additional primary samples.

The seven-second window targets the archived 6.1-6.3 s true-ready-to-admit
separation. It measures transient QoE during the treatment interval, not a
settled-state endpoint.

### 3.1 Metric Contract Amendment (2026-09-06, Option 1)

In all 14 archived runs the globally first dynamic true-ready per LAN occurs
10-25 s before the generator-labeled `compute_plateau` begins, so ±7 s windows
around it contain zero labeled-plateau rows and the original contract is
unsatisfiable. The amendment:

- **Anchor eligibility**: earliest dynamic candidate per LAN whose passive
  true-ready lies in `[plateau_lan_start + 30 s, plateau_lan_end - 7 s)`,
  with plateau bounds taken from the generator-labeled request timeline
  (per-LAN min/max `sent_at` of `compute_plateau` rows). `run_status`
  `started_at` is never used for phase bounds (it precedes traffic launch).
- **No admission conditioning**: candidates come from every admission-log row
  with a spawn timestamp, regardless of `result`. If the selected candidate
  is not admitted, the run fails instead of skipping.
- **Same rule everywhere**: historical lock, bridge, screens, and preflight
  use the identical eligibility rule; the anchor's plateau offset and rank
  among candidates are recorded for reporting.
- **Success floor**: each window must contain >=100 completed 2xx requests
  for its successful p95 to be valid.
- **Screens**: first-wave admissions and `scale_up` decisions are counted
  per LAN inside the first 120 s of the labeled plateau; the recovery window
  `[last first-wave admission + 60 s, +180 s)` is per LAN and must remain
  inside that LAN's plateau.
- **Preflight parity** (implemented, per §7): offered demand difference
  <=2 %, old-CPU difference <=10 pp, first-decision difference <=10 s/LAN,
  add-count difference <=1/LAN, all in the same 30 s pre-anchor LAN window.

Claim boundary: the design estimates the direct-vs-discovery readiness-window
contrast **under the locked low quota**. It does not claim that low headroom
*amplifies* the contrast relative to the archived `EDGE_CPUS=0.15` regime; that
claim would require concurrent 0.15 control cells in the same campaign.

## 4. Historical Reference

Before runtime changes, inventory all 14 August runs and require all seven
direct/discovery pairs to retain admission logs, request CSVs, service logs,
snapshots, and status files. Recompute the primary metric under the §3.1
eligibility rule and persist:

```text
H = max(0.010 s, max(abs(D[seed]) for seed in 3001..3007))
P = 0.010 s
```

`H` is a **descriptive, exploratory** envelope of the archived runs under the
amended endpoint (the archived `D` values were inspected during endpoint
development, so this is not a pre-registered noise bound). `P` is the fixed
10 ms preflight effect floor. The lock record is `rq3lh_metric_lock.json` and
includes run IDs, per-pair seeds (from `open_loop_schedule.json`), all
per-LAN values, `H`, `P`, artifact hashes (request CSV, admission logs,
phases/env/status snapshots, service logs), and the analyzer hash.

## 5. Preparation Bridge

Run before quota screening at the archived P4 quota:

| Order | Label | Arm | Seed | Quota |
| ---: | --- | --- | ---: | ---: |
| 1 | `rq3lh_bridge_direct` | direct | 3001 | 0.15 |
| 2 | `rq3lh_bridge_discovery` | discovery | 3001 | 0.15 |

This pair is a compatibility gate, not evidence. Require the normal integrity,
mechanism, flow, and snapshot gates; true-ready-to-admit separation >=5 s;
pooled sub-max CPU in `[30.3,53.7]` percent; and
`abs(D_bridge) <= max(H,P)`. The CPU range is the archived 40.3-43.7 percent
P4 range with a fixed +/-10 percentage-point tolerance.

## 6. Primary-Outcome-Blind Quota Screens

The screen command may inspect manipulation, CPU, decisions, admissions,
serving, crashes, baseline status, and final-plateau status. It must not emit
the readiness-window p95/timeout/failure metrics or legacy gap outcomes before
the quota lock.

| Order | Label | Seed | Quota |
| ---: | --- | ---: | ---: |
| 1 | `rq3lh_screen_q12_1` | 3099 | 0.12 |
| 2 | `rq3lh_screen_q10_1` | 3099 | 0.10 |
| 3 | `rq3lh_screen_q10_2` | 3100 | 0.10 |
| 4 | `rq3lh_screen_q12_2` | 3100 | 0.12 |

Each run requires:

- canceled+dropped <5%, baseline `http=000` = 0, baseline and final-plateau
  timeout/failure <=1%;
- D1/D2/D3, >=1 compute add/LAN, every add ready/admitted/serving, and no
  plateau scale-down;
- Docker inspection confirms the requested quota on every compute container;
- normal direct event fraction = 1.0 and median true-ready-to-admit <=1 s;
- first true-ready >=30 s after plateau start;
- old-backend CPU in the exact 30 s pre-ready window has median `[60,85]`
  percent and p95 <=95 percent;
- first-wave admissions are those tied to scale decisions in the first 120 s
  of `compute_plateau`, grouped per LAN; at least one/LAN;
- the recovery window `[last first-wave admission+60, +180)` remains wholly
  inside `compute_plateau`, meets the data floor, and shows >=10 percentage
  points old-backend CPU relief.

The CPU band is a hard calibration gate, not a claim that the regime is already
reachable. A quota qualifies only if both of its seed runs pass. Select 0.12 if
both q12 runs pass; otherwise select 0.10 if both q10 runs pass. A split or
empty result is a clean STOP: do not lower the quota, increase load, or relax
the gates. Persist `rq3lh_quota_lock.json` before primary analysis.

The capacity-screen command requires `--quota` and returns non-zero when any
run fails a gate. Its quota gate verifies `quota_snapshot.json`, which the
launcher writes after each run by inspecting every static and dynamic compute
container's Docker CPU limit.

## 7. Main Preflight Matrix

Use the locked quota with full reset between runs:

| Order | Label | Seed | Arm |
| ---: | --- | ---: | --- |
| 1 | `rq3lh_direct_1` | 3101 | direct |
| 2 | `rq3lh_discovery_1` | 3101 | discovery |
| 3 | `rq3lh_event_absent_1` | 3101 | event source absent |
| 4 | `rq3lh_event_absent_2` | 3102 | event source absent |
| 5 | `rq3lh_discovery_2` | 3102 | discovery |
| 6 | `rq3lh_direct_2` | 3102 | direct |

Normal direct runs require event fraction 1.0 and ready-to-admit median <=1 s.
Discovery runs require probe admissions. Event-absence runs are exempt from
normal-direct gates and instead require every admission to use
`probe_fallback`.

All runs require the base mechanism, validity, integrity, flow, quota, request,
and no-scale-down gates. Pair parity is checked in the same 30 s pre-ready LAN
window: offered demand difference <=2%, old CPU difference <=10 percentage
points, first decision time difference <=10 s/LAN, and add-count difference
<=1/LAN. Discovery-minus-direct ready-to-admit separation must be >=5 s.

Preflight GO requires both `D[3101]` and `D[3102]` to be positive and >=`P`,
with at least 3/4 LAN contrasts positive. The contextual comparison to `H` is
reported but does not decide GO. Timeout/failure and legacy gap metrics cannot
rescue a failed primary p95 result.

## 8. Event-Source-Absence Cell

The distinct delta env sets `EDGE_APP_READY_EVENT=0`. This tests total event
producer absence, not selective notification loss.

Require the env snapshot to show zero, no emitted/received `app_ready` events,
all admissions through `probe_fallback`, zero abandoned backends, every add
serving, and no readiness identity violation. Require observed admission no
later than `spawn_complete + READINESS_PROBE_MAX_S +
READINESS_PROBE_TIMEOUT_S` (125 s for the frozen 120+5 values). This is an
observed validity window, not a promise that fallback always succeeds.

Report fallback detection lag and QoE cost against the reused same-seed direct
controls by passing `--control-run` for each same-seed normal direct run. With
n=2, claim only reproduced fallback liveness and observed cost.

## 9. Conditional Campaign

Only after a GO verdict and separate approval: run fresh seeds 3201-3206 at
n=6/arm using the locked quota. The run remains the inferential unit; use paired
exact permutation as primary and exact MWU/Cliff's delta as supporting tests.
Do not pool bridge, screens, preflight, or event-absence runs with that cohort.

## 10. File Map

New:

- `source/scripts/testing/analysis/rq3/readiness_low_headroom.py`
- `source/scripts/testing/rq3lh_p0_01_prepare_frozen.py`
- `source/scripts/testing/rq3lh_p0_02_analyzer_selftest.py`
- `source/scripts/testing/rq3lh_p0_03_preflight.sh`
- `source/scripts/testing/rq3lh_p1_01_launch_run.sh`
- `source/scripts/testing/controller_env_overrides/rq3lh_direct_event_absent.env`
- generated per run: `quota_snapshot.json`
- `docs/operation/testing/experiment/v3/rq3_low_headroom/experiment_plan.md`
- `docs/operation/testing/experiment/v3/rq3_low_headroom/rq3lh_p0_preflight.md`
- `docs/operation/testing/experiment/v3/rq3_low_headroom/rq3lh_preflight_log.md`

Modify only:

- `docs/operation/testing/testing_overview.md`
- `docs/operation/testing/experiment/v3/README.md`

Generated later: `rq3lh_metric_lock.json`, `rq3lh_quota_lock.json`, analysis
CSVs, results, and post-run analysis. Never edit the local main
`phases.json`, `current_state_integrated.env`, controller/application source,
August results, thesis text, or BibTeX.

## 11. Local Validation and Handoff

Before any VM action: Python compilation, analyzer selftest, JSON/env merge
checks, shell syntax checks, wrong-worktree negative test, manifest validation,
and diagnostics. No SSH, Docker, `make`, launcher, or experiment command is
part of implementation validation.

After implementation, the Edge Experiment Runner performs archive inventory,
frozen setup, bridge, screens, six preflight runs, artifact sync, and image
restoration. The Edge Experiment Analyzer writes the verdict. Stop before the
conditional n=6 campaign.
