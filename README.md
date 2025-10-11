# efficient-storage-in-edge-scenarios

You can use a Linux Ubuntu VirtualBox Machine (VM).

In that VM install docker, and net-tools.

Copy the current directory to /home/user/containers

cd ~/containers

Build openvswitch image with the name ovs-container:
./build_openvswitch

Build ubuntu image with the name ubuntu-tools:
./build_ubuntu

Launch testbed:
sudo ./test_ovs_containers

Enter inside container1 via bash:
-u 0: to run as root user
-it: interactive terminal
sudo docker exec -u 0 -it container1 bash

Test this tesbed, inside container1, using ping commands.
ping -c1 10.0.0.3
ping www.google.pt
