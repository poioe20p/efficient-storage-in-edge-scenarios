# Plan: VIP Warm Start and VIP_DATA Recovery Path

This is the umbrella plan for the approved storage-recovery redesign. It
replaces the earlier refresh-centric idea in this file with a phased approach
that preserves the current VIP-based control pattern:

- the controller remains the only storage-backend selector
- the edge server only chooses whether the next Mongo client uses the normal
  VIP or a one-shot recovery VIP
- no controller-driven `PUT /vip_data` refresh is used for this scenario

## TL;DR

Implement the storage fix in phases:

1. **Phase 1 — fix warm node selection in the controller**
   Land bounded warm storage leases in
   [vip_routing.py](../../../../source/sdn_controller/vip_routing.py) and wire
   storage promotion in [main_n1.py](../../../../source/sdn_controller/main_n1.py)
   and [main_n2.py](../../../../source/sdn_controller/main_n2.py) to mark a
   promoted storage backend warm.

2. **Phase 2 — add one-shot recovery VIPs**
   Add `VIP_DATA_RECOVERY_N1` and `VIP_DATA_RECOVERY_N2`, and make the edge
   server in [app.py](../../../../source/docker/edge_server/source/app.py) use
   them only on the next client creation after a main-path connection failure.

3. **Phase 3 — keep recovery narrow and temporary**
   Recovery VIP flows are narrow and port-specific, recovered Mongo clients are
   reused for a bounded recovery session, and then the edge server switches
   back to the normal `VIP_DATA` path once the stale steady-state flow has had
   time to expire naturally.

4. **Phase 4 — optional follow-up**
   Add short-lived "avoid last failed backend" memory only if runs still show
   repeated reselection of the same unhealthy storage backend after Phases 1–3.

## Current Starting Point

This sequence starts from a mixed state in the current controller code:

- [main_n1.py](../../../../source/sdn_controller/main_n1.py) and
  [main_n2.py](../../../../source/sdn_controller/main_n2.py) already mark
  promoted storage backends warm, but they still retain the older
  promotion-triggered `/vip_data` refresh queue that this redesign is meant to
  retire.
- [vip_routing.py](../../../../source/sdn_controller/vip_routing.py) already
  contains the bounded warm-lease implementation and the controller-side
  lifecycle helpers that Phase 1 required.
- [app.py](../../../../source/docker/edge_server/source/app.py) still uses the
  current `vip_data_per_domain` map and `/vip_data` endpoint. That endpoint
  still retires the cached client for every provided LAN, even when the VIP
  mapping did not change, and the later `VIP_DATA_RECOVERY_*` path described
  in this plan is not implemented yet.

This document describes the intended convergence sequence from that starting
point to the approved recovery-VIP design.

## Problem

The remaining storage failure gap has two separate causes:

1. The edge server already retires a bad Mongo client in
   [app.py](../../../../source/docker/edge_server/source/app.py), but the
   current broad `VIP_DATA` flow can still match the next Mongo reconnect, so
   the controller may never get a fresh storage-selection opportunity.
2. The old promotion-triggered `/vip_data` refresh path and the current
  `/vip_data` endpoint semantics still try to create reconnect churn on the
  normal VIP, but that does not reliably force a fresh controller-visible
  selection. The promotion path in
   [main_n1.py](../../../../source/sdn_controller/main_n1.py) and
   [main_n2.py](../../../../source/sdn_controller/main_n2.py) expects
  storage promotion to make the backend eligible and warm, while the approved
  design reserves failure-triggered reselection for the recovery VIP path.

So the fix needs both:

- a guaranteed fresh selection opportunity after a real storage-path failure
- removal of the old refresh-centric path so recovery VIP is the only intended
  post-failure reselection mechanism

## Approved Decisions

- **Selector ownership:** the controller remains the only place that chooses a
  concrete storage backend.
- **No refresh fan-out:** do not use controller-driven `PUT /vip_data` refresh
  in this design; it risks disrupting healthy active connections.
- **Config-only `/vip_data`:** keep `/vip_data` only as a domain-to-VIP mapping
  surface; same-value updates are idempotent and must not retire the cached
  client.
- **No promotion-triggered refresh:** once Phase 2 lands, promotion-triggered
  `/vip_data` refresh should be removed from
  [main_n1.py](../../../../source/sdn_controller/main_n1.py) and
  [main_n2.py](../../../../source/sdn_controller/main_n2.py).
- **Recovery trigger:** arm recovery only on connection-level failures that
  retire the current Mongo client; generic query errors do not force recovery.
- **Recovery transport:** use per-domain recovery VIPs instead of a new direct
  synchronous side channel or MongoDB protocol metadata.
- **Recovery VIP identity:** recovery dispatch must preserve the recovery VIP
  IP/MAC identity inside the shared `_handle_vip_data(...)` path; the recovery
  flag is not only a selector hint.
- **Warm policy:** use short bounded warm leases with monotonic time expiry
  only, not an unbounded preference.
- **Warm identity safety:** dynamic backend IP/MAC identities are allocator-
  recycled, so Phase 1 must explicitly clear warm-lease state on intentional
  backend removal and still overwrite any prior lease on later admission
  before the backend becomes claimable.
- **Warm activation point:** mark a dynamic storage backend warm when it
  becomes `SECONDARY` and is admitted into the storage membership set.
- **Warm consumption model:** the bounded warm lease biases whichever eligible
  fresh storage selections occur before it expires; later recovery path limits
  exist to increase the odds that at least one such selection occurs within
  that short time window.
- **Warm timing model:** warm windows should stay close to the elasticity
  reaction horizon that produced the node, not the full `VIP_HARD_TIMEOUT`.
- **Recovery rule shape:** recovery flows must be narrower and shorter-lived
  than the steady-state `VIP_DATA` rule; they should match the recovery VIP and
  the Mongo client TCP source port.
- **Recovered-client lifecycle:** do not close the recovered Mongo client after
  every HTTP request; reuse it for a bounded recovery session and then switch
  back to the normal `VIP_DATA` path.
- **Switchback timing:** the recovery session max age should be slightly longer
  than the normal `VIP_DATA` idle timeout so the stale broad steady-state flow
  can expire naturally.
- **Storage vs compute capture:** Phases 2 and 3 are the intended storage-side
  answer to the fresh-selection gap; compute warm-start remains passive, so
  lack of forced fresh selection is only an expected limitation for compute or
  for a Phase-1-only rollout.
- **Compute scope:** compute warm-start remains passive and separate; this plan
  does not add compute scale-up logic or per-connection `VIP_SERVER` steering.

## Why This Shape

The current code already gives the system the right ownership boundaries:

1. [vip_routing.py](../../../../source/sdn_controller/vip_routing.py) owns
   backend choice for `VIP_SERVER` and `VIP_DATA`.
2. [app.py](../../../../source/docker/edge_server/source/app.py) already keeps
   one cached `MongoClient` per owner LAN and already retires it on
   connection-level failure.

What is missing is a way to make the next post-failure Mongo connection hit a
fresh controller decision without inventing a new controller-facing protocol.
Using a recovery VIP keeps that hint in-band on the same VIP pattern the system
already uses.

MongoDB-level metadata does not solve this problem. Fields like `appname`,
`comment`, read preference, or handshake metadata exist above TCP, while the
controller only sees the packet headers that reach the OpenFlow pipeline.

The recovery VIP also avoids the consistency problem of a new direct side
channel. Controller-to-edge control can continue to use the current HTTP
surface as a configuration surface only, and edge-to-controller async
telemetry can continue to use the current aggregator path. The only new
behavior is which VIP address the next Mongo client dials after a real
connection-level failure.

Phase 1 is intentionally useful on its own: it fixes controller-side warm
selection regardless of whether recovery VIPs already exist. Phases 2 and 3
then decide when and how many fresh selection opportunities are created within
that bounded warm-lease window.

## Scope

### In scope

- bounded warm-start preference for newly eligible dynamic storage backends
- one-shot `VIP_DATA_RECOVERY_*` paths for fresh post-failure storage
  selection
- narrow, port-specific recovery flows that avoid reproducing the broad normal
  `VIP_DATA` stickiness problem
- bounded recovery-session reuse and automatic switchback to normal
  `VIP_DATA`
- the controller-side warm selection fix that lets promoted dynamic storage win
  when the fresh selection opportunity occurs

### Out of scope

- controller-driven `PUT /vip_data` refresh for this scenario
- direct backend steering inside the edge server
- closing the recovered Mongo client after every HTTP request
- new direct synchronous controller hint channels
- compute scale-up changes
- per-connection `VIP_SERVER` routing

## Multi-Phase Breakdown

### Phase 1 — Fix Warm Storage Selection in the Controller

Reference: [vip_warm_leases_plan.md](./vip_warm_leases_plan.md)

Phase 1 stays controller-local. It lands the bounded warm-lease machinery in
`VipRoutingMixin`, wires the existing promotion hooks to it, and makes the
controller capable of preferring newly promoted dynamic storage on the next
eligible fresh selection opportunity.

This phase is now the live starting point for the remaining work. The next
phases should build on the landed warm-lease helpers rather than still
describing them as absent.

Phase 1 alone does not solve the storage reconnect-capture problem. It only
ensures that when a fresh storage selection opportunity reaches the controller,
the promoted backend can win it. Phases 2 and 3 are the intended storage-side
mechanism for creating those bounded fresh selections; compute remains
natural-move only.

### Phase 2 — Add Recovery VIPs and Edge Recovery Arming

Reference: [vip_data_recovery_vip_arming_plan.md](./vip_data_recovery_vip_arming_plan.md)

Phase 2 introduces `VIP_DATA_RECOVERY_N1` and `VIP_DATA_RECOVERY_N2`, teaches
the controller to answer and punt those VIPs, and adds one-shot recovery arming
to the edge server so the next fresh `MongoClient` creation after a real
connection-level failure reaches a fresh controller decision. As part of that
convergence, the earlier promotion-triggered `/vip_data` refresh queue is
removed and `/vip_data` remains config-only.

### Phase 3 — Keep Recovery Narrow and Temporary

Reference: [vip_data_recovery_flow_session_plan.md](./vip_data_recovery_flow_session_plan.md)

Phase 3 narrows recovery flows by matching the recovery VIP and Mongo TCP
source port, then bounds how long the recovered `MongoClient` stays on that
temporary path before later fresh connections return to normal `VIP_DATA`.

### Phase 4 — Optional Follow-Up: Failed-Backend Avoidance

Reference: [vip_data_failed_backend_avoidance_plan.md](./vip_data_failed_backend_avoidance_plan.md)

Only if experiments after Phases 1–3 still show repeated selection of the same
unhealthy backend, Phase 4 adds a short-lived controller-side avoid-last-failed
memory keyed by `(edge_server, domain)`.

## Supporting Plans

- [vip_warm_leases_plan.md](./vip_warm_leases_plan.md)
  Defines the bounded warm-lease machinery that Phase 1 relies on.
- [vip_data_recovery_vip_arming_plan.md](./vip_data_recovery_vip_arming_plan.md)
  Defines the controller recovery VIPs and edge-server one-shot arming used in
  Phase 2.
- [vip_data_recovery_flow_session_plan.md](./vip_data_recovery_flow_session_plan.md)
  Defines the narrow recovery-flow rules and bounded recovered-client lifetime
  used in Phase 3.
- [vip_data_failed_backend_avoidance_plan.md](./vip_data_failed_backend_avoidance_plan.md)
  Defines the optional avoid-last-failed controller memory for Phase 4.

## Consolidated File Ownership

- [vip_routing.py](../../../../source/sdn_controller/vip_routing.py)
  Warm leases, warm-first storage selection, recovery-VIP ARP/IP punt rules,
  and narrow recovery-flow installation.
- [main_n1.py](../../../../source/sdn_controller/main_n1.py)
  LAN1 storage promotion marks the backend warm; Phase 2 also removes the old
  promotion-triggered `/vip_data` refresh queue here.
- [main_n2.py](../../../../source/sdn_controller/main_n2.py)
  LAN2 storage promotion marks the backend warm; Phase 2 also removes the old
  promotion-triggered `/vip_data` refresh queue here.
- [topology.py](../../../../source/sdn_controller/topology/topology.py)
  Adds controller-side recovery VIP configuration.
- [scaling_config.py](../../../../source/sdn_controller/scaling_config.py)
  Holds the Phase 1 warm-lease knobs and is the source of truth for warm-start
  timing once Phase 1 lands; `vip_routing.py` should import those constants
  rather than re-parsing duplicate warm-start env vars.
- [app.py](../../../../source/docker/edge_server/source/app.py)
  Keeps `/vip_data` config-only and idempotent, arms one-shot recovery after
  main-path connection failure, chooses the next normal or recovery VIP for
  fresh client creation, and bounds the recovery session lifetime in later
  phases.
- [osken-controller.env](../../../../source/scripts/osken-controller.env)
  Defines controller-side recovery VIP addresses, MACs, and later recovery-flow
  timeout knobs.
- [compute_node_manager.py](../../../../source/sdn_controller/elasticity/compute_node_manager.py)
  Propagates recovery VIP env overrides into dynamically launched edge-server
  containers so static and dynamic launches stay aligned.
- [node_common.py](../../../../source/sdn_controller/elasticity/node_common.py)
  Documents `.252`–`.254` as reserved VIP space once recovery VIPs are added.
- [build_network_1.sh](../../../../source/scripts/network/build_network_1.sh)
  Wires recovery-related env vars into the LAN1 edge-server container when
  experiment control needs explicit container env.
- [build_network_2.sh](../../../../source/scripts/network/build_network_2.sh)
  Wires recovery-related env vars into the LAN2 edge-server container when
  experiment control needs explicit container env.
- [add_network_node.sh](../../../../source/scripts/network/add_network_node.sh)
  Documents `.252` as reserved in the shell-side attachment path alongside the
  other VIP suffixes.

Potential follow-up file updates once implementation lands:

- [create_test_clients.sh](../../../../source/scripts/network/clients/create_test_clients.sh)
- [test_conectivity.sh](../../../../source/scripts/test_conectivity.sh)

## Consolidated Verification

Validate the sequence experimentally after each phase. Phase 1 should show
warm-lease creation and claim in the controller. Phases 2 and 3 should then
show that a real connection-level failure can force one or more bounded fresh
storage selections through `VIP_DATA_RECOVERY_*`, reuse the recovered client
for a limited interval, and eventually return traffic to the normal
`VIP_DATA` path without relying on steady-state refresh fan-out as the desired
failover mechanism.

Also confirm that same-value `/vip_data` updates are idempotent and that
promotion to `SECONDARY` no longer triggers controller-driven refresh fan-out.

## Dependencies

- no new external packages
- reuse the current VIP ownership model in
  [vip_routing.py](../../../../source/sdn_controller/vip_routing.py)
- reuse the current edge-server Mongo-client lifecycle in
  [app.py](../../../../source/docker/edge_server/source/app.py)
- reuse the current controller env/config pattern in
  [osken-controller.env](../../../../source/scripts/osken-controller.env)
  and the current edge-server container wiring in
  [build_network_1.sh](../../../../source/scripts/network/build_network_1.sh)
  and [build_network_2.sh](../../../../source/scripts/network/build_network_2.sh)

## Documentation Updates

Update these documents once implementation lands:

- [vip_routing_overview.md](../vip_routing_overview.md)
  Document the distinction between the broad steady-state `VIP_DATA` path and
  the one-shot `VIP_DATA_RECOVERY` path.
- [system_mechanisms.md](../../system_mechanisms.md)
  Explain the failure-to-recovery sequence, bounded recovery session, and the
  controller-side warm preference.
- [elasticity_overview.md](../../elasticy_manager/elasticity_overview.md)
  Note that storage promotion to `SECONDARY` now creates a warm lease that is
  consumed by the next eligible storage selection opportunity.
- [telemetry_overview.md](../../telemetry/telemetry_overview.md)
  Update any references that still imply active client refresh is the storage
  failover path.

## Deferred Follow-Up

- short-lived avoid-last-failed-backend memory
- cross-controller coordination if future runs show a peer-LAN recovery gap
- per-connection `VIP_SERVER` steering
- compute recovery or elasticity changes tied to storage-path failures
