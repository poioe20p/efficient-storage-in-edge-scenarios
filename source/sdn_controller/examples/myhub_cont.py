from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_0

class MyHub_Cont(app_manager.RyuApp):
  OFP_VERSIONS = [ofproto_v1_0.OFP_VERSION]

  def __init__(self, *args, **kwargs):
    super(MyHub_Cont, self).__init__(*args, **kwargs)

  @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
  def switch_features_handler(self, ev):
    print ("message: ", ev.msg)
    datapath = ev.msg.datapath
    ofproto = datapath.ofproto
    parser = datapath.ofproto_parser

    # configure and send the default flow entry to the switch.
    match = parser.OFPMatch()
    # OFPP_CONTROLLER is a special port number that instructs the switch to send any received packet to the SDN controller.
    # Following this action, the switch encapsulates in an OpenFlow Packet-In message the received packet and sends it to the SDN controller.
    # After the Packet-In message arrival, a corresponding Event is created in the Ryu controller. See code below.
    actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER)]
    mod = datapath.ofproto_parser.OFPFlowMod(
            datapath=datapath, match=match, cookie=0,
            command=ofproto.OFPFC_ADD, idle_timeout=0, hard_timeout=0,
            priority=5,
            flags=ofproto.OFPFF_SEND_FLOW_REM, actions=actions)
    # send the flow rule to the switch; the switch after receiving this flow rule store it in a local table
    datapath.send_msg(mod)

  # Define a packet-in event handler, triggered when the switch sends a Packet-In message to the controller
  @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
  def packet_in_handler(self, ev):
    """
    This method handles the Packet-In event, which occurs after an OpenFlow Packet-In message just arrived to the controller.
    This Packet-In message has encapsulated a packet previously received by the switch
    that did not match any flow rule entry with a non-empty match field, and consequently the switch forwarded the packet to the controller, requiring some assistance.
    The controller in the method called by the current event analyzes the diverse received (by the switch) message header fields and then at the method final code sends 
    a Packet-Out message to the switch, instructing that switch how should locally process only the current packet.
    """

    # Get the Packet-In message from the event (ev), which contains the packet details
    msg = ev.msg
    # Print the received message for debugging purposes
    print("message: ", msg)

    # Get the switch (datapath) that sent the Packet-In message
    datapath = msg.datapath
    # Retrieve the OpenFlow protocol object for the switch (contains OpenFlow constants)
    ofproto = datapath.ofproto
    # Get the protocol parser to help construct OpenFlow messages and actions
    parser = datapath.ofproto_parser

    # Initialize the data variable as None, to hold packet data if necessary
    data = None
    # If the packet is not buffered on the switch (buffer_id is OFP_NO_BUFFER), retrieve the full packet data
    if msg.buffer_id == ofproto.OFP_NO_BUFFER:
      data = msg.data

    # Create an empty match object. This will match all packets (no specific fields matched).
    match = parser.OFPMatch()

    # Set the output port to "FLOOD", which means the packet will be sent to all ports except the one it came from
    out_port = ofproto.OFPP_FLOOD

    # Define the action as forwarding the packet to the out_port (FLOOD)
    actions = [parser.OFPActionOutput(out_port)]

    # Create a Packet-Out message to send the packet from the controller to the switch with the desired action
    # this action will be applied only to the current packet, not to the future packets!
    out = datapath.ofproto_parser.OFPPacketOut(
          datapath=datapath,           # Specify the switch that will receive the Packet-Out message
          buffer_id=msg.buffer_id,     # If the packet is buffered on the switch, pass its buffer ID
          in_port=msg.in_port,         # The port on the switch where the packet originally arrived
          actions=actions,             # The action list (in this case, flood the packet)
          data=data                    # The actual packet data if it's not buffered on the switch
    )

    # Send the Packet-Out message to the switch, telling it to flood only the received packet to all ports except the one where
    # the packet has previously arrived to the switch.
    datapath.send_msg(out)
