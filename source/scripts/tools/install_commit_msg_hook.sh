#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(git -C "${SCRIPT_DIR}" rev-parse --show-toplevel)
HOOKS_DIR="${REPO_ROOT}/.git/hooks"
HOOK_PATH="${HOOKS_DIR}/prepare-commit-msg"
SOURCE_HOOK="${REPO_ROOT}/source/scripts/tools/prepare_commit_msg_hook.sh"
BACKUP_PATH="${HOOKS_DIR}/prepare-commit-msg.pre-auto-msg.bak"

ACTION=${1:-install}

install_hook() {
    if [[ ! -f "${SOURCE_HOOK}" ]]; then
        echo "[ERROR] Source hook script not found: ${SOURCE_HOOK}" >&2
        exit 1
    fi

    mkdir -p "${HOOKS_DIR}"

    if [[ -f "${HOOK_PATH}" ]] && ! grep -q "AUTO-COMMIT-MSG-HOOK" "${HOOK_PATH}"; then
        cp "${HOOK_PATH}" "${BACKUP_PATH}"
        echo "[INFO] Existing hook backed up to ${BACKUP_PATH}"
    fi

    cp "${SOURCE_HOOK}" "${HOOK_PATH}"
    chmod +x "${HOOK_PATH}"
    echo "[INFO] Installed hook at ${HOOK_PATH}"
}

uninstall_hook() {
    if [[ ! -f "${HOOK_PATH}" ]]; then
        echo "[INFO] No prepare-commit-msg hook found; nothing to uninstall."
        return
    fi

    if grep -q "AUTO-COMMIT-MSG-HOOK" "${HOOK_PATH}"; then
        rm -f "${HOOK_PATH}"
        echo "[INFO] Removed auto commit-message hook."
    else
        echo "[INFO] Existing hook is not managed by this installer; leaving it unchanged."
    fi

    if [[ -f "${BACKUP_PATH}" ]] && [[ ! -f "${HOOK_PATH}" ]]; then
        mv "${BACKUP_PATH}" "${HOOK_PATH}"
        chmod +x "${HOOK_PATH}"
        echo "[INFO] Restored previous hook from backup."
    fi
}

case "${ACTION}" in
    install)
        install_hook
        ;;
    uninstall)
        uninstall_hook
        ;;
    *)
        echo "Usage: $0 [install|uninstall]" >&2
        exit 1
        ;;
esac
