# RQ2 — Conclusions and Evidence-Framing (v3 + extension campaigns, era-matched compute-bound re-run)

> **Status:** 2026-10-04 · final evidence record.
> **Updated:** 2026-10-04 · re-synced to the thesis §5.3 reading: the compute
> recovery claim corrected (start-up transient, control-reproduced; no
> add-attributable recovery), no-op-arm results added, platform follow-ups
> dispositioned. Supersedes the 2026-08-09/08-10 v3-only framing.
> Complements [`rq2.md`](rq2.md) (question + provenance) and
> [`rq2_evaluation.md`](rq2_evaluation.md) (v2 design rationale) with **what the
> completed campaigns actually showed and what the thesis may claim**.
> **Sources:** v3 package
> [`experiment_plan.md`](../../../docs/operation/testing/experiment/v3/rq2/experiment_plan.md),
> [`results.md`](../../../docs/operation/testing/experiment/v3/rq2/results.md),
> [`post_run_analysis.md`](../../../docs/operation/testing/experiment/v3/rq2/post_run_analysis.md),
> per-run `run_summary.md` in `analysis/<ts>/`, `analysis/rq2_v3_cell_stats.csv`;
> extension package
> [`experiment_plan.md`](../../../docs/operation/testing/experiment/rq2_extension/experiment_plan.md),
> [`results.md`](../../../docs/operation/testing/experiment/rq2_extension/results.md),
> [`parte_addendum.md`](../../../docs/operation/testing/experiment/rq2_extension/parte_addendum.md),
> [`post_run_analysis.md`](../../../docs/operation/testing/experiment/rq2_extension/post_run_analysis.md),
> `analysis/rq2pe_signature.txt`, `analysis/rq2pe_gate_battery.csv`.
> **Campaigns:** (1) v3: tag `rq2-v3-campaign-20260808`, `cloud-vm-rq2`,
> 6 cells × 6 replicates, seeds 42 (`_1.._5`) / 43 (`_6`); valid pool
> **34 runs** (36 − `ba_db_2` − `cf_db_5`, both MEMCG OOM incidents).
> (2) Extension (no-op arm + order-shifted varying-demand sequences): tag
> `rq2-extension-final-20260927`, 30 runs, all valid. (3) Era-matched
> compute-bound re-run: tag `rq2-extension-parte-final-20261003`, 3 arms ×
> 6 replicates on the hardened build, 18 runs, all valid.

---

## 1. What the campaign settled

RQ2 asks how **bottleneck-aware scale-up**, compared with fixed single-tier
policies, affects targeted-tier relief, service recovery, and resource use
under compute-bound and data-access-bound demand (canonical wording,
`tese/main.tex` §1.3) — a bottleneck-aware controller choosing *which* tier to
scale from tier telemetry, versus the single-tier fixed policies an operator
would otherwise configure. The evidence base is three campaigns: the v3
storage-bind campaign; its extension (a no-op arm for the harm/benefit
contrasts, and order-shifted varying-demand sequences for one configuration
across sequential regimes); and a later era-matched re-run of the
compute-bound arms on the hardened build, which removed the build mismatch
from the compute-bound panel.

The headline, stated without spin:

1. **No compute recovery is attributable to the action**: the v3 pre/post
   collapse is a start-up transient (a zero-action control reproduced it), and
   on the hardened build the onset is flat; the only multi-second latency is a
   late-episode tail in the arms that scale compute.
2. **The storage scale-up *mechanism* works and is reproduced** — reserve
   activation, tier-CPU relief, no cold spawn, floor-safe scale-down.
3. **The storage *user-visible benefit over inaction* is met** (data-bound
   ratio 0.374 against the 0.85 threshold, 6/6 support); the pre-registered
   **cell-level p95 criterion remains not met** for two documented reasons (a
   tail phenomenon in the measurement contract; the ba arm's second-tier
   churn).
4. **Wrong-tier costs are asymmetric**: compute-first on data-bound demand
   degrades service relative to the aligned action but does not harm it
   relative to inaction (the harm criterion was not met); storage-first on
   compute-bound demand wastes resources at the tested intensity.
5. **The classifier commits to the detected tier** (88–93 % agreement;
   storage first on data-bound; compute scaled on compute-bound), and the
   era-matched re-run confirms full engagement.
6. **The two container OOM incidents are a platform finding** — resolved by
   the subsequent hardening cycle; 0 incidents across the 48 later runs.

---

## 2. What the evidence supports (lead with the solid)

### 2.1 Compute scale-up under compute-bound demand: no add-attributable recovery

- The v3 pre/post p50 collapse (**12/12** aligned compute-bound replicates:
  pre-add p50 2.2–3.0 s → post-add ~3.3 ms; ratio 0.001–0.025) is **not
  attributable to the action**: a control run that withheld the compute action
  reproduced the collapse (a start-up transient at the episode onset), and the
  value-floor check against the no-op arm is a null (cb p50 `nn_cb` 3.2 ms vs
  `cf_cb` 3.5 ms, ratio 1.094).
- **Era-matched re-run (2026-10-04, hardened build, 3 arms × 6 replicates):**
  onset latency is flat (~3 ms); the only multi-second latency is a
  **late-episode tail in the arms that scale compute** (p95 medians 4.6 s
  `cf`, 1.6 s `ba`), absent where nothing is scaled (storage-only and
  no-action, ~7 ms). The tail's mechanism is not isolated (timing only, not
  claimed).
- **The compute axis is bounded**: the rate ladder and onset bracketing found
  no regime in [1.5, 3.0] where the deficit is both capacity-bound and
  cleanly treatable (onset strictly inside (2.0, 2.25]); the base campaign
  intensity sits below onset.
- Health: timeout 0.49–4.06 %, served ≥95.3 %, D-gates clean; scale-down in
  `demand_drop` confirmed bidirectional elasticity.

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
- **Against inaction (no-op arm, extension campaign): the user-visible
  benefit is met** (Q-A2 ratio **0.374** ≤ 0.85, 6/6 support; pinned for the
  thesis as ≈0.37).

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
- **Against inaction (no-op arm): the pre-registered harm criterion was NOT
  met** (Q-A1 ratio **0.492**, ≥1.2 required; 5/5 replicates below unity). The
  measured ordering on the data-bound episode is matched storage < mismatched
  compute < no action: the wrong action fails to help as much as the aligned
  one rather than harming service relative to doing nothing.

### 2.4 The classifier commits to the correct tier: ✅

- `ba_db`: classifier-vs-episode agreement **88–93 %**; storage is the declared
  bottleneck and the reserve is activated first; compute is only added
  *after* storage relief (storage score below threshold). `ba_cb`: compute is
  scaled, storage correctly not (agreement ≈ chance on cb is the documented,
  expected outcome — storage never wins on a compute-bound episode).
- **Era-matched re-run:** engagement confirmed (4 compute adds per LAN in
  every compute-scaling run; added-backend served-share medians 71.1 % `cf` /
  71.9 % `ba`, at or above the v3 engagement record).

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

**Follow-up disposition (2026-10-04): resolved.** The memory follow-up was
executed in the platform hardening cycle of 2026-09-27 (concurrency gate,
`/service_pressure` cache, 256 in-flight threads with 1 MB stacks) together
with the fd/log-rotation config fixes; every later run used the frozen
hardened image. The two v3 exclusions remain in the v3 pool record; the 48
subsequent campaign runs (30 extension + 18 era-matched) carry **no OOM
incidents**.

---

## 5. The thesis claim — shaped per the evidence

| Claim | Supported by | Thesis wording |
| --- | --- | --- |
| Compute scale-up recovers service quality under compute-bound demand | ❌ **not supported** (v3: control-reproduced transient; era-matched: onset flat, no recovery) | ❌ **do NOT claim** — "no recovery is attributable to the compute action: onset latency is flat and the only multi-second latency is a late-episode tail in the arms that scale up the compute tier" |
| Storage action benefits users over inaction (data-bound) | Q-A2 0.374 ≤ 0.85, 6/6 support | ✅ **claim** — "the episode endpoint p95 was about 0.6 s against about 1.6 s under no action, a ratio of about 0.37 against the pre-registered threshold of 0.85" |
| Harm of the mismatched compute action vs inaction (data-bound) | Q-A1 0.492 (≥ 1.2 required); 5/5 below unity | ❌ **do NOT claim harm** — "the pre-registered harm criterion was not met; the measured ordering is the matched storage action, then the mismatched compute action, then no action" |
| Bottleneck-aware selection commits to the detected tier | ba agreement 88–93 % (db), storage-first on cb; era-matched adds 4/4 per LAN every compute-scaling run | ✅ **claim** — "the classifier activated the storage reserve first on the data-bound episode and scaled compute only after storage relief" |
| Storage scale-up relieves the storage tier (resource side) | CPU ratio 0.57–0.66× (sf_db 12/12), reproduced | ✅ **claim** — "storage CPU fell from ~66–71 % to ~45 % after reserve activation, in every aligned replicate" |
| Storage scale-up reduces user-visible p95 latency | p95 CI ⊃ 1.0 | ❌ **do NOT claim** — report as "the pre-registered p95 cell-level criterion was not met; the median ratio favoured relief (0.727× for sf_db) but the 95 % CI includes 1.0; two documented causes (tail asymmetry; ba churn)" |
| Wrong-tier scaling wastes resources (sf_cb) and fails to help (cf_db) | sf_cb corrected-config rerun (2026-08-13); Q-A1 (not met) | ⚠️ **claim with the fail-to-help framing** — resource waste is reproduced (compute pinned ~61 % of the cap with 0 adds; storage activations wasted); the harm-over-inaction wording is not supported |
| One configuration across sequential regimes (L4) | Part B shift cells: collapse counts cf 0/6, ba ≈1/5 | ❌ **do NOT claim recovery** — "the pre-registered sequence criterion is not confirmable; the shift runs either never bound or jammed" |
| The platform sustains the scaling churn | 34/36 v3 clean; 2 OOM incidents; 0 incidents in the 48 post-hardening runs | ⚠️ **claim as a documented limitation, now resolved** — "2 of 36 v3 runs were excluded as MEMCG OOM platform incidents; after the subsequent platform hardening no further incidents occurred" |

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
- Seed-43 replicates (`_6`) confirm direction (sf_db p95 0.879) but are not
  pooled into the CIs.
- The extension and era-matched campaigns use the same completed-only,
  both-lanes-pooled, nearest-rank conventions; their verdicts rest on
  plan-defined thresholds and replicate floors (the era-matched re-run: the
  episode p95 median decides, floor 5/6 valid).

---

## 7. Follow-ups / open items

1. **Late-episode tail in the compute-scaling arms (new, open).** The
   era-matched re-run isolated a multi-second tail that appears only where
   the compute tier is scaled mid-episode (`cf` 5/6 runs, `ba` 3/6; absent in
   storage-only and no-action). Its mechanism (provisioning churn vs routing
   redistribution) is not isolated; the record carries timing only. A
   targeted probe is the follow-up.
2. **The v3 start-up transient question is closed.** The transient is
   control-reproduced and does not appear on the hardened build; it is
   recorded as a build-era artifact of the original campaign.
3. **Data-bound sparse tail (~0.8 % >10 s)** — root cause still not isolated;
   the pre-registered window contract explanation (§3.3) carries the reported
   reading. Any window amendment must be pre-registered with rationale, not
   post-hoc.
4. **Platform memory limitation → resolved (2026-09-27).** The fix cycle
   (concurrency gate; `/service_pressure` cache; 256-thread / 1 MB-stack
   memory hardening) eliminated the OOM class; 0 incidents in the 48
   subsequent campaign runs.
5. **sf_cb confound → resolved (2026-08-13)** — the 0.15/0.08 rerun confirms
   the sf_cb wrong-action claim as resource-waste only (no user-visible cost
   at the tested sub-capacity intensity; DF 8.7–9.1 %; high compute
   utilization without relief).
6. **Sequence / regime hand-off recovery → not demonstrated (2026-09-28).**
   Q-B1: the shift runs either never bound (`cf_shdbcb_3`, `ba_shcbdb_1`) or
   jammed at the elevated rate; the L4 recoverability claim is bounded.
7. Replica-sync **bandwidth** was not metered (join time + node-minutes +
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
- Extension package — `docs/operation/testing/experiment/rq2_extension/`:
  experiment plan, `results.md`, `parte_addendum.md`, `post_run_analysis.md`,
  `analysis/rq2pe_signature.{txt,json}`, `analysis/rq2pe_gate_battery.csv`.
- Era-matched figures + data:
  `docs/operation/testing/experiment/v3/rq2/graphs/thesis/rq2_thesis_figure_data_era_matched.csv`
  (legacy `rq2_thesis_figure_data.csv` retained).
