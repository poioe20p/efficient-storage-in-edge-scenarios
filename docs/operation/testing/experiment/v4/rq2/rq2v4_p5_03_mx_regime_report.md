# RQ2 v4 — P5.3 mixed (mx) regime report

> **Status:** mx regime **closed — 28/28 runs valid, 0 spares used**. All
> numbers below are as-measured; **cell-level verdicts are pending P6
> (analyzer)** per the campaign division of labour. Authored 2026-10-14 by
> the campaign close-out operator while the db batch ran (read-only
> analysis; no driver, run, or config touched; no run-folder writes).
> **Config (frozen seat):** `R_m = 1.15`, `EDGE_CPUS 0.15`,
> `STORAGE_CPUS 0.05`, mix `0.205 hash / 0.795 lookup`,
> `HASH_WORK_FACTOR 25000`, `SCALEUP_POLICY=dual`,
> `TELEMETRY_SOURCE=zmq`, SS off; seeds 42–48, 7/7 per cell.
> **Evidence:** run folders
> `source/scripts/testing/metrics/<ts>_rq2v4_<mode>_mx_<seed>` (28),
> per-run evidence `~/rq2v4_battery/evidence/rq2v4_<mode>_mx_<seed>.txt`,
> per-run metric JSONs `~/rq2v4_battery/mx_p5/<label>.json` (new
> `p5mx.py`), D12 JSONs `~/rq2v4_battery/g1_<label>.json` (`g1lock.py`,
> run with `G1_EPISODE=mixed_episode`), campaign status
> `rq2v4_run_status.csv` (**final mx state: 28 valid / 0 pending / 0
> excluded**; preflight pair `_42p` excluded by design).
> **Cross-refs:** P6.1 60 s-band artifact
> ([`rq2v4_p6_01_60s_band_artifact.md`](rq2v4_p6_01_60s_band_artifact.md))
> — quoted, not recomputed; D18 read-path pinning
> ([`rq2v4_p5_02_read_path_pinning.md`](rq2v4_p5_02_read_path_pinning.md))
> — the registered storage explanation.

## 1. Conventions and provenance (read this before the tables)

- **Analysis code path.** D12 uses the *same script* as the cb regime,
  `~/rq2v4_battery/g1lock.py`, extended **only** with an episode-name
  env override (`G1_EPISODE`, default `hash_episode` preserves the cb
  behaviour): anchor = first post-add selection burst with `band >= 4`
  (`spread band=` controller-log line, at/after the first `ComputeAlert`),
  phantom rows = `http_status 000` or `latency_s >= 300` excluded,
  episode-relative 10 s windows, relief share = post-window p95 < 1 s.
  The storage legs and the member-CPU legs use the new `p5mx.py`
  (read-only), which carries the `p3pilot.py`/`p5check.py` conventions
  and takes the member CPU series from `window_log.storage_servers`
  (dense superset of `per_node_stats` — identical values where both
  exist, verified 2026-10-14); sampled read shares come from
  `per_node_stats.request_count`. Its outputs were validated against
  `p5check.py` evidence on
  `none_mx_45` (completion 72.5/71.0, p50 9.84/10.22, p95x 23.27/23.29,
  lock 100/96.9, member 39.9/39.4 — exact match).
- **Completion** = share of episode (`mixed_episode`) client rows with
  `http_status 200`. **p50** = all episode rows (the `p5check.py`
  convention; the timeout-class rows reach the 30.91 s ceiling).
  **p95x** = phantom-excluded. Every leg is per lane (`lan1/lan2`).
- **Lock %** = absolute 10 s windows over `hash_challenge` rows whose
  window p95 ≥ 1 s (`p5check.py` convention; phantom-excluded). P6.1
  context: the ~8–10 s anti-relief band per minute caps any lane's
  relief share at ≈ 84–87 %, so relieved lanes retain ≈ 13–16 % locked
  windows (observed relieved-run lock readings: 17–31 % here).
- **G1 time-to-relief (D12)** = first `scale_up,ComputeAlert` row →
  first subsequent episode window with hash p95 < 1 s, per lane
  (`g1lock.py`; `None` = never in-episode).
- **D14 storage convention.** Activation = earliest in-episode
  (`>= ep0−5 s`) `reserve_activate,storage_lanN` decision row or
  `[reserve] activated` log line; **post-ready** = activation + 120 s →
  episode end. Two variants are computed and reported because they can
  diverge:
  - **literal (frozen plan text):** the *busiest pre-add member*
    (highest pre-add mean, tie-break peak then MAC) own per-window CPU
    < 0.75 × its own pre-add peak;
  - **win-max (P3 pilot convention, `p3pilot.py`):** per-window maximum
    CPU across all storage members < 0.75 × the pre-add win-max peak.
  Both are reported; **shares are descriptive** for `stor`@mx and are
  the G2 gate metric for `both`@mx (verdict pending P6).
- **Engagement:** ComputeAlert = `scale_up,ComputeAlert` decision rows;
  reserve activations = `[reserve] activated` controller-log lines per
  lane; spawns = `container_events.csv` `added` rows
  (`edge_server_lanN_dyn*` = compute, `edge_storage_lanN_dyn*` =
  storage).
- **MC battery scope:** MC1 (press) and MC4 (margin) are block-level on
  the `none` run; MC2/MC3/MC5 per-run. Culls read from the driver's
  per-run evidence (`triggering removal` = 0 in all 28 runs).

## 2. Per-cell tables (as measured; verdicts pending P6)

### 2.1 `both`@mx

| seed | valid | completion % | p50 (s) | p95x (s) | lock % | timeout % | alerts | reserve acts |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 42 | valid | 99.3/99.4 | 0.008/0.009 | 5.91/5.68 | 17.5/23.4 | 0.7/0.6 | 4/3 | 6/6 |
| 43 | valid | 98.8/98.7 | 0.009/0.009 | 6.60/6.90 | 26.2/29.5 | 1.2/1.2 | 4/3 | 6/6 |
| 44 | valid | 99.0/99.1 | 0.008/0.009 | 6.31/6.65 | 24.6/31.1 | 1.0/0.9 | 3/4 | 6/6 |
| 45 | valid | 99.3/99.2 | 0.008/0.009 | 5.92/6.31 | 26.2/21.9 | 0.7/0.8 | 3/4 | 5/6 |
| 46 | valid | 99.1/98.6 | 0.009/0.009 | 6.21/6.91 | 25.4/31.1 | 0.9/1.4 | 3/3 | 6/5 |
| 47 | valid | 99.1/99.1 | 0.008/0.009 | 5.95/6.28 | 18.8/29.7 | 0.9/0.9 | 3/3 | 5/6 |
| 48 | valid | 98.9/99.0 | 0.008/0.009 | 6.42/6.22 | 29.5/28.6 | 1.1/1.0 | 3/3 | 6/6 |
| **med** | 7/7 | **99.1/99.1** | **0.008/0.009** | **6.2/6.3** | **25.4/29.5** | **0.9/0.9** | 3/3 | 6/6 |

Compute spawns 3–4 per lane (storage spawns 3–5); both tiers engage in
every replicate. Completion ≈ 99 % at ~8–9 ms p50 — the co-located
regime holds up; timeouts ≤ 1.4 % (G4 ≤ 5 % ✓).

### 2.2 `comp`@mx

| seed | valid | completion % | p50 (s) | p95x (s) | lock % | timeout % | alerts | member ≥ 33 % win |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 42 | valid | 98.6/98.2 | 0.009/0.011 | 6.69/7.28 | 17.2/29.5 | 1.3/1.7 | 4/3 | 93.7/90.6 |
| 43 | valid | 98.3/98.3 | 0.009/0.010 | 7.25/7.33 | 26.2/27.9 | 1.7/1.7 | 3/3 | 96.7/96.7 |
| 44 | valid | 98.7/98.3 | 0.009/0.010 | 6.89/7.23 | 24.6/26.2 | 1.2/1.7 | 3/4 | 95.2/93.7 |
| 45 | valid | 98.9/98.6 | 0.009/0.011 | 6.78/6.73 | 23.0/29.7 | 1.1/1.4 | 4/3 | 92.2/92.2 |
| 46 | valid | 98.7/98.2 | 0.009/0.010 | 6.99/7.21 | 22.2/32.8 | 1.2/1.8 | 3/3 | 90.8/90.6 |
| 47 | valid | 98.3/97.8 | 0.009/0.010 | 7.38/7.45 | 27.0/26.6 | 1.6/2.1 | 3/4 | 90.8/90.8 |
| 48 | valid | 98.6/98.7 | 0.009/0.010 | 6.89/6.83 | 24.6/28.6 | 1.4/1.3 | 3/3 | 95.3/93.8 |
| **med** | 7/7 | **98.6/98.3** | **0.009/0.010** | **6.9/7.2** | **24.6/28.6** | **1.3/1.7** | 3/3 | **93.7/92.2** |

No storage engagement in any replicate (reserve lines 0/0, storage
spawns 0/0) — the MC2/MC3 read is clean; member CPU stays ≥ 33 % in
≈ 91–97 % of windows (the unrelieved leg, ≥ 60 % threshold).

### 2.3 `stor`@mx

| seed | valid | completion % | p50 (s) | p95x (s) | lock % | reserve acts | D14 literal % | D14 win-max % | pre-add member reads % |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 42 | valid | 77.7/76.4 | 8.73/9.01 | 22.4/22.5 | 98.4/100 | 6/6 | 2.0/2.1 | 2.0/2.0 | 54.6/63.9 |
| 43 | valid | 77.4/76.7 | 8.63/8.79 | 22.0/22.2 | 100/100 | 6/6 | 0.0/0.0 | 4.3/0.0 | 73.6/65.8 |
| 44 | valid | 77.2/76.1 | 8.93/8.96 | 22.3/22.3 | 100/100 | 6/6 | 0.0/10.9 | 2.1/0.0 | 56.2/65.3 |
| 45 | valid | 76.7/74.7 | 8.97/9.40 | 22.5/22.8 | 100/96.9 | 6/6 | 23.4/2.1 | 0.0/0.0 | 58.4/70.8 |
| 46 | valid | 71.7/70.2 | 9.40/9.77 | 22.5/22.8 | 100/100 | 6/6 | 0.0/19.6 | 4.2/0.0 | 51.9/81.2 |
| 47 | valid | 76.5/75.4 | 8.84/9.26 | 22.4/22.5 | 96.8/96.9 | 6/6 | 4.1/0.0 | 6.0/0.0 | 54.4/85.2 |
| 48 | valid | 76.1/75.7 | 9.04/9.23 | 22.6/22.5 | 98.4/95.3 | 6/6 | 4.1/4.2 | 7.8/6.0 | 97.0/83.9 |
| **med** | 7/7 | **76.7/75.7** | **8.93/9.23** | **22.4/22.5** | **100/100** | 6/6 | **2.0/2.1** | **4.2/0.0** | 56.2/70.8 |

`stor`@mx engages storage only (reserve 6/6 every replicate; 0 compute
alerts, 0 compute spawns) and **does not relieve** — lock stays
95.3–100 % (≥ 90 % MC3 leg), completion ~71–78 % at ~9 s p50. This is
the **D18-pre-registered outcome**, not an anomaly: with a fixed edge
set, storage reads move only through newly born connections
([`rq2v4_p5_02_read_path_pinning.md`](rq2v4_p5_02_read_path_pinning.md)),
and the per-member sampled-read shares (≈ 1 sample/window; descriptive)
still put 3–48 % (lan1) / 15–36 % (lan2) of post-ready reads on members
born in-episode (median 43.8/29.2 — i.e. pinning is not re-selection but
it does not forbid individual re-pins), while the CPU leg shows **no
member relief** (literal median 2.0/2.1 %, win-max median 4.2/0.0 %).

### 2.4 `none`@mx (press witness, block-level)

| seed | valid | completion % | p50 (s) | p95x (s) | lock % | lock halves lan1 | lock halves lan2 | member CPU % | storage_above % |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 42 | valid | 72.5/70.7 | 10.02/10.24 | 23.2/23.8 | 98.4/100 | 100+97 | 100+100 | 40.5/40.2 | 98.4 |
| 43 | valid | 72.3/72.7 | 9.82/9.90 | 23.2/23.1 | 100/100 | 100+100 | 100+100 | 40.6/39.8 | 100.0 |
| 44 | valid | 71.6/71.0 | 10.11/10.16 | 23.3/23.5 | 100/100 | 100+100 | 100+100 | 40.4/39.9 | 100.0 |
| 45 | valid | 72.5/71.0 | 9.84/10.22 | 23.3/23.3 | 100/96.9 | 100+100 | 100+94 | 39.9/39.4 | 100.0 |
| 46 | valid | 72.5/71.0 | 9.92/10.23 | 23.1/23.5 | 95.3/100 | 97+94 | 100+100 | 40.2/39.4 | 99.2 |
| 47 | valid | 68.0/73.8 | 10.32/9.55 | 23.1/23.0 | 96.8/98.4 | 97+97 | 100+97 | 38.8/40.6 | 98.4 |
| 48 | valid | 71.1/69.3 | 10.25/10.63 | 23.7/23.9 | 98.4/98.4 | 97+100 | 100+97 | 40.9/39.8 | 98.4 |
| **med** | 7/7 | **72.3/71.0** | **10.02/10.22** | **23.2/23.5** | **98.4/100** | — | — | **40.2/39.8** | 100.0 |

MC1(mx) passes in all 7 blocks: hash lock ≥ 95.3 % (≥ 80 %), member CPU
mean 38.8–40.9 % (≥ 33 %), `storage_above_threshold` ≥ 98.4 % of policy
rows (≥ 40 %). MC4 (no drift) passes: both episode halves ≥ 93.8 %
locked in every block. `none` runs 0 elasticity operations (0 alerts,
0 spawns everywhere).

## 3. G1 — compute relief by replicate (D12; verdict pending P6)

| seed | relief % lan1/lan2 (both) | TTR s (both) | relief % lan1/lan2 (comp) | TTR s (comp) |
| --- | --- | --- | --- | --- |
| 42 | 95.7/84.8 | 78/72 | 95.7/81.4 | 70/102 |
| 43 | 86.0/83.7 | 74/95 | 86.0/86.0 | 84/90 |
| 44 | 86.0/86.0 | 67/96 | 83.7/88.4 | 71/102 |
| 45 | 86.0/87.0 | 73/74 | 88.4/82.6 | 79/96 |
| 46 | 87.0/86.0 | 74/105 | 87.0/86.0 | 82/101 |
| 47 | 87.0/87.0 | 66/96 | 87.0/84.6 | 81/123 |
| 48 | 86.0/87.0 | 76/90 | 86.0/89.1 | 79/90 |
| **med** | **86.0/86.0** | **74/95** | **87.0/86.0** | **79/101** |

Per-run G1 threshold (≥ 80 % of post-steady windows): **14/14 runs meet
it on both lanes**; per-cell replicate floor (≥ 6/7): `both`@mx 7/7,
`comp`@mx 7/7 — **provisional pass, pending P6**. Relief shares mostly
sit in the P6.1 band-limited range (≈ 84–87 % cap; 5 of the 28 lane
readings are above it — 95.7/95.7/88.4/88.4/89.1 — left for P6: P6.1's
cap was derived on cb and the mx hash mixture is lighter; its
band-excluded sensitivity is 93–98 %, not recomputed here). TTR medians
≈ 74/95 s (`both`) and 79/101 s (`comp`) after the first scale-up.

## 4. Storage legs — `both`@mx G2 cell (as measured; verdict pending P6)

D14 shares (post-ready windows meeting the criterion) per replicate:

| seed | literal lan1/lan2 | win-max lan1/lan2 | lit. TTR s | win-max TTR s |
| --- | --- | --- | --- | --- |
| 42 | 98.0/98.0 | 2.0/4.0 | 10/10 | 510/460 |
| 43 | 45.7/34.8 | 10.4/4.3 | 10/20 | 50/40 |
| 44 | 100.0/26.1 | 8.5/2.1 | 10/10 | 50/470 |
| 45 | 28.6/8.5 | 20.0/0.0 | 10/180 | 30/— |
| 46 | 8.2/40.8 | 0.0/8.0 | 100/10 | —/470 |
| 47 | 12.0/55.6 | 9.8/0.0 | 60/10 | 20/— |
| 48 | 44.0/59.2 | 3.9/2.0 | 70/10 | 490/500 |

**Reading (descriptive; the G2 verdict stays with P6):** under the
literal D14 the replicates range 8.2–100 %/8.5–98 % (median 44.0/40.8) —
i.e. the busiest pre-add member's own CPU does **not** reliably drop
under 0.75 × its pre-add peak, even though reads do move: post-ready
sampled-read shares put ≈ 33 % (both_mx_45 lan1) of reads on members
born in-episode, consistent with the D18 downstream mechanism (compute
spawn → new edge pools → the only channel for new storage capacity to
receive reads). The win-max variant is lower still (median 8.5/2.1).
Two measurement caveats, flagged for P6 rather than resolved here:
1. **Thin, source-sensitive pre-add baseline.** Activations occur
   ~7–40 s into the 600 s episode (press ramps immediately), so
   "pre-add peak" is often a 1–3-window estimate; the busiest-member pick
   then hinges on the first windows of the ramp rather than a settled
   pre-press state, and it is sensitive to the member-series source:
   switching the series from `per_node_stats` to the dense
   `window_log.storage_servers` superset flips the busiest-member pick in
   `both_mx_42` lan2 (`:02:06` → `:00:06`) and the literal share with it
   (20.8 % → 98.0 %). The tables above use `window_log` (see §1). The
   recorded P3 pilot row (`mx_both`, 82.0/95.7 % ✓) is **not
   reproducible** under either convention on the archived pilot
   artifacts — see §4.1 for the bounded reconciliation.
2. **Member CPU is a delivery-bound signal at this seat** (P3 §6: member
   CPU invariant to offered rate at these quotas), so "no CPU relief"
   and "reads moved" are not mutually exclusive here — hence the plan's
   rule that read shares are descriptive and only the CPU leg is gated.

### 4.1 D14-reconciliation — P3 pilot `mx_both` 82.0/95.7 % (bounded; P6 adjudication)

Recorded: `mx_both` relieved in **82.0/95.7 %** of post-ready windows
(P3 §7/D14 row); `mx_stor` ✗/✗ 3.9/0.0 %. Bounded re-derivation on the
archived pilot artifacts (`p3_mx_both_m05`), grid = source
{`per_node_stats`, `window_log`} × tracked unit {PRIMARY, SECONDARY,
busiest pre-add, fleet win-max} × peak {own pre-add (episode), own
pre-add (all windows < act), own episode, fleet pre-add}:

| variant | lan1 | lan2 |
| --- | --- | --- |
| fleet win-max, fleet pre-add peak (p3pilot.py as-is) | 2.0 % | 0.0 % |
| busiest pre-add, own pre-add peak | 6.1 % | 4.3 % |
| busiest pre-add, fleet pre-add peak | 2.0 % | 0.0 % |
| **primary, own pre-add peak (all windows < act), `per_node_stats`** | **85.7 %** | 100.0 % |
| **primary, fleet pre-add (episode) peak, `per_node_stats`** | 65.3 % | **91.5 %** |
| primary, own episode peak | 79.6 % | 44.7 % |
| primary, own pre-add (all) peak, `window_log` | 100.0 % | 100.0 % |
| recorded | **82.0** | **95.7** |

The `mx_stor` row reproduces under the **fleet win-max** convention
(2/51 = 3.9 %, 0/49 = 0.0 %; today's re-run gives 4.0/0.0 % at n = 50/48
— one boundary window). The `mx_both` row
was evidently **primary-scoped** (its "reads moved" companion numbers
are independent); the closest reproducing variants are primary-scoped
with a pre-activation baseline peak — 85.7 % (lan1, `per_node_stats`,
own peak over all pre-act windows) and 91.5 % (lan2, fleet pre-add
episode peak) — but **no variant reproduces 82.0/95.7 % exactly**, and
the spike structure of the pre-episode `window_log` series (e.g. a
single 85.7 % transition window on the pilot's lan1 primary) makes the
metric swing between ~0 % and 100 % depending on the baseline window
set. Conclusion (in-bounds): the recorded pilot row is **not
reproducible from the archived artifacts**; the campaign tables in §2.3
and §4 stand on their own stated conventions. **Marked for P6
adjudication** — the registered D14 definition and the campaign numbers
are not changed here.

`comp`@mx unrelieved leg (MC3): member ≥ 33 % in 90.6–96.7 % of episode
windows (threshold ≥ 60 %), 0 storage engagements, 0 storage spawns —
clean in all 7 replicates; `none` holds 38.8–40.9 % domain mean.

## 5. Manipulation-check battery (all runs)

| Check | Result (28 runs) |
| --- | --- |
| MC1(mx) press (`none`, block-level) | PASS 7/7 blocks (lock ≥ 95.3 %, member ≥ 38.8 %, storage score ≥ 98.4 %) |
| MC2 engagement | PASS all: `both` alerts 3–4 + reserve 5–6/lane, 3–5 storage spawns; `comp` alerts 3–4, 0 reserve/0 storage spawns; `stor` reserve 6/6, 0 alerts/0 compute spawns; `none` 0 ops |
| MC3 specificity | PASS all: `stor` lock 95.3–100 % (≥ 90) with no compute ops; `comp` 0 storage engagements + unrelieved leg ≥ 90.6 % windows |
| MC4 margin (`none`) | PASS 7/7 (both halves ≥ 93.8 % lock) |
| MC5 liveness contract | PASS all (0 `triggering removal` lines, both lanes, 28/28 runs) |
| G4 health ceiling | `both` timeouts 0.6–1.4 %; `comp` 1.1–2.1 % (≤ 5 % ✓); `stor`/`none` exempt |
| D3 config pins | PASS all (phases_snapshot == intended regime JSON; env snapshot carries `dual`+`zmq`+`hash25k`) |

## 6. Provenance, validity reconciliation, host-sampler check

- **Status CSV final state (mx).** 28/28 `valid`, 0 `pending_review`, 0
  excluded; the 21 rows still `pending_review` from the batch were
  reconciled 2026-10-14 against the per-run evidence + recomputed
  metrics (`setvalid.py`, cause strings mirror the cb pattern and carry
  the numbers above). **Spares used: 0.** The db preflight pair
  (`none_db_42p`, `stor_db_42p`) is excluded from the campaign (R4
  preflight, separately recorded).
- **Host-sampler presence reconciliation (F2 aid).**
  `~/rq2v4_battery/host_sampler.csv` is continuous 1 Hz from
  2026-10-12T21:43:20Z with **0 gaps > 5 s**; spot-checked 3 mx
  episodes (`both_mx_45` 16:55:54–17:06:26, `stor_mx_44`
  08:07:39–08:17:41, `none_mx_47` 22:52:36–23:03:08): every episode
  fully covered (rows-in-episode = duration ± 1, max in-episode gap 2 s).
- **Analysis artifacts on `cloud-vm-rq2`:** `~/rq2v4_battery/p5mx.py`
  (new, read-only), `g1lock.py` (+`G1_EPISODE` override), `mx_p5/*.json`,
  `g1_rq2v4_{both,comp}_mx_*.json`, `evidence/*_mx_*.txt`.
  `p5check.py` evidence for all 28 runs was already present from the
  driver.
- **No run folder was modified** during this analysis; the driver moved
  on to the db batch at 10:36:21Z untouched.

## 7. Pointers for P6 (analyzer)

1. Adjudicate the `both`@mx G2 cell against the frozen D14 text given
   the two variant readings (§4) and the single-window pre-add
   sensitivity; P6.1 must be cited for the lock/relief band context.
2. Confirm the G1 replicate math (§3) and the per-cell floor.
3. Decide whether the P3 pilot row 82.0/95.7 % needs a correction note
   in [`rq2v4_p3_00_levers.md`](rq2v4_p3_00_levers.md) /
   [`preparation.md`](preparation.md) (D14 row), given the
   non-reproducibility recorded in §4.1.
