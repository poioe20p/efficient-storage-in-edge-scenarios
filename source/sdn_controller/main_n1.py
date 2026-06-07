import logging
import os
import time
from dataclasses import dataclass

from os_ken.base import app_manager
from os_ken.controller import ofp_event
from os_ken.controller.handler import (
    CONFIG_DISPATCHER,
    MAIN_DISPATCHER,
    set_ev_cls,
)
from os_ken.lib.packet import ethernet, ether_types, packet
from os_ken.ofproto import ofproto_v1_3
from os_ken import cfg

from .elasticity.elasticity import ComputeAlert, DataAlert, ElasticityManager, PrepareStandbyStorageAlert, CleanupReserveAlert
from .elasticity.node_common import NodeInfo
from .selective_sync.promotion import PromotionCoordinator
from .selective_sync.state_publisher import CoordinatorStatePublisher
from .telemetry.models import ServerSummary, TelemetrySummary
from .telemetry.zmq_source import ZmqTelemetrySource
from .topology.topology import TopologyMixin
from .vip_routing import VipRoutingMixin
from .scaling_policy import ScalingPolicy
from .scaling_config import (
    _NODE_BIRTH_GRACE_S,
    _SCALE_DOWN_CANDIDATE_MAX_STALENESS_S,
    _STORAGE_PERSISTENT_RESERVE_ENABLED,
    _STORAGE_RESERVE_PENDING_WINDOWS,
)
from .node_registry import DynamicNodeRegistry
from .control_events import ControlEventDispatcher

import requests

# Required so os-ken's app manager loads os_ken.topology.switches.
# topology.py imports os_ken.topology.api (which calls require_app with api_style=True),
# but that sets _REQUIRED_APP on the topology module, not on this entry-point module.
# The app manager resolves dependencies from sys.modules[cls.__module__], so it must
# be declared here explicitly.
_REQUIRED_APP = ['os_ken.topology.switches']

logger = logging.getLogger('os_ken.main_n1')


@dataclass(frozen=True)
class _ComputeScaleDownCandidate:
    node: NodeInfo
    summary: ServerSummary
    staleness_s: float
    age_s: float


class KenLearnAndLog(VipRoutingMixin, TopologyMixin, app_manager.OSKenApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        cfg.CONF.observe_links = True
        cfg.CONF.observe_hosts = True
        
        super(KenLearnAndLog, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.enable_reactive_learning = True
        self.datapaths = []
        self._datapath_by_id = {}
        self._lan_id = os.environ.get("LAN_ID", "lan1")

        _aggregator_endpoints = [
            ep.strip()
            for ep in os.environ.get(
                "AGGREGATOR_ENDPOINTS", "tcp://10.0.0.5:5556,tcp://10.0.1.5:5556"
            ).split(",")
            if ep.strip()
        ]
        _peer_endpoints = [
            ep.strip()
            for ep in os.environ.get("PEER_TOPOLOGY_ENDPOINTS", "").split(",")
            if ep.strip()
        ]
        logger.info("aggregator endpoints: %s", _aggregator_endpoints)
        logger.info("peer topology endpoints: %s", _peer_endpoints)

        # Thread 3 — must be created before ZmqTelemetrySource
        self._elasticity = ElasticityManager(topology_mixin=self)
        self._elasticity.start()

        # ── Composed components (Thread 2 only) ──
        self._scaling_policy = ScalingPolicy()
        self._node_registry = DynamicNodeRegistry()
        self._control_events = ControlEventDispatcher()

        # ── Tier 1 selective-sync coordinator wiring ──
        # The coordinator needs a live reference to the elasticity manager
        # (for ``submit``), so we build it here and inject it back via the
        # elasticity manager's late-attach setters.
        self._selective_sync_coordinator = PromotionCoordinator(
            my_lan=self._lan_id,
            elasticity=self._elasticity,
            broadcast_tier1_manifest=self._broadcast_tier1_manifest,
            resolve_owner_primary=self._resolve_owner_primary,
        )
        self._elasticity.attach_selective_sync_coordinator(
            self._selective_sync_coordinator)
        self._elasticity.attach_tier1_broadcaster(
            self._broadcast_tier1_manifest)

        # Coordinator-state PUB socket — emits one frame per window after
        # evaluate(). No-op when COORDINATOR_STATE_PUB_PORT=0. Subscribed
        # by collect_resource_stats.py to populate resource_stats.csv
        # coord_* columns.
        self._coordinator_state_publisher = CoordinatorStatePublisher()

        # Thread 2 — ZMQ subscriber
        self._telemetry = ZmqTelemetrySource(
            endpoints=_aggregator_endpoints + _peer_endpoints,
            on_update=self._on_telemetry_update,
            on_topology_update=self.on_topology_update,
        )
        self._telemetry.start()

    # ------------------------------------------------------------------
    # Tier 1 coordinator closures
    # ------------------------------------------------------------------

    def _resolve_owner_primary(self, owner_lan: str) -> tuple[str, str] | None:
        """Look up ``(rs_name, "host:port")`` for the peer-LAN RS primary.

        Thin wrapper around :meth:`TopologyMixin.resolve_peer_primary` that
        maps a consumer-facing ``owner_lan`` (e.g. ``"lan1"``) to the peer
        network id used by the topology fabric (``"lan1"``/``"lan2"``).
        Returns ``None`` until the peer controller has published role info.
        """
        return self.resolve_peer_primary(owner_lan)

    def _broadcast_tier1_manifest(self, network_id: str, manifest: dict) -> None:
        """PUT ``/tier1_manifest`` on every compute node in ``network_id``.

        Resolves IPs from the topology mixin's ``_mac_to_ip`` map, filtered
        by ``_local_server_macs`` so only edge-server nodes receive the
        manifest (storage / selective-storage / OS-Ken / OVS nodes don't
        run the edge Flask app).
        """
        for mac in list(self._local_server_macs):
            ip = self._mac_to_ip.get(mac)
            if not ip:
                continue
            url = f"http://{ip}:5000/tier1_manifest"
            try:
                requests.put(url, json=manifest, timeout=2.0)
            except requests.RequestException as exc:
                logger.warning("[tier1] manifest PUT %s failed: %s", url, exc)

    def _promote_storage_backend(self, mac: str, domain: str) -> None:
        self.add_storage_mac(mac, domain)
        self.mark_storage_backend_warm(mac, domain)
        logger.info(
            "[vip_data] promoted storage mac=%s domain=%s",
            mac,
            domain,
        )

    # ── Storage persistent reserve helpers ──────────────────────────────

    def _on_reserve_ready(self, mac: str) -> None:
        """Callback invoked by ControlEventDispatcher when a reserved node reaches SECONDARY."""
        self._node_registry.mark_storage_reserve_ready(mac)

    def _try_prepare_storage_reserve(self, summary: TelemetrySummary, lan: int) -> None:
        """Submit reserve preparation when the slot is NONE and the primary is available."""
        if not _STORAGE_PERSISTENT_RESERVE_ENABLED:
            return
        if not self._node_registry.should_prepare_storage_reserve(lan):
            return
        # Guard: need a visible PRIMARY to admit a new member
        if not any(ss.member_state == "PRIMARY" for ss in summary.storage_servers.values()):
            logger.debug("[reserve] no PRIMARY visible for lan=%d — skipping reserve prep", lan)
            return

        self._elasticity.submit(
            PrepareStandbyStorageAlert(
                lan=lan,
                network_id=summary.network_id,
                rs_name=f"rs_net{lan}",
                primary_container=f"edge_storage_server_n{lan}",
            )
        )
        self._node_registry.mark_storage_reserve_prepare_submitted(lan)

    def _handle_storage_reserve_trigger(self, summary: TelemetrySummary, lan: int, reason: str) -> bool:
        """Route a same-LAN storage trigger through the reserve model.

        Returns True if the trigger was handled by the reserve (activating or
        waiting), meaning the caller should NOT submit a separate DataAlert.
        Returns False if the reserve model is disabled — caller should fall
        through to normal Thread 3 submission.
        """
        if not _STORAGE_PERSISTENT_RESERVE_ENABLED:
            return False

        slot = self._node_registry.get_storage_reserve_slot(lan)

        if slot.state == "READY_RESERVED":
            info = self._node_registry.consume_ready_storage_reserve(lan)
            if info is None:
                logger.warning("[reserve] READY_RESERVED but consume returned None for lan=%d", lan)
                return False
            # Activate: add to VIP, clear standby flag, record activation.
            self._promote_storage_backend(info.mac, f"n{lan}")
            info.standby_reserved = False
            self._scaling_policy.record_storage_activation()
            logger.info("[reserve] activated lan=%d name=%s ip=%s mac=%s reason=%s",
                        lan, info.name, info.ip, info.mac, reason)
            # Immediately start preparing the next reserve.
            self._try_prepare_storage_reserve(summary, lan)
            return True

        # Reserve is PREPARING or NONE — latch pending and wait.
        self._node_registry.latch_storage_reserve_activation(lan, reason, _STORAGE_RESERVE_PENDING_WINDOWS)
        # If NONE, also submit preparation now.
        self._try_prepare_storage_reserve(summary, lan)
        return True

    def _pick_compute_scale_down_candidate(self) -> NodeInfo | None:
        now_wall = time.time()
        now_mono = time.monotonic()
        eligible: list[_ComputeScaleDownCandidate] = []

        for node in self._node_registry.list_dynamic("compute"):
            if self._elasticity.has_pending_drain(node.mac):
                logger.debug(
                    "[scale-down] compute candidate skip name=%s mac=%s reason=pending_drain",
                    node.name,
                    node.mac,
                )
                continue

            server = self._server_stats.get(node.mac)
            if server is None:
                logger.debug(
                    "[scale-down] compute candidate skip name=%s mac=%s reason=no_cached_server_summary",
                    node.name,
                    node.mac,
                )
                continue

            staleness_s = max(0.0, now_wall - server.last_report_ts)
            if staleness_s > _SCALE_DOWN_CANDIDATE_MAX_STALENESS_S:
                logger.debug(
                    "[scale-down] compute candidate skip name=%s mac=%s reason=stale staleness=%.1fs",
                    node.name,
                    node.mac,
                    staleness_s,
                )
                continue

            if server.state != "active":
                logger.debug(
                    "[scale-down] compute candidate skip name=%s mac=%s reason=state state=%s",
                    node.name,
                    node.mac,
                    server.state,
                )
                continue

            age_s = self._node_registry.node_age_s(node.mac, now_mono)
            if age_s < _NODE_BIRTH_GRACE_S:
                logger.debug(
                    "[scale-down] compute candidate skip name=%s mac=%s reason=too_young age=%.1fs",
                    node.name,
                    node.mac,
                    age_s,
                )
                continue

            eligible.append(
                _ComputeScaleDownCandidate(
                    node=node,
                    summary=server,
                    staleness_s=staleness_s,
                    age_s=age_s,
                )
            )

        if not eligible:
            logger.info(
                "[scale-down] compute underutilisation but no graceful candidate is eligible"
            )
            return None

        eligible.sort(key=lambda item: (
            item.summary.request_count,
            item.summary.avg_cpu_percent,
            item.summary.avg_time_proc_ms,
            -item.summary.last_report_ts,
        ))

        chosen = eligible[0]
        logger.info(
            "[scale-down] compute candidate selected name=%s mac=%s req=%d cpu=%.2f proc=%.2f stale=%.1fs age=%.1fs",
            chosen.node.name,
            chosen.node.mac,
            chosen.summary.request_count,
            chosen.summary.avg_cpu_percent,
            chosen.summary.avg_time_proc_ms,
            chosen.staleness_s,
            chosen.age_s,
        )
        return chosen.node

    def _on_telemetry_update(self, summary: TelemetrySummary) -> None:
        """Thread 2 callback — thin mediator that orchestrates composed components."""
        if summary.network_id != self._lan_id:
            logger.debug("ignoring telemetry for %s (this controller owns %s)",
                         summary.network_id, self._lan_id)
            return

        # 1. Sync node tracking (Thread 3 → Thread 2)
        self._node_registry.sync(self._elasticity)

        # 2. Dispatch control events
        self._control_events.process_drain_events(summary, self._elasticity)
        self._control_events.process_secondary_events(
            summary, self._node_registry, self._promote_storage_backend,
            on_reserve_ready_fn=self._on_reserve_ready,
        )

        # Mini-summaries (control event pass-throughs) have empty server dicts.
        if not summary.servers and not summary.storage_servers:
            return

        # Guard: domain_summary is Optional (None in mini-summaries, but the
        # mini-summary early-return above should catch those).
        if summary.domain_summary is None:
            logger.warning("non-mini summary with domain_summary=None — skipping scaling")
            return

        # 3. Observability
        self._log_and_update_stats(summary)

        # 3b. Sync local RS roles from this window's storage telemetry so the
        #     next topology snapshot advertises accurate ``storage_roles``,
        #     and run the Tier 1 promotion coordinator.
        self.sync_storage_roles(summary.storage_servers)
        self._selective_sync_coordinator.evaluate(summary)
        self._coordinator_state_publisher.publish(
            summary.network_id,
            summary.window_end,
            self._selective_sync_coordinator.snapshot(),
        )

        # 4. Fallback VIP promotion
        self._control_events.promote_storage_from_telemetry(
            summary, self._node_registry,
            self._local_storage_macs_n1, self._local_storage_macs_n2,
            self._promote_storage_backend,
            on_reserve_ready_fn=self._on_reserve_ready,
        )

        try:
            lan = int(summary.network_id.replace("lan", ""))
        except ValueError:
            logger.warning("could not parse LAN from network_id=%s", summary.network_id)
            return

        # 4b. Process reserve prepare failures (Thread 3 → Thread 2 outcome).
        # Per-LAN drain — this controller only consumes its own LAN's failures.
        for _ in self._elasticity.drain_reserve_prepare_failures(lan):
            self._node_registry.mark_storage_reserve_prepare_failed(lan)
            logger.info("[reserve] replenish_next_cycle lan=%d after prepare failure", lan)

        # 4c. Maintain persistent storage reserve — prepare if missing,
        #     tick pending activation, and auto-activate if ready.
        self._try_prepare_storage_reserve(summary, lan)
        slot = self._node_registry.get_storage_reserve_slot(lan)

        # Tick the bounded carry-forward budget.
        if slot.activation_pending and slot.state != "READY_RESERVED":
            expired = self._node_registry.tick_storage_reserve_pending_activation(lan)
            if expired:
                self._node_registry.clear_storage_reserve_pending_activation(lan)
                logger.info("[reserve] pending_expired lan=%d — clearing activation intent", lan)

        if slot.state == "READY_RESERVED" and slot.activation_pending:
            self._handle_storage_reserve_trigger(summary, lan, slot.pending_reason or "pending")

        # 5. Absent node detection → alert submission
        for mac in self._node_registry.detect_absent(summary):
            if self._elasticity.has_pending_drain(mac):
                logger.info("[scale-down] pending drain for mac=%s — submitting Phase B cleanup", mac)
                self._elasticity.submit_cleanup(mac)
            else:
                # Check if the absent node is the reserve — handle as reserve loss.
                info = self._node_registry.get_node_info(mac)
                if info and info.standby_reserved:
                    # 1. Clear the reserve slot first (while node is still in registry)
                    #    so replenish can start on the next maintenance cycle.
                    #    Pending activation is preserved for carry-forward.
                    self._node_registry.mark_storage_reserve_lost(mac)
                    # 2. Then unregister from tracking.
                    self._node_registry.unregister_reserved_node(mac)
                    # 3. Submit immediate-terminate cleanup to Thread 3.
                    self._elasticity.submit_cleanup_reserve(
                        CleanupReserveAlert(
                            lan=info.lan,
                            mac=info.mac,
                            container_name=info.name,
                            ip=info.ip or "",
                            rs_name=info.rs_name or "",
                            primary_container=info.primary_container or "",
                            port=info.port or 27018,
                        )
                    )
                    logger.info("[reserve] cleanup_submitted lan=%d mac=%s", info.lan, info.mac)
                    # Do NOT retry preparation here — next-cycle maintenance will decide.
                    continue
                alert = self._node_registry.build_scale_down_alert(mac)
                if alert:
                    logger.info("[scale-down] submitting alert: %s", alert)
                    self._elasticity.submit(alert)

        ds = summary.domain_summary

        # 5. Scale-up evaluation
        dynamic_storage_count = self._node_registry.count_dynamic("storage")
        registry_dynamic_compute_count = self._node_registry.count_dynamic("compute")
        pending_compute_drain_count = self._elasticity.pending_compute_drain_count()
        effective_dynamic_compute_count = max(
            0,
            registry_dynamic_compute_count - pending_compute_drain_count,
        )
        peer_network_id = "lan2" if summary.network_id == "lan1" else "lan1"
        peer_summary = self._telemetry.get_latest(peer_network_id)
        peer_ds = peer_summary.domain_summary if peer_summary and peer_summary.domain_summary else None

        compute_blocked = self._elasticity.blocks_compute_scale_up()
        storage_blocked = self._elasticity.blocks_storage_scale_up()

        if self._elasticity.has_active_operation():
            logger.debug("[scale-up] elasticity manager is busy — skipping")
        else:
            if compute_blocked:
                logger.debug("[scale-up] compute blocked by active elasticity operation — skipping")
            if storage_blocked:
                logger.debug("[scale-up] storage blocked by pending storage drain — skipping")

            for alert in self._scaling_policy.evaluate_scale_up(
                ds,
                lan,
                summary.network_id,
                dynamic_storage_count,
                effective_dynamic_compute_count,
                peer_ds,
                allow_compute=not compute_blocked,
                allow_storage=not storage_blocked,
            ):
                # ── Storage persistent reserve: same-LAN DataAlert → activate reserve first ──
                if isinstance(alert, DataAlert) and not getattr(alert, "cross_lan_rs", False):
                    if self._handle_storage_reserve_trigger(summary, alert.lan, "load"):
                        continue  # Reserve handled it — do not submit a raw DataAlert.

                # Dormant Tier 2 supersede hook. Drains any active Tier 1 for the
                # same (owner_lan → consumer_lan) direction *before* the Tier 2
                # alert lands. Today ``DataAlert`` is always same-LAN (adds a
                # secondary to ``rs_net{lan}``) and leaves ``cross_lan_rs=False``,
                # so this branch is never taken. See
                # docs/operation/elasticy_manager/implementation/tier1_selective_sync/event_protocol.md §2.4.
                if (isinstance(alert, DataAlert)
                        and getattr(alert, "cross_lan_rs", False)
                        and getattr(alert, "owner_lan", None) is not None):
                    self._selective_sync_coordinator.drain(
                        alert.owner_lan, reason="tier2_supersedes")
                self._elasticity.submit(alert)
                if (isinstance(alert, ComputeAlert)
                        and self._elasticity.has_pending_compute_drain()):
                    logger.info(
                        "[scale-up] compute triggered with %d pending compute drain(s) — submitting lower-priority cancel",
                        pending_compute_drain_count,
                    )
                    self._elasticity.submit_cancel_compute_drain()

        if self._elasticity.is_busy():
            logger.debug("[scale-down] elasticity manager is busy — skipping scaling evaluation")
            return

        # 6. Scale-down evaluation (with cooldown gating)
        remaining = self._scaling_policy.compute_cooldown_remaining()
        if remaining > 0:
            logger.debug("[scale-down] compute within %.0fs cooldown — skipping", remaining)
        else:
            if self._scaling_policy.evaluate_scale_down_compute(ds):
                node = self._pick_compute_scale_down_candidate()
                if node:
                    logger.info(
                        "[scale-down] compute underutilisation — removing %s", node.name)
                    alert = self._node_registry.build_scale_down_alert(node.mac)
                    if alert:
                        self._elasticity.submit(alert)
                else:
                    logger.info(
                        "[scale-down] compute underutilisation but no graceful candidate is eligible — clearing current window"
                    )
                self._scaling_policy.clear_scale_down_compute_window()

        remaining = self._scaling_policy.storage_cooldown_remaining()
        if remaining > 0:
            logger.debug("[scale-down] storage within %.0fs cooldown — skipping", remaining)
        else:
            if self._scaling_policy.evaluate_scale_down_storage(ds):
                node = self._node_registry.find_last_dynamic("storage")
                if node:
                    # Reserve-floor guard: do not scale down below active+reserve floor.
                    if not self._node_registry.can_scale_down_storage(node.mac, lan):
                        logger.info(
                            "[scale-down] storage underutilisation but reserve floor blocks removal of %s",
                            node.name,
                        )
                        self._scaling_policy.clear_scale_down_storage_window()
                    else:
                        logger.info(
                            "[scale-down] storage underutilisation — removing %s", node.name)
                        alert = self._node_registry.build_scale_down_alert(node.mac)
                        if alert:
                            self._elasticity.submit(alert)
                self._scaling_policy.clear_scale_down_storage_window()

    def _log_and_update_stats(self, summary: TelemetrySummary) -> None:
        """Print domain summary metrics and push per-server stats to Thread 1."""
        ds = summary.domain_summary
        print(
            f"[telemetry] network={summary.network_id} "
            f"proc_ms={ds.avg_time_proc_ms:.1f} "
            f"db_ms={ds.avg_time_db_ms:.1f} "
            f"requests={ds.total_requests} "
            f"cpu={ds.average_cpu_percent:.1f}%"
        )
        self.update_server_stats(summary.servers)
        self.update_storage_stats(summary.storage_servers)


    def _install_flow(self, datapath, priority, match, actions, *,
                      idle_timeout=0, hard_timeout=0, cookie=0, flags=None):
        ofproto = datapath.ofproto
        if flags is None:
            flags = ofproto.OFPFF_SEND_FLOW_REM
                
        instructions = [
            datapath.ofproto_parser.OFPInstructionActions(
                ofproto.OFPIT_APPLY_ACTIONS,
                actions,
            )
        ]
        mod = datapath.ofproto_parser.OFPFlowMod(
            datapath=datapath,
            priority=priority,
            match=match,
            instructions=instructions,
            idle_timeout=idle_timeout,
            hard_timeout=hard_timeout,
            cookie=cookie,
            flags=flags,
            command=ofproto.OFPFC_ADD,
        )
        datapath.send_msg(mod)


    def add_flow(self, datapath, in_port, dst, src, actions):
        """Default reactive learning-switch rule installer."""
        parser = datapath.ofproto_parser
        match = parser.OFPMatch(
            in_port=in_port,
            eth_dst=dst,
            eth_src=src,
        )
        
        logger.debug("reactive flow: dpid=%s in_port=%s src=%s dst=%s", datapath.id, in_port, src, dst)
        self._install_flow(
            datapath,
            priority=10,
            match=match,
            actions=actions,
            # idle_timeout=int(getattr(self, "l2_flow_idle_timeout_sec", 0) or 0),
            flags=datapath.ofproto.OFPFF_SEND_FLOW_REM,
        )


    # Event handler for switch features. This method is triggered when a switch connects to the controller.
    # @set_ev_cls decorator tells OS-Ken that the method "switch_features_handler" should be invoked when an EventOFPSwitchFeatures event is received.
    # CONFIG_DISPATCHER means this event is handled after the switch enters the configuration phase (after the initial handshake between switch and controller).
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, event):
        """Install the table-miss flow entry when the switch connects. 
        At first switch is configured to flood all packets in order to learn MAC addresses."""
    
        # Extract the datapath object, which represents in the controller enviroment the switch that is communicating with the controller.
        # The datapath contains information about the switch (datapath ID, methods to send messages, etc.)
        datapath = event.msg.datapath

        # ofproto represents the OpenFlow protocol, which includes constants (like action types and message types).
        ofproto = datapath.ofproto

        # The parser helps in creating OpenFlow messages such as matches, actions, flow mods, etc.
        parser = datapath.ofproto_parser
        
        # Register datapath early so proactive VIP rules can find the edge switch.
        self._datapath_by_id[datapath.id] = (datapath, datapath.id)

        if not any(getattr(dp, "id", None) == datapath.id for dp in self.datapaths):
            self.datapaths.append(datapath)

        # Create a match object with no specific fields, meaning it will match all packets (wildcard match).
        # This is the default behavior of a hub, which forwards all traffic.
        match = parser.OFPMatch()
        
        # Create an action to output the packets to the controller and not buffer them.
        # This ensures that all packets that do not match any flow entries are sent to the controller
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
        
        # Create a flow modification message to install the "table-miss" flow entry in the switch.
        instructions = [
            parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)
        ]
        mod = datapath.ofproto_parser.OFPFlowMod(
            datapath=datapath, # The switch this flow is being installed on.
            priority=0, # The lowest priority for the table-miss flow entry.
            match=match, # specifies the matching rule (matches all packets here because the match is empty and any traffic becomes selected).
            instructions=instructions, # Apply actions through the OpenFlow 1.3 instruction pipeline.
            flags=ofproto.OFPFF_SEND_FLOW_REM # flag that tells the switch to notify the controller when the flow is removed.
        )
        datapath.send_msg(mod)
        
        logger.info("switch connected: dpid=%s, table-miss flow installed", datapath.id)


    # Packet In Handler
    # This method is triggered when a packet is received by the switch.
    # It learns MAC addresses and their associated ports, logs the event, and forwards the packet.
    # The next time a packet with the same source and destination MAC addresses is received, it will be forwarded directly without flooding or 
    # involving the controller again.
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, event):
        """Learn MAC-port mappings, log the event, and forward the packet."""

        msg = event.msg  # Extract the message from the event
        datapath = msg.datapath  # Get the switch (datapath) that sent the message
        ofproto = datapath.ofproto  # Get the OpenFlow protocol constants for this datapath
        parser = datapath.ofproto_parser  # Get the OpenFlow message parser for creating messages
        in_port = msg.match["in_port"]  # Get the input port from which the packet was received
        
        pkt = packet.Packet(msg.data) # Create a Packet object from the incoming packet data
        eth = pkt.get_protocol(ethernet.ethernet) # Extract the Ethernet header from the message
        dst = eth.dst # Get the destination MAC address from the Ethernet header frame
        src = eth.src # Get the source MAC address from the Ethernet header frame
        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        # VIP interception — runs before L2 learning so VIP-destined packets
        # are not forwarded by L2 rules before DNAT is installed.
        self.snoop_arp(pkt)
        if self.handle_vip_packet_in(datapath, in_port, pkt, eth):
            return

        dpid_int = int(datapath.id)  # Datapath ID as integer for shard key routing
        self.mac_to_port.setdefault(dpid_int, {})  # Initialize mapping for this switch if absent
        
        # Learn a MAC address to avoid flooding next time.
        # Always update — handles the case where a container is replaced on a
        # different OVS port but retains the same MAC (elasticity retries).
        if self.mac_to_port[dpid_int].get(src) != in_port:
            logger.debug("MAC learned/updated: dpid=%s src=%s -> port=%s", dpid_int, src, in_port)
        self.mac_to_port[dpid_int][src] = in_port
        
        # Determine the output port for the destination MAC address    
        if dst in self.mac_to_port[dpid_int]:
            out_port = self.mac_to_port[dpid_int][dst]
        else:
            # Flood the packet if the destination MAC is unknown
            out_port = ofproto.OFPP_FLOOD

        # Create the action to forward the packet to the determined output port
        actions = [parser.OFPActionOutput(out_port)]

        # Install a flow entry to avoid future packet_in events for this flow
        if self.enable_reactive_learning and out_port != ofproto.OFPP_FLOOD:
            self.add_flow(datapath, in_port, dst, src, actions)
        
        data = None
        # If the packet is not buffered on the switch, include the packet data in the packet-out message
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        # Create a packet-out message to send the packet out of the switch
        out = datapath.ofproto_parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=data,
        )
        
        # Send the packet-out message to the switch
        datapath.send_msg(out)
        
        logger.debug(
            "packet_in: dpid=%s src=%s dst=%s in_port=%s out_port=%s",
            datapath.id, src, dst, in_port, out_port
        )
