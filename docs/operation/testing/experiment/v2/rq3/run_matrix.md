# RQ3 v2 — Run Matrix

**Date**: 2026-08-04 · **Plan**: `rq3_v2_rework_plan.md` §2.9/§4 Phase 5.1 · **Status**: 🔵 planned — to be executed on `cloud-vm-rq3`

## 1. Campaign

- **Cells**: `direct` × 5, `discovery` × 5, `discovery_15` × 3 = **13 runs**.
- **Primary blocks**: 5 blocks of 2 (`direct`/`discovery`), block seeds
  2001–2005, within-block order randomized per block seed.
- **Sensitivity block**: `discovery_15` × 3, seed 2006, run consecutively
  after the primary blocks in the same VM session.
- **Counterbalance verification**: each arm leads ≥ 2 of 5 blocks, no
  systematic first-position bias; if the sampled orders fail, the block seeds
  are **resampled deterministically** (increment seed until the constraint
  holds) and the final seed set recorded here.
- **Orders**: written to `counterbalance_order_v2.csv` (never overwrite an
  existing file). Void re-runs take the void's matrix position (marked
  `void`/`replacement` + seed); ≤ 1 void per cell.
- **Run suffixes**: `direct` / `disc` / `disc15`.

## 2. Launch contract

```text
TRAFFIC_DRIVER_MODE=open_loop CURL_MAX_TIME=300 INFLIGHT_WINDOW=1024 DRAIN_S=30
```

- Arm env: `env/rq3_direct.env` (with `EDGE_APP_READY_EVENT=1`,
  `READINESS_EVENT_FALLBACK_S=5.0`), `env/rq3_discovery.env`,
  `env/rq3_discovery_15.env` (`DISCOVERY_POLL_INTERVAL_S=15.0`).
- Env files synced to `cloud-vm-rq3:~/rq3_env/` before the campaign.

## 3. Matrix (fill during execution)

| Block | Seed | Run 1 (arm/suffix) | Run 2 (arm/suffix) | Result | Notes |
|---|---|---|---|---|---|
| B1 | 2001 | direct / direct | discovery / disc | | |
| B2 | 2002 | discovery / disc | direct / direct | | |
| B3 | 2003 | direct / direct | discovery / disc | | |
| B4 | 2004 | discovery / disc | direct / direct | | |
| B5 | 2005 | direct / direct | discovery / disc | | |
| B6 | 2006 | discovery_15 / disc15 ×3 | | | sensitivity |

*(The within-block order above is a template — the actual per-block order is
sampled from each block seed and recorded in `counterbalance_order_v2.csv`,
with the arm-leading ≥ 2-of-5 check applied.)*

## 4. Runtime estimate

~20–25 min/run (60+180+180 = 420 s workload + 4 × 30 s drains + spawn/setup/
teardown). 13 runs ≈ 4.5–5.5 h + up to 3 void re-runs (≈ +1–1.5 h) +
pre-flight/calibration (~4–6 runs ≈ 2 h). **Under 1 VM-day**.

> The 4–6 run pre-flight/calibration estimate does **not** include Stage-5
> fallback-chain re-runs (R1/R2 re-tuning) — budget up to +2–3 runs if the
> first calibration rate is not feasible (see `rq3_preflight.md` §8).
