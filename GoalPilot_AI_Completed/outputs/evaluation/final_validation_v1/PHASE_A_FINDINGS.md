# GoalPilot AI — Phase A Findings (Final RL Validation & Accounting Audit)

**Stage:** 1 of 6 in the execution order (§13) — *inspection only*.
**Status:** ✅ Inspection complete. **No project source file, dataset, checkpoint or archived CSV was modified.**
**Date:** 2026-10-11
**Working copy:** `S:\fyp\GoalPilot_AI_Completed` (authoritative original `S:\fyp\GoalPilot_AI` and the standalone notebook remain untouched)
**Interpreter:** `C:\Users\sudha\AppData\Local\Programs\Python\Python313\python.exe` (3.13.7)

---

## 1. Method

Read-only instrumentation only. Two new probes were written and executed:

| Probe | Purpose |
|---|---|
| `audit_tools/30_final_validation_probe.py` | D1 loan amortisation events, D2 `share`-mode borrowing, D3 goal-credit semantics, D4 ledger by policy, D5 reconciliation residual |
| `audit_tools/31_probe_followup.py` | D5 attribution, D2b share x credit-mode borrowing, D6 emergency reserve on the balance sheet |

Raw evidence: `outputs/audit/final_validation_v1/*.csv` and `probe_summary.json` / `probe_followup_summary.json`.

Baseline re-established this stage with the documented interpreter:

```
python -m pytest -q   (project root)              -> 64 passed
python -m pytest -q   (GoalPilot_MultiGoal_Extension) -> 26 passed
```

Console: `outputs/evaluation/pytest_baseline_final_validation.txt`, `outputs/evaluation/pytest_lp_baseline_final_validation.txt`.

Inspected in full: `goalpilot_env.py` (739 lines), `goalpilot_config.py` (191 lines),
`evaluation/{policy_evaluation,reward_decomposition,borrowing_audit,run_all,verify_against_archive}.py`,
`goalpilot_paths.py`, `pytest.ini`, `tests/conftest.py` + 6 test modules,
`archive/goalpilot_env_archived_20261010.py`, `docs/audit/AUDIT_REPORT.md`,
`docs/MODIFICATION_LOG.md`, `docs/EXECUTION.md`, both checkpoints, and all archived result CSVs.

Severity scale (as in the original audit): **S1** invalidates headline results · **S2** distorts conclusions · **S3** robustness/craft.

---

## 2. Findings table

| # | Finding | Evidence | Severity | Proposed fix | Regression test |
|---|---|---|---|---|---|
| **R-01** | **Residual loan principal is silently written off at tenure expiry.** | `goalpilot_env.py:525-528` — after the final payment the code does `if self.loan_balance <= 1e-6 or self.loan_months_left == 0: self.loan_balance = 0.0`. No cash movement, no write-off event. Measured: 12 write-off events over 560 episodes; largest ₹2,534.52; total ₹11,107.82 (`D1_loan_amortisation_events.csv`). Concrete event: `USER_00078`, month 138, `balance_before 5,591.57`, `interest_due 41.47`, `emi_paid 3,098.52`, `residual 2,534.52`, `months_left 1 → 0`, `balance_after 0.0`. | **S1** | Settle the residual as an **explicit accounting event**: pay it from accumulated cash; if cash is insufficient, keep it as an outstanding liability (continue servicing) instead of zeroing it. Record `residual_settled_cash` / `residual_carried` on `info`. Gate so `GoalPilotConfig.archived()` (legacy) keeps the historical write-off and archived parity is exact. | `test_loan_residual_is_settled_not_written_off` — reproduces `USER_00078` month 138; asserts `net_worth_change == expected_net_worth_change` through the settlement month and that `loan_balance` reaches 0 only via a real cash debit. |
| **R-02** | **The emergency reserve is entirely off the balance sheet** in `lp_parity` and `recommended`. | `goalpilot_env.py:276-280`: `self.cash = max(0, initial_savings − reconciled_earmarked − emergency_reserve)`; `initial_net_worth = cash + portfolio − loan_balance`. The reserve is stored only as a bare attribute. Measured on 5 held-out users x 2 configs: `emergency_reserve == initial_savings` always (i.e. the 6-month cap never binds), `earmarked == 0`, `cash_at_reset == 0`, and `reserve_off_balance_sheet` = ₹13,782 – ₹132,956 per user (`D6_emergency_reserve_balance_sheet.csv`). Example `USER_00001`: savings ₹178,733.65, portfolio ₹45,777.55, `initial_net_worth` ₹45,777.55 → ₹132,956.10 of real household money vanishes from the balance sheet. | **S1** | Represent the reserve as **restricted cash** inside `cash`, expose `restricted_cash` on `info`, and include it in `initial_net_worth` **and** in `net_worth`. Non-spendability is already structural (it never enters `surplus`), so this is a presentation/valuation fix, not a behavioural one. | `test_emergency_reserve_is_on_the_balance_sheet` — asserts `initial_net_worth == initial_savings + initial_investment` and `cash >= restricted_cash` for every reset in `lp_parity`. |
| **R-03** | **`growth_weighted` books *projected* future returns as realised goal funding.** | `goalpilot_env.py:344-361`: contributions are multiplied by `(1+r)^years` where `years = (deadline − month_index)/12` **before** `goal_balances` is incremented (`:568-573`). So ₹1 contributed to a 120-month goal is booked as ₹1.6289 of funding (5 %/yr). Measured (`D3_goal_credit_semantics.csv`, same user, same policy): `USER_00084` contributed ₹13,78,022 → booked ₹16,55,892 (**+20.2 %**); `USER_00091` ₹77,36,940 → ₹90,22,212 (**+16.6 %**). The same rupee is therefore valued under two incompatible return models — the synthetic `investment_return_assumption` for goal funding, and the real NIFTY monthly path for the portfolio. | **S1** | Keep `goal_balances` a **realised** account: credit the *contributed* amount plus only *realised* market revaluation of the invested portion (a new `market_weighted` credit mode). Report the projected deadline value separately as a clearly-labelled `goal_projected_value` planning memo which must **not** enter `net_worth`, the headline funding ratio, goal caps or loan sizing. Preserve `growth_weighted` for archived/LP-parity reproduction only. | `test_growth_weighted_does_not_create_wealth` — asserts `goal_balances_total <= cash + portfolio` every month under `recommended()`; `test_market_weighted_breaks_degeneracy_with_realised_returns` — mixed ≠ savings-only while funded value never exceeds contributed + realised gain. |
| **R-04** | **`interest_paid` reports accrued interest, not cash interest; unpaid interest is neither capitalised nor flagged.** | `goalpilot_env.py:518-530`: `interest_due = loan_balance x r` is computed **before** the payment, then `total_interest_paid += interest_due` (`:530`) and `info["interest_paid"] = interest_due` (`:685`) — regardless of `actual_payment = min(emi_due, payment_due)`. If `actual_payment < interest_due` the shortfall is silently forgiven (balance unchanged, never capitalised), so net worth is overstated by exactly the shortfall. `budget_audit` already computes the correct expectation (`expected_net_worth_change = surplus + investment_gain − interest_due`, `:658`) but the code's cash path uses `actual_payment − principal_paid`. | **S2** | Expose both quantities: `interest_paid_cash = actual_payment − principal_paid` and `interest_shortfall = interest_due − interest_paid_cash`. Capitalise any shortfall into `loan_balance` (accrual) so the liability stays real, or assert the shortfall is structurally zero and fail loudly if it is not. | `test_interest_paid_matches_cash_and_shortfall_is_zero` — asserts `sum(interest_paid) == sum(actual_payment − principal_paid)` and `interest_shortfall == 0` across all policies in ledger mode. |
| **R-05** | **The monthly budget guard clamps without exposing the scale; `cash` has a silent floor.** | `goalpilot_env.py:469-483` applies a two-stage `guard_scale` / `final_scale` to savings, investment **and** credited amounts, and neither scale is reported. `:558-561` wraps cash in `max(0.0, ...)`. The archived `combined_commitment > surplus` invariant (`:612-623`) raises instead of clamping, so the guard is a second, silent layer that can mask re-allocation events from the audit trail. | **S2** | Add `guard_scale` (product of both stages) and `cash_floor_active` to `budget_audit`; add an assertion/test showing the floor is never active under any reachable configuration. | `test_budget_guard_is_exposed_and_never_binds` — asserts `budget_audit["guard_scale"] == 1.0` and `cash` is never floored for every baseline policy in `corrected_accounting`. |
| **R-06** | **Per-month net-worth reconciliation residual is not fully attributed.** | `D5_recon_attribution.csv`: *episode-level* residual is fully explained by R-01 — `corrected_accounting` max \|residual\| ₹2,534.52 with aggregate write-offs ₹5,080.95 over 4 events; `lp_parity`/`recommended` ₹236.48 with write-offs ₹472.96 over 2 events (residual == write-off exactly). The `archived` residual is ₹13,352,497.35, the already-documented legacy double count (F-04 / AUDIT_REPORT §4.4.1). A separate probe aggregate (`sum_residual_all_events`, ≈₹1.70–1.78 x 10^8, ~₹10.4k per month-event) is **not yet attributed** and is *not* claimed to be a defect. | **S2** (measurement gap) | Emit a per-month cause breakdown: `interest_shortfall` (R-04), `residual_settled`/`writeoff` (R-01), `guard_scale` (R-05). Then assert `net_worth_change == expected_net_worth_change` per month in ledger mode. | `test_net_worth_reconciliation_per_month` — parameterised over all six baseline policies; residual < ₹0.01 per month. |
| **R-07** | **Reward design defects confirmed (inputs to Phase D, not yet fixed).** | `reward_decomposition_summary_*.csv`: components reconcile to the env reward to `max_abs_component_residual <= 1.8e-15` for all 6 policies in both `archived` and `lp_parity`. But: (a) `risk_penalty` dominates for Investments-only — **−270.44** of a −422.96 total vs −27.38 for Savings-only, i.e. a 10x multiply, because it scales with `portfolio/100000` and has **no offsetting terminal net-worth term**; (b) PPO earns the **lowest** progress reward of any active policy (**+29.99** vs +44.48); (c) `deadline_shortfall_penalty` fires only in the exact deadline month (`:594`), so there is no gradient to finish a goal early; (d) `loan_penalty` is `1e-5 x new_loan` (−11.84 for Savings+loan) against a mean interest cost of ₹19,028 per user. | **S1** (for training readiness) | Phase D: keep the archived reward untouched; add separately configurable candidate rewards with normalised progress, a distributed (not decision-month-only) shortfall signal, a risk term that is a *downside* measure rather than a wealth-scaled charge, and a **single** terminal net-worth/goal-achievement term that does not double-pay incremental progress. | Phase D harness: `test_candidate_reward_components_sum_to_reward` (tolerance 1e-12) plus per-policy component tables written to `outputs/reward_design/v1/`. |
| **R-08** | **Funds capped by the per-goal limit are not reallocated.** | `goalpilot_env.py:407-422`: `goal_cap_scale` reduces both channels for any goal whose remaining need is smaller than the request; the released budget becomes `unallocated_surplus` rather than being redirected to under-funded goals. Consequence: a policy cannot fill several goals in one month at full efficiency, while the LP can. | **S3** | Document as a known RL/LP behavioural difference for Phase E, or add an optional redistribution pass that re-solves the allocation over goals with remaining need. Do not change the archived path. | `test_goal_cap_does_not_lose_budget` (budget identity holds) and, if redistribution is added, `test_goal_cap_redistributes_to_unfunded_goals`. |
| **R-09** | **Cross-config earmark divergence changes `goal_balances` independently of the policy.** | `D3_goal_credit_semantics.csv`: `USER_00031` books ₹67,315.79 of pre-existing earmark under `archived` but ₹0 under `recommended` — because the emergency reserve changes `funding_scale` in the earmark reconciliation (`:262-273`). This is a *config* difference, not an agent behaviour, and must be controlled for in any archived-vs-recommended comparison. | **S3** | Document; in Phase E hold the reserve policy fixed when comparing policies, and report earmark reconciliation deltas alongside funding ratios. | `test_earmark_reconciliation_respects_reserve` — asserts `reconciled_earmarked + cash + reserve == initial_savings` at reset. |

### Carried-forward known defect (not re-opened)

| # | Finding | Status |
|---|---|---|
| **R-10** | Legacy/archived wealth aggregation double counts contributions (`cash` + `goal_balances`) and discards unallocated surplus (F-04 / §4.4.1). | **Confirmed, documented, deliberately preserved.** `GoalPilotConfig.archived()` reproduces the 2026-10-10 environment byte-for-byte and the archived CSVs verify against it. Not to be "fixed" — requirement 7/§4. |

---

## 3. Hypotheses tested and **refuted**

Recorded explicitly so they are not mistaken for defects.

| Hypothesis | Test | Result |
|---|---|---|
| **H-1** (mine, Phase A): `action_mode="share"` structurally prevents loan origination, because after normalisation `available_after_existing_loan − savings.sum() − invest.sum() ≈ 0`, so `emi_budget ≈ 0`. | `31_probe_followup.py` D2b: `magnitude` x `share` x `face_value` x `growth_weighted`, two borrowing policies, 20 held-out users. | **REFUTED.** Borrowing is *bit-identical* across all four combinations: `Savings+loan (0.5,0,1)` → 16 origination-months, ₹9,24,617.82; `Loan only (0,0,1)` → 33 origination-months, ₹41,70,436.05. Reason: the per-goal cap (`goal_cap_scale`) shrinks `savings_alloc`/`invest_alloc` *before* `emi_budget` is computed (`:439-446`), leaving a positive EMI budget. |
| **H-2**: the goal-credit mode changes borrowing behaviour. | same probe | **REFUTED** — identical to 15 significant figures. |
| **H-3**: `_credit_goals()` uses the wrong time remaining. | direct code reading: `goal_deadlines` are 1-based, `month_index` is 0-based pre-increment, and the deadline check uses `month_index + 1` (`:594`); `months_left = max(0, deadline − month_index)` (`:357`) is therefore the correct number of remaining months *including the current one*. | **REFUTED** — the horizon arithmetic is correct. The defect is the *concept* (R-03), not the arithmetic. |

---

## 4. Verified-correct behaviours (no change proposed)

| Area | Evidence |
|---|---|
| Reward components reconcile to the env reward | `max_abs_component_residual <= 1.8e-15` for 6 policies x 2 configs, 2,840 user-months each |
| All-zero action is a genuine no-op in `share` mode | `goalpilot_env.py:308-312`; `action_mode_comparison.csv` shows No-action funding ratio 0.00147 (not 0.19) |
| Investment capacity is honoured, including zero, without losing budget | `:321-331` — overflow is returned to savings |
| Loan proceeds credited exactly once | `:560` (`cash += new_loan`) and `:569-570` (memo earmark `<= new_loan`) |
| Loan limits and affordability enforced | `:439-462` — `emi_budget` bounded by remaining discretionary budget and `income x emi_income_ratio_cap − existing_emi − loan_emi`; capped by `max_new_loan` and remaining goal need |
| Monthly cash-flow invariant raises rather than clamps | `:612-623` |
| Archived parity intact | full 64-test suite passes unchanged, including `test_goalpilot_env_parity.py` (100 users x 5 policies x 142 months, reward to 1e-12) |

---

## 5. Genuine financial-model ambiguities — alternatives and recommendations

The task requires these to be documented rather than silently assumed. **Recommendations below need your decision before Phase B/D implementation, because they change headline `net_worth` and funding figures.**

### A-1 — How should growth-weighted goal credits be treated? (drives R-03)

| Option | Consequence |
|---|---|
| **(a) Keep as-is** — projected compounded value booked into `goal_balances` | Retains LP/RL conceptual parity (the LP also assumes a deterministic 5 % return), but the RL "goal funded" figure is a projection, not wealth; it conflicts with the stochastic NIFTY path the same money actually earns; the goal cap and loan sizing both key off the inflated figure. Violates §5 C2 as written. |
| **(b) `market_weighted`** — credit the contributed amount plus only *realised* market revaluation of the invested portion; expose projected value as a separate memo | ✅ **Recommended.** Each rupee counted once, `goal_balances` stays ≤ `cash + portfolio`, the savings-only/mixed degeneracy is still broken (by real returns), and Phase E can report nominal vs inflation-adjusted funding honestly. Cost: `recommended()` goal objectives become harder, so recommended-config funding ratios will fall relative to today's `growth_weighted` numbers. |
| **(c) Drop growth weighting entirely** (face value everywhere) | Simple and defensible, but re-creates the F-01 degeneracy in the recommended config, which §5 C3 explicitly asks to avoid. |

### A-2 — How should the emergency reserve be represented? (drives R-02)

| Option | Consequence |
|---|---|
| **(a) Restricted cash on the balance sheet** | ✅ **Recommended.** `initial_net_worth = initial_savings + initial_investment`; LP and RL become comparable on net worth; the reserve is non-spendable by construction already. Cost: `lp_parity`/`recommended` net worth rises by ₹13.8k–₹133k per user (mean ≈ ₹64k on the sampled users); `archived` and `corrected_accounting` (`emergency_months = 0`) are unaffected. |
| **(b) Keep it virtual/off-sheet** | Preserves current numbers but understates net worth by the full reserve in every `lp_parity`/`recommended` result and makes any LP-vs-RL net-worth claim invalid (§4 B2). |

### A-3 — Accrual or forgiveness for unpaid interest? (drives R-04)

`actual_payment = min(emi_due, payoff_amount, surplus)`; `interest_due` is booked as paid regardless.

| Option | Consequence |
|---|---|
| **(a) Capitalise the shortfall** (accrual) | ✅ **Recommended.** Liability stays real, `net_worth_change == expected_net_worth_change` holds every month. Introduces negative amortisation *if* the cap ever binds — which requires demonstrating reachability; the origination constraint (`new_emi <= surplus − savings − invest`, and `surplus` is constant per user) suggests it is **not** reachable, in which case the shortfall is structurally zero and the fix is an assertion rather than a behavioural change. |
| **(b) Report cash interest and flag the shortfall only** | Cheaper, still removes the misleading `interest_paid` figure, but leaves net worth overstated by the shortfall if it ever occurs. |

**Not yet settled:** whether the shortfall is reachable at all. Proposed: implement (a) with an explicit `interest_shortfall` audit field and a test asserting zero across all policies; if the test fails, the residual balance is the evidence that a real affordability defect exists at origination.

---

## 6. Open items requiring further measurement (not claimed as defects)

| Item | Status |
|---|---|
| Cause breakdown of the per-month net-worth residual (≈₹1.7–1.8 x 10^8 aggregate) | **Not attributed.** Needs the R-05/R-04/R-01 audit fields. |
| `monthly_financial_simulation_base.csv` (959 MB), `portfolio_simulation_validated.csv` (169 MB) | Content **not** validated — schema only (as already stated in `docs/EXECUTION.md`). |
| Whether loan-EMI capping by `surplus` is reachable | Not demonstrated; see A-3. |
| Google Colab execution | **Not run.** Colab readiness verified structurally only. |

---

## 7. Evidence inventory

```
outputs/audit/final_validation_v1/
  D1_loan_amortisation_events.csv          12 write-off events (balance_before/interest_due/emi_paid/residual)
  D1_D4_D5_ledger_by_policy.csv            per-policy ledger + reconciliation residual
  D2_share_mode_borrowing.csv              first share-mode borrowing probe
  D2b_share_face_value_borrowing.csv       refutation of H-1/H-2 (4 mode combinations)
  D3_goal_credit_semantics.csv             contributed vs booked vs realised portfolio value
  D5_recon_attribution.csv                 episode residual vs write-off sums, 4 configs
  D6_emergency_reserve_balance_sheet.csv   reserve vs on/off balance-sheet assets, 2 configs
  probe_summary.json, probe_followup_summary.json
outputs/evaluation/
  pytest_baseline_final_validation.txt     64 passed
  pytest_lp_baseline_final_validation.txt  26 passed
  final_validation_v1/PHASE_A_FINDINGS.md  this document
```

## 8. Recommended order for Stage 2 (subject to your decision on A-1/A-2/A-3)

1. **R-01** residual-lien settlement + regression test (gated to ledger mode; archived parity preserved).
2. **R-04/R-05** audit-field exposure (`interest_paid_cash`, `interest_shortfall`, `guard_scale`, `cash_floor_active`) + per-month reconciliation test **R-06**.
3. **R-02** restricted-cash representation + test.
4. **R-03** `market_weighted` credit mode for `recommended()`; `growth_weighted` retained for archived/LP-parity reproduction only.
5. Re-run both suites (64 + 26) and re-run the archived-parity verification, then proceed to Phases C/E.

---

## 9. Addendum — corrections made during Stage 2 verification

Two claims in the table above are corrected by the Stage 2 work. They are recorded here
rather than silently rewritten, so the inspection record stays auditable.

1. **R-06 — the "≈₹1.7–1.8 × 10⁸ aggregate" figure is withdrawn as a mis-derived metric.**
   `31_probe_followup.py:43` computed `sum_residual_all_events` as
   `events["residual_unamortised"].sum()`, but `30_final_validation_probe.py:82` appends an
   event for *every* month in which `prev_balance + interest − paid > 1e-6` — which is every
   month of every loan, not only true residuals. The number was therefore a sum of
   outstanding principal, not a reconciliation residual; that is why it came out identical
   for `archived` and `corrected_accounting`.
   **Corrected statement:** the episode-level reconciliation residual in ledger mode is
   fully explained by R-01 and is otherwise **exactly zero** — `corrected_accounting`
   max |residual| ₹2,534.52 = its single write-off; `lp_parity` / `recommended`
   ₹236.48 = their single write-off.

2. **R-04 — severity reduced from S2 to S3.** `interest_paid` was never actually
   overstated in a reachable configuration. With `new_emi <= surplus − savings − invest`
   enforced at origination, the cap `current_emi_due = min(scheduled_emi, payoff_amount,
   surplus)` cannot bind below the interest due, so accrued and cash interest coincide.
   Stage 2 measured `interest_shortfall == 0` for 3 users x 4 policies x 142 months x 2
   presets. R-04 is therefore an **audit-completeness** issue — two different interest
   quantities were conflated under one field name and an unpaid-interest path could have
   been silently forgiven had the cap ever bound — not a live valuation error.

**Status after Stage 2:** R-01, R-04, R-05 and R-06 are **confirmed and fixed**
(see `STAGE2_LEDGER_FIXES.md` in this directory). R-02 and R-03 remain
**confirmed but unresolved**, pending the decision on ambiguities A-1 and A-2 above.
R-07 to R-09 remain open and are scheduled for Phases D and E. R-10 is deliberately
unfixed.
