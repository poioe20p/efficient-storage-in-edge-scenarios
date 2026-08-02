# RQ1 — Telemetry Delivery Semantics

> **Status:** 2026-07-31 · idea-provenance document (current framing).
> **Framing source:** `tese/Notes/thesis_overview.md` §6-RQ1.
> **Related:** `tese/Notes/purpose_evidence_map.md` (I1, P4, P5); `tese/literature_review/global_literature_review.md` (§2.3, §5.1, §5.2).
> **Legacy:** the older "telemetry freshness / push-vs-poll cadence" framing and `Notas.txt` are superseded by `thesis_overview.md` §5.

---

## 1. Research question

> **How do verified event-preserving, delayed event-preserving, and latest-state telemetry delivery semantics affect overload observability, scaling response, and transient service quality in a stateful edge service?**

## 2. Position in the chain

This RQ studies the **observation interface** of the control loop:

```text
Demand shift
  -> [RQ1] telemetry observation  <-  this RQ
  -> scaling decision
  -> capacity action
  -> backend readiness
  -> routing admission
  -> successful user request
```

Held fixed: the aggregation window, scaling policy, routing policy, workload, topology, and resource limits. Only *how demand evidence reaches the decision* varies.

---

## 3. Where the idea stems from (the basis)

The seed is a simple realistic observation:

> **"If the controller sees demand late, or misses the intermediate demand evidence entirely, its scale-out decisions are worse — but which failure, delay or missing evidence, actually hurts?"**

The papers that ground this RQ:

| Paper | What it establishes | Strength | Role in the basis |
|---|---|---|---|
| **AdapPF — Huang & Pierre (2023)** | Varies Prometheus scrape interval; 60 s vs 5 s measurably degrades scheduling accuracy; adaptive cadence ≈ 36% traffic saving. | `MEASURED` | **The strongest seed.** Proves freshness affects decision quality — for one consumer (a scheduler). The thesis extends: does it matter for a *stateful service's* scaling + admission chain? |
| **Yaseen (2025)** — survey of programmable network-wide monitoring | Pull-based polling → "visibility gaps": *"SNMP polling operates on a pull-based model with periodic queries, introducing latency and potential data loss especially under congestion. This can lead to visibility gaps."* | `DOCUMENTED` | Names the failure mode the RQ isolates (pull = lost/absent intermediate state). |
| **Caiza & Campoverde (2024)** — WSM multi-resource LB policy | Closest algorithmic cousin (WSM cost function, like this thesis); collection happens *"periodically"* — the period is an implementation detail, never a variable. | `TAXONOMY-GAP` | Shows even a latency-aware selector treats freshness as a given. |
| **Zhang & Guo (2014)** | Same *"periodically"* assumption, a decade earlier, unchanged. | `TAXONOMY-GAP` | Shows the assumption is persistent, not a one-off. |
| **Belgaum et al. (2020)** — 76-paper SDN-LB review | Open issues: security, controller placement, AI. Nothing about freshness. | `SILENCE` | **Use only as inattention, never as importance** (see purpose map rule). Scope boundary: "even a 76-paper review has no dimension for this." |
| **Usman et al. (2022)** — constrained-edge resource management | "Appropriate measurement intervals" on constrained edge are explicitly unresolved. | `DOCUMENTED` (open problem) | Motivates the cadence/delivery dimension as a *live* open problem. *(Verify exact wording/DOI before quoting in the manuscript.)* |

### The distinguishing claim

AdapPF shows freshness matters for a scheduler. **No reviewed paper distinguishes two delivery semantics — delayed-but-complete (event-preserving) vs latest-state (intermediate observations discarded) — or traces them through a stateful service's scaling and admission path.** This RQ isolates which failure mode (delay, loss of evidence, or both) is the real driver, and measures magnitude per mode.

---

## 4. Experiment design (summary)

Three arms, everything else fixed:

1. **Event-preserving reference** — every completed telemetry window delivered exactly once, in source order.
2. **Delayed event-preserving** — same ordered windows, fixed pre-registered delay, no burst replay.
3. **Latest-state polling** — consumer gets only the most recent completed window; intermediate windows are not delivered.

### Primary measurements

Completed and missed overload windows · information age and delivery delay · demand-shift→decision time · demand-shift→usable-capacity time · offered vs completed requests · latency distributions and failure rate · controller/telemetry overhead.

### Required extension (implementation)

Durable, sequence-numbered telemetry-window log with retention, ordered replay, delivery acknowledgement, and shared event identifiers (the current ZMQ PUB/SUB path is not assumed event-preserving until sequence validation + gap recovery exist).

---

## 5. Honesty / scope notes

- Does **not** claim monitoring cadence is unstudied — AdapPF already shows it matters. Claims the *semantics* distinction (delay vs lost evidence) and the *downstream chain* are unstudied.
- The delivery semantics question is independent of the monitoring→decision *algorithm*; it is about the **handoff**, matching the thesis's interface framing.
- Any *between-arm difference* is direct evidence that the observation interface is consequential (the treatments vary only how evidence is delivered).

---

## 6. Papers to cite in related work (Ch.2)

AdapPF (Huang & Pierre, 2023) · Yaseen (2025) · Caiza & Campoverde (2024) · Zhang & Guo (2014) · Belgaum et al. (2020) · Usman et al. (2022, verify) · plus the telemetry SOTA README (`tese/literature_review/01_telemetry_rq1/README.md`).

## 7. Cross-references

- Purpose map: `tese/Notes/purpose_evidence_map.md` → I1 (interface evidence), P4 (documented/symptomatic/called-for), P5 (freshness hierarchy).
- Global review: `tese/literature_review/global_literature_review.md` → §2.3 (visibility gaps), §5.1 (monitoring→LB disconnect), §5.2 (monitoring→scaling disconnect).
- Experiment plan (docs): `docs/research_questions/v2/rq1/rq1_prepation.md`; `docs/operation/testing/experiment/v2/rq1/experiment_plan.md`.
