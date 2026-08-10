---
description: "Operational lessons learned during edge-platform experiments. Applies to experiment runner and analyzer agents to avoid repeating known mistakes."
applyTo: ".github/agents/experiment-runner-edge.agent.md,.github/agents/edge-experiment-analyzer.agent.md"
---

# Edge Platform — Lessons Learned

*Record operational lessons discovered during experiments to avoid repeating mistakes.*

## SSH Keepalive

The cloud VM's SSH server kills idle connections after ~5 min. **Always use
`ssh -o ServerAliveInterval=60`** for any `ssh` command that needs to stay open
longer than a quick check. This includes `mode=async` experiment launches,
mid-run status checks, and file sync operations.

Discovered on 2026-06-29 during `rq1_v2_push_1` attempts — SSH dropped
mid-settle, causing premature run termination. The 10+ min of accumulated
settle time from the two prior failed attempts was a fortunate side-effect, not
a reliable fallback.

## CRLF Line Endings from Windows `scp`

`scp` from Windows preserves CRLF line endings which break bash scripts on the
cloud VM. Always run `sed -i 's/\r$//'` on any `.sh` file synced from Windows
before using it. Also fix the local file's line endings to prevent recurrence.

When copying analysis outputs (summary CSVs, graphs, summaries) back from the
cloud VM to the local repo for archival, be aware that Windows tools may add
CRLF to text files that are later re-synced to the VM (e.g. shell scripts
deployed for a future run). Always verify shell scripts have Unix line endings
before re-deploying. Fix: `sed -i 's/\r$//'` on the cloud VM, or use `dos2unix`
if available. Run folders and raw artifacts always stay on the hosting VM —
only analysis outputs are synced back to the local repo.

Discovered on 2026-07-03 during `rq1_v2final_push_1` launch —
`build_network_setup.sh` synced with CRLF caused `set: pipefail: invalid option`
and make failed immediately.

## Shared Runner Gate False-Failures (RQ2 × RQ3 gate)

Enabling a cross-RQ feature at the config level can trip a *different* RQ's
post-run validity gate in the shared `run_experiment.sh`. When we enabled the
readiness admission gate for RQ2 (`READINESS_PROPAGATION=direct` +
`EDGE_APP_READY_EVENT=1`), every RQ2 run was mislabeled FAILED by the RQ3
validity gate, which hard-requires `EDGE_FLOW_ISOLATION=1` (an RQ3 measurement
instrument RQ2 deliberately leaves off).

**Fix:** the RQ3 gate now keys its RQ3-specific checks (flow-validation,
`EDGE_FLOW_ISOLATION=1`) on `VIP_FLOW_ISOLATION=1` in the env snapshot;
readiness-gate-only runs (`VIP_FLOW_ISOLATION=0`) get only the gate-relevant
checks (min-admissions, `EDGE_APP_READY_EVENT`).

**Lesson:** before enabling a config axis shared across RQs, audit the runner's
post-run gates for hard requirements that assume the original RQ's measurement
setup. A clean run can be marked failed by an unrelated gate — and a "failed"
run masks valid episode data.

Discovered on 2026-08-06 during `rq2_ba_cb_gate` — the episode data was
complete (0.46 % timeout) but the run was marked failed by the RQ3
`EDGE_FLOW_ISOLATION=1` requirement.

## Orchestrator "Already Completed" v2-Label Collision (RQ2 v3)

`run_rq2_campaign.py` `is_run_completed()` matched ANY metrics folder ending
in `_<run_label>` with a completed/failed `run_status.json`. The v2 RQ2
campaign (2026-08-06) used the SAME labels as v3 (`rq2_<cell>_1..3`), so on
the first v3 campaign launch the orchestrator silently skipped runs 1–13 and
started at `rq2_ba_cb_3` — corrupting the 36-run design (missing the `_1`/`_2`
replicates for every cell). Only the launch-time log revealed it.

**Fix:** `is_run_completed()` now requires the v3 marker
`STORAGE_PERSISTENT_RESERVE_ENABLED=1` in the folder's
`controller_env_snapshot.env` before treating it as completed; the v2 folders
(reserve off) no longer qualify. Validate the discriminator before relaunching
(a v2 folder must yield NOT, a v3 folder DONE).

**Lesson:** before an orchestrator/campaign tool reuses run labels across
campaign versions, audit its completion detection for era/provenance markers —
a "skip" is silent data loss. After launching, confirm the first 1–2
orchestrator log lines (`[1/N] ... attempting`) show attempts, not skips.

Discovered on 2026-08-08 during the RQ2 v3 campaign launch (attempt 1 aborted
at `rq2_ba_cb_3`, relaunched cleanly at `rq2_ba_cb_1`).

## Base Requirements Gate

Every run must be checked against `docs/operation/testing/testing_requirements.md`
before it is treated as evidence — the runner fail-fast at end of run, the
analyzer before any verdict. The base doc is the floor; RQ-specific gates in the
plan sit on top. Magnitudes are plan-defined, never invented at analysis time. A
missed hard gate ⇒ the run is not thesis evidence unless the plan pre-registered
the exception.

## Long-Run Monitoring (Open Investigation)

Runs can take 40+ minutes. The current approach (`mode=async` terminal +
`ServerAliveInterval=60`) works but has failure modes:

- **SSH keepalive gaps**: If the VM is slow to respond, the keepalive may not
  prevent a dropped connection on a 40-minute run.
- **No progress visibility**: The runner has no mid-run signal beyond
  `current_phase.txt` — if the run silently stalls, detection is delayed until
  the terminal exits (or doesn't).
- **Investigation needed**: Evaluate alternatives such as `nohup` +
  detached execution with periodic phase-polling from a separate SSH session,
  or a lightweight watchdog script on the cloud VM that writes heartbeat
  timestamps the runner can check independently.
