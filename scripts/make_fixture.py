"""Generate a small synthetic snapshot file with the same columns as the real data.

CI runs the whole pipeline on it, so it includes the things the code has to
handle: Thursday maintenance gaps, a switch to slower sampling, two expansion
launches (level cap 60 -> 70 -> 80, Blood Elves and Death Knights), guilds,
returning players and a few garbled race values. The numbers it produces mean
nothing; only the real dataset gives real results.

Usage: python scripts/make_fixture.py --out data/fixture/wow-fixture.parquet
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from growth.io import write_table  # noqa: E402

START = pd.Timestamp("2006-01-01")
END = pd.Timestamp("2009-01-10")
TBC = pd.Timestamp("2007-04-03")
WOTLK = pd.Timestamp("2008-11-19")
SLOW = pd.Timestamp("2008-11-07")
RACES = ["Orc", "Tauren", "Troll", "Undead"]
CLASSES = ["Druid", "Hunter", "Mage", "Priest", "Rogue", "Shaman", "Warlock", "Warrior"]
ZONES = ["Durotar", "The Barrens", "Orgrimmar", "Stranglethorn Vale", "Hellfire Peninsula", "Borean Tundra"]


def sweep_times():
    """Sweep start times: every 10 minutes, every 15 after SLOW, none during
    Thursday 03:00-11:00 maintenance."""
    fast = pd.date_range(START, SLOW, freq="10min", inclusive="left")
    slow = pd.date_range(SLOW, END, freq="15min")
    t = fast.append(slow)
    maint = (t.dayofweek == 3) & (t.hour >= 3) & (t.hour < 11)
    return t[~maint]


def level_cap(day):
    return 80 if day >= WOTLK else 70 if day >= TBC else 60


def simulate(n_avatars, seed):
    rng = np.random.default_rng(seed)
    sweeps = sweep_times()
    day_index = pd.date_range(START, END, freq="D")
    rows = []
    for pid in range(n_avatars):
        first = day_index[int(rng.integers(0, len(day_index) - 5))]
        # Launch weeks bring in extra avatars.
        if rng.random() < 0.15:
            first = (TBC if rng.random() < 0.6 else WOTLK) + pd.Timedelta(days=int(rng.integers(0, 14)))
        race = rng.choice(RACES + (["Blood Elf"] if first >= TBC else []))
        klass = "Death Knight" if (first >= WOTLK and rng.random() < 0.2) else rng.choice(CLASSES)
        level = 55 if klass == "Death Knight" else 1
        # A quarter of the early avatars are veterans already near the level cap.
        if first < TBC and klass != "Death Knight" and rng.random() < 0.25:
            level = int(rng.integers(50, 61))
        guild = float(rng.integers(1, 40)) if rng.random() < 0.3 else np.nan
        guild_day = first + pd.Timedelta(days=int(rng.integers(0, 30)))
        lifetime = int(rng.exponential(60)) + 1
        p_play = rng.uniform(0.15, 0.7)
        day = first
        while day <= min(first + pd.Timedelta(days=lifetime), END):
            if rng.random() < p_play:
                start = day + pd.Timedelta(minutes=int(rng.integers(0, 1440)))
                length = pd.Timedelta(minutes=int(rng.exponential(90)) + 10)
                mask = (sweeps >= start) & (sweeps < start + length)
                hits = sweeps[mask]
                cap = level_cap(day)
                for ts in hits:
                    if level < cap and rng.random() < (0.3 if level >= 59 else 0.08):
                        level += 1
                    g = guild if (not np.isnan(guild) and ts >= guild_day) else np.nan
                    seen_at = ts + pd.Timedelta(seconds=int(rng.integers(0, 200)))
                    rows.append((pid, g, level, race, klass, rng.choice(ZONES), seen_at))
            day += pd.Timedelta(days=1)
            # Some players lapse for a while and come back (more often at launches).
            if rng.random() < 0.01:
                day += pd.Timedelta(days=int(rng.integers(30, 120)))
    df = pd.DataFrame(rows, columns=["player_id", "guild", "level", "race", "class", "where", "datetime"])
    # A few garbled race values, like the real files.
    bad = rng.random(len(df)) < 0.001
    df.loc[bad, "race"] = "373x"
    return df.sort_values("datetime").reset_index(drop=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/fixture/wow-fixture.parquet")
    ap.add_argument("--avatars", type=int, default=1500)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    df = simulate(args.avatars, args.seed)
    df["player_id"] = df["player_id"].astype("int32")
    df["level"] = df["level"].astype("int32")
    write_table(df, args.out)
    print(f"wrote {len(df):,} rows for {df['player_id'].nunique():,} avatars to {args.out}")


if __name__ == "__main__":
    main()
