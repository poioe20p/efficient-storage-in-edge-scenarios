import os
import time
import logging

import psutil
import zmq
from pymongo import MongoClient
from pymongo.errors import PyMongoError

def _aggregator_addr_from_lan() -> str:
    """Derive the aggregator ZMQ PULL address from the LAN_ID env var (e.g. "lan1")."""
    lan_id = os.environ.get("LAN_ID", "")
    if not lan_id.startswith("lan"):
        return ""
    subnet_third_octet = int(lan_id[3:]) - 1  # lan1 → 10.0.0.x, lan2 → 10.0.1.x
    return f"tcp://10.0.{subnet_third_octet}.5:5555"


def _discover_mac() -> str:
    """Return the MAC address of the first non-loopback interface found in sysfs.

    Prefers the interface named by the IFACE env var (default: eth0), but falls
    back to scanning all interfaces so that containers whose primary interface is
    named differently still report a real MAC.
    """
    preferred = os.environ.get("IFACE", "eth0")
    candidates = [preferred]
    try:
        candidates += sorted(os.listdir("/sys/class/net"))
    except OSError:
        pass
    for iface in candidates:
        if iface == "lo":
            continue
        try:
            with open(f"/sys/class/net/{iface}/address") as f:
                mac = f.read().strip()
            if mac and mac != "00:00:00:00:00:00":
                return mac
        except OSError:
            continue
    return "unknown"


SERVER_MAC           = _discover_mac()
AGGREGATOR_PULL_ADDR = os.environ.get("AGGREGATOR_PULL_ADDR", "") or _aggregator_addr_from_lan()
MONGO_URI            = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
INTERVAL_S           = float(os.environ.get("TELEMETRY_INTERVAL_S", "2"))
HEARTBEAT_INTERVAL_S = float(os.environ.get("HEARTBEAT_INTERVAL_S", "60"))
LOG_LEVEL            = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(message)s")

_ctx  = zmq.Context.instance()
_sock = _ctx.socket(zmq.PUSH)
_sock.connect(AGGREGATOR_PULL_ADDR)
logger = logging.getLogger("mongo_telemetry")
logger.info("ZMQ PUSH socket connected to %s", AGGREGATOR_PULL_ADDR)


def _get_server_mac() -> str:
    """Return the cached MAC, re-discovering if the interface wasn't available yet."""
    global SERVER_MAC
    if SERVER_MAC == "unknown":
        SERVER_MAC = _discover_mac()
    return SERVER_MAC

_prev_opcounters: dict | None = None
_last_send_ts: float = 0.0


def _has_client_activity(current: dict, previous: dict | None) -> bool:
    """Return True if non-telemetry operations occurred since the last poll.

    The sidecar issues 2 admin commands per cycle (serverStatus + replSetGetStatus),
    so a command delta of exactly 2 with no other changes means no client activity.
    When previous is None this is the very first poll; we capture the baseline
    without reporting, so the 3 internal MongoDB connections don't produce a
    spurious mongo_stats event before any real client has connected.
    """
    if previous is None:
        return False  # first poll — capture baseline only, do not report

    for op in ("insert", "query", "update", "delete", "getmore"):
        if current.get(op, 0) - previous.get(op, 0) > 0:
            return True

    # Do NOT use the `command` opcounter as an activity signal — in a replica
    # set, internal heartbeat/election commands inflate it every cycle.
    return False


def _repl_lag_s(client: MongoClient):
    """Return replication lag in seconds for this node relative to the primary.

    Returns:
        0.0   — this node is the primary (always current).
        float — seconds this secondary lags behind primary (`>= 0`).
        None  — standalone (replica set not initialised); lag concept N/A.
    """
    try:
        status = client.admin.command("replSetGetStatus")
    except PyMongoError:
        logger.debug("replSetGetStatus failed — node is standalone or replica set not initialised")
        return None  # standalone or replica set not yet initialised

    primary_optime = None
    my_optime      = None
    my_state       = None

    for member in status.get("members", []):
        if member.get("self"):
            my_optime = member.get("optimeDate")
            my_state  = member.get("stateStr")
            logger.debug("This node: state=%s optimeDate=%s", my_state, my_optime)
        if member.get("stateStr") == "PRIMARY":
            primary_optime = member.get("optimeDate")
            logger.debug("Primary found: optimeDate=%s", primary_optime)

    if my_state == "PRIMARY" or primary_optime is None or my_optime is None:
        logger.debug("Replication lag not applicable (state=%s)", my_state)
        return 0.0

    lag = (primary_optime - my_optime).total_seconds()
    logger.debug("Replication lag calculated: %.3f s", lag)
    return max(lag, 0.0)


def _push_stats() -> None:
    global _prev_opcounters, _last_send_ts

    logger.debug("Connecting to MongoDB at %s", MONGO_URI)
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
    try:
        server_status       = client.admin.command("serverStatus")
        connections_current = server_status.get("connections", {}).get("current", -1)
        logger.debug("MongoDB connections current: %d", connections_current)
        repl_lag            = _repl_lag_s(client)
        logger.debug("Replication lag: %s s", repl_lag)
    except PyMongoError as exc:
        logger.info("Failed to query MongoDB stats: %s", exc)
        connections_current = -1
        repl_lag            = None
        _prev_opcounters    = None  # reset so next successful poll always sends
        return
    finally:
        client.close()

    opcounters = server_status.get("opcounters", {})
    activity   = _has_client_activity(opcounters, _prev_opcounters)
    _prev_opcounters = opcounters

    now = time.time()

    if activity:
        event_type = "mongo_stats"
    elif now - _last_send_ts >= HEARTBEAT_INTERVAL_S:
        event_type = "heartbeat"
    else:
        logger.debug("No client activity — skipping telemetry push")
        return

    event = {
        "event_type":          event_type,
        "server_id":           _get_server_mac(),
        "ts":                  now,
        "repl_lag_s":          repl_lag,
        "connections_current": connections_current,
        "cpu_percent":         psutil.cpu_percent(interval=None),
        "ram_used_mb":         psutil.virtual_memory().used / 1_048_576,
    }
    logger.debug("cpu=%.1f%% ram=%.1f MB", event["cpu_percent"], event["ram_used_mb"])
    logger.info("Pushing %s event for mac=%s", event_type, _get_server_mac())
    _sock.send_json(event, zmq.NOBLOCK)
    _last_send_ts = now


def main() -> None:
    logger.info("mongo_telemetry starting: mac=%s interval=%.1fs", _get_server_mac(), INTERVAL_S)
    while True:
        try:
            _push_stats()
        except Exception as exc:
            logger.info("Unexpected error in _push_stats: %s", exc)
        time.sleep(INTERVAL_S)


if __name__ == "__main__":
    main()
