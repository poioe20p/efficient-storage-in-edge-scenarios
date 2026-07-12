"""Phase 0 smoke test — verifies cross-region spawn plumbing."""
from sdn_controller.scaling_config import (
    _CROSS_REGION_STORAGE_ENABLED,
    _CROSS_REGION_STORAGE_WARM,
    _MAX_CROSS_REGION_STORAGE,
)
print("ENABLED =", _CROSS_REGION_STORAGE_ENABLED)
print("WARM    =", _CROSS_REGION_STORAGE_WARM)
print("MAX     =", _MAX_CROSS_REGION_STORAGE)

from sdn_controller.elasticity.elasticity import DataAlert
import inspect

params = list(inspect.signature(DataAlert).parameters.keys())
assert "owner_primary" in params, "MISSING owner_primary field on DataAlert"
print("DataAlert fields:", [p for p in params if p != "self"])
print("owner_primary field: OK")

# Verify defaults
a = DataAlert(lan=1, network_id="lan1", rs_name="rs_net1", primary_container="test")
assert a.owner_primary == "", f"Expected empty default, got: {a.owner_primary!r}"
assert a.cross_lan_rs is False, "Expected cross_lan_rs default False"
print("Defaults: OK")

# Verify cross-region construction works
b = DataAlert(
    lan=2, network_id="lan2", rs_name="rs_net1",
    primary_container="edge_storage_server_n1",
    cross_lan_rs=True, owner_lan="lan1",
    owner_primary="10.0.0.4:27018",
)
assert b.owner_primary == "10.0.0.4:27018"
assert b.owner_lan == "lan1"
assert b.cross_lan_rs is True
print("Cross-region construction: OK")

print("\n=== ALL PHASE 0 CHECKS PASSED ===")
