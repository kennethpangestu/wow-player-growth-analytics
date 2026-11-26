import numpy as np
import pandas as pd

from growth import early as ge


def test_threshold_search_finds_a_clean_split():
    df = pd.DataFrame({"x": [1, 1, 1, 1, 2, 3, 3, 4, 5, 6] * 10, "retained_d90": [0, 0, 0, 0, 0, 1, 1, 1, 1, 1] * 10})
    best, _ = ge.aha_moments(df, features=["x"])
    assert best.loc[0, "threshold"] == 3
    assert abs(best.loc[0, "youden_j"] - 1.0) < 1e-9


def test_e_value_formula():
    assert abs(ge.e_value(2.0) - (2 + np.sqrt(2))) < 1e-12
    assert abs(ge.e_value(0.5) - ge.e_value(2.0)) < 1e-12
    assert ge.e_value(1.0) == 1.0


def _confounded_sample(rng, n=10000, effect=0.10):
    """Engagement drives both guild joining and retention; the true effect is +10 pts.
    Confounding is moderate so treated and control avatars overlap, as in the real data."""
    eng = rng.gamma(2.0, 1.5, n)
    p_t = 1 / (1 + np.exp(-(-2.5 + 0.35 * eng)))
    t = rng.random(n) < p_t
    p_y = np.clip(0.05 + 0.06 * eng + effect * t, 0, 1)
    y = rng.random(n) < p_y
    return pd.DataFrame(
        {
            "active_days_w1": np.clip(np.round(eng), 1, 7),
            "hours_w1": eng * 2,
            "sessions_w1": np.round(eng * 1.5),
            "levels_gained_w1": np.round(eng * 2),
            "max_level_w1": np.round(eng * 2) + 1,
            "first_level": 1,
            "race": "Orc",
            "char_class": rng.choice(["Mage", "Rogue"], n),
            "cohort_quarter": rng.choice(["2007Q1", "2007Q2"], n),
            "treated": t.astype(int),
            "retained_d90": y,
        }
    )


def test_guild_effect_removes_confounding(rng):
    s = _confounded_sample(rng)
    r = ge.guild_effect(s, n_boot=30)
    assert r["naive_rd"] > 0.14  # inflated by engagement
    assert abs(r["ipw_rd"] - 0.10) < 0.035
    assert r["max_abs_smd_after"] < 0.1


def test_smd_zero_for_identical_groups():
    x = np.array([1.0, 2, 3, 1, 2, 3])
    t = np.array([1, 1, 1, 0, 0, 0])
    assert ge.smd(x, t) == 0
