import numpy as np
import pandas as pd

from experiments import design as ed
from experiments import population as ep


def test_sample_size_matches_the_textbook_formula():
    # 2 * (1.96 + 0.8416)^2 * sd^2 / mde^2 with sd = 1, mde = 0.2 -> 392.4
    assert ed.sample_size_mean(1.0, 0.2) == 393
    assert abs(ed.mde_mean(1.0, 393) - 0.2) < 0.001


def test_cuped_variance_reduction_is_rho_squared(rng):
    x = rng.normal(0, 1, 20000)
    y = 0.6 * x + rng.normal(0, 0.8, 20000)
    rho = np.corrcoef(x, y)[0, 1]
    _, vr = ed.cuped(y, x)
    assert abs(vr - rho**2) < 0.01


def test_srm():
    assert ed.srm_test(5000, 5000) == 1.0
    assert ed.srm_test(5200, 4800) < 0.001


def test_aa_false_positive_rate_near_alpha(rng):
    y = rng.poisson(2, 20000).astype(float)
    x = y + rng.normal(0, 1, 20000)
    r = ed.aa_simulation(y, x, 1000, n_sims=400, seed=1)
    assert 0.02 < r["false_positive_raw"] < 0.09
    assert 0.02 < r["false_positive_cuped"] < 0.09


def test_cuped_raises_power_without_bias(rng):
    x = rng.poisson(3, 20000).astype(float)
    y = np.minimum(np.round(0.7 * x + rng.poisson(1, 20000)), 28)
    r = ed.injection_simulation(y, x, effect=0.12, n_per_arm=2000, cap=28, n_sims=150, seed=2)
    assert r["power_cuped"] > r["power_raw"]
    assert abs(r["mean_estimate_cuped"] - r["true_effect"]) < 0.02


def test_peeking_inflates_false_positives(rng):
    daily = (rng.random((8000, 28)) < 0.3).astype(np.int8)
    r = ed.peeking_simulation(daily, 1000, n_sims=300, seed=3)
    assert r["false_positive_peeking"] > r["false_positive_fixed"] + 0.03


def test_at_risk_population_columns():
    rows = []
    r = pd.Timestamp("2007-06-01")
    # Player 1: active early in the pre-period, fading, no guild -> eligible.
    for d in [-27, -26, -25, -20, -3, 2, 20]:
        rows.append((1, r + pd.Timedelta(days=d), 60.0, False))
    # Player 2: in a guild -> not eligible.
    for d in [-27, -26, -3]:
        rows.append((2, r + pd.Timedelta(days=d), 60.0, True))
    pday = pd.DataFrame(rows, columns=["player_id", "date", "minutes", "in_guild"])
    df, daily = ep.at_risk_population(pday, r)
    assert df["player_id"].tolist() == [1]
    row = df.iloc[0]
    assert row["pre_days"] == 5 and row["y_days"] == 2 and bool(row["retained"])
    assert daily.shape == (1, 28) and daily[0, 2] == 1 and daily[0, 20] == 1
