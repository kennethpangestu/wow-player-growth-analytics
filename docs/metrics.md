# Metric definitions

Drafted by Kenneth, to be signed off by both owners. After sign-off, any change is a pull request the other person approves. The code that implements each definition is named in brackets.

## Building blocks

| Term | Definition |
|---|---|
| Snapshot row | One avatar seen online in one `/who` query: `player_id, guild, level, race, class, where, datetime`. |
| Sweep | One full round of `/who` queries. Rows less than 3 minutes apart belong to the same sweep (inside a sweep, rows are seconds apart; between sweeps the collector idles about 5 minutes). [`data.sweep_table`] |
| Sweep minutes | The minutes of play one sweep stands for: the time until the next sweep, capped at 1.5 times the local typical interval so maintenance and outages never count as play. About 10 minutes until 2008-11-06, about 15 after. |
| Avatar | One `player_id`. IDs are anonymized character names, so an avatar is a character, not a person (alts are separate avatars). |
| Reused ID | An ID that looks shared by two characters: a level drop of more than 5 between sightings, or two race/class combinations each seen 20+ times. Counted in DAU/MAU; excluded from avatar-level analyses. [`data.reused_ids`] |
| Active day | A calendar day (server time) on which the avatar appears in at least one sweep. A sweep counts toward the day its first query ran. [`data.player_day`] |
| Session | A run of sightings of one avatar in consecutive collected sweeps, allowing one missed sweep. Sweeps that were never collected (maintenance, outages) never end a session. Session minutes add up sweep minutes. [`data.sessionize`] |
| Coverage | Share of a day's 1,440 minutes that collected sweeps stand for. Days under 0.5 are **low coverage**: they are flagged and left out of daily models and averages. [`data.daily_coverage`] |
| Slow-sampling day | A day whose median sweep interval is over 12.5 minutes (from 2008-11-07 on). |

## Activity

| Metric | Definition |
|---|---|
| DAU | Distinct avatars active on the day. |
| DAU (adjusted) | DAU divided by the slow-sampling capture rate on slow-sampling days, otherwise DAU. The capture rate comes from thinning full 10-minute days to 2 of every 3 sweeps. The headline series uses adjusted DAU. [`metrics.daily_active`] |
| WAU / MAU | Distinct avatars active in the trailing 7 / 28 days, including the day itself. |
| Stickiness | Adjusted DAU / MAU. |
| Minutes per DAU | Total sweep minutes of all avatars on the day / DAU. |

## Growth accounting (monthly)

For each calendar month M and each avatar active in M:

| State | Rule |
|---|---|
| New | M is the avatar's first active month ever. |
| Retained | Also active in M - 1. |
| Resurrected ("returning") | Active before M - 1, but not in M - 1. |
| Churned (counted in M) | Active in M - 1, not active in M. |

MAU(M) = new + retained + resurrected, and MAU(M) - MAU(M - 1) = new + resurrected - churned.
**Quick ratio** = (new + resurrected) / churned. Reporting starts in April 2006 (January to March 2006 are burn-in, since every avatar looks new at the start) and stops at the last complete month. [`metrics.monthly_growth_accounting`]

## New avatars and retention

| Term | Definition |
|---|---|
| New avatar | First active day on or after 2006-04-01, first seen at level 10 or below, not a Death Knight (they start at 55), not a reused ID. [`metrics.new_avatars`] |
| Day 0 | The new avatar's first active day. |
| D1 | Active on day 1. |
| D7 | Active on any of days 7 to 13. |
| D30 | Active on any of days 30 to 59. |
| D90 | Active on any of days 90 to 119. Cohorts need 120 days of data after day 0. |
| Cohort retention | For new avatars grouped by first active month: share active in each later calendar month. |

## Launches

| Term | Definition |
|---|---|
| Launch day | First day any avatar is above the old level cap (60 for The Burning Crusade, 70 for Wrath of the Lich King). [`launch.detect_launch_dates`] |
| Lift | Total adjusted DAU over the post-launch window / total counterfactual DAU - 1, over days that are not low coverage. Counterfactual: log DAU fit on a weekly trend, day of week and a Lunar New Year flag over the 84 days before launch, projected forward. [`launch.counterfactual_lift`] |
| Launch entrants | Avatars active in the first 14 days from launch. **Already active**: active in the 30 days before launch. **Reactivated**: active before, but not in the 30 days before launch. **New**: first seen on or after launch day. |
| Still active a month later | Active on any of days 30 to 43 after launch. |

## Experiment (Q6)

| Term | Definition |
|---|---|
| Eligible (at risk) | Active in the 28 days before assignment, not in a guild on their last active day, and fewer active days in the last 14 days than in the 14 before. To be replaced by `ml_churn_scores`. |
| Primary metric | Active days in the 28 days after assignment. |
| Secondary metric | Active on any of days 14 to 27 after assignment. |
| Guardrail | Minutes per active day in the 28 days after assignment. |
| CUPED covariates | Active days and hours in the 28 days before assignment. |
