# RQ1 v7 — Forced Gap Visibility Pilot

**Status**: 📋 Planned · **Date**: 2026-07-21
**Predecessor**: [`../v5/results_v5.md`](../v5/results_v5.md) · [`../v6/experiment_plan_v6.md`](../v6/experiment_plan_v6.md)

## Intent

v5 established that the telemetry coordination gap exists at the mechanism level
(64% blind spot, 41% fewer spawns, 2.76× curl failures) but does not cause
catastrophic user-visible failure. The system's graceful degradation through
queueing absorbs the gap — requests wait longer rather than fail.

v6 tried lowering CURL_MAX_TIME to remove the queueing buffer, but cross-region
traffic was clipped in both modes equally, compressing the differential.

**v7 attacks the absorption from two independent angles:**

| Test | Mechanism | What it forces |
|------|-----------|---------------|
| **A — Cleanup Gaps** | Insert 180s low-load gaps between high-load phases | Every phase starts at zero dynamic nodes. Both modes must detect and spawn from scratch. No cross-phase carryover. |
| **B — Concurrency Limit** | `EDGE_MAX_CONCURRENT=12` semaphore per edge server | When all Flask threads are busy, new connections get 503 instead of queueing. Poll-30s has fewer edge servers → higher per-server concurrency → more 503s. |

Both tests keep everything else identical to v5 Pilot B: CLIENTS=96,
MAX_DYNAMIC_COMPUTE=12, STORAGE_CPUS=0.08, CURL_MAX_TIME=30, canonical phases
(Test B) or gap-augmented phases (Test A).

**4 runs per test, 8 total.** Push vs Poll-30s, n=2 per test.

## Hypothesis

### Test A — Cleanup Gaps

1. **Fresh start per phase**: With 180s cleanup gaps (exceeding 120s storage
   cooldown), all dynamic nodes scale down before each high-load phase. Both
   modes start each phase at zero dynamic capacity.
2. **Detection speed becomes the bottleneck**: Poll-30s needs 90s minimum to
   detect and decide; Push needs 30-50s. The ~40-60s window where Push has
   nodes and Poll-30s doesn't translates into a throughput gap.
3. **Throughput gap widens**: Without carryover nodes absorbing initial load,
   the throughput gap should return toward v4 levels (30-46%), up from v5's 20%.

### Test B — Concurrency Limit

1. **503s replace queueing**: With `EDGE_MAX_CONCURRENT=12`, when an edge
   server has 12 concurrent requests, the 13th gets an immediate 503. The
   system's queueing buffer is replaced by explicit rejection.
2. **Poll-30s hits the limit more often**: Poll-30s spawns fewer compute
   nodes → fewer total edge servers → same load concentrates on fewer servers
   → per-server concurrency is higher → more 503s.
3. **503 count becomes the gap**: The differential in 503 responses between
   Push and Poll-30s directly measures the coordination gap's user impact
   in count form, not latency percentiles.

## RQ Linkage

**Thesis RQ1**: How does telemetry delivery cadence affect reaction latency
and transient service quality during demand shifts?

**v7 contribution**: v5 proved the gap exists but is bounded by queueing.
v7 tests two independent methods of removing the queueing buffer:
- **Test A** removes the *temporal* buffer (cross-phase carryover)
- **Test B** removes the *spatial* buffer (per-server connection queueing)

If either makes the gap visible as a throughput collapse or rejection spike,
the thesis can state: "The coordination gap is bounded by two architectural
buffers — cross-phase node carryover and per-server connection queueing.
Removing either exposes the gap." If neither works, the bounding result is
even stronger: the system absorbs the gap regardless of temporal or spatial
buffers.

## Independent Variables

### Test A — Cleanup Gaps

| Parameter | v5 Pilot B | v7 Test A | Notes |
|-----------|------------|-----------|-------|
| **Telemetry mode** | Push / Poll-30s | Push / Poll-30s | Independent variable |
| **Phases** | Canonical (no gaps) | **Gap-augmented** | 180s cleanup gaps added |

### Test B — Concurrency Limit

| Parameter | v5 Pilot B | v7 Test B | Notes |
|-----------|------------|-----------|-------|
| **Telemetry mode** | Push / Poll-30s | Push / Poll-30s | Independent variable |
| **EDGE_MAX_CONCURRENT** | ∞ (unlimited) | **12** | Concurrency semaphore |

### Held Constant (Both Tests)

| Parameter | Value | Notes |
|-----------|-------|-------|
| CLIENTS | 96 | Identical to v5 Pilot B |
| MAX_DYNAMIC_COMPUTE | 12 | Identical to v5 Pilot B |
| STORAGE_CPUS | 0.08 | Identical to v5 Pilot B |
| STORAGE_MEMORY | 512m | Identical to v5 Pilot B |
| CURL_MAX_TIME | 30 | Restored from v6's 15s |
| CPU_SPAN | 40 | Identical to v5 Pilot B |
| WAN_RTT_MS | 185 | Identical to v5 Pilot B |
| Controller env | `current_state_integrated.env` | Identical to v5 Pilot B |

## Test A — Cleanup Gap Phases

### Phase Design

Two 240s cleanup gaps inserted: after `storage_storm` and after `reverse_hotspot`.
The 300s `inter_hotspot_cooldown` between `tier1_hotspot` and `reverse_hotspot`
already serves as a gap and is retained.

```
baseline (60s)
storage_storm (240s)
cleanup_gap_1 (240s)     ← NEW: force scale-down before tier1_hotspot
tier1_hotspot (180s)
inter_hotspot_cooldown (300s)  ← existing gap
reverse_hotspot (180s)
cleanup_gap_2 (240s)     ← NEW: force scale-down before compute_spike
compute_spike (180s)
demand_drop (300s)
```

**Total run duration**: 60+240+240+180+300+180+240+180+300 = 1920s = **32 min**.

**Why 240s?** The controller's `SCALEDOWN_COMPUTE_COOLDOWN_S=180` and
`SCALEDOWN_STORAGE_COOLDOWN_S=120` suppress scale-down evaluation after the
last spawn. A 240s gap provides 60s beyond the compute cooldown and 120s
beyond the storage cooldown for: sliding-window idle detection, decision
accumulation, drain signal, and container removal. Under Poll-30s, detection
of the load drop takes up to 30s, so effective margins are 30s (compute)
and 90s (storage) — tight but achievable.

### Cleanup Gap Configuration

Minimal load to maintain liveness without triggering spawns:

```json
{
  "name": "cleanup_gap_1",
  "duration_s": 180,
  "rate_per_client": 0.5,
  "cross_region_ratio": 0.0,
  "client_fraction": 0.05,
  "mix": {
    "content_lookup": 0.60,
    "feed_ranking": 0.25,
    "service_pressure": 0.15
  }
}
```

At 0.5 rps × 5% clients = negligible load. The 240s duration exceeds the
180s compute scale-down cooldown by 60s and the 120s storage scale-down
cooldown by 120s, allowing time for idle detection and container removal.

> **Canonical file note**: The project convention requires editing `phases.json`
> in place. `phases_gap.json` is an exception because Test A and Test B need
> different phase configurations simultaneously — one with gaps, one canonical.
> The run folder's `phases_snapshot.json` captures the variant used.

## Test B — Concurrency Limit

### Code Change

A `BoundedSemaphore` is added to the Flask edge server to limit concurrent
requests. When the limit is reached, new requests receive an immediate 503.

**File**: `source/docker/edge_server/source/app.py`

Add after `app = Flask(__name__)` (line 32) and before the hook registrations:

```python
import os
import threading
from flask import g, abort

_EDGE_MAX_CONCURRENT = int(os.environ.get("EDGE_MAX_CONCURRENT", "0"))
_REQUEST_SLOTS = (
    threading.BoundedSemaphore(_EDGE_MAX_CONCURRENT)
    if _EDGE_MAX_CONCURRENT > 0
    else None
)

if _REQUEST_SLOTS is not None:
    @app.before_request
    def _concurrency_gate():
        acquired = _REQUEST_SLOTS.acquire(blocking=False)
        g._slot_acquired = acquired
        if not acquired:
            abort(503, description="server at capacity")

    @app.teardown_request
    def _release_slot(exc):
        if getattr(g, "_slot_acquired", False):
            _REQUEST_SLOTS.release()
```

The env var `EDGE_MAX_CONCURRENT=0` (default) means no limit — preserving
backward compatibility. Setting it to 12 enables the semaphore.

**Docker image rebuild required** after this edit.

### Why 12?

From v6 edge server log analysis (push_1, edge_server_n1):

| Phase | Peak threads/sec | Traffic type |
|-------|-----------------|-------------|
| storage_storm | 11–14 | Cross-region (8–9s latency) |
| compute_spike | 4–8 | Local service_pressure (3ms) |

A limit of 12 means Push hovers near the limit during storage_storm 
(sporadic 503s), while Poll-30s — with fewer total edge servers — exceeds 
it more consistently (more 503s). The 503 count differential is the signal.

The 503 differential is the primary measurement for Test B. v5 had no 503s
(no concurrency limit). The expectation is that Poll-30s produces more 503s
than Push, particularly during storage_storm and tier1_hotspot where
cross-region latency creates sustained high concurrency per edge server.
compute_spike (100% service_pressure at 3ms) is unlikely to trigger the
limit in either mode.

> **503 handling verification**: Before Test B, confirm that Flask's default
> `abort(503)` produces a response the traffic generator captures in
> `client_requests.csv` with `http_status=503`. If the traffic generator
> treats non-200 responses as curl failures (http_status=0), add a custom
> error handler that returns a JSON body with status code 503:
> ```python
> @app.errorhandler(503)
> def _capacity_error(e):
>     return jsonify(error="server at capacity"), 503
> ```

## Run Matrix

### Test A — Cleanup Gaps

| # | Label | Mode | Phases |
|---|-------|------|--------|
| A1 | `rq1_v7_gap_push_1` | Push | `phases_gap.json` |
| A2 | `rq1_v7_gap_push_2` | Push | `phases_gap.json` |
| A3 | `rq1_v7_gap_poll30_1` | Poll-30s | `phases_gap.json` |
| A4 | `rq1_v7_gap_poll30_2` | Poll-30s | `phases_gap.json` |

### Test B — Concurrency Limit

| # | Label | Mode | EDGE_MAX_CONCURRENT |
|---|-------|------|---------------------|
| B1 | `rq1_v7_slot_push_1` | Push | 12 |
| B2 | `rq1_v7_slot_push_2` | Push | 12 |
| B3 | `rq1_v7_slot_poll30_1` | Poll-30s | 12 |
| B4 | `rq1_v7_slot_poll30_2` | Poll-30s | 12 |

**Total: 8 runs.** Run order: A1→A2→A3→A4 (gap tests first), then
B1→B2→B3→B4 (slot tests). Test A uses the gap phases JSON; Test B uses
the canonical phases JSON. The slot tests require the Docker image rebuild
before B1.

## Run Configuration

### Test A — Per-Run Invocation

```bash
# Push mode (A1, A2)
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=<LABEL> \
  PHASES_CONFIG=testing/phases_gap.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  WAN_RTT_MS=185 CLIENTS=96 DEVICES=6000 NODES=100 STORAGE_CPUS=0.08 \
  CURL_MAX_TIME=30 RANDOM_SEED=42 DATA_SEED=42 \
  > /tmp/<LABEL>.log 2>&1 &"

# Poll-30s mode (A3, A4) — add TELEMETRY_SOURCE and POLL_INTERVAL_S
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=<LABEL> \
  PHASES_CONFIG=testing/phases_gap.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  WAN_RTT_MS=185 CLIENTS=96 DEVICES=6000 NODES=100 STORAGE_CPUS=0.08 \
  TELEMETRY_SOURCE=poll POLL_INTERVAL_S=30 \
  CURL_MAX_TIME=30 RANDOM_SEED=42 DATA_SEED=42 \
  > /tmp/<LABEL>.log 2>&1 &"
```

### Test B — Per-Run Invocation

```bash
# Push mode (B1, B2) — canonical phases + EDGE_MAX_CONCURRENT=12
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=<LABEL> \
  PHASES_CONFIG=testing/phases.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  WAN_RTT_MS=185 CLIENTS=96 DEVICES=6000 NODES=100 STORAGE_CPUS=0.08 \
  EDGE_MAX_CONCURRENT=12 \
  CURL_MAX_TIME=30 RANDOM_SEED=42 DATA_SEED=42 \
  > /tmp/<LABEL>.log 2>&1 &"

# Poll-30s mode (B3, B4)
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=<LABEL> \
  PHASES_CONFIG=testing/phases.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  WAN_RTT_MS=185 CLIENTS=96 DEVICES=6000 NODES=100 STORAGE_CPUS=0.08 \
  TELEMETRY_SOURCE=poll POLL_INTERVAL_S=30 \
  EDGE_MAX_CONCURRENT=12 \
  CURL_MAX_TIME=30 RANDOM_SEED=42 DATA_SEED=42 \
  > /tmp/<LABEL>.log 2>&1 &"
```

> **Test B requires `EDGE_MAX_CONCURRENT` to propagate to Docker**: The
> `build_network_1.sh` / `build_network_2.sh` scripts must pass
> `-e EDGE_MAX_CONCURRENT="${EDGE_MAX_CONCURRENT:-0}"` to the
> `edge_server` container. See Prerequisites P4.

## Post-Run Workflow (per run)

Same as v5/v6: fix ownership → parse logs → M1–M9 CLIs → cleanup logs.

Additional checks for v7:

### Test A — Spawn Timing Check

```bash
# Verify no nodes were added during cleanup gaps.
python3 -c "
import csv, json
from pathlib import Path

run_dir = Path('$RUN_DIR')
with open(run_dir / 'phases_snapshot.json') as f:
    phases = json.load(f)['phases']
gap_phases = [p for p in phases if 'cleanup_gap' in p['name']]

with open(run_dir / 'node_lifecycle_timings.csv') as f:
    for row in csv.DictReader(f):
        add_ts = float(row.get('add_time', 0))
        nt = row.get('node_type', '')
        for gp in gap_phases:
            if gp['start_time'] <= add_ts <= gp['start_time'] + gp['duration_s']:
                print('WARNING: ' + nt + ' added during ' + gp['name'] + ' at t=' + str(add_ts))
print('G8 check complete')
"
```

### Test B — 503 Count

```bash
# Count 503 responses from client_requests.csv
python3 -c "
import csv
from pathlib import Path

run_dir = Path('$RUN_DIR')
total = http503 = 0
with open(run_dir / 'client_requests.csv') as f:
    for row in csv.DictReader(f):
        total += 1
        if row.get('http_status') == '503':
            http503 += 1
print(f'503s: {http503}/{total} ({http503/total*100:.2f}%)')
"
```

## Cross-Run Analysis

After all 8 runs, compare within each test:

### Test A — Throughput Gap

| Run | Mode | compute_spike reqs | tier1_hotspot reqs | reverse_hotspot reqs |
|-----|------|-------------------|--------------------|--------------------|
| A1 | Push | ? | ? | ? |
| A2 | Push | ? | ? | ? |
| A3 | Poll-30s | ? | ? | ? |
| A4 | Poll-30s | ? | ? | ? |

Expected: throughput gap ≥ 30% in at least one phase.

### Test B — 503 Count

| Run | Mode | Total 503s | 503 Rate | storage_storm 503s |
|-----|------|-----------|---------|-------------------|
| B1 | Push | ? | ?% | ? |
| B2 | Push | ? | ?% | ? |
| B3 | Poll-30s | ? | ?% | ? |
| B4 | Poll-30s | ? | ?% | ? |

Expected: Poll-30s 503 count > 2× Push.

## Primary Measurements (no gates)

v7 is exploratory. Measurements are reported, compared to v5 baselines, and
interpreted. No single measurement determines "success."

| Measurement | Test | What |
|-------------|------|------|
| Throughput gap per phase | A | Poll-30s/Push throughput in each high-load phase |
| Spawn timing relative to phase start | A | Time from phase start to first compute spawn |
| 503 count and rate | B | HTTP 503 responses per mode |
| Curl failure rate | Both | http_status=0 (curl failures) |
| Blind spot rate (M6) | Both | Breach windows unseen by controller |
| Spawn count gap (M1) | Both | Compute spawns per mode |
| Failure composition (M7) | Both | storage_bound, transient_spike, 503s |

## Pre-Run Verification Gates

| # | Gate | Test | When |
|---|------|------|------|
| G1 | `SCALEUP_CPU_SPAN=40` | Both | Pre-run |
| G2 | Controller loads `cpu_span=40` | Both | Post-run |
| G3 | `SKIP_SEED ?= 1` in Makefile | Both | Pre-run |
| G4 | `POLL_INTERVAL_S=30` (poll mode) | Both | Post-run |
| G5 | `MAX_DYNAMIC_COMPUTE=12` | Both | Pre-run |
| G6 | `phases_gap.json` has cleanup gaps | A | Pre-run |
| G7 | `phases.json` is canonical | B | Pre-run |
| G8 | No dynamic nodes during cleanup gaps | A | Post-run |
| G9 | 503s appear in client_requests.csv | B | Post-run |
| G10 | `EDGE_MAX_CONCURRENT=12` reaches Docker | B | Post-setup |

### G6 Detail

```bash
python3 -c "import json; phases=json.load(open('source/scripts/testing/phases_gap.json'))['phases']; print([p['name'] for p in phases])"
# Expected: ['baseline','storage_storm','cleanup_gap_1','tier1_hotspot','inter_hotspot_cooldown','reverse_hotspot','cleanup_gap_2','compute_spike','demand_drop']
```

### G8 Detail

```bash
python3 -c "
import csv; from pathlib import Path
run_dir = Path('$RUN_DIR')
with open(run_dir / 'node_lifecycle_timings.csv') as f:
    for row in csv.DictReader(f):
        add_ts = float(row.get('add_time', 0))
        # TBD: check add_ts against cleanup_gap phase time bounds
"
```

### G10 Detail

```bash
docker inspect edge_server_n1 --format '{{.Config.Env}}' | grep -o 'EDGE_MAX_CONCURRENT=[^ ]*'
# Expected: EDGE_MAX_CONCURRENT=12
```

## Prerequisites (Blockers)

| # | Item | Status |
|---|------|--------|
| P1 | **Create `phases_gap.json`** with cleanup gaps | ⬜ TODO |
| P2 | **Edit `app.py`**: Add concurrency semaphore | ⬜ TODO |
| P3 | **Rebuild `edge_server` Docker image** after P2 | ⬜ TODO |
| P4 | **`build_network_1.sh` / `build_network_2.sh`**: Pass `EDGE_MAX_CONCURRENT` to static edge_server containers | ⬜ TODO |
| P5 | **`compute_node_manager.py`**: Pass `EDGE_MAX_CONCURRENT` to dynamically-spawned edge_server containers | ⬜ TODO |
| P6 | **Verify 503 handling**: Confirm `abort(503)` is captured in `client_requests.csv` | ⬜ TODO |
| P7 | 6 RQ1 analysis CLIs (M2–M9) | ✅ Implemented |
| P8 | VM capacity (unchanged from v5, no new concerns) | ✅ Verified |

### P1 Detail — phases_gap.json

Copy canonical `phases.json` → `phases_gap.json`. Insert two cleanup gap phases
after `storage_storm` and after `reverse_hotspot` (before their respective
next high-load phases). The `inter_hotspot_cooldown` already serves as a gap
between tier1_hotspot and reverse_hotspot.

Cleanup gap phase definition:
```json
{
  "name": "cleanup_gap_1",
  "duration_s": 180,
  "rate_per_client": 0.5,
  "cross_region_ratio": 0.0,
  "client_fraction": 0.05,
  "mix": {
    "content_lookup": 0.60,
    "feed_ranking": 0.25,
    "service_pressure": 0.15
  }
}
```

Use the same definition for `cleanup_gap_2`. The load is too low to trigger
any spawning but keeps client connections alive.

### P2 Detail — app.py Edit

Add concurrency semaphore to `source/docker/edge_server/source/app.py`:

```python
# Insert after line 32 (app = Flask(__name__)), before line 36
# (register_pre_telemetry_request_hooks)

import os
import threading

_EDGE_MAX_CONCURRENT = int(os.environ.get("EDGE_MAX_CONCURRENT", "0"))
_REQUEST_SLOTS = (
    threading.BoundedSemaphore(_EDGE_MAX_CONCURRENT)
    if _EDGE_MAX_CONCURRENT > 0
    else None
)

if _REQUEST_SLOTS is not None:
    @app.before_request
    def _concurrency_gate():
        acquired = _REQUEST_SLOTS.acquire(blocking=False)
        g._slot_acquired = acquired
        if not acquired:
            abort(503, description="server at capacity")

    @app.teardown_request
    def _release_slot(exc):
        if getattr(g, "_slot_acquired", False):
            _REQUEST_SLOTS.release()
```

The `teardown_request` always runs (even after `abort(503)` in `before_request`).
The `g._slot_acquired` guard prevents double-release on rejected requests.

When `EDGE_MAX_CONCURRENT=0` (default, or unset), no semaphore is created —
behavior is identical to current code. This preserves backward compatibility
for all other experiments.

### P4 Detail — build_network Scripts

Add to the `docker run` command for all `edge_server` containers in
`build_network_1.sh` and `build_network_2.sh`:
```bash
-e EDGE_MAX_CONCURRENT="${EDGE_MAX_CONCURRENT:-0}"
```

This covers the 2 static edge servers. Dynamic edge servers are handled by P5.

### P5 Detail — compute_node_manager.py

**File**: `source/sdn_controller/elasticity/compute_node_manager.py`

In the `_docker_run_server` method, add to the list of `-e` flags:
```python
"-e", f"EDGE_MAX_CONCURRENT={os.environ.get('EDGE_MAX_CONCURRENT', '0')}",
```

Without this, only the 2 static edge servers get the semaphore — dynamically-
spawned edge servers (up to 12 per LAN during the run) would have unlimited
concurrency, collapsing Test B's signal.

### P6 Detail — 503 Handling Verification

Before any Test B runs, verify 503s are captured correctly:

1. Launch a 60s smoke test at 96 clients with `EDGE_MAX_CONCURRENT=1`
   (trivially low — nearly every request should get 503).
2. Check `client_requests.csv` for rows with `http_status=503`.
3. If 503s appear as `http_status=0` (curl treats non-200 as failure),
   add a custom Flask error handler:
   ```python
   @app.errorhandler(503)
   def _capacity_error(e):
       return jsonify(error="server at capacity"), 503
   ```
   This returns a proper HTTP 503 with JSON body, which Flask's test client
   and most HTTP clients record with the correct status code.
4. Rebuild and re-test until 503s are captured with `http_status=503`.

## Validity Threats & Limitations

| Threat | Mitigation |
|--------|------------|
| **Test A**: Cleanup gaps insufficient duration | 240s exceeds SCALEDOWN_COMPUTE_COOLDOWN_S=180 by 60s and SCALEDOWN_STORAGE_COOLDOWN_S=120 by 120s. G8 verifies no dynamic nodes exist during gaps. |
| **Test A**: Gaps change total run duration from 24→32 min | Longer run means more total requests, potentially more noise. Absolute throughput per phase is unchanged (180s each). |
| **Test A**: Low-load gaps may still trigger occasional spawns | If system noise triggers a spawn during a gap, the node would be online when the next phase starts — defeating the gap. Gate G8 verifies this didn't happen. |
| **Test B**: Semaphore value of 12 too high or too low | From log analysis, 11–14 threads/sec during storage_storm. 12 puts Push at the boundary. If both modes produce zero 503s, the value is too high. If both produce many, it's too low. The differential matters, not the absolute count. |
| **Test B**: Semaphore only matters during slow-traffic phases | compute_spike is 100% service_pressure (3ms) — concurrency never reaches 12. The 503 differential will appear in storage_storm and tier1_hotspot, where cross-region latency is high. This is acceptable: the gap should be visible where routing staleness matters most. |
| **Test B**: `teardown_request` / `g` interaction with existing hooks | Flask runs `before_request` hooks in registration order and `teardown_request` hooks in reverse registration order. The semaphore hooks are registered first (before existing hooks), so they run first on request entry and last on exit. `g._slot_acquired` is safe because Flask's `g` is thread-local. |
| **Test B**: Dynamic edge servers may not inherit `EDGE_MAX_CONCURRENT` | Addressed by P5 (edit `compute_node_manager.py`). Verification: after the first Test B run, check `docker inspect` on a dynamic edge server to confirm the env var is present. |
| n=2 per test per mode | Low statistical power. Both tests are exploratory — no formal pass/fail gates. |
| Run order (Test A first, then Test B) | Test B requires Docker rebuild (P3). Running Test A first avoids an extra rebuild cycle. VM performance drift across runs accepted. |

## Artifact Contract

Standard run-folder layout from `docs/operation/testing/testing_overview.md`.

### New Artifacts for v7

| Artifact | Location | Purpose |
|----------|----------|---------|
| `phases_gap.json` | `source/scripts/testing/` | Test A phase config with cleanup gaps |
| Modified `app.py` | `source/docker/edge_server/source/` | Test B concurrency semaphore |

## Graph Summary

| # | Graph | Test | Data Source |
|---|-------|------|-------------|
| G1 | Throughput by phase (gap vs v5) | A | `client_requests.csv` |
| G2 | Spawn timing vs phase start | A | `node_lifecycle_timings.csv` |
| G3 | 503 count per phase per mode | B | `client_requests.csv` (http_status=503) |
| G4 | Curl failure rate (both tests vs v5) | Both | `client_requests.csv` (http_status=0) |
| G5 | Blind spot rate | Both | `analysis/rq1/rq1_blind_spot_windows.csv` |
| G6 | Failure composition (with 503s) | B | M7 CSV + 503 count |

## Changelog

| Date | Change |
|------|--------|
| 2026-07-21 | v7 pilot plan created. Two independent tests: A (cleanup gaps, 240s to exceed SCALEDOWN_COMPUTE_COOLDOWN_S=180) and B (EDGE_MAX_CONCURRENT=12 semaphore). 4 runs per test, 8 total. All other params = v5 Pilot B. CURL_MAX_TIME=30s restored. No pass/fail gates. P5 (compute_node_manager.py) and P6 (503 handling) added after reviewer pass. |
