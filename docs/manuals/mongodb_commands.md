# MongoDB Sharded Cluster: Verification and Troubleshooting (Docker-based)

This guide assumes each MongoDB component runs in its own Docker container:
- **Config Server Replica Set (CSRS)**: `mongodb-config-server` (replSet `configReplSet`, port 27019, IP 192.168.100.1)
- **Shard Replica Sets**: `mongodb-n1` (replSet `rs_net1`, IP 10.0.0.4:27017), `mongodb-n2` (replSet `rs_net2`, IP 10.0.1.4:27017)
- **Mongos Routers**: `mongodb-router` (port 27020, IP 192.168.100.1)

Replace container names, ports, and replica set names with your actual setup.

---

## 0) Quick Health Checklist

Check ports reachable:
```bash
nc -zv 127.0.0.1 27017 27019 27020
```

Verify connectivity to components:
```bash
docker exec -it mongodb-router nc -zv 10.0.0.4 27017  # mongodb-n1
docker exec -it mongodb-router nc -zv 10.0.1.4 27017  # mongodb-n2
docker exec -it mongodb-router nc -zv 192.168.100.1 27019  # config server
```

---

## 1) Validate mongos Router

Full cluster summary:
```bash
docker exec -it mongodb-router mongosh --host 192.168.100.1 --port 27020 --quiet --eval 'sh.status()'
```

Ping test:
```bash
docker exec -it mongodb-router mongosh --host 192.168.100.1 --port 27020 --quiet --eval 'db.adminCommand({ ping: 1 })'
```

List shards:
```bash
docker exec -it mongodb-router mongosh --host 192.168.100.1 --port 27020 --quiet --eval 'db.adminCommand({ listShards: 1 })'
```

Balancer actions:
```bash
docker exec -it mongodb-router mongosh --port 27020 --quiet --eval 'sh.getBalancerState()'
docker exec -it mongodb-router mongosh --port 27020 --quiet --eval 'sh.isBalancerRunning()'
```

Config metadata:
```bash
docker exec -it mongodb-router mongosh --port 27020 --quiet --eval 'db.getSiblingDB("config").shards.find().pretty()'
docker exec -it mongodb-router mongosh --port 27020 --quiet --eval 'db.getSiblingDB("config").databases.find().pretty()'
docker exec -it mongodb-router mongosh --port 27020 --quiet --eval 'db.getSiblingDB("config").collections.find({ dropped:false }).pretty()'
docker exec -it mongodb-router mongosh --port 27020 --quiet --eval 'db.getSiblingDB("config").chunks.find().limit(5).pretty()'
```

---

## 2) Check Config Server Replica Set (CSRS)

Status:
```bash
docker exec -it mongodb-config-server mongosh --quiet --port 27019 --eval 'rs.status()'
```

Config:
```bash
docker exec -it mongodb-config-server mongosh --quiet --port 27019 --eval 'rs.conf()'
```

Role/hello:
```bash
docker exec -it mongodb-config-server mongosh --quiet --port 27019 --eval 'db.hello()'
```

Logs:
```bash
docker logs --tail 200 mongodb-config-server
```

---

## 3) Check Each Shard Replica Set

Status:
```bash
docker exec -it mongodb-n1 mongosh --quiet --eval 'rs.status()'
docker exec -it mongodb-n2 mongosh --quiet --eval 'rs.status()'
```

Config:
```bash
docker exec -it mongodb-n1 mongosh --quiet --eval 'rs.conf()'
docker exec -it mongodb-n2 mongosh --quiet --eval 'rs.conf()'
```

Hello info:
```bash
docker exec -it mongodb-n1 mongosh --quiet --eval 'db.hello()'
docker exec -it mongodb-n2 mongosh --quiet --eval 'db.hello()'
```

Cluster-wide replica set status:
```bash
docker exec -it mongodb-router mongosh --port 27020 --quiet --eval 'db.adminCommand({ replSetGetStatus: 1 })'
```

Logs:
```bash
docker logs --tail 200 mongodb-n1
docker logs --tail 200 mongodb-n2
```

List documents in `events` and `topology` collections directly on each shard (requires authentication):
```bash
docker exec -it mongodb-n1 mongosh "mongodb://appuser:app.04.app@10.0.0.4:27017/appdb?authSource=appdb" --quiet --eval '
db.events.find().limit(5).forEach(doc => printjson(doc));
db.topology.find().limit(5).forEach(doc => printjson(doc));
'
docker exec -it mongodb-n1 mongosh --quiet --eval 'db = db.getSiblingDB("appdb"); db.events.find().limit(5).forEach(printjson); db.topology.find().limit(5).forEach(printjson);'



docker exec -it mongodb-n2 mongosh "mongodb://appuser:app.04.app@10.0.1.4:27017/appdb?authSource=appdb" --quiet --eval '
db.events.find().limit(5).forEach(doc => printjson(doc));
db.topology.find().limit(5).forEach(doc => printjson(doc));
'
docker exec -it mongodb-n2 mongosh --quiet --eval 'db = db.getSiblingDB("appdb"); db.events.find().limit(5).forEach(printjson); db.topology.find().limit(5).forEach(printjson);
```

---

## 4) Verify Shards Are Added to Cluster

List shards:
```bash
docker exec -it mongodb-router mongosh --host 192.168.100.1 --port 27020 --quiet --eval 'db.adminCommand({ listShards: 1 })'
```

Add shard:
```bash
docker exec -it mongodb-router mongosh --host 192.168.100.1 --port 27020 --quiet --eval 'sh.addShard("rs_net1/10.0.0.4:27017")'
docker exec -it mongodb-router mongosh --host 192.168.100.1 --port 27020 --quiet --eval 'sh.addShard("rs_net2/10.0.1.4:27017")'
```

Confirm:
```bash
docker exec -it mongodb-router mongosh --host 192.168.100.1 --port 27020 --quiet --eval 'db.getSiblingDB("config").shards.find().pretty()'
```

---

## 5) Enable Sharding on a Database/Collection

Enable sharding on a database:
```bash
docker exec -it mongodb-router mongosh --port 27020 --quiet --eval 'sh.enableSharding("testdb")'
```

Shard a collection:
```bash
docker exec -it mongodb-router mongosh --port 27020 --quiet --eval 'sh.shardCollection("testdb.coll", { _id: "hashed" })'
```

Confirm:
```bash
docker exec -it mongodb-router mongosh --port 27020 --quiet --eval 'db.getSiblingDB("config").collections.find({ _id: "testdb.coll" })'
docker exec -it mongodb-router mongosh --port 27020 --quiet --eval 'db.getSiblingDB("config").chunks.find({ ns: "testdb.coll" }).limit(5).pretty()'
```

Test distribution:
```bash
docker exec -it mongodb-router mongosh --port 27020 --quiet --eval '
db = db.getSiblingDB("testdb");
for (let i=0;i<1000;i++) db.coll.insert({ _id: i, v: "x" });
db.coll.getShardDistribution();
'
```

---

## 6) Balancer and Chunk Distribution

Check balancer:
```bash
docker exec -it mongodb-router mongosh --port 27020 --quiet --eval 'sh.getBalancerState()'
docker exec -it mongodb-router mongosh --port 27020 --quiet --eval 'sh.isBalancerRunning()'
```

Start/stop balancer:
```bash
docker exec -it mongodb-router mongosh --port 27020 --quiet --eval 'sh.startBalancer()'
docker exec -it mongodb-router mongosh --port 27020 --quiet --eval 'sh.stopBalancer()'
```

Count chunks per shard:
```bash
docker exec -it mongodb-router mongosh --port 27020 --quiet --eval '
db.getSiblingDB("config").chunks.aggregate([{ $group: { _id: "$shard", n: { $sum: 1 } } }])
'
```

---

## 7) Connectivity & Routing Sanity Checks

Basic read/write test:
```bash
docker exec -it mongodb-router mongosh --port 27020 --quiet --eval '
db = db.getSiblingDB("health");
db.test.insertOne({ ts: new Date() });
printjson(db.test.findOne());
'
```

Check mongos logs:
```bash
docker logs --tail 200 mongodb-router
```

---

## 8) Authentication and Roles (if enabled)

Connection status:
```bash
docker exec -it mongodb-router mongosh --port 27020 --quiet --eval 'db.runCommand({ connectionStatus: 1 })'
```

List users:
```bash
docker exec -it mongodb-router mongosh --port 27020 --quiet --eval 'db.getSiblingDB("admin").system.users.find().pretty()'
```

Show roles info:
```bash
docker exec -it mongodb-router mongosh --port 27020 --quiet --eval '
db = db.getSiblingDB("admin");
db.runCommand({ rolesInfo: 1, showPrivileges: true })
'
```

See if auth is enabled
mongosh --quiet --host <addr> --port <port> --eval "db.adminCommand({getCmdLineOpts:1}).parsed.security.authorization"

---

## 9) Feature Compatibility and Versions

Feature compatibility:
```bash
docker exec -it mongodb-router mongosh --port 27020 --quiet --eval 'db.adminCommand({ getParameter: 1, featureCompatibilityVersion: 1 })'
```

Version/role info:
```bash
docker exec -it mongodb-router mongosh --port 27020 --quiet --eval 'db.hello()'
```

---

## 10) Troubleshooting Common Issues

**Shard RS not healthy**
```bash
docker exec -it mongodb-n1 mongosh --quiet --eval 'rs.status()'
docker exec -it mongodb-n2 mongosh --quiet --eval 'rs.status()'
```
Reconfirm hostnames in `rs.conf()` are reachable by all members. Ensure ports are open and using `--bind_ip_all`.

**Config servers not a replica set**
Ensure they're started with `--replSet configReplSet`.
Run:
```bash
docker exec -it mongodb-config-server mongosh --quiet --host 192.168.100.1 --port 27019 --eval 'rs.status()'
```

**Shards missing in mongos**
Re-add:
```bash
docker exec -it mongodb-router mongosh --host 192.168.100.1 --port 27020 --quiet --eval 'sh.addShard("rs_net1/10.0.0.4:27017")'
docker exec -it mongodb-router mongosh --host 192.168.100.1 --port 27020 --quiet --eval 'sh.addShard("rs_net2/10.0.1.4:27017")'
```

**Balancer stuck**
```bash
docker exec -it mongodb-router mongosh --host 192.168.100.1 --port 27020 --quiet --eval 'sh.getActiveMigrations()'
docker exec -it mongodb-router mongosh --host 192.168.100.1 --port 27020 --quiet --eval 'db.getSiblingDB("config").locks.find().pretty()'
```

**Uneven data distribution**
```bash
docker exec -it mongodb-router mongosh --host 192.168.100.1 --port 27020 --quiet --eval 'db.getSiblingDB("config").settings.find({ _id: "chunksize" })'
```

---

## 11) Optional: Zone Sharding (by Region)

Assign zones:
```bash
docker exec -it mongodb-router mongosh --host 192.168.100.1 --port 27020 --quiet --eval '
sh.addShardToZone("rs_net1", "zoneA");
sh.updateZoneKeyRange("testdb.coll", { region: "A" }, { region: "A" }, "zoneA");
'
```

Verify zones:
```bash
docker exec -it mongodb-router mongosh --host 192.168.100.1 --port 27020 --quiet --eval 'db.getSiblingDB("config").tags.find().pretty()'
```

---

## 12) Programmatic Checks from Python

```python
from pymongo import MongoClient

client = MongoClient("mongodb://localhost:27020/?appName=cluster-check")
print(client.admin.command("ping"))

# list shards
print(client.admin.command({"listShards": 1}))

# simple write/read test
db = client["testdb"]
db.test.insert_one({"x": 1})
print(db.test.find_one({"x": 1}))
```

---

## 13) Docker Runtime Checks

Running commands in Docker:

List container command/args:
```bash
docker inspect --format='{{.Config.Cmd}}' mongodb-router
```

Check ports inside container:
```bash
docker exec -it mongodb-n1 bash -lc 'ss -lntp | grep mongod'
```

Test connectivity between containers:
```bash
docker exec -it mongodb-n1 bash -lc 'nc -zv 192.168.100.1 27019'
```

Check user types:
```bash
docker exec -it mongodb-n1 mongosh --quiet --eval 'db.runCommand({ connectionStatus: 1 })'
```

```bash
docker exec -it mongodb-n2 mongosh --quiet --eval 'db.runCommand({ connectionStatus: 1 })'
```

Check how mongod was run:
```bash
docker exec -it mongodb-n2 bash -lc 'cat /proc/1/cmdline | tr "\0" " "'
```

## 14) Summary

**Success Criteria**
- All containers active and ports reachable.
- `rs.status()` shows healthy replica sets for config and shards.
- `sh.status()` lists all shards connected to mongos.
- Balancer runs as expected.
- Reads and writes through mongos succeed.
- Cluster metadata consistent (config DB).

If all these checks pass, your sharded cluster is correctly configured and operational.

## NOTAS