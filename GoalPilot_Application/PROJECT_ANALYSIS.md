# GoalPilot AI Current-State Analysis

## 1. Existing Architecture

The **GoalPilot AI** research repository is organized into a modular pipeline connecting empirical economic calibration, synthetic micro-data generation, dynamic monthly financial simulation, and Linear Programming (LP) optimization:

```
GoalPilot_AI/
├── simulation/
│   ├── 01_input_data/               # Empirical macroeconomic & household calibrations
│   ├── 02_synthetic_population/     # 10,000 synthetic individuals/households (demographics, income)
│   ├── 03_financial_profiles/       # Baseline balance sheets (savings, investments, debts, risk)
│   ├── 04_economic_environment/     # 144-month macroeconomic timeline (CPI, Nifty 50, WALR)
│   ├── 05_simulation_runs/          # Longitudinal monthly trajectories (cash flows, wealth)
│   ├── 06_results/                  # Aggregated financial states and LP optimization inputs
│   └── 07_validation/               # Statistical and methodology validation artifacts
│
└── optimization/
    ├── lp_inputs/                   # Intermediate formulations, audits, and diagnostics
    └── final_outputs/               # Master LP optimization dataset and summary reports
```

The pipeline operates strictly unidirectionally:
$$\text{Input Datasets} \longrightarrow \text{Synthetic Population} \longrightarrow \text{Monthly Simulation} \longrightarrow \text{LP Optimization} \longrightarrow \text{Performance Evaluation}$$

---

## 2. Simulation Pipeline

The simulation pipeline models 10,000 synthetic Indian household profiles across 144 monthly time steps (spanning 2015-01-01 to 2026-12-01):

1. **Macroeconomic Environment Integration**: Combines three core empirical data streams:
   - **CPI Inflation**: Calibrated monthly inflation rate and cumulative price level index.
   - **NIFTY 50 Returns**: Equity market return series and volatility regimes.
   - **WALR (Weighted Average Lending Rate)**: Benchmark lending and credit pressure dynamics.
2. **Dynamic Cash Flow Evolution**:
   - Monthly dynamic income grows in alignment with cumulative inflation:
     $$\text{Income}_{u,t} = \text{BaseIncome}_u \times \text{CumulativeInflationFactor}_t$$
   - Monthly dynamic expenditure scales with inflation:
     $$\text{Expenditure}_{u,t} = \text{BaseExpenditure}_u \times \text{CumulativeInflationFactor}_t$$
   - Fixed debt obligations ($\text{EMI}_u$) are serviced monthly.
   - Dynamic monthly surplus is calculated:
     $$\text{Surplus}_{u,t} = \text{Income}_{u,t} - \text{Expenditure}_{u,t} - \text{EMI}_u$$
   - Non-negative available cash flow for goal funding is determined:
     $$\text{PositiveCashFlow}_{u,t} = \max(0, \text{Surplus}_{u,t})$$
3. **Wealth and Balance Sheet Evolution**:
   - Liquid savings evolve with cash-flow balances and deficit absorption.
   - Initial investment portfolios fluctuate under simulated risk-adjusted market returns.

---

## 3. Simulation Inputs

| Input Category | Feature / Variable | Description / Source |
| :--- | :--- | :--- |
| **Macroeconomic** | `monthly_inflation_rate` | Empirical CPI inflation rate |
| **Macroeconomic** | `cumulative_inflation_factor` | Compounded inflation multiplier from base month $t_0$ |
| **Macroeconomic** | `nifty_monthly_return` | Nifty 50 index monthly return series |
| **Macroeconomic** | `average_walr` | Scheduled commercial banks' weighted average lending rate |
| **Household Profile** | `monthly_income` | Baseline monthly gross household earnings (₹) |
| **Household Profile** | `monthly_expenditure` | Baseline monthly consumption expenditure (₹) |
| **Household Profile** | `monthly_emi` | Fixed monthly loan installment commitment (₹) |
| **Balance Sheet** | `initial_savings` | Liquid emergency reserves / bank savings (₹) |
| **Balance Sheet** | `initial_investment` | Initial market investments (₹) |
| **Behavioral** | `risk_profile` | Risk tolerance tier (`conservative`, `moderate`, `aggressive`) |
| **Classification** | `financial_situation` | Demographic stratum (`financial_stress`, `vulnerable`, `moderate_saving`, `affluent`) |

---

## 4. Simulation Outputs

The simulation produces granular monthly time-series (`monthly_financial_simulation_base.csv`) and user-level summary outcomes (`final_optimisation_input.csv`):

- **Time-Series Variables ($t = 1 \dots 144$)**:
  - `positive_cash_flow`: Positive surplus available for goal allocation in month $t$.
  - `monthly_surplus_dynamic`: Net surplus/deficit in month $t$.
  - `savings_balance`: Liquid balance after deficit absorption.
  - `portfolio_value`: Equity/debt portfolio value under market returns.
- **User-Level Aggregates**:
  - `goal_horizon_funding_actual`: Cumulative goal funding under historical heuristic allocation.
  - `goal_shortfall_actual`: Shortfall under historical allocation policy.
  - `goal_achieved_on_time_actual`: Boolean indicator of baseline goal success.

---

## 5. Optimization Pipeline

The optimization layer formulates goal planning as a **Linear Program (LP)** solved using the Highs simplex/interior-point solver (`scipy.optimize.linprog(method="highs")`).

The optimization is strictly executed over the user's defined **Goal Horizon** ($H_u \le 144$ months):
1. Restricts monthly positive cash flows to the horizon window $t \in [1, H_u]$.
2. Formulates the shortfall minimization LP matrix ($A_{eq}, b_{eq}, \text{bounds}, c$).
3. Solves the LP per user to optimality.
4. Validates analytical consistency: $\text{Optimized Funding} = \min(\text{Target}_u, \sum_{t=1}^{H_u} P_{u,t})$ and $\text{Optimized Shortfall} = \max(\text{Target}_u - \sum_{t=1}^{H_u} P_{u,t}, 0)$.

---

## 6. Current Single-Goal Formulation

The current optimization model explicitly supports **EXACTLY ONE FINANCIAL GOAL** per user. 

### Decision Variables
1. **$G_{u,t}$** for $t = 1, \dots, H_u$: The monetary allocation directed towards the financial goal in month $t$.
2. **$D_u$**: The goal shortfall (unfunded gap) remaining at the target horizon date.
3. *(Derived)* **$R_{u,t} = P_{u,t} - G_{u,t}$**: Residual surplus cash retained by the user in month $t$.

### Total Variable Vector
$$\mathbf{x} = \begin{bmatrix} G_{u,1} & G_{u,2} & \dots & G_{u,H_u} & D_u \end{bmatrix}^T \in \mathbb{R}^{H_u + 1}$$

---

## 7. Optimization Inputs

The optimization model requires:
1. `user_id`: Identifier string.
2. `goal_horizon_months` ($H_u$): Positive integer representing goal duration in months.
3. `target_amount` ($\text{Target}_u$): Target monetary requirement in INR (₹).
4. `positive_cash_flow` ($P_{u,t}$): Array of length $H_u$ specifying surplus cash available per month.

---

## 8. Decision Variables

| Variable | Notation | Bounds | Dimension | Meaning |
| :--- | :--- | :--- | :--- | :--- |
| **Monthly Goal Funding** | $G_{u,t}$ | $0 \le G_{u,t} \le P_{u,t}$ | $H_u$ variables | Monthly contribution to the goal |
| **Goal Shortfall** | $D_u$ | $D_u \ge 0$ | $1$ variable | Unfunded goal balance at deadline |

---

## 9. Objective Function

$$\min_{\mathbf{x}} D_u$$

Under the target accounting identity ($\sum_{t=1}^{H_u} G_{u,t} + D_u = \text{Target}_u$), minimizing shortfall is mathematically identical to maximizing total goal funding:
$$\min D_u \iff \max \sum_{t=1}^{H_u} G_{u,t}$$

---

## 10. Constraints

1. **Monthly Cash-Flow Feasibility (Upper & Lower Bounds)**:
   $$0 \le G_{u,t} \le P_{u,t} \quad \forall t \in \{1, \dots, H_u\}$$
2. **Target Accounting Equality**:
   $$\sum_{t=1}^{H_u} G_{u,t} + D_u = \text{Target}_u$$
3. **Non-Negativity of Shortfall**:
   $$D_u \ge 0$$

---

## 11. Optimization Outputs

The LP solve yields:
- **`optimized_goal_funding`**: Total funding allocated to the goal ($\sum_{t=1}^{H_u} G_{u,t}^*$).
- **`optimized_shortfall`**: Remaining deficit ($D_u^*$).
- **`optimized_success`**: Boolean indicator ($\text{optimized\_goal\_funding} \ge \text{Target}_u - 10^{-6}$).
- **`monthly_allocations`**: Array of monthly funding $[G_{u,1}^*, \dots, G_{u,H_u}^*]$.
- **`residual_cash`**: Array of retained surplus $[R_{u,1}^*, \dots, R_{u,H_u}^*]$.
- **`solver_success`**: Status code and message from `scipy.optimize.linprog`.

---

## 12. Dependencies

- **Python**: 3.10+ / 3.11 / 3.12 / 3.13
- **Core Scientific Libraries**: `numpy`, `pandas`, `scipy` (specifically `scipy.optimize.linprog`)
- **Web Application Stack**: `FastAPI`, `Uvicorn`, `Pydantic` v2, `React`, `Vite`

---

## 13. Assumptions

1. **Single Goal Focus**: The user plans for one financial goal at a time over a fixed horizon $H_u$.
2. **Cash-Flow Backed**: Monthly contributions are funded from net monthly cash surplus ($P_t = \max(0, \text{Income}_t - \text{Expenses}_t - \text{EMI}_t)$).
3. **Deterministic Inflation Trajectory**: Dynamic income and expenses evolve according to historical CPI inflation calibration.
4. **No Unbacked Borrowing**: The model does not permit borrowing at WALR to artificially fund discretionary goals beyond cash capacity.
5. **No Speculative Return Reinvestment in LP**: As audited in Step 5Q of `GoalPilot_Optimization`, without explicit monthly investment contribution decision variables in the simulation data, returns are not assumed to guarantee goal funding.

---

## 14. Limitations

1. **Single-Goal Limitation**: Cannot balance multiple competing goals simultaneously (e.g., retirement + house down payment).
2. **Sequential Decisions**: Allocation decisions are solved over the deterministic horizon upfront rather than adapted via feedback policies.
3. **No Dynamic Portfolio Rebalancing within LP**: Portfolio wealth acts as a separate balance sheet reserve rather than a decision variable inside the LP.

---

## 15. Application Integration Requirements

1. **Preserve Research Core**: Never modify `GoalPilot_AI/`.
2. **Dual Execution Modes**:
   - **Interactive Custom Mode**: Takes any user profile and goal, dynamically generates the calibrated inflation cash-flow trajectory, and solves the single-goal LP.
   - **Research Benchmark Mode**: Evaluates benchmark profiles from the 10,000 synthetic dataset and validates exact numerical parity with notebook results.
3. **Extensibility**: Design clean adapter interfaces (`SingleGoalOptimizationAdapter`) so future multi-goal or RL decision engines can be swapped in seamlessly.
