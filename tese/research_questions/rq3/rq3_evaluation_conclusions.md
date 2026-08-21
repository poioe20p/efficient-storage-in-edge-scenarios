# RQ3 — Evaluation Conclusions & Critical Review

> **Status:** 2026-08-21 · conclusions from the completed RQ3 evaluation (v3 compute-saturation evidence folded in, §3.2).
> **Companion to:** `rq3.md` (research-question framing / provenance).
> **Evidence:** `docs/operation/testing/experiment/v2/rq3/` — `results.md` (§2–8),
> `post_run_analysis.md` (§3–6), `run_matrix.md` (§3–6),
> `rq3_campaign_summary.csv`, `rq3_probe_summary.csv`,
> `graphs/campaign_fixed/*` (`ready_to_admit_stratified.png`,
> `spawn_to_first_stratified.png`, `campaign_stratified_per_backend.csv`).
> **Thesis map:** `tese/Notes/thesis_overview.md` §6-RQ3.

---

## 1. Conclusions (evidence-based)

> **Storage extension (2026-08-08, closed):** a storage-replica scale-up
> extension was evaluated in a 4-run preflight at the locked read-write-mix
> config (P1/P2/P1-fix/P2-fix, seeds 3001, both arms + both baseline rates).
> SG-4 benefit was **null** in the 3 honest runs (P2 +3.6 %, P1-fix +0.6 %,
> P2-fix −1.9 %); P1's +38.2 % was a proven early-plateau transient-spike
> artifact. Replicas did offload reads (R-stor-3 passed) but never produced
> user-visible latency/CPU relief. Per the pre-registered RQ3-storage-3 rule,
> storage should **not** scale up under this workload — the extension is
> **not carried forward**. The compute RQ3 verdict below is unaffected.

### 1.0 Headline results at a glance

| Result | Finding |
|---|---|
| **Mechanism** (ready → admission) | Direct admits ~7 s sooner (0.001 vs 6.984 s), full separation (d = −1.000), every bind stratum |
| **End-to-end** (spawn → first success) | Direct serves a client ~6 s sooner on average (11.272 vs 17.698 s, p = 0.0005, d = −0.594); within-stratum d = −1.000 |
| **Orchestration** (scale-decision → usable capacity, rate-12 cell) | Direct reaches usable capacity ~3.8 s sooner (2.17 vs 6.01 s, full separation, p = 0.0022, d = −1.000) |
| **Sensitivity** (10 s → 15 s poll) | Quantization scales with the poll period (9.6 → 15.2 s) — the mechanism is the poll, not the host |
| **User-harm consequence** (gap-window timeout/failure) | Null — 0.000 in every arm at every load tested (pre-registered-acceptable) |

### 1.1 What was evaluated

Three evaluation stages, all on `cloud-vm-rq3`, open-loop driver, flow-isolation
mode, same readiness probe/cost/weights/pool/workload in both arms:

| Stage | Runs | Purpose | Outcome |
|---|---|---|---|
| v2 campaign (2026-08-04/05) | 18 + 1 | Pre-registered direct vs discovery vs discovery_15 | Timing claim confirmed but **direct arm contaminated** by a harness http=000 artifact |
| Boundary probe (2026-08-05/06) | 17 valid + rate-12 cell n=6/arm | Consequence under load | Consequence null at every load; timing persists; rate-12 scale→first p = 0.0022 |
| **Fixed-image campaign (2026-08-06)** | **12 (n=6/arm)** | Re-run with servability fix | **Definitive**: artifact gone; mechanism + end-to-end both significant |

The fixed-image campaign (seeds 2310–2321, `rq3_camp_{direct,disc}_{1..6}`,
image `638e3efdcdc5`, default `EDGE_CPUS=0.30`, rate 3.0) is the primary basis
for the thesis conclusions. All 12 runs exit 0, non-void, **0×http=000**,
`useful_share=1.000`, flow-validation A/B/C/D pass (47 backends).

### 1.2 Primary result — the mechanism (readiness → admission)

Time from a backend being *actually ready* (edge `app ready` log) to the
controller *admitting* it. Bind-independent by construction (measured after
bind). Per-backend medians (exact MWU p, Cliff's d):

| Stratum | direct (n) | discovery (n) | p | d |
|---|---|---|---|---|
| all | **0.001 s** (23) | **6.984 s** (24) | <0.0001 | −1.000 |
| fast-bind (<1 s) | 0.001 s (7) | 7.305 s (7) | 0.0006 | −1.000 |
| slow-bind (≥5 s) | 0.000 s (16) | 6.768 s (17) | <0.0001 | −1.000 |

**Conclusion 1 (mechanism).** Event-driven readiness notification admits a
ready backend essentially immediately, while a 10 s discovery period leaves
it dark for up to one poll period — **median ~7 s** of readiness-quantization
removed, full separation, d = −1.000 in every stratum. The quantization cost
also scales with the poll period (9.6 → 15.2 s for 10 s → 15 s polling,
campaign sensitivity cell), confirming the mechanism is the poll, not the
host.

### 1.3 End-to-end result (spawn → first success)

User-visible time from spawn decision to the first 2xx served by the new
backend, **controlled for the measured container-bind stall** (stratified):

| Stratum | direct (n) | discovery (n) | p | d |
|---|---|---|---|---|
| all | 11.272 s (23) | 17.698 s (24) | 0.0005 | −0.594 |
| fast-bind | **1.687 s** (7) | **9.164 s** (7) | 0.0006 | −1.000 |
| slow-bind | 11.461 s (16) | 18.282 s (17) | <0.0001 | −1.000 |

**Conclusion 2 (end-to-end).** The admission differential reaches the user:
direct serves a client **~6 s sooner on average** (pooled), and the
differential is perfect within both bind strata (fast-bind 1.7 vs 9.2 s;
slow-bind 11.5 vs 18.3 s). The absolute numbers are dominated by a shared
~10 s container-bind startup cost; the *differential* is the RQ3 signal.

**Conclusion 2a (orchestration smoothness).** The differential also reaches
the elasticity loop itself. At the high-load rate-12 cell (n=6/arm),
scale-decision → usable capacity is **2.17 s direct vs 6.01 s discovery**
(full separation, exact MWU p = 0.0022, Cliff's d = −1.000). Under discovery
the system runs up to one poll period with *spawned-but-dark* capacity — a
measurable orchestration-responsiveness cost (the control loop acts on
stale capacity for one quantization interval), distinct from the
user-facing timing cost of Conclusion 2.

### 1.4 Validity

- 0×http=000 and `useful_share=1.000` in all 47 backends — the direct-arm
  handover artifact (162–428 fast-fails/run in the pre-fix campaign, driven by
  the app firing readiness before its HTTP server bound) is **eliminated**.
- Flow-validation A/B/C/D pass on every run (coverage ≥ 0.97, reuse ≤ 1 %).
- All 12 runs non-void; per-LAN admission counts satisfied.

### 1.5 The user-harm consequence is null (stated plainly)

What is null is specifically the **user-facing harm during the transition**.
The pre-registered gap-window old-backend `timeout_rate`/`failure_rate` is
**0.000 in every arm at every load tested** — the campaign and probe evidence
are enumerated below. This is one of three consequence axes, and it is the
only null one — the user-timing consequence (Conclusion 2) and the
orchestration-smoothness consequence (Conclusion 2a) are both significant.

- campaign at the canonical rate 3.0 req/s/client (n=6/arm);
- boundary probe rates 8 / 12 / 25 req/s/client (old-backend CPU up to ~88 %,
  with the discovery arm carrying the ceiling load);
- the rate-12 cell extended to n=6/arm (6×6 all-zero runs, p = 1.000).

The null is **not dismissible as under-saturation**: the probe pushed old
backends to ~88 % CPU and still produced zero gap-window timeouts. The
practical limit is the open-loop driver's own delivery ceiling
(~100–120 req/s aggregate), beyond which the driver collapses before any
gap-window consequence appears. The platform's reserve capacity absorbs the
transition on this testbed; there is no between-arm service-quality
difference in the gap window. This is a pre-registered-acceptable null, not
a failure of the treatment.

**Why timing still matters (argued, not separately demonstrated):**
time-to-usable-capacity is a first-order auto-scaling metric; the quantization
is a tunable design cost the direct mechanism removes; and the benefit is a
resilience margin that pays off when headroom disappears — in a deployment
with weaker/fewer incumbent backends or higher relative load, the same ~7 s
quantization would convert into user-visible degradation.

### 1.6 The container-bind stall (shared infra cost, documented)

The ~10 s container startup stall is **not** the mechanism and not the
Werkzeug dev server. Instrumented `bind-timing` logs show it is in the raw
`socket.bind()`/`listen()` path inside `make_server`
(`getaddrinfo=0.000 s`, `importlib.metadata=0.001 s`,
`make_server(bind+listen)=10.03–10.04 s` for slow backends). It manifests only
during active runs at spawn time (kernel-level stall under network-namespace
churn), intermittently (~50–75 % of spawns), randomly across backends (statics
too), **equally in both arms**. No cheap harness knob removes it
(`EDGE_CPUS=1.0` was tried and rejected — it suppresses compute scale-up,
voiding the run). It is treated as a **measured covariate** (bind time per
backend from the logs) and controlled by stratification; it cancels in the
between-arm difference.

### 1.7 What is demonstrated vs argued (honest claim boundary)

**Demonstrated:**
1. Readiness quantization is ~7 s (up to the 10 s poll period) and scales with
   the poll period — decisive, all strata.
2. The differential reaches the user end-to-end (~6 s sooner, significant,
   perfect within strata).
3. The differential reaches the orchestration loop (scale-decision → usable
   capacity 2.17 vs 6.01 s at rate-12, full separation, p = 0.0022,
   d = −1.000) — the control loop acts on dark capacity for up to one poll
   period under discovery.
4. No **user-harm** consequence on this platform up to its load ceiling.
5. The pre-fix direct-arm http=000 artifact was a harness bug, now fixed and
   verified absent.

**Argued (mechanism-based, not separately demonstrated):** in a deployment
with less headroom (weaker/fewer incumbent backends, higher relative load),
the same ~7 s quantization would convert into user-visible degradation, which
event-driven admission would avoid. The testbed's driver ceiling (and the
platform's resilience) precludes observing that conversion here.

---

## 2. Review of the conclusions (critical assessment)

### 2.1 Genuine strengths

1. **The mechanism claim is decisive and robust** — 0.001 vs ~7 s, p < 0.0001,
   d = −1.000 in every stratum, over 12 independent runs. Not fragile.
2. **The end-to-end claim now holds** — the pre-fix campaign had this at
   p = 0.13 (NS); the fixed-image campaign is p = 0.0005 pooled and d = −1.0
   within strata. This is the single largest improvement over the earlier
   evidence.
3. **Validity is impeccable** — 0×000, `useful_share=1.000`, flow-valid in all
   47 backends; the artifact is gone at the source and provably so.
4. **The confounder is handled honestly** — the bind stall is measured,
   documented, and controlled statistically, not hidden or hand-waved.

### 2.2 Attack surfaces / weaknesses (what a critical examiner will probe)

1. **The "7000×" framing is a liability if led with.** 0.001 vs 6.98 s is a
   ratio of a near-zero to a poll interval. Frame as *"~7 s faster
   (eliminates the poll-period quantization)"*; use the multiplier only as a
   parenthetical.
2. **The bind stall is characterized, not explained.** We proved the raw
   `bind()/listen()` path and its conditions, but not *why* the kernel stalls
   ~10 s, and we could not fix it. Counter: it is measured, both arms, and the
   differential persists in both strata — but the thesis must preempt this in
   a limitations subsection.
3. **The user-harm consequence is null.** A reader will ask: *"if there is no
   user harm, why does admission timing matter?"* Answer with the two
   measured consequences first — the user-timing differential (~6 s sooner,
   p = 0.0005) and the decisive orchestration-smoothness differential
   (scale→first 2.17 vs 6.01 s, d = −1.000) — then state plainly that only
   the **transition-window user-harm** axis is null on this resilient
   testbed. The remaining *argued* (not separately demonstrated) step is that
   the ~7 s quantization would convert into user-visible degradation where
   headroom disappears (weaker/fewer incumbents, higher relative load).
4. **Absolute end-to-end numbers are bind-dominated.** Present the
   differential (and the strata), not the absolutes (11 vs 18 s), as the
   headline.
5. **Modest n** — n=6/arm; fast-bind stratum n=7/arm. Sufficient for the
   effect sizes (already p < 0.001), but avoid over-claiming stratum-level
   precision.
6. **Single-host testbed.** Absolute timings are environment-specific; only
   the mechanism (event vs poll) generalizes in principle. One-limitation
   line is required.
7. **Cross-RQ contamination** (outside RQ3): the same stall intermittently
   contaminates RQ1/RQ2; their campaigns need the fixed image before their
   numbers are final.

### 2.3 Presentation disciplines required

1. Lead with **"~7 s faster"**, never "57×/7000×".
2. Order: mechanism (`ready→admit`) → end-to-end (`spawn→first`, stratified) →
   orchestration consequence (`scale→first`, rate-12) → null user-harm
   consequence stated as a finding with the "why timing matters" argument.
3. Dedicated limitations subsection for the bind stall (measured,
   instrumented, both-arms, controlled-for) with appendix evidence.
4. One-line single-host generalizability caveat.
5. Do not let old-doc "57×/90×" artifact-era language leak into the thesis
   without the fix context.

### 2.4 Verdict

**Strong enough for a Master's thesis — yes, with the disciplines in §2.3
enforced.** The RQ3 contribution is a clean, controlled, statistically
decisive mechanism result (event-driven readiness admission removes up to a
poll period of admission quantization, ~7 s median), a now-significant
end-to-end differential, and honest limitation handling. It is **not a
dramatic result**; the two things most likely to draw examiner challenge are
the **null consequence** (answer it head-on) and the **bind stall** (own it in
limitations). Written with those, RQ3 is ready; led with "7000×" and burying
the null, it is not.

---

## 3. Explaining the benefits & generalizability

### 3.1 What the orchestration aspect is

RQ3 studies the **interface between the autoscaler and the load balancer** —
how a newly ready backend becomes *known to the routing plane*. The
load-balancing *policy* (backend-selection, weights, pool state) is held
fixed; only the readiness admission mechanism varies. The benefit claim is about this
integration, not about "better load balancing" in the selection sense.

### 3.2 The benefits, made explicit

| Axis | Evidence | What it buys | Who benefits |
|---|---|---|---|
| Mechanism responsiveness | ready→admitted ~7 s faster (v2, d=−1.000); per-position separation ~6 s (v3 compute-saturation campaign) | removes the poll-period quantization — a tunable design cost | the control loop (converges one poll period sooner) |
| End-to-end timing | spawn→first success ~6 s sooner (v2, p=0.0005); T2 p=0.004 (v3 compute-saturation campaign) | the user's first request after a scale-up arrives sooner | the user during the transition |
| Resource efficiency (v3 headline) | old-backend CPU relief ≥10 pp on majority of admissions, per arm; T_proc −60/−74 % (v3 compute-saturation campaign, 14 runs, n=7/arm) | less time running hot → energy, cost, thermal/battery headroom at the edge | the operator (cost) and the system (margin) |

> **Note (2026-08-21):** the "(v3)" evidence rows above come from the completed
> **v3 compute-saturation campaign** (`docs/operation/testing/experiment/v3/rq3/`,
> 14 runs, n=7/arm, seeds 3001–3007, config P4) — the primary RQ3 evidence.

The one-sentence explanation: **time-to-useful-capacity is a first-order
auto-scaling metric** — every second a newly scaled backend is *dark* is a
second the system pays for capacity without its benefit. Polling makes that
darkness equal to up to one poll period, deterministically; event-driven
admission removes it. The C1/C2 null says the *steady* user does not notice
because the platform is deliberately QoS-bounded — not that the mechanism has
no value.

### 3.3 Does it generalize?

- **Poll cadence — yes (measured).** The quantization scales with the poll
  period (10 s → 15 s ⇒ 9.6 → 15.2 s); the mechanism *is* the poll.
- **Platforms — yes, qualitatively.** Event-vs-poll is the universal
  dichotomy of every routing plane (readiness probes, health checks, registry
  sync); direction holds everywhere, magnitude is config-dependent.
- **Architecture — conditional.** Direct notification needs an event path
  between the readiness owner and the routing plane: free when co-located
  (the thesis apparatus); separated stacks pay an integration cost and lose
  polling's self-healing — which is why they default to polling.
- **Tiers — no (measured null).** The storage-replica extension was closed
  after a 4-run preflight (SG-4 null): read offload occurred but no
  user-visible relief. The benefit does not transfer to the storage tier at
  the locked read-write mix.
- **Workload regime — partial.** The timing benefit persists at every load
  tested (rates 8–25, old CPU up to ~88 %); the *conversion* of the ~7 s
  delay into user harm under bursty / low-headroom demand is **argued by
  mechanism, not separately demonstrated** — this is the stated boundary of
  the C1 null.

### 3.4 Recommended claim

> Event-driven readiness notification removes **up to one poll period** of
> admission quantization in every poll-based discovery system (mechanism
> generalizes; magnitude scales with the poll cadence). Its value is largest
> under fast demand shifts and low headroom, and in co-located architectures
> where the event path is free. On this platform the benefit is measured as
> faster usable capacity (≈6–7 s) and ≥10 pp compute-tier relief per arm, with
> **no user-harm consequence under bounded demand** — and it does **not**
> extend to the storage tier, which was evaluated and closed as a measured
> null.
