# MongoDB Sharding + Multi-LAN SDN Topology (Step-by-Step)

## 1. High-Level Goal

- Three L2 segments (A, B, C) each with an OVS bridge managed by one OS-Ken controller.
- A router (Linux or VyOS) interconnects the LANs.
- A MongoDB sharded cluster: one shard replica-set per segment; config servers + mongos on the controller node.
- Each switch logs packet/flow events to the nearest shard. Local analytics build a NetworkX graph per LAN. Global topology fused in the primary database.

## 2. Lab Topology Bring-Up

1. Provision VMs or containers: `ctrl` (OS-Ken + mongos + config server), `router`, `lan-a-hosts`, `lan-b-hosts`, `lan-c-hosts`.
2. On `router`, create three VLAN or subinterfaces (e.g., `eth0.10`, `eth0.20`, `eth0.30`) toward the LAN bridges.
3. Deploy an OVS bridge per LAN (`brA`, `brB`, `brC`). Attach hosts and router subinterfaces.
4. Start OS-Ken controller listening on management network; configure each OVS to use the controller (`ovs-vsctl set-controller brA tcp:ctrl:6653`, etc.).

## 3. MongoDB Sharded Cluster

1. For each LAN, run a shard replica set inside that segment (e.g., `shardA1`, `shardA2`, `shardA3`). Bind to LAN subnet so hosts log locally.
2. Deploy the config server replica set on the controller host (or mgmt network) because it must be reachable by all shards.
3. Start a `mongos` router on the controller node; configure `/etc/mongos.conf` with config server addresses.
4. Connect to `mongos` and run: `sh.addShard("shardA/hostA1:27017,hostA2:27017,hostA3:27017")`, repeat for shards B and C.
5. Enable sharding on the `sdn_logs` database, then shard the `events` collection on compound key `{lanId: 1, ts: 1}` to keep locality.

### 3.1 Replica Sets and Shard Internals

- **Replica set anatomy**

Each shard (and the config server) runs as a replica set: a named group of `mongod` processes. Initialization uses `replSetInitiate` with a config document such as:

```json
{
  "_id": "shardA",
  "members": [
    {"_id": 0, "host": "shardA1:27018"},
    {"_id": 1, "host": "shardA2:27018"},
    {"_id": 2, "host": "shardA3:27018"}
  ]
}
```

The `_id` matches the `--replSet` flag given to each `mongod`. Member `_id` values are unique integers; `host` strings are reachable addresses. For config servers add `"configsvr": true` and use the dedicated port (27019 in examples).

- **Election and failover**

One member becomes primary while others stay secondary. Writes target the primary; secondaries replicate via the oplog. If the primary fails, a new election promotes a secondary. Clients using a replica-set URI (`mongodb://n1,n2/?replicaSet=shardA`) automatically follow the change.

- **Shard registration**

After replica sets are healthy, connect to `mongos` and call `addShard("shardA/shardA1:27018,shardA2:27018,shardA3:27018")`. Each shard contributes its data to the global cluster namespace managed by the config server replica set.

- **Sharding metadata flow**

Config servers store database/collection metadata and chunk ranges. `mongos` caches this metadata and routes reads/writes to the correct shard based on the shard key. The balancer moves chunks between shards if distribution becomes uneven; in this topology most data remains local because the shard key begins with `lanId`.

- **Python automation**

All setup commands above can be invoked with PyMongo: `client.admin.command("replSetInitiate", config)`, `client.admin.command("addShard", "shardA/...")`, `client.admin.command("shardCollection", ...)`. Keep a bootstrap script that provisions config servers, shard replica sets, and sharding metadata to avoid manual `mongosh` steps.

## 4. Controller Logging Enhancements

1. Extend `KenLearnAndLog` to accept a `lan_id` and `shard_uri` per switch (via config file).
2. Instantiate separate `MongoClient` instances pointing to the local shard RS; use `readPreference=primaryPreferred` to survive elections.
3. When logging packet_in/flow events, include fields: `{lanId, dpid, src, dst, in_port, out_port, ts}`.
4. Add a periodic flush that writes aggregated stats (flow counts, host discovery) into a local `topology_nodes` and `topology_edges` collection.

## 5. Local Topology Discovery with NetworkX

1. For each LAN, run a worker (inside controller process or separate service) that reads `topology_nodes/edges` and builds a `networkx.Graph`.
2. Nodes: switches, hosts, router interface on that LAN. Edges: port-level connections.
3. Persist the serialized graph (e.g., `nx.node_link_data`) back into `topology_snapshots` with `{lanId, ts}`.

## 6. Global View Aggregation

1. On the controller host, schedule a job (e.g., every minute) connecting to `mongos`.
2. Fetch the latest snapshot per `lanId`; merge them by stitching router interfaces (known mapping `lanId -> router port`).
3. Build a global NetworkX `Graph` or `DiGraph` capturing cross-LAN paths.
4. Store the merged topology into `global_topology_snapshots` with metadata (timestamp, hash of inputs).

## 7. Router Awareness

1. Configure the router to export interface stats (via SNMP, Netlink, or log to MongoDB) to detect inter-LAN traffic.
2. Correlate router data with per-LAN logs to verify path completeness.
3. Optionally use LLDP inside each LAN to auto-discover host ports and annotate `topology_edges`.

## 8. Data Governance & TTL

- Apply TTL indexes on `events` (24h) and on `topology_snapshots` (e.g., 7 days) per shard to avoid storage explosion.
- Ensure `global_topology_snapshots` keeps longer history (30-60 days) for trend analysis.

## 9. Testing Checklist

1. Validate each LAN individually: host discovery, local NetworkX graph, shard writes.
2. Disconnect one shard node to confirm replica-set tolerance; check logging continuity.
3. Generate traffic across LANs; ensure router stats + cross-LAN edges appear in global view.
4. Kill `mongos` or config server to test control-plane resilience (controller should queue writes until available).
5. Run integration script that prints merged topology and verifies expected nodes/edges.

## 10. Next Steps

- Add Prometheus exporters per shard/lan for visibility.
- Introduce decision engine that uses global topology to recommend reroutes or QoS tweaks.
- Explore partitioning strategies when scaling beyond three LANs (e.g., shard tags, zone awareness).
