# Implementation Plan — v4 Code Changes

**Date**: 2026-06-29
**For**: `experiment_plan_v4.md`
**Target agent**: Implementation agent — make these changes, then hand back for verification + image rebuild + run execution.

---

## Change Summary

| # | File | Change |
|---|------|--------|
| 1 | `source/scripts/testing/phases.json` | v4 phase profile |
| 2 | `source/docker/edge_server/source/monitoring_workload_routes.py` | Add `POST /device_aggregate` endpoint + store 1KB `extra` field in device_update |
| 3 | `source/docker/edge_server/source/vip_data_mongo_runtime.py` | **No changes needed** (existing `run_with_request_lease` callback contract suffices for aggregation) |
| 4 | `source/scripts/testing/traffic_generator.py` | Add `device_aggregate` request type + body; add 1KB `extra` field to device_update body |
| 5 | `source/docker/edge_server/source/edge_server_config.py` | **No mandatory changes** — aggregation threshold is per-request, not config-driven |

---

## 1. `source/scripts/testing/phases.json`

Replace entire file. Key differences from v3:

- **storage_storm** replaces storage_hotspot: mix now includes `device_aggregate` at 20% and `device_update` at 30%. Rate increased to 4.0.
- **tier1_hotspot** replaces both tier1_hotspot_n1 and tier1_hotspot_n2: single bidirectional phase, no `hotspot_direction`. Mix includes 5% aggregation and 5% writes.
- **inter_hotspot_cooldown** kept at 300s.
- **compute_spike** unchanged from v3.
- **cooldown** unchanged.

```json
{
  "phases": [
    {
      "name": "baseline",
      "duration_s": 60,
      "rate_per_client": 1.0,
      "cross_region_ratio": 0.0,
      "client_fraction": 0.5,
      "mix": {
        "device_status": 0.60,
        "dashboard": 0.25,
        "service_pressure": 0.15
      }
    },
    {
      "name": "storage_storm",
      "duration_s": 240,
      "rate_per_client": 4.0,
      "cross_region_ratio": 0.90,
      "hotspot_direction": "",
      "client_fraction": 1.0,
      "mix": {
        "device_status": 0.35,
        "dashboard": 0.10,
        "service_pressure": 0.05,
        "device_update": 0.30,
        "device_aggregate": 0.20
      }
    },
    {
      "name": "tier1_hotspot",
      "duration_s": 180,
      "rate_per_client": 5.0,
      "cross_region_ratio": 0.95,
      "hotspot_direction": "",
      "client_fraction": 1.0,
      "mix": {
        "device_status": 0.80,
        "dashboard": 0.05,
        "service_pressure": 0.05,
        "device_update": 0.05,
        "device_aggregate": 0.05
      }
    },
    {
      "name": "inter_hotspot_cooldown",
      "duration_s": 300,
      "rate_per_client": 1.0,
      "cross_region_ratio": 0.0,
      "client_fraction": 0.10,
      "mix": {
        "device_status": 0.60,
        "dashboard": 0.25,
        "service_pressure": 0.15
      }
    },
    {
      "name": "compute_spike",
      "duration_s": 180,
      "rate_per_client": 4.0,
      "cross_region_ratio": 0.05,
      "hotspot_direction": "",
      "client_fraction": 1.0,
      "mix": {
        "device_status": 0.20,
        "dashboard": 0.65,
        "service_pressure": 0.15
      }
    },
    {
      "name": "cooldown",
      "duration_s": 120,
      "rate_per_client": 1.0,
      "cross_region_ratio": 0.0,
      "client_fraction": 0.10,
      "mix": {
        "device_status": 0.60,
        "dashboard": 0.25,
        "service_pressure": 0.15
      }
    }
  ]
}
```

---

## 2. `source/docker/edge_server/source/monitoring_workload_routes.py`

### 2a. Modify existing `device_update` route — store `extra` field

The `device_update` route currently `$set`s only `pressure_level` and `last_updated`. Add `extra` to the `$set` so the 1KB payload is persisted and enters the oplog:

```python
        result = db.sensor_reports.update_one(
            {"_id": device_id},
            {"$set": {
                "pressure_level": pressure,
                "last_updated": time.time(),
                "extra": data.get("extra", ""),
            }},
            upsert=True,
        )
```

### 2b. Add new `POST /device_aggregate` route

Add after the `device_update` route (after line ~55). The aggregation endpoint:

- Accepts `POST /device_aggregate` with JSON body: `{"lan": "lan1|lan2"}`
- Uses the VIP read path (NOT the write client) — calls `run_with_request_lease` on the target LAN's MongoDB
- Runs a `$match` → `$group` → `$sort` pipeline on the `sensor_reports` collection
- `$match`: filters devices with `pressure_level > 50` (configurable)
- `$group`: groups by `device_type`, computes average pressure and count
- `$sort`: descending by average pressure

**Add this route** inside `register_monitoring_workload_routes()`, after the `device_update` route:

```python
    @app.route("/device_aggregate", methods=["POST"])
    def device_aggregate():
        """Run an aggregation pipeline on the MongoDB collection via VIP.

        This endpoint uses the standard VIP-based read path.  The
        aggregation performs a full-collection scan + grouping + sort,
        which generates real MongoDB CPU work (not just quick point reads).
        """
        data = request.get_json(force=True)
        lan = data.get("lan", "lan1")
        pressure_threshold = data.get("pressure_threshold", 50)

        pipeline = [
            {"$match": {"pressure_level": {"$gt": pressure_threshold}}},
            {"$group": {
                "_id": "$device_type",
                "avg_pressure": {"$avg": "$pressure_level"},
                "count": {"$sum": 1},
            }},
            {"$sort": {"avg_pressure": -1}},
        ]

        try:
            results = run_with_request_lease(
                lan,
                op_name="sensor_reports.aggregate",
                replay_safe=False,
                fn=lambda db: list(
                    db["sensor_reports"].aggregate(pipeline)
                ),
            )
            # Convert ObjectId and non-serialisable types
            for doc in results:
                if "_id" in doc:
                    doc["_id"] = str(doc["_id"])
            return jsonify({"results": results, "count": len(results)})
        except PyMongoError as e:
            log_db_failure("aggregate", e)
            return jsonify({"error": "aggregation failed", "detail": str(e)}), 500
```

---

## 3. `source/docker/edge_server/source/vip_data_mongo_runtime.py`

The `run_with_request_lease` function already supports generic `fn=lambda db: ...` callbacks. The aggregation endpoint uses this pattern — no changes needed to the runtime. The `lambda db: list(db["sensor_reports"].aggregate(pipeline))` call will use whatever `db` object `run_with_request_lease` provides (the current VIP-selected MongoDB connection).

**No changes needed** to this file. The existing `run_with_request_lease` contract already supports the aggregation use case.

---

## 4. `source/scripts/testing/traffic_generator.py`

Add `device_aggregate` as a new request type. Three locations need changes:

### 4a. `pick_target()` — add elif for device_aggregate

After the `device_update` elif block (~line 144), add:

```python
    elif request_type == "device_aggregate":
        # Aggregation is a collection-level operation — no specific device needed.
        # Target region is always local (aggregation runs on the client's own
        # LAN's MongoDB; the aggregator doesn't cross regions).
        return {
            "device_id": "",
            "node_id": "",
            "target_region": client_lan,
        }
```

### 4b. `build_url()` — add elif for device_aggregate

After the `device_update` elif block (~line 157), add:

```python
    elif request_type == "device_aggregate":
        return f"{base}/device_aggregate"
```

### 4c. In `client_loop()` — expand device_update body + add body for device_aggregate

**Modify the existing device_update body block** (~line 250) to include a 1KB `extra` field. This generates a 1024-byte string of 'x' characters per write, increasing each write's oplog entry from ~100 bytes to ~1KB:

```python
        if req_type == "device_update":
            extra_payload = "x" * 1024  # 1KB of padding to inflate oplog entries
            body = (
                f'{{"device_id":"{target["device_id"]}",'
                f'"pressure_level":{random.randint(0,100)},'
                f'"lan":"{client_lan}",'
                f'"extra":"{extra_payload}"}}'
            )
```

After the device_update body block, add for device_aggregate:

```python
        if req_type == "device_aggregate":
            body = (
                f'{{"lan":"{client_lan}",'
                f'"pressure_threshold":{random.randint(30,70)}}}'
            )
```

---

## 5. `source/docker/edge_server/source/edge_server_config.py`

No mandatory changes. The aggregation pipeline's `$match` threshold is passed per-request by the client, not hardcoded. If you want a configurable default threshold, add:

```python
# Aggregation pipeline default pressure threshold
aggregation_pressure_threshold: int = int(os.environ.get("AGGREGATION_PRESSURE_THRESHOLD", "50"))
```

But this is optional — the endpoint already accepts `pressure_threshold` in the request body.

---

## 6. DEVICES=6000 — Launch Argument Only

No code changes needed. The experiment launch command passes `DEVICES=6000` to the Makefile, which seeds 6000 devices instead of 600. The `setup_test_data` target in the Makefile reads this variable.

---

## Verification Checklist

After implementation, before launching:

- [ ] `device_aggregate` route returns valid JSON when curl'd manually
- [ ] `device_update` route **stores the `extra` field** — verify by querying MongoDB after a write
- [ ] `traffic_generator.py` picks `device_aggregate` from mix
- [ ] `traffic_generator.py` includes 1KB `extra` payload in device_update body
- [ ] `phases.json` is valid JSON (no trailing commas)
- [ ] Rebuild `edge_server` image: `sudo bash source/scripts/build_images.sh edge_server`
- [ ] Smoke-test: `sudo docker run --rm edge_server:latest grep -c 'device_aggregate' /source/monitoring_workload_routes.py` returns ≥3 (route def + body parsing + pipeline)
- [ ] Smoke-test: `sudo docker run --rm edge_server:latest grep -c 'extra' /source/monitoring_workload_routes.py` returns ≥1 (extra field stored in $set)
- [ ] Smoke-test: `sudo docker run --rm edge_server:latest grep -c 'device_aggregate' /source/monitoring_workload_routes.py` returns ≥3
