# Request Trace — Implementation Plan

This document specifies the implementation of an end-to-end request trace script that demonstrates the full VIP routing pipeline working correctly. Given a client namespace and a curl command, the script fires the request, collects logs from every component the request touched (SDN controller + edge server), and formats them into a readable trace showing each hop in the lifecycle.

**Location:** `source/scripts/testing/trace_request.sh`

---

## Overview

A single bash script that produces a formatted trace of a request's journey through the platform:

```
CLIENT (namespace) → VIP_SERVER (SDN controller selects edge server)
                   → Edge Server (processes HTTP, connects to MongoDB via VIP_DATA)
                   → VIP_DATA (SDN controller selects storage node)
                   → Response back to client
```

The script is a debugging and demonstration tool — it proves the SDN routing, server selection (WSM cost function), and storage routing are all functioning as designed.

---

## Prerequisites

1. **Network deployed** — OVS bridges, containers, namespaces active
2. **At least one test client namespace** created (e.g., `lan1_client_1`)
3. **Docker accessible** — script calls `docker logs` on controller and edge server containers
4. **sudo access** — `ip netns exec` requires root

---

## CLI

```bash
sudo bash source/scripts/testing/trace_request.sh \
  --ns lan1_client_1 \
  -- curl -s "http://10.0.0.100:5000/device/lan1::device::001/latest?node_id=lan1::node::001"
```

| Flag | Required | Description |
|---|---|---|
| `--ns` | yes | Network namespace of the client to send the request from |
| `--` | yes | Separator; everything after this is the curl command to execute inside the namespace |

### Additional Examples

```bash
# Health check
sudo bash source/scripts/testing/trace_request.sh --ns lan1_client_1 \
  -- curl -s http://10.0.0.100:5000/health

# Anomaly detection query
sudo bash source/scripts/testing/trace_request.sh --ns lan1_client_1 \
  -- curl -s "http://10.0.0.100:5000/anomalies?region=lan1&window=1"

# Dashboard query
sudo bash source/scripts/testing/trace_request.sh --ns lan1_client_1 \
  -- curl -s "http://10.0.0.100:5000/dashboard/lan1::node::001?limit=10"

# Synthetic wait (for testing WSM load routing)
sudo bash tools/trace_request.sh --ns lan1_client_1 \
  -- curl -s -X POST http://10.0.0.100:5000/wait_time \
     -H "Content-Type: application/json" -d '{"wait_time_ms": 500}'
```

---

## What the Script Traces

The request lifecycle touches 4 platform components. The script collects relevant log lines from each.

### 1. VIP_SERVER Routing (SDN Controller)

When the client sends an HTTP request to `VIP_SERVER` (10.0.0.100), the SDN controller intercepts the packet and selects an edge server using the WSM cost function.

**Log patterns captured:**

```
select_server: mac=<MAC> cpu=<pct> ram=<MB> req=<count> hops=<hops> cost=<cost>
select_server: selected=<MAC> cost=<cost> (tied=<count> rr_idx=<idx>)
vip_server: client=<client_IP> -> vip=10.0.0.100 -> real=<edge_server_IP>
dnat/snat installed: vip=10.0.0.100 -> real=<edge_server_IP> (idle=30s hard=120s)
```

**Source:** `docker logs <controller>` filtered for client IP or `vip_server:` / `select_server:` / `dnat/snat`

### 2. Edge Server Processing

The selected edge server processes the HTTP request. For data endpoints, it connects to MongoDB through `VIP_DATA`.

**Log patterns captured:**

```
Created MongoClient for <lan> → mongodb://<VIP_DATA_IP>:27018/ (maxIdleTimeMS=30000)
<client_IP> - - [<timestamp>] "GET /device/... HTTP/1.1" 200 -
Sending telemetry event: {server_id: ..., time_total_ms: ..., time_db_ms: ..., status_code: ...}
device_latest error: <error message>
```

**Source:** `docker logs <edge_server>` filtered for client IP, `MongoClient`, `telemetry event`, or `error`

### 3. VIP_DATA Routing (SDN Controller)

When the edge server connects to `VIP_DATA` (10.0.0.200 or 10.0.1.200), the SDN controller intercepts and selects a storage node using the storage WSM cost function.

**Log patterns captured:**

```
select_storage(<domain>): mac=<MAC> cpu=<pct> ram=<MB> conn=<count> lag=<sec> hops=<hops> cost=<cost>
select_storage(<domain>): selected=<MAC> cost=<cost> (tied=<count> rr_idx=<idx>)
vip_data(<domain>): client=<edge_server_IP> -> vip=<VIP_DATA_IP> -> real=<storage_IP>
dnat/snat installed: vip=<VIP_DATA_IP> -> real=<storage_IP> (idle=30s hard=120s)
```

**Source:** same controller logs, filtered for edge server IP or `vip_data(` / `select_storage(`

**Note:** if the DNAT flow rule for this edge server→storage pair is already installed (from a recent request within the idle timeout window), no new `vip_data(` log line will appear — the packet matches the existing flow rule and bypasses the controller entirely. This is expected behavior.

### 4. Cross-LAN (if applicable)

If the request involves `VIP_DATA_N2` from LAN1 (or vice versa), the script also checks the peer SDN controller for routing logs.

**Additional patterns:**

```
dnat/snat: cross-network mac=<MAC> -> router port <port>
snat: cross-network, matching router mac=<ROUTER_MAC> instead of backend mac=<MAC>
```

---

## Infrastructure Mapping

The script uses these mappings to determine which containers to query:

| Client IP Range | LAN | SDN Controller | Edge Server | VIP_DATA |
|---|---|---|---|---|
| `10.0.0.x` | lan1 | `osken` | `edge_server_n1` | `10.0.0.200` |
| `10.0.1.x` | lan2 | `osken_2` | `edge_server_n2` | `10.0.1.200` |

```bash
# Derived from namespace IP
if [[ "$CLIENT_IP" == 10.0.0.* ]]; then
    LAN="lan1"; CONTROLLER="osken"; EDGE_SERVER="edge_server_n1"
    PEER_CONTROLLER="osken_2"
elif [[ "$CLIENT_IP" == 10.0.1.* ]]; then
    LAN="lan2"; CONTROLLER="osken_2"; EDGE_SERVER="edge_server_n2"
    PEER_CONTROLLER="osken"
fi
```

---

## Implementation

### Script Structure

```bash
#!/bin/bash
# ============================================================================
# trace_request.sh — End-to-end request trace for the edge platform
#
# Fires a single request from a client namespace, collects docker logs from
# the SDN controller and edge server, and formats a trace showing each hop
# in the VIP routing pipeline.
#
# Usage:
#   sudo bash trace_request.sh --ns <namespace> -- <curl command...>
# ============================================================================

set -euo pipefail
```

### Phase 1 — Argument Parsing

```bash
usage() {
    echo "Usage: $0 --ns <namespace> -- <curl command...>"
    echo ""
    echo "Options:"
    echo "  --ns    Network namespace of the client (e.g. lan1_client_1)"
    echo "  --      Separator; everything after is the curl command"
    echo ""
    echo "Example:"
    echo "  sudo $0 --ns lan1_client_1 -- curl -s http://10.0.0.100:5000/health"
    exit 1
}

NS=""
CURL_CMD=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --ns)   NS="$2"; shift 2 ;;
        --)     shift; CURL_CMD=("$@"); break ;;
        *)      usage ;;
    esac
done

[[ -z "$NS" ]]              && { echo "Error: --ns is required"; usage; }
[[ ${#CURL_CMD[@]} -eq 0 ]] && { echo "Error: curl command required after --"; usage; }
```

### Phase 2 — Network Discovery

Derive client IP and MAC from the namespace, then map to infrastructure containers.

```bash
# --- Derive client IP (first 10.x.x.x address on the namespace's veth) ---
CLIENT_IP=$(ip -n "$NS" -4 addr show \
    | grep -oP '(?<=inet\s)10\.\d+\.\d+\.\d+' | head -1)
[[ -z "$CLIENT_IP" ]] && { echo "Error: no 10.x.x.x IP in namespace $NS"; exit 1; }

# --- Derive client MAC ---
CLIENT_MAC=$(ip -n "$NS" link show \
    | grep -oP '(?<=link/ether\s)[0-9a-f:]+' | head -1)
[[ -z "$CLIENT_MAC" ]] && { echo "Error: no MAC in namespace $NS"; exit 1; }

# --- Map LAN ---
if [[ "$CLIENT_IP" == 10.0.0.* ]]; then
    LAN="lan1"; CONTROLLER="osken"; EDGE_SERVER="edge_server_n1"
    PEER_CONTROLLER="osken_2"
elif [[ "$CLIENT_IP" == 10.0.1.* ]]; then
    LAN="lan2"; CONTROLLER="osken_2"; EDGE_SERVER="edge_server_n2"
    PEER_CONTROLLER="osken"
else
    echo "Error: unexpected IP range $CLIENT_IP"; exit 1
fi
```

### Phase 3 — Execute Request with Timestamp Window

```bash
# --- Record start timestamp (1 second before for safety) ---
BEFORE_TS=$(date -u -d '-1 second' '+%Y-%m-%dT%H:%M:%S')

# --- Fire the request and capture response + HTTP status ---
RESPONSE=$(ip netns exec "$NS" "${CURL_CMD[@]}" \
    -w '\n%{http_code}' -o /dev/stdout 2>/dev/null) || true

# Split response body from HTTP status code (last line)
HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | sed '$d')

# --- Record end timestamp (5 seconds buffer for async telemetry) ---
AFTER_TS=$(date -u -d '+5 seconds' '+%Y-%m-%dT%H:%M:%S')
```

### Phase 4 — Collect & Filter Logs

```bash
# --- Helper: pull docker logs in time window ---
collect_logs() {
    local container="$1"
    docker logs "$container" --since "$BEFORE_TS" --until "$AFTER_TS" 2>&1
}

# --- Pull raw logs ---
CTRL_LOGS=$(collect_logs "$CONTROLLER")
EDGE_LOGS=$(collect_logs "$EDGE_SERVER")

# --- VIP_SERVER section ---
VIP_SERVER_LINES=$(echo "$CTRL_LOGS" | grep -E \
    "(select_server:|vip_server: client=$CLIENT_IP|dnat/snat installed:.*10\.0\.0\.100)" \
    || echo "  (no VIP_SERVER routing — DNAT flow may already be installed)")

# --- Edge server section ---
EDGE_LINES=$(echo "$EDGE_LOGS" | grep -E \
    "($CLIENT_IP|Created MongoClient|Sending telemetry event|error)" \
    || echo "  (no edge server logs in time window)")

# --- Extract the edge server IP that VIP_SERVER routed to ---
EDGE_IP=$(echo "$CTRL_LOGS" \
    | grep -F "vip_server: client=$CLIENT_IP" \
    | grep -oP '(?<=real=)\S+' | head -1 || true)

# --- VIP_DATA section ---
VIP_DATA_LINES=$(echo "$CTRL_LOGS" | grep -E \
    "(select_storage\(|vip_data\(|dnat/snat installed:.*10\.0\.[01]\.200)" \
    || echo "  (no VIP_DATA routing — DNAT flow may already be installed)")

# --- Cross-LAN check ---
PEER_LOGS=""
CROSS_LAN_LINES=""
if echo "$CTRL_LOGS" | grep -qE "cross-network"; then
    PEER_LOGS=$(collect_logs "$PEER_CONTROLLER")
    CROSS_LAN_LINES=$(echo "$PEER_LOGS" \
        | grep -E "(vip_data\(|select_storage\(|dnat/snat)" || true)
fi
```

### Phase 5 — Formatted Output

```bash
# --- ANSI colors (only when stdout is a terminal) ---
if [[ -t 1 ]]; then
    BOLD='\033[1m'; CYAN='\033[36m'; GREEN='\033[32m'
    YELLOW='\033[33m'; RED='\033[31m'; RESET='\033[0m'
else
    BOLD=''; CYAN=''; GREEN=''; YELLOW=''; RED=''; RESET=''
fi

# Determine result color from HTTP status
if [[ "$HTTP_CODE" == 2* ]]; then SC="$GREEN"
elif [[ "$HTTP_CODE" == 4* ]]; then SC="$YELLOW"
else SC="$RED"; fi

# Extract URL path for the header
URL_PATH=$(printf '%s ' "${CURL_CMD[@]}" \
    | grep -oP 'http://[^ ]+' | head -1 | sed 's|http://[^/]*||')
[[ -z "$URL_PATH" ]] && URL_PATH="(unknown path)"

echo ""
echo -e "${BOLD}══════════════════════════════════════════════════════════════${RESET}"
echo -e "${BOLD}  Request Trace: ${CYAN}${NS}${RESET}${BOLD} → ${URL_PATH}${RESET}"
echo -e "${BOLD}  Client: ${RESET}IP=${CLIENT_IP}  MAC=${CLIENT_MAC}  LAN=${LAN}"
echo -e "${BOLD}══════════════════════════════════════════════════════════════${RESET}"
echo ""

# Section 1: VIP_SERVER
echo -e "${BOLD}── 1. VIP_SERVER Routing (${CONTROLLER}) ──────────────────────${RESET}"
echo "$VIP_SERVER_LINES" | sed 's/^/  /'
echo ""

# Section 2: Edge Server
echo -e "${BOLD}── 2. Edge Server (${EDGE_SERVER}) ────────────────────────────${RESET}"
echo "$EDGE_LINES" | sed 's/^/  /'
echo ""

# Section 3: VIP_DATA
echo -e "${BOLD}── 3. VIP_DATA Routing (${CONTROLLER}) ────────────────────────${RESET}"
echo "$VIP_DATA_LINES" | sed 's/^/  /'
echo ""

# Section 4 (optional): Cross-LAN
if [[ -n "$CROSS_LAN_LINES" ]]; then
    echo -e "${BOLD}── 4. Cross-LAN Routing (${PEER_CONTROLLER}) ──────────────────${RESET}"
    echo "$CROSS_LAN_LINES" | sed 's/^/  /'
    echo ""
fi

# Response
echo -e "${BOLD}── Response ───────────────────────────────────────────────────${RESET}"
echo -e "  HTTP ${SC}${HTTP_CODE}${RESET}"
if [[ ${#BODY} -gt 200 ]]; then
    echo "  ${BODY:0:200}…"
else
    echo "  $BODY"
fi
echo ""
echo -e "${BOLD}══════════════════════════════════════════════════════════════${RESET}"
```

---

## Example Output

A successful `device_latest` request trace:

```
══════════════════════════════════════════════════════════════
  Request Trace: lan1_client_1 → /device/lan1::device::001/latest
  Client: IP=10.0.0.30  MAC=00:00:00:00:01:1e  LAN=lan1
══════════════════════════════════════════════════════════════

── 1. VIP_SERVER Routing (osken) ──────────────────────────────
  select_server: mac=00:00:00:00:00:02 cpu=0.0 ram=2049.4 req=0 hops=1 cost=0.4000
  select_server: selected=00:00:00:00:00:02 cost=0.4000 (tied=1 rr_idx=5)
  vip_server: client=10.0.0.30 -> vip=10.0.0.100 -> real=10.0.0.2
  dnat/snat installed: vip=10.0.0.100 -> real=10.0.0.2 (idle=30s hard=120s)

── 2. Edge Server (edge_server_n1) ────────────────────────────
  Created MongoClient for lan1 → mongodb://10.0.0.200:27018/ (maxIdleTimeMS=30000)
  10.0.0.30 - - [02/Apr/2026 20:10:05] "GET /device/lan1::device::001/latest ... HTTP/1.1" 200 -
  Sending telemetry event: {'server_id': '00:00:00:00:00:02', 'time_total_ms': 31.5, ...}

── 3. VIP_DATA Routing (osken) ────────────────────────────────
  select_storage(n1): mac=00:00:00:00:00:04 cpu=0.0 ram=512.0 conn=1.0 lag=0.00 hops=1 cost=0.3000
  select_storage(n1): selected=00:00:00:00:00:04 cost=0.3000 (tied=1 rr_idx=0)
  vip_data(n1): client=10.0.0.2 -> vip=10.0.0.200 -> real=10.0.0.4
  dnat/snat installed: vip=10.0.0.200 -> real=10.0.0.4 (idle=30s hard=120s)

── Response ───────────────────────────────────────────────────
  HTTP 200
  {"_id":"lan1::device::001","alert":true,"device_type":"pressure_sensor",...}

══════════════════════════════════════════════════════════════
```

When DNAT flows are already cached (second request within 30s idle timeout):

```
── 1. VIP_SERVER Routing (osken) ──────────────────────────────
  (no VIP_SERVER routing — DNAT flow may already be installed)

── 3. VIP_DATA Routing (osken) ────────────────────────────────
  (no VIP_DATA routing — DNAT flow may already be installed)
```

This is expected — the first request installs flow rules, and subsequent packets match them at the switch level without reaching the controller.

---

## Notes

- The script does **not** trace storage server (MongoDB) logs — only SDN controller + edge server, which is sufficient to demonstrate the routing pipeline.
- The time window is -1s before to +5s after the curl, to capture async telemetry events that the edge server sends after responding.
- `grep -E` is used instead of `grep -Ew` because `-w` (whole-word) breaks on patterns like `vip_data(n1)` where the character after `(` is a word character.
- If the response body exceeds 200 characters, it is truncated with `…` for readability.
