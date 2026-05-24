# VIP_DATA Recovery VIP and One-Shot Arming Plan

Reference: [vip_warm_start_and_vip_data_refresh_plan.md](./vip_warm_start_and_vip_data_refresh_plan.md)
Depends on: [vip_warm_leases_plan.md](./vip_warm_leases_plan.md)

## Objective

Add per-domain `VIP_DATA_RECOVERY_*` VIPs and a one-shot edge-server arming
path so that the next Mongo client creation after a real connection-level
failure reaches a fresh controller decision without changing steady-state
`VIP_DATA` routing semantics yet.

This is the Phase 2 subplan. It assumes Phase 1 already provides the bounded
warm-lease machinery in the controller. Phase 2 is responsible only for
creating the next fresh selection opportunity on demand.

This is also the storage-specific phase that closes the fresh-selection gap
left if Phase 1 is evaluated in isolation. It does not change the compute
warm-start model, which remains passive and natural-move only.

As Phase 2 lands, the earlier promotion-triggered `/vip_data` refresh path
should be removed from the intended recovery mechanism. `/vip_data` remains a
configuration surface for domain-to-VIP mapping only.

## Approved Decisions

- Keep the controller as the only component that chooses the concrete storage
  backend.
- Add two recovery VIPs, one per owner domain, alongside the existing
  `VIP_DATA_N1` and `VIP_DATA_N2` addresses.
- Let the edge server decide only whether the next Mongo client creation uses
  the normal VIP or the recovery VIP once.
- Arm recovery only on main-path connection failures that retire the current
  `MongoClient`.
- Do not rely on controller-driven `PUT /vip_data` refresh for this design.
- Treat `/vip_data` as a configuration-only surface; same-value updates must be
  idempotent and must not retire the cached client.
- Remove promotion-triggered `/vip_data` refresh from
  [main_n1.py](../../../../source/sdn_controller/main_n1.py) and
  [main_n2.py](../../../../source/sdn_controller/main_n2.py) as recovery VIP
  lands.
- This phase addresses storage only; it is not a compute warm-capture
  mechanism.
- Recovery dispatch must preserve the recovery VIP IP/MAC identity inside the
  shared `_handle_vip_data(...)` path; `recovery=True` is not just a logging
  tag.
- If controller env overrides recovery VIP IPs, both static and dynamic edge
  servers should receive the same values so recovery behavior cannot drift by
  launch path.
- Do not narrow recovery flow matches or bound recovered-client lifetime in
  this phase; Phase 3 owns that work.

---

## Implementation Steps

### 1. Add controller-side recovery VIP configuration

Modify [topology.py](../../../../source/sdn_controller/topology/topology.py),
[osken-controller.env](../../../../source/scripts/osken-controller.env),
[node_common.py](../../../../source/sdn_controller/elasticity/node_common.py),
and [add_network_node.sh](../../../../source/scripts/network/add_network_node.sh).

Recommended controller attributes:

```python
self.vip_data_recovery_n1_ip = os.environ.get("VIP_DATA_RECOVERY_N1_IP", "10.0.0.252")
self.vip_data_recovery_n1_mac = os.environ.get("VIP_DATA_RECOVERY_N1_MAC", "aa:bb:cc:dd:ee:12")
self.vip_data_recovery_n2_ip = os.environ.get("VIP_DATA_RECOVERY_N2_IP", "10.0.1.252")
self.vip_data_recovery_n2_mac = os.environ.get("VIP_DATA_RECOVERY_N2_MAC", "aa:bb:cc:dd:ee:13")
```

Recommended env additions:

```dotenv
VIP_DATA_RECOVERY_N1_IP=10.0.0.252
VIP_DATA_RECOVERY_N1_MAC=aa:bb:cc:dd:ee:12
VIP_DATA_RECOVERY_N2_IP=10.0.1.252
VIP_DATA_RECOVERY_N2_MAC=aa:bb:cc:dd:ee:13
```

Recommended allocator note update:

```python
    Suffixes 252â€“254 are reserved for VIPs:
        .252 recovery VIP_DATA for the LAN
        .253 VIP_SERVER
        .254 VIP_DATA
```

This is a documentation-only update in the allocator. No allocation logic
change is required because the dynamic pool already remains bounded to
suffixes `.6`â€“`.55`.

Recommended shell reservation note update:

```bash
# .1 = gateway, .252 = VIP_DATA recovery, .253 = VIP_SERVER,
# .254 = VIP_DATA_N{lan}; test clients (namespace-based) use .56+
declare -A RESERVED_SUFFIX=( [1]="1 252 253 254" [2]="1 252 253 254" )
```

The shell attach path does not need new allocation logic either because it
already auto-assigns from the general LAN space and can simply keep `.252`
documented as reserved alongside the other VIP suffixes.

What this achieves:

- gives recovery traffic its own controller-visible destination address
- keeps the existing per-domain VIP ownership model intact
- avoids inventing a new controller-side signaling surface
- keeps the allocator reservation note aligned with the new recovery VIP
  address at `.252`

### 2. Extend VIP routing to recognize recovery VIPs

Modify [vip_routing.py](../../../../source/sdn_controller/vip_routing.py).

Recommended binding helper:

```python
def _iter_vip_bindings(self):
    yield (self.vip_server_ip, self.vip_server_mac, "server", False)
    yield (self.vip_data_n1_ip, self.vip_data_n1_mac, "n1", False)
    yield (self.vip_data_n2_ip, self.vip_data_n2_mac, "n2", False)
    yield (self.vip_data_recovery_n1_ip, self.vip_data_recovery_n1_mac, "n1", True)
    yield (self.vip_data_recovery_n2_ip, self.vip_data_recovery_n2_mac, "n2", True)
```

Recommended recovery dispatch shape:

```python
if dst_ip == self.vip_data_recovery_n1_ip:
    return self._handle_vip_data(
        datapath, in_port, pkt, src_mac, src_ip, ip_proto,
        domain="n1", recovery=True,
    )
if dst_ip == self.vip_data_recovery_n2_ip:
    return self._handle_vip_data(
        datapath, in_port, pkt, src_mac, src_ip, ip_proto,
        domain="n2", recovery=True,
    )
```

Recommended shared handler shape:

```python
def _handle_vip_data(
  self, datapath, in_port, pkt, src_mac, src_ip, ip_proto, *,
  domain: str, recovery: bool = False,
) -> bool:
  if recovery and domain == "n1":
    vip_ip, vip_mac = self.vip_data_recovery_n1_ip, self.vip_data_recovery_n1_mac
  elif recovery and domain == "n2":
    vip_ip, vip_mac = self.vip_data_recovery_n2_ip, self.vip_data_recovery_n2_mac
  elif domain == "n1":
    vip_ip, vip_mac = self.vip_data_n1_ip, self.vip_data_n1_mac
  else:
    vip_ip, vip_mac = self.vip_data_n2_ip, self.vip_data_n2_mac
```

Recommended ARP/IP punt extension:

```python
for vip_ip, _, _, _ in self._iter_vip_bindings():
    match = parser.OFPMatch(eth_type=0x0800, ipv4_dst=vip_ip)
    actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                      ofproto.OFPCML_NO_BUFFER)]
    self._install_flow(datapath, priority=100, match=match, actions=actions)
```

What this achieves:

- makes recovery VIPs first-class VIPs in the controller's ARP and PacketIn
  handling
- keeps recovery selection inside the existing `_handle_vip_data(...)` path
- preserves the recovery VIP IP/MAC identity all the way through DNAT/SNAT
  installation instead of collapsing recovery traffic back onto the
  steady-state VIP pair
- avoids duplicating storage-selection logic outside `VipRoutingMixin`

### 3. Demote `/vip_data` to an idempotent config endpoint and add one-shot recovery state

Modify [app.py](../../../../source/docker/edge_server/source/app.py).

Recommended `/vip_data` shape:

```python
@app.route("/vip_data", methods=["PUT"])
def set_vip_data():
  body = request.get_json(silent=True) or {}
  changed_lans = []
  with vip_data_lock:
    for lan, vip_ip in body.items():
      if vip_data_per_domain.get(lan) != vip_ip:
        vip_data_per_domain[lan] = vip_ip
        changed_lans.append(lan)
  for lan in changed_lans:
    _retire_client(lan)
  return jsonify({
    "message": "VIP data updated",
    "vip_data": vip_data_per_domain,
    "changed_lans": changed_lans,
  }), 200
```

Recommended state:

```python
vip_data_recovery_per_domain = {
    "lan1": os.environ.get("VIP_DATA_RECOVERY_N1_IP", "10.0.0.252"),
    "lan2": os.environ.get("VIP_DATA_RECOVERY_N2_IP", "10.0.1.252"),
}
recovery_once_per_domain = {
    "lan1": False,
    "lan2": False,
}
```

Recommended selector helper:

```python
def _select_vip_ip_for_new_client(lan: str) -> tuple[str, str]:
    with vip_data_lock:
        if recovery_once_per_domain[lan]:
            recovery_once_per_domain[lan] = False
            return vip_data_recovery_per_domain[lan], "recovery"
        return vip_data_per_domain[lan], "normal"
```

Recommended `_get_client(...)` integration:

```python
vip_ip, mode = _select_vip_ip_for_new_client(lan)
url = f"mongodb://{vip_ip}:{DB_PORT}/"
client = MongoClient(...)
log.info("Created MongoClient for %s via %s path â†’ %s", lan, mode, url)
```

What this achieves:

- keeps `/vip_data` available as a config surface without letting same-value
  updates cause unnecessary reconnect churn
- keeps the edge server's role limited to choosing the next VIP address once
- preserves the current cached-`MongoClient` model already used by `app.py`
- makes recovery usage explicit in logs for later experiments

### 4. Arm recovery only on main-path connection failure

Modify [app.py](../../../../source/docker/edge_server/source/app.py).

Recommended arming helper:

```python
def _arm_recovery_once(lan: str) -> None:
    with vip_data_lock:
        recovery_once_per_domain[lan] = True
    log.info("Armed one-shot recovery VIP for %s", lan)
```

Recommended failure path:

```python
except AutoReconnect:
    breaker.record_failure()
    _arm_recovery_once(lan)
    _retire_client(lan)
    log.warning("timed_db: retired stale MongoClient for %s after connection failure", lan)
    raise
```

Why this specific hook:

- `AutoReconnect` already marks the boundary where the current Mongo socket is
  no longer usable
- the next `_get_client(...)` call already creates a fresh connection when the
  client cache is empty
- reusing the existing retire-and-recreate lifecycle avoids adding a second
  client-management state machine in this phase

### 5. Remove the promotion-triggered refresh queue from the controller path

Modify [main_n1.py](../../../../source/sdn_controller/main_n1.py) and
[main_n2.py](../../../../source/sdn_controller/main_n2.py).

Remove:

- `_pending_vip_data_refresh`
- `_vip_data_refresh_cursor`
- `_select_vip_data_refresh_targets(...)`
- `_refresh_vip_data_clients(...)`
- `_refresh_pending_storage(...)`
- the `_refresh_pending_storage()` calls in `_on_telemetry_update(...)`

Recommended promotion helper after the refresh path is removed:

```python
def _promote_storage_backend(self, mac: str, domain: str) -> None:
    self.add_storage_mac(mac, domain)
    self.mark_storage_backend_warm(mac, domain)
```

What this achieves:

- keeps storage promotion focused on VIP eligibility plus warm leasing only
- removes the old reconnect nudge that still reused the normal `VIP_DATA`
  destination and therefore did not guarantee a fresh controller-visible
  selection
- makes recovery VIP the only intended post-failure reselection mechanism

### 6. Propagate recovery VIP IPs into static and dynamic edge-server containers

Modify [build_network_1.sh](../../../../source/scripts/network/build_network_1.sh),
[build_network_2.sh](../../../../source/scripts/network/build_network_2.sh),
and [compute_node_manager.py](../../../../source/sdn_controller/elasticity/compute_node_manager.py).

Recommended container wiring:

```bash
docker run -dit --name edge_server_n1 --network none \
  -e LAN_ID=lan1 \
  -e VIP_DATA_RECOVERY_N1_IP=10.0.0.252 \
  -e VIP_DATA_RECOVERY_N2_IP=10.0.1.252 \
  edge_server
```

Recommended dynamic compute wiring:

```python
cmd = [
    "docker", "run", "-dit",
    "--network", "none",
    "--name", name,
    "-e", f"LAN_ID=lan{lan}",
    "-e", f"CONTAINER_NAME={name}",
    "-e", f"VIP_DATA_RECOVERY_N1_IP={os.environ.get('VIP_DATA_RECOVERY_N1_IP', '10.0.0.252')}",
    "-e", f"VIP_DATA_RECOVERY_N2_IP={os.environ.get('VIP_DATA_RECOVERY_N2_IP', '10.0.1.252')}",
    "edge_server",
]
```

What this achieves:

- keeps controller and edge-server recovery VIP configuration aligned
- keeps static and dynamic edge-server launches aligned if recovery VIP envs
  are later overridden for experiments
- avoids introducing a second checked-in env file just for edge servers
- matches the current container-launch pattern already used in the network
  scripts

---

## File Map

- [topology.py](../../../../source/sdn_controller/topology/topology.py)
  Add recovery VIP attributes beside the existing `VIP_DATA_N1/N2` fields.
- [vip_routing.py](../../../../source/sdn_controller/vip_routing.py)
  Recognize recovery VIPs in ARP reply, IP punt, and PacketIn dispatch, while
  preserving the recovery VIP IP/MAC identity inside `_handle_vip_data(...)`.
- [app.py](../../../../source/docker/edge_server/source/app.py)
  Make `/vip_data` idempotent and config-only, then add one-shot recovery
  arming and recovery-VIP selection for the next fresh Mongo client creation.
- [osken-controller.env](../../../../source/scripts/osken-controller.env)
  Define controller-side recovery VIP addresses and MACs.
- [node_common.py](../../../../source/sdn_controller/elasticity/node_common.py)
  Update the allocator reservation comment so VIP space is documented as
  `.252`â€“`.254` once recovery VIPs are introduced.
- [add_network_node.sh](../../../../source/scripts/network/add_network_node.sh)
  Update the shell-side reservation comment so `.252` is documented alongside
  the other VIP suffixes.
- [main_n1.py](../../../../source/sdn_controller/main_n1.py)
  Remove the promotion-triggered `/vip_data` refresh queue and keep storage
  promotion focused on VIP membership plus warm leasing.
- [main_n2.py](../../../../source/sdn_controller/main_n2.py)
  Remove the promotion-triggered `/vip_data` refresh queue and keep storage
  promotion focused on VIP membership plus warm leasing.
- [build_network_1.sh](../../../../source/scripts/network/build_network_1.sh)
  Pass recovery VIP IPs into LAN1 edge-server containers.
- [build_network_2.sh](../../../../source/scripts/network/build_network_2.sh)
  Pass recovery VIP IPs into LAN2 edge-server containers.
- [compute_node_manager.py](../../../../source/sdn_controller/elasticity/compute_node_manager.py)
  Pass recovery VIP IPs into dynamically launched edge-server containers.

---

## Dependencies

- Phase 1 warm leases from [vip_warm_leases_plan.md](./vip_warm_leases_plan.md)
  should already exist so the fresh recovery selection can prefer newly
  promoted dynamic storage.
- No new external packages.
- Phase 3 will later refine this path with narrow flow matching and bounded
  recovered-client lifetime.

---

## Verification

Validate this phase experimentally: after a real connection-level failure, the
next fresh Mongo client creation should target `VIP_DATA_RECOVERY_*`, trigger a
fresh PacketIn in the controller, and then continue using the resulting cached
client until Phase 3 introduces bounded recovery-session switchback.

Also verify that:

- promotion to `SECONDARY` no longer triggers controller-driven `/vip_data`
  refresh fan-out
- same-value `/vip_data` updates are idempotent and do not retire the cached
  client
- static and dynamic edge servers agree on the recovery VIP addresses when env
  overrides are supplied

---

## Documentation Updates

- [vip_routing_overview.md](../vip_routing_overview.md)
  Add the recovery VIP addresses as controller-recognized VIPs.
- [system_mechanisms.md](../../system_mechanisms.md)
  Describe the edge-server one-shot recovery arming behavior.
- [telemetry_overview.md](../../telemetry/telemetry_overview.md)
  Remove any storage-failover wording that still assumes `/vip_data` refresh is
  the intended post-failure mechanism.
