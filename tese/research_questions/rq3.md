# RQ3 — Readiness Propagation and Traffic Admission

> **Status:** 2026-07-31 · idea-provenance document (current framing).
> **Framing source:** `tese/Notes/thesis_overview.md` §6-RQ3.
> **Related:** `tese/Notes/purpose_evidence_map.md` (I3, P4, P5, P6); `tese/literature_review/global_literature_review.md` (§2.1, §2.6, §3.1, §5.6).
> **Legacy:** the older "trigger composition / backend-selection modes" framing and `Notas.txt` are superseded by `thesis_overview.md` §5.

---

## 1. Research question

> **For newly created compute backends that satisfy the same application-readiness criterion, how does direct lifecycle notification versus periodic discovery affect the time until a ready backend contributes usable capacity?**

## 2. Position in the chain

This RQ studies the **admission interface** of the control loop:

```text
Demand shift
  -> telemetry observation
  -> scaling decision
  -> capacity action
  -> backend readiness
  -> [RQ3] routing admission  <-  this RQ
  -> successful user request
```

Held fixed: readiness probe, routing cost function, load-balancing weights, pool state, workload, resource limits. Warm-lease priority and slow-start ramps are **disabled in both conditions**. Only the *propagation mechanism* varies.

---

## 3. Where the idea stems from (the basis)

The seed is a simple realistic observation:

> **"A new server can be fully started and still not serve a single request for tens of seconds, because the load balancer doesn't know it's ready."**

The papers that ground this RQ:

| Paper | What it establishes | Strength | Role in the basis |
|---|---|---|---|
| **Wang et al. (SDNFV)** | *"After synchronization completes, the proxy notifies LB-C to include the instance in session allocation."* | `DOCUMENTED` | **The core seed.** The spawn→state-sync→LB-inclusion delay is documented but never varied or measured. |
| **Pierro & Ullah** — K8s HPA for IoT | Throughput **decreases** as pods are added; names *"service discovery latency"* and *"load balancing distribution inefficiencies"* among orchestration-overhead causes. | `SYMPTOM` | Observed symptom of the spawn→discovery gap, misattributed as "K8s overhead". |
| **Pourghebleh et al. (2020)** — SD SLR | *"the freshness of the data still remains a problem"* — registry staleness acknowledged, never studied as a latency dimension. | `DOCUMENTED` | Service-discovery version of the same gap. |
| **Achir et al. (2022)** — SD taxonomy (60+ papers) | **No category** for discovery timing, registration latency, or registry freshness. | `TAXONOMY-GAP` | Even the most comprehensive SD taxonomy lacks the dimension. |
| **Yaseen (2025)** | Pull-based monitoring → "visibility gaps". | `DOCUMENTED` | The "same gap, three names" cross-domain thread (see below). |
| **Podolskiy et al. (IaaS)** | Reactive autoscaling *"jeopardizes"* QoS under dynamic load across all three clouds. | `DOCUMENTED` (context) | The LB-discovery lag is one segment of the reactive-scaling lag. |

### The "same gap, three names" (strongest cross-domain evidence)

Three fields independently describe the same blind spot without citing each other:

| Domain | Name for it | Paper |
|---|---|---|
| Monitoring | "Visibility gaps" — no knowledge of backend **load** | Yaseen (2025) |
| Service Discovery | "Freshness still a problem" — no knowledge of backend **existence** | Pourghebleh et al. (2020); Achir et al. (2022) |
| Load Balancing / Scaling | "Synchronization-before-inclusion delay" — no knowledge of backend **readiness** | Wang et al. (SDNFV); Pierro & Ullah |

RQ3 isolates the **readiness** member of this trio: the path from a backend becoming application-ready to it being eligible for traffic, holding the backend-selection function fixed.

### The gap statement

SDN load-balancing literature asks *"given available backend state, which backend?"* and treats backend availability/health as established fact. **No study isolates the path from a backend becoming application-ready to it becoming eligible to receive traffic, holding the backend-selection function fixed** — Wang et al. documents the delay but never varies it; Pierro & Ullah observe its symptom; the SD field names it "freshness" but never measures it as a latency dimension.

---

## 4. Experiment design (summary)

Two arms, compute backends only (the storage path has a distinct MongoDB SECONDARY readiness event and is excluded):

1. **Direct lifecycle notification** — backend registered after a verified application-readiness event.
2. **Periodic discovery** — the same readiness state is discovered periodically; direct registration is suppressed until the discovery result arrives.

### Foundation of the two arms

The two arms are the two mechanisms the corpus describes but never isolates — and the admission-side analogue of RQ1's delivery dichotomy:

| Arm | Mechanism | Foundation |
|---|---|---|
| **Direct lifecycle notification** | Event-driven inclusion: the component that owns the lifecycle (the controller that spawned the backend and verified readiness) immediately registers it into the routing pool. | **Wang et al. (SDNFV)** — *"After synchronization completes, the proxy notifies LB-C to include the instance in session allocation"* — notify-on-complete, i.e. event-driven inclusion. Only possible when the lifecycle owner and the routing plane share an event path (the thesis's co-located apparatus). |
| **Periodic discovery** | Pull/registry-based: the routing plane learns backend state by polling on a fixed period; admission is quantized to discovery cycles (up to one period of added delay). | Service-discovery field — Pourghebleh et al. ("freshness of the data still remains a problem"), Achir et al. (no discovery-timing category); the K8s-style endpoints/health-check status quo; the "same gap, three names" blind spot. |

Reasons these two, specifically:

1. **Push/pull parallel with RQ1.** RQ1 studies event-preserving vs latest-state *polling* for **telemetry**; RQ3 applies the identical dichotomy to **readiness/admission**. One consistent thesis theme — *how state moves from "known" to "acted upon"* — across two interfaces.
2. **The co-location question made measurable.** Direct notification is only possible when the controller owns the lifecycle (co-location). In separated architectures (K8s + HAProxy, registry-based LB) the LB *cannot* be notified directly — it must poll. The finding is therefore not the trivial "direct beats discovery" but **how much quantization cost periodic discovery adds, and whether co-location's direct path is worth it** — while acknowledging discovery is more fault-tolerant (it re-checks state). Readiness probe, warm-lease, and slow-start are held constant so *only propagation* varies.

Both use the same readiness probe, routing cost function, LB weights, pool state, workload, and resource limits. The experiment uses a **flow-isolation mode** (each measurement request gets a unique connection tuple; the controller removes the corresponding VIP flow after the response) so every measured request is a fresh backend-selection event — preventing flow affinity from masquerading as a propagation effect.

### Primary measurements

Backend-ready → routing-admitted delay · routing-admitted → first-flow delay · first-flow → first-successful-response delay · useful initial request share · transition-window latency and failures · scale-decision → usable-capacity time.

### Required extension (implementation)

Compute readiness probe and pending-backend registry; delay all pool admission until readiness succeeds; suppress direct admission in the discovery condition; decouple propagation from backend-selection policy, warm-lease priority, and ramp behavior.

---

## 5. Honesty / scope notes

- Does **not** compare the controller with Kubernetes, HAProxy, or another external LB. It isolates only the propagation of readiness information.
- Limited to **compute** backends (storage readiness is a distinct MongoDB SECONDARY event, out of scope for this RQ).
- Warm-lease priority and slow-start ramps are **held constant** (disabled in both arms) — only the propagation mechanism varies.
- Any *between-arm difference* is direct evidence that the admission interface is consequential.

---

## 6. Papers to cite in related work (Ch.2)

Wang et al. (SDNFV) · Pierro & Ullah · Pourghebleh et al. (2020) · Achir et al. (2022) · Yaseen (2025) · Podolskiy et al. (IaaS) · plus the Load Balancing on SDN and Service Discovery README SOTA.

## 7. Cross-references

- Purpose map: `tese/Notes/purpose_evidence_map.md` → I3 (interface evidence), P6 (SEND delimitation).
- Global review: `tese/literature_review/global_literature_review.md` → §2.1 (spawn-to-LB-inclusion), §2.6 (SD blind spot), §3.1 (Pierro & Ullah symptom), §5.6 (same gap, three names).
- Implementation plan (docs): `docs/research_questions/v2/rq3/rq3_preparation.md`.
