# Run Summary - 20260604_204334_tier1_hotspot_control

## Conclusion

Authoritative control run for Tier 1 activation. With `SS_ENABLED=0` and Tier 2 fully isolated (`STORAGE_PERSISTENT_RESERVE_ENABLED=0`, `MAX_DYNAMIC_STORAGE=0`), zero selective-sync events appeared. The run serves as the baseline for the Tier 1 activation comparison.

## Main Points

- Controller env verified via `docker exec osken env` before launch.
- Zero `SelectiveSync` / `sel_sync` events in either controller log.
- All 5 phases completed.
- `tier1_hotspot_n1` LAN2 median `time_db` = 84.5 ms — the cross-region penalty without Tier 1.

## Evidence

### Request Latency by Phase

| Phase | Requests | Failures | Rate |
| --- | ---: | ---: | ---: |
| `warmup` | ~1,000 | 0 | 0.00% |
| `tier1_hotspot_n1` | ~12,700 | 25 | 0.20% |
| `cooldown_n1` | ~200 | ~140 | ~67% |
| `tier1_hotspot_n2` | ~600 | 7 | ~1.2% |
| `cooldown_n2` | ~350 | 1 | 0.29% |

### Resource Shape (tier1_hotspot_n1)

- LAN1 `median_time_db_ms` = 2.05 ms
- LAN2 `median_time_db_ms` = 84.50 ms
- LAN2 `median_time_total_ms` = 86.59 ms

## Caveats

- Cooldown phases suffered from network namespace teardown (`Cannot open network namespace`), causing high failure rates unrelated to Tier 1.
- `resource_stats.csv` only covers `warmup`, `transition`, and `tier1_hotspot_n1`.
