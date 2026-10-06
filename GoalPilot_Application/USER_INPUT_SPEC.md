# GoalPilot Application - User Input Specification

This document defines the exact data schemas, validation constraints, and conversions required for user inputs in the GoalPilot Application, strictly adhering to the current single-goal optimization capabilities of GoalPilot AI.

---

## 1. User Financial Profile Schema

| Field Name | Type | Unit | Range / Constraints | Description |
| :--- | :--- | :--- | :--- | :--- |
| `monthly_income` | `float` | INR (₹) | $> 0$, typical: ₹10,000 - ₹2,000,000 | Baseline monthly gross income |
| `monthly_expenditure` | `float` | INR (₹) | $\ge 0$, typical: ₹5,000 - ₹1,500,000 | Baseline total monthly living expenses |
| `monthly_emi` | `float` | INR (₹) | $\ge 0$, default: $0.0$ | Existing fixed monthly loan EMI commitments |
| `initial_savings` | `float` | INR (₹) | $\ge 0$, default: $0.0$ | Current liquid bank balance / emergency reserves |
| `initial_investment` | `float` | INR (₹) | $\ge 0$, default: $0.0$ | Current financial investment portfolio |
| `risk_profile` | `enum` | - | `conservative`, `moderate`, `aggressive` | Investor risk preference category |

### Derived Financial Metrics (Backend Computed)
- **`baseline_monthly_surplus`**: $\text{monthly\_income} - \text{monthly\_expenditure} - \text{monthly\_emi}$
- **`savings_to_income_ratio`**: $\text{initial\_savings} / (12 \times \text{monthly\_income})$
- **`debt_service_ratio`**: $\text{monthly\_emi} / \text{monthly\_income}$
- **`financial_situation`**: Categorized based on cash-flow buffer and savings adequacy (`financial_stress`, `vulnerable`, `moderate_saving`, `affluent`).

---

## 2. Single Financial Goal Schema

The current system strictly plans for **EXACTLY ONE** financial goal.

| Field Name | Type | Unit | Range / Constraints | Description |
| :--- | :--- | :--- | :--- | :--- |
| `goal_name` | `string` | - | $1 \le \text{length} \le 100$ | Descriptive label (e.g., "Car Down Payment") |
| `target_amount` | `float` | INR (₹) | $> 0$ | Target monetary amount required to fulfill goal |
| `target_date` | `string` / `date` | YYYY-MM-DD | Must be future date ($\ge 1 \text{ month}$) | Target deadline for the goal |
| `goal_horizon_months` | `int` | Months | $1 \le H \le 144$ | Computed/verified monthly time horizon |
| `goal_priority` | `enum` | - | `essential`, `important`, `discretionary` | Goal priority classification |
| `purpose` | `string` | - | Optional text | Qualitative purpose or context of the goal |

---

## 3. Horizon Time Conversion

GoalPilot AI's simulation calendar operates on a **monthly discrete grid** ($t = 1, \dots, 144$ months).

### Conversion Logic
When a user selects a `target_date`:
1. The backend calculates elapsed whole months between current date $t_0$ and `target_date`:
   $$H = \max(1, (\text{year}_{\text{target}} - \text{year}_{\text{current}}) \times 12 + (\text{month}_{\text{target}} - \text{month}_{\text{current}}))$$
2. If $H > 144$ months, the horizon is capped at 144 months (the maximum macroeconomic simulation calibration window), and a clear advisory note is presented.
3. If the user directly inputs `goal_horizon_months`, `target_date` is derived accordingly.

---

## 4. Input Validation Rules

1. **Strict Positivity**:
   - `monthly_income > 0` (cannot be zero or negative).
   - `target_amount > 0` (goal amount must be positive).
   - `goal_horizon_months >= 1`.
2. **Non-Negativity**:
   - `monthly_expenditure >= 0`, `monthly_emi >= 0`, `initial_savings >= 0`, `initial_investment >= 0`.
3. **Deficit Advisory**:
   - If $\text{monthly\_income} < \text{monthly\_expenditure} + \text{monthly\_emi}$, the system accepts the input, flags a **Structural Monthly Deficit**, and transparently demonstrates why the LP yields zero goal funding and full shortfall.
