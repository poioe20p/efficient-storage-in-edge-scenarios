#!/usr/bin/env python3
"""
rq2v2_p5_02_topology_host_grace_test.py — Phase-5 gate for the topology
host_attachment grace-window fix (P5 ba_db preflight failure, 2026-08-08).

During dynamic-node churn the OS-Ken topology snapshot can transiently omit
backends. Previously ``get_sws_links_hosts`` rebuilt ``host_attachment``
wholesale, so a single incomplete poll dropped VIP backends and DNAT/SNAT flow
installs were skipped until the next complete poll (the LAN1 edge-tier outage
in P5). The fix retains a previously-known host that is missing from a poll
for ``_host_attach_grace_ticks`` consecutive polls before removal.

Checks (grace = 3):
  1. known hosts present -> attached.
  2. backend missing for polls 1..3 (ticks <= grace) -> RETAINED with the
     previous (dpid, port_no).
  3. backend missing for poll 4 (ticks > grace) -> EVICTED.
  4. a re-appearing host is reset (present again -> back in attachment, ticks
     cleared).
  5. never-known host absent -> never attached.
  6. no regression: a host present in the poll is attached exactly as before.

Exit 0 = all checks pass; non-zero = gate failed.
"""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sdn_controller.topology import topology as topo_mod  # noqa: E402

# MACs
SERVER = "00:00:00:00:00:02"
STORAGE = "00:00:00:00:00:04"
CLIENT = "00:00:00:00:01:38"
OTHER = "00:00:00:00:02:38"


def host(mac, dpid=1, port_no=3, ip="10.0.0.1"):
    return SimpleNamespace(mac=mac, port=SimpleNamespace(dpid=dpid, port_no=port_no),
                           ipv4=[ip])


def build(grace=3):
    g = topo_mod.TopologyMixin.__new__(topo_mod.TopologyMixin)
    g._host_attach_grace_ticks = grace
    g._host_missing_ticks = {}
    g.host_attachment = {}
    g.hosts = []
    g.links = []
    g.sws = []
    g.net = __import__("networkx").DiGraph()
    g._router_mac_blocklist = {
        "00:00:00:00:00:aa", "00:00:00:00:00:bb",
        "00:00:00:00:00:cc", "00:00:00:00:00:dd",
        "00:00:00:00:00:AA", "00:00:00:00:00:BB",
        "00:00:00:00:00:CC", "00:00:00:00:00:DD",
    }
    g._get_topology_api_app = lambda: object()
    return g


def run_poll(g, macs):
    """Patch get_host/get_all_link and run one get_sws_links_hosts() pass."""
    topo_mod.get_host = lambda app, dp=None: [host(m) for m in macs]
    topo_mod.get_all_link = lambda app: []
    g.get_sws_links_hosts()


def main() -> int:
    failures = []

    # -- 1. baseline: all known hosts present -------------------------------
    g = build()
    run_poll(g, [SERVER, STORAGE, CLIENT])
    for m in (SERVER, STORAGE, CLIENT):
        if m not in g.host_attachment:
            failures.append(f"1: {m} should be attached")
    if len(g.host_attachment) != 3:
        failures.append(f"1: expected 3 hosts, got {len(g.host_attachment)}")

    # -- 2. backend missing 1..3 polls -> retained with same port ------------
    for i in range(1, 4):
        run_poll(g, [STORAGE, CLIENT])   # SERVER missing
        if g.host_attachment.get(SERVER) != (1, 3):
            failures.append(
                f"2.{i}: SERVER should be retained at (1,3), "
                f"got {g.host_attachment.get(SERVER)}")

    # -- 3. missing on poll 4 -> evicted -------------------------------------
    run_poll(g, [STORAGE, CLIENT])
    if SERVER in g.host_attachment:
        failures.append("3: SERVER should be evicted after grace window")
    if SERVER in g._host_missing_ticks:
        failures.append("3: evicted host's missing-tick counter should be cleaned")

    # -- 4. re-appearing host resets ----------------------------------------
    run_poll(g, [SERVER, STORAGE, CLIENT])   # SERVER back
    if g.host_attachment.get(SERVER) != (1, 3):
        failures.append(f"4: SERVER should be re-attached, got {g.host_attachment.get(SERVER)}")
    if SERVER in g._host_missing_ticks:
        failures.append("4: SERVER missing-tick counter should be cleared on reappearance")
    # then missing again -> retained again (counter restarted)
    run_poll(g, [STORAGE, CLIENT])
    if g.host_attachment.get(SERVER) != (1, 3):
        failures.append("4: SERVER should be retained again after reset")

    # -- 5. never-known host absent -> never attached -----------------------
    g = build()
    run_poll(g, [SERVER])
    for i in range(4):
        run_poll(g, [SERVER, STORAGE])
    if OTHER in g.host_attachment:
        failures.append("5: never-known host must not appear")

    # -- 6. regression: present host attached exactly ----------------------
    g = build()
    run_poll(g, [STORAGE])
    if g.host_attachment.get(STORAGE) != (1, 3):
        failures.append("6: present host should attach at (1,3)")

    if failures:
        print("FAIL")
        for f in failures:
            print("  -", f)
        return 1
    print("PASS: topology host_attachment grace-window checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
