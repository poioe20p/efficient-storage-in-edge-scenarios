# RQ2 Extension — CPU-Cap Reduction Prior-Art Check (RQ3 Evidence)

**Date**: 2026-10-03 · **Status**: recorded survey — decision: **no new
quota-ladder probing campaign** · **Context**: requested before designing any
new "capacity-slack" probing runs for the RQ2 compute axis, to confirm whether
the CPU-cap reduction path (lower `EDGE_CPUS` to create a capacity-bound
compute tier whose queue scale-out can relieve) had already been tried.

## 1. Scope reviewed

All RQ3 experiment folders under [v3/](../v3/README.md):
[rq3/](../v3/rq3/experiment_plan.md) (saturation campaign — citable),
[rq3_timing/](../v3/rq3_timing/experiment_plan.md) (Family 4 — citable),
[rq3_soundness/](../v3/rq3_soundness/experiment_plan.md) (Family 5 — current),
[rq3_low_headroom_DO_NOT_CITE/](../v3/rq3_low_headroom_DO_NOT_CITE/experiment_plan.md),
[rq3_qoe_DO_NOT_CITE/](../v3/rq3_qoe_DO_NOT_CITE/experiment_plan.md),
[rq3_robustness_DO_NOT_CITE/](../v3/rq3_robustness_DO_NOT_CITE/experiment_plan.md);
plus the tuning-matrix source
[rq3_saturation/](../rq3_saturation/run_matrix.md) and the legacy
`research_q3` archive (no cap sweeps there).

**Citation status:** `rq3` and `rq3_timing` are citable evidence; the three
`_DO_NOT_CITE` families are archive-only (never cited as results); `rq3_soundness`
is preflight-only pending its E stage.

## 2. What was tried (the quota descents)

| Family / folder | `EDGE_CPUS` | Rate | Purpose | Outcome |
| --- | --- | --- | --- | --- |
| `rq3_saturation` P1–P4 (tuning) | **0.25 → 0.20 → 0.15** (rate fixed 1.5) | 1.5 | **Relief** descent: weaken backends until scale-up relief appears | P1 (mixed mix): 65–78 % CPU but relief **null** (DB co-bottleneck). P2 0.25: 24 % under-saturated. P3 0.20: 31 % under-saturated. **P4 0.15: 42–47 % + relief −18.9/−32.5 pp (−10.3/−26.7 reproduced) → locked.** P5 (rate 1.2 @ 0.20) not run |
| `v3/rq3` campaign (14 runs, n=7/arm) | 0.15 | 1.5 | Relief + timing + consequence at the locked cell | **R1 relief ✅ CPU leg** (per-run median 16.0/19.3 pp; G6 met). **Latency not the carrying leg** (R3 p50 45→49 ms, p95 117→140 ms — flat-to-marginal), C1/C2 **null**. Steady-state guard inexecutable (relief admissions sit in the plateau ramp) |
| `rq3_qoe` ladder (stopped) | **0.13 → 0.12 → 0.11** | 1.5 | **Consequence** descent: low quota + `loss_all` (static tier carries the full plateau, zero new capacity admitted) | Pressure 56–61 % (rung 0.13, below band) → 62–70 % (0.12, in band) → 64–65 % (0.11, in band); event_only failure **1.02 → 1.28 → 1.44 %**; contrast vs controls <1 pp → C1-INELIGIBLE at every rung; family **stopped** ("plateau-saturation failure rate structurally capped ~1.5 %"), paused after 7 runs, superseded 2026-09-08 |
| `rq3_low_headroom` (superseded) | planned **0.12 + 0.10** screens | 1.5 | Planned low-headroom capacity screens (direct/discovery) | **Never launched** — stopped 2026-09-06 at bridge stage; bridge artifacts retained |
| `rq3_robustness` (stopped) | 0.15 | 1.5 | Fault consequence at 0.15 | 19 valid runs; "cannot produce visible degradation at the 0.15 quota" (failure 0.28–0.69 %) → stopped |
| `rq3_timing` (36 runs) | **0.12** | **2.0** | Certified fault consequence | Visible only **under fault injection** (`loss_all`: event_only 8.3–14.4 % slow-share); no-fault tier healthy; overall pre-registered pass = **false** |
| `rq3_soundness` (current) | **0.12** | 2.0 | Fault robustness (Family 5) | Preflight P1 **complete 2026-10-03** (lock S=1200); 45-run E stage pending go/no-go |

Storage cap fixed at 0.08 in all of the above; **RAM was never shaped** —
`EDGE_CPUS` is the only swept cap axis. Demand escalation was explicitly
considered and **rejected** in the QoE plan (Approach B: "violates the
certified driver envelope … less reasonable as an edge regime") — consistent
with the Part D finding that 2.5/3.0 meltdowns are not capacity-bound.

## 3. Conclusion for the RQ2 design question

1. **The CPU-cap reduction path has been tried**, for relief (0.25→0.20→0.15,
   stopping at the first relief) and for consequence (0.13→0.12→0.11,
   stopping at a structural ~1.5 % failure ceiling). The standing low-quota
   working point is **0.12 at rate 2.0** (timing + soundness).
2. **The narrow untested sliver** is a *relief-focused measurement below 0.15*
   (0.12/0.10) — planned once (low-headroom) and superseded before launch. The
   adjacent evidence makes it low-value: even with **zero new capacity
   admitted** at 0.11–0.13, user-visible harm stayed ~1.0–1.4 % failure; and
   wherever relief did appear, it was **resource-side only** (latency did not
   carry) — the same conditional shape the RQ2 chapter already reports.
3. **Decision (2026-10-03): do not design a new quota-ladder probing
   campaign.** The task this check protects against — repeating prior work —
   would occur; any future compute-bound probing would need a genuinely new
   mechanism, not another cap or rate rung. If a citable low-quota anchor is
   ever needed, reuse `v3/rq3` (0.15, relief = CPU leg) and `v3/rq3_timing`
   (0.12/2.0, consequence via fault).

## Changelog

| Date | Change | Rationale |
| --- | --- | --- |
| 2026-10-03 | Survey created (read-only review of all v3 RQ3 folders + `rq3_saturation` + legacy `research_q3`) | Pre-design prior-art check before any new probing runs |
