# RQ2 v4 — Post-Run Analysis (capstone)

> **Status:** campaign **complete** (2026-10-15/16) · authored 2026-10-16 by
> the P6 campaign analyst. Synthesises — it does not duplicate —
> [`experiment_plan.md`](experiment_plan.md) (pre-registration),
> [`results.md`](results.md) (cell-level verdicts, figures data, adjudication
> register), the regime reports
> [`rq2v4_p5_03_mx_regime_report.md`](rq2v4_p5_03_mx_regime_report.md) /
> [`rq2v4_p5_04_db_regime_report.md`](rq2v4_p5_04_db_regime_report.md) /
> [`rq2v4_p5_05_campaign_summary.md`](rq2v4_p5_05_campaign_summary.md), and
> the two registered platform findings
> ([`rq2v4_p6_01_60s_band_artifact.md`](rq2v4_p6_01_60s_band_artifact.md),
> [`rq2v4_p5_02_read_path_pinning.md`](rq2v4_p5_02_read_path_pinning.md)).
> All per-run evidence is on `cloud-vm-rq2`
> (`~/rq2v4_battery/…`, run folders under
> `source/scripts/testing/metrics/<ts>_rq2v4_<arm>_<regime>_<seed>`).

## 1. Objective

RQ2 asks how **bottleneck-aware scale-up** affects targeted-tier relief,
service recovery, and resource use under compute-bound and data-access-bound
demand, compared with the fixed single-tier policies an operator would
otherwise configure (canonical thesis wording, `tese/main.tex` §1.3; results
panel Ch5 §5.3). The v4 campaign re-tested this on the **repaired platform**
(P1 liveness/cull fix; P2.6/P2.8 backend-selection spread and band floor)
after the v3 era — the pre-registered hypothesis (plan §2.2): under a
compute-bound (cb), mixed (mx) and data-bound (db) press, the aligned arms
(`both`; `comp` on cb/mx; `stor` on db) **relieve the pressed tier across 7
replicates**, the misaligned arms show **no benefit** (specificity, G3), and
the no-action comparator stays locked. The independent variable is the
**scaling-mode capability ablation** (which tier the controller may scale:
6/6 · 6/0 · 0/6 · 0/0), holding regime, seed, quotas and pins fixed.

## 2. Mechanism

- **Design.** 21 blocks × 4 arms = **84 runs** (cb/mx: 600 s episode, rate
  0.23 / 1.15 per client; db: 480 s, rate 5.0, v3-carried shape), seeds
  42–48, Latin-square arm order within blocks, regime-major execution;
  counterbalanced block order per regime. One shared seed/block ⇒ each
  block's `none` run is its press witness.
- **Configuration (frozen seats).** cb EC/SC 0.15/0.15; mx 0.15/0.05
  (R_m 1.15, mix 0.205/0.795); db 1.20/0.15; `SCALEUP_POLICY=dual`,
  `TELEMETRY_SOURCE=zmq`, `HASH_WORK_FACTOR=25000`, scaling suppression off;
  D3 provenance snapshots present in every run.
- **Measurement.** Frozen per-run tools (`g1lock.py` with `G1_EPISODE`
  overrides; `p5mx.py`; `closeout_db_aux.py`; screening via `p5check.py` /
  `db_finalize.py`), cell rule ≥ 6/7 replicates on both lanes (plan §5.3),
  n = 7 mandated (D5/D20).
- **Mid-campaign registrations (kept, not hidden):** the **60 s VIP re-arm
  band** (P6.1) — arm-independent anti-relief artifact capping window-share
  metrics at ≈ 84–87 % on the compute-bound regime (the mixed regime reads
  above the cap; results.md §2.1); **D18 read-path pinning** — storage reads move only
  via newly born connections (fixed edge set ⇒ mid-press storage capacity
  receives no reads); **db OOM incident class** (D19/D20) — 5 excluded db
  runs, three D20 top-ups restoring n = 7, block-42 witness restored.

## 3. Results

### 3.1 Pre-registered criteria — verdicts (details in `results.md` §2)

| Criterion | Verdict | One-line evidence |
| --- | --- | --- |
| G1 compute relief, both/comp @ mx | ✅ met | 7/7 + 7/7 replicates ≥ 80 % post-steady windows, both lanes; p50 8–10 ms vs 10.0 s (`none`) |
| G1 compute relief, both/comp @ cb | ❌ **as-is** (5/7, 4/7) | band-capped (P6.1); artifact-excluded sensitivity **14/14 pass** (diagnostic — not a gate redefinition) |
| G2 storage relief, both @ mx | ❌ as-is (1/7 literal, 0/7 win-max) | thin pre-add baselines + delivery-bound member CPU; reads do move (descriptive, sampled single-run illustration: ≈ 33 % on in-episode members, s45-lan1; not a gate input) but the gated CPU leg does not reproduce at cell level |
| G2 storage relief, both @ db | ❌ as-is (5/7; both variants) | misses s45-lan1 (2.9 %), s48-lan2 (11.8 %); s44-lan2 borderline 80.0 counted meet — floor missed either way |
| G2/db `stor` storage claim | **superseded by D18** (0/7 = expected) | fixed edge set ⇒ no relief possible; registered 2026-10-14, pre-emptive of the measurement |
| `stor`@mx storage (descriptive) | 0/7 recorded | pre-registered "measured, not assumed" outcome; compute side also unrelieved (lock 95.3–100 %) |
| G3 comparators / misaligned | ✅ all rows | `none` presses hold 21/21 blocks with 0 ops; stor@cb 0 compute spawns; comp@db 0 storage engagements; stor@mx 0 alerts; comp@mx 0 storage engagements |
| G4 health ceiling | ✅ for recovering cells; **scope note** for stor@db | cb ≤ 0.1 %, mx ≤ 2.1 %, both@db ≤ 0.9 %, all ≤ 5 %; stor@db 6.1–16.9 % = the unrelieved press (D18), out of the ceiling's calibration scope |
| MC1–MC5 + D3 | ✅ all | press 7/7 per regime; margin 21/21; specificity 28/28; liveness 0 violations in 84/84 valid runs; pins in 89/89 |
| Exclusions | ✅ ≠ effect | 5 db runs, one incident class (container OOM) — platform finding, no cell verdict touched; n = 7 everywhere |

Cell-level summary: **compute relief is demonstrated** (mx 7/7 + 7/7; cb
band-capped with 14/14 sensitivity; db descriptive comp 7/7 / both 6/7 aux);
**the storage-relief benefit claims are not met at cell level** in either
aligned storage cell (`both`@mx 1/7, `both`@db 5/7), with D18 explaining the
storage-only arms' no-relief; the comparator pattern (locked everywhere) and
specificity rows are clean. That is the RQ2 answer on v4: *aligned scaling
relieves the pressed tier it is built for — decisively on the compute side;
the storage side of the platform cannot demonstrate the same benefit at this
seat because mid-press added members receive no reads.*

### 3.2 Base-requirements verdict (`docs/operation/testing/testing_requirements.md`)

| Requirement | Verdict | Evidence |
| --- | --- | --- |
| Reproducibility cross-cutting (n ≥ 2; direction consistent; fixed seeds) | ✅ | every cell n = 7; direction consistent across replicates; seeds 42–48 pinned |
| **B1** compute benefit | ✅ met (cb/mx) | latency collapse + lock collapse vs `none`; cb as-is share band-capped — plan-level caveat registered mid-campaign (P6.1, 2026-10-13) |
| **B2** storage benefit | ⚠️ **not demonstrated** at cell level (mx 1/7; db 5/7); storage-only arms: `stor`@mx pre-registered "measured, not assumed" and `stor`@db superseded by D18 (registered mid-campaign) — no storage relief measured in either | G2 rows §3.1; D18 as the structural cause for `stor` arms |
| **M1** claimed scale-up fires | ✅ | per-cell engagement (§ results.md §1); `none` = 0 ops |
| **M2** new capacity usable | ✅ compute adds serve; ⚠️ storage members added mid-press receive no reads under a fixed edge set | D18 — pre-registered platform mechanism; recorded, not hidden; `both` storage relief is downstream of the compute spawn |
| **V1** bottleneck evidenced | ✅ | MC1 legs all regimes (cb lock 93.8–100 %; mx member 38.8–40.9 % + storage score ≥ 98.4 %; db member 67.2–69.7 %) |
| **I1** enough demand | ✅ | ≥ 2 000 hash / ≥ 5 000 lookup per LAN per episode at ~99 % completion (cb 3.3 k hash rows/lane, mx ~3.4 k hash + ~13 k lookup, db ~58 k) |
| **I2** outcome classes | ✅ | timeout kept distinct everywhere (e.g. db `none` 7.8/6.4 % vs completion 92.1/93.4 %) |
| **D1** data path clean | ✅ | no `NotPrimary` rows recorded in any valid run (screening) |
| **D2** no mid-run crash | ✅ valid runs; the 5 D2 violations correctly excluded | OOM class (D19/D20) |
| **D3** provenance | ✅ | snapshots + pins in all 89 runs (+ preflight) |
| **F1/F2 flags** | no flags | no cause note; F2 attribution on `both_db_43` superseded by the OOM mechanism (D20) |

### 3.3 Key evidence and cross-run trends

- **Latency step change (medians):** cb p50 2.28/2.73 s → 0.21/0.21 s
  (both) and 0.17/0.26 s (comp); mx 10.0/10.2 s → 8–10 ms; db 1.90/1.72 s →
  29/58 ms (both) and 27/49 ms (comp). Completion 97/95 % → 100 % (cb),
  72 % → 99 % (mx), 92/93 % → ~99 % (db). Timeouts: comparator 1.7 % (cb),
  27–29 % (mx), 7.8/6.4 % (db) → 0 % / ≤ 2.1 % / ≤ 0.9 % in aligned cells.
- **Relief windows:** mx passes as-is (7/7 + 7/7, shares at the band-limited
  ≈ 84–87 % ceiling); cb is ceiling-limited (5/7 + 4/7 as-is; all misses are
  1–4 windows beyond the band; 14/14 under exclusion); db compute readable
  descriptively (aux 6/7 + 7/7; TTR medians 47/51 and 44/50 s). Relief
  onset is fast where the action fires: TTR medians ≈ 57–79 s (lan1) /
  95–106 s (lan2) in cb/mx.
- **Where relief is absent it is structural, not stochastic:** `stor`@db
  0/7 with one lane at 42.9 % (collapsed-tail artifact) and `stor`@mx 0/7
  (literal median 2.8/0.0); the mechanism (D18) explains the absent reads — the one non-zero lane reading (42.9 %) is a collapsed-tail artifact of the excluded-class run, not a D18 prediction.
- **Resource use:** the press domain follows the arm — e.g. mx member CPU
  median 49 % (comp, storage never engaged) vs 30 % with storage eng
  (both) vs 40 % (none); db member 72 % (comp) vs 32 % (both) — the tier
  choice moves the resource picture exactly as the ablation intends.
- **Variability that remains seed-level:** the cb G1 misses are all
  band-localized (s43/s46 lan-specific); the db D14 misses are two
  idiosyncratic lanes (s45-lan1 slow, s48-lan2 never — including a 210 s
  relief lag where the baseline-window pick is fragile); the mx D14
  busiest-member pick flips with the member-series source (s42-lan2
  20.8 % ↔ 98.0 %). These are metric-fragility observations, recorded, not
  averaged away.

## 4. Gaps & Next Steps

**What remains unclear / untested**

1. **The cb as-is G1 shortfall is a platform artifact, not an outcome** —
   but the platform fix is an open engineering question (P6.1 §4: the 60 s
   hard timeout may be load-bearing for redistribution; candidate fix =
   proactive re-pin on topology change). A whole-cell rerun (≈ 14 cb runs)
   becomes meaningful only after that question is resolved; not attempted.
2. **D18 fix candidates are parked** (proactive re-pin, pool renewal,
   per-request selection — D18 handling). Until one lands, the storage-side
   benefit claims cannot be demonstrated in any fixed-edge-set arm; the
   `both`-arm storage relief channel runs through the compute spawn.
3. **D14 metric robustness** — thin pre-add baselines (1–5 windows) make
   the busiest-member pick source-sensitive at the mx/db seats. A stronger
   baseline protocol (pre-press steady-state window, fixed series source)
   should be pre-registered before any follow-up storage claim.
4. **The db seat is the v3-carried shape at pool 6** (v3: pool 12), never
   re-calibrated on the repaired platform; the lookup press is also the
   only regime that drove the container OOM class (256 MB cap).
5. **Read-share instrumentation** (≈ 1 sample/window) is descriptive only —
   adequate for mechanism attribution, too coarse for gating; flagged.
6. **P3-pilot D14 row correction** (`mx_both` 82.0/95.7 %) — superseded,
   not reproducible; correction note to be applied by the main session
   (results.md §5 item 6).

**Limitations carried into the thesis**

- Emulated two-domain single-host testbed; no geo-distributed WAN claim.
- D13: mx (0.05) and db (0.15) storage quotas are quota-relative — never
  pooled; cross-regime storage CPU is not load-comparable.
- db compute-side numbers are descriptive (frozen D12 anchor structurally
  absent in lookup traffic).
- n = 7 per cell: enough for the pre-registered floor and direction claims;
  not enough for distributional claims on the fragile tail lanes.
- The 60 s band sensitivity is a diagnostic; the as-measured cb counts
  (5/7, 4/7) stand in the record next to it.

**Next actions (ordered)**

1. P6.2 figures (data tables ready in `results.md` §4; driver adaptation +
   variance dots; archive under `graphs/comparison/` per the campaign
   skill).
2. Dossier update — `tese/research_questions/rq2/` addendum (done in this
   P6 pass; thesis-prose integration parked with the author, including the
   v3-note 9/10 → 8/10 fix).
3. Author decisions surfaced: P6.1 handling (adopted (a) by this analysis —
   confirm), the s44 borderline convention, the P3-pilot correction note,
   whether the storage-side claim gets a follow-up campaign after a D18
   fix.
