# System Mechanisms — Operational Architecture Gateway

This document is the entry point for the operational architecture of the
SDN-based edge orchestration platform. It orients the reader and points to
authoritative subsystem overview pages for detailed mechanisms, configuration,
and implementation evolution.

---

## What This Repository Contains

The platform integrates network steering, compute elasticity, and storage
placement under a single SDN control loop:

1. **OS-Ken SDN controller** — a Python-based OpenFlow controller that
   intercepts traffic destined for virtual IPs, selects backends, and installs
   flow rules.
2. **OVS-based network steering** — Open vSwitch bridges perform DNAT/SNAT
   rewriting in the data plane after the controller installs flow rules.
3. **Containerized edge servers** — Flask-based HTTP servers that handle
   client requests, report per-request telemetry, and consult controller-
   broadcast manifests for Tier 1 selective-sync short-circuiting.
4. **MongoDB-based storage placement** — replica sets partitioned by network
   origin with adaptive tier transitions: remote reads (Tier 0), selective
   sync nodes (Tier 1), and full replica-set extension (Tier 2).
5. **Telemetry aggregation** — per-network aggregators collect latency and
   resource metrics via ZeroMQ, publish windowed summaries, and feed both VIP
   routing decisions and elasticity thresholds.
6. **Elasticity-driven mutation** — a priority-queue-based elasticity manager
   spawns and removes compute and storage containers in response to sustained
   latency degradation or underutilisation.

---

## System Architecture at a Glance

### Three Execution Contexts

The controller runs three concurrent execution contexts, each with a distinct
responsibility and no shared mutable state:

| Context | Type | Responsibility |
|:---|:---|:---|
| Thread 1 — Fast path | OS-Ken event loop + greenthreads | Handles every OpenFlow packet-in, selects backends via WSM cost functions, installs DNAT/SNAT flow rules. Strictly non-blocking. |
| Telemetry greenthread | ZMQ subscriber (eventlet) | Receives windowed telemetry summaries, updates in-memory state for Thread 1 scoring, evaluates degradation thresholds, and submits typed alerts to Thread 3. |
| Thread 3 — Slow path | Python daemon thread | Blocks on a priority queue, pops alerts, and mutates infrastructure (spawn/remove containers, update VIP pools). |

### Traffic Split

The platform separates traffic into four distinct flows:

1. **`VIP_SERVER`** — client-to-server HTTP traffic. The controller selects
   the best edge server per request.
2. **`VIP_DATA`** — server-to-MongoDB traffic, per network domain
   (`VIP_DATA_N1`, `VIP_DATA_N2`). The controller selects the best storage
   backend.
3. **Telemetry flow** — edge servers and MongoDB sidecars push metrics via
   ZeroMQ to per-network aggregators, which publish windowed summaries to the
   controller.
4. **Elasticity actions** — Thread 3 provisions or removes compute/storage
   containers and updates VIP pools; these are slow infrastructure mutations,
   not per-packet decisions.

See the [VIP Routing Overview](vip_routing/vip_routing_overview.md) for the
full traffic-handling architecture.

---

## Runtime Responsibilities

### Controller Fast Path (Thread 1)

Intercepts VIP-addressed packets, scores candidate backends using
multi-dimensional WSM cost functions fed by in-memory telemetry state, installs
DNAT/SNAT flow rule pairs, and outputs the first packet. Subsequent packets in
the same flow are handled entirely in the OVS switch without controller
involvement.

→ Authority: [VIP Routing Overview](vip_routing/vip_routing_overview.md)

### Telemetry Observation Path (Telemetry Greenthread)

Receives `TelemetrySummary` messages via ZMQ SUB from both per-network
aggregators. Updates `_server_stats` and `_storage_stats` dicts (read by
Thread 1 for WSM scoring). Evaluates domain-level degradation scores against
adaptive thresholds and submits typed alerts to Thread 3's priority queue.
Also processes control events (`drain_complete`, `rs_secondary_ready`) for
lifecycle management.

→ Authority: [Telemetry Overview](telemetry/telemetry_overview.md)

### Elasticity and Placement Path (Thread 3)

Blocking on a `queue.PriorityQueue`, pops alerts in priority order, and
dispatches to handlers that spawn or drain containers. Compute and storage
scale independently — a compute bottleneck does not trigger data placement
changes, and a data locality problem does not spawn web servers.

→ Authority: [Elasticity Overview](elasticy_manager/elasticity_overview.md)

### Edge Server Role

Each edge server is a Flask container that handles HTTP requests in a
dedicated thread. It connects to `VIP_DATA_N*` for all MongoDB access — the
driver never discovers physical `mongod` topology. After each request it
pushes a per-request telemetry event via ZMQ PUSH. For Tier 1 selective sync,
the `cached_collection(...)` wrapper consults a controller-broadcast manifest
and short-circuits eligible point reads to a local standalone `mongod`; all
other reads and every write fall through to `VIP_DATA`.

→ Authority: [Selective Sync Overview](selective_sync/selective_sync_overview.md)

### Storage Role

Each storage container runs a bare `mongod` with a Python sidecar that reports
`mongo_stats` (replication lag, member state, connections, CPU, RAM) via ZMQ
PUSH. Storage nodes are members of per-network replica sets. The sidecar
handles async `rs.add()` for dynamic nodes and emits `rs_secondary_ready`
control events for deferred VIP_DATA promotion.

→ Authority: [Elasticity Overview](elasticy_manager/elasticity_overview.md)
and [VIP Routing Overview](vip_routing/vip_routing_overview.md)

---

## Data Placement Tiers

The platform uses three tiers of data placement, triggered by sustained demand
signals. Tier transitions are workload-agnostic — they react to measured
latency, not to application semantics.

### Tier 0 — Direct Routing

The base state. Each network has its own replica set primary. Cross-network
reads are served by routing packets over `VIP_DATA` to the remote primary.
No local copy exists.

### Tier 1 — Selective Sync Node

A standalone `mongod` deployed in the **consumer LAN**, seeded with only the
hot subset of documents being read cross-region. One Change Stream per hot
collection (with a `$match` filter on the hot document IDs) keeps the node
current. Tier 1 selection is **client-side and manifest-driven**: the edge
server's `cached_collection(...)` wrapper consults the controller-broadcast
`tier1_manifest` and short-circuits eligible point-lookup reads to the local
standalone `mongod`. Cold reads and all writes still fall through to
`VIP_DATA` as normal. The controller does **not** route `VIP_DATA` to the
selective-sync node.

Feature-flagged behind `SS_ENABLED` (default off).

### Tier 2 — Full Replica

A full replica-set secondary added via `rs.add()`. MongoDB oplog replication
runs autonomously. `VIP_DATA` routes to the local secondary for all reads in
that domain. Used when sustained demand justifies the full replication
footprint.

→ Authority: [Selective Sync Overview](selective_sync/selective_sync_overview.md)
for Tier 1; [Elasticity Overview](elasticy_manager/elasticity_overview.md)
for Tier 2 triggers.

---

## Where to Read Next

This section is the main handoff surface — each entry points to the canonical
subsystem overview.

| Subsystem | Document | Summary |
|:---|:---|:---|
| VIP Routing | [VIP Routing Overview](vip_routing/vip_routing_overview.md) | VIP interception, ARP handling, WSM backend selection, DNAT/SNAT flow installation, cross-network forwarding, edge-side epoch and recovery model |
| Telemetry | [Telemetry Overview](telemetry/telemetry_overview.md) | Producer-side metrics, per-network aggregation, controller-side consumption for routing and elasticity, control-event dispatch |
| Topology | [Topology Overview](topology/topology_overview.md) | Local discovery, hop-cache computation, VIP pool rebuild, peer topology sharing via ZMQ PUB/SUB, MAC-role propagation |
| Elasticity | [Elasticity Overview](elasticy_manager/elasticity_overview.md) | Alert types and priority, compute/storage scale-up triggers and adaptive thresholds, scale-down AND-gate sliding window, two-phase drain, anti-thrashing mechanisms |
| Selective Sync | [Selective Sync Overview](selective_sync/selective_sync_overview.md) | Tier 1 promotion predicate, Change-Stream forwarder architecture, manifest protocol, client-side short-circuiting, two-phase teardown, cooldown and drain signals |
| Testing | `testing/` directory | Traffic generator, compute-load harness, trace-request tooling, analysis toolchain |
| Scenarios | [System Scenarios](system_scenarios.md) | Concise walkthroughs of VIP interception, telemetry propagation, compute/storage scale-up and scale-down, and selective-sync promotion |

---

## Repository Navigation

Key folders for a new reader:

| Folder | Purpose |
|:---|:---|
| `source/sdn_controller/` | OS-Ken SDN controller — VIP routing, elasticity, telemetry consumption, topology discovery, selective-sync coordination |
| `source/docker/` | Container images — edge server, edge storage server, edge selective storage, OVS, OS-Ken, local state server, NAT router |
| `source/scripts/` | Build, network setup, cleanup, testing harness, WAN emulation, and tool scripts |
| `docs/operation/` | Operational documentation — this gateway, subsystem overviews, testing references, and archived historical plans |
| `tese/` | Thesis manuscript (LaTeX) — chapters, bibliography, and research-question notes |

---

## Documentation Lifecycle

The `docs/` tree uses a consistent lifecycle so readers can tell at a glance
whether a document describes current behaviour, in-progress work, or
historical context.

### Current Reference Documents

These describe the landed baseline. They use descriptive names (e.g.
`*_overview.md`) rather than plan-style filenames.

- `system_mechanisms.md` (this file)
- `system_scenarios.md`
- `vip_routing/vip_routing_overview.md`
- `telemetry/telemetry_overview.md`
- `topology/topology_overview.md`
- `elasticy_manager/elasticity_overview.md`
- `selective_sync/selective_sync_overview.md`
- Testing references in `testing/`
- Stable tooling references in `other/`

### Active Plans Kept in Place

These `*_plan.md` files describe approved but not-yet-landed work. They stay
in the active tree so they are visible alongside the subsystems they affect.

- `other/micro_breaker_and_service_logs_plan.md`
- `other/edge_storage_connection_hard_failure_epoch_plan.md`
- Plans under `vip_routing/implementation/plans/`
- Plans under `elasticy_manager/implementation/`

### Implemented Phase Folders Kept in Place

Phased implementation folders (e.g. `implemented_02_*`, `implemented_03_*`)
remain in the tree as implementation history and optional follow-on tracking.
The overview documents above are the canonical reference for the landed
baseline; the phase folders capture the order and rationale of incremental
delivery.

### Archived Historical Plans

Plans that have fully landed and are no longer active live under
`docs/operation/archive/`. They are preserved because they explain why the
current mechanism behaves the way it does.

### Naming and Archival Guidance

- **Current reference docs** should avoid `*_plan.md` filenames when they
  describe landed behaviour or stable tooling.
- **Active plans** use `*_plan.md` and stay in the subsystem directory they
  affect until fully landed.
- **Implemented phase folders** stay in place as history; do not expand them
  with new work.
- **Historical plans** move to `archive/` after landing. Experiment result
  files and campaign briefs remain in the active tree because they are
  records, not pending work.
