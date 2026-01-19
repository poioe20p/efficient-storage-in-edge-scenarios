from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import networkx as nx
from sdn_controller.repositories.repositories.topology import TopologyRepository
from sdn_controller.repositories.models.topology import Host, Topology
from sdn_controller.models.mongodb_host import MongodbRouter
from eventlet import spawn_n

class CalculateGlobalTopology:
    def __init__(self):
        self._mongo_uri = MongodbRouter().get_simple_connection_string(add_app=True)
        self.topology_repository = TopologyRepository(self._mongo_uri)
        self.switchs: List[Any] = []
        self.links: List[Any] = []
        self.hosts: List[Host] = []
        self.mac_to_port: Dict[Any, Dict[str, int]] = {}
        self.last_topology_lan1_store_time: Optional[str] = None
        self.last_topology_lan2_store_time: Optional[str] = None
        self.net = nx.DiGraph()
        self._cached_snapshot: Optional[Dict[str, Any]] = None

    def _persist_topology_snapshot(self, topology: Topology) -> None:
        repo = TopologyRepository(self._mongo_uri)
        try:
            repo.insert_topology(topology)
        finally:
            repo.close()
        
    def run(self, local_topology_n1: Optional[Topology] = None, local_topology_n2: Optional[Topology] = None) -> Optional[Dict[str, Any]]:
        topology_n1 = self.topology_repository.get_topology("topology_lan1")
        topology_n2 = self.topology_repository.get_topology("topology_lan2")
        
        if topology_n1 is None or topology_n2 is None:
            print("At least one of the topology is missing can't create global topology now.")
            return None
        
        if local_topology_n1 and topology_n1.timestamp != local_topology_n1.timestamp:
            topology_n1 = local_topology_n1
            spawn_n(self._persist_topology_snapshot, local_topology_n1)
            
        
        if local_topology_n2 and topology_n2.timestamp != local_topology_n2.timestamp:
            topology_n2 = local_topology_n2
            spawn_n(self._persist_topology_snapshot, local_topology_n2)

        lan1_changed = self.last_topology_lan1_store_time != topology_n1.timestamp
        lan2_changed = self.last_topology_lan2_store_time != topology_n2.timestamp

        if not (lan1_changed or lan2_changed):
            if self._cached_snapshot is None:
                return None
            cached = dict(self._cached_snapshot)
            cached["changed"] = False
            return cached

        snapshot = self._build_snapshot(topology_n1, topology_n2)
        self.last_topology_lan1_store_time = topology_n1.timestamp
        self.last_topology_lan2_store_time = topology_n2.timestamp
        self._cached_snapshot = snapshot
        snapshot_with_flag = dict(snapshot)
        snapshot_with_flag["changed"] = True
        return snapshot_with_flag

    def _build_snapshot(self, topology_n1: Topology, topology_n2: Topology) -> Dict[str, Any]:
        self.switchs = list(dict.fromkeys(topology_n1.switchs + topology_n2.switchs))
        self.links = topology_n1.links + topology_n2.links
        self.hosts = topology_n1.hosts + topology_n2.hosts

        graph = nx.DiGraph()

        host_tuples: List[Tuple[str, str, int]] = []
        for host in self.hosts:
            host_tuples.append((host.mac, host.switch_dpid, host.port_no))
            graph.add_edge(host.mac, host.switch_dpid, weight=1, port=1)
            graph.add_edge(host.switch_dpid, host.mac, weight=1, port=host.port_no)

        for link in self.links:
            graph.add_edge(link.src_dpid, link.dst_dpid, weight=1, port=link.src_port_no)

        return {
            "graph": graph.copy(),
            "hosts": host_tuples,
            "links": list(self.links),
            "switchs": list(self.switchs),
        }

    def print_global_topology(self, global_snapshot: Dict[str, Any]) -> None:
        """Print a global topology snapshot with the same format as local topology logs."""
        if not global_snapshot:
            return

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{ts}] ************************************")

        changed = global_snapshot.get("changed")
        if changed is None:
            print(f"[{ts}] Global topology")
        else:
            print(f"[{ts}] Global topology (changed={changed})")

        switchs = global_snapshot.get("switchs") or []
        hosts = global_snapshot.get("hosts") or []
        links = global_snapshot.get("links") or []

        # Normalize link objects to the same tuple format used in local printing
        links_as_tuples: List[Any] = []
        for link in links:
            src_dpid = getattr(link, "src_dpid", None)
            dst_dpid = getattr(link, "dst_dpid", None)
            src_port_no = getattr(link, "src_port_no", None)
            if src_dpid is None or dst_dpid is None or src_port_no is None:
                links_as_tuples.append(link)
            else:
                links_as_tuples.append((src_dpid, dst_dpid, src_port_no))

        print(f"[{ts}] Switches:  {switchs}")
        print(f"[{ts}] Network links:  {links_as_tuples}")
        print(f"[{ts}] Hosts:  {hosts}")

        graph = global_snapshot.get("graph")
        if graph is None:
            return

        try:
            components = nx.number_weakly_connected_components(graph)
        except Exception:
            components = None

        print(
            f"[{ts}] Global summary: nodes={graph.number_of_nodes()} edges={graph.number_of_edges()} "
            f"weak_components={components}"
        )


