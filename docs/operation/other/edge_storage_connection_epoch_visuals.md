# Edge Storage Connection Epoch Visuals

This note captures the implemented edge-server epoch model visually so the
request boundary, cutover behavior, and housekeeping responsibilities stay easy
to reason about.

Related references:

- [vip_routing_overview.md](../vip_routing/vip_routing_overview.md)
- [system_mechanisms.md](../system_mechanisms.md)
- [vip_data_recovery_flow_session_plan.md](../vip_routing/implementation/vip_data_recovery_flow_session_plan.md)

## 1. LAN-Scoped Runtime Ownership

```mermaid
graph TD
    State["_LanEpochState\nnormal_vip_ip\nrecovery_vip_ip\nbreaker\ncurrent\nretiring[]"]
    Current["current epoch\nepoch_id\nmode\nvip_ip\nclient\nlease_count\nrecovery_expires_at"]
    Retiring["retiring epochs\nold vip_ip\nold client\ndrain_deadline\nlease_count"]
    Breaker["single circuit breaker\nCLOSED / OPEN / HALF_OPEN"]

    State --> Current
    State --> Retiring
    State --> Breaker
```

What this means:

- one LAN owns one breaker and one lifecycle lock
- the current epoch is the path for newly admitted requests
- retiring epochs keep old requests alive until their leases drain

## 2. Request Lease and Failure Rotation

```mermaid
sequenceDiagram
    participant ReqA as Request A
    participant App as app.py
    participant Epoch1 as Epoch 1 (normal)
    participant Epoch2 as Epoch 2 (recovery)
    participant Ctrl as VIP routing / controller

    ReqA->>App: timed_db(lan)
    App->>Epoch1: lease current epoch
    App->>Epoch1: lazy client creation if needed
    ReqA->>Ctrl: traffic via Epoch 1 vip_ip
    Ctrl-->>ReqA: Mongo path active

    ReqA->>App: AutoReconnect
    App->>App: CAS rotate current epoch
    App->>Epoch1: mark retiring
    App->>Epoch2: create new current recovery epoch

    Note over ReqA,Epoch1: Request A still holds Epoch 1

    participant ReqB as Request B
    ReqB->>App: timed_db(lan)
    App->>Epoch2: lease new current epoch
    ReqB->>Ctrl: traffic via recovery vip_ip
```

Key property:

- old and new requests can overlap without sharing the same mutable client
  state after rotation

## 3. VIP Update Cutover

```mermaid
sequenceDiagram
    participant CP as PUT /vip_data
    participant App as app.py
    participant Old as current epoch (old VIP)
    participant New as current epoch (new VIP)

    CP->>App: validate payload
    App->>App: reject malformed or unknown LANs
    App->>Old: move old current to retiring
    App->>New: create replacement normal epoch with new VIP

    Note over Old: already leased requests keep old VIP path
    Note over New: newly admitted requests use new VIP path
```

## 4. Housekeeping Ownership

```mermaid
graph LR
    Sweep["epoch housekeeping loop"] --> Expiry["roll expired recovery epochs\nback to normal"]
    Sweep --> Drain["close drained retiring epochs\nlease_count == 0"]
    Drain --> Warn["warn if drain deadline passed\nbut leases still active"]
    Expiry --> Continue["log per-LAN config errors\nand continue"]
```

The important separation is that request-end hooks no longer own recovery
rollback. They only accumulate and log `T_dados`; housekeeping owns bounded
recovery expiry and drained-epoch cleanup.

## 5. Rationale Snapshot

Epoch began as a way to reduce the blast radius of a damaged shared MongoDB
client. It became the owning abstraction for request attribution, bound VIP
selection, recovery lifecycle, `/vip_data` cutover, breaker installation, and
cleanup because those responsibilities have to move together for overlapping
failures and VIP updates to stay coherent.