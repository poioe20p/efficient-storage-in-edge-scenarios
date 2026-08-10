# RQ3 v2 — Pre-Flight (Phase 6) — explicit, ordered, fail-fast

**Date**: 2026-08-04 · **Plan**: `rq3_v2_rework_plan.md` §4 Phase 6 · **VM**: `cloud-vm-rq3` (dedicated RQ3 VM; base tooling verified present, not yet provisioned)
**Companion script**: `source/scripts/testing/rq3v2_p6_01_preflight.sh`

## 1. Purpose

Guarantee, **before any campaign block starts**, that `cloud-vm-rq3` is
provisioned and every Phase-6 gate is verifiably satisfied with **recorded
decisions**. A single failed hard gate stops the sequence (fail-fast); nothing
is "deferred with a note" except where this document explicitly records an
**outcome** rather than a gate (e.g., the gap-window verdict).

**Block rule**: blocks do not start until **all** of Stage 0 → Stage 6 pass
(and Stage 5 decisions are recorded).

## 2. Ground rules

- Every command below runs on `cloud-vm-rq3`; repo at
  `~/efficient-storage-in-edge-scenarios`; docker via `sudo -n` (non-interactive).
- Each gate has: an **exact command**, a **pass criterion**, and a **record
  artifact**. The companion script automates the host-runnable gates and writes
  `rq3_preflight_report.txt`; full-run gates (calibration, measurability) are
  run sequentially by the operator and their run folders fed back to the script.
- Recorded decisions live in §11 (Decision log) and are copied into the plan's
  run matrix before execution.

## 3. Stage 0 — VM baseline (no repo changes)

| # | Check | Command | Pass criterion | Record |
|---|---|---|---|---|
| 0.1 | Host facts | `hostname; nproc; free -h \| head -1; grep PRETTY_NAME /etc/os-release` | Ubuntu 22.04, ≥ 4 CPU | §11 |
| 0.2 | Docker daemon | `docker --version; sudo -n docker ps -q \| wc -l` | daemon reachable via `sudo -n` | §11 |
| 0.3 | Fresh state | `sudo -n docker ps -q \| wc -l` | 0 containers (no stale stack) | §11 |
| 0.4 | Repo | `ls -d ~/efficient-storage-in-edge-scenarios; git -C ~/efficient-storage-in-edge-scenarios log --oneline -1` | repo present, HEAD recorded | §11 |
| 0.5 | Python deps | `python3 -c 'import aiohttp'`; `python3 -c 'import requests'`; `pip3 --version` | aiohttp + requests import clean | §11 |
| 0.6 | Tooling + OVS | `make --version`; `git --version`; `sudo -n modprobe openvswitch; lsmod \| grep openvswitch`; `sudo -n docker images \| grep ovs-container` | make, git present; **openvswitch kernel module loadable** + **`ovs-container` image present** — OVS is containerized (source/docker/OVS/), the host never has a host `ovs-vsctl` binary; setup_network runs OVS inside the container | §11 |
| 0.7 | CPU/OS floor | `[ "$(nproc)" -ge 4 ]`; `grep -q 22.04 /etc/os-release` | ≥ 4 CPU; Ubuntu 22.04 | §11 |

## 4. Stage 1 — Source sync + code gates

| # | Check | Command | Pass criterion |
|---|---|---|---|
| 1.1 | Sync latest code | `git -C ~/efficient-storage-in-edge-scenarios pull` (or scp the changed files) | RQ3 v2 code present; HEAD recorded |
| 1.2 | New-code markers | `grep -q 'EDGE_APP_READY_EVENT' source/docker/edge_server/source/edge_server_process_state.py`; `grep -q '"app_ready"' source/docker/local_state_server/aggregator.py`; `grep -q 'def admit_on_event' source/sdn_controller/readiness_gate.py`; `grep -q 'discovery_15' docs/research_questions/v2/rq3/rq3_admission_analysis.py` | all four markers present |
| 1.3 | Shared driver selftest (host) | `make -C source/scripts driver_selftest` | exit 0 |
| 1.4 | RQ3 analyzer selftest | `make -C source/scripts rq3_analyzer_selftest` | exit 0 |
| 1.5 | RQ3 app_ready selftest | `make -C source/scripts rq3_app_ready_selftest` | exit 0 |
| 1.6 | Legacy sync regression | post-provision (Stage 4): `make -C source/scripts run_experiment TRAFFIC_DRIVER_MODE=sync OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/rq3_discovery.env DRY_RUN=1 RUN_LABEL=rq3_sync_smoke` | sync mode launches cleanly (regression); the driver selftest (1.3) already covers the driver itself |

> **Ordering:** 1.6 runs **after Stage 4** (it needs the provisioned network), not
> in Stage-1 sequence — it is listed here for grouping, not execution order.

## 5. Stage 2 — Image builds

The RQ3 v2 code changed **two images**; the controller is **volume-mounted**
(no rebuild — new `readiness_gate.py`/`main_n*.py`/`scaling_config.py` are
picked up on controller restart).

| # | Check | Command | Pass criterion |
|---|---|---|---|
| 2.1 | `edge_server` rebuilt | repo build script (`build_images.sh` / docker compose) | image exists, build after the app_ready code change |
| 2.2 | `local_state_server` rebuilt | same build | image exists (aggregator `app_ready` whitelist) |
| 2.3 | controller mount | verify the controller container mounts `source/sdn_controller` (read-only volume) | mount present → no image rebuild needed |
| 2.4 | base images present | `sudo -n docker images` | `edge_storage_server` (repo storage image name), `edge_server`, `local_state_server` listed (clients are **netns**, created in Stage 4 — not images) |

## 6. Stage 3 — Env regime validation

`~/rq3_env/` must be synced (from `docs/operation/testing/experiment/v2/rq3/env/`)
and each arm file must assert **exactly** the pre-registered knobs. The
companion script checks these assertions.

| Key | direct | discovery | discovery_15 |
|---|---|---|---|
| `READINESS_PROPAGATION` | `direct` | `discovery` | `discovery` |
| `DISCOVERY_POLL_INTERVAL_S` | `10.0` | `10.0` | `15.0` |
| `READINESS_EVENT_FALLBACK_S` | `5.0` | — | — |
| `EDGE_APP_READY_EVENT` | `1` | — | — |
| `EDGE_FLOW_ISOLATION` | `1` | `1` | `1` |
| `VIP_FLOW_ISOLATION` | `1` | `1` | `1` |
| `VIP_SERVER_PER_CONNECTION_FLOWS` | `1` | `1` | `1` |
| `EDGE_READY_PORT` | `5000` | `5000` | `5000` |
| `BACKEND_SELECTION_POLICY` | `topology_host` | `topology_host` | `topology_host` |
| `VIP_WARM_SERVER_SECONDS` | `0` | `0` | `0` |
| `SCALEUP_POLICY` | `dual` | `dual` | `dual` |
| `MAX_DYNAMIC_COMPUTE` | `6` | `6` | `6` |
| `TELEMETRY_SOURCE` | `event_preserving` | `event_preserving` | `event_preserving` |
| `STORAGE_PERSISTENT_RESERVE_ENABLED` | `0` | `0` | `0` |
| `SS_ENABLED` | `0` | `0` | `0` |
| `CROSS_REGION_STORAGE_ENABLED` | `0` | `0` | `0` |

> **`MAX_DYNAMIC_COMPUTE` is REQUIRED (calibration finding):** the base env
> `osken-controller.env` sets `MAX_DYNAMIC_COMPUTE=0`, which silently disables
> compute scale-up — the readiness gate never enqueues a pending backend and
> no `admission_log` is ever written. Calibration run 20260804_190659 showed
> the compute layer WAS saturated (spike `average_cpu_percent` 9.58%, max
> 21.7%, vs the 4.5% scale-up floor) yet `max_nodes=0` blocked every ComputeAlert.
> All three arm files therefore set `MAX_DYNAMIC_COMPUTE=6`.

Additional checks (all **FAIL-hard**, no warn-and-continue):

- **Sync (canonical == VM mirror)**: `diff` between
  `source/scripts/testing/controller_env_overrides/rq3_*.env` (the canonical
  files the runs use) and `~/rq3_env/rq3_*.env` (the VM mirror) → **must be
  byte-clean**. The runs use the canonical `controller_env_overrides` paths, so
  a dirty mirror is a divergence, not a note.
- **Docs env copies**: `docs/operation/testing/experiment/v2/rq3/env/rq3_*.env`
  must exist and carry the same knob lines as the canonical files (they add a
  provenance header by design, so the check is per-knob, not byte-diff).
- **Port consistency**: `EDGE_READY_PORT=5000` == edge `bind_port` default 5000
  (`os.environ.get("BIND_PORT", "5000")` in `edge_server_config.py`) — the
  `/ready` probe depends on it.
- **Controller propagation**: `EDGE_APP_READY_EVENT`/`EDGE_FLOW_ISOLATION`
  must be present in the **controller env** (they are read by
  `compute_node_manager._docker_run_server` and passed to dynamic edges).
- **Edge self-identity (`OWN_MAC`)**: every edge server must self-report the
  MAC the controller assigned it, or its telemetry is invisible to WSM
  selection (cross-LAN routing). Calibration run 20260804_193235 showed
  `edge_server_n2` self-reporting a random veth MAC (`ea:62:ea:e6:62:e3`)
  because `_discover_mac()` raced the veth attach and latched the pre-set MAC —
  the storage server already handled this via `OWN_MAC`
  (`mongo_telemetry.py`), and the fix was ported to
  `edge_server/source/telemetry.py` (`OWN_MAC` validated first) with
  `-e OWN_MAC=` wired in `build_network_1/2.sh` (static edges) and
  `compute_node_manager._docker_run_server` (dynamic edges). Verify in the
  edge-container env: `printenv OWN_MAC` equals the OVS-learned MAC.
- **Cross-LAN stats merge (`main_n1.py`/`main_n2.py`)**: the selection pools
  deliberately include cross-LAN candidates (`topology._server_macs =
  local ∪ peer`), and both controllers subscribe to both aggregators' PUB
  (`AGGREGATOR_ENDPOINTS` includes `10.0.0.5:5556` and `10.0.1.5:5556`) — the
  peer summaries arrive (controller logs show "ignoring telemetry for <peer>")
  but were previously discarded before `update_server_stats`, so cross-LAN
  candidates were permanently `0/0` and won every WSM cost (run 20260804_203701:
  LAN1 selected `edge_server_n2` 534× at cost 0.56 while the local edge at cost
  0.88 was never selected). The fix merges peer `servers`/`storage_servers`
  stats into the pools before the per-LAN early-return, keeping scaling/control
  local; the hops term then favours the local edge.
- **Per-connection VIP_SERVER flows (`VIP_SERVER_PER_CONNECTION_FLOWS=1`)**:
  RQ3 arms scope each VIP_SERVER DNAT/SNAT pair to the client's ephemeral
  source port (the edge emits `client_port` in `request_complete`), so the
  async flow delete for one request can never collide with the next request's
  flow. Calibration run 20260804_212441 showed Check C at 0.40 (per-client
  flows shared a generation whenever the ~1 s delete landed after the 333 ms
  dispatch interval); per-connection mode restores coverage ≈ 1.0. Default 0 =
  per-client (canonical/RQ1/RQ2 byte-identical). Verify `printenv
  VIP_SERVER_PER_CONNECTION_FLOWS` == 1 on the controller and that
  `request_complete` events carry `client_port`.

## 7. Stage 4 — Network provisioning + probe reachability

| # | Check | Command | Pass criterion |
|---|---|---|---|
| 4.1 | Build network | `EDGE_FLOW_ISOLATION=1 make -C source/scripts setup_network` (base env; the export is **REQUIRED** — `build_network_1/2.sh` defaults `EDGE_FLOW_ISOLATION=0`) | OVS bridges up; then verify the static edges: `docker exec edge_server_n1 printenv EDGE_FLOW_ISOLATION` == `1` (and `edge_server_n2`) |
| 4.2 | Create clients | `make -C source/scripts create_clients` | `lan1_client_*`, `lan2_client_*` netns exist |
| 4.3 | **Probe reachability (T12.11)** | resolve a static edge IP: `IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' edge_server_n1)`; then `curl -m 5 http://${IP}:5000/ready` from the controller host | HTTP 200/503 **reachable** (a 503 "starting" is fine — reachability is what matters; a connection-refused/timeout fails) |
| 4.4 | Host route | `ip route show \| grep -E '10\.0\.0\.0/24|10\.0\.1\.0/24'` | routes via the OVS bridge exist (controller runs `--network host`) |
| 4.5 | In-netns driver selftest | `sudo -n ip netns exec lan1_client_1 python3 ~/efficient-storage-in-edge-scenarios/source/scripts/testing/openloop_p1_01_driver_selftest.py` | exit 0 (the Stage-1.3 host variant is a prerequisite) |
| 4.6 | **Seed + snapshot (empty VM!)** | `make -C source/scripts run_experiment ... SKIP_SEED=0 SKIP_SNAPSHOT=0` on the FIRST calibration run (the Makefile defaults `SKIP_SEED ?= 1`/`SKIP_SNAPSHOT ?= 1`, and the VM starts empty — without seeding the first run crashes on an empty DB / missing snapshot) | data seeded, workload snapshot exported; **all** runs keep `SKIP_SEED=0 SKIP_SNAPSHOT=0` (per-run fresh data per thesis §8) |

## 8. Stage 5 — Calibration (G2) + concurrency

**Pre-step: edit `phases_rq3_compute_episode.json` spike `rate_per_client` to
`3.0` in place** before the calibration runs (the current `5.0` violates the
budget: `1024/5 = 204.8 < 300`). Two calibration runs under open-loop, using
the **arm** env, with **distinct seeds** (2101 direct, 2102 discovery — outside
the campaign block range 2001–2006):

```
make -C source/scripts run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/rq3_direct.env \
  RANDOM_SEED=2101 TRAFFIC_DRIVER_MODE=open_loop CURL_MAX_TIME=300 \
  INFLIGHT_WINDOW=1024 DRAIN_S=30 \
  PHASES_CONFIG=testing/phases_override/phases_rq3_compute_episode.json \
  SKIP_CLIENTS=0 SKIP_SEED=0 SKIP_SNAPSHOT=0 \
  RUN_LABEL=rq3_calib_direct
# …repeat with rq3_discovery.env → RUN_LABEL=rq3_calib_discovery, RANDOM_SEED=2102
```

**Per-run reset (thesis §8 — fresh data every run; seeding is an upsert, so
only a teardown actually resets data):** before EACH run (calibration and
campaign), run `make -C source/scripts teardown_clients` (removes clients +
`cleanup.sh`), then
`EDGE_FLOW_ISOLATION=1 make -C source/scripts setup_network
OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/<arm>.env` —
**the override MUST be passed to `setup_network` too**: the controller env is
fixed at setup time (`build_network_setup.sh` starts `osken` with the merged
base+override `--env-file`), so running only `run_experiment` with the
override leaves the controller on the base env and the RQ3 env gate fails —
then the run with `SKIP_CLIENTS=0 SKIP_SEED=0 SKIP_SNAPSHOT=0` (creates
clients, seeds, exports the snapshot, and runs — the same cycle RQ1/RQ2 v2
use, and the same override passed to `run_experiment`).

**Pre-registered decision rules (recorded, not post-hoc). Feasible spike-rate
interval:** the rate must be ≥ the saturation floor (old-backend `timeout_rate`
≥ 5 pp above baseline in a calibration run) and ≤ the budget ceiling
`min(3.0, INFLIGHT_WINDOW/300)` per client. With `CLIENTS ?= 3` per LAN (6
clients total), per-client max in-flight = rate × 300 ≤ the per-client window
(`INFLIGHT_WINDOW`); the **aggregate** rate × 6 × 300 must fit
`nf_conntrack_max` (checked separately, R3).

| Rule | Criterion | Action |
|---|---|---|
| R1 `dropped` budget | calibration `dropped` > 1% of offered | **lower the rate** toward the saturation floor (2.0–3.0); if the floor and the ceiling cannot both hold, raise `INFLIGHT_WINDOW` (1024 → 2048) to widen the ceiling — record the choice |
| R2 spike rate | per-client `window/rate > 300` (rate ≤ 3.0 at window 1024; ≤ 6.0 at window 2048) **AND** saturation ≥ 5 pp above baseline | choose the **highest rate in the feasible interval**; re-tune `phases_rq3_compute_episode.json` spike rate in place; record |
| R3 concurrency stress | per-client `rate × 300` ≤ `INFLIGHT_WINDOW`; **aggregate** `rate × 6 × 300` ≤ `nf_conntrack_max` (`sysctl net.netfilter.nf_conntrack_max`) and container limits; confirm via `sudo -n ss -s` during calibration | tune `net.core.somaxconn`/conntrack if it does; **if no rate satisfies R1+R2+R3, STOP and record — do not proceed** |

**Calibration outputs** (feeds Stage 6): per-run analyzer summary, the
persisted per-run CSV (`rq3_calib_summary.csv` — the pre-flight script writes
it via `--calib-summary`), the per-run flow-validation verdicts, and the
run-log driver config line (confirms `open_loop`, window, drain).

## 9. Stage 6 — Measurability + arming gates (on the calibration runs)

Run on each calibration run folder:

```
python3 docs/research_questions/v2/rq3/rq3_admission_analysis.py \
  <rq3_calib_direct_dir> <rq3_calib_discovery_dir> --csv <calib_summary.csv>
python3 docs/research_questions/v2/rq3/rq3_flow_validation.py <run_dir>   # per run
```

| Gate | Criterion | Outcome |
|---|---|---|
| G1 gap-window measurability | ≥ 20 gap-window requests per LAN, **both arms** | pass / fail (fail blocks) |
| G2 min-admissions arming | ≥ 1 admitted backend per LAN, **both arms** | pass / fail (fail blocks) |
| G3 event-fraction (direct) | `admit_source=event` ≥ 0.80 on the direct calibration run | pass / fail (fail blocks; instrument-degraded) |
| G4 | flow validation | Checks A/B pass, C ≥ 0.85 (amended 2026-08-05 from 0.9), D ≤ 1% on both calibration runs (run `rq3_flow_validation.py` per folder; the pre-flight script gates it) | pass / degraded / fail |
| G5 | gap verdict | gap-window old-backend `timeout_rate` ≥ 5 pp above baseline, per arm | **recorded outcome** (hurt / not-hurt) — NOT a gate |
| G6 | sync regression | legacy `sync`-mode smoke (Stage 1.6) still passes | pass (regression) |

**discovery_15 (sensitivity) measurability**: checked on the FIRST sensitivity
run (block seed 2006). If its gap window falls below 20/LAN, it is **recorded**
(sensitivity is descriptive — Cliff's delta only, ≥ 2 runs/cell per the plan) —
it is not a campaign blocker; the achieved n is reported.

## 10. Stage 7 — Run-launch contract (campaign)

Every campaign run uses exactly this shape (arm env, block seed, shared knobs),
**preceded by the per-run reset cycle** (teardown_clients → setup_network → run,
Stage 5):

```
make -C source/scripts run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/rq3_<arm>.env \
  RANDOM_SEED=<block_seed> \
  TRAFFIC_DRIVER_MODE=open_loop CURL_MAX_TIME=300 INFLIGHT_WINDOW=<decided> DRAIN_S=30 \
  PHASES_CONFIG=testing/phases_override/phases_rq3_compute_episode.json \
  SKIP_CLIENTS=0 SKIP_SEED=0 SKIP_SNAPSHOT=0 \
  RUN_LABEL=rq3_<arm>_b<block>_r<replicate>
```

**Per-run verification (recorded in the run folder):**
1. `controller_env_snapshot.env` — arm label (`READINESS_PROPAGATION`),
   cadence knobs, `EDGE_APP_READY_EVENT`/`EDGE_FLOW_ISOLATION`/`VIP_FLOW_ISOLATION`.
2. Run-log driver config line — `open-loop supervisor (window=…, drain=…s)`
   (the driver's actual banner, `traffic_generator.py` supervisor print).
3. Edge containers — `docker exec <edge> printenv EDGE_FLOW_ISOLATION
   EDGE_APP_READY_EVENT` + `BIND_PORT` (dynamic edges; static edges carry
   `EDGE_FLOW_ISOLATION`).
4. `verify_rq3_run()` in `run_experiment.sh` — min-admissions, flow-validation,
   controller + dynamic-edge env (already wired).

Block order comes from `counterbalance_order_v2.csv` (seeds 2001–2005 primary,
2006 sensitivity). Voids take the matrix position (≤ 1 per cell).

## 11. Decision log (fill during pre-flight)

| # | Decision | Value | Recorded by |
|---|---|---|---|
| D1 | Spike rate (after R2) | | |
| D2 | `INFLIGHT_WINDOW` (after R1) | | |
| D3 | `dropped` % in calibration | | |
| D4 | Concurrency stress result | | |
| D5 | Measurability G1 (direct/discovery) | | |
| D6 | Min-admissions G2 (direct/discovery) | | |
| D7 | Event-fraction G3 (direct) | | |
| D8 | Flow-validation G4 (both) | | |
| D9 | Gap verdict G5 (direct/discovery) | | outcome, not gate |
| D10 | Sync regression G6 | | |
| D11 | Edge `BIND_PORT` confirmed | 5000 | |
| D12 | `/ready` reachability (T12.11) | | |

## 12. Go / No-Go checklist (ordered)

- [ ] Stage 0 baseline (0.1–0.5)
- [ ] Stage 1 code gates (1.1–1.6)
- [ ] Stage 2 images (2.1–2.4)
- [ ] Stage 3 env regimes (all assertions + sync + port consistency)
- [ ] Stage 4 network + probe reachability (4.1–4.5)
- [ ] Stage 5 calibration + decisions D1–D4
- [ ] Stage 6 gates G1–G6 + decisions D5–D10
- [ ] Stage 7 run-launch contract + per-run verification template confirmed
- [ ] Decision log §11 complete
- [ ] `rq3_preflight_report.txt` shows all gates PASS
- [ ] **GO** → start primary block B1; **NO-GO** → fix the failed gate, re-run
