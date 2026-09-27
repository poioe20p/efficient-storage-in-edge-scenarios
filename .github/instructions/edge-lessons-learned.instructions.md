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

## Pre-Registered Zero-Admission Cells vs the Shared Min-Admissions Gate (RQ3 robustness)

The shared RQ3 gate in `run_experiment.sh` hard-requires ≥1 admitted backend
per LAN. The robustness `loss_all × event_only` cell pre-registers ZERO
admissions (every event dropped; the 130 s fallback is inert because abandon
fires at probe max 120) — and the gate false-failed a run whose data was
exactly as pre-registered (0 admitted, 32 abandoned, zero `probe_fallback`,
flow checks all PASS).

**Fix:** the gate now waives min-admissions when the env snapshot has
`READINESS_EVENT_DROP_MODE=all` AND `READINESS_EVENT_FALLBACK_S >= 120`
(the zero-admission cell signature). Any other cell keeps the hard gate.

**Lesson:** when a plan pre-registers an outcome that a shared gate treats as
an error, the gate must be keyed to the cell's config signature BEFORE the
first evidence run — same class as the RQ2 × RQ3 gate false-failure above.
Diagnose from the gate's own output first; a "failed" run can hold valid data.

Discovered on 2026-09-06 during `rq3rob_loss_all_event_only_0` (Stage 0.2.3).

## osken Logging Config Suppresses sdn_controller INFO (Fault-Evidence Invisible)

The `osken-controller` image's `/etc/osken/logging.conf` sets the ROOT logger
to WARNING and only promotes `os_ken.*` to DEBUG. `sdn_controller.*` module
loggers inherit root, so `logger.info(...)` evidence lines never reach the
captured controller logs. The RQ3 robustness drop-knob originally logged
dropped app_ready events at INFO: the mechanism worked (all admissions were
`probe_fallback`) but zero drop rows appeared in `controller_lan*.log`,
breaking the plan's "drop-log rows match mode" gate.

**Fix:** fault-evidence lines in `sdn_controller` must be emitted at WARNING
(or the logging config must promote the module). Verify the level change with
a live mid-run grep of the captured controller log before the run ends.

Discovered on 2026-09-06 during `rq3rob_loss_all_hybrid_0` (Stage 0.2.2).

## Frozen Worktree Materialization: Verify Phases CONTENT, Not Just JSON Validity

When materializing canonical phases into a frozen worktree, copy from the
correct source and verify the CONTENT (phase names, durations, mixes) — not
just `python3 -m json.tool`. The base tag's `phases_override/
phases_rq3_saturation.json` carries a MIXED plateau (service_pressure 0.6 /
content_lookup 0.2 / feed_ranking 0.2), while the canonical pure-compute P4
(service_pressure 1.0) lives in the low-headroom frozen worktree. Copying the
wrong variant produced a run with 33% plateau timeouts and a degraded
flow-validation Check D before the mistake was caught by comparing the
plateau endpoint mix and CPU envelope against the archived healthy run.

Discovered on 2026-09-06 during `rq3rob_none_hybrid_0` (Stage 0.2.1, attempt 1).

## Docker Log Growth, the Sep 15 Storage Death, and Container Recreation

Unbounded docker `json-file` logs filled the VM disk and silently killed the
storage tier. The idle lab writes ~730 MB/day of telemetry chatter: the
controllers log DEBUG per topology tick (~335 MB/day each) and the aggregators
logged DEBUG per `/windows` poll (~42 MB/day each). After the last campaign
(2026-08-09) the logs reached ~29 GB, the 75 GB disk hit 100 % around
mid-September, and **both `edge_storage_server` containers aborted (SIGABRT,
exit 134) on 2026-09-15 01:42** (MongoDB abort under a full disk). Docker's
metadata kept listing them `Up 6 weeks` while `docker exec` failed with
"container is not running" — a dockerd state desync masked the death for 11
days. **Never trust `docker ps` alone for storage health: probe with
`mongosh rs.status()` or `docker exec`.**

Built-in fixes (2026-09-26): every script-launched container carries
`--log-opt max-size=100m --log-opt max-file=3` (≤ 300 MB each); the
aggregator runs at `LOG_LEVEL=${AGG_LOG_LEVEL:-INFO}` (set `AGG_LOG_LEVEL=DEBUG`
only while debugging the HTTP window API); controllers keep DEBUG (analyzers
depend on it) and are rotation-bounded only. `/etc/docker/daemon.json` holds
the same defaults; it is **not live-reloadable**, so docker-API-spawned
containers (controller-created dynamic nodes) pick it up only after the next
docker daemon restart.

Recreation procedure (the build scripts are one-shot — `docker run --name`
plus fresh veth pairs — so do not re-run them on a live lab): `docker rm -f`
the container; delete and recreate its veth pair (both ends live inside
container netns; the bridge end belongs to the `ovs` netns); re-add the OVS
port; `docker run` with the script's exact flags plus `--log-opt`; move the
peer into the new netns and re-apply rename/MAC/IP/route via `nsenter` (per
container values in the build scripts). After recreating controllers or
storages: re-point OVS (`ovs-vsctl set-controller`), wait for
`is_connected: true`, then **re-run `bash test_conectivity.sh all` — the ARP
bootstrap is mandatory**, or the controllers' VIP pools stay empty and spam
`pool empty` warnings. Storage containers keep their data volume
(`-v edge_storage_server_*_data:/data/db`) and rejoin as PRIMARY; the
controllers then self-heal any replica-set members listed in the stored config
(non-voting dynamic members are respawned automatically).

Discovered on 2026-09-26 during the VM maintenance pass (RQ1 thesis
preparation).

**Sync note (2026-09-27):** these built-ins were **local-only** until
2026-09-27 — `cloud-vm-rq2` ran its first 8 campaign-probe runs **without**
them (unbounded `json-file` logs; single edge logs ≥146 MB; aggregator at
DEBUG). Synced with the fd fix on 2026-09-27 (`build_network_{1,2}.sh`,
md5 `da479154…` / `6bb54940…`). **Pre-campaign check per host:**
`sudo docker inspect <name> --format '{{.HostConfig.LogConfig}}'` must show
the size/file opts, and the aggregator `LOG_LEVEL` must be `INFO`.

## Edge Server fd Exhaustion (EMFILE) — Silent Lane Outage

Edge servers can exhaust their file descriptors (container `nofile` limit
is only **1024**): expect `OSError: [Errno 24] Too many open files` bursts
at phase transitions / heavy episodes under high load. **Incidence 3 of 8
RQ2-extension probe runs, 2026-09-27:** contingency R2 (×12 232; R2 then
melted — 14–22 % timeouts, p50 33–74 s), B-P1 R2 (×4 088; `edge_server_n1`
went silent and lan1 stopped serving for the rest of the run —
`demand_drop` lan1 = 840/840 timeouts, while the container stayed `running`
and the run exited 0), B-P2 R1 (×10 892 / ×11 101; 149 k dropped/lane,
p50 ~204–213 s, recovered at demand_drop). Seversity ranges from severe
degradation to a permanent lane wedge — both invisible to crash-based gates.

**Detection (add to every run's post-run battery):**
`grep -c 'Too many open files' <run>/service_logs/edge_server_n{1,2}.log`,
plus a per-phase per-lane service-health check — **for BOTH episodes**
(an R1-scoped battery missed the contingency's severe R2 meltdown for a
day). A lane with ~zero completions / all-timeout in a phase, and an edge
log that stops emitting mid-run, are the signatures. No artifact records
fd counts — the log line is the detector.

**Status:** per-run both-episode scan accepted 2026-09-27 (§5.10 D4);
**nofile raise applied 2026-09-27** (`--ulimit nofile=65536:65536`);
**B-P2r verified 0 EMFILE — but the same overload spiral now terminates in
MEMCG OOM instead** (see next section): the fd limit was a proximate
ceiling, not the root cause.

Discovered on 2026-09-27 during the RQ2-extension B-P1 forensic pass.

## Edge Server Overload Spiral — Thread Explosion → MEMCG OOM (post-fd-fix terminal)

With the fd limit raised (65536), the RQ2-extension overload spiral no longer
stops at EMFILE — it now runs to the **512 MB memcg** and the kernel kills the
edge server. Observed in B-P2r (`rq2_ext_b_dbcb_rep`, 2026-09-27 — R1 = the
rate-15 episode running SECOND after the churn-heavy R2): both edges killed
at 07:14:49/50 — `journalctl -k`: `oom-kill:constraint=CONSTRAINT_MEMCG …
task=python3`; `total-vm:43.4 GB`, anon-rss ~255 MB, pgtables ~21 MB per
process; thread indices reached **66 596 / 68 041** in the preceding 5 min
(thread-per-connection pile-up under the client retry jam). `docker inspect`
after: `RestartCount=1` (restart-in-place via `--restart=on-failure`);
post-restart the edges logged nothing — service never returned
(`demand_drop` 0/839 + 0/842). Pre-fix runs hit the 1024-fd ceiling first
(EMFILE) — same spiral, earlier tripwire.

**Detection:** `container_events.csv` `restarting / Restarting (137)`;
`journalctl -k | grep CONSTRAINT_MEMCG`; thread index in the edge log
(`Thread-<N>`); `docker inspect .RestartCount`.

**Status:** **fix applied 2026-09-27** — bounded-concurrency gate in the
edge `app.py` (`_apply_request_concurrency_bound`, `EDGE_MAX_CONCURRENCY=1024`:
the accept loop waits for a free slot instead of spawning unbounded threads;
excess connections queue in the kernel backlog; image `32642cda5693`).
**Verified in `rq2_ext_b_dbcb_fix1`:** gate engaged exactly once per edge
(n1 08:30:00 / n2 08:30:54), fd 0, no OOM, no restarts — **the spiral-death
is eliminated**. But the same R1 episode **still collapsed** — the thread
pile-up was a *symptom*; see the next section for the actual root cause
(per-request O(buffer) `/service_pressure` scan; fix2). **Post-fix2 update
(2026-09-27): the 1024-thread cap was still too generous — in
`rq2_ext_b_dbcb_fix2` the cap filled completely during the data episode and
~1024 × 8 MB thread stacks OOM-killed n1 (`total-vm 8.6 GB`; the request
buffer is only ~50 MB). Fix 3: cap **256** + **1 MB** worker stacks
(`EDGE_THREAD_STACK_SIZE_KB`).**

Discovered on 2026-09-27 during the B-P2r verification run.

## `/service_pressure` O(buffer) Summary Scan — the dbcb R1-Second Collapse

The actual root cause of the dbcb R1 collapse (B-P2r OOM **and** the fix1
jam): the `/service_pressure` summary is **O(retained events) and computed
per request** — `events_since_with_truncation` scans every retained event,
builds a snapshot dict per matched event, then `compute_service_pressure`
runs O(n) stats. With an empty buffer (cbdb — R1 runs first) each call
≈ 0.14 ms of processing. After a **content-heavy episode fills the shared
72 000-event buffer** (content/feed stage request events; dbcb — R1 runs
second), each rate-15 `service_pressure` call (~360 rps/lane) costs tens of
ms of CPU — at 0.6 cores the edge serves ≈ 20 rps ≪ demand →
accepted-connection jam (45 s waits, 92 % CPU pinned, `time_proc`
44 972 ms per window). **Diagnostic signature:** R1 request paths 100 %
`service_pressure`, `time_db ≈ 0`, zero storage leases in R1, steady
~22 rps completions. All 3 dbcb R1s collapsed; all cbdb R1s healthy —
**episode ORDER silently changes the second episode’s per-request cost.**

**Fix (2026-09-27):** short-TTL single-flight cache in
`monitoring_workload_routes.py` (`SERVICE_PRESSURE_CACHE_TTL_S`, default 5 s;
fresh hit serves the cached summary; exactly one refresher; others serve the
previous summary — staleness ≤ TTL accepted for the monitoring payload; `0`
disables). md5 `59a922c9…` → `3d4c1538…`; image `83cf6d973afe`. Verification:
`rq2_ext_b_dbcb_fix2` — **verified: compute-episode per-request handling
collapsed to 0.2 ms and throughput recovered to ~300–325 rps (vs ~22 in the
jam); refresh duty ≈ 1.5 %**. A residual ~10–15 % capacity gap vs the
empty-buffer regime (early-drain backlog + single-run contamination on that
run) is under observation; a clean rerun decides whether it persists.

**Lesson (restart rejoin, 2026-09-27):** a restarted edge server does NOT
rejoin service — after restart-in-place the process re-creates its Mongo
write client but the VIP ping fails for the full 180 s readiness window
(`app NOT ready: MongoDB ping failed within 180s`) and the lane never serves
again (B-P2r both edges post-OOM; fix2 n1 → lan1 dark 23 min). **Any mid-run
restart = lost run (D2); restart prevention is the only practical mitigation
until the rejoin path is understood.** Also: the harness's
`service_logs/*` capture **stops at a container restart** — post-restart
output exists only in the raw `docker logs`; D-gate log scans must not
assume full-run capture.

## Storage Reserve Churn at the Data→Compute Boundary (dbcb) Throttles Delivery

In dbcb-order runs (`rq2_ext_b_dbcb_fix2/fix3`), the compute episode's first
~4–6 minutes deliver only ~170–300 rps while the edge is **idle-fast**
(handler 0.1–0.4 ms, CPU 37–55 %): a *delivery-side* constraint, not an edge
jam. The coincidence is exact: the storage **reserve release/reconfiguration
burst** (dyn-node removals + re-add, replicaset reconfig; see
`node_lifecycle_timings.csv`) fires right at the recovery-gap→compute
boundary (10:13:31–10:14:19 in fix3) — the reserve reacting to the just-ended
data episode — and delivery returns to full rate only after the tier
settles (~4–5 min). **Do not misdiagnose as an edge/thread/CPU problem: check
the storage lifecycle timeline first** (`node_lifecycle_timings.csv`,
`elasticity_events.csv`, `container_events.csv` around the phase boundary).
This is an *elasticity signature of the data-first order*, shared by both
lanes and all arms — within-order comparisons unaffected; across-order
comparisons carry a documented head asymmetry.

Discovered on 2026-09-27 during the fix2/fix3 forensics.

**Lesson:** endpoints reading shared live state must be O(1)-amortized —
cost audits are **per-episode-order**, since a preceding phase can poison the
next phase’s per-request cost through shared buffers.

Discovered on 2026-09-27 (B-P2r + fix1 forensics).

## Image Rebuilds: Preserve Dependency Parity (Build FROM the Frozen Image)

Bake targeted source fixes **from the current campaign image**, never a cold
rebuild. On 2026-09-27 an `edge_server` rebuild re-ran `apt` + `pip` (the
`ubuntu:22.04` base tag had moved since the previous build) and silently
changed deps: `pymongo 4.17.0 → 4.18.2`, `pyzmq 27.1.0 → 27.2.0` (Flask /
Werkzeug unchanged) — comparability with every prior run would have broken.
Caught before launch by comparing `docker history` layer ages (a fresh `pip`
layer = cache miss) + `pip3 list` old-vs-new. **Fix construction used:**
`FROM <previous-image-id>` + `COPY source /source` → only the source layer
changes; deps frozen (image `83cf6d973afe` FROM `32642cda5693`). **Check
every rebuild:** layer ages + `pip3 list` parity + in-image file md5s.

Discovered on 2026-09-27 during the RQ2-extension fix2 build.
