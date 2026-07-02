# Request Trace

This document describes the end-to-end request trace script that demonstrates
the full VIP routing pipeline. Given a client namespace and a curl command, the
script fires one request, collects the controller and edge-server logs from the
same time window, and formats the result into a readable trace.

**Location:** `source/scripts/testing/trace_request.sh`

---

## Overview

The trace flow is:

```text
CLIENT (namespace) -> VIP_SERVER (SDN controller selects edge server)
                   -> Edge Server (HTTP + MongoDB via VIP_DATA)
                   -> VIP_DATA (SDN controller selects storage node)
                   -> Response back to client
```

This is a debugging and demonstration tool. It proves that request routing,
edge selection, and storage selection are all functioning on the current
content-discovery routes.

---

## Prerequisites

1. The network is deployed.
2. At least one test client namespace exists, for example `lan1_client_1`.
3. Docker logs are accessible on the host.
4. `sudo` access is available for `ip netns exec`.

---

## CLI

```bash
sudo bash source/scripts/testing/trace_request.sh \
  --ns lan1_client_1 \
  -- curl -s "http://10.0.0.253:5000/content/lan1::content::001?requester=lan1::user::001"
```

| Flag | Required | Description |
| --- | --- | --- |
| `--ns` | yes | Client namespace that will send the request |
| `--` | yes | Separator; everything after it is the curl command to execute inside the namespace |

### Additional Examples

```bash
# Health check
sudo bash source/scripts/testing/trace_request.sh --ns lan1_client_1 \
  -- curl -s http://10.0.0.253:5000/health

# Local service-pressure query
sudo bash source/scripts/testing/trace_request.sh --ns lan1_client_1 \
  -- curl -s "http://10.0.0.253:5000/service_pressure?window_min=10&limit=10"

# Feed query
sudo bash source/scripts/testing/trace_request.sh --ns lan1_client_1 \
  -- curl -s "http://10.0.0.253:5000/feed/lan1::user::001?limit=10"

# Synthetic wait for WSM routing checks
sudo bash source/scripts/testing/trace_request.sh --ns lan1_client_1 \
  -- curl -s -X POST http://10.0.0.253:5000/wait_time \
     -H "Content-Type: application/json" -d '{"wait_time_ms": 500}'
```

---

## What The Script Traces

### 1. VIP_SERVER routing

When the client sends an HTTP request to `VIP_SERVER` (`10.0.0.253`), the SDN
controller intercepts the packet and selects an edge server with the WSM cost
function.

Typical log patterns:

```text
select_server: mac=<MAC> cpu=<pct> ram=<MB> req=<count> hops=<hops> cost=<cost>
select_server: selected=<MAC> cost=<cost> (tied=<count> rr_idx=<idx>)
vip_server: client=<client_IP> -> vip=10.0.0.253 -> real=<edge_server_IP>
dnat/snat installed: vip=10.0.0.253 -> real=<edge_server_IP> (idle=30s hard=120s)
```

### 2. Edge-server processing

For workload requests, the selected edge server processes HTTP locally and, if
needed, connects to MongoDB through `VIP_DATA`.

Typical log patterns:

```text
Created MongoClient for <lan> -> mongodb://<VIP_DATA_IP>:27018/ (maxIdleTimeMS=30000)
<client_IP> - - [<timestamp>] "GET /content/... HTTP/1.1" 200 -
<client_IP> - - [<timestamp>] "GET /feed/... HTTP/1.1" 200 -
Sending telemetry event: {server_id: ..., time_total_ms: ..., time_db_ms: ..., status_code: ...}
content_lookup error: <error message>
feed_ranking error: <error message>
```

### 3. VIP_DATA routing

When the edge server connects to `VIP_DATA` (`10.0.0.200` or `10.0.1.200`),
the SDN controller selects a storage node.

Typical log patterns:

```text
select_storage(<domain>): mac=<MAC> cpu=<pct> ram=<MB> conn=<count> lag=<sec> hops=<hops> cost=<cost>
select_storage(<domain>): selected=<MAC> cost=<cost> (tied=<count> rr_idx=<idx>)
vip_data(<domain>): client=<edge_server_IP> -> vip=<VIP_DATA_IP> -> real=<storage_IP>
dnat/snat installed: vip=<VIP_DATA_IP> -> real=<storage_IP> (idle=30s hard=120s)
```

If a DNAT flow is already cached, no new `vip_data(` log line will appear. The
packet is handled in the switch fast path, which is expected behavior.

### 4. Cross-LAN routing

If the request crosses LANs, the script also checks the peer SDN controller for
cross-network routing lines.

Typical cross-LAN patterns:

```text
dnat/snat: cross-network mac=<MAC> -> router port <port>
snat: cross-network, matching router mac=<ROUTER_MAC> instead of backend mac=<MAC>
```

---

## Infrastructure Mapping

| Client IP Range | LAN | SDN Controller | Edge Server | VIP_DATA |
| --- | --- | --- | --- | --- |
| `10.0.0.x` | lan1 | `osken` | `edge_server_n1` | `10.0.0.200` |
| `10.0.1.x` | lan2 | `osken_2` | `edge_server_n2` | `10.0.1.200` |

The script derives the LAN from the namespace IP and then picks the right
controller and edge-server container names.

---

## Example Output

A successful `content_lookup` request trace looks like this:

```text
==============================================================
  Request Trace: lan1_client_1 -> /content/lan1::content::001
  Client: IP=10.0.0.30  MAC=00:00:00:00:01:1e  LAN=lan1
==============================================================

-- 1. VIP_SERVER Routing (osken) ------------------------------
  select_server: mac=00:00:00:00:00:02 cpu=0.0 ram=2049.4 req=0 hops=1 cost=0.4000
  select_server: selected=00:00:00:00:00:02 cost=0.4000 (tied=1 rr_idx=5)
  vip_server: client=10.0.0.30 -> vip=10.0.0.253 -> real=10.0.0.2
  dnat/snat installed: vip=10.0.0.253 -> real=10.0.0.2 (idle=30s hard=120s)

-- 2. Edge Server (edge_server_n1) ----------------------------
  Created MongoClient for lan1 -> mongodb://10.0.0.200:27018/ (maxIdleTimeMS=30000)
  10.0.0.30 - - [02/Apr/2026 20:10:05] "GET /content/lan1::content::001?... HTTP/1.1" 200 -
  Sending telemetry event: {'server_id': '00:00:00:00:00:02', 'time_total_ms': 31.5, ...}

-- 3. VIP_DATA Routing (osken) -------------------------------
  select_storage(n1): mac=00:00:00:00:00:04 cpu=0.0 ram=512.0 conn=1.0 lag=0.00 hops=1 cost=0.3000
  select_storage(n1): selected=00:00:00:00:00:04 cost=0.3000 (tied=1 rr_idx=0)
  vip_data(n1): client=10.0.0.2 -> vip=10.0.0.200 -> real=10.0.0.4
  dnat/snat installed: vip=10.0.0.200 -> real=10.0.0.4 (idle=30s hard=120s)

-- Response ---------------------------------------------------
  HTTP 200
  {"_id":"lan1::content::001","relevance":{"relevance":"steady",...}}

==============================================================
```

When cached DNAT flows are reused, the routing sections can legitimately show
no new controller lines. That is not a failure; it means the switch handled the
request without a new controller round-trip.

---

## Notes

- The script traces controller and edge-server logs, not raw MongoDB logs.
- The time window is slightly widened around the curl execution so async
  telemetry events are captured.
- The examples above use the current content/user route naming. If you trace a
  historical run artifact, remember that older CSVs may still contain the
  pre-Phase-C request labels.
