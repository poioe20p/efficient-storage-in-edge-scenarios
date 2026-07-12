# Cross-Region Tier 2 — Implementation Plan

**Status**: 📋 Planned
**Depends on**: [Storage Persistent Reserve](../storage_persistent_reserve/README.md) (same-LAN Tier 2 warm — implemented)
**RQ3 Context**: [`tese/miscelineous/system_to_thesis_map_rq_v2.md`](../../../tese/miscelineous/system_to_thesis_map_rq_v2.md)

---

## Scope

Enable Tier 2 cross-region replica placement: spawn a MongoDB secondary of the
**remote** replica set in the **consumer** LAN, so consumers can read remote
data without crossing the WAN.

This plan covers two readiness profiles:

| Profile | When the replica exists | Activation cost | Idle cost |
|---|---|---|---|
| **Warm standby** | Pre-spawned at baseline, pre-synced, held outside VIP | Admission only (~instant) | Ongoing replication traffic + container resources |
| **Cold-start** | Spawned on demand when cross-region pressure detected | Full initial sync (minutes) | Zero |

---

## Architecture Summary

```
Controller LAN2 (consumer)
  │
  ├── Telemetry shows: t_db_p95_ms_per_lan["lan1"] > threshold
  │   (LAN2 consumers are hurting from cross-region reads to LAN1's data)
  │
  ├── Warm path:  pre-spawned rs_net1 secondary already READY_RESERVED
  │               → admit to VIP_DATA_N2 → LAN2 consumers read locally
  │
  └── Cold path:  no standby exists
                  → DataAlert(cross_lan_rs=True, owner_lan="lan1")
                  → spawn rs_net1 secondary in LAN2
                  → full initial sync from LAN1 primary via WAN
                  → SECONDARY → admit to VIP_DATA_N2
```

The `DataAlert` already has dormant fields (`cross_lan_rs: bool`, `owner_lan: str | None`)
— this plan activates them. The `_docker_run_storage` already accepts `rs_seed_host` —
this plan uses it for cross-region RS joins.

---

## Phases

| # | Phase | What it delivers | Test gate | Status |
|---|---|---|---|---|
| **0** | Foundation | Shared plumbing: env vars, seed host override, cross-region dispatch | Spawn a cross-region node manually, verify RS join | ✅ Implemented |
| **1** | Warm Standby | Pre-spawned cross-region standby; admit on demand | Standby READY → pressure detected → admitted → local reads work | ✅ Implemented |
| **2** | Cold-Start | On-demand cross-region spawn; full sync; admit | Pressure detected → spawn → sync → admitted → local reads work | ✅ Implemented |
| **3** | Post-Ground-Setting Fixes | Warm pre-spawn deferral; cross-region scale-down lifecycle | No re-spawn oscillation; standby pre-spawns after topology stable | ✅ Implemented |

**Phase 1 must be tested before Phase 2 starts.** Warm standby exercises the
entire cross-region pipeline (spawn, RS join, VIP registration, read serving)
with the simplest activation path. Cold-start adds the on-demand spawn and
sync-timing measurement on top of the same pipeline.

---

## Activation Signal

All RQ3 strategies (Tier 1, Tier 2 cold, Tier 2 warm) activate on the **same
detection signal**:  `t_db_p95_ms_per_lan[peer_lan] > threshold` (p95 DB time
for the peer LAN exceeds the configured threshold).  The threshold is
calibrated above baseline WAN transit (normal cross-region reads at 260ms WAN
≈ 300–500ms p95) and below saturation (2–10s p95).  Default is 1000ms,
tunable via env var per strategy:

| Strategy | Env var for threshold |
|---|---|
| Tier 1 | `TAU_DADOS_MS` (read by `selective_sync/hotness.py`) |
| Tier 2 cold/warm | `CROSS_REGION_DB_P95_THRESHOLD_MS` (read by `scaling_config.py`) |

Tier 1 additionally gates on hot-document concentration, cross-region ratio,
write ratio, and minimum reads — these are **strategy-intrinsic** conditions
(partial caching only works for concentrated, read-heavy workloads).  Tier 2
has no additional gates because a full replica works for any read pattern.

The comparison is: **same problem severity → different response strategy.**
Only one strategy is enabled per run (env-var gated).

---

## RQ3 Mapping

| RQ3 Strategy | Phase | Env override | Key vars |
|---|---|---|---|
| Remote only | Baseline | `rq3_remote.env` | All disabled |
| Tier 1 | Existing | `rq3_tier1.env` | `SS_ENABLED=1`, `TAU_DADOS_MS=1000` |
| Tier 2 cold | Phase 2 | `rq3_tier2_cold.env` | `CROSS_REGION_STORAGE_ENABLED=1`, `WARM=0`, `THRESHOLD_MS=1000` |
| Tier 2 warm | Phase 1 | `rq3_tier2_warm.env` | `CROSS_REGION_STORAGE_ENABLED=1`, `WARM=1`, `THRESHOLD_MS=1000` |

---

## Related Documents

| Document | Purpose |
|---|---|
| [Phase 0 — Foundation](./phase_0_foundation_cross_region_spawn.md) | Shared plumbing for both warm and cold |
| [Phase 1 — Warm Standby](./phase_1_cross_region_tier2_warm_standby.md) | Pre-spawned cross-region standby activation |
| [Phase 2 — Cold-Start](./phase_2_cross_region_tier2_cold_start.md) | On-demand cross-region replica spawn + sync |
| [Phase 3 — Post-Ground-Setting Fixes](./phase_3_post_ground_setting_fixes.md) | Warm pre-spawn deferral; cross-region scale-down lifecycle |
| [`system_to_thesis_map_rq_v2.md`](../../../tese/miscelineous/system_to_thesis_map_rq_v2.md) | Full thesis RQ framing |
| [Storage Persistent Reserve](../storage_persistent_reserve/README.md) | Same-LAN warm standby (existing, adapted for cross-region) |
| [`source/sdn_controller/elasticity/elasticity.py`](../../../source/sdn_controller/elasticity/elasticity.py) | `DataAlert`, `_handle_data`, `PrepareStandbyStorageAlert` |
| [`source/sdn_controller/elasticity/storage_node_manager.py`](../../../source/sdn_controller/elasticity/storage_node_manager.py) | `add_storage_node`, `_docker_run_storage` |
| [`source/sdn_controller/scaling_config.py`](../../../source/sdn_controller/scaling_config.py) | Env-var constants |
