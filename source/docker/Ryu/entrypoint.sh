#!/bin/bash
set -euo pipefail

if [ -d /workspace/ryu ]; then
    echo "[entrypoint] Ensuring editable install of Ryu..."
    pip install -e /workspace/ryu >/tmp/ryu_pip_install.log 2>&1 || {
        echo "[entrypoint] pip install failed; see /tmp/ryu_pip_install.log" >&2
        cat /tmp/ryu_pip_install.log >&2
        exit 1
    }
fi

echo "[entrypoint] Launching ryu-manager $*"
exec ryu-manager "$@"
