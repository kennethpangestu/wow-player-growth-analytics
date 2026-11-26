# Experiment plan: guild recommendations for at-risk players

Numbers quoted here are filled in from `reports/headline_metrics.json` (`q6`), computed on real players by `scripts/run_analysis.py`. Edit `docs/experiment_plan.template.md`, not this file.

## Hypothesis

Q3 found that joining a guild in a player's second week raises day-90 retention by about {{q3.guild.ipw_rd|pts1}} points, after balancing on first-week behavior. If a "Guilds looking for members like you" recommendation gets more at-risk, unguilded players into a guild, they will play more days over the following four weeks.

## Design

| | |
|---|---|
| Population | Players active in the last 28 days, not in a guild, and at risk of lapsing. For now, "at risk" means fewer active days in the last 14 days than in the 14 before. It switches to the churn model's top-risk segment (`ml_churn_scores`) when that exists. |
| Unit of randomization | Player (avatar). Hash of `player_id` with an experiment salt, 50/50. |
| Treatment | A guild recommendation panel on login, with guilds matched on level band and play times. |
| Control | No panel (current experience). |
| Primary metric | Active days in the 28 days after assignment. |
| Secondary metrics | Active at all in days 14 to 27 after assignment; joined a guild within 14 days (the mechanism). |
| Guardrails | Minutes per active day (no drop), guild leave rate within 7 days of joining (no rise), and complaints or reports about guild invites. |
| Analysis | Difference in means on CUPED-adjusted active days (covariates: active days and hours in the 28 days before assignment), Welch t-test, two-sided alpha 0.05, 80% power. |
| Horizon | Fixed: 28 days of outcome after the last player is assigned. No early stopping on the primary metric. |

## Sample size

CUPED removes about {{q6.cuped_variance_reduction|pct0}} of the variance in the primary metric (pre-period active days correlate {{q6.corr_pre_days|num2}} with the outcome), which cuts the sample needed by the same share.

| Relative lift | Per arm, no CUPED | Per arm, CUPED |
|---|---|---|
| 5% | {{q6.power_table.0.n_per_arm_raw|int}} | {{q6.power_table.0.n_per_arm_cuped|int}} |
| 10% | {{q6.power_table.1.n_per_arm_raw|int}} | {{q6.power_table.1.n_per_arm_cuped|int}} |
| 20% | {{q6.power_table.2.n_per_arm_raw|int}} | {{q6.power_table.2.n_per_arm_cuped|int}} |

One realm produces about {{q6.at_risk_per_snapshot|int}} eligible players per four-week window, so on one realm only a 20% lift is realistic (about {{q6.power_table.2.four_week_cohorts_needed_cuped|num1}} windows). Across realms, or at the scale of a full player base, 5% is within reach.

## Checks before reading results

1. **Sample ratio mismatch.** Chi-square test of the 50/50 split. If p < 0.001 (for example, 52/48 on 10,000 players), stop and fix assignment first.
2. **A/A validation.** On historical data, random splits flag a false positive {{q6.aa.false_positive_raw|pct1}} of the time without CUPED and {{q6.aa.false_positive_cuped|pct1}} with it ({{q6.aa_sims|int}} simulated tests), so the test is calibrated.
3. **Effect injection.** Planting a +{{q6.sim_effect_relative|pct0}} lift in {{q6.sim_n_per_arm|int}} real players per arm, CUPED detects it {{q6.injection.power_cuped|pct0}} of the time vs. {{q6.injection.power_raw|pct0}} without, and both estimates are unbiased.
4. **No peeking.** Checking every day and stopping at the first p < 0.05 gives {{q6.peeking.false_positive_peeking|pct0}} false positives instead of {{q6.peeking.false_positive_fixed|pct0}}. If the team needs early reads, use a sequential test with an alpha-spending rule instead.

## Decision rule

Ship if the primary metric improves at p < 0.05, no guardrail worsens beyond its tolerance, and the guild-join rate rose (so the mechanism matches the story). If the primary metric is flat but guild joins rose, the recommendation works but guild membership alone does not move activity for at-risk players. In that case, look at guild quality (activity, size) before iterating.

## Code

- `population.py`: builds the historical at-risk population with pre-period covariates and outcomes.
- `design.py`: power and sample size, CUPED, SRM test, and the A/A, effect-injection and peeking simulations.
- Tests: `tests/test_experiments.py`.
