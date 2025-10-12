# efficient-storage-in-edge-scenarios

## Instructions

> All paths below are relative to the repository root (`efficient-storage-in-edge-scenarios`). Run the commands from that directory unless noted otherwise.

### 1. Prepare MongoDB credentials (`.env-mongo`)

- **Directory:** project root
- **Command:** Create or edit `.env-mongo` following the template in [`docs/setups/mongodb.md`](docs/setups/mongodb.md).
- **What it does:** Supplies the MongoDB entrypoint with admin/app credentials during initialization.
- **Result:** Subsequent scripts automatically load the variables and the database starts with authentication enabled (or without auth if the admin pair is omitted).

### 2. Build Docker images (`scripts/build_images.sh`)

- **Directory:** project root
- **Command:**

  ```bash
  ./scripts/build_images.sh
  ```

- **What it does:** Builds all project images (`ovs-container`, `ubuntu-nat-router`, `ubuntu-host-1`, `ubuntu-host-2`, `ubuntu-mongodb`) using the Dockerfiles in `docker/`.
- **Result:** `docker images` lists the refreshed `:latest` tags for each component, ready to be launched.

### 3. Provision the topology (`scripts/build_setup.sh`)

- **Directory:** project root
- **Command:**

  ```bash
  ./scripts/build_setup.sh
  ```

- **What it does:** Cleans previous runs, starts the Open vSwitch and host containers, wires veth pairs, launches the NAT router and MongoDB (loading `.env-mongo`), and connects everything to the Ryu controller.
- **Result:** Containers `ovs`, `container1`, `container2`, `nat-router`, `mongodb`, and `ryu` are running with the virtual network configured and `mongodb-data` volume mounted.

### 4. Run integration checks (`scripts/test_db.sh`)

- **Directory:** project root
- **Command:**

  ```bash
  ./scripts/test_db.sh
  ```

- **What it does:** Verifies MongoDB authentication and basic CRUD operations from the Ubuntu host containers.
- **Result:** Prints success messages for insert/read tests if the deployment is healthy.

### 5. Run connectivity checks (`scripts/test_connectivity.sh`)

- **Directory:** project root
- **Command:**

  ```bash
  ./scripts/test_connectivity.sh
  ```

- **What it does:** Pings between containers and verifies routing across the virtual topology (hosts ⇄ router ⇄ MongoDB ⇄ NAT).
- **Result:** Displays successful ping summaries for each hop; any failure indicates a networking issue to investigate.

### 6. Tear down or reset (`scripts/cleanup.sh`)

- **Directory:** project root
- **Command:**

  ```bash
  ./scripts/cleanup.sh --reset
  ```

- **What it does:** Removes network artifacts, all containers, and the `mongodb`/`mongodb-data` volumes. Use other flags (`--network`, `--docker`, `--images`, `--volumes`) for targeted cleanup.
- **Result:** Host returns to a clean state with docker resources and custom networks removed.
