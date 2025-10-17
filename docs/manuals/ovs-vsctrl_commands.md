# Open vSwitch (ovs-vsctl) quick reference

Commands tailored for the lab topology where `ovs-br0` is managed by a Ryu controller listening on TCP port 6633.

## Controller management

```bash
# Point ovs-br0 at the Ryu controller container (replace host if needed)
ovs-vsctl set-controller ovs-br0 tcp:127.0.0.1:6633

# Verify controller connection state and bridge details
ovs-vsctl show

# Allow switch to keep forwarding with last flows if controller is unreachable
ovs-vsctl set-fail-mode ovs-br0 secure

# Remove controller assignment (back to standalone operation)
ovs-vsctl del-controller ovs-br0
```

## Bridge and port inspection

```bash
# List bridges managed by OVS
ovs-vsctl list-br

# List ports attached to ovs-br0
ovs-vsctl list-ports ovs-br0

# Show interface details (link state, MAC) for veth5
ovs-vsctl list interface veth5

# Enable/disable a port (e.g., isolate mongodb temporarily)
ovs-vsctl set interface veth5 admin_state=down
ovs-vsctl set interface veth5 admin_state=up
```

## Flow troubleshooting (Ryu-programmed)

```bash
# Dump current OpenFlow entries that Ryu installed
ovs-ofctl dump-flows ovs-br0

# Dump flows with stats and table separation
ovs-ofctl dump-flows ovs-br0 -O OpenFlow13 --stats

# View table statistics (helps confirm packets match expected rules)
ovs-ofctl dump-table-features ovs-br0

# Clear all flows (forces Ryu to repopulate tables)
ovs-ofctl del-flows ovs-br0

# Clear flows in a specific table (e.g., table 1)
ovs-ofctl --strict del-flows ovs-br0 "table=1"

# Insert a temporary static flow (bypass Ryu) to drop traffic from 10.0.0.4
ovs-ofctl add-flow ovs-br0 "priority=100,ip,nw_src=10.0.0.4,actions=drop"

# Insert a flow to forward traffic from container1 to Mongo via veth5
ovs-ofctl add-flow ovs-br0 "priority=90,ip,nw_src=10.0.0.2,nw_dst=10.0.0.4,actions=output:port-of-veth5"

# Remove the specific flow
ovs-ofctl --strict del-flows ovs-br0 "priority=100,ip,nw_src=10.0.0.4"

# Capture live packet-in events (requires tcpdump/wireshark on controller interface)
# Useful when diagnosing why Ryu reacts to packets
```

> **Note:** When adding manual flows, replace `port-of-veth5` with the numeric port ID from `ovs-ofctl show ovs-br0`.

> **Tip:** The `ovs-ofctl` commands complement `ovs-vsctl` by showing the OpenFlow state. Run them from the host while the controller is active.

## Adding/removing ports dynamically

```bash
# Attach a new device (example: tap123) to ovs-br0
ovs-vsctl add-port ovs-br0 tap123

# Detach the port when finished
ovs-vsctl del-port ovs-br0 tap123
```

## Reset to clean state

```bash
# Remove controller assignment and return bridge to standalone mode
ovs-vsctl del-controller ovs-br0

# Clear custom fail-mode
ovs-vsctl set-fail-mode ovs-br0 standalone

# Delete and recreate the bridge (use with caution)
ovs-vsctl del-br ovs-br0
ovs-vsctl add-br ovs-br0
```

Keep these commands handy while experimenting with Ryu flow logic and the container-based network lab.
