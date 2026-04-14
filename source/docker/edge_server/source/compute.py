"""compute.py — CPU-intensive edge analytics applied to pre-fetched data.

These functions implement generic edge analytics patterns — per-request data
enrichment, temporal trend detection, and multi-factor composite ranking —
instantiated with IoT monitoring semantics for the experimental workload.

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

# How many recent query_events to use for trend analysis
TREND_WINDOW_SIZE = 20

# Staleness decay half-life in seconds (for dashboard ranking)
STALENESS_HALF_LIFE_S = 300.0


# ---------------------------------------------------------------------------
# Function 1: Per-device severity scoring
# ---------------------------------------------------------------------------

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

    # Exponential weighting: different device types have different sensitivity
    # curves (e.g. temperature sensors have sharper urgency near threshold).
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


# ---------------------------------------------------------------------------
# Function 2: Temporal trend analysis
# ---------------------------------------------------------------------------

def compute_trend(query_events: list[dict]) -> dict:
    """Compute a linear-regression trend over recent query_events for a device.

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
    if len(query_events) < 3:
        return {
            "trend_slope": 0.0,
            "trend_label": "insufficient_data",
            "sample_count": len(query_events),
            "latency_mean": 0.0,
            "latency_std": 0.0,
        }

    # Extract (timestamp_epoch, latency_ms) pairs
    points = []
    for ev in query_events:
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

    # Linear regression: slope = sum((x-x_mean)(y-y_mean)) / sum((x-x_mean)^2)
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


# ---------------------------------------------------------------------------
# Function 3: Composite anomaly risk scoring
# ---------------------------------------------------------------------------

def score_anomaly_results(hot_devices: list[dict]) -> list[dict]:
    """Compute composite risk scores for anomaly detection results.

    For each device, the risk score combines:
      - Z-score of query_count (popularity pressure)
      - Z-score of avg_latency_ms (access cost)
      - Threshold proximity (value / alert_threshold from sensor data)

    The list is re-sorted by composite_risk descending.
    """
    if len(hot_devices) < 2:
        for d in hot_devices:
            d["composite_risk"] = 1.0
            d["z_query_count"] = 0.0
            d["z_latency"] = 0.0
        return hot_devices

    # Extract vectors
    counts = [d.get("query_count", 0) for d in hot_devices]
    latencies = [d.get("avg_latency_ms", 0) for d in hot_devices]

    # Z-score normalization
    count_mean = statistics.mean(counts)
    count_std = statistics.pstdev(counts)
    lat_mean = statistics.mean(latencies)
    lat_std = statistics.pstdev(latencies)

    for d in hot_devices:
        z_count = (d.get("query_count", 0) - count_mean) / count_std if count_std > 0 else 0.0
        z_lat = (d.get("avg_latency_ms", 0) - lat_mean) / lat_std if lat_std > 0 else 0.0

        # Threshold proximity from sensor data (0.0 if not available)
        value = d.get("value")
        threshold = d.get("threshold")
        proximity = (value / threshold) if (value and threshold) else 0.0

        # Composite risk: weighted sum of z-scores + proximity
        composite = 0.35 * z_count + 0.30 * z_lat + 0.35 * proximity

        d["z_query_count"] = round(z_count, 4)
        d["z_latency"] = round(z_lat, 4)
        d["composite_risk"] = round(composite, 4)

    # Re-sort by composite risk descending
    hot_devices.sort(key=lambda d: d["composite_risk"], reverse=True)
    return hot_devices


# ---------------------------------------------------------------------------
# Function 4: Multi-factor dashboard urgency scoring
# ---------------------------------------------------------------------------

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
            if last_updated.tzinfo is None:
                last_updated = last_updated.replace(tzinfo=timezone.utc)
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


# ---------------------------------------------------------------------------
# Function 5: Dashboard fleet summary statistics
# ---------------------------------------------------------------------------

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
