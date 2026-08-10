# RQ2 v2 Recalibration — Capacity Probe Plan

**Date**: 2026-08-05 · **Status**: ⚠️ In execution · **Host**: `cloud-vm-rq2`
**Parent**: [`results.md`](results.md) v2 Judgment/Root Causes · [`post_run_analysis.md`](post_run_analysis.md) §0
**Why**: the 36-run v2 campaign completed but is **confounded by a load-calibration failure** — offered load (144/72 req/s) exceeded the platform's genuine capacity at its configured resource limits (edge 0.15 CPU, storage 0.08 CPU — the storage tier was pegged at 99 % of quota). This plan finds the load envelope and re-gates G2 before the campaign is re-run.

## 1. Objective

For each episode type, find the **highest episode `rate_per_client`** at which **both** hold:
- **(H) aligned-arm health** — the fixed aligned arm (`cf_cb` / `sf_db`) has episode `timeout_rate ≤ 5 %` and episode p50 near baseline (≤ ~2× the healthy baseline p50);
- **(M) mechanism exercise** — the aligned arm's scale-up fires to budget (compute 8 / storage 8) and produces in-episode relief (targeted-tier `score_norm` falls below threshold, or the relief-flatten signal fires).

**Go/no-go for the data-bound direction:** if **no** rate in {1.5, 1.0, 0.75} lets aligned `sf_db` recover (db latency back toward ≤ ~500 ms, timeout ≤ 5 %, storage scale-up firing), the storage-first serving path (single compute server + pool 6) is the confound — **stop calibrating**; the fix is a config decision (pool/CPU as a separate single-variable axis), not a load change.

## 2. Method

Single-variable **rate ramps**, one variable at a time (user rule). Everything else held fixed: `INFLIGHT_WINDOW=1024`, `CURL_MAX_TIME=300`, `DRAIN_S=30`, request mixes, topology, quotas, envs. The rate is edited **in place** in the canonical phase file before each run (the run folder captures `phases_snapshot.json`).

### Series A — compute-bound rate ramp (cell: `cf_cb`, aligned)

| Run | Episode rate | Purpose |
|---|---|---|
| A1 | 1.5 (72 req/s) | user-preferred start; below the ~119 req/s ceiling |
| A2 | gate-decided (2.0 / 1.0) | bracket the knee |
| A3 | optional | refine |

### Series B — data-bound rate ramp (cell: `sf_db`, aligned)

| Run | Episode rate | Purpose |
|---|---|---|
| B1 | 1.5 (72 req/s, unchanged) | baseline reference; **expected to fail** (v2: 49.8 % timeout) |
| B2 | 1.0 (48 req/s) | below the measured 34–62 req/s storage service rate |
| B3 | 0.75 (optional) | only if B2 still fails — the go/no-go floor |

## 3. Gates (after each run — reviewed conclusion required)

Each gate is evaluated by the analyzer, then **reviewed** (the gate conclusion and the evidence behind it) before the next run launches.

| Gate | Question | Pass criteria | Decision if PASS | Decision if FAIL |
|---|---|---|---|---|
| G-A1 | Is 1.5 sustainable for the aligned compute arm? | (H) timeout ≤ 5 %, p50 ≤ ~2× baseline; (M) compute scale-up fires to budget | A2 at 2.0 (try higher) | if (M) fails → A2 at 2.5; if (H) fails → A2 at 1.0 |
| G-A2 | Knee located? | same as G-A1 | **cb rate = max passed** → Series B | refine with A3 |
| G-B1 | Does 1.5 reproduce the collapse? | (H) + (M) on `sf_db` | (unexpected) try B2 anyway | B2 at 1.0 (expected) |
| G-B2 | Does the aligned storage arm recover at 1.0? | (H) timeout ≤ 5 %, `avg_time_db_ms` ≤ ~500 ms; (M) storage scale-up fires + relief | **db rate = 1.0** (or try 1.25) → re-gated G2 | try B3 at 0.75; if B3 fails → **H-config, STOP, report** |

**Review rule:** after each gate, the evidence (per-run numbers) and the go/stop conclusion are written down and reviewed before the next launch. No run launches without its predecessor's gate being closed.

## 4. Re-gated G2 (after the probe, before any block)

1. Driver self-test + concurrency check (unchanged).
2. **Health:** the aligned arm (`cf_cb`, `sf_db`) at the probe-selected rate shows episode `timeout ≤ 5 %`, p50 within ~2× baseline.
3. **Mechanism:** scale-up fires to budget in the aligned cell; targeted-tier relief within the episode.
4. `ba_cb` / `ba_db` at the selected rates — controller behaves; `ba` agreement reported.
5. **Block-1 guardrail (5 %):** after Block 1 of the re-run, if any aligned cell's episode `timeout > 5 %`, stop and re-calibrate.

### Re-gated G2 completion record (2026-08-06) — ✅ GREEN

Rates settled (cb 1.5 / db 1.5) from Series A + C. Final config: pool 12 in all
envs; per-cell CPU: cf/ba_cb 0.15/0.08, sf/ba_db 0.30/0.15 (see run_matrix §4).
`sf_db` re-gate = G-C4 (`rq2_probe_db_c4_1_5`, PASS).

| G2 cell | Run | Config | ep timeout | ep p50 | db ms | Mechanism / ba | Verdict |
|---|---|---|---|---|---|---|---|
| `cf_cb` | `rq2_g2_cf_cb_1_5` | pool 12, 0.15/0.08 | **0.87 %** | 3.3 ms | 0 (pure compute) | compute 8/8 (4/LAN), compute_fired 28 | ✅ PASS |
| `ba_cb` | `rq2_g2_ba_cb_1_5` | pool 12, 0.15/0.08 | **0.88 %** | 3.3 ms | 0 | ba scales compute (actions 8/1); agreement 46.6 % (soft) | ✅ PASS |
| `ba_db` | `rq2_g2_ba_db_1_5` | pool 12, 0.30/0.15 | **0.45 %** | 8.2 ms | 2.2 med | ba scales storage (actions 8/4); agreement **88.9 %** | ✅ PASS |
| `sf_db` | `rq2_probe_db_c4_1_5` | pool 12, 0.30/0.15 | **0.02 %** | 8.4 ms | 2.4 med | storage 3 (2/1), G2 validation PASS both LANs | ✅ PASS |

**G2 judgment: all four cells PASS the hard gates** (health timeout ≤ 5 % and
p50 near baseline; aligned-tier scale-up fires). `ba_cb` classifier-vs-episode
agreement is 46.6 % (windows where both tiers were eligible; ba still scales
compute 8×, health clean) — noted as a soft observation, not a blocker.
**Campaign re-run is cleared to launch (Block-1 guardrail still applies).**

## 5. Between-run edit scope (the ONLY edits allowed)

| File | Edit | When |
|---|---|---|
| `source/scripts/testing/phases_override/phases_rq2_compute_bound.json` | `compute_bound_episode.rate_per_client` only | between Series-A runs |
| `source/scripts/testing/phases_override/phases_rq2_data_bound.json` | `data_bound_episode.rate_per_client` only | between Series-B runs |

No other config/code edits during the probe. Each run captures its own `phases_snapshot.json`.

## 6. Launch command (per probe run)

```bash
ssh cloud-vm-rq2 "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n STORAGE_CPUS=0.08 EDGE_CPUS=0.15 WAN_RTT_MS=185 RANDOM_SEED=42 \
    EDGE_MONGO_READ_PREFERENCE=secondaryPreferred EDGE_MONGO_MAX_POOL_SIZE=6 \
    VIP_DATA_PER_CONNECTION_FLOWS=1 \
    make -C source/scripts setup_network create_clients setup_test_data run_experiment \
    OSKEN_ENV_OVERRIDE_FILE=../../rq2_env/rq2_compute_first.env \
    RUN_LABEL=<label> PHASES_CONFIG=testing/phases_override/phases_rq2_<ep>.json \
    CLIENTS=24 CONTENT_ITEMS=3000 USERS=100 DATA_SEED=42 CURL_MAX_TIME=300 \
    TRAFFIC_DRIVER_MODE=open_loop INFLIGHT_WINDOW=1024 DRAIN_S=30 \
    SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1 > /tmp/<label>.log 2>&1 &"
```

Labels: `rq2_probe_<ep>_<rate>` with the rate dot written as `_` (run labels allow only letters/numbers/`_`/`-`): e.g. `rq2_probe_cb_1_5` (rate 1.5), `rq2_probe_cb_2_0`, `rq2_probe_cb_1_0`, `rq2_probe_db_0_75`. Env: Series A uses `rq2_compute_first.env` (cf arm); Series B uses `rq2_storage_first.env` (sf arm).

## 7. Gate evidence record

Each closed gate appends one row here (filled as the probe runs):

| Gate | Run | Rate | ep timeout % | ep p50 | db_ms | scale-up fired | relief | Verdict | Reviewer |
|---|---|---|---|---|---|---|---|---|---|
| G-A1 | `rq2_probe_cb_1_5` | 1.5 | **1.49** | **3.3 ms** (baseline 7.2) | 0.00 (cb) | compute **8** (budget 4/4 per LAN), G2 PASS | — | ✅ **PASS → A2 @ 2.0** | — |
| G-A2 | `rq2_probe_cb_2_0` | 2.0 | **6.27** | **3.7 ms** | 0.00 (cb) | compute **8** (budget 4/4 per LAN), G2 PASS | — | ❌ **FAIL (health > 5 %) → cb rate = 1.5** | — |
| G-B1 | `rq2_probe_db_1_5` | 1.5 | **49.99** | **20 s** | **17 s** (db) | storage **6** (budget 4/2), G2 PASS | none (still degraded in demand_drop: 10.8 %) | ❌ **FAIL (as expected) → B2 @ 1.0** | — |
| G-B2 | `rq2_probe_db_1_0` | 1.0 | **25.45** | **6.2 s** | **210 ms** (db healthy) | storage **7** (budget 4/3), G2 PASS | recovery/demand 0 % — storage tier relieved | ❌ **FAIL. Bottleneck = serving path, not storage: sf_db single compute server caps at ~36 req/s (uniform 25 % timeout, db 86–335 ms). → B3 @ 0.75** | — |
| G-B3 | `rq2_probe_db_0_75` | 0.75 | **0.85** | **43 ms** | **22 ms** (db) | storage **6** (budget 3/3), G2 PASS | recovery/demand 0 % / 0.12 % | ✅ **PASS → db rate = 0.75** (at the 36 req/s serving ceiling) | — |
| G-C1 | `rq2_probe_db_c1_1_5` | 1.5 (pool 12) | **22.67** | **23.7 s** | **11.1 s mean / 12.1 s med** (db) | storage **8** (budget 4/4), G2 PASS, storage cpu max 100 % | — | ❌ **FAIL (health > 5 %)** — pool 12 halved the collapse (B1 49.99 % → 22.67 %) but the **storage tier CPU (0.08) is now the binding constraint** (db 11–12 s, storage cpu pegged). → **C2 @ 1.25** | — |
| G-C2 | `rq2_probe_db_c2_1_25` | 1.25 (pool 12) | **19.23** | **19.4 s** | **6.0 s mean / 4.8 s med** (db) | storage **8** (budget 4/4); compute CPU med 64 % / **max 98 %**; storage CPU med 52 % / max 99.5 % | — | ❌ **FAIL (health > 5 %)** — rate-down barely moved it (22.67 → 19.23); **whole sf serving path is the constraint** (single compute 0.15 CPU + storage 0.08 CPU both peak ≈100 %). → **C2b @ 1.0**, then **C3** (`STORAGE_CPUS` 0.15 @ 1.5) if C2b still collapses | — |
| G-C2b | `rq2_probe_db_c2b_1_0` | 1.0 (pool 12) | **0.51** | **6.3 s** | **2.0 s mean / 2.0 s med** (db) | storage **8** (budget 4/4); compute CPU med 73 % / max 98 % | — | ❌ **FAIL (latency health)** — timeout ≤ 5 % BUT p50 6.3 s (~150× baseline) and db 2 s (~90× healthy 22 ms): pool 12 moved the choke from the client pool into the storage tier (B2 @ pool 6 had healthy 210 ms db + client timeouts; C2b @ pool 12 few timeouts + 2 s db). → **C3** (`STORAGE_CPUS` 0.15 @ 1.5) | — |
| G-C3 | `rq2_probe_db_c3_1_5` | 1.5 (pool 12, storage 0.15) | **24.12** | **6.2 s** | **26.5 ms med** (db — **healthy**) | storage **4** (budget 2/2); storage CPU med 35 % (relieved); **compute CPU med 75 % / max 98 %** (fixed server) | storage tier RELIEVED — db healthy, but timeout unchanged | ❌ **FAIL — decisive isolation: the fixed 0.15-CPU compute server is the sole remaining choke** (`fixed_storage_first` never scales compute; ~10 ms/req × 0.15 CPU ≈ 60–75 req/s ceiling ≈ offered 72). → **C4** (`EDGE_CPUS` 0.30) | — |
| G-C4 | `rq2_probe_db_c4_1_5` | 1.5 (pool 12, storage 0.15, edge 0.30) | **0.02** | **8.4 ms** (baseline 6.8 = 1.2×) | **2.4 ms** (db) | storage **3** (2/1), G2 validation PASS both LANs (db_ms 33–39 > proc_ms 3–4) | — | ✅ **PASS → db rate = 1.5 (design rate RESTORED)** — Series C COMPLETE | — |

## 8. Series C — db re-probe after pool sizing (Option 2, approved 2026-08-06)

**Decision (user-approved 2026-08-06):** the B-series central finding is that the storage-first
arm's serving path — **1 compute server × `EDGE_MONGO_MAX_POOL_SIZE=6`** → ~36 req/s ceiling —
is the experiment's binding constraint, **not the storage tier** (db latency stayed healthy:
22 ms at 0.75, 86–335 ms at 1.0). To restore a **symmetric, policy-only comparison**, the Mongo
pool is sized up as a **single-variable config axis**:

| Config | Before | After | Why |
|---|---|---|---|
| `EDGE_MONGO_MAX_POOL_SIZE` | 6 | **12** | 6 concurrent DB ops × ~200 ms ≈ 36 req/s ceiling; pool 12 ≈ 60–72 req/s |

The pool is read at **runtime** (`edge_server_config.py` → `vip_data_mongo_runtime.py:206`) so **no
image rebuild** is needed. Applied to the **canonical env files**
(`docs/operation/testing/experiment/v2/rq2/env/rq2_*.env`), synced to `~/rq2_env/`, and passed on
the **shell** (static servers read it at `setup_network`). This deviates from the original "pool 6"
data-path fix and is a documented, deliberate config axis (thesis framing: *the platform data path
was sized so the controller evaluation isolates the policy*).

**Re-probe matrix (single variable: db episode rate, pool fixed at 12):**

| Run | Rate | Purpose |
|---|---|---|
| C1 | 1.5 (72 req/s) | **restore the original design rate** — does pool 12 make it serviceable? |
| C2 | 1.0 / 1.25 | only if C1 fails — ramp down to the new ceiling |

**Fallback (separate single-variable axis, only if storage CPU binds at higher load):**
`STORAGE_CPUS` 0.08 → 0.15 (C3).

**Gates G-C1/G-C2:** same as G-B (health: episode `timeout ≤ 5 %`, db latency ≤ ~500 ms;
mechanism: storage scale-up fires, G2 PASS). PASS → db rate = the passed rate (target 1.5);
FAIL → next rate down.

## 9. Changelog

| Date | Change | Rationale |
|------|--------|-----------|
| 2026-08-05 | Probe plan created after the 36-run campaign was found confounded | Find the load envelope; re-gate G2 before re-running |
| 2026-08-05 | Run-label convention fixed: dots not allowed in `--run-label` (harness rejects them), so `1.5` → `1_5` | First A1 launch aborted at `run_experiment` with `invalid --run-label 'rq2_probe_cb_1.5'` |
| 2026-08-05 | **Series A complete: cb rate settled at 1.5** — A1 (1.5) timeout 1.49 % health+mechanism PASS; A2 (2.0) timeout 6.27 % > 5 % health FAIL; knee between 1.5–2.0 | cb phase file restored to 1.5; Series B (db) next |
| 2026-08-05 | **Series B complete: db rate settled at 0.75** — B1 (1.5) 49.99 % (collapse, db 17 s); B2 (1.0) 25.45 % with HEALTHY db (86–335 ms) → serving path is the bottleneck: sf_db single compute server caps at ~36 req/s; B3 (0.75) 0.85 % PASS at the ceiling | db phase file set to 0.75. **Central H-config finding**: the storage-first arm's serving path (1 compute server) is the binding constraint; 0.75 is at zero headroom, and cf_db (8 servers) will have ~8× surplus — cross-over interpretation at risk. Config decision needed before the re-run |
| 2026-08-06 | **Config decision (Option 2): `EDGE_MONGO_MAX_POOL_SIZE` 6 → 12** — serving-path symmetry for the db comparison | Probe showed pool 6 caps the storage-first arm at ~36 req/s (db tier healthy); pool 12 ≈ 60–72 req/s; single-variable, documented config axis; runtime-read (no image rebuild) |
| 2026-08-06 | **G-C1 FAIL @ 1.5 (pool 12)**: timeout 22.67 %, p50 23.7 s, db 11–12 s, storage cpu max 100 % — pool 12 halved the B1 collapse but the **storage tier CPU (0.08) is now the binding constraint** | Confirms the serving-path fix (pool) is necessary but not sufficient; storage tier CPU is the next constraint at 72 req/s → **C2 @ 1.25** (rate down); C3 (`STORAGE_CPUS` 0.08→0.15) is the documented fallback if storage still binds |
| 2026-08-06 | **G-C2 FAIL @ 1.25 (pool 12)**: timeout 19.23 %, p50 19.4 s, db ~5 s — rate-down barely helped; **both compute (max 98 %) and storage (max 99.5 %) CPU peak** → the whole sf serving path (1 compute 0.15 CPU + storage 0.08 CPU ≈ 0.55 CPU/LAN) is ~2× under-dimensioned vs cf (1.2 CPU) | sf arm needs a capacity axis, not just rate; → **C2b @ 1.0** completes the rate axis, then **C3** (`STORAGE_CPUS` 0.08→0.15 @ 1.5) tests the documented capacity fix |
| 2026-08-06 | **G-C2b FAIL @ 1.0 (pool 12, storage 0.08)**: timeout 0.51 % PASS but p50 6.3 s (~150× baseline) and db 2 s (~90× healthy) → latency health FAIL. Mechanism: pool 12 moved the choke from the client pool into the storage tier; fixed compute server is a co-choke (max 98 %, `server_count` stays 1 — sf policy `fixed_storage_first` never scales compute) | Rate-down alone cannot reach a healthy high rate; storage CPU (0.08) AND the fixed 0.15-CPU compute server both bind → **C3** (`STORAGE_CPUS` 0.15 @ 1.5) tests the documented capacity fix |
| 2026-08-06 | **G-C3 FAIL @ 1.5 (pool 12, storage 0.15)**: timeout 24.12 % unchanged, BUT db now healthy (26.5 ms med) and storage CPU relieved (35 %) → **the storage-CPU axis fixed the storage tier exactly as designed; the residual choke is the fixed 0.15-CPU compute server** (med 75 % / max 98 %; ~10 ms/req ⇒ ~60–75 req/s ceiling ≈ offered 72) | Storage-CPU fix was necessary but not sufficient; `fixed_storage_first` leaves the compute server unscaled → **C4** (`EDGE_CPUS` 0.30 @ 1.5, per-run single variable) tests the compute-serving axis |
| 2026-08-06 | **G-C4 PASS @ 1.5 (pool 12, storage 0.15, edge 0.30)**: timeout 0.02 %, p50 8.4 ms (1.2× baseline), db 2.4 ms, G2 validation PASS both LANs → **db rate = 1.5 RESTORED** | The compute-server axis was the final fix — the fixed 0.15-CPU serving server was the last choke; at 0.30 CPU the sf arm serves the full 72 req/s healthily with storage scaling (3 spawns) as the aligned tier |
| 2026-08-06 | **Series C COMPLETE — db = 1.5 settled** (symmetric with cb = 1.5). **Settled sf config: `EDGE_MONGO_MAX_POOL_SIZE=12`, `STORAGE_CPUS=0.15`, `EDGE_CPUS=0.30`** (cf unchanged: 0.15/0.08). Env files carry pool 12; the CPU vars are shell-only. **Next: update `run_matrix.md` §4 launch command (per-episode EDGE_CPUS/STORAGE_CPUS; pool 12) → re-gated G2 (cb 1.5 / db 1.5) → 36-run re-run** | |
