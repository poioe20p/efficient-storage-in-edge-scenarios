# Architecture Gaps and Weaknesses — Examiner-Style Review Record

> **Status:** 2026-09-05. Record of an examiner-style review of the Chapter 3
> architecture against eight corpus papers. Verdict: the architecture is
> logically sufficient for a controlled experimental Master's thesis. The gaps
> below are split into two tiers (recalibrated 2026-09-05 after re-reading the
> seven local reference dissertations): **Tier 1** — scope-internal honesty
> items to disclose in the manuscript; **Tier 2** — out-of-scope production
> concerns to omit or reduce to a one-line future-work mention.

## 1. Verdict

The platform has the essential stack for the three research questions:
programmable data plane (OpenFlow), service indirection (double-VIP),
container lifecycle control, compute and storage elasticity, telemetry with
configurable delivery semantics, readiness gating, resource caps and
cooldowns, and end-to-end instrumentation.

It is **not production-ready** and must never be described as such. Chapter 3
should define it explicitly as a controlled experimental platform.

## 2. One real issue to fix or qualify: admitted vs routable

- A backend is recorded as admitted when its MAC is registered.
- The forwarding pool is rebuilt by the periodic topology worker, not
  atomically on registration.
- Consequence: a backend can be logged as *admitted* before it is selectable,
  and a draining backend can remain selectable until the next topology cycle.
  This affects the precision of the RQ3 ready→admitted→first-flow timestamps.

Options:

1. atomically update the relevant VIP pool on add/remove; or
2. redefine the metric as *registered*, and use first pool inclusion / first
   successful flow as the true routability timestamps.

The ~6–7 s RQ3 direct-vs-discovery difference is unlikely to reverse; this is
a timestamp-accuracy matter, not a result-reversal risk.

## 3. Scope limits — two tiers (recalibrated 2026-09-05)

The seven local reference dissertations do not enumerate production-grade
weaknesses; they disclose (a) obstacles encountered while working, (b)
in-scope items not measured, and (c) one-line future work. The items below
follow that standard.

**Tier 1 — disclose in the thesis (scope-internal honesty).**

| Area | Assessment | Thesis placement |
|---|---|---|
| Admission timing | A backend is recorded as admitted (MAC registered) before the periodic topology rebuild makes it selectable. | Qualify the RQ3 ready→admitted→first-flow timestamps in Ch.3/Ch.4, or make the pool update atomic. |
| RQ2 storage action | The evaluated same-LAN action is activation of a prepared secondary reserve; cold `rs.add()` runs at preparation/replenishment. | Correct the wording in Ch.3 §3.3 and every results claim. |
| Data consistency | Writes go to the primary; reads use `secondaryPreferred` (eventual consistency); no read-after-write, causal, or quorum-durable guarantees. | One sentence in Ch.3 §3.3: reads are eventually consistent; the evaluation does not rely on read-after-write semantics. |
| Testbed realism | Emulated two-domain single-host testbed; host-local control paths; single-site evaluated data path. | Already stated in Ch.3 §3.2; keep as-is. |
| Concurrency wording | The three contexts share routing pools, telemetry maps, and lifecycle state. | Ensure Ch.3 describes ownership and handoff without claiming "no shared mutable state". |

**Tier 2 — at most a one-line future-work mention, or omit (production concerns).**

| Area | Assessment | Thesis placement |
|---|---|---|
| Controller availability | Two peer controllers, no active/standby redundancy; per-domain control-plane single point of failure. | Optional one-liner in §6.4 ("controller redundancy and secure multi-domain control"). |
| Peer state | Non-blocking PUB/SUB snapshots, no peer-expiry; stale peer membership possible after a peer failure. | Optional, same §6.4 one-liner. |
| Security | No TLS, authentication, RBAC, tenant isolation, or threat model; trusted single-tenant assumption. | Optional, same §6.4 one-liner. |
| Resource optimization | Latency/utilization-driven; no energy, bandwidth, or global-cost claims (not measured). | Omit; simply never claim. |
| Mobility / QoS | No mobility, radio, or per-application SLA guarantees. | Omit. |

## 4. RQ2 storage-action accuracy

Describe the evaluated storage action as **activation of a prepared secondary
reserve** (warm, outside the VIP pool until a data action fires), with cold
`rs.add()` at reserve preparation/replenishment — not as cold replica creation
on the reaction path.

## 5. Benchmark position vs the eight papers

| Paper | Benchmark contribution | Position of this architecture |
|---|---|---|
| 5G backhaul monitoring architecture | Per-device telemetry microservices, collector restart, time-series storage | Deeper telemetry semantics/instrumentation experimentally; no claim of carrier scale or collector fault tolerance |
| SEND | Data labels, freshness/shelf life, cloud archival, metadata-driven placement | Not a missing core unless metadata-driven placement is claimed; the system manages capacity around existing data |
| VNF scaling + LB (Llorens) | Flow affinity, health handling, scaling bounds, active/standby controllers | Closest comparator; matches or exceeds lifecycle, routing, and telemetry detail; HA is the significant missing production feature |
| Industrial IIoT orchestration | Kubernetes migration, energy measurements | More detailed control-loop design; no energy claim |
| Vehicular MEC resource management | Cloud/MEC hierarchy, mobility, radio slicing, QoS | Different scope; no mobility/radio/SLA claims is acceptable for a static HTTP testbed |
| Network-centric SDN-edge survey | Secure/reliable east-west interfaces, distributed-control scalability | Peer topology exchange is a prototype, not a secure multi-domain control plane |
| SDN-edge survey (Baktir) | Service-centric routing, synchronization, mobility, soft state, controller reliability | VIP indirection and lifecycle handling aligned; mobility and HA out of scope |
| Resource-optimization study (Nain) | Broader compute/storage/bandwidth/energy/security optimization | Targeted resource-management experiment, not a comprehensive optimization framework |

## 6. Minimum actions (recalibrated two-tier)

**Tier 1 — thesis text (Ch.3/§6.3):**

- [ ] Qualify the VIP-pool admission/removal timing (fix or redefine the metric).
- [ ] Add one consistency-contract sentence in §3.3 Data.
- [ ] Correct the RQ2 storage-action wording to reserve activation.
- [ ] Ensure the Ch.3 control-workflow prose states ownership/handoff without "no shared mutable state".

**Tier 2 — at most one §6.4 future-work one-liner:**

- [ ] Optionally add "controller redundancy and secure multi-domain control" as future work.

## 7. Do not build (would broaden the thesis without strengthening the RQs)

Kubernetes, controller clustering, cloud archival, vehicle mobility, data
labels, or a security system — the three RQs do not require them.
