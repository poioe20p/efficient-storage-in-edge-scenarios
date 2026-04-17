import logging
import os

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

from .elasticity.elasticity import ElasticityManager
from .telemetry.models import TelemetrySummary
from .telemetry.zmq_source import ZmqTelemetrySource
from .topology.topology import TopologyMixin
from .vip_routing import VipRoutingMixin
from .scaling_policy import ScalingPolicy
from .node_registry import DynamicNodeRegistry
from .control_events import ControlEventDispatcher

# Required so os-ken's app manager loads os_ken.topology.switches.
# topology.py imports os_ken.topology.api (which calls require_app with api_style=True),
# but that sets _REQUIRED_APP on the topology module, not on this entry-point module.
# The app manager resolves dependencies from sys.modules[cls.__module__], so it must
# be declared here explicitly.
_REQUIRED_APP = ['os_ken.topology.switches']

logger = logging.getLogger('os_ken.main_n1')


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

        # Thread 2 — ZMQ subscriber
        self._telemetry = ZmqTelemetrySource(
            endpoints=_aggregator_endpoints + _peer_endpoints,
            on_update=self._on_telemetry_update,
            on_topology_update=self.on_topology_update,
        )
        self._telemetry.start()

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
            summary, self._node_registry, self.add_storage_mac,
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

        # 4. Fallback VIP promotion
        self._control_events.promote_storage_from_telemetry(
            summary, self._node_registry,
            self._local_storage_macs_n1, self._local_storage_macs_n2,
            self.add_storage_mac,
        )

        try:
            lan = int(summary.network_id.replace("lan", ""))
        except ValueError:
            logger.warning("could not parse LAN from network_id=%s", summary.network_id)
            return

        # 5. Absent node detection → alert submission
        for mac in self._node_registry.detect_absent(summary):
            if self._elasticity.has_pending_drain(mac):
                logger.info("[scale-down] pending drain for mac=%s — submitting CleanupComputeAlert", mac)
                self._elasticity.submit_cleanup_compute(mac)
            else:
                alert = self._node_registry.build_scale_down_alert(mac)
                if alert:
                    logger.info("[scale-down] submitting alert: %s", alert)
                    self._elasticity.submit(alert)

        if self._elasticity.is_busy():
            logger.debug("[scale-down] elasticity manager is busy — skipping scaling evaluation")
            return

        ds = summary.domain_summary

        # 6. Scale-up evaluation
        dynamic_storage_count = self._node_registry.count_dynamic("storage")
        dynamic_compute_count = self._node_registry.count_dynamic("compute")
        peer_network_id = "lan2" if summary.network_id == "lan1" else "lan1"
        peer_summary = self._telemetry.get_latest(peer_network_id)
        peer_ds = peer_summary.domain_summary if peer_summary and peer_summary.domain_summary else None

        for alert in self._scaling_policy.evaluate_scale_up(
            ds,
            lan,
            summary.network_id,
            dynamic_storage_count,
            dynamic_compute_count,
            peer_ds,
        ):
            self._elasticity.submit(alert)

        # 7. Scale-down evaluation (with cooldown gating)
        remaining = self._scaling_policy.compute_cooldown_remaining()
        if remaining > 0:
            logger.debug("[scale-down] compute within %.0fs cooldown — skipping", remaining)
        else:
            if self._scaling_policy.evaluate_scale_down_compute(ds):
                node = self._node_registry.find_last_dynamic("compute")
                if node:
                    logger.info(
                        "[scale-down] compute underutilisation — removing %s", node.name)
                    alert = self._node_registry.build_scale_down_alert(node.mac)
                    if alert:
                        self._elasticity.submit(alert)
                self._scaling_policy.clear_scale_down_compute_window()

        remaining = self._scaling_policy.storage_cooldown_remaining()
        if remaining > 0:
            logger.debug("[scale-down] storage within %.0fs cooldown — skipping", remaining)
        else:
            if self._scaling_policy.evaluate_scale_down_storage(ds):
                node = self._node_registry.find_last_dynamic("storage")
                if node:
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
