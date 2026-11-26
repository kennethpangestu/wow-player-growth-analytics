import numpy as np
import pandas as pd
from conftest import make_raw

from growth import data as gd


def _sweeps_at(times):
    df = pd.DataFrame({"datetime": pd.to_datetime(times)})
    return gd.sweep_table(df["datetime"])


def test_rows_seconds_apart_form_one_sweep():
    sweeps, lookup = _sweeps_at(
        ["2007-01-01 10:00:00", "2007-01-01 10:00:40", "2007-01-01 10:03:30", "2007-01-01 10:10:00"]
    )
    assert len(sweeps) == 2
    assert lookup.iloc[0] == lookup.iloc[2]
    assert lookup.iloc[3] == 1


def test_sweep_minutes_are_capped_across_gaps():
    times = pd.date_range("2007-01-01", periods=200, freq="10min")
    times = times.append(pd.date_range("2007-01-03", periods=10, freq="10min"))
    sweeps, _ = _sweeps_at(times)
    # The sweep before the long gap stands for at most 1.5 x 10 minutes, not two days.
    assert sweeps["minutes"].max() <= 15 + 1e-9
    assert sweeps["minutes"].iloc[0] == 10


def test_garbled_attributes_are_blanked_but_rows_kept():
    raw = make_raw(
        [
            (1, None, 10, "Orc", "Warrior", "Durotar", "2007-01-01 10:00:00"),
            (1, None, 10, "547x", "Warrior", "Durotar", "2007-01-01 10:10:00"),
            (2, 5, 20, "Troll", "12ab", "Orgrimmar", "2007-01-01 10:00:05"),
        ]
    )
    df = gd.clean_raw(raw)
    assert len(df) == 3
    assert df["race"].isna().sum() == 1
    assert df["char_class"].isna().sum() == 1


def _obs_for(player_sweeps, sweeps_n=40):
    times = pd.date_range("2007-01-01", periods=sweeps_n, freq="10min")
    rows = []
    for pid, idx in player_sweeps.items():
        for i in idx:
            rows.append((pid, None, 10, "Orc", "Warrior", "Durotar", str(times[i])))
    # A filler avatar online in every sweep, so every sweep is "collected".
    for i in range(sweeps_n):
        rows.append((99, None, 10, "Orc", "Warrior", "Durotar", str(times[i])))
    df = gd.clean_raw(make_raw(rows))
    sweeps, lookup = gd.sweep_table(df["datetime"])
    return gd.add_sweep_ids(df, lookup), sweeps


def test_session_survives_one_missed_sweep_but_not_two():
    obs, sweeps = _obs_for({1: [0, 1, 3, 4], 2: [0, 1, 4, 5]})
    s = gd.sessionize(obs, sweeps)
    assert (s["player_id"] == 1).sum() == 1  # missed sweep 2 only
    assert (s["player_id"] == 2).sum() == 2  # missed sweeps 2 and 3


def test_uncollected_sweeps_do_not_end_a_session():
    # Maintenance: no sweeps at all between 03:00 and 11:00.
    before = pd.date_range("2007-01-04 02:00", "2007-01-04 02:50", freq="10min")
    after = pd.date_range("2007-01-04 11:00", "2007-01-04 11:50", freq="10min")
    times = before.append(after)
    rows = [(1, None, 10, "Orc", "Warrior", "Durotar", str(t)) for t in times]
    df = gd.clean_raw(make_raw(rows))
    sweeps, lookup = gd.sweep_table(df["datetime"])
    obs = gd.add_sweep_ids(df, lookup)
    s = gd.sessionize(obs, sweeps)
    assert len(s) == 1
    # ...but the eight hours offline are not counted as play time.
    assert s["minutes"].iloc[0] <= 12 * 10 + 5


def test_player_day_counts_minutes_and_guild():
    obs, sweeps = _obs_for({1: [0, 1, 2]})
    obs.loc[(obs["player_id"] == 1) & (obs["sweep_id"] == 2), "guild"] = 7.0
    pday = gd.player_day(obs, sweeps)
    row = pday.loc[pday["player_id"] == 1].iloc[0]
    assert row["snapshots"] == 3
    assert abs(row["minutes"] - 30) < 1e-9
    assert bool(row["in_guild"])


def test_coverage_and_slow_sampling_flag():
    fast = pd.date_range("2008-11-01", "2008-11-02 23:50", freq="10min")
    slow = pd.date_range("2008-11-03", "2008-11-04 23:45", freq="15min")
    sweeps, _ = _sweeps_at(fast.append(slow))
    cov = gd.daily_coverage(sweeps)
    assert cov["slow_sampling"].tolist() == [False, False, True, True]
    assert (cov["coverage"].iloc[:3] > 0.97).all()


def test_reused_ids_flag_level_drops_and_two_characters():
    rows = []
    t = pd.date_range("2007-01-01", periods=60, freq="10min")
    for i in range(25):
        rows.append((1, None, 60, "Undead", "Warlock", "Undercity", str(t[i])))
    for i in range(25, 50):
        rows.append((1, None, 3, "Blood Elf", "Paladin", "Eversong Woods", str(t[i])))
    for i in range(30):
        rows.append((2, None, 10 + i // 10, "Orc", "Hunter", "Durotar", str(t[i])))
    df = gd.clean_raw(make_raw(rows))
    sweeps, lookup = gd.sweep_table(df["datetime"])
    obs = gd.add_sweep_ids(df, lookup)
    r = gd.reused_ids(obs)
    assert r["any"] == {1}
    assert 1 in r["level_drop"] and 1 in r["two_characters"]


def test_thinning_ratio_is_one_when_everyone_is_always_online():
    times = pd.date_range("2007-01-01", "2007-01-03 23:50", freq="10min")
    rows = [(p, None, 10, "Orc", "Warrior", "Durotar", str(x)) for x in times for p in (1, 2, 3)]
    df = gd.clean_raw(make_raw(rows))
    sweeps, lookup = gd.sweep_table(df["datetime"])
    obs = gd.add_sweep_ids(df, lookup)
    cov = gd.daily_coverage(sweeps)
    th = gd.thinning_ratio(obs, sweeps, cov, min_coverage=0.9)
    assert len(th) == 3
    assert np.allclose(th["ratio"], 1.0)
