# RQ2 v3 — sf_cb Rerun at the Binding Compute Config (Wrong-Action Cell Fix)

**Status:** PLANNED — PRE-REGISTRATION FOR THE RERUN (2026-08-12).
**Parent:** [experiment_plan.md](experiment_plan.md) (v3 campaign) ·
[results.md](results.md) · [post_run_analysis.md](post_run_analysis.md).
**Host:** `cloud-vm-rq2` · **Tag:** `rq2-v3-campaign-20260808`
(controller/edge source unchanged — only the `sf_cb` launch allocation changes).
**Notation:** `{REPO}` = `~/efficient-storage-in-edge-scenarios` on
`cloud-vm-rq2`; `{METRICS}` = `{REPO}/source/scripts/testing/metrics`.

## 1. Objective

Resolve the `sf_cb` confound. The original `sf_cb` cell ran the compute-bound
episode at **EDGE_CPUS=0.30 / STORAGE_CPUS=0.15**, while `cf_cb`/`ba_cb` ran
**0.15 / 0.08**. That allocation provisioned the compute tier **above its
binding point**, so `sf_cb` never exercised the wrong-action cost: service
quality held (~3 ms p50) and per-node CPU was *lower* than `cf_cb`. This rerun
re-runs `sf_cb` at the **binding config** to test the pre-registered
wrong-action expectation directly.

Single question: **does `fixed_storage_first` on the compute-bound episode, at
the same binding allocation as `cf_cb`/`ba_cb`, show the wrong-action cost
(sustained degradation + wasted storage actions)?**

## 2. Motivation & Hypothesis

- Mechanism relation (from the plan): *worse trigger awareness ⇒ worse user
  service quality*.
- On the compute-bound episode the compute tier is the binding resource:
  static-edge CPU clips at **75–85 % of the 0.15 cap in bursts** (cf_cb PRE
  p50 2.2–3.0 s → ~3 ms after compute adds).
- `sf_cb` at 0.30 never bound → the original cell is **not evidence for or
  against** the wrong-action cost (already flagged as a confound in
  `results.md`; its per-node CPU was ~2× lower, confirming provisioning, not a
  policy result).
- **Hypothesis:** at 0.15 static compute with no compute scale-up, `sf_cb`
  sustains the binding (peaks clip, requests queue) → **episode p50 stays in
  the seconds range** with elevated timeouts, and any storage reserve
  activations are **wasted** (no relief, storage node-minutes).

## 3. Config Change (the only source change)

`tools/run_rq2_campaign.py` (on `cloud-vm-rq2`) — `CELLS["sf_cb"]`:

- **From:** `"STORAGE_CPUS=0.15 EDGE_CPUS=0.30 EDGE_MONGO_MAX_POOL_SIZE=12"`
- **To:**   `"STORAGE_CPUS=0.08 EDGE_CPUS=0.15 EDGE_MONGO_MAX_POOL_SIZE=12"`
  (matches `cf_cb`/`ba_cb`).

Nothing else changes at the policy level: same `rq2_storage_first.env` family
(the launch source `{REPO}/rq2_env/rq2_storage_first.env`, reserve=1), same
`phases_rq2_compute_bound.json`, same pool 12, same controller/edge tag.
**Env-hash note (provenance):** the current launch env (md5 `c41bd38e…`)
differs from the campaign-launch hash (`3e18ffc…`) only by the documented
2026-08-08 hardening — `EDGE_MEMORY` 256m→512m (runs 1–14 vs 15+; see
`run_matrix.md` §1/§5 and `experiment_plan.md` §3). The policy-relevant
settings (reserve=1, policy, pool, thresholds) are unchanged; the memory
delta is already accounted in §4. Verified: all other five cells already ran
the intended config (policies, reserve, pool, budget, caps, phases — see run
snapshots).

**Provenance:** this edit is **already applied** on the VM (verified:
`CELLS["sf_cb"]` = `STORAGE_CPUS=0.08 EDGE_CPUS=0.15
EDGE_MONGO_MAX_POOL_SIZE=12`; no `0.30` remains; `py_compile` OK; backup
`tools/run_rq2_campaign.py.bak_20260812`). New orchestrator hash
`d45cdb2939d7a010c548fb410d9261b5` — record in `run_matrix.md` §5 alongside
the old `268b5799…`; record the order-CSV hash when it is created. **The
rerun launcher is an untagged VM edit** (the campaign tag
`rq2-v3-campaign-20260808` no longer matches the running code) — record a
rerun tag/commit (or rely on the recorded hash) so the rerun state is pinned
like the campaign was.

## 4. Run Matrix

| Label | Cell | Seed | EDGE_CPUS | STORAGE_CPUS | EDGE_MEMORY |
| --- | --- | --- | --- | --- | --- |
| rq2_sf_cb_1..5 | sf_cb | 42 | 0.15 | 0.08 | 512m |
| rq2_sf_cb_6 | sf_cb | 43 | 0.15 | 0.08 | 512m |

- n = 6 (seeds 42 ×5 + 43), same seed scheme as the original sf_cb block.
- `EDGE_MEMORY=512m`: inherited from the current env files (platform hardening
  from campaign runs 15+). Delta vs originals: old `sf_cb_1/2` ran at 256m
  (campaign runs 1–14). For a no-compute-spawn cell the memory cap is **not
  expected** to change behavior — stated as an expectation, not asserted as
  tested.
- **Provenance handling (required) — quarantine two sets, BEFORE the first
  launch (preflight #4/#5 are hard gates):**
  1. The **6 original `sf_cb` folders** (`{METRICS}/*_rq2_sf_cb_[1-6]`) →
     `{METRICS}/_superseded_sf_cb_030/` (superseded config).
  2. The **2 excluded incident folders** `{METRICS}/*_rq2_ba_db_2` and
     `{METRICS}/*_rq2_cf_db_5` → `{METRICS}/_superseded_incidents/`.
  Rationale: `discover_runs()` returns **every** top-level `RUN_RE` match with
  no exclusion mechanism, so a folder-mode rebuild without quarantining set 2
  would **silently re-include the two D2-excluded runs** (and every cell would
  then have 6 runs, so the `!=6` WARN would not fire). Both sets must be moved
  aside **before** the rebuild. Nothing is deleted (repo rule: run folders are
  never deleted).
- **Order CSV(s):** one-shot 1-row CSV per run, per the repo temp convention:
  `temp/sf_cb_run_1.csv … temp/sf_cb_run_6.csv` on the VM, header
  `run_label,cell,traffic_seed` (the launcher reads exactly these three columns
  via `csv.DictReader` — verified in `tools/run_rq2_campaign.py` `main()`:
  `plan = [(r["run_label"], r["cell"], r.get("traffic_seed","42")) for r in rows]`;
  `block`/`position` are not accessed, so the 1-row CSVs need only these three
  columns), one row each:
  `rq2_sf_cb_1,sf_cb,42` · `rq2_sf_cb_2,sf_cb,42` · `rq2_sf_cb_3,sf_cb,42` ·
  `rq2_sf_cb_4,sf_cb,42` · `rq2_sf_cb_5,sf_cb,42` · `rq2_sf_cb_6,sf_cb,43`.
  Record their md5s in `run_matrix.md` §5; delete after the rerun (temp
  cleanup). **One-row CSVs (not a single 6-row CSV) are required** so each run
  is launched individually and the per-run falsification checkpoint in §5/§7
  can stop the batch between runs. A dedicated CSV is required to **restrict
  each launch to one sf_cb row**: reusing the full 36-row counterbalance order
  after the quarantine would walk all 36 rows and — because only **28**
  non-sf_cb folders remain (the 2 incident runs are quarantined) — the
  orchestrator would **re-launch `ba_db_2` and `cf_db_5`**, re-creating the
  two D2-excluded labels and defeating the quarantine. The dedicated CSV is
  the only way to launch exactly the 6 sf_cb rows.

## 5. Run Configuration

- **Launch one run at a time (required by the §7 per-run falsification
  checkpoint):** for each sf_cb label, invoke the orchestrator with its 1-row
  order CSV:
  `cd ~/efficient-storage-in-edge-scenarios && python3 tools/run_rq2_campaign.py --host cloud-vm-rq2 --order temp/sf_cb_run_<N>.csv --log /tmp/rq2_sf_cb_rerun.log`
  (the orchestrator applies `CELLS["sf_cb"]` env/phases/cpus via the same
  `launch()` make chain as the campaign). After each run completes, apply the
  §7 per-run falsification checkpoint before launching the next run — a
  6-row batch cannot be paused, so the guardrail would be nominal.
- **Launch check (outcome-based, mandatory):** after each launch the sf_cb
  folder count must **increase by exactly 1** and the log must contain **no**
  "already completed — skipping" line for that label; after the **final**
  launch the total must be **exactly 6 new folders**. If an sf_cb label is
  skipped, distinguish the cause:
  - an **original sf_cb folder** still top-level (quarantine was missed) →
    move it to `{METRICS}/_superseded_sf_cb_030/` (the correct destination —
    NOT `_superseded_incidents/`) and relaunch;
  - a **D1/D3-tripped or non-D2-failed rerun folder** still exists → move it
    to `{METRICS}/_superseded_incidents/` (per §6.3) and relaunch the same
    label — a failed rerun folder that `is_run_completed()` treats as
    completed is never reused as evidence. **A D2 crash-exit is NOT relaunched**
    (permanent exclusion + halt; see §6.3).
  After the launches, the folder count must be **exactly 6−k new** (k = D2
  exclusions): fewer (a skip) or more (originals not quarantined) → **stop**,
  re-check the quarantine before analyzing.
- Verify each new run folder:
  - `controller_env_snapshot.env`: `STORAGE_PERSISTENT_RESERVE_ENABLED=1`,
    `SCALEUP_POLICY=fixed_storage_first`, `EDGE_MONGO_MAX_POOL_SIZE=12`
    (and `EDGE_CPUS` / `STORAGE_CPUS` only **if present** — they are make-vars
    and typically absent from the controller env snapshot; the CPU allocation
    is verified by the docker-inspect spot check below);
  **Env disambiguation (verified on the VM):** the launch env is
  `{REPO}/rq2_env/rq2_storage_first.env` (`STORAGE_PERSISTENT_RESERVE_ENABLED=1`,
  md5 `c41bd38e…`) — this is what
  `OSKEN_ENV_OVERRIDE_FILE=../../rq2_env/rq2_storage_first.env` (full file
  path, as `launch()` passes it) resolves to from `source/scripts`, and the
  run snapshots carry reserve=1. Two
  other same-named copies are STALE and must NOT be used:
  `~/rq2_env/rq2_storage_first.env` (STALE, `=0`, md5 `e8a5e9e2…` — the
  run_matrix §1 footnote labels it STALE) and
  `source/scripts/testing/controller_env_overrides/rq2_storage_first.env`
  (`=0`, v2-era). Verify the snapshot matches the `{REPO}/rq2_env/` copy
  (reserve=1).
  - `phases_snapshot.json` = `phases_rq2_compute_bound.json` (rate 1.5,
    `service_pressure` 1.0);
  - container CPU caps actually applied on at least one run:
    `docker inspect --format '{{.HostConfig.NanoCpus}}' <static-edge>` and
    `<storage>` → expected **150000000** (0.15) and **80000000** (0.08) if the
    platform uses `--cpus`/NanoCpus; if it uses `CpuShares`, expected
    ~154 / ~82. Check the build/launch scripts to confirm which field the
    platform sets, and record the observed value.

## 6. Measurements & Success Criteria (pre-registered for the rerun)

### 6.1 Wrong-action degradation signal (primary — verdict on the p50 leg)

- **Degradation CONFIRMED** iff **episode p50 ≥ 1.0 s, sustained** through the
  episode. **"Sustained" (operational):** the episode-phase p50 (over the full
  episode window) is ≥ 1.0 s AND the per-30 s-bucket p50 is ≥ 1.0 s in
  ≥ 50 % of episode windows (rules out a single-bucket spike). **Data
  sources:** episode p50 from `latency_summary.csv` (aggregate row, as the
  campaign analyzer reads it); the 30 s-bucket p50 series is computed directly
  from the run's `client_requests.csv` (always present; committed artifact) —
  bucket completed requests (`completed_at`, or `sent_at` + `latency_s`) by
  30 s, p50 per bucket per LAN (`client_lan`), averaged across LANs per bucket.
  The run's `analysis/rq2_v3_trajectory.csv` (if produced by the per-run
  analyzer) is used as a cross-check, not the primary source (its producer is
  VM-only and not named in the repo). Reference: cf_cb POST ~3.3 ms,
  old sf_cb@0.30 ~3.2–3.4 ms.
- **Corroborating signals (reported, not required):** episode timeout % ≥
  1.62 % (the old sf_cb@0.30 maximum; cf_cb@0.15 range 0.65–4.06 % — so
  timeout alone is a weak discriminator and is NOT co-equal); static-edge CPU
  > 70 % of the 0.15 cap in ≥ 30 % of episode windows (mirrors cf_cb PRE,
  ~3/10 windows >70 %).

### 6.1a Time-fraction metrics (2026-08-13 amendment — pre-registered)

**Discovery (recorded 2026-08-12/13):** the preflight analysis (P8 seed 2001,
pilot seed 42) showed the whole-episode aggregate p50 is **insensitive to
time-limited degradation**. The pilot spent 11/21 episode buckets (DF 52 %) in
seconds-range p50 with up to 27 % timeouts yet its aggregate p50 read 7.6 ms;
P8 degraded ~2 buckets (DF 9.5 %). A full-campaign scan (34 valid runs,
2026-08-13) confirmed the mask is general: binding cb arms hide degradation
(cf_cb DF 18–41 %, ba_cb 13–23 %) while the over-provisioned sf_cb@0.30
originals show **DF 0 %** — the confound is directly measurable. **This
amendment adds a time-fraction leg to the verdict.**

- **DF (degraded-time fraction):** fraction of 30 s episode buckets with
  bucket-p50 ≥ 1.0 s, computed with the §6.1 sustained-test series convention
  (per-LAN p50 per bucket, averaged across LANs per bucket) from the run's
  `client_requests.csv` (committed artifact). DF ≥ 50 % equals the §6.1
  "sustained" definition.
- **DT-p50 (degraded-time-weighted p50):** time-weighted mean of the
  per-bucket p50 series (each 30 s bucket = equal weight → the mean of the
  bucket p50s). **Secondary / report-only** — sensitive to single outlier
  buckets (e.g., sf_db_1 3.5 s from one window) and never the sole basis for
  a verdict.
- **Pre-registered time-fraction threshold: DF ≥ 15 %** (run-level, I1 ≥
  5 000) ⇒ **degradation confirmed** (time-fraction leg), regardless of the
  aggregate p50. **Threshold rationale (2026-08-13 scan):** binding cb arms
  ≥ 13 % (cf_cb 18–41 %, ba_cb 13–23 %); clean/incident-free arms ≤ 11 %
  (mostly ≤ 6 %); sf_cb@0.30 = 0 % — 15 % cleanly separates them.
- A run with DF ≥ 15 % is **confirmed, never falsification** (see §6.4).

### 6.2 Wrong-action footprint (secondary — both branches pre-registered)

- **0 compute adds** (no compute scale-up in any run).
- **Branch A — storage activates (1–2/LAN):** assess per-activation relief (no
  p50 drop, no storage-CPU reduction attributable to the activation); storage
  node-minutes positive and above cf_cb's (~0, since cf_cb never scales
  storage) = waste. Baseline: old sf_cb@0.30 had 1–2 wasted activations/LAN.
- **Branch B — storage does NOT activate (0):** the "does-nothing" branch —
  sf_cb sustains the degradation with no actions; the wrong-action cost is the
  sustained degradation (no relief path) and node-minutes ≈ 0. Verdict still
  read on §6.1.
- **P8 reference:** `rq2_sf_cb_preflight_1` (P8, `run_matrix.md` §2 — currently
  🔄 QUEUED) answers whether storage fires at all on `service_pressure 1.0`
  cb. Resolve/run P8 before or alongside the rerun so the activation behavior
  is known in advance; the rerun's Branch A/B is read consistently with it.
  **Launch (concrete):** run it via the **same direct make chain as the §7
  pilot**, substituting `RANDOM_SEED=2001` and
  `RUN_LABEL=rq2_sf_cb_preflight_1` (amended `CELLS["sf_cb"]` vars 0.08/0.15
  and the BASE_ENV vars inlined, as in the pilot command) — OR via a 1-row
  order CSV (`rq2_sf_cb_preflight_1,sf_cb,2001`) through the orchestrator,
  which inherits the amended `CELLS["sf_cb"]` (0.15/0.08) — exactly what the
  Branch A/B reading needs. Its folder (`*_rq2_sf_cb_preflight_1`) does NOT
  match `RUN_RE` (`[1-6]$`), so it stays out of the dataset; quarantine it in
  `{METRICS}/_superseded_pilot/` after use.

### 6.3 Base gates + no-benefit-arm tension rule (aligned with parent §6)

- **Data-path integrity (hard halts, per parent §6):** D1 = 0 `NotPrimary`,
  D2 = 0 container crash-exits, D3 = snapshots present.
- **Health gates (this plan pre-registers the no-benefit-arm reading):**
  timeout ≤ 5 % and served ≥ 95 % — parent §6 explicitly exempts `sf_cb` from
  the health-timeout ceiling, and scopes the no-collapse (served < 95 %) halt
  to *healthy* cells without defining that term; this plan **pre-registers**
  that `sf_cb` (pre-registered to degrade) is not a healthy cell, so for this
  arm timeout > 5 % and served < 95 % are the **expected degradation** and do
  NOT halt (recorded here to settle the ambiguous clause before the runs).
- **Tension rule (pre-registered):** the verdict is the §6.1 degradation
  direction. **D1/D2/D3 remain hard halts, aligned with parent §6** (a hard
  data-path trip halts even for no-benefit cells):
  - **D2 crash-exit = permanent exclusion + halt** (no same-label relaunch,
    mirroring the campaign's `ba_db_2`/`cf_db_5` handling): the run folder is
    moved to `{METRICS}/_superseded_incidents/`, the label is NOT relaunched,
    and the sf_cb valid pool decreases (see the adjusted targets below).
  - **D1/D3 trip on any rerun run = halt, re-examine, THEN relaunch the same
    label** — before the relaunch the failed run folder is moved to
    `{METRICS}/_superseded_incidents/` (repo rule: never deleted); otherwise
    `is_run_completed()` treats it as done and the orchestrator skips the
    label (see §5).
  A degraded run tripping the health gates is reported as **"wrong-action cost
  evidenced + gate caveat"** — NOT excluded, does NOT halt.
- **Adjusted targets if a D2 exclusion occurs (pre-registered):** with k D2
  exclusions, the §5/§7 targets become "exactly 6−k new folders" and
  "exactly 34−k rows", and the cell verdict is computed on the remaining
  valid pool with the reduced-n limitation reported (per the aggregation
  rule — the ≥4/5 threshold requires 5 seed-42 runs; with fewer, report what
  n remains and do not claim).
- **Flags (reported, NOT exempt, NOT halting):** I1 < 5 000 completed/LAN and
  F2 > 3× are not part of the parent per-run stop-rule for any cell. On a
  degraded run: F2 > 3× → report the symmetry caveat. **I1 precedence
  (pre-registered):** a run with I1 < 5 000 has an unreliable p50 — its
  verdict is **Ambiguous / not evaluable**, and it can **never** trigger the
  §6.4 falsification guardrail (the p50 is not a meaningful counter-signal if
  the demand never materialized). Within I1-met runs, §6.4 decides.
- **Cell-level aggregation (pre-registered):** degradation is CONFIRMED at the
  cell level iff **≥ 4/5 seed-42 runs** confirm (per the §6.4 table) AND no
  run triggers the falsification guardrail. The seed-43 `_6` replicate is
  reported separately (campaign seed convention: seed-42 n=5 pool + seed-43
  separate) — it does **NOT** count toward the 4/5 threshold. **The
  falsification guardrail applies to EVERY run, including the seed-43 `_6`** —
  a falsifying `_6` also triggers stop + re-examine V1 (it is only excluded
  from the 4/5 count, not from the guardrail). **A falsifying run is NOT a
  "mixed outcome".** Mixed non-falsifying outcomes (some confirm, some
  ambiguous) → cell verdict **"not reproduced / mixed"** → no claim; report
  per-run.

### 6.4 Falsification guardrail + gray-band handling

Decision table (pre-registered; closes the gray bands). **Applies to runs
with I1 ≥ 5 000**; a low-demand run (I1 < 5 000) is **Ambiguous** (not
evaluable) regardless of p50/timeout (see §6.3):

| Episode p50 | DF (§6.1a) | Timeout % | Verdict |
| --- | --- | --- | --- |
| ≥ 1.0 s, sustained (§6.1) | any | any | **Degradation confirmed** (aggregate-sustained leg; wrong-action cost evidenced) |
| any | ≥ 15 % | any | **Degradation confirmed** (time-fraction leg — aggregate p50 is insensitive) |
| < 0.5 s | < 15 % | < 0.65 % | **Falsification guardrail** — premise in question → **stop**, re-examine V1 |
| < 0.5 s | < 15 % | ≥ 0.65 % | **Ambiguous / not reproduced** — report "no wrong-action signal; no claim"; do NOT treat as falsification |
| [0.5, 1.0) s | < 15 % | any | **Ambiguous / not reproduced** — report; no claim |
| any | [5, 15) % | any | **Ambiguous / intermittent** — report DF; no claim |

Precedence: the two **Degradation confirmed** rows are evaluated top-down and
take precedence over falsification (a run with DF ≥ 15 % is confirmed, never
falsification, even at p50 < 0.5 s). All rows require I1 ≥ 5 000.

Verdict vocabulary (standardized): **Degradation confirmed** (wrong-action
cost evidenced) · **Ambiguous** (no claim; covers gray bands, not-sustained,
and I1 < 5 000 not-evaluable) · **Falsification** (stop). Cell-level mixes of
confirm/ambiguous → **not reproduced / mixed** (no claim).

- **Falsification boundary (deliberately strict):** p50 < 0.5 s AND timeout <
  0.65 % (below cf_cb's minimum) AND **DF < 15 %** (§6.1a — a DF ≥ 15 % run
  is confirmed, never falsification). **I1 precedence:** the falsification row
  applies ONLY to runs with I1 ≥ 5 000 (demand materialized); a low-demand run
  (I1 < 5 000) is **Ambiguous / not evaluable** regardless of p50/timeout (see
  §6.3). A non-degraded outcome with timeout inside cf_cb's normal 0.65–4.06 %
  range lands in "Ambiguous / not reproduced" — which still prevents the
  wrong-action claim; only the strongest counter-evidence triggers the stop.
  (Acknowledged: low-probability given 12/12 cf_cb/ba_cb binding evidence at
  the same 0.15 allocation; kept as a guardrail, not the primary test.)

## 7. Analysis Approach

- **Pilot first:** launch `rq2_sf_cb_pilot` (seed 42) via the **direct make
  chain** (the same chain and base vars the orchestrator's `launch()` builds —
  bypasses the orchestrator's order-CSV/label handling for the single probe):
  `cd ~/efficient-storage-in-edge-scenarios && nohup sudo -n RANDOM_SEED=42
  STORAGE_CPUS=0.08 EDGE_CPUS=0.15 EDGE_MONGO_MAX_POOL_SIZE=12
  WAN_RTT_MS=185 EDGE_MEMORY=512m EDGE_MONGO_READ_PREFERENCE=secondaryPreferred
  VIP_DATA_PER_CONNECTION_FLOWS=1 OVERLOAD_CPU_PCT=30 OVERLOAD_PEAK_LATENCY_MS=2000
  make -C source/scripts setup_network create_clients setup_test_data run_experiment
  OSKEN_ENV_OVERRIDE_FILE=../../rq2_env/rq2_storage_first.env
  RUN_LABEL=rq2_sf_cb_pilot PHASES_CONFIG=testing/phases_override/phases_rq2_compute_bound.json
  CLIENTS=24 CONTENT_ITEMS=3000 USERS=100 DATA_SEED=42 CURL_MAX_TIME=300
  TRAFFIC_DRIVER_MODE=open_loop INFLIGHT_WINDOW=1024 DRAIN_S=30
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1 > /tmp/rq2_sf_cb_pilot.log 2>&1 &`
  (all make-vars inlined — no placeholders; matches `BASE_ENV` +
  `CELLS["sf_cb"]` + the `launch()` make chain in `tools/run_rq2_campaign.py`.
  `SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1` are the orchestrator's standard
  launch flags — the campaign used the identical set and produced full client
  traffic, so the pilot does too).
  The `SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1` flags are carried verbatim
  from `launch()` (identical to the campaign runs) — they do not suppress
  client traffic; the open-loop driver (`CLIENTS=24 … INFLIGHT_WINDOW=1024`)
  still generates the requests that yield the gate's p50 / timeout % / I1.
  `_pilot` does **not** match `RUN_RE` (requires `[1-6]`), so it never enters
  the campaign dataset. Analyze it with the standard per-run analyzer (rollups
  into the v3 `vm_per_run`); after analysis, move the pilot folder to
  `{METRICS}/_superseded_pilot/` (NOT the 0.30-quarantine folder — the pilot
  runs at the new 0.15/0.08 config) to keep top-level `metrics/` clean.
  **Pilot gate (pre-registered):** a "confirmed pilot" = the pilot shows the
  §6.4 **degradation confirmed** row; a **falsifying pilot** → stop +
  re-examine V1 (per §6.4); an **ambiguous pilot** → proceed to n=6 but
  record that no early signal was obtained. Confirm the §6.1/§6.4 direction
  before committing the n=6 batch.
  **Preflight outcome (recorded 2026-08-12/13, at the amended 0.15/0.08
  config):** P8 (seed 2001) — Branch A (storage fires; 2 on lan2), DF 9.5 %,
  aggregate p50 3.4 ms, timeout 0.50 %, I1 42 928; falsification-shaped but a
  **probe** (not a dataset run; role = Branch A/B + preflight only). Pilot
  (seed 42) — DF 52 % (11/21 buckets ≥ 1 s), aggregate p50 7.6 ms, timeout
  10.77 %, served 89.2 %, I1 38 493 → under the amended §6.4 the pilot reads
  **Degradation confirmed (time-fraction leg)** → the "confirmed pilot"
  branch is satisfied and the n=6 batch may proceed. **Seed-variance note:**
  seed 2001 degraded ~1 min, seed 42 ~5.5 min; the 4/5 seed-42 cell rule
  absorbs this, and a falsifying `_6` still halts.
- **Per-run falsification checkpoint (mandatory, not deferrable):** after
  **each** of the 6 runs completes — and BEFORE launching the next — generate
  that run's rollups and compute its §6.4 verdict from its own data: episode
  p50 from `latency_summary.csv` (aggregate), the 30 s-bucket p50 series
  computed from `client_requests.csv` (per §6.1; trajectory CSV as
  cross-check) for the "sustained" test **and for DF / DT-p50 (§6.1a)**, and
  timeout % and I1 from the run's client data / `run_summary.md`. If the run
  shows the falsification row (aggregate p50 < 0.5 s AND timeout < 0.65 %
  AND **DF < 15 %**, with I1 ≥ 5 000), **stop and re-examine V1 before
  launching the next run**. A run with DF ≥ 15 % is confirmed (proceed). The
  checkpoint is NOT deferred to the end of the batch.
- **Per-run analysis deliverables (explicit — one record per run, so the
  analysis is fully specified):** (1) aggregate episode p50/p90/p95 from
  `latency_summary.csv`; (2) DF and DT-p50 from the 30 s-bucket series
  (§6.1a); (3) episode timeout %, served %, I1; (4) storage activations per
  LAN + per-activation relief (p50 change after activation, storage CPU) —
  Branch A/B per §6.2, read consistently with P8; (5) compute adds (expect
  0); (6) D1/D2/D3 gates; (7) verdict per amended §6.4 (top-down) + base-gate
  note. Record all seven in the run's `run_summary.md`/rollups.
- Generate per-run rollups for the 6 new runs with the per-run analyzers: the
  four `rq2_{bottleneck_validation,decision_analysis,relief_analysis,node_minutes}.py`
  are **VM-only** (at `docs/research_questions/v2/rq2/` on `cloud-vm-rq2` —
  not committed under `source/`), and `extract_spawn_metrics.py` **is**
  committed (`source/scripts/testing/analysis/rq2/extract_spawn_metrics.py`).
  Write the `<run>_*.txt` rollups into the v3 `vm_per_run` (the folder the §7
  rebuild reads). The `docs/operation/testing/experiment/v3/rq2/analysis/`
  folder (with `vm_per_run/`) exists on `cloud-vm-rq2` — it is not committed
  locally (removed per repo housekeeping 2026-08-12); the rebuild runs on the
  VM against it. If the VM paths differ, fix before the rebuild — the
  post-rebuild empty-values check catches missing rollups.
- **Dataset supersession (mandatory):** rebuild in **folder mode** with explicit
  **v3 paths** (the analyzer's `--vm-per-run`/`--out` defaults point at the v2
  folder; `--metrics-dir` already defaults to `source/scripts/testing/metrics`);
  run from the repo root:
  ```
  cd ~/efficient-storage-in-edge-scenarios && python3 -m source.scripts.testing.analysis.rq2.rq2_bottleneck_aware_campaign \
    --metrics-dir source/scripts/testing/metrics \
    --vm-per-run docs/operation/testing/experiment/v3/rq2/analysis/vm_per_run \
    --out docs/operation/testing/experiment/v3/rq2/analysis \
    --graphs-dir docs/operation/testing/experiment/v3/rq2/graphs/comparison
  ```
  This rebuilds `campaign_dataset.csv` + comparison graphs from the current
  **top-level** folders: (36 − 6 quarantined sf_cb − 2 quarantined incidents) +
  6 new sf_cb = **34 runs** (the valid pool is 34; the 6 new sf_cb *replace*
  the 6 originals, they do not add to them).
  **Expected analyzer WARN (pre-registered):** after the correct quarantine,
  `cf_db` and `ba_db` have 5 runs each (the 2 incident runs excluded), so the
  analyzer prints `[WARN] replicate counts != 6` for those two cells — this is
  expected and correct, NOT a rebuild failure; the comparison graphs show
  5-replicate cells for them. Only a WARN/error involving sf_cb or an
  unexpected count is a problem.
- **Post-rebuild dataset verification (mandatory):** the rebuilt
  `campaign_dataset.csv` must contain **exactly 34 rows** and its run_id set
  must be exactly the expected 34 run_ids. Since the new runs **reuse the
  sf_cb labels** (only the `<ts>` prefix differs), the check MUST use the
  recorded **timestamped run_ids**, not label suffixes:
  - **forbidden:** the 6 recorded **original sf_cb run_ids** (full
    `<ts>_rq2_sf_cb_N`, recorded in preflight #3) and any run_id whose label
    is `rq2_ba_db_2` or `rq2_cf_db_5`;
  - **required:** the 6 **new sf_cb run_ids** (their actual
    `<ts>_rq2_sf_cb_N` names) present with non-empty per-run values (a folder
    without its `vm_per_run` rollups still yields a row with empty values).
  If the count is ≠ 34, a forbidden run_id appears, or a new run has empty
  values → stop and fix before any synthesis.
- **DF/DT-p50 columns (2026-08-13 amendment):** the rebuilt
  `campaign_dataset.csv` gains `df` and `dt_p50` columns (per-run values
  from the §6.1a 30 s-bucket method). The full-campaign scan recorded
  2026-08-13 (34-run pool: cf_cb 18–41 %, ba_cb 13–23 %, sf_db 0–6 %,
  ba_db 0–11 %, cf_db 0 %, sf_cb@0.30 0 %) is the reference baseline and
  **must be recomputed after the 6 new sf_cb runs replace the originals** —
  the amended sf_cb row should read DF ≥ 15 % if the wrong-action cost
  reproduces.
- **Cell-stats / B2-synthesis CSVs (limitation):** `rq2_v3_cell_stats.csv` /
  `rq2_v3_b2_synthesis.csv` have **no committed generator** (not in the repo
  or on the VM — produced by an ad-hoc script on 08-09). Regenerate via the
  same ad-hoc synthesis (recreate it from the values documented in
  `results.md`/`post_run_analysis.md`), or flag as a limitation; the primary
  synthesis is reproducible from the rebuilt `campaign_dataset.csv`.
- **Old sf_cb@0.30 baseline:** taken **only** from §8 (values cross-checked
  against the archived `results.md`, recorded before quarantine). Do NOT run an
  analyzer pass over `_superseded_sf_cb_030/` — a `--metrics-dir`-only pass
  would read the v2-default `--vm-per-run` (empty rollups for v3 runs) and
  could overwrite v2 analysis outputs; the archived values are authoritative.
- Sustained-degradation metric: episode p50/p95/timeouts + CPU-clip share vs
  cf_cb POST and vs old sf_cb@0.30. The sf_cb row should now read as
  wrong-action (degraded + wasted), completing the matrix (cf_db degrades on
  db; sf_cb degrades + wastes on cb).

## 8. Baselines (old sf_cb@0.30, from results.md) and references

| Run | Seed | Timeout % | Served % | Storage activations | Episode p50 (ms) |
| --- | --- | --- | --- | --- | --- |
| sf_cb_1 | 42 | 1.62 | 98.4 | 2 (lan2, wasted) | 3.2 |
| sf_cb_2 | 42 | 0.00 | 100.0 | 1 (lan2, wasted) | 3.4 |
| sf_cb_3 | 42 | 0.00 | 100.0 | 1 (lan2, wasted) | 3.2 |
| sf_cb_4 | 42 | 0.00 | 100.0 | 2 (lan2, wasted) | 3.3 |
| sf_cb_5 | 42 | 0.00 | 100.0 | 2 (lan2, wasted) | 3.2 |
| sf_cb_6 | 43 | 0.00 | 100.0 | 2 (lan1+lan2, wasted) | 3.2 |

cf_cb reference (aligned, 0.15): timeout 0.65–4.06 %, served 95.3–99.0 %,
PRE p50 2.2–3.0 s → POST ~3.3 ms, 8 compute adds, 0 storage activations.

## 9. Post-run Doc Updates

- `results.md`: timeline row **"sf_cb rerun (2026-08-12)"** (avoid the "v2"
  label — that denotes the aborted v2 campaign); update the header "Runs"
  note; replace the sf_cb measurements/synthesis with the **DF/DT-p50
  + aggregate + timeout** set (§6.1a); point comparison graphs to the rebuilt
  set; note the full-campaign DF scan (2026-08-13).
- `run_matrix.md`: sf_cb row at 0.15/0.08; provenance md5s (new orchestrator +
  1-row order CSVs + env-hash reconciliation); P8 resolution; valid-pool note.
- `experiment_plan.md`: §3 locked-config table (already updated for the
  amendment) + §9 Changelog (already updated).
- `rq2_conclusions.md` / `rq2.md`: refresh the sf_cb caveat (waste-only →
  wrong-action cost) if the hypothesis holds.
- `post_run_analysis.md`: note the resolved confound.

## Appendix — Preflight checks (before launch, in order)

1. **Baseline pool verified (BEFORE quarantine):**
   `ls -d {REPO}/source/scripts/testing/metrics/*_rq2_{cf,sf,ba}_{cb,db}_[1-6]`
   shows **exactly 36 folders** (the v2 campaign used the same
   `_rq2_<cell>_1..3` label suffixes — a stray v2 folder would break the
   34-row expectation). Record the count.
2. Config edit verified: `grep 'sf_cb' tools/run_rq2_campaign.py` shows
   `STORAGE_CPUS=0.08 EDGE_CPUS=0.15` (done — see §3).
3. **Record the 6 original sf_cb run_ids** (full `<ts>_rq2_sf_cb_N`) BEFORE
   moving them (needed for the post-rebuild dataset check in §7).
4. Quarantine set 1 verified: `ls -d {METRICS}/*_rq2_sf_cb_[1-6]` is **empty**,
   and `ls {METRICS}/_superseded_sf_cb_030/` shows the 6 originals.
5. Quarantine set 2 verified: `ls -d {METRICS}/*_rq2_ba_db_2 {METRICS}/*_rq2_cf_db_5`
   is **empty**, and `ls {METRICS}/_superseded_incidents/` shows both.
6. `is_run_completed()` non-recursion **functionally confirmed**: after
   quarantine, run the launcher's exact glob for each sf_cb label
   (`ls -dt {METRICS}/*_rq2_sf_cb_1 …`) and confirm it returns empty (this is
   the same top-level glob `is_run_completed()` uses).
7. Stale launcher state removed: `rm -f {METRICS}/active_run.json` (a stale
   lock from 08-09→08-12 must not block launches).
8. No `rq2_sf_cb_*` run currently in flight (`pgrep -f RUN_LABEL`).
9. **P8 resolved (mandatory before the n=6 batch):** `rq2_sf_cb_preflight_1`
   run + analyzed (its folder quarantined in `{METRICS}/_superseded_pilot/`).
   "Alongside" is NOT allowed — a concurrent P8 on the same VM during the
   rerun would confound the runs; §6.2's Branch A/B reading needs P8's outcome
   in advance.
10. Disk headroom on `cloud-vm-rq2` (originals + incidents retained + pilot +
    6 new runs).
11. **Rerun code pinned:** a tag/commit for the amended launcher created (or
    the `d45cdb29…` hash recorded as the pinned rerun state) before launch.
12. **Docker CPU field confirmed:** inspect the build/launch scripts to confirm
    whether the platform sets `NanoCpus` or `CpuShares`; record which and the
    expected values before launch (the §5 spot check uses it).
13. Pilot `rq2_sf_cb_pilot` (seed 42) launched + analyzed per the §7 pilot
    gate: **confirmed** → proceed; **falsifying** → stop + re-examine V1;
    **ambiguous** → proceed to n=6 but record that no early signal was
    obtained.


