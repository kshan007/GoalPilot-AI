t 800

# GoalPilot AI — Multi-Goal LP Extension Prototype

## Status

This is a tested, standalone prototype built after inspecting the uploaded optimization and simulation archives. It does not overwrite the original notebooks or archive contents. It is an extension foundation, not yet a fully integrated production financial planner.

## What the existing project contains

- Simulation archive: 28 entries; synthetic user financial profiles, market/credit scenarios, CPI/WALR calibration, economic environment, monthly simulation output, goal outcomes, and validation reports.
- Optimization archive: 73 entries; LP audit CSVs, solver outputs, user-level/monthly results, validation, and final summary/documentation.
- Separately attached notebooks: a 163-cell simulation notebook and a 40-cell optimization notebook.
- The supplied simulation validation report states 10,000 synthetic users, 143 monthly records per user, and 64.51% historical simulated goal success. These are results from the supplied synthetic simulation, not observed real-world client outcomes.

## Existing single-goal LP (verified from supplied documentation)

The existing documented formulation uses monthly goal funding variables `G_(u,t)` and shortfall `D_u`; it minimizes total goal shortfall subject to nonnegative contributions, monthly positive-cash-flow upper bounds, and target accounting. The supplied documentation reports 10,000 users, 626,970 contribution variables, 10,000 shortfall variables, and 7,582 optimized successes versus 6,451 historical successes (75.82% vs 64.51%). These are the archive's reported outcomes; this standalone run did not reproduce the full 10,000-user solve.

The existing LP documentation explicitly excludes monthly investment-contribution variables, borrowing/WALR decisions, future Nifty-return decisions, and a minimum emergency-reserve constraint. The extension therefore implements those as a separate prototype rather than claiming they already existed.

## Synthetic multi-goal dataset (new)

A reproducible generator now creates a multi-goal input for all 10,000 simulated financial profiles. The dataset contains 39,932 goal rows (3–5 goals per user): one legacy simulated goal plus 2–4 generated goals per user across eight goal categories. Generated goals are synthetic assumptions, not real or user-reported facts. See `docs/synthetic_multigoal_validation_report_2026-10-10.md`.

The LP was run for the first 1,000 users: all 1,000 solved optimally, producing 4,031 goal allocation rows. This is a sample validation, not a full 10,000-user optimization run. Reproduce with `python generate_multigoal_dataset.py --max-users 1000`; use `--generate-only` to regenerate the full dataset without solving LPs.

## Files

- `src/multi_goal_optimizer.py`: goal preparation, validation, LP formulation, EMI/FV helpers, and strategy comparison.
- `src/simulation_adapter.py`: maps the current simulation financial-profile schema into the optimizer input model. Risk-profile mapping is an explicit proxy, not financial advice.
- `run_simulation_integration_smoke.py`: runs a one-user integration smoke test using the simulation ZIP financial profile and synthetic three-goal sample.
- `generate_multigoal_dataset.py`: seeded generator for the full 10,000-user / 39,932-goal dataset, plus sample LP optimization runner.
- `data/synthetic_multigoal_input.csv`: generated multi-goal input dataset.
- `data/multigoal_financial_profiles.csv`: financial profiles copied from the supplied synthetic simulation input.
- `outputs/synthetic_multigoal_optimization_*_sample1000.*`: allocation and summary results for 1,000-user LP run.
- `run_demo.py`: reproducible synthetic 3-goal demonstration and output generation.
- `data/sample_financial_state.json`: clearly labelled synthetic profile.
- `data/sample_goals.csv`: three illustrative goals.
- `outputs/derived_goals.csv`: derived inflation-adjusted costs, funding gaps, priority scores, and monthly contribution baselines.
- `outputs/multi_goal_allocations.csv`: goal-wise allocation results.
- `outputs/optimization_summary.json`: solver status, constraints, and assumptions.
- `outputs/strategy_comparison.csv`: savings-only, savings+investment, and loan-enabled strategy runs.
- `outputs/economic_scenario_comparison.csv`: baseline and parameter sensitivity scenarios.
- `tests/test_optimizer.py`: automated validation tests.
- `docs/*_archive_inventory.csv`: file inventories for the supplied ZIP archives.
- `data/`: selected compact CSV inputs/results copied from the archives for traceability. The huge monthly simulation CSV was not duplicated into this deliverable.

## Run locally

Python 3.10+ recommended.

```bash
python -m pip install pandas scipy pytest
python run_demo.py
python -m pytest -q
```

## Formulation summary

For each goal, the LP uses continuous decision variables for:

- initial liquid savings allocated;
- monthly savings contributions;
- monthly investment contributions;
- loan principal;
- remaining shortfall.

The goal accounting equation links these to the future funding gap. Available liquid savings are capped at liquid savings minus the emergency reserve and goal funding already earmarked (assuming that earmarked funding is included in reported liquid savings). Monthly savings plus investment contributions are capped by monthly surplus. Total new loan EMI is capped by the configured EMI affordability limit after existing EMI. Loan principal is bounded per goal. An investment option is disabled when its configured risk score exceeds the supplied risk-capacity score. Objective penalties are documented in source and configurable.

## Important limitations before production use

1. The simulation archive contains one synthetic goal record per user in the final goal outcome dataset; it does not supply a true multi-goal dataset. The three-goal example is explicitly synthetic.
2. The LP uses a static shared monthly-surplus cap across all goals. It is conservative but does not yet model a month-by-month cash-flow schedule where contributions to a completed goal can be reallocated later.
3. Investment return and risk are scenario inputs, not forecasts, recommendations, or guarantees. This prototype uses one investment candidate, not a product-level candidate universe or covariance-based portfolio risk model.
4. Loan rates, maximum loan amounts, EMI ratio, inflation, and returns must be calibrated/verified for each deployment. A 30–35% EMI ratio is a configurable educational thumb rule, not universal advice.
5. The current LP has no dedicated objective term for illiquidity/maturity or tax, fees, default risk, insurance, or loan eligibility underwriting. These need to be added with data and explicit assumptions before user-facing deployment.
6. The supplied notebooks use Google Drive paths under `/content/drive/MyDrive/GoalPilot_AI`; those paths were not available in this execution environment. The existing notebook was inspected but the full original 10,000-user notebook pipeline was not rerun end-to-end.
7. The prototype's weighted achievement is calculated from projected funding relative to each goal's funding gap. It is not a probability of success.

## Validation performed

- The demo LP solved with HiGHS.
- Automated tests: 12 passed, including simulation-adapter checks, earmarked-funding regression, and emergency-reserve reporting semantics.
- Simulation integration smoke test: one financial profile row from the uploaded simulation archive plus three synthetic sample goals; solver status `optimal`. See `docs/validation_report_2026-10-10.md`.
- Tests cover goal derivation, multiple-goal solving, monthly-surplus/EMI/emergency-fund checks, risk gating, duplicate identifiers, negative values, and shortfall when there is no surplus.
- Passing these tests validates the prototype's tested behaviors only; it does not certify production readiness or the full original simulation pipeline.
