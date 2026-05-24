# ============================================================================
# Top-level orchestration for the edge-storage experiment.
#
# Usage:
#   make setup_network                  # Build the virtual network
#   make create_clients                 # Create test clients on both LANs
#   make teardown_clients               # Remove test clients and stop containers
#   make setup_test_data                # Run all test data seeding steps
#   make setup_test_data DEVICES=200    # Override defaults
#   make cleanup_metrics                # Remove metrics run folders
# ============================================================================

PYTHON       ?= python3
MONGO_LAN1   ?= mongodb://10.0.0.4:27018/
MONGO_LAN2   ?= mongodb://10.0.1.4:27018/
DEVICES      ?= 100
NODES        ?= 45
CLIENTS      ?= 3
SNAPSHOT_DIR ?= testing/data/workload_snapshot
SKIP_CLIENTS  ?= 1
SKIP_SEED     ?= 1
SKIP_SNAPSHOT ?= 1
DRY_RUN       ?=
RUN_LABEL     ?=
PHASES_CONFIG ?=
FAULT_PLAN    ?=


.PHONY: setup_network \
        create_clients teardown_clients \
        setup_test_data seed_sensor_reports seed_device_registry create_indexes export_snapshot \
	run_experiment cleanup_metrics \
	install_commit_msg_hook uninstall_commit_msg_hook preview_commit_msg

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

# ── Experiment ────────────────────────────────────────────────────────────────

## Remove all metrics run folders under testing/metrics.
cleanup_metrics:
	@set -eu; \
	metrics_dir="$(abspath testing/metrics)"; \
	find "$$metrics_dir" -mindepth 1 -maxdepth 1 -type d | while IFS= read -r run_dir; do \
		case "$$run_dir" in \
			"$$metrics_dir"/*) \
				printf 'Removing %s\n' "$$run_dir"; \
				rm -rf -- "$$run_dir"; \
				;; \
			*) \
				echo "Refusing unexpected path: $$run_dir" >&2; \
				exit 1; \
				;; \
		esac; \
	done

## Run the full 4-phase experiment (traffic generator + resource stats collector).
## Optional flags (set to any non-empty value to enable):
##   make run_experiment SKIP_CLIENTS=1   # namespaces already created
##   make run_experiment SKIP_SEED=1      # data already seeded
##   make run_experiment SKIP_SNAPSHOT=1  # snapshot already exported
##   make run_experiment DRY_RUN=1        # no real HTTP requests
##   make run_experiment RUN_LABEL=c0     # metrics folder becomes <timestamp>_c0
##   make run_experiment PHASES_CONFIG=testing/phases_custom.json
##   make run_experiment FAULT_PLAN=testing/fault_plan.json
run_experiment:
	sudo bash testing/run_experiment.sh \
	  $(if $(strip $(RUN_LABEL)),--run-label "$(strip $(RUN_LABEL))") \
	  --snapshot-dir $(abspath $(SNAPSHOT_DIR)) \
	  $(if $(strip $(PHASES_CONFIG)),--phases-config "$(strip $(PHASES_CONFIG))") \
	  $(if $(strip $(FAULT_PLAN)),--fault-plan "$(strip $(FAULT_PLAN))") \
	  $(if $(filter-out 0 false,$(SKIP_CLIENTS)),--skip-clients) \
	  $(if $(filter-out 0 false,$(SKIP_SEED)),--skip-seed) \
	  $(if $(filter-out 0 false,$(SKIP_SNAPSHOT)),--skip-snapshot) \
	  $(if $(filter-out 0 false,$(DRY_RUN)),--dry-run)

## Install the local prepare-commit-msg hook that auto-generates commit messages.
install_commit_msg_hook:
	bash tools/install_commit_msg_hook.sh install

## Remove the local prepare-commit-msg hook and restore previous backup when available.
uninstall_commit_msg_hook:
	bash tools/install_commit_msg_hook.sh uninstall

## Preview the generated commit message for currently staged changes.
preview_commit_msg:
	$(PYTHON) tools/generate_commit_message.py --from-staged
