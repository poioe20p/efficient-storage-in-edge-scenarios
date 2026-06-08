# Experiment Plan — Conntrack VIP_DATA Routing

## Intent

Evaluate whether OVS conntrack-based VIP_DATA routing eliminates the stale-rule
→ `AutoReconnect` → epoch-rotation failure cascade that drives 56–65% failure
in compute phases under the v5.5 baseline. Compare one conntrack run against
one static-NAT control run, same workload, same controller config.

## Hypothesis / Expected Outcome

If conntrack forward rules are deleted synchronously on
`unregister_storage_backend`, new connections will never be DNAT'd to a dead
backend, eliminating the primary `AutoReconnect` trigger. Expected outcomes:

1. **Overall failure rate ≤3%** (vs v5.5 B at 6.7%) — the 92% of isolated
   `AutoReconnect` failures are prevented at the source.
2. **Compute phases (compute_ramp / compute_spike / sustained_plateau) ≤5%**
   (vs 56–65%) — dashboard-heavy phases no longer cascade through epoch
   rotation during storage churn.
3. **Zero epoch rotations in edge server logs** during storage-churn phases
   (`storage_stress`, `cross_region_hotspot`, `reverse_hotspot`). Recovery
   path may still fire during compute phases if DB query latency alone causes
   timeouts, but storage-driven rotations should be absent.
4. **Conntrack entries visible** in `resource_stats.csv` (`conntrack_entries_n1`,
   `conntrack_entries_n2` > 0 during active phases) and controller logs show
   "forward rule deleted" on each `unregister_storage_backend`.

## RQ Linkage

Supports the service-quality baseline for RQ2 (metadata-aware backend
selection) and RQ3 (locality/readiness strategy). Stale-rule elimination is
a correctness prerequisite — if the routing substrate drops connections during
normal elasticity operations, no backend-selection or locality policy can be
evaluated fairly.

## Independent Variable & Held-Constant Set

- **Independent variable**: VIP_DATA routing mechanism.
  - Control: current static DNAT/SNAT (`install_vip_dnat_snat`).
  - Experiment: conntrack forward + reply rules (Phase 1–2 implementation).
- **Held constant**: same workload (`phases.json`), same `current_state_integrated.env`
  controller config, same `CLIENTS=8 DEVICES=600 NODES=100`, same images except
  the controller (Python-only change, no image rebuild needed), same WAN profile,
  same host/VM, no `--fault-plan`.

## Run Matrix

| Run label | Routing mechanism | Phase file |
| --- | --- | --- |
| `conntrack_ctrl` | Static DNAT/SNAT (current `flows.py`) | `testing/phases.json` |
| `conntrack_experiment` | Conntrack forward + reply rules | `testing/phases.json` |

Run order: control first to rebaseline the static-NAT failure rate on the
current images, then experiment. No code, env, or image changes between runs
other than the `flows.py` / `ingress.py` / `state.py` swap.

## Run Configuration

Both runs use the standard integrated-launch path. The only difference is
which `flows.py` / `ingress.py` / `state.py` is present on the VM.

```bash
# Control (static NAT)
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  RUN_LABEL=conntrack_ctrl \
  PHASES_CONFIG=testing/phases.json \
  CLIENTS=8 DEVICES=600 NODES=100 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1

# Experiment (conntrack) — after syncing the three changed controller files
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  RUN_LABEL=conntrack_experiment \
  PHASES_CONFIG=testing/phases.json \
  CLIENTS=8 DEVICES=600 NODES=100 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
```

Controller files to sync before the experiment run (Python-only, no image rebuild):
- `source/sdn_controller/_vip_routing/flows.py`
- `source/sdn_controller/_vip_routing/ingress.py`
- `source/sdn_controller/_vip_routing/state.py`
- `source/sdn_controller/vip_routing.py`
- `source/scripts/testing/collect_resource_stats.py`

Rollback for control: revert the five files above to pre-conntrack state.

## Focus & Evidence

**Primary focus**: `client_requests.csv` per-phase failure rates + edge server
service logs (`edge_server_n1.log`, `edge_server_n2.log`) for epoch rotation
count and `AutoReconnect` frequency.

**Secondary focus**: controller logs for "forward rule deleted" markers +
`resource_stats.csv` conntrack columns.

| Artifact | Shows |
| --- | --- |
| `client_requests.csv` | Per-phase, per-LAN, per-endpoint p95/p99 latency and HTTP failure rate via `phase_stats.py` |
| `service_logs/edge_server_n1.log`, `edge_server_n2.log` | `ERROR db_failure` count, epoch rotation count (`current_recovery_epoch_failed`), `AutoReconnect` frequency |
| `controller_lan1.log`, `controller_lan2.log` | "forward rule deleted" on each `unregister_storage_backend`, `vip_data(...)` per-client forward/reply rule installation |
| `resource_stats.csv` | `conntrack_entries_n1`, `conntrack_entries_n2` — should be >0 during active phases |
| `container_events.csv` | Storage container add/remove ground truth — correlates with expected rule deletion events |
| `elasticity_events.csv` | Storage scale-up/down timing — cross-reference with rule deletion log lines |
| `phases_snapshot.json` | Confirms phase order, durations, request mix |

## Metrics & Success Criteria

| # | Metric | Control expectation | Experiment target | Primary artifact |
| --- | --- | --- | --- | --- |
| 1 | Overall failure rate | ≤10% (v5.5 baseline ~6.7%) | ≤3% | `client_requests.csv` |
| 2 | Compute-phase failure (ramp/spike/plateau) | 50–70% (known cursor/epoch cascade) | ≤5% | `client_requests.csv` |
| 3 | Storage-hotspot failure (stress/cross/reverse) | ≤15% | ≤5% | `client_requests.csv` |
| 4 | Baseline + local_moderate failure | 0% | 0% | `client_requests.csv` |
| 5 | Epoch rotations during storage-churn phases | ≥10 (v5.5 B had 33 total) | 0 | `edge_server_n1.log`, `edge_server_n2.log` |
| 6 | "forward rule deleted" log lines | 0 (not implemented) | ≥1 per `unregister_storage_backend` | `controller_lan1.log`, `controller_lan2.log` |
| 7 | `conntrack_entries_n1` + `conntrack_entries_n2` > 0 | 0 (columns empty) | >0 during active phases | `resource_stats.csv` |
| 8 | Tier 2 storage exercise | `storage_count > 1` | `storage_count > 1` | `resource_stats.csv` |
| 9 | Tier 1 selective-sync ACTIVE both directions | ACTIVE | ACTIVE | `resource_stats.csv` / `controller_lan*.log` |
| 10 | Compute elasticity trigger | `server_count > 1` | `server_count > 1` | `resource_stats.csv` |
| 11 | All dynamic containers drained by idle | 0 dynamic at end | 0 dynamic at end | `container_events.csv` |

## Validity Threats & Limitations

- **Single-run comparison**: one run per mechanism is not statistically robust.
  If results are borderline, a replicate pair may be needed.
- **WAN non-determinism**: v5.4 A (2.0%) vs v5.4 B (8.1%) showed that WAN
  conditions alone can produce a 6-point spread with identical code. The
  control run may land on an unusually good or bad WAN day.
- **Conntrack does not fix DB query latency**: dashboard phases at 56–65%
  failure are driven by two factors — (a) stale-rule routing (fixed by
  conntrack) and (b) 2–3.5s DB query latency (not fixed). If query latency
  alone causes `serverSelectionTimeoutMS` expiration, epoch rotation may
  still fire. The ≤5% compute target assumes stale-rule elimination removes
  the dominant trigger.
- **Recovery VIP path still exists on edge side**: the edge server's
  `_MongoEpoch` recovery VIP logic is unchanged. If epoch rotation fires for
  any reason, the recovery path ≤51% success rate still applies.
- **No Docker image rebuild**: the OVS and OS-Ken images already support
  conntrack. The controller changes are Python-only. The edge server image
  is unchanged (recovery VIP logic still present).

## Artifact Contract

Standard run-folder layout from `testing_overview.md` plus experiment-specific
columns `conntrack_entries_n1` / `conntrack_entries_n2` in `resource_stats.csv`.
No additional `analysis/` outputs beyond standard `cli_overview` / `phase_stats.py`.
