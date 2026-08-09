# RQ3 Saturation Re-Run — Experiment Plan

**Status:** � **CONFIG LOCKED — P4 (2026-08-09) after full tuning matrix; reproducibility re-run in progress.** The tuning matrix (`run_matrix.md`) established the relief-validated config: **`service_pressure 1.0` mix + `EDGE_CPUS 0.15` + rate 1.5 + 48 clients**. P4 shows **measured CPU relief on both arms** (direct −18.9 pp, discovery −32.5 pp old-backend CPU pre→post, both ≥ 10 pp — B1 CPU leg met) with PG-1/3/6 clean, D1/D2/D3 clean, at n=2. PG-2 (65–92 % band) is not met (~42 % sub-max median — the compute-pure ceiling); B1 is the base gate and passes. A **P4 reproducibility re-run (n=2 more)** is in progress to confirm the relief is stable before the campaign.
**History:** preflight n=1 (2026-08-08, 0.6/0.2/0.2 mix) hit the saturation band but relief was null (DB co-bottleneck, T_db 197 ms vs T_proc 74 ms); the mix was revised to `service_pressure 1.0` (2026-08-08) which cleaned the driver but under-saturated at 0.25 (24 %); the matrix then swept EDGE_CPUS (0.25→0.20→0.15) — relief appeared at 0.15 (P4).
**Scope:** Re-run the RQ3 readiness-propagation evaluation (direct vs discovery)
under a **saturation-capable configuration** where compute scale-up produces
visible relief and the admission-timing differential becomes consequential.
**Basis:** [`rq3_evaluation_conclusions.md`](../../../tese/research_questions/rq3/rq3_evaluation_conclusions.md)
(v2 campaign null consequence) + RQ1/RQ2 relief evidence (§1).
**Predecessor:** [`experiment_plan.md`](../v2/rq3/experiment_plan.md) and
[`rq3_v2_rework_plan.md`](../v2/rq3/rq3_v2_rework_plan.md) (the 6-client v2 campaign, complete).
**Host:** `cloud-vm-rq3` (idle after the v2 campaign).

---

## 1. Why this re-run exists (locked decision)

### 1.1 The v2 campaign's null — and its root cause

The completed v2 campaign (fixed image `638e3efdcdc5`, **6 clients**, rate 3.0,
`phases_rq3_compute_episode.json`) produced a **decisive timing result** and a
**null consequence**:

| Result | Value |
|---|---|
| Ready → admission (mechanism) | 0.001 s vs 6.98 s, d = −1.000 (all strata) |
| Spawn → first success (end-to-end) | 11.27 s vs 17.70 s, p = 0.0005 |
| Gap-window timeout / failure rate | **0.000 in every arm at every load** (up to ~88 % old-backend CPU, rate 25) |
| Old-backend CPU relief after scale-up | **None observable** (rate 3: ~10 % flat; rate 12: ~35–40 % flat) |

**Root cause (evidence-based, not hypothesis):** the 6-client open-loop driver
cannot deliver enough aggregate load to press the compute tier. Per-backend CPU
never exceeds ~35–40 % at the driver's usable envelope (the v2 boundary probe
stayed clean up to ~72 req/s and began collapsing at ~96 req/s), so there is
no pressure to relieve and no consequence to observe. The null is a **harness
load-delivery limitation**, not evidence against the mechanism.

### 1.2 The relief evidence from RQ1 / RQ2 (the fix)

RQ1 (cloud-vm, current campaign) and RQ2 (cloud-vm-rq2) run **48 clients
(24/LAN)** and **demonstrably saturate** the compute tier:

- RQ1 `20260806_195315_rq1_delivery_ls_4` (run folder lives on `cloud-vm`; run
  folders are never copied locally — the analysis-location rule): a 600 s
  `compute_plateau` at rate 1.2, `EDGE_CPUS=0.25` → compute CPU
  **~70–98 %** with one server → **~35–50 %** with two servers (relief
  **≈ 30–50 pp**); storage CPU ~50–90 % → ~30–35 % after storage scale-up.
  RQ1 root-cause analysis confirmed compute-tier saturation at this client
  count (`v2/rq1/results.md`, `rq1_v2_rework_plan.md` G2).
- RQ2 uses the same 48-client pattern (`data_bound_episode`, rate 1.5).

**Conclusion (locked):** scale-up produces visible relief **when the offered
load actually presses the tier**, and the lever is **client count +
workload**, not threshold calibration (the RQ3 trigger already fires
correctly).

### 1.3 What the re-run must demonstrate

1. **Relief:** old-backend compute CPU (primary; T_proc / per-request latency
   supporting) drops after the new backend is admitted — the "CPU or latency
   or RAM, something" that the thesis needs.
2. **Consequence:** under a saturated plateau, the gap window
   `[spawn_started, min(admitted, plateau_end)]` leaves the saturated old
   backends serving alone for **≈ 10 s (direct) vs ≈ 17 s (discovery)** —
   the ~7 s difference being the readiness quantization on top of a shared
   ~10 s spawn→ready bind/init segment. Discovery should show measurably
   more gap-window timeout/latency than direct.
3. **Timing re-confirmed:** ready → admission quantization (~7 s) and
   spawn → first success differential persist at the new config.

---

## 2. Research question mapping

Unchanged RQ (same as `tese/research_questions/rq3/rq3.md`):

> For newly created compute backends that satisfy the same application-readiness
> criterion, how does direct lifecycle notification versus periodic discovery
> affect the time until a ready backend contributes usable capacity?

The re-run adds the **consequence dimension** that the v2 campaign could not
measure: under saturation, does the admission-timing differential convert into
user-visible service-quality differences (and measurable resource relief)?

---

## 3. Configuration — the saturation regime

### 3.1 Launch parameters (per run, on `cloud-vm-rq3`)

```text
TRAFFIC_DRIVER_MODE=open_loop
CURL_MAX_TIME=300
INFLIGHT_WINDOW=1024        # per-client window; covers the cap 1.5 (450 <= 1024)
DRAIN_S=30
CLIENTS=24                  # per LAN -> 48 clients total (RQ1/RQ2 golden)
EDGE_CPUS=<probe-locked>    # 0.25 default, 0.20 fallback; locked by Phase 1
STORAGE_CPUS=0.08
WAN_RTT_MS=185
```

- **Workload:** `source/scripts/testing/phases_override/phases_rq3_saturation.json`
  (new; §3.2).
- **Arm env:** `source/scripts/testing/controller_env_overrides/rq3sat_direct.env`
  / `rq3sat_discovery.env` (new; §3.3), synced to `~/rq3sat_env/` on the VM.
- **Image:** fixed+instrumented edge image `638e3efdcdc5` (bind-before-ready;
  must be confirmed present with `docker images` before the probe).
- **Mongo data-path knobs (48-client requirement — RQ1 G2 calib3):**
  **Phase 0 finding (2026-08-06):** `EDGE_MONGO_MAX_POOL_SIZE` is
  **env-configurable, not platform code** — dynamic edge servers read it from
  the controller env (`compute_node_manager.py`), and static edges from the
  shell var at `setup_network` (`build_network_*.sh` use
  `${EDGE_MONGO_MAX_POOL_SIZE:-1}`). The v2 RQ3 runs had pool 1 because the
  arm envs never carried it. The saturation regime therefore:
  - sets `EDGE_MONGO_MAX_POOL_SIZE=6` in **both `rq3sat_*.env`** (controller
    → dynamic edges), and
  - passes `EDGE_MONGO_MAX_POOL_SIZE=6`,
    `EDGE_MONGO_READ_PREFERENCE=secondaryPreferred`,
    `VIP_DATA_PER_CONNECTION_FLOWS=1`, `ulimit -n 65535`, and the
    `CONTENT_ITEMS`/`USERS` seeding as **shell vars at `setup_network`/launch**
    (RQ1 `rq1_launch_run.sh` precedent; §6.2) — a launch-contract item,
    verified in Phase 0 before the probe. **No launcher code edit is
    required.**
- **Scoring thresholds:** G0-v6 values unchanged (identical across arms;
  only the arm-selected readiness mechanism varies). Scale-up must fire.

### 3.2 Workload phases — `phases_rq3_saturation.json`

Mirrors RQ1's **proven** `phases_rq1_stress_plateau.json` shape
(600 s plateau judged STABLE in RQ1), but **compute-only** (no
`content_update` / `content_aggregate` — RQ3 is compute-only; storage
readiness is out of scope):

| Phase | Duration | Rate/client | Client frac | Mix |
|---|---|---|---|---|
| `baseline` | 60 s | 1.0 | 0.1 | 60 % lookup / 25 % ranking / 15 % pressure |
| `compute_plateau` | **600 s** | **1.2** | 1.0 | **60 % service_pressure / 20 % lookup / 20 % feed_ranking** (80 % CPU-bound; `service_pressure` is DB-free) |
| `recovery_gap` | 120 s | 0.5 | 0.05 | baseline mix |
| `demand_drop` | 420 s | 1.0 | 0.1 | baseline mix |
| `idle_tail` | 420 s | 0.05 | 0.05 | baseline mix |

Total 1 620 s (~27 min) + setup/teardown ≈ **~30 min/run**.

> **Why this presses the compute tier:** 48 clients × rate 1.2 ≈ **58 req/s**
> aggregate (below the driver's clean envelope ~72 req/s and well below the
> ~96 req/s collapse onset), and the mix is 80 % CPU-bound. **`service_pressure`
> is the key endpoint: it reads in-memory request state and performs **0 DB
> ops** (pure CPU), so it presses the compute tier without loading the storage
> tier (`monitoring_workload_routes.py`). The **probe (§5) verifies the
> actual CPU band**; the rate is the primary escalation knob, **capped at
> 1.5 (72 req/s)** so the driver stays clean.
>
> **P-A calibration finding (2026-08-07):** the original candidate mix
> (55 % feed_ranking / 25 % pressure / 20 % lookup) collapsed in an
> **I/O-bound (storage) regime** — feed_ranking (3 ops) + lookup (2 ops) =
> ~2.05 DB ops/req → ~59 ops/s/LAN, above RQ1's proven ~45 ops/s/LAN cliff →
> compute CPU stayed at 33–41 % (PG-2 FAIL) while whole-run timeouts hit 46 %
> and canceled 8.5 % (PG-1 FAIL). The mix was corrected to
> `service_pressure 0.60 / lookup 0.20 / feed_ranking 0.20` (~1.0 DB ops/req,
> ~29 ops/s/LAN) and P-A′ re-run.
>
> **Canonical-file note:** this is a distinct, named workload regime; the
> repo's `phases_override/` convention (dozens of RQ-specific precedent files,
> e.g. `phases_rq1_stress_plateau.json`) is the established practice for
> RQ-specific workloads — the in-place-edit rule targets `phases.json`
> itself, which is untouched.

### 3.3 Arm env files — deltas from the v2 arms

Deltas from `rq3_direct.env` / `rq3_discovery.env`:
- `MAX_DYNAMIC_COMPUTE=12` (was 6) — capacity headroom for multiple scale-ups
  on a 48-client saturated pool (old G0-v6 golden cap).
- `EDGE_MONGO_MAX_POOL_SIZE=6` (new — v2 used pool 1) — the 48-client
  data-path requirement (Phase 0 launcher finding; §3.1).

All readiness, flow-isolation, topology, and warm-lease knobs are unchanged
(`READINESS_PROPAGATION` differs only by arm; `VIP_WARM_SERVER_SECONDS=0`;
`topology_host`; `VIP_FLOW_ISOLATION=1`; `EDGE_APP_READY_EVENT=1` in direct).

---

## 4. Phase 0 — Tooling prep (REQUIRED; the analysis depends on it)

The v2 analysis tools are phase-name-bound and path-bound. Three small,
**scoped** edits are required **before the probe** (analysis tooling only —
**no platform/source code changes**):

| # | Tool | Required edit |
|---|---|---|
| 0-1 | `docs/research_questions/v2/rq3/rq3_admission_analysis.py` (the real per-run analyzer; **`tools/rq3_admission_analysis.py` does not exist**) | (a) Make the phase-substring matcher `_SPIKE_SUBSTR` (currently `("spike", "compute_spike", "episode")`) configurable via argv/env (default keeps the current value so v2 artifacts stay reproducible; the saturation run passes `compute_plateau`); (b) also emit **gap-window latency p95/p99 and baseline latency p95/p99** (metric C3) alongside the existing gap `timeout_rate`/`failure_rate` |
| 0-2 | `tools/rq3_camp_prepost_resources.py` (relief tool) | Parameterize the phase filter — default `compute_spike` (v2 reproducible); the saturation run passes `compute_plateau`. Apply the same parameter to the `spike_rows`/`spike_start` computation (not just `in_spike()`). Add an `avg_time_proc_ms` (T_proc) extraction to the per-node pass (metric R2). Keep PRE_S=60 / POST_DELAY_S=10 / POST_S=60 |
| 0-3 | `tools/gen_rq3_counterbalance.py` | Parameterize via argv: seed base (3001), output path (`counterbalance_order.csv` **in this folder — must not overwrite** `v2/rq3/counterbalance_order_v2.csv`), label prefix (`rq3sat_`), block count (6 blocks × 2 = 12 runs, no disc15 block), and the **label scheme `{prefix}_{arm}_{seq}` with seq = per-arm sequence 1..6** (matches the v2 CSV convention; the tool's current block-number scheme must be parameterized, not assumed backward-compatible) |
| 0-4 | `tools/rq3sat_relief_latency.py` (new; campaign-scoped, kept in `tools/`) | Pool-wide per-request latency p50/p95 pre → post from `client_requests.csv`, `compute_plateau`-filtered, `[spawn−60, spawn]` vs `[admitted+10, admitted+70]`, **old-backends only** (excludes the newly admitted backend so pre/post compare the same serving set) — metric R3 |

Each edit is a few lines and must keep **backward-compatible defaults** so the completed v2 campaign outputs remain reproducible (phase filters default to `compute_spike`, label/seed defaults reproduce the v2 scheme). Verify edits 0-1/0-2 against the v2 campaign artifacts before the probe (done — Phase 0 verification reproduced the v2 outputs exactly). Edit 0-4 is a **campaign-scoped tool kept under `tools/`** (reusable, not temporary).

---

## 5. Phase 1 — Calibration probe (mandatory pre-campaign gate)

**Purpose:** confirm the saturation config works before committing to 12 runs:
(a) open-loop driver stays clean at 48 clients with the RQ3 mix; (b) edge CPU
reaches the target band; (c) scale-up fires; (d) relief is measurable; (e) the
consequence direction appears (discovery gap-window harm > direct).

### 5.1 Probe cells (in order)

| Cell | Arm | EDGE_CPUS | Rate/client | Aggregate | Why |
|---|---|---|---|---|---|
| P-A | direct | 0.25 | 1.2 | 58 req/s | Candidate — **rerun as P-A′ with the corrected mix after the P-A storage-collapse finding (§3.2)** |
| P-B | direct | 0.25 | 1.5 | 72 req/s | Escalate rate after P-A′: PG-2 PASS (pooled 69 %, window_log) but PG-4 relief marginal (−9.7 pp < 10) and consequence weak — more load to strengthen both (72 req/s = driver-clean cap) |
| P-C | direct | 0.20 | 1.2 | 58 req/s | Weaker backends if rate cannot saturate |
| P-D | direct | 0.20 | 1.5 | 72 req/s | Last escalation |
| P-E | discovery | *locked* | *locked* | *locked* | Confirm consequence direction at the locked config |

Stop as soon as P-A..P-D meets **PG-1..PG-4**; P-E then runs at the locked config to verify **PG-5** and the consequence direction (§5.5).
**Never exceed rate 1.5 / 72 req/s aggregate** (the v2 boundary probe showed
driver drain-cancel collapse onset at ~96 req/s, i.e. rate 16 × 6 clients).

### 5.2 Probe gates (all must pass to lock the config)

| Gate | Criterion |
|---|---|
| PG-1 Driver clean | canceled+dropped < 5 % of offered (48-client driver baseline ≈ 2.9 % — RQ1 ls runs at 48 clients; collapse regime ≈ 8.5 %+); flow-validation Check D PASS; **http=000 ≈ 0 in `baseline`** (timeouts in `compute_plateau` are the treatment regime, NOT a driver fault — RQ1's same envelope ran ~7–9 %) |
| PG-2 Saturation | **sub-max-server-state** old-backend compute CPU **pooled median in [65, 92] %, each LAN ≥ 55 %** (sub-max = `compute_plateau` rows where that LAN's `server_count` < its plateau max — the pre-scale-up-relief state, NOT diluted by post-scale-up dips). Re-anchored after P-A′: scale-up fires in window 1–2 (demand surge), so "pre-first-admission" was degenerate (1 window on lan1) |
| PG-3 Scale-up fires | ≥ 1 admitted compute backend per LAN |
| PG-4 Relief | old-backend compute CPU **pre → post drop ≥ 10 pp** (mean over `compute_plateau` windows in `[spawn−60, spawn]` vs `[admitted+10, admitted+70]`) — same windows and threshold as campaign gate G6 and the pre-registered R1 (≥ 10 pp). **Restricted to steady-state admissions (spawn ≥ 120 s after plateau start; `--steady-s 120`)**: early surge scale-ups are ramp-confounded (P-A′ showed a spurious +16 pp because pre-windows sit on the 6 %→88 % ramp) |
| PG-5 Quantization intact | checked on **P-E** (direct cells cannot evaluate it): direct `ready → admitted` ≲ 1 s; discovery ≥ 5 s at the locked config |
| PG-6 No driver collapse | whole-run canceled/dropped < 5 % and Check D PASS — **driver cleanliness only**. (Whole-run timeouts > 0 are EXPECTED under saturation — RQ1's same envelope showed ~7–9 % — and are the treatment regime, not a driver fault.) |

### 5.3 Escalation / de-escalation / stop rules

- **Under-saturation** (PG-2 fail, pooled sub-max CPU < 65 %): rate 1.2 → 1.5 (P-B); if still
  < 65 % at 1.5, drop `EDGE_CPUS` 0.25 → 0.20 (P-C), then rate 1.5 at 0.20
  (P-D). **Never drop `EDGE_CPUS` below 0.20** (RQ1 G2: 0.15 → 60–80 %
  timeouts).
- **Overshoot** (CPU > 92 % at the locked cell): on **P-B** (rate 1.5), drop
  the rate back to 1.2; on **P-A** (already 1.2), reduce the `feed_ranking`
  share in the plateau mix by 0.1 (rebalance to lookup) — an explicit
  mid-probe edit of `phases_rq3_saturation.json`, re-run as a new P-A cell.
  Do not run with median CPU > 92 % (over-saturation confounds the
  consequence).
- **Driver strain** (PG-1/PG-6 fail): **stop escalating load** — that is the
  config's limit. Report; do not force more.
- **`EDGE_CPUS` is NOT a driver knob:** lowering it cannot fix driver strain;
  it only weakens backends (used for under-saturation, never for driver
  strain).
- Lock the config on **PG-1..PG-4** (direct cells P-A..P-D); record the locked
  values in §10.

### 5.4 Probe deliverable

`probe_summary.md` in this folder + `rq3sat_probe_summary.csv` (per cell:
offered/canceled/dropped, pre-first-admission edge CPU median/max, admissions,
relief pp, ready→admit, gap timeout/failure, Check A–D). Gate metrics are
computed by `tools/rq3_camp_prepost_resources.py` (after edit 0-2) plus a small
`rq3sat_probe_gate.py` rollup (temporary script — deleted after the probe, per
the repo's temporary-scripts rule).

### 5.5 Probe decision rule (consequence direction)

P-E (discovery at the locked config) must show the **consequence direction**.
Probe finding (P-B / P-D / P-E / P-E2 / P-B2, 2026-08-07): the **gap-window**
outcome is null in every cell (old backends at 70–88 % CPU absorb the
~10–17 s gap: gap `timeout_rate` ≈ 0, gap p95 ≈ 3–23 ms). The **plateau-level**
timeout outcome is also **not usable as a direction**: it is dominated by
stochastic per-run degradation bursts (same config AND same seed 3002: P-B
11.4 % vs P-B2 27.7 %, the latter a snowballing 4-min burst 688→3096→2996;
storage CPU / count / conntrack all similar across runs), so the one-off
P-E2-vs-P-B difference (17.3 vs 11.4 %) was noise, not the arm treatment.
**Probe verdict: the consequence is not measurable at achievable saturation.**
The compute tier cannot over-saturate — the RQ2-calibrated autoscaler fires at
70–88 % CPU (score is T_proc-dominated; CPU normalization saturates at ~9.5 %),
and the rate/EDGE_CPUS envelope (≤ 1.5 / ≥ 0.20) cannot outrun it. Retuning the
autoscaler or capping capacity to force over-saturation would break RQ1/RQ2
comparability (scale-up must be the same mechanism) and is rejected. The
campaign therefore tests the **timing (T1/T2) + relief (R1/R2) claims with the
consequence reported as a pre-registered null** (v2-consistent; now with relief
measured and the saturation bound identified).

---

## 6. Phase 2 — Campaign

### 6.1 Design

- **Arms:** `direct` (rq3sat_direct.env) vs `discovery` (rq3sat_discovery.env),
  **n = 6/arm → 12 runs** (matches the v2 campaign's n convention and the
  exact-MWU p = 0.0022 headroom).
- **Counterbalance:** 6 blocks of 2 (`direct`/`discovery`), block seeds
  3001–3006, deterministic order via `tools/gen_rq3_counterbalance.py`
  (after edit 0-3), each arm leading ≥ 2 blocks, recorded in
  `counterbalance_order.csv` **in this folder** (never overwrite the v2
  matrix). Void re-runs take the void's matrix position.
- **Sensitivity cell (`discovery_15`):** **optional/deferred** — the
  quantization-scales-with-poll-period result is already established; only
  add it if the campaign completes early within budget.
- **Runtime:** ~30 min/run × 12 ≈ **6 h** + voids.

### 6.2 Launch contract (per run)

```text
TRAFFIC_DRIVER_MODE=open_loop CURL_MAX_TIME=300 INFLIGHT_WINDOW=1024 DRAIN_S=30
CLIENTS=24 EDGE_CPUS=<probe-locked> STORAGE_CPUS=0.08 WAN_RTT_MS=185
EDGE_MONGO_MAX_POOL_SIZE=6 EDGE_MONGO_READ_PREFERENCE=secondaryPreferred
VIP_DATA_PER_CONNECTION_FLOWS=1 ulimit -n 65535 CONTENT_ITEMS=3000
phases = phases_rq3_saturation.json
env    = rq3sat_<arm>.env   (carries EDGE_MONGO_MAX_POOL_SIZE=6 for the controller)
```

Run labels: `rq3sat_direct_{1..6}` / `rq3sat_disc_{1..6}`.

---

## 7. Pre-registered metrics & hypotheses

All metrics are computed **within `compute_plateau` only** (phase-filtered; the
workload has **no** `compute_spike` — the v2 "spike" terminology does not
apply here).

### 7.1 Relief (the new primary)

| ID | Metric | Expectation |
|---|---|---|
| **R1** (primary) | Old-backend compute CPU, mean over `[spawn−60, spawn]` vs `[admitted+10, admitted+70]` — **steady-state admissions only** (spawn ≥ 120 s into `compute_plateau`; `--steady-s 120`, see PG-4 ramp-confound note) | **Both arms drop ≥ 10 pp** (same threshold as PG-4/G6; RQ1 shows ~30–50 pp as the expected magnitude) |
| R2 (supporting) | Old-backend T_proc (`per_node_stats.avg_time_proc_ms`) pre → post (via relief tool after edit 0-2) | Drop |
| R3 (supporting) | Pool-wide per-request latency p50/p95 pre → post (`client_requests.csv`, completed only) | Drop or stable; not worse |
| R4 (context) | Old-backend RAM pre → post | ~flat (small drift OK) |

### 7.2 Consequence (the new headline)

The gap window is `[spawn_started, min(admitted, plateau_end)]`. In **both** arms
a pre-ready segment (spawn → bind/ready, ~10 s shared) is served by old
backends alone: direct's gap is **≈ 10 s**, discovery's is **≈ 17 s** (adds
the ~7 s quantization). Pre-registered contrasts: gap-window outcome **by arm**
and **vs the saturated baseline** `[spawn−60, spawn]` (both arms' baseline is
saturated by design — gap harm *beyond* that baseline is the treatment signal).

| ID | Metric | Expectation |
|---|---|---|
| **C1** (primary) | Gap-window pool-wide old-backend `timeout_rate` | **discovery ≥ direct**; excess over the saturated baseline is the treatment effect (direct ≈ 0 is NOT expected — direct also has a ~10 s saturated pre-ready gap) |
| C2 | Gap-window `failure_rate` | Same direction |
| C3 | Gap-window latency p95/p99 vs baseline p95/p99 | discovery's excess above baseline > direct's |
| C4 | Useful initial share (post-admission transition) | ≈ 1.0 both arms (fixed image; no http=000) |
| C5 | `GAP_DELTA_PP=5` context flag (gap vs baseline, per v2 contract) | reported, not a verdict |
| **C6** (reported, not a verdict) | Plateau-level pool-wide `timeout_rate` over `compute_plateau` | Noisy across runs (5–28 % at same config/seed — stochastic bursts); NOT a usable direction; reported for completeness |

### 7.3 Timing (re-confirm at the new config)

| ID | Metric | Expectation |
|---|---|---|
| T1 | `ready → admitted` (per backend) | direct ≈ 0.001 s vs discovery ≈ 7 s (d = −1.000) |
| T2 | `spawn → first success` | direct faster; **absolute differential ≥ v2** (capacity is valuable under saturation) |

### 7.4 Analysis

- Per-run analyzer: `docs/research_questions/v2/rq3/rq3_admission_analysis.py`
  (after edit 0-1) → T1/T2/C1–C5 (incl. gap-window latency p95/p99 for C3);
  `tools/rq3_camp_prepost_resources.py` (after edit 0-2) → R1/R2/R4;
  `rq3sat_relief_latency.py` (edit 0-4) → R3.
- Stats: exact MWU + Cliff's δ, per-arm medians, n=6/arm; relief paired sign
  test on per-admission (pre, post). Bind-stratified for T1/T2 (the shared
  ~10 s bind stall persists; handled as a measured covariate exactly as in
  the fixed-image campaign).
- Graphs: the v2 campaign family + new `relief_cpu_prepost.png`,
  `gap_timeout_vs_quantization.png`.

---

## 8. Gates & validity (per run + campaign)

| Gate | Criterion | Stage |
|---|---|---|
| G1 measurability | ≥ 20 gap requests / LAN | per run |
| G2 min-admissions | ≥ 1 admitted backend / LAN | per run |
| G3 event fraction (direct) | ≥ 0.80 event-driven | per run |
| G4 flow validation | Check A/B/D hard, C ≥ 0.85 | per run |
| G5 driver clean | canceled < 1 %; no Check-D void; 0×http=000 | per run |
| G6 relief | R1 ≥ 10 pp drop, majority of admissions (same threshold as PG-4 / pre-registered R1) | campaign |
| G7 quantization | T1 separation ≥ 5 s | campaign |
| G8 no plateau scale-down churn | no removals mid-plateau that confound relief | per run |

Void rule: any run failing G1–G5 is void; take its matrix position with a
replacement seed (≤ 1 void/arm). G6–G8 are campaign-level verdicts.

---

## 9. File map

**Created by this plan:**

| File | Purpose |
|---|---|
| `docs/operation/testing/experiment/rq3_saturation/experiment_plan.md` | This plan |
| `source/scripts/testing/phases_override/phases_rq3_saturation.json` | Saturation workload |
| `source/scripts/testing/controller_env_overrides/rq3sat_direct.env` | Direct arm env (canonical) |
| `source/scripts/testing/controller_env_overrides/rq3sat_discovery.env` | Discovery arm env (canonical) |
| `docs/operation/testing/experiment/rq3_saturation/env/rq3sat_{direct,discovery}.env` | Mirrored arm envs (v2 convention) |

**Edited by this plan (Phase 0 — analysis tooling only, no platform code):**

| File | Edit |
|---|---|
| `docs/research_questions/v2/rq3/rq3_admission_analysis.py` | parameterize `_SPIKE_SUBSTR` (default `compute_spike`); emit gap-window latency p95/p99 + baseline p95/p99 (edit 0-1) |
| `tools/rq3_camp_prepost_resources.py` | parameterize phase filter (default `compute_spike`); add T_proc (edit 0-2) |
| `tools/gen_rq3_counterbalance.py` | parameterize seeds/labels/output + per-arm label scheme (edit 0-3) |
| `tools/rq3sat_relief_latency.py` | **new** campaign-scoped tool for R3 (edit 0-4), kept in `tools/` |

**Created at execution time (not now):** probe/campaign run folders on
`cloud-vm-rq3`; `probe_summary.md`, `counterbalance_order.csv`, `run_matrix.md`,
`results.md`, `post_run_analysis.md`, `graphs/`, synced analysis CSVs.

**Documentation to update after results:**

- `tese/research_questions/rq3/rq3.md` — §4 evaluation-status note: add the
  saturation re-run stage.
- `tese/research_questions/rq3/rq3_evaluation_conclusions.md` — add the
  saturation-consequence section (replaces the "consequence is null" reading
  if C1 is non-null; otherwise documents the bounded null at 48 clients).
- `tese/Notes/thesis_overview.md` §6-RQ3 status line.

---

## 10. Dependencies, pre-flight & probe-locked values

- `cloud-vm-rq3` **idle** (no `active_run.json` run in progress; RQ1/RQ2 run on
  the other two VMs — no contention).
- Fixed image `638e3efdcdc5` present (`docker images`); bind-before-ready
  verified.
- Mongo data-path knobs: **Phase 0 finding** — pool 6 is env-level
  (`EDGE_MONGO_MAX_POOL_SIZE` in `rq3sat_*.env` for the controller/dynamic
  edges; shell var at `setup_network` for statics). The launch contract
  carries the shell vars (§6.2). **No launcher code edit required** (verified
  in Phase 0).
- Readiness gate + flow isolation already implemented — **no platform code
  changes**; the only code edits are the Phase 0 analysis tools (0-1..0-4).
- Phase 0 tooling edits 0-1..0-4 done and verified against the v2 artifacts.
- SSH with `ServerAliveInterval=60` (lessons-learned) for all launches.

**Probe-locked values (filled after Phase 1 + tuning matrix):**

| Locked parameter | Value |
|---|---|
| EDGE_CPUS | **0.15** (locked 2026-08-09 at P4 — the matrix swept 0.25→0.20→0.15; relief appears only at 0.15, the RQ2-cb-identical value. Was 0.25) |
| plateau rate_per_client | **1.5** (72 req/s) |
| plateau mix | **`service_pressure 1.0`** (compute-pure — the 0.6/0.2/0.2 mix is 40 % DB-bound (T_db 197 ms vs T_proc 74 ms) so compute adds cannot relieve; mirrors RQ2 cb with proven B1 relief p50 2421→3 ms) |
| INFLIGHT_WINDOW | 1024 (raise only if the probe requires) |
| READINESS_EVENT_FALLBACK_S | **20.0** (direct arm; 5.0 → raised after P-B's probe_fallback contamination) |
| **matrix cells / verdict** | **P1** (0.25, 0.6/0.2/0.2, n=2): PG-2 PASS 67.8/65.1 %, **relief null** (DB co-bottleneck). **P2** (0.25, 1.0, n=2): driver very clean, **PG-2 FAIL 24 %** (under-saturated). **P3** (0.20, 1.0, n=2): PG-2 FAIL 31 %. **P4 (0.15, 1.0, n=2): RELIEF MET — old-backend CPU pre→post −18.9 pp (direct) / −32.5 pp (discovery); PG-1/3/6 + D1/D2/D3 clean; PG-2 ~42 % (band not met — compute-pure ceiling). B1 base gate PASS.** P5 not run (rate 1.2 would lower load, cannot help). Full detail: `run_matrix.md`. |

---

## 11. Risks & mitigations

| Risk | Mitigation |
|---|---|
| 48 clients strain the driver | PG-1/PG-6 gates; rate capped at 1.5 (≤ 72 req/s); never escalate into the ~96 req/s collapse onset |
| Plateau unstable / overshoots 92 % | De-escalation rules (§5.3); `EDGE_CPUS` floor 0.20 (0.15 is the RQ1 timeout regime) |
| Bind stall (~10 s shared) | Measured covariate + bind stratification (v2 method); cancels between arms |
| Consequence still null at saturation | Pre-registered-acceptable; C1 decides the claim (timing + argued margin if null) |
| Analysis tools phase-bound (`compute_spike`) | Phase 0 edits 0-1/0-2 make the tools match `compute_plateau`; verified before the probe |
| Cross-RQ gate contamination | RQ3-specific gates key on `VIP_FLOW_ISOLATION=1` (lessons-learned fix); this regime sets it |
| Whole-run timeouts > 0 under saturation | Expected (RQ1 ~7–9 % at the same envelope); PG-6 judges driver cleanliness, not timeout rate |

---

## 12. Timeline

| When | Action |
|---|---|
| Now (documented) | Plan approved; config files in place |
| Phase 0 | Tooling edits 0-1..0-4 + Mongo-knob launch verification (pool 6: env + shell var at setup_network) |
| Phase 1 | Probe cells P-A..P-E (≈ 2–3 h), lock config (PG-1..PG-4), P-E decision rule (§5.5), fill §10 |
| After probe | Approve campaign |
| Phase 2 | 12-run campaign (≈ 6 h + voids) on `cloud-vm-rq3` |
| After | Analysis, results.md, post_run_analysis.md, graph family |
| After | Update thesis docs (§9) |
