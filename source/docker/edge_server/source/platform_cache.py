"""Platform cache wrapper for selective Tier 1 sync.

Per-request telemetry fields produced here (``access_records``, ``op_counts``,
``time_db_ms_per_lan``) are documented in
``docs/operation/telemetry/telemetry_overview.md``.

This module owns three pieces of state so that ``cached_collection()`` can read
them without creating a circular import with the Flask app:

1. ``_WRITE_OPS`` — read/write classifier. Duplicated verbatim in
   ``aggregator.py`` and ``hotness.py``; they're separately-deployed images
   with no shared import root.
2. ``_TIER1_REGISTRY`` — ``{owner_lan: (MongoClient, {collection: frozenset[hot_doc_id]})}``,
   populated by ``set_tier1_manifest()`` which the Flask ``PUT /tier1_manifest``
   route calls.
3. ``_owner_lan: ContextVar[str]`` — set by the edge server's ``timed_db(lan)``
   context manager; read by ``cached_collection()`` to tag accesses with their
   owning LAN.

Per-request accumulation is via Flask's ``g``: the wrapper appends records
into ``g.access_records`` and ``g.op_counts`` on each call; ``telemetry.py``
ships them verbatim on the existing per-request event.
"""
from __future__ import annotations

import logging
import os
import threading
from collections.abc import Mapping
from contextvars import ContextVar
from typing import Any

from flask import g
from pymongo import MongoClient
from pymongo.errors import PyMongoError

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants shared with the controller
# ---------------------------------------------------------------------------
# Duplicated in aggregator.py and hotness.py (separately-deployed images).
_WRITE_OPS: frozenset[str] = frozenset({
    "insert_one", "insert_many",
    "update_one", "update_many", "replace_one",
    "delete_one", "delete_many",
    "bulk_write",
    "find_one_and_update", "find_one_and_replace", "find_one_and_delete",
})


# ---------------------------------------------------------------------------
# Owner-LAN propagation (set by timed_db(lan) in app.py)
# ---------------------------------------------------------------------------
# ContextVar (not threading.local / global):
#   - safe under threads AND asyncio tasks;
#   - nests correctly: a nested ``timed_db("lanB")`` inside ``timed_db("lanA")``
#     restores "lanA" on exit via the token returned by set();
#   - no cross-request leakage — each Flask request runs in its own context.
_owner_lan: ContextVar[str] = ContextVar("_owner_lan")


# ---------------------------------------------------------------------------
# Tier 1 manifest registry
# ---------------------------------------------------------------------------
_TIER1_REGISTRY: dict[str, tuple[MongoClient, dict[str, frozenset]]] = {} # {owner_lan: (client, {collection: hot_doc_ids})}
_tier1_lock = threading.Lock()


def set_tier1_manifest(owner_lan: str, host: str | None,
                       collections: dict[str, list] | None) -> None:
    """Install / replace / revoke the Tier 1 manifest for ``owner_lan``.

    Called from the Flask ``PUT /tier1_manifest`` route. Passing ``host=None``
    or an empty ``collections`` dict revokes the manifest and closes the
    per-owner MongoClient.
    """
    collections = collections or {}
    with _tier1_lock:
        old = _TIER1_REGISTRY.pop(owner_lan, None)
        if old is not None:
            try:
                old[0].close()
            except Exception:
                log.debug("tier1 client close failed for %s", owner_lan)
        if host and collections:
            client = MongoClient(
                f"mongodb://{host}/",
                maxPoolSize=1,
                serverSelectionTimeoutMS=1000,
                directConnection=True,
            )
            _TIER1_REGISTRY[owner_lan] = (
                client,
                {c: frozenset(ids) for c, ids in collections.items()},
            )
    log.info("tier1_manifest updated owner=%s host=%s colls=%s",
             owner_lan, host, list(collections))


# ---------------------------------------------------------------------------
# Wrapped pymongo collection
# ---------------------------------------------------------------------------
class _CachedCollection:
    """Narrow wrapper around a pymongo ``Collection``.

    Intercepts the methods that contribute to the read/write ratio so they
    feed ``g.op_counts`` and (for cross-region point reads) ``g.access_records``.
    Everything else passes through via ``__getattr__``.
    """

    def __init__(self, coll, consumer_lan: str, owner_lan: str) -> None:
        self._coll = coll
        self._consumer_lan = consumer_lan
        self._owner_lan = owner_lan

    # ---- per-request bookkeeping (request-scoped via flask.g) -------------
    def _record_access(self, doc_id: Any) -> None:
        # Only cross-region point reads feed the hotness top-N. Same-region
        # reads and complex filters are ignored here but still counted by
        # _record_op so total_hits can be derived downstream.
        if doc_id is None or self._consumer_lan == self._owner_lan:
            return
        try:
            records = getattr(g, "access_records", None)
            if records is None:
                records = []
                g.access_records = records
            records.append({
                "owner_lan":  self._owner_lan,
                "collection": self._coll.name,
                "doc_id":     doc_id,
            })
        except RuntimeError:
            # Outside Flask request context — nothing to record.
            pass

    def _record_op(self, op_type: str) -> None:
        try:
            ops = getattr(g, "op_counts", None)
            if ops is None:
                ops = {}
                g.op_counts = ops
            by_coll = ops.setdefault(self._owner_lan, {}).setdefault(self._coll.name, {})
            by_coll[op_type] = by_coll.get(op_type, 0) + 1
        except RuntimeError:
            pass

    # ---- Tier 1 point-lookup gate (fail-open) -----------------------------
    def _try_tier1(self, filter_: Any):        
        if not isinstance(filter_, Mapping) or list(filter_.keys()) != ["_id"]:
            return None
        entry = _TIER1_REGISTRY.get(self._owner_lan)
        if entry is None:
            return None
        # client is the mongo client connected to the tier 1 replica
        client, hot_by_coll = entry
        hot = hot_by_coll.get(self._coll.name)
        key = filter_["_id"]
        if not hot or key not in hot:
            return None
        try:
            # In here self._coll is not used directly as it points to VIP_DATA
            # instead is used just to accurately populate the database and collection name
            doc = client[self._coll.database.name][self._coll.name].find_one({"_id": key})
            if doc is not None:
                log.debug("served_from_tier=1 owner=%s coll=%s key=%r",
                          self._owner_lan, self._coll.name, key)
            return doc
        except PyMongoError as exc:
            log.debug("tier1 miss owner=%s coll=%s key=%r: %s — falling back to VIP_DATA",
                      self._owner_lan, self._coll.name, key, exc)
            return None

    # ---- wrapped pymongo surface ------------------------------------------
    # Record the op type for every call, even those that don't feed the hotness top-N
    # and then proceed with the normal call. This keeps the op_counters accurate for write_ratio()
    def find_one(self, filter=None, *args, **kwargs):
        self._record_op("find_one")
        self._record_access(_extract_doc_id(filter))
        hit = self._try_tier1(filter)
        if hit is not None:
            return hit
        return self._coll.find_one(filter, *args, **kwargs)

    def find(self, filter=None, *args, **kwargs):
        self._record_op("find")
        return self._coll.find(filter, *args, **kwargs)

    def aggregate(self, pipeline, *args, **kwargs):
        self._record_op("aggregate")
        return self._coll.aggregate(pipeline, *args, **kwargs)

    def insert_one(self, doc, *args, **kwargs):
        self._record_op("insert_one")
        return self._coll.insert_one(doc, *args, **kwargs)

    def insert_many(self, docs, *args, **kwargs):
        self._record_op("insert_many")
        return self._coll.insert_many(docs, *args, **kwargs)

    def update_one(self, filter, update, *args, **kwargs):
        self._record_op("update_one")
        return self._coll.update_one(filter, update, *args, **kwargs)

    def update_many(self, filter, update, *args, **kwargs):
        self._record_op("update_many")
        return self._coll.update_many(filter, update, *args, **kwargs)

    def replace_one(self, filter, replacement, *args, **kwargs):
        self._record_op("replace_one")
        return self._coll.replace_one(filter, replacement, *args, **kwargs)

    def delete_one(self, filter, *args, **kwargs):
        self._record_op("delete_one")
        return self._coll.delete_one(filter, *args, **kwargs)

    def delete_many(self, filter, *args, **kwargs):
        self._record_op("delete_many")
        return self._coll.delete_many(filter, *args, **kwargs)

    def bulk_write(self, requests, *args, **kwargs):
        self._record_op("bulk_write")
        return self._coll.bulk_write(requests, *args, **kwargs)

    def find_one_and_update(self, filter, update, *args, **kwargs):
        self._record_op("find_one_and_update")
        return self._coll.find_one_and_update(filter, update, *args, **kwargs)

    def find_one_and_replace(self, filter, replacement, *args, **kwargs):
        self._record_op("find_one_and_replace")
        return self._coll.find_one_and_replace(filter, replacement, *args, **kwargs)

    def find_one_and_delete(self, filter, *args, **kwargs):
        self._record_op("find_one_and_delete")
        return self._coll.find_one_and_delete(filter, *args, **kwargs)

    # Unwrapped pass-through — count_documents, create_index, etc. reach the
    # underlying Collection directly and do not feed op_counters.
    def __getattr__(self, name: str):
        return getattr(self._coll, name)


def _extract_doc_id(filter_: Any) -> Any:
    """Best-effort point-lookup key.

    Returns the ``_id`` value iff ``filter_`` is a single-key ``{"_id": X}``
    mapping with a hashable scalar; otherwise ``None`` (complex filter).
    """
    if not isinstance(filter_, Mapping) or list(filter_.keys()) != ["_id"]:
        return None
    key = filter_["_id"]
    if isinstance(key, Mapping):
        return None
    try:
        hash(key)
    except TypeError:
        return None
    return key


def cached_collection(db, name: str) -> _CachedCollection:
    """Entry point for edge-server app code.

    Must be called from inside an active ``timed_db(...)`` block so
    ``_owner_lan.get()`` resolves; raises ``LookupError`` otherwise.
    """
    return _CachedCollection(
        db[name],
        consumer_lan=os.environ.get("LAN_ID", ""),
        owner_lan=_owner_lan.get(),
    )
