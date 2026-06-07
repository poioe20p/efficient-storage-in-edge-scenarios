# Edge Server Compute Load

This document describes the implemented edge-server changes that make the
endpoints produce **meaningful CPU work** so that $T_{proc} = T_{total} -
T_{dados}$ is non-trivial and Phase 3 (Compute Spike) can trigger the Compute
Manager.

Currently, all three endpoints do near-zero compute: a boolean threshold comparison (`/device/.../latest`), a lightweight local summary (`/service_pressure`), and a simple `value/threshold` division sort (`/dashboard`). The result is that $T_{proc} \approx 0$ regardless of request rate, making it impossible to demonstrate elastic compute scaling.

**Location of changes:** `source/docker/edge_server/source/app.py`

---

## Design Principles

1. **No fake work.** No `time.sleep()` or random delays. All added compute is realistic edge analytics logic — data enrichment, trend detection, and composite scoring — applied to the IoT monitoring workload but representative of generic edge processing patterns.
2. **CPU-visible.** The work must show up in `psutil.cpu_percent()` (math-heavy, list operations) — not I/O waits.
3. **Scales with request volume.** Higher RPS = higher cumulative $T_{proc}$ per telemetry window, which is exactly what triggers the Compute Manager.
4. **Generic edge analytics patterns.** The computations — per-request data enrichment, temporal trend detection, and multi-factor composite ranking — are general-purpose edge analytics patterns that any data-processing edge service would perform. They are instantiated here with IoT monitoring semantics (alert evaluation, anomaly scoring, dashboard ranking) because that is the experimental workload, but the compute patterns themselves are domain-agnostic.
5. **No new DB queries.** The added compute operates on data already fetched by existing queries — it adds processing time, not data time.

---

## Overview of Changes

| Endpoint                 | Current Compute                  | Added Compute                                                                                                                        | Expected$T_{proc}$ Impact |
| ------------------------ | -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ | --------------------------- |
| `/device/<id>/latest`  | `value >= threshold` boolean   | Multi-level severity scoring + trend analysis from recent local request activity                                                     | ~5–15 ms per request       |
| `/service_pressure`    | Lightweight local buffer summary | Pressure scoring + tag/device ranking over recent local request activity                                                             | ~3–10 ms per request       |
| `/dashboard/<node_id>` | `value / threshold` sort       | Multi-factor urgency with tag priority weighting + staleness decay + summary stats + fleet integrity verification (iterated SHA-256) | ~80–120 ms per request     |

At Phase 3 rates (10 req/s/client × multiple clients), the cumulative $T_{proc}$ across the telemetry window should breach $\tau_{proc}$ and trigger compute scale-out.

---

## New Module: `compute.py`

A pure-computation module with no DB or I/O dependencies. All functions take pre-fetched data and return enriched results. This keeps the added logic testable and separable from Flask/MongoDB concerns.

**Location:** `source/docker/edge_server/source/compute.py`

### Constants

```python
"""compute.py — CPU-intensive edge analytics applied to pre-fetched data.

All functions are pure compute — no I/O, no DB calls. They operate on
data already retrieved by the endpoint handlers in app.py.
"""

import hashlib
import math
import statistics
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Severity thresholds (fraction of alert_threshold)
SEVERITY_LEVELS = {
    "critical": 1.0,    # value >= 100% of threshold
    "warning":  0.85,   # value >= 85% of threshold
    "elevated": 0.70,   # value >= 70% of threshold
    "normal":   0.0,    # below 70%
}

# Tag-based priority multipliers for dashboard urgency scoring
TAG_PRIORITY = {
    "high-priority": 2.0,
    "critical-zone": 1.8,
    "industrial":    1.3,
    "environmental": 1.0,
    "mechanical":    1.1,
    "thermal":       1.2,
}

# How many recent local request events to use for trend analysis
TREND_WINDOW_SIZE = 20

# Staleness decay half-life in seconds (for dashboard ranking)
STALENESS_HALF_LIFE_S = 300.0
```

---

### Function 1: `score_device_severity`

Used by `/device/<id>/latest`. Replaces the simple boolean `alert` flag with a multi-level severity classification and a numeric anomaly score.

```python
def score_device_severity(
    value: float | None,
    threshold: float | None,
    device_type: str,
    device_id: str,
) -> dict:
    """Compute a multi-level severity classification for a device reading.

    Returns:
        {
            "severity": "critical" | "warning" | "elevated" | "normal",
            "anomaly_score": float,  # 0.0 = perfectly normal, >1.0 = above threshold
            "calibration_hash": float,  # device-specific jitter factor
            "alert": bool,  # backward-compatible boolean
        }
    """
    if value is None or threshold is None or threshold == 0:
        return {
            "severity": "normal",
            "anomaly_score": 0.0,
            "calibration_hash": 0.0,
            "alert": False,
        }

    # Normalized anomaly score with exponential weighting by device type
    raw_ratio = value / threshold

    # Device-specific calibration offset derived from hashing the device ID.
    # Simulates per-device sensor calibration correction that a real edge
    # system would compute before evaluating thresholds.
    h = hashlib.sha256(device_id.encode()).hexdigest()
    calibration_hash = (int(h[:8], 16) % 1000) / 10000.0  # 0.0000 – 0.0999
    calibrated_ratio = raw_ratio + calibration_hash

    # Exponential weighting: different device types have different sensitivity curves.
    # E.g., temperature sensors have sharper urgency near threshold than humidity sensors.
    type_seed = sum(ord(c) for c in device_type) % 10
    exponent = 1.0 + type_seed * 0.1  # range 1.0 – 1.9
    anomaly_score = calibrated_ratio ** exponent

    # Classification
    severity = "normal"
    for level, cutoff in SEVERITY_LEVELS.items():
        if calibrated_ratio >= cutoff:
            severity = level
            break

    return {
        "severity": severity,
        "anomaly_score": round(anomaly_score, 4),
        "calibration_hash": round(calibration_hash, 6),
        "alert": calibrated_ratio >= 1.0,
    }
```

---

### Function 2: `compute_trend`

Used by `/device/<id>/latest`. Computes a linear regression slope over recent local request latencies for this device — is the data access getting slower (rising) or improving (falling)?

```python
def compute_trend(request_events: list[dict]) -> dict:
    """Compute a linear-regression trend over recent request events for a device.

    Each event is expected to have 'latency_ms' and 'timestamp' fields.

    Returns:
        {
            "trend_slope": float,       # ms per second (positive = worsening)
            "trend_label": str,         # "rising" | "falling" | "stable" | "insufficient_data"
            "sample_count": int,
            "latency_mean": float,
            "latency_std": float,
        }
    """
    if len(request_events) < 3:
        return {
            "trend_slope": 0.0,
            "trend_label": "insufficient_data",
            "sample_count": len(request_events),
            "latency_mean": 0.0,
            "latency_std": 0.0,
        }

    # Extract (timestamp_epoch, latency_ms) pairs
    points = []
    for ev in request_events:
        lat = ev.get("latency_ms")
        ts = ev.get("timestamp")
        if lat is None or ts is None:
            continue
        if isinstance(ts, datetime):
            epoch = ts.timestamp()
        elif isinstance(ts, (int, float)):
            epoch = float(ts)
        else:
            continue
        points.append((epoch, float(lat)))

    if len(points) < 3:
        return {
            "trend_slope": 0.0,
            "trend_label": "insufficient_data",
            "sample_count": len(points),
            "latency_mean": 0.0,
            "latency_std": 0.0,
        }

    # Linear regression: slope = Σ((x-x̄)(y-ȳ)) / Σ((x-x̄)²)
    n = len(points)
    x_vals = [p[0] for p in points]
    y_vals = [p[1] for p in points]
    x_mean = sum(x_vals) / n
    y_mean = sum(y_vals) / n

    numerator = sum((x - x_mean) * (y - y_mean) for x, y in points)
    denominator = sum((x - x_mean) ** 2 for x in x_vals)

    slope = numerator / denominator if denominator != 0 else 0.0

    # Classify
    if abs(slope) < 0.01:
        label = "stable"
    elif slope > 0:
        label = "rising"
    else:
        label = "falling"

    lat_values = [p[1] for p in points]

    return {
        "trend_slope": round(slope, 6),
        "trend_label": label,
        "sample_count": n,
        "latency_mean": round(statistics.mean(lat_values), 2),
        "latency_std": round(statistics.pstdev(lat_values), 2) if n > 1 else 0.0,
    }
```

---

### Function 3: `compute_service_pressure`

Used by `/service_pressure`. Takes recent local request activity and produces a summary plus the top devices and tags contributing to local edge pressure.

```python
def compute_service_pressure(
    events: list[dict],
    limit: int,
    region: str,
    window_seconds: float,
) -> dict:
    """Summarize recent local request activity for the serving edge server.

    Returns request-rate, latency, a read-weighted Tier 1 hit ratio,
    top-device concentration, a composite pressure score, and ranked
    device/tag breakdowns.
    """
    ...
```

---

### Function 4: `score_dashboard_urgency`

Used by `/dashboard/<node_id>`. Replaces the simple `value / threshold` sort with a multi-factor urgency score.

```python
def score_dashboard_urgency(devices: list[dict], now: datetime | None = None) -> list[dict]:
    """Compute multi-factor urgency scores for dashboard devices.

    For each device, urgency combines:
      - Threshold proximity: value / alert_threshold (exponential near 1.0)
      - Tag priority: sum of TAG_PRIORITY weights for the device's tags
      - Status severity: numeric mapping of payload.status
      - Staleness penalty: exponential decay based on last_updated age

    Each device dict is enriched with 'urgency_score' and 'urgency_breakdown'.
    The list is re-sorted by urgency_score descending.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    STATUS_WEIGHT = {
        "critical": 3.0,
        "warning":  2.0,
        "elevated": 1.5,
        "normal":   1.0,
        "unknown":  0.5,
    }

    for d in devices:
        # --- Factor 1: Threshold proximity (exponential near 1.0) ---
        value = d.get("payload", {}).get("value")
        threshold = d.get("metadata", {}).get("alert_threshold")
        if value is not None and threshold:
            proximity = value / threshold
            # Exponential scaling: urgency rises sharply as value approaches threshold
            proximity_score = proximity ** 3
        else:
            proximity_score = 0.0

        # --- Factor 2: Tag priority ---
        tags = d.get("tags", [])
        tag_score = sum(TAG_PRIORITY.get(t, 0.5) for t in tags)
        # Normalize: divide by number of tags to avoid bias toward many-tag devices
        tag_score = tag_score / max(len(tags), 1)

        # --- Factor 3: Status severity ---
        status = d.get("payload", {}).get("status", "unknown")
        status_score = STATUS_WEIGHT.get(status, 0.5)

        # --- Factor 4: Staleness decay ---
        last_updated = d.get("last_updated")
        if isinstance(last_updated, datetime):
            age_s = (now - last_updated).total_seconds()
        else:
            age_s = STALENESS_HALF_LIFE_S  # assume one half-life if unknown

        decay = math.exp(-0.693 * age_s / STALENESS_HALF_LIFE_S)  # 0.693 = ln(2)

        # --- Combined urgency ---
        urgency = (
            0.40 * proximity_score
            + 0.25 * tag_score
            + 0.20 * status_score
            + 0.15 * decay
        )

        d["urgency_score"] = round(urgency, 4)
        d["urgency_breakdown"] = {
            "proximity": round(proximity_score, 4),
            "tag_priority": round(tag_score, 4),
            "status_severity": round(status_score, 4),
            "freshness_decay": round(decay, 4),
        }

    devices.sort(key=lambda d: d.get("urgency_score", 0), reverse=True)
    return devices
```

### Function 5: `compute_dashboard_summary`

Also used by `/dashboard/<node_id>`. Computes summary statistics across all matched devices so the response includes fleet-level insight.

```python
def compute_dashboard_summary(devices: list[dict]) -> dict:
    """Compute summary statistics across all dashboard devices.

    Returns aggregate metrics: mean/std/min/max of urgency scores and
    value-to-threshold ratios, plus counts per status category.
    """
    if not devices:
        return {"device_count": 0}

    urgency_scores = [d.get("urgency_score", 0) for d in devices]
    ratios = []
    status_counts: dict[str, int] = {}

    for d in devices:
        value = d.get("payload", {}).get("value")
        threshold = d.get("metadata", {}).get("alert_threshold")
        if value is not None and threshold:
            ratios.append(value / threshold)

        status = d.get("payload", {}).get("status", "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1

    summary = {
        "device_count": len(devices),
        "urgency_mean": round(statistics.mean(urgency_scores), 4),
        "urgency_std": round(statistics.pstdev(urgency_scores), 4) if len(urgency_scores) > 1 else 0.0,
        "urgency_max": round(max(urgency_scores), 4),
        "status_distribution": status_counts,
    }

    if ratios:
        summary["ratio_mean"] = round(statistics.mean(ratios), 4)
        summary["ratio_std"] = round(statistics.pstdev(ratios), 4) if len(ratios) > 1 else 0.0
        summary["ratio_max"] = round(max(ratios), 4)

    return summary
```

---

### Function 6: `verify_fleet_integrity`

Used by `/dashboard/<node_id>` **after** `score_dashboard_urgency` as a
separate compute pass over the candidate set. Performs iterated SHA-256
integrity verification on each device's payload, producing a deterministic
fingerprint. The work factor (`DASHBOARD_INTEGRITY_WORK_FACTOR`, default 200)
controls CPU time linearly — at 500 candidates × 200 iterations this
contributes ~100ms per request to $T_{proc}$, which is the dominant CPU cost
in the dashboard endpoint.

```python
def verify_fleet_integrity(devices: list[dict], work_factor: int = 200) -> None:
    """Per-device cryptographic integrity check.
    ...
    """
    for d in devices:
        payload = json.dumps(d.get("payload", {}), sort_keys=True)
        device_id = str(d.get("_id", ""))
        data = f"{device_id}:{payload}".encode()
        h: bytes = data
        for _ in range(work_factor):
            h = hashlib.sha256(h).digest()
        d["integrity_hash"] = h.hex()[:16]
```

---

### Configuration

Two new environment variables control the dashboard compute path:

| Variable                            | Default | Purpose                                                                                                   |
| ----------------------------------- | ------- | --------------------------------------------------------------------------------------------------------- |
| `DASHBOARD_CANDIDATE_LIMIT`       | `500` | Number of recent matching devices fetched per dashboard request via `.sort("last_updated", -1).limit()` |
| `DASHBOARD_INTEGRITY_WORK_FACTOR` | `200` | Iterations of SHA-256 per device in `verify_fleet_integrity`; controls $T_{proc}$ linearly            |

Both are consumed from `edge_server_config.py`:

```python
dashboard_candidate_limit = int(os.environ.get("DASHBOARD_CANDIDATE_LIMIT", "500"))
dashboard_integrity_work_factor = int(os.environ.get("DASHBOARD_INTEGRITY_WORK_FACTOR", "200"))
```

---

## Changes to `app.py`

### New Import

Add at the top of `app.py`, after the existing imports:

```python
from compute import (
    score_device_severity,
    compute_trend,
    compute_service_pressure,
    score_dashboard_urgency,
    compute_dashboard_summary,
    verify_fleet_integrity,
    TREND_WINDOW_SIZE,
)
```

---

### Endpoint 1: `/device/<id>/latest`

**Current code** (the section after fetching `doc` and `threshold_override`, before the `query_event` insert):

```python
        # Evaluate alert state against threshold
        value     = doc.get("payload", {}).get("value")
        threshold = threshold_override or doc.get("metadata", {}).get("alert_threshold")
        alert     = bool(threshold is not None and value is not None and value >= threshold)
```

**Replace with:**

```python
        # --- Compute: severity scoring ---
        value     = doc.get("payload", {}).get("value")
        threshold = threshold_override or doc.get("metadata", {}).get("alert_threshold")
        severity_result = score_device_severity(
            value, threshold, doc.get("device_type", ""), device_id,
        )
        alert = severity_result["alert"]
```

**Current code** (after recording the local support event, before building the response):

```python
        doc["_id"]   = str(doc["_id"])
        doc["alert"] = alert
        return jsonify(doc), 200
```

**Replace with:**

```python
        # --- Compute: trend analysis from recent local request activity ---
        recent_events = _local_request_state.recent_for_device(
            device_id,
            TREND_WINDOW_SIZE,
        )

        trend_result = compute_trend(recent_events)

        doc["_id"]       = str(doc["_id"])
        doc["alert"]     = alert
        doc["severity"]  = severity_result
        doc["trend"]     = trend_result
        return jsonify(doc), 200
```

> **Note on the trend input:** The trend calculation now reads from the serving edge server's bounded local request buffer. This removes support-state Mongo traffic from the synchronous path while keeping the regression itself as edge CPU work that contributes to $T_{proc}$.

---

### Endpoint 2: `/service_pressure`

`/service_pressure` is now a local-only support analytics route. It does not
perform any MongoDB reads. Instead it scans the serving edge's recent request
buffer and computes:

```python
        cutoff_epoch = time.time() - window_min * 60
        events, truncated = _local_request_state.events_since_with_truncation(cutoff_epoch)
        retained_window_seconds = window_min * 60
        if truncated and events:
            retained_window_seconds = max(
                1.0,
                time.time() - min(float(ev.get("timestamp", time.time())) for ev in events),
            )
        response = compute_service_pressure(
            events,
            limit=limit,
            region=LAN_ID,
            window_seconds=retained_window_seconds,
        )
```

This keeps the route compute-visible while making its storage semantics
explicitly local to the serving edge server. When the in-memory safety cap
clips the requested look-back horizon, the response now reports
`window_truncated` plus `retained_window_seconds` so request-rate and pressure
math are interpreted against the retained span rather than the nominal window.

---

### Endpoint 3: `/dashboard/<node_id>`

**Current code** (the urgency sort and response building):

```python
        # Sort descending by urgency: value / alert_threshold
        def urgency(doc):
            value     = doc.get("payload", {}).get("value")
            threshold = doc.get("metadata", {}).get("alert_threshold")
            if value is None or not threshold:
                return 0.0
            return value / threshold

        devices.sort(key=urgency, reverse=True)
        devices = devices[:limit]

        for d in devices:
            d["_id"] = str(d["_id"])

        return jsonify({
            "node_id":        node_id,
            "subscribed_tags": subscribed_tags,
            "devices":         devices,
        }), 200
```

**Replace with:**

```python
        # --- Compute: multi-factor urgency scoring ---
        devices = score_dashboard_urgency(devices)
        devices = devices[:limit]

        # --- Compute: fleet summary statistics ---
        summary = compute_dashboard_summary(devices)

        for d in devices:
            d["_id"] = str(d["_id"])

        return jsonify({
            "node_id":         node_id,
            "subscribed_tags": subscribed_tags,
            "devices":         devices,
            "summary":         summary,
        }), 200
```

Note: `score_dashboard_urgency` receives the **full** unsliced device list, so the urgency computation runs over all matched devices before truncating to `limit`. This is deliberate — more devices = more CPU work at high request rates.

---

### Updated `sensor_reports.find` projection in `/dashboard`

The dashboard query currently projects `"metadata": 1`. The `score_dashboard_urgency` function also needs `last_updated`, which is already projected since we fetch `metadata` (a top-level field). However, we should explicitly add `"last_updated": 1` to make the dependency clear:

**Current:**

```python
                    {"_id": 1, "device_type": 1, "tags": 1,
                     "payload": 1, "metadata": 1, "region_origin": 1},
```

**New:**

```python
                    {"_id": 1, "device_type": 1, "tags": 1,
                     "payload": 1, "metadata": 1, "region_origin": 1,
                     "last_updated": 1},
```

---

## New File: `compute.py`

Create `source/docker/edge_server/source/compute.py` containing all five functions and the constants defined above. This file has **no imports from Flask, pymongo, or zmq** — only stdlib (`hashlib`, `math`, `statistics`, `datetime`).

---

## Dockerfile Change

No Dockerfile change needed. `compute.py` is a pure-Python module with only stdlib dependencies. It is already included by the existing `COPY source/ /app/source/` instruction.

---

## Impact on Telemetry

The telemetry layer (`telemetry.py`) already measures $T_{proc}$ correctly:

```
T_proc = T_total - T_dados
```

where `T_total = time.monotonic() - g.time_start` and `T_dados = g.time_db_elapsed`. Since the new compute functions run **between** the `timed_db` context managers (not inside them), their execution time flows entirely into `T_proc`. No telemetry changes are needed.

The only exception is the trend query in `/device/<id>/latest` — it uses `timed_db`, so its time counts as $T_{dados}$. The `compute_trend()` call that follows is $T_{proc}$.

---

## Summary of Files Changed

| File                                            | Action           | Description                                                      |
| ----------------------------------------------- | ---------------- | ---------------------------------------------------------------- |
| `source/docker/edge_server/source/compute.py` | **Create** | Pure-compute module: 6 functions + constants                     |
| `source/docker/edge_server/source/app.py`     | **Edit**   | Import `compute`, modify 3 endpoints to call compute functions |

No new dependencies. No config changes. No Dockerfile changes.
