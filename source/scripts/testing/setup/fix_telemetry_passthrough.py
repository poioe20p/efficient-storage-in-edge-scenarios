"""Fix telemetry variable passthrough in build_network_setup.sh.

Adds TELEMETRY_SOURCE and POLL_INTERVAL_S environment variable forwarding
to both osken and osken_2 docker run commands in build_network_setup.sh.

Without this fix, main_n1.py silently defaults to TELEMETRY_SOURCE=zmq
and all poll-mode runs become push runs.

Usage:
    python fix_telemetry_passthrough.py [--dry-run]
"""
import shutil
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
BUILD_SCRIPT = REPO_ROOT / "source" / "scripts" / "build_network_setup.sh"

INSERT_LINES = [
    '    -e TELEMETRY_SOURCE="${TELEMETRY_SOURCE:-zmq}" \\\n',
    '    -e POLL_INTERVAL_S="${POLL_INTERVAL_S:-10}" \\\n',
]


def fix(dry_run: bool = False) -> None:
    if not BUILD_SCRIPT.exists():
        print(f"ERROR: {BUILD_SCRIPT} not found")
        sys.exit(1)

    lines = BUILD_SCRIPT.read_text().splitlines(keepends=True)

    # Check if already patched
    if any("TELEMETRY_SOURCE" in l for l in lines):
        print("TELEMETRY_SOURCE already present — no changes needed.")
        return

    if not dry_run:
        shutil.copy(BUILD_SCRIPT, str(BUILD_SCRIPT) + ".bak")

    new_lines = []
    edge_count = 0
    for line in lines:
        new_lines.append(line)
        if "-e EDGE_CPUS=" in line:
            edge_count += 1
            if edge_count <= 2:  # osken + osken_2
                new_lines.extend(INSERT_LINES)

    if dry_run:
        print(f"Would add TELEMETRY_SOURCE/POLL_INTERVAL_S after EDGE_CPUS lines")
        for i, line in enumerate(new_lines):
            if "TELEMETRY_SOURCE" in line or "POLL_INTERVAL_S" in line:
                print(f"  Line {i+1}: {line.rstrip()}")
    else:
        BUILD_SCRIPT.write_text("".join(new_lines))
        print(f"Added TELEMETRY_SOURCE/POLL_INTERVAL_S passthrough to {BUILD_SCRIPT}")
        for i, line in enumerate(BUILD_SCRIPT.read_text().splitlines(keepends=True)):
            if "TELEMETRY_SOURCE" in line or "POLL_INTERVAL_S" in line:
                print(f"  Line {i+1}: {line.rstrip()}")

    print()
    print("Verification: after make setup_network, run:")
    print("  docker exec osken env | grep -E 'TELEMETRY_SOURCE|POLL_INTERVAL_S'")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    fix(dry_run=dry_run)
