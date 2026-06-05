# Run Summary - 20260604_205108_tier1_hotspot_enabled

## Conclusion

Authoritative Tier 1 enabled run. With `SS_ENABLED=1` and Tier 2 fully isolated, Tier 1 selective-sync activated in both hotspot directions, kept failures well below 1%, and cleaned up all selective containers. The first-direction DB-latency comparison shows Tier 1 eliminating the cross-region penalty present in the control run (84.5 ms → 3.58 ms).

## Main Points

- Controller env verified via `docker exec osken env` before launch: `SS_ENABLED=1`, `STORAGE_PERSISTENT_RESERVE_ENABLED=0`, `MAX_DYNAMIC_STORAGE=0`.
- All 5 phases completed.
- 160 Tier 1 events (69 LAN1 + 91 LAN2).
- `sel_sync_lan1_dyn1` and `sel_sync_lan2_dyn1` created, ran, and removed cleanly.
- First-direction DB latency: control 84.5 ms → enabled 3.58 ms (95.8% reduction).

## Evidence

### Container Lifecycle

- `sel_sync_lan2_dyn1`: added at `tier1_hotspot_n1` (63.5s), removed at `tier1_hotspot_n1` (294.9s)
- `sel_sync_lan1_dyn1`: added at `tier1_hotspot_n1` (77.6s), removed at `tier1_hotspot_n1` (278.9s)
- No residual `sel_sync_*` containers after `cooldown_n2`.

### Request Latency by Phase

| Phase | Requests | Failures | Rate |
| --- | ---: | ---: | ---: |
| `tier1_hotspot_n1` | ~11,600 | 6 | 0.05% |
| `cooldown_n1` | ~700 | 0 | 0.00% |
| `tier1_hotspot_n2` | ~17,500 | 3 | 0.02% |
| `cooldown_n2` | ~700 | 1 | 0.14% |

### Resource Shape

- `tier1_hotspot_n1` LAN2: `median_time_db_ms` = 3.58 ms, `median_time_total_ms` = 5.25 ms
- `tier1_hotspot_n2` LAN1: `median_time_db_ms` = 3.11 ms, `median_time_total_ms` = 5.34 ms

## Comparison with Control

| Metric | Control | Enabled |
| --- | ---: | ---: |
| Tier 1 events | 0 | 160 |
| `tier1_hotspot_n1` LAN2 `time_db` | 84.5 ms | 3.58 ms |
| `tier1_hotspot_n1` failures | 0.20% | 0.05% |
| Teardown | N/A | Clean |
