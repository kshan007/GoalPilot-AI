# Exact reward equations and coefficients used in the controlled experiment

**Version:** v1 · **Date:** 2026-10-11
**Source of truth:** `simulation/05_simulation_runs/rl_prototype/goalpilot_env.py`, reward block in
`GoalPilotEnv.step`, selected by `GoalPilotConfig.reward_version`.

All three experiments use `GoalPilotConfig.recommended()` and differ **only** in
`reward_version` and the random seed. Verified by the validity gate in
`audit_tools/33_reward_experiment.py`: identical fixed-policy rollouts under all three versions
produce **bit-identical** state trajectories (cash, portfolio, loan balance, goal balances, net
worth). The reward version therefore changes the learning signal and nothing else, so any
difference in financial outcomes is attributable to learning.

## Notation

| Symbol | Meaning |
|---|---|
| $r_j$ | goal $j$'s funding ratio, $\min(1, \text{funded}_j / \text{target}_j)$ |
| $\Delta r_j$ | $r_j - r_j^{\text{previous month}}$ |
| $p_j, c_j$ | goal $j$'s `priority` and `criticality` (both on a 1–5 scale) |
| $L_j$ | months remaining to goal $j$'s deadline, **inclusive** of the current month |
| $S$ | the household's monthly surplus, $\max(0,\ \text{income} - \text{expenses} - \text{existing EMI})$ |
| $I_t$ | interest accrued this month on the environment's own loan |
| $m_t$ | the month's market return |
| $X_t$ | money moved into the portfolio this month |

## 1. `archived_v1` — the historical reward, unchanged

$$R_t = \underbrace{2.0 \sum_j \max(0, \Delta r_j) \frac{p_j}{5}}_{\text{incremental\_progress}}
\;-\; \underbrace{\mathbf{1}[t = D_j]\ 5.0 \sum_j (1-r_j)\frac{c_j}{5}}_{\text{deadline\_shortfall\_penalty}}
\;-\; \underbrace{10^{-5}\,\text{new\_loan}_t}_{\text{loan\_penalty}}
\;-\; \underbrace{\max\!\big(0, |m_t| - 0.05\, \text{risk}_i\big)\frac{\text{portfolio}_t}{10^5}}_{\text{risk\_penalty}}$$

No terminal term. This is the default and is byte-for-byte the archived expression.

## 2. `candidate_a` — goal-completion centric

$$R_t = \underbrace{2.0 \sum_j \max(0, \Delta r_j)\frac{p_j}{5}}_{\text{incremental\_progress (unchanged)}}
\;-\; \underbrace{5.0 \sum_{j:\,0 < L_j \le W} \Big(1-\frac{L_j-1}{W}\Big)(1-r_j)\frac{c_j}{5}}_{\text{graduated shortfall}}
\;-\; \underbrace{w_L \frac{I_t}{\max(S,1)}}_{\text{loan penalty}}
\;-\; \underbrace{w_D \frac{\max(0,-m_t)\,X_t}{\max(S,1)}}_{\text{downside risk}}$$

plus, **in the terminal month only**:

$$+\; w_T \frac{\text{net worth}_T - \text{net worth}_0}{|\text{net worth}_0|}$$

| Coefficient | Value |
|---|---|
| $W$ = `shortfall_window_months` | **12** |
| $w_L$ = `loan_cost_weight` | **5.0** |
| $w_D$ = `downside_risk_weight` | **2.0** |
| $w_T$ = `terminal_net_worth_weight` | **2.0** |

Design consequences, stated explicitly:

- The shortfall ramp $(1-(L_j-1)/W)$ is $1/W$ at $L_j = W$ and **exactly 1** at $L_j = 1$, so the
  peak penalty magnitude is *identical* to `archived_v1`; only its distribution over time changes.
- Goals further out than $W$ months are not charged at all, and neither is any goal after its
  deadline (the shortfall ratio would be static, so the term would add a constant with no
  gradient).
- `loan_penalty` prices **debt service**, not principal: a cheaper loan is genuinely cheaper, and
  the charge is normalised by the household's own budget.
- `risk_penalty` is **downside-only** and applies only to the money exposed this month, never to
  accumulated wealth — so a gain is never penalised.
- The terminal net-worth term cannot double-pay goal progress: goal balances are excluded from
  net worth by construction (finding R-11 / audit requirement B2).

## 3. `candidate_b` — realised-wealth centric

$$R_t = \underbrace{w_W \frac{\text{net worth}_t - \text{net worth}_{t-1}}{\max(S,1)}}_{\text{wealth\_delta}}
\;-\; \underbrace{5.0 \sum_{j:\,0 < L_j \le W}\Big(1-\frac{L_j-1}{W}\Big)(1-r_j)\frac{c_j}{5}}_{\text{graduated shortfall (as A)}}$$

plus, **in the terminal month only**:

$$+\; w_A \cdot \frac{1}{n}\sum_j r_j \frac{p_j}{5}$$

| Coefficient | Value |
|---|---|
| $w_W$ = `wealth_delta_weight` | **2.0** |
| $w_A$ = `terminal_achievement_weight` | **3.0** |
| $W$ | **12** |

Design consequences:

- Debt cost and market risk are **endogenous**: interest paid reduces the net-worth delta and
  market losses reduce it, so no hand-set penalty is needed.
- `wealth_delta` rewards *movement*; `terminal_goal_achievement` rewards *completion*. These are
  different quantities (wealth vs goal ratio), so this is not a double payment of the same event.

## 4. What these versions deliberately do NOT do

- **No reward for borrowing that merely raises goal balances.** Candidate A charges the interest;
  candidate B lets the interest reduce the wealth delta. Neither pays for principal.
- **No reward for a large terminal portfolio that ignores missed goals.** Both retain a shortfall
  signal, and B adds a terminal achievement term.
- **No projected return is ever rewarded.** Goal crediting under `recommended()` is
  `market_weighted`: realised revaluation only (finding R-03).

## 5. Honest status of the coefficients

The six coefficients are **design parameters, not fitted optima**. Each was chosen so that its
term is of a comparable order of magnitude to the per-goal progress term. They were **not** tuned
against the held-out users, and the held-out users were not inspected while choosing them. A
different set of coefficients would produce a different experiment, and the results reported for
this experiment describe *these* coefficients only.

## 6. Reproducing

```powershell
$py = "C:\Users\sudha\AppData\Local\Programs\Python\Python313\python.exe"
Set-Location S:\fyp\GoalPilot_AI_Completed
& $py audit_tools\33_reward_experiment.py --mode smoke
& $py audit_tools\33_reward_experiment.py --mode full --timesteps 50000 --seeds 7,17,27
& $py audit_tools\34_reward_experiment_report.py
```

Checkpoints are versioned under `training_logs/experiments/reward_experiment_v1/<version>/`;
per-run `monitor_*.csv` and `training_episodes_*.csv` logs accompany each checkpoint.
