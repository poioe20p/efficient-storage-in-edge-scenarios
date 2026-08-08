#!/usr/bin/env python3
"""
rq2v2_p5_01_policy_gate_ba_commit_test.py — Phase-5 gate for the bottleneck-
aware one-fired commit fix (P5 ba_db preflight failure, 2026-08-08).

The ba arm on the data-bound episode failed because the per-window one-fired
selection acted on a compute fire even though the classifier had already
declared storage the bottleneck (storage eligible with higher score but not
yet "fired"). This gate verifies the fix: in bottleneck_aware mode a fire is
acted on only when its tier is the classifier's declared bottleneck; a
mismatch is suppressed (select() -> (), last_suppressed() -> the tier).

Checks:
  1. compute fires alone, storage eligible + higher score -> compute SUPPRESSED
     (this is the exact P5 w37 shape: class=storage, cF=1, sF=0, sScore>cScore).
  2. next window storage fires alone -> storage selected (reserve activates).
  3. storage relieved (score below threshold, not eligible) -> compute fires
     alone -> compute selected (compute is now the declared bottleneck).
  4. one-fired when the other tier is NOT eligible -> fired tier acts (no
     regression).
  5. both fire -> classified tier (unchanged).
  6. margin tie (|d| <= margin) -> storage tie-break suppresses a compute fire.
  7. strict mode, not committed, compute fires alone with storage eligible
     higher -> suppressed (step-4 consistency).
  8. last_suppressed() is None when nothing was suppressed.

Exit 0 = all checks pass; non-zero = gate failed.
"""
import os
import sys

os.environ["SCALEUP_POLICY"] = "bottleneck_aware"
os.environ["BOTTLENECK_STRICT_SINGLE"] = "0"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sdn_controller.policy_gate import PolicyGate  # noqa: E402
from sdn_controller.scaling_policy import ScaleUpVerdict  # noqa: E402


def V(tier, fired, score_norm, threshold=0.5, eligible=None):
    if eligible is None:
        eligible = score_norm >= threshold
    return ScaleUpVerdict(
        tier=tier, eligible=eligible, fired=fired,
        score_norm=score_norm, score=score_norm, threshold=threshold)


def main() -> int:
    failures = []

    # -- 1. P5 w37 shape: compute fires alone, storage eligible + higher -----
    g = PolicyGate()
    sel = g.select(
        V("compute", True, 0.47, threshold=0.18),
        V("storage", False, 0.60, threshold=0.35),
    )
    if sel != ():
        failures.append(f"1: expected suppression (), got {sel}")
    if g.last_suppressed() != "compute":
        failures.append(f"1: last_suppressed should be 'compute', got {g.last_suppressed()}")

    # -- 2. P5 w38 shape: storage fires alone -> storage selected ------------
    sel = g.select(
        V("compute", False, 0.37, threshold=0.28),
        V("storage", True, 0.58, threshold=0.35),
    )
    if sel != ("storage",):
        failures.append(f"2: expected ('storage',), got {sel}")
    if g.last_suppressed() is not None:
        failures.append("2: nothing suppressed this window")

    # -- 3. storage relieved: compute fires alone, storage not eligible ------
    sel = g.select(
        V("compute", True, 0.50, threshold=0.38),
        V("storage", False, 0.30, threshold=0.45),
    )
    if sel != ("compute",):
        failures.append(f"3: compute is now the bottleneck, expected ('compute',), got {sel}")

    # -- 4. other tier NOT eligible -> fired tier acts -----------------------
    g = PolicyGate()
    sel = g.select(
        V("compute", True, 0.50, threshold=0.38),
        V("storage", False, 0.10, threshold=0.35),
    )
    if sel != ("compute",):
        failures.append(f"4: expected ('compute',), got {sel}")

    # -- 5. both fire -> classified tier (storage higher) --------------------
    g = PolicyGate()
    sel = g.select(
        V("compute", True, 0.40, threshold=0.18),
        V("storage", True, 0.60, threshold=0.35),
    )
    if sel != ("storage",):
        failures.append(f"5: expected ('storage',), got {sel}")

    # -- 6. margin tie -> storage tie-break suppresses a compute fire --------
    g = PolicyGate()
    sel = g.select(
        V("compute", True, 0.60, threshold=0.18),
        V("storage", False, 0.63, threshold=0.35),
    )
    if sel != ():
        failures.append(f"6: margin tie should suppress to storage, got {sel}")
    if g.last_suppressed() != "compute":
        failures.append(f"6: last_suppressed should be 'compute', got {g.last_suppressed()}")

    # -- 7. strict mode, not committed, step-4 consistency (subprocess: the
    #        module reads BOTTLENECK_STRICT_SINGLE at import time) -----------
    import subprocess
    import textwrap
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    code = textwrap.dedent(f"""
        import os, sys
        os.environ['SCALEUP_POLICY'] = 'bottleneck_aware'
        os.environ['BOTTLENECK_STRICT_SINGLE'] = '1'
        sys.path.insert(0, {root!r})
        from sdn_controller.policy_gate import PolicyGate
        from sdn_controller.scaling_policy import ScaleUpVerdict
        def V(tier, fired, score_norm, threshold=0.5, eligible=None):
            if eligible is None:
                eligible = score_norm >= threshold
            return ScaleUpVerdict(tier=tier, eligible=eligible, fired=fired,
                                  score_norm=score_norm, score=score_norm,
                                  threshold=threshold)
        g = PolicyGate()
        assert g.strict_enabled(), 'strict must be ON'
        sel = g.select(V('compute', True, 0.47, threshold=0.18),
                       V('storage', False, 0.60, threshold=0.35))
        assert sel == (), f'strict step-4 should suppress, got {{sel}}'
        assert g.last_suppressed() == 'compute', g.last_suppressed()
        print('  [PASS] 7: strict step-4 suppresses the non-bottleneck fire')
    """)
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    if r.returncode != 0:
        failures.append(f"7: strict subprocess failed: {r.stderr.strip()}")

    # -- 8. nothing fired -> no suppression ---------------------------------
    g = PolicyGate()
    sel = g.select(
        V("compute", False, 0.30, threshold=0.38),
        V("storage", False, 0.20, threshold=0.45),
    )
    if sel != ():
        failures.append(f"8: expected (), got {sel}")
    if g.last_suppressed() is not None:
        failures.append("8: last_suppressed should be None when nothing fired")

    if failures:
        print("FAIL")
        for f in failures:
            print("  -", f)
        return 1
    print("PASS: all bottleneck-aware one-fired commit checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
