# GoalPilot AI — defence pack

**Date:** 2026-10-11
Purpose: everything needed to *demonstrate and defend* the project — assumptions, the
completed/experimental/future split, a reproducible demo, worked scenarios, a report outline and
prepared answers to likely panel questions.

---

## 1. Assumptions and limitations

### 1.1 Financial assumptions (all explicit, all configurable)

| assumption | value | where |
|---|---|---|
| Inflation applied to goal targets | 3 % p.a. | `GoalPilotConfig.annual_inflation` |
| Savings return | 0 % (face value) | `annual_savings_return` |
| Investment return assumed by the LP | 5 % p.a. | `investment_return_assumption` |
| RL investment return | realised NIFTY monthly path | `rl_market_credit_validated.csv` |
| Loan rate | LP: 12 % p.a. fixed · RL: monthly `walr_monthly` | config / market |
| Loan tenure | 60 months | `loan_tenure_months` |
| Max new loan in one month | 150,000 | `max_new_loan` |
| EMI/income affordability cap | 35 % | `emi_income_ratio_cap` |
| Emergency reserve | 6 months of essential expenses (RL `recommended` / LP) | `emergency_months` |
| Investment capacity | `investment_capacity_ratio × surplus available after loan commitments` | env `_allocate` |
| Horizon | RL 142 months · LP per-goal horizon | data |
| Goal credit | `market_weighted`: face value + realised market revaluation | `goal_credit_mode` |

### 1.2 Limitations — stated plainly

1. **Synthetic population.** All users are simulated. `investment_capacity_ratio` is an
   affordability ceiling produced by the pipeline, **not** a validated risk-suitability measure.
   HCES is a population benchmark, not an individual's expenditure.
2. **Historical returns are not forecasts.** NIFTY monthly returns are what happened, not what
   will happen. Goal funding under `market_weighted` is credited from realised revaluation.
3. **LP and RL are not exact parity.** The LP is a one-shot static plan; the environment is a
   monthly stochastic decision. Horizons, return conventions and decision timing differ and are
   documented, not hidden.
4. **The reward function is unchanged.** F-03 (risk penalty dominates, no terminal-value offset)
   and F-07 (component scaling) are diagnosed and quantified but were deliberately not fixed.
5. **No reward version has been selected.** The fresh-split paired difference between
   `candidate_a` and `archived_v1` was +0.0069 (CI [−0.0268, +0.0444], p = 0.72) — not
   significant.
6. **`residual_carried` (R-01b)** is asserted but never exercised by the real data.
7. **Small held-out cohorts.** 16 users; bootstrap CIs are wide and should be read as such.
8. **`monthly_surplus` in the population CSV excludes EMI** (finding B-1); the RL environment
   nets it out. They must not be joined naively.
9. **The web application is single-goal, unconstrained LP** — no multi-goal, no RL inference.
10. **Colab was never executed** from this host; readiness is structural only.

## 2. Completed work vs experimental findings vs future work

### 2.1 Completed and verified

- Repository audit with 15 findings (F-01…F-15) and 13 stage-2 findings (R-01…R-13).
- Ledger accounting (F-04, F-05, R-01, R-02, R-11) with archived parity preserved to 1e-12.
- Action semantics fixed (`share`) removing the PPO handicap (F-02); opt-in `mix` (R-12).
- Goal-credit modes fixing the savings/investment degeneracy (F-01) and the projected-return
  booking (R-03).
- Capacity-constrained LP benchmark (v7): overflow 10,130.92 → 0.000058 per month.
- **Content validation of the two large simulation CSVs** (F-14) — 1,430,000 rows × 2 files,
  portfolio, market-coupling and cross-file identities all pass.
- **Fair evaluation framework** with held-out cohorts, paired differences and bootstrap CIs.
- **Grounded explainability layer** (`goalpilot_explain`, `goalpilot_knowledge`) with 10 tests.
- Application verified: **15 backend tests pass**, live `/api/health` and `/api/optimize`.
- Full test suite: **164 RL + 26 LP = 190 passing** (before this pass's additions).

### 2.2 Experimental findings (evidence, not settled conclusions)

- The **existing LP's achievement advantage was largely an accounting artefact**: requiring it to
  respect investment capacity costs −0.2476 achievement (CI [−0.3405, −0.1538]).
- The LP's **deadline-success advantage survived** the capacity correction but is statistically
  indistinguishable from the constrained LP (n = 16).
- Under `share`+`legacy` the unconstrained LP plans **zero** monthly savings and 13,736.66/month
  of investment, of which the environment accepts 2,023.56 and relabels 10,130.92 as savings.
- Rule-based urgency and need-proportional savings score **0.0000 deadline success**.
- 22 of 100 users are structurally cash-flow-negative; the shortfall there is identical across
  every arm.
- **v8 (this pass): the best arm on the 16 fresh test users is `investment-only` (0.5800), above
  both RL arms (0.4842 `archived_v1`, 0.4398 `candidate_a`).** RL beats the capacity-constrained
  LP (+0.2390, significant) but not the simple rules. Reward-version gains did not reproduce.

### 2.3 Future work

- Retrain under a *selected* reward version at ≥ 100k steps with a larger held-out cohort.
- Decompose the residual plan-vs-executed execution gap (§2.4 of the v7 benchmark).
- Multi-goal planning and RL inference in the web application.
- An evidence-backed investor-education knowledge base with real citations.
- A multi-period stochastic LP to replace the one-shot plan if exact LP/RL parity is wanted.

## 3. Reproducible end-to-end demo procedure

```powershell
$py = "C:\Users\sudha\AppData\Local\Programs\Python\Python313\python.exe"
Set-Location S:\fyp\GoalPilot_AI_Completed

# (1) the research test suite — the regression guarantee
& $py -m pytest -q                                  # RL environment suite
Set-Location GoalPilot_MultiGoal_Extension
& $py -m pytest -q                                  # LP optimizer suite
Set-Location ..

# (2) data integrity of the two large simulation outputs
& $py audit_tools\70_large_csv_validation.py

# (3) the constrained-LP benchmark (capacity, execution, comparison)
& $py audit_tools\56_constrained_lp_comparison.py

# (4) the PPO training + held-out evaluation experiment
& $py audit_tools\80_ppo_training_v8.py --stage all

# (5) a worked, explained demo across feasible / partial / infeasible users
& $py audit_tools\90_demo_end_to_end.py

# (6) the web application
Set-Location S:\fyp\GoalPilot_Application\backend
& $py -m uvicorn app.main:app --port 8000          # http://127.0.0.1:8000/docs
```

## 4. Example user scenarios

`audit_tools\90_demo_end_to_end.py` selects one user of each kind by an explicit, deterministic
rule and writes an explained plan for each to `outputs/demo/`:

| scenario | selection rule | what it demonstrates |
|---|---|---|
| **Feasible** | gross cash-flow ceiling (`surplus × months`) ≥ total inflated target | all goals can be funded from cash flow; the plan is a scheduling problem |
| **Partially feasible** | `surplus > 0` but the ceiling < total target | the trade-off: some goals funded, others short; priority and deadline decide |
| **Structurally infeasible** | `surplus ≤ 0` after essential expenses and existing EMI | no policy can fund these goals from cash flow; the honest answer is "change the goal, the horizon or the cash flow" |

Each scenario prints and saves: goal table (target, funded, ratio, shortfall), why the allocation
was chosen, why other goals received less, shortfall/deadline risk, the role of savings/returns/
borrowing, and the sensitivity to capacity and market assumptions.

## 5. Final report outline, linked to real outputs

1. **Introduction & problem statement** — multi-goal personal finance planning for Indian households.
2. **Related work** — goal-based planning, LP portfolio/liability models, RL for sequential
   financial decisions. *(present the literature honestly; cite only sources actually read)*
3. **Data** — HCES 2023–24, RBI CPI, RBI WALR, NIFTY 50; provenance, units, conventions
   (`docs/final/ARCHITECTURE_AND_METHODOLOGY.md` §2).
4. **System architecture** — `docs/final/architecture.svg`.
5. **Financial simulation** — §3 of the methodology; the ledger and its invariants.
6. **LP optimisation** — §4; the base formulation and its recorded `UNSUPPORTED` elements; the
   capacity-constrained benchmark.
7. **RL environment** — §5; observation, action, reward versions, training protocol.
8. **Evaluation methodology** — `docs/final/EVALUATION_AND_RESULTS.md` §1–2.
9. **Results** — §4: baselines vs LP vs constrained LP vs PPO on held-out users, with CIs.
10. **Ablation & sensitivity** — §5: capacity, action mode, overflow policy, reward version.
11. **Explainability** — `docs/EXPLAINABILITY.md`.
12. **Application** — `docs/APPLICATION.md`.
13. **Limitations & future work** — §1–2 above.
14. **Conclusion** — what is demonstrably true, and what is not claimed.

## 6. Likely panel questions, with accurate answers

**Q: Does your RL agent beat the LP optimiser?**
A: It beats the *capacity-constrained* LP on goal achievement (+0.2390, CI [0.1516, 0.3214],
significant) but not on deadline success (CI [−0.1083, 0.0174], inconclusive — the constrained LP
has the best deadline rate, 0.1531 vs 0.1083). And it does **not** beat the simple rules:
`investment-only` achieves 0.5800 against the best RL arm's 0.4842, a significant −0.0957. That
negative result is reported as such. Earlier claims that the LP dominated were partly an
accounting artefact: the *unconstrained* LP plans investment the environment can never execute
and the overflow is relabelled as savings. Full paired tables:
`outputs/evaluation/final_validation_v8/ppo_v8_paired.csv`.

**Q: Why is PPO weak?**
A: Three measured reasons. (1) The archived reward's risk penalty dominates and has no
terminal-value offset (F-03), which teaches the agent not to invest. (2) The historical action
encoding was a magnitude, not a share, so policies emitting below the saturation point
under-funded goals while the reward stayed flat above it — no gradient (F-02). (3) 50k steps is
≈ 352 episodes against a 142-month horizon (F-10). The `share` action mode and the candidate
rewards address (1)–(2).

**Q: How do you know your corrections didn't change the original results?**
A: `tests/test_goalpilot_env_parity.py` rolls out 100 users × 5 policies × 142 months against
both the archived module and the reworked one and compares rewards to 1e-12 and state to 1e-9.
Every behaviour change is an opt-in preset; `GoalPilotConfig.archived()` reproduces the archive
exactly.

**Q: Is `investment_capacity_ratio` a real financial concept?**
A: No — it is a synthetic affordability ceiling generated by the pipeline. It is documented as
such everywhere, and the environment's own explanation states explicitly that it is not a
validated risk-suitability measure. That is precisely why v7 added the capacity constraint to the
LP and why the capacity sensitivity analysis is versioned.

**Q: Where does the return data come from, and is it leaked?**
A: NIFTY 50 monthly returns, 142 months, taken from the historical series. The policy sees only
information available at the decision date; the observation does not contain future returns or
future goal requirements, and this is pinned by tests. Lending rates are forward-filled with no
future information (validated by the NIFTY/WALR reconstruction audit).

**Q: Your goal targets — nominal or inflation-adjusted?**
A: Both exist and the choice is explicit (`target_basis`). The LP historically used inflated
targets; the archived RL used nominal ones, which is exactly the mismatch that made the original
LP-vs-RL comparison invalid (F-06). `lp_parity()` and `recommended()` put both on the inflated
basis.

**Q: Are you double-counting money?**
A: Not in `ledger` mode. Earmarked goal funding is a *memo* total that is a subset of assets; it
is never added to net worth. In `legacy` mode the historical behaviour did double-count, which
is why net worth differs between the modes (see `plots/03_net_worth_double_count.png`).

**Q: Is this financial advice?**
A: No. It is a research prototype and educational demo. Every return and rate is an explicit
assumption or a synthetic value; the explanation layer makes no return promises and cites no
sources it cannot verify.

**Q: What is actually new here versus the original project?**
A: A corrected ledger; the `share`/`mix` action semantics; goal-credit modes; the
capacity-constrained LP benchmark; content validation of the two large simulation outputs; a fair
held-out evaluation framework with CIs; a controlled PPO training and selection protocol; and a
grounded explainability layer. See `docs/REQUIREMENTS_TRACEABILITY.md` for the file-level map.
