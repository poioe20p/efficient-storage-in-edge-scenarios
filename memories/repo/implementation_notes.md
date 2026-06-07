# Implementation Notes

## Retry Architecture with Collective Failure Threshold (v5.5)

### Files Changed
- `source/docker/edge_server/source/edge_server_config.py`: Added 4 fields
- `source/docker/edge_server/source/vip_data_mongo_runtime.py`: 4 changes
- `docs/operation/vip_routing/vip_data_edge_epoch_and_recovery.md`: Added §5a, updated field tables

### Key Design Decisions
1. `recent_failures` counter on `_MongoEpoch`, reset on success in `_run_db_op_once`
2. Backoff: 100ms → 200ms → 400ms (3 attempts max) on same epoch
3. Threshold=5 triggers epoch rotation; 92% of runs are isolated (filtered by backoff)
4. `serverSelectionTimeoutMS` reduced from 3000→1000 (configurable)
5. `_rebind_request_lease_after_autoreconnect` inner try/except prevents infinite loop on rotation failure
6. Non-replay-safe writes keep old behavior: rotate immediately on first failure

### Env Vars (all have sensible defaults)
- `MONGO_RETRY_BACKOFF_MS=100`
- `MONGO_RETRY_MAX_ATTEMPTS=3`
- `MONGO_CONSECUTIVE_FAILURE_THRESHOLD=5`
- `MONGO_SERVER_SELECTION_TIMEOUT_MS=1000`
