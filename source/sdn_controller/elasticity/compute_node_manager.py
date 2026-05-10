"""
compute_node_manager.py — Timed, idempotent lifecycle for compute (edge_server) nodes.

Covers:
  - Spawning an edge_server container and attaching it to OVS (add_edge_server)
  - Two-phase graceful drain and removal of a compute node
      Phase A: initiate_drain   — discover veth, send HTTP drain signal
      Phase B: cleanup_compute_node — OVS teardown + docker rm
"""

from __future__ import annotations

import logging
import re
import subprocess
import time
from dataclasses import dataclass

from .node_common import (
    SCRIPTS_DIR,
    NodeOperationState,
    NodeResult,
    RemovalResult,
    RemovalTimings,
    StepTimings,
    _BaseNodeAdder,
)

logger = logging.getLogger("os_ken.node_manager")


@dataclass
class PendingDrain:
    """In-progress drain record. Created in Phase A, consumed in Phase B.

    Shared between compute (``node_type="compute"``) and Tier 1 selective-sync
    (``node_type="selective_storage"``) drain flows. Phase B dispatch in
    ``ElasticityManager.submit_cleanup`` routes on ``node_type``. Tier 1
    drains have no OVS veth attached to a DNAT/VIP pool, so ``veth`` is left
    empty for selective nodes and the script teardown path skips DNAT flush.
    """
    mac:            str
    veth:           str            # OVS-side veth name; "unknown" only if discovery failed, "" for selective
    container_name: str
    lan:            int
    initiated_ts:   float
    drain_signaled: bool = True    # False when drain HTTP call failed but veth is known
    ip:             str  = ""      # for IP release in Phase B cleanup
    node_type:      str  = "compute"   # "compute" | "selective_storage"
    owner_lan:      str | None = None   # selective only; source LAN whose data is mirrored


class ComputeNodeAdder(_BaseNodeAdder):
    """Stateless helper — each method is a self-contained, timed, idempotent lifecycle."""

    def add_edge_server(self, lan: int, name: str, ip: str | None = None, mac: str | None = None) -> NodeResult:
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
        ok, stdout, stderr = self._docker_run_server(name, lan)
        timings.docker_run_s = time.perf_counter() - t0

        if not ok:
            timings.total_s = time.perf_counter() - t_total
            return NodeResult(False, name, None, None, timings, NodeOperationState.FAILED, stdout, stderr)

        # ── Step 2: network attachment ────────────────────────────────────────
        logger.info("[node_add] step=attach_network container=%s lan=%d", name, lan)
        t0 = time.perf_counter()
        script_args = ["--lan", str(lan), "--name", name]
        if ip:
            script_args += ["--ip", ip]
        if mac:
            script_args += ["--mac", mac]
        ok, ip, mac, stdout2, stderr2 = self._run_script(
            SCRIPTS_DIR / "add_network_node.sh",
            script_args,
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

    def initiate_drain(self, lan: int, name: str, mac: str) -> PendingDrain | None:
        """Phase A: discover veth (requires running container), send drain signal.

        Returns ``PendingDrain`` with ``drain_signaled=True`` when drain was
        acknowledged.  Returns ``PendingDrain`` with ``drain_signaled=False``
        when the veth was found but the drain HTTP call failed (container is
        dead — caller should submit CleanupComputeAlert immediately without
        waiting for a drain_complete ZMQ event).  Returns ``None`` only when
        veth discovery itself fails (container netns is already gone).
        """
        veth = self._discover_veth(name)
        if veth is None:
            logger.warning("[node_remove] cannot discover veth for %s — container netns is gone", name)
            return None

        drain_ok = False
        for attempt in range(1, 4):
            ok, _, _ = self._run_cmd([
                "docker", "exec", name,
                "curl", "-sf", "-X", "POST", "http://localhost:5000/drain",
            ])
            if ok:
                drain_ok = True
                break
            logger.warning("[node_remove] drain attempt %d/3 failed for %s", attempt, name)

        if not drain_ok:
            logger.warning(
                "[node_remove] all drain attempts failed for %s (veth=%s) — will cleanup immediately",
                name, veth,
            )
        else:
            logger.info("[node_remove] drain initiated for %s (veth=%s)", name, veth)

        return PendingDrain(
            mac=mac,
            veth=veth,
            container_name=name,
            lan=lan,
            initiated_ts=time.time(),
            drain_signaled=drain_ok,
        )

    def cleanup_compute_node(self, pending: PendingDrain) -> RemovalResult:
        """Phase B: stop container, flush flows, remove OVS port/veth, docker rm.

        Called after a drain_complete ZMQ event or telemetry-timeout fallback.
        The veth was discovered in Phase A and stored in ``pending``; the
        script receives it via ``--veth`` so it can skip nsenter discovery
        (the container's netns is gone once it has exited).
        """
        timings = RemovalTimings()
        t_total = time.perf_counter()

        logger.info("[node_remove] cleanup_compute: container=%s mac=%s veth=%s",
                    pending.container_name, pending.mac, pending.veth)

        t0 = time.perf_counter()
        ok, _, _, stdout, stderr = self._run_script(
            SCRIPTS_DIR / "remove_network_node.sh",
            [
                "--lan",  str(pending.lan),
                "--name", pending.container_name,
                "--veth", pending.veth,
                "--mac",  pending.mac,
            ],
        )
        timings.network_cleanup_s = time.perf_counter() - t0
        timings.total_s = time.perf_counter() - t_total

        state = NodeOperationState.DONE if ok else NodeOperationState.FAILED
        if ok:
            logger.info("[node_remove] cleanup_compute done: container=%s", pending.container_name)
        else:
            logger.error("[node_remove] cleanup_compute FAILED: container=%s\nstdout=%s\nstderr=%s",
                         pending.container_name, stdout, stderr)
        return RemovalResult(ok, pending.container_name, pending.mac, timings, state, stdout, stderr)

    def cancel_drain(self, name: str) -> bool:
        """Cancel a previously started compute drain via the edge server API."""
        command = [
            "docker", "exec", name,
            "curl", "-sf", "--max-time", "2",
            "-X", "POST",
            "-H", "Content-Type: application/json",
            "-d", '{"command":"cancel"}',
            "http://localhost:5000/drain",
        ]
        for attempt in range(1, 3):
            ok, _, _ = self._run_cmd(command)
            if ok:
                logger.info("[node_remove] drain cancel acknowledged for %s", name)
                return True
            logger.warning("[node_remove] drain cancel attempt %d/2 failed for %s", attempt, name)

        return False

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _docker_run_server(self, name: str, lan: int) -> tuple[bool, str, str]:
        state = self._container_state(name)
        if state == "running":
            logger.info("[node_add] container %s already running — skipping docker run", name)
            return True, "", ""
        if state is not None:
            logger.info("[node_add] removing stale container %s (state=%s)", name, state)
            self._cleanup_container(name)
        cmd = [
            "docker", "run", "-dit",
            "--network", "none",
            "--name", name,
            "-e", f"LAN_ID=lan{lan}",
            "-e", f"CONTAINER_NAME={name}",
            # Dynamic nodes inherit HEARTBEAT_ENABLED=0 (the image default).
            # Lifecycle is handled by scale-down (graceful) + telemetry-window
            # absence timeout (failure). See
            # docs/operation/other/heartbeat_dynamic_node_gate_plan.md.
            "edge_server",
        ]
        return self._run_cmd(cmd)

    def _discover_veth(self, name: str) -> str | None:
        """Discover the OVS-side veth name for a running container via nsenter.

        Returns the veth interface name, or ``None`` if discovery fails
        (container's network namespace is already gone).
        """
        # Get container PID
        ok, stdout, _ = self._run_cmd(
            ["docker", "inspect", "-f", "{{.State.Pid}}", name]
        )
        if not ok or not stdout.strip():
            return None
        pid = stdout.strip()

        # Get the peer ifindex of the container's eth0
        peer_result = subprocess.run(
            ["sudo", "nsenter", "-t", pid, "-n",
             "ip", "link", "show", "eth0"],
            capture_output=True, text=True,
        )
        if peer_result.returncode != 0:
            return None
        m = re.search(r"@if(\d+)", peer_result.stdout)
        if not m:
            return None
        peer_ifindex = m.group(1)

        # Get OVS container PID
        ok2, stdout2, _ = self._run_cmd(
            ["docker", "inspect", "-f", "{{.State.Pid}}", "ovs"]
        )
        if not ok2 or not stdout2.strip():
            return None
        ovs_pid = stdout2.strip()

        # Find the link with that ifindex in the OVS netns
        ovs_result = subprocess.run(
            ["sudo", "nsenter", "-t", ovs_pid, "-n", "ip", "link", "show"],
            capture_output=True, text=True,
        )
        if ovs_result.returncode != 0:
            return None
        m2 = re.search(rf"^{re.escape(peer_ifindex)}:\s+(\S+?)[@:]",
                        ovs_result.stdout, re.MULTILINE)
        if not m2:
            return None
        return m2.group(1)
