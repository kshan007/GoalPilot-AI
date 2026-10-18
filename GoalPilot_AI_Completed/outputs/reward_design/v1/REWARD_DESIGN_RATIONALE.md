# Reward design rationale (Phase D)

**Version:** v1 · **Date:** 2026-10-11
**Historical reward:** `archived_v1` — **never modified, still the default.**
**Candidates:** `candidate_a` (goal-completion centric), `candidate_b` (realised-wealth centric).

Both candidates are opt-in through `GoalPilotConfig.reward_version`. With
`reward_version="archived_v1"` the reward expression in `GoalPilotEnv.step` is byte-for-byte
the archived one, which is what keeps `test_goalpilot_env_parity.py` exact.

---

## 1. What the archived reward does (measured, not assumed)

Decomposed for all six baseline policies over 20 held-out users x 142 months
(`outputs/evaluation/final_validation_v1/` pre-fix record and the `archived` block of
`reward_version_comparison_v1.csv`):

| Component | Form | Measured behaviour |
|---|---|---|
| `incremental_progress` | `+ 2.0 x Δratio x priority/5`, positive part only | bounded, ratio-normalised. PPO earns **+29.99 — the lowest of any active policy** (vs +44.48 for Savings only) |
| `deadline_shortfall_penalty` | `− 5.0 x shortfall_ratio x criticality/5` **in the exact deadline month only** | 73 month-events for No action, 62 for Savings only. **No signal in any other month**, so there is no gradient toward finishing a goal early |
| `loan_penalty` | `− 1e-5 x new_loan_principal` | −11.84 total for Savings+loan, against a mean interest cost of ₹19,028 per user — i.e. the penalty is ~2 orders of magnitude smaller than the cost it nominally prices |
| `risk_penalty` | `− max(0, \|market_return\| − risk_score x 0.05) x portfolio/100000` | **−270.44 for Investments-only vs −27.38 for Savings-only.** Only the portfolio-size term differs, so this charges *for being invested at all*, not for downside. There is no offsetting terminal-value term |

Components reconcile to the environment reward to `1.8e-15` in every policy and preset
(`max_component_residual`), so the decomposition is faithful; the problem is the design, not
the accounting.

### Defects the design must address

1. **Risk is charged on wealth, not on downside.** `|market_return|` penalises large gains as
   heavily as losses, and the charge scales with the portfolio.
2. **No terminal value.** Nothing rewards ending wealthy; only goal progress is rewarded.
3. **The deadline signal is a single month.** A goal missed at month 60 and one missed at
   month 141 are indistinguishable outside their deadline month.
4. **Debt is priced on principal, not on cost.** Borrowing is penalised the same whatever the
   rate and whatever the benefit.
5. **Absolute loan magnitudes are not normalised** by the household's budget, so the same
   ₹150,000 loan is judged identically for a ₹40,000/month and a ₹200,000/month household.

---

## 2. Candidate A — goal-completion centric

| Term | Expression | Why |
|---|---|---|
| `incremental_progress` | `+ 2.0 x max(0, Δratio) x priority/5` | **Unchanged.** It is already ratio-normalised and bounded per goal, so large and small goals are equally tractable. Rewriting it would have been change for its own sake |
| `deadline_shortfall_penalty` | **Graduated**: for `0 < months_left ≤ 12`, `− 5.0 x ramp x (1 − ratio) x criticality/5` where `ramp = 1 − (months_left−1)/12` | Replaces the single-month spike with a signal that ramps to the *same* full weight in the deadline month, so the peak magnitude is unchanged but a gradient exists for a year beforehand. Goals further out than the window are not charged |
| `loan_penalty` | `− 5.0 x (interest_due / max(surplus,1))` | Prices **debt service**, not principal, normalised by the household's own budget. Borrowing is therefore judged on affordability, and a cheaper loan is genuinely cheaper |
| `risk_penalty` | `− 2.0 x max(0, −market_return) x (invest_total / max(surplus,1))` | **Downside only**, and only on the money actually exposed this month — not on accumulated wealth. Gains are no longer penalised |
| `terminal_net_worth` | `+ 2.0 x (net_worth − initial_net_worth)/\|initial_net_worth\|`, final month only | Supplies the missing terminal-value term. It **cannot double-pay goal progress** because goal balances are excluded from net worth by construction |

Post-deadline shortfalls are not punished. That is deliberate: after the deadline the
shortfall ratio is static, so a charge would add a constant with no gradient while biasing
the return scale — it is logged instead through the evaluation metrics.

## 3. Candidate B — realised-wealth centric

| Term | Expression | Why |
|---|---|---|
| `wealth_delta` | `+ 2.0 x (net_worth_change / max(surplus,1))` each month | A single interpretable quantity. `net_worth_change` already nets interest paid **and** market gains, so debt cost and investment risk are priced endogenously instead of by hand-tuned penalties |
| `deadline_shortfall_penalty` | graduated, as in A | Goal attainment still needs a direct signal; a wealth-only reward can fund the wrong goals |
| `terminal_goal_achievement` | `+ 3.0 x` priority-weighted mean achievement, final month only | Charged **once**. It rewards *completion* while `wealth_delta` rewards *movement*; the two quantities are different (wealth vs goal ratio), so this is not a double payment of the same thing |

Candidate B is genuinely different from A: A is goal-completion centric with explicit debt and
downside penalties; B is wealth centric with those effects internalised. B is the design that
would be preferred if the objective were "maximise the household's wealth subject to meeting
goals", A if the objective is "meet goals subject to not destroying wealth".

## 4. What the candidates deliberately do **not** do

- **No reward for borrowing that merely raises goal balances.** `loan_penalty` in A prices the
  interest; in B the interest reduces the wealth delta. Neither pays for the principal.
- **No reward for a large terminal portfolio that ignores missed goals.** A keeps the
  graduated shortfall; B adds a terminal achievement term.
- **No new coefficient is presented as fitted or optimal.**

## 5. Open questions — recorded, not hidden

1. **Coefficient magnitudes are design choices, not fitted optima.** Each weight
   (`loan_cost_weight = 5`, `downside_risk_weight = 2`, `terminal_net_worth_weight = 2`,
   `wealth_delta_weight = 2`, `terminal_achievement_weight = 3`) was chosen so the term is of
   a comparable order to the per-goal progress term. They are **not** claimed to be optimal.
   The comparison in `reward_version_comparison_v1.csv` reports component-mean magnitudes so
   the balance can be inspected; tuning them is a training experiment, not a paper exercise.
2. **Should the graduated window be 12 months for every goal?** A goal with a 6-month horizon
   is charged from month 1; a 240-month goal is charged only near the end. A
   horizon-proportional window may be fairer. Untested.
3. **Is a terminal net-worth reward necessary given the graduated shortfall?** Both are
   present in A; ablating one is the clean way to find out.
4. **Candidate B's `wealth_delta` may reward saving over goal completion** when a goal is
   already unreachable. The terminal achievement term is the only counterweight; whether it
   is strong enough is untested.

## 6. Selection rule

A reward was **not** selected because it produced the highest PPO total reward. The
comparison reports, per reward version and policy: component means, total reward,
`weighted_goal_achievement`, `pct_goals_fully_funded`, `pct_goals_met_by_deadline`, final net
worth, total interest paid, total loan principal and downside exposure
(`reward_version_comparison_v1.csv`, `reward_version_outcomes_v1.csv`). Selection must be
made on those **financial** outcomes, and only after a policy has actually been trained under
each version on held-out users — which has **not** been done here.
