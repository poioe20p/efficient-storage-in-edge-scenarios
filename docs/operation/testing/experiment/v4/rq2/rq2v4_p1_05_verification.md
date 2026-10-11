# RQ2 v4 — P1.4: Fix-verification battery (results)

> **Status:** 2026-10-11 · battery run complete (5/5 valid). Gates (a)/(b)/(e)
> pass, (d) passes episode-scoped, **(c) is not evaluable as pinned — and its
> un-evaluability is itself the finding: the 2.5 rung no longer presses on the
> repaired platform** (press re-anchor moves to P2/P3 as planned). One latency
> anomaly found, leading hypothesis recorded below.
> **Artifacts:** run folders on `cloud-vm-rq2` `source/scripts/testing/metrics/`
> (full retention); VM HEAD `4591a4c`; aggregator image
> `sha256:2e173ce66324…` (lockstep asserted).
> **Companion:** [`rq2v4_p1_01_liveness_fix.md`](rq2v4_p1_01_liveness_fix.md)
> (§11 pins), [`rq2v4_plan.md`](rq2v4_plan.md) (P1.4), [`preparation.md`](preparation.md).

## 1. Deployment + lockstep (P1.3)

- Checkout synced to `4591a4c`; `local_state_server` image pre-built, deployed
  as-is (nothing else rebuilt). Aggregator container image id verified equal
  to the build (both LANs), post-deploy and post-battery.
- Mounted controller code contains `request_evidence`
  (`main_n1.py`, `main_n2.py`, `telemetry/models.py`, `node_registry.py`).
- Idle probe: 155 s of windows at 10 s cadence, all carrying
  `request_evidence`; 7+7 windows with `heartbeat_only: true` entries;
  zero tracebacks in either controller log. **Smoke clean.**

## 2. Battery results (seed 42, 5/5 valid, full retention)

| Run | Folder | Culls | Absent rows | scale_up/down | Max consec empty (global / episode) | Zero-lat anomalies |
| --- | --- | --- | --- | --- | --- | --- |
| `none_cb25` | `20261011_160335_rq2v4_p1_none_cb25` | 0/0 | 0 | — | 28/24 / **0/0** | 0 |
| `comp_cb25` | `20261011_164429_rq2v4_p1_comp_cb25` | 0/0 | 0/0 | 10 / 3 (post-episode) | 33/29 / **1/0** | 0 |
| `stor_cb25` | `20261011_171600_rq2v4_p1_stor_cb25` | 0/0 | 0/0 | 4 / 2 (post-episode) | 33/30 / **0/0** | 0 |
| `none_db` | `20261011_174715_rq2v4_p1_none_db` | 0/0 | 0 | — | 32/28 / **0/0** | 0 |
| `stor_db` | `20261011_181427_rq2v4_p1_stor_db` | 0/0 | 0/0 | 9 / 7 (post-episode) | 33/29 / **0/2** | 0 |

Assignments: every added unit served requests (comp: all 10; stor_cb: 2/2
storage; stor_db: 7/7 storage). Envelope verified live for the db pair
(edges 1.20 CPU / storage 0.15).

**Gate verdicts**

- **(a) zero culls — PASS** (all runs; 0 `triggering removal` lines).
- **(b) no removal of added units across episode + margin — PASS.** All
  scale-downs occur after the demand fell (post-episode: comp 16:58–17:04,
  stor 17:29–17:30, stor_db 18:25–18:28 — during recovery/demand-drop), via
  the graceful policy path (no absent-typed rows exist at all). Margin
  definition to keep: "episode end → first recovery window".
- **(c) comp@2.5 relief + unlock — NOT EVALUABLE AS PINNED; press too weak
  post-fix.** The action fires **+21 s into the episode** (first scale_up
  16:46:23; episode start 16:46:02), so the pinned pre-add window
  (add−180…add) is dominated by off-press baseline and the pinned lock
  test finds no lock (p95 ≥ 1 s in only 44 %/22 % of pre windows). Worse for
  the campaign: **`none`@2.5 does not lock at all** — client p95 86 ms,
  edge CPU ~80 %, 100 % completion over the whole 10-min press. A single
  static edge at 0.15 core absorbs 2.5 · 1.5 clients cleanly. The rung is
  below the post-fix knee.
- **(d) no more than 2 consecutive empty windows — PASS episode-scoped**
  (0/0, 1/0, 0/0, 0/0, 0/2 during episode+margin). Global counts (28–33)
  occur only in the near-idle recovery/demand_drop phases (0.5 rps × 5 %
  clients ⇒ genuinely no traffic; `request_evidence:false` is correct
  there). Recorded scoping decision: gate (d) is an episode-scoped gate.
- **(e) assignments + no zero-latency poisoning — PASS.**

## 3. Finding F1 — press re-anchor (moves to P2/P3)

Post-repair, rate 2.5 is a *clean, served* press: `none` completes every
request at p95 86 ms. The v3-era knee (~50–55 rps/lane at 0.15 core) was
measured on the pre-fix platform whose self-harm (culls/churn) inflated the
apparent press. Consequences:

- The campaign's compute press must be re-derived on the fixed platform —
  P2's hashing kind + knee calibration now carries this (make the ladder
  start **above** 2.5, e.g. 3.0/3.5/4.0 brackets, and require the none-arm
  to lock before declaring a rung the campaign operating point).
- D4 ("compute-bound rate ≈ 2.5") is superseded by that calibration.

## 4. Finding F2 — latency bursts (recorded, leading hypothesis)

`comp_cb25`: two latency bursts — 16:50:02–16:51:02 (706 slow requests) and
16:55:02–16:56:34 (p50 1.5 s, 4 138 slow of 7 106; 192 client timeouts,
status 000, sent 16:48–16:51). Concentrated on 3 of 10 dynamic units
(`edge_server_lan1_dyn2`, `lan2_dyn4`, `lan2_dyn5`: p95 1.35–3.1 s) while
their quotas were **not** saturated in the burst windows (CPU 34–73 % of
quota) and their LAN peers were clean (p95 13–24 ms). The signature is
connection-level (quantised values; `now already known` from autopsy #1:
TCP retransmit series), i.e. the delay precedes the unit.

Leading hypothesis: **host-side interference during the episodes** — the
testbed is single-host; disk/CPU-heavy host activity (monitoring, artifact
collecting, scans by the harness/user during the run) starves the client /
punt path. Corroborating: `none_cb25` (whose episode ran in a quiet period)
shows a flat p95 30–217 ms; the bursts coincide with known host-activity
windows. Not proven; needs one confirmation (below).

Also recorded (measurement note): assignments **rotate per window** — each
window one unit per LAN serves ~600 req at 60–90 % of quota, alternating
units across windows. Relief metrics must use the **serving unit's** CPU
per window, not the fleet mean (fleet means understate the hot unit; e.g.
comp lan2 fleet mean 47.7 % while the serving unit ran at 60–96 %).

## 5. Consequences for the campaign (carry into P4)

1. **Passive-monitoring protocol hardened:** no host-side heavy commands
   (scans, `du`, greps, artifact collects) while an episode is running;
   evidence collection strictly between runs. The comp-run bursts are the
   cautionary precedent.
2. **Confirm F2 once**: the P2 knee calibration will run saturated episodes
   anyway — hold host activity to zero during them and check whether burst
   signatures reappear (if absent → F2 = host interference; if present →
   reopen as a platform finding before P4).
3. **Pin in P4:** `TELEMETRY_SOURCE` explicitly (battery inherited the
   controller default `zmq`; the v3 RQ2 era ran `event_preserving` —
   decide consciously) and `SCALEUP_POLICY` explicitly (battery ran the
   default "dual" → 5-column decision logs; v3 RQ2 arms logged 20-column
   rows with per-tier evidence columns — decide what the v4 analysis
   needs).
4. **Relief metric definition** (F2 note): serving-unit-scoped.
5. **Re-anchored compute gates (replace the dead (c) pin):** defined in
   `rq2v4_p2_01_hash_kind.md` §5 — (i) press gate: `none` locks (p95 ≥ 1 s
   in ≥ 80 % of episode windows, completion degrades); (ii) relief gate:
   same-shape `comp` recovers both sides and stays recovered; (iii) margin:
   `none` stays locked (no borderline drift); (iv) specificity: `stor` does
   not clear the compute lock; (v) hash cost dominates the overhead split.
   P2.3 seats the rate; P4 inherits the gate set as the campaign's
   manipulation checks.

## 6. D8 (closed)

v3 RQ2-era folders checked: `SS_ENABLED=0`, zero selective_sync /
selective_storage rows. Tier-1 was never engaged in v3 RQ2; the v4
`SS_ENABLED=0` pin matches the historical configuration. D8 **approved**.

## 7. Provenance

- Battery executor: VM harness session 2026-10-11 15:41–18:36 Z
  (deploy 15:41, runs 16:03–18:36, `phases.json` restored identical).
- Analysis: main session, host-local parse of pulled window logs / decision
  logs / client CSVs (scratch files under `temp/`, deleted after the report
  round).
- Disk on VM: 74 G → 71 G free (full retention kept).
