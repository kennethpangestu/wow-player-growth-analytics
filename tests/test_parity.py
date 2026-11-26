"""Metric parity: the pandas growth accounting must match the dbt mart exactly.

Skips until the teammate's warehouse exists (warehouse/wow.duckdb with the
agg_growth_accounting_monthly mart, see docs/data_contract.md).
"""

from pathlib import Path

import pandas as pd
import pytest

from growth import metrics as gm

WAREHOUSE = Path(__file__).resolve().parents[1] / "warehouse" / "wow.duckdb"


@pytest.mark.skipif(not WAREHOUSE.exists(), reason="dbt marts not built yet (warehouse/wow.duckdb)")
def test_growth_accounting_matches_the_mart():
    duckdb = pytest.importorskip("duckdb")
    con = duckdb.connect(str(WAREHOUSE), read_only=True)
    pday = con.execute("select player_id, activity_date as date from fct_player_day").df()
    pday["date"] = pd.to_datetime(pday["date"])
    mart = con.execute(
        "select month_start, new_players, retained_players, resurrected_players, churned_players "
        "from agg_growth_accounting_monthly order by month_start"
    ).df()
    mart["month_start"] = pd.to_datetime(mart["month_start"])
    end = mart["month_start"].max() + pd.offsets.MonthBegin(1)
    ours = gm.monthly_growth_accounting(pday, start=mart["month_start"].min(), end=end)
    m = ours.merge(mart, on="month_start", how="outer", indicator=True)
    assert (m["_merge"] == "both").all(), "months differ between pandas and the mart"
    for ours_col, mart_col in [
        ("new", "new_players"),
        ("retained", "retained_players"),
        ("resurrected", "resurrected_players"),
        ("churned", "churned_players"),
    ]:
        assert (m[ours_col] == m[mart_col]).all(), f"{ours_col} does not match {mart_col}"
