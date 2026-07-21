# RQ1 v6 — Short Fuse Pilot

**Status**: 📋 Planned · **Date**: 2026-07-20
**Predecessor**: [`../v5/experiment_plan_v5.md`](../v5/experiment_plan_v5.md) · [`../v5/results_v5.md`](../v5/results_v5.md)

## Intent

v5 Pilot B proved the telemetry coordination gap is real at the mechanism level
(64% blind spot, 41% fewer compute spawns) but does not cause user-visible
throughput collapse. The system handles 96 clients gracefully: only 1.9–2.7%
timeout rate, despite 60–74% of those timeouts being `storage_bound`.

The gap's primary user-visible manifestation is **diffuse, stochastic
degradation** — 3.5× more `transient_spike` failures, 2.8× more curl
drops, 1.8× wider latency spread. But CURL_MAX_TIME=30s provides a deep
queueing buffer that absorbs the pathological tail: Poll-30s p99 hits 30s on
`service_pressure` while Push p99 is only 1.3s. These requests complete as
slow successes rather than failures.

**v6 removes the buffer.** By lowering CURL_MAX_TIME from 30s to 10s, Poll-30s's
10–30s stale-routing tail converts from "slow success" to "explicit curl
failure." Push, with p99=1.3s, is unaffected. Everything else — storage,
clients, phases, thresholds — stays identical to v5 Pilot B.

**Why 10s?** Push p99=1.3s → unaffected. Poll-30s p99=30s → the 10–30s tail is
pure stale-routing damage. Cross-region p95=8–9s → legitimate WAN traffic fits.

This is a **pilot**: Push vs Poll-30s, n=2 (4 runs). Single variable change.

## Hypothesis / Expected Outcome

1. **CURL_MAX_TIME=15s exposes the tail**: Poll-30s's 15–30s latency victims
   become explicit curl failures (http_status=0). Push, with p99=1.3s, is
   essentially unaffected.
2. **Curl failure ratio amplifies**: Poll-30s/Push curl failure ratio increases
   from v5's 2.76× toward 3–4×. This is the primary v6 measurement (M10).
3. **Failure composition shifts**: `storage_bound` still dominates (storage
   is unchanged), but a new `curl_failure` category emerges prominently in
   Poll-30s, capturing the clipped tail.
4. **Throughput gap widens modestly**: With less queueing buffer, Poll-30s
   completes fewer requests in compute_spike. Gap should widen from v5's
   20% toward 30%+.
5. **Blind spot persists**: M6 remains ~64% for Poll-30s, ~0% for Push —
   the telemetry mechanism is unchanged by CURL_MAX_TIME.

## RQ Linkage

**Thesis RQ1**: How does telemetry delivery cadence affect reaction latency
and transient service quality during demand shifts?

**v6 contribution**: v5 established that stale routing causes *diffuse,
stochastic degradation*. v6 proves the mechanism by removing the queueing
buffer that hid it — the stochastic degradation converts to explicit,
measurable failure. Same blind spot, same stale routing, shorter fuse.

## Independent Variable & Held-Constant Set

| Parameter                         | v5 Pilot B                       | v6 Pilot             | Notes                            |
| --------------------------------- | -------------------------------- | -------------------- | -------------------------------- |
| **Telemetry mode**          | Push / Poll-30s                  | Push / Poll-30s      | Independent variable             |
| **CURL_MAX_TIME**           | **30s**                    | **15s**        | **Single variable change** |
| STORAGE_CPUS                      | 0.08                             | 0.08                 | Held constant                    |
| STORAGE_MEMORY                    | 512m                             | 512m                 | Held constant                    |
| wiredTigerCacheSizeGB             | 0.25                             | 0.25                 | Held constant                    |
| `maxPoolSize` (edge→VIP)       | 1                                | 1                    | Held constant                    |
| CLIENTS                           | 96                               | 96                   | Held constant                    |
| MAX_DYNAMIC_COMPUTE               | 12                               | 12                   | Held constant                    |
| Phases                            | Canonical (60–300s)             | Canonical (60–300s) | Held constant                    |
| CPU_SPAN                          | 40                               | 40                   | Held constant                    |
| WAN_RTT_MS                        | 185                              | 185                  | Held constant                    |
| Controller env                    | `current_state_integrated.env` | Same                 | Held constant                    |
| `compute_spike` rate_per_client | 2.0 rps                          | 2.0 rps              | Held constant                    |

**This is a single-variable experiment.** Everything except CURL_MAX_TIME is
identical to v5 Pilot B. No storage tuning, no Docker rebuilds, no new env vars.
v6 answers: "Does removing the queueing buffer make the existing pattern explicit?"

### Why 15s?

| Factor                                | Value                   | Rationale                                            |
| ------------------------------------- | ----------------------- | ---------------------------------------------------- |
| Push p99 (service_pressure, v5)       | 1.3s                    | Well under 15s — Push unaffected                    |
| Poll-30s p99 (service_pressure, v5)   | **30.0s**         | Hitting cap; 15–30s tail = stale-routing damage     |
| Cross-region p95 (content_lookup, v5) | 8–9s                   | Comfortable 6–7s margin — p99 likely fits            |
| v5`transient_spike` gap             | 3.5× more in Poll-30s  | "Should have worked" → at 15s, they fail explicitly |
| v5 curl failure ratio                 | 2.76× (5.71% vs 2.07%) | At 15s, expected to reach 3–4×                     |

At 30s: "Poll-30s is 1.4× worse on timeouts."
At 15s: "Poll-30s is 3–4× worse on curl failures."

The ratio change IS the finding — same mechanism, shorter fuse.

## Run Matrix

| #  | Label                     | Mode       | CURL_MAX_TIME |
| -- | ------------------------- | ---------- | ------------- |
| V1 | `rq1_v6_pilot_push_1` | Push (zmq) | **15**  |
| V2 | `rq1_v6_pilot_push_2` | Push (zmq) | **15**  |
| V3 | `rq1_v6_pilot_poll30_1` | Poll-30s   | **15**  |
| V4 | `rq1_v6_pilot_poll30_2` | Poll-30s   | **15**  |

All other parameters identical to v5 Pilot B: STORAGE_CPUS=0.08, STORAGE_MEMORY=512m,
CLIENTS=96, MAX_DYNAMIC_COMPUTE=12, canonical phases, CPU_SPAN=40, WAN_RTT_MS=185.

**Total: 4 runs.** Run order: V1→V2→V3→V4. ~2h campaign. No setup required
(no Docker rebuilds, no config file edits beyond the CURL_MAX_TIME flag).

## Primary Measurement: Curl Failure Ratio (M10)

v6 is **exploratory** — it asks "what becomes visible when the queueing buffer
is removed?" There is no pass/fail gate. The primary measurement is:

**M10 — Curl Failure Ratio**: Poll-30s curl failure rate ÷ Push curl failure
rate, computed across the full run (all phases). Reported with inter-replicate
min-max range.

v5 baseline at CURL_MAX_TIME=30s: 2.76× (5.71% vs 2.07%).
At 15s, Push should barely move (p99=1.3s << 15s); Poll-30s's 15–30s tail
converts from slow successes to curl failures. Expected: 3–4×.

**Why curl failures, not timeouts?** At CURL_MAX_TIME=15s, latency-based
timeouts (≥29.9s) become rare — requests hit the curl cap first. Curl failures
capture the same phenomenon at the new ceiling.

### Supporting measurements (no gates)

| Measurement | What | v5 baseline |
|-------------|------|-------------|
| M10 — Curl failure ratio | Poll-30s/Push curl failure rate | 2.76× |
| M4 — Throughput gap | Poll-30s/Push throughput in compute_spike | 80% (20% gap) |
| M1 — Spawn count gap | Compute spawns Poll-30s vs Push | 41% gap |
| M6 — Blind spot rate | Breach windows unseen by controller | 0% vs 64% |
| M7 — Failure composition | storage_bound, transient_spike, curl_failure | 60–74% storage_bound |
| M8 — Latency spread | p50-p95 spread on service_pressure | 1.8× wider |

All measurements are reported, compared to v5 baselines, and interpreted.
No single measurement determines "success" — the full pattern matters.

## Run Configuration

### Per-Run Invocation

```bash
# Push mode (V1, V2) — identical to v5 Pilot B except CURL_MAX_TIME=15
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=<LABEL> \
  PHASES_CONFIG=testing/phases.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  WAN_RTT_MS=185 CLIENTS=96 DEVICES=6000 NODES=100 STORAGE_CPUS=0.08 \
  CURL_MAX_TIME=15 RANDOM_SEED=42 DATA_SEED=42 \
  > /tmp/<LABEL>.log 2>&1 &"

# Poll-30s mode (V3, V4)
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=<LABEL> \
  PHASES_CONFIG=testing/phases.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  WAN_RTT_MS=185 CLIENTS=96 DEVICES=6000 NODES=100 STORAGE_CPUS=0.08 \
  TELEMETRY_SOURCE=poll POLL_INTERVAL_S=30 \
  CURL_MAX_TIME=15 RANDOM_SEED=42 DATA_SEED=42 \
  > /tmp/<LABEL>.log 2>&1 &"
```

### Post-Run Workflow

#### Phase 1 — Gate Verification & Log Parsing (per run)

```bash
RUN_DIR="source/scripts/testing/metrics/<timestamp>_<label>"
sudo chown -R testop:testop "$RUN_DIR"

# ── Gates (BEFORE log deletion) ──
grep 'cpu_span.*40' "$RUN_DIR/controller_lan1.log" | head -5          # G2
grep 'poll_interval_s.*30' "$RUN_DIR/controller_lan1.log" | head -5   # G4 (poll only)

# ── Parse logs ──
python3 source/scripts/tools/parse_elasticity_logs.py \
  "$RUN_DIR/controller_lan1.log" "$RUN_DIR/controller_lan2.log" \
  -o "$RUN_DIR/elasticity_events.csv" \
  --timings-output "$RUN_DIR/node_lifecycle_timings.csv"
```

#### Phase 2 — Metric Extraction (per run)

```bash
# Core statistics
python3 source/scripts/tools/metrics_stats.py "$RUN_DIR" --by-phase --by-lan --by-endpoint
python3 source/scripts/tools/metrics_stats.py -r "$RUN_DIR/resource_stats.csv" --by-phase --by-network

# RQ1 analysis (M1–M9)
python3 -m source.scripts.testing.analysis.rq1.cli.timings --run-dir "$RUN_DIR"
python3 -m source.scripts.testing.analysis.rq1.cli.missed_opportunities --run-dir "$RUN_DIR"
python3 -m source.scripts.testing.analysis.rq1.cli.time_to_capacity --run-dir "$RUN_DIR"
python3 -m source.scripts.testing.analysis.rq1.cli.blind_spot_windows --run-dir "$RUN_DIR"
python3 -m source.scripts.testing.analysis.rq1.cli.timeout_root_cause --run-dir "$RUN_DIR"
python3 -m source.scripts.testing.analysis.rq1.cli.endpoint_latency --run-dir "$RUN_DIR"
python3 -m source.scripts.testing.analysis.rq1.cli.recovery_lag --run-dir "$RUN_DIR"
python3 -m source.scripts.testing.analysis.rq1.cli.decision_quality --run-dir "$RUN_DIR"
python3 -m source.scripts.testing.analysis.rq1.cli.overhead --run-dir "$RUN_DIR"
```

#### Phase 3 — Log Cleanup (per run)

```bash
rm "$RUN_DIR/controller_lan1.log" "$RUN_DIR/controller_lan2.log"
rm -rf "$RUN_DIR/service_logs/"
```

#### Phase 4 — Cross-Run Analysis (after all 4 runs)

```bash
BASE="source/scripts/testing/metrics"

# M10: curl failure ratio (measurement, not gate)
python3 -c "
import csv; from pathlib import Path
base = Path('$BASE')
modes = {'push': [], 'poll30': []}
for rd in base.glob('*rq1_v6_pilot*'):
    label = rd.name
    total = http0 = 0
    with open(rd / 'client_requests.csv') as f:
        for row in csv.DictReader(f):
            total += 1
            if row.get('http_status') == '0':
                http0 += 1
    rate = http0/total*100 if total else 0
    if 'push' in label:
        modes['push'].append(rate)
    else:
        modes['poll30'].append(rate)

push_avg = sum(modes['push'])/len(modes['push']) if modes['push'] else 0
poll_avg = sum(modes['poll30'])/len(modes['poll30']) if modes['poll30'] else 0
ratio = poll_avg/push_avg if push_avg else 0
print(f'Push curl failure: {push_avg:.2f}%')
print(f'Poll-30s curl failure: {poll_avg:.2f}%')
print(f'M10 ratio: {ratio:.1f}x (v5 baseline: 2.76x at 30s cap)')
"

# M4: throughput in compute_spike
python3 -c "
import csv; from pathlib import Path
base = Path('$BASE')
counts = {'push': [], 'poll30': []}
for rd in base.glob('*rq1_v6_pilot*'):
    label = rd.name
    count = 0
    with open(rd / 'client_requests.csv') as f:
        for row in csv.DictReader(f):
            if row.get('phase') == 'compute_spike':
                count += 1
    if 'push' in label:
        counts['push'].append(count)
    else:
        counts['poll30'].append(count)

push_avg = sum(counts['push'])/len(counts['push']) if counts['push'] else 1
poll_avg = sum(counts['poll30'])/len(counts['poll30']) if counts['poll30'] else 0
ratio = poll_avg/push_avg*100
print(f'Push throughput: {push_avg:.0f} reqs')
print(f'Poll-30s throughput: {poll_avg:.0f} reqs')
print(f'M4 ratio: {ratio:.0f}% (v5 baseline: 80%)')
"
```

## Analysis → Graphs Mapping

| #            | Graph                              | Data Source                                                          | What It Shows                                                                                        | Criterion     |
| ------------ | ---------------------------------- | -------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- | ------------- |
| G1           | **Blind Spot Rate**          | `analysis/rq1_blind_spot_windows.csv`                              | Breached vs consumed windows; Push ~0%, Poll-30s ~64%                                                | C9            |
| G2           | **Compute Spawn Count**      | `node_lifecycle_timings.csv`                                       | Bar chart: Push vs Poll-30s compute spawns; ≥40% gap                                                | C3            |
| G3           | **Throughput by Phase**      | `client_requests.csv` (phase)                                      | Per-phase request count, Push vs Poll-30s                                                            | C2, C6        |
| G4           | **Mean Latency by Phase**    | `client_requests.csv` (latency_s, phase)                           | Per-phase mean latency with inter-replicate min-max range                                            | C11           |
| **G5** | **Curl Failure Rate**        | `client_requests.csv` (http_status=0)                              | **Headline v6 graph**: curl failure % with M10 ratio annotation                  | M10           |
| G6           | **Failure Composition**      | `analysis/rq1_timeout_root_cause.csv` + curl failures              | Stacked bar: storage_bound, transient_spike, unclassified, + explicit `curl_failure` bar (see G6 detail below) | M7            |
| G7           | **Latency CDF**              | `client_requests.csv` (latency_s, compute_spike, service_pressure) | Overlaid CDFs: Push (steep, p99~1.3s) vs Poll-30s (tail to 15s). Vertical line at CURL_MAX_TIME=15s. | M8            |
| G8           | **Endpoint Latency Heatmap** | `analysis/rq1_endpoint_latency.csv`                                | p50/p95/p99 per endpoint per mode                                                                    | C11           |
| G9           | **Missed Opportunities**     | `analysis/rq1_missed_opportunities.csv`                            | Phases with CPU pressure but no spawns                                                               | C4            |
| G10          | **Recovery Lag**             | `analysis/rq1_recovery_lag.csv`                                    | Time to baseline after demand_drop                                                                   | Diagnostic    |

### Graph Style

- Colors: `#2196F3` (Push), `#F44336` (Poll-30s)
- Font: sans-serif, title: `"RQ1 v6 — Description"`
- Bar alpha: 0.80, grid alpha: 0.25, hide top/right spines
- Inter-replicate min-max range as error bars

### New for v6

| Graph                    | Novelty                                      |
| ------------------------ | -------------------------------------------- |
| G5 (Curl Failure Rate)   | Headline metric replacing timeout rate       |
| G6 (Failure Composition) | `curl_failure` as explicit category        |
| G7 (Latency CDF)         | Full distribution + CURL_MAX_TIME=15s marker |

### G6 Implementation Detail

G6 merges two disjoint data sources into a single stacked bar per mode:

1. **M7 categories** (from `rq1_timeout_root_cause.csv`): latency-based timeouts
   (≥29.9s) classified as storage_bound, transient_spike, unclassified, etc.
   At CURL_MAX_TIME=15s, these will be sparse — few requests survive to 29.9s.

2. **Curl failures** (from `client_requests.csv`): `http_status='0'` AND
   `latency_s < 29.9`. These are requests killed by the 15s curl cap before
   reaching the M7 latency threshold. Labeled `curl_failure`.

The two sets are **disjoint** because M7 requires `latency_s ≥ 29.9` and curl
failures have `http_status='0'` (no valid latency). Implementation:

```python
# Per run:
m7_counts = Counter(row['category'] for row in m7_csv)  # from M7 CLI output
curl_count = sum(1 for row in client_csv
                 if row['http_status'] == '0' and float(row.get('latency_s',0)) < 29.9)
# Stack: m7_counts + {'curl_failure': curl_count}
```

This ensures every failed request is counted exactly once.

## Focus & Evidence

| Artifact                                  | What it shows                                   | Priority          | Feeds Graph    |
| ----------------------------------------- | ----------------------------------------------- | ----------------- | -------------- |
| `client_requests.csv`                   | Curl failures, throughput, latency distribution | **Primary** | G3, G4, G5, G7 |
| `analysis/rq1_blind_spot_windows.csv`   | Blind spot rate per mode                        | **Primary** | G1             |
| `node_lifecycle_timings.csv`            | Compute/storage spawn counts                    | **Primary** | G2             |
| `analysis/rq1_timeout_root_cause.csv`   | Failure composition                             | **Primary** | G6             |
| `analysis/rq1_endpoint_latency.csv`     | Per-endpoint p50/p95/p99                        | Secondary         | G8             |
| `analysis/rq1_missed_opportunities.csv` | Phases with CPU pressure, no spawns             | Secondary         | G9             |
| `analysis/rq1_recovery_lag.csv`         | Scale-down asymmetry                            | Secondary         | G10            |
| `resource_stats.csv`                    | server/storage count, CPU/RAM                   | Reference         | —             |
| `phases_snapshot.json`                  | Phase order, durations                          | Reference         | —             |

## Metrics & Measurements

| #   | Measurement                          | What                                             | Origin |
| --- | ------------------------------------ | ------------------------------------------------ | ------ |
| C1  | All 4 pilot runs complete            | 4/4 → idle, zero controller tracebacks          | v5     |
| M10 | Curl failure ratio (primary)         | Poll-30s/Push curl failure rate, with min-max    | v6     |
| M4  | Throughput gap                       | Poll-30s/Push throughput in compute_spike        | v5     |
| M1  | Spawn count gap                      | Push compute spawns vs Poll-30s                  | v5     |
| M6  | Blind spot windows                   | Breach windows consumed vs unseen                | v5     |
| M7  | Failure composition                  | storage_bound, transient_spike, curl_failure     | v5     |
| M8  | Endpoint-specific degradation        | p50/p95/p99 per endpoint per mode                | v5     |
| M2  | Missed opportunities                 | Phases with CPU pressure, < 2 spawns             | v5     |
| M9  | Recovery lag                        | Time to baseline after demand_drop               | v5     |

> **No pass/fail gates.** All metrics are measurements reported with v5 baselines
> for comparison. The pattern across measurements matters, not any single threshold.
> M7 will have few rows at 15s cap (requests hit curl cap before 29.9s) — this
> is expected and confirms the mechanism.

## Pre-Run Verification Gates

| #  | Gate                               | Command                                                                                                   | When     |
| -- | ---------------------------------- | --------------------------------------------------------------------------------------------------------- | -------- |
| G1 | `SCALEUP_CPU_SPAN=40`            | `grep CPU_SPAN source/scripts/testing/controller_env_overrides/current_state_integrated.env`            | Pre-run  |
| G3 | `SKIP_SEED ?= 1`                 | Verify in`source/scripts/Makefile`                                                                      | Pre-run  |
| G7 | `MAX_DYNAMIC_COMPUTE=12`         | `grep MAX_DYNAMIC_COMPUTE source/scripts/testing/controller_env_overrides/current_state_integrated.env` | Pre-run  |
| G2 | Controller loads`cpu_span=40`    | `grep 'cpu_span.*40' "$RUN_DIR/controller_lan1.log"`                                                    | Post-run |
| G4 | `POLL_INTERVAL_S=30` (poll mode) | `grep 'poll_interval_s.*30' "$RUN_DIR/controller_lan1.log"`                                             | Post-run |
| G10 | CURL_MAX_TIME=15 applied | `grep -i 'max.time\|CURL_MAX_TIME' "$RUN_DIR/controller_env_snapshot.env"` (post-run); also check traffic generator log for `--max-time 15` | Post-run |

> Gates G5/G6/G8/G9 (storage parameter propagation) removed — storage is
> unchanged from v5. **G10 is new for v6** — verifies the single variable change.

## Prerequisites (Blockers)

| #  | Item                                                                        | Status                    |
| -- | --------------------------------------------------------------------------- | ------------------------- |
| P1 | 6 RQ1 analysis CLIs (M2–M9)                                                | ✅ Implemented & verified |
| P2 | CURL_MAX_TIME=15 propagates to traffic generator | ⬜ Verify |
| P3 | **Graph generation script for v6** (`generate_thesis_graphs_v6.py`) | ⬜ TODO |

> No code changes needed — storage and all other config is identical to v5.

### P2 Detail — CURL_MAX_TIME Propagation

Verify CURL_MAX_TIME=15 reaches the traffic generator:
```bash
grep 'CURL_MAX_TIME\|curl_max_time' "$RUN_DIR/controller_env_snapshot.env"
```
Also check the traffic generator process that curl commands use `--max-time 15`.
Gate G10 (post-run) provides additional verification.

### P3 Detail — Graph Generation Script

Must produce G1–G10. Key requirements:
- **G5 (Curl Failure Rate)** is headline — show M10 ratio annotation (e.g., "3.2× more")
- **G6 (Failure Composition)** includes `curl_failure` (http_status=0) as a category,
  merged with M7 categories per the G6 Implementation Detail above
- **G7 (Latency CDF)** shows overlaid CDFs with vertical dashed line at CURL_MAX_TIME=15s
- All graphs: `#2196F3`/`#F44336`, sans-serif, `"RQ1 v6 — Title"`

## Validity Threats & Limitations

| Threat                                                 | Mitigation                                                                                                                                                                                               |
| ------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| CURL_MAX_TIME=15 clips legitimate cross-region traffic | Cross-region p95 is 8–9s (v5), leaving 6–7s margin. Only p99 may clip, and likely equally for both modes — the ratio signal is preserved. If Push curl failures spike unexpectedly, fallback: 20s. |
| CURL_MAX_TIME=15 hides latency-based timeout signal    | By design — curl failures replace timeouts as the primary failure metric. M7 will have few rows (requests hit curl cap before 29.9s).                                                               |
| n=2 per mode                                           | Low power. M10 uses ratio of averages. At expected Poll-30s curl rate increase of several points, signal should exceed v5's within-mode variance of 3–8%.                                            |
| Blocked run order (Push first)                         | Later runs benefit from warm caches. Accepted for pilot.                                                                                                                                                 |
| M7 sparse at 15s cap                                   | Expected — requests hit curl cap before 29.9s. M7 will classify very few rows. This proves the mechanism (curl is the ceiling). Report M7 row count alongside results.                                   |
| Storage still dominates failure composition            | Expected — storage is unchanged from v5. M10 measures the ADDITIONAL curl failures from the clipped tail. The composition shift (G6) and CDF shape (G7) matter more than absolute failure rates. |

## Artifact Contract

Standard run-folder layout from `docs/operation/testing/testing_overview.md`.

### Per-Run Artifacts

| Artifact                         | Location                    | Producer                      |
| -------------------------------- | --------------------------- | ----------------------------- |
| `client_requests.csv`          | `<run_dir>/`              | Traffic generator             |
| `resource_stats.csv`           | `<run_dir>/`              | `collect_resource_stats.py` |
| `per_node_stats.csv`           | `<run_dir>/`              | Telemetry aggregation         |
| `node_lifecycle_timings.csv`   | `<run_dir>/`              | `parse_elasticity_logs.py`  |
| `elasticity_events.csv`        | `<run_dir>/`              | `parse_elasticity_logs.py`  |
| `controller_env_snapshot.env`  | `<run_dir>/`              | `run_experiment.sh`         |
| `phases_snapshot.json`         | `<run_dir>/`              | `run_experiment.sh`         |
| `rq1_blind_spot_windows.csv`   | `<run_dir>/analysis/rq1/` | M6 CLI                        |
| `rq1_timeout_root_cause.csv`   | `<run_dir>/analysis/rq1/` | M7 CLI                        |
| `rq1_endpoint_latency.csv`     | `<run_dir>/analysis/rq1/` | M8 CLI                        |
| `rq1_missed_opportunities.csv` | `<run_dir>/analysis/rq1/` | M2 CLI                        |
| `rq1_recovery_lag.csv`         | `<run_dir>/analysis/rq1/` | M9 CLI                        |
| `rq1_time_to_capacity.csv`     | `<run_dir>/analysis/rq1/` | M3 CLI                        |

### Cross-Run Artifacts

| Artifact         | Location         | Producer                         |
| ---------------- | ---------------- | -------------------------------- |
| G1–G10 graphs   | `v6/graphs/`   | `generate_thesis_graphs_v6.py` |
| M10 + M4 summary | stdout (Phase 4) | Cross-run analysis               |

## Expansion Plan

If the pilot reveals a clear pattern, expand to full campaign:

| Mode       | Runs          | Total |
| ---------- | ------------- | ----- |
| Push (zmq) | +1 (have n=2) | n=3   |
| Poll-5s    | +3 new        | n=3   |
| Poll-12s   | +3 new        | n=3   |
| Poll-30s   | +1 (have n=2) | n=3   |

**8 additional runs.** All at CURL_MAX_TIME=15, everything else = v5 Pilot B.
Run order: push_3 → poll5_1/2/3 → poll12_1/2/3 → poll30_3.

Full campaign enables n=3 error bars on all graphs, mode ranking, and
characterization of intermediate poll intervals at the shorter timeout.

## Changelog

| Date       | Change                                                                                                                                                                                                                                                          |
| ---------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2026-07-20 | v6 pilot plan created — single-variable experiment: CURL_MAX_TIME 30→15s. All other parameters identical to v5 Pilot B. Primary measurement M10 (curl failure ratio). No pass/fail gates — exploratory. Analysis→Graphs G1–G10 mapped with G6 implementation detail. G10 verification gate added. No storage tuning, no Docker rebuilds, no code changes. |
