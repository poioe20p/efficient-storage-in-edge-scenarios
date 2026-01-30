# Implementation Plan: Link Debit (Port) Stats + Redirect Mongo Traffic

## Goal
Implement an OS-Ken controller feature that:
1. Continuously collects OpenFlow statistics that approximate **network debit per link** (interpreted as per-switch **port throughput**) for every datapath the controller manages.
2. Prints these stats periodically (first milestone).
3. Later: compares the debit of the MongoDB-facing link against a configurable threshold derived from the **overall network average**, and redirects Mongo traffic to an alternate MongoDB server when overloaded.

This document focuses on **Milestone 1** (collect + print stats), while laying out a clear path to the redirect behavior.

---

## Definitions
- **Datapath / Switch**: OpenFlow switch connected to the controller.
- **Link debit** (as used in this project): the **bitrate** observed on a switch port, computed from OpenFlow counters.
- **Port throughput**:
  - $rx\_bps = \frac{(rx\_bytes(t) - rx\_bytes(t-\Delta t))\times 8}{\Delta t}$
  - $tx\_bps = \frac{(tx\_bytes(t) - tx\_bytes(t-\Delta t))\times 8}{\Delta t}$
  - Optionally also print $total\_bps = rx\_bps + tx\_bps$.

---

## Scope & Target Code
Primary controller modules in this repo:
- `source/sdn_controller/osken_learn_and_log_n1.py` (LAN1)
- `source/sdn_controller/osken_learn_and_log_n2.py` (LAN2)

Milestone 1 should be implemented in **all controller variants you actually run** in the lab. If you run LAN1/LAN2 controllers separately, implement in `*_n1.py` and `*_n2.py`.

---

## Milestone 1: Collect & Print Port Stats ("all links")

### Which OpenFlow stats make sense here?
For **link debit / link utilization**, the most direct and robust counters are **port counters**:
- **Use:** `OFPPortStatsRequest` / `OFPPortStatsReply`
   - This directly exposes `rx_bytes` / `tx_bytes` per `port_no`, which is exactly what we need to compute per-link (per-port) bitrate.
   - This is the right fit for “stats for all links of each switch and print them”.

Support/optional stats that are often helpful:
- **Also consider:** `OFPPortDescStatsRequest` / `OFPPortDescStatsReply`
   - Gives port metadata (`name`, `hw_addr`, `curr_speed`, etc.).
   - Useful to make logs readable (e.g., print `port_name`) and to filter/ignore special ports.

Stats that are *not* the best primary signal for “link debit”:
- **Not for link debit:** `OFPDescStatsRequest` / `OFPDescStatsReply`
   - This is switch description (vendor strings, serial, etc.), not traffic counters.

Stats that become useful later (Milestone 4/5), but for different questions:
- **Use later (Mongo traffic only):** `OFPFlowStatsRequest` / `OFPFlowStatsReply`
   - Good if you want *application-specific* accounting (e.g., bytes for flows that match Mongo TCP ports) rather than total port utilization.
   - This answers “how much Mongo traffic” not “how loaded is the link overall”.
- **Use later (summaries):** `OFPAggregateStatsRequest` / `OFPAggregateStatsReply`
   - Good for fast totals across a match (e.g., all Mongo-matching flows) without listing every flow.

Multipart note:
- Many stats replies can be multipart (`OFPMPF_REQ_MORE`). For Milestone 1, start simple; if you observe multipart replies in practice, accumulate until `flags` no longer indicates “more” before printing a final sample.

### Why port stats?
OpenFlow `OFPPortStats` counters exist on every datapath and provide stable RX/TX byte counters per port. They are the simplest way to approximate “link debit” without needing a full topology graph first.

### Acceptance criteria
- For every connected datapath, the controller prints a periodic summary (every N seconds) including:
  - datapath id
  - port number
   - timestamp
  - `rx_bytes`, `tx_bytes` (cumulative)
  - `rx_bps`, `tx_bps` (computed from deltas)
- The print loop tolerates switches connecting/disconnecting without crashing.
- Stats are also persisted to MongoDB periodically (see Milestone 1b).

### Implementation steps
1. **Track active datapaths**
   - Add a `self._datapaths: dict[int, Datapath]`.
   - Register an `EventOFPStateChange` handler to add/remove datapaths when entering/leaving `MAIN_DISPATCHER`.

2. **Start a periodic polling green thread**
   - Use Eventlet (already monkey-patched in these apps) to spawn a periodic function in `__init__`.
   - Poll interval: start with `POLL_INTERVAL_SEC = 2` or `5`.

3. **Send `OFPPortStatsRequest` to each datapath**
   - For each datapath in `self._datapaths.values()`:
     - Build `OFPPortStatsRequest(datapath, 0, ofproto.OFPP_ANY)`.
     - `datapath.send_msg(request)`.

4. **Handle `EventOFPPortStatsReply`**
   - Implement a handler for `ofp_event.EventOFPPortStatsReply`.
   - For each `stat` entry in `event.msg.body`:
     - Extract `port_no`, `rx_bytes`, `tx_bytes`, and (optionally) packet/error counters.

5. **Compute bitrate from deltas**
   - Store last counters per `(dpid, port_no)`:
     - `self._last_port_counters[(dpid, port_no)] = {"ts": now, "rx_bytes": ..., "tx_bytes": ...}`
   - On each reply compute deltas and bps using wall-clock time between samples.
   - Handle counter resets (if deltas negative, treat as reset and skip rate for that sample).

6. **Print a stable, greppable log format**
   Suggested single-line format per port (matches the stated goal):
   - `PORT_DEBIT ts=<iso> dpid=<id> port=<no> total_bps=<...> rx_bps=<...> tx_bps=<...>`
   - Optionally include counters for debugging: `rx_bytes=<...> tx_bytes=<...>`

### Notes / gotchas
- Some ports may be “local” (e.g., `OFPP_LOCAL`) or have special numbers; decide whether to print all ports or filter these.
- If the switch returns stats for many ports, printing can be noisy; consider:
  - print only non-zero bps, or
  - print a compact table per datapath every K polls.

---

## Milestone 1b: Store Port Debit Stats in MongoDB (no sharding)

### Goal
Persist the same per-port debit samples you print in Milestone 1 into MongoDB **periodically**, without using the sharded/event “dpid range” scheme.

### Why “no sharding” is fine here
Port debit samples are time-series telemetry. For this use case:
- You typically query by time window (and maybe by datapath/port).
- Using a simple collection with indexes is enough for a lab-scale deployment.

### Data model (recommended)
Collection name (suggestion): `port_debit_samples`

Document example:
```json
{
   "ts": "2026-01-19T12:34:56",
   "ts_epoch": 1768826096.123,
   "controller": "osken_learn_and_log_n1",
   "dpid": 1,
   "port_no": 2,
   "rx_bytes": 123456,
   "tx_bytes": 654321,
   "rx_bps": 1000000.0,
   "tx_bps": 2000000.0,
   "total_bps": 3000000.0,
   "poll_interval_sec": 5.0,
   "ttl": 1768836896.123
}
```

Key points:
- Store both `ts` (ISO) and `ts_epoch` (float) to make queries and plotting easy.
- `ttl` is optional but strongly recommended so the collection doesn’t grow forever.

### Indexing
Create indexes once during bootstrap:
- TTL index on `ttl` (expireAfterSeconds=0)
- Compound index on `(dpid, port_no, ts_epoch)`

### Controller integration
1. Keep the poller/request/reply logic from Milestone 1.
2. For each computed sample, build a “sample doc” as above.
3. Insert asynchronously (Eventlet `spawn_n`) so stats writes never block dataplane handling.
4. Use a dedicated repository/collection for debit samples.

### Repository guidance (aligning with this repo)
This repo already has a Mongo abstraction pattern in:
- `source/sdn_controller/models/mongodb_host.py`
- `source/sdn_controller/repositories/repositories/*`

Already implemented building blocks you can reuse:
- The controller apps already use Eventlet (`eventlet.monkey_patch()`), so asynchronous inserts via `eventlet.spawn_n(...)` fit the existing style.
- Mongo URIs are already centralized via `MongodbRouter().get_simple_connection_string(add_app=True)`.
- The current `EventRepository` is intentionally tied to a sharded key strategy (replace by `_id==dpid`); do not reuse that approach for debit telemetry.

Recommended approach:
- Add a new repository (e.g., `PortDebitRepository`) and (optionally) a dataclass model.
- Use a **simple insert** (append-only) into `port_debit_samples`.
- Do not reuse the existing event sharding key logic for this telemetry.

---

## Milestone 2: Map “Ports” to “Links” (Optional but recommended)
To talk about “each link” rather than “each port”, you need to know what a port connects to.

Options:
1. **Topology discovery (LLDP)** using OS-Ken topology events
   - Use `os_ken.topology` APIs/events (`EventLinkAdd`, `get_link`, etc.) to learn switch-to-switch links.
   - Then label ports as `link_to_switch(dpid, port) -> neighbor_dpid`.

2. **Static mapping** from your lab scripts
   - If port numbering is deterministic in your OVS setup scripts, define a mapping table per network.

Milestone 1 does not depend on this; it becomes important when you specifically target the Mongo-facing port.

---

## Milestone 3: Identify the MongoDB-facing port(s)
Goal: determine, for each datapath, which **port** is the one that “faces” the MongoDB server (i.e., the switch port that forwards frames toward the Mongo host).

Important clarification (what “debit” means here):
- If you want the **debit of the link/port connected to Mongo** (overall utilization of that port, regardless of application), then:
   - Identify `mongo_port_no` and use **`OFPPortStats*`** on that `(dpid, mongo_port_no)`.
- If instead you want **only the Mongo traffic volume** (bytes attributable to Mongo flows), then:
   - Use **`OFPFlowStats*`** or **`OFPAggregateStats*`** with a match for Mongo (TCP dst 27017/27018 and/or IPv4 dst), and treat that as “Mongo traffic debit”.

In most overload scenarios you’ll likely want both:
- **Port debit** (is the physical/virtual link saturated?)
- **Mongo-traffic debit** (is Mongo the reason it is saturated?)

Practical approaches in this lab:
- **MAC learning correlation (best for L2 controllers)**: once the Mongo host MAC is observed, `mac_to_port[dpid][mongo_mac]` gives the edge port.
   - Already implemented: the learning-switch controllers already maintain `mac_to_port` per datapath inside their PacketIn handler.
- **Static MACs from the lab scripts (best if deterministic)**: if your `build_network_*.sh` assigns deterministic MAC addresses to Mongo containers, treat those as constants in controller config and resolve `mongo_port_no` via `mac_to_port`.
- **IP → MAC via ARP observation (if MAC is not known ahead of time)**:
   - When you observe ARP packets (`arp` protocol) for `10.0.0.4` / `10.0.1.4`, learn the corresponding sender/target MAC and pin it as the Mongo MAC.
- **Topology graph**: if you already compute a graph elsewhere, pick the first hop port from each switch toward the Mongo node.

Output of this milestone:
- A function `mongo_port_for_dpid(dpid) -> port_no | None`.

Once you have `mongo_port_for_dpid`, you can print the key metric you want:
- `MONGO_PORT_DEBIT dpid=<id> port=<mongo_port_no> total_bps=<...> rx_bps=<...> tx_bps=<...>`

---

## Milestone 4: Compute network average + threshold decision
Given per-port total bps:
1. Choose the set $S$ of ports to include in the “overall network average”:
   - All non-local ports, or
   - Only Mongo-facing ports across all switches, depending on your intent.
2. Compute average $avg\_bps = \frac{1}{|S|}\sum_{p\in S} total\_bps(p)$.
3. Overload test (example):
   - instantaneous overload if `mongo_port_total_bps > avg_bps * THRESHOLD_MULTIPLIER`.
   - sustained overload (recommended to avoid fluctuations):
     - overload only if the instantaneous condition is true for **N measurements in a row**.
     - example: with `poll_interval_sec = 5` and `N = 3`, you trigger after ~15 seconds.
     - example absolute threshold variant (no network-average): overload if `mongo_port_total_bps > 100_000_000` (100 Mbit/s) for 3 measurements in a row.

Config knobs (env vars or `config.py`):
- `STATS_POLL_INTERVAL_SEC`
- `DEBIT_THRESHOLD_MULTIPLIER` (e.g., 1.5, 2.0)
- Optional `DEBIT_THRESHOLD_BPS_ABS` (absolute cap)

---

## Milestone 5: Redirect Mongo traffic to alternate server

### Concrete model: Virtual IP (VIP) + Controller-selected backend (NAT in the switch)
Instead of “redirecting to an alternate server after overload”, introduce a **service IP** (virtual IP / VIP) that all clients target.
The controller then chooses the best backend **per new flow** using the cost signal:

- **Distance**: hop count (link-hops) from client host MAC to backend server MAC, computed from the topology graph.
- **Load**: backend server-facing port debit (bps), measured via `OFPPortStats` and already persisted by the stats apps.

This design matches the idea:
"Cliente contactar o serviço da server farm através dum IP virtual" and "router NAT implementado localmente no switch".

#### VIP example
- VIP: `10.0.0.100` (LAN1 example)
- VIP MAC: `aa:bb:cc:dd:ee:ff` (a stable virtual MAC)

Note: if you want one VIP per LAN, use e.g. `10.0.0.100` (LAN1) and `10.0.1.100` (LAN2). A single global VIP across both LANs requires a connected “cost graph” that includes the router/interconnect.

---

### Step 1 — Proactive ARP reply inside the switch (no controller involvement)
Install a high-priority ARP flow so the switch replies to ARP requests for the VIP directly.

Proactive ARP Reply Flow Rule (OpenFlow 1.3 with OVS/Nicira extensions):

```bash
ovs-ofctl -O OpenFlow13 add-flow s1 \
"priority=200,arp,arp_op=1,arp_tpa=10.0.0.100,actions=\\
move:NXM_OF_ETH_SRC[]->NXM_OF_ETH_DST[],\\
set_field:aa:bb:cc:dd:ee:ff->eth_src,\\
set_field:2->arp_op,\\
move:NXM_NX_ARP_SHA[]->NXM_NX_ARP_THA[],\\
set_field:aa:bb:cc:dd:ee:ff->arp_sha,\\
move:NXM_OF_ARP_SPA[]->NXM_OF_ARP_TPA[],\\
set_field:10.0.0.100->arp_spa,\\
IN_PORT"
```

Result: clients learn `10.0.0.100` → `aa:bb:cc:dd:ee:ff` and will send IPv4 packets to the VIP MAC.

Implementation note:
- This rule is easiest to inject from the setup scripts using `ovs-ofctl`.
- Installing this exact rule from OS-Ken may require Nicira action support; treat script injection as the reference approach.

---

### Step 2 — Send only “new service flows” to the controller
When the client sends the first packet to the VIP (ICMP echo now; TCP SYN later), ensure it generates a `PacketIn`.

Two practical ways:
1) Keep the table-miss to controller (already typical), but ensure packets to VIP are not matched by other higher-priority rules.
2) Add an explicit “punt VIP traffic” rule at higher priority than generic forwarding rules.

Example punt rules (LAN1 VIP):

- For ICMP to VIP:
   - Match: `ip,nw_dst=10.0.0.100,nw_proto=1`
- For TCP SYN to VIP (future):
   - Match: `tcp,nw_dst=10.0.0.100,tp_dst=27017`

Once a backend is chosen, the controller installs specific forward+reverse rules so subsequent packets do not go to the controller.

---

### Step 3 — Backend selection based on cost = hop + debit
When the controller receives the `PacketIn` for VIP traffic, it chooses the backend server that minimizes a score.

#### Inputs
1) Hop count (link-hops)
- Use the current `networkx` graph in the topology apps (`topology_n1.py` / `topology_n2.py`).
- `hops = len(nx.shortest_path(G, host_mac, server_mac)) - 1`

2) Server-facing port debit (bps)
- Read the most recent snapshot persisted by the stats app (`calculate_stats_n1.py` / `calculate_stats_n2.py`) via `DebitRepository.get_debit_by_lan_id(lan_id)`.
- The per-server debit you want is the entry where:
   - `neighbor_switch_id is None` (host-facing)
   - `peer_mac == server_mac`
   - `switch_id == server_access_switch_dpid` and `port_no == server_access_port_no` (from topology host attachment)

#### Score (example)
Start with a simple weighted sum:

- `score = hops + beta * debit_bps`

Later, normalize debit by a capacity or threshold:

- `score = hops + beta * (debit_bps / capacity_bps)`

Selection should be made per-flow (per ICMP “session” or per TCP 5-tuple) to keep session affinity.

---

### Step 4 — NAT-like rewrite rules (both directions)
After selecting a backend, the controller installs two rules:

#### 4.1 Forward rule (client → VIP) = DNAT
Goal: client sends to VIP, switch rewrites destination to the chosen backend.

Match (minimum for ICMP ping):
- `eth_type=0x0800` (IPv4)
- `ipv4_dst=VIP`
- `ip_proto=ICMP`
- `icmpv4_type=8` (echo request)

Actions:
- `set_field:backend_ip -> ipv4_dst`
- `set_field:backend_mac -> eth_dst`
- Forward along existing L2 path rules (or output toward the next hop).

#### 4.2 Reverse rule (backend → client) = SNAT
Goal: backend replies, switch rewrites source to VIP so the client thinks it is talking to the VIP.

Match (minimum for ICMP reply):
- `eth_type=0x0800`
- `ipv4_src=backend_ip`
- `ip_proto=ICMP`
- `icmpv4_type=0` (echo reply)

Actions:
- `set_field:VIP -> ipv4_src`
- `set_field:VIP_MAC -> eth_src`
- Forward to the client (existing L2 path rules).

Timeouts:
- Use `idle_timeout` so that new requests can be re-evaluated and potentially mapped to a different backend as debit changes.

TCP extension (future):
- Use per-5tuple matching (src/dst IP, src/dst port, proto) to keep a connection pinned to a backend.

---

### Step 5 — Observability
Log backend selection decisions in a greppable format (controller stdout):

- `VIP_SELECT lan_id=<lan_1> vip=10.0.0.100 client_mac=<...> backend_ip=<...> backend_mac=<...> hops=<n> debit_bps=<x> score=<y>`

Optional: persist these selections as a separate collection (append-only) so experiments can correlate routing decisions with observed debits.

---

## Test Scenario: VIP selection changes with debit

This scenario validates that:
1) clients use a single VIP (`10.0.0.100`) and get an ARP reply from the switch,
2) the controller chooses a backend using hop+debit,
3) the installed rewrite rules make the backend appear as the VIP.

### Preconditions
- Proactive ARP reply rule for VIP is installed on the client-facing switch.
- Port debit stats are being persisted (`debits` collection, `_id==lan_1` / `_id==lan_2`).
- At least 2 backend servers are available and included in the controller’s server list.

### Procedure (LAN1 example)
1) From a LAN1 client host, run `ping 10.0.0.100`.
2) Verify ARP resolution (should map to `aa:bb:cc:dd:ee:ff`).
3) Observe controller logs for `VIP_SELECT ...` showing chosen backend.
4) Generate load on one backend’s server-facing link (e.g., with iperf toward that backend IP).
5) After debit increases, start *new* VIP flows (new ping bursts or new TCP connections) and verify the controller selects the less-loaded / closer backend.

Expected outcomes:
- Pings to VIP succeed.
- Backend selection correlates with increasing debit (all else equal).
- Reply packets appear to come from VIP (source IP rewritten to VIP).

---

## Validation Plan

### Milestone 1–4 validation
- Verify port debit printing/persistence works (already covered by prior milestones).
- Verify topology graph includes the backend server MAC nodes and can compute paths.

### Milestone 5 validation (VIP anycast)
- Confirm ARP reply is handled in the switch:
   - `ovs-ofctl -O OpenFlow13 dump-flows <bridge>` shows the ARP reply rule.
- Confirm VIP traffic triggers controller selection only for the first packet:
   - first packet → `PacketIn`
   - subsequent packets → hit installed rewrite rules
- Confirm installed OpenFlow rules exist for both directions:
   - forward DNAT (VIP → backend)
   - reverse SNAT (backend → VIP)

