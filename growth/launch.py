"""Q2: how much each expansion launch lifted DAU, and whether the players it
brought back stayed.

The main estimate is a counterfactual: fit log DAU on a trend and day-of-week
effects over the weeks before launch, project it over the weeks after, and
compare. A moving-block bootstrap gives the interval. Three checks back it up:
the same estimator at placebo dates with no launch, other pre-period windows,
and a year-over-year comparison of the same calendar weeks.
"""

import numpy as np
import pandas as pd

# Lunar New Year (Taiwan's biggest holiday) falls in some pre-launch windows.
LUNAR_NEW_YEAR = [pd.Timestamp(d) for d in ["2006-01-29", "2007-02-18", "2008-02-07", "2009-01-26"]]
LNY_DAYS = (-1, 6)  # from New Year's Eve to the 6th day


def detect_launch_dates(pday):
    """Launch day of each expansion, read from the data.

    The Burning Crusade raised the level cap from 60 to 70 and Wrath of the Lich
    King from 70 to 80, so the first day any avatar is above the old cap is the
    day the expansion went live on this realm.
    """
    first_above = {}
    for name, cap in [("tbc", 60), ("wotlk", 70)]:
        first_above[name] = pday.loc[pday["max_level"] > cap, "date"].min()
    return first_above


def _design(dates, origin, trend=True):
    dates = pd.DatetimeIndex(dates)
    cols = [np.ones(len(dates))]
    names = ["const"]
    if trend:
        cols.append(((dates - origin) / pd.Timedelta(days=1)).to_numpy() / 7.0)
        names.append("trend_per_week")
    for k in range(1, 7):
        cols.append((dates.dayofweek == k).astype(float))
        names.append(f"dow_{k}")
    lny = np.zeros(len(dates))
    for d in LUNAR_NEW_YEAR:
        off = ((dates - d) / pd.Timedelta(days=1)).to_numpy()
        lny += (off >= LNY_DAYS[0]) & (off <= LNY_DAYS[1])
    cols.append(np.minimum(lny, 1))
    names.append("lunar_new_year")
    X = np.column_stack(cols)
    return X, names


def _ols(X, y):
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    return beta


def _block_resample(resid, n, block, rng):
    if len(resid) <= block:
        return rng.choice(resid, size=n, replace=True)
    starts = rng.integers(0, len(resid) - block + 1, size=n // block + 1)
    out = np.concatenate([resid[s : s + block] for s in starts])
    return out[:n]


def counterfactual_lift(
    daily,
    launch,
    pre_days=84,
    post_days=56,
    value="dau_adj",
    trend=True,
    n_boot=2000,
    block=7,
    seed=0,
    exclude=None,
):
    """Lift in DAU over the post window versus a pre-period counterfactual.

    `daily` needs date, `value` and low_coverage columns. Low-coverage days are
    left out of both fitting and scoring, as are days inside any (start, end)
    period in `exclude` (known anomalies such as the level-1 avatar wave). Returns a dict with the lift (ratio of
    total actual to total counterfactual player-days, minus 1), its bootstrap
    interval, the extra player-days, and a day-by-day frame for charts.
    """
    launch = pd.Timestamp(launch)
    d = daily.set_index("date")
    pre = d.loc[launch - pd.Timedelta(days=pre_days) : launch - pd.Timedelta(days=1)]
    post = d.loc[launch : launch + pd.Timedelta(days=post_days - 1)]

    def drop_excluded(frame):
        bad = np.zeros(len(frame), dtype=bool)
        for s_, e_ in exclude or []:
            bad |= (frame.index >= pd.Timestamp(s_)) & (frame.index <= pd.Timestamp(e_))
        return frame.loc[~bad]

    pre = drop_excluded(pre.loc[~pre["low_coverage"] & (pre[value] > 0)])
    post_ok = drop_excluded(post.loc[~post["low_coverage"] & (post[value] > 0)])
    origin = launch
    Xp, names = _design(pre.index, origin, trend)
    keep = Xp.std(axis=0) > 0
    keep[0] = True
    Xp = Xp[:, keep]
    yp = np.log(pre[value].to_numpy(dtype=float))
    beta = _ols(Xp, yp)
    resid = yp - Xp @ beta
    smear = np.mean(np.exp(resid))
    Xq, _ = _design(post.index, origin, trend)
    Xq = Xq[:, keep]
    cf_all = np.exp(Xq @ beta) * smear
    ok = post.index.isin(post_ok.index)
    actual = post[value].to_numpy(dtype=float)
    lift = actual[ok].sum() / cf_all[ok].sum() - 1

    rng = np.random.default_rng(seed)
    boots = np.empty(n_boot)
    fitted = Xp @ beta
    Xq_ok = Xq[ok]
    for b in range(n_boot):
        y_star = fitted + _block_resample(resid, len(resid), block, rng)
        b_star = _ols(Xp, y_star)
        e_post = _block_resample(resid, ok.sum(), block, rng)
        cf_star = np.exp(Xq_ok @ b_star + e_post)
        boots[b] = actual[ok].sum() / cf_star.sum() - 1
    lo, hi = np.percentile(boots, [2.5, 97.5]) if n_boot else (np.nan, np.nan)

    frame = pd.DataFrame(
        {
            "date": post.index,
            "actual": actual,
            "counterfactual": cf_all,
            "scored": ok,
        }
    )
    pre_frame = pd.DataFrame(
        {
            "date": pre.index,
            "actual": pre[value].to_numpy(dtype=float),
            "counterfactual": np.exp(fitted) * smear,
            "scored": False,
        }
    )
    return {
        "launch": launch,
        "pre_days": pre_days,
        "post_days": post_days,
        "trend": trend,
        "lift": float(lift),
        "ci_low": float(lo),
        "ci_high": float(hi),
        "extra_player_days": float(actual[ok].sum() - cf_all[ok].sum()),
        "counterfactual_dau": float(cf_all[ok].mean()),
        "actual_dau": float(actual[ok].mean()),
        "pre_r2": float(1 - resid.var() / yp.var()),
        "coef": dict(zip([n for n, k in zip(names, keep, strict=True) if k], beta.round(5), strict=True)),
        "series": pd.concat([pre_frame, frame], ignore_index=True),
    }


def weekly_lift(result):
    """Lift by week since launch, from a counterfactual_lift result."""
    s = result["series"]
    s = s.loc[s["scored"]].copy()
    s["week"] = ((s["date"] - result["launch"]) / pd.Timedelta(days=7)).astype(int) + 1
    w = s.groupby("week")[["actual", "counterfactual"]].sum()
    w["lift"] = w["actual"] / w["counterfactual"] - 1
    return w.reset_index()


def placebo_lifts(daily, candidates, blackout, **kwargs):
    """Run the estimator at dates with no launch.

    `blackout` is a list of (start, end) periods that the pre or post window of a
    placebo date must not touch (launches and other known events).
    """
    pre_days = kwargs.get("pre_days", 84)
    post_days = kwargs.get("post_days", 56)
    out = []
    lo_date, hi_date = daily["date"].min(), daily["date"].max()
    for c in candidates:
        c = pd.Timestamp(c)
        a, b = c - pd.Timedelta(days=pre_days), c + pd.Timedelta(days=post_days)
        if a < lo_date or b > hi_date:
            continue
        if any(not (b <= pd.Timestamp(s) or a >= pd.Timestamp(e)) for s, e in blackout):
            continue
        kw = dict(kwargs, n_boot=0)
        out.append({"placebo_date": c, "lift": counterfactual_lift(daily, c, **kw)["lift"]})
    return pd.DataFrame(out)


def yoy_lift(daily, launch, compare_years, pre_days=28, post_days=56, value="dau_adj"):
    """Year-over-year check: post/pre change around launch versus the same
    calendar days in other years. Returns the lift and the per-year ratios."""
    d = daily.set_index("date")

    def ratio(anchor):
        pre = d.loc[anchor - pd.Timedelta(days=pre_days) : anchor - pd.Timedelta(days=1)]
        post = d.loc[anchor : anchor + pd.Timedelta(days=post_days - 1)]
        pre = pre.loc[~pre["low_coverage"], value]
        post = post.loc[~post["low_coverage"], value]
        return post.mean() / pre.mean()

    launch = pd.Timestamp(launch)
    r_launch = ratio(launch)
    others = {}
    for y in compare_years:
        anchor = launch + pd.DateOffset(years=y - launch.year)
        others[y] = ratio(pd.Timestamp(anchor))
    base = float(np.mean(list(others.values())))
    return {"lift": float(r_launch / base - 1), "launch_ratio": float(r_launch), "compare_ratios": others}


def launch_cohorts(pday, launch, entry_days=14, lapse_days=30, later=(30, 44), exclude_ids=None):
    """Who showed up in the first two weeks after a date, and who was still there later.

    Segments (by activity before the date):
      new: first seen on or after the date
      reactivated: seen before, but not in the `lapse_days` before the date
      already active: seen in the `lapse_days` before the date
    "Still active" means active on any day in [date + later[0], date + later[1]).
    IDs in `exclude_ids` (shared by two characters) are left out.
    """
    L = pd.Timestamp(launch)
    p = pday[["player_id", "date"]]
    if exclude_ids is not None:
        p = p.loc[~p["player_id"].isin(exclude_ids)]
    entry = p.loc[(p["date"] >= L) & (p["date"] < L + pd.Timedelta(days=entry_days)), "player_id"].unique()
    before = p.loc[p["date"] < L]
    ever_before = set(before["player_id"].unique())
    recent = set(before.loc[before["date"] >= L - pd.Timedelta(days=lapse_days), "player_id"].unique())
    seg = pd.Series(
        np.where(
            ~pd.Series(entry).isin(ever_before),
            "new",
            np.where(pd.Series(entry).isin(recent), "already active", "reactivated"),
        ),
        index=entry,
        name="segment",
    )
    later_ids = set(
        p.loc[
            (p["date"] >= L + pd.Timedelta(days=later[0])) & (p["date"] < L + pd.Timedelta(days=later[1])),
            "player_id",
        ].unique()
    )
    df = seg.rename_axis("player_id").reset_index()
    df["still_active"] = df["player_id"].isin(later_ids)
    summary = df.groupby("segment").agg(players=("player_id", "size"), still_active=("still_active", "mean"))
    summary["share_of_entrants"] = summary["players"] / summary["players"].sum()
    return df, summary.reset_index()


def segment_days(pday, launch, segments, days=56):
    """Player-days in the post window by segment (from launch_cohorts)."""
    L = pd.Timestamp(launch)
    p = pday.loc[(pday["date"] >= L) & (pday["date"] < L + pd.Timedelta(days=days)), ["player_id", "date"]]
    p = p.merge(segments[["player_id", "segment"]], on="player_id", how="left")
    p["segment"] = p["segment"].fillna("joined after week 2")
    return p.groupby("segment").size().rename("player_days").reset_index()
