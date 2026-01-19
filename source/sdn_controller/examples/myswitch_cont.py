from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_0
from ryu.lib.mac import haddr_to_bin
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet

class MySwitch_Cont(app_manager.RyuApp):
  OFP_VERSIONS = [ofproto_v1_0.OFP_VERSION]

  def __init__(self, *args, **kwargs):
    super(MySwitch_Cont, self).__init__(*args, **kwargs)
    self.mac_to_port = {}

  def add_flow(self, datapath, in_port, dst, src, actions):
    # Get the OpenFlow protocol object for the given switch (datapath)
    ofproto = datapath.ofproto

    # Create a match object based on the input port, source MAC address (src), and destination MAC address (dst)
    # 'haddr_to_bin' converts the MAC addresses from human-readable form to binary, as required by OpenFlow
    match = datapath.ofproto_parser.OFPMatch(
        in_port=in_port,                      # Match the input port
        dl_dst=haddr_to_bin(dst),             # Match the destination MAC address (dl_dst = data-link (OSI Layer 2) destination)
        dl_src=haddr_to_bin(src))             # Match the source MAC address (dl_src = data-link source)

    # Create a flow modification message to add a new flow entry to the switch
    # The OFPFlowMod message includes match criteria, priority, timeout, and actions
    mod = datapath.ofproto_parser.OFPFlowMod(
        datapath=datapath,                    # The switch (datapath) to apply the flow modification
        match=match,                          # The match criteria defined above (in_port, src, dst)
        cookie=0,                             # Cookie identifier for tracking the flow (set to 0 in this case)
        command=ofproto.OFPFC_ADD,            # Command to add a new flow entry (OFPFC_ADD)
        idle_timeout=0,                       # No idle timeout (the flow will not expire due to inactivity)
        hard_timeout=0,                       # No hard timeout (the flow will not expire over time)
        priority=10,                          # Priority of the flow (higher values mean higher priority)
        flags=ofproto.OFPFF_SEND_FLOW_REM,    # Flag to send a Flow Removed message when the flow is deleted
        actions=actions                       # Actions to perform on matching packets (e.g., forward to a port)
    )

    # Send the flow modification message to the switch (datapath)
    # This installs the flow entry into the switch's flow table
    datapath.send_msg(mod)

  @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
  def switch_features_handler(self, ev):
    print ("message: ", ev.msg)
    datapath = ev.msg.datapath
    ofproto = datapath.ofproto
    parser = datapath.ofproto_parser

    # install the default flow entry.
    match = parser.OFPMatch()
    actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER)]
    mod = datapath.ofproto_parser.OFPFlowMod(
            datapath=datapath, match=match, cookie=0,
            command=ofproto.OFPFC_ADD, idle_timeout=0, hard_timeout=0,
            priority=5,
            flags=ofproto.OFPFF_SEND_FLOW_REM, actions=actions)
    datapath.send_msg(mod)

  @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)  # Decorator to register the event handler for Packet In events
  def packet_in_handler(self, ev):  # Handler function for packet-in events
    msg = ev.msg  # Extract the message from the event
    print("ev message: ", msg)  # Print the event message for debugging purposes

    datapath = msg.datapath  # Get the switch (datapath) that sent the message
    ofproto = datapath.ofproto  # Get the OpenFlow protocol constants for this datapath
    parser = datapath.ofproto_parser  # Get the OpenFlow message parser for creating messages

    in_port = msg.in_port  # Get the input port where the message arrived
    pkt = packet.Packet(msg.data)  # Create a Packet object from the incoming packet data
    eth = pkt.get_protocols(ethernet.ethernet)[0]  # Extract the Ethernet header from the message
    dst = eth.dst  # Get the destination MAC address from the Ethernet header frame
    src = eth.src  # Get the source MAC address from the Ethernet header frame

    dpid = datapath.id  # Get the unique identifier for the switch (datapath ID)
    self.mac_to_port.setdefault(dpid, {})  # Initialize an entry for the switch (dictionary key) in the MAC to port mapping if it doesn't exist

    # Learn a MAC address to avoid flooding next time
    if not src in self.mac_to_port[dpid]:  # If the source MAC is not already in the mapping for the current switch dpid
        self.mac_to_port[dpid][src] = in_port  # Add the source MAC and associated input port to the mapping
        print("mac_to_port: ", self.mac_to_port)  # Print the updated MAC to port mapping for debugging

    # Determine the output port for the destination MAC address
    if dst in self.mac_to_port[dpid]:  # If the destination MAC is in the mapping for the current switch dpid
        out_port = self.mac_to_port[dpid][dst]  # Use the known output switch port for the current destination MAC
    else:
        out_port = ofproto.OFPP_FLOOD  # Otherwise, flood the packet to all ports (broadcast) except in_port, because the destination mac was not yet learned

    # Prepare the action to be taken for the packet
    actions = [parser.OFPActionOutput(out_port)]  # Create an action to output the packet to the determined out_port

    # In addition, install a flow rule entry to avoid future packet_in events for the flow associated to the current message
    if out_port != ofproto.OFPP_FLOOD:  # Only install a flow if we're not flooding; otherwise, all the flow pakets would be always flooded, which would be very inefficent for the network.
        self.add_flow(datapath, msg.in_port, dst, src, actions)  # Call a method to send a new flow rule entry for this packet to the switch

    data = None  # Initialize data variable for packet data
    if msg.buffer_id == ofproto.OFP_NO_BUFFER:  # If the packet is not buffered
        data = msg.data  # Use the raw packet data from the message

    # Create a packet-out message to send the packet out of the switch
    out = datapath.ofproto_parser.OFPPacketOut(
        datapath=datapath,  # The switch that will send the packet
        buffer_id=msg.buffer_id,  # The buffer ID of the incoming packet, or OFP_NO_BUFFER if not buffered
        in_port=msg.in_port,  # The input port from which the packet arrived
        actions=actions,  # The list of actions to take (e.g., output to the determined out_port)
        data=data  # The raw packet data (if applicable)
    )

    datapath.send_msg(out)  # Send the packet-out message to the switch to forward only the current packet (not the upcoming ones)
