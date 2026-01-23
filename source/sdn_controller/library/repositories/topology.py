"""MongoDB persistence helpers for Topology snapshots."""

from dataclasses import asdict
from typing import Any, Dict, Optional
from pymongo import MongoClient
from sdn_controller.library.models.topology import Host, Topology, Link


class TopologyRepository:
	"""CRUD helper focused on a single topology document."""

	def __init__(
		self,
		mongo_uri: str,
		database: str = "app_db",
		collection: str = "topology",
	) -> None:
		self._client = MongoClient(mongo_uri, connect=False)
		self._collection = None
		self.database = database
		self.collection = collection

	def connect(self) -> None:
		"""Initialize the database/collection handle lazily."""
		if self._collection is None:
			db = self._client[self.database]
			self._collection = db[self.collection]

	def close(self) -> None:
		"""Close the MongoClient used by this repository."""
		if self._client:
			self._client.close()

	# ------------------------------------------------------------------
	# CRUD helpers
	# ------------------------------------------------------------------
	def insert_topology(self, topology: Topology) -> str:
		"""Insert a topology snapshot (overwrites any document with same id)."""
		self.connect()
		doc = self._topology_to_doc(topology)
		self._collection.replace_one({"_id": doc["_id"]}, doc, upsert=True)
		return doc["_id"]

	def update_topology(self, topology: Topology) -> bool:
		"""Update fields of an existing topology document."""
		self.connect()
		doc = self._topology_to_doc(topology)
		topology_id = doc.pop("_id", topology.id)
		result = self._collection.update_one({"_id": topology_id}, {"$set": doc})
		return result.matched_count > 0

	def delete_topology(self, topology_id: str) -> bool:
		"""Remove the stored topology with the provided identifier."""
		self.connect()
		result = self._collection.delete_one({"_id": topology_id})
		return result.deleted_count > 0

	def get_topology(self, topology_id: str = "current") -> Optional[Topology]:
		"""Fetch a topology snapshot, returning None if absent."""
		self.connect()
		doc = self._collection.find_one({"_id": topology_id})
		if not doc:
			return None
		return self._doc_to_topology(doc)

	# ------------------------------------------------------------------
	# Serialization helpers
	# ------------------------------------------------------------------
	@staticmethod
	def _topology_to_doc(topology: Topology) -> Dict[str, Any]:
		doc = asdict(topology)
		doc["_id"] = doc.pop("id")
		return doc

	@staticmethod
	def _doc_to_topology(doc: Dict[str, Any]) -> Topology:
		hosts = [Host(**host_doc) for host_doc in doc.get("hosts", [])]
		links = [Link(**link_doc) for link_doc in doc.get("links", [])]
		return Topology(
			id=doc.get("_id") or doc.get("id"),
			hosts=hosts,
			links=links,
			switchs=doc.get("switchs", []),
			ttl=doc.get("ttl", 0.0),
			timestamp=doc.get("timestamp", ""),
			controller_name=doc.get("controller_name", "")
		)
