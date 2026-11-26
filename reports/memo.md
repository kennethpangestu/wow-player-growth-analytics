# Memo: what drives player growth on a WoW realm

**From:** Kenneth Pangestu (analytics and experimentation) · **Data:** 91,064 avatars on one Taiwanese realm, January 2006 to January 2009 · **Details:** [README](../README.md)

## Bottom line

The realm grew in launch-driven bursts and shrank slowly between them. Launches bring players in but don't keep them. Whether a new player stays is mostly settled in their first two weeks, and guilds are a lever we can pull. A guild recommendation for at-risk players is worth testing, but one realm only has enough players to detect a large effect.

## Findings

1. **Launches buy attention, not loyalty.** The Burning Crusade lifted DAU **44%** over 8 weeks (95% CI 38% to 52%), fading from +79% in week 1 to +24% in week 8. Wrath of the Lich King added 12%. Players reactivated by the launch stuck around at their usual rate (33% still active a month later vs. 68% of already-active players), and only 17% of launch-week new avatars lasted a month.
   *Recommendation:* plan launch follow-up (weeks 2 to 6) for reactivated players and new alts, the segments that fall off.

2. **The first week decides retention.** New avatars that play on **2+ of their first 7 days** are 4.7x as likely to be around at day 90 (22% vs. 4.8%), but only 39% get there. Overall, 18% of new avatars are active in days 30 to 59 and 12% in days 90 to 119.
   *Recommendation:* make "come back on a second day" the onboarding goal and track it as a leading indicator.

3. **Guilds probably cause better retention.** Joining a guild in days 7 to 13 raises day-90 retention by **8.7 points** (36.4% → 45.1%, 95% CI 5.6 to 12.0) after balancing on first-week behavior, down from a naive 12.8. An unmeasured confounder would need a risk ratio of 1.8 with both joining and retention to erase it.
   *Recommendation:* test a guild recommendation (below) rather than ship it on observational evidence.

4. **Test it with CUPED, a fixed horizon and an SRM check.** CUPED cuts the sample needed by 43%. Even so, a 5% lift in active days needs 20,745 players per arm, about 23 four-week windows' worth of this realm's at-risk players. A 20% lift needs 1,297. Checking results daily would raise false positives from 5% to 15%.
   *Recommendation:* run it across realms, or on one realm for a 20%+ effect, for a fixed 28 days.

## What it's worth

One extra point of D30 retention is about **+14.7 DAU after 6 months** (0.8% of current DAU) on this realm, a conservative figure that counts only play after day 30.

## How sure we are

High for the counts and the launch lifts. Every launch check (other windows, year-over-year, 36 placebo dates) agrees for TBC. Moderate for the guild effect: it is observational, and an avatar is not a person. The data comes from one realm in 2006 to 2009, with known collection gaps (fixed in [docs/decisions.md](../docs/decisions.md)).

## Next

Swap the at-risk proxy for the churn model's scores, swap the 8-week DAU baseline for the teammate's forecast, and confirm the guild effect holds within the churn model's high-risk segment.
