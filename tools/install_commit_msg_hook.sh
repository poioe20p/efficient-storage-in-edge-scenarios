#!/usr/bin/env bash
# Install or uninstall the prepare-commit-msg hook.
set -euo pipefail

REPO_ROOT=$(git rev-parse --show-toplevel)
HOOK_FILE="${REPO_ROOT}/.git/hooks/prepare-commit-msg"

install_hook() {
    if [[ -f "${HOOK_FILE}" ]]; then
        # Backup existing hook if it is not our hook
        if ! grep -q "AUTO-COMMIT-MSG-HOOK" "${HOOK_FILE}" 2>/dev/null; then
            cp "${HOOK_FILE}" "${HOOK_FILE}.backup.$(date +%Y%m%d%H%M%S)"
            echo "Backed up existing hook."
        fi
    fi

    cat > "${HOOK_FILE}" << 'HOOKEOF'
#!/usr/bin/env bash

# AUTO-COMMIT-MSG-HOOK
# Generates a commit message via DeepSeek V4 Flash agent.
# Only runs when no user message exists and staged changes are stable.

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
GENERATOR="${REPO_ROOT}/tools/generate_commit_message.py"

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

if ! "${PYTHON_BIN}" "${GENERATOR}" --from-staged >"${TMP_FILE}" 2>/dev/null; then
    # Agent generation failed silently — let user type their own message
    exit 0
fi

if [[ ! -s "${TMP_FILE}" ]]; then
    exit 0
fi

cat "${TMP_FILE}" >"${MSG_FILE}"
HOOKEOF

    chmod +x "${HOOK_FILE}"
    echo "Commit message hook installed at ${HOOK_FILE}"
}

uninstall_hook() {
    if [[ -f "${HOOK_FILE}" ]] && grep -q "AUTO-COMMIT-MSG-HOOK" "${HOOK_FILE}" 2>/dev/null; then
        rm "${HOOK_FILE}"
        echo "Commit message hook removed."

        # Restore most recent backup if available
        local newest_backup
        newest_backup=$(ls -t "${HOOK_FILE}.backup."* 2>/dev/null | head -1 || true)
        if [[ -n "${newest_backup}" ]]; then
            cp "${newest_backup}" "${HOOK_FILE}"
            echo "Restored backup: ${newest_backup}"
        fi
    else
        echo "No AUTO-COMMIT-MSG-HOOK found to uninstall."
    fi
}

case "${1:-}" in
    install) install_hook ;;
    uninstall) uninstall_hook ;;
    *)
        echo "Usage: $0 {install|uninstall}"
        exit 1
        ;;
esac
