# Experiment Plan v2-Lite — RQ1 at Reduced WAN Latency

**Status**: 🔵 Designed · **Date**: 2026-07-01
**Parent plan**: [`experiment_plan_v2.md`](./experiment_plan_v2.md) — all structural details there
**Motivation**: [`results_v2.md`](./results_v2.md) §2, Criterion 5

## Intent

Re-run each telemetry mode **at WAN=200ms** with `VIP_HARD_TIMEOUT=60s`
in two passes that isolate a different variable:

- **Pass 1** — all four modes (Push → Poll-5s → Poll-12s → Poll-30s) with the
  default `curl --max-time 10s`. Establishes the baseline failure rate and
  confirms the v2 blind-spot patterns hold at reduced WAN.
- **Pass 2** — same four modes with `curl --max-time` raised to **30s**.
  The independent variable is client patience. The question: does the higher
  client timeout (a) reduce the HTTP-0 failure rate, and (b) reveal the true
  uncensored cross-region latency distribution that the 10s timeout masks?

This is a **complementary confirmation plus a client-timeout sensitivity
check**, not a full experiment. It inherits the v2 plan's hypothesis, RQ
linkage, phases, and success criteria — only the WAN latency, client timeout,
and run order differ. A cloud-VM reboot between runs eliminates
memory-accumulation confounds.

## Hypothesis / Expected Outcome

Same as v2 §Hypothesis, with two refinements:

5. **Service quality degrades with polling interval, now measurable above
   a lower noise floor.** At WAN=200ms, the v6 calibration experiment
   measured ~7% baseline failure rate (vs ~29% at WAN=260ms). The blind-spot
   contribution (+3–5pp) should be distinguishable from run-to-run variance
   at this baseline.

6. **Raising `curl --max-time` from 10s to 30s reduces HTTP-0 failures and
   uncensors the latency distribution.** At WAN=200ms the v6 Tier 1 experiment
   established that `curl --max-time 10s` censors cross-region latency data:
   `avg_time_db_ms` reaches 5.9 s (Tier 1 ON) to 24.5 s (Tier 1 OFF) in
   `tier1_hotspot`, yet client-observed latency is hard-capped at exactly
   10.0 s. Requests exceeding 10 s are killed and counted as HTTP-0. Raising
   `curl --max-time` to 30 s should:
   - **Reduce Pass 1→Pass 2 failure rate** by 5–15 pp (slow requests complete
     instead of being killed)
   - **Reveal true latency** — the median and p95 shift upward in Pass 2
     because the distribution is no longer right-censored at 10 s
   - **Not affect controller-side mechanisms** — Tier 1 activation, storage
     scale-out, and compute scale-up trigger on CPU/DB-time/request-rate
     signals that are independent of whether the client counts the response
     as HTTP‑200 or HTTP‑0

## Reasoning — Why curl=30s + VIP=60s

This section summarises the evidence chain and is not repeated elsewhere.

### The censorship discovery (v6 mechanism_necessity T1–T10)

| Run | WAN | Tier 1 | VIP Timeout | tier1_hotspot Fail% | Data Quality |
|-----|-----|--------|-------------|---------------------|-------------|
| T1: 200ms ON | 200ms | ON | 30s | 11.7% | ✅ Valid |
| T2: 200ms OFF | 200ms | OFF | 30s | 12.1% | ✅ Valid |
| T6: 260ms OFF | 260ms | OFF | 30s | **52.3%** | ❌ Censored — median fake (2.3 s vs real 5.9 s) |
| T9: 260ms ON | 260ms | ON | **60s** | 10.0% | ✅ Gold standard |
| T10: 260ms OFF | 260ms | OFF | **60s** | 32.8% | ✅ Gold standard |

**Key insight**: At 200 ms WAN the 10 s `curl --max-time` is adequate (both ON
and OFF data are valid — T1/T2). But the v6 Tier 1 ON-vs-OFF experiment
showed that even at 200 ms, `avg_time_db_ms` in `tier1_hotspot` reaches
~3.4 s (ON) to ~3.2 s (OFF) — close to the 10 s cap under load. The v2-lite
workload (7 phases, CLIENTS=48) is **heavier** than the v6 workload (6 phases)
because it includes a `storage_hotspot` phase with higher write volume.
Without Tier 1 active (the default in v2-lite: `SS_ENABLED=1` but Tier 1 is
a separate mechanism), cross-region DB time can climb toward the 24.5 s peak
observed in v6 T10.

### Why not adjust VIP_HARD_TIMEOUT instead

- `VIP_HARD_TIMEOUT` controls the OVS flow-rule removal cadence — it governs
  backend re-selection, not request patience. Changing it alters per-server
  request distribution, which changes the CPU signal that elasticity
  mechanisms depend on. This conflates two variables.
- `curl --max-time` is the actual kill switch — it directly controls whether
  a slow request is counted as HTTP-200 or HTTP-0, without touching any
  controller-side mechanism.

### The ordering constraint: curl < VIP

`curl --max-time 30s` < `VIP_HARD_TIMEOUT 60s` — 2× headroom ensures the
flow-rule never expires while a request is in flight. If they were equal
(both 30 s), the OVS rule removal and the curl kill would collide at T+30 s,
producing unpredictable per-run behaviour.

## Independent Variable & Held-Constant Set

| Parameter | v2 Value | v2-Lite Pass 1 | v2-Lite Pass 2 | Reason |
|-----------|---------|----------------|----------------|--------|
| `WAN_RTT_MS` | 260 | **200** | **200** | Reduce baseline failure rate per v6 calibration |
| `curl --max-time` | 10s (hardcoded) | **10s** (default) | **30s** | **Independent variable** — tests client-timeout effect on failure rate |
| `VIP_HARD_TIMEOUT` | 60 | **60** | **60** | Held constant — v6 gold-standard value, 2× headroom above curl |
| Reboot between runs | No | **Yes** | **Yes** | Eliminate memory-accumulation confound |
| Everything else | — | Same as v2 | Same as v2 | Phases, CLIENTS=48, DEVICES=6000, NODES=100, STORAGE_CPUS=0.10, SS_ENABLED=1, etc. |

## Run Matrix

| # | Pass | Label | `TELEMETRY_SOURCE` | `POLL_INTERVAL_S` | `WAN_RTT_MS` | `CURL_MAX_TIME` |
|---|------|-------|-------------------|--------------------|--------------|-----------------|
| 1 | 1 | `rq1_v2lite_push_1` | `zmq` (default) | — | 200 | 10s (default) |
| 2 | 1 | `rq1_v2lite_poll5_1` | `poll` | 5 | 200 | 10s (default) |
| 3 | 1 | `rq1_v2lite_poll12_1` | `poll` | 12 | 200 | 10s (default) |
| 4 | 1 | `rq1_v2lite_poll30_1` | `poll` | 30 | 200 | 10s (default) |
| 5 | 2 | `rq1_v2lite_push_t30` | `zmq` (default) | — | 200 | **30s** |
| 6 | 2 | `rq1_v2lite_poll5_t30` | `poll` | 5 | 200 | **30s** |
| 7 | 2 | `rq1_v2lite_poll12_t30` | `poll` | 12 | 200 | **30s** |
| 8 | 2 | `rq1_v2lite_poll30_t30` | `poll` | 30 | 200 | **30s** |

**Total: 8 runs** (Pass 2 always executes — it is a treatment axis, not a replicate).
**Run order**: Pass 1 (Push → Poll-5s → Poll-12s → Poll-30s), then Pass 2 (same order).
**Campaign duration**: ~4 h (each run ~28 min with reboot).

## Run Configuration

### Prerequisites

All prerequisites from v2 §Prerequisites Summary remain in effect
(7-phase `phases.json`, `VIP_HARD_TIMEOUT=60`, TELEMETRY passthrough in
`build_network_setup.sh`). One new prerequisite:

- **`CURL_MAX_TIME` env var in `traffic_generator.py`** — the `curl --max-time`
  value must be read from the environment (`os.environ.get("CURL_MAX_TIME", "10")`)
  instead of the hardcoded string `"10"` at line 194. Without this change,
  Pass 2 runs will still use 10 s regardless of the `CURL_MAX_TIME=30` setting
  on the make command line. This change is **blocking** for Pass 2.

### Pass 1 — First Replicate (always executes)

#### Run 1 — Push

```bash
ssh -o ServerAliveInterval=60 cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=rq1_v2lite_push_1 \
  PHASES_CONFIG=testing/phases.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  WAN_RTT_MS=200 CLIENTS=48 DEVICES=6000 NODES=100 STORAGE_CPUS=0.10 \
  > /tmp/rq1_v2lite_push_1.log 2>&1 &"
```

#### Run 2 — Poll-5s

```bash
ssh -o ServerAliveInterval=60 cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=rq1_v2lite_poll5_1 \
  PHASES_CONFIG=testing/phases.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  WAN_RTT_MS=200 CLIENTS=48 DEVICES=6000 NODES=100 STORAGE_CPUS=0.10 \
  TELEMETRY_SOURCE=poll POLL_INTERVAL_S=5 \
  > /tmp/rq1_v2lite_poll5_1.log 2>&1 &"
```

#### Run 3 — Poll-12s

```bash
ssh -o ServerAliveInterval=60 cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=rq1_v2lite_poll12_1 \
  PHASES_CONFIG=testing/phases.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  WAN_RTT_MS=200 CLIENTS=48 DEVICES=6000 NODES=100 STORAGE_CPUS=0.10 \
  TELEMETRY_SOURCE=poll POLL_INTERVAL_S=12 \
  > /tmp/rq1_v2lite_poll12_1.log 2>&1 &"
```

#### Run 4 — Poll-30s

```bash
ssh -o ServerAliveInterval=60 cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=rq1_v2lite_poll30_1 \
  PHASES_CONFIG=testing/phases.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  WAN_RTT_MS=200 CLIENTS=48 DEVICES=6000 NODES=100 STORAGE_CPUS=0.10 \
  TELEMETRY_SOURCE=poll POLL_INTERVAL_S=30 \
  > /tmp/rq1_v2lite_poll30_1.log 2>&1 &"
```

### Pass 1 → Pass 2 Transition

Pass 1 and Pass 2 share the same WAN=200ms, VIP=60s, and telemetry modes.
The only change is `CURL_MAX_TIME`. Pass 2 always executes — it is **not
gated on Pass 1 results** because it tests a different independent variable
(client patience), not a replicate.

After Pass 1 post-run analysis is complete for all four modes:
1. Run the standard post-run workflow (chown, parse, 6 CLIs, delete logs).
2. Execute the reboot protocol.
3. Launch Pass 2 runs with `CURL_MAX_TIME=30`.

### Pass 2 — curl=30s Treatment (always executes)

#### Run 5 — Push (curl=30s)

```bash
ssh -o ServerAliveInterval=60 cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=rq1_v2lite_push_t30 \
  PHASES_CONFIG=testing/phases.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  WAN_RTT_MS=200 CLIENTS=48 DEVICES=6000 NODES=100 STORAGE_CPUS=0.10 \
  CURL_MAX_TIME=30 \
  > /tmp/rq1_v2lite_push_t30.log 2>&1 &"
```

#### Run 6 — Poll-5s (curl=30s)

```bash
ssh -o ServerAliveInterval=60 cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=rq1_v2lite_poll5_t30 \
  PHASES_CONFIG=testing/phases.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  WAN_RTT_MS=200 CLIENTS=48 DEVICES=6000 NODES=100 STORAGE_CPUS=0.10 \
  TELEMETRY_SOURCE=poll POLL_INTERVAL_S=5 \
  CURL_MAX_TIME=30 \
  > /tmp/rq1_v2lite_poll5_t30.log 2>&1 &"
```

#### Run 7 — Poll-12s (curl=30s)

```bash
ssh -o ServerAliveInterval=60 cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=rq1_v2lite_poll12_t30 \
  PHASES_CONFIG=testing/phases.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  WAN_RTT_MS=200 CLIENTS=48 DEVICES=6000 NODES=100 STORAGE_CPUS=0.10 \
  TELEMETRY_SOURCE=poll POLL_INTERVAL_S=12 \
  CURL_MAX_TIME=30 \
  > /tmp/rq1_v2lite_poll12_t30.log 2>&1 &"
```

#### Run 8 — Poll-30s (curl=30s)

```bash
ssh -o ServerAliveInterval=60 cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=rq1_v2lite_poll30_t30 \
  PHASES_CONFIG=testing/phases.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  WAN_RTT_MS=200 CLIENTS=48 DEVICES=6000 NODES=100 STORAGE_CPUS=0.10 \
  TELEMETRY_SOURCE=poll POLL_INTERVAL_S=30 \
  CURL_MAX_TIME=30 \
  > /tmp/rq1_v2lite_poll30_t30.log 2>&1 &"
```

### Between-Run Reboot Protocol

After each run's post-run analysis (chown, parse, 6 CLIs, delete logs):

```bash
# 1. Reboot the cloud VM to clear accumulated memory
ssh cloud-vm "sudo reboot"

# 2. Wait for VM to shut down and come back (~90s typical)
Start-Sleep -Seconds 90

# 3. Confirm SSH is responsive
ssh -o ConnectTimeout=10 -o ConnectionAttempts=10 cloud-vm "echo 'VM ready'"
```

**Rationale**: The v2 12-run campaign revealed progressive memory accumulation
on the cloud VM over extended uptime. A cold reboot between runs eliminates this
confound and ensures each run starts from a clean host state.

### Post-Run Workflow (per run)

Same as v2 §Post-Run Workflow (chown, parse, 6 CLIs, delete controller/service logs).
After analysis, execute the reboot protocol above before launching the next run.

## Focus & Evidence

Same as v2 §Focus & Evidence. Primary focus: reaction latency (Criterion 3).
Secondary: service quality with reduced noise floor (Criterion 5).

**Additional Pass 1-vs-Pass 2 comparison**:
- **Latency files** (`client_requests.csv`) — compare per-mode failure rate
  and latency percentiles (p50, p95, p99) between Pass 1 (curl=10s) and
  Pass 2 (curl=30s). The failure rate should drop; the latency distribution
  should shift right (uncensored tail).
- **Resource files** (`resource_stats.csv`) — `avg_time_db_ms` should be
  identical between passes (the controller sees the same DB time regardless
  of client timeout). This is the mechanism-neutrality check.
- **Controller logs** — same elasticity events, same Tier 1 activations,
  same scale-up counts across passes. Confirms `CURL_MAX_TIME` does not
  alter controller behaviour.

## Metrics & Success Criteria

Same 10 criteria as v2 §Metrics & Success Criteria, with adjusted expectations
and two Pass 2-specific criteria:

| # | Criterion | v2-Lite Expectation |
|---|-----------|-------------------|
| 1 | All runs complete | Pass 1: 4/4 → idle; Pass 2: 4/4 → idle |
| 2 | Information age ~0 | Push ~0.05s; Poll ~5–10s (poll-interval gated) |
| 3 | Reaction latency ↑ with poll interval | Push < Poll-5s < Poll-12s < Poll-30s (same pattern as v2, both passes) |
| 4 | Mechanisms exercise | All 4 mechanisms in all 8 runs |
| 5 | Service quality degrades | Push ≤ Poll-5s ≤ Poll-12s ≤ Poll-30s, with failure rates lower in Pass 2 than Pass 1 |
| 6 | **Pass 2 failure rate < Pass 1** | Per-mode Δ ≥ +3 pp improvement (e.g. Poll-30s: 12%→7%). The higher curl timeout reduces HTTP‑0 kills. |
| 7 | **Mechanism neutrality** | `avg_time_db_ms`, elasticity event counts, and Tier 1 activation counts statistically indistinguishable between Pass 1 and Pass 2 for the same telemetry mode. |

## Validity Threats

1. **n=1 per mode × timeout** — one run per (telemetry_mode, curl_timeout) cell.
   Formal confidence intervals require more replicates; this plan provides
   pattern confirmation and a directional check on the timeout effect.
2. **Time-separated comparison** — Pass 1 and Pass 2 run at different wall-clock
   times (~2 h apart). Cloud-VM host conditions (background load, thermal
   throttling) may differ. Reboot between every run and between passes
   mitigates but does not eliminate this confound.
3. **Run order confound** — Push always first within each pass (cleanest
   post-reboot host). Mitigated by reboot between every run (all runs start
   cold) and same mode ordering as v2.
4. **Cross-WAN comparability** — Results at WAN=200ms are not directly
   comparable to v2 WAN=260ms. The two datasets characterise the blind-spot
   effect at different operating points.
5. **Reboot adds ~2 min per run** — acceptable; host-state consistency is the
   higher priority.
6. **`CURL_MAX_TIME` env var prerequisite** — if `traffic_generator.py` still
   hardcodes `--max-time 10`, Pass 2 runs will silently use 10 s instead of
   30 s. The runner must verify the env var is consumed before launching
   Pass 2 (e.g. `grep -n 'CURL_MAX_TIME' source/scripts/testing/traffic_generator.py`).
7. All other v2 validity threats (§Validity Threats) apply unchanged.

## Artifact Contract

Same as v2 §Artifact Contract. Run folders at:
- `source/scripts/testing/metrics/<timestamp>_rq1_v2lite_push_1/`
- `source/scripts/testing/metrics/<timestamp>_rq1_v2lite_poll5_1/`
- `source/scripts/testing/metrics/<timestamp>_rq1_v2lite_poll12_1/`
- `source/scripts/testing/metrics/<timestamp>_rq1_v2lite_poll30_1/`
- `source/scripts/testing/metrics/<timestamp>_rq1_v2lite_push_t30/`
- `source/scripts/testing/metrics/<timestamp>_rq1_v2lite_poll5_t30/`
- `source/scripts/testing/metrics/<timestamp>_rq1_v2lite_poll12_t30/`
- `source/scripts/testing/metrics/<timestamp>_rq1_v2lite_poll30_t30/`

Results will be documented in `results_v2_lite.md` in this folder.
