# Implementation Plan — Conntrack-Based VIP_DATA Routing

**Depends on**: [recovery_removal](../recovery_removal/recovery_removal_plan.md) (deployed together)
**Design rationale**: see [conntrack_vip_routing_design.md](conntrack_vip_routing_design.md)

## 1. Step-by-Step Implementation

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
    dnat_eth_dst = (_ROUTER_MAC if is_cross_network and _ROUTER_MAC
                    else backend_mac)

    # ct(commit, nat(dst=backend_ip))
    # Uses ct_zone to differentiate domains: zone=1 for n1, zone=2 for n2.
    # Reply rules match on the same zone so they can set the correct VIP MAC.
    # zone_src=None means "immediate value" (not read from a register);
    # the zone number is encoded via nicira_ext.ofs_nbits.
    _CT_ZONE = {"n1": 1, "n2": 2}
    ct_action = parser.NXActionCT(
        flags=1,                                    # NX_CT_FLAG_COMMIT
        zone_src=None,                              # immediate zone value
        zone_ofs_nbits=nicira_ext.ofs_nbits(0, 15), # 16-bit zone (1 or 2)
        recirc_table=ofproto.OFPTT_ALL,
        alg=0,
        actions=[
            parser.NXActionNAT(
                flags=0,                            # 0 = DNAT
                range_ipv4_min=backend_ip,          # IP as string
                range_ipv4_max=backend_ip,
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

**Important — verify at implementation time**:
The code sketch above shows the intended `NXActionCT`/`NXActionNAT` structure.
The parameter names are based on OS-Ken 4+ docs; this project uses
**OS-Ken 3.1.1** (`pip install os-ken==3.1.1`). The 3.1.1 parser may use
different class names (e.g., `OFPActionCt`), different parameter names, or a
different zone-encoding scheme. Verify the actual signatures before coding:

```bash
python3 -c "from os_ken.ofproto import ofproto_v1_3_parser as p; help(p.NXActionCT)"
python3 -c "from os_ken.ofproto import ofproto_v1_3_parser as p; help(p.NXActionNAT)"
```

If the 3.1.1 parser lacks these classes or the signatures are incompatible,
use the fallback below — it is functionally equivalent and avoids version
sensitivity entirely.

**Fallback (preferred for 3.1.1)**
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

### Phase 3 — Conntrack Monitoring

**File**: `source/scripts/testing/collect_resource_stats.py` (or new companion script)

#### Step 4.1 — Conntrack availability check at controller startup

Add to `main_n1.py` / `main_n2.py` or `_on_datapath_connected`:

```python
def _verify_conntrack_available():
    """Refuse to start if OVS conntrack is not available on the system."""
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

### Phase 4 — Documentation

**File**: `docs/operation/vip_routing/vip_routing_interception_and_flow_rules.md`

#### Step 4.1 — Verify recovery docs already updated

Recovery removal from the controller code is already complete (all Phase 3
steps executed). Verify that `vip_routing_backend_selection_and_warm_leases.md`
no longer references `recovery` parameter, `_filter_previous_normal_backend`,
`_remember_normal_storage_choice`, `_forget_normal_storage_choice`,
`_last_normal_storage_choice`, or recovery-specific timeout constants.

#### Step 4.2 — Add conntrack design section to `vip_routing_interception_and_flow_rules.md`

Add new § after the current §8 "VIP_DATA Routing":

- Per-client forward + per-client-per-domain reply rule structure with diagrams
- Conntrack piece roles table (ct(commit) creates, ct_state matches, kernel 5-tuple routes) — explicitly distinguishing the three mechanisms
- Conntrack entry lifecycle (create → established → expire)
- Why it's safe to delete the forward rule (entries live in kernel, not OVS)
- Cookie scheme for targeted bulk deletion
- Idle/hard timeout rationale (10s/120s)
- Comparison table: old per-client static NAT vs new per-client conntrack rules

#### Step 4.3 — Update existing sections

- §4 (VIP Address Binding Set): Remove recovery bindings — now 3 bindings (server, n1, n2)
- §9 (Recovery narrow-flow behavior): Remove or mark as deprecated
- Add cross-reference to [recovery_removal plan](../recovery_removal/recovery_removal_plan.md)

## 2. File Map

| File                                                                            | Action                                                                                                                               | Phase |
| ------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ | ----- |
| `source/sdn_controller/_vip_routing/flows.py`                                 | **Major rewrite** — new per-client forward rules with ct(commit...), per-client reply rules, cookie registry, deletion helper | 1, 2  |
| `source/sdn_controller/_vip_routing/ingress.py`                               | **Modify** — update flow call sites to use conntrack forward/reply rules                                                      | 1     |
| `source/sdn_controller/_vip_routing/state.py`                                 | **Modify** — wire flow deletion into unregister                                                                               | 2     |
| `source/sdn_controller/main_n1.py`                                            | **Modify** — add conntrack startup check                                                                                      | 3     |
| `source/sdn_controller/main_n2.py`                                            | **Modify** — add conntrack startup check                                                                                      | 3     |
| `source/scripts/testing/collect_resource_stats.py`                            | **Modify** — add conntrack monitoring                                                                                         | 3     |
| `docs/operation/vip_routing/vip_routing_backend_selection_and_warm_leases.md` | **Verify** — recovery sections already removed; confirm no stale references remain                                             | 4     |
| `docs/operation/vip_routing/vip_routing_interception_and_flow_rules.md`       | **Update** — add conntrack §, remove recovery §                                                                              | 4     |

## 3. Dependencies & Deployment Order

1. Controller changes are Python-only — file sync + controller restart.
   **No Docker image rebuilds required** — both the OVS image (kernel-datapath
   conntrack built-in) and OS-Ken image (Nicira extensions in os-ken 3.1.1)
   already support conntrack as built.
2. Recovery VIP removal is **already deployed** (controller-side and edge-side).
   No further recovery-related changes are needed.
3. Conntrack must be available in the OVS kernel datapath. Verify with
   `ovs-appctl dpctl/dump-conntrack` before deployment.
4. Conntrack monitoring (Phase 3) can be deployed after the core changes —
   it's additive and does not affect routing.

## 4. Rollback Plan

1. Revert `flows.py` to pre-conntrack `install_vip_dnat_snat`
2. Revert `state.py` to remove flow deletion on unregister

Conntrack monitoring (Phase 3) can stay — it's read-only and doesn't affect
routing behavior.

## 5. Testing & Validation

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
