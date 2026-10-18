# RQ2 v5 — W1.1 evidence: the db seat was path-bound, not store-bound

> **Status:** deposited 2026-10-16 (W1 evidence, per `rq2v5_plan.md` S1/S8).
> Source data: v4 db run folders on `cloud-vm-rq2`
> (`source/scripts/testing/metrics/20261014_*`), episode windows only.
> **Purpose:** the measurement that justifies the v5 seat recalibration
> (member saturation required for H1's `t_db` headroom) and the D21b
> distribution requirement.

## 1. Method (reproducible)

Per run, parse the edge window log `window_log_lanX.jsonl` and keep windows
with `window_end` inside the run's episode bounds (from the run's per-run
metrics JSON episode start/end). Per window:

- **edge units** = number of entries in `servers` (non-heartbeat-only);
- **delivered requests** = sum of `servers[*].request_count` (all request
  kinds; offered rate is ~1200/window = 24 clients x 5 rps x 10 s);
- **member CPU (win-max)** = max of `storage_servers[*].avg_cpu_percent`;
- **t_db** = `domain_summary.avg_time_db_ms`;
- client completion/p50 from `client_requests.csv` (episode rows, v4 pipeline
  conventions).

Arms: `none` (labels `none_db_42_r1,43,44,45,46,47,48`) and `comp`
(`comp_db_42,43,44,45,46_r1,47,48`) — 7 valid seeds each; means over
episode windows.

## 2. Result

| quantity (db, episode) | `none` | `comp` | reading |
| --- | --- | --- | --- |
| edge units per lane (mean over windows) | 1.0 | 1.9 (1 static + 1 spawned) | the only intervention that changed delivery |
| edge-delivered requests/window (of ~1200 offered) | ~1083-1103 (~90 %) | ~1186 (~99 %) | delivery recovers when the edge set doubles |
| single-member CPU, win-max mean (l1/l2) | 68.5/70.0 % | 72.4/73.0 % | the SAME single member absorbed FULL delivery at ~72-73 % -> >= 27 pp headroom |
| `t_db` (domain `avg_time_db_ms`, l1/l2) | ~62/63 ms | ~60/64 ms | member service leg flat - no t_db headroom existed at `sc=0.15` |
| client completion / p50 | 92/93 % @ 1.9/1.7 s | 99.8 % @ 27/49 ms | the deficit was the client-facing path, not the member |

## 3. Interpretation carried into v5

1. The v4 db press was data-*heavy* but **path-bound**: the member never
   approached saturation (headroom >= 27 pp in every arm), and recovery was
   produced by widening the edge-mediated request path, not by any storage
   action.
2. H1 ("storage-only scale-up lowers `t_db`") can only be tested with `t_db`
   headroom -> the v5 db seat lowers `STORAGE_CPUS` (candidate 0.07-0.11,
   start 0.09) with `EDGE_CPUS=1.20` pinned.
3. The band requirement (D21b): with storage selection being strict argmin,
   even a delivered storage add would concentrate on one member; the epsilon
   band + two-wave renewal is the distribution mechanism (see plan S3).
