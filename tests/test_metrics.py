import numpy as np
import pandas as pd

from growth import metrics as gm


def _pday(pairs):
    df = pd.DataFrame(pairs, columns=["player_id", "date"])
    df["date"] = pd.to_datetime(df["date"])
    df["minutes"] = 60.0
    return df


def test_rolling_distinct_matches_brute_force(rng):
    days = pd.date_range("2007-01-01", periods=60, freq="D")
    pairs = {(int(p), days[int(d)]) for p, d in zip(rng.integers(0, 30, 400), rng.integers(0, 60, 400), strict=True)}
    pday = _pday(sorted(pairs))
    for window in (1, 7, 28):
        fast = gm.rolling_distinct(pday, window, days)
        for i, d in enumerate(days):
            lo = d - pd.Timedelta(days=window - 1)
            brute = pday.loc[(pday["date"] >= lo) & (pday["date"] <= d), "player_id"].nunique()
            assert fast[i] == brute


def test_growth_accounting_toy_example():
    pday = _pday(
        [
            ("A", "2007-01-05"),
            ("B", "2007-01-06"),
            ("A", "2007-02-02"),
            ("C", "2007-02-10"),
            ("B", "2007-03-03"),
        ]
    )
    pday["player_id"] = pday["player_id"].map({"A": 1, "B": 2, "C": 3})
    ga = gm.monthly_growth_accounting(pday, start="2007-01-01", end="2007-04-01").set_index("month")
    feb, mar = ga.loc[pd.Period("2007-02", "M")], ga.loc[pd.Period("2007-03", "M")]
    assert (feb["new"], feb["retained"], feb["resurrected"], feb["churned"]) == (1, 1, 0, 1)
    assert (mar["new"], mar["retained"], mar["resurrected"], mar["churned"]) == (0, 0, 1, 2)
    # MAU change equals gains minus losses.
    assert mar["mau"] - feb["mau"] == mar["mau_change"]


def test_growth_accounting_identity_holds_on_random_data(rng):
    days = pd.date_range("2006-01-01", periods=400, freq="D")
    pairs = {
        (int(p), days[int(d)]) for p, d in zip(rng.integers(0, 200, 3000), rng.integers(0, 400, 3000), strict=True)
    }
    ga = gm.monthly_growth_accounting(_pday(sorted(pairs)), start="2006-02-01", end="2007-02-01")
    assert (ga["mau"] == ga["new"] + ga["retained"] + ga["resurrected"]).all()
    assert (ga["mau"].diff().iloc[1:] == ga["mau_change"].iloc[1:]).all()


def test_change_decomposition_sums_to_one(rng):
    ga = pd.DataFrame(
        {
            "new": rng.integers(100, 500, 24),
            "resurrected": rng.integers(50, 150, 24),
            "churned": rng.integers(100, 600, 24),
        }
    )
    ga["mau_change"] = ga["new"] + ga["resurrected"] - ga["churned"]
    parts = gm.change_decomposition(ga)
    assert abs(sum(parts.values()) - 1) < 1e-9


def test_retention_windows():
    pday = _pday([(1, "2007-01-01"), (1, "2007-01-02"), (1, "2007-02-05"), (2, "2007-01-01"), (2, "2007-04-05")])
    cohort = pd.DataFrame({"player_id": [1, 2], "first_day": pd.to_datetime(["2007-01-01", "2007-01-01"])})
    f = gm.retention_flags(pday, cohort).set_index("player_id")
    assert f.loc[1, "d1"] and f.loc[1, "d30"] and not f.loc[1, "d90"]
    assert not f.loc[2, "d1"] and f.loc[2, "d90"]


def test_new_avatar_rule():
    av = pd.DataFrame(
        {
            "player_id": [1, 2, 3, 4, 5],
            "first_day": pd.to_datetime(["2007-01-01", "2006-02-01", "2007-01-01", "2008-12-01", "2007-01-01"]),
            "first_level": [1, 1, 60, 55, 1],
            "char_class": pd.Categorical(["Mage", "Mage", "Mage", "Death Knight", "Mage"]),
            "reused_id": [False, False, False, False, True],
        }
    )
    kept = gm.new_avatars(av, pd.Timestamp("2009-01-01"))["player_id"].tolist()
    assert kept == [1]


def test_daily_active_adjusts_slow_sampling_days():
    pday = _pday([(1, "2007-01-01"), (2, "2007-01-01"), (1, "2007-01-02")])
    cov = pd.DataFrame(
        {"date": pd.to_datetime(["2007-01-01", "2007-01-02"]), "coverage": [1.0, 1.0], "slow_sampling": [False, True]}
    )
    d = gm.daily_active(pday, cov, slow_sampling_ratio=0.5)
    assert d["dau"].tolist() == [2, 1]
    assert d["dau_adj"].tolist() == [2.0, 2.0]
    assert np.isclose(d["stickiness"].iloc[0], 1.0)
