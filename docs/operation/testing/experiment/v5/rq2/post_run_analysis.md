# Post-Run Analysis — RQ2 v5 campaign (read-path renewal + storage ε-band)

**Date**: 2026-10-18 · **Campaign**: `rq2v5` (56 runs + 1 approved replacement)
· **Plan**: [`experiment_plan.md`](./experiment_plan.md) · **Design**:
[`rq2v5_plan.md`](./rq2v5_plan.md) · **Cell data**:
[`rq2v5_cell_stats.csv`](./rq2v5_cell_stats.csv) · **Full results**:
[`results.md`](./results.md)

---

## 1. Objective

Determine whether, under a genuinely storage-bound database press, **scaling the
pressed tier actually relieves it** — i.e. whether the platform can convert
added storage capacity into lower `t_db` (and whether adding *both* tiers beats
adding either alone), and whether the same holds under a mixed press. The
campaign is the thesis's RQ2 instrument: v4 had shown storage scale-up to be
inert (reads are pinned to storage members at connection birth), which
invalidated any storage-benefit claim.

- **Independent variable:** scaling action (`none` / `comp` / `stor` / `both`),
  held at fixed seat per regime (`db` sc=0.09/ec=1.20; `mx` sc=0.05/ec=0.15).
- **Hypothesis under test (D24):** in the storage press, `stor` and `both` beat
  `none` *and* `comp` on `t_db` + same-tier relief; in the mixed press every
  action arm beats `none` and `both` beats each single arm.

## 2. Mechanism

The v5 platform adds an **admission-time read-path renewal**: on every storage
admission the controller broadcasts a two-wave `POST /pool_renew` to the edge
(wave A immediately, wave B at +45 s after the 30 s warm-lease TTL), and the
edge retires its pinned Mongo connections so that newly born connections
re-select members. A storage **ε-band** (D21b: RR within 3 % of the argmin,
≥2 candidates) makes selection spread across near-equal members instead of
collapsing onto one. The db seat was recalibrated (sc 0.15→0.09) so the
signature member actually saturates (~98 % CPU under `none`), and
`EDGE_MEMORY` was raised 256 m→384 m after pilot OOMs.

- **Design:** 2 regimes × 4 modes × 7 seeds (42–48), regime-major, per-seed mode
  order identical to v4 (paired comparability). mx phases: baseline 60 s /
  mixed_episode 600 s / recovery 120 s / demand_drop 420 s / idle_tail 420 s;
  db phases: baseline 30 s / data_bound_episode 480 s / recovery 60 s /
  demand_drop 360 s.
- **Instrumentation:** `window_log_lanX.jsonl` (10 s windows; `t_db`, `t_proc`,
  per-member CPU, member count), `elasticity_events.csv` (adds/readies/
  removals), controller logs (`[pool_renew] broadcast`, `storage_band=`,
  culls), client request CSVs (outcome classes).
- **Held constant:** workload seeds, client count, hash factor, read
  preference (`secondaryPreferred`), pins file (`EDGE_POOL_RENEW_*`,
  `EDGE_MEMORY=384m`), phases workload per regime.

## 3. Results

### 3.1 D24 success criteria (verdicts at three materiality readings)

| Gate | Direction-only | ≥5 % | ≥20 % |
|---|---|---|---|
| D1 `both`@db > `none` (t_db + relief) | ✅ 7/7 | ✅ 7/7 | ✅ 7/7 |
| D2 `stor`@db > `none` (t_db + relief) | ✅ 7/7 | ✅ 6/7 | ❌ 5/7 |
| D3 `both`@db > `comp` | ✅ 7/7 | ✅ 7/7 | ✅ 7/7 |
| D4 `stor`@db > `comp` | ✅ 7/7 | ✅ 7/7 | ✅ 7/7 |
| M1 `stor`@mx > `none` (any of t_db/t_proc/relief) | ✅ 7/7 | ✅ 7/7 | ✅ 7/7 |
| M2 `comp`@mx > `none` | ✅ 7/7 | ✅ 7/7 | ✅ 7/7 |
| M3 `both`@mx > `none` | ✅ 7/7 | ✅ 7/7 | ✅ 7/7 |
| M4 `both`@mx > `stor` | ✅ 7/7 | ✅ 7/7 | ✅ 7/7 |
| M5 `both`@mx > `comp` | ✅ 7/7 | ✅ 7/7 | ✅ 7/7 |

✅ **Registered verdict: all nine D24 hard gates pass** under the
direction-only materiality rule (D25, author 2026-10-18). Sensitivity: the only
threshold-sensitive gate is D2 (6/7 at ≥ 5 %, 5/7 at ≥ 20 %), flagged below.

Key evidence: db `none` runs the signature member at **97.8/98.3 %** CPU with
`t_db` ≈ **2.15 s**; `stor`/`both` deliver **60–90 ms** in the healthy seeds
(with the member dropping to **42–47 %** and 3 members carrying traffic);
`comp`@db **worsens** `t_db` to **4.2 s** while improving `t_proc` 51→15 ms.
mx ordering is unanimous in 7/7 seeds: **both 6.4 ms < comp 9.7 ≪ stor 90.4 <
none 103.6**.

### 3.2 Base-requirements verdict (`docs/operation/testing/testing_requirements.md`)

| Gate | Verdict | Evidence |
|---|---|---|
| **B1** compute benefit | ✅ met | `comp`@mx `t_proc` 124→10 ms and `t_db` 103.6→9.7 ms (7/7 seeds); `comp`@db `t_proc` 51→15 ms |
| **B2** storage benefit | ✅ met (with flag) | direction in 8/8 arms; strong in 4–5/7 db seeds (`t_db` 2.15 s→60–69 ms, storage CPU 98→42–47 %); **3/8 db arms show only partial relief** (see §4) |
| **M1** claimed scale-up fires | ✅ met | storage adds per lane per run: db 6/6, mx 7/7; scale-down present when applicable (db 5/lane; mx `stor` has none — v4 baseline, plan made no recovery claim) |
| **M2** new capacity usable | ✅ met (proxy) | `node_ready_timing` 1:1 with adds; every added member appears in episode windows with non-zero CPU (per-member request counts are not exported — proxy, not direct) |
| **V1** intended bottleneck | ✅ met | db `none`: member 97.8/98.3 % CPU, `t_db` ≈2.15 s; mx `none`: `t_proc` ≈124 ms (edge-bound) with storage at 41 % |
| **I1** enough demand | ✅ met | ≈58 k offered requests per LAN per run; ≥19 k completed in the harshest arm |
| **I2** honest outcomes | ✅ met | `completed` / `timeout` / `canceled` are distinct status classes; completion computed on 200-only |
| **D1** data-path clean | ✅ met | **zero** `NotPrimary*` occurrences across all 57 runs' client CSVs |
| **D2** no mid-run crash | ⚠️ **missed in 2/57** | edge OOM at episode onset: `stor_db_43` (replaced, spare 1/14) and `both_db_48` (retained by author decision; hard metrics valid, soft completion 42 %) |
| **D3** provenance | ✅ met | `phases_snapshot.json` + `controller_env_snapshot.env` + `.run_completed` present in **57/57** |

Flags: **F2 LAN symmetry** — mostly good; the intermittency cluster (§4) is
lane-2-asymmetric (ratios 1.0–21× between lanes), reported not invalidated.

### 3.3 Cross-run trends (confirmed, ≥2 independent runs)

1. **Ordering (mx):** `both` < `comp` ≪ `stor` < `none` — 7/7 seeds, both lanes,
   stable to ±2 ms. This is the RQ2 headline for the mixed regime.
2. **Wrong-action signature (db):** `comp` raises `t_db` above `none`
   (median 3.61 s vs 2.08 s; 7/7 seeds) while improving `t_proc` and
   completion — a clean demonstration that scaling the un-pressed tier can hurt
   the pressed metric.
3. **Relief intermittency (db `stor`):** 3 of 8 `stor` arms deliver only
   partial relief (`43_r1` 1166/1796, `44` 89/1932, `48` 68/545 ms) while the
   admission/renewal census is complete in all of them (6/6 adds, 5–6
   broadcasts, band picks present). Mechanism fires, delivery fails — leading
   hypothesis: wave-B selection while member stats are still lagging
   (`storage_band` picking a cold member; plan §7.3). **Tentative** — no
   edge-side fire logs survive the run (containers recreated), so this is
   inferred from census + outcome, not proven.

## 4. Gaps & Next Steps

- **Materiality rule for "better": resolved by D25** (author, 2026-10-18 —
  direction only; "if the overall direction stands then that's good enough").
  The stricter readings (≥ 5 % ⇒ D2 6/7; ≥ 20 % ⇒ D2 5/7) remain reported as
  sensitivity and should travel with any storage-benefit claim in the thesis.
- **Why does relief delivery fail in ~1/3 of `stor`@db runs?** Untested
  hypotheses: wave-B band selection with stale member stats; connection-birth
  scarcity during the press; lan-2-specific edge saturation. A follow-up needs
  (a) edge-log capture per run (currently lost with the container), (b)
  per-connection / per-member request accounting, (c) a controlled test that
  pins wave-B timing vs telemetry cadence.
- **Edge OOM at press onset** (2/56 at 384 m, ~367–370 MB peaks; 256 m killed
  2/2 pilots). 512 m is the evidence-backed candidate; changing it now would
  break comparability with this campaign.
- **Not measured**: per-member request counts (M2 is proxy-verified), the
  `t_db` read/write split per member, and any client-side effect of the
  renewal epoch churn beyond completion/latency aggregates.
- **Campaign-level evidence is complete** (57/57 runs with provenance, zero
  culls, zero data-path errors); only the two OOM runs carry D2 exceptions, one
  of which was replaced.
- **Thesis implication:** RQ2's storage-benefit claim is supportable at the
  cell level (D1/D3/D4 unambiguous; D2 depends on the materiality rule), and
  the mx ordering claim is robust. The honest wording must carry the
  intermittency caveat: storage scale-up *can* relieve a storage-bound press
  (it never could in v4), but delivery is not yet deterministic.
