# Experiment Plan — Conntrack VIP_DATA Routing (v2 — ct_state fix)

**Status**: `ct_state` reply-rule bug fixed (2026-06-08). Design doc updated at
`docs/operation/vip_routing/implementation/plans/conntrack_vip_routing/conntrack_vip_routing_design.md`
(see §3k for the pitfall explanation).

## Intent

Evaluate whether OVS conntrack-based VIP_DATA routing eliminates the stale-rule
→ `AutoReconnect` → epoch-rotation failure cascade. The v5.5 baseline (static
DNAT/SNAT) achieved 56–65% failure in compute phases due to stale rules DNAT'ing
connections to removed backends for up to 120 s. This experiment runs the fixed
conntrack implementation and compares against the v5.5 baseline.

## Hypothesis / Expected Outcome

With the `ct_state` bug fixed, conntrack forward rules are deleted synchronously
on `unregister_storage_backend`, and reply rules correctly reverse-NAT traffic
via `ct(zone=N,nat)` actions. Expected outcomes:

1. **Overall failure rate ≤3%** (vs v5.5 B at 6.7%) — stale-rule `AutoReconnect`
   failures are prevented at the source.
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
  - Baseline: static DNAT/SNAT (v5.5 run, `install_vip_dnat_snat` for VIP_DATA).
  - Experiment: fixed conntrack forward + reply rules (this run).
- **Held constant**: same workload (`phases.json`), same `current_state_integrated.env`
  controller config, same `CLIENTS=8 DEVICES=600 NODES=100`, same Docker images
  (Python-only controller change, no rebuild needed), same WAN profile, same
  host/VM, no `--fault-plan`.

## Prerequisites

### Bug fix — ct_state reply-rule failure

The original conntrack implementation (Phases 1–4, deployed before 2026-06-08)
had a **critical bug**: reply rules matched on `ct_state=+est+trk`, but reply
packets never pass through a `ct()` action, so `ct_state` was always `0`. The
forward rule created the kernel conntrack entry correctly, but the reply rule
never fired → 100% connection failure.

**Fix** (deployed 2026-06-08):
- Reply rule **match**: replaced `ct_state=(34,34), ct_zone=N` with
  `ipv4_src=<backend_subnet/24>, tcp_src=27018`
- Reply rule **actions**: added `ct(zone=N,nat)` before `set_field(eth_src=vip_mac)`
- Domain differentiation: `ipv4_src=10.0.0.0/24` (n1) vs `ipv4_src=10.0.1.0/24` (n2)

See design doc §3f and §3k for full rationale.

### Files changed

Only two files were modified from the Phase 1–4 implementation:

| File | Change |
|---|---|
| `source/sdn_controller/_vip_routing/flows.py` | Rewrote `install_vip_data_reply_rule()` — ct_state match → L3/L4 match + ct(nat) action; added `_BACKEND_SUBNET` constant |
| `source/sdn_controller/_vip_routing/ingress.py` | Updated Packet-Out comment only |

No other controller files, Docker images, or test scripts changed. The
`state.py`, `vip_routing.py`, and `collect_resource_stats.py` files listed
in the original plan are unchanged from Phase 1–4.

## Run Matrix

| Run label | Routing mechanism | Phase file | Baseline reference |
| --- | --- | --- | --- |
| `conntrack_experiment` | Fixed conntrack forward + reply rules | `testing/phases.json` | v5.5 (static NAT, 56–65% compute failure) |

Single run. The v5.5 run serves as the static-NAT baseline — no separate
control run is needed. If results are borderline, a replicate may be added.

## Run Configuration

```bash
# Single experiment run — controller already has the fixed flows.py/ingress.py
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  RUN_LABEL=conntrack_experiment \
  PHASES_CONFIG=testing/phases.json \
  CLIENTS=8 DEVICES=600 NODES=100 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
```

No between-run code swaps needed. `setup_network` restarts the controllers,
which pick up the volume-mounted Python files. A fresh `setup_network` also
ensures the MAC→IP table is fully populated during topology discovery (the
MAC→IP learning issue discussed in `implementation_notes.md` only affects
controller restarts without topology rebuild).

## Focus & Evidence

**Primary focus**: `client_requests.csv` per-phase failure rates + edge server
service logs (`edge_server_n1.log`, `edge_server_n2.log`) for epoch rotation
count and `AutoReconnect` frequency.

**Secondary focus**: controller logs for "forward rule deleted" markers +
`resource_stats.csv` conntrack columns + OVS flow dumps confirming reply rules
have `n_packets > 0` (evidence the ct_state fix is active).

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

| # | Metric | v5.5 baseline | Experiment target | Primary artifact |
| --- | --- | --- | --- | --- |
| 1 | Overall failure rate | ~6.7% | ≤3% | `client_requests.csv` |
| 2 | Compute-phase failure (ramp/spike/plateau) | 56–65% | ≤5% | `client_requests.csv` |
| 3 | Storage-hotspot failure (stress/cross/reverse) | ≤15% | ≤5% | `client_requests.csv` |
| 4 | Baseline + local_moderate failure | 0% | 0% | `client_requests.csv` |
| 5 | Epoch rotations during storage-churn phases | ≥10 (v5.5 B: 33 total) | 0 | `edge_server_n1.log`, `edge_server_n2.log` |
| 6 | "forward rule deleted" log lines | 0 (not implemented) | ≥1 per `unregister_storage_backend` | `controller_lan1.log`, `controller_lan2.log` |
| 7 | `conntrack_entries_n1` + `conntrack_entries_n2` > 0 | 0 (columns empty) | >0 during active phases | `resource_stats.csv` |
| 8 | Reply rule `n_packets > 0` in OVS dumps | N/A | >0 for each active client | OVS flow dump (manual check) |
| 9 | Tier 2 storage exercise | `storage_count > 1` | `storage_count > 1` | `resource_stats.csv` |
| 10 | Tier 1 selective-sync ACTIVE both directions | ACTIVE | ACTIVE | `resource_stats.csv` / `controller_lan*.log` |
| 11 | Compute elasticity trigger | `server_count > 1` | `server_count > 1` | `resource_stats.csv` |
| 12 | All dynamic containers drained by idle | 0 dynamic at end | 0 dynamic at end | `container_events.csv` |

## Validity Threats & Limitations

- **Single-run comparison**: one conntrack run vs one baseline run is not
  statistically robust. If results are borderline, a replicate is warranted.
- **WAN non-determinism**: v5.4 A (2.0%) vs v5.4 B (8.1%) showed that WAN
  conditions alone can produce a 6-point spread with identical code. The
  baseline date may differ from the experiment date.
- **Conntrack does not fix DB query latency**: dashboard phases at 56–65%
  failure are driven by two factors — (a) stale-rule routing (fixed by
  conntrack) and (b) 2–3.5s DB query latency (not fixed). If query latency
  alone causes `serverSelectionTimeoutMS` expiration, epoch rotation may
  still fire. The ≤5% compute target assumes stale-rule elimination removes
  the dominant trigger.
- **Recovery VIP path still exists on edge side**: the edge server's
  `_MongoEpoch` recovery VIP logic is unchanged. If epoch rotation fires for
  any reason, the recovery path ≤51% success rate still applies.
- **ipv4_src subnet match is broader than ct_zone**: the reply rule matches
  any reply from the entire backend subnet (`10.0.0.0/24` or `10.0.1.0/24`),
  not just the specific backend. Non-VIP traffic from other backends on the
  same LAN would also match the reply rule, but `ct(nat)` would be a no-op
  (no conntrack entry) and the packet would be forwarded to the client
  unchanged — harmless noise in this closed test environment.
- **No Docker image rebuild**: the OVS and OS-Ken images already support
  conntrack. The controller changes are Python-only. The edge server image
  is unchanged (recovery VIP logic still present).

## Artifact Contract

Standard run-folder layout from `testing_overview.md` plus experiment-specific
columns `conntrack_entries_n1` / `conntrack_entries_n2` in `resource_stats.csv`.
No additional `analysis/` outputs beyond standard `cli_overview` / `phase_stats.py`.

## Changelog

| Date | Change | Rationale |
|---|---|---|
| 2026-06-08 | v2 — Simplified to single run; documented ct_state bug fix prerequisites; dropped control run (v5.5 baseline used instead) | ct_state reply-rule bug discovered and fixed; codebase already routes VIP_DATA via conntrack; control run redundant |
| 2026-06-08 | v1 run completed (`conntrack_experiment`, 11:29 UTC). 123K requests, 10/10 phases. Compute 1.4% failure (40× improvement). Storage-churn 0.04%. Zero epoch rotations. Overall 9.4% inflated by reverse_hotspot LAN2 WAN artifact. | results.md §1 — full analysis |

