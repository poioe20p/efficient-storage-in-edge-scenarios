# RQ3 (Final) — Readiness-Admission Coordination and Usable-Capacity Realization

> **Status:** consolidated final framing, 2026-09-10. Supersedes the framing in
> `rq3.md` and folds in `rq3_reframing_recommendation.md` plus the completed
> `rq3_timing` campaign (36/36 runs, `docs/operation/testing/experiment/v3/rq3_timing/`).
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
genuinely carry load (30,000–45,000 requests each).

**One sentence:** getting a ready server into use is the step that makes
capacity real — event-driven does it ~7 s faster, and that speed carries a
measured cost (visible slowdown when the signal is lost) that a fallback or a
poll removes.

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

## 3. Decomposition

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

## 4. Hypotheses

- **H3-mech (RQ3a).** Lifecycle-coupled admission realizes usable capacity
  sooner than reconciliation — by up to one poll period on the ready→admit
  interval, reaching the user end-to-end and smoothing the elasticity loop
  itself.
- **H-T1 (RQ3b, headline).** Under total event loss with thin headroom, an
  event-only arm degrades user service *visibly and boundedly* on the slow-share
  axis, while fallback and polling arms recover — a contrast of at least 5 pp
  on both the full plateau and the demand-onset window.
- **H3-rob (RQ3c).** Under selective loss, total loss, and restart, fallback
  and polling preserve admission of ready capacity; event-only does not.
- **H-T3 (health floor).** A no-fault run stays healthy (bad ≤ 1 %, plateau-tail
  slow ≤ 2 pp) — the baseline against which the fault cell's degradation is read.

## 5. Results

**RQ3a — mechanism (primary).** Lifecycle-coupled admission removes ~7 s of
readiness quantization (ready→admit 0.001 vs 6.984 s, d = −1.000, p < 0.0001,
every bind stratum). The differential reaches the user (~6 s sooner
end-to-end, p = 0.0005) and the elasticity loop (scale-decision → usable
capacity 2.17 vs 6.01 s, p = 0.0022). The cost scales with the poll period
(9.6 → 15.2 s for 10 s → 15 s polling).

**RQ3b — consequence (supporting).** Under total event loss at quota 0.12 /
rate 2.0, the event-only arm degrades to 8.3–14.4 % slow-share (onset window
29.7–39.0 % slow) while hybrid/reconcile recover to a ≤ 2 pp tail: a
full-plateau contrast of **6.2–10.9 pp (median 7.64 pp, MWU p = 0.004,
δ = 1.0)** and an onset contrast of **25–31 pp (median 28 pp)**, reproduced in
5/5 assessable blocks. The degradation is bounded (median 10.6 %, ceiling
25 %) and onset-transient-dominated.

**Usable capacity.** Admitted dynamic backends serve **30,000–45,000 successful
requests each** per control run — direct evidence that recovered capacity
carries load, not merely that it is admitted.

**RQ3c — robustness (supporting).** The robustness family (19 valid runs) shows
fallback and polling preserve admission under total loss, selective loss, and
restart, while event-only does not.

**H-T3 — health floor (mostly clean).** 16/18 no-fault runs meet both floors;
the two breaches (bad 1.19 % — 0.19 pp over; tail 4.29 % — a single 30-s
window) are stochastic transients of the same class seen in preflight. They do
not touch the contrast, which is computed *between* arms and therefore controls
for fault-independent instability.

**The combined law.** The coordination delay is **absorbed** while the event
path is healthy and headroom exists (zero harm at every tested load in the
healthy regime), and becomes a **visible, bounded, recoverable** cost when the
path fails and headroom is thin. The two arms of that conditional are the
healthy-regime null and the fault-regime H-T1.

## 6. The claim it supports

> Horizontal scale-out is not complete when a backend is created, or even when
> it becomes application-ready — it is complete only when the backend is
> admitted to the routing path and carries traffic. Readiness-admission
> coordination determines how quickly that completion happens and whether its
> delay becomes user-visible: lifecycle-coupled admission realizes capacity
> ~7 s sooner, and that advantage is priced against a measured, bounded
> robustness cost (~6–11 pp slow-share under total event loss) that fallback or
> polling eliminates.

## 7. Scope and boundaries

- The consequence is demonstrated for **total event loss** with constrained
  headroom and demand escalation; it is not evidence about selective loss,
  duplication, reordering, or controller restart (those are covered
  descriptively by the robustness family, not inferentially).
- The degradation is **bounded and transient**, not collapse; the direction is
  expected by construction (the event-only fallback is provably inert), so the
  contribution is the *quantified trade-off*, not the discovery that fallback
  helps.
- The none-cell stochastic humps show the static tier is near saturation at
  rate 2.0 independent of the fault; the between-arm contrast metric is what
  isolates the fault's effect.
