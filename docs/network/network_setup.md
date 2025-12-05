## Router ↔ Shard Connectivity Checklist

This note explains, step by step, how the automation scripts wire each shard network to the NAT router and expose the MongoDB instances to the rest of the lab. Every item below references the commands inside `build_network_1.sh`, `build_network_2.sh`, and the final orchestration in `build_setup.sh`.

### 1. Create the switch fabric inside the OVS container
1. `docker exec ovs ovs-vsctl add-br ovs-br0` / `ovs-br1` – add one bridge per shard network.
2. `sudo ip link add vethX type veth peer name vethX-peer` – create host-side veth pairs that will become the switch ports and container NICs.
3. `sudo ip link set vethX netns ovs` followed by `docker exec ovs ovs-vsctl add-port …` – move the switch-facing ends into the OVS container namespace and attach them to the correct bridge so packets can reach the router and MongoDB containers.

### 2. Launch the workload and MongoDB containers detached from Docker networking
1. `docker run -dit --network none ubuntu-host` (containers 1–4) and `docker run … ubuntu-mongodb mongod --shardsvr …` – start each host/shard container with no default interfaces so we have full control over their NICs.
2. `docker inspect -f '{{.State.Pid}}' <name>` – capture each container PID; we need it for namespace operations.

### 3. Drop the peer NICs into the correct namespaces with `nsenter`
1. `sudo ip link set vethX-peer netns $PIDY` – move the host-side peers into the target container namespace.
2. Inside the container namespace (`sudo nsenter -t $PIDY -n …`):
	- Rename: `ip link set vethX-peer name eth0` so Linux treats it as the primary NIC.
	- Fix MACs: `ip link set eth0 address 00:…` to keep deterministic datapath IDs for OS-Ken.
	- Bring up: `ip link set eth0 up` and assign addresses (`ip addr add 10.0.0.2/24 dev eth0`, etc.).
	- Configure default routes (`ip route add default via 10.0.0.1` or `10.0.1.1`) so each container sends traffic through the NAT router.

### 4. Configure the NAT router LAN sides
1. `sudo nsenter -t $PID_ROUTER -n ip link set veth3-peer name eth1` (network 1) and `veth12-peer name eth2` (network 2) – rename each LAN interface inside the router.
2. `ip addr add 10.0.0.1/24 dev eth1` and `ip addr add 10.0.1.1/24 dev eth2` – give the router gateway IPs for both networks/lans.
3. `echo 1 > /proc/sys/net/ipv4/ip_forward` – enable forwarding so the router passes packets between LANs and WAN.

### 5. Wire the router WAN side and host attachment
1. `sudo nsenter -t $PID_ROUTER -n ip link set veth4-peer name eth0` and `ip addr add 192.168.100.2/24 dev eth0` – give the router a WAN interface on the management subnet.
2. On the host: `sudo ip addr add 192.168.100.1/24 dev veth4` plus `sudo ip route replace 10.0.0.0/24 via 192.168.100.2 dev veth4` (and similarly for `10.0.1.0/24`) – let the host reach the lab subnets via the router.

### 6. Expose shard ports to the router using iptables DNAT/SNAT
1. `iptables -t nat -A PREROUTING -d 192.168.100.2 --dport 27018 -j DNAT --to 10.0.0.4:27018` – forward connections hitting the router WAN IP on 27018 to the LAN1 Mongo primary.
2. `iptables -t nat -A PREROUTING -d 192.168.100.2 --dport 27118 -j DNAT --to 10.0.1.4:27018` – same idea for the second shard (different external port).
3. Matching `POSTROUTING -j SNAT --to-source 192.168.100.2:27018/27118` rules ensure replies appear to come from the router WAN IP, keeping TCP flows symmetric.
4. `iptables -A FORWARD -i eth0 -o eth1 -j ACCEPT` (and the reverse) – allow the DNAT'd packets to traverse the router between WAN and LAN interfaces.

**What DNAT/SNAT mean:**
- **DNAT (Destination NAT)** rewrites the *destination* address/port of inbound packets so traffic aimed at the router (192.168.100.2:27xxx) is delivered to the internal shard hosts (10.0.x.4:27018). The router keeps a mapping so return traffic is sent back to the original client.
- **SNAT (Source NAT)** rewrites the *source* address/port of outbound packets so the internal shard replies appear to originate from the router's WAN IP. Without SNAT, responses would come from 10.0.x.4, which external clients cannot route back to directly.

### 7. Provide Internet access to the lab
1. `sudo ip link set veth6 up` plus `ip addr replace 172.20.0.1/30 dev veth6` on the host and `nsenter -t $PID_ROUTER -n ip addr replace 172.20.0.2/30 dev eth3` – create a dedicated point-to-point uplink (eth3) between the host and router.
2. `nsenter -t $PID_ROUTER -n ip route replace default via 172.20.0.1 dev eth3` – make the router send outbound traffic through that uplink.
3. Host-side NAT: `sudo iptables -t nat -A POSTROUTING -s 192.168.100.0/24 -o <uplink> -j MASQUERADE` – translate router WAN traffic so it can reach the real Internet via the host.
4. Router-side NAT: `iptables -t nat -A POSTROUTING -s 10.0.0.0/24 ! -d 192.168.100.0/24 -o eth0 -j MASQUERADE` (and equivalent for LAN2/eth2 and eth3) – translate packets leaving each shard subnet toward the WAN or dedicated uplink so responses return properly.

### 8. High-level orchestration (`build_setup.sh`)
1. The script runs `build_network_1.sh` and `build_network_2.sh` in sequence, so both shard environments are wired before Mongo router (`mongos`) and the OS-Ken controller start.
2. After both networks exist, it launches the config server, shard members, router, and finally `mongos`, which expects to reach shards at `192.168.100.2:27018` and `:27118`—the very ports mapped via the DNAT/SNAT rules above.
3. With routing tables, NAT, and veth plumbing in place, the controller container (running on the host network) can also talk directly to the shards, while regular lab hosts reach the Internet through the router→host uplink path configured in steps 5–7.

These ordered operations ensure every shard has a deterministic MAC/IP, the router knows how to reach each LAN, outside services can hit the shards through DNAT, and lab traffic exits to the wider Internet through layered MASQUERADE rules.
