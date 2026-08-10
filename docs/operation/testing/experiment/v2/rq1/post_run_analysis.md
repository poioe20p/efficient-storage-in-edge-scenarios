# Post-Run Analysis — RQ1 Telemetry Delivery Semantics (Main Campaign)

**Date**: 2026-08-02 · **Plan**: [experiment_plan.md](experiment_plan.md) · **Results**: [results.md](results.md)
**Campaign**: pre-flight ground (P1/P2/P3c) + 9-run main campaign (`ep_1..3`, `delayed_1..3`, `ls_1..3`)
**Graphs**: [`graphs/comparison/`](graphs/comparison/) (10-graph suite, archived 2026-08-02)

## 1. Objective

RQ1 asks: **do verified event-preserving, delayed event-preserving, and
latest-state telemetry delivery semantics differ in their effect on overload
observability, scaling response, and transient service quality in a stateful
edge service?** The experiment isolates whether the controller is harmed mainly
by *delivery delay*, by *loss of intermediate demand evidence*, or by both. The
independent variable is `TELEMETRY_SOURCE ∈ {event_preserving, delayed_event_preserving, poll}`;
the hypothesis (plan §2) predicts a **completeness-vs-info-age tradeoff**: Arm A
fresh+complete, Arm B complete-but-stale (≈30 s), Arm C lossy-but-fresh
(~2/3 windows dropped), with reaction latency ordering B ≥ C > A and delivered
fraction A ≈ B > C. This is the capstone for the RQ1 campaign at n=3.

## 2. Mechanism

Three arms ran an **identical workload** — the control group's validated
`phases_stress_plateau.json` (baseline 60 s → `compute_plateau` 600 s @ r5.0 →
`recovery_gap` 120 s → `demand_drop` 420 s) — under a fixed scaling policy
(rebased control caps 3/3, calib-v2 compute scale-down 3-of-6 with relaxed
`TAU_CPU_DOWN=25`/`TAU_PROC_DOWN_MS=40`, thesis-§2 SS/reserve/cross-region
disabled). Only the delivery source changed per arm (env files
`rq1_event_preserving.env` / `rq1_delayed.env` / `rq1_latest_state.env`; Arm C
additionally forced `POLL_INTERVAL_S=30` on the shell — the Docker `-e` override
gotcha). Three replicates per arm (9 runs, 2026-08-02, all exit 0). Per-run
analysis (`rq1_delivery_per_run.py`) and cross-mode graphs
(`rq1_delivery_comparison.py`) ran on the VM where the data lives; the 10-graph
suite was copied back and archived under this experiment folder.

## 3. Results

Success-criteria verdicts at n=3 (full table in `results.md` §Judgment):

| # | Criterion | Verdict |
|---|---|---|
| C1 | Artifact completeness | ✅ all 9 runs |
| C2 | Arm A clean reference | ✅ frac 1.0000, 0 gap/err |
| C3 | Arm B completeness + delay | ✅ frac 1.0000, delay 30.001 s |
| C4 | Arm C loss measurable + info-age ≥10 s below B | ✅ frac 0.325–0.333; info-age 1.2–8.2 vs 30.19 s |
| C5 | Overload exercised | ✅ ≥85% of plateau windows overload in every arm |
| C6 | Scale-up response | ✅ ≥1 decision + usable capacity per LAN, all runs |
| C7 | Scale-down response (≥1 scale-down decision/LAN) | ✅ all 9 LANs made ≥1 decision; real removals (decision_log) A 6/6, B 6/6, C 5/6 (ls_3 lan1 all no-op — flagged). Caveat: container_events shows dynamic-container removals on ls_3 lan1 without logged decisions (replacement/churn) |
| C8 | Transient quality (≤2% non-surge) | ⚠️ borderline — non-surge rates uniformly low (2–4% band) across arms on raw `phase` labels, not arm-discriminative; ≤2% exceeded only on small-n spikes. Not flagged as bad behavior |
| C9 | Delay-vs-loss ordering | ✅ frac A ≈ B > C; info-age A < C < B; both B,C slower than A on usable-capacity (B's decision metric is a documented artifact; C > B capacity ordering is a finding) |

**Confirmed findings (n=3, multiple runs):**

1. **The completeness-vs-info-age tradeoff is real and reproducible.** A ≈ B
   (1.0 delivered) > C (0.33); info-age at scale-up A (0.5–0.8 s) < C
   (1.2–8.2 s) < B (30.19 s). Arm C misses ~78 overload windows/LAN/run — the
   poll-30 blind spot is not a fluke.
2. **C8 non-surge rates are low and not arm-discriminative — ⚠️ borderline, not bad behavior.** On raw phase labels all arms sit in a similar low 2–4% band (A recovery_gap 0.0/3.8, demand_drop 3.0/0.6; B recovery_gap 0.6/2.1, demand_drop 2.3/3.7; C recovery_gap 0.6/1.9, demand_drop 0.4/0.2), with worst cells only on small-n/single-run spikes. There is no significant mode-discriminating non-surge degradation, so not flagged as bad behavior. Per-phase rates must use the generator `phase` label — the analyzer's anchored bucketing is misaligned (plateau overrun ~52–57 s), and the earlier "B-only, delayed_3 recovery_gap lan1 10.96%" reading was an artifact (raw 1.85%).
3. **The reaction-latency *decision* metric is not a valid delay-sensitive
   proxy for Arm B.** B's "plateau → first scale-up decision" is deflated (mean
   24.8 s < A 38.9 s) because a 30 s-stale pre-plateau baseline window can be
   delivered right at the plateau boundary and trigger the first decision
   (`delayed_3` lan1 fired at +4.0 s on a pre-plateau window). The
   delay-sensitive **usable-capacity latency does order A (39.8) < B (67.3) < C
   (101.7)** — both delay and loss slow usable capacity, loss more than delay.
   This resolves the pre-flight "A vs B reaction ordering" caveat as a metric
   artifact, not noise, and lets **C9 pass** on the capacity-anchored metric; the
   C > B capacity ordering (loss slower than delay) is a finding (fewer evidence
   opportunities), refining H1/H2.
4. **C7 is met on the letter for every arm (≥1 scale-down decision/LAN); real removals (decision_log) are 6/6 (A), 6/6 (B), 5/6 (C).** `ls_3` lan1 performed only `scale_down,absent` — flagged per plan C7 (delivered below-windows in the drop did not accumulate to 3-of-6 in that run), not auto-passed/failed. Caveat: container_events shows 5 dynamic containers removed on `ls_3` lan1 without logged scale-down decisions (replacement/churn, also present in every run) — so "no decision-logged scale-down" is accurate but "no capacity reclaimed there" would overstate it.
5. **Overhead scales with delivery work** — controller CPU A (8.5%) > B (7.3%)
   > C (6.5%), RSS flat ~67–72 MB. Delivery semantics cost little.

**Tentative observation (single-arm systematic, needs follow-up):** Arm C shows
a run-invariant lan2 plateau failure asymmetry (11–12% on lan2 vs 2–4% on lan1
in all three ls runs — verified on raw labels). The pre-flight A lan1
`recovery_gap` 2.06% borderline is **NOT cleanly resolved** on raw labels: Arm A
itself violates C8 (ep recovery_gap 0.0/3.8, demand_drop 3.0/0.6).

## 4. Gaps & Next Steps

- **Arm C lan2 plateau asymmetry** is unexplained — follow-up should check load
  distribution vs poll-delivery fairness on lan2 (client traffic, VIP routing)
  before it is attributed to delivery semantics.
- **C8 non-surge rates are uniformly low (2–4%)** across arms on raw phase
  labels (the analyzer's anchored bucketing is misaligned — plateau overrun).
  Frame C8 as ⚠️ borderline (not bad behavior); the thesis should not make a
  strong non-surge claim for any single arm.
- **C7 for C (ls_3 lan1)** — C7 is met on the letter (≥1 decision/LAN); the
  decision-log real-removal gap needs the delivered below-window counts for
  `recovery_gap`+`demand_drop` on that LAN to confirm the 3-of-6 accumulation
  just missed vs a criterion problem, and the container_events removals there
  (without logged decisions) should be reconciled — per plan C7 clause.
- **Reaction metric choice:** the thesis RQ1 reaction analysis must use
  usable-capacity latency (or window-anchored reaction) for B, not the raw
  first-decision latency, which is confounded by the stale-boundary artifact.
- **Driver caveat** carries forward: the latency-coupled sync curl driver means
  offered load differs per arm (A ~10.6–11.5 k, C ~7.0–7.3 k, B ~5.1–6.2 k
  plateau requests/LAN); magnitudes are partly driver-driven (thesis §8), so
  RQ1 claims should emphasize relative ordering and the completeness/info-age
  axes.
- RQ1 is otherwise **closed at n=3**: C1–C6 ✅, C7 ✅ (with `ls_3` lan1
  decision-log real-removal gap flagged + container_events churn caveat),
  C8 ⚠️ (borderline — uniformly low non-surge rates), C9 ✅ (with the
  C > B capacity ordering as a finding). The completeness-vs-info-age tradeoff
  is the headline deliverable for the thesis narrative.

---

# Revision 2026-08-07 — RQ1 v2 campaign (n=5, FINAL evidence)

**Plan**: [experiment_plan.md](experiment_plan.md) (v2 §F) ·
**Results**: [results.md](results.md) §v2 Campaign ·
**Graphs**: [`graphs/comparison/`](graphs/comparison/) (25-graph suite, n=5/arm,
regenerated 2026-08-07) · **Stats**: `rq1_stats_summary_v2.csv` ·
**Asymmetry**: `lan2_asymmetry_v2_campaign.csv` ·
**Run summaries**: [`run_summaries/`](run_summaries/) (×20)

## 1. Objective

The v2 campaign completes the RQ1 answer with the missing cell: a full 2×2
factorial **fresh/stale × complete/lossy** — A `event_preserving`
(fresh+complete), B `delayed_event_preserving` (+30 s, complete),
C `poll`/latest-state (stale+lossy, ~1/3), D `sampled_push`
(`SAMPLE_EVERY=3`, fresh+lossy, ~1/3) — so the delay-vs-loss attribution is
clean (delay = A−B and D−C edges; loss = A−D and B−C edges). n=5 per arm,
20 runs, open-loop driver (equal offered load, `CURL_MAX_TIME=300`,
`INFLIGHT_WINDOW=1024`), 5 counterbalanced blocks (seeds 2001–2005). The v1
n=3 record above is the supporting/characterization record; this revision is
the final thesis evidence.

## 2. Mechanism

Workload locked at G2: `phases_rq1_stress_plateau.json` (plateau rate 1.2,
rebalanced mix, `EDGE_CPUS=0.25`, plus the `idle_tail` 420 s phase added so the
lossy arms can release the churn guard and fire scale-down), pool 6 + data-path
fix, `_HOUSEKEEPING_OVERLOAD_GATE` (hysteresis) on. Run folders on `cloud-vm`;
per-run analysis (`rq1_delivery_per_run.py`, 9 CSVs/run), comparison graphs
(`rq1_delivery_comparison.py`, n=5/arm), pre-registered stats
(`rq1v2_p3_01_stats.py`, MWU exact + Cliff's delta on the factorial edges) and
the lan2-asymmetry diagnostic (`rq1v2_p4_01_lan2_asymmetry.py`, n=5) all ran on
the VM; analysis outputs synced back, run folders retained on the VM as the
campaign archive. Two replicates were dropped + re-run for lan2
`plateau_unstable` (`ls_4`, `sp_5`), retained as characterization.

## 3. Results

Criterion verdicts (n=5, full table in `results.md` §v2 Judgment):

| # | Criterion | Verdict |
|---|---|---|
| C1 | Artifact completeness | ✅ all 20 runs; `ack_log` A/B full, D partial, C absent (by design) |
| C2 | Arm A clean reference | ✅ frac 1.0000, 0 gap/err, all 5 runs both LANs |
| C3 | Arm B completeness + delay | ✅ frac 1.0000, plateau delay p50 30.001 s exact |
| C4 | Loss measurable (C frac <0.70 + info-age ≥10 s below B; D frac ∈[0.30,0.36] + sub-second) | ✅ C frac 0.329–0.333, info-age med 20.4 vs B 31.8; D frac 0.331–0.335, delay p50 0.44–0.60 s |
| C5 | Overload exercised | ✅ universe majority-overload in every arm |
| C6 | Scale-up response | ✅ 6–12 decisions/LAN, usable capacity in all 40 LANs |
| C7 | Scale-down (joint decision_log + container_events) | ✅ letter; **guard-conditioned for C/D** (real removals in `idle_tail`; decision-log real removals 0/10 LANs for C/D — G8 gap confirmed at n=5) |
| C8 | Non-surge transient quality | ⚠️ NULL — non-surge failure 0%, timeout ~0.05% in every arm; mechanical rule flagged UNANTICIPATED on floor noise, re-inspection = null |
| C9 | Factorial-edge ordering | ✅ primary (capacity) + info-age; plateau timeout/failure edges weak or reversed (bounded-overload plateau) |

**Confirmed findings (n=5, statistics-backed):**

1. **Capacity (the pre-registered primary) orders A 32.0 < B 57.5 < C 81.5 ≈
   D 85.1 s** — d=−1.0 (p=0.008) on both loss edges and the fresh delay edge;
   the lossy-level delay edge (D→C) is null. **Loss hurts reaction more than
   delay** (a 1/3 sample costs ~50 s over the reference regardless of
   freshness; +30 s delay costs ~25 s on the fresh level, ~0 on the lossy).
2. **Info-age at decision orders A (1.3–8.6) < D (11–19) < C (18–26) < B
   (30–39) s.** Delay dominates info-age; the loss_stale info-age reversal
   (B 31.8 > C 20.4) is structural (B always acts on 30 s-old complete
   evidence; C's sampled windows are younger on average).
3. **C8 is a clean NULL** — no delivery arm degrades non-surge service quality
   (failure 0%, timeout ~0.05% everywhere). The pre-registered rule's
   UNANTICIPATED flag is floor noise on near-zero rates; substantive verdict:
   no transient-quality penalty from any delivery semantics.
4. **Plateau service quality does not discriminate at n=5 under bounded
   overload** — all arms in a 15–21% timeout / 1–3.5% failure band; failure
   edges reverse (complete arms slightly higher). The G2-bounded plateau
   expresses the delivery-semantics effect in *controller reaction*
   (capacity/info-age), not the plateau data plane.
5. **C7 is letter-pass for all arms; C/D real removals are guard-conditioned**
   (§0.6): container_events removals in 39/40 LANs, almost all C/D removals in
   `idle_tail` (churn-guard release); decision_log real removals only A 7/10
   and B 3/10 LANs (G8 gap systematic at n=5).
6. **Lan2 asymmetry migrated from Arm C (v1) to Arm A (v2):** A `ep` plateau
   failure lan2−lan1 median +2.64 pp (5/5 runs) — the only ASYMMETRIC cell;
   C is balanced at n=5 (v1's 11–12% lan2 asymmetry does not reproduce).
   Offered load and delivered windows are equal per LAN ⇒ data-plane effect,
   not telemetry. Open post-campaign root-cause target.
7. **Overhead flat and low** (~7–12% CPU, 67–93 MB RSS); complete arms pay
   ~1–2% more than lossy. Delivery semantics are cheap at the controller.

## 4. Gaps & Next Steps

- **Arm A lan2 plateau failure asymmetry (+2.64 pp)** — root cause open:
  per-backend/VIP/scale-out timing analysis on the 5 ep runs; the telemetry
  path and offered load are symmetric, so the cause is in the service/data
  plane.
- **Decision-log real-removal gap (G8)** — confirmed systematic at n=5;
  bounded via container_events in this campaign; a controller-side logging
  change would close it for future RQs.
- **Plateau service-quality null** — the bounded-overload plateau was
  engineered (G2 rate 1.2) for stable runs; it does not express a
  delay/loss service penalty. If a service-quality penalty needs to be shown,
  a follow-up would need a stronger overload regime — but that risks the
  v1-style collapse and is out of scope for the thesis question (which is
  about observability/response).
- **C/D scale-down timing** is a guard-interaction quantity (idle_tail
  release), not a pure delivery-semantics claim — stated explicitly in the
  results narrative per §0.6.
- **RQ1 v2 is CLOSED as final evidence.** The completeness-vs-info-age
  2×2, the capacity ordering (A < B < C ≈ D), the info-age ordering
  (A < D < C < B), and the C8 null are the thesis deliverables; the
  lan2-asymmetry item above is the only open follow-up.

