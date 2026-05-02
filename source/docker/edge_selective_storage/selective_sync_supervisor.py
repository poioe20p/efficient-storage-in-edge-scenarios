"""Selective-sync supervisor entry point for the Tier 1 edge_selective_storage container.

Wires together :mod:`config`, :mod:`forwarder`, and :mod:`admin`. Each
``ForwarderWorker`` is one Python thread running one MongoDB Change Stream
against exactly one hot collection on the owner replica set. The supervisor
itself does no tailing; its responsibilities are bootstrapping workers from
the initial environment config, exposing the ``/forwarder_config`` admin
endpoint for live reconfiguration, and keeping the admin server in the
foreground so the container stays alive.

Design reference: ``docs/operation/elasticy_manager/implementation/
tier1_selective_sync/`` (README + telemetry_and_config).
"""

from __future__ import annotations

import logging
import threading

from pymongo import MongoClient

import admin
from config import DB_NAME, LOCAL_PORT, LOG_LEVEL, TOKEN_DIR, load_env
from forwarder import ForwarderWorker

logger = logging.getLogger("selective_sync_supervisor")


def run() -> None:
    """Supervisor entry point.

    Loads the initial config from the environment, spawns one
    ForwarderWorker thread per hot collection, hands the shared state to
    the admin module, then blocks in the Flask server.
    """
    logging.basicConfig(level=LOG_LEVEL,
                        format="%(asctime)s %(levelname)s %(message)s")

    cfg = load_env()
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)

    local_db = MongoClient(f"mongodb://localhost:{LOCAL_PORT}/")[DB_NAME]
    # Primary-pinning invariant: the supervisor talks to exactly one owner host
    # (the RS primary at promotion time) and never follows failovers.
    # ``directConnection=true`` forces pymongo into single-server SDAM mode —
    # no RS topology discovery, no secondary fallback, no automatic failover
    # following — even if the server's ``hello`` response advertises RS
    # membership. On primary step-down the Change Stream errors out, the
    # ForwarderWorker exits, the supervisor restarts it, and the next attempt
    # fails against the now-secondary host. ``selective_sync_lag_s`` grows
    # past ``SS_STALENESS_LIMIT_S``; the scale-down staleness guard tears the
    # container down; a fresh promotion request resolves the new primary.
    remote_db = (MongoClient(f"mongodb://{cfg.owner_host}/?directConnection=true")[DB_NAME]
                 if cfg.owner_host else None)

    workers: dict[str, ForwarderWorker] = {}
    workers_lock = threading.Lock()

    if remote_db is not None:
        with workers_lock:
            for coll, ids in cfg.collections.items():
                w = ForwarderWorker(local_db, remote_db, coll, ids, cfg.max_ttl_s)
                w.start()
                workers[coll] = w
        logger.info("Started %d forwarder worker(s): %s",
                    len(workers), sorted(workers))
    else:
        logger.warning("OWNER_HOST unset — supervisor starting with no workers")

    admin.init_state(
        workers=workers,
        workers_lock=workers_lock,
        local_db=local_db,
        remote_db=remote_db,
        max_ttl_s=cfg.max_ttl_s,
    )
    admin.run_admin_server()


if __name__ == "__main__":
    run()
