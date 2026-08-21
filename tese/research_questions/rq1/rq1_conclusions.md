# RQ1 — Conclusions (Telemetry Delivery Semantics)

> **Status:** 2026-08-09 · **v3 campaign (final)** — 4 arms × n=7 = 28 runs, seeds 3001–3007, analyzed and verified against run artifacts on `cloud-vm`. This is the authoritative RQ1 conclusions document (the earlier v2 n=3 analysis is superseded; its record lives in the v2 experiment docs).
> **Companion docs:** `rq1.md` (framing/provenance); campaign analysis (kept on `cloud-vm`, `docs/operation/testing/experiment/v3/rq1/analysis/`): `rq1_campaign_summary.md`, `rq1_v3_campaign_dataset.csv`, `rq1_v3_campaign_stats.csv`; capstone `docs/operation/testing/experiment/v3/rq1/post_run_analysis.md`; graphs `docs/operation/testing/experiment/v3/rq1/graphs/` (comparison + thesis).
> **Verification:** every claim below was independently recomputed from run artifacts (`client_requests.csv`, `analysis/rq1_delivery/*`, `phase_service_quality.csv`, `reaction_timeline.csv`, `elasticity_events.csv`, `container_events`, `controller_lan{1,2}.log`, provenance snapshots) on the cloud VM.

---

## 1. Answer to the RQ

**The observation interface is consequential: how demand evidence reaches the scaling decision measurably changes user-visible service quality under overload, and the two failure modes — loss of intermediate demand evidence and delivery delay — harm the system with different severity and robustness.**

The four arms — A `ep` (event-preserving, fresh + complete), B `delayed` (+30 s, complete), C `ls` (latest-state poll-30, ~1/3 of windows), D `sp` (sampled-push /3, ~1/3 of windows) — ran an identical co-loaded workload under an identical policy (controller pin `d267099`), counterbalanced in 7 seed-matched blocks. The between-arm differences are therefore attributable to how demand evidence reaches the decision:

- **Lossy delivery (C/D) costs ~9× per-episode p95 with perfect separation across all 7 replicates** (δ = −1.000, exact p = 0.0006, both LANs) — the robust, severe driver.
- **Delay (B) is significant in aggregate** (A−B p = 0.0012, 7/7 direction) **but trajectory-dependent** (bimodal: ~65 s at seeds 3001/3007, ~5–13 s at five seeds).
- **Non-surge quality is unaffected in every arm** (~1.05–1.08 s p95 baseline/recovery/demand-drop) — the cost is confined to the overload episode.
- The campaign is **artifact-free**: 0 timeouts in every episode, served-basis completion ≥ 95.7 %, no harness collapse, D1/D2/D3 clean in 28/28 runs.

## 2. Confirmed findings (n=7 per arm, independently verified)

| # | Finding | Evidence |
|---|---|---|
| F1 | **Usable-capacity ordering reproduces (H1)** | Medians A 28.5 < B 59.6 < C 79.6 ≈ D 83.2 s; A<B in 7/7, B<C in 7/7 blocks; C vs D 5/7 (D marginally later, not cleanly separated) |
| F2 | **Latest-state (lossy) arms — both realizations — severely degrade per-episode p95 (H2, core claim)** | C/D 22.2–40.0 s vs A 2.4–5.6 s → ~9×; A−D δ = −1.000, p = 0.0006, perfect separation 7/7 on both LANs |
| F3 | **Delay arm degrades p95 in aggregate** | A−B medians 3.73 vs 10.77 s; p = 0.0012, δ = −0.959 [−1.000, −0.755], direction 7/7 |
| F4 | **Delay arm is bimodal — B does not reliably sit between A and C** | B episode p95 65.3/64.7 s at seeds 3001/3007, 5.0–12.6 s elsewhere; B−C n.s. (p = 0.209, δ CI crosses 0) |
| F5 | **C ≈ D (the two latest-state realizations); "D strictly worst" not supported** | D−C p = 0.456; point estimate C marginally worse (δ = −0.265; C > D in 5/7 blocks) |
| F6 | **Non-surge phases clean in all arms (H3)** | baseline/recovery/demand_drop p95 ~1.05–1.08 s; only 300 s-cap tail timeouts in demand_drop (0.07–0.12 %) and two single-window recovery blips (C 4.2 s, D 5.8 s) |
| F7 | **No differential-cancellation artifact** | Episode timeouts = 0 in all 28 runs → offered-basis ≡ served-basis; canceled shares flat ~5–7 % across arms (single `sp_6` outlier at 21.2 %) |
| F8 | **Delivery per design** | delivered fraction ep/delayed 1.0; ls 0.325–0.336; sp 0.328–0.336 (0.333 ± 0.1) — verified per run |

## 3. The two-axis result (delay vs loss)

The headline is that **loss and delay are not interchangeable, and loss is the robust driver** — directly answering the RQ's seed question ("which failure, delay or missing evidence, actually hurts?"):

- **Loss of intermediate demand evidence (C/D) is the severe, robust driver of user-visible cost.** Both lossy arms land at ~31–40 s episode p95 regardless of seed, with **perfect separation from A across all 7 replicates and both LANs**. Whether the loss is implemented as latest-state polling (C) or sampled push (D) does not materially change the user cost (C ≈ D).
- **Delay (B) is significant in aggregate but heterogeneous.** The delayed arm's user cost depends on trajectory: at two seeds it is as bad as the loss arms (~65 s), at five seeds it is near-A-healthy (~5–13 s) — even though B's usable-capacity timing is stable (55.1–61.5 s). The delayed arm's cost is therefore a **seed/trajectory-dependent phenomenon**, not a stable dose of degradation.
- **Mechanism → user cost chain is connected.** The control-loop link (H1, when the controller scales) is cleanly reproduced; the user link (H2) is confirmed for the loss arms and in aggregate for delay. Because the traffic generator is identical across arms, the p95 contrast is an **end-to-end outcome of the delivery mode**, not a confound.

## 4. Methodology findings

- **Pre-registered primary endpoint carried the verdict.** Served-basis episode p95 was pinned pre-campaign; episode timeouts are 0 in all arms so the ordering is carried by p95, with failure/canceled reported as distinct outcome classes (I2). No multiplicity correction on the 4 pinned edges (documented, expected 2 n.s.).
- **Usable-capacity latency is the reaction metric.** As in v2, the naive "plateau → first scale-up decision" latency is not a valid delay-sensitive proxy for B (a stale pre-plateau window can trigger the first decision at the plateau boundary); reaction claims use usable-capacity latency (`reaction_timeline.csv`).
- **Differential cancellation was checked, not assumed.** Served-vs-offered gap is 0.0 s in every run (timeouts = 0); canceled shares are flat across arms — the pre-registered "cancellation rises with degradation" expectation (from n=1 probes) did **not** reproduce and must not be cited.
- **Counterbalancing and seed-matching.** All four arms share the block seed (3001–3007); ordering claims rest on the 28 replicates only. Probes (M2, P-B, P-C, D-recheck) are calibration/feasibility, explicitly excluded from the ordering claim.

## 5. Non-finding / resilience (H3)

**Non-surge transient quality shows no mode-discriminating difference.** All four arms sit at ~1.05–1.08 s p95 in baseline, recovery_gap, and demand_drop; the only degradations are the known 300 s client-cap tail timeouts in demand_drop (0.07–0.12 %, all arms) and two single-window recovery blips in the lossy arms (C 4.2 s, D 5.8 s — brief, not phase-wide). **The platform is resilient to delivery semantics on non-surge quality; the cost is confined to the overload episode.**

## 6. Secondary observations / open items

- **B-arm bimodality (the open question).** B's usable capacity is tight (55.1–61.5 s) yet its episode p95 spans 5.0–65.3 s. The likely mechanism (from v2 §4): whether the stale pre-plateau window that triggers B's first scale-up decision lands before or after surge onset. **Recommended before finalizing the chapter: trace B's first-decision window timing per run in the decision/telemetry logs to convert the bimodality from a limitation into a mechanism finding.**
- **C-arm `ack_count = 0` — structural, resolved.** Latest-state acks are logged by the local_state_server aggregator (`ACK_LOG_PATH`, `aggregator.py:77`), not the run-folder `ack_log_lan{1,2}.jsonl`; C deliveries are fully tracked in `telemetry_delivery_log_*.csv` (mode=`latest_state`). No delivery-integrity impact.
- **`delayed_3` (seed 3003) lan2 asymmetry 5.26×** (served p95 21.1 s vs 4.0 s lan1) — the only run above the ≤3× line; part of the B variability story, not a gate miss.
- **B residual `http=000` completed class** (2.22 % of offered; A 0.03 %, C 0.22 %, D 0.42 %) — a genuine small error population, distinct from timeout (I2), never merged; no gate impact.
- **`sp_6` (seed 3006) cancellation outlier** — 21.2 % canceled / offered-basis 77.0 % (reportable flag for D); served-basis 97.7 %, no collapse; single-replicate spike.
- **Storage scale-down `FAILED` retries** in `elasticity_events.csv` in all arms (mean 6.4–9.7/run) — known scale-down bookkeeping flag (containers removed cleanly per `container_events`; not D2; outside the episode).

## 7. How to frame in the thesis

- **Strongly:** the completeness-axis result (F2 — ~9× p95, δ = −1.000, p = 0.0006, perfect separation, n=7); the two-axis discrimination (loss robust/severe vs delay aggregate-significant/heterogeneous, §3); the artifact-free integrity of the campaign (0 episode timeouts, no collapse, D1/D2/D3 clean, differential-cancellation checked); the v2 → v3 arc (null root-caused to platform artifacts, fixed, then measured — a methodological strength).
- **Cautiously:** any monotone ordering claim — the full A < B < C ≈ D is **not** reproduced (B−C n.s.); "D strictly worst" is **not** supported (C ≈ D, point estimate C marginally worse); absolute latency magnitudes are regime-relative (co-loaded 180 s/1.2 on the fixed 2-edge-node platform).
- **Methodologically:** served-basis p95 as the pre-registered primary endpoint; usable-capacity latency for reaction; report offered-vs-served and canceled per arm; never cite the n=1 probes for ordering claims.

## 8. Cross-references

- Framing / provenance: `rq1.md`
- Campaign plan + run matrix: `docs/operation/testing/experiment/v3/rq1/experiment_plan.md`, `run_matrix.md`
- Campaign analysis (kept on `cloud-vm`): `docs/operation/testing/experiment/v3/rq1/analysis/rq1_campaign_summary.md` (+ `rq1_v3_campaign_dataset.csv`, `rq1_v3_campaign_stats.csv`)
- Capstone: `docs/operation/testing/experiment/v3/rq1/post_run_analysis.md`
- Graph suite (25 graphs): `docs/operation/testing/experiment/v3/rq1/graphs/comparison/`
- Platform fix record (why v3 exists): `docs/operation/testing/experiment/v2/rq1/rq1_v3_platform_fix_plan.md`
- v2 precursor (docs): `docs/operation/testing/experiment/v2/rq1/results.md`, `post_run_analysis.md`

## 9. Caveats / limitations

- **B−C power is limited by B's bimodality.** n=7 was pre-registered to absorb run-to-run variance, but B's two ~65-s blocks straddle C's distribution, so the B−C edge cannot separate on campaign data. Pinning B's position would require more B replicates or a B-arm redesign.
- **Single regime, single platform.** Magnitudes are on the co-loaded regime (0.30/0.35/0.15/0.10/0.10 @ 180 s episode / rate 1.2) and the fixed 2-edge-node fleet — regime-relative, per `testing_requirements.md` relative-criteria rule. No cross-regime/cross-topology generalization.
- **Unit choice**: per-run mean-of-LANs; per-LAN sensitivity is consistent (directions and significance unchanged on both LANs for every edge), except `delayed_3`'s 5.26× lan2 asymmetry (visible only per-LAN, flagged).
- **No multiplicity correction** (pre-registered; 4 primary edges, 2 expected n.s.).
- **`sp_6` is a single-replicate cancellation outlier**; D-arm per-run cancellation otherwise 3.7–6.8 %.
- **Signal-statistic pin**: RQ1 runs on the legacy mean-based decision signals (`LATENCY_SIGNAL_MODE=mean`, storage signal `W_STORAGE_CPU=0 / W_T_DB=1.0`); the mean→median/composite signal work is gated to RQ2+ and does not affect RQ1's internally consistent comparison.

---

## 10. Thesis-ready statement (v3)

> On the fixed co-loaded platform, the observation interface has a measured, replicated user cost. Latest-state (lossy) telemetry delivery — ~1/3 completeness, robust across its two realizations (polling and sampled push) — degrades per-episode p95 by ~9× with perfect separation across all seven replicates (Cliff's δ = −1.000, exact p = 0.0006); a +30 s delivery delay is significant in aggregate (p = 0.0012, 7/7 direction) but seed-dependent (bimodal); non-surge quality and data-path integrity remain clean in every arm. The completeness axis, not the delay axis, is the robust driver of user-visible degradation — the two failure modes of the observation interface are distinguishable, and the observation interface itself is a first-order determinant of transient service quality under overload.
