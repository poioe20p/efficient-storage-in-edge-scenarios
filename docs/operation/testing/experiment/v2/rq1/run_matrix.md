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
  nohup bash source/scripts/testing/rq1_launch_run.sh \
    <ENV_FILE> <LABEL> <SEED> [POLL_INTERVAL_S=30 for Arm C] \
    > /tmp/<LABEL>.log 2>&1 &"
```

The launcher `source/scripts/testing/rq1_launch_run.sh` encodes the canonical
make chain: open-loop driver (`TRAFFIC_DRIVER_MODE=open_loop`,
`CURL_MAX_TIME=300`, `INFLIGHT_WINDOW=1024`, `DRAIN_S=30`),
`PHASES_CONFIG=testing/phases_override/phases_rq1_stress_plateau.json` (rate
3.0), and the Mongo data-path block
(`EDGE_MONGO_READ_PREFERENCE=secondaryPreferred`, `EDGE_MONGO_MAX_POOL_SIZE=12`,
`VIP_DATA_PER_CONNECTION_FLOWS=1`). All knobs are make command-line variables
so they survive sudo `env_reset`. Arm C additionally passes `POLL_INTERVAL_S=30`
as the optional extra-args slot.

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
| `compute_plateau` | 600 s | 1.2 | 1.0 | lookup 0.35 / feed 0.2 / pressure 0.2 / upd 0.15 / agg 0.1 | induce overload + scale-up (rate + mix re-anchored 2026-08-05: ~35 DB ops/s/LAN, below RQ2's ~42 cliff) |
| `recovery_gap` | 120 s | 0.5 | 0.05 | baseline mix | post-plateau lull; A/B first scale-down lands here; drain Arm B hold queue (≥ `DELAY_S`+`WINDOW_S`) |
| `demand_drop` | 420 s | 1.0 | 0.1 | baseline mix | trigger scale-down (storage reclaim in-window); drain Arm B residual |
| `idle_tail` | 420 s | 0.05 | 0.05 | baseline mix | **Added 2026-08-05** — near-idle tail so the lossy arms (C poll, D sampled_push) observe a clean-idle window, the churn guard releases, and scale-down can arm/fire (C7 measurable for every arm). Fixes Arm C's zero-scale-down gate failure (`rq1_g2_armC_rerun`). |

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

---

## 9. RQ1 v2 matrix (final evidence — 20 runs)

Authoritative spec: [`rq1_v2_rework_plan.md`](rq1_v2_rework_plan.md). The
v1 9-run campaign above (§1–§8) becomes the **v1 / supporting record** once v2
completes.

**Structure:** 4 arms × 5 replicates = **20 runs**, 5 counterbalanced blocks
of 4 (seeds **2001–2005** = driver `RANDOM_SEED` base; distinct-order
verification — re-sample a block's seed on collision). Orders are recorded in
a **new** `counterbalance_order_v2.csv` (distinct from any prior order file).

| Arm | `TELEMETRY_SOURCE` | Env override | Suffix |
|---|---|---|---|
| A | `event_preserving` | `env/rq1_event_preserving.env` | `ep` |
| B | `delayed_event_preserving` | `env/rq1_delayed.env` | `delayed` |
| C | `poll` | `env/rq1_latest_state.env` | `ls` |
| D | `sampled_push` | `env/rq1_sampled_push.env` | `sp` |

**Launch (per run, cloud VM):** `TRAFFIC_DRIVER_MODE=open_loop
CURL_MAX_TIME=300 INFLIGHT_WINDOW=1024 DRAIN_S=30`; workload =
**`phases_rq1_stress_plateau.json`** (2026-08-04 G2 retune, Option A:
`compute_plateau` rate **3.0** — see retune note; a per-RQ1 copy of the
control group's `phases_stress_plateau.json`, which stays at rate 5.0 for the
control-group record). **Each run's launch prefix
sets `RANDOM_SEED=<block seed>` (2001–2005), NOT the v1-fixed 42** — do not
copy the §4 command verbatim; the counterbalance order file records the
per-run seed. **Arm C: `POLL_INTERVAL_S=30`
on the shell** (Docker `-e` override trap — restated from v1; dropping it runs
C at poll-10 and destroys the factorial). **Arm D:** `SAMPLE_EVERY` comes from
the env file (no `-e` override exists for it; verify in
`controller_env_snapshot.env`). Run folders
`<timestamp>_rq1_delivery_<suffix>_<1..5>`; checkpoint **C4 arm set is
`ep | delayed | ls | sp`**.

**2026-08-04 G2 retune (Option A):** the true open-loop G2 revealed the
collapse root cause — (1) RQ1 envs predated the 2026-08-03 data-path fix, so
edge servers ran Mongo pool size 1 (serialized DB → DB latency explosion →
256 MB OOM → lan1 telemetry silence → no scale-up; the "lan1 asymmetry" is a
downstream symptom, not an independent bug); (2) rate 5.0 = 120 req/s/LAN ≈ 3×
sustainable. Fix: **data-path fix (`EDGE_MONGO_READ_PREFERENCE=secondaryPreferred`,
`VIP_DATA_PER_CONNECTION_FLOWS=1`, `EDGE_MONGO_MAX_POOL_SIZE=6`) added to all 4
RQ1 env files** (matching RQ2/control) + **new `phases_rq1_stress_plateau.json`
at rate 3.0** (RQ2's proven-stable level). **All launch knobs are make
command-line variables** (sudo `env_reset` strips exported env — the
2026-08-04 launch bug). Re-validation run pending before any block starts.
**2026-08-04 G2 calib4:** pool 6 still collapsed at rate 3.0 (detection stable
— 121/121 overload windows, 100% delivery, no OOM — but plateau p50 24–34 s,
timeout ~63%; telemetry proven lossless, so the gap is 60 s VIP-timeout kills).
Root cause: DB-path knife's edge (~50 DB ops/s/LAN demand vs ~48 capacity with
pool 6; storage idle ~25% CPU). **Pool raised 6→12 in all 4 env files +
`source/scripts/testing/rq1_launch_run.sh`** (formalized from temp
`_rq1_launch.sh`; ~96 DB ops/s capacity, keeps rate 3.0).

**2026-08-04 G2 calib6 (pool 12 + absent-cleanup slot fix): still collapsed —
workload RE-ANCHORED, not patched.** Plateau p50 22.2/30.5 s, timeout 68%,
completion ~29%, delivery 124/124, detection 118/105. Pool 12 did NOT help →
the DB-ceiling hypothesis was wrong. Root cause = **control-loop churn
collapse**: overload → bursty completions → sparse telemetry presence →
absent-node cleanup + scale-down removed LIVE compute/storage nodes mid-overload
→ RS reconfig + fleet shrink (25 adds/17 removes; compute fleet ~1 node for
76/125 windows) → DB ops stall 6–16 s → worse overload (self-amplifying; every
DB spike coincided with a churn event). *(Updated 2026-08-05: the rate-2.0
re-run with the hysteresis guard removed ALL removals and the plateau still
collapsed — the churn was an amplifier, not the root cause; see sweep below.)*
**Driver-mismatch finding:** the
control-group / RQ2 “proven-stable” rates (5.0 / 1.5) were measured with the
legacy SYNC (closed-loop) driver (13-col CSVs, no `status`), which
backpressures and hides data-plane collapse; RQ1's open-loop driver (fixed load
— correct for the thesis) was never rate-calibrated.

**Fix (2026-08-04): churn guard + open-loop rate sweep.**
1. **Controller churn guard** (all RQs; `_HOUSEKEEPING_OVERLOAD_GATE` default
   ON, hysteresis `_HOUSEKEEPING_OVERLOAD_LOOKBACK=5`): while the LAN is
   overloaded (current OR any of the last 5 delivered windows),
   `_run_housekeeping` suppresses absent-node cleanup AND scale-down (they
   destroy live capacity under sparse telemetry); scale-up still runs.
2. **Open-loop rate sweep** (Arm A reference, seed 2001, pool 12 held), edit
   `phases_rq1_stress_plateau.json` rate in place. **Run `rq1_g2_rate20`
   (rate 2.0, current-window guard): COLLAPSED** — p50 16.5/19.2 s, timeout
   76–78%, completion ~22%; guard engaged (100 suppressions) but the overload
   label flickers on lull windows (sparse telemetry) → absent-cleanup still
   fired (19 adds/11 removes; 52 `scale_down absent` on lan2). **Hysteresis
   added** (suppress if ANY of last 5 windows overloaded).
   **Re-run `rq1_g2_rate20` (hysteresis guard): STILL COLLAPSED with a STABLE
   fleet** — p50 16.3/17.5 s, timeout 70–73%, failure 11–19%, completion
   27–29%, **0 removals** (guard fully effective; 12 adds = base+3 dyn),
   multiple backends served, DB spikes 3–23 s. ⇒ **churn is an amplifier, not
   the root cause.**
3. **RQ2-comparison root cause (decisive):** RQ2 open-loop data-bound
   (`ba_db_cal4`, rate 1.5, 600 s) completes **86.8%** at p50 **1.98 s** with
   the same platform/pool-6/WAN — and it churned (12 removes) yet stayed
   stable. RQ1 at rate 2.0 collapses (~27%). The difference is **DB-op
   demand**: RQ1's mix is 40% `feed_ranking` (2 DB ops/request:
   user_profiles.find_one + content_items.find) ⇒ **~54 DB ops/s at rate 2.0**
   vs RQ2's proven-sustainable **~42 DB ops/s** (rate 1.5, 100% DB mix) — RQ1
   sits ~29% above the cliff. All RQ1 endpoints collapse uniformly (p50
   15.3–17.5 s) → shared-path queueing behind the DB layer (per-op read ~190
   ms even at baseline — a platform constant in the edge DB wrapper, not WAN
   netem, which only applies on the inter-LAN router).
4. **rate-1.5 test (`rq1_g2_rate15`, pool 12 + guard): STILL COLLAPSED** — p50
   15.6/16.9 s, timeout 62–67%, completion 33–37%, overload 120/123. This
   disproved the DB-demand hypothesis (RQ1 ~40 DB ops/s vs RQ2's stable ~42).
5. **Pool 6 re-anchor (`rq1_g2_rate15_p6`):** RQ2's proven config is
   `EDGE_MONGO_MAX_POOL_SIZE=6` (6 conns/edge; its env comment: “so storage
   serving scales with edges × pool”). 4 edges × pool 12 = 48 concurrent Mongo
   ops thrash the storage tier at `STORAGE_CPUS=0.08` → per-op latency explodes.
   **Pool reverted 12 → 6 in all 4 env files + launcher** (failed calibration
   runs deleted; v1 campaign + pre-flight kept). Rate 1.5 + pool 6 + churn
   guard = the exact RQ2-comparable bounded-overload test. **Gate run
   `rq1_g2_rate15_p6` EXECUTED — ❌ FAILED.**

   **Gate result (`20260805_065605_rq1_g2_rate15_p6`, exit 0):** stable fleet
   (0 removals, adds to dyn5/dyn6 caps), no OOM, telemetry lossless (124/124
   both LANs, 0 missed), dropped 0, overload detected (lan1 115/124, lan2
   119/124), scale-up fired — but **plateau collapsed identically to pool 12**:
   lan1 p50 16.2 s / timeout 68.3% / completion 31.0%; lan2 p50 16.8 s /
   timeout 66.4% / completion 32.6% (vs pool 12 rate-1.5: p50 15.6/16.9 s,
   timeout 62–67%, completion 33–37%). ⇒ **pool size DISPROVED as root cause.**
   Secondary: every `demand_drop` scale-down decision was an `absent` no-op —
   no real removal executed. Open hypotheses: RQ1 compute endpoints
   (`feed_ranking`/`service_pressure` CPU cost at `EDGE_CPUS=0.15`) vs RQ2
   pure-DB mix; scale-down no-op. **No campaign block until plateau stabilized.**
6. **Plateau re-anchor — three-fix combo (`rq1_g2_rate12_mix_ec25`): ✅ PASS.**
   Root cause of the remaining collapse confirmed as **compute-tier saturation**
   at `EDGE_CPUS=0.15`: edge CPU 55–73% med / peaks 99%; `feed_ranking` actually
   costs **3 DB ops/req** (1 `user_profiles` + 1 `content_items.find` per LAN ×
   2) not 2 ⇒ plateau demand at rate 1.5 = **54 DB ops/s/LAN** (~29% above
   RQ2's proven ~42); 70% of the mix was CPU-heavy endpoints. **Fixes applied
   together**: plateau rate 1.5→1.2 (~35 DB ops/s), mix rebalanced
   (feed 0.4→0.2, service 0.3→0.2, lookup 0.2→0.35, update 0.05→0.15, agg
   0.05→0.1), `EDGE_CPUS` 0.15→0.25 (launcher).

   **Gate result (`20260805_074127_rq1_g2_rate12_mix_ec25`, exit 0): ✅ PASS —
   plateau LOCKED.** lan1 p50 2.32 s / p95 12.7 s / timeout 8.9% / failure
   0.92% / completion 88.5%; lan2 p50 1.46 s / p95 8.3 s / timeout 7.4% /
   failure 0.53% / completion 90.4%. Delivery lossless (124/124, 0 missed),
   dropped 0, no OOM, overload detected (lan1 66/124, lan2 120/124), 12 adds +
   **4 real removals** (scale-down works). Remaining observation: lan1 overload
   detection 66/124 vs lan2 120/124 — same lan1-vs-lan2 asymmetry pattern to
   track via `rq1v2_p4_01_lan2_asymmetry.py` (not a gate blocker: 0 missed).

**Pre-flight (hard gates, fail-fast; blocks do not start until all pass):**
(a) `make driver_selftest` (host + netns) — ✅ passed; (b) `make
rq1_analyzer_selftest` — ✅ passed (local + VM); (c) **sampled-push selftest
inside the `osken-controller` image** (the VM host python3 lacks pydantic; the
selftest injects an os_ken hub stub so it runs without the controller runtime):
`sudo -n docker run --rm -v $PWD:/workspace -w /workspace -e PYTHONPATH=/workspace --entrypoint python3 osken-controller source/scripts/testing/rq1v2_p2_01_sampled_push_selftest.py`
(`make rq1_sampled_push_selftest` works on hosts where python3 has os_ken +
pydantic — e.g. the dev machine) — ✅ passed in-container; (d) concurrency
stress check (aggregate in-flight at rate 5.0 × 24 clients × 300 s cap must not
exhaust container/conntrack limits) — ✅ satisfied by the calibration plateau
(82 req/s over 600 s, conntrack 262144, no exhaustion); (e) **G2 calibration
under open-loop** — plateau rate 5.0 with `INFLIGHT_WINDOW=1024` ⇒ worst-case
in-flight/client = 1500 > window ⇒ **`dropped` is possible by design** and is a
designed, reported outcome (counted in offered, excluded from latency/failure);
decision rule: if calibration `dropped` > 1% of offered, raise
`INFLIGHT_WINDOW` up to the concurrency limit, else keep 1024 — recorded in the
plan; **🚨 BLOCKED — re-run executed but FAILED (true open-loop)**. The
re-run `20260804_165925_rq1_delivery_ep_calib2` ran open-loop correctly (fix
verified: `open_loop_schedule.json`, workers `--driver-mode open_loop
--in-flight-window 1024 --drain-s 30.0`) but revealed: (i) **catastrophic
overload collapse** — plateau ≈ 120 req/s/LAN (open-loop preserves offered
load), lan1 timeout 87.7%/p50 21.9 s, lan2 timeout 68.2%; `dropped` =
3.13%/15.51% both > 1% → G2 rule requires raising `INFLIGHT_WINDOW` or
re-tuning the offered rate; (ii) **lan1 overload-detection/scaling
asymmetry** — lan1 flagged 14/173 overload windows (lan2: 123/167), made 2
scale-ups (lan2: 6), scaled to dyn2 only, `server_count` collapsed to 1
mid-plateau, yet lan1 was the worse-performing LAN (inverse of v1's Arm C
lan2 asymmetry). **No campaign block may start until the lan1 asymmetry is
root-caused and G2 is retuned**; (f) **per-arm
scale-down arming check** (esp. Arm D — its ~30 s delivery cadence stretches
the 3-of-6 below-window accumulation; must fire ≥ 1 scale-down decision/LAN —
the v1 P3 failure mode); **✅ PASS 2026-08-05:** Arm A `rate12_mix_ec25` (4
real removals), Arm B `armB` (real storage removals in recovery_gap), Arm C
`armC_rerun` (7 real removals in the new `idle_tail` — the first Arm C run
`rq1_g2_armC_arm` fired ZERO scale-downs because the poll's stale view kept the
overload label ≥5% through demand_drop → churn guard suppressed until the last
second; root cause verified via ground-truth `resource_stats`/`client_requests`
— identical demand (~1680 reqs) in both arms, difference is the controller's
view, not the workload; **fix = `idle_tail` phase** (420 s near-idle after
demand_drop) so the lossy arm observes idle, the guard releases, and C7 is
measurable); Arm D pending (its dry-run doubles as D's arming check); (g) Arm
D dry-run (delivered fraction ∈ [0.30, 0.36],
delivery-delay p50 < 2 s — the sampled-push selftest assertion) — **⚠️
INVALIDATED — RE-RUN PENDING** (sync-driver evidence only from
`20260804_162043_rq1_delivery_sp_calib`; open-loop re-run required); (h) lan2
asymmetry diagnostic on the
calibration runs (`rq1v2_p4_01_lan2_asymmetry.py`) — pending on valid open-loop
calibration runs; (i) legacy `sync`-mode
regression smoke.

**Per-arm env verification (Phase-6 gate):** A/B: `TELEMETRY_SOURCE`; C:
`TELEMETRY_SOURCE=poll` **and** shell `POLL_INTERVAL_S=30`; D:
`TELEMETRY_SOURCE=sampled_push` and `SAMPLE_EVERY=3`. Driver-mode/window/drain
are shell-only knobs and never appear in `controller_env_snapshot.env` —
verify them from the run log's printed config line ("Driver mode: open_loop
(window=…, drain=…)").

**Wall-clock:** ~20 runs × ~30–35 min (incl. 3 phase-boundary drains + run-end
drain of 30 s each + setup) ≈ 11–12 h ≈ 1.5–2 VM-days, **plus** pre-flight /
calibration (~4–6 runs ≈ 3 h). RQ2's v2 campaign (18-run, 6 cells × 3) has VM
priority; RQ1 v2 runs after (or interleaved per user).
