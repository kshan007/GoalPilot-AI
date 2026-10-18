# Optimization Methodology

Date: 2026-10-10

## Input Model

The optimizer accepts one `FinancialState` and a DataFrame of goals. Financial state contains income, essential expenses, optional discretionary expenses, current EMI, liquid savings, total existing investments, explicitly usable existing investments, emergency-fund months, EMI cap, and risk capacity.

Generated multi-goal inputs are synthetic. They combine one legacy simulated goal per user with additional generated goals. These should not be represented as real user goals.

## Decision Variables

For each goal `g`, the LP uses:

- `cash_g`: initial liquid savings allocated after emergency reserve and earmarks.
- `asset_g`: explicitly usable existing investment assets allocated to the goal.
- `save_g`: monthly savings/deposit contribution.
- `invest_g`: monthly investment contribution.
- `loan_g`: new loan principal.
- `shortfall_g`: remaining unfunded gap.

## Goal Accounting

Each goal has one equality:

`cash_g + asset_g * asset_growth_factor + save_g * savings_fv_factor + invest_g * investment_fv_factor + loan_g + shortfall_g = future_goal_cost_g - existing_funding_g`

`future_goal_cost_g` is calculated once using annual inflation and the goal horizon. Existing goal funding is treated as already earmarked for that goal and is not put back into the shared cash pool.

## Hard Constraints

- Sum of `cash_g` across goals cannot exceed liquid savings minus emergency reserve minus earmarked goal funding.
- Sum of `asset_g` cannot exceed explicitly usable existing investments.
- Sum of monthly savings and investment contributions cannot exceed monthly income minus essential expenses, discretionary expenses, and existing EMI.
- New loan EMI cannot exceed the configured EMI/income cap after existing EMI.
- Loan principal is capped by the selected offer and per-goal maximum.
- Investment and existing-asset allocations are disabled when their risk score exceeds the user's risk capacity.
- All allocation and shortfall variables are nonnegative.

## Objective

The LP minimizes weighted goal shortfall plus transparent penalties for loan cost, investment risk, existing-asset risk, and minor resource-use tie breakers. Priority and criticality are normalized into a goal-priority score with a bounded urgency factor for shorter horizons. Weighted goal achievement is a normalized funding metric, not a success probability.

## Provider Layer

`src/providers.py` defines normalized records for:

- `InvestmentCandidate`
- `LoanOffer`
- `SavingsProduct`
- `EconomicScenario`

Local JSON/CSV providers validate deterministic fixtures. The solver accepts normalized option lists but does not perform HTTP calls. This keeps the core optimization independent of source-specific parsing and makes the test suite offline-safe.

## Scenario Handling

An `EconomicScenario` can override inflation, savings return, investment return, and loan rate. The included fixture scenarios are baseline, favorable, and adverse offline assumptions derived from the project data context, not live forecasts.

## Interpretation

Outputs are conditional prototype allocations. They are not investment recommendations, loan approvals, trading instructions, or guarantees. Synthetic loan offers are not lender quotes. Historical market/NAV data should not be treated as future return forecasts.
