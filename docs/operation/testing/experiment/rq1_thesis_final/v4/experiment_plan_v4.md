# RQ1 v4 — Scoring-Corrected Re-run

**Status**: 📋 Planned · **Date**: 2026-07-19
**Parent plan**: [`experiment_plan_v3.md`](../rq1_thesis_final/experiment_plan_v3.md) — v3 (executed 2026-07-03, analysis 2026-07-04)
**Predecessor results**: [`results_v3.md`](../rq1_thesis_final/results_v3.md)

## Intent

RQ3 v4 validation revealed that `SCALEUP_CPU_SPAN=5` saturated the compute
scoring function — any node at ≥10% CPU received the maximum compute score
of 0.60. This caused **uncontrolled compute spawning** in every prior RQ1
run. The controller spawned compute nodes whenever any edge server touched
10% CPU, regardless of actual need.

The v3 RQ1 campaign produced two headline findings:

| Finding                                                          | Trust status after CPU_SPAN=5 discovery                                                                             |
| ---------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| Timeout rate: Poll-30s 4.3× higher than Push                    | **Directionally correct** (blind spot → more timeouts), but magnitude unreliable                             |
| Bimodality: runs split into healthy (~2%) and degraded (10–35%) | **Now untrustworthy** — the saturated spawn loop may have randomly reached enough servers to survive, or not |
| Reaction latency monotonic: Push < Poll-5s < Poll-12s < Poll-30s | **Directionally correct**, but detection segment inflated by excessive spawning activity                      |
| Staleness step-function: Push ~0s, Poll-30s ~10s                 | **Trustworthy** — staleness is a property of the aggregation pipeline, not the scoring function              |
| All 4 mechanisms exercise                                        | **Trustworthy** — mechanism exercise is infrastructure-level, not scoring-level                              |

This v4 re-run targets the two **endpoint modes** (Push and Poll-30s) at
n=3 replicates each under the corrected scoring function (`SCALEUP_CPU_SPAN=40`)
to answer: **does the coordination gap survive a properly calibrated trigger?**

## Hypothesis / Expected Outcome

1. **The coordination gap persists**: Poll-30s produces higher timeout rates
   and slower reaction latency than Push, even with calibrated scoring. The
   direction is preserved; the magnitude may differ from v3.
2. **Bimodality resolves or is reduced**: With controlled compute spawning,
   within-mode variance decreases. If bimodality persists with CPU_SPAN=40,
   it is genuinely a system phase transition, not an artifact of the
   saturated spawn loop. If it disappears, the v3 bimodality was an artifact.

## Independent Variable & Held-Constant Set

| Parameter                              | Value                            | Notes                                                                                                                                                                                                                     |
| -------------------------------------- | -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Telemetry mode**               | Push / Poll-30s                  | **Independent variable** — endpoints only                                                                                                                                                                          |
| `SCALEUP_CPU_SPAN`                   | **40**                     | **Corrected** — was 5 in v3                                                                                                                                                                                        |
| `RANDOM_SEED`                        | 42                               | Fixed workload sequence (unchanged from v3)                                                                                                                                                                               |
| `DATA_SEED`                          | 42                               | **New** — fixed content/user data seeding                                                                                                                                                                          |
| `WAN_RTT_MS`                         | 185                              | RQ3-calibrated (was 200 in v3)                                                                                                                                                                                            |
| `VIP_HARD_TIMEOUT`                   | 60                               |                                                                                                                                                                                                                           |
| `CURL_MAX_TIME`                      | 30                               |                                                                                                                                                                                                                           |
| `CLIENTS`                            | 48                               |                                                                                                                                                                                                                           |
| `DEVICES`                            | 6000                             |                                                                                                                                                                                                                           |
| `NODES`                              | 100                              |                                                                                                                                                                                                                           |
| `STORAGE_CPUS`                       | 0.08                             | RQ3-calibrated (was 0.10 in v3)                                                                                                                                                                                           |
| `SS_ENABLED`                         | 1                                |                                                                                                                                                                                                                           |
| `STORAGE_PERSISTENT_RESERVE_ENABLED` | 1                                |                                                                                                                                                                                                                           |
| Workload                               | 7-phase mixed                    | Canonical`source/scripts/testing/phases.json` (RQ3-updated; `compute_spike` uses `service_pressure`)                                                                                                                |
| Controller env                         | `current_state_integrated.env` | RQ3-calibrated: CPU span 5→40, floor 3%→10%, W_CPU 0.40→0.60, W_STORAGE_CPU 0.60→0 (latency-only). MAX_DYNAMIC_STORAGE=8, MAX_DYNAMIC_COMPUTE=8 (RQ3 validated self-regulation at 20; 8 is sufficient for RQ1 scale). |
| `cleanup.sh -r` between runs         | Yes                              |                                                                                                                                                                                                                           |
| Reboot between runs                    | Yes                              |                                                                                                                                                                                                                           |
| Replicates per mode                    | 3                                |                                                                                                                                                                                                                           |

> **Why Push + Poll-30s only?** Poll-5s and Poll-12s established the ordinal
> relationship in v3 (monotonic: Push < Poll-5s < Poll-12s < Poll-30s). The
> question now is whether the gap exists *at all* under calibrated scoring.
> If Push and Poll-30s differ, we can re-add the intermediate points later.
> If they don't differ, the intermediate points are moot.

## Run Matrix

| # | Label               | `TELEMETRY_SOURCE` | `POLL_INTERVAL_S` | `RANDOM_SEED` | `DATA_SEED` |
| - | ------------------- | -------------------- | ------------------- | --------------- | ------------- |
| 1 | `rq1_v4_push_1`   | `zmq`              | —                  | 42              | 42            |
| 2 | `rq1_v4_push_2`   | `zmq`              | —                  | 42              | 42            |
| 3 | `rq1_v4_push_3`   | `zmq`              | —                  | 42              | 42            |
| 4 | `rq1_v4_poll30_1` | `poll`             | 30                  | 42              | 42            |
| 5 | `rq1_v4_poll30_2` | `poll`             | 30                  | 42              | 42            |
| 6 | `rq1_v4_poll30_3` | `poll`             | 30                  | 42              | 42            |

**Total: 6 runs.** Run order: Push_1→2→3, Poll-30s_1→2→3.
**Campaign duration**: ~3 hours (6 × ~28 min + cleanup/reboot overhead).

## Run Configuration

### Per-Run Protocol

For each of the 6 runs:

```bash
# 1. Launch
ssh -o ServerAliveInterval=60 cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=<LABEL> \
  PHASES_CONFIG=testing/phases.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  WAN_RTT_MS=185 CLIENTS=48 DEVICES=6000 NODES=100 STORAGE_CPUS=0.08 \
  CURL_MAX_TIME=30 RANDOM_SEED=42 DATA_SEED=42 \
  > /tmp/<LABEL>.log 2>&1 &"

# 2. Wait for completion (~28 min)

# 3. Post-run analysis (see below)

# 4. Cleanup + reboot:
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && sudo bash source/scripts/cleanup.sh -r"
ssh cloud-vm "sudo reboot"
# Wait ~90s for VM to come back
```

### Mode-Specific Flags

| Mode     | Extra`make` flags                          |
| -------- | -------------------------------------------- |
| Push     | *(none — zmq is default)*                 |
| Poll-30s | `TELEMETRY_SOURCE=poll POLL_INTERVAL_S=30` |

### Pre-Run Verification Gates

**Gate 1 — Env file has corrected span:**

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  grep 'SCALEUP_CPU_SPAN' source/scripts/testing/controller_env_overrides/current_state_integrated.env"
# Expected: SCALEUP_CPU_SPAN=40
```

**Gate 2 — Controller actually loaded the value at runtime (not just file presence):**
After launching the first run, wait ~60s for the controller to start, then:

```bash
ssh cloud-vm "grep 'ScalingPolicy.*init\|cpu_span' \
  ~/efficient-storage-in-edge-scenarios/source/scripts/testing/metrics/*/controller_lan1.log 2>/dev/null | head -3"
# Expected: a log line showing cpu_span=40 (or SCALEUP_CPU_SPAN=40) in the loaded config dump
```

If the controller log shows `cpu_span=5` or `cpu_span=10` (the default), **stop** — the env override is not being sourced correctly.

**Gate 3 — DATA_SEED propagation:**
The `setup_test_data` Makefile target passes `--data-seed $(DATA_SEED)` to both
`seed_content_items.py` and `seed_user_profiles.py`. This is the canonical
seeding path. However, `run_experiment.sh`'s internal `run_seed()` also calls
these scripts but does **not** pass `--data-seed`. This is safe because
`SKIP_SEED ?= 1` in the Makefile skips the internal seeding — the
`setup_test_data` seeding survives. Verify this dependency holds:

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  grep 'SKIP_SEED' source/scripts/Makefile"
# Expected: SKIP_SEED ?= 1
```

If `SKIP_SEED` is ever set to 0, the deterministically-seeded data will be
silently overwritten with unseeded random data. Do not change this default.

**Gate 4 — POLL_INTERVAL_S not silently defaulting to 10 s:**
`main_n1.py` and `main_n2.py` default `POLL_INTERVAL_S` to 10 s if the env var
is unset. A Poll-30s run with a missing `POLL_INTERVAL_S=30` flag silently
becomes Poll-10s. After launching a poll-mode run, verify:
```bash
ssh cloud-vm "grep 'POLL_INTERVAL_S\|poll_interval' \
  ~/efficient-storage-in-edge-scenarios/source/scripts/testing/metrics/*rq1_v4_poll30*/controller_lan1.log 2>/dev/null | head -3"
# Expected: POLL_INTERVAL_S=30 (or poll_interval=30) in the loaded config
```
If the log shows `POLL_INTERVAL_S=10` or `poll_interval=10`, **stop** — the
flag was not passed correctly and the run is invalid.

### Post-Run Workflow (per run)

Identical to v3. Use the reusable `~/post_run.sh` script on the cloud VM:

```bash
RUN_DIR="source/scripts/testing/metrics/<timestamp>_<label>"

# Fix ownership
sudo chown -R testop:testop "$RUN_DIR"

# Parse controller logs → elasticity events
python3 source/scripts/tools/parse_elasticity_logs.py \
  "$RUN_DIR/controller_lan1.log" "$RUN_DIR/controller_lan2.log" \
  -o "$RUN_DIR/elasticity_events.csv" \
  --timings-output "$RUN_DIR/node_lifecycle_timings.csv"

# RQ1 analysis CLIs
python3 -m source.scripts.testing.analysis.rq1.cli.timings --run-dir "$RUN_DIR"
python3 -m source.scripts.testing.analysis.rq1.cli.overhead --run-dir "$RUN_DIR"
python3 -m source.scripts.testing.analysis.rq1.cli.decision_quality --run-dir "$RUN_DIR"

# Cleanup large artifacts
rm "$RUN_DIR/controller_lan1.log" "$RUN_DIR/controller_lan2.log"
rm -rf "$RUN_DIR/service_logs/"
```

Then `scp` the run folder to local:

```powershell
scp -r "cloud-vm:~/efficient-storage-in-edge-scenarios/$RUN_DIR" "C:\...\source\scripts\testing\metrics\"
```

## CSV Schema

Same v3 schema — `sent_at` column, `phase` captured at send-time:

```
sent_at, phase, client_ns, client_lan, endpoint, content_id, user_id,
target_region, http_status, latency_s, completed_at
```

## Focus & Evidence

| Artifact                              | What it shows                                                    | Priority                                              |
| ------------------------------------- | ---------------------------------------------------------------- | ----------------------------------------------------- |
| `client_requests.csv`               | Per-phase failure rate (send-time bucketed), latency percentiles | **Primary**                                     |
| `analysis/rq1_reaction_latency.csv` | Breach-to-spawn latency, segmented into detection + provisioning | **Primary**                                     |
| `analysis/rq1_staleness.csv`        | Information age per mode                                         | Secondary (trusted from v3)                           |
| `elasticity_events.csv`             | Scaling event count and timing                                   | **Primary** — did CPU_SPAN=40 reduce spawning? |
| `node_lifecycle_timings.csv`        | Container spawn/stop counts by type                              | **Primary** — compare compute spawns vs v3     |
| `resource_stats.csv`                | Storage/server count, CPU/RAM per phase                          | Secondary                                             |
| `phases_snapshot.json`              | Phase order, durations, request mix                              | Reference                                             |

**Primary focus**: Compare compute spawn counts and timeout rates against v3.
The key question is whether the bimodal split persists under calibrated scoring.

## Metrics & Success Criteria

| #  | Criterion                      | Expectation                                                                                                                                                                                                                                                                                      |
| -- | ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| C1 | All 6 runs complete            | 6/6 → idle, zero controller tracebacks                                                                                                                                                                                                                                                          |
| C2 | Coordination gap persists      | Poll-30s timeout rate > Push timeout rate (direction preserved)                                                                                                                                                                                                                                  |
| C3 | Reaction latency gap persists  | Poll-30s reaction latency > Push reaction latency                                                                                                                                                                                                                                                |
| C4 | Compute spawning is controlled | Compute spawn count per run is**lower** than v3 (no uncontrolled 10%-CPU triggers)                                                                                                                                                                                                         |
| C5 | Bimodality assessment          | If σ(timeout_rate) within each mode drops below**3 percentage points** (v3 was 7.2% Push, 9.1% Poll-30s), the v3 bimodality was an artifact of CPU_SPAN=5. If σ remains above 5pp, bimodality is genuine system non-determinism. Between 3–5pp: inconclusive — more replicates needed. |
| C6 | Staleness step-function        | Push ~0s, Poll-30s ~10s (window-gated) — should be unchanged from v3                                                                                                                                                                                                                            |
| C7 | Latency uncensored             | p95 ok_latency reflects true cross-region response times, not artificial cap (CURL_MAX_TIME=30). Re-verified under corrected scoring.                                                                                                                                                            |
| C8 | All 4 mechanisms exercise      | Storage scale-out, compute scale-up, Tier 1 selective sync, reserve activation in all 6 runs                                                                                                                                                                                                     |

## Post-Completion: Comparison with v3

After all 6 runs are analyzed, produce a focused comparison table:

| Metric                                                         | v3 Push (n=3) | v4 Push (n=3) | v3 Poll-30s (n=3) | v4 Poll-30s (n=3) |
| -------------------------------------------------------------- | ------------- | ------------- | ----------------- | ----------------- |
| Timeout rate (μ ± σ)                                        | 5.9 ± 7.2%   | ?             | 25.5 ± 9.1%      | ?                 |
| Reaction latency (μ)                                          | 33.2 s        | ?             | 75.7 s            | ?                 |
| Compute nodes spawned (μ, from`node_lifecycle_timings.csv`) | 18.3          | ?             | 8.7               | ?                 |
| Storage nodes spawned (μ, from`node_lifecycle_timings.csv`) | 15.3          | ?             | 15.0              | ?                 |
| Max storage count (from`resource_stats.csv`)                 | 7–8          | ?             | 8                 | ?                 |
| Max server count (from`resource_stats.csv`)                  | 5             | ?             | 4                 | ?                 |

## Validity Threats & Limitations

| Threat                                       | Mitigation                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| CPU_SPAN=5 artifact in v3                    | Corrected to 40 — but we have no intermediate calibration. 40 was validated in RQ3 v4 runs; whether it's the*optimal* value is undetermined                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| Only endpoint modes tested                   | If the gap disappears at the endpoints, Poll-5s and Poll-12s are irrelevant. If it persists, we can re-add them as a follow-up.**Caveat**: if CPU_SPAN=40 changes the system's response curve nonlinearly (e.g., the gap only appears above some cadence threshold), the intermediate points might reveal behavior the endpoints miss. This risk is accepted for now.                                                                                                                                                                                                                                                                                                                                                                       |
| STORAGE_CPU_SPAN still at 5                  | Storage nodes may still spawn aggressively. Note that the actual reason this is harmless is that`SCALEUP_W_STORAGE_CPU=0` — the CPU component has zero weight in the storage degradation score, so the span is multiplied by zero regardless of its value. If future experiments set `W_STORAGE_CPU > 0`, the storage span must also be corrected.                                                                                                                                                                                                                                                                                                                                                                                           |
| DATA_SEED=42 is new                          | v3 used only RANDOM_SEED=42 for traffic, but content/user data seeding was not seeded.**(a)** This means v4 runs have identical content distributions across all 6 runs — a strict improvement over v3. **(b)** However, it also means the v4 content distribution may differ from any specific v3 run's distribution. Direct v3→v4 comparison of timeout rates and reaction latency is therefore confounded: a change could be due to the scoring fix, different content placement, or both. **Mitigation**: compare v3→v4 *within-mode variance* (σ) rather than *point estimates* (μ). The σ reduction is the primary bimodality test; it is less sensitive to content distribution differences than the μ shift. |
| n=3 per mode                                 | Same statistical power as v3. With v3 σ of 7–9pp, a 10pp between-mode difference has pooled SE ≈ 6.5pp and t ≈ 1.5 (df≈4) — not significant at α=0.05. The experiment may fail to detect a genuine coordination gap due to limited power. This is accepted as a constraint of the 6-run scope; adding replicates is deferred to a follow-up if results are borderline.                                                                                                                                                                                                                                                                                                                                                                     |
| Blocked run order (Push×3 then Poll-30s×3) | If the VM's performance drifts over the ~3h campaign (thermal throttling, hypervisor load), the mode effect is confounded with time. v3 used the same order, so v3→v4 within-mode comparisons are consistent. Acknowledged as a limitation. |
| Sliding-window wall-clock duration triples in Poll-30s | Scale-up windows are defined in *window counts* (5 windows, 3 hits for compute). In Push (10 s/window) this spans ~50 s; in Poll-30s (30 s/poll) it spans ~150 s — a 3× compound effect beyond simple data freshness. The experiment measures the **compound** coordination gap (delivery cadence × decision latency), not pure delivery cadence. This is the real architectural property — separated monitoring systems compound both dimensions. Documented explicitly. |
| Dead-node detection takes 3× longer in Poll-30s | TELEMETRY_TIMEOUT_WINDOWS=18 means 18 consecutive absent windows before node removal: 180 s Push vs 540 s Poll-30s. If a node crashes during a load spike, Push recovers capacity 3× faster. This is a secondary mechanism that compounds with the primary delivery gap. |
| VIP routing uses up to 30 s-stale server stats in Poll-30s | _server_stats (used by VIP routing WSM cost functions) and peer summaries (used for cross-LAN scale-up relief) are refreshed only when telemetry arrives. In Poll-30s, routing decisions may use up to 30 s-stale data, potentially sending disproportionate traffic to overloaded servers. This adds a routing-quality dimension to the measured effect. |'s performance drifts over the ~3h campaign (thermal throttling, hypervisor load), the mode effect is confounded with time. v3 used the same order, so v3→v4 within-mode comparisons are consistent. Acknowledged as a limitation.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |

## Changelog

| Date       | Change                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 2026-07-19 | Plan created. Changes from v3: (1) only Push + Poll-30s (endpoints only), (2) SCALEUP_CPU_SPAN=40 (corrected from 5), (3) DATA_SEED=42 (new — seeded content/user data), (4) n=6 runs (was 12).                                                                                                                                                                                                                                                                                                                                                                                           |
| 2026-07-19 | **Review corrections** (Reviewer agent): added runtime controller log verification for CPU_SPAN load (Gate 2); documented DATA_SEED propagation dependency on SKIP_SEED=1 (Gate 3); fixed STORAGE_CPU_SPAN=5 reasoning (actual reason: W_STORAGE_CPU=0); acknowledged cross-campaign comparison confound from DATA_SEED; restored C7 (latency uncensored); added quantitative bimodality threshold (σ < 3pp = resolved, > 5pp = genuine); added blocked run order and statistical power limitations to validity threats; clarified compute spawn metric source in comparison table. |
| 2026-07-19 | **Code audit findings** (SDN controller audit): added Gate 4 — verify POLL_INTERVAL_S=30 at runtime (silent 10 s default risk); added 3 validity threats: (1) sliding-window wall-clock duration triples in Poll-30s (compound delivery cadence × decision latency), (2) dead-node detection takes 3× longer (540 s vs 180 s), (3) VIP routing uses up to 30 s-stale server stats in Poll-30s. These are real secondary mechanisms that compound the coordination gap beyond simple data freshness. |
| 2026-07-20 | **V4 campaign executed and analyzed** (12 runs, expanded from planned 6): Push×3, Poll-5s×3, Poll-12s×3, Poll-30s×3. All runs completed. Bimodality resolved (σ < 0.5pp vs v3's 7–12pp) — confirmed artifact of CPU_SPAN=5. Coordination gap in timeout rate reduced by ~98% (1.2% Push vs 1.6% Poll-30s). Threshold cliff in elasticity behavior identified between Poll-12s and Poll-30s (compute spawns drop 52%). Results in [`results_v4.md`](results_v4.md). |
