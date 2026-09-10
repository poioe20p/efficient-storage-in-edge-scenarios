# RQ3 QoE-Consequence Configuration Discovery — Plan (approved draft)

**Family:** reframed RQ3, Family 3 (QoE consequence). Family 2
(`rq3_robustness`) established the frozen-regime envelope (0.28–0.69% failure)
and was **STOPPED by user decision after 19 valid runs** because n=6/arm
cannot produce *visible* service degradation at the 0.15 quota. This family
descends a uniform-quota ladder to find and lock a **reasonable** low-headroom
configuration where readiness-event loss produces a **visible, bounded** QoE
consequence — then certifies that contrast as headline evidence.

**Status:** pre-registration approved 2026-09-07 (Approach A). Discovery in
flight: rungs 0.13/0.12 C1-INELIGIBLE (pressure gates), rung 0.11 run 1
launched. **Amendment 2026-09-08 (user-approved): slow-share QoE axis** added
as a co-primary — QoE worsening = "higher latency and/or timeouts" — see
§3/§4/§5 and the changelog at the end of this document.

## 1. Objective and treatment

Discover and lock a **reasonable** low-headroom configuration in which total
readiness-event loss (`loss_all`) produces **visible, bounded service
degradation** in the `event_only` arm while `hybrid` (20 s fallback) and
`reconcile` (10 s discovery) stay healthy — then certify that contrast as QoE
headline evidence at n=6/arm.

**QoE definition (amendment 2026-09-08):** "visible" is read on two co-primary
axes — plateau pooled `timeout_rate` and the slow-share `slow_rate` (requests
slower than 1.0 s or timed out; see §3) — each with a ≥5 pp
`event_only`-vs-controls contrast; "bounded" requires `event_only`
`bad_rate ≤15 %` **and** `slow_rate ≤25 %` plus controls healthy on both axes
(`bad ≤1 %` ∧ `slow ≤2 pp`).

**Reasonableness boundaries (hard):**

- No controller/application code changes; fault knobs and arm env deltas are
  reused **byte-identical** from the robustness family (`rq3rob_*.env`,
  `rq3sat_direct.env`, `rq3sat_discovery.env`).
- Workload frozen at canonical P4 (pure-compute plateau, 24 clients/LAN, rate
  1.5 — the measured driver-clean ceiling) from the frozen worktree at commit
  `852a8a3` (final robustness attestation).
- Single swept axis: **uniform `EDGE_CPUS` quota** (static + dynamic compute),
  ladder `{0.13, 0.12, 0.11, 0.10, 0.09}` descending.
- A collapsed regime (controls degrade, driver collapse, baseline errors) is
  **invalid** — never evidence, never "chased" by further lowering.

Arms (one per run):

| Arm | Configuration | Behavior under loss_all |
| --- | --- | --- |
| `event_only` | direct + `READINESS_EVENT_FALLBACK_S=130` (inert, > probe max 120) | every lost app_ready event yields an **abandoned** backend; no recovery → static tier carries the plateau |
| `hybrid` | `rq3sat_direct.env` (fallback 20 s) | lost events recovered by fallback probe (~20 s cadence) |
| `reconcile` | `rq3sat_discovery.env` (10 s poll) | discovery-only; unaffected by event drops |

Fault cells (one per run):

| Cell | Injection | Pre-registered contrast |
| --- | --- | --- |
| `none` | no fault | health floor at the locked quota: event_only must stay healthy (bad_rate ≤1%, event fraction 1.0, ≥1 event admit/LAN, 0 abandoned) |
| `loss_all` | every app_ready event dropped (`READINESS_EVENT_DROP_MODE=all`) | event_only abandons all new backends → degradation; hybrid/reconcile recover → healthy |
| `loss_alt` | every 2nd app_ready event per LAN dropped (`mode=alternate`) | event_only loses ~half of backends (aggregate claim only); hybrid/reconcile recover |

## 2. Approaches (Pass A)

**Approach A — Uniform-quota ladder with calibration/evidence split
(recommended and adopted).** Sweep `EDGE_CPUS` down the ladder {0.13 … 0.09};
per rung screen the 3 `loss_all` arms (C1); measure the QoE contrast (C2);
lock the first (highest) rung where `event_only` degrades ≥5 pp while controls
stay ≤1%; confirm at 2 fresh seeds (C3); then certify at fresh seeds n=6/arm
(E). Pros: single fair axis, mechanism-faithful, reuses all attested tooling,
dose-finding explicit. Cons: 2–4 discovery stages before evidence; worst case
no qualifying rung (pre-registered STOP).

**Approach B — Demand escalation first (rejected).** Keep quota at 0.15 and
raise rate above 1.5. Violates the certified driver envelope first, stresses
all arms symmetrically (contrast weaker and harder to bound), less
"reasonable" as an edge regime.

**Approach C — Scale-gate retuning (rejected).** Slower recovery or capped
scale-out depth to amplify loss. Structurally dead: an arm that admits zero
dynamics is unaffected by scale caps — only controls degrade, shrinking the
contrast. Cooldown retunes also change attested mechanism semantics.

## 3. QoE measurement contract (family-defined)

- **Window:** `compute_plateau` bounds from the run's `phases_snapshot.json`;
  rows selected by `sent_at`.
- **Classes:** `completed` / `timeout` (driver status); `failure` =
  completed ∧ non-2xx; `canceled`/`dropped` excluded from rates but counted in
  `offered` (driver-clean gate: <5%).
- `timeout_rate = timeout / (completed + timeout)`;
  `failure_rate = failure / completed`;
  **`bad_rate = (timeout + failure) / (completed + timeout)`** (aggregate;
  explicitly **≠** sum of the two components — different denominators).
- Computed **per LAN then pooled** (pooled = both LANs combined).
- Floors: ≥5,000 pooled service rows and ≥1,000 per LAN in the plateau window;
  **baseline-phase floor pooled ≥100 and per-LAN ≥50** (the P4 baseline is
  ~2 active clients/LAN at `client_fraction` 0.1 over 60 s ≈ 120 rows/LAN, so a
  floor of ≥1,000 per LAN is unreachable; the baseline floor is an
  artifact-sanity minimum — enough rows for the baseline `bad_rate` ≤1 % read
  to be meaningful, never a workload target).
  *Amendment 2026-09-07 (approved): replaces the earlier draft's unreachable
  "≥1,000 per LAN baseline" figure.*
- Canceled/dropped counted in `offered`; pooled `cancel_rate < 5%` is a
  driver-clean gate (no driver collapse).
- **Slow-share axis (amendment 2026-09-08):** `slow_rate = #(plateau service
  rows with status == "timeout" OR (latency_s valid AND latency_s > 1.0 s)) /
  (completed + timeout)`, pooled; per-LAN reported descriptively. A timeout is
  slow unconditionally (driver cap 300 s > threshold; a missing/unparseable
  latency never drops it). Canceled/dropped excluded from numerator and
  denominator. Contrast `Δ_slow = slow_rate(event_only) − max(slow_rate(hybrid),
  slow_rate(reconcile))`; lock bar = the same 5 pp as the timeout axis.
  Descriptive-only: completed-row p50/p95/p99 latency, `slow_5s` (same formula,
  5 s). The baseline window gains **no** slow gate (noise at ~120 rows/LAN);
  baseline keeps `bad_rate ≤1 %` + `http000 = 0`.
- **Controls healthy on both axes (hard, every stage):** plateau pooled
  controls (hybrid, reconcile) `bad_rate ≤1 %` **and** `slow_rate ≤2 pp`;
  none-cell (all arms) the same two ceilings. Per-arm `slow_rate ≥
  timeout_rate` always holds; `Δ_slow` can sit below `Δ_timeout` by up to the
  controls' slow share (≤2 pp) — a timeout-only lock remains possible.

## 4. Stages

| Stage | What | Gates / decision | Runs |
| --- | --- | --- | --- |
| **C0** | Frozen tag `rq3qoe-preflight-<date>` **from commit `852a8a3`** (final robustness attestation), detached worktree `~/rq3qoe_frozen`; verify `HEAD == 852a8a3`; `rq3qoe_p0_01_prepare_tag.py` hashes from that tree | mismatch = STOP | 0 |
| **C1** | Eligibility screen (per rung, seed 5301, 3 `loss_all` runs = one per arm) | Outcome-blind eligibility: integrity (D1/D2/D3/quota/flow A-B-D hard + C ≥0.85 + driver clean), mechanism per arm (event_only 0 admitted, ≥2 abandoned/LAN, zero `probe_fallback`, drops `mode=all`; hybrid all `probe_fallback`; reconcile all probe; ≥1 admit/LAN; no plateau scale-down), pressure (old-backend CPU median [60, 85] %, p95 ≤95 % in 30 s pre-first-ready), **controls `bad_rate ≤1 %` ∧ `slow_rate ≤2 pp` (pooled plateau) + baseline `bad_rate ≤1 %`** (baseline is pre-treatment — no spawns, no drops — so fault-independent) | ineligible → next rung; all 5 rungs ineligible → STOP | 3–15 |
| **C2** | Contrast probe (reads the C1 runs of the current rung; no new runs) | lock iff **eligible** ∧ **both axes bounded** (event_only `bad ≤15 %` ∧ `slow ≤25 %`) ∧ (`Δ_timeout ≥5 pp` **OR** `Δ_slow ≥5 pp`); `lock_component` = slow when Δ_slow qualifies (slow-first precedence), else timeout | first eligible rung with a visible, bounded contrast = **lock candidate**; visible but unbounded → **STOP-NULL** (regime-unreasonable, monotone in quota — never descended) | 0 |
| **C3** | Lock confirmation — **immediate re-run for reproducibility** (user directive: as soon as visible degradation is found, re-run) | 2 fresh seeds (5302, 5303) × 4 runs (3 arms `loss_all` + `event_only`×`none`); lock iff **both** seeds confirm **the same `lock_component`** (≥5 pp on that axis) **and** all C1 gates **and** both-axes boundedness **and** none-cell healthy (bad ≤1 % ∧ slow ≤2 pp); monotone-gate failure (boundedness / none-cell health) → **STOP-NULL**; contrast non-reproduction only → next rung | failure → next rung (contrast only); at 0.09 → STOP (NULL report); 2 consecutive C3 ineligible (incl. integrity voids) → STOP | 8–16 |
| **Midpoint rule** | If rung q eligible but Δ <5 pp AND q+1 C1-ineligible → one C1 screen at midpoint quota ((q + q+1)/2) | eligible → C3 entry; midpoint C3 failure → STOP | bounded | 0–11 |
| **E** | Evidence | Fresh seeds 5201–5206; cells `none`/`loss_all`/`loss_alt` × arms × 6 blocks = **54 runs**; per-block arm rotation (replicate r = rotation r), arm-major, cells none→loss_all→loss_alt, full reset between runs | H-Q1…H-Q4 below | 54 |

**Ladder discipline (user directive):** descend one rung at a time; the moment
C2 shows a visible contrast (Δ_timeout **or** Δ_slow ≥5 pp) on an eligible
rung, **stop descending and run C3 immediately**. Never continue lowering
quota to "chase" a stronger effect. A visible-but-unbounded contrast at the
first visible rung is a STOP-NULL (regime-reasonableness; monotone in quota —
descending cannot repair it).

**Verdict exit codes (amended analyzer):** `0` lock · `2` descend ·
`3` STOP-NULL (family-terminating). A legacy/pre-v2 `c1.json` fed to C2/C3 is
a STOP (exit 3), never a fallback.

## 5. E-stage hypotheses (locked rung, all pre-registered)

- **H-Q1 (timeout co-primary):** `loss_all` `timeout_rate` (and `bad_rate`
  secondary): `event_only > hybrid` and `> reconcile`; per-block contrast
  `Δ_timeout = timeout_rate(event_only) − max(hybrid, reconcile)` ≥5 pp in
  ≥4/6 timeout-assessable blocks and ≥5 pp median; exact MWU + Cliff's δ on
  the per-block Δ list vs zeros (n reported; <4 assessable blocks ⇒ not
  assessable).
- **H-Q1b (slow co-primary, amendment 2026-09-08):** `loss_all` `slow_rate`
  (threshold 1.0 s; timeouts slow unconditionally): per-block contrast
  `Δ_slow = slow_rate(event_only) − max(hybrid, reconcile)` ≥5 pp in ≥4/6
  slow-assessable blocks and ≥5 pp median; MWU + Cliff's δ on the per-block
  Δ_slow list vs zeros (exact H-Q1 mirror, paired by block).
- **Controls health (both axes, both components):** controls `bad_rate ≤1 %`
  AND `slow_rate ≤2 pp` (pooled plateau). Per-axis assessability:
  timeout-assessable = floors + driver-clean + controls bad ≤1 % + Δ
  computable; slow-assessable = the same + controls slow ≤2 pp + Δ_slow
  computable.
- **Boundedness (both, hard):** event_only `bad_rate` median ≤15 % ∧ ≥4/6
  blocks ≤15 % (over timeout-assessable blocks); event_only `slow_rate` median
  ≤25 % ∧ ≥4/6 blocks ≤25 % (over slow-assessable blocks). Failure =
  component FAIL (reported; the other component judged separately). Neither
  ceiling voids the other component's magnitude. Because both ceilings are
  hard, a timeout-only headline still requires slow-axis assessability
  (≥4 slow-assessable blocks) — stated, never inferred.
- **H-Q2 (bad dose):** event_only per-block `bad_rate` ordering
  `loss_all ≥ loss_alt ≥ none` in ≥4/6 timeout-assessable blocks; supporting
  MWU loss_all vs loss_alt.
- **H-Q2b (slow dose, amendment 2026-09-08):** the same ordering on
  `slow_rate` in ≥4/6 slow-assessable blocks; supporting MWU loss_all vs
  loss_alt.
- **H-Q3 (mechanism carryover):** loss_all preservation 0.0 / 1.0 / 1.0
  (event_only / hybrid / reconcile); loss_alt event_only per-run aggregate in
  [0.3, 0.7] (hypothesis range only — never a void reason); hybrid/reconcile
  1.0 per LAN unit.
- **H-Q4:** none-cell all-arms `bad_rate ≤1 %` AND `slow_rate ≤2 pp` (health
  floor only; no equality claim).
- **Overall pass:** `(H-Q1 ∧ H-Q2) ∨ (H-Q1b ∧ H-Q2b)` ∧ both boundedness ∧
  H-Q3 ∧ H-Q4. Whichever co-primary certifies is the headline; the other is
  reported, never OR-combined post hoc. The two 5 pp bars are not
  severity-equivalent (a slow request is milder than a timeout); the headline
  wording names the certifying component.
- **Direction checks:** blocks 3 (2-of-3) and 5 (3-of-5) on each axis's
  contrast; failed directions reported, never chased.
- **Void rule (all stages):** integrity/harness voids (D1/D2/D3/quota/flow/
  driver, baseline http000, veth/attach failures) → diagnose → replace same
  seat/seed, ≤1 per cell per diagnosed root cause; systemic environmental
  causes require a diagnosed fix before replacement. Controls `bad_rate >1 %`
  or `slow_rate >2 pp` is **not** a void — that block is excluded from the
  corresponding axis (≥3/6 excluded ⇒ not assessable, regime-reasonableness
  failure reported).

## 6. Cost (45 min/run measured cadence incl. full reset)

| Scenario | Runs | Wall |
| --- | ---: | ---: |
| typical (lock at 0.11) | 71 | ≈ 53 h |
| worst S3-reaching | 85 | ≈ 64 h |
| worst incl. midpoint | 96 | ≈ 72 h |
| no lock (STOP) | ≤31 | ≈ 23 h |

## 7. Implementation surface (new files, frozen tree lineage)

1. `source/scripts/testing/rq3qoe_p0_01_prepare_tag.py` (manifest;
   PROTECTED/ARM_ENVS identical to rq3rob — envs reused byte-identical).
2. `source/scripts/testing/rq3qoe_p0_02_analyzer_selftest.py` (synthetic
   fixtures: qoe-screen gates + campaign contrast/H-Q1 unit checks).
3. `source/scripts/testing/rq3qoe_p0_03_preflight.sh` (static checks; manifest
   + image guard + env hash verification + py_compile/bash -n).
4. `source/scripts/testing/rq3qoe_p1_01_launch_run.sh` (mirror
   `rq3rob_p1_01_launch_run.sh`; **adds 5th positional `edge_cpus`** on the
   0.13–0.09 ladder; `quota_snapshot.json` writer takes `EDGE_CPUS` from the
   arg; label prefix `rq3qoe_`).
5. `source/scripts/testing/analysis/rq3/readiness_robustness.py` — add
   `qoe-screen` (C1/C2/C3 gates) and `qoe-campaign` (E-stage H-Q1…H-Q4)
   subcommands; reuse `readiness_low_headroom` helpers (`status_rates`,
   `phase_bounds`, `capacity_summary`, `classify`, etc.).
6. Docs: `docs/operation/testing/experiment/v3/rq3_qoe/`
   {`experiment_plan.md`, `run_matrix.md`, `preflight_campaign.md`,
   `preflight_log.md`}; cross-reference in `rq3_robustness/experiment_plan.md`;
   update `testing_overview.md`, `v3/README.md`.

Non-goals: no `phases.json`/env-delta edits, no controller or application code
changes, no new images (lineage `852a8a3` images already verified), thesis
text unchanged until evidence.

## 8. Budget and stop rules

Discovery C1→C3 is sequential on `cloud-vm-rq3` after the robustness campaign
STOP (no overlap). Between-run checkpoint row per run in `preflight_log.md`
with GO/STOP/DIAGNOSE verdicts. E stage runs only after a lock file
`rq3qoe_quota_lock.json` is written at the locked rung. A failed pre-registered
direction or a boundedness-component failure is reported, never chased.

## 9. Validation before VM

py_compile + analyzer selftest (synthetic fixtures for qoe-screen gates and
campaign H-Q1 contrast); bash -n/shellcheck; env-merge proof (same merge
semantics as rq3rob); manifest/tag identity; launcher negative tests
(bad `edge_cpus`, wrong arg count, bad label); dry run of make vars. No
experiment executes during implementation.

## 10. Changelog

- 2026-09-07 — pre-registration approved (Approach A); baseline-floor
  amendment (pooled ≥100 / per-LAN ≥50 artifact-sanity minimum).
- **2026-09-08 — slow-share QoE axis (user-approved).** Added `slow_rate`
  co-primary (threshold 1.0 s; timeouts slow unconditionally), `Δ_slow ≥5 pp`
  lock component with slow-first precedence, controls slow ≤2 pp gate,
  none-cell slow health, both-axes boundedness (bad ≤15 % ∧ slow ≤25 %) at
  C2/C3/E, H-Q1b/H-Q2b, C3 same-component confirmation, exit code 3 =
  STOP-NULL for an unbounded first contrast and for monotone-gate C3 failure,
  and `c1.json` `contract_version: 2`. **Approver: user, 2026-09-08.**
  Step 0 sanity (0.13/0.12 retained runs, read-only): controls slow@1 s
  ≤1.26 % (2 pp ceiling feasible), healthy completed p99 ≤0.46 s (1.0 s
  threshold sits well above the healthy tail), Δ_slow already 2.2–3.0 pp
  where Δ_timeout was 0.64 pp.
