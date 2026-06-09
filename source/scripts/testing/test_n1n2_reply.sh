#!/bin/bash
CLIENT_MAC=00:00:00:00:01:38
CLIENT_IP=10.0.0.56
CLIENT_PORT=6
VIP_N1_MAC=aa:bb:cc:dd:ee:02
VIP_N2_MAC=aa:bb:cc:dd:ee:03
VIP_N1_IP=10.0.0.254

echo '=== Clean existing reply rules ==='
sudo docker exec ovs ovs-ofctl del-flows ovs-br0 "tcp,dl_dst=$CLIENT_MAC,tcp_src=27018" 2>&1 || true

echo '=== Add n1 reply rule (10.0.0.0/24 backend subnet) ==='
sudo docker exec ovs ovs-ofctl add-flow ovs-br0 "priority=200,tcp,dl_dst=$CLIENT_MAC,nw_src=10.0.0.0/24,nw_dst=$CLIENT_IP,tcp_src=27018,actions=ct(zone=1,nat),mod_dl_src:$VIP_N1_MAC,output:$CLIENT_PORT"

echo '=== Add n2 reply rule (10.0.1.0/24 backend subnet) ==='
sudo docker exec ovs ovs-ofctl add-flow ovs-br0 "priority=200,tcp,dl_dst=$CLIENT_MAC,nw_src=10.0.1.0/24,nw_dst=$CLIENT_IP,tcp_src=27018,actions=ct(zone=2,nat),mod_dl_src:$VIP_N2_MAC,output:$CLIENT_PORT"

echo '=== Verify both rules coexist ==='
sudo docker exec ovs ovs-ofctl dump-flows ovs-br0 | grep "$CLIENT_MAC.*tcp_src=27018"

echo '=== Add forward rule for n1 ==='
sudo docker exec ovs ovs-ofctl add-flow ovs-br0 "priority=200,tcp,dl_src=$CLIENT_MAC,dl_dst=$VIP_N1_MAC,nw_src=$CLIENT_IP,nw_dst=$VIP_N1_IP,tp_dst=27018,actions=ct(commit,zone=1,nat(dst=10.0.0.4)),mod_dl_dst:00:00:00:00:00:04,output:2"

echo '=== Test n1 VIP curl ==='
sudo ip netns exec lan1_client_1 curl -s --max-time 5 http://10.0.0.254:27018/
echo ''

echo '=== Both reply rules stats ==='
sudo docker exec ovs ovs-ofctl dump-flows ovs-br0 | grep "$CLIENT_MAC.*tcp_src=27018"
