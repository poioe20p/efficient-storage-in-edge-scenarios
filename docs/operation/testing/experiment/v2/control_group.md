# Control Group — Scale vs No-Scale (generic reference for RQ1/RQ2/RQ3)

> **Status:** ✅ **Validated (2026-08-01)** — retune pair `cgr_scalable` / `cgr_noscale`
> passed: **storage reclaimed in-window** (3/LAN in `demand_drop`), error **1.31% vs
> 2.77%**, **rate 5.0 locked**. Caps are soft +1 (reserve standby by design).
> **Purpose:** A single, reproducible **scale-vs-no-scale control group** that
> each research-question experiment (RQ1, RQ2, RQ3) references as its *generic
> control* — the "regular scenario" contrast showing what the elastic platform
> buys (latency / throughput / CPU relief) versus a fixed-capacity system.
> **Source evidence:** [`post_implementation_verification/results.md`](post_implementation_verification/results.md) Runs 13–14 (V1h, `cgr_*`) + Judgment 14; prior config Runs 7–12 (V1e/V1f/V1g).
> **Parent:** [`post_implementation_verification/experiment_plan.md`](post_implementation_verification/experiment_plan.md).

---

## 1. What the control group is

- **Scalable arm** = the integrated elastic platform: compute scale-up, storage
  scale-up, and the persistent reserve **enabled** (`current_state_integrated.env`).
- **No-scale arm** = the identical platform with all capacity-adding mechanisms
  **disabled** (`MAX_DYNAMIC_COMPUTE=0`, `MAX_DYNAMIC_STORAGE=0`,
  `STORAGE_PERSISTENT_RESERVE_ENABLED=0`; `ablation_noscale.env`). Tier1
  selective-sync stays **on** in both arms, so the ablation isolates only the
  capacity mechanisms.
- Both arms run the **same** workload, hardware, and scale. The only differences
  are the three capacity knobs.

## 2. Recommended configuration

| Item | Value |
|---|---|
| Workload phase file | `phases_stress_plateau.json` (sustained 600 s plateau **rate 5.0 — locked**, `demand_drop` 420 s) |
| Scalable env | `current_state_integrated.env` (caps **3/3** active dynamic per LAN, storage scale-down **30 s + 3/5 windows** — control-group retune 2026-08-01; **median latency signals** — control-group reset 2026-08-03) |
| No-scale env | `ablation_noscale.env` |
| Latency signal statistic | **`LATENCY_SIGNAL_MODE=median` + COMPOSITE storage signal** (storage CPU 0.60 / median latency 0.40, CPU-aware scale-down — G0-v4, validated 2026-08-03; see [`mean_vs_median_signal_finding.md`](mean_vs_median_signal_finding.md) §6) |
| Hardware sim | `STORAGE_CPUS=0.08  EDGE_CPUS=0.15  WAN_RTT_MS=185  RANDOM_SEED=42` |
| Scale | `CLIENTS=24  CONTENT_ITEMS=3000  USERS=100  DATA_SEED=42  CURL_MAX_TIME=30` |
| RQ flags | none (defaults: `TELEMETRY_SOURCE=zmq`, `SCALEUP_POLICY=dual`, `READINESS_PROPAGATION=off`, `VIP_FLOW_ISOLATION=0`, `EDGE_FLOW_ISOLATION=0`) |
| Launch | `make -C source/scripts setup_network create_clients setup_test_data run_experiment` with `PHASES_CONFIG=testing/phases_override/phases_stress_plateau.json` |

## 3. Phase file (`phases_stress_plateau.json`, 1200 s)

| Phase | Dur | rate/cl | client frac | mix |
|---|---|---|---|---|
| baseline | 60 s | 1.0 | 0.1 | lookup 0.6 / feed 0.25 / pressure 0.15 |
| **compute_plateau** | **600 s** | **5.0** | 1.0 | lookup 0.2 / **feed 0.4** / pressure 0.3 / update 0.05 / aggregate 0.05 |
| recovery_gap | 120 s | 0.5 | 0.05 | baseline mix |
| demand_drop | 420 s | 1.0 | 0.1 | baseline mix |

The **single sustained 600 s plateau** is the defining feature: scale events land
inside one high-load window, so the **per-add CPU relief is directly measurable**
(unlike a sawtooth config, where spike→gap oscillation masks it). The **420 s
demand_drop** is the recovery runway: with the fast storage scale-down (30 s
cooldown + 3/5 windows ≈ 80 s per removal), it allows ~4–5 removal cycles so
storage reclaim completes **in-window** (RQ3 v7 precedent).

## 4. Thresholds in effect (from `controller_env_snapshot.env`)

| Group | Value |
|---|---|
| Features (scalable) | `STORAGE_PERSISTENT_RESERVE_ENABLED=1`, `SS_ENABLED=1`, `MAX_DYNAMIC_COMPUTE=3`, `MAX_DYNAMIC_STORAGE=3` (active per LAN; reserve standby extra) |
| Signal statistic | `LATENCY_SIGNAL_MODE=median` (both arms, control-group reset 2026-08-03) — ALL latency decision signals use the window median; CPU stays mean (bounded). Storage scale-up is **COMPOSITE** (G0-v4): `W_STORAGE_CPU=0.60`/`W_T_DB=0.40`; storage CPU floor 10/span 30; scale-down is CPU-aware (`STORAGE_SCALE_DOWN_CPU_AWARE=1`, `TAU_STORAGE_CPU_DOWN=22`) |
| Features (no-scale) | reserve + both dynamic caps = 0; `SS_ENABLED=1` |
| Compute scale-up | base threshold `0.18`, `W_CPU=0.60` `W_T_PROC=0.40`, CPU floor 10 / span 40, T_proc floor 25 / span 50 (base `osken-controller.env`), cooldown `45 s` (base `osken-controller.env`); no `peer relief` key — see `current_state_integrated.env` |
| Storage scale-up | **COMPOSITE (G0-v4):** `W_STORAGE_CPU=0.60` / `W_T_DB=0.40`, storage CPU floor **10** / span **30**, T_db floor **10** / span **50** (latency crossing 27.5 ms), τ `0.35`, cooldown `120 s` |
| Scale-down | compute `SCALEDOWN_COMPUTE_COOLDOWN_S=180`, `SCALE_DOWN_COMPUTE_REQUIRED=9`; storage **`SCALEDOWN_STORAGE_COOLDOWN_S=30`**, **`SCALE_DOWN_STORAGE_WINDOW_SIZE=5`**, **`SCALE_DOWN_STORAGE_REQUIRED=3`** (fast reclaim — retune 2026-08-01); `TAU_DB_DOWN_MS=8` + **CPU-aware gate** (`STORAGE_SCALE_DOWN_CPU_AWARE=1`, `TAU_STORAGE_CPU_DOWN=22`) — G0-v4 |
| WSM weights (base) | compute `W_CPU 0.3 / W_RAM 0.1 / W_REQUESTS 0.2 / W_HOPS 0.28`; storage `W_STORAGE_CPU 0.2 / W_RAM 0.1 / W_CONNECTIONS 0.2 / W_LAG 0.2 / W_HOPS 0.3` |
| VIP | `VIP_IDLE_TIMEOUT=30`, `VIP_HARD_TIMEOUT=60` |

## 5. Scale vs No-Scale — metric tables (validated at plateau rate 5.0, median-era composite — 2026-08-03)

> CPU% is **quota-relative** (100% = the `EDGE_CPUS=0.15` cap). Load-phase
> metrics pool the `compute_plateau` windows of the **median-era validated pair**
> (`cgr_v3_scalable` / `cgr_v3_noscale`, 2026-08-03, composite G0-v4 config).
> Retained evidence: `source/scripts/testing/metrics/20260803_043244_cgr_v3_scalable`
> and `.../20260803_073050_cgr_v3_noscale`.

> **Note:** the 2026-08-01 mean-era tables were superseded on 2026-08-03 by the
> median-era composite control (G0-v4). The composite reproduces the mean-era
> envelope (see [`mean_vs_median_signal_finding.md`](mean_vs_median_signal_finding.md) §6).

### 5.1 Service quality (user-facing)
| Metric | Scalable | No-scale | Effect |
|---|---|---|---|
| total requests | **21,460** | 10,372 | **×2.1** more demand served |
| error % (plateau) | **2.00** | 3.99 | scalable better |
| p50 latency (plateau) | **74 ms** | 662 ms | **×8.9** lower |
| p95 latency (plateau) | **4.33 s** | 8.38 s | −48% |

### 5.2 Resource / tier health (load phases pooled)
| Metric | Scalable | No-scale |
|---|---|---|
| storage CPU (quota-rel) | **31.2%** | 50.9% |
| DB latency (median T_db) | **4.6 ms** | 177 ms (×38) |
| avg servers | 2.0 | 1.0 |
| avg storage | 3.0 | 1.0 |
| peak storage (incl. reserve) | 5 | 1 |

### 5.3 Mechanism (per LAN)
| Metric | Scalable | No-scale |
|---|---|---|
| compute adds (per LAN) | 3–4 | 0 |
| storage adds incl. reserve (per LAN) | 4–7 | 0 |
| **storage reclaimed in `demand_drop`** | **st 3.0 → 2.0 (in-window)** | 0 |
| scale-down | fast reclaim 30 s + 3/5, CPU-aware gate | — |

→ The sustained plateau + 420 s `demand_drop` + 30 s storage scale-down means
storage capacity is now **reclaimed in-window** after demand drops (the v1g run
grew to 8/LAN with zero reclaim).

## 6. How each RQ references this control group

- **RQ1 (telemetry delivery):** RQ1 **reuses** the control group's platform +
  workload (scalable arm: `phases_stress_plateau.json`, `EDGE_CPUS=0.15`, caps
  3/3, storage scale-down 30 s+3/5), varying only `TELEMETRY_SOURCE`. Per thesis
  §2, RQ1 disables Tier 1 selective sync, persistent reserves, and cross-region
  storage — a deviation **no control arm validates** (both control arms run
  `SS_ENABLED=1`/reserve on), so RQ1 pre-flight G1 verifies scale-up still fires
  in the SS-off config rather than assuming it from these tables. **RQ1
  scale-down calibration (2026-08-02):** RQ1 uses compute
  `SCALE_DOWN_COMPUTE_WINDOW_SIZE=6` / `SCALE_DOWN_COMPUTE_REQUIRED=3` (3-of-6)
  with `TAU_CPU_DOWN=25` / `TAU_PROC_DOWN_MS=40` in all three arm env files so a
  lossy latest-state arm can fire compute scale-down (the drop's residual CPU
  ~17–24% exceeded the control's `TAU_CPU_DOWN=15`, so the criterion was the
  blocker); storage scale-down is not calibrated — it is capped for all arms by
  the reserve-floor guard at ≤2 dynamic nodes (RQ1 disables reserves).
- **RQ2 (bottleneck-aware scaling):** the control group is the **scalable-vs-no-scale
  contrast** that justifies measuring scale *selection*; RQ2 varies
  `SCALEUP_POLICY` on top of the scalable arm.
- **RQ3 (readiness propagation):** the control group is the readiness-`off`
  baseline; RQ3 varies `READINESS_PROPAGATION` on top of the scalable arm.
- In every case, the control-group tables (§5) are the "does the platform work /
  what does scaling buy" reference; each RQ reports its own deltas relative to
  this control.

## 7. Tuning note (locked decision)

- The 7.86% error in the scalable arm is a **rate-vs-CPU-cap** artifact: errors
  are spread uniformly across endpoints (~6–10%), i.e., the 0.15-core compute
  tier queues under the sustained **rate 6.0** plateau. `EDGE_CPUS` is **not**
  changed.
- **Validated (2026-08-01, `cgr_scalable` / `cgr_noscale`):** the retune met its
  targets. Storage **≤ ~4 active + 1 reserve standby/LAN** (down from 8/LAN) and
  **3 storage nodes/LAN reclaimed in-window** during `demand_drop` (v1g: 0);
  error % **1.31% (scalable) vs 2.77% (no-scale)** — the rate-6.0 inversion is
  gone; benefits preserved (p50 ×6.8, DB ×2.1, p95 −38%). Residual: the caps are
  *soft +1 by design* (the persistent reserve keeps one standby RS member beyond
  `MAX_DYNAMIC_STORAGE`), and `feed_ranking` carries a 30 s `CURL_MAX_TIME` tail
  (3.3% scalable vs 6.9% no-scale). Evidence + gates:
  [`post_implementation_verification/results.md`](post_implementation_verification/results.md) Runs 13–14 / Judgment 14,
  and the [`control_group_retune/experiment_plan.md`](control_group_retune/experiment_plan.md) plan.
- **Locked values (2026-08-01):** plateau `rate_per_client` **5.0**; caps **3/3**
  active dynamic per LAN (reserve standby extra); storage scale-down **30 s +
  3/5 windows**; `demand_drop` **420 s**.

---

## Changelog
| Date | Change | Rationale |
|---|---|---|
| 2026-08-01 | Created control-group reference from plateau runs (rate 6.0 evidence); moved to experiment-folder level; locked plateau rate = 5.0 | Define the generic scale-vs-no-scale control for RQ1/RQ2/RQ3; record config + thresholds |
| 2026-08-01 | Retuned control-group config: caps 3/3, storage scale-down 30 s + 3/5 windows, `demand_drop` 420 s; validation run `cgr_*` pending | v1g grew storage to 8/LAN with zero in-window reclaim — unacceptable for the edge scenario; see `control_group_retune/experiment_plan.md` |
| 2026-08-01 | **Validated** retune (`cgr_scalable`/`cgr_noscale`): storage reclaimed 3/LAN in-window, err% 1.31% vs 2.77%, caps soft +1 (reserve). §5 tables now at rate 5.0 | Control-group pair passed gates; retuned config is the recommended scale-vs-no-scale control for RQ1/RQ2/RQ3 |
| 2026-08-03 | **Control-group reset (mean→median signal):** scalable + no-scale arms now set `LATENCY_SIGNAL_MODE=median` — ALL latency decision signals (scale-up + scale-down, compute + storage) use the window median; CPU stays mean (bounded). RQ1 stays mean-based (`LATENCY_SIGNAL_MODE=mean`) so archived RQ1 results remain byte-identical. See [`mean_vs_median_signal_finding.md`](mean_vs_median_signal_finding.md) | Mean-based latency signals let one slow request dominate the decision in low-volume windows (RQ2 compute-bound evidence); median is robust |
| 2026-08-03 | **Matrix complete — composite wins (G0-v4):** run matrix (`cgr_v3_scalable` A-composite 2.00% err / `cgr_v4_scalable` B-narrow 3.29% / `cgr_v3_noscale` 3.99%; concurrent storage 3.0) — composite (storage CPU 0.60 / median latency 0.40, CPU-aware scale-down) folded into `current_state_integrated.env` + RQ2 envs; §5 tables rebuilt | Storage CPU is bounded and differentiates load (plateau 44% vs demand_drop 18%); the composite reproduces the mean-era envelope (2.0% err, 3.0 concurrent, storage CPU 31.2% ≈ mean-era 31.9%) where the pure-latency median could not |
