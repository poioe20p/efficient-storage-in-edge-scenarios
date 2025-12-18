from datetime import datetime
from os_ken import cfg
from os_ken.base import app_manager
from os_ken.topology.api import get_all_link, get_host
from sdn_controller.osken_learn_and_log_n1 import KenLearnAndLog
from os_ken.controller.handler import MAIN_DISPATCHER, DEAD_DISPATCHER
from os_ken.controller.handler import set_ev_cls
from os_ken.controller import ofp_event
from os_ken.lib import hub
from sdn_controller.repositories.repositories.topology import TopologyRepository
from sdn_controller.repositories.models.topology import Topology, Host
from sdn_controller.models.mongodb_host import MongodbHost
import networkx as nx
import eventlet
from datetime import datetime

class Topology_proactive(KenLearnAndLog):
    REQUIRED_APP = ['os_ken.topology.switches']

    def __init__(self, *args, **kwargs):
        cfg.CONF.observe_links = True
        super(Topology_proactive, self).__init__(*args, **kwargs)
        self.net = nx.DiGraph()
        self.cnt = 0
        self.sws = []
        self.links = []
        self.hosts = []
        self.sws_prev = []
        self.links_prev = []
        self.hosts_prev = []
        self.INTERVAL = 2
        self._datapath_by_id = {}
        self._installed_flow_keys = set()
        self._arp_rules_installed = set()
        self._topology_api_app = None
        self._topology_api_lookup_warned = False
        self.enable_reactive_learning = True
        self._router_mac_blocklist = {
            "00:00:00:00:00:aa",  # nat-router LAN (network 1)
            "00:00:00:00:00:bb",  # nat-router WAN (to host)
            "00:00:00:00:00:cc",  # nat-router LAN (network 2)
            "00:00:00:00:00:dd",  # dedicated internet uplink
            "00:00:00:00:00:AA",  # nat-router LAN (network 1)
            "00:00:00:00:00:BB",  # nat-router WAN (to host)
            "00:00:00:00:00:CC",  # nat-router LAN (network 2)
            "00:00:00:00:00:DD",  # dedicated internet uplink
        }
        self.topology_has_been_stored = False
        self.topology_repo_n1 = TopologyRepository(
            MongodbHost(host="10.0.0.4", port=27018, database_name="app_db").get_simple_connection_string(
                add_app=True
            )
        )
        self.last_topology_store_time = None
        
        
        hub.spawn(self._topology_worker)

    @set_ev_cls(ofp_event.EventOFPStateChange,[MAIN_DISPATCHER, DEAD_DISPATCHER])
    def _state_change_handler(self, ev):
        """
        Docstring for _state_change_handler
        Handles state changes of switches (datapaths) in the network.
        When a switch connects (MAIN_DISPATCHER), it is registered and added to the list of switches.
        When a switch disconnects (DEAD_DISPATCHER), it is unregistered and removed from the list.
        """
        datapath = ev.datapath
        if ev.state == MAIN_DISPATCHER:
            if datapath not in self.sws:
                #self.logger.debug('%s:register datapath: %016x', time.time() - self.s_time, datapath.id)
                self.sws.append((datapath, datapath.id))
                self._datapath_by_id[datapath.id] = (datapath, datapath.id)
        elif ev.state == DEAD_DISPATCHER:
            if datapath in self.sws:
                #self.logger.debug('%s:unregister datapath: %016x', time.time() - self.s_time, datapath.id)
                self.sws.remove((datapath, datapath.id))
            self._datapath_by_id.pop(datapath.id, None)

    def check_link(self, link_in, links_list):
        """
        Check if a switch output port is already connected to a direct link neighbor.
        In this case, returns False. It avoids links between non-neighbor switches, and
        duplicated links between the local self.sw and the os_ken topology links.
        """
        for link in links_list:
            if link[0] == link_in[0] and link[2] == link_in[2]:
                return False
        return True

    def _get_topology_api_app(self):
        """
        Lazily resolve the topology switches service so topology APIs receive
        the expected handle even if the controller starts first.
        """
        if self._topology_api_app is None:
            self._topology_api_app = app_manager.lookup_service_brick('switches')
            if self._topology_api_app is None:
                if not self._topology_api_lookup_warned:
                    self.logger.debug("Topology API service not ready yet")
                    self._topology_api_lookup_warned = True
            else:
                self._topology_api_lookup_warned = False
        return self._topology_api_app

    def get_sws_links_hosts (self):
        # Before update the topology, clean the previous one!
        self.links = []
        self.hosts = []
        self.net.clear()

        topo_api_app = self._get_topology_api_app()
        if topo_api_app is None:
            return

        # get list of hosts
        host_list = get_host(topo_api_app, None) or []
        # host_list = get_host(self, None) or []
        self.hosts = [
            (host.mac, host.port.dpid, host.port.port_no)
            for host in host_list
            if getattr(host, "port", None) is not None
            and host.mac not in self._router_mac_blocklist
        ]

        # update networkx topology with the hosts links
        for host in self.hosts:
            self.net.add_edge(host[0], host[1], weight=1, port=1)
            self.net.add_edge(host[1], host[0], weight=1, port=host[2])

        # get list of links between switches
        links_list = get_all_link(topo_api_app) or []
        # links_list = get_all_link(self)
        links = [(link.src.dpid, link.dst.dpid, link.src.port_no) for link in links_list]
        l = self.links
        for link in links:
            if self.check_link(link, l):
                self.links.append(link)

        # update networkx topology with the links between switches
        for link in self.links:
            self.net.add_edge(link[0], link[1], weight=1, port=link[2])

    def _topology_worker(self):
       """
       This function runs in an infinite loop and periodically checks the network topology (switches, links, and hosts).
       It refreshes the topology and compares the current state with the previous state.
       If any changes are detected in the topology, flow rules are installed proactively for all switches.
       """
       while True:
         try:
            # Sleep for a specified interval (self.INTERVAL) before executing the next iteration
            hub.sleep(self.INTERVAL)

            # Controller refreshes the network topology, getting current switches, links, and hosts
            self.get_sws_links_hosts()

            # Every 5th iteration, perform additional actions like printing the current network state
            if self.cnt % 5 == 0:
                self.cnt = 0  # Reset the counter
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                print(f"[{ts}] ************************************")
                print(f"[{ts}] Switches:  {self.sws}")  # Print current switches in the network
                print(f"[{ts}] Network links:  {self.links}")  # Print current links in the network
                print(f"[{ts}] Hosts:  {self.hosts}")  # Print current hosts in the network
                
                # Store the topology in the database only once at the beginning
                if not self.topology_has_been_stored:
                    eventlet.spawn_n(
                        self.store_topology_in_db
                    )
                    self.topology_has_been_stored = True
                    self.last_topology_store_time = datetime.now()

                # Detect changes on topology / hosts
                change_flow_rules = (
                    self.hosts != self.hosts_prev or
                    self.links != self.links_prev or
                    self.sws != self.sws_prev
                )

                # Atualiza cópias para próxima comparação
                self.hosts_prev = self.hosts.copy()
                self.links_prev = self.links.copy()
                self.sws_prev = self.sws.copy()

                if (self.sws and self.links and self.hosts) and change_flow_rules:
                    self._installed_flow_keys.clear()
                    self._arp_rules_installed.clear()
                    self.mac_to_port.clear()
                    self.send_all_flow_rules_proactively()
                    eventlet.spawn_n(
                        self.store_topology_in_db
                    )
                    self.last_topology_store_time = datetime.now()
                else:
                    time_since_last_store = (datetime.now() - self.last_topology_store_time).total_seconds()
                    if time_since_last_store >= 200:
                        eventlet.spawn_n(
                            self.store_topology_in_db
                        )
                        self.last_topology_store_time = datetime.now()

            # Increment the iteration counter (used for the % 5 check)
            self.cnt = self.cnt + 1

         except Exception as e:
            self.logger.error(f"Error in topology thread: {e}")

         except KeyboardInterrupt:
            # Handle user interruption (Ctrl+C) and print a closing message before stopping the loop
            print("Closing ....")
            pass

    def proactive_flow_rule_install(self, sw, p):
      """
      This method installs bidirectional flow rules proactively in the switch.
      It installs flows for a specific path and hosts for both directions (src -> dst and dst -> src).

      Args:
      sw (tuple): A tuple containing (dp, dpid) where dp is the datapath object (switch) and dpid is the switch ID.
      p (list): List representing the nodes in the path (from source to destination).
      """
      # Extract the switch datapath and dpid (datapath ID)
      dp = sw[0]
      dpid = sw[1]

      # Extract source and destination MAC addresses from the path 'p'
      src_mac = p[0]    # Source MAC address is the first in the path
      dst_mac = p[-1]   # Destination MAC address is the last in the path

      # Initialize the mac_to_port dictionary for the given switch (dpid) if it doesn't already exist
      self.mac_to_port.setdefault(dpid, {})

      # Retrieve the protocol parser and ofproto objects
      parser = dp.ofproto_parser
      ofproto = dp.ofproto

      try:
          index_current_dpid = p.index(dpid)
          prev_node = p[index_current_dpid - 1]
          next_node = p[index_current_dpid + 1]
      except (ValueError, IndexError):
          self.logger.warning("Switch %s not fully present in calculated path %s", dpid, p)
          return

      try:
          in_port = self.net[dpid][prev_node]['port']
          out_port = self.net[dpid][next_node]['port']
      except KeyError:
          self.logger.warning("Missing port data for %s in path %s", dpid, p)
          return

      forward_key = (dpid, src_mac, dst_mac)
      reverse_key = (dpid, dst_mac, src_mac)

      if forward_key not in self._installed_flow_keys:
          match = parser.OFPMatch(in_port=in_port, eth_dst=dst_mac, eth_src=src_mac)
          actions = [parser.OFPActionOutput(out_port)]
          self._install_flow(dp, priority=5, match=match, actions=actions)
          self._installed_flow_keys.add(forward_key)

      if reverse_key not in self._installed_flow_keys:
          match = parser.OFPMatch(in_port=out_port, eth_dst=src_mac, eth_src=dst_mac)
          actions = [parser.OFPActionOutput(in_port)]
          self._install_flow(dp, priority=5, match=match, actions=actions)
          self._installed_flow_keys.add(reverse_key)

      if dpid not in self._arp_rules_installed:
          match = parser.OFPMatch(eth_type=0x806)
          actions = [parser.OFPActionOutput(ofproto.OFPP_FLOOD)]
          self._install_flow(dp, priority=1, match=match, actions=actions)
          self._arp_rules_installed.add(dpid)

      # Manually update the mac_to_port mapping for src_mac and dst_mac
      # This simulates that the controller has "learned" the MAC-port mapping
      # It avoids relying on Packet-In events since the flow rules are installed proactively.
      self.mac_to_port[dpid][src_mac] = in_port
      self.mac_to_port[dpid][dst_mac] = out_port


    def send_all_flow_rules_proactively(self):
      """
      This method installs proactive flow rules for all possible host-to-host communication paths.
      It iterates over all host pairs and finds the shortest path between them, then installs bidirectional flow rules.
      """
      if not self.hosts or not self._datapath_by_id:
          return

      for idx, host1 in enumerate(self.hosts):
          for host2 in self.hosts[idx + 1:]:
              try:
                  path = nx.shortest_path(self.net, host1[0], host2[0])
              except (nx.NetworkXNoPath, nx.NodeNotFound):
                  continue
              self._install_path_flows(path)

    def _install_path_flows(self, path):
      for node in path:
          sw = self._datapath_by_id.get(node)
          if sw:
              self.proactive_flow_rule_install(sw, path)

    def store_topology_in_db(self):
        hosts_model = [
            Host(mac=host[0], switch_dpid=host[1], port_no=host[2])
            for host in self.hosts
        ]

        topology_model = Topology(
            hosts=hosts_model,
            links=self.links,
            switchs=[sw[1] for sw in self.sws],
            timestamp=datetime.now().isoformat(timespec="seconds"),
            ttl=(datetime.now().timestamp() + 3 * 3600),
            controller_name="osken_n1"
        )
        
        self.topology_repo_n1.insert_topology(topology_model, topology_id="current")
        print("Topology stored in database successfully.")