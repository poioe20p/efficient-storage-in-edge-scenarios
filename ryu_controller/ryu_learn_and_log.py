# ryu_apps/learn_and_log.py
from datetime import datetime
from config import MongoConfig
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.lib.packet import ethernet, ether_types, packet
from ryu.ofproto import ofproto_v1_3
from pymongo import MongoClient

class LearnAndLog(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(LearnAndLog, self).__init__(*args, **kwargs)
        self.mac_to_port = {}  # dpid -> {mac -> port}
        # optional: init pymongo here and reuse a single client
        self.mongo = None
        self.db = None
        self.mongo_config = None
        try:
            self.mongo_config = MongoConfig.load()
            self.mongo = MongoClient(self.mongo_config.app_uri())
            self.db = self.mongo[self.mongo_config.database]
        except Exception as e:
            self.logger.warning("MongoDB not connected: %s", e)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        """Runs when a switch connects; sets up table-miss flow entry."""
        datapath = ev.msg.datapath
        ofp = datapath.ofproto
        parser = datapath.ofproto_parser
        # table-miss to controller
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofp.OFPP_CONTROLLER, ofp.OFPCML_NO_BUFFER)]
        inst = [parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]
        datapath.send_msg(parser.OFPFlowMod(datapath=datapath,
                                            priority=0, match=match, instructions=inst))

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        """Handles incoming packets: learns MAC-port mapping, logs to MongoDB, and forwards."""
        msg = ev.msg
        datapath = msg.datapath
        ofp = datapath.ofproto
        parser = datapath.ofproto_parser
        dpid = datapath.id
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        dst = eth.dst
        src = eth.src

        self.mac_to_port.setdefault(dpid, {})
        self.mac_to_port[dpid][src] = in_port

        # Logging to Mongo (optional)
        if self.mongo:
            try:
                self.db.events.insert_one({
                    "type": "packet_in",
                    "dpid": dpid,
                    "src": src, "dst": dst, "in_port": in_port,
                    "ts": datetime.now(),
                })
            except Exception as e:
                self.logger.warning("Mongo insert failed: %s", e)

        # If destination MAC is known, forward to that port, else flood
        out_port = self.mac_to_port[dpid].get(dst, ofp.OFPP_FLOOD)
        actions = [parser.OFPActionOutput(out_port)]

        # Install a flow to avoid future packet-ins for this dst at this switch
        if out_port != ofp.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst)
            inst = [parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]
            datapath.send_msg(parser.OFPFlowMod(datapath=datapath,
                                                priority=100, match=match,
                                                instructions=inst))
        # Send packet out immediately
        out = parser.OFPPacketOut(datapath=datapath,
                                  buffer_id=msg.buffer_id,
                                  in_port=in_port, actions=actions)
        datapath.send_msg(out)