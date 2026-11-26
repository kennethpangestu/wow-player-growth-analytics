# WoW Player Growth Analytics

[![CI](https://github.com/kennethpangestu/wow-player-growth-analytics/actions/workflows/ci.yml/badge.svg)](https://github.com/kennethpangestu/wow-player-growth-analytics/actions/workflows/ci.yml)

Three years of real World of Warcraft player telemetry ({{data_quality.raw_rows|m1}} sightings of {{data_quality.raw_avatars|int}} avatars, 2006 to 2009), analyzed the way a game growth team would. It covers where daily players come from, what an expansion launch actually buys, which first-week behaviors keep new players around, whether joining a guild causes better retention, and how to A/B test a fix.

A two-person project. **Kenneth Pangestu** owns analytics and experimentation (this README's results). **Teammate** owns the data platform and ML: the dbt warehouse, churn model, DAU forecast and Streamlit explorer, which are in progress.

> Every result in this README is filled in from [`reports/headline_metrics.json`](reports/headline_metrics.json), which the code writes. A test fails if the two ever disagree. The one-page summary is [`reports/memo.md`](reports/memo.md).

## Results at a glance

| Question | Answer |
|---|---|
| Where do monthly players come from? | Over {{q1.months|int}} months, new avatars brought in {{q1.share_gross_adds_new|pct0}} of gross monthly additions and returning players {{q1.share_gross_adds_resurrected|pct0}}. Swings in MAU came from new-avatar waves and churn ({{q1.mau_change_variance_share.new|pct0}} and {{q1.mau_change_variance_share.churned|pct0}} of the variance), not from returning players ({{q1.mau_change_variance_share.resurrected|pct0}}). |
| What did The Burning Crusade buy? | **+{{q2.tbc.lift|pct0}} DAU over 8 weeks** (95% CI {{q2.tbc.ci.0|pct0}} to {{q2.tbc.ci.1|pct0}}), from +{{q2.tbc.week1_lift|pct0}} in week 1 down to +{{q2.tbc.last_full_week_lift|pct0}} in week 8. Players it brought back were no stickier than ordinary returners ({{q2.tbc.still_active_reactivated|pct0}} still active a month later vs. {{q2.tbc.baseline_still_active_reactivated|pct0}}) and half as sticky as players who were already active ({{q2.tbc.still_active_already_active|pct0}}). |
| And Wrath of the Lich King? | A smaller **+{{q2.wotlk.lift|pct0}}** over {{q2.wotlk.post_days|int}} days (95% CI {{q2.wotlk.ci.0|pct0}} to {{q2.wotlk.ci.1|pct0}}). |
| Which first-week behavior predicts day-90 retention? | Playing on **{{q3.aha_threshold|int}} or more of the first 7 days**: {{q3.aha_retention_at_or_above|pct0}} of those avatars are still around at day 90, vs. {{q3.aha_retention_below|pct1}} of the rest ({{q3.aha_lift|x1}}). Only {{q3.aha_share|pct0}} of new avatars get there. |
| Does joining a guild cause higher retention? | Probably yes: joining in days 7 to 13 raises day-90 retention by **{{q3.guild.ipw_rd|pts1}} points** ({{q3.guild.ipw_control|pct1}} to {{q3.guild.ipw_treated|pct1}}, 95% CI {{q3.guild.ipw_rd_ci.0|pts1}} to {{q3.guild.ipw_rd_ci.1|pts1}}), after balancing on first-week behavior. The naive gap is {{q3.guild.naive_rd|pts1}} points. |
| Can we A/B test a guild recommendation on this realm? | Only for big effects. CUPED cuts the sample needed by **{{q6.sample_size_cut|pct0}}**, but detecting a 5% lift still takes {{q6.power_table.0.n_per_arm_cuped|int}} players per arm, about {{q6.power_table.0.four_week_cohorts_needed_cuped|int}} four-week windows of this realm's at-risk players. A 20% lift needs {{q6.power_table.2.n_per_arm_cuped|int}} per arm. |
| What is +1 point of D30 retention worth? | About **+{{sizing.extra_dau_at_horizon|num1}} DAU after 6 months** ({{sizing.extra_dau_share_at_horizon|pct1}} of today's {{sizing.baseline_dau|int}}), from {{sizing.new_avatars_per_day|int}} new avatars a day. |

![Daily active avatars](reports/figures/dau_history.png)

## The data

[World of Warcraft Avatar History (WoWAH)](http://web.cs.wpi.edu/~claypool/mmsys-dataset/2011/wow/), Lee, Chen, Cheng and Lei, MMSys 2011. A collector logged in to one Taiwanese realm (Light's Hope, Horde) and ran `/who` every 10 minutes from January 2006 to January 2009, recording every avatar online with its level, race, class, zone and guild. Avatar and guild names are replaced by consistent random integers.

Before any analysis, the data layer turns {{data_quality.raw_rows|int}} raw rows into {{data_quality.sweeps|int}} collection sweeps, {{data_quality.sessions|int}} sessions and {{data_quality.player_days|int}} player-days. Checking it turned up six things that change results if they're ignored:

1. **The collector slowed down on {{data_quality.slow_sampling_start|date}}**, from a sweep every 10 minutes to about every 15. Sparser sampling misses short logins, so I measured it: keeping 2 of every 3 sweeps on {{data_quality.thinning_days|int}} full days before the switch catches {{data_quality.thinning_dau_ratio|pct1}} of daily actives. DAU after the switch is scaled up by that factor, which matters because it covers the whole Wrath of the Lich King launch.
2. **Launch dates come from the data, not from US release dates.** The first avatar above level 60, the first Blood Elf and the first Paladin all appear on {{data_quality.launch_dates.tbc|date}} (The Burning Crusade), and the first avatar above level 70 and the first Death Knight on {{data_quality.launch_dates.wotlk|date}} (Wrath of the Lich King). Both are later than the North American launches.
3. **{{data_quality.reused_ids|int}} IDs belong to more than one character.** IDs are anonymized names, and names get reused after a character is deleted: {{data_quality.reused_ids_level_drop|int}} IDs drop more than 5 levels between sightings (levels never go down) and {{data_quality.reused_ids_two_characters|int}} show two different race/class combinations. They still count toward DAU and MAU, but they are left out of every analysis that follows individual avatars.
4. **Two waves of avatars that aren't ordinary sign-ups.** On {{data_quality.waves.1.first_day|date}}, {{data_quality.waves.1.new|int}} avatars appeared in a day, {{data_quality.waves.1.share_above_level_10|pct0}} already above level 10 (character transfers). On {{data_quality.waves.0.first_day|date}}, {{data_quality.waves.0.new|int}} appeared, and {{data_quality.waves.0.share_never_above_level_1|pct0}} never got past level 1 (throwaway or spam accounts). Both are in [`docs/event_calendar.csv`](docs/event_calendar.csv) and stay out of the launch baselines.
5. **Maintenance gaps don't end sessions.** Thursday maintenance takes out 8 hours of sweeps every week, and {{data_quality.days_without_data|int}} days have no data at all. Sessions are built on collected sweeps only, so a gap in collection is never counted as a player logging off. Days with under half their normal coverage ({{data_quality.low_coverage_days|int}} of them) are left out of daily models.
6. **The paper's session count doesn't reconcile.** The authors report {{data_quality.paper.sessions|int}} sessions, but the data has {{data_quality.player_days|int}} player-days, so the average session would have to cover about three calendar days. No gap rule gets close: counts run from {{data_quality.sessions_no_missed_sweeps|int}} (no missed sweeps allowed) to {{data_quality.sessions_six_missed_sweeps|int}} (six allowed). I use {{data_quality.sessions|int}}, allowing one missed sweep inside a session. The avatar count matches the paper to within 1 ({{data_quality.raw_avatars|int}} vs. {{data_quality.paper.avatars|int}}).

Rules and thresholds are defined in [`docs/metrics.md`](docs/metrics.md) and every judgment call is logged in [`docs/decisions.md`](docs/decisions.md).

## Q1. Growth accounting: where do active players come from?

![Monthly growth accounting](reports/figures/growth_accounting.png)

Each month every active avatar is **new** (first month ever), **retained** (also active last month) or **returning** (active before, but not last month). Avatars active last month but not this one have **churned**. From {{q1.first_month|str}} to {{q1.last_month|str}} (the first three months are burn-in, since everyone active at the start looks new):

- An average month gained {{q1.avg_new_per_month|int}} new and {{q1.avg_resurrected_per_month|int}} returning avatars and lost {{q1.avg_churned_per_month|int}}. The quick ratio ((new + returning) / churned) was above 1 in only {{q1.months_quick_ratio_above_1|int}} of {{q1.months|int}} months, with a median of {{q1.median_quick_ratio|num2}}. Outside launch months the realm was slowly shrinking.
- Month-to-month MAU changes are explained by new-avatar inflow ({{q1.mau_change_variance_share.new|pct0}} of the variance) and churn ({{q1.mau_change_variance_share.churned|pct0}}). Returning players are a steady {{q1.avg_resurrected_per_month|int}} a month and explain only {{q1.mau_change_variance_share.resurrected|pct0}}. Without the two anomaly months the split is {{q1.mau_change_variance_share_without_anomaly_months.new|pct0}} new, {{q1.mau_change_variance_share_without_anomaly_months.churned|pct0}} churn and {{q1.mau_change_variance_share_without_anomaly_months.resurrected|pct0}} returning.
- Average DAU was {{q1.avg_dau|int}} and MAU (28-day) {{q1.avg_mau|int}}, for a DAU/MAU stickiness of {{q1.avg_stickiness|pct0}}. Peak DAU was {{q1.peak_dau|int}} on {{q1.peak_dau_date|date}}, the day after The Burning Crusade went live.
- Of {{q1.new_avatar_cohort|int}} new avatars, {{q1.retention.d1|pct0}} came back the next day, {{q1.retention.d7|pct0}} in days 7 to 13, {{q1.retention.d30|pct0}} in days 30 to 59 and {{q1.retention.d90|pct0}} in days 90 to 119.

![Cohort retention](reports/figures/cohort_retention.png)

**So what.** Growth on this realm came in launch-driven bursts of new avatars, and churn was the steady drain. Returning players are a reliable base, not a lever that moves MAU. The biggest opportunity is the first week, where most new avatars are lost (see Q3). *Confidence:* high for the counts. *Caveat:* alts look like new avatars, so "new" overstates new people.

## Q2. Launch impact: what does an expansion buy?

![Launch impact](reports/figures/launch_impact.png)

For each launch I fit log DAU on a trend, day-of-week and Lunar New Year over the 12 weeks before, projected it over the weeks after, and compared. The interval comes from a moving-block bootstrap. Three checks back it up: other pre-period windows (8 and 16 weeks with a trend, 4 weeks flat), a year-over-year comparison of the same calendar weeks, and the same estimator at {{q2.placebo_n|int}} placebo dates with no launch.

| | The Burning Crusade | Wrath of the Lich King |
|---|---|---|
| DAU lift over the post-launch window | **+{{q2.tbc.lift|pct0}}** (95% CI {{q2.tbc.ci.0|pct0}} to {{q2.tbc.ci.1|pct0}}) | **+{{q2.wotlk.lift|pct0}}** (95% CI {{q2.wotlk.ci.0|pct0}} to {{q2.wotlk.ci.1|pct0}}) |
| Actual vs. expected average DAU | {{q2.tbc.actual_dau|int}} vs. {{q2.tbc.counterfactual_dau|int}} | {{q2.wotlk.actual_dau|int}} vs. {{q2.wotlk.counterfactual_dau|int}} |
| Other pre-period windows | +{{q2.tbc.sensitivity_min|pct0}} to +{{q2.tbc.sensitivity_max|pct0}} | +{{q2.wotlk.sensitivity_min|pct0}} to +{{q2.wotlk.sensitivity_max|pct0}} |
| Year-over-year check | +{{q2.tbc.yoy.lift|pct0}} | +{{q2.wotlk.yoy.lift|pct0}} |
| Share of the {{q2.placebo_n|int}} placebo dates with a lift this large | {{q2.tbc.placebo_share_as_large|pct0}} | {{q2.wotlk.placebo_share_as_large|pct0}} |
| Week 1 → last full week | +{{q2.tbc.week1_lift|pct0}} → +{{q2.tbc.last_full_week_lift|pct0}} | +{{q2.wotlk.week1_lift|pct0}} → +{{q2.wotlk.last_full_week_lift|pct0}} |

Placebo lifts have a standard deviation of {{q2.placebo_sd|pct1}} and reach at most {{q2.placebo_max_abs|pct0}} in absolute value, so both launches are well outside normal noise. For Wrath, leaving the October 2008 level-1 wave inside the baseline would inflate it and cut the estimate to +{{q2.wotlk.lift_with_anomaly_days_in_fit|pct0}} (95% CI {{q2.wotlk.ci_with_anomaly_days_in_fit.0|spct0}} to {{q2.wotlk.ci_with_anomaly_days_in_fit.1|spct0}}).

**Did the players it brought back stay?** Avatars active in the two weeks after each launch, by what they were doing in the 30 days before, and whether they were active again in days 30 to 43:

| | Burning Crusade: share of entrants | Still active a month later | Same segment 13 weeks earlier |
|---|---|---|---|
| Already active | {{q2.tbc.share_already_active|pct0}} | {{q2.tbc.still_active_already_active|pct0}} | |
| Reactivated (lapsed 30+ days) | {{q2.tbc.share_reactivated|pct0}} | {{q2.tbc.still_active_reactivated|pct0}} | {{q2.tbc.baseline_still_active_reactivated|pct0}} |
| New avatars | {{q2.tbc.share_new|pct0}} | {{q2.tbc.still_active_new|pct0}} | {{q2.tbc.baseline_still_active_new|pct0}} |

For Wrath of the Lich King: {{q2.wotlk.still_active_reactivated|pct0}} of reactivated players were still active a month later ({{q2.wotlk.baseline_still_active_reactivated|pct0}} for ordinary returners), vs. {{q2.wotlk.still_active_already_active|pct0}} of already-active players.

**So what.** The Burning Crusade was a very large event, about {{q2.tbc.extra_player_days|int}} extra player-days in 8 weeks. But more than half of the avatars who showed up in launch weeks were new (largely Blood Elf alts) and only {{q2.tbc.still_active_new|pct0}} of them were around a month later, and reactivated players lapsed again at their usual rate. A launch buys attention, not loyalty. The follow-up that pays is a re-engagement plan for the weeks after launch, aimed at reactivated players and fresh alts. *Confidence:* high for TBC (every check agrees), moderate for Wrath (shorter window, slower sampling, and the anomaly decision moves it). *Caveat:* one realm, and observational: the counterfactual assumes the pre-launch trend would have continued.

## Q3. Early behaviors: what keeps new players around?

![Retention by first-week activity](reports/figures/aha_week1_days.png)

**The "aha" threshold.** I scanned thresholds on five first-week behaviors for {{q3.cohort|int}} new avatars and scored each by how cleanly it separates avatars still active at day 90 from the rest (Youden's J). The best single signal is playing on **{{q3.aha_threshold|int}} or more of the first 7 days**. {{q3.aha_share|pct0}} of new avatars do, and {{q3.aha_retention_at_or_above|pct0}} of them are active in days 90 to 119, vs. {{q3.aha_retention_below|pct1}} of the rest. Sessions, hours played and levels gained come next ([`reports/tables/q3_aha_best.csv`](reports/tables/q3_aha_best.csv)). This is correlation: it tells us who to watch, not what causes retention.

**Does joining a guild cause higher retention?** Only {{q3.guild_in_week1_share|pct0}} of new avatars are in a guild by the end of week 1. To get a causal estimate the timeline is kept strict:

- days 0 to 6: baseline behavior (active days, hours, sessions, levels, class, race, start quarter); avatars already in a guild are excluded
- days 7 to 13: treatment, joining a first guild, among avatars active at least once that week
- days 90 to 119: outcome, active at least once

{{q3.guild.n_treated|int}} of {{q3.guild.n|int}} eligible avatars joined a guild in week 2. A propensity model reweights the {{q3.guild.controls|int}} controls to look like the joiners (largest standardized difference {{q3.guild.max_abs_smd_before|num2}} before, {{q3.guild.max_abs_smd_after|num2}} after; effective control sample {{q3.guild.control_effective_n|int}}).

![Guild effect](reports/figures/guild_effect.png)

| Estimate | Day-90 retention: joiners vs. comparable non-joiners | Difference |
|---|---|---|
| Naive | {{q3.guild.naive_treated|pct1}} vs. {{q3.guild.naive_control|pct1}} | +{{q3.guild.naive_rd|pts1}} pts |
| Inverse propensity weighting | {{q3.guild.ipw_treated|pct1}} vs. {{q3.guild.ipw_control|pct1}} | **+{{q3.guild.ipw_rd|pts1}} pts** (95% CI {{q3.guild.ipw_rd_ci.0|pts1}} to {{q3.guild.ipw_rd_ci.1|pts1}}) |
| 1:1 matching on the propensity score | | +{{q3.guild.match_rd|pts1}} pts |

The risk ratio is {{q3.guild.ipw_rr|num2}}. Its **E-value is {{q3.guild.e_value|num2}}** ({{q3.guild.e_value_ci|num2}} for the lower confidence bound): an unmeasured confounder would need to raise both the chance of joining and the chance of being retained by about {{q3.guild.e_value|num1}}x, beyond everything already controlled for, to explain the effect away.

**So what.** About {{q3.guild.selection_share_of_naive_gap|pct0}} of the raw guild gap is selection (engaged players join guilds), but a real effect of about {{q3.guild.ipw_rd|pts1}} points survives. That makes guild joining in week 2 a credible lever, and it is worth an experiment (Q6). *Confidence:* moderate. *Caveats:* observational, an avatar is not a person, and "joined a guild" may stand in for having friends in the game.

## Q6. Experiment design: testing a guild recommendation

The feature would recommend guilds to at-risk players who aren't in one. Until the churn model's scores land, "at risk" means fewer active days in the last 14 days than in the 14 before. Pooling {{q6.reference_dates|int}} historical four-week windows gives {{q6.population_rows|int}} player-windows of real data, about {{q6.at_risk_per_snapshot|int}} eligible players per window.

- **Primary metric:** active days in the 28 days after assignment (mean {{q6.y_mean|num2}}, SD {{q6.y_sd|num2}}; {{q6.y_share_zero|pct0}} of players have zero). **Secondary:** active at all in days 14 to 27 (baseline {{q6.secondary_retained_rate|pct0}}; +2 points needs {{q6.secondary_n_per_arm_2pts|int}} per arm). **Guardrail:** minutes per active day must not fall, since a recommendation spammed at players could annoy them.
- **CUPED** with pre-period active days and hours (correlation {{q6.corr_pre_days|num2}}) removes {{q6.cuped_variance_reduction|pct0}} of the variance, cutting the sample needed by {{q6.sample_size_cut|pct0}}.

| Lift to detect (relative) | Per arm, no CUPED | Per arm, CUPED | Four-week windows of this realm |
|---|---|---|---|
| 5% | {{q6.power_table.0.n_per_arm_raw|int}} | {{q6.power_table.0.n_per_arm_cuped|int}} | {{q6.power_table.0.four_week_cohorts_needed_cuped|num1}} |
| 10% | {{q6.power_table.1.n_per_arm_raw|int}} | {{q6.power_table.1.n_per_arm_cuped|int}} | {{q6.power_table.1.four_week_cohorts_needed_cuped|num1}} |
| 20% | {{q6.power_table.2.n_per_arm_raw|int}} | {{q6.power_table.2.n_per_arm_cuped|int}} | {{q6.power_table.2.four_week_cohorts_needed_cuped|num1}} |

![Power curves](reports/figures/power_curves.png)

**Checked by simulation on the real players:**

- **A/A tests** (random splits, no treatment): false-positive rates of {{q6.aa.false_positive_raw|pct1}} without CUPED and {{q6.aa.false_positive_cuped|pct1}} with it across {{q6.aa_sims|int}} tests, close to the 5% target.
- **Effect injection:** planting a +{{q6.sim_effect_relative|pct0}} lift ({{q6.injection.true_effect|num2}} days) in {{q6.sim_n_per_arm|int}} players per arm, CUPED detects it {{q6.injection.power_cuped|pct0}} of the time (the design target is 80%) vs. {{q6.injection.power_raw|pct0}} without. Both estimates are unbiased (average {{q6.injection.mean_estimate_cuped|num2}} days).
- **Peeking:** checking an A/A test every day and stopping at the first p < 0.05 gives a false positive {{q6.peeking.false_positive_peeking|pct0}} of the time, vs. {{q6.peeking.false_positive_fixed|pct1}} at a fixed 28-day horizon. Half of those false alarms come by day {{q6.peeking.median_first_false_alarm_day|int}}. Fix the horizon, or use a sequential test.
- **Sample ratio mismatch:** a 52/48 split on 10,000 players gives p {{q6.srm_example_p_52|p}}, so the test is stopped and the assignment debugged before anyone reads the metrics.

**So what.** Run it as a fixed-horizon 28-day test with CUPED. On one realm, target a lift of 20% or more, or run it across realms; with a whole game's player base, a 5% lift is well within reach. The full plan is in [`experiments/README.md`](experiments/README.md).

## Opportunity sizing

Raising D30 retention by 1 point keeps 1% more of each day's {{sizing.new_avatars_per_day|int}} new avatars past day 30, and each of them then plays like a typical retained avatar. Summed over 6 months of arrivals, that is **+{{sizing.extra_dau_at_horizon|num1}} DAU at month 6** ({{sizing.extra_dau_share_at_horizon|pct1}} of {{sizing.baseline_dau|int}}, the {{sizing.baseline_source|str}}) and {{sizing.extra_player_days_over_horizon|int}} extra player-days. It ignores any extra play before day 30, so it errs low. When the teammate's DAU forecast lands in `reports/dau_forecast.csv`, the baseline switches to it automatically.

## How to run it

```bash
pip install -r requirements.txt
make data       # download the dataset (318 MB) and check its SHA-256
make analysis   # build tables, run Q1-Q6 and sizing, write reports/ (about 2 minutes)
make docs       # fill README.md, reports/memo.md and experiments/README.md from the metrics JSON
make test       # unit tests (CI also runs the whole pipeline on a synthetic fixture)
make all        # all of the above
```

```
ingest/download.py        download and verify the dataset
growth/data.py            snapshots -> sweeps, sessions, player-days, avatars (+ data quality)
growth/metrics.py         Q1: DAU/WAU/MAU, growth accounting, cohort retention
growth/launch.py          Q2: counterfactual lift, placebos, year-over-year, launch cohorts
growth/early.py           Q3: aha thresholds, propensity weighting and matching, E-values
growth/sizing.py          opportunity sizing
experiments/              Q6: at-risk population, power, CUPED, A/A, effect injection, peeking, SRM
scripts/run_analysis.py   runs everything and writes reports/
scripts/render_docs.py    fills README, memo and experiment plan from headline_metrics.json
scripts/make_fixture.py   synthetic data for CI
reports/                  headline_metrics.json, tables/, tableau/ extracts, figures/, memo.md
dashboards/SPEC.md        the Tableau growth dashboard
docs/                     metric definitions, data contract, decisions, event calendar
```

## Caveats

- One Taiwanese Horde realm, 2006 to 2009. Patterns may not carry over to other realms, regions or today's games.
- An avatar is not a player. Alts look like new players, and players who switch characters look like churn.
- Sessions and minutes are inferred from 10- or 15-minute snapshots, so short logins are missed.
- Left censoring: avatars active in early 2006 are not new, hence the 3-month burn-in. Right censoring: day-90 retention needs 120 days of future data, so cohorts after mid-September 2008 are left out.
- Q2 and Q3 are observational. Their assumptions are stated above, and the sensitivity checks show how far the conclusions can move.

## Citation

Y.-T. Lee, K.-T. Chen, Y.-M. Cheng and C.-L. Lei, "World of Warcraft Avatar History Dataset," *Proceedings of ACM Multimedia Systems (MMSys)*, 2011. The authors make the dataset free to download for research. It is not included in this repo. The parquet conversion used here is by Vincent Warmerdam ([koaning/wow-avatar-datasets](https://github.com/koaning/wow-avatar-datasets)).

World of Warcraft is a trademark of Blizzard Entertainment, now part of Microsoft Gaming. This project is not affiliated with either.

## License

MIT
