# RQ2 Extension — Part D Addendum: Compute-Lock Onset Bracketing and Treated-Arm Expression (`rq2pd`)

**Date**: 2026-10-02 · **Status**: 📋 **draft — awaiting the review gate; frozen by the FREEZE-4 commit (§7)** · **Parent package**: [experiment_plan.md](experiment_plan.md) · [run_matrix.md](run_matrix.md) · [results.md](results.md) · **Predecessor**: [partc_addendum.md](partc_addendum.md) (CLOSED — "stop + record", 2026-09-28)

> **Continues, does not amend.** Part C is CLOSED; its probe ladder locked
> at 3.0 and the treated arm did not express there, while the bounded
> diagnostic pair @ 2.5 showed a real but unstable signal. This addendum
> pre-registers **Part D**: a bounded screening phase that **brackets the
> compute-lock onset inside (1.5, 2.5)** — never tested, because the Part C
> ladder jumped 1.5 → 3.0 — and re-tests treated-arm expression at the
> **lowest locking rung**, with a pre-registered confirmation rule before
> any campaign investment. It reuses the Part C gate framework (addendum §5
> / §7) and the identical platform configuration. **Probes are NOT
> evidence**; Part D contributes no evidence runs.

## 1. Why Part D (context, cited)

Part C established the two ends of the range and the failure modes:

- **`nn`@1.5 (P-0): no lock** — slow-share 0.999 %, p50 3.3 ms. The tier
  never queues; nothing to treat.
- **`nn`@3.0 (P-1): LOCK** — 99.0 % slow, p50 3.42 s, 24 017 timeouts;
  **`cf`@3.0 (P-4) cannot express it** — 4 compute adds per LAN fired,
  were admitted and served, yet PRE→POST p50 ratio 0.86 / 0.81,
  POST slow-share 99.2 / 96.7 %, completions ≈ the `nn` run. The
  constraint at 3.0 is **elsewhere** (not a compute-capacity deficit).
- **`nn`@2.5: LOCK** (97.0 % slow, p50 2.79 s); **`cf`@2.5: real but
  unstable expression** — lan2 PRE→POST ×21.4 (PRE p50 ≈ 1.87 s → POST
  ≈ 0.087 s, minutes 3–5 at 3–4 ms) yet lan1 ×0.76 (never collapsed),
  lan2 relapsed from minute 6, and lan1's added nodes were torn down
  mid-episode by the node-registry liveness cull (14:22:48–14:24:50).

Two mechanisms are recorded (Part C record): **(i) registry liveness
cull** — "seen" does not track served traffic; **(ii) near-capacity
assignment concentration** — a lane's whole per-minute demand lands on one
node, and relief appears only when the assignment splits load across two
added nodes. Open platform questions registered, not probed: liveness
semantics; assignment drivers.

**The gap this addendum closes:** the lock onset is somewhere in
**(1.5, 2.5]** and was never bracketed. The 2.5 rung sits deep in the
meltdown (the `nn` reference 97 % slow; the `cf` diagnostic 74 % blended
slow), where expression is assignment-gated; the shallow-lock
band just above onset is the remaining place where a **capacity-bound,
treatable** deficit could exist. Part D tests exactly that — with the
screening discipline *one run per rung; repeat only on a pass*:

- **one `nn` run per rung** classifies lock / no-lock (margins are large:
  1.5 → 0.999 % slow vs 2.5 → 97 % slow, so one run suffices);
- **one `cf` run at the lowest locking rung** tests expression;
- **repeats happen only for a pre-registered reason**: a pass triggers
  confirmation replicates; a diagnosed-partial failure (assignment
  starvation documented, §4) may be repeated once; a clean failure is not
  repeated — the negative is recorded;
- **validity failures** follow the Part C unified rule: document + the one
  relaunch allowance (parent plan §4.7).

Claim layers (parent plan §1.2): Part D targets **L1** (consequence
asymmetry under a real compute bind) and **L2** (no fixed policy
consequence-free). It does not re-test L3/L4.

## 2. Platform continuity — no rebuild

Part D touches **only harness/orchestration/docs artifacts, never the
running platform**. Verified at freeze (§7):

**Unchanged (byte-identical, verified at freeze):** controller code, all
four arm envs (`rq2_none.env`, `rq2_compute_first.env`,
`rq2_storage_first.env`, `rq2_bottleneck_aware.env`), the base phase files
(`phases_rq2_compute_bound.json`, `phases_rq2_data_bound.json`), the
`phases_rq2pc_cb.json` override **in its Part C-frozen state**
(`d40f5f59…`), the edge image, and all caps (storage 0.08 / edge 0.15 /
pool 12).

**New/changed files (the FREEZE-4 restricted diff = exactly these):**

| # | Path | Change |
| --- | --- | --- |
| 1 | `docs/operation/testing/experiment/rq2_extension/partd_addendum.md` | **NEW** — this file |
| 2 | `docs/operation/testing/experiment/rq2_extension/run_matrix.md` | §7 (Part D stage plan + checklist) + changelog row |
| 3 | `docs/operation/testing/experiment/rq2_extension/results.md` | Part D status row + changelog entry (no results yet) |
| 4 | `tools/run_rq2pd_probes.py` | **NEW** — staged screening launcher (§4; force-added, like the Part C probe launcher — `tools/` is gitignored) |

**Canonical-files rule (same exception as Part C):** the canonical
`phases.json` is untouched; the rate is edited **in place** in
`phases_rq2pc_cb.json` (the established named-regime override) and the file
is restored to the frozen state at Part D close. No new phase file is
created.

## 3. Run shape and arms

Exactly the Part C single-episode shape and configuration; **only the
episode demand rate and the arm env vary**:

| Element | Value | Why |
| --- | --- | --- |
| Phases | `phases_override/phases_rq2pc_cb.json`: baseline 60 s @1.0 · `compute_bound_episode` 600 s @**R** · recovery_gap 120 s @0.5 · demand_drop 420 s @1.0; episode mix `service_pressure: 1.0`, `client_fraction: 1.0` | Single variable = episode demand level; all windows identical to Part C runs → comparable with the 1.5/2.5/3.0 record |
| Arms | `nn` = `rq2_none.env` (no-op reference, lock classification); `cf` = `rq2_compute_first.env` (aligned treatment, expression test). `sf`/`ba` are campaign arms — **not** screening arms | `nn` proves the rate genuinely locks; `cf` tests whether the aligned action can express. `sf` is pre-registered no-benefit on `cb`; `ba` only matters for the campaign selector question |
| Caps | `STORAGE_CPUS=0.08 EDGE_CPUS=0.15 EDGE_MONGO_MAX_POOL_SIZE=12` | The Series-C allocation where the v3 `cb` bind is defined; changing caps redefines the rate's meaning |
| Platform env | `EDGE_MEMORY=512m WAN_RTT_MS=185 EDGE_MONGO_READ_PREFERENCE=secondaryPreferred VIP_DATA_PER_CONNECTION_FLOWS=1 OVERLOAD_CPU_PCT=30 OVERLOAD_PEAK_LATENCY_MS=2000` | Held-constant Part C regime — overload thresholds and the data path must match or the lock behaviour moves |
| Client/load | `CLIENTS=24 CONTENT_ITEMS=3000 USERS=100 TRAFFIC_DRIVER_MODE=open_loop INFLIGHT_WINDOW=1024 CURL_MAX_TIME=300 DRAIN_S=30 DATA_SEED=42 RANDOM_SEED=42` | Open loop is required to expose queueing (closed loop self-throttles); 300 s = the timeout definition; seeds keep rungs comparable |
| Launch | Direct make chain (same as Part C launcher): `setup_network create_clients setup_test_data run_experiment`, `OSKEN_ENV_OVERRIDE_FILE=../../rq2_env/<arm>.env`, `RUN_LABEL=rq2pd_*`, `SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1` | Established probe path; no `CELLS` entries, probes stay out of the campaign dataset |

## 4. Stage plan and decision tree (frozen)

**Rungs:** R1 = 2.0, R2 = 2.25, R3 = 2.4 (R3 only if R1 and R2 both no-lock).
**Label code = rate × 100** (`200`, `225`, `240`, `250`) — Part D only
(Part C codes were rate × 10), and `250` exists solely as the fallback
label `rq2pd_fb_cf_250`. `--start-at` resume: rate codes resolve to `nn`
rungs only; resuming at a `cf` step requires its exact label, and the
resumed step runs on the operator's assertion of the prior gate (recorded
in the probe log).

| Stage | Runs | Labels | Condition |
| --- | --- | --- | --- |
| **bracket** | `nn`@R1 → (`cf`@R1 first-lock case) → `nn`@R2 (if needed) → (`cf`@R2) → `nn`@R3 (if needed) → (`cf`@R3) | `rq2pd_r1_nn_200`, `rq2pd_r1_cf_200`; `rq2pd_r2_nn_225`, `rq2pd_r2_cf_225`; `rq2pd_r3_nn_240`, `rq2pd_r3_cf_240` | `cf` runs **only at the lowest locking rung** (R_s). If no rung locks → **STOP** (onset ∈ (2.4, 2.5]) |
| **repeat** (only for a diagnosed-partial `cf`) | 1 × `cf`@R_s | `rq2pd_rp_cf_<code>` | The screening `cf` failed **partially** with documented assignment starvation: per-minute per-backend shares show the failing lane's load served by ≤ 1 node during the failed window (instrumentation §5). One repeat maximum |
| **confirm** (only after a `cf` pass) | 2 × `cf`@R_s | `rq2pd_c1_cf_<code>`, `rq2pd_c2_cf_<code>` | Screening run (or its partial repeat) **passed** the signature (§5) |
| **fallback** (terminal diagnostic) | 1 × `cf`@2.5 | `rq2pd_fb_cf_250` | A **clean failure** at R_s (or failed confirmations / failed partial repeat). Reproducibility check of the only observed expression (Part C diag pair) |

**Decision tree (fixed):**

1. Bracket R1 → first lock? no → R2 → no → R3 → no → **STOP + report**
   (no `cf` runs; boundary reported).
2. First locking rung R_s → `cf`@R_s:
   - **pass** → confirm (2 runs): **confirmed** iff ≥ 2 of the 3 signature
     classifications pass with clean validity → campaign contingency (§6);
     otherwise → fallback → **STOP + report**.
   - **partial (assignment starvation documented)** → one repeat → pass →
     confirm as above; fail → fallback → **STOP + report**.
   - **clean fail** → fallback → **STOP + report**. (No `cf` is probed at
     deeper rungs for a pass: 3.0 shows non-expression, and 2.5 is revisited
     exactly once, by the terminal fallback run.)
3. The **fallback** run itself is never repeated; its outcome is recorded
   as the terminal diagnostic.

**Budget:** ≤ 8 launches in total, including the single validity relaunch
(bracket ≤ 4 · repeat ≤ 1 · confirm ≤ 2 · fallback ≤ 1; the reachable path
maximum is 7, so one relaunch still fits the cap; expected ≈ 6–8 h wall
clock). The launcher enforces the global counts via the durable event
ledger (`source/scripts/testing/metrics/rq2pd_events.jsonl` on the VM —
untracked); exceeding the allowance → abort + user decision (never a
silent relaunch).

## 5. Gates and acceptance criteria

**Validity battery (before any verdict counts; Part C §5):** 0 lane
blackouts · D1–D4 clean · I1 ≥ 5 000 completed/LAN (episode) · driver-side
drop-share ≤ 10 % per LAN · no unexpected status classes · lane
blackout/asymmetry screens.

**Lock gate (frozen, unchanged):** LOCK iff blended-LAN episode
slow-share ≥ 10 % AND blended completed-request p50 ≥ 1 s, over the full
600 s episode.

**Treated-arm signature (`cf`) — pre-registered ALL-of:**

1. **Add requirement** — ≥ 1 in-episode compute scale-up add per LAN
   (decision-log `scale_up` rows with a compute action, anchored to the
   episode window).
2. **Zero pre-episode fires** — no `scale_up` action row of any tier in
   the `baseline` window.
3. **B1 collapse ≥ 2× per LAN** — PRE = episode start → first compute
   `node_add`; POST = first compute `node_ready` + 120 s → episode end
   (fallback ready = add + 40 s); PRE→POST p50 ratio ≤ 0.5 on **both**
   LANs. A one-LAN pass is a flagged partial (triggers the §4 repeat
   rule only with documented assignment starvation).
4. **Recovery** — blended `demand_drop` slow-share ≤ 5 %.
5. **Added nodes served (M2)** — each added backend's served share > 0 in
   the run's client CSV `backend_id` distribution.

**`nn` persistent-deficit check (nn runs):** the final 120 s of the
episode still shows blended p50 ≥ 1 s AND slow-share ≥ 10 %.

**Mechanism instrumentation (read-only, recorded per run — attributes a
verdict, not a gate):**

- per-minute per-backend served share per lane (fan-out descriptor: share
  of episode minutes with ≥ 2 added backends serving; dominant-backend
  share);
- registry cull events (`[registry] mac=… not seen for N s — triggering
  removal` + removal executions) counted inside/outside the pinned
  windows;
- concurrency-gate engagement (edge log `request-concurrency gate
  engaged`; distinguishes connection/admission-limited meltdown from
  work-limited);
- per-server CPU descriptor (≈ 90–100 % of the 0.15 cap during a locked
  episode; reported).

An ungrounded signature extraction (missing artifact or column) is a
**validity flag** — it takes the unified-relaunch path and is never
recorded as a clean fail. **M2 zero matches are classified by the
id-space discriminator:** mapping evidence present (some client
`backend_id` matches a lifecycle node name) → genuine M2 fail (signature
item 5 fails); no mapping evidence at all → validity flag (ungrounded).

**Confirmation rule (frozen):** R_s is confirmed iff **≥ 2 of 3** `cf`
runs (screening-or-partial-repeat + 2 confirmations) pass the signature
with clean validity.

## 6. Confirmation and campaign contingency

- **Confirmed** → proceed to a campaign at R_s: the Part C campaign
  pattern (cells `nn`/`cf`/`sf`/`ba` × single-episode `cb`, 6 replicates
  each, seeds 42×5 + 43, staged 3+3, gates as Part C §7) instantiated at
  the confirmed rate and **pre-registered separately** (Part D.2: order
  CSV + FREEZE-5 record) before any campaign run. The campaign is the
  evidence; the Part D runs are selection runs and are not pooled into it.
- **Not confirmed** → **STOP + record**: the negative is bounded inside
  [onset, 3.0]; the recorded mechanisms and the boundary are the output.
  No campaign.

## 7. FREEZE-4 and execution sequence

1. **Restricted diff check:** exactly the four enumerated paths in §2
   differ; platform code, arm envs, and the phase file in its frozen state
   verified byte-identical (md5).
2. **VM sync + VM-side commit (Part C §9.2 pattern):** the four artifacts
   are synced to the VM working copy of record (`rq2-extension` branch),
   `tools/run_rq2pd_probes.py` force-added (`tools/` is gitignored),
   `py_compile` + `--plan` re-run VM-side, and the FREEZE-4 commit is
   made **on the VM**; md5s of the four paths and
   `phases_rq2pc_cb.json` (`d40f5f59…` state) recorded in
   [run_matrix.md](run_matrix.md) §7; no tag (tags follow execution
   records, Part C pattern).
3. **Pre-run (clean VM):** local↔VM sync verified; launcher dry-parse
   (`py_compile` + `--plan`); the deployed lock/signature checker smoked
   against stored Part C run folders (`*_rq2pc_pd_nn_025`,
   `*_rq2pc_pd_cf_025`, `*_rq2pc_p1_nn_030`) to validate parsers before
   any new run; clean-VM / free-disk checks as Part C.

   **Between-stage constraint:** every launch-stage invocation must start
   from the frozen phases file — after a stage that edited the rate, run
   `--restore-phases` before the next stage (and before any `--start-at`
   resume); the md5 preflight enforces this and aborts otherwise.
4. **Execution:** stage by stage per §4; each stage is classified before
   the next stage launches (runner-side; checkpoint pattern); the probe
   record is appended to the results.md **Part D — Record (`rq2pd`)**
   section; existing labels are never re-run; run folders are never
   deleted.
5. **Close:** `phases_rq2pc_cb.json` restored via
   `git checkout -- source/scripts/testing/phases_override/phases_rq2pc_cb.json`
   on the VM (launcher `--restore-phases`), md5 re-verified against
   `d40f5f592375360c76a1d55f4c168200`; records-only commit; outcome
   recorded in the results.md Part D record (confirmed → Part D.2
   pre-registration; not confirmed → negative record).

## 8. Risks and open items

- **Onset sharpness:** the lock knee may be steep and fall between rungs;
  R3 (2.4) narrows the band toward (2.5]; if all rungs no-lock, the
  boundary is reported without a campaign.
- **Known mechanisms may still gate expression at R_s** (registry
  liveness cull; assignment concentration). Part D does **not** fix them
  (no platform changes); the instrumentation attributes the outcome, so a
  failure is reported as mechanism-gated, not as an unexplained negative.
- **Small-n confirmation:** 3 runs at R_s cannot fully exclude a lottery;
  the campaign, if entered, carries the pre-registered ≥ 4/6 replicate
  rule, and a rate that fails there is reported as such.
- **Run-count discipline:** the launcher enforces ≤ 8 launches in total,
  including the single validity relaunch, via the durable event ledger
  (`source/scripts/testing/metrics/rq2pd_events.jsonl`); a missing/empty
  ledger with existing `*_rq2pd_*` run folders aborts for a manual
  decision, so a `/tmp` clean-up or reboot cannot silently reset the
  budget; the probe record mirrors the counts.

## Changelog

| Date | Change | Rationale |
| --- | --- | --- |
| 2026-10-02 | Addendum created (draft, pre-review): bracketing ladder (2.0 / 2.25 / 2.4), `cf` at the lowest locking rung, partial-repeat rule, confirmation rule (≥ 2/3), terminal 2.5 fallback, mechanism instrumentation, FREEZE-4 sequence | Part D pre-registration (user-directed, continues the Part C closure) |
