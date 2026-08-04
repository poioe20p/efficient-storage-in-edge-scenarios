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

# ── Latency signal statistic ──────────────────────────────────────────
# Which per-window latency statistic feeds the decision signals (scale-up
# score and scale-down below/ceiling checks). Latency is right-skewed with
# unbounded outliers, so "median" is robust while "mean" can be dominated by a
# single slow request in a low-volume window — see
# docs/operation/testing/experiment/v2/mean_vs_median_signal_finding.md.
#   "mean"   → avg_time_* (legacy; default — keeps RQ1 byte-identical).
#   "median" → median_time_* (control group / RQ2+, robust). Falls back to the
#              mean when the aggregator did not publish a median.
_LATENCY_SIGNAL_MODE = os.environ.get("LATENCY_SIGNAL_MODE", "mean").strip().lower()

# CPU-aware storage scale-down gate (control group / RQ2+ composite signal).
# When enabled, storage scale-down additionally requires the storage CPU to be
# idle (below _TAU_STORAGE_CPU_DOWN), protecting the plateau from teardown when
# the median latency alone is low (the median's plateau-vs-demand_drop range is
# only ~1.4 ms in the control workload — see
# docs/operation/testing/experiment/v2/mean_vs_median_signal_finding.md §6).
# Default OFF → pure latency scale-down, RQ1 byte-identical.
_STORAGE_SCALE_DOWN_CPU_AWARE = os.environ.get(
    "STORAGE_SCALE_DOWN_CPU_AWARE", "0"
).strip().lower() in ("1", "true", "yes")

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

# ── RQ1 Design B housekeeping clock ───────────────────────────────────
# Time-based housekeeping (absent-node detection, scale-down evaluation)
# runs on this fixed internal ticker instead of on telemetry arrival.
_CONTROL_TICK_S = float(os.environ.get("CONTROL_TICK_S", "10"))
# Time-based absence timeout — comfortably above the longest heartbeat so
# idle-but-alive nodes are not falsely flagged absent. Scales with the
# housekeeping clock (semantic change from per-window counts).
_TELEMETRY_TIMEOUT_S = max(
    _TELEMETRY_TIMEOUT_WINDOWS * _CONTROL_TICK_S,
    3.0 * float(os.environ.get("HEARTBEAT_INTERVAL_S", "60")),
)

# ── Churn guard (G2 calib4/calib6 finding) ─────────────────────────────
# During an overload episode the LAN must NOT shed capacity: absent-node
# cleanup and scale-down both remove LIVE nodes when telemetry presence is
# sparse (bursty completions under load), which reconfigures the replica set
# and stalls in-flight DB ops — the self-amplifying collapse seen at open-loop
# rate 3.0 / 70% DB mix (pool 12 did NOT fix it; the churn did the damage).
# Default ON (correct behavior for all RQs); set HOUSEKEEPING_OVERLOAD_GATE=0
# to reproduce the pre-fix behavior.
_HOUSEKEEPING_OVERLOAD_GATE = os.environ.get(
    "HOUSEKEEPING_OVERLOAD_GATE", "1"
).strip().lower() in ("1", "true", "yes")
# Hysteresis lookback: the producer overload label (D3) flickers on lull
# windows under sparse telemetry, so a current-window-only gate lets
# absent-cleanup/scale-down fire mid-episode. Suppress while ANY of the last N
# delivered windows was overloaded.
_HOUSEKEEPING_OVERLOAD_LOOKBACK = int(os.environ.get(
    "HOUSEKEEPING_OVERLOAD_LOOKBACK", "5"))

# ── RQ2 bottleneck policy gate ─────────────────────────────────────────
# SCALEUP_POLICY selects the scale-up selection policy:
#   "dual"                 → pre-RQ2 behavior (both tiers may fire + submit
#                            independently, no budget, RQ1 decision log) —
#                            DEFAULT. Keeps canonical / RQ1 runs byte-identical.
#   "fixed_compute_first"  → RQ2 arm: always compute, never storage.
#   "fixed_storage_first"  → RQ2 arm: always storage, never compute.
#   "bottleneck_aware"     → RQ2 arm: classify the bottleneck from tier-specific
#                            telemetry and select the matching tier.
# Unknown value → log error + fall back to "dual" (deliberate, documented).
_SCALEUP_POLICY = os.environ.get("SCALEUP_POLICY", "dual")

# RQ2 action budget: hard ceiling on scale-up (spawn) submissions per tier per
# controller (per LAN). 0 disables enforcement (dual). Scale-down does not
# consume budget. See docs/research_questions/v2/rq2/rq2_preparation.md.
_ACTION_BUDGET_PER_TIER = int(os.environ.get("ACTION_BUDGET_PER_TIER", "4"))

# RQ2 bottleneck classifier margin (D3): |compute_score_norm - storage_score_norm|
# <= margin → classify as storage (documented tie-break; storage is the
# higher-urgency tier). Pre-registered per run, identical across arms.
_BOTTLENECK_CLASSIFY_MARGIN = float(
    os.environ.get("BOTTLENECK_CLASSIFY_MARGIN", "0.05")
)

# RQ2 ba-strict (sticky commitment): when enabled, once the episode is
# classified the gate COMMITS to the classified tier and suppresses the other
# tier even when it fires alone, until relief (score_norm < threshold for
# STRICT_RELEASE_N consecutive windows). The suppressed fire is still logged
# (*_fired=1, rejected_action). 0 = current per-window behavior unchanged.
_BOTTLENECK_STRICT_SINGLE = int(os.environ.get("BOTTLENECK_STRICT_SINGLE", "0"))
_STRICT_COMMIT_N = int(os.environ.get("STRICT_COMMIT_N", "2"))
_STRICT_RELEASE_N = int(os.environ.get("STRICT_RELEASE_N", "3"))

# ── RQ3 readiness-propagation gate ─────────────────────────────────
# READINESS_PROPAGATION selects compute-backend admission timing:
#   "off"       → current pre-RQ3 behavior: register into the VIP_SERVER pool
#                 immediately after spawn (no probe, no admission log, no
#                 readiness worker thread) — DEFAULT. Canonical / RQ1 / RQ2
#                 runs byte-identical.
#   "direct"    → RQ3 v2 arm (approach A, event-driven): admit on the edge's
#                 `app_ready` control event (no probe before admission);
#                 /ready is used only for the post-admission identity check,
#                 the event-absence safety net, and abandonment detection.
#   "discovery" → RQ3 arm: probe /ready only on DISCOVERY_POLL_INTERVAL_S
#                 cadence; admit when a discovery pass sees 200 (periodic
#                 discovery).
# Unknown value → log error + fall back to "off" (deliberate, documented).
_READINESS_PROPAGATION = os.environ.get("READINESS_PROPAGATION", "off")

# Per-attempt /ready HTTP timeout (seconds).
_READINESS_PROBE_TIMEOUT_S = float(os.environ.get("READINESS_PROBE_TIMEOUT_S", "5.0"))
# Abandon a pending backend that is not ready within this many seconds of
# spawn completion (full teardown + IP release). Must exceed
# DISCOVERY_POLL_INTERVAL_S and app startup time.
_READINESS_PROBE_MAX_S = float(os.environ.get("READINESS_PROBE_MAX_S", "120.0"))
# direct-mode probe retry interval (seconds). Must be << DISCOVERY_POLL_INTERVAL_S.
_READINESS_PROBE_RETRY_S = float(os.environ.get("READINESS_PROBE_RETRY_S", "1.0"))
# direct-mode event-absence safety net: no /ready probing until this many
# seconds after spawn-complete, giving the `app_ready` event time to arrive.
# A lost event cannot strand a ready backend — probing resumes afterwards
# (admit_source="probe_fallback"), which the analyzer's event-fraction gate
# surfaces as instrumentation-degraded.
_READINESS_EVENT_FALLBACK_S = float(os.environ.get("READINESS_EVENT_FALLBACK_S", "5.0"))
# discovery-mode scan cadence (seconds). Pre-registered per run.
_DISCOVERY_POLL_INTERVAL_S = float(os.environ.get("DISCOVERY_POLL_INTERVAL_S", "10.0"))
# Edge-server /ready port. Must equal the edge server's BIND_PORT (5000) in RQ3 runs.
_EDGE_READY_PORT = int(os.environ.get("EDGE_READY_PORT", "5000"))
# RQ3 admission log (per controller / per LAN). Written only when the gate is active.
_ADMISSION_LOG_PATH = os.environ.get("ADMISSION_LOG_PATH", "/tmp/admission_log.csv")
# Flow-isolation mode: 1 = delete a client's VIP_SERVER flows after each
# response (one fresh backend-selection event per request). RQ3 measurement
# instrumentation; 0 elsewhere.
_VIP_FLOW_ISOLATION = int(os.environ.get("VIP_FLOW_ISOLATION", "0"))
# Per-connection VIP_SERVER flow matching (RQ3 flow isolation, 2026-08-04).
# 0 (default) = per-CLIENT flows (one DNAT/SNAT pair per client, keyed by
#   client_mac); preserves canonical/RQ1/RQ2 byte-identical behavior and the
#   original D5 per-client design.
# 1 = per-CONNECTION flows keyed on tcp_src (the client's ephemeral port).
#   Each fresh request connection gets its own flow pair, so the async
#   request_complete delete for one request can never collide with the next
#   request's flow -> Check C delete coverage approaches 1.0 under the
#   calibrated spike rate (per-client flows shared a generation whenever the
#   delete landed after the next SYN). RQ3 arm envs set this to 1.
_VIP_SERVER_PER_CONNECTION = int(
    os.environ.get("VIP_SERVER_PER_CONNECTION_FLOWS", "0"))
# Misconfiguration guard: warn (once) if flow isolation is enabled but no
# request_complete events have arrived within this many seconds of startup.
_FLOW_ISOLATION_WARMUP_S = float(os.environ.get("FLOW_ISOLATION_WARMUP_S", "120.0"))

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
