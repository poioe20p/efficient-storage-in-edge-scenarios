from ryu.base import app_manager
import networkx as nx
from ryu.topology import event, switches
from ryu.topology.api import get_all_switch, get_all_link, get_host
from myswitch_cont import MySwitch_Cont
from ryu.lib import hub

from ryu.controller.handler import MAIN_DISPATCHER,DEAD_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.controller import ofp_event
import time

class Topology_proactive(MySwitch_Cont):
    def __init__(self):
        super(Topology_proactive, self).__init__()
        hub.spawn(self.myfunction)
        self.net = nx.DiGraph()
        self.cnt = 0
        self.sws = []
        self.links = []
        self.hosts = []
        self.sws_prev = []
        self.links_prev = []
        self.hosts_prev = []
        self.INTERVAL = 2
        #self.s_time = time.time()

    @set_ev_cls(ofp_event.EventOFPStateChange,[MAIN_DISPATCHER, DEAD_DISPATCHER])
    def _state_change_handler(self, ev):
        datapath = ev.datapath
        if ev.state == MAIN_DISPATCHER:
            if datapath not in self.sws:
                #self.logger.debug('%s:register datapath: %016x', time.time() - self.s_time, datapath.id)
                self.sws.append((datapath,datapath.id))
        elif ev.state == DEAD_DISPATCHER:
            if datapath in self.sws:
                #self.logger.debug('%s:unregister datapath: %016x', time.time() - self.s_time, datapath.id)
                self.sws.remove((datapath,datapath.id))


    """
    Check if a switch output port is already connected to a direct link neighbor.
    In this case, returns False. It avoids links between non-neighbor switches.
    """
    def check_link(self,link_in, links_list):
        for link in links_list:
            if link[0] == link_in[0] and link[2] == link_in[2]:
                return False
        return True

    def get_sws_links_hosts (self):
        # Before update the topology, clean the previous one!
        self.links = []
        self.hosts = []
        self.net.clear()

        # get list of hosts
        host_list = get_host(self, None)
        self.hosts = [(host.mac, host.port.dpid, host.port.port_no) if host.mac < '00:00:00:00:00:ff' else '' for host in host_list]
        self.hosts = list(filter(lambda x: x != "", self.hosts))

        # update networkx topology with the hosts links
        for host in self.hosts:
            self.net.add_edge(host[0], host[1], weight=1, port=1)
            self.net.add_edge(host[1], host[0], weight=1, port=host[2])

        # get list of links between switches
        links_list = get_all_link(self)
        links=[(link.src.dpid,link.dst.dpid,link.src.port_no) for link in links_list]
        l = self.links
        for link in links:
            if self.check_link(link, l):
                self.links.append(link)

        # update networkx topology with the links between switches
        for link in self.links:
            self.net.add_edge(link[0], link[1], weight=1, port=link[2])

    def myfunction(self):
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
                print("************************************")
                print("Switches: ", self.sws)  # Print current switches in the network
                print("Network links: ", self.links)  # Print current links in the network
                print("Hosts: ", self.hosts)  # Print current hosts in the network

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
                    self.send_all_flow_rules_proactively()

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

      # Determine the input port based on the previous node in the path
      # Find the index of the current switch in the path
      index_current_dpid = p.index(dpid)
      # Identify the previous node in the path (before the current switch)
      prev_node = p[index_current_dpid - 1]
      # Get the port on the current switch (dpid) that connects to the previous node
      in_port = self.net[dpid][prev_node]['port']

      # Determine the output port based on the next node in the path
      # Identify the next node in the path (after the current switch)
      next_node = p[index_current_dpid + 1]
      # Get the port on the current switch (dpid) that connects to the next node
      out_port = self.net[dpid][next_node]['port']

      # Install a flow rule for the forward direction (src -> dst)
      # Match on the in_port, source MAC (src_mac), and destination MAC (dst_mac)
      match = parser.OFPMatch(in_port=in_port, dl_dst=dst_mac, dl_src=src_mac)
      # Action is to output the packet to the determined out_port
      actions = [parser.OFPActionOutput(out_port)]
      # Install the flow rule with priority 5
      self.add_flow(dp, 5, match, actions)

      # Install a flow rule for the reverse direction (dst -> src)
      # Match on the out_port, reverse the src_mac and dst_mac
      match = parser.OFPMatch(in_port=out_port, dl_dst=src_mac, dl_src=dst_mac)
      # Action is to output the packet to the input port (reverse path)
      actions = [parser.OFPActionOutput(in_port)]
      # Install the flow rule with priority 5
      self.add_flow(dp, 5, match, actions)

      # Install a flow rule for ARP Request Broadcast (specific to ARP traffic)
      # Match on the Ethernet type (dl_type=0x806 for ARP) and network protocol (nw_proto=1)
      match = parser.OFPMatch(dl_type=0x806, nw_proto=1)
      # Action is to flood the ARP requests across all ports
      actions = [parser.OFPActionOutput(ofproto.OFPP_FLOOD)]
      # Install the flow rule with priority 5
      self.add_flow(dp, 5, match, actions)

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
      # Loop through all possible pairs of hosts
      for host1 in self.hosts:
          for host2 in self.hosts:
              # Avoid creating paths from a host to itself
              if host1 != host2:
                  # Find all shortest paths between host1 and host2 using NetworkX
                  paths = nx.shortest_simple_paths(self.net, host1[0], host2[0])
                  # For each path found
                  for p in paths:
                      #self.logger.debug('%s:****Start to install a new end-to-end bidirectional path!****', time.time() - self.s_time)
                      # Loop through all nodes in the path (except the last one)
                      for i in range(len(p)-1):
                          # Find the corresponding switch in the list of switches (self.sws)
                          for sw in self.sws:
                              # If the switch matches a node in the path
                              if sw[1] == p[i]:
                                  # Install proactive flow rules for this switch along the path 'p'
                                  self.proactive_flow_rule_install(sw, p)
                      #print ("****Finish the installation of a new end-to-end path!****")
