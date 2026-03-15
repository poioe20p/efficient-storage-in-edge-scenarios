# Implementation Plan: On-the-fly Cost = Hop Count + Mongo Server Link Debit

## Goal
Introduce a **cost** concept for routing/decision-making where the cost from **any host** to **each MongoDB server** is computed **on the fly** as:

- **Hop component**: number of **link-hops** on the shortest path (each traversed edge counts as 1).
- **Debit component**: the **server-facing port debit** (bps) already computed/printed/persisted by the stats controller (see `source/sdn_controller/calculate_stats_n1.py`).

This plan aligns with:
- Local topology discovery + `networkx` path computation in `source/sdn_controller/usecases/topology_n1.py` (and `topology_n2.py`).
- Server-link debit measured from OpenFlow **port stats** in `source/sdn_controller/calculate_stats_n1.py` (and `calculate_stats_n2.py`) and persisted in MongoDB via `DebitRepository`.

The outcome is a reusable primitive:

> `cost(host_mac -> server_mac) = f(hops, server_link_debit_bps)`

usable for observability, experiments, and later policies (e.g., load-based redirection).

---

## Definitions

### Link-hop
A **hop** is one graph edge traversal. With a `networkx` path:

- `path = nx.shortest_path(G, src, dst)`
- `hops = len(path) - 1`

This matches your requirement: hop should be link-hop.

### Server link debit (bps)
The **server link debit** is the value already produced in `calculate_stats_n1.py`:

- It polls `OFPPortStats` periodically.
- It computes a rate (`total_bps`) from counter deltas.
- It prints `PORT_RATE ... peer_mac=<server_mac>` only when the port is host-facing and `peer_mac in self.servers_mac`.
- It persists snapshots into MongoDB as a single document per LAN using `DebitRepository.upsert_debit_by_lan_id()`.

Relevant code anchors:
- Mongo persistence: `source/sdn_controller/library/repositories/debit.py`
- Data model: `source/sdn_controller/library/models/debit.py`
- Server MAC list: `source/sdn_controller/osken_learn_and_log.py` (`self.servers_mac = ["00:00:00:00:00:04", "00:00:00:00:00:07"]`)

---

## Constraints / Observations (Important)

1. **Topology nodes are MACs + DPIDs**
   - `topology_n1.py` builds a graph where host nodes are MAC strings and switch nodes are DPIDs.

2. **Router MACs are currently excluded**
   - `Topology_proactive` uses `_router_mac_blocklist` to filter hosts (router interfaces).
   - This is good for avoiding unwanted host entries for flow installation, but it has a consequence:
     - **Cross-network hop paths** (LAN1 host → LAN2 Mongo) will typically be **unreachable** in the merged global graph if the router is the “bridge” between LANs.

3. **Global topology is only an observation union**
   - `CalculateGlobalTopology` merges the stored snapshots but does not add inter-LAN links.

To support the requirement “any host to each server (each mongodb) in both networks”, you must decide whether you want:
- **Local costs only** (LAN1 hosts → LAN1 server(s), LAN2 hosts → LAN2 server(s)), or
- **Cross-LAN costs**, which require representing the router/interconnect in the cost graph.

This plan supports both, with an explicit milestone to enable cross-LAN reachability.

---

## Cost model (recommended options)

You want cost to increase with distance (hops) and with load (debit).

### Option A (simple additive, good default)
Normalize debit by a threshold (or capacity) and add a weighted term:

- `cost = hops + alpha * (server_debit_bps / threshold_bps)`

Where:
- `threshold_bps` can reuse `KenLearnAndLog.threashold_server_bps` (currently 1 Mbps) or be a separate config.
- `alpha` controls how much debit affects cost relative to one hop.

### Option B (penalize near saturation)
If you know a capacity `cap_bps`:

- `util = clamp(server_debit_bps / cap_bps, 0, 1)`
- `cost = hops + alpha * util^p` (e.g., `p=2` to strongly punish high utilization)

### Option C (multi-objective output)
Instead of a single scalar, return a tuple-like structure:

- `cost = {"hops": hops, "server_debit_bps": debit, "score": score}`

This is helpful for analysis and avoids prematurely committing to a scalar formula.

Recommendation:
- Start with **Option C** in storage/logging.
- Derive **Option A** score only where you need a single comparator.

---

## Data sources

### Topology graph (per LAN)
From `Topology_proactive.get_sws_links_hosts()`:
- Hosts: `(mac, dpid, port_no)`
- Links: `(src_dpid, dst_dpid, src_port_no)`
- Graph edges:
  - host → switch, switch → host (host-facing access)
  - switch → switch (inter-switch links)

### Debit snapshots (per LAN)
From MongoDB collection `debits`:
- Document `_id == lan_id` where lan_id is `"lan_1"` or `"lan_2"`.
- Fields: `DebitStats.port[]` entries with:
  - `switch_id`, `port_no`, `flow_rate` (bps), `peer_mac`, `neighbor_switch_id`

Important filtering (matches your definition of “server link debit”):
- choose entries where:
  - `neighbor_switch_id is None` (host-facing), and
  - `peer_mac in self.servers_mac` (Mongo hosts)

---

## Proposed architecture changes (no breaking behavior)

### 1) Add a “cost computation” helper to Topology apps
In `topology_n1.py` / `topology_n2.py`:
- Add helper methods (names illustrative):
  - `_get_hops(src_mac, dst_mac) -> int | None`
  - `_get_latest_server_debit_bps(lan_id, server_mac) -> float | None`
  - `compute_costs_to_servers() -> dict`

Keep this **read-only** relative to flow installation: do not change how flows are computed/installed.

### 2) Read debit from `DebitRepository`
- Instantiate `DebitRepository(MongodbRouter().get_simple_connection_string(add_app=True))`.
- Fetch latest snapshot via `get_debit_by_lan_id("lan_1")` or `get_debit_by_lan_id("lan_2")`.

Performance note:
- Do not query MongoDB for each (host,server) pair.
- Refresh debit snapshot on a timer (e.g., once per 5–10 seconds) and cache it.

### 3) Identify Mongo servers by MAC
Use the canonical source already in the controller base class:
- `KenLearnAndLog.servers_mac`

This keeps “which hosts are MongoDB” consistent across:
- stats printing/persistence, and
- cost calculation.

---

## Algorithm details

### Per-LAN cost computation
For each LAN controller (LAN1 and LAN2):

1. Build/refresh `self.net` as already done.
2. Determine servers present in the LAN topology:
   - `servers_present = [mac for mac in self.servers_mac if mac in self.net]`
3. Load cached debit snapshot for this LAN:
   - `debit_bps_by_server_mac = {peer_mac: flow_rate_bps}` from the latest `DebitStats`.
4. For every host MAC in `self.hosts` (including non-servers, excluding router MACs if you keep the blocklist):
   - for each server MAC in `servers_present`:
     - `hops = len(nx.shortest_path(self.net, host_mac, server_mac)) - 1` (handle `NoPath` / `NodeNotFound`)
     - `server_debit_bps = debit_bps_by_server_mac.get(server_mac)`
     - produce `cost_payload` per the chosen model.

Output shape (recommended):
```json
{
  "lan_1": {
    "<host_mac>": {
      "<server_mac>": {
        "hops": 3,
        "server_debit_bps": 12500000.0,
        "score": 4.25
      }
    }
  }
}
```

### Global “both networks” cost computation
If you truly need “any host to each server in both networks”:

- Build a **global cost graph** from `CalculateGlobalTopology._build_snapshot()`.
- Ensure the graph includes a path between LANs.

#### Critical milestone: make LAN1↔LAN2 connected in the cost graph
Because router MACs are currently filtered out, the merged graph may have **two disconnected components**.

Two workable approaches:

A) **Include router nodes in cost graph only** (recommended)
- Keep `_router_mac_blocklist` for flow install behavior.
- Create a second graph `self.cost_net` that is identical to `self.net` but also includes router hosts.
- Persist router hosts/links into topology snapshots (or synthesize them during global build).

B) **Static interconnect edge** (quickest for experiments)
- Add a synthetic edge between the LAN1 “gateway switch” and LAN2 “gateway switch” with weight=1.
- This yields stable cross-LAN hop counts without depending on host discovery for router MACs.

Once connected, compute hop costs in the global graph the same way:
- `hops(host_mac, server_mac) = len(shortest_path(global_graph, host, server)) - 1`

For the debit term in global costs:
- lookup server MAC in the correct LAN debit snapshot:
  - if `server_mac` is LAN1 server → use `lan_1` debit
  - if LAN2 server → use `lan_2` debit

---

## Persistence and observability

### Minimal observability (first milestone)
- Print cost summaries periodically in each topology controller:
  - `COST lan=lan_1 host=<mac> server=<mac> hops=<n> debit_bps=<x> score=<y>`

### Optional persistence
If you want costs stored:

Option 1: Store as a separate collection
- `cost_snapshots` with TTL
- keyed by `lan_id` and timestamp

Option 2: Store inside topology snapshot
- Extend `Topology` model to include `costs` (map/dict)
- Requires updating `TopologyRepository` serialization

Recommendation:
- Store costs in a **separate collection** initially to avoid changing topology schema and risking compatibility.

---

## Milestones

### Milestone 1 — Local cost (hop + debit) per LAN
- Add cost computation to `topology_n1.py` and `topology_n2.py`.
- Pull debit snapshots from `DebitRepository`.
- Print cost info periodically.

Acceptance:
- For servers present in that LAN, each host gets a `hops` value.
- Each server also has a `server_debit_bps` from the printed/stored stats.

### Milestone 2 — Cache debit snapshots
- Add a small refresh loop or timestamped cache to avoid frequent Mongo reads.

Acceptance:
- Cost computation does not spam MongoDB.

### Milestone 3 — Global cost across both LANs
- Implement a global cost graph and compute costs to **all servers**.

Acceptance:
- LAN1 host → LAN2 server hop count exists (not `NoPath`).

### Milestone 4 — Use cost in a policy (optional)
- Use computed scores to choose a server (or decide whether to redirect).

---

## Edge cases & handling

- **Server not discovered yet**: no host node → skip costs for that server.
- **Debit snapshot missing**: set `server_debit_bps=None`; still return hops.
- **No path**: return `hops=None`, `score=None`.
- **Router MAC filtered**: cross-LAN paths missing → requires Milestone 3 connectivity work.

---

## Validation checklist

1. Bring up the lab and controllers.
2. Confirm debit snapshots exist in MongoDB:
   - `_id=="lan_1"` and `_id=="lan_2"` in `debits`.
3. Confirm server-facing stats are printed:
   - `PORT_RATE ... peer_mac=<00:00:00:00:00:04 or 00:00:00:00:00:07>`
4. Confirm topology includes server MAC nodes (not filtered).
5. Confirm cost prints show:
   - `hops` increasing with distance
   - `server_debit_bps` matching the stats output

---

## Notes on configuration

Current relevant knobs:
- `KenLearnAndLog.servers_mac` in `source/sdn_controller/osken_learn_and_log.py`
- `KenLearnAndLog.threashold_server_bps` (can be reused for normalization)
- `CalculateSwitchPortDebit._lan_id` (`lan_1` / `lan_2`)

Recommended additional knobs (env vars or `config.py`):
- `COST_ALPHA` (debit weight)
- `SERVER_CAPACITY_BPS` (optional)
- `COST_PRINT_INTERVAL_SEC`
