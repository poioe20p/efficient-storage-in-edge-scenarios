# RQ1 — Telemetry Delivery Semantics: Implementation Plan (Design B)

> **Status:** ✅ IMPLEMENTED (2026-07-31) — the code has landed; this document
> is the historical plan/spec for the delivered behaviour.
> **Scope:** RQ1 "required extension" from `tese/Notes/thesis_overview.md`.
> **Date:** 2026-07-31.

> **Implementation note:** the delivered code additionally adds
> `source/sdn_controller/scaling_config.py` (`_CONTROL_TICK_S`,
> `_TELEMETRY_TIMEOUT_S`) to the file map, and lands the planned
> `build_network_1.sh`/`build_network_2.sh`, `run_experiment.sh`, `Dockerfile`
> (`EXPOSE 5558`), and `current_state_integrated.env` changes described in § 3
> and T10 below.

This plan implements the RQ1 required extension: a durable, sequence-numbered
telemetry-window log (retention, ordered replay, delivery acknowledgement,
shared event identifiers), three delivery modes (**event-preserving reference**,
**delayed event-preserving**, **latest-state**), and the controller internal-loop
split (**Design B**) so time-based housekeeping runs on a fixed clock rather than
on telemetry arrival.

This plan is **not phased**; no phase/order prefixes apply. New Python modules
keep import-safe names; the new doc gets the scope prefix.

---

## 1. Locked decisions

- **D1 — Window universe:** every `WINDOW_S` interval is a window with monotonic
  `window_seq` (1,2,3,…). Empty windows are real windows, always published.
  Control-event mini-summaries have `window_seq=None`.
- **D2 — Delayed arm:** every window delivered exactly once, strictly increasing
  seq order; released when `now ≥ window_end + DELAY_S`; FIFO; no batching, no
  backward fetch/backfill, no replay; backlog drains one-per-step at due times;
  measured delay excess is not masked.
- **D3 — Overload label:** pre-registered threshold definition (documented proxy,
  *not* a replication of the internal `degradation_score`), evaluated at the
  aggregator at production time, stamped `overload: bool`, identical across
  arms/runs. The decision log records whether the controller actually acted per
  overload window.

## 2. Architecture (Design B split)

**Stays on delivery arrival** in `_on_telemetry_update`: network gate,
node-registry sync, control events, `_log_and_update_stats`, `sync_storage_roles`,
selective-sync coordinator, fallback VIP promotion, storage-reserve
prepare/tick/activate, cross-region warm-standby, **scale-up evaluation**.

**Moves to a fixed ticker** `_housekeeping_loop` (period `CONTROL_TICK_S`,
default = `WINDOW_S`): **absent-node detection** and **scale-down evaluation**
(compute + storage), preserving cooldown and `is_busy()` gating. The old
scale-down + absent-node blocks are **removed** from `_on_telemetry_update`
(never duplicated).

**`_last_summary` guard:** updated only after the local-LAN gate, and only for
real windows:

```python
if summary.window_seq is not None and summary.network_id == self._lan_id:
    self._last_summary = summary
```

This is the single source of truth for the ticker — peer-LAN summaries and
control mini-summaries never reach it.

## 3. File map

**New**

| File | Purpose |
|---|---|
| `source/sdn_controller/telemetry/event_preserving_source.py` | Arm 1: in-order pull-from-log, seq validation + defensive gap recovery |
| `source/sdn_controller/telemetry/delayed_source.py` | Arm 2: in-order pull + FIFO hold queue, per-window release at `window_end + DELAY_S` |
| `source/sdn_controller/telemetry/delivery_log.py` | Shared CSV delivery-logger + best-effort ack client |

**Modified**

| File | Change |
|---|---|
| `source/sdn_controller/telemetry/models.py` | add `window_seq: int\|None=None`, `window_id: str\|None=None`, `overload: bool=False` |
| `source/sdn_controller/telemetry/polling_source.py` | seq-keyed dedup; pass every observed window; seq-aware delivery log |
| `source/sdn_controller/main_n1.py`, `main_n2.py` | mode selection, `_control_zmq` wiring, ticker, split, decision log |
| `source/sdn_controller/node_registry.py` | time-based absence detection |
| `source/sdn_controller/scaling_config.py` | add `_CONTROL_TICK_S`, `_TELEMETRY_TIMEOUT_S` (housekeeping clock + time-based absence timeout) |
| `source/docker/local_state_server/aggregator.py` | seq/window_id/overload/always-publish/window log/endpoints/ack |
| `source/docker/local_state_server/Dockerfile` | `EXPOSE 5558` |
| `source/scripts/network/build_network_1.sh`, `build_network_2.sh` | aggregator env vars (read from env with defaults) |
| `source/scripts/build_network_setup.sh` | no default change (`zmq` stays); nothing else |
| `source/scripts/testing/controller_env_overrides/current_state_integrated.env` | controller env defaults |
| `source/scripts/testing/run_experiment.sh` | artifact collection (`docker cp`) + aggregator env snapshot |

## 4. Task breakdown (ordered)

### T1 — `models.py`

Add the three fields (defaults keep mini-summary compatibility):

```python
class TelemetrySummary(BaseModel):
    network_id: str
    window_end: float
    window_seq: int | None = None      # None for control mini-summaries
    window_id: str | None = None       # f"{NETWORK_ID}:{window_seq}"
    overload: bool = False
    servers: dict[str, ServerSummary]
    storage_servers: dict[str, StorageServerSummary] = {}
    domain_summary: DomainSummary | None = None
    control_events: list[dict] = []
```

### T2 — `aggregator.py` (producer)

1. Monotonic `_window_seq` starting at 1; `window_id = f"{NETWORK_ID}:{window_seq}"`.
2. Remove both skip-publish branches (`if not window: continue` and the
   no-valid-events branch). **Always publish.** Window shape is precise:
   - **Empty** (zero valid events of any kind): `servers={}`,
     `storage_servers={}`, `domain_summary=None`, `overload=False`,
     `control_events=[]`, `window_seq` set.
   - **Any ≥1 valid event**: exactly today's `domain_summary` shape (zeros for
     missing parts) — storage-only windows keep a zeros domain_summary,
     unchanged.
3. Overload label (only when `domain_summary is not None`):

   ```python
   error_rate = (statistics.mean(s.error_rate for s in servers.values())
                 if servers else 0.0)
   overload = (domain_summary["average_cpu_percent"] >= OVERLOAD_CPU_PCT
               or domain_summary["peak_time_total_ms"] >= OVERLOAD_PEAK_LATENCY_MS
               or error_rate >= OVERLOAD_ERROR_RATE)
   ```

   `OVERLOAD_ERROR_RATE` is a fraction (default `0.05`); `OVERLOAD_CPU_PCT`
   default `5.0` (container CPU %); `OVERLOAD_PEAK_LATENCY_MS` default `1000`.
   Placeholders, pre-registered per run, identical across arms.
4. Window log: append each published window to JSONL at `WINDOW_LOG_PATH`
   (default `/tmp/window_log.jsonl`) **and** an in-memory deque (retention
   `WINDOW_LOG_RETENTION`, default 10000). On boot: load the JSONL tail into the
   deque and resume `_window_seq` from the last seq in the file (0 if none) —
   restart-continuous. A `threading.Lock` guards the deque + `_window_seq`
   against the publish loop, handler threads, and boot load.
5. Switch the HTTP server to `ThreadingHTTPServer` (port 5558), exact contract:
   - `GET /latest_summary` (existing, now includes seq/overload)
   - `GET /window?seq=N` → `200` window | `404 {"error":"not_found","seq":N}`
     | `410 {"error":"aged_out","seq":N,"first_available_seq":X}`
   - `GET /windows?after_seq=N&limit=K` (default K=100) →
     `200 {"windows":[...],"next_after_seq":M,"truncated":bool}`
     | `410 {"error":"aged_out","after_seq":N,"first_available_seq":X}`
   - `POST /ack` body `{"window_id":…,"window_seq":N,"delivered_at":ts}` →
     `200 {"ok":true}`; appends to **separate** `ack_log.jsonl`
6. `_publish_control_events` mini-summaries: `window_seq` left `None` (never
   shares the closing window's seq domain).

### T3 — `delivery_log.py`

Thread-safe CSV appender, columns
`network_id, window_seq, window_id, window_end, delivery_ts, delay_s, mode, release_ts`
(`release_ts = delivery_ts` in non-delayed modes; actual release time in delayed
mode). Plus `send_ack(base_url, window_id, window_seq, delivered_at)` —
best-effort `requests.post`, timeout 2 s, swallow errors.

### T4 — `event_preserving_source.py` (arm 1)

Per-network `last_seq` (init 0); loop `GET /windows?after_seq=last_seq&limit=1`;
on window: cache only if non-empty; `on_update`; delivery-log row; best-effort
ack; advance `last_seq`. On `410 aged_out`: record a gap row for the **full
range** `[last_seq+1, first_available_seq-1]`, advance
`last_seq = first_available_seq-1`, continue (defensive gap recovery). Sleep
`EVENT_POLL_INTERVAL_S` (default 0.5). Cache at delivery time only.

### T5 — `delayed_source.py` (arm 2)

Producer greenthread pulls in-order exactly as T4 and puts windows into an
**eventlet `Queue`** (FIFO). Consumer greenthread:

```python
while True:
    w = q.get()                      # blocks when empty; FIFO = seq order
    hub.sleep(max(0.0, (w.window_end + DELAY_S) - time.time()))
    # deliver: cache only if non-empty (at RELEASE time), on_update,
    # delivery-log row with release_ts, best-effort ack
```

Steady-state cadence = `WINDOW_S`; backlog drains one-per-step at due times
(deliver immediately if already due) — no batching, no replay. On `aged_out`:
record gap, continue. `DELAY_S` env (default 30).

### T6 — `polling_source.py` (arm 3)

Keep `/latest_summary` polling; change dedup key from `window_end` to
`window_seq` (robust to aggregator restart seq resume); replace the mini-summary
filter with `window_seq is None → skip (control)`. **Pass every observed window
(including empty) to `on_update`**; cache only non-empty in `_latest`. Record
every observed window in the delivery log. **No gap/range logging in the source**
— missed windows are computed only by the analyzer.

### T7 — `main_n1.py` / `main_n2.py` (mode selection)

- `TELEMETRY_SOURCE ∈ {zmq, poll, event_preserving, delayed_event_preserving}`.
  `zmq` is **kept** (unchanged default in `build_network_setup.sh` — RQ2/RQ3
  re-runs unaffected). Unknown value → log error + fall back to `poll`
  (deliberate; documented).
- `event_preserving` / `delayed_event_preserving` construct their source with
  `http://<aggregator-host>:5558` endpoints (same derivation poll mode uses).
- **All non-zmq modes** wire the ZMQ SUB control channel (`ZmqTelemetrySource`)
  for control events + topology; its forward predicate is
  **`summary.window_seq is None`** (never empty-servers), so empty real windows
  can't leak via ZMQ or bypass `DELAY_S`.
- Start `hub.spawn(self._housekeeping_loop)`.

### T8 — `main_n1.py` / `main_n2.py` (split + ticker + decision log)

- Remove the absent-node block and the scale-down block from
  `_on_telemetry_update`; move them into `_run_housekeeping()`.
- `_run_housekeeping` per tick:

  ```python
  def _run_housekeeping(self):
      try:
          s = self._last_summary
          if s is None or s.window_seq is None:
              return
          # absent-node detection (time-based, T9)
          for mac in self._node_registry.detect_absent(s):
              # ... same alert/cleanup submission logic as today
          # scale-down — only on windows with a domain summary
          if s.window_seq != self._last_scale_eval_seq:
              self._last_scale_eval_seq = s.window_seq     # advance for EVERY real window
              if s.domain_summary is not None:
                  # ... compute + storage scale-down with cooldown + is_busy() gating
      except Exception:
          logger.exception("[housekeeping] tick failed — continuing")
  ```

  One consideration per window (no double-count → sliding-window contract
  preserved); empty windows (`domain_summary=None`) skip evaluation exactly as
  they did before always-publish. Mini-summaries never advance
  `_last_scale_eval_seq` (they never reach `_last_summary`).
- **Concurrency invariant:** the ticker is an eventlet greenthread in the same
  hub as the delivery/poll/control loops — cooperative, no preemption.
  `_run_housekeeping` must contain **no blocking/yielding calls**;
  `_log_decision` appends to a buffered local file (no yield); any
  potentially-blocking I/O goes through `eventlet.tpool.execute`. No locks
  (append-vs-clear on `_scaling_policy` lists cannot interleave).
- `_log_decision(...)` writes CSV rows
  (`ts, network_id, window_id, action_type, action`) to `DECISION_LOG_PATH`
  (default `/tmp/decision_log.csv`) at **every Thread-2 capacity-action
  submission site**, exhaustively: scale-up per-alert submit, compute/storage
  scale-down submit, absent-node `submit_cleanup`/scale-down alert, reserve-loss
  `submit_cleanup_reserve`, reserve activation (`_handle_storage_reserve_trigger`
  — **only on actual activation**, not the latch-pending return), cross-region
  activation, and `submit_cancel_compute_drain`.

### T9 — `node_registry.py` (time-based absence)

- Add `self._last_seen_mono: dict[str, float] = {}`.
- Set at **all** addition sites: the `sync()` addition handler and the reserve
  reconstruction path in `consume_ready_storage_reserve`.
- Pop at **both** removal sites: the `sync()` removal handler and
  `unregister_reserved_node`.
- `detect_absent`:

  ```python
  now = time.monotonic()
  for mac in list(self._dynamic_node_macs):
      if now - self._birth_ts.get(mac, float('-inf')) < _NODE_BIRTH_GRACE_S:
          continue
      present = (mac in summary.servers) or (mac in summary.storage_servers)
      if present:
          self._last_seen_mono[mac] = now
      elif now - self._last_seen_mono.get(mac, now) > _TELEMETRY_TIMEOUT_S:
          timed_out.append(mac)
  ```

  `_TELEMETRY_TIMEOUT_S = max(TELEMETRY_TIMEOUT_WINDOWS * CONTROL_TICK_S, 3 * HEARTBEAT_INTERVAL_S)`
  (default `max(180,180)=180 s`; heartbeat default 60 s). Birth grace remains as
  a second protection layer for re-added nodes. Documented semantic change: the
  timeout now scales with `CONTROL_TICK_S`, not `WINDOW_S`.

### T10 — scripts

- `build_network_1.sh` / `build_network_2.sh`: add
  `-e OVERLOAD_CPU_PCT="${OVERLOAD_CPU_PCT:-5.0}"`,
  `-e OVERLOAD_PEAK_LATENCY_MS="${OVERLOAD_PEAK_LATENCY_MS:-1000}"`,
  `-e OVERLOAD_ERROR_RATE="${OVERLOAD_ERROR_RATE:-0.05}"`,
  `-e WINDOW_LOG_RETENTION="${WINDOW_LOG_RETENTION:-10000}"`,
  `-e WINDOW_LOG_PATH="${WINDOW_LOG_PATH:-/tmp/window_log.jsonl}"`
  (env-pass-through so the run harness can override per run).
- `current_state_integrated.env`: `TELEMETRY_SOURCE=event_preserving`,
  `DELAY_S=30`, `CONTROL_TICK_S=10`, `EVENT_POLL_INTERVAL_S=0.5`,
  `DELIVERY_LOG_PATH=/tmp/telemetry_delivery_log.csv`,
  `DECISION_LOG_PATH=/tmp/decision_log.csv`.
- `run_experiment.sh`: post-run, **before external cleanup**, `docker cp` the
  four artifacts: `window_log_lan1/lan2.jsonl` + `ack_log_lan1/lan2.jsonl` from
  `aggregator_n1/n2:/tmp/…`; `telemetry_delivery_log_lan1/lan2.csv` +
  `decision_log_lan1/lan2.csv` from `osken/osken_2:/tmp/…`. Write a separate
  `aggregator_env_snapshot.env` (aggregator-side vars only: `WINDOW_S`,
  `OVERLOAD_*`, `WINDOW_LOG_*`) alongside the existing
  `controller_env_snapshot.env`.
- Constraints (documented):
  `DELAY_S + WINDOW_S < _SCALE_DOWN_CANDIDATE_MAX_STALENESS_S` (default 40 < 90).
  `CONTROL_TICK_S = WINDOW_S` default for one-consideration-per-window steady
  state. `OVERLOAD_*` identical across arms/runs.

### T11 — docs

Update `telemetry_overview.md` (transport/default prose — no longer "ZMQ push
default"), `controller_telemetry_consumer.md`,
`aggregation_publication/aggregator.md`; fix the dangling
`implementation/rq1_polling_mechanism/` references (3 docs) → new
`implementation/rq1_delivery_semantics/rq1_delivery_semantics_plan.md`; note
`collect_resource_stats.py` (PUB subscriber, skips `domain_summary=None`) is
unaffected.

### T12 — validation

Models parse; aggregator publishes empty windows + monotonic seq + restart
continuity; sources deliver in order; delayed release timing
(`delay_s ≈ DELAY_S`); ticker one-consideration-per-window; control events
immediate in all modes (`window_seq=None` predicate); poll-mode `_last_summary`
advances through empties.

## 5. Measurement contract

- **Window universe** = `window_log.jsonl` (all seqs, labeled overload).
  **Delivered** = delivery-log CSV. **Missed overload windows** = overload in
  universe not in delivery log — computed by the **analyzer only**, excluding
  windows still in the DELAY_S hold queue at run end
  (`window_end + DELAY_S > universe_last_window_end`), reported separately as
  "in-delay-at-run-end".
- **Delivery-log row conventions:** a row with a non-empty `window_id` is a
  real delivered window (dedup by `window_id`). A `window_id=None` row is NOT
  a delivered window; `mode` distinguishes `gap_recovery` (aged out / never
  delivered) from `processing_error` (delivered from the log but the
  controller's `on_update` raised before consuming it).
- `delivery_delay_s = delivery_ts − window_end`; **info age at decision** =
  `decision_ts − window_end` (join via `window_id`).
- **Ack log** = producer-side acknowledgement (thesis "delivery acknowledgement"
  requirement), used for audit/cross-check; primary "delivered" source =
  delivery log CSV.
- Overhead derivable from logs (per-window counts + byte sizes).
- Documented caveats: delayed-mode local and peer (`get_latest`) signals both lag
  by `DELAY_S`; scale-down candidate staleness grows by `DELAY_S`; exactly-once
  holds absent controller restarts (analyzer dedups delivery log by `window_id`);
  release timing assumes same-host wall clocks (true today).

## 6. Dependencies

Existing only: `pydantic`, `requests`, `zmq`, `eventlet`/`os_ken.lib.hub`
(Queue via eventlet), stdlib `http.server.ThreadingHTTPServer`. No new packages,
no image build changes beyond `EXPOSE 5558`.

## 7. Documentation updates

- `docs/operation/telemetry/telemetry_overview.md`
- `docs/operation/telemetry/controller_side/controller_telemetry_consumer.md`
- `docs/operation/telemetry/aggregation_publication/aggregator.md`
- **New:** `docs/operation/telemetry/implementation/rq1_delivery_semantics/rq1_delivery_semantics_plan.md`
- Fix dangling `rq1_polling_mechanism` references in the three docs above

## 8. Out of scope / follow-ups

- The RQ1 **experiment plan** (runs, phases, thresholds, workload episodes) — a
  separate step for the Experiment Designer.
- `tese/Notes/thesis_overview.md` — untouched (scope unchanged).
- Tier 1 / reserves / cross-region remain disabled for RQ1 runs per thesis §2.

## 9. Implementation notes (2026-07-31)

- **Controller env regime:** RQ1 delivery-mode defaults live in a dedicated
  `source/scripts/testing/controller_env_overrides/rq1_delivery_semantics.env`
  (not `current_state_integrated.env`, which stays the baseline) and set
  `STORAGE_PERSISTENT_RESERVE_ENABLED=0`, `SS_ENABLED=0`,
  `CROSS_REGION_STORAGE_ENABLED=0` per thesis §2.
  **Superseded for runs (2026-07-31):** the RQ1 experiment campaign uses
  per-arm regime files `env/rq1_event_preserving.env` / `env/rq1_delayed.env` /
  `env/rq1_latest_state.env` (which also set the capacity overrides and
  `SCALEDOWN_COMPUTE_COOLDOWN_S=60`); see
  `docs/operation/testing/experiment/v2/rq1/experiment_plan.md`.
- **TELEMETRY_SOURCE pass-through:** `build_network_setup.sh` no longer forces
  `-e TELEMETRY_SOURCE="${TELEMETRY_SOURCE:-zmq}"`; it passes the var only when
  set on the shell (`${TELEMETRY_SOURCE:+-e …}`), so the controller env file is
  authoritative. Unset → controller default `zmq`.
- **Design B applies to all modes (incl. zmq):** the housekeeping split
  (absent-node + scale-down on the fixed ticker) is controller-level, so
  RQ2/RQ3 re-runs with `zmq` also use time-based housekeeping. Scale-down is
  deduped per `window_seq` (at most once per window); windows delivered between
  ticks are not individually evaluated (Design-B time-based check).
- **Delivery sources:** `_poll_one`/`_release_loop` are exception-guarded so a
  malformed window or `on_update` error cannot kill the delivery greenthread.
  The delayed release loop yields between releases (no batching); a post-stall
  backlog drains at max due-rate (approved D2 semantics).
- **Restart caveat (documented):** exactly-once delivery holds absent controller
  restarts. A mid-run controller restart re-pulls from the durable window log
  and would re-deliver windows (duplicate decisions). The RQ1 protocol must not
  restart controllers mid-run (a crash invalidates the run per thesis §8).
- **Config additions to the file map:** `scaling_config.py` (`_CONTROL_TICK_S`,
  `_TELEMETRY_TIMEOUT_S`), `build_network_1/2.sh` (aggregator env),
  `build_network_setup.sh` (pass-through), `Dockerfile` (EXPOSE 5558),
  `run_experiment.sh` (`collect_rq1_artifacts`), and the dedicated
  `rq1_delivery_semantics.env` (superseded for runs by the per-arm regime files,
  see above).
