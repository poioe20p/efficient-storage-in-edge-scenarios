---
name: auto-review
description: >-
  Use when: an agent has created or modified a file, plan, or implementation
  and needs a sub-agent review before finalizing. Spawns the Reviewer agent
  (deepseek-v4-flash, high thinking) to flag issues, then the calling agent
  fixes them. Triggers on: after implementing code, after authoring a plan,
  after creating experiment plans, before declaring work complete.
argument-hint: '<file or plan to review> [--implemented | --to-be-implemented]'
---

# Auto-Review Gate

## Purpose

Every file creation or modification by an implementation or design agent must
pass through a review gate before being considered complete. This skill spawns
the **Reviewer** agent as a sub-agent to find and flag issues, then the calling
agent fixes them.

## Workflow

### Step 1 — Invoke the Reviewer

Spawn the `Reviewer` agent as a sub-agent with these parameters:

- **Model**: `deepseek-v4-flash` with `reasoning: high` and
  `thinking-effort: high`
- **Input**: the file(s) to review and the review mode:
  - `--implemented` for already-implemented code, config, or docs
  - `--to-be-implemented` for plans that have not yet been built
- **Constraint**: the reviewer only flags issues — it does not propose fixes

### Step 2 — Triage Issues

The reviewer returns a list of issues categorized by severity:

- 🔴 **Critical** — broken logic, missing requirement, will cause failure
- 🟡 **Warning** — likely problem, ambiguous, fragile, or inconsistent
- 🔵 **Observation** — minor issue, style, clarity, forward-compatibility

### Step 3 — Fix

1. Fix all 🔴 Critical issues. These are blockers.
2. Fix all 🟡 Warning issues. These are likely to cause problems.
3. Review 🔵 Observations and fix those that improve clarity or correctness.
4. If substantive changes were made during fixing, re-run the review gate
   (go back to Step 1) on the changed portions only.

### Step 4 — Finalize

Only after all critical and warning issues are resolved, mark the work as
complete.

## Integration Points

This skill is invoked by these agents at these specific points in their
workflow:

| Agent | Trigger Point |
|---|---|
| `edge-implementation-developer` | After implementing code, before declaring done |
| `planning-architect-edge` | After producing an implementation plan, before presenting to user |
| `experiment-designer-edge` | After authoring an experiment plan, before finalizing |

## Constraints

- Do not skip the review gate for "trivial" changes — even small edits can
  introduce bugs.
- Do not argue with the reviewer's findings — if a flag is incorrect, fix
  the underlying ambiguity that caused the false positive.
- Do not finalize until all 🔴 and 🟡 issues are addressed.
- The reviewer sub-agent must use `deepseek-v4-flash` with high thinking —
  do not substitute a different model.
