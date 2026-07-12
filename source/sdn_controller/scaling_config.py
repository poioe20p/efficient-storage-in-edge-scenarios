"""scaling_config.py — environment-based scaling constants.

Shared by ScalingPolicy, DynamicNodeRegistry, and the mediator.
"""

import os

# ── Scale-up: weighted degradation score ────────────────────────────────
#
#  score = W_CPU * max(0, cpu - FLOOR) / SPAN  +  W_T * max(0, lat - FLOOR) / SPAN
#
# W_T is _W_T_PROC (compute) or _W_T_DB (storage) depending on the tier.
#
# Score ≥ THRESHOLD for at least REQUIRED of the last WINDOW_SIZE windows
# triggers scale-up.

# Storage score weights & normalisation (CPU-dominant — scaling fixes CPU, not T_db)
# Floors/spans are calibrated for container-level CPU readings (typical edge
# container range 0–6 %) and observed t_db distributions.
_W_STORAGE_CPU     = float(os.environ.get("SCALEUP_W_STORAGE_CPU",     "0.7"))
_W_T_DB            = float(os.environ.get("SCALEUP_W_T_DB",            "0.3"))
_STORAGE_CPU_FLOOR = float(os.environ.get("SCALEUP_STORAGE_CPU_FLOOR", "5"))
_STORAGE_CPU_SPAN  = float(os.environ.get("SCALEUP_STORAGE_CPU_SPAN",  "10"))
_T_DB_FLOOR        = float(os.environ.get("SCALEUP_T_DB_FLOOR",        "150"))
_T_DB_SPAN         = float(os.environ.get("SCALEUP_T_DB_SPAN",         "600"))

# Compute score weights & normalisation
_W_CPU        = float(os.environ.get("SCALEUP_W_CPU",      "0.40"))
_W_T_PROC     = float(os.environ.get("SCALEUP_W_T_PROC",   "0.60"))
_CPU_FLOOR    = float(os.environ.get("SCALEUP_CPU_FLOOR",  "5"))
_CPU_SPAN     = float(os.environ.get("SCALEUP_CPU_SPAN",   "10"))
_T_PROC_FLOOR = float(os.environ.get("SCALEUP_T_PROC_FLOOR", "20"))
_T_PROC_SPAN  = float(os.environ.get("SCALEUP_T_PROC_SPAN",  "80"))

# Compute scale-up sliding window
_SCALE_UP_WINDOW_SIZE = int(os.environ.get("SCALEUP_WINDOW_SIZE", "5"))
_SCALE_UP_REQUIRED    = int(os.environ.get("SCALEUP_REQUIRED",    "3"))

_SCALEUP_COMPUTE_BASE_THRESHOLD = float(
	os.environ.get("SCALEUP_COMPUTE_BASE_THRESHOLD", "0.45")
)
_SCALEUP_COMPUTE_THRESHOLD_INCREMENT = float(
	os.environ.get("SCALEUP_COMPUTE_THRESHOLD_INCREMENT", "0.10")
)
_SCALEUP_COMPUTE_MAX_THRESHOLD = float(
	os.environ.get("SCALEUP_COMPUTE_MAX_THRESHOLD", "0.85")
)
_SCALEUP_COMPUTE_COOLDOWN_S = float(
	os.environ.get("SCALEUP_COMPUTE_COOLDOWN_S", "45")
)
_SCALEUP_COMPUTE_PEER_RELIEF = float(
	os.environ.get("SCALEUP_COMPUTE_PEER_RELIEF", "0.03")
)
_SCALEUP_COMPUTE_PEER_HEALTH_THRESHOLD = float(
	os.environ.get("SCALEUP_COMPUTE_PEER_HEALTH_THRESHOLD", "0.35")
)

# Adaptive storage scale-up threshold (diminishing increment per dynamic node)
_SCALEUP_STORAGE_BASE_THRESHOLD      = float(os.environ.get("SCALEUP_STORAGE_BASE_THRESHOLD",      "0.25"))
_SCALEUP_STORAGE_THRESHOLD_INCREMENT = float(os.environ.get("SCALEUP_STORAGE_THRESHOLD_INCREMENT",  "0.10"))
_SCALEUP_STORAGE_MIN_INCREMENT       = float(os.environ.get("SCALEUP_STORAGE_MIN_INCREMENT",        "0.05"))
_SCALEUP_STORAGE_MAX_THRESHOLD       = float(os.environ.get("SCALEUP_STORAGE_MAX_THRESHOLD",        "0.55"))
_SCALEUP_STORAGE_WINDOW_SIZE         = int(os.environ.get("SCALEUP_STORAGE_WINDOW_SIZE",             "5"))
_SCALEUP_STORAGE_REQUIRED            = int(os.environ.get("SCALEUP_STORAGE_REQUIRED",                "2"))

# Hard caps — maximum dynamic containers per tier per LAN
_MAX_DYNAMIC_STORAGE = int(os.environ.get("MAX_DYNAMIC_STORAGE", "5"))
_MAX_DYNAMIC_COMPUTE = int(os.environ.get("MAX_DYNAMIC_COMPUTE", "4"))

# Scale-down thresholds — mirrored against the scale-up *_FLOOR values so
# scale-up and scale-down cannot disagree about a window's health (a window
# below the floor is healthy by construction). Calibrated for container-level
# CPU readings.
_TAU_CPU_DOWN              = float(os.environ.get("TAU_CPU_DOWN",              "15"))
_TAU_PROC_DOWN_MS          = float(os.environ.get("TAU_PROC_DOWN_MS",          "20"))
_TAU_STORAGE_CPU_DOWN      = float(os.environ.get("TAU_STORAGE_CPU_DOWN",      "15"))
_TAU_DB_DOWN_MS            = float(os.environ.get("TAU_DB_DOWN_MS",            "150"))
_TELEMETRY_TIMEOUT_WINDOWS = int(os.environ.get("TELEMETRY_TIMEOUT_WINDOWS",   "18"))

# Timeout ceiling — indeterminate windows (neither increment nor reset)
_SCALE_DOWN_PROC_TIMEOUT_CEILING_MS = float(os.environ.get("SCALE_DOWN_PROC_TIMEOUT_CEILING_MS", "5000"))
_SCALE_DOWN_DB_TIMEOUT_CEILING_MS   = float(os.environ.get("SCALE_DOWN_DB_TIMEOUT_CEILING_MS",   "5000"))

# Scale-down sliding window
_SCALE_DOWN_COMPUTE_WINDOW_SIZE = int(os.environ.get("SCALE_DOWN_COMPUTE_WINDOW_SIZE", "12"))
_SCALE_DOWN_COMPUTE_REQUIRED    = int(os.environ.get("SCALE_DOWN_COMPUTE_REQUIRED",     "7"))
_SCALE_DOWN_STORAGE_WINDOW_SIZE = int(os.environ.get("SCALE_DOWN_STORAGE_WINDOW_SIZE", "12"))
_SCALE_DOWN_STORAGE_REQUIRED    = int(os.environ.get("SCALE_DOWN_STORAGE_REQUIRED",     "7"))
_SCALE_DOWN_CANDIDATE_MAX_STALENESS_S = float(
	os.environ.get("SCALE_DOWN_CANDIDATE_MAX_STALENESS_S", "90")
)

# Cooldowns — suppress evaluation for a grace period after scale-up
_SCALEDOWN_STORAGE_COOLDOWN_S = float(os.environ.get("SCALEDOWN_STORAGE_COOLDOWN_S", "120"))
_SCALEDOWN_COMPUTE_COOLDOWN_S = float(os.environ.get("SCALEDOWN_COMPUTE_COOLDOWN_S",  "40"))
_SCALEUP_STORAGE_COOLDOWN_S   = float(os.environ.get("SCALEUP_STORAGE_COOLDOWN_S",   "120"))

# Birth grace — skip absent-node detection for newly spawned nodes
_NODE_BIRTH_GRACE_S = float(os.environ.get("NODE_BIRTH_GRACE_S", "60"))

# ── Storage persistent reserve ─────────────────────────────────────────
# 1 = maintain one ready same-LAN storage reserve per LAN; 0 = off.
_STORAGE_PERSISTENT_RESERVE_ENABLED = int(
    os.environ.get("STORAGE_PERSISTENT_RESERVE_ENABLED", "0")
)
# Telemetry-window budget for pending reserve activation.
# A trigger that latches while the reserve is PREPARING carries forward
# across reserve replacement but expires after this many telemetry windows.
_STORAGE_RESERVE_PENDING_WINDOWS = int(
    os.environ.get("STORAGE_RESERVE_PENDING_WINDOWS", "6")
)

# ── VIP warm-start knobs ───────────────────────────────────────────────
_VIP_WARM_STORAGE_SECONDS = float(
	os.environ.get("VIP_WARM_STORAGE_SECONDS", "30")
)
_VIP_WARM_SERVER_SECONDS = float(
	os.environ.get("VIP_WARM_SERVER_SECONDS", "45")
)

# ── Tier 1 selective-sync knobs (see tier1_selective_sync/) ─────────────
# Enables the Tier 1 subsystem end-to-end. 0 = no-op baseline for reproducibility.
_SS_ENABLED = int(os.environ.get("SS_ENABLED", "0"))
# Final cap on (owner_lan, collection) hot-doc list after merging per-edge
# access slices across every edge server in the consumer LAN.
_SS_HOT_DOC_LIMIT = int(os.environ.get("SS_HOT_DOC_LIMIT", "50"))
# Guard: don't promote (owner_lan, coll) if the read volume this window is
# below the floor — prevents promotion on trivial query bursts. Tuned to the
# observed per-window read counts under the standard `phases.json` workload
# (cross_region_hotspot phase typically lands in the 15–40 range).
_SS_MIN_READS_PER_WINDOW = int(os.environ.get("SS_MIN_READS_PER_WINDOW", "14"))
# Guard: don't promote (owner_lan, coll) if writes > this fraction of ops.
# Tier 1 replicates reads only; write-heavy collections pay full cost for
# little benefit.
_SS_WRITE_RATIO_MAX = float(os.environ.get("SS_WRITE_RATIO_MAX", "0.30"))

# ── Tier 1 scale-down knobs (consumed by the Tier 1 scale-down evaluator,
# co-located with the full-replica scale-down path; see
# docs/operation/elasticy_manager/implementation/tier1_selective_sync/README.md §3) ──
#
# Change Stream replication-lag ceiling. ``lag_s`` is emitted per-collection
# by the selective-sync supervisor as ``now - change.clusterTime`` at the
# moment the ForwarderWorker applies the event locally. Exceeding this on
# *any* collection tears the whole container down (shared mongod + shared
# remote connection mean one bad lag signal implicates all collections).
_SS_STALENESS_LIMIT_S = float(os.environ.get("SS_STALENESS_LIMIT_S", "10"))
# Minimum cross-region hits per window to keep a collection in the container.
# Falling below this for ``_SS_SCALEDOWN_WINDOW`` windows triggers reconfigure.
_SS_SCALEDOWN_THRESHOLD = int(os.environ.get("SS_SCALEDOWN_THRESHOLD", "5"))
_SS_SCALEDOWN_WINDOW    = int(os.environ.get("SS_SCALEDOWN_WINDOW",    "8"))

# ── PromotionCoordinator-only knobs ────────────────────────────────────
# Fraction of reads on (owner_lan, coll) that must be served cross-region
# before the collection is eligible for Tier 1 promotion.
_SS_PROMOTION_CROSS_REGION_THRESHOLD = float(
    os.environ.get("SS_PROMOTION_CROSS_REGION_THRESHOLD", "0.4"))
# Post-teardown dwell time before the same (owner_lan) direction can be
# promoted again. Prevents thrash when the cross-region predicate is still
# true on the next window immediately after a drain.
_SS_COOLDOWN_S = float(os.environ.get("SS_COOLDOWN_S", "90"))
# Sliding-window debounce on the QoE breach signal — require at least M
# windows with ``t_db_p95_ms_per_lan[owner_lan] > TAU_DADOS_MS`` out of the
# most recent N before submitting the first SelectiveSyncAlert for an
# (owner_lan). Mirrors storage (2-of-5) / compute (3-of-5) scale-up.
_SS_BREACH_WINDOWS_N = int(os.environ.get("SS_BREACH_WINDOWS_N", "5"))
_SS_BREACH_WINDOWS_M = int(os.environ.get("SS_BREACH_WINDOWS_M", "2"))
# Optional TTL on cached docs; 0 disables. Belt-and-suspenders guard.
_SS_MAX_TTL_S = int(os.environ.get("SS_MAX_TTL_S", "0"))

# ── Cross-region Tier 2 storage (feature flags) ───────────────────────
_CROSS_REGION_STORAGE_ENABLED = int(os.environ.get(
    "CROSS_REGION_STORAGE_ENABLED", "0"))
_CROSS_REGION_STORAGE_WARM = int(os.environ.get(
    "CROSS_REGION_STORAGE_WARM", "0"))
_MAX_CROSS_REGION_STORAGE = int(os.environ.get(
    "MAX_CROSS_REGION_STORAGE", "1"))

# ── Cross-region Tier 2 detection/policy ──────────────────────────────
# Cooldown after cross-region admission/spawn before re-evaluating.
_CROSS_REGION_STORAGE_COOLDOWN_S = float(os.environ.get(
    "CROSS_REGION_STORAGE_COOLDOWN_S", "120"))
# M-of-N sliding window for cross-region DB pressure (mirrors Tier 1
# breach ring in selective_sync/promotion.py).
_CROSS_REGION_BREACH_WINDOWS_M = int(os.environ.get(
    "CROSS_REGION_BREACH_WINDOWS_M", "2"))
_CROSS_REGION_BREACH_WINDOWS_N = int(os.environ.get(
    "CROSS_REGION_BREACH_WINDOWS_N", "5"))
# p95 DB time (ms) threshold per remote LAN for cross-region pressure.
# Must be set above baseline WAN transit (normal cross-region reads at
# 260ms WAN ≈ 300–500ms p95), but below saturation (2–10s p95).
# Default 1000ms catches queuing before connection-pool failures start.
# Mirrors the same signal Tier 1 uses (TAU_DADOS_MS in
# selective_sync/hotness.py), but at a cross-region-appropriate level.
_CROSS_REGION_DB_P95_THRESHOLD_MS = float(os.environ.get(
    "CROSS_REGION_DB_P95_THRESHOLD_MS", "1000"))

# Minimum cross-region read volume per telemetry window to sustain a
# cold-started cross-region replica.  When demand drops below this floor,
# the replica is eligible for scale-down.  Activation uses p95 > threshold;
# sustainment uses demand volume — two independent signals prevent the
# control-loop paradox where the replica's presence suppresses p95.
_CROSS_REGION_MIN_READS_TO_SUSTAIN = int(os.environ.get(
    "CROSS_REGION_MIN_READS_TO_SUSTAIN", "10"))

# Sliding-window debounce on the sustainment signal — require at least M
# windows with ``total_reads < _CROSS_REGION_MIN_READS_TO_SUSTAIN`` out of
# the most recent N before submitting a cross-region scale-down.  Short
# windows (default 2-of-3) prevent single-window dips from triggering
# unnecessary scale-down→re-spawn cycles while still responding quickly
# when demand truly subsides (cooldown reads stay at 0–15 for many windows).
_CROSS_REGION_SUSTAIN_WINDOWS_M = int(os.environ.get(
    "CROSS_REGION_SUSTAIN_WINDOWS_M", "2"))
_CROSS_REGION_SUSTAIN_WINDOWS_N = int(os.environ.get(
    "CROSS_REGION_SUSTAIN_WINDOWS_N", "3"))

# Minimum cross-region read volume per telemetry window required to
# activate a cross-region replica (warm standby admission or cold-start
# spawn).  Prevents spurious spawns during low-load phases (e.g.,
# baseline) where natural content distribution produces a handful of
# cross-region reads whose p95 may breach the threshold but whose volume
# is too low to justify a dedicated replica.  Calibrated from RQ3
# strategy-comparison v1: baseline shows ~12 xreg reads/window;
# pressure windows produce 100–300+ per collection.
_CROSS_REGION_MIN_READS_TO_ACTIVATE = int(os.environ.get(
    "CROSS_REGION_MIN_READS_TO_ACTIVATE", "50"))
