# ============================================================================
# Top-level orchestration for the edge-storage experiment.
#
# Usage:
#   make setup_network                  # Build the virtual network
#   make create_clients                 # Create test clients on both LANs
#   make teardown_clients               # Remove test clients and stop containers
#   make setup_test_data                # Run all test data seeding steps
#   make setup_test_data DEVICES=200    # Override defaults
# ============================================================================

PYTHON       ?= python3
MONGO_LAN1   ?= mongodb://10.0.0.4:27018/
MONGO_LAN2   ?= mongodb://10.0.1.4:27018/
DEVICES      ?= 100
NODES        ?= 60
CLIENTS      ?= 3
SNAPSHOT_DIR ?= testing/data/workload_snapshot

.PHONY: setup_network \
        create_clients teardown_clients \
        setup_test_data seed_sensor_reports seed_device_registry create_indexes export_snapshot

# ── Network ──────────────────────────────────────────────────────────────────

## Build the virtual network (OVS, replica sets, SDN controllers)
setup_network:
	bash build_network_setup.sh

# ── Test clients ──────────────────────────────────────────────────────────────

## Create $(CLIENTS) namespace-based test clients on each LAN
create_clients:
	bash network/clients/create_test_clients.sh \
	  --lan 1 --count $(CLIENTS) --prefix lan1_client
	bash network/clients/create_test_clients.sh \
	  --lan 2 --count $(CLIENTS) --prefix lan2_client

## Remove test clients from both LANs, then stop all running containers
teardown_clients:
	bash network/clients/remove_test_clients.sh \
	  --lan 1 --prefix lan1_client
	bash network/clients/remove_test_clients.sh \
	  --lan 2 --prefix lan2_client
	bash cleanup.sh -v

# ── Test data ─────────────────────────────────────────────────────────────────

## Run all seeding steps in order
setup_test_data: seed_sensor_reports seed_device_registry create_indexes export_snapshot

## 1 — Seed sensor_reports collection on both LANs
seed_sensor_reports:
	$(PYTHON) testing/sensor_reports.py \
	  --mongo-lan1 $(MONGO_LAN1) \
	  --mongo-lan2 $(MONGO_LAN2) \
	  --devices $(DEVICES)

## 2 — Seed device_registry collection on both LANs
seed_device_registry:
	$(PYTHON) testing/device_registry.py \
	  --mongo-lan1 $(MONGO_LAN1) \
	  --mongo-lan2 $(MONGO_LAN2) \
	  --devices $(DEVICES) \
	  --nodes $(NODES)

## 3 — Create indexes on both replica-set primaries
create_indexes:
	$(PYTHON) testing/create_indexes.py \
	  --mongo-lan1 $(MONGO_LAN1) \
	  --mongo-lan2 $(MONGO_LAN2)

## 4 — Export workload snapshot JSON files for the traffic generator
export_snapshot:
	$(PYTHON) testing/export_workload_snapshot.py \
	  --mongo-lan1 $(MONGO_LAN1) \
	  --mongo-lan2 $(MONGO_LAN2) \
	  --output-dir $(SNAPSHOT_DIR)
