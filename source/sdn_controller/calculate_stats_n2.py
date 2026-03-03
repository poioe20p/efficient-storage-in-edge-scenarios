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
from sdn_controller.library.models.debit import DebitStats
from sdn_controller.library.repositories.debit import DebitRepository
from sdn_controller.models.mongodb_host import MongodbRouter
import time

class CalculateSwitchPortDebit(Topology_proactive):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(CalculateSwitchPortDebit, self).__init__(*args, **kwargs)
        self.polling_interval = float(5)
        self.monitor_thread = hub.spawn(self._monitor)
        self._last_port_counters = {}
        self._port_desc = {}

        self.lan_id = "lan_2"
        self._other_lan_id = "lan_1"
        self._port_stats_reply_count = 0
        self._debit_repo = DebitRepository(MongodbRouter().get_simple_connection_string(add_app=True))
        
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
        if self._datapath_by_id:
            for dp, _ in self._datapath_by_id.values():
                yield dp
            return

        if self.sws:
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


    def _get_other_lan_stats(self):
        try:
            return self._debit_repo.get_debit_by_lan_id(self._other_lan_id)
        except Exception:
            return None


    def _build_host_ports(self):
        host_ports = {}
        for host in getattr(self, "hosts", []) or []:
            try:
                host_ports[(int(host[1]), int(host[2]))] = str(host[0])
            except Exception:
                continue
        return host_ports


    def _build_link_neighbors(self):
        link_ports = set()
        link_neighbors = {}
        for link in getattr(self, "links", []) or []:
            try:
                key = (int(link[0]), int(link[2]))
                link_ports.add(key)
                link_neighbors[key] = int(link[1])
            except Exception:
                continue
        return link_ports, link_neighbors


    def _compute_sample_ts(self, stat, now_epoch):
        duration_sec = getattr(stat, "duration_sec", None)
        duration_nsec = getattr(stat, "duration_nsec", None)
        if duration_sec is not None:
            return float(duration_sec) + (float(duration_nsec or 0) * 1e-9)
        return now_epoch


    def _compute_port_total_bps(self, key, rx_bytes, tx_bytes, sample_ts):
        prev = self._last_port_counters.get(key)

        rx_bps = 0.0
        tx_bps = 0.0
        if prev is not None:
            dt = sample_ts - float(prev.get("ts", 0.0) or 0.0)
            if dt > 0:
                rx_delta = rx_bytes - int(prev.get("rx_bytes", 0) or 0)
                tx_delta = tx_bytes - int(prev.get("tx_bytes", 0) or 0)

                # Handle counter reset/rollover.
                if rx_delta >= 0:
                    rx_bps = (rx_delta * 8.0) / dt
                if tx_delta >= 0:
                    tx_bps = (tx_delta * 8.0) / dt

        return rx_bps + tx_bps


    def _print_debit_stats(self, debit_stats, *, prefix, show_header):
        if debit_stats is None:
            return

        if show_header:
            if prefix == "PORT_RATE_OTHER":
                print("----- PORT RATES FROM OTHER LAN (lan_id={}) -----".format(debit_stats.lan_id))
            else:
                print("----- PORT RATES (lan_id={}) -----".format(debit_stats.lan_id))

        for p in getattr(debit_stats, "port", []) or []:
            try:
                neighbor = getattr(p, "neighbor_switch_id", None)
                peer_mac = getattr(p, "peer_mac", None)
                if neighbor is not None:
                    # Keep current behavior: do not print switch-link entries.
                    continue

                is_server = peer_mac in getattr(self, "servers_mac", [])
                if not is_server:
                    # Keep current behavior: only print server-facing host ports.
                    continue

                if prefix == "PORT_RATE_OTHER":
                    print(
                        "PORT_RATE_OTHER lan_id={} dpid={} port={} bps={:.2f} peer_mac={}".format(
                            debit_stats.lan_id,
                            p.switch_id,
                            p.port_no,
                            float(p.flow_rate),
                            peer_mac,
                        )
                    )
                else:
                    print(
                        "PORT_RATE dpid={} port={} bps={:.2f} peer_mac={}".format(
                            p.switch_id,
                            p.port_no,
                            float(p.flow_rate),
                            peer_mac,
                        )
                    )
            except Exception:
                continue

        if show_header:
            print("---------------------------------------")


    def _collect_port_stats_entries(self, *, datapath, dpid, now_epoch, stats_body, host_ports, link_ports, link_neighbors):
        port_stats_entries = []

        for stat in stats_body:
            port_no = stat.port_no
            if port_no == datapath.ofproto.OFPP_LOCAL:
                continue

            key = (int(dpid), int(port_no))
            peer_mac = host_ports.get(key)
            if peer_mac is None and key in link_ports:
                peer_mac = self._port_desc.get(key, {}).get("hw_addr")

            # Only keep ports that topology has classified as host-facing or switch-link.
            if peer_mac is None:
                continue

            rx_bytes = int(getattr(stat, "rx_bytes", 0) or 0)
            tx_bytes = int(getattr(stat, "tx_bytes", 0) or 0)
            sample_ts = self._compute_sample_ts(stat, now_epoch)

            total_bps = self._compute_port_total_bps(key, rx_bytes, tx_bytes, sample_ts)
            neighbor = link_neighbors.get(key)

            port_stats_entries.append(
                DebitStats.SwitchPortStats(
                    switch_id=str(dpid),
                    port_no=int(port_no),
                    flow_rate=float(total_bps),
                    peer_mac=str(peer_mac),
                    neighbor_switch_id=str(neighbor) if neighbor is not None else None,
                )
            )

            self._last_port_counters[key] = {
                "ts": sample_ts,
                "rx_bytes": rx_bytes,
                "tx_bytes": tx_bytes,
            }

        return port_stats_entries


    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def port_stats_reply_handler(self, ev):
        """Handles the reply for port statistics and prints per-port rate (bps)."""
        datapath = ev.msg.datapath
        dpid = datapath.id
        now_epoch = time.time()

        self._port_stats_reply_count += 1

        other_lan_stats = self._get_other_lan_stats()
        self._print_debit_stats(other_lan_stats, prefix="PORT_RATE_OTHER", show_header=True)

        host_ports = self._build_host_ports()
        link_ports, link_neighbors = self._build_link_neighbors()

        port_stats_entries = self._collect_port_stats_entries(
            datapath=datapath,
            dpid=dpid,
            now_epoch=now_epoch,
            stats_body=ev.msg.body,
            host_ports=host_ports,
            link_ports=link_ports,
            link_neighbors=link_neighbors,
        )

        # Print local rates (keep current behavior: only server-facing host ports).
        if port_stats_entries:
            self._print_debit_stats(
                DebitStats(lan_id=self.lan_id, switch_ports=port_stats_entries),
                prefix="PORT_RATE",
                show_header=False,
            )

        # Persist periodically (every 2nd stats reply) to avoid excessive writes.
        if port_stats_entries and (self._port_stats_reply_count % 2 == 0):
            try:
                debit_stats = DebitStats(lan_id=self.lan_id, switch_ports=port_stats_entries)
                self._debit_repo.upsert_debit_by_lan_id(debit_stats)
            except Exception:
                pass
    