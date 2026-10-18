# Algorithm Design

How GoalPilot AI turns a financial profile and a set of goals into an allocation, and where each
responsibility sits.

```
profile, goals, assets, liabilities, actuals
        │
        ▼
 cash-flow builder ──► monthly surplus, protected buffer, available goal budget
        │
        ├──► LP arm ────────────────► feasible allocation (default)
        ├──► RL arm ────────────────► bounded policy action
        └──► hybrid: RL θ ──► LP re-solve ──► allocation
                                  │
                                  ▼
                    validation (budget, non-negativity, goal accounting)
                                  │
                                  ▼
                    persisted run + diff + structured explanation
```

---

## 1. Cash flow: the single definition of "available"

Every arm consumes the same object, so no arm can disagree about what money exists.

```
surplus            = income − essential − discretionary − existing EMI
desired_buffer     = max(monthly_savings_target, preferred_cash_buffer)
sustainable_buffer = min(desired_buffer, max(0, surplus))
protected_buffer   = desired_buffer      if the buffer is mandatory
                   = sustainable_buffer  otherwise
buffer_deficit     = desired_buffer − sustainable_buffer
goal_budget        = max(0, surplus) − protected_buffer
```

Taking the **maximum**, never the sum, is what prevents the savings target, the cash reserve and
the emergency fund from being counted as three separate outflows. The emergency fund is a *stock*
target and is excluded from the goal cash pool instead.

Both optimisers receive the buffer as part of their discretionary line. That makes the solver's
own budget equal `goal_budget` without touching the research solver, shrinking the emergency-fund
target (which is built from *essential* expenses) or changing the EMI ceiling (built from
*income*). The mapping is disclosed in every response as `protected_buffer`,
`gross_monthly_surplus` and `monthly_surplus` (the post-buffer budget).

## 2. Linear program

Decision variables per goal *g*: savings contribution, investment contribution, loan principal,
and a shortfall variable; plus initial-cash and existing-asset allocations.

Constraints:

1. **Budget** — total monthly outflow ≤ `goal_budget` (post-buffer).
2. **Goal accounting** — for each goal: initial cash + existing assets + capitalised savings +
   capitalised investments + loan proceeds + shortfall = inflation-adjusted target.
3. **Liquidity** — allocations from liquid savings ≤ liquid savings − emergency reserve.
4. **Existing assets** — an asset can be earmarked once; it cannot fund two goals.
5. **Debt** — new EMI ≤ the user's own EMI-to-income ceiling minus existing EMI; loan principal
   and EMI are linked by the amortisation identity at the assumed rate.
6. **Risk** — investment contribution ≤ `risk_capacity`-derived share of the contribution.
7. **Non-negativity** on every variable.

Inflation is applied per goal: `future_target = current_cost × (1 + π_g)^years`, with a goal-level
override where supplied. The objective maximises weighted, discounted goal achievement net of
shortfall penalties; weights come from goal priority and criticality.

The solver is `scipy.optimize.linprog(method="highs")`. Infeasibility is reported as a status, not
an exception, and named constraints are returned so the UI can explain which one binds.

## 3. Reinforcement learning

**Markov decision process.** State: normalised income and its variability, essential and
discretionary expenses, savings trend, buffer, liquid savings and emergency status, debt and EMI
load, a fixed-size goal summary (count, weighted progress, urgency, shortfall), market and rate
assumptions, shock indicators, horizon, risk preference. Variable goal counts are handled by a
masked summary block; the mask prevents silent truncation of goals beyond the block width.

**Action.** A bounded continuous vector: savings-vs-investment split, contribution scaling,
risk-exposure adjustment, liquidity-preservation flag, and a borrow-evaluation flag. The policy
cannot authorise a loan, execute an investment or exceed a user preference; it proposes
parameters only.

**Reward.** Weighted goal progress and on-time completion, minus penalties for: dropping below the
protected buffer, missing essential obligations, unsustainable contribution ratios, borrowing
cost, and constraint violations. Reward shaping was audited for the specific failure modes named
in the brief — borrowing to accelerate a goal, chasing return, underfunding essentials — and the
penalties dominate those paths.

**Training and inference are separate.** Inference loads a frozen checkpoint per request and never
learns from user data. Retraining is offline, versioned, and gated on an explicit deployment
check; the checkpoint in use is recorded on every persisted run.

## 4. Hybrid

The RL output θ is converted into LP parameters (contribution split, investment ceiling within the
user's approved band, liquidity preference). The LP then re-solves with θ applied and remains the
sole authority on feasibility.

Reporting is deliberately blunt: on the current evaluation sweep the hybrid produces the same
allocation as LP because the budget binds before the parameters the RL adjusts
(`docs/ALGORITHM_EVALUATION.md` §3.2). The integration is real — a test asserts the parameters
change — but "materially different outcome" is not claimed.

If the policy fails to load, returns a malformed action, or produces parameters outside the
approved band, the request falls back to LP-only and records why.

## 5. Selection

All available arms run on identical inputs. The rule is **LP-anchored**, not a free ranking: an
alternative displaces the LP only if it beats it by at least a fixed achievement margin *and* gives
up no more than a fixed tolerance of deadline success. Otherwise the LP is recommended. If the LP
plan itself fails validation, the best validated arm is named explicitly as a fallback, not an
endorsement. Every arm's metrics are returned alongside a reason for each arm that was not selected,
so the decision can be audited line by line. On the current sweep this yields LP three times and the
rule baseline twice.

## 6. Validation and determinism

Before any plan is persisted: contributions non-negative, total ≤ goal budget, no goal counted
twice, no asset double- earmarked, and the sum of goal-level funding reconciling to the summary.
Fixed seeds make repeated runs reproducible; the LP is deterministic by construction.
