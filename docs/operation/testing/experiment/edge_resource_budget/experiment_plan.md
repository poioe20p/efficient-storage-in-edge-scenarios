# Edge Resource Budget -- Calibrating a Valid Edge-Scale Configuration

**Status**: 🔵 Calibrating · **Date**: 2026-07-29
**Mode**: degradation_score only (round-robin VIP routing, default)
**Independent of**: RQ1/RQ2/RQ3 -- standalone calibration experiment

---

## 1. Objective

Find a degradation_score configuration that exercises the full elasticity lifecycle (scale-up + scale-down) under realistic edge resource caps, and produces acceptable service quality.

## 2. Valid Config Criteria

A configuration is **valid** when ALL nine criteria hold across >=2 of 3 replicates:

### Infrastructure Gates

| # | Criterion | Measurement | Threshold | Source |
|---|-----------|------------|-----------|--------|
| V1 | Scale-up exercised | Spawn count | >=2 spawns per LAN | `controller_lan*.log` |
| V2 | Scale-down exercised | SD ARMED count | >=5 per LAN | `controller_lan*.log` |
| V3 | Final node count | Dynamic nodes in `demand_drop` phase | <=3 dynamic per LAN | `per_node_stats.csv` (excl static MACs 02/04/05/06 + real HW) |

### Mechanism Gates

| # | Criterion | Measurement | Threshold | Source |
|---|-----------|------------|-----------|--------|
| V6 | Tier-1 selective sync exercised | `selective_storage` node additions | >=1 across both LANs | `elasticity_events.csv` |

### Service Quality Gates

| # | Criterion | Measurement | Threshold | Source |
|---|-----------|------------|-----------|--------|
| V4 | Acceptable latency | p50 across all phases | <=500ms | `client_requests.csv` |
| V10 | Acceptable tail latency | p95 across all phases | <=10000ms | `client_requests.csv` |
| V11 | Acceptable mean latency | Mean latency_s across all phases | <=4000ms | `client_requests.csv` |
| V5 | CPU utilization | Mean cpu_percent across all nodes, all phases | >=25% | `per_node_stats.csv` |
| V9 | No excessive timeouts | Fraction of requests with `latency_s >= 29.9` (curl --max-time 30) | <=15% | `client_requests.csv` |

### Scale-Up Benefit Gates (elasticity must help)

| # | Criterion | Measurement | Threshold | Source |
|---|-----------|------------|-----------|--------|
| V7 | Compute scale-up reduces CPU | For at least 1 compute spawn: mean cpu_percent of compute nodes drops >=15% within 3 telemetry windows (30s) post-spawn vs pre-spawn | >=1 spawn with >=15% CPU drop | `per_node_stats.csv` + `elasticity_events.csv` |
| V8 | Storage scale-up reduces latency | For at least 1 storage spawn: p50 latency_s drops >=20% within 3 telemetry windows (30s) post-spawn vs pre-spawn | >=1 spawn with >=20% p50 drop | `client_requests.csv` + `elasticity_events.csv` |

### Measurement details

**V7 (compute CPU benefit)**: For each compute `node_spawning` event in `elasticity_events.csv`, map the spawn timestamp to the nearest `window_end` in `per_node_stats.csv` (10s windows). Filter compute nodes (`role=compute`). Compute mean `cpu_percent` across all compute nodes in the 3 windows before vs 3 windows after (skipping the window containing the spawn). The post-spawn mean must be >=15% lower than pre-spawn for at least one spawn event.

**V8 (storage latency benefit)**: For each storage `node_spawning` event, map the spawn timestamp to the nearest `window_end`. Bucket `client_requests.csv` by 10s windows using `sent_at` timestamps. Compute p50 of `latency_s` for requests in the 3 windows before vs 3 windows after. At least one spawn must show >=20% p50 improvement.

**V6 (Tier-1)**: Count `node_type=selective_storage` events in `elasticity_events.csv`. At least 1 such node must be spawned during the run (indicating the controller detected Tier-1 hotspot conditions and spun up a selective-sync node).

## 3. Configuration Axes (tunable)

### Caps (edge scarcity)

| Parameter | Starting | Range |
|---|---|---|
| MAX_DYNAMIC_STORAGE | 3 | 2-4 |
| MAX_DYNAMIC_COMPUTE | 2 | 1-3 |

### Phases (stress/drain)

| Phase | Starting | Tunable |
|---|---|---|
| storage_storm | 180s @ 4 req/s | 120-240s, 2-6 req/s |
| tier1_hotspot | 180s @ 5 req/s | 120-240s, 3-8 req/s |
| reverse_hotspot | 180s @ 5 req/s | 120-240s, 3-8 req/s |
| compute_spike | 180s @ 4 req/s | 120-240s, 2-6 req/s |
| demand_drop | 300s @ 1 req/s | 240-480s, 0.5-2 req/s |
| cross_region_ratio (stress) | 0.90-0.95 | 0.5-1.0 |

### Scale Gates (starting: relaxed, caps are the real limiter)

| Parameter | Starting | Range |
|---|---|---|
| Storage up | 3/5, 0.25tau, 120s | 2-4/5, 0.15-0.35tau, 60-180s |
| Storage down | 3/4, 400ms, 40s | 2-4/4-6, 250-600ms, 30-90s |
| Compute up | 3/5, 0.25tau, 90s | 2-4/5, 0.15-0.35tau, 60-180s |
| Compute down | 3/4, 25%/50ms, 30s | 2-4/4-6, 20-40%/30-100ms, 30-90s |

## 4. Calibration Protocol

1. Start with baseline config (caps + phases + gates above)
2. Run DS calibration run
3. Check V1-V9
4. If ALL pass: run 2 more replicates -> validated
5. If ANY fail: adjust the relevant axis, goto 2

### Expected failure -> fix

| Symptom | Likely fix |
|---|---|
| V1 (no spawns) | Lower scale-up thresholds, increase stress rate/duration, or increase caps |
| V2 (no SD) | Lower scale-down window/required, reduce cooldown, raise TAU_DB_DOWN |
| V3 (too many nodes) | Increase demand_drop, lower scale-down gates |
| V4 (high latency) or V9 (high timeouts) | Increase caps, reduce stress intensity, lower scale-up thresholds so nodes spawn faster |
| V5 (low CPU) | Reduce caps (fewer nodes = higher per-node CPU) |
| V6 (no Tier-1) | Increase cross_region_ratio in tier1_hotspot, increase hotspot duration |
| V7 (no compute benefit) | Increase compute_spike rate/duration to create genuine CPU pressure before spawn |
| V8 (no storage benefit) | Increase storage_storm cross_region_ratio, increase rate, ensure T_db pressure |

## 5. Run Matrix

| Phase | Labels | Purpose |
|---|---|---|
| Calibration | `edge_budget_cal_N` | Find valid config, N=1.. |
| Validation | `edge_budget_val_1`..`_3` | Replicates of valid config |

## 6. Launch Command

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n STORAGE_CPUS=0.08 EDGE_CPUS=0.25 WAN_RTT_MS=185 RANDOM_SEED=42 \
    make -C source/scripts setup_network create_clients setup_test_data run_experiment \
    OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/edge_budget_degradation_score.env \
    RUN_LABEL=<LABEL> \
    PHASES_CONFIG=testing/phases_override/phases_edge_budget.json \
    CLIENTS=48 CONTENT_ITEMS=6000 USERS=100 \
    DATA_SEED=42 CURL_MAX_TIME=30 \
    SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1 \
    > /tmp/<LABEL>.log 2>&1 &"
```

## 7. Per-Run Validation Script

```python
# Quick validation check after each run
# V1: spawns >= 2 per LAN
spawn_lan1 = grep -c 'scale-up.*triggered' controller_lan1.log
spawn_lan2 = grep -c 'scale-up.*triggered' controller_lan2.log

# V2: SD >= 5 per LAN
sd_lan1 = grep -c 'scale-down.*ARMED' controller_lan1.log
sd_lan2 = grep -c 'scale-down.*ARMED' controller_lan2.log

# V3: dynamic nodes in demand_drop (excl static 02/04/05/06 and real HW)
# V4: p50 from client_requests.csv
# V5: mean cpu_percent from per_node_stats.csv
```

## 8. References

- [RQ3 v7 experiment plan](../rq3_evaluation/v7/experiment_plan_v7.md)
- [node_registry.py](../../../../../../source/sdn_controller/node_registry.py) -- reserve-floor decoupling
- [traffic_generator.py](../../../../../../source/scripts/testing/traffic_generator.py)

## 9. Pre-Flight

- [x] node_registry.py reserve-floor decoupling deployed
- [x] edge_budget_degradation_score.env created (MAX_STORAGE=3, MAX_COMPUTE=2)
- [x] phases_edge_budget.json created (1320s)
- [ ] Synced to cloud VM
- [ ] Calibration run 1 launched
