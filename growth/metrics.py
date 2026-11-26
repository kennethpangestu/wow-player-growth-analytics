"""Q1: active players, stickiness, growth accounting and retention.

Definitions live in docs/metrics.md. Inputs are the player-day table
(one row per avatar per active day) and the daily coverage table.
"""

import numpy as np
import pandas as pd

# Calendar days with fewer than half of the expected sweeps undercount DAU;
# they are flagged and left out of models and averages.
LOW_COVERAGE = 0.5

# Players already active when collection began look "new" in the first months.
# Growth accounting and new-player cohorts start after this burn-in.
BURN_IN_END = pd.Timestamp("2006-04-01")

# New-avatar rule: first seen after burn-in, starting at level 10 or below (rules
# out realm transfers), not a Death Knight (they start at level 55), and not an
# ID that looks shared by two characters (see data.reused_ids).
NEW_AVATAR_MAX_START_LEVEL = 10

RETENTION_WINDOWS = {"d1": (1, 2), "d7": (7, 14), "d30": (30, 60), "d90": (90, 120)}


def _day_index(dates, origin):
    return ((pd.to_datetime(dates) - origin) / pd.Timedelta(days=1)).astype("int64")


def rolling_distinct(pday, window, days):
    """Distinct avatars active in the trailing `window` days ending on each day.

    Each active day keeps an avatar counted for `window` days, unless the next
    active day already restarts the count. A difference array makes this exact
    and linear in the number of player-days.
    """
    origin = days[0]
    n = len(days)
    d = pday[["player_id", "date"]].sort_values(["player_id", "date"])
    di = _day_index(d["date"], origin).to_numpy()
    pid = d["player_id"].to_numpy()
    nxt = np.empty_like(di)
    nxt[:-1] = di[1:]
    nxt[-1] = np.iinfo(np.int64).max
    last = np.ones(len(di), dtype=bool)
    last[:-1] = pid[1:] != pid[:-1]
    nxt[last] = np.iinfo(np.int64).max
    stop = np.minimum(di + window, nxt)
    stop = np.minimum(stop, n)
    diff = np.zeros(n + 1, dtype=np.int64)
    np.add.at(diff, di, 1)
    np.add.at(diff, stop, -1)
    return np.cumsum(diff)[:n]


def daily_active(pday, coverage, slow_sampling_ratio=None):
    """DAU, WAU (7-day), MAU (28-day), stickiness and coverage per day.

    `slow_sampling_ratio` is the share of DAU that the slower (15-minute) schedule
    still catches, from data.thinning_ratio. On slow-sampling days `dau_adj`
    scales DAU up by its inverse so the series is comparable across schedules.
    """
    days = pd.DatetimeIndex(coverage["date"])
    dau = pday.groupby("date").size().reindex(days, fill_value=0)
    out = pd.DataFrame({"date": days, "dau": dau.to_numpy()})
    out["wau"] = rolling_distinct(pday, 7, days)
    out["mau"] = rolling_distinct(pday, 28, days)
    out["coverage"] = coverage["coverage"].to_numpy()
    slow = coverage["slow_sampling"].to_numpy() if "slow_sampling" in coverage else np.zeros(len(out), bool)
    out["slow_sampling"] = slow
    out["dau_adj"] = out["dau"].astype(float)
    if slow_sampling_ratio:
        out.loc[slow, "dau_adj"] = out.loc[slow, "dau"] / slow_sampling_ratio
    out["stickiness"] = out["dau_adj"] / out["mau"].replace(0, np.nan)
    out["low_coverage"] = out["coverage"] < LOW_COVERAGE
    minutes = pday.groupby("date")["minutes"].sum().reindex(days, fill_value=0)
    out["minutes_per_dau"] = minutes.to_numpy() / out["dau"].replace(0, np.nan)
    return out


def monthly_growth_accounting(pday, start=BURN_IN_END, end=None):
    """Monthly MAU split into new, retained and resurrected, plus churned.

    new: first active month ever. retained: also active last month.
    resurrected: active before, but not last month. churned: active last month,
    not this month. MAU = new + retained + resurrected, and
    MAU change = new + resurrected - churned. Months before `start` are used as
    history only; a final partial month should be cut with `end`.
    """
    pm = pday[["player_id"]].copy()
    pm["month"] = pday["date"].dt.to_period("M")
    pm = pm.drop_duplicates().sort_values(["player_id", "month"])
    m = pm["month"].astype("int64").to_numpy()  # months since 1970-01
    pid = pm["player_id"].to_numpy()
    same_prev = np.zeros(len(pm), dtype=bool)
    same_prev[1:] = pid[1:] == pid[:-1]
    prev = np.where(same_prev, np.concatenate([[0], m[:-1]]), -1)
    status = np.where(~same_prev, "new", np.where(prev == m - 1, "retained", "resurrected"))
    pm["status"] = status
    same_next = np.zeros(len(pm), dtype=bool)
    same_next[:-1] = pid[:-1] == pid[1:]
    nxt = np.where(same_next, np.concatenate([m[1:], [0]]), -1)
    churn_month = m[(nxt != m + 1)] + 1  # month in which the avatar is first missing
    counts = pm.groupby(["month", "status"]).size().unstack(fill_value=0)
    for col in ["new", "retained", "resurrected"]:
        if col not in counts:
            counts[col] = 0
    churn = pd.Series(churn_month).value_counts()
    churn.index = pd.PeriodIndex.from_ordinals(churn.index.to_numpy(), freq="M")
    out = counts[["new", "retained", "resurrected"]].copy()
    out["churned"] = churn.reindex(out.index, fill_value=0).to_numpy()
    out["mau"] = out[["new", "retained", "resurrected"]].sum(axis=1)
    out = out.reset_index().rename(columns={"index": "month"})
    out["month"] = out["month"].astype("period[M]")
    out["quick_ratio"] = (out["new"] + out["resurrected"]) / out["churned"].replace(0, np.nan)
    out["mau_change"] = out["new"] + out["resurrected"] - out["churned"]
    keep = out["month"] >= pd.Period(start, "M")
    if end is not None:
        keep &= out["month"] < pd.Period(end, "M")
    out = out.loc[keep].reset_index(drop=True)
    out["month_start"] = out["month"].dt.to_timestamp()
    return out


def change_decomposition(ga):
    """Share of the variance in monthly MAU change explained by each flow.

    MAU change = new + resurrected - churned, so
    var(change) = cov(change, new) + cov(change, resurrected) + cov(change, -churned),
    and the three shares add up to 1.
    """
    y = ga["mau_change"].astype(float)
    parts = {
        "new": ga["new"].astype(float),
        "resurrected": ga["resurrected"].astype(float),
        "churned": -ga["churned"].astype(float),
    }
    v = y.var()
    return {k: float(np.cov(y, x)[0, 1] / v) for k, x in parts.items()}


def new_avatars(avatars, end_date, start=BURN_IN_END):
    """Avatars that look genuinely new (see module constants)."""
    a = avatars
    keep = (
        (a["first_day"] >= start)
        & (a["first_level"] <= NEW_AVATAR_MAX_START_LEVEL)
        & (a["char_class"].astype("object") != "Death Knight")
        & (a["first_day"] <= end_date)
    )
    if "reused_id" in a:
        keep &= ~a["reused_id"].astype(bool)
    return a.loc[keep].copy()


def retention_flags(pday, cohort, windows=RETENTION_WINDOWS):
    """For each avatar in `cohort`, whether it was active in each retention window.

    A window (a, b) means active on at least one day in [first_day + a, first_day + b).
    """
    d = pday.loc[pday["player_id"].isin(cohort["player_id"]), ["player_id", "date"]]
    d = d.merge(cohort[["player_id", "first_day"]], on="player_id")
    age = ((d["date"] - d["first_day"]) / pd.Timedelta(days=1)).astype(int)
    out = cohort[["player_id", "first_day"]].copy().set_index("player_id")
    for name, (a, b) in windows.items():
        hit = d.loc[(age >= a) & (age < b), "player_id"].unique()
        out[name] = out.index.isin(hit)
    return out.reset_index()


def retention_curve(pday, cohort, max_day):
    """Share of the cohort active on each day since first seen (day 0 = 100%)."""
    d = pday.loc[pday["player_id"].isin(cohort["player_id"]), ["player_id", "date"]]
    d = d.merge(cohort[["player_id", "first_day"]], on="player_id")
    age = ((d["date"] - d["first_day"]) / pd.Timedelta(days=1)).astype(int)
    counts = age[age <= max_day].value_counts().reindex(range(max_day + 1), fill_value=0)
    return pd.DataFrame({"day": counts.index, "share_active": counts.to_numpy() / len(cohort)})


def monthly_cohort_retention(pday, cohort, last_month, max_months=24):
    """Long table: cohort month x months since start -> share of cohort active."""
    c = cohort[["player_id", "first_day"]].copy()
    c["cohort"] = c["first_day"].dt.to_period("M")
    pm = pday.loc[pday["player_id"].isin(c["player_id"]), ["player_id", "date"]].copy()
    pm["month"] = pm["date"].dt.to_period("M")
    pm = pm[["player_id", "month"]].drop_duplicates().merge(c[["player_id", "cohort"]], on="player_id")
    pm["k"] = (pm["month"].astype("int64") - pm["cohort"].astype("int64")).astype(int)
    last = pd.Period(last_month, "M")
    pm = pm.loc[(pm["k"] <= max_months) & (pm["month"] <= last)]
    active = pm.groupby(["cohort", "k"]).size().rename("active").reset_index()
    size = c.groupby("cohort").size().rename("cohort_size").reset_index()
    out = active.merge(size, on="cohort")
    out["share_active"] = out["active"] / out["cohort_size"]
    out["cohort_start"] = out["cohort"].dt.to_timestamp()
    return out.sort_values(["cohort", "k"]).reset_index(drop=True)
