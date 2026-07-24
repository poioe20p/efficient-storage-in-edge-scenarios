---
name: experiment-post-analysis
description: >-
  Use when: an experiment run has completed and been analyzed — trace the
  experiment's objective, how it tried to reach that objective, and what the
  results show. Produces a structured post_run_analysis.md in the experiment
  plan folder. Triggers on: 'post-run analysis', 'summarize experiment',
  'experiment conclusion', 'what did we learn', after run_summary.md is written.
argument-hint: '<path to experiment plan folder under docs/operation/testing/experiment/>'
---

# Experiment Post-Run Analysis

## Outcome

Produce a structured `post_run_analysis.md` in the experiment plan folder
(`docs/operation/testing/experiment/<name>/`) that traces the full arc of the
experiment: what it set out to determine → how it tried to determine it → what
the results actually show.

This is the **capstone** document for an experiment campaign. It should be
readable standalone — a future reader should understand the experiment's
purpose, design, and conclusions without reading the raw run artifacts.

## When to Run

- After the **Edge Experiment Analyzer** has completed single-run analysis
  (`run_summary.md` written, graphs archived) for all runs in the campaign.
- This is the final step before declaring an experiment campaign complete.

## Input Resolution

1. Accept a path to an experiment plan folder, e.g.
   `docs/operation/testing/experiment/rq1_thesis_final/`.
2. Confirm the folder contains `experiment_plan.md`. If missing, stop and
   report.
3. Check for `results.md` — may or may not exist depending on whether this is
   a single-run or multi-run campaign.

## Evidence To Inspect

Read these files in the experiment folder before writing conclusions:

- `experiment_plan.md` — the source of truth for intent, hypothesis, variable,
  success criteria, and expected outcomes.
- `results.md` (if present) — the cumulative timeline of runs, their
  conclusions, and changes made.
- `run_summary.md` files in each referenced run folder — per-run verdicts and
  evidence.
- `graphs/` folder (if present) — archived comparison and per-run graphs.

## Required Structure

Author `post_run_analysis.md` with these sections:

### 1. Objective

- What was the experiment trying to determine? One paragraph.
- Link to the thesis RQ if applicable.
- State the independent variable and what hypothesis was being tested.

### 2. Mechanism

- How did the experiment try to reach that objective?
- Summarize the experimental design: run matrix, phases/workload, what was
  varied vs held constant.
- Reference the key configuration choices (phases, env overrides, controller
  settings).

### 3. Results

- Did the experiment meet its success criteria? Per-criterion verdict
  (✅ met / ❌ missed / ⚠️ inconclusive).
- Key evidence: latency numbers, resource metrics, controller behavior.
- Cross-run trends if multiple runs exist.

### 4. Gaps & Next Steps

- What remains unclear or untested?
- What would a follow-up experiment need to address?
- Limitations of the current evidence.

## Working Style

- Be concise. This is a synthesis document, not a log.
- Every claim must reference specific evidence (a run folder, a graph, a
  metric).
- Distinguish between confirmed findings (backed by multiple runs) and
  tentative observations (single-run or circumstantial).
- If the experiment failed to answer its question, say so directly — do not
  spin inconclusive results as findings.

## Constraints

- Do not fabricate conclusions when data is missing or conflicting.
- Do not duplicate the full content of `run_summary.md` or `results.md` —
  synthesize, don't repeat.
- Do not modify `experiment_plan.md` or `results.md` — this is a new,
  separate document.
- If the experiment folder already has a `post_run_analysis.md`, update it
  rather than overwriting (append a dated revision section).
