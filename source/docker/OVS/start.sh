#!/bin/bash

# Create OVS database if it doesn't exist
if [ ! -f /etc/openvswitch/conf.db ]; then
    ovsdb-tool create /etc/openvswitch/conf.db /usr/share/openvswitch/vswitch.ovsschema
fi

# Start ovsdb-server
ovsdb-server \
    --remote=punix:/var/run/openvswitch/db.sock \
    --remote=db:Open_vSwitch,Open_vSwitch,manager_options \
    --pidfile --detach

# Initialize OVS
ovs-vsctl --no-wait init

# Start ovs-vswitchd
ovs-vswitchd --pidfile --detach

# Keep container running
tail -f /dev/null
