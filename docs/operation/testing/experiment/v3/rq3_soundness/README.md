# RQ3 Soundness — Plain-Language Guide

*Recorded 2026-10-03 at P1 lock, so the campaign's purpose is clear without
reading the full plan. This wording is the campaign's reference summary.*

## The question, in one sentence

**Can the platform's admission rules tell whether a new server is *actually
ready* — and what happens to user traffic when they can't?**

## Why it matters — the three ways the "ready" signal can be wrong

A new backend announces *"I'm ready, send me traffic."* The platform has three
ways to react:

1. **`event_only`** — believe the announcement (trust the call).
2. **`hybrid`** — believe it, with a backup timer.
3. **`reconcile`** — don't believe it; probe the server and admit only if the
   probe passes (an inspector).

The announcement can be wrong in three ways:

| Fault | What happens | Consequence |
| --- | --- | --- |
| **F1 — lost claim** | The server is ready but the call never arrives | Ready capacity stays **unused** (dark) |
| **F2 — premature claim** | The call arrives 2/5/10 s **before** the server can serve | Whoever trusts the call sends traffic to a server that isn't serving yet → **failed requests** |
| **F3 — semantic lie** | The server answers "ready" but **serves errors** for a while | Even a probe passes — it checks that the server *answers*, not that it *works* → **failed requests** |

So the campaign evaluates, per admission rule: the consequences of **admitting
and using a server that is not actually ready** (F2/F3), and of **failing to
use one that is** (F1).

## How the "ready" state is generated and propagated (plain mechanics)

On each edge server:

1. **The condition**: the server marks itself ready only after (a) it has
   bound its socket (it can accept connections) and (b) a real MongoDB
   round-trip succeeds. `/ready` then answers 200. That is all "ready" means
   here — it says nothing yet about whether requests will succeed.
2. **The push path (event)**: if enabled (`EDGE_APP_READY_EVENT=1`), the
   moment the flag flips the server sends a small `app_ready` message —
   `{event_type, server_id (MAC), ts}` — down its **normal ZMQ telemetry
   pipe**: edge server → aggregator → controller. The controller's readiness
   gate receives it and (in event-driven mode) admits that backend
   immediately. The event is the evidence.
3. **The pull path (probe)**: in discovery/reconcile mode nobody is pushed
   anything; the controller asks the server directly (`GET /ready`, every
   ~10 s) and admits it when a probe succeeds. The probe is the evidence.
4. **Backup timer**: in event-driven mode, if no event arrives within
   `READINESS_EVENT_FALLBACK_S`, the controller falls back to probing (or, in
   `event_only`, gives up — its timer is deliberately set beyond the probe
   limit).

So "propagation" is literally: **a message over the metrics channel (push) or
an HTTP poll (pull)**, sent after the server's own "I'm ready now" condition
fires — and the controller only listens for servers it just spawned.

## The faults, mapped onto those mechanics

- **F1 — the message is dropped / never arrives.** The controller waits; the
  fallback timer decides the fate. `event_only` has no working fallback →
  capacity stays dark.
- **F2 — the message fires too early** (before the socket can serve). Whoever
  trusts the message admits a not-yet-serving server; whoever probes waits for
  real servability and is immune.
- **F3 — nothing is broken in the message or the probe, but the service
  fails** (the server answers "ready" and then serves errors). Both push and
  pull evidence pass; the lie is visible only in request outcomes — "the
  channel is verified" ≠ "the service is truthful".

## Relevance & realism — "isn't this artificial?"

The faults are *generated* deterministically (by design), but the fault
*classes* are real phenomena — observed here and named in the field:

- **F2 (premature claim) is an actual, recorded bug in this codebase** — the
  pre-2026-08-06 ordering where the readiness event preceded servability by up
  to ~10 s (http=000 fast-fails, identity-check violations, admitted→first-flow
  lag; it also contaminated RQ1/RQ2 runs). The campaign re-introduces it
  *deterministically* so the consequences can be measured as a function of
  lead time (2/5/10 s) — impossible with an intermittent natural bug.
  Generalizing: readiness that fires before a node is *useful* is the norm
  (runtime warmup, lazy connection pools, slow mounts) — the reason Kubernetes
  added `startupProbe`/`minReadySeconds` and Istio a `slowStart` mode.
- **F3 (semantic lie) is the classic "gray failure"**: the process is up and
  the health endpoint passes, but the service is failing (broken dependency,
  degraded replica, wrong config). This platform has its own instances: lanes
  going silent while the container stayed `running` (the EMFILE / thread-spiral
  incidents — the run exited 0 while lan1 served nothing), and storage
  containers Docker listed as "Up 6 weeks" that had actually been dead for days.
- **F1 (lost claim)** travels over the ZMQ telemetry channel (edge →
  aggregator → controller) — the exact path that degrades during the load
  spikes that trigger scale-ups in the first place (the fault coincides with
  the event that forces scaling).

What is deliberately artificial is only the **dose** — deterministic leads and
a lie window spanning the plateau — i.e., boundary testing. The deliverable is
a design rule: *if the readiness signal can be early by more than N\*, trust
costs X pp of requests; verification fixes timing but cannot fix content at
any dose.* The headline asymmetry (probe survives F2, not F3) is
**structural** — it follows from what each check verifies — and therefore does
not depend on the chosen magnitudes.

Ties to common use cases: the compared rules are the platform's own deployed
modes and archetypes of real deployment choices (trust / trust+fallback /
poll-verify / wake+verify); admission is this platform's hot path (every run
spawns 4–5 nodes; ≈17–21 s spawn→admit); and at the edge — cheap,
slow-warming nodes on flaky links — "can admission tell truth from timing
luck?" is precisely where capacity realization succeeds or fails.

Scope statement: mechanisms are workload-independent; magnitudes are
regime-specific and reported as boundary bounds (not field-frequency
estimates).

Candidate literature to vet (propose–approve before citing anywhere):
gray-failure (observer-vs-truth) literature — e.g., Huang et al., "Gray
Failure", HotOS 2017 — and Kubernetes readiness-probe semantics / slow-start
practice.

## What the campaign measures

- **Damage**: the share of requests that fail or crawl, compared against the
  same-seed no-fault run (`D_s = U(fault) − U(none)` in percentage points).
- For every {admission rule} × {fault type}: how much user-visible damage each
  rule takes, per seed (3 seeds per cell).
- The **"how early is too early" curve** (lead N = 2/5/10 s) and where
  trusting-the-call stops paying off versus probing (`N*` crossover).

## Expected headline (pre-registered)

**No existing rule survives all three fault types.** Trust-based rules fail
F1/F2; probe-based verification fixes *timing* but not *lying* — `reconcile`
passes F2 yet fails F3. In one line: **"the channel is verified" ≠ "the
service is truthful"** — the platform needs admission that verifies service
correctness, not just liveliness.

## What "complete" means (execution scope, 2026-10-03)

- **P1 preflight**: done — R1 (`_90r`) / R2 (`_91`) / R3 (`_92`) all gates
  pass, **lock written** (`analysis/rq3snd_preflight_lock.json`); optional
  R3b (`_93`) included for completeness.
- **E stage**: 45 core runs (3 seed-blocks × 15) + 15 optional runs
  (`wake_verify` arm ×3 cells, `loss_all` push anchor, `semantic×hybrid`
  descriptive) = **60 runs**, ≈ 35 h of sequential VM time (user approved:
  storage verified, time not a constraint).

## Status ledger

- 2026-10-02 — P1 attempt 1 (`_90`) STOP: bind-timing artifact (blocking DNS
  lookup) → instrument fixed (tag `rq3snd-preflight-20261003`, image
  `207b1f9e8f64`).
- 2026-10-03 — P1 certified: R1r/R2/R3 pass; lock written; canonical
  `phases.json` restored; plain-language wording recorded (this file).
- 2026-10-03 — complete campaign starting: R3b + 60 E runs; execution tracker
  in [`e_stage_log.md`](e_stage_log.md).
