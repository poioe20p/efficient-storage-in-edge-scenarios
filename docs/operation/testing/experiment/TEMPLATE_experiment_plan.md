# Experiment Plan — [Title]

**Date**: YYYY-MM-DD · **Status**: [✅ Active / ⚠️ Needs Rerun / 🔄 In Progress / 📋 Planned]

<!-- The status emoji convention: ✅=passed/active, ⚠️=marginal/warning, 🔴=failed/blocking, 🔄=in progress, 📋=planned -->

## 1. Objective
<!-- Single paragraph: the overarching goal. What question does this experiment answer? What is the one thing we need to learn? Be specific and concrete. One experiment = one question. -->

## 2. Motivation & Hypothesis
<!-- 
Explain WHY this experiment is needed:
- What change was implemented that led to the assumption this needs testing? Link to the relevant code/docs.
- What is the expected outcome if the implementation works correctly?
- State the hypothesis concretely enough that the analyst can mark it met/missed/inconclusive.
- Identify the single independent variable being isolated.
- List everything held constant (workload shape, thresholds, routing policy, telemetry mode, schema, window size).
-->

## 3. Run Matrix
<!-- 
Table: each row = one run. Columns:
| # | Label | Purpose | Env Override / Policy | Phase File |
|---|---|---|---|---|
| 1 | label_a | Baseline run | current_state_integrated.env | phases.json |
| 2 | label_b | Changed X | override_with_X.env | phases.json |

Each run's purpose must state what changes vs the baseline and why.
If runs depend on each other, state the order explicitly.
-->

## 4. Run Configuration
<!-- 
Per-run launch commands. Use concrete `run_experiment.sh` knobs:
- `--phases-config`, `--run-label`, `--batch-dir`
- `--clients-per-lan`, `--seed-devices`, `--seed-nodes`
- Skip flags (`--skip-clients`, `--skip-seed`, `--skip-snapshot`)
- `--fault-plan` only when synthetic failure is in scope
- Any code/config toggle the run depends on
- Whether images must be rebuilt before launch

Provide the exact `sudo -n make ... run_experiment RUN_LABEL=<label> ...` invocation.

Also provide cleanup commands if applicable.
-->

## 5. Measurements & Success Criteria
<!-- 
WHAT to measure and HOW to judge success:

Primary evidence (what artifacts carry the answer):
- Latency files: client_requests.csv (per-phase/LAN/endpoint p95/p99, failures) via metrics_stats.py
- Resource files: resource_stats.csv, per_node_stats.csv (CPU/RAM, balance, server_count/storage_count, phase)
- Container lifecycle: container_events.csv (spawn/stop, Tier 2 storage, Tier 1 selective-sync anchors)
- Controller logs: controller_lan1.log / controller_lan2.log (alerts, scale decisions, recovery markers, exceptions)
- Phase/workload: phases_snapshot.json

Success criteria (numbered, each must be objectively checkable):
1. Criterion description → threshold (e.g., "≤1% failure rate in Phase 3")
2. Criterion description → threshold
...

Prefer per-phase and per-plane breakdowns over whole-run averages.
-->

## 6. Analysis Approach
<!-- 
HOW to analyze the measurements:
- Which comparisons matter (run A vs run B, phase X vs phase Y)
- Which CLIs/scripts to use (metrics_stats.py, parse_elasticity_logs.py, analysis CLIs)
- What patterns to look for in controller logs
- How to interpret elasticity events
- What graphs to generate (if any)
-->

## Appendix
<!-- Include ONLY if needed for this experiment. Keep each subsection brief; omit if empty. -->

### A. Prerequisites
<!-- Before-launch checklist: what must exist or be installed before running. -->

### B. Checkpoints (In-Run Observations)
<!-- Read-only checkpoints for the runner: trigger (phase/elapsed/symptom), what to check, what question it answers. -->

### C. Validity Threats & Limitations
<!-- Confounders, low-diversity risks, and what this experiment CANNOT prove. -->

### D. Artifact Contract
<!-- Confirm standard run-folder layout from testing_overview.md plus any experiment-specific files. -->

## Changelog
<!-- 
| Date | Change | Rationale |
|------|--------|-----------|
| YYYY-MM-DD | What changed | Why |
-->
