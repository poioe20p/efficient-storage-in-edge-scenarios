# RQ2 v2 Rework Plan — Bottleneck-Aware Scaling Action (final evidence)

**Date**: 2026-08-04 · **Status**: 🔵 Plan (reviewed) — awaiting implementation
**Review gate**: 2 rounds of Reviewer (deepseek-v4-flash, to-be-implemented) —
Round 1: 4 🔴 / 12 🟡 / 5 🔵; Round 2: 3 🟡 / 4 🔵; all 🔴/🟡 resolved (see §8).
**Supersedes as primary evidence**: the 2026-08-04 18-run campaign
(`experiment_plan.md`, `results.md`) becomes **supporting/characterization
evidence** once this rework completes.
**Thesis gates**: `thesis_overview.md` §5/§8 and `thesis_structure.md` §5.4
(open-loop driver, Mann–Whitney U + Cliff's delta, action-cost measurement).

---

## 1. Why this rework exists

The 18-run RQ2 campaign (2026-08-04) produced directionally correct,
reproducible results (cross-over reproduces in 3/3 replicates; `cf_db` pins
p99 at the 30 s timeout; `ba_db` is the cleanest data-bound cell). It is
**not** final thesis evidence because of five structural gaps:

| # | Gap | Evidence |
|---|---|---|
| G1 | **Latency-coupled sync driver** (`traffic_generator.py` `client_loop()` awaits each curl; 1 in-flight/client; issued rate = min(rate, 1/latency)). In the data-bound episode, `cf_db`/`sf_db` issued ~60 % *less* load than intended while `ba_db` issued ~29 % *more* — the arms faced different demand. | driver code; `campaign_dataset.csv` ep_p50 vs rate; RQ1's own `results.md` acknowledges the same for RQ1 ("offered load differs per arm (latency-coupled driver)") |
| G2 | **p99 censored at 30 s** (`CURL_MAX_TIME=30`): `p99=30000.0` is the cap, not a measurement; timeout conflated with failure (`http_status != 200`). | `campaign_dataset.csv` `ep_p99_ms=30000`; `traffic_generator.py` `--max-time` |
| G3 | **No statistics**: n=3 cannot reach Mann–Whitney U significance (min p = 0.10 at n=3); no effect sizes, no censoring-aware reporting. | `results.md` (no MWU/Cliff's delta); thesis §5.4 mandates both |
| G4 | **`ba_db` both-tiers confound**: `ba` scaled compute 8 + storage 8 per LAN; its quality edge over `sf_db` may be capacity, not classification. **Verified**: `policy_gate.py:select()` already returns a single tier per window, so the 8+8 is cross-window (both tiers fired on different windows); the clean H1 test therefore needs a **sticky commitment** (ba-strict) that suppresses the non-classified tier. Efficiency claim over-stated (`ba_db` 4.29 vs `sf_db` 3.21 node-min/1000). | `policy_gate.py:select()`; `campaign_dataset.csv` `dec_compute_actions=8, dec_storage_actions=8`; `results.md` criterion 9 |
| G5 | **Promised-but-unmeasured**: replica-sync action cost (rq2.md §3/§5; thesis §5.3/§0.3) is qualitative only; relief metric partial in the compute-bound regime (criterion 6); dataset denominators inconsistent (`sel_*`/`reason_*` subsets vs decision universe). | `analysis_focus.md` §3; `results.md` criterion 6; `campaign_dataset.csv` |

**Decision basis (user-approved, 2026-08-04, then scoped 2026-08-04):** rework
on all fronts; approach chosen = **Full compliance rework** (build the
open-loop driver, n=3, effect-size statistics, action-cost measurement; the
`ba-strict` arm is implemented but not run). The
open-loop driver is a thesis-wide requirement (§8) needed by RQ1/RQ3 too.

---

## 2. Locked requirements

1. **Driver**: build an **open-loop** traffic driver (arrival process
   independent of completions; per-request synchronous response timing
   preserved). Rationale citation to add: Schroeder, Wierman & Harchol-Balter,
   *Open Versus Closed: A Cautionary Tale* (NSDI 2006) — closed models mask
   overload; currently uncited anywhere in the corpus (verified 2026-08-04).
2. **Timeouts**: per-request cap = `CURL_MAX_TIME=300` s; `timeout` recorded
   as a distinct outcome class (never merged into `failure`). Latency
   percentiles are descriptive only (censoring flag where the cap binds); the
   **per-run `timeout_rate` is the primary degradation statistic** (defined
   for every run).
3. **Replicates**: n = 3 per cell (min achievable MWU p = 0.10 at n=3 — **no α
   claims**; conclusions by Cliff's delta ≥ 0.6 + 3/3 direction consistency,
   scoped to what n=3 supports).
4. **Cells**: 6 cells — `cf_cb, cf_db, sf_cb, sf_db, ba_cb, ba_db` — 18 runs
   total, 3 counterbalanced blocks. The **`ba-strict`** arm (Phase 3: sticky
   commitment — commits to the classified tier and suppresses the other tier
   until relief) is **implemented and unit-tested but NOT run** in this
   campaign; kept as a documented option for a follow-up
   capacity-vs-classification test.
5. **Statistics**: **effect-size hierarchy at n=3 (no α claims)** — per
   episode: aligned vs mis-aligned (headline), `ba` vs mis-aligned, `ba` vs
   aligned (equivalence ≤ 1.5×) on `timeout_rate`, `failure_rate`,
   `node-minutes`, `time-to-recover`; Mann–Whitney U reported **descriptively**
   (n=3 min p = 0.10 — no significance claim); conclusions by **Cliff's delta
   ≥ 0.6 + 3/3 direction consistency**. Other cell-pairs are exploratory
   (Cliff's delta only). Latency percentiles are descriptive
   (median-of-replicates + per-run scatter + IQR) with a censoring flag where
   the cap binds.
6. **Action cost**: measure replica-sync cost per added storage member
   (initial-sync duration, bytes applied, storage CPU during sync) via a **new
   collector** (Phase 2.1) — not inferred from existing artifacts.
7. **Relief**: add "score flattening after action" as a secondary relief
   signal in the compute-bound regime.
8. **Reporting**: offered vs completed recorded separately; unified
   denominators; classifier asymmetry reported honestly (cb ≈ chance, db
   strong); efficiency claim narrowed to "robust, not cheapest".
9. **Docs**: edit canonical files in place (no duplicates). Thesis docs
   updated to lift the "calibration-only" caveat for RQ2.
10. **Seeds**: `RANDOM_SEED=42` = traffic seed **base**. In open-loop mode
    each per-netns worker seeds `random.seed(base + ns_index)` so per-client
    request-type sequences stay distinct (documented change from v1's single
    RNG). Block seeds 2001–2003 for counterbalanced order; `DATA_SEED=42`
    unchanged.
11. **Concurrency budget**: per-client in-flight window and episode rate are
    jointly chosen so `INFLIGHT_WINDOW / rate > CURL_MAX_TIME` (no `dropped`
    within the cap). Target `INFLIGHT_WINDOW=1024`, episode rate ≤ 3
    req/s/client (re-calibrated in G2). With `window/rate > cap`, max in-flight
    = rate × 300 = 900 < 1024, so **`dropped` is unreachable in production by
    design** (offered load fully preserved); `dropped` accounting is still
    implemented and validated via a bounded self-test override (Phase 1.2,
    scenario B). Aggregate in-flight bounded by a pre-flight concurrency check
    (Phase 5 step 1b).
12. **Drain**: `DRAIN_S=30` at each **phase boundary** (must stay < the
    shortest phase, 60 s baseline): dispatch stops at the boundary, in-flight
    requests are awaited up to `DRAIN_S`, then cancelled and logged
    `status="canceled"` (counted in offered, excluded from latency and
    failure, reported separately). Drains are sequential — the next phase's
    dispatch starts only after the previous phase's drain completes (no
    concurrent drain+dispatch). Run-time estimate accounts for it.

---

## 3. Approach comparison (recorded)

| | **A — Full compliance rework (chosen)** | B — Surgical hardening + relabel |
|---|---|---|
| What | Open-loop driver; n=3; effect-size stats (no α); sync-cost; relief-flatten; reporting fixes; ba-strict implemented-not-run | Keep 18 runs; raise timeout to 300; report caveats; MWU on n=3 (effect sizes only) |
| Removes G1? | ✅ yes (confound removed) | ❌ no (only reported) |
| Meets §5.4/§8? | ✅ yes | ❌ no (no open-loop; n=3) |
| Effort / Risk | High / Medium | Medium / Medium |
| Edge impact | Host-side driver only; no image rebuilds | None |

**Why A:** the user asked for a strong, solid evaluation; B keeps the central
confound and cannot support the thesis's primary claim. The driver is shared
infrastructure RQ1/RQ3 need regardless.

---

## 4. Phased task breakdown

File naming convention (scope prefix + order + phase): new files are named
`<scope>_p<phase>_<nn>_<name>.<ext>` where `<scope>` = `openloop` (shared
driver) or `rq2v2` (RQ2-specific). Existing canonical files are edited in
place (never duplicated).

### Phase 1 — Open-loop driver (shared infra) · scope `openloop`

**Goal**: replace the latency-coupled sync driver with an open-loop driver;
prove it preserves offered load under degradation.

| # | File | Action | Task |
|---|---|---|---|
| 1.1 | `source/scripts/testing/traffic_generator.py` | Edit in place | Add `--driver-mode {sync,open_loop}` (default `sync` for back-compat). In `open_loop` mode the **supervisor** (this file's `run()`) keeps the phase timeline and computes the per-phase active-netns mask **with a dedicated seeded RNG** (`random.Random(BASE_SEED)` used ONLY for mask sampling — per-LAN proportional sampling as today, but it no longer consumes the per-client request RNG stream, a documented deterministic improvement over v1's interleaved sampling), writes a **schedule file** (phases + per-phase active mask), then launches **one worker process per netns** and joins them. Each worker (new args `--client-ns`, `--vip`, `--schedule-file`): (a) runs inside its netns (`ip netns exec`); (b) seeds `random.seed(base + ns_index)`; (c) uses an **in-process async HTTP client** (`aiohttp`) with **`TCPConnector(force_close=True)`** so every request uses a fresh TCP connection and a distinct source port (preserves RQ3 per-connection flow semantics — no keep-alive reuse); (d) dispatches only in phases where its netns is in the active mask; (e) fires on the schedule (`interval = 1/rate_per_client` + jitter) and **never awaits completion** before the next dispatch; (f) holds an in-flight slot via `asyncio.Semaphore(INFLIGHT_WINDOW=1024)`; (g) times each request with `time.monotonic()`; (h) per-request timeout = `CURL_MAX_TIME=300`, exceeded → `status="timeout"`; (i) window full → `status="dropped"`; (j) at each phase boundary: stop dispatch → drain in-flight up to `DRAIN_S=30` → cancel the rest (`status="canceled"`) → start the next phase's dispatch (sequential; no concurrent drain+dispatch); (k) writes rows to a **per-worker temp CSV** (`client_requests_<ns>.csv`), merged by the supervisor into `client_requests.csv` (header once). **Preserve `backend_id`** (X-Backend-ID response header) **and `source_port`** (connection local sockname via `resp.connection` transport; record `0` + warn if unavailable) for RQ3 flow-validation compatibility. |
| 1.2 | `source/scripts/testing/openloop_p1_01_driver_selftest.py` | **Create** | Hard gate, wired as `make driver_selftest`. **Scenario A (production config)**: against a synthetic slow endpoint with latency `L` where `L < CURL_MAX_TIME` and `window/rate > cap`: assert issued rate == configured rate, and **zero `dropped`**. **Scenario B (drop accounting, bounded override)**: run with a small `INFLIGHT_WINDOW` and short `CURL_MAX_TIME` (test-only overrides) so the window provably fills; assert the first `dropped` appears exactly at the window bound and is counted separately. In both: (c) `timeout` vs `failure` separated; (d) drain: in-flight at phase end awaited up to `DRAIN_S`, then `canceled`; (e) CSV schema = 13 existing columns **plus** `status` appended as the 14th/last column (consumers validated accordingly). Exit non-zero on any assertion failure. |
| 1.3 | `source/scripts/testing/run_experiment.sh` | Edit in place | Add `TRAFFIC_DRIVER_MODE` passthrough. Replace the single-process `run_traffic()` with: supervisor start, N worker starts (`&`), join with exit-code propagation (`set -euo pipefail`-safe), CSV merge. Run `driver_selftest` before the campaign when mode=open_loop (fail-fast). Collect sync-cost artifacts (Phase 2.1) into the run folder. |
| 1.4 | `source/scripts/Makefile` | Edit in place | Add `TRAFFIC_DRIVER_MODE`, `INFLIGHT_WINDOW`, `DRAIN_S` vars (passed through the sudo env exactly as `RANDOM_SEED` already is, so the per-netns workers inherit them). `CURL_MAX_TIME` **already exists** — no duplicate. Add a `driver_selftest` target. |
| 1.5 | `loader.py`, `metrics_stats.py`, `source/scripts/testing/analysis/rq2/rq2_bottleneck_aware_campaign.py`, and **every other consumer of `client_requests.csv`** (RQ1 analyzers, `cli_*` tools) | Edit in place | **Full consumer audit.** Row-value contract: `timeout` → `http_status="000"`, `latency_s` = elapsed to timeout, `status="timeout"`; `dropped`/`canceled` → `http_status=""`, `latency_s=""`, `status=<class>`. Failure rate = **completed only** (`status=completed` and `http_status != 200`); timeout rate = `status=timeout` / offered; offered = all rows. Never compute failure from a timeout row; never let a stale consumer reintroduce the cap artifact into p99. |

**Phase-1 gate (before any Phase 3/5 work):** `make driver_selftest` passes on the host and inside a netns; legacy `sync` mode still passes existing smoke tests (regression); consumer audit confirms no existing analyzer silently reintroduces the cap artifact.

### Phase 2 — Measurement additions · scope `rq2v2`

**Goal**: deliver the mandated action-cost measurement, fix the relief metric,
and add the statistics layer. Canonical location for per-run analyzers is
`docs/research_questions/v2/rq2/` (per `experiment_plan.md` §6, "referenced,
not duplicated"); the campaign dataset builder stays at
`source/scripts/testing/analysis/rq2/rq2_bottleneck_aware_campaign.py`.

| # | File | Action | Task |
|---|---|---|---|
| 2.1 | `docs/research_questions/v2/rq2/rq2v2_p2_01_sync_cost.py` + collector in `run_experiment.sh` | **Create** | A **collector** samples per-storage-member `rs.status()` state (STARTUP2 → SECONDARY) and, during the sync window, `db.currentOp()` initial-sync fields (`progress`, `bytesToCopy`) via `mongosh` in the storage container; writes `sync_cost.csv` per member: add timestamp, first-SECONDARY timestamp, sync duration, **bytes applied** (derived from `bytesToCopy`/oplog progress deltas; recorded as `null` if unobtainable — sync duration + storage CPU remain the primary metrics), storage CPU during sync (joined with `resource_stats.csv`). The analyzer outputs a per-run summary. **Do not infer from existing artifacts** — the current artifact contract records none of these. |
| 2.2 | `docs/research_questions/v2/rq2/rq2v2_p2_02_relief_flatten.py` | **Create** | Secondary relief signal: "score flattening after action" — target-tier `score_norm` stops rising / plateaus within `RELIEF_FLATTEN_WINDOW_S` after the action, in addition to the existing below-threshold recovery. Outputs `relief_flatten.csv`. |
| 2.3 | `docs/research_questions/v2/rq2/rq2v2_p2_03_stats.py` | **Create** | Effect-size hierarchy at n=3 (see §2.5): per episode, aligned vs mis-aligned (headline) + `ba` vs mis-aligned + `ba` vs aligned (primary) — Mann–Whitney U reported descriptively (n=3, no α claim) + Cliff's delta + 3/3 direction-consistency check, on `timeout_rate`, `failure_rate`, `node-minutes`, `time-to-recover`. **No censored value enters MWU** — latency percentiles are descriptive only. **Missing values**: a comparison is evaluated only where all 3 runs per cell have a defined value; cells with undefined values (e.g., `cf_cb`/`sf_cb` time-to-recover, cells that add no storage for sync-cost) are excluded and reported as counts + medians. Unified denominators (decision universe vs episode-window subset). Output `stats_summary.csv` + console table. |

### Phase 3 — Controller: `ba-strict` mode · scope `rq2v2`

**Goal**: clean H1 test. Verified current behavior (`policy_gate.py:select()`):
bottleneck_aware acts on whichever tier fires per window (both fired →
classified tier). So `ba_db` legitimately scaled both tiers across the episode
(the G4 confound). `ba-strict` adds a **sticky commitment** — a real delta.

| # | File | Action | Task |
|---|---|---|---|
| 3.1 | `source/sdn_controller/policy_gate.py` | Edit in place | Add `BOTTLENECK_STRICT_SINGLE` behavior with a **confidence-qualified commit** (avoids a single spurious fire locking the wrong tier). The gate keeps a `committed` tier (initially empty). It commits when either: (a) **both** tiers fire in a window (classify with D3 margin), or (b) the **same single tier** fires in `STRICT_COMMIT_N` consecutive windows (default 2). While committed, ONLY the committed tier can be selected — the other tier's fires are suppressed but still logged (`*_fired=1`, `rejected_action=<suppressed>`, `selected_action` = committed tier or `none`). The commitment releases when the committed tier's `score_norm` falls back under its threshold for `STRICT_RELEASE_N` consecutive windows (relief); the gate then requires the same confidence trigger to re-commit, and cannot re-commit to the opposite tier before release (no chained oscillation). When `=0`, behavior is **byte-identical** to today. |
| 3.2 | `source/sdn_controller/scaling_config.py` | Edit in place | Add `BOTTLENECK_STRICT_SINGLE` (default 0), `STRICT_COMMIT_N` (default 2), `STRICT_RELEASE_N` (default e.g. 3). The gate reads these directly from `scaling_config` (no `scaling_policy.py` passthrough — that is not how the gate is wired). |
| 3.3 | `source/sdn_controller/main_n1.py`, `main_n2.py` | Edit in place | Wire the committed-tier state through the mediator's per-window `select()` call; verify the 20-column decision log records the suppressed fire (`*_fired=1`, `rejected_action`). |
| 3.4 | `docs/operation/testing/experiment/v2/rq2/env/rq2_bottleneck_aware_strict.env` | **Create** | Copy of `rq2_bottleneck_aware.env` + `BOTTLENECK_STRICT_SINGLE=1`. (Distinct configuration regime — allowed by the canonical-env rule.) |

**Phase-3 gate:** unit check — both tiers firing with strict on yields exactly
one selected action and the suppressed fire logged; a later window where the
non-committed tier fires alone is suppressed; a **single spurious fire does NOT
commit** (needs `STRICT_COMMIT_N` consecutive or a both-fired classification);
release-on-relief works and no opposite-tier re-commit before release; a
**wrong-first-commit scenario** is tested (spurious early fire in the
compute-bound episode must not lock in storage); `BOTTLENECK_STRICT_SINGLE=0`
behavior byte-identical to before (regression).

### Phase 4 — Experiment plan + thesis docs (edit in place)

| # | File | Action | Task |
|---|---|---|---|
| 4.1 | `experiment_plan.md` | Edit in place | Add RQ2-v2 rework section: open-loop driver, n=3, 6 cells, ba-strict implemented-not-run, sync-cost, new gates (driver self-check, stats, censoring), updated hypothesis table, updated timeline (SC1–SC6, effect-size). Mark the 18-run campaign as the v1/supporting record. |
| 4.2 | `run_matrix.md` | Edit in place | Add v2 matrix: 6 cells × 3 replicates = 18 runs, 3 counterbalanced blocks (seeds 2001–2003, **distinct-order verification kept** — re-sample a block's seed on collision), per-run launch with `TRAFFIC_DRIVER_MODE=open_loop`, `CURL_MAX_TIME=300`, `INFLIGHT_WINDOW=1024`, `DRAIN_S=30`, per-netns process launch, sync-cost collection. v2 orders are written to a **new** `counterbalance_order_v2.csv` (never overwrite the v1 file). |
| 4.3 | `analysis_focus.md` | Edit in place | Add `status`-aware metrics (offered vs completed, timeout rate), sync-cost metric, relief-flatten metric, stats contract (MWU + Cliff's delta), unified denominators, censoring rule. |
| 4.4 | `results.md` | Edit in place | Restructure as the v2 template: timeline + per-cell tables + judgment; retain v1 results as an appendix/supporting record with the caveats. |
| 4.5 | `thesis_overview.md` | Edit in place | §8: cite Schroeder et al. (2006) for the open-loop requirement; note the RQ1 cross-campaign acknowledgment. §5: RQ2 final protocol implemented. |
| 4.6 | `thesis_structure.md` | Edit in place | §5.4: mark open-loop driver as implemented for RQ2. §7.3: update limitations (n=3, MWU descriptive/effect-size, driver fixed, action cost measured). |
| 4.7 | `tese/references.bib` | Edit in place | Add `Schroeder2006OpenVersusClosed` (USENIX NSDI 2006). NSDI is USENIX-published and the ACM-legacy DOI prefix (10.5555/…) is **not reliably resolvable** — add the entry manually from DBLP and verify the URL; only fall back to `tools/add_bib_from_doi.py` if a resolvable DOI is confirmed. |
| 4.8 | `docs/research_questions/v2/rq2/rq2_preparation.md` | Edit in place | Record the `BOTTLENECK_STRICT_SINGLE` knob and the sticky-commitment gate behavior (the parent implementation-plan doc must stay in sync with the new controller behavior). |

### Phase 5 — Campaign execution (cloud VM, via Edge Experiment Runner)

**Goal**: run and analyze the 40-run campaign; produce final graphs + stats.

1. **Pre-flight (hard gates, fail-fast)**: (a) `make driver_selftest` on the
   VM (host + inside a netns); (b) **concurrency stress check** — max in-flight
   at the intended rate and 300 s cap must not exhaust container/conntrack
   connection limits (tune limits if it does; if infeasible, lower the window
   or rate and re-record the concurrency budget in §2.11); (c) 2 G2 calibration
   runs (`ba_cb`, `ba_db`) under open-loop to re-tune episode rates (target
   ≤ 3 req/s/client so `window/rate > 300 s`); (d) legacy `sync`-mode
   regression smoke. **Blocks do not start until all pass.**
2. **Main campaign**: 6 cells × 3 replicates, 3 counterbalanced blocks (block
   seeds 2001–2003, orders verified distinct, `counterbalance_order_v2.csv`).
   18 runs × ~30–35 min (incl. 4 drains of 30 s + setup) ≈ 9–11 h ≈
   **1 VM-day of blocks**.
3. **Per-run analysis**: bottleneck validation, decision analysis, relief
   (+flatten), sync-cost, node-minutes, spawn metrics, latency/timeout.
4. **Cross-cell**: updated comparison graphs (per-replicate scatter, medians,
   IQR, Cliff's delta on the effect-size hierarchy; MWU p reported
   descriptively); stats summary.
5. **Post-run**: `post_run_analysis.md` + `results.md` v2 judgment; archive
   raw run folders on the VM; retain graphs + analysis locally.

**Phase-5 gates:** all runs exit 0, correct env knobs, driver-mode=open_loop +
`INFLIGHT_WINDOW`/`DRAIN_S` confirmed in every env snapshot, 0×
`NotPrimaryOrSecondary`, no controller restart; the driver self-check is
enforced **per run** (fail-fast inside `run_traffic()`, in addition to the
pre-flight run); per-run checkpoints are the existing ones (fresh
window seq + decision log contains only this run's rows); stats computed on all
effect-size comparisons with missing-value exclusions recorded.

---

## 5. Dependencies

- **Phase 1 before Phases 3/5**: `make driver_selftest` must pass; legacy sync
  mode regression-clean; consumer audit complete.
- **Controller code** is volume-mounted → no image rebuild for Phase 3.
  **Edge server image is untouched** (driver is host-side).
- **Env files** (`env/*.env`, incl. `rq2_bottleneck_aware_strict.env`) synced
  to the VM (`~/rq2_env/`) before Phase 5.
- **aiohttp** must be available in the VM Python env for `open_loop` mode
  (add to the VM env if absent; verify import in pre-flight step 1a).
- **Concurrency budget** verified in pre-flight step 1b before calibration.
- Phase 4 docs edits can proceed in parallel with Phase 1–3 code work but must
  be complete before Phase 5.

## 6. Documentation updates (summary)

`experiment_plan.md`, `run_matrix.md`, `analysis_focus.md`, `results.md`
(all in `docs/operation/testing/experiment/v2/rq2/`), `thesis_overview.md`,
`thesis_structure.md`, `tese/references.bib`, plus the new plan doc itself
(this file).

## 7. Out of scope (explicit)

- Tier 1 selective sync / persistent reserves / cross-region placement remain
  disabled (thesis §2).
- Control-plane distribution across the WAN (data-plane only).
- RQ1/RQ3 campaigns: the open-loop driver is *built* here for them but their
  re-runs are separate efforts.
- Real multi-region testbed: emulation stays the primary design (per
  `global_literature_review.md` §11.5).

## 8. Review changelog (2026-08-04)

**Round 1** (Reviewer, deepseek-v4-flash, `--to-be-implemented`) flagged 4 🔴 /
12 🟡 / 5 🔵. Resolutions applied in this revision:

- 🔴 ba-strict redefined as **sticky commitment** (was a no-op — verified
  against `policy_gate.py:select()`).
- 🔴 in-flight window/rate joint calibration (`window/rate > cap`), self-test
  assertion bounded to `L < window/rate`; `dropped` only beyond the cap.
- 🔴 per-netns split preserves `client_fraction` via supervisor-computed
  active mask + per-worker seed (`base + ns_index`).
- 🔴 drain policy (`DRAIN_S=60`, `canceled` class) + reconciled timeline.
- 🟡 pre-registered primary stats hierarchy; no censored value in MWU;
  missing-value exclusions; full consumer audit + row-value contract;
  `backend_id`/`source_port` preserved; canonical analyzer location; sync-cost
  collector added; launch/join + CSV-merge spec; Makefile/gate wiring;
  counterbalance distinct-order verification + `_v2.csv`; concurrency stress
  check; `scaling_policy.py` passthrough removed (gate reads config directly).
- 🔵 DOI fixed (manual DBLP entry); timeline reconciled; `rq2_preparation.md`
  added to doc list; gate wording fixed; per-worker seeding documented.

**Round 2** (re-review of changed portions) flagged 3 🟡 / 4 🔵; all resolved:

- 🟡 `dropped` unreachable in production (window/rate > cap) → stated as a
  design property; self-test split into Scenario A (preserve offered load,
  zero drops) and Scenario B (bounded overrides to exercise drop accounting).
- 🟡 aiohttp keep-alive defeats per-connection source-port semantics →
  `TCPConnector(force_close=True)` for fresh connections per request.
- 🟡 sticky commit could lock in a spurious fire → **confidence-qualified
  commit** (`STRICT_COMMIT_N` consecutive same-tier fires, or both-fired
  classification); no opposite-tier re-commit before release; wrong-first-
  commit added to the Phase-3 gate.
- 🔵 supervisor mask RNG decoupled from the per-client RNG (dedicated seeded
  RNG for mask sampling; documented improvement over v1 interleaving).
- 🔵 drain made sequential per phase boundary and `DRAIN_S` set to 30 s
  (< shortest phase, 60 s).
- 🔵 schema wording fixed (`status` = 14th/last column; consumers validated).
- 🔵 sync-cost `bytes applied` derivation specified (`bytesToCopy`/oplog
  deltas; `null` fallback).

**Round 3 (user scope decision, 2026-08-04):** campaign scoped to **18 runs**
(6 cells × 3 replicates, 3 blocks, seeds 2001–2003); `ba-strict` implemented
but **not run** (follow-up option); statistics are **effect-size at n=3** (no α
claims; MWU descriptive; Cliff's delta ≥ 0.6 + 3/3 direction consistency);
no-scale control arm declined; conclusions scoped to what this supports.
