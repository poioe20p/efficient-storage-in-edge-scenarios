# RQ2 v5 — Experiment Setup Declaration

> **Canonical reference** for how RQ2 v5 was tested. Values extracted from
> `experiment_plan_v5.md`, `phases_rq2.json`, `current_state_integrated.env`,
> `rq2_topology_*.env`, and `scaling_config.py`.
> **Corresponding RQ doc**: [`rq2_v5.md`](rq2_v5.md)
> **Predecessor**: [`rq2_setup_v3.md`](rq2_setup_v3.md)
>
> **v5 is a full re-run** with corrected architecture. 9 new runs (3 modes × 3
> replicates). Setup values are identical to v3 config but the underlying
> scoring architecture has been corrected (CPU_SPAN=40, CPU_FLOOR=10,
> W_STORAGE_CPU=0), env override files have been aligned to
> `current_state_integrated.env`, and the MAC-reuse extraction fix is
> applied in `extract_spawn_metrics.py`.

---

## 1. Phases — `phases_rq2.json`

Identical to v3. 9 phases, 1740 s total (~29 min). Two-cycle scale-up workout
with all-local traffic (cross_region_ratio=0.0) to isolate routing mechanism
from cross-region effects.

| # | Phase | Duration | Rate/client | Cross-region | Client frac | Dominant mix |
|---|-------|----------|-------------|--------------|-------------|-------------|
| 1 | `baseline` | 60 s | 1.0 | 0% | 50% | 60% lookup, 25% ranking, 15% pressure |
| 2 | `storage_storm` | 240 s | 4.0 | 0% | 100% | 35% lookup, 30% update, 20% aggregate |
| 3 | `cooldown_1` | 180 s | 1.0 | 0% | 10% | baseline mix |
| 4 | `compute_spike` | 180 s | 4.0 | 0% | 100% | 100% service_pressure |
| 5 | `cooldown_2` | 180 s | 1.0 | 0% | 10% | baseline mix |
| 6 | `storage_storm_2` | 240 s | 4.0 | 0% | 100% | Same as storage_storm |
| 7 | `cooldown_3` | 180 s | 1.0 | 0% | 10% | baseline mix |
| 8 | `compute_spike_2` | 180 s | 4.0 | 0% | 100% | 100% service_pressure |
| 9 | `demand_drop` | 300 s | 1.0 | 0% | 10% | baseline mix |

Same rationale as v3: all-local isolates routing from WAN effects; two-cycle
design doubles spawn events per run; 100% service_pressure guarantees compute
spawns even with corrected scoring (CPU_SPAN=40); no tier1_hotspot or
reverse_hotspot (Tier 1 disabled for RQ2).

---

## 2. Resource Limits

Corrected architecture (identical launch params to v3):

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `CLIENTS` | 96 (48/LAN) | RQ1 v7 golden — sufficient to drive spawns at rate=4.0 |
| `MAX_DYNAMIC_COMPUTE` | 12 | RQ1 v7 golden |
| `MAX_DYNAMIC_STORAGE` | 8 | RQ1 v7 golden |
| `STORAGE_CPUS` | 0.08 | RQ1 v7 golden — tight enough to create CPU pressure |
| `STORAGE_MEMORY` | 512m | Default |
| `EDGE_CPUS` | 0.30 | Default — drives compute spawns |
| `EDGE_MEMORY` | 256m | Default |
| `CURL_MAX_TIME` | 30 s | RQ1 v7 golden |
| `WAN_RTT_MS` | 185 ms | RQ1 v7 golden |
| `RANDOM_SEED` | 42 | Fixed — deterministic client behavior |
| `DATA_SEED` | 42 | Deterministic content/user data seeding across runs |

---

## 3. Controller Scoring — Compute Scale-Up

Corrected scoring (same values as v3's env, now validated by RQ1 v4). Source: `current_state_integrated.env` / `rq2_topology_*.env`.

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `SCALEUP_W_CPU` | 0.60 | CPU-weighted for compute stress |
| `SCALEUP_W_T_PROC` | 0.40 | Latency is secondary |
| `SCALEUP_CPU_FLOOR` | 10 | Only detect meaningful CPU elevation |
| `SCALEUP_CPU_SPAN` | 40 | **Critical** — prevents score saturation. Corrected from 5 (RQ1 v4 validated this fix) |
| `SCALEUP_T_PROC_FLOOR` | 25 ms | Slightly elevated |
| `SCALEUP_COMPUTE_BASE_THRESHOLD` | 0.18 | Compensates for wider span |
| `SCALEUP_COMPUTE_THRESHOLD_INCREMENT` | 0.10 | Default |
| `SCALEUP_COMPUTE_MAX_THRESHOLD` | 0.85 | Default |
| `SCALEUP_WINDOW_SIZE` | 5 | Default |
| `SCALEUP_REQUIRED` | 3 | Default |
| `SCALEUP_COMPUTE_COOLDOWN_S` | 45 s | Default |

---

## 4. Controller Scoring — Storage Scale-Up

Corrected scoring (latency-only; same as v3 env).

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `SCALEUP_W_STORAGE_CPU` | 0 | CPU excluded — I/O-wait, not a scaling signal |
| `SCALEUP_W_T_DB` | 1.0 | Latency-only |
| `SCALEUP_STORAGE_CPU_FLOOR` | 1.5 | Lowered for tight CPU limits |
| `SCALEUP_STORAGE_CPU_SPAN` | 5 | Narrower for constrained range |
| `SCALEUP_T_DB_FLOOR` | 60 ms | Lowered — latency elevates earlier at 0.08 CPUs |
| `SCALEUP_T_DB_SPAN` | 250 ms | Narrower |
| `SCALEUP_STORAGE_BASE_THRESHOLD` | 0.35 | RQ3-validated |
| `SCALEUP_STORAGE_WINDOW_SIZE` | 5 | Default |
| `SCALEUP_STORAGE_REQUIRED` | 2 | Default |
| `SCALEUP_STORAGE_COOLDOWN_S` | 120 s | Default |

---

## 5. Scale-Down

Identical to v3.

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `SCALEDOWN_COMPUTE_COOLDOWN_S` | 180 s | Keeps nodes alive through phase transitions |
| `SCALE_DOWN_COMPUTE_REQUIRED` | 9 | Stronger evidence of sustained low load |
| `SCALE_DOWN_COMPUTE_WINDOW_SIZE` | 12 | Default |
| `SCALEDOWN_STORAGE_COOLDOWN_S` | 120 s | Default |
| `TELEMETRY_TIMEOUT_WINDOWS` | 18 | Default |
| `NODE_BIRTH_GRACE_S` | 60 s | Default |

---

## 6. VIP Routing

Identical to v3.

### 6.1 Backend Selection Policy (Independent Variable)

| Mode | Unknown stats default | Warm lease | Ramp |
|---|---|---|---|
| `topology_host` | 0.0 (best-case) | Skipped | None — round-robin |
| `topology_slowstart` | 0.0 (neutral) + penalty 1.0 | Skipped | Graduated: penalty 1.0→0.0 over 45 s |
| `topology_lifecycle` | 1.0 (worst-case, bypassed) | Created at spawn, `max(started_ts)` | Warm lease priority window (45 s) |

> **Note**: v4 tested replacing `max(started_ts)` with round-robin in
> `_claim_warm_backend()`. The change did not affect median TTFT (20.9 s
> both ways). v5 keeps the original `max(started_ts)` policy. See
> [`v4/results.md`](../../operation/testing/experiment/rq2_evaluation/v4/results.md).

### 6.2 WSM Weights

| Parameter | Value |
|-----------|-------|
| `W_CPU` | 0.3 |
| `W_RAM` | 0.1 |
| `W_REQUESTS` | 0.2 |
| `W_HOPS` | 0.28 |
| `CROSS_NETWORK_HOP_PENALTY` | 3 |

### 6.3 Flow Timeouts

| Parameter | Value |
|-----------|-------|
| `VIP_IDLE_TIMEOUT` | 30 s |
| `VIP_HARD_TIMEOUT` | 60 s |

---

## 7. Telemetry Aggregation

Identical to v3.

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Aggregation window | 10 s | Default |
| Delivery mode | **Push** (ZMQ, window-close) | Held constant — isolates routing from telemetry cadence |

---

## 8. Topology & Seeds

Identical to v3 plus `DATA_SEED=42`:

| Parameter | Value |
|-----------|-------|
| `RANDOM_SEED` | 42 |
| `DATA_SEED` | **42** — **new in v5** |
| `CONTENT_ITEMS` | 6000 |
| Topology | 2 LANs, 1 NAT router, OVS bridges |
| Static backends/LAN | 1 edge_server, 1 edge_storage_server, 1 aggregator |
| Tier 1 selective sync | **Disabled** (`SS_ENABLED=0`) |
| Persistent reserve | Enabled (`STORAGE_PERSISTENT_RESERVE_ENABLED=1`) |
| Warm-lease TTLs | Server 45 s, Storage 30 s |
| cross_region_ratio | 0.0 (all phases) |

---

## 9. Docker Images

Identical to v3. No rebuild needed. `EDGE_MAX_CONCURRENT` semaphore not
enabled for RQ2.

---

## 10. Run Matrix

3 modes × 3 replicates = **9 new runs**. Run order: Host×3 → Slowstart×3 → Lifecycle×3.
~5.5 hours total.

| # | Label | BACKEND_SELECTION_POLICY | Env Override |
|---|-------|--------------------------|-------------|
| TH1–TH3 | `rq2_v5_th_{1,2,3}` | `topology_host` | `rq2_topology_host.env` |
| SS1–SS3 | `rq2_v5_ss_{1,2,3}` | `topology_slowstart` | `rq2_topology_slowstart.env` |
| TL1–TL3 | `rq2_v5_tl_{1,2,3}` | `topology_lifecycle` | `rq2_topology_lifecycle.env` |

---

## 11. Measurements

All metric definitions identical to v3 (§11 of `rq2_setup_v3.md`). The only
change: TTFT (M1) and derived metrics use the corrected extraction.

### Extraction Fix

`extract_spawn_metrics.py`, `compute_ttft()`:

```diff
- first-window-ever per MAC (bug: Docker MAC reuse → stale match)
+ first-window-after-spawn per MAC (correct: window_end >= spawn_ts)
```

The fix is already deployed. Extraction runs after each v5 run completes — see [`experiment_plan_v5.md`](../../operation/testing/experiment/rq2_evaluation/v5/experiment_plan_v5.md) §5.2.

---

## 12. What Changed from v3

| Change | v3 | v5 | Why |
|--------|----|----|-----|
| `DATA_SEED` | Not set | 42 | Deterministic content seeding across runs |
| `compute_ttft()` | first-window-ever per MAC | first-window-after-spawn per MAC | Fixes Docker MAC-reuse inflation (Slowstart: −20.6 s, Lifecycle: −9.7 s) |
| Warm-lease policy | `max(started_ts)` | `max(started_ts)` (unchanged) | v4 round-robin was tested and did not help |
| All other config | — | Identical | No reason to change — v3 config is correct for RQ2 |
