# `ovs-ofctl` Quick Reference

`ovs-ofctl` is the standard CLI for interrogating and programming OpenFlow datapaths. The sections below highlight the commands most relevant to this repository's OS-Ken controller.

## Switch & Table Introspection
- `show SWITCH` – summarize OpenFlow configuration for a bridge.
- `dump-desc SWITCH` – report datapath hardware/software description.
- `dump-tables SWITCH` – inspect per-table packet/byte counters.
- `dump-table-features SWITCH` / `dump-table-desc SWITCH` – detailed table metadata (OF 1.3+/1.4+).
- `mod-port SWITCH IFACE ACT` – change a port's behavior.
- `mod-table SWITCH MOD` – adjust table behavior (`controller`, `continue`, `drop`, `evict`, `vacancy:*`).
- `get-frags SWITCH` / `set-frags SWITCH MODE` – view or set fragment handling (`normal`, `drop`, `reassemble`, `nx-match`).
- `dump-ports SWITCH [PORT]` – print live port statistics.
- `dump-ports-desc SWITCH [PORT]` – print port descriptions (names, speeds, state).

## Flow Lifecycle
- `dump-flows SWITCH [FLOW]` – print flow entries or filtered matches.
- `dump-aggregate SWITCH [FLOW]` – aggregate packet/byte counts for matching flows.
- `add-flow SWITCH FLOW` / `add-flows SWITCH FILE` – install single or bulk rules.
- `mod-flows SWITCH FLOW` – update actions for matching flows.
- `del-flows SWITCH [FLOW]` – delete matching entries (omit `FLOW` to clear tables).
- `replace-flows SWITCH FILE` – replace current flows atomically with `FILE` contents.
- `diff-flows SOURCE1 SOURCE2` – compare two flow dumps.

## Packet Handling & Monitoring
- `packet-out SWITCH IN_PORT ACTIONS PACKET...` – execute actions on crafted packets.
- `monitor SWITCH [MISSLEN] [invalid_ttl] [watch:...]` – stream packets received from the switch.
- `snoop SWITCH` – observe controller-switch OpenFlow traffic.

## Groups, Queues, and Meters
- `add-group`, `add-groups FILE`, `mod-group`, `del-groups`, `dump-groups`, `dump-group-stats`, `dump-group-features`, `insert-buckets`, `remove-buckets` – manage group entries and buckets.
- `queue-get-config SWITCH [PORT]` / `queue-stats SWITCH [PORT [QUEUE]]` – inspect queue configuration and counters.
- `add-meter`, `mod-meter`, `del-meters`, `dump-meters`, `meter-stats`, `meter-features` – manage OpenFlow meters.
- `add-tlv-map`, `del-tlv-map`, `dump-tlv-map` – configure experimenter TLV mappings.
- `dump-ipfix-bridge SWITCH` / `dump-ipfix-flow SWITCH` – inspect IPFIX exporter state.
- `ct-flush-zone SWITCH ZONE` – flush conntrack entries in a zone.

## Reachability & Parsing Utilities
- `probe TARGET` – check whether a datapath or controller endpoint responds.
- `ping TARGET [N]` – measure latency using N-byte OpenFlow echo requests.
- `benchmark TARGET N COUNT` – estimate throughput using repeated echoes.
- `ofp-parse FILE` – decode OpenFlow messages from text dumps.
- `ofp-parse-pcap PCAP` – decode OpenFlow conversations captured in PCAP files.

## Connection Methods & PKI
- `tcp:HOST[:PORT]` – default OpenFlow transport (6653 by default; 6633 legacy).
- `ssl:HOST[:PORT]` – TLS transport; requires `--private-key`, `--certificate`, and `--ca-cert`.
- `unix:FILE` – UNIX domain socket.

## Global Options
- `-O, --protocols` – restrict allowed OpenFlow versions (use `-O OpenFlow13` here).
- `-v/--verbose`, `--log-file`, `--syslog-*` – control logging destinations/verbosity.
- `--strict` – enforce exact-match semantics for flow commands.
- `-F, --flow-format` / `-P, --packet-in-format` – force specific parsing/printing formats.
- `--names` / `--no-names` – toggle port name resolution in command output.
- `--read-only`, `--readd`, `-t/--timeout`, `--timestamp`, `--color`, `--unixctl`, `-h/--help`, `-V/--version` – additional runtime controls.

## Project Example: Inspecting Proactive Flows
After `scripts/build_setup.sh` completes, the `ovs` container hosts both Open vSwitch bridges (`ovs-br0`, `ovs-br1`) controlled by `Topology_proactive`. Because the controller programs OpenFlow 1.3 rules, include `-O OpenFlow13` whenever you inspect or modify flows.

```bash
# Dump every rule currently installed on ovs-br0.
docker exec ovs \
	ovs-ofctl -O OpenFlow13 dump-flows ovs-br0

# Focus on a specific host-to-host flow (adjust MACs as needed).
docker exec ovs \
	ovs-ofctl -O OpenFlow13 dump-flows ovs-br0 \
	"dl_src=00:00:00:00:00:01,dl_dst=00:00:00:00:00:02"
```

Suggested workflow:
1. Run `build_setup.sh` to launch MongoDB, the OS-Ken controller (`osken` container), and both bridges.
2. Monitor `docker logs -f osken` until `Topology_proactive` announces topology updates and proactive installs.
3. Use the commands above to verify each switch carries the bidirectional priority-5 rules plus the fallback ARP flood rule (priority 1). If entries are missing, rerun the proactive installer or compare bridges with `ovs-ofctl diff-flows ovs-br0 ovs-br1` to spot inconsistencies.
