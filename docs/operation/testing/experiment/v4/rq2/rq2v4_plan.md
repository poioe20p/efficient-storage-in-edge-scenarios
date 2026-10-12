# RQ2 v4 — Execution Plan (master)

> **Status:** 2026-10-11 · program plan for the RQ2 rebuild.
> **Companion:** [`preparation.md`](preparation.md) — findings, decisions (D1–D7),
> and provenance. This file maps the full execution: phases, ordered steps,
> gates, artifacts, and executors.
> **Naming:** step artifacts use the scope prefix `rq2v4`, phase `pN`, order
> `NN` (e.g. `rq2v4_p1_01_liveness_fix.md`) and live in this folder unless
> stated otherwise. Code and tests live in `source/` with the same prefixes
> where campaign-specific; scratch files in `temp/` only, deleted after use.
> **Labels:** modes `both` (compute and storage scaling, dual) / `comp`
> (compute-only) / `stor` (storage-only) / `none` (no-action comparator);
> regimes `cb` (compute-bound) / `db` (data-bound) / `mx` (mixed). Run
> folders: `<ts>_rq2v4_<mode>_<regime>_<seed>`.

---

## Phase map (dependency order)

```
P1 liveness fix (code) ─► P1.3 build ─► P1.4 battery ─► (P1.5 if relief lopsided)
P2 hashing kind (code, written in parallel)
        └─► P2.2 combined build (after the P1.4 battery) ─► P2.3 knee calibration
                                        │
P3 mixed-regime construction ◄──────────┘
        │
P4 experiment plan freeze (review + approval)
        │
P5 campaign execution (VM)
        │
P6 analysis & synthesis
        │
P7 thesis integration
```

P1 and P2 **code** may be written in parallel (disjoint files); **builds and
verification serialize**: the P1-only build and battery come first, then the
combined (P1+P2) build and the P2 calibration — the battery must not run on
an image carrying the hashing kind.

---

## Phase 1 — Liveness/cull fix and verification

**Goal:** under saturation the platform stops culling live added units; the
aligned compute action relieves both lanes and sticks.

1. **P1.1 Diff draft** — artifact `rq2v4_p1_01_liveness_fix.md`. Three minimal
   patches (review-gate anchors below; exact paths and lines re-verified
   against the code during the draft):
   (a) refresh node presence on **every** delivered window, outside the churn
   guard (`main_n1.py` / `main_n2.py`, review anchor `main_n1.py:967–973`);
   (b) empty/no-evidence windows must not produce absence evidence anywhere
   in the chain: the overload-history append site (`main_n1.py:568–573`),
   the churn guard's direct `s.overload` read (`main_n1.py:967`), the
   absence evaluation (`node_registry.py:125–152`), and the upstream
   overload computation for no-evidence windows (`aggregator.py:143–163`);
   (c) periodic heartbeat for dynamic containers — **both** compute and
   storage sidecars (`telemetry.py:157–165, 209–213`; storage-side
   enablement at `storage_node_manager.py:376` / `mongo_telemetry.py`) — with
   liveness-only semantics: heartbeat-only samples must not enter routing
   stats as zero-latency entries (`aggregator.py:479–500` →
   `main_n1.py:558–568`), which would distort assignment.
   Pinned here: the campaign operating point — dynamic caps 6/6 per domain
   (aligned with v3 RQ2 and the thesis appendix; the mode env files set
   `MAX_DYNAMIC_COMPUTE`/`MAX_DYNAMIC_STORAGE` = 6/6 over the canonical
   override, which currently carries 3/3 — used from the battery onward;
   revisit only with evidence), the relief windows/thresholds used by the
   battery's gate (c) (v3 convention), and the config belt
   `TELEMETRY_TIMEOUT_S` (already 600 s — verify at apply). Docs: the
   heartbeat decision note lives at
   `docs/operation/archive/other/heartbeat_dynamic_node_gate_plan.md` —
   supersede it with the new decision (or record the supersession beside
   it).
   **Gate: user approves the diff before anything is applied.** Refined,
   review-cleared anchors and exact diffs:
   [`rq2v4_p1_01_liveness_fix.md`](rq2v4_p1_01_liveness_fix.md) —
   `_compute_overload` untouched (additive `request_evidence` flag);
   extra gated sites (release-recall feed, scale-down evaluation,
   delivery-freshness bound); churn-guard read unchanged by design;
   mode deltas `rq2v4_mode_*` created here for the battery.
2. **P1.2 Implement + tests** ✅ (2026-10-11) — patches applied; new
   `source/scripts/testing/rq2v4_p1_02_liveness_selftest.py` green (27
   assertions incl. the live aggregator contract); config belt (4 mode +
   4 transport deltas) and `rq2v4_launch_run.sh` added; implemented-diff
   review gate closed (critical candidate-staleness finding fixed).
3. **P1.3 Build + deploy (P1-only)** — sync the VM checkout to the fix
   commit (the controller runs from the bind-mounted checkout — an image
   rebuild does not deploy it); rebuild the `local_state_server` image with
   the fix (record its id) — edge images unchanged (heartbeat code already
   present; enabled via docker-run env) — deploy to `cloud-vm-rq2`, low-rate
   smoke run. **Gate: smoke clean, telemetry continuous, no startup
   regressions; lockstep asserted per the artifact §11.**
4. **P1.4 Verification battery** — 5 runs (lean core, author-scoped
   2026-10-11) under the `rq2v4_mode_*` deltas merged over the canonical
   override (canonical phases file edited in place per shape; snapshots
   captured per run):
   (i) compute-bound at the hard rung (rate 2.5): `none`/`comp`/`stor` (3) —
   `comp` must relieve **and** unlock, `none` must stay bound, `stor` must
   not relieve (specificity);
   (ii) data-bound re-anchor pair (`none`, `stor` at the campaign data
   config) — the fix changes liveness/scale-down semantics, so the
   data-bound row is re-anchored post-fix.
   Full retention + 1 Hz host sampler
   (`source/scripts/testing/rq2v4_p1_04_host_sampler.py`).
   Optional add-ons only if a gate needs disambiguation (author-informed):
   the 2.25 relief rung and the regime-shift run. The RQ1-mode smoke set is
   **out of RQ2 scope** (RQ1-owned; what/where/how/why recorded in the
   artifact §12.1).
   **Gates: (a) zero culls of added units [primary]; (b) no removal of any
   added unit across its episode plus the post-phase margin; (c) `comp`@2.5
   relieves both sides — pre/post window CPU ratio ≤ 0.75 (artifact §11) —
   and unlocks (lock present pre-add, cleared post-add under the same
   window convention); (d) no more than 2 consecutive empty windows;
   (e) added units keep receiving assignments, and window/routing stats
   show no zero-latency poisoning.** Artifact
   `rq2v4_p1_05_verification.md`.
   **Outcome (2026-10-11):** battery executed 5/5 valid —
   `rq2v4_p1_05_verification.md`. Gates (a)/(b)/(e) **pass**, (d) **pass
   episode-scoped**, (c) **not evaluable as pinned**: the action fires +21 s
   into the episode and 2.5 no longer locks on the repaired platform (none
   p95 86 ms) → **press re-anchor moves to P2** (Finding F1). One latency
   burst recorded with the host-interference hypothesis (Finding F2) —
   confirm during P2 calibration under strict host quiescence; protocol
   hardened: no host-side heavy commands during episodes. P4 must also pin
   `TELEMETRY_SOURCE` and `SCALEUP_POLICY` explicitly.
   **Decision gate:** (c) not evaluable ≠ failed — no P1.5.
5. **P1.5 (conditional) Assignment engagement** — time-boxed diagnosis of why
   added nodes miss load rotations (routing metric staleness / per-minute
   rotation); minimal fix; re-run the failing battery rows.
   **Not triggered** (2026-10-11): every added unit served in the battery;
   the rotation itself is a selection behaviour, recorded as a measurement
   note in the verification artifact §4.

**Exit:** battery green, or a documented residual with an explicit decision.

---

## Phase 2 — Hashing request kind (honest compute press)

1. **P2.1 Spec + implement** ✅ (2026-10-11, review-clean 4 rounds) — artifact
   [`rq2v4_p2_01_hash_kind.md`](rq2v4_p2_01_hash_kind.md): endpoint
   `/compute/hash` (`HASH_WORK_FACTOR` env, default 25000; **in-container
   measured basis: raw ≈ 8.7 ms/request, wall quota-quantization dominated —
   spec §1.2**, seeded by `hash_chain` in `compute.py`), generator kind
   `hash_challenge`, carrier mechanics with two lift points + controller `-e`
   (all carrier combinations reduce to one value); selftest
   `source/scripts/testing/rq2v4_p2_01_hash_kind_selftest.py` green
   (all assertions). Expected campaign press: ≈5–10 rps/lane capacity at
   0.15 ⇒ ladder rungs 0.20–0.35 — P2.3 seats the rate.
2. **P2.2 Build + deploy** ✅ (2026-10-11) — edge image rebuilt
   (`30a2c88bc1ce → 12c9ef0dc4b7`, edge_server only); lockstep asserted
   (static edges on the new image, endpoint live incl. the 400-on-missing-
   nonce contract); mixed smoke `20261011_201900_rq2v4_p2_smoke`: all six
   kinds served, 0×5xx, 0 culls, no exceptions. Discovery recorded in the
   spec §1.2: VM CPU ~3× the P2.1 host (8.7 ms raw per request); in-container
   wall latency is quota-quantization dominated; measured hash capacity
   ≈ 5–10 rps/lane at 0.15.
3. **P2.3 Knee calibration** — **done 2026-10-11** (artifact
   [`rq2v4_p2_02_knee_calibration.md`](rq2v4_p2_02_knee_calibration.md)):
   ladder seated **R_s = 0.20** (0.25–0.35 skipped by decision logic —
   first rung locked both lanes: 95.3/100 % windows ≥ 1 s, p50 ≈ 1.9 s);
   **press gate PASSED**. Seat runs at 0.23: `comp` engaged fully
   (6+6 units, all serving) but **relief FAILED** (lock persisted, ~1.8 s
   p50 sustained); `stor` **specificity PASSED**; margin PASSED. Mechanism
   signature: traffic concentrates one-unit-at-a-time (multi-window hot-seat
   rotation); queue sits ahead of the serving handler. Seat freeze deferred.
4. **P2.5 Relief diagnosis (read-only)** — **done 2026-10-11** (autopsy #3;
   artifact [`rq2v4_p2_03_relief_diagnosis.md`](rq2v4_p2_03_relief_diagnosis.md)):
   the funnel = per-client DNAT binding + synchronized 60 s hard-timeout
   epochs + deterministic single actor per burst (argmin `tied=1` or an
   unconsumed 45 s warm claim); one unit per lane serves each epoch ⇒ added
   capacity never becomes concurrency. Fix options ranked; recommended =
   ε-band tie-spread (+ warm-band inclusion).
5. **P2.6 Relief repair** — ✅ **implemented 2026-10-11** (author-approved):
   `_BACKEND_SELECTION_SPREAD_EPS` knob (default 0.03, env-overridable,
   0 = legacy) in `scaling_config.py`; `select_server` builds a near-min band
   (cost ≤ min + ε) plus any live warm claim and spreads via a stateless
   deterministic client hash (band sorted by MAC); warm branch joins the
   band instead of monopolising. Selftest
   `source/scripts/testing/rq2v4_p2_06_selection_spread_selftest.py` green
   (band membership, spread balance, determinism, legacy-at-0, warm
   inclusion, beyond-eps exclusion, peer guard). Controller-only — deployed
   by checkout sync (each launcher run recreates the containers).
6. **P2.7 Relief re-seat** — **done 2026-10-12; gate FAILED, diagnosis
   recorded** (`rq2v4_p2_02_knee_calibration.md` §6): the P2.6 spread broke
   the timeout regime (comp timeouts 229 → 0, completion up, lan1 fan-out up
   to 5 MACs/epoch) but the ε-band collapses to one member in most bursts
   whenever a unit is strict argmin by > ε (lan1 5/9, lan2 8/9 epochs
   one-hot) — relief failed as pre-registered (0/15 post-add windows both
   lanes); the single band=5 epoch coincided with full relief (p50
   0.05–0.12 s). Stor specificity passed. → P2.8.
7. **P2.8 Band floor + verification re-seat** — **done 2026-10-12;
   verified** (artifact
   [`rq2v4_p2_08_band_floor.md`](rq2v4_p2_08_band_floor.md) §6): mechanism
   gates all pass — band = 4 in every steady-state epoch, every
   floor-complete burst seats all 4 members, 3–4 concurrent servers
   sustained (48/61 windows per lane), stor specificity held, comp
   completion 100 %, timeouts 0, T_proc halved. Relief passes in the
   post-engagement steady state (83.3/82.1 % of windows, medians ≈ 0.5 s);
   the pinned post-add window fails structurally (first floor-complete
   burst ≈ add+177 s — the re-selection cadence, not the repair) →
   **D12**: campaign relief gate re-anchored to that steady state, with
   time-to-relief as a measured endpoint. **Seat frozen** (R_s = 0.20 /
   hash 25000 / quota 0.15 / caps 6/6) → Phase 3.
8. **P2.4 Workload documentation** — update the demand-model/kind and phase
   tables in the operational docs (e.g.
   `docs/operation/testing/testing_workloads.md`, already stale vs
   `phases.json`) to the v4 kinds: add `hash_challenge`; `service_pressure`
   stays a platform kind but is not a v4 stressor.

**Exit:** compute-bound regime constructible and treatable with the new kind
(no-action locks; compute-only relieves; storage-only wastes).

---

## Phase 3 — Mixed ("both") regime construction

1. **P3.1 Levers study** — **done (2026-10-12)**, artifact
   [`rq2v4_p3_00_levers.md`](rq2v4_p3_00_levers.md): hold edge 0.15 (the
   frozen seat), move the storage member quota to 0.08 as the balancing
   lever, mix `hash_challenge 0.205 : content_lookup 0.795`, R_m = 1.15 →
   5.66 hash + 21.9 lookup rps/lane; co-press math + margins; ~7-run ladder
   (3 rate rungs + 1 contingency + 3 pilots) with a 4-leg pass criterion,
   exact decision-log evidence, D12/v3-B2 relief anchors. **Awaiting author
   decisions (artifact §5 items 1–10) before P3.2.**
2. **P3.2 Calibration ladder** — **running (2026-10-12, approved; all 10
   study decisions per artifact §5)**: ~6–8 runs: vary total rate at fixed
   mix/quotas → find the point where `none` degrades on **both** tier
   signals (both fire in the decision log); if one tier does not fire, add
   quota-shift rungs (edge/member) before concluding; pilots: dual relieves
   both sides; compute-only leaves the storage side unrelieved; storage-only
   leaves the compute side unrelieved. Artifact
   `rq2v4_p3_01_mixed_calibration.md` (frozen mix, quotas, rate).
   **Decision gate:** if the co-press is not stable after one quota-shift
   round (time-boxed), **stop and bring options to the author** — quota
   rework vs a revised D6. Do **not** silently substitute the sequential
   variant: it is a different treatment (D7), not a fallback.

**Exit:** mixed regime frozen with manipulation evidence.

---

## Phase 4 — Campaign plan freeze

1. **P4.1 Author [`experiment_plan.md`](experiment_plan.md)** — executor:
   Edge Experiment Designer. Must contain: treatments (3 modes × 3 regimes);
   held constants; **config mechanics, file by file** — the three demand
   regimes are *workloads*: the single canonical
   `source/scripts/testing/phases.json` is **edited in place** per regime
   (regime-major ordering minimises edits; every run folder keeps its
   `phases_snapshot.json` and preflight verifies it); the three mode regimes
   are *named configuration regimes*: env deltas merge over the canonical
   override in `source/scripts/testing/controller_env_overrides/`
   (precedent: `mechanism_necessity_*.env`, `research_q3_launch_run.sh`;
   the four `rq2v4_mode_*` deltas are created in P1.2);
   **no variant duplicates and no copies under `docs/`.**
   Replication 7 per cell (D5) + no-action comparator per regime;
   **enumerated seeds** (7); **block = 4 runs** (one regime: the three modes
   + its no-action comparator, sharing one seed) × 7 seeds × 3 regimes =
   **84 runs**; counterbalanced order within blocks; per-run naming
   `<ts>_rq2v4_<mode>_<regime>_<seed>` (analyzers glob by name); screening
   rules, exclusions, and **manipulation checks as per-run inclusion
   criteria**; pre-registered per-cell expectations (the matrix) with
   **numeric gate magnitudes and the CI method** inherited from the v3
   conventions (medians of per-replicate ratios, 95 % CIs, replicate
   floors); analysis plan and tool paths; run matrix and launcher deltas.
2. **P4.2 Auto-review gate** on the plan; fix all critical/warning findings.
3. **P4.3 User approval.**

**Exit:** frozen plan.

---

## Phase 5 — Campaign execution (VM)

1. **P5.1 Preflight** — image/config hashes, seeds, canonical snapshots
   captured per run, launcher dry-run, **disk-headroom check for full
   retention** of the whole campaign.
2. **P5.2 Blocks in counterbalanced order, regime-major** (fewer canonical
   phases edits, cleaner batches) — passive monitoring; per-run screening;
   incident protocol (document, exclude, rerun slots); **full retention
   until analysis completes** (slim-archive only after P6, per the Part D
   lesson).
3. **P5.3 Campaign log** + run-matrix status maintained per run.

**Exit:** all valid runs collected; exclusions documented with causes.

---

## Phase 6 — Analysis & synthesis

1. **P6.1 Cell statistics + gate battery** → `results.md`; analyzers adapted
   from `source/scripts/testing/analysis/rq2/` (new `rq2v4` variants as
   needed).
2. **P6.2 Figures** — relief per regime, latency per regime, engagement,
   resource use; cross-mode comparison graphs per the repository skill.
3. **P6.3** `post_run_analysis.md` + dossier update
   (`tese/research_questions/rq2/`): v4 supersession of the conclusions
   record; fix the stale v3 note (ba relief 9/10 → 8/10, artifact-verified)
   as part of the record.

**Exit:** analysis records complete; gates reported honestly, including
unmet ones.

---

## Phase 7 — Thesis integration

1. **P7.1** Ch1/Ch2 RQ2 text re-derived from the final core (question,
   contribution bullet, gap row) — the parked simplification batch re-based
   on the v4 evidence; core-independent term fixes applied in the same pass.
2. **P7.2** Ch5 §5.3 rewrite for the 3×3 (design table, figures, per-cell
   outcomes, honesty on unmet gates).
3. **P7.3** Ch5 §5.5 synthesis row; Ch6 answers/limitations/future when
   written.
4. **P7.4** Appendix v4 config rows (including `HASH_WORK_FACTOR`).
5. **P7.5** Auto-review + build; reload reminder to the author.

**Exit:** thesis text frozen for this campaign.

---

## Run budget (VM, ~25 min/run)

| Phase | Runs |
| --- | --- |
| P1 verification battery (lean core) | 5 |
| P2 knee calibration | ~5 |
| P3 mixed calibration | ~6–8 |
| P5 campaign | 84 + spares ~14 |
| **Total** | **≈ 116** |

Wall clock: ≈ 50–65 VM-hours including switching — run in daily batches.

---

## Risks and decision points

- **P1.4 relief still lane-lopsided** → P1.5 assignment investigation
  (time-boxed; if unresolved, document as a platform limit).
- **P3 co-press unstable** → quota rework, then an **explicit author
  decision** on any D6 revision; never a silent substitution (the sequential
  variant is a different treatment, D7).
- **RQ1 teardown divergence:** the fix replaces absence-driven teardown with
  heartbeat-backed liveness; RQ1 archived results stand as the pre-fix
  record (audit: artifact §12.3; decision D9). Teardown replication is
  parked, not planned.
- **Retention:** full until P6; slim-archive only after analysis (Part D
  lesson).
- **No pooling with v3** (platform + workload era changed): v4 stands alone.
- **Pre-existing ~1 s baseline tail** (autopsy item): check in the P1.4
  samples; handle in analysis if it touches any gate.
- **Build/era discipline:** record image hashes and config snapshots per
  run; one variable per verification step; the battery runs on the P1-only
  build, so the hashing kind cannot confound it.

## Executors

- Code diffs/implementation: main session + implementation agent; **user
  approves every diff before apply**.
- VM runs: Edge Experiment Runner (`cloud-vm-rq2`).
- Experiment plan: Edge Experiment Designer; reviews via `general-purpose`
  (custom-agent model-pitfall rule).
- Analysis: Edge Experiment Analyzer.
- Thesis text: main session with the `thesis-writing` skill, per the
  propose-approve-verify workflow.
