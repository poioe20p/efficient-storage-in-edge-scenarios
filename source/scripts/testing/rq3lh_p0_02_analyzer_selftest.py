#!/usr/bin/env python3
"""Small synthetic selftest for the RQ3 low-headroom analyzer."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "source/scripts/testing/analysis"))

from rq3 import readiness_low_headroom as analysis  # noqa: E402


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    check(analysis.percentile([1.0, 2.0, 3.0, 4.0], 0.5) == 2.5,
          "linear percentile")
    rows = [
        {"status": "completed", "http_status": "200", "latency_s": 0.010},
        {"status": "completed", "http_status": "500", "latency_s": 0.001},
        {"status": "timeout", "http_status": "000", "latency_s": None},
        {"status": "canceled", "http_status": "000", "latency_s": None},
    ]
    check(sum(analysis.is_success(row) for row in rows) == 1, "status classification")
    check(analysis.label_key("rq3lh_direct_1") == "1", "run label pairing")
    check(analysis.label_key("rq3lh_event_absent_2") == "2", "absence label pairing")
    check(analysis.label_key("unrelated") is None, "unrelated label rejection")
    check(round(analysis.timestamp("2026-08-09T12:02:45.752451697Z"), 6)
          == round(1786276965.752451, 6), "9-digit fraction timestamp")

    plateau_rows = [
        {"phase": "compute_plateau", "client_lan": "lan1", "_sent": 100.0},
        {"phase": "compute_plateau", "client_lan": "lan1", "_sent": 700.0},
        {"phase": "compute_plateau", "client_lan": "lan2", "_sent": 100.0},
        {"phase": "compute_plateau", "client_lan": "lan2", "_sent": 700.0},
    ]
    bounds = analysis.labeled_plateau_bounds(plateau_rows)
    check(bounds[1] == (100.0, 700.0), "labeled plateau bounds lan1")
    check(bounds[2] == (100.0, 700.0), "labeled plateau bounds lan2")

    original_spawned = analysis.spawned
    try:
        analysis.spawned = lambda _run_dir: [
            {"lan": 1, "container": "pre", "result": "admitted",
             "_true_ready": 120.0, "_admitted": 120.0},
            {"lan": 1, "container": "ok", "result": "admitted",
             "_true_ready": 160.0, "_admitted": 160.0},
            {"lan": 1, "container": "late", "result": "admitted",
             "_true_ready": 695.0, "_admitted": 695.0},
            {"lan": 2, "container": "ok2", "result": "admitted",
             "_true_ready": 160.0, "_admitted": 160.0},
        ]
        anchors = analysis.first_anchors(Path("unused"), plateau_rows)
        check(anchors[1]["container"] == "ok",
              "eligible anchor selected over pre-plateau candidate")
        check(anchors[2]["container"] == "ok2", "eligible anchor lan2")

        analysis.spawned = lambda _run_dir: [
            {"lan": 1, "container": "bad", "result": "rejected",
             "_true_ready": 160.0, "_admitted": None},
            {"lan": 2, "container": "ok2", "result": "admitted",
             "_true_ready": 160.0, "_admitted": 160.0},
        ]
        try:
            analysis.first_anchors(Path("unused"), plateau_rows)
            check(False, "unadmitted eligible anchor must fail the run")
        except ValueError:
            pass

        analysis.spawned = lambda _run_dir: [
            {"lan": 1, "container": "pre", "result": "admitted",
             "_true_ready": 120.0, "_admitted": 120.0},
            {"lan": 2, "container": "ok2", "result": "admitted",
             "_true_ready": 160.0, "_admitted": 160.0},
        ]
        try:
            analysis.first_anchors(Path("unused"), plateau_rows)
            check(False, "no eligible candidate must fail the run")
        except ValueError:
            pass
    finally:
        analysis.spawned = original_spawned

    def fake_row(sent: float, status: str, http: str,
                 lat: float | None) -> dict:
        return {"phase": "compute_plateau", "client_lan": "lan1",
                "status": status, "http_status": http, "latency_s": lat,
                "_sent": sent, "_latency": lat}

    ok_rows = [fake_row(10.0 + i * 0.01, "completed", "200", 0.001)
               for i in range(120)]
    metric = analysis.window_metric(ok_rows, 1, 10.0, 20.0)
    check(metric["requests"] == 120, "window request count")
    check(metric["successful"] == 120, "window success count")
    few_success = [fake_row(10.0 + i * 0.01, "completed", "200", 0.001)
                   for i in range(80)]
    few_success += [fake_row(20.0 + i * 0.01, "timeout", "000", None)
                    for i in range(50)]
    try:
        analysis.window_metric(few_success, 1, 10.0, 30.0)
        check(False, "success floor must reject sparse-success windows")
    except ValueError:
        pass

    print("RQ3 low-headroom analyzer selftest: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
