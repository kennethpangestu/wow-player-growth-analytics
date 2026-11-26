"""From raw /who snapshots to sweeps, sessions, player-days and avatars.

Raw rows are one avatar seen online in one /who query. The collector ran a full
sweep of /who queries every 10 minutes, and each row carries its own timestamp,
so rows are first grouped into sweeps. Sessions and player-days are built on
sweeps, which keeps missing sweeps (Thursday maintenance, collector outages)
from breaking sessions or counting as time offline.

All rules and thresholds here are recorded in docs/decisions.md.
"""

import numpy as np
import pandas as pd

from growth.io import read_table

RAW_COLUMNS = ["player_id", "guild", "level", "race", "class", "where", "datetime"]

VALID_RACES = ["Blood Elf", "Orc", "Tauren", "Troll", "Undead"]
VALID_CLASSES = [
    "Death Knight",
    "Druid",
    "Hunter",
    "Mage",
    "Paladin",
    "Priest",
    "Rogue",
    "Shaman",
    "Warlock",
    "Warrior",
]

SNAPSHOT_MINUTES = 10
# Rows less than 3 minutes apart belong to the same sweep. Inside a sweep, rows
# are seconds apart; between sweeps the collector idles for about 5 minutes.
SWEEP_GAP_SECONDS = 180
# A session survives one collected sweep that missed the avatar (about 1% of
# consecutive sightings). Sweeps that were never collected never end a session.
SESSION_MAX_MISSED_SWEEPS = 1
# Sweeps used to estimate the local sampling interval (about a day's worth).
SWEEP_INTERVAL_WINDOW = 145
# A sweep stands for at most 1.5x the typical interval (one missed sweep or less).
SWEEP_WEIGHT_CAP = 1.5
# Days whose median sweep interval is above this run on the slower schedule.
SLOW_REGIME_MINUTES = 12.5


def load_raw(path):
    return read_table(path, columns=RAW_COLUMNS)


def _valid_category(values, allowed):
    v = values.astype("object")
    return pd.Categorical(v.where(v.isin(allowed)), categories=allowed)


def clean_raw(raw):
    """Standardize column names and types and blank out corrupt attributes.

    About 0.1% of rows have a garbled race or class (digits or stray characters
    from the original text files). Their player, time and level are fine, so the
    rows are kept for activity and only the bad attribute is set to missing.
    """
    df = pd.DataFrame(
        {
            "player_id": raw["player_id"].astype("int32"),
            "guild": raw["guild"].astype("float32"),
            "level": raw["level"].astype("int16"),
            "race": _valid_category(raw["race"], VALID_RACES),
            "char_class": _valid_category(raw["class"], VALID_CLASSES),
            "zone": raw["where"].astype("category"),
            "datetime": pd.to_datetime(raw["datetime"]).astype("datetime64[s]"),
        }
    )
    df = df.drop_duplicates(["player_id", "datetime"])
    return df.reset_index(drop=True)


def sweep_table(datetimes, gap_seconds=SWEEP_GAP_SECONDS):
    """Group distinct timestamps into sweeps.

    Returns (sweeps, lookup): `sweeps` has one row per sweep with its start, end,
    date and the minutes of play it stands for; `lookup` maps each distinct
    timestamp to its sweep id.

    The collector ran every 10 minutes until early November 2008 and about every
    15 minutes after that. Each sweep therefore stands for the time until the next
    sweep, capped at 1.5 times the local typical interval so that maintenance
    windows and outages are not counted as play time.
    """
    ts = np.sort(pd.unique(np.asarray(datetimes, dtype="datetime64[s]")))
    gaps = np.diff(ts).astype("int64")
    new_sweep = np.concatenate([[True], gaps > gap_seconds])
    sweep_id = np.cumsum(new_sweep) - 1
    lookup = pd.Series(sweep_id.astype("int32"), index=pd.DatetimeIndex(ts))
    starts = ts[new_sweep]
    ends = ts[np.concatenate([new_sweep[1:], [True]])]
    sweeps = pd.DataFrame(
        {
            "sweep_id": np.arange(len(starts), dtype="int32"),
            "start": starts,
            "end": ends,
        }
    )
    # A sweep counts toward the day its first query ran.
    sweeps["date"] = sweeps["start"].dt.normalize()
    to_next = sweeps["start"].shift(-1).sub(sweeps["start"]).dt.total_seconds() / 60
    typical = to_next.rolling(SWEEP_INTERVAL_WINDOW, center=True, min_periods=1).median()
    typical = typical.fillna(SNAPSHOT_MINUTES)
    sweeps["interval_minutes"] = typical.to_numpy()
    sweeps["minutes"] = np.minimum(to_next.fillna(typical), SWEEP_WEIGHT_CAP * typical).to_numpy()
    return sweeps, lookup


def add_sweep_ids(df, lookup):
    out = df.copy()
    out["sweep_id"] = lookup.reindex(pd.DatetimeIndex(out["datetime"])).to_numpy()
    out = out.sort_values(["player_id", "sweep_id", "datetime"], kind="stable")
    # An avatar can show up twice in one sweep when two queries overlap; keep the last row.
    out = out.drop_duplicates(["player_id", "sweep_id"], keep="last")
    return out.reset_index(drop=True)


def daily_coverage(sweeps):
    """Collected sweeps per day, the day's sampling interval, and coverage.

    Coverage is the share of the day's 1,440 minutes that collected sweeps stand
    for. A normal day is about 1.0; maintenance Thursdays are about 0.65.
    """
    days = pd.date_range(sweeps["date"].min(), sweeps["date"].max(), freq="D")
    g = sweeps.groupby("date")
    cov = pd.DataFrame({"date": days})
    cov["sweeps"] = g.size().reindex(days, fill_value=0).to_numpy()
    cov["interval_minutes"] = g["interval_minutes"].median().reindex(days).to_numpy()
    minutes = g["minutes"].sum().reindex(days, fill_value=0).to_numpy()
    cov["coverage"] = np.clip(minutes / 1440, 0, 1)
    cov["slow_sampling"] = cov["interval_minutes"] > SLOW_REGIME_MINUTES
    return cov


def thinning_ratio(obs, sweeps, coverage, keep_every=(1, 1, 0), n_days=60, min_coverage=0.97):
    """How much DAU a sparser sampling schedule would miss.

    Takes the last `n_days` full-coverage days on the 10-minute schedule, keeps
    only the sweeps marked 1 in the repeating `keep_every` pattern (the default
    keeps 2 of every 3, an average of one sweep per 15 minutes) and returns the
    DAU ratio thinned / full for each day.
    """
    ok = coverage.loc[(coverage["coverage"] >= min_coverage) & ~coverage["slow_sampling"], "date"]
    days = pd.DatetimeIndex(ok).sort_values()[-n_days:]
    sw = sweeps.loc[sweeps["date"].isin(days)].sort_values("start").copy()
    pattern = np.array(keep_every, dtype=bool)
    sw["keep"] = pattern[np.arange(len(sw)) % len(pattern)]
    o = obs.loc[obs["sweep_id"].isin(sw["sweep_id"]), ["player_id", "sweep_id"]]
    o = o.merge(sw[["sweep_id", "date", "keep"]], on="sweep_id")
    full = o.groupby("date")["player_id"].nunique()
    thin = o.loc[o["keep"]].groupby("date")["player_id"].nunique()
    out = pd.DataFrame({"dau_full": full, "dau_thinned": thin}).reset_index()
    out["ratio"] = out["dau_thinned"] / out["dau_full"]
    return out


def count_sessions(obs, max_missed):
    """Number of sessions under a given missed-sweep tolerance (for reconciliation)."""
    pid = obs["player_id"].to_numpy()
    sid = obs["sweep_id"].to_numpy()
    breaks = (pid[1:] != pid[:-1]) | (sid[1:] - sid[:-1] > 1 + max_missed)
    return int(breaks.sum()) + 1


def sessionize(obs, sweeps, max_missed=SESSION_MAX_MISSED_SWEEPS):
    """One row per session.

    `obs` must have one row per (player_id, sweep_id), sorted by player and sweep,
    as returned by add_sweep_ids. Sweep ids only count collected sweeps, so a gap
    of one id means back-to-back sightings even across a maintenance window. A
    session ends when the avatar is missing from more than `max_missed` collected
    sweeps in a row. Minutes add up the minutes each sweep stands for.
    """
    pid = obs["player_id"].to_numpy()
    sid = obs["sweep_id"].to_numpy()
    new = np.ones(len(obs), dtype=bool)
    new[1:] = (pid[1:] != pid[:-1]) | (sid[1:] - sid[:-1] > 1 + max_missed)
    session_no = np.cumsum(new) - 1
    weight = sweeps.set_index("sweep_id")["minutes"].reindex(sid).to_numpy()
    g = obs.assign(session_no=session_no, in_guild=obs["guild"].notna(), w=weight).groupby("session_no", sort=False)
    sessions = pd.DataFrame(
        {
            "player_id": g["player_id"].first(),
            "start": g["datetime"].first(),
            "end": g["datetime"].last(),
            "snapshots": g.size(),
            "span_sweeps": g["sweep_id"].last() - g["sweep_id"].first() + 1,
            "start_level": g["level"].first(),
            "end_level": g["level"].last(),
            "in_guild": g["in_guild"].any(),
            "minutes": g["w"].sum(),
        }
    ).reset_index(drop=True)
    sessions.insert(0, "session_id", np.arange(len(sessions), dtype="int64"))
    return sessions


def player_day(obs, sweeps):
    """One row per avatar per active day (the day of the sweep it was seen in)."""
    sw = sweeps.set_index("sweep_id")
    o = pd.DataFrame(
        {
            "player_id": obs["player_id"].to_numpy(),
            "date": sw["date"].reindex(obs["sweep_id"]).to_numpy(),
            "w": sw["minutes"].reindex(obs["sweep_id"]).to_numpy(),
            "level": obs["level"].to_numpy(),
            "guild": obs["guild"].to_numpy(),
            "zone": obs["zone"].cat.codes.to_numpy(),
        }
    )
    g = o.groupby(["player_id", "date"], sort=True)
    pday = pd.DataFrame(
        {
            "snapshots": g.size(),
            "min_level": g["level"].min(),
            "max_level": g["level"].max(),
            "guild": g["guild"].last(),
            "in_guild": g["guild"].count() > 0,
            "zones": g["zone"].nunique(),
            "minutes": g["w"].sum(),
        }
    ).reset_index()
    pday["player_id"] = pday["player_id"].astype("int32")
    pday["snapshots"] = pday["snapshots"].astype("int32")
    return pday


def _mode(series):
    s = series.dropna()
    if s.empty:
        return np.nan
    return s.value_counts().index[0]


# An ID is "reused" when the evidence says two characters shared it: a level drop
# of more than this many levels between sightings (levels never go down), or two
# race/class combinations each seen at least REUSE_MIN_ROWS times.
REUSE_LEVEL_DROP = 5
REUSE_MIN_ROWS = 20


def reused_ids(obs):
    """IDs that look like they were used by more than one character.

    IDs are anonymized character names, and a name can be taken again after its
    character is deleted, so one ID can cover two characters.
    """
    pid = obs["player_id"].to_numpy()
    lv = obs["level"].to_numpy().astype(int)
    same = pid[1:] == pid[:-1]
    drop_ids = np.unique(pid[1:][same & (lv[1:] < lv[:-1] - REUSE_LEVEL_DROP)])
    combos = obs[["player_id", "race", "char_class"]].dropna()
    combos = combos.groupby(["player_id", "race", "char_class"], observed=True).size()
    combos = combos[combos >= REUSE_MIN_ROWS].reset_index().groupby("player_id").size()
    combo_ids = combos[combos >= 2].index.to_numpy()
    return {
        "level_drop": set(drop_ids.tolist()),
        "two_characters": set(combo_ids.tolist()),
        "any": set(drop_ids.tolist()) | set(combo_ids.tolist()),
    }


def avatar_table(obs, pday, reused=None):
    """One row per avatar: first and last day seen, first level, race and class.

    `reused_id` marks IDs that look shared by two characters (see reused_ids).
    """
    first = obs.groupby("player_id", sort=True).agg(first_seen=("datetime", "first"), first_level=("level", "first"))
    attrs = obs[["player_id", "race", "char_class"]].dropna()
    attrs = attrs.groupby(["player_id", "race", "char_class"], observed=True).size()
    attrs = attrs.reset_index(name="n").sort_values(["player_id", "n"], ascending=[True, False])
    attrs = attrs.drop_duplicates("player_id").set_index("player_id")[["race", "char_class"]]
    days = pday.groupby("player_id").agg(
        first_day=("date", "min"),
        last_day=("date", "max"),
        active_days=("date", "size"),
        max_level=("max_level", "max"),
    )
    guild_days = pday.loc[pday["in_guild"]].groupby("player_id")["date"].min().rename("first_guild_day")
    av = first.join(days).join(attrs).join(guild_days).reset_index()
    av["race"] = _valid_category(av["race"], VALID_RACES)
    av["char_class"] = _valid_category(av["char_class"], VALID_CLASSES)
    av["reused_id"] = av["player_id"].isin(reused["any"]) if reused else False
    return av


def build_all(raw):
    """Run the whole data layer. Returns a dict of tables plus a quality dict."""
    quality = {"raw_rows": int(len(raw)), "raw_avatars": int(raw["player_id"].nunique())}
    df = clean_raw(raw)
    quality["rows_after_dedupe"] = int(len(df))
    quality["garbled_attribute_rows"] = int((df["race"].isna() | df["char_class"].isna()).sum())
    sweeps, lookup = sweep_table(df["datetime"])
    obs = add_sweep_ids(df, lookup)
    del df
    quality["avatar_sweep_rows"] = int(len(obs))
    for label, col, value in [
        ("first_blood_elf", "race", "Blood Elf"),
        ("first_paladin", "char_class", "Paladin"),
        ("first_death_knight", "char_class", "Death Knight"),
    ]:
        quality[label] = obs.loc[obs[col] == value, "datetime"].min()
    quality["first_above_level_60"] = obs.loc[obs["level"] > 60, "datetime"].min()
    quality["first_above_level_70"] = obs.loc[obs["level"] > 70, "datetime"].min()
    quality["sessions_no_missed_sweeps"] = count_sessions(obs, 0)
    quality["sessions_six_missed_sweeps"] = count_sessions(obs, 6)
    reused = reused_ids(obs)
    quality["reused_ids_level_drop"] = len(reused["level_drop"])
    quality["reused_ids_two_characters"] = len(reused["two_characters"])
    quality["reused_ids"] = len(reused["any"])
    coverage = daily_coverage(sweeps)
    tables = {
        "sweeps": sweeps,
        "coverage": coverage,
        "sessions": sessionize(obs, sweeps),
        "thinning": thinning_ratio(obs, sweeps, coverage),
    }
    tables["player_day"] = player_day(obs, sweeps)
    tables["avatars"] = avatar_table(obs, tables["player_day"], reused)
    quality["sweeps"] = int(len(sweeps))
    quality["days"] = int(len(coverage))
    quality["days_without_data"] = int((coverage["sweeps"] == 0).sum())
    quality["sessions"] = int(len(tables["sessions"]))
    quality["player_days"] = int(len(tables["player_day"]))
    tables["quality"] = quality
    return tables
