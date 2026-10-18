# Explanation - USER_00058

_Source: simulated state (goalpilot_env), recorded per month; numbers are computed, not forecast._

## Goals and constraints
- 3 goals with a combined inflated target of 505,555.
- Monthly income 47,900, essential expenses 24,000, existing loan service 4,139, leaving an investable surplus of 19,761.
- Declared risk profile `moderate` (score 0.63) and an investment-capacity ratio of 0.4125. The capacity ratio is an affordability ceiling in the simulator, not a validated risk-suitability measure.

## Why this allocation
- The plan could allocate from a monthly investable surplus of 19,761; across 142 months it executed 170,274 of savings and 1,157,609 of investment contributions.
- The investment ceiling (0.4125 of available surplus) never bound, so no requested investment was refused by the capacity rule.
- 2,394,342 of surplus was left unallocated over the horizon.
- 2,394,342 of budget was released by per-goal caps once a goal reached its target. In this configuration that released budget is not reallocated to goals that still have need (finding R-13), so it is the same money reported above as unallocated surplus - the two figures are not additive.
- Contributions were directed to goals in priority order until each goal's remaining need was met; the weighted achievement across all goals is 1.0000, i.e. 100.0% of the priority-weighted target.

## Why other goals received less
- Every goal reached its target, so no goal had to be funded less than another.

## Expected shortfalls and deadline risk
- No goal shortfall: every goal was fully funded within the horizon.

## Savings, returns and borrowing
- No new borrowing was used, so no interest cost was incurred.
- Final balance sheet: cash 2,724,094 (including restricted emergency cash held inside the cash balance), portfolio 779,497, loan balance 0, net worth 3,503,591.
- Investment gain realised over the horizon: 471,901. This is a realised path outcome, not a forecast.
- Earmarked goal funding is 775,128. This is a *memo* total - a subset of assets already counted in net worth - and must never be added to net worth (that was finding F-04).

## Sensitivity to assumptions
- Under `capacity x0.5` the weighted achievement becomes 0.8669 (change -0.1331 vs the 1.0000 baseline); shortfall +53,265.
- Under `market path x0.5` the weighted achievement becomes 1.0000 (change +0.0000 vs the 1.0000 baseline); shortfall +0.
- These are deterministic what-if re-runs under changed assumptions, not forecasts, and they show the recommendation is conditional on them.

## What could change the result
- A change in realised market returns, because goal funding here is credited from realised portfolio revaluation, not a projected return.
- A change in the investment-capacity assumption, which bounds how much of the surplus can be invested at all.
- A change in income, essential expenses or existing debt service, which moves the investable surplus and therefore every allocation.
- A change in goal amounts, deadlines or priorities, which reorders the trade-off among goals.

## General principles referenced

- **emergency reserve** (emergency_fund, uncited_general_principle): A commonly recommended starting point is to hold several months of essential expenses in a liquid, low-risk form before committing money to longer-term goals. The exact number of months depends on income stability and dependants.
- **horizon and volatility** (goal_horizon_risk, uncited_general_principle): The shorter the horizon before the money is needed, the less a plan should depend on volatile assets, because there is less time to recover from a market decline. Long horizons can tolerate more volatility than short ones.
- **inflation** (inflation_erodes, uncited_general_principle): Goal costs usually rise with inflation, so a target expressed in today's money is normally below the amount that will actually be needed later. A plan that ignores inflation understates the target.
- **debt and affordability** (debt_service_first, uncited_general_principle): Scheduled loan repayments reduce the cash flow available for goals, and interest is a certain cost whereas investment returns are uncertain. Borrowing to fund a goal converts an uncertain return into a fixed cost.
- **investable surplus** (capacity_affordability, uncited_general_principle): The amount that can prudently be invested is bounded by income left after essential spending, existing debt service and a reserve. Capacity is an affordability limit, not a statement about risk appetite.
- **conflicting goals** (prioritisation, uncited_general_principle): When goals cannot all be funded, a common approach is to protect essential and near-term commitments first and to treat discretionary, long-dated goals as flexible, accepting that their amount or timing may need to change.
- **historical returns** (returns_uncertain, uncited_general_principle): Past market returns are observations of what happened, not promises about what will happen. A plan that depends on a specific return being achieved is fragile to that assumption being wrong.
- **earmarking versus ownership** (separate_money, uncited_general_principle): Money earmarked to a goal is not a separate asset; it is part of the same wealth and must not be counted twice. Progress toward goals and total wealth are different measures and should be reported separately.

_General, uncited financial principles compiled for this project. They are not quotations from NISM or any other body and are not personalised advice._

## Goal detail

| goal | priority | deadline (mo) | target | funded | ratio | shortfall |
|---|---:|---:|---:|---:|---:|---:|
| Emergency buffer | 5 | 7 | 222,340 | 280,956 | 100.0% | 0 |
| Travel fund | 1 | 17 | 144,876 | 144,876 | 100.0% | 0 |
| Legacy simulated goal | 3 | 102 | 138,339 | 349,297 | 100.0% | 0 |