# RQ2 v2 — Current State Definition (baseline anchor before the 18-run campaign)

**Date**: 2026-08-04 · **Status**: baseline definition from the v1 campaign
dataset (`analysis/campaign_dataset.csv`, 18 runs) + measurement contract
(`analysis_focus.md` §7).
**Purpose**: define, unambiguously, the **current state** of the key metrics —
latency, scale-up, pre/post scale-up effect, throughput, load distribution —
so the v2 18-run campaign's results are judged against a fixed, quantified
anchor. All values below are **v1 (sync-driver) episode-phase medians over 3
replicates** unless noted; per-run values are in `campaign_dataset.csv`.

> ⚠ **v1 caveats that the v2 open-loop campaign removes** (do not forget when
> reading these numbers): (1) the **sync (stop-and-wait) driver** collapsed
> offered load in degraded cells (~80 % fewer requests issued in `cf_db`/
> `sf_db` vs the healthy cells), so cross-arm throughput is *not* comparable in
> v1; (2) **p99 is censored at 30 s** (`CURL_MAX_TIME=30`), so `p99=30000` is a
> cap, not a measurement; (3) **timeout is conflated with failure** (v1
> `failure%` includes timeouts). v2 fixes all three (open-loop driver,
> `CURL_MAX_TIME=300`, distinct `status` classes).

---

## 1. Metric definitions (the contract — what each metric means)

| Metric | Definition | Denominator / unit | Source artifact |
|---|---|---|---|
| **Latency p50/p95/p99** | episode-phase latency percentiles (completed requests only; v2) | ms, descriptive (never enters MWU) | `client_requests.csv` → `campaign_dataset` `ep_pXX_ms` |
| **Timeout rate** | `status=timeout` / offered (v2; primary degradation statistic) | % of offered | `client_requests.csv` `status` |
| **Failure rate** | completed & `http_status` not in (`200`,`""`) / completed | % of completed | `client_requests.csv` |
| **Offered / completed** | offered = every dispatched request; completed = `status=completed` | count | `client_requests.csv` |
| **Scale-up actions** | per-tier scale-up submissions (`dec_compute_actions` / `dec_storage_actions`) | count per run (max 8/tier = budget 4 × 2 LANs) | `decision_log_lan{1,2}.csv` |
| **Budget used** | `*_budget_used` vs `budget_cap=4` per tier per LAN | 0–4 per LAN | decision log |
| **Pre/post scale-up: relief** | whether the selected action's targeted tier recovered (`relief_recovered_num/den`) | fraction of actions | `rq2_relief_analysis` + `relief_flatten` |
| **Pre/post scale-up: time-to-recover** | selected-action ts → targeted tier `score_norm` back under threshold | s | relief tool |
| **Pre/post scale-up: time-to-usable-capacity (TTFT)** | action ts → first serving on the new node | s | `extract_spawn_metrics --anchor decision` |
| **Throughput (offered demand)** | requests issued to the service (v2: the open-loop schedule) | count/run | `client_requests.csv` |
| **Load distribution (per-LAN)** | failure % and latency split by LAN1/LAN2 | % | `ep_failure_lan1/2_pct` |
| **Efficiency** | compute+storage node-minutes per 1000 requests | node-min/1000 | `rq2_node_minutes` |

---

## 2. Current state per cell (v1, median of 3 replicates)

### 2.1 Latency (episode p50 / p95 / p99, ms)

| cell | p50 | p95 | p99 | note |
|---|---:|---:|---:|---|
| `cf_cb` (aligned) | **2.7** | **233.8** | 503 | healthy compute-bound |
| `cf_db` (mis-aligned) | **484.8** | **1990** | **30000 ⚠** | p99 pinned at cap (censored) |
| `sf_cb` (mis-aligned) | **163.2** | **376.4** | 873 | ~60× p50 worse than aligned |
| `sf_db` (aligned) | **500.6** | **1865** | **30000 ⚠** | p99 at cap in 2/3 replicates |
| `ba_cb` (H1) | **3.4** | **236.9** | 694 | ≈ aligned |
| `ba_db` (H1) | **126.6** | **1181** | **2201** | no cap; best data-bound cell |

### 2.2 Scale-up (actions per run; budget = 4/tier/LAN)

| cell | compute actions | storage actions | budget state |
|---|---|---|---|
| `cf_cb` | 8 | 0 | compute exhausted (4/4 per LAN), storage 0 |
| `cf_db` | 8 | 0 | compute exhausted **on a data-bound episode** (wrong tier) |
| `sf_cb` | 0 | 1 | barely acted (storage signal rarely fires in cb) |
| `sf_db` | 0 | 8 | storage exhausted (4/4 per LAN) |
| `ba_cb` | 8 | 0–2 | compute exhausted; residual storage fires (floor-35 tail) |
| `ba_db` | 8 | 8 | **both tiers exhausted** (4/4 each per LAN) |

### 2.3 Pre/post scale-up effect

| cell | TTFT compute (s) | TTFT storage (s) | relief (recovered/actions) | time-to-recover (s) |
|---|---|---|---|---|
| `cf_cb` | 29–40 | — | 0–4 / 8 | 60–90 |
| `cf_db` | 29–60 | — | 4–5 / 8 (**wrong tier** — no service relief) | 39–50 |
| `sf_cb` | — | ~39 | 0 / 1 (no relief) | — |
| `sf_db` | — | 29–39 | 4 / 8 | **~20** |
| `ba_cb` | 29–34 | 39–40 | 0–2 / 8–10 | 10–41 |
| `ba_db` | 39–50 | 29–40 | 7–8 / 16 | 30–51 |

### 2.4 Throughput (offered requests per run; v1 sync-driver — load collapsed in degraded cells)

| cell | offered (median) | failure % (incl. timeouts, v1) |
|---|---:|---:|
| `cf_cb` | 153 013 | 0.44 |
| `cf_db` | **31 309** | 2.10 |
| `sf_cb` | 100 498 | 0.26 |
| `sf_db` | **31 840** | 1.05 |
| `ba_cb` | 156 566 | 0.64 |
| `ba_db` | **59 827** | 0.55 |

### 2.5 Load distribution (per-LAN failure %, v1)

| cell | LAN1 | LAN2 | note |
|---|---:|---:|---|
| `cf_cb` | 0.34–0.45 | 0.06–0.70 | balanced |
| `cf_db` | 1.0–2.6 | 1.1–5.4 | degraded both LANs |
| `sf_cb` | 0.22–0.31 | 0.25–0.27 | balanced |
| `sf_db` | 0.77–1.25 | 0.99–1.14 | balanced |
| `ba_cb` | 0.08–1.10 | 0.10–1.16 | balanced |
| `ba_db` | 0.38–1.29 | 0.33–0.64 | balanced |

### 2.6 Decision quality (classifier-vs-episode agreement, `ba` cells)

| cell | agreement (per replicate) | vs chance (50 %) |
|---|---|---|
| `ba_cb` | 54 / 63 / 59 % | ≈ chance (reported honestly) |
| `ba_db` | 77 / 74 / 71 % | above chance |

---

## 3. What the current state says (narrative, v1)

1. **Latency.** The cross-over is present and large: in the compute-bound
   episode `cf`≈`ba` (p50 ~3 ms) vs `sf` (~163 ms, ~50× worse); in the
   data-bound episode `ba_db` is the only cell with p99 ≤ 2.5 s (no cap),
   while both fixed arms hit the 30 s cap at least once. The mis-aligned
   `cf_db` is pinned at the cap in **3/3** replicates.
2. **Scale-up.** The budget binds at 4/tier/LAN in every scaled cell. The
   mis-aligned arms act on the wrong tier (`cf_db` exhausts compute on a
   data-bound episode) or barely act (`sf_cb` 1 storage action), while `ba_db`
   is the only cell that exhausts **both** tiers.
3. **Pre/post scale-up.** TTFT is 29–60 s (compute) / 29–40 s (storage) —
   capacity is usable within ~1 minute of the action everywhere. Relief is
   meaningful only in the *aligned* and `ba` data-bound cells (sf_db 4/8 @
   ~20 s; ba_db 7–8/16 @ 30–51 s); `cf_db` recovers its *compute* score
   (wrong tier) yet the service stays degraded (p99 = cap) — the wrong-action
   cost made concrete. The cb relief metric is weak by design (score stays
   near threshold after scale-out) — the v2 relief-flatten signal addresses
   this.
4. **Throughput.** v1 offered load is **not comparable across arms** (sync
   driver collapse: cf_db/sf_db/ba_db issued ~60–80 % fewer requests). v2's
   open-loop driver restores a fixed offered schedule per arm — the v1
   numbers here are the *artifact*, and v2 is expected to show **higher** real
   load reaching the degraded arms (more timeouts/failures, larger effect).
5. **Load distribution.** Balanced across LANs in all cells (no systematic
   LAN1/LAN2 asymmetry); per-LAN failure tracks the cell's overall level.
6. **Decision quality.** The classifier is reliable in the data-bound
   direction (74 % mean) and ≈ chance in compute-bound (59 %) — consistent
   with the design note; v2 reports this honestly.

---

## 4. Caveats and the v2 delta (what changes)

| Dimension | v1 current state | v2 (18-run) expected change |
|---|---|---|
| Driver | sync stop-and-wait; offered load collapses under latency | **open-loop**: offered load = the fixed schedule per arm |
| Timeout | conflated with failure; p99 censored at 30 s | distinct `timeout` class; `CURL_MAX_TIME=300`; `timeout_rate` primary |
| Throughput | not comparable across arms | comparable; degraded arms receive the intended load |
| Statistics | n=3, no effect-size framing | **effect-size at n=3**: Cliff's delta ≥ 0.6 + 3/3 direction consistency; MWU descriptive (pre-registered, SC1–SC6) |
| Relief | cb-relief metric weak | relief-flatten signal added |
| Replicates | 3 | 3 (18 runs) |

---

## 5. Anchors for the v2 campaign (expectations derived from current state)

The v2 campaign is expected to **confirm and cleanly quantify**:

- **SC1 cross-over**: aligned beats mis-aligned on p95 + `timeout_rate`
  (v1 suggests ≥ large effect: cf_db p99 at cap vs ba_db ≤ 2.5 s).
- **SC2 value-of-info**: `ba` within 1.5× of aligned median and beats
  mis-aligned (v1: ba_db p99 2201 vs cf_db cap; ba_cb p50 3.4 ≈ cf_cb 2.7).
- **SC3 wrong-action cost**: mis-aligned shows no targeted-tier relief and
  wastes node-minutes on the wrong tier (v1: cf_db 4.2–4.7 compute
  node-min/1000 on a data-bound episode with no relief).
- **SC4 classification**: ba_db agreement > 50 % (v1 70–77 %); ba_cb reported
  (v1 ≈ chance).
- **New expectation under open-loop**: the mis-aligned arms will receive the
  *full* offered load, so v2 `timeout_rate`/failure in `cf_db`/`sf_db` is
  expected to be **higher than v1's collapsed-load failure** — the effect
  should be *larger*, not smaller. If instead it collapses, the Block-1
  sequential check (documented in `rq2_evaluation.md` §6) triggers.

---

## 6. Cross-references

- `analysis/campaign_dataset.csv` — per-run source of all v1 values above.
- `analysis_focus.md` §7 — v2 measurement contract (status-aware metrics).
- `results.md` (v1 appendix) — narrative + per-run tables.
- `rq2_evaluation.md` — pre-registration + success criteria SC1–SC6.
- `experiment_plan.md` / `run_matrix.md` §10 — the v2 18-run design.
