# Plan - Adaptive Micro-Breaker for MongoDB Path Failures

**Status:** Proposed
**Scope:** Edge-server fail-fast behavior for MongoDB connectivity failures only
**Primary file:**

- `source/docker/edge_server/source/app.py`

---

## 1. Problem Summary

The current edge server uses a per-LAN breaker with a fixed `5` second cooldown.
That is too coarse for the failure pattern we are seeing:

- without a breaker, repeated requests can pile up on full MongoDB driver timeouts
- with the current fixed breaker, one brief connectivity fault can turn into a long synthetic outage window

The goal is to keep fail-fast protection while shrinking the artificial outage window.

---

## 2. Current Behavior

The current control path lives in `source/docker/edge_server/source/app.py`:

- `_CircuitBreaker`
  - `CLOSED -> OPEN -> HALF_OPEN`
  - fixed cooldown via `CIRCUIT_COOLDOWN_S`
- `timed_db(lan)`
  - checks the breaker
  - uses one LAN-pinned `MongoClient`
  - on `AutoReconnect`, retires the client and arms the recovery VIP once

This gives the right shape of protection, but the wrong timing behavior.

---

## 3. Approaches Considered

| # | Approach | Description | Pros | Cons | Effort | Risk | Edge impact |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A | Remove the breaker | Let every request attempt MongoDB access and rely on timeouts plus client retirement only. | Simplest code path. | Reintroduces repeated timeout stalls under a dead path. | Low | High | Can turn a bad backend into a timeout storm. |
| B | Keep a shorter fixed breaker | Reduce `CIRCUIT_COOLDOWN_S` from `5` seconds to a much smaller constant. | Smallest code change. | Still too blunt; a single value is either too long for small glitches or too short for persistent faults. | Low | Medium | Better than current behavior, but still not adaptive. |
| C | Adaptive micro-breaker | Start with a very short open interval, allow one probe, back off only on consecutive connectivity failures, and reset immediately on success. | Preserves fail-fast protection while minimizing synthetic outage time. | Slightly more state and transition logic. | Medium | Low | Best balance between latency protection and availability. |

**Recommended:** Approach C.

The key trade-off is simple: the edge server still needs a guard against repeated full timeout waits, but that guard should operate on the scale of hundreds of milliseconds, not five seconds.

---

## 4. Recommended Design

### 4.1 State model

Keep the same three logical states:

- `CLOSED`: all requests may try MongoDB normally
- `OPEN`: fail fast for a short interval
- `HALF_OPEN`: allow exactly one probe request

### 4.2 Trigger condition

Only connectivity-class failures should drive the breaker state machine.

Examples:

- `AutoReconnect`
- `ConnectionFailure`
- `NetworkTimeout`
- `ServerSelectionTimeoutError`

Non-connectivity command errors should not increase the breaker cooldown window.

### 4.3 Timing policy

Suggested first-pass values:

| Setting | Value | Purpose |
| --- | --- | --- |
| `MICRO_BREAKER_INITIAL_MS` | `250` | First open interval |
| `MICRO_BREAKER_BACKOFF_FACTOR` | `2.0` | Exponential backoff on consecutive failures |
| `MICRO_BREAKER_MAX_MS` | `1500` | Cap the open interval |
| `MICRO_BREAKER_PROBE_LIMIT` | `1` | Single half-open probe |

Example progression:

- first failure: `250 ms`
- second consecutive failure: `500 ms`
- third consecutive failure: `1000 ms`
- later failures: capped at `1500 ms`

Any successful probe resets the failure streak to `0` and returns the breaker to `CLOSED`.

### 4.4 Interaction with recovery VIP logic

The micro-breaker does not replace the current recovery logic.

Keep the existing behavior in `timed_db(lan)` for connection-level failures:

1. mark the breaker as failed
2. arm the one-shot recovery VIP
3. retire the stale `MongoClient`
4. let a later request recreate the client through the recovery path if needed

The change is only how long the breaker stays open and how it responds to repeated failures.

---

## 5. Implementation Plan

### Phase 1 - Error classification

Modify `source/docker/edge_server/source/app.py`.

1. Define a connectivity-error tuple.
2. Route only those exceptions into breaker backoff logic.
3. Leave command-level MongoDB errors outside the backoff state machine.

Code sketch:

```python
CONNECTIVITY_ERRORS = (
    AutoReconnect,
    ConnectionFailure,
    NetworkTimeout,
    ServerSelectionTimeoutError,
)


def _is_connectivity_error(exc: Exception) -> bool:
    return isinstance(exc, CONNECTIVITY_ERRORS)
```

### Phase 2 - Replace fixed cooldown with adaptive timing

Modify `_CircuitBreaker` in `source/docker/edge_server/source/app.py`.

1. Add failure-streak tracking.
2. Replace `_opened_at + CIRCUIT_COOLDOWN_S` with an explicit `open_until` deadline.
3. Compute the deadline from the adaptive cooldown formula.
4. Preserve exactly one half-open probe at a time.

Code sketch:

```python
class _CircuitBreaker:
    def __init__(self):
        self.state = _CircuitState.CLOSED
        self._failure_streak = 0
        self._open_until = 0.0
        self._probe_inflight = False
        self._lock = threading.Lock()

    def _cooldown_s(self) -> float:
        cooldown_ms = min(
            MICRO_BREAKER_INITIAL_MS
            * (MICRO_BREAKER_BACKOFF_FACTOR ** max(0, self._failure_streak - 1)),
            MICRO_BREAKER_MAX_MS,
        )
        return cooldown_ms / 1000.0

    def check(self) -> bool:
        now = time.monotonic()
        with self._lock:
            if self.state is _CircuitState.CLOSED:
                return True

            if self.state is _CircuitState.OPEN:
                if now < self._open_until:
                    return False
                self.state = _CircuitState.HALF_OPEN
                self._probe_inflight = False

            if self.state is _CircuitState.HALF_OPEN and not self._probe_inflight:
                self._probe_inflight = True
                return True

            return False

    def record_failure(self) -> None:
        with self._lock:
            self._failure_streak += 1
            self.state = _CircuitState.OPEN
            self._probe_inflight = False
            self._open_until = time.monotonic() + self._cooldown_s()

    def record_success(self) -> None:
        with self._lock:
            self.state = _CircuitState.CLOSED
            self._failure_streak = 0
            self._probe_inflight = False
            self._open_until = 0.0
```

### Phase 3 - Keep recovery retirement in the same slice

Modify `timed_db(lan)` in `source/docker/edge_server/source/app.py`.

1. Keep breaker checks at the start of the context manager.
2. Keep `AutoReconnect` handling local to the same block.
3. Ensure the adaptive breaker is still paired with:
   - one-shot recovery VIP arming
   - stale client retirement
   - normal success reset

Code sketch:

```python
@contextmanager
def timed_db(lan: str):
    breaker = _get_breaker(lan)
    if not breaker.check():
        raise CircuitOpenError(f"circuit open for {lan}")

    try:
        try:
            yield _get_client(lan)[DB_NAME]
            breaker.record_success()
        except CONNECTIVITY_ERRORS:
            breaker.record_failure()
            _arm_recovery_once(lan)
            _retire_client(lan)
            raise
    finally:
        ...
```

### Phase 4 - Optional config wiring

If breaker parameters should be runtime-configurable from the existing environment flow, propagate them through:

- `source/scripts/osken-controller.env`
- `source/scripts/network/build_network_1.sh`
- `source/scripts/network/build_network_2.sh`
- `source/sdn_controller/elasticity/compute_node_manager.py`

If we want the smallest first landing, keep the defaults inside `app.py` and defer env wiring to a follow-up.

---

## 6. File Map

| File | Change |
| --- | --- |
| `source/docker/edge_server/source/app.py` | Adaptive breaker state, connectivity error classification, timing policy, and integration with `timed_db(lan)` |
| `source/scripts/osken-controller.env` | Optional micro-breaker defaults |
| `source/scripts/network/build_network_1.sh` | Optional static edge env injection |
| `source/scripts/network/build_network_2.sh` | Optional static edge env injection |
| `source/sdn_controller/elasticity/compute_node_manager.py` | Optional dynamic edge env injection |
| `docs/operation/system_mechanisms.md` | Replace the fixed-breaker description with the adaptive micro-breaker behavior |
| `docs/operation/vip_routing/vip_routing_overview.md` | Update breaker semantics and recovery interaction |

---

## 7. Verification Plan

1. Run a narrow syntax check on `source/docker/edge_server/source/app.py`.
2. Induce a short MongoDB-path disruption and confirm the first open interval is sub-second.
3. Confirm exactly one half-open probe is allowed after the first open interval expires.
4. Confirm a successful probe resets the breaker immediately to `CLOSED`.
5. Confirm repeated consecutive failures back off only up to the configured cap.
6. Confirm recovery VIP arming and stale-client retirement still happen on connectivity failures.
7. Compare a short failure run before and after the change to verify that long `503` plateaus become short fail-fast clusters instead of multi-second blackout windows.

---

## 8. Out of Scope

- Extra edge-server or storage-server logging changes
- Service-log collection changes
- Telemetry schema changes
- Raw `mongod` debug logging
- Any redesign of the recovery VIP mechanism itself

---

## 9. Recommended Execution Order

1. Add connectivity error classification in `app.py`
2. Replace fixed cooldown logic with adaptive micro-breaker timing
3. Revalidate the `timed_db(lan)` recovery path
4. Optionally wire breaker parameters through the environment layer
5. Update the two operations docs that describe the breaker

This keeps the change local to the edge-server decision point and avoids reopening the broader observability surface.
