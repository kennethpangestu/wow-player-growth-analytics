# Tableau dashboard: WoW growth overview

One dashboard on Tableau Public, built from the extracts that `make analysis` writes to `reports/tableau/`. The dashboard must show the same DAU and MAU as the extracts (metric parity). Spot-check the numbers listed at the bottom after every rebuild.

## Data sources

| File | Grain | Used for |
|---|---|---|
| `daily_active.csv` | one row per day | DAU trend, stickiness, coverage flags |
| `growth_accounting_monthly.csv` | one row per month (2006-04 to 2008-12) | gains and losses bars, quick ratio |
| `cohort_retention.csv` | cohort month x months since start | retention heatmap |
| `launch_impact.csv` | launch x day | actual vs. expected DAU around each launch |

Set `date`, `month_start` and `cohort_start` to Date type. In `daily_active.csv`, filter out `low_coverage = True` on every sheet (data source filter), so the dashboard matches the analysis.

## Sheets

1. **DAU trend.** Line of `dau_adj`, 7-day moving average (table calculation: moving average of the previous 3, current and next 3). Reference lines on 2007-04-03 (The Burning Crusade) and 2008-11-19 (Wrath of the Lich King). Tooltip: date, raw `dau`, `dau_adj`, `mau`, `coverage`.
2. **Stickiness.** Line of `stickiness` (DAU/MAU), same filters, percent format.
3. **Where players come from.** Bars by `month_start`: `new` and `resurrected` stacked above zero, `churned` as a negative bar (calculated field `-[churned]`). Label `resurrected` as "Returning". Tooltip with `quick_ratio`.
4. **Cohort retention heatmap.** Rows `cohort_start` (month), columns `k` (1 to 12), color `share_active` on a single-hue sequential palette (light = low). Hide `k = 0`.
5. **Launch impact.** Two small multiples (filter on `launch`): `actual` and `counterfactual` by days from launch (calculated field `DATEDIFF('day', #launch date#, [date])`), with a 7-day moving average. Title each panel with the lift from `reports/headline_metrics.json`.

## Layout

Title "WoW Player Growth: Light's Hope realm, 2006 to 2009". Top row: KPI tiles (average DAU, average MAU, stickiness, TBC lift). Middle: DAU trend, full width. Bottom: growth accounting (left) and cohort heatmap (right). Second tab: launch impact. One date-range filter at the top applies to sheets 1 to 3. Colors: blue for actual/new, orange for returning/expected, aqua for churned, matching the README charts.

## Parity check (do this after every rebuild)

Compare against `reports/headline_metrics.json`:

- Average DAU (adjusted, excluding low-coverage days, from 2006-04-01): `q1.avg_dau`
- Average MAU over the same days: `q1.avg_mau`
- Peak DAU and its date: `q1.peak_dau`, `q1.peak_dau_date`
- MAU for 2007-04 in `growth_accounting_monthly.csv` vs. the dashboard bar total

If any differ, the dashboard filter or calculation is wrong, not the extract.

## Publishing

Publish to Tableau Public under the profile `kenneth.pangestu`, then add the link to the README under "Results at a glance".
