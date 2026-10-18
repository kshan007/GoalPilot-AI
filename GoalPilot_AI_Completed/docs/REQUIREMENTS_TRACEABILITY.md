# Requirements traceability matrix — GoalPilot AI

**Last updated:** 2026-10-11
**Scope:** `S:\fyp\GoalPilot_AI_Completed` (working copy) plus the companion application
`S:\fyp\GoalPilot_Application`. Originals (`S:\fyp\GoalPilot_AI`, `S:\fyp\GoalPilot_RL_PreCheck.ipynb`)
are untouched.

**How to read this.** Every row maps a requirement of the final-year-project brief to the file
that implements it, the artefact that evidences it, and its true status. A feature is *Verified*
only where a command was executed in this environment and its output is on disk. Where a
capability exists in code but has not been exercised end-to-end, the status says so.

Status vocabulary

| status | meaning |
|---|---|
| **Verified** | implemented and exercised; artefact on disk from a real run |
| **Implemented** | code exists and is covered by tests, but the specific end-to-end artefact was not re-run in this pass |
| **Diagnosed** | measured and documented; the underlying behaviour was deliberately not changed |
| **Partial** | some part of the requirement is met; the gap is stated |
| **Not applicable** | the requirement does not fit this project's actual scope |

---

## 1. Phase A — Repository and requirements audit

| # | Requirement | Implementation | Evidence | Status |
|---|---|---|---|---|
| A1 | Inventory implemented / partial / missing / broken / duplicated / obsolete | `audit_tools/00_env_check.py`, `01_notebook_compare.py`, `02_inventory.py`, `03_extract_nb.py` | `docs/audit/AUDIT_REPORT.md` §1 (552 files, 4,800.2 MB, 147 duplicate groups, 3,128.03 MB redundant) | Verified |
| A2 | Identify authoritative files and datasets | `goalpilot_paths.py` (single root resolver) | `docs/audit/AUDIT_REPORT.md` §1.2–1.3 | Verified |
| A3 | Which config/env produced each historical result | `goalpilot_config.py` presets; per-artefact `*_config_*.json` | `outputs/evaluation/policy_config_*.json` (9 files) | Verified |
| A4 | Which checkpoints load with which obs/action spaces | `tests/test_goalpilot_config_paths.py`, `tests/test_goalpilot_env_lifecycle.py` | `docs/audit/AUDIT_REPORT.md` §2; `docs/EXECUTION.md` §3 | Verified |
| A5 | Which tests exist and what they protect | `tests/` (15 files) | `outputs/evaluation/pytest_baseline_recheck_20261011.txt` | Verified |
| A6 | Necessary dependencies / data files | `README.md` §2 | `docs/EXECUTION.md` §0 | Verified |
| A7 | Notebooks duplicating importable code | `audit_tools/01_notebook_compare.py`; `audit_tools/20_make_portable_notebook.py` | `GoalPilot_RL_PreCheck_portable.ipynb` (114 cells path-patched, 14 disabled) | Verified |
| A8 | Features existing only in documentation | this matrix | rows marked Partial / Diagnosed | Verified |
| A9 | Requirements traceability matrix | this file | — | Verified |
| A10 | Version-1 phase report | `outputs/evaluation/final_validation_v1/PHASE_A_FINDINGS.md` | — | Verified |

## 2. Phase B — Financial data and simulation integrity

| # | Requirement | Implementation | Evidence | Status |
|---|---|---|---|---|
| B1 | Validate HCES 2023–24 expenditure use | `simulation/02_synthetic_population/*`; `generate_multigoal_dataset.py` | `GoalPilot_MultiGoal_Extension/docs/synthetic_multigoal_validation_report_2026-10-10.md` | Implemented |
| B2 | Validate RBI CPI use | `simulation/01_input_data/cpi_historical_calibration.csv` | `simulation/07_validation/simulation_methodology_validation.csv` | Implemented |
| B3 | Validate RBI WALR use, no future leakage | `simulation/01_input_data/walr_scaled.csv`; `rl_market_credit_validated.csv` | `optimization/lp_inputs/nifty_walr_reconstruction_audit.csv` | Implemented |
| B4 | Validate NIFTY 50 use | `simulation/01_input_data/market_scaled.csv` | identity `A4` in the large-CSV validation below | Verified |
| B5 | Provenance, units, ranges, duplicates, transformations | `audit_tools/70_large_csv_validation.py` | `outputs/audit/large_csv_validation_v1/large_csv_validation_report.md` | **Verified** |
| B6 | Cash-flow identities tested (surplus, balances, EMI, interest, net worth) | `tests/test_goalpilot_env_ledger_integrity.py`, `test_goalpilot_env_accounting.py`, `test_goalpilot_constrained_lp.py` | `outputs/evaluation/pytest_baseline_recheck_20261011.txt` (164 passed) | Verified |
| B7 | Goal progress distinguished from owned assets; no double counting | `goalpilot_env.earmarked_goal_funding` vs `net_worth`; finding F-04 | `outputs/plots/03_net_worth_double_count.png`; `tests/test_goalpilot_env_ledger_integrity.py` | Verified |
| B8 | Reproducible data-validation reports; originals preserved | `audit_tools/70_*`, `71_*` | `outputs/audit/large_csv_validation_v1/` | **Verified** |
| B9 | Large 959 MB / 169 MB outputs content-validated (was finding F-14) | `audit_tools/70_large_csv_validation.py` | 1,430,000 rows × 2 files, 10,000 users; see §1 below | **Verified** |

### B-§1 — Large-CSV validation results (this pass)

Both files: 1,430,000 data rows, 10,000 users, no duplicate `(user_id, period)`, no nulls, no
non-numeric cells, zero period-order violations, range 2015-02-01 … 2026-12-01.

| identity | comparisons | failures |
|---|---:|---:|
| `portfolio_value[t] == prev × (1+return[t])` | 1,430,000 | **0** |
| `portfolio_return == market_exposure × nifty_monthly_return` | 1,430,000 | **0** |
| `market_exposure == risk_score` | 1,430,000 | **0** |
| `monthly_surplus == income − expenditure` | 1,430,000 | **0** |
| `monthly_surplus == income − expenditure − emi` | 1,430,000 | 601,744 |
| same key sequence across the two files | 1,430,000 | **0** |
| `portfolio_return` / `portfolio_value` agree across files | 1,430,000 | **0** |

**Finding B-1 (documentation precision).** In the full-population output the column named
`monthly_surplus` equals `income − expenditure`; the EMI is *not* netted out (it is a separate
column). It therefore fails the naive `income − expenditure − emi` identity on exactly the
601,744 rows (42.08 %) that carry an EMI, and passes on every row without one. This is a
**naming/clarity issue**, not corruption: the alternative identity holds exactly (max deviation
9.5e-11). The RL environment, by contrast, computes surplus *net* of EMI. Anyone joining the two
must be aware of the differing convention.

## 3. Phase C — Investment-capacity gate (before training)

| # | Requirement | Implementation | Evidence | Status |
|---|---|---|---|---|
| C1 | How `investment_capacity_ratio` is generated / interpreted / applied | `goalpilot_env._allocate`; `goalpilot_constrained_lp.capacity_ratio_for` | `outputs/reward_design/v7/CONSTRAINED_LP_BENCHMARK.md` §1; `docs/audit/AUDIT_REPORT.md` §1.3 | Verified |
| C2 | Trace interaction with surplus, reserves, EMIs, caps, action encoding | `goalpilot_env.py`; `tests/test_goalpilot_env_action_mix.py` | `outputs/reward_design/v4/R12_ACTION_SPACE_DESIGN.md` | Verified |
| C3 | Versioned sensitivity analysis of capacity assumptions | `audit_tools/56_constrained_lp_comparison.py` | `outputs/evaluation/final_validation_v7/constrained_lp_*.csv` | Verified |
| C4 | Requested vs permitted vs executed investment reported | same | `outputs/evaluation/final_validation_v7/constrained_lp_plan_vs_executed_v1.csv` | Verified |
| C5 | Production default unchanged | `goalpilot_config.py` presets opt-in | `tests/test_goalpilot_env_parity.py` (archived parity) | Verified |
| C6 | Capacity is an affordability ceiling, not validated risk suitability | documented in `goalpilot_explain.build_facts` and §C of the methodology | this doc + `docs/EXPLAINABILITY.md` | **Verified** |

## 4. Phase D — LP optimizer

| # | Requirement | Implementation | Evidence | Status |
|---|---|---|---|---|
| D1 | Existing LP retained, not rewritten | `GoalPilot_MultiGoal_Extension/src/multi_goal_optimizer.py` (unchanged) | 26 LP tests pass | Verified |
| D2 | Explicit documented formulation (variables, objective, constraints) | `optimization/lp_inputs/lp_5r_formal_lp_specification.csv`, `lp_constraint_mapping_audit.csv` | `docs/final/ARCHITECTURE_AND_METHODOLOGY.md` §4 | Verified |
| D3 | Optimizer must not rely on the environment relabelling infeasible investment | capacity-constrained LP `goalpilot_constrained_lp.py` | `CONSTRAINED_LP_BENCHMARK.md` §2.4 (overflow 10,130.92 → 0.000058 per month) | Verified |
| D4 | Solution executable by the simulator; report solver status/residuals/gaps | `audit_tools/56_constrained_lp_comparison.py` | `constrained_lp_detail_v1.csv`; `tests/test_goalpilot_constrained_lp.py` (11) | Verified |
| D5 | Compare original vs constrained LP without overwriting history | versioned outputs `final_validation_v6`, `v7` | `CONSTRAINED_LP_BENCHMARK.md` §4.3 | Verified |
| D6 | Label unsupported constraints as assumptions | `CONSTRAINED_LP_BENCHMARK.md` §1.3, §6 | same | Verified |

## 5. Phase E — RL environment and decision policy

| # | Requirement | Implementation | Evidence | Status |
|---|---|---|---|---|
| E1 | Observation contains the needed financial variables | `goalpilot_env._get_observation` (42-dim) | `docs/audit/AUDIT_REPORT.md` §1.3 | Verified |
| E2 | No future returns / outcomes exposed to the policy | `goalpilot_env.py`; `tests/test_goalpilot_env_semantics.py` | 164-test suite | Verified |
| E3 | Action space meaningful; `share` / `mix` / LP encoder validated | `goalpilot_config.ACTION_MODES`; `goalpilot_lp_encoder.py` | `outputs/reward_design/v4/R12_ACTION_SPACE_DESIGN.md`, `v5/LP_ENCODING_AND_OVERFLOW_POLICY.md`; `tests/test_goalpilot_lp_encoder.py` | Verified |
| E4 | Transitions: cash flow, market, goal progression, inflation, loans, reserve, net worth, termination | `goalpilot_env.step` | `tests/test_goalpilot_env_accounting.py`, `_lifecycle.py`, `_ledger_integrity.py` | Verified |
| E5 | Gymnasium compliance, deterministic seeding, reproducible resets | `check_env` in `audit_tools/32_ppo_smoke_test.py` | `outputs/evaluation/final_validation_v1/ppo_smoke_test.json` | Verified |
| E6 | Reward components audited for scale/sign/meaning | `evaluation/reward_decomposition.py` | `outputs/evaluation/reward_decomposition_summary_*.csv`; `AUDIT_REPORT.md` F-03/F-07 | Diagnosed |
| E7 | Reward not changed to improve metrics; candidates separate | `goalpilot_config.reward_version` (archived_v1 / candidate_a / candidate_b) | `outputs/reward_design/v1/REWARD_EXPERIMENT_REPORT.md` | Verified |

## 6. Phase F — Multi-goal planning logic

| # | Requirement | Implementation | Evidence | Status |
|---|---|---|---|---|
| F1 | Multiple goals, amounts, priorities, deadlines | `goalpilot_env.user_goals`; `goalpilot_config.n_goal_slots` | 100 users, 390 goals (3–5 each, mean 3.9) | Verified |
| F2 | Distinguish fully-funded / shortfall / structurally infeasible | `goalpilot_explain._explain_shortfalls`; feasibility cohort in evaluators | `docs/EXPLAINABILITY.md`; `CONSTRAINED_LP_BENCHMARK.md` §3 | **Verified** |
| F3 | No invented money; no automatic borrowing to fake achievability | `tests/test_goalpilot_env_ledger_integrity.py`; borrowing audit | `outputs/evaluation/borrowing_audit_*.csv` | Verified |
| F4 | Explain trade-offs among priority, deadline, contribution, affordability | `goalpilot_explain._why_others_less` | `tests/test_goalpilot_explain.py` | **Verified (new)** |

## 7. Phase G — Fair evaluation framework

| # | Requirement | Implementation | Evidence | Status |
|---|---|---|---|---|
| G1 | Compare baseline / savings / investment / LP / constrained LP / PPO | `evaluation/fair_comparison_harness_v2.py`, `audit_tools/80_ppo_training_v8.py` | `outputs/evaluation/final_validation_v3/`, `…_v7/`, `…_v8/` | Verified |
| G2 | No privileged strategies in the main comparison | harness uses only deployable actions | `HARNESS_NOTES` in `fair_comparison_harness_v2.py` docstring | Verified |
| G3 | Identical users, goals, scenarios, initial conditions | `tests/test_lp_rl_target_parity.py` | `outputs/evaluation/final_validation_v1/` | Verified |
| G4 | Report achievement, fully-funded, deadline, shortfall, allocations, capacity, debt, net worth, cohorts, seeds, CIs | `80_ppo_training_v8.py` summary/paired CSVs | `outputs/evaluation/final_validation_v8/` | **Verified (new)** |
| G5 | Held-out cohort not used to tune | `fresh_split_v1` manifest | `training_logs/experiments/fresh_split_v1/fresh_split_v1_manifest.json` | Verified |
| G6 | Do not compare raw reward across versions; do not claim RL superiority without evidence | `REWARD_EXPERIMENT_REPORT.md`, `FRESH_SPLIT_CONFIRMATION.md` | same | Verified |

## 8. Phase H — Train and select the final RL policy

| # | Requirement | Implementation | Evidence | Status |
|---|---|---|---|---|
| H1 | Smoke test before substantial training | `audit_tools/32_ppo_smoke_test.py` | `…/final_validation_v1/ppo_smoke_test.json` | Verified |
| H2 | Explicit config + reward version, multiple seeds, reproducible logs, checkpoints | `audit_tools/80_ppo_training_v8.py` | `training_logs/experiments/ppo_recommended_v1/` | **Verified (new)** |
| H3 | Validation-based checkpoint selection | `EvalCallback` on the 16 validation users | `…/seed*/best/best_model.zip`, `…/seed*/eval/evaluations.npz` | **Verified (new)** |
| H4 | Held-out final evaluation + comparison to non-RL baselines and constrained LP | `80_ppo_training_v8.py` (eval stage) | `outputs/evaluation/final_validation_v8/ppo_v8_*.csv` | **Verified (new)** |
| H5 | Training duration, timesteps, hardware, config recorded | per-run `run_*.json` | same | **Verified (new)** |
| H6 | Keep best historical checkpoint and prior experiments intact | archived checkpoints untouched | `simulation/05_simulation_runs/rl_prototype/models/` | Verified |

## 9. Phase I — Financial knowledge and explainability

| # | Requirement | Implementation | Evidence | Status |
|---|---|---|---|---|
| I1 | Inspect existing NISM KB / retrieval / recommendation modules | repository-wide search | `docs/EXPLAINABILITY.md` §1 — **none found** | Verified |
| I2 | Educational explanations + rule-based guidance, clearly distinguished | `goalpilot_knowledge.py`, `goalpilot_explain.py` | `docs/EXPLAINABILITY.md` §3 | **Verified (new)** |
| I3 | Every recommendation explainable (goals, why funded, reasons, shortfalls, roles, sensitivity) | `goalpilot_explain.explain` (7 sections) | `tests/test_goalpilot_explain.py` (10) | **Verified (new)** |
| I4 | No fabricated sources; no return promises | `goalpilot_knowledge.UNCITED` status; test banning guarantee language | same tests | **Verified (new)** |
| I5 | Retrieval grounded; missing evidence acknowledged | `KnowledgeBase.retrieve` returns `[]` for unknown queries | `test_retrieval_unknown_query_is_empty_not_a_guess` | **Verified (new)** |

## 10. Phase J — Application integration

| # | Requirement | Implementation | Evidence | Status |
|---|---|---|---|---|
| J1 | Inspect actual frontend/backend/API/DB/auth before deciding | `GoalPilot_Application/` (FastAPI + Vite/React) | `docs/APPLICATION.md` §1 | Verified |
| J2 | Reuse working components; no second backend | single backend reused | same | Verified |
| J3 | Profile entry/validation, goal creation, capacity/feasibility, LP execution, allocations, comparison, disclosures | `backend/app/` (health, optimize, derive-profile, benchmarks) | `docs/APPLICATION.md` §2–3 | Verified |
| J4 | Frontend/API/optimizer/simulator agree on units and schemas | Pydantic v2 contracts | `backend/tests/` (15 passed) + live E2E | Verified |
| J5 | No hard-coded secrets; env-var setup documented | `backend/.env.example` | `docs/APPLICATION.md` §4 | Verified |
| J6 | Multi-goal + RL in the app | not implemented in the app (single-goal LP only) | out of the app's v1 scope; declared in the UI | **Not applicable (documented gap)** |
| J7 | Honest attribution of educational content | `nism_guidance_notes` relabelled from "NISM Guidance" to general principles + disclaimer | `docs/APPLICATION.md` §5 | **Verified (new, corrected)** |

## 11. Phase K — Testing and regression protection

| # | Requirement | Implementation | Evidence | Status |
|---|---|---|---|---|
| K1 | Run the full suite before and after; verify the reported baseline | — | before: `outputs/evaluation/pytest_baseline_recheck_20261011.txt` (164 passed); after: `outputs/evaluation/pytest_final_after_phaseI_20261011.txt` (**174 passed in 599.33s**) | **Verified** |
| K2 | Preserve the archived 100×5×142 parity check at 1e-12 | `tests/test_goalpilot_env_parity.py` | part of the 164 | Verified |
| K3 | Add tests for identities, loans, funding, inflation, capacity, LP parity, action encode/decode, obs/action compatibility, termination/reset, no leakage, reward correctness, save/load, boundaries | `tests/` (15 files) | 164 RL + 26 LP = 190 | Verified |
| K4 | Never weaken tests to go green | reviewed; `CONSTRAINED_LP_BENCHMARK.md` §2.5 records a corrected over-claim; this pass's mask-inversion bug was fixed in the validator rather than by relaxing the check | same | Verified |

**Totals:** 174 RL + 26 LP = **200 tests, 0 failures, 0 errors, 0 skips**.

## 12. Phase L — Reproducibility, deployment, documentation

| # | Requirement | Implementation | Evidence | Status |
|---|---|---|---|---|
| L1 | README with architecture | `README.md` (refreshed this pass) | — | Verified |
| L2 | Setup + dependency instructions | `README.md` §2 | — | Verified |
| L3 | Dataset provenance / preparation | `GoalPilot_MultiGoal_Extension/docs/free_data_sources.md` | — | Implemented |
| L4 | Env/config documentation | `goalpilot_config.py` docstrings; `docs/final/ARCHITECTURE_AND_METHODOLOGY.md` | — | Verified |
| L5 | LP formulation documented | `docs/final/ARCHITECTURE_AND_METHODOLOGY.md` §4 | — | Verified |
| L6 | RL state/action/reward/training documented | same §5 | — | Verified |
| L7 | Financial assumptions + limitations | `docs/final/DEFENCE_PACK.md` §1 | — | Verified |
| L8 | Evaluation methodology and results | `docs/final/EVALUATION_AND_RESULTS.md` | — | Verified |
| L9 | Test commands + expected outcomes | `README.md` §7 | — | Verified |
| L10 | Checkpoint + inference instructions | `README.md` §5, `docs/APPLICATION.md` | — | Verified |
| L11 | Application startup instructions | `docs/APPLICATION.md` §4 | live E2E | Verified |
| L12 | `.env` example without secrets | `backend/.env.example` | — | Verified |
| L13 | Containerisation | not required for the research system; app is a plain FastAPI/Vite app | deliberately not added | Not applicable |

## 13. Phase M — FYP deliverables

| # | Requirement | File | Status |
|---|---|---|---|
| M1 | Final architecture diagram | `docs/final/ARCHITECTURE_AND_METHODOLOGY.md` §1 + `docs/final/architecture.svg` | Verified |
| M2 | Data & preprocessing flow diagram | same §2 | Verified |
| M3 | Financial simulation methodology | same §3 | Verified |
| M4 | LP objective and constraints | same §4 | Verified |
| M5 | RL environment and learning methodology | same §5 | Verified |
| M6 | Evaluation methodology and quantitative results | `docs/final/EVALUATION_AND_RESULTS.md` | Verified |
| M7 | Ablation / sensitivity analysis | `EVALUATION_AND_RESULTS.md` §5; `docs/EXPLAINABILITY.md` §4 | Verified |
| M8 | Limitations and assumptions | `docs/final/DEFENCE_PACK.md` §1 | Verified |
| M9 | Baseline / LP / constrained LP / RL comparison | `EVALUATION_AND_RESULTS.md` §4 | Verified |
| M10 | Reproducible end-to-end demo procedure | `docs/final/DEFENCE_PACK.md` §3 | Verified |
| M11 | Example feasible / partial / infeasible scenarios | `DEFENCE_PACK.md` §4 | Verified |
| M12 | Final report outline linked to real outputs | `DEFENCE_PACK.md` §5 | Verified |
| M13 | Panel questions with accurate answers | `DEFENCE_PACK.md` §6 | Verified |
| M14 | Separation of completed / experimental / future work | `DEFENCE_PACK.md` §2 | Verified |

---

## Outstanding issues (honest list)

1. **Reward function unchanged.** F-03 (risk penalty dominates, no terminal-value offset) and
   F-07 (component scaling) remain diagnosed, not fixed. Candidates exist and are opt-in; the
   archived reward is untouched.
2. **No reward version selected.** v3's fresh-split paired difference between `candidate_a` and
   `archived_v1` was +0.0069 (CI [−0.0268, +0.0444], p = 0.72) — not significant. The v8 held-out
   evaluation points the same way: `candidate_a` achieves 0.4398 vs `archived_v1` 0.4842, i.e.
   no evidence that the candidate reward is better.
3. **`legacy` overflow policy remains the default**; `retain_as_cash` / `redirect_to_savings` are
   opt-in and not adopted.
4. **`residual_carried` branch (R-01b)** is covered by an assertion but never exercised by the
   real data.
5. **The application is single-goal LP only.** Multi-goal planning and RL inference exist in the
   research system, not in the web app.
6. **Google Colab was never executed** from this host; Colab readiness is structural only.
7. **`monthly_surplus` naming** in the full-population CSV excludes EMI (finding B-1).
