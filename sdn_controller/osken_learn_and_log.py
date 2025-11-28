"""Learning-switch style OS-Ken app that logs packet events to MongoDB."""
import random
import eventlet
eventlet.monkey_patch()
from datetime import datetime
from pymongo import MongoClient
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

# This class defines a simple OS-Ken application that acts like a switch in an OpenFlow network and
# logs packet events to a MongoDB database.
class KenLearnAndLog(app_manager.OSKenApp):
    """Simple layer-2 learning switch with optional MongoDB logging."""
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(KenLearnAndLog, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        mongodb_host_n1 = MongodbHost(
            host="10.0.0.4",
            port=27018,
        )
        mongodb_host_n2 = MongodbHost(
            host="10.0.1.4",
            port=27018,
        )
        self.host_n1_conn = MongoClient(
            mongodb_host_n1.get_simple_connection_string(
                add_app=True
            ),
            connect=False
        )
        self.host_n2_conn = MongoClient(
            mongodb_host_n2.get_simple_connection_string(
                add_app=True
            ),
            connect=False
        )
        self._zone_size = 10000
        self._zone_order = ["shard_zone_rs_net1", "shard_zone_rs_net2"]
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

    def add_flow(self, datapath, in_port, dst, src, actions):
        # Get the OpenFlow protocol object for the given switch (datapath)
        ofproto = datapath.ofproto

        # Create a match objectE based on the input port, source MAC address (src), and destination MAC address (dst)
        match = datapath.ofproto_parser.OFPMatch(
            in_port=in_port,                      # Match the input port
            eth_dst=dst,                          # Match the destination MAC address (eth_dst = layer-2 destination)
            eth_src=src)                          # Match the source MAC address (eth_src = layer-2 source)

        # Create a flow modification message to add a new flow entry to the switch
        # The OFPFlowMod message includes match criteria, priority, timeout, and actions
        instructions = [
            datapath.ofproto_parser.OFPInstructionActions(
                ofproto.OFPIT_APPLY_ACTIONS,
                actions,
            )
        ]
        
        # Potencialmente guardar na db os flows adicionadas
        mod = datapath.ofproto_parser.OFPFlowMod(
            datapath=datapath,                    # The switch (datapath) to apply the flow modification
            match=match,                          # The match criteria defined above (in_port, src, dst)
            cookie=0,                             # Cookie identifier for tracking the flow (set to 0 in this case)
            command=ofproto.OFPFC_ADD,            # Command to add a new flow entry (OFPFC_ADD)
            idle_timeout=0,                       # No idle timeout (the flow will not expire due to inactivity)
            hard_timeout=0,                       # No hard timeout (the flow will not expire over time)
            priority=10,                          # Priority of the flow (higher values mean higher priority)
            flags=ofproto.OFPFF_SEND_FLOW_REM,    # Flag to send a Flow Removed message when the flow is deleted
            instructions=instructions             # Apply the actions via the instruction set (OpenFlow 1.3 requirement)
        )

        # Send the flow modification message to the switch (datapath)
        # This installs the flow entry into the switch's flow table
        datapath.send_msg(mod)
        
    def _assign_zone_to_switch(self, datapath_id: str) -> str:
        for zone in self._zone_order:
            if self._zone_state[zone]["switch_dpid"] is None:
                self._zone_state[zone]["switch_dpid"] = datapath_id
                self.datapath_zone_map[datapath_id] = zone
                return zone
        zone = random.choice(self._zone_order)
        print(
            "Warning: More than configured switches connected; reusing zone",
            zone,
        )
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
            print("mac_to_port[%s]: %s", dpid_int, self.mac_to_port[dpid_int])
        
        # Determine the output port for the destination MAC address    
        if dst in self.mac_to_port[dpid_int]:
            out_port = self.mac_to_port[dpid_int][dst]
        else:
            # Flood the packet if the destination MAC is unknown
            out_port = ofproto.OFPP_FLOOD

        # Create the action to forward the packet to the determined output port
        actions = [parser.OFPActionOutput(out_port)]

        # Install a flow entry to avoid future packet_in events for this flow
        if out_port != ofproto.OFPP_FLOOD:
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
                "ts": datetime.now().timestamp(),
            }
        self._queue_event_for_zone(zone_name, event_payload, datapath_id)


    def _queue_event_for_zone(self, zone_name: str, event_payload: dict, datapath_key: str):
        if zone_name == "shard_zone_rs_net1":
            client = self.host_n1_conn
            label = "N1"
        elif zone_name == "shard_zone_rs_net2":
            client = self.host_n2_conn
            label = "N2"
        else:
            print(f"Unknown shard zone '{zone_name}' for datapath {datapath_key}; skipping log")
            return

        eventlet.spawn_n(
            self._insert_event,
            client,
            event_payload,
            label,
            datapath_key,
            zone_name,
        )

    def _insert_event(
        self,
        client: MongoClient,
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

        database = client.get_default_database()
        if database is None:
            database = client["app_db"]

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
                database.events.insert_one(payload)
            except Exception as exc:
                print(
                    f"Mongo insert {label} failed for {zone_name} (datapath {datapath_key}): {exc}"
                )
                return

            zone_state["next_offset"] += 1