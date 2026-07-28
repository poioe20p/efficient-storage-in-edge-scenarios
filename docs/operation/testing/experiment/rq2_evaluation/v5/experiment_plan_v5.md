# Experiment Plan v5 — RQ2 Routing-Awareness Coordination Gap (Corrected Re-run)

**Status**: 📋 Planned · **Date**: 2026-07-28
**Predecessors**:
- [v3](../v3/experiment_plan_v3.md) — initial RQ2 campaign (9 runs, 3 modes × 3 reps; invalidated by architectural scoring issues)
- [v4](../v4/experiment_plan_v4.md) — warm-lease round-robin fix (negative result; revealed MAC-reuse extraction bug)
- [RQ1 v4](../../rq1_thesis_final/v4/experiment_plan_v4.md) — scoring-corrected re-run that exposed architectural issues across all experiments
**Code affected**: [`source/sdn_controller/`](../../../../source/sdn_controller/) (scoring, routing, elasticity)
**Analysis CLI**: [`source/scripts/testing/analysis/rq2/extract_spawn_metrics.py`](../../../../source/scripts/testing/analysis/rq2/extract_spawn_metrics.py)
**Campaign aggregation**: [`source/scripts/testing/analysis/rq2/campaign_analysis.py`](../../../../source/scripts/testing/analysis/rq2/campaign_analysis.py)
**Graphs output**: `docs/operation/testing/experiment/rq2_evaluation/v5/graphs/`

---

## 1. Objective

Answer: **Does spawn-time routing awareness (`topology_lifecycle`) produce faster load redistribution and better service quality than discovery-time awareness (`topology_slowstart`) or no integration (`topology_host`), under properly calibrated compute scoring?**

This is a **full re-run** of the RQ2 campaign. RQ1 v4 demonstrated that the architectural fixes (`SCALEUP_CPU_SPAN=40`, `SCALEUP_CPU_FLOOR=10`, `SCALEUP_W_STORAGE_CPU=0`, latency-only storage scoring) resolved scoring saturation that contaminated all prior experiments. While RQ2 v3 ran with corrected env values, code-level architectural issues persisted. v5 re-runs with the fully corrected codebase.

---

## 2. Motivation & Hypothesis

### 2.1 Why re-run

RQ1 v4 identified systematic issues in the scoring architecture:

| Issue | Impact on RQ2 |
|---|---|
| `SCALEUP_CPU_SPAN=5` saturated compute scoring (any ≥10% CPU → max score) | Excessive compute spawning inflated pool sizes, distorting TTFT and latency |
| `SCALEUP_W_STORAGE_CPU=0.60` → `0` (latency-only storage) | Storage spawns fired on CPU I/O noise rather than genuine DB pressure |
| Floor 3% → 10% | Noise-triggered spawns in idle/cooldown phases |
| `STORAGE_CPUS=0.10` → `0.08` | Different resource contention profile affects spawning cadence |

These were fixed in code and validated in RQ1 v4. RQ2 v3's data may reflect pre-fix code paths. v5 ensures all measurements come from the corrected architecture.

### 2.2 Hypothesis

v4's corrected extraction measured the coordination gap at 9.5 s (Slowstart 30.4 s − Lifecycle 20.9 s). v5 tests whether this gap survives under the fully corrected architecture.

| Metric | Expected (v4-corrected baseline) | Mechanism |
|---|---|---|
| **TTFT** (Time-To-First-Traffic) | host (≈10 s) < lifecycle (≈21 s) < slowstart (≈30 s) | Host round-robin at t=0; warm lease at spawn; invisible-until-discovery |
| **TFR** (Time-To-Full-Ramp) | lifecycle < slowstart | Priority window → immediate ramp vs. graduated decay |
| **Coordination-gap penalty** | TTFT(slowstart) − TTFT(lifecycle) ≥ 5 s | Minimum one extra telemetry window a separated LB waits |
| **Initial load share** | lifecycle > slowstart > host | Priority routing > graduated ramp > round-robin 1/N |
| **Non-stress latency** | lifecycle ≈ slowstart < host | Warm backends handle traffic; host thrashes cold backends |
| **Within-mode TTFT variance** | σ(host) < σ(lifecycle) < σ(slowstart) | Host deterministic; lifecycle priority-window bounded; slowstart discovery-time variable |

### 2.3 Independent Variable & Held-Constant Set

| Parameter | Value | Notes |
|---|---|---|
| **`BACKEND_SELECTION_POLICY`** | `topology_host` / `topology_slowstart` / `topology_lifecycle` | **Independent variable** |
| `SCALEUP_CPU_SPAN` | **40** | Corrected (was 5 in early experiments) |
| `SCALEUP_CPU_FLOOR` | **10** | Corrected (was 3) |
| `SCALEUP_W_STORAGE_CPU` | **0** | Latency-only storage scoring |
| `MAX_DYNAMIC_COMPUTE` | **12** | Golden config |
| `MAX_DYNAMIC_STORAGE` | **8** | Golden config |
| `WAN_RTT_MS` | 185 | RQ3-calibrated |
| `CLIENTS` | 96 | 48 per LAN |
| `CONTENT_ITEMS` | 6000 | |
| `STORAGE_CPUS` | 0.08 | RQ3-calibrated |
| `EDGE_CPUS` | 0.30 | |
| `CURL_MAX_TIME` | 30 | |
| `RANDOM_SEED` | 42 | Fixed workload sequence |
| `DATA_SEED` | 42 | Fixed content/user data. Depends on Makefile default: `SKIP_SEED` must NOT be set. |
| `SS_ENABLED` | **0** | RQ2 isolates routing from Tier 1 effects |
| Workload | `phases_rq2.json` (9-phase, two-cycle, all-local) | Canonical RQ2 phases |
| Controller env | `rq2_topology_{host,slowstart,lifecycle}.env` | Mirrors `current_state_integrated.env` + `SS_ENABLED=0` |
| `cleanup.sh` between runs | Yes | |
| Reboot between runs | Between modes only | |
| Replicates per mode | 3 | |

### 2.4 Mode Encoding

| Mode | Routing awareness | Mechanism |
|---|---|---|
| `topology_host` | Immediate (t=0) | Unknown stats → 0.0; round-robin distributes evenly |
| `topology_slowstart` | At discovery (first telemetry) | Invisible (penalty 1.0) until discovery, then graduated ramp |
| `topology_lifecycle` | At spawn time (atomic) | Warm lease with bounded priority window (45 s). Multi-lease tie-breaking: **round-robin** (parallel warm-up). See §4.6 for checkpoint protocol. |

---

## 3. Run Matrix

| # | Label | Policy | Env Override | Replicate |
|---|---|---|---|---|
| 1 | `rq2_v5_th_1` | `topology_host` | `rq2_topology_host.env` | 1 |
| 2 | `rq2_v5_th_2` | `topology_host` | `rq2_topology_host.env` | 2 |
| 3 | `rq2_v5_th_3` | `topology_host` | `rq2_topology_host.env` | 3 |
| 4 | `rq2_v5_ss_1` | `topology_slowstart` | `rq2_topology_slowstart.env` | 1 |
| 5 | `rq2_v5_ss_2` | `topology_slowstart` | `rq2_topology_slowstart.env` | 2 |
| 6 | `rq2_v5_ss_3` | `topology_slowstart` | `rq2_topology_slowstart.env` | 3 |
| 7 | `rq2_v5_tl_1` | `topology_lifecycle` | `rq2_topology_lifecycle.env` | 1 |
| 8 | `rq2_v5_tl_2` | `topology_lifecycle` | `rq2_topology_lifecycle.env` | 2 |
| 9 | `rq2_v5_tl_3` | `topology_lifecycle` | `rq2_topology_lifecycle.env` | 3 |

**Total: 9 runs.** Run order: Host×3, Slowstart×3, Lifecycle×3.
**Campaign duration**: ~5.5 hours (9 × ~30 min + cleanup/reboot overhead).

> **Lifecycle checkpoint protocol**: Each Lifecycle run uses round-robin warm-lease
> tie-breaking by default. After each Lifecycle run, a per-run checkpoint
> determines whether to continue with round-robin or switch to `max(started_ts)`
> for the remaining Lifecycle runs. Host and Slowstart modes are unaffected
> (they do not use warm leases). See §4.6.

---

## 4. Run Configuration

### 4.1 Canonical Launch Command

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=<LABEL> \
  PHASES_CONFIG=testing/phases_override/phases_rq2.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/<ENV_FILE> \
  WAN_RTT_MS=185 CLIENTS=96 CONTENT_ITEMS=6000 STORAGE_CPUS=0.08 EDGE_CPUS=0.30 \
  CURL_MAX_TIME=30 RANDOM_SEED=42 DATA_SEED=42 \
  > /tmp/<LABEL>.log 2>&1 &"
```

### 4.2 Per-Run Commands

```bash
# ── topology_host (runs 1–3) ──
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=rq2_v5_th_1 \
  PHASES_CONFIG=testing/phases_override/phases_rq2.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/rq2_topology_host.env \
  WAN_RTT_MS=185 CLIENTS=96 CONTENT_ITEMS=6000 STORAGE_CPUS=0.08 EDGE_CPUS=0.30 \
  CURL_MAX_TIME=30 RANDOM_SEED=42 DATA_SEED=42 \
  > /tmp/rq2_v5_th_1.log 2>&1 &"
# [repeat for th_2, th_3]

# ── Between-mode: cleanup + reboot ──
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && sudo -n make -C source/scripts cleanup"
ssh cloud-vm "sudo reboot"; sleep 120

# ── topology_slowstart (runs 4–6) ──
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=rq2_v5_ss_1 \
  PHASES_CONFIG=testing/phases_override/phases_rq2.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/rq2_topology_slowstart.env \
  WAN_RTT_MS=185 CLIENTS=96 CONTENT_ITEMS=6000 STORAGE_CPUS=0.08 EDGE_CPUS=0.30 \
  CURL_MAX_TIME=30 RANDOM_SEED=42 DATA_SEED=42 \
  > /tmp/rq2_v5_ss_1.log 2>&1 &"
# [repeat for ss_2, ss_3]

# ── Between-mode: cleanup + reboot ──

# ── topology_lifecycle (runs 7–9) ──
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=rq2_v5_tl_1 \
  PHASES_CONFIG=testing/phases_override/phases_rq2.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/rq2_topology_lifecycle.env \
  WAN_RTT_MS=185 CLIENTS=96 CONTENT_ITEMS=6000 STORAGE_CPUS=0.08 EDGE_CPUS=0.30 \
  CURL_MAX_TIME=30 RANDOM_SEED=42 DATA_SEED=42 \
  > /tmp/rq2_v5_tl_1.log 2>&1 &"
# [repeat for tl_2, tl_3]
```

### 4.3 Between-Run Protocol

```bash
# Between replicates (same mode): cleanup only, no reboot
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && sudo -n make -C source/scripts cleanup"

# Between modes: cleanup + reboot with Docker/OVS verification
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && sudo -n make -C source/scripts cleanup"
ssh cloud-vm "sudo reboot"
# Wait for VM to come back, then verify:
sleep 90
ssh cloud-vm "docker ps"              # Docker daemon running
ssh cloud-vm "sudo ovs-vsctl show"    # OVS bridges clear (only OVS-ken bridge, no stale ports)
# If either check fails, sleep 30 s and retry up to 3 times
```

### 4.4 Runtime Verification Gates (After Each Run Launch)

Verify config was loaded correctly at controller startup:

```bash
# Gate 1 — BACKEND_SELECTION_POLICY loaded (within 60 s of launch)
ssh cloud-vm "grep 'BACKEND_SELECTION_POLICY' ~/efficient-storage-in-edge-scenarios/source/scripts/testing/metrics/*/controller.log | tail -1"
# Expected: BACKEND_SELECTION_POLICY=<mode> (the value from the env override)

# Gate 2 — SCALEUP_CPU_SPAN=40 (not defaulting to 5)
ssh cloud-vm "grep 'SCALEUP_CPU_SPAN' ~/efficient-storage-in-edge-scenarios/source/scripts/testing/metrics/*/controller.log | tail -1"
# Expected: SCALEUP_CPU_SPAN=40

# Gate 3 — SS_ENABLED=0 (Tier 1 disabled for RQ2 isolation)
ssh cloud-vm "grep 'SS_ENABLED' ~/efficient-storage-in-edge-scenarios/source/scripts/testing/metrics/*/controller.log | tail -1"
# Expected: SS_ENABLED=0
```

### 4.5 Monitoring During Run

```bash
# Check run is alive:
ssh cloud-vm "tail -5 /tmp/rq2_v5_<mode>_<n>.log"

# Check phase progress:
ssh cloud-vm "ls -la ~/efficient-storage-in-edge-scenarios/source/scripts/testing/metrics/"

# Check completion:
ssh cloud-vm "grep -c 'phase_start\|phase_end' /tmp/rq2_v5_<mode>_<n>.log"
```

---

### 4.6 Lifecycle-Mode Per-Run Checkpoint Protocol

Lifecycle mode uses **round-robin warm-lease tie-breaking** (`selection.py`
`_claim_warm_backend()` selects `candidates[idx % len]`) by default. After
each Lifecycle run, evaluate the per-run checkpoint below. If the run fails
any criterion, **revert `selection.py` to `max(started_ts)`**, re-extract the
failed run with the corrected code, and run all remaining Lifecycle replicates
with `max(started_ts)`.

#### Checkpoint Criteria (after each `rq2_v5_tl_{n}` run completes)

Extract spawn metrics, then evaluate:

```bash
python3 source/scripts/testing/analysis/rq2/extract_spawn_metrics.py \
  source/scripts/testing/metrics/<run_folder> --mode topology_lifecycle
```

| # | Criterion | Threshold | Action if failed |
|---|-----------|-----------|-----------------|
| CP1 | No spawn starvation | All spawns: TTFT ≤ 45 s (warm-lease TTL) | Revert to `max(started_ts)` — round-robin is starving backends |
| CP2 | Lifecycle TTFT median | med ≤ 25 s | Revert — warm-lease not delivering timely first traffic |
| CP3 | Lifecycle TTFT IQR | IQR < 50 s | Revert — variance too high to trust mode comparison |

**Protocol**:

1. Run `rq2_v5_tl_1` with round-robin. Extract. Check CP1–CP3.
   - **Pass** → proceed to tl_2 with round-robin.
   - **Fail** → sync `max(started_ts)` version of `selection.py` to cloud VM, rebuild edge_server image, re-run tl_1 with `max(started_ts)`. All remaining Lifecycle runs use `max(started_ts)`.
2. Run `rq2_v5_tl_2`. Extract. Check CP1–CP3.
   - **Pass** → proceed to tl_3.
   - **Fail** → same revert + rerun protocol as step 1.
3. Run `rq2_v5_tl_3`. Extract. Check CP1–CP3.
   - **Pass** → Lifecycle mode complete with round-robin.
   - **Fail** → revert + rerun as above.

**Design rationale**: Round-robin is the sounder default (parallel warm-up
prevents seniority-based starvation). The checkpoint catches pathological
cases (runaway IQR, warm-lease window exhaustion) without pre-judging the
outcome.

---

## 5. Measurements & Success Criteria

### 5.1 Primary Artifacts (per run)

| Artifact | Description |
|---|---|
| `client_requests.csv` | All client requests: send-time, latency, status |
| `per_node_stats.csv` | 10 s window aggregates: request counts per backend |
| `container_events.csv` | Spawn/destroy events with timestamps |
| `node_lifecycle_timings.csv` | Node lifecycle: spawn, init, ready, destroy |
| `controller.log` | Controller decisions, routing events |
| `analysis/spawn_metrics.json` | Extracted TTFT, TFR, init_time, initial_share per spawn |

### 5.2 Extraction (Post-Run)

```bash
# Per run:
python3 source/scripts/testing/analysis/rq2/extract_spawn_metrics.py \
  source/scripts/testing/metrics/<run_folder> --mode <topology_mode>
```

### 5.3 Success Criteria

| # | Criterion | Threshold | Measurement |
|---|---|---|---|
| C1 | All 9 runs complete | 100% | `phases_snapshot.json` shows full 9-phase progression |
| C2 | Coordination gap ≥ 5 s | TTFT(slowstart) − TTFT(lifecycle) ≥ 5 s | `spawn_metrics.json` pooled medians |
| C3 | Lifecycle TTFT med ≤ 25 s AND Slowstart ≥ 25 s | lifecycle TTFT med ≤ 25 s, slowstart TTFT med ≥ 25 s | `spawn_metrics.json` per-mode medians |
| C4 | Lifecycle initial share > host | lifecycle med > host med | `spawn_metrics.json` `initial_share` field |
| C5 | Non-stress p50: host elevated vs lifecycle | host p50 > lifecycle p50 in cooldown phases | Per-phase `client_requests.csv` latency |
| C6 | Stress phases converge | All modes p50 within 3× in storage_storm | Per-phase `client_requests.csv` latency |
| C7 | Timeout rate ≤ 5% | All runs, all modes | `client_requests.csv` status codes |
| C8 | TTFT match rate ≥ 80% | Per-mode; MAC-reuse fix validated (v4 achieved 88%) | `spawn_metrics.json` count of valid TTFT pairs |
| C9 | Compute spawning controlled | Compare v5 spawn counts to v3. v3 env had CPU_SPAN=40 — same as v5. Differences reflect code-level changes between v3 and v5, not env drift. | `node_lifecycle_timings.csv` |
| C10 | Within-mode TTFT variance bounded | IQR(host) < IQR(lifecycle) < 50 s | `spawn_metrics.json` per-mode IQR |
| C11 | Lifecycle checkpoint passes (all 3 runs) | CP1 + CP2 + CP3 per run (see §4.6) | `spawn_metrics.json` per-run |

---

## 6. Analysis Approach

### 6.1 Comparisons

1. **TTFT by mode** — Box plot: Host vs Slowstart vs Lifecycle
2. **TFR by mode** — Box plot
3. **Initial load share** — Box plot: lifecycle > slowstart > host
4. **Per-phase p50 latency** — Grouped bar per phase per mode
5. **Percentile distribution** — p50/p95/p99 per mode
6. **Phase-type p50/p95** — Stress (storage_storm, tier1_hotspot) vs non-stress (baseline, cooldowns, demand_drop)

### 6.2 Campaign Aggregation

```bash
cd ~/efficient-storage-in-edge-scenarios
python3 source/scripts/testing/analysis/rq2/campaign_analysis.py \
  --run th_1:topology_host:source/scripts/testing/metrics/<folder_1> \
  --run th_2:topology_host:source/scripts/testing/metrics/<folder_2> \
  --run th_3:topology_host:source/scripts/testing/metrics/<folder_3> \
  --run ss_1:topology_slowstart:source/scripts/testing/metrics/<folder_4> \
  --run ss_2:topology_slowstart:source/scripts/testing/metrics/<folder_5> \
  --run ss_3:topology_slowstart:source/scripts/testing/metrics/<folder_6> \
  --run tl_1:topology_lifecycle:source/scripts/testing/metrics/<folder_7> \
  --run tl_2:topology_lifecycle:source/scripts/testing/metrics/<folder_8> \
  --run tl_3:topology_lifecycle:source/scripts/testing/metrics/<folder_9> \
  --out-dir docs/operation/testing/experiment/rq2_evaluation/v5/graphs
```

### 6.3 Expected Graphs (12)

| File | Content |
|---|---|
| `g1_ttft.png` | TTFT Distribution by Mode |
| `g2_tfr.png` | TFR Distribution by Mode |
| `g2b_ttft_vs_tfr.png` | TTFT vs TFR Scatter |
| `g3_init_time.png` | Backend Initialisation Time |
| `g4_initial_share.png` | Initial Load Share Distribution |
| `g4b_ttft_vs_share.png` | TTFT vs Initial Share |
| `g5_baseline_p50.png` | Baseline p50 Latency |
| `g5b_nonstress_p50.png` | Non-Stress p50 by Phase |
| `g6_per_phase_p50.png` | Per-Phase p50 Latency |
| `g7_percentiles.png` | Latency Percentiles p50/p95/p99 |
| `g8_phase_type_p95.png` | Phase Type p95 |
| `g8b_phase_type_p50.png` | Phase Type p50 |

---

## Appendix A — Prerequisites

- [x] `current_state_integrated.env` has CPU_SPAN=40, CPU_FLOOR=10, W_STORAGE_CPU=0, MAX_DYNAMIC_COMPUTE=12, MAX_DYNAMIC_STORAGE=8
- [x] `rq2_topology_{host,slowstart,lifecycle}.env` updated to mirror `current_state_integrated.env` + `SS_ENABLED=0` + `BACKEND_SELECTION_POLICY=<mode>`
- [x] `extract_spawn_metrics.py` has MAC-reuse fix (per-MAC window collection, `window_end >= spawn_ts` matching)
- [x] `phases_rq2.json` exists at `source/scripts/testing/phases_override/phases_rq2.json`
- [x] Cloud VM accessible via `ssh cloud-vm`
- [ ] All source code synced to cloud VM (`git pull` on cloud-vm)
- [x] Round-robin warm-lease tie-breaking active in `selection.py` (`_claim_warm_backend()` uses `controller._warm_rr_idx % len(candidates)`) — confirmed on cloud VM
- [ ] `SKIP_SEED` not set (Makefile default 0) — required for `DATA_SEED=42` to take effect

## Appendix B — Pre-Flight Checklist

```bash
# Verify cloud VM has latest code
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && git status --short"

# Verify all three env override files match golden config (excluding SS_ENABLED/BACKEND_SELECTION_POLICY)
for f in host slowstart lifecycle; do
  ssh cloud-vm "diff \
    <(grep -Ev '^#|BACKEND_SELECTION_POLICY|^SS_ENABLED' ~/efficient-storage-in-edge-scenarios/source/scripts/testing/controller_env_overrides/rq2_topology_\${f}.env | sort) \
    <(grep -v '^#' ~/efficient-storage-in-edge-scenarios/source/scripts/testing/controller_env_overrides/current_state_integrated.env | sort)"
done

# Verify phases file exists
ssh cloud-vm "ls -la ~/efficient-storage-in-edge-scenarios/source/scripts/testing/phases_override/phases_rq2.json"

# Verify extraction script has MAC-reuse fix
ssh cloud-vm "grep 'window_end >= spawn_ts' ~/efficient-storage-in-edge-scenarios/source/scripts/testing/analysis/rq2/extract_spawn_metrics.py"
```

## Appendix C — Validity Threats

| Threat | Mitigation |
|---|---|
| Code drift between local and cloud VM | Pre-flight diff check (Appendix B) |
| Scoring function not correcting spawn behavior | C9: compare v5 spawn counts to v3 |
| MAC-reuse still inflating TTFT | C8: TTFT match rate ≥ 80% |
| Between-run resource residues | `cleanup.sh` between every run |
| VM state accumulation | Reboot between modes |
| Run order effects | Fixed order: Host → Slowstart → Lifecycle |
| Round-robin may inflate Lifecycle IQR beyond acceptable bounds | v4 showed IQR 49.6 s — near but below the 50 s CP3 threshold. Per-run checkpoint (§4.6) catches violations and triggers revert to `max(started_ts)`. |

## Appendix D — Relationship to Prior Experiments

| | v3 | v4 | v5 |
|---|---|---|---|
| **What** | Initial RQ2 campaign | Warm-lease round-robin fix | Full re-run, corrected architecture |
| **Runs** | 9 new runs | 3 new Lifecycle runs | 9 new runs |
| **Key finding** | Coordination gap: 20.4 s | Fix had no effect; MAC-reuse bug discovered | Tests corrected scoring + MAC-reuse fix |
| **Status** | Invalidated | Negative result | This plan |

## Appendix E — Changelog

| Date | Change |
|------|--------|
| 2026-07-28 | Original v5 plan: data re-extraction of v3 runs (MAC-reuse fix only, no new runs) |
| 2026-07-28 | **Rewritten as full re-run**: 9 new runs with corrected architecture (CPU_SPAN=40, CPU_FLOOR=10, W_STORAGE_CPU=0), aligned `rq2_topology_*.env` files to `current_state_integrated.env`, MAC-reuse fix in extraction, same labels and config as v3 |
| 2026-07-28 | **Lifecycle checkpoint protocol added**: round-robin by default with per-run CP1–CP3 gates. Failing any gate triggers revert to `max(started_ts)` for remaining Lifecycle runs. Host and Slowstart unaffected. |