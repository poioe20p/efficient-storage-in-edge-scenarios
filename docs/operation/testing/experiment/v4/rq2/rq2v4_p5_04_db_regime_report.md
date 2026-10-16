# RQ2 v4 — P5.4 data-bound (db) regime report

> **Status:** db regime **closed — 28/30 runs valid**, **5 excluded** under
> §5.5(i) D2 (in-episode container OOM kills: 4 core runs + 1 replacement).
> The escalation (5 exclusions; replacements withheld for `stor_db_48` /
> `none_db_42` / the seed-43 second) was resolved by **author decision D20
> (2026-10-15): n=7 mandated — three top-ups authorised and executed**
> (`both_db_43_r2`, `stor_db_48_r1`, `none_db_42_r1` — all valid; kernel
> sweeps clean; §6.1). All
> numbers below are as-measured; **cell-level
> verdicts are pending P6 (analyzer)** per the campaign division of labour.
> Authored 2026-10-15 by the campaign close-out operator (read-only analysis;
> no driver, run, or config touched; no run-folder writes).
> **Config (frozen db seat):** `EDGE_CPUS 1.20`, `STORAGE_CPUS 0.15`,
> episode `data_bound_episode` 480 s @ rate 5.0/client, frac 1.0, mix
> `{content_lookup 0.9, feed_ranking 0.1}` (per-run `phases_snapshot.json`
> matches — D3 True in all 33 runs), pool 6 (launcher default; the v3
> pool-12 caveat is carried, plan §7 Q3/Q7), `SCALEUP_POLICY=dual`,
> `TELEMETRY_SOURCE=zmq`, `HASH_WORK_FACTOR=25000` (pins present in all 33
> env snapshots), SS off; seeds 42–48, replacements `_r1` for seeds 43
> (`both`) and 46 (`comp`), plus the D20 top-ups (`both_db_43_r2`,
> `stor_db_48_r1`, `none_db_42_r1`).
> **Evidence:** run folders
> `source/scripts/testing/metrics/<ts>_rq2v4_<mode>_db_<seed>[_r1|_r2]` (33),
> per-run evidence `~/rq2v4_battery/evidence/rq2v4_<mode>_db_<seed>[_r1].txt`,
> per-run metric JSONs `~/rq2v4_battery/mx_p5/<label>.json` (`p5mx.py`,
> rebuilt by `db_finalize.py`), D12 JSONs `~/rq2v4_battery/g1_<label>.json`
> (`g1lock.py` with `G1_EPISODE=data_bound_episode`; 28 — every original db
> run except the excluded `both_db_43` and `comp_db_46` originals; the D20
> top-up rows' aux/TTR were recomputed independently, §7), aux probe outputs
> `~/rq2v4_battery/db_aux.txt` + `db_aux_all.txt`, band census
> `~/rq2v4_battery/band_census.txt`, kernel OOM forensics (journalctl/dmesg),
> campaign status `rq2v4_run_status.csv` (**final db state: 28 valid / 0
> pending / 5 excluded**; the 33 db rows exclude the R4 preflight pair
> `*_db_42p`, recorded separately).
> **Cross-refs:** P6.1 60 s-band artifact
> ([`rq2v4_p6_01_60s_band_artifact.md`](rq2v4_p6_01_60s_band_artifact.md))
> — quoted, not recomputed; D18 read-path pinning
> ([`rq2v4_p5_02_read_path_pinning.md`](rq2v4_p5_02_read_path_pinning.md))
> — the registered `stor`@db no-relief explanation; P5.3 mx report
> ([`rq2v4_p5_03_mx_regime_report.md`](rq2v4_p5_03_mx_regime_report.md))
> — format/convention exemplar.

## 1. Conventions and provenance (read this before the tables)

- **Analysis code path.** Per-run metrics use `p5mx.py` (identical to the mx
  regime; phantom row = `http_status 000` or `latency_s >= 300` excluded;
  completion = share of episode rows with `http_status 200`; p50 = all
  episode rows; p95x = phantom-excluded; every leg per lane). D12 uses
  `g1lock.py` run with the **episode-name override**
  `G1_EPISODE=data_bound_episode`.
- **D12 anchor is structurally absent in db — with one post-episode
  exception.** The frozen D12 post-steady anchor is the first
  `spread band ≥ 4` line (anywhere in the controller log, per `g1lock.py`).
  **No db run logs a `band ≥ 4` line during its episode**: the band census
  is 1–3 only (e.g. `both_db_42` lan1: 77× `band=1`, 271× `band=2`,
  39× `band=3`; census artifact `~/rq2v4_battery/band_census.txt`; mx
  control: 382× `band=4`; run-wide coverage = `anchor_utc: null` in the
  other db runs' g1 JSONs). The single ≥ 4 burst anywhere in the db logs is
  post-episode — `both_db_44` lan1, 25× `band=4` at 13:16:54–55, ≈ 30 s
  after that run's episode end (13:16:25) — which `g1lock.py` does pick up as an
  anchor (`anchor_utc 13:16:54`) with **0** post-anchor episode windows.
  Every db run therefore yields `post_windows = 0` and the post-steady
  share is **not evaluable** in db under the frozen rule (the anchor was
  designed on cb/mx; db lookup traffic never fans the compute path wide
  enough). No redefinition is made here. Instead §3 reports, as
  **auxiliary descriptive metrics**: (a) the **alert-anchored relief
  share** — first `scale_up,ComputeAlert` timestamp per lane → episode
  end, share of 10 s windows (phantom-excluded) with p95 < 1 s — computed
  by the read-only close-out probe `closeout_db_aux.py` / `db_aux.txt`;
  (b) the frozen **time-to-relief (D12)** endpoint (first alert → first
  p95 < 1 s window, as `g1lock.py` computes it); (c) the episode
  **latency-lock** share (`g1lock.py` `lock_share_pct`: windows with
  all-row p95 ≥ 1 s — db has no hash rows, so this is the db analogue of
  the lock leg). Adjudication of the anchor-absence handling is a P6 item
  (§8).
- **G1 scope note.** Plan §5.2 defines gate G1 for `both`/`comp` @ **cb/mx**
  only; the db compute side is pre-registered **descriptive** (§2.2 db row:
  "compute-side engagement descriptive"). §3 is therefore descriptive
  evidence, not a gate evaluation.
- **D14 storage convention** (identical to P5.3 §1, carried unchanged):
  activation = earliest in-episode (`>= ep0−5 s`) `reserve_activate,storage_lanN`
  decision row or `[reserve] activated` line; **post-ready** = activation +
  120 s → episode end; two variants — **literal** (busiest pre-add member,
  highest pre-add mean, tie-break peak then MAC, own CPU < 0.75 × its own
  pre-add peak) and **win-max** (P3 pilot convention: per-window max CPU
  across members < 0.75 × the pre-add win-max peak); **shares are
  descriptive**; time-to-relief = first post-ready window meeting the
  criterion, reported offset from ready (=0 means met immediately) and from
  the activation timestamp. Pre-add baselines are thin in db too
  (activations land ~10–35 s into the episode; busiest-member `pre_n` =
  3–5 windows, second member 1 window) — same caveat class as P5.3 §4.
- **MC battery scope** (plan §5.1): MC1 (press) and MC4 (margin) are
  block-level on the block's `none` run; MC2/MC3/MC5 per-run; G4 timeout
  ceiling applies to `both`@db, `stor`@db (comp/none exempt — note the
  wording tension in §5).
- **Phantom exclusion** as above; `canceled` rows remain distinct (I2).

## 2. Per-cell tables (as measured; verdicts pending P6)

Validity column read from `rq2v4_run_status.csv` (final). `both_db_43` and
`comp_db_46` rows are their excluded originals; the replacement rows stand in
their cells (43's replacement is also excluded — see §6).

### 2.1 `both`@db

| seed | valid | completion % | p50 (s) | p95x (s) | timeout % | alerts | reserve acts | aux relief % (descriptive) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 42 | valid | 99.0/99.1 | 0.029/0.066 | 2.19/2.23 | 0.6/0.9 | 1/1 | 3/4 | 73.9/68.9 |
| 43 (orig) | **excluded** | 10.5/96.9 | 30.54/0.029 | 24.55/9.03 | 38.9/3.0 | 1/1 | 1/5 | — |
| 43_r1 | **excluded** | 42.9/98.9 | 1.32/0.020 | 1.39/2.07 | 38.3/1.1 | 1/1 | 2/3 | 91.1/97.7 |
| 44 | valid | 99.4/99.3 | 0.036/0.078 | 2.16/2.35 | 0.5/0.6 | 1/1 | 3/4 | 89.1/87.0 |
| 45 | valid | 99.8/99.7 | 0.029/0.058 | 1.37/1.47 | 0.2/0.2 | 1/1 | 3/4 | 91.3/91.1 |
| 46 | valid | 99.3/99.5 | 0.038/0.067 | 1.87/2.08 | 0.6/0.5 | 1/1 | 3/2 | 91.1/87.0 |
| 47 | valid | 99.2/99.2 | 0.026/0.048 | 2.10/2.22 | 0.7/0.8 | 1/1 | 3/4 | 89.1/89.1 |
| 48 | valid | 99.5/99.3 | 0.028/0.054 | 2.04/2.21 | 0.5/0.7 | 1/1 | 3/3 | 89.1/89.1 |
| 43_r2 | valid (D20 top-up) | 99.2/99.2 | 0.028/0.056 | 2.13/2.15 | 0.8/0.7 | 1/1 | 4/3 | 88.9/87.0 |
| **med** | 7/9 rows | **99.3/99.3** | **0.029/0.058** | **2.10/2.21** | **0.6/0.7** | 1/1 | 3/4 | **89.1/87.0** |

Valid runs: completion ≈ 99.3 % at ~29–78 ms p50 (the co-located db regime
holds up), timeouts ≤ 0.9 % (G4 ≤ 5 % ✓ on all valid rows). Both tiers
engage in every valid replicate (1 alert + 2–4 storage activations per
lane; spawns 1+3 on lan1, 1+2–1+4 on lan2). Medians over the 7 valid rows
(the `43_r2` top-up row's aux share recomputed independently — §7);
the two exclusions and their cause class are in §6.

### 2.2 `comp`@db

| seed | valid | completion % | p50 (s) | p95x (s) | timeout % | alerts (descriptive) | member ≥ 50 % win |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 42 | valid | 99.6/99.8 | 0.024/0.043 | 1.69/1.31 | 0.3/0.2 | 1/1 | 93.9/95.9 |
| 43 | valid | 99.8/99.6 | 0.029/0.055 | 1.56/2.08 | 0.2/0.3 | 1/1 | 95.8/95.9 |
| 44 | valid | 99.8/99.8 | 0.027/0.050 | 0.90/1.04 | 0.1/0.1 | 1/1 | 95.9/95.9 |
| 45 | valid | 99.8/99.9 | 0.027/0.049 | 1.10/1.17 | 0.1/0.1 | 1/1 | 95.8/95.9 |
| 46 (orig) | **excluded** | 67.5/97.6 | 0.25/0.030 | 9.67/7.05 | 17.7/2.3 | 4/3 | — (no JSON) |
| 46_r1 | valid | 99.8/99.8 | 0.022/0.038 | 1.38/1.31 | 0.2/0.2 | 1/1 | 95.9/95.9 |
| 47 | valid | 99.8/99.8 | 0.032/0.057 | 1.17/1.55 | 0.2/0.2 | 1/1 | 95.9/95.9 |
| 48 | valid | 99.8/99.9 | 0.024/0.038 | 1.21/1.09 | 0.1/0.1 | 1/1 | 95.9/95.9 |
| **med** | 7/8 rows | **99.8/99.8** | **0.027/0.049** | **1.21/1.31** | **0.2/0.2** | 1/1 | **95.9/95.9** |

No storage engagement in any valid replicate (reserve lines 0/0, storage
spawns 0) — MC3 read clean. The member CPU persists ≥ 50 % in ≈ 94–96 % of
episode windows (≥ 60 % leg ✓); the unrelieved leg is the cell's
pre-registered storage direction. The excluded original's member means
(57.1/66.9 % over 49–50 windows, per its evidence) are
incident-contaminated and shown for context only; its `domain_ge50` share
was never computed (row left `pending_review` at halt time, excluded before
a JSON existed).

### 2.3 `stor`@db

| seed | valid | completion % | p50 (s) | p95x (s) | timeout % | reserve acts | D14 literal % | D14 win-max % | lit. TTR (ready/act) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 42 | valid | 92.2/93.7 | 1.99/1.63 | 11.70/10.03 | 7.7/6.1 | 6/3 | 0.0/2.9 | 0.0/2.9 | —/350–470 |
| 43 | valid | 90.7/93.6 | 2.20/1.47 | 16.41/10.05 | 9.1/6.1 | 3/3 | 2.9/0.0 | 2.9/0.0 | 350/— |
| 44 | valid | 88.1/89.5 | 2.33/2.26 | 16.86/16.65 | 11.6/10.3 | 3/3 | 0.0/0.0 | 0.0/0.0 | — |
| 45 | valid | 91.7/92.7 | 2.08/2.05 | 15.42/11.71 | 8.1/7.2 | 3/5 | 2.9/0.0 | 2.9/0.0 | 350/— |
| 46 | valid | 87.5/82.3 | 2.37/3.13 | 20.20/19.85 | 11.8/16.9 | 3/2 | 2.8/42.9 | 2.8/42.9 | 360/60 |
| 47 | valid | 92.3/93.8 | 2.11/1.89 | 14.52/11.20 | 7.6/6.1 | 2/3 | 0.0/0.0 | 0.0/0.0 | — |
| 48 | **excluded** | 71.2/87.1 | 2.53/2.14 | 18.12/16.82 | 19.2/12.3 | 3/3 | 31.4/73.5 | 31.4/73.5 | 70/50 |
| 48_r1 | valid (D20 top-up) | 90.2/90.4 | 2.18/2.20 | 16.24/15.56 | 9.6/9.4 | 4/4 | 2.9/0.0 | 2.9/0.0 | — |
| **med** | 7/8 rows | **90.7/92.7** | **2.18/2.05** | **16.24/11.71** | **9.1/7.2** | 3/3 | **2.8/0.0** | **2.8/0.0** | — |

`stor`@db engages storage only (2–6 activations per lane; **0 compute alerts,
0 compute spawns** — MC3 ✓) and **does not relieve**: literal shares
0.0–42.9 %, i.e. **0/7 valid replicates meet the ≥ 80 % criterion on both
lanes** (incl. the D20 top-up `stor_db_48_r1` at 2.9/0.0) — the
pre-registered D18 outcome (§4). The lane latency sits at
2–3 s p50 / ~10–20 s p95x when unrelieved, and the latency-lock (all-row
windows, §1) is 95.9–100 % in all 7 valid runs (`stor_db_48` lan2's 91.8 %
reading is the excluded one).

### 2.4 `none`@db (press witness, block-level)

| seed | valid | completion % | p50 (s) | p95x (s) | timeout % | member CPU % | halves ge50 lan1/lan2 | storage_above % | lat-lock % |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 42 | **excluded** | 30.4/94.9 | 30.42/0.55 | 8.30/16.38 | 40.8/4.7 | 38.5/62.8 | 56/0, 71/100 | 81.0 | 89.7/51.0 |
| 42_r1 | valid (D20 top-up) | 89.8/91.9 | 2.18/2.04 | 16.32/11.82 | 10.0/7.9 | 67.8/68.7 | 92/100, 92/100 | 82.4 | 100/100 |
| 43 | valid | 92.3/93.1 | 1.96/1.72 | 11.54/11.79 | 7.6/6.8 | 68.4/68.7 | 92/100, 92/100 | 87.5 | 100/100 |
| 44 | valid | 91.2/93.4 | 1.72/1.55 | 14.38/9.97 | 8.6/6.4 | 68.3/69.6 | 92/100, 92/100 | 83.3 | 95.9/91.8 |
| 45 | valid | 90.8/90.8 | 2.16/2.18 | 16.44/15.72 | 9.0/9.0 | 67.2/68.9 | 92/100, 92/100 | 85.0 | 100/100 |
| 46 | valid | 93.4/93.7 | 1.83/1.75 | 9.90/9.75 | 6.4/6.2 | 67.5/69.2 | 88/100, 92/100 | 78.9 | 100/100 |
| 47 | valid | 95.8/96.7 | 1.53/1.29 | 8.74/8.49 | 4.1/3.1 | 68.4/69.7 | 92/100, 92/100 | 84.2 | 100/85.7 |
| 48 | valid | 92.1/94.7 | 1.90/1.49 | 15.17/9.06 | 7.8/5.1 | 68.4/69.3 | 92/100, 92/100 | 82.4 | 98.0/100 |
| **med** | 7/8 rows | **92.1/93.4** | **1.90/1.72** | **14.38/9.97** | **7.8/6.4** | **68.3/69.2** | **92/100, 92/100** | 83.3 | 100/100 |

MC1(db) passes in all 7 valid blocks (block-42 witness restored by the D20
top-up `none_db_42_r1`, member 67.8/68.7): member CPU mean 67.2–69.7 %
(≥ 50 %), held in both halves (h1 88.0–92.0 %), `storage_above_threshold` in
78.9–87.5 % of policy rows; 0 elasticity operations everywhere (0 alerts,
0 spawns). `none_db_42`'s excluded original stays in §6.1.

## 3. Compute side — D12 anchor absence, aux relief (descriptive; verdict pending P6)

**Anchor absence (as measured).** No run in the db regime logs a
`spread band ≥ 4` line *during its episode* (bands 1–3; the sole such burst
is post-episode — `both_db_44` lan1, §1), so the frozen D12 post-steady
share is not evaluable. The frozen **time-to-relief** endpoint is evaluable
and is reported below together with the aux alert-anchored share
(descriptive substitute; not a gate).

| seed | alert s (lan1/lan2) | aux relief % l1/l2 | TTR s l1/l2 (D12 endpoint) |
| --- | --- | --- | --- |
| **`both`@db** | | | |
| 42 | 22:34:55/22:35:01 | 73.9/68.9 | 44/50 |
| 44 | 13:08:49/13:08:52 | 89.1/87.0 | 55/63 |
| 45 | 14:22:27/14:22:42 | 91.3/91.1 | 45/41 |
| 46 | 15:35:23/15:35:17 | 91.1/87.0 | 47/54 |
| 47 | 20:32:40/20:32:45 | 89.1/89.1 | 55/51 |
| 48 | 21:45:24/21:45:28 | 89.1/89.1 | 54/51 |
| 43_r2 | 21:25:12/21:25:07 | 88.9/87.0 | 60/70 |
| **med (7 valid)** | — | **89.1/87.0** | **54/51** |
| **`comp`@db** | | | |
| 42 | 22:59:43/22:59:47 | 89.1/87.0 | 55/62 |
| 43 | 10:43:07/10:43:02 | 93.3/89.1 | 37/53 |
| 44 | 13:33:35/13:33:40 | 93.5/93.3 | −6\*/0\* |
| 45 | 14:47:20/14:47:25 | 93.3/93.3 | 36/32 |
| 46_r1 | 00:36:08/00:36:14 | 91.3/91.1 | 45/50 |
| 47 | 19:19:17/19:19:22 | 91.3/91.1 | 44/50 |
| 48 | 22:10:19/22:10:14 | 91.1/91.3 | 46/41 |
| **med (7 valid)** | — | **91.3/91.1** | **44/50** |

\*`comp_db_44`: the first p95 < 1 s window and the first alert fall in the
same 10 s window (negative by construction of the windowed endpoint).

**Reading (descriptive; pending P6):** every valid `both`/`comp` db run
reaches p95 < 1 s by its first alert window or within 32–70 s of it, on
both lanes (`both` median 54/51 s; `comp` median 44/50 s), and the aux
post-alert relief share stays ≥ 80 % on both lanes in **`comp` 7/7** and
**`both` 6/7** (`both_db_42` 73.9/68.9 is the only miss — its alert lands
26 s into the episode and its first minutes include the storage activation
lag). Meeting-run aux shares 87.0–93.5 % sit at/above the cb band-capped
range (≈ 84–87 %, P6.1 §3); per P6.1 §5 the artifact is referenced as-is —
nothing is recomputed here, and no db row was adjusted for band windows.
The episode latency-lock (§1) is 12.2–16.3 % in the valid
`comp`/`both` runs except `both_db_42` (30.6/36.7 %), versus 85.7–100 % in
every valid `none`/`stor` run — the aligned arms are decisively de-locked
relative to the comparators, measured on the same all-row window
convention.

## 4. Storage legs — `both`@db (G2 claim) and `stor`@db (D18 outcome)

**`both`@db (G2 cell).** D14 literal shares per valid replicate: 86.1/97.1,
100/80.0, 2.9/54.3, 100/88.2, 100/94.4, 100/11.8, plus the D20 top-up
`both_db_43_r2` at 100/97.1 (recomputed independently — §7) → **5/7
replicates meet the ≥ 80 % both-lane criterion** (misses: s45 lan1 2.9 %,
lan2 54.3 %; s48 lan2 11.8 %; s44's lan2 reads 79.4–80.0 depending on
window-boundary handling — a threshold-borderline replicate flagged for
P6; the win-max variant yields the same 5/7 count).
The literal TTR (first post-ready window meeting the criterion, per lane)
reads 10 s in 9 of the 14 valid-run lane readings, 60 s in `both_db_42`
lan1 and `43_r2` lan1, 70 s in `43_r2` lan2, and 210 s in the two slowest
lanes — `both_db_45` lan1 and `both_db_48` lan2, both belonging to
replicate-misses.
Post-ready sampled-read shares (≈ 1
sample/window; descriptive) show a minority of post-activation members
receiving reads in some runs (e.g. `both_db_42` lan1 07/09 → 21.4 + 7.1 %;
several runs 0 %) — consistent with the D18 downstream channel (compute
spawn → new edge pools → new connections re-pin), and with the P5.3 §4
caveat that member CPU is a delivery-bound signal at this seat. Thin
pre-add baselines (3–5 windows) apply as in P5.3.

**`stor`@db — no relief (D18, registered).** 0/7 valid replicates meet the
criterion in either variant (max reading 42.9 % in `stor_db_46` lan2; the
D20 top-up `stor_db_48_r1` reads 2.9/0.0 — its sibling's 31.4/73.5 in the
excluded original was boundary noise at the collapsed tail);
medians 2.8/0.0 (lan1/lan2, frozen-tool rows). With a fixed edge set, no new client connections are born
after the press starts, so the members admitted by storage scaling receive
no reads — storage read paths are pinned to the connections existing at
activation ([`rq2v4_p5_02_read_path_pinning.md`](rq2v4_p5_02_read_path_pinning.md),
D18). **Plan-row note:** plan §2.2's claim table still shows `storage
relief ✓ (D14)` for the db `stor` cell; D18 (registered 2026-10-14, P5.2 /
[`rq2v4_p5_02_read_path_pinning.md`](rq2v4_p5_02_read_path_pinning.md); the
plan's risk notes carry it) supersedes it for the fixed-edge-set case — the measured
0/6 is the post-D18 expectation, and P6 is asked to reconcile the stale
claim row. This is the **pre-registered** D18 outcome, not an anomaly: the same
signature was measured in `stor`@mx (0/7, P5.3 §2.3) and the comparator
read is clean (`none` holds member CPU 67.2–69.7 % with 0 activations).
Post-ready read shares in `stor`@db are thin and mostly zero on
post-activation members — the pinning is total for the fixed-set case.
`none`@db has no activation by construction → D14 n/a (witness = the
persisting member CPU above).

## 5. Manipulation-check battery (all 30 db runs)

| Check | Result |
| --- | --- |
| MC1(db) press (`none`, block-level) | PASS 6/7 blocks (member mean 67.2–69.7 % ≥ 50; ranges above); block 42 witness incident-excluded (block-42 reading in §6.1) |
| MC2 engagement | `both`: 1 alert + 2–4 reserve activations per lane, all runs; `comp`: compute-side alerts 1/1 (descriptive; adds meet MC5/M2), **0 storage engagements**; `stor`: 2–6 activations, 0 compute ops; `none`: 0 ops |
| MC3 specificity | `comp`@db: 0 storage engagements + member ≥ 50 % in 93.9–95.9 % of episode windows (≥ 60 ✓); `stor`@db: 0 compute alerts/spawns ✓ |
| MC4 margin (`none`) | PASS 6/7 (halves ge50: lan1 88.0–92.0 %, lan2 100 % in every valid block; sustained) |
| MC5 liveness contract | PASS: 0 `triggering removal` lines in 32/33 runs; `comp_db_46` (excluded) has the 1 correct dead-unit absence-cleanup of its OOM'd dyn unit — the D19 log line is the P1 fix working (§6) |
| G4 health ceiling (timeouts ≤ 5 %) | `both`@db valid rows ≤ 0.9 % ✓; `comp` exempt; `stor`@db 6.1–16.9 % in all valid rows — **wording tension carried from screening, §5.1 below**; `none` exempt |
| D3 config pins | PASS all 33 (phases snapshot == db shape; `dual=True zmq=True hash25k=True`) |

### 5.1 G4 wording tension (`stor`@db) — for P6 adjudication

Plan §5.2 lists `stor`@db under the G4 cells (timeout ≤ 5 %), but every
valid `stor`@db run reads 6.1–16.9 % timeouts (and the no-action comparator
`none`@db 3.1–9.0 %, G4-exempt). The screening convention recorded these rows as
**valid** (5 of the 6 valid rows carry the "G4 wording tension — see
P5.04" cause note — spelling varies, hyphen in `stor_db_45`/`46`; `stor_db_43`
predates the note but is the same
class), on the reading that the 5 % ceiling was calibrated on
recovering cells while `stor`@db is structurally unrelieved by D18 (its
lane latencies sit at 2 s p50 / 10–20 s p95x *with* storage engaged).
This report carries the numbers as-is and does **not** redefine G4; P6 must
adjudicate (options in §8). No row's validity depends on the resolution —
the runs themselves are clean (§6 shows the incident-excluded ones are a
different set).

## 6. Incidents & exclusions (D19 update): the db OOM class

**The db regime's single incident mechanism.** Five db runs were invalidated
by in-episode container **cgroup OOM kills** (256 MB container cap) — the
same class first registered for `comp_db_46` (D19(b)). Kernel forensics
(journalctl; dmesg -T shows the same events shifted +53 s) plus the runs'
own `container_events.csv`:

| # | UTC (journalctl) | container | run | consequence |
| --- | --- | --- | --- | --- |
| 1 | 11:56:20 | `edge_server_n1` OOM-killed | `both_db_43` | base lan1 member restarted ~35 s later |
| 2 | 11:58:06 | `edge_server_lan1_dyn3` OOM / Exited(137) | `both_db_43` | second lan1 kill → lane black-hole: completion 10.5/96.9, F1 35 consec empty windows |
| 3 | 16:01:22 | `edge_server_lan1_dyn1` OOM-killed (D19(b)) | `comp_db_46` | lan1 completion 67.5 vs lan2 97.6; + `dyn2` Exited(137) 16:02:46; correct absence-cleanup 16:11:21 ("not seen for 608 s") tripped the driver's `culls_nonzero` halt (batch halted 16:17Z) |
| 4 | 21:03:19 | `edge_server_n1` OOM-killed (restart 21:03:20–21) | `stor_db_48` | last ~6 episode windows collapsed (lan1 p50 30–55 s); completion 71.2/87.1; F1 max_consec=8 |
| 5 | 23:50:56 | `edge_server_n1` OOM-killed | `none_db_42` | member absent ~4.5 min; lan1 completion 30.4 %; MC1/MC4 fail as consequence |
| 6 | 00:12:02 | `edge_server_n1` OOM-killed | `both_db_43_r1` | lan1 completion 42.9 %, timeout 38.3 % (G4), 000 38.6 % |

Events 5–6 were **missed by the container_events poller** (the docker
restart window fell between polls) and are witnessed only by the kernel log
— recorded here so P6 does not re-derive them. No OOM events exist anywhere
in the cb/mx batches (journalctl scan back to 2026-10-10); the class is
db-specific (the lookup press drives edge-server process memory against the
256 MB cap). Full per-run evidence:
`~/rq2v4_battery/evidence/*_db_*.txt`, run `container_events.csv`,
`sudo -n journalctl --since 2026-10-10`.

**Reclassification of `both_db_43`.** D19(a) excluded it as §5.5(iii)
F2 host-interference (sampler load 16.4 / busy 94 %). The close-out scan
shows kernels kills (rows 1–2 above) in exactly its episode, and shows the
same sampler load profile is routine for db episodes (the clean
`comp_db_46_r1` carries an equivalent profile) — the host-sampler reading
was the workload itself. The run stays excluded (outcome unchanged); the
cause is corrected to §5.5(i) D2-OOM in the status CSV and D19(a) is
**superseded on mechanism** (author may wish to amend the D-log).

### 6.1 Exclusions, replacements, escalation (status CSV, final)

| label | status | cause class |
| --- | --- | --- |
| `both_db_43` | excluded | (i) D2-OOM (reclassified from (iii), §6); replaced by `both_db_43_r1` |
| `both_db_43_r1` | excluded | (i) D2-OOM (replacement itself killed); seed-43 slot consumed — **2nd replacement = author decision** |
| `comp_db_46` | excluded | (i) D2-OOM (D19(b), unchanged); replaced by `comp_db_46_r1` |
| `stor_db_48` | excluded | (i) D2-OOM; replacement withheld |
| `none_db_42` | excluded | (i) D2-OOM (+ MC1/MC4 consequence); replacement withheld |
| `comp_db_46_r1` | **valid** | clean replacement (folder 20261015_003439) — comp@db cell back to n=7 |
| `both_db_43_r2` | **valid** | D20 top-up (third seed-43 attempt, folder 20261015_212335): completion 99.2/99.2; kernel sweep clean |
| `stor_db_48_r1` | **valid** | D20 top-up (folder 20261015_214836): completion 90.2/90.4; reserve 4/4; kernel sweep clean |
| `none_db_42_r1` | **valid** | D20 top-up (folder 20261015_221248): block-42 press witness restored (member 67.8/68.7); kernel sweep clean |

- **Resolution (D20, author 2026-10-15):** the escalation below was carried to
  the author; **n=7 was mandated** — three top-ups authorised and executed
  (all valid, kernel sweeps clean 21:18–22:31Z). Both/stor/none@db are back
  to **n=7**; replacements used = **5 of ≤14** (author exception to §5.5's
  ">4 stop" rule recorded in D20). The five exclusions stand as recorded
  (incident class, not treatment effect).
- **Historical escalation record (superseded by D20):** db exclusions = **5**,
  exceeding D19(c)'s registered stop-and-escalate threshold ("if db
  exclusions exceed 4"); two replacements were queued and run for the slots
  that had one (one clean, one also killed). Filling all three remaining
  slots would take the regime to **5 replacements**, exceeding plan §5.5's
  ">4 replacements → stop that regime and escalate" rule — the withhold was
  that rule's default until the author signed off.
- **`none_db_42` block reading (plan §5.1):** two readings exist — (a) witness-run
  incident only (this CSV: row excluded; the other three seed-42 runs stand
  on their own gates, which all pass); (b) the plan's literal "MC1 failure
  excludes the four runs of the block". The press property itself is
  witnessed by the 6 clean `none` runs + the R4 preflight
  (`none_db_42p`, member 66.8/68.5 ≥ 50). **P6/author adjudication.**
- **What did *not* change:** no gate was redefined; all as-known valid rows
  from earlier screening stand; no run folder was modified.

## 7. Provenance, artifacts, status-CSV state

- **Screening tooling.** `~/rq2v4_battery/db_finalize.py` (p5mx + evidence
  checks + MC1–MC4 for db) run over the 14 pending labels 2026-10-15;
  `setvalid.py` applied the 7 screening edits: `stor_db_42` / `stor_db_47`
  → valid (tension note, §5.1) and the five §6.1 exclusions set/refined;
  exclude causes cite journalctl/container_events evidence read on 2026-10-15.
- **Status CSV final state (`rq2v4_run_status.csv`, on `cloud-vm-rq2`):**
  91 rows = 2 R4-preflight + 89 campaign; campaign = **84 valid / 5
  excluded** (all 5 db; cb/mx 56/56 valid); db subset = 28 valid / 5
  excluded. No `pending_review` rows remain. The D20 top-up rows carry the
  mandated n=7 note; their aux/D14/lat-lock numbers in §§2–4 were recomputed
  in the main session with the frozen conventions (reproduction checks passed
  on known rows to ≤2 pp at window boundaries; the s44-lan2 borderline is
  flagged in §4).
- **Analysis scripts on `cloud-vm-rq2` (all read-only):** `p5mx.py`,
  `g1lock.py` (+ `G1_EPISODE`), `db_finalize.py`, close-out probes
  `closeout_db_aux.py`, `closeout_client_windows.py`,
  `closeout_sampler_win.py`, `closeout_d2_scan.py`, `closeout_kill_scan.py`
  (outputs `db_aux.txt`, probe logs). No run folder was written to.
- **Host sampler:** `~/rq2v4_battery/host_sampler.csv` continuous 1 Hz from
  2026-10-12T21:43:20Z; every db episode is covered with max in-episode gap
  ≤ 2 s (28-row coverage artifact `~/rq2v4_battery/db_aux_all.txt`; the two
  excluded originals spot-checked per-minute) — the sampler is not a
  confound for any db reading.
- **Run history:** db batch 2026-10-14T10:36→16:17 (halted at `comp_db_46`),
  resume 18:24:17 → complete 2026-10-15T00:53:37Z (`driver.log`); D20 top-up
  batch 2026-10-15T21:18:16→22:31:44Z (`launch_topups.sh`, all rc=0, all
  valid); first/last db folders `20261014_104130` /
  `20261015_221248_rq2v4_none_db_42_r1`.

## 8. Pointers for P6 (analyzer)

1. **D12 anchor-absence handling for db** (structural: bands ≤ 3): decide
   whether the frozen `band ≥ 4` anchor needs a db annex (e.g. alert-anchored
   share as here) or the descriptive reading stands. The aux metric is
   labeled descriptive and is not a gate.
2. **G2 cell math for `both`@db**: 4/6 valid replicates meet literal D14
   both-lane ≥ 80 (misses s45, s48); decide the cell treatment given n=6
   (author replacements pending) and the thin-baseline caveat.
3. **G4 wording tension for `stor`@db** (§5.1): resolve the ≤ 5 % timeout
   ceiling vs the 6.1–16.9 % measured in a D18-unrelieved cell.
4. **OOM class escalation** (§6): **resolved — D20 (author 2026-10-15)**:
   exclusions confirmed; three top-ups executed, all valid; all db cells at
   n=7; block-42 press witness restored (reading (a) of §6.1 — witness-run
   incident only — is the operative one).
5. **P6.1 inheritance**: db aux shares use the same as-is + artifact
   handling; no db row was adjusted for band windows.
6. If D19's `both_db_43` mechanism note is amended, mirror it in
   [`preparation.md`](preparation.md) (this report's §6 is the evidence).


## 9. Post-fix follow-up (2026-10-16)

**Author directive D21 (2026-10-16):** the D18 constraint documented in this
report is addressed by an authorised platform fix (admission-time epoch
renewal: storage admission now triggers graceful Mongo-connection renewal on
the edge servers, so newly admitted members can receive reads) plus a
recalibrated db seat (member quota lowered so storage is the first-binding
resource). A new campaign (`rq2v5`, 56 runs: mx + db) will re-measure the
storage cells under the fix, gated on the author's hard goals (t_db reduction
and same-tier relief under storage-only scale-up; client benefit not
required). This report remains the **pre-fix diagnosis record**; v5 numbers
must never be pooled with the v4 rows here. Plan:
[`../../v5/rq2/rq2v5_plan.md`](../../v5/rq2/rq2v5_plan.md).
