# Experiment Plan — WAN HTTP-0 Root-Cause Isolation

**Status**: R1 complete — H1 CONFIRMED (2026-06-09). R2/R3 deprioritized per diagnostic decision table.

## Intent

Identify which layer — throughput capacity, WAN latency interaction, or
netfilter conntrack — causes the LAN-asymmetric HTTP-0 failures observed in
v5.6 runs (2.2% Run A → 21.3% Run B, with LAN-flip behavior). Each run
isolates one independent variable against an instrumented baseline.

## Hypothesis / Expected Outcome

The LAN-flip signature (one LAN completely dead while the other is perfect,
swapping mid-run, recovering cleanly in `demand_drop`) points to a **shared
WAN-path bottleneck** — the `nat-router` container. Three hypotheses are
tested, ordered by likelihood:

| # | Hypothesis | Test | If confirmed… |
|---|-----------|------|---------------|
| H1 | **Throughput saturation** — 8 clients/LAN exceeds nat-router forwarding capacity | Halve request rate (CLIENTS=4) | Failures vanish or drop below 1% |
| H2 | **WAN latency amplification** — 10 ms RTT interacts with compute-churn flow changes, causing TCP retransmit storms | Zero WAN latency (WAN_RTT_MS=0) | Failures vanish or drop below 1% |
| H3 | **netfilter conntrack overflow** — nat-router conntrack table fills, dropping new TCP SYNs | 4× `nf_conntrack_max` on nat-router | Failures vanish or drop significantly |

Expected: **H1 or H2** explains the variance; H3 is less likely given the
low total connection count (~600 devices × 2 connections each ≈ 1200
conntrack entries, well below the default 65536). H1 is the strongest
candidate — the LAN-flip shows one LAN starves the other of a shared
capacity pool.

## RQ Linkage

Not directly thesis-linked. This is a platform-infrastructure diagnostic.
Resolving it is a prerequisite for fair evaluation of RQ2 (backend selection)
and RQ3 (locality strategy), which require stable WAN connectivity.

## Independent Variable & Held-Constant Set

| Run | Independent variable | Changed how |
|-----|---------------------|-------------|
| R0 | Baseline (none) | Current `current_state_integrated.env`, full probe capture |
| R1 | Request rate | `CLIENTS=4` instead of `8` |
| R2 | WAN latency | `WAN_RTT_MS=0` in `wan.env` |
| R3 | Conntrack capacity | 4× `nf_conntrack_max` on nat-router **(BLOCKED — see §Prerequisites)** |

**Held constant** across all runs: `phases.json` workload, `current_state_integrated.env`
controller config, `DEVICES=600 NODES=100`, same Docker images, same host/VM,
no `--fault-plan`.

## Prerequisites

### ✅ Available now

- **R0**: Full probe capture via `capture_reverse_hotspot_probe.sh` (tcpdump,
  conntrack, OVS flow dumps) — already implemented.
- **R1**: `CLIENTS` knob in Makefile — already supported.
- **R2**: `wan.env` already controls `WAN_RTT_MS` — already supported.

### 🔴 BLOCKED — R3: nat-router conntrack max injection

The `nat-router` container has no mechanism to receive a custom
`nf_conntrack_max` value. Required changes before R3 can run:

1. **`source/docker/ubuntu-nat-router/Dockerfile`**: Install `conntrack` package
   (`apt-get install -y conntrack`) for monitoring. Rebuild image.
2. **`source/scripts/network/build_router.sh`**: After `ip link set eth0 up`,
   apply `sysctl -w net.netfilter.nf_conntrack_max=${NAT_CONNTRACK_MAX:-65536}`
   inside the router netns. Accept value from environment.
3. **`source/scripts/testing/controller_env_overrides/current_state_integrated.env`**:
   Add `NAT_CONNTRACK_MAX=262144` for the conntrack-capacity run.

**Without these changes, R3 cannot execute.** The plan documents the intent;
the runner should build the prerequisite before launching R3.

## Run Matrix

| # | Run label | Variable | Phase file | Prereq | Expected outcome |
|---|-----------|----------|------------|--------|-----------------|
| R0 | `wan_diag_baseline` | None (instrumented) | `testing/phases.json` | None | Captures failure signature with full diagnostics |
| R1 | `wan_diag_low_tput` | Request rate (CLIENTS=4) | `testing/phases.json` | None | If H1 correct: ≤1% failure |
| R2 | `wan_diag_zero_lat` | WAN latency (RTT=0) | `testing/phases.json` | Edit `wan.env` | If H2 correct: ≤1% failure |
| R3 | `wan_diag_big_conntrack` | Conntrack max (262144) | `testing/phases.json` | §Prerequisites | If H3 correct: ≤3% failure |

**Run order**: R0 → R1 → R2 → R3. R0 establishes the baseline signature.
R1 and R2 are independent — either order works. R3 requires the prerequisite
build, so it runs last. If R1 already confirms H1, R3 may be skipped.

## Run Configuration

### R0 — Instrumented Baseline

```bash
# Full probe capture during reverse_hotspot phase
# Step 1: Preflight
make -C source/scripts probe_capture_preflight \
  PROBE_CAPTURE_ROOT=/tmp/wan_diag_capture

# Step 2: Launch experiment + probe capture in parallel
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  RUN_LABEL=wan_diag_baseline \
  PHASES_CONFIG=testing/phases.json \
  CLIENTS=8 DEVICES=600 NODES=100 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1 &

# Launch probe capture once reverse_hotspot phase starts (or pre-launch at experiment start)
make -C source/scripts probe_capture_launch \
  PROBE_CAPTURE_RUN_DIR=source/scripts/testing/metrics/<timestamp>_wan_diag_baseline \
  PROBE_CAPTURE_ROOT=/tmp/wan_diag_capture
```

**Probe capture collects**: tcpdump on `veth5` (WAN host side), `conntrack -L`
on host, OVS flow dumps on `br-router` every N seconds during `reverse_hotspot`
and compute phases. See `capture_reverse_hotspot_probe.sh` for sampling controls.

### R1 — Low Throughput

```bash
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  RUN_LABEL=wan_diag_low_tput \
  PHASES_CONFIG=testing/phases.json \
  CLIENTS=4 DEVICES=600 NODES=100 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
```

### R2 — Zero WAN Latency

```bash
# Before run: edit source/scripts/wan.env, set WAN_RTT_MS=0
# setup_network reads wan.env → inject_wan_latency.sh applies tc netem

sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  RUN_LABEL=wan_diag_zero_lat \
  PHASES_CONFIG=testing/phases.json \
  CLIENTS=8 DEVICES=600 NODES=100 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
```

**Restore** `WAN_RTT_MS=10` in `wan.env` after this run.

### R3 — Conntrack Capacity (BLOCKED)

```bash
# After prerequisite build:
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  RUN_LABEL=wan_diag_big_conntrack \
  PHASES_CONFIG=testing/phases.json \
  CLIENTS=8 DEVICES=600 NODES=100 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
```

The env file must include `NAT_CONNTRACK_MAX=262144`. `build_router.sh` applies
the sysctl inside the nat-router netns during network setup.

## Focus & Evidence

**Primary focus** (all runs): `client_requests.csv` per-phase, per-LAN failure
rates via `phase_stats.py`. The LAN asymmetry (LAN1 vs LAN2 failure split) is
THE diagnostic signal.

**Secondary focus** (R0 only): Probe capture artifacts — tcpdump traces showing
where SYNs are dropped, conntrack table occupancy, OVS flow drop counters.

| Artifact | Shows |
|---|---|
| `client_requests.csv` | Per-phase, per-LAN, per-endpoint HTTP status — primary pass/fail |
| `controller_lan1.log`, `controller_lan2.log` | VIP server selection, IP resolution warnings, flow rule installation |
| `resource_stats.csv` | `server_count`, `storage_count` — confirms compute/storage churn occurred |
| `container_events.csv` | Compute add/remove timing — correlates with failure onset |
| `phases_snapshot.json` | Phase order, durations, request mix — confirms workload identity |
| Probe capture: `conntrack/tcp_*.txt` | NAT router conntrack table at sample points — shows occupancy |
| Probe capture: `flows/*.txt` | OVS flow dumps — shows drop counters, rule counts |
| Probe capture: `pcap/*.pcap` | tcpdump on veth5 — confirms where TCP SYNs are lost |

## Metrics & Success Criteria

### Per-run pass/fail

| Run | Primary metric | Pass threshold | Rationale |
|-----|---------------|----------------|-----------|
| R0 | Overall failure rate | — (baseline) | Captures current failure magnitude |
| R1 | Overall failure rate | ≤1.0% | H1: if throughput is the bottleneck, halving rate fixes it |
| R1 | LAN asymmetry (max/min LAN fail %) | ≤2× | Both LANs should be equally stable |
| R2 | Overall failure rate | ≤1.0% | H2: if WAN latency drives the failure, zero latency fixes it |
| R3 | Overall failure rate | ≤3.0% | H3: if conntrack is the bottleneck, expanding table fixes it |

### Cross-run comparison

| # | Metric | How evaluated |
|---|--------|---------------|
| M1 | Per-phase failure rate (all 10 phases) | `phase_stats.py` on each `client_requests.csv` |
| M2 | LAN1 vs LAN2 failure split | `client_requests.csv` grouped by `client_lan` |
| M3 | Failure-by-endpoint breakdown | `client_requests.csv` grouped by `endpoint` |
| M4 | Compute-churn vs quiet-phase failure contrast | Compare `compute_ramp`/`compute_spike`/`sustained_plateau` against `baseline`/`local_moderate`/`inter_hotspot_cooldown` |
| M5 | Failure temporal pattern (within-phase) | `client_requests.csv` sorted by `timestamp` — does failure cluster at phase boundaries? |
| M6 | NAT conntrack occupancy (R0, R3) | Probe capture conntrack files — count entries over time |
| M7 | OVS datapath drops (R0) | `ovs-appctl dpctl/show` in probe capture — any non-zero drop counters |

### Diagnostic Decision Table

| R1 result | R2 result | Conclusion |
|-----------|-----------|------------|
| ≤1% | ≤1% | Both throughput AND WAN latency contribute — bottleneck is throughput × latency interaction |
| ≤1% | ~20% | Pure throughput saturation — WAN latency is irrelevant |
| ~20% | ≤1% | WAN latency amplification — rate alone doesn't cause it, but WAN RTT does |
| ~20% | ~20% | Neither explains it → look at VIP flow churn / controller code (not WAN infrastructure) |

## Checkpoints

During R0 (instrumented baseline), the runner may observe:

| Trigger | Question | Action |
|---------|----------|--------|
| `reverse_hotspot` phase starts | Is conntrack table growing? | Check `wc -l /tmp/wan_diag_capture/conntrack/tcp_*.txt` |
| LAN-flip observed in `client_requests.csv` streaming | Which LAN died first? | Cross-reference with probe capture timestamps |
| `compute_ramp` starts | Do failures begin immediately or with lag? | Note timestamp of first HTTP-0 vs first compute scale-up log line |
| Any phase shows >50% failure | Is the nat-router still responsive? | `docker exec nat-router ping -c 3 192.168.100.1` |

**Report only** — the runner should not modify the experiment mid-run.

## Changelog

| Date | Change | Rationale |
|------|--------|-----------|
| 2026-06-08 | Initial experiment plan | Diagnostic experiment to isolate WAN HTTP-0 root cause across 3 hypotheses |
| 2026-06-09 | R1 completed — H1 confirmed (0.02% failure) | Throughput saturation at nat-router identified as root cause. R2/R3 deprioritized. See `results.md` §1. |

## Validity Threats & Limitations

- **Single replicate per run**: With the high variance seen in v5.6 (2.2% vs
  21.3%), a single replicate per condition may not be conclusive. If R1 or R2
  show borderline results (e.g., 3–8% instead of clear ≤1% or ~20%), run a
  replicate of that condition.
- **R3 (conntrack capacity) is blocked**: Until the prerequisite build is done,
  H3 cannot be tested. The other runs should be prioritized.
- **Probe capture may perturb results**: tcpdump and conntrack sampling add
  CPU load on the host. The effect is small but non-zero.
- **Observing R0 may change timing**: The probe capture runs during
  `reverse_hotspot` by design; its presence may affect the failure pattern.
  Compare R0's overall failure rate against the un-instrumented v5.6 runs
  to assess probe overhead.
- **WAN topology change for R2**: Setting `WAN_RTT_MS=0` removes tc netem
  qdiscs from the router interfaces. This changes the effective topology
  (same-LAN and cross-LAN become equivalent at the IP layer). This is
  intentional for the diagnostic but does not represent a realistic deployment.

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
    ├── edge_server_n1.log
    └── edge_server_n2.log
```

**R0 additionally** — probe capture under `/tmp/wan_diag_capture/`:
```
/tmp/wan_diag_capture/
├── conntrack/
│   └── tcp_<unix_ts>.txt
├── flows/
│   └── flows_<unix_ts>.txt
└── pcap/
    └── veth5_<unix_ts>.pcap
```

**Analysis outputs** (generated by analyst after all runs complete):
- `wan_diag_comparison.md` — cross-run comparison of M1–M7
- Updated `run_summary.md` per run folder
