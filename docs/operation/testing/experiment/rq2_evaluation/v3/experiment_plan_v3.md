# Experiment Plan v3 — RQ2 Routing-Awareness Coordination Gap (v7-Aligned)

**Status**: Designed · **Date**: 2026-07-21
**Replaces**: [v2](../v2/experiment_plan_v2.md) (config not aligned with RQ1 v7 golden baseline)
**Predecessor**: Original RQ2 run (2026-07-06) — invalidated by aggressive compute scoring (CPU_SPAN=10 default)
**Implementation**: [`source/sdn_controller/_vip_routing/selection.py`](../../../../source/sdn_controller/_vip_routing/selection.py)
**Analysis CLI**: [`source/scripts/testing/analysis/rq2/cli_rq2_redistribution.py`](../../../../source/scripts/testing/analysis/rq2/cli_rq2_redistribution.py)

---

## 1. Intent

Evaluate whether the **coordination gap in the routing plane** — the delay
between backend spawn and routing-plane awareness — measurably affects load
redistribution quality. Three policy modes isolate different awareness
timings. The experiment also characterises a second dimension — **backend
readiness** — by measuring the mismatch between traffic arrival and warm-up.

The single question: **Does spawn-time routing awareness produce faster load
redistribution than discovery-time awareness, and does either beat no
integration at all?**

**This is a rerun.** The original RQ2 campaign ran with aggressive compute
scoring (CPU_FLOOR=3, CPU_SPAN=10 default). v3 uses the **RQ1 v7 golden
configuration** — fully corrected scoring (CPU_SPAN=40, CPU_FLOOR=10,
STORAGE_BASE_THRESHOLD=0.35), CLIENTS=96, STORAGE_CPUS=0.08 — ensuring
cross-RQ comparability. The only v7 mechanism NOT carried over is the
`EDGE_MAX_CONCURRENT` semaphore (RQ2 does not need it).

---

## 2. Hypothesis / Expected Outcome

### 2.1 Awareness Timing (coordination gap)

| Metric | Expected ranking | Mechanism |
|---|---|---|
| **TTFT** | lifecycle < host < slowstart | Warm lease at t=0; round-robin counter-dependent; invisible until discovery |
| **Initial load share** | lifecycle > slowstart > host | Priority routing; graduated ramp; round-robin ~1/N fair share |
| **Coordination-gap penalty** | TTFT(slowstart) − TTFT(lifecycle) ≥ 20 s | Extra telemetry window a separated LB waits |

### 2.2 Readiness Timing

| Mode | Traffic starts | Backend warm | Mismatch | Expected non-stress p50 |
|---|---|---|---|---|
| host | t≈0 s | t≈5–10 s | 5–10 s | Elevated (>>7 ms) |
| slowstart | t≈10 s | t≈5–10 s | ~0 s | Lowest (~7 ms) |
| lifecycle | t≈0 s | t≈2–3 s | ~2 s | Near slowstart (~7 ms) |

### 2.3 Service Quality

- **Non-stress phases (baseline, cooldowns, demand_drop)**: host p50 elevated
  vs slowstart/lifecycle. Slowstart and lifecycle indistinguishable.
- **Stress phases (storage_storm, compute_spike)**: all modes converge
  (MongoDB I/O dominates); p50 within 3× of each other per phase.
- **p95 latency**: all modes within 15% of each other, per phase.
- **Failure rate**: ≤ 0.1% across all modes.

---

## 3. RQ Linkage

| RQ element | This experiment |
|---|---|
| Independent variable | `BACKEND_SELECTION_POLICY` (host / slowstart / lifecycle) |
| Dependent variables | TTFT, initial load share, per-phase p50/p95/p99, readiness mismatch |
| Held constant | RQ1 v7 golden config: workload, compute scoring, storage scoring, push telemetry, topology, WSM weights |

Thesis RQ2: *How does the timing of routing-plane awareness relative to
backend spawn affect load redistribution quality during scale-up events?*

---

## 4. Independent Variable & Held-Constant Set

### Independent Variable

| Mode | When routing becomes aware | Mechanism | Encodes |
|---|---|---|---|
| `topology_host` | Immediately — unknown stats → 0.0, round-robin distributes evenly | No ramp, no warm lease, no readiness concept | No integration between provisioner and LB |
| `topology_slowstart` | At discovery (first telemetry, 0–10 s post-spawn) | Invisible (penalty 1.0) until discovery, then graduated ramp | Separated architecture — Wang et al. spawn-to-LB-inclusion delay |
| `topology_lifecycle` | At spawn time (atomic with pool registration) | Warm lease with bounded priority window (45 s) | Unified architecture — zero coordination gap |

### Held Constant

| Parameter | Value | Source |
|---|---|---|
| Workload | `phases_rq2.json` (9-phase, two-cycle, rate=4.0, all-local) | `PHASES_CONFIG` |
| **CLIENTS** | **96** (192 total across both LANs) | RQ1 v7 golden |
| CONTENT_ITEMS | 6000 | make var |
| RANDOM_SEED | 42 | make var |
| **STORAGE_CPUS** | **0.08** | RQ1 v7 golden |
| EDGE_CPUS | 0.30 | default |
| **WAN_RTT_MS** | **185** | RQ1 v7 golden |
| CURL_MAX_TIME | 30 | RQ1 v7 golden |
| **MAX_DYNAMIC_COMPUTE** | **12** | RQ1 v7 golden |
| **MAX_DYNAMIC_STORAGE** | **8** | RQ1 v7 golden |
| **SCALEUP_STORAGE_BASE_THRESHOLD** | **0.35** | RQ1 v7 golden (RQ3-validated) |
| **SCALEUP_COMPUTE_BASE_THRESHOLD** | **0.18** | RQ1 v7 golden |
| Compute scoring | CPU_FLOOR=10, CPU_SPAN=40, T_PROC_FLOOR=25, W_CPU=0.60, W_T_PROC=0.40 | RQ1 v7 golden |
| Storage scoring | W_STORAGE_CPU=0, W_T_DB=1.0, STORAGE_CPU_FLOOR=1.5, STORAGE_CPU_SPAN=5, T_DB_FLOOR=60, T_DB_SPAN=250, STORAGE_REQUIRED=2, STORAGE_WINDOW_SIZE=5 | RQ1 v7 golden |
| Scale-down | COMPUTE_COOLDOWN_S=180, COMPUTE_REQUIRED=9, STORAGE_COOLDOWN_S=120 | RQ1 v7 golden |
| Telemetry | Push (ZMQ, window-close) | Controller default |
| **SS_ENABLED** | **0** | RQ2-specific (no Tier 1 pool contamination) |
| VIP_HARD_TIMEOUT | 60 s | RQ1 v7 golden |
| STORAGE_PERSISTENT_RESERVE_ENABLED | 1 | RQ1 v7 golden |
| WSM weights | Defaults (identical across modes) | `osken-controller.env` |
| Warm-lease TTLs | Server 45 s, Storage 30 s | `scaling_config.py` defaults |
| cross_region_ratio | 0.0 (all phases) | `phases_rq2.json` |

**Bold** = changed from v2 to align with RQ1 v7 golden.

---

## 5. Prerequisites

### 5.1 Env Override Files

Three new env override files must be created for v3. Each mirrors
`current_state_integrated.env` (the RQ1 v7 golden config) with exactly
two overrides:

| Override | Value | Reason |
|---|---|---|
| `SS_ENABLED` | `0` | RQ2 must exclude Tier 1 selective sync |
| `BACKEND_SELECTION_POLICY` | `topology_host` / `topology_slowstart` / `topology_lifecycle` | RQ2 independent variable |

**Files to create** (in `source/scripts/testing/controller_env_overrides/`):

| File | BACKEND_SELECTION_POLICY |
|---|---|
| `rq2_v3_topology_host.env` | `topology_host` |
| `rq2_v3_topology_slowstart.env` | `topology_slowstart` |
| `rq2_v3_topology_lifecycle.env` | `topology_lifecycle` |

Each file must contain the exact golden values:

```
STORAGE_PERSISTENT_RESERVE_ENABLED=1
SS_ENABLED=0
MAX_DYNAMIC_STORAGE=8
MAX_DYNAMIC_COMPUTE=12
SCALEUP_STORAGE_BASE_THRESHOLD=0.35
SCALEUP_COMPUTE_BASE_THRESHOLD=0.18
SCALEUP_CPU_FLOOR=10
SCALEUP_CPU_SPAN=40
SCALEUP_T_PROC_FLOOR=25
SCALEUP_W_CPU=0.60
SCALEUP_W_T_PROC=0.40
SCALEDOWN_COMPUTE_COOLDOWN_S=180
SCALE_DOWN_COMPUTE_REQUIRED=9
SCALEUP_W_STORAGE_CPU=0
SCALEUP_W_T_DB=1.0
SCALEUP_STORAGE_CPU_FLOOR=1.5
SCALEUP_STORAGE_CPU_SPAN=5
SCALEUP_T_DB_FLOOR=60
SCALEUP_T_DB_SPAN=250
SCALEUP_STORAGE_REQUIRED=2
SCALEUP_STORAGE_WINDOW_SIZE=5
SCALEUP_STORAGE_COOLDOWN_S=120
VIP_HARD_TIMEOUT=60
BACKEND_SELECTION_POLICY=<mode>
```

### 5.2 Verification (CP-1 gate)

```bash
for f in rq2_v3_topology_host.env rq2_v3_topology_slowstart.env rq2_v3_topology_lifecycle.env; do
  echo "=== $f ==="
  grep -E "MAX_DYNAMIC|SCALEUP_|SCALEDOWN|SS_ENABLED|BACKEND_SELECTION|VIP_HARD|STORAGE_PERSISTENT" \
    "testing/controller_env_overrides/$f" | sort
done
```

Expected (diff should be empty against golden except for SS_ENABLED=0 and BACKEND_SELECTION_POLICY):

```
BACKEND_SELECTION_POLICY=topology_<mode>
MAX_DYNAMIC_COMPUTE=12
MAX_DYNAMIC_STORAGE=8
SCALEUP_COMPUTE_BASE_THRESHOLD=0.18
SCALEUP_CPU_FLOOR=10
SCALEUP_CPU_SPAN=40
SCALEUP_STORAGE_BASE_THRESHOLD=0.35
SCALEUP_STORAGE_CPU_FLOOR=1.5
SCALEUP_STORAGE_CPU_SPAN=5
SCALEUP_STORAGE_COOLDOWN_S=120
SCALEUP_STORAGE_REQUIRED=2
SCALEUP_STORAGE_WINDOW_SIZE=5
SCALEUP_T_DB_FLOOR=60
SCALEUP_T_DB_SPAN=250
SCALEUP_T_PROC_FLOOR=25
SCALEUP_W_CPU=0.60
SCALEUP_W_STORAGE_CPU=0
SCALEUP_W_T_DB=1.0
SCALEUP_W_T_PROC=0.40
SCALEDOWN_COMPUTE_COOLDOWN_S=180
SCALE_DOWN_COMPUTE_REQUIRED=9
SS_ENABLED=0
STORAGE_PERSISTENT_RESERVE_ENABLED=1
VIP_HARD_TIMEOUT=60
```

**Gate**: if any file differs, do not proceed. Fix and re-verify.

### 5.3 Phases File

`phases_rq2.json` is at `source/scripts/testing/phases_override/phases_rq2.json`.
It is a 9-phase, two-cycle, all-local workload (cross_region_ratio=0.0 for all
phases, rate=4.0 for stress phases). No changes needed — this is the RQ2-tailored
workload and is held constant across all runs.

### 5.4 Images

No Docker image rebuild required. The `EDGE_MAX_CONCURRENT` semaphore from
RQ1 v7 Test B is **not** enabled for RQ2.

---

## 6. Run Matrix

| # | Label | Env Override | Policy |
|---|---|---|---|
| 1 | `rq2_v3_th_1` | `rq2_v3_topology_host.env` | `topology_host` |
| 2 | `rq2_v3_th_2` | `rq2_v3_topology_host.env` | `topology_host` |
| 3 | `rq2_v3_th_3` | `rq2_v3_topology_host.env` | `topology_host` |
| 4 | `rq2_v3_ss_1` | `rq2_v3_topology_slowstart.env` | `topology_slowstart` |
| 5 | `rq2_v3_ss_2` | `rq2_v3_topology_slowstart.env` | `topology_slowstart` |
| 6 | `rq2_v3_ss_3` | `rq2_v3_topology_slowstart.env` | `topology_slowstart` |
| 7 | `rq2_v3_tl_1` | `rq2_v3_topology_lifecycle.env` | `topology_lifecycle` |
| 8 | `rq2_v3_tl_2` | `rq2_v3_topology_lifecycle.env` | `topology_lifecycle` |
| 9 | `rq2_v3_tl_3` | `rq2_v3_topology_lifecycle.env` | `topology_lifecycle` |

**Total**: 9 runs (3 modes × 3 replicates). `v3` prefix distinguishes from
original `rq2_th_1` and v2 `rq2_v2_th_1` labels.

**Run order**: Group by mode — all TH, then all SS, then all TL. Between
every run: cleanup + reboot (see §8).

### Phase Table (`phases_rq2.json`)

| # | Phase | Duration | Rate | Stress |
|---|---|---|---|---|
| 1 | baseline | 60 s | 1.0 | Control |
| 2 | storage_storm | 240 s | 4.0 | Storage |
| 3 | cooldown_1 | 180 s | 1.0 | Drain |
| 4 | compute_spike | 180 s | 4.0 | Compute |
| 5 | cooldown_2 | 180 s | 1.0 | Drain |
| 6 | storage_storm_2 | 240 s | 4.0 | Storage |
| 7 | cooldown_3 | 180 s | 1.0 | Drain |
| 8 | compute_spike_2 | 180 s | 4.0 | Compute |
| 9 | demand_drop | 300 s | 1.0 | Final drain |

Total: 1740 s (**29 min**). All phases: `cross_region_ratio=0.0`.

---

## 7. Run Configuration

### topology_host (Runs 1–3)

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=rq2_v3_th_1 \
  PHASES_CONFIG=testing/phases_override/phases_rq2.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/rq2_v3_topology_host.env \
  WAN_RTT_MS=185 CLIENTS=96 CONTENT_ITEMS=6000 STORAGE_CPUS=0.08 EDGE_CPUS=0.30 \
  CURL_MAX_TIME=30 RANDOM_SEED=42 \
  > /tmp/rq2_v3_th_1.log 2>&1 &"
```

Repeat for `rq2_v3_th_2`, `rq2_v3_th_3`.

### topology_slowstart (Runs 4–6)

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=rq2_v3_ss_1 \
  PHASES_CONFIG=testing/phases_override/phases_rq2.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/rq2_v3_topology_slowstart.env \
  WAN_RTT_MS=185 CLIENTS=96 CONTENT_ITEMS=6000 STORAGE_CPUS=0.08 EDGE_CPUS=0.30 \
  CURL_MAX_TIME=30 RANDOM_SEED=42 \
  > /tmp/rq2_v3_ss_1.log 2>&1 &"
```

Repeat for `rq2_v3_ss_2`, `rq2_v3_ss_3`.

### topology_lifecycle (Runs 7–9)

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=rq2_v3_tl_1 \
  PHASES_CONFIG=testing/phases_override/phases_rq2.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/rq2_v3_topology_lifecycle.env \
  WAN_RTT_MS=185 CLIENTS=96 CONTENT_ITEMS=6000 STORAGE_CPUS=0.08 EDGE_CPUS=0.30 \
  CURL_MAX_TIME=30 RANDOM_SEED=42 \
  > /tmp/rq2_v3_tl_1.log 2>&1 &"
```

Repeat for `rq2_v3_tl_2`, `rq2_v3_tl_3`.

- `--fault-plan`: omitted.
- No `SKIP_CLIENTS`/`SKIP_SEED`/`SKIP_SNAPSHOT` — full setup per run.
- `EDGE_MAX_CONCURRENT`: not set (no concurrency limit).

---

## 8. Between-Run Protocol

Apply **between every run** (not just between modes):

1. Verify run folder contains all standard artifacts.
2. `source/scripts/cleanup.sh` (~30 s).
3. Reboot cloud VM (~2–3 min).
4. Verify Docker daemon running (`docker info` succeeds).
5. Verify OVS bridges clear (`ovs-vsctl show` shows no stale bridges).
6. Retry steps 4–5 up to 3 times at 30 s intervals. **If still failing after
   3 retries, abort the campaign and investigate.** Do not proceed with
   degraded infrastructure.

---

## 9. Focus & Evidence

### Primary Artifacts

`controller_lan*.log` + `per_node_stats.csv` → `cli_rq2_redistribution.py`:

```bash
python3 -m source.scripts.testing.analysis.rq2.cli_rq2_redistribution \
  <run_folder>
```

Run per-folder after each run completes. Outputs per run:
- `analysis/rq2_redistribution_profile.csv` — per-event, per-window load share
- `analysis/rq2_redistribution_summary.csv` — per-event TTFT, initial share
- `analysis/rq2_redistribution_aggregates.csv` — per-mode aggregate stats

After all 9 runs, aggregate across the campaign with:
```bash
python3 -m source.scripts.testing.analysis.rq2.campaign_analysis \
  <run_folder_1> <run_folder_2> ... <run_folder_9>
```

### Secondary Artifacts

- `client_requests.csv` → per-phase, per-LAN p50/p95/p99 via `metrics_stats.py`
- `container_events.csv` → verify no `sel_sync_` containers (`SS_ENABLED=0`)
- `elasticity_events.csv` → cross-reference spawn events
- `controller_env_snapshot.env` → verify `BACKEND_SELECTION_POLICY`,
  `SCALEUP_CPU_SPAN=40`, `SS_ENABLED=0`, `MAX_DYNAMIC_COMPUTE=12`
- `phases_snapshot.json` → verify correct phases file

### Thesis Graphs Produced

| Graph | Measurement | Type |
|---|---|---|
| G1 — TTFT Distribution by Mode | §10.1 | Box plot per mode + scatter dots |
| G2 — Initial Load Share Distribution by Mode | §10.1 | Box plot per mode + scatter dots |
| G3 — Coordination Gap Decomposition | §10.1 | Grouped bar (time + share) |
| G4 — Readiness Mismatch by Mode | §10.2 | Box plot per mode + scatter dots |
| G5 — Non-Stress p50 Latency by Mode | §10.2 | Grouped bar per phase |
| G6 — Per-Phase p50 Latency by Mode | §10.3 | Grouped bar, all phases |
| G7 — Per-Mode Latency Percentiles (p50/p95/p99) | §10.3 | Grouped bar per mode |
| G8 — Stress vs Non-Stress p95 by Mode | §10.3 | Grouped bar, two conditions |

---

## 10. How It Is Measured

Four measurements answer the question, following the pattern established in
[RQ1](../../../../research_questions/rq1.md#5-how-it-is-measured). **Measurement 1
(TTFT + Initial Load Share) is the core thesis evidence** — the others provide
confirmation, context, and user-visible impact assessment. Each measurement
names the thesis-level graph that visualises it.

### 10.1 Traffic Allocation at Spawn — Core Evidence (Awareness Timing)

This measurement captures the **coordination gap** — how quickly and how
forcefully a newly spawned backend receives traffic. It directly answers the
thesis question: does spawn-time routing awareness produce faster, higher-volume
load redistribution than discovery-time awareness?

**TTFT (Time-to-First-Traffic):**

```
ttft = t(first_request_arrives_at_new_backend) − spawn_done_ts
```

Computed per spawn event from `controller_lan*.log` (spawn_done timestamp,
backend MAC) and `per_node_stats.csv` (first telemetry window with
`request_count > 0` for that MAC). The telemetry window cadence (~10 s) is the
natural resolution.

**Initial Load Share:**

```
initial_share = new_backend_request_count / total_VIP_requests_in_first_window
```

The fraction of VIP traffic the new backend captures in its first visible
telemetry window. Computed per spawn event from the same artifacts.

**What each mode encodes in these two metrics:**

| Mode | TTFT driver | Initial share driver | Expected TTFT | Expected share |
|---|---|---|---|---|
| `topology_host` | Round-robin counter state — backend wins when its turn arrives. High variance (0–251 s in original run). | ~1/N fair share (~30% at N≈3). Every backend ties at cost 0.0; round-robin distributes evenly. | 51 s median | ~30% |
| `topology_slowstart` | Discovery delay (~10 s avg) + ramp duration. Backend invisible until first telemetry. Consistent, predictable. | Graduated ramp — starts low, builds to full weight. Invisible until discovery, then penalty decays over 45 s. | 71 s median | ~55% |
| `topology_lifecycle` | Warm lease at t=0 — selected immediately via WSM bypass. Consistent, fastest. | Priority routing — WSM short-circuited during warm lease. Highest immediate share. | 40 s median | ~73% |

**Why both metrics together:** TTFT alone doesn't tell the full story. A
backend could receive its first request quickly (low TTFT) but capture only
a trickle of traffic (low share). Conversely, a backend could wait longer
(high TTFT) but then receive a flood (high share). The two metrics together
characterise both *when* redistribution begins and *how aggressively* it
proceeds — the speed and the magnitude of the routing response.

**Variance is a first-class finding.** Host's round-robin mechanism produces
inherently variable TTFT (counter-dependent). Lifecycle's warm lease is
deterministic. The variance difference between modes is as informative as the
median difference — it reveals whether the routing mechanism provides
*predictable* load redistribution or a *lottery*.

**Thesis-level graphs:**

| Graph | Type | What it shows |
|---|---|---|
| **G1 — TTFT Distribution by Mode** | Box plot (or violin) per mode, individual spawn events as scatter dots | Central tendency AND variance. Host's wide IQR (round-robin lottery) vs lifecycle's tight cluster (deterministic warm lease). The variance IS the finding. |
| **G2 — Initial Load Share Distribution by Mode** | Box plot per mode, individual spawn events as scatter dots | How aggressively each mode redirects traffic. Lifecycle's high median + tight IQR vs host's low median + wide spread. |
| **G3 — Coordination Gap Decomposition** | Grouped bar: ΔTTFT and ΔInitialShare between mode pairs | The coordination gap expressed as **time lost** (TTFT_slowstart − TTFT_lifecycle) AND **throughput lost** (InitialShare_lifecycle − InitialShare_slowstart). Parallels RQ1's breach-detection penalty as the routing-plane analogue. |

**Success criteria:**

| ID | Criterion | Operational definition | Expected |
|---|---|---|---|
| C1 | Lifecycle fastest TTFT | Per-mode median TTFT across all compute spawn events, all reps | lifecycle < host < slowstart |
| C2 | Coordination-gap penalty | TTFT_median(slowstart) − TTFT_median(lifecycle) | ≥ 20 s |
| C3 | Lifecycle highest initial share | Per-mode mean initial share across all compute spawn events | lifecycle > slowstart > host |

### 10.2 Readiness Alignment — Secondary (Readiness Timing)

This measurement captures the second timing dimension: **when the backend is
actually ready to serve** relative to when traffic arrives. It answers: does
the routing mechanism align traffic arrival with backend warm-up, or does it
send traffic to a cold backend?

**Readiness Mismatch:**

```
mismatch = window_end_ts − spawn_done_ts
```

Where `window_end_ts` is the closing boundary of the first telemetry window in
which the backend appears with `request_count > 0`. This uses the telemetry
window cadence (~10 s) as the natural resolution of the readiness measurement.
Small mismatch = traffic arrived in or near the first window after spawn.

**What each mode encodes:**

| Mode | Traffic starts | Backend warm at | Mismatch | Mechanism |
|---|---|---|---|---|
| `topology_host` | t≈0 s | t≈5–10 s | **5–10 s gap** | Round-robin sends traffic immediately to a cold backend. Fair-share dilution means no single backend gets enough concentrated load to warm its DB pool and caches quickly. Backend serves cold — elevated latency until caches populate. |
| `topology_slowstart` | t≈10 s | t≈5–10 s | **~0 s gap** | Discovery delay (~10 s) doubles as a warm-up window. By the time the backend becomes visible and receives traffic, its DB connection pool and caches are already warm. Best alignment — but by accident, not by design. |
| `topology_lifecycle` | t≈0 s | t≈2–3 s | **~2 s gap** | Warm lease concentrates traffic on the new backend immediately, accelerating cache population. Small initial gap, fast convergence — the backend warms up *because* it receives priority traffic, not before. |

**The cold-start penalty is visible in non-stress latency.** Under low load
(baseline, cooldowns, demand_drop), the dominant latency factor is backend
readiness — whether the DB connection pool is populated and caches are hot.
Under high load (storage_storm, compute_spike), MongoDB I/O dominates and
masks the readiness effect. Non-stress p50 is therefore the **user-visible
proxy for readiness alignment**.

**Thesis-level graphs:**

| Graph | Type | What it shows |
|---|---|---|
| **G4 — Readiness Mismatch by Mode** | Box plot per mode, individual spawn events as scatter dots | Quantifies the traffic-arrival-to-warm-up gap. Slowstart's near-zero mismatch (serendipitous alignment) vs host's large positive gap (cold serving) vs lifecycle's small gap (accelerated warm-up). |
| **G5 — Non-Stress p50 Latency by Mode** | Grouped bar per non-stress phase (baseline, cooldowns, demand_drop), three bars per phase (host/slowstart/lifecycle) | The user-visible consequence of readiness mismatch. Host's elevated p50 (cold backends) vs slowstart/lifecycle's low p50 (warm backends). This graph makes the readiness penalty tangible — it answers "does the user notice?" |

**Success criteria:**

| ID | Criterion | Operational definition | Expected |
|---|---|---|---|
| C4 | Host elevated non-stress p50 | Per-mode p50 latency for baseline+cooldowns+demand_drop phases, LAN1, all reps | host > slowstart AND host > lifecycle; slowstart vs lifecycle within 20% |
| C8 | Host largest readiness mismatch | Per-mode median mismatch across all compute spawn events | host > lifecycle > slowstart |
| C9 | Slowstart near-zero mismatch | slowstart median mismatch | ≤ 10 s (one telemetry window) |

### 10.3 Per-Phase Service Quality — User-Visible Impact

This measurement captures the **end-user experience** across the full workload
timeline. It answers: do the routing mechanisms produce different latency
profiles under different load conditions, and do they converge when MongoDB
I/O dominates?

**Per-phase p50/p95/p99 latency** from `client_requests.csv`, disaggregated by
phase, LAN, and mode. Computed via `metrics_stats.py`.

**Phase-dependent latency regimes:**

| Phase type | Phases | Dominant latency factor | Expected mode effect |
|---|---|---|---|
| **Non-stress** | baseline, cooldown_1/2/3, demand_drop | Backend readiness (DB pool, caches) | **host >> slowstart ≈ lifecycle**. Host routes to cold backends; slowstart/lifecycle backends are warm. p50 differential is the readiness penalty. |
| **Storage stress** | storage_storm, storage_storm_2 | MongoDB I/O (content_update, content_aggregate at 4.0 rps) | **All modes converge.** Storage I/O dominates — the routing choice is irrelevant. p95 ~2500 ms in all modes. |
| **Compute stress** | compute_spike, compute_spike_2 | CPU saturation (feed_ranking, service_pressure) | **Modes may diverge** if uneven load distribution creates hotspots. Lifecycle's concentrated routing could overload individual backends; host's round-robin could spread CPU load more evenly. This is the phase where routing quality matters most for compute-bound workloads. |

**Why phase disaggregation matters:** A whole-run average conflates non-stress
phases (where routing quality dominates) with storage phases (where I/O
dominates). The per-phase breakdown reveals *when* routing matters and *when*
it doesn't — bounding the scope of the routing-plane coordination gap.

**Thesis-level graphs:**

| Graph | Type | What it shows |
|---|---|---|
| **G6 — Per-Phase p50 Latency by Mode** | Grouped bar chart, one group per phase (9 phases), three bars per group (host/slowstart/lifecycle) | The full timeline. Mode differences visible in non-stress phases (readiness effect), convergence in storage_storm (I/O dominance), possible divergence in compute_spike (load distribution effect). This is the **master service-quality graph** — the single most informative visualisation of RQ2's user-visible impact. |
| **G7 — Per-Mode Latency Percentiles (p50/p95/p99)** | Grouped bar chart, one group per mode, three bars per group (p50, p95, p99) | Aggregate view across all phases. Shows that p95/p99 are storage-dominated (~2500 ms in all modes, mode-independent) while p50 reflects routing quality. Demonstrates that routing choice affects **median** experience but not **tail** latency — the tail is storage-bound regardless of routing policy. |
| **G8 — Stress vs Non-Stress p95 by Mode** | Grouped bar chart, two groups (stress phases pooled, non-stress phases pooled), three bars each | Confirms convergence under stress and divergence under low load. Stress p95 bars nearly equal height; non-stress p95 bars show host penalty. |

**Success criteria:**

| ID | Criterion | Operational definition | Expected |
|---|---|---|---|
| C5 | All modes converge in storage stress | Per-mode p50 for storage_storm+storage_storm_2 phases, any LAN | max(host,slowstart,lifecycle) / min(host,slowstart,lifecycle) ≤ 3.0 |
| C6 | p95 within 15% across modes | Per-mode p95 per phase, all LANs | max/min ratio ≤ 1.15 for each phase independently |

**C5 rationale**: In the original run, storage-phase p50 ranged from ~200 ms
to ~600 ms across modes — a 3× spread driven partly by aggressive scoring.
With corrected scoring (CPU_SPAN=40), convergence should be tighter. The
≤ 3.0 threshold is intentionally loose — it tests whether convergence exists
at all, not whether it's perfect.

**C6 rationale**: The original run showed p95 ~2500 ms across all modes —
well within 15%. This criterion verifies that storage-bound tail latency
remains mode-independent regardless of scoring correction.

### 10.4 Failure Rate — Safety Check

HTTP status ≠ 200 count / total requests, per mode, from `client_requests.csv`.
Expected ≤ 0.1% across all modes (30 s client timeout ceiling).

| ID | Criterion | Operational definition | Expected |
|---|---|---|---|
| C7 | Zero failures | HTTP status ≠ 200 count / total requests, per mode | ≤ 0.1% |

**Graph**: Not a standalone thesis graph — reported as a statistic in the
results narrative. If failures exceed 0.1%, a per-phase failure breakdown
becomes a supplementary graph and the analysis investigates whether failures
correlate with specific routing modes or phases.

### 10.5 Measurement Chain (Causal Model)

```text
BACKEND_SELECTION_POLICY
  │
  ├─→ Awareness Timing (§10.1)
  │     ├─ TTFT (G1) ─────────── when does redistribution begin?
  │     ├─ Initial Load Share (G2) ─ how much traffic moves?
  │     └─ Coordination Gap (G3) ── time lost + throughput lost
  │
  ├─→ Readiness Alignment (§10.2)
  │     ├─ Mismatch (G4) ──────── does traffic hit a warm backend?
  │     └─ Non-Stress p50 (G5) ── do users notice cold backends?
  │
  └─→ Service Quality (§10.3)
        ├─ Per-Phase p50 (G6) ─── when does routing matter?
        ├─ Aggregate Percentiles (G7) ─ median vs tail
        └─ Stress vs Non-Stress p95 (G8) ─ convergence vs divergence
```

The causal interpretation: `BACKEND_SELECTION_POLICY` determines **when**
routing becomes aware of a new backend (awareness timing) and **how** traffic
arrives (concentrated via warm lease vs diluted via round-robin), which
determines **whether** the backend is warm when traffic hits (readiness
alignment), which determines **what** latency users experience (service
quality).

The coordination gap (§10.1) is the **direct mechanism** — the delay between
spawn and routing action. Readiness (§10.2) is the **mediating variable** —
the backend's internal state when that action occurs. Service quality (§10.3)
is the **user-visible outcome**. All three are necessary to fully answer RQ2:
a mechanism without user impact is academic; user impact without mechanism is
unexplained.

This three-tier structure mirrors RQ1's measurement chain (missed windows →
breach detection → timeout rate) and enables the cross-RQ synthesis the thesis
requires: RQ1 measures the monitoring gap, RQ2 measures the routing gap, RQ3
measures the detection gap — together characterising whether collapsing three
control-plane concerns eliminates delays that matter in practice.

### 10.6 Sanity Checks

| ID | Check | Artifact | Expectation |
|---|---|---|---|
| S1 | Golden scoring applied | `controller_env_snapshot.env` | `SCALEUP_CPU_SPAN=40`, `SCALEUP_CPU_FLOOR=10`, `SCALEUP_STORAGE_BASE_THRESHOLD=0.35`, `MAX_DYNAMIC_COMPUTE=12` |
| S2 | Policy applied | `controller_env_snapshot.env` | `BACKEND_SELECTION_POLICY` matches label |
| S3 | No Tier 1 | `container_events.csv` | Zero `sel_sync_` containers |
| S4 | Scale-ups occurred | `elasticity_events.csv` | ≥ 2 unique `spawn_done` events per run |
| S5 | Spawn count consistent | `elasticity_events.csv` | IQR of spawn count within mode < 50% of mode median |

**S4 note**: At CLIENTS=96 with corrected scoring, spawn counts will be lower
than the original run's 222–301 events (which fired on every minor CPU bump).
≥ 2 per run yields ≥ 6 per mode across 3 reps — sufficient for median/IQR of
TTFT and initial share. The v7 experience (4 spawns/run at rate=2.0
compute_spike) suggests RQ2's rate=4.0 at CLIENTS=96 should produce more.

---

## 11. Checkpoints

| # | Trigger | Question | Action |
|---|---|---|---|
| **CP-1** | Before ANY run | Do all three RQ2 v3 env override files match golden + RQ2 overrides? Run verification from §5.2. | **Gate: if any file differs, fix it and re-verify. Do NOT launch any run until CP-1 passes.** |
| CP0 | After `rq2_v3_th_1` | ≥ 2 unique spawn_done events? `SCALEUP_CPU_SPAN=40` confirmed in `controller_env_snapshot.env`? | Gate: if spawns < 2, assess whether CLIENTS=96 needs adjustment (unlikely). If scoring wrong, abort and fix env files. |
| CP1 | After first mode's 3 reps | TTFT and initial share consistent across replicates? (IQR < 50% of median for both metrics) | If variance extreme: check for external noise. Consider 4th replicate. |
| CP2 | After second mode's 3 reps | Do TTFT and initial share differ visibly between modes? | Qualitative check. Continue to lifecycle regardless. |
| CP3 | End of campaign | Golden scoring + policy confirmed for all 9 `controller_env_snapshot.env` files? | Cross-check. Flag any deviation. |

---

## 12. Failure Recovery

1. Note failure: run label, elapsed time, last phase, errors from controller logs.
2. Run cleanup + reboot as usual.
3. Retry with identical `RUN_LABEL` (new timestamp → new folder). Mark failed
   folder with `FAILED_` prefix or delete.
4. If same run fails twice: skip it. Collect 2 reps for that mode.
5. If a mode loses >1 rep: flag as under-sampled in analysis.
6. If Docker/OVS fails to recover after 3 retries (§8 step 6): **abort
   campaign** and investigate host state.

---

## 13. Validity Threats & Limitations

| Threat | Mitigation |
|---|---|
| **CLIENTS=96 may overwhelm with rate=4.0** | 96 clients × 4.0 rps = 384 req/s per LAN. Original RQ2 at CLIENTS=48 failed LAN2 under broken scoring. With corrected scoring (CPU_SPAN=40), fewer spawns but each spawn is meaningfully driven by real load. If runs fail: reduce CLIENTS to 48 — but document as a deviation from golden. |
| **Corrected scoring reduces spawn count below useful threshold** | S4 gates at ≥ 2 per run. If all modes fail S4, workload needs recalibration. Unlikely given v7 produced 4 spawns at rate=2.0 — RQ2's rate=4.0 should produce more. |
| **Ordinal findings may not replicate** | Routing mechanisms (warm lease, discovery gap, round-robin) are independent of scoring. Ordinal ranking should hold. Magnitudes may shift with CLIENTS=96. |
| **Host within-mode variance** | Round-robin tie-breaking is inherently timing-dependent. If variance persists with corrected scoring, confirms it is a genuine property, not a scoring artifact. |
| **SS_ENABLED=0 not representative of production** | Acknowledged. Tier 1 disabled to isolate routing mechanism. Production would have SS_ENABLED=1, which RQ1 already evaluates. |
| **Three replicates may miss small effects** | Large effects (share, host p50) conclusive at n=3. p95 differences honestly reported as null. |
| **Env override files silently diverge from golden** | CP-1 gatekeeps. `controller_env_snapshot` captured per run as audit trail. |
| **WAN_RTT_MS=185 with all-local traffic** | WAN_RTT affects storage sync between LANs but not request latency (cross_region_ratio=0.0). Held constant — does not confound mode comparisons. |

---

## 14. Artifact Contract

Standard run-folder layout per `testing_overview.md`. Analysis outputs
generated by `cli_rq2_redistribution.py` per run, then aggregated across
the campaign via `campaign_analysis`.

Post-analysis cleanup: remove transient `client_requests.csv` and
`controller_lan*.log` files after the run summary is produced, per the
`metrics-run-summary` skill workflow.

---

## 15. References

- RQ2 definition: [`docs/research_questions/rq2.md`](../../../../research_questions/rq2.md)
- RQ1 v7 plan (golden config source): [`docs/operation/testing/experiment/rq1_thesis_final/v7/experiment_plan_v7.md`](../../rq1_thesis_final/v7/experiment_plan_v7.md)
- Golden env: [`source/scripts/testing/controller_env_overrides/current_state_integrated.env`](../../../../source/scripts/testing/controller_env_overrides/current_state_integrated.env)
- Phases: [`source/scripts/testing/phases_override/phases_rq2.json`](../../../../source/scripts/testing/phases_override/phases_rq2.json)
- VIP routing selection: [`source/sdn_controller/_vip_routing/selection.py`](../../../../source/sdn_controller/_vip_routing/selection.py)
- Original results (invalidated scoring): [`../v1/results.md`](../v1/results.md)
- v2 plan (superseded): [`../v2/experiment_plan_v2.md`](../v2/experiment_plan_v2.md)
