# RQ2 Extension — Run Matrix

Part of [`experiment_plan.md`](experiment_plan.md). Per-run configuration and
provenance for the RQ2 extension campaign (Parts A/B; Part P provenance).

> **Status: ✅ plan APPROVED (2026-09-26) — steps 1–8 executed; campaign
> COMPLETE — 30/30 runs (Stage A1 checkpoint 6/6; Stage 2 verified — hard
> gates clean; two instrumentation items open, analysis-side); **Part C
> (`rq2pc`) CLOSED 2026-09-28 — probes + bounded diagnostic pair executed;
> campaign NOT executed ("stop + record", user decision); closure + hash
> records §6; no `-final-` tag**; ⚠ local `git bundle` mirror
> refresh pending.** Step 1 (v3-final) is executed
> on the VM (`rq2-v3-final` @ `5e3d29a`, tag `rq2-v3-final-20260926`); step 2
> (extension draft) is committed on branch `rq2-extension` and tagged
> `rq2-extension-draft-20260926` after the full VM test gate (unit check,
> harness dry-parse, analyzer regression smokes); step 3 verified the
> tag-to-tag diff is **restricted to the 16 enumerated additive files**
> (arm envs + base phase files byte-identical — verification block below);
> step 4 filled the **FREEZE-1** pre-probe hashes (launcher provisional);
> steps 6–7 later finalized the launch state and recorded **FREEZE-2** (§1;
> per `experiment_plan.md` §3.2/§9). The "reference (local, 2026-09-26)" column
> records local hashes taken at plan time — **the `policy_gate.py` and base
> phase-file values reflect the stale local mirror** (see the VM-reference
> note after the table). Probes (Stage 0) and Stage A1 (`nn_cb` × 6) are
> executed — the probe record lives in [results.md](results.md) (probes are
> not evidence); campaign rows accrue there.

---

## 1. Provenance block (fill at freeze)

**Rule:** extension runs are **"v3 code + additive-only changes"** — the
tag(s) below must differ **only** by the additive set enumerated in
`experiment_plan.md` §3.1 (diff review is a freeze gate): `rq2-v3-final` →
`rq2-extension-draft` restricted to the enumerated paths;
`rq2-extension-final` differs from the draft only by the probe-finalized
values of enumerated paths (varying phases files; launcher caps on a Beta
switch).

| Item | Branch / tag | md5 at freeze | Reference (local, 2026-09-26) |
| --- | --- | --- | --- |
| v3-final state (v3 docs amendments + `EDGE_MEMORY=512m` env edits + amended launcher) — **EXECUTED 2026-09-26** | branch `rq2-v3-final` (from tag `rq2-v3-campaign-20260808`, on the VM) · tag **`rq2-v3-final-20260926`** — commit `5e3d29a` (216 files changed; `git describe` verified; clean tree) | n/a (state row — the tag is the record) | — |
| Extension state (additive set only; final state = campaign launch state) | branch `rq2-extension` · draft tag **`rq2-extension-draft-20260926`** (step 2) → final tag **`rq2-extension-final-20260927`** @ `34cd78e` (step 6 — **EXECUTED 2026-09-27**) | — | — |
| `tools/run_rq2_campaign.py` (launcher; `tools/` gitignored — **force-added** via `git add -f`; no `.gitignore` edit — plan §3.2; **re-hashed at FREEZE-2** — probe finalization can change shift-cell caps on the Beta path; the FREEZE-1 md5 is provisional and superseded, both kept) | as above | `036fb333fd0abaafd533c0bcd788ea87` (**FREEZE-1**, 2026-09-26, pre-probe — **provisional**) md5 + `db91c5665e0c7b268a45ed929c107097` (**FREEZE-2**, 2026-09-27, post-probe — launch-state) md5 — both retained; **the FREEZE-2 value is the launch-state value** | `D45CDB2939D7A010C548FB410D9261B5` |
| `rq2_env/rq2_none.env` (NEW — created 2026-09-26; canonical launch location; **no archive mirror** — it exists ONLY in `rq2_env/`; the v3 `env/` mirror is untracked/informational) | `rq2-extension` branch | `c23967dec2a9bbe6dad8e6b4ee9d9f4e` (**FREEZE-1**, 2026-09-26) | — |
| `rq2_env/rq2_compute_first.env` (must be byte-identical across tags) | as above | `33ce4df766e8a6e893011486a443fcab` (**FREEZE-1**; byte-identical across tags ✓) | `33CE4DF766E8A6E893011486A443FCAB` |
| `rq2_env/rq2_storage_first.env` (byte-identical across tags) | as above | `c41bd38ef309cc1dd6822757c89dbb52` (**FREEZE-1**; byte-identical across tags ✓) | `C41BD38EF309CC1DD6822757C89DBB52` |
| `rq2_env/rq2_bottleneck_aware.env` (byte-identical across tags) | as above | `ac54f77a4b12aebf6a5157ddc123e6f0` (**FREEZE-1**; byte-identical across tags ✓) | `AC54F77A4B12AEBF6A5157DDC123E6F0` |
| `source/sdn_controller/policy_gate.py` (v3 branches untouched; `fixed_none` additive) | as above | `a078a95d75b655d1a6fbe1d70556c96b` (**FREEZE-1**, 2026-09-26) | `7A32E55F884A468A8628043386985FB9` |
| `source/scripts/testing/phases_override/phases_rq2_compute_bound.json` (reference) | as above | `d40f5f592375360c76a1d55f4c168200` (**FREEZE-1**, 2026-09-26; = the AS-RUN snapshot value) | `512A19F73CC7E79C61EA7908D1FCE8D3` |
| `source/scripts/testing/phases_override/phases_rq2_data_bound.json` (reference) | as above | `06a880c5dbfceb78c4ae5639870b5cd5` (**FREEZE-1**, 2026-09-26; = the AS-RUN snapshot value) | `50D3815C7178C6C23A9C3E3631F6547B` |
| `phases_rq2_varying_cbdb.json` / `phases_rq2_varying_dbcb.json` (NEW — created 2026-09-26) | `rq2-extension` branch (probe-finalized — rate sweep / `G` — before tag `rq2-extension-final-20260927`) | cbdb `a7db82c849e76647c412422ea2f70ce9` / dbcb `46fd82af397e4646b60bbd6080002836` (**FREEZE-2**, 2026-09-27, tied to `rq2-extension-final-20260927`) | — |
| `extension_order_v1a.csv` / `extension_order_v1b.csv` (NEW — created 2026-09-26; CSV-1 Stage A1; CSV-2 remaining 24; this folder; v3 convention) | `rq2-extension` branch | `96d7f35a820618ad2a986a0f1817f7a3` / `22922274ddac3d32ac5d12b6ea388de3` (**FREEZE-2**, 2026-09-27 — **unchanged from FREEZE-1** ✓; tied to `rq2-extension-final-20260927`) | — |
| Implementation-recorded lists — analysis-extension file list (plan §3.1 item 5) + G2 producing-script path (VM-side tooling, plan §4.5) | `rq2-extension` branch | n/a (list) | ✅ recorded 2026-09-26 — see the block below |

**VM reference md5s (working copy of record, 2026-09-26):** `policy_gate.py`
= `2AD6302AC889BDBE187786D9778CA384` and the base phase files =
`D40F5F59…` / `06A880C5…` — these **differ from the local-mirror values in
the table above** (the local repo predates the VM's `84cbd8b` snapshot
commit; the three arm envs match: `33CE4DF7…` / `C41BD38E…` / `AC54F77A…`).
The local mirror is refreshed **from** the VM (`git bundle`; plan §8 item 6).

**Phase-drift reconciliation — RESULT (2026-09-26): NO DRIFT.**
The VM's base `phases_rq2_compute_bound.json` / `phases_rq2_data_bound.json`
are byte-identical to **all examined AS-RUN snapshots** (cb = `D40F5F59…` in
`cf_cb_1` / `ba_cb_1` / `sf_cb_1`-rerun; db = `06A880C5…` in `cf_db_1` /
`ba_db_5` / `cf_db_6`). The earlier `512A19F7…` / `50D3815C…` mismatch was
the **stale local mirror only**. ⇒ The `nn` cells reuse the base cb/db files;
**no extension-specific phase copies are built** (plan §5.2 branch not taken).

**Implementation-recorded lists (2026-09-26; completed at step 2):**

- **Analysis-extension files:**
  `source/scripts/testing/analysis/rq2/rq2_bottleneck_aware_campaign.py`
  (RUN_RE extended for `nn` + `shcbdb`/`shdbcb`; per-segment dataset —
  `segment_idx` / `segment_phase` + per-segment recovery columns; compute leg
  anchored at the first compute add (v3 tool mirror), storage leg anchored at
  the first reserve activation (decision-log `reserve_activate`) with the
  `node_ready` + 120 s POST start; `nn` N/A flags + M1 zero-action evidence
  (`scaleups_non_none` / `reserve_activates` / `zero_action_ok`;
  `adds_compute` / `adds_storage` kept informational — elasticity node adds
  include baseline bring-up containers); `nn` all-none reference in the
  selected-action graph; new per-phase recovery graph `shift_recovery.png`);
  `docs/research_questions/v2/rq2/rq2_bottleneck_validation.py` (per-segment
  `--episode-phase NAME`);
  `docs/research_questions/v2/rq2/rq2_decision_analysis.py`,
  `docs/research_questions/v2/rq2/rq2_relief_analysis.py`,
  `docs/research_questions/v2/rq2/rq2_node_minutes.py` (VM-side per-run
  tools: `fixed_none` added to the RQ2 arm guard — one line each, no other
  change; the action-centric rollups report an empty action set for `nn`,
  which is the expected state — zero-action evidence comes from the analyzer
  dataset + G2);
  `source/sdn_controller/rq2v2_p6_01_policy_gate_fixed_none_test.py` (NEW
  unit check).
- **Run-summary tooling:** **NO code change** — `metrics_stats.py
  --by-phase` (both `client_requests.csv` and `resource_stats.csv` modes)
  already yields per-phase sections, and shift episodes carry unique phase
  names; the per-phase pre/post + carryover fields come from the analyzer
  dataset + the metrics-run-summary skill authoring (plan §7 item 3 is
  satisfied by tooling + dataset, recorded here).
- **G2 producing script:** `docs/research_questions/v2/rq2/rq2_bottleneck_validation.py`
  (per-segment mode added).
- **Launcher:** `tools/run_rq2_campaign.py` — `CELLS`-only change; the
  order-CSV path is already generic (no schema change).

**Extension-draft verification (step 3, 2026-09-26) — restricted-diff adjudge:**

- Tag anchors (annotated): `rq2-v3-final-20260926` → commit `5e3d29a` (tag
  object `4a905bfc…`); `rq2-extension-draft-20260926` → commit `6903e21`
  (tag object `3bae3959…`; `git describe --tags` at the draft = the draft
  tag; tree clean).
- `git diff --name-status rq2-v3-final-20260926..rq2-extension-draft-20260926`
  = **exactly the 16 enumerated additive files** — 5 docs-package files (A),
  analyzer + `policy_gate.py` + launcher + 4 per-run tools (M),
  `rq2_none.env` + 2 varying phases files + unit check (A). **No deletions
  anywhere**; 16 files changed, **+2273/−64** (all inside the enumerated
  paths — the deletions are replaced lines within those files).
- **Cross-tag invariants (0 diff lines):** the three arm envs
  (`rq2_compute_first.env` / `rq2_storage_first.env` /
  `rq2_bottleneck_aware.env`) and the base phase files
  (`phases_rq2_compute_bound.json` / `phases_rq2_data_bound.json`).
  The `policy_gate.py` diff touches ONLY the new `fixed_none` mode +
  docstrings/comments — the `dual`, `cf`, `sf`, `ba`, and strict-commit
  branches are unchanged (diff reviewed).
- **Draft-state md5s** (the verification object; FREEZE-1 re-hashes these and
  must match — except `run_matrix.md` / `results.md`, which receive THIS
  record and are re-hashed at FREEZE-1 in their post-record state):

  | # | File | md5 (draft tag) |
  | --- | --- | --- |
  | 1 | `source/sdn_controller/policy_gate.py` | `a078a95d75b655d1a6fbe1d70556c96b` |
  | 2 | `source/sdn_controller/rq2v2_p6_01_policy_gate_fixed_none_test.py` | `cc0be5d4557472e9c4e4d9209d33a2fd` |
  | 3 | `rq2_env/rq2_none.env` | `c23967dec2a9bbe6dad8e6b4ee9d9f4e` |
  | 4 | `source/scripts/testing/phases_override/phases_rq2_varying_cbdb.json` | `a42aab43bf56cee00313624a8a88c911` |
  | 5 | `source/scripts/testing/phases_override/phases_rq2_varying_dbcb.json` | `3a06c924793fa91d8bb222dd587d63c0` |
  | 6 | `tools/run_rq2_campaign.py` | `036fb333fd0abaafd533c0bcd788ea87` |
  | 7 | `source/scripts/testing/analysis/rq2/rq2_bottleneck_aware_campaign.py` | `9ab745744d59667d9ac062cc9f619a9b` |
  | 8 | `docs/research_questions/v2/rq2/rq2_bottleneck_validation.py` | `bd1e9412d4aa966d7ecb09994c118059` |
  | 9 | `docs/research_questions/v2/rq2/rq2_decision_analysis.py` | `0c5e2be8807f8c038b59c2e2fc25fc7e` |
  | 10 | `docs/research_questions/v2/rq2/rq2_relief_analysis.py` | `2707e963d48aebff3816f39794e83b8e` |
  | 11 | `docs/research_questions/v2/rq2/rq2_node_minutes.py` | `a918cec78ec5648f91fc10ea407e7843` |
  | 12 | `docs/operation/testing/experiment/rq2_extension/experiment_plan.md` | `7da1ee0faff7570981cef173e0d954e5` |
  | 13 | `docs/operation/testing/experiment/rq2_extension/run_matrix.md` | `89e7d44f0231efe169913cc697276bac` — pre-record; re-hashed at FREEZE-1 |
  | 14 | `docs/operation/testing/experiment/rq2_extension/results.md` | `1797a8b8dabd3d6143aead551a0a1fe7` — pre-record; re-hashed at FREEZE-1 |
  | 15 | `docs/operation/testing/experiment/rq2_extension/extension_order_v1a.csv` | `96d7f35a820618ad2a986a0f1817f7a3` |
  | 16 | `docs/operation/testing/experiment/rq2_extension/extension_order_v1b.csv` | `22922274ddac3d32ac5d12b6ea388de3` |

**Freeze points (fixed — steps 4 and 7 of the canonical sequence):**

- **FREEZE-1 (pre-probe):** code / env / launcher / **plan** hashes recorded
  (the rows above except those marked FREEZE-2; the plan-package hash);
  order CSVs **as applicable**. The launcher md5 recorded here is
  **provisional** — probe finalization can change the shift-cell caps (Beta
  path), in which case FREEZE-2 supersedes it (both kept).
- **FREEZE-2 (post-probe, before campaign launch):** the varying phases
  files + **shift-cell caps** (the P1 pass point — or Beta, which changes
  caps **and** both episodes) + order CSVs hashed and recorded — **tied to
  `rq2-extension-final-<date>`** (plan §3.2 step 7). **FREEZE-2 re-hashes
  EVERY artifact that probe finalization can modify** — the varying phases
  files, the launcher (shift-cell caps change on the Beta path), and the
  order CSVs; the launcher's md5 recorded at FREEZE-1 is **provisional and
  superseded** by the FREEZE-2 value (**both kept**).
- Both freeze points precede the campaign launch: **nothing is launched
  before FREEZE-2** (Stage-0 probes excepted — they inform FREEZE-2).

**FREEZE-1 record (2026-09-26, pre-probe) — executed.** State: branch
`rq2-extension` @ `654ab1b` (records commit; the code state = draft tag
`6903e21`), tree clean; nothing launched. All 16 additive-set hashes
re-verified against the step-3 table — **stable** (the only drift is
`run_matrix.md` / `results.md`, now the step-3 record versions
`d32f6c60…` / `c0fd2279…` — by design). Filled above: launcher
(**provisional**), `rq2_none.env`, the three arm envs (byte-identical to
v3-final ✓), `policy_gate.py`, base cb/db phase files (= the AS-RUN
snapshot values, phase-drift §1). Plan package at FREEZE-1:
`experiment_plan.md` = `7da1ee0faff7570981cef173e0d954e5`,
`extension_order_v1a.csv` = `96d7f35a820618ad2a986a0f1817f7a3`,
`extension_order_v1b.csv` = `22922274ddac3d32ac5d12b6ea388de3`;
`run_matrix.md` / `results.md` are **records files** that keep accruing by
design — the FREEZE-1 state of the package is the commit carrying this
record (audit via `git log`), and FREEZE-2 re-hashes the full package for
the launch state. FREEZE-2 slots (varying phases files, launcher
launch value, order CSVs) remain `<fill>`.

**FREEZE-2 record (2026-09-27, post-probe) — executed.** State: tag
**`rq2-extension-final-20260927`** @ commit **`34cd78e`** (branch
`rq2-extension`; tree clean; `git describe` = the tag). Launch-state hashes
(working tree of record):

- **Launcher** `tools/run_rq2_campaign.py` = `db91c5665e0c7b268a45ed929c107097`
  (Beta finalization: the six shift cells `cf/sf/ba × shcbdb/shdbcb` moved
  to `EDGE_CPUS=0.6` / storage 0.15; `nn_*` + all Part A cells untouched —
  `EDGE_CPUS=1.20` remains for `cf/sf/ba_db` + `nn_db`, `0.15` for the cb
  cells; supersedes the FREEZE-1 provisional value above).
- **Varying phases** (rate-15 final): `phases_rq2_varying_cbdb.json` =
  `a7db82c849e76647c412422ea2f70ce9`; `phases_rq2_varying_dbcb.json` =
  `46fd82af397e4646b60bbd6080002836`.
- **Order CSVs** (unchanged from FREEZE-1 ✓): `extension_order_v1a.csv` =
  `96d7f35a820618ad2a986a0f1817f7a3`; `extension_order_v1b.csv` =
  `22922274ddac3d32ac5d12b6ea388de3`.
- **Unchanged since FREEZE-1** (re-verified): `policy_gate.py` =
  `a078a95d75b655d1a6fbe1d70556c96b`; base cb/db phases =
  `d40f5f592375360c76a1d55f4c168200` / `06a880c5dbfceb78c4ae5639870b5cd5`;
  `rq2_none.env` = `c23967dec2a9bbe6dad8e6b4ee9d9f4e`; arm envs =
  `33ce4df7…` / `c41bd38e…` / `ac54f77a…` (byte-identical to v3-final ✓).
- **Platform stability fixes (probe stage, user-approved 2026-09-27 — part
  of the launch state):** `source/docker/edge_server/source/app.py` =
  `971dc2d52abe9719664f33923ad74a0c` (concurrency gate + memory hardening:
  cap 256, 1 MB stacks); `monitoring_workload_routes.py` =
  `3d4c15387775778434095e025ff24782` (`/service_pressure` TTL cache);
  `build_network_1.sh` = `da479154ffc67b4238267a2d54f29889`;
  `build_network_2.sh` = `6bb549404d61ed9c42c18dec4aee9930`; controller
  override `current_state_integrated.env` =
  `68921d0a4b0f932e48d927b8b8410592`. **Edge image in place:
  `edge_server:latest` = `30a2c88bc1ce`** (built FROM `83cf6d973afe` + COPY
  source; dependency parity verified).
- **Docs at launch state** (records accrue by design; the freeze-state
  package = commit `34cd78e` carrying this record): plan =
  `95c704f79acd453dd07c302ec2ca0f1c`, run_matrix =
  `68405afb6f8baf62835f0771295d4da8`, results =
  `b2f080b3b19b1613514c33a42683acea`, lessons =
  `ee785dcb92217ab6db21fc3254c17bb0`.

**Sweep-evidence cleanup (2026-09-27, user-authorized) — executed.** The
four closed P1-sweep folders (`rq2_ext_p1_r6`, `_r9`, `_r12`,
`_contingency`; 636 M + 725 M + 807 M + 1.3 G) were slim-archived and
deleted on the VM: archive
`source/scripts/testing/metrics/_archived/rq2_p1_sweep_20260927.tar.gz`
(584 072 B; **76 files** — run_status, env snapshots, phases, container /
elasticity / lifecycle / decision logs, current-phase, small CSVs; excludes
client-request CSVs, service logs, controller logs, jsonl streams; manifest
alongside), md5 `e96c7e7723d2631a5607c66d5b049a6c`. The probe numbers remain
in [results.md](results.md) (§probe table). All other run folders retained
(campaign archive).

**Phase-drift reconciliation (freeze item):** before freeze, **both the
varying files AND the base cb/db files** (`phases_rq2_compute_bound.json` /
`phases_rq2_data_bound.json`) are diffed against the v3 per-run
`phases_snapshot.json`; the **frozen parameter set = the AS-RUN snapshot
values** (never from possibly-drifted current files). If the current files
drift materially, **extension-specific copies are built from the snapshot
values** (new `phases_override/` files for the extension — **including for
the `nn` cells**, which otherwise reuse the base cb/db files); the v3 base
files are never mutated. The diff summary is recorded here (§1). The
canonical `source/scripts/testing/phases.json` is **untouched** — the varying
files are regime-override files under `phases_override/` (the established v3
mechanism for named configuration regimes; intentional — plan §5.2).

**Pre-launch verification (mandatory):** the campaign launches from the
frozen **`rq2-extension-final-<date>`** state (plan §3.2 step 8) — after
FREEZE-2, all git operations happen **on `cloud-vm-rq2`** (working copy of
record), `git describe --tags` and the md5s above are checked on the VM
**before the first launch**, and the tag + md5s are recorded here; the local
repo is mirrored **from** the VM (`git bundle`, or push if a remote exists;
`experiment_plan.md` §3.2).

**Note:** the local `main` branch has moved on — it is **not** the base for
either branch.

---

## 2. Stage-0 probes (status column; probes are NOT evidence)

Run **before any campaign run** (plan §5.4). Results go to
[results.md](results.md) probe record. Labels are plan-proposed; exact label
recorded at probe time.

| # | Label (proposed) | Shape / config | Acceptance | Status |
| --- | --- | --- | --- | --- |
| P1-1 | `rq2_ext_p1_r6` | cbdb shape · rate 6 · `service_pressure 1.0` · edge 1.20 / storage 0.15 | ALL-of: compute fires (decision log) · edge CPU ≥ 75 % of cap in ≥ 30 % of episode windows · storage quiet, zero storage fires · I1 ≥ 5000/LAN · timeout < 10 % · D-gates pass — **thresholds plan-defined (plan §1.3)** | ❌ FAIL (r6) — (b): 0 % of windows ≥ 75 % of cap |
| P1-2 | `rq2_ext_p1_r9` | cbdb shape · rate 9 (same allocation) | same; sweep in order, stop at first pass | ❌ FAIL (r9) — (b): 0 % ≥ 75 % of cap |
| P1-3 | `rq2_ext_p1_r12` | cbdb shape · rate 12 (same allocation) | same; last Alpha point | ❌ FAIL (r12) — (b) + service wall (p95 ~10 s; timeouts 2.8 %) |
| P1-4 | `rq2_ext_p1_contingency` | **Highest feasible rate** (plan-defined: highest sustained without client-side saturation — client drops < 10 % — recorded in the probe record) · R1 duration **doubled to 1200 s [probe]** (bind-time check) | ONE confirmatory attempt if 6/9/12 all fail; on pass the campaign R1 duration is **1200 s [probe]**; still failing → **Alpha infeasible → Beta switch recorded** | ❌ FAIL (r15, 1200 s) — (b): 0 % ≥ 75 %; **ALPHA INFEASIBLE → Beta** (see results.md) |
| B-P1 | `rq2_ext_b_r15` | cbdb · **edge 0.6** / storage 0.15 · rate 15 [probe] · R1 600 s · arm `rq2_none.env` (**Beta switch, user-approved 2026-09-26**) | same ALL-of list as P1, with (b) normalized to the 0.6 cap | ✅ PASS (pooled (b) 31.1 %; strict 27.1 % / 35.0 % recorded; caps 0.6/0.15 verified via `docker inspect`) |
| B-P1b | `rq2_ext_b_r16` | cbdb · edge 0.6 / storage 0.15 · rate 16 [probe] · R1 600 s · arm `rq2_none.env` (**user-ordered improvement check, 2026-09-27**) | same ALL-of list; strict per-LAN (b) target (lan1 ≥ 30 %) | ❌ no improvement — pooled 27.7 % (< 30 %); lanes flipped; p50 261 ms degraded → conditional fired |
| B-P1r | `rq2_ext_b_r15_rep` | cbdb · edge 0.6 / storage 0.15 · rate 15 [probe] · R1 600 s · arm `rq2_none.env` (**reproducibility check, user-ordered 2026-09-27**) | reproduce B-P1's pooled (b) ≈ 31 % (one-off check) | 🔁 **R1 reproduced** — episode metrics match (timeouts 1.621 % vs 1.574 %; completed 208 750/208 711 vs 208 696/208 897); (b) 29.4 % vs 31.1 % pooled (two-run pooled **30.25 %** — cut inside jitter); fd scan clean |
| B-P2 | `rq2_ext_b_dbcb` | dbcb · edge 0.6 / storage 0.15 · `sf` arm · R2 exact-v3 first (rate 5), R1 rate 15 | storage bind + compute-quiet in R2; **P2** `G` derivation; **P3** boundary observations | ⚠ **completed (2026-09-27) — partial**: R2 ✓ (activation 1×/LAN, 05:24:06/11; storage med 41 %; edge med 75–76 % — “compute-quiet” not met at 0.6); **(P2) replenish 17.6/17.0 s → G = 120 s**; **R1 EMFILE meltdown** (149 k dropped/lane); (P3) partial |
| B-P2r | `rq2_ext_b_dbcb_rep` | dbcb · edge 0.6 / storage 0.15 · `sf` arm · same config (**fd-fix verification rerun, user-approved 2026-09-27**) | verify EMFILE eliminated; clean R1 | ⚠ **fd fix verified (0 EMFILE) but R1 = MEMCG OOM meltdown** — thread explosion (66 596 / 68 041); both edges kernel-killed 07:14:49/50, `RestartCount=1`, no recovery; R2 ✓ (**P2 re-confirmed: replenish 17.1/16.2/17.5 s → G = 120 s**) — **dbcb R1 2/2 failed** |
| B-P2f | `rq2_ext_b_dbcb_fix1` | dbcb · same config (**concurrency-fix verification run**, user-approved 2026-09-27) | verify no spiral/OOM; clean R1 under the bounded gate | ✅ gate **verified live** (engaged once per edge: n1 08:30:00 / n2 08:30:54); fd 0; no OOM / no restarts — **spiral-death eliminated** — ❌ **but R1 still collapsed** (edge CPU pinned ~92 %; ~22 rps/lane; 45 s waits; `time_proc` 44 972 ms; R1 paths 100 % `service_pressure`; zero R1 leases) → **root cause found (O(buffer) summary scan) → B-P2g** |
| B-P2g | `rq2_ext_b_dbcb_fix2` | dbcb · same config (**service_pressure-cache fix verification**, user-approved 2026-09-27; image `83cf6d973afe`) | verify R1-second serves at design capacity (no jam) | ⚠ **jam fix verified on lan2** (~300–325 rps vs ~22; 0.2 ms/req; fd 0; zero errors) — **but n1 OOM-killed during the data episode** (~1024 live threads × 8 MB stacks; total-vm 8.6 GB) and **the restarted edge failed to rejoin** (Mongo ping failed 180 s → lan1 dark 23 min) → run tainted (D2); residual ~10–15 % capacity gap + early-backlog p50 inflation → **fix3 (memory) → B-P2h** |
| B-P2h | `rq2_ext_b_dbcb_fix3` | dbcb · same config (**memory-hardening verification**, user-approved 2026-09-27; image `30a2c88bc1ce`) | verify no OOM/restart; both lanes' R1 ≥ ~330 rps; timeouts < 10 % (pre-stated) | ✅ **no OOM/restart (0/0; gate never blocked; mem ≤ ~86 MiB/512); timeouts 6.0/5.2 % < 10 %; fd 0** — C2 ◐ avg 307/312 rps: **head 10:14–10:18 (~170–210 rps delivered, edge idle — reserve release/reconfig burst 10:13:31–10:14:19), full 354 rps from 10:19** |
| P2 | `rq2_ext_p2_reserve` | reserve replenishment timing — derive `replenish` = (next READY − activation) from v3 db records, **else** 1 dedicated dbcb probe (`sf` arm) | sets **G = max(120 s, replenish_p95 + 60 s)**; scale-down settle > G → increase G (record the measurement) | ✅ **done (via B-P2, 2026-09-27)**: replenish = **17.6 / 17.0 s**; settle 22 s / 42 s; **G = 120 s** (floor holds) |
| P3 | `rq2_ext_p3_boundary` | carried-state verification across the phase boundary (**6 items**; strict-commit verified NOT engaged — excluded) — code read + probe check (≤1 dedicated run if needed) | carried-state table (plan §5.4) verified; unverifiable items recorded as limitations | ◐ code-read recorded; probe check via B-P1/B-P1r + B-P2 (2026-09-27) — B-P2 R1-side observations meltdown-contaminated; boundary-region data usable |

**Probe budget:** P1 ≤ 4 runs · P2 ≤ 1 run · P3 ≤ 1 run · **Beta (user-approved 2026-09-26): ≤ 2 runs + 1 contingency** (beyond the P1 envelope) · **B-P1b + B-P1r (user-ordered 2026-09-27)** · **B-P2 = the 2nd Beta probe run — launched 2026-09-27; serves P2 (`G` derivation) + P3 (boundary)**.

**Platform incident recorded (2026-09-27 forensics, B-P1):** edge servers
logged `OSError: [Errno 24] Too many open files` in an R2-onset burst
(`edge_server_n1` ×1 170, 22:55:20–22:55:44; `edge_server_n2` ×2 918) and
**lan1 stopped serving from ~22:56 to run end** (edge log silence;
`demand_drop` lan1 = 840/840 timeouts; containers stayed running; exit 0;
R1/episode metrics uncontaminated). Smaller non-fatal bursts in
`rq2_ext_p1_contingency` (×12 232, its R2 onset); the other five probe runs
clean. Edge container nofile limit = 1024 (no `--ulimit` at launch; no
artifact records fd counts — the log line is the detector). **Accepted
(user, 2026-09-27):** per-run fd scan added to the D-gate set (plan §5.10
D4) + lessons-log entry; nofile raise + root-cause deferred (comparability
vs v3).

**Update (2026-09-27, post-B-P2 + audit):** incidence now **3 / 8 probe
runs** — contingency R2 (×12 232; 14–22 % timeouts; p50 33–74 s), B-P1 R2
(×4 088; lan1 wedge), **B-P2 R1 (×10 892 / ×11 101; 149 k dropped/lane)**;
the first two were under-observed because batteries were episode-1-scoped —
the battery now covers **both episodes** (D4 + per-phase service health).
**Fixes applied (user-approved, 2026-09-27):** `--ulimit nofile=65536:65536`
added to the edge-container launches; the 2026-09-26 **log-rotation fix**
(`--log-opt` rotation + aggregator `INFO` default + `OVERLOAD_MIN_REQUESTS`)
synced in the same pass — it was **local-only until now**, and the eight
probe runs so far ran with unbounded container logs (single logs ≥146 MB).
New md5s: `f9fc62f3…`→`da479154…` (file 1), `754c7fe6…`→`6bb54940…`
(file 2); applies at container recreation (no image rebuild); folds into
the probe-finalized commit + FREEZE-2. **Verification rerun
`rq2_ext_b_dbcb_rep` launched** (same dbcb/`sf` config) — validates the fix
and completes P3. Root-cause remains a follow-up.

**Post-fix verification (B-P2r, 2026-09-27):** EMFILE eliminated (0 / 0), but
the same overload spiral now terminates in **MEMCG OOM** — kernel
`CONSTRAINT_MEMCG` kills of both edge servers at 07:14:49/50 (thread
explosion: 66 596 / 68 041; total-vm 43 GB; `RestartCount=1` each); no
service returned (demand_drop 0/839 + 0/842). **dbcb R1 = 2/2 failed
attempts** → the overload-spiral root cause (edge concurrency model under
sustained/jam load) is re-opened and **gates the campaign** (user call).

**Root-cause fix applied (user-approved, 2026-09-27):**
`source/docker/edge_server/source/app.py` gains a bounded-concurrency gate
(`_apply_request_concurrency_bound`; `EDGE_MAX_CONCURRENCY` default 1024 —
excess connections wait in the kernel accept backlog instead of spawning
threads); md5 `f9f7ad39…` → `3192e12d…`; edge image rebuilt `aeaa8b6c7cd3`
→ `32642cda5693` (only the `COPY source` layer changed — pip layer
cache-reused, dependency parity by construction) + in-image smoke ✓;
startup log confirms the gate on both edges. **Verification run
`rq2_ext_b_dbcb_fix1` launched** (same dbcb/`sf` config); folds into the
probe-finalized commit + FREEZE-2.

**fix1 verification outcome (2026-09-27):** the bounded gate verified live
(engaged once per edge — n1 08:30:00 / n2 08:30:54), fd scan 0 / 0, no OOM,
no restarts: **the spiral-death is eliminated** — but the dbcb R1 **still
collapsed**, now with a clean signature: edge CPU pinned ~92 %, ~22 rps/lane
served, 45 s client waits, `time_proc` 44 972 ms per window (healthy
≈ 0.14 ms), R1 request paths **100 % `service_pressure`**, zero storage
leases in R1. **True root cause (diagnosed):** the `/service_pressure`
summary is **O(retained events) and computed per request**
(`events_since_with_truncation` scan + per-event snapshots +
`compute_service_pressure` stats) — in dbcb order the preceding R2 content
episode fills the 72 000-event local buffer, so each rate-15 R1 query scans
~57 k events (tens of ms of CPU) instead of the designed ~1 ms; at 0.6 cores
the edge serves ≈ 20 rps ≪ demand → accepted-connection jam. This is
**episode-order-dependent** (all 3 dbcb R1s collapsed; cbdb R1s always
healthy — empty buffer at switch).

**Root-cause fix 2 applied (user-approved, 2026-09-27):**
`monitoring_workload_routes.py` gains a **short-TTL single-flight cache** for
the `/service_pressure` summary (`SERVICE_PRESSURE_CACHE_TTL_S`, default 5 s:
fresh hit → cached summary; otherwise exactly one refresher computes while
concurrent requests serve the previous summary; `0` disables); md5
`59a922c9…` → `3d4c1538…`. **Image provenance:** the first cold rebuild
re-ran `apt`/`pip` (the `ubuntu:22.04` base tag had moved) and silently
changed deps (pymongo 4.17.0 → 4.18.2, pyzmq 27.1.0 → 27.2.0) — caught by
layer-age + `pip3 list` comparison and discarded; the deployed image was
reconstructed **`FROM 32642cda5693` + `COPY source`** → **`83cf6d973afe`**
(dependency parity by construction; in-image md5s verified: `app.py`
`3192e12d…` × `monitoring_workload_routes.py` `3d4c1538…`). **Verification
run `rq2_ext_b_dbcb_fix2` launched** (same dbcb/`sf` config).

**fix2 verification outcome (2026-09-27):** the `/service_pressure` cache
fix is **proven on the surviving lane** — lan2's compute episode served
~300–325 rps steady (vs ~22 rps in the fix1 jam), per-request handling
0.2 ms, fd scan 0/0, zero ERROR lines; refresh duty ≈ 1.5 % of the episode
(119 requests > 50 ms ≈ the expected cadence). **But n1 OOM-killed at
09:10:28 during the data episode** — memcg kill with `total-vm 8.6 GB`: the
1024-thread cap was fully occupied (~1024 × 8 MB stacks; the request buffer
is only ~50 MB). The restart in place (09:10:29) then **failed to rejoin**:
`app NOT ready: MongoDB ping failed within 180s` — lan1 stayed dark for the
rest of the run (R2-tail + R1 + drain, 23 min). The run is **D2-tainted →
not evidence**. lan2's R1 ran ~300–325 rps vs the healthy ~348 (timeouts
8.3 % vs ~1.6 % cbdb) with the client p50 inflated by the early R2-drain
backlog and lan1-death contamination — the residual gap is TBD on a clean
rerun.

**Fix 3 applied (user-approved, 2026-09-27 — final planned platform fix
cycle):** `app.py` memory hardening — `EDGE_MAX_CONCURRENCY` default
**1024 → 256** and `EDGE_THREAD_STACK_SIZE_KB` (**default 1024 KB** worker
stacks; `threading.stack_size`); md5 `3192e12d…` → `971dc2d5…`; image
reconstructed **`FROM 83cf6d973afe` + `COPY source`** → `30a2c88bc1ce`
(dependency parity verified; in-image md5s checked). **Verification run
`rq2_ext_b_dbcb_fix3` launched** (same dbcb/`sf` config); **pre-stated pass
criteria: no OOM/restart on either edge; both lanes' R1 ≥ ~330 rps;
timeouts < 10 % (user-set, 2026-09-27)** — time-boxed: no further fix cycles after this one
(scope decision instead).

**fix3 verification outcome (2026-09-27):** **stability solved** — no
OOM/restart (RestartCount 0/0, zero memcg kills), the concurrency gate was
never blocked (256 sufficed), live edge memory ≤ ~86 MiB of 512 (fix2 died
at 473 MiB), fd 0/0, zero ERROR lines; compute-episode timeouts **6.0 % /
5.2 %** (< 10 %); handlers uniformly 0.08–0.36 ms. **The compute episode is
bimodal:** a constrained head (10:14–10:18, ~170–210 rps delivered; edge
CPU 37–55 % — a *delivery-side* constraint, the edge itself idle-fast)
coincides with the **storage reserve release/reconfiguration burst at the
data→compute boundary** (10:13:31–10:14:19: dyn-node removals + re-add,
replicaset reconfig; `node_lifecycle_timings.csv`), then from 10:19 the
lane absorbs at **full healthy rate** (354 rps server-side; zero
drops/timeouts in the final minutes). Episode average 307/312 rps vs
B-P1's 348. **Reading:** the head is a storage-tier *elasticity* signature
of the data-first order (the reserve reaction to the just-ended data
episode landing on the compute head), symmetric across lanes and shared by
all arms — not an edge-platform defect. Steady-state capacity is at the
healthy level.

**P1 launch configuration (fixed).** Arm `rq2_none.env` (passive observation;
also pre-exercises the Part A arm); `phases_rq2_varying_cbdb.json` iterated
**IN PLACE** for the rate sweep (each probe run snapshots phases + env);
launch = **direct `make` chain** on the VM (documented command pattern) —
**NOT** via the launcher (no `CELLS` entries); run folders stored in
`metrics/` following the v3 preflight pattern. The probe-finalized in-place
edits are committed and tagged `rq2-extension-final-<date>` before FREEZE-2
(plan §3.2 steps 6–7).

---

## 3. Campaign cells

Part A caps are identical to the corresponding v3 cells. Part B shift-cell
caps are the **Alpha allocation** ([probe]-finalized; Beta fallback changes
both caps and both episodes — plan §5.3) — **2026-09-26: Alpha FAILED P1 →
BETA switch in progress (edge ≈ 0.6); the caps below are provisional until
Beta finalization.** Shift-cell caps are **frozen at FREEZE-2**, tied to
`rq2-extension-final-<date>` (§1). All statuses are 📋 planned.

| Cell | Arm env (`rq2_env/`) | Phases file | Caps EDGE / STORAGE | Replicates / seeds | Status |
| --- | --- | --- | --- | --- | --- |
| `nn_cb` | `rq2_none.env` (NEW) | `phases_rq2_compute_bound.json` | 0.15 / 0.08 | 6 → `_1.._5` seed 42, `_6` seed 43 | 📋 planned |
| `nn_db` | `rq2_none.env` (NEW) | `phases_rq2_data_bound.json` | 1.20 / 0.15 | 6 → `_1.._5` seed 42, `_6` seed 43 | 📋 planned |
| `cf_shcbdb` | `rq2_compute_first.env` (unchanged) | `phases_rq2_varying_cbdb.json` (NEW) | 1.20 / 0.15 [probe] | Stage 1: 3 (seed 42); extendable 5+1 | 📋 planned |
| `sf_shcbdb` | `rq2_storage_first.env` (unchanged) | `phases_rq2_varying_cbdb.json` | 1.20 / 0.15 [probe] | Stage 1: 3 (seed 42); extendable 5+1 | 📋 planned |
| `ba_shcbdb` | `rq2_bottleneck_aware.env` (unchanged) | `phases_rq2_varying_cbdb.json` | 1.20 / 0.15 [probe] | Stage 1: 3 (seed 42); extendable 5+1 | 📋 planned |
| `cf_shdbcb` | `rq2_compute_first.env` (unchanged) | `phases_rq2_varying_dbcb.json` (NEW) | 1.20 / 0.15 [probe] | Stage 1: 3 (seed 42); extendable 5+1 | 📋 planned |
| `sf_shdbcb` | `rq2_storage_first.env` (unchanged) | `phases_rq2_varying_dbcb.json` | 1.20 / 0.15 [probe] | Stage 1: 3 (seed 42); extendable 5+1 | 📋 planned |
| `ba_shdbcb` | `rq2_bottleneck_aware.env` (unchanged) | `phases_rq2_varying_dbcb.json` | 1.20 / 0.15 [probe] | Stage 1: 3 (seed 42); extendable 5+1 | 📋 planned |

Shared shell env (unchanged from v3): `WAN_RTT_MS=185`, `EDGE_MEMORY=512m`
(**all extension runs are `512m`** — cap-split caveat, plan §4.6),
`EDGE_MONGO_READ_PREFERENCE=secondaryPreferred`,
`VIP_DATA_PER_CONNECTION_FLOWS=1`, `OVERLOAD_CPU_PCT=30`,
`OVERLOAD_PEAK_LATENCY_MS=2000`, pool 12 (`EDGE_MONGO_MAX_POOL_SIZE=12`).

**Env caveat (plan §3.1):** shift-cell arm envs are **byte-identical to the
v3-final committed state** (md5s at FREEZE-1); the known difference vs the
**per-replicate v3 launch records** is the `EDGE_MEMORY=512m` campaign-era
edit — carried as a comparability caveat (plan §4.6 cap-split note).

**Phase-file note (plan §5.2):** the phase files listed are current
references; the freeze-time reconciliation (§1) may substitute
extension-specific copies — including for the `nn` cells — built from the
AS-RUN snapshot values; the v3 base files are never mutated.

**Stage-1 totals:** 30 runs = `nn_cb` 6 + `nn_db` 6 + 6 shift cells × 3.

---

## 4. Extension order-CSV plan (two CSVs; explicit stop)

Two order CSVs (same schema as `counterbalance_order_v2.csv`:
`block,position,cell,run_label,traffic_seed`), created at implementation
time and hashed in §1 at **FREEZE-2** before the first launch. **CSV-1** is
**Stage A1** (`nn_cb` × 6); after it completes the launcher run is
**stopped** and the Stage-A1 checkpoint executed. **CSV-2** (the remaining 24
runs) launches only after the checkpoint passes: blocks 2–4 are the blocked
round-robin of the 7 remaining cells (1 replicate each per block); block 5
closes `nn_db` reps 4–6. Within-block positions use a fixed rotation
(counterbalance intent); composition is fixed as below.

**CSV-1 — `extension_order_v1a.csv` (Stage A1; launcher stopped after it completes):**

```csv
block,position,cell,run_label,traffic_seed
1,1,nn_cb,rq2_nn_cb_1,42
1,2,nn_cb,rq2_nn_cb_2,42
1,3,nn_cb,rq2_nn_cb_3,42
1,4,nn_cb,rq2_nn_cb_4,42
1,5,nn_cb,rq2_nn_cb_5,42
1,6,nn_cb,rq2_nn_cb_6,43
```

**CSV-2 — `extension_order_v1b.csv` (remaining 24 runs; launch only after the checkpoint passes):**

```csv
block,position,cell,run_label,traffic_seed
2,1,nn_db,rq2_nn_db_1,42
2,2,cf_shcbdb,rq2_cf_shcbdb_1,42
2,3,sf_shcbdb,rq2_sf_shcbdb_1,42
2,4,ba_shcbdb,rq2_ba_shcbdb_1,42
2,5,cf_shdbcb,rq2_cf_shdbcb_1,42
2,6,sf_shdbcb,rq2_sf_shdbcb_1,42
2,7,ba_shdbcb,rq2_ba_shdbcb_1,42
3,1,sf_shdbcb,rq2_sf_shdbcb_2,42
3,2,ba_shdbcb,rq2_ba_shdbcb_2,42
3,3,nn_db,rq2_nn_db_2,42
3,4,cf_shcbdb,rq2_cf_shcbdb_2,42
3,5,sf_shcbdb,rq2_sf_shcbdb_2,42
3,6,ba_shcbdb,rq2_ba_shcbdb_2,42
3,7,cf_shdbcb,rq2_cf_shdbcb_2,42
4,1,cf_shcbdb,rq2_cf_shcbdb_3,42
4,2,sf_shcbdb,rq2_sf_shcbdb_3,42
4,3,ba_shcbdb,rq2_ba_shcbdb_3,42
4,4,cf_shdbcb,rq2_cf_shdbcb_3,42
4,5,sf_shdbcb,rq2_sf_shdbcb_3,42
4,6,ba_shdbcb,rq2_ba_shdbcb_3,42
4,7,nn_db,rq2_nn_db_3,42
5,1,nn_db,rq2_nn_db_4,42
5,2,nn_db,rq2_nn_db_5,42
5,3,nn_db,rq2_nn_db_6,43
```

**Explicit stop instruction:** after CSV-1 completes, the launcher run is
**stopped** (no further blocks are read) and the Stage-A1 checkpoint is
executed (analyze + gates, plan §4.7) — **mirrors the `sf_cb` 1-row CSV
practice**. The checkpoint requires **6 passing `nn_cb` runs** (D2 relaunches
happen before it clears). CSV-2 (blocks 2–5) launches **only after** the
checkpoint passes. Stage 2 (shift cells `_4`,`_5` seed 42, `_6` seed 43) is
contingent on the Stage-1 analysis — separate order file, recorded in
[results.md](results.md); the replicate criterion then scales to **≥ 4/6**
(plan §5.9).

**Launch discipline (v3 lessons applied):** per launch, the run folder count
must increase by exactly 1 and no "already completed — skipping" line may
appear for that label; a skipped label triggers the quarantine distinction
procedures (run folders are **never deleted**). Extension labels (`nn_*`,
`*_sh*`) do not collide with v2/v3 label patterns — verify with a folder scan
pre-launch anyway.

---

## 5. Checklist

### Pre-freeze

- [x] Plan package approved (`experiment_plan.md` §9) — approval recorded in [results.md](results.md) (2026-09-26)
- [x] Open items (plan §8) resolved or explicitly accepted — ratifications/deferrals in the [results.md](results.md) timeline; remainder carried as flagged analysis-side notes (2026-09-28)
- [x] Beta fallback criteria acknowledged (switch only via the P1 decision rule) — exercised 2026-09-26 (Alpha INFEASIBLE → Beta switch; recorded)
- [x] Dual-bind scan capture committed as an artifact — **recorded block in [results.md](results.md)** (original 23/10,044; regenerated 2026-09-28: 27/12,207 over 44 v3-marker folders; 0.22 % both times) (plan §8 item 5)

### Execution sequence (canonical — plan §3.2; keep this order)

- [x] **(1) v3-final (VM):** branch from tag `rq2-v3-campaign-20260808`; commit the pending campaign-era edits (v3 docs amendments + `EDGE_MEMORY` env edits + amended launcher); pre-tag `git status --short` reviewed; tag `rq2-v3-final-20260926` (tag message lists the exact file set) — **DONE 2026-09-26**: `rq2-v3-final` @ `5e3d29a` (216 files changed; clean tree; `git describe` = `rq2-v3-final-20260926`)
- [x] **(2) Extension draft (VM):** branch `rq2-extension`; apply **only** the additive set (plan §3.1 — the Parts A/B implementation), including:
  - **DONE 2026-09-26** — branch `rq2-extension` @ tag `rq2-extension-draft-20260926` (this commit). Test gate on the VM: `fixed_none` unit check **PASSED in the `osken` container** (exit 0; no `dual` fallback); `rq2_none.env` diff = header + `SCALEUP_POLICY` only; both varying files **dry-parsed via `traffic_generator.PhaseConfig`** (5 phases, 1680 s, order per file name); analyzer regression smoke — from-dataset on a v3 dataset **copy** (15 PNGs, `shift_recovery` correctly absent) + folder-mode on 2 real v3 runs (79-column dataset; `cf_cb`: anchor True/False, `b2_na` True; `ba_db`: reserve-anchored, storage relief = 0.691); G2 per-segment smoke OK.
  - `fixed_none` unit checks pass (`py_compile` + policy-gate tests; no `dual` fallback)
  - `rq2_none.env` diff vs `rq2_compute_first.env` shows only `SCALEUP_POLICY` + header comment
  - Phase files validated by **traffic-generator/harness dry parse** (the phases file is parsed by the traffic step; exact command recorded at implementation): both varying files load; phase sequence + durations as specified
  - Launcher `CELLS` extended (`nn_cb`, `nn_db`, 6 shift cells); launcher force-added (`git add -f tools/run_rq2_campaign.py`)
  - Analyzer extensions implemented; regression smoke test on a **copy** of the v3 dataset
  - Phase-drift reconciliation done (base cb/db + varying files vs AS-RUN snapshots; extension-specific copies built if needed — plan §5.2; §1 here)
  - commit; tag `rq2-extension-draft-20260926`
- [x] **(3) Verify (VM):** diff `rq2-v3-final-20260926`..`rq2-extension-draft-20260926` restricted to the enumerated additive paths (existing policy branches + three arm envs unchanged); md5s recorded in §1; completed analysis-extension file list + G2 producing-script path recorded in §1 — **DONE 2026-09-26**: diff = **exactly the 16 enumerated additive files** (no deletions; +2273/−64); three arm envs + base phase files **byte-identical across tags**; `policy_gate` diff additive-only (new mode + docstrings); draft-state md5s + tag anchors recorded in the §1 verification block (`run_matrix`/`results` re-hashed at FREEZE-1 after this record)
- [x] **(4) FREEZE-1:** pre-probe hashes recorded — code / env / launcher / plan (order CSVs as applicable); **launcher md5 marked provisional** (probe finalization can change shift-cell caps on the Beta path — FREEZE-2 supersedes; both kept) — **DONE 2026-09-26**: hashes recorded in the §1 FREEZE-1 record (launcher `036fb333…` provisional; `rq2_none.env` `c23967de…`; arm envs byte-identical ✓; `policy_gate` `a078a95d…`; base cb/db `d40f5f59…` / `06a880c5…`; plan-package hashes recorded); **full additive set re-verified stable** vs the step-3 table
- [x] **(5) Stage 0 probes:** — **DONE 2026-09-26/27**: P1 sweep closed (r6/r9/r12 + contingency; Alpha INFEASIBLE → Beta pre-registered switch); B-P1/B-P1b/B-P1r/B-P2/B-P2r + fix1/fix2/fix3 platform-fix verification runs completed; **G = 120 s finalized** (P2 re-confirmed in B-P2r); probe record + incidents written to [results.md](results.md); P3 carried-state observations remain partial (analysis-side).
- [x] **(6) Probe-finalized commit (VM):** — **DONE 2026-09-27**: commit `34cd78e` (11 files) + tag `rq2-extension-final-20260927`; md5s verified (§1).
- [x] **(7) FREEZE-2:** — **DONE 2026-09-27** (recorded in §1 + records commit `ee62a47`; launcher `db91c566…` supersedes the FREEZE-1 provisional; both kept).
- [x] **(8) Launch:** — **DONE 2026-09-27/28**: launched from the frozen state after VM verification; **30/30 runs completed + verified** (Stage A1 checkpoint 6/6; Stage 2 hard gates clean); ⚠ outstanding: local mirror refresh (`git bundle`) + remaining local↔VM doc reconciliations.

### Launch discipline (step 8)

- [x] Stage A1 (CSV-1: `nn_cb` × 6) launched + completed; **launcher stopped**; checkpoint analyzed + gates pass — **DONE 2026-09-27: 6/6; independent audit closed.**
- [x] CSV-2 (blocks 2–5) launched only after the checkpoint passes — **DONE: 24/24 completed + verified (2026-09-28).**
- [x] Memory watch active (exit-137 / container crash ⇒ D2 unified rule) — **zero D2 incidents**; two host-side orchestrator terminal deaths handled by resume (no duplicate launches).
- [x] Shift-cell gates evaluated per run (`§5.10`) — hard gates + I1 clean; **two instrumentation items open** (G2 shift-window anchoring; M1/teardown per-phase consolidation) — analysis-side; closure rows appended to [results.md](results.md).

---

## 6. Part C — confirmatory compute-bound campaign (`rq2pc`)

**Design + probe package: [partc_addendum.md](partc_addendum.md)**
(pre-registration; frozen by FREEZE-3). Summary:

- **Cells** (4 × 6 = 24 runs; single-episode `cb` shape at the Series-C
  allocation, phases `phases_rq2pc_cb.json`, episode rate = probe-locked R*):

| Cell (order-CSV key = orchestrator key) | Arm env | Run labels | Replicates / seeds |
| --- | --- | --- | --- |
| `pc_nn_cb` | `rq2_none.env` | `rq2pc_nn_cb_1..6` | `_1.._5` seed 42; `_6` seed 43 |
| `pc_cf_cb` | `rq2_compute_first.env` | `rq2pc_cf_cb_1..6` | as above |
| `pc_sf_cb` | `rq2_storage_first.env` | `rq2pc_sf_cb_1..6` | as above |
| `pc_ba_cb` | `rq2_bottleneck_aware.env` | `rq2pc_ba_cb_1..6` | as above |

- **Probes** (ascending lock ladder on `nn`; stop at first lock; P-4 = `cf`
  confirmation at R*; probes are NOT evidence — addendum §4):

| Probe | Label | Shape | Acceptance | Status |
| --- | --- | --- | --- | --- |
| P-0 | `rq2pc_p0_nn_015` | nn · rate 1.5 (as-is) | lock gate + validity (addendum §5) | ✅ executed — **NO LOCK** (slow-share 0.999 %; p50 3.3 ms) → ascending |
| P-1 | `rq2pc_p1_nn_030` | nn · rate 3.0 (if needed) | as P-0 | ✅ executed — **LOCK** (99.0 %; p50 3.42 s) ⇒ **R* = 3.0** |
| P-2 | `rq2pc_p2_nn_050` | nn · rate 5.0 (if needed) | as P-0 | ⏭ skipped (lock at P-1) |
| P-3 | `rq2pc_p3_nn_070` | nn · rate 7.0 (if needed) | as P-0 | ⏭ skipped (lock at P-1) |
| P-4 | `rq2pc_p4_cf_<R*>` | cf · rate R* | lock re-check + arm signature (addendum §7) | ✅ executed @ 3.0 — lock re-check PASS; **signature FAIL** (4 adds/LAN, zero collapse) |
| diag | `rq2pc_pd_nn_090` | nn · rate 9.0 (only if no lock) | as P-0 | ⏭ not needed (lock found) — superseded by the approved diag pair |
| diag pair | `rq2pc_pd_nn_025` | nn · rate 2.5 (bounded extension, user-approved) | as P-0 | ✅ executed — **LOCK** (97.0 %; p50 2.79 s) |
| diag pair | `rq2pc_pd_cf_025` | cf · rate 2.5 | as P-0 + signature windows | ✅ executed — **partial signal** (lan2 ×21.4; lan1 ×0.76; lan2 relapse min 6; lan1 mid-episode registry cull) |

- **Order CSV:** `extension_order_partc.csv` (24 rows; blocks 1–6 =
  reps 1–6; within-block rotation; staged **3+3** — Stage 1 = blocks 1–3,
  launcher stopped with the 12th run in flight, checkpoint battery, Stage 2
  = blocks 4–6 resumed at `--start-at rq2pc_ba_cb_4`). Artifacts + hashes
  recorded in §1 at the FREEZE-3 commit.

### Part C checklist (executed at its own freeze/run time)

- [x] Review gate passed on [partc_addendum.md](partc_addendum.md) + artifacts — **passed 2026-09-28** (4 review rounds; all 🔴/🟡 issues fixed)
- [x] FREEZE-3 draft commit (closure sweep + artifacts; hash record; restricted diff) — **`50b694c`** (9 files; no tag)
- [x] Pre-run sync/verification — **passed 2026-09-28** (md5s byte-identical local↔VM; phases copy VM-side `cp` = `d40f5f59…`; clean-VM 0/0/0; 77 GB free)
- [x] Probes P-0..P-4 executed; probe record appended to [results.md](results.md) — **DONE 2026-09-28** (P-2/P-3 skipped after the 3.0 lock; + the user-approved bounded diag pair @ 2.5; 5 probe runs total ≤ 7 cap)
- [x] ~~Probe-finalized commit + tag `rq2-extension-partc-final-<date>`~~ — **superseded by the closure decision:** records-only commit, **no tag** (closure record below)
- [x] ~~Campaign Stage 1 (12 runs) → checkpoint battery → Stage 2 (12 runs)~~ — **NOT executed (Part C closed 2026-09-28; "stop + record")**
- [x] Records appended ([results.md](results.md) timeline + run_matrix statuses) — **DONE 2026-09-28 (closure record)**

**FREEZE-3 record (2026-09-28):** draft commit **`50b694c`** (9 files; no
tag — the probe-finalized tag `rq2-extension-partc-final-<date>` follows
the ladder). md5s (byte-identical local↔VM): launcher
`34b40b5a0b31382438e58d97c6ca4d69`; probe launcher
`79b20162c9b13b7fccd8c15fabe29204`; `phases_rq2pc_cb.json`
`d40f5f592375360c76a1d55f4c168200` (= the base cb file, byte-identical;
created VM-side via `cp`); order CSV `abd0f15589034e38b8842b9791a595ce`;
addendum `409dcc3abf6d23306578aa474537ddac`. **Restricted diff (mechanical
`git diff --cached --name-only`): exactly the 9 enumerated paths**
(closure sweep + Part C artifacts + analyzer RUN_RE edit). Analyzer
`(?:pc)?` verified functional (rq2 + rq2pc match; probe labels excluded);
launcher / probe launcher / analyzer `py_compile` clean on the VM.

**Part C closure record (2026-09-28) — "stop + record" (user decision).**
The ladder locked at 3.0 and the user-approved bounded diagnostic pair ran
@ 2.5; the focused analysis then found **no reliably treatable window**
across 1.5–3.0. Evidence: at 3.0 the meltdown is **not capacity-bound**
(P-4: 4 adds/LAN fired, zero benefit — PRE→POST p50 ratio 0.86 / 0.81);
at 2.5 the treatment signal is real but unstable — `cf`@2.5 lan2 PRE→POST
**×21.4** (minutes 3–5 at 3–4 ms) yet lan1 **×0.76** (never collapsed),
lan2 **relapsed from minute 6**, and lan1's added nodes were **torn down
mid-episode** by the node-registry liveness cull (`[registry] … not seen
for N s`; 14:22:48–14:24:50). Mechanisms recorded (see [results.md](results.md)
§ Part C): (i) **registry liveness cull** — "seen" does not track served
traffic; systematic across the probe runs (feeds the open M1/teardown
consolidation item); (ii) **near-capacity assignment concentration** — one
node carries the lane's whole per-minute demand; relief appears only when
the assignment splits load. **The 24-run campaign is NOT executed**
(probes are not evidence; Part C contributes no evidence runs). Closure
state: 5 probe runs total (≤ 7 budget; no relaunches); `phases_rq2pc_cb.json`
restored to the frozen state (`d40f5f59…`; transient in-place rate edits
1.5→3.0→2.5 documented in [partc_probe_log.txt](partc_probe_log.txt));
closure commit `7817edf` (records-only on `rq2-extension`) — **no
`-final-` tag** (the planned tag implied campaign readiness). Open platform
questions registered: registry liveness semantics; compute
assignment/concentration at near-capacity rates.

---

## 7. Part D — compute-lock onset bracketing (`rq2pd`)

**Design: [partd_addendum.md](partd_addendum.md)** (pre-registration;
frozen by FREEZE-4). Summary: the Part C ladder jumped 1.5 → 3.0 and never
bracketed the lock onset inside (1.5, 2.5); the 2.5 rung sits deep in the
meltdown (`nn` reference 97 % slow, assignment-gated). Part D screens the
untested shallow-lock band with `nn` rungs **2.0 → 2.25 → 2.4**, tests
`cf` expression at the **lowest locking rung** (R_s), and repeats only for
two pre-registered reasons — a **pass** (2 confirmation runs, ≥ 2/3 rule)
or a **diagnosed-partial failure** (one repeat, assignment starvation
documented) — before the terminal `cf`@2.5 fallback. Probes are NOT
evidence.

| Stage | Runs | Labels | Condition |
| --- | --- | --- | --- |
| bracket | `nn`@2.0 → (`cf`@2.0) → `nn`@2.25 → (`cf`@2.25) → `nn`@2.4 → (`cf`@2.4) | `rq2pd_r1_nn_200` · `rq2pd_r1_cf_200` · `rq2pd_r2_nn_225` · `rq2pd_r2_cf_225` · `rq2pd_r3_nn_240` · `rq2pd_r3_cf_240` | `cf` only at the lowest locking rung; all-no-lock → STOP (boundary ∈ (2.4, 2.5]) |
| repeat | 1 × `cf`@R_s | `rq2pd_rp_cf_<code>` | partial fail with assignment starvation documented |
| confirm | 2 × `cf`@R_s | `rq2pd_c1_cf_<code>` · `rq2pd_c2_cf_<code>` | screening `cf` (or its partial repeat) passed the signature |
| fallback | 1 × `cf`@2.5 | `rq2pd_fb_cf_250` | clean fail at R_s / failed confirmations / failed repeat |

Label codes are rate × 100 (Part D only; Part C used rate × 10; `250`
exists solely as the fallback label).

- **Gates:** Part C §5 validity battery + lock gate; treated-arm signature
  (adds ≥ 1/LAN, zero pre-episode fires, B1 collapse ≥ 2× both LANs,
  recovery slow-share ≤ 5 %, added nodes served) — addendum §5.
- **Budget:** ≤ 8 launches in total, including the single validity relaunch
  (reachable path maximum 7 + 1; expected ≈ 6–8 h wall clock); the launcher
  enforces the global counts via the durable event ledger
  (`source/scripts/testing/metrics/rq2pd_events.jsonl`; missing ledger with
  existing `*_rq2pd_*` folders → abort).
- **Confirmed** → Part D.2 pre-registration of the 4-arm campaign at R_s
  (the campaign is the evidence; Part D runs are selection runs);
  **not confirmed** → STOP + record; the negative is bounded inside
  [onset, 3.0].
- **Launcher:** `tools/run_rq2pd_probes.py` (stages `bracket` / `repeat` /
  `confirm` / `fallback`; `--plan` offline; same launch chain, envs, caps,
  and checker semantics as Part C).

### Part D checklist (executed at its own freeze/run time)

- [x] Review gate passed on [partd_addendum.md](partd_addendum.md) + artifacts
- [x] FREEZE-4 record (commits `4df5719` / `1aca277` / `959b5c1`; restricted diff + md5s below)
- [x] Pre-run verification (local↔VM md5s; launcher `py_compile` + `--plan`; checker smoke on stored Part C folders — reproduced exactly; clean VM)
- [x] Bracket executed → **R_s = 2.25** (R1 nn@2.0 NO LOCK 0.928 % / 3.4 ms; R2 nn@2.25 **LOCK** 66.098 % / 1.8325 s; R3 skipped)
- [x] Cross-stage gate: `rq2pd_r2_cf_225` classified before downstream stages — **clean fail** (B1 one-LAN partial lan1 0.046 / lan2 0.792; recovery 12.33 % > 5 %; adds 4/LAN; pre-fires 0; no assignment starvation → no repeat)
- [x] Repeat / confirmations / fallback executed per the decision tree — **fallback `rq2pd_fb_cf_250` = terminal diagnostic (Part C pattern reproduced); repeat/confirmations not triggered**
- [x] Global launch/relaunch counts enforced (durable ledger; final: 4/8 launches, 0 relaunches)
- [x] Close: phases restored (`d40f5f59…` verified); records-only commit; **Part D CLOSED — NOT CONFIRMED (STOP + record; no campaign)**
- [x] Cleanup (user instruction): full teardown verified (containers 0, clients 0, netns 0, veths 0, OVS 0); run folders slim-archived (`_archive_rq2pd_slim.tar.gz`, 25 KB) and deleted — recorded exception to the addendum §7.4 no-deletion rule
- [x] CPU-cap prior-art check recorded ([cpu_cap_prior_art_check.md](cpu_cap_prior_art_check.md)) — the quota-reduction path is covered by RQ3 (relief at 0.15; consequence capped ~1.5 % at 0.11–0.13; standing quota 0.12); **no new quota-ladder probing campaign**
- [ ] Outcome recorded in [results.md](results.md); `phases_rq2pc_cb.json` restored; records-only commit

**FREEZE-4 record (2026-10-02):** artifacts commit **`4df5719`** (exactly
the four enumerated paths of addendum §2 staged — restricted diff
verified; no tag). Launcher deploy fix commit **`1aca277`** (FREEZE-4a:
checker shipped via `scp` — the 38 KB base64 echo exceeded the Windows
argv limit, WinError 206; chunked-append fallback kept). md5s
(byte-identical local↔VM): addendum `b61bffc1591f47bceccd007b49a2c5bc`;
launcher `014c690fdf4f5f6b7fdebcfd03bf3774`; `phases_rq2pc_cb.json`
`d40f5f592375360c76a1d55f4c168200` (Part C-frozen state). Pre-run checker
smoke on stored Part C folders reproduced the record exactly: `p1_nn_030`
LOCK 99.001 % / 3.4222 s; `pd_nn_025` LOCK 97.043 % / 2.7884 s;
`pd_cf_025` LOCK 74.315 % / 2.0749 s with `signature_grounded=true`
(missing=[], notes=[]).

**FREEZE-4b record (2026-10-03, instrumentation correction):** during
execution the checker's action counts were corrected to the frozen "action
row" semantics — actions taken = decision-log rows with a
`selected_action` tier (`scaleups_non_none`), not `compute_fired` alert
flags. On `rq2pd_r2_cf_225` the corrected read is **4 adds/LAN, 0
pre-episode fires** (raw flag counts 12/31 retained as informational
fields `decision_compute_fired_rows_episode` /
`decision_scaleup_rows_pre_episode`). Gate definitions unchanged.
Launcher md5 → `077a1e36e927be621207d341a5e578cc` (VM commit `acd43e9`).

---

## Changelog

| Date | Change | Rationale |
| --- | --- | --- |
| 2026-09-26 | Run matrix created with the plan package | Pre-registration |
| 2026-09-26 | Reviewer resolution pass applied — 34 items (C1–C3, W1–W25, O1–O6): two order CSVs, freeze points, force-add launcher, P1 launch config, unified D2 / carried-state rules | Review gate (pre-approval) |
| 2026-09-26 | Second review-resolution pass applied (CR1, W1′–W11′, O1–O9): canonical execution-sequence checklist; FREEZE-1/2 tags and pointers; `rq2_none.env` + varying-phases provenance notes; harness dry-parse wording; 6-item carried-state; P1-4 definition; replicated criterion Stage-2 scaling | Review gate (pre-approval) |
| 2026-09-26 | Final corrections pass: no env archive mirror (`rq2_none.env` only in `rq2_env/`; v3 mirror untracked/informational); FREEZE-2 re-hash rule (launcher md5 provisional at FREEZE-1 — superseded at FREEZE-2, both kept); package-level `demand_drop` = 420 s decision referenced | Pre-approval corrections |
| 2026-09-26 | Plan approved; step 1 executed (v3-final tag on the VM); step-2 additive set authored + locally validated; phase-drift reconciliation RESULT recorded (**NO DRIFT** — `nn` cells reuse the base files); VM-reference md5s recorded (local-mirror staleness caveat); implementation-recorded lists completed (analysis-extension file list, run-summary flow decision, G2 path) | Execution record |
| 2026-09-28 | Part C (`rq2pc`) addendum + artifacts authored — §6 added (cells, probe ladder, order plan, checklist) | Part C pre-registration (user-specified) |
| 2026-09-28 | Part C probes executed (ladder P-0/P-1/P-4 + bounded diag pair @ 2.5); **Part C CLOSED — campaign NOT executed** ("stop + record"); closure record + mechanisms in §6 (registry liveness cull; assignment concentration; no treatable window 1.5–3.0); `phases_rq2pc_cb.json` restored to the frozen state; no `-final-` tag | Part C execution + user decision |
| 2026-10-02 | Part D (`rq2pd`) addendum + artifacts authored — §7 added (bracketing rungs 2.0/2.25/2.4, `cf` at the lowest locking rung, repeat/confirm/fallback rules, budget, FREEZE-4 slots) | Part D pre-registration (user-directed; continues the Part C closure) |
| 2026-10-03 | Part D executed across FREEZE-4/4a/4b (`4df5719`/`1aca277`/`acd43e9`): 4 launches (0 relaunches); R_s = 2.25 (first lock); `cf`@2.25 clean fail → fallback `cf`@2.5 reproduced the Part C pattern; **CLOSED — NOT CONFIRMED**; phases restored; records committed | Part D execution + close |
| 2026-10-02 | Part D review gate executed (4 rounds; verdict **non-blocking**): launcher criticals fixed (analyzer-grounded decision parsing with zero-resolution guard; restore-before-md5 ordering; durable launch ledger with missing-ledger guard) and warnings fixed (missing/notes split, lifecycle lane guards, M2 id-space discriminator, any-tier pre-episode fires, unmatched `--start-at` abort, budget wording); addendum §4/§5/§7 aligned | Review gate (pre-approval) |
