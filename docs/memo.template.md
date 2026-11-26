# Memo: what drives player growth on a WoW realm

**From:** Kenneth Pangestu (analytics and experimentation) · **Data:** {{data_quality.raw_avatars|int}} avatars on one Taiwanese realm, January 2006 to January 2009 · **Details:** [README](../README.md)

## Bottom line

The realm grew in launch-driven bursts and shrank slowly between them. Launches bring players in but don't keep them. Whether a new player stays is mostly settled in their first two weeks, and guilds are a lever we can pull. A guild recommendation for at-risk players is worth testing, but one realm only has enough players to detect a large effect.

## Findings

1. **Launches buy attention, not loyalty.** The Burning Crusade lifted DAU **{{q2.tbc.lift|pct0}}** over 8 weeks (95% CI {{q2.tbc.ci.0|pct0}} to {{q2.tbc.ci.1|pct0}}), fading from +{{q2.tbc.week1_lift|pct0}} in week 1 to +{{q2.tbc.last_full_week_lift|pct0}} in week 8. Wrath of the Lich King added {{q2.wotlk.lift|pct0}}. Players reactivated by the launch stuck around at their usual rate ({{q2.tbc.still_active_reactivated|pct0}} still active a month later vs. {{q2.tbc.still_active_already_active|pct0}} of already-active players), and only {{q2.tbc.still_active_new|pct0}} of launch-week new avatars lasted a month.
   *Recommendation:* plan launch follow-up (weeks 2 to 6) for reactivated players and new alts, the segments that fall off.

2. **The first week decides retention.** New avatars that play on **{{q3.aha_threshold|int}}+ of their first 7 days** are {{q3.aha_lift|x1}} as likely to be around at day 90 ({{q3.aha_retention_at_or_above|pct0}} vs. {{q3.aha_retention_below|pct1}}), but only {{q3.aha_share|pct0}} get there. Overall, {{q1.retention.d30|pct0}} of new avatars are active in days 30 to 59 and {{q1.retention.d90|pct0}} in days 90 to 119.
   *Recommendation:* make "come back on a second day" the onboarding goal and track it as a leading indicator.

3. **Guilds probably cause better retention.** Joining a guild in days 7 to 13 raises day-90 retention by **{{q3.guild.ipw_rd|pts1}} points** ({{q3.guild.ipw_control|pct1}} → {{q3.guild.ipw_treated|pct1}}, 95% CI {{q3.guild.ipw_rd_ci.0|pts1}} to {{q3.guild.ipw_rd_ci.1|pts1}}) after balancing on first-week behavior, down from a naive {{q3.guild.naive_rd|pts1}}. An unmeasured confounder would need a risk ratio of {{q3.guild.e_value|num1}} with both joining and retention to erase it.
   *Recommendation:* test a guild recommendation (below) rather than ship it on observational evidence.

4. **Test it with CUPED, a fixed horizon and an SRM check.** CUPED cuts the sample needed by {{q6.sample_size_cut|pct0}}. Even so, a 5% lift in active days needs {{q6.power_table.0.n_per_arm_cuped|int}} players per arm, about {{q6.power_table.0.four_week_cohorts_needed_cuped|int}} four-week windows' worth of this realm's at-risk players. A 20% lift needs {{q6.power_table.2.n_per_arm_cuped|int}}. Checking results daily would raise false positives from {{q6.peeking.false_positive_fixed|pct0}} to {{q6.peeking.false_positive_peeking|pct0}}.
   *Recommendation:* run it across realms, or on one realm for a 20%+ effect, for a fixed 28 days.

## What it's worth

One extra point of D30 retention is about **+{{sizing.extra_dau_at_horizon|num1}} DAU after 6 months** ({{sizing.extra_dau_share_at_horizon|pct1}} of current DAU) on this realm, a conservative figure that counts only play after day 30.

## How sure we are

High for the counts and the launch lifts. Every launch check (other windows, year-over-year, {{q2.placebo_n|int}} placebo dates) agrees for TBC. Moderate for the guild effect: it is observational, and an avatar is not a person. The data comes from one realm in 2006 to 2009, with known collection gaps (fixed in [docs/decisions.md](../docs/decisions.md)).

## Next

Swap the at-risk proxy for the churn model's scores, swap the 8-week DAU baseline for the teammate's forecast, and confirm the guild effect holds within the churn model's high-risk segment.
