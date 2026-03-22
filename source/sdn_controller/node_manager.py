"""
node_manager.py — Low-level, timed, idempotent container lifecycle for Thread 3.

Each public method covers the complete lifecycle for one node type:
  1. docker run  --network none  <image>  [<cmd args>]
  2. bash script (veth + OVS attachment, and optionally rs.add for storage nodes)

Every step is individually timed with ``time.perf_counter()``.  On failure the
already-running container is stopped and removed so the next attempt is clean.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

logger = logging.getLogger("os_ken.node_manager")

# Scripts directory — override via NODE_SCRIPTS_DIR env var when the controller
# runs inside a container where the scripts are mounted at a different path.
_pkg_root = Path(__file__).parent.parent   # source/sdn_controller/ -> source/
SCRIPTS_DIR = Path(os.environ.get("NODE_SCRIPTS_DIR", str(_pkg_root / "scripts" / "network")))

_RESULT_IP_RE  = re.compile(r"^RESULT_IP=(\S+)",  re.MULTILINE)
_RESULT_MAC_RE = re.compile(r"^RESULT_MAC=(\S+)", re.MULTILINE)


class NodeOperationState(Enum):
    PENDING           = auto()
    RUNNING_CONTAINER = auto()
    ATTACHING_NETWORK = auto()
    JOINING_RS        = auto()  # storage only
    DONE              = auto()
    FAILED            = auto()


@dataclass
class StepTimings:
    """Wall-clock durations (seconds) for each lifecycle phase.

    ``total_s`` is measured end-to-end and includes inter-step overhead; it is
    NOT the arithmetic sum of the individual fields.
    """
    docker_run_s:       float = 0.0
    network_attach_s:   float = 0.0
    replica_set_join_s: float = 0.0  # storage only; absorbed in network_attach_s when not split
    total_s:            float = 0.0


@dataclass
class NodeResult:
    success:        bool
    container_name: str
    ip:             str | None
    mac:            str | None
    timings:        StepTimings
    state:          NodeOperationState
    stdout:         str = ""
    stderr:         str = ""


class NodeAdder:
    """Stateless helper — each method is a self-contained, timed, idempotent lifecycle."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_edge_server(self, lan: int, name: str) -> NodeResult:
        """Spawn an edge_server container and attach it to OVS LAN ``lan``.

        Steps:
          1. ``docker run --network none edge_server``
          2. ``add_network_node.sh --lan <lan> --name <name>``
        """
        timings = StepTimings()
        t_total = time.perf_counter()

        # ── Step 1: docker run ────────────────────────────────────────────────
        logger.info("[node_add] step=docker_run container=%s", name)
        t0 = time.perf_counter()
        ok, stdout, stderr = self._docker_run_server(name)
        timings.docker_run_s = time.perf_counter() - t0

        if not ok:
            timings.total_s = time.perf_counter() - t_total
            return NodeResult(False, name, None, None, timings, NodeOperationState.FAILED, stdout, stderr)

        # ── Step 2: network attachment ────────────────────────────────────────
        logger.info("[node_add] step=attach_network container=%s lan=%d", name, lan)
        t0 = time.perf_counter()
        ok, ip, mac, stdout2, stderr2 = self._run_script(
            SCRIPTS_DIR / "add_network_node.sh",
            ["--lan", str(lan), "--name", name],
        )
        timings.network_attach_s = time.perf_counter() - t0
        timings.total_s = time.perf_counter() - t_total

        if not ok:
            self._cleanup_container(name)
            return NodeResult(
                False, name, None, None, timings, NodeOperationState.FAILED,
                stdout + stdout2, stderr + stderr2,
            )

        logger.debug("[node_add] attach complete  container=%s ip=%s mac=%s", name, ip, mac)
        return NodeResult(True, name, ip, mac, timings, NodeOperationState.DONE,
                          stdout + stdout2, stderr + stderr2)

    def add_storage_node(
        self,
        lan: int,
        name: str,
        rs_name: str,
        primary_container: str,
        port: int = 27018,
    ) -> NodeResult:
        """Spawn an edge_storage_server container, attach it to OVS LAN ``lan``,
        and join the replica set via ``rs.add()``.

        Steps:
          1. ``docker run --network none edge_storage_server mongod --replSet ...``
          2. ``add_network_storage_node.sh`` (veth + OVS + rs.add + SECONDARY wait)
        """
        timings = StepTimings()
        t_total = time.perf_counter()

        # ── Step 1: docker run ────────────────────────────────────────────────
        logger.info("[node_add] step=docker_run container=%s rs=%s", name, rs_name)
        t0 = time.perf_counter()
        ok, stdout, stderr = self._docker_run_storage(name, rs_name, port)
        timings.docker_run_s = time.perf_counter() - t0

        if not ok:
            timings.total_s = time.perf_counter() - t_total
            return NodeResult(False, name, None, None, timings, NodeOperationState.FAILED, stdout, stderr)

        # ── Step 2: network attach + RS join (handled inside the script) ──────
        logger.info("[node_add] step=attach_and_join container=%s lan=%d", name, lan)
        t0 = time.perf_counter()
        ok, ip, mac, stdout2, stderr2 = self._run_script(
            SCRIPTS_DIR / "add_network_storage_node.sh",
            [
                "--lan", str(lan),
                "--name", name,
                "--rs-name", rs_name,
                "--primary", primary_container,
                "--port", str(port),
            ],
        )
        timings.network_attach_s = time.perf_counter() - t0
        timings.total_s = time.perf_counter() - t_total

        if not ok:
            self._cleanup_container(name)
            return NodeResult(
                False, name, None, None, timings, NodeOperationState.FAILED,
                stdout + stdout2, stderr + stderr2,
            )

        logger.debug("[node_add] attach+join complete  container=%s ip=%s mac=%s", name, ip, mac)
        return NodeResult(True, name, ip, mac, timings, NodeOperationState.DONE,
                          stdout + stdout2, stderr + stderr2)

    def log_timings(self, result: NodeResult) -> None:
        t = result.timings
        logger.info(
            "[node_add] timing  container=%s  docker_run=%.2fs  net_attach=%.2fs"
            "  rs_join=%.2fs  total=%.2fs  state=%s",
            result.container_name,
            t.docker_run_s, t.network_attach_s,
            t.replica_set_join_s, t.total_s,
            result.state.name,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _container_state(self, name: str) -> str | None:
        """Return the Docker container status string, or None if not found."""
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Status}}", name],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            return None
        return result.stdout.strip()

    def _docker_run_server(self, name: str) -> tuple[bool, str, str]:
        state = self._container_state(name)
        if state == "running":
            logger.info("[node_add] container %s already running — skipping docker run", name)
            return True, "", ""
        if state is not None:
            logger.info("[node_add] removing stale container %s (state=%s)", name, state)
            self._cleanup_container(name)
        cmd = ["docker", "run", "-dit", "--network", "none", "--name", name, "edge_server"]
        return self._run_cmd(cmd)

    def _docker_run_storage(self, name: str, rs_name: str, port: int) -> tuple[bool, str, str]:
        state = self._container_state(name)
        if state == "running":
            logger.info("[node_add] container %s already running — skipping docker run", name)
            return True, "", ""
        # Always clean up: removes stale container (if any) AND orphaned volume
        # whose replica-set ID would otherwise clash with rs.add().
        self._cleanup_container(name)
        vol = f"{name}-data"
        cmd = [
            "docker", "run", "-dit",
            "--network", "none",
            "--name", name,
            "-v", f"{vol}:/data/db",
            "edge_storage_server",
            "mongod", "--replSet", rs_name, "--bind_ip_all", "--port", str(port),
        ]
        return self._run_cmd(cmd)

    def _run_script(self, script: Path, args: list[str]) -> tuple[bool, str | None, str | None, str, str]:
        cmd = ["/bin/bash", str(script), *args]
        logger.debug("[node_add] running script: %s", " ".join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True)
        ip:  str | None = None
        mac: str | None = None
        m = _RESULT_IP_RE.search(result.stdout)
        if m:
            ip = m.group(1)
        m = _RESULT_MAC_RE.search(result.stdout)
        if m:
            mac = m.group(1)
        ok = result.returncode == 0
        if ok:
            logger.debug("[node_add] script ok  ip=%s mac=%s\n%s", ip, mac, result.stdout)
        else:
            logger.error(
                "[node_add] script failed  cmd=%s\n--- stdout ---\n%s\n--- stderr ---\n%s",
                " ".join(cmd), result.stdout, result.stderr,
            )
        return ok, ip, mac, result.stdout, result.stderr

    def _run_cmd(self, cmd: list[str]) -> tuple[bool, str, str]:
        logger.debug("[node_add] running cmd: %s", " ".join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True)
        ok = result.returncode == 0
        if ok:
            logger.debug("[node_add] cmd ok: %s", result.stdout.strip())
        else:
            logger.error(
                "[node_add] command failed  cmd=%s\nstdout=%s\nstderr=%s",
                " ".join(cmd), result.stdout, result.stderr,
            )
        return ok, result.stdout, result.stderr

    def _cleanup_container(self, name: str) -> None:
        """Best-effort stop + remove + volume removal. Does not raise on failure."""
        logger.debug("[node_add] cleanup: stopping and removing container %s", name)
        for cmd in (
            ["docker", "stop", name],
            ["docker", "rm", name],
            ["docker", "volume", "rm", f"{name}-data"],
        ):
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.debug("[node_add] cleanup %s: %s", " ".join(cmd), result.stderr.strip())
