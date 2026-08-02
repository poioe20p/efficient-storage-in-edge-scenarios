# RQ1 — Conclusions (Telemetry Delivery Semantics)

> **Status:** 2026-08-02 · main campaign (9 runs, n=3 per arm) analyzed and deep-verified against raw artifacts.
> **Companion docs:** `rq1.md` (framing/provenance); experiment results `docs/operation/testing/experiment/v2/rq1/results.md` (§Main Campaign), `post_run_analysis.md`; graphs `docs/operation/testing/experiment/v2/rq1/graphs/comparison/`.
> **Verification:** every claim below was independently recomputed from raw run artifacts (`client_requests.csv`, `window_log`, `telemetry_delivery_log`, `decision_log`, `container_events`, `controller_stats`, `per_node_stats`) on the cloud VM.

---

## 1. Answer to the RQ

**Telemetry delivery semantics are consequential: the observation interface changes what the controller sees and how fast it reacts, and the two failure modes harm the system through different mechanisms.**

The three arms — A (event-preserving: complete + fresh), B (delayed event-preserving: complete + stale, +30 s), C (latest-state poll: lossy + fresh, ~1/3 of windows) — ran an identical workload under an identical policy. The differences that appear are therefore attributable to how demand evidence reaches the decision:

- **Completeness-vs-info-age tradeoff is real and reproducible.** Delivered fraction A ≈ B (1.0) > C (0.325–0.333); info age at scale-up A (0.5–0.8 s) < C (1.2–8.2 s) < B (30.19 s). Arm C misses ~78 overload windows per LAN per run (76–81 across replicates).
- **Delay and loss harm the system along different axes** (see §3): delay penalizes *sustained* service (served demand, plateau quality); loss penalizes *reaction speed* (usable-capacity latency).

## 2. Confirmed findings (n=3, independently verified)

| # | Finding | Evidence |
|---|---|---|
| F1 | Completeness-vs-info-age tradeoff | frac A≈B (1.0) > C (0.33); info-age at scale-up A < C < B; C misses ~78 overload windows/LAN/run |
| F2 | Info-age ordering A < C < B is robust | A ~0.5–1 s; C ~1–8 s (scale-up) / ~11–17 s (decision p50); B 30.19 s / ~32–33 s — robust on independent recomputation |
| F3 | Reaction (usable-capacity) ordering A < B < C | A ~36–40 s < B ~65–67 s < C ~99–102 s — both delay and loss slow usable capacity; **loss more than delay** |
| F4 | Sustained served demand ordering A > C > B | plateau requests A ~10.6–11.5 k > C ~7.0–7.3 k > B ~5.1–6.2 k per LAN; plateau p50 B (0.24–0.30 s) worst, A (0.07–0.08 s) best |
| F5 | Overhead scales with delivery work, flat and low | controller CPU A 8.5% > B 7.3% > C 6.5%; RSS ~67–72 MB |
| F6 | Overload observability is the cleanest discriminator | A/B see every overload window; C loses ~2/3 — mechanism-level, not load-dependent |
| F7 | Scale-down fires in all arms | real removals (decision log) A 6/6, B 6/6, C 5/6 LANs; `ls_3` lan1 decision-log gap flagged (container churn caveat) |

## 3. The two-axis result (delay vs loss)

The headline is that **delay and loss are not interchangeable** — they degrade different parts of the chain:

- **Delay (B) penalizes sustained service quality.** Stale (30 s) complete evidence → the controller reacts late to the surge → the platform stays overloaded longer → highest plateau latency (p50 0.24–0.30 s) and the **lowest served demand** (A > C > B). The latency-coupled driver converts this into measurable throughput loss.
- **Loss (C) penalizes reaction speed.** Fresh but sparse evidence → the controller detects the shift later (fewer evidence opportunities) → the **slowest usable-capacity latency** (A < B < C), even though what it does see is fresher.

Because the traffic generator is identical across arms, the achieved-throughput difference is an **end-to-end outcome of the delivery mode** (not a confound): each mode determines how much demand the platform can serve. The sync (latency-coupled) driver caveat applies to *absolute* latency magnitudes only; the *relative* orderings are delivery-semantics effects.

## 4. Methodology finding (reaction-metric choice)

The naive "plateau → first scale-up decision" latency is **not a valid delay-sensitive proxy for Arm B**. A 30 s-stale pre-plateau baseline window can be delivered right at the plateau boundary and trigger the first decision (delayed_3 lan1: first scale-up at plateau+4.0 s on a pre-plateau window), deflating B's apparent reaction latency. The thesis RQ1 reaction analysis must use the **usable-capacity latency** (or window-anchored reaction) for B. This is a documented artifact, not a hypothesis violation.

## 5. Non-finding / resilience

**Non-surge transient quality shows no significant, mode-discriminating difference.** On corrected raw phase labels all arms sit in a low 2–4% band (baseline/recovery_gap/demand_drop), with only small-n or single-run spikes; the ≤2% criterion is exceeded only on those spikes. **The system is resilient to delivery semantics on non-surge quality.** (Note: per-phase rates must use the generator `phase` label — the analyzer's anchored phase bucketing was misaligned by a plateau overrun; the earlier "B-only" reading was an artifact.)

## 6. Secondary observations / open items

- **Arm C lan2 plateau asymmetry** (11.5–12.1% failure on lan2 vs 2.2–3.7% on lan1, all 3 runs) is real but unexplained — present as an open follow-up, not a delivery-semantics claim.
- **C7 for `ls_3` lan1**: no decision-logged real scale-down (only no-op `scale_down,absent`); container_events shows dynamic-container removals there without logged decisions (replacement/churn) — flagged for inspection per the plan's C7 clause.

## 7. How to frame in the thesis

- **Strongly:** the completeness-vs-info-age tradeoff (F1–F2, F6); the two-axis delay-vs-loss result (F3–F4); overhead (F5).
- **Cautiously:** absolute latency magnitudes (driver caveat); C8 → state "resilient, no significant non-surge difference"; C lan2 asymmetry → open item.
- **Methodologically:** use usable-capacity latency for reaction; cite the stale-boundary artifact.

## 8. Cross-references

- Framing / provenance: `rq1.md`
- Experiment plan + run matrix: `docs/operation/testing/experiment/v2/rq1/experiment_plan.md`, `run_matrix.md`
- Results (timeline, measurements, judgment): `docs/operation/testing/experiment/v2/rq1/results.md`
- Capstone: `docs/operation/testing/experiment/v2/rq1/post_run_analysis.md`
- Graph suite (25 graphs): `docs/operation/testing/experiment/v2/rq1/graphs/comparison/`
- Implementation: `docs/research_questions/v2/rq1/rq1_prepation.md`
