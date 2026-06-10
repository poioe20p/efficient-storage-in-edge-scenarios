# Experiment Plan — Storage Scale-Down Diagnostic

**Status**: Planned — not yet run.  
**Date**: 2026-06-10.  
**Depends on**: [zombie_node_fix](../zombie_node_fix/experiment_plan.md) — same phase file and config; [vip_warm_method_fix](#fixes-applied) — `mark_storage_backend_warm` now wired to `VipRoutingMixin`.

## Fixes Applied Before This Run

1. **`mark_storage_backend_warm`/`mark_server_backend_warm`/`clear_*_warm`** — 4 missing methods added to `VipRoutingMixin` in `vip_routing.py`. Fixes `AttributeError` in `main_n1.py:156` / `main_n2.py:138` where `self.mark_storage_backend_warm(mac, domain)` was called on a mixin that lacked the method.

2. **Diagnostic logging upgrades** — 4 `logger.debug` → `logger.info` changes (2 in `main_n1.py`, 2 in `main_n2.py`) so the storage scale-down decision path is fully visible at the default INFO log level:
   - `is_busy()` guard → `"[scale-down] elasticity manager is busy — skipping scaling evaluation"`
   - Storage cooldown skip → `"[scale-down] storage within Xs cooldown — skipping"`

## Intent

Diagnose why storage scale-down evaluation produces zero log output after cooldown expiry in the `zombie_fix_verify` experiment. The code path after the `is_busy()` guard is sequential — compute and storage eval run back-to-back with no branching. Since compute eval runs (produces `"no graceful candidate"` at INFO), storage eval MUST also be reached. Three hypotheses explain the silence; this run discriminates between them.

Answers one question: **which of the three possible blockers is preventing `evaluate_scale_down_storage()` from running?**

## Hypotheses

| # | Hypothesis | Predicted log signature if true |
|---|---|---|
| H1 | `storage_cooldown_remaining()` perpetually > 0 — `_last_storage_scale_up_ts` keeps getting reset by repeated scale-up/reserve activation | `"storage within Xs cooldown — skipping"` appears every cycle |
| H2 | `evaluate_scale_down_storage()` runs but a non-float in `ds.avg_storage_cpu_percent` or `ds.avg_time_db_ms` crashes the `%.1f` format string before the log emits | `"telemetry receive error"` at WARNING from the ZMQ handler, with a `TypeError` or `ValueError` message |
| H3 | The storage eval lines were present but missed by previous log analysis (wrong grep pattern, different format) | `"storage eval: stCpu=... db=... below=... hits=... armed=..."` appears normally |

## Independent Variable & Held-Constant Set

- **Independent variable**: diagnostic INFO-level logging (the 4 DEBUG→INFO upgrades) — single run, no A/B comparison.
- **Held constant**: all configuration from `zombie_fix_verify`, same `phases.json`, `SCALEDOWN_COMPUTE_COOLDOWN_S=180`.

### Configuration

All values from [`current_state_integrated.env`](../../../../../../source/scripts/testing/controller_env_overrides/current_state_integrated.env):

- `CLIENTS=8`, `DEVICES=600`, `NODES=100`
- `STORAGE_PERSISTENT_RESERVE_ENABLED=1`, `SS_ENABLED=1`
- `MAX_DYNAMIC_COMPUTE=6`, `MAX_DYNAMIC_STORAGE=5`
- `SCALEUP_STORAGE_BASE_THRESHOLD=0.12`, `SCALEUP_COMPUTE_BASE_THRESHOLD=0.20`
- `SCALEDOWN_COMPUTE_COOLDOWN_S=180`, `SCALEDOWN_STORAGE_COOLDOWN_S=120`

**No Docker image rebuild needed** — controller code (`vip_routing.py`, `main_n1.py`, `main_n2.py`) is volume-mounted.

## Run Matrix

| Run label | Phase file | Fixes applied? | Reboot before? |
| --------- | ---------- | -------------- | -------------- |
| `storage_sd_diag` | `testing/phases.json` | All 3 (vip warm methods + diagnostic logs) | Yes |

Single diagnostic run — we only need log output, not variance measurement.

## Run Configuration

```bash
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  RUN_LABEL=storage_sd_diag \
  PHASES_CONFIG=testing/phases.json \
  CLIENTS=8 DEVICES=600 NODES=100 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
```

No `--fault-plan`. No Docker rebuild. Controllers will pick up the edited `.py` files via the existing volume mounts on next restart (which `make run_experiment` triggers).

## Phases (`phases.json`)

~15 min total. Exercises all elasticity paths, ends with 6 min idle:

| # | Phase | Duration | Rate/client | Cross-region | Purpose |
| - | ----- | -------- | :---------: | :----------: | ------- |
| 1 | baseline | 30s | 1.0 | 0% | Warm up |
| 2 | storage_stress | 120s | 5.0 | 75% | Trigger storage elasticity + Tier 1 |
| 3 | cross_region_hotspot | 120s | 6.0 | 95% | Sustained storage/Tier 1 load |
| 4 | compute_ramp | 90s | 5.0 | 5% | Trigger compute elasticity |
| 5 | compute_spike | 120s | 7.0 | 5% | Peak compute load |
| 6 | sustained_plateau | 60s | 5.0 | 5% | Moderate compute |
| 7 | **demand_drop** | **360s** | **1.0** | **0%** | **Idle — scale-down observation window** |

Total: 900s (15 min).

## Focus & Evidence

**Primary — controller logs ONLY**: `controller_lan1.log` and `controller_lan2.log`. This is a log-diagnostic run, not a performance run. All other artifacts (`client_requests.csv`, `container_events.csv`, etc.) are secondary and only consulted if the primary question is answered and a follow-up emerges.

### What to grep for (in priority order)

| # | Pattern | Tells us |
| --- | --- | --- |
| 1 | `storage eval:` | H3 confirmed — eval was running, previous analysis missed it |
| 2 | `storage within.*cooldown.*skipping` | H1 confirmed — cooldown perpetually active |
| 3 | `elasticity manager is busy` | `is_busy()` blocking both (but compute eval also wouldn't run — contradiction) |
| 4 | `telemetry receive error` | H2 confirmed — format crash in `evaluate_scale_down_storage` |
| 5 | `storage triggered` | If appearing during `demand_drop`: explains perpetual cooldown (H1 variant — scale-up firing during idle) |
| 6 | `reserve.*activated` | Same as above — `record_storage_activation()` resets cooldown |

### Analysis script

```bash
# After the run, from the run folder:
grep -n "storage eval:\|storage within.*cooldown\|elasticity manager is busy\|telemetry receive error\|storage triggered\|reserve.*activated" \
  controller_lan1.log controller_lan2.log | head -100
```

Count occurrences per phase to see the pattern.

## Metrics & Success Criteria

This is a diagnostic run — success means we can **unambiguously identify which hypothesis is correct**:

- **H1 confirmed**: ≥1 `"storage within Xs cooldown"` line after the `demand_drop` phase starts → investigate what's resetting `_last_storage_scale_up_ts`.
- **H2 confirmed**: ≥1 `"telemetry receive error"` containing `TypeError` or `format` after the `demand_drop` phase starts → fix the `DomainSummary` field or add a guard.
- **H3 confirmed**: `"storage eval:"` lines appear with `hits=` and `armed=` → the eval was running; re-check previous log analysis methodology.
- **None of the above**: Something else is wrong — escalate.

## Validity Threats & Limitations

- Single diagnostic run — no statistical power. Acceptable because we're tracing a deterministic code path, not measuring a distribution.
- The 4 DEBUG→INFO changes are temporary diagnostic instrumentation and should be reverted after the root cause is identified and fixed.
- If the VM environment differs from the previous `zombie_fix_verify` run (different Docker state, leftover containers), the symptom may not reproduce exactly.

## Artifact Contract

Standard run-folder layout per [`testing_overview.md`](../../testing_overview.md). Only `controller_lan1.log` and `controller_lan2.log` are required for the primary analysis. All other artifacts are optional for this diagnostic.

## Post-Run: Determine Next Steps

| Finding | Next action |
| --- | --- |
| H1 (perpetual cooldown) | Investigate what resets `_last_storage_scale_up_ts` — check for spurious `"storage triggered"` or `"reserve.*activated"` during `demand_drop` |
| H2 (format crash) | Fix the `DomainSummary` field or add a `try`/`except` guard in `evaluate_scale_down_storage` |
| H3 (missed by analysis) | Re-run previous log analysis with correct pattern; if storage eval was healthy, the real issue is downstream (candidate selection, alert submission, or Thread 3 execution) |
