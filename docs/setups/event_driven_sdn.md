# Event-Driven SDN Rollout (Step-by-Step)

## 1. MongoDB Collections

- `events` (time-series): `{dpid, src, dst, in_port, out_port, vlan, buffer_id, total_len, reason, seen_count, ts}`
- `decisions`: `{action, params, priority, createdAt, status, error?, tsApplied?, idempotencyKey}`
- `popularity_ts` (time-series aggregates): `{flow_key, window, count, bytes, ts}`
- Optional safety nets: `nodes`, `links`, and `resume_tokens` (`{streamId, token, ts}`) for change-stream restarts

Set indexes right away:

- `events`: TTL on `ts` (24–72h) + meta `{dpid, ts}` or `{src, dst, ts}`
- `decisions`: unique `idempotencyKey`, plus `{status, createdAt}`
- `popularity_ts`: TTL that matches your sliding-window horizon

## 2. Controller Logging (OS-Ken App)

- Keep current multiprocessing queue so packet_in never blocks
- Add optional sampler (first N packets per flow or every Kth packet)
- Export Prometheus counters: packet_in total, queue depth, failed inserts

## 3. Planner Job (produces decisions)

- Run every 5s in a lightweight worker or cron thread
- Query `events` from the last 30s grouped by `{src, dst, dpid}`
- Calculate PPS/bytes; pick flows above threshold/top-K
- Insert into `decisions`: `{action: "prioritize_flow", params, priority: 5, status: "pending", idempotencyKey}`

## 4. Actuator Service (consumes decisions)

- Separate Python process with `pymongo.watch`
- Filter change stream for new inserts with allowed actions + status `pending`
- Call OS-Ken adapters per action, then update document with `status`, `tsApplied`, and `error` if something fails
- Skip work if same `idempotencyKey` already applied

## 5. Actions to Implement First

- `prioritize_flow`: match + `set_queue=queue_id` then `output` (ensure OVS QoS/queues exist)
- `block_flow`: match + high-priority drop rule
- `mirror_flow`: match + duplicate output to original and `mirror_out_port`
- `reroute_flow` (later): match + new `out_port` overriding learned path

## 6. Immediate To-Do List

1. Stand up Mongo collections with TTL + indexes
2. Add sampler/metrics to OS-Ken logging path
3. Build Planner v0 (threshold-based)
4. Build Actuator v0 covering `prioritize_flow` and `block_flow`
5. Extend actuator for `mirror_flow`, then experiment with reroute logic
