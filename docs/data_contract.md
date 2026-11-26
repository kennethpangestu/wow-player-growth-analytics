# Data contract: marts the analytics code reads

The teammate builds these in DuckDB with dbt (staging and marts), and Kenneth reviews. Until they land, Kenneth's code builds the same tables in pandas from the raw parquet (`growth/data.py`). The pandas tables are the reference implementation: definitions follow [`metrics.md`](metrics.md), and the marts must reconcile with them (counts below).

Warehouse file: `warehouse/wow.duckdb` (gitignored). CI builds it from the synthetic fixture (`scripts/make_fixture.py`).

## stg_snapshots

Grain: one row per raw snapshot row after de-duplication on (`player_id`, `datetime`).

| Column | Type | Notes |
|---|---|---|
| player_id | int | |
| guild_id | int, nullable | |
| level | smallint | |
| race | varchar, nullable | null when garbled (not one of the 5 Horde races) |
| class | varchar, nullable | null when garbled (not one of the 10 classes) |
| zone | varchar | raw column `where` |
| seen_at | timestamp | |
| sweep_id | int | dense id of collected sweeps (rows less than 3 minutes apart share a sweep) |

Tests: `not_null(player_id, seen_at, sweep_id)`, accepted values for race and class (or null), `unique(player_id, seen_at)`.

## dim_sweep

Grain: one row per collected sweep. Columns: `sweep_id` (pk), `started_at`, `ended_at`, `sweep_date`, `interval_minutes`, `minutes`. Rules as in `data.sweep_table`.

## fct_sessions

Grain: one row per session. Columns: `session_id` (pk), `player_id`, `started_at`, `ended_at`, `snapshots`, `minutes`, `start_level`, `end_level`, `in_guild`. A session ends when the avatar is missing from 2+ consecutive collected sweeps.

## fct_player_day

Grain: one row per (`player_id`, `activity_date`). Columns: `snapshots`, `minutes`, `min_level`, `max_level`, `guild_id` (last seen that day), `in_guild`, `zones`.

## dim_player

Grain: one row per `player_id`. Columns: `first_seen_at`, `first_level`, `first_day`, `last_day`, `active_days`, `max_level`, `race`, `class` (most common valid value), `first_guild_day`, `reused_id`.

## dim_date

Grain: one row per calendar day, 2005-12-31 to 2009-01-10. Columns: `date`, `sweeps`, `coverage`, `low_coverage`, `interval_minutes`, `slow_sampling`, `is_lunar_new_year`, `event` (from `docs/event_calendar.csv`).

## agg_growth_accounting_monthly

Grain: one row per month from 2006-04 to 2008-12. Columns: `month_start`, `new_players`, `retained_players`, `resurrected_players`, `churned_players`, `mau`. **Metric parity:** must equal `metrics.monthly_growth_accounting` exactly (`tests/test_parity.py`).

## ml_churn_scores (teammate's churn model)

Grain: one row per (`player_id`, `as_of_date`). Columns: `churn_probability` (lapse in the next 30 days), `model_version`. Used by Q6 to replace the at-risk proxy.

## dau_forecast (teammate's forecast)

File `reports/dau_forecast.csv` with columns `date`, `dau_forecast`, `lower`, `upper`. Used by the opportunity sizing baseline.

## Reconciliation targets

The marts must match the pandas build on the full dataset. Current values are in `reports/headline_metrics.json` under `data_quality`: `sweeps`, `sessions`, `player_days`, `raw_avatars` and `reused_ids`. The paper's session count (667,032) cannot be matched by any session rule consistent with the data (see `decisions.md`).
