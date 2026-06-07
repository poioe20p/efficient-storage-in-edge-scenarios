# Experiment Plan — VIP Recovery Removal Validation

**Date**: 2026-06-07
**Status**: Plan — ready
**Depends on**: [recovery_removal_plan](../../../vip_routing/implementation/plans/recovery_removal/recovery_removal_plan.md) (implemented)

## Intent

Validate that the VIP recovery removal was implemented correctly by running a short workload and confirming: (a) the system routes VIP_DATA traffic normally without recovery VIPs, (b) no recovery-related code paths are exercised in edge-server or controller logs, and (c) the new backoff-only retry path produces the expected failure signatures when MongoDB connections fail.

## Hypothesis / Expected Outcome

If recovery removal is correct:
1. **Edge server**: all epoch creations are `mode=normal`, no `mode=recovery` epochs appear, no `success_after_rebind` lease outcomes, no `recovery_expired` rollbacks, no `_rebind_request_lease_after_autoreconnect` log traces.
2. **Controller**: no `vip_data_recovery_n*` references in flow-rule or packet-in logs, no `_RECOVERY_DISTRESS_OUTCOMES` / `_domain_summary_has_recovery_distress` calls, no `recovery=True` in `select_storage` or `_handle_vip_data` paths.
3. **Retry behavior**: `run_with_request_lease` retries on the same normal VIP with exponential backoff; terminal failures carry `terminal_reason="...:retries_exhausted"` (not `"...:rebinds_exhausted"` or `"...:rotation_failed"`).
4. **System health**: overall non-200 rate ≤ 5%, no controller Python tracebacks, no edge-server crash loops.

## Independent Variable & Held-Constant Set

- **Independent variable**: recovery VIP infrastructure removed (current HEAD vs. pre-removal baseline). This is a single-configuration validation run — the comparison is against the expected log absence, not against a control run.
- **Held constant**: current repository HEAD, freshly rebuilt `edge_server` Docker image (recovery code removed), current `osken-controller.env` (recovery env vars still present but harmless — no code reads them), canonical `phases.json`, `CLIENTS=8`, `DEVICES=600`, `NODES=100`, no `--fault-plan`.

## Run Matrix

| Run label | What changes | Phase file |
| --- | --- | --- |
| `recovery_removed_val_a` | Current HEAD with recovery removed, fresh edge_server image | `phases.json` |

Single run. A second replicate (`recovery_removed_val_b`) is optional if the first run shows any anomaly — otherwise one clean run suffices for validation.

## Run Configuration

Must rebuild the `edge_server` Docker image before the run (recovery code was removed from `vip_data_mongo_runtime.py` and `edge_server_config.py`). Controller changes are Python-only — file sync + restart.

```bash
# 1. Rebuild edge_server image
sudo -n make -C source/scripts build_edge_server

# 2. Launch experiment
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=recovery_removed_val_a \
  PHASES_CONFIG=testing/phases.json \
  CLIENTS=8 DEVICES=600 NODES=100 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
```

- `--phases-config`: `testing/phases.json` (canonical, unchanged)
- `--run-label`: `recovery_removed_val_a`
- `--clients-per-lan`: `8`
- `--seed-devices`: `600`, `--seed-nodes`: `100`
- `--fault-plan`: **omitted** — no synthetic failure injection
- Controller override: none (use base `osken-controller.env`; the recovery env vars in it are harmless dead vars)
- Image rebuild: **required** for `edge_server` before run

## Focus & Evidence

**Primary focus: controller logs + edge-server service logs.** This is a log-validation experiment. Metrics are secondary — they confirm the system stayed healthy but the real answer is in log absence.

| Artifact | What to check |
| --- | --- |
| `controller_lan1.log` / `controller_lan2.log` | **Must NOT contain**: `vip_data_recovery`, `recovery=True`, `_VIP_DATA_RECOVERY`, `_RECOVERY_DISTRESS_OUTCOMES`, `_domain_summary_has_recovery_distress`, `recovery_distress`. **Must contain**: normal `vip_data(n1)` / `vip_data(n2)` packet-in and DNAT/SNAT log lines. |
| `service_logs/edge_server_*/` | **Must NOT contain**: `mode=recovery`, `recovery_expires_at`, `recovery_expired`, `success_after_rebind`, `rebinds_used`, `_rebind_request_lease_after_autoreconnect`, `Rotated epoch`, `recovery_session_max_age_s`. **Must contain**: `mode=normal` epoch creations, `Created MongoClient` without `recovery_session_max_age_s` field. |
| `client_requests.csv` | Overall non-200 ≤ 5%. Any 503 responses should correlate with `terminal_reason="...:retries_exhausted"` in service logs. |
| `resource_stats.csv` | `server_count` and `storage_count` stable; no unexpected container churn. |
| `container_events.csv` | No unusual add/remove cycles tied to VIP changes. |
| `phases_snapshot.json` | Confirm the canonical 10-phase profile ran. |

**Secondary focus**: `elasticity_events.csv`, `per_node_stats.csv` — only needed if primary evidence shows an anomaly.

## Metrics & Success Criteria

| # | Criterion | How to check |
| --- | --- | --- |
| 1 | Zero recovery-related strings in controller logs | `grep -ci 'vip_data_recovery\|recovery=True\|_RECOVERY_DISTRESS' controller_lan*.log` → `0` |
| 2 | Zero recovery-related strings in edge-server logs | `grep -ri 'mode=recovery\|success_after_rebind\|recovery_expired\|rebinds_used' service_logs/` → `0` |
| 3 | All epoch creations are `mode=normal` | `grep -c 'mode=normal' service_logs/` ≥ 2 (one per LAN); `grep -c 'mode=recovery'` = 0 |
| 4 | No `recovery_session_max_age_s` in MongoClient creation log | `grep -ri 'recovery_session_max_age_s' service_logs/` → `0` |
| 5 | Terminal failures use new reason string | If any 503s occur: `grep 'retries_exhausted' service_logs/` matches; `grep 'rebinds_exhausted\|rotation_failed'` → `0` |
| 6 | Overall non-200 ≤ 5% | `metrics_stats.py` on `client_requests.csv` |
| 7 | No controller Python tracebacks | `grep -c 'Traceback (most recent call last)' controller_lan*.log` → `0` |
| 8 | Run completes all phases to `idle` | `current_phase.txt` = `idle` at run end |

## Checkpoints

| Trigger | Question | Evidence | Runner action |
| --- | --- | --- | --- |
| After phase `baseline` (~60s) | Are edge servers creating normal-mode epochs? | `grep 'Created MongoClient' service_logs/` | Report count; abort if any `mode=recovery` seen |
| After phase `local_moderate` (~180s) | Is VIP_DATA routing working normally? | `grep 'vip_data.*client=.*vip=.*real=' controller_lan1.log` | Report first 3 log lines; abort if none found |
| Run end | All success criteria met? | Full grep pass per criteria 1–8 | Report pass/fail per criterion |

## Validity Threats & Limitations

- **No synthetic failures**: without fault injection, the retry path (`retries_exhausted`) may not be exercised. A follow-up experiment with `--fault-plan` targeting storage backends can validate the backoff-only path under real failure.
- **Single run**: one clean run confirms the removal didn't break normal operation but doesn't prove resilience under stress. If anomalies appear, run a second replicate.
- **Env vars still present**: `osken-controller.env` still defines `VIP_DATA_RECOVERY_*` vars. They're harmless (no code reads them) but could confuse an operator. Defer cleanup to a follow-up env-file sweep.
- **Does not validate conntrack interaction**: this plan assumes the [conntrack_vip_routing plan](../../../vip_routing/implementation/plans/conntrack_vip_routing/conntrack_vip_routing_plan.md) is deployed together. If conntrack is not yet deployed, stale flow rules could still cause failure windows — but the edge server will now retry with backoff instead of rotating to recovery, which is the intended behavior.

## Artifact Contract

Standard run-folder layout per `testing_overview.md`:
```
metrics/<batch_dir>/<timestamp>_recovery_removed_val_a/
  client_requests.csv
  resource_stats.csv
  per_node_stats.csv
  container_events.csv
  elasticity_events.csv
  node_lifecycle_timings.csv
  phases_snapshot.json
  current_phase.txt
  controller_lan1.log
  controller_lan2.log
  service_logs/
    edge_server_*/
  controller_env_snapshot.env
```

No experiment-specific additional files expected.
