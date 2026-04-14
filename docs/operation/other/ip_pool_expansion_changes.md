# IP Pool Expansion — Required Code Changes

```
Static (unchanged):
  .1   router (gateway)
  .2   edge_server (compute)
  .3   (reserved)
  .4   edge_storage_server (MongoDB primary)
  .5   local_state_server (aggregator)

Dynamic nodes (elasticity):
  .6–.55   (50 IPs)
  LAN 1 veths: 100–149
  LAN 2 veths: 200–249

Test clients (namespace-based):
  .56–.105  (50 IPs)
  LAN 1 veths: 150–199
  LAN 2 veths: 250–299

VIPs:
  .253  VIP_SERVER  (was .100)
  .254  VIP_DATA    (was .200)

Reserved suffixes: 1, 253, 254
```

> **Goal:** Expand each LAN from 24 dynamic IPs to 100 (50 for elasticity nodes, 50 for test clients). Relocate VIPs from `.100`/`.200` to `.253`/`.254`.

## New IP/Veth Layout (per LAN)

---

## 1. `source/sdn_controller/elasticity/node_common.py`

**IpAllocator** — expand dynamic range from `.6–.29` to `.6–.55`.

```python
# ── BEFORE ──
class IpAllocator:
    """Per-LAN IP allocator for dynamic service nodes (.6–.29).

    Suffixes 1–5 are reserved for static infrastructure on each LAN:
        .1  router (default gateway)
        .2  edge_server (compute)
        .3  (reserved)
        .4  edge_storage_server (MongoDB primary)
        .5  local_state_server (aggregator)

    Dynamic nodes start at suffix 6 to avoid IP collisions.

    MAC addresses are derived deterministically:
        00:00:00:00:{lan:02x}:{suffix:02x}
    """

    _MIN_SUFFIX = 6
    _MAX_SUFFIX = 29

# ── AFTER ──
class IpAllocator:
    """Per-LAN IP allocator for dynamic service nodes (.6–.55).

    Suffixes 1–5 are reserved for static infrastructure on each LAN:
        .1  router (default gateway)
        .2  edge_server (compute)
        .3  (reserved)
        .4  edge_storage_server (MongoDB primary)
        .5  local_state_server (aggregator)

    Suffixes 56–105 are reserved for test clients (namespace-based).
    Suffixes 253–254 are reserved for VIPs (VIP_SERVER, VIP_DATA).

    Dynamic nodes start at suffix 6 to avoid IP collisions.

    MAC addresses are derived deterministically:
        00:00:00:00:{lan:02x}:{suffix:02x}
    """

    _MIN_SUFFIX = 6
    _MAX_SUFFIX = 55
```

---

## 2. `source/scripts/network/add_network_node.sh`

**Veth ranges + reserved suffixes** — expand and update VIP references.

```bash
# ── BEFORE ──
declare -A VETH_RANGE_START=( [1]=10 [2]=30 )
declare -A VETH_RANGE_END=( [1]=19 [2]=49 )
# .1 = gateway, .100 = VIP_Web, .200 = VIP_Data; test clients (namespace-based) use .30+
declare -A RESERVED_SUFFIX=( [1]="1 100 200" [2]="1 100 200" )

# ── AFTER ──
declare -A VETH_RANGE_START=( [1]=100 [2]=200 )
declare -A VETH_RANGE_END=( [1]=149 [2]=249 )
# .1 = gateway, .253 = VIP_SERVER, .254 = VIP_DATA; test clients (namespace-based) use .56+
declare -A RESERVED_SUFFIX=( [1]="1 253 254" [2]="1 253 254" )
```

---

## 3. `source/scripts/network/add_network_storage_node.sh`

Same changes as add_network_node.sh.

```bash
# ── BEFORE ──
declare -A VETH_RANGE_START=( [1]=10 [2]=30 )
declare -A VETH_RANGE_END=( [1]=19 [2]=49 )
# .1 = gateway, .100 = VIP_Web, .200 = VIP_Data; test clients (namespace-based) use .30+
declare -A RESERVED_SUFFIX=( [1]="1 100 200" [2]="1 100 200" )

# ── AFTER ──
declare -A VETH_RANGE_START=( [1]=100 [2]=200 )
declare -A VETH_RANGE_END=( [1]=149 [2]=249 )
# .1 = gateway, .253 = VIP_SERVER, .254 = VIP_DATA; test clients (namespace-based) use .56+
declare -A RESERVED_SUFFIX=( [1]="1 253 254" [2]="1 253 254" )
```

---

## 4. `source/scripts/network/clients/create_test_clients.sh`

**Four changes** — veth ranges, reserved suffixes, IP auto-assign start, and header comment.

### 4a. Header comment (lines 8-12)

```bash
# ── BEFORE ──
# Veth ranges reserved for test clients (must not overlap with service nodes):
#   LAN 1 → veth50–veth69  (service nodes use 10–19)
#   LAN 2 → veth70–veth89  (service nodes use 30–49)
#
# This separation prevents the SDN controller's find_free_veth_index() from
# exhausting its range when test clients are active simultaneously.

# ── AFTER ──
# Veth ranges reserved for test clients (must not overlap with service nodes):
#   LAN 1 → veth150–veth199  (service nodes use 100–149)
#   LAN 2 → veth250–veth299  (service nodes use 200–249)
#
# This separation prevents the SDN controller's find_free_veth_index() from
# exhausting its range when test clients are active simultaneously.
```

### 4b. Veth ranges + reserved suffixes (lines 25-29)

```bash
# ── BEFORE ──
# Test client veth ranges — separate from add_network_node.sh ranges (10–19, 30–49)
declare -A VETH_RANGE_START=( [1]=50 [2]=70 )
declare -A VETH_RANGE_END=(   [1]=69 [2]=89 )
# .1 = gateway, .100 = VIP_Web, .200 = VIP_Data
declare -A RESERVED_SUFFIX=( [1]="1 100 200" [2]="1 100 200" )

# ── AFTER ──
# Test client veth ranges — separate from add_network_node.sh ranges (100–149, 200–249)
declare -A VETH_RANGE_START=( [1]=150 [2]=250 )
declare -A VETH_RANGE_END=(   [1]=199 [2]=299 )
# .1 = gateway, .253 = VIP_SERVER, .254 = VIP_DATA
declare -A RESERVED_SUFFIX=( [1]="1 253 254" [2]="1 253 254" )
```

### 4c. auto_assign_ip() — IP start range (line ~131) and error message (line ~137)

```bash
# ── BEFORE ──
	# Start from .30 — octets .2–.29 are reserved for dynamic service nodes
	# added via add_network_node.sh / add_network_storage_node.sh.
	for host in $(seq 30 254); do

# ── AFTER ──
	# Start from .56 — octets .2–.55 are reserved for dynamic service nodes
	# added via add_network_node.sh / add_network_storage_node.sh.
	for host in $(seq 56 105); do
```

```bash
# ── BEFORE ──
	die "No free IP address available in ${subnet}.30-254 (test client range)."}

# ── AFTER ──
	die "No free IP address available in ${subnet}.56-105 (test client range)."}
```

---

## 5. `source/scripts/osken-controller.env`

**VIP IP addresses** — relocate to top of subnet. MACs are unchanged.

```env
# ── BEFORE ──
VIP_SERVER_IP=10.0.0.100
VIP_SERVER_MAC=aa:bb:cc:dd:ee:01

# Per-domain VIP_DATA — each domain has its own VIP address.
# When a server connects to VIP_DATA_N1 it is routed to LAN1's storage;
# connecting to VIP_DATA_N2 routes to LAN2's storage.
VIP_DATA_N1_IP=10.0.0.200
VIP_DATA_N1_MAC=aa:bb:cc:dd:ee:02
VIP_DATA_N2_IP=10.0.1.200
VIP_DATA_N2_MAC=aa:bb:cc:dd:ee:03

# ── AFTER ──
VIP_SERVER_IP=10.0.0.253
VIP_SERVER_MAC=aa:bb:cc:dd:ee:01

# Per-domain VIP_DATA — each domain has its own VIP address.
# When a server connects to VIP_DATA_N1 it is routed to LAN1's storage;
# connecting to VIP_DATA_N2 routes to LAN2's storage.
VIP_DATA_N1_IP=10.0.0.254
VIP_DATA_N1_MAC=aa:bb:cc:dd:ee:02
VIP_DATA_N2_IP=10.0.1.254
VIP_DATA_N2_MAC=aa:bb:cc:dd:ee:03
```

---

## 6. `source/sdn_controller/topology/topology.py`

**Fallback defaults** — must match osken-controller.env.

```python
# ── BEFORE ──
        self.vip_server_ip  = os.environ.get("VIP_SERVER_IP",  "10.0.0.100")
        self.vip_server_mac = os.environ.get("VIP_SERVER_MAC", "aa:bb:cc:dd:ee:01")

        # Per-domain VIP_DATA
        self.vip_data_n1_ip  = os.environ.get("VIP_DATA_N1_IP",  "10.0.0.200")
        self.vip_data_n1_mac = os.environ.get("VIP_DATA_N1_MAC", "aa:bb:cc:dd:ee:02")
        self.vip_data_n2_ip  = os.environ.get("VIP_DATA_N2_IP",  "10.0.1.200")
        self.vip_data_n2_mac = os.environ.get("VIP_DATA_N2_MAC", "aa:bb:cc:dd:ee:03")

# ── AFTER ──
        self.vip_server_ip  = os.environ.get("VIP_SERVER_IP",  "10.0.0.253")
        self.vip_server_mac = os.environ.get("VIP_SERVER_MAC", "aa:bb:cc:dd:ee:01")

        # Per-domain VIP_DATA
        self.vip_data_n1_ip  = os.environ.get("VIP_DATA_N1_IP",  "10.0.0.254")
        self.vip_data_n1_mac = os.environ.get("VIP_DATA_N1_MAC", "aa:bb:cc:dd:ee:02")
        self.vip_data_n2_ip  = os.environ.get("VIP_DATA_N2_IP",  "10.0.1.254")
        self.vip_data_n2_mac = os.environ.get("VIP_DATA_N2_MAC", "aa:bb:cc:dd:ee:03")
```

---

## 7. `source/docker/edge_server/source/app.py`

**Hardcoded VIP_DATA per domain**.

```python
# ── BEFORE ──
vip_data_per_domain = {
    "lan1": "10.0.0.200",
    "lan2": "10.0.1.200",
}

# ── AFTER ──
vip_data_per_domain = {
    "lan1": "10.0.0.254",
    "lan2": "10.0.1.254",
}
```

---

## 8. `source/scripts/test_conectivity.sh`

```bash
# ── BEFORE ──
VIP_SERVER=10.0.0.100        # shared VIP — punt rule installed on both switches
LAN1_VIP_DATA=10.0.0.200
LAN2_VIP_DATA=10.0.1.200

# ── AFTER ──
VIP_SERVER=10.0.0.253        # shared VIP — punt rule installed on both switches
LAN1_VIP_DATA=10.0.0.254
LAN2_VIP_DATA=10.0.1.254
```

---

## 9. `source/scripts/testing/run_experiment.sh`

```bash
# ── BEFORE ──
VIP="10.0.0.100:5000"

# ── AFTER ──
VIP="10.0.0.253:5000"
```

---

## 10. `source/scripts/testing/trace_request.sh`

Three occurrences of `10.0.0.100` → `10.0.0.253`:

```bash
# ── BEFORE ── (line 19)
#   sudo bash trace_request.sh --ns lan1_client_1 \
#     -- curl -s "http://10.0.0.100:5000/device/lan1::device::001/latest?node_id=lan1::node::001"

# ── AFTER ──
#   sudo bash trace_request.sh --ns lan1_client_1 \
#     -- curl -s "http://10.0.0.253:5000/device/lan1::device::001/latest?node_id=lan1::node::001"
```

```bash
# ── BEFORE ── (line 22)
#   sudo bash trace_request.sh --ns lan1_client_1 \
#     -- curl -s http://10.0.0.100:5000/health

# ── AFTER ──
#   sudo bash trace_request.sh --ns lan1_client_1 \
#     -- curl -s http://10.0.0.253:5000/health
```

```bash
# ── BEFORE ── (line 57)
  sudo $SCRIPT_NAME --ns lan1_client_1 \\
    -- curl -s "http://10.0.0.100:5000/device/lan1::device::001/latest?node_id=lan1::node::001"

# ── AFTER ──
  sudo $SCRIPT_NAME --ns lan1_client_1 \\
    -- curl -s "http://10.0.0.253:5000/device/lan1::device::001/latest?node_id=lan1::node::001"
```

---

## 11. `source/scripts/testing/traffic_generator.py`

Three occurrences of `10.0.0.100` → `10.0.0.253`:

```python
# ── BEFORE ── (line 18, docstring)
      [--vip 10.0.0.100:5000] \

# ── AFTER ──
      [--vip 10.0.0.253:5000] \
```

```python
# ── BEFORE ── (line 372)
        "--vip", default="10.0.0.100:5000",

# ── AFTER ──
        "--vip", default="10.0.0.253:5000",
```

```python
# ── BEFORE ── (line 373)
        help="VIP_SERVER address:port (default: 10.0.0.100:5000)"

# ── AFTER ──
        help="VIP_SERVER address:port (default: 10.0.0.253:5000)"
```

---

## 12. `source/scripts/tools/tools.txt`

Global find-and-replace: **all** occurrences of `10.0.0.100` → `10.0.0.253`.

This is an ad-hoc scratch file with many curl examples. All instances reference VIP_SERVER.

> **Note:** Line 11 uses `10.0.0.100:5555` (port 5555, not 5000). This is still VIP_SERVER — the port targets the edge-storage-server's ZMQ endpoint exposed on that IP. It should be updated to `10.0.0.253:5555` along with the rest.

---

## 13. `source/scripts/network/manage_rs_parity.sh`

**Reserved suffixes** — was already missing `.200`; update to new VIP suffixes.

```bash
# ── BEFORE ──
declare -A RESERVED_SUFFIX=(  [1]="1 100"                  [2]="1 100"                  )

# ── AFTER ──
declare -A RESERVED_SUFFIX=(  [1]="1 253 254"              [2]="1 253 254"              )
```

---

## 14. `source/scripts/network/clients/remove_test_clients.sh`

**Veth ranges** — must match `create_test_clients.sh`.

```bash
# ── BEFORE ──
# Test client veth range — must match create_test_clients.sh
declare -A VETH_RANGE_START=( [1]=50 [2]=70 )
declare -A VETH_RANGE_END=(   [1]=69 [2]=89 )

# ── AFTER ──
# Test client veth range — must match create_test_clients.sh
declare -A VETH_RANGE_START=( [1]=150 [2]=250 )
declare -A VETH_RANGE_END=(   [1]=199 [2]=299 )
```

---

## Files NOT Changed

| File                        | Reason                                                                          |
| --------------------------- | ------------------------------------------------------------------------------- |
| `build_network_1.sh`      | Static infra only; uses veth1–4, IPs .1/.2/.4/.5 — all outside dynamic ranges |
| `build_network_2.sh`      | Same as above; uses veth21–24                                                  |
| `vip_routing.py`          | Reads VIPs from topology attributes (no hardcoded IPs)                          |
| `remove_network_node.sh`  | Takes veth index as argument; no hardcoded ranges                               |
| `elasticity.py`           | Delegates IP allocation to `IpAllocator`; no hardcoded ranges                 |
| `compute_node_manager.py` | Passes IP/MAC from allocator through to script                                  |
| `storage_node_manager.py` | Same as above                                                                   |

---

## Verification Checklist

After applying all changes:

1. **No stale references:** `grep -rn "10\.0\.[01]\.100\|10\.0\.[01]\.200" source/` should return zero matches (excluding old experiment logs under `metrics/`)
2. **IpAllocator pool size:** `IpAllocator(1)` should yield 50 allocations (`.6–.55`) before raising `RuntimeError`
3. **No veth overlaps:** Static (1–4, 21–24) ∩ Dynamic (100–149, 200–249) ∩ Clients (150–199, 250–299) = ∅
4. **Connectivity:** Run `test_conectivity.sh` — VIPs respond at `.253`/`.254`
5. **End-to-end:** Short experiment confirming elasticity spawns and client traffic reach VIP
