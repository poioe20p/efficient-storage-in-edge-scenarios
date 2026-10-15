# RQ3 Admission Modes — Readiness-Admission Completion Campaign (7-block standardisation) — Plan

**Family:** reframed RQ3 (readiness admission), Family 6
(`rq3_admission_modes`). This campaign **completes the evidence sets** of the
family to the thesis-wide **seven-replicate standard**: it extends the
Family-4 cells (`v3/rq3_timing`, intact and lost, 6 blocks) and the Family-5
cells (`v3/rq3_soundness`, premature claim at the 10 s lead, 3 blocks) to
seven seed-matched blocks — adding matched no-fault partners for the
premature blocks (12 runs, one per mode per block 4–7) — and raises the four
**intact-source supporting
sets** to seven runs: the per-backend admission campaign (`v2/rq3` §6
fixed-image), the higher-rate arm (`v2/rq3` §5 rate-12 cell), the
poll-interval sensitivity arm (`v2/rq3` §3 `disc15`), and the relief
comparison campaign (`v3/rq3` saturation, already seven — no run here). The
evaluated matrix value of the premature condition is frozen at the **10 s
lead**; leads 2 s / 5 s are pilot-only; wake-and-verify is un-parked by the
2026-10-13 (m) amendment (22 runs, §4.4). No new
mechanism, no code change: ≈35 new runs (12 faulted premature + 12 matched
no-fault partners + 6 intact/lost + 5 supporting) close replication gaps,
gated by a platform-identity prerequisite.

**Status:** pre-registration drafted 2026-10-11 from the approved consolidated
RQ3 design (2026-10-11). **No run has launched. P0 (platform identity) gates
every run.**

## 1. Objective

When a newly provisioned backend becomes ready, how do the three admission
rules (the readiness message alone, the message with a bounded re-check, and a
periodic check of the backend) affect **whether and when the new capacity
starts serving requests** and **what users experience**, under **an intact
message, a lost message, or a message that arrives before the backend can
serve**?

Deliverable: the completed **7 seed-matched blocks per condition** —
intact (A–C × 7), lost (A–C × 7), premature at the 10 s lead (A–C × 7 with
matched no-fault partners) — plus the seven-run intact-source supporting
sets; **35 new runs in total** (12 faulted premature + 12 matched no-fault
partners + 6 intact/lost + 5 supporting), computable with the family
analyzers after the P0 identity gate. The answer is read in the three parts
the family already fixes: admission-chain intervals and relief (intact),
slow-share contrasts (lost), damage against the matched no-fault partner
(premature).

Non-goals: new mechanisms or fault classes; premature leads
2 s / 5 s beyond the recorded pilot; the stopped robustness family (archive
only); storage-tier readiness (out of scope); re-measuring or re-gating the
already-certified results; thesis text (updated by the user after results).
Wake-and-verify is **no longer a non-goal** (2026-10-13 (m)): it is evaluated
as the third story mode with 22 prepared runs (§4.4, §7.5).

## 2. Reasonableness boundaries (hard)

- No controller/application code changes. Arm and fault deltas are reused
  **byte-identical**: `rq3sat_direct.env`, `rq3sat_discovery.env`,
  `rq3rob_event_only.env`, `rq3rob_loss_all.env`,
  `rq3snd_premature_lead10.env`, and (supporting sets) `rq3_direct.env`,
  `rq3_discovery.env`, `rq3_discovery_15.env` — all existing canonical files.
  **One** canonical phases file (`source/scripts/testing/phases.json`, edited
  in place only) and **one** canonical env override baseline
  (`source/scripts/testing/controller_env_overrides/current_state_integrated.env`);
  never create `phases_<variant>.json` or `current_state_<variant>.env`
  duplicates. The pre-existing archived variant profiles
  (`source/scripts/testing/phases_override/`, `phases_gap.json`) belong to
  earlier campaigns — recorded history, never launch sources here, and this
  campaign creates no variant file; the only phases file edited or launched
  from is the canonical `phases.json`.
- **One uniform regime for every matrix cell**: baseline (60 s) + 600 s
  compute-bound plateau + recovery gap + demand drop + idle tail (the
  canonical profile, as-is), plateau rate 2.0 req/s/client, per-backend CPU
  quota `EDGE_CPUS=0.12`, 24 clients per domain (the launchers' `CLIENTS=24`,
  i.e. per LAN), same readiness criterion and probe semantics
  (`READINESS_PROBE_TIMEOUT_S=5.0`, retry 1.0 s, `READINESS_PROBE_MAX_S=120.0`
  abandonment bound), same load-balancing policy (`BACKEND_SELECTION_POLICY=topology_host`,
  fixed weights, warm-lease disabled), same flow isolation.
- The supporting intact-source sets are extended **as replicates under each
  set's own fixed workload and quota** (their recorded design property, thesis
  §5.4). Samples are **never pooled across conditions or sets**.
- A collapsed control (driver cancel ≥5 %, quota mismatch, missing
  provenance, mid-run restart, floors missed) is **invalid** — never
  evidence, never chased by raising load.
- The premature matrix value is the **10 s lead**; leads 2 s / 5 s stay pilot
  data.
- Drift of the deployed build on the admission path relative to the
  2026-09-09/10 reference is a **P0 STOP** (re-run decision, §6), never a
  silent extension.

## 3. Design — modes × conditions × 7 blocks

### 3.1 Modes

| Mode | Mechanism | Under lost | Under premature (10 s) |
| --- | --- | --- | --- |
| **A — message only** | admit the moment the readiness message arrives; fallback inert | no re-derivation: zero admission, capacity dark | trusts the claim → serves into an unbindable backend |
| **B — message with a bounded re-check** | admit on the message; a 20 s event-absence timer re-checks via probe | recovers after the timer (delayed, bounded) | admits a present-but-premature claim as true (the fallback is event-absence based → inert under a premature claim); the measured damage grows with the lead (−0.82 / +8.62 / +13.33 pp at 2 / 5 / 10 s, the recorded F2 medians) |
| **C — periodic check** | ignore the message; admit when the 10 s poll observes readiness | recovers at the next poll (delayed, bounded) | waits for servability → immune to the timing lie |
| **D — event + confirmation** (`wake_verify`, 2026-10-13 (m)) | the readiness message only *wakes* an immediate probe; admission requires the probe to succeed; the same 20 s event-absence fallback applies when no message arrives | recovers via the 20 s fallback (delayed, bounded, like B) | probes at the claim; admits only at true servability → immune to the timing lie |

Raw configuration literals for every mode live in §5 only (run labels keep
the recorded arm names `event_only` / `hybrid` / `reconcile` / `wake_verify`;
the mapping is A→`event_only`, B→`hybrid`, C→`reconcile`, D→`wake_verify`,
and no existing cell is relabelled).

**Story reframe (2026-10-13 (m)):** the thesis story is the operational trio
— **event only** / **periodic** / **event + confirmation** — with the
recorded `hybrid` retained as the *recovery-without-verification control* (it
recovers loss but is fooled by a false claim). The four-rule matrix
(`event_only`, `hybrid`, `reconcile`, `wake_verify`) stands as the evidence;
the story is told in three.

### 3.2 Conditions

- **intact** — no fault; readiness path healthy. Read: per-backend
  admission-chain intervals (verified readiness → admission → first routed
  request → first success), stratified by start-up class, plus redistribution
  and relief.
- **lost** — the controller drops every readiness message
  (`READINESS_EVENT_DROP_MODE=all`). Read: slow-share contrasts per block
  over the full plateau, the onset window, and the plateau tail; admissions
  and abandonments; relief completion.
- **premature** — the backend claims readiness 10 s before it can serve
  (`EDGE_READY_PREMATURE_S=10`). The lead is one checking period: the same
  unit that bounds recovery in the lost condition, longer than the backend's
  recorded start-up lag, and the dosage where the recorded signal is decisive
  (the 2 s and 5 s leads were thinner). It is a chosen dosage, not a
  discovered constant. Read: per-rule damage against the matched no-fault
  partner, in the family's common user-visible measure.

### 3.3 Replication, blocking, ordering

- **7 seed-matched blocks per condition**; within a block, one run per mode
  (A, B, C) shares the block seed, and the **arm order rotates per block** so
  no mode systematically runs first.
- Existing valid runs are **not re-run**: intact and lost extend blocks 1–6
  (seeds 5201–5206) with block 7 (seed 5207); premature extends blocks 1–3
  (seeds 6301–6303) with blocks 4–7 (seeds 6304–6307), faulted runs and
  matched no-fault partners alike. **Every premature block has its matched
  no-fault partner** — recorded for blocks 1–3, added here for blocks 4–7.
- The campaign-level rotation continues each family's recorded cycle; §4
  fixes every order.
- Primary units: intact → **backend** (pooled over blocks, within start-up
  class); lost → **block** (matched A/B/C per seed); premature → **block**
  (matched A/B/C per seed) with the paired damage against the matched
  no-fault partner of every block (recorded for blocks 1–3, added for
  blocks 4–7); supporting sets → **run** (within their own set).

## 4. Run list (exact)

All labels are new and refused by the launchers if a run folder already ends
with the label. Seeds are fixed via `RANDOM_SEED`; uniqueness is stated per
set at plan time and re-checked at P0 against the recorded campaigns: 5207 —
new (the timing set uses 5201–5206); 6304–6306 — reserved by the soundness
plan amendment and unused, 6307 — newly assigned by this plan (no recorded
run uses it); each of 6304–6307 serves **both** the faulted premature run
and its matched no-fault partner of the same block (§4.1); 2322–2323 — new
(the fixed-image set uses 2310–2321);
2226–2227 — new (the rate-12 set uses its recorded 2203–2225 seed block);
2007 — **not globally unused**: the v2 `disc15` sensitivity block ran on seed
2007 (6 runs), and the added replicate continues the set's own seed
convention (one fixed seed per sensitivity set); only the label
`rq3_disc15_7` is new.

### 4.1 Matrix completion — 30 runs

**Intact and lost, block 7 (seed 5207)** — executed arm-major, cells in the
order none → `loss_all` per arm, arms in the block-7 rotation A → B → C:

| # | Label | Mode | Condition |
| ---: | --- | --- | --- |
| 1 | `rq3tim_none_event_only_7` | A | intact |
| 2 | `rq3tim_loss_all_event_only_7` | A | lost |
| 3 | `rq3tim_none_hybrid_7` | B | intact |
| 4 | `rq3tim_loss_all_hybrid_7` | B | lost |
| 5 | `rq3tim_none_reconcile_7` | C | intact |
| 6 | `rq3tim_loss_all_reconcile_7` | C | lost |

Rotation check (blocks 1–7, true counts over the recorded cycle — blocks 1–6
`ABC, BCA, CAB, ACB, BAC, CBA`, block 7 `ABC`): A leads three blocks (b1,
b4, b7); B and C lead two each (B: b2, b5; C: b3, b6); B sits second three
times (b1, b6, b7) and C third three times (b1, b5, b7). Block 7 continues
the recorded cycle (`event_only → hybrid → reconcile`, the block-1 order).

**Premature at the 10 s lead, blocks 4–7 (seeds 6304–6307)** — one run per
mode per block, order rotated per block (continuing the recorded cycle):

| Block | Seed | Order | Labels |
| ---: | ---: | --- | --- |
| 4 | 6304 | A → B → C | `rq3snd_premature10_event_only_4`, `…_hybrid_4`, `…_reconcile_4` |
| 5 | 6305 | B → C → A | `…_hybrid_5`, `…_reconcile_5`, `…_event_only_5` |
| 6 | 6306 | C → A → B | `…_reconcile_6`, `…_event_only_6`, `…_hybrid_6` |
| 7 | 6307 | A → B → C | `…_event_only_7`, `…_hybrid_7`, `…_reconcile_7` |

(`…` = `rq3snd_premature10_`; all 12 labels share that prefix. The orders
continue the recorded period-3 soundness cycle — blocks 1–7
`ABC, BCA, CAB, ABC, BCA, CAB, ABC` — so A leads three blocks (b1, b4, b7)
and B and C two each (B: b2, b5; C: b3, b6).)

**Matched no-fault partners, blocks 4–7 (seeds 6304–6307)** — one partner
per mode per block under the `none` fault configuration, recording the
standard fault attestation like every run (validity judged by the recorded
no-fault health floors, §9), same regime as everything else (rate 2.0,
quota 0.12, 600 s plateau), same seed and same per-block arm order as the
faulted runs; as recorded in the soundness blocks, each arm's no-fault
control runs first within the arm's sub-batch:

| Block | Seed | Order | Labels |
| ---: | ---: | --- | --- |
| 4 | 6304 | A → B → C | `rq3snd_none_event_only_4`, `…_hybrid_4`, `…_reconcile_4` |
| 5 | 6305 | B → C → A | `…_hybrid_5`, `…_reconcile_5`, `…_event_only_5` |
| 6 | 6306 | C → A → B | `…_reconcile_6`, `…_event_only_6`, `…_hybrid_6` |
| 7 | 6307 | A → B → C | `…_event_only_7`, `…_hybrid_7`, `…_reconcile_7` |

(`…` = `rq3snd_none_`; launcher
`rq3snd_p1_01_launch_run.sh <arm> none <label> <seed>`, quota 0.12.) With
these, **every premature block has its matched no-fault partner** (blocks
1–3 recorded, blocks 4–7 added here), so seed-matched damage (E-P3) is
computed on all seven pairs — no unpaired seeds remain.

### 4.2 Supporting intact-source sets — 5 runs

| # | Label | Set (mechanism) | Seed | Set regime (own workload / quota) |
| ---: | --- | --- | ---: | --- |
| 1 | `rq3_camp_direct_7` | per-backend admission campaign (direct) | 2322 | `compute_spike` 3.0 req/s/client, 6 clients, quota 0.30, window 1024 |
| 2 | `rq3_camp_disc_7` | per-backend admission campaign (discovery) | 2323 | same set |
| 3 | `rq3_probe_cell12_direct_6` | higher-rate arm (direct) | 2226 | rate 12.0 req/s/client, 6 clients, quota 0.30, window 4096 |
| 4 | `rq3_probe_cell12_disc_6` | higher-rate arm (discovery) | 2227 | same set |
| 5 | `rq3_disc15_7` | poll-interval sensitivity arm (discovery, 15 s poll) | 2007 | rate 3.0 req/s/client, 6 clients, quota 0.30, window 1024 |

Each set runs its own profile and quota (the sets are never pooled); the
per-backend and higher-rate orders run the set's mechanisms back-to-back
(direct → discovery), the disc15 arm runs alone at the sensitivity seed.

### 4.3 Consolidated counts

| Group | Existing | New | Completed |
| --- | ---: | ---: | ---: |
| A–C intact | 18 (6 blocks) | 3 (block 7) | 21 (7 blocks) |
| A–C lost | 18 (6 blocks) | 3 (block 7) | 21 (7 blocks) |
| A–C premature, 10 s lead | 9 (3 blocks) | 12 (blocks 4–7) | 21 (7 blocks) |
| premature no-fault partners | 9 (3 blocks, recorded `rq3snd_none_*`) | 12 (blocks 4–7) | 21 (7 blocks) |
| per-backend campaign | 6 per mechanism | 1 per mechanism | 7 per mechanism |
| higher-rate arm | 6 per mechanism | 1 per mechanism | 7 per mechanism |
| poll-interval sensitivity | 6 | 1 | 7 |
| relief comparison (`v3/rq3`) | 7 per arm (direct, discovery) | 0 (already seven) | 7 per arm (direct, discovery) |
| wake-and-verify (2026-10-13 (m), §4.4) | 9 pilot runs (3 cells × 3 ordinals) | 22 | 31 (7 blocks × 3 sets + the 3 recorded pilots' cells) |
| **Total new runs** | | **35 + 22 (m)** | |

**Completed matrix positions: 84** — 21 per condition set (intact, lost,
premature faulted, premature no-fault partners). The 35 new runs are 12
faulted premature + 12 matched no-fault partners + 6 intact/lost + 5
supporting. The 2026-10-13 (m) amendment adds the **22-run wake-and-verify
completion** (§4.4): 7 intact/loss `none` + 7 `loss_all` (seeds 5201–5207),
+ 4 `premature10` + 4 `none` partners (seeds 6304–6307); with the three
recorded pilot ordinals reused per cell (seeds 6301–6303), the four-rule
matrix completes at 28 additional positions (112 total).

### 4.4 Wake-and-verify completion — 22 runs (2026-10-13 (m))

All from `rq3snd_frozen2` @ `541fb22` with
`rq3snd_p1_01_launch_run.sh wake_verify <fault> <label> <seed>`; the
standalone label check (`rq3adm_p0_04_label_check.sh`) runs immediately
before every launch. The wake `none` cell carries two ordinal families
(the launcher refuses duplicate labels): **1–7 = the premature-cell
partners** (pilots 1–3 @ 6301–6303, new 4–7 @ 6304–6307) and **8–14 = the
intact/lost family** (seeds 5201–5207, mirroring `COMPLETION_LOST_SEEDS`).

| Family | Block | Seed | Labels (ordinal) | Status |
| --- | ---: | ---: | --- | --- |
| intact + loss partners | 1–7 | 5201–5207 | `rq3snd_none_wake_verify_8..14` | **new (7)** |
| lost | 1–7 | 5201–5207 | `rq3snd_loss_all_wake_verify_8..14` | **new (7)** |
| premature (10 s) | 4–7 | 6304–6307 | `rq3snd_premature10_wake_verify_4..7` | **new (4)** |
| premature partners | 4–7 | 6304–6307 | `rq3snd_none_wake_verify_4..7` | **new (4)** |
| premature (10 s) | 1–3 | 6301–6303 | `rq3snd_premature10_wake_verify_1..3` | recorded pilots, reused (verified valid) |
| premature partners | 1–3 | 6301–6303 | `rq3snd_none_wake_verify_1..3` | recorded pilots, reused (verified valid) |

Order: block-major with the recorded rotation (arm/fault order `none` → the
faulted cell within each block; the block order rotates as the recorded
cycle). Harness preflight (read-only, 2026-10-13): the frozen launcher's
case branches accept `wake_verify` with `none` / `premature10` /
`loss_all`, `rq3rob_loss_all.env` is already wired, and all six reused
pilots carry the resolved wake attestation
(`READINESS_WAKE_VERIFY_MODE=probe`, `READINESS_EVENT_FALLBACK_S=20`) with
`valid: True`. The recorded pilot ordinals 1–3 of the remaining `semantic`
cell are not part of this completion.

## 5. Configuration

### 5.1 Matrix cells

- **Phases**: canonical `source/scripts/testing/phases.json`, unmodified
  (baseline 60 s @1.0 → `compute_plateau` 600 s @2.0, pure
  `service_pressure` → recovery gap → demand drop → idle tail). Both matrix
  launchers assert the profile before launching (wrong-file edit = STOP).
- **Canonical env baseline**: `controller_env_overrides/current_state_integrated.env`
  is **not modified**; the family's named regime envs (`rq3sat_direct.env` /
  `rq3sat_discovery.env`) are the documented "distinct named regime" full
  overrides (the saturation regime), and the arm/fault deltas merge over them
  byte-identically at launch (the launcher's env-merge routine).
- **Controller env** (canonical files, merged by the launcher, byte-identical
  reuse):

  | Mode | Base env | Arm delta |
  | --- | --- | --- |
  | A | `controller_env_overrides/rq3sat_direct.env` | `rq3rob_event_only.env` (`READINESS_EVENT_FALLBACK_S=130.0` — inert past the 120 s bound) |
  | B | `controller_env_overrides/rq3sat_direct.env` | — (`READINESS_EVENT_FALLBACK_S=20.0`) |
  | C | `controller_env_overrides/rq3sat_discovery.env` | — (`READINESS_PROPAGATION=discovery`, `DISCOVERY_POLL_INTERVAL_S=10.0`) |
  | D | `controller_env_overrides/rq3sat_direct.env` | `rq3snd_wake_verify.env` (`READINESS_WAKE_VERIFY_MODE=probe`, `READINESS_EVENT_FALLBACK_S=20`) |

  Mode D (2026-10-13 (m)) merges the recorded wake delta over the direct
  base — same 600 s @2.0 pure-`service_pressure` plateau, quota 0.12,
  `CLIENTS=24`, identical launch parameters to A–C (mirrors the recorded
  soundness launcher, §4.4). Frozen semantics (`readiness_gate.py`): the
  `app_ready` event *wakes* an immediate probe and admission requires the
  probe to pass (`admit_source="wake_verify_probe"`); with the event
  dropped (`loss_all`), the 20 s event-absence fallback admits with
  `admit_source="probe_fallback"` (direct propagation).

  Fault deltas: lost adds `rq3rob_loss_all.env`; premature adds
  `rq3snd_premature_lead10.env`; intact and the matched no-fault partners
  add nothing.
- **Launch parameters** (as the recorded Family-4/5 invocation — the P0
  full-invocation diff against the family launchers is the binding check):
  `CLIENTS=24 CONTENT_ITEMS=3000 USERS=100 DATA_SEED=42`, open-loop driver,
  `CURL_MAX_TIME=300 INFLIGHT_WINDOW=1024 DRAIN_S=30`, `STORAGE_CPUS=0.08`,
  `EDGE_CPUS=0.12`, `WAN_RTT_MS=185`, `RANDOM_SEED=<block seed>`,
  `EDGE_MONGO_READ_PREFERENCE=secondaryPreferred`,
  `EDGE_MONGO_MAX_POOL_SIZE=6`, `VIP_DATA_PER_CONNECTION_FLOWS=1`,
  `EDGE_FLOW_ISOLATION=1`, `SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1`.
- **Launchers** (existing, run from the frozen tree that produced the cell):

  ```
  rq3tim_p1_01_launch_run.sh <arm> none|loss_all rq3tim_<cell>_<arm>_7 5207 2.0
  rq3snd_p1_01_launch_run.sh <arm> premature10 rq3snd_premature10_<arm>_<block> <seed>
  rq3snd_p1_01_launch_run.sh <arm> none rq3snd_none_<arm>_<block> <seed>
  rq3snd_p1_01_launch_run.sh wake_verify none|premature10|loss_all rq3snd_<cell>_wake_verify_<ordinal> <seed>   # 2026-10-13 (m), §4.4
  ```

  Both refuse duplicate labels and write the quota snapshot; the soundness
  launcher writes the per-run fault attestation for every run (the `none`
  partners included). Both assert quota 0.12.

  **Frozen-tree enforcement (2026-10-11 (c)):** C1/C2 launch from
  `rq3tim_frozen` @ `852a8a3` and `rq3snd_frozen2` @ `541fb22`, whose launcher
  copies predate the in-tree duplicate-label guard. The runner must therefore
  invoke `bash source/scripts/testing/rq3adm_p0_04_label_check.sh <label>`
  **immediately before every launch from a frozen tree** (exit 3 = duplicate
  → STOP, never launch; exit 0 = launch may proceed) and record its outcome in
  `campaign_log.md`; the in-tree guard on the campaign launcher remains the
  same predicate.

### 5.2 Supporting runs

- **Phases**: for each set, the canonical `source/scripts/testing/phases.json`
  is edited **in place** inside the campaign frozen tree, restored from that
  set's own archived `phases_snapshot.json` (first available run folder of the
  set on the VM; the v2 primary-set snapshots also exist in the local repo
  `source/scripts/testing/metrics/`). Assert on restore: baseline 60 s @1.0;
  `compute_spike` 180 s @ the set's rate (3.0; 12.0 for the higher-rate set)
  **with the recorded mix (`service_pressure` 0.9 / `feed_ranking` 0.05 /
  `content_lookup` 0.05)**; `cleanup_gap` 180 s @0.5. Record source path +
  hash; after the supporting batch, restore the family profile (600 s @2.0,
  pure `service_pressure`) and **assert the restore — mismatch = STOP** —
  recording it. The legacy `phases_override/` profiles are not used or
  modified.
- **Controller env** (canonical files, no delta): `rq3_direct.env` /
  `rq3_discovery.env` / `rq3_discovery_15.env`.
- **Launch parameters** (the sets' recorded contract): `CLIENTS=3` per LAN,
  `INFLIGHT_WINDOW=1024` (4096 for the higher-rate set), `DRAIN_S=30`,
  `CURL_MAX_TIME=300`, open-loop driver, `EDGE_CPUS=0.30`,
  `EDGE_MONGO_MAX_POOL_SIZE=1` (the sets' recorded 6-client v2 value; the
  matrix cells pin 6), `OSKEN_ENV_OVERRIDE_FILE` passed **both** to
  `setup_network` and
  `run_experiment`, `SKIP_CLIENTS=0 SKIP_SEED=0 SKIP_SNAPSHOT=0`, per-run reset
  cycle (teardown_clients → setup_network → run) as recorded for the sets.
- **Launcher** (new, §12): `rq3adm_p1_01_launch_run.sh <set> <arm> <label>
  <seed>` with per-set assertions (profile hash incl. the `compute_spike`
  mix, env composition, window, quota, pool) and
  duplicate-label refusal. `restore-family` additionally compares the restored
  `phases.json` hash against the preflight-recorded `canonical_hashes.json`
  (mismatch = STOP).

## 6. Prerequisite — P0 platform-identity gate (no runs)

Extension is valid only if the platform that produced the existing cells is
recoverable and matched. For each group, the deployment under test is that
group's execution tree (the frozen worktree used to launch its runs); the
operator tree is not part of the identity surface and is reported
informationally. For the supporting sets (C3), the deployment under test is
the campaign tree the supporting launcher runs from (it derives its
`REPO_ROOT` from its own location); that group's recorded reference is the v2
env files (`rq3_direct.env` / `rq3_discovery.env` / `rq3_discovery_15.env`)
and the per-set archived profile hashes the supporting launcher asserts — the
declared drop knob is not part of its surface (2026-10-11 (f)). **Stage-scoped
verdict (2026-10-11 (g)):** the verdict is read per stage — `c1_c2_gate`
(timing + soundness groups: the 84-run matrix) and `c3_gate`
(supporting/campaign group: the five C3 runs); a support-group block
(UNDEFINED or DRIFT) stops only C3 and never C1/C2, a timing/soundness block
stops the matrix, and the overall verdict is their conjunction. P0 records, on
`cloud-vm-rq3`:

1. **Deployed identity** — the working copy HEAD, the available frozen
   worktrees and tags (`rq3tim_frozen` @ `852a8a3`, tag
   `rq3tim-preflight-<date>`; `rq3snd_frozen2` @ `541fb22`, tag
   `rq3snd-preflight-20261003`), and `edge_server:latest` image IDs
   (recorded `207b1f9e8f64` for the soundness era; an unrecorded deployed
   image ID makes that comparison item UNDEFINED — see the verdict rule).
2. **Reference identity** — the build that produced the 2026-09-09/10
   campaign is pinned by its recorded commit/worktree (`rq3tim_frozen` @
   `852a8a3`, tag `rq3tim-preflight-<date>`) plus the recorded admission-path
   hashes; **no image ID is recorded for that build** (only the soundness-era
   `207b1f9e8f64`), so the image half of the intact/lost reference comparison
   is waived — see the waiver below. **Recorded waiver (2026-10-11 (c),
   semantics fixed 2026-10-11 (d)):** the timing-reference identity is the
   recorded commit/worktree plus the recorded admission-path hashes, and the
   image half is waived **in the record** because no timing-era ID exists
   there — the P0 gate reports the timing-image item **WAIVED** (explicitly,
   with the waiver text and its provenance; non-blocking; never a silent
   pass) unless the deployed-side record (image-guard state, timing docs, run
   folders) yields an ID, in which case the item becomes required and is
   compared. The waiver covers the timing-image item only; every other
   required item keeps the UNDEFINED-blocks rule. The soundness build is
   recorded as the same admission-path surface plus the declared default-off
   fault knobs (the recorded off-path byte-identity proof).
3. **Admission-path surface comparison** — hashes of `readiness_gate.py`,
   `compute_node_manager.py` admission functions, `edge_server/source/app.py`
   readiness/bind ordering, `control_events.py`, the arm/fault env files, and
   the `phases.json` profile, deployed vs reference. **Rule for files that
   carry declared default-off knobs** (`edge_server/source/app.py`:
   `EDGE_READY_PREMATURE_S`, `EDGE_READY_SEMANTIC_LIE_S`; `readiness_gate.py`:
   `READINESS_WAKE_VERIFY_MODE`): the hash is taken over the configured /
   off-path surface (the declared knob block excluded), or the recorded
   off-path byte-identity proof (manifest hash + the recorded
   `make_server`-bind-before-emission ordering facts) substitutes for the
   hash on that file; a difference outside a declared knob block, or an
   unverifiable knob-off claim, fails the comparison. Harness-only drift
   (telemetry, storage, docs, thesis) does not block.
4. **Verdict** (every required comparison item must be *defined* — recorded
   on both sides — and equal; a required item missing from the record is
   reported **UNDEFINED** and **blocks**, never a silent pass; the sole
   exception is the timing-image item waived in item 2, which reports
   **WAIVED** and does not block — still explicit, never silent):
   - **MATCH** → proceed. Each matrix group runs from the frozen tree that
     produced its cells (timing → `rq3tim_frozen`; premature →
     `rq3snd_frozen2`) — the group's execution tree is the identity surface
     (the operator tree is informational); with a group's execution tree
     absent, that group's identity is UNDEFINED and blocks (no operator-tree
     substitution, 2026-10-11 (e)). The supporting runs run from the campaign
     tree the supporting launcher runs from (its C3 execution group, validated
     against the v2 env files and the per-set archived profile hashes); each
     added replicate's build identity is recorded with the set (documented
     build split; never silently pooled).
   - **DRIFT** (any admission-path difference vs the reference; *affected* =
     the whole extension — the drift invalidates the shared admission-path
     reference for all three conditions, so intact, lost and premature cells
     are all affected) → **do not extend**. The runner records the drift
     evidence in `campaign_log.md` and executes the corrective re-run **in
     full on the deployed build** — the pre-registered corrective matrix is
     identical in seeds and orders to §4.1 but with all seven blocks run
     fresh: intact 21 runs, lost 21 runs, premature 21 faulted runs + 21
     matched no-fault partner runs (84 matrix runs); the supporting
     batch then runs on the same deployed build with its identity recorded.
     **Wake stage under DRIFT (2026-10-13 (m)/(o)):** the wake code exists
     only in its reference tree @ `541fb22`, so the wake stage (§4.4, 22
     runs) **always launches from that reference tree and is never
     re-launched on any other build**; its identity dependency is the snd
     tree @ `541fb22` (verified in the (m) harness preflight). If the drift
     affects the soundness group, the corrective A/B/C matrix runs on the
     deployed build while the wake stage still runs from `541fb22`, and every
     E-W contrast is then reported as **cross-build** (stated in
     `results.md`); drift confined to the timing group leaves the wake stage
     unaffected.
     The extension run list is abandoned (archived as superseded in the
     campaign log).

     **Corrective-matrix budget and sequencing (pre-registered):** 84 fresh
     matrix runs (21 per condition set — intact, lost, premature faulted,
     premature matched no-fault partners — each 7 blocks × 3 arms) plus the
     5 supporting runs plus the **22 wake runs** (7 intact/loss `none` + 7
     `loss_all` + 4 `premature10` + 4 partners; §4.4), one at a time with
     full reset; ≈42 min per matrix/wake run
     + ≈12–13 min per supporting run + reset/screening overhead →
     **≈77–83 h wall time** on `cloud-vm-rq3` (matrix + supports ≈61–66 h;
     the wake stage adds ≈16–17 h). Sequencing: intact → lost →
     premature (faulted + partners) → supporting batch → wake stage
     (`none` → `loss_all`; per block `none` → `premature10`; always from
     `541fb22`, §6 DRIFT clause), the same order
     discipline as §4;
     the corrective matrix replaces the §4 extension (archived superseded),
     never runs in addition to it.

P0 verdict and hashes are written to `analysis/platform_identity.json` and a
human summary row in `campaign_log.md`. No run launches before MATCH.

## 7. Pre-registered expectations per cell

Thresholds are relative to the certified Family-4/5 results they replicate.
"Pass" per condition is the conjunction below; failed directions are reported,
never chased. Accept counts that restate recorded family rules carry their
recorded, fixed pre-registered denominators; the added seventh block is
reported per-block under the same rules, and no accept count is re-scoped to
the surviving or assessable subset.

### 7.1 Intact (A–C × 7 blocks) — admission chain and relief

- **E-I1 (mechanism, gated, primary A vs C; B vs C secondary — leg
  re-scoped 2026-10-12 (h)):** per-backend **spawn → first successful
  response**, pooled over the 7 blocks and compared **within start-up class**
  (fast-binding vs slow-binding, the recorded v2 strata; class from the
  per-backend bind record): A and B serve earlier than C by median in every
  primary stratum, and C's median sits later than A/B by roughly its check
  period (band (0, one 10 s poll period]; recorded same-regime anchor for
  this leg: 11.27 s vs 17.70 s, exact MWU p = 0.0005; the C1 stage screen
  read A 13.19 / B 13.15 / C 15.36 s). Exact MWU + Cliff's δ reported on the
  campaign's own pooled backends; the per-class direction flags and the
  C-band are reported alongside. **Leg note (2026-10-12 (h)):** the
  ready→admission leg (`app_ready_ts→admitted_ts`) is **unmeasurable in this
  build** — instrument degeneracy: it reads ~0.000 s for all three arms
  across the intact set, while the service-log trace shows C's ≈2.9 s
  quantization — so it is recorded as a note in the report and never gates;
  the earlier regime-note d = −0.837 / P(direct < discovery) = 0.706 belongs
  to the adjacent `admit→first-routed` interval. B's admit-source mix
  reported; ≥80 % `event` expected (if below, reported with diagnosis, not
  chased).
- **E-I2 (handover quality, descriptive — no gate):** admitted → first routed
  request and spawn → first success reported per mode, with the initial-mix
  share and zero unattributed `000`, against the recorded handover-quality
  anchors (v2 fixed-image: `useful_share` = 1.000 and 0× http=000 fast-fails,
  12 runs / 47 backends; the pre-fix direct 0.739 artifact recorded as
  superseded). No mode separation beyond the admission shift is expected; a
  divergence is reported, never chased.
- **E-I3 (redistribution onset, descriptive):** the first served request
  reaches the new backend ≈ one poll period sooner under A/B; the amount
  redistributed and the incumbent relief once admitted are unchanged between
  modes (the v2/v3 precedent: relief magnitude not separated, p = 0.209).
- **E-I4 (health floor — the recorded H-T3 run-level gate):** every intact
  (none-cell) run is judged under the recorded all-or-nothing floor — bad ≤1 %
  (full plateau) ∧ plateau-tail slow ≤2 pp — over the explicit denominator of
  the 21 intact runs (3 arms × 7 blocks; 18 recorded + 3 new); driver-clean
  (cancel <5 %) stays a per-run validity floor (§9). The recorded outcome
  stands (16/18 clean → `none_cell_healthy = false`, the blocks 3 and 5
  single-window transients); the floor is never re-scoped to a per-block
  majority.

### 7.2 Lost (A–C × 7 blocks) — slow-share contrasts

Block assessability stays as recorded: floors + driver-clean + controls
(B ∧ C) plateau-tail slow ≤2 pp + Δ computable. **Block 4 (seed 5204)
remains excluded** from assessability (recorded reconcile control tail
4.08 %); the completed set is assessed on blocks 1, 2, 3, 5, 6, 7.

- **E-L1 (headline, gated):** per-block
  `Δ_slow = slow_rate(A) − max(slow_rate(B), slow_rate(C))` ≥5 pp in **≥4/6
  assessable blocks** — the recorded H-T1 accept rule (denominator fixed at
  the family's pre-registered six-block set; 5 assessable after the recorded
  block-4 exclusion) — ∧ full-plateau median Δ ≥5 pp, and the same ≥4/6 +
  median over the **onset window** (first 150 s) as co-primary; exact
  one-sample MWU on the per-block Δ list vs zeros + Cliff's δ. (Certified
  precedent: 5/5 assessable, medians 7.64 pp full / 28.01 pp onset.)
- **E-L2 (mechanism and relief, gated):** A: 0 admitted / ≥2 abandoned
  candidates per LAN, zero new-backend successes, in ≥5/6 blocks (the
  recorded H-T2 accept count); B: every admission via `probe_fallback`, ≥1
  per LAN; C: every admission via `probe`, ≥1 per LAN; relief completion
  (B ∧ C plateau-tail slow ≤2 pp) in ≥5/6 blocks (recorded H-T2 accept
  count).
- **E-L3 (boundedness, gated):** A slow-share median ≤25 % and ≤25 % in ≥4/6
  assessable blocks (the recorded H-T1 boundedness accept count).
- **E-L4 (health floor):** the no-fault (intact) runs are judged under the
  same recorded H-T3 run-level gate as E-I4 — bad ≤1 % (full plateau) ∧
  plateau-tail slow ≤2 pp on every intact run (denominator explicit: the 21
  intact runs, 3 arms × 7 blocks); the recorded blocks 3 and 5 single-window
  transients stay recorded, not re-chased, and the fresh block 7 runs enter
  under the same per-run gate.

### 7.3 Premature, 10 s lead (A–C × 7 blocks) — damage vs matched no-fault

- **E-P1 (mechanism attestation):** the 12 new faulted runs carry per-run
  validity + attestation: measured claim→bind deferral ∈ [9, 11] s and
  `EDGE_READY_PREMATURE_S=10` attested; A and B show the false-claim
  signature (in-window `000` ≥10/LAN; ≥1 `CHECK VIOLATION` warning); C shows
  immunity (**`000` rows ≤1 per run ∧ ≤0.2 % of offered**; 0 successful
  new-backend flows before bind; 0 `CHECK VIOLATION`). A signature failure on
  a new run → harness re-check (max 1, §9); the 9 recorded runs (blocks 1–3)
  keep their recorded attestations from the soundness campaign and are never
  re-run. Cell-level checks against the recorded bands: admitted → first
  *successful* flow ∈ [8, 12] s (A/B — the recorded R1(c) band); C:
  `t_claim` → first success ∈ [10, 22] s (the recorded R2(d) band), with the
  recorded descriptive sanity admitted → first flow ∈ [0, 2] s. A cell is
  assessable on ≥5/7 passing blocks. Log-based gates are not evaluable when
  the run folder carries neither `controller_lan1.log` nor
  `controller_lan2.log` (the recorded-era folders predate that capture); a
  not-evaluable gate is reported explicitly (`not_evaluable_logs_absent:`
  true plus the reason, and the `E-P1.not_evaluable_runs` list) and is
  excluded from the per-run pass/fail — never treated as passed or failed
  (2026-10-13 (j)). The 12 new matched no-fault partner
  runs run under the `none` fault configuration and record the standard
  fault attestation like every run; what distinguishes them is the `none`
  fault branch, and their validity is judged by the recorded no-fault health
  floors (§9); the mid-run restart / provenance rules apply to them
  unchanged.
- **E-P2 (rule separation, gated, all 7 blocks):** per-block
  `Δ_s = U(A) − U(C)` and `U(B) − U(C)` > 0 in ≥5/7 blocks per contrast,
  median Δ ≥5 pp, exact one-sample MWU on the seven Δ values vs 0 + Cliff's
  δ. Each block's runs share the seed (identical demand), so the contrast
  needs no no-fault partner: it measures the trusting rules' exposure
  relative to the waiting rule under the same fault and demand.
- **E-P3 (absolute damage, gated on the seven matched pairs):**
  `D_s(rule) = U(rule, premature10, s) − U(rule, none, s)` on **all seven
  seed-matched pairs** (seeds 6301–6307 — blocks 1–3 with the recorded
  `rq3snd_none_*` partners, blocks 4–7 with the partners added here), in the
  family's class-based damage measure (`U` over `offered`, §8). A and B:
  median `D_s` ≥5 pp with ≥5/7 pairs positive (`D_s` > 0 pp — the sign
  count; the ≥5 pp bar is the median criterion, so the certified B seeds
  {13.34, 3.86, 16.41} are 3/3 positive, recorded as-is); C: per-pair `D_s`
  ≤2 pp with ≥5/7 pairs passing (the recorded three pairs score 3/3 under
  this rule). The recorded three pairs (seeds 6301–6303) re-assert their
  certified values; the certified F2 result stands (+12.57 / +13.33 vs
  −0.99 pp medians).

### 7.4 Supporting sets — added replicates

A single added replicate per mechanism cannot carry the set's significance
statistics (the set-level δ / exact p are n=6/arm results over many
backends); it can show its own validity and direction/consistency against the
recorded set results — it cannot re-derive the set statistics, and the
set-level statistic remains the certified v2 value. Each added run must pass
its set's validity gates and reproduce the set's direction:

- **E-S1 (per-backend campaign; leg re-scoped 2026-10-13 (l)):** the gated
  leg is **spawn → first successful response**, per backend — the registered
  ready → admit leg is unmeasurable in this build (it reads exactly 0.000 s
  for both mechanisms, `app_ready_ts == admitted_ts`; the same instrument
  degeneracy as the 2026-10-12 (h) amendment, reconfirmed on the C3 runs) and
  is reported as a note, never gating. Direction: direct earlier than
  discovery in every backend of the replicate (C3 screen probe: 4/4 backends
  on the two camp runs; medians 1.93 s vs 6.16 s — discovery later by
  approximately its poll wait; the every-backend form is used). Gated,
  leg-independent facts retained: direct event-sourced, discovery
  probe-sourced; handover quality reported against the set's recorded anchors
  (`useful_share` = 1.000, 0× http=000 fast-fails, 12 runs / 47 backends).
  The registered band readings (direct ≤0.05 s; discovery in (0, 10 s]) stay
  reported inside the `ready_to_admit_leg` note; direction consistent with
  the set's recorded full separation (0.001 s vs 6.984 s, δ = −1.000 within
  every stratum — the δ is the recorded set statistic, not recomputable from
  one replicate).
- **E-S2 (higher-rate arm):** scale decision → usable capacity reported
  against the set's recorded medians (direct 2.17 s vs discovery 6.01 s,
  n=6/arm, exact p = 0.0022, d = −1.000 — set-level, not recomputable from
  one run); the added replicate checks the direction (direct < discovery) and
  the recorded null (gap-window timeout/failure = 0.000, 6×6 all-zero);
  driver clean at window 4096.
- **E-S3 (poll-interval sensitivity, descriptive):** the 15 s poll's
  readiness → admission quantization ≈ one period scale, larger than the
  recorded 10 s arm by ≈half the period difference (precedent 9.6 → 15.2 s
  per position); reported descriptively. The registered ready → admit
  reading is the same unmeasurable (h)/(l) leg: when it reads 0.000 s the
  band check is not assessable and is reported as a note (2026-10-13 (l)).

Deviations are flagged against the set's recorded range and reported — a
flagged replicate is a finding, not a rerun trigger (except harness
invalidity, §9).

### 7.5 Wake-and-verify (event + confirmation) — 2026-10-13 (m)

The un-parked third story mode on its own 7-block sets (§4.4). Gated vs
descriptive is explicit per check:

- **E-W1 (intact, gated direction + descriptive companion):** on the (h)/(l)
  leg (per-backend **spawn → first successful response**, stratified by
  start-up class), the wake median is **earlier than periodic (reconcile) in
  every primary stratum** — direction gated, per the E-I1 stratification
  (fast <1 s / slow ≥5 s binding; the pooled class is descriptive). Reported
  against `event_only` descriptively (a near-tie is expected: the event wake
  adds only a probe round-trip). The pilot's small no-fault cost
  (+0.2 / +3.1 pp at two of the recorded seeds, H-S4 healthy-cell read) is
  the open item this set re-resolves; no expected user harm. Evidence seeds
  5201–5207 (`rq3snd_none_wake_verify_8..14`). **Provenance (2026-10-13
  (o)).** The wake runs come from the soundness tree while the
  `event_only` / periodic intact runs come from the timing family — same
  regime and readiness criterion, P0-verified per tree — so E-W1 is a
  **cross-tree** contrast, stated as such when reported (under
  soundness-group drift it is additionally cross-build, §6).
- **E-W2 (lost, gated no-harm + recorded mechanism):** recovery rides the
  20 s event-absence fallback; the per-block paired **slow-share delta vs its
  own `none` partner ≤ 2 pp in ≥5/7 blocks** (full plateau; a partner
  no-fault-floor breach or invalidity drops the pair, ≥2 lost seeds make the
  component not assessable — recorded §4.5 rule). The mechanism source is
  **recorded** (frozen `readiness_gate.py`: event dropped ⇒
  `admit_source="probe_fallback"`; the no-fault wake source is
  `wake_verify_probe`), and the recovery timing is reported against the
  recorded hybrid loss anchor (≈21 s; descriptive).
- **E-W3 (premature 10 s, gated immunity + paired damage):** run-wide
  `000` ≤1 and ≤0.2 % of offered; zero successful new-backend flows before
  bind; zero `CHECK VIOLATION` (log-absent folders: not evaluable, §7.3
  E-P1 rule); paired damage `D_s ≤ 2 pp` in ≥5/7 pairs (one-sided per-pair
  form, as C); `claim → first` within [10, 22] s with the median reported
  against periodic's (expected at the early end — admission at true
  servability). The recorded pilot `premature10_wake_verify_1` carries a
  recorded pre-bind transient (2 successes, like the recorded b2 reconcile
  control) — reported per run, the cell stays assessable at 6/7.
- **E-P2 extension (gated + descriptive):** the damage contrast
  `U(A) − U(D)` ("A vs D", wake vs event_only) uses the E-P2 accept rule
  (positive in ≥5/7 blocks, median ≥5 pp, exact MWU + Cliff's δ); the
  `U(D) − U(C)` read ("D vs C", wake vs periodic) is **descriptive**
  (near-tie expected).

**Amendment (2026-10-15) — E-W screen executed and integrated.** The §4.4
22-run C4 completion is done — 22/22 wake runs valid, cell-exact,
restart-free (`campaign_log.md` C4; 2026-10-13 → 2026-10-14) — and the
three wake screens (`completion_intact_wake.json`,
`completion_lost_wake.json`, `completion_premature_wake.json`) were
executed and integrated. Verdicts against the checks above:

- **E-W1 (intact):** fast class D **4.01 s** (n = 41) vs A 4.08 s
  (near-tie, +0.07 s) and C 9.98 s — D earlier than C by 5.97 s. Slow
  class: no D evidence — the ~10 s bind stall was universal in the
  September runs (10.0–10.4 s every backend) and absent in every October
  run (0/41 backends ≥ 5 s; max 0.089 s). Recorded gate pass = false.
- **E-W2 (lost):** paired plateau slow-share deltas 7/7 blocks ≤ 2 pp
  (median −0.4 pp; −0.32 / −1.51 / −0.65 / −0.01 / −0.71 / −0.37 /
  +1.23); mechanism `probe_fallback` 44/44 under loss, `wake_verify_probe`
  30/30 intact; admits 6–7 per run, 0 abandoned. Recorded screen read NA
  (it dropped the b2/b5 pairs for partner tails of 2.19 % and 3.64 %).
- **E-W3 (premature 10 s):** damage median −0.9 pp over the 7
  seed-matched pairs (recorded 6-pair median −2.05; 6/7 within 2 pp,
  exception b5 +3.13 pp whose partner tail was 3.64 %); claim → first
  10.99 s vs periodic 19.47 s; gated A−D contrast +16.86 pp, 7/7 blocks
  positive, MWU p = 0.00029, Cliff's δ = 1.0 (pass); D−C −0.24 pp
  near-tie (descriptive); two wake runs carry the recorded two-success
  pre-bind transient (b1 pilot, b4). Recorded gate pass = true.
- **Strata-with-evidence reading (E-W1).** The gate phrase "in every
  primary stratum" is read on the strata that contain evidence: the slow
  stratum is empty for D because the bind stall did not occur in the
  completion era (0/41 backends ≥ 5 s; max 0.089 s), while the A–C slow
  class comes from the September runs. The recorded analyzer pass stays
  **false** and the thesis reports this as a limitation (the era-scope
  qualifier applies wherever the strata are described).
- **Author ruling (2026-10-14) applied.** Marginal 2–4 % variation is
  not by itself a reason to drop runs or pairs; affected pairs are
  retained with the deviation carried as a note. Applied: E-W2 re-read
  at 7/7 (b2/b5 partner tails 2.19 %, 3.64 %); E-W3's b1 pair re-included
  (partner tail 3.95 %, damage −0.87 pp). The recorded b5 A-pair breach
  (8.93 % tail) is outside the ruling and stays dropped (A's median stays
  on 6 usable pairs).

## 8. Analysis procedure
Tools: `source/scripts/testing/analysis/rq3/readiness_robustness.py`
(extended, §12) and `tools/rq3_stratified_analysis.py` (extended to
multi-run aggregation); per-run stats via `tools/rq3_campaign_stats.py`.

- **Windows** come from each run's `phases_snapshot.json` labeled phase
  bounds; rows are selected by `sent_at`. Plateau = 600 s block;
  onset = first 150 s; tail = last 300 s.
- **Classes (I2-honest, priority order, first match wins):** `timeout` →
  `000` → `fail5xx` → `slow` (completed, latency >1.0 s) → `good`;
  `cancelled` / `dropped` excluded from offered and reported separately.
- **Intact** (primary unit: backend): from `admission_log_lan{1,2}.csv`,
  `app_ready_ts → admitted_ts` (verified readiness → admission),
  `admitted_ts →` first routed request (from `client_requests.csv` by
  `backend_id`), and spawn → first successful response; start-up class from
  the per-backend bind record (fast <1.0 s, slow ≥5.0 s; the [1, 5) s band is
  recorded and included in the pooled "all" stratum only). Exact MWU + Cliff's
  δ between modes, per stratum, over pooled backends; medians reported. No
  confidence intervals — the family's pre-registered test is exact MWU + δ
  plus agreement across blocks.
- **Lost** (primary unit: block): `slow_rate` per run = timeouts + latency
  >1.0 s over completed + timeout, pooled; per-LAN descriptive. Per-block
  full-plateau and onset Δ against `max(B, C)`; tail slow per mode; exact
  one-sample MWU on the Δ list vs zeros + Cliff's δ; relief accounting from
  the admission logs. The recorded block-4 exclusion applies; the new block
  7 is assessed fresh under the same rules.
- **Premature** (primary unit: block): `U` = share of timeout + 000 + fail5xx
  + slow over offered (plateau); `D_s` per matched pair; `Δ_s` per block
  (E-P2); exact one-sample MWU + sign counts; `CHECK VIOLATION` and in-window
  `000` counts extracted per the recorded F2 window
  `[t_bind − 20 s, t_bind + 30 s]` (lead 10 s).
- **Supporting**: per-set metrics (E-S1…E-S3) computed within each set only by
  the `completion-support` subcommand (§12); the added replicate is reported
  alongside the set's recorded values and never pooled with other sets.
- **Multiplicity**: none — a small number of named contrasts fixed in
  advance, per the thesis's stated discipline.

## 9. Validity and exclusion rules

| Req | Plan magnitude / evidence |
| --- | --- |
| Reproducibility | n = 7 blocks/condition; direction counts (≥5/7); seeds fixed per block |
| B1/B2 | N/A — no benefit claim; lost/premature judged against their own directions |
| M1 | ≥1 compute add per LAN in the plateau, every run (controller log + quota snapshot) |
| M2 | admitted backends serve ≥1 success (A lost is the designed zero — reported, not gated) |
| V1 | old-tier CPU median ≥60 % pre-first-ready on the matrix runs (recorded anchor); supporting sets keep their recorded saturation criteria |
| I1 | matrix floors: ≥5,000 pooled / ≥1,000 per LAN plateau offered+outcome rows; baseline ≥100 pooled / ≥50 per LAN; F2 window ≥15/LAN; supporting sets: ≥2,000 `compute_spike` completed pooled and ≥100 baseline |
| I2 | §8 classes; denominators: `offered` for U/D, completed + timeout for slow-share |
| D1 | 0× `NotPrimary`/`NotPrimaryOrSecondary` (matrix); supporting sets keep their recorded flow-validation gates (Check C ≥0.85) |
| D2 | no controller restart, no container crash |
| D3 | `phases_snapshot.json` + `controller_env_snapshot.env` + `quota_snapshot.json` (+ `rq3snd_fault_attestation.txt` for every premature-cell run — the `none` partners record it under the `none` fault branch) in every run folder |
| Flags | telemetry continuity; LAN symmetry ≤3× (flag, not exclusion) |

- **Exclusions (pre-registered):** lost block 4 remains excluded from
  assessability; intact blocks 3 and 5's recorded health transients remain
  recorded; **every premature block has a matched no-fault partner** (blocks
  1–3 recorded, blocks 4–7 added here), so E-P3 is computed on all seven
  seed-matched pairs — no unpaired seeds remain; the matched partner runs
  are valid only if they meet the recorded no-fault health floors, and the
  mid-run restart / provenance rules apply to them unchanged; a pair whose
  partner breaches the recorded no-fault health floors is dropped from the
  contrast, and if two or more seeds are lost for a rule, that rule's
  paired-damage component is reported as not assessable (the recorded
  soundness §4.5 rule); a component is
  **NA** if fewer than 5/7 blocks are assessable (NA ≠ stop).
- **Harness-invalid reruns:** allowed once per scheduled run for harness
  invalidity only (wrong profile, missing attestation, quota mismatch,
  mid-run restart, unrecoverable driver failure) — never for a fail
  direction, never to replace a valid run. Premature reruns use the
  launcher's `r` suffix; a voided timing-extension run is quarantined
  (`*_void` folder) and replaced under its planned label. All reruns and
  quarantines are recorded in `campaign_log.md`.
- **Stop rules:** P0 DRIFT → extension abandoned, corrective full re-run
  matrix (§6) applies; a run whose attestation/provenance fails twice in the
  same label → stop that cell and report; a systematic mechanism failure
  across a condition (e.g., B failing to recover under lost in ≥3 blocks) →
  stop the remaining cells of that condition and report; driver-clean
  failures ≥2 consecutive runs → stop and diagnose the harness.

## 10. What the runner must capture

- **Per run**: `phases_snapshot.json`, `controller_env_snapshot.env`,
  `quota_snapshot.json` (all compute containers match the requested quota —
  0.12 matrix / 0.30 supports), `admission_log_lan{1,2}.csv`,
  `client_requests.csv`, controller logs, `container_events.csv`,
  `node_lifecycle_timings.csv`, `elasticity_events.csv`, `run_status.json`;
  for every premature-cell run the `rq3snd_fault_attestation.txt` (faulted
  and `none` partners alike); the exact launcher invocation line for every
  run; and the `rq3adm_p0_04_label_check.sh` outcome for every run launched
  from a frozen tree (invoked immediately before the launch, §5.1).
- **Per campaign**: a checkpoint row per run in `campaign_log.md` (label,
  seed, mode, condition, quota verdict, mechanism counts — admitted by
  source, abandoned — floors, driver-clean, verdict GO/REPORT/STOP);
  `analysis/platform_identity.json` + the P0 summary; group-level checkpoints
  after intact+lost block 7, after premature blocks 4–7, and after the
  supporting batch.
- **Released to this folder**: `analysis/` JSONs/CSVs per condition
  (interval tables, slow-share per block, damage per rule, mechanism
  accounting), `graph` source data as produced; `results.md` is written only
  after the runs, never before.

## 11. Stages, cost, stop rules

1. **P0 — identity + harness readiness (no runs)**: §6 gate; the launcher
   profile assertions rehearsed in dry-run; analyzer selftest green.
2. **C1 — intact + lost block 7 (6 runs)**: run order as §4.1; checkpoint
   after each run; a 6-run validity screen (floors, mechanism, health) gates
   C2.
3. **C2 — premature blocks 4–7 + matched no-fault partners (24 runs)**: run
   order as §4.1 (per block: the faulted runs and their partners); per-run
   attestation gate for the faulted runs, recorded no-fault health floors
   for the partners; screen after block 5 gates the rest.
4. **C3 — supporting batch (5 runs)**: profile restores per set (§5.2);
   restore the family profile after the batch, assert it (mismatch = STOP),
   and record it.
5. **C4 — wake-and-verify (22 runs, 2026-10-13 (m))**: §4.4 order — the
   intact/loss family (`none` → `loss_all` per block) then the premature
   family (per block `none` → `premature10`); single arm D from
   `rq3snd_frozen2` @ `541fb22` (the only tree with the wake code); the
   reused pilot ordinals 1–3 are never relaunched; per-run label check +
   predicate before every launch.
6. **Analysis**: `completion-lost` on the 7-block set (with the recorded
   block-4 exclusion; pass the loss set plus the 21 `none` runs for E-L4),
   `completion-intact` (the 21 `none` runs; pooled backends/strata),
   `completion-premature` — E-P1 (new faulted runs), E-P2 (7 blocks),
   E-P3 (7 seed-matched pairs) — and `completion-support` tables
   (E-S1…E-S3); with the wake stage included, add the wake input sets and
   the E-W1/E-W2/E-W3 reads (§7.5, `run_matrix.md` C4); then `results.md`
   and the thesis-facing tables.
   **Analyzer exit codes (`completion-intact` / `completion-lost`, also
   documented in `run_matrix.md`):** **0** = every gated component passes
   with no NA (lost: E-L1, E-L2, E-L3 and the E-L4 recorded-floor
   conformance; intact: E-I1 and the E-I4 conformance); **2** = a gated
   component failed or is NA (a report signal — NA ≠ stop); **3** = analyzer
   error. The E-I4/E-L4 floor is reported exactly as recorded (16/18 →
   `none_cell_healthy=false` where it applies) as a qualification of the
   recorded set: conformance requires the recorded outcome reproduced plus a
   clean block 7, so a green verdict remains reachable and the qualification
   never touches the between-arm contrast.

Cost: 35 runs (+ the 22-run wake stage, C4 — 2026-10-13 (m)); ≈42 min per
matrix run (30 runs; the recorded spacing is
≈44 min) and ≈12–13 min per supporting run (5 runs, the recorded v2 set
spacing; the earlier ≈20–25 min estimate was conservative) plus reset and
screening overhead → ≈24–29 h wall time on `cloud-vm-rq3`; the wake stage
adds ≈16–17 h (22 runs ≈42 min each, sequenced after the matrix and the
supports; its identity dependency is the soundness tree @ `541fb22`, already
verified; the wake stage always launches from that reference tree — under
soundness-group drift its E-W contrasts are reported cross-build, §6). DRIFT contingency:
the corrective set (§6) is 84 matrix runs + 5 supports + the 22 wake runs
(always from `541fb22`) with its own ≈77–83 h budget, replacing — never
adding to — this path.
Stop rules as §9; runs are one-at-a-time with passive monitoring.

## 12. Implementation surface

1. `source/scripts/testing/rq3adm_p0_01_platform_identity.py` — captures and
   compares the deployed identity and admission-path surface vs the recorded
   reference, per group against that group's execution tree (timing /
   soundness / supporting-C3 — the trees the runs launch from; the operator
   tree is reported informationally and never causes DRIFT); emits
   `analysis/platform_identity.json`; exit codes: 0 MATCH /
   3 DRIFT (mirroring the family's stop conventions). Items with no recorded
   reference are reported `NOT_RECORDED` and the verdict output prints a
   summary line counting them (`NOT_RECORDED (informational): N items`).
2. `source/scripts/testing/rq3adm_p0_02_preflight.sh` — static checks
   (py_compile/pyflakes, `bash -n`), env-merge byte-identity re-proof for the
   arm/fault deltas (env files and launcher texts sourced from the execution
   trees; a skip when none are given), canonical-file hashes (`phases.json`,
   `current_state_integrated.env`), launcher negatives (wrong set, duplicate
   label, wrong profile hash). Execution-tree checks: matrix groups via
   `--exec-tree <path>` (repeatable) or `RQ3ADM_EXEC_TREES` (classification:
   frozen-manifest presence first, worktree basename as fallback; generic
   trees still assert the premature-delta contents when that file is
   present), the supporting/C3 group via `--support-tree` (default: the
   campaign tree the supporting launcher runs from; v2 env files + per-set
   archived profile hashes + family profile; no drop knob), with cross-tree
   byte-identity asserted only for the shared matrix arm/fault env files; the
   terminal summary line records every skipped check class.
3. `source/scripts/testing/rq3adm_p1_01_launch_run.sh` — guarded launcher for
   the five supporting runs: per-set profile hash assertion (restored from the
   set's archived snapshot, `compute_spike` rate + mix pinned), env
   composition (`rq3_direct.env` / `rq3_discovery.env` /
   `rq3_discovery_15.env`), per-set window/quota/client/pool parameters,
   per-run reset cycle, duplicate-label refusal, run attestation;
   `restore-family` installs a hash-verified family `phases.json` copy —
   `$RQ3ADM_FAMILY_PROFILE_FILE`, else the frozen trees' `phases.json` under
   `$RQ3ADM_FAMILY_TREES` (default `~/rq3tim_frozen`, `~/rq3snd_frozen2`;
   read-only), never a tree-local `git checkout` — validates it before
   touching the canonical file and asserts the installed hash against
   `analysis/canonical_hashes.json` (mismatch = STOP; 2026-10-13 (k)).
   `source/scripts/testing/rq3adm_p0_04_label_check.sh` — standalone
   pre-launch label check for the frozen-tree launchers (§5.1/§10; exit 3 =
   duplicate, STOP).
4. `source/scripts/testing/analysis/rq3/readiness_robustness.py` — extend
   with `completion-intact`, `completion-lost`, `completion-premature`
   subcommands (reusing `_timing_*` and `_soundness_*` machinery; 7-block
   acceptance; the recorded block-4 exclusion; `completion-premature`
   computes E-P1 on the 12 new faulted runs, E-P2 on the 7 blocks and E-P3
   on the 7 seed-matched pairs; no E-P4 handling) and a `completion-support`
   subcommand computing E-S1–E-S3 on the
   added replicates (ready → admit intervals, admitted → first flow, scale
   decision → usable capacity, gap-window nulls, poll quantization; per set,
   run-level); fixture-based selftest additions.
5. `tools/rq3_stratified_analysis.py` — multi-run aggregation per mode and
   stratum (campaign-level interval tables); `--json` output for the plan
   folder. The mode/rule axis is derived from the full composed env identity
   (A/B/C satisfied by the recorded arm compositions; matrix-vs-v2 separation
   by the composed snapshot's `MAX_DYNAMIC_COMPUTE` pin, so C never pools
   with the v2 discovery set), and a run folder given twice is refused
   (exit 3).
6. Docs: this file, [`run_matrix.md`](run_matrix.md), the `v3/README.md`
   family row, a one-line completion cross-reference in the Family-4/Family-5
   folders. Non-goals: no new env/phase files (`phases_override/` untouched),
   no controller/application changes, no thesis edits.
7. VM sync list (workstation → `~/efficient-storage-in-edge-scenarios` on
   `cloud-vm-rq3`, the campaign tree): the analyzer package
   `source/scripts/testing/analysis/rq3/` — `__init__.py`,
   `readiness_robustness.py`, and **`readiness_low_headroom.py`** (missing on
   the VM operator tree as of 2026-10-11; sha256 `56857833…`, present and
   identical in both frozen execution trees; `readiness_robustness.py` imports
   it via `from .readiness_low_headroom import ...`, verified by import) —
   plus `source/scripts/testing/rq3adm_p0_01_platform_identity.py`,
   `rq3adm_p0_02_preflight.sh`, `rq3adm_p0_03_analyzer_selftest.py`,
   `rq3adm_p0_04_label_check.sh`, `rq3adm_p1_01_launch_run.sh`, and
   `tools/rq3_stratified_analysis.py` (the preflight's runtime check imports
   it). **Ratified additions (2026-10-11 (g), from the VM pass):** the four
   campaign env files the preflight requires — `rq3rob_event_only.env`
   (`eefd5dab…`), `rq3rob_loss_all.env` (`ed756592…`),
   `rq3snd_premature_lead10.env` (`f5b0d894…`), `rq3snd_wake_verify.env`
   (`e01ac58c…`) — and the two analyzer selftests the preflight runs —
   `rq3tim_p0_02_analyzer_selftest.py` (`4f955071…`),
   `rq3snd_p0_02_analyzer_selftest.py` (`995f10ac…`).
   **C3 snapshot provisioning:** the supporting launcher resolves, per set
   and per glob in order (camp `*_rq3_direct_*` / `*_rq3_disc_*`; cell12
   `*_rq3_probe_cell12_direct_*` / `*_rq3_probe_cell12_disc_*`; disc15
   `*_rq3_disc15_*`), the **lexicographically first matching folder of that
   glob** and requires `phases_snapshot.json` **in that folder**; if the
   folder lacks the file the resolver moves to the **next glob** — never to a
   later folder of the same glob — and with no glob resolving the launcher
   STOPs (the P0 `c3_gate` reports the set UNDEFINED). The resolved file must
   satisfy the set profile (rate 3.0; 12.0 for cell12; mix
   `service_pressure` 0.9 / `feed_ranking` 0.05 / `content_lookup` 0.05).
   The recorded v2 copies live in the workstation repo
   `source/scripts/testing/metrics/` (19 folders: `rq3_direct_*`,
   `rq3_disc_*`, `rq3_disc15_*`; snapshot sha256 `702bc05196ae…` for
   camp/disc15) and must be synced into the campaign tree like the code (run
   folders are data). **C3 prerequisite resolved (2026-10-12):** the cell12
   archived profile snapshot is provisioned in the workstation repo at
   `source/scripts/testing/metrics/20260805_205423_rq3_probe_cell12_direct_1/phases_snapshot.json`
   (the recorded first cell12 run folder) — the camp snapshot's bytes with
   only the `compute_spike` rate changed 3.0 → 12.0, raw sha256
   `37bc546de326c6ea2e81597db616544e74dae4aa0efe3ec3f68ce096e6b771fa`; the
   P0 reference records that hash (`recorded_snapshot_sha256`) and the P0
   `c3_gate` resolves cell12 as MATCH. The file is a config-profile
   reconstruction, not a run artifact: the runs it governs are fresh
   executions — the launcher restores the profile and records each fresh
   run's own snapshot path and hash. This campaign tree is also the
   supporting/C3 EXECUTION tree (2026-10-11 (f)) — the synced files are
   exactly its execution surface; the frozen execution trees are never
   synced (they are the identity reference).

Validation before any VM run: all of §12.2 green, analyzer selftest green
(any red = STOP). No experiment executes during implementation.

## 13. Parked (explicitly no runs)

- **Wake-and-verify** — ~~parked~~ **un-parked 2026-10-13 (m)**: evaluated
  as the third story mode with the 22-run completion of §4.4 and the §7.5
  expectations (E-W1/E-W2/E-W3; `rq3snd_wake_verify*` pilot ordinals 1–3 of
  the `none`/`premature10` cells are reused, verified valid).
- **Premature leads 2 s and 5 s** — the recorded pilot runs remain as-is; the
  evaluated matrix value is the 10 s lead; no new runs, no lead trend.
- **Stopped robustness family** (`rq3_robustness_DO_NOT_CITE`) — archive
  only, never cited.
- **Storage-tier readiness** — out of scope (thesis boundary).

## 14. Changelog

- 2026-10-11 — pre-registration drafted from the approved consolidated RQ3
  design: 7-block completion of the intact/lost cells (+1 block each),
  premature 10 s lead extended to 7 seeds (+4 each), supporting
  intact-source sets raised to seven (+5 runs), total 23; P0
  platform-identity gate with a full re-run contingency; leads 2/5 s and
  wake-and-verify parked.
- 2026-10-11 (review round, same day) — review-driven corrections with the
  design frozen (cells, 23 runs, seeds, orders unchanged): true rotation
  counts (§4.1), per-set seed provenance (2007 not globally unused; 6307
  newly assigned), E-P1 scoped to the 12 new runs with the recorded band
  labels and the restored C immunity gate (`000` ≤1/run ∧ ≤0.2 % of offered),
  E-P3 restored to the certified one-sided criterion, E-I4/E-L4 restored to
  the recorded run-level H-T3 gate, E-L1/E-L2/E-L3 accept counts restored to
  the recorded H-T fractions, E-I1 regime note, B-row mechanism fix,
  P0 UNDEFINED/off-path rules, corrective-matrix budget (≈46–50 h),
  E-S1/E-S2 restated as direction/consistency checks, `completion-support`
  named, question wording aligned to the thesis, matrix/README aligned.
- 2026-10-11 (b) — seven-seed standardisation: +12 matched no-fault
  partner runs for the premature condition (35 new runs total); E-P4
  retired.
- 2026-10-11 (c) — review-round implementation fixes (no gate, cell, seed or
  count changed): §5.1/§10 frozen-tree label-check enforcement
  (`rq3adm_p0_04_label_check.sh`, §12); §6 timing-image waiver sentence
  (timing-reference identity = recorded commit/worktree + admission-path
  hashes; the image half waived in the record — reported semantics revised in
  (d)); §11 analyzer
  exit codes for `completion-intact`/`completion-lost` with the recorded
  E-I4/E-L4 qualification reading (16/18 → `none_cell_healthy=false`;
  conformance = recorded outcome reproduced + clean block 7; NA ≠ stop);
  `run_matrix.md` analysis inputs/exit codes/block-7 reading and the
  soundness seeds-table alignment.
- 2026-10-11 (d) — second review-round implementation fixes (no gate, cell,
  seed or count changed): the §6 timing-image item now reports **WAIVED**
  (explicit, provenance-carrying, non-blocking) for the timing group only —
  the (c) UNDEFINED-and-blocks reading left the primary path unreachable on
  the record as it stands; `tools/rq3_stratified_analysis.py` rule axis
  re-derived from the recorded env compositions (A/B/C satisfied by the
  actual keys: A `rq3sat_direct`+`rq3rob_event_only` fallback 130; B
  `rq3sat_direct` fallback 20; C `rq3sat_discovery` discovery/10 s poll with
  no fallback key — C's composition records no 20 s fallback), with
  matrix-vs-v2 separation from the composed snapshot's `MAX_DYNAMIC_COMPUTE`
  marker (12 vs 6), so C never pools with the v2 discovery set; the preflight
  fixture exercises all three regimes plus `wake_verify`, the v2 sets and the
  locally recorded v2 snapshots; duplicate run folders are refused (exit 3);
  `run_matrix.md` label convention qualified to the campaign-tree launcher and
  the mandated `rq3adm_p0_04_label_check.sh` invocation added to the C1/C2
  sections; the `completion-support` console summary prints the descriptive
  E-S3 status (no stale pass key); the VM sync list (item 7).
- 2026-10-11 (f) — third review-round implementation fixes (no gate, cell,
  seed or count changed): the supporting/C3 group becomes an explicit
  execution group (§6 sentence added; `--support-tree`, default the campaign
  tree the C3 launcher runs from; validated against the C3 record — the v2
  env files `rq3_direct.env` / `rq3_discovery.env` / `rq3_discovery_15.env`
  by CR-stripped hash and the per-set archived profile hashes the supporting
  launcher asserts, with the drop knob deliberately not part of its surface);
  the preflight runs the same support checks via the P0 module, classifies
  exec trees by frozen-manifest presence first (basename fallback; generic
  trees still assert the premature-delta contents when present), keeps the
  cross-tree byte-identity assertion to the shared matrix arm/fault env files
  only (the supporting-set files legitimately differ across trees — F1), and
  sources the env-merge proof's env files and launcher texts from the
  execution trees only (never the operator tree — F2); the terminal preflight
  summary line now records every skipped check class; the verdict output
  prints a `NOT_RECORDED (informational): N items` summary line and the
  timing-image search is scoped to the timing execution tree (operator-tree
  candidates are informational and never upgrade the item).
- 2026-10-11 (g) — fourth review-round implementation fixes (no gate, cell,
  seed or count changed): the P0 verdict is stage-scoped (§6 sentence;
  `c1_c2_gate` / `c3_gate` fields with per-stage item lists, overall verdict =
  conjunction; a support-group UNDEFINED — e.g. the still-missing per-set
  archived snapshots — blocks only C3 and never C1/C2, and the console prints
  both stage readings); the preflight's rule-axis fixture is
  machine-independent (embedded composed-identity fixtures; recorded v2-set
  snapshots validated only as an optional extra, with leakage flagged only
  inside the v2-set globs — legitimately recorded campaign snapshots such as
  `rq3sat_camp_*` are never flagged); the P0 support check resolves each
  set's snapshot exactly as the supporting launcher does (per glob in order,
  the lexicographically first matching folder; the file must sit in that
  folder or the resolver moves to the next glob; the P0 selftest covers the
  fall-through and the no-resolution blocking paths); §12.7 sync
  list completed with the ratified env files and analyzer selftests plus the
  C3 snapshot provisioning and the cell12 open prerequisite; run_matrix P0
  invocations documented with `sudo -n` (run-folder snapshots are root-owned
  600).
- 2026-10-12 (h) — C1 stage-screen amendment (no cell, seed or count
  changed): the screen found the E-I1 gated leg degenerate in this run set —
  the ready→admission interval (`app_ready_ts→admitted_ts`) reads ~0.000 s
  for all three arms across the intact seven-block set — while the mechanism
  itself behaved as expected (the service-log trace shows C's ≈2.9 s
  quantization and the adjacent legs separate: spawn→first-success medians
  A 13.19 / B 13.15 / C 15.36 s; spawn→first-routed 74.58 / 73.97 /
  81.13 s; recorded same-regime anchor 11.27 vs 17.70 s, exact p = 0.0005).
  §7.1's gated intact expectation is therefore re-scoped to the **spawn →
  first successful response** interval, stratified by start-up class,
  directional (A and B earlier than C by median; C later than A/B by at most
  one 10 s check period), citing the recorded anchors; the ready→admission
  leg is recorded as unmeasurable in this build (report note only; the
  service-log diagnostic and the earlier regime-note attribution — d = −0.837
  belongs to the adjacent admit→first-routed interval — are retained). The
  analyzer evaluates the new leg (the old leg stays as an informational
  line). Block-7 disposition: the three flagged block-7 runs
  (`rq3tim_none_reconcile_7`, tail breach 3.84 %;
  `rq3tim_loss_all_reconcile_7`, control tail 6.50 %;
  `rq3tim_loss_all_event_only_7`, muted degradation 2.78 %) are quarantined
  as `<label>_void` and re-run under their planned `_7` labels (the recorded
  §9 mechanic; the analysis treats the fresh run identically to any planned
  run and never assumes its outcome — if the fresh numbers differ, results
  report them as fresh evidence).
- 2026-10-11 (e) — P0 scoping fix after the VM audit (no gate, cell, seed or
  count changed): the platform-identity comparison is per group against that
  group's EXECUTION tree (§6 sentence added; timing `~/rq3tim_frozen` vs the
  recorded timing references, soundness `~/rq3snd_frozen2` vs the recorded
  soundness references), the operator tree is informational
  (`required=False`, labelled "operator tree — not an execution surface") and
  can never cause DRIFT; a group's execution tree absent is UNDEFINED and
  blocks, retiring the operator-tree substitution path; the preflight's
  drop-knob and campaign env-file checks (plus each execution tree's
  `phases.json` copy, byte-identical `57bccc12`) run against the execution
  trees via `--exec-tree`/`RQ3ADM_EXEC_TREES`, with an explicit SKIP — never a
  silent PASS — when none are given; the §12 surface list gains the VM sync
  list (the analyzer's missing `readiness_low_headroom.py` dependency
  included).
- 2026-10-12 (i) — C3 support-stage prerequisite resolved (approved Option A;
  no gate, cell, seed or count changed): the cell12 set's archived profile
  snapshot — the one open constituent of the §12.7 sync list — is
  provisioned as a config-profile reconstruction (the camp snapshot's bytes,
  `compute_spike` rate 3.0 → 12.0; raw sha256 `37bc546d…`) in the recorded
  first cell12 run folder (`20260805_205423_rq3_probe_cell12_direct_1`); the
  P0 `SUPPORT_SET_SPECS` reference now records that hash (the NOT_RECORDED
  class reports 0 items; its selftest expectation updated), and the P0
  support surface resolves all three sets as MATCH on both ends. The runs
  the file governs are fresh executions.
- 2026-10-13 (j) — C2 stage-screen evidence-capture fix (no gate, cell, seed
  or count changed): the recorded-era run folders (blocks 1–3, Oct 3–4)
  contain no `controller_lan{1,2}.log` — that capture was added later — so
  the log-based E-P1 gates read `CHECK VIOLATION` = 0 and failed 6 of the 9
  recorded runs for `event_only`/`hybrid`, reporting E-P1 cell assessability
  4/7 where the plan requires ≥5/7 (all 12 new runs pass every gate).
  Amendment: when a run folder carries neither controller LAN log, the
  log-based gate (`check_violation_ge_1` for A/B, `zero_check_violations`
  for C) becomes **not evaluable** — reported explicitly in the per-run
  entry (`not_evaluable_logs_absent: true` + reason, plus the
  `E-P1.not_evaluable_runs` list) and excluded from `gates`/`failed` — never
  silently passed and never failed; with at least one log file present the
  gate evaluates exactly as before. This is era-agnostic and matches the
  recorded-runs attestation rule above. Expected post-fix E-P1 cell counts:
  `event_only` 7/7, `hybrid` 7/7, `reconcile` 6/7 (all assessable) — the
  b2 reconcile `zero_pre_bind_successes` signature is unaffected: it is
  computed from the archived client rows and the service-log spawn/bind
  times, not from the controller logs, and stays a reported failure.
- 2026-10-13 (k) — `restore-family` made tree-agnostic (no gate, cell, seed
  or count changed): it previously restored the family profile with
  `git checkout -- source/scripts/testing/phases.json`, which assumes HEAD
  carries the family profile — true in the frozen execution trees, false in
  the campaign/operator tree, where the checkout reverted the working tree to
  a non-family copy and then failed the assertion (exit 1). The restore now
  installs a byte-identical verified family `phases.json` (sha256
  `57bccc12…`) from, in order, `$RQ3ADM_FAMILY_PROFILE_FILE` or the frozen
  trees in `$RQ3ADM_FAMILY_TREES` (default `~/rq3tim_frozen`,
  `~/rq3snd_frozen2`; read-only — the frozen trees are never modified),
  validates the source before touching the canonical file, asserts the
  installed hash against the preflight-recorded `analysis/canonical_hashes.json`
  (falling back to the built-in recorded hash when the record is absent) with
  STOP on mismatch, and keeps writing the `analysis/family_profile_restore.json`
  evidence record. The C3 runner's recovery (the operator tree's `phases.json`
  at `57bccc12…`, evidence in that record) is the recorded starting point.
- 2026-10-13 (l) — C3 supporting-screen leg re-scope (no gate, cell, seed or
  count changed; mirrors the 2026-10-12 (h) amendment, same root cause): the
  just-run `completion-support` screen found E-S1's registered ready → admit
  leg degenerate on the camp runs and E-S3's on the disc15 run — per-backend
  `app_ready_ts == admitted_ts` (0.000 s) — the documented instrument
  degeneracy, not a mechanism deviation (sources and handover read correctly;
  E-S2 passed unchanged: direct 1.873 s vs discovery 8.984 s, direction 4/4,
  anchors fine). Amendment: E-S1's gate rides the measurable **spawn → first
  successful response** leg with the registered per-backend direction style
  (C3 probe on the two camp runs: direct 1.888/1.970 s LAN1 and 2.539/1.598 s
  LAN2 vs discovery 8.894/8.655 s LAN1 and 3.529/3.663 s LAN2 — 4/4 clean,
  discovery later by approximately its poll wait; the every-backend form is
  used, not the median form), keeping the source-vocabulary checks gated; the
  registered leg and its band readings are reported in a `ready_to_admit_leg`
  note and never gate. E-S3 keeps its descriptive band check; when the
  registered leg is degenerate the band check is not assessable and is
  reported as a note (the out-of-band descriptive finding is reserved for a
  measurable reading).
- 2026-10-13 (m) — **wake-and-verify un-parked** (decision 2026-10-13; no
  gate, cell, seed or count changed for A–C): the story is reframed to the
  operational trio — **event only / periodic / event + confirmation** — with
  the recorded `hybrid` retained as the **recovery-without-verification
  control** (it recovers loss but is fooled by a false claim); the four-rule
  matrix (`event_only`, `hybrid`, `reconcile`, `wake_verify`) stands as the
  evidence, the story is told in three. Mode D becomes a first-class matrix
  rule with the frozen semantics (the `app_ready` event wakes an immediate
  probe; admission requires the probe to pass; the same 20 s event-absence
  fallback applies) composed as direct base + `rq3snd_wake_verify.env`
  (§5.1). The **22-run completion** (§4.4) runs from `rq3snd_frozen2` (the
  only tree with the wake code): 7 intact/loss `none` + 7 `loss_all` (seeds
  5201–5207, ordinals 8–14 — the wake `none` cell's second ordinal family;
  the launcher refuses duplicate labels) + 4 `premature10` + 4 `none`
  partners (seeds 6304–6307, ordinals 4–7), with the pilot ordinals 1–3
  (seeds 6301–6303) **reused after read-only verification** (all six reused
  runs `valid: True`; attestations resolved `READINESS_WAKE_VERIFY_MODE=probe`
  / `READINESS_EVENT_FALLBACK_S=20`). Harness preflight passed read-only: the
  frozen launcher's case branches accept `wake_verify` × {`none`,
  `premature10`, `loss_all`} (`rq3rob_loss_all.env` already wired), the
  standalone label check runs before every launch, and the stratified tool
  derives `wake_verify:<fault>` from the composed identity (no tool change
  needed). New expectations (§7.5): **E-W1** wake earlier than periodic per
  primary stratum on the (h) leg (gated; wake-vs-`event_only` near-tie
  descriptive), **E-W2** lost paired slow-share delta ≤2 pp in ≥5/7 (gated)
  with the recorded `probe_fallback` mechanism and the ≈21 s hybrid timing
  anchor, **E-W3** premature immunity + one-sided paired damage (gated);
  `completion-premature` additionally reports the gated A-vs-D damage
  contrast and the descriptive D-vs-C near-tie. Analyzer + selftest updated;
  leads 2 s / 5 s stay parked (§13).
- 2026-10-13 (n) — (m) review-round documentation fixes (no gate, cell, seed
  or count changed; no run impact — the live C4 runner already used the
  correct protocol and `none`-first order): the exact working label-check
  protocol replaces the bare invocation in `run_matrix.md` (C1/C2/C4 and the
  label convention) — from the operator tree,
  `rq3adm_p0_04_label_check.sh --tree <execution-tree> <label>` (script gains
  a repeatable `--tree <path>`, default its own tree) plus the independent
  predicate `find <execution-tree>/source/scripts/testing/metrics -maxdepth 1
  -name '*_<label>'` (expected empty); per-family guard facts stated (the
  timing launcher @ `852a8a3` predates the duplicate-label guard — C1 relies
  on the check + predicate; the soundness launcher @ `541fb22` carries its
  own refusal — C2/C4 have both); the C4 premature-family tables now read
  `none` (block-first) → `premature10` and every C4 order statement matches
  plan §4.4; §6's corrective set and §11's cost now include the 22-run wake
  stage (≈16–17 h; DRIFT total ≈77–83 h; identity dependency the soundness
  tree @ `541fb22`, verified).
- 2026-10-13 (o) — DRIFT-clause coherence + `--tree` repeatability (no gate,
  cell, seed or count changed; no run impact): the wake stage **always
  launches from its reference tree @ `541fb22`** and is never re-launched on
  any other build; under soundness-group drift the corrective A/B/C matrix
  runs on the deployed build while the wake stage still runs from `541fb22`,
  and every E-W contrast is then reported **cross-build** (stated in
  `results.md`); timing-group drift leaves the wake stage unaffected
  (§6/§11). E-W1 records its **cross-tree** provenance (wake = soundness
  tree, `event_only` / periodic intact = timing family; same regime and
  readiness criterion, P0-verified per tree; §7.5).
  `rq3adm_p0_04_label_check.sh --tree` is genuinely repeatable: every given
  tree is scanned (one `scanned:` line per tree, order preserved, exact
  repeats de-duplicated), the label is refused if **any** tree holds it
  (exit 3), any invalid tree/path exits 2 before scanning, and a repeated
  `--tree` accumulates — never silently last-wins.
- 2026-10-15 (p) — **E-W screen executed and integrated** (analysis-only;
  no gate, cell, seed or count changed): the three wake screens
  (`completion_intact_wake.json`, `completion_lost_wake.json`,
  `completion_premature_wake.json`) read the §4.4 completion — C4
  delivered 22/22 valid, cell-exact, restart-free (2026-10-13 →
  2026-10-14; `campaign_log.md` C4) — and are integrated into
  `results.md` §2.5 with the thesis D slots filled. Readings: E-W1 intact
  direction holds in the fast class (D 4.01 s n = 41 vs A 4.08 s
  near-tie, +0.07 s; C 9.98 s, D earlier by 5.97 s) while the slow
  stratum is empty for D — the ~10 s bind stall was universal in the
  September runs (10.0–10.4 s) and absent in every October run (0/41
  backends ≥ 5 s; max 0.089 s) — so the recorded E-W1 pass stays false,
  read on the strata that contain evidence and reported in the thesis as
  an era-scope limitation; E-W2 lost no-harm 7/7 paired blocks ≤ 2 pp
  (median −0.4 pp) with `probe_fallback` 44/44; E-W3 premature damage
  median −0.9 pp (6/7 ≤ 2 pp) with the gated A−D contrast +16.86 pp,
  7/7 positive, p = 0.00029, δ = 1.0, and claim → first 10.99 s vs
  periodic 19.47 s. The recorded screen flags (E-W2 NA on the two
  dropped partner tails; E-W3 6-pair median on the b1 drop) are
  qualified under the **author ruling (2026-10-14)** — marginal 2–4 %
  variation is a note, not a drop — which re-includes E-W2 b2/b5 and
  E-W3 b1; the b5 A-pair breach (8.93 %) stays dropped. Three scenario
  figures planned for the RQ3 results section (F1 intact intervals /
  F2 lost outcome / F3 premature damage at the 10 s lead; four modes
  each; `source/scripts/testing/analysis/rq3/scripts/generate_thesis_figure.py`).
