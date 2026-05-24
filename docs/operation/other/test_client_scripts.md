# Test Client Scripts — Namespace-based HTTP Clients

## Goal

This document describes the implemented scripts under
`source/scripts/network/clients/` that manage
**lightweight Linux network namespace clients** for testing VIP routing. These
clients have no container image — they are pure namespace + veth pairs, each
with a unique MAC and IP, connected to an OVS bridge exactly like any other
node on the LAN.

| Script | Purpose |
| --- | --- |
| `create_test_clients.sh` | Create N namespace-based clients on a given LAN |
| `remove_test_clients.sh` | Remove test clients (all or a specific one) |

Each script has **one job**. Traffic generation (HTTP requests, curl, etc.) is a
separate concern handled elsewhere.

---

## 1. Why Namespaces Instead of Containers

The SDN controller identifies clients by **MAC + IP in OpenFlow match rules** —
it never inspects whether the source is a Docker container or a bare kernel
namespace. A `ip netns` namespace with a veth pair is sufficient, lighter, and
faster to create.

Comparison:

| | Docker container | `ip netns` namespace |
| --- | --- | --- |
| Image required? | Yes | No |
| Startup time | ~0.5-2 s | <50 ms |
| Overhead | `containerd`, cgroups, overlayfs | None (just a netns file) |
| Usable for curl/HTTP | Yes | Yes (via `ip netns exec`) |
| OVS wiring | Same veth + `nsenter` method | Same veth + `ip link set netns` |

---

## 2. Proposed CLI Interface

### `create_test_clients.sh`

```bash
./create_test_clients.sh \
  --lan <1|2>        # required — target OVS bridge / subnet
  --count <N>        # required — number of clients to create
  [--prefix <name>]  # optional — namespace name prefix (default: test_client)
```

**Example:**
```bash
# Create 4 clients on LAN 1
./create_test_clients.sh --lan 1 --count 4

# Create 2 clients on LAN 2 with a custom prefix
./create_test_clients.sh --lan 2 --count 2 --prefix bench_client
```

Each client is named `<prefix>_<N>` (e.g., `test_client_1`, `test_client_2`).

**Output per client (machine-readable):**
```
RESULT_NS=test_client_1 RESULT_IP=10.0.0.7 RESULT_MAC=00:00:00:00:01:07
RESULT_NS=test_client_2 RESULT_IP=10.0.0.8 RESULT_MAC=00:00:00:00:01:08
```

### `remove_test_clients.sh`

```bash
./remove_test_clients.sh \
  --lan <1|2>              # required — which LAN to clean up
  [--prefix <name>]        # optional — only remove namespaces with this prefix (default: test_client)
  [--name <ns_name>]       # optional — remove a single named namespace
```

**Examples:**
```bash
# Remove all test_client_* namespaces on LAN 1
./remove_test_clients.sh --lan 1

# Remove all bench_client_* namespaces on LAN 2
./remove_test_clients.sh --lan 2 --prefix bench_client

# Remove a single namespace by name
./remove_test_clients.sh --lan 1 --name test_client_3
```

---

## 3. Per-LAN Constants (inherited from existing scripts)

| Property | LAN 1 | LAN 2 |
| --- | --- | --- |
| OVS bridge | `ovs-br0` | `ovs-br1` |
| Subnet | `10.0.0.0/24` | `10.0.1.0/24` |
| Gateway | `10.0.0.1` | `10.0.1.1` |
| Veth range (static core nodes) | `1–9` | `21–29` |
| Veth range (dynamic service nodes, `add_network_node.sh`) | `10–19` | `30–49` |
| **Veth range (test clients)** | `50–69` | `70–89` |
| Reserved IPs (never auto-assigned) | `.1` (gw), `.2–.29` (service node range), `.100` (VIP_Web), `.200` (VIP_Data) | same |
| **IP auto-assign start for test clients** | `.30` | `.30` |

> **IP Address Partition:**
> The `/24` subnet is split by convention:
>
> | Range | Owner |
> | --- | --- |
> | `.1` | Gateway |
> | `.2–.29` | Static + dynamic **service nodes** (`add_network_node.sh`) |
> | `.30–.99` | **Test clients** (`create_test_clients.sh`) |
> | `.100` | VIP_Web |
> | `.101–.199` | **Test clients** (continued) |
> | `.200` | VIP_Data |
> | `.201–.254` | **Test clients** (continued) |

> **Why separate ranges matter:**
> `node_manager.py` (Thread 3 in the SDN controller) spawns new edge server and
> storage nodes by calling `add_network_node.sh` / `add_network_storage_node.sh`.
> Those scripts run `find_free_veth_index()`, which scans its designated range
> (`10–19` for LAN 1, `30–49` for LAN 2) for the first unused index.
>
> If test clients occupied those same ranges, the controller's scan would find
> them all taken and **die with an error** the moment it tries to add a legitimate
> service node. Placing test clients in their own non-overlapping ranges (`50–69`
> / `70–89`) ensures the controller's allocation logic is never disrupted, even
> when 10+ test clients are active simultaneously.

---

## 4. `create_test_clients.sh` — Step-by-Step

For each client index `i` from 1 to `--count`:

### Step 1 — Allocate IP & MAC

1. Scan IP addresses in use: for each item in `ip netns list` **plus** each
   running container PID, read addresses via `ip -o addr show` inside the
   namespace / via `nsenter`. Collect taken host octets.
2. Pick the next free host octet (starting from `.30`) that is not reserved.
   Host octets `.2–.29` are reserved for dynamic service nodes added via
   `add_network_node.sh` / `add_network_storage_node.sh`; never use them for
   test clients even if they appear free.
3. Derive MAC deterministically:
   ```bash
   printf '00:00:00:00:%02x:%02x' "$LAN" "$host_octet"
   # LAN 1, IP ending .11 → 00:00:00:00:01:0b
   ```

### Step 2 — Find free veth index

```bash
for idx in $(seq "${VETH_RANGE_START[$LAN]}" "${VETH_RANGE_END[$LAN]}"); do
    if ! ip link show "veth${idx}" >/dev/null 2>&1 \
        && ! sudo nsenter -t "$PID_OVS" -n ip link show "veth${idx}" >/dev/null 2>&1; then
        echo "$idx"; return 0
    fi
done
```

### Step 3 — Create the network namespace

```bash
sudo ip netns add "${NS_NAME}"
```

### Step 4 — Create veth pair

```bash
sudo ip link add "veth${IDX}" type veth peer name "veth${IDX}-peer"
```

### Step 5 — Move OVS-side end into OVS namespace & attach to bridge

```bash
PID_OVS=$(docker inspect -f '{{.State.Pid}}' ovs)
sudo ip link set "veth${IDX}" netns "$PID_OVS"
docker exec ovs ip link set "veth${IDX}" up
docker exec ovs ovs-vsctl add-port "${OVS_BRIDGE}" "veth${IDX}"
```

### Step 6 — Move peer into the namespace & configure

```bash
sudo ip link set "veth${IDX}-peer" netns "${NS_NAME}"
sudo ip netns exec "${NS_NAME}" ip link set "veth${IDX}-peer" name eth0
sudo ip netns exec "${NS_NAME}" ip link set eth0 address "${MAC}"
sudo ip netns exec "${NS_NAME}" ip link set eth0 up
sudo ip netns exec "${NS_NAME}" ip addr add "${IP}/24" dev eth0
sudo ip netns exec "${NS_NAME}" ip route add default via "${GATEWAY}"
```

### Step 7 — Print machine-readable result

```bash
echo "RESULT_NS=${NS_NAME} RESULT_IP=${IP} RESULT_MAC=${MAC}"
```

---

## 5. `remove_test_clients.sh` — Step-by-Step

For each namespace matching the removal criteria:

### Step 1 — Identify the veth used by the namespace

The namespace name alone is enough to derive its veth because stale veths are
detectable from the OVS bridge ports list:

```bash
# List all ports on the bridge
docker exec ovs ovs-vsctl list-ports "${OVS_BRIDGE}"

# For each veth port, check if its peer is in the target namespace
ip -n "${NS_NAME}" link show eth0 2>/dev/null
```

Alternatively, record the veth index in a state label on the namespace itself
(using a naming convention like `veth<IDX>` as the interface inside the namespace
before rename — but renaming to `eth0` overwrites this). The simpler approach:
**scan all veth ports on the bridge** and probe each peer namespace.

### Step 2 — Detach veth from OVS bridge & delete pair

```bash
docker exec ovs ovs-vsctl del-port "${OVS_BRIDGE}" "veth${IDX}"
# Deleting one end of the pair removes both
sudo nsenter -t "$PID_OVS" -n ip link del "veth${IDX}" 2>/dev/null || true
```

### Step 3 — Flush stale OVS flow rules for this client

```bash
docker exec ovs ovs-ofctl del-flows "${OVS_BRIDGE}" "dl_src=${MAC}"
docker exec ovs ovs-ofctl del-flows "${OVS_BRIDGE}" "dl_dst=${MAC}"
```

### Step 4 — Delete the namespace

```bash
sudo ip netns del "${NS_NAME}"
```

---

## 6. Veth → Namespace Association

The tricky part in removal is mapping an OVS bridge port back to a namespace.
Two approaches:

| Approach | Method | Pros | Cons |
| --- | --- | --- | --- |
| **A — Probe by namespace** | For each `ip netns list` entry matching prefix, check if `ip -n $NS link show eth0` exists and find the peer veth index via `ip -n $NS link show eth0 \| grep -o 'veth[0-9]*'` | Self-contained | Requires iterating all namespaces |
| **B — State file** | `create_test_clients.sh` writes to `/tmp/test_clients_state` a line per client: `NS_NAME VETH_IDX IP MAC` | O(1) lookup | State file can go stale if cleanup crashes |

**Recommended: Approach A** — querying live namespaces is reliable and avoids
stale-state problems. The namespace list is small in test scenarios.

---

## 7. Using the Clients (after creation)

To send an HTTP request from a namespace-based client:

```bash
# Single request
ip netns exec test_client_1 curl http://10.0.0.100:80/api/doc/123

# In a loop from all clients
for ns in $(ip netns list | awk '{print $1}'); do
    ip netns exec "$ns" curl -s http://10.0.0.100:80/api/doc/123 &
done
wait
```

> Traffic generation (load patterns, concurrency, intervals) belongs in a
> separate script — not in these two scripts.

---

## 8. What These Scripts Do NOT Do

- Start or stop containers.
- Send HTTP traffic or generate load.
- Modify MongoDB replica sets.
- Interact with the SDN controller directly.

---

## 9. Open Questions

1. **Veth range bounds** — `50–69` and `70–89` give 20 and 20 slots. If more
   than 20 test clients per LAN are needed, extend the ranges or switch to a
   name-based scheme (e.g., `veth-tc-<name>`).
2. **ARP seeding** — The first packet from each client will trigger an ARP
   request for the VIP. The proactive ARP responder in the controller handles
   this automatically. No pre-seeding needed.
3. **Loopback in namespace** — `ip netns exec` brings up `lo` automatically
   in modern kernels. Confirm on the target kernel version if needed.
