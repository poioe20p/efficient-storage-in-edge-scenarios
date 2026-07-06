"""Backend selection logic: warm-lease claiming, WSM cost functions,
and round-robin tie-breaking for server and storage VIPs.
"""

import time

from .config import (
    _W_CPU, _W_RAM, _W_REQUESTS, _W_HOPS,
    _W_STORAGE_CPU, _W_STORAGE_RAM, _W_STORAGE_CONNECTIONS,
    _W_STORAGE_LAG, _W_STORAGE_HOPS,
    _BACKEND_SELECTION_POLICY,
    logger,
)
from ..scaling_config import _VIP_WARM_SERVER_SECONDS, _VIP_WARM_STORAGE_SECONDS


def _unknown_stats_default():
    """Return the unknown-stats normalised value for the current policy mode.

    topology_host:      0.0 (best-case  → cold-start herd)
    topology_slowstart: 0.0 (neutral    → penalty handles all deterrence)
    topology_lifecycle: 1.0 (worst-case → warm lease short-circuits WSM anyway;
                          also protects against preferring unmeasured peer backends)
    """
    if _BACKEND_SELECTION_POLICY == "topology_host":
        return 0.0
    if _BACKEND_SELECTION_POLICY == "topology_slowstart":
        return 0.0     # neutral — penalty owns all deterrence
    return 1.0          # topology_lifecycle (default)


def _slowstart_penalty(controller, mac: str, ttl_s: float) -> float:
    """Graduated cost penalty for discovery-time slow-start ramp (RQ2).

    Before discovery: returns 1.0 — the backend is worst-case, effectively
    invisible in practice (will only win traffic via round-robin tie-breaking
    if all other backends are equally penalised).

    After discovery: linear decay from 1.0 at discovery time to 0.0 at
    discovery_time + ttl_s.

    Returns 0.0 if the policy mode is not topology_slowstart, or if the
    ramp period has elapsed.

    Design note — penalty magnitude: the unweighted penalty (range 0–1)
    exceeds the maximum weighted WSM cost sum (0.88 for compute,
    0.90 for storage). This means the penalty is architecturally dominant —
    a backend under slowstart cannot win against any backend with real
    stats until the penalty has decayed substantially. This is intentional:
    the ramp IS the mechanism, not a subtle bias. In a separated system,
    the LB's slow-start weight dominates routing in the same way.
    """
    if _BACKEND_SELECTION_POLICY != "topology_slowstart":
        return 0.0
    discovered = controller._backend_discovery_ts.get(mac)
    if discovered is None:
        return 1.0          # undiscovered → maximum deterrence
    elapsed = time.monotonic() - discovered
    if elapsed >= ttl_s:
        return 0.0
    return 1.0 - (elapsed / ttl_s)


def _claim_warm_backend(
    controller,
    vip_name: str,
    leases: dict,
    pool: dict,
) -> dict | None:
    """Check for and claim any warm lease for a backend in the pool."""
    now = time.monotonic()

    with controller._warm_lock:

        expired = [
            mac
            for mac, lease in leases.items()
            if lease.expires_ts <= now
        ]
        for mac in expired:
            leases.pop(mac, None)

        candidates = [
            (mac, lease)
            for mac, lease in leases.items()
            if mac in pool and mac in controller._mac_to_ip
        ]
        if not candidates:
            for mac in expired:
                logger.info("%s warm lease expired: mac=%s", vip_name, mac)
            return None

        mac, lease = max(candidates, key=lambda item: item[1].started_ts)
        chosen = pool[mac]

    for expired_mac in expired:
        logger.info("%s warm lease expired: mac=%s", vip_name, expired_mac)

    logger.info(
        "%s warm lease claimed: mac=%s remaining=%.1fs",
        vip_name,
        mac,
        max(lease.expires_ts - now, 0.0),
    )
    return chosen


def select_server(controller, client_mac: str) -> dict | None:
    """Pick the web server with the lowest WSM cost from vip_server_pool.

    Cost_j = w_cpu·(CPU_j/CPU_max) + w_ram·(RAM_j/RAM_max)
           + w_req·(Req_j/Req_max) + w_hops·(Hops_j/Hops_max)

    When multiple candidates share the lowest cost (typical during cold
    start when all resource dimensions are 0.0), round-robin across them
    to distribute traffic evenly.
    """
    pool = controller.vip_server_pool
    if not pool:
        logger.warning("select_server: pool empty")
        return None

    # Warm lease: only active in topology_lifecycle mode (RQ2).
    # topology_host and topology_slowstart skip it — the WSM cost
    # function handles new-backend selection via unknown-stats defaults.
    if _BACKEND_SELECTION_POLICY == "topology_lifecycle":
        warm = _claim_warm_backend(
            controller, "vip_server", controller._warm_server_leases, pool,
        )
        if warm is not None:
            return warm

    # Compute max values for normalization (only from servers in the pool)
    pool_stats = [controller._server_stats[m] for m in pool if m in controller._server_stats]
    cpu_max = max((s.avg_cpu_percent for s in pool_stats), default=0.0) or 1.0
    ram_max = max((s.avg_ram_used_mb  for s in pool_stats), default=0.0) or 1.0
    req_max = max((s.request_count    for s in pool_stats), default=0)   or 1
    hops_max = max(controller._hop_cache_max, 1)

    best_cost = float("inf")
    tied: list[dict] = []

    for mac, entry in pool.items():
        stats = controller._server_stats.get(mac)

        # Unknown stats default depends on policy mode (RQ2).
        _default = _unknown_stats_default()
        cpu_norm = (stats.avg_cpu_percent / cpu_max) if stats else _default
        ram_norm = (stats.avg_ram_used_mb  / ram_max) if stats else _default
        req_norm = (stats.request_count    / req_max) if stats else _default

        hops = (controller.hop_cache.get(client_mac) or {}).get(mac)
        if hops is None:
            if mac in controller.peer_hosts:
                local_avg = max(controller._avg_hop_count, 1.0)
                peer_avg  = max(controller._peer_avg_hop_count, 1.0)
                hops = local_avg + peer_avg
            elif mac in controller.host_attachment:
                hops = max(controller._avg_hop_count, 1.0)
            else:
                hops = hops_max
        hop_norm = hops / hops_max

        cost = (_W_CPU * cpu_norm + _W_RAM * ram_norm
                + _W_REQUESTS * req_norm + _W_HOPS * hop_norm)
        # Slow-start penalty (RQ2): topology_slowstart adds a graduated
        # cost penalty decaying 1.0→0.0 over WARM_SERVER TTL from discovery.
        # No-op for topology_host and topology_lifecycle.
        #
        # Design note — TTL reuse: the penalty decay period reuses
        # _VIP_WARM_SERVER_SECONDS (45 s) — the same TTL used for
        # warm-lease priority windows. These are semantically distinct
        # (warm-lease priority vs. discovery-time ramp), but using the
        # same TTL makes the comparison between topology_slowstart and
        # topology_lifecycle cleaner: both have a 45 s window, differing
        # only in when that window starts (discovery vs. spawn).
        cost += _slowstart_penalty(controller, mac, _VIP_WARM_SERVER_SECONDS)
        logger.debug(
            "select_server: mac=%s cpu=%.1f ram=%.1f req=%s hops=%s cost=%.4f",
            mac,
            stats.avg_cpu_percent if stats else 0.0,
            stats.avg_ram_used_mb if stats else 0.0,
            stats.request_count if stats else 0,
            hops, cost,
        )
        if cost < best_cost:
            best_cost = cost
            tied = [entry]
        elif cost == best_cost:
            tied.append(entry)

    if not tied:
        return None

    chosen = tied[controller._rr_server_idx % len(tied)]
    controller._rr_server_idx += 1
    logger.info(
        "select_server: selected=%s cost=%.4f (tied=%d rr_idx=%d)",
        chosen["mac"], best_cost, len(tied), controller._rr_server_idx - 1,
    )
    return chosen


def select_storage(
    controller,
    domain: str,
    client_mac: str,
) -> dict | None:
    """Pick the storage node with the lowest WSM cost from the domain's pool.

    Cost_j = w_cpu·(CPU_j/CPU_max) + w_ram·(RAM_j/RAM_max)
           + w_conn·(Conn_j/Conn_max) + w_lag·(Lag_j/Lag_max)
           + w_hops·(Hops_j/Hops_max)

    When multiple candidates share the lowest cost (typical during cold
    start when all resource dimensions are 0.0), round-robin across them
    to distribute traffic evenly.  Each domain has its own counter.
    """
    pool = controller.vip_storage_pool_n1 if domain == "n1" else controller.vip_storage_pool_n2
    if not pool:
        logger.warning("select_storage(%s): pool empty", domain)
        return None

    if _BACKEND_SELECTION_POLICY == "topology_lifecycle":
        warm = _claim_warm_backend(
            controller,
            f"vip_data({domain})",
            controller._warm_storage_leases.setdefault(domain, {}),
            pool,
        )
        if warm is not None:
            return warm

    pool_stats = [controller._storage_stats[m] for m in pool if m in controller._storage_stats]
    cpu_max  = max((s.avg_cpu_percent        for s in pool_stats), default=0.0) or 1.0
    ram_max  = max((s.avg_ram_used_mb         for s in pool_stats), default=0.0) or 1.0
    conn_max = max((s.avg_connections          for s in pool_stats), default=0.0) or 1.0
    lag_max  = max((s.avg_repl_lag_s or 0      for s in pool_stats), default=0.0) or 1.0
    hops_max = max(controller._hop_cache_max, 1)

    best_cost = float("inf")
    tied: list[dict] = []

    for mac, entry in pool.items():
        stats = controller._storage_stats.get(mac)

        # Unknown stats default depends on policy mode (RQ2).
        _default = _unknown_stats_default()
        cpu_norm  = (stats.avg_cpu_percent        / cpu_max)  if stats else _default
        ram_norm  = (stats.avg_ram_used_mb         / ram_max)  if stats else _default
        conn_norm = (stats.avg_connections          / conn_max) if stats else _default
        lag_norm  = ((stats.avg_repl_lag_s or 0)   / lag_max)  if stats else _default

        hops = (controller.hop_cache.get(client_mac) or {}).get(mac)
        if hops is None:
            if mac in controller.peer_hosts:
                local_avg = max(controller._avg_hop_count, 1.0)
                peer_avg  = max(controller._peer_avg_hop_count, 1.0)
                hops = local_avg + peer_avg
            elif mac in controller.host_attachment:
                hops = max(controller._avg_hop_count, 1.0)
            else:
                hops = hops_max
        hop_norm = hops / hops_max

        cost = (_W_STORAGE_CPU * cpu_norm + _W_STORAGE_RAM * ram_norm
                + _W_STORAGE_CONNECTIONS * conn_norm
                + _W_STORAGE_LAG * lag_norm + _W_STORAGE_HOPS * hop_norm)
        # Slow-start penalty (RQ2): same design as select_server.
        # Reuses _VIP_WARM_STORAGE_SECONDS (30 s) for the ramp period —
        # same TTL as storage warm leases, differing only in start time.
        cost += _slowstart_penalty(controller, mac, _VIP_WARM_STORAGE_SECONDS)
        logger.debug(
            "select_storage(%s): mac=%s cpu=%.1f ram=%.1f conn=%.1f lag=%.2f hops=%s cost=%.4f",
            domain, mac,
            stats.avg_cpu_percent if stats else 0.0,
            stats.avg_ram_used_mb if stats else 0.0,
            stats.avg_connections if stats else 0.0,
            (stats.avg_repl_lag_s or 0) if stats else 0.0,
            hops, cost,
        )
        if cost < best_cost:
            best_cost = cost
            tied = [entry]
        elif cost == best_cost:
            tied.append(entry)

    if not tied:
        return None

    rr_idx = controller._rr_storage_idx.get(domain, 0)
    chosen = tied[rr_idx % len(tied)]
    controller._rr_storage_idx[domain] = rr_idx + 1
    logger.info(
        "select_storage(%s): selected=%s cost=%.4f (tied=%d rr_idx=%d)",
        domain, chosen["mac"], best_cost, len(tied), rr_idx,
    )
    return chosen
