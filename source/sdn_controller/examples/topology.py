# Import necessary modules from Ryu
from ryu.base import app_manager  # Base class for Ryu applications
from ryu.topology import event, switches  # For topology events and switch management
from ryu.topology.api import get_all_switch, get_all_link, get_host  # API for retrieving switches, links, and hosts
from ryu.lib import hub  # For managing periodic tasks

from ryu.controller.handler import MAIN_DISPATCHER, DEAD_DISPATCHER  # Ryu states for OpenFlow communication
from ryu.controller.handler import set_ev_cls  # Event decorator to specify when a OpenFlow event function should be triggered
from ryu.controller import ofp_event  # OpenFlow protocol events

# Class that represents the topology management application
class Topology(app_manager.RyuApp):
    def __init__(self):
        """
        Initializes the topology app:
        - Starts a background task (self.myfunction)
        - Initializes counters, lists of switches, links, hosts, and an interval for periodic tasks
        """
        super(Topology, self).__init__()
        # Launch a background task (self.myfunction) that periodically runs
        hub.spawn(self.myfunction)

        # Counter for keeping track of iterations
        self.cnt = 0

        # Lists to store switches, links, and hosts in the network
        self.sws = []
        self.links = []
        self.hosts = []

        # Time interval in seconds for the periodic task (2 seconds)
        self.INTERVAL = 2

    # Event handler to track state changes in OpenFlow switches
    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def _state_change_handler(self, ev):
        """
        Handles the state change of OpenFlow switches:
        - Adds a switch to the list when it connects (enters MAIN_DISPATCHER)
        - Removes a switch when it disconnects (enters DEAD_DISPATCHER)
        """
        datapath = ev.datapath  # Reference to the switch's datapath object
        if ev.state == MAIN_DISPATCHER:  # Switch connected and ready
            if datapath not in self.sws:
                # Add the switch to the list with its datapath and dpid (datapath ID)
                self.sws.append((datapath, datapath.id))
        elif ev.state == DEAD_DISPATCHER:  # Switch disconnected
            if datapath in self.sws:
                # Remove the switch from the list if it was previously added
                self.sws.remove((datapath, datapath.id))

    """
    Check if a switch output port is already connected to a direct link neighbor.
    If such a link already exists, returns False to avoid adding the same link twice.
    """
    def check_link(self, link_in, links_list):
        # Iterate through the current list of links and check if the link already exists
        for link in links_list:
            if link[0] == link_in[0] and link[2] == link_in[2]:  # Compare source switch and source port
                return False  # Link already exists
        return True  # Link is new

    # Function to refresh the lists of switches, links, and hosts
    def get_sws_links_hosts(self):
        """
        This method fetches and updates the list of hosts and links in the current topology:
        - Hosts are filtered to exclude those with MAC addresses >= '00:00:00:00:00:ff'.
        - Links between switches are checked for duplication before adding.
        """
        # Get the list of all hosts and filter based on MAC addresses
        host_list = get_host(self, None)
        
        # Each host is represented as a tuple (MAC, switch DPID, port number) or else
        self.hosts = [(host.mac, host.port.dpid, host.port.port_no) for host in host_list if host.mac < '00:00:00:00:00:ff']
        self.hosts = list(filter(lambda x: x != "", self.hosts))  # Remove empty entries

        # Get the list of all links between switches
        links_list = get_all_link(self)
        links = [(link.src.dpid, link.dst.dpid, link.src.port_no, link.dst.port_no) for link in links_list]

        # Loop through all the links and add them to self.links if they are new
        l = self.links
        for link in links:
            if self.check_link(link, l):  # Only add the link if it's not a duplicate
                self.links.append(link)

    # Function that runs periodically in the background to monitor and print the network state
    def myfunction(self):
        """
        Background task that:
        - Sleeps for a set interval (self.INTERVAL)
        - Refreshes the network topology (switches, links, hosts)
        - Prints the current topology every 5 iterations
        """
        while True:
            try:
                # Sleep for a specified interval before refreshing the topology
                hub.sleep(self.INTERVAL)

                # Refresh the current topology (switches, links, and hosts)
                self.get_sws_links_hosts()

                # Every 5 iterations, print the current network state (switches, links, and hosts)
                if self.cnt % 5 == 0:
                    self.cnt = 0  # Reset the counter
                    print("************************************")
                    print("Switches: ", self.sws)  # Print the current switches in the network
                    print("Network links: ", self.links)  # Print the current links in the network
                    print("Hosts: ", self.hosts)  # Print the current hosts in the network

                # Increment the counter for the next iteration
                self.cnt = self.cnt + 1

            # Handle KeyboardInterrupt (Ctrl+C) to stop the application gracefully
            except KeyboardInterrupt:
                print("Closing ....")
                pass
