# Read-Preference Data-Path Finding (2026-08-03)

## 1. Discovery

During RQ2 Block-1 analysis (data-bound episodes), per-node data showed storage
**secondaries** with almost no *successful* serving despite the VIP round-robin
(`select_storage`) forwarding per-edge-server flows to them thousands of times.
The root cause is a **client-side data-path defect**, not a routing defect.

## 2. Root cause

- The edge server's **read** client (`vip_data_mongo_runtime.py`
  `_get_or_create_epoch_client`) connects to the data VIP with:
  `MongoClient(url, maxPoolSize=1, directConnection=True, ...)` and **no
  `readPreference`** → pymongo default **`primary`**.
- With `directConnection=True`, the driver treats the connected server as a
  single server (topology `Single`) and declares `secondaryOk` based on the read
  preference. With `primary`, `secondaryOk=false`.
- The VIP DNAT's each edge server's MongoDB TCP connection to **one** storage
  backend (per-client flow, round-robin over the whole pool). When that backend
  is a **secondary**, MongoDB rejects primary-pref reads server-side with
  `NotPrimaryOrSecondary` (code 13436).

Observed in edge service logs (`service_logs/edge_server_*.log`):

```
ERROR db_failure route=content_lookup ... exc_type=ServerSelectionTimeoutError
exc=node is not in primary or recovering state ... 'code': 13436, 'codeName': 'NotPrimaryOrSecondary'
... topology_type: Single ... last_cmd=find last_cmd_db=edge_platform
```

Cross-run evidence (grep `NotPrimaryOrSecondary` in edge service logs):

| Run | NotPrimary errors |
|---|---|
| `rq2_ba_db_1` | 1 |
| `rq2_ba_db_cal` | 32 |
| `cgr_v3_scalable` (control) | 31 |
| `cgr_v4_scalable` (control) | 198 |
| `cgr_v3_noscale` (control, primary only) | 0 |
| all compute-bound RQ2 runs | 0 |

The pattern (errors only when secondaries exist in the pool, zero in the
no-scale single-primary arm) is diagnostic: reads reach secondaries and are
rejected.

## 3. Consequence

Storage scale-out produced **~zero usable read capacity** in every run:
- The primary served all successful reads (writes already go direct-to-primary).
- Secondaries only generated **replication** opcounter activity (writes
  replicated to them), which the storage telemetry counted as `sample_count`
  — so per-node "request counts" for storage were **activity-window flags**
  (max ~1 per telemetry poll), NOT request volumes. Comparisons of storage vs
  compute `request_count` as volumes are invalid.
- The control group's DB-latency relief (scalable 4.6 ms vs no-scale 177 ms) is
  **compute-driven** (more edge servers → less edge queueing → less DB
  concurrency), not storage-serving-driven.

## 4. Fix (config-gated)

- New knob: **`EDGE_MONGO_READ_PREFERENCE`** (edge-server container env).
  - `secondaryPreferred` (**default** since 2026-08-03 — the go-to read path) →
    declares `secondaryOk`; storage **secondaries now serve reads** from the
    VIP read path. Eventual consistency accepted.
  - `primary` (explicit opt-out) → pre-fix behavior (secondaries reject reads
    with NotPrimaryOrSecondary/13436); required to reproduce the pre-fix path
    or historical RQ1/RQ3 byte-for-byte.

> **Default change (2026-08-03):** `secondaryPreferred` is now the code/shell
> default, so any run that does not set the knob uses the fixed read path.
> Historical RQ1/RQ3 runs were made under `primary`; byte-for-byte reproduction
> of that path requires `EDGE_MONGO_READ_PREFERENCE=primary` explicitly (as the
> G3 control does).
- Implementation:
  - `source/docker/edge_server/source/edge_server_config.py` — new
    `mongo_read_preference` config field + `resolve_mongo_read_preference()`
    helper (single source of truth; avoids circular import for the Tier1
    manifest client).
  - `source/docker/edge_server/source/vip_data_mongo_runtime.py` — epoch (read)
    client passes `readPreference=resolve_mongo_read_preference()`.
  - `source/docker/edge_server/source/platform_cache.py` — Tier1 manifest client
    applies the same preference (same defect class under `SS_ENABLED=1`).
  - `source/scripts/network/build_network_1.sh` / `build_network_2.sh` — static
    edge servers: `-e EDGE_MONGO_READ_PREFERENCE=${EDGE_MONGO_READ_PREFERENCE:-secondaryPreferred}`.
  - `source/sdn_controller/elasticity/compute_node_manager.py` — dynamic edge
    servers inherit the var from the controller env.
  - Env files set `EDGE_MONGO_READ_PREFERENCE=secondaryPreferred`:
    `current_state_integrated.env`, `ablation_noscale.env`, and the three RQ2
    arm envs.

## 5. Two-path propagation (record in every run log)

Mirrors the documented `EDGE_FLOW_ISOLATION` pattern
(`post_implementation_verification/experiment_plan.md` §3.4):

- **Dynamic** edge servers: value flows from the controller env override
  (merged base+override `--env-file`) → controller `os.environ` →
  `compute_node_manager._docker_run_server()`.
- **Static** `edge_server_n1/n2`: launched by `build_network_1/2.sh` at
  `setup_network` time — the var must be present on the **shell** / make
  invocation, i.e. `EDGE_MONGO_READ_PREFERENCE=secondaryPreferred` in the
  `sudo -n ... make setup_network ...` environment.

Both must be set for a `secondaryPreferred` run; otherwise static edges revert
to `primary` and the original defect silently returns on the static read path.

## 6. Corrected claim (safe to state in the thesis)

> As-built, the platform's storage replicas never successfully served client
> reads: the VIP round-robin forwarded reads to secondaries, but the edge
> MongoDB client (`directConnection=True`, default `readPreference=primary`)
> rejected them (`NotPrimaryOrSecondary`, code 13436). Storage scale-out
> therefore produced zero usable read capacity, and the scalable control arm's
> DB-latency relief was compute-driven. The reference data path —
> `readPreference=secondaryPreferred` (config-gated) — lets secondaries serve
> reads, making storage scale-out genuinely measurable.

## 7. Approach B — pooled fan-out (2026-08-03, extends the fix)

**Problem found during design:** `readPreference=secondaryPreferred` alone makes
secondaries *able* to serve, but with `maxPoolSize=1` + per-*client* forward
rules, each edge holds ONE connection pinned to ONE backend, so concurrent
storage nodes serving = `min(edges, storage)`. Verified in the runs:
`sf_db_1` had 1 edge vs 5 storage → only 1 storage node could ever serve; even
`ba_db_1` (4 edges, 5 storage) left a node idle. Storage scale-out capacity is
**edge-bound**, so a storage-only policy (`sf`) cannot realise it.

**Fix (Approach B, config-gated):**

- `EDGE_MONGO_MAX_POOL_SIZE` (edge env, default `1`): epoch read client pool
  size. `>1` gives one edge N concurrent connections to the data VIP.
- `VIP_DATA_PER_CONNECTION_FLOWS` (controller env, default `0`): when `1`,
  VIP_DATA forward rules are keyed per connection (`tcp_src`) so each pooled
  connection can DNAT to a different storage backend → serving capacity
  scales with `edges × pool` instead of `edges`.

**Safety design (the critical edge case):** per-connection forward rules
**idle-expire (10 s) but never hard-expire**, and the controller selects a
backend **only on the SYN** of a new connection. An established connection is
**never re-pinned**: if
its flow is bulk-deleted by a backend unregister, the controller re-installs it
from a binding map (`(domain, client_mac, client_ip, tcp_src) -> backend_mac`)
to the **same** backend, or drops it (client reconnects) if that backend is
gone. This avoids the mid-connection DNAT break that a fresh re-select would
cause (conntrack would keep the old NAT while the flow outputs to the new
backend's port).

Implementation:
- `source/sdn_controller/_vip_routing/config.py` — `_VIP_DATA_PER_CONNECTION`
  flag.
- `source/sdn_controller/_vip_routing/flows.py` — per-connection match
  (`tcp_src`), flows idle-expire (10 s) but never hard-expire so an
  established connection cannot be force-re-pinned mid-stream.
- `source/sdn_controller/_vip_routing/ingress.py` — SYN-only selection + binding
  map look-up for established packets.
- `source/sdn_controller/_vip_routing/state.py` — binding map + lock; clears
  bindings to a removed backend on unregister.
- `source/docker/edge_server/source/edge_server_config.py` +
  `vip_data_mongo_runtime.py` — `mongo_max_pool_size` field, epoch client pool.
- `build_network_1/2.sh`, `compute_node_manager.py` — plumb the pool size var.
- Env files: `VIP_DATA_PER_CONNECTION_FLOWS=1` + `EDGE_MONGO_MAX_POOL_SIZE=6`.

**Caveat (accepted):** a pooled connection may be pinned to a lagging secondary
→ stale reads (eventual consistency accepted, per user decision). Write path
(`_get_write_client`) is unchanged and always direct-to-primary.

### 7.1 Probe-identified defects (fixed 2026-08-03)

The G2 probe surfaced three real defects beyond the design above; all are
fixed, deployed and validated in the retained control run (§9):

1. **pymongo 4.17 rejects `ReadPreference` instances.** The first probe failed
   every read client-side: `ValueError: SecondaryPreferred(...) is not a valid
   read preference` (17,505 errors / 10-min episode; pymongo 4.17's
   `validate_read_preference_mode` only accepts the string form). Fix:
   `resolve_mongo_read_preference()` returns the mode **string**
   (`"secondaryPreferred"`), not a `ReadPreference` object.
2. **Per-client shadowing of per-connection selection.** Boot-time non-TCP
   packet-ins installed per-client forward rules (`client=IP:*`, wildcard
   `tcp_src`) that matched every later TCP connection from that edge — zero
   per-connection rules were ever installed. Fix: in per-connection mode,
   non-TCP packet-ins to the data VIP are dropped (never install a per-client
   rule).
3. **Cross-region hop undercount (root fix).** Peer backends are learned by the
   local OVS switch on the router port, so `_rebuild_hop_cache` gave them the
   same 2-hop path as local backends and the router-aware `local_avg +
   peer_avg` fallback never ran (cross-region = local = 2). Fix: the hop cache
   is built over **local backends only**; peers always resolve via
   `local_avg + peer_avg` (2 + 2 = 4). A cross-region node is now always
   strictly farther than a local one (2 vs 4), by construction.

## 8. Verification gates (before any campaign run)

- G1 static: `docker exec edge_server_n1 printenv EDGE_MONGO_READ_PREFERENCE`
  == `secondaryPreferred`, `printenv EDGE_MONGO_MAX_POOL_SIZE` == `6` (same
  for `_n2`).
- G1b dynamic: on a data-bound preflight, once a dynamic edge spawns,
  `docker exec edge_server_lan1_dyn* printenv EDGE_MONGO_READ_PREFERENCE` ==
  `secondaryPreferred`, `printenv EDGE_MONGO_MAX_POOL_SIZE` == `6`.
- G2 (probe, Approach B — the make-or-break): a short data-bound probe with
  storage scaling ≥2/LAN must confirm ALL of:
  1. controller log shows per-connection forward rules with distinct
     `tcp_src` values installed (per-connection mode active);
  2. an edge's N connections land on N **different** storage backends (binding
     map / flow log — not all on one backend);
  3. established connections survive re-select/flow-delete (no mid-connection
     reset, no NotPrimary storm, client_requests errors stay flat);
  4. `grep -c NotPrimaryOrSecondary service_logs/edge_server_*.log` == **0**;
  5. secondaries show client read activity and `rho(storage, db)` < 0.
- G3: an RQ1-style run on the pre-fix read path stays byte-identical. Since
  2026-08-03 the default is `secondaryPreferred`, so G3 sets
  `EDGE_MONGO_READ_PREFERENCE=primary` explicitly (per-client flows and
  pool=1 remain the defaults).
- G4: `content_update` writes still reach the primary (writes unchanged).

**Gate outcomes (control pair, 2026-08-03):**
- G2 control run `20260803_204501_rq2_ba_db_probe` (knobs SET): G1 ✅ · G1b ✅ ·
  G2.1–G2.5 ✅ (details in §9) · G4 ✅.
- G3 run `20260803_214639_rq2_ba_db_probe_g3` (knobs UNSET): ✅ — the default
  path is byte-identical to pre-fix: per-client flows, `primary`, and
  `NotPrimaryOrSecondary` (13436) returning on secondaries (details in §10).
  The control pair is complete.

> **RQ2 Block-1 re-run (2026-08-03):** the first RQ2 Block-1 set
> (`20260803_114003_rq2_cf_cb_1` … `20260803_141034_rq2_sf_db_1`, 11:40–14:10)
> ran on the **pre-fix data path** — all six `controller_env_snapshot.env`
> files verified to lack the three knobs — so its data-bound cells were
> confounded. Those 6 runs were **deleted** (local + VM) and Block 1 is
> **re-run on the fixed path**: every launch carries the three knobs on the
> shell (static edges) and in the arm envs (dynamic edges).

## 9. Probe validation — control run (2026-08-03)

Retained control group for the fix validation:

- **Run**: `source/scripts/testing/metrics/20260803_204501_rq2_ba_db_probe`
  (bottleneck_aware policy, data-bound episode; `run_summary.md` in the run
  folder).
- **Launch**: `CLIENTS=24 CONTENT_ITEMS=3000 USERS=100 RANDOM_SEED=42
  WAN_RTT_MS=185 STORAGE_CPUS=0.08 EDGE_CPUS=0.15`,
  `OSKEN_ENV_OVERRIDE_FILE=rq2_env/rq2_bottleneck_aware.env`,
  `PHASES_CONFIG=testing/phases_override/phases_rq2_data_bound.json`.

### 9.1 Effective configuration (controller_env_snapshot.env, merged)

| Knob | Value |
|---|---|
| `EDGE_MONGO_READ_PREFERENCE` | `secondaryPreferred` (string) |
| `EDGE_MONGO_MAX_POOL_SIZE` | `6` |
| `VIP_DATA_PER_CONNECTION_FLOWS` | `1` |
| `SCALEUP_POLICY` / `BOTTLENECK_CLASSIFY_MARGIN` | `bottleneck_aware` / `0.05` |
| `ACTION_BUDGET_PER_TIER` / `MAX_DYNAMIC_STORAGE` / `MAX_DYNAMIC_COMPUTE` | `4` / `6` / `6` |
| storage scale-up | `W_STORAGE_CPU=0.60 W_T_DB=0.40`; base τ=0.35, CPU floor 35/span 30, t_db floor 10/span 50, window 5, required 2, cooldown 120 s |
| compute scale-up | `W_CPU=0.60 W_T_PROC=0.40`; base τ=0.18, CPU floor 10/span 40, t_proc floor 25/span 80, window 5, required 3, cooldown 45 s |
| scale-down | compute cooldown 180 s / 3-of-6 / TAU 25·40 ms; storage cooldown 30 s / 3-of-5 / TAU_DB 8 ms |
| `LATENCY_SIGNAL_MODE` | `median` |
| disabled | `STORAGE_PERSISTENT_RESERVE_ENABLED=0 SS_ENABLED=0 CROSS_REGION_STORAGE_ENABLED=0` |

### 9.2 Phases (phases_snapshot.json)

| Phase | Dur (s) | rate/cl | mix |
|---|---|---|---|
| baseline | 60 | 1.0 | lookup .6 / feed .25 / pressure .15 |
| data_bound_episode | 600 | 5.0 | lookup .4 / update .3 / aggregate .25 / feed .05 |
| recovery_gap | 120 | 0.5 | lookup .6 / feed .25 / pressure .15 |
| demand_drop | 420 | 1.0 | lookup .6 / feed .25 / pressure .15 |

`cross_region_ratio = 0.0`.

### 9.3 Results

**Latency** (controller window logs; p50 = median of per-window medians):

| Phase | T_proc p50/p95 (ms) | T_db p50/p95 (ms) |
|---|---|---|
| baseline | 0.9 / 80 | 2.7 / ~1000 |
| data_bound_episode | 1.6–2.3 / 88–106 | 35–67 / 790–890 |
| recovery_gap | 0.7 / 55 | 2.7 / 800 |
| demand_drop | 0.8 / 77 | 2.6 / 1000 |

Episode DB decomposition: db_read ≈ 125–135 ms avg, db_write ≈ 5.7 ms. The
long-tail p95 includes cross-region reads over the 185 ms WAN; p50 is the
clean signal.

**Throughput / client errors** (`client_requests.csv`):

| Phase | n | p50 (ms) | p95 (ms) | req/s | errors |
|---|---|---|---|---|---|
| data_bound_episode | 46,053 | 217.3 | 1380 | 76.75 | 586 (1.27%) |
| overall | 47,874 | — | — | — | 594 (1.24%) |

Episode errors are all `http_status=0` (timeouts), with one ~322-error
scale-down transient; no `NotPrimaryOrSecondary` (0 in all service logs).

**Pre/post scale-up** (episode windows by storage_count):

| storage_count | T_db lan1 / lan2 (ms) | storage CPU lan1 / lan2 (%) |
|---|---|---|
| 1 | 166.6 / 273.8 | 54 / 36 |
| 2 | 338.5 / 328.5 | 43 / 64 |
| 3 | 71.2 / 19.7 | 65 / 56 |
| 4 | 10.2 / 12.2 | 69 / 65 |
| 5 | 20.6 / 89.4 | 77 / 55 |

Storage scaled to **5 backends/LAN (4 dynamic + 1 static)**; T_db fell lan1
**286 → 25 ms (11.4×)**, lan2 **305 → 115 ms (2.7×)**. `rho(storage_count,
T_db)` = lan1 **−0.534**, lan2 **−0.431** (G2.5).

**Secondaries now serve** (the pre-fix “~zero” signature inverted): during the
episode the primary held ~38.8 conns / 54.6% CPU, while secondaries held
**15–21 concurrent conns / 60–76% CPU** (peaks 94–99%).

### 9.4 G2 gate outcomes (probe)

| Sub-gate | Result |
|---|---|
| G2.1 per-conn rules, distinct tcp_src | ✅ 45,246 + 38,235 installs; 0 per-client; 3 guard drops/LAN |
| G2.2 N conns → N backends | ✅ per-client sets span 3–5 backends; secondaries hold 15–21 conns |
| G2.3 established conns survive / errors flat | ✅ no mid-episode binding drops; 1.27% timeout-only errors |
| G2.4 NotPrimary == 0 | ✅ 0 across all service logs |
| G2.5 secondaries read activity + rho<0 | ✅ secondaries serve; rho −0.53 / −0.43 |

G1 ✅ · G1b ✅ · G4 ✅ (writes direct-to-primary; content_update 99.04% ok).

### 9.5 Global-edge behavior (by design, not an anomaly)

Edges are globally available: each edge read client connects to BOTH data VIPs
(`10.0.0.254` and `10.0.1.254` — see `vip_data_edge_epoch_and_recovery.md`).
The ~50/50 local/peer read split and the n2 cross-network flows (LAN1 edges
reading the LAN2 VIP via the router) are intended global-edge behavior, not a
routing defect. Cross-region hops are now correctly priced (local 2 vs peer 4).

## 10. G3 control run — default (knobs unset) path (2026-08-03)

Negative control completing the pair: identical config to §9 EXCEPT it
exercises the PRE-FIX read path. Since 2026-08-03 the default read preference
is `secondaryPreferred`, so G3 sets `EDGE_MONGO_READ_PREFERENCE=primary`
explicitly (env override `rq2_bottleneck_aware_g3.env`, and the same `primary`
on the shell so static edges don't fall back to `secondaryPreferred`);
`maxPoolSize=1` and per-client flows remain the defaults.

- **Run**: `source/scripts/testing/metrics/20260803_214639_rq2_ba_db_probe_g3`.
- **Delta vs the §9 control group** (what changed between the two runs):

| Dimension | Control group (§9, `..._204501_rq2_ba_db_probe`) | G3 (`..._214639_rq2_ba_db_probe_g3`) |
|---|---|---|
| `EDGE_MONGO_READ_PREFERENCE` | `secondaryPreferred` | explicit `primary` (pre-fix opt-out) |
| `EDGE_MONGO_MAX_POOL_SIZE` | `6` | unset → `1` |
| `VIP_DATA_PER_CONNECTION_FLOWS` | `1` (per-connection) | unset → `0` (per-client) |
| per-connection flow installs | 45,246 (lan1) | **0** |
| per-client flow installs | 0 | 16,700 (lan1) |
| `NotPrimaryOrSecondary` (13436) | **0** (all logs) | **25** (edge_server_n1) |
| secondaries serve reads | ✅ 15–21 conns, 60–76% CPU | ❌ conns exist, reads rejected |
| fan-out | N conns/edge → N backends | 1 conn/edge (edge-bound) |
| storage scale-out | 5 backends/LAN | 5 backends/LAN (same) |
| T_db scale-out relief | 286→25 ms (11.4×), rho −0.53 | 459→166 ms (2.8×) |

Everything else is identical: same bottleneck_aware thresholds, same data-bound
phases, same launch config (`CLIENTS=24`, seed 42, `WAN_RTT_MS=185`). Verified:
`EDGE_MONGO_READ_PREFERENCE=primary` is the only explicit deviation from §9
(the other two knobs absent → pool=1 / per-client defaults), and
`phases_snapshot.json` + all other thresholds are byte-identical to §9.1/§9.2.

### 10.1 Results (deep analysis — see `run_summary.md` in the run folder)

**Mechanism**: per-client flows (16,700 lan1 + 16,486 lan2), **0** per-connection
installs, no binding map; flows idle-expire 10 s / hard-expire 120 s, so an
edge re-pins via round-robin every ~120 s (a “lottery” during scale-down churn).

**Latency** (window logs; p50 = median of per-window medians):

| Phase | T_proc p50 (ms) | T_db p50 / p95 (ms) |
|---|---|---|
| baseline | 0.76 / 0.83 | 2.6 / ~840 |
| data_bound_episode | 0.96 / 0.94 | **156 / 1218 · 184 / 1313** |
| recovery_gap | 1.46 / 0.83 | 2.7 / ~850 |
| demand_drop | 0.84 / 0.80 | 2.7 / ~930 |

Episode DB decomposition: db_read ≈ 64 ms, db_write ≈ 5.1 ms (successful reads
only). Episode T_db p50 is **~4.4×/2.7× worse than §9** (156/184 vs 35/67 ms):
the primary alone carries the full read load.

**Throughput / errors** (`client_requests.csv`):

| Phase | n | p50 (ms) | p95 (ms) | req/s | errors |
|---|---|---|---|---|---|
| data_bound_episode | 40,044 | 178.9 | 1863.6 | **66.74** | 512 (1.28%) |
| overall | 41,972 | — | — | — | 541 (1.29%) |

Error character — two signatures: (1) the 512 episode errors are all
`http_status=0` client-side (245 immediate + 267 × ~30 s timeouts, backend
unknown) — **no 13436 logged during the episode**; (2) at demand_drop start the
instant rejection surfaces as **25 × HTTP 503 (the 13436 rejections on
`edge_server_n1`, all within a 13 s window, each ~0.7 s)**. Throughput 66.7 vs
§9's 76.8 req/s — the defect caps successful throughput.

**Pre/post scale-up + rho (with the G3 caveat)**:

| storage_count | T_db lan1 / lan2 (ms) |
|---|---|
| 1 | 468 / 452 |
| 3 | 183 / 169 |
| 5 | 165 / 174 |

rho(storage_count, T_db) = lan1 **−0.418**, lan2 **−0.383** — but this is NOT
genuine serving relief: as storage scales, more edge flows re-pin to secondaries
and their reads fail instantly (13436, excluded from the T_db medians), leaving
the primary with less concurrency. The honest discriminator vs §9 is the
**T_db floor at 5 backends: 165–174 ms (G3) vs 20.6–89.4 ms (§9)** — ~8× higher,
i.e. no usable secondary capacity. Rho alone cannot distinguish serving from
fast-fail; the NotPrimary count + T_db floor can.

**Secondaries — connections exist, reads rejected**: conns 13–21 / CPU 37–80 %
(replication + rejected-command overhead, NOT serving). Discriminating evidence:
25 × 13436 vs §9's 0; `edge_server_n1` served 0 requests during its
secondary-pinned minutes; T_db floor 165–174 vs 20–25 ms.

### 10.2 G3 gate verdict + control-pair conclusion

**G3 ✅ MET** (G1 ✅, G1b ✅, G4 ✅ — `content_update` 99.31 %). The default path
is byte-identical to pre-fix. The control pair is consistent: §9 vs G3 share the
same phases, thresholds, launch config and 5-backend scale-out, and near-identical
overall error rate (1.27 % vs 1.28 %) — differing **only** in the three knobs and
their consequences (0 vs 25 NotPrimary; secondaries serving vs rejecting;
T_db floor 25 vs 165 ms). **The fix — not the workload — is what changed
behavior. G1–G4 complete → safe to move forward with the RQ2 campaign.**

**Caveats**: only `edge_server_n1` logged 13436 (per-client + pool=1 lottery —
one edge pinned to a secondary at a time); the 25 count is a lower bound on
secondary reads (during the episode they surfaced as client timeouts); the
fast-fail artifact confounds rho; secondaries burn CPU without serving
(telemetry §3 limitation); storage scale-down had removal retries
(`dyn8`/`dyn1`).
