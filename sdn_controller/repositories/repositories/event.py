from dataclasses import asdict
from typing import Optional
from pymongo import MongoClient
from sdn_controller.repositories.models.event import Event


class EventRepository:
    """Simple CRUD helper for Event documents keyed by dpid."""

    def __init__(
        self,
        mongo_uri: str,
        database: str = "app_db",
        collection: str = "events"
    ) -> None:
        self._client = MongoClient(mongo_uri, connect=False)
        self._collection = None
        self.database = database
        self.collection = collection
        
    def connect(self) -> None:
        """Establish the MongoDB connection."""
        if self._collection is None:
            db = self._client[self.database]
            self._collection = db[self.collection]

    def insert_event(self, event: Event) -> str:
        """Insert or replace an Event. Returns the document _id."""
        self.connect()
        doc = asdict(event)
        doc["_id"] = event.dpid
        # Include the shard key (dpid) in the replace filter so mongos can target the write
        self._collection.replace_one({"_id": event.dpid, "dpid": event.dpid}, doc, upsert=True)
        return str(event.dpid)

    def get_event(self, dpid: float) -> Optional[Event]:
        """Fetch an Event by dpid, returning None when absent."""
        self.connect()
        doc = self._collection.find_one({"_id": dpid})
        if not doc:
            return None
        doc.pop("_id", None)
        return Event(**doc)

    def delete_event(self, dpid: float) -> bool:
        """Delete an Event by dpid. Returns True when a document was removed."""
        self.connect()
        result = self._collection.delete_one({"_id": dpid})
        return result.deleted_count > 0

    def close(self) -> None:
        """Close the underlying MongoClient if this instance created it."""
        if self._client:
            self._client.close()