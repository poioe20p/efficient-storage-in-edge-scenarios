from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_0

class MySwitch(app_manager.RyuApp):
  OFP_VERSIONS = [ofproto_v1_0.OFP_VERSION]

  def __init__(self, *args, **kwargs):
    super(MySwitch, self).__init__(*args, **kwargs)

  @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
  def switch_features_handler(self, ev):
    print ("message: ", ev.msg)
    datapath = ev.msg.datapath
    ofproto = datapath.ofproto
    parser = datapath.ofproto_parser

    # install the default flow entry for the switch operating as a local switch
    match = parser.OFPMatch()
    # OFPP_NORMAL is a special port in OpenFlow that indicates the packet should be processed via a legacy MAC-learning and L2 (Layer 2) switching.
    # The packets are forwarded just like a traditional switch would, without any further SDN controller intervention.
    actions = [parser.OFPActionOutput(ofproto.OFPP_NORMAL)]
    mod = datapath.ofproto_parser.OFPFlowMod(
            datapath=datapath, match=match, cookie=0,
            command=ofproto.OFPFC_ADD, idle_timeout=0, hard_timeout=0,
            priority=ofproto.OFP_DEFAULT_PRIORITY,
            flags=ofproto.OFPFF_SEND_FLOW_REM, actions=actions)
    datapath.send_msg(mod)
