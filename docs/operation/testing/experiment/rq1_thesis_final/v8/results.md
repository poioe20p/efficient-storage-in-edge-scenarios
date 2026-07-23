# RQ1 v8 — Results

**Status**: ✅ Complete · **Date**: 2026-07-21 to 2026-07-22
**Plan**: [`experiment_plan_v8.md`](experiment_plan_v8.md)
**Graphs**: [`graphs/`](graphs/) · [`graphs/comparison/`](graphs/comparison/)

## Run Timeline

| Run | Date | Status | Success Rate | G8 | Notes |
|-----|------|--------|-------------|-----|-------|
| P1 (`rq1_v8_push_1`) | 2026-07-21 18:49 | ✅ | 97.1% | PASS | Re-run after SSH kill (1st attempt: tee pipe broken) |
| P2 (`rq1_v8_push_2`) | 2026-07-21 19:48 | ✅ | 96.8% | PASS | |
| P3 (`rq1_v8_push_3`) | 2026-07-22 00:07 | ✅ | 96.1% | PASS | 3rd attempt (first 2 stalled at cleanup_gap phases) |
| F1 (`rq1_v8_poll5_1`) | 2026-07-22 01:08 | ✅ | 87.8% | PASS | |
| F2 (`rq1_v8_poll5_2`) | 2026-07-22 02:08 | ✅ | 97.7% | PASS | |
| F3 (`rq1_v8_poll5_3`) | 2026-07-22 03:06 | ✅ | 97.5% | PASS | |
| W1 (`rq1_v8_poll12_1`) | 2026-07-22 04:04 | ✅ | 95.9% | PASS | |
| W2 (`rq1_v8_poll12_2`) | 2026-07-22 05:03 | ✅ | 97.7% | PASS | |
| W3 (`rq1_v8_poll12_3`) | 2026-07-22 06:01 | ✅ | 97.5% | PASS | |
| T1 (`rq1_v8_poll30_1`) | 2026-07-22 06:59 | ✅ | 97.1% | PASS | |
| T2 (`rq1_v8_poll30_2`) | 2026-07-22 07:57 | ✅ | 90.3% | PASS | |
| T3 (`rq1_v8_poll30_3`) | 2026-07-22 08:54 | ✅ | 95.8% | PASS | |

**All 12 runs G8 PASS** — no dynamic nodes spawned during cleanup gaps. Every high-load phase starts from zero.

## Overall Health

| Mode | n | Mean Success | Min | Max | σ |
|------|---|-------------|-----|-----|---|
| Push | 3 | 96.7% | 96.1% | 97.1% | 0.4% |
| Poll-5s | 3 | 94.3% | 87.8% | 97.7% | 4.6% |
| Poll-12s | 3 | 97.0% | 95.9% | 97.7% | 0.8% |
| Poll-30s | 3 | 94.4% | 90.3% | 97.1% | 2.9% |

**Caveat**: Aggregate success rate is a coarse metric — it masks per-phase degradation during cross-region stress phases. The dose-response curve emerges from the RQ1-specific metrics (blind spot rate, reaction latency, per-phase throughput gap), not from aggregate success rate. See cross-mode comparison graphs for the full picture.

## Per-Run Quick Stats

### Push Mode

| Run | Requests | 200 | 0 (timeout) | 503 | 500 |
|-----|----------|-----|-------------|-----|-----|
| P1 | 65,551 | 63,640 | 1,623 | 275 | 13 |
| P2 | 65,937 | 63,845 | 1,754 | 330 | 7 |
| P3 | 70,390 | 67,638 | 2,270 | 468 | 13 |

### Poll-5s Mode

| Run | Requests | 200 | 0 (timeout) | 503 |
|-----|----------|-----|-------------|-----|
| F1 | 66,355 | 58,234 | 8,108 | 12 |
| F2 | ~66,687 | 65,178 | 1,508 | — |
| F3 | 68,860 | 67,122 | 1,550 | 188 |

### Poll-12s Mode

| Run | Requests | 200 | 0 (timeout) | 503 |
|-----|----------|-----|-------------|-----|
| W1 | 65,400 | 62,687 | 2,572 | 141 |
| W2 | 71,758 | 70,126 | 1,483 | 149 |
| W3 | 68,050 | 66,337 | 1,660 | 53 |

### Poll-30s Mode

| Run | Requests | 200 | 0 (timeout) | 503 |
|-----|----------|-----|-------------|-----|
| T1 | 72,802 | 70,717 | 1,658 | 427 |
| T2 | 37,927 | 34,259 | 3,608 | 60 |
| T3 | 52,857 | 50,633 | 2,224 | — |

## Operational Notes

### P3 Stall Issue
P3 required 3 attempts. The first two stalled at cleanup_gap phases (v1 at cleanup_gap_2, v2 at cleanup_gap_1) with processes at 0% CPU. Root cause not yet diagnosed — controller logs show 1 `Traceback`/`Error`/`EXCEPTION`/`FATAL` match in each log, but the specific error was not inspected. The third attempt succeeded normally. This may be a rare race condition during low-load cleanup_gap phases.

### SSH Keepalive
The first P1 attempt was killed when the SSH connection dropped and broke the `tee` pipe. All subsequent runs used `nohup ... > log 2>&1 &` to fully detach from the terminal. This pattern should be the standard for all future campaigns.

### Anomalies
- **F1** (Poll-5s): 87.8% success is notably lower than F2 (97.7%) and F3 (97.5%). The 8,108 timeouts exceed the other Poll-5s replicates by ~5×. Worth flagging as a potential outlier.
- **T2** (Poll-30s): 90.3% success shows the expected Poll-30s degradation vs faster modes. T1 (97.1%) and T3 (95.8%) are closer to Push-mode performance, suggesting bimodality — a known characteristic of Poll-30s from v3-v7.

## Evidence Inventory

All 12 runs have complete analysis outputs:
- 12 PNGs per run: `overview_throughput.png`, `overview_latency.png`, `overview_resources.png`, `simple_run.png`, `phase_summary.png`, `endpoint_breakdown.png`, `scale_down.png`, `lifecycle_gantt.png`, `cpu_drivers.png`, `tdb_drivers.png`, `rq1_staleness.png`, `rq1_reaction_latency.png`
- 3 additional PNGs: `rq1_overhead_cpu.png`, `rq1_overhead_ram.png`, `rq1_decision_quality.png`
- 11 RQ1 CSVs per run in `analysis/rq1/`: `rq1_blind_spot_windows.csv`, `rq1_timeout_root_cause.csv`, `rq1_missed_opportunities.csv`, `rq1_time_to_capacity.csv`, `rq1_endpoint_latency.csv`, `rq1_recovery_lag.csv`, `rq1_decision_quality.csv`, `rq1_overhead.csv`, plus reaction latency and staleness CSVs
- Cross-mode comparison: 8 PNGs + 1 CSV in `graphs/comparison/`

Per-run graphs archived at `graphs/<run_timestamp>/`. Comparison graphs at `graphs/comparison/`.
