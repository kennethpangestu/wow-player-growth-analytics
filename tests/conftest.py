import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def make_raw(rows):
    """rows: (player_id, guild, level, race, class, where, datetime-string)."""
    df = pd.DataFrame(rows, columns=["player_id", "guild", "level", "race", "class", "where", "datetime"])
    df["datetime"] = pd.to_datetime(df["datetime"])
    df["guild"] = df["guild"].astype(float)
    return df


@pytest.fixture
def rng():
    return np.random.default_rng(42)
