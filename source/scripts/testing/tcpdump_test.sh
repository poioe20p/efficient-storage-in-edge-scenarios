#!/bin/bash
echo '=== Find veth pair for port 2 ==='
PORT2_IF=$(ip link | grep -B1 'veth112' | head -1 | awk -F: '{print $2}' | tr -d ' ')
echo "Port 2 host interface: $PORT2_IF"

if [ -z "$PORT2_IF" ]; then
    echo "Could not find veth interface for port 2"
    exit 1
fi

echo '=== Capture on host veth while testing ==='
sudo timeout 6 tcpdump -i "$PORT2_IF" -n port 27018 -c 20 &
TCPDUMP_PID=$!
sleep 1

sudo ip netns exec lan1_client_1 curl -s --max-time 5 http://10.0.0.254:27018/
echo ""

wait $TCPDUMP_PID 2>/dev/null
sudo pkill tcpdump 2>/dev/null || true
echo '=== Capture complete ==='
