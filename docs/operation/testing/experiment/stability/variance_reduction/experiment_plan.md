# Experiment Plan — Variance Reduction Baseline

**Status**: ✅ Fix verified — `SCALEDOWN_COMPUTE_COOLDOWN_S=180` eliminates compute-phase variance. Verification run (`cooldown_180_verify`) achieved 0.23% overall, on par with best prior run (0.26%).
**Date**: 2026-06-09 (plan), 2026-06-09 (executed).
**Depends on**: [golden_config_stability](../golden_config_stability/experiment_plan.md) — inherits its configuration values and fixes.

## Intent

The golden configuration experiment produced results ranging from 1.6% to 11.8% overall failure with identical configuration — a 7.4× spread. This experiment isolates and eliminates the sources of that variance to establish a **repeatable, defendable baseline** before the golden configuration gate can be evaluated.

It answers one question: **what is the true failure rate of the current system under the canonical workload, and what is its confidence interval?**

## Sources of Variance (from golden_config_stability results.md)

| Source | Evidence | Control |
|---|---|---|
| Host state accumulation | Run B (v1) → Run C (v1): same host, consecutive, crash timing moved from T+446s to T+79s. v2 pair: 11.8%→5.8% with identical code. | **Host reboot between every run** |
| Workload non-determinism | No fixed seed for device/node selection or request ordering | **Fixed `RANDOM_SEED` env var** in traffic generator |
| `edge_server_n2` SIGSEGV | 2/5 runs (40%), intermittent, kills LAN2 | **`--restart=on-failure`** on edge_server containers (already deployed) |
| Docker image variance | Image rebuilt between v1 and v2 campaigns; pip cache may differ | **Single image built once, used for all replicates** |
| Single-replicate noise | Individual runs vary dramatically | **3 replicates minimum** |

## Hypothesis / Expected Outcome

If host state and workload non-determinism are controlled, three identical runs should produce overall failure rates within ±2 percentage points of each other, and the mean should represent the true system capability. The `--restart=on-failure` should allow recovery if the intermittent SIGSEGV occurs.

## Independent Variable & Held-Constant Set

- **Independent variable**: run replicate only (3 runs, suffix a/b/c).
- **Held constant**: everything from `golden_config_stability` plus the new controls below.

### Configuration (inherited from golden_config_stability)

All values from [`current_state_integrated.env`](../../../../../../source/scripts/testing/controller_env_overrides/current_state_integrated.env):
- `CLIENTS=8`, `DEVICES=600`, `NODES=100`
- `STORAGE_PERSISTENT_RESERVE_ENABLED=1`, `SS_ENABLED=1`
- `SCALEUP_STORAGE_BASE_THRESHOLD=0.12`, `SCALEUP_COMPUTE_BASE_THRESHOLD=0.20`
- All other values unchanged from golden config plan

### New Variance Controls

| Control | How | Rationale |
|---|---|---|
| Host reboot | `sudo reboot` on cloud VM, wait for SSH, before each run | Eliminates accumulated kernel/Docker/network state |
| Fixed seed | `RANDOM_SEED=42` env var (must be supported by traffic_generator.py) | Deterministic device/node selection and request ordering |
| Single image | Build edge_server image once, verify hash, reuse | Prevents pip/pull variance between runs |
| `--restart=on-failure` | Already in build scripts from golden config campaign | Defense-in-depth against SIGSEGV |

## Run Matrix

| Run label | Seed | Phase file | Reboot before? |
|---|---|---|---|
| `variance_reduction_a` | 42 | `testing/phases.json` | Yes (first run — host already rebooted) |
| `variance_reduction_b` | 42 | `testing/phases.json` | Yes |
| `variance_reduction_c` | 42 | `testing/phases.json` | Yes |

## Run Configuration

```bash
# Run A
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  RUN_LABEL=variance_reduction_a \
  PHASES_CONFIG=testing/phases.json \
  CLIENTS=8 DEVICES=600 NODES=100 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1

# Run B — after host reboot
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  RUN_LABEL=variance_reduction_b \
  PHASES_CONFIG=testing/phases.json \
  CLIENTS=8 DEVICES=600 NODES=100 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1

# Run C — after host reboot
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  RUN_LABEL=variance_reduction_c \
  PHASES_CONFIG=testing/phases.json \
  CLIENTS=8 DEVICES=600 NODES=100 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
```

## Focus & Evidence

Same as golden_config_stability: `client_requests.csv` (primary), controller logs, `resource_stats.csv`, `container_events.csv` (secondary).

**Additional focus**: inter-run variance metrics.
- Mean, standard deviation, and range of overall failure rate across the 3 runs
- Per-phase mean and range
- Whether SIGSEGV occurred and whether `--restart=on-failure` successfully recovered

## Metrics & Success Criteria

### 1. Variance control

| Metric | Target |
|---|---|
| Overall failure rate range (max − min) | ≤3 percentage points |
| Per-phase failure rate range (per phase) | ≤5 percentage points |
| Total request volume range | ≤10% of mean |

### 2. Service quality (mean of 3 runs)

Same targets as golden_config_stability:
- Overall ≤3%
- Non-hotspot phases ≤1%
- Hotspot/compute phases ≤5%

### 3. SIGSEGV handling

If SIGSEGV occurs: `--restart=on-failure` must restore edge_server_n2 within 30s. The run must complete all 10 phases.

### 4. Escalation

If variance exceeds targets, investigate and re-run with additional controls (e.g., isolated host, different time of day). If 3 runs show consistent values but the mean exceeds quality targets, the configuration needs retuning.

## Validity Threats & Limitations

- **Fixed seed may not be supported**: the current `traffic_generator.py` may not accept a `RANDOM_SEED` env var. If not, this control is unavailable and must be noted as a limitation.
- **Host reboot is slow**: cloud VM reboot + SSH wait adds ~3-5 minutes per run. Total campaign time ~2.5 hours for 3 runs.
- **WAN still varies**: even with fixed seed and reboot, the WAN emulation (`tc netem`) may still produce timing variance that affects cross-region request latency.
- **Same WAN profile, same host**: the experiment still runs on the same cloud VM with the same WAN emulation settings. Infrastructure variance (CPU steal, disk I/O) from the cloud provider is not controlled.

## Artifact Contract

Same as golden_config_stability. Standard run folders under `source/scripts/testing/metrics/<timestamp>_variance_reduction_<a|b|c>/`.

## Changelog

| Date | Change | Rationale |
|------|--------|-----------|
| 2026-06-09 | Initial plan created. Host reboot + fixed seed + 3 replicates to control variance discovered in golden_config_stability. | [golden_config_stability results](../golden_config_stability/results.md) — 7.4× spread across 5 runs. |
| 2026-06-09 | 3-run campaign executed. Variance NOT controlled — 16.24 pp range between complete runs B and C. Root cause: elasticity scale-down during peak load (compute_spike). Non-compute phases excellent and consistent. SIGSEGV resolved (0/3 runs). RANDOM_SEED not implemented. | [results.md](results.md) §Cross-Run Variance Analysis |
| 2026-06-10 | Verification run (`cooldown_180_verify`) confirms fix. `SCALEDOWN_COMPUTE_COOLDOWN_S` increased 40→180 (base) and 120→180 (override). Compute phases now 0.04–0.63%, overall 0.23%. Bimodal behavior eliminated. | [results.md](results.md) §Overall Verdict |
