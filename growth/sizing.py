"""Opportunity sizing: what +1 point of D30 retention is worth in DAU.

Logic: each day N new avatars arrive. Raising D30 retention by one point keeps
0.01 x N more of each day's arrivals past day 30. Each of those extra players
then plays like a typical D30-retained avatar: active on day k with probability
a(k). Extra DAU on day H is the sum over cohorts c <= H of 0.01 x N x a(H - c),
counting only ages of 30 days and up (any extra play before day 30 is ignored,
so the estimate is conservative).

The baseline DAU comes from the teammate's forecast (reports/dau_forecast.csv,
columns date and dau_forecast) when it exists, otherwise from the average DAU of
the last 8 weeks of data.
"""

from pathlib import Path

import numpy as np
import pandas as pd

from growth.metrics import new_avatars, retention_flags

HORIZON_DAYS = 182
BASELINE_DAYS = 56


def activity_curve_retained(pday, cohort, max_day, retained_ids):
    """a(k): share of D30-retained avatars active on day k after first seen."""
    c = cohort.loc[cohort["player_id"].isin(retained_ids), ["player_id", "first_day"]]
    d = pday.loc[pday["player_id"].isin(c["player_id"]), ["player_id", "date"]].merge(c, on="player_id")
    age = ((d["date"] - d["first_day"]) / pd.Timedelta(days=1)).astype(int)
    counts = age[age <= max_day].value_counts().reindex(range(max_day + 1), fill_value=0)
    return counts.to_numpy() / len(c)


def incremental_dau(new_per_day, curve, points=1.0, horizon=HORIZON_DAYS, start_age=30):
    """Extra DAU on each day 0..horizon from a `points`-point D30 lift."""
    a = np.asarray(curve, dtype=float).copy()
    a[:start_age] = 0.0
    extra = np.zeros(horizon + 1)
    for h in range(horizon + 1):
        ages = np.arange(h + 1)
        extra[h] = (points / 100) * new_per_day * a[ages].sum()
    return extra


def baseline_dau(daily, forecast_path="reports/dau_forecast.csv", days=BASELINE_DAYS):
    path = Path(forecast_path)
    if path.exists():
        f = pd.read_csv(path, parse_dates=["date"])
        return float(f["dau_forecast"].mean()), "teammate forecast"
    d = daily.loc[~daily["low_coverage"]].tail(days)
    return float(d["dau_adj"].mean()), f"average DAU of the last {days} days"


def size_d30_lift(pday, avatars, daily, points=1.0, horizon=HORIZON_DAYS, forecast_path="reports/dau_forecast.csv"):
    end = pday["date"].max()
    # Cohorts old enough to observe the whole horizon.
    full = new_avatars(avatars, end - pd.Timedelta(days=horizon + 1))
    flags = retention_flags(pday, full)
    retained = flags.loc[flags["d30"], "player_id"]
    curve = activity_curve_retained(pday, full, horizon, retained)
    recent = new_avatars(avatars, end, start=end - pd.Timedelta(days=BASELINE_DAYS - 1))
    new_per_day = len(recent) / BASELINE_DAYS
    extra = incremental_dau(new_per_day, curve, points, horizon)
    base, source = baseline_dau(daily, forecast_path)
    return {
        "points": points,
        "new_avatars_per_day": float(new_per_day),
        "d30_retention": float(flags["d30"].mean()),
        "extra_dau_at_horizon": float(extra[-1]),
        "extra_dau_avg_over_horizon": float(extra.mean()),
        "extra_player_days_over_horizon": float(extra.sum()),
        "baseline_dau": base,
        "baseline_source": source,
        "extra_dau_share_at_horizon": float(extra[-1] / base),
        "curve": curve,
        "extra_by_day": extra,
    }
