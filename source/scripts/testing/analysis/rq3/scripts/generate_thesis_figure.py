"""RQ3 thesis figures --- rendered into the house thesis style.

Three renders for the RQ3 results section:
  * `rq3_admission_intervals_v2.png` -- the intact-source interval chain:
    (a) provisioning -> first successful response per backend,
    (b) scaling decision -> usable capacity per run (rate-12 cell).
    (v1, whose first panel was the log-scale verified-readiness ->
    admission dot plot, was superseded 2026-10-05; that interval remains
    in `tab:rq3_delays`.) Sources (read-only):
    `docs/operation/testing/experiment/v2/rq3/graphs/campaign_fixed/
    campaign_stratified_per_backend.csv` and `.../v2/rq3/rq3_probe_summary.csv`
    (the twelve P2 + cell-12 runs per arm, listed in CELL12_RUNS).
  * `rq3_event_loss_outcome.png` -- (a) slow share over time under total
    readiness-event loss, median across the six seed blocks, one line per
    admission configuration; (b) admitted backends per run (dots per block,
    median bar with min--max), showing that the configuration without a
    re-derivation path admits nothing while 32--35 candidates per run are
    abandoned and torn down. Source: the frozen-record export
    `docs/operation/testing/experiment/v3/rq3_timing/analysis/
    timing_figures_data.json`.
  * `rq3_recovery_ordering.png` -- provisioning -> admission per seed block
    for the two re-deriving configurations under total event loss
    (analysis-only re-anchored ordering). Source: the analysis-only companion
    `docs/operation/testing/experiment/v3/rq3_timing/analysis/
    timing_campaign_reanchored.json`. Kept as an archive render; not
    referenced by the thesis build since 2026-10-05.
  * `rq3_soundness_damage_v2.png` -- the timing-lie grid: episode damage
    against the claim lead per rule (seed medians as lines, individual
    seeds as dots). Sources: `docs/operation/testing/experiment/v3/
    rq3_soundness/analysis/rq3snd_damage_all.json` and
    `.../rq3snd_crossover_all.json`; the render is also copied to
    `tese/images/` for the thesis build. (v1, a two-panel version that
    included the retired false-claim family, was superseded 2026-10-05.)

Style mirrors `source/scripts/testing/analysis/rq1/scripts/generate_thesis_graphs.py`
(house seaborn-deep palette, 150/200 dpi, black per-run dots).

Renders are written to the experiment folders
(`.../v2/rq3/graphs/thesis/` and `.../v3/rq3_timing/graphs/thesis/`) and
copied to `tese/images/` (house flow: a revised figure gets a new `_v2` name
and `main.tex` is updated).
"""
from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[6]
DATA = (ROOT / "docs/operation/testing/experiment/v3/rq3_timing/analysis/"
        "timing_figures_data.json")
OUT = ROOT / "docs/operation/testing/experiment/v3/rq3_timing/graphs/thesis"
OUT.mkdir(parents=True, exist_ok=True)

# seaborn-deep --- the thesis house palette (cf. RQ1/RQ2 figures)
COLORS = {"event_only": "#C44E52", "hybrid": "#DD8452", "reconcile": "#4C72B0"}
LABELS = {
    "event_only": "direct lifecycle notification",
    "hybrid": "probe fallback variant",
    "reconcile": "periodic discovery",
}
BLOCKS = [1, 2, 3, 4, 5, 6]
ONSET_S = 150.0
BIN_MIN_SERVICE = 10
RNG = np.random.default_rng(42)

V2 = ROOT / "docs/operation/testing/experiment/v2/rq3"
STRATIFIED_CSV = V2 / "graphs/campaign_fixed/campaign_stratified_per_backend.csv"
PROBE_SUMMARY_CSV = V2 / "rq3_probe_summary.csv"
OUT_V2 = V2 / "graphs/thesis"
OUT_V2.mkdir(parents=True, exist_ok=True)
REANCHORED_JSON = (ROOT / "docs/operation/testing/experiment/v3/rq3_timing/"
                   "analysis/timing_campaign_reanchored.json")
SND = ROOT / "docs/operation/testing/experiment/v3/rq3_soundness"
SND_DAMAGE = SND / "analysis/rq3snd_damage_all.json"
SND_CROSS = SND / "analysis/rq3snd_crossover_all.json"
OUT_SND = SND / "graphs/thesis"
OUT_SND.mkdir(parents=True, exist_ok=True)
COL_SND = {**COLORS, "wake_verify": "#64B5CD"}
LABELS_SND = {**LABELS, "wake_verify": "wake-and-verify"}

# interval-figure arms: direct lifecycle vs periodic discovery (same colours
# as the event-loss figure: direct red, discovery blue, fallback orange)
COL_ARM = {"direct": COLORS["event_only"], "discovery": COLORS["reconcile"],
           "fallback": COLORS["hybrid"]}
GROUPS = [("direct", "fast"), ("direct", "slow"),
          ("discovery", "fast"), ("discovery", "slow")]
GROUP_X = [0, 1, 3, 4]

# rate-12 cell: P2 + cell-12 runs 1..5 per arm of the probe campaign
CELL12_RUNS = {
    "direct": [
        "20260805_184258_rq3_probe_p2_direct",
        "20260805_205423_rq3_probe_cell12_direct_1",
        "20260806_022046_rq3_probe_cell12_direct_2",
        "20260806_024626_rq3_probe_cell12_direct_3",
        "20260806_031155_rq3_probe_cell12_direct_4",
        "20260806_033629_rq3_probe_cell12_direct_5",
    ],
    "discovery": [
        "20260805_190300_rq3_probe_p2_disc",
        "20260805_210637_rq3_probe_cell12_disc_1",
        "20260806_023330_rq3_probe_cell12_disc_2",
        "20260806_025851_rq3_probe_cell12_disc_3",
        "20260806_032414_rq3_probe_cell12_disc_4",
        "20260806_034852_rq3_probe_cell12_disc_5",
    ],
}

plt.rcParams.update({
    "font.size": 12, "axes.labelsize": 12, "xtick.labelsize": 11,
    "ytick.labelsize": 11, "legend.fontsize": 9.5,
    "figure.dpi": 150, "savefig.dpi": 200, "savefig.bbox": "tight",
})


def load() -> dict:
    return json.loads(DATA.read_text(encoding="utf-8"))["data"]


def pooled_series(data: dict, arm: str) -> tuple[list[int], list[float]]:
    """Median slow share (%) per 10 s bin across the six event-loss blocks."""
    buckets: dict[int, list[float]] = {}
    for block in BLOCKS:
        record = data[f"b{block}_loss_all_{arm}"]
        for point in record["series"]:
            if point["slow_rate"] is None or point["service"] < BIN_MIN_SERVICE:
                continue
            buckets.setdefault(round(point["t_rel"]), []).append(point["slow_rate"])
    xs = sorted(buckets)
    ys = [100.0 * float(np.median(buckets[t])) for t in xs]
    return xs, ys


def panel_a(ax, data: dict) -> None:
    x_last = -60
    for arm in ("reconcile", "hybrid", "event_only"):  # affected line on top
        xs, ys = pooled_series(data, arm)
        x_last = max(x_last, xs[-1])
        ax.plot(xs, ys, color=COLORS[arm], lw=1.9, label=LABELS[arm])
    ax.axvspan(0, ONSET_S, color="#C44E52", alpha=0.10, lw=0)
    ax.set_xlabel("time since plateau onset (s)")
    ax.set_ylabel("slow share (%)")
    ax.set_xlim(-65, x_last + 5)
    ax.set_ylim(bottom=0)
    ax.grid(axis="y", alpha=0.25, linestyle="--")
    ax.legend(loc="upper right", frameon=False)
    top = ax.get_ylim()[1]
    ax.text(ONSET_S - 4, top * 0.985, "onset window", ha="right", va="top",
            fontsize=9.5, color="#8c4a4a")
    ax.text(-0.10, 1.045, "(a)", transform=ax.transAxes, fontweight="bold",
            fontsize=11)


def panel_b(ax, data: dict) -> None:
    for i, arm in enumerate(("event_only", "hybrid", "reconcile")):
        values = np.array(
            [data[f"b{block}_loss_all_{arm}"]["admissions"]["admitted"]
             for block in BLOCKS], dtype=float)
        median = float(np.median(values))
        ax.bar(i, median, 0.5, color=COLORS[arm], alpha=0.85,
               edgecolor="white", zorder=2)
        if values.min() != values.max():
            ax.errorbar(i, median,
                        yerr=[[median - values.min()], [values.max() - median]],
                        fmt="none", ecolor="#333", capsize=3, lw=1.2, zorder=3)
        jitter = np.linspace(-0.12, 0.12, len(values))
        ax.scatter(i + jitter, values, color="black", s=20, zorder=4)
        ax.text(i, median + 0.22 if median > 0 else 0.6, f"{int(median)}",
                ha="center", fontsize=10, fontweight="bold")
    ax.set_xticks(np.arange(3), ["direct\nlifecycle", "fallback\nvariant",
                                 "periodic\ndiscovery"])
    ax.set_ylabel("admitted backends per run")
    ax.set_ylim(0, 7.5)
    ax.grid(axis="y", alpha=0.25, linestyle="--")
    ax.text(0.03, 0.97, "direct-lifecycle runs: 0 admitted;\n"
            "32\u201335 candidates per run abandoned",
            transform=ax.transAxes, va="top", fontsize=9)
    ax.text(-0.16, 1.045, "(b)", transform=ax.transAxes, fontweight="bold",
            fontsize=11)


def load_stratified() -> list[dict]:
    """Per-backend rows of the fixed-image readiness campaign."""
    with open(STRATIFIED_CSV, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for row in rows:
        row["ready_ms"] = float(row["ready_to_admit_s"]) * 1000.0
        row["first_s"] = float(row["spawn_to_first_s"])
    return rows


def load_cell12() -> dict[str, list[float]]:
    """Scaling-decision -> usable-capacity per run of the rate-12 cell."""
    with open(PROBE_SUMMARY_CSV, newline="", encoding="utf-8") as fh:
        by_name = {Path(r["run_dir"]).name: r for r in csv.DictReader(fh)}
    out: dict[str, list[float]] = {}
    for arm, names in CELL12_RUNS.items():
        out[arm] = [float(by_name[name]["scale_to_first_success_median_s"])
                    for name in names]  # KeyError = data drift; fail loudly
    return out


def _group_values(rows: list[dict], arm: str, stratum: str,
                  key: str) -> np.ndarray:
    return np.array([r[key] for r in rows
                     if r["arm"] == arm and r["stratum"] == stratum],
                    dtype=float)


def _stylize_strata_axis(ax) -> None:
    ax.set_xticks(GROUP_X, ["fast", "slow", "fast", "slow"])
    for label, (arm, _stratum) in zip(ax.get_xticklabels(), GROUPS):
        label.set_color(COL_ARM[arm])
    transform = ax.get_xaxis_transform()
    ax.text(0.5, -0.115, "direct lifecycle", transform=transform, ha="center",
            va="top", fontsize=9.5, color=COL_ARM["direct"])
    ax.text(3.5, -0.115, "periodic discovery", transform=transform,
            ha="center", va="top", fontsize=9.5, color=COL_ARM["discovery"])
    ax.grid(axis="y", alpha=0.25, linestyle="--")


def panel_intervals_b(ax, rows: list[dict], letter: str = "(b)") -> None:
    """Provisioning -> first successful response, per backend."""
    for x, (arm, stratum) in zip(GROUP_X, GROUPS):
        values = _group_values(rows, arm, stratum, "first_s")
        median = float(np.median(values))
        ax.bar(x, median, 0.55, color=COL_ARM[arm], alpha=0.8,
               edgecolor="white", zorder=2)
        ax.errorbar(x, median,
                    yerr=[[median - values.min()], [values.max() - median]],
                    fmt="none", ecolor="#333", capsize=3, lw=1.2, zorder=3)
        jitter = RNG.uniform(-0.15, 0.15, len(values))
        ax.scatter(x + jitter, values, s=14, color="black", alpha=0.75,
                   linewidths=0, zorder=4)
        ax.text(x, values.max() + 0.8, f"{median:.1f}", ha="center",
                fontsize=9.5)
    ax.set_ylim(0, 25)
    ax.set_ylabel("provisioning \u2192 first success (s)")
    _stylize_strata_axis(ax)
    ax.text(-0.18, 1.05, letter, transform=ax.transAxes, fontweight="bold",
            fontsize=11)


def panel_intervals_c(ax, probes: dict[str, list[float]],
                      letter: str = "(c)") -> None:
    """Scaling decision -> usable capacity, per run (rate-12 cell)."""
    for x, arm in enumerate(("direct", "discovery")):
        values = np.array(probes[arm], dtype=float)
        median = float(np.median(values))
        ax.bar(x, median, 0.5, color=COL_ARM[arm], alpha=0.8,
               edgecolor="white", zorder=2)
        ax.errorbar(x, median,
                    yerr=[[median - values.min()], [values.max() - median]],
                    fmt="none", ecolor="#333", capsize=3, lw=1.2, zorder=3)
        jitter = RNG.uniform(-0.09, 0.09, len(values))
        ax.scatter(x + jitter, values, s=28, color="black", alpha=0.85,
                   linewidths=0, zorder=4)
        ax.text(x, values.max() + 0.35, f"{median:.2f}", ha="center",
                fontsize=9.5)
    ax.set_xticks([0, 1], ["direct\nlifecycle", "periodic\ndiscovery"])
    for label, arm in zip(ax.get_xticklabels(), ("direct", "discovery")):
        label.set_color(COL_ARM[arm])
    ax.set_ylim(0, 9.5)
    ax.set_ylabel("scaling decision \u2192 usable capacity (s)")
    ax.grid(axis="y", alpha=0.25, linestyle="--")
    ax.text(-0.20, 1.05, letter, transform=ax.transAxes, fontweight="bold",
            fontsize=11)


def interval_figure() -> None:
    """Intact-source admission-chain intervals (two panels, v2)."""
    rows = load_stratified()
    probes = load_cell12()
    fig, axes = plt.subplots(1, 2, figsize=(8.8, 4.4))
    panel_intervals_b(axes[0], rows, letter="(a)")
    panel_intervals_c(axes[1], probes, letter="(b)")
    fig.tight_layout()
    out = OUT_V2 / "rq3_admission_intervals_v2.png"
    fig.savefig(out)
    plt.close(fig)
    shutil.copyfile(out, ROOT / "tese/images/rq3_admission_intervals_v2.png")
    print(f"wrote {out} and tese/images/rq3_admission_intervals_v2.png")
    for arm, stratum in GROUPS:
        first = _group_values(rows, arm, stratum, "first_s")
        print(f"  {arm}/{stratum}: n={len(first)} "
              f"first_s med={np.median(first):.3f}")
    for arm, values in probes.items():
        print(f"  scale->usable {arm}: n={len(values)} "
              f"med={np.median(values):.2f} "
              f"range={min(values):.2f}-{max(values):.2f}")


def ordering_figure() -> None:
    """Provisioning -> admission under event loss, per seed block."""
    with open(REANCHORED_JSON, encoding="utf-8") as fh:
        payload = json.load(fh)
    blocks = payload["blocks"]
    fig, ax = plt.subplots(figsize=(6.9, 4.0))
    for entry in blocks:
        b = entry["block"]
        hy = entry["hybrid"]["spawn_to_admit_s"]
        rc = entry["reconcile"]["spawn_to_admit_s"]
        ax.plot([b, b], [rc, hy], color="#a8a8a8", lw=1.4, zorder=1)
    ax.scatter([e["block"] for e in blocks],
               [e["hybrid"]["spawn_to_admit_s"] for e in blocks],
               s=62, color=COL_ARM["fallback"], edgecolor="white",
               zorder=3, label="probe fallback variant")
    ax.scatter([e["block"] for e in blocks],
               [e["reconcile"]["spawn_to_admit_s"] for e in blocks],
               s=62, color=COL_ARM["discovery"], edgecolor="white",
               zorder=3, label="periodic discovery")
    ax.set_xticks(range(1, 7), ["b1", "b2", "b3", r"b4$^{*}$", "b5", "b6"])
    ax.set_xlabel("seed block")
    ax.set_ylabel("provisioning \u2192 admission (s)")
    ax.set_ylim(0, 26)
    ax.grid(axis="y", alpha=0.25, linestyle="--")
    ax.legend(loc="upper left", frameon=False)
    fig.tight_layout()
    out = OUT / "rq3_recovery_ordering.png"
    fig.savefig(out)
    plt.close(fig)
    print(f"wrote {out}")
    hy = [e["hybrid"]["spawn_to_admit_s"] for e in blocks]
    rc = [e["reconcile"]["spawn_to_admit_s"] for e in blocks]
    print(f"  hybrid {hy} med={np.median(hy):.2f}")
    print(f"  reconcile {rc} med={np.median(rc):.2f}")
    print(f"  reconcile faster: {sum(r < h for r, h in zip(rc, hy))}/6")


def event_loss_figure(data: dict) -> None:
    """Fault consequence: slow share over time + admitted backends per run."""
    fig, (axa, axb) = plt.subplots(
        1, 2, figsize=(11, 4.4), gridspec_kw={"width_ratios": [1.55, 1]})
    panel_a(axa, data)
    panel_b(axb, data)
    fig.tight_layout()
    out = OUT / "rq3_event_loss_outcome.png"
    fig.savefig(out)
    plt.close(fig)
    print(f"wrote {out}")

    for arm in ("event_only", "hybrid", "reconcile"):
        admitted = [data[f"b{b}_loss_all_{arm}"]["admissions"]["admitted"]
                    for b in BLOCKS]
        abandoned = [data[f"b{b}_loss_all_{arm}"]["admissions"]["abandoned"]
                     for b in BLOCKS]
        print(f"  {arm}: admitted {admitted}  abandoned {abandoned}")


def soundness_figure() -> None:
    """Timing-lie grid: episode damage against the claim lead (single panel).

    v2 (2026-10-05): the two-panel v1 included the retired false-claim
    family; the thesis now reports the timing grid only.
    """
    damage = json.loads(SND_DAMAGE.read_text(encoding="utf-8"))
    cross = json.loads(SND_CROSS.read_text(encoding="utf-8"))
    medians = damage["medians"]

    def seed_values(arm: str, cell: str) -> list[float]:
        record = medians.get(f"{arm}|{cell}")
        if record is None:
            return []
        return [record["seeds_ok"][s] for s in sorted(record["seeds_ok"])]

    fig, ax = plt.subplots(figsize=(6.4, 4.2))

    leads = [2, 5, 10]
    for arm in ("event_only", "hybrid", "reconcile"):
        meds = [medians[f"{arm}|premature{n}"]["d_bar_pp"] for n in leads]
        ax.plot(leads, meds, color=COLORS[arm], lw=1.9, marker="o", ms=5,
                label=LABELS[arm])
        for n in leads:
            for value in seed_values(arm, f"premature{n}"):
                ax.scatter(n + RNG.uniform(-0.09, 0.09), value, s=20,
                           color="black", alpha=0.8, linewidths=0, zorder=4)
    wk = medians["wake_verify|premature10"]
    ax.scatter([10], [wk["d_bar_pp"]], s=36, color=COL_SND["wake_verify"],
               zorder=5, label=LABELS_SND["wake_verify"])
    for value in seed_values("wake_verify", "premature10"):
        ax.scatter(10 + RNG.uniform(-0.09, 0.09), value, s=20,
                   color="black", alpha=0.8, linewidths=0, zorder=4)
    ax.axhline(0, color="#888", lw=0.9, zorder=1)
    ax.set_xticks(leads, ["2", "5", "10"])
    ax.set_xlabel("claim lead (s)")
    ax.set_ylabel("episode damage (pp)")
    ax.set_ylim(-13, 18.5)
    ax.grid(axis="y", alpha=0.25, linestyle="--")
    ax.legend(loc="upper left", frameon=False)

    fig.tight_layout()
    out = OUT_SND / "rq3_soundness_damage_v2.png"
    fig.savefig(out)
    plt.close(fig)
    shutil.copyfile(out, ROOT / "tese/images/rq3_soundness_damage_v2.png")
    print(f"wrote {out} and tese/images/rq3_soundness_damage_v2.png")
    print(f"  band: {cross['crossover']['band']} "
          f"n*={cross['crossover']['n_star']} "
          f"gate_pass={cross['growth']['gate_pass']}")


def main() -> None:
    event_loss_figure(load())
    interval_figure()
    ordering_figure()
    soundness_figure()


if __name__ == "__main__":
    main()
