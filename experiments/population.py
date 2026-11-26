"""Historical stand-in for the experiment population.

The feature targets players who are about to lapse and are not in a guild. Until
the churn model's scores (ml_churn_scores) exist, "at risk" is a simple proxy:
fewer active days in the last 14 days than in the 14 days before.

For each reference date r, every eligible player gets:
  pre_days   active days in [r - 28, r)        (CUPED covariate)
  pre_hours  hours played in [r - 28, r)       (second covariate)
  y_days     active days in [r, r + 28)        (primary metric)
  retained   active at all in [r + 14, r + 28) (secondary metric)
  daily      28 columns, active on day k of the test (for the peeking simulation)
"""

import numpy as np
import pandas as pd

TEST_DAYS = 28


def reference_dates(start, end, every_days, blackout):
    dates = pd.date_range(start, end, freq=f"{every_days}D")
    keep = []
    for r in dates:
        a, b = r - pd.Timedelta(days=TEST_DAYS), r + pd.Timedelta(days=TEST_DAYS)
        if any(not (b <= pd.Timestamp(s) or a >= pd.Timestamp(e)) for s, e in blackout):
            continue
        keep.append(r)
    return keep


def at_risk_population(pday, r, use_proxy=True):
    """Eligible players at reference date `r` with pre-period and outcome columns."""
    r = pd.Timestamp(r)
    p = pday.loc[
        (pday["date"] >= r - pd.Timedelta(days=TEST_DAYS)) & (pday["date"] < r + pd.Timedelta(days=TEST_DAYS)),
        ["player_id", "date", "minutes", "in_guild"],
    ]
    age = ((p["date"] - r) / pd.Timedelta(days=1)).astype(int)
    pre = p.loc[age < 0]
    last = pre.sort_values("date").groupby("player_id").tail(1).set_index("player_id")
    g = pre.groupby("player_id")
    df = pd.DataFrame(
        {
            "pre_days": g.size(),
            "pre_hours": g["minutes"].sum() / 60,
            "recent_days": pre.loc[age.loc[pre.index] >= -14].groupby("player_id").size(),
        }
    ).fillna(0)
    df["earlier_days"] = df["pre_days"] - df["recent_days"]
    df["in_guild_last"] = last["in_guild"].reindex(df.index).fillna(False).astype(bool)
    eligible = ~df["in_guild_last"]
    if use_proxy:
        eligible &= df["recent_days"] < df["earlier_days"]
    df = df.loc[eligible].copy()
    post = p.loc[(age >= 0) & p["player_id"].isin(df.index)]
    post_age = age.loc[post.index]
    df["y_days"] = post.groupby("player_id").size().reindex(df.index, fill_value=0)
    late = post.loc[post_age >= 14, "player_id"].unique()
    df["retained"] = df.index.isin(late)
    daily = np.zeros((len(df), TEST_DAYS), dtype=np.int8)
    pos = pd.Series(np.arange(len(df)), index=df.index)
    daily[pos.reindex(post["player_id"]).to_numpy(), post_age.to_numpy()] = 1
    df["ref_date"] = r
    return df.reset_index(), daily


def pooled_population(pday, dates):
    frames, mats = [], []
    for r in dates:
        df, daily = at_risk_population(pday, r)
        frames.append(df)
        mats.append(daily)
    return pd.concat(frames, ignore_index=True), np.vstack(mats)
