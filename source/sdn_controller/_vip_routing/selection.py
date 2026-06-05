"""Backend selection logic: warm-lease claiming, WSM cost functions,
and round-robin tie-breaking for server and storage VIPs.
"""

import time

from .config import (
    _W_CPU, _W_RAM, _W_REQUESTS, _W_HOPS,
    _W_STORAGE_CPU, _W_STORAGE_RAM, _W_STORAGE_CONNECTIONS,
    _W_STORAGE_LAG, _W_STORAGE_HOPS,
    logger,
)


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


def _filter_previous_normal_backend(
    controller,
    domain: str,
    client_mac: str,
    pool: dict[str, dict],
) -> dict[str, dict]:
    key = (client_mac, domain)
    with controller._warm_lock:
        previous_normal_mac = controller._last_normal_storage_choice.get(key)

    if previous_normal_mac is None or previous_normal_mac not in pool:
        return pool

    filtered = {
        mac: entry
        for mac, entry in pool.items()
        if mac != previous_normal_mac
    }
    if filtered:
        logger.info(
            "select_storage(%s): recovery avoiding last normal backend mac=%s client=%s",
            domain,
            previous_normal_mac,
            client_mac,
        )
        return filtered

    logger.info(
        "select_storage(%s): recovery fallback to full pool after avoidance would empty candidates client=%s mac=%s",
        domain,
        client_mac,
        previous_normal_mac,
    )
    return pool


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

        # Unknown stats → treat as worst-case (1.0) so backends without
        # telemetry yet (e.g. peer backends, newly added nodes) are not
        # accidentally preferred over measured local backends.
        cpu_norm = (stats.avg_cpu_percent / cpu_max) if stats else 1.0
        ram_norm = (stats.avg_ram_used_mb  / ram_max) if stats else 1.0
        req_norm = (stats.request_count    / req_max) if stats else 1.0

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
    *,
    recovery: bool = False,
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

    if recovery:
        pool = _filter_previous_normal_backend(controller, domain, client_mac, pool)

    warm = _claim_warm_backend(
        controller,
        f"vip_data({domain})",
        controller._warm_storage_leases.setdefault(domain, {}),
        pool,
    )
    if warm is not None:
        if not recovery:
            from .state import _remember_normal_storage_choice
            _remember_normal_storage_choice(controller, client_mac, domain, warm["mac"])
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

        # Unknown stats → treat as worst-case (1.0) so backends without
        # telemetry yet (e.g. peer backends, newly added nodes) are not
        # accidentally preferred over measured local backends.
        cpu_norm  = (stats.avg_cpu_percent        / cpu_max)  if stats else 1.0
        ram_norm  = (stats.avg_ram_used_mb         / ram_max)  if stats else 1.0
        conn_norm = (stats.avg_connections          / conn_max) if stats else 1.0
        lag_norm  = ((stats.avg_repl_lag_s or 0)   / lag_max)  if stats else 1.0

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
    if not recovery:
        from .state import _remember_normal_storage_choice
        _remember_normal_storage_choice(controller, client_mac, domain, chosen["mac"])
    return chosen
