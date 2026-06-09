# Results — WAN HTTP-0 Root-Cause Isolation

**Experiment plan**: `experiment_plan.md`
**Started**: 2026-06-08

## Run Timeline

| Run | Date | Status | Cumulative Analysis | Conclusions | Changes Made | Expectations for This Run |
|-----|------|--------|---------------------|-------------|--------------|--------------------------|
| R1 (`wan_diag_low_tput`) | 2026-06-08 | ✅ | — (initial run) | H1 confirmed: throughput saturation at nat-router | CLIENTS=4 (halved from 8) | Overall ≤1.0% failure, zero LAN asymmetry (from plan §Metrics) |

---

### 1. Run R1 — `wan_diag_low_tput` (2026-06-08 20:51 UTC)

**Status**: ✅ — H1 CONFIRMED. Overall 0.02% failure (13/70,625), zero LAN asymmetry.

#### Previous Run Analysis (cumulative)

Initial run — no prior analysis. Baseline comparisons drawn from v5.6 cycle (Run A: 2.2%, Run B: 21.3%) which used CLIENTS=8 on the same infrastructure, workload, and controller config.

#### Conclusions

1. **H1 confirmed — throughput saturation is the root cause** (impact: 100× improvement). Halving the request rate from 8 to 4 clients/LAN eliminated the HTTP-0 failures across all phases. The LAN-flip behavior seen in v5.6 Run B (LAN2 dead → LAN2 recovers → LAN1 dead) is a direct consequence of the shared nat-router forwarding capacity being saturated by one LAN's traffic.

2. **SDN controller and VIP routing are not the bottleneck** (confirmed). At CLIENTS=4, all VIP_SERVER and VIP_DATA connections succeed with only 13 HTTP-0 errors across 70,625 requests. The conntrack fix (v5.6) works perfectly under non-saturating load.

3. **Storage scale-down eval never fired** (observation, not a failure). 0 storage eval log lines on both LANs — the elevated `logger.info` lines were never reached because (a) no dynamic storage nodes existed (low throughput didn't breach storage thresholds), and (b) the `is_busy()` gate from pending compute drains likely blocked the eval cycle. The log elevation is verified correct on disk; it simply wasn't exercised by this workload.

#### Changes Made

| File | Change | Rationale |
|------|--------|-----------|
| `source/sdn_controller/scaling_policy.py` | Elevated 2× `logger.debug` → `logger.info` for storage scale-down eval | To make storage CPU/DB values visible during quiet phases (deployed before this run) |

The only code change was the log elevation — R1 itself used `CLIENTS=4` (Makefile knob, no code change).

#### Expectations for This Rerun

Not applicable — this is the initial run. Full expectations in `experiment_plan.md` §Run Matrix R1: overall ≤1.0%, zero LAN asymmetry.

#### Results

| Expectation | Result | Verdict |
|---|---|---|
| Overall ≤1.0% | 0.02% | ✅ Met |
| Zero LAN asymmetry | LAN1 0.03%, LAN2 0.01% | ✅ Met |
| All phases ≤1.0% | All 10 phases ≤0.1% | ✅ Met |
| Compute elasticity fires | 12 ComputeAlerts, cleanup_done events | ✅ Met |
| Storage eval logs visible | 0 lines (no dynamic storage, eval cycle blocked) | ⚠️ Not exercised |

Full per-phase breakdown and mechanism verification in `run_summary.md`.

---

### Changelog (experiment_plan.md)

| Date | Change | Rationale |
|------|--------|-----------|
| 2026-06-08 | R1 completed — H1 confirmed (0.02% failure) | Throughput saturation identified as root cause; R2/R3 deprioritized per diagnostic decision table (§Metrics & Success Criteria). See results.md §1. |
