The only important things are is the docs folder and in the scripts folder

If you have to edit multiple files try to delegate each file editing to a subagent to save context tokens.

Before any changes you will perform always ask and clarify the changes you want to make.

When making changes, try to understand where in terms of context it belongs to and how it incorporates into the workflow. Also before making changes try to see what files or file the plan should be added to or create a new file if it's an entirely new file.

Always keep documentation in order and updated.

Disregard development cost, as it's not actually important.

## Canonical Experiment Files — No Duplicates

- **Phases file**: There is exactly ONE canonical phases JSON at `source/scripts/testing/phases.json`. When an experiment needs a different workload, EDIT this file in place. Never create `phases_<variant>.json` duplicates. The experiment run folder automatically captures a `phases_snapshot.json` copy.
- **Controller env override**: There is exactly ONE canonical env override at `source/scripts/testing/controller_env_overrides/current_state_integrated.env`. When an experiment needs different thresholds/cooldowns/caps, EDIT this file in place. Never create `current_state_<variant>.env` duplicates. The run folder captures a `controller_env_snapshot.env` copy with base/override provenance comments.
- If an experiment genuinely needs a DIFFERENT kind of config (e.g., tier1_hotspot enabled vs control), that's a separate configuration axis and a second env file is acceptable — but only if it serves a distinct, named configuration regime, not a per-experiment tweak.

## Temporary Scripts — Clean Up

- **Temporary one-time files** (scratch scripts, one-shot probes, ad-hoc analysis) must be placed in the `temp/` folder at the repo root — never in the repo root, `source/`, or `tools/` — and deleted after they have served their purpose. This is an explicit exception to the ask-and-clarify gate: throwaway scratch files in `temp/` do not require prior approval.
- If a script proves reusable, keep it and give it a proper name and location (e.g., under `tools/`).
