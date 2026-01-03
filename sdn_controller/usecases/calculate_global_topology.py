from typing import Any, Dict, List, Optional, Tuple

import networkx as nx

from sdn_controller.repositories.repositories.topology import TopologyRepository
from sdn_controller.repositories.models.topology import Host, Topology
from sdn_controller.models.mongodb_host import MongodbRouter


class CalculateGlobalTopology:
    def __init__(self):
        self.topology_repository = TopologyRepository(
            MongodbRouter().get_simple_connection_string(
                add_app=True
            )
        )
        self.switchs: List[Any] = []
        self.links: List[Any] = []
        self.hosts: List[Host] = []
        self.mac_to_port: Dict[Any, Dict[str, int]] = {}
        self.last_topology_lan1_store_time: Optional[str] = None
        self.last_topology_lan2_store_time: Optional[str] = None
        self.net = nx.DiGraph()
        self._cached_snapshot: Optional[Dict[str, Any]] = None
        
    def run(self):
        topology_n1 = self.topology_repository.get_topology("topology_lan1")
        topology_n2 = self.topology_repository.get_topology("topology_lan2")
        
        if topology_n1 is None or topology_n2 is None:
            print("At least one of the topology is missing can't create global topology now.")
            return None

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


