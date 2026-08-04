# VM Provisioning Runbook

Reproducible procedure to stand up an experiment VM for this platform. It
mirrors the golden host `cloud-vm`. Use this when adding a new VM or rebuilding
one.

## VM Inventory

| RQ | VM host alias | IP | User | Spec |
| --- | --- | --- | --- | --- |
| RQ1 | `cloud-vm` | `204.168.202.35` | `testop` | Ubuntu 22.04.5 LTS, 4 vCPU, 8 GB, 150 GB |
| RQ2 | `cloud-vm-rq2` | `62.238.107.159` | `testop` | Ubuntu 22.04.5 LTS, 4 vCPU, 8 GB, 150 GB |
| RQ3 | `cloud-vm-rq3` | `62.238.107.141` | `testop` | Ubuntu 22.04.5 LTS, 4 vCPU, 8 GB, 150 GB |

Local SSH config aliases (`~/.ssh/config`) for the RQ2/RQ3 hosts point at the
`edge-testop` key:

```ini
Host cloud-vm-rq2
  HostName 62.238.107.159
  User testop
  IdentityFile ~/.ssh/edge-testop
  IdentitiesOnly yes
  ForwardAgent no

Host cloud-vm-rq3
  HostName 62.238.107.141
  User testop
  IdentityFile ~/.ssh/edge-testop
  IdentitiesOnly yes
  ForwardAgent no
```

## Preconditions

- Fresh Ubuntu 22.04.5 LTS VM, reachable as `root` with the `edge-testop` public
  key in `/root/.ssh/authorized_keys`.
- Outbound internet (apt + pip + Docker Hub) for provisioning and image builds.
- No swap is configured on the VMs (same as `cloud-vm`); 8 GB RAM is sufficient
  for the full stack (measured base footprint ~1.1 GiB; RQ3 peak ~7 GiB).

## Phase 1 — OS Provisioning (as root)

```bash
apt-get update
apt-get install -y docker.io make jq python3-pip rsync curl git
systemctl enable --now docker
useradd -m -s /bin/bash testop
# seed testop's authorized_keys from root's (edge-testop pubkey)
install -d -m 700 -o testop -g testop /home/testop/.ssh
cp /root/.ssh/authorized_keys /home/testop/.ssh/authorized_keys
chown testop:testop /home/testop/.ssh/authorized_keys && chmod 600 /home/testop/.ssh/authorized_keys
usermod -aG docker testop
echo 'testop ALL=(ALL) NOPASSWD: ALL' > /etc/sudoers.d/testop && chmod 440 /etc/sudoers.d/testop
echo 'net.ipv4.ip_forward=1' > /etc/sysctl.d/99-edge.conf && sysctl -w net.ipv4.ip_forward=1
# system-wide python for ROOT (all experiment python runs as root via sudo -n make)
pip3 install pymongo==4.17.0 pyzmq==27.1.0 aiohttp
# testop user-site (mirrors cloud-vm layout; analysis libs)
sudo -u testop -H python3 -m pip install --user pandas==2.3.3 numpy==2.2.6 matplotlib==3.10.9
```

Notes:

- The pinned `pymongo`/`pyzmq`/`pandas`/`numpy`/`matplotlib` versions match
  `cloud-vm`. `aiohttp` is required by the open-loop driver (`TRAFFIC_DRIVER_MODE=open_loop`).
- Everything in `run_experiment.sh` executes under **root** (`sudo -n make ...`),
  so `pymongo`/`aiohttp`/`pyzmq` MUST be system-wide, not user-site.

Gate before switching the SSH alias to `testop`:

```bash
ssh root@<ip> "sudo -n true && docker info --format {{.ServerVersion}} \
  && sudo -n python3 -c 'import pymongo,aiohttp,zmq'"
ssh testop@<ip> "sudo -n true && python3 -c 'import pandas,numpy,matplotlib'"
```

## Phase 2 — Repo Deploy (as testop)

The local working tree is the source of truth (it carries uncommitted fixes), so
`git pull` alone is NOT sufficient. Deploy via clone + source overlay:

```bash
# 1) clone (gets .git so the runner's git-diff verification works)
ssh <HOST> "git clone https://github.com/poioe20p/efficient-storage-in-edge-scenarios.git ~/efficient-storage-in-edge-scenarios"

# 2) overlay the local source/ working tree (byte-identical), excluding run data
#    On Windows: tar locally to a file, scp, extract (no local rsync).
tar -C <repo> -cf source.tar --exclude='*/testing/metrics*' --exclude='*/__pycache__/*' --exclude='*.pyc' source
scp source.tar <HOST>:/tmp/source.tar
ssh <HOST> "tar -xf /tmp/source.tar -C ~/efficient-storage-in-edge-scenarios"

# 3) verify byte-identity of a critical file
#    (local) Get-FileHash source/docker/edge_server/source/edge_server_config.py -Algorithm MD5
ssh <HOST> "md5sum ~/efficient-storage-in-edge-scenarios/source/docker/edge_server/source/edge_server_config.py"
```

RQ2-only: the campaign env overrides live outside the repo (`rq2_env/` at repo
root). Copy the doc-hosted originals:

```bash
mkdir -p ~/efficient-storage-in-edge-scenarios/rq2_env
scp <repo>/docs/operation/testing/experiment/v2/rq2/env/*.env <HOST>:~/efficient-storage-in-edge-scenarios/rq2_env/
```

## Phase 3 — Build Docker Images (as testop)

```bash
ssh <HOST> "cd ~/efficient-storage-in-edge-scenarios && sudo -n bash source/scripts/build_images.sh"
# expect: edge_server, edge_storage_server, edge_selective_storage,
#         osken-controller, local_state_server, ubuntu-nat-router, ovs-container
```

## Phase 4 — Smoke Verification (as testop)

```bash
ssh <HOST> "cd ~/efficient-storage-in-edge-scenarios && sudo -n make -C source/scripts setup_network create_clients \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env"
ssh <HOST> "cd ~/efficient-storage-in-edge-scenarios && sudo -n make -C source/scripts driver_selftest"
ssh <HOST> "cd ~/efficient-storage-in-edge-scenarios && nohup sudo -n make -C source/scripts setup_test_data run_experiment \
  RUN_LABEL=smoke PHASES_CONFIG=testing/phases_override/phases_mini.json CLIENTS=2 CONTENT_ITEMS=30 USERS=20 DATA_SEED=42 \
  TRAFFIC_DRIVER_MODE=open_loop INFLIGHT_WINDOW=256 DRAIN_S=5 \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  > /tmp/smoke.log 2>&1 < /dev/null &"
# local: python3 tools/watch_run.py --host <HOST> --run-label smoke
ssh <HOST> "cd ~/efficient-storage-in-edge-scenarios && sudo -n make -C source/scripts teardown_clients"
```

Verify the run folder contains a non-empty `client_requests.csv` and
`resource_stats.csv`.

## Known Runtime Items (tracked separately)

- `traffic_generator.py` declares `--config` as `required=True` but the
  open-loop supervisor spawns workers without it, so real open-loop workers exit
  `rc=2` (the `driver_selftest` masks this by calling `_worker_main` in-process).
  Fix: make `--config` conditionally required (skip when `--worker`). Tracked for
  the runner agents to resolve before RQ1/RQ2 open-loop campaigns.
