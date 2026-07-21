# Calibration v2 — LAN2 Symmetry Fix

**Date**: 2026-07-06
**Parent**: [`calibration_plan.md`](./calibration_plan.md) · [`experiment_plan.md`](./experiment_plan.md)

---

## Problem

Calibration v1 found that `topology_host` mode causes severe LAN2 degradation:

| Clients | LAN1 Fail | LAN2 Fail | Overall |
|---|---|---|---|
| 16 (C5) | 0.6% | 12.3% | 5.0% |
| 24 (C4) | 6.8% | 87.9% | 65% |
| 32 (C3) | 3.3% | 89.3% | 58% |
| 48 (C2) | — | — | 58% |

Root cause: `topology_host` herds all traffic to one backend (unknown stats → cost=0.0). The connection burst overflows the Flask dev server's TCP listen queue (`somaxconn` default = 128). Kernel sends immediate RST for overflow connections — 2-5ms failures, no app or controller log entries.

`topology_lifecycle` distributes traffic → no burst → symmetric LANs (1.5%/1.4%).

---

## Fix

Add `--sysctl net.core.somaxconn=1024` to all edge server containers:

| File | Container(s) | Type |
|---|---|---|
| `source/scripts/network/build_network_1.sh` | `edge_server_n1` | Static |
| `source/scripts/network/build_network_2.sh` | `edge_server_n2` | Static |
| `source/sdn_controller/elasticity/compute_node_manager.py` | Dynamic `edge_server_lan*_dyn*` | Dynamic |

The fix is kernel-level — does not change routing behavior, WSM costs, or the RQ2 independent variable.

---

## Verification Runs

Test `topology_host` at the worst-affected client count (CLIENTS=24) where LAN2 was 87.9% failure pre-fix. Two runs to confirm repeatability.

| # | Label | Policy | CLIENTS | Purpose |
|---|---|---|---|---|
| V1 | `rq2_symfix_1` | topology_host | 24 | Verify LAN2 ≤5% |
| V2 | `rq2_symfix_2` | topology_host | 24 | Confirm repeatable |

If both pass, run one lifecycle run at CLIENTS=24 to confirm symmetry:
| V3 | `rq2_symfix_tl` | topology_lifecycle | 24 | Symmetry baseline |

---

## Success Criteria

| Check | Threshold |
|---|---|
| LAN2 failure rate | ≤5% |
| LAN1 failure rate | ≤5% |
| LAN symmetry | LAN2/LAN1 failure ratio ≤ 3× |
| Scale-up events | ≥8 total |
| No fd exhaustion | 0 "Too many open files" in edge server logs |

---

## Run Configuration

```bash
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/rq2_topology_host.env \
  RUN_LABEL=rq2_symfix_1 \
  PHASES_CONFIG=testing/phases_override/phases_rq2.json \
  WAN_RTT_MS=50 CLIENTS=24 CONTENT_ITEMS=6000 USERS=100 STORAGE_CPUS=0.10 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
```

Between-run protocol: cleanup → reboot → verify → launch.

---

## Go/No-Go

- ✅ Both V1/V2 pass → lock CLIENTS=24, proceed to full 9-run campaign
- ⚠️ One passes, one fails → run V3 tiebreaker, investigate variance
- ❌ Both fail → somaxconn not sufficient; investigate other causes (gunicorn, keep-alive, client staggering)
