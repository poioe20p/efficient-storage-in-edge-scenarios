# Plan: Per-LAN VIP_SERVER (Dual VIP_SERVER N1 + N2)

**Status**: Awaiting approval  
**Date**: 2026-07-06  
**Scope**: Add `VIP_SERVER_N2` (`10.0.1.253`, MAC `aa:bb:cc:dd:ee:04`) so each SDN controller routes its own LAN's client-facing HTTP traffic.

## Motivation

Currently `VIP_SERVER` exists only at `10.0.0.253` on LAN1. ALL client traffic — from both LAN1 and LAN2 — goes through this single VIP. The LAN1 controller (`osken`) makes **every** client-facing routing decision; LAN2's controller (`osken_2`) never routes a single HTTP request.

This is a critical gap for RQ2 ("does SDN controller co-location eliminate routing-plane coordination gaps?") because:

1. LAN2's backend-selection policy is never exercised for client traffic
2. LAN2 clients cross the WAN (50ms RTT) just to reach the VIP before any routing decision
3. Real edge deployments have per-region load balancers — single global VIP is architecturally unusual

Adding `VIP_SERVER_N2` makes each controller independently exercise the policy for its own LAN's traffic.

## Files to Modify (9 files)

### A. SDN Controller (4 files)

| # | File | Change |
|---|------|--------|
| A1 | `source/sdn_controller/topology/topology.py` | Add `vip_server_n2_ip` / `vip_server_n2_mac` env vars; update comment |
| A2 | `source/sdn_controller/_vip_routing/ingress.py` | Add N2 to `_iter_vip_bindings()` and `handle_vip_packet_in()` dispatch; parameterize `_handle_vip_server()` to use the correct VIP IP/MAC |
| A3 | `source/sdn_controller/elasticity/node_common.py` | Update IpAllocator docstring: `.253` and `.254` lines |
| A4 | `source/sdn_controller/vip_routing.py` | Update `VipRoutingMixin` class docstring to list new `vip_server_n2_*` attributes |

### B. Environment Files (1 file)

| # | File | Change |
|---|------|--------|
| B1 | `source/scripts/osken-controller.env` | Add `VIP_SERVER_N2_IP=10.0.1.253` / `VIP_SERVER_N2_MAC=aa:bb:cc:dd:ee:04` |

> **Why no override files?** `VIP_SERVER_N2_*` are topology constants — they don't vary across `topology_host`, `topology_slowstart`, or `topology_lifecycle`. The base `osken-controller.env` (B1) is sufficient. Adding them to override files creates redundant copies of a value that should only exist in one place.

### C. Testing Scripts (3 files)

| # | File | Change |
|---|------|--------|
| C1 | `source/scripts/testing/run_experiment.sh` | Replace single `VIP="10.0.0.253:5000"` with `VIP_LAN1`/`VIP_LAN2`; pass both to traffic_generator |
| C2 | `source/scripts/testing/traffic_generator.py` | Replace `--vip` with `--vip-lan1`/`--vip-lan2`; use correct VIP per `client_lan` |
| C3 | `source/scripts/Makefile` | No changes needed. The Makefile passes `OSKEN_ENV_OVERRIDE_FILE` through to `build_network_setup.sh` (for controller env) and delegates all VIP addressing to `run_experiment.sh`'s internal `VIP_LAN1`/`VIP_LAN2` defaults. Neither the `setup_network` nor `run_experiment` Makefile targets reference VIP addresses. |

### D. Documentation (1 file)

| # | File | Change |
|---|------|--------|
| D1 | `docs/operation/vip_routing/vip_routing_overview.md` | Document dual VIP_SERVER model (Architecture Summary, Thread 1 dispatch, diagram references) |

---

## Detailed Changes

### A1. `topology/topology.py`

**Location**: After line 28 (the blank line after `vip_server_mac`), before the `# Per-domain VIP_DATA` comment at line 29.

**Change 1** — Update the comment on line 24 from:
```python
        # Global VIPs — identical on both controllers
```
to:
```python
        # VIP_SERVER — one per LAN. N1 (LAN1) uses vip_server_*; N2 (LAN2) uses vip_server_n2_*.
```

**Change 2** — Add N2 VIP vars immediately after `vip_server_mac`, mirroring the contiguous `vip_data_n1`/`vip_data_n2` pattern:

```python
        self.vip_server_ip  = os.environ.get("VIP_SERVER_IP",  "10.0.0.253")
        self.vip_server_mac = os.environ.get("VIP_SERVER_MAC", "aa:bb:cc:dd:ee:01")
        self.vip_server_n2_ip  = os.environ.get("VIP_SERVER_N2_IP",  "10.0.1.253")
        self.vip_server_n2_mac = os.environ.get("VIP_SERVER_N2_MAC", "aa:bb:cc:dd:ee:04")
```

Keep existing `vip_server_ip`/`vip_server_mac` as-is (they serve as N1). Add only the N2 pair, no separator comment — same style as VIP_DATA.

### A2. `_vip_routing/ingress.py`

**Change 1** — `_iter_vip_bindings()` (line 14-16): Add N2 binding:

```python
def _iter_vip_bindings(controller):
    yield (controller.vip_server_ip, controller.vip_server_mac, "server")
    yield (controller.vip_server_n2_ip, controller.vip_server_n2_mac, "server_n2")
    yield (controller.vip_data_n1_ip, controller.vip_data_n1_mac, "n1")
    yield (controller.vip_data_n2_ip, controller.vip_data_n2_mac, "n2")
```

**Change 2** — `handle_vip_packet_in()` (after line 72): Add N2 dispatch:

```python
if dst_ip == controller.vip_server_ip:
    logger.debug("vip server packet-in: dpid=%s in_port=%s ip=%s", datapath.id, in_port, ip_pkt)
    return _handle_vip_server(controller, datapath, in_port, pkt, src_mac, src_ip, ip_proto)
if dst_ip == controller.vip_server_n2_ip:
    logger.debug("vip server n2 packet-in: dpid=%s in_port=%s ip=%s", datapath.id, in_port, ip_pkt)
    return _handle_vip_server(controller, datapath, in_port, pkt, src_mac, src_ip, ip_proto)
```

**Change 3** — `_handle_vip_server()` (line ~137): Parameterize which VIP IP/MAC to use in the DNAT/SNAT flow. Currently it hardcodes `controller.vip_server_ip` and `controller.vip_server_mac`. Add VIP resolution at the top:

```python
def _handle_vip_server(controller, datapath, in_port, pkt, src_mac, src_ip, ip_proto) -> bool:
    # Determine which VIP was hit
    ip_pkt = pkt.get_protocol(ipv4.ipv4)
    dst_ip = ip_pkt.dst
    if dst_ip == controller.vip_server_n2_ip:
        vip_ip, vip_mac = controller.vip_server_n2_ip, controller.vip_server_n2_mac
    else:
        vip_ip, vip_mac = controller.vip_server_ip, controller.vip_server_mac

    server = selection.select_server(controller, src_mac)
    # ... (rest unchanged)

    # Use vip_ip/vip_mac instead of controller.vip_server_ip/controller.vip_server_mac
    flows.install_vip_dnat_snat(
        controller, datapath, in_port, pkt,
        client_mac=src_mac, client_ip=src_ip, ip_proto=ip_proto,
        vip_ip=vip_ip, vip_mac=vip_mac,
        real_backend_ip=server_ip, real_backend_mac=server_mac,
    )

    logger.info(
        "vip_server: client=%s -> vip=%s -> real=%s",
        src_ip, vip_ip, server_ip,
    )
    return True
```

### A3. `elasticity/node_common.py`

**Location**: IpAllocator docstring (line ~222).

**Change**: Update VIP reservation comment. Both `.253` and `.254` lines are updated — `.253` for the new per-LAN VIP_SERVER, `.254` as a doc fix for already-existing per-domain VIP_DATA:

```python
    Suffixes 252–254 are reserved for VIPs:
        .252 recovery VIP_DATA for the LAN
        .253 VIP_SERVER_N1 (LAN1) / VIP_SERVER_N2 (LAN2)
        .254 VIP_DATA_N1 (LAN1) / VIP_DATA_N2 (LAN2)
```

### A4. `vip_routing.py`

**Location**: `VipRoutingMixin` class docstring (lines ~40-43), "Depends on TopologyMixin attributes" list.

**Change**: Add the two new attributes so the docstring accurately reflects the dependency surface:

```python
    Depends on TopologyMixin attributes (set at __init__ time):
        vip_server_ip, vip_server_mac,
        vip_server_n2_ip, vip_server_n2_mac,
        vip_data_n1_ip, vip_data_n1_mac, vip_data_n2_ip, vip_data_n2_mac,
        ...
```

### B1. `osken-controller.env`

**Location**: After existing `VIP_SERVER_MAC` line.

**Change**: Add N2 VIP. Update the section comment to reflect that VIP_SERVER is now per-LAN:

```bash
# VIP_SERVER — per-LAN client-facing HTTP VIP.
# LAN1 clients use VIP_SERVER (10.0.0.253); LAN2 clients use VIP_SERVER_N2 (10.0.1.253).
VIP_SERVER_IP=10.0.0.253
VIP_SERVER_MAC=aa:bb:cc:dd:ee:01

VIP_SERVER_N2_IP=10.0.1.253
VIP_SERVER_N2_MAC=aa:bb:cc:dd:ee:04
```

> **RQ2 override files (no changes needed):** `VIP_SERVER_N2_*` are topology constants, not policy knobs. They do not vary across `topology_host`, `topology_slowstart`, or `topology_lifecycle`. The base env (B1) covers all modes — no entries are needed in `rq2_topology_*.env` override files.

### C1. `run_experiment.sh`

**Change 1** — Line ~75: Replace single VIP with per-LAN:

```bash
# Per-LAN VIP_SERVER addresses
VIP_LAN1="10.0.0.253:5000"
VIP_LAN2="10.0.1.253:5000"
```

**Change 2** — Lines ~557-564: Pass both VIPs to traffic_generator and update the diagnostic echo:

```bash
python3 "${SCRIPT_DIR}/traffic_generator.py" \
    --config        "$PHASES_CONFIG" \
    --clients-lan1  "$CLIENTS_LAN1" \
    --clients-lan2  "$CLIENTS_LAN2" \
    --snapshot-dir  "$SNAPSHOT_DIR" \
    --output        "$METRICS_OUTPUT" \
    --vip-lan1      "$VIP_LAN1" \
    --vip-lan2      "$VIP_LAN2" \
    "${extra_flags[@]}"
```

**Change 3** — Line ~623: Replace the single `VIP` diagnostic echo with two explicit lines (the old `echo " VIP         : ${VIP}"` will crash with `set -u` after the variable rename):

```bash
echo " VIP LAN1    : ${VIP_LAN1}"
echo " VIP LAN2    : ${VIP_LAN2}"
```

### C2. `traffic_generator.py`

**Change 1** — Argument parser (line ~492): Replace single `--vip` with per-LAN:

```python
parser.add_argument(
    "--vip-lan1", default="10.0.0.253:5000",
    help="VIP_SERVER_N1 address:port for LAN1 clients (default: 10.0.0.253:5000)"
)
parser.add_argument(
    "--vip-lan2", default="10.0.1.253:5000",
    help="VIP_SERVER_N2 address:port for LAN2 clients (default: 10.0.1.253:5000)"
)
```

**Change 2** — `run()` function (lines ~457-464): Replace `args.vip` with a LAN-conditional in the list comprehension:

```python
            tasks = [
                asyncio.create_task(
                    client_loop(ns, lan, phase, snap,
                                args.vip_lan1 if lan == "lan1" else args.vip_lan2,
                                csv_targets, csv_lock, args.dry_run)
                )
                for ns, lan in phase_clients
            ]
```

`client_loop()` already receives `vip` as a parameter — no signature change needed.

---

## What Does NOT Need Changing

| Area | Reason |
|------|--------|
| `_vip_routing/flows.py` | `install_vip_dnat_snat()` already takes `vip_ip`/`vip_mac` as parameters — works generically for any VIP |
| `_vip_routing/selection.py` | `select_server()` uses `vip_server_pool` which is already shared across LANs via peer topology sync |
| `_vip_routing/state.py` | Warm lease logic is MAC-based, VIP-agnostic |
| `_vip_routing/config.py` | No VIP-specific constants |
| `build_network_1.sh` / `build_network_2.sh` | VIPs are virtual — controller handles ARP reply; no OVS IP assignment needed |
| `build_network_setup.sh` | Both controllers share the same env file — N2 vars automatically available to both |
| `build_router.sh` / `inject_wan_latency.sh` | `10.0.1.253` is already in LAN2's subnet — no routing/tc changes needed |
| Docker images (`edge_server`, `osken-controller`, etc.) | Edge server listens on `0.0.0.0:5000`; controller reads VIPs from env |
| `Makefile` | No changes needed. The Makefile passes `OSKEN_ENV_OVERRIDE_FILE` through to `build_network_setup.sh` (for controller env) and delegates all VIP addressing to `run_experiment.sh`'s internal `VIP_LAN1`/`VIP_LAN2` defaults. Neither the `setup_network` nor `run_experiment` Makefile targets reference VIP addresses. |

## Architecture After Change

```
LAN1 (10.0.0.0/24)                    LAN2 (10.0.1.0/24)
┌─────────────────────────┐           ┌─────────────────────────┐
│ VIP_SERVER_N1  .253     │           │ VIP_SERVER_N2  .253     │  ← NEW
│ VIP_DATA_N1    .254     │           │ VIP_DATA_N2    .254     │
│                         │           │                         │
│ ovs-br0 ─── osken       │           │ ovs-br1 ─── osken_2     │
│   ▲                     │           │   ▲                     │
│   │ LAN1 clients        │           │   │ LAN2 clients        │
│   │ use 10.0.0.253      │           │   │ use 10.0.1.253      │
└─────────────────────────┘           └─────────────────────────┘
        │                                      │
        └──────── NAT Router (50ms) ───────────┘
```

- **LAN1 clients** → `10.0.0.253:5000` → `osken` routes → selects from shared `vip_server_pool`
- **LAN2 clients** → `10.0.1.253:5000` → `osken_2` routes → selects from shared `vip_server_pool`
- Both controllers independently exercise the configured `BACKEND_SELECTION_POLICY`
- Cross-LAN backend selection still possible (pool includes peer's servers via topology sync)

## Implementation Order

1. **Env file** (B1) — add N2 vars (safe, no runtime effect until controller reads them)
2. **Controller** (A1-A4) — read N2 vars, dispatch in ingress, parameterize `_handle_vip_server`, update docstrings
3. **Traffic scripts** (C1-C2) — per-LAN VIP for clients
4. **Documentation** (D1) — update VIP routing overview
5. **Sync to cloud VM, rebuild network, smoke test**

## Verification

After implementation, verify with a minimal smoke test:

1. Rebuild network: `make setup_network OSKEN_ENV_OVERRIDE_FILE=...`
2. Create 1 client per LAN
3. Run a single-phase test (e.g., baseline only)
4. **Verify LAN1 regression**: confirm LAN1 clients still reach `10.0.0.253` and get routed correctly (existing functionality must not break).
5. Check controller logs:
   - `osken` log should show `vip_server` decisions for LAN1 clients
   - `osken_2` log should show `vip_server n2` decisions for LAN2 clients
6. Verify zero cross-WAN VIP traffic for LAN2 clients (they hit `10.0.1.253` locally)
7. **Dump OVS flows** on both bridges to confirm punt rules:
   - `docker exec ovs ovs-ofctl dump-flows ovs-br0 | grep "10.0.0.253"`
   - `docker exec ovs ovs-ofctl dump-flows ovs-br1 | grep "10.0.1.253"`
