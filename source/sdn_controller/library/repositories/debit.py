from dataclasses import asdict, fields
from typing import Any, Dict, Optional

from bson import ObjectId
from pymongo import MongoClient
from sdn_controller.library.models.debit import DebitStats

class DebitRepository:
    def __init__(
        self,
        
        mongo_uri: str,
        database: str = "app_db",
        collection: str = "debits",
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
    
    def insert_debit(self, debit: DebitStats) -> str:
        """Insert a debit record."""
        self.connect()
        doc = asdict(debit)
        result = self._collection.insert_one(doc)
        return str(result.inserted_id)

    def upsert_debit_by_lan_id(self, debit: DebitStats) -> str:
        """Insert or replace the latest debit snapshot for a given lan_id.

        Uses MongoDB's `_id` as the lan_id so reads are O(1) and always return
        the latest snapshot.
        """
        self.connect()
        doc = asdict(debit)
        doc["_id"] = debit.lan_id
        self._collection.replace_one({"_id": debit.lan_id}, doc, upsert=True)
        return debit.lan_id
    
    def update_debit(self, debit_id: str, debit: DebitStats) -> bool:
        """Update fields of an existing debit record."""
        self.connect()
        doc = asdict(debit)
        result = self._collection.update_one({"_id": self._coerce_object_id(debit_id)}, {"$set": doc})
        return result.matched_count > 0
    
    def get_debit(self, debit_id: str) -> Optional[DebitStats]:
        """Fetch a debit record by its identifier."""
        self.connect()
        doc = self._collection.find_one({"_id": self._coerce_object_id(debit_id)})
        if doc:
            return self._doc_to_debit(doc)
        return None

    def get_debit_by_lan_id(self, lan_id: str) -> Optional[DebitStats]:
        """Fetch the latest debit snapshot for a LAN (stored under `_id==lan_id`)."""
        return self.get_debit(lan_id)

    @staticmethod
    def _coerce_object_id(value: str) -> Any:
        """Convert a hex string into an ObjectId if possible."""
        try:
            return ObjectId(value)
        except Exception:
            return value

    # ------------------------------------------------------------------
    # Helpers to convert between dataclass and MongoDB document
    # ------------------------------------------------------------------
    
    @staticmethod
    def _doc_to_debit(doc: Dict[str, Any]) -> DebitStats:
        """Convert a MongoDB document to a DebitStats dataclass."""
        allowed_port_fields = {f.name for f in fields(DebitStats.SwitchPortStats)}

        port_stats_list = []
        for port in doc.get("port", []) or []:
            if not isinstance(port, dict):
                continue

            # Ignore unknown keys to tolerate schema evolution.
            cleaned = {k: v for k, v in port.items() if k in allowed_port_fields}
            port_stats_list.append(DebitStats.SwitchPortStats(**cleaned))

        lan_id = doc.get("lan_id") or doc.get("_id")
        debit_kwargs: Dict[str, Any] = {
            "lan_id": lan_id,
            "port": port_stats_list,
        }

        if "time_stamp" in doc:
            debit_kwargs["time_stamp"] = doc["time_stamp"]

        return DebitStats(**debit_kwargs)