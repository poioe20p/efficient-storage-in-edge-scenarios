# RQ2 Extension — No-Op Arm, Varying-Demand Campaign, and Provenance (Pre-Registration)

> **Date:** 2026-09-26 · **Status: DESIGN — PENDING APPROVAL.**
> This package is a **pre-registration**: objectives, questions, gates, verdict
> rules and execution order are fixed **before** any run. **No run has been
> launched.** Results will be recorded in [results.md](results.md); per-run
> configuration and provenance in [run_matrix.md](run_matrix.md).
>
> **Purpose.** Extend the completed RQ2 v3 campaign (tag
> `rq2-v3-campaign-20260808`; 6 cells × 6 replicates, 34 valid runs) with
> three parts: **(Part A)** a no-op (`fixed_none`) arm measuring the
> harm-vs-inaction contrast and the value floor of the right action;
> **(Part B)** a varying-demand (two-regime sequential) campaign measuring the
> value of one configuration under **regime uncertainty** (claim layer L4) and
> characterising regime-hand-off carryover; **(Part P)** a code/config
> provenance plan so that every extension run is provably *"v3 code +
> additive-only changes"*.
>
> **Parent evidence:** [`../v3/rq2/experiment_plan.md`](../v3/rq2/experiment_plan.md)
> (v3 campaign) · [`../v3/rq2/results.md`](../v3/rq2/results.md) ·
> [`../v3/rq2/sf_cb_rerun_plan.md`](../v3/rq2/sf_cb_rerun_plan.md) (decision-table
> style used here) · [`../v3/rq2/ba_db_2_incident.md`](../v3/rq2/ba_db_2_incident.md)
> (MEMCG OOM incident context for the carryover memory watch) ·
> [`../v3/rq2/run_matrix.md`](../v3/rq2/run_matrix.md) (matrix + hash conventions).
>
> **Gate floor:** [`../../testing_requirements.md`](../../testing_requirements.md)
> — B1/B2, M1/M2, V1, I1/I2, D1–D3, flags (F1/F2), reproducibility n ≥ 2, and
> the "numbers live in the plan" rule. Every threshold used below is either
> cited from v3 records or marked **plan-defined**; numbers not yet fixed are
> marked **[probe]** (probe-determined).
>
> **Consumer docs (updated only after results):**
> [`../../../../../tese/research_questions/rq2/rq2.md`](../../../../../tese/research_questions/rq2/rq2.md) ·
> [`../../../../../tese/research_questions/rq2/rq2_conclusions.md`](../../../../../tese/research_questions/rq2/rq2_conclusions.md)
> (claim shaping — no claim is made or changed by this plan).

---

## 1. Objectives and pre-registered questions

### 1.1 What the v3 campaign established (cited context — not re-litigated here)

| Finding | v3 record |
| --- | --- |
| **B1** compute scale-up benefit: **12/12** aligned compute-bound replicates; PRE p50 2.2–3.0 s → POST ~3.3 ms (ratio 0.001–0.025 vs the ≥2× threshold) | `rq2_conclusions.md` §2.1; v3 `results.md` |
| **Storage CPU relief reproduced**: peak storage-CPU ratio **0.57–0.66×** in **12/12** `sf_db` LANs (criterion <0.75×); ba_db 9/10 LANs | `rq2_conclusions.md` §2.2 |
| **B2 p95 cell-level gate NOT met** (`sf_db` median 0.727×, CI [0.574, 1.393]; `ba_db` 1.083×, CI [0.897, 13.968]); two documented causes: PRE/POST window-length tail asymmetry, ba post-relief compute churn | `rq2_conclusions.md` §3 |
| **Wrong-action costs**: `cf_db` (compute-first on data-bound) degrades service (episode p50 ~36–78 ms, p95 ~706–1135 ms vs aligned `sf_db` ~40–70 ms / ~502–756 ms); `sf_cb` (storage-first on compute-bound, corrected 0.15/0.08 rerun) shows **resource waste only** at the tested intensity (compute tier pinned ~61 % of the 0.15 cap in 93–97 % of windows with **0 COMPUTE adds** (v3 `sf_cb` rerun record); wasted storage activations) | `rq2_conclusions.md` §2.3 |
| **Classifier commits to the correct tier**: `ba_db` agreement 88–93 %; storage first, compute only after storage relief | `rq2_conclusions.md` §2.4 |
| **Platform**: 2/36 runs excluded as MEMCG OOM incidents (256 MB and 512 MB caps); `EDGE_MEMORY=512m` for campaign runs 15+ | `ba_db_2_incident.md`; `rq2_conclusions.md` §4 |

### 1.2 Claim layers (reframed structure this extension serves)

| Layer | Claim | Current status | Extension coverage |
| --- | --- | --- | --- |
| **L1** | **Consequence asymmetry** — a wrong action does not cost the same as the aligned action, and the two wrong actions cost differently (`cf` on db: service degraded; `sf` on cb: resource waste only) | established (v3) | **Q-A1**, **Q-A3** |
| **L2** | **No fixed policy is consequence-free across regimes** — each fixed arm has a regime where it loses | established (v3) | Q-A1 (inaction baseline), Part B cross-regime falsification |
| **L3** | **The selector matches the aligned arm per regime with bounded churn** | established (v3; agreement + documented churn) | Q-A3, **Q-B1** |
| **L4** | **Value under regime uncertainty** — one configuration across **sequential** regimes | **argued, not measured** | **Q-B1, Q-B2** (Part B is the measurement) |

> **Mapping note:** L1–L4 are working labels for the claim structure in
> [`tese/research_questions/rq2/rq2.md`](../../../../../tese/research_questions/rq2/rq2.md) §5
> and
> [`rq2_conclusions.md`](../../../../../tese/research_questions/rq2/rq2_conclusions.md) §5.

### 1.3 Pre-registered questions

| # | Question | Design | Claim layer | Verdict rule |
| --- | --- | --- | --- | --- |
| **Q-A1** | **Harm vs inaction**: how much worse is the wrong fixed action (`cf` on db) than doing nothing (`nn` on db)? | `cf_db` (v3 records) vs `nn_db` (new) — per-replicate episode p95, seed-42 | L1, L2 | §4.6 — "harm evidenced" / "neutral" / ambiguous |
| **Q-A2** | **Storage user-side between-arm baseline**: is the aligned storage action (`sf_db`) user-visibly better than inaction (`nn_db`)? (also reported vs `ba_db`) | `nn_db` (new) vs `sf_db` (v3 records; `ba_db` supporting) — per-replicate episode p95, seed-42 | L1, L2, L4 baseline | §4.6 — "user-visible storage benefit supported" / "not statistically supported at this n" |
| **Q-A3** | **Value floor of the right action**: how much does the aligned action recover over inaction on the compute axis? (descriptive) | `nn_cb` (new) vs `cf_cb` (v3 records) — p50 collapse magnitude | L1, L3 | §4.6 — descriptive |
| **Q-B1** | Can the selector (**one configuration**) recover **both** regimes in sequence — compute-bound then data-bound, and the reverse? | Part B shift cells (§5) | L4 | §5.9 decision table |
| **Q-B2** | What state carries across the regime hand-off, and does it bound the observable benefit? | Part B carryover checks (§5.8) + Stage-0 probe P3 | L4 (support/robustness) | §5.8 / reported per item |

**Standing rules:** pre-registration tense throughout ("will", "is expected");
probes are **not** evidence (Stage-0 probe results are recorded in
[results.md](results.md) as probe record only); a no-benefit arm is judged
against its own claimed direction (`testing_requirements.md`, B section).

**Plan-defined thresholds (consolidated):** This list is the canonical
location for plan-defined thresholds; point-of-use text states the value
without needing to repeat the tag. Q-A1 harm ratio **≥ 1.2**; Q-A1 neutral
band **0.8–1.2**; support fraction **≥ 80 %** of available replicates; Q-A2
storage-benefit ratio **≤ 0.85**; `sf`-on-R1 falsification leg — POST/PRE p50
ratio **≤ 0.1**, or edge CPU drop **≥ 25 %** (the `sf`-on-R1
falsification-leg alternative); P1 timeout ceiling **< 10 %**; P1 edge-CPU
bind **≥ 75 %** of cap; P1 episode-window coverage **≥ 30 %**; P1-4
client-side drop threshold **< 10 %**; storage-relief ratio (R2 legs; the v3
carrying leg) **< 0.75**; run-health flag — episode timeout **> 50 %** ⇒
flagged collapsed-run review (reported, not an automatic gate failure; §4.5 /
§5.10). The list covers measurement/decision thresholds; replication-count
criteria (**≥ 2/3**, scaled to **≥ 4/6**) and action-count requirements
(**≥ 1 add / ≥ 1 teardown / ≥ 1 fired window**) are plan-defined as well and
are stated at their points of use.

---

## 2. Scope and exclusions

### 2.1 Simultaneous dual-bind episode — OUT OF SCOPE

A simultaneous dual-tier bind (both the compute and storage signals genuinely
saturated at once) is **not** part of this extension. Evidence for the
exclusion (v3 decision-log scan, 2026-09-26; capture committed as an artifact
before FREEZE-1 — §8 item 5): **both tiers fired in the same window in 23 of
10,044 scale-up windows (0.23 %)**; the `ba` arm saw only **3** such
windows, **all classified correctly (storage)**.

Rationale (fixed): sustained dual saturation requires episode engineering —
the v3 binds are **allocation-specific** (per-run caps; bindings are
workload-aspect specific), and forcing a sustained dual bind carries
conflation/balance/platform risks. It is not needed for L4 (one configuration
across **sequential** regimes), which Part B measures directly.

### 2.2 Other exclusions and restated scope

- **Cross-region** placement/scaling stays out of scope: `SS_ENABLED=0` and
  `CROSS_REGION_STORAGE_ENABLED=0` in all extension arms (unchanged from v3).
  Tier-1 selective sync stays disabled.
- **No new mechanism beyond the additive set** (§3.1). In particular: **no
  budget reset/refund** (none exists; none will be added — cross-phase budget
  depletion is a *measured* carryover item, §5.6), and **no mid-run cap
  switching** (allocation option Gamma is rejected, §5.3).
- **Same-LAN persistent-reserve path only** for storage scale-up; replica-sync
  **bandwidth is not metered** (v3 limitation, restated) — action cost proxies
  remain join time + node-minutes + transient CPU/latency.
- **B2 p95 measurement-contract caveat carries over**: the PRE/POST
  window-length tail asymmetry documented in `rq2_conclusions.md` §3.3 is a
  known property; Part B phase-level windows will be reported with the same
  discipline and the caveat named, not hidden.

---

## 3. Part P — Provenance plan (prerequisite, not the campaign)

### 3.1 Rule

Extension runs must be **"v3 code + additive-only changes"**, verified by diff
review; the three existing arms must behave **identically** (existing
`policy_gate.py` branches untouched). **Env identity (evidence):** the
shift-cell arm envs are **byte-identical to the v3-final COMMITTED state** —
md5-verified at FREEZE-1 ([run_matrix.md](run_matrix.md) §1); differences vs
the **per-replicate v3 launch records** are enumerated — the known instance
is the `EDGE_MEMORY=512m` campaign-era edit (present in the VM working tree,
**uncommitted as of 2026-09-26**; it is committed with the v3-final state,
§3.2) — and are carried as a **comparability caveat** (§4.6 cap-split note).

**The additive set (enumerated by path — nothing else may differ; item 5's
file list is completed at implementation time and recorded in
[run_matrix.md](run_matrix.md) §1):**

1. `source/sdn_controller/policy_gate.py` — **only** the `fixed_none`
   addition (`_VALID_MODES` entry + `select()` branch + docstring, §4.1);
   all existing branches unchanged.
2. `rq2_env/rq2_none.env` — new arm env, canonical launch location (§4.2);
   **no archive mirror** — it exists ONLY in the canonical `rq2_env/`.
3. `source/scripts/testing/phases_override/phases_rq2_varying_cbdb.json`
   and `phases_rq2_varying_dbcb.json` — the two varying phases files (§5.2).
4. `tools/run_rq2_campaign.py` — `CELLS` entries for `nn_cb`, `nn_db`, and
   the six shift cells; order-CSV support (§6; force-added, §3.2).
5. **Analyzer/dataset files** — `source/scripts/testing/analysis/rq2/`
   (analyzer/dataset generation + run-summary tooling, e.g.
   `rq2_bottleneck_aware_campaign.py`; §7), plus the **ratio-graph tool if
   extended** (§7). **The analysis-extension file list is completed at
   implementation time and recorded in [run_matrix.md](run_matrix.md) §1; the
   freeze diff adjudicates against that completed list.**
6. Order CSVs — `extension_order_v1a.csv` / `extension_order_v1b.csv` (this
   docs package; §6, [run_matrix.md](run_matrix.md) §4).
7. This docs package — everything under
   `docs/operation/testing/experiment/rq2_extension/` (this plan, run matrix,
   results).

**Diff criterion:** the diff `rq2-v3-final-20260926` ↔
`rq2-extension-draft-20260926` is **restricted to the enumerated paths**;
existing policy branches and the three arm envs are **unchanged**. The
restriction is **re-verified for `rq2-extension-final-<date>`** — probe
finalization edits only enumerated paths (the varying phases files; on a Beta
switch, the launcher's shift-cell caps).

### 3.2 Execution sequence (canonical — this single ordering governs §4–§6, [run_matrix.md](run_matrix.md) §5, and §9; all operations ON the VM `cloud-vm-rq2` — working copy of record; currently at tag `rq2-v3-campaign-20260808` with a dirty tree)

> **Invariant:** every git operation (branch, commit, tag, verify) happens on
> the **VM**; the local repo is a mirror that receives the VM state — never
> the reverse. The mirror is refreshed after each verify step (3 and 6).

1. **v3-final (after plan approval):** branch from tag
   `rq2-v3-campaign-20260808`; commit the pending campaign-era edits (v3
   docs amendments + the `EDGE_MEMORY=512m` env edits + the amended
   launcher) as the final v3 state; tag `rq2-v3-final-20260926`.
2. **Extension draft:** branch `rq2-extension`; apply the additive set
   (§3.1 — the Parts A/B implementation, §4–§7) and commit; tag
   `rq2-extension-draft-20260926`.
3. **Verify:** the diff between `rq2-v3-final-20260926` and
   `rq2-extension-draft-20260926` touches **only** the enumerated additive
   paths (§3.1 — existing policy branches and the three arm envs
   unchanged); record md5s (launcher, arm envs, phases, `policy_gate.py`) in
   [run_matrix.md](run_matrix.md) §1.
4. **FREEZE-1** — pre-probe hashes recorded: code / env / launcher / plan /
   order CSVs **as applicable** ([run_matrix.md](run_matrix.md) §1).
5. **Stage-0 probes P1–P3** (§5.4; [run_matrix.md](run_matrix.md) §2) — P1
   iterates `phases_rq2_varying_cbdb.json` **in place on the branch**; a
   Beta switch would change caps/episodes (§5.3).
6. **Probe-finalized commit:** commit the probe-determined artifacts on the
   branch; tag `rq2-extension-final-<date>`; verify md5s.
7. **FREEZE-2** — post-probe hashes recorded: the varying phases files,
   shift-cell caps, and order CSVs — **tied to `rq2-extension-final-<date>`**
   ([run_matrix.md](run_matrix.md) §1). **FREEZE-2 re-hashes EVERY artifact
   that probe finalization can modify — the varying phases files, the
   launcher (shift-cell caps change on the Beta path), and the order CSVs;
   the launcher's md5 recorded at FREEZE-1 is provisional and is superseded
   by the FREEZE-2 value (both kept).**
8. **Campaign launch** from the frozen (`rq2-extension-final-<date>`) state;
   record tag + md5s in [run_matrix.md](run_matrix.md).

**Probe-finalized state (fixed):** probe-determined values (the in-place P1
edits to `phases_rq2_varying_cbdb.json`; on a Beta switch, the changed caps
and both episode parameter sets) are committed and tagged
`rq2-extension-final-<date>` **before FREEZE-2**; the campaign runs from that
tag's state.

**Launcher version control (fixed):** `tools/` is gitignored (`.gitignore`
line 244), so the launcher is **force-added** with
`git add -f tools/run_rq2_campaign.py` — no `.gitignore` edit.

**Pre-tag verification (fixed):** before each tag, `git status --short` is
reviewed against the expected file set (the enumerated paths, §3.1);
unexpected entries are either committed intentionally (and recorded in the
tag message) or stashed; **the tag message lists the exact file set**.

> **Note (fixed):** the local `main` branch has moved on — it must **not** be
> used as the base for either branch.

---

## 4. Part A — no-op arm (`fixed_none`)

### 4.1 Code change (additive-only)

- `source/sdn_controller/policy_gate.py`:
  - add `"fixed_none"` to `_VALID_MODES`;
  - add a `select()` branch returning `()` (no actions) and update the mode
    docstring.
- **Criticality note (pre-registered):** the constructor falls back to
  `dual` on an unknown `SCALEUP_POLICY` — and `dual` **acts on every fired
  tier**. The `_VALID_MODES` addition and the `select()` branch must land
  together; a unit check (extending the existing policy-gate test
  conventions, e.g. `rq2v2_p3_01_policy_gate_strict_test.py` style) will
  assert `fixed_none ∈ _VALID_MODES` and `select() == ()` for
  fired/fired, fired/none, none/fired verdicts.
- Existing branches untouched; mediator budget API unused (no consumption).

### 4.2 Config — new arm env file

- `rq2_none.env` = clone of `rq2_compute_first.env` with
  `SCALEUP_POLICY=fixed_none` and an updated header comment. **No other knob
  changes.**

**Env-copy audit (2026-09-26) — canonical location.** Three candidate
locations exist for the rq2 arm envs:

| Location | Status | md5 (2026-09-26) |
| --- | --- | --- |
| `rq2_env/` (repo root) | **CANONICAL launch source** — v3 `run_matrix.md` §1; `OSKEN_ENV_OVERRIDE_FILE=../../rq2_env/<arm>.env` from `source/scripts` resolves here; tracked in git | `rq2_compute_first.env` `33CE4DF7…`, `rq2_storage_first.env` `C41BD38E…`, `rq2_bottleneck_aware.env` `AC54F77A…` |
| `docs/operation/testing/experiment/v3/rq2/env/` | byte-identical **archived mirror** (same md5s); v3 campaign provenance; **NOT tracked by git** — informational only (audit note below) | identical to the above |
| `source/scripts/testing/controller_env_overrides/rq2_*.env` | **STALE v2-era copies** — different md5s; `STORAGE_PERSISTENT_RESERVE_ENABLED=0`, caps 12/8; file header says "SUPERSEDED — DO NOT USE for RQ2 runs". **NOT authoritative — must not be used or cloned** | `rq2_compute_first.env` `C6F6AC05…`, etc. |

**Env-audit note (fixed):** The v3 mirror directory
(`docs/operation/testing/experiment/v3/rq2/env/`) is subject to `.gitignore`
(`env/` rule) and is **NOT tracked by git**; it is **informational only**.
The canonical launch source is repo-root `rq2_env/` (tracked), and the
per-run record is each run folder's `controller_env_snapshot.env`.

**Decision:** `rq2_none.env` will be created in **`rq2_env/`** — the ONE
canonical launch location (per the existing pattern). **No extension archive
mirror is created** (the extension package carries no `env/` directory; the
v3 `env/` mirror is informational only — see the audit note above). **No
copy will be added under `controller_env_overrides/`.**

### 4.3 Cells

| Cell | Arm env | Phases file | EDGE_CPUS | STORAGE_CPUS | Replicates / seeds | Run-id pattern |
| --- | --- | --- | --- | --- | --- | --- |
| `nn_cb` | `rq2_none.env` | `phases_rq2_compute_bound.json` | 0.15 | 0.08 | 6 (reps 1–5 seed 42; rep 6 seed 43) | `<ts>_rq2_nn_cb_<rep>` |
| `nn_db` | `rq2_none.env` | `phases_rq2_data_bound.json` | 1.20 | 0.15 | 6 (reps 1–5 seed 42; rep 6 seed 43) | `<ts>_rq2_nn_db_<rep>` |

Caps are identical to the corresponding v3 cells (`cf_cb`/`sf_cb`/`ba_cb` at
0.15/0.08; `cf_db`/`sf_db`/`ba_db` at 1.20/0.15).

**Phase-file note:** the files listed are the current references; if the §5.2
reconciliation orders extension-specific copies (including for `nn` cells),
those copies are used and recorded in [run_matrix.md](run_matrix.md) §1.

### 4.4 Semantics (pre-registered expectations)

- **No actions ever** — `select()` returns `()` for every window.
- The decision log still records the **fired flags** with
  `selected_action=none` (existing `_log_decision` path; no new logging
  mechanism).
- **Reserve untouched**; **no scale-down dynamics** (nothing dynamic is ever
  created).
- Budget counters stay at zero (no consumption).

### 4.5 Gates (plan-defined; per `testing_requirements.md`)

| Gate | Requirement for `nn_*` runs |
| --- | --- |
| **D1/D2/D3** | Hard: 0× `NotPrimary*`; no restart/crash; snapshots present |
| **I1** | **≥ 5000 completed requests per LAN** in the episode (same magnitude as v3 §6) |
| **I2** | Outcome classification honest (timeout a distinct class; consistent denominators) |
| **B1/B2** | Judged against the **claimed direction** ("no benefit expected, arm inert") — a pre-registered no-benefit run is a valid finding, not a failure (`testing_requirements.md`, B section) |
| **V1 (restated)** | The **G2 bottleneck-validation** (per-run artifact; definition below) must pass **AND** the intended tier's signal must **fire in ≥ 1 window** during the episode (fired flags are logged even with no action). If **EITHER** the G2 validation fails **OR** no window fires → the nn cell is **uninformative → rerun** (one-relaunch rule, §4.7) |
| **M1 (restated)** | Scoped to rows with `action_type=scale_up`: **zero with `action != none`**; **zero reserve activations** (evidence: action tables + decision log) |
| **M2** | **Vacuous — not waived.** M2 applies to **ADDED** nodes; the `nn` arm adds none (evidence: zero add rows) — the requirement is vacuous, not waived. Stated per `testing_requirements.md` "Relative criteria" |
| **Health flag (plan-defined)** | Episode timeout **> 50 %** ⇒ **flagged collapsed-run review** (reported, not an automatic gate failure) |

**G2 definition (fixed — as in v3):** the per-run v3 bottleneck-validation
artifact (`<run>_bottleneck_validation.txt`) — **per-LAN median tier signals
+ per-LAN verdicts**, with PASS = all verdicts PASS (the v3 criterion; v3
`sf_cb_rerun_plan.md` §7 tooling conventions) — extended to **per-segment
phase coverage** for shift runs (§7 item 8). The producing script is
**VM-side tooling** (v3 convention: not committed under `source/`); its path
is recorded at implementation ([run_matrix.md](run_matrix.md) §1).

### 4.6 Pre-registered verdict rules

**Window convention (stated once):** Part A metrics are **episode-window
aggregates** — the no-op arm has **no action anchor**, so the pinned PRE/POST
convention is **undefined** for it. The pinned PRE/POST windows are used
**only where an action anchor exists** (shift-cell legs, §5; and v3
cross-references). "Episode p95" = completed-request p95 over the episode
window per LAN, per replicate, seed-42 unless stated.

**Comparison machinery (fixed):** cell-level medians of the per-replicate
episode-window p95 (seed-42); **ratio = median(A) / median(B)**;
**per-replicate support = fraction of AVAILABLE seed-42 replicates** (Q-A1:
above the `nn_db` median; Q-A2: below it).

- **Q-A1 (harm vs inaction; `cf_db` vs `nn_db`)**: ratio =
  median(`cf_db`)/median(`nn_db`); support = fraction of available `cf_db`
  seed-42 replicates above the `nn_db` median.
  - **"Harm evidenced"** iff **ratio ≥ 1.2 AND support ≥ 80 %**.
  - **"Neutral"** iff **ratio within 0.8–1.2 AND support ≥ 80 %**.
  - Otherwise **ambiguous**.
  > *Operational note (flagged for approval; §8 item 2):* the v3 `cf_db`
> valid set is **`1, 2, 3, 4, 6`** (rep 5 excluded — v3 `run_matrix.md`);
> the seed-42 pool is **n = 4** ({1, 2, 3, 4}; rep 6 is seed 43). The
> support denominator is the **available** replicates (with n = 4, ≥ 80 %
> support means 4/4).
- **Q-A2 (storage user-side between-arm baseline; `nn_db` vs `sf_db`, `ba_db`
  supporting)**: ratio = median(`sf_db`)/median(`nn_db`); support = fraction
  of available `sf_db` seed-42 replicates **below** the `nn_db` median.
  - **"User-visible storage benefit supported"** iff **ratio ≤ 0.85 AND
    support ≥ 80 %**.
  - Else report as **"not statistically supported at this n"** — **no CI
    gate is added** by this extension.
- **Time-fraction secondary leg (Q-A1/Q-A2, alongside the aggregates):**
  per-30 s bucket over the episode — **fraction of buckets with served %
  ≥ 95 and timeout ≤ 5 %** (the `sf_cb` amendment convention).
- **Q-A3 (value floor; descriptive)**: per-replicate episode-window **p50**
  for `nn_cb` vs `cf_cb` (seed-42); report the values + the **median ratio
  `cf_cb`/`nn_cb`**; descriptive only (v3 within-cell reference: PRE→POST
  ratio 0.001–0.025).
- **Cap-split caveat (applies to Q-A1..Q-A3):** v3 runs 1–14 ran at
  `EDGE_MEMORY=256m`, runs 15+ at `512m`; **all extension runs are `512m`**.
  Every per-replicate comparison against v3 cells carries its **cap label**;
  where a pool spans caps (e.g. `cf_db` seed-42 {1,2,3,4}), the split is
  stated and the **512m subset is reported as a sensitivity** alongside the
  full pool.
- **Build-delta caveat (applies to Q-A1..Q-A3; Part A cross-era
  comparisons):** all extension runs use the probe-hardened edge build
  (bounded concurrency + memory hardening, `EDGE_MAX_CONCURRENCY=256` /
  1 MB stacks; `/service_pressure` TTL cache with ≤ 5 s staleness; image
  `30a2c88bc1ce`), while the v3 comparator runs predate these fixes. Every
  cross-era per-replicate comparison carries this **build label** alongside
  the cap label; the ≤ 5 s cache-staleness bound is a named contract
  difference of extension runs.

### 4.7 Execution order

**Stage A1 = `nn_cb` × 6 first** (CSV-1; the launcher is stopped after it,
§6), then a **checkpoint (analyze + gates)** before the rest. Checkpoint pass
= **six PASSING runs** clearing D1/D2/D3, I1 ≥ 5000/LAN, the M1 zero-action
criterion (**zero scale_up rows with `action != none`; zero reserve
activations**), and V1; then proceed to
`nn_db` per the order plan (§6). Checkpoint failure (actions observed ⇒ mode
broken) **halts** implementation work before the campaign continues.

**D2 incident handling (unified for Parts A and B):** any **exit-137 /
container crash = D2 hard-gate incident** → the run is **excluded +
documented in [results.md](results.md) + relaunched ONCE**. A **second
failure in the same cell halts that cell** and is reported — no further runs
until a user decision. Relaunches happen **before** the `nn_cb` checkpoint
clears. **No relaunch for pre-registered no-benefit outcomes — only for gate
failures.**

### 4.8 Analysis handling

- Analyzer `RUN_RE` extended to accept `nn` (and the Part B tokens, §7).
- `nn` cells appear in the latency / failure / node-minutes graphs.
- **B1/B2 windows are N/A for `nn`** — stated in the run summaries (not
  silently blank).
- Classifier/selected-action graphs include `nn` as the **all-none reference**
  (no classifier-agreement rows exist for `nn`; that panel stays cf/sf/ba).

---

## 5. Part B — varying-demand campaign

### 5.1 Goal

Measure **L4** — one configuration across **sequential** regimes — and
characterise carryover across the regime hand-off (**Q-B2**). Runs combine a
retuned compute-bound episode and the exact v3 data-bound episode in one run,
in both orders.

### 5.2 Run shape and phase files

Per run: `baseline(60 s) → episode1 → recovery_gap(G) → episode2 →
demand_drop` (the FINAL phase is `demand_drop`, for
bidirectional-elasticity/scale-down measurement). Two order files, both new,
under `source/scripts/testing/phases_override/`, following the existing
schema (`name` / `duration_s` / `rate_per_client` / `client_fraction` /
`mix` / `cross_region_ratio` / `hotspot_direction` — the latter optional and
blank in these files, as in the v3 rq2 files):

| # | Phase (both files keep these NAMES) | cbdb file | dbcb file | Values | Source |
| --- | --- | --- | --- | --- | --- |
| 1 | `baseline` | ✓ | ✓ | 60 s, rate 1.0, cf 0.1, standard mix | **plan-defined** (cb convention) |
| 2/4 | `compute_bound_episode` | position 2 | position 4 | 600 s [plan-defined]; **1200 s [probe] if P1-4 is the passing probe point** (§5.4), rate **[probe]** (Alpha candidate sweep 6/9/12), cf 1.0, mix `service_pressure 1.0` | **retuned** for Alpha — exact values frozen by P1 |
| 3 | `recovery_gap` | ✓ | ✓ | **G = max(120 s, replenish_p95 + 60 s) [probe]** (fixed by P2, §5.4), rate 0.5, cf 0.05, standard mix | **plan-defined / [probe]** |
| 2/4 | `data_bound_episode` | position 4 | position 2 | 480 s, rate 5.0, cf 1.0, mix `content_lookup 0.9 / feed_ranking 0.1` | **EXACT v3 db episode parameters** (Alpha) |
| 5 | `demand_drop` | ✓ | ✓ | 420 s, rate 1.0, cf 0.1, standard mix | **plan-defined** (v3 compute-side convention — §8 item 4 settled) |

Canonical phase **names are kept** (`compute_bound_episode` /
`data_bound_episode`) so existing pipelines key on them; the analyzer gains
per-segment handling (§7). `phases_rq2_varying_cbdb.json` = compute first;
`phases_rq2_varying_dbcb.json` = data-bound first. **"Standard mix"** =
`content_lookup 0.6 / feed_ranking 0.25 / service_pressure 0.15` (the v3
baseline/recovery/demand_drop mix).

**Canonical-files rule (explicit exception, fixed):** the canonical
`source/scripts/testing/phases.json` is **untouched**; the two varying files
are **regime-override files** under `phases_override/` — the established v3
mechanism for named configuration regimes (the config-axis exception to the
one-canonical-phases rule) — and this is **intentional**.

**Phase-drift reconciliation (freeze item):** before freeze, **both the
varying files AND the base cb/db files** (`phases_rq2_compute_bound.json` /
`phases_rq2_data_bound.json`) are diffed against the v3 per-run
`phases_snapshot.json`; the **frozen parameter set = the AS-RUN snapshot
values** (never from possibly-drifted current files). If the current files
drift materially, **extension-specific copies are built from the snapshot
values** (new `phases_override/` files for the extension — **including for
the `nn` cells**, which otherwise reuse the base cb/db files); the v3 base
files are **never mutated**. The diff summary is recorded in
[run_matrix.md](run_matrix.md) §1.

### 5.3 Allocation problem and decision rule (pre-registered)

**Problem statement (plainly):** v3 binds are **allocation-specific** — the cb
cells bind at edge 0.15 / storage 0.08; the db cells bind at edge 1.20 /
storage 0.15 — and **caps are per-run, not per phase**. A **single allocation**
per run must therefore make **each regime's intended tier bind** (whichever
phase position the regime occupies — §5.7 mapping).

| Option | Allocation | R1 (`compute_bound_episode`) treatment | R2 (`data_bound_episode`) treatment | Verdict |
| --- | --- | --- | --- | --- |
| **ALPHA (RECOMMENDED)** | shared allocation = **db-cell caps** (edge 1.20 / storage 0.15) | **retuned** compute-heavy episode that saturates edge 1.20 with storage quiet (candidate sweep: `mix.service_pressure 1.0` at rate **6/9/12** — [probe]) | **EXACT v3 db episode parameters** | preferred |
| **BETA (fallback)** | **mid** allocation (~edge 0.6 / storage 0.15) | **retuned up** ([probe]) | **retuned down** to keep compute quiet at the lower edge cap ([probe]) | only if Alpha fails |
| **GAMMA** | mid-run cap switching | — | — | **REJECTED** — a new mechanism; confound |

**Decision rule (fixed):** attempt **Alpha first** (probe budget **≤ 4 runs**);
if no rate point passes P1 (§5.4), **switch to Beta** and record the switch in
the probe record ([results.md](results.md)). Beta re-anchors **both** phases
at probe time; its cross-config comparability limits will then be restated in
the probe record.

**Alpha comparability limit (pre-registered):** Alpha's phase-1 episode is
**not** the v3 cb episode (rate 1.5 @ edge 0.15) — the expected signature is
B1-style (compute binds; p50 collapse after adds), **not** numeric equality
with the v3 cb cells.

### 5.4 Stage-0 probes (pre-registered; run BEFORE any campaign run; probes are NOT evidence)

| Probe | Question | Acceptance / output | Budget |
| --- | --- | --- | --- |
| **P1** | Alpha phase-1 feasibility: can a retuned compute-heavy episode bind at edge 1.20 with storage quiet? | Accept **iff ALL of**: **(a)** the compute signal fires during the episode (decision log); **(b)** edge CPU ≥ 75 % of the cap in **≥ 30 % of episode windows** — **plan-defined** probe criterion (list §1.3); **(c)** storage quiet (below threshold; **zero storage fires**); **(d)** **I1 ≥ 5000 completed/LAN** in the episode; **(e)** **timeout < 10 %**; **(f)** D-gates pass. Sweep rate points in order; **stop at first pass** | ≤ 4 runs |
| **P1-4 (contingency)** | If 6/9/12 all fail: ONE confirmatory attempt at the **highest feasible rate** — defined as the highest rate the harness sustained **without client-side saturation (client drops < 10 %)**, recorded in the probe record — with the R1 episode **doubled to 1200 s [probe]** (bind-time check) | Accept iff (a)–(f) hold; if it still fails → **declare Alpha infeasible, switch to Beta**, record. **If P1-4 passes: campaign R1 duration = 1200 s [probe]** (§5.2) | within P1 ≤ 4 |
| **P2** | Reserve replenishment timing (needed for the **db→cb** order, where phase 1 activates the reserve) | Derive `replenish` = (next READY time − activation time) from v3 db-cell records → **G = max(120 s, replenish_p95 + 60 s)**; **if underivable from records → one dedicated probe** (dbcb shape, `sf` arm); if scale-down settle exceeds G → **increase G** (record the measurement) | ≤ 1 run |
| **P3** | State inventory across the phase boundary | Code read (carried-state table below, 2026-09-26 — **6 items**; strict-commit verified NOT engaged, excluded) **+ probe check** on a boundary-crossing run (the P1-pass run and/or ≤ 1 dedicated probe). Output: the carried-state table **verified**; unverifiable items recorded as limitations | ≤ 1 run |

**P1 launch configuration (fixed).** Arm: `rq2_none.env` — passive
observation, no actions by construction (also **pre-exercises the Part A
arm**). Phases: `phases_rq2_varying_cbdb.json`, **iterated IN PLACE** for the
rate sweep (each probe run snapshots phases + env into its run folder, as any
run). **Probe-finalized note:** the in-place edits are committed on the
`rq2-extension` branch and tagged `rq2-extension-final-<date>` before
FREEZE-2 (§3.2 steps 6–7) — a Beta switch changes caps/episodes (§5.3).
Launch: a **direct `make` chain** on the VM (documented command
pattern), **NOT** via the campaign launcher — **no `CELLS` entries** for
probes. Labels: `rq2_ext_p1_r6` / `rq2_ext_p1_r9` / `rq2_ext_p1_r12`
(+ contingency). Probe run folders are stored in `metrics/`, following the v3
preflight pattern.

**Carried-state table (code-read 2026-09-26; 6 items — §5.8's recorded list
is aligned to these; column "verified by P3" filled at probe time):**

| State | Where | Reset behaviour (code-read) | Pre-registered carryover check | Verified by P3 |
| --- | --- | --- | --- | --- |
| **Action budget** (`PolicyGate._used`) | `policy_gate.py` | Cumulative per tier per controller (per LAN); **NO reset/refund API exists** (only `budget_available` / `consume_budget`) — **DOCUMENT, do not add a reset mechanism** | Decision-log `*_budget_used` recorded at **BOTH phase starts** and first phase-2 action rows; depletion expectations per §5.6 (both orders) | ⬜ |
| **Adaptive compute threshold** | `scaling_policy.py` `evaluate_compute_scale_up` | `base 0.18 + dyn_compute × 0.10` (cap 0.85) — follows the **current** dynamic-node count (run-level) ⇒ stays elevated while phase-1 adds remain in service | Record `τ_eff` at phase-2 first fire + number of phase-1 adds still present | ⬜ |
| **Adaptive storage threshold** | `scaling_policy.py` `evaluate_storage_scale_up` | geometric-halving increment per dynamic storage node (floor 0.05; cap 0.55) — same carry logic | Same, storage side | ⬜ |
| **Scale-up cooldowns** | `scaling_policy.py` | **Time-based** (compute 45 s, storage 120 s); wall-clock — **not cleared by a phase boundary**; reserve activation **resets the storage cooldown + scale-down window** (cross-direction reset) | Earliest phase-2 fire vs phase-2 start + residual cooldown; reserve-activation timestamp in the db-first order | ⬜ |
| **Reserve state** (READY / activated / replenishing) | mediator/registry; `main_n1/n2` | Run-level machine; activation consumes storage budget; replenishment creates a new READY standby | cb→db: expect **READY/untouched** at phase-2 start (zero phase-1 storage adds); db→cb: record status + replenishment completion (this is the P2 anchor) | ⬜ |
| **Dynamic pool composition** (phase-1 adds still in service) | mediator/registry pool state (`main_n1/n2`) | Run-level; adds persist until scale-down (no teardown at a phase boundary) | Phase-1 adds still present at phase-2 start (measured; §5.8 item 2) | ⬜ |

**Strict-commit status — NOT ENGAGED (verified 2026-09-26, fact):**
`BOTTLENECK_STRICT_SINGLE` defaults to `0` and no arm `.env` sets it ⇒ the
strict-commit state (`_committed`, streaks) is **never engaged** in this
campaign configuration; it is excluded from the carried-state set (six
items).

### 5.5 Cells

| Cell | Arm env (byte-identical to the v3-final committed state — §3.1) | Phases file | Caps | Stage-1 replicates |
| --- | --- | --- | --- | --- |
| `cf_shcbdb` / `cf_shdbcb` | `rq2_compute_first.env` | `phases_rq2_varying_cbdb.json` / `..._dbcb.json` | Alpha: 1.20 / 0.15 [probe] | 3 (seed 42) |
| `sf_shcbdb` / `sf_shdbcb` | `rq2_storage_first.env` | as above | as above | 3 (seed 42) |
| `ba_shcbdb` / `ba_shdbcb` | `rq2_bottleneck_aware.env` | as above | as above | 3 (seed 42) |

Run-id pattern: `<ts>_rq2_<arm>_shcbdb_<rep>` / `<ts>_rq2_<arm>_shdbcb_<rep>`
(rep 1–3). **Extendable to 5+1** (`_4`,`_5` seed 42; `_6` seed 43) after the
Stage-1 analysis if needed (separate order file; decision recorded in
[results.md](results.md); the replicate criterion then scales — §5.9
quantification).

### 5.6 Budget decision (fixed)

- **KEEP** the canonical `ACTION_BUDGET_PER_TIER=4` **cumulative** (no new
  mechanism; zero config divergence).
- Cross-phase budget depletion is a **measured carryover item**.
  **Pre-registered expectations (both orders):**
  - **cb→db:** phase-1 compute adds are likely to spend the **compute**
    budget (`cf` and `ba`) ⇒ phase-2 compute adds **may be budget-blocked**
    (expected, not a failure); the **storage budget is fresh**.
  - **db→cb:** phase-1 storage activations spend the **storage** budget
    (`sf`, `ba`) ⇒ phase-2 storage actions **may be blocked** — expected and
    non-blocking, because phase 2 is compute-bound and storage action is not
    needed. **Additionally, phase 1 (R2) can spend the COMPUTE budget** (v3
    reference: `cf_db` scaled compute — **6 actions**; `ba` churn adds on
    top) ⇒ **`cf`/`ba` may be budget-blocked in their aligned R1 phase 2**;
    pre-registered as expected, with the interpretation limit that the **R1
    legs for `cf`/`ba` in db→cb are budget-limited by design**.
  - **Budget counters are recorded at BOTH phase starts** (carryover
    evidence, §5.8).
- **Interpretation limit (pre-registered):** a budget-blocked phase-2 action
  is a measured property of the single-configuration design (the budget is
  part of the configuration); it is reported with the blocked-row evidence
  and bounds L4's interpretation, not hidden.

### 5.7 Pre-registered expectations (per REGIME, not per phase position)

**Regime vocabulary (fixed):**

- **R1 = `compute_bound_episode`** — the compute-bound regime.
- **R2 = `data_bound_episode`** — the data-bound regime.
- **Mapping (fixed):** for `*_shcbdb` cells, phase 1 = **R1**, phase 2 =
  **R2**; for `*_shdbcb` cells, phase 1 = **R2**, phase 2 = **R1**.
  Segments are identified by **phase NAME occurrence**, never by position
  number.

| Arm | R1 — compute-bound regime | R2 — data-bound regime |
| --- | --- | --- |
| `cf` | **Scales compute** — **B1-style p50 collapse** expected after compute adds | **No storage relief** (storage suppressed); service degradation per v3 `cf_db`; budget note per order (§5.6) |
| `sf` | **No relief** — compute stays pressured; storage use is **resource waste only** (v3 `sf_cb` rerun resource-side framing) | **Storage CPU relief ratio < 0.75** (the v3 carrying leg; `rq2_conclusions.md` §2.2); reserve activated |
| `ba` | **Scales compute** — same B1-style collapse expected as `cf` | **Storage first** (classifier), storage CPU relief ratio < 0.75; optional post-relief **compute churn** (budget-dependent; the v3 churn observation is the reference) |

Mismatched-regime failure directions (for §5.9): `cf` in **R2** shows no
storage relief; `sf` in **R1** shows no compute relief (resource-waste
framing only, per v3). Both are quantified at **≥ 2/3 replicates** (§5.9).

### 5.8 Carryover checks (per order — pre-registered)

1. **Reserve** READY at phase-2 start (cb→db: expect ready/untouched; db→cb:
   record replenishment status).
2. **Pool composition** at phase-2 start (phase-1 adds torn down during G? —
   **measure**).
3. **Budget counters** recorded at **BOTH phase starts** (§5.6).
4. **Adaptive-threshold state** at phase-2 start.
5. **Memory watch** — phase 2 follows phase-1 churn; cap **512m**; **any
   exit-137 / container crash = D2 incident → unified rule (§4.7):
   exclude + document + ONE relaunch; second failure halts the cell**
   (per `ba_db_2_incident.md` conventions; both orders).
6. **Cooldown state** at phase-2 start.

All **six** checks are recorded per shift run in the run summaries (§7);
the carried-state table in §5.4 is aligned to this set (its two
adaptive-threshold rows are recorded here as one item; the memory watch is
the additional platform check). **Strict-commit is not part of the set** —
verified not engaged in this configuration (§5.4).

### 5.9 Success criteria and decision table (L4)

**L4 confirmed** iff: `ba` recovers **BOTH regimes** (R1: B1-style collapse;
R2: storage relief ratio < 0.75) — **each regime leg at ≥ 2/3 replicates in
the same direction** — **AND** `cf`/`sf` fail their **mismatched regimes**
per the claimed direction (**each mismatch failure at ≥ 2/3 replicates**)
**AND** no carryover penalty beyond the documented bounds (§5.8). Regime
mapping as §5.7: `*_shcbdb` cells phase 1 = R1, phase 2 = R2; `*_shdbcb`
cells phase 1 = R2, phase 2 = R1; segments by **phase NAME occurrence**.

| Outcome | `ba` result | Fixed-arm result | Carryover | Verdict |
| --- | --- | --- | --- | --- |
| ✅ **Confirmed** | Both regimes recovered (R1 + R2) | `cf`/`sf` fail their mismatched regime per claimed direction | Within documented bounds | L4 supported — one configuration recovered both sequential regimes |
| ❌ **Falsified** | Does **not** recover a regime | **or** a fixed arm **recovers** its mismatched regime (operationalization below; structurally unreachable for the fixed arms — retained for completeness) | any | L4 not supported as stated |
| ⚠️ **Ambiguous** | anything else | — | — | e.g. one regime recovered, mixed direction, or an unlisted carryover effect |

**Operational definitions (plan-defined; keyed to REGIME):**

- **"B1-style collapse" (R1, either phase position)**: PRE→POST p50 drop
  ≥ 2× per the v3 B1 threshold (`../v3/rq2/experiment_plan.md` §6).
- **R1 PRE/POST anchor (plan-defined):** PRE = episode start → the **first
  compute `node_add`** event; POST = **first compute `node_ready` + 120 s**
  → episode end (ready source = harness ready log; **fallback = add + 40 s**,
  the v3 fallback convention).
- **"Storage relief ratio < 0.75" (R2, either phase position)**: post-window
  peak storage CPU / pre-window peak storage CPU — the v3 B2 CPU leg
  criterion (<0.75×), the carrying leg for storage (`rq2_conclusions.md`
  §2.2/§3.1). The v3 B2 **p95 leg is reported but NOT re-used as a success
  leg** (its measurement-contract asymmetry is documented; §2.2).
- **"Fixed arm recovers its mismatched regime" (falsification leg —
  operationalized, plan-defined):** `sf` on R1 = **compute relief observed**
  — edge CPU drop **≥ 25 %** within the episode **OR** POST/PRE p50 ratio
  **≤ 0.1**; `cf` on R2 = **storage CPU relief ratio < 0.75** (the carrying
  leg). *Note:* for the fixed arms this branch is **structurally
  unreachable** (no cross-tier action path — `sf` cannot act on compute,
  `cf` cannot act on storage) and is retained for completeness; the **live
  falsification risk is the `ba` legs.**
- **"Within documented bounds"**: every crossed **regime** still shows its
  claimed-direction outcome, and any budget-blocked action is the
  pre-registered depletion expectation (§5.6). An unlisted carryover item
  that blocks a claimed-direction outcome is **beyond bounds**.
- **Quantification (fixed):** every leg requires **≥ 2/3 replicates in the
  same direction** — both `ba` regime legs and each fixed-arm mismatch
  failure. **Stage-2 scaling:** if a leg is extended to the 5+1 replicate set
  (`_4`,`_5` seed 42; `_6` seed 43 — §5.5), the ≥ 2/3 rule becomes **≥ 4/6**.
- A phase failure caused by a **D2 incident** excludes the run (not a
  policy verdict) — unified rule §4.7 (exclude + document + ONE relaunch;
  second failure halts the cell). A phase failure caused by policy/carryover
  counts for the table with its cause reported.

### 5.10 Shift-cell gates & rerun rules

| Gate | Shift-run requirement |
| --- | --- |
| **D1/D2/D3** | **Hard** — 0× `NotPrimary*`; no restart/crash; snapshots present. Any exit-137 / container crash = D2 incident (unified rule, §4.7) |
| **D4 (fd scan — added 2026-09-27)** | **Edge fd-exhaustion scan** (accepted, user 2026-09-27): scan both `service_logs/edge_server_n{1,2}.log` for `Too many open files`; cross-check per-phase per-lane service health. A service-breaking EMFILE burst / lane blackout = incident (unified rule: exclude + document + ONE relaunch) |
| **I1** | **≥ 5000 completed requests per LAN per episode phase** (each regime segment) |
| **I2** | Outcome classification honest (timeout a distinct class; consistent denominators) |
| **M1** | Per **claimed tier per phase** (claimed-direction arms only): `cf`/`ba` in R1 → **≥ 1 compute add** during the R1 phase, per LAN; `sf`/`ba` in R2 → **≥ 1 storage activation** during the R2 phase, per LAN (**reserve activation counts** as the storage scale-up action — v3 mechanism); arms in their **mismatched regime** (`cf` in R2; `sf` in R1) → **M1 exempt** (no-benefit pre-registration). Elasticity clause: the final `demand_drop` must show **≥ 1 teardown for each tier that scaled up** (where applicable) |
| **M2** | Per **added node** — each added node serves ≥ 1 request (`testing_requirements.md` relative criteria) |
| **V1** | Per **phase** — per-segment **G2** bottleneck validation passes (v3 artifact; §4.5 note; §7 item 8) |
| **B1/B2** | Judged **per claimed direction**, with a pre-registered **no-benefit exemption** for the mismatched regimes (`cf` on R2; `sf` on R1): a no-benefit outcome there is a valid finding, not a failure (`testing_requirements.md`, B section) |
| **F1/F2** | **Flags** — reported, not gate failures; **health flag (plan-defined): episode timeout > 50 % ⇒ flagged collapsed-run review** |

**M1/elasticity note (plan-defined):** the 420 s `demand_drop` window is
sized so the teardown gate (≥ 1 teardown per scaled tier) is observable,
matching the v3 compute convention.

**Rerun rule (fixed):** a gate-tripped shift run is **excluded + documented
in [results.md](results.md) + relaunched ONCE**. A **second failure in the
same cell halts the cell** — no further runs until a user decision (mirrors
the unified D2 rule, §4.7). No relaunch for pre-registered no-benefit
outcomes — only for gate failures.

---

## 6. Run matrix and order plan (pointer)

Full per-run detail lives in [run_matrix.md](run_matrix.md): provenance block,
Stage-0 probe table, campaign-cell table, and the extension order-CSV plan.

**Order summary (fixed):** **two order CSVs** — **CSV-1** = Stage A1
(`nn_cb` × 6); the launcher is **stopped** after CSV-1 and the Stage-A1
checkpoint is executed (**mirrors the `sf_cb` 1-row CSV practice**);
**CSV-2** = the remaining 24 runs, launched only after the checkpoint
passes. CSV-2 is a **blocked round-robin**: `nn_db` + the six shift cells,
one replicate per cell per block × 3 blocks, then `nn_db` reps 4–6 (seeds
42, 42, 43). Seeds: reps `_1.._5` = 42, `_6` = 43 everywhere. Stage 2
(shift cells 5+1) is contingent on the Stage-1 analysis.

---

## 7. Analysis and reporting extensions (required work items)

1. **RUN_RE** in `source/scripts/testing/analysis/rq2/rq2_bottleneck_aware_campaign.py`
   extended for tokens **`nn`** and **`shcbdb`/`shdbcb`** (exact regex at
   implementation; old tokens must keep matching — no regression on the v3
   dataset).
2. **Dataset generation must segment TWO episode windows per shift run**, by
   **phase occurrence** — segments identified by **phase NAME occurrence**
   (R1 = `compute_bound_episode`, R2 = `data_bound_episode`), never by
   position number — with new per-segment columns (segment index + phase
   name); the segment index distinguishes the two occurrences of a name.
3. **Run summaries gain per-phase sections** (pre/post windows per episode
   segment; carryover fields, §5.8).
4. **`nn` N/A handling**: B1/B2 windows blank with an explicit N/A flag;
   zero-action evidence captured as the M1 criterion (among
   `action_type=scale_up` rows: zero with `action != none`; zero reserve
   activations).
5. **Classifier/selected-action graphs gain the `nn` all-none reference**
   (agreement panel unchanged).
6. **New per-phase recovery graph** for shift cells (per-phase treatment
   trajectory).
7. Dataset rebuild + graph regeneration smoke-tested on a **copy** of the v3
   dataset (old-token regression check) before any new run is analyzed.
8. **Per-segment G2 bottleneck validation** — the v3 G2 artifact (§4.5 note)
   extended to **per-phase segments** for shift runs, and applied to the
   `nn` cells (single episode each).

---

## 8. Risks and open items

| # | Item | Type | Handling |
| --- | --- | --- | --- |
| 1 | **Alpha feasibility** (retuned phase 1 may not bind at edge 1.20) | risk | P1 sweep; Beta fallback pre-registered (§5.3) |
| 2 | **Q-A1 denominator** — v3 `cf_db` valid = **1, 2, 3, 4, 6** (rep 5 excluded — v3 `run_matrix.md`); seed-42 pool **n = 4** | interpretation (flagged) | Support fraction is defined over **AVAILABLE** replicates (§4.6); with n = 4, ≥ 80 % support means **4/4** — recorded, not silently changed |
| 3 | **Q-A2 wording** — previously admitted two readings | interpretation (flagged) | Operationalized in §4.6: ratio-of-medians **AND** support ≥ 80 % of available replicates; both reported |
| 4 | **`baseline` 60 s / `demand_drop` 420 s durations** are plan-defined (v3 cb uses 60/420, db 30/360); one uniform choice per run — **settled at `demand_drop` = 420 s [v3 compute-side convention]** | plan-defined | **Decision recorded — no longer open**; changeable only **before FREEZE-1** ([run_matrix.md](run_matrix.md) §1) |
| 5 | **Both-fired scan provenance** — the 23/10,044 figures come from a VM-side scan (2026-09-26) not yet committed | provenance | Committed as an artifact (small CSV or recorded block in [results.md](results.md)) **before FREEZE-1** ([run_matrix.md](run_matrix.md) §5) |
| 6 | **Git topology** — all git operations happen **on the VM** (working copy of record); the local repo is a mirror | provenance | Invariant (§3.2): the local mirror is updated **from** the VM (`git bundle`/push); both ends carry identical tags/branches; the VM verifies `git describe` + md5s pre-launch |
| 7 | **MEMCG OOM recurrence** under phase-1 churn (phase 2 follows churn; 2 v3 incidents at 256 MB/512 MB) | platform | 512m cap; exit-137 / container crash = D2 ⇒ unified rule: exclude + document + ONE relaunch; second failure halts the cell (§4.7). **Materialized 2026-09-27 (B-P2r R1): both edges OOM-killed — thread explosion under the post-churn high-rate episode; dbcb R1 2/2 failed; campaign gate**; **resolved by fix1 (gate) + fix2 (cache — jam removed) + fix3 (memory hardening: thread cap 256 + 1 MB stacks; verification `rq2_ext_b_dbcb_fix3` — final planned fix cycle, time-boxed)** |
| 8 | **Budget depletion** may suppress `cf`'s phase-2 activity | design | Measured carryover item + pre-registered interpretation limit (§5.6) |
| 9 | **Tail asymmetry** (v3 §3.3) will re-appear in phase-level windows | measurement | Report with the caveat named (§2.2) |
| 10 | **Beta fallback loses the exact-v3 phase anchor** for phase 2 | comparability | Re-anchor statements in the probe record at switch time (§5.3) |
| 11 | **Probes are not evidence** | discipline | Probe record only in [results.md](results.md) |
| 12 | **Freeze ordering** — two freeze points; probe finalization (and a Beta switch) changes enumerated artifacts after FREEZE-1 | provenance | Canonical sequence (§3.2): **FREEZE-1** (pre-probe hashes: code/env/launcher/plan; order CSVs as applicable) → probes → probe-finalized commit + tag `rq2-extension-final-<date>` → **FREEZE-2** (post-probe: **FREEZE-2 re-hashes EVERY artifact that probe finalization can modify — the varying phases files, the launcher (shift-cell caps change on the Beta path), and the order CSVs; the launcher's md5 recorded at FREEZE-1 is provisional and is superseded by the FREEZE-2 value (both kept)**; tied to the final tag); both **before the campaign launch**, which runs from the frozen `rq2-extension-final` state ([run_matrix.md](run_matrix.md) §1) |
| 13 | **Edge fd exhaustion (EMFILE)** — observed 2026-09-27 (forensics): three meltdowns in 8 probe runs — contingency R2 (×12 232; 14–22 % timeouts; p50 33–74 s), B-P1 R2 (×4 088; lan1 wedge), B-P2 R1 (×10 892 / ×11 101; 149 k dropped/lane); containers never crash; container nofile = 1024 | platform | **D4 scan per run (§5.10 — both episodes)**; **nofile raise + log-rotation sync applied 2026-09-27** (user-approved; `--ulimit nofile=65536:65536` + `--log-opt` rotation on the RQ2 VM); verification via `rq2_ext_b_dbcb_rep` ✓ (0 EMFILE); **root cause resolved 2026-09-27 — the fd limit was a proximate ceiling: the spiral’s engine was the per-request O(buffer) `/service_pressure` scan (fix2 TTL cache, image `83cf6d973afe`; verification `rq2_ext_b_dbcb_fix2`)** |

---

## 9. Approval gates and next steps

**This package is the approval object.** Until it is approved, **no other file
is edited, no code is changed, and no run is launched.**

Only after approval, in order — the **canonical execution sequence** (§3.2;
mirrored in [run_matrix.md](run_matrix.md) §5):

1. **v3-final (VM)**: branch from tag `rq2-v3-campaign-20260808`; commit the
   pending campaign-era edits (v3 docs amendments + `EDGE_MEMORY` env edits +
   amended launcher); tag `rq2-v3-final-20260926`.
2. **Extension draft (VM)**: branch `rq2-extension`; apply the additive set
   (§3.1 — Parts A/B implementation): `policy_gate.py` `fixed_none` + unit
   check; `rq2_none.env`; launcher `CELLS` + force-add;
   the two varying phases files; the two order CSVs (CSV-1/CSV-2, §6);
   analyzer extensions (§7) with the regression smoke test; run
   `py_compile` and the policy-gate tests; commit; tag
   `rq2-extension-draft-20260926`.
3. **Verify (VM)**: diff `rq2-v3-final-20260926` ↔
   `rq2-extension-draft-20260926` restricted to the enumerated additive
   paths (§3.1); record md5s in [run_matrix.md](run_matrix.md) §1.
4. **FREEZE-1**: pre-probe hashes (code / env / launcher / plan; order CSVs
   as applicable).
5. **Stage-0 probes**: P1 (fixed launch config, §5.4 — in-place edits on the
   branch) / P2 / P3; record in [results.md](results.md); finalize **G** and
   Alpha/Beta.
6. **Probe-finalized commit (VM)**: commit the probe-determined artifacts;
   tag `rq2-extension-final-<date>`; verify md5s.
7. **FREEZE-2**: post-probe hashes recorded. **FREEZE-2 re-hashes EVERY
   artifact that probe finalization can modify — the varying phases files,
   the launcher (shift-cell caps change on the Beta path), and the order
   CSVs; the launcher's md5 recorded at FREEZE-1 is provisional and is
   superseded by the FREEZE-2 value (both kept).** Tied to
   `rq2-extension-final-<date>`.
8. **Campaign launch**: from the frozen (`rq2-extension-final-<date>`) state
   — Stage A1 = **CSV-1**; launcher stopped; checkpoint (analyze + gates;
   **6 passing runs**); **CSV-2** continues (§6); Part B Stage 1 launches
   after the checkpoint and probe completion; record tag + md5s in
   [run_matrix.md](run_matrix.md).

After the campaign: **docs integration** — cross-link this family from the
experiment docs index and the v3 RQ2 README note; thesis documents are
updated **only after results**, per claim discipline.

---

## Changelog

| Date | Change | Rationale |
| --- | --- | --- |
| 2026-09-26 | Plan package drafted (`experiment_plan.md`, `run_matrix.md`, `results.md`) — awaiting approval | Pre-registration before any implementation or run |
| 2026-09-26 | Reviewer resolution pass applied — 34 items (C1–C3, W1–W25, O1–O6): regime-keyed expectations, Part B gates + rerun rules, P1 launch config, freeze points, VM-side git sequence, additive-set path enumeration, cap-split + support conventions | Review gate (pre-approval) |
| 2026-09-26 | Second review-resolution pass applied (CR1, W1′–W11′, O1–O9): single canonical execution sequence + freeze tagging (`rq2-extension-draft` → `rq2-extension-final`); shift-cell M1 rescoped; strict-commit non-engagement verified; db→cb compute-budget carryover; base-file drift rule; plan-defined threshold consolidation; `cf_db` citation fixed to v3 `run_matrix.md` (`1, 2, 3, 4, 6`) | Review gate (pre-approval) |
| 2026-09-26 | Final corrections pass: threshold list completed (edge CPU drop ≥ 25 % falsification-leg alternative; P1-4 client drop < 10 %) and canonical-list claim reworded; env archive mirror removed (`rq2_none.env` only in `rq2_env/`; v3 mirror untracked — audit note); FREEZE-2 re-hash rule added (§3.2 step 7); `demand_drop` = 420 s settled (§5.2, §5.10 note, §8 item 4) | Pre-approval corrections |
| 2026-09-27 | **User ratified (items 1–3, 2026-09-27):** Beta bind **accepted** (two-run pooled 30.25 %, both readings recorded); incident handling = **D4 fd scan added (§5.10)** + §8 item 13 + lessons-log entry; nofile raise + root-cause deferred; **B-P2 `rq2_ext_b_dbcb` approved to launch** | User decision (post-B-P1r) |
| 2026-09-27 | **B-P2 executed:** **P2 `G` = 120 s derived** (replenish 17.6/17.0 s); R2 ✓ (activation; “compute-quiet” not met at 0.6 — regime finding); **R1 EMFILE meltdown → B-P2 partial**; two-episode audit (contingency R2 correction; battery = both episodes); fd incidence 3/8 — root-cause/nofile decision gates the campaign | Probe execution |
| 2026-09-27 | fd mitigation + log-rotation fix synced to the RQ2 VM (`--ulimit nofile=65536:65536`; `--log-opt` rotation; aggregator `INFO`); verification rerun `rq2_ext_b_dbcb_rep` launched | User decision (items 1–3) |
| 2026-09-27 | B-P2r verified the fd fix (0 EMFILE) but exposed the underlying **overload spiral → MEMCG OOM** (both edges; thread explosion); **dbcb R1 2/2 failed**; P2 re-confirmed (G = 120 s); root-cause mitigation gates the campaign | Probe execution |
| 2026-09-27 | **Edge-server concurrency bound implemented** (root-cause fix for the overload spiral — bounded request threads; `EDGE_MAX_CONCURRENCY=1024`); edge image rebuilt + smoked; verification run `rq2_ext_b_dbcb_fix1` launched | User decision (root-cause path) |
| 2026-09-27 | **fix2 verified the cache** (compute episode ~300–325 rps vs ~22 jam; 0.2 ms/req) **but n1 OOM-killed** (~1024 live threads × 8 MB stacks at the 512 m cap; total-vm 8.6 GB) **and the restarted edge failed to rejoin** (Mongo ping 180 s) → run D2-tainted; **fix 3 approved (memory hardening: thread cap 256 + 1 MB stacks)** | Probe execution |
| 2026-09-27 | **Probe finalization + FREEZE-2 executed (canonical steps 6–7):** Beta shift-cell caps finalized in the launcher (edge 0.6 / storage 0.15); probe-finalized commit `34cd78e` + tag **`rq2-extension-final-20260927`**; launch-state hashes recorded ([run_matrix.md](run_matrix.md) §1 — launcher `db91c566…`, phases `a7db82c8…`/`46fd82af…`, order CSVs unchanged, platform fixes, image `30a2c88bc1ce`); **sweep cleanup executed** (4 P1 folders → slim archive `_archived/rq2_p1_sweep_20260927.tar.gz` md5 `e96c7e77…` + deleted) | Canonical sequence (finalization) |
| 2026-09-28 | **Stage A1 + Stage 2 executed + verified (30/30 runs); Part B execution closed**; Part C (`rq2pc`) pre-registration + FREEZE-3 draft (`50b694c`) recorded ([results.md](results.md) timeline; [run_matrix.md](run_matrix.md)) — backfilled at Part C closure | Execution record |
| 2026-09-28 | **Part C probe ladder + bounded diagnostic pair @ 2.5 executed** (P-0 no lock; P-1 `nn`@3.0 LOCK ⇒ **R* = 3.0**; P-4 `cf`@3.0 lock re-check PASS, **signature FAIL**; diag pair: lan2 ×21.4 collapse, lan1 ×0.76, lan2 relapse min 6, lan1 mid-episode registry cull) | Probe execution |
| 2026-09-28 | **Part C CLOSED — user decision "stop + record": campaign NOT executed** (no reliably treatable window 1.5–3.0; mechanisms: registry liveness cull + assignment concentration); closure record in [results.md](results.md) § Part C + [run_matrix.md](run_matrix.md) §6; `phases_rq2pc_cb.json` restored to the frozen state; no `-final-` tag | User decision (post-diagnostic) |
| 2026-09-28 | **Part A/B pre-battery verification pass recorded** — read-only recompute of the Part A headline numbers from raw artifacts (v3 `latency_summary` reproduced exactly; plan-convention **Q-A1 0.680 / Q-A2 0.487** vs the draft quotes ≈0.56–0.62 / ≈0.35; Q-A3 + startup-transient/zero-add checks confirmed); pin list for the final battery (ratio conventions, ≈3× multiplier, L4 counts, build-delta/cap labels, `nn_db_3`) — [results.md](results.md) § Part A/B note | Verification (pre-battery) |
