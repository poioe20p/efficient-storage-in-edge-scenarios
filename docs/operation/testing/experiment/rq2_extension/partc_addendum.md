# RQ2 Extension — Part C Addendum: Confirmatory Compute-Bound Campaign (`rq2pc`)

**Date**: 2026-09-28 · **Status**: 📋 **draft — awaiting the review gate; frozen by the FREEZE-3 commit (§9)** · **Parent package**: [experiment_plan.md](experiment_plan.md) · [run_matrix.md](run_matrix.md) · [results.md](results.md)

> **Continues, does not amend.** Parts A/B of the extension package are
> closed (campaign COMPLETE, 30/30 — [results.md](results.md)). This
> addendum pre-registers **Part C**: a dedicated confirmatory campaign for
> the **compute axis** on the v3-validated Series-C allocation. It reuses
> the parent package's gate framework (plan §5.10, adapted to a single
> episode) and adds the Part C acceptance criteria (§7). Where this addendum
> and the parent package disagree, **this addendum governs for `rq2pc`
> runs**.

## 1. Why Part C (context, cited)

- The extension campaign's designed compute stress **did not reproduce the
  locked compute-bound regime** at the tested configuration: Stage A1
  (`nn_cb`, the v3 `cb` shape at rate 1.5) ran the episode at ≈ 61 % of the
  0.15 edge cap (median, 60.7–61.7 %; max 72.8 % — [results.md](results.md)
  audit rows), and a shift run's episode showed only ≈ 3 % blended
  slow-share (lock check, 2026-09-28) — no genuine compute bind to treat.
- v3 established the `cb` bind at the **Series-C allocation** (edge 0.15 /
  storage 0.08) with **12/12** aligned compute-bound replicates showing the
  B1 collapse (plan §1.1) — but at a demand level that the platform no
  longer reaches in the current image/config without a probe-set level.
- **Part C = the same single-episode `cb` shape, same allocation, with the
  episode demand level set by an ascending probe ladder until the episode
  genuinely locks**, then measured across the four arms (`nn`, `cf`, `sf`,
  `ba`) with 6 replicates each.

**Relationship to the claim layers (parent plan §1.2):** Part C targets
**L1** (consequence asymmetry: right vs wrong vs no action under a real
compute bind), **L2** (no fixed policy consequence-free), and **L3**
(selector matches the aligned arm). It does **not** re-test L4 (Part B's
sequential-regime question) and is **not** a re-litigation of Part B.

**Probes are not evidence** (standing rule): the ladder's runs are recorded
in the probe record only; the campaign's 24 runs are the evidence.

## 2. Platform continuity — no rebuild

Part C touches **only harness/orchestration/docs artifacts, never the
running platform**. Verified at freeze (§9):

**Unchanged (byte-identical, verified at freeze):** controller code
(including `policy_gate.py`), all four arm envs (`rq2_none.env`,
`rq2_compute_first.env`, `rq2_storage_first.env`,
`rq2_bottleneck_aware.env`), the base phase files
(`phases_rq2_compute_bound.json` md5 `d40f5f59…`,
`phases_rq2_data_bound.json` `06a880c5…`), the two varying files
(`a7db82c8…` / `46fd82af…`), the edge image (`30a2c88bc1ce`), and all caps
(storage 0.08 / edge 0.15 / pool 12).

**New/changed files (the FREEZE-3 restricted diff = exactly these):**

| # | Path | Change |
| --- | --- | --- |
| 1 | `source/scripts/testing/phases_override/phases_rq2pc_cb.json` | **NEW** — exact copy of the base `cb` file; the probes edit **only** the `compute_bound_episode.rate_per_client` field in place (post-probe diff vs the base file = that one field; the base file is never mutated) |
| 2 | `tools/run_rq2pc_probes.py` | **NEW** — Part C probe-ladder launcher (§4; force-added, like the campaign launcher — `tools/` is gitignored) |
| 3 | `tools/run_rq2_campaign.py` | **CELLS additions only** — the four `pc_*_cb` entries |
| 4 | `docs/operation/testing/experiment/rq2_extension/extension_order_partc.csv` | **NEW** — the 24-run order CSV (§6) |
| 5 | This docs package | this addendum + `run_matrix.md` Part C sections + `results.md` status rows (+ the Part B closure sweep bundled in the same commit) |
| 6 | `source/scripts/testing/analysis/rq2/rq2_bottleneck_aware_campaign.py` | **RUN_RE extension only** (§8) |

**Canonical-files rule (explicit exception, as parent plan §5.2):** the
canonical `phases.json` is untouched; `phases_rq2pc_cb.json` is a
**named-configuration-regime file** under `phases_override/` — the
established v3/extension mechanism — and this is intentional.

**Consequence:** probes may start on the clean VM directly once the
FREEZE-3 draft commit is in place and the pre-run sync/verification (§9)
passes.

## 3. Run shape and cells

**Single-episode shape** (per run) — exactly the base `cb` file's shape;
only the episode demand rate is [probe]-determined:

| # | Phase | Duration | Rate/client | cf | Mix | Source |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `baseline` | 60 s | 1.0 | 0.1 | standard | base `cb` file (unchanged) |
| 2 | `compute_bound_episode` | 600 s | **R\*** | 1.0 | `service_pressure 1.0` | rate **[probe]** (ladder, §4); everything else unchanged |
| 3 | `recovery_gap` | 120 s | 0.5 | 0.05 | standard | base `cb` file (unchanged) |
| 4 | `demand_drop` | 420 s | 1.0 | 0.1 | standard | base `cb` file (unchanged) |

"Standard mix" = `content_lookup 0.6 / feed_ranking 0.25 /
service_pressure 0.15`. **R\*** = the probe-locked episode rate
(`rate_per_client`; ladder labels encode the rate ×10 — 015 ↔ 1.5,
030 ↔ 3.0, 050 ↔ 5.0, 070 ↔ 7.0).

**Cells** (4 × 6 = 24 runs; run labels `rq2pc_{arm}_cb_{rep}`, folders
`<ts>_rq2pc_{arm}_cb_{rep}`; ≈ 30–36 min/run single-episode incl. setup):

| Cell key | Arm env (`rq2_env/`) | Phases file | Caps STORAGE / EDGE | Replicates |
| --- | --- | --- | --- | --- |
| `pc_nn_cb` | `rq2_none.env` | `phases_rq2pc_cb.json` | 0.08 / 0.15 | 6 → `_1.._5` seed 42, `_6` seed 43 |
| `pc_cf_cb` | `rq2_compute_first.env` | `phases_rq2pc_cb.json` | 0.08 / 0.15 | as above |
| `pc_sf_cb` | `rq2_storage_first.env` | `phases_rq2pc_cb.json` | 0.08 / 0.15 | as above |
| `pc_ba_cb` | `rq2_bottleneck_aware.env` | `phases_rq2pc_cb.json` | 0.08 / 0.15 | as above |

Shared shell env (unchanged from the campaign): `WAN_RTT_MS=185`,
`EDGE_MEMORY=512m`, `EDGE_MONGO_READ_PREFERENCE=secondaryPreferred`,
`VIP_DATA_PER_CONNECTION_FLOWS=1`, `OVERLOAD_CPU_PCT=30`,
`OVERLOAD_PEAK_LATENCY_MS=2000`, `EDGE_MONGO_MAX_POOL_SIZE=12`;
`CLIENTS=24 CONTENT_ITEMS=3000 USERS=100 DATA_SEED=42
CURL_MAX_TIME=300 TRAFFIC_DRIVER_MODE=open_loop INFLIGHT_WINDOW=1024
DRAIN_S=30 SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1`.

## 4. Stage-PC probes — the compute-lock ladder (pre-registered; probes are NOT evidence)

**Question:** at which episode demand level does the single-episode
compute-bound run at the Series-C allocation genuinely **lock** (§5), and
does the treated arm (`cf`) then show the full expected signature (§7) at
that level? **Design:** an ascending ladder on the **no-op arm** (`nn` —
stress measured without treatment interference), **stop at the first lock**;
then one **treated-arm confirmation** (`cf`) at the locked rate.

| Probe | Label | Shape / config | Acceptance (ALL-of) | Budget |
| --- | --- | --- | --- | --- |
| **P-0** | `rq2pc_p0_nn_015` | `nn` arm · rate 1.5 (label 015) · base file state (no rate edit) | **lock gate (§5)** · validity set: 0 blackouts · D1–D4 clean · I1 ≥ 5000/LAN · driver integrity · lane asymmetry ≤ 3× | 1 run |
| **P-1** | `rq2pc_p1_nn_030` | `nn` · rate 3.0 (edit in place) — only if P-0 did not lock | as P-0 | 1 run |
| **P-2** | `rq2pc_p2_nn_050` | `nn` · rate 5.0 — only if no lock so far | as P-0 | 1 run |
| **P-3** | `rq2pc_p3_nn_070` | `nn` · rate 7.0 (top rung) — only if no lock so far | as P-0 | 1 run |
| **P-4** | `rq2pc_p4_cf_<code>` | `cf` arm · rate **R\*** = first locking rung (`<code>` ∈ {015,030,050,070}) | **lock gate re-check** + treated-arm signature: **add requirement** (≥ 1 compute add in-episode per LAN) · **zero pre-episode fires** · **B1 collapse ≥ 2×** · **POST slow-share ≤ 5 %** (§7); validity set as P-0 | 1 run |

**Ladder rules (fixed):**

1. Ascending order **015 → 030 → 050 → 070**; after **each** rung compute
   the lock gate (§5) + the validity set (§5) immediately (runner-side
   operational trigger; the recorded classification is re-verified in the
   analysis battery). **Stop at the first LOCK**; the locked rung's rate is
   **R\***. If P-0 (rate 1.5) already locks, P-1..P-3 are skipped (recorded).
2. P-4 always runs at R\* (its label carries R\*'s code). A crashed
   launcher may resume the ladder with `--start-at <code>` (earlier rungs
   are operator-asserted no-lock; the resume is recorded in the log); a
   mid-rung crash, a post-lock crash, or a post-ladder no-lock crash
   (diagnostic pending — `rq2pc_pd_nn_090` has no resume flag) is resumed
   via the documented direct make chain and recorded in the probe record.
3. Each probe run snapshots phases + env into its run folder (usual
   behavior); the in-place rate edit lands **only** in
   `phases_rq2pc_cb.json` and is committed at probe finalization (§9).
4. Launch config (fixed): **direct `make` chain via
   `tools/run_rq2pc_probes.py`** — NOT via the campaign launcher (no
   `CELLS` entries for probes); `nn` probes use `rq2_none.env`, P-4 uses
   `rq2_compute_first.env`; caps/limits as §3; run folders in `metrics/`
   (v3 preflight pattern). The probe launcher carries the lock checker
   (embedded copy of the smoke-tested tool) and deploys it to the VM.
5. **Probe-record discipline:** results go to the "Part C — Record (`rq2pc`)"
   section of [results.md](results.md) (per rung: per-LAN + blended
   slow-share/p50, LOCK verdict, validity rows, severity band, per-server
   CPU descriptor). The P-4 signature pass uses the standard runner-side
   artifacts (decision logs, ready log, client CSVs); exact commands are
   recorded in the probe record. Probes are not evidence.

**Contingencies and budget (fixed):**

- **Any probe run failing** — launch not confirmed, nonzero exit, missing
  folder, checker failure, or **validity flags** (a rung's lock verdict
  does not count until validity passes, §5) — follows the parent §4.7
  unified rule: exclude + document + relaunch ONCE. **The probe phase
  allows ONE relaunch event in total**; a second failing run halts the
  phase → user decision.
- **Wait timeout** → the launcher **aborts WITHOUT relaunch** (the run may
  still be live; a relaunch could double-serve) — manual decision required.
- **No lock through P-3** → ONE diagnostic run `rq2pc_pd_nn_090` (rate 9.0,
  `nn`). Whatever its outcome, **STOP and report** — no silent rate
  escalation; the campaign decision (rate > 7.0 vs redesign) is a user
  decision recorded in [results.md](results.md).
- **P-4 fails its signature** → one re-run at the same rate (the launcher's
  unified relaunch if detected in-script, else the documented direct make
  chain — both folders are recorded); still failing → STOP + report + user
  decision before the campaign.

**Probe budget:** ≤ 5 ladder/confirm runs (P-0..P-4) **+ ≤ 1 relaunch + ≤ 1
  diagnostic = ≤ 7 runs total** (≈ 5–9 GB; ≈ 4 h wall-clock).

## 5. Lock gate and validity battery

**One-line spec (frozen):** **LOCK iff blended-LAN episode slow-share
≥ 10 % AND blended completed-request p50 ≥ 1 s**, where

- **slow-share** = (timed out OR completed latency > 1 s) / (completed +
  timed out) — the **served** denominator;
- **p50** = lower median over **completed** requests;
- both are computed over the **full 600 s `compute_bound_episode`** phase
  from the per-client CSVs, **per LAN + blended**.

Computed immediately after each rung (runner-side); the recorded
classification is re-verified in the analysis battery.

**Validity alongside (before a rung's lock counts):** 0 blackouts · D1–D4
clean · I1 ≥ 5000 completed/LAN (episode) · driver integrity — loader-side
drop-share ≤ 10 % per LAN (the P1-4 driver threshold, parent plan §1.3) and
no unexpected status classes · lane sanity screens: the loader-side
completed-count ratio (flag > 3× or a lane blackout) and the house F2
screen (per-LAN spawns + storage CPU ≤ 3× — `../v3/rq2/analysis_focus.md`)
applied in the battery.

**Reporting (probe record + campaign records):** episode **severity band**
by timeout share — ≤ 5 % / 5–25 % / > 25 % — and the **per-server CPU
descriptor** (expected ≈ 90–100 % of the 0.15 cap during a locked episode;
reported, **not** a gate).

## 6. Campaign order plan (staged 3+3)

One order CSV — `extension_order_partc.csv` (schema
`block,position,cell,run_label,traffic_seed`, cell values = the four §3
keys; hashed at FREEZE-3):

```csv
block,position,cell,run_label,traffic_seed
1,1,pc_nn_cb,rq2pc_nn_cb_1,42
1,2,pc_cf_cb,rq2pc_cf_cb_1,42
1,3,pc_sf_cb,rq2pc_sf_cb_1,42
1,4,pc_ba_cb,rq2pc_ba_cb_1,42
2,1,pc_cf_cb,rq2pc_cf_cb_2,42
2,2,pc_sf_cb,rq2pc_sf_cb_2,42
2,3,pc_ba_cb,rq2pc_ba_cb_2,42
2,4,pc_nn_cb,rq2pc_nn_cb_2,42
3,1,pc_sf_cb,rq2pc_sf_cb_3,42
3,2,pc_ba_cb,rq2pc_ba_cb_3,42
3,3,pc_nn_cb,rq2pc_nn_cb_3,42
3,4,pc_cf_cb,rq2pc_cf_cb_3,42
4,1,pc_ba_cb,rq2pc_ba_cb_4,42
4,2,pc_nn_cb,rq2pc_nn_cb_4,42
4,3,pc_cf_cb,rq2pc_cf_cb_4,42
4,4,pc_sf_cb,rq2pc_sf_cb_4,42
5,1,pc_nn_cb,rq2pc_nn_cb_5,42
5,2,pc_cf_cb,rq2pc_cf_cb_5,42
5,3,pc_sf_cb,rq2pc_sf_cb_5,42
5,4,pc_ba_cb,rq2pc_ba_cb_5,42
6,1,pc_cf_cb,rq2pc_cf_cb_6,43
6,2,pc_sf_cb,rq2pc_sf_cb_6,43
6,3,pc_ba_cb,rq2pc_ba_cb_6,43
6,4,pc_nn_cb,rq2pc_nn_cb_6,43
```

- Blocks 1–6 = replicate 1–6 of each cell, within-block positions rotated
  (counterbalance intent, as the extension CSVs); seeds: reps `_1.._5` = 42,
  `_6` = 43 everywhere.
- **Stage 1 = blocks 1–3 (12 runs); Stage 2 = blocks 4–6 (12 runs).**
- **Stop/restart procedure (fixed):** the launcher is **stopped while the
  12th run (last block-3 row) is in flight** so no block-4 row can launch;
  a missed-window raced launch is **adopted** (not relaunched) and recorded.
  The Stage-1 **checkpoint battery** (§7 gates + acceptance) **waits for
  the 12th run to finish and covers all 12 Stage-1 runs**; any post-stop
  Stage-1 failure is handled by the §4.7 rule before Stage 2 launches.
  Stage 2 resumes with `--start-at rq2pc_ba_cb_4`.
- **Launch discipline (unchanged):** per launch the run-folder count must
  increase by exactly 1; no "already completed — skipping" line for the
  launched label; run folders are never deleted; the orchestrator is
  resume-safe (`--start-at <next-or-in-flight label>`); §4.7 unified rule
  for incidents.

## 7. Gates and acceptance criteria

**Gate framework:** the parent plan §5.10 gate set, adapted to the
single-episode shape: D1/D2/D3 + D4 (fd scan) **hard**; I1 ≥ 5000
completed/LAN (episode); I2 classification honest; M2 per added node; V1
(G2 per-episode bottleneck validation); F1/F2 flags + collapsed-run flag
(episode timeout > 50 % ⇒ flagged review).

**Part C acceptance criteria — per run (the five confirmed items):**

1. **Add requirement** — `cf`/`ba`: **≥ 1 compute scale-up add during the
   episode, per LAN** (decision-log `scale_up` rows with a compute action,
   anchored to the episode window). `sf` is **M1-exempt** (mismatched
   regime: a no-benefit outcome is a valid finding, parent plan §5.10);
   `nn` must show **zero** action rows (a nonzero count is a validity flag).
2. **Zero pre-episode fires** — no `scale_up` action row of any tier before
   the episode start (the `baseline` window). A pre-episode fire flags the
   run (excluded per the unified rule if it changes the regime; documented).
3. **B1 collapse ≥ 2×** — `cf`/`ba`: PRE→POST p50 drop **≥ 2×** (v3 B1
   threshold), PRE = episode start → first compute `node_add`; POST = first
   compute `node_ready` + 120 s → episode end (**fallback = add + 40 s**,
   v3 convention). Required on **both LANs**; a one-LAN pass is a flagged
   partial (reported; not a run-level pass).
4. **POST slow-share ≤ 5 %** — all arms: blended slow-share over the
   `demand_drop` window ≤ 5 % (recovery after the episode; lingering-jam
   check). The `demand_drop` severity band is reported per run.
5. **`nn` persistent-deficit check** — `nn`: the deficit persists to episode
   end: the **final 120 s** of the episode still shows blended p50 ≥ 1 s
   **AND** slow-share ≥ 10 %. (No B1 PRE/POST anchor for `nn` — N/A flag,
   parent plan §7.)

**`sf` expected signature (reported, not gated beyond validity):** 0
compute adds; no compute relief (deficit comparable to `nn`); storage-side
activity measured as waste (`sf`-on-`cb` reference: v3 `sf_cb` rerun
record — compute tier pinned with **0 COMPUTE adds**, wasted storage
activations).

**Reproduce/verdict rules (fixed):** per-cell criteria require **≥ 4/6**
replicates in the same direction (the scaled rule). A gate-tripped run is
excluded + documented + relaunched ONCE (unified rule); a second failure in
the same cell halts the cell → user decision. Pre-registered no-benefit
outcomes (`sf` on the compute axis) are findings, not gate failures.

## 8. Analysis extensions

1. **RUN_RE** (`source/scripts/testing/analysis/rq2/rq2_bottleneck_aware_campaign.py`
   line 86) — exact edit (all other analyzer behavior unchanged; the one
   usage at `discover_runs`/`load_run` reads the four groups unchanged):

   ```python
   RUN_RE = re.compile(r"(\d{8}_\d{6})_rq2(?:pc)?_(cf|sf|ba|nn)_(cb|db|shcbdb|shdbcb)_([1-6])$")
   ```

   (non-capturing `(?:pc)?` insert — old tokens keep matching; `rq2pc`
   runs accepted; probe folders `..._rq2pc_p…` stay excluded by
   construction). **Applied on the VM branch's copy; the local mirror's
   analyzer is pre-extension/stale — never sync the local file over the VM
   copy.**
2. **Dataset:** `rq2pc` runs enter the same arm/mode groups (single-episode
   `cb` segmentation already supported — dry-run validated); the Part C
   battery reports the **rq2pc subset** (filter by folder token) against
   §5/§7; graphs regenerate from the same analyzer.
3. **Carried analysis-side items (required before the Part C analysis
   battery, not before the freeze — user-confirmed):** (i) G2 shift-window
   anchoring tool fix; (ii) M1/teardown per-phase consolidation.

## 9. FREEZE-3 and execution sequence

1. **Review gate** on this addendum + the §2 artifacts (pre-implementation).
2. **FREEZE-3 draft commit (VM, no tag):** first the sync — scp to the VM:
   this addendum, `run_matrix.md`, `results.md`,
   `extension_order_partc.csv`,
   `.github/instructions/edge-lessons-learned.instructions.md` (closure
   sweep), `tools/run_rq2pc_probes.py`, `tools/run_rq2_campaign.py`;
   **VM-side only:** create `phases_rq2pc_cb.json` (`cp` from the VM base
   file — byte-exact, so the exact-copy claim and the one-field post-probe
   diff hold on the working copy of record) and apply the §8.1 RUN_RE edit
   to the VM analyzer copy (the local mirror is stale — never sync it over).
   Then commit the **Part B closure sweep** + all §2 artifacts; **hash
   record**: `tools/run_rq2_campaign.py`, `tools/run_rq2pc_probes.py`,
   `phases_rq2pc_cb.json` (= base md5), `extension_order_partc.csv`, this
   addendum. **Restricted-diff check (mechanical):** `git diff --name-only`
   against the §2 + closure-sweep path list — nothing else may ride along
   (e.g., no `tese/` or other local edits).
3. **Pre-run sync/verification (runner):** re-hash artifacts + docs vs the
   §9.2 record; `git describe`; clean-VM check (0 containers/netns/veths),
   disk check.
4. **Probes (§4)** — on the user's go; results into the Part C probe record
   ([results.md](results.md)).
5. **Probe-finalized commit + tag** — commits the probe-determined rate
   (in-place edit) + the probe record; tag
   **`rq2-extension-partc-final-<date>`**; md5s re-hashed and recorded.
6. **Campaign:** Stage 1 → checkpoint battery → Stage 2 (§6); records in
   [run_matrix.md](run_matrix.md) + [results.md](results.md).
7. **After the campaign:** the Part C analysis battery (§8) — only then do
   thesis documents get touched (claim discipline).

**Naming freeze (fixed once; no churn after FREEZE-3):** token `rq2pc`;
campaign folders `YYYYMMDD_HHMMSS_rq2pc_{nn|cf|sf|ba}_cb_{1..6}`; probes
`..._rq2pc_p{0..4}_{nn|cf}_{015|030|050|070}` (rate ×10) + diagnostic
`rq2pc_pd_nn_090`; cell keys `pc_nn_cb`/`pc_cf_cb`/`pc_sf_cb`/`pc_ba_cb`;
phases file `phases_rq2pc_cb.json`; probe launcher
`tools/run_rq2pc_probes.py`; order CSV `extension_order_partc.csv`;
RUN_RE `_rq2pc_(nn|cf|sf|ba)_cb_([1-6])$`; final tag
`rq2-extension-partc-final-<date>`.

## 10. Risks and open items

| # | Item | Type | Handling |
| --- | --- | --- | --- |
| 1 | **No lock through the ladder** | risk | One diagnostic run at 9.0 (§4); report-gated stop; user decision — no silent escalation |
| 2 | **Minimal-lock fragility** (R\* = *first* locking rung) | risk | The campaign runs AT R\*; if Stage-1 shows systematic non-lock or signature deviation → checkpoint pause + user decision (R\* retained; no silent re-tuning) |
| 3 | **Platform stress at the locked rate** (meltdown class) | platform | Minimal sufficient rate by construction; hardened image `30a2c88bc1ce`; D2/D4 gates; §4.7 unified rule |
| 4 | **`sf`-signature interpretation** (waste-only vs service harm) | interpretation | Pre-registered as reported (§7); no-benefit exemption; not a gate |
| 5 | **Disk/budget** | resource | ≤ 7 probe runs + 24 campaign runs ≈ 23–37 GB vs 77 GB free (2026-09-28) |
| 6 | **Probe discipline** | discipline | Probes are not evidence; probe-determined values tagged [probe] |

## Changelog

| Date | Change | Rationale |
| --- | --- | --- |
| 2026-09-28 | Addendum drafted (Part C pre-registration; user-specified design) — awaiting the review gate | Pre-registration before FREEZE-3 |
