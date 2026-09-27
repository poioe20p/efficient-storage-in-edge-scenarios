# RQ3 QoE-Consequence Configuration Discovery — Run Matrix

Parent plan: [`experiment_plan.md`](experiment_plan.md) · Host: `cloud-vm-rq3`
· Frozen base: commit `852a8a3` (robustness final attestation); tag
`rq3qoe-preflight-<date>` recorded in the manifest at preparation time.

Launch: `rq3qoe_p1_01_launch_run.sh <arm> <fault> <label> <seed> <edge_cpus>`.
The run folder is `metrics/<timestamp>_<label>`; labels are globally unique.

## Label convention

- **Discovery** runs (C1/C3) use block ordinals **50, 51, …**, assigned
  sequentially as runs are scheduled (append-only in
  [`preflight_log.md`](preflight_log.md)): `rq3qoe_<cell>_<arm>_<NN>`.
- **Evidence (E)** runs use blocks **1–6**: `rq3qoe_<cell>_<arm>_<block>`.
  Discovery ordinals ≥50 never collide with E block numbers 1–6.

## Discovery stage (per rung, ladder 0.13 → 0.09)

One rung at a time; the first eligible rung whose C2 contrast is visible AND
bounded (Δ_timeout ≥5 pp OR Δ_slow ≥5 pp — slow-share amendment 2026-09-08)
is locked and immediately confirmed (C3) — **descending stops the moment
visible degradation is found** (user directive). A visible-but-unbounded
contrast is a STOP-NULL. If a rung is C1-ineligible the ladder descends
without C3. Rung recipes (ordinals continue across rungs):

| Stage | Seed | Runs (per rung) | Labels (first rung 0.13; continue ordinals on later rungs) | Purpose |
| --- | ---: | --- | --- | --- |
| C1 | 5301 | 3 | `rq3qoe_loss_all_event_only_50`, `rq3qoe_loss_all_hybrid_51`, `rq3qoe_loss_all_reconcile_52` | eligibility + C2 contrast read |
| C3 | 5302 | 4 | `rq3qoe_loss_all_event_only_53`, `rq3qoe_loss_all_hybrid_54`, `rq3qoe_loss_all_reconcile_55`, `rq3qoe_none_event_only_56` | lock confirmation seed A |
| C3 | 5303 | 4 | `rq3qoe_loss_all_event_only_57`, `rq3qoe_loss_all_hybrid_58`, `rq3qoe_loss_all_reconcile_59`, `rq3qoe_none_event_only_60` | lock confirmation seed B |

The C3 label ordinals in the table above are the first-rung (0.13) recipe;
live discovery continues ordinals across rungs via the append-only
preflight_log (0.12 C1 used 53–55; 0.11 continues from 56). C3 runs only at
the first eligible rung with a visible, bounded contrast; each C3 screen
invocation gets `--c1-json <c1.json>` (contract_version 2) and confirms the
`lock_component` on both seeds (slow-share amendment 2026-09-08). All
discovery runs at the rung's `EDGE_CPUS` (quota snapshot written by the
launcher). On C3 lock: write `rq3qoe_quota_lock.json` (locked `EDGE_CPUS`) and
proceed to E. Midpoint rule adds one C1 screen at the midpoint quota when rung
q is eligible but shows no visible contrast and rung q+1 is C1-ineligible.
Verdict exit codes: `0` lock / `2` descend / `3` STOP-NULL.

## Evidence stage — E (54 runs, headline evidence)

Cells `none`, `loss_all`, `loss_alt` × arms × 6 blocks at the **locked**
`EDGE_CPUS`. Block seeds 5201–5206. Arm order rotates per block (replicate
r = rotation r); within a block cells run arm-major in order
none → loss_all → loss_alt.

| Block | Seed | Order |
| ---: | ---: | --- |
| 1 | 5201 | event_only, hybrid, reconcile |
| 2 | 5202 | hybrid, reconcile, event_only |
| 3 | 5203 | reconcile, event_only, hybrid |
| 4 | 5204 | event_only, reconcile, hybrid |
| 5 | 5205 | hybrid, event_only, reconcile |
| 6 | 5206 | reconcile, hybrid, event_only |

Labels: `rq3qoe_{cell}_{arm}_{block}`, e.g. `rq3qoe_loss_all_hybrid_2`.
Analyze with `readiness_robustness.py qoe-campaign` after block 6 (direction
checks at blocks 3 and 5, 2-of-3 and 3-of-5 on each axis's contrast). Overall
pass (slow-share amendment 2026-09-08): `(H-Q1 ∧ H-Q2) ∨ (H-Q1b ∧ H-Q2b)` ∧
both boundedness ∧ H-Q3 ∧ H-Q4. A failed pre-registered direction or
boundedness component is reported, never chased.
