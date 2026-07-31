# RQ3 v6 — Experiment Setup Declaration

> **Canonical reference** for how RQ3 v6 is configured. All values are
> **final** — locked by the v5 divergence calibration
> ([`calibration_results_v2.md`](../../operation/testing/experiment/rq3_evaluation/v5/calibration_results_v2.md)).
> No TBDs remain.
>
> **Corresponding RQ doc**: [`rq3_v6.md`](rq3_v6.md)
> **Implementation**: [`experiment_plan_v6.md`](../../operation/testing/experiment/rq3_evaluation/v6/experiment_plan_v6.md)
> **Supersedes**: [`rq3_setup_v2.md`](rq3_setup_v2.md) (v2 — TBD markers, 0.60/0.40 storage weights)
> **Status**: ✅ Final — ready for evaluation

---

## 1. Phases — `phases_rq1_7phase.json`

**File**: `source/scripts/testing/phases_override/phases_rq1_7phase.json`

7 phases, 1,440 s total (~24 min). Tier 1 selective-sync enabled
(`SS_ENABLED=1`) — exercises storage, Tier 1, and compute stress in a
single run, giving all three trigger modes a rich detection surface.

| # | Phase | Duration | Rate/client | Cross-region | Client frac | Dominant mix |
|---|-------|----------|-------------|--------------|-------------|-------------|
| 1 | `baseline` | 60 s | 1.0 | 0% | 50% | 60% lookup, 25% ranking, 15% pressure |
| 2 | `storage_storm` | 240 s | 4.0 | 90% | 100% | 35% lookup, 30% update, 20% aggregate, 10% ranking, 5% pressure |
| 3 | `tier1_hotspot` | 180 s | 5.0 | 95% | 100% | 80% lookup — Tier 1 selective-sync stress |
| 4 | `inter_hotspot_cooldown` | 300 s | 1.0 | 0% | 10% | baseline mix — drain before reverse hotspot |
| 5 | `reverse_hotspot` | 180 s | 5.0 | 95% | 100% | 80% lookup — hotspot direction reversed |
| 6 | `compute_spike` | 180 s | 4.0 | 5% | 100% | 65% feed_ranking, 20% lookup, 15% pressure — compute-bound |
| 7 | `demand_drop` | 300 s | 1.0 | 0% | 10% | baseline mix — extended drain for scale-down |

> **compute_spike mix correction**: The actual JSON uses `{content_lookup:
> 0.20, feed_ranking: 0.65, service_pressure: 0.15}` — not 100%
> service_pressure as earlier docs stated. Feed_ranking is CPU-intensive
> (ranking computation). The 5% cross-region ratio keeps storage I/O minimal.
> The calibration's D3 divergence check used this exact mix and produced
> clear three-way separation (cpu_only 0.454 > degradation_score 0.295 >
> latency_only 0.066).

### Rationale for key design choices

| Choice | Why |
|--------|-----|
| `phases_rq1_7phase.json` (not canonical phases.json) | The canonical 9-phase file has cleanup gaps and no compute_spike — designed for RQ1's detection-speed isolation. RQ3 needs compute_spike for pure compute-tier isolation and no cleanup gaps (nodes may persist across phases). |
| 90% cross-region in `storage_storm` | Saturates WAN links, stresses storage tier cross-LAN routing — produces T_db elevation that all three trigger modes must detect. |
| 95% cross-region in hotspot phases | Triggers Tier 1 selective sync. G0-v6 validated at 40% cross-region: T_db 209–292 ms in tier1_hotspot, 221–838 ms in reverse_hotspot. At 95% (this configuration), T_db elevation is expected higher — these are lower bounds. |
| 65% feed_ranking in `compute_spike` | Isolates compute-bound stress — CPU-intensive ranking with minimal storage I/O (5% cross-region). Realistic workload, not an artificial benchmark. At 0.25 CPUs with 96 clients, CPU pre→post drop is 23–28pp (G0-v6 validated). |
| 300 s `inter_hotspot_cooldown` | Drain between hotspot directions. Longer than cleanup gaps because hotspot phases need more drain time. |
| 300 s `demand_drop` | Extended final drain — allows observation of full scale-down sequence. |
| No cleanup gaps between phases | Unlike RQ1 (which needs gaps to isolate detection speed), RQ3 evaluates detection *composition* — nodes may persist across phases, and that's acceptable. Phase transitions exercise cooldown mechanisms identically for all three modes. |

### Phase-type grouping (for G5b — Latency by Phase Type)

| Group | Phases | Dominant latency factor |
|---|---|---|
| **Baseline** | baseline | Routing quality — only phase guaranteed to start quiescent |
| **Storage stress** | storage_storm, tier1_hotspot, reverse_hotspot | Storage I/O (content_update, content_aggregate, cross-region MongoDB reads) |
| **Compute stress** | compute_spike | CPU saturation (feed_ranking, service_pressure) |
| **Post-stress** | inter_hotspot_cooldown, demand_drop | Mixed — residual effects from preceding stress phase |

---

## 2. Resource Limits — Definitive

All values confirmed by G0-v6 validation and divergence calibration.

| Parameter | Value | Source | Rationale |
|-----------|-------|--------|-----------|
| `CLIENTS` | 48 (per LAN, 96 total) | RQ1 v8 golden | Matches RQ1/RQ2 client count for cross-RQ comparability. The Makefile variable `CLIENTS` is per-LAN; the launch commands pass `CLIENTS=48`, producing 96 clients total (48 on LAN1 + 48 on LAN2). |
| `MAX_DYNAMIC_COMPUTE` | 12 | RQ1 v8 golden | Gives all modes room to demonstrate spawn count differences |
| `MAX_DYNAMIC_STORAGE` | 8 | RQ1 v8 golden | G0-v6 peaked at 7; cap is adequate |
| `STORAGE_CPUS` | 0.08 | G0-v6 validated | Tight enough for CPU pressure; loose enough that CPU isn't pure I/O-wait |
| `STORAGE_MEMORY` | 512m | Default | |
| `EDGE_CPUS` | 0.25 | G0-v6 validated | Produces clear compute pre→post improvement (23–28pp) |
| `EDGE_MEMORY` | 256m | Default | |
| `CURL_MAX_TIME` | 30 s | RQ1 v8 golden | Hard timeout for client HTTP requests |
| `WAN_RTT_MS` | 185 ms | G0-v6 validated | One-way ~92 ms; reduced from 260 ms to lower I/O-wait dominance |
| `RANDOM_SEED` | 42 | Fixed | Deterministic traffic patterns |
| `DATA_SEED` | 42 | Fixed | Deterministic test data |
| `DEVICES` | 6000 | Default | Synthetic device pool |
| `NODES` | 100 | Default | Synthetic content nodes |

---

## 3. Controller Scoring — Compute Scale-Up

**Independent variable**: the four weight variables (`SCALEUP_W_CPU`,
`SCALEUP_W_T_PROC`, `SCALEUP_W_STORAGE_CPU`, `SCALEUP_W_T_DB`). All
other parameters are **identical across all three modes**.

### 3.1 Weights — Independent Variable (Per-Mode)

Three env override files, differing only in the four weight variables:

| Variable | `degradation_score` | `cpu_only` | `latency_only` |
|----------|---------------------|------------|----------------|
| `SCALEUP_W_CPU` | 0.40 | 1.00 | 0.00 |
| `SCALEUP_W_T_PROC` | 0.60 | 0.00 | 1.00 |
| `SCALEUP_W_STORAGE_CPU` | **0.20** | 1.00 | 0.00 |
| `SCALEUP_W_T_DB` | **0.80** | 0.00 | 1.00 |

> **Storage weight calibration**: Originally proposed as 0.60/0.40 (v2).
> Divergence calibration found that at 0.08 CPUs, storage CPU at 0.60
> dominated T_db (24 spawns, indistinguishable from cpu_only). A storage
> CPU weight probe tested 0.20: 18 spawns — between cpu_only (22–24) and
> latency_only (15–17). CPU carries a real secondary signal (−21.8pp
> pre→post) without dominating T_db.

### 3.2 Scoring Parameters — Definitive

All values confirmed by G0-v6 validation and divergence calibration.
No TBDs — these are the final values. Weights are in §3.1; these tables
cover floors, spans, thresholds, and windowing/cooldown parameters.

> **Source note**: The base floors, spans, and thresholds originate from
> `current_state_integrated.env` (G0-v6 validated). The weights in
> `current_state_integrated.env` (W_CPU=0.60, W_T_PROC=0.40,
> W_STORAGE_CPU=0) are NOT the experiment values — those are supplied
> by the per-mode env override files. This section covers only the
> parameters that are identical across all three modes.

**Compute scoring:**

| Parameter | Value | Role |
|-----------|-------|------|
| `SCALEUP_CPU_FLOOR` | 10 | Below-floor CPU → zero CPU component. Above baseline noise, below stress saturation. |
| `SCALEUP_CPU_SPAN` | 40 | Wide span prevents score saturation at moderate CPU. Critical for `cpu_only` — if too narrow, saturates immediately; if too wide, never crosses. |
| `SCALEUP_T_PROC_FLOOR` | 25 ms | Above healthy edge latency (~5–15 ms), below stress latency. |
| `SCALEUP_T_PROC_SPAN` | 80 | Code default. |
| `SCALEUP_COMPUTE_BASE_THRESHOLD` | 0.18 | Lowered: wide span compresses scores; threshold compensates. Above baseline scores, below stress scores. |
| `SCALEUP_COMPUTE_THRESHOLD_INCREMENT` | 0.10 | Adaptive escalation per existing dynamic node. |
| `SCALEUP_COMPUTE_MAX_THRESHOLD` | 0.85 | Ceiling for adaptive threshold (code default). |
| `SCALEUP_WINDOW_SIZE` | 5 | Telemetry windows evaluated. |
| `SCALEUP_REQUIRED` | 3 | 3 of 5 must breach. Prevents single-window spikes. |
| `SCALEUP_COMPUTE_COOLDOWN_S` | 45 | Grace period after each spawn. |
| `SCALEUP_COMPUTE_PEER_RELIEF` | 0.03 | Score reduction per peer node (code default — not in env override files). |
| `SCALEUP_COMPUTE_PEER_HEALTH_THRESHOLD` | 0.35 | Peer considered healthy below this (code default). |

**Storage scoring:**

| Parameter | Value | Role |
|-----------|-------|------|
| `SCALEUP_STORAGE_CPU_FLOOR` | 1.5 | Matches tight CPU limits. Storage CPU at 0.08 CPUs is typically 1–5% at baseline. |
| `SCALEUP_STORAGE_CPU_SPAN` | 5 | Narrow span for constrained CPU range. |
| `SCALEUP_T_DB_FLOOR` | 60 ms | Storage latency elevates earlier at 0.08 CPUs than at default. |
| `SCALEUP_T_DB_SPAN` | 250 ms | Narrower T_db range at this CPU level. |
| `SCALEUP_STORAGE_BASE_THRESHOLD` | 0.35 | G0-v6 validated — storage scoring loop closes at τ=0.35. |
| `SCALEUP_STORAGE_THRESHOLD_INCREMENT` | 0.10 | Adaptive escalation. |
| `SCALEUP_STORAGE_MAX_THRESHOLD` | 0.55 | Ceiling. |
| `SCALEUP_STORAGE_WINDOW_SIZE` | 5 | Default. |
| `SCALEUP_STORAGE_REQUIRED` | 2 | 2 of 5 must breach (faster than compute's 3/5). |
| `SCALEUP_STORAGE_COOLDOWN_S` | 120 | Default. |

---

## 4. Controller Scoring — Storage Scale-Up

### 4.1 Weights

Same pattern as compute: weights vary, everything else identical.

| Variable | `degradation_score` | `cpu_only` | `latency_only` |
|----------|---------------------|------------|----------------|
| `SCALEUP_W_STORAGE_CPU` | **0.20** | 1.00 | 0.00 |
| `SCALEUP_W_T_DB` | **0.80** | 0.00 | 1.00 |

> The v2 proposal of 0.60/0.40 was superseded by calibration. At 0.08 CPUs,
> storage CPU is a real but weak signal (−21.8pp pre→post from 37.4% to
> 15.6%). At 0.60 weight it dominated T_db; at 0.20 it contributes as a
> secondary signal while T_db (0.80) remains the primary driver.

---

## 5. Scale-Down — Definitive

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `SCALEDOWN_COMPUTE_COOLDOWN_S` | 180 s | **Raised** — keeps nodes alive through phase transitions. Complements the absence of cleanup gaps (unlike RQ1, RQ3 allows nodes to persist across phases). |
| `SCALE_DOWN_COMPUTE_REQUIRED` | 9 | Raised — requires stronger evidence of sustained low load. |
| `SCALE_DOWN_COMPUTE_WINDOW_SIZE` | 12 | Default. |
| `SCALE_DOWN_STORAGE_WINDOW_SIZE` | 12 | Default. |
| `SCALE_DOWN_STORAGE_REQUIRED` | 7 | Default. |
| `SCALEDOWN_STORAGE_COOLDOWN_S` | 120 s | Default. |
| `TELEMETRY_TIMEOUT_WINDOWS` | 18 | ~180 s without telemetry → node marked dead. |
| `NODE_BIRTH_GRACE_S` | 60 s | Skip dead-node detection for first 60 s after spawn. |

---

## 6. VIP Routing — Held Constant

RQ2's domain. Warm-lease routing (`topology_lifecycle`) eliminates the LB
discovery gap so trigger composition is the only variable.

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `BACKEND_SELECTION_POLICY` | `topology_lifecycle` | **Fixed** — warm lease at spawn time. |
| `VIP_IDLE_TIMEOUT` | 30 s | Default. |
| `VIP_HARD_TIMEOUT` | 60 s | Halved from default 120 s — forces flow re-evaluation sooner. |
| `W_CPU` (server WSM) | 0.3 | CPU-weighted routing. |
| `W_RAM` | 0.1 | From `osken-controller.env`. |
| `W_REQUESTS` | 0.2 | Default. |
| `W_HOPS` | 0.28 | Default. |
| `CROSS_NETWORK_HOP_PENALTY` | 3 | Additive penalty for cross-LAN backends. |

---

## 7. Telemetry Aggregation — Held Constant

RQ1's domain. Push-mode delivery (ZMQ at window close) eliminates the
monitoring blind spot so trigger composition is the only variable.

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Aggregation window (`WINDOW_S`) | 10 s | Default — 10 s summaries. |
| Delivery mode | **Push** (ZMQ, window-close) | Held constant — RQ1's optimal delivery. |
| Latency signal | **Mean-only** (`avg_time_proc_ms`, `avg_time_db_ms`) | Avoids timeout-censored p95 contamination. Consistent with autoscaling literature (all 16 reviewed papers use mean/rate/ratio for triggers). |

### 7.1 Latency Signal: Mean-Only Rationale

Both tiers use **mean-only** latency signals:

| Tier | Signal | Source |
|------|--------|--------|
| **Compute** | `ds.avg_time_proc_ms` | `scaling_policy.py:compute_latency_signal()` |
| **Storage** | `ds.avg_time_db_ms` | `scaling_policy.py:storage_latency_signal()` |

p95 remains collected in telemetry for SLO monitoring and post-hoc analysis
but is excluded from the degradation score. When a significant fraction of
requests hit the 30 s client timeout, p95 measures the timeout ceiling
(30,001 ms), not the system's actual performance.

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
| Tier 1 selective sync | **Enabled** (`SS_ENABLED=1`) | Fixed — exercises Tier 1 pool. |
| Persistent reserve | **Enabled** (`STORAGE_PERSISTENT_RESERVE_ENABLED=1`) | Reserve spawns excluded from M1 (baseline FP) counts. |
| Warm-lease TTLs | Server 45 s, Storage 30 s | `scaling_config.py` defaults. |

---

## 9. Docker Images

| Image | Notes |
|-------|-------|
| `edge_server` | Must include mean-only latency signal in `scaling_policy.py`. |
| `edge_storage_server` | Unchanged. |
| `edge_selective_storage` | Used (`SS_ENABLED=1`). |
| `osken-controller` | Must include mean-only latency signal code change (§7.1). |
| `local_state_server` | Unchanged. |
| `ovs-container` | Unchanged. |
| `ubuntu-nat-router` | Unchanged. |

---

## 10. Run Matrix

3 modes × 3 replicates = 9 runs.

| # | Label | Trigger Mode | Env Override File | Compute W | Storage W |
|---|-------|-------------|-------------------|-----------|-----------|
| DS1–DS3 | `rq3_v6_ds_{1,2,3}` | `degradation_score` | `rq3_v2_degradation_score.env` | 0.40/0.60 | 0.20/0.80 |
| CO1–CO3 | `rq3_v6_cpu_{1,2,3}` | `cpu_only` | `rq3_v2_cpu_only.env` | 1.00/0.00 | 1.00/0.00 |
| LO1–LO3 | `rq3_v6_lat_{1,2,3}` | `latency_only` | `rq3_v2_latency_only.env` | 0.00/1.00 | 0.00/1.00 |

All other parameters (`CLIENTS=96`, `WAN_RTT_MS=185`, `STORAGE_CPUS=0.08`,
`EDGE_CPUS=0.25`, `CURL_MAX_TIME=30`, `RANDOM_SEED=42`, `DATA_SEED=42`,
`PHASES_CONFIG=testing/phases_override/phases_rq1_7phase.json`) identical
across all 9 runs.

**Between every run**: cleanup + VM reboot. **Total**: ~4.4 hours.

### 10.1 Env Override Files

Three files under `source/scripts/testing/controller_env_overrides/`, all
derived from the same base configuration. Only the four weight variables differ.

The files are named `rq3_v2_*.env` (v2 = RQ doc version, not experiment
version). For full file contents, see the files directly:

- [`rq3_v2_degradation_score.env`](../../../source/scripts/testing/controller_env_overrides/rq3_v2_degradation_score.env)
- [`rq3_v2_cpu_only.env`](../../../source/scripts/testing/controller_env_overrides/rq3_v2_cpu_only.env)
- [`rq3_v2_latency_only.env`](../../../source/scripts/testing/controller_env_overrides/rq3_v2_latency_only.env)

---

## References

- [RQ3 v6 — Trigger Composition Characterization](rq3_v6.md) — measurement framework, M1–M7, G1–G8, C1–C8
- [Experiment Plan v6](../../operation/testing/experiment/rq3_evaluation/v6/experiment_plan_v6.md) — implementation details, launch commands, artifact contract
- [Theory Predictions v6](rq3_theory_prediction_v6.md) — formalised predictions
- [Divergence Calibration Results](../../operation/testing/experiment/rq3_evaluation/v5/calibration_results_v2.md) — 8-run calibration
