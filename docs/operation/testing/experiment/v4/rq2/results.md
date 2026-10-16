# RQ2 v4 — Campaign Results (P6, cell-level verdicts)

> **Status:** campaign **complete** — **cell-level verdicts below are final**
> for the 89-run campaign (**84 valid / 5 excluded**; all cells **n = 7**).
> Authored 2026-10-16 by the P6 campaign analyst. Analysis was read-only on
> `cloud-vm-rq2` (no run, driver, config, or run folder touched; computations
> over finished folders only, F2-compliant); reviewed by the main session (auto-review gate, 2026-10-16) and committed with the counter-pass fixes applied.
> **Pre-registration:** [`experiment_plan.md`](experiment_plan.md) §2.2 claim
> rows + §5.1/§5.2 gate definitions + §5.3 cell-level rule (**≥ 6/7 replicates
> per cell**). Every deviation from the pre-registered surface (post-hoc
> registrations, stale rows, recompute flags) is listed in **§5 Adjudication
> register** — nothing is silently rewritten.
> **Run tally:** status CSV (`source/scripts/testing/metrics/rq2v4_run_status.csv`
> on `cloud-vm-rq2`): **91 rows = 2 R4-preflight + 89 campaign** = 84 valid /
> 0 pending / 5 excluded (cb 28/28 valid, mx 28/28, db 28/33). The five
> exclusions are all db and all one mechanism — in-episode container OOM
> (256 MB cap), the campaign's only incident class (§3 of
> [`rq2v4_p5_05_campaign_summary.md`](rq2v4_p5_05_campaign_summary.md));
> D20 (author, 2026-10-15) mandated n = 7 and authorised the three D20
> top-ups (`both_db_43_r2`, `stor_db_48_r1`, `none_db_42_r1` — all valid).

## Config seats (frozen; per `phases_snapshot.json` + `controller_env_snapshot.env` in every run)

| regime | episode | rate / client | mix | `EDGE_CPUS` | `STORAGE_CPUS` | arms | seeds |
| --- | --- | --- | --- | --- | --- | --- | --- |
| cb | 600 s | 0.23 | `{hash_challenge 1.0}` | 0.15 | 0.15 | both / comp / stor / none | 42–48 |
| mx | 600 s | 1.15 (R_m 1.15) | `{hash 0.205, lookup 0.795}` | 0.15 | 0.05 | both / comp / stor / none | 42–48 |
| db | 480 s | 5.0 | `{content_lookup 0.9, feed_ranking 0.1}` | 1.20 | 0.15 | both / comp / stor / none | 42–48 |

Common pins: `SCALEUP_POLICY=dual`, `TELEMETRY_SOURCE=zmq`,
`HASH_WORK_FACTOR=25000`, SS off; mode caps `both` 6/6 · `comp` 6/0 (+ reserve
off) · `stor` 0/6 · `none` 0/0 (+ reserve off); db run shape is the **v3 shape
carried, not re-calibrated** (Q3) at launcher pool 6 (v3 used pool 12) — a
recorded limitation, not a measured result. **D13:** mx storage quota (0.05)
and db storage quota (0.15) are quota-relative — cross-regime storage-CPU
numbers are never pooled.

## Provenance (tool → artifact → where)

| Tool (all read-only) | Produces | Used for |
| --- | --- | --- |
| `~/rq2v4_battery/g1lock.py` (+ `G1_EPISODE=mixed_episode` for mx, `=data_bound_episode` for db) | `~/rq2v4_battery/g1_<label>.json` | D12/G1 relief shares, lock, TTR; db latency-lock |
| `~/rq2v4_battery/p5mx.py` | `~/rq2v4_battery/mx_p5/<label>.json` | per-run completion/p50/p95x/timeout, D14 storage legs, engagement, domain CPU, policy shares |
| `~/rq2v4_battery/closeout_db_aux.py` | `db_aux.txt` / `db_aux_all.txt`; rerun `p6_repro/db_aux_rerun.txt` | db alert-anchored aux relief share, sampler coverage |
| `~/rq2v4_battery/p5check.py`, `db_finalize.py`, `setvalid.py` | `~/rq2v4_battery/evidence/<label>.txt`; status CSV cause strings | screening, MC battery, validity |
| `~/rq2v4_battery/bursts.py`, `band_census.txt` | P2.8/P5.04 band census | db anchor-absence evidence |

**P6 reproduction (this analysis).** Before any verdict was written, the frozen
tools were **re-run over the valid set** and diffed against the pre-P6
snapshot (`~/rq2v4_battery/p6_repro/` — `*.json` = pre-P6 copy,
`after/` = regenerated, `*.stdout` = tool output; driver `p6_rederive.py`):
**all 56 pre-existing g1 JSONs and all mx/db `mx_p5` JSONs regenerated
byte-identically**; the three D20 top-up rows were generated fresh; the only
non-identical outputs are **db `both` TTR/aux recompute flags, the `stor_db_48_r1` D14 boundary flag and the cb
`p5mx` descriptive-tail drift — all flagged in §5** (items 7 and 8). Run
folders: `source/scripts/testing/metrics/<ts>_rq2v4_<mode>_<regime>_<seed>[_r1|_r2]`
on `cloud-vm-rq2` (`ts` per label in the status CSV). All per-run numbers
below cite **tool + label**; the label resolves to its folder via the status
CSV.

---

## 1. Manipulation checks — verdicts

**n = 7 per cell** (7 blocks per regime; each block = both + comp + stor +
none at one seed; seeds 42–48; block order seed-rotated per regime).

| Check | Regime | Measured (valid runs) | Verdict |
| --- | --- | --- | --- |
| **MC1 press** (`none`, block-level) | cb | hash p95 ≥ 1 s in **93.8–100 %** of episode windows, 7/7 blocks | **PASS 7/7** |
| | mx | hash lock ≥ **95.3 %** (≥ 80); member CPU mean **38.8–40.9 %** (≥ 33); `storage_above_threshold` in **98.4–100 %** of policy rows (≥ 40) | **PASS 7/7** |
| | db | member CPU mean **67.2–69.7 %** (≥ 50); block 42 witness restored by `none_db_42_r1` (67.8/68.7) | **PASS 7/7** |
| **MC2 engagement** (per cell) | cb | both: 5–6 `ComputeAlert`s + 5–6 compute spawns/lane; comp: 4–6 alerts, 0 storage ops; stor: 0 compute ops (0 alerts/spawns), storage activations occur **only after the 600 s episode ends** (earliest at episode-start + 626 s — late activations also in 2/7 `both` runs; 0 within the episode proper, inert under the hash-only mix); none: 0 ops | **PASS all** (screener cause strings record `storage 0 inert`; the status-CSV cause prose's "alerts" counters are the screener's log-line counter — decision-row counts are these) |
| | mx | both: 3–4 alerts + 4–6 reserve activation rows (5–6 log lines) + 3–5 storage spawns/lane; comp: 3–4 alerts, 0 storage engagements; stor: reserve 6/6 every run, 0 alerts/0 compute spawns; none: 0 ops | **PASS all** |
| | db | both: 1 alert + 2–4 reserve activations/lane; comp: storage engagements **0**, compute alert 1/1 (descriptive; recorded); stor: 2–6 activations, 0 alerts/0 compute spawns; none: 0 ops | **PASS all** |
| **MC3 specificity** | stor@cb | lock 93.8–100 % (≥ 80), 0 compute spawns | **PASS 7/7** |
| | comp@db | 0 storage engagements; member CPU ≥ 50 % in **93.9–95.9 %** of episode windows (≥ 60) | **PASS 7/7** |
| | stor@mx | 0 `ComputeAlert` rows/spawns; hash p95 ≥ 1 s in **95.3–100 %** windows (≥ 90) | **PASS 7/7** |
| | comp@mx | 0 storage engagements; member ≥ 33 % in **90.6–96.7 %** windows (≥ 60) | **PASS 7/7** |
| **MC4 margin** (`none`, block-level) | cb | both halves ≥ **87.9 %** lock, 7/7 | **PASS 7/7** |
| | mx | both halves ≥ **93.8 %** lock, 7/7 | **PASS 7/7** |
| | db | halves ge50: lan1 **88.0–92.0 %**, lan2 **100 %** — sustained, 7/7 | **PASS 7/7** |
| **MC5 liveness contract** | all | 0 `triggering removal` lines for added units in all 84 valid runs; the only such line in the whole campaign is the **correct** dead-unit absence-cleanup of the OOM'd `comp_db_46` dyn unit (excluded run; P1 fix working as designed) | **PASS all** |
| **D3 config pins** | all | `phases_snapshot.json` matches the regime shape and `dual=True zmq=True hash25k=True` in every run (89/89 + both preflight) | **PASS all** |
| **F1/F2 flags** | all | no F1/F2 cause note on any valid row; the campaign's only F2 reading (`both_db_43`) was reclassified to the OOM class in D20 (P5.04 §6) | **no flags** |
| **D13 comparability** | mx vs db | storage presses are quota-relative (0.05 vs 0.15); never pooled | **stated** |

## 2. Gate battery per cell (pre-registered thresholds; **n = 7 per cell**)

Cell rule (plan §5.3): a benefit claim passes iff **≥ 6/7 replicates** meet
the per-run threshold on **both lanes**. Single runs are never evidence.

### 2.1 G1 — compute relief (D12)

Per-run threshold: hash-kind p95 < 1 s in **≥ 80 % of post-steady windows**
(anchor = first `spread band ≥ 4` burst → episode end), both lanes.

| cell | pre-registered | measured replicates (≥80 both lanes) | verdict | notes |
| --- | --- | --- | --- | --- |
| G1 both@cb | ≥ 6/7 | **5/7** — misses s43-lan1 78.6 %, s46-lan2 71.1 % | **❌ as-is** | P6.1 band-capped; artifact-excluded sensitivity **14/14 pass** (diagnostic; §5 item 5). All 5 misses across cb cells are 1–4 windows beyond the band |
| G1 comp@cb | ≥ 6/7 | **4/7** — misses s42/44/46 lan2 (76.2–78.6 %) | **❌ as-is** | same band handling |
| G1 both@mx | ≥ 6/7 | **7/7** (shares 83.7–95.7 %) | **✅ met** | 5/28 lane readings sit above the cb-derived ≈ 84–87 % cap (95.7, 95.7, 88.4, 88.4, 89.1) — consistent with a softer band effect on the lighter mx mix; no action (§5 item 5) |
| G1 comp@mx | ≥ 6/7 | **7/7** (81.4–95.7 %) | **✅ met** | as above |

Per-run detail (g1 JSONs; tool + label traceable):

- **both@cb** — 42: 84.4/86.7; 43: 78.6/85.7; 44: 91.1/83.3; 45: 90.5/86.7;
  46: 84.3/71.1; 47: 86.7/89.6; 48: 86.7/86.7 — **TTR median 57/104 s**
  (per-run lan1/lan2 TTR: 57/104, 108/103, 57/104, 55/102, 48/105, 105/112,
  103/100).
- **comp@cb** — 42: 91.1/76.2; 43: 85.7/85.7; 44: 88.9/78.6; 45: 88.1/84.4;
  46: 84.4/78.6; 47: 86.7/80.0; 48: 93.3/84.4 — **TTR median 67/106 s**
  (59/106, 99/113, 58/105, 69/105, 67/142, 105/101, 67/114).
- **both@mx** — 42: 95.7/84.8; 43: 86.0/83.7; 44: 86.0/86.0; 45: 86.0/87.0;
  46: 87.0/86.0; 47: 87.0/87.0; 48: 86.0/87.0 — **TTR median 74/95 s**.
- **comp@mx** — 42: 95.7/81.4; 43: 86.0/86.0; 44: 83.7/88.4; 45: 88.4/82.6;
  46: 87.0/86.0; 47: 87.0/84.6; 48: 86.0/89.1 — **TTR median 79/101 s**.

### 2.2 G2 / D14 — storage relief (and the db aux substitute)

Per-run threshold (frozen D14): busiest pre-add member's own-peak CPU < 0.75 ×
its own pre-add peak in **≥ 80 % of post-ready windows** (activation + 120 s →
end), both lanes; **read shares descriptive, never gated** (≈ 1 sample/window).

| cell | pre-registered | measured | verdict | notes |
| --- | --- | --- | --- | --- |
| G2 both@mx | ≥ 6/7 | literal **1/7** (s42 98.0/98.0 only); win-max **0/7** | **❌ as-is** | thin pre-add baselines (1–3-window peaks), member series source flips the busiest pick (s42-lan2 20.8 % ↔ 98.0 %), member CPU is delivery-bound at this seat (P5.03 §4). Reads do move — (descriptive, sampled single-run illustration: s45-lan1 post-ready shares ≈ 33 % on in-episode members; not a gate input) — but the gated CPU leg does not reproduce at cell level; the P3-pilot `mx_both` storage figures (82.0/95.7 %) are **superseded — not reproducible** (P5.3 §4.1) and are replaced by these campaign rows |
| G2 both@db | ≥ 6/7 | literal **5/7**, win-max **5/7** | **❌ as-is** | misses: s45 (lan1 2.9 %, lan2 54.3 %), s48 (lan2 11.8 %); s44-lan2 borderline **80.0** (counted **meet** per the frozen tool; alternative boundary handling reads 79.4 → still below the floor either way, §5 item 2). D14 TTR (frozen tool): 10 s in 11/14 lane readings; 60 s in s42-lan1; 210 s in the two miss lanes (s45-lan1, s48-lan2) — frozen-tool `43_r2` reads 10/10, published recompute read 60/70 (§5 item 7) |
| stor@mx storage | descriptive (plan §2.2: "measured, not assumed") | literal **0/7** (median 2.0/2.1 %); win-max **0/7** | **outcome recorded** (not a gate failure) | D18-registered no-relief; compute side unrelieved too (lock 95.3–100 %, MC3 ≥ 90 ✓) |
| stor@db storage | plan row says `storage relief ✓ (D14)` — **superseded by D18** | **0/7** (max reading 42.9 % s46-lan2; D20 top-up `stor_db_48_r1` 2.9/0.0 frozen-tool) | **expected post-D18** (no gate failure) | fixed edge set → reads move only via new connections → mid-press members receive none; registered 2026-10-14, §5 item 9 |
| db aux (alert-anchored share; **descriptive substitute** for the unevaluable D12 share) | — (descriptive) | both **6/7** (miss s42 73.9/68.9), comp **7/7**; meeting-run shares 87.0–93.5 %; TTR medians both **47/51 s**, comp **44/50 s** | **adopted as the descriptive db row** | frozen D12 anchor never occurs in db episodes (bands 1–3; sole ≥ 4 burst post-episode) — §5 item 1; db compute side stays descriptive per plan §2.2 |

### 2.3 G3 — comparator & mis-aligned arms (judged on their claimed direction)

| cell | threshold | measured | verdict |
| --- | --- | --- | --- |
| `none` @ cb/mx/db | MC1 + MC4 hold; 0 ops | presses hold 7/7 blocks per regime (values in §1); 0 elasticity ops in every block | **✅ 21/21 blocks** |
| stor@cb compute | lock ≥ 80 %, 0 compute spawns | lock 93.8–100 %, 0 spawns (activating only non-episode phases) | **✅ 7/7** |
| comp@db storage | 0 engagements; member ≥ 50 % in ≥ 60 % windows | 0 engagements; 93.9–95.9 % windows ≥ 50 % | **✅ 7/7** |
| stor@mx compute | 0 alerts; lock ≥ 90 % | 0 alerts/0 spawns; lock 95.3–100 % | **✅ 7/7** |
| comp@mx storage | 0 engagements; member ≥ 33 % in ≥ 60 % windows | 0 engagements; 90.6–96.7 % windows ≥ 33 % | **✅ 7/7** |

### 2.4 G4 — health ceiling (timeouts ≤ 5 % per run)

| cell | measured (valid rows, lan1/lan2 %) | verdict |
| --- | --- | --- |
| both@cb | 0.0/0.0 (max single reading 0.1 %) | **✅** |
| comp@cb | 0.0/0.0 (max 0.1) | **✅** |
| both@mx | 0.6/0.7–1.4 (all ≤ 2.1) | **✅** |
| comp@mx | 1.1–2.1 | **✅** |
| both@db | median 0.6/0.7; all ≤ 0.9 | **✅** |
| stor@db | **6.1–16.9** in all 7 valid rows | **scope note (adjudicated)** — see below |
| none / stor@cb / comp@db / stor@mx | exempt by pre-registration (comparators / no-recovery arms) | exempt |

**G4 scope note (adopted, §5 item 3):** the ≤ 5 % ceiling was calibrated on
cells pre-registered to recover. `stor`@db is structurally unrelieved under
D18 (its lanes sit at 2 s p50 / 10–20 s p95x *with* storage engaged — the
timeouts are the unrelieved press, not a health regression), so the ceiling
is read as **not applicable by scope** for that cell; the rows stay valid and
the numbers are reported as-is. Screening recorded the same reading (five of
the six pre-top-up valid rows carry the "G4 wording tension" cause note;
the D20 top-up row shares the cell-level tension).

### 2.5 Exclusions ≠ effect

The five excluded runs are all db, all the **single incident class**
(in-episode container cgroup OOM at the 256 MB cap under the db lookup
press — kernel-confirmed; P5.04 §6): `both_db_43` (reclassified (iii) → (i)),
`both_db_43_r1`, `comp_db_46`, `stor_db_48`, `none_db_42`. No cb/mx
exclusion exists; no MC gate failed as a consequence (block-42 witness
restored by the D20 top-up). Replacement/top-up policy per D20; spares used
**5 of ≤ 14** (author exception to the > 4 stop rule recorded). The incident
class is a **platform finding** (not a treatment effect) and does not enter
any cell verdict.

## 3. The RQ2 answer (synthesis)

**The 3×3 story.** RQ2 asks whether bottleneck-aware scale-up relieves the
pressed tier relative to fixed single-tier policies — and whether the wrong
tier helps instead. The campaign answers it cleanly, with two platform
constraints that frame the numbers.

1. **Aligned arms relieve the pressed tier.** Where the demand press is on
   the compute side — cb and mx — the aligned arms (`both`, `comp`) deliver
   a step change: cb p50 collapses from 2.28/2.73 s (`none`) to 0.21/0.21 s
   and 0.17/0.26 s with 100 % completion and 0.0 % timeouts (comparator:
   97.0/95.4 % completion); mx p50 drops from 10.0/10.2 s to 8–10 ms with
   99 % completion and 0.6–2.1 % timeouts (comparator: 72 % completion,
   27–29 % timeouts). The relief-window share meets the pre-registered bar
   in **mx 7/7 + 7/7 replicates**; in cb it is **band-capped at 5/7 + 4/7
   as-measured** (below the ≥ 6/7 floor) with every one of the 14 replicates
   passing once the registered 60 s re-arm band windows are excluded
   (14/14; diagnostic — see the constraint below). On the db row the
   compute side reads the same direction descriptively (alert-anchored share
   **comp 7/7, both 6/7**; TTR medians ≈ 44–51 s; episode latency-lock
   10.2–18.4 % for comp and 12.2–36.7 % for both (high end = s42) vs
   85.7–100 % for the stor/none comparators).
2. **Mis-aligned arms do not.** `stor`@cb never un-locks the hash press
   (lock 93.8–100 %, 0 compute spawns — specificity holds). `comp`@mx
   leaves storage unrelieved (member ≥ 33 % in 90.6–96.7 % of windows,
   0 storage engagements). `stor`@mx delivers no compute relief and no
   storage CPU relief (literal median 2.0/2.1 % of post-ready windows;
   lock 95.3–100 %). `stor`@db cannot relieve at all — **0/7 replicates**
   (one lane reading 42.9 % at a collapsed tail; D20 top-up 2.9/0.0) — which
   is the **pre-registered D18 expectation** for a fixed edge set, not an
   anomaly. `comp`@db never engages storage (0) and the db press persists.
3. **Comparators stay locked everywhere.** `none` medians: cb 2.28/2.73 s
   p50 with 98.4/96.8 % lock; mx 10.0/10.2 s with 98.4/100 % lock; db
   1.90/1.72 s with median 100/100 % latency-lock (min lane reading 85.7 %) —
   and every `none` run carries the press witness for its block
   (7/7 per regime).

**Two platform constraints frame the result (both registered mid-campaign,
neither a cause of any exclusion):**

- **P6.1 — the ~60 s VIP re-arm band** (arm-independent anti-relief
  artifact): once per minute a ~8–10 s band adds +0.3–1.4 s latency, failing
  6–7 of every 42–51 post-settle windows *even in fully relieved lanes* and
  thereby capping any window-share at ≈ 84–87 %. Handling adopted: (a)
  report as-is **plus** the artifact-excluded sensitivity as a diagnostic
  (93–98 % per P6.1 §3; an independent window-exclusion re-derivation in
  this analysis clears **all 14** cb aligned replicates, min lane 81.1 % —
  method detail in §5 item 5). The constraint affects the *window-share
  metric*, not the latency outcome (p50 ≈ 0.2 s / 8 ms, ~100 % completion).
- **D18 — read-path pinning**: storage reads move only through newly born
  connections; under a fixed edge set, storage capacity added mid-press
  receives no reads. Consequence: `stor`@mx/db no-relief is structural (the
  five storage-only cells' negative results are evidence about the
  platform, not about the policy logic), and `both`-arm storage relief is
  downstream of the compute spawn (new edge containers → new pools → new
  connections) — the tier-coupling asymmetry for the thesis narrative.

**Honest caveats (all recorded, none re-interpreted):** (i) thin pre-add
baselines make the D14 member-CPU leg source-sensitive at mx/db seats
(1–5-window peak estimates); (ii) D13 quota-relative storage presses — no
cross-regime pooling; (iii) db is the v3-carried shape (Q3) at pool 6
(v3: pool 12), never re-calibrated on the repaired platform; (iv) sampled
read shares are ≈ 1 sample/window — descriptive only; (v) the cb as-measured
G1 counts are band-capped (5/7, 4/7) and the sensitivity is a diagnostic,
not a gate redefinition; (vi) `both`@db G2 stands at 5/7 — below floor
under either reading of the s44 borderline; (vii) all db compute-side
numbers are descriptive (frozen D12 anchor structurally absent); (viii)
single-run values never carry verdicts — every cell above rests on n = 7.

## 4. Figure data for P6.2 (exact tables) and adaptation assessment

Planned P6.2 figures: relief per regime; latency per regime; engagement;
resource use. Tables below are **plot-ready** (medians across the cell's
n = 7 valid replicates unless stated; lanes l1/l2). Derivation: medians over
`mx_p5`/`g1` JSONs (regenerated, §Provenance); per-run relief arrays are
in §2.1/§2.2. All values traceable by label + tool as above.

**F1 — Relief per regime** (bar = cell share; dots = per-run values from
§2.1/§2.2 arrays):

| cell | n | relief metric | per-run shares (l1/l2) | cell value plotted |
| --- | --- | --- | --- | --- |
| cb both | 7 | G1 D12 share (as-is; sensitivity in note) | 84.4/86.7 · 78.6/85.7 · 91.1/83.3 · 90.5/86.7 · 84.3/71.1 · 86.7/89.6 · 86.7/86.7 | median 86.7/86.7; 5/7 ≥ 80 |
| cb comp | 7 | G1 D12 share (as-is) | 91.1/76.2 · 85.7/85.7 · 88.9/78.6 · 88.1/84.4 · 84.4/78.6 · 86.7/80.0 · 93.3/84.4 | median 88.1/80.0; 4/7 ≥ 80 |
| mx both | 7 | G1 D12 share | §2.1 | median 86.0/86.0; 7/7 |
| mx comp | 7 | G1 D12 share | §2.1 | median 87.0/86.0; 7/7 |
| db both | 7 | aux alert-anchored share (descriptive) | 73.9/68.9 · 91.1/89.1 · 89.1/87.0 · 91.3/91.1 · 91.1/87.0 · 89.1/89.1 · 89.1/89.1 | median 89.1/89.1; 6/7 |
| db comp | 7 | aux alert-anchored share | 89.1/87.0 · 93.3/89.1 · 93.5/93.3 · 93.3/93.3 · 91.3/91.1 · 91.3/91.1 · 91.1/91.3 | median 91.3/91.1; 7/7 |
| mx both | 7 | D14 storage share (literal) | 98.0/98.0 · 45.7/34.8 · 100/26.1 · 28.6/8.5 · 8.2/40.8 · 12.0/55.6 · 44.0/59.2 | median 44.0/40.8; 1/7 |
| mx stor | 7 | D14 literal | 2.0/2.1 · 0/0 · 0/10.9 · 23.4/2.1 · 0/19.6 · 4.1/0 · 4.1/4.2 | median 2.0/2.1; 0/7 |
| db both | 7 | D14 literal | 86.1/97.1 · 100/97.1 · 100/80.0 · 2.9/54.3 · 100/88.2 · 100/94.4 · 100/11.8 | median 100/88.2; 5/7 |
| db stor | 7 | D14 literal | 0/2.9 · 2.9/0 · 0/0 · 2.9/0 · 2.8/42.9 · 0/0 · 2.9/0 | median 2.8/0; 0/7 |
| cb stor / cb none | 7 | hash-lock % (comparators) | lock medians 95.3/100 and 98.4/96.8 (ranges §1) | from §2.1 table |
| mx stor / mx none | 7 | hash-lock % | 100/100 and 98.4/100 (ranges 96.8–100 / 95.3–100) | — |

*Note for the cb bars:* plot as-is; annotate the band-capped sensitivity
(14/14 pass under artifact exclusion) as a second, hatched bar or a note —
never blend the two into one statistic (P6.1 handling (a)).

**F2 — Latency per regime** (per-cell medians, l1/l2; n = 7):

| cell | completion % | p50 (s) | p95x (s) | timeout % | lock % (hash; db = latency-lock) |
| --- | --- | --- | --- | --- | --- |
| cb both | 100.0/100.0 | 0.212/0.213 | 1.87/1.97 | 0.0/0.0 | 31.2/32.8 |
| cb comp | 100.0/100.0 | 0.174/0.260 | 1.76/2.25 | 0.0/0.0 | 26.6/35.9 |
| cb stor | 97.6/98.7 | 2.15/2.68 | 7.99/14.06 | 1.1/0.5 | 95.3/100 |
| cb none | 97.0/95.4 | 2.28/2.73 | 20.68/22.15 | 1.7/1.7 | 98.4/96.8 |
| mx both | 99.1/99.1 | 0.008/0.009 | 6.21/6.31 | 0.9/0.9 | 25.4/29.5 |
| mx comp | 98.6/98.3 | 0.009/0.010 | 6.89/7.23 | 1.3/1.7 | 24.6/28.6 |
| mx stor | 76.7/75.7 | 8.93/9.23 | 22.37/22.49 | 22.9/24.1 | 100/100 |
| mx none | 72.3/71.0 | 10.02/10.22 | 23.25/23.48 | 27.3/28.6 | 98.4/100 |
| db both | 99.3/99.3 | 0.029/0.058 | 2.10/2.21 | 0.6/0.7 | 16.3/16.3 (range 12.2–36.7) |
| db comp | 99.8/99.8 | 0.027/0.049 | 1.21/1.31 | 0.2/0.2 | 14.3/16.3 (range 10.2–18.4) |
| db stor | 90.7/92.7 | 2.18/2.05 | 16.24/11.71 | 9.1/7.2 | 100/100 (range 95.9–100) |
| db none | 92.1/93.4 | 1.90/1.72 | 14.38/9.97 | 7.8/6.4 | 100/100 (range 85.7–100) |

**F3 — Engagement** (per-cell medians, l1/l2; ranges in §1; `none` = 0
everywhere):

| cell | alerts | reserve rows | reserve lines | compute spawns | storage spawns |
| --- | --- | --- | --- | --- | --- |
| cb both | 5/5 | 3/2 | 3/2 | 5/5 | 3/2 (non-episode phases only) |
| cb comp | 5/5 | 0/0 | 0/0 | 5/5 | 0/0 |
| cb stor | 0/0 | 3/2 | 3/2 | 0/0 | 3/2 (non-episode phases only) |
| mx both | 3/3 | 5/6 | 6/6 | 3/3 | 4/4 |
| mx comp | 3/3 | 0/0 | 0/0 | 3/3 | 0/0 |
| mx stor | 0/0 | 6/6 | 6/6 | 0/0 | 4/4 |
| db both | 1/1 | 3/4 | 3/4 | 1/1 | 3/4 |
| db comp | 1/1 | 0/0 | 0/0 | 1/1 | 0/0 |
| db stor | 0/0 | 3/3 | 3/3 | 0/0 | 3/3 |

**F4 — Resource use** (per-cell medians, l1/l2):

| cell | member CPU (domain mean %) | member ge50 share % | storage_above % (policy rows) |
| --- | --- | --- | --- |
| cb both | 7.4/7.3 | 0/0 | 0.8 |
| cb comp | 1.6/1.7 | 0/0 | 0.0 |
| cb stor | 6.8/6.8 | 0/0 | 0.0 |
| cb none | 1.3/1.6 | 0/0 | 0.0 |
| mx both | 30.1/30.0 | 0/0 | 89.1 |
| mx comp | 49.1/48.4 | 68.9/62.5 | 96.0 |
| mx stor | 28.5/27.7 | 0/0 | 98.4 |
| mx none | 40.4/39.8 | 0/0 | 99.2 |
| db both | 32.4/32.9 | 4.1/6.1 | 83.3 |
| db comp | 71.7/73.1 | 95.9/95.9 | 86.4 |
| db stor | 30.1/30.8 | 4.2/6.1 | 84.2 |
| db none | 68.3/69.2 | 95.9/95.9 | 83.3 |

*Reading note:* member CPU is a **delivery-bound signal** at the mx/db seats
(invariant to offered rate at these quotas) — the resource figure shows the
press domain and the effect of tier choice; it is not a capacity-utilisation
metric.

**Adaptation assessment (no PNGs produced here).** The v3-era scripts under
`source/scripts/testing/analysis/rq2/` were inspected: `campaign_analysis.py`
and `regenerate_rq2_graphs.py` hardcode v3 run labels/phases/modes;
`pooled_comparison_graphs.py` reads per-run `client_requests.csv`
(v4-folder-compatible) but hardcodes the v3 topology-arm vocabulary.
Adaptation is therefore **not a read-only exercise** — the v4 figures need a
new/adapted driver, which is exactly what plan §6.2 assigns to P6.2
("adapt … into rq2v4 variants as needed") and the repository
`cross-mode-comparison` skill governs (plan-driven vocabulary resolution,
per-replicate variance dots mandatory, archive to
`<experiment_dir>/graphs/comparison/`). **What remains for P6.2, precisely:**
(1) write/adapt the v4 comparison driver consuming the §4 tables (or the
`mx_p5`/`g1` JSONs) with axes regime × arm; (2) plot F1–F4 as bar charts
(F1 split as-is vs sensitivity for cb; db compute bars carry the
"descriptive" label; stor cells carry the D18 annotation); (3) keep the
RQ1-v8 style constants (10×6 in, DPI 150, bar labels bold, y-grid α 0.25)
per the existing scripts; (4) add per-replicate scatter dots — a graph
without variance dots does not meet the comparison standard; (5) archive
PNGs + their CSV inputs under
`docs/operation/testing/experiment/v4/rq2/graphs/comparison/`; (6) attach
the figure-data CSVs (one per F-table) so the thesis figure workflow can
pick them up. Do not use AI image generation for any of these.

## 5. Adjudication register (P6 items resolved)

| # | Item (source) | Decision | Rationale (one line) |
| --- | --- | --- | --- |
| 1 | D12 anchor-absence in db (P5.04 §8.1) | **Accept the aux alert-anchored share as the descriptive db row** (both 6/7, comp 7/7; TTR endpoint as frozen); no db annex to the D12 anchor rule, no gate redefinition | the anchor is structurally absent (bands 1–3); the aux metric is transparent, labeled descriptive, and the db compute side was pre-registered descriptive anyway |
| 2 | both@db G2 math at n = 7 (P5.04 §8.2; s44-lan2 borderline) | **G2 not met: 5/7** (literal; win-max identical); s44-lan2 **counted meet at the frozen tool's 80.0** (alternative boundary handling 79.4 only lowers the count); the ≥ 6/7 floor is missed under either reading | the borderline cannot change the verdict; recording it as meet-or-miss is immaterial to the cell outcome and both readings are stated |
| 3 | stor@db G4 wording tension (P5.04 §5.1/§8.3) | **Scope note adopted:** the ≤ 5 % ceiling is read as calibrated on recovering cells; stor@db (D18-unrelieved) is out of scope; rows stay valid, numbers reported as-is (6.1–16.9 %) | timeouts in stor@db are the unrelieved press, not a health regression; no row's validity depended on the reading |
| 4 | OOM class / D20 n = 7 (P5.04 §8.4) | **Acknowledged as closed:** exclusions = one incident class; all cells n = 7; spares 5/≤14; `both_db_43` reclassification (iii)→(i) is recorded in D20 + P5.04 §6 (satisfies the "mirror in preparation.md" pointer — D20 is the mirror; an optional cross-ref line in the D19 row is left to the main session) | the evidence and the author decision are in the log; nothing further needed for correctness |
| 5 | P6.1 handling (P6.1 §5) | **(a) adopted:** report as-is + artifact-excluded sensitivity as a diagnostic; stated for cb (5/7, 4/7 as-is; 14/14 under exclusion); mx/db inherit as-is with no band-window adjustments | the band is arm-independent and pre-dates any scaling; sensitivity is diagnostic-only by the registered policy. *Method flag:* independent re-derivation (drop the one window per minute containing the band) clears 14/14 with min lane 81.1 %, it does not reproduce P6.1's exact 93–98 % range (different exclusion granularity); P6.1's registered range is quoted as the headline sensitivity |
| 6 | P3-pilot D14 discrepancy (P5.03 §4.1/§7.3) | **Campaign-cell numbers are authoritative; the pilot row `mx_both` 82.0/95.7 % is superseded — not reproducible** from archived artifacts; recorded in the mx storage rows (§2.2, above). Correction note added 2026-10-16 in `preparation.md` (D14 row) | bounded re-derivation (P5.03 §4.1) exhausted the convention grid; the campaign tables stand on their own stated conventions; history stays visible via the note |
| 7 | D20 top-up recompute flags (this analysis) | Frozen-tool recomputes **adopted with flags** for `both_db_43_r2`: aux 91.1/89.1 (published 88.9/87.0; +2.2 pp > 2 pp boundary tolerance), compute-side TTR 47/53 s (published 60/70 — first-relief window boundary; the trace crosses < 1 s at +46 s/+52 s after the first alert), D14 storage TTR 10/10 s (published 60/70). `stor_db_48_r1` D14 lan1 2.9 % (published 0.0). Cell medians printed above use the frozen-tool values (both compute-TTR med l1 **47** vs published 54; comp unchanged 44/50; D14-TTR triage in §2.2 uses frozen values); cell counts/verdicts unchanged | method rule: deviations beyond convention tolerance are flagged, not silently kept; neither flag moves a replicate count or verdict |
| 8 | cb `p5mx` descriptive-tail drift (this analysis) | No action: regenerated cb JSONs differ from the screening-era copies only in storage-descriptive fields (pre_n ±1 window, winmax peak, `maxnode_n`) — none read by any cb gate; published cb numbers stand | tool revision after the cb batch touched only legs that are inert in cb (hash-only mix); headline metrics regenerated identical |
| 9 | Stale plan rows (P5.05 §2.2 note; this analysis) | **Supersession stated (plan not rewritten):** (a) db `stor` `storage relief ✓ (D14)` → superseded by D18 for fixed-edge-set runs (measured 0/7 = post-D18 expectation); (b) mx `both` "both tiers relief ✓ (D12 + D14)" → the D14 storage leg is **not met** (1/7 literal, 0/7 win-max) and is recorded with its measurement caveats; the D12 leg is met (7/7) | post-hoc registrations (D18 + the P5.03 §4 caveats) govern; the register keeps the pre-registration honest |
| 10 | P5.05 §6 "81/86 runs valid" line | **Micro-inconsistency flagged and corrected 2026-10-16:** authoritative tally is **84 valid / 89 campaign folders / 5 excluded** (status CSV); the §6 line was a pre-top-up remnant and now reads 84/89 | keeps the count contract (counts must reconcile with the status CSV) |
| 11 | mx G1 shares above the cb-derived band cap (P5.03 §3) | No action: 5/28 lane readings 88.4–95.7 % exceed the ≈ 87 % cap; consistent with a lighter band effect on the mx mix; recorded as a stated observation | the cap was derived on cb; mx passes as-is regardless; nothing recomputed |
| 12 | stor@cb whole-run activation counts (this analysis) | Recorded precisely: storage activations occur **only after the 600 s episode ends** (earliest activation at episode-start + 626 s — late activations also in 2/7 `both` runs; 0/7 `stor` runs inside the episode); MC2 stays PASS | protects the "storage inert in cb" reading against the whole-run counts visible in `mx_p5` engagement fields |
