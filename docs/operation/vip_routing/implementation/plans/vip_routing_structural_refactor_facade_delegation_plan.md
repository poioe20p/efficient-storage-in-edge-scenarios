# VIP Routing Structural Refactor Plan

## Status

Implemented.

## Objective

Refactor [source/sdn_controller/vip_routing.py](../../../../source/sdn_controller/vip_routing.py)
into smaller internal units while preserving the current runtime behavior
exactly.

The public facade must remain:

- `VipRoutingMixin`
- defined in [source/sdn_controller/vip_routing.py](../../../../source/sdn_controller/vip_routing.py)
- imported unchanged by [source/sdn_controller/main_n1.py](../../../../source/sdn_controller/main_n1.py)
  and [source/sdn_controller/main_n2.py](../../../../source/sdn_controller/main_n2.py)

This is a structural refactor for easier reasoning. It is not an architecture
rewrite, behavior change, or documentation update pass.

## Locked Requirements

1. Keep runtime behavior exactly the same.
2. Keep the public import path and class name unchanged.
3. Keep a single public facade class.
4. Do not require caller changes in:
   - [source/sdn_controller/main_n1.py](../../../../source/sdn_controller/main_n1.py)
   - [source/sdn_controller/main_n2.py](../../../../source/sdn_controller/main_n2.py)
   - [source/sdn_controller/elasticity/elasticity.py](../../../../source/sdn_controller/elasticity/elasticity.py)
   - [source/sdn_controller/topology/topology.py](../../../../source/sdn_controller/topology/topology.py)
5. Keep documentation changes out of scope for this pass.

## Why This Shape

The current file mixes five responsibilities that are tightly coupled but still
separable for reasoning purposes:

1. import-time config and lightweight types
2. controller-owned mutable VIP-routing state
3. backend selection logic
4. DNAT and SNAT flow programming
5. ingress handling for ARP, VIP packet dispatch, and punt rules

The safest split is therefore not additional internal mixins. It is one public
facade class delegating into one private helper package. That preserves the
current inheritance shape and avoids new MRO risk around cooperative hooks like
`__init__` and `_on_datapath_connected`.

## Public Contract To Preserve

The refactor must preserve these caller-facing methods on
[source/sdn_controller/vip_routing.py](../../../../source/sdn_controller/vip_routing.py):

1. `snoop_arp`
2. `handle_vip_packet_in`
3. `register_backend_ip`
4. `register_new_server_backend`
5. `unregister_server_backend`
6. `unregister_storage_backend`
7. `update_server_stats`
8. `update_storage_stats`
9. `install_vip_arp_punt_rules`
10. `install_vip_punt_rules`

The refactor must also preserve the current cooperative behavior of:

1. `__init__`
2. `_on_datapath_connected`

## Target Structure

Keep [source/sdn_controller/vip_routing.py](../../../../source/sdn_controller/vip_routing.py)
as the only public module.

Add one private helper package:

- [source/sdn_controller/_vip_routing](../../../../source/sdn_controller/_vip_routing)

Planned internal modules:

1. [source/sdn_controller/_vip_routing/config.py](../../../../source/sdn_controller/_vip_routing/config.py)
2. [source/sdn_controller/_vip_routing/state.py](../../../../source/sdn_controller/_vip_routing/state.py)
3. [source/sdn_controller/_vip_routing/selection.py](../../../../source/sdn_controller/_vip_routing/selection.py)
4. [source/sdn_controller/_vip_routing/flows.py](../../../../source/sdn_controller/_vip_routing/flows.py)
5. [source/sdn_controller/_vip_routing/ingress.py](../../../../source/sdn_controller/_vip_routing/ingress.py)

## File Ownership Plan

### Public Facade

[source/sdn_controller/vip_routing.py](../../../../source/sdn_controller/vip_routing.py)
should keep only:

1. the public class docstring
2. `VipRoutingMixin`
3. cooperative `__init__`
4. cooperative `_on_datapath_connected`
5. thin delegating methods for the remaining behavior

### Shared Config And Lightweight Types

[source/sdn_controller/_vip_routing/config.py](../../../../source/sdn_controller/_vip_routing/config.py)
should own:

1. `logger`
2. `WarmLease`
3. server WSM weights
4. storage WSM weights
5. generic VIP timeouts
6. recovery VIP timeouts
7. cross-network router configuration

### Controller State And Lifecycle Helpers

[source/sdn_controller/_vip_routing/state.py](../../../../source/sdn_controller/_vip_routing/state.py)
should own the logic that operates on facade state for:

1. initial VIP-routing state setup
2. backend IP registration
3. warm lease creation and clearing
4. server backend register and unregister
5. storage backend register and unregister
6. telemetry cache updates
7. storage-choice memory cleanup

All mutable state remains on `self`.

### Backend Selection

[source/sdn_controller/_vip_routing/selection.py](../../../../source/sdn_controller/_vip_routing/selection.py)
should own:

1. warm-lease claiming
2. remembered normal storage-choice tracking
3. recovery filtering
4. `select_server`
5. `select_storage`

### Flow Programming

[source/sdn_controller/_vip_routing/flows.py](../../../../source/sdn_controller/_vip_routing/flows.py)
should own:

1. DNAT and SNAT rule construction
2. backend output-port resolution
3. first-packet `PacketOut`

### Ingress And VIP Handling

[source/sdn_controller/_vip_routing/ingress.py](../../../../source/sdn_controller/_vip_routing/ingress.py)
should own:

1. VIP binding iteration
2. ARP snooping
3. VIP packet dispatch
4. ARP reply generation
5. VIP server handling
6. VIP data handling
7. ARP punt-rule installation
8. IP punt-rule installation

## Step-By-Step Plan

### Step 1 - Create the private helper package

Create:

1. [source/sdn_controller/_vip_routing/__init__.py](../../../../source/sdn_controller/_vip_routing/__init__.py)
2. [source/sdn_controller/_vip_routing/config.py](../../../../source/sdn_controller/_vip_routing/config.py)
3. [source/sdn_controller/_vip_routing/state.py](../../../../source/sdn_controller/_vip_routing/state.py)
4. [source/sdn_controller/_vip_routing/selection.py](../../../../source/sdn_controller/_vip_routing/selection.py)
5. [source/sdn_controller/_vip_routing/flows.py](../../../../source/sdn_controller/_vip_routing/flows.py)
6. [source/sdn_controller/_vip_routing/ingress.py](../../../../source/sdn_controller/_vip_routing/ingress.py)

Do not move behavior yet.

### Step 2 - Extract shared config and lightweight types

Move the following from
[source/sdn_controller/vip_routing.py](../../../../source/sdn_controller/vip_routing.py)
to [source/sdn_controller/_vip_routing/config.py](../../../../source/sdn_controller/_vip_routing/config.py):

1. `logger`
2. `WarmLease`
3. `_W_CPU`
4. `_W_RAM`
5. `_W_REQUESTS`
6. `_W_HOPS`
7. `_W_STORAGE_CPU`
8. `_W_STORAGE_RAM`
9. `_W_STORAGE_CONNECTIONS`
10. `_W_STORAGE_LAG`
11. `_W_STORAGE_HOPS`
12. `_VIP_IDLE_TIMEOUT`
13. `_VIP_HARD_TIMEOUT`
14. `_VIP_DATA_RECOVERY_IDLE_TIMEOUT`
15. `_VIP_DATA_RECOVERY_HARD_TIMEOUT`
16. `_ROUTER_OVS_PORT`
17. `_ROUTER_MAC`

Constraints:

1. preserve import-time env parsing
2. preserve constant names
3. preserve default values

Validation after this step:

1. compile [source/sdn_controller/vip_routing.py](../../../../source/sdn_controller/vip_routing.py)
2. compile [source/sdn_controller/main_n1.py](../../../../source/sdn_controller/main_n1.py)
3. compile [source/sdn_controller/main_n2.py](../../../../source/sdn_controller/main_n2.py)

### Step 3 - Extract controller state and lifecycle helpers

Keep `VipRoutingMixin.__init__` in
[source/sdn_controller/vip_routing.py](../../../../source/sdn_controller/vip_routing.py),
but move the state-setup logic into a helper function in
[source/sdn_controller/_vip_routing/state.py](../../../../source/sdn_controller/_vip_routing/state.py).

Extract the logic for:

1. `_ip_to_mac` and `_mac_to_ip` setup
2. `_server_stats` and `_storage_stats` setup
3. round-robin counters
4. warm-lock and warm-lease maps
5. last-normal storage-choice memory
6. `register_backend_ip`
7. `mark_server_backend_warm`
8. `mark_storage_backend_warm`
9. `clear_server_backend_warm`
10. `clear_storage_backend_warm`
11. `register_new_server_backend`
12. `unregister_server_backend`
13. `unregister_storage_backend`
14. `update_server_stats`
15. `update_storage_stats`

Constraints:

1. keep mutable state on `self`
2. keep attribute names unchanged
3. keep log messages unchanged where possible

Validation after this step:

1. compile [source/sdn_controller/vip_routing.py](../../../../source/sdn_controller/vip_routing.py)
2. compile [source/sdn_controller/elasticity/elasticity.py](../../../../source/sdn_controller/elasticity/elasticity.py)
3. smoke-import `VipRoutingMixin`

### Step 4 - Extract selection logic

Move the following into
[source/sdn_controller/_vip_routing/selection.py](../../../../source/sdn_controller/_vip_routing/selection.py):

1. `_claim_warm_backend`
2. `_remember_normal_storage_choice`
3. `_forget_normal_storage_choice`
4. `_filter_previous_normal_backend`
5. `select_server`
6. `select_storage`

Constraints:

1. preserve the current storage decision order exactly:
   1. choose pool
   2. apply recovery filter when requested
   3. claim warm lease if possible
   4. run WSM fallback
   5. apply round-robin tie-break
2. preserve the current hop fallback rules
3. preserve current treatment of missing telemetry
4. preserve current remembered-normal behavior for recovery

Validation after this step:

1. compile [source/sdn_controller/vip_routing.py](../../../../source/sdn_controller/vip_routing.py)
2. compile [source/sdn_controller/main_n1.py](../../../../source/sdn_controller/main_n1.py)
3. compile [source/sdn_controller/main_n2.py](../../../../source/sdn_controller/main_n2.py)

### Step 5 - Extract flow programming

Move `_install_vip_dnat_snat` into
[source/sdn_controller/_vip_routing/flows.py](../../../../source/sdn_controller/_vip_routing/flows.py).

If needed, add one tiny private helper in the same module for backend-port
resolution only.

Constraints:

1. preserve DNAT match fields
2. preserve SNAT match fields
3. preserve action order
4. preserve router-MAC cross-network behavior
5. preserve recovery TCP-port narrowing
6. preserve timeout selection
7. preserve first-packet `PacketOut`

Validation after this step:

1. compile [source/sdn_controller/vip_routing.py](../../../../source/sdn_controller/vip_routing.py)
2. compile [source/sdn_controller/main_n1.py](../../../../source/sdn_controller/main_n1.py)
3. compile [source/sdn_controller/main_n2.py](../../../../source/sdn_controller/main_n2.py)

### Step 6 - Extract ingress and VIP handling

Move the following into
[source/sdn_controller/_vip_routing/ingress.py](../../../../source/sdn_controller/_vip_routing/ingress.py):

1. `_iter_vip_bindings`
2. `snoop_arp`
3. `handle_vip_packet_in`
4. `_reply_vip_arp`
5. `_handle_vip_server`
6. `_handle_vip_data`
7. `install_vip_arp_punt_rules`
8. `install_vip_punt_rules`

Keep `_on_datapath_connected` in the facade file.

Constraints:

1. preserve the packet path relative to:
   - [source/sdn_controller/main_n1.py](../../../../source/sdn_controller/main_n1.py)
   - [source/sdn_controller/main_n2.py](../../../../source/sdn_controller/main_n2.py)
2. preserve the current VIP binding set:
   - `VIP_SERVER`
   - `VIP_DATA_N1`
   - `VIP_DATA_N2`
   - `VIP_DATA_RECOVERY_N1`
   - `VIP_DATA_RECOVERY_N2`
3. preserve the current protocol filtering behavior
4. preserve current recovery-path TCP checks

Validation after this step:

1. compile [source/sdn_controller/vip_routing.py](../../../../source/sdn_controller/vip_routing.py)
2. compile [source/sdn_controller/main_n1.py](../../../../source/sdn_controller/main_n1.py)
3. compile [source/sdn_controller/main_n2.py](../../../../source/sdn_controller/main_n2.py)

### Step 7 - Rebuild the facade as thin delegation

Reduce [source/sdn_controller/vip_routing.py](../../../../source/sdn_controller/vip_routing.py)
to:

1. the public class
2. the public class docstring
3. cooperative `__init__`
4. cooperative `_on_datapath_connected`
5. thin delegating methods

Recommended facade shape:

```python
from ._vip_routing import config, flows, ingress, selection, state


class VipRoutingMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        state.init_vip_routing_state(self)

    def _on_datapath_connected(self, datapath) -> None:
        super()._on_datapath_connected(datapath)
        self.install_vip_arp_punt_rules(datapath)
        self.install_vip_punt_rules(datapath)

    def snoop_arp(self, pkt) -> None:
        return ingress.snoop_arp(self, pkt)

    def handle_vip_packet_in(self, datapath, in_port, pkt, eth) -> bool:
        return ingress.handle_vip_packet_in(self, datapath, in_port, pkt, eth)

    def select_server(self, client_mac: str):
        return selection.select_server(self, client_mac)

    def select_storage(self, domain: str, client_mac: str, *, recovery: bool = False):
        return selection.select_storage(self, domain, client_mac, recovery=recovery)

    def _install_vip_dnat_snat(self, datapath, in_port, pkt, **kwargs):
        return flows.install_vip_dnat_snat(self, datapath, in_port, pkt, **kwargs)
```

Constraints:

1. keep `VipRoutingMixin` as the only public facade class
2. keep import path unchanged
3. keep method names and signatures unchanged

### Step 8 - Run focused validation

Run these checks after the facade is fully rebuilt.

#### Syntax and import checks

```powershell
python -m py_compile `
  source/sdn_controller/vip_routing.py `
  source/sdn_controller/main_n1.py `
  source/sdn_controller/main_n2.py `
  source/sdn_controller/elasticity/elasticity.py `
  source/sdn_controller/topology/topology.py
```

#### Facade contract smoke check

```powershell
python -c "from source.sdn_controller.vip_routing import VipRoutingMixin; required = ['snoop_arp','handle_vip_packet_in','update_server_stats','update_storage_stats','register_backend_ip','register_new_server_backend','unregister_server_backend','unregister_storage_backend','install_vip_arp_punt_rules','install_vip_punt_rules']; print(all(hasattr(VipRoutingMixin, name) for name in required))"
```

#### Diagnostics

1. run diagnostics on the touched files
2. fix any import or type errors introduced by the split

#### Final review

1. inspect the final diff only after the executable checks pass

## Rollback Rules

1. If any extraction slice breaks imports, stop and fix that slice before moving on.
2. If the facade no longer imports cleanly, do not continue to the next slice.
3. If `_on_datapath_connected` requires non-trivial delegation tricks, keep more
   of that logic in the facade rather than forcing it into helpers.
4. If any caller file needs changes to accommodate the split, treat that as a
   plan violation and revert to the last safe slice.
5. If any function cannot be moved without behavior uncertainty, keep it in the
   facade for this pass.

## Explicit Non-Goals

This plan does not do any of the following:

1. change runtime behavior
2. rename public methods
3. rename controller-owned instance attributes
4. alter log semantics intentionally
5. change MRO shape in the controller entry points
6. update docs outside this plan file
7. introduce new external packages
8. rewrite VIP routing into service objects or dataclass-owned state graphs

## Dependencies

1. Continue relying on topology-owned attributes from
   [source/sdn_controller/topology/topology.py](../../../../source/sdn_controller/topology/topology.py).
2. Continue relying on the concrete flow installer in:
   - [source/sdn_controller/main_n1.py](../../../../source/sdn_controller/main_n1.py)
   - [source/sdn_controller/main_n2.py](../../../../source/sdn_controller/main_n2.py)
3. Continue exposing the lifecycle hooks expected by
   [source/sdn_controller/elasticity/elasticity.py](../../../../source/sdn_controller/elasticity/elasticity.py).
4. No new external dependencies are required.

## Final File Map

### File To Modify

1. [source/sdn_controller/vip_routing.py](../../../../source/sdn_controller/vip_routing.py)

### Files To Create

1. [source/sdn_controller/_vip_routing/__init__.py](../../../../source/sdn_controller/_vip_routing/__init__.py)
2. [source/sdn_controller/_vip_routing/config.py](../../../../source/sdn_controller/_vip_routing/config.py)
3. [source/sdn_controller/_vip_routing/state.py](../../../../source/sdn_controller/_vip_routing/state.py)
4. [source/sdn_controller/_vip_routing/selection.py](../../../../source/sdn_controller/_vip_routing/selection.py)
5. [source/sdn_controller/_vip_routing/flows.py](../../../../source/sdn_controller/_vip_routing/flows.py)
6. [source/sdn_controller/_vip_routing/ingress.py](../../../../source/sdn_controller/_vip_routing/ingress.py)

### Files Expected To Remain Unchanged

1. [source/sdn_controller/main_n1.py](../../../../source/sdn_controller/main_n1.py)
2. [source/sdn_controller/main_n2.py](../../../../source/sdn_controller/main_n2.py)
3. [source/sdn_controller/elasticity/elasticity.py](../../../../source/sdn_controller/elasticity/elasticity.py)
4. [source/sdn_controller/topology/topology.py](../../../../source/sdn_controller/topology/topology.py)

## Execution Order Summary

1. create the private helper package
2. extract shared config and types
3. extract state and lifecycle helpers
4. extract selection logic
5. extract flow programming
6. extract ingress logic
7. slim the facade
8. run focused validation after each slice
9. review the final diff only after executable checks pass

## Documentation Scope

Deferred.

No documentation files other than this plan should be changed in this pass.
