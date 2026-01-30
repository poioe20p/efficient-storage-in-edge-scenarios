# VIP OpenFlow Explanation

This document explains how the VIP (Anycast service IP) works in the SDN lab and what OpenFlow rules are involved.

## What the VIP is

The VIP is a **virtual IP address** (e.g., 10.0.0.100 or 10.0.1.100) that clients use as a single entry point. The real servers keep their **real IPs** (e.g., 10.0.0.4 and 10.0.1.4). The switch and controller rewrite packets so clients talk to the VIP, while traffic actually reaches a chosen backend.

## What OpenFlow does (three pieces)

### 1) VIP ARP reply flow (installed by scripts)
Clients need a MAC for the VIP. The switch replies to ARP requests **as if** it owns the VIP.

- **Match:** ARP request for VIP (arp_tpa=VIP)
- **Action:** build an ARP reply with VIP MAC

This makes the client learn:
```
VIP IP -> VIP MAC
```

### 2) VIP punt flow (priority 100, installed by controller)
The first VIP packet is sent to the controller so it can pick a backend.

- **Match:** IPv4 dst = VIP, ICMP echo (or later TCP/UDP)
- **Action:** send to controller

### 3) DNAT/SNAT flows (priority 200, installed by controller)
After choosing a backend, the controller installs two flows on the edge switch:

**DNAT (client → backend):**
- Change destination **IP** from VIP → real server IP
- Change destination **MAC** from VIP MAC → server MAC
- Forward toward the backend

**SNAT (backend → client):**
- Change source **IP** from real server IP → VIP IP
- Change source **MAC** from server MAC → VIP MAC
- Forward back to the client

## Why there is no conflict between flows
- The **DNAT/SNAT flows have higher priority (200)** than the punt flow (100).
- Once DNAT/SNAT rules exist, traffic is forwarded in the switch without controller involvement.
- The punt flow only handles the **first packet** before the rewrite rules exist.

## Summary (one sentence)
The switch pretends to own the VIP (ARP), the controller chooses a backend on first contact (punt), and then the switch rewrites packets so the client always sees the VIP while the real server receives the traffic (DNAT/SNAT).
