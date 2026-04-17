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

# Storage score weights & normalisation
_W_STORAGE_CPU     = float(os.environ.get("SCALEUP_W_STORAGE_CPU",     "0.3"))
_W_T_DB            = float(os.environ.get("SCALEUP_W_T_DB",            "0.7"))
_STORAGE_CPU_FLOOR = float(os.environ.get("SCALEUP_STORAGE_CPU_FLOOR", "50"))
_STORAGE_CPU_SPAN  = float(os.environ.get("SCALEUP_STORAGE_CPU_SPAN",  "35"))
_T_DB_FLOOR        = float(os.environ.get("SCALEUP_T_DB_FLOOR",        "15"))
_T_DB_SPAN         = float(os.environ.get("SCALEUP_T_DB_SPAN",         "75"))

# Compute score weights & normalisation
_W_CPU        = float(os.environ.get("SCALEUP_W_CPU",      "0.40"))
_W_T_PROC     = float(os.environ.get("SCALEUP_W_T_PROC",   "0.60"))
_CPU_FLOOR    = float(os.environ.get("SCALEUP_CPU_FLOOR",  "50"))
_CPU_SPAN     = float(os.environ.get("SCALEUP_CPU_SPAN",   "35"))
_T_PROC_FLOOR = float(os.environ.get("SCALEUP_T_PROC_FLOOR", "10"))
_T_PROC_SPAN  = float(os.environ.get("SCALEUP_T_PROC_SPAN",  "30"))

# Compute scale-up sliding window
_SCALE_UP_WINDOW_SIZE = int(os.environ.get("SCALEUP_WINDOW_SIZE", "5"))
_SCALE_UP_REQUIRED    = int(os.environ.get("SCALEUP_REQUIRED",    "3"))

_SCALEUP_COMPUTE_BASE_THRESHOLD = float(
	os.environ.get("SCALEUP_COMPUTE_BASE_THRESHOLD", "0.33")
)
_SCALEUP_COMPUTE_THRESHOLD_INCREMENT = float(
	os.environ.get("SCALEUP_COMPUTE_THRESHOLD_INCREMENT", "0.10")
)
_SCALEUP_COMPUTE_MAX_THRESHOLD = float(
	os.environ.get("SCALEUP_COMPUTE_MAX_THRESHOLD", "0.70")
)
_SCALEUP_COMPUTE_COOLDOWN_S = float(
	os.environ.get("SCALEUP_COMPUTE_COOLDOWN_S", "45")
)
_SCALEUP_COMPUTE_PEER_RELIEF = float(
	os.environ.get("SCALEUP_COMPUTE_PEER_RELIEF", "0.03")
)
_SCALEUP_COMPUTE_PEER_HEALTH_THRESHOLD = float(
	os.environ.get("SCALEUP_COMPUTE_PEER_HEALTH_THRESHOLD", "0.33")
)

# Adaptive storage scale-up threshold (lower base, increment per dynamic node)
_SCALEUP_STORAGE_BASE_THRESHOLD      = float(os.environ.get("SCALEUP_STORAGE_BASE_THRESHOLD",      "0.35"))
_SCALEUP_STORAGE_THRESHOLD_INCREMENT = float(os.environ.get("SCALEUP_STORAGE_THRESHOLD_INCREMENT",  "0.12"))
_SCALEUP_STORAGE_MAX_THRESHOLD       = float(os.environ.get("SCALEUP_STORAGE_MAX_THRESHOLD",        "0.65"))
_SCALEUP_STORAGE_WINDOW_SIZE         = int(os.environ.get("SCALEUP_STORAGE_WINDOW_SIZE",             "5"))
_SCALEUP_STORAGE_REQUIRED            = int(os.environ.get("SCALEUP_STORAGE_REQUIRED",                "2"))

# Scale-down thresholds
_TAU_CPU_DOWN              = float(os.environ.get("TAU_CPU_DOWN",              "65"))
_TAU_PROC_DOWN_MS          = float(os.environ.get("TAU_PROC_DOWN_MS",          "5"))
_TAU_STORAGE_CPU_DOWN      = float(os.environ.get("TAU_STORAGE_CPU_DOWN",      "60"))
_TAU_DB_DOWN_MS            = float(os.environ.get("TAU_DB_DOWN_MS",            "100"))
_TELEMETRY_TIMEOUT_WINDOWS = int(os.environ.get("TELEMETRY_TIMEOUT_WINDOWS",   "18"))

# Timeout ceiling — indeterminate windows (neither increment nor reset)
_SCALE_DOWN_PROC_TIMEOUT_CEILING_MS = float(os.environ.get("SCALE_DOWN_PROC_TIMEOUT_CEILING_MS", "5000"))
_SCALE_DOWN_DB_TIMEOUT_CEILING_MS   = float(os.environ.get("SCALE_DOWN_DB_TIMEOUT_CEILING_MS",   "5000"))

# Scale-down sliding window
_SCALE_DOWN_COMPUTE_WINDOW_SIZE = int(os.environ.get("SCALE_DOWN_COMPUTE_WINDOW_SIZE", "12"))
_SCALE_DOWN_COMPUTE_REQUIRED    = int(os.environ.get("SCALE_DOWN_COMPUTE_REQUIRED",     "7"))
_SCALE_DOWN_STORAGE_WINDOW_SIZE = int(os.environ.get("SCALE_DOWN_STORAGE_WINDOW_SIZE", "15"))
_SCALE_DOWN_STORAGE_REQUIRED    = int(os.environ.get("SCALE_DOWN_STORAGE_REQUIRED",     "9"))

# Cooldowns — suppress evaluation for a grace period after scale-up
_SCALEDOWN_STORAGE_COOLDOWN_S = float(os.environ.get("SCALEDOWN_STORAGE_COOLDOWN_S", "120"))
_SCALEDOWN_COMPUTE_COOLDOWN_S = float(os.environ.get("SCALEDOWN_COMPUTE_COOLDOWN_S",  "40"))
_SCALEUP_STORAGE_COOLDOWN_S   = float(os.environ.get("SCALEUP_STORAGE_COOLDOWN_S",   "120"))

# Birth grace — skip absent-node detection for newly spawned nodes
_NODE_BIRTH_GRACE_S = float(os.environ.get("NODE_BIRTH_GRACE_S", "60"))
