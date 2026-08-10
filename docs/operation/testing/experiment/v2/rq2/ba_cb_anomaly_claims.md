# RQ2 ba_cb Post-Fix Anomaly — Root-Cause Investigation Claims (2026-08-06)

**Status:** Draft claims for reviewer verification. Evidence is on `cloud-vm-rq2`
in the run folders listed below. Not yet accepted.

## Background

The re-gated G2 post-fix per-cell map showed `ba_cb` at 4.40 % episode timeout /
2183 `http=000` rows — 6× worse than `cf_cb` (0.70 % / 925). The first hypothesis
(scale-down removes backends with in-flight traffic → orphaned requests) drove an
Option-A drain fix recommendation, but the controller logs contradict it.

## CLAIMS (each with evidence location)

### CLAIM 1 — The removals were absent-cleanup, NOT orphan-inducing scale-down
- `ba_cb` run `20260806_101147_rq2_g2_ba_cb_postfix/controller_lan2.log` 10:23:01:
  `[scale-down] submitting alert: ScaleDownComputeAlert(... reason='absent')` for
  `edge_server_lan2_dyn1/dyn4/dyn2` — reason is **absent**, not policy scale-down.
- Same run `node_lifecycle_timings.csv`: remove timing `drain_signal_s=0.0`,
  `net_cleanup_s` only, `total_s` 0.35–0.45 — no drain wait.
- Same run `service_logs/edge_server_lan2_dyn1.log` 10:23:01: `/drain` → `Drain
  activated — quiescing with **0 in-flight**`; `drain_complete` ~1 s later.
- **Conclusion:** no in-flight request was orphaned by the removals → a graceful
  drain fix (Option A) would not change these numbers.

### CLAIM 2 — Affected edge servers STOPPED processing client requests mid-episode
- Telemetry is sent per-request (see `source/docker/edge_server/source/telemetry.py`
  + the per-request "Sending telemetry event" log line), so telemetry continuity
  == request-processing continuity.
- `ba_cb` lan2: `dyn1` last telemetry bucket 10:19, `dyn2` 10:16, `dyn4` 10:20
  (grep 'Sending telemetry event' per-minute counts), then silence until the
  10:23 drain. `dyn3` kept serving (telemetry at 10:28, cpu=100 %).
- **Not ba-specific:** `cf_cb` post-fix `20260806_093846_rq2_g2_cf_cb_postfix`
  lan2 `dyn1` last telemetry 09:48:24, `dyn3` last 09:55:22 — same mid-episode
  stoppage under the cf policy too. ba was the worst instance, not the only one.

### CLAIM 3 — The apps were healthy, not hung; requests stopped ARRIVING (VIP/flow)
- `ba_cb` service logs show **0 errors** (grep error|exception|traceback|oom = 0)
  in every lan2 dyn log.
- At 10:23:01–02 the controller `docker exec`'d a NEW connection to
  `localhost:5000/drain` and the app accepted + processed it (access-log line,
  telemetry event, drain_complete) — the WSGI accept loop worked at 10:23.
- The app logs no client-request lines from the silence point to the drain ⇒
  client requests did not reach the WSGI handler ⇒ **routing/flow-delivery issue
  at the VIP/OVS layer**, not an app-process hang.

### CLAIM 4 — Metric sender is non-blocking (refutes sender-induced thread hang)
- `source/docker/edge_server/source/telemetry.py` `ZmqMetricSender.send` uses
  `self._sock.send_json(event, zmq.NOBLOCK)` under a lock, dropping on
  `zmq.Again` — the sender cannot block request threads.

### CLAIM 5 — Absent-marking is a consequence, not the cause
- Controller marks a node absent after ~90 s without telemetry
  (TELEMETRY_TIMEOUT_WINDOWS=18). The lan2 servers' last report ~10:19–10:20 →
  absent at 10:23. Consistent with CLAIM 2 (telemetry stops when serving stops).

### CLAIM 6 — Config-table correction (cf_db) is real and validated
- `cf_db` at 0.15/0.08 (`20260806_111533_rq2_g2_cf_db_postfix`): 22.21 % timeout,
  db 9 s median, 9847 `000`s. At 0.30/0.15 (`20260806_114512_rq2_g2_cf_db_corrected`):
  0.49 % timeout, db 2.3 ms, 291 `000`s. Episode-based config rule confirmed.

### CLAIM 7 — Campaign is NOT ready; the blocker is VIP/flow delivery, not drain
- Mid-episode backend unresponsiveness contaminates compute-bound cells
  (cf_cb 925 `000`s, ba_cb 2183) and is differential across arms. The next
  investigation target is the controller's per-connection flow lifecycle
  (`VIP_SERVER_PER_CONNECTION_FLOWS=1`) and DNAT flow expiry/reprogramming for
  the affected backends — NOT the scale-down drain path.

## OPEN / UNCERTAIN
- Exact VIP/OVS mechanism (why flows to specific backends stop delivering
  mid-episode) — not yet root-caused. This is the next step after verification.
- Whether the stoppage correlates with a controller event (topology republish,
  flow batch, peer_relief) at each server's silence point — partial correlation
  only at this stage.

## Reviewer verification (subagent, 2026-08-06) — draft status maintained

A Reviewer subagent audited these claims against the code + local records
(reviewer had no VM shell access; operator re-verified the VM-dependent points
below after review). Verdicts and corrections:

| # | Claim | Reviewer verdict | Correction / note |
|---|---|---|---|
| 1 | Absent-cleanup, 0 in-flight, not orphan-inducing | **PARTIALLY SUPPORTED** | Mechanism confirmed in code (`main_n1.py` absent branch → `initiate_drain` → `/drain`; `drain_signal_s=0.0` = instant HTTP, not "drain skipped"). VM timestamps re-verified by operator. |
| 2 | Servers stopped processing mid-episode; not ba-specific | **PARTIALLY SUPPORTED** | Per-request telemetry confirmed (`telemetry.py` emits per request). **Correction:** cf_cb dyn1/dyn3 stoppage is *permanent* (last telemetry 09:48:24 / 09:55:22, never resumed) yet cf_cb had 0 removes — cf_cb's nodes were NOT absent-removed, so "same mechanism under cf" is NOT established; ba-cf difference needs the absent-detection logs. |
| 3 | Apps healthy; requests stopped arriving (VIP/flow) | **PARTIALLY SUPPORTED** | **Correction:** the "no access-log lines ⇒ no arrival" inference is invalid (Werkzeug access lines write on completion). The conclusion rests on the stronger 0-in-flight + localhost `/drain`-accepted evidence instead. |
| 4 | Metric sender non-blocking | **CONFIRMED** (code) | `send_json(NOBLOCK)` under lock, `zmq.Again` dropped. |
| 5 | Absent-marking is a consequence; ~90 s | **REFUTED on 90 s** | **Correction: timeout is 180 s** (`CONTROL_TICK_S=10` × 18 windows). Operator re-verified exact last-telemetry times (dyn1 10:19:24, dyn2 10:16:23, dyn4 10:20:25) — only dyn1 fits the 180 s chain to the 10:23:01 removal; dyn2/dyn4 do not → the single-tick removal is NOT cleanly explained by per-node timeout; mechanism still open. |
| 6 | cf_db config correction real | **PARTIALLY SUPPORTED** | Strongly cross-consistent (operator records + run_matrix); raw CSV counts VM-side. |
| 7 | Blocker is VIP/flow delivery, not drain | **PARTIALLY SUPPORTED / OVERSTATED** | "Not ready" well-supported. **Correction:** the named flag is wrong — RQ2 uses `VIP_DATA_PER_CONNECTION_FLOWS=1` + `VIP_HARD_TIMEOUT=60` (the `VIP_SERVER_PER_CONNECTION_FLOWS` flag is RQ3-only, confirmed in env files). Re-scope to RQ2's `VIP_SERVER` per-client flow lifecycle + `VIP_HARD_TIMEOUT=60` expiry/reprogramming. |

**Reviewer bottom line:** the evidence rules out "app busy/orphaning" and
"removals draining in-flight traffic" as the cause of the 10:22–10:23 timeouts,
and points at the client→backend delivery path; the exact mechanism (connection
never established vs established-but-not-flowing vs re-pinned flow) is **not**
established. The claims doc stays **draft** until the absent-detection +
flow-lifecycle logs are read (recommended: hand to the analyzer with VM access).

**Reconciled elsewhere:** `run_matrix.md` §4 `ba_cb` row updated 2026-08-06 to
"mid-episode backend unresponsiveness / VIP-flow delivery — investigation
pending" (replaces the stale "drain fix pending" label).

## Focused analyzer pass (2026-08-06) — mechanism pinned to the data plane

Deep pass over the absent-detection + VIP flow lifecycle on `cloud-vm-rq2`
(both runs). Results:

1. **Churn guard explains the removal timing.** `HOUSEKEEPING_OVERLOAD_GATE`
   ("LAN overloaded (recent) — suppressing absent-cleanup + scale-down") was
   **ON continuously** in both ba_cb (10:12–10:34) and cf_cb (09:39–09:53+).
   → cf_cb's 0 removes are explained: absent-cleanup was suppressed the whole
   run. The ba_cb lan2 removals fired at 10:23:01 during a brief guard lift
   (suppression ticks 6→3 that minute) after the compute load collapsed
   (~10:21:56), so all pending-absent nodes (dyn1/dyn2/dyn4, absent after
   telemetry-stop + 180 s) were cleaned together. The reviewer's "single-tick
   removal unexplained" is resolved.
2. **Dynamic nodes send no heartbeats** (`HEARTBEAT_ENABLED=false` default;
   telemetry.py). Presence == per-request telemetry only → telemetry-stop ⇒
   absent after 180 s. Absent-marking is purely a consequence of the serving
   stop.
3. **Affected servers DEGRADED, not died.** Selection logs show dyn1's
   per-window requests collapsing 359→15→11 (cpu 59.5→3.1 %), dyn2/dyn4 stats
   freezing (req stuck at 234/363). The controller **kept selecting them**
   (dyn1 low-cost-idle; dyn2/dyn4 stale-stats) and kept installing per-client
   DNAT/SNAT flows (RQ2 per-client mode, idle=10 s, hard=`VIP_HARD_TIMEOUT`=60).
4. **The decisive evidence — WSGI threads blocked at the socket-read layer.**
   dyn1's thread numbers jumped Thread-2262 (10:15:59) → Thread-4505 (10:23:01
   drain): ~2242 connections were **accepted** (threads spawned) with **no
   completion logged** (access lines + telemetry write on completion) and
   **0 errors / no slowdown before the stop**. And `/drain` reported
   `active_requests: 0` — so the stuck connections **never reached Flask's
   `before_request`** (they would have been counted). Conclusion: connections
   were accepted at the TCP layer but the **request bytes never flowed through
   to the WSGI handler** → a **data-plane/flow delivery break to those
   backends**, not an app-logic deadlock (the request-hook locks in
   `edge_server_process_state.py` are short and non-reentrant).
5. **`/drain` (docker exec localhost, bypasses the VIP) worked** at 10:23 — the
   app was healthy; the VIP/OVS data path to those backends was what broke.
6. **Hung requests were spread across all 48 clients** (lan1 992 / lan2 908;
   peak 10:21–10:22) — consistent with per-client flow re-pinning distributing
   connections over the degraded backends over time, not one pinned client.

### Updated root-cause statement
The blocker is a **mid-episode data-plane delivery break to individual edge
backends** (VIP/OVS flow path stops delivering request bytes; the WSGI threads
block on socket read; no completion/telemetry → absent → batch-removed when the
churn guard lifts). The controller's per-client selection kept routing to them,
so clients pinned to them hung (300 s timeouts). This is shared across arms
(cf_cb 925 `000`s, ba_cb 2183) and ba was the worst instance.

### Exact mechanism still open (needs a live capture)
Whether the data-plane break is (a) a per-client flow
expiry/reprogramming race, (b) conntrack divergence (SYN-ACK by kernel, data
dropped), or (c) OVS flow state corruption for those backends — cannot be
pinned post-hoc from logs. **Recommended next step:** a live instrumented run
with `ovs-ofctl dump-flows` + `conntrack -L` snapshots and a `py-spy`/thread
stack dump at the stall onset (or `/proc/<pid>/task/*/stack`) to read where the
WSGI threads block (kernel `tcp_recvmsg` waiting vs userspace). Until then the
campaign stays blocked.

**Note:** the earlier "flow-delivery" framing was correct in direction but the
specific flag (`VIP_SERVER_PER_CONNECTION_FLOWS`) was RQ3-only; RQ2 uses
per-client `VIP_SERVER` flows + `VIP_DATA_PER_CONNECTION_FLOWS=1` +
`VIP_HARD_TIMEOUT=60` (verified in env files).

## Live instrumented run (2026-08-06, `rq2_ba_cb_instrument`) — stall NOT reproduced

A live capture loop (10 s poll: per-edge thread count + `wchan` histogram;
full `ovs-ofctl dump-flows` + `/proc stacks` + container logs on a thread-spike
anomaly) ran over a full `ba_cb` run. Results:

- **Result of the run:** timeout **1.67 %** (722), `000`s **1368** — a *milder*
  instance than the earlier 4.40 % / 2183 (p50 3.5 ms healthy).
- **The severe stall did NOT recur:** max thread count was 28 (no 2242-thread
  accumulation), no `anomaly_*` capture fired, and the `wchan` scan showed only
  idle socket polling (`do_select`/`ep_poll`/`do_poll`) with a handful of
  `futex_wait_queue_me` tokens — no `tcp_recvmsg`-block or lock-stall pattern.
- **This run's `000` signature is the ADMISSION-WINDOW type:** concentrated
  early (13:29 spike = episode min 1–2, 0.7 ms fast-fails), correlating with
  `lan2_dyn2` spawning 13:27:32 and stopping 13:28:33 (~1 min), `dyn4` stopping
  13:32:36 — freshly-spawned backends that never integrate properly.
- **Contrast with the severe run:** 3 *established* lan2 servers stopped
  mid-episode (10:16–10:20) → WSGI socket-read stall (2242 threads) → 4.40 % /
  late-episode spike.

### Conclusion on mechanism & variance
The artifact is **intermittent**, with severity driven by how many backends stop
serving and when:
- *Mild* (this run, cf_cb runs): early admission-window fast-fails when a
  freshly-spawned backend never integrates; ~0.7–1.7 % timeout.
- *Severe* (earlier ba_cb run): established backends stop serving mid-episode →
  data-plane delivery break (inferred) → WSGI threads block → 4.40 % timeout.

The severe stall could not be captured live in one attempt (intermittent);
catching it would need repeated instrumented runs. **RQ2 has no readiness gate**
(`READINESS_PROPAGATION` unset — RQ3 has it and masks these admission artifacts),
which is the strongest candidate for a config-level mitigation: admit a spawned
backend to the VIP pool only once it is actually serving.

### Status
**Decision (b) SELECTED, IMPLEMENTED and VERIFIED (2026-08-06).**

Implementation (env-only): `READINESS_PROPAGATION=direct` +
`EDGE_APP_READY_EVENT=1` (+ probe knobs) added to all three arm env files
(`docs/operation/testing/experiment/v2/rq2/env/*.env`, synced to `~/rq2_env/`),
with RQ3 measurement flags (`VIP_FLOW_ISOLATION`, `VIP_SERVER_PER_CONNECTION_FLOWS`,
`EDGE_FLOW_ISOLATION`) left unset so per-client D5 flows are preserved. No code
change, no image rebuild (edge image already carries the `app_ready` code;
controller already has the gate and propagates `EDGE_APP_READY_EVENT`).

Verification — two `ba_cb` runs with the gate on (canonical `rq2_probe_gate.py`):

| Run | episode timeout % | p50 | admission | gate |
|---|---|---|---|---|
| `20260806_141245_rq2_ba_cb_gate` | **0.46 %** (199/43136) | 3.2 ms | 8 admitted / 0 abandoned, all `event` | PASS |
| `20260806_144249_rq2_ba_cb_gate2` | **1.12 %** (485/43138) | 3.4 ms | 8 admitted / 0 abandoned, all `event` | PASS |

vs the no-gate baselines: 1.67 % (mild admission-window) and 4.40 % (severe
mid-episode stall). **The admission-window fast-fail signature is gone** (the
pre-gate 0.7 ms `000`s are absent; all residual `000`s are true 300 s timeouts,
`backend_id=unknown`, clustered at episode min 0–1 and min 8 → 180 s absent
cleanup, 4 removes). The severe 4.40 % / 2242-thread stall did not recur.
Residual intermittent delivery-break timeouts remain but are contained well
under the Block-1 5 % guardrail.

Tooling fix required to run RQ2 with the gate: `run_experiment.sh`'s RQ3
validity gate now applies its RQ3-specific checks (flow-validation,
`EDGE_FLOW_ISOLATION=1`) only when `VIP_FLOW_ISOLATION=1`; readiness-gate-only
runs (RQ2, `VIP_FLOW_ISOLATION=0`) get min-admissions + `EDGE_APP_READY_EVENT`
checks and pass (previously every RQ2-with-gate run was mislabeled failed by the
`EDGE_FLOW_ISOLATION=1` requirement).

**Campaign can now run under the Block-1 5 % guardrail** (ba_cb no longer the
risk cell at 1.67–4.40 %; now 0.46–1.12 %). Options (a) and (c) no longer needed.
