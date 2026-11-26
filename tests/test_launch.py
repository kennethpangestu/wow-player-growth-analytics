import numpy as np
import pandas as pd

from growth import launch as gl


def _daily(lift, rng, launch="2007-04-03", noise=0.03):
    dates = pd.date_range("2006-10-01", "2007-07-01", freq="D")
    base = 1500 * (1 + 0.1 * (dates.dayofweek >= 5)) * np.exp(rng.normal(0, noise, len(dates)))
    post = dates >= pd.Timestamp(launch)
    dau = np.where(post, base * (1 + lift), base)
    return pd.DataFrame({"date": dates, "dau_adj": dau, "low_coverage": False})


def test_recovers_a_known_lift(rng):
    r = gl.counterfactual_lift(_daily(0.30, rng), "2007-04-03", n_boot=300)
    assert abs(r["lift"] - 0.30) < 0.05
    assert r["ci_low"] < 0.30 < r["ci_high"]


def test_no_launch_no_lift(rng):
    r = gl.counterfactual_lift(_daily(0.0, rng), "2007-04-03", n_boot=300)
    assert abs(r["lift"]) < 0.04
    assert r["ci_low"] < 0 < r["ci_high"]


def test_low_coverage_and_excluded_days_are_ignored(rng):
    d = _daily(0.2, rng)
    spike = (d["date"] >= "2007-02-01") & (d["date"] <= "2007-02-05")
    d.loc[spike, "dau_adj"] *= 3
    biased = gl.counterfactual_lift(d, "2007-04-03", n_boot=0)["lift"]
    clean = gl.counterfactual_lift(d, "2007-04-03", n_boot=0, exclude=[("2007-02-01", "2007-02-05")])["lift"]
    assert abs(clean - 0.2) < abs(biased - 0.2)
    d.loc[spike, "low_coverage"] = True
    flagged = gl.counterfactual_lift(d, "2007-04-03", n_boot=0)["lift"]
    assert abs(flagged - clean) < 1e-9


def test_detect_launch_dates():
    pday = pd.DataFrame(
        {
            "date": pd.to_datetime(["2007-01-01", "2007-04-03", "2007-04-04", "2008-11-19"]),
            "max_level": [60, 61, 70, 71],
        }
    )
    d = gl.detect_launch_dates(pday)
    assert d["tbc"] == pd.Timestamp("2007-04-03")
    assert d["wotlk"] == pd.Timestamp("2008-11-19")


def test_launch_cohort_segments():
    rows = [
        (1, "2007-03-20"),
        (1, "2007-04-04"),
        (1, "2007-05-10"),  # already active, still active
        (2, "2007-01-05"),
        (2, "2007-04-05"),  # reactivated, gone later
        (3, "2007-04-06"),
        (3, "2007-05-08"),  # new, still active
        (4, "2007-01-05"),
        (4, "2007-04-05"),  # reactivated, but excluded
    ]
    pday = pd.DataFrame(rows, columns=["player_id", "date"])
    pday["date"] = pd.to_datetime(pday["date"])
    seg, summ = gl.launch_cohorts(pday, "2007-04-03", exclude_ids=[4])
    s = seg.set_index("player_id")
    assert s.loc[1, "segment"] == "already active" and s.loc[1, "still_active"]
    assert s.loc[2, "segment"] == "reactivated" and not s.loc[2, "still_active"]
    assert s.loc[3, "segment"] == "new" and s.loc[3, "still_active"]
    assert 4 not in s.index


def test_yoy_lift(rng):
    dates = pd.date_range("2006-01-01", "2008-12-31", freq="D")
    dau = np.full(len(dates), 1000.0)
    dau[(dates >= "2007-04-03") & (dates < "2007-05-29")] = 1500
    d = pd.DataFrame({"date": dates, "dau_adj": dau, "low_coverage": False})
    r = gl.yoy_lift(d, "2007-04-03", [2006, 2008])
    assert abs(r["lift"] - 0.5) < 1e-9
