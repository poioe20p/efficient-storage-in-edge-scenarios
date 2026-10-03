# Chapter 3 — Core Ideas (working reference)

> Working note, not thesis text. A one-page mental model of
> `ch:system_architecture` for use while writing Chapter 4 and keeping the
> design/implementation boundary clean. Source of truth: `tese/main.tex`
> §3.1–§3.5; per-campaign values: Appendix A. Last update: 2026-10-03.

## In one line

A two-domain SDN platform whose single-process controller observes windowed
demand evidence, decides through a sustained-degradation policy with adaptive
thresholds, and acts on two independent tiers, with telemetry delivery,
capacity-action selection, and readiness admission as separate, configurable
interfaces of the demand-to-capacity chain.

## 1. Role of the chapter

- The platform is the experimental apparatus: it makes the three interfaces
  measurable; no superiority claim over other orchestrators.
- The demand-to-capacity chain is the spine: delivery (RQ1) → selection (RQ2)
  → admission (RQ3).
- DR1–DR6 state what the design must guarantee; the chapter intro maps each
  requirement to the section that realises it.
- Labels to keep: Tier 0/1 are platform capabilities; cross-domain service
  placement is a held-constant capability; cross-domain storage placement is
  disabled; single-host, two-domain testbed with host-local control paths.

## 2. Architecture

- Two domains joined by an emulated inter-domain link (data path only).
- Double VIP: `VIP_SERVER` for service routing, `VIP_DATA` for storage reads;
  writes go direct to the replica-set primary. Two distinct routing surfaces.
- Flows are steered when first observed; installed flows stay where placed.
- Three paths, coordinated in one controller process: request data path,
  telemetry observation path, slow infrastructure-management path.
- Three non-blocking execution contexts (packet, observation, action) exchange
  state through shared structures: telemetry state, action queue, lifecycle
  state, routing pools.

## 3. Observation, decisions, and node state

- Producers → aggregator → windowed summaries → two consumers: routing state
  and the decision engine. Delivery to the controller is the configurable
  interface (default push; latest-state; sampled-push; event-preserving
  immediate or delayed) — the RQ1 surface.
- Per tier, two signals: CPU utilisation + latency, where the latency signal is
  the edge-service component — request processing for compute, data access for
  storage; the window statistic is the mean or the median, configured per
  campaign.
- Decision per window: degradation score (floors, spans, weights) → adaptive
  threshold θ(k) with peer relief → sustained R of W eligible windows → typed,
  prioritised request (adds before removes; storage before compute); cooldowns,
  caps, window clearing; scale-down from the idle condition over a longer
  window, with indeterminate windows excluded.
- When both tiers signal, the design can commit a single action per window; the
  bottleneck-aware configuration commits the action matched to the identified
  bottleneck — the RQ2 surface. Every decision is recorded with its evidence.
- **Node state and liveness (added 2026-10-03).** Heartbeats keep idle nodes
  visible (heartbeat-only nodes stay in the summaries; a bootstrap heartbeat
  makes a starting node visible immediately); summaries carry each node's
  last-report time; state-dependent decisions carry freshness bounds (e.g. the
  compute scale-down candidate filter); a node silent beyond the absence bound
  is treated as gone and cleaned up; nodes without fresh telemetry receive a
  configured default in selection rather than an implicit preference.
  Principle: the controller acts only on capacity it can observe.
  [In Ch3 as of 2026-10-03: §3.4 liveness paragraph and the §3.3.2
  recent-reports clause; heartbeat intervals and bounds remain Ch4 values.]

## 4. Elastic allocation — actions and lifecycle

- Compute: scale-up → provision → register → readiness admission (direct
  notification / periodic discovery / fallback probe; the RQ3 surface) → usable;
  scale-down = least-loaded dynamic replica first, two-phase drain with
  cancel-on-rebound.
- Storage: scale-up = activation of the prepared reserve + immediate
  replenishment; a joining member is admitted only when it can serve reads;
  removal = LIFO among platform-added members only, under the idle condition.
- Provisioned ≠ usable (DR4); the chain is instrumented to the first successful
  request (DR6).

## 5. Selection (load balancing)

- Cost-based WSM, two pools with separate metric sets — backends (CPU, RAM,
  requests, hops) and storage members (CPU, RAM, connections, replication lag,
  hops).
- Each metric as a fraction of the pool maximum; configurable weights (App A);
  lowest cost wins; round-robin across ties.
- Hop distance = reach: a peer-domain candidate is always farther; local is
  preferred at comparable state (cross-domain service placement is a
  held-constant capability).
- Eligibility is admission-gated; draining nodes leave the pool. Reads spread
  via VIP_DATA; writes direct (primary writes, eventually consistent secondary
  reads).

## 6. Workflow and coordination

- Execution order (adds before removes; cancel before execute) is distinct from
  action selection.
- Peer exchange is informational: each controller acts on its own domain's
  demand; peer effects are the β_peer threshold relief and peer-domain
  selection candidates.

## 7. Chapter 4 hooks (implementation deltas to describe there)

- Topology learning mechanics (ARP interception, hop-cache rebuilds), flow
  installation (DNAT/SNAT, conntrack), per-client vs per-connection flows.
- ReadinessGate (pending registry, app_ready admission, probe fallback,
  abandonment bound); warm leases and slow-start selection dimension (held
  constant in RQ3).
- Heartbeat intervals, absence timeout, staleness bounds, unknown-state
  defaults; bootstrap heartbeat.
- Aggregator window log and delivery-source implementations; environment-driven
  configuration surfaces (values → Appendix A).
- Chapter 5 exposure to ground here (from the Ch5→Ch3 audit, 2026-10-03):
  controller restart (what the robustness set exercises; what restart
  re-derives), the admission→routable path with the fixed servability defect
  (§5.4 provenance note), and container start-up variability (fast/slow-binding
  strata). Also: "no burst replay" is now stated in Ch3, and the action budget
  and classification margin have Ch3 anchors — no Ch5 item should be new.
