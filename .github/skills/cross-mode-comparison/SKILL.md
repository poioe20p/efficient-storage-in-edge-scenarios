---
name: cross-mode-comparison
description: 'Use when: generating cross-mode (arm/policy/mode) comparison graphs for an experiment campaign after all its runs are analyzed. Triggers on: "comparison graphs", "cross-mode graphs", "generate comparison graphs", "compare runs", "rq graphs". Generic and plan-driven: resolves the experiment folder, the arm/mode vocabulary, and the comparison script from the experiment plan — never from hardcoded campaign versions.'
argument-hint: '<experiment plan folder under docs/operation/testing/experiment/, or a run label to resolve>'
---

# Cross-Mode Comparison Graphs

## Outcome

Generate the complete set of cross-mode comparison graphs for an experiment
campaign and archive them to `<experiment_dir>/graphs/comparison/`. Every graph
must show per-replicate variance (scatter dots on bars, per-event dots on box
plots), matching the variance standard of the campaign's measurement contract.

## When to Run

- After **all runs** of the campaign have completed per-run analysis
  (`run_summary.md` written, per-run graphs archived).
- Mandatory, not optional, for campaigns whose plan requires cross-run
  comparison (all thesis RQ campaigns).
- Re-run after any new runs are added to the campaign.

## Plan-Driven Resolution (never hardcode a campaign version)

The skill is intentionally generic — versions, modes, folders, and hosts change
between campaigns. Derive everything from the experiment plan:

1. **Resolve the experiment folder** — match the run label / workload shape to
   `docs/operation/testing/experiment/<category>/<experiment_name>/`, or use
   the folder the user names.

2. **Read the arm/mode vocabulary from the plan** — from `experiment_plan.md`,
   `run_matrix.md`, and `analysis_focus.md` extract:
   - the run-label pattern (e.g. `<label>_<arm>_<replicate>`);
   - the arms/modes/policies to compare and their grouping rule;
   - the per-run analysis outputs that feed the comparison (which CLIs/CSVs);
   - the measurement section the graphs must mirror.

3. **Group the runs** by that vocabulary — scan the metrics folder on the
   hosting VM, group by arm, order by replicate.

4. **Run the comparison script the plan designates** — per-RQ comparison
   tooling lives under `source/scripts/testing/analysis/<rq>/` (e.g.
   `campaign_analysis.py`, `generate_comparison_graphs.py`). If the plan does
   not designate a script, state it as a limitation — never invent one.

5. **Archive** the PNGs to `<experiment_dir>/graphs/comparison/` on the local
   repo. The comparison output dir on the VM is a staging area only.

## Guardrails

- Run folders stay on the hosting VM; only analysis outputs (PNGs, CSVs,
  summaries) sync back. Never copy run folders locally.
- Use the per-RQ VM host from the plan (`cloud-vm` / `cloud-vm-rq2` /
  `cloud-vm-rq3`) — never assume a host.
- Every graph must carry per-replicate variance; a graph without variance dots
  does not meet the standard.
- If the plan lacks a comparison script, an arm vocabulary, or a measurement
  contract, stop and report — do not guess.
