# MongoDB Sharding + Multi-LAN SDN Topology (Step-by-Step)

## Network Topology (Two-Network Example)

- Two isolated networks, each with its own OVS switch and MongoDB container.
- Each MongoDB instance runs as a single-node replica set (for sharding).
- The SDN controller (via `database.py`) does the following:
  - Connects only to the mongodb-router.
  - Initiates 

## 1. High-Level Goal

- Three L2 segments (A, B) each with an OVS bridge managed by one OS-Ken controller.
- A router (Linux or VyOS) interconnects the LANs.
- A MongoDB sharded cluster: one shard replica-set per segment; config servers + mongos on the controller node.
- Each switch logs packet/flow events to the nearest shard. Local analytics build a NetworkX graph per LAN. Global topology fused in the primary database.

## 2. Lab Topology Bring-Up

1. Provision VMs or containers: `ctrl` (OS-Ken + mongos + config server), `router`, `lan-a-hosts`, `lan-b-hosts.`
2. On `router`, use eth0 to connected LAN bridges to WAN.
3. Deploy an OVS bridge per LAN (`brA`, `brB)`. Attach hosts and router subinterfaces.
4. Start OS-Ken controller listening on management network; configure each OVS to use the controller (`ovs-vsctl set-controller brA tcp:ctrl:6653`, etc.).

## 3. MongoDB Sharded Cluster

1. For each LAN, run a shard replica set inside that segment (e.g., `shardA1`, `shardA2`, `shardA3`). Bind each MongoDB process to both the host-facing IP (e.g., 10.0.0.4 for LAN A) and loopback (127.0.0.1) to allow early controller calls via localhost and external connectivity for the cluster.
2. Deploy the config server replica set on the controller host (or mgmt network) because it must be reachable by all shards. Bind to both 192.168.100.1 and 127.0.0.1.
3. Start a `mongos` router on the controller node; configure `/etc/mongos.conf` with config server addresses. Bind to both 192.168.100.1 and 127.0.0.1.
4. Connect to `mongos` and run: `sh.addShard("shardA/10.0.0.4:27017")`, repeat for shards B and C (e.g., `sh.addShard("shardB/10.0.1.4:27017")`).
5. Enable sharding on the `sdn_logs` database, then shard the `events` collection on compound key `{lanId: 1, ts: 1}` to keep locality.

### 3.1 Replica Sets and Shard Internals

- **Replica set anatomy**

Each shard (and the config server) runs as a replica set: a named group of `mongod` processes. Initialization uses `replSetInitiate` with a config document such as:

```json
{
  "_id": "shardA",
  "members": [
    {"_id": 0, "host": "10.0.0.4:27017"}
  ]
}
```

For config servers, use port 27019 and add `"configsvr": true`:

```json
{
  "_id": "configReplSet",
  "configsvr": true,
  "members": [
    {"_id": 0, "host": "192.168.100.1:27019"}
  ]
}
```

### 3.2 Binding IP Addresses

Letting each MongoDB process bind to both the host-facing IP and loopback solves a scoping mismatch:

You start the config server, shards, and mongos with --network host. They listen only on the interfaces you pass in --bind_ip.
Before the veth wiring finishes, those containers can still reach themselves only via loopback. Later, you still want your host to reach them on 192.168.100.1 (config) and 10.0.x.x (shards).
Binding to the host IP and 127.0.0.1 covers both cases. Early controller calls like mongo --host 127.0.0.1 succeed inside the container, while the SDN controller and mongos keep using the host IP.
It’s the union of both address scopes that makes it work once—no more “connection refused” when a tool defaults to localhost, and no loss of external connectivity for the cluster.

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