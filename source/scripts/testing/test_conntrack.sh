#!/bin/bash
set -e

CLIENT_NS=lan1_client_1
CLIENT_IP=$(sudo ip netns exec $CLIENT_NS ip addr show eth0 | grep 'inet ' | awk '{print $2}' | cut -d/ -f1)
CLIENT_MAC=$(sudo ip netns exec $CLIENT_NS cat /sys/class/net/eth0/address)
CLIENT_PORT=1

# Use static storage n1: 10.0.0.4, MAC 00:00:00:00:00:04, port 2
STORAGE_IP=10.0.0.4
STORAGE_MAC=00:00:00:00:00:04
STORAGE_PORT=2
VIP_IP=10.0.0.254
VIP_MAC=aa:bb:cc:dd:ee:02

echo "Client: IP=$CLIENT_IP MAC=$CLIENT_MAC port=$CLIENT_PORT"
echo "Storage: IP=$STORAGE_IP MAC=$STORAGE_MAC port=$STORAGE_PORT"
echo "VIP: IP=$VIP_IP MAC=$VIP_MAC"

echo ""
echo "=== 1. Clearing old VIP flows ==="
sudo docker exec ovs ovs-ofctl del-flows ovs-br0 "tcp,nw_dst=10.0.0.254" 2>&1 || true

echo "=== 2. Adding forward flow ==="
sudo docker exec ovs ovs-ofctl add-flow ovs-br0 "priority=200,tcp,dl_dst=$VIP_MAC,nw_dst=$VIP_IP,tp_dst=27018,actions=ct(commit,zone=1,nat(dst=$STORAGE_IP)),mod_dl_dst:$STORAGE_MAC,output:$STORAGE_PORT"
echo "Forward rule added"

echo "=== 3. Adding reply flow ==="
sudo docker exec ovs ovs-ofctl add-flow ovs-br0 "priority=200,ct_state=+est+trk,ct_zone=1,tcp,dl_dst=$CLIENT_MAC,nw_dst=$CLIENT_IP,actions=mod_dl_src:$VIP_MAC,output:$CLIENT_PORT"
echo "Reply rule added"

echo ""
echo "=== 4. Testing with curl ==="
HTTP_CODE=$(sudo ip netns exec $CLIENT_NS curl -s -o /dev/null -w '%{http_code}' --max-time 5 'http://10.0.0.254:27018/' 2>&1)
echo "HTTP code: $HTTP_CODE"

echo ""
echo "=== 5. Flow stats after test ==="
sudo docker exec ovs ovs-ofctl dump-flows ovs-br0 | grep -E 'ct_zone=1|zone=1' | head -10

echo ""
echo "=== 6. Conntrack entries ==="
sudo docker exec ovs ovs-appctl dpctl/dump-conntrack 2>&1 | grep 'zone=1' | head -5

echo ""
echo "=== 7. Checking if storage is reachable directly ==="
sudo ip netns exec $CLIENT_NS curl -s -o /dev/null -w '%{http_code}' --max-time 5 'http://10.0.0.4:27018/' 2>&1 || echo "direct failed"

echo ""
echo "=== 8. Checking if backend responds to ping ==="
sudo ip netns exec $CLIENT_NS ping -c 2 -W 1 10.0.0.4 2>&1 || echo "ping failed"

echo ""
echo "Done."
