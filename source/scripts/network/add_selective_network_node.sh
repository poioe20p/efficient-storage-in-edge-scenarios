#!/bin/bash

# ============================================================================
# Attach a running Tier 1 selective-sync container to an existing LAN.
#
# Thin wrapper around add_network_node.sh. The Tier 1 container runs mongod
# standalone (no --replSet) and therefore has no RS-join wait — the attach
# steps themselves are identical to those for full replicas, so this script
# just delegates. It exists as a separate entry point so the SDN controller's
# SelectiveStorageNodeAdder can call a dedicated script (mirroring the
# StorageNodeAdder → add_network_node.sh mapping).
# ============================================================================

set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${SCRIPT_DIR}/add_network_node.sh" "$@"
