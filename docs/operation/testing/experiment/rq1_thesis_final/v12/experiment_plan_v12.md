# RQ1 v12 — Storage Cascade Dose-Response (4 modes, n=3, EDGE=0.15, STORAGE=0.05)

**Status**: 📋 Planned · **Date**: 2026-07-27
**Predecessor**: [`../v11_calibration/experiment_plan_v11_calibration.md`](../v11_calibration/experiment_plan_v11_calibration.md)
**Thesis RQ**: [`docs/research_questions/rq1/rq1_v12.md`](../../../../research_questions/rq1/rq1_v12.md)

## Intent

v11_calibration swept `STORAGE_CPUS` and `cross_region_ratio` at
`EDGE_CPUS=0.15`. The winning configuration — S2 (`STORAGE_CPUS=0.05`,
`cross_region_ratio=0.40`) with `--connect-timeout 5` in the traffic
generator — produced a clean, 5-of-6 gate pass in a single pilot pair:

| Metric | Push | Poll-30s | Δ |
|--------|------|----------|---|
| Total requests | 85,682 | 60,081 | −30% |
| Timeout rate | 2.8% | 8.1% | +2.9× |
| p50 latency | 195 ms | 66 ms | — |
| p95 latency | 9.6 s | 18.0 s | +1.88× |
| Latency stddev | 4.9 s | 6.1 s | +24% |

**v12 is the definitive campaign on S2+CT5**: all four telemetry modes, n=3
per mode, 12 runs total, with a **sequential gate**. The Push and Poll-30s
extremes run first (6 runs). If the S2 pilot separation does not replicate
across n=3, the campaign stops. If the separation holds, Poll-5s and
Poll-12s complete the dose-response curve.

Unlike v10 (which was based on a single-pilot C2 calibration that proved
unreliable at n=3), v12 is based on a systematic 5-config calibration sweep
with n=2 Poll-30s per config before committing Push runs. The S2
configuration produced consistent Poll-30s degradation across both
replicates (58.5K/57.5K, 3.0%/4.2% TO without CT; 60.1K, 8.1% TO with CT).

## Hypothesis / Expected Outcome

1. **Push vs Poll-30s separation holds at n=3.** Push completes ≥80K
   requests per run with ≤3.5% timeout; Poll-30s completes ≤62K with ≥6%
   timeout. No overlap between the worst Push and best Poll-30s replicate.

2. **Full dose-response curve is monotonic.** Push ≈ Poll-5s (both near-zero
   blind spot) > Poll-12s (intermediate) > Poll-30s (major blind spot).
   Throughput, timeout rate, p95 latency, and latency variance follow the
   polling interval gradient.

3. **p95 latency separates cleanly.** Push p95 < 12 s; Poll-30s p95 ≥ 16 s;
   Poll-5s and Poll-12s fall between. p95 gap follows the polling interval
   gradient.

4. **Timeout rate separates via TCP accept-queue failures.** At
   `STORAGE_CPUS=0.05` + `--connect-timeout 5`, the edge server accept queue
   saturates during P30's blind spot. P30 sees ≥6% timeout vs Push ≤3.5%.

5. **Latency variance increases with polling interval.** Stddev of latency
   increases monotonically from Push → Poll-30s as blind-spot queuing
   introduces dispersion.

6. **G8 passes for all 12 runs.** No dynamic nodes spawn during cleanup gaps.

## RQ Linkage

**Thesis RQ1**: How does telemetry delivery cadence affect reaction latency
and transient service quality during demand shifts?

v12 establishes the full dose-response curve on a storage-constrained
configuration where the blind-spot penalty cascades through the TCP accept
queue into measurable timeout separation. The v11 calibration proved that
the storage tier is the cascade amplifier — tightening `STORAGE_CPUS` from
0.08 (v10) to 0.05 (v12) makes the 20s detection gap between Push and
Poll-30s visible across throughput, timeout, p95 latency, and latency
variance.

## Independent Variable & Held-Constant Set

### Independent Variable

**Telemetry delivery mode**: Push (ZMQ at window close), Poll-5s (HTTP every
5 s), Poll-12s (HTTP every 12 s), Poll-30s (HTTP every 30 s).

### Held Constant

| Parameter | Value | Notes |
|-----------|-------|-------|
| `EDGE_CPUS` | **0.15** | Same as v10; Push handles this (≥94% success) |
| `STORAGE_CPUS` | **0.05** | v11 winner — storage cascade amplifier (−38% vs v10) |
| `CLIENTS` | 96 | Same as v8/v10 |
| `DEVICES` | 6000 | Same as v8/v10 |
| `NODES` | 100 | Same as v8/v10 |
| `MAX_DYNAMIC_COMPUTE` | 12 | Same as v8/v10 |
| `MAX_DYNAMIC_STORAGE` | 8 | Same as v8/v10 |
| `STORAGE_MEMORY` | 512m | Same as v8/v10 |
| `EDGE_MEMORY` | 256m | Build script default |
| `CURL_MAX_TIME` | 30 | Same as v8/v10 |
| `--connect-timeout` | **5** | Added to `traffic_generator.py` — permanent |
| `CPU_SPAN` | 40 | Same as v8/v10 |
| `WAN_RTT_MS` | 185 | Same as v8/v10 |
| `RANDOM_SEED` | 42 | Same as v8/v10 |
| `DATA_SEED` | 42 | Same as v8/v10 |
| Phases | `phases.json` (9-phase cleanup-gap) | Same as v8/v10, CR=0.40 |
| Controller env | `current_state_integrated.env` | Same as v8/v10 |

### Why STORAGE_CPUS = 0.05

At v10's `STORAGE_CPUS=0.08`, the storage tier had enough headroom that the
blind-spot penalty only produced a throughput gap (−14%) — timeout rates
converged because both modes eventually provisioned enough nodes.

At 0.05 (−38% vs v10), the storage tier becomes the cascade bottleneck.
Under stress-phase load, storage operations take longer → edge servers queue
waiting for storage → the accept queue fills → TCP connections fail. Push
Push detects storage saturation and receives the telemetry within ~14 s
(window close + delivery + scoring) and provisions storage nodes. Poll-30s
may not detect for up to 30 s (average ~15 s) — during which the storage cascade propagates through
the edge tier, saturating the TCP accept queue. `--connect-timeout 5` catches
these TCP-level failures as `http_status=0`, producing the 2.9× timeout ratio.

The 240 s cleanup gaps exceed the controller's `SCALEDOWN_COMPUTE_COOLDOWN_S=180`
and `SCALEUP_STORAGE_COOLDOWN_S=120`, ensuring all dynamic nodes drain during
gaps.

## Run Matrix

| # | Label | Mode | EDGE_CPUS | STORAGE_CPUS |
|---|-------|------|-----------|-------------|
| P1 | `rq1_v12_push_1` | Push | 0.15 | 0.05 |
| P2 | `rq1_v12_push_2` | Push | 0.15 | 0.05 |
| P3 | `rq1_v12_push_3` | Push | 0.15 | 0.05 |
| T1 | `rq1_v12_poll30_1` | Poll-30s | 0.15 | 0.05 |
| T2 | `rq1_v12_poll30_2` | Poll-30s | 0.15 | 0.05 |
| T3 | `rq1_v12_poll30_3` | Poll-30s | 0.15 | 0.05 |
| F1 | `rq1_v12_poll5_1` | Poll-5s | 0.15 | 0.05 |
| F2 | `rq1_v12_poll5_2` | Poll-5s | 0.15 | 0.05 |
| F3 | `rq1_v12_poll5_3` | Poll-5s | 0.15 | 0.05 |
| W1 | `rq1_v12_poll12_1` | Poll-12s | 0.15 | 0.05 |
| W2 | `rq1_v12_poll12_2` | Poll-12s | 0.15 | 0.05 |
| W3 | `rq1_v12_poll12_3` | Poll-12s | 0.15 | 0.05 |

**Total: 12 runs.** Run order: P1→P2→P3→T1→T2→T3 → **gate check** →
F1→F2→F3→W1→W2→W3. The gate after T3 verifies the Push vs Poll-30s
separation before committing to intermediate modes.

Each run: ~32 min (1920 s phases). Total wall-clock: **10–14 h** (including
~3–5 launch attempts per run and namespace cleanup between runs).

### Sequential Gate (after T3)

After the first 6 runs (P1–P3, T1–T3), check:

| Gate | Check | Pass condition |
|------|-------|---------------|
| Throughput separation | Push μ vs Poll-30s μ | Push ≥ 80K, Poll-30s ≤ 62K, no overlap |
| Timeout separation | Push μ vs Poll-30s μ | Push ≤ 3.5%, Poll-30s ≥ 6%, Poll-30s ≥ 1.7× Push |
| p95 latency separation | Push μ vs Poll-30s μ | Poll-30s p95 ≥ 1.5× Push p95 AND Poll-30s p95 ≥ 16 s |
| G8 | All 6 runs | No spawns during cleanup gaps |

If all four gates pass, proceed to F1–W3. If any gate fails, stop and
diagnose.

Quick gate check from the cloud VM (after P1–P3, T1–T3 complete) — run from
the metrics directory:

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios/source/scripts/testing/metrics
# Throughput
for d in 202*_rq1_v12_push_* 202*_rq1_v12_poll30_*; do
  echo "$d: $(wc -l < $d/client_requests.csv) requests"
done

# Timeout rate (http_status=0 rows / total) — handles zero-timeout case
for d in 202*_rq1_v12_push_* 202*_rq1_v12_poll30_*; do
  total=$(wc -l < $d/client_requests.csv)
  timeouts=$(grep -c ',0$' $d/client_requests.csv 2>/dev/null || true)
  [ -z "$timeouts" ] && timeouts=0
  python3 -c "print(f'$d: {$timeouts/$total*100:.1f}%')"
done
```

### Prerequisites

- `traffic_generator.py` must contain `--connect-timeout 5` (verified in
  v11 calibration — permanent change)
- `phases.json` must have the 9-phase cleanup-gap structure with
  `cross_region_ratio=0.40` in hotspot phases
- `current_state_integrated.env` must match v10/v11 baseline
- No Docker image rebuild needed

### Per-Run Cleanup

```bash
ssh cloud-vm "sudo python3 /tmp/clean_ns.py && \
  sudo -n bash ~/efficient-storage-in-edge-scenarios/source/scripts/cleanup.sh"
```

## Run Configuration

### Push Mode (P1–P3)

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n make -C source/scripts setup_network create_clients \
    setup_test_data run_experiment \
  RUN_LABEL=<LABEL> \
  EDGE_CPUS=0.15 STORAGE_CPUS=0.05 \
  PHASES_CONFIG=testing/phases.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  WAN_RTT_MS=185 CLIENTS=96 STORAGE_MEMORY=512m \
  CURL_MAX_TIME=30 RANDOM_SEED=42 DATA_SEED=42 \
  > /tmp/<LABEL>.log 2>&1 &"
```

### Poll-30s Mode (T1–T3)

Same as Push, with `TELEMETRY_SOURCE=poll POLL_INTERVAL_S=30`.

### Poll-5s Mode (F1–F3)

Same as Push, with `TELEMETRY_SOURCE=poll POLL_INTERVAL_S=5`.

### Poll-12s Mode (W1–W3)

Same as Push, with `TELEMETRY_SOURCE=poll POLL_INTERVAL_S=12`.

### Run Monitoring

```bash
# Check if run is alive
ssh cloud-vm "pgrep -af 'run_experiment'"

# Tail the log
ssh cloud-vm "tail -20 /tmp/<LABEL>.log"

# Launch watchdog
python tools/watch_run.py --host cloud-vm --run-label <LABEL> \
  --poll-interval 15 --timeout 5400
```

## Metrics & Success Criteria

| Measurement | Expected | Evidence |
|-------------|----------|----------|
| **Throughput** | Push ≥ 80K; Poll-30s ≤ 62K; no overlap | `client_requests.csv` total row count |
| **Timeout rate** | Push ≤ 3.5%; Poll-30s ≥ 6% in each replicate | `client_requests.csv` http_status=0 |
| **p95 latency** | Push < 12 s; Poll-30s ≥ 16 s | `client_requests.csv` latency_s percentile |
| **Latency stddev** | Poll-30s > Push; monotonic with interval | `client_requests.csv` latency_s stdev |
| **Spawn count** | Poll-30s spawns fewer compute nodes (detection delay = fewer spawn opportunities) | `node_lifecycle_timings.csv` |
| **G8** | PASS all 12 runs | No spawns in cleanup_gap phases |
| **Controller overhead** | Flat across modes | `resource_stats.csv` |

## Validity Threats

1. **Single STORAGE level.** S2 (0.05) was the calibration winner. Other
   STORAGE levels may produce different separation magnitudes.

2. **`--connect-timeout` is configuration-dependent.** The TCP accept-queue
   saturation effect depends on STORAGE_CPUS=0.05. At higher STORAGE, the
   accept queue may not saturate and CT would have no effect.

3. **Single workload shape.** The 9-phase cleanup-gap workload is one demand
   pattern.

4. **Known stall bug.** Expect ~3–5 launch attempts per run. Recovery:
   teardown_clients → cleanup.sh → clean_ns.py → retry.

## Changelog

| Date | Change | Rationale |
|------|--------|-----------|
| 2026-07-27 | Plan authored | v11 calibration winner: S2+CT5 (EDGE=0.15, STORAGE=0.05, connect-timeout=5). Systematic calibration, not single-pilot. |
| 2026-07-27 | Campaign aborted after 7 runs | ~30% catastrophic failure rate at n=3. S2+CT5 unstable due to `compute_spike` variance with `window_min=1`. See [results.md](results.md) §3. |
| 2026-07-27 | v13 redesign decided | Shorter stress phases (150s), tighter cleanup gaps (220s), replace `compute_spike` with `storage_storm_2`, keep S2 config, drop CT5. See [results.md](results.md) §4.3. |
