# RQ1 Delivery Semantics — Run Matrix

Part of [`experiment_plan.md`](experiment_plan.md). Detailed per-run
configuration for the RQ1 delivery-semantics campaign.

## 1. Campaign structure

| Stage | Runs | Purpose |
|---|---|---|
| **Pre-flight** | 3 (one per arm) | P1–P3 runs; gates G1–G3 (§7) |
| **Main** | 9 (3 per arm) | Replicated cross-arm comparison |

Run-label pattern: `rq1_delivery_<arm>_<suffix>` with
`arm ∈ {ep, delayed, ls}`. Run folder becomes
`<timestamp>_rq1_delivery_<arm>_<suffix>`.

## 2. Run matrix

| # | Label | Arm | `TELEMETRY_SOURCE` | Env override | Purpose |
|---|---|---|---|---|---|
| P1 | `rq1_delivery_ep_preflight` | A | `event_preserving` | `rq1_event_preserving.env` | Validate artifacts + tooling on arm A |
| P2 | `rq1_delivery_delayed_preflight` | B | `delayed_event_preserving` | `rq1_delayed.env` | Validate artifacts + drain timing |
| P3 | `rq1_delivery_ls_preflight` | C | `poll` | `rq1_latest_state.env` | Validate artifacts + loss profile |
| 1–3 | `rq1_delivery_ep_1..3` | A | `event_preserving` | `rq1_event_preserving.env` | Replicates |
| 4–6 | `rq1_delivery_delayed_1..3` | B | `delayed_event_preserving` | `rq1_delayed.env` | Replicates |
| 7–9 | `rq1_delivery_ls_1..3` | C | `poll` | `rq1_latest_state.env` | Replicates |

All runs: `CONTROL_TICK_S=10`, `DELIVERY_LOG_PATH=/tmp/telemetry_delivery_log.csv`,
`DECISION_LOG_PATH=/tmp/decision_log.csv`, Tier 1 / reserves / cross-region
disabled, platform **rebased from the control group** (2026-08-01): caps
`MAX_DYNAMIC_STORAGE=3`, `MAX_DYNAMIC_COMPUTE=3`, compute scale-down
`SCALEDOWN_COMPUTE_COOLDOWN_S=180`/`SCALE_DOWN_COMPUTE_REQUIRED=9`, storage
scale-down `SCALEDOWN_STORAGE_COOLDOWN_S=30`/`SCALE_DOWN_STORAGE_WINDOW_SIZE=5`/
`SCALE_DOWN_STORAGE_REQUIRED=3` (see `experiment_plan.md` §2).

## 3. Per-arm env files

This experiment folder's `env/` subfolder
(`docs/operation/testing/experiment/v2/rq1/env/`):

| File | Delivery-specific vars |
|---|---|
| `rq1_event_preserving.env` | `TELEMETRY_SOURCE=event_preserving`, `EVENT_POLL_INTERVAL_S=0.5` |
| `rq1_delayed.env` | `TELEMETRY_SOURCE=delayed_event_preserving`, `DELAY_S=30`, `EVENT_POLL_INTERVAL_S=0.5` |
| `rq1_latest_state.env` | `TELEMETRY_SOURCE=poll`, `POLL_INTERVAL_S=30` |

The shared block (capacity, scale-down, disable flags, `CONTROL_TICK_S`, log
paths) is intentionally identical across the three files — **rebased from
`current_state_integrated.env`** (control-group retune 2026-08-01) plus the
thesis-§2 disable flags; see `experiment_plan.md` §3. The old RQ1-only values
(`MAX_DYNAMIC_STORAGE=8`, `MAX_DYNAMIC_COMPUTE=12`,
`SCALEDOWN_COMPUTE_COOLDOWN_S=60`) are **removed** — the rebased block supplies
3/3 and 180s/9.

Rationale for `POLL_INTERVAL_S=30` with `WINDOW_S=10`: each poll sees the newest
of ~3 completed windows → ~2/3 of intermediate windows dropped, making the
"loss of intermediate evidence" axis measurable (matches the old poll-30 blind
spot). Rationale for `DELAY_S=30`: symmetric with the poll loss so delay-vs-loss
is a fair comparison.

**Launch mechanics:** `build_network_setup.sh` passes
`-e POLL_INTERVAL_S="${POLL_INTERVAL_S:-10}"` (Docker `-e` overrides the env
file), so Arm C must also set `POLL_INTERVAL_S=30` **on the shell** in the launch
prefix (see §4). The `OVERLOAD_*` thresholds are read by `build_network_1/2.sh`
from the shell, not from the controller env file — any calibration adjustment
(G2) is made via shell env vars in the launch command, identical across arms.

## 4. Per-run launch command

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n STORAGE_CPUS=0.08 EDGE_CPUS=0.15 WAN_RTT_MS=185 RANDOM_SEED=42 \
    make -C source/scripts setup_network create_clients setup_test_data run_experiment \
    OSKEN_ENV_OVERRIDE_FILE=../../docs/operation/testing/experiment/v2/rq1/env/<ENV_FILE> \
    RUN_LABEL=<LABEL> \
    PHASES_CONFIG=testing/phases_override/phases_stress_plateau.json \
    CLIENTS=24 CONTENT_ITEMS=3000 USERS=100 \
    DATA_SEED=42 CURL_MAX_TIME=30 \
    SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1 \
    > /tmp/<LABEL>.log 2>&1 &"
```

`OSKEN_ENV_OVERRIDE_FILE` is resolved relative to `source/scripts` (make cwd);
the `../../docs/...` path points at the per-arm env files in this v2/rq1 folder.
`PHASES_CONFIG=testing/phases_override/phases_stress_plateau.json` reuses the
control group's canonical workload (repo-synced to the VM with `source/`, so no
docs-housed phase staging is needed).

| Run | `<ENV_FILE>` | `<LABEL>` |
|---|---|---|
| P1 | `rq1_event_preserving.env` | `rq1_delivery_ep_preflight` |
| P2 | `rq1_delayed.env` | `rq1_delivery_delayed_preflight` |
| P3 | `rq1_latest_state.env` | `rq1_delivery_ls_preflight` |
| 1–3 | `rq1_event_preserving.env` | `rq1_delivery_ep_1`–`_3` |
| 4–6 | `rq1_delayed.env` | `rq1_delivery_delayed_1`–`_3` |
| 7–9 | `rq1_latest_state.env` | `rq1_delivery_ls_1`–`_3` |

**Scale (`CLIENTS`/`CONTENT_ITEMS`) is a calibration variable** — start at
`24 / 3000`; the pre-flight gate (below) decides whether to keep or adjust
before the main 9 runs.

**Per-arm extra shell env (added to the launch prefix):**
- Arms A, B: none extra.
- Arm C: `POLL_INTERVAL_S=30` (required — `build_network_setup.sh` `-e` default
  would otherwise force 10; see §3).
- All arms (G2 calibration only): `OVERLOAD_CPU_PCT=… OVERLOAD_PEAK_LATENCY_MS=…
  OVERLOAD_ERROR_RATE=…` as needed.

**Calibrated-value carryover:** any value changed during G2 calibration —
`OVERLOAD_*` shell vars, `CLIENTS`, `CONTENT_ITEMS`, or `rate_per_client` — MUST
be carried into the launch prefix / command of the **main 9 runs** (identical
across arms) and recorded in the run log; otherwise the main runs silently fall
back to un-calibrated values, invalidating criteria 5/6.

## 5. Phases (`phases_stress_plateau.json`, 1200 s — control group)

Reuses the validated control-group workload
(`source/scripts/testing/phases_override/phases_stress_plateau.json`); no
per-RQ1 phase file. The single sustained `compute_plateau` at rate 5.0 gives RQ1
a clean demand-shift boundary (baseline→plateau) for reaction latency and ~60
overload windows for observability; the 420 s `demand_drop` gives the
scale-down runway and drains Arm B's `DELAY_S` hold queue.

| Phase | Duration | Rate/client | Client frac | Mix focus | Purpose |
|---|---|---|---|---|---|
| `baseline` | 60 s | 1.0 | 0.1 | lookup 0.6 / feed 0.25 / pressure 0.15 | establish |
| `compute_plateau` | 600 s | 5.0 | 1.0 | feed 0.4 / pressure 0.3 / lookup 0.2 | induce overload + scale-up |
| `recovery_gap` | 120 s | 0.5 | 0.05 | baseline mix | post-plateau lull; A/B first scale-down lands here; drain Arm B hold queue (≥ `DELAY_S`+`WINDOW_S`) |
| `demand_drop` | 420 s | 1.0 | 0.1 | baseline mix | trigger scale-down (storage reclaim in-window); drain Arm B residual |

## 6. Between-run procedure

1. Confirm run artifacts collected (C3).
2. Cleanup so the **aggregator and controller containers are recreated** — this
   is required for a fresh `window_log.jsonl` (seq restarts), delivery log and
   decision log. Reuse the repo's cleanup (e.g. `cleanup.sh` / the cleanup make
   target) before the next `setup_network`.
3. Verify checkpoint C1 (fresh state) before launching the next run.
4. No controller restart mid-run (C2). No VM reboot between replicates unless
   state contamination is observed.

## 7. Pre-flight gate (must pass before the main 9 runs)

After the P1–P3 pre-flight runs are analyzed (gates G1–G3 below):

- **G1 — tooling + reference sanity:** all four RQ1 artifacts present for both
  LANs; `rq1_delivery_per_run.py` runs clean and `rq1_delivery_comparison.py`
  renders the graph suite; Arm A meets criteria 2 and 6. Criterion 6 (≥1
  scale-up/LAN) is verified here **under the SS-off/reserve-off config** — no
  control arm ran SS-off, so it is not assumed from control evidence.
- **G2 — overload calibration:** criterion 5 holds in all three pre-flight runs
  (≥ 30% of `compute_plateau` windows labeled `overload`). If not, adjust
  `CLIENTS`/`rate_per_client`, or the `OVERLOAD_*` thresholds **via shell env
  vars in the launch command** (`OVERLOAD_CPU_PCT`/`OVERLOAD_PEAK_LATENCY_MS`/
  `OVERLOAD_ERROR_RATE` — consumed by `build_network_1/2.sh`, not the controller
  env file; keep identical across arms), then re-run the failing arm's
  pre-flight. Plateau rate 5.0 stays **locked** (control-group decision); G2
  adjusts `OVERLOAD_*`/`CLIENTS`, not the rate.
- **G3 — drain + loss profile:** Arm B pre-flight shows **no `compute_plateau`
  window** `in-delay-at-run-end` (drain works; residual in-delay is limited to
  the final ≈ `DELAY_S/WINDOW_S`+1 windows — expected); Arm C pre-flight shows
  delivered fraction < 0.70 (loss is measurable).

## 8. Estimated wall-clock

~25–30 min per run (1200 s traffic + setup/teardown + artifact copy) →
pre-flight 3 runs ≈ 1.5 h; main 9 runs ≈ 4.5 h; total **≈ 6–7 h**, plus any
calibration re-runs.
