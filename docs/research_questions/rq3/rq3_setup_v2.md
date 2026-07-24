# RQ3 v2 — Experiment Setup Declaration

> **Canonical reference** for how RQ3 will be tested. Values extracted from
> `phases.json`, `current_state_integrated.env`, `osken-controller.env`,
> `scaling_config.py`, G0-v6 validation results, and C3b calibration results.
> **Corresponding RQ doc**: [`rq3_v2.md`](rq3_v2.md)
> **Status**: **Draft** — resource configuration and scoring thresholds pending
> Phase 1a calibration (§3.6 of rq3_v2.md). Values marked **(TBD)** will be
> finalised before the 9-run evaluation begins.

---

## 1. Phases — `phases.json`

**The canonical phases file** (`source/scripts/testing/phases.json`). No
RQ3-specific variant — the same workload used by RQ1 and RQ2, ensuring
cross-RQ comparability.

7 phases, 1,440 s total (~24 min). Tier 1 selective-sync enabled
(`SS_ENABLED=1`) — exercises storage, Tier 1, and compute stress in a
single run, giving all three trigger modes a rich detection surface.

| # | Phase | Duration | Rate/client | Cross-region | Client frac | Dominant mix |
|---|-------|----------|-------------|--------------|-------------|-------------|
| 1 | `baseline` | 60 s | 1.0 | 0% | 10% | 60% lookup, 25% ranking, 15% pressure |
| 2 | `storage_storm` | 240 s | 4.0 | 90% | 100% | 35% lookup, 30% update, 20% aggregate |
| 3 | `tier1_hotspot` | 180 s | 5.0 | 40% | 100% | 80% lookup — Tier 1 selective-sync stress |
| 4 | `inter_hotspot_cooldown` | 300 s | 1.0 | 0% | 10% | baseline mix — drain before reverse hotspot |
| 5 | `reverse_hotspot` | 180 s | 5.0 | 40% | 100% | 80% lookup — hotspot direction reversed |
| 6 | `compute_spike` | 180 s | 2.0 | 0% | 100% | 100% `service_pressure` — pure compute stress |
| 7 | `demand_drop` | 300 s | 1.0 | 0% | 10% | baseline mix — extended drain for scale-down observation |

### Rationale for key design choices

| Choice | Why |
|--------|-----|
| Canonical phases.json (no RQ3 variant) | Cross-RQ comparability. RQ1 and RQ2 use this workload; RQ3 using it means all three RQs are evaluated under identical demand patterns. |
| 90% cross-region in `storage_storm` | Saturates WAN links, stresses storage tier cross-LAN routing — produces T_db elevation that all three trigger modes must detect. |
| 40% cross-region in hotspot phases | Enough to trigger Tier 1 selective sync without saturating WAN (G0-v6 validated: T_db 209–292 ms in tier1_hotspot, 221–838 ms in reverse_hotspot). |
| 100% `service_pressure` in `compute_spike` | Isolates compute-bound stress — no storage component to confound. At 0.08/0.25 CPUs with 96 clients, CPU pre→post drop is 23–28pp (G0-v6 validated). |
| 300 s `inter_hotspot_cooldown` | Longer than cleanup gaps because hotspot phases need more drain time (higher rate = more inflight requests). |
| 300 s `demand_drop` | Extended final drain — allows observation of full scale-down sequence. |
| No cleanup gaps between phases | Unlike RQ1 (which needs gaps to isolate detection speed), RQ3 evaluates detection *composition* — nodes may persist across phases, and that's acceptable. The phase transitions exercise the cooldown mechanisms identically for all three modes. |

### Phase-type grouping (for G5b — Latency by Phase Type)

| Group | Phases | Dominant latency factor |
|---|---|---|
| **Baseline** | baseline | Routing quality — only phase guaranteed to start quiescent |
| **Storage stress** | storage_storm, tier1_hotspot, reverse_hotspot | Storage I/O (content_update, content_aggregate, cross-region MongoDB reads) |
| **Compute stress** | compute_spike | CPU saturation (service_pressure) |
| **Post-stress** | inter_hotspot_cooldown, demand_drop | Mixed — residual effects from preceding stress phase |

---

## 2. Resource Limits

**Status**: **(TBD)** — to be determined by Phase 1a calibration (§3.6 of
rq3_v2.md). The calibration selects the configuration where pre-scale→post-scale
improvement in CPU and latency is clearest for both tiers.

### 2.1 Candidate: G0-v6 (Validated)

The G0-v6 configuration at 0.08/0.25 CPUs with WAN=185 ms has been validated
through 6 G0 iterations (v1→v6). It produces:

- **compute_spike**: CPU pre→post drop of 23–28pp on both LANs (G0-v6)
- **storage_storm**: T_db pre→post improvement confirmed; storage scoring loop
  closes at τ=0.35 (G0-v6)
- **All success rates ≥ 96.6%** across all phases
- **Storage cap at 8 not exceeded** (7 nodes at peak, below the 8-node cap)

| Parameter | Candidate Value | Source | Rationale |
|-----------|----------------|--------|-----------|
| `CLIENTS` | 96 (48/LAN) | RQ1 v8 golden | Matches RQ1/RQ2 client count for cross-RQ comparability |
| `MAX_DYNAMIC_COMPUTE` | 12 | RQ1 v8 golden | Raised from v2's 4; gives all modes room to demonstrate spawn count differences |
| `MAX_DYNAMIC_STORAGE` | 8 | RQ1 v8 golden | Raised from v2's 5; G0-v6 peaked at 7, so cap is adequate |
| `STORAGE_CPUS` | 0.08 | G0-v6 validated | Tight enough to create CPU pressure during storage_storm without I/O-wait dominance |
| `STORAGE_MEMORY` | 512m | Default in `build_network_*.sh` | |
| `EDGE_CPUS` | 0.25 | G0-v2 proposal | Tighter than RQ1's 0.30 to increase compute CPU pressure; exact value TBD from calibration |
| `EDGE_MEMORY` | 256m | Default in `build_network_*.sh` | |
| `CURL_MAX_TIME` | 30 s | RQ1 v8 golden | Hard timeout for client HTTP requests |
| `WAN_RTT_MS` | 185 ms | G0-v6 validated | One-way WAN delay (~92 ms per direction); reduced from 260 ms (G0-v1) to reduce I/O-wait dominance |

### 2.2 Why Not C4 (0.04/0.06 CPUs)?

The C3b calibration at C4 resources (`STORAGE_CPUS=0.04`, `EDGE_CPUS=0.06`,
WAN=260 ms) was the original RQ3 target but has three issues:

| Issue | Detail |
|-------|--------|
| **Baseline instability** | Edge CPU spikes to 72–92% in ~2 of 12 baseline windows. This produces ~1 score-triggered FP per run even with aggressive floors (CPU_FLOOR=70). The FP is random system noise — it affects all three modes equally, diluting the signal. |
| **Cross-tier contamination** | At C4, both tiers are stressed simultaneously — when one tier's stress phase runs, the other tier's metrics also spike. This muddies per-tier trigger evaluation. |
| **Threshold sensitivity asymmetry** | C3b floors (CPU_FLOOR=70, T_PROC_FLOOR=80) are so aggressive that only extreme spikes cross them. This compresses the behavioral space — all three modes may look identical because the floors filter almost everything. |

G0-v6 (0.08/0.25, WAN=185) has lower baseline variance and cleaner tier
separation. The calibration will confirm whether it also meets the
pre-scale→post-scale improvement requirement.

---

## 3. Controller Scoring — Compute Scale-Up

**Independent variable**: the four weight variables (`SCALEUP_W_CPU`,
`SCALEUP_W_T_PROC`, `SCALEUP_W_STORAGE_CPU`, `SCALEUP_W_T_DB`). All
other parameters (floors, spans, thresholds, window counts, cooldowns)
are **identical across all three modes**.

### 3.1 Weights — Independent Variable (Per-Mode)

Three env override files, differing only in the four weight variables:

| Variable | `degradation_score` | `cpu_only` | `latency_only` |
|----------|---------------------|------------|----------------|
| `SCALEUP_W_CPU` | 0.40 | 1.00 | 0.00 |
| `SCALEUP_W_T_PROC` | 0.60 | 0.00 | 1.00 |
| `SCALEUP_W_STORAGE_CPU` | 0.60 | 1.00 | 0.00 |
| `SCALEUP_W_T_DB` | 0.40 | 0.00 | 1.00 |

**Why these weights**: The `degradation_score` weights (0.40/0.60 for compute,
0.60/0.40 for storage) emerged from pre-experiment calibration and are held
constant. The single-dimension weights (1.00/0.00) are the logical extremes —
the industry default (CPU-only) and the user-experience dimension
(latency-only). The comparison is between three points in the design space,
not between tuned optima.

### 3.2 Floors, Spans, and Thresholds — **(TBD)**

**Status**: These must be calibrated so that ALL three modes produce meaningful
behavioral differences at the selected resource configuration. The calibration
must satisfy:

1. `degradation_score` produces near-zero FPs during baseline
2. `cpu_only` produces measurably more FPs than `degradation_score` during
   baseline (CPU spikes without latency confirmation)
3. `latency_only` produces measurably more FPs than `degradation_score` during
   baseline (transient latency spikes without CPU confirmation)
4. All three modes fire reliably during stress phases
5. No single mode is advantaged by the chosen floors/spans

**Starting point**: G0-v6 validated values (from `current_state_integrated.env`),
which work for `degradation_score` at 0.08/0.25 CPUs with WAN=185 ms. These
must be verified to also produce the expected behavioral differences for
`cpu_only` and `latency_only`.

| Parameter | G0-v6 Starting Point | Default | Role |
|-----------|---------------------|---------|------|
| `SCALEUP_CPU_FLOOR` | 10 | 5 | Below-floor CPU = zero CPU component. Must be above baseline noise, below stress saturation. |
| `SCALEUP_CPU_SPAN` | 40 | 10 | Wider span prevents score saturation at moderate CPU. Critical for `cpu_only` — determines sensitivity. |
| `SCALEUP_T_PROC_FLOOR` | 25 ms | 20 ms | Below-floor T_proc = zero latency component. Must be above healthy edge latency (~5–15 ms), below stress latency. |
| `SCALEUP_T_PROC_SPAN` | 80 | 80 | Explicit — matches code default. Determines how quickly latency component saturates. |
| `SCALEUP_COMPUTE_BASE_THRESHOLD` | 0.18 | 0.45 | Lowered: wider span compresses scores; threshold compensates. Must be above baseline scores, below stress scores. |
| `SCALEUP_COMPUTE_THRESHOLD_INCREMENT` | 0.10 | 0.10 | Default — adaptive escalation per existing dynamic node. |
| `SCALEUP_COMPUTE_MAX_THRESHOLD` | 0.85 | 0.85 | Default — ceiling for adaptive threshold. |
| `SCALEUP_WINDOW_SIZE` | 5 | 5 | Default — 5 telemetry windows evaluated. |
| `SCALEUP_REQUIRED` | 3 | 3 | Default — 3 of 5 windows must breach threshold. Prevents single-window spikes from triggering. |
| `SCALEUP_COMPUTE_COOLDOWN_S` | 45 s | 45 s | Default — grace period after each spawn. |
| `SCALEUP_COMPUTE_PEER_RELIEF` | 0.03 | 0.03 | Default — score reduction per peer node. |
| `SCALEUP_COMPUTE_PEER_HEALTH_THRESHOLD` | 0.35 | 0.35 | Default — peer considered healthy below this. |

**Why CPU_SPAN=40 is critical**: `CPU_SPAN=5` (RQ1 v3) caused immediate score
saturation — the controller spawned at every minor CPU bump. `CPU_SPAN=40`
(RQ1 v4 onward) makes the score linear across the observed CPU range (0–50%).
For RQ3, this is essential: if the span is too narrow, `cpu_only` saturates
immediately and cannot be distinguished from `degradation_score`. If too wide,
`cpu_only` never crosses threshold and cannot be distinguished from
`latency_only`. The span controls the dynamic range — the calibration must
find the value where the three modes diverge.

### 3.3 Calibration Verification

Before the 9-run evaluation, a single verification run with each mode at the
calibrated thresholds must confirm:

| Check | What to verify |
|-------|---------------|
| `cpu_only` baseline FPs > `degradation_score` baseline FPs | CPU spikes without latency confirmation cross threshold |
| `latency_only` baseline FPs > `degradation_score` baseline FPs | Transient latency spikes without CPU confirmation cross threshold |
| All three modes fire during `storage_storm` and `compute_spike` | No mode is blind to genuine overload |
| Score component decomposition (G8 data) shows distinct trigger patterns | The three modes are behaviourally different |

---

## 4. Controller Scoring — Storage Scale-Up

### 4.1 Weights — Independent Variable (Per-Mode)

Same pattern as compute: weights vary, everything else identical.

| Variable | `degradation_score` | `cpu_only` | `latency_only` |
|----------|---------------------|------------|----------------|
| `SCALEUP_W_STORAGE_CPU` | 0.60 | 1.00 | 0.00 |
| `SCALEUP_W_T_DB` | 0.40 | 0.00 | 1.00 |

> **Note on storage CPU weight**: The G0-v6 config uses `SCALEUP_W_STORAGE_CPU=0`
> (latency-only storage scaling) because at 0.08 CPUs, storage CPU is I/O-wait
> and not a meaningful scaling signal. For RQ3, the `degradation_score` mode
> uses the canonical 0.60/0.40 weights to test whether CPU adds value as a
> storage signal. The `cpu_only` mode tests whether CPU alone can drive storage
> scaling. The calibration will reveal whether storage CPU is a viable signal
> at the selected resource configuration.

### 4.2 Floors, Spans, and Thresholds — **(TBD)**

| Parameter | G0-v6 Starting Point | Default | Role |
|-----------|---------------------|---------|------|
| `SCALEUP_STORAGE_CPU_FLOOR` | 1.5 | 5 | Lowered to match tight CPU limits. Storage CPU at 0.08 CPUs is typically 1–5% at baseline. |
| `SCALEUP_STORAGE_CPU_SPAN` | 5 | 10 | Narrower span for constrained CPU range. |
| `SCALEUP_T_DB_FLOOR` | 60 ms | 150 ms | Lowered: storage latency at 0.08 CPUs elevates earlier than at default 0.10 CPUs. |
| `SCALEUP_T_DB_SPAN` | 250 ms | 600 ms | Narrower: tighter latency range at this CPU level. |
| `SCALEUP_STORAGE_BASE_THRESHOLD` | 0.35 | 0.25 | Raised: G0-v6 validated — storage scoring loop closes at τ=0.35. |
| `SCALEUP_STORAGE_THRESHOLD_INCREMENT` | 0.10 | 0.10 | Default. |
| `SCALEUP_STORAGE_MAX_THRESHOLD` | 0.55 | 0.55 | Default. |
| `SCALEUP_STORAGE_WINDOW_SIZE` | 5 | 5 | Default. |
| `SCALEUP_STORAGE_REQUIRED` | 2 | 2 | Default — 2 of 5 windows must breach. |
| `SCALEUP_STORAGE_COOLDOWN_S` | 120 s | 120 s | Default. |

---

## 5. Scale-Down

**Status**: **(TBD)** — scale-down parameters may need adjustment if the
resource configuration changes from G0-v6. Starting point: RQ1 v8 golden
values.

| Parameter | Starting Point | Default | Rationale |
|-----------|---------------|---------|-----------|
| `SCALEDOWN_COMPUTE_COOLDOWN_S` | 180 s | 40 s | **Raised** — keeps nodes alive through phase transitions. Complements the absence of cleanup gaps (unlike RQ1, RQ3 allows nodes to persist across phases). |
| `SCALE_DOWN_COMPUTE_REQUIRED` | 9 | 7 | Raised — requires stronger evidence of sustained low load. |
| `SCALE_DOWN_COMPUTE_WINDOW_SIZE` | 12 | 12 | Default. |
| `SCALE_DOWN_STORAGE_WINDOW_SIZE` | 12 | 12 | Default. |
| `SCALE_DOWN_STORAGE_REQUIRED` | 7 | 7 | Default. |
| `SCALEDOWN_STORAGE_COOLDOWN_S` | 120 s | 120 s | Default. |
| `TELEMETRY_TIMEOUT_WINDOWS` | 18 | 18 | Default — 18 windows (~180 s) without telemetry → node marked dead. |
| `NODE_BIRTH_GRACE_S` | 60 s | 60 s | Default — skip dead-node detection for first 60 s after spawn. |

---

## 6. VIP Routing

Held constant — RQ2's domain. Warm-lease routing (`topology_lifecycle`)
eliminates the LB discovery gap so trigger composition is the only variable.

| Parameter | Value | Default | Rationale |
|-----------|-------|---------|-----------|
| `BACKEND_SELECTION_POLICY` | `topology_lifecycle` | `topology_lifecycle` | **Fixed** — warm lease at spawn time. Eliminates the routing-plane coordination gap (RQ2's domain). |
| `VIP_IDLE_TIMEOUT` | 30 s | 30 s | Default — flow idle before eviction. |
| `VIP_HARD_TIMEOUT` | 60 s | 120 s | **Halved** — from `current_state_integrated.env`; forces flow re-evaluation sooner. |
| `W_CPU` (server WSM) | 0.3 | 0.2 | From `osken-controller.env` — CPU-weighted routing. |
| `W_RAM` | 0.1 | 0.2 | From `osken-controller.env`. |
| `W_REQUESTS` | 0.2 | 0.2 | Default. |
| `W_HOPS` | 0.28 | 0.28 | Default. |
| `CROSS_NETWORK_HOP_PENALTY` | 3 | 3 | Default — additive penalty for cross-LAN backends. |

---

## 7. Telemetry Aggregation

Held constant — RQ1's domain. Push-mode delivery (ZMQ at window close)
eliminates the monitoring blind spot so trigger composition is the only
variable.

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Aggregation window (`WINDOW_S`) | 10 s | Default — 10 s summaries; fixed. |
| Delivery mode | **Push** (ZMQ, window-close) | Held constant — RQ1's optimal delivery. Eliminates the monitoring blind spot. |
| Latency signal | **Mean-only** (`avg_time_proc_ms`, `avg_time_db_ms`) | G0-v2 decision — avoids timeout-censored p95 contamination. Consistent with autoscaling literature (all 16 reviewed papers use mean/rate/ratio for triggers). |
| Aggregator cache | HTTP `/telemetry/latest` — always holds freshest completed window | Not used for push mode; available for verification. |

### 7.1 Latency Signal: Mean-Only Rationale

G0-v1 used `max(avg, p95)` for both tiers (the "symmetric signal"). Analysis
revealed this is counterproductive: when a significant fraction of requests
hit the 30 s client timeout, p95 measures the timeout ceiling (30,001 ms),
not the system's actual performance. The p95 value is timeout-censored and
misleading as a trigger input.

Both tiers use **mean-only** latency signals:

| Tier | Signal | Source |
|------|--------|--------|
| **Compute** | `ds.avg_time_proc_ms` | `scaling_policy.py:compute_latency_signal()` |
| **Storage** | `ds.avg_time_db_ms` | `scaling_policy.py:storage_latency_signal()` |

p95 remains collected in telemetry for SLO monitoring and post-hoc analysis
but is excluded from the degradation score. This is consistent with the
autoscaling literature — all 16 reviewed papers use mean (or rate/ratio) for
triggering, never percentiles.

---

## 8. Topology & Seeds

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `RANDOM_SEED` | 42 | Fixed across all runs — deterministic client behavior. |
| `DATA_SEED` | 42 | Fixed across all runs — deterministic test data. |
| `DEVICES` | 6000 | Synthetic device pool for content generation. |
| `NODES` | 100 | Synthetic content nodes. |
| Topology | 2 LANs, 1 NAT router, OVS bridges | Static throughout all runs. |
| Static backends/LAN | 1 edge_server, 1 edge_storage_server, 1 aggregator | Fixed. |
| SDN controller | OS-Ken/Ryu, 2 instances (LAN1 + LAN2), shared topology | Fixed. |
| Tier 1 selective sync | **Enabled** (`SS_ENABLED=1`) | Fixed — exercises Tier 1 pool. All three modes experience the same Tier 1 behavior. |
| Persistent reserve | **Enabled** (`STORAGE_PERSISTENT_RESERVE_ENABLED=1`) | Fixed — pre-warms a storage node. Reserve spawns are NOT degradation-score FPs; they are excluded from M1 (baseline FP spawns). |
| Warm-lease TTLs | Server 45 s, Storage 30 s | `scaling_config.py` defaults. |

---

## 9. Docker Images

| Image | Notes |
|-------|-------|
| `edge_server` | May need rebuild if `FEED_INTEGRITY_WORK_FACTOR` is adjusted during calibration. |
| `edge_storage_server` | Unchanged. |
| `edge_selective_storage` | Used (SS_ENABLED=1). |
| `osken-controller` | Requires the mean-only latency signal code change (§7.1) — `scaling_policy.py` methods changed to return `avg_time_proc_ms` / `avg_time_db_ms`. |
| `local_state_server` | Unchanged. |
| `ovs-container` | Unchanged. |
| `ubuntu-nat-router` | Unchanged. |

### 9.1 Code Change Required: Mean-Only Latency Signal

Before RQ3 runs begin, two methods in `source/sdn_controller/scaling_policy.py`
must be changed:

```python
@staticmethod
def compute_latency_signal(ds: DomainSummary) -> float:
    """Mean proc latency — avoids timeout-censored p95 contamination."""
    return ds.avg_time_proc_ms

@staticmethod
def storage_latency_signal(ds: DomainSummary) -> float:
    """Mean DB latency — avoids timeout-censored p95 contamination."""
    return ds.avg_time_db_ms
```

The p95 computation in `aggregator.py` and `models.py` is **preserved** —
p95 remains available for monitoring and post-hoc analysis, just not for
trigger decisions.

---

## 10. Run Matrix

3 modes × 3 replicates = 9 runs. Order: degradation_score → cpu_only →
latency_only (grouped by mode for operational efficiency).

| # | Label | Trigger Mode | Env Override File | Weight Variables |
|---|-------|-------------|-------------------|------------------|
| DS1–DS3 | `rq3_v2_ds_{1,2,3}` | `degradation_score` | `rq3_v2_degradation_score.env` | W_CPU=0.40, W_T_PROC=0.60, W_STORAGE_CPU=0.60, W_T_DB=0.40 |
| CO1–CO3 | `rq3_v2_cpu_{1,2,3}` | `cpu_only` | `rq3_v2_cpu_only.env` | W_CPU=1.00, W_T_PROC=0.00, W_STORAGE_CPU=1.00, W_T_DB=0.00 |
| LO1–LO3 | `rq3_v2_lat_{1,2,3}` | `latency_only` | `rq3_v2_latency_only.env` | W_CPU=0.00, W_T_PROC=1.00, W_STORAGE_CPU=0.00, W_T_DB=1.00 |

All other parameters (`CLIENTS`, `WAN_RTT_MS`, `STORAGE_CPUS`, `EDGE_CPUS`,
`CURL_MAX_TIME`, `RANDOM_SEED`, `DATA_SEED`, `PHASES_CONFIG=testing/phases.json`)
identical across all 9 runs. Only the four weight variables differ.

**Between every run**: cleanup + VM reboot.

**Total wall-clock estimate**: 9 × (24 min run + 5 min cleanup/reboot) ≈
**4.4 hours**.

### 10.1 Env Override Files

Three files under `source/scripts/testing/controller_env_overrides/`, all
derived from the same base configuration (floors, spans, thresholds, cooldowns
— all identical). Only the four weight variables differ:

**`rq3_v2_degradation_score.env`** (canonical composite):
```
# Base configuration (identical across all three files)
SCALEUP_CPU_FLOOR=<TBD>
SCALEUP_CPU_SPAN=<TBD>
SCALEUP_T_PROC_FLOOR=<TBD>
SCALEUP_T_PROC_SPAN=<TBD>
SCALEUP_COMPUTE_BASE_THRESHOLD=<TBD>
SCALEUP_COMPUTE_THRESHOLD_INCREMENT=0.10
SCALEUP_COMPUTE_MAX_THRESHOLD=0.85
SCALEUP_WINDOW_SIZE=5
SCALEUP_REQUIRED=3
SCALEUP_COMPUTE_COOLDOWN_S=45
SCALEUP_COMPUTE_PEER_RELIEF=0.03
SCALEUP_COMPUTE_PEER_HEALTH_THRESHOLD=0.35
SCALEUP_STORAGE_CPU_FLOOR=<TBD>
SCALEUP_STORAGE_CPU_SPAN=<TBD>
SCALEUP_T_DB_FLOOR=<TBD>
SCALEUP_T_DB_SPAN=<TBD>
SCALEUP_STORAGE_BASE_THRESHOLD=<TBD>
SCALEUP_STORAGE_THRESHOLD_INCREMENT=0.10
SCALEUP_STORAGE_MAX_THRESHOLD=0.55
SCALEUP_STORAGE_WINDOW_SIZE=5
SCALEUP_STORAGE_REQUIRED=2
SCALEUP_STORAGE_COOLDOWN_S=120
SCALEDOWN_COMPUTE_COOLDOWN_S=180
SCALE_DOWN_COMPUTE_REQUIRED=9
SCALE_DOWN_COMPUTE_WINDOW_SIZE=12
SCALEDOWN_STORAGE_COOLDOWN_S=120
SCALE_DOWN_STORAGE_WINDOW_SIZE=12
SCALE_DOWN_STORAGE_REQUIRED=7
TELEMETRY_TIMEOUT_WINDOWS=18
NODE_BIRTH_GRACE_S=60
STORAGE_PERSISTENT_RESERVE_ENABLED=1
SS_ENABLED=1
MAX_DYNAMIC_STORAGE=8
MAX_DYNAMIC_COMPUTE=12
VIP_HARD_TIMEOUT=60

# Weights — degradation_score (cross-signal confirmation)
SCALEUP_W_CPU=0.40
SCALEUP_W_T_PROC=0.60
SCALEUP_W_STORAGE_CPU=0.60
SCALEUP_W_T_DB=0.40
```

**`rq3_v2_cpu_only.env`**: Same base, only weights differ:
```
SCALEUP_W_CPU=1.00
SCALEUP_W_T_PROC=0.00
SCALEUP_W_STORAGE_CPU=1.00
SCALEUP_W_T_DB=0.00
```

**`rq3_v2_latency_only.env`**: Same base, only weights differ:
```
SCALEUP_W_CPU=0.00
SCALEUP_W_T_PROC=1.00
SCALEUP_W_STORAGE_CPU=0.00
SCALEUP_W_T_DB=1.00
```

---

## 11. Measurements (M1–M7 + G8 Diagnostic)

See [`rq3_v2.md` §5](rq3_v2.md#5-how-it-is-measured) for full metric
definitions and the causal measurement chain.

### 11.1 Detection Quality — M1–M4

| M | Metric | Graph | Primary artifact | Operational definition |
|---|--------|-------|-----------------|----------------------|
| M1 | Baseline FP Spawns | G1, G1b | `elasticity_events.csv` + controller log | Count of score-triggered spawns during `baseline` phase. Reserve spawns (persistent storage mechanism, identifiable by `standby_storage: spawning reserve` in controller log) excluded. |
| M2 | Stress Spawn Count | G2 | `elasticity_events.csv` | Score-triggered spawns per stress phase (storage_storm, tier1_hotspot, reverse_hotspot, compute_spike), per mode. |
| M3 | Time-to-First-Spawn (TTFS) | G3 | `elasticity_events.csv` + `phases_snapshot.json` | `first_spawn_start_ts − phase_start_ts`, per stress phase, per mode. |
| M4 | Missed Detections | (narrative) | Derived from M2 + per-phase CPU/latency from `per_node_stats.csv` | Stress phases where mean per-node CPU and p95 latency exceed threshold yet < 1 spawn occurred. Accounts for adaptive threshold escalation. |

### 11.2 Service Quality — M5–M7

| M | Metric | Graph | Primary artifact | Operational definition |
|---|--------|-------|-----------------|----------------------|
| M5 | Per-Phase Latency | G4, G5, G5b | `client_requests.csv` via `metrics_stats.py` | p50/p95/p99 latency per phase per mode. Disaggregated by phase type for G5b. |
| M6 | Timeout Rate | G6 | `client_requests.csv` | Per-phase timeout rate (latency ≥ 29.9 s). |
| M7 | Throughput | G7 | `client_requests.csv` | Completed requests per stress phase, per mode. |

### 11.3 Diagnostic

| ID | Metric | Graph | Primary artifact | Operational definition |
|----|--------|-------|-----------------|----------------------|
| D1 | Score Component Decomposition | G8 | `per_node_stats.csv` replayed through `breach_detector.py` | Per-window CPU and latency components, per mode. Median replicate by total spawn count. Horizontal dashed line at threshold. Shaded stress phases. |

### 11.4 Sanity Checks

| ID | Check | Artifact | Expectation |
|----|-------|----------|-------------|
| S1 | Weights applied | `controller_env_snapshot.env` | Weight variables match mode label (0.40/0.60, 1.00/0.00, or 0.00/1.00) |
| S2 | Identical non-weight parameters | `controller_env_snapshot.env` across all 9 runs | Floors, spans, thresholds, cooldowns, window counts identical across all modes |
| S3 | Push mode active | `controller_env_snapshot.env` | `TELEMETRY_SOURCE` not set to `poll` (defaults to push) |
| S4 | Warm-lease routing active | `controller_env_snapshot.env` | `BACKEND_SELECTION_POLICY=topology_lifecycle` |
| S5 | Mean-only latency signal | Controller log | Confirmation that `compute_latency_signal` and `storage_latency_signal` use mean-only |
| S6 | Scale-ups occurred | `elasticity_events.csv` | ≥ 2 unique `spawn_done` events per run |
| S7 | Spawn count consistent within mode | `elasticity_events.csv` | IQR of spawn count within mode < 50% of mode median |
| S8 | Reserve spawns excluded from M1 | Controller log | M1 counts only `scale-up:` spawns, not `standby_storage: spawning reserve` |

---

## 12. Validity Gates

| Gate | Trigger | Check | Source |
|------|---------|-------|--------|
| **CP-1** | Before ANY run | All three RQ3 v2 env override files exist and differ ONLY in the four weight variables. Non-weight parameters match across all three files. | `rq3_v2_degradation_score.env`, `rq3_v2_cpu_only.env`, `rq3_v2_latency_only.env` |
| **CP0** | After `rq3_v2_ds_1` | ≥ 2 unique spawn_done events? Mean-only latency signal confirmed in controller log? Push mode active? | `elasticity_events.csv`, controller log, `controller_env_snapshot.env` |
| **CP1** | After first mode's 3 reps | Baseline FP spawns and stress spawn counts consistent across replicates? (IQR < 50% of median for both) | `elasticity_events.csv` |
| **CP2** | After second mode's 3 reps | Do baseline FP spawns differ visibly between modes? (C3 — baseline FP separation) | Qualitative — full dataset needed for conclusion |
| **CP3** | End of campaign | Weights confirmed for all 9 `controller_env_snapshot.env` files. Non-weight parameters identical across all 9 files. | Cross-check all 9 snapshots |
| **CP4** | End of campaign | Pre-scale→post-scale improvement confirmed at selected resource config (C8 — scaling prerequisite) | `per_node_stats.csv` — pre-scale vs post-scale CPU and latency per stress phase |
| **S6** | Per run | Scale-ups occurred (≥ 2 per run) | `elasticity_events.csv` |
| **S7** | Per mode | Spawn count IQR < 50% of median within mode | `elasticity_events.csv` |
