# Experiment Plan — Polling Mechanism Verification

**Status**: 🔵 Designed · **Date**: 2026-06-11
**Parent**: RQ1 — Telemetry Freshness and Delivery Cadence

## Intent

Verify that the HTTP polling telemetry source works correctly across all
phases of a workload: summaries are retrieved at the expected cadence,
deduplication prevents duplicate `_on_telemetry_update` calls, control events
(`drain_complete`, `rs_secondary_ready`) still arrive immediately via ZMQ,
and the system completes a full run without transport-specific failures.

This is a **smoke test**, not an RQ1 evaluation. It answers: *does the
polling mechanism function correctly end-to-end?*

## Hypothesis / Expected Outcome

If the polling implementation is correct:

1. **Both runs complete all phases** — push (baseline) and poll — without
   controller crashes, ZMQ errors, or HTTP polling failures.
2. **Poll cadence is respected** — `POLL_INTERVAL_S=10` produces a new summary
   consumption approximately every 10 s (jitter ≤ 1 s), matching the push cadence.
3. **Dedup is benign at 10 s** — with `POLL_INTERVAL_S=10` and
   `WINDOW_S=10`, each poll sees a new summary; no duplicates.
4. **Dedup fires correctly at 5 s and 1 s** (Runs C, E) — duplicate
   `window_end` values are skipped without re-triggering scaling
   evaluations or corrupting `_latest`. No excessive logging at 1 s.
5. **Stale data does not crash the controller** (Run D) — with
   `POLL_INTERVAL_S=30`, the controller operates on summaries 20–30 s
   behind. No timeouts, no "data too old" errors, no transport-specific
   failures. Scaling decisions may be delayed but the run completes.
4. **Control events arrive** — `drain_complete` and `rs_secondary_ready`
   events appear in controller logs at the same timestamps in both runs
   (they stay on ZMQ push regardless of `TELEMETRY_SOURCE`).
5. **Scaling decisions are comparable** — same phases trigger same mechanism
   classes (compute scale-up, storage reserve, Tier 1 activation) in both
   runs. Timing may differ (poll staleness), but *which* mechanisms fire
   should be consistent.

## Independent Variable & Held-Constant Set

- **Independent variable**: `TELEMETRY_SOURCE` (`zmq` vs `poll`).
- **Held constant**: workload, scaling config, infrastructure, window size.

| Parameter | Value | Notes |
|---|---|---|
| Phase file | `phases_mini.json` | 2 phases: baseline (30s) + quick_stress (90s) |
| `WINDOW_S` | 10 | Default aggregation window |
| `CLIENTS` | 8 | Standard |
| `DEVICES` | 600 | Standard |
| `NODES` | 100 | Standard |
| Controller env | `current_state_integrated.env` | Golden config |
| `TELEMETRY_SOURCE` | `zmq` (Run A) / `poll` (Runs B–E) | |

## Run Matrix

| Run | `TELEMETRY_SOURCE` | `POLL_INTERVAL_S` | Phase file | Edge case tested |
|---|---|---|---|---|
| **A** (baseline) | `zmq` | — | `phases_mini.json` | Push still works |
| **B** (poll-10s) | `poll` | `10` | `phases_mini.json` | Poll at push cadence (simplest) |
| **C** (poll-5s) | `poll` | `5` | `phases_mini.json` | Dedup: interval < window. Every 2nd poll is duplicate |
| **D** (poll-30s) | `poll` | `30` | `phases_mini.json` | Stale data: controller 1–2 windows behind. RQ1 W10-Poll-30s preview |
| **E** (poll-1s) | `poll` | `1` | `phases_mini.json` | Extreme dedup: 9/10 polls duplicate. Checks for excessive logging/CPU, no `hub.sleep` drift |

## Run Configuration

Both runs use the cloud VM. The polling mechanism is already deployed in the
controller and aggregator images (no rebuild needed if images are current).

### Run A — Push baseline

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && sudo -n make setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=poll_verify_push \
  PHASES_CONFIG=testing/phases_override/phases_mini.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  CLIENTS=8 DEVICES=600 NODES=100 \
  2>&1"
```

`TELEMETRY_SOURCE` defaults to `zmq` — no env override needed.

### Run B — Poll mode

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && sudo -n make setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=poll_verify_poll \
  PHASES_CONFIG=testing/phases_override/phases_mini.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  CLIENTS=8 DEVICES=600 NODES=100 \
  TELEMETRY_SOURCE=poll POLL_INTERVAL_S=10 \
  2>&1"
```

`TELEMETRY_SOURCE` and `POLL_INTERVAL_S` must be passed through to the
controller containers. Check `run_experiment.sh` for the mechanism — may
require adding them to the controller env override file or the Makefile.

### Run C — Poll mode, faster cadence (dedup stress)

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && sudo -n make setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=poll_verify_dedup \
  PHASES_CONFIG=testing/phases_override/phases_mini.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  CLIENTS=8 DEVICES=600 NODES=100 \
  TELEMETRY_SOURCE=poll POLL_INTERVAL_S=5 \
  2>&1"
```

With `POLL_INTERVAL_S=5` and `WINDOW_S=10`, every second poll should hit
the same summary. The dedup logic must skip duplicate `window_end` values
and log `duplicate summary ... skipping`. Scaling evaluations must NOT
fire twice for the same window.

### Run D — Poll mode, stale data (30 s)

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && sudo -n make setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=poll_verify_stale \
  PHASES_CONFIG=testing/phases_override/phases_mini.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  CLIENTS=8 DEVICES=600 NODES=100 \
  TELEMETRY_SOURCE=poll POLL_INTERVAL_S=30 \
  2>&1"
```

With `POLL_INTERVAL_S=30` and `WINDOW_S=10`, the controller is always
1–2 windows behind (20–30 s staleness). This is the W10-Poll-30s condition
from the RQ1 evaluation matrix. The system must complete the run without
crashes, timeout errors, or "data too old" rejections — the controller
has no such concept; it should operate on whatever summary is available.

### Run E — Poll mode, extreme dedup (1 s)

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && sudo -n make setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=poll_verify_fast \
  PHASES_CONFIG=testing/phases_override/phases_mini.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  CLIENTS=8 DEVICES=600 NODES=100 \
  TELEMETRY_SOURCE=poll POLL_INTERVAL_S=1 \
  2>&1"
```

With `POLL_INTERVAL_S=1` and `WINDOW_S=10`, 9 out of 10 polls hit the
same summary. Checks: (a) dedup fires correctly 9× per window without
errors, (b) controller CPU/RAM is not materially higher than Run B,
(c) `duplicate summary ... skipping` log volume is manageable (not
flooding stderr), (d) `hub.sleep(1)` does not drift significantly over
the run duration.

## Focus & Evidence

### Primary — controller logs

| Artifact | What to check |
|---|---|
| `controller_lan1.log` | `polling telemetry source starting` message with correct endpoints and interval |
| `controller_lan1.log` | `new summary network=lan1 window_end=` at ~5 s intervals |
| `controller_lan1.log` | `duplicate summary ... skipping` if dedup fires (should be rare at 5s/10s) |
| `controller_lan1.log` | No `poll failed for` errors |
| `controller_lan1.log` | `Control events received types=... publishing mini-summary` — same as push run |
| `controller_lan1.log` | `Summary cache HTTP server listening on port 5558` in aggregator logs |
| `controller_lan2.log` | Same checks for LAN2 |

### Secondary — run artifacts

| Artifact | What to check |
|---|---|
| `client_requests.csv` | All phases present; failure rate comparable between runs |
| `resource_stats.csv` | Per-window rows present; `window_end` values advance |
| `container_events.csv` | Scaling events fire in both runs |
| `phases_snapshot.json` | Confirms phase structure |

### Tertiary — quick HTTP check during run

During Run B, from the cloud VM:
```bash
curl -s http://10.0.0.5:5558/latest_summary | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('window_end','empty'))"
curl -s http://10.0.1.5:5558/latest_summary | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('window_end','empty'))"
```
Both should return valid `window_end` timestamps after the first 10 s window closes.

## Metrics & Success Criteria

| # | Criterion | How checked | Pass threshold |
|---|---|---|---|
| 1 | All five runs complete all phases | `client_requests.csv` has rows for `baseline` and `quick_stress` | Both phases present in all runs |
| 2 | No poll failures | Grep `controller_lan*.log` for `poll failed` | Zero occurrences in Runs B–E |
| 3 | Poll source starts correctly | Grep for `polling telemetry source starting` | Present in both controllers in Runs B–E |
| 4 | HTTP cache serves summaries | `curl` during run returns valid JSON with `window_end` | Non-empty, valid JSON |
| 5 | Dedup: no duplicates at 10 s (Run B) | No duplicate `window_end` in `resource_stats_debug.csv` per `(network_id, window_end)` | Zero duplicates |
| 6 | Dedup: fires correctly at 5 s (Run C) | `duplicate summary ... skipping` appears in controller logs; scaling evaluations do not fire twice for same window | Duplicate-skip log present; no double-evaluation |
| 7 | Dedup: extreme at 1 s (Run E) | Same as #6; additionally controller CPU/RAM not materially higher than Run B; log volume manageable | No CPU/RAM anomaly; `duplicate summary` logs per window ≤ 18 (9 duplicates × 2 LANs) |
| 8 | Stale data tolerated (Run D) | Run completes without `poll failed`, timeouts, or transport errors | Zero errors; all phases complete despite 20–30 s staleness |
| 9 | Control events arrive | Grep `controller_lan*.log` for `drain_complete` / `rs_secondary_ready` | Present in all runs, comparable counts |
| 10 | No transport-specific crashes | All controller containers survive all runs | Exit code 0, no `SIGSEGV` or `traceback` in logs |
| 11 | Failure rate comparable | `client_requests.csv` failure % via `metrics_stats.py` | Within 2× across runs; Run D may be worse (stale data) |

## Validity Threats & Limitations

- **Short workload** — two phases may not exercise all scaling mechanisms.
  Acceptable for a smoke test; RQ1 evaluation uses the full `phases.json`.
- **Single run each** — this is a verification, not a statistical comparison.
  If any run crashes, the mechanism is broken. If all pass, RQ1 evaluation
  can proceed.
- **TELEMETRY_SOURCE env passthrough** — must verify that `run_experiment.sh`
  or the controller env override propagates `TELEMETRY_SOURCE` and
  `POLL_INTERVAL_S` to the controller containers.

## Artifact Contract

Standard run-folder layout per `testing_overview.md`:
- `client_requests.csv`, `resource_stats.csv`, `resource_stats_debug.csv`
- `per_node_stats.csv`, `container_events.csv`, `elasticity_events.csv`
- `controller_lan1.log`, `controller_lan2.log`
- `phases_snapshot.json`, `controller_env_snapshot.env`
- Aggregator logs: `aggregator_n1.log`, `aggregator_n2.log`
