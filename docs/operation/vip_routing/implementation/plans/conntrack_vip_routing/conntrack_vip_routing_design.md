# Design Document — Conntrack-Based VIP_DATA Routing

**Recovery removal**: already deployed (controller-side and edge-side)
**Implementation**: see [conntrack_vip_routing_plan.md](conntrack_vip_routing_plan.md)

## 1. Motivation

The v5.x experiment campaign identified **stale OVS flow rules** as the root
cause of 55-65% failure rates in compute phases. When a storage backend is
removed from the VIP_DATA pool via `unregister_storage_backend`, the existing
DNAT+SNAT flow rule pair is NOT deleted. The stale rule continues to DNAT new
TCP connections to the dead backend for up to 120 seconds (hard timeout).

The current flow rules use static L2-L4 field matching without OVS connection
tracking. This means the rules cannot be safely deleted while connections are
in flight — the rules ARE the connection state. Deleting a rule would reroute
in-flight packets to a different backend, breaking established TCP connections.

OVS conntrack solves this by separating **connection establishment** (flow
rules) from **connection state** (conntrack table). Once a connection is
established, its NAT mapping lives in the conntrack table independently of
the flow rule that created it. The forward rule can be safely deleted —
established connections survive in conntrack, and new connections trigger a
fresh `select_storage` via the punt rule.

## 2. Design Overview

### 2a. Current Architecture (Static NAT)

```
Per-client, per-backend rule pairs:

  Rule FWD-1: client_A → VIP → DNAT to backend_X
  Rule REV-1: backend_X → client_A → SNAT to VIP

  Rule FWD-2: client_B → VIP → DNAT to backend_X
  Rule REV-2: backend_X → client_B → SNAT to VIP

Problem: Deleting any FWD rule breaks in-flight connections because the
DNAT action is baked into the rule, not tracked per-connection.
Rules stay for 30-120s after backend removal → stale routing.
```

### 2b. Conntrack Architecture

```
Per-client forward rules (one per client per domain), shared reply rules:

  Rule FWD-A (forward, client A → VIP):
    Match: eth_src=clientA_mac, eth_dst=vip_mac, ipv4_src=clientA_ip, ipv4_dst=vip_ip, tcp_dst=27018
    Action: ct(commit, nat(dst=backend_X_ip)), set_field(eth_dst=backend_X_mac), output:backend_port
    Idle: 10s | Hard: 120s | Priority: 200 | Cookie: per-domain (same cookie for all clients)

  Rule FWD-B (forward, client B → VIP):
    Match: eth_src=clientB_mac, eth_dst=vip_mac, ipv4_src=clientB_ip, ipv4_dst=vip_ip, tcp_dst=27018
    Action: ct(commit, nat(dst=backend_Y_ip)), set_field(eth_dst=backend_Y_mac), output:backend_port
    Idle: 10s | Hard: 120s | Priority: 200 | Cookie: per-domain (same cookie for all clients)

  Rule REV-A-n1 (reply, established → client A, domain n1):
    Match: ct_state=+est+trk, ct_zone=1, eth_dst=clientA_mac, ipv4_dst=clientA_ip
    Action: set_field(eth_src=vip_n1_mac), output:clientA_port
    Idle: 0 (never) | Hard: 0 (never) | Priority: 200

  Rule REV-A-n2 (reply, established → client A, domain n2):
    Match: ct_state=+est+trk, ct_zone=2, eth_dst=clientA_mac, ipv4_dst=clientA_ip
    Action: set_field(eth_src=vip_n2_mac), output:clientA_port
    Idle: 0 (never) | Hard: 0 (never) | Priority: 200

  Conntrack table (automatic, per-connection):
    conn_1: client_A:50001 → VIP:27018 → nat → backend_X:27018
    conn_2: client_A:50002 → VIP:27018 → nat → backend_X:27018
    conn_3: client_B:50003 → VIP:27018 → nat → backend_Y:27018
    ...

Deleting all FWD rules for a domain (by cookie):
  → Established connections: untouched — conntrack entries survive ✅
  → New SYNs from any client: no rule matches → punted to controller → fresh select_storage ✅
  → Reply rules stay — each handles established connections via conntrack state ✅

Per-client WSM distribution preserved:
  → Client A's first SYN → select_storage() → backend_X → Rule FWD-A-n1 installed
  → Client B's first SYN → select_storage() → backend_Y → Rule FWD-B-n1 installed
  → Each client independently load-balanced ✅
  → On client A's next selection (idle expiration): new Rule FWD-A overwrites old one
    (same match fields), client B's Rule FWD-B untouched ✅

Domain differentiation via ct_zone:
  → Forward rules use ct(commit, zone=1, ...) for n1, ct(commit, zone=2, ...) for n2
  → Reply rules match ct_zone=1 or ct_zone=2 — different matches, no collision
  → Kernel conntrack automatically places reply packets in the correct zone ✅
```

### 2c. Connection Lifecycle

```
NEW CONNECTION (client A):
  SYN → matches Rule FWD-A (eth_src=clientA_mac, ...) → ct(commit) creates conntrack entry
  → DNAT to backend_X → SYN-ACK returns
  → Reply packets match Rule REV-A (ct_state=+est+trk, eth_dst=clientA_mac)
  → ct(nat) reverses mapping → Connection in conntrack, no longer needs Rule FWD-A

NEW CONNECTION (client B, same domain):
  SYN → matches Rule FWD-B (eth_src=clientB_mac, ...) → ct(commit) creates conntrack entry
  → DNAT to backend_Y (possibly different from client A's backend)
  → Reply packets match Rule REV-B → conntrack reverses mapping
  → Each client independently load-balanced via WSM cost function

ESTABLISHED CONNECTION:
  All subsequent packets match the per-client reply rule (ct_state=+est+trk)
  → ct(nat) applies the stored NAT mapping automatically
  → The forward rule is never consulted again for this connection

AFTER ALL FWD RULES DELETED (unregister_storage_backend):
  Established connections: reply rules + conntrack still handle them ✅
  New SYN from any client: no matching forward rule → hits priority 100 punt rule
  → packet-in to controller → select_storage() → new per-client forward rule installed
  → ct(commit) creates new conntrack entry → connection proceeds ✅

AFTER SINGLE FWD RULE EXPIRES (idle timeout, normal lifecycle):
  Client A's rule expires → client A's next SYN punts → fresh select_storage()
  → New Rule FWD-A installed (overwrites via same match) → MAY pick a different backend
  Client B's rule still active → client B unaffected ✅
```

### 2d. How Conntrack Identifies Connections

Each piece of the conntrack design has a distinct role. They are not interchangeable:

| Piece                                       | Purpose                                                                                                                                                                                                                                                                                                                              |
| ------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `ct(commit, zone=1, nat(dst=10.0.0.100))` | **Creates** an entry for this packet's 5-tuple. The kernel auto-generates the entry identity from `(src_ip, src_port, dst_ip, dst_port, protocol)`. This is the *only* piece that writes state.                                                                                                                            |
| `ct_state=+est+trk`                       | **Matches** ANY packet whose 5-tuple already has an entry in the kernel conntrack table. It is a broad gate — it does not reference a specific entry ID. Every established connection in the zone satisfies it.                                                                                                               |
| The kernel's 5-tuple lookup                 | **Routes** each reply packet to the correct entry. The kernel compares the packet's `(src_ip, src_port, dst_ip, dst_port, protocol)` against every entry in the zone. When the reply direction matches, `ct(nat)` reverses the NAT automatically. This is transparent — no flow rule action is needed for the IP rewrite. |

```
Example: Three connections from edge server A to VIP_DATA_N1

  Entry #1: (10.0.0.10, 50001, 10.0.0.254, 27018, TCP) → nat: dst=10.0.0.100
  Entry #2: (10.0.0.10, 50002, 10.0.0.254, 27018, TCP) → nat: dst=10.0.0.100
  Entry #3: (10.0.0.10, 50003, 10.0.0.254, 27018, TCP) → nat: dst=10.0.0.100

#1, #2, and #3 all NAT to the same backend — the per-client forward rule
has no tcp_src in its match, so every connection from the same client IP
hits the same rule. The only difference between entries is the source port.
The kernel uses the full 5-tuple to tell them apart.

When a reply packet arrives from 10.0.0.100:27018 → 10.0.0.10:50002:
  → Kernel finds entry #2 (reply direction matches)
  → ct(nat) rewrites src to 10.0.0.254 (the VIP)
  → The reply rule's ct_state=+est+trk match gates entry into the flow
  → set_field(eth_src=VIP_N1_MAC) fixes the L2 header
```

The flow rules never know about individual entries. The kernel handles
per-connection identity entirely on its own. This is why deleting the
forward rule is safe: the entries are not stored in OVS, they're in the
kernel's conntrack table, and the reply rule (`ct_state=+est+trk`) still
matches them regardless of whether the forward rule exists.

## 3. Design Decisions & Rationale

### 3a. Per-Client Forward Rules (Not Shared)

The forward rule match includes `eth_src=client_mac` and `ipv4_src=client_ip`,
preserving the per-client WSM load distribution from the current static-NAT
design. Each client independently triggers `select_storage()` on its first
SYN, and different clients may be routed to different backends — exactly as
they are today.

Trade-offs:

- Pro: No regression in load distribution — clients are independently
  balanced across storage backends via the WSM cost function.
- Pro: Same OVS rule count as today (N clients × 2 domains × 1 forward rule = 2N rules).
- Con: Slightly more rules than a single shared rule per domain, but the
  difference is negligible (8 clients → 8 forward rules instead of 1).

The per-client match omits `tcp_src` — all TCP connections from the same
client IP route to the same backend. Multiple concurrent connections (e.g.
pymongo's connection pool) are handled correctly; they simply cannot be
distributed across different backends. This matches the traffic generator's
sequential `curl`-per-namespace model and the read-only workload design. If
per-connection backend selection were ever needed, `tcp_src` would be added
to the match.

### 3b. Per-Domain Cookies (Bulk Deletion)

All per-client forward rules for a given domain share the same cookie. This
enables bulk `OFPFC_DELETE` on `unregister_storage_backend` — one flow-mod
deletes every client's forward rule, forcing all clients to re-select on
their next SYN. Per-client cookies would require tracking which clients have
active rules, adding state complexity with no benefit.

Cookie-keyed deletion is only used in the unregister path. Normal backend
re-selection (idle timeout expiry) does not delete anything: the new rule
overwrites the old one naturally via same-priority/same-match OVS semantics.

### 3c. Idle Timeout: 10s (reduced from 30s)

The forward rule idle timeout is the safety net: if flow deletion on
unregister fails for any reason, the stale per-client rule idles out in 10s
instead of 30s. During active traffic, the idle timer resets on every new
SYN from that client, so the rule stays alive as long as traffic flows.

10s is chosen because:

- It's long enough that brief traffic pauses (e.g., phase transitions) don't
  unnecessarily expire per-client rules and trigger controller round-trips
- It's short enough that stale rules don't cause extended failure windows
- The primary mechanism is proactive deletion on unregister; 10s is the
  fallback, not the primary path

### 3d. Warm-Lease Pre-Installation (Deferred)

The current warm-lease system gives new backends a **selection-time**
preference in `select_storage` — they're more likely to be chosen by the WSM
cost function for a short window (default: server 5s, storage 30s). It does
NOT pre-install any flow rules.

A future extension could pre-install a forward rule at lower priority (190)
when a warm lease is granted. When the current backend is removed and its
rule deleted, the warm rule is promoted to priority 200 — zero packet-in
latency on switchover.

**Deferred** because the packet-in latency (<1ms) is negligible compared to
the 30-120s failure windows we're fixing.

### 3e. How Per-Client Reply Rules Distinguish Clients

The reply rule must route a response packet from the backend back to the
correct client. Three pieces of information are needed, and each comes from
a different source:

| Information | Source | Encoded in |
|-------------|--------|------------|
| Which client IP to send to? | `ipv4_dst=client_ip` in rule match | Per-client reply rule |
| Which client MAC to send to? | `eth_dst=client_mac` in rule match | Per-client reply rule |
| Which OVS port to output on? | `output:in_port` in rule action | Per-client reply rule |
| Reverse the DNAT (backend IP → VIP)? | Kernel conntrack `ct(nat)` | Automatic — no rule action needed |

The kernel conntrack handles the IP-level NAT reversal transparently: when
a reply packet arrives, conntrack looks up the 5-tuple, finds the original
forward entry, and rewrites `src=backend_ip` → `src=vip_ip`. But conntrack
does NOT store OVS port numbers or L2 MAC addresses — those must come from
the flow rule.

This is why the reply rule is per-client: the L2 rewrite (`eth_src=vip_mac`)
and output port (`output:in_port`) are client-specific and must be matched
to the correct client via `eth_dst=client_mac, ipv4_dst=client_ip`.

The `ct_state=+est+trk` match ensures the rule only processes packets that
belong to established conntrack connections. A backend talking to a random
non-VIP host would have no conntrack entry and would not match. The per-client
MAC/IP match is an additional safety filter — defense in depth.

**Client distinction in the reply direction works the same way as the current
static NAT SNAT rules:** the current `install_vip_dnat_snat` installs SNAT
rules scoped to `eth_src=backend_mac, eth_dst=client_mac, ipv4_src=backend_ip,
ipv4_dst=client_ip`. The conntrack reply rule replaces the `eth_src` and
`ipv4_src` match fields with `ct_state=+est+trk` (kernel handles the backend
identification), but keeps `eth_dst` and `ipv4_dst` for client identification.
This is a simplification of the current design, not a new concept.

### 3f. Domain Differentiation via ct_zone

The reply rule must set `eth_src` to the correct VIP MAC — and
`VIP_DATA_N1_MAC` ≠ `VIP_DATA_N2_MAC`. A single reply rule per client
can only set one `eth_src` value, and two reply rules with identical match
fields would collide (last-one-wins overwrite).

**Solution**: the forward rule tags each connection with `ct_zone=N` (1 for n1,
2 for n2). The reply rule matches `ct_zone=N` in addition to `ct_state`
and client fields. Since the match now differs by zone, both reply rules
coexist for the same client without collision. The kernel automatically
places reply packets in the zone where the original conntrack entry was
created — no extra logic needed.

Zones are also useful for monitoring: `ovs-appctl dpctl/dump-conntrack`
can be filtered per-zone to get per-domain connection counts without
parsing VIP IPs from the conntrack output.

### 3g. Multi-Client Reply Rules

The reply rule is per-client because the L2 destination (`eth_dst=client_mac`,
`output:in_port`) is client-specific — conntrack handles the IP NAT reversal
but does not store OVS port numbers or MAC addresses (see §3e). An incidental
benefit is that backends cannot hijack non-VIP traffic: a packet not belonging
to a conntrack entry won't match `ct_state=+est+trk`.

With 8 clients × 2 domains = 16 forward rules + 16 reply rules = 32 total
rules — same count as the current static NAT design (2 rules × 8 clients ×
2 domains). Negligible OVS overhead. No optimization needed now.

### 3h. Conntrack Availability — Startup Requirement

Conntrack is mandatory. The controller refuses to start if `ovs-appctl dpctl/dump-conntrack` fails. This prevents silent fallback to broken
static-NAT behavior.

### 3i. Docker Image Dependencies

**OVS image** (`source/docker/OVS/`): Uses `ubuntu:20.04` + `openvswitch-switch`.
Kernel-datapath conntrack is included out of the box — no Dockerfile or
`start.sh` changes needed. Verify with `ovs-appctl dpctl/dump-conntrack`
after container startup.

**OS-Ken image** (`source/docker/os-ken/`): Uses `os-ken==3.1.1` (Ryu fork).
Nicira extension classes (`NXActionCT`, `NXActionNAT`) are inherited from
upstream Ryu's `ryu.ofproto.nx_actions`. No additional pip packages or
Dockerfile changes required. **However**, the 3.1.1 API may differ from the
OS-Ken 4+ docs — parameter names, zone encoding, and IP address format may
vary. Verify with `help(p.NXActionCT)` at implementation time. If the 3.1.1
signatures are incompatible, the preferred path is `ovs-ofctl` raw action
strings through the existing `_install_flow` abstraction — functionally
equivalent and version-agnostic.

**Conclusion**: Both images already support conntrack as built today.
No Docker image rebuilds are required for the conntrack changes.

### 3j. Conntrack Table Capacity and Entry Lifecycle

The kernel conntrack table defaults to 65,536 entries on Ubuntu 20.04
(`/proc/sys/net/netfilter/nf_conntrack_max`). At typical load (8 edge
servers × ~10 MongoDB connections each = 80 entries), usage is 0.12% of
capacity. Even at 100 connections per server (800 entries), 1.2%. No tuning
is needed.

Entries clean themselves up naturally:

| TCP state          | Kernel default timeout | Trigger                  |
| ------------------ | ---------------------- | ------------------------ |
| ESTABLISHED (idle) | 5 days                 | Connection idle, no data |
| CLOSE_WAIT         | 60 s                   | Local close initiated    |
| TIME_WAIT          | 120 s                  | Both sides closed        |

In practice, pymongo's connection pool (`maxIdleTimeMS=30000`) closes idle
connections after 30s. The TCP FIN handshake transitions entries through
CLOSE_WAIT → TIME_WAIT → expired within ~3 minutes. Entries from active
connections persist naturally until the application closes them.

The forward rule's 10s idle timeout provides an additional bound: after 10s
of no new SYNs, the OVS rule expires, but established conntrack entries
survive independently. When those connections eventually close, their kernel
entries expire. No manual cleanup is required.
