# GoalPilot AI — Stage 2: Ledger Correctness Fixes

**Stage:** 2 of 6 in the execution order (§13) — *fix confirmed financial-accounting defects with regression tests*.
**Date:** 2026-10-11
**Working copy:** `S:\fyp\GoalPilot_AI_Completed` (authoritative original `S:\fyp\GoalPilot_AI` still untouched)
**Interpreter:** `C:\Users\sudha\AppData\Local\Programs\Python\Python313\python.exe` (3.13.7)

Supersedes nothing. All Phase A artefacts and every archived result are preserved.

---

## 1. Files modified

| File | Change | Reason | Finding |
|---|---|---|---|
| `simulation/05_simulation_runs/rl_prototype/goalpilot_env.py` | Loan-repayment block (~L514–559), budget-guard block (~L464–486), cash-movement block (~L569–620), audit trail (~L688–750) | See §2 | R-01, R-04, R-05, R-06 |
| `tests/test_goalpilot_env_ledger_integrity.py` | **New** — 11 regression tests | Pins the fixed behaviour | R-01, R-04, R-05, R-06 |
| `outputs/evaluation/final_validation_v1/PHASE_A_FINDINGS.md` | Addendum §9 correcting two claims | Inspection record must stay auditable | R-04, R-06 |

**Not modified:** the domain reward function, PPO hyper-parameters, the LP optimizer, every
dataset, both model checkpoints, all `goalpilot_env.py.pre_*.bak` backups, the archived
environment copy, and every archived result CSV. No archived behaviour was removed.

---

## 2. What changed and why

### R-01 — residual loan principal is no longer silently written off

**Before** the repayment block ended with:

```python
if self.loan_balance <= 1e-6 or self.loan_months_left == 0:
    self.loan_balance = 0.0
```

Because the level EMI is fixed at the **origination** month's rate while interest accrues at
each month's **actual** rate, the schedule can leave a small principal residual when the
tenure runs out. The condition above then erased it with no cash movement and no recorded
event — 12 occurrences over 560 episodes, largest ₹2,534.52
(`outputs/audit/final_validation_v1/D1_loan_amortisation_events.csv`).

**After**, the clearing and the expiry cases are separated:

```python
if self.loan_balance <= 1e-6:
    ...  # genuinely repaid
elif self.loan_months_left == 0:
    if self.config.accounting_mode == ACCOUNTING_MODE_LEDGER:
        residual_due = self.loan_balance          # keep the liability
    else:
        residual_written_off = self.loan_balance  # archived behaviour, preserved
        ...
```

and the residual is then discharged in the cash-movement block:

```python
if residual_due > 0.0:
    residual_settled_cash = min(residual_due, self.cash)   # cash out
    self.cash -= residual_settled_cash
    outstanding = residual_due - residual_settled_cash
    if outstanding > 1e-6:
        self.loan_balance = outstanding      # keep it on the books...
        self.loan_months_left = 1            # ...and keep servicing it
        residual_carried = outstanding
```

Two documented accounting events replace one undocumented disappearance. Settlement is
net-zero on net worth (cash down, liability down), so the reconciliation identity is
unaffected; a carried residual stays a liability and keeps being serviced.

### R-04 — cash interest and accrued interest are now separate quantities

`interest_paid_cash = min(actual_payment, interest_due)` and
`interest_shortfall = interest_due − interest_paid_cash` are computed and reported.
`info["interest_paid"]` now reports the **cash** figure; `info["interest_accrued"]` reports
the accrual figure; `budget_audit` reports both plus the shortfall. In `ledger` mode any
shortfall is capitalised into `loan_balance` rather than being forgiven.

Measured severity: the shortfall is **zero in every reachable configuration** (the
origination constraint `new_emi <= surplus − savings − invest` means the EMI cap never binds
below interest due), which is why Phase A's S2 rating was corrected to S3 in the addendum.
This change is therefore audit completeness plus a guard against silent forgiveness, not a
change to any reported number.

### R-05 — the budget guard and the cash floor are exposed

`budget_audit["guard_scale"]` now carries the product of both re-scaling stages applied to
the savings/investment/credited allocations, and `budget_audit["cash_floor_active"]` records
whether the `max(0.0, …)` cash floor ever engaged. §4 B4 requires that a clamp be visible
rather than silent; previously both were invisible.

### R-06 — per-month reconciliation is now assertable

`budget_audit` exposes `interest_accrued`, `interest_paid_cash`, `interest_shortfall`,
`guard_scale`, `cash_floor_active`, `residual_settled_cash`, `residual_carried` and
`residual_written_off`, so the net-worth identity can be checked month by month and every
otherwise-invisible event is attributable.

---

## 3. Tests added — `tests/test_goalpilot_env_ledger_integrity.py`

| Test | What it pins |
|---|---|
| `test_residual_lien_is_settled_or_carried_never_written_off` (x2, parameterised) | Reproduces `USER_00078`/`corrected_accounting` (₹2,534.52, month 138) and `USER_00081`/`lp_parity` (₹236.48, month 138). Asserts no write-off in ledger mode, the event still occurs at the recorded month and amount, settlement debits cash and clears the liability, a carry keeps it on the books, and the net-worth identity holds |
| `test_cash_flow_conservation_with_residual_settlement` (x2) | Every month: `Δcash == surplus − EMI − investment + new_loan − residual_settled_cash` |
| `test_archived_mode_keeps_the_historical_write_off` | Proves the fix is gated: `archived()` still writes off ₹2,534.52 at month 138 and never settles in cash |
| `test_interest_paid_is_cash_interest_and_shortfall_is_zero` (x2) | 3 users x 4 policies x 142 months: `interest_shortfall == 0`, `interest_paid_cash == interest_accrued`, `total_interest_paid` equals the summed cash interest |
| `test_budget_guard_and_cash_floor_are_exposed` (x2) | `guard_scale` always reported and in `(0, 1]`, exactly 1.0 when no re-scaling is needed, `cash_floor_active` never True, budget identity holds |
| `test_net_worth_reconciliation_holds_every_month` (x2) | 4 users x 6 policies x 142 months in `corrected_accounting` and `lp_parity` |

`R-01` was invisible to the existing suite because both offending users (`USER_00078`,
`USER_00081`) fall outside the 6-user `small_slice` fixture used by
`test_goalpilot_env_accounting.py`.

---

## 4. Test execution — real console output

All three commands were executed with the documented interpreter. Nothing below is projected.

```
$ python -m pytest tests\test_goalpilot_env_ledger_integrity.py -q

...........                                                              [100%]
11 passed in 12.28s
```

```
$ python -m pytest -q          # project root, full RL suite

........................................................................ [ 96%]
...                                                                      [100%]
75 passed in 410.40s (0:06:50)
```

```
$ cd GoalPilot_MultiGoal_Extension
$ python -m pytest -q

..........................                                               [100%]
26 passed in 3.67s
```

**Totals: 64 pre-existing RL tests + 11 new = 75, all passing; 26 LP tests passing; 0 failures,
0 errors, 0 skips.** The full-suite run includes `test_goalpilot_env_parity.py`
(100 users x 5 policies x 142 months against the archived environment module, reward to
1e-12), so **archived reproduction is still exact after the fix**.

Raw console logs: `pytest_ledger_integrity.txt`, `pytest_full_suite_after_fixes.txt`,
`pytest_lp_suite_after_fixes.txt` (all in this directory).

---

## 5. Status of the Phase A findings

| Finding | Status |
|---|---|
| R-01 residual lien silently written off | **Confirmed and fixed** (ledger mode); archived path deliberately preserved |
| R-04 `interest_paid` conflated accrued/cash interest | **Confirmed and fixed**; severity corrected S2 → S3 after measurement |
| R-05 budget guard / cash floor invisible | **Confirmed and fixed** |
| R-06 per-month reconciliation unattributable | **Confirmed and fixed**; the accompanying "aggregate residual" figure withdrawn as mis-derived |
| R-02 emergency reserve off the balance sheet | **Confirmed, unresolved** — awaits the A-2 decision |
| R-03 `growth_weighted` books projected returns | **Confirmed, unresolved** — awaits the A-1 decision |
| R-07 reward-design defects | **Confirmed, unresolved** — Phase D |
| R-08 goal-cap funds not reallocated | **Open** — Phase E documentation |
| R-09 earmark divergence across configs | **Open** — Phase E control |
| R-10 legacy double count | **Confirmed, deliberately preserved** |

---

## 6. Reproducing this stage

```powershell
$py = "C:\Users\sudha\AppData\Local\Programs\Python\Python313\python.exe"
Set-Location S:\fyp\GoalPilot_AI_Completed
& $py -m pytest tests\test_goalpilot_env_ledger_integrity.py -q
& $py -m pytest -q
Set-Location GoalPilot_MultiGoal_Extension
& $py -m pytest -q
```

---

## 7. Remaining limitations introduced or carried forward

1. **R-02 and R-03 are not fixed.** `lp_parity`/`recommended` net worth still omits the
   emergency reserve, and `growth_weighted` still books projected growth as goal funding.
   Both need the A-1/A-2 decision before implementation.
2. **A carried residual keeps the loan "active", which blocks a new origination in the
   following month.** This is realistic but is new behaviour; it is visible on
   `residual_carried` and has not yet been exercised by any policy that cannot settle, so
   the carried branch is covered by assertion but not by an observed real case.
3. **The reward function is still the archived one.** R-07 is diagnosed and quantified, not
   fixed.
4. **PPO has not been retrained** and the existing checkpoint is still only valid under
   archived semantics.
5. **No large dataset was content-validated** — `monthly_financial_simulation_base.csv`
   (959 MB) and `portfolio_simulation_validated.csv` (169 MB) remain schema-inspected only.
6. Re-running `evaluation/run_all.py` is required before `outputs/evaluation/*.csv`
   reflect the R-01 fix; the existing CSVs were produced before it and are preserved as the
   pre-fix record.
