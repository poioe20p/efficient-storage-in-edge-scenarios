# Plan: `add_network_node.sh` — Add a Node to an Existing LAN

## Goal

Create a single script (`source/scripts/network/add_network_node.sh`) that attaches
an **already-running** Docker container to either **LAN 1** (`ovs-br0`,
`10.0.0.0/24`) or **LAN 2** (`ovs-br1`, `10.0.1.0/24`) at runtime — without
rebuilding the full topology.

The script only handles Layer 2/3 wiring (veth pair, OVS port, IP/MAC config).
It does **not** start containers, initialise MongoDB replica sets, or modify
application-level configuration.

---

## 1. Proposed CLI Interface

```bash
./add_network_node.sh \
  --lan <1|2>                   # required – target LAN
  --name <container_name>       # required – already-running Docker container
  [--ip <x.x.x.x>]             # optional – auto-assigned if omitted
  [--mac <XX:XX:XX:XX:XX:XX>]   # optional – auto-generated if omitted
  [--iface <name>]              # optional – interface name inside container (default: eth0)
```

### Auto-assignment behaviour

| Parameter | When omitted |
| --- | --- |
| `--ip` | Script scans the LAN subnet via `nsenter` + `ip -o addr` on every running container PID and picks **the lowest free host address** starting from `.2` (`.1` is the gateway). Prints the chosen IP at the end. |
| `--mac` | Generated deterministically from the IP: `00:00:00:00:XX:YY` where `XX:YY` is derived from the LAN index and host octet. |

> **Answer to "can I do one at a time?"** — Yes. Every step is purely kernel-level
> (`ip link`, `nsenter`, `ovs-vsctl`), serial by nature, and idempotent. You
> can run the script repeatedly to add one node at a time.

---

## 2. Per-LAN Constants (derived from existing scripts)

| Property | LAN 1 | LAN 2 |
| --- | --- | --- |
| OVS bridge | `ovs-br0` | `ovs-br1` |
| Subnet | `10.0.0.0/24` | `10.0.1.0/24` |
| Gateway IP | `10.0.0.1` | `10.0.1.1` |
| Router interface | `eth1` | `eth2` |
| Router LAN iptables iface | `eth1` | `eth2` |
| Router WAN iface | `eth0` | `eth0` |
| Veth index range | `10–19` (new nodes) | `30–49` (new nodes) |
| Reserved IPs | `.1` (gw), `.100` (VIP_Web), `.200` (VIP_Data) | same |
| IP auto-assign range | `.2–.29` (service nodes only; test clients use `.30+`) | same |

> Existing scripts now use `veth1-3` for LAN 1, `veth21-23` for LAN 2,
> and router-related links such as `veth4` / `veth6`.
> New dynamic nodes use non-overlapping ranges: `10-19` for LAN 1 and
> `30-49` for LAN 2.

---

## 3. Step-by-step Operations

Each step maps 1-to-1 to what `build_network_{1,2}.sh` already do for static
nodes. The script performs them **sequentially** (kernel netns ops are inherently
serial).

### Step 1 — Allocate resources

1. Resolve `OVS_BRIDGE`, `SUBNET`, and `GATEWAY` from `--lan`.
2. If `--ip` is omitted → scan existing addresses in the subnet and pick next
   free (see § 5 below).
3. If `--mac` is omitted → derive from IP.
4. Pick next free veth index in the LAN's range by checking
   `ip link show vethN 2>/dev/null`.
5. If stale interfaces with that index already exist, remove them before creating the new pair.

### Step 2 — Create veth pair

```bash
sudo ip link add veth${IDX} type veth peer name veth${IDX}-peer
```

### Step 3 — Move OVS-side end into OVS namespace & attach to bridge

```bash
PID_OVS=$(docker inspect -f '{{.State.Pid}}' ovs)
sudo ln -sf /proc/$PID_OVS/ns/net /var/run/netns/ovs   # idempotent
sudo ip link set veth${IDX} netns ovs
docker exec ovs ip link set veth${IDX} up
docker exec ovs ovs-vsctl add-port ${OVS_BRIDGE} veth${IDX}
```

### Step 4 — Move peer end into the running container namespace

```bash
PID=$(docker inspect -f '{{.State.Pid}}' ${CONTAINER_NAME})
sudo ip link set veth${IDX}-peer netns $PID
```

### Step 5 — Configure interface inside the container

```bash
sudo nsenter -t $PID -n ip link set veth${IDX}-peer name eth0
sudo nsenter -t $PID -n ip link set eth0 address ${MAC}
sudo nsenter -t $PID -n ip link set eth0 up
sudo nsenter -t $PID -n ip addr add ${IP}/24 dev eth0
sudo nsenter -t $PID -n ip route add default via ${GATEWAY}
```

### Step 6 — Print summary

```text
Node added successfully
  Container      : my_new_node
  LAN            : 1 (ovs-br0)
  IP             : 10.0.0.7/24
  MAC            : 00:00:00:00:01:07
  Gateway        : 10.0.0.1
  Switch port    : veth10          (inside OVS / ovs-br0)
  Container link : veth10-peer  ->  eth0 (inside my_new_node)
```

---

## 4. What Else to Consider

### 4.1. IP Auto-Assignment Strategy

Scan the subnet for used addresses. Two practical approaches:

| Approach | Pros | Cons |
| --- | --- | --- |
| **A — Query running containers** (`docker ps` + `nsenter ip addr`) | Precise, no network traffic | Requires iterating every running container |
| **B — Ping sweep** (`for i in $(seq 2 254); do ping -c1 -W0.1 10.0.X.$i; done`) | Simple | Slow, may miss powered-off containers |

**Recommended: Approach A** — iterate running containers, resolve each container
PID, read its IP via `nsenter -t PID -n ip -4 -o addr show`, and collect
taken addresses. **Also scan `ip netns list`** and read addresses from each
named namespace via `sudo ip -n "$ns" -4 -o addr show` — this covers
namespace-based test clients created by `create_test_clients.sh` which are
invisible to `docker ps`. Add `.1` (gateway), `.100` (VIP_Web), and `.200`
(VIP_Data) to the reserved set.

Implementation pattern (matches `create_test_clients.sh`):
```bash
# Docker containers
for cid in $(docker ps -q); do
    pid=$(docker inspect -f '{{.State.Pid}}' "$cid") || continue
    sudo nsenter -t "$pid" -n ip -4 -o addr show | grep -oE "${subnet//./\.}\.[0-9]+"
done

# Named namespaces (test clients invisible to docker ps)
while read -r ns _rest; do
    sudo ip -n "$ns" -4 -o addr show | grep -oE "${subnet//./\.}\.[0-9]+"
done < <(ip netns list 2>/dev/null || true)
```

Applies to both `add_network_node.sh` and `add_network_storage_node.sh`
(each has its own copy of `collect_used_ips`).

### 4.2. MAC Address Collisions

Current static MACs: `00:00:00:00:00:02` through `00:00:00:00:00:06`,
plus `…:AA`, `…:BB`, `…:CC`, `…:DD` for the router.

Auto-generated MACs should derive deterministically from the LAN index and
IP host octet (`00:00:00:00:0L:HH`) to guarantee uniqueness within the lab.

### 4.3. Veth Index Exhaustion

With the current ranges (`10–19` for LAN 1, `30–49` for LAN 2), the script can
add 10 dynamic nodes to LAN 1 and 20 dynamic nodes to LAN 2. If more are
needed, extend the ranges or switch to name-based veth naming.

### 4.4. Idempotency / Re-run Safety

Before each step, check whether the resource already exists:

- the target container exists and is already running.
- `ip link show veth${IDX}` → skip veth creation if exists.
- `docker exec ovs ovs-vsctl port-to-br veth${IDX}` → skip OVS attach if
  already on bridge.

### 4.5. Cleanup / Node Removal

A separate cleanup script is preferable to keep `add_network_node.sh` focused.
That script should:

1. Detach the container-side interface and remove the veth pair.
2. Delete the veth pair (`sudo ip link del veth${IDX}` removes both ends).
3. Remove the OVS port (`docker exec ovs ovs-vsctl del-port`).
4. Restore any container networking state if needed.

### 4.6. MongoDB-Specific Nodes

For MongoDB shard members, start the container separately first, then attach it:

```bash
./add_network_node.sh --lan 1 --name mongodb_n3 --ip 10.0.0.6
```

After the node is attached, the caller (or [source/scripts/build_setup.sh](source/scripts/build_setup.sh)) must still:

- `rs.add("IP:27018")` to join the replica set.
- Optionally update replica-set, sharding, or zone/chunk configuration.

The `add_network_node.sh` script should NOT handle MongoDB initialization — it is a
pure networking tool.

### 4.7. OVS Controller Awareness

The new port is automatically visible to the SDN controller because OVS sends a
`PORT_STATUS` message on port additions. The learning switch in
`osken_learn_and_log.py` handles unknown ports via the table-miss flow, so no
controller-side changes are required for basic L2 connectivity.

### 4.8. DNS / Hostname Resolution

Containers created with `--network none` have no Docker DNS. If inter-container
name resolution is needed, the caller should mount a custom `/etc/hosts` or use
IPs directly (the current setup already uses IPs everywhere).

### 4.9. Validation Checks

The script should validate **before** making changes:

- `ovs` container is running.
- Target OVS bridge exists.
- Target container exists and is running.
- IP is not already in use on the subnet.

## 5. File Structure

```text
source/scripts/network/
├── add_network_node.sh        ← attach individual running containers to a LAN
├── build_network_1.sh      ← existing: provisions full LAN 1 topology
└── build_network_2.sh      ← existing: provisions full LAN 2 topology
```

`add_network_node.sh` is complementary to — not a replacement for — the existing
static build scripts. The static scripts create the initial topology (bridges,
router, base containers); `add_network_node.sh` attaches extra running containers on top of
that already-deployed topology.

---

## 6. Example Usage Session

```bash
# Add a plain host to LAN 1 (IP auto-assigned)
./add_network_node.sh --lan 1 --name edge_server
# Output includes IP, switch port name, and container link name

# Attach a MongoDB member already running in LAN 2 with a manual IP
./add_network_node.sh --lan 2 --name mongodb_n2_member2 --ip 10.0.1.5
```
