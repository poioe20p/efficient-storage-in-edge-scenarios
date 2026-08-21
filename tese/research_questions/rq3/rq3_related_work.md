# RQ3 — Related Work: Evaluation Practice in readiness admission & Elasticity

> **Status:** 2026-08-12 · draft for the related-work (Ch.2) positioning.
> **Companion to:** `rq3.md` (research-question framing, basis papers) and
> `rq3_evaluation_conclusions.md` (results + critical review).
> **Purpose:** this document answers *how the field evaluates
> resource-orchestration mechanisms*, where RQ3 sits in that practice, and
> how the RQ3 results should be read against it. It is the
> evaluation-practice lens on the related work, not a replacement for the
> basis-paper provenance in `rq3.md` §3.
> **Bibliography note:** `tese/references.bib` currently holds 19 entries; the
> RQ3 basis papers listed in `rq3.md` §6 are **not yet in the .bib**. Every
> citation proposed below must be **verified by DOI**
> (`tools/add_bib_from_doi.py`) before it is added — none are fabricated.

---

## 1. The gap RQ3 addresses (recap)

The readiness-admission blind spot, as established in `rq3.md` §3 and the
global review §5.5 — the *same gap, two names* (monitoring ↔ service
discovery): monitoring ("visibility gaps", Yaseen) and service discovery
("freshness still a problem", Pourghebleh; no discovery-timing category,
Achir). No study isolates the
path **from a backend becoming application-ready to it becoming eligible for
traffic**, holding the backend-selection function fixed. RQ3 isolates the
*readiness* member of that blind spot.

This document adds a second, complementary lens: **even the evaluations that
exist do not all measure the axis RQ3 measures** — so a reviewer's question
"what does the field count as evidence here?" needs an explicit answer.

---

## 2. How the field evaluates orchestration — three styles

Papers in the same context (edge resource orchestration, auto-scaling,
SDN-programmable platforms, service discovery/registration) split into three
evaluation cultures:

| Style | What they evaluate | Typical metrics | Where it dominates |
|---|---|---|---|
| **A — Efficiency-only** | The orchestrator/scheduler itself | utilization, energy, cost, node count, makespan, over/under-provisioning, convergence time, decision latency | Operations-research-flavoured scheduling; VM/container consolidation; autoscaler-internal studies |
| **B — QoS-headline** | The end-user experience of the platform | E2E latency (p50/p95/p99), throughput, completion rate, deadline/SLA violation, error rate | Edge offloading, SDN-edge platforms, fog orchestration, serverless edge — anything whose *motivation* is user-facing latency |
| **C — SLA-preserving efficiency / hybrid** | Efficiency **at constant QoS**, or an explicit QoS↔cost relationship | "meets the SLO with X % fewer resources/nodes/energy"; Pareto cost-vs-QoS; a **consequence check** ("the mechanism did not hurt users") | The most defensible pattern; increasingly what reviewers expect |

Practical notes:

- **Pure schedulers (A)** legitimately report efficiency only — but this is a
  known review weakness ("you reduced utilization; did the user notice?").
  Accepted when the contribution is purely algorithmic (placement,
  bin-packing, decision quality).
- **Edge *platform* papers (B)** almost always add service-quality metrics,
  because the entire justification of edge is user latency. A platform paper
  that reports only CPU will be flagged.
- **The dominant defensible pattern (C)** keeps efficiency as the objective
  and treats QoS as a *constraint* (p99 under target, report the savings) or
  as a *consequence check* (proof the mechanism did not degrade users).
  RQ3 follows C + a consequence check.

---

## 3. Where RQ3 sits

RQ3 deliberately evaluates **all three axes**, which maps cleanly onto the
styles:

| RQ3 axis | Metric | Style |
|---|---|---|
| Mechanism responsiveness | T1 ready→admitted; T2 spawn→first success; scale→usable capacity | B (timing) + A (control-loop convergence) |
| Resource efficiency (headline, v3) | R1 old-backend CPU relief ≥10 pp; R2 T_proc drop | A + C |
| QoS consequence | C1/C2 gap-window timeout/failure = 0.000 (pre-registered null) | C (consequence check) |

**Why the null is a legitimate finding, not a non-result** (this is the
answer a reviewer will demand): a "no user-visible harm" result is accepted
in the literature **if and only if** three conditions hold, and RQ3 satisfies
all of them:

1. the system is *deliberately QoS-bounded* (autoscaler firing band 70–88 % +
   admission gate ⇒ the tier cannot over-saturate);
2. the efficiency/relief benefit is *real and quantified* (R1/R2, n=7/arm);
3. the *boundary of the null* is stated (holds under bounded/open-loop
   demand; under bursty demand the ~7 s quantization would convert into
   degradation — argued by mechanism, not separately demonstrated).

The review risk is the inverse: claiming a *user-facing benefit* ("lower
latency") while only showing efficiency + a null would look like the
mechanism does not matter. RQ3's framing — **efficiency + bounded-QoS
robustness** — is the safe one.

---

## 4. Applying the lens to the RQ3 basis papers

Classifying the basis papers in `rq3.md` §3 by evaluation style shows why the
ready→admitted axis is unmeasured: the field either reports the *symptom*
without isolating the mechanism (B), or classifies without a timing dimension
(A), or measures efficiency without the admission path (A/C).

| Paper (label from `rq3.md`) | Style | What it measures | What it does NOT measure |
|---|---|---|---|
| Pourghebleh et al. (2020) | A (survey) | registry freshness acknowledged | not measured as a latency dimension |
| Achir et al. (2022) | A (taxonomy) | SD categories (87 approaches) | **no category for discovery timing / registration latency** |
| Yaseen (2025) | B | pull-based monitoring → visibility gaps | readiness, not load, is the gap |
| Podolskiy et al. (IaaS) | B | reactive autoscaling jeopardizes QoS | the LB-discovery lag is one segment, not isolated |

The table doubles as the thesis's positioning argument: the corpus has
mechanism-adjacent results (B) and taxonomies (A) but **no isolated,
controlled measurement of the ready→admitted quantization** — which is RQ3's
contribution.

---

## 5. Bibliography status & to-add list (verify before citing)

`tese/references.bib` has **19 entries**; the RQ3 basis papers (`rq3.md` §6)
are not yet in it. Priority additions for the Ch.2 evaluation-practice
section, each to be **verified by DOI** before it lands in the .bib:

| Candidate (to verify) | Why | Style it evidences |
|---|---|---|
| Elasticity survey — Herbst et al., *Elasticity in Cloud Computing: What It Is, and What It Is Not* (ICAC 2013) | canonical definition of elasticity and its evaluation | A/C taxonomy |
| A container cold-start / provisioning-delay study (serverless-edge or K8s) | the time-to-usable-capacity axis, directly parallel to T1/T2 | B |
| A Kubernetes readiness-probe / service-discovery propagation evaluation | the event-vs-poll dichotomy in a mainstream platform | B + C |
| An edge auto-scaling QoS evaluation (SLO-preserving) | the "meet SLO with fewer resources" pattern | C |

> Honesty rule: no citation is added to `references.bib` without DOI
> verification. Until then these appear only as search directions, not as
> cited claims.

---

## 6. Cross-references

- `rq3.md` — research question, basis papers (§3), papers-to-cite list (§6).
- `rq3_evaluation_conclusions.md` — results, critical review, the
  "demonstrated vs argued" claim boundary (§1.7).
- `tese/literature_review/global_literature_review.md` — §2.4 (SD blind spot),
  §5.5 (same gap, two names).
- `tese/Notes/purpose_evidence_map.md` — I3 (interface evidence), P6 (SEND
  delimitation).
