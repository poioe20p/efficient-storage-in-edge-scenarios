# Phase 3 - Request Lease Outcome Visibility

**Status:** Implemented in
[source/docker/edge_server/source/app.py](../../../../../../source/docker/edge_server/source/app.py)
and
[source/docker/edge_server/source/telemetry.py](../../../../../../source/docker/edge_server/source/telemetry.py)

**Goal:** make request-lease outcomes visible enough in request-scoped logs and
per-request telemetry for experiments, while defining the semantic contract
that later controller-side follow-up can reuse through its own dedicated event
path, without changing backend selection, replay policy, or the Phase 2
recovery semantics.

This phase does not change how a request binds, rebinds, or fails. It exposes
the result of the implemented request-lease state machine.

## 1. Why This Phase Exists

Phase 2 already introduced the request-local fields that govern failure
semantics in [app.py](../../../../../../source/docker/edge_server/source/app.py):

- `RequestLeaseLifecycle.ACTIVE`, `FAILED`, `COMPLETED`
- `rebinds_used`
- `replay_safe`
- `terminal_reason`

What is still missing is one request-scoped visibility contract that can answer
for each owner LAN touched by a request:

- did the request complete on its original epoch?
- did it complete after one bounded rebind or stale-epoch catch-up?
- did it terminate after recovery was exhausted or disallowed?

Without that final projection, experiments have to infer behavior from failure
logs and internal fields, and the later optional failed-backend avoidance phase
still lacks a clean request-level semantic source even if its concrete
controller trigger later travels through a narrower control-event path.

## 2. File Map

- [source/docker/edge_server/source/app.py](../../../../../../source/docker/edge_server/source/app.py)
- [source/docker/edge_server/source/telemetry.py](../../../../../../source/docker/edge_server/source/telemetry.py)

No Phase 3 change is required in
[source/docker/edge_server/source/platform_cache.py](../../../../../../source/docker/edge_server/source/platform_cache.py).
Phase 2 already keeps replay safety and per-operation request accounting on the
serving boundary, and this phase only exposes the final request-lease result.

## 3. Final Outcome Model

Phase 3 should describe the implemented lease fields rather than reintroducing
older names such as `state` or `recovery_used`.

Recommended final request-visible projection in
[app.py](../../../../../../source/docker/edge_server/source/app.py):

```python
def _project_request_lease_outcome(lease: RequestLease) -> dict[str, Any]:
    projected_lifecycle = (
        RequestLeaseLifecycle.FAILED
        if lease.lifecycle == RequestLeaseLifecycle.FAILED
        else RequestLeaseLifecycle.COMPLETED
    )

    if projected_lifecycle == RequestLeaseLifecycle.FAILED:
        outcome = "failure_terminal"
    elif lease.rebinds_used > 0:
        outcome = "success_after_rebind"
    else:
        outcome = "success_normal"

    return {
        "lan": lease.lan,
        "epoch_id": lease.epoch.epoch_id,
        "epoch_mode": lease.epoch.mode,
        "lifecycle": projected_lifecycle.name,
        "outcome": outcome,
        "rebinds_used": lease.rebinds_used,
        "replay_safe": lease.replay_safe,
        "terminal_reason": lease.terminal_reason,
    }


def _collect_request_lease_outcomes() -> list[dict[str, Any]]:
    registry = getattr(g, "db_request_leases", None) or {}
    return [
        _project_request_lease_outcome(lease)
        for lease in registry.values()
    ]
```

The stable outcome vocabulary for this phase should be:

- `success_normal` - request completed without consuming a rebind
- `success_after_rebind` - request completed after one bounded rebind, whether
  that rebind triggered `normal -> recovery` cutover or caught the request up
  to an already-current epoch
- `failure_terminal` - request ended in the terminal failure path

This stable vocabulary gives experiments and later controller-side follow-up a
clean semantic contract without requiring downstream consumers to parse
free-form reason strings.

Important distinction: the visibility payload is a finalized projection, not a
raw dump of the live in-memory lease. Successful leases are still `ACTIVE`
until teardown in the current implementation, so Phase 3 should report them as
`COMPLETED` in logs and telemetry without mutating the live lease early.

## 4. Response-End Finalization

Phase 3 should build the request-scoped outcome list near response end rather
than append ad hoc entries during the request. That keeps the visibility record
aligned with the final lease state that the request actually reached.

Recommended hook in
[app.py](../../../../../../source/docker/edge_server/source/app.py):

```python
@app.after_request
def _finalize_request_lease_outcomes(response):
    outcomes = _collect_request_lease_outcomes()
    g.request_lease_outcomes = outcomes
    for entry in outcomes:
        _log_request_lease_outcome(entry)
    return response
```

Placement matters. This hook should be registered after `init_telemetry(...)`
so Flask runs it before telemetry emission, and before request teardown clears
`g.db_request_leases`.

At request start, initialize the request-scoped container so the field never
leaks across requests:

```python
g.request_lease_outcomes: list[dict[str, Any]] = []
```

That initialization can live in the telemetry before-request setup or in the
existing request bootstrap path in `app.py`; the important point is that the
authoritative data still comes from `_collect_request_lease_outcomes()`.

## 5. Telemetry Integration

Extend [telemetry.py](../../../../../../source/docker/edge_server/source/telemetry.py)
at the existing per-request emission path.

Before-request initialization:

```python
g.request_lease_outcomes: list[dict[str, Any]] = []
```

After-request payload extension:

```python
event["request_lease_outcomes"] = getattr(g, "request_lease_outcomes", [])
```

This keeps visibility tied to the existing request telemetry stream rather than
inventing a second request-outcome channel.

`telemetry.py` should transport the already-projected records from `g` rather
than walk `db_request_leases` directly. The lease semantics belong to the
owning module in `app.py`, and the telemetry layer should remain a passive
request-event emitter.

This Phase 3 scope stops at the edge-server request frame and log output. It
does not yet require the aggregator to roll `request_lease_outcomes` into its
window summaries or the existing experiment CSV collectors to add dedicated
columns for them. If later experiment automation needs that aggregated view,
that should be treated as a separate follow-on to this base visibility phase.

Likewise, later controller-side failed-backend avoidance should not consume
`request_lease_outcomes` directly from the telemetry summary path. It should
reuse the same request-level semantics, but publish its own dedicated terminal
failure control event on the existing `control_events` route described in the
separate `03_` plan.

## 6. Logging Hooks

Recommended logging pattern in
[app.py](../../../../../../source/docker/edge_server/source/app.py):

```python
def _log_request_lease_outcome(entry: dict[str, Any]) -> None:
    log.info(
        "request lease outcome request_id=%s lan=%s lifecycle=%s outcome=%s "
        "epoch_id=%s epoch_mode=%s rebinds_used=%s replay_safe=%s "
        "terminal_reason=%s",
        getattr(g, "request_id", "unknown"),
        entry["lan"],
        entry["lifecycle"],
        entry["outcome"],
        entry["epoch_id"],
        entry["epoch_mode"],
        entry["rebinds_used"],
        entry["replay_safe"],
        entry["terminal_reason"],
    )
```

This should emit one final line per request-owned lease, not one line per
intermediate transition. The goal of this phase is a clean request-level
outcome contract. If later debugging needs transition-level traces, that can be
added separately without changing the base Phase 3 schema.

The log line is intentionally parallel to the existing `_log_db_failure(...)`
shape so run artifacts remain easy to correlate.

## 7. Documentation Surface

Once the code lands, update:

- [../../vip_routing_overview.md](../../vip_routing_overview.md)
- [../../../system_mechanisms.md](../../../system_mechanisms.md)
- [../vip_data_recovery_epoch_model.md](../vip_data_recovery_epoch_model.md)
- [../../../other/edge_storage_connection_epoch_visuals.md](../../../other/edge_storage_connection_epoch_visuals.md)
- [../../../telemetry/telemetry_overview.md](../../../telemetry/telemetry_overview.md)

The docs should explain that the epoch remains the lower-level path owner,
while the request lease is the user-visible correctness boundary. Request
telemetry should describe the final per-LAN lease outcome projection rather
than exposing raw internal lifecycle timing. They should also make the scope
boundary explicit: Phase 3 adds request-level visibility to edge-server logs
and per-request telemetry, while controller-trigger wiring remains part of the
separate control-event follow-up.

## 8. Verification

1. Per-request edge-server telemetry includes one `request_lease_outcomes`
    record per owner LAN touched by the request.
2. Successful requests are reported as `COMPLETED` in the visibility payload
   even though the live lease is only marked `COMPLETED` during teardown.
3. Request telemetry can distinguish `success_normal`,
   `success_after_rebind`, and `failure_terminal`.
4. Logs emit one final structured outcome line per request-owned lease with the
   final epoch id, epoch mode, lifecycle, rebind count, replay safety, and
   terminal reason.
5. Outcome fields remain request-scoped and do not leak across requests.
6. Phase 3 does not change breaker admission, backend selection, replay
    behavior, or the separate control-event contract used by later
    controller-side follow-up.
