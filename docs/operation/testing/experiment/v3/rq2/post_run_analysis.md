# Post-Run Analysis — RQ2 v3 Bottleneck-Aware Scaling (Storage-Bind Config)

**Date**: 2026-08-09 · **Plan**: [experiment_plan.md](experiment_plan.md) · **Results**: [results.md](results.md) · **Run matrix**: [run_matrix.md](run_matrix.md)

## 1. Objective

RQ2 asks whether **bottleneck-aware action selection** (which tier to scale) buys user-visible service quality compared with fixed-tier policies, on an edge platform where compute (edge) and data (storage) tiers scale independently. The independent variable is the **policy arm** — `fixed_compute_first` (cf), `fixed_storage_first` (sf), `bottleneck_aware` (ba) — crossed with the **episode type** — compute-bound (cb) / data-bound (db). The hypothesis is the mechanism relation *worse trigger awareness ⇒ worse user service quality*: the correctly-aligned tier should show a reproduced scale-up benefit (B1 for compute, B2 for storage), the mis-aligned arms should show the designed cost, and the bottleneck-aware arm should match the correct fixed arm without the wrong-action cost.

## 2. Mechanism

Six cells × 6 replicates = 36 runs in a counterbalanced 6-block design on `cloud-vm-rq2` (tag `rq2-v3-campaign-20260808`, per-run seeds 42 for `_1.._5` and 43 for `_6`). Two pre-registered workload shapes: compute-bound (rate 1.5, `service_pressure 1.0`, EDGE_CPUS 0.15 for cf/ba) and data-bound (rate 5.0, `content_lookup 0.9`, EDGE_CPUS 1.20) with a `demand_drop` recovery phase. The v3 storage mechanism is the **persistent reserve**: a pre-created `READY` storage standby is *activated* (`[reserve] activated`, no cold spawn) on load and replenished; scale-down in `demand_drop` is floor-safe. B2 is assessed on pinned PRE/POST windows (PRE = episode start → first activation; POST = ready+120 s → episode end) with the pre-registered cell-level criterion: median of replicate p95 ratios with a 95 % CI excluding 1.0, computed on the n=5 seed-42 pool, seed-43 reported separately.

## 3. Results

### Per-criterion verdict (pre-registered gates)

| Criterion | Result | Evidence |
| --- | --- | --- |
| B1 — compute scale-up benefit | ✅ **met and robust** | 12/12 aligned cb replicates: PRE p50 2.2–3.0 s → POST p50 ~3.3 ms (p50 ratio 0.001–0.025, threshold ≥2×). `results.md` Cross-Run Comparison. |
| B2 — storage scale-up benefit | ⚠️ **mechanism met, p95-leg cell-level gate NOT met** | sf_db p95 median 0.727 CI **[0.574, 1.393]** (⊃1.0); ba_db median 1.083 CI **[0.897, 13.968]** (n=4, ⊃1.0). CPU-relief leg: sf_db 12/12 LANs <0.75×; ba_db 9/10. `analysis/rq2_v3_cell_stats.csv`. |
| M1/M2 — mechanism exercised + usable | ✅ | Reserve activated both LANs in all 11 aligned db replicates (no cold spawn); activated reserves served; sf_db/ba_db scale-down (3–11 removals) in `demand_drop`. |
| V1 — intended bottleneck evidenced | ✅ | cb: edge CPU rising pre-add; db: storage CPU 66–71 % pre-activation. ba_db_6 lan1 is the single V1 miss (no CPU relief). |
| I1/I2 — demand + outcome classification | ✅ | >5 000 completed/LAN in every run; `status` column separates timeout/canceled (I2 clean). |
| D1–D3 — data-path + provenance | ✅ (2 incidents) | 0 NotPrimary, 0 restart of the controller, snapshots present in 36/36. **2 container OOM crashes → D2 violations → 2 runs excluded** (below). |
| F1/F2 — telemetry continuity + LAN symmetry | ✅ | No telemetry blackouts; F2 ≤3× in all retained runs. |

### Base-requirements verdict per arm

| Arm | Verdict | Note |
| --- | --- | --- |
| cf_cb | ✅ evidence | B1 robust; healthy; the aligned compute baseline. |
| ba_cb | ✅ evidence | B1 robust; classifier correct on cb (storage not scaled); one lan1 storage serving-add leak in ba_cb_2. |
| sf_cb | ✅ evidence (no-benefit) | No compute add; storage activations wasted (late/non-serving). Service healthy — **confound: sf static compute = 0.30 cpus vs 0.15**, so no user-visible collapse; cost is resource waste. |
| sf_db | ✅ evidence (B2 p95-leg nuance) | Reserve + CPU relief reproduced (n=6); p95-leg CI ⊃1.0 (tail + window-length asymmetry). |
| ba_db | ✅ evidence (B2 p95-leg nuance + ba cost) | Classifier commits storage-first (agree 88–93 %), then adds compute post-relief; compute churn degrades the tail (ba_db_3/ba_db_6: p95 ratio up to 35×, timeout up to 4.42 %). |
| cf_db | ✅ evidence (no-benefit) | Compute scaled on data-bound, storage suppressed; degraded vs sf_db; `cf_db_5` excluded (OOM incident). |

### Headline findings

1. **Compute scale-up benefit is real and reproducible** (B1, 12/12 replicates, both seeds) — the compute axis of the platform works as claimed.
2. **The storage reserve mechanism works** (activation, CPU relief, no cold spawn, floor-safe scale-down) — but the **user-visible p95 benefit does not survive the pre-registered cell-level CI test** for either aligned db cell. Two reproducible causes: (a) a sparse ~0.8 % completed-request tail (>10 s) that the long POST window always contains and the short PRE window rarely does; (b) the ba arm's post-relief compute churn injecting tail spikes. The CPU-relief leg is the robust storage signal (sf_db 12/12).
3. **The ba arm's cost is real**: ba_db matches sf_db when the compute adds stay quiet (ba_db_1/4/5) but degrades the tail and elevates timeouts when they fire hard (ba_db_3/6) — the "relief → next bottleneck" churn is not free.
4. **Two MEMCG OOM incidents** (ba_db_2 @256 MB, cf_db_5 @512 MB) — the 512 MB raise reduced but did not eliminate edge-server OOM under compute churn; both runs excluded (D2), valid pool = 34.

## 4. Gaps & Next Steps

- **B2 claim reframing**: the thesis cannot claim a reproduced p95 benefit for storage scale-up at the pre-registered threshold. The defensible claim is the **mechanism + tier-CPU relief** (reproduced), with the p95 nuance documented; alternatively re-examine the pinned-window contract (tail contamination) before any re-run.
- **Tail root cause** (~0.8 % completed >10 s in db episodes, storage CPU ~40 %): not isolated (driver stall / Mongo read path / WAN). A targeted probe is the follow-up.
- **Memory-cap hardening**: the edge-server MEMCG OOM persists at 512 MB under compute churn; raise the cap or fix memory accounting before any future compute-heavy campaign.
- **sf_cb confound**: 0.30 vs 0.15 static compute allocation prevents a clean service-quality comparison for the sf_cb wrong-action cost (only resource-waste framing is valid).
- **Not measured**: replica-sync bandwidth (join time + node-minutes measured instead — stated limitation in the plan).
- The seed-43 demand-robustness replicate (`_6`) confirms the direction on every arm (B1 robust; sf_db/ba_db p95 ratios 0.88/22.2) but is not pooled into the CIs (pre-registered).

---

*Synthesis of 34 valid runs + 2 documented incidents. Per-run details in `analysis/<run_timestamp>/run_summary.md`; graphs in `graphs/` (per-run + `comparison/`).*
