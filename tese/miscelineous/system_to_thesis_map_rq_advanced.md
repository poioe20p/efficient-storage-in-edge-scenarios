# Advanced System-to-Thesis RQ Map

The main purpose of this note is to answer five practical questions:

1. What are the strongest working research questions for the thesis?
2. Why are these questions academically defensible?
3. What concepts and comparison axes does each question involve?
4. What additional development is required before each question can be answered rigorously?
5. What measurements and scenarios are required to evaluate each question?

---

## 1. Thesis Framing

The thesis should be framed around a **cross-layer orchestration framework for stateful edge systems.**

What the thesis **is** about:

- how control-plane information is acquired and consumed
- how backend-selection decisions use cross-layer metadata
- how data-locality and elasticity mechanisms trade off service quality, readiness, and operating cost

---

## 2. RQ Selection Principles

The chosen RQs should satisfy all of the following conditions:

1. They must ask about a **systems trade-off or control problem**, not merely restate a feature.
2. They must be **empirically answerable** with measurable variables and controlled baselines.
3. They must **isolate the main independent variable** instead of changing several architectural dimensions at once.
4. They must remain faithful to the implemented system unless explicitly marked as requiring further development.
5. They must support a clear methodology chapter and a defensible results chapter.

For this reason, the recommended advanced RQ set below separates:

- **information acquisition** from **decision policy**
- **routing quality** from **elasticity quality**
- **cold-start capacity growth** from **reserved or pre-synchronized capacity**

---

## 3. Advanced Working RQ Set

## RQ1. Push vs Polling Telemetry Acquisition

> **RQ1.** How does push-based versus periodic polling-based telemetry acquisition affect controller decision staleness, reaction latency, and transient service quality when the same orchestration policy is held constant in a stateful edge system?

### Why RQ1 is a strong RQ

This is a strong thesis RQ because it isolates a real control-plane design choice:

- whether the controller learns state through **push-based summaries** or through **periodic retrieval**
- whether fresher state actually improves adaptation during transients
- whether the monitoring method itself introduces measurable control overhead

It avoids a weak "MongoDB versus ZMQ" framing and instead asks a transport-agnostic control question about **state freshness**, **decision staleness**, and **response quality**.

### Concepts involved in RQ1

- push versus pull telemetry acquisition
- controller state freshness
- decision staleness window
- reaction latency
- transient QoE degradation
- control-plane overhead
- aggregation boundary versus raw event storage

### Why RQ1 matches the current architecture

The current controller already consumes telemetry through an abstract source boundary:

- [`../../source/sdn_controller/telemetry/source.py`](../../source/sdn_controller/telemetry/source.py)
- [`../../source/sdn_controller/telemetry/zmq_source.py`](../../source/sdn_controller/telemetry/zmq_source.py)

The current push-based path is:

1. emit raw events from edge/server sidecars
2. aggregate them into a `TelemetrySummary`
3. push the summary to the controller via ZMQ PUB/SUB

This means the clean comparison is **not** to redesign the whole telemetry plane, but to keep the same summary schema and vary only how the controller receives it.

### Development required for RQ1

Required for rigorous comparison:

1. Implement a **polling telemetry source** on the controller side.
2. Persist `TelemetrySummary` objects at the **aggregator-controller boundary**.
3. Keep the raw emitter behavior unchanged for the first comparison.
4. Add timestamps needed to measure summary publication, retrieval, and controller consumption delay.

Recommended design:

- keep raw event emission unchanged in:
  - [`../../source/docker/edge_server/source/telemetry.py`](../../source/docker/edge_server/source/telemetry.py)
  - [`../../source/docker/edge_storage_server/mongo_telemetry.py`](../../source/docker/edge_storage_server/mongo_telemetry.py)
- keep summary construction unchanged in:
  - [`../../source/docker/local_state_server/aggregator.py`](../../source/docker/local_state_server/aggregator.py)
- add persistence of each windowed summary to a MongoDB collection
- implement a new controller-side polling source parallel to `ZmqTelemetrySource`

Not required for the first comparison:

- storing **raw** edge telemetry in MongoDB
- replacing the aggregator with a database-only architecture

### Measurements required for RQ1

Primary measurements:

1. **Decision staleness window**
   Definition: controller consume time minus summary window end / publish time.
2. **Reaction latency**
   Definition: breach becomes visible to controller until alert submission and infrastructure action starts.
3. **Transient service quality**
   Use p95 and p99 latency, failure rate, and completed requests during workload transitions.
4. **Control-plane overhead**
   Controller CPU/RAM, database reads issued by the controller, and polling traffic volume.

Secondary measurements:

1. summary miss rate or delayed-summary count
2. stale-decision frequency during directed spikes
3. controller-side queueing delay under bursty updates

### Evaluation design for RQ1

Hold constant:

- workload shape
- scaling thresholds
- routing policy
- summary schema
- aggregator window size

Vary only:

- telemetry acquisition mode at the controller: push-subscribe versus periodic polling

Suggested baselines:

1. Push-based summary subscription
2. Polling every 1 s
3. Polling every 5 s
4. Polling every 10 s

---

## RQ2. Metadata-Aware Backend Selection

> **RQ2.** To what extent does metadata-aware backend selection improve load distribution and request handling compared with topology-only and topology-plus-host-load selection in a stateful edge system?

### Why RQ2 is a strong RQ

This is a strong RQ because it asks about **decision quality**, not about elasticity or infrastructure size. It tests whether adding richer state to the selection logic improves outcomes beyond simpler policies.

It is also strong because it can be evaluated while holding the underlying substrate constant:

- same controllers
- same VIP model
- same traffic generator
- same infrastructure
- different selection policies only

### Concepts involved in RQ2

- topology-aware routing
- host-load-aware routing
- replica-state-aware routing
- cross-layer optimization
- compute plane versus data plane
- leading indicators for steering
- stateful backend admissibility and freshness

### Why RQ2 matches the current architecture

The current routing layer already uses a weighted cost model in:

- [`../../source/sdn_controller/vip_routing.py`](../../source/sdn_controller/vip_routing.py)

The key point, however, is that a rigorous RQ2 cannot be answered by merely changing numeric weights. It needs **explicit policy modes** that define which metadata each policy is allowed to use.

This question should be evaluated separately on the two current traffic planes:

1. **Compute plane**: `VIP_SERVER`
2. **Data plane**: `VIP_DATA_N*`

### Development required for RQ2

Required for rigorous comparison:

1. Add explicit backend-selection policy modes.
2. Hold all non-policy behavior constant.
3. Define clearly which metadata each mode may use.
4. Evaluate compute and data planes separately, even if the thesis keeps a unified RQ.

Recommended policy family:

1. `topology_only`
   - allowed inputs: hop distance only
2. `topology_host`
   - allowed inputs: hops, CPU, RAM, request count / connections
3. `topology_host_replica`
   - allowed inputs: hops, host load, and replica-state metadata such as replication lag

Optional extension:

1. `full_current_policy`
   - same as above plus any existing warm-admission behavior already used by the controller

Instrumentation that would help:

- structured trace logging of candidate scores and exclusion reasons
- per-policy request assignment counts
- explicit tagging of compute-plane versus data-plane decisions in analysis

### Measurements required for RQ2

Compute-plane measurements:

1. p95/p99 request latency
2. failure rate
3. request distribution across servers
4. Jain's fairness index over compute CPU usage
5. spillover frequency to peer-LAN backends

Data-plane measurements:

1. p95/p99 DB-side latency contribution
2. failure rate under data stress
3. fraction of reads routed to lagged or stressed backends
4. hop count and cross-LAN routing frequency
5. storage CPU balance and connection balance across eligible nodes

Shared measurements:

1. routing churn or instability
2. number of policy-induced bad choices under constructed stress cases
3. per-phase latency and fairness rather than only whole-run averages

### Evaluation design for RQ2

Hold constant:

- telemetry acquisition mode
- scaling behavior
- workload
- flow timeouts

Vary only:

- policy mode

Important methodological note:

RQ2 should not be answered with a single aggregate statement such as "cross-layer is better." It should show **where** the richer policy helps:

- under compute-heavy imbalance
- under storage lag or replica-state asymmetry
- under cross-LAN spillover opportunities

### Main validity threats for RQ2

- weight tuning can masquerade as algorithmic improvement if policy modes are not explicit
- low backend diversity can make differences too small to interpret
- mixing compute and data-plane effects in one aggregate metric can hide the actual cause

---

## RQ3. Partial Replication vs Cold and Reserved Capacity

> **RQ3.** Under shifting cross-region demand, how do remote serving, selective partial replication, cold-start full replica placement, and reserved-standby full replica promotion trade off service benefit, activation overhead, and lifecycle complexity?

### Why RQ3 is a strong RQ

This is the strongest version of the elasticity-and-locality question because it does **not** reduce elasticity to generic horizontal scaling. Instead, it compares several strategies with different readiness and cost profiles:

1. do nothing and serve remotely
2. place only the hot subset locally
3. provision a full local replica reactively
4. keep a pre-synchronized standby that can be admitted quickly

This makes elasticity central again, but in a way that is meaningful for a stateful edge system.

### Concepts involved in RQ3

- cross-region demand shifts
- data locality
- selective partial replication
- cold-start elasticity
- reserved capacity / warm elasticity
- sync tax
- time-to-benefit
- reservation tax
- lifecycle complexity and cleanup debt

### Strategy family for evaluating RQ3

1. **Remote serving only**
   - baseline
   - no local copy
2. **Selective partial replication**
   - Tier 1-style hot-set replication
3. **Cold-start full replica placement**
   - full remote replica created only after the demand breach
4. **Reserved-standby full replica promotion**
   - pre-created and pre-synchronized standby excluded from service until promotion
5. **Hybrid first-step reserved policy**
   - first extra node uses reserved capacity
   - additional nodes remain cold-start elastic

### Development required for RQ3

Required for the strongest version of this RQ:

1. Implement **true consumer-LAN full replica placement**, not only same-LAN replica-set growth.
2. Integrate that placement into the controller's locality logic.
3. Implement a **reserved-standby mode** for the first full-replica promotion.
4. Add instrumentation for activation timestamps, sync progress, and admission-to-service timing.
5. Measure cleanup debt explicitly.

Reserved capacity should be interpreted as a **warm elasticity mode**, not as the removal of elasticity from the thesis. It changes the trade-off from:

- pay cold-start cost only on demand

to:

- pay idle reservation cost in exchange for faster burst response

The most defensible reserved-capacity design is likely:

- reserve capacity only for the **first** full scale-up
- use cold-start growth only for later additional replicas

This keeps the comparison realistic for edge environments with limited idle resources.

### Measurements required for RQ3

Service-benefit measurements:

1. p95/p99 latency during cross-region hotspot phases
2. failure rate and completed request volume
3. phase-specific recovery behavior after a demand surge

Activation-overhead measurements:

1. **Activation latency**
   - breach detected to backend eligible for routing
2. **Sync tax**
   - time, CPU, and bandwidth spent before a cold full replica becomes usable
3. **Time-to-benefit**
   - breach detected to latency recovery or service stabilization

Steady-state overhead measurements:

1. **Reservation tax**
   - idle CPU/RAM/storage/replication traffic for standby capacity
2. extra node-hours or container-hours consumed by each strategy
3. background replication cost while standby is not yet serving

Lifecycle-complexity measurements:

1. cleanup debt
2. failed removals
3. lingering containers at run end
4. post-cleanup stale control work
5. control-plane exceptions caused by scale-down or reconfiguration

### Evaluation design for RQ3

The workload should include different demand regimes, not just a single long-cycle run:

1. brief burst
2. medium-duration hotspot
3. sustained hotspot
4. reversed hotspot direction

The main value of RQ3 is not to show that one strategy is universally best. It is to determine **when** the faster readiness of reserved capacity justifies its idle cost, and **when** partial replication is sufficient without escalating to a full remote copy.

### Main validity threats for RQ3

- if full-replica placement remains same-LAN only, the cross-region interpretation weakens substantially
- standby cost must be measured explicitly rather than assumed to be small
- Tier 1 observability gaps can still confound comparisons if not instrumented clearly

### Fallback narrower RQ if the stronger version is not implemented

If consumer-LAN full replica placement and reserved standby are not implemented in time, the narrower fallback RQ is:

> What service-quality benefit and lifecycle cost does selective partial replication provide under shifting cross-region demand compared with remote serving only?

This fallback is weaker, but still defensible.

---

## 4. Cross-RQ Measurement Matrix

| RQ            | Main independent variable     | Main dependent variables                                                   | Required development                                                              | Existing support level |
| :------------ | :---------------------------- | :------------------------------------------------------------------------- | :-------------------------------------------------------------------------------- | :--------------------: |
| **RQ1** | telemetry acquisition mode    | decision staleness, reaction latency, transient p95/p99, control overhead  | polling source, summary persistence, timing instrumentation                       |         Medium         |
| **RQ2** | backend-selection policy mode | latency, fairness, failure rate, bad-choice frequency, spillover behavior  | explicit policy modes, per-policy traceability                                    |         Medium         |
| **RQ3** | locality / readiness strategy | latency recovery, activation cost, sync tax, reservation tax, cleanup debt | consumer-LAN full replica, reserved standby, timing and lifecycle instrumentation |     Low to Medium     |

---

## 5. Development Priorities Implied by the RQs

If the thesis follows this advanced RQ set, the implementation priorities should be:

1. **Aggregator boundary persistence + polling controller source**
   - required for RQ1
2. **Explicit routing policy modes**
   - required for RQ2
3. **Improved timing instrumentation for alert-to-action and action-to-service**
   - required for RQ1 and RQ3
4. **Consumer-LAN full replica placement**
   - required for the stronger RQ3
5. **Reserved-standby first-scale promotion path**
   - strongest extension for making elasticity itself a central thesis contribution
