# Ryu CLI Quick Reference

- `ryu-manager --help` – list global options and available app loading flags.
- `ryu-manager ryu.app.simple_switch_13` – start the OpenFlow 1.3 learning switch sample.
- `ryu-manager --verbose ryu_controller.ryu_learn_and_log` – launch the custom controller with extra logging (workspace on `PYTHONPATH`).
- `ryu-manager --observe-links ryu.topology.switches` – enable link-discovery and expose topology events.
- `ryu-manager --app-list` – print entry-point names for apps exposed via setuptools.
- `ryu-manager --log-config-file etc/ryu/ryu.conf ryu.app.ofctl_rest` – run the RESTful OpenFlow controller with custom logging config.
- `ryu-manager --cpuset 0,1 ryu.app.simple_monitor_13` – pin controller threads to selected CPU cores.
- `ryu-manager --ryu-ctl ryu.app.qos_rest_v1` – expose the built-in control socket for runtime app commands.
- `ryu-client --help` – inspect the RPC client used with the control socket (`--ryu-ctl`).
- `ryu-client --ryu-ctl tcp:127.0.0.1:6634 rest-controller status` – query a running controller using the control interface.
