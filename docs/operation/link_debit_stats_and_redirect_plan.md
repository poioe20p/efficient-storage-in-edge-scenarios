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
   - overload if `mongo_port_total_bps > avg_bps * THRESHOLD_MULTIPLIER`.

Config knobs (env vars or `config.py`):
- `STATS_POLL_INTERVAL_SEC`
- `DEBIT_THRESHOLD_MULTIPLIER` (e.g., 1.5, 2.0)
- Optional `DEBIT_THRESHOLD_BPS_ABS` (absolute cap)

---

## Milestone 5: Redirect Mongo traffic to alternate server

### Redirect model (high-level)
When overload is detected on the Mongo-facing port, redirect new flows destined to Mongo to a different Mongo server.

In OpenFlow 1.3 terms, redirection can be done by:
- Matching traffic for Mongo (L2 or L3 match):
  - `eth_type=0x0800`, `ip_proto=TCP`, `tcp_dst=27017/27018`, `ipv4_dst=<mongo_ip>`
  - or if you’re operating at L2 only: match `eth_dst=<mongo_mac>`
- Rewriting destination (and possibly source) fields:
  - `OFPActionSetField(ipv4_dst=<alt_mongo_ip>)`
  - `OFPActionSetField(eth_dst=<alt_mongo_mac>)`
- Output to the port leading to the alternate Mongo server.

### Important design choice
Decide whether you want:
- **Controller-only L2 behavior** (simpler, but requires known MACs), or
- **L3/L4-aware policy** (cleaner targeting Mongo traffic, but requires parsing/flow matches for IP/TCP).

### Safety / correctness constraints
- Ensure symmetry (return traffic) if you do L3 rewriting; otherwise connections may break.
- Prefer redirecting only **new** flows; avoid mid-connection rewrite.

---

## Test Scenario: Overload Detection + Partial Redirect (100M vs 25M)

This section defines a reproducible lab test to validate that:
1) the controller detects sustained overload on the **Mongo-facing port**, and
2) installs redirect rules that shift approximately **50%** of *new* Mongo traffic to the alternate MongoDB server.

### Test intent
- Drive asymmetric offered load:
   - **Server A (primary)** receives ~**100 Mbit/s** of Mongo-directed traffic.
   - **Server B (alternate)** receives ~**25 Mbit/s** baseline.
- Configure an overload threshold of **90 Mbit/s** on the primary’s Mongo-facing port.
- Require overload to persist for a configurable window before redirect triggers.

### Signals used for detection
- Primary signal (Milestone 1): `OFPPortStats` computed `total_bps` on the **Mongo-facing port**.
- Optional refinement (later milestone): `OFPFlowStats` filtered to Mongo TCP ports to isolate “Mongo traffic” from other link utilization.

### Suggested control-loop timing
These values aim to avoid flapping while keeping reaction time reasonable.

- Poll interval: **5 seconds** (already used in `calculate_stats_n1.py` / `calculate_stats_n2.py`).
- Trigger condition: **N consecutive samples** above threshold.
   - Recommended: `N = 3` → trigger after ~**15 seconds** above threshold.
   - More conservative: `N = 4` → ~**20 seconds**.
- Clear condition (hysteresis): require the port to stay below a lower threshold for M samples.
   - Example: `clear_threshold = 70 Mbit/s`, `M = 4` (~20 seconds).
- Cooldown: once redirect is enabled/disabled, wait **30–60 seconds** before changing state again.

Rationale:
- Port-rate samples can spike (queueing / bursty replies), and short spikes should not trigger redirects.
- A small hysteresis band prevents oscillation around the threshold.

### Redirect behavior (what “50%” means)
OpenFlow cannot reliably “split a single TCP flow 50/50” without breaking the connection. The practical goal is:
- Redirect ~50% of **new flows** (or new 5-tuples) to the alternate server.

Recommended mechanisms (ordered by practicality):

1) **Group table (type=SELECT) with weighted buckets**
    - Create a `SELECT` group with two buckets:
       - Bucket A → forward to primary Mongo
       - Bucket B → forward to alternate Mongo
    - Set equal weights (50/50). The selection is typically per-flow hash-based, which is what we want.
    - Apply to traffic matched as “Mongo-bound” (L2 MAC match or L3/L4 match).

2) **Controller-chosen per-flow rules**
    - For each new connection (first packet/PacketIn), decide destination (primary vs alternate) using a deterministic hash.
    - Install a flow entry for that 5-tuple to keep the connection stable.
    - This is more work but makes behavior explicit.

Important: if you do IP/port redirection (L3/L4), ensure return-path symmetry (or use a proper L4 proxy). L2-only redirection (matching `eth_dst=<mongo_mac>` and rewriting `eth_dst`) is simpler if MACs are stable.

### Concrete load-generation procedure

Prerequisites:
- The iperf generator is available and containers include `iperf3`.
- The controller can resolve “Mongo-facing port” (e.g., by learning `mongo_mac` and mapping `mac_to_port`).

Generate asymmetric load (example using UDP because it gives a controllable send rate):

1) Start background baseline to the alternate server (25 Mbit/s):
    - `iperf3 -u -b 25M -t 300 -c <ALT_MONGO_IP>` from a client host

2) Start higher load to the primary server (100 Mbit/s):
    - `iperf3 -u -b 100M -t 300 -c <PRIMARY_MONGO_IP>` from a client host

Notes:
- If you want to use the provided script, either run two separate invocations (one targeting each server) or extend the script to accept per-LAN bandwidth values (e.g., `--lan1-bandwidth` / `--lan2-bandwidth`).

### Expected controller behavior and observable outputs

During the first ~15–20 seconds:
- The primary controller prints `PORT_RATE ...` for the Mongo-facing port at ~100 Mbit/s.
- The overload counter increments each poll.

Once triggered:
- The controller logs something like:
   - `OVERLOAD_DETECTED dpid=<...> port=<mongo_port> bps=<...> threshold_bps=90000000 samples=3`
- The controller installs (or updates) redirect rules:
   - Either a `SELECT` group with ~50/50 weights, or
   - per-flow rules for new Mongo connections.

After redirect is active:
- The observed `total_bps` on the primary Mongo-facing port should drop (often not exactly 50/50 due to iperf timing and hashing).
- The alternate Mongo-facing port should increase.

Validation checklist:
- Confirm redirect rule is present in the switch:
   - `ovs-ofctl -O OpenFlow13 dump-flows <bridge>` and/or group dump if using groups.
- Confirm both servers receive traffic (iperf output on clients + port stats).
- Confirm the redirect state does not flap rapidly (hysteresis + cooldown working).

---

## Validation Plan

### Milestone 1 validation (required)
- Bring the lab up.
- Verify that controller logs show port stats for each connected datapath at the chosen interval.
- Confirm that stats change when generating traffic (e.g., ping/iperf between hosts).

### Later milestones (future)
- Generate load toward Mongo.
- Confirm overload detection triggers only when intended.
- Confirm traffic is redirected and Mongo remains reachable.

---

## Next action to implement after this plan
Implement Milestone 1 in the OS-Ken app(s) you run:
- Add datapath tracking, periodic `OFPPortStatsRequest`, and a stats-reply handler that prints computed bps per port.
