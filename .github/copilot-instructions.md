# Copilot Instructions

## Project Snapshot
- This repo orchestrates a lab where OVS switches, Ubuntu hosts, NAT router, and sharded MongoDB run inside Docker (see [scripts](scripts) + [docker](docker)).
- The SDN controller lives in [sdn_controller](sdn_controller); it hosts OS-Ken apps that learn L2 paths and log events into MongoDB.
- Network and procedure references live under [docs/network](docs/network) and [docs/setups](docs/setups); keep scripts consistent with those diagrams and notes.

## Runtime Environment (Ubuntu VM)
- Treat the Ubuntu virtual machine as the execution environment for this project: Docker containers, bash automation scripts, the SDN controller (Python/OS-Ken), and the overall network lab are designed to run (and do run) inside the Ubuntu VM.
- Windows is used primarily for authoring/editing; avoid changes that assume native Windows networking/iptables semantics.

## OS & Line Endings
- Authoring happens on Windows, but bash scripts and controller code run inside an Ubuntu VM; keep all repo files (especially scripts/*.sh and docker/*) saved with LF to avoid bash syntax errors and broken shebangs.
- In VS Code force `LF` in the status bar before saving; avoid editors that auto-convert to CRLF.
- If Git warns about CRLF, set `core.autocrlf=input` (or add a `.gitattributes` entry for `*.sh text eol=lf`) so line endings stay Unix-style when committed.

## Required Config
- The loader in [config.py](config.py) fails fast if any of the five vars are missing.
- `MongoConfig.dpid_to_shard_map` accepts `MONGO_DPID_ZONE_MAP="1=rs_net1,2=rs_net2"`; omit it to auto round-robin dpids across `rs_net{n}`.
- OS-Ken containers expect LAN reachability to MongoDB (`10.0.0.4/10.0.1.4`); keep host routes (`10.0.x.0/24 via 192.168.100.2`) aligned with [docs/network/network_setup.md](docs/network/network_setup.md).

## Build & Run Workflow
- Build all custom images first with `./scripts/build_images.sh`; it mirrors Dockerfiles from [docker/*](docker).
- Deploy the full topology via `./scripts/build_setup.sh`; it cleans prior runs, enforces iptables FORWARD ACCEPT, provisions veth pairs, boots config server, runs [scripts/build_network_1.sh](scripts/build_network_1.sh) and [scripts/build_network_2.sh](scripts/build_network_2.sh), and initializes replica sets.
- Use `./scripts/test_connectivity.sh` and `./scripts/test_db.sh` once containers are up; they assume the IP plan documented in [docs/network/network_setup.md](docs/network/network_setup.md).
- Reset everything with `./scripts/cleanup.sh --reset` when you need a fresh state; the setup scripts rely on starting from clean namespaces.

## Controller Architecture
- [sdn_controller/osken_learn_and_log.py](sdn_controller/osken_learn_and_log.py) implements `KenLearnAndLog`, an OpenFlow 1.3 learning-switch that installs a table-miss flow, learns `src→port`, and mirrors packets to MongoDB.
- Zone assignment ties datapath IDs to shard ranges using `_zone_order` (`rs_net1`, `rs_net2`) and `_zone_size` chunks; extend these lists if you add switches or shards.
- Packet logs are prepared in `_queue_event_for_zone` and pushed asynchronously with Eventlet to avoid blocking dataplane reactions; reuse that pattern for any new persistence tasks.
- Toggle `enable_reactive_learning` when you need pure hub behavior (e.g., debugging new topologies) without editing flow logic.

## Data + Mongo Layer
- Mongo endpoints and URIs are centralized in [sdn_controller/models/mongodb_host.py](sdn_controller/models/mongodb_host.py); prefer `MongodbRouter.get_simple_connection_string(add_app=True)` over inlined URIs.
- Event payload schema is defined in [sdn_controller/repositories/models/event.py](sdn_controller/repositories/models/event.py); extend the dataclass before changing repository writes.
- [sdn_controller/repositories/repositories/event.py](sdn_controller/repositories/repositories/event.py) replaces documents by `_id==dpid` to keep shard keys stable; any new query must include `dpid` so `mongos` routes correctly.
- When sharding, chunk ranges follow the integer `dpid` space set in the controller; keep `_zone_size` large enough to avoid exhausting zones mid-run.

## Network Automation Insights
- [docs/network/network_setup.md](docs/network/network_setup.md) and [docs/setups/sdn_controller_and_mongodb.md](docs/setups/sdn_controller_and_mongodb.md) explain every veth, bridge, and NAT rule; mirror those comments when editing shell scripts so future maintainers can trace packet paths.
- `build_setup.sh` depends on host interface `enp0s3` owning `192.168.100.4/24`; adjust both the script and documentation before renaming host NICs.
- NAT/DNAT expectations (e.g., router exposing shards on 27018/27118) are baked into Mongo router bootstrap; keep iptables changes in sync with `sh.addShard` targets documented in [docs/setups/mongodb_sharding_and_sdn_topology.md](docs/setups/mongodb_sharding_and_sdn_topology.md).

## Troubleshooting & Tips
- Watch `docker logs ovs` and `docker logs ryu` to verify controller attachment before debugging flows; the system assumes controllers run on host networking.
- `ovs-ofctl dump-flows ovs-br0` should show a `priority=0` controller rule plus `priority=10` learned entries; absence of the latter usually means Mongo logging failed early and `enable_reactive_learning` got disabled.
- Mongo issues typically surface as missing `.env-mongo`, wrong bind IPs, or failed replica-set init; scripts already check for `"ok":1`—keep new automation steps validating outputs before proceeding.
- Wireshark captures should target `veth5` with `ip.addr==10.0.0.4 && tcp.port==27017` as documented in [README.md](README.md) when crafting OpenFlow policies around Mongo traffic.
