# RQ3 Soundness — Run Matrix

Parent plan: [`experiment_plan.md`](experiment_plan.md) · Host: `cloud-vm-rq3`
· Frozen base: current HEAD at tag time; tag `rq3snd-preflight-<date>`
recorded in `rq3snd_protected_surface.json`. Full reset between runs.

Launch (wrapper): `bash source/scripts/testing/rq3snd_p1_01_launch_run.sh <arm> <fault> <label> <seed>`
The launcher asserts the frozen Family-4 phase profile (600 s plateau /
rate 2.0 / sp 1.0), known arm/fault, unique label, quota 0.12; composes the
arm env + fault env + app knobs; sets `RANDOM_SEED=<seed>`; writes
`rq3snd_fault_attestation.txt`; delegates to `run_experiment.sh
--phases-config <frozen phases.json> --run-label <label>` with the Family-4
invocation parameter set taken from `rq3tim_p1_01_launch_run.sh` at both the
make-variable and script-flag layers (the P0 full-invocation diff against the
Family-4 launcher is the binding check — any deviation = STOP) and
`RANDOM_SEED=<seed>`. No `--fault-plan` (faults are env-injected).
Fault vocabulary: `none`, `premature2|5|10`, `semantic`, `loss_all`.
Arms: `event_only`, `hybrid`, `reconcile`, `wake_verify` (optional).

## Label convention

- E (blocks 1–3): `rq3snd_<fault>_<arm>_<block>`, e.g.
  `rq3snd_premature10_event_only_1`. Globally unique; launcher refuses
  duplicates.
- Preflight: ordinals 90–93 — `rq3snd_premature10_event_only_90`,
  `rq3snd_premature10_reconcile_91`, `rq3snd_semantic_event_only_92`,
  `rq3snd_semantic_reconcile_93` (optional). Never collide with blocks 1–3.

## Seeds

| Use | Seeds | Note |
| --- | --- | --- |
| E core | 6301–6303 | n=3 per cell; ≥2/3 rule |
| Reserved | 6304–6306 | plan amendment only (no tie-break extension in this campaign) |
| Preflight | 6351–6354 | distinct from E seeds |

6xxx verified unused in v3 docs at plan time (no prior campaign uses this
block). `RANDOM_SEED` fixed per run.

## Cells × arms (runs per cell)

| Fault cell | `event_only` | `hybrid` | `reconcile` | `wake_verify` | Core | Optional |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `none` | 3 | 3 | 3 | 3 | 9 | 3 |
| `premature2` | 3 | 3 | 3 | – | 9 | 0 |
| `premature5` | 3 | 3 | 3 | – | 9 | 0 |
| `premature10` | 3 | 3 | 3 | 3 | 9 | 3 |
| `semantic` | 3 | 3 | 3 | 3 | 6 | 6 |
| `loss_all` | 3 | – | 3 | – | 3 | 3 |
| **Total** | **15 (+3)** | **12 (+3)** | **18** | **(9)** | **45** | **15** |

Core = 45 runs (3 seed-blocks × 15). Optional ≤15 appended after core,
wall-time permitting (includes the optional `wake_verify` arm and the F1
push anchor). Hard cap 60 runs.

## Counterbalancing — E blocks (arm order rotates per seed; arm-major within block)

| Block | Seed | Arm order | Cells per arm (ascending) | Runs |
| ---: | ---: | --- | --- | ---: |
| 1 | 6301 | event_only → hybrid → reconcile | event_only: none, p2, p5, p10, semantic · hybrid: none, p2, p5, p10 · reconcile: none, p2, p5, p10, semantic, loss_all | 15 |
| 2 | 6302 | hybrid → reconcile → event_only | same cell lists per arm | 15 |
| 3 | 6303 | reconcile → event_only → hybrid | same cell lists per arm | 15 |

Optional runs (append after block 3, per seed-block): `semantic_hybrid`
(descriptive only — hybrid's claim-(a) component is F2), `loss_all_event_only`
(F1 push anchor, descriptive), `wake_verify`: none, p10, semantic → 5 per
block.

## Example commands

```
bash source/scripts/testing/rq3snd_p1_01_launch_run.sh event_only premature10 rq3snd_premature10_event_only_1 6301
bash source/scripts/testing/rq3snd_p1_01_launch_run.sh reconcile  semantic    rq3snd_semantic_reconcile_1    6301
bash source/scripts/testing/rq3snd_p1_01_launch_run.sh event_only loss_all    rq3snd_loss_all_event_only_3   6303   # optional
bash source/scripts/testing/rq3snd_p1_01_launch_run.sh wake_verify premature10 rq3snd_premature10_wake_verify_1 6301  # optional
```

Preflight (stage P1, seeds 6351–6354):

```
bash source/scripts/testing/rq3snd_p1_01_launch_run.sh event_only premature10 rq3snd_premature10_event_only_90 6351
bash source/scripts/testing/rq3snd_p1_01_launch_run.sh reconcile  premature10 rq3snd_premature10_reconcile_91 6352
bash source/scripts/testing/rq3snd_p1_01_launch_run.sh event_only semantic    rq3snd_semantic_event_only_92   6353
bash source/scripts/testing/rq3snd_p1_01_launch_run.sh reconcile  semantic    rq3snd_semantic_reconcile_93   6354  # optional R3b
```

## Wall time (~40 min/run)

| Stage | Runs | Estimate |
| --- | ---: | ---: |
| P1 preflight | 3 (+1) | ≈ 2.0–2.7 h |
| E core | 45 | ≈ 30 h |
| Optional | ≤15 | ≈ ≤10 h |
| E cap (core+optional) | ≤60 | ≈ ≤40 h |
| P1 rerun allowance | ≤4 | ≈ ≤2.7 h |
| **Campaign total (P1 + E cap + reruns)** | **≤68** | **≈ ≤46 h** |

## Analysis

- Damage tables: `readiness_robustness.py soundness-damage --run-dir <folders> --out analysis/soundness_damage.json`
- Crossover + verdicts: `readiness_robustness.py soundness-crossover --damage-json analysis/soundness_damage.json --out analysis/soundness_crossover.json`
- Preflight lock: `readiness_robustness.py soundness-preflight --run-dir <90–93 folders> --out rq3snd_preflight_results.json --lock-out rq3snd_preflight_lock.json` (exit 0 lock · 2 diagnose · 3 stop)

## Order amendment — 2026-10-03 (user-approved)

All optional `wake_verify` runs execute **at the campaign tail** (after every
other run) instead of at block tails, and only if the **pre-tail gate scan**
passes (validity + floors + none-health + mechanism attestation over every
preceding run; otherwise the block is skipped and recorded in the ledger as
`pre-tail scan: SKIP …`). Relative order of every other run is unchanged
(blocks 1–3 core, with `semantic_hybrid` / `loss_all_event_only` descriptive
runs kept at their block-tail positions). Executed by
`/tmp/rq3snd_e_sequence2.sh` (sequencer part 2); the part-1 sequencer was
stopped mid-stage as a coordinator-only swap — the in-flight run
(`rq3snd_premature2_reconcile_1`) was never interrupted (orphan-adopted by
part 2). Ledger evidence: `ORDER-AMENDMENT` line in
`/tmp/rq3snd_e_ledger.txt`; docs: `preflight_log.md` row 3.1.

## Incident amendment — 2026-10-03 (run-17 STOP)

`loss_all` × `event_only` runs trip the inherited RQ3-v2 **min-admissions
gate** in `run_experiment.sh` (requires ≥1 admitted backend per LAN)
although **0 admissions is the expected F1 mechanism** (Family-4
certificate: 0 admitted / 33 abandoned at this cell). Run 17
(`rq3snd_loss_all_event_only_1`) is **accepted** on the campaign gate
(`valid=True`, floors PASS, 32 bind-verified spawns, 0 admitted / 32
abandoned) — no rerun; a rerun would reproduce the artifact and the
outcome is in-spec. The part-3 sequencer
(`/tmp/rq3snd_e_sequence3.sh`) accepts this artifact for loss_all cells
only when the log shows the min-admissions gate and the campaign gate
returns OK; otherwise the chain stops. Runs 37 and 57 are the remaining
affected cells. Docs: `preflight_log.md` row 4.1; ledger `RESUME` line.
