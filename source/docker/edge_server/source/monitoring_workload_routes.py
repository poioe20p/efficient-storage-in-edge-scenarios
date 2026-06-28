from __future__ import annotations

import time

from flask import Flask, jsonify, request
from pymongo.errors import PyMongoError
from werkzeug.exceptions import BadRequest

from compute import (
    TREND_WINDOW_SIZE,
    compute_dashboard_summary,
    compute_service_pressure,
    compute_trend,
    score_dashboard_urgency,
    score_device_severity,
    verify_fleet_integrity,
)
from edge_request_lifecycle import stage_local_request_event
from platform_cache import cached_collection
from vip_data_mongo_runtime import (
    _get_write_client,
    log_db_failure,
    run_with_request_lease,
    snapshot_normal_vip_config,
)


def register_monitoring_workload_routes(app: Flask, config, process_state) -> None:

    @app.route("/device_update", methods=["POST"])
    def device_update():
        """Write a pressure-level update for a device to the primary MongoDB.

        This endpoint bypasses the VIP-based read path and connects directly
        to the replica-set primary via a dedicated MongoClient.  Writes
        generate oplog traffic that stresses all replica-set members, making
        storage scale-up measurable.
        """
        data = request.get_json(force=True)
        device_id = data["device_id"]
        pressure = data.get("pressure_level", 0)
        lan = data.get("lan", "lan1")

        client = _get_write_client(lan)
        db = client[config.db_name]
        result = db.sensor_reports.update_one(
            {"_id": device_id},
            {"$set": {"pressure_level": pressure, "last_updated": time.time()}},
            upsert=True,
        )
        return jsonify({
            "matched": result.matched_count,
            "modified": result.modified_count,
            "upserted_id": str(result.upserted_id) if result.upserted_id else None,
        })

    @app.route("/device/<path:device_id>/latest", methods=["GET"])
    def device_latest(device_id: str):
        """Return the latest sensor report for a device."""

        node_id = request.args.get("node_id", "unknown")
        device_lan = device_id.split("::")[0]

        try:
            doc = run_with_request_lease(
                device_lan,
                op_name="sensor_reports.find_one",
                replay_safe=True,
                fn=lambda db: cached_collection(db, "sensor_reports").find_one({"_id": device_id}),
            )

            if doc is None:
                return jsonify({"error": "device not found", "device_id": device_id}), 404

            threshold_override = None
            if node_id != "unknown":
                node_lan = node_id.split("::")[0]
                registry = run_with_request_lease(
                    node_lan,
                    op_name="device_registry.find_one",
                    replay_safe=True,
                    fn=lambda db: cached_collection(db, "device_registry").find_one(
                        {"_id": node_id},
                        {"alert_config.threshold_override": 1},
                    ),
                )
                if registry:
                    dev_type = doc.get("device_type", "")
                    threshold_override = (
                        registry.get("alert_config", {})
                        .get("threshold_override", {})
                        .get(dev_type)
                    )

            value = doc.get("payload", {}).get("value")
            threshold = threshold_override or doc.get("metadata", {}).get("alert_threshold")
            severity_result = score_device_severity(
                value,
                threshold,
                doc.get("device_type", ""),
                device_id,
            )

            recent_events = process_state.local_request_state.recent_for_device(
                device_id,
                TREND_WINDOW_SIZE,
            )
            trend_result = compute_trend(recent_events)

            stage_local_request_event(
                request_kind="device_status",
                device_id=device_id,
                node_id=node_id,
                severity=severity_result["severity"],
                status=doc.get("payload", {}).get("status", "unknown"),
                tags=tuple(doc.get("tags") or ()),
            )

            doc["_id"] = str(doc["_id"])
            doc["alert"] = severity_result["alert"]
            doc["severity"] = severity_result
            doc["trend"] = trend_result
            return jsonify(doc), 200

        except PyMongoError as exc:
            log_db_failure("device_latest", exc)
            return jsonify({"error": "database error"}), 503

    @app.route("/service_pressure", methods=["GET"])
    def service_pressure():
        """Return a local summary of recent request activity seen by this edge."""

        try:
            window_min = float(
                request.args.get(
                    "window_min",
                    str(config.service_pressure_default_window_min),
                )
            )
            limit = int(
                request.args.get(
                    "limit",
                    str(config.service_pressure_default_limit),
                )
            )
        except ValueError as exc:
            raise BadRequest("window_min must be numeric and limit must be an integer") from exc

        if window_min <= 0:
            raise BadRequest("window_min must be greater than 0")
        if limit <= 0:
            raise BadRequest("limit must be greater than 0")

        limit = min(limit, 50)
        requested_window_seconds = window_min * 60
        now_epoch = time.time()
        cutoff_epoch = now_epoch - requested_window_seconds
        events, truncated = process_state.local_request_state.events_since_with_truncation(
            cutoff_epoch
        )
        retained_window_seconds = requested_window_seconds
        if truncated and events:
            oldest_retained_epoch = min(float(ev.get("timestamp", now_epoch)) for ev in events)
            retained_window_seconds = max(1.0, now_epoch - oldest_retained_epoch)

        response = compute_service_pressure(
            events,
            limit=limit,
            region=config.lan_id,
            window_seconds=retained_window_seconds,
        )
        response["window_min"] = window_min
        response["window_truncated"] = truncated
        response["retained_window_seconds"] = round(retained_window_seconds, 3)
        response["buffer_capacity_events"] = config.local_request_buffer_max_events
        return jsonify(response), 200

    @app.route("/dashboard/<node_id>", methods=["GET"])
    def dashboard(node_id: str):
        """Return the most urgent devices for a monitoring node."""

        limit = int(request.args.get("limit", "10"))
        node_lan = node_id.split("::")[0]

        try:
            registry = run_with_request_lease(
                node_lan,
                op_name="device_registry.find_one",
                replay_safe=True,
                fn=lambda db: cached_collection(db, "device_registry").find_one({"_id": node_id}),
            )

            if registry is None:
                return jsonify({"error": "node not found", "node_id": node_id}), 404

            subscribed_tags = registry.get("subscribed_tags", [])

            devices: list[dict] = []
            for lan in snapshot_normal_vip_config():
                devices.extend(
                    run_with_request_lease(
                        lan,
                        op_name="sensor_reports.find.dashboard",
                        replay_safe=True,
                        fn=lambda db, subscribed_tags=subscribed_tags: list(
                            cached_collection(db, "sensor_reports").find(
                                {"tags": {"$in": subscribed_tags}},
                                {
                                    "_id": 1,
                                    "device_type": 1,
                                    "tags": 1,
                                    "payload": 1,
                                    "metadata": 1,
                                    "region_origin": 1,
                                    "last_updated": 1,
                                },
                                batch_size=config.dashboard_candidate_limit,
                            ).sort("last_updated", -1).limit(config.dashboard_candidate_limit)
                        ),
                    )
                )

            devices = score_dashboard_urgency(devices)
            devices = devices[:limit]
            verify_fleet_integrity(devices, config.dashboard_integrity_work_factor)
            summary = compute_dashboard_summary(devices)

            stage_local_request_event(
                request_kind="dashboard",
                device_id=None,
                node_id=node_id,
                severity="normal",
                status="dashboard",
                tags=tuple(subscribed_tags),
            )

            for device in devices:
                device["_id"] = str(device["_id"])

            return jsonify(
                {
                    "node_id": node_id,
                    "subscribed_tags": subscribed_tags,
                    "devices": devices,
                    "summary": summary,
                }
            ), 200

        except PyMongoError as exc:
            log_db_failure("dashboard", exc)
            return jsonify({"error": "database error"}), 503