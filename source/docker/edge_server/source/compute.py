"""compute.py — CPU-intensive edge analytics applied to pre-fetched data.

These functions implement generic edge analytics patterns — per-request data
enrichment, temporal trend detection, local service-pressure summarization,
and multi-factor composite ranking — instantiated with IoT monitoring
semantics for the experimental workload.

All functions are pure compute — no I/O, no DB calls. They operate on
data already retrieved by the monitoring workload route module.
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
# Function 3: Local service-pressure summary
# ---------------------------------------------------------------------------

def compute_service_pressure(
    events: list[dict],
    limit: int,
    region: str,
    window_seconds: float,
) -> dict:
    """Summarize recent local request activity for the serving edge server.

    Returns a summary plus the top devices and tags contributing to recent
    service pressure on this edge.
    """
    request_count = len(events)
    if request_count == 0:
        return {
            "region_served": region,
            "summary": {
                "request_count": 0,
                "unique_device_count": 0,
                "request_rate_rps": 0.0,
                "latency_mean_ms": 0.0,
                "latency_p95_ms": 0.0,
                "tier1_hit_ratio": 0.0,
                "tier1_eligible_read_count": 0,
                "tier1_observed_request_count": 0,
                "top_device_share": 0.0,
                "pressure_score": 0.0,
                "pressure_label": "low",
            },
            "request_kind_counts": {},
            "top_devices": [],
            "top_tags": [],
        }

    window_seconds = max(window_seconds, 1.0)
    latencies = [float(ev.get("latency_ms", 0.0)) for ev in events]
    tier1_hit_total = 0.0
    tier1_eligible_read_count = 0
    tier1_observed_request_count = 0

    devices: dict[str, dict] = {}
    tags: dict[str, dict] = {}
    request_kind_counts: dict[str, int] = {}

    for ev in events:
        request_kind = str(ev.get("request_kind", "unknown"))
        request_kind_counts[request_kind] = request_kind_counts.get(request_kind, 0) + 1

        eligible_reads = int(ev.get("tier1_eligible_reads", 0) or 0)
        if eligible_reads > 0:
            tier1_observed_request_count += 1
            tier1_eligible_read_count += eligible_reads
            tier1_hit_total += eligible_reads * float(
                ev.get(
                    "tier1_hit_ratio",
                    1.0 if str(ev.get("served_from_tier", "0")) == "1" else 0.0,
                )
            )

        device_id = ev.get("device_id")
        latency = float(ev.get("latency_ms", 0.0))
        timestamp = float(ev.get("timestamp", 0.0))
        severity = ev.get("severity", "normal")
        status = ev.get("status", "unknown")
        event_tags = tuple(ev.get("tags") or ())

        for tag in event_tags:
            tag_stats = tags.setdefault(
                tag,
                {
                    "tag": tag,
                    "request_count": 0,
                    "device_ids": set(),
                    "latencies": [],
                },
            )
            tag_stats["request_count"] += 1
            if device_id:
                tag_stats["device_ids"].add(device_id)
            tag_stats["latencies"].append(latency)

        if not device_id:
            continue

        device_stats = devices.setdefault(
            device_id,
            {
                "device_id": device_id,
                "request_count": 0,
                "latencies": [],
                "last_seen_epoch": 0.0,
                "last_severity": "normal",
                "last_status": "unknown",
                "tags": (),
            },
        )
        device_stats["request_count"] += 1
        device_stats["latencies"].append(latency)
        if timestamp >= device_stats["last_seen_epoch"]:
            device_stats["last_seen_epoch"] = timestamp
            device_stats["last_severity"] = severity
            device_stats["last_status"] = status
            device_stats["tags"] = event_tags

    top_devices = []
    for device_stats in devices.values():
        device_latencies = device_stats.pop("latencies")
        top_devices.append(
            {
                "device_id": device_stats["device_id"],
                "request_count": device_stats["request_count"],
                "avg_latency_ms": round(statistics.mean(device_latencies), 2),
                "last_seen_epoch": round(device_stats["last_seen_epoch"], 3),
                "last_severity": device_stats["last_severity"],
                "last_status": device_stats["last_status"],
                "tags": list(device_stats["tags"]),
            }
        )
    top_devices.sort(key=lambda d: (d["request_count"], d["avg_latency_ms"]), reverse=True)
    top_devices = top_devices[:limit]

    top_tags = []
    for tag_stats in tags.values():
        tag_latencies = tag_stats["latencies"]
        top_tags.append(
            {
                "tag": tag_stats["tag"],
                "request_count": tag_stats["request_count"],
                "unique_device_count": len(tag_stats["device_ids"]),
                "avg_latency_ms": round(statistics.mean(tag_latencies), 2),
            }
        )
    top_tags.sort(key=lambda d: (d["request_count"], d["avg_latency_ms"]), reverse=True)
    top_tags = top_tags[:limit]

    request_rate_rps = request_count / window_seconds
    latency_mean_ms = statistics.mean(latencies)
    latency_p95_ms = _percentile(latencies, 0.95)
    tier1_hit_ratio = (
        tier1_hit_total / tier1_eligible_read_count
        if tier1_eligible_read_count > 0
        else 0.0
    )
    top_device_share = (top_devices[0]["request_count"] / request_count) if top_devices else 0.0

    rate_component = _normalize(request_rate_rps, 10.0)
    latency_component = _normalize(latency_p95_ms, 150.0)
    concentration_component = _normalize(top_device_share, 0.5)
    tier1_miss_component = 1.0 - tier1_hit_ratio if tier1_eligible_read_count > 0 else 0.0

    pressure_score = (
        0.35 * rate_component
        + 0.30 * latency_component
        + 0.20 * concentration_component
        + 0.15 * tier1_miss_component
    )
    if pressure_score < 0.35:
        pressure_label = "low"
    elif pressure_score < 0.65:
        pressure_label = "moderate"
    else:
        pressure_label = "high"

    return {
        "region_served": region,
        "summary": {
            "request_count": request_count,
            "unique_device_count": len(devices),
            "request_rate_rps": round(request_rate_rps, 2),
            "latency_mean_ms": round(latency_mean_ms, 2),
            "latency_p95_ms": round(latency_p95_ms, 2),
            "tier1_hit_ratio": round(tier1_hit_ratio, 4),
            "tier1_eligible_read_count": tier1_eligible_read_count,
            "tier1_observed_request_count": tier1_observed_request_count,
            "top_device_share": round(top_device_share, 4),
            "pressure_score": round(pressure_score, 4),
            "pressure_label": pressure_label,
        },
        "request_kind_counts": dict(
            sorted(request_kind_counts.items(), key=lambda item: item[1], reverse=True)
        ),
        "top_devices": top_devices,
        "top_tags": top_tags,
    }


def _normalize(value: float, ceiling: float) -> float:
    if ceiling <= 0:
        return 0.0
    return max(0.0, min(value / ceiling, 1.0))


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]

    rank = (len(ordered) - 1) * percentile
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[lower]

    weight = rank - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


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
