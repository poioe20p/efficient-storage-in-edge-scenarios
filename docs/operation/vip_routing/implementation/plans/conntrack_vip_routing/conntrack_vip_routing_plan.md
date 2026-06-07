# Implementation Plan & Guide — Conntrack-Based VIP_DATA Routing

**Date**: 2026-06-07
**Status**: Plan — awaiting approval
**Scope**: Controller-side `flows.py`, `state.py`, `ingress.py`, `selection.py`, `config.py`, `vip_routing.py`, `topology/topology.py`, `main_n1.py`, `main_n2.py` + new monitoring in `collect_resource_stats.py`
**Depends on**: [recovery_removal](../recovery_removal/recovery_removal_plan.md) (deployed together)

## 1. Motivation

The v5.x experiment campaign identified **stale OVS flow rules** as the root
cause of 55-65% failure rates in compute phases. When a storage backend is
removed from the VIP_DATA pool via `unregister_storage_backend`, the existing
DNAT+SNAT flow rule pair is NOT deleted. The stale rule continues to DNAT new
TCP connections to the dead backend for up to 120 seconds (hard timeout).

The current flow rules use static L2-L4 field matching without OVS connection
tracking. This means the rules cannot be safely deleted while connections are
in flight — the rules ARE the connection state. Deleting a rule would reroute
in-flight packets to a different backend, breaking established TCP connections.

OVS conntrack solves this by separating **connection establishment** (flow
rules) from **connection state** (conntrack table). Once a connection is
established, its NAT mapping lives in the conntrack table independently of
the flow rule that created it. The forward rule can be safely deleted —
established connections survive in conntrack, and new connections trigger a
fresh `select_storage` via the punt rule.

## 2. Design Overview

### 2a. Current Architecture (Static NAT)

```
Per-client, per-backend rule pairs:

  Rule FWD-1: client_A → VIP → DNAT to backend_X
  Rule REV-1: backend_X → client_A → SNAT to VIP

  Rule FWD-2: client_B → VIP → DNAT to backend_X
  Rule REV-2: backend_X → client_B → SNAT to VIP

Problem: Deleting any FWD rule breaks in-flight connections because the
DNAT action is baked into the rule, not tracked per-connection.
Rules stay for 30-120s after backend removal → stale routing.
```

### 2b. Conntrack Architecture

```
Per-client forward rules (one per client per domain), shared reply rules:

  Rule FWD-A (forward, client A → VIP):
    Match: eth_src=clientA_mac, eth_dst=vip_mac, ipv4_src=clientA_ip, ipv4_dst=vip_ip, tcp_dst=27018
    Action: ct(commit, nat(dst=backend_X_ip)), set_field(eth_dst=backend_X_mac), output:backend_port
    Idle: 10s | Hard: 120s | Priority: 200 | Cookie: per-domain (same cookie for all clients)

  Rule FWD-B (forward, client B → VIP):
    Match: eth_src=clientB_mac, eth_dst=vip_mac, ipv4_src=clientB_ip, ipv4_dst=vip_ip, tcp_dst=27018
    Action: ct(commit, nat(dst=backend_Y_ip)), set_field(eth_dst=backend_Y_mac), output:backend_port
    Idle: 10s | Hard: 120s | Priority: 200 | Cookie: per-domain (same cookie for all clients)

  Rule REV-A-n1 (reply, established → client A, domain n1):
    Match: ct_state=+est+trk, ct_zone=1, eth_dst=clientA_mac, ipv4_dst=clientA_ip
    Action: set_field(eth_src=vip_n1_mac), output:clientA_port
    Idle: 0 (never) | Hard: 0 (never) | Priority: 200

  Rule REV-A-n2 (reply, established → client A, domain n2):
    Match: ct_state=+est+trk, ct_zone=2, eth_dst=clientA_mac, ipv4_dst=clientA_ip
    Action: set_field(eth_src=vip_n2_mac), output:clientA_port
    Idle: 0 (never) | Hard: 0 (never) | Priority: 200

  Conntrack table (automatic, per-connection):
    conn_1: client_A:50001 → VIP:27018 → nat → backend_X:27018
    conn_2: client_A:50002 → VIP:27018 → nat → backend_X:27018
    conn_3: client_B:50003 → VIP:27018 → nat → backend_Y:27018
    ...

Deleting all FWD rules for a domain (by cookie):
  → Established connections: untouched — conntrack entries survive ✅
  → New SYNs from any client: no rule matches → punted to controller → fresh select_storage ✅
  → Reply rules stay — each handles established connections via conntrack state ✅

Per-client WSM distribution preserved:
  → Client A's first SYN → select_storage() → backend_X → Rule FWD-A-n1 installed
  → Client B's first SYN → select_storage() → backend_Y → Rule FWD-B-n1 installed
  → Each client independently load-balanced ✅
  → On client A's next selection (idle expiration): new Rule FWD-A overwrites old one
    (same match fields), client B's Rule FWD-B untouched ✅

Domain differentiation via ct_zone:
  → Forward rules use ct(commit, zone=1, ...) for n1, ct(commit, zone=2, ...) for n2
  → Reply rules match ct_zone=1 or ct_zone=2 — different matches, no collision
  → Kernel conntrack automatically places reply packets in the correct zone ✅
```

### 2c. Connection Lifecycle

```
NEW CONNECTION (client A):
  SYN → matches Rule FWD-A (eth_src=clientA_mac, ...) → ct(commit) creates conntrack entry
  → DNAT to backend_X → SYN-ACK returns
  → Reply packets match Rule REV-A (ct_state=+est+trk, eth_dst=clientA_mac)
  → ct(nat) reverses mapping → Connection in conntrack, no longer needs Rule FWD-A

NEW CONNECTION (client B, same domain):
  SYN → matches Rule FWD-B (eth_src=clientB_mac, ...) → ct(commit) creates conntrack entry
  → DNAT to backend_Y (possibly different from client A's backend)
  → Reply packets match Rule REV-B → conntrack reverses mapping
  → Each client independently load-balanced via WSM cost function

ESTABLISHED CONNECTION:
  All subsequent packets match the per-client reply rule (ct_state=+est+trk)
  → ct(nat) applies the stored NAT mapping automatically
  → The forward rule is never consulted again for this connection

AFTER ALL FWD RULES DELETED (unregister_storage_backend):
  Established connections: reply rules + conntrack still handle them ✅
  New SYN from any client: no matching forward rule → hits priority 100 punt rule
  → packet-in to controller → select_storage() → new per-client forward rule installed
  → ct(commit) creates new conntrack entry → connection proceeds ✅

AFTER SINGLE FWD RULE EXPIRES (idle timeout, normal lifecycle):
  Client A's rule expires → client A's next SYN punts → fresh select_storage()
  → New Rule FWD-A installed (overwrites via same match) → MAY pick a different backend
  Client B's rule still active → client B unaffected ✅
```

### 2d. How Conntrack Identifies Connections

Each piece of the conntrack design has a distinct role. They are not interchangeable:

| Piece                                       | Purpose                                                                                                                                                                                                                                                                                                                              |
| ------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `ct(commit, zone=1, nat(dst=10.0.0.100))` | **Creates** an entry for this packet's 5-tuple. The kernel auto-generates the entry identity from `(src_ip, src_port, dst_ip, dst_port, protocol)`. This is the *only* piece that writes state.                                                                                                                            |
| `ct_state=+est+trk`                       | **Matches** ANY packet whose 5-tuple already has an entry in the kernel conntrack table. It is a broad gate — it does not reference a specific entry ID. Every established connection in the zone satisfies it.                                                                                                               |
| The kernel's 5-tuple lookup                 | **Routes** each reply packet to the correct entry. The kernel compares the packet's `(src_ip, src_port, dst_ip, dst_port, protocol)` against every entry in the zone. When the reply direction matches, `ct(nat)` reverses the NAT automatically. This is transparent — no flow rule action is needed for the IP rewrite. |

```
Example: Three connections from edge server A to VIP_DATA_N1

  Entry #1: (10.0.0.10, 50001, 10.0.0.254, 27018, TCP) → nat: dst=10.0.0.100
  Entry #2: (10.0.0.10, 50002, 10.0.0.254, 27018, TCP) → nat: dst=10.0.0.100
  Entry #3: (10.0.0.10, 50003, 10.0.0.254, 27018, TCP) → nat: dst=10.0.0.101

The only difference between #1 and #2 is the source port.
The kernel uses the full 5-tuple to tell them apart.

When a reply packet arrives from 10.0.0.100:27018 → 10.0.0.10:50002:
  → Kernel finds entry #2 (reply direction matches)
  → ct(nat) rewrites src to 10.0.0.254 (the VIP)
  → The reply rule's ct_state=+est+trk match gates entry into the flow
  → set_field(eth_src=VIP_N1_MAC) fixes the L2 header
```

The flow rules never know about individual entries. The kernel handles
per-connection identity entirely on its own. This is why deleting the
forward rule is safe: the entries are not stored in OVS, they're in the
kernel's conntrack table, and the reply rule (`ct_state=+est+trk`) still
matches them regardless of whether the forward rule exists.

## 3. Step-by-Step Implementation

### Phase 1 — Conntrack Flow Rules

**File**: `source/sdn_controller/_vip_routing/flows.py`

#### Step 1.1 — Add flow cookie registry

Define cookies for targeted bulk rule deletion. All per-client forward rules
for a given domain share the same cookie, so `_delete_flow_by_cookie` removes
every client's forward rule in one operation:

```python
# Flow cookies for VIP_DATA forward rules, keyed by domain.
# All per-client forward rules for a domain share the same cookie, allowing
# bulk OFPFC_DELETE on unregister_storage_backend without tracking
# individual clients.
_COOKIE_VIP_DATA_FWD = {
    "n1": 0x56494441,  # 'VIDA' in hex
    "n2": 0x56494442,  # 'VIDB' in hex
}
```

#### Step 1.2 — Add `install_vip_data_forward_rule`

New function replacing the DNAT half of `install_vip_dnat_snat`. Uses
`ct(commit, nat(...))` so OVS creates per-connection conntrack entries.
The match is **per-client** (scoped by `eth_src`/`ipv4_src`) so each client
independently load-balances via `select_storage()`. No delete-before-install
is needed: when the same client gets a new backend, the new rule has the
same match fields and OVS overwrites the old one naturally.

```python
def install_vip_data_forward_rule(
    controller, datapath,
    vip_ip, vip_mac, domain,
    client_mac, client_ip,
    backend_ip, backend_mac, backend_port,
    is_cross_network=False,
):
    """Install/update a per-client forward rule for a VIP_DATA domain.

    The match is scoped to one client (eth_src / ipv4_src), preserving the
    per-client WSM load distribution from the current static-NAT design.

    Uses ct(commit, nat(dst=backend_ip)) so OVS tracks each connection
    independently.  Multiple per-client forward rules share the same
    domain cookie — they can be bulk-deleted on unregister_storage_backend.

    Cross-network: when the backend is on the peer LAN, eth_dst must be
    the router's MAC so the router accepts the frame for L3 forwarding.
    """
    parser = datapath.ofproto_parser
    ofproto = datapath.ofproto

    # Per-client match — preserves per-client WSM load distribution
    match = parser.OFPMatch(
        eth_type=0x0800,
        eth_src=client_mac,
        eth_dst=vip_mac,
        ipv4_src=client_ip,
        ipv4_dst=vip_ip,
        ip_proto=6,           # TCP
        tcp_dst=27018,        # MongoDB
    )

    # Destination MAC: router MAC for cross-network, backend MAC for local
    from .config import _ROUTER_MAC
    dnat_eth_dst = (_ROUTER_MAC if is_cross_network and _ROUTER_MAC
                    else backend_mac)

    # ct(commit, nat(dst=backend_ip))
    # Uses ct_zone to differentiate domains: zone=1 for n1, zone=2 for n2.
    # Reply rules match on the same zone so they can set the correct VIP MAC.
    _CT_ZONE = {"n1": 1, "n2": 2}
    ct_action = parser.NXActionCT(
        flags=ofproto.NX_CT_FLAG_COMMIT,
        zone=_CT_ZONE[domain],
        recirc_table=ofproto.OFPTT_ALL,
        alg=0,
        actions=[
            parser.NXActionNAT(
                flags=0,
                range_ipv4_min=backend_ip.encode(),
                range_ipv4_max=backend_ip.encode(),
            ),
        ],
    )

    actions = [
        ct_action,
        parser.OFPActionSetField(eth_dst=dnat_eth_dst),
        parser.OFPActionOutput(backend_port),
    ]

    # NOTE: No delete-before-install.  When this client re-selects (e.g.
    # after idle timeout or backend unregister), the new rule has the same
    # match (eth_src + ipv4_src + VIP fields) and OVS overwrites the old
    # one automatically via the same-priority/same-match rule.
    controller._install_flow(
        datapath,
        priority=200,
        match=match,
        actions=actions,
        idle_timeout=10,                          # 10s (down from 30s)
        hard_timeout=120,                         # unchanged
        cookie=_COOKIE_VIP_DATA_FWD[domain],
    )

    logger.info(
        "vip_data(%s): per-client forward rule installed — client=%s vip=%s "
        "backend=%s (idle=10s hard=120s cookie=0x%x)",
        domain, client_ip, vip_ip, backend_ip, _COOKIE_VIP_DATA_FWD[domain],
    )
```

**Important**: The exact `NXActionCT` and `NXActionNAT` signatures depend on
the Ryu/OS-Ken OpenFlow protocol parser version in this project. The code
above shows the intended structure. During implementation, verify the actual
class names and parameter names against the installed Ryu version:

- `NXActionCT` may be `OFPActionCt` or similar
- `NX_CT_FLAG_COMMIT` constant name may differ
- `NXActionNAT` may require the IP as `ipv4_min`/`ipv4_max` or a different
  encoding
- The `range_ipv4_min`/`range_ipv4_max` parameters may need the IP as a
  packed bytes string (e.g., `socket.inet_aton(backend_ip)`) or as an integer

**Fallback**: If the Ryu version does not support Nicira conntrack extensions,
use the kernel datapath directly via `ovs-ofctl` with a `ct(commit,...)`
action string. This is less elegant but functionally equivalent. The
`_install_flow` method already abstracts flow installation — we can add a
raw action string path there.

#### Step 1.3 — Add `install_vip_data_reply_rule`

Installed once per client per domain per switch reconnect. Handles ALL
established connections for that client+domain combination regardless of
which backend they go to. The `ct_zone` match differentiates n1 from n2
so each domain gets its own VIP MAC in the `set_field(eth_src=...)` action.

```python
def install_vip_data_reply_rule(
    controller, datapath,
    client_mac, client_ip, vip_mac, in_port, domain,
):
    """Install a reply rule for VIP_DATA traffic for one client+domain.

    The reply rule matches packets belonging to established connections
    (already in conntrack) and rewrites their source to the domain's VIP MAC.
    The IP NAT reversal is handled automatically by conntrack's ct(nat).

    ct_zone scoping ensures n1 and n2 reply rules have different matches
    and can coexist for the same client without collision.
    """
    parser = datapath.ofproto_parser
    ofproto = datapath.ofproto

    _CT_ZONE = {"n1": 1, "n2": 2}

    match = parser.OFPMatch(
        ct_state=(ofproto.OFPSC_ESTABLISHED | ofproto.OFPSC_TRACKED),
        ct_zone=_CT_ZONE[domain],
        eth_type=0x0800,
        eth_dst=client_mac,
        ipv4_dst=client_ip,
        ip_proto=6,
    )
    actions = [
        parser.OFPActionSetField(eth_src=vip_mac),
        parser.OFPActionOutput(in_port),
    ]
    controller._install_flow(
        datapath,
        priority=200,
        match=match,
        actions=actions,
        idle_timeout=0,    # Never idle — conntrack manages lifecycle
        hard_timeout=0,    # Never expire
        cookie=0,          # No cookie needed — never deleted
    )
```

#### Step 1.4 — Add `_delete_flow_by_cookie` helper

```python
def _delete_flow_by_cookie(controller, datapath, cookie):
    """Delete all flows matching a specific cookie value."""
    parser = datapath.ofproto_parser
    ofproto = datapath.ofproto
    mod = parser.OFPFlowMod(
        datapath=datapath,
        cookie=cookie,
        cookie_mask=0xFFFFFFFFFFFFFFFF,
        table_id=ofproto.OFPTT_ALL,
        command=ofproto.OFPFC_DELETE,
        out_port=ofproto.OFPP_ANY,
        out_group=ofproto.OFPG_ANY,
        match=parser.OFPMatch(),  # wildcard — cookie is the filter
    )
    datapath.send_msg(mod)
```

#### Step 1.5 — Update `_handle_vip_data` in ingress.py

The `_handle_vip_data` function currently calls `flows.install_vip_dnat_snat`
with per-client scoping. Replace with calls to the new per-client conntrack
forward rule + reply rule:

```python
def _handle_vip_data(controller, datapath, in_port, pkt,
                     src_mac, src_ip, ip_proto, *, domain):
    # ... select_storage, resolve backend IP/MAC/port ...

    # Determine if cross-network
    is_cross_network = (real_backend_mac in controller.peer_hosts)

    # Install/update the per-client forward rule with conntrack
    flows.install_vip_data_forward_rule(
        controller, datapath,
        vip_ip=vip_ip, vip_mac=vip_mac, domain=domain,
        client_mac=src_mac, client_ip=src_ip,
        backend_ip=storage_ip, backend_mac=storage_mac,
        backend_port=backend_port,
        is_cross_network=is_cross_network,
    )

    # Install reply rule for this client+domain (idempotent — same match means
    # re-installation is a no-op). ct_zone keeps n1/n2 rules from colliding.
    flows.install_vip_data_reply_rule(
        controller, datapath,
        client_mac=src_mac, client_ip=src_ip,
        vip_mac=vip_mac, in_port=in_port, domain=domain,
    )

    # Packet-Out the first packet so it reaches the backend immediately
    # (same as current behavior)
    ...
```

### Phase 2 — Flow Rule Deletion on Backend Unregister

**Files**: `source/sdn_controller/_vip_routing/flows.py`, `state.py`

#### Step 2.1 — Add `delete_vip_data_forward_rule`

```python
def delete_vip_data_forward_rule(controller, datapath, domain):
    """Delete the forward rule for a VIP_DATA domain.

    After deletion, new SYNs to the VIP will be punted to the controller
    (priority-100 punt rule), triggering fresh select_storage().
    Established connections survive in conntrack state.

    Called from unregister_storage_backend via state.py.
    """
    _delete_flow_by_cookie(controller, datapath, _COOKIE_VIP_DATA_FWD[domain])
    logger.info(
        "vip_data(%s): forward rule deleted (cookie=0x%x)",
        domain, _COOKIE_VIP_DATA_FWD[domain],
    )
```

#### Step 2.2 — Wire into `unregister_storage_backend`

In `state.py`, add flow deletion after pool removal:

```python
def unregister_storage_backend(controller, mac: str, domain: str) -> None:
    controller.remove_storage_mac(mac, domain)
    clear_storage_backend_warm(controller, mac, domain)
    _forget_normal_storage_choice(controller, mac, domain)

    # NEW: Delete the forward rule so new connections get a fresh backend.
    # The reply rule is NOT deleted — it's shared and handles all
    # established connections via conntrack state.
    for dp_id, datapath in controller.datapaths.items():
        try:
            flows.delete_vip_data_forward_rule(controller, datapath, domain)
        except Exception:
            logger.exception(
                "vip_data(%s): failed to delete forward rule on dp=%s",
                domain, dp_id,
            )
```

**Why this is safe**: The forward rule (Rule FWD) only matches NEW connections
(SYN packets with no existing conntrack entry). Established connections are
handled by Rule REV + conntrack state. Deleting Rule FWD cannot affect
in-flight queries — their packets never match Rule FWD (they match Rule REV
via `ct_state=+est+trk`), and their NAT mapping lives in conntrack, not in
any flow rule.

### Phase 3 — Recovery VIP References Removal (Conntrack-Affected Parts)

**Files**: `ingress.py`, `selection.py`, `state.py`, `config.py`, `vip_routing.py`, `topology/topology.py`

The recovery VIP was a workaround for stale flow rules. With conntrack
eliminating stale rules at the source, the recovery VIP infrastructure
is dead code. This phase removes the controller-side parts that directly
interact with the conntrack changes. The edge-side removal is covered in
the [recovery_removal plan](../recovery_removal/recovery_removal_plan.md).

#### Step 3.1 — Remove recovery from ingress.py

In `_iter_vip_bindings()`, remove the two recovery bindings:

```python
# BEFORE — 5 bindings:
yield (controller.vip_data_recovery_n1_ip, controller.vip_data_recovery_n1_mac, "n1", True)
yield (controller.vip_data_recovery_n2_ip, controller.vip_data_recovery_n2_mac, "n2", True)

# AFTER — 3 bindings:
# Recovery bindings removed.
```

In `handle_vip_packet_in()`, remove the recovery VIP dispatch (lines 84-93):
the `if dst_ip == controller.vip_data_recovery_n1_ip:` and
`if dst_ip == controller.vip_data_recovery_n2_ip:` blocks.

In `_handle_vip_data()`, remove the `recovery` parameter and all
recovery-specific logic:

- TCP port scoping (`tcp_src_port`/`tcp_dst_port` extraction)
- Non-Mongo packet drop for recovery
- Recovery VIP MAC/IP selection
- Recovery-specific timeout overrides passed to flow installation

#### Step 3.2 — Remove recovery from selection.py

- Remove `recovery` parameter from `select_storage()`
- Remove `_filter_previous_normal_backend()` function
- Remove the `if recovery:` branch that filters the pool
- Remove the `if not recovery:` branch that calls `_remember_normal_storage_choice`

#### Step 3.3 — Remove recovery from state.py

- Remove `_remember_normal_storage_choice()` function
- Remove `_forget_normal_storage_choice()` function
- Remove `_last_normal_storage_choice` initialization from `init_vip_routing_state()`

#### Step 3.4 — Remove recovery from config.py

Remove the recovery-specific timeout constants:

- `_VIP_DATA_RECOVERY_IDLE_TIMEOUT`
- `_VIP_DATA_RECOVERY_HARD_TIMEOUT`

#### Step 3.5 — Remove recovery from vip_routing.py facade

- Remove `recovery` parameter from `select_storage()` method
- Remove recovery VIP attributes from docstring

#### Step 3.6 — Remove recovery from topology.py

Remove initialization of recovery VIP attributes from `topology/topology.py`
(lines 34-37):

- `vip_data_recovery_n1_ip`, `vip_data_recovery_n1_mac`
- `vip_data_recovery_n2_ip`, `vip_data_recovery_n2_mac`

These attributes are defined on `TopologyMixin`, not in `main_n*.py`. The
`vip_routing.py` facade docstring (lines 50-51) also references them as
TopologyMixin dependencies — update the docstring accordingly.

### Phase 4 — Conntrack Monitoring (Phase 6 in combined plan)

**File**: `source/scripts/testing/collect_resource_stats.py` (or new companion script)

#### Step 4.1 — Conntrack availability check at controller startup

Add to `main_n1.py` / `main_n2.py` or `_on_datapath_connected`:

```python
def _verify_conntrack_available():
    """Refuse to start if OVS conntrack is not available on the system."""
    import subprocess
    try:
        result = subprocess.run(
            ["ovs-appctl", "dpctl/dump-conntrack"],
            capture_output=True, timeout=5,
        )
        # Command should succeed even if table is empty
        if result.returncode != 0:
            raise RuntimeError(
                "OVS conntrack is required for VIP_DATA routing. "
                "Ensure the kernel datapath has conntrack support enabled. "
                "Check: CONFIG_NF_CONNTRACK=y in kernel config."
            )
    except FileNotFoundError:
        raise RuntimeError(
            "ovs-appctl not found — is OVS installed?"
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            "ovs-appctl dpctl/dump-conntrack timed out — "
            "conntrack may not be functional."
        )
    logger.info("OVS conntrack available — VIP_DATA routing ready")
```

#### Step 4.2 — Periodic conntrack dump

Add to `collect_resource_stats.py` (every 10s, aligned with telemetry window):

```python
def _collect_conntrack_stats(bridge_names=("ovs-br0", "ovs-br1")):
    """Collect conntrack entry counts per VIP_DATA domain.
  
    Returns dict with keys:
      conntrack_entries_n1: int
      conntrack_entries_n2: int
      conntrack_entries_total: int
      conntrack_dump_ok: bool
    """
    import subprocess
    result = {
        "conntrack_entries_n1": 0,
        "conntrack_entries_n2": 0,
        "conntrack_entries_total": 0,
        "conntrack_dump_ok": False,
    }
    try:
        proc = subprocess.run(
            ["ovs-appctl", "dpctl/dump-conntrack"],
            capture_output=True, text=True, timeout=5,
        )
        if proc.returncode != 0:
            return result
      
        # Parse conntrack entries — count by VIP destination IP
        for line in proc.stdout.splitlines():
            # Example conntrack line format varies by kernel version.
            # Match on VIP IPs: 10.0.0.254 (n1) or 10.0.1.254 (n2)
            result["conntrack_entries_total"] += 1
            if "10.0.0.254" in line:
                result["conntrack_entries_n1"] += 1
            elif "10.0.1.254" in line:
                result["conntrack_entries_n2"] += 1
      
        result["conntrack_dump_ok"] = True
      
        # Warn on suspicious state
        if result["conntrack_entries_total"] == 0:
            logger.warning("conntrack: zero entries — no active VIP_DATA connections?")
      
    except Exception:
        logger.exception("conntrack dump failed")
  
    return result
```

#### Step 4.3 — Emit to resource_stats.csv

Add two new columns to the CSV header and populate from `_collect_conntrack_stats()`:

- `conntrack_entries_n1`
- `conntrack_entries_n2`

#### Step 4.4 — Alert on stale entries

Log a warning when conntrack entries persist longer than the hard timeout (120s).
This can be done by tracking entry creation time (from `ovs-appctl dpctl/dump-conntrack -m`
which includes timestamps in some OVS versions) or by detecting entries whose
5-tuple hasn't changed across multiple dumps.

### Phase 5 — Documentation

**File**: `docs/operation/vip_routing/vip_routing_interception_and_flow_rules.md`

#### Step 5.1 — Update `vip_routing_backend_selection_and_warm_leases.md`

- §6 (Storage Selection): Remove `recovery` parameter from `select_storage()` signature description, remove recovery filtering from selection order
- §9 ("Recovery Avoidance via Last Normal Choice"): Remove entire section — `_filter_previous_normal_backend()`, `_remember_normal_storage_choice()`, `_forget_normal_storage_choice()`, and `_last_normal_storage_choice` no longer exist
- §11 (Flow Timeouts table): Remove `VIP_DATA_RECOVERY_IDLE_TIMEOUT` and `VIP_DATA_RECOVERY_HARD_TIMEOUT` rows

#### Step 5.2 — Add conntrack design section to `vip_routing_interception_and_flow_rules.md`

Add new § after the current §8 "VIP_DATA Routing":

- Per-client forward + per-client-per-domain reply rule structure with diagrams
- Conntrack piece roles table (ct(commit) creates, ct_state matches, kernel 5-tuple routes) — explicitly distinguishing the three mechanisms
- Conntrack entry lifecycle (create → established → expire)
- Why it's safe to delete the forward rule (entries live in kernel, not OVS)
- Cookie scheme for targeted bulk deletion
- Idle/hard timeout rationale (10s/120s)
- Comparison table: old per-client static NAT vs new per-client conntrack rules

#### Step 5.3 — Update existing sections

- §4 (VIP Address Binding Set): Remove recovery bindings — now 3 bindings (server, n1, n2)
- §9 (Recovery narrow-flow behavior): Remove or mark as deprecated
- Add cross-reference to [recovery_removal plan](../recovery_removal/recovery_removal_plan.md)

## 4. File Map

| File                                                                            | Action                                                                                                                               | Phase |
| ------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ | ----- |
| `source/sdn_controller/_vip_routing/flows.py`                                 | **Major rewrite** — new per-client forward rules with ct(commit...), per-client reply rules, cookie registry, deletion helper | 1, 2  |
| `source/sdn_controller/_vip_routing/ingress.py`                               | **Modify** — remove recovery bindings/dispatch/handler, update flow call sites                                                | 1, 3  |
| `source/sdn_controller/_vip_routing/state.py`                                 | **Modify** — wire flow deletion into unregister, remove recovery state helpers                                                | 2, 3  |
| `source/sdn_controller/_vip_routing/selection.py`                             | **Modify** — remove recovery param and filter                                                                                 | 3     |
| `source/sdn_controller/_vip_routing/config.py`                                | **Modify** — remove recovery timeouts                                                                                         | 3     |
| `source/sdn_controller/vip_routing.py`                                        | **Modify** — remove recovery from facade, update docstring                                                                    | 3     |
| `source/sdn_controller/topology/topology.py`                                  | **Modify** — remove recovery VIP attrs (lines 34-37)                                                                          | 3     |
| `source/sdn_controller/main_n1.py`                                            | **Modify** — add conntrack startup check (Phase 4)                                                                            | 4     |
| `source/sdn_controller/main_n2.py`                                            | **Modify** — add conntrack startup check (Phase 4)                                                                            | 4     |
| `source/scripts/testing/collect_resource_stats.py`                            | **Modify** — add conntrack monitoring                                                                                         | 4     |
| `docs/operation/vip_routing/vip_routing_backend_selection_and_warm_leases.md` | **Update** — remove §9 Recovery Avoidance, remove recovery param from §6, remove recovery timeouts from §11                | 5     |
| `docs/operation/vip_routing/vip_routing_interception_and_flow_rules.md`       | **Update** — add conntrack §, remove recovery §                                                                             | 5     |

## 5. Design Decisions & Rationale

### 5a. Per-Client Forward Rules (Not Shared)

The forward rule match includes `eth_src=client_mac` and `ipv4_src=client_ip`,
preserving the per-client WSM load distribution from the current static-NAT
design. Each client independently triggers `select_storage()` on its first
SYN, and different clients may be routed to different backends — exactly as
they are today.

Trade-offs:

- Pro: No regression in load distribution — clients are independently
  balanced across storage backends via the WSM cost function.
- Pro: Same OVS rule count as today (N clients × 2 domains × 1 forward rule = 2N rules).
- Con: Slightly more rules than a single shared rule per domain, but the
  difference is negligible (8 clients → 8 forward rules instead of 1).

### 5b. Per-Domain Cookies (Bulk Deletion)

All per-client forward rules for a given domain share the same cookie. This
enables bulk `OFPFC_DELETE` on `unregister_storage_backend` — one flow-mod
deletes every client's forward rule, forcing all clients to re-select on
their next SYN. Per-client cookies would require tracking which clients have
active rules, adding state complexity with no benefit.

Cookie-keyed deletion is only used in the unregister path. Normal backend
re-selection (idle timeout expiry) does not delete anything: the new rule
overwrites the old one naturally via same-priority/same-match OVS semantics.

### 5c. Idle Timeout: 10s (reduced from 30s)

The forward rule idle timeout is the safety net: if flow deletion on
unregister fails for any reason, the stale per-client rule idles out in 10s
instead of 30s. During active traffic, the idle timer resets on every new
SYN from that client, so the rule stays alive as long as traffic flows.

10s is chosen because:

- It's long enough that brief traffic pauses (e.g., phase transitions) don't
  unnecessarily expire per-client rules and trigger controller round-trips
- It's short enough that stale rules don't cause extended failure windows
- The primary mechanism is proactive deletion on unregister; 10s is the
  fallback, not the primary path

### 5d. Warm-Lease Pre-Installation (Deferred)

The current warm-lease system gives new backends a **selection-time**
preference in `select_storage` — they're more likely to be chosen by the WSM
cost function for a short window (default: server 5s, storage 30s). It does
NOT pre-install any flow rules.

A future extension could pre-install a forward rule at lower priority (190)
when a warm lease is granted. When the current backend is removed and its
rule deleted, the warm rule is promoted to priority 200 — zero packet-in
latency on switchover.

**Deferred** because the packet-in latency (<1ms) is negligible compared to
the 30-120s failure windows we're fixing.

### 5e. `ct_zone` and Per-Client Reply Rules

`ct_zone` (zone 1 for n1, zone 2 for n2) isolates conntrack entries by
domain — it prevents an n1 forward rule's conntrack entry from matching an
n2 reply rule, and vice versa. This is already baked into the rule design
(see §2b).

`ct_zone` does NOT eliminate the need for per-client reply rules. Even
within a single zone, different clients are on different OVS ports, and
the `output:client_port` action must target the correct port. Conntrack
entries store NAT mappings (IP/port rewrites) but not OVS port numbers.
Per-client reply rules are the simplest way to encode the output port.

With 8 clients × 2 domains = 16 reply rules, this is negligible OVS
overhead. No optimization needed at this scale.

### 5e. Domain Differentiation via ct_zone

The reply rule must set `eth_src` to the correct VIP MAC — and
`VIP_DATA_N1_MAC` ≠ `VIP_DATA_N2_MAC`. A single reply rule per client
can only set one `eth_src` value, and two reply rules with identical match
fields would collide (last-one-wins overwrite).

**Solution**: the forward rule tags each connection with `ct_zone=N` (1 for n1,
2 for n2). The reply rule matches `ct_zone=N` in addition to `ct_state`
and client fields. Since the match now differs by zone, both reply rules
coexist for the same client without collision. The kernel automatically
places reply packets in the zone where the original conntrack entry was
created — no extra logic needed.

Zones are also useful for monitoring: `ovs-appctl dpctl/dump-conntrack`
can be filtered per-zone to get per-domain connection counts without
parsing VIP IPs from the conntrack output.

### 5f. Multi-Client Reply Rules

The reply rule needs `eth_dst=client_mac` to avoid hijacking non-VIP traffic
from backends. This means two reply rules per client (one per domain). With
8 clients × 2 domains = 16 reply rules + 8 forward rules = 24 total rules —
negligible OVS overhead. No optimization needed now.

### 5g. Conntrack Availability — Startup Requirement

Conntrack is mandatory. The controller refuses to start if `ovs-appctl dpctl/dump-conntrack` fails. This prevents silent fallback to broken
static-NAT behavior.

### 5h. Docker Image Dependencies

**OVS image** (`source/docker/OVS/`): Uses `ubuntu:20.04` + `openvswitch-switch`.
Kernel-datapath conntrack is included out of the box — no Dockerfile or
`start.sh` changes needed. Verify with `ovs-appctl dpctl/dump-conntrack`
after container startup.

**OS-Ken image** (`source/docker/os-ken/`): Uses `os-ken==3.1.1` (Ryu fork).
Nicira extension classes (`NXActionCT`, `NXActionNAT`) are inherited from
upstream Ryu's `ryu.ofproto.nx_actions`. No additional pip packages or
Dockerfile changes required. If the exact class names differ at implementation
time, the fallback is `ovs-ofctl` raw action strings through the existing
`_install_flow` abstraction.

**Conclusion**: Both images already support conntrack as built today.
No Docker image rebuilds are required for the conntrack changes.

### 5i. Conntrack Table Capacity and Entry Lifecycle

The kernel conntrack table defaults to 65,536 entries on Ubuntu 20.04
(`/proc/sys/net/netfilter/nf_conntrack_max`). At typical load (8 edge
servers × ~10 MongoDB connections each = 80 entries), usage is 0.12% of
capacity. Even at 100 connections per server (800 entries), 1.2%. No tuning
is needed.

Entries clean themselves up naturally:

| TCP state          | Kernel default timeout | Trigger                  |
| ------------------ | ---------------------- | ------------------------ |
| ESTABLISHED (idle) | 5 days                 | Connection idle, no data |
| CLOSE_WAIT         | 60 s                   | Local close initiated    |
| TIME_WAIT          | 120 s                  | Both sides closed        |

In practice, pymongo's connection pool (`maxIdleTimeMS=30000`) closes idle
connections after 30s. The TCP FIN handshake transitions entries through
CLOSE_WAIT → TIME_WAIT → expired within ~3 minutes. Entries from active
connections persist naturally until the application closes them.

The forward rule's 10s idle timeout provides an additional bound: after 10s
of no new SYNs, the OVS rule expires, but established conntrack entries
survive independently. When those connections eventually close, their kernel
entries expire. No manual cleanup is required.

## 6. Dependencies & Deployment Order

1. Controller changes are Python-only — file sync + controller restart.
   **No Docker image rebuilds required** — both the OVS image (kernel-datapath
   conntrack built-in) and OS-Ken image (Nicira extensions in os-ken 3.1.1)
   already support conntrack as built.
2. Must deploy **together with** [recovery_removal](../recovery_removal/recovery_removal_plan.md)
   — the controller removes recovery DNAT installation, and the edge stops
   trying to use recovery VIPs. Deploying one without the other causes
   failures.
3. Conntrack must be available in the OVS kernel datapath. Verify with
   `ovs-appctl dpctl/dump-conntrack` before deployment.
4. Conntrack monitoring (Phase 4) can be deployed after the core changes —
   it's additive and does not affect routing.

## 7. Rollback Plan

1. Revert `flows.py` to pre-conntrack `install_vip_dnat_snat`
2. Revert `state.py` to remove flow deletion on unregister
3. Restore recovery VIP infrastructure in `ingress.py`, `selection.py`,
   `config.py`, `vip_routing.py`, `topology/topology.py`
4. Restore edge-side recovery (if also reverted — see recovery_removal plan)

Conntrack monitoring (Phase 4) can stay — it's read-only and doesn't affect
routing behavior.

## 8. Testing & Validation

### Pre-deployment

- [ ] Verify `ovs-appctl dpctl/dump-conntrack` works on cloud VM
- [ ] Verify Ryu/OS-Ken supports `NXActionCT` and `NXActionNAT`
- [ ] If not, verify `ovs-ofctl` can install `ct(commit,...)` actions as
  raw action strings through the existing `_install_flow` abstraction

### Post-deployment

- [ ] Conntrack entries visible via `ovs-appctl dpctl/dump-conntrack` during
  active traffic
- [ ] Forward rule deleted on each `unregister_storage_backend` (check
  controller log for "forward rule deleted" message)
- [ ] Reply rule survives forward rule deletion (check `ovs-ofctl dump-flows`)
- [ ] No in-flight query failures during backend removal (check edge server
  log for absence of `ERROR db_failure`)
- [ ] Conntrack entry count in `resource_stats.csv` correlates with active
  client count
- [ ] Full `current_state_long_cycle` experiment: overall ≤3%, compute
  phases ≤5%
