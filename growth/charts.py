"""Static charts for the README and memo (matplotlib, light theme).

Colors follow one fixed categorical order (blue, orange, aqua), checked for
color-vision deficiency; every chart with two or more series has a legend and
direct labels, and every number plotted is also in a CSV under reports/tables/.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

SERIES = ["#257de0", "#f47230", "#00b894"]
INK = "#191919"
INK_2 = "#666666"
GRID = "#e7e7e7"
AXIS = "#c2c2c2"
SURFACE = "#ffffff"
BLUE_RAMP = ["#cce3fd", "#9dc8f7", "#6aabf1", "#338ced", "#2370cd", "#1757ac", "#0e3d7e"]

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 10,
        "axes.edgecolor": AXIS,
        "axes.labelcolor": INK_2,
        "axes.titlecolor": INK,
        "axes.titlesize": 12,
        "axes.titleweight": "bold",
        "axes.titlelocation": "left",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "axes.grid.axis": "y",
        "axes.axisbelow": True,
        "grid.color": GRID,
        "grid.linewidth": 0.8,
        "grid.linestyle": "-",
        "xtick.color": INK_2,
        "ytick.color": INK_2,
        "xtick.labelcolor": INK_2,
        "ytick.labelcolor": INK_2,
        "legend.frameon": False,
        "legend.labelcolor": INK_2,
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "savefig.dpi": 160,
        "lines.linewidth": 2,
        "lines.solid_capstyle": "round",
        "lines.solid_joinstyle": "round",
    }
)


def _thousands(ax, axis="y", compact=None, absolute=False):
    """Full numbers under 10,000; compact (5K, 10K) on an axis that reaches 10,000."""
    a = ax.yaxis if axis == "y" else ax.xaxis
    lo, hi = ax.get_ylim() if axis == "y" else ax.get_xlim()
    if compact is None:
        compact = max(abs(lo), abs(hi)) >= 10000

    def f(v, _):
        v = abs(v) if absolute else v
        if compact:
            return "0" if v == 0 else f"{v / 1000:g}K"
        return f"{v:,.0f}"

    a.set_major_formatter(matplotlib.ticker.FuncFormatter(f))


def _pct(ax, axis="y", decimals=0):
    fmt = matplotlib.ticker.FuncFormatter(lambda v, _: f"{v * 100:.{decimals}f}%")
    (ax.yaxis if axis == "y" else ax.xaxis).set_major_formatter(fmt)


def _subtitle(ax, text):
    ax.text(0, 1.02, text, transform=ax.transAxes, color=INK_2, fontsize=9, va="bottom")


def _save(fig, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def dau_history(daily, events, path):
    """Seven-day average DAU over the whole window, with launches marked."""
    d = daily.set_index("date")["dau_adj"].where(~daily.set_index("date")["low_coverage"])
    smooth = d.rolling(7, min_periods=4).mean()
    fig, ax = plt.subplots(figsize=(9, 3.6))
    ax.plot(smooth.index, smooth.to_numpy(), color=SERIES[0])
    top = np.nanmax(smooth.to_numpy())
    for date, label in events:
        ax.axvline(date, color=AXIS, linewidth=1, zorder=0)
        ax.text(date, top * 1.04, f" {label}", color=INK_2, fontsize=9, va="bottom")
    ax.set_ylim(0, top * 1.18)
    _thousands(ax)
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.set_title("Daily active avatars, 7-day average", pad=22)
    _subtitle(ax, "Light's Hope realm (Taiwan), Horde. Days with under half the snapshots left out.")
    return _save(fig, path)


def growth_accounting(ga, path):
    """Monthly gross adds (new, resurrected) above zero and churned below."""
    x = np.arange(len(ga))
    w = 0.7
    fig, ax = plt.subplots(figsize=(9, 3.8))
    gap = 0.0
    ax.bar(x, ga["new"], width=w, color=SERIES[0], label="New", linewidth=0)
    ax.bar(
        x,
        ga["resurrected"],
        width=w,
        bottom=ga["new"] + gap,
        color=SERIES[1],
        label="Returning",
        linewidth=0,
        edgecolor=SURFACE,
    )
    ax.bar(x, -ga["churned"], width=w, color=SERIES[2], label="Churned", linewidth=0)
    # 2px surface gap between stacked segments
    ax.bar(x, np.zeros(len(x)) + ga["new"].max() * 0.004, bottom=ga["new"], width=w, color=SURFACE, linewidth=0)
    ax.axhline(0, color=AXIS, linewidth=1)
    labels = [m.strftime("%b\n%Y") if m.month in (1, 7) else "" for m in ga["month_start"]]
    ax.set_xticks(x, labels)
    ax.tick_params(axis="x", length=0)
    top = (ga["new"] + ga["resurrected"]).max()
    ax.set_ylim(-ga["churned"].max() * 1.08, top * 1.3)
    _thousands(ax, absolute=True)
    ax.legend(loc="upper left", ncol=3, bbox_to_anchor=(0, 1.0))
    ax.set_title("Where monthly active avatars came from", pad=22)
    _subtitle(ax, "Avatars gained each month (above zero) and lost (below zero).")
    return _save(fig, path)


def launch_panels(results, path):
    """Actual vs counterfactual DAU around each launch, one panel per launch."""
    fig, axes = plt.subplots(1, len(results), figsize=(9.5, 3.8), sharey=False)
    axes = np.atleast_1d(axes)
    for ax, (name, r) in zip(axes, results.items(), strict=True):
        s = r["series"].sort_values("date").set_index("date")
        full = pd.date_range(s.index.min(), s.index.max(), freq="D")
        s = s.reindex(full)  # days left out of the fit become gaps
        post = s.index >= r["launch"]
        days = (s.index - r["launch"]).days
        # Post-launch days that were not scored (low coverage) are not drawn.
        act = s["actual"].where(~post | s["scored"].fillna(False).astype(bool))
        act_s = act.rolling(7, min_periods=5, center=True).mean()
        # Before launch the expected line is the model's in-sample fit.
        cf_s = s["counterfactual"].rolling(7, min_periods=5, center=True).mean()
        ax.plot(days, act_s, color=SERIES[0], label="Actual DAU")
        ax.plot(days, cf_s, color=SERIES[1], label="Expected without the launch")
        ax.axvline(0, color=AXIS, linewidth=1, zorder=0)
        ax.set_title(f"{name}: +{r['lift'] * 100:.0f}% over {r['post_days'] // 7} weeks", fontsize=11, pad=8)
        ax.set_xlabel("Days from launch")
        ax.set_ylim(0, np.nanmax(act_s.to_numpy()) * 1.15)
        _thousands(ax)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper left", ncol=2, bbox_to_anchor=(0.01, 0.93), fontsize=9)
    fig.suptitle(
        "DAU after each expansion launch vs. a pre-launch trend",
        x=0.01,
        ha="left",
        fontsize=12,
        fontweight="bold",
        color=INK,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.86))
    return _save(fig, path)


def cohort_heatmap(cr, path, max_k=12):
    """Monthly cohorts x months since first seen, share still active."""
    piv = cr.loc[cr["k"].between(1, max_k)].pivot(index="cohort_start", columns="k", values="share_active")
    cmap = LinearSegmentedColormap.from_list("blue", BLUE_RAMP)
    fig, ax = plt.subplots(figsize=(8, 6))
    im = ax.imshow(piv.to_numpy(), aspect="auto", cmap=cmap, vmin=0, vmax=np.nanpercentile(piv.to_numpy(), 99))
    ax.set_xticks(range(len(piv.columns)), [str(k) for k in piv.columns])
    ys = list(range(0, len(piv.index), 3))
    ax.set_yticks(ys, [piv.index[i].strftime("%b %Y") for i in ys])
    ax.grid(False)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_xlabel("Months since first seen")
    cb = fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02)
    cb.ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v * 100:.0f}%"))
    cb.outline.set_visible(False)
    cb.ax.tick_params(colors=INK_2)
    ax.set_title("Share of each monthly cohort of new avatars still active", pad=22)
    _subtitle(ax, "New avatars only (first seen at level 10 or below, after March 2006).")
    return _save(fig, path)


def aha_bars(features, path, threshold):
    """Day-90 retention by active days in the first week."""
    g = features.groupby("active_days_w1")["retained_d90"].agg(["mean", "size"]).reset_index()
    fig, ax = plt.subplots(figsize=(7, 3.6))
    ax.bar(g["active_days_w1"], g["mean"], width=0.55, color=SERIES[0], linewidth=0)
    for _, row in g.iterrows():
        if row["active_days_w1"] in (1, threshold, g["active_days_w1"].max()):
            ax.text(
                row["active_days_w1"],
                row["mean"] + 0.012,
                f"{row['mean'] * 100:.0f}%",
                ha="center",
                color=INK,
                fontsize=9,
            )
    ax.set_xticks(g["active_days_w1"])
    ax.tick_params(axis="x", length=0)
    _pct(ax)
    ax.set_xlabel("Days active in the first 7 days")
    ax.set_ylim(0, g["mean"].max() * 1.18)
    ax.set_title("Day-90 retention by first-week activity", pad=22)
    _subtitle(ax, "Share of new avatars active on any of days 90-119.")
    return _save(fig, path)


def guild_estimates(res, path):
    """Naive, matched and IPW estimates of the guild effect."""
    rows = [
        ("Naive difference", res["naive_rd"], None),
        ("Matched (1:1)", res["match_rd"], None),
        ("Weighted (IPW)", res["ipw_rd"], res["ipw_rd_ci"]),
    ]
    fig, ax = plt.subplots(figsize=(7, 2.6))
    for i, (_label, est, ci) in enumerate(rows):
        if ci:
            ax.plot(ci, [i, i], color=SERIES[0], linewidth=2)
        ax.plot([est], [i], "o", color=SERIES[0], markersize=8, markeredgecolor=SURFACE, markeredgewidth=2)
        ax.text(est, i + 0.22, f"+{est * 100:.1f} pts", ha="center", color=INK, fontsize=9)
    ax.axvline(0, color=AXIS, linewidth=1)
    ax.set_yticks(range(len(rows)), [r[0] for r in rows])
    ax.set_ylim(-0.6, len(rows) - 0.3)
    ax.grid(axis="x")
    ax.grid(axis="y", visible=False)
    _pct(ax, "x")
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v * 100:+.0f} pts"))
    ax.set_xlim(min(0, min(r[1] for r in rows)) - 0.02, max(res["ipw_rd_ci"][1], res["naive_rd"]) + 0.03)
    ax.set_title("Effect of joining a guild in days 7-13 on day-90 retention", pad=22)
    _subtitle(ax, "Line shows the 95% bootstrap interval for the weighted estimate.")
    return _save(fig, path)


def power_curves(sd_raw, sd_cuped, mean_y, path, n_max=40000):
    """Minimum detectable effect by sample size, with and without CUPED."""
    from experiments.design import mde_mean

    n = np.linspace(1000, n_max, 80)
    raw = np.array([mde_mean(sd_raw, k) for k in n]) / mean_y
    cup = np.array([mde_mean(sd_cuped, k) for k in n]) / mean_y
    fig, ax = plt.subplots(figsize=(7, 3.6))
    ax.plot(n, raw, color=SERIES[1], label="Without CUPED")
    ax.plot(n, cup, color=SERIES[0], label="With CUPED")
    ax.annotate(
        "Without CUPED",
        (n[-1], raw[-1]),
        xytext=(-4, 8),
        textcoords="offset points",
        ha="right",
        color=INK_2,
        fontsize=8,
    )
    ax.annotate(
        "With CUPED",
        (n[-1], cup[-1]),
        xytext=(-4, -12),
        textcoords="offset points",
        ha="right",
        color=INK_2,
        fontsize=8,
    )
    _pct(ax)
    ax.set_xlim(0, n_max * 1.02)
    _thousands(ax, "x", compact=True)
    ax.set_xlabel("Players per arm")
    ax.set_ylim(0, raw[0] * 1.05)
    ax.legend(loc="upper right")
    ax.set_title("Smallest lift in active days the test can detect", pad=22)
    _subtitle(ax, "80% power, 5% two-sided. Variance from real at-risk players.")
    return _save(fig, path)
