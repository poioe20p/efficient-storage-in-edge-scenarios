# Topology Documentation Split Plan

## Scope

Refresh and split the current topology overview into a short hub page plus
dedicated documents for local discovery and proactive flows, backend roles and
VIP pools, and peer topology exchange plus snapshot models.

This plan is scoped to the topology documentation area. Do not retarget links
outside `docs/operation/topology` in this pass.

Keep Tier 1 material topology-focused: document the `storage_roles` contract
and peer-primary lookup where topology owns them, then point outward to the
selective-sync overview instead of re-explaining that subsystem here.

## Review Workflow

1. Execute one step at a time.
2. Stop after each review checkpoint.
3. Review the output of the current step before starting the next one.
4. Do not batch multiple steps into one implementation pass.

## Target Files

### Files To Create

1. `docs/operation/topology/topology_local_discovery_and_flows.md`
2. `docs/operation/topology/topology_backend_roles_and_vip_pools.md`
3. `docs/operation/topology/topology_peer_exchange_and_models.md`

### Conditional File To Create

1. `docs/operation/topology/topology_wan_emulation.md`

Create this file only if the WAN section cannot stay short in the trimmed
overview.

### Files To Update

1. `docs/operation/topology/topology_overview.md`

## Step 1 - Create the new document structure

Create these files with titles and section headings only. Do not move content
yet.

1. `docs/operation/topology/topology_local_discovery_and_flows.md`
2. `docs/operation/topology/topology_backend_roles_and_vip_pools.md`
3. `docs/operation/topology/topology_peer_exchange_and_models.md`

Use these section headings.

### `topology_local_discovery_and_flows.md`

1. Purpose
2. Current Files
3. OS-Ken Topology Service Dependency
4. Local Discovery Poll Loop
5. Router Filtering
6. Host Attachment and Graph Build
7. Hop Cache and Average Hop Count
8. Switch Reconnect Handling
9. Proactive Flow Installation
10. Reactive Learning Boundary

### `topology_backend_roles_and_vip_pools.md`

1. Purpose
2. Current Files
3. VIP Address Set
4. Local and Peer MAC Role Sets
5. Dynamic Backend Registration
6. VIP Pool Rebuild Rules
7. Storage Role Tracking
8. Peer Primary Resolution Contract
9. Short Tier 1 Reference

### `topology_peer_exchange_and_models.md`

1. Purpose
2. Current Files
3. Topology Models
4. Published Snapshot Shape
5. Publish Triggers
6. Peer Update Receive Path
7. Peer MAC and Role Replacement Rules
8. Peer Host IP Seeding
9. Backward-Compatibility Fields

### Review checkpoint 1

Verify:

1. All three new files exist
2. File names are correct
3. Section headings are present
4. No content has been moved yet

## Step 2 - Rewrite the overview as a short hub page

Update `docs/operation/topology/topology_overview.md`.

Keep only these parts:

1. Purpose and scope of the topology subsystem
2. A short architecture summary covering local discovery, proactive flow
   installation, VIP-pool rebuild, and peer topology exchange
3. A document map linking to:
   1. local discovery and proactive flows
   2. backend roles and VIP pools
   3. peer topology exchange and models
4. A short note that topology feeds VIP routing and also exposes the
   `storage_roles` contract used by selective sync
5. A short WAN emulation note if it fits cleanly in the overview, otherwise a
   short link placeholder to a separate WAN note created later

Remove these parts from the overview:

1. Full local discovery walkthrough details
2. Full proactive-flow priority tables and per-path installation detail
3. Full VIP and role-management detail tables
4. Full topology snapshot field-by-field contract detail
5. Long WAN explanation if it prevents the overview from staying compact
6. Any stale wording that says router filtering comes from
   `ROUTER_MAC_BLOCKLIST`
7. Any stale wording that says proactive topology flows cover peer-discovered
   hosts
8. Any stale wording that says peer-primary resolution returns `ip:27017`
9. Any stale wording that omits the recovery VIP_DATA addresses now owned by
   the topology mixin
10. Any stale wording that omits `type`, `ts`, or `storage_roles` from the
    current snapshot model

### Review checkpoint 2

Verify:

1. The overview is short
2. The overview acts as a hub page
3. The overview links to all split documents
4. Tier 1 is referenced briefly, not re-explained

## Step 3 - Fill the local discovery and proactive flows document

Update `docs/operation/topology/topology_local_discovery_and_flows.md`.

Include:

1. The current files:
   1. `source/sdn_controller/topology/topology.py`
   2. `source/sdn_controller/main_n1.py`
2. The current OS-Ken dependency note through `REQUIRED_APP` in the mixin and
   `_REQUIRED_APP` in `main_n1.py`
3. The current worker loop through `_topology_worker()`
4. The current local discovery path through `_get_topology_api_app()` and
   `get_sws_links_hosts()`
5. The current router filtering rule through the built-in
   `_router_mac_blocklist`
6. The current host-attachment and NetworkX graph build path
7. The current hop-cache rebuild through `_rebuild_hop_cache()`, including
   `_hop_cache_max` and `_avg_hop_count`
8. The current switch reconnect handling through `_state_change_handler()`,
   stale-flow flush, table-miss reinstall, and `_on_datapath_connected()`
9. The current proactive-flow installation path through
   `_install_local_topology_flows()`, `send_all_flow_rules_proactively()`,
   `_install_path_flows()`, and `proactive_flow_rule_install()`
10. The current boundary that proactive topology flows are installed for local
    host pairs discovered in `self.hosts`, not for peer-only hosts
11. The current relationship to reactive learning in `main_n*.py` as a short
    boundary note only

Do not include:

1. Full VIP pool membership details
2. Full peer topology publish and receive contract details
3. Long Tier 1 or selective-sync rationale

### Review checkpoint 3

Verify:

1. The file is discovery-and-flow focused
2. The router-filtering description matches the current code
3. The proactive-flow scope matches the current local-host behavior
4. The reconnect path is covered

## Step 4 - Fill the backend roles and VIP pools document

Update `docs/operation/topology/topology_backend_roles_and_vip_pools.md`.

Include:

1. The current file:
   1. `source/sdn_controller/topology/topology.py`
2. The current VIP address set:
   1. `VIP_SERVER`
   2. `VIP_DATA_N1`
   3. `VIP_DATA_N2`
   4. `VIP_DATA_RECOVERY_N1`
   5. `VIP_DATA_RECOVERY_N2`
3. The current local and peer MAC role sets for server and storage backends
4. The union properties `_server_macs`, `_storage_macs_n1`, and
   `_storage_macs_n2`
5. The current dynamic registration methods:
   1. `add_server_mac()`
   2. `remove_server_mac()`
   3. `add_storage_mac()`
   4. `remove_storage_mac()`
6. The current VIP-pool rebuild path through `_rebuild_vip_pools()`
7. The current rule that only configured and reachable hosts appear in the VIP
   pools
8. The current storage-role tracking methods:
   1. `update_storage_role()`
   2. `sync_storage_roles()`
   3. `forget_storage_role()`
9. The current peer-primary lookup contract through
   `resolve_peer_primary(peer_network_id)` returning `(rs_name, "ip:27018")`
   or `None`
10. A short note that topology provides this contract for selective sync, with
    a reference to the selective-sync overview for subsystem-level behavior

Do not include:

1. Full peer snapshot serialization detail
2. Full worker-loop discovery detail
3. Full selective-sync lifecycle or policy detail

### Review checkpoint 4

Verify:

1. The file is roles-and-pools focused
2. Recovery VIPs are included
3. The peer-primary port matches the current code
4. Tier 1 remains a short reference only

## Step 5 - Fill the peer topology exchange and models document

Update `docs/operation/topology/topology_peer_exchange_and_models.md`.

Include:

1. The current files:
   1. `source/sdn_controller/topology/models.py`
   2. `source/sdn_controller/topology/topology.py`
   3. `source/sdn_controller/main_n1.py`
2. The current model set:
   1. `TopologyHostEntry`
   2. `TopologyLinkEntry`
   3. `TopologyNetworkSection`
   4. `TopologySnapshot`
3. The current `TopologySnapshot` fields, including:
   1. `type`
   2. `network_id`
   3. `networks`
   4. flat compatibility fields `hosts`, `links`, and `switches`
   5. `hops`
   6. `ts`
   7. `avg_hop_count`
   8. `server_macs`
   9. `storage_macs_n1`
   10. `storage_macs_n2`
   11. `storage_roles`
4. The current publish path through `_publish_topology()`
5. The current publish triggers in `_topology_worker()`:
   1. first valid topology
   2. local change
   3. correction publish
   4. heartbeat publish
6. The current receive path through `on_topology_update()` after callback
   wiring from `ZmqTelemetrySource`
7. The current stale-peer detection logic through `_topo_correction_needed`
8. The current wholesale replacement rule for peer MAC sets and peer
   `storage_roles`
9. The current peer-host IP seeding through `register_backend_ip()`
10. The current reason flat compatibility fields still exist in the snapshot

Do not include:

1. Full VIP routing cost-function detail
2. Full backend-role rationale already moved to the roles document
3. Long WAN shaping detail

### Review checkpoint 5

Verify:

1. The file is peer-exchange-and-model focused
2. The snapshot field list matches the current models
3. Publish triggers are covered
4. Peer role replacement and IP seeding are covered

## Step 6 - Decide WAN placement and update accordingly

Assess whether WAN emulation can stay short in the trimmed overview.

Keep WAN in `topology_overview.md` only if all of the following are true:

1. It fits in one short section
2. It only needs a concise statement of purpose
3. It only needs short references to:
   1. `source/scripts/wan.env`
   2. `source/scripts/network/inject_wan_latency.sh`
   3. `source/scripts/tools/wan_set.sh`
4. It only needs one short note that shaping applies to inter-LAN router
   interfaces, not the Internet uplink

If that is not true, create `docs/operation/topology/topology_wan_emulation.md`
and move the full WAN content there.

If the separate WAN file is created, include these section headings:

1. Purpose
2. Current Files
3. Why WAN Shaping Is Needed
4. Router Interface Scope
5. Configuration Inputs
6. Apply Path During Bringup
7. Runtime Retuning
8. Profiles and Caveats

Then reduce the overview to a short WAN summary plus a link to the new file.

### Review checkpoint 6

Verify:

1. WAN placement follows the short-versus-separate rule
2. The overview stays compact
3. If created, the WAN file stays operational and focused

## Step 7 - Consistency and stale-text cleanup pass

Do one final pass across the overview and all split topology documents.

Check and correct:

1. Router filtering is described as the current built-in blocklist, not an env
   var-driven setting
2. Proactive topology flows are described as local-host installation only
3. Recovery VIP_DATA addresses are included where topology-owned VIPs are
   listed
4. `resolve_peer_primary()` is documented with `ip:27018`
5. `TopologySnapshot` includes `type`, `ts`, and `storage_roles`
6. Tier 1 remains a short topology contract reference, not a full subsystem
   explanation
7. The overview remains a hub page after the cleanup pass
8. Terminology stays consistent across the split documents

### Review checkpoint 7

Verify:

1. Stale wording has been removed
2. File names stay consistent
3. The split matches the current code boundaries
4. The overview remains short after the cleanup pass
