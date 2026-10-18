# Execution Record — GoalPilot AI

**Date:** 2026-10-10
**Host:** Windows 11 (10.0.26300), 16 logical cores, 16.83 GB RAM, **no GPU**
**Interpreter:** `C:\Users\sudha\AppData\Local\Programs\Python\Python313\python.exe` (3.13.7)
**Working copy:** `S:\fyp\GoalPilot_AI_Completed`

Everything below was actually executed. Nothing in this document is projected or assumed.
Where a stage failed or was skipped, it is stated as such.

> **Interpreter note.** Bare `python` on this machine resolves to
> `…\Accio\pre-install\bd5ff2c6816a\python\python.exe` (3.12.2), which has **no** project
> dependencies. All commands below used the full path to Python 3.13.

---

## 0. Dependencies installed during this work

`gymnasium`, `stable_baselines3`, `sb3_contrib` and `pulp` were absent and were installed:

```powershell
& $py -m pip install "gymnasium>=0.29" "stable-baselines3>=2.3" "sb3_contrib>=2.3" "pulp>=2.7"
```

Result: `gymnasium 1.4.0`, `stable_baselines3 2.9.0`, `sb3_contrib 2.9.0`, `pulp 4.0.0`.
(`pulp` turned out not to be needed — the LP uses `scipy.optimize.linprog(method="highs")`.)

Resolved versions of everything else that matters: `numpy 2.2.3`, `pandas 2.3.1`,
`scipy 1.16.0`, `scikit-learn 1.7.2`, `statsmodels 0.14.6`, `matplotlib 3.10.3`,
`seaborn 0.13.2`, `plotly 6.2.0`, `torch 2.8.0+cpu`, `tensorboard 2.20.0`, `pytest 9.1.1`,
`nbformat 5.10.4`, `nbconvert 7.17.1`, `psutil 7.0.0`.

---

## 1. Baseline — original project, before any change

```powershell
Set-Location S:\fyp\GoalPilot_AI\GoalPilot_MultiGoal_Extension
& $py -m pytest tests -q
```

```
..........................                                               [100%]
26 passed in 4.02s
```

**Note:** the committed `outputs/test_results.txt` claims *"11 passed in 0.96s"*. That file is
**stale** — it predates 15 later tests. The live suite is 26 and all pass.

---

## 2. Audit evidence

```powershell
& $py S:\fyp\_audit\00_env_check.py        # dependency + hardware probe
& $py S:\fyp\_audit\01_notebook_compare.py # notebook comparison
& $py S:\fyp\_audit\02_inventory.py        # inventory + duplicate detection
& $py S:\fyp\_audit\03_extract_nb.py       # notebook -> flat source + cell index
& $py S:\fyp\_audit\10_diag_env.py         # F-01, F-02, F-04 measurement
```

Copies of all six scripts are in `audit_tools/`, with the raw CSVs in
`audit_tools/diag_baseline/`.

### 2.1 Inventory result

```
TOTAL FILES: 552  TOTAL MB: 4,800.2
duplicate groups: 147
redundant bytes : 3,128.03 MB
```

### 2.2 Notebook comparison result

```
[ROOT]      S:\fyp\GoalPilot_RL_PreCheck.ipynb
[IN_FOLDER] S:\fyp\GoalPilot_AI\Copy of GoalPilot_RL_PreCheck.ipynb
  cells = 144 both, code_with_outputs = 142 both
  nb total source chars = 271,463 both
SOURCE-LEVEL DIFF
identical_source = True
```

### 2.3 Baseline diagnostics (the F-01 / F-02 / F-04 evidence)

```
=== POLICY SUMMARY (100 users each) ===
        policy  mean_funding_ratio  mean_funded  mean_final_portfolio  mean_unallocated  mean_reward
 Savings only             0.2735   1220790.18             165778.06         776755.09      -7.9173
 Mixed allocation         0.2735   1220790.18             710294.22         776755.09     -11.6654
 Investments only         0.2440   1140057.11            2259643.42         857488.15     -23.1258
 Flat 0.25 savings        0.2527   1150004.96             165778.06         847540.31      -8.1805
 Flat 0.50 savings        0.2735   1220790.18             165778.06         776755.09      -7.9173
 Flat 0.75 savings        0.2735   1220790.18             165778.06         776755.09      -7.9173

=== H1: Savings-only vs Mixed allocation goal funding ===
users where |mixed - savings| <= 1e-12 : 100 / 100
max abs difference                       : 1.665e-16
max abs funded_sum difference            : 1.397e-09
median |portfolio difference|            : 237,955.72

=== H4: degeneracy vs goal count / investment capacity ===
goal count vs exact match:      n_goals 3 -> 40, 4 -> 30, 5 -> 30   (all exact)
theoretical identity n >= 2/(1+ICR) vs observed exact match:  True/True = 100
```

### 2.4 Deeper reference checks (run inline, not as scripts)

- `User_00001` ledger reconstruction: `final_cash == initial_cash + contributions` → `True`
  for all sampled users, and `goal_balances == earmark + contributions` → `True`.
- `max_goals` inference: full panel 5; train slice 5; test slice 5 (so nothing broke — but the
  fragility is real and is now pinned by `n_goal_slots`).
- Per-user double-count arithmetic quoted in `AUDIT_REPORT.md` §4.4 was verified numerically
  against `rl_baseline_policy_comparison.csv`.

---

## 3. Implementation validation

### 3.1 Archived parity — the critical regression guard

```powershell
& $py -m pytest tests\test_goalpilot_env_parity.py -q
```

```
...                                                                      [100%]
3 passed in 158.29s (0:02:38)
```

This rolls out **100 users × 5 policies × 142 months** against both the archived environment
module and the reworked one, and compares month by month:

- `total_reward` to `1e-12`
- `goal_balances`, `goal_targets` to `1e-9`
- `cash`, `portfolio`, `loan_balance` to `1e-6`
- per-month `reward`, `savings_contribution`, `investment_contribution`,
  `new_loan_principal`, `new_loan_emi`, `active_loan_emi`,
  `combined_monthly_commitment`, `monthly_surplus`

### 3.2 Intermediate full-suite runs

| run | when | result |
|---|---|---|
| after parity + accounting suites | mid-implementation | `18 passed in 134.66s` |
| after mode fixes | mid-implementation | `8 passed in 11.20s` |
| after accounting test correction | mid-implementation | `7 passed in 14.36s` |
| after lifecycle fixes | mid-implementation | `18 passed in 13.02s` |
| config + paths + LP parity | mid-implementation | `28 passed in 0.81s` |
| collection with `pytest.ini`, no env vars | mid-implementation | `64 tests collected in 0.57s` |
| **final: full suite, no env vars, one command** | **after all edits** | **`64 passed in 153.49s`** |

### 3.2.1 Final validation (authoritative)

```powershell
Set-Location S:\fyp\GoalPilot_AI_Completed
Remove-Item Env:PYTHONPATH          # prove pytest.ini alone is sufficient
& $py -m pytest -q
```

```
................................................................         [100%]
64 passed in 153.49s (0:02:33)
```

```powershell
Set-Location S:\fyp\GoalPilot_AI_Completed\GoalPilot_MultiGoal_Extension
& $py -m pytest -q
```

```
..........................                                               [100%]
26 passed in 1.22s
```

Verbatim console output: `outputs/evaluation/pytest_final.txt` and
`outputs/evaluation/pytest_lp_final.txt`.

**Totals: 64 new tests + 26 extant LP tests = 90 tests, 0 failures, 0 errors, 0 skips.**
No environment variables were set, confirming `pytest.ini` makes the project self-contained.

### 3.3 Portable notebook

```powershell
& $py audit_tools\20_make_portable_notebook.py `
    "GoalPilot_AI_Completed\Copy of GoalPilot_RL_PreCheck.ipynb" `
    "GoalPilot_AI_Completed\GoalPilot_RL_PreCheck_portable.ipynb"
```

```
source cells        : 144
cells path-patched  : 114
cells disabled      : 14  (in-place goalpilot_env.py writers)
output cells        : 145 now
```

Syntax validation of every executable cell: **0 syntax errors**.
Bootstrap cell executed successfully from the project root *and* from the workspace root
(the latter via the one-level-down search, preferring a `…Completed` folder).

---

## 4. Full evaluation pipeline

```powershell
Set-Location S:\fyp\GoalPilot_AI_Completed
& $py evaluation\run_all.py --project-root .
```

**Result: `ALL EVALUATION STAGES COMPLETED` — every stage exited 0. Total wall time 486 s.**
Full raw console: `outputs/evaluation/run_all_console.txt` (48,526 bytes).

Stage timings and exit codes as reported by the orchestrator:

| stage | exit | seconds |
|---|---:|---:|
| archive verification | 0 | 1.0 |
| policy eval `archived` / all | 0 | 98.7 |
| policy eval `archived` / test | 0 | 27.9 |
| policy eval `corrected_accounting` / all | 0 | 95.4 |
| policy eval `corrected_accounting` / test | 0 | 28.2 |
| policy eval `lp_parity` / all | 0 | 102.1 |
| policy eval `lp_parity` / test | 0 | 31.1 |
| action-mode comparison | 0 | 28.1 |
| reward decomposition `archived` | 0 | 28.4 |
| reward decomposition `lp_parity` | 0 | 9.5 |
| borrowing audit `corrected_accounting` | 0 | 9.6 |
| borrowing audit `archived` | 0 | 2.5 |
| plots | 0 | — |

### 4.1 Archive verification

```
[PASS] rl_baseline_policy_comparison.csv        vs policy_detail_archived_all.csv   : 4800 comparisons, 0 mismatches
[PASS] rl_policy_diagnostic_summary.csv         vs policy_summary_archived_all.csv  :   16 comparisons, 0 mismatches
[PASS] rl_heldout_policy_comparison_detail.csv  vs policy_detail_archived_test.csv  :  700 comparisons, 0 mismatches
[PASS] rl_heldout_policy_comparison_summary.csv vs policy_summary_archived_test.csv :   25 comparisons, 0 mismatches
OVERALL: PASS
```

### 4.2 Figures produced

```
01_funding_ratio_by_policy_archived_all.png    45.6 KB
02_funding_ratio_by_policy_archived_test.png   45.6 KB
03_net_worth_double_count.png                  57.2 KB
04_reward_components.png                       77.2 KB
05_borrowing_audit.png                         70.3 KB
06_action_mode_comparison.png                  51.2 KB
```

### 4.3 Action-mode comparison — the F-02 fix, measured

`outputs/evaluation/action_mode_comparison.csv` (held-out users, `lp_parity` basis):

| action_mode | policy | mean funding ratio | mean unallocated surplus |
|---|---|---:|---:|
| magnitude | Flat 0.25 savings | 0.17960 | 782,167.92 |
| magnitude | Flat 0.50 savings | 0.19292 | 694,266.25 |
| magnitude | Flat 0.75 savings | 0.19292 | 694,266.25 |
| magnitude | Savings only | 0.19292 | 694,266.25 |
| **share** | Flat 0.25 savings | **0.19292** | **694,266.25** |
| **share** | Flat 0.50 savings | **0.19292** | **694,266.25** |
| **share** | Flat 0.75 savings | **0.19292** | **694,266.25** |
| **share** | Savings only | **0.19292** | **694,266.25** |

In `share` mode every constant action from 0.25 upward allocates the whole budget and yields
identical funding. In `magnitude` mode, 0.25 loses 1.33 percentage points of goal funding
(0.17960 vs 0.19292) — 88,000 of monthly surplus left unallocated that a policy could not
recover.

### 4.4 A new finding the corrected ledger exposed

`outputs/evaluation/policy_summary_corrected_accounting_test.csv` vs the archived
`rl_heldout_policy_comparison_summary.csv`:

| policy | archived net wealth | corrected ledger net worth | mean unallocated surplus |
|---|---:|---:|---:|
| No action | 232,303.39 | **2,030,439.84** | 1,798,136.44 |
| Savings only | 1,302,720.08 | 2,030,439.84 | 727,719.76 |
| Investments only | 2,182,848.29 | 2,983,077.47 | 800,229.18 |
| PPO | 887,092.48 | 2,098,076.46 | 1,128,588.05 |

The difference equals the unallocated surplus exactly, because the archived environment never
recorded unallocated surplus in any account. Written up in `AUDIT_REPORT.md` §4.4.1.

### 4.5 LP-parity basis

`outputs/evaluation/policy_summary_lp_parity_test.csv` — same users, but with the LP's inflated
3 % goal targets and 6-month emergency reserve:

| policy | mean funding ratio | mean net worth | mean new loan principal | mean reward |
|---|---:|---:|---:|---:|
| No action | 0.00147 | 1,975,351.22 | 0 | −13.853 |
| Savings only | 0.19292 | 1,975,351.22 | 0 | −8.885 |
| Investments only | 0.18338 | 2,966,493.14 | 0 | −21.880 |
| Mixed (0.50/0.50) | 0.19292 | 2,254,494.86 | 0 | −12.328 |
| Savings + loan | 0.19587 | 1,964,697.93 | 46,230.89 | −9.331 |
| PPO | 0.14619 | 2,055,804.71 | 76,166.34 | −12.255 |

Funding ratios fall relative to the nominal basis because the targets are inflated — which is
precisely the F-06 mismatch that made the original LP-vs-RL comparison invalid.

---

## 5. What was NOT executed

| item | reason |
|---|---|
| **PPO retraining** | Explicitly deferred: the task required diagnostics before any reward change. The archived 50 k-step checkpoint is still the only one |
| PPO evaluated under `action_mode="share"` | Would require a new checkpoint; running the archived policy under share semantics is not a meaningful comparison |
| Content validation of `monthly_financial_simulation_base.csv` (959 MB) and `portfolio_simulation_validated.csv` (169 MB) | Exceeds the safe working set against 5.61 GB free RAM; schemas inspected only (F-14) |
| Independent re-derivation of `generate_multigoal_dataset.py` | Read and found internally consistent with its docs; not re-derived (F-15) |
| Google Colab execution | Not reachable from this host. Colab readiness was verified structurally (path resolver + `check_env` + guarded imports), not by running there |

---

## 6. Reproducing this record

```powershell
$py = "C:\Users\sudha\AppData\Local\Programs\Python\Python313\python.exe"
Set-Location S:\fyp\GoalPilot_AI_Completed

& $py -m pytest -q                          # 64 new tests
& $py evaluation\run_all.py --project-root . # every artefact above

Set-Location GoalPilot_MultiGoal_Extension
& $py -m pytest -q                          # 26 extant LP tests
```

Raw console of the pipeline is preserved verbatim at
`outputs/evaluation/run_all_console.txt`.

---

# Addendum — execution record for the 2026-10-11 pass

**Host:** Windows 11, 16 logical cores, 16 GB RAM, **no GPU** (same machine as the record above).
**Interpreter:** `C:\Users\sudha\AppData\Local\Programs\Python\Python313\python.exe` (3.13.7).
**Working copy:** `S:\fyp\GoalPilot_AI_Completed`.

Everything below was actually executed. Where a stage failed, it says so.

## E1. Dependency set captured

```powershell
& $py audit_tools\05a_version_dump.py
```

```
python==3.13.7   numpy==2.2.3     pandas==2.3.1     scipy==1.16.0
sklearn==1.7.2   statsmodels==0.14.6   matplotlib==3.10.3   seaborn==0.13.2
plotly==6.2.0    gymnasium==1.4.0   stable_baselines3==2.9.0   sb3_contrib==2.9.0
torch==2.8.0+cpu tensorboard==2.20.0  pytest==9.1.1   nbformat==5.10.4
nbconvert==7.17.1  pulp==4.0.0
```

Recorded as `requirements.txt` (previously absent) with `pulp` left optional, since the LP uses
`scipy.optimize.linprog(method="highs")`.

## E2. Baseline test verification (the reported 164 / 26 / 190)

```powershell
Set-Location S:\fyp\GoalPilot_AI_Completed ; Remove-Item Env:PYTHONPATH
& $py -m pytest -q
```

```
164 passed in 454.15s (0:07:34)
```

```powershell
Set-Location S:\fyp\GoalPilot_AI_Completed\GoalPilot_MultiGoal_Extension
& $py -m pytest -q
```

```
26 passed in 1.94s
```

**The reported baseline is confirmed: 164 RL + 26 LP = 190 tests, 0 failures, 0 errors, 0 skips.**
Console: `outputs/evaluation/pytest_baseline_recheck_20261011.txt` and
`outputs/evaluation/pytest_lp_baseline_recheck_20261011.txt`.

## E3. Large-CSV content validation (finding F-14 → closed)

```powershell
& $py audit_tools\70_large_csv_validation.py
```

Ran in 46–48 s streaming both files in lockstep. 1,430,000 rows per file, 10,000 users,
2015-02-01 … 2026-12-01.

| identity | comparisons | failures |
|---|---:|---:|
| `portfolio_value[t] == prev × (1+return[t])` | 1,430,000 | 0 |
| `portfolio_return == market_exposure × nifty_monthly_return` | 1,430,000 | 0 |
| `market_exposure == risk_score` | 1,430,000 | 0 |
| `monthly_surplus == income − expenditure` | 1,430,000 | 0 |
| `monthly_surplus == income − expenditure − emi` | 1,430,000 | 601,744 |
| identical key sequence across files | 1,430,000 | 0 |
| `portfolio_return` / `portfolio_value` agree across files | 1,430,000 | 0 |

Duplicates, nulls, non-numeric cells and period-order violations: **all zero** in both files.
Outputs: `outputs/audit/large_csv_validation_v1/`.

The naive EMI-inclusive identity fails on exactly the EMI-carrying rows; the diagnosis
(`audit_tools/71_large_csv_anomaly_diagnosis.py`) shows `monthly_surplus == income − expenditure`
holds on all rows (max deviation 9.5e-11) and that neither surplus nor EMI varies within a user.
This is a **naming/convention** finding (B-1), not corruption.

> **Corrected in-pass.** The first draft of the validator had an inverted mask that skipped the
> anchor row of each chunk, which produced two spurious `portfolio_value` failures. Diagnosing
> rather than trusting the output found it; after the fix the identity has **0** failures.

## E4. Explainability layer (Phase I) — new

```powershell
& $py -m pytest tests\test_goalpilot_explain.py -q
```

```
10 passed in 2.81s
```

## E5. End-to-end demo scenarios (Phase M10–M11)

```powershell
& $py audit_tools\90_demo_end_to_end.py
```

Classification over the 100-user RL sample: **1 feasible / 77 partial / 22 structurally
infeasible**. Selected and executed:

| scenario | user | investable surplus | goals | inflated target | funded | weighted achievement | net worth |
|---|---|---:|---:|---:|---:|---:|---:|
| feasible | `USER_00058` | 19,760.80 | 3 | 505,554.96 | 505,554.96 | 1.0000 | 3,503,590.81 |
| partial | `USER_00001` | 14,481.34 | 3 | 12,592,268.89 | 2,516,588.02 | 0.0800 | 2,817,588.19 |
| infeasible | `USER_00002` | −12,898.95 | 3 | 461,064.58 | 0.00 | 0.0000 | 13,659.35 |

Sensitivity (deterministic): for `USER_00058`, halving the capacity ratio takes achievement from
1.0000 to 0.8669 (shortfall +53,265). Explanations written to `outputs/demo/*.md`.

## E6. Application (Phase J)

```powershell
Set-Location S:\fyp\GoalPilot_Application\backend
& $py -m pytest tests -q
```

```
15 passed in 71.24s
```

Live end-to-end (server started with `uvicorn app.main:app --port 8011`, then stopped):
`GET /api/health` → `"status":"healthy"` with `cpi_calibration_loaded: true` and
`benchmark_dataset_loaded: true`; `POST /api/optimize` → `status "optimal_shortfall"`;
`GET /api/benchmarks` → 200. `node v22.23.2`, `npm 10.9.8` present for the frontend.

## E7. Controlled PPO training and held-out evaluation (Phase H)

```powershell
& $py audit_tools\80_ppo_training_v8.py --stage all
& $py audit_tools\81_ppo_v8_report.py
```

`recommended()`; reward versions `archived_v1` and `candidate_a`; seeds 7/17/27; **50,000
timesteps each**; checkpoint selection on the 16 validation users; evaluation on the 16 held-out
test users against five rule baselines and the capacity-constrained LP. Raw console:
`outputs/evaluation/final_validation_v8/console.txt`; report:
`outputs/reward_design/v8/PPO_TRAINING_AND_EVALUATION.md`.

```
all 6 training runs completed: 353 episodes each, 65-169 steps/s, 46.6 min total training time
held-out mean weighted achievement (16 fresh test users):
  investment-only 0.5800 | mixed allocation 0.5800 | uniform savings 0.5584
  RL archived_v1  0.4842 | RL candidate_a   0.4398 | urgency 0.4051
  need-proportional 0.3211 | constrained_LP 0.2452
0 affordability violations; max budget-identity residual 7.28e-12
```

> **Execution note.** The first attempt used a 100,000-step budget and could not finish inside the
> host's 15-minute background-command limit; the budget was reduced to 50,000 (matching v1/v3) and
> the remaining runs were trained one invocation at a time, skipping completed runs. Two runs were
> cut off mid-flight by the limit and were cleared and retrained from scratch — no partial
> checkpoint was used. A concurrent full-suite run was also terminated by the same limit, which is
> why E8 below was re-run with the machine otherwise idle.

## E8. Full suite after all changes

```powershell
Set-Location S:\fyp\GoalPilot_AI_Completed
Remove-Item Env:PYTHONPATH
& $py -m pytest -q
```

```
........................................................................ [ 41%]
........................................................................ [ 82%]
..............................                                           [100%]
174 passed in 599.33s (0:09:59)
```

174 = the 164 tests verified before this pass + the 10 new `tests/test_goalpilot_explain.py`.
With the LP suite (26), the project now has **200 tests, 0 failures, 0 errors, 0 skips**, and the
archived 100 × 5 × 142 parity check is among them. Console:
`outputs/evaluation/pytest_final_after_phaseI_20261011.txt`.
