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
3. Fix-verification battery (before the campaign, lean core): compute-bound
   at the hard rung (2.5) × `none`/`comp`/`stor`, plus the data-bound
   re-anchor pair (`none`, `stor`) — 5 runs. Optional add-ons only if a
   gate needs disambiguation: the 2.25 rung and the regime-shift run. Full
   retention + 1 Hz host sampler; gates — no culls, no removal of added
   units, relief + unlock, no stat poisoning (full list: `rq2v4_plan.md`
   P1.4).

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
| D3 | New compute-heavy request kind (hashing on the edge), configurable work factor | **implemented 2026-10-11** (P2.1: `/compute/hash` + `hash_challenge`; selftest green; ≈26 ms/request at the default) |
| D4 | Compute-bound rate ≈ 2.5 per client | **superseded 2026-10-11 by F1**: 2.5 no longer locks on the repaired platform (none p95 86 ms); the press is re-anchored by the P2 knee calibration (ladder above 2.5, none-arm must lock) |
| D5 | Replicates: 7 per cell (standardised with RQ1's seven) + no-action comparators | approved 2026-10-11 |
| D6 | The mixed "both" regime = single simultaneous episode (both knees co-placed by calibration) | constructible; recipe in §4; calibration before the campaign |
| D7 | Regime-shift sequence (compute→storage, storage→compute in one run) | candidate v4 extension after the core matrix validates |
| D8 | Tier-1 held off in all v4 modes (`SS_ENABLED=0`) so no un-evaluated spawn path escapes the ablation; verify v3 RQ2 Tier-1 activity at P1.2 | proposed 2026-10-11 |
| D9 | RQ1 interaction: archived results stand as the pre-fix platform record; the fix changes teardown semantics only (audit §2.4); mode producibility holds by construction (additive fields); any RQ1 re-proof is RQ1-owned and parked | recommended 2026-10-11 |
| D10 | Compute relief not demonstrable under a real press (P2.3: comp engaged fully, lock persisted — traffic concentrates one-unit-at-a-time). P2.5 read-only diagnosis opened; seat freeze deferred; fallback = author decision on re-scoping the compute claim | **narrowed 2026-10-12**: root cause = the 60 s one-hot funnel; P2.6 ε-spread broke the timeout regime (comp timeouts 229 → 0) but band collapse kept relief failed (P2.7 verdict, knee §6) → P2.8 band floor; **resolved 2026-10-12**: P2.8 verified — mechanism gates pass, steady-state relief both lanes (artifact §6); re-scoping fallback not exercised |
| D11 | Spread band floor `_BACKEND_SELECTION_SPREAD_MIN_BAND` (default 4): the band (candidate set) is topped up to ≥ min(k, eligible locals) members with the cheapest eligible local units (finite cost, known IP, not peer, slow-start penalty fully decayed) so a strict single winner cannot take a burst once at least two eligible locals exist; fan-out is hash-determined from that band; keeps ε-band + warm-share semantics, peers stay ε-gated | approved 2026-10-12 (P2.8, [`rq2v4_p2_08_band_floor.md`](rq2v4_p2_08_band_floor.md)); **verified 2026-10-12** — re-seat `_v3`: band=4 every steady-state burst, all members seated, 3–4 concurrent servers sustained, stor specificity held (artifact §6) |
| D12 | Relief definition re-anchor: campaign relief gate = post-engagement steady state (first floor-complete burst → episode end) + time-to-relief recorded as a measured endpoint of compute cells; the pinned [add+30, +180] window measured the platform's re-selection cadence (first floor-complete burst ≈ add+177 s), not the repair | approved 2026-10-12 (P2.8 verdict, [`artifact`](rq2v4_p2_08_band_floor.md) §6); seat frozen (R_s = 0.20, hash 25000, quota 0.15, caps 6/6) with this definition |
| D13 | Mixed co-press construction: ladder v1 (rungs 1.0/1.15/1.3 + pre-authorized `edge020`) **all failed leg (iii)** — member CPU pinned ≈25 %, invariant to rate (19→37 lookup rps), member quota (0.08→0.10) and edge quota (0.15→0.20): the edge caps lookup delivery, so the member cannot be rate-pressed at 0.08 (mixed regime is edge-delivery-limited at the frozen seat — finding recorded in the study §6). **Option A approved**: member-quota rework `STORAGE_CPUS` 0.08→**0.05** (the designated balancing lever; per-regime quotas = v3 precedent) + one confirm rung at 1.15, then pilots; comparability caveat (mixed@0.05 vs data-bound@0.15) recorded for P4 | approved 2026-10-12; **done 2026-10-12**: confirm rung PASSED all four legs (member 40.2/38.6 %); pilots `mx_both` ✓/✓, `mx_comp` ✓/✓, `mx_stor` ✓/**✗** (study §7) |
| D14 | Storage-relief criterion re-anchor: judged on the busiest pre-add member's own-peak CPU (< 0.75 in ≥ 80 % of post-ready windows); activated-member read shares reported (sampled counters), never gated — the v3-era single-member ≥ 40 % rule is structurally wrong for multi-member splits. Under D14: `mx_both` ✓/✓ (82.0/95.7 %), `mx_stor` ✗/✗ (3.9/0.0 %) | approved 2026-10-12 (P3 pilots, study §7); carried into the P4 campaign gates |
| D15 | P4.3 sign-off: campaign plan **frozen** — R1–R16 approved as recommended; **R4** db re-anchor preflight approved (2 runs, seed 42); **R12** per-read attribution parked post-campaign; **R15** F2 confirmation carried into P5.1 (host sampler + first-block review); 84-run matrix, seeds 42–48, pins `rq2v4_p4_pins.env` (dual + zmq) | approved 2026-10-12 (author: "i approve proceed"); P5 preflight + campaign start authorized |
| D16 | First-block ordering gate (author directive): after each regime's first 4-run block, the ordering must hold on episode completion + p50 — aligned mode(s) (`both` ≈ the regime-aligned single) beat `none` ≈ the misaligned single; for db additionally the edge CPU must sit well below the member CPU (the storage press must not be compute-impeding). Violation → stop + report. Status: cb seed-42 block ✓ (both/comp 100 % @ 0.16–0.21 s vs stor/none 98.7/96.1 % @ 2.2–2.6 s); **mx seed-45 block ✓ (both/comp 99.2/98.8 % @ 0.009–0.010 s vs stor/none 75.7/71.7 % @ 9.2–10.0 s)**; **db preflight ⚠ — `stor` ≈ `none`** (91.3 vs 93.5 %; edge mean 39 %, member 68–74 % ⇒ edge not binding) — read-only investigation scheduled before the db blocks | directed 2026-10-13; investigation open |
| D17 | P5.1 preflight **PASS** (db pair: `none` MC1 member 66.8/68.5 %, completion 92.9/94.0 %; `stor` engagement OK — reserve activations 3/5) → campaign executed autonomously via VM driver (`campaign_driver.sh` + `chain_db.sh`, auto-phases install/restore, `CAMPAIGN_DONE` marker). Deviations (all no-impact): plan-referenced `rq2v4_p1_04_host_sampler.py` absent from repo → substitute `~/rq2v4_battery/host_sampler.py` at 1 Hz; one accidental duplicate launch killed during setup (no folder/rows); driver batch-file stdin bug fixed after one affected-but-valid run; transient ssh drop | preflight 2026-10-12/13; campaign running; sampler substitution to be reconciled in P6 records |
| D18 | **Read-path pinning finding** (P5.2, [`rq2v4_p5_02_read_path_pinning.md`](rq2v4_p5_02_read_path_pinning.md), registered 2026-10-14): storage reads move ONLY through new connections — per-connection pins are never re-selected; during a fixed-edge press, connection births ≈ 0, so members admitted mid-press receive no reads (`stor_db` 6 births all pre-activation, 99 % pinned; `mx_both` relief came from new edge containers' pools — 36 births, all to new members). Consequences: `stor`@db/mx relief is structurally impossible while the edge set is fixed (report as measured no-relief + this cause); `both` storage relief is downstream of compute spawn (tier-coupling asymmetry for the thesis narrative). Handling: no mid-campaign change; post-campaign fix candidates parked (proactive re-pin / pool renewal / per-request selection) | registered 2026-10-14; db regime running |
| D19 | **db campaign incidents + resume** (2026-10-14): (a) `both_db_43` **excluded** §5.5(iii) — F2 host-interference signature (lan1 black-hole; host sampler load 16.4/busy 94 %; lan2 clean); plan-sanctioned replacement `both_db_43_r1` queued. (b) `comp_db_46` **excluded** §5.5(i) — mid-run crash: `edge_server_lan1_dyn1` **OOM-killed** (`OOMKilled=true`, exit 137, 256 MB container cgroup cap; dmesg cgroup-OOM) at 16:01:22Z; the 16:11:21Z `not seen for 608s — triggering removal` line is the CORRECT absence-cleanup of the dead unit (P1 fix intact) but tripped the driver's `culls_nonzero` halt rule → batch halted at 16:17Z with 14 runs pending; `chain_db.sh` exited without restoring phases (phases left at db state — used as-is for the resume). Replacement `comp_db_46_r1` queued. (c) Batch **resumed 18:24:17Z** (`batch_db_rest.txt`, 16 rows = 14 pending + 2 replacements; driver detached; verified single run tree, no duplicate processes/containers after a 15 s `missing_folder` false-start at 18:22:53Z that left no orphan). Per-run dyn-container OOM check added; escalation if db exclusions exceed 4 | registered 2026-10-14; resumed batch in flight |
| D20 | **db OOM class + author n=7 decision** (2026-10-15): kernel-log re-audit found **6 OOM kills across 5 db runs** (journalctl; invisible to `container_events`): `both_db_43` (n1 11:56 + dyn3 11:58 — **reclassified (iii)→(i)**, the F2 sampler "load" was routine db workload), `both_db_43_r1` (n1 00:12; 42.9 % completion → **excluded too**), `comp_db_46` (dyn1+dyn2; replaced clean by `comp_db_46_r1`), `stor_db_48` (n1 21:03), `none_db_42` (n1 23:50). Pattern: the **static lan1 edge server (256 MB cap)** OOMs under the v3-carried lookup shape; not host memory. Escalation fired (>4 exclusions regime rule; replacements withheld) → **author decision: n=7 mandatory; option 2 chosen — three top-up replacements authorized**: `rq2v4_both_db_43_r2` (seed 43, third attempt), `rq2v4_stor_db_48_r1` (seed 48), `rq2v4_none_db_42_r1` (seed 42) — restoring both/stor/none@db to n=7 (comp@db already 7). One-shot rule: any top-up that fails → stop + report, no auto-retry. Author exception to §5.5's >4 stop recorded. Spares used after top-ups: 5 of ≤14 | approved 2026-10-15 (author: "No n has to be 7 — so 2 is what I choose"); **executed 2026-10-15/16 — all three top-ups valid** (`both_db_43_r2` 99.2/99.2 % completion, `stor_db_48_r1` 90.2/90.4, `none_db_42_r1` 89.8/91.9; kernel OOM sweeps clean; status CSV 91 rows = 84 valid / 5 excluded); all db cells at **n=7**; P5 closed |

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
2. ~~Run the fix-verification battery~~ ✅ (2026-10-11, 5-run lean core;
   results in `rq2v4_p1_05_verification.md`: repair verified — zero culls /
   absent-cleanups / poisoning; press re-anchor to P2 per F1; F2 latency
   burst to confirm under host quiescence).
3. ~~Implement the hashing request kind~~ ✅ (2026-10-11, P2.1 implemented +
   selftest green; build + calibration next).
4. ~~Calibrate the mixed regime; re-anchor the compute-bound rate~~ — the
   compute seat is seated (R_s = 0.20) but its **relief is unresolved**
   (P2.5 diagnosis running; see `rq2v4_p2_02_knee_calibration.md`). Mixed
   regime (P3) waits on the relief resolution.
5. Freeze the v4 experiment plan (treatments, gates, replication,
   counterbalancing, blocks) and run the campaign.

## 6. Provenance

- Autopsies: read-only passes on `cloud-vm-rq2`, 2026-10-11 (compute-knee and
  era table; cull root cause).
- Author decisions: 2026-10-11 (scaling modes, dual wording, hashing kind,
  v4 recording).
