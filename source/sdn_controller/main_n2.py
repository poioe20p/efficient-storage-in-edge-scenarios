import logging
import os
import time
from collections import deque

from os_ken.base import app_manager
from os_ken.controller import ofp_event
from os_ken.controller.handler import (
    CONFIG_DISPATCHER,
    MAIN_DISPATCHER,
    set_ev_cls,
)
from os_ken.lib.packet import ethernet, ether_types, packet
from os_ken.ofproto import ofproto_v1_3
from os_ken import cfg

from .elasticity.elasticity import ComputeAlert, DataAlert, ElasticityManager, ScaleDownComputeAlert, ScaleDownDataAlert
from .telemetry.models import TelemetrySummary, DomainSummary
from .telemetry.zmq_source import ZmqTelemetrySource
from .topology.topology import TopologyMixin
from .vip_routing import VipRoutingMixin

# Required so os-ken's app manager loads os_ken.topology.switches.
# topology.py imports os_ken.topology.api (which calls require_app with api_style=True),
# but that sets _REQUIRED_APP on the topology module, not on this entry-point module.
# The app manager resolves dependencies from sys.modules[cls.__module__], so it must
# be declared here explicitly.
_REQUIRED_APP = ['os_ken.topology.switches']

logger = logging.getLogger('os_ken.main_n2')

# ── Scale-up: weighted degradation score ────────────────────────────────
#
#  score = W_CPU * max(0, cpu - FLOOR) / SPAN  +  W_LAT * max(0, lat - FLOOR) / SPAN
#
# Score ≥ THRESHOLD for at least REQUIRED of the last WINDOW_SIZE windows triggers scale-up.

# Storage score weights & normalisation
_W_STORAGE_CPU  = float(os.environ.get("SCALEUP_W_STORAGE_CPU",  "0.3"))
_W_T_DB         = float(os.environ.get("SCALEUP_W_T_DB",         "0.7"))
_STORAGE_CPU_FLOOR = float(os.environ.get("SCALEUP_STORAGE_CPU_FLOOR", "50"))   # below this → 0 contribution
_STORAGE_CPU_SPAN  = float(os.environ.get("SCALEUP_STORAGE_CPU_SPAN",  "35"))   # 50+35=85% → score component = 1.0
_T_DB_FLOOR        = float(os.environ.get("SCALEUP_T_DB_FLOOR",        "15"))   # ms — baseline T_db
_T_DB_SPAN         = float(os.environ.get("SCALEUP_T_DB_SPAN",         "75"))   # 15+75=90ms → score component = 1.0

# Compute score weights & normalisation
_W_CPU      = float(os.environ.get("SCALEUP_W_CPU",      "0.3"))
_W_T_PROC   = float(os.environ.get("SCALEUP_W_T_PROC",   "0.7"))
_CPU_FLOOR  = float(os.environ.get("SCALEUP_CPU_FLOOR",  "50"))   # below this → 0 contribution
_CPU_SPAN   = float(os.environ.get("SCALEUP_CPU_SPAN",   "35"))   # 50+35=85% → score component = 1.0
_T_PROC_FLOOR = float(os.environ.get("SCALEUP_T_PROC_FLOOR", "1"))   # ms — baseline T_proc
_T_PROC_SPAN  = float(os.environ.get("SCALEUP_T_PROC_SPAN",  "11"))  # 1+11=12ms → score component = 1.0

# Scale-up sliding window
_SCALE_UP_SCORE_THRESHOLD  = float(os.environ.get("SCALEUP_SCORE_THRESHOLD", "0.40"))
_SCALE_UP_WINDOW_SIZE      = int(os.environ.get("SCALEUP_WINDOW_SIZE",      "5"))
_SCALE_UP_REQUIRED         = int(os.environ.get("SCALEUP_REQUIRED",         "2"))

# Adaptive storage threshold (predictive — lower base, increment per node)
_SCALEUP_STORAGE_BASE_THRESHOLD      = float(os.environ.get("SCALEUP_STORAGE_BASE_THRESHOLD", "0.25"))
_SCALEUP_STORAGE_THRESHOLD_INCREMENT = float(os.environ.get("SCALEUP_STORAGE_THRESHOLD_INCREMENT", "0.10"))
_SCALEUP_STORAGE_MAX_THRESHOLD       = float(os.environ.get("SCALEUP_STORAGE_MAX_THRESHOLD", "0.65"))
_SCALEUP_STORAGE_WINDOW_SIZE         = int(os.environ.get("SCALEUP_STORAGE_WINDOW_SIZE", "5"))
_SCALEUP_STORAGE_REQUIRED            = int(os.environ.get("SCALEUP_STORAGE_REQUIRED", "2"))

# Scale-down thresholds
_TAU_CPU_DOWN           = float(os.environ.get("TAU_CPU_DOWN",           "65"))
_TAU_PROC_DOWN_MS       = float(os.environ.get("TAU_PROC_DOWN_MS",       "5"))
_TAU_STORAGE_CPU_DOWN   = float(os.environ.get("TAU_STORAGE_CPU_DOWN",   "60"))
_TAU_DB_DOWN_MS         = float(os.environ.get("TAU_DB_DOWN_MS",         "100"))
_TELEMETRY_TIMEOUT_WINDOWS = int(os.environ.get("TELEMETRY_TIMEOUT_WINDOWS", "10"))

# Timeout ceiling — windows with latency above this are indeterminate (neither
# increment nor reset the sliding window).  Prevents RS election / connectivity
# timeouts from poisoning the scale-down signal.
_SCALE_DOWN_PROC_TIMEOUT_CEILING_MS = float(os.environ.get("SCALE_DOWN_PROC_TIMEOUT_CEILING_MS", "5000"))
_SCALE_DOWN_DB_TIMEOUT_CEILING_MS   = float(os.environ.get("SCALE_DOWN_DB_TIMEOUT_CEILING_MS",   "5000"))

# Sliding window — scale-down fires when at least REQUIRED of the last
# WINDOW_SIZE evaluation windows were below threshold.
_SCALE_DOWN_COMPUTE_WINDOW_SIZE = int(os.environ.get("SCALE_DOWN_COMPUTE_WINDOW_SIZE", "12"))
_SCALE_DOWN_COMPUTE_REQUIRED    = int(os.environ.get("SCALE_DOWN_COMPUTE_REQUIRED",    "7"))
_SCALE_DOWN_STORAGE_WINDOW_SIZE = int(os.environ.get("SCALE_DOWN_STORAGE_WINDOW_SIZE", "15"))
_SCALE_DOWN_STORAGE_REQUIRED    = int(os.environ.get("SCALE_DOWN_STORAGE_REQUIRED",    "9"))

# Scale-down cooldown — suppress scale-down evaluation for a grace period
# after scale-up to prevent thrashing (removing nodes before they're ready).
_SCALEDOWN_STORAGE_COOLDOWN_S = float(os.environ.get("SCALEDOWN_STORAGE_COOLDOWN_S", "120"))
_SCALEDOWN_COMPUTE_COOLDOWN_S = float(os.environ.get("SCALEDOWN_COMPUTE_COOLDOWN_S", "40"))

# Scale-UP cooldown — suppress storage scale-up evaluation for a grace period
# after a DataAlert is submitted, so the new node has time to join and absorb load.
_SCALEUP_STORAGE_COOLDOWN_S = float(os.environ.get("SCALEUP_STORAGE_COOLDOWN_S", "120"))

# Birth grace — skip absent-node detection for newly spawned nodes during bootstrap.
_NODE_BIRTH_GRACE_S = float(os.environ.get("NODE_BIRTH_GRACE_S", "60"))


class KenLearnAndLog(VipRoutingMixin, TopologyMixin, app_manager.OSKenApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        cfg.CONF.observe_links = True
        cfg.CONF.observe_hosts = True
        
        super(KenLearnAndLog, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.enable_reactive_learning = True
        self.datapaths = []
        self._datapath_by_id = {}
        self._lan_id = os.environ.get("LAN_ID", "lan2")

        _aggregator_endpoints = [
            ep.strip()
            for ep in os.environ.get(
                "AGGREGATOR_ENDPOINTS", "tcp://10.0.0.5:5556,tcp://10.0.1.5:5556"
            ).split(",")
            if ep.strip()
        ]
        _peer_endpoints = [
            ep.strip()
            for ep in os.environ.get("PEER_TOPOLOGY_ENDPOINTS", "").split(",")
            if ep.strip()
        ]
        logger.info("aggregator endpoints: %s", _aggregator_endpoints)
        logger.info("peer topology endpoints: %s", _peer_endpoints)
        logger.info(
            "scale-up: compute[\u03c4=%.2f window=%d/%d w_cpu=%.1f w_lat=%.1f]  "
            "storage[\u03c4_base=%.2f incr=%.2f cap=%.2f window=%d/%d w_cpu=%.1f w_lat=%.1f cooldown=%.0fs]",
            _SCALE_UP_SCORE_THRESHOLD, _SCALE_UP_REQUIRED, _SCALE_UP_WINDOW_SIZE,
            _W_CPU, _W_T_PROC,
            _SCALEUP_STORAGE_BASE_THRESHOLD, _SCALEUP_STORAGE_THRESHOLD_INCREMENT,
            _SCALEUP_STORAGE_MAX_THRESHOLD, _SCALEUP_STORAGE_REQUIRED, _SCALEUP_STORAGE_WINDOW_SIZE,
            _W_STORAGE_CPU, _W_T_DB, _SCALEUP_STORAGE_COOLDOWN_S,
        )

        # Thread 3 — must be created before ZmqTelemetrySource so the
        # on_update callback can safely reference self._elasticity.
        self._elasticity = ElasticityManager(topology_mixin=self)
        self._elasticity.start()

        # Dynamic node tracking for scale-down (populated on add, cleared on remove)
        self._dynamic_node_macs: set[str] = set()
        self._active: dict = {}           # mac -> NodeInfo (insertion order = LIFO)

        # Telemetry timeout: per-MAC absent-window counters
        self._absent_window_count: dict[str, int] = {}

        # Birth grace: per-MAC monotonic timestamp of first tracking
        self._birth_ts: dict[str, float] = {}

        # Underutilization: per-tier sliding-window deques (True = below threshold)
        self._scale_down_compute_window: deque[bool] = deque(maxlen=_SCALE_DOWN_COMPUTE_WINDOW_SIZE)
        self._scale_down_storage_window: deque[bool] = deque(maxlen=_SCALE_DOWN_STORAGE_WINDOW_SIZE)
        # Scale-up: per-tier sliding-window deques (True = score above threshold)
        self._scale_up_compute_window: deque[bool] = deque(maxlen=_SCALE_UP_WINDOW_SIZE)
        self._scale_up_storage_window: deque[bool] = deque(maxlen=_SCALEUP_STORAGE_WINDOW_SIZE)

        # Per-tier cooldowns: suppress scale-down for a grace period after scale-up.
        # Initialised to -inf so the cooldown condition is never true at startup
        # (time.monotonic() starts from an arbitrary reference, often system boot).
        self._last_storage_scale_up_ts: float = float('-inf')
        self._last_compute_scale_up_ts: float = float('-inf')

        # Thread 2 — ZMQ subscriber for telemetry summaries and topology updates.
        self._telemetry = ZmqTelemetrySource(
            endpoints=_aggregator_endpoints + _peer_endpoints,
            on_update=self._on_telemetry_update,
            on_topology_update=self.on_topology_update,
        )
        self._telemetry.start()

    def _on_telemetry_update(self, summary: TelemetrySummary) -> None:
        """Thread 2 callback — orchestrate telemetry processing and forward threshold breaches to Thread 3."""
        if summary.network_id != self._lan_id:
            logger.debug("ignoring telemetry for %s (this controller owns %s)", summary.network_id, self._lan_id)
            return

        self._sync_node_tracking()
        self._process_drain_events(summary)
        self._process_secondary_events(summary)

        # Mini-summaries (control event pass-throughs) have empty server dicts.
        # A regular summary always has at least one server from heartbeats.
        if not summary.servers and not summary.storage_servers:
            return

        self._log_and_update_stats(summary)
        self._promote_storage_from_telemetry(summary)

        try:
            lan = int(summary.network_id.replace("lan", ""))
        except ValueError:
            logger.warning("could not parse LAN from network_id=%s", summary.network_id)
            return

        self._detect_absent_nodes(summary)

        if self._elasticity.is_busy():
            logger.debug("[scale-down] elasticity manager is busy — skipping underutilisation check")
            return

        ds = summary.domain_summary
        self._evaluate_scale_up(ds, lan, summary.network_id)

        now = time.monotonic()

        compute_cooldown_remaining = _SCALEDOWN_COMPUTE_COOLDOWN_S - (now - self._last_compute_scale_up_ts)
        if compute_cooldown_remaining > 0:
            logger.debug(
                "[scale-down] compute within %.0fs cooldown — skipping",
                compute_cooldown_remaining,
            )
        else:
            self._evaluate_scale_down_compute(ds)

        storage_cooldown_remaining = _SCALEDOWN_STORAGE_COOLDOWN_S - (now - self._last_storage_scale_up_ts)
        if storage_cooldown_remaining > 0:
            logger.debug(
                "[scale-down] storage within %.0fs cooldown — skipping",
                storage_cooldown_remaining,
            )
        else:
            self._evaluate_scale_down_storage(ds)


    def _sync_node_tracking(self) -> None:
        """Consume removal and addition completions from Thread 3 into local tracking state."""
        for mac in self._elasticity.consume_removal_completions():
            self._dynamic_node_macs.discard(mac)
            self._absent_window_count.pop(mac, None)
            self._active.pop(mac, None)
            self._birth_ts.pop(mac, None)
            logger.info("[scale-down] removed MAC %s from dynamic tracking after cleanup", mac)

        for info in self._elasticity.consume_addition_completions():
            self._dynamic_node_macs.add(info.mac)
            self._active[info.mac] = info
            self._birth_ts[info.mac] = time.monotonic()
            logger.info("[scale-down] tracking new dynamic %s node mac=%s name=%s",
                        info.node_type, info.mac, info.name)

    def _process_drain_events(self, summary: TelemetrySummary) -> None:
        """Handle drain_complete control events forwarded by the aggregator."""
        for event in summary.control_events:
            if event.get("event_type") == "drain_complete":
                mac = event.get("server_id")
                if mac and self._elasticity.has_pending_drain(mac):
                    logger.info("[scale-down] drain_complete received for mac=%s — submitting Phase B cleanup", mac)
                    self._elasticity.submit_cleanup_compute(mac)

    def _process_secondary_events(self, summary: TelemetrySummary) -> None:
        """Handle rs_secondary_ready control events — add storage node to VIP pool."""
        for event in summary.control_events:
            if event.get("event_type") == "rs_secondary_ready":
                mac = event.get("server_id", None)
                if not mac:
                    continue
                info = self._active.get(mac, None)
                if info is None:
                    logger.warning("[scale-up] rs_secondary_ready for unknown mac=%s — ignoring", mac)
                    continue
                if info.node_type != "storage":
                    logger.warning("[scale-up] rs_secondary_ready for non-storage mac=%s — ignoring", mac)
                    continue
                self.add_storage_mac(mac, domain=f"n{info.lan}")
                logger.info(
                    "[scale-up] rs_secondary_ready received for mac=%s — "
                    "added to VIP storage pool (ip=%s, name=%s)",
                    mac, info.ip, info.name,
                )

    def _promote_storage_from_telemetry(self, summary: TelemetrySummary) -> None:
        """Fallback VIP promotion: detect SECONDARY from regular telemetry.

        If a storage node reports member_state=="SECONDARY" in its aggregated
        telemetry but has not been added to the VIP pool yet (rs_secondary_ready
        was lost or arrived before the socket was ready), promote it now.
        """
        for mac, ss in summary.storage_servers.items():
            if ss.member_state != "SECONDARY":
                continue
            info = self._active.get(mac, None)
            if info is None or info.node_type != "storage":
                continue
            domain = f"n{info.lan}"
            already_in = (
                mac in self._local_storage_macs_n1 if domain == "n1"
                else mac in self._local_storage_macs_n2
            )
            if already_in:
                continue
            self.add_storage_mac(mac, domain=domain)
            logger.info(
                "[scale-up] promoting storage mac=%s via telemetry fallback "
                "(member_state=SECONDARY, ip=%s, name=%s)",
                mac, info.ip, info.name,
            )


    def _log_and_update_stats(self, summary: TelemetrySummary) -> None:
        """Print domain summary metrics and push per-server stats to Thread 1."""
        ds = summary.domain_summary
        print(
            f"[telemetry] network={summary.network_id} "
            f"proc_ms={ds.avg_time_proc_ms:.1f} "
            f"db_ms={ds.avg_time_db_ms:.1f} "
            f"requests={ds.total_requests} "
            f"cpu={ds.average_cpu_percent:.1f}%"
        )
        self.update_server_stats(summary.servers)
        self.update_storage_stats(summary.storage_servers)


    def _detect_absent_nodes(self, summary: TelemetrySummary) -> None:
        """Detect dynamic nodes that have stopped reporting and trigger their removal."""
        now = time.monotonic()
        for mac in list(self._dynamic_node_macs):
            # Skip freshly spawned nodes that are still booting
            if now - self._birth_ts.get(mac, float('-inf')) < _NODE_BIRTH_GRACE_S:
                continue

            present = (mac in summary.servers) or (mac in summary.storage_servers)
            if present:
                self._absent_window_count[mac] = 0
            else:
                self._absent_window_count[mac] = self._absent_window_count.get(mac, 0) + 1
                count = self._absent_window_count[mac]
                logger.debug("[scale-down] mac=%s absent for %d windows", mac, count)
                if count >= _TELEMETRY_TIMEOUT_WINDOWS:
                    logger.warning("[scale-down] mac=%s absent for %d windows — triggering removal", mac, count)
                    self._absent_window_count[mac] = 0
                    if self._elasticity.has_pending_drain(mac):
                        # Phase A already ran; go straight to Phase B cleanup.
                        logger.info("[scale-down] pending drain exists for mac=%s — submitting CleanupComputeAlert", mac)
                        self._elasticity.submit_cleanup_compute(mac)
                    else:
                        self._submit_scale_down_alert(mac)


    @staticmethod
    def _degradation_score(cpu: float, latency: float,
                           w_cpu: float, w_lat: float,
                           cpu_floor: float, cpu_span: float,
                           lat_floor: float, lat_span: float) -> float:
        """Compute a weighted degradation score in [0, +inf)."""
        cpu_component = max(0.0, cpu - cpu_floor) / cpu_span if cpu_span else 0.0
        lat_component = max(0.0, latency - lat_floor) / lat_span if lat_span else 0.0
        return w_cpu * cpu_component + w_lat * lat_component

    def _count_dynamic_storage_nodes(self) -> int:
        """Count pending + active dynamic storage nodes for adaptive threshold."""
        return sum(
            1 for info in self._active.values()
            if info.node_type == "storage"
        )

    def _evaluate_storage_scale_up(self, ds: DomainSummary, lan: int, network_id: str) -> None:
        """Evaluate storage scale-up using adaptive threshold with a sliding window."""
        storage_score = self._degradation_score(
            ds.avg_storage_cpu_percent, ds.avg_time_db_ms,
            _W_STORAGE_CPU, _W_T_DB,
            _STORAGE_CPU_FLOOR, _STORAGE_CPU_SPAN,
            _T_DB_FLOOR, _T_DB_SPAN,
        )

        # Adaptive threshold: increases with each dynamic storage node
        dynamic_count = self._count_dynamic_storage_nodes()
        effective_threshold = min(
            _SCALEUP_STORAGE_BASE_THRESHOLD + dynamic_count * _SCALEUP_STORAGE_THRESHOLD_INCREMENT,
            _SCALEUP_STORAGE_MAX_THRESHOLD,
        )

        above = storage_score >= effective_threshold
        self._scale_up_storage_window.append(above)
        logger.debug(
            "[scale-up] storage score=%.2f (τ_eff=%.2f, base=%.2f +%d×%.2f) "
            "cpu_s=%.1f%% T_db=%.1fms  window=%d/%d on %s",
            storage_score, effective_threshold,
            _SCALEUP_STORAGE_BASE_THRESHOLD, dynamic_count, _SCALEUP_STORAGE_THRESHOLD_INCREMENT,
            ds.avg_storage_cpu_percent, ds.avg_time_db_ms,
            sum(self._scale_up_storage_window), len(self._scale_up_storage_window),
            network_id,
        )
        if sum(self._scale_up_storage_window) >= _SCALEUP_STORAGE_REQUIRED:
            logger.info(
                "[scale-up] storage triggered: %d/%d windows ≥ %.2f "
                "(eff_τ=%.2f, dyn_nodes=%d, last score=%.2f, cpu_s=%.1f%%, T_db=%.1fms) on %s",
                sum(self._scale_up_storage_window),
                len(self._scale_up_storage_window),
                effective_threshold, effective_threshold, dynamic_count,
                storage_score, ds.avg_storage_cpu_percent, ds.avg_time_db_ms, network_id,
            )
            self._scale_up_storage_window.clear()
            self._scale_down_storage_window.clear()  # cross-direction reset
            self._elasticity.submit(
                DataAlert(
                    lan=lan,
                    network_id=network_id,
                    rs_name=f"rs_net{lan}",
                    primary_container=f"edge_storage_server_n{lan}",
                )
            )
            self._last_storage_scale_up_ts = time.monotonic()

    def _evaluate_scale_up(self, ds: DomainSummary, lan: int, network_id: str) -> None:
        """Evaluate scale-up using weighted degradation scores with a sliding window."""
        # ── Compute score ──
        compute_score = self._degradation_score(
            ds.average_cpu_percent, ds.avg_time_proc_ms,
            _W_CPU, _W_T_PROC,
            _CPU_FLOOR, _CPU_SPAN,
            _T_PROC_FLOOR, _T_PROC_SPAN,
        )
        above = compute_score >= _SCALE_UP_SCORE_THRESHOLD
        self._scale_up_compute_window.append(above)
        logger.debug(
            "[scale-up] compute score=%.2f (τ=%.2f) cpu=%.1f%% T_proc=%.1fms  "
            "window=%d/%d on %s",
            compute_score, _SCALE_UP_SCORE_THRESHOLD,
            ds.average_cpu_percent, ds.avg_time_proc_ms,
            sum(self._scale_up_compute_window), len(self._scale_up_compute_window),
            network_id,
        )
        if sum(self._scale_up_compute_window) >= _SCALE_UP_REQUIRED:
            logger.info(
                "[scale-up] compute triggered: %d/%d windows ≥ %.2f "
                "(last score=%.2f, cpu=%.1f%%, T_proc=%.1fms) on %s",
                sum(self._scale_up_compute_window),
                len(self._scale_up_compute_window),
                _SCALE_UP_SCORE_THRESHOLD, compute_score,
                ds.average_cpu_percent, ds.avg_time_proc_ms, network_id,
            )
            self._scale_up_compute_window.clear()
            self._scale_down_compute_window.clear()  # cross-direction reset
            self._elasticity.submit(
                ComputeAlert(lan=lan, network_id=network_id)
            )
            self._last_compute_scale_up_ts = time.monotonic()

        # ── Storage score ──
        now = time.monotonic()
        scaleup_storage_cooldown_remaining = _SCALEUP_STORAGE_COOLDOWN_S - (now - self._last_storage_scale_up_ts)
        if scaleup_storage_cooldown_remaining > 0:
            logger.debug(
                "[scale-up] storage within %.0fs scale-up cooldown — skipping",
                scaleup_storage_cooldown_remaining,
            )
        else:
            self._evaluate_storage_scale_up(ds, lan, network_id)

    def _evaluate_scale_down_compute(self, ds: DomainSummary) -> None:
        """Evaluate compute scale-down and remove the last added dynamic compute node if sustained."""
        # Timeout guard — indeterminate window; skip without affecting the sliding window.
        if ds.avg_time_proc_ms > _SCALE_DOWN_PROC_TIMEOUT_CEILING_MS:
            logger.debug(
                "[scale-down] compute: avg_time_proc_ms=%.1f exceeds timeout ceiling (%.0f) — skipping window",
                ds.avg_time_proc_ms, _SCALE_DOWN_PROC_TIMEOUT_CEILING_MS,
            )
            return

        below = (ds.average_cpu_percent < _TAU_CPU_DOWN
                 and ds.avg_time_proc_ms < _TAU_PROC_DOWN_MS)
        self._scale_down_compute_window.append(below)

        if sum(self._scale_down_compute_window) >= _SCALE_DOWN_COMPUTE_REQUIRED:
            last = self._find_last_dynamic_compute_node()
            if last is not None:
                logger.info(
                    "[scale-down] compute underutilisation: %d/%d windows below threshold — removing %s",
                    sum(self._scale_down_compute_window),
                    len(self._scale_down_compute_window), last.name,
                )
                self._scale_down_compute_window.clear()
                self._submit_scale_down_alert(last.mac)
            else:
                # No eligible node; discard accumulated windows
                self._scale_down_compute_window.clear()

    def _evaluate_scale_down_storage(self, ds: DomainSummary) -> None:
        """Evaluate storage scale-down and remove the last added dynamic storage node if sustained."""
        # Timeout guard — indeterminate window; skip without affecting the sliding window.
        if ds.avg_time_db_ms > _SCALE_DOWN_DB_TIMEOUT_CEILING_MS:
            logger.debug(
                "[scale-down] storage: avg_time_db_ms=%.1f exceeds timeout ceiling (%.0f) — skipping window",
                ds.avg_time_db_ms, _SCALE_DOWN_DB_TIMEOUT_CEILING_MS,
            )
            return

        below = (ds.avg_storage_cpu_percent < _TAU_STORAGE_CPU_DOWN
                 and ds.avg_time_db_ms < _TAU_DB_DOWN_MS)
        self._scale_down_storage_window.append(below)

        if sum(self._scale_down_storage_window) >= _SCALE_DOWN_STORAGE_REQUIRED:
            last = self._find_last_dynamic_storage_node()
            if last is not None:
                logger.info(
                    "[scale-down] storage underutilisation: %d/%d windows below threshold — removing %s",
                    sum(self._scale_down_storage_window),
                    len(self._scale_down_storage_window), last.name,
                )
                self._scale_down_storage_window.clear()
                self._submit_scale_down_alert(last.mac)
            else:
                self._scale_down_storage_window.clear()

    def _find_last_dynamic_compute_node(self):
        """Return the NodeInfo for the most recently added dynamic compute node (LIFO)."""
        for mac, info in reversed(list(self._active.items())):
            if info.node_type == "compute" and mac in self._dynamic_node_macs:
                return info
        return None

    def _find_last_dynamic_storage_node(self):
        """Return the NodeInfo for the most recently added dynamic storage node (LIFO)."""
        for mac, info in reversed(list(self._active.items())):
            if info.node_type == "storage" and mac in self._dynamic_node_macs:
                return info
        return None

    def _submit_scale_down_alert(self, mac: str) -> None:
        """Build and submit the appropriate scale-down alert for the given MAC.

        Only dynamically added MACs are eligible — static/primary nodes are
        never removed.  Looks up the NodeInfo to populate all alert fields.
        """
        if mac not in self._dynamic_node_macs:
            logger.warning("[scale-down] mac=%s not in dynamic_node_macs — ignoring", mac)
            return
        info = self._active.get(mac)
        if info is None:
            logger.warning("[scale-down] no NodeInfo for mac=%s — cannot build alert", mac)
            return

        if info.node_type == "compute":
            alert = ScaleDownComputeAlert(
                lan=info.lan,
                network_id=info.network_id,
                container_name=info.name,
                mac=mac,
                ip=info.ip,
            )
        else:
            alert = ScaleDownDataAlert(
                lan=info.lan,
                network_id=info.network_id,
                container_name=info.name,
                mac=mac,
                ip=info.ip,
                rs_name=info.rs_name,
                primary_container=info.primary_container,
                port=info.port,
            )
        logger.info("[scale-down] submitting alert: %s", alert)
        self._elasticity.submit(alert)

    def _install_flow(self, datapath, priority, match, actions, *,
                      idle_timeout=0, hard_timeout=0, cookie=0, flags=None):
        ofproto = datapath.ofproto
        if flags is None:
            flags = ofproto.OFPFF_SEND_FLOW_REM
                
        instructions = [
            datapath.ofproto_parser.OFPInstructionActions(
                ofproto.OFPIT_APPLY_ACTIONS,
                actions,
            )
        ]
        mod = datapath.ofproto_parser.OFPFlowMod(
            datapath=datapath,
            priority=priority,
            match=match,
            instructions=instructions,
            idle_timeout=idle_timeout,
            hard_timeout=hard_timeout,
            cookie=cookie,
            flags=flags,
            command=ofproto.OFPFC_ADD,
        )
        datapath.send_msg(mod)


    def add_flow(self, datapath, in_port, dst, src, actions):
        """Default reactive learning-switch rule installer."""
        parser = datapath.ofproto_parser
        match = parser.OFPMatch(
            in_port=in_port,
            eth_dst=dst,
            eth_src=src,
        )
        
        self._install_flow(
            datapath,
            priority=10,
            match=match,
            actions=actions,
            # idle_timeout=int(getattr(self, "l2_flow_idle_timeout_sec", 0) or 0),
            flags=datapath.ofproto.OFPFF_SEND_FLOW_REM,
        )


    # Event handler for switch features. This method is triggered when a switch connects to the controller.
    # @set_ev_cls decorator tells OS-Ken that the method "switch_features_handler" should be invoked when an EventOFPSwitchFeatures event is received.
    # CONFIG_DISPATCHER means this event is handled after the switch enters the configuration phase (after the initial handshake between switch and controller).
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, event):
        """Install the table-miss flow entry when the switch connects. 
        At first switch is configured to flood all packets in order to learn MAC addresses."""
    
        # Extract the datapath object, which represents in the controller enviroment the switch that is communicating with the controller.
        # The datapath contains information about the switch (datapath ID, methods to send messages, etc.)
        datapath = event.msg.datapath

        # ofproto represents the OpenFlow protocol, which includes constants (like action types and message types).
        ofproto = datapath.ofproto

        # The parser helps in creating OpenFlow messages such as matches, actions, flow mods, etc.
        parser = datapath.ofproto_parser
        
        # Register datapath early so proactive VIP rules can find the edge switch.
        self._datapath_by_id[datapath.id] = (datapath, datapath.id)

        if not any(getattr(dp, "id", None) == datapath.id for dp in self.datapaths):
            self.datapaths.append(datapath)

        # Create a match object with no specific fields, meaning it will match all packets (wildcard match).
        # This is the default behavior of a hub, which forwards all traffic.
        match = parser.OFPMatch()
        
        # Create an action to output the packets to the controller and not buffer them.
        # This ensures that all packets that do not match any flow entries are sent to the controller
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
        
        # Create a flow modification message to install the "table-miss" flow entry in the switch.
        instructions = [
            parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)
        ]
        mod = datapath.ofproto_parser.OFPFlowMod(
            datapath=datapath, # The switch this flow is being installed on.
            priority=0, # The lowest priority for the table-miss flow entry.
            match=match, # specifies the matching rule (matches all packets here because the match is empty and any traffic becomes selected).
            instructions=instructions, # Apply actions through the OpenFlow 1.3 instruction pipeline.
            flags=ofproto.OFPFF_SEND_FLOW_REM # flag that tells the switch to notify the controller when the flow is removed.
        )
        datapath.send_msg(mod)


    # Packet In Handler
    # This method is triggered when a packet is received by the switch.
    # It learns MAC addresses and their associated ports, logs the event, and forwards the packet.
    # The next time a packet with the same source and destination MAC addresses is received, it will be forwarded directly without flooding or 
    # involving the controller again.
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, event):
        """Learn MAC-port mappings, log the event, and forward the packet."""

        msg = event.msg  # Extract the message from the event
        datapath = msg.datapath  # Get the switch (datapath) that sent the message
        ofproto = datapath.ofproto  # Get the OpenFlow protocol constants for this datapath
        parser = datapath.ofproto_parser  # Get the OpenFlow message parser for creating messages
        in_port = msg.match["in_port"]  # Get the input port from which the packet was received
        
        pkt = packet.Packet(msg.data) # Create a Packet object from the incoming packet data
        eth = pkt.get_protocol(ethernet.ethernet) # Extract the Ethernet header from the message
        dst = eth.dst # Get the destination MAC address from the Ethernet header frame
        src = eth.src # Get the source MAC address from the Ethernet header frame
        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        # VIP interception — runs before L2 learning so VIP-destined packets
        # are not forwarded by L2 rules before DNAT is installed.
        self.snoop_arp(pkt)
        if self.handle_vip_packet_in(datapath, in_port, pkt, eth):
            return

        dpid_int = int(datapath.id)  # Datapath ID as integer for shard key routing
        self.mac_to_port.setdefault(dpid_int, {})  # Initialize mapping for this switch if absent
        
        # Learn a MAC address to avoid flooding next time.
        # Always update — handles the case where a container is replaced on a
        # different OVS port but retains the same MAC (elasticity retries).
        self.mac_to_port[dpid_int][src] = in_port
        
        # Determine the output port for the destination MAC address    
        if dst in self.mac_to_port[dpid_int]:
            out_port = self.mac_to_port[dpid_int][dst]
        else:
            # Flood the packet if the destination MAC is unknown
            out_port = ofproto.OFPP_FLOOD

        # Create the action to forward the packet to the determined output port
        actions = [parser.OFPActionOutput(out_port)]

        # Install a flow entry to avoid future packet_in events for this flow
        if self.enable_reactive_learning and out_port != ofproto.OFPP_FLOOD:
            self.add_flow(datapath, in_port, dst, src, actions)
        
        data = None
        # If the packet is not buffered on the switch, include the packet data in the packet-out message
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        # Create a packet-out message to send the packet out of the switch
        out = datapath.ofproto_parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=data,
        )
        
        # Send the packet-out message to the switch
        datapath.send_msg(out)
