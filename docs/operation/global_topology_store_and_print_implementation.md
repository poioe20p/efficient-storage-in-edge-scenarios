# Implementation Plan: Local Flow Rules + Store and Print Global Topology

Objective (only objective):

1. `topology_n1.py` installs proactive flow rules using **LAN1 local topology only**.
2. `topology_n2.py` installs proactive flow rules using **LAN2 local topology only**.
3. Both controllers **store their local topology** snapshots in MongoDB.
4. A **global topology** snapshot (LAN1 ∪ LAN2) is computed from MongoDB and **printed for observability only**.

No controller should ever install flows derived from the global/merged topology.

---

## 0) Files in Scope

- `source/sdn_controller/usecases/topology_n1.py`
- `source/sdn_controller/usecases/topology_n2.py`
- `source/sdn_controller/usecases/calculate_global_topology.py`
- `source/sdn_controller/repositories/repositories/topology.py`
- `source/sdn_controller/repositories/models/topology.py`

---

## 1) Acceptance Criteria

### Local flow rules
- LAN1 controller (`topology_n1.py`) calls `send_all_flow_rules_proactively()` only for paths computed on `self.net` built from LAN1 observations.
- LAN2 controller (`topology_n2.py`) calls `send_all_flow_rules_proactively()` only for paths computed on `self.net` built from LAN2 observations.
- There is no code path that swaps `self.net` to a global graph to install flows.

### Persistence
- MongoDB contains two documents:
  - `_id == "topology_lan1"`
  - `_id == "topology_lan2"`
- Each document can be read back and deserialized into `Topology(hosts=[Host...], links=[Link...], ...)` without exceptions.

### Global topology printing
- Once both snapshots exist, a global summary prints periodically (counts only; no full graph dumps).
- If one snapshot is missing, the controller prints the existing “missing topology” message and continues.

---

## 2) Data Contract (Snapshot Schema)

Both controllers must write the same schema.

### `Topology`
- `id`: string
  - LAN1: `"topology_lan1"`
  - LAN2: `"topology_lan2"`
- `timestamp`: ISO string with seconds precision
  - e.g. `2026-01-15T12:34:56`
- `ttl`: unix epoch seconds (float)
- `controller_name`: string
- `switchs`: list of dpids (keep type consistent)
  - Recommended: use OS-Ken datapath IDs as `int`

### `Host`
- `mac`: string
- `switch_dpid`: same type as `switchs`
- `port_no`: int

### `Link`
Use the dataclass field names from `source/sdn_controller/repositories/models/topology.py`:
- `src_dpid`
- `src_port_no`
- `dst_dpid`

Important note:
- Do not introduce `dst_port_no` unless you also extend the `Link` dataclass and repository serialization.

---

## 3) Fix MongoDB Round-Trip for Links (Repository Layer)

File: `source/sdn_controller/repositories/repositories/topology.py`

Problem:
- `_doc_to_topology()` expects `links` as a list of dicts to rebuild `Link(**link_doc)`.
- `_topology_to_doc()` must therefore serialize `Link` dataclasses into dicts.

Implementation:
- Change `_topology_to_doc()` so it stores:
  - `"links": [asdict(link) for link in topology.links]`

Acceptance:
- Writing + reading a topology snapshot works for both LAN1 and LAN2.

---

## 4) Controller Changes (LAN1 and LAN2)

### 4.1 Keep flow installs local

LAN1 (`topology_n1.py`):
- Remove/disable any use of `_apply_global_topology_flows(...)`.
- On local topology change, call only `_install_local_topology_flows()`.

LAN2 (`topology_n2.py`):
- Do not add any global-flow installation logic.
- Keep behavior: install local flows when local topology changes.

### 4.2 Persist local topology snapshots

In both controllers:
- On the existing print cadence (every 5 iterations) and on topology changes:
  - build `hosts_model: List[Host]`
  - build `links_model: List[Link]` using only `(src_dpid, dst_dpid, src_port_no)`
  - build `Topology(..., timestamp=<single ISO string>, ttl=<now + 3h>, controller_name=...)`
  - store via `TopologyRepository.insert_topology()`
- Keep DB writes async using `eventlet.spawn_n(...)`.

### 4.3 Print global topology (observe-only)

- After storing the local snapshot, call:
  - `snapshot = CalculateGlobalTopology().run()` (or reuse the instance you already have in LAN1).
- If `snapshot` is present, print a concise summary:
  - nodes/edges counts (`graph.number_of_nodes()`, `graph.number_of_edges()`)
  - switches/hosts/links counts
  - weakly connected components count

Recommendation to reduce duplicate logs:
- Print global topology in LAN1 only (LAN2 can store-only).

---

## 5) Validation Checklist

1) Bring up both controllers and the lab.

2) Confirm MongoDB has both snapshots:
- `topology_lan1`
- `topology_lan2`

3) Confirm global topology prints (LAN1 controller):
- Initially may say missing topology until both exist
- Then prints stable counts

4) Confirm flow behavior remains local:
- LAN1 controller installs only LAN1 host-to-host flows
- LAN2 controller installs only LAN2 host-to-host flows

---

## 6) Rollback Plan

- Revert changes in the repository serializer and both controllers.
- No script/Docker/OVS rollback needed (this task is controller + repo code only).
