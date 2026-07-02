# Golden Configuration

This document records the canonical sizing, mechanism toggles, and trigger
thresholds for the current content-discovery workload.

All toggles and thresholds are encoded in
`source/scripts/testing/controller_env_overrides/current_state_integrated.env`.

---

## Workload Sizing

| Parameter | Value | Source |
| --- | --- | --- |
| `WAN_RTT_MS` | `260` | v6 Tier 1 WAN curve where cross-region penalty is visible without timeout censorship |
| `CLIENTS` | `48` | v6 load volume for storage and Tier 1 stress |
| `CONTENT_ITEMS` | `6000` | v6 dataset cardinality for realistic query cost |
| `USERS` | `100` | Held constant across the current experiment families |
| `STORAGE_CPUS` | `0.10` | v6 storage calibration where a single node reaches about 46 percent CPU without elasticity |
| `VIP_HARD_TIMEOUT` | `60s` | Prevents timeout censorship at WAN >= 200 ms |

### Canonical Phase File

The sole canonical active workload profile is
`source/scripts/testing/phases.json`.

| Phase | Duration | Rate/client | Cross-region | Dominant stress |
| --- | --- | --- | --- | --- |
| `baseline` | `60s` | `1 r/s` | `0%` | Tier 0 control |
| `storage_storm` | `240s` | `4 r/s` | `90%` on `content_lookup` | Storage locality plus write/aggregation amplification |
| `tier1_hotspot` | `180s` | `5 r/s` | `95%` on `content_lookup` | Tier 1 hotspot response |
| `inter_hotspot_cooldown` | `300s` | `1 r/s` | `0%` | Drain and recovery observation |
| `compute_spike` | `180s` | `4 r/s` | `5%` on `content_lookup` | Feed-ranking compute pressure |
| `cooldown` | `120s` | `1 r/s` | `0%` | Cooldown-gated scale-in observation |

Non-canonical validation and diagnostic profiles live under
`source/scripts/testing/phases_override/`.

---

## Mechanism Toggles

| Parameter | Value | Purpose |
| --- | --- | --- |
| `STORAGE_PERSISTENT_RESERVE_ENABLED` | `1` | Tier 2 storage reserve enabled |
| `SS_ENABLED` | `1` | Tier 1 selective sync enabled |
| `MAX_DYNAMIC_STORAGE` | `5` | Up to 5 dynamic storage nodes per LAN |
| `MAX_DYNAMIC_COMPUTE` | `6` | Up to 6 dynamic compute nodes across LANs |

---

## Storage Trigger Bundle

The current storage activation boundary is `0.12 < tau <= 0.15`.

`0.12` is the highest threshold that still activates the reserve under the
calibration probe workload. It avoids over-sensitivity while still letting the
mechanism fire in the intended storage-heavy windows.

| Parameter | Value | Notes |
| --- | --- | --- |
| `SCALEUP_STORAGE_BASE_THRESHOLD` | `0.12` | Highest threshold that still activates |
| `SCALEUP_W_STORAGE_CPU` | `0.60` | Default weight |
| `SCALEUP_W_T_DB` | `0.40` | Default weight |
| `SCALEUP_STORAGE_CPU_FLOOR` | `1.5` | Default floor |
| `SCALEUP_STORAGE_CPU_SPAN` | `5` | Default span |
| `SCALEUP_T_DB_FLOOR` | `60` | Default floor |
| `SCALEUP_T_DB_SPAN` | `250` | Default span |
| `SCALEUP_STORAGE_REQUIRED` | `2` | Consecutive windows required |
| `SCALEUP_STORAGE_WINDOW_SIZE` | `5` | Sliding window |
| `SCALEUP_STORAGE_COOLDOWN_S` | `120` | Default cooldown |

---

## Compute Trigger Bundle

The cooldown value remains the load-bearing parameter for compute scale-down.

| Parameter | Value | Why it matters |
| --- | --- | --- |
| `SCALEUP_COMPUTE_BASE_THRESHOLD` | `0.20` | Lowered from `0.45` so feed-ranking-heavy but distributed load still triggers scale-out |
| `SCALEUP_CPU_FLOOR` | `3` | Lowered from `5` |
| `SCALEUP_T_PROC_FLOOR` | `15` | Lowered from `20` |
| `SCALEDOWN_COMPUTE_COOLDOWN_S` | `180` | Prevents premature removal during the storage-to-compute transition |
| `SCALE_DOWN_COMPUTE_REQUIRED` | `9` | Consecutive below-threshold windows |

---

## Infrastructure Fixes (Deployed, Not Tuneable)

These are code-level fixes confirmed by dedicated experiments. They are part of
the standard deployment, not operator-tuned knobs.

| Fix | Effect |
| --- | --- |
| Conntrack VIP_DATA routing | Eliminates stale-rule to AutoReconnect cascades during storage churn |
| Cross-LAN veth TX queue (`txqueuelen=10000`) | Eliminates TCP collapse on LAN2 under WAN-heavy runs |
| MAC-recycling collision fix in `node_registry.py` | Makes storage reserve activation robust when MACs are reused |
| Virtual-MAC mismatch fix in `resolve_peer_primary()` | Restores bidirectional Tier 1 activation |

---

## Canonical Launch Command

```bash
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  RUN_LABEL=<label> \
  PHASES_CONFIG=testing/phases.json \
  WAN_RTT_MS=260 CLIENTS=48 CONTENT_ITEMS=6000 USERS=100 STORAGE_CPUS=0.10 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
```

Use `testing/phases_override/phases_tier1_smoke.json` only when the goal is a
focused Tier 1 hotspot validation instead of the canonical integrated profile.
