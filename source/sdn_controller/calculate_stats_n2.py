import eventlet
eventlet.monkey_patch()
from os_ken.ofproto import ofproto_v1_3
from os_ken.lib import hub
from os_ken.controller.handler import (
    MAIN_DISPATCHER,
    set_ev_cls,
)
from os_ken.controller import ofp_event
from sdn_controller.usecases.topology_n2 import Topology_proactive
import time

class CalculateSwitchPortDebit(Topology_proactive):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(CalculateSwitchPortDebit, self).__init__(*args, **kwargs)
        self.polling_interval = float(5)
        self.monitor_thread = hub.spawn(self._monitor)
        self._last_port_counters = {}
        self._port_desc = {}
        
    def _monitor(self):
        while True:
            for datapath in self._iter_datapaths():
                self.request_port_desc(datapath)
                self.request_port_stats(datapath)
            hub.sleep(self.polling_interval)


    def _iter_datapaths(self):
        """Yields datapaths currently connected to the controller.

        Topology_proactive tracks datapaths in `self._datapath_by_id` and `self.sws`.
        This helper keeps the stats poller resilient to internal representation changes.
        """
        if hasattr(self, "_datapath_by_id") and isinstance(self._datapath_by_id, dict):
            for dp, _ in self._datapath_by_id.values():
                yield dp
            return

        if hasattr(self, "sws") and isinstance(self.sws, list):
            for dp, _ in self.sws:
                yield dp
            return

        for dp in getattr(self, "datapaths", []) or []:
            yield dp


    def request_port_stats(self, datapath):
        """Sends a request for port statistics to the switch."""
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        req = parser.OFPPortStatsRequest(datapath, 0, ofproto.OFPP_ANY)
        datapath.send_msg(req)


    def request_port_desc(self, datapath):
        """Sends a request for port descriptions (includes port MAC/hw_addr)."""
        parser = datapath.ofproto_parser
        req = parser.OFPPortDescStatsRequest(datapath, 0)
        datapath.send_msg(req)


    @set_ev_cls(ofp_event.EventOFPPortDescStatsReply, MAIN_DISPATCHER)
    def port_desc_reply_handler(self, ev):
        datapath = ev.msg.datapath
        dpid = datapath.id
        for port in ev.msg.body:
            port_no = getattr(port, "port_no", None)
            if port_no is None:
                continue
            if port_no == datapath.ofproto.OFPP_LOCAL:
                continue

            hw_addr = getattr(port, "hw_addr", None)
            name = getattr(port, "name", None)
            if isinstance(name, (bytes, bytearray)):
                try:
                    name = name.decode("utf-8", errors="replace")
                except Exception:
                    name = None

            self._port_desc[(dpid, int(port_no))] = {
                "hw_addr": hw_addr,
                "name": name,
            }


    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def port_stats_reply_handler(self, ev):
        """Handles the reply for port statistics and prints per-port rate (bps)."""
        datapath = ev.msg.datapath
        dpid = datapath.id
        now_epoch = time.time()

        host_ports = {}
        for host in getattr(self, "hosts", []) or []:
            try:
                host_ports[(int(host[1]), int(host[2]))] = str(host[0])
            except Exception:
                continue

        link_ports = set()
        link_neighbors = {}
        for link in getattr(self, "links", []) or []:
            try:
                key = (int(link[0]), int(link[2]))
                link_ports.add(key)
                link_neighbors[key] = int(link[1])
            except Exception:
                continue

        for stat in ev.msg.body:
            port_no = stat.port_no
            if port_no == datapath.ofproto.OFPP_LOCAL:
                continue

            key = (int(dpid), int(port_no))
            peer_mac = host_ports.get(key)
            if peer_mac is None and key in link_ports:
                peer_mac = self._port_desc.get(key, {}).get("hw_addr")

            # Only print ports that topology has classified as host-facing or switch-link.
            if peer_mac is None:
                continue

            rx_bytes = int(getattr(stat, "rx_bytes", 0) or 0)
            tx_bytes = int(getattr(stat, "tx_bytes", 0) or 0)

            prev = self._last_port_counters.get(key)

            rx_bps = 0.0
            tx_bps = 0.0
            if prev is not None:
                dt = now_epoch - float(prev.get("ts_epoch", 0.0) or 0.0)
                if dt > 0:
                    rx_delta = rx_bytes - int(prev.get("rx_bytes", 0) or 0)
                    tx_delta = tx_bytes - int(prev.get("tx_bytes", 0) or 0)

                    # Handle counter reset/rollover.
                    if rx_delta >= 0:
                        rx_bps = (rx_delta * 8.0) / dt
                    if tx_delta >= 0:
                        tx_bps = (tx_delta * 8.0) / dt

            total_bps = rx_bps + tx_bps
            neighbor = link_neighbors.get(key)
            if neighbor is not None:
                print("PORT_RATE dpid={} port={} bps={:.2f} peer_mac={} neighbor_dpid={}".format(dpid, port_no, total_bps, peer_mac, neighbor))
            else:
                print("PORT_RATE dpid={} port={} bps={:.2f} peer_mac={}".format(dpid, port_no, total_bps, peer_mac))

            self._last_port_counters[key] = {
                "ts_epoch": now_epoch,
                "rx_bytes": rx_bytes,
                "tx_bytes": tx_bytes,
            }
    