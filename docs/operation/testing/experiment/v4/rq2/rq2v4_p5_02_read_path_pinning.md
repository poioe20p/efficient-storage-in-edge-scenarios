# RQ2 v4 — P5.2 platform finding: storage reads move only through NEW connections (read-path pinning)

> **Status:** registered 2026-10-14 (Edge Experiment Runner; author-directed
> db-regime transition investigation). Analysis-time finding — **no run is
> invalidated**; no campaign config changes (comparability rule).
> **Evidence runs:** `stor_db_42p`, `none_db_42p` (preflight pair),
> `mx_both_m05`, `mx_stor_m05` (P3 pilots) — controller logs + client CSVs,
> all on `cloud-vm-rq2`.
> **Solves:** the P3 §7 open question ("why did reads move under
> `mx_both` but not under `mx_stor`") and the db preflight anomaly
> (`stor` ≈ `none`).

## 1. What was measured

Controller-log analysis of the per-connection `vip_data` install path
(`per-connection forward rule installed — client=IP:port … backend=IP`),
episode-scoped, lan1:

| Run | Distinct edge→mongo connections (whole run) | Born **inside** the episode | Born after | `select_storage` calls | New storage members' in-episode share |
| --- | --- | --- | --- | --- | --- |
| `stor_db_42p` | 41 | **6** (all in the first 4 s, *before* the first activation at +33 s) | 25 | 42 | **0 % of new connections**; 99 % of installs stayed on the pre-existing member |
| `mx_stor_m05` | 28 | **4** (at episode start) | 16 | few | new members ≈ 1–2 % (P3 §7) |
| `mx_both_m05` | 77 | **36** — from **4 edge containers' fresh pools** (static `10.0.0.2` + new dynamics `10.0.0.9/.10/.11` at +1/+2/+3 min) | 32 | many | new members served **all** of those births (30.8 % of sampled reads) |

In `stor_db_42p` the install volume (~35 k lines) vastly exceeds the
connection count (41): the traffic is **re-installs of pinned connections**
(flow expiry churn — same 60 s-band family as P6.1), not re-selection.
`select_storage` ran only 42 times in the entire run.

## 2. Mechanism

1. Each edge→Mongo connection is **pinned at birth** to one storage member
   (`_vip_data_conn_map`; the code comment: *"reuse the recorded backend.
   Never re-select — a different backend would change the DNAT
   mid-stream"*).
2. Fresh connections are born only at: **(a)** an edge container's pool
   warm-up (start of its first use), **(b)** a newly spawned edge
   container's pool (each dynamic unit opens its own), **(c)** post-press
   churn (pool idle-timeout / reconnect after the load drops).
3. During a sustained press with a fixed edge set, births fall to ≈ zero.
   Storage members admitted mid-press therefore receive **no reads** — the
   added capacity is invisible to the data plane no matter how the
   selection policy scores it.
4. Selection (incl. warm leases) only decides what **new** connections
   get. It cannot move established traffic.

## 3. Consequences for the campaign (pre-registered, honest)

- **`stor` cells in db (and mx) cannot relieve the user-visible or member
  press by construction** while the edge set is fixed. The db preflight
  pair (stor ≈ none, stor marginally worse) is this mechanism, not a
  budget accident. D14's CPU leg will read "not relieved" — that is the
  measured result to report, with this finding as the explanation.
- **`both` relief is partly mediated by the compute spawn**: new edge
  containers = new pools = new connections = the only channel through
  which mid-press storage capacity can receive reads. This is the actual
  tier-coupling asymmetry of the platform (storage relief is downstream of
  edge renewal) and belongs in the thesis narrative as such.
- **v3-era storage-relief claims need this qualification** (pool-12,
  different churn regime, no spawn coupling analysis) — carried to the P6
  comparison notes.
- **60 s-band interaction**: the band's re-install churn keeps the pins
  alive but never refreshes them — band windows do not create
  redistribution.

## 4. Handling (registered)

- **No mid-campaign change** (all campaign runs share the canonical
  config; cb/mx already executed).
- db cells run as planned; `stor`@db and `stor`@mx are written up as
  "measured; no relief; cause = read-path pinning (this finding)".
- **Post-campaign fix candidates** (none attempted now):
  (a) proactive re-pin — flow-mod push that re-binds a share of
  connections at storage admission (blocked by the mid-stream DNAT
  constraint; would need a safe drain/swap protocol);
  (b) pool-renewal trigger — signal edge containers to recycle Mongo
  connections on storage admission;
  (c) per-request selection (no pinning) — changes flow semantics,
  needs its own design+validation.
  Each is a platform-design change, out of campaign scope (R12 discipline).

## 5. Reproduction pointers (on `cloud-vm-rq2`)

- Birth census / install timeline: episode-scoped regex over
  `controller_lan{1,2}.log` (`forward rule installed … client=…:… backend=…`;
  `select_storage(…) selected=…`), scripts under `~/rq2v4_battery/`
  (probe run 2026-10-14, described in this doc's tables).
- Key folder: `source/scripts/testing/metrics/20261012_221616_rq2v4_stor_db_42p`
  (episode 22:17:19–22:25:21 UTC; activations 22:17:52/22:20:03/22:22:33;
  first post-press births 22:27:23 — all to new members).
