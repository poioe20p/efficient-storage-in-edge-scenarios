# Plan: MongoDB cross-container access

Run MongoDB inside container1 and query it from container2 over the existing OVS-based network. Start simple (no auth), then add persistence and optional auth.

## Assumptions

- container1 IP: 10.0.0.2, container2 IP: 10.0.0.3 (per `network_layout.drawio`).
- L3 connectivity is already verified (ping works between containers).
- You can exec into containers from the host.

## Minimal working setup (no auth)

1. Start MongoDB in container1

- Create data dir and run mongod:

```bash
mkdir -p /data/db
mongod --bind_ip_all --dbpath /data/db --port 27017 \
    --logpath /var/log/mongodb/mongod.log --fork
```

- Verify it is listening:

```bash
ss -ltnp | grep 27017
```

2. Insert a test document in container1

```bash
echo 'db.test.insertOne({host:"container1", ts:new Date()})' | \
    mongosh --host 127.0.0.1 --port 27017

echo 'db.test.countDocuments()' | \
    mongosh --host 127.0.0.1 --port 27017
```

3. From container2, query container1’s MongoDB

- Use container1 IP 10.0.0.2:

```bash
echo 'db.test.find().toArray()' | \
    mongosh --host 10.0.0.2 --port 27017
```

- If this fails, check firewall rules in containers/host and confirm OVS bridge ports/flows are up.

## Persistence

- Map a host volume for MongoDB data so it survives container restarts.
- Example: mount `/data/db` to a host dir.

```bash
# When starting container1 (example run flag)
-v /opt/mongo/data:/data/db
```

- Optionally add an init script in container1 to ensure the dir exists and start mongod on boot.

## Optional: enable authentication

1. In container1, create an admin user:

```bash
echo 'use admin; db.createUser({user:"admin", pwd:"strongpass", roles:["root"]})' | \
    mongosh --host 127.0.0.1 --port 27017
```

2. Restart mongod with auth:

```bash
mongod --bind_ip_all --dbpath /data/db --auth --port 27017 \
    --logpath /var/log/mongodb/mongod.log --fork
```

3. From container2, connect with credentials:

```bash
echo 'db.getSiblingDB("test").find().toArray()' | \
    mongosh --host 10.0.0.2 --port 27017 \
    -u admin -p strongpass --authenticationDatabase admin
```

## Health checks and quick debugging

- In container1:

```bash
pgrep -fa mongod
mongosh --eval 'db.adminCommand({ping:1})'
```

- In container2:

```bash
nc -vz 10.0.0.2 27017 || telnet 10.0.0.2 27017
```

- If name resolution is preferred, add `/etc/hosts` entries (e.g., `10.0.0.2 mongo1`).

## Security and isolation tips

- Keep MongoDB bound to container1 interfaces only (avoid publishing 27017 to host unless needed).
- If you publish the port for host access, restrict sources with firewall rules.
- Separation of concerns is already good: DB (container1) and client (container2).

## Stretch goals

- Add startup scripts:
- container1: start `mongod` automatically.
- container2: small client script to query `db.test` and print results.
- Add a smoke test from the host:

```bash
docker exec container2 mongosh --host 10.0.0.2 --eval 'db.adminCommand({ping:1})'
```

## Acceptance checklist

- container1 runs `mongod` and persists data across restarts.
- container2 can read documents from container1 over 10.0.0.2:27017.
- Optional: auth enabled and tested from container2.
