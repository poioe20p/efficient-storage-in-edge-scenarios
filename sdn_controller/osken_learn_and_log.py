"""Learning-switch style OS-Ken app that logs packet events to MongoDB."""
import eventlet
eventlet.monkey_patch()
from datetime import datetime
from config import MongoConfig
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

# This class defines a simple OS-Ken application that acts like a switch in an OpenFlow network and
# logs packet events to a MongoDB database.
class KenLearnAndLog(app_manager.OSKenApp):
    """Simple layer-2 learning switch with optional MongoDB logging."""
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(KenLearnAndLog, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.mongo_config = None
        self._mongo_thread = None
        self._mongo_setup_thread = None
        self._mongo_client = None
        self._db = None
        self._mongo_uri = None
        self._mongo_ready = False

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
        self._ensure_mongo_connector()


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
        
        dpid = datapath.id  # Get the unique identifier for the switch (datapath ID)
        self.mac_to_port.setdefault(dpid, {}) # Initialize an entry for the switch (dictionary key) in the MAC to port mapping if it doesn't exist
        
        # Learn a MAC address to avoid flooding next time
        if src not in self.mac_to_port[dpid]:  # If the source MAC is not already in the mapping for the current switch dpid
            self.mac_to_port[dpid][src] = in_port
            self.logger.info("mac_to_port[%s]: %s", dpid, self.mac_to_port[dpid])
        
        # Determine the output port for the destination MAC address    
        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
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

        db = self._db
        if db is None:
            self.logger.debug("MongoDB handle not ready; skipping event persistence")
            return

        try:
            client_nodes = getattr(self._mongo_client, "nodes", None)
            self.logger.debug(
                "Attempting packet log insert into db=%s via uri=%s nodes=%s",
                db.name,
                self._mongo_uri or "<unavailable>",
                client_nodes,
            )
            db.events.insert_one(
                {
                    "type": "packet_in",
                    "dpid": dpid,
                    "src": src,
                    "dst": dst,
                    "in_port": in_port,
                    "out_port": out_port,
                    "ts": datetime.now().timestamp(),
                }
            )
            self.logger.debug(
                "Packet log insert succeeded for uri=%s",
                self._mongo_uri or "<unavailable>",
            )
        except Exception as exc:
            client_nodes = getattr(self._mongo_client, "nodes", None)
            self.logger.warning(
                "Mongo insert failed via uri=%s nodes=%s: %s",
                self._mongo_uri or "<unavailable>",
                client_nodes,
                exc,
            )

    def _ensure_mongo_connector(self):
        if self.mongo_config is None:
            try:
                self.mongo_config = MongoConfig.load()
            except Exception as exc:
                self.logger.warning("MongoDB config load failed: %s", exc)
                return
            self.logger.info(
                "MongoDB targets router=%s:%s config=%s:%s",
                self.mongo_config.router_host,
                self.mongo_config.router_port,
                self.mongo_config.config_host,
                self.mongo_config.config_port,
            )

        def start_connector_thread():
            if self._mongo_thread and not self._mongo_thread.dead:
                return
            self._mongo_uri = self.mongo_config.router_app_uri()
            self.logger.debug("Starting MongoDB connector targeting %s", self._mongo_uri)
            self._mongo_thread = eventlet.spawn(
                self._mongo_connector_loop,
                self._mongo_uri,
            )

        if not self._mongo_ready:
            if self._mongo_setup_thread and not self._mongo_setup_thread.dead:
                return

            def setup_sharding():
                try:
                    from sdn_controller.database import MongoDatabase

                    db_helper = MongoDatabase(self.mongo_config)
                    db_helper.setup_sharded_cluster(self.mongo_config.database, self.mongo_config)
                    self._mongo_ready = True
                    self.logger.info("MongoDB sharded cluster configured")
                    start_connector_thread()
                except Exception as exc:
                    self.logger.warning("MongoDB sharding setup failed: %s", exc)
                finally:
                    self._mongo_setup_thread = None

            self._mongo_setup_thread = eventlet.spawn(setup_sharding)
            return
        else:
            start_connector_thread()

    def _mongo_connector_loop(self, uri: str):
        while True:
            client = None
            db = None
            try:
                client = MongoClient(uri, serverSelectionTimeoutMS=2000)
                db = client[self.mongo_config.database]
                nodes = getattr(client, "nodes", None)
                self._mongo_client = client
                self._db = db
                self.logger.info("MongoDB connection established to %s nodes=%s", uri, nodes)
                while True:
                    try:
                        client.admin.command("ping")
                        eventlet.sleep(10)
                    except Exception as exc:
                        self.logger.warning(f"Lost connection to {uri}: {exc}")
                        break
            except Exception as exc:
                self.logger.warning(f"MongoDB connection attempt failed for {uri}: {exc}")
            finally:
                if client is not None:
                    try:
                        client.close()
                    except Exception:
                        pass
                if self._mongo_client is client:
                    self._mongo_client = None
                if self._db is db:
                    self._db = None
                eventlet.sleep(5)
