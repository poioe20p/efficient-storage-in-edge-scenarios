# SDN Controller + MongoDB Notes

## Runtime Flow (LearnAndLog)

- **App boot**: `eventlet.monkey_patch()` runs before any other imports, and `EVENTLET_NO_GREENDNS=yes` is set to avoid PyMongo’s greendns bug. Core state (`mac_to_port`, Mongo placeholders) is initialised, but no database connection is attempted yet.
- **Switch join (`EventOFPSwitchFeatures`)**: `switch_features_handler` installs the OpenFlow 1.3 table-miss with `priority=0` and `OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)`, forwarding unknown traffic to `OFPP_CONTROLLER` with `max_len=OFPCML_NO_BUFFER`. After the flow is committed the app spawns a background Eventlet green thread that is responsible for bringing MongoDB online.
- **Deferred Mongo connector**: `_mongo_connector` loads `.env-mongo`, creates `MongoClient(self.mongo_config.app_uri(), connect=False, serverSelectionTimeoutMS=2000)`, and repeatedly issues `client.admin.command("ping")` every five seconds until it succeeds. When the ping returns `ok:1`, the thread saves `self.mongo` / `self.db` and logs “MongoDB connection established”. Until that flag flips, packet processing continues but logging is skipped.
- **Packet-in (`EventOFPPacketIn`)**: the handler extracts `in_port`, learns the source MAC, determines the output port (known vs flood), pushes a unicast flow via `add_flow` (match on `in_port`, `eth_src`, `eth_dst`), and emits an `OFPPacketOut`. If `self.db` is ready, it inserts a document into `events`; otherwise it does nothing and the dataplane still converges.
- **Flow install (`add_flow`)**: matches use the OpenFlow 1.3 field names (`eth_src`, `eth_dst`) and actions are wrapped in an instruction list. Idle/hard timeouts remain zero and `priority=10` keeps learned flows above the table-miss.

## Interaction With `build_setup.sh`

- The script wires veth pairs into the `ovs` container, adds them to `ovs-br0`, and assigns addresses in `10.0.0.0/24` to the hosts and MongoDB (`10.0.0.4`).
- The controller container (`osken`, built from the `osken-controller` image) runs with host networking; a static route on the host (`10.0.0.0/24 via 192.168.100.2`) gives it reachability to the lab subnet and to MongoDB.
- `ovs-vsctl set-controller ovs-br0 tcp:127.0.0.1:6633` attaches OVS to the controller. With the deferred connector in place it’s now safe to point the bridge as soon as the LAN wiring is complete—the controller suppresses Mongo logging until the database answers the ping.

### Recommended Startup Sequence

1. Run `./scripts/build_setup.sh` from the repository root. (If you prefer to validate the LAN first, you can still comment out the `set-controller` line temporarily.)
2. Confirm MongoDB is reachable from the host or one of the containers (`nsenter ... mongo --eval 'db.runCommand({ping:1})'` or `nc -z 10.0.0.4 27017`). The controller’s `_mongo_connector` will keep retrying every five seconds until this works.
3. Watch `docker logs osken` for the “MongoDB connection established” line. Once it appears, packet-in events will start persisting automatically. If you deferred the controller attachment, run `docker exec ovs ovs-vsctl set-controller ovs-br0 tcp:127.0.0.1:6633` at this stage.

## MongoDB Logging Notes

- `.env-mongo` must set `MONGO_APP_HOST=10.0.0.4` and `MONGO_APP_PORT=27017` so the controller connects to the LAN address instead of `localhost`.
- Logged documents currently capture `{type="packet_in", dpid, src, dst, in_port, ts}`. Adjust the payload in `osken_learn_and_log.py` if additional metadata is required.
- If Mongo goes offline mid-run, the connector thread reports failures (“MongoDB connection attempt failed …”) and keeps retrying without blocking the dataplane. The first successful ping re-enables inserts.

## Troubleshooting Checklist

- `docker logs osken` should show the table-miss installation, learning-table updates (`mac_to_port[...]`), periodic Mongo connection attempts, and finally “MongoDB connection established”.
- `ovs-ofctl dump-flows ovs-br0` should list one `priority=0` controller rule and learned `priority=10` unicast rules for each MAC pair.
- If packet-ins keep flooding, verify that the controller container still has reachability to `10.0.0.4` and that `PYTHONPATH=/workspace` is set so `MongoConfig` can locate `.env-mongo`.
- If the Mongo connector thread never succeeds, double-check credentials in `.env-mongo`, ensure the database is bound to the LAN address, and confirm no firewall is blocking port `27017` inside the topology.
