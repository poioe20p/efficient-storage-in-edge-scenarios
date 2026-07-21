# RQ2 Calibration Plan — Stable Operating Point

**Date**: 2026-07-05
**Parent plan**: [`experiment_plan.md`](./experiment_plan.md)

---

## Problem

Two CP0 runs at CLIENTS=48 failed:
- **rate=6.0**: LAN2 edge_server_n2 fd exhaustion (`OSError: [Errno 24] Too many open files`). 25.2% failure.
- **rate=4.0**: Cascading spawn/die cycle (37 added, 30 removed). 53.4% failure.

Root cause: `topology_host` herds ALL traffic to one new backend (cost=0.0 for unknown stats). At 48 clients × 4 req/s = 192 req/s per LAN concentrated on one server, the Flask dev server can't cope.

Historical data from `storage_reserve_load_sweep` confirms: **single edge server saturates at ~100 req/s**.

---

## Calibration Strategy

Bisect CLIENTS to find the highest stable value where all three modes survive with ≥8 scale-up events and ≤5% failure rate.

Held constant: rate=4.0, WAN=50ms, SS_ENABLED=0, cross_region_ratio=0.0, phases_rq2.json.

---

## Steps

### Step 1 — Verify topology_lifecycle baseline

**Run**: `rq2_tl_cal` at CLIENTS=48, `rq2_topology_lifecycle.env`

If lifecycle fails → the RQ2 configuration itself is broken regardless of mode. Debug and fix before continuing.

If lifecycle passes → proceed to Step 2.

### Step 2 — Bisect topology_host

| Iteration | CLIENTS | Req/s per LAN | Expected outcome |
|---|---|---|---|
| 2a | 48 | 192 | Likely fails (herd overload) |
| 2b | 32 | 128 | May fail (above ~100 ceiling) |
| 2c | 24 | 96 | Borderline (at ceiling) |
| 2d | 16 | 64 | Should pass (well below ceiling) |

Stop at the first stable iteration. Verify ≥8 scale-up events at that level. If <8 events, try CLIENTS+4 until events ≥8.

### Step 3 — Lock configuration

Update `experiment_plan.md` with the calibrated CLIENTS value. Verify all three env overrides are correct. Then run the full 9-run campaign.

---

## Success Criteria per Calibration Run

| Check | Threshold |
|---|---|
| Overall failure rate | ≤5% |
| Scale-up events | ≥8 |
| No cascading spawn/die | <15 added containers |
| No fd exhaustion | 0 "Too many open files" in edge server logs |

---

## Run Matrix

| # | Label | Policy | CLIENTS | Purpose |
|---|---|---|---|---|
| C1 | `rq2_tl_cal` | topology_lifecycle | 48 | Verify baseline config works |
| C2 | `rq2_th_cal_48` | topology_host | 48 | Expected: fail |
| C3 | `rq2_th_cal_32` | topology_host | 32 | If C2 fails |
| C4 | `rq2_th_cal_24` | topology_host | 24 | If C3 fails |
| C5 | `rq2_th_cal_16` | topology_host | 16 | Fallback |

Between-run protocol: cleanup → reboot → verify → launch (per experiment plan §6).
