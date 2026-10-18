# Modification Log — GoalPilot AI

**Date:** 2026-10-10
**Working copy:** `S:\fyp\GoalPilot_AI_Completed`
**Originals:** `S:\fyp\GoalPilot_AI` and `S:\fyp\GoalPilot_RL_PreCheck.ipynb` — **not modified**

Every change below is recorded with its reason, the audit finding it addresses, the backup
that preserves the previous state, and the test that pins the new behaviour.

Rule applied throughout: **no archived behaviour was removed, only made optional.**
`GoalPilotConfig.archived()` reproduces the 2026-10-10 environment exactly, and
`evaluation/verify_against_archive.py` proves it against the archived CSVs.

---

## 1. Modified files

### 1.1 `simulation/05_simulation_runs/rl_prototype/goalpilot_env.py`

| | |
|---|---|
| **Backup** | `goalpilot_env.py.orig_20261010` (byte-identical to the original; SHA-256 `FDFE6D9D…4A9FEFD`) |
| **Also archived as** | `archive/goalpilot_env_archived_20261010.py` (importable copy used by the parity tests) |
| **Lines before / after** | 457 → ~740 |
| **Behaviour** | Unchanged by default *except* `accounting_mode`, which now defaults to `"ledger"` |

| # | Change | Finding | Why | Pinned by |
|---|---|---|---|---|
| 1 | `__init__` accepts a `config: GoalPilotConfig`; `seed` still accepted for compatibility | F-06, F-12 | One place to control every assumption | `test_goalpilot_config_paths.py` |
| 2 | **Ledger accounting** (`accounting_mode="ledger"`, default): cash moves by `surplus − actual_payment − invest_total + new_loan`; loan proceeds credit `cash`; EMI payments debit `cash`; `goal_balances` is documented as a **memo** account | **F-04, F-05** | The archive kept a contribution accumulator in `cash` while `goal_balances` held the same money, and never recorded loan proceeds or payments. Net worth was meaningless | `test_goalpilot_env_accounting.py::test_ledger_net_worth_change_equals_expected`, `…::test_loan_proceeds_and_repayment_are_balanced` |
| 3 | Legacy behaviour preserved on request: `accounting_mode="legacy"` (used by `GoalPilotConfig.archived()`) | — | Archived results must stay reproducible | `test_goalpilot_env_parity.py` (100 users × 5 policies × 142 months, exact) |
| 4 | `action_mode="share"` normalises the action to shares and always allocates the full budget; investment capacity is honoured **including when it is zero**; an all-zero action remains a true no-op | **F-02** | `budget_scale = min(1, budget/total)` never scaled *up*, so any policy emitting below the saturation point silently underfunded goals, while *above* it the reward was flat (no gradient). Baselines emitting exactly 1.0 always captured the whole budget; PPO could not learn to | `test_goalpilot_env_modes.py::test_share_mode_makes_action_magnitude_irrelevant`, `…::test_share_mode_never_exceeds_the_budget` |
| 5 | `goal_credit_mode="growth_weighted"` compounds savings and investment contributions at their own rates to the goal deadline | **F-01** | A rupee was credited at face value whichever vehicle carried it, so savings-only and mixed-allocation produced *identical* goal funding by construction | `test_goalpilot_env_modes.py::test_growth_weighted_crediting_breaks_the_degeneracy` |
| 6 | `target_basis="inflated"` applies `(1+inflation)^(months/12)` to goal targets | **F-06** | The LP used inflated targets while the environment used nominal costs, and the two were compared | `test_lp_rl_target_parity.py::test_lp_inflates_and_rl_can_match_it` |
| 7 | `n_goal_slots` pins the action/observation shape independently of the user subset | latent fragility found while testing | `max_goals` was inferred from whichever subset was passed, so an 80-user train env and a 20-user eval env could disagree on the space shape | `test_goalpilot_env_lifecycle.py::test_n_goal_slots_pins_the_space_across_subsets` |
| 8 | New audit surface on `info`: `reward_components`, `budget_audit`, `ledger`, `net_worth`, `unallocated_surplus`, `interest_paid`, `investment_gain`, `cash`. All archived keys retained | **F-07** | The reward had never been decomposed, so no one knew which term dominated | `test_goalpilot_env_lifecycle.py::test_reward_components_sum_to_reward` |
| 9 | **The reward function is byte-for-byte unchanged.** No term was added, removed or rescaled | — | The task required diagnostics before any reward change | `test_goalpilot_env_parity.py` reward equality to 1e-12 |

**Deliberately NOT changed:** the reward weights, the PPO hyper-parameters, the LP optimizer,
the datasets, and both model checkpoints.

---

## 2. New files

### 2.1 Configuration and paths

| File | Purpose | Finding |
|---|---|---|
| `goalpilot_config.py` *(in `…/rl_prototype/`)* | `GoalPilotConfig` — every assumption in one dataclass, with `archived()`, `corrected_accounting()`, `lp_parity()` and `recommended()` presets | F-06 |
| `goalpilot_paths.py` | Environment-agnostic project-root resolution: env var → walk up → one level down → Colab. Validates that the resolved root really is a project root | F-12 |
| `pytest.ini` | `pythonpath` + `testpaths` so `python -m pytest` works with no environment setup | F-09 |

### 2.2 Evaluation (`evaluation/`)

| File | Purpose | Finding |
|---|---|---|
| `policy_evaluation.py` | The **single** evaluation loop. Reports `net_worth_ledger` and `net_worth_archived_aggregate` side by side, and a budget metric that does **not** double count | F-08, F-11 |
| `verify_against_archive.py` | Compares the new evaluator against the four archived CSVs field by field; fails loudly on any mismatch | verification |
| `reward_decomposition.py` | Per-month, per-component reward breakdown by policy | F-07 |
| `borrowing_audit.py` | Attributes every rupee of borrowing: principal, interest, funding delta, net-worth delta, cost per extra funded rupee, per-user verdict. Also asserts borrowing alone does not create net worth | F-05, F-07 |
| `make_plots.py` | Six PNG figures into `outputs/plots/` | reporting |
| `run_all.py` | One command reproduces every artefact in order | reproducibility |

The ad-hoc evaluation loops were **consolidated** here; the notebook cells that contained
them are preserved as the record.

### 2.3 Tests (`tests/`) — 64 tests, all passing

| File | Tests | Covers |
|---|---:|---|
| `conftest.py` | — | fixtures: archived-env loader, RL data, 6-user slice |
| `test_goalpilot_env_parity.py` | 3 | **Archived parity**: 100 users × 5 policies × 142 months, reward and state to 1e-12 |
| `test_goalpilot_env_accounting.py` | 7 | F-04, F-05: budget identity, net-worth identity, episode reconciliation, double-count demonstration, loan balance |
| `test_goalpilot_env_modes.py` | 8 | F-01, F-02, F-06: saturation plateau, share mode, degeneracy on the record, growth-weighted fix, inflated targets |
| `test_goalpilot_env_lifecycle.py` | 18 | F-09, F-13: `check_env`, spaces, determinism, reward decomposition, invariants, PPO checkpoint load + rollout |
| `test_goalpilot_config_paths.py` | 24 | config validation, presets, path resolution |
| `test_lp_rl_target_parity.py` | 4 | F-06: LP and RL target parity, LP still solves |
| **New tests subtotal** | **64** | run with `python -m pytest` from the project root |
| **Extant LP suite** (`GoalPilot_MultiGoal_Extension/tests/`) | 26 | unchanged, still passing; run with `python -m pytest` from that folder |

Before this work the RL environment had **zero** tests (F-09).

### 2.4 Notebook

| File | Change |
|---|---|
| `GoalPilot_RL_PreCheck_portable.ipynb` | **New.** Derived from the archived notebook. 114 cells had Colab path literals rewritten to `GOALPILOT_ROOT`; the 14 cells that rewrote `goalpilot_env.py` in place are disabled and preserved as commented source; a bootstrap cell resolves the project root for both local and Colab use. All 144 original cells and their outputs are retained |
| `Copy of GoalPilot_RL_PreCheck.ipynb` | **Unchanged** |

### 2.5 Documentation and audit tooling

| File | Purpose |
|---|---|
| `docs/audit/AUDIT_REPORT.md` | Full audit: inventory, notebook comparison, environment probe, 15 findings with evidence, prioritised plan |
| `docs/MODIFICATION_LOG.md` | This file |
| `docs/EXECUTION.md` | What was actually run, with raw output |
| `docs/FYP_DEMO_GUIDE.md` | Scripted demonstration |
| `README.md` | How to run locally and in Colab |
| `audit_tools/` | The scripts that produced the audit evidence, re-runnable |

### 2.6 Generated outputs (not hand-written)

```
outputs/evaluation/   policy_detail_*.csv, policy_summary_*.csv, reward_decomposition_*.csv,
                      borrowing_audit_*.csv, action_mode_comparison.csv,
                      archive_verification.json, *_config_*.json, run_all_console.txt
outputs/plots/        01…06 *.png
```

---

## 3. Files explicitly preserved unchanged

| Path | Reason |
|---|---|
| `simulation/05_simulation_runs/rl_prototype/models/**` | Model checkpoints |
| `…/training_logs/**` | Original training logs |
| `…/rl_*.csv` (all archived result CSVs) | Baseline evidence for verification |
| `…/goalpilot_env.py.pre_*.bak` (9 files) | Patch history |
| `GoalPilot_MultiGoal_Extension/**` | The working LP optimizer, its 26 tests, data and docs |
| `optimization/**`, `simulation/01…04_*`, `simulation/06_results`, `simulation/07_validation` | Datasets and results |
| `datasets/**` (in the workspace) | Upstream datasets |

---

## 4. Known limitations carried forward

1. **The reward function is still the archived one.** F-03 (the risk penalty dominates and
   has no offsetting terminal-value term) and F-07 are *diagnosed and quantified* but not
   fixed. Fixing them requires a retrain, which the task deferred.
2. **PPO has not been retrained.** The existing checkpoint was trained against the archived
   action semantics and the archived reward; it is not expected to perform well under
   `action_mode="share"` or `goal_credit_mode="growth_weighted"`.
3. **The PPO comparison is now fair only in the sense that the structural handicap is
   removable** — running PPO against `action_mode="share"` requires a new checkpoint.
4. **`torch` is CPU-only** here, so a full retrain is slow locally; use Colab for anything
   beyond a smoke run.
5. `monthly_financial_simulation_base.csv` (959 MB) and `portfolio_simulation_validated.csv`
   (169 MB) were schema-inspected but **not content-validated** (F-14).
6. The multi-goal synthetic generator was read but not independently re-derived (F-15).

---

# Addendum — 2026-10-11 pass (Phases B, H, I, J, M)

**Working copy:** `S:\fyp\GoalPilot_AI_Completed` · companion app `S:\fyp\GoalPilot_Application`
Originals untouched. Rule unchanged: **no archived behaviour removed, only made optional.**

## A1. New files

| File | Phase | Purpose |
|---|---|---|
| `audit_tools/70_large_csv_validation.py` | B | streaming content validation of the two large simulation CSVs (finding F-14) |
| `audit_tools/71_large_csv_anomaly_diagnosis.py` | B | diagnoses the two identities that the first pass flagged |
| `audit_tools/80_ppo_training_v8.py` | H | controlled PPO training under `recommended()` with validation-based selection and held-out evaluation |
| `audit_tools/81_ppo_v8_report.py` | H | renders the Phase-H report from the run's own artefacts |
| `audit_tools/90_demo_end_to_end.py` | M | reproducible demo across feasible / partial / infeasible users |
| `audit_tools/05a_version_dump.py` | L | records the exact dependency set |
| `requirements.txt` | L | pinned, verified dependency set (previously absent) |
| `simulation/05_simulation_runs/rl_prototype/goalpilot_knowledge.py` | I | uncited general financial principles + deterministic retrieval |
| `simulation/05_simulation_runs/rl_prototype/goalpilot_explain.py` | I | grounded explanation engine + sensitivity |
| `tests/test_goalpilot_explain.py` | I | 10 tests pinning grounding, tone and determinism |
| `docs/REQUIREMENTS_TRACEABILITY.md` | A/M | requirement → file → evidence → status |
| `docs/EXPLAINABILITY.md` | I | what existed, what was added, the grounding contract |
| `docs/APPLICATION.md` | J | application inventory + verified startup + E2E evidence |
| `docs/final/architecture.svg` | M | final architecture diagram |
| `docs/final/ARCHITECTURE_AND_METHODOLOGY.md` | M | data flow, simulation, LP and RL methodology |
| `docs/final/EVALUATION_AND_RESULTS.md` | M | evaluation methodology and results |
| `docs/final/DEFENCE_PACK.md` | M | assumptions, demo, scenarios, panel Q&A, report outline |

## A2. Modified files

| File | Change | Why | Evidence |
|---|---|---|---|
| `goalpilot_explain.py` | clarified that budget released by per-goal caps is the **same money** reported as unallocated surplus (not additive) | the two totals coincide, which read as a double count | `outputs/demo/*.md` |
| `GoalPilot_Application/backend/app/integration/optimization_adapter.py` | guidance strings relabelled from `"NISM Guidance: …"` to `"General principle: …"`; a disclaimer note added | asserted a source the project cannot cite | app suite `15 passed`; live `/api/optimize` |
| `GoalPilot_Application/frontend/src/components/ResultsDashboard.jsx` | heading "NISM Investor Guidance & Financial Best Practices" → "Investor Guidance & Financial Best Practices" | same | — |
| `docs/MODIFICATION_LOG.md` | this addendum | record keeping | — |

## A3. Findings from this pass

| id | finding | status |
|---|---|---|
| **B-1** | In `monthly_financial_simulation_base.csv` the column `monthly_surplus` equals `income − expenditure`; the EMI is **not** netted out. It therefore deviates from `income − expenditure − emi` on exactly the 601,744 rows (42.08 %) that carry an EMI. The alternative identity holds to 9.5e-11. The RL environment, by contrast, computes surplus *net* of EMI. | documented; no data is corrupt |
| **F-14 closed** | 1,430,000 rows × 2 files validated: portfolio compounding, `portfolio_return = market_exposure × nifty_monthly_return`, `market_exposure = risk_score`, no duplicate keys, no nulls, no non-numeric cells, cross-file returns and values agree exactly. | **resolved** |
| — | a mask-inversion bug in the *first draft* of the validator incorrectly flagged 2 portfolio rows; it was found by diagnosing rather than trusting the output, fixed, and re-run to 0 failures. | corrected in-pass |

## A4. What this pass did **not** change

The reward function, the reward weights, the LP optimizer, the datasets, both archived model
checkpoints, `GoalPilotConfig` defaults, and every archived result CSV. All new experiments
write to versioned folders (`final_validation_v8`, `reward_design/v8`, `outputs/audit`,
`outputs/demo`).

## A5. Limitations carried forward

Previously listed limitations 1–4 and 6 still stand (reward unchanged; no reward version
selected; CPU-only training; `residual_carried` never exercised; multi-goal generator not
re-derived). Limitation 5 (**large CSVs not content-validated**) is now closed. Added:

7. The explainability knowledge base is ten **uncited** general principles; there is no external
   corpus and no RAG.
8. The web application remains single-goal and unconstrained; multi-goal and RL are research-only.
