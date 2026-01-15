from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_0

# This class defines a simple Ryu application that acts like a hub in an OpenFlow network.
# A hub forwards packets to all ports, effectively "broadcasting" the packets to all other hosts.
# The MyHub class inherits from app_manager.RyuApp, which is the base class for Ryu applications.
class MyHub(app_manager.RyuApp):

    # Specify that the OpenFlow version to be used is 1.0. This is set using OFP_VERSIONS.
    # OpenFlow 1.0 (ofproto_v1_0) is one of the first versions of OpenFlow.
    OFP_VERSIONS = [ofproto_v1_0.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        # Initialize the parent class (RyuApp) using super() to inherit properties and methods.
        super(MyHub, self).__init__(*args, **kwargs)

    # Event handler for switch features. This method is triggered when a switch connects to the controller.
    # @set_ev_cls decorator tells Ryu that the method "switch_features_handler" should be invoked when an EventOFPSwitchFeatures event is received.
    # CONFIG_DISPATCHER means this event is handled after the switch enters the configuration phase (after the initial handshake between switch and controller).
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        # Print a log message showing the message details from the event (ev) sent by the switch with their internal characteristics.
        print("message: ", ev.msg)

        # Extract the datapath object, which represents in the controller enviroment the switch that is communicating with the controller.
        # The datapath contains information about the switch (datapath ID, methods to send messages, etc.)
        datapath = ev.msg.datapath

        # ofproto represents the OpenFlow protocol, which includes constants (like action types and message types).
        ofproto = datapath.ofproto

        # The parser helps in creating OpenFlow messages such as matches, actions, flow mods, etc.
        parser = datapath.ofproto_parser

        # Create a match object with no specific fields, meaning it will match all packets (wildcard match).
        # This is the default behavior of a hub, which forwards all traffic.
        match = parser.OFPMatch()

        # Create an action to output the packets to all switch ports (flood the traffic).
        # OFPP_FLOOD means that the packet should be sent to all ports except the one it arrived on.
        actions = [parser.OFPActionOutput(ofproto.OFPP_FLOOD)]

        # Create a flow modification message to install the "hub" behavior in the switch.
        # The controller is installing a flow rule that will match all packets and flood them out to all ports.
        # Fields in the OFPFlowMod:
        # - datapath: the switch this flow is being installed on.
        # - match: specifies the matching rule (matches all packets here because the match is empty and any traffic becomes selected).
        # - actions: list of actions to take on matched packets (flood the packets here).
        # - idle_timeout: time (in seconds) after which the flow will expire due to inactivity and it will be removed from the switch (0 means never).
        # - hard_timeout: absolute time (in seconds) after which the flow will expire and it will be removed from the switch (0 means never).
        # - priority: defines the priority of the flow. Default priority is used here.
        # - OFPFF_SEND_FLOW_REM: flag that tells the switch to notify the controller when the flow is removed.
        mod = datapath.ofproto_parser.OFPFlowMod(
            datapath=datapath, match=match, cookie=0,
            command=ofproto.OFPFC_ADD, idle_timeout=0, hard_timeout=0,
            priority=ofproto.OFP_DEFAULT_PRIORITY,
            flags=ofproto.OFPFF_SEND_FLOW_REM, actions=actions)

        # Send the flow modification message to the switch to install the hub behavior.
        datapath.send_msg(mod)
