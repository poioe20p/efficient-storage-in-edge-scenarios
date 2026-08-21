# RQ2 — Conclusions and Evidence-Framing (v3 campaign)

> **Status:** 2026-08-09 · final evidence record after the 36-run v3 campaign.
> **Updated:** 2026-08-10 · graphs cross-reference (per-run graphs now VM-only;
> curated thesis figure set added).
> Complements [`rq2.md`](rq2.md) (question + provenance) and
> [`rq2_evaluation.md`](rq2_evaluation.md) (v2 design rationale) with **what the
> completed campaign actually showed and what the thesis may claim**.
> **Sources:** [`experiment_plan.md`](../../docs/operation/testing/experiment/v3/rq2/experiment_plan.md)
> (v3), [`results.md`](../../docs/operation/testing/experiment/v3/rq2/results.md),
> [`post_run_analysis.md`](../../docs/operation/testing/experiment/v3/rq2/post_run_analysis.md),
> per-run `run_summary.md` in `analysis/<ts>/`, `analysis/rq2_v3_cell_stats.csv`.
> **Campaign:** tag `rq2-v3-campaign-20260808`, `cloud-vm-rq2`, 6 cells × 6
> replicates, seeds 42 (`_1.._5`) / 43 (`_6`); valid pool **34 runs**
> (36 − `ba_db_2` − `cf_db_5`, both MEMCG OOM incidents).

---

## 1. What the campaign settled

RQ2 asks whether **bottleneck-aware selection of compute or storage scale-out**
improves service recovery and resource management efficiency relative to
workload-agnostic fixed-priority policies when both actions are available
(canonical wording, `tese/main.tex` §1.3) — a bottleneck-aware controller
choosing *which* tier to scale from tier telemetry, versus the single-tier
fixed policies an operator would otherwise configure. The v3 campaign is the
evidence that answers it, at the storage-bind
config where the data tier actually binds (the v2 campaign could not show a
storage benefit and was aborted at run 13; v3 rebased on a locked config with a
persistent storage reserve).

The headline, stated without spin:

1. **Compute scale-up benefit (B1) is real, large, and reproduced** — every
   aligned compute-bound replicate.
2. **The storage scale-up *mechanism* works and is reproduced** — reserve
   activation, tier-CPU relief, no cold spawn, floor-safe scale-down.
3. **The storage *user-visible p95* benefit does not reach statistical
   significance at the pre-registered cell-level criterion** — for either
   aligned data-bound cell — for two documented reasons (a tail phenomenon in
   the measurement contract; the ba arm's second-tier churn).
4. **Wrong-tier scaling costs are real**: compute-first on data-bound demand
   degrades service; storage-first on compute-bound demand wastes resources.
5. **Two container OOM incidents are a platform finding** — not campaign noise.

---

## 2. What the evidence supports (lead with the solid)

### 2.1 B1 — compute scale-up benefit: ✅ robust

- **12/12** aligned compute-bound replicates (`cf_cb`, `ba_cb`, both seeds):
  pre-add p50 **2.2–3.0 s** (compute saturated) → post-add **~3.3 ms**; p50
  ratio **0.001–0.025** (threshold ≥2×, actual 40×–1000×). Direction
  consistent in every replicate.
- Healthy: timeout 0.49–4.06 % (≤5 %), served ≥95.3 %, D1=0/D2=0/D3, I1 met,
  F2 ≤3×. Scale-down in `demand_drop` confirmed bidirectional elasticity.

### 2.2 The storage reserve mechanism + tier-CPU relief: ✅ reproduced

- In **11/11** aligned data-bound replicates (`sf_db` 6, `ba_db` 5) the
  persistent reserve **activated on both LANs** (`[reserve] activated`, no cold
  spawn) and served reads (M1/M2).
- **Storage CPU relief is the robust storage signal**: pre-activation storage
  CPU **66–71 %** → post **42–49 %**; peak-CPU ratio **0.57–0.66× in all 12/12
  sf_db LANs** (criterion <0.75×); ba_db 9/10 LANs pass. V1 (bottleneck
  evidenced) holds.
- Scale-down in `demand_drop` was floor-safe (reserve satisfied the floor;
  0 reserve-floor blocks).

### 2.3 Wrong-action costs: ✅ as pre-registered (no-benefit arms)

- **`cf_db`** (compute-first on data-bound): compute scaled (6 adds), storage
  suppressed (no reserve activation in 5/5 valid); episode p50 ~36–78 ms and
  p95 ~706–1135 ms vs aligned `sf_db` (~40–70 ms / ~502–756 ms) — degraded
  service; compute adds gave no p50 benefit (ratio 0.13–1.52×).
- **`sf_cb`** (storage-first on compute-bound): **confound resolved by the
  2026-08-12/13 rerun at 0.15/0.08** (the original 0.30 allocation never bound —
  DF 0 % in all 6 originals). At the corrected config, 6/6 rerun replicates show
  **no user-visible wrong-action cost at the tested (sub-capacity) intensity**:
  agg p50 ~3.3 ms, timeout 0.22–0.53 %, DF 8.7–9.1 % (first ~60 s per episode
  only). The wrong-action cost is **resource-side**: compute tier pinned ~61 % of
  the 0.15 cap in 93–97 % of episode windows with 0 compute adds, plus wasted
  storage activations. The "or" (wastes resources **or** degrades service) is
  satisfied via resource waste; the user-service-quality leg on the cb axis is
  not demonstrated at this intensity (falsification-shaped 6/6; pilot outlier
  DF 52 % not reproducible).

### 2.4 The classifier commits to the correct tier: ✅

- `ba_db`: classifier-vs-episode agreement **88–93 %**; storage is the declared
  bottleneck and the reserve is activated first; compute is only added
  *after* storage relief (storage score below threshold). `ba_cb`: compute is
  scaled, storage correctly not (agreement ≈ chance on cb is the documented,
  expected outcome — storage never wins on a compute-bound episode).

---

## 3. The B2 p95 result — the gate that was not met (transparent section)

This section exists so the thesis reports the negative result exactly, with its
reasons, instead of letting the median hide the CI.

### 3.1 The pre-registered criterion

Per `experiment_plan.md` §6 (2026-08-08): B2 is met per LAN by the OR rule
(p95 < 0.8× OR peak storage-CPU < 0.75×). For the **cell-level verdict the p95
leg is primary**, evaluated as the **median of replicate p95 ratios with a 95 %
CI excluding 1.0**, computed on the **n=5 seed-42** replicates; the `_6`
seed-43 replicate is reported separately (demand-robustness, not pooled).

### 3.2 The numbers

| Cell | p95 ratio per replicate (seed-42) | Median (95 % CI) | CI excludes 1.0? | seed-43 |
| --- | --- | --- | --- | --- |
| `sf_db` | 0.579, 0.727, 0.574, 1.393, 1.050 | **0.727 [0.574, 1.393]** | **no** | 0.879 |
| `ba_db` | 0.984, 13.968, 1.181, 0.897 (n=4)* | **1.083 [0.897, 13.968]** | **no** | 22.199 |

\* ba_db's seed-42 pool is n=4 (`ba_db_2` excluded as an incident), so the
pre-registered n=5 CI could not be computed for this cell; the n=4 CI is
reported with this stated as a limitation.

**Verdict: the cell-level B2 p95 gate is NOT met for `sf_db` or `ba_db`** —
even though the CPU-relief leg passes (sf_db 12/12). The thesis must not claim
a reproduced user-visible p95 storage benefit.

### 3.3 Why — two documented causes

1. **A sparse completed-request tail in data-bound episodes.** ~0.8 % of
   completed requests take >10 s (30 s-bucket p99 up to ~84 s) with storage CPU
   only ~40 %. The pinned **PRE window is short** (30–60 s, ~3–5 k requests)
   and rarely contains a tail event; the **POST window is long** (300+ s,
   ~35–38 k requests) and always contains one. This **window-length asymmetry**
   inflates POST p95 independently of the scale action — a measurement-contract
   property, not evidence that the add hurt. Its root cause is not yet isolated.
2. **The ba arm's post-relief compute churn.** `ba_db` adds compute after
   storage relief; each compute add coincides with a 30 s-bucket p95 spike
   (ba_db_3: spikes at t≈120/180/270 s matching dyn adds at 121/211/351 s; p95
   up to ~69 s) and elevated timeout (ba_db_3 2.65 %, ba_db_6 4.42 % vs sf_db
   0.03–1.36 %). The **ba cost** — second-tier churn during a data-bound
   episode — is real and reproducible (2 of 5 ba_db replicates).

### 3.4 What this does and does not mean

- Does **not** mean the storage scale-up had no effect: the tier-CPU relief is
  reproduced, and the p95 "failures" partly reflect a measurement asymmetry the
  short PRE window cannot contain.
- Does **not** mean the storage add hurt users: in the tail-free majority the
  POST window is comparable or better (sf_db 3/5 seed-42 replicates pass <0.8×;
  lan2 passes in 4/5).
- **Does** mean the evidence cannot support a *statistically robust* p95 claim,
  and the thesis must say so.

---

## 4. Platform finding — the MEMCG OOM incidents (framed as a finding, not a footnote)

Two runs were excluded from evidence (D2 hard-gate violation: container
crash-exits), both with the **same confirmed mechanism** (kernel `dmesg`
`CONSTRAINT_MEMCG` kills of edge compute nodes):

| Incident | Cap | Kills | Consequence |
| --- | --- | --- | --- |
| `ba_db_2` (run 7) | **256 MB** (`EDGE_MEMORY` default) | 1 (t≈+74 s) | cascade: failed netns/veth cleanup → full flow rebuild → `server_count` 0 → mass timeouts → false scale-down churn |
| `cf_db_5` (run 25) | **512 MB** (after the raise) | 2 (t≈338 s, t≈532 s; anon-RSS ~462–463 MB at kill) | 30 s-bucket timeout 14 %→27 %→**47.7 %** after the first kill; served 90.4 % |

**Framing for the thesis (rec: platform finding, not a footnote):**

- The **512 MB hardening reduced but did not eliminate** the edge-server MEMCG
  OOM under compute churn — the two incidents bracket the phenomenon at 256 MB
  and 512 MB. The 256m→512m split (runs 1–14 vs 15+) is platform hardening, not
  a treatment; within-cell config splits are reported where a cell spans both
  caps (no direction change observed).
- These incidents are **evidence about the cost of churn** — thematically
  aligned with "efficient resource management," not random noise: aggressive
  multi-tier scaling drives memory pressure that the container cap cannot hold.
- The thesis should state: 34/36 runs were clean evidence; 2/36 were excluded
  as documented platform incidents with a confirmed root cause; the finding is a
  genuine **platform limitation of the current edge-server memory budget** and
  is reported as such (follow-up: raise the cap or fix memory accounting).

---

## 5. The thesis claim — shaped per the evidence

| Claim | Supported by | Thesis wording |
| --- | --- | --- |
| Compute scale-up recovers service quality under compute-bound demand | B1, 12/12, both seeds | ✅ **claim** — "p50 collapsed ~40–1000× after the first compute add, consistent across all replicates and both seeds" |
| Bottleneck-aware selection commits to the detected tier | ba agreement 88–93 % (db), storage-first on cb | ✅ **claim** — "the classifier activated the storage reserve first on the data-bound episode and scaled compute only after storage relief" |
| Storage scale-up relieves the storage tier (resource side) | CPU ratio 0.57–0.66× (sf_db 12/12), reproduced | ✅ **claim** — "storage CPU fell from ~66–71 % to ~45 % after reserve activation, in every aligned replicate" |
| Storage scale-up reduces user-visible p95 latency | p95 CI ⊃ 1.0 | ❌ **do NOT claim** — report as "the pre-registered p95 cell-level criterion was not met; the median ratio favoured relief (0.727× for sf_db) but the 95 % CI includes 1.0; two documented causes (tail asymmetry; ba churn)" |
| Wrong-tier scaling degrades service (cf_db) / wastes resources (sf_cb) | pre-registered no-benefit direction | ✅ **claim** — with the sf_cb confound resolved by the 2026-08-13 0.15 rerun; resource-waste framing confirmed at the corrected config (no user-visible cost at tested intensity) |
| The platform sustains the scaling churn | 34/36 clean; 2 OOM incidents | ⚠️ **claim as a documented limitation** — "2 of 36 runs were excluded as MEMCG OOM platform incidents (256 MB and 512 MB caps); the memory budget is a current platform limitation" |

**Wording rules (consistent with `rq2_evaluation.md` §7):** "consistent across
replicates", "large effect", "reproduced mechanism", "the pre-registered
criterion was not met"; never "significant", "proves", "optimal". Where a CI is
reported, it is reported in full — the median alone is never presented as the
result.

---

## 6. Statistical note

- All thresholds, window definitions (PRE/POST), and the CI-on-seed-42 rule
  were **pre-registered** in `experiment_plan.md` §6 before the campaign.
- The B2 p95 CI includes 1.0 for both aligned db cells → the p95 gate is not
  met; the CPU leg is reported as the carrying leg where it holds (sf_db all;
  ba_db lan2 all, lan1 except `ba_db_6`).
- `ba_db`'s seed-42 CI is n=4 (not the pre-registered n=5) — stated as a
  limitation in §3.2.
- Seed-43 replicates (`_6`) confirm direction (B1 robust; sf_db p95 0.879) but
  are not pooled into the CIs.

---

## 7. Follow-ups / open items

1. **Isolate the ~0.8 % >10 s completed-request tail** (driver stall / MongoDB
   read path / WAN / memory pressure) with a pre-registered probe — the single
   most valuable follow-up; it converts the biggest B2 ambiguity into a
   documented fact.
2. **Re-examine the B2 window contract** (PRE vs POST length asymmetry) — any
   amendment must be pre-registered with rationale, not post-hoc.
3. **Raise or fix the edge `EDGE_MEMORY` cap** — 2 OOM incidents at 256 MB and
   512 MB; current budget is a platform limitation under compute churn.
4. **sf_cb confound → resolved (2026-08-13)** — the 0.15/0.08 rerun confirms the
   sf_cb wrong-action claim as resource-waste only (no user-visible cost at the
   tested sub-capacity intensity; DF 8.7–9.1 %; high compute utilization without
   relief).
5. Replica-sync **bandwidth** was not metered (join time + node-minutes +
   transient CPU/latency measured instead) — stated limitation.

---

## 8. Cross-references

- `rq2.md` — question, gap, hypotheses (this folder).
- `rq2_evaluation.md` — v2 evaluation-design rationale (superseded design; v3
  is the evidence).
- `docs/operation/testing/experiment/v3/rq2/experiment_plan.md` — pre-registered
  gates and pinned windows.
- `docs/operation/testing/experiment/v3/rq2/results.md` — per-run measurements,
  judgment, root causes.
- `docs/operation/testing/experiment/v3/rq2/post_run_analysis.md` — capstone
  synthesis.
- `docs/operation/testing/experiment/v3/rq2/analysis/rq2_v3_cell_stats.csv` —
  cell-level CI table.
- `docs/operation/testing/experiment/v3/rq2/analysis/<ts>/run_summary.md` —
  per-run evidence.
- `docs/operation/testing/experiment/v3/rq2/graphs/` — `comparison/` (19 cross-mode
  graphs incl. `b1_p50_ratio.png`, `b2_cpu_ratio.png`, `b2_p95_ratio.png`) and the
  curated thesis figure set `thesis/` (17 graphs supporting the strong results);
  per-run graphs are archived on `cloud-vm-rq2` (run `analysis/` folders), not
  locally.
