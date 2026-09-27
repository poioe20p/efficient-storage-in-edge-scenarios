# RQ3 (Final) — Readiness-Admission Coordination and Usable-Capacity Realization

> **Status:** consolidated final framing, 2026-09-10; the sole RQ3 framing
> document since 2026-09-26, when the former `rq3.md` was deleted and its
> final-relevant content absorbed here. Folds in
> `rq3_reframing_recommendation.md` plus the completed
> `rq3_timing` campaign (36/36 runs, `docs/operation/testing/experiment/v3/rq3_timing/`).
> **Revised 2026-09-25:** claim-discipline corrections after verification against the
> experiment records (restart claim, delay-vs-loss framing, transience wording,
> per-backend range source check — notes inline).
> **Revised 2026-09-26:** added the design-rationale section (§3.5 — fault
> choice and re-derivability framing) and the resource-relief,
> load-balancing, and capacity-accounting readings in §6; stopped/superseded
> experiment families are archive-only under `_DO_NOT_CITE` folder names.
> **Revised 2026-09-26 (b):** §5 now carries the consolidated outcome-expectation
> set (E-LB1–E-LB4, E-RO1–E-RO3); the per-backend volume claim was removed as
> uncitable, and the relief and delayed-admission phrasings were corrected.
> **Revised 2026-09-26 (c):** H-T2 ordering re-anchored (analysis-only) —
> tested and directionally supported (reconcile sooner; spawn→admit 6/6,
> spawn→first serve 5/6 + tie); the campaign pass remains false on H-T3 alone.
> **Companions:** `rq3_evaluation_conclusions.md` (mechanism evidence),
> `rq3_related_work.md`, `rq3_diagrams.md`.

## Summary (plain language)

A server is not useful just because it is started and ready — it is useful only
once the system actually starts sending it traffic. RQ3 asks how quickly a
ready server gets put to work, and whether it matters to users when that step
is slow or breaks.

Two ways to decide a server is ready: **event-driven** (use it the instant it
announces readiness — fast, but a lost announcement leaves it idle forever) and
**polling/fallback** (check periodically — slightly slower, but always finds it
eventually).

**What was found:** event-driven admission is ~7 s faster at putting a ready
server to work, with no user harm while nothing fails. But when the readiness
events are lost and spare capacity is tight, the event-only system visibly
hurts users (~8–14 % slow requests, far more at the demand spike), while the
fallback/polling systems recover and look healthy again. The recovered servers
demonstrably serve traffic for the remainder of the plateau (admission and
relief evidence; per-backend volume figures are not citable — see §6).

**One sentence:** getting a ready server into use is the step that makes
capacity real — event-driven does it ~7 s faster, but it has no self-healing:
when the signal is lost and headroom is thin, the lost admission (capacity dark)
becomes a visible, bounded cost that a fallback or a poll removes. The
seconds-level delay, where a recovery path exists, was not shown to be
user-visible in any tested regime.

## 1. The research question

> **During compute scale-out at the network edge, how does readiness-admission
> coordination affect the realization of usable capacity — and does the
> coordination delay become a transient service-quality cost when incumbent
> headroom is constrained and the lifecycle event source fails?**

Readiness-admission coordination is operationalized as two mechanisms over the
*same* verified-readiness state:

- **lifecycle-coupled admission** — admit the backend the moment its readiness
  event fires;
- **periodically reconciled admission** — admit it when a periodic check
  observes the same state.

The readiness criterion, the backend-selection function, the workload, and the
resource limits are held constant, so that coordination is the treatment.

## 2. Foundation and basis

Three premises, each grounded in the reviewed corpus:

1. **The premise (non-tautological).** *Elastic capacity has no operational
   value until the routing plane safely turns it into serving capacity.*
   Starting a server is not putting it to work; the interval between verified
   readiness and routing eligibility is the object of study, not a
   transport-preference contest.
2. **The gap.** The SDN load-balancing corpus optimises *which* backend to
   select given accurate state, treating readiness as established (Belgaum
   et al., 2020; Neghabi et al., 2018). Production systems mechanise the
   readiness→traffic interface as fixed platform behaviour.
   Within the corpus, no study
   isolates the post-readiness handoff under controlled invariants, and none
   tests whether delay at that handoff becomes a transient service-quality cost
   when headroom is constrained.
3. **The dichotomy.** Lifecycle-driven admission is *reactive* and has no
   self-healing property — a lost readiness event leaves a ready backend dark;
   periodic discovery is *proactive* and reconciles state every cycle.
   Coordination is therefore both a **latency** choice and a **reliability**
   choice, mirroring RQ1's push-versus-poll question at the admission end of
   the control loop.

### Provenance carried from the former `rq3.md` (deleted 2026-09-26)

The seed observation:

> "A new server can be fully started and still not serve a single request for
> tens of seconds, because the load balancer doesn't know it's ready."

The papers that ground the question:

| Paper | What it establishes | Strength | Role in the basis |
| --- | --- | --- | --- |
| **Yaseen (2025)** | Pull-based monitoring → "visibility gaps". | `DOCUMENTED` | Cross-domain thread, monitoring side. |
| **Podolskiy et al. (IaaS)** | Reactive autoscaling *"jeopardizes"* QoS under dynamic load across all three clouds. | `DOCUMENTED` (context) | The LB-discovery lag is one segment of the reactive-scaling lag. |

The cross-domain thread was reduced (2026-09-18): the service-discovery side
was retired with its sources (Pourghebleh et al. 2020 — verified but out of
scope; Achir et al. 2022 — unobtainable). What remains is the monitoring side:
Yaseen (2025), "visibility gaps" — no knowledge of backend **load**. RQ3
isolates the **readiness** member of that blind spot: the path from a backend
becoming application-ready to it being eligible for traffic.

Position in the control loop:

```text
Demand shift
  -> telemetry observation
  -> scaling decision
  -> capacity action
  -> backend readiness
  -> [RQ3] routing admission  <-  this RQ
  -> successful user request
```

## 3. Experimental apparatus and design

### 3.1 The two admission mechanisms

| Arm | Mechanism | Foundation |
| --- | --- | --- |
| **Lifecycle-coupled admission** | Event-driven inclusion: the component that owns the lifecycle (the controller that spawned the backend and verified readiness) immediately registers it into the routing pool. | Notify-on-complete, i.e. event-driven inclusion. Only possible when the lifecycle owner and the routing plane share an event path (the thesis's co-located apparatus). |
| **Periodically reconciled admission** | Pull/registry-based: the routing plane learns backend state by polling on a fixed period; admission is quantized to discovery cycles (up to one period of added delay). | The K8s-style endpoints/health-check status quo: admission is quantized to the reconciliation period. |

Reasons these two, specifically:

1. **Push/pull parallel with RQ1.** RQ1 studies event-preserving vs
   latest-state *polling* for **telemetry**; RQ3 applies the identical
   dichotomy to **readiness/admission** — one consistent thesis theme, *how
   state moves from "known" to "acted upon"*, across two interfaces.
2. **The co-location question made measurable.** Direct notification requires
   an event path between the component that observes readiness and the
   routing plane. Co-location makes that path *free* (in-process, no
   integration contract); in separated architectures it is possible but
   costs an explicit integration (webhook, bus, registry watch) and loses
   the self-healing property of polling — a lost notification leaves
   capacity dark with no re-check, which is why the lifecycle-coupled arm
   carries an event-absence fallback. Separated stacks therefore default to
   polling. The finding is not the trivial "direct beats discovery" but
   **how much quantization cost periodic discovery adds**, and whether the
   direct path is worth its integration and robustness trade-offs.

### 3.2 The readiness gate (implementation extension)

The mechanism this RQ studies did not exist in the pre-RQ3 controller: after
a spawn, the controller registered the backend into the routing pool
immediately — readiness was *assumed*, not verified. Testing the two
coordination mechanisms therefore required making admission conditional on
verified readiness and selectable per run:

- a **compute readiness gate** (`ReadinessGate`) with a **pending-backend
  registry** — a spawned backend is not admitted to the routing pool until
  `/ready` returns 200;
- **all pool admission delayed until readiness succeeds** — a backend that
  never becomes ready within `READINESS_PROBE_MAX_S` (120 s) is abandoned
  (full teardown, no leak);
- **direct admission suppressed in the discovery condition** — the poll
  cadence is the treatment, so no event or early registration can admit a
  backend ahead of the scan;
- **readiness admission decoupled from backend-selection policy, warm-lease
  priority, and ramp behaviour** — held constant (disabled) in all arms.

### 3.3 Measurement environment

Flow isolation: each measurement request gets a unique connection tuple and
the controller removes the corresponding VIP flow after the response, so
every measured request is a fresh backend-selection event — flow affinity
cannot masquerade as a readiness-admission effect. The driver is open-loop;
compute backends only.

Primary measurements: backend-ready → routing-admitted delay ·
admitted → first-flow delay · first-flow → first-successful-response delay ·
useful initial request share · transition-window latency and failures ·
scale-decision → usable-capacity time.

### 3.4 The campaigns

**Mechanism campaign (RQ3a evidence).** Direct vs discovery admission plus a
poll-period sensitivity cell; the complete evidence chain (three stages) is
in `docs/operation/testing/experiment/v2/rq3/` and `v3/rq3/` as summarised in
`rq3_evaluation_conclusions.md`.

**Timing campaign (RQ3b/RQ3c evidence, 36 runs, 2026-09-09/10).** Three
admission arms crossed with two fault cells at rate 2.0 and quota 0.12:

| Arm | Event path | Fallback | Under total event loss |
| --- | --- | --- | --- |
| `event_only` | admit on event | 130 s fallback — provably inert (`READINESS_PROBE_MAX_S` = 120 s) | zero admission, capacity stays dark |
| `hybrid` | admit on event | 20 s fallback reconcile | recovered via the fallback (spawn→admit ≈21 s) |
| `reconcile` | none — pure 10 s poll | the poll is the mechanism | delayed admission (≤ one poll period), immune by construction |

Fault cells: `none` (healthy baseline) and `loss_all` (the controller drops
every `app_ready` event, `READINESS_EVENT_DROP_MODE=all`). The fault is
uniform controller-side event loss — it exercises exactly the event channel
the lifecycle-coupled arm depends on; `reconcile` ignores the event channel
by design and is immune by construction. That asymmetry is deliberate: it
prices the timeliness-vs-robustness trade-off rather than handicapping any
arm. Evidence: `docs/operation/testing/experiment/v3/rq3_timing/`.

**Robustness family (stopped; archive only).** An exploratory family probed
selective loss and controller restart (19 valid runs; stopped by user
decision) and is retained as archive only — no claim rests on it
(`docs/operation/testing/experiment/v3/rq3_robustness_DO_NOT_CITE/`).

### 3.5 Design rationale: the fault choice and what the arms encode

**The fault is uniform; the asymmetry is the variable under test.** The
controller drops the `app_ready` event for every arm equally — a lost
notification is simply invisible to a mechanism that never consumes it.
The arms differ only in whether admission *depends* on the event:

- **`event_only`** — admission depends on the event and nothing re-checks:
  a lost edge is lost permanently (nothing re-emits it), so the backend
  never enters the pool. Its 130 s fallback sits beyond the 120 s probe
  bound, making it provably inert — this arm is the deliberate control for
  naive notification coupling with no recovery path.
- **`hybrid`** — the realistic event-driven design: the event is the fast
  path, and a bounded re-check timer (20 s) recovers a lost edge.
- **`reconcile`** — pure pull: admission re-reads full state every cycle
  (10 s) and ignores the event channel by design, so single-message loss
  cannot affect it.

**Why the fault targets the event channel.** A single dropped poll is
absorbed by the next cycle (bounded, self-healing); a lost edge with no
re-derivation is unrecoverable. A total poll-service outage is a different
threat model — a subsystem outage — and whole-system outages (controller
restart) were explored only in a stopped, archive-only family and are not
carried as evidence. Lost lifecycle notifications are the
mundane, silent failure class that production reconciliation loops exist
to absorb.

**The single factor across the three arms: can the system re-derive
readiness without the event?** `event_only` = no; `hybrid` and `reconcile`
= yes, in two styles (timer, poll). The outcome space collapses
accordingly: recovering arms show *delayed realization*; the non-deriving
arm shows *lost realization*. At the tested operating point the recovery
style was outcome-equivalent (both recovering arms restored admission
without visible harm); which style recovers faster is the untested H-T2
ordering and is not claimed.

## 4. Decomposition

- **RQ3a — Realization latency (mechanism).** How long after verified readiness
  does new capacity become routing-eligible and serve its first successful
  request, and how does that differ between lifecycle-coupled and periodically
  reconciled admission?
- **RQ3b — Operational consequence.** Under constrained headroom, does
  ready-but-dark capacity prolong incumbent pressure or degrade
  transition-window service quality?
- **RQ3c — Supporting robustness.** When the lifecycle event source is absent,
  does fallback reconciliation preserve eventual admission, and what QoE cost
  accompanies it?

## 5. Expectations and hypotheses

### 5.1 Outcome-level expectations (consolidated, official evidence)

| # | Expectation | Outcome (§6) |
| --- | --- | --- |
| E-LB1 | **Selectability** — event-driven admission makes a ready backend eligible for selection ~one poll period sooner | Met — 0.001 vs 6.984 s (d = −1.000, every bind stratum), replicated (~6.1–6.3 s per position); cost scales with the poll period (9.6 → 15.2 s for 10 → 15 s) |
| E-LB2 | **Handover quality** — once admitted, load reaches the new backend promptly and successfully (confirmatory: the handover path is not the treatment) | Met — post-fix admitted→first-flow ≈0.4–1.2 s on both arms; useful share 1.000; zero fast-fails (the pre-fix ~10 s lag was a fixed servability defect) |
| E-LB3 | **Redistribution latency** — the LB begins steering load to the new backend ~one poll period sooner (onset inherits the admission delay); the amount redistributed once admitted is unchanged | Met (onset; probe-consistent: incumbents reach 88 % vs 61.7 % CPU max under later admission); relief magnitude n.s. between arms (p = 0.209) |
| E-LB4 | **Fault redistribution** — under total event loss, the non-recovering arm never redistributes; recovering arms redistribute after a bounded delay | Met — 0 admitted / 0 new-backend successes, 6/6 blocks; recovering arms delayed (hybrid ≈21 s; reconcile ≤ one poll period); user cost +7.64 pp median slow-share (+28 pp onset) |
| E-RO1 | **Loop closure** — scale-decision → usable capacity arrives ~one poll period sooner, scaling with the poll period | Met — 2.17 vs 6.01 s (p = 0.0022, d = −1.000); replicated (12.48 vs 15.55 s, δ = −0.878) |
| E-RO2 | **Usable-capacity realization** — provisioning ≠ usable; under fault without a recovery path the new capacity realizes zero | Met — zero admission / zero new-backend successes in 6/6 blocks; recovered capacity serves and relief completes; per-backend volume totals are not citable (see §6) |
| E-RO3 | **Relief completes** — after delayed admission, incumbent relief completes | Met — plateau tails ≤ 2 pp in 5/6 assessable blocks (the excluded block's control tail spiked to 4.08 %) |

Two earlier candidates are **not carried**: boundedness is reported as a
qualifier inside the H-T1 claim (affected-arm median 10.6 %, pre-registered
ceiling 25 %), and controller-restart behaviour was probed only in a stopped,
archive-only family — it is outside the evaluated scope (scope line only, no
claim).

### 5.2 Pre-registered timing-campaign hypotheses

- **H-T1 (headline) — met.** Under total event loss with thin headroom the
  event-only arm degrades visibly and boundedly (median contrast 7.64 pp full
  plateau / 28 pp onset; boundedness median 10.6 %, ceiling 25 %), while the
  recovering arms stay healthy.
- **H-T2 — met on the re-anchored metric (analysis-only, 2026-09-26).** Relief
  completes for hybrid ∧ reconcile in 5/6 blocks; with the relief clock
  anchored at the first relief backend's spawn, reconcile recovers sooner than
  hybrid — spawn→admit in 6/6 blocks (median 17.1 vs 21.4 s), spawn→first
  serve in 5/6 plus one sub-second tie (median 17.8 vs 22.1 s) — supporting the
  plan's direction; the slow-rate relief-completion timing remains
  non-separating.
- **H-T3 — mostly clean (16/18).** Two stochastic breaches of the health
  floors (bad 1.19 %; a single tail window at 4.29 %), same class as preflight
  transients; they do not touch the between-arm contrast.

The campaign's pre-registered conjunction (H-T1 ∧ H-T2 ∧ H-T3) was **not
fully met** (overall pass = false, now gated on H-T3 alone): H-T1 met; H-T2
met on the re-anchored ordering; H-T3 marginal (16/18). The consequence claim
rests on H-T1, with H-T2's ordering directionally supported and its
relief-completion component met.

## 6. Results

**RQ3a — mechanism (primary).** Lifecycle-coupled admission removes ~7 s of
readiness quantization (ready→admit 0.001 vs 6.984 s, d = −1.000, p < 0.0001,
every bind stratum). The differential reaches the user (~6 s sooner
end-to-end, p = 0.0005) and the elasticity loop (scale-decision → usable
capacity 2.17 vs 6.01 s, p = 0.0022). The cost scales with the poll period
(9.6 → 15.2 s for 10 s → 15 s polling). At the resource level, scale-up
produced old-tier CPU relief ≥10 pp on the majority of admissions in **both**
arms (direct 8/14, discovery 11/14; per-run medians 16.0 vs 19.3 pp; T_proc
−60 to −74 %), while the between-arm relief magnitudes were not significantly
different (p = 0.209) and user QoE was unaffected in that regime (v3
compute-saturation campaign, 14 runs, n=7/arm).

**RQ3b — consequence (supporting).** Under total event loss at quota 0.12 /
rate 2.0, the event-only arm degrades to 8.3–14.4 % slow-share (onset window
29.7–39.0 % slow) while hybrid/reconcile recover to ≤ 2 pp tails (5/6
assessable blocks; the excluded block's control tail spiked to 4.08 %): a
full-plateau contrast of **6.2–10.9 pp (median 7.64 pp, MWU p = 0.004,
δ = 1.0)** and an onset contrast of **25–31 pp (median 28 pp)**, reproduced in
5/5 assessable blocks. The degradation is bounded (median 10.6 %, ceiling
25 %) and predominantly onset-concentrated — onset median 28 pp vs
full-plateau 7.64 pp; block 2 shows a residual event-only tail of 11.4 %, so
transience is not block-uniform. What the contrast prices is **lost
admission**, not delay: the event-only arm admits zero backends and records
32–35 abandoned candidates per block (its fallback is provably inert), while
the recovering arms' admission was merely delayed (hybrid ≈21 s via its
probe-fallback path; reconcile within its 10 s poll; on the re-anchored
relief clock reconcile recovers sooner — spawn→admit 6/6, spawn→first serve
5/6 + tie) and produced no visible harm.

**Usable capacity.** Admitted dynamic backends serve traffic for the remainder
of the plateau — each admitted backend serves, and incumbent relief completes
in 5/6 blocks, so recovered capacity serves rather than merely being admitted.
*Source check completed (2026-09-26): the per-backend range "30,000–45,000
successful requests each" appears in no retained record and is inconsistent
with the recorded campaign volume (≈57.2–57.4k pooled requests per plateau run,
≈28.7k per LAN across all backends) — **do not cite**. The citable record is
that the recovering arms admit and serve backends (4–6 per block via the 20 s
probe fallback; 4–5 via the 10 s poll, no abandoned candidates) while
event-only achieves zero new-backend successes (6/6 blocks).*

**RQ3c — robustness (not carried).** An exploratory robustness family (19
valid runs; stopped by user decision) probed selective loss and controller
restart, but it is archive-only and no claim rests on it
(`…rq3_robustness_DO_NOT_CITE/`). The timing campaign's
pre-registered conjunction (H-T1 ∧ H-T2 ∧ H-T3) was **not** met: H-T1 is met
and H-T2's ordering component was re-anchored (analysis-only, 2026-09-26) and
is directionally supported — reconcile recovers sooner than hybrid (5/6
blocks plus one sub-second tie); H-T3 remains marginal (16/18). The claim
therefore rests on H-T1, with H-T2 met on its re-anchored ordering and
relief-completion components.

**H-T3 — health floor (mostly clean).** 16/18 no-fault runs meet both floors;
the two breaches (bad 1.19 % — 0.19 pp over; tail 4.29 % — a single 30-s
window) are stochastic transients of the same class seen in preflight. They do
not touch the contrast, which is computed *between* arms and therefore controls
for fault-independent instability.

**The combined law.** The coordination delay is **absorbed** while the event
path is healthy and headroom exists (zero harm at every tested load in the
healthy regime); when the event path fails **without a recovery path** and
headroom is thin, the **loss of admission** (capacity staying dark) becomes a
**visible, bounded, recoverable** cost. The two arms of that conditional are the
healthy-regime null and the fault-regime H-T1.

**Load-balancing reading.** At the routing plane, admission is the gate on
the eligible set's membership, and the selection function is held fixed.
The fault cell therefore contrasts **lost redistribution** (`event_only`:
the set never changes; load stays entirely on the incumbents although the
capacity is ready and running) with **delayed redistribution** (recovering
arms: hybrid ≈21 s; reconcile ≤ one poll period — ordering untested — then
normal). In the healthy regime the same gate
shifts redistribution onset by the ~7 s quantization, which the incumbent
relief metrics register at the resource level even when users cannot.
With flow isolation every measured request is a fresh selection, so
membership changes appear in the distribution at request granularity;
where flows are pinned, admission affects only new flows.

**Capacity accounting.** A platform that counts ready backends as capacity
would have read the `event_only` fault cell as healthy while delivering
zero new serving capacity; scale-out completion is fully recorded only at
first successful traffic (approved → carrying traffic).

## 7. The claim it supports

> Horizontal scale-out is not complete when a backend is created, or even when
> it becomes application-ready — it is complete only when the backend is
> admitted to the routing path and carries traffic. Readiness-admission
> coordination determines how quickly that completion happens — lifecycle-coupled
> admission realizes capacity ~7 s sooner — and what it costs when it fails:
> without a recovery path, total event loss under thin headroom produces a
> bounded slowdown (~6–11 pp median slow-share; affected-arm median 10.6 %,
> pre-registered ceiling 25 %) that fallback or polling eliminates; the
> seconds-level delay, where a recovery path exists, was not shown to be
> user-visible in any tested regime.

## 8. Scope and boundaries

- The consequence is demonstrated for **total event loss** with constrained
  headroom and demand escalation; it is not evidence about selective loss,
  duplication, or reordering. Controller restart is outside the tested scope.
- The degradation is **bounded** (median 10.6 %, ceiling 25 %) and
  **predominantly onset-concentrated** — not block-uniformly transient (block 2
  shows a residual 11.4 % tail) — and not a collapse; the direction is expected
  by construction (the event-only fallback is provably inert), so the
  contribution is the *quantified trade-off*, not the discovery that fallback
  helps.
- The none-cell stochastic humps show the static tier is near saturation at
  rate 2.0 independent of the fault; the between-arm contrast metric is what
  isolates the fault's effect.
- Limited to **compute** backends. Storage-replica readiness is a distinct
  MongoDB SECONDARY event and is out of scope; the storage scale-up extension
  was evaluated in a closed preflight with **no measurable benefit** at the
  locked read-write-mix configuration and is not carried forward.
- Does **not** compare the controller with Kubernetes, HAProxy, or another
  external load balancer; only the readiness-admission mechanism is isolated.
- Warm-lease priority and slow-start ramps are **held constant** (disabled in
  all arms), so only the readiness-admission mechanism varies. Any
  between-arm difference is direct evidence that the admission interface is
  consequential.

## 9. Papers to cite and cross-references

**Related work (Ch.2):** Yaseen (2025) · Podolskiy et al. (IaaS) — the
evaluation-practice positioning and the to-verify list live in
`rq3_related_work.md`.

**Companions:** `rq3_evaluation_conclusions.md` (mechanism evidence and
critical review), `rq3_related_work.md`, `rq3_diagrams.md`.

**Evidence folders:** mechanism campaigns `docs/operation/testing/experiment/v2/rq3/`
and `docs/operation/testing/experiment/v3/rq3/`; timing campaign
`docs/operation/testing/experiment/v3/rq3_timing/` (`results.md`,
`post_run_analysis.md`, `analysis/timing_campaign.json`). Archive only (never
cited): `docs/operation/testing/experiment/v3/rq3_robustness_DO_NOT_CITE/`.

**Thesis map:** `tese/Notes/purpose_evidence_map.md` (I3, P6) ·
`tese/Notes/thesis_overview.md` §6-RQ3 ·
`tese/literature_review/global_literature_review.md` §5.5.
