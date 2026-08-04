# RQ3 — Readiness Propagation and Traffic Admission: Implementation Plan

> **Status:** Approved plan — to be implemented.
> **Scope:** RQ3 "required extension" from `tese/Notes/thesis_overview.md`.
> **Prerequisites:** RQ1 (`docs/research_questions/v2/rq1/rq1_prepation.md`) and
> RQ2 (`docs/research_questions/v2/rq2/rq2_preparation.md`) are **IMPLEMENTED**.
> This plan builds on RQ1's `_log_decision`/`DECISION_LOG_PATH`, `window_id`,
> event-preserving delivery, `_housekeeping_loop` ticker, and the RQ1/RQ2
> artifact collection in `run_experiment.sh`; and on RQ2's `PolicyGate`,
> `_SCALEUP_POLICY`, and mode-aware `_log_decision`.
> **Date:** 2026-07-31.
> **RQ3 v2 sync (2026-08-04):** the mechanism here is implemented. The v2
> evaluation design (`docs/operation/testing/experiment/v2/rq3/rq3_v2_rework_plan.md`,
> approach A) extends the **direct** arm to be genuinely event-driven — the
> edge emits an `app_ready` control event (`EDGE_APP_READY_EVENT=1`) at the
> readiness flip; the controller admits on the event (no probe before
> admission) with an event-absence safety net (`READINESS_EVENT_FALLBACK_S=5`),
> and the admission log records `admit_source` (`event` | `probe_fallback` |
> `probe`). **D3 invariant break (recorded):** under event-driven `direct`,
> `app_ready_ts` is an **event** observation time, not a probe observation, so
> the "`app_ready_observed → admitted` ≈ 0 in both arms" invariant applies to
> `discovery` only. **T12.4 superseded:** the cross-arm `spawn_complete →
> app_ready_observed` overlap check is dropped as a statistic — replaced by the
> post-admission confirming `/ready` probe + the `admit_source` event-fraction
> gate (see the v2 plan §2.2/§2.4). **§5 measurement contract updated:** the
> headline is the gap-window pool `timeout_rate` differential
> (`[spawn_started, min(admitted, spike_end)]`), and useful initial share is
> pool-wide over `[spawn_started, admitted + TRANSITION_WINDOW_S]` — not the
> new backend's post-admission window only. The v2 campaign runs on
> `cloud-vm-rq3` under the open-loop driver.

This plan implements the RQ3 required extension: a **compute readiness gate**
that gates `VIP_SERVER` pool admission on a verified **application-readiness
event**, under two switchable propagation modes (**direct lifecycle
notification**, **periodic discovery**), a **flow-isolation measurement mode**
that forces one fresh backend-selection event per measured request, and a
per-node **admission log** recording spawn/app-ready/admitted timing.

`READINESS_PROPAGATION=off` (the **default**) preserves the current behavior
exactly — Thread 3 registers a spawned compute backend into the pool
immediately (`register_new_server_backend`), no probe, no admission log, no
flow isolation, no readiness worker thread. Canonical / RQ1 / RQ2 runs are
byte-identical. The two RQ3 arms are explicitly selected per run; each run uses
exactly one arm.

This plan is **not phased** (like RQ1/RQ2); no phase/order prefixes apply to
controller modules (import-safe names). New experiment/analyzer/env/phase files
carry the `rq3_` scope prefix. The plan doc itself is `rq3_preparation.md`.

---

## 1. Locked decisions

- **D1 — Propagation modes (switchable, per run):**
  - `READINESS_PROPAGATION=off` (**default**) — current pre-RQ3 behavior: after
    `add_edge_server` succeeds, Thread 3 calls `register_new_server_backend(mac,
    ip)` immediately (no readiness probe, no admission log, no readiness worker
    thread, no flow isolation). Preserves canonical + RQ1 + RQ2 runs unchanged.
    **Not** an RQ3 comparison arm.
  - `READINESS_PROPAGATION=direct` — after spawn, the readiness gate probes the
    backend's `/ready` endpoint immediately and on a tight retry cadence
    (`READINESS_PROBE_RETRY_S`, default `1.0`); on `200` the backend is admitted
    to the `VIP_SERVER` pool. **Direct lifecycle notification.**
  - `READINESS_PROPAGATION=discovery` — after spawn, direct registration is
    suppressed; a periodic discovery worker probes `/ready` on a fixed cadence
    (`DISCOVERY_POLL_INTERVAL_S`, default `10.0`); the backend is admitted only
    when a discovery pass observes `200`. **Periodic discovery.**
  The two RQ3 arms are the comparison set; a run never mixes arms. Unknown value
  → log error + fall back to `off` (deliberate, documented).
- **D2 — Identical readiness criterion (hard requirement):** both arms use the
  **same** `/ready` probe with identical semantics. `/ready` returns `200` only
  when the edge server is application-ready, defined by a single testable flag:
  `EdgeServerProcessState.app_ready` is `True` only after (a) Flask routes are
  registered, (b) the first MongoDB operation through the `VIP_DATA` epoch
  runtime completes successfully (a real DB round-trip), and (c) the telemetry
  sender is initialized. `/ready` returns `200` iff `app_ready` is `True`;
  otherwise `503`. `off` mode
  does **not** probe at all (no `/ready` dependency). The probe is
  `GET http://<backend_ip>:<EDGE_READY_PORT>/ready` with
  `READINESS_PROBE_TIMEOUT_S` (default `5.0`) per attempt.
  `EDGE_READY_PORT` (default `5000`) must equal the edge server's `BIND_PORT`
  for RQ3 runs (pinned to `5000`, T8). A pending backend that does not become
  ready within `READINESS_PROBE_MAX_S` (default `120.0`) is **abandoned**: the
  gate calls `on_abandon(pb)` which tears the node down fully (OVS veth/port +
  host entries + container) and releases the IP (T3) — the node must **not**
  leak. `READINESS_PROBE_MAX_S` must
  exceed `DISCOVERY_POLL_INTERVAL_S` and typical app-startup time.
- **D3 — The probe/admission cadence is the independent variable:** `direct`
  admits on the tight retry cadence (`READINESS_PROBE_RETRY_S`); `discovery`
  admits on the coarse scan cadence (`DISCOVERY_POLL_INTERVAL_S`). Both arm env
  files set BOTH cadence knobs to the same fixed values; only
  `READINESS_PROPAGATION` differs, selecting which cadence is used. **Primary
  observable metric:** `spawn_complete → admitted`. The true app-ready instant
  is **unobservable between probes** (it can only be detected at probe times),
  so `app_ready_ts` is the *first probe observation* of readiness and
  `app_ready_observed → admitted` is ≈ `0` in both arms (documented). The
  treatment effect appears in the quantization of `spawn_complete → admitted`:
  ≈ app-startup + `[0, READINESS_PROBE_RETRY_S]` in `direct` vs ≈ app-startup +
  `[0, DISCOVERY_POLL_INTERVAL_S]` in `discovery`. `probe_first_ts`,
  `app_ready_ts`, and `admitted_ts` are all logged; the analyzer reports the
  raw distributions, not a fabricated `app_ready → admitted`.
- **D4 — Backend-selection operating point (identical in both arms):**
  `BACKEND_SELECTION_POLICY=topology_host` (unknown-stats **best-case `0.0`** →
  a newly admitted backend is strongly preferred by WSM until it acquires
  telemetry) **and** `VIP_WARM_SERVER_SECONDS=0` (explicitly no warm lease).
  Rationale (verified in `_vip_routing/selection.py`): with no warm lease in
  `topology_lifecycle` mode, a new backend gets worst-case unknown stats `1.0`
  and **starves** (never ties, never wins WSM, never gets telemetry). Round-robin
  tie-breaking (`_rr_server_idx`) only fires on **truly equal** costs, which a
  worst-case new backend is not. `topology_host` avoids starvation: the new
  backend wins on resource dimensions (best-case `0.0`) as soon as it is
  admitted. **Precision:** the new backend is strongly preferred, not
  unconditional — its `hops` component uses the real hop count once the MAC is
  in `host_attachment` (topology polls every `TOPOLOGY_INTERVAL` = 1 s, and the
  container is attached before enqueue, so by the time `/ready` returns `200`
  — seconds later — attachment is populated). T12 validates that at admission
  the backend is in `host_attachment` (real hops, not `hops_max`). Under
  extremely light load, equal-cost ties resolve by round-robin — arm-identical,
  so it does not confound the comparison. This satisfies the thesis's
  "warm-lease priority and slow-start ramps disabled in both conditions" while
  keeping the WSM cost function and weights identical.
- **D5 — Flow isolation (measurement instrumentation, identical in both arms):**
  `VIP_FLOW_ISOLATION=1` in both RQ3 arm env files, active for the **whole RQ3
  run** in both arms (so there are never pre-existing flows to exclude; the
  thesis's "existing flows are excluded before the timing interval" is satisfied
  trivially). **Client precondition (required by the mechanism):** the RQ3
  measurement window uses **one fresh TCP connection per request, closed after
  the response** (no keep-alive reuse, no pipelining) — matching the existing
  per-request `ip netns exec curl` driver; concurrent in-flight requests from a
  single client are not used. Mechanism: the edge server emits a
  `request_complete` control event (carrying `client_ip`) **after the response
  has been flushed** (emitted from a short-lived background thread, T4), **only
  when** the edge-container env `EDGE_FLOW_ISOLATION=1` (default `0`, so
  non-RQ3 runs never emit it and stay byte-identical). The aggregator whitelists
  `request_complete`; the controller, when `VIP_FLOW_ISOLATION=1`, deletes that
  client's `VIP_SERVER` DNAT+SNAT flows **using the exact recorded client→backend
  mapping** (T6) → the next request from that client re-triggers backend
  selection. **Why:** the `VIP_SERVER` flow match is per-client, not
  per-connection (`flows.py` `install_vip_dnat_snat`: `eth_src=client_mac,
  ipv4_src=client_ip, ipv4_dst=vip_ip, ip_proto` — no source port), so a fresh
  TCP connection from the same client within the 30 s idle window is pinned to
  the same backend with no new selection event. Without flow isolation, flow
  affinity would be indistinguishable from a readiness-propagation effect.
  **Controller overhead:** the controller is never in the data path — only the
  first packet (SYN) of each flow generates a packet-in; after flow install,
  OVS carries every data packet at line rate. Flow isolation adds exactly one
  packet-in + one `request_complete` control event per request, uniform across
  both arms, and the run's offered load is calibrated to stay well below the
  controller's packet-in throughput (a known, RQ1-measured quantity).
  **Misconfiguration guard:** if `VIP_FLOW_ISOLATION=1` but no `request_complete`
  events arrive within a warmup period, `process_flow_events` logs a warning
  (T6) — a forgotten `EDGE_FLOW_ISOLATION=1` cannot silently invalidate the run.
  **Asynchronous-delete caveat:** the flow delete is asynchronous (control event
  → Thread 2), so a client's very next request can occasionally re-match the
  still-present flow before the delete lands — bounded, arm-identical
  (measurement instrumentation), and surfaced by `rq3_flow_validation.py`
  Check C (delete coverage < requests).
- **D6 — Admission log (new artifact, separate from RQ2's decision log):**
  `ADMISSION_LOG_PATH` (default `/tmp/admission_log.csv`), written by the
  readiness gate (controller-side, per LAN). One row per dynamically spawned
  compute backend (including abandoned backends, so leaks are visible). Written
  only when the gate is active (`READINESS_PROPAGATION != "off"`), so non-RQ3
  runs produce no admission log and no new writer. `network_id` uses the
  controller's LAN id (`lan1`/`lan2`), consistent with the decision log. This
  log is **additive** — it does not alter RQ2's `decision_log.csv` contract.
- **D7 — Confounders disabled + controlled interfaces:** `SS_ENABLED=0`,
  `STORAGE_PERSISTENT_RESERVE_ENABLED=0`, `CROSS_REGION_STORAGE_ENABLED=0`.
  Telemetry delivery = `TELEMETRY_SOURCE=event_preserving` (RQ1 reference arm).
  Scaling-action selection = `SCALEUP_POLICY=dual` (RQ1 reference) — RQ3 does
  **not** drag in RQ2's treatment; the scaling interface is held at the RQ1
  reference. The RQ3 episode is compute-bound so storage scale-up does not fire;
  the analyzer focuses on compute admissions regardless. Backend-admission
  condition is the only varied interface.
- **D8 — Compute-only subject, same-LAN:** RQ3 studies compute (`edge_server`)
  backend admission for clients and backends on the same LAN (the default
  workload). The storage admission path (`rs_secondary_ready`, deferred
  `VIP_DATA` promotion) is a distinct readiness event and is **out of scope**,
  held constant (unchanged). Cross-network `VIP_SERVER` flows are out of scope
  (the RQ3 `delete_vip_server_client_flows` facade handles this controller's own
  per-LAN `VIP_SERVER` only; documented in T6).
- **D9 — Scope:** RQ3 measures the **readiness-propagation + traffic-admission
  interface only**. It changes neither the readiness criterion between arms
  (same `/ready`, D2) nor the backend-selection function (identical WSM, D4),
  nor telemetry (D7), nor scaling (D7). The thesis's "decouple propagation from
  backend-selection policy, warm-lease priority, and ramp behavior" is satisfied
  by D4 (fixed operating point, no lease, no ramp) and D5 (identical flow
  isolation).

---

## 2. Architecture

### 2.1 Two-layer split (spawn → readiness gate → admission)

`_handle_compute` (Thread 3) keeps spawn mechanics unchanged; a new
`ReadinessGate` performs **probe + admission timing**; the mediator admits via
the existing `register_new_server_backend` path. When `READINESS_PROPAGATION=off`
the mediator takes the legacy path unchanged (byte-identical).

```text
_handle_compute()                                [Thread 3, elasticity.py]
  │  name/ip/mac allocation, add_edge_server() — UNCHANGED
  │  (fail → release ip, error log — UNCHANGED)
  │
  ├─ self.readiness_gate is None (READINESS_PROPAGATION == "off")
  │    → _admit_compute_backend(mac, ip, ...)     [current behavior, unchanged]
  │
  └─ RQ3 arms (self.readiness_gate is not None):
      ├─ ReadinessGate.enqueue(PendingBackend(...))   [do NOT register yet]
      └─ ReadinessGate worker (native daemon thread, per controller):
          ├─ probe GET /ready  (identical probe, both arms — D2)
          ├─ direct:     probe immediately (Condition wake on enqueue),
          │              retry every READINESS_PROBE_RETRY_S; on 200 → _admit
          ├─ discovery:  probe on DISCOVERY_POLL_INTERVAL_S cadence; on 200 during
          │              a pass → _admit
          ├─ abandon if now - spawn_complete > READINESS_PROBE_MAX_S
          │    → on_abandon(pb): release IP + remove container (T3)
          └─ _admit(pb):
              ├─ write admission_log row (probe_first/app_ready/admitted, ...)
              ├─ mediator._admit_compute_backend(mac, ip, name, lan, network_id,
              │                                 source="readiness_gate")
              │    ├─ register_new_server_backend(mac, ip)      (existing)
              │    ├─ log_ready_timing(name, "compute", "readiness_gate", ...)
              │    └─ NodeInfo append under _addition_complete_lock (existing)
              └─ clear pending entry
```

The `ReadinessGate` reference is **injected into the `ElasticityManager`** as
`elasticity.readiness_gate` (default `None`) by the mediator after construction
(T7). `_handle_compute` branches on `self.readiness_gate is not None` — no
reference to the controller object from the elasticity manager.

### 2.2 Readiness gate (registry + worker + probe)

```python
@dataclass
class PendingBackend:
    mac: str
    ip: str
    name: str
    lan: int
    network_id: str                 # controller LAN id: "lan1" / "lan2"
    ready_port: int = 5000          # EDGE_READY_PORT (must equal edge BIND_PORT)
    spawn_started_wall_s: float = 0.0     # time.time() at spawn start
    spawn_complete_wall_s: float = 0.0    # time.time() when add_edge_server returned
    spawn_started_mono_s: float = 0.0     # time.monotonic() at spawn start (for timing line)
    probe_first_wall_s: float | None = None
    app_ready_wall_s: float | None = None
    admitted_wall_s: float | None = None

class ReadinessGate:
    def __init__(self, propagation: str, probe_timeout_s: float,
                 probe_max_s: float, probe_retry_s: float,
                 discovery_interval_s: float, ready_port: int,
                 admission_log_path: str,
                 on_admit: Callable[[PendingBackend], None],
                 on_abandon: Callable[[PendingBackend], None]) -> None: ...
    def start(self) -> None: ...        # spawn worker daemon thread
    def enqueue(self, pb: PendingBackend) -> None: ...   # Thread 3 → gate; sets wake event
    def _worker(self) -> None: ...      # loop: wait(wake|cadence) → scan → probe → admit/abandon
    def _admit(self, pb: PendingBackend) -> None: ...    # log row + on_admit(pb)
    def _abandon(self, pb: PendingBackend) -> None: ...  # log row + on_abandon(pb)
```

- **Threading:** the worker is a `threading.Thread(daemon=True)` (native thread,
  like Thread 3) because it performs blocking HTTP probes — it must **not** be
  an eventlet greenthread (RQ1's no-blocking rule applies to greenthreads only).
- **Registry + wake mechanism:** a list of `PendingBackend` guarded by a
  `threading.Lock`, plus a `threading.Condition`. `enqueue` appends and calls
  `condition.notify()` **only in `direct` mode**. In **direct** mode the worker
  wakes immediately on enqueue (first probe is not delayed by the cadence —
  this is the "direct notification"); in **discovery** mode the worker waits on
  the cadence (`condition.wait(discovery_interval_s)`) and **ignores notify
  wakes** (it re-checks `time.monotonic() - last_scan >= discovery_interval_s`
  before probing), so the first probe is at most one cadence after
  spawn-complete. Each pass scans a snapshot and probes each pending backend
  that is not yet ready and not yet past `probe_max_s`.
- **Probe:** `requests.get(f"http://{pb.ip}:{pb.ready_port}/ready",
  timeout=probe_timeout_s)` (requests is already a dependency via RQ1 delivery
  sources). `200` → app-ready; non-200 / connection-refused / exception → not
  ready yet.
- **Abandonment:** if `now - spawn_complete_wall_s > probe_max_s` and never
  ready → `_abandon(pb)` (error log row + `on_abandon`).
- **Startup:** constructed in `main_n*.py` only when
  `READINESS_PROPAGATION != "off"` (no new object/thread in non-RQ3 runs → D1
  byte-identical). `on_admit`/`on_abandon` are mediator closures (T3, T7).

### 2.3 Flow isolation (control event → per-client flow delete)

```text
edge server after_request hook            [edge_server, only when EDGE_FLOW_ISOLATION=1]
  └─ spawn short-lived daemon thread that, after the response is flushed,
       MetricSender.send({"event_type": "request_complete",
                          "server_id": <mac>, "client_ip": request.remote_addr, "ts": ...})
        → edge PUSH → aggregator PULL → _extract_control_events → mini-summary (window_seq=None)
        → controller _control_events (Thread 2) [control_events.py]
            └─ process_flow_events(summary, vip_routing, flow_isolation_enabled)
                 if event_type == "request_complete" and enabled:
                     delete_vip_server_client_flows(client_ip)     [precise delete, T6]
```

- **Client→backend mapping (required for a precise delete):** `_vip_routing/
  state.py` adds `controller._vip_server_client_map: dict[str, ClientVipBinding]`
  keyed by `client_mac`, where `ClientVipBinding = (client_mac, client_ip,
  backend_mac, backend_ip, vip_ip, vip_mac)`. `install_vip_dnat_snat` records
  the binding when the installed VIP is a `VIP_SERVER` VIP (the caller passes
  the vip identity, T6). The binding is updated on every re-selection (the map
  is per-client and the newest selection wins) and cleared on backend removal.
- `delete_vip_server_client_flows(client_ip)` (new facade method on
  `VipRoutingMixin`): resolves `client_mac = _ip_to_mac.get(client_ip)` and the
  recorded binding; if either is missing, log debug + return. Deletes **exactly**
  the recorded DNAT forward rule (`eth_src=client_mac, eth_dst=vip_mac,
  ipv4_src=client_ip, ipv4_dst=vip_ip, ip_proto=6`) and the recorded SNAT reply
  rule (`eth_src=<backend_mac|router_mac>, eth_dst=client_mac,
  ipv4_src=<backend_ip>, ipv4_dst=client_ip, ip_proto=6`) at priority 200 on the
  controller's datapaths, then clears the binding. **This is intentionally
  exact** — it must NOT match the never-expiring `VIP_DATA` reply rule for the
  same client (`tcp_src=27018`), nor another backend's `VIP_SERVER` SNAT rule.
  After deletion the priority-100 punt rule resumes → the next SYN triggers
  fresh `select_server()`.
- **Aggregator:** add `request_complete` to `_CONTROL_EVENT_TYPES`
  (`aggregator.py`) so it is forwarded (whitelist-only; non-RQ3 runs never emit
  it, so no behavior change).
- **Controller:** `process_flow_events(summary, vip_routing, enabled)` is called
  from `_on_telemetry_update` (Thread 2) alongside the existing
  `process_drain_events` / `process_secondary_events`; it is a no-op unless
  `VIP_FLOW_ISOLATION=1`. **Misconfiguration guard:** it counts
  `request_complete` events; if enabled and none have arrived after
  `FLOW_ISOLATION_WARMUP_S` (default `120` s, a `scaling_config` constant) of
  controller uptime, log a prominent warning ("VIP_FLOW_ISOLATION=1 but no
  request_complete events received — check EDGE_FLOW_ISOLATION on edge
  containers"). Thread-safety: the flow delete calls the OVS `delete_flow` from
  Thread 2, following the existing Thread-3 pattern (`unregister_storage_backend`
  deletes flows); the `_vip_server_client_map` is guarded by a lock because
  Thread 1 writes bindings (selection) and Thread 2 deletes them.

### 2.4 Admission-log schema

`ADMISSION_LOG_PATH` CSV (header row on first write), columns in order:

| Column | Value |
|---|---|
| `ts` | wall clock when the row is written (== `admitted_ts` for admitted; == abandon time for abandoned) |
| `network_id` | controller LAN id (`lan1` / `lan2`), matching the decision log |
| `lan` | `1` / `2` |
| `container` | edge-server container name (e.g. `edge_server_lan1_dyn2`) |
| `mac` | backend MAC |
| `ip` | backend IP |
| `mode` | `direct` / `discovery` |
| `result` | `admitted` / `abandoned` |
| `spawn_started_ts` | wall clock when `_handle_compute` began spawning |
| `spawn_complete_ts` | wall clock when `add_edge_server` returned success |
| `probe_first_ts` | wall clock of the first `/ready` probe attempt |
| `app_ready_ts` | wall clock when `/ready` first returned `200` (first probe **observation** of readiness; empty for abandoned) |
| `admitted_ts` | wall clock when `register_new_server_backend` was called (empty for abandoned) |

Rules:
- One row per dynamically spawned **compute** backend in RQ3-arm runs —
  **including abandoned backends** (`result="abandoned"`, empty
  `app_ready_ts`/`admitted_ts`) so IP/container leaks are visible in the run.
- `probe_first_ts` is always filled for RQ3-arm runs.
- `episode_label` is **not** a controller column; the analyzer attaches it from
  `phases_snapshot.json` (post-hoc, same as RQ2 D5).

---

## 3. File map

**New**

| File | Purpose |
|---|---|
| `docs/research_questions/v2/rq3/rq3_preparation.md` | This plan |
| `source/sdn_controller/readiness_gate.py` | `PendingBackend` + `ReadinessGate` (registry, worker thread, probe, admission log writer, on_admit/on_abandon) |
| `source/scripts/testing/controller_env_overrides/rq3_direct.env` | Full RQ3 regime, `READINESS_PROPAGATION=direct` |
| `source/scripts/testing/controller_env_overrides/rq3_discovery.env` | Full RQ3 regime, `READINESS_PROPAGATION=discovery` |
| `source/scripts/testing/phases_override/phases_rq3_compute_episode.json` | Single compute-scale-up episode: baseline → compute-bound → recovery (one file, used by both arms; mirrors the RQ1/RQ2 `phases_override/phases_rq*_*.json` precedent) |
| `docs/research_questions/v2/rq3/rq3_admission_analysis.py` | Per-run timing segments + cross-arm comparison (primary RQ3 analysis) |
| `docs/research_questions/v2/rq3/rq3_flow_validation.py` | Flow-isolation + admission-leak validity checks |

**Modified**

| File | Change |
|---|---|
| `source/sdn_controller/scaling_config.py` | `_READINESS_PROPAGATION`, `_READINESS_PROBE_TIMEOUT_S`, `_READINESS_PROBE_MAX_S`, `_READINESS_PROBE_RETRY_S`, `_DISCOVERY_POLL_INTERVAL_S`, `_EDGE_READY_PORT`, `_ADMISSION_LOG_PATH`, `_VIP_FLOW_ISOLATION`, `_FLOW_ISOLATION_WARMUP_S` |
| `source/sdn_controller/elasticity/elasticity.py` | `readiness_gate` attribute (injected, default `None`); `_handle_compute` dispatch (off vs RQ3); extract `_admit_compute_backend` helper; `_abandon_compute_backend` (full teardown via initiate_drain + submit_cleanup, IP release) |
| `source/sdn_controller/elasticity/compute_node_manager.py` | `remove_failed_container` (abandon fallback); `EDGE_FLOW_ISOLATION` env pass-through in `_docker_run_server` |
| `source/sdn_controller/main_n1.py`, `main_n2.py` | Construct/start `ReadinessGate` when active; inject into `elasticity`; wire `on_admit`/`on_abandon`; call `process_flow_events`; startup provenance log |
| `source/sdn_controller/_vip_routing/state.py` | `_vip_server_client_map` (client→backend binding) + `ClientVipBinding`; record on VIP_SERVER selection; clear on backend removal |
| `source/sdn_controller/_vip_routing/flows.py` | Add `delete_vip_server_client_flows(...)` (exact-match DNAT+SNAT delete using the recorded binding) |
| `source/sdn_controller/vip_routing.py` | Facade method `delete_vip_server_client_flows(client_ip)` (own per-LAN `VIP_SERVER` only) |
| `source/sdn_controller/control_events.py` | `process_flow_events(summary, vip_routing, enabled, uptime_s)` for `request_complete` + warn-once misconfiguration guard |
| `source/docker/edge_server/source/control_plane_routes.py` | Add `/ready` route (`200` iff `process_state.app_ready`) |
| `source/docker/edge_server/source/edge_server_config.py` | `app_ready` startup flag + readiness predicate config |
| `source/docker/edge_server/source/edge_server_process_state.py` | `app_ready` state; add `/ready` to `SKIP_COUNTING_PATHS` |
| `source/docker/edge_server/source/app.py` | `after_request` captures client ip in-context + spawns a background thread emitting `request_complete` when `EDGE_FLOW_ISOLATION=1` and the path is not in `SKIP_COUNTING_PATHS` (after response flush) |
| `source/docker/local_state_server/aggregator.py` | Add `request_complete` to `_CONTROL_EVENT_TYPES` |
| `source/scripts/testing/run_experiment.sh` | `collect_rq3_artifacts` (admission logs, resolved via `docker exec printenv`); `EDGE_FLOW_ISOLATION` pass-through for edge containers |
| `source/scripts/testing/traffic_generator.py` | record the curl local source port per request (`-w '%{local_port}'`) as a `source_port` column (for `rq3_flow_validation.py` Check D) |
| `docs/operation/vip_routing/vip_routing_overview.md` | Readiness-gated admission + flow-isolation mode |
| `docs/operation/vip_routing/vip_routing_backend_selection_and_warm_leases.md` | RQ3 operating point (`topology_host`, no lease) + readiness gate |
| `docs/operation/elasticy_manager/elasticity_overview.md` | Readiness gate in the compute spawn path; link this plan |
| `docs/operation/testing/testing_overview.md` | Add `admission_log_lan1/lan2.csv` to the artifact contract |
| `docs/operation/telemetry/controller_side/controller_telemetry_consumer.md` | `request_complete` control-event handling |
| `docs/operation/telemetry/aggregation_publication/aggregator.md` | `request_complete` whitelisted control type |

**Unchanged (superseded old RQ3 framing — do not touch):**
`docs/research_questions/rq3/rq3_v2.md`, `rq3_v6.md`, `rq3_setup_*.md`,
`rq3_theory_prediction_v6.md`, `source/scripts/testing/controller_env_overrides/rq3_v2_*.env`,
`rq3_v7_*.env`, `rq3_cal_*.env`, `phases_override/phases_rq3_v7.json`. These are
the old trigger-composition framing, superseded by `tese/Notes/thesis_overview.md`;
the new RQ3 files above use fresh names to avoid collision. `tese/Notes/thesis_overview.md`
is untouched (scope unchanged).

---

## 4. Task breakdown (ordered)

### T1 — `scaling_config.py`

```python
# ── RQ3 readiness-propagation gate ─────────────────────────────────
# READINESS_PROPAGATION selects compute-backend admission timing:
#   "off"       → current pre-RQ3 behavior: register into the VIP_SERVER pool
#                 immediately after spawn (no probe, no admission log, no
#                 readiness worker thread) — DEFAULT. Canonical / RQ1 / RQ2
#                 runs byte-identical.
#   "direct"    → RQ3 arm: probe /ready immediately + every
#                 READINESS_PROBE_RETRY_S; admit on 200 (direct lifecycle
#                 notification).
#   "discovery" → RQ3 arm: probe /ready only on DISCOVERY_POLL_INTERVAL_S
#                 cadence; admit when a discovery pass sees 200 (periodic
#                 discovery).
# Unknown value → log error + fall back to "off" (deliberate, documented).
_READINESS_PROPAGATION = os.environ.get("READINESS_PROPAGATION", "off")

# Per-attempt /ready HTTP timeout (seconds).
_READINESS_PROBE_TIMEOUT_S = float(os.environ.get("READINESS_PROBE_TIMEOUT_S", "5.0"))
# Abandon a pending backend that is not ready within this many seconds of
# spawn completion. Must exceed DISCOVERY_POLL_INTERVAL_S and app startup time.
_READINESS_PROBE_MAX_S = float(os.environ.get("READINESS_PROBE_MAX_S", "120.0"))
# direct-mode probe retry interval (seconds). Must be << DISCOVERY_POLL_INTERVAL_S.
_READINESS_PROBE_RETRY_S = float(os.environ.get("READINESS_PROBE_RETRY_S", "1.0"))
# discovery-mode scan cadence (seconds). Pre-registered per run.
_DISCOVERY_POLL_INTERVAL_S = float(os.environ.get("DISCOVERY_POLL_INTERVAL_S", "10.0"))
# Edge-server /ready port. Must equal the edge server's BIND_PORT (5000) in RQ3 runs.
_EDGE_READY_PORT = int(os.environ.get("EDGE_READY_PORT", "5000"))
# RQ3 admission log (per controller / per LAN). Written only when the gate is active.
_ADMISSION_LOG_PATH = os.environ.get("ADMISSION_LOG_PATH", "/tmp/admission_log.csv")
# Flow-isolation mode: 1 = delete a client's VIP_SERVER flows after each
# response (one fresh backend-selection event per request). RQ3 measurement
# instrumentation; 0 elsewhere.
_VIP_FLOW_ISOLATION = int(os.environ.get("VIP_FLOW_ISOLATION", "0"))
# Misconfiguration guard: warn if flow isolation is enabled but no
# request_complete events have arrived within this many seconds of startup.
_FLOW_ISOLATION_WARMUP_S = float(os.environ.get("FLOW_ISOLATION_WARMUP_S", "120.0"))
```

### T2 — `readiness_gate.py` (new)

Implement `PendingBackend` + `ReadinessGate` per §2.2. Pure controller-side
logic, native worker daemon thread, `threading.Condition` wake mechanism,
blocking HTTP probe via `requests`. `_write_admission_row` is a locked CSV
appender (header on first write, exact column order of §2.4, including
`result="admitted"|"abandoned"`). `on_admit(pb)` / `on_abandon(pb)` are invoked
once per backend. The worker never raises out of its loop (each pass wrapped in
try/except, log + continue) — a probe failure on one backend must not stall the
others.

### T3 — `elasticity.py` (`_handle_compute` dispatch + helpers)

Add `self.readiness_gate = None` in `ElasticityManager.__init__` (injected by
the mediator in T7). Extract the current admission block into a reusable helper
so `off` stays byte-identical and RQ3 reuses it:

```python
def _admit_compute_backend(self, effective_mac, effective_ip, name, lan,
                           network_id, spawn_started_monotonic_s, source: str) -> None:
    self._topo.register_new_server_backend(effective_mac, effective_ip)
    log_ready_timing(name, "compute", source, time.monotonic() - spawn_started_monotonic_s)
    logger.info("[elasticity] compute: %s online  ip=%s  mac=%s",
                name, effective_ip, effective_mac)
    info = NodeInfo(
        mac=effective_mac, lan=lan, network_id=network_id,
        name=name, ip=effective_ip, node_type="compute",
        spawn_started_monotonic_s=spawn_started_monotonic_s, ready_logged=True,
    )
    with self._addition_complete_lock:
        self._addition_complete_infos.append(info)

def _abandon_compute_backend(self, effective_mac, effective_ip, name, lan) -> None:
    # A spawned-but-never-ready backend must not leak. Reuse the EXISTING full
    # compute teardown (Phase A drain discovery + Phase B cleanup) so the OVS
    # veth/port and host_attachment/MAC entries are torn down too — not just
    # the container. Best-effort and exception-safe.
    drain = self._compute_adder.initiate_drain(lan, name, effective_mac)
    if drain is not None:
        self.submit_cleanup(effective_mac)      # Phase B: OVS teardown + docker rm
    else:
        self._compute_adder.remove_failed_container(name)   # no veth → bare docker rm
    self._get_allocator(lan).release(effective_ip)
    logger.error("[elasticity] compute: %s abandoned (never ready) — ip=%s released, teardown submitted",
                 name, effective_ip)
```

- `_admit_compute_backend` now takes `lan` and `network_id` as plain values
  (the RQ3 gate thread does not have the original `ComputeAlert`). The `off`
  path passes `alert.lan` and `alert.network_id` — identical to today.
- **`remove_failed_container`:** add a small method to `ComputeNodeAdder`
  (mirrors the existing `_cleanup_container` used on spawn failure): `docker rm
  -f <name>` best-effort. It is the fallback only when veth discovery fails
  (`initiate_drain` returns `None`); the primary abandonment path reuses the
  existing `initiate_drain` + `submit_cleanup` teardown so the OVS veth/port and
  host-attachment entries do not leak. Only reached on the RQ3 abandonment path
  (never in `off` mode).
- `_handle_compute`, in the `if effective_mac:` branch (inside the existing
  `if result.success and result.ip:` block), becomes:

```python
if effective_mac:
    if self.readiness_gate is None:
        # ── current behavior — UNCHANGED (byte-identical) ─────────
        self._admit_compute_backend(effective_mac, effective_ip, name,
                                    alert.lan, alert.network_id,
                                    spawn_started_monotonic_s, "vip_backend_registered")
    else:
        # ── RQ3 arms: hand off to the readiness gate (no registration yet) ──
        self.readiness_gate.enqueue(PendingBackend(
            mac=effective_mac, ip=effective_ip, name=name,
            lan=alert.lan, network_id=alert.network_id,
            ready_port=_EDGE_READY_PORT,
            spawn_started_wall_s=spawn_start_wall_s,
            spawn_complete_wall_s=time.time(),
            spawn_started_mono_s=spawn_started_monotonic_s,
        ))
else:
    # ── PRESERVED in all modes — "MAC not available in script output" ──
    logger.warning(
        "[elasticity] compute: %s online at %s but MAC not available in script output",
        name, result.ip,
    )
```

- `spawn_start_wall_s = time.time()` is captured at the top of `_handle_compute`
  next to `spawn_started_monotonic_s`.
- The `else:` MAC-missing warning branch is **preserved in all modes**.
- **Concurrency note:** `on_admit` runs in the gate thread and appends to
  `_addition_complete_infos` under `_addition_complete_lock` (as today) and
  calls `register_new_server_backend` (already a cross-thread-safe pattern:
  warm leases use `_warm_lock`, topology sets are the existing Thread-3 write
  pattern).

### T4 — edge server `/ready` + `request_complete`

- `edge_server_config.py` / `control_plane_routes.py`: add `/ready` (GET) that
  returns `200 {"status":"ready"}` iff `process_state.app_ready` is `True`
  (D2) and `503 {"status":"starting"}` otherwise. Add `app_ready` to
  `EdgeServerProcessState`, initially `False`, set `True` after (a) Flask routes
  are registered, (b) the first successful MongoDB operation through the
  `VIP_DATA` epoch runtime completes, and (c) the telemetry sender is
  initialized — the single concrete, testable readiness predicate. Exclude
  `/ready` from request-counting paths in `edge_server_process_state.py`
  (`SKIP_COUNTING_PATHS`), alongside `/health`.
- `app.py`: in `_add_backend_identity` (the existing `after_request` hook), when
  `os.environ.get("EDGE_FLOW_ISOLATION", "0") == "1"` **and**
  `request.path not in SKIP_COUNTING_PATHS` (so the controller's own `/ready`
  probes and `/health`/`/drain` calls do not emit `request_complete`), capture
  `client_ip = request.remote_addr` and `server_mac = <mac>` **inside the
  request context**, then spawn a short-lived daemon thread that emits **after
  the response is flushed**:
  `threading.Thread(target=_emit_request_complete, args=(process_state,
  client_ip, server_mac), daemon=True).start()`, where `_emit_request_complete`
  only calls `process_state.metric_sender.send({"event_type":
  "request_complete", "server_id": server_mac, "client_ip": client_ip,
  "ts": time.time()})` — it never touches the (torn-down) request context.
  Emitting from a background thread (rather than inline in `after_request`)
  ensures the delete lands after the response bytes are on the wire (D5 race
  avoidance). `EDGE_FLOW_ISOLATION` defaults off → non-RQ3 runs emit nothing
  (byte-identical).

### T5 — `aggregator.py`

Add `"request_complete"` to `_CONTROL_EVENT_TYPES`. No other change — the
existing `_extract_control_events` / `_publish_control_events` path forwards it
in the control mini-summary (`window_seq=None`), reaching the controller's
`_control_zmq` / `_control_events` dispatcher exactly like `drain_complete`.

### T6 — controller flow isolation (`_vip_routing` + `control_events.py`)

1. `state.py`: add `ClientVipBinding` (frozen dataclass: `client_mac,
   client_ip, backend_mac, backend_ip, vip_ip, vip_mac, snat_eth_src`) and
   `controller._vip_server_client_map: dict[str, ClientVipBinding]` keyed by
   `client_mac`. Record the binding **inside `install_vip_dnat_snat`** (the
   VIP_SERVER-only installer — no `ingress.py` change is needed): capture the
   exact `snat_eth_src` used at install time (`backend_mac` or `_ROUTER_MAC`)
   so the delete can reuse it. On **re-selection** for a client that already
   has a binding, first delete the old exact DNAT+SNAT pair (using the old
   binding — otherwise the previous backend's SNAT rule lingers with a different
   match), then record the new binding. Clear the binding in
   `unregister_server_backend`. Guard the map with the existing `_warm_lock`
   (Thread 1 writes, Thread 2 deletes). Storage `VIP_DATA` flows use the
   separate cookie/conntrack family and are never recorded here.
2. `flows.py`: add `delete_vip_server_client_flows(controller, datapath,
   binding: ClientVipBinding)` — deletes **exactly** the recorded DNAT forward
   rule (`eth_type=0x0800, eth_src=binding.client_mac, eth_dst=binding.vip_mac,
   ipv4_src=binding.client_ip, ipv4_dst=binding.vip_ip, ip_proto=6`) and the
   recorded SNAT reply rule (`eth_type=0x0800,
   eth_src=<binding.backend_mac|_ROUTER_MAC>, eth_dst=binding.client_mac,
   ipv4_src=binding.backend_ip, ipv4_dst=binding.client_ip, ip_proto=6`) at
   priority 200. **Exact match only** — it must not match the never-expiring
   `VIP_DATA` reply rule (`tcp_src=27018`) or another backend's SNAT rule.
   After deletion the priority-100 punt rule resumes → fresh selection on next
   SYN.
3. `vip_routing.py` facade: add `delete_vip_server_client_flows(self,
   client_ip)` — resolve `client_mac = self._ip_to_mac.get(client_ip)`; look up
   the binding; if either missing, log debug + return; else for each datapath
   call the `flows.py` helper, then clear the binding. Handles this controller's
   **own per-LAN** `VIP_SERVER` only (D8 — cross-network server flows are out of
   scope; document in the docstring).
4. `control_events.py`: add `process_flow_events(self, summary, vip_routing,
   enabled, uptime_s)` — for each `event_type == "request_complete"` with a
   `client_ip`, when `enabled`, call
   `vip_routing.delete_vip_server_client_flows(client_ip)`. Track a
   `_request_complete_count`. Misconfiguration guard: if `enabled` and
   `uptime_s > FLOW_ISOLATION_WARMUP_S` and `_request_complete_count == 0`,
   log the warning **exactly once** (a `_guard_warned` flag) — not on every
   telemetry update. `uptime_s = time.monotonic()` since controller start.
   Thread 2 context; the flow delete follows the existing Thread-3 OVS
   `delete_flow` pattern.
5. `main_n1.py` / `main_n2.py`: call
   `self._control_events.process_flow_events(summary, self,
   _VIP_FLOW_ISOLATION == 1, time.monotonic())` in `_on_telemetry_update`,
   **alongside the existing `process_drain_events` / `process_secondary_events`
   control-event calls and BEFORE the `if not summary.servers and not
   summary.storage_servers: return` early return** — `request_complete` events
   arrive on control mini-summaries whose server dicts are empty. `self` here
   is the controller instance, which mixes in `VipRoutingMixin` and therefore
   provides `delete_vip_server_client_flows` directly (there is **no**
   `self._topo` on the controller class — that attribute lives only on
   `ElasticityManager`).

### T7 — `main_n1.py` / `main_n2.py` (gate wiring + injection)

- Import `ReadinessGate`, `PendingBackend`, and the RQ3 `scaling_config`
  constants.
- In `__init__`, after the elasticity manager is constructed:

  ```python
  if _READINESS_PROPAGATION != "off":
      self._readiness_gate = ReadinessGate(
          propagation=_READINESS_PROPAGATION,
          probe_timeout_s=_READINESS_PROBE_TIMEOUT_S,
          probe_max_s=_READINESS_PROBE_MAX_S,
          probe_retry_s=_READINESS_PROBE_RETRY_S,
          discovery_interval_s=_DISCOVERY_POLL_INTERVAL_S,
          ready_port=_EDGE_READY_PORT,
          admission_log_path=_ADMISSION_LOG_PATH,
          on_admit=lambda pb: self._elasticity._admit_compute_backend(
              pb.mac, pb.ip, pb.name, pb.lan, pb.network_id,
              pb.spawn_started_mono_s, "readiness_gate",
          ),
          on_abandon=lambda pb: self._elasticity._abandon_compute_backend(
              pb.mac, pb.ip, pb.name, pb.lan,
          ),
      )
      self._elasticity.readiness_gate = self._readiness_gate
      self._readiness_gate.start()
  else:
      self._readiness_gate = None      # elasticity.readiness_gate stays None
  ```

- **Timing correctness:** `on_admit` uses `pb.spawn_started_mono_s` (a
  `time.monotonic()` value captured at spawn start) for the `[node_ready]`
  timing line — no wall→mono conversion.
- **Injection ordering:** construct the gate and assign
  `self._elasticity.readiness_gate` **before** `self._elasticity.start()` runs
  (or immediately after elasticity construction), so a stray early alert can
  never take the `off` path.
- Startup provenance: log `READINESS_PROPAGATION`, probe knobs,
  `VIP_FLOW_ISOLATION`, `EDGE_READY_PORT` at controller start (mirrors RQ2's
  startup log of `SCALEUP_POLICY`, budget, margin).

### T8 — env regimes (2 files) + phase file

Each arm file sets the **full** RQ3 regime (distinct, named configuration
regime — allowed by the repo rules, matching RQ2's precedent). The two files
differ **only** in the `READINESS_PROPAGATION` line. Selected per run via
`OSKEN_ENV_OVERRIDE_FILE`; the run folder snapshots it to
`controller_env_snapshot.env` (the analyzer's arm label source). **Base-env
layering:** these files are an *override* on `osken-controller.env`; a knob not
listed here keeps the BASE value. State in each file's header comment that
unlisted knobs resolve from the base env.

```text
# RQ3 readiness-propagation arm regime — <ARM NAME>
# Unlisted knobs resolve from the base osken-controller.env (override semantics).
# The two arm files are identical except the READINESS_PROPAGATION line; the
# knobs below fix the absolute operating point shared by both arms.
STORAGE_PERSISTENT_RESERVE_ENABLED=0
SS_ENABLED=0
CROSS_REGION_STORAGE_ENABLED=0
TELEMETRY_SOURCE=event_preserving
SCALEUP_POLICY=dual
READINESS_PROPAGATION=<arm>            # direct | discovery  (the ONLY difference)
READINESS_PROBE_TIMEOUT_S=5.0
READINESS_PROBE_MAX_S=120.0
READINESS_PROBE_RETRY_S=1.0
DISCOVERY_POLL_INTERVAL_S=10.0
EDGE_READY_PORT=5000
ADMISSION_LOG_PATH=/tmp/admission_log.csv
VIP_FLOW_ISOLATION=1
FLOW_ISOLATION_WARMUP_S=120.0
BACKEND_SELECTION_POLICY=topology_host
VIP_WARM_SERVER_SECONDS=0
VIP_WARM_STORAGE_SECONDS=30
# ── WSM routing weights (identical across arms; pinned absolute) ──
W_CPU=0.2
W_RAM=0.2
W_REQUESTS=0.2
W_HOPS=0.28
W_STORAGE_CPU=0.2
W_STORAGE_RAM=0.2
W_STORAGE_CONNECTIONS=0.1
W_STORAGE_LAG=0.2
W_STORAGE_HOPS=0.3
# ── VIP flow timeouts (unchanged; flow isolation handles affinity) ──
VIP_IDLE_TIMEOUT=30
VIP_HARD_TIMEOUT=120
# ── RQ1/RQ2 delivery + decision-log knobs (pinned; unlisted resolve from base) ──
CONTROL_TICK_S=10
DELAY_S=30
EVENT_POLL_INTERVAL_S=0.5
DELIVERY_LOG_PATH=/tmp/telemetry_delivery_log.csv
DECISION_LOG_PATH=/tmp/decision_log.csv
```

**Structural requirement:** both arm files are identical except the
`READINESS_PROPAGATION` line. The RQ3 runs additionally require:
- edge-server container env **`EDGE_FLOW_ISOLATION=1`** (set by the run
  harness / edge-server `docker run` env pass-through — T9), and
- edge-server **`BIND_PORT=5000`** (the compiled default; `EDGE_READY_PORT=5000`
  must match).

Phase file `phases_override/phases_rq3_compute_episode.json` — a
**single-episode** compute-bound run (D7): `baseline` → `compute_spike`
(episode mix dominated by `service_pressure` / `feed_ranking`, low DB traffic,
no cross-region hotspot, sustained rate high enough to fire compute scale-up
repeatedly) → `cleanup_gap` (recovery tail). Used by **both** arms (workload is
identical; the arm is chosen by the controller env). This follows the RQ1/RQ2
precedent of RQ-specific phase files under `phases_override/` (`phases_rq1_7phase.json`,
`phases_rq2_compute_bound.json`, etc.) — a distinct named regime, not a
modification of the canonical `phases.json`. Exact durations/rates/mix weights
are **experiment-design calibration** (Experiment Designer) — this plan fixes
the *structure* and endpoint families.

### T9 — `run_experiment.sh` (artifact collection + edge flag)

- Add `collect_rq3_artifacts()` modeled on `collect_rq1_artifacts()`: resolve
  each path via `docker exec` (the RQ1 pattern — never a bare host-side
  variable):

  ```bash
  _adm1="$(docker exec osken printenv ADMISSION_LOG_PATH 2>/dev/null || echo /tmp/admission_log.csv)"
  _adm2="$(docker exec osken_2 printenv ADMISSION_LOG_PATH 2>/dev/null || echo /tmp/admission_log.csv)"
  docker cp "osken:${_adm1}" "${RUN_DIR}/admission_log_lan1.csv"   2>/dev/null \
      || echo "  WARNING: admission_log_lan1 unavailable (non-RQ3 run?)" >&2
  docker cp "osken_2:${_adm2}" "${RUN_DIR}/admission_log_lan2.csv" 2>/dev/null \
      || echo "  WARNING: admission_log_lan2 unavailable (non-RQ3 run?)" >&2
  ```

  Call it in the post-run sequence alongside `collect_rq1_artifacts`; add the
  two paths to the run-completion echo.
- Wire `EDGE_FLOW_ISOLATION` pass-through for edge-server containers
  (add_network_node.sh / edge-server `docker run`): `-e
  EDGE_FLOW_ISOLATION="${EDGE_FLOW_ISOLATION:-0}"`. Document in
  `testing_overview.md` that RQ3 runs must launch with `EDGE_FLOW_ISOLATION=1`
  and `BIND_PORT=5000`, and that the controller-side misconfiguration guard
  (T6) catches a forgotten edge flag.

### T10 — analyzer tools (`docs/research_questions/v2/rq3/`, scope-prefixed)

Both tools **first confirm the run is an RQ3 run** by reading
`controller_env_snapshot.env`: only runs whose `READINESS_PROPAGATION` is
`direct` or `discovery` are processed; `off`/absent runs are skipped.

**Driver change (prerequisite for Check D):** `traffic_generator.py` adds the
curl local source port to each request row (`curl -w '%{local_port}'`),
emitted as a `source_port` column in `client_requests.csv`. This makes the
one-fresh-connection-per-request model verifiable (Check D).

- `rq3_admission_analysis.py` — from `admission_log_lan1/lan2.csv`, attach
  `episode_label` from `phases_snapshot.json` (post-hoc, D6 rule). For each
  compute backend compute:
  - `spawn_complete → app_ready_observed` (app startup + first-observation
    quantization; sanity-check the readiness criterion is identical across
    arms),
  - **`spawn_complete → admitted`** (the **primary** metric — D3; it embeds the
    propagation-delay quantization),
  - `admitted → first_flow` and `first_flow → first_success` — join
    `client_requests.csv` on `X-Backend-ID == container` (already stamped by
    `_add_backend_identity`) for rows with `ts >= admitted_ts`; `first_flow` =
    first row attributed to this backend with a **non-`unknown` backend id**
    (a request that reached the backend but whose curl parse failed logs
    `backend_id="unknown"` and is **not** attributed to the backend — see
    caveats), `first_success` = first such row with a `2xx` status,
  - `scale decision → usable capacity` — join the triggering `scale_up` row
    from `decision_log_*.csv` (action `ComputeAlert`, nearest `ts` before
    `spawn_started_ts`) → `first_success`,
  - **useful initial request share** — in a pre-registered transition window
    `[admitted_ts, admitted_ts + TRANSITION_WINDOW_S]` (default 30 s, an
    analyzer flag), the fraction of requests served by this backend that
    succeed,
  - transition-window p50/p95/p99 latency + failure rate for requests served
    by the new backend.
  Emit per-run tables + the **arm × replicate** counterbalance matrix and a
  cross-arm summary (mean/median + per-run variance of each segment).
- `rq3_flow_validation.py` — flow-isolation + leak validity (D5, D2):
  - **Check A (no pre-admission traffic):** no request in `client_requests.csv`
    is attributed to a backend before its `admitted_ts`.
  - **Check B (no post-removal traffic):** after a backend is removed (from
    `container_events.csv`/decision-log removal rows), no request is attributed
    to it (no stale pinned flow survives removal).
  - **Check C (flow-delete coverage):** the count of `request_complete` events
    (from controller logs / a counter exposed in the decision log is optional)
    ≈ the count of measured requests; if the controller-side counter is not
    exported, this check is derived from Check A/B plus a controller-log grep
    of `request_complete` handling.
  - **Check D (client model):** within the RQ3 measurement window, each
    client uses one fresh connection per request (no keep-alive reuse) — verify
    from the new `source_port` column in `client_requests.csv` that no two
    requests from the same client share a source port within a short reuse
    window. Report violations; the criterion is **not** "different backend per
    request" (under `topology_host` the newest backend legitimately wins
    repeatedly — D4).

### T11 — documentation

Per §7 below (docs list in the file map). Keep prose minimal and factual.

### T12 — validation

1. `READINESS_PROPAGATION=off` → mediator behaves byte-identically to pre-RQ3
   (immediate `register_new_server_backend`, no probe, no admission log, no
   readiness worker thread started, no `/ready` dependency, no `request_complete`
   emission, no `_vip_server_client_map` writes).
2. `direct`: after spawn, `/ready` is probed immediately (Condition wake) and on
   `1.0` s retries; admission happens within ~1 s of readiness being observable;
   `probe_first_ts`/`app_ready_ts`/`admitted_ts` logged; admission-log row
   written with `result="admitted"`.
3. `discovery`: direct registration is suppressed; `/ready` probed only on the
   `10.0` s cadence; `spawn_complete → admitted` is quantized to
   `[0, DISCOVERY_POLL_INTERVAL_S]` on top of app startup; spot-check via DEBUG
   logs + admission log.
4. Identical readiness criterion: same `/ready` condition in both arms; the
   `spawn_complete → app_ready_observed` distribution overlaps across arms.
5. `topology_host` + `VIP_WARM_SERVER_SECONDS=0`: a newly admitted backend
   receives its first request promptly (no starvation); warm leases are never
   consumed (no `warm lease claimed` log); **at admission the backend is present
   in `host_attachment`** (real hops, not `hops_max` — verified in DEBUG logs).
6. Flow isolation: with `VIP_FLOW_ISOLATION=1` and `EDGE_FLOW_ISOLATION=1`, two
   consecutive requests from the same client produce fresh selections (verified
   via controller flow-delete logs + `rq3_flow_validation.py` Checks A–D); with
   either flag off, no `request_complete` handling and no flow deletion
   (byte-identical to baseline).
7. `request_complete` reaches the controller: aggregator whitelists it, control
   mini-summary (`window_seq=None`) arrives, `process_flow_events` deletes the
   exact client+backend flow pair (verified via controller log + next request's
   fresh selection); the `VIP_DATA` reply rule for the same client is **not**
   deleted (no breakage of established MongoDB return paths).
8. Abandonment: a backend that never becomes ready within `READINESS_PROBE_MAX_S`
   is abandoned — `result="abandoned"` row written, IP released, container
   removed (no leak); no admission; `_abandon_compute_backend` best-effort and
   exception-safe.
9. Admission-log format: header + columns exactly per §2.4; one row per compute
   backend (including abandoned); `""` only for never-occurred timestamps;
   `network_id` = `lan1`/`lan2`.
10. RQ1/RQ2 artifacts (window log, delivery log, decision log) are still
    produced unchanged in RQ3 runs; `SCALEUP_POLICY=dual` decision rows keep
    RQ1/RQ2 semantics. Misconfiguration guard fires a warning if
    `VIP_FLOW_ISOLATION=1` with no `request_complete` events.
11. **Probe reachability:** before the first RQ3 run, verify the controller
    host can reach the OVS-bridge backend subnets at `<backend_ip>:5000` — the
    `/ready` probe is the first direct controller→backend HTTP GET in the
    platform (the controller runs `--network host`, so confirm a host route
    exists to `10.0.0.0/24` / `10.0.1.0/24` via the bridge). If not routable,
    add a host route (documented harness step); otherwise every RQ3-arm backend
    would be abandoned at `READINESS_PROBE_MAX_S`.

---

## 5. Measurement contract

- **Universe of RQ3 observations:** `admission_log_*.csv` rows (one per
  dynamically spawned compute backend in RQ3-arm runs). **Arm ground truth:**
  `controller_env_snapshot.env` `READINESS_PROPAGATION` (direct | discovery).
  **Episode context:** `phases_snapshot.json` (post-hoc join, same as RQ2 D5).
  **Trigger join:** `decision_log_*.csv` `scale_up` row with action
  `ComputeAlert`, nearest `ts` before the admission's `spawn_started_ts`.
- **Primary outcome:** `spawn_complete → admitted` (D3 — embeds the
  propagation-delay quantization; true app-ready is unobservable between
  probes). Reported as raw per-run distributions, not a fabricated
  `app_ready → admitted`.
- **Secondary outcomes:**
  - `spawn_complete → app_ready_observed` (readiness-criterion identity check).
  - `admitted → first_flow`, `first_flow → first_success`.
  - Time from scale decision to usable capacity (`decision ts → first_success`).
  - Useful initial request share (transition window).
  - Transition-window p50/p95/p99 latency + failures (existing collectors).
- **Flow-isolation validity:** `rq3_flow_validation.py` Checks A–D (no
  pre-admission traffic, no post-removal traffic, flow-delete coverage, client
  one-connection-per-request model).
- **Counterbalance check:** `rq3_admission_analysis.py` reports the arm ×
  replicate matrix.
- **Caveats (documented):** discovery-arm `spawn_complete → admitted` is
  quantized to `[0, DISCOVERY_POLL_INTERVAL_S]`; direct-arm pays probe retry
  latency (`~READINESS_PROBE_RETRY_S`). True app-ready is only observable at
  probe times (D3). Flow isolation adds one packet-in + one `request_complete`
  control event per request, uniform across both arms, active for the whole RQ3
  run; the run's offered load is calibrated below the controller's packet-in
  throughput (RQ1-measured). `client_requests.csv` rows whose curl parse failed
  carry `backend_id="unknown"` and are not attributed to a backend (`first_flow`
  excludes them — a request that reached the backend but failed to parse is not
  counted as a first flow, so `first_flow` and `first_success` are computed from
  attributed rows). Clock alignment: `admitted_ts` (controller wall clock) and
  `client_requests.csv` timestamps (driver wall clock) are assumed same-host —
  the controller runs in Docker on the same host as the driver; document this
  assumption. `topology_host` cold-start herd makes the newest backend receive
  most fresh requests until it acquires telemetry — identical in both arms and
  intended (D4). Non-RQ3 runs (canonical/RQ1/RQ2) are byte-identical (D1, D5
  edge flag off).

---

## 6. Dependencies

- **RQ1 + RQ2 implemented first** (hard prerequisites, confirmed landed):
  event-preserving delivery, `window_id`, `_log_decision`/`DECISION_LOG_PATH`,
  `_housekeeping_loop`, RQ1/RQ2 artifact collection, `PolicyGate`,
  `_SCALEUP_POLICY`, mode-aware decision log.
- **Two image rebuilds:** `edge_server` (new `/ready` route + `request_complete`
  emission) and `local_state_server` (aggregator `request_complete` whitelist).
  No new container images.
- Existing packages only: `requests` (already a dependency), `pydantic`, `csv`,
  `json`, `threading`, stdlib. No new dependencies.

---

## 7. Documentation updates

- **New:** `docs/research_questions/v2/rq3/rq3_preparation.md` (this plan).
- `docs/operation/vip_routing/vip_routing_overview.md`
- `docs/operation/vip_routing/vip_routing_backend_selection_and_warm_leases.md`
- `docs/operation/elasticy_manager/elasticity_overview.md`
- `docs/operation/testing/testing_overview.md`
- `docs/operation/telemetry/controller_side/controller_telemetry_consumer.md`
- `docs/operation/telemetry/aggregation_publication/aggregator.md`
- `tese/Notes/thesis_overview.md` — untouched (scope unchanged).

---

## 8. Out of scope / follow-ups

- The RQ3 **experiment plan** (run matrix, episode durations/rates/mix
  calibration, transition-window length, replicate counts, blocking) — a
  separate step for the Experiment Designer, reusing the env regimes and phase
  file this plan provides.
- Storage-backend readiness propagation (`rs_secondary_ready` admission) —
  distinct readiness event, out of scope (D8), held constant.
- Cross-network `VIP_SERVER` flow isolation — out of scope (D8, same-LAN RQ3
  workload).
- The superseded old-RQ3 (trigger composition) artifacts are untouched; they are
  supporting calibration evidence only per `tese/Notes/thesis_overview.md`.
- Tier 1 / reserves / cross-region remain disabled for RQ3 runs per thesis §2.

---

## 9. Implementation notes (2026-07-31)

- **Binding map gated on flow isolation (D1):** the ``_vip_server_client_map``
  record + re-selection flow delete inside ``install_vip_dnat_snat`` run ONLY
  when ``VIP_FLOW_ISOLATION=1`` (RQ3 arms). With ``VIP_FLOW_ISOLATION=0``
  (default) no map writes and no re-selection deletes occur → canonical/RQ1/RQ2
  runs are byte-identical.
- **/ready predicate (D2, concrete):** the edge marks ``app_ready`` after a
  real MongoDB round-trip — ``_get_write_client(lan).admin.command("ping")``
  against the direct primary write client (not the VIP_DATA epoch runtime).
  This is the single testable readiness predicate; a deliberate simplification
  of the plan's "through the VIP_DATA epoch runtime" wording (the direct client
  is guaranteed to exist, the epoch client is created lazily). RQ3 runs rely on
  ``READINESS_APP_MAX_S`` (edge, default 180) > ``READINESS_PROBE_MAX_S``
  (controller, 120) so the edge never gives up before the controller would
  abandon.
- **Abandon teardown (T3):** abandonment is routed through the elasticity
  queue as ``AbandonComputeBackendAlert`` so the teardown runs in Thread 3
  (``_busy=True``) and never blocks the readiness-gate worker. Primary path =
  ``initiate_drain`` + ``submit_cleanup`` (full OVS + container + IP release);
  fallback (``initiate_drain`` returns ``None``, container netns gone) =
  ``remove_failed_container`` + IP release, mirroring the existing scale-down
  None path (accepted limitation).
- **Static edge servers:** the static ``edge_server_n1/n2`` also carry
  ``EDGE_FLOW_ISOLATION`` (added to ``build_network_1/2.sh``); RQ3 runs must
  launch the network setup with ``EDGE_FLOW_ISOLATION=1`` so the static servers
  emit ``request_complete`` too.
- **Edge sender locking:** ``ZmqMetricSender`` serializes sends with a lock
  (the ZMQ PUSH socket is shared across the telemetry, drain-monitor, and RQ3
  ``request_complete`` threads).
- **Check C log contract:** the controller logs
  ``vip_server: request_complete: client flows deleted`` (info) only for
  request_complete-driven deletes; ``rq3_flow_validation.py`` greps that exact
  string.
