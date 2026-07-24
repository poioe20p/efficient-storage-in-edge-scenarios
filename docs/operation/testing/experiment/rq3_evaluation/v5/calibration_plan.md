# RQ3 v2 — Trigger Divergence Calibration

**Date**: 2026-07-24
**Status**: 📋 Partially Executed — main divergence calibration (6 runs) complete, storage CPU weight probe pending
**Depends on**: G0-v6 resource validation (complete — 0.08/0.25 CPUs at 96 clients, WAN=185 produces clear pre→post improvement)
**Purpose**: Verify that the G0-v6 scoring thresholds (floors, spans, base thresholds) produce behavioural divergence when the three RQ3 trigger weight configurations are applied.
**Supersedes**: The concrete thresholds in this plan supersede the (TBD) markers in `rq3_setup_v2.md` §3.2 and §4.2 for calibration purposes. The setup doc will be finalised after this calibration produces the definitive values.

---

## 1. Intent

RQ3 compares three trigger compositions — `degradation_score` (cross-signal
confirmation), `cpu_only` (industry default), `latency_only` (user-experience
dimension) — with **identical floors, spans, thresholds, and window
parameters**. Only the four weight variables differ. The comparison is only
meaningful if the three modes produce **different** behaviour under the same
conditions.

**What is being tested**: The G0-v6 thresholds (`CPU_FLOOR=10`, `CPU_SPAN=40`,
`T_PROC_FLOOR=25`, `T_PROC_SPAN=80`, `BASE_THRESHOLD=0.18` for compute;
`STORAGE_CPU_FLOOR=1.5`, `T_DB_FLOOR=60`, `T_DB_SPAN=250`,
`STORAGE_BASE_THRESHOLD=0.35` for storage) were calibrated for the
`degradation_score` weight configuration. This calibration tests whether
these same thresholds also produce behavioural divergence when the weights
change to `cpu_only` (1.00/0.00) and `latency_only` (0.00/1.00).

The weights are different by design — that is RQ3's independent variable.
The question is whether the **common non-weight parameters** (floors, spans,
base thresholds) create a parameter region where the three weight
configurations produce observably different spawn counts and score component
distributions.

**How we got here**: G0-v6 validated the resource configuration at 0.08/0.25
CPUs with 96 clients and WAN=185 ms (compute_spike CPU drops 23–28pp
pre→post, storage T_db shows measurable improvement, storage scoring loop
closes at τ=0.35). The G0 series (v1→v6) progressively refined the resource
config from the original Phase 1a calibration space (C4 at 0.04/0.06 CPUs,
WAN=260 ms) to the current tighter-but-stable operating point. G0-v6 is the
canonical resource baseline for this calibration.

This calibration answers a single yes/no question: **do the G0-v6 thresholds
make the three weight configurations diverge?** If yes, the 9-run evaluation
can proceed immediately. If no, the calibration identifies which parameter is
compressing the behavioural space and in which direction to adjust it.

This is **6 runs (2 per mode), not a campaign**. The output is a go/no-go decision with
parameter adjustment guidance if needed. Two replicates per mode provide a
basic consistency check: if the two replicates disagree, the mode's behaviour
is dominated by noise and the divergence signal is unreliable.

---

## 2. Hypothesis / Expected Outcome

### 2.1 If the G0-v6 thresholds are in the "divergence zone"

| Metric | `degradation_score` | `cpu_only` | `latency_only` |
|---|---|---|---|
| Baseline FP spawns | Near-zero (0–1) | Higher (CPU spikes without latency confirmation) | Higher (latency spikes without CPU confirmation) |
| storage_storm spawns | Fires — both CPU and T_db elevate | Fires — CPU alone crosses threshold, possibly more spawns | Fires — T_db alone crosses threshold |
| compute_spike spawns | Fires — both CPU and T_proc elevate | Fires — CPU alone crosses threshold | Fires — T_proc alone crosses threshold |
| Score composition (G8) | Both components contribute | Only CPU component non-zero | Only latency component non-zero |

The three modes should produce **visibly different spawn counts and score
component distributions** — not three copies of the same outcome.

### 2.2 If the G0-v6 thresholds are outside the divergence zone

| Failure mode | Symptom | Fix direction |
|---|---|---|
| `CPU_SPAN` too narrow | `cpu_only` saturates immediately; indistinguishable from `degradation_score` (both fire on everything) | **Increase** `CPU_SPAN` — widen the dynamic range |
| `CPU_SPAN` too wide | `cpu_only` never crosses threshold; indistinguishable from `latency_only` (neither fires on CPU) | **Decrease** `CPU_SPAN` — compress the dynamic range |
| `CPU_FLOOR` too high | CPU component always zero; `cpu_only` never fires, all modes look like `latency_only` | **Lower** `CPU_FLOOR` |
| `CPU_FLOOR` too low | CPU component non-zero even at baseline; `cpu_only` and `degradation_score` both fire on minor fluctuations | **Raise** `CPU_FLOOR` |
| `T_PROC_FLOOR` too high | Latency component always zero; `latency_only` never fires, all modes look like `cpu_only` | **Lower** `T_PROC_FLOOR` |
| `T_PROC_SPAN` too narrow | `latency_only` saturates immediately on minor T_proc elevation; indistinguishable from `cpu_only` in saturation behaviour | **Increase** `T_PROC_SPAN` — widen the latency dynamic range |
| `T_PROC_SPAN` too wide | `latency_only` never crosses threshold even under stress; indistinguishable from `cpu_only` (neither fires on latency) | **Decrease** `T_PROC_SPAN` — compress the latency dynamic range |
| `BASE_THRESHOLD` too high | No mode fires during stress — all three miss genuine overload | **Lower** `BASE_THRESHOLD` |
| `BASE_THRESHOLD` too low | All three fire during baseline — FP rates converge at ceiling | **Raise** `BASE_THRESHOLD` |
| Storage CPU is I/O-wait noise at 0.08 CPUs | `cpu_only` storage spawns are driven by I/O-wait fluctuations, not genuine storage overload. Behaviour is random — sometimes fires, sometimes doesn't, with no systematic relationship to storage stress. | Not a fixable parameter — this is a finding. If `cpu_only` storage behaviour is noise-driven, the divergence analysis must treat storage tier `cpu_only` as degenerate. D2 relaxes for this case (§6.1, §7). |

The calibration's diagnostic (G8 score component decomposition) is designed
to identify which failure mode is active before the spawn counts are even
examined — the score traces alone tell you which parameter to adjust.

---

## 3. Independent Variable & Held-Constant Set

### 3.1 Independent Variable

| Variable | Values |
|---|---|
| Trigger composition (four weight variables) | `degradation_score` (0.40/0.60, 0.60/0.40), `cpu_only` (1.00/0.00, 1.00/0.00), `latency_only` (0.00/1.00, 0.00/1.00) |

The compute and storage weight pairs are **coupled** — each mode applies the
same logical composition to both tiers (cross-signal, CPU-only, or
latency-only). Independent compute/storage weight variation (e.g., cpu_only
compute + latency_only storage) is a combinatorial space deferred to future
work. Coupling keeps the independent variable to 3 levels and aligns with the
RQ3 research question: does trigger composition matter at all, for either tier?

### 3.2 Held Constant

| Parameter | Value | Rationale |
|---|---|---|
| `STORAGE_CPUS` | 0.08 | G0-v6 validated — storage CPU drops measurably post-scale |
| `EDGE_CPUS` | 0.25 | G0-v6 validated — edge CPU drops 23–28pp in compute_spike |
| `WAN_RTT_MS` | 185 | G0-v6 validated — reduced I/O-wait dominance |
| `CLIENTS` | 96 | RQ1 v8 golden — matches RQ1/RQ2 client count |
| `MAX_DYNAMIC_COMPUTE` | 12 | RQ1 v8 golden — gives all modes room to diverge |
| `MAX_DYNAMIC_STORAGE` | 8 | RQ1 v8 golden — G0-v6 peaked at 7 |
| `RANDOM_SEED` | 42 | Reproducible request sequence |
| `DATA_SEED` | 42 | Reproducible test data |
| `PHASES_CONFIG` | `testing/phases.json` | Canonical 7-phase workload |
| `STORAGE_PERSISTENT_RESERVE_ENABLED` | 1 | Fixed — reserve spawns excluded from FP counts |
| `SS_ENABLED` | 1 | Fixed — Tier 1 selective sync active |
| `BACKEND_SELECTION_POLICY` | `topology_lifecycle` | Fixed — warm-lease routing (RQ2's domain) |
| Telemetry delivery | Push (ZMQ) | Fixed — RQ1's optimal delivery |
| Latency signal | Mean-only (`avg_time_proc_ms`, `avg_time_db_ms`) | G0-v2 decision — avoids timeout-censored p95 |
| `VIP_HARD_TIMEOUT` | 60 | Fixed |
| `CURL_MAX_TIME` | 30 s | Fixed |

### 3.3 Scoring Parameters (Identical Across All Three Modes)

| Parameter | G0-v6 Value | Role |
|---|---|---|
| `SCALEUP_CPU_FLOOR` | 10 | Below-floor CPU = zero CPU component |
| `SCALEUP_CPU_SPAN` | 40 | Determines CPU sensitivity — the key divergence parameter |
| `SCALEUP_T_PROC_FLOOR` | 25 ms | Below-floor T_proc = zero latency component |
| `SCALEUP_T_PROC_SPAN` | 80 | Determines T_proc sensitivity |
| `SCALEUP_COMPUTE_BASE_THRESHOLD` | 0.18 | Must be above baseline scores, below stress scores |
| `SCALEUP_COMPUTE_THRESHOLD_INCREMENT` | 0.10 | Adaptive escalation per existing dynamic node |
| `SCALEUP_COMPUTE_MAX_THRESHOLD` | 0.85 | Ceiling for adaptive threshold |
| `SCALEUP_WINDOW_SIZE` | 5 | 5 telemetry windows evaluated |
| `SCALEUP_REQUIRED` | 3 | 3 of 5 windows must breach |
| `SCALEUP_COMPUTE_COOLDOWN_S` | 45 s | Grace period after each spawn |
| `SCALEUP_COMPUTE_PEER_RELIEF` | 0.03 | Score reduction per peer node (code default, explicit for transparency) |
| `SCALEUP_COMPUTE_PEER_HEALTH_THRESHOLD` | 0.35 | Peer considered healthy below this (code default, explicit for transparency) |
| `SCALEUP_STORAGE_CPU_FLOOR` | 1.5 | Storage CPU floor — very low, I/O-wait dominant |
| `SCALEUP_STORAGE_CPU_SPAN` | 5 | Storage CPU span |
| `SCALEUP_T_DB_FLOOR` | 60 ms | Below-floor T_db = zero T_db component |
| `SCALEUP_T_DB_SPAN` | 250 ms | Determines T_db sensitivity |
| `SCALEUP_STORAGE_BASE_THRESHOLD` | 0.35 | G0-v6 validated — storage scoring loop closes at τ=0.35 |
| `SCALEUP_STORAGE_REQUIRED` | 2 | 2 of 5 windows must breach |
| `SCALEUP_STORAGE_COOLDOWN_S` | 120 s | Grace period after each storage spawn |
| `SCALEUP_STORAGE_THRESHOLD_INCREMENT` | 0.10 | Adaptive escalation per existing dynamic storage node (code default, explicit for transparency) |
| `SCALEUP_STORAGE_MAX_THRESHOLD` | 0.55 | Ceiling for adaptive storage threshold (code default, explicit for transparency) |
| `SCALEDOWN_COMPUTE_COOLDOWN_S` | 180 s | Keeps nodes alive through phase transitions |
| `SCALE_DOWN_COMPUTE_REQUIRED` | 9 | Requires strong evidence of sustained low load |
| `SCALE_DOWN_COMPUTE_WINDOW_SIZE` | 12 | Compute scale-down evaluation window (code default, explicit for transparency) |
| `SCALEDOWN_STORAGE_COOLDOWN_S` | 120 s | Storage scale-down grace period (code default, explicit for transparency) |
| `SCALE_DOWN_STORAGE_WINDOW_SIZE` | 12 | Storage scale-down evaluation window (code default, explicit for transparency) |
| `SCALE_DOWN_STORAGE_REQUIRED` | 7 | Storage scale-down required windows (code default, explicit for transparency) |
| `TELEMETRY_TIMEOUT_WINDOWS` | 18 | Windows without telemetry → node marked dead (code default, explicit for transparency) |
| `NODE_BIRTH_GRACE_S` | 60 s | Skip dead-node detection for first 60 s after spawn (code default, explicit for transparency) |

> **Note on "code default, explicit for transparency"**: These parameters match
> `scaling_config.py` defaults. They are included in the env override files
> (rather than relying on code defaults) so that `controller_env_snapshot.env`
> captures the complete scoring configuration in one place. This makes S3
> (non-weight parameter diff) a single-file comparison. They will appear in
> the diff against G0-v6's `current_state_integrated.env` (which omits them),
> but the diff is semantically neutral — these are the same values the code
> would use if they were absent.

---

## 4. Run Matrix

6 runs, two per trigger mode. Grouped by mode for operational simplicity —
within-mode replicates run back-to-back to minimise configuration churn.

| # | Label | Trigger Mode | Env Override File | Weights (compute) | Weights (storage) |
|---|-------|-------------|-------------------|-------------------|-------------------|
| **C-DS1** | `rq3_cal_ds_1` | `degradation_score` | `rq3_v2_degradation_score.env` | 0.40 / 0.60 | 0.60 / 0.40 |
| **C-DS2** | `rq3_cal_ds_2` | `degradation_score` | `rq3_v2_degradation_score.env` | 0.40 / 0.60 | 0.60 / 0.40 |
| **C-CO1** | `rq3_cal_cpu_1` | `cpu_only` | `rq3_v2_cpu_only.env` | 1.00 / 0.00 | 1.00 / 0.00 |
| **C-CO2** | `rq3_cal_cpu_2` | `cpu_only` | `rq3_v2_cpu_only.env` | 1.00 / 0.00 | 1.00 / 0.00 |
| **C-LO1** | `rq3_cal_lat_1` | `latency_only` | `rq3_v2_latency_only.env` | 0.00 / 1.00 | 0.00 / 1.00 |
| **C-LO2** | `rq3_cal_lat_2` | `latency_only` | `rq3_v2_latency_only.env` | 0.00 / 1.00 | 0.00 / 1.00 |

**Run order**: C-DS1 → C-DS2 → C-CO1 → C-CO2 → C-LO1 → C-LO2.
`degradation_score` first — it uses the weights closest to G0-v6 (though not
identical — G0-v6 used 0.60/0.40 compute and 0/1.0 storage; C-DS uses the
canonical RQ3 weights 0.40/0.60 and 0.60/0.40). The C-DS pair serves as the
infrastructure health check: if both complete cleanly with spawns during
stress phases, the controller, mean-only signal, and resource config are all
functional before testing the single-dimension modes.

**Between every run**: cleanup + VM reboot.

**Total wall-clock estimate**: 6 × (24 min run + 5 min cleanup/reboot) ≈
**3 hours**.

---

## 5. Run Configuration

### 5.1 Prerequisites

Before any calibration run:

1. **Create the three env override files** in
   `source/scripts/testing/controller_env_overrides/`. Copy the base block
   from §5.3 into each file, then append the mode-specific weight lines.
   Verify with `diff` that only the four `SCALEUP_W_*` lines differ:
   ```bash
   diff rq3_v2_degradation_score.env rq3_v2_cpu_only.env
   diff rq3_v2_degradation_score.env rq3_v2_latency_only.env
   ```
2. **Deploy the mean-only latency signal code change** in
   `scaling_policy.py` (§7.1 of `rq3_setup_v2.md`) and rebuild the
   controller image. G0-v2 through G0-v6 used mean-only signals — verify
   this change is still in place (it may have been reverted if the
   controller image was rebuilt from a clean checkout after G0-v6).
3. Confirm `MAX_DYNAMIC_COMPUTE=12` and `MAX_DYNAMIC_STORAGE=8` are in
   the env override files (not left at code defaults of 4 and 5).

### 5.2 Launch Commands

All three runs use the same base command, varying only `RUN_LABEL` and
`OSKEN_ENV_OVERRIDE_FILE`.

> **Note on `SKIP_CLIENTS=1` + `create_clients`**: `create_clients` in the
> Make target chain only builds the Docker network and client containers;
> `SKIP_CLIENTS=1` is passed through to `run_experiment.sh`'s `--skip-clients`
> flag, which skips the *launch* of client processes (already running from
> the network setup). Both are needed and do not conflict.

```bash
# C-DS — degradation_score (baseline reference)
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/rq3_v2_degradation_score.env \
  RUN_LABEL=rq3_cal_ds \
  PHASES_CONFIG=testing/phases.json \
  WAN_RTT_MS=185 CLIENTS=96 CONTENT_ITEMS=6000 USERS=100 \
  STORAGE_CPUS=0.08 EDGE_CPUS=0.25 \
  STORAGE_MEMORY=512m EDGE_MEMORY=256m \
  RANDOM_SEED=42 DATA_SEED=42 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1

# C-CO — cpu_only
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/rq3_v2_cpu_only.env \
  RUN_LABEL=rq3_cal_cpu \
  PHASES_CONFIG=testing/phases.json \
  WAN_RTT_MS=185 CLIENTS=96 CONTENT_ITEMS=6000 USERS=100 \
  STORAGE_CPUS=0.08 EDGE_CPUS=0.25 \
  STORAGE_MEMORY=512m EDGE_MEMORY=256m \
  RANDOM_SEED=42 DATA_SEED=42 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1

# C-LO — latency_only
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/rq3_v2_latency_only.env \
  RUN_LABEL=rq3_cal_lat \
  PHASES_CONFIG=testing/phases.json \
  WAN_RTT_MS=185 CLIENTS=96 CONTENT_ITEMS=6000 USERS=100 \
  STORAGE_CPUS=0.08 EDGE_CPUS=0.25 \
  STORAGE_MEMORY=512m EDGE_MEMORY=256m \
  RANDOM_SEED=42 DATA_SEED=42 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
```

### 5.3 Env Override Files

Three files, identical base, differing only in four weight lines:

**`rq3_v2_degradation_score.env`**:
```
# Base — all three files identical from here down
SCALEUP_CPU_FLOOR=10
SCALEUP_CPU_SPAN=40
SCALEUP_T_PROC_FLOOR=25
SCALEUP_T_PROC_SPAN=80
SCALEUP_COMPUTE_BASE_THRESHOLD=0.18
SCALEUP_COMPUTE_THRESHOLD_INCREMENT=0.10
SCALEUP_COMPUTE_MAX_THRESHOLD=0.85
SCALEUP_WINDOW_SIZE=5
SCALEUP_REQUIRED=3
SCALEUP_COMPUTE_COOLDOWN_S=45
SCALEUP_COMPUTE_PEER_RELIEF=0.03
SCALEUP_COMPUTE_PEER_HEALTH_THRESHOLD=0.35
SCALEUP_STORAGE_CPU_FLOOR=1.5
SCALEUP_STORAGE_CPU_SPAN=5
SCALEUP_T_DB_FLOOR=60
SCALEUP_T_DB_SPAN=250
SCALEUP_STORAGE_BASE_THRESHOLD=0.35
SCALEUP_STORAGE_THRESHOLD_INCREMENT=0.10
SCALEUP_STORAGE_MAX_THRESHOLD=0.55
SCALEUP_STORAGE_WINDOW_SIZE=5
SCALEUP_STORAGE_REQUIRED=2
SCALEUP_STORAGE_COOLDOWN_S=120
SCALEDOWN_COMPUTE_COOLDOWN_S=180
SCALE_DOWN_COMPUTE_REQUIRED=9
SCALE_DOWN_COMPUTE_WINDOW_SIZE=12
SCALEDOWN_STORAGE_COOLDOWN_S=120
SCALE_DOWN_STORAGE_WINDOW_SIZE=12
SCALE_DOWN_STORAGE_REQUIRED=7
TELEMETRY_TIMEOUT_WINDOWS=18
NODE_BIRTH_GRACE_S=60
STORAGE_PERSISTENT_RESERVE_ENABLED=1
SS_ENABLED=1
MAX_DYNAMIC_STORAGE=8
MAX_DYNAMIC_COMPUTE=12
VIP_HARD_TIMEOUT=60

# Weights — degradation_score (cross-signal confirmation)
SCALEUP_W_CPU=0.40
SCALEUP_W_T_PROC=0.60
SCALEUP_W_STORAGE_CPU=0.60
SCALEUP_W_T_DB=0.40
```

**`rq3_v2_cpu_only.env`**: Same base, only weights differ:
```
SCALEUP_W_CPU=1.00
SCALEUP_W_T_PROC=0.00
SCALEUP_W_STORAGE_CPU=1.00
SCALEUP_W_T_DB=0.00
```

**`rq3_v2_latency_only.env`**: Same base, only weights differ:
```
SCALEUP_W_CPU=0.00
SCALEUP_W_T_PROC=1.00
SCALEUP_W_STORAGE_CPU=0.00
SCALEUP_W_T_DB=1.00
```

### 5.4 Docker Images

The `osken-controller` image must be rebuilt with the mean-only latency
signal change (§7.1 of `rq3_setup_v2.md`). All other images unchanged.

### 5.5 Between-Run Protocol

```bash
# 1. Cleanup
sudo -n make -C source/scripts cleanup

# 2. Reboot VM
sudo reboot

# 3. After reboot — verify infrastructure
sudo docker ps                # Docker daemon running
sudo docker network ls        # OVS bridges visible
sudo ovs-vsctl show           # OVS operational
```

If any verification step fails, re-run `setup_network` before proceeding
to the next calibration run.

---

## 6. Focus & Evidence

### 6.1 Primary Evidence — Divergence Checks

| Check | Artifact | Measurement | Pass condition |
|---|---|---|---|
| D1 — Baseline FP divergence | `elasticity_events.csv` + controller log | Score-triggered spawns during `baseline` phase (reserve spawns excluded — see identification procedure below). Mean across 2 replicates per mode. | `cpu_only` mean FPs > `degradation_score` mean FPs, AND `latency_only` mean FPs > `degradation_score` mean FPs. Within-mode replicates must agree directionally (both > composite, or both ≤ composite). If replicates disagree, the FP signal is noise-dominated — D1 fails. |
| D2 — Stress detection (compute) | `elasticity_events.csv` | Score-triggered spawns during `compute_spike`. Both replicates per mode. | All three modes have ≥ 1 compute spawn in BOTH replicates. If only one replicate spawns, the mode's detection is unreliable. |
| D2b — Stress detection (storage) | `elasticity_events.csv` | Score-triggered spawns during `storage_storm`. Both replicates per mode. | `degradation_score` and `latency_only` have ≥ 1 storage spawn in BOTH replicates. `cpu_only` may have zero — storage CPU at 0.08 CPUs is I/O-wait noise (§2.2, §8). If one `cpu_only` replicate spawns and the other doesn't, storage CPU is noise-driven — treat as zero. |
| D3 — Score component divergence | `per_node_stats.csv` replayed through `breach_detector.py` | Per-window CPU and latency components during baseline and stress phases. One representative replicate per mode (median by total spawn count). | The three modes show visibly different score component traces — `cpu_only` traces dominated by CPU component, `latency_only` dominated by latency component, `degradation_score` showing both. Consistency across the two replicates confirmed qualitatively. |

**Reserve spawn identification procedure**:
1. Search controller log for `standby_storage: spawning reserve` — these are reserve spawns. Exclude them.
2. Search controller log for `scale-up: storage triggered` or `scale-up: compute triggered` — these are score-triggered spawns. Count only these.
3. In `elasticity_events.csv`, reserve spawns appear with `reason=persistent_reserve`; score-triggered spawns appear with `reason=degradation_score`. Filter by the `reason` column.
4. If in doubt, cross-reference the spawn timestamp against the controller log — reserve spawns are timestamped during baseline startup (~T+10–30s), not in response to telemetry windows.

### 6.2 Secondary Evidence — Sanity Checks

| Check | Artifact | Expectation |
|---|---|---|
| S1 — Env files created correctly | `controller_env_snapshot.env` from all 6 runs | `diff` between any two snapshots from different modes shows ONLY the four `SCALEUP_W_*` lines differ. All other parameters identical. |
| S2 — Weights applied correctly | `controller_env_snapshot.env` | Weight variables match the mode label for each run |
| S3 — Mean-only signal active | Controller log | Confirmation that `compute_latency_signal` and `storage_latency_signal` return mean-only values |
| S4 — No controller tracebacks | `controller_lan1.log`, `controller_lan2.log` | Zero tracebacks across all 6 runs |
| S5 — All runs complete | Run output | All 6 runs reach idle shutdown, no early termination |
| S6 — Infrastructure functional (C-DS pair) | `elasticity_events.csv` from C-DS1 and C-DS2 | ≥ 1 spawn during `storage_storm` AND ≥ 1 spawn during `compute_spike` in BOTH replicates. Confirms the controller, mean-only signal, and resource config are functional before testing single-dimension modes. |

### 6.3 Diagnostic — Score Component Decomposition

After all six runs complete, replay the telemetry through `breach_detector.py`
to produce the G8 score component traces. This is the **most informative
single artifact** — it shows whether the three modes are behaviourally
different before looking at spawn counts.

**Tool**: `source/scripts/testing/analysis/rq1/lib/breach_detector.py`

**Invocation** (per run folder):
```bash
python source/scripts/testing/analysis/rq1/lib/breach_detector.py \
  --run-folder metrics/<batch>/<timestamp>_rq3_cal_<mode>/ \
  --weights-env source/scripts/testing/controller_env_overrides/rq3_v2_<mode>.env \
  --output rq3_cal_<mode>_score_components.csv
```

**Diagnostic interpretation**:
- If `cpu_only` and `degradation_score` traces look identical: `CPU_SPAN` is
  too narrow (both saturate) or `CPU_FLOOR` is too low (both fire on minor
  fluctuations).
- If `latency_only` and `degradation_score` traces look identical: `T_PROC_SPAN`
  is too narrow (both saturate on latency) or `T_PROC_FLOOR` is too low.
- If `latency_only` shows zero crossings everywhere while `degradation_score`
  shows crossings: `T_PROC_FLOOR` is too high or `T_PROC_SPAN` too wide —
  latency component always zero.
- If `cpu_only` shows zero crossings: `CPU_FLOOR` is too high or `CPU_SPAN`
  too wide — CPU component always zero.
- If `cpu_only` storage component oscillates randomly (crosses threshold in
  some windows, not others, with no relationship to storage_storm onset):
  storage CPU is I/O-wait noise — expected at 0.08 CPUs (§2.2, §8).

---

## 7. Decision Rule

After all six runs complete and the divergence checks are evaluated:

| Outcome | Action |
|---|---|
| **All D1, D2, D2b, D3 pass** | ✅ Proceed to 9-run RQ3 evaluation. G0-v6 thresholds are in the divergence zone. |
| **D1 passes but D2 or D2b fails for a mode other than `cpu_only` storage** | ⚠️ A mode missed genuine overload. Lower `BASE_THRESHOLD` and retry the failing mode (both replicates). |
| **D2b fails for `cpu_only` storage specifically (zero storage spawns in both replicates, or noise-driven disagreement)** | ⚠️ Expected if storage CPU is I/O-wait noise (§2.2, §8). Check G8 traces: if the CPU component is non-zero but below threshold, this is a finding, not a failure — `cpu_only` cannot drive storage scaling at 0.08 CPUs. Proceed with this acknowledged. If the CPU component IS zero everywhere, `STORAGE_CPU_FLOOR` or `STORAGE_CPU_SPAN` is mis-calibrated — adjust and retry. |
| **D1 fails — all three modes have similar FP rates** | ⚠️ No divergence. Examine G8 traces to identify the compressing parameter. Adjust one parameter and retry all three modes (2 replicates each = 6 runs). |
| **D1 fails because within-mode replicates disagree** (e.g., `cpu_only` rep1 has FPs > composite, rep2 does not) | ⚠️ The mode's baseline behaviour is noise-dominated. The G0-v6 thresholds may be too close to the noise floor at 0.08/0.25 CPUs. Consider a tighter resource config or raise `BASE_THRESHOLD` to suppress noise-driven divergence, then retry. |
| **D1 fails in an unexpected direction** (e.g., `degradation_score` has MORE FPs than `cpu_only`) | 🔴 The weights are applied backwards or the score formula has a bug. Verify the env override files and controller code. |
| **S4 fails (tracebacks)** | 🔴 Fix the code issue before proceeding. This is not a calibration problem. |

### 7.1 Retry Protocol

If parameters need adjustment, change **one parameter at a time**, retry all
three modes (2 replicates each = 6 runs), and re-evaluate. The adjustment
direction follows §2.2:

1. First suspect: `CPU_SPAN` or `T_PROC_SPAN` (the parameters most likely to
   be mis-calibrated for single-dimension modes — determine which from G8 traces).
2. Second suspect: `BASE_THRESHOLD` (if all modes fire too much or too little).
3. Third suspect: `CPU_FLOOR` or `T_PROC_FLOOR` (if one specific mode is
   suppressed — `cpu_only` → `CPU_FLOOR`; `latency_only` → `T_PROC_FLOOR`).

**Maximum retries**: 2 rounds (12 additional runs). If divergence is not
achieved after 3 total rounds (18 runs), the G0-v6 resource configuration
may not support trigger composition divergence — consider a tighter resource
config from the Phase 1a calibration space.

---

## 8. Storage CPU Weight Calibration (W_STORAGE_CPU)

### 8.1 Rationale

The canonical RQ3 `degradation_score` storage weights (0.60 CPU, 0.40 T_db)
were set before G0-v6 established that storage CPU at 0.08 CPUs is I/O-wait
and not a meaningful scaling signal. The calibration data from §6 confirms
the problem: `cpu_only` (W_STORAGE_CPU=1.0) produced 22–24 storage spawns,
and `degradation_score` (W_STORAGE_CPU=0.60) produced 24 — identical within
noise. The CPU component is dominating the storage score with I/O-wait noise.

For RQ3, `degradation_score` storage should show a **measurable CPU
contribution** during `storage_storm` (confirming both signals are active)
without letting CPU noise drown out the T_db signal. This calibration finds
the highest weight that still lets T_db be the primary driver.

**Historic context from v4**: At C4 resources (0.04/0.06 CPUs, WAN=260ms),
storage CPU reached 55–76% during `storage_storm` — it was a real signal
(calibration_results.md §4). At G0-v6 (0.08/0.25 CPUs, WAN=185ms), storage
CPU dropped to 22–23% — well below the compute stress range. The question is
whether ANY CPU weight can add meaningful information without dominating.

### 8.2 What Is Being Tested

**Single variable**: `SCALEUP_W_STORAGE_CPU` (and correspondingly
`SCALEUP_W_T_DB = 1.0 − W_STORAGE_CPU`).

**4 weight candidates** spanning the range from C-DS (0.60) down to near-zero:

| Candidate | W_STORAGE_CPU | W_T_DB | Rationale |
|---|---|---|---|
| **W40** | 0.40 | 0.60 | Upper-mid — still CPU-heavy. Tests whether any reduction from 0.60 helps. |
| **W30** | 0.30 | 0.70 | Mid — T_db is the dominant signal. Likely sweet spot. |
| **W20** | 0.20 | 0.80 | Conservative — CPU is a minority contributor. |
| **W10** | 0.10 | 0.90 | Minimal — CPU barely contributes. Tests whether ANY CPU signal is visible. |

The existing C-DS pair (W_STORAGE_CPU=0.60, 24 storage spawns) serves as
the upper bound. C-LO (0.00, 15–17 spawns) is the lower bound.

### 8.3 Run Configuration

Up to 5 runs, `degradation_score` mode only. Other modes unaffected — `cpu_only`
storage is always W_STORAGE_CPU=1.0 (testing the extreme), `latency_only` is
always 0 (genuine latency-only baseline).

| # | Label | W_STORAGE_CPU | W_T_DB | Expected storage spawns |
|---|---|---|---|---|
| **C-W30** | `rq3_cal_ds_w30` | 0.30 | 0.70 | 18–22 |
| **C-W20** | `rq3_cal_ds_w20` | 0.20 | 0.80 | 15–20 |
| **C-W10** | `rq3_cal_ds_w10` | 0.10 | 0.90 | 15–18 |
| **C-W40** | `rq3_cal_ds_w40` | 0.40 | 0.60 | Only if W10/W20/W30 are inconclusive |
| **C-Wxx_R** | `rq3_cal_ds_wxx_rep` | *(winning weight)* | *(1.0 − winning)* | Confirm consistency |

**Run order**: C-W20 → C-W10 → C-W30. Start in the middle and bracket:
if W20 already shows clear CPU contribution, skip W30 (it's redundant —
higher weight, same conclusion). If W20 shows NO CPU contribution, skip
W10 (it's redundant — lower weight, same conclusion of no contribution).
W40 only runs if the W20–W30 range is ambiguous.

**Between every run**: cleanup + VM reboot.

**Total wall-clock estimate**: 3–5 × (24 min run + 5 min cleanup/reboot) ≈
**1.5–2.5 hours**.

**Launch command** (C-W20 — others vary only `RUN_LABEL` and storage weights):
```bash
# 1. Update storage weights in the env file on cloud VM
ssh cloud-vm "sed -i 's/^SCALEUP_W_STORAGE_CPU=.*/SCALEUP_W_STORAGE_CPU=0.20/' ~/efficient-storage-in-edge-scenarios/source/scripts/testing/controller_env_overrides/rq3_v2_degradation_score.env"
ssh cloud-vm "sed -i 's/^SCALEUP_W_T_DB=.*/SCALEUP_W_T_DB=0.80/' ~/efficient-storage-in-edge-scenarios/source/scripts/testing/controller_env_overrides/rq3_v2_degradation_score.env"

# 2. Verify
ssh cloud-vm "grep 'SCALEUP_W_STORAGE_CPU\|SCALEUP_W_T_DB' ~/efficient-storage-in-edge-scenarios/source/scripts/testing/controller_env_overrides/rq3_v2_degradation_score.env"

# 3. Launch (standard command — no Make variable overrides needed)
ssh -o ServerAliveInterval=60 cloud-vm "cd ~/efficient-storage-in-edge-scenarios && sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/rq3_v2_degradation_score.env \
  RUN_LABEL=rq3_cal_ds_w20 \
  PHASES_CONFIG=testing/phases.json \
  WAN_RTT_MS=185 CLIENTS=96 CONTENT_ITEMS=6000 USERS=100 \
  STORAGE_CPUS=0.08 EDGE_CPUS=0.25 \
  STORAGE_MEMORY=512m EDGE_MEMORY=256m \
  RANDOM_SEED=42 DATA_SEED=42 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1"
```

> **Note**: The Makefile does NOT pass arbitrary `SCALEUP_W_*` variables through
> to the controller. Instead, `sed` edits the env override file on the cloud VM
> before each probe run. After the probe completes, restore the original 0.60/0.40
> values:
> ```bash
> ssh cloud-vm "sed -i 's/^SCALEUP_W_STORAGE_CPU=.*/SCALEUP_W_STORAGE_CPU=0.60/' ~/efficient-storage-in-edge-scenarios/source/scripts/testing/controller_env_overrides/rq3_v2_degradation_score.env"
> ssh cloud-vm "sed -i 's/^SCALEUP_W_T_DB=.*/SCALEUP_W_T_DB=0.40/' ~/efficient-storage-in-edge-scenarios/source/scripts/testing/controller_env_overrides/rq3_v2_degradation_score.env"
> ```

### 8.4 Evaluation

Three checks, applied to each run. W3 (pre→post improvement) is the
**gating check** — if CPU-triggered storage spawns don't produce real T_db
improvement, the CPU weight is noise-driven and should not be used.

| Check | Artifact | Measurement | Criterion |
|---|---|---|---|
| **W1 — CPU contribution visible** | `policy_state.csv` | `storage_score` during first 120s of `storage_storm` (both LANs) | Score > `storage_base_threshold` in ≥ 2 windows. Confirms CPU component crosses threshold during storage stress. |
| **W2 — T_db still primary driver** | Controller log | Storage spawn count | Between C-LO (15–17) and C-DS (24). If spawn count ≈ C-DS (≥22), CPU noise still dominates. If ≈ C-LO (≤17), CPU adds nothing. Ideal: 18–21 — CPU adds a moderate secondary contribution. |
| **W3 — Pre→post T_db improvement** | `per_node_stats.csv` | Mean T_db in first 60s vs last 60s of `storage_storm` on each LAN | T_db drops measurably post-scale on at least one LAN. If T_db is flat or rises, CPU-triggered spawns are not relieving storage pressure — the CPU signal is noise, not a real overload indicator. This is the same pre→post check used for compute in G0-v6 (§8.4 of results_v4.md). |

### 8.5 Decision Rule

Evaluate in order: W3 first (is the improvement real?), then W2 (is T_db
still primary?), then W1 (is CPU contributing at all?).

| Outcome | Action |
|---|---|
| **W3 fails at all tested weights** | 🔴 CPU-triggered storage spawns don't produce real T_db improvement. The CPU signal is noise. Use W_STORAGE_CPU=0, W_T_DB=1.0 (latency-only storage) for the 9-run evaluation. The thesis bounds trigger composition to compute-only for the storage tier. |
| **W3 passes, W20 passes W1 + W2 (ideal: 18–21 spawns)** | ✅ Use W_STORAGE_CPU=0.20. Run one replicate (C-W20_R) to confirm consistency. If consistent, lock in 0.20. |
| **W3 passes, W20 fails W1 (no CPU component), W30 passes W1 + W2** | ✅ Use W_STORAGE_CPU=0.30. Run replicate to confirm. |
| **W3 passes at W20/W30 but W2 shows spawns ≈ C-DS (≥22)** | ⚠️ Even at 0.20/0.30, CPU noise dominates. Try W10. |
| **W3 passes, but all weights W10–W30 fail W1 (no CPU component)** | ⚠️ CPU is not a viable storage signal at any weight. Use W_STORAGE_CPU=0. This is a finding, not a failure — the thesis shows that trigger composition diverges for compute (where both signals are meaningful) but converges for storage (where only T_db is meaningful). |
| **W20–W30 ambiguous — W40 passes W1/W2/W3 with 18–21 spawns** | ⚠️ Use W_STORAGE_CPU=0.40. This indicates storage CPU has a real but weak signal that emerges only at higher weight. |

### 8.6 Relationship to Main Calibration

This section runs AFTER the main divergence calibration (§1–§7) confirms
three-way compute divergence. It fine-tunes one parameter (storage CPU weight)
before the 9-run evaluation. The main calibration's go/no-go decision (§7) is
independent of this section — compute divergence is the primary gate. This
section determines whether storage provides a convergent control group
(expected) or shows divergence as well (unexpected).

---

## 9. Validity Threats

| Threat | Mitigation |
|---|---|
| **n=2 per mode.** Two replicates provide a basic consistency check — modes with divergent replicates are noise-dominated and the divergence signal is unreliable. Cannot estimate variance with n=2 (SEM requires n≥3). | This is a calibration, not an evaluation. If within-mode replicates disagree directionally (D1: one rep shows FPs > composite, the other does not), the mode's behaviour is noise-dominated — the decision rule has a dedicated branch for this (§7). The 9-run evaluation uses n=3 per mode. |
| **C-DS uses different weights than G0-v6.** G0-v6 used `SCALEUP_W_CPU=0.60, SCALEUP_W_T_PROC=0.40` (CPU-weighted) and `SCALEUP_W_STORAGE_CPU=0, SCALEUP_W_T_DB=1.0` (latency-only storage). C-DS uses the canonical RQ3 weights: `0.40/0.60` compute and `0.60/0.40` storage. Spawn counts will NOT match G0-v6. | C-DS is not expected to reproduce G0-v6. It serves as the infrastructure health check (S6): if it completes cleanly with spawns during stress phases, the controller, mean-only signal, and resource config are functional. The weight difference is intentional — these are the canonical RQ3 weights from `rq3_v2.md` §3.3. |
| **Storage CPU weight 0.60 contradicts G0-v6's latency-only storage rationale.** G0-v6 explicitly removed storage CPU from the score (`SCALEUP_W_STORAGE_CPU=0`) because storage CPU at 0.08 CPUs is I/O-wait and not a meaningful scaling signal. The RQ3 `degradation_score` mode restores it at weight 0.60. | This is intentional — RQ3 tests whether CPU adds value as a storage signal when combined with T_db (cross-signal confirmation). If `degradation_score` storage behaviour is identical to `latency_only` storage behaviour (because the CPU component is I/O-wait noise), that's a finding: CPU adds no information for storage at this resource level. The `cpu_only` storage mode tests the extreme case — CPU alone. The D2b relaxation (§6.1, §7) accounts for the possibility that `cpu_only` storage is degenerate. |
| **The mean-only latency signal code change may not be deployed.** If `scaling_policy.py` still uses `max(avg, p95)`, the latency component will be systematically higher than intended (p95 is timeout-censored at 30,001 ms). | S3 checks the controller log. The runner must confirm the code change is deployed before any run. G0-v2 through G0-v6 used mean-only signals — verify the change is still in place. |
| **`cpu_only` storage CPU weight = 1.00 may be meaningless at 0.08 CPUs.** G0-v6 uses `SCALEUP_W_STORAGE_CPU=0` because storage CPU at 0.08 is I/O-wait. `cpu_only` with storage CPU weight = 1.00 forces the controller to scale storage based on I/O-wait CPU — this may produce zero spawns during storage_storm, which is a valid finding (CPU is not a viable storage signal at this resource level). | Not a threat — this is a finding. The decision rule (§7) and D2b (§6.1) explicitly handle this case. If `cpu_only` produces zero storage spawns while `degradation_score` produces several, that bounds the trigger composition space: storage scaling requires a latency component at 0.08 CPUs. |
| **Reserve spawns may contaminate baseline FP counts.** `STORAGE_PERSISTENT_RESERVE_ENABLED=1` pre-warms a storage node — this spawn appears during baseline but is NOT a degradation-score FP. | Use the reserve spawn identification procedure in §6.1: filter `elasticity_events.csv` by `reason=degradation_score`, cross-reference controller log for `standby_storage: spawning reserve` vs `scale-up: storage triggered`. |
| **Baseline phase is only 60 s — limited FP detection window.** With 10 s telemetry windows and `REQUIRED=3` of 5, baseline yields at most 6 windows and ~2 independent breach opportunities. A borderline mode may or may not produce an FP depending on window alignment. | Two replicates per mode provide two independent baseline windows, so the FP signal is averaged across two draws. If both replicates agree (both show FPs > composite, or both do not), the signal is consistent. If they disagree, D1 fails explicitly — the mode's FP behaviour is alignment-sensitive and unreliable. The 9-run evaluation (n=3) provides a third draw. |

---

## 10. Artifact Contract

Standard run-folder layout per `docs/operation/testing/testing_overview.md`:

```
metrics/<batch>/<timestamp>_rq3_cal_<mode>/
├── client_requests.csv
├── resource_stats.csv
├── per_node_stats.csv
├── container_events.csv
├── elasticity_events.csv
├── node_lifecycle_timings.csv
├── controller_lan1.log
├── controller_lan2.log
├── phases_snapshot.json
├── controller_env_snapshot.env
└── resource_config.env          ← runner appends STORAGE_CPUS/EDGE_CPUS/CLIENTS/WAN_RTT_MS
```

No experiment-specific files beyond the standard layout.

### Post-Calibration Output

After all three runs complete and the decision is made, produce a brief
`calibration_results_v2.md` in the same directory containing:

1. **Decision**: go / no-go / parameter-adjusted
2. **Divergence check results**: D1, D2, D2b, D3 pass/fail with per-replicate values
3. **Spawn count summary**: per mode, per replicate, per phase (storage_storm, compute_spike, baseline), with compute and storage spawns listed separately
4. **G8 score component trace**: one representative replicate per mode (median by spawn count) showing the divergence (or lack thereof)
5. **If no-go**: which parameter to adjust, in which direction, and the retry plan
