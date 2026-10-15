#!/usr/bin/env bash
# Pre-launch per-run label check for the frozen-tree launchers (plan §5.1/§10).
#
# C1/C2/C4 launch from the frozen worktrees `rq3tim_frozen` @ 852a8a3 and
# `rq3snd_frozen2` @ 541fb22. The TIMING launcher (852a8a3) predates the
# duplicate-label guard — the standalone check is C1's protection. The
# SOUNDNESS launcher (541fb22) carries its own duplicate-label refusal, so
# C2/C4 have the launcher guard in addition to this check. The runner invokes
# this check IMMEDIATELY BEFORE EVERY launch from a frozen tree (and after
# every quarantine/rerun decision), pointed at the EXECUTION tree whose
# metrics/ holds the runs:
#
#   bash ~/efficient-storage-in-edge-scenarios/source/scripts/testing/rq3adm_p0_04_label_check.sh \
#       --tree ~/rq3snd_frozen2 <label>          # C2/C4 (or ~/rq3tim_frozen for C1)
#
# `--tree` is repeatable: every given tree is scanned (one `scanned:` line
# per tree, in the order given), the check refuses the label if ANY tree
# holds a `*_<label>` run folder, and it exits 2 if ANY tree (or its
# metrics/ dir) is invalid — a repeated `--tree` accumulates, never
# silently last-wins. With no `--tree`, the check scans its own tree's
# metrics/ (the pre-`--tree` behaviour); the frozen-tree predicate
# `find <tree>/source/scripts/testing/metrics -maxdepth 1 -name '*_<label>'`
# is the independent cross-check, expected empty.
#
# The label must be the exact planned label (e.g. rq3tim_none_event_only_7,
# rq3snd_premature10_hybrid_4, rq3snd_none_reconcile_5); the check refuses a
# label that already has a run folder under any scanned tree's
# source/scripts/testing/metrics/ (`*_<label>`), which is the same predicate
# the campaign launchers use.
#
# Exit codes: 0 = no existing run folder in any scanned tree (launch may
#                 proceed);
#             3 = duplicate label (STOP — never launch; the run is already
#                 recorded under this label);
#             2 = usage error / fail-closed error (any unknown or missing
#                 tree, or a metrics scan that fails — an unreadable or
#                 IO-erroring metrics dir never passes silently).
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

usage() {
    echo "usage: $0 [--tree <tree-root>]... <label>" >&2
    exit 2
}

TREES=()
ARGS=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --tree)
            [[ $# -ge 2 && -n "${2:-}" ]] || usage
            TREES+=("$2")
            shift 2
            ;;
        --tree=*)
            [[ -n "${1#--tree=}" ]] || usage
            TREES+=("${1#--tree=}")
            shift
            ;;
        -h|--help)
            echo "usage: $0 [--tree <tree-root>]... <label>"
            exit 0
            ;;
        -*)
            usage
            ;;
        *)
            ARGS+=("$1")
            shift
            ;;
    esac
done
[[ ${#ARGS[@]} -eq 1 && -n "${ARGS[0]:-}" ]] || usage

readonly LABEL="${ARGS[0]}"
[[ "$LABEL" != *"/"* && "$LABEL" != *".."* ]] || {
    echo "ERROR: invalid label '$LABEL'" >&2
    exit 2
}

if [[ ${#TREES[@]} -eq 0 ]]; then
    TREES=("$REPO_ROOT")
fi

# De-duplicate exact repeats (order preserved); each remaining tree is
# scanned, so a repeated flag accumulates instead of last-winning.
UNIQUE_TREES=()
for tree in "${TREES[@]}"; do
    duplicate=0
    for prior in "${UNIQUE_TREES[@]}"; do
        if [[ "$prior" == "$tree" ]]; then
            duplicate=1
            break
        fi
    done
    [[ $duplicate -eq 1 ]] || UNIQUE_TREES+=("$tree")
done

# Validate EVERY tree before scanning any of them (fail closed on any typo).
for tree in "${UNIQUE_TREES[@]}"; do
    [[ -d "$tree" ]] || {
        echo "ERROR: tree root not found: $tree" >&2
        exit 2
    }
    [[ -d "$tree/source/scripts/testing/metrics" ]] || {
        echo "ERROR: metrics dir not found: $tree/source/scripts/testing/metrics (wrong --tree?)" >&2
        exit 2
    }
done

hits=0
for tree in "${UNIQUE_TREES[@]}"; do
    metrics_dir="$tree/source/scripts/testing/metrics"
    echo "scanned: $metrics_dir"
    if ! existing_run="$(find "$metrics_dir" -mindepth 1 -maxdepth 1 -type d \
            -name "*_${LABEL}" -print 2>/dev/null | sort)"; then
        echo "ERROR: metrics scan failed for tree '$tree' ($metrics_dir) — cannot establish label uniqueness (fail closed)" >&2
        exit 2
    fi
    if [[ -n "$existing_run" ]]; then
        hits=1
        while IFS= read -r hit; do
            echo "DUPLICATE LABEL: '$LABEL' already has a run folder: $hit" >&2
        done <<< "$existing_run"
    fi
done

if [[ $hits -ne 0 ]]; then
    echo "STOP: never launch; escalate to campaign_log.md (quarantine/replace)." >&2
    exit 3
fi

echo "label check PASS: no existing run folder for '$LABEL' in any scanned tree (launch may proceed)"
exit 0
