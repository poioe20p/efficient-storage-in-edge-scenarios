# RQ2 — Bottleneck-Aware Scaling Action: Implementation Plan

> **Status:** Approved plan — to be implemented.
> **Scope:** RQ2 "required extension" from `tese/Notes/thesis_overview.md`.
> **Prerequisite:** RQ1 delivery-semantics plan (`docs/research_questions/v2/rq1/rq1_prepation.md`)
> must be implemented FIRST. This plan builds on RQ1's event-preserving delivery,
> `window_id` shared identifiers, `_log_decision`/`DECISION_LOG_PATH`, and the
> `_housekeeping_loop` ticker.
> **Date:** 2026-07-31.

This plan implements the RQ2 required extension: a **policy gate** that selects
scaling actions from a **declared bottleneck classification**, under three
switchable RQ2 policies (**compute-first fixed**, **storage-first fixed**,
**bottleneck-aware**), with a per-tier **action budget**, and a per-decision log
of evidence, selected action, rejected action, and budget.

`SCALEUP_POLICY=dual` (the **default**) preserves the current pre-RQ2 behavior
exactly (both tiers may scale independently, no budget, RQ1 per-submission
logging) so canonical and RQ1 runs are byte-identical. The three RQ2 arms are
explicitly selected per run; each run uses exactly one arm.

This plan is **not phased** (like RQ1); no phase/order prefixes apply to
controller modules (import-safe names). New experiment/analyzer files carry the
`rq2_` scope prefix. The plan doc itself is `rq2_preparation.md`.

---

## 1. Locked decisions

- **D1 — Policy arms (switchable, per run):**
  - `SCALEUP_POLICY=dual` (**default**) — current pre-RQ2 behavior: both tiers
    may fire and submit independently, no budget, RQ1 per-submission decision
    logging. Preserves canonical + RQ1 runs unchanged. **Not** an RQ2 comparison
    arm.
  - `SCALEUP_POLICY=fixed_compute_first` — always scale compute, never storage.
  - `SCALEUP_POLICY=fixed_storage_first` — always scale storage, never compute.
  - `SCALEUP_POLICY=bottleneck_aware` — classify the bottleneck from
    tier-specific telemetry and select the matching action.
  The three RQ2 arms are the comparison set; a run never mixes arms. Unknown
  value → log error + fall back to `dual` (deliberate, documented).
- **D2 — Identical evaluation rule across the three RQ2 arms (hard
  requirement):** the evaluation **mechanics** — sliding-window append +
  clear-on-fire, per-tier eligibility checks (not busy, not at cap), and the
  degradation-score formula — are identical in every RQ2 arm; the only
  difference is which fired tier becomes a **submitted action** (commit).
  **Scale-up** cooldown timestamps are set in `commit_*` (actual scaling), never
  on firing, so cooldown state diverges across arms only as the direct
  consequence of the different selection (the treatment effect, not a confound).
  **Scale-down** cooldown protection is keyed on **firing** (D7), keeping that
  protective behavior arm-identical.
- **D3 — Bottleneck classifier:** controller-side, in Thread 2, on
  `DomainSummary`. Compares each tier's **weight-normalised, clamped degradation
  score** `score_norm = min(1.0, score / (w_cpu + w_lat)) ∈ [0,1]` — a measure
  of "how far above its own floor each tier's composite signal is". The higher
  tier is the bottleneck; a pre-registered margin `BOTTLENECK_CLASSIFY_MARGIN`
  (default `0.05`) suppresses noise ties (tie → storage, documented: storage is
  the higher-urgency tier). Documented proxy (like RQ1's `overload`),
  pre-registered per run, identical across arms. Caveat: under RQ2 weights the
  compute score mixes CPU+proc-latency while storage is T_db-only, so the
  classifier is validated empirically by the induced-episode raw-signal check
  (T7 `rq2_bottleneck_validation.py`).
- **D4 — Action budget:** `ACTION_BUDGET_PER_TIER` (default `4`), a hard ceiling
  on **scale-up (spawn) submissions per tier per controller (per LAN)**.
  Scale-down does not consume budget. `dual` ignores the budget. Once a tier's
  budget is exhausted, that tier can never be submitted again for the rest of
  the run. Budget usage is logged per decision (`budget_used`, `budget_cap`).
  Each controller runs its own `PolicyGate`, so a two-LAN run can reach 2× per
  tier; analysis aggregates per-tier counts across LANs and reports budget per
  LAN.
- **D5 — Episode label is post-hoc:** the controller stays **blind** to the
  induced episode. The run's `phases_snapshot.json` is the ground-truth label;
  the **analyzer** attaches it to every decision row in the final dataset. No
  `EPISODE_LABEL` env is injected. The thesis's "log the known induced episode
  label ... for every decision" is satisfied at the **analysis layer**: the
  final per-decision dataset (not the controller CSV) carries `episode_label`.
- **D6 — Single episode per run:** each run executes exactly **one** induced
  bottleneck episode (compute-bound **or** data-access-bound) plus baseline and
  recovery-tail phases. Episode type and policy arm are **counterbalanced /
  blocked** across the campaign (full factorial: 3 policies × 2 episodes × N
  replicates).
- **D7 — Scale-down stays active and identical:** RQ1's `_housekeeping_loop`
  ticker runs scale-down (compute + storage) with the same thresholds in all
  arms. The **scale-down cooldown keys on the scale-up fire timestamp**
  (`_last_<tier>_scale_up_fired_ts`, §2.2): when a tier's scale-up sliding
  window fires — including a fire that is policy-suppressed and never submitted
  — that tier's scale-down is cooldown-suppressed for `SCALEDOWN_*_COOLDOWN_S`.
  In `dual` (pre-RQ2) every fire is also a submit, so both timestamps advance
  together and dual behavior is preserved; in RQ2 arms a suppressed fire still
  engages the scale-down cooldown, protecting the fire region from down-scale.
  Firing is arm-identical, so this protection is identical across arms and
  closes the storage scale-up/scale-down overlap (scale-up fires near
  `TAU_DB_DOWN_MS` while scale-down arms below it). Validated in T9 via the
  logged `*_fired` columns. Node-minutes and action counts remain a complete,
  comparable footprint measure.
- **D8 — Confounders disabled for RQ2 runs:** `STORAGE_PERSISTENT_RESERVE_ENABLED=0`,
  `SS_ENABLED=0`, cross-region off. Telemetry delivery = `event_preserving`
  (RQ1 reference arm) in all RQ2 runs.
- **D9 — Scope:** RQ2 studies **scale-out selection only**. The backend-admission
  condition is the existing VIP admission (held constant); RQ3's readiness probe
  is out of scope.

---

## 2. Architecture

### 2.1 Two-layer split (evaluation vs selection)

`ScalingPolicy` keeps **pure per-tier evaluation** (identical in all RQ2 arms);
a new `PolicyGate` performs **selection + budget enforcement**; the mediator
commits the selected action. When `SCALEUP_POLICY=dual` the mediator takes the
legacy RQ1 path unchanged.

```text
_on_telemetry_update()                        [Thread 2 mediator, main_n*.py]
  │  (empty window, domain_summary None → skip, as RQ1)
  │  (elasticity busy → skip evaluation, as RQ1)
  ├─ SCALEUP_POLICY == "dual" → legacy RQ1 path (facade + RQ1 logging) — unchanged
  │
  └─ RQ2 arms:
      ├─ evaluate_compute_scale_up(ds, …) → ScaleUpVerdict (eligible, fired, score_norm)
      ├─ evaluate_storage_scale_up(ds, …) → ScaleUpVerdict (eligible, fired, score_norm)
      │     (sliding windows advance + clear-on-fire IDENTICALLY in all RQ2 arms;
      │      cooldown/cap → eligible=False, no advance — same rule as today)
      ├─ gate.select(compute_v, storage_v) → selected tiers (fixed / bottleneck / both)
      ├─ budget filter (RQ2 arms only)
      ├─ commit_*() for each selected tier     (cooldown + cross-direction reset)
      ├─ submit alert(s)  (storage path keeps the reserve branch first, as today)
      └─ _log_decision(...)  → ONE 'scale_up' row per window with evidence + decision
```

### 2.2 Evaluation verdict (identical in all RQ2 arms)

`evaluate_*` always returns a `ScaleUpVerdict` (never `None`); the cooldown and
cap checks stay **inside** the evaluation methods (as today: when in cooldown or
at cap, `eligible=False` and the sliding window does **not** advance). Evidence
(`score_norm`, `threshold`) is computed for every call regardless of eligibility
— this is what makes the decision log a continuous evidence series.

```python
@dataclass(frozen=True)
class ScaleUpVerdict:
    tier: Literal["compute", "storage"]
    eligible: bool        # not busy/blocked, not in scale-up cooldown, not at cap
    fired: bool           # eligible AND window hits >= REQUIRED (window advanced + cleared)
    score_norm: float     # min(1.0, score / (w_cpu + w_lat)) — always computed, [0,1]
    score: float          # raw degradation_score (diagnostics)
    threshold: float      # effective threshold (always computed)

class ScalingPolicy:
    def evaluate_compute_scale_up(self, ds, dynamic_compute_count, peer_ds,
                                  *, blocked=False) -> ScaleUpVerdict: ...
    def evaluate_storage_scale_up(self, ds, dynamic_storage_count,
                                  *, blocked=False) -> ScaleUpVerdict: ...
    def commit_compute_scale_up(self) -> None:  # sets _last_compute_scale_up_ts +
    def commit_storage_scale_up(self) -> None:  # clears the cross-direction scale-down window
```

`blocked` = the mediator's `blocks_compute_scale_up()` / `blocks_storage_scale_up()`
(busy / pending-storage-drain). Two cooldown timestamp pairs per tier (D7):
`evaluate_*` sets `_last_<tier>_scale_up_fired_ts` **on fire** (consumed only by
`compute_cooldown_remaining()` / `storage_cooldown_remaining()`, the scale-**down**
cooldowns); `commit_*` sets `_last_<tier>_scale_up_ts` (consumed by
`*_scaleup_cooldown_remaining()`, the scale-**up** cooldowns). The legacy
`evaluate_scale_up` facade is **kept** and used only by the `dual` path (RQ1
unchanged); it is not called in RQ2 arms.

### 2.3 Policy gate (selection + budget)

```python
class PolicyGate:
    def __init__(self, mode: str, budget_per_tier: int, margin: float) -> None: ...

    def select(self, compute_v, storage_v) -> tuple[Literal["compute", "storage"], ...]:
        """dual:             every fired tier (0..2), no budget.
        fixed_compute_first: ("compute",) if compute_v.fired else ()
        fixed_storage_first: ("storage",) if storage_v.fired else ()
        bottleneck_aware:    both fired → (classify(),);
                             one fired → that tier; none → ()"""

    def classify(self, compute_v, storage_v) -> Literal["compute", "storage"]:
        """Considers ELIGIBLE verdicts only. Exactly one eligible tier → that
        tier. Both eligible → higher score_norm wins; |Δ| <= margin → storage
        (documented tie-break). Neither eligible → caller uses "n/a"."""

    def budget_available(self, tier) -> bool: ...
    def consume_budget(self, tier) -> None: ...
    def budget_used(self, tier) -> int: ...
    @property
    def mode(self) -> str: ...
```

`mode` from `SCALEUP_POLICY`; `budget_per_tier` from `ACTION_BUDGET_PER_TIER`
(`0` in `dual` → budget disabled); `margin` from `BOTTLENECK_CLASSIFY_MARGIN`.
Read at construction in `main_n*.py` and logged at startup for provenance.

### 2.3.1 `ba-strict` sticky commitment (`BOTTLENECK_STRICT_SINGLE`)

Added in the RQ2 v2 rework (2026-08-04, `rq2_v2_rework_plan.md` Phase 3) as a
**distinct, named configuration regime** (env
`rq2_bottleneck_aware_strict.env`; allowed by the canonical-env rule — a named
axis — sticky vs per-window commitment — not a per-experiment tweak). It keeps
`SCALEUP_POLICY=bottleneck_aware` and adds a **sticky commitment** so the clean
H1 test isolates "telemetry picks the right single action" from the v1
`ba_db` both-tiers effect (v1's gate acted on whichever tier fired alone per
window, accumulating 8 compute + 8 storage).

**Knobs** (read by `scaling_config.py`, consumed directly by `PolicyGate` —
no `scaling_policy.py` passthrough):

| Knob | Default | Meaning |
|---|---|---|
| `BOTTLENECK_STRICT_SINGLE` | `0` | `1` enables sticky commitment (only meaningful with `bottleneck_aware`). `0` → behavior **byte-identical** to the non-strict gate. |
| `STRICT_COMMIT_N` | `2` | consecutive same-tier fires required to commit when only one tier fires alone |
| `STRICT_RELEASE_N` | `3` | consecutive windows below the committed tier's threshold required to release the commitment (relief) |

**Gate behavior while committed:**

1. **Confidence-qualified commit** (avoids a single spurious fire locking the
   wrong tier): the gate commits when either (a) **both** tiers fire in a
   window (classified with the D3 margin), or (b) the **same single tier**
   fires in `STRICT_COMMIT_N` consecutive windows.
2. **Suppression while committed:** ONLY the committed tier can be selected.
   When the other tier fires alone it is **suppressed** — the fire is still
   logged (`*_fired=1`, `rejected_action=<suppressed tier>`), the decision
   row's `reason="strict_suppressed"`, and `selected_action` = committed tier
   (or `"none"` when only the suppressed tier fired). Verified in
   `main_n1.py`/`main_n2.py` (20-column decision log).
3. **Release on relief:** the commitment releases when the committed tier's
   `score_norm` falls back under its `*_threshold` for `STRICT_RELEASE_N`
   consecutive windows; the gate then requires the same confidence trigger to
   re-commit and **cannot re-commit to the opposite tier before release** (no
   chained oscillation).

`BOTTLENECK_STRICT_SINGLE=0` keeps the per-window behavior of §2.3 exactly
(regression-tested in T9).

### 2.4 Decision-log schema (extends RQ1)

`_log_decision` keeps RQ1's row shape `ts, network_id, window_id, action_type, action`
and RQ1 call sites unchanged. RQ2 adds **keyword-only optional columns** and a
new per-window `scale_up` row for RQ2 arms:

| Column (new, keyword-only) | Value |
|---|---|
| `compute_score_norm` | evidence, always filled on RQ2 `scale_up` rows |
| `storage_score_norm` | evidence, always filled on RQ2 `scale_up` rows |
| `compute_threshold` | effective compute threshold for the window |
| `storage_threshold` | effective storage threshold for the window |
| `compute_fired` | `1`/`0` — compute scale-up window fired this window |
| `storage_fired` | `1`/`0` — storage scale-up window fired this window |
| `compute_eligible` | `1`/`0` — compute was eligible (not busy/blocked/cooldown/cap) |
| `storage_eligible` | `1`/`0` — storage was eligible |
| `bottleneck_class` | `"compute"` / `"storage"` / `"n/a"` (classifier over ELIGIBLE tiers; `"n/a"` when neither is eligible) |
| `selected_action` | `"compute"` / `"storage"` / `"none"` (RQ2 arms, ≤1) |
| `rejected_action` | the tier that FIRED but was not selected, where non-selection was **policy** (not budget): the other tier when exactly one is selected and it fired; or the sole fired tier in a fixed arm when nothing was selected. `""` when reason is `"budget_exhausted"` or nothing fired. Budget-rejected tiers are visible via `*_fired` + `*_budget_used` |
| `compute_budget_used` | compute budget counter after this decision (always filled) |
| `storage_budget_used` | storage budget counter after this decision (always filled) |
| `budget_cap` | `ACTION_BUDGET_PER_TIER` |
| `reason` | `"action"` if an action was submitted; else `"budget_exhausted"` if any fired tier was budget-blocked; else `"none"` |

**CSV contract (mode-dependent):** the format is chosen once at controller start
from `SCALEUP_POLICY`.
- **dual (and any pre-RQ2 / canonical run):** RQ1's exact format, byte-identical
  to pre-RQ2 — header `ts,network_id,window_id,action_type,action` (RQ1's
  `_log_decision` already writes this header) + 5-column rows.
- **RQ2 arms:** header row on first write + full column set in the exact order
  `ts, network_id, window_id, action_type, action, compute_score_norm,
  storage_score_norm, compute_threshold, storage_threshold, compute_fired,
  storage_fired, compute_eligible, storage_eligible, bottleneck_class,
  selected_action, rejected_action, compute_budget_used, storage_budget_used,
  budget_cap, reason`. The keyword-only parameter order in `_log_decision` MUST
  match this header order. RQ2-arm rows leave a column empty (`""`) only where a
  value is not applicable — never for the evidence/`*_fired`/`*_eligible`/`*_budget_used`
  columns.

Rules:
- **RQ2 arms:** exactly **one** `scale_up` row per evaluated window (a window
  with `domain_summary` and Thread 2 not busy), including `selected_action="none"`.
  Empty windows (`domain_summary is None`) and busy windows produce **no**
  `scale_up` row (no decision was made) — this defines the decision universe.
- **dual:** RQ1's per-submission rows, unchanged (no RQ2 columns).
- Non-scale-up submissions (scale-down, absent-node, reserve, cancel-drain) keep
  their RQ1 rows (`action_type`/`action` exactly as RQ1) with the RQ2 columns empty.
- `episode_label` is **not** a controller column; the analyzer attaches it from
  `phases_snapshot.json` (D5).

---

## 3. File map

**New**

| File | Purpose |
|---|---|
| `docs/research_questions/v2/rq2/rq2_preparation.md` | This plan |
| `source/sdn_controller/policy_gate.py` | `PolicyGate`: select + classify + budget (modes: dual + 3 RQ2 arms) |
| `source/scripts/testing/phases_override/phases_rq2_compute_bound.json` | Single-episode run: baseline → compute-bound → recovery |
| `source/scripts/testing/phases_override/phases_rq2_data_bound.json` | Single-episode run: baseline → data-bound → recovery |
| `source/scripts/testing/controller_env_overrides/rq2_compute_first.env` | Full RQ2 regime, `SCALEUP_POLICY=fixed_compute_first` |
| `source/scripts/testing/controller_env_overrides/rq2_storage_first.env` | Full RQ2 regime, `SCALEUP_POLICY=fixed_storage_first` |
| `source/scripts/testing/controller_env_overrides/rq2_bottleneck_aware.env` | Full RQ2 regime, `SCALEUP_POLICY=bottleneck_aware` |

> **2026-08-02 supersession (experiment-plan authoring):** the **authoritative**
> copies of these three env files now live at
> `docs/operation/testing/experiment/v2/rq2/env/` (rebase: caps 6/6 + budget 4
> + Q6 scale-down calibration). The `controller_env_overrides/` copies listed
> above are **superseded** — do not use them for runs (kept for provenance).
| `docs/research_questions/v2/rq2/rq2_bottleneck_validation.py` | Induced-episode validation from raw `window_log.jsonl` signals (independent of the controller's classifier) |
| `docs/research_questions/v2/rq2/rq2_decision_analysis.py` | Join decision+window+delivery logs → per-run decision/action table + counterbalance check |
| `docs/research_questions/v2/rq2/rq2_relief_analysis.py` | Time-to-recover + relief-in-targeted-tier from the decision log's per-window evidence series |
| `docs/research_questions/v2/rq2/rq2_node_minutes.py` | Compute/storage node-minutes from decision-log scale-up/scale-down rows |

**Modified**

| File | Change |
|---|---|
| `source/sdn_controller/scaling_config.py` | `SCALEUP_POLICY` (default `dual`), `ACTION_BUDGET_PER_TIER`, `BOTTLENECK_CLASSIFY_MARGIN` |
| `source/sdn_controller/scaling_policy.py` | Add `ScaleUpVerdict` + `evaluate_compute/storage_scale_up` + `commit_*`; keep the `evaluate_scale_up` facade for `dual`; expose `score_norm` |
| `source/sdn_controller/main_n1.py`, `main_n2.py` | Mode dispatch (`dual` vs RQ2 arms); wire `PolicyGate`; `commit_*` on submission; extend `_log_decision` with RQ2 columns |
| `source/scripts/testing/analysis/rq2/extract_spawn_metrics.py` | Extend to cover storage-tier spawns (`data:` spawning lines) and decision-log action anchoring (`--tiers compute,storage`, `--anchor decision`) for time-to-usable-capacity |
| `docs/operation/elasticy_manager/elasticity_overview.md` | Document the policy gate + link this plan |
| `docs/operation/elasticy_manager/scale_up/compute_scale_up.md` | Note selection goes through the gate in RQ2 arms |
| `docs/operation/elasticy_manager/scale_up/storage_scale_up.md` | Note selection goes through the gate in RQ2 arms |
| `docs/operation/telemetry/controller_side/controller_telemetry_consumer.md` | Update `evaluate_scale_up` reference: facade is now the `dual` path only |
| `docs/operation/elasticy_manager/implementation/storage_persistent_reserve/phase_3_storage_persistent_reserve_activation_and_replenishment.md` | Update `evaluate_scale_up` reference: facade is now the `dual` path only |

**Unchanged:** `run_experiment.sh` (RQ1 already collects `decision_log`,
`window_log`, `phases_snapshot.json`, `controller_env_snapshot.env`). `tese/Notes/thesis_overview.md`
untouched. (Archived `docs/operation/archive/other/telemetry_refactor_plan.md`
also references the facade — archived, note-only, no change.)

---

## 4. Task breakdown (ordered)

### T1 — `scaling_config.py`

```python
_SCALEUP_POLICY = os.environ.get("SCALEUP_POLICY", "dual")
# ∈ {"dual", "fixed_compute_first", "fixed_storage_first", "bottleneck_aware"}
# "dual" (default) = pre-RQ2 behavior (RQ1/canonical runs unchanged).
# unknown value → log error + fall back to "dual" (deliberate, documented).

_ACTION_BUDGET_PER_TIER = int(os.environ.get("ACTION_BUDGET_PER_TIER", "4"))
_BOTTLENECK_CLASSIFY_MARGIN = float(os.environ.get("BOTTLENECK_CLASSIFY_MARGIN", "0.05"))
```

### T2 — `scaling_policy.py`

1. Add `ScaleUpVerdict` dataclass (module-level) per §2.2. Initialize
   `_last_compute_scale_up_fired_ts` / `_last_storage_scale_up_fired_ts =
   float('-inf')` in `__init__` alongside the existing pair (avoids AttributeError
   on the first scale-down cooldown query before any fire).
2. Add `evaluate_compute_scale_up(ds, dynamic_compute_count, peer_ds, *, blocked=False) -> ScaleUpVerdict`:
   compute evidence (score, `score_norm = min(1.0, score/(w_cpu+w_lat))`, threshold)
   **always**; `eligible = not blocked and dynamic_compute_count < _MAX_DYNAMIC_COMPUTE
   and compute_scaleup_cooldown_remaining() <= 0`; if not eligible return
   `fired=False` **without touching the window**; if eligible, append
   `score >= threshold`; **on fire** set `_last_compute_scale_up_fired_ts =
   time.monotonic()` (D7 scale-down cooldown), clear the **scale-up** window,
   return `fired=True`.
3. Add `evaluate_storage_scale_up(ds, dynamic_storage_count, *, blocked=False) -> ScaleUpVerdict`:
   same treatment (sets `_last_storage_scale_up_fired_ts` on fire).
4. Add `commit_compute_scale_up()` / `commit_storage_scale_up()`: set
   `_last_compute_scale_up_ts` / `_last_storage_scale_up_ts = time.monotonic()`
   (scale-up cooldown) and clear the same-tier **scale-down** window (the
   cross-direction resets that today live inside the fire blocks). Called
   **only** on actual submission.
5. **Switch the two scale-down cooldown queries** `compute_cooldown_remaining()`
   and `storage_cooldown_remaining()` from `_last_<tier>_scale_up_ts` to
   `_last_<tier>_scale_up_fired_ts` (they feed the housekeeping scale-down path
   in ALL modes — §2.2). Also update `record_storage_activation` (reserve
   feature) to set BOTH `_last_storage_scale_up_ts` and
   `_last_storage_scale_up_fired_ts` — a reserve activation is a scale-up event,
   so dual-with-reserve scale-down cooldown stays byte-identical to pre-RQ2.
6. **Update the legacy `evaluate_scale_up` facade (dual path only):** at its
   existing fire/submit point, in addition to `_last_<tier>_scale_up_ts`, also
   set `_last_<tier>_scale_up_fired_ts = time.monotonic()` — in dual fire==submit,
   so both timestamps advance together and dual behavior stays byte-identical to
   today. RQ2 arms never call the facade.
7. Scale-down evaluation methods unchanged.

### T3 — `policy_gate.py` (new)

Implement `PolicyGate` per §2.3. Pure logic, no I/O, Thread 2 only. Modes:
`dual` (return every fired tier, budget disabled), `fixed_compute_first`,
`fixed_storage_first`, `bottleneck_aware` (classify per D3; tie → storage).
Budget counters per tier; `budget_per_tier=0` disables enforcement.

### T4 — `main_n1.py` / `main_n2.py` (mediator wiring)

The dispatch replaces the body of the existing `else:` scale-up branch in
`_on_telemetry_update` (the branch that currently runs `evaluate_scale_up(...)`),
so it sits **inside** the existing `has_active_operation()` early-return (that
check stays shared by both modes — the RQ2 path does **not** re-check busy). All
surrounding values (`ds`, `lan`, `dynamic_storage_count`,
`effective_dynamic_compute_count`, `peer_ds`, `compute_blocked`,
`storage_blocked`) are already computed above the branch and are **reused**; do
not recompute them.

```python
if self._elasticity.has_active_operation():
    logger.debug("[scale-up] elasticity manager is busy — skipping")
else:
    if _SCALEUP_POLICY == "dual":
        # ── RQ1 legacy path — UNCHANGED ───────────────────────────
        # existing evaluate_scale_up(...) loop, reserve branch, RQ1 _log_decision
        # rows (legacy 5-column format). (Do not modify this branch.)
        ...
    else:
        # ── RQ2 arms path ─────────────────────────────────────────
        # `ds is not None` is guaranteed: `_on_telemetry_update` already returns
        # early when `domain_summary is None` (RQ1). Guard kept as defense-in-depth.
        if ds is not None:
            compute_v = self._scaling_policy.evaluate_compute_scale_up(
                ds, effective_dynamic_compute_count, peer_ds, blocked=compute_blocked)
            storage_v = self._scaling_policy.evaluate_storage_scale_up(
                ds, dynamic_storage_count, blocked=storage_blocked)

            selected = list(self._policy_gate.select(compute_v, storage_v))
            selected = [t for t in selected if self._policy_gate.budget_available(t)]

            bottleneck_class = (self._policy_gate.classify(compute_v, storage_v)
                                if (compute_v.eligible or storage_v.eligible) else "n/a")

            for tier in selected:
                if tier == "compute":
                    self._scaling_policy.commit_compute_scale_up()
                    self._policy_gate.consume_budget("compute")
                    self._elasticity.submit(ComputeAlert(lan=lan, network_id=summary.network_id))
                    if self._elasticity.has_pending_compute_drain():
                        # cancel-compute-drain: keep RQ1's existing logging for that
                        # submission site (match RQ1's action_type/action exactly;
                        # do NOT add a second row here).
                        self._elasticity.submit_cancel_compute_drain()
                elif tier == "storage":
                    # keep the existing reserve branch FIRST, as today:
                    #   if self._handle_storage_reserve_trigger(summary, lan, "load"): continue
                    # (defensive only — unreachable in RQ2 runs:
                    #  STORAGE_PERSISTENT_RESERVE_ENABLED=0)
                    self._scaling_policy.commit_storage_scale_up()
                    self._policy_gate.consume_budget("storage")
                    self._elasticity.submit(DataAlert(
                        lan=lan, network_id=summary.network_id,
                        rs_name=f"rs_net{lan}", primary_container=f"edge_storage_server_n{lan}"))

            reason = ("action" if selected
                      else "budget_exhausted"
                      if any((compute_v.fired and not self._policy_gate.budget_available("compute"),
                              storage_v.fired and not self._policy_gate.budget_available("storage")))
                      else "none")

            self._log_decision(
                "scale_up",
                "ComputeAlert" if selected == ["compute"]
                else "DataAlert" if selected == ["storage"]
                else "none",
                window_id=summary.window_id,
                compute_score_norm=compute_v.score_norm,
                storage_score_norm=storage_v.score_norm,
                compute_threshold=compute_v.threshold,
                storage_threshold=storage_v.threshold,
                compute_fired=1 if compute_v.fired else 0,
                storage_fired=1 if storage_v.fired else 0,
                compute_eligible=1 if compute_v.eligible else 0,
                storage_eligible=1 if storage_v.eligible else 0,
                bottleneck_class=bottleneck_class,
                selected_action=selected[0] if selected else "none",
                rejected_action=("" if reason == "budget_exhausted"
                                 else "storage" if selected == ["compute"] and storage_v.fired
                                 else "compute" if selected == ["storage"] and compute_v.fired
                                 else "storage" if not selected and storage_v.fired and not compute_v.fired
                                 else "compute" if not selected and compute_v.fired and not storage_v.fired
                                 else ""),
                compute_budget_used=self._policy_gate.budget_used("compute"),
                storage_budget_used=self._policy_gate.budget_used("storage"),
                budget_cap=_ACTION_BUDGET_PER_TIER,
                reason=reason,
            )
        # (empty windows never reach here; no scale-up decision row for them, as RQ1)
```

Notes:
- Scale-down path untouched (RQ1 ticker). `record_storage_activation` stays
  inside the reserve feature's own path, unrelated to RQ2.
- Fixed arms still call **both** `evaluate_*` (windows advance identically, D2);
  the gate never selects the suppressed tier. The suppressed tier's fire is
  recorded (`*_fired=1`, `selected="none"`) so the counterfactual is analyzable.
- Evidence and `*_fired`/`*_eligible`/`*_budget_used` are logged on **every**
  RQ2 window — including `selected="none"`, budget-exhausted, and cooldown
  windows — so the decision log is a continuous evidence series.
- `classify` restricts to eligible tiers (§2.3); `bottleneck_class` is `"n/a"`
  only when neither tier is eligible.
- `_log_decision` selects the CSV format from `SCALEUP_POLICY` (CSV contract,
  §2.4): dual → RQ1's header + 5 columns, byte-identical; RQ2 arms → header +
  full column set. Existing RQ1 call sites (positional) are otherwise untouched.

### T5 — controller env regimes (3 files)

Each file sets the **full** RQ2 regime (distinct, named configuration regime —
allowed by the repo rules). The three files differ **only** in `SCALEUP_POLICY`.
Selected per run via `OSKEN_ENV_OVERRIDE_FILE`; the run folder snapshots it to
`controller_env_snapshot.env`. The block below lists the **complete** set of
scaling knobs read by `scaling_config.py`/`scaling_policy.py`. **Base-env
layering:** these files are applied as an *override* on `osken-controller.env`
(see `run_experiment.sh prepare_controller_env_source`); a knob **not** listed
here keeps the BASE value, not the compiled default. Cross-arm identity is
already guaranteed because the three files are identical except `SCALEUP_POLICY`;
listing a knob here fixes its absolute operating point (state in each file's
header comment that unlisted knobs resolve from the base env).

```text
# RQ2 policy arm regime — <ARM NAME>
# Unlisted knobs resolve from the base osken-controller.env (override semantics).
# The three arm files are identical except the SCALEUP_POLICY line; the knobs
# below fix the absolute operating point shared by all three arms.
STORAGE_PERSISTENT_RESERVE_ENABLED=0
SS_ENABLED=0
CROSS_REGION_STORAGE_ENABLED=0
TELEMETRY_SOURCE=event_preserving
SCALEUP_POLICY=<arm>
ACTION_BUDGET_PER_TIER=4
BOTTLENECK_CLASSIFY_MARGIN=0.05
# ── scale-up weights / floors / spans ──
SCALEUP_W_CPU=0.60
SCALEUP_W_T_PROC=0.40
SCALEUP_CPU_FLOOR=10
SCALEUP_CPU_SPAN=40
SCALEUP_T_PROC_FLOOR=25
SCALEUP_T_PROC_SPAN=80
SCALEUP_W_STORAGE_CPU=0
SCALEUP_W_T_DB=1.0
SCALEUP_STORAGE_CPU_FLOOR=1.5
SCALEUP_STORAGE_CPU_SPAN=5
SCALEUP_T_DB_FLOOR=60
SCALEUP_T_DB_SPAN=250
# ── compute scale-up thresholds / window / cooldown / peer relief ──
SCALEUP_COMPUTE_BASE_THRESHOLD=0.18
SCALEUP_COMPUTE_THRESHOLD_INCREMENT=0.10
SCALEUP_COMPUTE_MAX_THRESHOLD=0.85
SCALEUP_WINDOW_SIZE=5
SCALEUP_REQUIRED=3
SCALEUP_COMPUTE_COOLDOWN_S=45
SCALEUP_COMPUTE_PEER_RELIEF=0.03
SCALEUP_COMPUTE_PEER_HEALTH_THRESHOLD=0.35
# ── storage scale-up thresholds / window / cooldown ──
SCALEUP_STORAGE_BASE_THRESHOLD=0.35
SCALEUP_STORAGE_THRESHOLD_INCREMENT=0.10
SCALEUP_STORAGE_MIN_INCREMENT=0.05
SCALEUP_STORAGE_MAX_THRESHOLD=0.55
SCALEUP_STORAGE_WINDOW_SIZE=5
SCALEUP_STORAGE_REQUIRED=2
SCALEUP_STORAGE_COOLDOWN_S=120
# ── caps ──
MAX_DYNAMIC_COMPUTE=12
MAX_DYNAMIC_STORAGE=8
# ── scale-down thresholds / windows / cooldowns / ceilings ──
TAU_CPU_DOWN=15
TAU_PROC_DOWN_MS=20
TAU_STORAGE_CPU_DOWN=15
TAU_DB_DOWN_MS=150
SCALE_DOWN_COMPUTE_WINDOW_SIZE=12
SCALE_DOWN_COMPUTE_REQUIRED=9
SCALE_DOWN_STORAGE_WINDOW_SIZE=12
SCALE_DOWN_STORAGE_REQUIRED=7
SCALEDOWN_COMPUTE_COOLDOWN_S=180
SCALEDOWN_STORAGE_COOLDOWN_S=120
SCALE_DOWN_PROC_TIMEOUT_CEILING_MS=5000
SCALE_DOWN_DB_TIMEOUT_CEILING_MS=5000
SCALE_DOWN_CANDIDATE_MAX_STALENESS_S=90
# ── absent-node / heartbeat (RQ1 housekeeping) ──
TELEMETRY_TIMEOUT_WINDOWS=18
NODE_BIRTH_GRACE_S=60
# ── RQ1 delivery / decision logging (pinned; unlisted knobs resolve from base) ──
CONTROL_TICK_S=10
DELAY_S=30
EVENT_POLL_INTERVAL_S=0.5
DELIVERY_LOG_PATH=/tmp/telemetry_delivery_log.csv
DECISION_LOG_PATH=/tmp/decision_log.csv
```

Values above mirror the current integrated reference / compiled defaults where
available; the Experiment Designer pre-registers the final identical set for all
three arms. The structural requirement: **all three arm files are identical
except the `SCALEUP_POLICY` line**, so every knob (including the RQ1 delivery
knobs above) resolves to the same effective value in every arm.

### T6 — episode phase files (2 files, `phases_override/`)

Each is a **single-episode** run (D6): `baseline` → `<episode>` →
`cleanup_gap` (recovery tail). Selected per run via `--phases-config`
(existing mechanism); run folder snapshots to `phases_snapshot.json` (the
post-hoc episode label source).

- `phases_rq2_compute_bound.json` — episode mix dominated by **compute-bound**
  endpoints (`service_pressure`, `feed_ranking`), low DB traffic, no cross-region
  hotspot, sustained rate high enough to push `T_proc`/CPU.
- `phases_rq2_data_bound.json` — episode mix dominated by **data-bound**
  endpoints (`content_lookup`, `content_update`, `content_aggregate`), low
  compute pressure, sustained rate high enough to push `T_db`/storage CPU.

Exact durations/rates/mix weights are **experiment-design calibration**
(Experiment Designer) — this plan fixes the *structure* and the endpoint
families. `phases.json` (canonical) is untouched; these are distinct named
regimes under the existing `phases_override/` mechanism.

### T7 — analyzer scripts (`docs/research_questions/v2/rq2/`, scope-prefixed)

All four tools **first confirm the run is an RQ2 run** by reading
`controller_env_snapshot.env`: only runs whose `SCALEUP_POLICY` is one of the
three RQ2 arms are processed; RQ1/canonical runs (`dual` or absent) are skipped
(RQ1's own analyzers handle those).

- `rq2_bottleneck_validation.py` — **independent** of the controller: from
  `window_log.jsonl` raw `domain_summary` signals, confirm the induced episode
  produced the intended bottleneck across all three arms (compute-bound runs:
  `avg_time_proc_ms`/`average_cpu_percent` elevated while `avg_time_db_ms`/
  `avg_storage_cpu_percent` stay low during the episode; data-bound: inverse).
  Emit a per-run validation table.
- `rq2_decision_analysis.py` — filter `decision_log.csv` rows where
  `action_type="scale_up"`; join `window_id` ↔ `window_log.jsonl` (delivery
  timing) and attach `episode_label` from `phases_snapshot.json`. Emit per-run:
  decision time, evidence (`compute_score_norm`, `storage_score_norm`),
  `selected_action`, `rejected_action`, `bottleneck_class`, budget usage,
  per-tier action counts, the **per-window classifier-vs-episode agreement**
  (fraction of windows where `bottleneck_class` matches the induced episode,
  computed **only over windows whose `window_end` falls inside the episode
  phase** per `phases_snapshot.json` — the empirical check of the D3 proxy),
  and the counterbalance matrix (policy × episode × replicate). Report budget
  per LAN (D4).
- `rq2_relief_analysis.py` — per selected action: from the decision log's
  per-window evidence series, find when the targeted tier's `score_norm` falls
  back under its `*_threshold` → time-to-recovery; report whether relief is in
  the targeted tier.
- `rq2_node_minutes.py` — per tier per run: count **actual spawns** only — rows
  where `action_type="scale_up"` **and** `selected_action == tier` (rows with
  `selected_action="none"` are not spawns). Dedup rows by `(window_id, action_type)`
  (restart-robust). Pair spawns to removals per tier in **LIFO order** (matching
  the candidate-based removal `_pick_compute_scale_down_candidate` /
  `find_last_dynamic`): tier-specific `scale_down` rows (`action` =
  `"compute"`/`"storage"`) terminate that tier's most recent unpaired spawn;
  tier-ambiguous rows (`absent`/`absent_cleanup`/`reserve_loss`) carry **no
  tier** in the decision log and terminate **nothing** (their node is accounted
  live-until-run-end); a node never removed lives until run end. Σ(node count ×
  lifetime), normalised per unit of completed demand.

### T8 — documentation

- `elasticity_overview.md` — document the policy gate in the Thread 2
  description; link this plan in the implementation-plans list.
- `compute_scale_up.md` / `storage_scale_up.md` — note that in RQ2 arms the
  trigger path ends in `PolicyGate.select` before submission, and at most one
  action is emitted per window; the `dual` path is unchanged.
- `controller_telemetry_consumer.md` and
  `storage_persistent_reserve/phase_3_storage_persistent_reserve_activation_and_replenishment.md` —
  update their `evaluate_scale_up` references to note the facade is now the
  `dual` path only.

### T9 — validation

1. Models/verdicts parse; startup logs `SCALEUP_POLICY`, budget, margin.
2. **Dual equivalence:** with `SCALEUP_POLICY=dual`, the mediator behaves
   byte-identically to pre-RQ2 (facade path; RQ1 decision rows unchanged).
3. Fixed arms: configured tier submits when fired; suppressed tier never submits
   but its window/evidence advances identically (spot-check via DEBUG logs).
4. `bottleneck_aware`: classifier picks the higher `score_norm` tier; margin
   suppresses noise ties (tie → storage).
5. Budget: after `ACTION_BUDGET_PER_TIER` submissions of one tier, that tier
   returns no further actions; `budget_used`/`budget_cap`/`reason` logged.
6. One `scale_up` decision row per evaluated window with all RQ2 columns,
   including `selected="none"`, budget-exhausted, and cooldown windows; no row
   for empty (`domain_summary is None`) or busy windows.
7. Evidence series is continuous: `score_norm`/`threshold` present on every RQ2
   `scale_up` row.
8. **Fire-keyed scale-down protection (D7):** from the decision log's `*_fired`
   columns, verify no **cooldown-gated** `scale_down` row (`action`
   `ScaleDownComputeAlert`/`ScaleDownDataAlert`) for a tier appears within
   `SCALEDOWN_*_COOLDOWN_S` after a window where that tier's `*_fired=1`
   (including policy-suppressed fires). Absent-node rows are not cooldown-gated
   and are excluded from this check. Under `fixed_compute_first` in a data-bound
   episode, storage is never scaled down while storage is firing (the fire region
   around `TAU_DB_DOWN_MS`).
9. All arms behave identically on a synthetic flat (no-pressure) window:
   nothing fires, no commits, no submissions.
10. RQ1 artifacts (window log, delivery log) are still produced unchanged in RQ2
    runs. In RQ2-arm runs the `scale_up` rows are the new per-window 20-column
    rows; the non-scale-up rows (scale-down, absent, reserve, cancel) keep RQ1's
    `action_type`/`action` semantics within the 20-column format. Dual runs keep
    the legacy 5-column decision-log format byte-identical.

---

## 5. Measurement contract

- **Universe of RQ2 decisions:** `decision_log.csv` rows with
  `action_type="scale_up"` = one per evaluated window (a window with
  `domain_summary`, Thread 2 not busy). **Episode ground truth:**
  `phases_snapshot.json` (post-hoc join, D5). **Evidence:**
  `compute_score_norm`, `storage_score_norm`, and the per-tier `*_threshold`
  columns on each decision row (no window-log re-derivation).
- **Primary outcomes:**
  - Time to recover bottleneck-specific pressure = selected-action row time → the
    targeted tier's `score_norm` falls back under its `*_threshold` (relief tool).
  - Time to usable capacity = action time → first successful request on the new
    node. Extracted by `source/scripts/testing/analysis/rq2/extract_spawn_metrics.py`
    with `--tiers compute,storage --anchor decision`:
      - `--anchor decision` anchors TTFT/TFR on the decision-log `scale_up`
        action row (action time), not the controller-log "spawning" line —
        matched per LAN/tier in time order (`action_ts`, `action_to_spawn_s`).
      - `--tiers compute,storage` covers both tiers: compute spawns from
        `compute:` lines + `client_requests.csv` `backend_id` (TFR); storage
        spawns from `data:` lines — storage serves DB ops (no HTTP
        `backend_id`), so its TFR is empty and its usable-capacity signal is the
        first serving window (`ttft_s` from `per_node_stats.csv`
        `request_count>0`), with `rs_secondary_ready` in `elasticity_events.csv`
        as a readiness diagnostic.
  - p50/p95/p99 latency, failures, offered vs completed demand (existing
    collectors, unchanged).
  - Compute/storage node-minutes (node-minutes tool).
  - Number of scale actions per tier (decision-analysis tool).
  - Relief in targeted tier (relief tool).
- **Bottleneck validity:** `rq2_bottleneck_validation.py` confirms the induced
  episode (raw window-log signals) dominated the intended tier across all arms —
  the empirical check of the classifier proxy (D3).
- **Counterbalance check:** decision-analysis tool reports the policy × episode
  × replicate matrix so order/block effects are visible.
- **Caveats (documented):** fixed arms may exhaust their budget on the wrong tier
  and stop acting — expected treatment effect. In `bottleneck_aware`, once the
  dominant (classifier-selected) tier's budget is exhausted, **no** further
  action is emitted even if the other tier is firing and has budget (budget is
  per tier; visible via `*_budget_used`). Busy/empty windows produce no decision
  row (documented). Node-minutes uses decision-row timing (approximation).
  Budget is per LAN (D4). The decision-log format gains a header + additive
  columns from RQ2 (supersedes RQ1's 5-column no-header format; any RQ1 reader
  is updated in T4). Exactly-once delivery holds **only absent** controller
  restarts (i.e., not across a restart) — the analyzer dedups the RQ2 universe by
  `(window_id, action_type)` on `action_type="scale_up"`.

---

## 6. Dependencies

- **RQ1 implemented first** (hard prerequisite): event-preserving delivery,
  `window_id`, `_log_decision`, housekeeping ticker, window log.
- Existing packages only (`pydantic`, `csv`, `json`, stdlib). No new
  dependencies, no image rebuilds.

---

## 7. Documentation updates

- **New:** `docs/research_questions/v2/rq2/rq2_preparation.md` (this plan).
- `docs/operation/elasticy_manager/elasticity_overview.md`
- `docs/operation/elasticy_manager/scale_up/compute_scale_up.md`
- `docs/operation/elasticy_manager/scale_up/storage_scale_up.md`
- `docs/operation/telemetry/controller_side/controller_telemetry_consumer.md`
- `docs/operation/elasticy_manager/implementation/storage_persistent_reserve/phase_3_storage_persistent_reserve_activation_and_replenishment.md`
- `tese/Notes/thesis_overview.md` — untouched (scope unchanged).

---

## 8. Out of scope / follow-ups

- The RQ2 **experiment plan** (run matrix, episode durations/rates/mix
  calibration, replicate counts, blocking) — a separate step for the Experiment
  Designer, reusing the env regimes and phase files this plan provides.
- RQ3 readiness probe / pending-backend registry — separate RQ.
- Tier 1 / reserves / cross-region remain disabled for RQ2 runs per thesis §2.
