# Experiment Plan — Tier 1 Activation Smoke Test (Topology Fix Verification)

**Status**: 🔵 Designed · **Date**: 2026-06-26
**Parent**: [`rq1_eval_v2_findings.md`](../../../../source/scripts/testing/analysis/rq1/rq1_eval_v2_findings.md) §Remaining Issues §1

## Intent

Verify that the topology resolution fix in `topology.py` restores **bidirectional**
Tier 1 selective-sync activation. The `resolve_peer_primary()` method previously
iterated virtual MACs (`_peer_storage_macs_n*`) and looked them up in a map keyed
by real Docker MACs (`_peer_storage_roles`), causing the lan2→lan1 direction to
always fail with "no primary known for owner=lan2." The fix uses a two-step
resolution: confirm primary existence via `_peer_storage_roles` (real MACs),
then resolve the IP via `_peer_storage_macs_n*` → `peer_hosts` (virtual MACs).

This is a **binary gate**, not a measurement experiment. The single question:
**does `sel_sync_lan1_dyn*` appear in `node_lifecycle_timings.csv`?**

The lan1→lan2 direction (lan2 controller spawns `sel_sync_lan2_dyn*`) has
always worked — it serves as the positive control.

## Hypothesis / Expected Outcome

If the topology fix works:
- `node_lifecycle_timings.csv` contains `sel_sync_lan1_dyn*` container entries
  with lifecycle `add → ready(ACTIVE) → remove` on the lan1 controller.
- `node_lifecycle_timings.csv` also contains `sel_sync_lan2_dyn*` (positive control,
  lan1→lan2 direction — already confirmed working in v2).

If the fix does NOT work:
- `sel_sync_lan1_dyn*` is absent. Debug required before full RQ1 replicate rerun.

## RQ Linkage

Supports RQ1 (Information Acquisition pillar) by ensuring Tier 1 mechanism
integrity. Without bidirectional Tier 1, the thesis cannot provide the full
multi-tier reaction-latency comparison. This smoke test gates the RQ1 v2-replicate
rerun.

## Independent Variable & Held-Constant Set

- **Independent variable**: none — this is a single-run verification
- **Held constant**: Push mode, golden config, both hotspot directions

| Parameter | Value | Rationale |
|---|---|---|
| Phase file | `testing/phases_override/phases_tier1_smoke.json` | 5 phases, ~9 min: baseline → hotspot_lan2→lan1 → cooldown → hotspot_lan1→lan2 → idle. Both hotspot directions present. |
| `TELEMETRY_SOURCE` | `zmq` (Push) | No blind spot — gives Tier 1 the best chance to activate |
| Controller env | `current_state_integrated.env` | Golden config |
| `CLIENTS` | 8 | Standard |
| `DEVICES` | 600 | Standard |
| `NODES` | 100 | Standard |
| `WAN_RTT_MS` | 10 | Default metro — required for Tier 1 breach gate |
| `SS_ENABLED` | 1 | Required |
| Images | Current HEAD with topology fix | Must include: `node_registry.py` B1+B2, `elasticity.py` B1, `topology.py` `resolve_peer_primary()` two-step fix |

## Run Configuration

Single run — Push mode with minimal phases.

### Pre-run Checklist

- [ ] Cloud VM host rebooted
- [ ] `topology.py` fix verified on cloud VM (`grep 'Step 1.*confirm.*primary'`)
- [ ] `phases_override/phases_tier1_smoke.json` synced to cloud VM
- [ ] `current_state_integrated.env` is golden config
- [ ] `sudo -n` working

### Launch

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=tier1_smoke \
  PHASES_CONFIG=testing/phases_override/phases_tier1_smoke.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  CLIENTS=8 DEVICES=600 NODES=100 \
  2>&1"
```

## Focus & Evidence

**Primary — single binary check:**

| # | Measurement | Artifact | Question |
|---|---|---|---|
| 1 | `sel_sync_lan1_dyn*` lifecycle | `node_lifecycle_timings.csv` | Does the lan2→lan1 Tier 1 direction activate? |

**Secondary — positive control:**

| # | Measurement | Artifact | Question |
|---|---|---|---|
| 2 | `sel_sync_lan2_dyn*` lifecycle | `node_lifecycle_timings.csv` | Does the lan1→lan2 direction still work? |

**Tertiary — health:**

| # | Check | Artifact |
|---|---|---|
| 3 | No `no primary known` warnings | `controller_lan1.log` |
| 4 | No tracebacks | `controller_lan1.log`, `controller_lan2.log` |
| 5 | All 5 phases complete | `current_phase.txt` |

## Metrics & Success Criteria

| # | Criterion | How checked | Pass condition |
|---|---|---|---|
| 1 | Bidirectional Tier 1 | `grep 'sel_sync_lan1_dyn' node_lifecycle_timings.csv` | ≥ 1 row with lifecycle state `ACTIVE` |
| 2 | Positive control | `grep 'sel_sync_lan2_dyn' node_lifecycle_timings.csv` | ≥ 1 row with lifecycle state `ACTIVE` |
| 3 | No topology warnings | `grep -c 'no primary known' controller_lan1.log` | 0 |
| 4 | No crashes | `grep -c 'Traceback' controller_lan*.log` | 0 |
| 5 | Run completes | `cat current_phase.txt` | `idle` |

**Gate decision**: If criterion 1 passes → proceed to RQ1 v2-replicate rerun.
If criterion 1 fails → debug topology fix before any rerun.

## Validity Threats

1. **Single run** — if Tier 1 activation is probabilistic (timing-dependent topology
   publication), one run may not be representative. Mitigation: if criterion 1 fails,
   run a second smoke test before declaring the fix broken.

2. **Short workload** — 180s hotspot phases may not give enough time for the
   sliding-window threshold + cooldown to trigger Tier 1. Mitigation: the 180s
   duration matches the full phases.json hotspot phases that successfully triggered
   Tier 1 in v2 (lan1→lan2 direction).

3. **No compute/storage exercise** — the smoke test workload is designed for Tier 1
   only. Reserve and compute may not fire. This is intentional — the gate is
   Tier 1-specific.

## Artifact Contract

Standard run-folder layout per `testing_overview.md`. Controller logs must be
preserved (do NOT delete after post-run — the `no primary known` check requires them).

Post-run checks (on cloud VM, before log deletion):

```bash
# Binary gate check
grep 'sel_sync_lan1_dyn' metrics/<ts>/node_lifecycle_timings.csv
grep 'sel_sync_lan2_dyn' metrics/<ts>/node_lifecycle_timings.csv

# Topology warnings
sudo grep -c 'no primary known' metrics/<ts>/controller_lan1.log

# Tracebacks
sudo grep -c 'Traceback' metrics/<ts>/controller_lan*.log
```

---

## Changelog

| Date | Change | Rationale |
|------|--------|-----------|
| 2026-06-26 | Initial plan — Tier 1 topology fix smoke test | Gates RQ1 v2-replicate rerun |
