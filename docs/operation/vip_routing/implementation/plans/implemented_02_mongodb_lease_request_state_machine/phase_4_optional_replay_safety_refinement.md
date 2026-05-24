# Phase 4 - Optional Replay Safety Refinement

**Goal:** recover more safely replayable requests without weakening
correctness.

This phase is optional. It should land only if the conservative replay-safety
gate from Phase 2 proves too restrictive for the target experiments.

## 1. Why This Phase Exists

Phase 2 intentionally treats mutating or ambiguous work as replay unsafe by
default. That is the safe default, but it may be stricter than necessary for
some specific operations.

This phase exists to carve out narrowly provable replay-safe cases without
undoing the fail-safe default.

## 2. File Map

- [source/docker/edge_server/source/platform_cache.py](../../../../../../source/docker/edge_server/source/platform_cache.py)
- [source/docker/edge_server/source/app.py](../../../../../../source/docker/edge_server/source/app.py)

## 3. Refinement Direction

The intended refinement is explicit annotation, not implicit guesswork.

Recommended annotation shape:

```python
@dataclass(frozen=True)
class LeaseOpPolicy:
    replay_safe: bool
    write_intent: bool
```

Example policy table:

```python
LEASE_OP_POLICIES = {
    "sensor_reports.find_one": LeaseOpPolicy(replay_safe=True, write_intent=False),
    "device_registry.find_one": LeaseOpPolicy(replay_safe=True, write_intent=False),
}
```

Local support-state writes committed to the serving edge buffer are outside the
request-owned Mongo lease model and therefore do not appear in this policy
table.

## 4. Helper Boundary

Recommended explicit API at the call-site boundary:

```python
def run_with_request_lease_policy(
    lan: str,
    *,
    op_name: str,
    fn: Callable[[Any], T],
) -> T:
    policy = LEASE_OP_POLICIES[op_name]
    return run_with_request_lease(
        lan,
        op_name=op_name,
        replay_safe=policy.replay_safe,
        fn=fn,
    )
```

This keeps the default behavior conservative while making any relaxation
explicit in code review.

## 5. Constraints

1. No unannotated mutating operation should become replay-safe by accident.
2. Ambiguous write outcomes must still fail conservatively.
3. The request lease state machine from Phases 1 through 3 remains unchanged;
   only the replay-safety input gets refined.

## 6. Verification

1. Explicitly annotated replay-safe operations can use the one bounded cutover.
2. Unannotated or ambiguous writes still fail conservatively.
3. Request telemetry remains able to distinguish safe recovery from terminal
   failure.
