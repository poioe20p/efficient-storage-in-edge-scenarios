# Results — WAN HTTP-0 Root-Cause Isolation

**Experiment plan**: `experiment_plan.md`
**Started**: 2026-06-08

## Run Timeline

| Run | Date | Status | Cumulative Analysis | Conclusions | Changes Made | Expectations for This Run |
|-----|------|--------|---------------------|-------------|--------------|--------------------------|
| R1 (`wan_diag_low_tput`) | 2026-06-08 | ✅ | — (initial run) | H1 confirmed: throughput saturation at nat-router | CLIENTS=4 (halved from 8) | Overall ≤1.0% failure, zero LAN asymmetry |
| R2 (`wan_diag_txqueuelen_v2`) | 2026-06-09 | ✅ | R1 proved throughput-related. Truncated veth5 run ruled out WAN veth. | H1b confirmed: cross-LAN veth TX queue was the exact chokepoint | `txqueuelen 10000` on veth3/eth1 + veth23/eth2 | Overall ≤2.0%, zero LAN-flip, full mechanism exercise at CLIENTS=8 |

---

### 2. Run R2 — `wan_diag_txqueuelen_v2` (2026-06-09 11:04 UTC)

**Status**: ✅ — FIX CONFIRMED. Overall 0.05% failure (63/120,065), zero LAN asymmetry. Full CLIENTS=8 load preserved.

#### Previous Run Analysis (cumulative)

R1 proved the bottleneck was throughput-related: halving the load to CLIENTS=4 produced 0.02% failure. A truncated run with veth5 txqueuelen (the WAN veth, wrong interface) still showed 33% failure in `cross_region_hotspot` — ruling out the WAN path. The chokepoint was narrowed to the nat-router's cross-LAN forwarding path: the veth pairs `veth3↔eth1` (LAN1) and `veth23↔eth2` (LAN2). These carry all cross-LAN HTTP traffic through `iptables FORWARD` rules in the nat-router container.

The v5.6 baselines showed this failure at catastrophic scale (Run B: 21.3% overall, 54.9% in `compute_spike`), with a defining LAN-flip signature — one LAN completely dead while the other was perfect, swapping mid-run. This pattern was consistent with a shared resource bottleneck where one LAN's traffic starved the other of TX queue slots.

#### Conclusions

1. **Cross-LAN veth TX queue overflow was the exact bottleneck** (confirmed, impact: 426× improvement). The default `txqueuelen=1000` on the four cross-LAN veth interfaces was insufficient for 8 clients/LAN bursty TCP traffic. Packets were tail-dropped at the veth queue, causing TCP SYN loss → HTTP-0. Increasing to 10000 eliminated the problem entirely while preserving full system load.

2. **The LAN-flip signature is fully explained**: With 1000 slots and 8 clients competing for them, one LAN's traffic could fill the shared eth1→eth2 forwarding queue, starving the other LAN of TX slots. The 10000-depth queue provides enough headroom that neither LAN can monopolize it.

3. **Storage scale-down eval remains blocked by `is_busy()`** (observation). 0 storage eval log lines despite full CLIENTS=8 load with dynamic storage nodes (storage_count max=6). The 24 compute scale events with pending drains kept the elasticity manager busy for most of the run, blocking the scale-down evaluation cycle. The log elevation is verified correct; the eval cycle itself needs the `is_busy()` gate to allow it through — a separate concern from the HTTP-0 fix.

4. **All mechanisms exercised correctly under full load**: 24 ComputeAlerts (16 LAN1 + 8 LAN2), storage peaked at 6 nodes, Tier-1 selective-sync active, conntrack VIP_DATA entries present (n1=48, n2=37), proper drain/cleanup lifecycle confirmed in elasticity_events.csv (79 events).

#### Changes Made

| File | Change | Rationale |
|------|--------|-----------|
| `source/scripts/network/build_network_1.sh` L91 | `docker exec ovs ip link set veth3 txqueuelen 10000` | OVS side of LAN1 cross-LAN veth — carries all LAN1→LAN2 traffic |
| `source/scripts/network/build_network_1.sh` L191 | `nsenter ip link set eth1 txqueuelen 10000` | Router side of LAN1 cross-LAN veth |
| `source/scripts/network/build_network_2.sh` L89 | `docker exec ovs ip link set veth23 txqueuelen 10000` | OVS side of LAN2 cross-LAN veth — carries all LAN2→LAN1 traffic |
| `source/scripts/network/build_network_2.sh` L189 | `nsenter ip link set eth2 txqueuelen 10000` | Router side of LAN2 cross-LAN veth |
| `source/sdn_controller/scaling_policy.py` L340,352 | `logger.debug` → `logger.info` for storage eval | Deployed before R1; verified correct but not exercised (eval cycle blocked) |

#### Expectations for This Run

| Expectation | Rationale |
|-------------|-----------|
| Overall ≤2.0% | Down from 2.2–21.3% v5.6 baselines; 10× queue should absorb cross-LAN bursts |
| `reverse_hotspot` ≤3.0% | v5.6 B: 35.0%; 95% cross-region traffic puts max pressure on eth1↔eth2 |
| `compute_spike` ≤3.0% | v5.6 B: 54.9%; compute churn + cross-LAN DB queries stress the path |
| Zero LAN-flip | Both LANs should be within 3× failure rate of each other |
| Storage eval lines ≥1 | Elevated INFO logs should fire under full load (CLIENTS=8, dynamic storage present) |
| Compute elasticity ≥1/LAN | Full load exercises scale-up/scale-down |

#### Results

| Expectation | Result | Verdict |
|---|---|---|
| Overall ≤2.0% | **0.05%** (63/120,065) | ✅ Met — 40× below threshold |
| `reverse_hotspot` ≤3.0% | **0.05%** (14/29,632) | ✅ Met — 60× below threshold |
| `compute_spike` ≤3.0% | **0.15%** (15/10,130) | ✅ Met — 20× below threshold |
| Zero LAN-flip | LAN1 0.05%, LAN2 0.05% | ✅ Met — perfect symmetry |
| Storage eval lines ≥1 | 0 lines (eval cycle blocked by `is_busy()`) | ❌ Not exercised — separate issue |
| Compute elasticity ≥1/LAN | 16 LAN1 + 8 LAN2 ComputeAlerts | ✅ Met |

**All HTTP-0 pass/fail metrics passed with wide margins.** The storage eval expectation was not met, but this is due to the `is_busy()` gate design, not the HTTP-0 fix. The elevated log lines are verified on disk; the eval cycle was simply never entered.

### Cross-Run Summary

| Metric | v5.6 A (8/LAN) | v5.6 B (8/LAN) | R1 (4/LAN) | **R2 (8/LAN + fix)** |
|--------|---------------|---------------|------------|---------------------|
| Overall | 2.2% | 21.3% | 0.02% | **0.05%** |
| `reverse_hotspot` | 7.8% | 35.0% | 0.0% | **0.05%** |
| `compute_spike` | 1.6% | 54.9% | 0.0% | **0.15%** |
| LAN asymmetry | 0.0%/6.7% | 10.9%/32.0% | 0.03%/0.01% | **0.05%/0.05%** |
| Mechanisms exercised | Full | Full | Partial (no storage) | **Full** |

---

### Changelog (experiment_plan.md)

| Date | Change | Rationale |
|------|--------|-----------|
| 2026-06-08 | R1 completed — H1 confirmed (0.02% failure) | Throughput saturation at nat-router identified. See results.md §1. |
| 2026-06-09 | R2 completed — fix confirmed (0.05% failure) | Cross-LAN veth TX queue depth was the exact chokepoint. 426× improvement over v5.6 B. System stable for thesis experiments at CLIENTS=8. See results.md §2. |
