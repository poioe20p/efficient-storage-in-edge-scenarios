#!/usr/bin/env bash

# AUTO-COMMIT-MSG-HOOK
# Generates a commit message only when staged changes remain identical for 3s.

set -euo pipefail

MSG_FILE=${1:-}
SOURCE=${2:-}

if [[ -z "${MSG_FILE}" ]]; then
    exit 0
fi

case "${SOURCE}" in
    merge|squash|commit)
        exit 0
        ;;
esac

# If the user already typed a message, do not overwrite it.
if grep -Eq '^[^#[:space:]].*' "${MSG_FILE}"; then
    exit 0
fi

if git diff --cached --quiet; then
    exit 0
fi

HASH0=$(git diff --cached --binary | git hash-object --stdin)
if [[ -z "${HASH0}" ]]; then
    exit 0
fi

sleep 3

HASH1=$(git diff --cached --binary | git hash-object --stdin)
if [[ "${HASH0}" != "${HASH1}" ]]; then
    exit 0
fi

REPO_ROOT=$(git rev-parse --show-toplevel)
GENERATOR="${REPO_ROOT}/source/scripts/tools/generate_commit_message.py"

if [[ ! -f "${GENERATOR}" ]]; then
    exit 0
fi

PYTHON_BIN=""
if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
fi

if [[ -z "${PYTHON_BIN}" ]]; then
    exit 0
fi

TMP_FILE=$(mktemp)
trap 'rm -f "${TMP_FILE}"' EXIT

if ! "${PYTHON_BIN}" "${GENERATOR}" --from-staged >"${TMP_FILE}"; then
    exit 0
fi

if [[ ! -s "${TMP_FILE}" ]]; then
    exit 0
fi

cat "${TMP_FILE}" >"${MSG_FILE}"
