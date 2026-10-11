#!/usr/bin/env python3
"""rq2v4_p2_06_selection_spread_selftest.py — P2.6 backend-selection spread.

Exercises the P2.6 spread in ``sdn_controller/_vip_routing/selection.py``
(``select_server``):

- Band membership: candidates within ``_BACKEND_SELECTION_SPREAD_EPS`` of the
  pool minimum are spread across clients; candidates beyond eps are excluded.
- Client spread: a synchronized burst (many distinct client MACs, identical
  pool state) fans out over the band instead of collapsing to one winner.
- Determinism: the same client gets the same band member for a stable band.
- Legacy: with eps = 0 the exact pre-P2.6 behaviour holds (unique argmin
  wins for every client; a warm claim owns the selection exclusively).
- Warm inclusion: with eps > 0 a live warm claim JOINS the band (gets a
  share) instead of monopolising it.
- Peer guard: a cross-LAN unit beyond eps never enters a local band.

Exit non-zero on any assertion failure. Host Python, stdlib only.
See docs/operation/testing/experiment/v4/rq2/rq2v4_p2_03_relief_diagnosis.md.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[3]
SOURCE = REPO / "source"
sys.path.insert(0, str(SOURCE))

for _var in ("BACKEND_SELECTION_SPREAD_EPS", "BACKEND_SELECTION_POLICY",
             "VIP_SERVER_PER_CONNECTION_FLOWS",
             "W_CPU", "W_RAM", "W_REQUESTS", "W_HOPS"):
    os.environ.pop(_var, None)

from sdn_controller._vip_routing import selection  # noqa: E402
from sdn_controller._vip_routing.config import WarmLease  # noqa: E402


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        print(f"FAIL: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(f"  ok: {msg}")


def _stats(cpu: float) -> SimpleNamespace:
    return SimpleNamespace(avg_cpu_percent=cpu, avg_ram_used_mb=0.0,
                           request_count=0)


def _controller(units: dict, hop_max: float = 2.0,
                peers: set | None = None) -> SimpleNamespace:
    """units: {mac: stats_or_None}. All units are local unless in peers."""
    peers = peers or set()
    pool = {mac: {"mac": mac, "ip": f"10.0.0.{i + 10}"} for i, mac in enumerate(units)}
    return SimpleNamespace(
        vip_server_pool=pool,
        _server_stats={mac: st for mac, st in units.items() if st is not None},
        peer_hosts=peers,
        hop_cache={},                 # filled per test for the client
        _hop_cache_max=hop_max,
        host_attachment=set(),
        _avg_hop_count=2.0,
        _peer_avg_hop_count=2.0,
        _warm_server_leases={},
        _warm_lock=threading.Lock(),
        _warm_rr_idx=0,
        _rr_server_idx=0,
        _backend_discovery_ts={},
        _mac_to_ip={mac: entry["ip"] for mac, entry in pool.items()},
    )


CLIENTS = [f"aa:bb:cc:00:00:{i:02x}" for i in range(60)]


def _seed_hops(ctrl, macs) -> None:
    if isinstance(macs, dict):
        for client in CLIENTS:
            ctrl.hop_cache[client] = dict(macs)
    else:
        for client in CLIENTS:
            ctrl.hop_cache[client] = {mac: 1.0 for mac in macs}


def test_band_membership_and_spread() -> None:
    # cpu_max = 100 -> A (0) and B (2) are 0.2 * 0.02 = 0.004 apart -> band.
    # C (100) is 0.20 away -> excluded.
    a, b, c = "00:00:00:00:00:01", "00:00:00:00:00:02", "00:00:00:00:00:03"
    ctrl = _controller({a: _stats(0.0), b: _stats(2.0), c: _stats(100.0)})
    _seed_hops(ctrl, (a, b, c))

    picks = [selection.select_server(ctrl, client)["mac"] for client in CLIENTS]
    distinct = set(picks)
    _assert(c not in distinct, "beyond-eps candidate never enters the band")
    _assert(distinct == {a, b}, "within-eps candidates both receive clients")
    _assert(picks.count(a) > 10 and picks.count(b) > 10,
            f"spread is roughly balanced (a={picks.count(a)} b={picks.count(b)})")

    first = selection.select_server(ctrl, CLIENTS[0])["mac"]
    again = selection.select_server(ctrl, CLIENTS[0])["mac"]
    _assert(first == again, "same client is deterministic for a stable band")


def test_legacy_epsilon_zero() -> None:
    a, b, c = "00:00:00:00:00:01", "00:00:00:00:00:02", "00:00:00:00:00:03"
    ctrl = _controller({a: _stats(0.0), b: _stats(10.0), c: _stats(100.0)})
    _seed_hops(ctrl, (a, b, c))

    original = selection._BACKEND_SELECTION_SPREAD_EPS
    try:
        selection._BACKEND_SELECTION_SPREAD_EPS = 0.0
        picks = {selection.select_server(ctrl, client)["mac"] for client in CLIENTS}
        _assert(picks == {a}, "eps=0: unique argmin wins for every client (legacy funnel)")
    finally:
        selection._BACKEND_SELECTION_SPREAD_EPS = original


def test_warm_inclusion() -> None:
    # a and b: identical stats, near hops -> band {a,b}. e: same stats but 2x
    # hops (delta 0.14 > eps) -> excluded. W: no stats -> joins via the claim.
    a, b, e, w = ("00:00:00:00:00:01", "00:00:00:00:00:02",
                  "00:00:00:00:00:04", "00:00:00:00:00:0f")
    ctrl = _controller({a: _stats(99.0), b: _stats(99.0), e: _stats(99.0), w: None})
    _seed_hops(ctrl, {a: 1.0, b: 1.0, e: 2.0, w: 1.0})
    now = time.monotonic()
    ctrl._warm_server_leases[w] = WarmLease(started_ts=now, expires_ts=now + 45.0)

    picks = [selection.select_server(ctrl, client)["mac"] for client in CLIENTS]
    counts = {mac: picks.count(mac) for mac in (a, b, w)}
    _assert(all(counts[mac] > 0 for mac in (a, b, w)),
            f"warm claim joins the band, all receive clients: {counts}")
    _assert(e not in picks, "beyond-eps candidate stays out with a warm claim live")

    first = selection.select_server(ctrl, CLIENTS[3])["mac"]
    again = selection.select_server(ctrl, CLIENTS[3])["mac"]
    _assert(first == again, "warm band is deterministic per client")

    # Legacy: the warm claim owns the selection exclusively.
    original = selection._BACKEND_SELECTION_SPREAD_EPS
    try:
        selection._BACKEND_SELECTION_SPREAD_EPS = 0.0
        ctrl._warm_server_leases[w] = WarmLease(started_ts=now, expires_ts=now + 45.0)
        picks = {selection.select_server(ctrl, client)["mac"] for client in CLIENTS}
        _assert(picks == {w}, "eps=0: warm claim monopolises (legacy)")
    finally:
        selection._BACKEND_SELECTION_SPREAD_EPS = original


def test_peer_guard() -> None:
    a, p = "00:00:00:00:00:01", "00:00:00:00:00:09"
    ctrl = _controller({a: _stats(0.0), p: _stats(0.0)}, hop_max=4.0, peers={p})
    _seed_hops(ctrl, (a, p))
    picks = {selection.select_server(ctrl, client)["mac"] for client in CLIENTS}
    _assert(picks == {a},
            "cross-LAN unit beyond eps never enters a local band (peer guard)")


def test_single_candidate_and_nan_band() -> None:
    a, c = "00:00:00:00:00:01", "00:00:00:00:00:03"

    # Single candidate: band size 1 (no spread possible, still serves).
    ctrl = _controller({a: _stats(0.0)})
    _seed_hops(ctrl, (a,))
    picks = {selection.select_server(ctrl, client)["mac"] for client in CLIENTS}
    _assert(picks == {a}, "single-candidate band returns the only member")

    # All-NaN costs (malformed telemetry): no comparable minimum -> None.
    nan = float("nan")
    ctrl = _controller({a: _stats(nan), c: _stats(nan)})
    _seed_hops(ctrl, (a, c))
    _assert(selection.select_server(ctrl, CLIENTS[0]) is None,
            "all-NaN costs return None instead of raising")


def main() -> int:
    print("rq2v4 P2.6 selection-spread selftest")
    _assert(selection._BACKEND_SELECTION_SPREAD_EPS == 0.03,
            "default eps is 0.03 (env unset)")
    print("-- band membership + spread")
    test_band_membership_and_spread()
    print("-- legacy eps=0")
    test_legacy_epsilon_zero()
    print("-- warm inclusion")
    test_warm_inclusion()
    print("-- peer guard")
    test_peer_guard()
    print("-- single candidate + NaN band")
    test_single_candidate_and_nan_band()
    print("PASS: all rq2v4 P2.6 selection-spread assertions hold")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
