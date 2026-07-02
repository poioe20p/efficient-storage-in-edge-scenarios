# Experiment Campaign Brief

This document is the durable live runbook for VM-backed experiment campaigns.
Use it together with `testing_overview.md`, the experiment-runner agent, and
the specific experiment plan under `docs/operation/testing/experiment/` when a
campaign needs a concrete run matrix.

The purpose of this file is not to preserve stale one-off commands. Its purpose
is to keep the current operator workflow, current workload vocabulary, and
current launch surface in one place.

---

## Current Active Workload Surface

Canonical profile and overrides:

- `source/scripts/testing/phases.json`
- `source/scripts/testing/phases_override/phases_tier1_smoke.json`
- `source/scripts/testing/phases_override/phases_rq1_verify.json`
- `source/scripts/testing/phases_override/phases_mini.json`

Current seed and launch vocabulary:

- `CONTENT_ITEMS` and `USERS` at the `make` layer
- `--seed-content-items` and `--seed-users` at the `run_experiment.sh` layer
- `content_lookup`, `feed_ranking`, `service_pressure`, `content_update`, and
  `content_aggregate` as the current request-type names

Current workload-facing routes:

- `GET /content/<content_id>?requester=<user_id>`
- `GET /feed/<user_id>?limit=<N>`
- `GET /service_pressure?window_min=<minutes>&limit=<N>`
- `POST /content`
- `POST /content/aggregate`

If a campaign needs a different workload shape, edit `source/scripts/testing/phases.json`
or choose an existing profile under `source/scripts/testing/phases_override/`.
Do not point operators at nonexistent `phases_experiment_*.json` files.

---

## Operator Checklist

Before any run:

1. Read the campaign-specific experiment plan.
2. Confirm which phase file the run uses.
3. Confirm the current local code is the source of truth.
4. Sync changed runtime-bearing files to `cloud-vm`.
5. Rebuild any image touched under `source/docker/`.
6. Verify the remote files contain the expected content.
7. Confirm the required `sudo -n` make path is permitted.

The experiment-runner agent already enforces the code-sync and image-rebuild
workflow. This brief records the current operator-facing commands and policy.

---

## Canonical Launch Templates

### Canonical integrated profile

```bash
ssh -o ServerAliveInterval=60 cloud-vm "cd ~/efficient-storage-in-edge-scenarios; sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment RUN_LABEL=<label> PHASES_CONFIG=testing/phases.json WAN_RTT_MS=260 CLIENTS=48 CONTENT_ITEMS=6000 USERS=100 STORAGE_CPUS=0.10 SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1"
```

### Focused Tier 1 smoke

```bash
ssh -o ServerAliveInterval=60 cloud-vm "cd ~/efficient-storage-in-edge-scenarios; sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment RUN_LABEL=<label> PHASES_CONFIG=testing/phases_override/phases_tier1_smoke.json CLIENTS=6 CONTENT_ITEMS=30 USERS=40 SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1"
```

### Short verification profile

```bash
ssh -o ServerAliveInterval=60 cloud-vm "cd ~/efficient-storage-in-edge-scenarios; sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment RUN_LABEL=<label> PHASES_CONFIG=testing/phases_override/phases_rq1_verify.json CLIENTS=6 CONTENT_ITEMS=600 USERS=100 SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1"
```

Replace `<label>` with a campaign-specific run label. If a campaign needs a
customized canonical phase file, update `source/scripts/testing/phases.json`
first and let the run capture `phases_snapshot.json`.

---

## Live Checkpoint Template

Each campaign should define:

- objective
- intended run delta
- checkpoint question
- read-only evidence sources
- stop or restart criteria
- allowed between-run edit scope

Preferred read-only evidence sources during a live run:

- `current_phase.txt`
- `resource_stats.csv`
- `per_node_stats.csv`
- `container_events.csv`
- `controller_lan1.log`
- `controller_lan2.log`
- `service_logs/`

Do not modify repo files during an active run.

---

## Artifact Handling

After each completed run:

1. Resolve the run folder under `source/scripts/testing/metrics/`.
2. Copy the run folder back locally unless the plan explicitly says otherwise.
3. Verify the local copy before deleting any remote copy.
4. If controller logs are no longer needed, trim the run folder only after the
   summary exists.
5. Keep the run folder's `phases_snapshot.json` and
   `controller_env_snapshot.env`; they are part of the reproducibility contract.

For deep post-run interpretation and run-summary authoring, hand off to the
analysis workflow documented in `metrics-run-summary`.

---

## Between-Run Changes

Allowed between-run edits must be explicit in the experiment plan.

- Prefer the smallest possible change.
- Validate the touched slice before the next run.
- Keep `source/scripts/testing/phases.json` as the only canonical active phase
  profile unless the plan explicitly says to use one of the existing override
  files.

---

## Campaign Record Template

For a specific campaign, append or link only the current items that still drive
operator decisions:

- Campaign name
- Objective
- Run matrix
- Launch authority
- Checkpoint policy
- Artifact retention policy
- Completed-run outcomes that still affect the next run

Historical one-off run notes that no longer guide the active campaign should
live in experiment-specific plans, results docs, or run folders instead of
remaining here as stale workload-facing instructions.
