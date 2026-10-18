# Phase H - controlled PPO training and held-out evaluation (v8)

- configuration: `recommended()` (share + ledger + market_weighted + inflated targets + 6-month reserve)
- reward versions: archived_v1, candidate_a (archived reward never modified)
- seeds: [7, 17, 27]; timesteps per run: 50,000
- split `fresh_split_v1`: 48 train / 16 validation / 16 held-out test
- checkpoint selection: validation partition only (`EvalCallback`)
- total affordability violations across every arm: 0
- maximum budget-identity residual: 0.000000000007

## 1. Training runs

| reward version | seed | timesteps | seconds | steps/s | episodes | mean train return |
|---|---:|---:|---:|---:|---:|---:|
| archived_v1 | 7 | 50,000 | 503.2 | 99 | 353 | -13.575 |
| archived_v1 | 17 | 50,000 | 407.6 | 123 | 353 | -14.384 |
| archived_v1 | 27 | 50,000 | 409.6 | 122 | 353 | -14.379 |
| candidate_a | 7 | 50,000 | 413.2 | 121 | 353 | -54.063 |
| candidate_a | 17 | 50,000 | 769.4 | 65 | 353 | -55.180 |
| candidate_a | 27 | 50,000 | 295.5 | 169 | 353 | -54.552 |

Hardware: CPU only (torch CPU build); total training wall time 46.6 minutes across 6 runs.

## 2. Held-out test results (all 16 fresh test users, identical data and config)

| arm | seeds | weighted_goal_achievement | pct_goals_fully_funded | pct_goals_met_by_deadline | net_worth | goal_level_shortfall | investment_cap_overflow | total_interest_paid |
|---|---|---|---|---|---|---|---|---|---|
| investment-only | — | 0.5800 | 0.4656 | 0.1427 | 2,751,776.9413 | 8,567,393.7363 | 1,479,047.9740 | 0.0000 |
| mixed allocation | — | 0.5800 | 0.4656 | 0.1427 | 2,751,776.9413 | 8,567,393.7363 | 439,155.5328 | 0.0000 |
| uniform savings | — | 0.5584 | 0.4531 | 0.1427 | 2,363,889.6201 | 8,783,225.8515 | 0.0000 | 0.0000 |
| RL archived_v1 | 3 | 0.4842 | 0.3674 | 0.1083 | 2,659,501.9973 | 8,973,439.6004 | 776,631.2169 | 8,637.9353 |
| RL candidate_a | 3 | 0.4398 | 0.3059 | 0.0892 | 2,633,769.5675 | 8,862,778.9395 | 355,556.2781 | 20,046.8013 |
| urgency | — | 0.4051 | 0.0625 | 0.0000 | 2,363,889.6201 | 8,125,196.7095 | 0.0000 | 0.0000 |
| need-proportional savings | — | 0.3211 | 0.0625 | 0.0000 | 2,363,889.6201 | 8,125,196.7095 | 0.0000 | 0.0000 |
| constrained_LP | — | 0.2452 | 0.2323 | 0.1531 | 2,606,859.4951 | 9,192,529.4911 | 0.0082 | 11,357.3903 |

Sources: `ppo_v8_summary.csv`, `ppo_v8_detail.csv`.

### 2.1 RL arms - spread across seeds

| arm | seeds | weighted_goal_achievement (mean) | pct_goals_fully_funded (mean) | pct_goals_met_by_deadline (mean) |
|---|---|---|---|---|
| RL archived_v1 | 3 | 0.4842 | 0.3674 | 0.1083 |
| RL candidate_a | 3 | 0.4398 | 0.3059 | 0.0892 |

Across-seed standard deviations: RL archived_v1: weighted_goal_achievement=0.0554, pct_goals_fully_funded=0.0664, pct_goals_met_by_deadline=0.0156; RL candidate_a: weighted_goal_achievement=0.0852, pct_goals_fully_funded=0.1154, pct_goals_met_by_deadline=0.0539.

### 2.2 By financial-feasibility group

Eligibility is ex-ante: `monthly_income - monthly_expenditure - monthly_emi > 0`. For the RL arms the `users` column counts user-seed observations (users x seeds), not distinct users.

| cohort | arm | users | weighted_goal_achievement | pct_goals_met_by_deadline | net_worth |
|---|---|---:|---:|---:|---:|
| surplus>0 | investment-only | 14 | 0.6628 | 0.1631 | 3,137,257.37 |
| surplus>0 | mixed allocation | 14 | 0.6628 | 0.1631 | 3,137,257.37 |
| surplus>0 | uniform savings | 14 | 0.6382 | 0.1631 | 2,693,957.58 |
| surplus>0 | RL archived_v1 | 42 | 0.5534 | 0.1238 | 3,031,800.29 |
| surplus>0 | RL candidate_a | 42 | 0.5026 | 0.1020 | 3,002,391.80 |
| surplus>0 | urgency | 14 | 0.4630 | 0.0000 | 2,693,957.58 |
| surplus>0 | need-proportional savings | 14 | 0.3669 | 0.0000 | 2,693,957.58 |
| surplus>0 | constrained_LP | 14 | 0.2803 | 0.1750 | 2,971,637.43 |
| zero-surplus | investment-only | 2 | 0.0000 | 0.0000 | 53,413.92 |
| zero-surplus | mixed allocation | 2 | 0.0000 | 0.0000 | 53,413.92 |
| zero-surplus | uniform savings | 2 | 0.0000 | 0.0000 | 53,413.92 |
| zero-surplus | RL archived_v1 | 6 | 0.0000 | 0.0000 | 53,413.92 |
| zero-surplus | RL candidate_a | 6 | 0.0000 | 0.0000 | 53,413.92 |
| zero-surplus | urgency | 2 | 0.0000 | 0.0000 | 53,413.92 |
| zero-surplus | need-proportional savings | 2 | 0.0000 | 0.0000 | 53,413.92 |
| zero-surplus | constrained_LP | 2 | 0.0000 | 0.0000 | 53,413.92 |

## 3. Paired, user-level differences (RL mean over seeds minus each baseline)

| RL arm | baseline | metric | better? | mean diff | CI95 | significant? |
|---|---|---|---|---:|---|---|
| RL archived_v1 | uniform savings | weighted_goal_achievement | uniform savings | -0.0742 | [-0.1187, -0.0298] | yes |
| RL archived_v1 | uniform savings | pct_goals_fully_funded | uniform savings | -0.0858 | [-0.1566, -0.0267] | yes |
| RL archived_v1 | uniform savings | pct_goals_met_by_deadline | — | -0.0344 | [-0.0813, 0.0090] | inconclusive |
| RL archived_v1 | uniform savings | investment_cap_overflow | uniform savings | 776,631.2169 | [461,235.0322, 1,121,203.8040] | yes |
| RL archived_v1 | uniform savings | net_worth | **RL archived_v1** | 295,612.3771 | [140,601.5505, 500,642.5032] | yes |
| RL archived_v1 | investment-only | weighted_goal_achievement | investment-only | -0.0957 | [-0.1423, -0.0497] | yes |
| RL archived_v1 | investment-only | pct_goals_fully_funded | investment-only | -0.0983 | [-0.1795, -0.0302] | yes |
| RL archived_v1 | investment-only | pct_goals_met_by_deadline | — | -0.0344 | [-0.0813, 0.0090] | inconclusive |
| RL archived_v1 | investment-only | investment_cap_overflow | **RL archived_v1** | -702,416.7571 | [-1,054,260.3176, -380,766.5092] | yes |
| RL archived_v1 | investment-only | net_worth | investment-only | -92,274.9440 | [-179,273.4553, -25,523.2822] | yes |
| RL archived_v1 | mixed allocation | weighted_goal_achievement | mixed allocation | -0.0957 | [-0.1423, -0.0497] | yes |
| RL archived_v1 | mixed allocation | pct_goals_fully_funded | mixed allocation | -0.0983 | [-0.1795, -0.0302] | yes |
| RL archived_v1 | mixed allocation | pct_goals_met_by_deadline | — | -0.0344 | [-0.0813, 0.0090] | inconclusive |
| RL archived_v1 | mixed allocation | investment_cap_overflow | mixed allocation | 337,475.6841 | [180,364.3030, 530,487.2832] | yes |
| RL archived_v1 | mixed allocation | net_worth | mixed allocation | -92,274.9440 | [-179,273.4553, -25,523.2822] | yes |
| RL archived_v1 | need-proportional savings | weighted_goal_achievement | **RL archived_v1** | 0.1632 | [0.0628, 0.2604] | yes |
| RL archived_v1 | need-proportional savings | pct_goals_fully_funded | **RL archived_v1** | 0.3049 | [0.1788, 0.4219] | yes |
| RL archived_v1 | need-proportional savings | pct_goals_met_by_deadline | **RL archived_v1** | 0.1083 | [0.0521, 0.1684] | yes |
| RL archived_v1 | need-proportional savings | investment_cap_overflow | need-proportional savings | 776,631.2169 | [461,235.0322, 1,121,203.8040] | yes |
| RL archived_v1 | need-proportional savings | net_worth | **RL archived_v1** | 295,612.3771 | [140,601.5505, 500,642.5032] | yes |
| RL archived_v1 | urgency | weighted_goal_achievement | **RL archived_v1** | 0.0791 | [0.0076, 0.1504] | yes |
| RL archived_v1 | urgency | pct_goals_fully_funded | **RL archived_v1** | 0.3049 | [0.1788, 0.4219] | yes |
| RL archived_v1 | urgency | pct_goals_met_by_deadline | **RL archived_v1** | 0.1083 | [0.0521, 0.1684] | yes |
| RL archived_v1 | urgency | investment_cap_overflow | urgency | 776,631.2169 | [461,235.0322, 1,121,203.8040] | yes |
| RL archived_v1 | urgency | net_worth | **RL archived_v1** | 295,612.3771 | [140,601.5505, 500,642.5032] | yes |
| RL archived_v1 | constrained_LP | weighted_goal_achievement | **RL archived_v1** | 0.2390 | [0.1516, 0.3214] | yes |
| RL archived_v1 | constrained_LP | pct_goals_fully_funded | **RL archived_v1** | 0.1351 | [0.0615, 0.2066] | yes |
| RL archived_v1 | constrained_LP | pct_goals_met_by_deadline | — | -0.0448 | [-0.1083, 0.0174] | inconclusive |
| RL archived_v1 | constrained_LP | investment_cap_overflow | constrained_LP | 776,631.2087 | [461,235.0256, 1,121,203.7754] | yes |
| RL archived_v1 | constrained_LP | net_worth | **RL archived_v1** | 52,642.5022 | [3,889.5551, 102,614.7510] | yes |
| RL candidate_a | uniform savings | weighted_goal_achievement | uniform savings | -0.1187 | [-0.1619, -0.0774] | yes |
| RL candidate_a | uniform savings | pct_goals_fully_funded | uniform savings | -0.1472 | [-0.2115, -0.0896] | yes |
| RL candidate_a | uniform savings | pct_goals_met_by_deadline | uniform savings | -0.0535 | [-0.1031, -0.0035] | yes |
| RL candidate_a | uniform savings | investment_cap_overflow | uniform savings | 355,556.2781 | [203,092.3802, 523,003.8786] | yes |
| RL candidate_a | uniform savings | net_worth | **RL candidate_a** | 269,879.9474 | [128,944.0477, 443,362.3677] | yes |
| RL candidate_a | investment-only | weighted_goal_achievement | investment-only | -0.1402 | [-0.1876, -0.0948] | yes |
| RL candidate_a | investment-only | pct_goals_fully_funded | investment-only | -0.1597 | [-0.2208, -0.1045] | yes |
| RL candidate_a | investment-only | pct_goals_met_by_deadline | investment-only | -0.0535 | [-0.1031, -0.0035] | yes |
| RL candidate_a | investment-only | investment_cap_overflow | **RL candidate_a** | -1,123,491.6960 | [-1,720,499.0673, -591,092.4839] | yes |
| RL candidate_a | investment-only | net_worth | investment-only | -118,007.3738 | [-200,482.3891, -49,783.4621] | yes |
| RL candidate_a | mixed allocation | weighted_goal_achievement | mixed allocation | -0.1402 | [-0.1876, -0.0948] | yes |
| RL candidate_a | mixed allocation | pct_goals_fully_funded | mixed allocation | -0.1597 | [-0.2208, -0.1045] | yes |
| RL candidate_a | mixed allocation | pct_goals_met_by_deadline | mixed allocation | -0.0535 | [-0.1031, -0.0035] | yes |
| RL candidate_a | mixed allocation | investment_cap_overflow | — | -83,599.2547 | [-226,462.7052, 54,503.9434] | inconclusive |
| RL candidate_a | mixed allocation | net_worth | mixed allocation | -118,007.3738 | [-200,482.3891, -49,783.4621] | yes |
| RL candidate_a | need-proportional savings | weighted_goal_achievement | **RL candidate_a** | 0.1187 | [0.0291, 0.2043] | yes |
| RL candidate_a | need-proportional savings | pct_goals_fully_funded | **RL candidate_a** | 0.2434 | [0.1069, 0.3535] | yes |
| RL candidate_a | need-proportional savings | pct_goals_met_by_deadline | **RL candidate_a** | 0.0892 | [0.0535, 0.1267] | yes |
| RL candidate_a | need-proportional savings | investment_cap_overflow | need-proportional savings | 355,556.2781 | [203,092.3802, 523,003.8786] | yes |
| RL candidate_a | need-proportional savings | net_worth | **RL candidate_a** | 269,879.9474 | [128,944.0477, 443,362.3677] | yes |
| RL candidate_a | urgency | weighted_goal_achievement | — | 0.0347 | [-0.0442, 0.1209] | inconclusive |
| RL candidate_a | urgency | pct_goals_fully_funded | **RL candidate_a** | 0.2434 | [0.1069, 0.3535] | yes |
| RL candidate_a | urgency | pct_goals_met_by_deadline | **RL candidate_a** | 0.0892 | [0.0535, 0.1267] | yes |
| RL candidate_a | urgency | investment_cap_overflow | urgency | 355,556.2781 | [203,092.3802, 523,003.8786] | yes |
| RL candidate_a | urgency | net_worth | **RL candidate_a** | 269,879.9474 | [128,944.0477, 443,362.3677] | yes |
| RL candidate_a | constrained_LP | weighted_goal_achievement | **RL candidate_a** | 0.1945 | [0.1024, 0.2861] | yes |
| RL candidate_a | constrained_LP | pct_goals_fully_funded | — | 0.0736 | [-0.0007, 0.1396] | inconclusive |
| RL candidate_a | constrained_LP | pct_goals_met_by_deadline | — | -0.0639 | [-0.1455, 0.0163] | inconclusive |
| RL candidate_a | constrained_LP | investment_cap_overflow | constrained_LP | 355,556.2698 | [203,092.3689, 523,003.8688] | yes |
| RL candidate_a | constrained_LP | net_worth | — | 26,910.0725 | [-37,425.2874, 102,243.0576] | inconclusive |

Direction is respected: for `investment_cap_overflow` a *lower* value is the better outcome, so a positive difference means the RL arm did worse, not better.
Bootstrap intervals resample users (the independent unit); a verdict of `inconclusive` means the interval spans zero and no difference is claimed.

## 4. What the run supports

1. Highest mean weighted achievement: **investment-only** (0.5800).
2. Best RL arm: **RL archived_v1** (0.4842) — not above the best non-RL arm by 0.0957.
3. Significant paired verdicts among the headline metrics: RL better in **14**, baseline better in **15**, inconclusive in 53 of 204 rows overall.
4. No superiority claim is made beyond the intervals above. Where an interval spans zero the arms are treated as indistinguishable.
5. Structurally infeasible users are policy-invariant: every arm scores identically there, so they cannot separate the policies.
