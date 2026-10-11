# RQ2 v4 — Preparation and Findings Record

> **Status:** 2026-10-11 · pre-campaign record for the RQ2 rebuild.
> **Scope:** rebuild RQ2 as a 3 demand-regime × 3 scaling-mode matrix on a
> repaired platform. Supersedes the v3 RQ2 campaign as the evidence base for
> the RQ2 claim; `v3/rq2` and `rq2_extension` remain the record of the
> storage-side mechanism findings and the platform incidents.
> **Sources:** v3/rq2 and rq2_extension records; two read-only autopsies on
> `cloud-vm-rq2` (2026-10-11: compute-demand ceiling; added-replica cull root
> cause); author decisions of 2026-10-11.

---

## 1. The rethought RQ2

**Core.** Understanding where the load rise presses on, and scaling that.

**Design.** 3 demand regimes × 3 scaling modes (capability ablations):

| Demand ↓ / Scaling → | compute+storage scaling (dual) | compute-only | storage-only |
| --- | --- | --- | --- |
| compute-bound | recovers (expected) | recovers (expected) | no relief (expected) |
| data-bound | recovers (expected) | fails to help (expected) | recovers (expected) |
| both (mixed) | recovers (expected) | half unrelieved (expected) | half unrelieved (expected) |

- Scaling modes are **platform capability configurations**: only-compute
  (`MAX_DYNAMIC_STORAGE=0` + reserve off), only-storage
  (`MAX_DYNAMIC_COMPUTE=0`), and both — the knobs already exist
  (mechanism-necessity envs).
- The both mode performs **dual selection**: every tier whose signal fires is
  scaled. Thesis wording: "compute and storage scaling".
- The pattern above is the pre-registered hypothesis set, per cell, not an
  asserted outcome.

## 2. Autopsy findings (2026-10-11)

### 2.1 The compute-demand knee

- The compute tier binds through its **container CPU quota**: ≈50–55 rps/lane
  at 0.15 core; ≈350 rps/lane at 0.6 core. The v3 episode (rate 1.5 →
  36 rps/lane) sat below the knee; rate 2.25 (53.2 rps/lane) crosses it
  (2.0 = 47.9 rps/lane cruises at p50 3.4 ms).
- At the knee the client-observed latency is **connection-level** (quantised,
  ~doubling TCP backoff series 1.8→60 s); handler p50 ≈ 0.2 ms, data-access
  ≈ 0 ms, the concurrency gate never engages, edge CPU ≈ 67 % of quota. The
  per-request CPU beyond the handler is ≈2.3–2.6 ms at 0.15 core
  (thread-per-connection churn + unconditional per-request telemetry
  print/ZMQ; `telemetry.py:319–345`), with the quota throttling the accept
  loop.
- The "300–325 rps" fix-verification figure is a 4×-quota run at its own
  saturation knee — no contradiction with the 2.25 lock.

### 2.2 The liveness/cull self-defeat

- Dynamic nodes carry no heartbeats; liveness = presence in the delivered
  windows; the removal bound is 180 s (`node_registry.py:125–152`;
  `scaling_config.py:103,129,137–142`).
- Empty telemetry windows count as "absent" and also append `overload=False`;
  the churn guard returns **before** the absence detector, so suppression
  freezes presence ages (`main_n1.py:967–973`). Under saturation, telemetry
  blackouts occur (per-request emission is `zmq.NOBLOCK` and silently
  dropped — `telemetry.py:209–213`), so live added nodes age out and are
  **batch-removed mid-episode** (Part C: "not seen for 238–440 s" → all
  added nodes removed; Part D fallback: cull ×7 → the 2.5 treatment never
  unlocks).
- Assignment concentration (per-minute load rotation) feeds the loop and
  dilutes relief; the culls are systematic, not lane-selective. The cull is a
  self-inflicted capacity loss under saturation and a POST-window
  contaminant.

### 2.3 Fix plan (approved 2026-10-11)

1. Code (minimal): refresh presence on telemetry receipt outside the churn
   guard; do not derive absence evidence (nor `overload=False`) from
   empty/meta windows; enable heartbeats on dynamic containers.
2. Config belt (mitigation only): `TELEMETRY_TIMEOUT_S` raise — already in
   place (600 s) on the canonical override.
3. Fix-verification battery (before the campaign): ladder `none` / `comp` /
   `stor` at 2.25 and 2.5, one regime-shift run, and a data-bound
   re-anchor pair (9 gate runs); plus a 4-run RQ1 delivery-mode smoke set
   (`rq2v4_transport_*` deltas) re-proving mode producibility on the fixed
   build — 13 runs total. Full retention + 1 Hz host sampler; gates — no
   culls, no removal of added units, both-lane relief, treatment unlocks.
   The full gate list is `rq2v4_plan.md` P1.4.

### 2.4 RQ1 interaction (audited 2026-10-11)

Read-only audit of all 12 archived RQ1 delivery runs
(`source/scripts/testing/metrics/2026080*_rq1_delivery_*`): zero scale-down
decisions at demand above 10 % of each run's peak window — every removal
sits in the post-drop reclaim phase and is absence-driven (absent rows ≈
scale-down rows; e.g. ep_1 70/70, sp_1 125/125, ls_2 215/215). RQ1's
load-rise measurements are therefore unaffected; its teardown behaviour was
the pre-fix absence path, which the repair replaces with heartbeat-backed
liveness. Decision D9: archived results stand as the pre-fix record; the
smoke set re-proves mode producibility; teardown replication is parked.
Full write-up: `rq2v4_p1_01_liveness_fix.md` §12.

## 3. Decisions log

| # | Decision | State |
| --- | --- | --- |
| D1 | Scaling modes = capability ablations (knobs exist) | approved 2026-10-11 |
| D2 | The both mode = dual selection; wording "compute and storage scaling" | approved 2026-10-11 |
| D3 | New compute-heavy request kind (hashing on the edge), configurable work factor | proposed 2026-10-11; to implement |
| D4 | Compute-bound rate ≈ 2.5 per client | proposed; re-verify under the fix |
| D5 | Replicates: 7 per cell (standardised with RQ1's seven) + no-action comparators | approved 2026-10-11 |
| D6 | The mixed "both" regime = single simultaneous episode (both knees co-placed by calibration) | constructible; recipe in §4; calibration before the campaign |
| D7 | Regime-shift sequence (compute→storage, storage→compute in one run) | candidate v4 extension after the core matrix validates |
| D8 | Tier-1 held off in all v4 modes (`SS_ENABLED=0`) so no un-evaluated spawn path escapes the ablation; verify v3 RQ2 Tier-1 activity at P1.2 | proposed 2026-10-11 |
| D9 | RQ1 interaction: archived results stand as the pre-fix platform record; the fix changes teardown semantics only (audit §2.4); the 4-mode smoke set re-proves producibility on the fixed build | recommended 2026-10-11 |

## 4. Mixed-regime construction (design answer)

A single episode can press both tiers simultaneously: each tier binds when its
own share of the stream exceeds its own knee. Construction levers: hash work
factor (tunable per-request compute cost), mix weights, per-tier quotas, and
total rate — chosen so that hash-rate × cost exceeds the edge quota and the
lookup rate exceeds the member knee, with both tier signals firing.
Calibration via the established bracket method. The sequential variant
(compute episode then storage episode in one run) is a **different
treatment** — "one configuration across a moving regime" — planned as D7
rather than a substitute for the mixed row.

## 5. Next steps

1. ~~Draft the minimal fix diff for review~~ ✅ (no VM touch before approval —
   done; approved and implemented 2026-10-11).
2. Run the fix-verification battery (13 runs: 9 gates + 4 RQ1-mode smokes)
   on `cloud-vm-rq2`.
3. Implement the hashing request kind (+ generator support; the demand-model
   table grows to six kinds).
4. Calibrate the mixed regime; re-anchor the compute-bound rate.
5. Freeze the v4 experiment plan (treatments, gates, replication,
   counterbalancing, blocks) and run the campaign.

## 6. Provenance

- Autopsies: read-only passes on `cloud-vm-rq2`, 2026-10-11 (compute-knee and
  era table; cull root cause).
- Author decisions: 2026-10-11 (scaling modes, dual wording, hashing kind,
  v4 recording).
