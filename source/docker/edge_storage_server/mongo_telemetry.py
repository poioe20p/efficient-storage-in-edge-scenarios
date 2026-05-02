import os
import socket
import subprocess
import time
import logging

import zmq
from pymongo import MongoClient
from pymongo.errors import PyMongoError


# --- Container resource accounting (cgroup-based) -----------------------
# psutil.cpu_percent() and psutil.virtual_memory() read /proc, which is NOT
# namespaced inside Docker — they report host-wide values. We instead read
# the container's cgroup files, which are populated by the kernel for this
# container's cgroup only. Supports cgroup v2 (preferred) and v1 fallback.

_CGROUP_ROOT = "/sys/fs/cgroup"
_cpu_state: dict[str, float | None] = {"usec": None, "mono": None}


def _is_cgroup_v2() -> bool:
    return os.path.exists(f"{_CGROUP_ROOT}/cgroup.controllers")


def _read_cpu_usage_usec() -> int | None:
    try:
        if _is_cgroup_v2():
            with open(f"{_CGROUP_ROOT}/cpu.stat") as f:
                for line in f:
                    if line.startswith("usage_usec"):
                        return int(line.split()[1])
        else:
            with open(f"{_CGROUP_ROOT}/cpuacct/cpuacct.usage") as f:
                return int(f.read().strip()) // 1000  # ns → µs
    except (OSError, ValueError):
        return None
    return None


def _effective_cpu_count() -> float:
    try:
        if _is_cgroup_v2():
            with open(f"{_CGROUP_ROOT}/cpu.max") as f:
                quota, period = f.read().split()
            if quota != "max":
                return int(quota) / int(period)
        else:
            with open(f"{_CGROUP_ROOT}/cpu/cpu.cfs_quota_us") as f:
                quota = int(f.read().strip())
            if quota > 0:
                with open(f"{_CGROUP_ROOT}/cpu/cpu.cfs_period_us") as f:
                    period = int(f.read().strip())
                return quota / period
    except (OSError, ValueError):
        pass
    return float(os.cpu_count() or 1)


def container_cpu_percent() -> float:
    """CPU% normalised to the container's quota (100% = full quota).
    First call returns 0.0 (no baseline yet). Polled periodically by the
    telemetry loop so no extra caching layer is needed here."""
    now_t = time.monotonic()
    now_u = _read_cpu_usage_usec()
    if now_u is None:
        return 0.0
    last_u = _cpu_state["usec"]
    last_t = _cpu_state["mono"]
    _cpu_state["usec"] = float(now_u)
    _cpu_state["mono"] = now_t
    if last_u is None or last_t is None:
        return 0.0
    elapsed_us = (now_t - last_t) * 1_000_000
    if elapsed_us <= 0:
        return 0.0
    cpus = _effective_cpu_count() or 1.0
    return min(100.0 * (now_u - last_u) / (elapsed_us * cpus), 100.0)


def container_ram_used_mb() -> float:
    try:
        if _is_cgroup_v2():
            with open(f"{_CGROUP_ROOT}/memory.current") as f:
                return int(f.read().strip()) / 1_048_576
        with open(f"{_CGROUP_ROOT}/memory/memory.usage_in_bytes") as f:
            return int(f.read().strip()) / 1_048_576
    except (OSError, ValueError):
        return 0.0

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
MONGO_URI            = os.environ.get("MONGO_URI", "mongodb://localhost:27018/")
INTERVAL_S           = float(os.environ.get("TELEMETRY_INTERVAL_S", "0.5"))
HEARTBEAT_INTERVAL_S = float(os.environ.get("HEARTBEAT_INTERVAL_S", "60"))
# Heartbeats are the only liveness signal for the static primary DB during
# quiet periods. The default is disabled: dynamic storage secondaries don't
# need heartbeats (idleness is handled by scale-down, failure by the
# telemetry-window absence timeout). Static containers opt in by setting
# HEARTBEAT_ENABLED=true in their docker run command. See
# docs/operation/other/heartbeat_dynamic_node_gate_plan.md.
HEARTBEAT_ENABLED = (
    os.environ.get("HEARTBEAT_ENABLED", "false").strip().lower() == "true"
)
LOG_LEVEL            = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(message)s")

_ctx  = zmq.Context.instance()
# ZMQ socket is created in main() after _rs_self_join() (which ensures eth0
# exists), but BEFORE _wait_for_ready() so telemetry can flow even while
# the node is still syncing to SECONDARY.
_sock: zmq.Socket | None = None
logger = logging.getLogger("mongo_telemetry")


def _get_server_mac() -> str:
    """Return the cached MAC, re-discovering if the interface wasn't available yet."""
    global SERVER_MAC
    if SERVER_MAC == "unknown":
        SERVER_MAC = _discover_mac()
    return SERVER_MAC

_prev_opcounters: dict | None = None
_last_send_ts: float = 0.0
_sent_secondary_bootstrap = False


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


def _repl_lag_and_state(client: MongoClient) -> tuple[float | None, str | None]:
    """Return (replication_lag_seconds, member_state_str) for this node.

    Returns:
        (0.0, "PRIMARY")   — this node is the primary.
        (float, "SECONDARY") — seconds this secondary lags behind primary.
        (None, None)        — standalone (replica set not initialised).
    """
    try:
        status = client.admin.command("replSetGetStatus")
    except PyMongoError:
        logger.debug("replSetGetStatus failed — node is standalone or replica set not initialised")
        return None, None

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
        return 0.0, my_state

    lag = (primary_optime - my_optime).total_seconds()
    logger.debug("Replication lag calculated: %.3f s", lag)
    return max(lag, 0.0), my_state


def _push_stats(*, force_bootstrap_secondary: bool = False) -> None:
    global _prev_opcounters, _last_send_ts, _sent_secondary_bootstrap

    logger.debug("Connecting to MongoDB at %s", MONGO_URI)
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
    try:
        server_status       = client.admin.command("serverStatus")
        connections_current = server_status.get("connections", {}).get("current", -1)
        logger.debug("MongoDB connections current: %d", connections_current)
        repl_lag, member_state = _repl_lag_and_state(client)
        logger.debug("Replication lag: %s s  state: %s", repl_lag, member_state)
    except PyMongoError as exc:
        logger.info("Failed to query MongoDB stats: %s", exc)
        connections_current = -1
        repl_lag            = None
        member_state        = None
        _prev_opcounters    = None  # reset so next successful poll always sends
        return
    finally:
        client.close()

    opcounters = server_status.get("opcounters", {})
    activity   = _has_client_activity(opcounters, _prev_opcounters)
    _prev_opcounters = opcounters

    now = time.time()

    if force_bootstrap_secondary and member_state == "SECONDARY" and not _sent_secondary_bootstrap:
        event_type = "mongo_stats"
        _sent_secondary_bootstrap = True
    elif activity:
        event_type = "mongo_stats"
    elif HEARTBEAT_ENABLED and now - _last_send_ts >= HEARTBEAT_INTERVAL_S:
        event_type = "heartbeat"
    else:
        logger.debug("No client activity — skipping telemetry push")
        return

    event = {
        "event_type":          event_type,
        "server_id":           _get_server_mac(),
        "ts":                  now,
        "repl_lag_s":          repl_lag,
        "member_state":        member_state,
        "connections_current": connections_current,
        "cpu_percent":         container_cpu_percent(),
        "ram_used_mb":         container_ram_used_mb(),
    }
    logger.debug("cpu=%.1f%% ram=%.1f MB", event["cpu_percent"], event["ram_used_mb"])
    logger.info("Pushing %s event for mac=%s", event_type, _get_server_mac())
    _sock.send_json(event, zmq.NOBLOCK)
    _last_send_ts = now


_RS_MAX_ATTEMPTS    = 5
_RS_INITIAL_BACKOFF = 3.0    # seconds
_RS_BACKOFF_FACTOR  = 2.0
_NETWORK_WAIT_TIMEOUT = 120.0  # seconds to wait for eth0 + seed connectivity
RS_READY_TIMEOUT_S  = float(os.environ.get("RS_READY_TIMEOUT_S", "300"))


def _wait_for_network(seed_host: str, seed_port: int, timeout: float = _NETWORK_WAIT_TIMEOUT) -> bool:
    """Block until eth0 exists AND the seed host is TCP-reachable.

    The container starts with ``--network none``.  ``add_network_node.sh``
    creates the veth pair and attaches eth0 *after* ``docker run``.
    This function must complete before ``_rs_self_join()`` can connect
    to the RS primary.

    Returns True when connectivity is confirmed, False on timeout.
    """
    deadline = time.monotonic() + timeout
    logger.info("Waiting for network (eth0 + IPv4 + TCP %s:%d) ...", seed_host, seed_port)
    while time.monotonic() < deadline:
        # 1. Does the network interface exist yet?
        if not os.path.exists("/sys/class/net/eth0"):
            time.sleep(1)
            continue
        # 2. Does eth0 have an IPv4 address?
        #    add_network_node.sh creates the veth pair before assigning the IP,
        #    so the interface may appear in sysfs before the address is set.
        own_ip = _discover_own_ip()
        if not own_ip:
            logger.debug("eth0 exists but no IPv4 yet — retrying")
            time.sleep(1)
            continue
        # 3. Can we TCP-connect to the seed host?
        try:
            with socket.create_connection((seed_host, seed_port), timeout=3):
                logger.info("Network ready \u2014 own_ip=%s  seed %s:%d reachable", own_ip, seed_host, seed_port)
                return True
        except OSError:
            time.sleep(1)
    logger.error("Network wait timed out after %.0fs", timeout)
    return False


def _discover_own_ip() -> str:
    """Discover this container's IP from eth0 (or first non-loopback interface)."""
    preferred = os.environ.get("IFACE", "eth0")
    try:
        result = subprocess.run(
            ["ip", "-4", "-o", "addr", "show", preferred],
            capture_output=True, text=True, timeout=5,
        )
        # Output: "2: eth0    inet 10.0.0.7/24 brd 10.0.0.255 scope global eth0"
        for part in result.stdout.split():
            if "/" in part and "." in part:
                return part.split("/")[0]
    except Exception:
        pass
    return ""


def _rs_self_join() -> None:
    """Join this node to the replica set by connecting to the seed host.

    Steps:
      1. Connect to RS_SEED_HOST, query isMaster to find the current primary.
      2. Discover own IP from eth0.
      3. Clean stale member at own host:port if present.
      4. rs.add({host: own_ip:port, priority: 0}) with retry/backoff.

    Environment:
      RS_SEED_HOST  \u2014 host:port of a known RS member (seed)
      MONGO_PORT    \u2014 port this mongod listens on
      MONGO_REPLSET \u2014 replica set name (for validation)
    """
    seed_host = os.environ.get("RS_SEED_HOST", "")
    port      = int(os.environ.get("MONGO_PORT", "27018"))

    if not seed_host:
        logger.warning("RS_ADD_SELF=true but RS_SEED_HOST not set \u2014 skipping self-join")
        return

    # Parse host:port for the network wait
    seed_parts = seed_host.rsplit(":", 1)
    seed_ip    = seed_parts[0]
    seed_port_int = int(seed_parts[1]) if len(seed_parts) > 1 else port

    # Wait for eth0 + seed connectivity (blocks until add_network_node.sh runs)
    if not _wait_for_network(seed_ip, seed_port_int):
        logger.error("Network never became available \u2014 cannot self-join RS")
        return

    own_ip = _discover_own_ip()
    if not own_ip:
        logger.error("Could not discover own IP \u2014 cannot self-join RS")
        return
    member_host = f"{own_ip}:{port}"
    logger.info("RS self-join: seed=%s own=%s", seed_host, member_host)

    backoff = _RS_INITIAL_BACKOFF
    for attempt in range(1, _RS_MAX_ATTEMPTS + 1):
        try:
            # Connect to seed to discover the current primary
            client = MongoClient(f"mongodb://{seed_host}/",
                                 serverSelectionTimeoutMS=5000,
                                 directConnection=True)
            try:
                is_master = client.admin.command("isMaster")
                primary_host = is_master.get("primary")
                logger.info("Attempt %d/%d: isMaster → primary=%s, setName=%s",
                            attempt, _RS_MAX_ATTEMPTS, primary_host,
                            is_master.get("setName", "?"))
            finally:
                client.close()

            if not primary_host:
                logger.warning("Attempt %d/%d: no primary in isMaster response \u2014 retrying in %.0fs",
                               attempt, _RS_MAX_ATTEMPTS, backoff)
                time.sleep(backoff)
                backoff *= _RS_BACKOFF_FACTOR
                continue

            # Connect to the actual primary
            primary_client = MongoClient(f"mongodb://{primary_host}/",
                                        serverSelectionTimeoutMS=5000,
                                        directConnection=True)
            try:
                # Single config fetch: remove stale member (if any) AND add
                # ourselves in one replSetReconfig to avoid version drift.
                config = primary_client.admin.command("replSetGetConfig")["config"]
                logger.info("Attempt %d/%d: RS config v%d, %d members: %s",
                            attempt, _RS_MAX_ATTEMPTS, config["version"],
                            len(config["members"]),
                            [m["host"] for m in config["members"]])

                # Clean stale member at our host:port if present
                original_len = len(config["members"])
                config["members"] = [
                    m for m in config["members"] if m.get("host") != member_host
                ]
                if len(config["members"]) < original_len:
                    logger.info("Removing stale RS member at %s from config", member_host)

                # rs.add() \u2014 append ourselves
                max_id = max(m["_id"] for m in config["members"])
                config["version"] += 1
                config["members"].append({
                    "_id": max_id + 1,
                    "host": member_host,
                    "priority": 0,
                    "votes": 0,
                })
                primary_client.admin.command("replSetReconfig", config)
                logger.info("RS self-join succeeded: added %s to RS (attempt %d, new config v%d, %d members)",
                            member_host, attempt, config["version"], len(config["members"]))
                return
            finally:
                primary_client.close()

        except PyMongoError as exc:
            logger.warning("Attempt %d/%d: RS self-join failed: %s \u2014 retrying in %.0fs",
                           attempt, _RS_MAX_ATTEMPTS, exc, backoff)
            time.sleep(backoff)
            backoff *= _RS_BACKOFF_FACTOR

    logger.error("RS self-join FAILED after %d attempts \u2014 node will not join RS", _RS_MAX_ATTEMPTS)


_READY_STATES = frozenset({"SECONDARY", "PRIMARY"})


def _wait_for_ready(timeout: float = RS_READY_TIMEOUT_S) -> str | None:
    """Block until this node reaches SECONDARY or PRIMARY state, or timeout.

    Returns the state string ("SECONDARY" or "PRIMARY") on success,
    or ``None`` if the timeout expires.  When ``None`` is returned the
    caller should still enter the telemetry loop so the controller
    receives heartbeats and diagnostics.
    """
    logger.info("Waiting for a ready replica-set state (timeout=%.0fs) ...", timeout)
    deadline = time.monotonic() + timeout
    last_progress = time.monotonic()
    while time.monotonic() < deadline:
        try:
            client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
            try:
                status = client.admin.command("replSetGetStatus")
            finally:
                client.close()

            for member in status.get("members", []):
                if member.get("self") and member.get("stateStr") in _READY_STATES:
                    state_str = member["stateStr"]
                    logger.info("Replica-set state reached: %s", state_str)
                    return state_str
        except Exception as exc:
            logger.debug("Not ready yet: %s", exc)

        now = time.monotonic()
        if now - last_progress >= 30:
            elapsed = now - (deadline - timeout)
            logger.info("Still waiting for RS ready state (%.0f/%.0fs elapsed)", elapsed, timeout)
            last_progress = now

        time.sleep(INTERVAL_S)

    logger.error("_wait_for_ready timed out after %.0fs — node never reached SECONDARY/PRIMARY", timeout)
    return None


def main() -> None:
    global _sock

    logger.info("mongo_telemetry starting: mac=%s interval=%.1fs", _get_server_mac(), INTERVAL_S)

    # If RS_ADD_SELF is set, self-join the RS first (with retry/backoff).
    # _rs_self_join() calls _wait_for_network() internally, ensuring eth0
    # is available when it returns (even if the join itself fails).
    if os.environ.get("RS_ADD_SELF") == "true":
        _rs_self_join()

    # Create ZMQ socket EARLY — before _wait_for_ready() — so that even
    # if the RS join failed or the node is stuck in STARTUP2, diagnostic
    # heartbeats can still reach the controller.
    _sock = _ctx.socket(zmq.PUSH)
    _sock.connect(AGGREGATOR_PULL_ADDR)
    logger.info("ZMQ PUSH socket connected to %s", AGGREGATOR_PULL_ADDR)

    # Wait for RS state with timeout — returns None if timeout expires.
    state_str = _wait_for_ready()

    # Emit rs_secondary_ready if applicable (fast path for VIP promotion).
    if state_str == "SECONDARY":
        container_name = os.environ.get("CONTAINER_NAME", "unknown")
        event = {
            "event_type": "rs_secondary_ready",
            "server_id":  _get_server_mac(),
            "container":  container_name,
            "ts":         time.time(),
        }
        logger.info(
            "SECONDARY reached — emitting rs_secondary_ready (mac=%s)",
            _get_server_mac(),
        )
        _sock.send_json(event, zmq.NOBLOCK)
        _push_stats(force_bootstrap_secondary=True)
    elif state_str == "PRIMARY":
        logger.info("PRIMARY detected — skipping rs_secondary_ready event")
    else:
        logger.warning(
            "_wait_for_ready returned None — entering telemetry loop without confirmed RS state"
        )

    logger.info("Entering normal telemetry loop")
    while True:
        try:
            _push_stats()
        except Exception as exc:
            logger.info("Unexpected error in _push_stats: %s", exc)
        time.sleep(INTERVAL_S)


if __name__ == "__main__":
    main()
