#!/bin/bash
# ============================================================================
# Apply or update WAN-emulation netem on the inter-LAN router (eth1 ↔ eth2).
#
# Half of WAN_RTT_MS goes on each LAN-side egress so RTT(lan1↔lan2) ≈ WAN_RTT_MS.
# Same-LAN traffic stays inside its OVS bridge and never enters this netns,
# so it is unaffected.
#
# Idempotent: re-running replaces any existing root qdisc on eth1/eth2.
# All knobs default to 0 (no emulation) so calling this with no env set is
# a safe no-op clear.
#
# Env knobs (set in source/scripts/wan.env):
#   WAN_RTT_MS     — symmetric round-trip latency, ms (default 0 = no delay)
#   WAN_JITTER_MS  — netem jitter on top of one-way delay, ms (default 0)
#   WAN_LOSS_PCT   — packet loss percentage, 0–100 (default 0)
#   WAN_RATE_KBIT  — egress bandwidth cap in kbit, 0 = uncapped (default 0)
#
# Caveats:
#   - Internet-bound replies returning via the router (eth0→eth1/eth2) are
#     also delayed. Negligible for phases.json (no Internet calls), but
#     would matter for workloads that fetch from outside.
# ============================================================================
set -euo pipefail

PID_ROUTER=${PID_ROUTER:-$(docker inspect -f '{{.State.Pid}}' nat-router 2>/dev/null || true)}
if [[ -z "${PID_ROUTER}" ]]; then
    echo "[wan] nat-router container not running — skipping netem setup" >&2
    exit 0
fi

RTT=${WAN_RTT_MS:-0}
JIT=${WAN_JITTER_MS:-0}
LOSS=${WAN_LOSS_PCT:-0}
RATE=${WAN_RATE_KBIT:-0}
ONE_WAY=$(( RTT / 2 ))

apply_one() {
    local iface=$1
    # Always clear first so re-runs are idempotent.
    sudo nsenter -t "${PID_ROUTER}" -n tc qdisc del dev "${iface}" root 2>/dev/null || true

    if [[ "${RTT}" -eq 0 && "${LOSS}" -eq 0 && "${RATE}" -eq 0 ]]; then
        echo "[wan] ${iface}: cleared (no emulation)"
        return
    fi

    local args=()
    if [[ "${RTT}" -gt 0 ]]; then
        if [[ "${JIT}" -gt 0 ]]; then
            args+=(delay "${ONE_WAY}ms" "${JIT}ms" distribution normal)
        else
            args+=(delay "${ONE_WAY}ms")
        fi
    fi
    [[ "${LOSS}" -gt 0 ]] && args+=(loss "${LOSS}%")
    [[ "${RATE}" -gt 0 ]] && args+=(rate "${RATE}kbit")

    sudo nsenter -t "${PID_ROUTER}" -n tc qdisc add dev "${iface}" root netem "${args[@]}"
    echo "[wan] ${iface}: ${args[*]}"
}

apply_one eth1
apply_one eth2
