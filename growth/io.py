"""Table I/O in one place, so every module reads and writes data the same way."""

from pathlib import Path

import pandas as pd


def read_table(path, columns=None):
    """Read a parquet table."""
    return pd.read_parquet(path, columns=columns)


def write_table(df, path):
    """Write a parquet table, creating the folder if needed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return path
