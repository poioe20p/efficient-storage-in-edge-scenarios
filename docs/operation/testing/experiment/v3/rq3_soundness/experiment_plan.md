# RQ3 Soundness — Readiness-Admission Fault Robustness (soundness half) — Plan

**Family:** reframed RQ3 (`usable-capacity realization through readiness-admission
coordination`), Family 5 (`rq3_soundness`). Family 4 (`v3/rq3_timing`,
completed 2026-09-09/10, 36 runs) measured the **liveness half**: under total
readiness-loss every admission rule eventually recovers except `event_only`
(H-T1 passed decisively — slow-share contrast, median 7.64 pp full / 28.01 pp
onset; cited, not re-measured here). Family 5 measures the **soundness half**:
whether the same rules realize **usable** capacity when the readiness channel
fails in three ways — **F1 lost claim** (measured; reused), **F2 premature
claim** (new, deterministic), **F3 semantic lie** (new).

**Pre-registered claims:** (a) no existing rule survives all three fault
families — `event_only` fails F1 (Family 4), F2 and F3; `hybrid` fails F2
(F3 defeat expected — descriptive where run; its claim-(a) component is F2);
`reconcile` fails F3 only; (b) `reconcile`'s F2 immunity is
channel-veridicality, not verification (F3 exposes it: the same probe passes
while the service fails); (c) the composed wake+verify rule (event wake-up +
probe-verified admission + bounded fallback) is robust to the two *channel*
faults F1/F2 at a priced speed cost — it does NOT survive F3, and no rule in
the design space does; (d) the push-vs-pull crossover is quantified in ONE
common damage currency (claim (d) is the analysis-design risk settled in §4).

**Status:** pre-registration drafted 2026-10-02. **No run has launched;
preflight P1 pending.** E stage is gated on the P1 lock file.

## 1. Objective

One question: *Can any existing admission rule (`event_only`, `hybrid`,
`reconcile`) deliver sound usable-capacity realization across all three
readiness-channel fault families, and where does push-trust vs pull-verification
cross over — quantified in one common damage currency?*

Deliverable: pre-registered verdicts H-S1…H-S3 (optional H-S4) computable from
campaign artifacts after a 3-run go/no-go preflight. Non-goals: re-measuring
liveness timing (Family 4), thesis text, rate ladders.

## 2. Reasonableness boundaries (hard)

- Only the two pre-specified app fault knobs are added; both **default-off and
  byte-identical on the off-path** (manifest hash + selftest enforce).
- Regime = Family-4 lock, unchanged: `compute_plateau` 600 s,
  `rate_per_client 2.0`, pure-compute (`service_pressure 1.0`),
  `EDGE_CPUS=0.12`. Single swept axis inside E = fault family / lead N; no
  ladder. Reused unchanged for currency comparability with the Family-4
  imports and the in-campaign F1 anchor; soundness is not
  saturation-dependent, so there is no rate sweep to justify.
- Faults deterministic; P1 re-validates against the **observed pre-fix
  signature**: run-wide fast-fail share 4.6–12 % and 162–428 `http=000` rows
  per run, admitted→first-success ≈10 s vs ≈0.8 s (discovery), 2–4
  non-gating `post-admission identity CHECK VIOLATION` warnings/run
  (readiness_gate.py `_process_confirmations`, ~line 303) — pre-2026-08-06
  ordering, fixed 2026-08-06 by synchronous `make_server` bind before event
  emission (app.py ~line 214; `_run_app_ready_probe` line 108). Those shares
  come from v2-era direct runs (different regime/denominator); the operative
  P1 floors are §5.
- A collapsed control (none-cell unhealthy, driver cancel_rate ≥5 %, quota
  mismatch, provenance missing, mid-run restart, mechanism absent) is
  **invalid** — never evidence, never chased.
- **Pre-registered adversarial / expected-damage campaign:** damage is the
  measured outcome, never a gate failure (base-doc no-collapse and
  no-benefit rules). Only harness/validity failures fail.
- Artificial-fault objection mitigated by precedent (the drop knob is itself a
  published injected fault) + boundary-test framing — no stop action.
- LAN-symmetry flag: damage-share asymmetry ≤3×.

## 3. Arms and cells

| Arm | Configuration | F2 premature | F3 semantic | F1 lost (ref.) |
| --- | --- | --- | --- | --- |
| `event_only` | `rq3rob_event_only.env` + `READINESS_EVENT_FALLBACK_S=130` (provably inert) | admits on claim → failures | admits → keeps failing | abandons all; 0 admitted (Family 4 H-T1) |
| `hybrid` | `rq3sat_direct.env` (fallback 20 s) | push-like (fallback is event-absence based → inert) | admits → keeps failing | recovers via fallback (Family 4 spawn→admit median ≈21.4 s) |
| `reconcile` | `rq3sat_discovery.env` (10 s poll) | waits for servability → immune | admits → keeps failing (predicate satisfied) | recovers via poll (≈17.1 s spawn→admit; sooner than hybrid 6/6) |
| `wake_verify` *(optional)* | `rq3snd_wake_verify.env` (direct base + fallback 20 s + mode probe) | probe-before-admission → bounded | still fails (probe passes; predicate satisfied) — as every rule | recovers via inherited fallback (descriptive; not gated) |

**Cells:** `none` (health floor, all arms); `premature2`, `premature5`,
`premature10` (F2 lead N ∈ {2, 5, 10} s); `semantic` (F3); `loss_all` (F1
in-campaign anchor: `reconcile` core, `event_only` optional).

All arms/env files byte-identical to Family 4 except the new deltas in §7.3.

## 4. Measurement contract — one common damage currency

### 4.1 Outcome classes (I2-honest; disjoint; priority order)

Classes, priority order (first match wins): `timeout` (driver `status=timeout`
— checked FIRST so a timeout's `http_status=000` encoding cannot be swallowed)
→ `000` (driver `status=completed` ∧ `http_status=000`: transport
fast-fail/connection failure) → `fail5xx` (`status=completed` ∧ HTTP ≥500,
app-layer) → `slow` (completed, latency_s > 1.0 s — Family-4 definition) →
`good` (completed, ≤1.0 s). Each row in exactly one class. Excluded from D and
from `offered`: `cancelled` (reported separately; driver-clean <5 %) and
`dropped` (reported separately). P0 selftest asserts these field encodings
against fixtures.

### 4.2 Damage share D (the currency)

For run (arm, cell, seed s): `U = 100 · (#timeout + #000 + #fail5xx + #slow)
/ #offered`, offered = the five classes (cancelled/dropped excluded).
**Decision statistic (per seed, paired by seed):
`D_s(arm, cell) = U(arm, cell, s) − U(arm, none, s)` (pp)** — same-seed
`none` subtraction cancels the shared demand transient; a component passes iff
≥2/3 seeds meet its threshold (§6). **Descriptive aggregate:
`D̄(arm, cell) = median over seeds [D_s]`** — reported and used as the input
to the crossover fits (§4.4). The D currency is the single primary **gated**
metric for F2 and F3; F1 keeps the same currency **descriptively** (anchor
check §4.4; Family-4 evidence cited, not re-gated) — this settles the
common-currency decision.

### 4.3 Fault windows (same artifacts: `client_requests.csv` + `phases_snapshot.json`)

- **F2 (per app spawn, pooled; anchored on servability, not on the event):**
  `[t_bind − N − 10 s, t_bind + 30 s]`, where `t_bind` = the app's first
  serve-capable (listening) timestamp and `N` = the cell's attested knob value
  (0 for `none`). The claim moment is `t_claim = t_bind − N` by construction;
  `EDGE_APP_READY_EVENT` may be 0 (reconcile arms) — windowing therefore
  needs no event artifact. Matched none-cell comparisons use the fault cell's
  N in the same formula. Knob-active runs log `READINESS_CLAIM` and
  `READINESS_BIND`; the measured deferral must satisfy
  `t_bind − t_claim ∈ [N−1, N+1] s` (attestation + analyzer check).
- **F3:** `[t_bind, min(t_bind + S, plateau_end)]` (lie window), clipped to
  plateau; S = 1200 s fixed (§7.3; spans any bind through plateau end). The
  clip means S is NOT a coverage lever — a shortfall is a schedule outcome
  handled by §5 R3(a).
- **F1:** plateau full window (Family-4 comparability).
- `t_bind` (all runs) and `t_claim` (knob-active runs) extraction is an
  analyzer-selftest requirement (P0); if a fault run's timestamps are not
  extractable → P1 fail.

### 4.4 Crossover (F2 leg) — pre-registered

`D_push(N)` = `D_s(event_only, prematureN)` — primary; `hybrid` secondary
(descriptive). `D_pull(N)` = `D_s(reconcile, prematureN)`.
- Pairwise per seed: `N*_s = min{N ∈ {2,5,10} : D_s(push,N) ≥ D_s(pull,N)}`;
  if no N satisfies → `N*_s = ∞` (right-censored). Campaign
  `N* = median over seeds (∞ counted as 11, just beyond the grid), with the
  censored count reported`; if ≥2/3 seeds are censored → band =
  push-advantage-through-N10. Bands: `N* ≤ 2` pull-dominates-immediately ·
  `2 < N* ≤ 10` crossover at `N*` · else push-advantage-through-N10.
- OLS fit `D̄(N) = β + α·N` per arm over the seed-median `D̄` (3 points/arm);
  `N*_fit = (β_pull − β_push)/(α_push − α_pull)` with seed-bootstrap 95 % CI,
  reported (marked extrapolated when outside [2, 10]; if the denominator is
  ≤0 or the fit is non-identifiable, `N*_fit` is reported as
  non-identifiable); the pairwise bands are the decision, the fit is
  reported.
- Growth gate: `α_push ≥ 0.5 pp/s` point estimate ∧ CI lower > 0.2 pp/s.
- Decision precedence (no overlap, pre-registered):
  1. `max over N of D̄(event_only, N) < 2 pp` → `stop_null` (no growth test,
     no N escalation);
  2. else compute the growth gate; if it fails and `max D̄ < 5 pp` →
     **sub-threshold report**;
  3. growth fails with `max D̄ ≥ 5 pp` → **growth-gate failure** recorded
     (H-S3 not met; descriptive bands still reported; not a stop);
  4. growth passes → report `N*`/band per above (any band, including the
     censored rule, counts as an `N*` report; H-S3 met).
- Calibration: the `{2, 5, 10}` grid is fixed a priori — **no ladder, no N
  escalation**. P1-R1 at N=10 calibrates measurability against the §5 gates;
  if the floors are unmet there, STOP and re-think the regime — never raise N.
- F1 anchor (descriptive, non-gated): `|D̄(reconcile, loss_all) −
  D̄(reconcile, premature10)| ≤ 10 pp` (seed-median aggregation, §4.2) as
  currency-consistency evidence. In-campaign anchor chosen over import: same
  seeds/regime/session ⇒ same instrument chain; Family-4 `event_only`/`hybrid`
  `loss_all` recomputed with the same currency = cross-campaign context,
  never gated.

### 4.5 Plan magnitudes & floors (base doc is relative — numbers live here)

- n = 3 per cell (seeds 6301–6303); every component decision = ≥2/3 seeds
  (base-doc reproducibility ≥2).
- Floors: ≥5,000 pooled / ≥1,000 per-LAN plateau offered+outcome rows; F2
  window (§4.3) ≥15 offered rows per LAN per spawn window; none-cell
  plateau-tail slow ≤2 pp ∧ bad ≤1 %; quota attest 0.12 requested and granted;
  driver cancel_rate <5 %.
- **None-cell breach policy (pre-registered):** a seed whose same-arm `none`
  run breaches the none floors (plateau-tail slow >2 pp or bad >1 % — Family 4
  saw 2/18 such transients at this regime) is excluded from that arm×cell
  contrast (`D_s` not computable) — documented, never chased, no rerun. A
  component remains evaluable iff ≥2/3 seeds for it stay assessable; if ≥2
  seeds are lost, report that component as **non-assessable (NA)** — recorded
  in the verdict table, distinct from `stop_null`; NA components count as
  unmet for their hypothesis. Harness-invalidity reruns (§5) are the only
  reruns this campaign allows.
- Gated F2/F3 thresholds: §6.

### 4.6 Base requirements mapping (`testing_requirements.md`)

| Req | Applies? | Plan magnitude / evidence |
| --- | --- | --- |
| Reproducibility | yes | n=3/cell, direction ≥2/3, seeds `RANDOM_SEED` fixed; campaign tables |
| B1/B2 benefit | **N/A** | pre-registered adversarial/no-benefit campaign — judged against own direction |
| M1 scale-up fires | yes | ≥1 add per LAN in pressure phase; controller log + quota snapshots |
| M2 usable capacity | **not gated** | admission-without-usability IS the phenomenon; report per-backend admitted→first-success (flag when admission never serves) |
| V1 bottleneck | yes | old-tier edge CPU median ≥60 % during plateau on P1-R1/R2 + E descriptive (telemetry CSVs) |
| I1 demand | yes | floors §4.5; F2 window floor ≥15/LAN |
| I2 classification | yes | §4.1 classes (timeout-first); denominators: `offered` for `U`/`D`; cancelled/dropped reported separately |
| D1 data-path | yes | 0× `NotPrimary`/`NotPrimaryOrSecondary`; no mechanism exception pre-registered (F3 503s are app-layer, not data-path) |
| D2 no restart/crash | yes | hard gate; knob must not restart the app (ordering inversion within one start) |
| D3 provenance | yes | `phases_snapshot.json` + `controller_env_snapshot.env` + fault attestation per run |
| Flags | report | telemetry continuity; LAN symmetry ≤3× on D |

### 4.7 Success criteria (numbered)

- SC-1 (P0): tag + manifest verify; analyzer selftest all-green; Family-4
  phase profile asserted (600 s / 2.0 / 1.0) in the frozen tree.
- SC-2 (P1-R1): §5 gates met. SC-3 (P1-R2): §5 gates met. SC-4 (P1-R3): §5
  gates met.
- SC-5 (E): H-S1 components ≥2/3 seeds each (event_only and hybrid show the
  F2 false-claim mechanism: in-window `000` ≥10/LAN per seed; event_only
  `D_s(semantic) ≥30 pp`; reconcile `D_s(semantic) ≥30 pp`).
- SC-6 (E): H-S2 contrast — reconcile at max lead (N=10): `D_s(F2) ≤2 pp` ∧
  `D_s(F3) ≥30 pp` (gap ≥28 pp), zero `CHECK VIOLATION` in F3 runs (≥2/3
  seeds each).
- SC-7 (E): H-S3 — §4.4 decision precedence executed; growth gate + `N*`
  band reported in the common currency.
- SC-8: base-requirement evidence present for every assessed run (hard gates
  pass; flags reported).

## 5. Stages — P0 → P1 (go/no-go) → E only after lock

**P0 — frozen runtime (no runs).**
1. Commit the §7 implementation on the branch (the tag must capture it; no
   post-tag edits to protected-surface files — the single declared
   `phases.json` restore in step 3 is manifest-recorded; any other fix
   requires a new commit + new tag).
2. Tag `rq3snd-preflight-<date>` at that commit + detached worktree
   `~/rq3snd_frozen`; verify `HEAD == tag`; after the step-3 restore and
   BEFORE step-4 manifest generation, `git status --porcelain` must show
   exactly one modification — `phases.json` (the single declared exception;
   source + hash in the manifest). Any other difference = STOP. (P0 tooling
   artifacts created afterwards — manifest/lock files — are recorded in the
   lock and exempt.)
3. Restore the Family-4 locked phase profile inside the frozen worktree
   `phases.json`, source rule (first available): (i) an archived
   `*_rq3tim_*/phases_snapshot.json` on the VM
   (`source/scripts/testing/metrics/`; any none-cell E run — phases identical
   across runs), (ii) the Family-4 frozen worktree `phases.json` at its
   recorded tag; neither found → STOP and escalate (never invent the
   profile). Assert `compute_plateau` 600 s / `rate_per_client` 2.0 /
   `service_pressure` 1.0 (mismatch = STOP); record the source path + hash.
4. `rq3snd_p0_01_prepare_tag.py` generates the protected-surface manifest
   (`rq3snd_protected_surface.json`: app.py, edge_server_process_state.py,
   control_events.py, readiness_gate.py, compute_node_manager.py, `phases.json`
   (post-restore), env deltas, launcher, analyzer) over the FINAL frozen tree
   (which differs from the tag ONLY by the declared `phases.json` restore) —
   no pre-restore hashing.
5. Static checks + analyzer selftest green (any red = STOP).

**P1 — go/no-go preflight (3 core runs + 1 optional).** Seeds 6351–6354
(distinct from E seeds). Runs R1–R3 (+ optional R3b), one checkpoint row each.

- **R1 — F2 reproduction (`event_only` × `premature10`, seed 6351).** Pass iff
  (a) transport-failure rows (`000`) inside `[t_bind − N, t_bind]` ≥10 per LAN
  (denominator: all offered rows in the window; expected routing share
  ≈1/pool_size);
  (b) run-wide `000` ≥0.3 % of offered ∧ ≥50 rows (floor set below the
  pre-fix observed count range 162–428 rows/run; the 4.6–12 % figure is
  regime/denominator-specific and is context only);
  (c) median admitted→first-**successful** flow ∈ [8, 12] s (≈ N);
  (d) ≥1 `CHECK VIOLATION` warning logged;
  (e) fault attestation present (`EDGE_READY_PREMATURE_S=10` in
  `rq3snd_fault_attestation.txt` + env snapshot);
  (f) measured claim→bind deferral ∈ [9, 11] s (`READINESS_CLAIM`/
  `READINESS_BIND` log lines).
- **R2 — F2 immunity (`reconcile` × `premature10`, seed 6352).** Pass iff
  (a) `000` rows ≤1 per run ∧ ≤0.2 % of offered;
  (b) zero successful flows attributed to the new backend before `t_bind`;
  (c) zero `CHECK VIOLATION`;
  (d) median `t_claim→first-successful flow` ∈ [10, 22] s (`t_claim =
  t_bind − N` by construction; = N + ≤ one poll cycle (10 s) + probe/margin
  (2 s)); descriptive sanity: median `t_admit→first flow` ∈ [0, 2] s;
  (e) admission source = `probe` (discovery scan; no event trust).
- **R3 — F3 signature (`event_only` × `semantic`, seed 6353).** Pass iff
  (a) lie window clipped to plateau covers ≥90 % of plateau (S = 1200 s
  fixed; the clip means S is not a lever, so a shortfall = late bind →
  DIAGNOSE: one same-config P1-R3 re-run; a repeated shortfall = STOP/re-spec
  — late binds are a schedule outcome, not a config);
  (b) among completed rows **attributed to faulted (lying) backends** inside
  the window (backend_id attribution; 503 carries the marker body +
  `X-Backend-ID`), ≥90 % are 5xx, with ≥15 such rows per LAN (volume floor);
  (c) transport `000` ≤1 % of window offered (channel stays up —
  distinguishes F3 from F2);
  (d) zero `CHECK VIOLATION` (the /ready predicate stays satisfied while the
  service fails).
- **R3b (optional, `reconcile` × `semantic`, seed 6354):** same gates as R3 —
  certifies "veridicality ≠ verification" mechanism directly.

**Kill rules (pre-agreed).** R1 fail → STOP (signature not reproducible;
re-design before any spend). R2 fail → structural claim broken; re-design; no
E. R3 fail → scope reduction (F3 leg descoped or re-specified; E only under an
amended plan). P1 reruns are allowed ONLY for harness invalidity or DIAGNOSE
verdicts — max 1 per R-run, pre-registered — never to chase a fail direction
or a none-cell breach (§4.5). Full matrix launches **only after R1 ∧ R2 pass
and R3 lands**; lock written as `rq3snd_preflight_lock.json` by
`readiness_robustness.py soundness-preflight`: exit 0 = lock written; exit
2 = DIAGNOSE (gates inconclusive; rerun allowance; still no E); exit 3 = STOP
(kill-rule fail, or a run invalid per the base gates and not repaired by its
single rerun; no E).

**E — evidence (exactly 45 core runs; ≤15 optional; E cap 60; after lock
file).** Blocks/seeds per
[`run_matrix.md`](run_matrix.md): per seed-block seeds 6301–6303, arm-rotation
counterbalanced; optional runs (≤15) appended after core, wall-time permitting.

**Analysis.** A1 lock; A2 damage tables (`U` and `D_s` by arm × fault × seed;
`D̄` aggregates; matched windows; class split; identity-warning counts;
adm→flow medians); A3 crossover fit + figure; A4 hypothesis verdicts (incl. NA
rows) + base-requirements table; A5 STOP-NULL / sub-threshold report when
triggered.

## 6. E-stage hypotheses (pre-registered; every gate has a number + rule)

- **H-S1 (headline: every existing rule fails a fault family).** Scope: core
  matrix, per-seed statistics, ≥2/3 seeds per component. Components:
  (i) `event_only` F2 false-claim mechanism exercised: per-seed in-window
  `000` ≥10/LAN (the false claim is admitted and traffic fails; damage
  magnitude reported here, cost side is H-S3); (ii) `hybrid` F2 same as (i);
  (iii) `event_only` `D_s(semantic) ≥30 pp`; (iv) `reconcile`
  `D_s(semantic) ≥30 pp`; (v) F1 `event_only` defeat cited from Family 4 (no
  re-gating). Pass = all components ≥2/3 seeds; reversed directions reported,
  never chased; components lost to none-floor breaches (≥2 seeds, §4.5) are
  recorded NA and count as unmet (not as `stop_null`). (The F2 mechanism
  components remain decidable even if the F2 damage curve is flat — no
  claim-(a) hole in the `stop_null` branch.)
- **H-S2 (veridicality ≠ verification).** Scope: reconcile, n=3, seeds
  6301–6303. Pass iff at max lead (N=10) `D_s(F2) ≤2 pp` ∧ `D_s(F3) ≥30 pp`
  (gap ≥28 pp, both ≥2/3 seeds) ∧ zero `CHECK VIOLATION` in F3 runs (≥2/3
  seeds). Optional wake_verify F3 cell (if run) supports mechanically.
- **H-S3 (quantified crossover in the common currency).** Scope: F2 grid,
  per-seed. Pass iff the §4.4 growth gate is met and an `N*` band is reported
  (any band, including ≥2/3-censored → push-advantage-through-N10);
  `stop_null`/sub-threshold/growth-failure branches recorded per the §4.4
  precedence. F1 anchor check §4.4 descriptive.
- **H-S4 (optional/secondary; excluded from primary verdicts).** wake_verify:
  `D_s(F2) ≤2 pp` ∧ `D_s(F3) ≥30 pp` ∧ healthy-cell cost ≤ +2 pp vs
  `event_only` (all ≥2/3 seeds; healthy-cell cost = per-seed
  `U(wake_verify, none, s) − U(event_only, none, s)`). F1 recovery is
  inherited from the fallback path (descriptive only; not gated). The price
  is reported as: (i) this healthy-cell cost and (ii) the admission-latency
  delta (median admitted→first-success, none cell, wake_verify − event_only;
  descriptive timing). Certifies claim (c) for the channel faults; absence is
  not a campaign failure.
- **Stop rules.** P1 kill rules (R1/R2 fail → STOP); `stop_null` only via the
  §4.4 precedence step 1; non-commensurable currency (D not computable for a
  class at P0/P1) → STOP before E spend; none-cell breach policy §4.5 (NA
  outcomes recorded distinct from `stop_null`; affected hypotheses count as
  unmet).

## 7. Implementation surface (specify only — nothing implemented yet)

### 7.1 App knobs — `source/docker/edge_server/source/app.py` (+ `edge_server_process_state.py`)

- **`EDGE_READY_PREMATURE_S`** (int s, default `0` = off; off-path behavior
  unchanged). N=0: the current code path (bind → probe thread → on Mongo-ping
  success `mark_app_ready()`). N>0: the readiness probe thread starts BEFORE
  bind; on Mongo-ping success `mark_app_ready()` runs (readiness flag set;
  `app_ready` event emitted when `EDGE_APP_READY_EVENT=1`), the app logs
  `READINESS_CLAIM`, then the process sleeps N s, then `make_server` binds and
  the app logs `READINESS_BIND`. Exactly one deferral per process start.
  During the gap the readiness state is true while no socket exists — the
  claim, not the channel, is what lies (`/ready` cannot answer while nothing
  is listening). Expected signatures: `000` fast-fails in `[t_claim, t_bind]`;
  admitted→first-success ≈N (event/direct arms); ≥1 `CHECK VIOLATION`
  (identity probe fails while unbound); both log lines present (analyzer
  extracts the measured deferral). Acceptance is signature-based (P1-R1), not
  path-based; exact log wording free, format fixed by analyzer needs.
- **`EDGE_READY_SEMANTIC_LIE_S`** (int s, default `0` = off). S>0: for S s
  counted from `t_bind`, every *workload* request (all paths except `/ready`,
  `/health`, `/drain` — there is no `/service` route; the catch-all covers the
  driver-exercised routes) returns a well-formed HTTP 503 (constant marker
  body; normal response path incl. `X-Backend-ID`) while `/ready` stays 200
  and TCP accepts — the app's own predicate stays satisfied, so the semantic
  contract is the lie. After `[t_bind, t_bind+S]`: normal. Window logged.
  Default S=1200 (locked; §7.3).
- **Pass-through:** `source/sdn_controller/elasticity/compute_node_manager.py`
  (~line 262, beside `-e EDGE_APP_READY_EVENT=...`): add
  `-e EDGE_READY_PREMATURE_S=…` and `-e EDGE_READY_SEMANTIC_LIE_S=…`.

### 7.2 Controller

- F2/F3: **no new knobs**; `CHECK VIOLATION` remains a WARNING (counted by
  analyzer). F1: reuse `READINESS_EVENT_DROP_MODE=all` (`rq3rob_loss_all.env`).
- **Optional `wake_verify`:** `readiness_gate.py` knob
  `READINESS_WAKE_VERIFY_MODE=off|probe` (default off). In `probe` mode (with
  the direct base + `READINESS_EVENT_FALLBACK_S=20`): an `app_ready` event no
  longer admits — it wakes a probe; admission occurs only after 1 successful
  `/ready` probe (`admit_source=wake_verify_probe`). No event within the
  fallback window → the existing fallback probe path applies (as in
  `hybrid`). Retry cadence and abandonment bounds unchanged; there is **no
  exhaustion-admission path** — the gate never admits unverified. Decisions
  logged `wake_verify=pass|fallback`. Optional arm; excluded from primary
  hypotheses.

### 7.3 Env deltas — `source/scripts/testing/controller_env_overrides/` (mirror `rq3rob_*` precedent)

`rq3snd_premature_lead2.env`, `rq3snd_premature_lead5.env`,
`rq3snd_premature_lead10.env` (`EDGE_READY_PREMATURE_S=2|5|10`);
`rq3snd_semantic.env` (`EDGE_READY_SEMANTIC_LIE_S=1200` fixed; it spans any
bind through plateau end — no config remedy exists for late-bind coverage,
see §5 R3(a));
`rq3snd_wake_verify.env` (`rq3sat_direct.env` + `READINESS_WAKE_VERIFY_MODE=probe`
+ `READINESS_EVENT_FALLBACK_S=20`). Arms reuse `rq3rob_event_only.env`,
`rq3sat_direct.env`, `rq3sat_discovery.env`, `rq3rob_loss_all.env`.

### 7.4 Scripts & analyzer (`rq3snd_*` mirroring Family 4)

- `rq3snd_p0_01_prepare_tag.py` — tag/manifest/protected-surface verify.
- `rq3snd_p0_02_analyzer_selftest.py` — shared harness + fixtures: `timeout`-
  first class order + 000 / 503 / slow-boundary classes, window extraction
  (`t_bind`; `t_claim` when the knob is active), lead fit, crossover.
- `rq3snd_p0_03_preflight.sh` — static checks (py_compile, bash -n, env merge
  proof, phase-profile assertion, quota, manifest).
- `rq3snd_p1_01_launch_run.sh` — `rq3snd_p1_01_launch_run.sh <arm> <fault>
  <label> <seed>`; asserts frozen phase profile (rate 2.0 / 600 s / sp 1.0),
  known arm/fault, unique label, quota 0.12; composes controller + app env;
  writes `rq3snd_fault_attestation.txt`; delegates to `run_experiment.sh
  --phases-config <frozen phases.json> --run-label <label>` with the
  Family-4 invocation parameter set taken from `rq3tim_p1_01_launch_run.sh`
  at BOTH the make-variable layer and the run_experiment flags (e.g.
  `CLIENTS=24`, `EDGE_CPUS=0.12`, `CURL_MAX_TIME=300`, `INFLIGHT_WINDOW=1024`,
  `DRAIN_S=30`, `STORAGE_CPUS=0.08`, `WAN_RTT_MS=185`,
  `TRAFFIC_DRIVER_MODE=open_loop`, `CONTENT_ITEMS=3000`, `USERS=100`,
  `DATA_SEED=42`, `EDGE_MONGO_READ_PREFERENCE=secondaryPreferred`,
  `EDGE_MONGO_MAX_POOL_SIZE=6`, `EDGE_FLOW_ISOLATION=1`,
  `VIP_DATA_PER_CONNECTION_FLOWS=1`, `SKIP_CLIENTS`/`SKIP_SEED`/`SKIP_SNAPSHOT`;
  illustrative, not exhaustive — the P0 diff of the launcher's FULL
  invocation (make + script layers) against the Family-4 launcher is the
  binding check) and `RANDOM_SEED=<seed>`. The launcher hash is
  manifest-protected; any deviation = STOP. No `--fault-plan` (faults are
  env-injected).
- Analyzer additions in `source/scripts/testing/analysis/rq3/
  readiness_robustness.py`: `soundness-preflight` (R1–R3 gates → lock JSON),
  `soundness-damage` (D tables, classes, windows, identity counts, adm→flow),
  `soundness-crossover` (fits, N*, bands, verdicts).

### 7.5 Phases

Canonical `source/scripts/testing/phases.json` edited **in place** — never a
duplicate. P0: restore the Family-4 locked profile inside the frozen worktree
from the §5-P0(3) source rule (archived `rq3tim` snapshot preferred; STOP if
none found); the manifest is generated **post-restore** (§5 P0(4)). At P1
lock: apply the same in-place restore to the repo canonical (it currently
holds a different five-phase profile). Run folders capture
`phases_snapshot.json` (existing). Launcher asserts the profile on every run.
The single-canonical rule applies to this campaign: rq3snd creates no new
phase files; pre-existing variant files elsewhere in the tree
(`phases_gap.json`, `phases_override/`) are not modified or referenced.

### 7.6 Docs

`docs/operation/testing/experiment/v3/rq3_soundness/` {this file,
`run_matrix.md`, `preflight_campaign.md`; `preflight_log.md` + `results.md` +
`post_run_analysis.md` at execution}; v3 README status row.

## 8. Cost and stop rules

- Runs: P1 3 (+1 optional) ≈ 2.0–2.7 h; E core 45 ≈ 30 h; optional ≤15
  ≈ ≤10 h; E cap (core+optional) ≤60 runs ≈ ≤40 h; campaign total (P1 ≤8
  runs, incl. the rerun allowance) ≤68 runs ≈ ≤46 h at ~40 min/run
  (wall-time table in `run_matrix.md`). No tie-break extension
  runs exist; seeds 6304–6306 are reserved for a plan amendment only. Config:
  hosts as Family 4 (`cloud-vm-rq3`), full reset between runs.
- STOP before E: R1 fail / R2 fail / currency not computable (P0 selftest or
  P1). `stop_null` only via the §4.4 precedence step 1 (max `D̄` < 2 pp);
  never N escalation. Artificial-fault risk: premise-accepted, mitigated, no
  stop action.

## 9. Validation before VM (no experiment executes during implementation)

Shared selftest (soundness fixtures included, all green) · py_compile /
pyflakes · `bash -n` · launcher negatives (wrong rate ↔ phases mismatch, unknown
fault, duplicate label) · env-merge proof (off-path byte-identical) ·
manifest/tag identity · phase-profile assertion.

## 10. Open decisions (both options + recommended default)

1. **`wake_verify` optional block (9 runs).** Default: include as optional
   after core, wall-time permitting (certifies claim (c); nothing primary
   depends on it). Alternative: drop; claims (a)–(b)–(d) unaffected.
2. **Repo canonical `phases.json` swap timing.** Default: at P1 lock, in place
   (single-canonical rule; rq3tim precedent). Alternative: coordinate first if
   the RQ1 campaign re-activates; frozen worktree keeps P1 self-contained.
3. **In-campaign F1 push anchor (`event_only` × `loss_all` ×3).** Default:
   optional (Family-4 recompute serves as context); run only if wall-time.

## 11. Changelog

- 2026-10-02 — pre-registration drafted (Family 5, soundness half). Decisions
  1–8 resolved in-file; open decisions carry recommended defaults. No runs.
- 2026-10-02 — review-gate revision: per-seed decision statistic `D_s`;
  F2 window re-anchored on `t_bind` (event-free); R1–R3 gates re-specified
  (denominators, floors, deferral check); wake_verify bounded without
  exhaustion-admission; P0 commit→tag→restore→manifest order fixed;
  S=1200 locked; seeds 6304–6306 reserved (no tie-break); cost arithmetic
  corrected; Family-4 recovery magnitudes updated (21.4 s / 17.1 s).
- 2026-10-03 — R1 attempt 1 (`rq3snd_premature10_event_only_90`, seed 6351)
  STOP: gates R1(c)/(f) failed (claim→bind 15.3–20.2 s vs N = 10). Root
  cause: blocking `socket.getfqdn` reverse lookup inside werkzeug's
  `make_server` stalls 5.3–10.3 s under the lab resolver (same stall in
  knob-off Family-4 archives). Instrument fix: scoped bind-lookup guard in
  `app.py` (display name only — no runtime semantics change); new commit
  `541fb22` + tag `rq3snd-preflight-20261003` + worktree `~/rq3snd_frozen2`;
  edge_server rebuilt `207b1f9e8f64` (smoke `make_server = 0.000 s`); gates
  unchanged; one permitted harness-invalidity rerun `_90r` (seed 6351).
- 2026-10-03 — **P1 preflight COMPLETE (lock)**: R1 `_90r` (seed 6351,
  6/6 gates; deferrals 10.01–10.02 s) ∧ R2 `_91` (6352, 5/5) ∧ R3 `_92`
  (6353, 4/4; coverage 1.0) all pass under the fixed instrument;
  `rq3snd_preflight_lock.json` written (S = 1200; seeds recorded); repo
  canonical `phases.json` restored in place (§7.5); optional R3b not run;
  E awaits go/no-go.
