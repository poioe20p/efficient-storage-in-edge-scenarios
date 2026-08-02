# Post-Implementation Verification — RQ1 + RQ2 + RQ3

> **Status:** 🔵 In progress — V0 PASSED (2026-07-31), V1 PASSED (2026-07-31).
> **Scope:** Confirm the combined RQ1 (telemetry delivery), RQ2 (policy gate),
> RQ3 (readiness gate) implementation is "working as expected" before the RQ1
> evaluation campaign (and, later, RQ2/RQ3) proceeds.
> **Parents:** [`rq1_prepation.md`](../../../research_questions/v2/rq1/rq1_prepation.md),
> [`rq2_preparation.md`](../../../research_questions/v2/rq2/rq2_preparation.md),
> [`rq3_preparation.md`](../../../research_questions/v2/rq3/rq3_preparation.md).
> **Committed state:** `62b2238` (2026-07-31).
> **Execution:** runs on `cloud-vm` via the experiment-runner agent. Only
> `source/` is synced to the VM — `docs/` never needs to exist there. Where a
> gate needs files that live under `docs/` (RQ1's env/phase files), those files
> are copied to the VM explicitly (§4.2).
> **Gate names:** this plan's gates are **V0–V4** to avoid colliding with the
> RQ1 run matrix's own pre-flight gates G1–G3 (`v2/rq1/run_matrix.md` §7).

## 1. What "working as expected" means (4 layers)

Every gate below checks one or more of these layers. A gate **fails** if any
checked assertion fails.

- **L1 — Non-regression (defaults preserve pre-RQ behavior).** With defaults
  (`TELEMETRY_SOURCE=zmq`, `SCALEUP_POLICY=dual`, `READINESS_PROPAGATION=off`,
  `VIP_FLOW_ISOLATION=0`, `EDGE_FLOW_ISOLATION=0`), every behavior the three
  plans promised to preserve is preserved: no `ReadinessGate` object/thread,
  immediate `register_new_server_backend`, no `/ready` probe, no admission log,
  no `PolicyGate` interference, no `request_complete` emission, no
  `_vip_server_client_map` writes, no flow deletion, and the pre-existing
  decision-log row semantics (5-column `ts,network_id,window_id,action_type,
  action`) are unchanged. **Precision:** a few artifacts are EXPECTED-NEW on
  the canonical path because RQ1 introduced them unconditionally —
  `window_log*.jsonl`, the decision-log header line, always-published empty
  windows, and the `window_seq`/`window_id`/`overload` labels. These are
  classified as **expected additions** (schema-checked), not regressions.
  "Byte-identical" therefore means: RQ features absent AND preserved behaviors
  identical (schema + row semantics + no spurious rows), not bit-for-bit file
  equality. Note: a window where both tiers fire legitimately yields two
  `scale_up` rows sharing `window_id` with distinct `action`s — that is
  expected (one row per submitted alert), not a duplicate defect.
- **L2 — Per-RQ feature correctness.** Each RQ arm does what its plan's
  validation section specifies (RQ1 T12, RQ2 T9, RQ3 T12).
- **L3 — Cross-RQ artifact integration.** RQ2/RQ3 runs still produce RQ1
  artifacts (`window_log`, `delivery_log`, `decision_log`,
  `controller_env_snapshot.env`); RQ3 runs with `SCALEUP_POLICY=dual` keep
  RQ1/RQ2 decision semantics.
- **L4 — Measurement contract intact.** Artifact schemas match what the
  analyzers expect so every downstream tool runs and yields intended metrics.

## 2. Gate matrix

| # | Gate | What we run | Layers | Pass = | RQ scope |
|---|---|---|---|---|---|
| V0 | Static sanity | Imports, config defaults, env-file structure, wiring presence | L1 (static) | All §3.0 assertions | all |
| V1 | Canonical non-regression | One canonical default-config run (`current_state_integrated.env`, canonical `phases.json`) | L1, L3, L4 | All §3.1 assertions | all |
| V1b | No-scale counterfactual | One run with compute/storage scale-up + reserve DISABLED (`ablation_noscale.env`), same workload | L3 | §3.1b — confirm the system suffers (or not) vs V1 | all |
| V2 | RQ1 pre-flight | P1–P3 per `v2/rq1/run_matrix.md` + that doc's §7 gates | L2, L3, L4 | RQ1 T12 checks AND run-matrix §7 G1–G3 | RQ1 |
| V3 | RQ2 pre-flight | 4 arm×episode runs (§3.3) | L2, L3, L4 | RQ2 T9 checks | RQ2 |
| V4 | RQ3 pre-flight | 2 arm runs (direct / discovery) | L2, L3, L4 | RQ3 T12 checks | RQ3 |

**Ordering is mandatory:** V0 → V1 → V2 → then V3 and V4 (either order; they
are independent of each other — RQ3 uses `SCALEUP_POLICY=dual` and does not
build on RQ2-arm behavior). Do **not** start an RQ pre-flight while the
previous gate has any failure.

## 3. Per-gate assertion lists

### 3.0 V0 — Static sanity ✅ PASSED (2026-07-31)

1. ✅ `get_errors` across `source/sdn_controller`, `source/docker/edge_server`,
   `source/docker/local_state_server` → **no errors**.
2. ✅ All RQ1/RQ2/RQ3 modules import cleanly in the venv
   (`scaling_config`, `policy_gate`, `readiness_gate`, `telemetry/models`).
3. ✅ `scaling_config` defaults resolve correctly:
   `SCALEUP_POLICY=dual`, `READINESS_PROPAGATION=off`, `VIP_FLOW_ISOLATION=0`,
   `ACTION_BUDGET_PER_TIER=4`, `BOTTLENECK_CLASSIFY_MARGIN=0.05`,
   `EDGE_READY_PORT=5000`, `ADMISSION_LOG_PATH=/tmp/admission_log.csv`.
4. ✅ Arm env files differ **only** in the intended line (verified by diff):
   - RQ2: `rq2_compute_first.env` / `rq2_storage_first.env` /
     `rq2_bottleneck_aware.env` → differ only in `SCALEUP_POLICY`.
   - RQ3: `rq3_direct.env` / `rq3_discovery.env` → differ only in
     `READINESS_PROPAGATION`.
5. ✅ Phase files exist for all arms — RQ1 reuses the control group's
   `phases_stress_plateau.json` (2026-08-01 rebase: the per-RQ1
   `phases_rq1_delivery.json` is deleted), the RQ2/RQ3 phase files are under
   `source/scripts/testing/phases_override/`:
   - `source/scripts/testing/phases_override/phases_stress_plateau.json`
   - `source/scripts/testing/phases_override/phases_rq2_compute_bound.json`,
     `phases_rq2_data_bound.json`
   - `source/scripts/testing/phases_override/phases_rq3_compute_episode.json`
6. ✅ RQ3 wiring present: edge `/ready` route + `app_ready` flag,
   `request_complete` emission gated on `EDGE_FLOW_ISOLATION`,
   `SKIP_COUNTING_PATHS` includes `/ready`; aggregator whitelists
   `request_complete`; controller `process_flow_events`,
   `delete_vip_server_client_flows`, `_vip_server_client_map`,
   `_admit_compute_backend` / `_abandon_compute_backend`, gate injection in
   `main_n1.py`/`main_n2.py`.
7. ✅ RQ1/RQ2 wiring present: `_housekeeping_loop` spawned; `event_preserving`
   / `delayed_event_preserving` source modes; `_log_decision`; `PolicyGate`
   constructed and dispatched (`mode == "dual"` legacy path preserved).

### 3.1 V1 — Canonical non-regression (NEXT)

**Run spec (cloud-vm):**
- Launch (modeled on the RQ1 run-matrix §4 command; env-override paths resolve
  relative to `source/scripts`, the make cwd):
  ```bash
  ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \\
    nohup sudo -n STORAGE_CPUS=0.08 EDGE_CPUS=0.25 WAN_RTT_MS=185 RANDOM_SEED=42 \\
      make -C source/scripts setup_network create_clients setup_test_data run_experiment \\
      OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \\
      RUN_LABEL=v1_nonregression \\
      CLIENTS=24 CONTENT_ITEMS=3000 USERS=100 \\
      DATA_SEED=42 CURL_MAX_TIME=30 \\
      > /tmp/v1_nonregression.log 2>&1 &"
  ```
- `current_state_integrated.env` is the integrated baseline (Tier1 + reserves
  enabled). **Do not** set any RQ flag on the shell or in the env file:
  `TELEMETRY_SOURCE` unset (→ `zmq`), `SCALEUP_POLICY` unset (→ `dual`),
  `READINESS_PROPAGATION` unset (→ `off`), `VIP_FLOW_ISOLATION` unset (→ `0`),
  `EDGE_FLOW_ISOLATION` unset (→ `0`).
- Workload: canonical default `phases.json` (no `--phases-config`).
- The scale (`CLIENTS=24 CONTENT_ITEMS=3000 USERS=100`) is fixed for the run
  and MUST be recorded in the run log — any baseline value-diff (B3) is only
  comparable at the same scale.
- After completion, copy the run folder back locally for assertion review.

**Assertions (data source in parentheses):**

*L1 — RQ-feature absence:*
- A1. No `admission_log_lan1.csv` / `admission_log_lan2.csv` in the run folder
  (no gate → no admission log). *(run folder / controller container)*
- A2. No `request_complete` handling in the controller log — no
  `vip_server: request_complete: client flows deleted` and no flow-delete
  activity. (The `window_log` is real-window-only and never carries control
  events, so it is not a check source here.) *(controller log)*
- A3. `decision_log_*.csv` uses the **exact legacy format**: header
  `ts,network_id,window_id,action_type,action` (5 columns) and 5-column rows;
  no RQ2 columns (`compute_score_norm`, `selected_action`, `budget_cap`, …).
  **Row count == submission count:** one `scale_up` row per submitted alert, so
  a window where both tiers fire legitimately yields two `scale_up` rows
  sharing `window_id` with distinct `action`s (`ComputeAlert` / `DataAlert`) —
  expected, not a duplicate defect. `action` values come from the known
  submission set (`ComputeAlert`, `DataAlert`, scale-down / absent / reserve /
  cancel actions). No spurious rows. *(decision log)*
- A4. Observable gate absence (no provenance log exists in the default path —
  the RQ3 readiness-gate log is only emitted when `READINESS_PROPAGATION !=
  "off"`): no `ReadinessGate`/readiness worker thread (no `/ready` probe
  HTTP in controller logs, no `readiness_gate.enqueue` activity), no gate
  object in `_elasticity.readiness_gate`. *(controller log)*
- A5. Backend admission is immediate: the `[elasticity] compute: ... online`
  line and `[node_ready]` timing appear at spawn time (no gate delay), and the
  timing source is the legacy path (not `readiness_gate`). *(controller log)*

*L1/L3 — canonical health (platform still works):*
- B1. Full canonical workload completes end-to-end with no crash; standard
  artifacts present: `client_requests.csv`, `per_node_stats.csv`,
  `resource_stats_debug.csv`, `resource_stats.csv`, `controller_stats.csv`,
  `window_log_lan1/lan2.jsonl`, `decision_log_lan1/lan2.csv`,
  `controller_env_snapshot.env`, `aggregator_env_snapshot.env`,
  `phases_snapshot.json`, `elasticity_events.csv`, `container_events.csv`,
  `controller_lan1/lan2.log`. *(run folder)*
- B2. Elastic behavior fires in both directions: compute + storage scale-up and
  scale-down rows in `decision_log_*.csv` / `elasticity_events.csv`. *(run
  folder)*
- B3. **Value-level identity (mandatory, scope-aware):** a true pre-RQ1
  baseline run folder (golden-config-stability era) predates `decision_log` /
  `window_log` (RQ1-introduced), so value-level diffing applies **only** to
  signals present in both: `elasticity_events.csv` scale-up/down event shape,
  `container_events.csv` spawn/removal timing, and aggregate health (timeout /
  error rates, p95/p99 latency) — diffed **only if a same-scale baseline
  folder exists on the VM**. `decision_log`/`window_log` presence and schema
  are asserted against the plan specs (A3, L4), never against an old run. If
  **no** baseline folder exists, record the V1 run as the new canonical
  reference and state in the run summary that value-level identity is
  **asserted from the schema and presence checks, not diffed against a pre-RQ
  run**. *(analysis tools, elasticity_events, controller log)*

*Design-B (the single intended default-path change):*
- C1. Housekeeping ticker runs on `CONTROL_TICK_S`; scale-down + absent-node
  detection fire on the fixed ticker with the same outcomes as before (present,
  non-duplicated — one consideration per `window_seq`). *(decision log
  `scale_down` rows, controller log)*
- C2. `controller_env_snapshot.env` shows `TELEMETRY_SOURCE` unset/`zmq` and
  **no** RQ flags. *(snapshot env)*

**V1 PASS = A1–A5 all absent-checks pass AND B1–B3 AND C1–C2.**

### 3.1b V1b — No-scale counterfactual (causal check on scale-up benefit)

- **Purpose:** the V1 analysis shows compute scale-up benefit (per-node CPU
  distribution + static-tier 30 s-tail relief) but the causal claim is
  strongest with a counterfactual. V1b removes ALL capacity-adding mechanisms
  under the identical workload.
- **Run spec:** identical to V1 (hardware sim vars, `CLIENTS=24`,
  `CONTENT_ITEMS=3000`, `USERS=100`, canonical `phases.json`) with
  `OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/ablation_noscale.env`
  (`MAX_DYNAMIC_COMPUTE=0`, `MAX_DYNAMIC_STORAGE=0`,
  `STORAGE_PERSISTENT_RESERVE_ENABLED=0`; `SS_ENABLED=1` kept so only the
  capacity mechanisms are removed). Run label: `v1b_noscale`.
- **PASS/interpretation criteria (compare V1 vs V1b):**
  - If V1b shows materially worse service quality (error rate ↑, static-tier
    30 s tail dominates, p95/p99 latency ↑) and/or static-node CPU saturation,
    the counterfactual confirms scale-up benefit (system "clearly suffers"
    without it).
  - If V1b shows no degradation, the scale-up benefit at this scale is not
    material and is documented as such.
  - Report: total requests, error %, timeout %, p50/p95/p99, per-phase
    dynamic-vs-static split (dynamic should be ~absent), compute/storage CPU,
    server_count/storage_count, mechanism-exercise (expect NO spawns, NO
    reserve activations; Tier1 sel_sync may still appear).

### 3.2 V2 — RQ1 pre-flight (after V1)

> **2026-08-01 rebase note:** RQ1 now runs the control-group rebased config
> (see `v2/rq1/experiment_plan.md` changelog): workload
> `phases_stress_plateau.json`, `EDGE_CPUS=0.15`, caps 3/3, storage scale-down
> 30 s+3/5, compute scale-down 180 s/9. `phases_rq1_delivery.json` is deleted;
> the per-arm env files are rebased from `current_state_integrated.env`.

- **VM sync (required — the RQ1 env files live in `docs/`, which is not on
  the VM):** copy the RQ1 per-arm env files to the VM before the runs (§4.2).
  File list: `env/rq1_event_preserving.env`, `env/rq1_delayed.env`,
  `env/rq1_latest_state.env` (from
  `docs/operation/testing/experiment/v2/rq1/` — **the env files are
  in the `env/` subfolder**). The RQ1 workload is the control group's
  `phases_stress_plateau.json` under `source/scripts/testing/phases_override/`
  (repo-synced with `source/`, so no phases staging is needed).
- Runs P1–P3 from `v2/rq1/run_matrix.md`
  (`rq1_delivery_ep_preflight`, `rq1_delivery_delayed_preflight`,
  `rq1_delivery_ls_preflight`), using the exact launch command in run_matrix §4
  (incl. `STORAGE_CPUS=0.08 EDGE_CPUS=0.15 WAN_RTT_MS=185 RANDOM_SEED=42`,
  `CLIENTS=24 CONTENT_ITEMS=3000 USERS=100`). Arm C additionally sets
  `POLL_INTERVAL_S=30` on the shell. **Rewrite the `../../docs/...` path** in
  the §4 command to the VM-local sync target (§4.2) — it cannot resolve on
  the VM (no `docs/` there).
- **PASS criteria — RQ1 T12 implementation checks** (L2): models parse;
  aggregator publishes empty windows + monotonic `window_seq`; sources deliver
  in order; delayed release timing `delay_s ≈ DELAY_S` (30–40 s); ticker
  one-consideration-per-window; control events immediate (`window_seq=None`);
  poll-mode `_last_summary` advances through empties.
- **PASS criteria — run-matrix §7 pre-flight gates (MANDATORY, not optional):**
  - §7 G1 (tooling + reference sanity): all four RQ1 artifacts present for
    both LANs (`window_log`, `delivery_log`, `decision_log`, `ack_log` — the
    latter absent-by-design for Arm C); `rq1_delivery_per_run.py` runs clean;
    `rq1_delivery_comparison.py` renders the graph suite; Arm A meets criteria
    2 and 6 of experiment_plan.md §5.
  - §7 G2 (overload calibration): criterion 5 holds in **all three** pre-flight
    runs (≥ 30% of `compute_plateau` windows labeled `overload`); if not,
    adjust `CLIENTS`/`rate_per_client` or `OVERLOAD_*` via shell vars, then
    re-run the failing arm.
  - §7 G3 (drain + loss profile): Arm B shows **no `compute_plateau` window**
    `in-delay-at-run-end`; Arm C shows delivered fraction < 0.70.
- **Artifact-schema checks (L4):** `window_log`, `delivery_log`, `ack_log`,
  `decision_log` columns match §5 of `rq1_prepation.md`; `aggregator_env_snapshot.env`
  captured.
- **Out of pre-flight scope (documented):** aggregator-restart seq-resume
  continuity is not exercised by P1–P3 (between-run cleanup recreates the
  aggregator); it is validated by the RQ1 analyzer against the durable
  `window_log` and documented in the run summary.
- **Gate passes** → RQ1 evaluation campaign may start.

### 3.3 V3 — RQ2 pre-flight (after V2)

> **2026-08-02 supersession note:** the RQ2 evaluation campaign plan now lives
> at `v2/rq2/experiment_plan.md` (its pre-flight stage is this V3, RQ1 style).
> The authoritative per-arm env files moved to `v2/rq2/env/`
> (`rq2_compute_first.env` / `rq2_storage_first.env` / `rq2_bottleneck_aware.env`,
> rebased to caps 6/6 + budget 4 + the RQ2/Q6 scale-down calibration). The
> `controller_env_overrides/rq2_*.env` files referenced below are **superseded**
> — do not use them; point the pre-flight at the VM-synced `v2/rq2/env/` files
> (see `v2/rq2/run_matrix.md` §4 for the VM-local path rewrite).

- **Pre-flight matrix (covers both episode types + the fire-keyed scale-down
  case):**
  | # | `SCALEUP_POLICY` | Episode phase file | Why |
  |---|---|---|---|
  | 1 | `bottleneck_aware` | `phases_rq2_compute_bound.json` | classifier picks compute; T9.4 |
  | 2 | `bottleneck_aware` | `phases_rq2_data_bound.json` | classifier picks storage; T9.4 |
  | 3 | `fixed_compute_first` | `phases_rq2_data_bound.json` | suppressed-storage fire + fire-keyed scale-down protection (T9.8) |
  | 4 | `fixed_storage_first` | `phases_rq2_compute_bound.json` | suppressed-compute fire + storage-submits (T9.3) |
  Env files: `rq2_compute_first.env`, `rq2_storage_first.env`,
  `rq2_bottleneck_aware.env` — the **authoritative** copies at
  `docs/operation/testing/experiment/v2/rq2/env/`, VM-synced per §4.2 (the
  `source/scripts/testing/controller_env_overrides/` copies are **superseded** —
  do not use them). Phase files under
  `source/scripts/testing/phases_override/phases_rq2_<episode>.json` (already
  on the VM). Launch shape = the same make invocation as V1/V2 with
  `OSKEN_ENV_OVERRIDE_FILE=<VM-local path to v2/rq2/env/rq2_<arm>.env>` and
  `PHASES_CONFIG=phases_override/phases_rq2_<episode>.json`; scale fixed and
  recorded in the run log.
- **PASS criteria = RQ2 T9:** dual-equivalence — evidence is the **V1 canonical
  run** (a `SCALEUP_POLICY=dual` default run that already passed V1; no separate
  dual run is needed in V3); fixed-arm suppression with identical window
  advance; classifier +
  margin (tie → storage); budget exhaustion + `budget_used`/`budget_cap`/
  `reason` logging; one `scale_up` row per evaluated window with all 20
  columns (including `selected="none"`, budget-exhausted, cooldown windows);
  **fire-keyed scale-down protection** — no cooldown-gated `scale_down` row
  within `SCALEDOWN_*_COOLDOWN_S` of a window with `*_fired=1` (verified from
  the `*_fired` columns, run 3 above); flat-window inertness; RQ1 artifacts
  still produced unchanged.
- **Analysis tools (run locally on copied-back folders):**
  `rq2_bottleneck_validation.py`, `rq2_decision_analysis.py`,
  `rq2_relief_analysis.py`, `rq2_node_minutes.py` (under
  `docs/research_questions/v2/rq2/`).
- **Gate passes** → RQ2 evaluation campaign may start.

### 3.4 V4 — RQ3 pre-flight (after V2; independent of V3)

- **EDGE_FLOW_ISOLATION propagation (two paths — document in the run log):**
  `rq3_direct.env`/`rq3_discovery.env` set `EDGE_FLOW_ISOLATION=1`, which
  propagates to **dynamically spawned** edge servers via
  `compute_node_manager.py`; the **static** `edge_server_n1/n2` need
  `EDGE_FLOW_ISOLATION=1` on the **shell** when launching the network setup
  (RQ3 §9). Both must be set for the arm runs. Edge `BIND_PORT=5000`.
- Two arm runs using `rq3_direct.env`, `rq3_discovery.env`; phase file
  `phases_rq3_compute_episode.json`. Launch shape = the same make invocation as
  V1/V2 with `OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/rq3_<arm>.env`
  and `PHASES_CONFIG=phases_override/phases_rq3_compute_episode.json`; scale
  fixed and recorded in the run log. Confirm controller host → backend subnet
  `/ready` reachability **before** the first RQ3 run (RQ3 T12.11) — if not
  routable, add a documented host route.
- **PASS criteria = RQ3 T12:** probe quantization (`spawn_complete → admitted`
  ≈ app-startup + `[0, READINESS_PROBE_RETRY_S]` in `direct` vs + `[0,
  DISCOVERY_POLL_INTERVAL_S]` in `discovery`); identical `/ready` criterion
  (`spawn_complete → app_ready_observed` distributions overlap); `topology_host`
  no-starvation + backend in `host_attachment` at admission; flow isolation
  Checks A–D via `rq3_flow_validation.py`; **T12.7 — the client's `VIP_DATA`
  reply rule (`tcp_src=27018`) is NOT deleted** (MongoDB return paths intact);
  **T12.10 — the misconfiguration guard warns when `VIP_FLOW_ISOLATION=1` but
  no `request_complete` events arrive**; abandonment teardown (`result="abandoned"`
  row, IP released, container removed, no leak); admission-log schema §2.4.
- **Analysis tools (run locally on copied-back folders):**
  `rq3_admission_analysis.py`, `rq3_flow_validation.py` (under
  `docs/research_questions/v2/rq3/`).
- **Gate passes** → RQ3 evaluation campaign may start.

## 4. Execution notes

- **VM scope:** `cloud-vm` needs only `source/`. After pulling, verify
  `source/` matches `62b2238` (or the current origin/main) before runs.
- **Ordering:** a failed gate blocks the next. V3 and V4 are independent of
  each other but both require V2 to pass. Record results in §6; update this
  doc's status line on each change.
- **Analysis tools (run locally on copied-back folders; they live in `docs/`,
  not on the VM):**
  - RQ1: `rq1_delivery_per_run.py`, `rq1_delivery_comparison.py` under
    `docs/operation/testing/experiment/v2/rq1/analysis/`.
  - RQ2: `rq2_bottleneck_validation.py`, `rq2_decision_analysis.py`,
    `rq2_relief_analysis.py`, `rq2_node_minutes.py` under
    `docs/research_questions/v2/rq2/`.
  - RQ3: `rq3_admission_analysis.py`, `rq3_flow_validation.py` under
    `docs/research_questions/v2/rq3/`.
- **Cleanup:** per repo rules, temporary helper scripts are removed after use;
  transient client-request CSV/controller-log files are cleaned after the run
  summary is produced.

### 4.2 VM file-sync for gates that need `docs/`-housed config

Only the RQ1 pre-flight (V2) currently needs this — its env files live under
`docs/operation/testing/experiment/v2/rq1/env/`. Before the P1–P3 runs, copy
these to `~/efficient-storage-in-edge-scenarios/rq1_run_config/` on the VM
(kept out of `source/`, so it never pollutes the synced tree):

```text
env/rq1_event_preserving.env  → rq1_run_config/rq1_event_preserving.env
env/rq1_delayed.env           → rq1_run_config/rq1_delayed.env
env/rq1_latest_state.env      → rq1_run_config/rq1_latest_state.env
```

**Mandatory:** rewrite the launch command's `../../docs/...` path (run_matrix
§4) to resolve on the VM. From the `source/scripts` make cwd:
- `OSKEN_ENV_OVERRIDE_FILE=../../rq1_run_config/<env_file>`
- `PHASES_CONFIG=testing/phases_override/phases_stress_plateau.json` (the
  control group's workload — already on the VM via `source/`, no staging)

RQ3 config already lives under `source/scripts/testing/` (controller_env_overrides/
and phases_override/), so V4 needs no extra sync. **RQ2 is an exception
(2026-08-02):** its authoritative per-arm env files live at
`docs/operation/testing/experiment/v2/rq2/env/` (not on the VM) — copy
`env/rq2_{compute_first,storage_first,bottleneck_aware}.env` to the VM and
rewrite the launch path to the VM-local target before V3. Record the sync
target in the run log so the run is reproducible.

## 5. Artifact contract (L4 reference)

| Artifact | Produced by | Consumed by |
|---|---|---|
| `window_log_lan1/lan2.jsonl` + `ack_log_*.jsonl` | aggregator | RQ1 analyzers, overload universe (`ack_log` absent-by-design for Arm C) |
| `telemetry_delivery_log_lan1/lan2.csv` | controller delivery sources | RQ1 analyzers |
| `decision_log_lan1/lan2.csv` | controller `_log_decision` | RQ1/RQ2/RQ3 analyzers |
| `admission_log_lan1/lan2.csv` | readiness gate (RQ3 arms only) | RQ3 analyzers |
| `controller_env_snapshot.env` | run harness | arm-ground-truth for all RQ analyzers |
| `aggregator_env_snapshot.env` | run harness | `OVERLOAD_*`/`WINDOW_*` ground truth (RQ1) |
| `phases_snapshot.json` | run harness | episode-label join (post-hoc) |
| `client_requests.csv` (incl. `source_port` — RQ3-scoped column, may be absent in RQ1/RQ2), `per_node_stats.csv`, `elasticity_events.csv`, `container_events.csv` | traffic generator / collectors | latency, TFR, spawn/removal timing |
| `resource_stats_debug.csv`, `controller_stats.csv`, `controller_lan1/lan2.log` | collectors / controller | RQ3 flow-validation Check C, absence checks, overhead |

## 5.5 Generic control group

The scale-vs-no-scale contrast produced by the verification (recommended: the
plateau pair) is documented as the **generic control group** for RQ1/RQ2/RQ3 in
[`../control_group.md`](../control_group.md) (experiment-folder level) — each RQ
references it as its regular scenario baseline. Plateau rate is **locked at 5.0**
for subsequent runs; a validation run is pending.

## 6. Status log

| Gate | Status | Date | Notes |
|---|---|---|---|
| V0 | ✅ PASSED | 2026-07-31 | All §3.0 assertions verified locally |
| V1 | ✅ PASSED | 2026-07-31 | Run `20260731_220352_v1_nonregression`, exit 0. A1–A5/B1–B3/C1–C2 all green. Reference health: 19,262 req, error 1.87%, timeout 0%, p50 12.7 ms / p95 4.6 s / p99 5.05 s. No same-scale pre-RQ baseline on VM → recorded as new canonical reference (B3). |
| V1b | ✅ PASSED | 2026-08-01 | Run `20260731_233027_v1b_noscale`, exit 0. Treatment confirmed (0 spawns, 0 reserve). System clearly suffers without scaling: storage DB latency 3–6× worse (449 ms vs 96 ms in storage_storm_2), per-node compute CPU ×1.6–1.9, throughput −10%. Counterfactual confirms scale-up + reserve benefit. |
| V2 | ⏳ pending | — | RQ1 pre-flight P1–P3 + VM sync of RQ1 config (env/ subfolder) |
| V3 | ⏳ pending | — | After V2 passes |
| V4 | ⏳ pending | — | After V2 passes (independent of V3) |

**Known doc inconsistency (not a blocker):** `rq2_preparation.md` §5 describes
the RQ1 decision-log format as "5-column no-header", but the implemented
`_log_decision` writes a 5-column **header** in dual mode (V1 A3 asserts the
header). The code is authoritative; the RQ2 doc line is stale and should be
corrected during the RQ2 documentation updates.
