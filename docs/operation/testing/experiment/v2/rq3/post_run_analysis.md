# RQ3 v2 — Post-Run Analysis

**Status**: 🔵 placeholder — to be written after the Phase 6 campaign on `cloud-vm-rq3` (per the standard post-run workflow).

## Objective recap

How does readiness propagation (event-driven `app_ready` push vs periodic
`/ready` discovery) affect when a ready backend becomes usable capacity?

## Questions to answer

1. Did the admission gap degrade service (between-arm differential on
   gap-window pool `timeout_rate`), or is the honest conclusion a null on the
   consequence metrics (claim narrows to timing quantization)?
2. Did the quantization cost scale with the discovery interval
   (`discovery` vs `discovery_15`)?
3. Was the direct arm genuinely event-driven (admit_source fraction ≥ 0.80)?
4. Were the manipulation checks met (selection function held fixed, flow
   isolation valid, readiness criterion identical)?

## Evidence artifacts

- `admission_log_lan1/lan2.csv` (with `admit_source`)
- per-run `rq3_admission_analysis.py` reports + `per_run_summary.csv`
- per-run `rq3_flow_validation.py` reports
- `rq3v2_p3_01_stats.py` `stats_summary.csv`
- `counterbalance_order_v2.csv`
