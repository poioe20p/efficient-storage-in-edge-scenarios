"""Learning-switch style OS-Ken app that logs packet events to MongoDB."""
import eventlet

eventlet.monkey_patch()

from datetime import datetime
from os_ken.base import app_manager
from os_ken.controller import ofp_event
from os_ken.controller.handler import (
    CONFIG_DISPATCHER,
    MAIN_DISPATCHER,
    set_ev_cls,
)
from os_ken.lib.packet import ethernet, ether_types, packet
from os_ken.ofproto import ofproto_v1_3
from sdn_controller.models.mongodb_host import MongodbHost
from sdn_controller.repositories.repositories.event import EventRepository
from sdn_controller.repositories.models.event import Event


class KenLearnAndLog(app_manager.OSKenApp):
    """Simple layer-2 learning switch with optional MongoDB logging."""
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(KenLearnAndLog, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.host_n2_event_repository = EventRepository(
            MongodbHost(host="10.0.1.4", port=27018, database_name="app_db").get_simple_connection_string(
                add_app=True
            )
        )

        self._zone_size = 1000000000
        self._zone_order = ["shard_zone_rs_net2"]
        self._zone_state = {}
        start = 0
        for zone in self._zone_order:
            self._zone_state[zone] = {
                "switch_dpid": None,
                "next_offset": 0,
                "range_start": start,
                "lock": eventlet.semaphore.Semaphore(),
            }
            start += self._zone_size
        self.datapath_zone_map = {}
        self._connected_switches = 0
        self.enable_reactive_learning = True

    def _install_flow(self, datapath, priority, match, actions, *,
                      idle_timeout=0, hard_timeout=0, cookie=0, flags=None):
        """Shared helper so subclasses can install arbitrary matches."""
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
        self._install_flow(
            datapath,
            priority=10,
            match=match,
            actions=actions,
            flags=datapath.ofproto.OFPFF_SEND_FLOW_REM,
        )
        
    def _assign_zone_to_switch(self, datapath_id: str) -> str:
        zone = self._zone_order[0]
        if self._zone_state[zone]["switch_dpid"] is None:
            self._zone_state[zone]["switch_dpid"] = datapath_id
        self.datapath_zone_map[datapath_id] = zone
        return zone

    def _zone_bounds(self, zone_name: str):
        state = self._zone_state.get(zone_name)
        if not state:
            return (0, 0)
        start = state["range_start"]
        return (start, start + self._zone_size)



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
        
        datapath_id_str = str(datapath.id)
        assigned_zone = self._assign_zone_to_switch(datapath_id_str)
        self._connected_switches += 1
        print(f"Datapath {datapath_id_str} mapped to {assigned_zone}.")
            
        

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
        
        dpid_int = int(datapath.id)  # Datapath ID as integer for shard key routing
        self.mac_to_port.setdefault(dpid_int, {})  # Initialize mapping for this switch if absent
        
        # Learn a MAC address to avoid flooding next time
        if src not in self.mac_to_port[dpid_int]:  # If the source MAC is not already tracked for this switch
            self.mac_to_port[dpid_int][src] = in_port
            # print("mac_to_port[%s]: %s", dpid_int, self.mac_to_port[dpid_int])
        
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
        
        datapath_id = str(datapath.id)
        zone_name = self.datapath_zone_map.get(datapath_id)
        if zone_name is None:
            print(f"No shard zone assignment for datapath {datapath_id}; skipping log")
            return
        event_payload = {
            "type": "packet_in",
            "src": src,
            "dst": dst,
            "in_port": in_port,
            "out_port": out_port,
            "created_ts": datetime.now().timestamp(),
            "ttl": datetime.now().timestamp() + (3 * 60),
        }
        self._queue_event_for_zone(zone_name, event_payload, datapath_id)


    def _queue_event_for_zone(self, zone_name: str, event_payload: dict, datapath_key: str):
        if zone_name != "shard_zone_rs_net2":
            print(f"Unknown shard zone '{zone_name}' for datapath {datapath_key}; skipping log")
            return

        event_repository = self.host_n2_event_repository
        label = "N2"

        eventlet.spawn_n(
            self._insert_event,
            event_repository,
            event_payload,
            label,
            datapath_key,
            zone_name,
        )

    def _insert_event(
        self,
        event_repository: EventRepository,
        event_payload: dict,
        label: str,
        datapath_key: str,
        zone_name: str,
    ):
        zone_state = self._zone_state.get(zone_name)
        if zone_state is None:
            print(
                f"Skipping Mongo insert {label}: shard zone {zone_name} not tracked"
            )
            return

        lock = zone_state["lock"]
        with lock:
            if zone_state["next_offset"] >= self._zone_size:
                print(
                    f"Shard zone {zone_name} exhausted; cannot log datapath {datapath_key}"
                )
                return

            shard_key = zone_state["range_start"] + zone_state["next_offset"]
            payload = dict(event_payload)
            payload.update(
                {
                    "datapath_id": datapath_key,
                    "shard_zone": zone_name,
                    "dpid": shard_key,
                }
            )

            try:
                event_payload = Event(**payload)
                event_repository.insert_event(event_payload)
            except Exception as exc:
                print(
                    f"Mongo insert {label} failed for {zone_name} (datapath {datapath_key}): {exc}"
                )
                return

            zone_state["next_offset"] += 1