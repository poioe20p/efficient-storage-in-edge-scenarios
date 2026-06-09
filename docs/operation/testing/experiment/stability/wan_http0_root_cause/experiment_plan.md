# Experiment Plan — WAN HTTP-0 Root-Cause Isolation

**Status**: ✅ COMPLETE — R2 confirms fix (0.05% failure). System stable at CLIENTS=8.
**Updated**: 2026-06-09.

## Intent

Eliminate LAN-asymmetric HTTP-0 failures in v5.6 runs (2.2% → 21.3%, with
LAN-flip). Hypothesis: nat-router cross-LAN veth pairs overflow their default
TX queue (1000 packets) under 8-client bursty load, causing tail-drop.

### Per-direction testing: not needed

The `phases.json` workload already alternates hotspot directions
(`cross_region_hotspot`: LAN1-hot, `reverse_hotspot`: LAN2-hot). The
bottleneck is symmetric — eth1↔eth2 is one software bridge, same capacity
both ways. Both LANs failed in v5.6 Run B. Separate per-direction runs would
triple time without adding value.

## Hypothesis

| # | Hypothesis | Test | Evidence |
|---|-----------|------|----------|
| H1 | **Cross-LAN veth TX queue overflow** — default `txqueuelen=1000` drops under 8-client load | CLIENTS=4 (halves throughput) | ✅ Confirmed: 0.02% failure |
| H1b | **Targeted fix** — `txqueuelen=10000` on eth1/eth2 + veth3/veth23 | CLIENTS=8 + txqueuelen fix | 🔄 Pending |

### Ruled out

| Hypothesis | Why |
|-----------|-----|
| WAN veth (veth5↔eth0) queue | Truncated run with veth5 fix: still 33% failure in `cross_region_hotspot` |
| WAN latency (10 ms RTT) | CLIENTS=4 had full WAN latency and 0.02% failure |
| netfilter conntrack overflow | Max 38 entries — nowhere near 65536 default |
| VIP routing / SDN controller | Conntrack fix validated v5.6; zero epoch rotations |

## RQ Linkage

Platform-infrastructure prerequisite for RQ2 (backend selection) and RQ3
(locality strategy), which require stable cross-LAN connectivity under load.

## Independent Variable & Held-Constant Set

| Run | Independent variable | Changed how |
|-----|---------------------|-------------|
| R1 | Request rate (throughput) | `CLIENTS=4` |
| R2 | Cross-LAN veth TX queue depth | `txqueuelen 10000` on veth3/eth1 + veth23/eth2 |

**Held constant**: `phases.json` workload, `current_state_integrated.env`
controller config, `DEVICES=600 NODES=100`, `WAN_RTT_MS=10`, same Docker
images, same host/VM, no `--fault-plan`.

## Prerequisites

All satisfied — no blocked runs.

| Prereq | Status |
|--------|--------|
| `CLIENTS` knob in Makefile | ✅ |
| `txqueuelen` in `build_network_1.sh` (lines 91, 191) | ✅ Implemented & synced |
| `txqueuelen` in `build_network_2.sh` (lines 89, 189) | ✅ Implemented & synced |
| `build_router.sh` clean (no veth5 txqueuelen) | ✅ User reverted |

### Files changed for R2

| File | Line | Change |
|------|------|--------|
| `source/scripts/network/build_network_1.sh` | 91 | `docker exec ovs ip link set veth3 txqueuelen 10000` |
| `source/scripts/network/build_network_1.sh` | 191 | `nsenter ... ip link set eth1 txqueuelen 10000` |
| `source/scripts/network/build_network_2.sh` | 89 | `docker exec ovs ip link set veth23 txqueuelen 10000` |
| `source/scripts/network/build_network_2.sh` | 189 | `nsenter ... ip link set eth2 txqueuelen 10000` |

These four interfaces carry all cross-LAN HTTP traffic. Each gets 10× queue
depth on both sides of the veth pair.

## Run Matrix

| # | Run label | Variable | Phase file | Expected |
|---|-----------|----------|------------|----------|
| R1 | `wan_diag_low_tput` | CLIENTS=4 | `testing/phases.json` | ✅ ≤1% (achieved: 0.02%) |
| R2 | `wan_diag_txqueuelen_v2` | txqueuelen 10000 on cross-LAN veths | `testing/phases.json` | ≤2% failure, zero LAN-flip |

**Run order**: R1 → R2. R1 complete. R2 pending — verification that the
correct interfaces were the chokepoint.

## Run Configuration

### R1 — Low Throughput ✅ COMPLETE

```bash
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  RUN_LABEL=wan_diag_low_tput \
  PHASES_CONFIG=testing/phases.json \
  CLIENTS=4 DEVICES=600 NODES=100 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
```

Run folder: `source/scripts/testing/metrics/20260608_205101_wan_diag_low_tput/`
Result: **0.02% failure** (13/70,625). Full analysis in `run_summary.md`.

### R2 — Cross-LAN TX Queue Fix 🔄 PENDING

```bash
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  RUN_LABEL=wan_diag_txqueuelen_v2 \
  PHASES_CONFIG=testing/phases.json \
  CLIENTS=8 DEVICES=600 NODES=100 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
```

The `setup_network` step applies the txqueuelen commands from the modified
`build_network_1.sh` and `build_network_2.sh`. No extra env vars needed.

## Focus & Evidence

**Primary focus**: `client_requests.csv` per-phase, per-LAN failure rates.
LAN asymmetry (LAN1 vs LAN2 split) is THE signal.

**Secondary**: Controller logs for storage eval lines (elevated to INFO),
mechanism exercise (compute/storage/Tier-1 elasticity under full load).

| Artifact | Shows |
|---|---|
| `client_requests.csv` | Per-phase, per-LAN, per-endpoint HTTP status |
| `resource_stats.csv` | `server_count`, `storage_count`, conntrack entries |
| `container_events.csv` | Compute/storage add/remove ground truth |
| `elasticity_events.csv` | Scale-up/down timing |
| `controller_lan1.log`, `controller_lan2.log` | Storage eval lines (INFO), VIP warnings, scale alerts |

## Metrics & Success Criteria

### R2 pass/fail

| Metric | Threshold | Rationale |
|--------|-----------|-----------|
| Overall failure rate | ≤2.0% | Down from 2.2–21.3% (v5.6); matches conntrack ≤3% target |
| `reverse_hotspot` failure | ≤3.0% | v5.6 B: 35.0%; R1: 0.0% |
| `compute_ramp`/`spike`/`plateau` failure | ≤3.0% | v5.6 B: 44–55%; R1: 0.0–0.1% |
| LAN-flip (one dead, other perfect) | Absent | LAN1/LAN2 failure within 3× |
| Storage scale-down eval lines | ≥1 | Confirms elevated INFO logs fire under full load |
| Compute elasticity | ≥1 ComputeAlert/LAN | Confirms full-load exercise |

### Cross-run comparison

| # | Metric | v5.6 A (8/LAN) | v5.6 B (8/LAN) | R1 (4/LAN) | R2 target (8/LAN+fix) |
|---|--------|---------------|---------------|------------|----------------------|
| M1 | Overall | 2.2% | 21.3% | 0.02% | ≤2.0% |
| M2 | `reverse_hotspot` | 7.8% | 35.0% | 0.0% | ≤3.0% |
| M3 | `compute_spike` | 1.6% | 54.9% | 0.0% | ≤3.0% |
| M4 | LAN asymmetry | 0.0%/6.7% | 10.9%/32.0% | 0.03%/0.01% | ≤3× ratio |
| M5 | Storage eval lines | 0 (DEBUG) | 0 (DEBUG) | 0 (no dyn storage) | ≥1 (INFO) |

## Checkpoints

During R2, the runner may observe:

| Trigger | Question | Action |
|---------|----------|--------|
| `cross_region_hotspot` starts | Are HTTP-0 failures absent? | Check `tail -f client_requests.csv` for non-200 statuses |
| LAN-flip suspected | Are both LANs alive? | Compare LAN1 vs LAN2 last_status in traffic generator output |
| `compute_ramp` starts | Do failures appear or stay at zero? | Note first HTTP-0 timestamp vs first ComputeAlert |

**Report only** — do not modify the experiment mid-run.

## Changelog

| Date | Change | Rationale |
|------|--------|-----------|
| 2026-06-08 | Initial 4-run plan across H1/H2/H3 | Diagnostic experiment design |
| 2026-06-09 | R1 completed — H1 confirmed (0.02%) | Throughput saturation at nat-router |
| 2026-06-09 | Truncated veth5 test: still 33% failure | Ruled out WAN veth as bottleneck |
| 2026-06-09 | **Plan simplified to 2 runs** — dropped R0, old R2, R3 | Evidence narrowed cause to cross-LAN veth TX queues |
| 2026-06-09 | Added R2: CLIENTS=8 + txqueuelen on eth1/eth2/veth3/veth23 | Verification run for the correct chokepoint |
| 2026-06-09 | **R2 completed — fix confirmed (0.05% failure)** | Cross-LAN veth TX queue depth was the chokepoint. 426× improvement over v5.6 B. System stable at CLIENTS=8. See `results.md` §2. |

## Validity Threats & Limitations

- **Single replicate**: R2 is one run. Variance is possible (v5.6 A vs B showed
  10× spread). A borderline result (3–8%) warrants a replicate.
- **txqueuelen may not be enough**: If the bottleneck is at a different layer
  (OVS datapath, kernel softirq, iptables rule processing), the fix won't help.
  The truncated veth5 test (still 33% failure) already showed the WAN veth
  isn't the issue; this test isolates the cross-LAN veths.
- **Storage eval logs may still not fire**: Even under CLIENTS=8, if the
  `is_busy()` gate blocks scale-down evaluation due to pending compute drains,
  the elevated INFO lines won't appear. This is a separate concern from the
  HTTP-0 fix.

## Artifact Contract

Standard run-folder layout per `docs/operation/testing/testing_overview.md`:

```
source/scripts/testing/metrics/<timestamp>_<run_label>/
├── client_requests.csv
├── resource_stats.csv
├── resource_stats_debug.csv
├── per_node_stats.csv
├── container_events.csv
├── elasticity_events.csv
├── node_lifecycle_timings.csv
├── policy_state.csv
├── controller_lan1.log
├── controller_lan2.log
├── current_phase.txt
├── phases_snapshot.json
└── service_logs/
```

Analysis outputs: `run_summary.md` per run folder.
