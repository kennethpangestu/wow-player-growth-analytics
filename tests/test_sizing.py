import numpy as np
import pandas as pd

from growth import sizing as gs


def test_incremental_dau_with_a_flat_curve():
    curve = np.ones(200)
    extra = gs.incremental_dau(new_per_day=100, curve=curve, points=1.0, horizon=182)
    # 1 extra player per day of arrivals, each active every day from age 30 on.
    assert extra[29] == 0
    assert extra[30] == 1
    assert extra[182] == 153


def test_baseline_prefers_the_forecast_file(tmp_path):
    daily = pd.DataFrame({"date": pd.date_range("2008-01-01", periods=100), "dau_adj": 1000.0, "low_coverage": False})
    base, source = gs.baseline_dau(daily, forecast_path=tmp_path / "missing.csv")
    assert base == 1000 and "last" in source
    f = tmp_path / "dau_forecast.csv"
    pd.DataFrame({"date": pd.date_range("2009-01-11", periods=56), "dau_forecast": 1200.0}).to_csv(f, index=False)
    base, source = gs.baseline_dau(daily, forecast_path=f)
    assert base == 1200 and source == "teammate forecast"
