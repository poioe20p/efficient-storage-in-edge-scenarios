# RQ3 Admission Modes — Run Matrix

Parent plan: [`experiment_plan.md`](experiment_plan.md) · Host:
`cloud-vm-rq3` · **≈35 new runs, one at a time, full reset between runs.**

P0 (**platform identity**) gates everything: MATCH → extend (this matrix);
DRIFT → the whole extension is re-run in full instead (all three conditions
+ the matched no-fault partners; plan §6). No run launches before MATCH.
The comparison is per group against that group's **execution tree**
(`~/rq3tim_frozen`, `~/rq3snd_frozen2`, and the campaign tree for the
supporting/C3 runs — the tree the C3 launcher runs from, validated against
the v2 env files and the per-set archived profile hashes; the operator-tree
role is informational and never causes DRIFT). The verdict is **stage-scoped
(plan §6, 2026-10-11 (g))**: read `c1_c2_gate` (timing + soundness — MATCH
permits C1/C2) and `c3_gate` (supporting — a block stops only C3); the
overall verdict is their conjunction and the exit code is 3 unless all stages
MATCH. Run the P0 preflight and the identity gate with `sudo -n` on the VM —
run-folder snapshots are root-owned `-rw-------`, so the unsandboxed
invocation fails with `PermissionError`:

```
sudo -n bash source/scripts/testing/rq3adm_p0_02_preflight.sh \
    --exec-tree ~/rq3tim_frozen --exec-tree ~/rq3snd_frozen2 \
    --support-tree ~/efficient-storage-in-edge-scenarios

sudo -n python3 source/scripts/testing/rq3adm_p0_01_platform_identity.py \
    --timing-tree ~/rq3tim_frozen --soundness-tree ~/rq3snd_frozen2 \
    --support-tree ~/efficient-storage-in-edge-scenarios
```

Without `--exec-tree` (or `RQ3ADM_EXEC_TREES="<tim> <snd>"`) the
execution-tree checks (drop knob, matrix env files, `phases.json`) and the
env-merge proof report an explicit SKIP — never a silent PASS — and the
terminal summary line records the skipped check classes. `--support-tree`
defaults to the tree the preflight runs from (env `RQ3ADM_SUPPORT_TREE`);
the rule-axis fixture is machine-independent (embedded fixtures, with the
recorded v2-set snapshots validated only as an optional extra when present).

## Label convention

New labels follow the cells they extend — never relabelled:

- intact/lost block 7: `rq3tim_{none|loss_all}_{event_only|hybrid|reconcile}_7`
- premature blocks 4–7: `rq3snd_premature10_{event_only|hybrid|reconcile}_{4..7}`
- premature no-fault partners, blocks 4–7:
  `rq3snd_none_{event_only|hybrid|reconcile}_{4..7}`
- supporting: `rq3_camp_{direct|disc}_7`, `rq3_probe_cell12_{direct|disc}_6`,
  `rq3_disc15_7`
- wake-and-verify (C4, 2026-10-13 (m)):
  `rq3snd_{none|loss_all}_wake_verify_{8..14}` (intact/lost, seeds
  5201–5207) and `rq3snd_{premature10|none}_wake_verify_{4..7}` (seeds
  6304–6307); the pilots `..._1..3` (seeds 6301–6303) are reused, never
  relaunched.

Guard facts per family: the campaign-tree launcher
(`rq3adm_p1_01_launch_run.sh`, C3) refuses duplicate labels in-tree (a
`*_<label>` run folder must not exist); the **soundness** frozen-tree launcher
(`rq3snd_frozen2` @ `541fb22`, C2/C4) carries its own duplicate-label refusal,
so C2/C4 have the launcher guard **and** the standalone check; the **timing**
frozen-tree launcher (`rq3tim_frozen` @ `852a8a3`, C1) predates that guard, so
C1 relies on the standalone check + predicate alone. **Every C1/C2/C4 launch
is preceded immediately by** the check pointed at the run's execution tree —
from the operator tree:
`bash ~/efficient-storage-in-edge-scenarios/source/scripts/testing/rq3adm_p0_04_label_check.sh --tree <execution-tree> <label>`
(exit 3 = duplicate → STOP, never launch; exit 0 = launch may proceed; plan
§5.1) — with the independent predicate cross-check
`find <execution-tree>/source/scripts/testing/metrics -maxdepth 1 -name '*_<label>'`
(expected empty), and the outcome recorded in `campaign_log.md`. `--tree` is
**repeatable** — several trees in one invocation, e.g.
`--tree ~/rq3tim_frozen --tree ~/rq3snd_frozen2`, each scanned tree printing
its metrics dir; the label is refused if any scanned tree holds it (exit 3)
and any invalid tree exits 2.
Premature reruns (harness invalidity only, max 1) use the `r` suffix; a voided
timing run is quarantined as `*_<label>_void` and replaced under its planned
label. Every run gets a row in `campaign_log.md`.

Seed provenance (P0 re-check): 5207 new (timing set 5201–5206);
6304–6306 reserved unused (soundness amendment), 6307 newly assigned by this
plan (no recorded run) — each of 6304–6307 serves both the faulted premature
run and its matched no-fault partner of that block; 2322–2323 new
(fixed-image set 2310–2321); 2226–2227
new (rate-12 set 2203–2225); 2007 is the v2 `disc15` set's own seed (its six
recorded runs ran on 2007) — only the `rq3_disc15_7` label is new.

## C1 — intact + lost block 7 (6 runs, seed 5207, order A → B → C, none → loss_all per arm)

Frozen-tree launcher (timing tree `rq3tim_frozen` @ `852a8a3`, whose launcher
predates the duplicate-label guard — the check below is C1's protection): run
the mandated check immediately before every launch — from the operator tree,
pointed at the timing **execution** tree, plus the predicate cross-check
(exit 3 / any output = STOP; plan §5.1) — protocol once, then the six
launches:

```
# per launch (from the operator tree; shown for the first cell, then repeated
# for each label below before its launch):
bash ~/efficient-storage-in-edge-scenarios/source/scripts/testing/rq3adm_p0_04_label_check.sh --tree ~/rq3tim_frozen rq3tim_none_event_only_7
find ~/rq3tim_frozen/source/scripts/testing/metrics -maxdepth 1 -name '*_rq3tim_none_event_only_7'   # expect no output
# launches (from the timing tree):
bash ~/rq3tim_frozen/source/scripts/testing/rq3tim_p1_01_launch_run.sh event_only none      rq3tim_none_event_only_7      5207 2.0
bash ~/rq3tim_frozen/source/scripts/testing/rq3tim_p1_01_launch_run.sh event_only loss_all  rq3tim_loss_all_event_only_7  5207 2.0
bash ~/rq3tim_frozen/source/scripts/testing/rq3tim_p1_01_launch_run.sh hybrid    none      rq3tim_none_hybrid_7          5207 2.0
bash ~/rq3tim_frozen/source/scripts/testing/rq3tim_p1_01_launch_run.sh hybrid    loss_all  rq3tim_loss_all_hybrid_7      5207 2.0
bash ~/rq3tim_frozen/source/scripts/testing/rq3tim_p1_01_launch_run.sh reconcile none      rq3tim_none_reconcile_7       5207 2.0
bash ~/rq3tim_frozen/source/scripts/testing/rq3tim_p1_01_launch_run.sh reconcile loss_all  rq3tim_loss_all_reconcile_7   5207 2.0
```

Screen after the block (validity + mechanism + health) gates C2.

## C2 — premature 10 s lead, blocks 4–7 + matched no-fault partners (24 runs: 12 faulted + 12 partners)

Frozen-tree launcher (soundness tree `rq3snd_frozen2` @ `541fb22`, which
carries its own duplicate-label refusal in addition to the standalone check):
run the mandated check immediately before **every** launch below (faulted and
partners) — from the operator tree, pointed at the soundness **execution**
tree, with the predicate cross-check, e.g. for block 4's first label:
`bash ~/efficient-storage-in-edge-scenarios/source/scripts/testing/rq3adm_p0_04_label_check.sh --tree ~/rq3snd_frozen2 rq3snd_premature10_event_only_4`
and
`find ~/rq3snd_frozen2/source/scripts/testing/metrics -maxdepth 1 -name '*_rq3snd_premature10_event_only_4'`
(expected empty) — exit 3 / any output = STOP; plan §5.1 — recording the
outcome in `campaign_log.md`. Launches run from the soundness tree:
`bash ~/rq3snd_frozen2/source/scripts/testing/rq3snd_p1_01_launch_run.sh …`.

| Block | Seed | Order | Launches (`rq3snd_p1_01_launch_run.sh <arm> premature10 <label> <seed>`) |
| ---: | ---: | --- | --- |
| 4 | 6304 | A → B → C | `... event_only rq3snd_premature10_event_only_4 6304` · `... hybrid rq3snd_premature10_hybrid_4 6304` · `... reconcile rq3snd_premature10_reconcile_4 6304` |
| 5 | 6305 | B → C → A | `... hybrid …_hybrid_5 6305` · `... reconcile …_reconcile_5 6305` · `... event_only …_event_only_5 6305` |
| 6 | 6306 | C → A → B | `... reconcile …_reconcile_6 6306` · `... event_only …_event_only_6 6306` · `... hybrid …_hybrid_6 6306` |
| 7 | 6307 | A → B → C | `... event_only …_event_only_7 6307` · `... hybrid …_hybrid_7 6307` · `... reconcile …_reconcile_7 6307` |

Per-run gate: attestation (`EDGE_READY_PREMATURE_S=10`, deferral [9, 11] s),
quota 0.12, floors, mechanism signature. Screen after block 5 gates the rest.

Matched no-fault partners — one per arm per block, same regime (rate 2.0,
quota 0.12), same seed and same per-block arm order as the faulted runs;
each arm's partner runs first within the arm's sub-batch (recorded soundness
convention). The same mandated check + predicate precedes each partner
launch, e.g.
`bash ~/efficient-storage-in-edge-scenarios/source/scripts/testing/rq3adm_p0_04_label_check.sh --tree ~/rq3snd_frozen2 rq3snd_none_event_only_4`
(exit 3 = duplicate → STOP). Partners run under the `none` fault configuration and record
the standard fault attestation like every run; what distinguishes them is
the `none` fault branch, and their validity is judged by the recorded
no-fault health floors, quota 0.12, and the provenance / no-restart rules
unchanged. A pair whose partner breaches the recorded no-fault health floors
is dropped from the contrast; if two or more seeds are lost for a rule, that
rule's paired-damage component is reported as not assessable (the recorded
soundness §4.5 rule).

| Block | Seed | Order | Partner launches (`rq3snd_p1_01_launch_run.sh <arm> none <label> <seed>`) |
| ---: | ---: | --- | --- |
| 4 | 6304 | A → B → C | `... event_only rq3snd_none_event_only_4 6304` · `... hybrid rq3snd_none_hybrid_4 6304` · `... reconcile rq3snd_none_reconcile_4 6304` |
| 5 | 6305 | B → C → A | `... hybrid rq3snd_none_hybrid_5 6305` · `... reconcile rq3snd_none_reconcile_5 6305` · `... event_only rq3snd_none_event_only_5 6305` |
| 6 | 6306 | C → A → B | `... reconcile rq3snd_none_reconcile_6 6306` · `... event_only rq3snd_none_event_only_6 6306` · `... hybrid rq3snd_none_hybrid_6 6306` |
| 7 | 6307 | A → B → C | `... event_only rq3snd_none_event_only_7 6307` · `... hybrid rq3snd_none_hybrid_7 6307` · `... reconcile rq3snd_none_reconcile_7 6307` |

**Every premature block has its matched no-fault partner** (blocks 1–3
recorded, blocks 4–7 added here), so seed-matched damage (E-P3) is computed
on all seven seed-matched pairs — no unpaired seeds remain. (`…` =
`rq3snd_none_`; row 4 spells every label of the block.)

## C3 — supporting sets (5 runs; own profile restored in the campaign frozen tree, own quota 0.30)

```
bash source/scripts/testing/rq3adm_p1_01_launch_run.sh camp   direct     rq3_camp_direct_7          2322
bash source/scripts/testing/rq3adm_p1_01_launch_run.sh camp   discovery  rq3_camp_disc_7            2323
bash source/scripts/testing/rq3adm_p1_01_launch_run.sh cell12 direct     rq3_probe_cell12_direct_6  2226
bash source/scripts/testing/rq3adm_p1_01_launch_run.sh cell12 discovery  rq3_probe_cell12_disc_6    2227
bash source/scripts/testing/rq3adm_p1_01_launch_run.sh disc15 discovery  rq3_disc15_7               2007
```

Profile source rule per set (first available): the set's archived
`phases_snapshot.json` on the VM; assert baseline 60 s @1.0 /
`compute_spike` 180 s @3.0 (12.0 for `cell12`) with the recorded mix
(`service_pressure` 0.9 / `feed_ranking` 0.05 / `content_lookup` 0.05) /
`cleanup_gap` 180 s @0.5; record path + hash; restore the family profile
(600 s @2.0) after the batch with
`bash source/scripts/testing/rq3adm_p1_01_launch_run.sh restore-family` — it
installs a hash-verified copy (`$RQ3ADM_FAMILY_PROFILE_FILE`, else the frozen
trees' `phases.json`; never a tree-local `git checkout`) and asserts it
(mismatch = STOP; 2026-10-13 (k)). Launch
parameters per the sets' v2 contract: `EDGE_MONGO_MAX_POOL_SIZE=1` (the
6-client regime; the matrix cells pin 6), `CLIENTS=3`/LAN, `EDGE_CPUS=0.30`,
window 1024 (4096 for `cell12`).

C3 execution surface (plan §6, 2026-10-11 (f)): this campaign tree is the
supporting group's execution tree (the launcher derives `REPO_ROOT` from its
own location). Pre-run validation (P0 + preflight, `--support-tree`): the v2
env files by recorded CR-stripped hash, the per-set archived profile hashes
above, and the canonical family profile — the declared drop knob is not part
of this group's surface (it lives in the frozen matrix trees).

## C4 — wake-and-verify (event + confirmation) — 22 runs (2026-10-13 (m))

Frozen-tree launcher: **`~/rq3snd_frozen2`** (the only tree with the wake
code). Ordinal↔seed map: the wake `none` cell carries two ordinal families —
**8–14 = the intact/lost family** @ seeds 5201–5207 (block k ↔ ordinal k+7;
mirrors `COMPLETION_LOST_SEEDS`) and **1–7 = the premature-cell partners**
(1–3 recorded pilots @ 6301–6303, reused; 4–7 new @ 6304–6307). The launcher
refuses duplicate labels, so the families cannot share ordinals; the mandated
label check runs before **every** launch.

Template per run (soundness tree `rq3snd_frozen2` @ `541fb22`; its launcher
refuses duplicate labels itself — the standalone check + predicate below are
the independent guard; wrapper appends `LAUNCHER_EXIT` / `LAUNCH_END`, e.g.
to `/tmp/<label>.log`; record the outcome in `campaign_log.md`):

```
cd ~/rq3snd_frozen2
LABEL=<label>
bash ~/efficient-storage-in-edge-scenarios/source/scripts/testing/rq3adm_p0_04_label_check.sh --tree ~/rq3snd_frozen2 "$LABEL"   # 0 = proceed, 3 = duplicate -> STOP
find ~/rq3snd_frozen2/source/scripts/testing/metrics -maxdepth 1 -name "*_${LABEL}"   # expect no output
nohup sudo -n bash source/scripts/testing/rq3snd_p1_01_launch_run.sh \
    wake_verify <none|premature10|loss_all> "$LABEL" <seed> \
    > ~/c4logs/"$LABEL".log 2>&1 &
```

Per-run verification: cell-exact fault knobs
(`READINESS_WAKE_VERIFY_MODE=probe`, `READINESS_EVENT_FALLBACK_S=20` — plus
`EDGE_READY_PREMATURE_S=10` on the premature runs and
`READINESS_EVENT_DROP_MODE=all` on the `loss_all` runs); quota **0.12**
(`quota_snapshot.json` all-compute match); `rq3snd_fault_attestation.txt`
present with the resolved knobs; zero mid-run restarts; floors and the
standard provenance rules.

**W1a — intact + loss partners (`none`), 7 runs**

| # | Label | Fault | Seed |
| ---: | --- | --- | ---: |
| 1 | `rq3snd_none_wake_verify_8` | `none` | 5201 |
| 2 | `rq3snd_none_wake_verify_9` | `none` | 5202 |
| 3 | `rq3snd_none_wake_verify_10` | `none` | 5203 |
| 4 | `rq3snd_none_wake_verify_11` | `none` | 5204 |
| 5 | `rq3snd_none_wake_verify_12` | `none` | 5205 |
| 6 | `rq3snd_none_wake_verify_13` | `none` | 5206 |
| 7 | `rq3snd_none_wake_verify_14` | `none` | 5207 |

**W1b — lost, 7 runs** (order per block: `none` → `loss_all`)

| # | Label | Fault | Seed |
| ---: | --- | --- | ---: |
| 8 | `rq3snd_loss_all_wake_verify_8` | `loss_all` | 5201 |
| 9 | `rq3snd_loss_all_wake_verify_9` | `loss_all` | 5202 |
| 10 | `rq3snd_loss_all_wake_verify_10` | `loss_all` | 5203 |
| 11 | `rq3snd_loss_all_wake_verify_11` | `loss_all` | 5204 |
| 12 | `rq3snd_loss_all_wake_verify_12` | `loss_all` | 5205 |
| 13 | `rq3snd_loss_all_wake_verify_13` | `loss_all` | 5206 |
| 14 | `rq3snd_loss_all_wake_verify_14` | `loss_all` | 5207 |

**W2a — premature matched no-fault partners, 4 runs** (each block's **first**
run — per block the order is `none` → `premature10`, plan §4.4; single arm D,
so the A–C rotation does not apply)

| # | Label | Fault | Seed |
| ---: | --- | --- | ---: |
| 15 | `rq3snd_none_wake_verify_4` | `none` | 6304 |
| 16 | `rq3snd_none_wake_verify_5` | `none` | 6305 |
| 17 | `rq3snd_none_wake_verify_6` | `none` | 6306 |
| 18 | `rq3snd_none_wake_verify_7` | `none` | 6307 |

**W2b — premature 10 s lead, 4 runs** (each block's **second** run, after its
partner)

| # | Label | Fault | Seed |
| ---: | --- | --- | ---: |
| 19 | `rq3snd_premature10_wake_verify_4` | `premature10` | 6304 |
| 20 | `rq3snd_premature10_wake_verify_5` | `premature10` | 6305 |
| 21 | `rq3snd_premature10_wake_verify_6` | `premature10` | 6306 |
| 22 | `rq3snd_premature10_wake_verify_7` | `premature10` | 6307 |

**Reused pilots (do not relaunch):** `rq3snd_premature10_wake_verify_1..3`
and `rq3snd_none_wake_verify_1..3` @ seeds 6301–6303 — the premature cell's
blocks 1–3 and their partners; verified valid (read-only, 2026-10-13),
attestations resolved `READINESS_WAKE_VERIFY_MODE=probe` /
`READINESS_EVENT_FALLBACK_S=20`. They are never relaunched; the 22 runs
above complete the set.

## Analysis

```
readiness_robustness.py completion-intact    --run-dir <21 none runs: rq3tim_none_*_{1..7}> --out analysis/completion_intact.json
readiness_robustness.py completion-lost      --run-dir <21 loss_all runs + the 21 none runs (E-L4)> --out analysis/completion_lost.json
readiness_robustness.py completion-premature --run-dir <21 rq3snd_premature10_* + 21 rq3snd_none_* partners> --out analysis/completion_premature.json
readiness_robustness.py completion-support   --run-dir <the 5 added replicates> --out analysis/completion_support.json
python3 tools/rq3_stratified_analysis.py <runs...> --csv analysis/per_backend_intervals.csv [--json analysis/per_backend_intervals.json]
```

**Required input sets per subcommand** (each returns exit 0 = every gated
component passes with no NA; 2 = a gated component failed or is NA — a report
signal, NA ≠ stop; 3 = analyzer error):

- `completion-intact` — exactly the 21 `rq3tim_none_*_{1..7}` runs (passing
  the full 42-run set raises a wrong-cell error: STOP, use the `none` subset).
  Gated: E-I1 (A/B before C by median per fast/slow stratum on the
  **spawn→first-success leg** — 2026-10-12 (h) re-scope; the
  ready→admission leg is unmeasurable in this build and is a report note
  only; the pooled `all` stratum is descriptive) and E-I4 conformance.
  These are the core matrix screen inputs; when the wake stage is analysed,
  add the wake intact runs per the C4 bullet below (2026-10-13 (m)).
- `completion-lost` — the 21 `rq3tim_loss_all_*_{1..7}` runs **plus** the 21
  `rq3tim_none_*` runs for E-L4 (without the `none` runs the E-L4
  conformance read is NA, never a silent pass). Gated: E-L1, E-L2, E-L3 and
  E-L4 conformance. Core matrix screen inputs; the wake loss inputs are in
  the C4 bullet below (2026-10-13 (m)).
- `completion-premature` — the 21 `rq3snd_premature10_*` runs plus the 21
  `rq3snd_none_*` partners (E-P1 per run incl. the recorded blocks 1–3, E-P2
  on all 7 blocks, E-P3 on the 7 seed-matched pairs; no E-P4 handling).
  E-P1's log-based gates are not evaluable when a run folder carries neither
  `controller_lan1.log` nor `controller_lan2.log` — the recorded blocks 1–3
  predate that capture (2026-10-13 (j)): they are reported
  (`not_evaluable_logs_absent`), never failed, and never counted as passed;
  new runs carry the logs and evaluate as before. Core matrix screen inputs;
  the wake premature inputs are in the C4 bullet below (2026-10-13 (m)).
- `completion-support` — the 5 added replicates (one run per set/arm;
  a duplicate set/arm identity is refused with exit 3, never last-wins).
  E-S1's gate rides the spawn → first-success leg, per backend (2026-10-13
  (l): the registered ready → admit leg reads 0.000 s in this build and is a
  note); E-S3's band check stays descriptive and is not assessable on that
  degenerate leg (reported as a note, never as out-of-band).
- **wake-and-verify (C4, 2026-10-13 (m)) — required input sets per
  subcommand, each command with its own ordinal family** (the wake `none`
  ordinals 1–7 are refused by `completion-intact`/`completion-lost` and the
  8–14 ordinals by `completion-premature`, exit 3):
  `completion-intact` = the 21 `rq3tim_none_*` runs + the 7
  `rq3snd_none_wake_verify_8..14` (E-W1: wake earlier than periodic in every
  primary stratum on the spawn→first-success leg, gated; wake vs
  `event_only` descriptive near-tie; E-I1/E-I4 unchanged);
  `completion-lost` = the 21 `rq3tim_loss_all_*` + the 21 `rq3tim_none_*` +
  the 7 `rq3snd_loss_all_wake_verify_8..14` + the 7
  `rq3snd_none_wake_verify_8..14` (E-W2: per-block paired slow-share delta
  vs the same-ordinal `none` partner ≤ 2 pp in ≥5/7, gated; the
  `probe_fallback` mechanism and the ≈21 s hybrid timing anchor are
  recorded); `completion-premature` = the 21 `rq3snd_premature10_*` + the 21
  `rq3snd_none_*` + the 7 `rq3snd_premature10_wake_verify_1..7` + the 7
  `rq3snd_none_wake_verify_1..7` (E-W3: immunity branch + one-sided paired
  damage; the gated A-vs-D damage contrast and the descriptive D-vs-C
  near-tie). Wiring as pre-registered in plan §7.5;
  `tools/rq3_stratified_analysis.py` derives `wake_verify:<fault>` from the
  composed identity (direct base + `rq3snd_wake_verify.env` + fault delta) —
  no tool change needed.

**Reading the recorded E-I4/E-L4 qualification:** the health floor is
reported exactly as recorded — 16/18 clean among the recorded blocks with
`none_cell_healthy=false` where it applies — and the blocks 3/5 single-window
transients stay recorded, never re-chased. The campaign conformance read
requires the recorded outcome reproduced (16 clean, breaches only in blocks
3/5) plus a clean block 7, so the recorded qualification does not make a
green verdict impossible and never touches the between-arm contrast.

**Block-7 per-block reading:** the added seventh block (seed 5207) is reported
per block under the same rules (`E-L1.block7`, `E-L2.block7`, `E-L3.block7`,
E-I1/E-I4 as part of the seven-block pools) and no accept count is re-scoped
to the surviving or assessable subset.

Verdicts and counts go to `results.md` after the runs; the P0 identity
evidence lives in `analysis/platform_identity.json` and `campaign_log.md`.
Runs launched from a frozen tree (`rq3tim_frozen`, `rq3snd_frozen2`) require
the check immediately before the launch, pointed at that execution tree —
`bash ~/efficient-storage-in-edge-scenarios/source/scripts/testing/rq3adm_p0_04_label_check.sh --tree <execution-tree> <label>`
(exit 3 = duplicate label, STOP; §5.1 of the plan) — plus the predicate
cross-check `find <execution-tree>/source/scripts/testing/metrics -maxdepth 1 -name '*_<label>'`
(expected empty).

**Operator-tree sync before analysis (plan §12 item 7):** sync the analyzer
package `source/scripts/testing/analysis/rq3/` — including
`readiness_low_headroom.py`, which is missing on the VM operator tree despite
being present in both frozen execution trees — plus the `rq3adm_*` scripts and
`tools/rq3_stratified_analysis.py`; `readiness_robustness.py` imports
`readiness_low_headroom.py` (`from .readiness_low_headroom import ...`), so
the analysis package fails to import without it. The frozen execution trees
are never synced.
