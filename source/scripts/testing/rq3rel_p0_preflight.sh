#!/bin/bash
# ============================================================================
# rq3rel_p0_preflight.sh — research_q3 release-mechanism pre-flight gate.
#
# Runs on the cloud VM (cd's to the repo root, so any CWD works).
#
# The research_q3 mini phases are deliberately NOT used here: the quarantine
# timeline (a release held for RELEASE_STABILIZE_S before completing) cannot be
# exercised in a short run. This calibration run is therefore the
# mechanism-firing gate for the STABILIZED arm (Stages 0–2 of the staged
# preflight in docs/operation/testing/experiment/research_q3/preflight_campaign.md);
# Stages 3–4 (arm smokes + the 28-run campaign) are runner-driven per that doc.
#
# Stage 1 — harness quick check:
#   1. canonical phases file present (source/scripts/testing/phases.json)
#   2. canonical controller override pins RELEASE_MECHANISM=off
# Stage 2 — one full-length STABILIZED calibration run:
#   research_q3_launch_run.sh arm_stabilized.env research_q3_cal_s1 42, then an
#   rs_status probe on the newest run dir, then a manual checklist plus
#   script-checkable PASS/FAIL hints (release-log event rows).
#
# Exit 0 = all checked gates pass; 1 = a gate failed.
# ============================================================================

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../../.." || exit 1

echo "== rq3rel_p0_preflight: repo root = $(pwd) =="

# ---------------------------------------------------------------------------
# Stage 1 — harness quick check
# ---------------------------------------------------------------------------
echo
echo "== Stage 1 — harness quick check =="
if [[ ! -f source/scripts/testing/phases.json ]]; then
    echo "[FAIL] source/scripts/testing/phases.json missing — canonical phases file required" >&2
    exit 1
fi
echo "[PASS] canonical phases.json present"

if ! grep -qE '^RELEASE_MECHANISM=off($|[[:space:]])' \
     source/scripts/testing/controller_env_overrides/current_state_integrated.env; then
    echo "[FAIL] current_state_integrated.env does not pin RELEASE_MECHANISM=off" \
         "(the incumbent arm must have the release mechanism explicitly off)" >&2
    exit 1
fi
echo "[PASS] canonical env pins RELEASE_MECHANISM=off"

# ---------------------------------------------------------------------------
# Stage 2 — full-length STABILIZED calibration run (the riskiest timeline)
# ---------------------------------------------------------------------------
echo
echo "== Stage 2 — STABILIZED calibration run (mechanism-firing gate) =="
echo "  launch: bash source/scripts/testing/research_q3_launch_run.sh arm_stabilized.env research_q3_cal_s1 42"
bash source/scripts/testing/research_q3_launch_run.sh arm_stabilized.env research_q3_cal_s1 42
echo "[DONE] calibration run completed"

echo
echo "== Stage 2b — post-run replica-set probe (newest run dir) =="
RUN_DIR="$(ls -dt source/scripts/testing/metrics/*/ 2>/dev/null | head -n1 || true)"
if [[ -z "$RUN_DIR" ]]; then
    echo "[FAIL] no run dir found under source/scripts/testing/metrics/" >&2
    exit 1
fi
RUN_DIR="${RUN_DIR%/}"
echo "  newest run dir: $RUN_DIR"
python3 source/scripts/testing/rq3rel_p4_rs_probe.py --run-dir "$RUN_DIR" --label cal_s1

echo
echo "== Manual verification checklist (operator verifies) =="
echo "  [ ] harness active      : controller logs show flow-isolation markers"
echo "  [ ] storm spawn         : both tiers (compute + storage) spawn in storm"
echo "  [ ] release events      : quarantine/recall rows in release_log_lan{1,2}.csv"
echo "  [ ] evictions           : 0 non-ok evictions in rs_evict_logs_lan{1,2}/"
echo "  [ ] D1 attribution      : D1 clean outside attribution windows"

echo
echo "== Script-checkable hints (release log event rows) =="
_qb_total=0
_rc_total=0
_en_total=0
for _f in "$RUN_DIR"/release_log_lan1.csv "$RUN_DIR"/release_log_lan2.csv; do
    if [[ ! -f "$_f" ]]; then
        echo "  [hint] $(basename "$_f") missing — quarantine never armed?"
        continue
    fi
    # release_log is CSV; the event column value is matched (e.g. ,recall,).
    _qb="$(grep -c ',quarantine_begin,' "$_f" 2>/dev/null || true)"
    _rc="$(grep -c ',recall,' "$_f" 2>/dev/null || true)"
    _en="$(grep -c ',end,' "$_f" 2>/dev/null || true)"
    echo "  [hint] $(basename "$_f"): quarantine_begin=$_qb recall=$_rc end=$_en"
    _qb_total=$((_qb_total + ${_qb:-0}))
    _rc_total=$((_rc_total + ${_rc:-0}))
    _en_total=$((_en_total + ${_en:-0}))
done
if [[ "$_qb_total" -gt 0 ]] && [[ "$_rc_total" -gt 0 ]]; then
    echo "  [PASS] quarantine_begin rows: $_qb_total; recall rows: $_rc_total"
else
    echo "  [FAIL] calibration run must show quarantine_begin AND recall rows" \
         "(quarantine_begin=$_qb_total recall=$_rc_total — the stabilized arm never armed or never recalled)" >&2
    exit 1
fi
if [[ "$_en_total" -gt 0 ]]; then
    echo "  [PASS-hint] end rows: $_en_total"
else
    echo "  [FAIL-hint] no end rows — release never completed (informational)"
fi

echo
echo "[DONE] rq3rel_p0_preflight complete"
