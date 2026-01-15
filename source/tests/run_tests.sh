#!/bin/bash

# Entrypoint for lab validation checks.
# - Ensures required containers are running
# - Runs the connectivity test suite

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

print_usage() {
  cat <<'EOF'
Usage: ./run_tests.sh [lan1|lan2|cross|all]

Runs container checks plus the connectivity suite.

Defaults:
  If no argument is provided, runs: all
EOF
}

main() {
  local suite=${1:-all}

  case "$suite" in
    -h|--help|help)
      print_usage
      exit 0
      ;;
  esac

  "${SCRIPT_DIR}/check_containers.sh"
  "${SCRIPT_DIR}/test_conectivity.sh" "$suite"
}

main "$@"
