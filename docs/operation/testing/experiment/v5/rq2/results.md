# Results — RQ2 v5 (read-path renewal + storage ε-band + recalibrated db seat)

**Date**: 2026-10-18 · **Experiment Plan**: [`experiment_plan.md`](./experiment_plan.md)
(design: [`rq2v5_plan.md`](./rq2v5_plan.md); pilots:
[`rq2v5_p2_01_pilot_evidence.md`](./rq2v5_p2_01_pilot_evidence.md))
**Runs**: 56 campaign runs (`rq2v5_<mode>_<regime>_<seed>`, seeds 42–48 ×
both/comp/stor/none × mx/db) + 1 approved replacement
(`rq2v5_stor_db_43_r1`). Cell-level data: [`rq2v5_cell_stats.csv`](./rq2v5_cell_stats.csv).
**Gate registration**: D24 (author, 2026-10-17) — the only hard goals; D22 froze
seat/config.

---

## Run Timeline

| Run | Date | Status | Cumulative analysis | Conclusions | Changes made | Expectations for this run |
|-----|------|--------|---------------------|-------------|--------------|---------------------------|
| W2 pilots (`rq2v5_p2_pilot_*`, 6 runs) | 2026-10-16/17 | ✅ | — (initial) | Read-path pinning fixed: stor@db t_db 0.03×; mx sub-bar 0.83–0.86 | EDGE_MEMORY 256m→384m (OOM); seat db sc=0.09/ec=1.20 | Mechanism engages without OOM |
| v1 — mx block (28 runs) | 2026-10-17 05:23 → 2026-10-18 00:06 | ✅ | pilots | — | — (frozen config) | both > comp ≳ stor > none |
| v2 — db block (28 runs) | 2026-10-18 00:06 → 12:16 | ✅ | mx block | mx gates hold; comp@db t_db inversion appears | — | stor/both beat none **and** comp on t_db + relief |
| v3 — replacement (`stor_db_43_r1`) | 2026-10-18 12:46 → 13:12 | ⚠️ | db block | OOM incident on seed 43; replacement clean but weak relief | 1 spare (of ≤14), author-approved | Clean seed-43 stor measurement |

Campaign wall time ≈ 31 h for 56 runs; OOM incidents 2/56 (both edge-OOM at
episode onset); culls 0 in every run; `phases.json` restored byte-exactly
(`57bccc12bebb98dfeb92`).

## Measurements — Per-Run

Measurements only (no judgment) — episode-window medians from
`window_log_lanX.jsonl`; completion = episode-phase HTTP 200 share. Full 57-row
detail (including band picks, broadcasts and storage-CPU per lane) is in
[`rq2v5_cell_stats.csv`](./rq2v5_cell_stats.csv).

### mx block — `avg_time_db_ms` (lan1 / lan2)

| seed | none | comp | stor | both |
|---|---|---|---|---|
| 42 | 103 / 103 | 10 / 10 | 87 / 92 | 6 / 6 |
| 43 | 105 / 103 | 10 / 9 | 86 / 90 | 8 / 7 |
| 44 | 106 / 103 | 8 / 9 | 89 / 89 | 6 / 6 |
| 45 | 99 / 104 | 10 / 10 | 89 / 92 | 6 / 7 |
| 46 | 106 / 100 | 9 / 10 | 90 / 90 | 7 / 6 |
| 47 | 103 / 107 | 11 / 9 | 90 / 92 | 6 / 6 |
| 48 | 101 / 104 | 9 / 9 | 91 / 94 | 6 / 7 |

### mx block — `avg_time_proc_ms` (lan1 / lan2) and episode completion %

| seed | none | comp | stor | both |
|---|---|---|---|---|
| 42 | 123 / 125 (72 / 71) | 11 / 11 (98 / 98) | 111 / 116 (79 / 76) | 11 / 10 (99 / 99) |
| 43 | 119 / 125 (73 / 68) | 10 / 11 (99 / 98) | 110 / 115 (76 / 76) | 10 / 10 (99 / 99) |
| 44 | 121 / 127 (72 / 68) | 11 / 11 (99 / 98) | 119 / 121 (76 / 73) | 9 / 10 (99 / 99) |
| 45 | 118 / 132 (73 / 68) | 11 / 10 (98 / 99) | 110 / 116 (75 / 72) | 10 / 10 (99 / 99) |
| 46 | 121 / 124 (69 / 69) | 10 / 11 (99 / 98) | 113 / 117 (73 / 74) | 10 / 11 (99 / 99) |
| 47 | 125 / 124 (72 / 71) | 10 / 10 (99 / 98) | 115 / 121 (75 / 74) | 10 / 11 (99 / 99) |
| 48 | 121 / 131 (72 / 69) | 10 / 10 (99 / 99) | 113 / 121 (75 / 73) | 10 / 10 (96 / 99) |

### db block — `avg_time_db_ms` (lan1 / lan2)

| seed | none | comp | stor | both |
|---|---|---|---|---|
| 42 | 2024 / 2126 | 4658 / 2890 | 69 / 64 | 81 / 533 |
| 43 | 2176 / 2047 | 3929 / 2800 | **1166 / 1796** (replacement) | 69 / 87 |
| 44 | 2197 / 2016 | 3962 / 2752 | 89 / **1932** | 69 / 70 |
| 45 | 2250 / 1861 | 4452 / 2778 | 64 / 66 | 72 / **870** |
| 46 | 2177 / 1830 | 3606 / 2787 | 60 / 58 | 62 / 61 |
| 47 | 2133 / 1959 | 4837 / 2773 | 60 / 61 | 170 / 79 |
| 48 | 2231 / 1967 | 4801 / 2797 | 68 / 545 | 53 / 56 ‡ |

### db block — episode completion % (lan1 / lan2)

| seed | none | comp | stor | both |
|---|---|---|---|---|
| 42 | 78 / 75 | 81 / 75 | 86 / 85 | 97 / 87 |
| 43 | 77 / 77 | 83 / 82 | 70 / 69 | 93 / 91 |
| 44 | 78 / 78 | 84 / 81 | 82 / 74 | 94 / 98 |
| 45 | 77 / 78 | 84 / 80 | 83 / 87 | 89 / 89 |
| 46 | 75 / 79 | 83 / 80 | 89 / 91 | 99 / 99 |
| 47 | 78 / 79 | 85 / 80 | 89 / 90 | 95 / 98 |
| 48 | 77 / 79 | 84 / 79 | 82 / 76 | 42 ‡ / 97 |

‡ `both_db_48` hit the edge OOM at episode onset (retained by author decision:
hard metrics intact, soft completion degraded).

### Mechanism exercise (medians per mode; lan1/lan2)

| block | storage adds | compute adds | renew broadcasts | `storage_band=` picks | members in episode | storage CPU % |
|---|---|---|---|---|---|---|
| mx/none | 0/0 | 0/0 | 0/0 | 15/16 | 1.0/1.0 | 42.1/41.2 |
| mx/comp | 0/0 | 3/3 | 0/0 | 64/61 | 1.0/1.0 | 51.9/51.5 |
| mx/stor | 7/7 | 0/0 | 6/6 | 33/39 | 4.0/5.0 | 28.4/27.7 |
| mx/both | 7/7 | 3/3 | 6/6 | 68/74 | 4.0/4.0 | 29.8/29.6 |
| db/none | 0/0 | 0/0 | 0/0 | 11/13 | 1.0/1.0 | 97.8/98.3 |
| db/comp | 0/0 | 1/1 | 0/0 | 20/22 | 1.0/1.0 | 98.7/98.7 |
| db/stor | 6/6 | 0/0 | 6/5 | 51/44 | 3.0/3.0 | 42.3/46.6 |
| db/both | 6/6 | 1/1 | 6/5 | 86/94 | 3.0/3.0 | 49.4/47.0 |

Culls: **0** in every run of both blocks. Manipulation checks hold exactly:
`none` adds nothing; `comp` adds only compute; `stor` adds only storage;
`both` adds both.

## Cross-Run Comparison

Mode ordering (median of per-seed lane-means across the 7 seeds; `seed 43` uses
the approved replacement):

| Block | none | comp | stor | both | Ordering |
|---|---|---|---|---|---|
| mx t_db (ms) | 103.0 | 9.8 | 89.7 | 6.2 | **both < comp ≪ stor < none** |
| mx t_proc (ms) | 124.1 | 10.4 | 114.9 | 10.3 | both ≈ comp ≪ stor < none |
| mx completion % | 70.6 | 98.4 | 74.0 | 98.9 | both ≈ comp ≫ stor > none |
| db t_db (ms) | 2075.0 | 3614.9 | 66.0 | 78.0 | **both ≈ stor ≪ none < comp** |
| db t_proc (ms) | 54.5 | 15.1 | 20.8 | 15.1 | both ≈ comp < stor < none |
| db completion % | 77.5 | 82.1 | 84.7 | 92.0 | both ≫ stor > comp > none |

Note on the db `stor` median: the median is 66 ms even though three seeds carry
the intermittency (per-seed lane-means 306.5 / 1010.5 / 1481 ms); the other
four are 59–66.5 ms. The healthy-only subset (all lanes < 1 s) is
`stor` 65 ms (n=5) and `both` 78 ms (n=7) — the intermittency does not move the
`stor` median but does widen its spread.

Graphs (archived in [`graphs/comparison/`](./graphs/comparison/)):
`fig1_mx_tdb_by_mode.png`, `fig2_db_tdb_by_mode.png`,
`fig3_mx_completion_by_mode.png`, `fig4_db_completion_by_mode.png`,
`fig5_mechanism_by_mode.png` (members present + storage-tier CPU per mode).
Regenerate with `python source/scripts/testing/analysis/rq2v5_plots.py
--cells rq2v5_cell_stats.csv --outdir graphs/comparison`.

## Judgment

### D24 hard gates

Materiality of "better" was registered by the author **after** all three
readings below were presented (D25, 2026-10-18: *"if the overall direction
stands then that's good enough"*) — i.e. **direction-only**. The stricter
readings are retained as sensitivity so the choice is auditable.

| Gate | Requirement | **Direction (registered, D25)** | ≥ 5 % (sensitivity) | ≥ 20 % (sensitivity) |
|---|---|---|---|---|
| **D1** `both`@db > `none` | t_db + relief | ✅ 7/7 | ✅ 7/7 | ✅ 7/7 |
| **D2** `stor`@db > `none` | t_db + relief | ✅ 7/7 | ✅ 6/7 | ❌ 5/7 |
| **D3** `both`@db > `comp` | t_db + relief | ✅ 7/7 | ✅ 7/7 | ✅ 7/7 |
| **D4** `stor`@db > `comp` | t_db + relief | ✅ 7/7 | ✅ 7/7 | ✅ 7/7 |
| **M1** `stor`@mx > `none` | any of t_db / t_proc / relief | ✅ 7/7 | ✅ 7/7 | ✅ 7/7 (via relief + t_proc; t_db alone is −13 %) |
| **M2** `comp`@mx > `none` | any of | ✅ 7/7 | ✅ 7/7 | ✅ 7/7 |
| **M3** `both`@mx > `none` | any of | ✅ 7/7 | ✅ 7/7 | ✅ 7/7 |
| **M4** `both`@mx > `stor` | any of | ✅ 7/7 | ✅ 7/7 | ✅ 7/7 |
| **M5** `both`@mx > `comp` | any of | ✅ 7/7 | ✅ 7/7 | ✅ 7/7 |

**Verdict (registered): all nine D24 hard goals are met.** D2 is the only gate
that moves under a stricter reading (6/7 at ≥ 5 %, 5/7 at ≥ 20 %), driven by
the delivery-intermittency cluster (below); its direction holds in 7/7 seeds on
both lanes. The mx gates are insensitive to the threshold because D24 lets them
pass on *any* of t_db/t_proc/relief, and relief is large everywhere
(static-tier CPU 42→28 %).

Client-visible metrics (soft): mx completion rises 71→99 % (both/comp) and
71→75 % (stor); db completion rises 77→94 % (both). `comp`@db improves
completion only marginally (77→82 %) and **worsens t_db**.

### Findings (ranked)

1. **`stor`@db relief is intermittent in 3 of 8 runs** (`43_r1` 1166/1796,
   `44` 89/1932, `48` 68/545) while the renewal census is complete in all of
   them (6/6 storage adds, 5–6 broadcasts, band picks present). The mechanism
   fires; the *delivery* of relief fails in ~1/3 of runs. Confirmed across three
   independent seeds/runs; the plan's risk §7.3 (wave-B selection with lagging
   member stats, `storage_band` picking a cold member) is the leading
   hypothesis, not yet proven. This is why D2 is threshold-sensitive.
2. **`comp`@db inverts `t_db`** (median 3.61 s vs `none` 2.08 s) while improving
   `t_proc` (51→15 ms) and completion (+5 pp). Removing edge serialisation
   pushes more requests onto the un-scaled storage tier, so the storage queue
   grows. This is the clean "wrong action" signature and is exactly why D24
   does not require `comp` to beat `none`.
3. **Edge-memory cap is marginal at press onset** — 2/56 runs OOM'd, both with
   ~367–370 MB RSS at episode onset against the 384 m cap (at 256 m the class
   killed 2/2 pilots mid-episode). Behavioural data survive (`both_db_48`: t_db
   52.8/56.4 ms), but the class is not closed; 512 m is the evidence-backed
   candidate for a post-campaign seat revision.
4. **Ordering (RQ2's headline):** mx = **both (6.4 ms) < comp (9.7) ≪ stor
   (90.4) < none (103.6)** — every arm beats `none` and `both` beats each
   single arm, in 7/7 seeds; db = `both`/`stor` at 66/78 ms vs `none` 2.08 s
   and `comp` 3.61 s. The v4 anomaly (`stor` ≈ `none` in mx and db) is gone.

### Threats to validity

- Materiality rule for "better" was not fixed pre-W4 (reported above).
- The OOM'd `stor_db_43` original (446/380 ms, completion 48.7 %) is superseded
  by the replacement; both are on disk.
- Per-lane renewal *fire* auditing is impossible post-hoc (edge containers are
  recreated each run and their logs are not captured) — the intermittency
  finding is inferred from census + outcome, not from edge-side fire logs.
- `both_db_48` completion (42 %) is an OOM artifact; its t_db is valid.

## Root Causes (issues found)

| # | Issue | Impact | Status |
|---|---|---|---|
| 1 | Relief delivery intermittency in `stor`@db (3/8 runs) | D2 threshold-sensitive; mx unaffected | Open — needs band/wave-B delivery study (hypothesis, plan §7.3) |
| 2 | `comp`@db t_db inversion | Explains "wrong action" cell; no gate requires otherwise | Explained (mechanism: edge serialisation removed → storage queue grows) |
| 3 | Edge OOM at press onset under 384 m | 2/56 runs incident; one replaced, one retained | Mitigated, not closed; 512 m candidate |

## Next Actions

1. **Author decision:** fix the D24 materiality rule (≥ 5 % ⇒ D2 passes 6/7;
   ≥ 20 % ⇒ D2 fails 5/7). Record as a new decision row before the verdict is
   written into the thesis.
2. Per-run `analysis/run_summary.md` generation (Edge Experiment Analyzer) and
   cross-mode comparison graphs → `graphs/comparison/`.
3. Transient cleanup (per-client request CSVs, controller logs) after the
   summaries are verified — pending explicit approval (irreversible).
4. Post-campaign engineering candidates: `EDGE_MEMORY=512m`; wave-B/band
   delivery investigation with per-connection auditing and edge-log capture.
5. Update `v4/rq2/experiment_plan.md` §5.2 G3 + `rq2v4_p5_03_mx_regime_report.md`
   §2.3 with the v5 override pointers (plan §6); documentation of the renewal
   trigger in `docs/operation/vip_routing/*`.

## Changelog

| Date | Change | Rationale |
|---|---|---|
| 2026-10-18 | Initial results.md — 56-run campaign + replacement analysed; D24 gate matrix under three materiality readings | W4 close-out of the v5 battery |
| 2026-10-18 | **D25 registered** (author): materiality = per-seed direction, no magnitude floor; verdict updated to "all nine hard gates pass"; ≥ 5 %/≥ 20 % retained as sensitivity | Author decision after all three readings were presented |
