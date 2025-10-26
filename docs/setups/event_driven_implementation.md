# Minimal End-to-End Scenario

This lab proves the core loop: OS-Ken senses events, installs flows, logs to MongoDB, and keeps running through a MongoDB failover.

## Objective

Build a 1-switch, 2-host lab where:

- OS-Ken acts as an L2 learning switch.
- All packet-in events and flow installs are logged to MongoDB.
- A basic "hot flow" is detected and prioritized.
- MongoDB runs as a replica set (3 containers) so your controller keeps working through a primary failover.

## Demonstration Checklist

1. Basic traffic flows between two hosts via OVS controlled by OS-Ken.
2. OS-Ken writes events and flows to MongoDB and reads them back for decisions.
3. A simple popularity trigger increases priority of a hot flow.
4. Killing the MongoDB primary does not break the controller (PyMongo re-routes).

## Topology

- OVS bridge: `ovs-br0`.
- Hosts:
  - h1: `10.0.0.2/24`.
  - h2: `10.0.0.3/24`.
- MongoDB replica set `rs0`: containers `mongo1`, `mongo2`, `mongo3`.
- OS-Ken controller on the host (or a container with host networking).

## Controller Behavior

- Learning switch installs flows on `packet_in` and logs events plus new flows.
- Periodic aggregation every 5 seconds:
  - Counts packet_in events per source/destination in the last 30 seconds.
  - Treats counts above 100 as hot (tune threshold as needed).
  - Installs priority-200 rules to fast-path hot flows.
  - Records an `actions` document for each change.

## MongoDB Usage

- Replica set `rs0` with three members.
- Collections:
  - `events`: packet_in logs.
  - `flows`: installed flows.
  - `actions`: prioritization records.
- Suggested indexes:
  - `events`: `(dpid, ts)` and `(type, ts)`.
  - `flows`: `(dpid, installed_at)`.
  - `actions`: `(ts)`.

## Test Plan

1. Bring up infrastructure (OVS, hosts, OS-Ken, MongoDB replica set).
2. Initiate the replica set with `rs.initiate` (via Python or `mongosh`).
3. Ping between h1 and h2; confirm flow installs and MongoDB event logs.
4. Generate burst traffic (iperf or ping flood) to create a hot flow.
5. Verify the controller installs a priority-200 rule for the hot flow and logs an action.
6. Stop the MongoDB primary with `docker stop mongo1` while traffic continues.
7. Confirm logging resumes after election and flows remain active.

## Minimal Code Additions (Skeleton)

Periodic aggregator inside the OS-Ken app:

```python
def start(self):
    super().start()
    eventlet.spawn_after(5, self._aggregator_loop)

def _aggregator_loop(self):
    while True:
        try:
            cutoff = datetime.utcnow() - timedelta(seconds=30)
            pipeline = [
                {"$match": {"type": "packet_in", "ts": {"$gte": cutoff}}},
                {"$group": {"_id": {"dpid": "$dpid", "src": "$src", "dst": "$dst"}, "cnt": {"$sum": 1}}},
                {"$match": {"cnt": {"$gt": 100}}}
            ]
            hot = list(self.db.events.aggregate(pipeline))
            for h in hot:
                dpid = h["_id"]["dpid"]
                src = h["_id"]["src"]
                dst = h["_id"]["dst"]
                dp = self._get_datapath(dpid)
                if not dp:
                    continue
                parser = dp.ofproto_parser
                ofp = dp.ofproto
                # High-priority rule to fast-path the hot flow
                port = self.mac_to_port.get(dpid, {}).get(dst)
                if port:
                    actions = [parser.OFPActionOutput(port)]
                    match = parser.OFPMatch(eth_src=src, eth_dst=dst)
                    inst = [parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]
                    mod = parser.OFPFlowMod(datapath=dp, priority=200, match=match, instructions=inst)
                    dp.send_msg(mod)
                    self.db.actions.insert_one({
                        "type": "prioritize",
                        "dpid": dpid,
                        "src": src,
                        "dst": dst,
                        "priority": 200,
                        "ts": datetime.utcnow(),
                    })
        except Exception as exc:
            self.logger.warning("Aggregator error: %s", exc)
        eventlet.sleep(5)
```

Packet-in logging enrichment:

```python
pkt_len = getattr(msg, "total_len", len(msg.data) if msg.data else None)
self.db.events.insert_one({
  "type": "packet_in",
  "dpid": dpid,
  "src": src,
  "dst": dst,
  "in_port": in_port,
  "out_port": out_port,
  "installed_flow": out_port != ofproto.OFPP_FLOOD,
  "pkt_len": pkt_len,
  "ts": datetime.utcnow(),
})
```

Flow logging when installing rules:

```python
self.db.flows.insert_one({
  "dpid": datapath.id,
  "match": {"in_port": in_port, "eth_src": src, "eth_dst": dst},
  "actions": [{"type": "OUTPUT", "port": getattr(actions[0], "port", None)}],
  "priority": 10,
  "installed_at": datetime.utcnow(),
})
```

## How to Run

- Bring up OVS and host containers (use your existing script).

- Start the MongoDB replica set:

```bash
docker network create rs-net
for n in 1 2 3; do
  docker run -d --name mongo$n --net rs-net -p 2701$n:27017 mongo:6.0 \
    mongod --replSet rs0 --bind_ip_all
done
docker exec -it mongo1 mongosh --eval 'rs.initiate({_id:"rs0",members:[{_id:0,host:"mongo1:27017"},{_id:1,host:"mongo2:27017"},{_id:2,host:"mongo3:27017"}]})'
```

- Start the OS-Ken app (host network or container):

```bash
osken-manager /path/to/ken_learn_and_log.py
```

- Generate traffic:

```bash
docker exec -it container1 bash -lc "apt-get update && apt-get install -y iputils-ping iperf3 && ping -f -c 500 10.0.0.3"
```

- Inspect MongoDB activity:

```bash
docker exec -it mongo1 mongosh --eval 'db.getSiblingDB("netstate").events.find().sort({ts:-1}).limit(5)'
```

- Run the failover test:

```bash
docker stop mongo1
# Keep traffic running; after roughly 10 seconds a new primary should be elected
```

## Success Criteria

- h1 <-> h2 ping succeeds; flows install after initial packet_in events.
- `events` and `flows` documents appear in MongoDB.
- Burst traffic installs a priority-200 hot-flow rule and an `actions` entry.
- Stopping the primary does not break the controller; inserts resume after election.

## Why This Scenario Matters

- Forces SDN control, database logging, analytics, enforcement, and HA to work together.
- Small enough to build and debug quickly.
- Sets up future work on topology-aware routing, security analytics, and sharding.

## Optional Extras

- Provide a ready-to-run Docker Compose file for the MongoDB replica set.
- Add a helper script to generate bursts and query hot flows.
- Create a troubleshooting checklist (hostnames, auth, replica-set status, PyMongo URI).
