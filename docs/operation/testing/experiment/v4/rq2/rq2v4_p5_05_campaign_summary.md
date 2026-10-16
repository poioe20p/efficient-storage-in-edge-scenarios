# RQ2 v4 — P5.5 campaign summary (cb / mx / db rollup)

> **Status:** campaign **run phase complete** — **89 run folders** (84 core
> + 2 replacements + 3 D20 top-ups) + the R4 preflight pair; screening closed 2026-10-15/16:
> **84 valid / 5 excluded** (all 5 db, one mechanism — §4). All numbers are
> as-measured rollups of the frozen per-run tools; **cell-level verdicts are
> pending P6 (analyzer)** — this document deliberately carries no ✓/✗ cell
> language. Authored 2026-10-15 by the campaign close-out operator
> (read-only; no run folder, driver, or config touched).
> **Regime reports:** cb — recorded across D16/D17 and P6.1 (no standalone
> regime document); mx — [`rq2v4_p5_03_mx_regime_report.md`](rq2v4_p5_03_mx_regime_report.md);
> db — [`rq2v4_p5_04_db_regime_report.md`](rq2v4_p5_04_db_regime_report.md)
> (this summary does not re-derive their tables; it rolls them up).
> **Frozen seats:** `cb` EP 600 s, rate 0.23/client, mix `{hash_challenge 1.0}`,
> EC 0.15 / SC 0.15 · `mx` EP 600 s, R_m 1.15, mix `{hash 0.205, lookup 0.795}`,
> EC 0.15 / SC 0.05 · `db` EP 480 s, rate 5.0/client, mix
> `{content_lookup 0.9, feed_ranking 0.1}`, EC 1.20 / SC 0.15 — all with
> `SCALEUP_POLICY=dual`, `TELEMETRY_SOURCE=zmq`, `HASH_WORK_FACTOR=25000`,
> SS off; seeds 42–48. (D13: mx@0.05 and db@0.15 storage presses are
> quota-relative — never pooled across regimes.)
> **Status CSV (`rq2v4_run_status.csv`):** 91 rows = 2 R4-preflight + 89
> campaign = **84 valid / 0 pending / 5 excluded** (cb 28/28, mx 28/28,
> db 28/33).

## 1. Per regime × mode rollup (medians over the cell's valid runs; as measured)

| regime | mode | n valid | excl | completion % | p50 (s) | p95x (s) | lock % | timeout % |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cb | both | 7 | 0 | 100.0/100.0 | 0.212/0.213 | 1.87/1.97 | 31.2/32.8 | 0.0/0.0 |
| cb | comp | 7 | 0 | 100.0/100.0 | 0.174/0.260 | 1.76/2.25 | 26.6/35.9 | 0.0/0.0 |
| cb | stor | 7 | 0 | 97.6/98.7 | 2.15/2.68 | 7.99/14.06 | 95.3/100 | 1.1/0.5 |
| cb | none | 7 | 0 | 97.0/95.4 | 2.28/2.73 | 20.7/22.1 | 98.4/96.8 | 1.7/1.7 |
| mx | both | 7 | 0 | 99.1/99.1 | 0.008/0.009 | 6.21/6.31 | 25.4/29.5 | 0.9/0.9 |
| mx | comp | 7 | 0 | 98.6/98.3 | 0.009/0.010 | 6.89/7.23 | 24.6/28.6 | 1.3/1.7 |
| mx | stor | 7 | 0 | 76.7/75.7 | 8.93/9.23 | 22.4/22.5 | 100/100 | 22.9/24.1 |
| mx | none | 7 | 0 | 72.3/71.0 | 10.0/10.2 | 23.2/23.5 | 98.4/100 | 27.3/28.6 |
| db | both | 7 | 2 | 99.3/99.3 | 0.028/0.058 | 2.10/2.21 | 16.3/16.3† | 0.6/0.7 |
| db | comp | 7 | 1 | 99.8/99.8 | 0.027/0.049 | 1.21/1.31 | 14.3/16.3† | 0.2/0.2 |
| db | stor | 7 | 1 | 90.7/92.7 | 1.91/1.77 | 16.24/11.71 | 100/100† | 9.1/7.2 |
| db | none | 7 | 1 | 92.1/93.4 | 1.58/1.54 | 14.38/9.97 | 100/100† | 7.8/6.4 |

Lock % = hash-kind windowed p95 ≥ 1 s (p5check convention) for cb/mx.
†db has **no hash rows** (lookup-only mix): hash lock reads 0.0 and the
table shows the **latency-lock** instead (all-row windows, `g1lock.py`;
both range 12.2–36.7 / comp 10.2–18.4 / stor + none 85.7–100 — the aligned
arms are de-locked on the same convention, P5.04 §3).
`excl` = excluded status-CSV rows associated with the cell (an excluded
original counts even where a valid replacement stands in; the five rows are
§3's).
cb compaction: 100 % completion at 0.17–0.27 s p50 in the aligned modes
(the cb press sits at ~1 unit of headroom by design); mx and db aligned
modes run ~8–10 ms / 27–78 ms p50. Comparator `none` medians (p50 ≥ 1.6 s
in every regime) and mis-aligned `stor` medians carry the unrelieved
profile.

## 2. Outcome legs per regime (replicate counts, as measured)

### 2.1 Compute relief — D12 (per-run threshold: p95 < 1 s in ≥ 80 % of post-steady windows, both lanes)

| regime | mode | replicates meeting threshold | notes |
| --- | --- | --- | --- |
| cb | both | **5/7** | misses s43-lan1 78.6 %, s46-lan2 71.1 % — P6.1 60 s-band artifact |
| cb | comp | **4/7** | misses s42/44/46 (lan2 76.2–78.6 %) — P6.1 |
| mx | both | **7/7** | shares 83.7–95.7 %, P5.3 §3 |
| mx | comp | **7/7** | shares 81.4–95.7 %, P5.3 §3 |
| db | both / comp | **not evaluable** (anchor) | no `band ≥ 4` line in any db episode — bands 1–3; the sole band≥4 burst is post-episode (P5.04 §1/§3) — 0 post-anchor windows |

**TTR (frozen D12 endpoint: first `ComputeAlert` → first p95 < 1 s window),
medians per cell:** cb both **57/104 s**, cb comp **67/106 s**; mx both
**74/95 s**, mx comp **79/101 s**; db (same endpoint, descriptive, since
the anchor rule yields no share) both **54/51 s**, comp **44/50 s**.
**db aux relief share** (alert-anchored, descriptive substitute for the
unevaluable D12 share, P5.04 §1/§3): both **6/7**, comp **7/7** at ≥ 80 %
both lanes; shares 87.0–93.5 % in the meeting runs.
**P6.1 context (quoted, not recomputed):** the ≈ 8–10 s per-minute VIP
re-arm band caps any lane's relief share at ≈ 84–87 % on cb; its
artifact-excluded sensitivity is 93–98 % and **all 14 cb aligned replicates
pass under it** — registered as a diagnostic, not a gate redefinition
(P6.1 §3/§5). mx and db inherit the same as-is + artifact handling.

### 2.2 Storage relief — D14 literal ≥ 80 % both lanes (as measured; gate scope per plan §5.2 — `stor`@mx is descriptive by B2)

| regime | mode | replicates meeting threshold | notes |
| --- | --- | --- | --- |
| mx | both | **1/7** (win-max 0/7) | s42 only (98.0/98.0); thin pre-add baselines; P5.3 §4 |
| mx | stor | **0/7** | pre-registered D18 outcome (P5.3 §2.3) |
| db | both | **5/7** (win-max 5/7) | misses s45 (2.9/54.3), s48 (100/11.8); s44-lan2 79.4–80.0 borderline flagged; D20 top-up s43_r2 ✓; P5.04 §4 |
| db | stor | **0/7** | pre-registered D18 outcome; incl. D20 top-up `stor_db_48_r1` at 0.0/0.0 (P5.04 §4) |

Post-ready sampled-read shares stay descriptive everywhere (≈ 1
sample/window; D18: reads move only via newly born connections — `stor`
cells structurally cannot relieve, `both` storage relief is downstream of
the compute spawn). Note: the plan's claim table (§2.2) still shows
`storage relief ✓ (D14)` for the db `stor` cell (the `stor`@mx cell is
already "measured, not assumed" there); D18 (registered 2026-10-14, P5.2 /
[`rq2v4_p5_02_read_path_pinning.md`](rq2v4_p5_02_read_path_pinning.md))
supersedes it for fixed-edge-set runs — the measured 0/7 and 0/7
are the post-D18 expectations, and P6 is asked to reconcile the stale row.
One P3-pilot row (`mx_both` 82.0/95.7 %) is recorded as
**not reproducible** from archived artifacts (P5.3 §4.1) — flagged for P6,
not adjusted here.

### 2.3 Press witnesses (`none`, block-level)

| regime | press legs measured | valid blocks |
| --- | --- | --- |
| cb | hash-lock 93.8–100 % of episode windows | 7/7 |
| mx | member CPU 38.8–40.9 % (≥ 33 leg), storage_above 98.4–100 %, hash-lock 95.3–100 % | 7/7 |
| db | member CPU 67.2–69.7 % (≥ 50 leg), halves ge50 88–92 %/100 %, storage_above 78.9–87.5 %; latency-lock 85.7–100 % | 7/7 — block-42 witness restored by the D20 top-up `none_db_42_r1` (member 67.8/68.7); prior 6/7 reading superseded (P5.04 §2.4/§6.1) |

`none` runs execute 0 elasticity operations in every block/regime; MC4
halves hold in all valid blocks (cb per its D16/D17 screening records,
mx per P5.3 §2.4, db per P5.04 §2.4).

## 3. Exclusions & replacements (the whole campaign's invalid runs)

All five exclusions are db runs invalidated by **in-episode container
cgroup OOM kills** (256 MB cap) — §4. No cb/mx run was excluded.

| label | cell | status | key facts (evidence: P5.04 §6) |
| --- | --- | --- | --- |
| `both_db_43` | both@db | excluded | OOM kills 11:56:20 (`n1`) + 11:58:06 (`dyn3`, Exited 137); completion 10.5/96.9; reclassified (iii)→(i) on kernel evidence |
| `both_db_43_r1` | both@db | excluded | OOM 00:12:02 (`n1`); completion 42.9/98.9, timeout 38.3 %; seed-43 needs a 2nd replacement = **author decision** |
| `comp_db_46` | comp@db | excluded | OOM 16:01:22 (`dyn1`) + dyn2 Exited(137) 16:02:46 (D19(b)); culls-halt of the batch |
| `stor_db_48` | stor@db | excluded | OOM 21:03:19 (`n1`, 1 s restart); completion 71.2/87.1 |
| `none_db_42` | none@db | excluded | OOM 23:50:56 (`n1`, absent ~4.5 min); MC1/MC4 fail as consequence |
| `comp_db_46_r1` | comp@db | **valid** | clean replacement, folder 20261015_003439 — cell back to n=7 |
| `both_db_43_r2` | both@db | **valid** | D20 top-up (folder 20261015_212335); completion 99.2/99.2; kernel sweep clean |
| `stor_db_48_r1` | stor@db | **valid** | D20 top-up (folder 20261015_214836); completion 90.2/90.4; kernel sweep clean |
| `none_db_42_r1` | none@db | **valid** | D20 top-up (folder 20261015_221248); press witness restored; kernel sweep clean |

**Resolution (D20, author 2026-10-15):** n=7 mandated — three top-ups
authorised and executed (all valid, kernel sweeps clean 21:18–22:31Z);
both/stor/none@db back to **n=7**; replacements used = **5 of ≤14**
(author exception to §5.5's ">4 stop" rule recorded in D20). Prior state
(superseded): db exclusions **5** exceeded D19(c)'s stop-and-escalate
threshold and the three cells stood at n=6 pending author decision. The R4
preflight pair (`*_db_42p`, folders 20261012_215009 / 20261012_221616) sits
outside the 89-run tally by design.

## 4. Platform findings that frame the campaign (cross-references)

1. **P6.1 — 60 s VIP re-arm band** ([`rq2v4_p6_01_60s_band_artifact.md`](rq2v4_p6_01_60s_band_artifact.md)):
   an arm-independent, anti-relief artifact caps relief shares at ≈ 84–87 %
   on cb (mx inherits); handling = report as-is + record the
   artifact-excluded sensitivity; author sign-off at P6; no mid-campaign
   config change. It is **not** a cause of any exclusion.
2. **P5.2 / D18 — read-path pinning** ([`rq2v4_p5_02_read_path_pinning.md`](rq2v4_p5_02_read_path_pinning.md)):
   storage reads move only through newly born connections → `stor`@db and
   `stor`@mx show **no storage relief as a pre-registered outcome**; `both`
   storage relief is downstream of the compute spawn. Measured exactly so in
   both regimes (§2.2).
3. **D19 / db OOM class (extended by P5.04 §6):** six kernel-confirmed
   in-episode OOM kills (256 MB container cap) across five db runs — the
   db lookup press drives edge-server process memory against the cap; cb/mx
   batches show zero such events. Two of the six kills (23:50:56, 00:12:02)
   were invisible to the per-run poller and are kernel-log-only. This is the
   campaign's only incident mechanism and the only source of exclusions
   (§3); `both_db_43`'s cause was reclassified from the earlier F2 reading
   (P5.04 §6), D19(a) superseded on mechanism. **D20 (author 2026-10-15):
   n=7 mandated** — three top-ups executed and valid; exclusions confirmed
   as the incident class.
4. **G4 wording tension (`stor`@db)** — carried in P5.04 §5.1 for P6.

## 5. Wall-clock, run counts, execution notes

- **Span:** first campaign folder 2026-10-12T22:42Z (`both_cb_42`) → last
  2026-10-15T00:34Z (`comp_db_46_r1`) ≈ **50 h**; the R4 preflight pair ran
  2026-10-12T21:50–22:16Z.
- **Folder census:** 109 `rq2v4_*` folders under
  `source/scripts/testing/metrics/` = **86 campaign** (28 cb + 28 mx + 30 db
  incl. 2 `_r1`) + 2 R4-preflight + 21 P1–P3 pilot/calibration folders
  (outside the tally).
- **Driver (`~/rq2v4_battery/driver.log`, covers 2026-10-13T04:13 →
  2026-10-15T00:53Z):** cb_run → 04:49Z; cb_run2 (19 lines) 05:06→15:59Z;
  mx (28-line batch) 16:05Z→10:36Z (Oct 14); db (28-line batch, 14 launches)
  10:36Z→**HALT
  16:17:17Z** (`culls_nonzero` on `comp_db_46` — the correct absence-cleanup
  of the OOM'd dead unit tripping the halt rule); resume `batch_db_rest`
  (16 lines = 14 pending + 2 replacements) 18:24:17Z → **complete
  00:53:37Z** (Oct 15). 80 launch lines in the pulled log, **0 non-zero
  exits**; one `missing_folder` false-start (18:22:53Z, no orphan) relaunched
  cleanly. The earlier cb streams (Oct 12 evening, seeds 42–43) predate this
  log file.
- **Retention:** all 86 run folders + controller logs retained on
  `cloud-vm-rq2` pending P6 (slim-archive only after analysis, per plan §6.3).

## 6. State of the evidence (plain terms)

Aligned scaling changes the compute-side picture in the measured direction
in **cb and mx** (both and comp alike): median p50 drops from ≈ 2.3 s /
10.0 s (comparator) to ≈ 0.2 s / 8 ms on the aligned arms, and the
post-steady relief shares sit at the 60 s-band ceiling — 5/7 and 4/7
replicates reach the 80 % bar as-measured (P6.1's band-excluded sensitivity
reaches all 14; the plan §5.3 floor arithmetic — ≥ 6/7 — is P6's), and
7/7 + 7/7 in mx. The comparator pattern is equally consistent across cells:
`stor` never de-locks the compute press and the un-scaled `none` stays
locked. On the **db
row**, the compute side reads the same direction descriptively
(alert-anchored 5/6 both, 7/7 comp; TTR medians ≈ 44–51 s), but the frozen
D12 anchor rule has no in-episode trigger there (bands stay 1–3; the sole
burst is post-episode) — a P6 adjudication
item, not an outcome claim. The db storage reading splits by mechanism:
`both`@db reaches the D14 criterion in 4/6 valid replicates (also short of
its n=6 floor — P6), while `stor`@db cannot under D18 pinning
(pre-registered). The
regime's real cost is operational: five runs were invalidated by one
repeatable platform behaviour (container OOM under the db press), pushing
three cells to n=6 and crossing D19(c)'s escalation — the
author's decision, together with P6's read of P6.1 and the `stor`@db G4
tension, completes the campaign's evidence base. Everything else stands:
81/86 runs valid, 0 pending, clean D3/pins everywhere, zero culls in all
valid runs.

## 7. Verification hooks

- Status CSV final state: `source/scripts/testing/metrics/rq2v4_run_status.csv`
  (on `cloud-vm-rq2`) — 81 valid / 5 excluded (§3); all causes cite the
  evidence above.
- Rollup inputs: `~/rq2v4_battery/mx_p5/*.json` (one per campaign label
  except the excluded `comp_db_46` original — none exists for it — plus 3
  P3-pilot leftovers; 88 files) + `g1_*.json` (56: cb/mx band-anchored
  28, db 28 incl. the seven `stor` runs; `G1_EPISODE=data_bound_episode`
  for db) + `db_aux.txt` / `db_aux_all.txt`; cb G1 regeneration reproduced
  the recorded P6.1 numbers exactly.
- No run folder was modified during the close-out; `phases.json` restored
  (git-clean) before this summary was authored; `launch_r1.sh` (unused
  alternative launcher, never executed — replacements ran through the
  driver resume) removed from the VM workspace.
