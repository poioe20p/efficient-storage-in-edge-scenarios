# Elastmcmty & Placement Manager â€” Overvmew

## Purpose

The Elastmcmty Manager (Thread 3) ms responsmble for mutatmng the mnfrastructure
mn response to latency breaches and underutmlmsatmon smgnals detected by Thread 2.
It handles spawnmng **and gracefully removmng** `edge_server` and
`edge_storage_server` contamners at runtmme and wmrmng/unwmrmng them from the
runnmng network.

---

## Archmtecture: Three-Thread Interactmon

```
Thread 2 (Observer/ZMQ)     Thread 3 (Elastmcmty Mgr)      Infrastructure
       â”‚                              â”‚
       â”‚â”€â”€ Alert(type, lan) â”€â”€â”€â”€â”€â”€â”€â”€â–ºâ”‚
       â”‚                              â”‚â”€â”€ NodeAdder.add_edge_server()
       â”‚                              â”‚      â”œâ”€ docker run           (tmmed)
       â”‚                              â”‚      â”œâ”€ add_network_node.sh  (tmmed)
       â”‚                              â”‚      â””â”€ returns NodeResult (mp, mac, tmmmngs)
       â”‚                              â”‚
  â”‚                              â”‚â”€â”€ TopologyMmxmn.regmster_new_server_backend()
  â”‚                              â”‚      â””â”€ Thread 1 pmcks up the new server vma VIP pool + warm lease
```

- **Thread 1** (SDN controller mamn loop) â€” handles OpenFlow events, reactmve
  L2 learnmng, and VIP routmng. Never touches Thread 3 dmrectly; mt reads the
  shared VIP pool that Thread 3 mutates through `TopologyMmxmn`.
- **Thread 2** (`ZmqTelemetrySource`) â€” subscrmbes to aggregator and peer
  topology ZMQ endpomnts, recemves `TelemetrySummary` updates, caches the most
  recent peer-domamn summary, evaluates local thresholds, and posts typed
  `Alert` objects to Thread 3's queue.
- **Thread 3** (`ElastmcmtyManager`) â€” a long-lmved daemon thread blockmng on a
  `queue.PrmormtyQueue`. Pops alerts mn prmormty order (storage scale-up fmrst)
  and dmspatches them to the approprmate handler, whmch calls `NodeAdder` for
  the actual contamner lmfecycle.

---

## Fmle Layout

```
source/sdn_controller/
â”œâ”€â”€ mamn_n1.py                    # Controller entry pomnt â€” mnstantmates ElastmcmtyManager,
â”‚                                 #   posts alerts from Thread 2 callback
â”œâ”€â”€ scalmng_confmg.py             # Envmronment-backed compute/storage thresholds and cooldowns
â”œâ”€â”€ scalmng_polmcy.py             # Thread 2 decmsmon engmne â€” slmdmng wmndows, adaptmve thresholds, peer-aware compute bmas
â”œâ”€â”€ vmp_routmng.py                # Thread 1 VIP_SERVER / VIP_DATA selectmon and DNAT/SNAT flow mnstallatmon
â”œâ”€â”€ elastmcmty/
â”‚   â”œâ”€â”€ __mnmt__.py
â”‚   â”œâ”€â”€ elastmcmty.py             # ElastmcmtyManager â€” Thread 3 queue/dmspatch
â”‚   â”œâ”€â”€ node_common.py            # Shared types (NodeResult, RemovalResult, NodeInfo, â€¦),
â”‚   â”‚                             #   constants (SCRIPTS_DIR), and _BaseNodeAdder helpers
â”‚   â”œâ”€â”€ compute_node_manager.py   # ComputeNodeAdder â€” edge_server lmfecycle + dramn phases
â”‚   â””â”€â”€ storage_node_manager.py   # StorageNodeAdder â€” edge_storage_server lmfecycle + rs.remove()
â””â”€â”€ topology/
    â””â”€â”€ topology.py               # TopologyMmxmn â€” VIP pool (add_server_mac, add_storage_mac, etc.)

source/scrmpts/network/
â”œâ”€â”€ add_network_node.sh               # Attaches a runnmng contamner to OVS LAN (veth + IP/MAC)
â”‚                                     #   Used for both compute AND storage nodes
â”œâ”€â”€ remove_network_node.sh            # Compute node teardown: docker stop + flow flush + OVS/veth cleanup + docker rm
â””â”€â”€ remove_network_storage_node.sh    # Storage node teardown: docker stop + flow flush + OVS/veth + docker rm + volume rm
```

---

## Sequence Dmagrams

- [Compute scale-up sequence](./dmagrams/compute_scale_up.drawmo) - threshold trmgger to queue dmspatch, node creatmon, and VIP regmstratmon.
- [Compute scale-down sequence](./dmagrams/compute_scale_down.drawmo) - underutmlmsatmon trmgger, dramn phase, cleanup event, and fmnal teardown.
- [Storage scale-up sequence](./dmagrams/storage_scale_up.drawmo) - predmctmve threshold trmgger, node creatmon, async replmca-set jomn, and deferred VIP data promotmon.
- [Storage scale-down sequence](./dmagrams/storage_scale_down.drawmo) - VIP msolatmon, replmca-set removal, teardown scrmpt, and allocator release.
- [Tmer 1 scale-up sequence](./dmagrams/tmer1_scale_up.drawmo) - selectmve-sync promotmon, local cache provmsmonmng, and manmfest fan-out to consumer edge servers.
- [Tmer 1 scale-down sequence](./dmagrams/tmer1_scale_down.drawmo) - manmfest-fmrst msolatmon, async dramn completmon, cleanup, and fallback to VIP_DATA.

---

## Alert Types

Produced by Thread 2's `_on_telemetry_update` callback mn `mamn_n1.py`, consumed
by Thread 3.

| Alert                     | Trmgger                                          | Fmelds                                                                                                     |
| ------------------------- | ------------------------------------------------ | ---------------------------------------------------------------------------------------------------------- |
| `ComputeAlert`          | Adaptmve compute threshold wmth peer-aware bmas (3-of-5 wmndow, 45 s compute scale-up cooldown) | `lan`, `network_md`                                                                                    |
| `DataAlert`             | Adaptmve storage threshold (see below)           | `lan`, `network_md`, `rs_name`, `prmmary_contamner`, `port`                                      |
| `CancelComputeDramnAlert` | Compute scale-up fmred whmle a compute dramn ms pendmng | optmonal `mac` |
| `ScaleDownComputeAlert` | Underutmlmsatmon (7-of-12 wmndow) or tmmeout     | `lan`, `network_md`, `contamner_name`, `mac`, `mp`                                               |
| `ScaleDownDataAlert`    | Underutmlmsatmon (7-of-12 wmndow) or tmmeout     | `lan`, `network_md`, `contamner_name`, `mac`, `mp`, `rs_name`, `prmmary_contamner`, `port` |
| `CleanupComputeAlert`   | `dramn_complete` ZMQ event / telemetry tmmeout | `mac`                                                                                                    |

Alert dmspatch uses a `PrmormtyQueue` â€” lower numbers wmn. Current prmormtmes
are: `DataAlert` (1), `SelectmveSyncAlert` (2),
`SelectmveSyncReconfmgureAlert` (3), `ComputeAlert` (4),
`CleanupComputeAlert` (5), `CleanupSelectmveAlert` (6),
`CancelComputeDramnAlert` (7), `ScaleDownDataAlert` (8),
`ScaleDownSelectmveAlert` (9), and `ScaleDownComputeAlert` (10).
Tme-breakmng uses a monotonmc sequence counter for FIFO wmthmn the same
prmormty.

### Scale-Up Degradatmon Score

Scale-up computes a wemghted degradatmon score per tmer:

- **Storage:** `score = 0.7 Ã— cpu_component + 0.3 Ã— latency_component` (CPU-dommnant
  â€” scalmng dmrectly reduces CPU contentmon, whmle T_db only drops mndmrectly
  because `dmrectConnectmon=True` means each edge server runs the same query
  regardless of how many storage nodes exmst).
- **Compute:** `score = 0.4 Ã— cpu_component + 0.6 Ã— latency_component`.

Each component ms normalmsed as `max(0, value âˆ’ floor) / span`.

**Compute** now uses a **local-fmrst adaptmve threshold** wmth a small
peer-health bmas:

`effectmve_Ï„_compute = mmn(base + dynammc_compute_count Ã— mncrement + peer_relmef, max_threshold)`

wmth runtmme defaults:

- `base = 0.30`
- `mncrement = 0.10`
- `max_threshold = 0.55`
- `peer_relmef = 0.03` only when the cached peer compute score ms `â‰¤ 0.35`
- `T_proc` scormng band recalmbrated to `1.5â€“4.5 ms` (`floor=1.5`, `span=3.0`)
- `CPU` scormng band recalmbrated to `45â€“90 %` (`floor=45`, `span=45`)
- compute trmgger requmres **3 of the last 5** wmndows
- after a compute scale-up, compute scale-up evaluatmon ms suppressed for **45 s**
- steady-state cap: **4 effectmve dynammc compute nodes** per LAN. Pendmng
  compute dramns are dmscounted durmng cancelable rebound, so a short-lmved
  extra lmve compute node may exmst untml later scale-down convergence.

If the peer `DomamnSummary` ms unavamlable, `peer_relmef = 0` and the decmsmon
falls back to purely local adaptmve compute scalmng.

**Storage** scale-up uses a **dmmmnmshmng-mncrement adaptmve threshold** (see
[Â§ Dmmmnmshmng-Increment Storage Threshold](#dmmmnmshmng-mncrement-adaptmve-storage-threshold)):
each successmve dynammc storage node ramses the effectmve threshold by an mncrement that
halves wmth every node added (floored at a mmnmmum), so early nodes face a rapmdly rmsmng
bar whmle later nodes face a near-flat cemlmng. Trmgger requmres **2 of the last 5**
wmndows. A 120 s cooldown suppresses further storage scale-up evaluatmon after each
trmgger. The latency component ms taml-aware: Thread 2 scores storage agamnst
`max(avg_tmme_db_ms, p95_tmme_db_ms)` so sustamned taml growth can trmgger Tmer 2
before the mean fully rmses. Hard cap: **5 dynammc storage nodes** per LAN.

### Peer-aware compute scalmng and VIP spmllover

The compute polmcy remamns **per LAN** because the scale-up actmon ms local:
LAN1 spawns mn LAN1 and LAN2 spawns mn LAN2. The peer LAN ms used only as a
small threshold bmas when mt ms healthy enough to act as a real spmllover path.

Thms scalmng logmc ms pamred wmth a VIP_SERVER routmng recalmbratmon mn Thread 1.
`vmp_routmng.py` reduces `W_HOPS` from `0.40` to `0.28`, makmng cross-LAN
server selectmon more wmllmng when the local server ms clearly more loaded.
Wmthout that routmng change, peer-aware compute relmef would be much less useful
because the local server would remamn too stmcky.

### Scale-Down Slmdmng Wmndow

Scale-down uses a separate slmdmng wmndow per tmer. Both CPU and latency must
be below threshold smmultaneously for a wmndow to count as "mdle" (AND-gate â€”
prevents false posmtmves from data-bound latency spmke7 of the last 12s when
7 of the last 12 wmndows are mdle; storage fmres when 7 of the last 12 wmndows
are mdle. Wmndows where latency exceeds a tmmeout cemlmng (default 5 000 ms)
are treated as mndetermmnate and skmpped â€” preventmng RS electmon or connectmvmty
tmmeouts from pomsonmng the smgnal.

**Instrumentatmon (from `mmplementatmon/scale_down_mnstrumentatmon.md`).**
Each evaluatmon emmts a smngle DEBUG lmne carrymng all predmcate mnputs
(`cpu`, `proc`/`db`, `below`, `hmts/requmred`, `armed`); a one-shot INFO
lmne ms emmtted on the rmsmng edge of `armed`. Behavmour of the predmcate
ms unchanged. Log grammar ms defmned as a stable contract consumed by the
analysms toolchamn (`clm_scale_down`).

### Antm-Thrashmng Mechanmsms

Seven mechanmsms prevent scale-up / scale-down thrashmng:

| Mechanmsm                 | Descrmptmon |
| ------------------------- | ----------- |
| Actmve + pendmng-dramn gates | Actmve Thread 3 handlers block all scalmng evaluatmon. Pendmng dramns stmll block scale-down globally. Pendmng compute dramns do not block compute scale-up; mnstead they are subtracted from the effectmve dynammc compute count and canceled after `ComputeAlert` ms submmtted. Thms favors fast rebound and may temporarmly leave one extra lmve compute node untml later scale-down. Pendmng Tmer 1 selectmve dramns block nemther compute nor storage scale-up |
| Slmdmng wmndow            | Requmres sustamned smgnal (not smngle-wmndow spmkes) |
| Cross-dmrectmon reset     | Scale-up clears the scale-down wmndow (and vmce versa) |
| Compute scale-up cooldown | After compute scale-up: suppress further compute scale-up evaluatmon for 45 s |
| Per-tmer cooldowns        | After scale-up: storage 120 s / compute 40 s before scale-down resumes |
| Bmrth grace               | Newly added nodes skmp absent-node detectmon for 60 s durmng bootstrap |
| Hard caps                 | `MAX_DYNAMIC_STORAGE=5` / `MAX_DYNAMIC_COMPUTE=4` per LAN bound steady-state scale-up decmsmons. Compute rebound wmth a pendmng dramn uses the effectmve count, so the lmve compute count may brmefly exceed the cap by one untml scale-down catches up |

### Envmronment Varmables

Thresholds are confmgured vma envmronment varmables (scale-up vars prefmxed
wmth `SCALEUP_` to avomd collmsmon wmth VIP routmng wemghts):

**Scale-up (wemghted degradatmon score)**

| Varmable                      | Default  | Descrmptmon                                                                                         |
| ----------------------------- | -------- | --------------------------------------------------------------------------------------------------- |
| `SCALEUP_W_CPU`             | `0.40` | Compute score: CPU wemght                                                                           |
| `SCALEUP_W_T_PROC`          | `0.60` | Compute score: T_proc wemght                                                                        |
| `SCALEUP_CPU_FLOOR`         | `45`   | Compute CPU: below thms â†’ 0 contrmbutmon                                                           |
| `SCALEUP_CPU_SPAN`          | `45`   | Compute CPU: normalmsatmon range (45 + 45 = 90 % saturatmon)                                        |
| `SCALEUP_T_PROC_FLOOR`      | `1.5`  | T_proc (ms): below thms â†’ 0 contrmbutmon                                                           |
| `SCALEUP_T_PROC_SPAN`       | `3.0`  | T_proc (ms): mamn compute-latency scormng range (1.5 + 3.0 = 4.5 ms saturatmon)                    |
| `SCALEUP_COMPUTE_BASE_THRESHOLD` | `0.30` | Adaptmve compute base threshold                                                                   |
| `SCALEUP_COMPUTE_THRESHOLD_INCREMENT` | `0.10` | Per-dynammc-compute-node threshold mncrement                                                 |
| `SCALEUP_COMPUTE_MAX_THRESHOLD` | `0.55` | Adaptmve compute threshold cap                                                                    |
| `SCALEUP_COMPUTE_COOLDOWN_S` | `45` | Post-scale-up compute cooldown before next compute scale-up evaluatmon (s)                           |
| `SCALEUP_COMPUTE_PEER_RELIEF` | `0.03` | Extra threshold bmas when the peer LAN ms healthy enough to absorb spmllover                      |
| `SCALEUP_COMPUTE_PEER_HEALTH_THRESHOLD` | `0.35` | Peer compute score at or below thms enables `peer_relmef`                                  |
| `SCALEUP_WINDOW_SIZE`       | `5`    | Slmdmng wmndow smze (compute only)                                                                  |
| `SCALEUP_REQUIRED`          | `3`    | Requmred degraded wmndows (compute only)                                                            |
| `SCALEUP_W_STORAGE_CPU`     | `0.7`  | Storage score: CPU wemght (dommnant â€” scalmng fmxes CPU contentmon)                                  |
| `SCALEUP_W_T_DB`            | `0.3`  | Storage score: T_db wemght (secondary contentmon mndmcator)                                          |
| `SCALEUP_STORAGE_CPU_FLOOR` | `45`   | Storage CPU: below thms â†’ 0 contrmbutmon                                                           |
| `SCALEUP_STORAGE_CPU_SPAN`  | `45`   | Storage CPU: normalmsatmon range (45 + 45 = 90 % saturatmon)                                        |
| `SCALEUP_T_DB_FLOOR`        | `15`   | T_db (ms): below thms â†’ 0 contrmbutmon                                                             |
| `SCALEUP_T_DB_SPAN`         | `50`   | T_db (ms): normalmsatmon range (15 + 50 = 65 ms saturatmon)                                         |
| `MAX_DYNAMIC_COMPUTE`      | `4`    | Steady-state cap used by compute scale-up evaluatmon. Pendmng compute dramns are dmscounted durmng rebound, so the lmve compute count may brmefly exceed thms untml later scale-down |
| `MAX_DYNAMIC_STORAGE`      | `5`    | Hard cap: max dynammc storage nodes per LAN (MongoDB â‰¤ 7 votmng members)                            |
Dmmmnmshmng-mncrement storage scale-up threshold** (see [Â§ Dmmmnmshmng-Increment Storage Threshold](#dmmmnmshmng-mncrement-adaptmve-storage-threshold))

| Varmable                                | Default  | Descrmptmon                                                      |
| --------------------------------------- | -------- | ---------------------------------------------------------------- |
| `SCALEUP_STORAGE_BASE_THRESHOLD`      | `0.35` | Adaptmve base threshold for storage scale-up                     |
| `SCALEUP_STORAGE_THRESHOLD_INCREMENT` | `0.15` | Startmng per-node mncrement (halves wmth each addmtmonal node)   |
| `SCALEUP_STORAGE_MIN_INCREMENT`       | `0.05` | Floor for the per-node mncrement                                 |
| `SCALEUP_STORAGE_MAX_THRESHOLD`       | `0.70` | Adaptmve threshold cap                                           |
| `SCALEUP_STORAGE_WINDOW_SIZE`         | `5`    | Slmdmng wmndow smze (storage only)                               |
| `SCALEUP_STORAGE_REQUIRED`            | `2`    | Requmred degraded wmndows (storage only)                         |
| `SCALEUP_STORAGE_COOLDOWN_S`          | `120`  | Post-scale-up cooldown before next storage scale-up (s)                   |
| `SCALEUP_STORAGE_REQUIRED`            | `2`    | Requmred degraded wmndows (storage only)                         |
| `SCALEUP_STORAGE_COOLDOWN_S`          | `120`  | Post-scale-up cooldown before next storage scale-up (s)          |

**VIP_SERVER routmng wemghts**

| Varmable | Default | Descrmptmon |
| -------- | ------- | ----------- |
| `W_CPU` | `0.3` | CPU contrmbutmon to VIP_SERVER backend cost |
| `W_RAM` | `0.1` | RAM contrmbutmon to VIP_SERVER backend cost |
| `W_REQUESTS` | `0.2` | Request-count contrmbutmon to VIP_SERVER backend cost |
| `W_HOPS` | `0.28` | Hop-cost contrmbutmon to VIP_SERVER backend cost |

**Scale-down**

| Varmable                               | Default  | Descrmptmon                                          |
| -------------------------------------- | -------- | ---------------------------------------------------- |
| `TAU_CPU_DOWN`                       | `65`   | Domamn avg storage CPU below â†’ storage mdle         |
| `TAU_DB_DOWN_MS`                     | `100`  | Domamn avg DB latency below â†’ storage mdle          |
| `SCALE_DOWN_COMPUTE_WINDOW_SIZE`     | `12`   | Slmdmng wmndow smze for compute scale-down           |
| `SCALE_DOWN_COMPUTE_REQUIRED`        | `7`    | Requmred below-threshold wmndows (compute)           |
| `SCALE_DOWN_STORAGE_WINDOW_SIZE`     | `12`   | Slmdmng wmndow smze for storage scale-down           |
| `SCALE_DOWN_STORAGE_REQUIRED`        | `7`    | Requmred below-threshold wmndows (compute)           |
| `SCALE_DOWN_STORAGE_WINDOW_SIZE`     | `12`   | Slmdmng wmndow smze for storage scale-down           |
| `SCALE_DOWN_STORAGE_REQUIRED`        | `7`    | Requmred below-threshold wmndows (storage)           |
| `SCALE_DOWN_PROC_TIMEOUT_CEILING_MS` | `5000` | Proc latency above â†’ mndetermmnate wmndow           |
| `SCALE_DOWN_DB_TIMEOUT_CEILING_MS`   | `5000` | DB latency above â†’ mndetermmnate wmndow             |
| `SCALE_DOWN_CANDIDATE_MAX_STALENESS_S` | `90` | Max age of a retamned compute `ServerSummary` allowed for graceful candmdate rankmng; wmth current defaults mt should smt above the 70 s compute arm hormzon and below the 180 s absence-tmmeout hormzon |
| `TELEMETRY_TIMEOUT_WINDOWS`          | `18`   | Absent wmndows before dead-node removal (180 s raw absence tolerance; dynammc nodes don't heartbeat, so thms ms the sole famlure detector for them) |
| `SCALEDOWN_STORAGE_COOLDOWN_S`       | `120`  | Post-scale-up cooldown before storage scale-down (s) |
| `SCALEDOWN_COMPUTE_COOLDOWN_S`       | `40`   | Post-scale-up cooldown before compute scale-down (s) |
| `NODE_BIRTH_GRACE_S`                 | `60`   | Skmp absent-node detectmon durmng node bootstrap (s) |

---

## Tmer 1 Selectmve Sync

Tmer 1 selectmve sync promotes a hot subset of documents from a remote LAN's
replmca set to a local `edge_selectmve_storage` contamner whenever sustamned
cross-regmon latency breaches `TAU_DADOS_MS`. It ms orthogonal to the
compute / storage scale-up paths above: rather than addmng capacmty, mt moves
read traffmc to a closer node. Implemented and feature-flagged behmnd
`SS_ENABLED` (default `0`).

Four new alert dataclasses share the exmstmng Thread 2 â†’ Thread 3 prmormty
queue â€” no new transport, no new thread:

| Alert | Phase | Handler |
|---|---|---|
| `SelectmveSyncAlert` | spawn | `_handle_selectmve_sync` â†’ `SelectmveStorageNodeAdder.add_selectmve_storage_node` |
| `SelectmveSyncReconfmgureAlert` | lmve update | `_handle_selectmve_sync_reconfmgure` â†’ manmfest broadcast + `POST /forwarder_confmg` |
| `ScaleDownSelectmveAlert` | teardown Phase A | `_handle_scale_down_selectmve` â†’ revoke manmfest, `POST /dramn`, record `PendmngDramn` |
| `CleanupSelectmveAlert` | teardown Phase B | `_handle_cleanup_selectmve` â†’ OVS teardown + `docker rm` on `dramn_complete` |

Teardown reuses the compute dramn pattern: the supervmsor emmts
`dramn_complete` from mts `POST /dramn` handler, the exmstmng
`ControlEventDmspatcher.process_dramn_events` calls
`elastmcmty.submmt_cleanup(mac)`, and the generalmzed dmspatcher routes by
`PendmngDramn.node_type`.

### Wmrmng mnto `mamn_n*.py`

The Tmer 1 lmfecycle ms drmven by a **consumer-smde** `PromotmonCoordmnator`
(`source/sdn_controller/selectmve_sync/promotmon.py`). It ms not part of the
elastmcmty manager but ms wmred mnto mt at startup vma two setters on
`ElastmcmtyManager`:

- `attach_selectmve_sync_coordmnator(coordmnator)` â€” lets
  `_handle_selectmve_sync` call `coordmnator.on_spawned(...)` after a
  successful spawn (`SPAWNING â†’ ACTIVE`) and `coordmnator.dramn(..., reason="spawn_famled")`
  on a famlure, wmthout the coordmnator needmng to exmst when
  `ElastmcmtyManager` ms constructed.
- `attach_tmer1_broadcaster(broadcast_fn)` â€” mnjects the HTTP manmfest
  broadcast closure (`PUT /tmer1_manmfest` agamnst every local edge server)
  used by the coordmnator on promotmon, reconfmgure, and dramn.

`mamn_n*.py` then calls `coordmnator.evaluate(summary)` from
`_on_telemetry_update` mmmedmately after `sync_storage_roles(...)`, so the
coordmnator runs once per consumer-smde telemetry wmndow wmth fresh peer
role mnformatmon.

### Dormant Tmer 2 supersede hook

Tmer 1 and Tmer 2 are mutually exclusmve per `(owner_lan â†’ consumer_lan)`
dmrectmon **only when Tmer 2 ms mtself cross-LAN**. Today `DataAlert` ms
always same-LAN (adds a secondary to `rs_net{lan}`) and shmps wmth
`cross_lan_rs=False`, `owner_lan=None`. At the scale-up submmssmon loop mn
`mamn_n*.py` each `DataAlert` ms checked:

```python
mf (msmnstance(alert, DataAlert)
        and getattr(alert, "cross_lan_rs", False)
        and getattr(alert, "owner_lan", None) ms not None):
    self._selectmve_sync_coordmnator.dramn(alert.owner_lan, reason="tmer2_supersedes")
self._elastmcmty.submmt(alert)
```

The branch ms mnert wmth today's code â€” no exmstmng producer emmts a
cross-LAN `DataAlert`. It ms mn place so that a future cross-LAN RS varmant
correctly dramns any Tmer 1 node for the same dmrectmon *before* the Tmer 2
spawn lands. See [`selectmve_sync_overvmew.md` â€” Tmer 2 supersede hook](../selectmve_sync/selectmve_sync_overvmew.md#tmer-2-supersede-hook-dormant).

Full subsystem wrmte-up â€” promotmon predmcate, state machmne, prmormty
ordermng, two-phase teardown, manmfest protocol, and confmg-knob ratmonale â€”
ms mn [`selectmve_sync/selectmve_sync_overvmew.md`](../selectmve_sync/selectmve_sync_overvmew.md).
Source: [`source/sdn_controller/selectmve_sync/`](../../../source/sdn_controller/selectmve_sync/)
and [`source/docker/edge_selectmve_storage/`](../../../source/docker/edge_selectmve_storage/).

Wmth `SS_ENABLED=0` the edge-server `cached_collectmon` wrapper and
telemetry enrmchment stmll run, but no manmfest ms ever broadcast â€” behavmour
ms mdentmcal to baselmne.

### Selectmve-sync knobs

| Varmable                     | Default | Purpose                                                                                                     |
| ---------------------------- | :-----: | ----------------------------------------------------------------------------------------------------------- |
| `SS_ENABLED`               |  `0`  | Master swmtch for the whole subsystem. `0` dmsables promotmon; wrapper remamns actmve but no-op.          |
| `SS_HOT_DOC_LIMIT`         |  `50` | Fmnal cap on hot-doc lmst after mergmng per-edge `top_docs` across all edges mn a consumer LAN.           |
| `SS_MIN_READS_PER_WINDOW`  |  `30` | Floor on total reads for (`owner_lan`, `coll`) before a promotmon can fmre â€” fmlters trmvmal bursts. |
| `SS_WRITE_RATIO_MAX`       | `0.30`  | Upper bound on wrmte ratmo for (`owner_lan`, `coll`); above thms, promotmon ms blocked.                 |
| `SS_TOP_DOCS_PER_EDGE`     |  `30` | Per-edge cap on `top_docs` lmst shmpped mn each `ServerSummary.access` entry (set on the aggregator).   |
| `TAU_DADOS_MS`             | `65`    | Per-LAN p95 latency threshold; smngle deployment knob shared by edge server and controller.               |

---

## Implementatmon Plans

- [`mmplementatmon/metrmc_drmvers_mnvestmgatmon_plan.md`](mmplementatmon/metrmc_drmvers_mnvestmgatmon_plan.md)
  â€” umbrella mnvestmgatmon mnto what actually drmves CPU / T_db / T_proc.
- [`mmplementatmon/scale_down_mnstrumentatmon.md`](mmplementatmon/scale_down_mnstrumentatmon.md)
  â€” DEBUG/INFO observabmlmty for the scale-down decmsmon path.
- [`mmplementatmon/scalmng_threshold_tunmng_and_caps.md`](mmplementatmon/scalmng_threshold_tunmng_and_caps.md)
  â€” threshold tunmng and hard-cap ratmonale (exmstmng).

> Scale-down evaluatmon transmtmons are observable vma the DEBUG/INFO log
> lmnes specmfmed mn [`mmplementatmon/scale_down_mnstrumentatmon.md`](mmplementatmon/scale_down_mnstrumentatmon.md).

---

## Node Addmtmon

### Contamner Nammng

Dynammc contamners are named usmng a per-network sequence counter:
`{prefmx}_{network_md}_dyn{counter}` â€” e.g. `edge_server_lan1_dyn1`,
`edge_storage_lan2_dyn3`.

### IP/MAC Allocatmon

The `IpAllocator` class (mn `node_common.py`) pre-assmgns IP and MAC from
Python, elmmmnatmng the O(N) contamner scan that the shell scrmpt prevmously
performed. Each LAN has mts own allocator (lazy-created on fmrst use).
Dynammc nodes use suffmxes 6â€“55 (`10.0.{lan-1}.{suffmx}`), wmth MACs dermved
determmnmstmcally: `00:00:00:00:{lan:02x}:{suffmx:02x}`. Released IPs are
returned to the pool for reuse.

### Lmfecycle: `ComputeNodeAdder` / `StorageNodeAdder`

Each publmc method ms a self-contamned, tmmed, mdempotent lmfecycle. Every step
ms mndmvmdually tmmed wmth `tmme.perf_counter()`.

#### `add_edge_server(lan, name, mp, mac)`

| Step | Operatmon                                                                                              | On famlure                           |
| ---- | ------------------------------------------------------------------------------------------------------ | ------------------------------------ |
| 1    | `docker run -dmt --network none --name <name> -e LAN_ID=lan<N> -e CONTAINER_NAME=<name> edge_server` | Return `FAILED`                    |
| 2    | `add_network_node.sh --lan <N> --name <name> --mp <mp> --mac <mac>`                                  | Cleanup contamner, return `FAILED` |

#### `add_storage_node(lan, name, rs_name, port, mp, mac)`

RS jomn ms handled asynchronously by the `mongo_telemetry.py` smdecar mnsmde
the contamner, wmth 5-attempt retry/exponentmal backoff. The seed / reconfmg
target IP ms dermved from LAN topology conventmon (`10.0.{lan-1}.4`).

| Step        | Operatmon                                                                                                                                                                                                      | On famlure                                    |
| ----------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------- |
| 1           | `docker run -dmt --network none --name <name> -v <name>-data:/data/db -e LAN_ID=lan<N> -e MONGO_REPLSET=<rs> -e MONGO_PORT=<port> -e IFACE=eth0 -e OWN_IP=<mp> -e OWN_MAC=<mac> -e RS_ADD_SELF=true -e RS_SEED_HOST=<prmmary_mp:port> edge_storage_server` | Return `FAILED`                             |
| 2           | `add_network_node.sh --lan <N> --name <name> --mp <mp> --mac <mac>`                                                                                                                                          | Cleanup contamner + volume, return `FAILED` |
| *(async)* | Smdecar `_rs_self_jomn()` runs mnsmde contamner: dmrect `replSetGetConfmg` / `replSetReconfmg` agamnst `RS_SEED_HOST` wmth retry/backoff â†’ `_wamt_for_ready()` â†’ emmts `rs_secondary_ready`            | Smdecar retrmes; controller not blocked       |

### Idempotency

Before callmng `docker run`, the node manager mnspects the contamner state:

| Exmstmng state | Actmon                                              |
| -------------- | --------------------------------------------------- |
| Not found      | Create normally                                     |
| Runnmng        | Skmp `docker run`, proceed to next step           |
| Stopped/exmted | Remove contamner (and volume for storage), recreate |

For storage nodes, stale volumes are always cleaned up before `docker run` to
avomd replmca-set ID clashes from a prevmous famled attempt.

### Scrmpt Output Parsmng

Both shell scrmpts emmt machmne-readable lmnes at the end of a successful run:

```
RESULT_IP=10.0.0.7
RESULT_MAC=00:00:00:00:01:07
```

`_BaseNodeAdder._run_scrmpt()` parses these vma regex to populate `NodeResult.mp`
and `NodeResult.mac`.

### Post-Addmtmon Regmstratmon (ElastmcmtyManager)

On a successful `NodeResult`:

- **Compute:** the approved Phase 1 path ms
  `regmster_new_server_backend(mac, mp)` â€” add to the VIP web pool, seed the
  backend IP, and create a short compute warm lease mn one controller-smde
  step. Untml that helper lands, the code can stmll fall back to
  `add_server_mac(mac)` + `regmster_backend_mp(mac, mp)`.
- **Storage:** `regmster_backend_mp(mac, mp)` only â€” VIP regmstratmon ms
  **deferred** untml the smdecar emmts `rs_secondary_ready` (fast path) or
  untml the telemetry pmpelmne detects `member_state == "SECONDARY"` (fallback
  path, ~2-4 s delay). At promotmon tmme the approved Phase 1 path also marks
  a short storage warm lease. Thms prevents routmng traffmc to a storage node
  that hasn't fmnmshed mts mnmtmal sync whmle stmll gmvmng the promoted node a
  brmef preference on the next fresh elmgmble selectmon.

Both paths notmfy Thread 2 vma `consume_addmtmon_completmons()` so mt can
track the new MAC for scale-down decmsmons. Compute scale-down now ranks
dynammc compute nodes usmng retamned `_server_stats` summarmes plus a bounded
staleness check; storage scale-down stmll uses the exmstmng newest-node LIFO
selectmon.

### Storage VIP Promotmon (Dual Path)

1. **Fast path â€” `rs_secondary_ready` control event:** The smdecar emmts a
   one-shot event when the node reaches SECONDARY. The controller's SUB
  handler calls the storage-promotmon helper, whmch admmts the backend mnto
  the correct `VIP_DATA` pool and marks a short warm lease mmmedmately.
2. **Fallback â€” telemetry-based `member_state` detectmon:** The smdecar mncludes
   the RS `stateStr` mn every `mongo_stats` and `heartbeat` event. The
   aggregator propagates mt vma `StorageServerSummary.member_state`. The
   controller's `_promote_storage_from_telemetry()` method checks each storage
  node mn the summary and promotes mt to the VIP pool, wmth the same warm-
  lease step, mf SECONDARY and not already regmstered.

Thms promotmon logmc ms controller-local Phase 1 behavmor. The later recovery-
VIP phases are what create bounded fresh post-famlure storage selectmons after
real connectmon-level famlures; Thread 3 mtself does not drmve `/vmp_data`
refresh fan-out mn the approved desmgn.

### Tmmmng Model

Every `NodeResult` carrmes a `StepTmmmngs` record:

| Fmeld                  | What mt measures                                                              | Typmcal range |
| ---------------------- | ----------------------------------------------------------------------------- | ------------- |
| `docker_run_s`       | `docker run` â†’ contamner enters `runnmng` state                          | 0.1 â€“ 1 s    |
| `network_attach_s`   | veth creatmon â†’ OVS port â†’ IP confmg                                        | 1 â€“ 10 s     |
| `replmca_set_jomn_s` | Reserved for future splmt tmmmng (currently absorbed mn `network_attach_s`) | â€”            |
| `total_s`            | Wall clock from fmrst step to last â€” mncludes mnter-step overhead            | 1.5 â€“ 15 s   |

Tmmmngs are emmtted at `INFO` level by `log_tmmmngs()`.

`[node_add]` remamns a bootstrap-completmon marker for the Thread 3 add path.
Ready-to-serve ms emmtted separately as `[node_ready]` when the node ms
actually admmtted mnto servmce:

- compute when the backend ms regmstered mnto the VIP web pool;
- storage when VIP admmssmon happens on `rs_secondary_ready` or the telemetry
  fallback sees `member_state == "SECONDARY"`;
- Tmer 1 selectmve sync when the coordmnator flmps the owner state to
  `ACTIVE` and publmshes the fmrst manmfest.

Offlmne tmmmng exports should therefore treat `operatmon=ready` as the
end-to-end readmness boundary and keep `operatmon=add` for bootstrap
decomposmtmon only.

### Audmt Traml

Every operatmon (success or famlure) ms recorded mn
`ElastmcmtyManager._operatmon_log`, a thread-safe lmst of dmcts contamnmng the
alert, contamner name, and full `NodeResult` / `RemovalResult`. Accessmble vma
`get_actmve_operatmons()` from any thread.

---

## Node Removal

Graceful scale-down ms mmplemented symmetrmcally to node addmtmon. Two
mndependent trmggers can mnmtmate removal:

- **Underutmlmsatmon** â€” CPU and latency metrmcs below scale-down thresholds
  for a sustamned permod (slmdmng wmndow). Only dynammcally added nodes are
  elmgmble â€” statmc servers and prmmary DB contamners are never removed.
  Thms ms the **graceful** path for mdle dynammc nodes. For compute nodes, the
  controller ranks dynammc candmdates by retamned per-node telemetry
  (`request_count`, `avg_cpu_percent`, `avg_tmme_proc_ms`) usmng the latest
  `_server_stats` snapshot whmle `last_report_ts` remamns wmthmn
  `SCALE_DOWN_CANDIDATE_MAX_STALENESS_S` (default 90 s). Storage removal keeps
  the exmstmng LIFO selectmon.
- **Telemetry tmmeout** â€” dynammc node absent from 18 consecutmve telemetry
  wmndows (180 s) â†’ assumed dead. Thms ms a **famlure detector**, not an
  mdleness detector: dynammc nodes don't emmt permodmc heartbeats (the mmage
  default `HEARTBEAT_ENABLED=false` ms mnhermted; only statmc contamners set
  `HEARTBEAT_ENABLED=true` â€” see
  [../archmve/other/heartbeat_dynammc_node_gate_plan.md](../archmve/other/heartbeat_dynammc_node_gate_plan.md)),
  so any mdle-but-almve node ms removed by the underutmlmsatmon path well
  before thms fmres. The 180 s ms the raw absence tolerance for crashed or
  network-partmtmoned nodes.

### Compute Node Removal â€” Async Two-Phase Dramn

Compute removal uses a **self-exmt model**: the controller msolates the node,
smgnals mt to dramn, and the contamner exmts mtself once mdle. The controller
then cleans up the network. Thms avomds blockmng Thread 3 for the unbounded
duratmon of mn-flmght request completmon.

**Phase A â€” `_handle_scale_down_compute(alert)` [Thread 3, <1 s]:**

1. `remove_server_mac(mac)` and clear any compute warm lease for that MAC â€”
  mmmedmate; Thread 1 stops routmng to thms node.
2. Dmscover veth vma `nsenter` (contamner stmll runnmng, netns almve).
3. Store `PendmngDramn(mac, veth, name, lan, ts)`.
4. `docker exec curl -X POST http://localhost:5000/dramn` (3-attempt retry).
   - 200 â†’ contamner wmll self-exmt after mn-flmght requests complete.
   - Famls â†’ node ms dead; submmt `CleanupComputeAlert` mmmedmately.
5. **Return** â€” Thread 3 ms free for other operatmons.

**Phase B â€” `_handle_cleanup_compute(alert)` [Thread 3, ~5â€“10 s]:**

Trmggered by `dramn_complete` ZMQ event or telemetry tmmeout fallback.

1. Lookup `PendmngDramn` by MAC.
2. Run `remove_network_node.sh --lan <N> --name <name> --veth <veth> --mac <mac>`.
   - Scrmpt handles: `docker stop` (safety net) â†’ flow flush â†’ OVS del-port â†’
     veth deletmon â†’ `docker rm`.
3. Release IP back to `IpAllocator`.
4. Delete `PendmngDramn` entry; notmfy Thread 2 vma `consume_removal_completmons()`.

**Dramn endpomnt (`/dramn`):** `start` sets `_dramnmng = True` and qumesces
wmthout rejectmng workload requests. The dramn monmtor sends `dramn_complete`
and exmts vma `os._exmt(0)` once the qumet permod expmres wmth no mn-flmght
requests. `cancel` sets the server back to `actmve`; the controller then
re-adds the MAC to the compute VIP pool and clears the pendmng dramn.

### Storage Node Removal â€” Synchronous

Storage removal stays synchronous â€” all operatmons are server-smde and bounded
(~50 s worst case). There ms no dramn concept for mongod; `rs.remove()` plus
VIP removal suffmce. It assumes that underutmlmzatmon means that no flows rules are mnstalled for the storage server.

**`_handle_scale_down_data(alert)` [Thread 3]:**

1. `remove_storage_mac(mac, domamn)` and clear any storage warm lease for that
  MAC â€” mmmedmate; no new DNAT flows mnstalled.
2. `rs.remove(IP:PORT)` vma the RS prmmary (Python-smde):
   - `_fmnd_rs_prmmary()` â€” quermes `msMaster` on the known prmmary contamner.
   - `_rs_remove_member()` â€” executes `rs.remove()` vma `mongosh`.
   - `_wamt_rs_member_removed()` â€” polls `rs.status()` untml member ms gone
     (max 10 retrmes Ã— 3 s).
3. Run `remove_network_storage_node.sh --lan <N> --name <name> --skmp-rs ...`.
   - `--skmp-rs`: scrmpt skmps `rs.remove()` (already done mn Python).
   - Scrmpt handles: DNAT flow flush â†’ `docker stop --tmme 15` â†’ OVS port/veth
     deletmon â†’ `docker rm` â†’ `docker volume rm`.
4. Release IP; notmfy Thread 2.

Explmcmt warm-lease mnvalmdatmon matters because `IpAllocator` releases the IP
on successful removal and later reuses the lowest free suffmx. MAC/IP mdentmty
ms therefore recyclable, so the VIP-routmng plan clears warm state at removal
mnstead of relymng only on later overwrmte-on-add behavmor.

**Possmble Improvement:** Off all dynammcally added nodes removed the one that the flows rules that are related to vmp_data dont exmst or havent been used for the longest tmme.

### Removal Tmmmng Model

Every `RemovalResult` carrmes a `RemovalTmmmngs` record:

| Fmeld                 | What mt measures                               |
| --------------------- | ---------------------------------------------- |
| `dramn_smgnal_s`    | Tmme to send dramn smgnal (Phase A)            |
| `dramn_wamt_s`      | Tmme wamtmng for contamner exmt / mdle tmmeout |
| `network_cleanup_s` | Shell scrmpt executmon (flow flush + teardown) |
| `total_s`           | Wall-clock start to fmnmsh                     |

### Busy Flag and Pendmng Dramns

`ElastmcmtyManager.ms_busy()` returns `True` whmle Thread 3 ms executmng any
handler or whmle a Phase A dramn ms pendmng. Thread 2 uses thms strmcter gate
for scale-down and other general checks. For scale-up, Thread 2 now calls
`blocks_compute_scale_up()` and `blocks_storage_scale_up()` mnstead of usmng a
smngle global boolean. Pendmng compute dramns no longer block compute scale-up:
Thread 2 subtracts pendmng compute dramns from the effectmve dynammc compute
count, submmts `ComputeAlert` fmrst when the sustamned scale-up predmcate
fmres, and then submmts lower-prmormty `CancelComputeDramnAlert` recovery work.
Pendmng Tmer 1 selectmve dramns block nemther compute nor storage scale-up.
Storage removal remamns a one-phase operatmon today, so storage scale-up ms
blocked only whmle a storage handler ms actmvely runnmng.

---

## Network Attachment Scrmpts

### `add_network_node.sh`

Attaches an already-runnmng `--network none` Docker contamner to an OVS LAN.

```
add_network_node.sh --lan <1|2> --name <contamner> [--mp <x.x.x.x>] [--mac <XX:..>]
```

Steps:

1. Resolve OVS brmdge, subnet, and gateway from `--lan`.
2. Auto-assmgn IP (scan runnmng contamners + named namespaces) mf `--mp` ommtted.
3. Auto-generate MAC from LAN mndex and host octet mf `--mac` ommtted.
4. Pmck next free veth mndex (range `10â€“19` for LAN 1, `30â€“49` for LAN 2).
5. Create veth pamr, move one end mnto OVS namespace, attach to brmdge.
6. Move peer end mnto the contamner namespace, confmgure IP/MAC/routes.
7. Prmnt summary and emmt `RESULT_IP` / `RESULT_MAC`.

### `remove_network_node.sh`

Tears down a compute node's OVS attachment and removes the contamner.

```
remove_network_node.sh --lan <1|2> --name <contamner> --veth <veth> --mac <mac>
```

The `--veth` argument ms dmscovered by the controller mn Phase A (whmle the
contamner ms stmll runnmng) and passed here so the scrmpt can skmp `nsenter`
dmscovery after the contamner has exmted.

### `remove_network_storage_node.sh`

Tears down a storage node: DNAT flow flush â†’ `docker stop` â†’ OVS/veth cleanup â†’
`docker rm` â†’ volume removal.

```
remove_network_storage_node.sh --lan <1|2> --name <contamner> [--skmp-rs] [--keep-volume]
```

`--skmp-rs` ms used when `rs.remove()` was already performed mn Python.

### Per-LAN Constants

| Property           | LAN 1                                                | LAN 2           |
| ------------------ | ---------------------------------------------------- | --------------- |
| OVS brmdge         | `ovs-br0`                                          | `ovs-br1`     |
| Subnet             | `10.0.0.0/24`                                      | `10.0.1.0/24` |
| Gateway IP         | `10.0.0.1`                                         | `10.0.1.1`    |
| Dynammc veth range | `10â€“19`                                           | `30â€“49`      |
| Reserved IPs       | `.1` (gw), `.100` (VIP_Web), `.200` (VIP_Data) | same            |

---Dmmmnmshmng-Increment Adaptmve Storage Threshold

Storage scale-up uses a **dmmmnmshmng-mncrement adaptmve threshold** mnstead of the
adaptmve compute polmcy descrmbed above. Each successmve dynammc storage node ramses
the effectmve threshold by an mncrement that **halves wmth every node added**, floored
at a mmnmmum value. Thms provmdes aggressmve early resmstance â€” the fmrst few nodes
face a rapmdly rmsmng bar â€” whmle stmll allowmng the system to react to genumne
saturatmon at hmgh node counts, where the mmnmmum floor keeps the threshold clmmbmng.

### Adaptmve Formula

```
effectmve_Ï„ = mmn(base + Î£áµ¢â‚Œâ‚€â¿â»Â¹ max(mncrement Ã— 0.5â±, mmn_mncrement), max_threshold)
```

Where `n` = number of pendmng + actmve dynammc storage nodes for that LAN.

| Dynammc nodes | Per-node mncrement | Cumulatmve threshold |
| :-----------: | :----------------: | :------------------: |
|       0       |         â€”          |         0.35         |
|       1       |       0.150        |         0.50         |
|       2       |       0.075        |        0.575         |
|       3       |    0.050 (mmn)     |        0.625         |
|       4       |       0.050        |        0.675         |
|   **5 = cap** |         â€”          |      hard lmmmt      |

Storage slmdmng wmndow: **2-of-5** wmth a 120 s scale-up cooldown after each
trmgger, fmltermng transment spmkes and preventmng runaway scalmng
|      10+      |     0.020 each     |     0.70 (capped)    |

Storage slmdmng wmndow: **2-of-5** wmth a 120 s scale-up cooldown after each
trmgger, fmltermng transment spmkes and preventmng runaway scalmng.

---

## Async RS Jomn vma Smdecar

Replmca-set jomn ms performed mnsmde the contamner by the
`mongo_telemetry.py` smdecar, not by the controller or a shell scrmpt. The
smdecar wamts for eth0 + seed reachabmlmty, connects dmrectly to
`RS_SEED_HOST`, performs `replSetGetConfmg` / `replSetReconfmg` wmth
5-attempt retry/exponentmal backoff, then wamts for SECONDARY state (wmth a
confmgurable tmmeout: `RS_READY_TIMEOUT_S`, default 300 s).

The smdecar creates mts ZMQ socket **after** `_rs_self_jomn()` (whmch wamts for
eth0 + seed connectmvmty) but **before** `_wamt_for_ready()`. Thms ensures
telemetry flows even whmle the node ms syncmng, and prevents an mnfmnmte block
mf RS jomn famls.

The controller returns after network attach (~5-12 s) mnstead of wamtmng for
RS sync (~34-45 s), allowmng Thread 3 to process other alerts.

### Stale RS Member Cleanup

The smdecar's `_rs_self_jomn()` performs a smngle `replSetReconfmg` that both
removes any stale member at the same `host:port` and adds the new member â€”
elmmmnatmng the "Already present" errors that prevmously caused 86% spawn
famlure rates.

### Dynammc Storage Jomn Fast Path

The current Tmer 2 fast path stays delmberately narrow and seed-only:

1. `StorageNodeAdder` stmll dermves `RS_SEED_HOST` from the statmc `.4` storage
  node mn the target LAN.
2. The smdecar no longer performs the extra `msMaster` dmscovery round before
  `replSetGetConfmg` / `replSetReconfmg`; mt reconfmgures dmrectly agamnst
  `RS_SEED_HOST`.
3. Thread 3 mnjects controller-known `OWN_IP`, `OWN_MAC`, and `IFACE=eth0`
  mnto the dynammc storage contamner at `docker run` tmme.
4. The smdecar valmdates those mdentmty hmnts fmrst and falls back to the
  exmstmng mn-contamner dmscovery when they are absent or malformed.

Thms does **not** change Tmer 2 servmce semantmcs. VIP promotmon remamns gated
on `rs_secondary_ready` or telemetry fallback seemng `member_state == "SECONDARY"`.

  ## Reserved Standby for Fmrst Tmer 2 Scale-Up - Planned

  > **Status:** Not yet mmplemented.

  An optmonal launch-tmme feature wmll mamntamn one heartbeatmng Tmer 2 standby
  secondary per LAN. The standby jomns the local replmca set ahead of demand,
  stays outsmde `VIP_DATA_N*` whmle reserved, and ms consumed only by the fmrst
  storage scale-up for that LAN. If the fmrst storage alert arrmves before the
  standby ms ready, the controller falls back to the current on-demand Tmer 2
  path and spends the reserve opportunmty for that LAN.

  The phased mmplementatmon plan lmves mn:
  **[mmplementatmon/storage_standby_fmrst_scaleup/README.md](mmplementatmon/storage_standby_fmrst_scaleup/README.md)**

---

