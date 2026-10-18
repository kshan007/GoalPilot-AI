# GoalPilot AI — completed working project

Multi-goal personal-finance planning for Indian households: a static LP optimizer, a monthly
Gymnasium reinforcement-learning environment, a capacity-constrained LP benchmark, a fair
evaluate-and-compare harness, a grounded explainability layer, and an audit trail that explains
every number.

> **Research prototype. Not a financial-advice system.** Every return, rate and goal is either an
> explicit assumption or a synthetic value. See `docs/audit/AUDIT_REPORT.md` and
> `docs/final/DEFENCE_PACK.md` §1.

This folder is the **completed working copy**. The originals (`S:\fyp\GoalPilot_AI`,
`S:\fyp\GoalPilot_RL_PreCheck.ipynb`) are untouched.

---

## 1. What is in here

```
GoalPilot_AI_Completed/
├── README.md                           <- you are here
├── requirements.txt                    pinned, verified dependency set
├── pytest.ini                          makes `pytest` work with no setup
├── goalpilot_paths.py                  project-root resolution (local + Colab)
├── archive/                            the pre-audit environment, byte-exact
├── docs/
│   ├── audit/AUDIT_REPORT.md           15 findings (F-01…F-15) + prioritised plan
│   ├── MODIFICATION_LOG.md             every change, its reason, its test
│   ├── EXECUTION.md                    what was run, with raw output (2026-10-10)
│   ├── REQUIREMENTS_TRACEABILITY.md    requirement → file → evidence → status
│   ├── EXPLAINABILITY.md               the Phase-I knowledge + explanation layer
│   ├── APPLICATION.md                  the web app: inventory, startup, E2E evidence
│   └── final/                          FYP deliverables
│       ├── architecture.svg
│       ├── ARCHITECTURE_AND_METHODOLOGY.md
│       ├── EVALUATION_AND_RESULTS.md
│       └── DEFENCE_PACK.md             assumptions · demo · scenarios · panel Q&A
├── tests/                              RL environment, config, parity, explainability
├── evaluation/                         shared evaluator + diagnostics + plots
├── audit_tools/                        the scripts that produced every result
├── outputs/                            versioned results: audit, evaluation v1…v8, plots, demo
├── training_logs/experiments/          PPO runs (reward_experiment_v1, fresh_split_v1, ppo_recommended_v1)
├── GoalPilot_MultiGoal_Extension/      LP optimizer + its own 26 tests
├── optimization/                       LP inputs and historical outputs (unchanged)
└── simulation/                         datasets, simulation runs, RL prototype
```

A separate companion application lives at `S:\fyp\GoalPilot_Application` (FastAPI + Vite/React,
single-goal LP). See `docs/APPLICATION.md`.

---

## 2. Requirements

| | |
|---|---|
| Python | **3.13.7** (the version every recorded result used) |
| Install | `python -m pip install -r requirements.txt` |
| Hardware | any CPU. `torch` CPU-only is fine; no GPU is required |

> **Interpreter note.** On this machine bare `python` is a **different, empty** interpreter.
> Use the full path:
> ```powershell
> $py = "C:\Users\sudha\AppData\Local\Programs\Python\Python313\python.exe"
> ```

---

## 3. Quick start

```powershell
$py = "C:\Users\sudha\AppData\Local\Programs\Python\Python313\python.exe"
Set-Location S:\fyp\GoalPilot_AI_Completed

& $py -m pytest -q                              # RL environment suite
Set-Location GoalPilot_MultiGoal_Extension
& $py -m pytest -q                              # LP optimizer suite (26)
Set-Location ..

& $py audit_tools\70_large_csv_validation.py    # data integrity of the large simulation CSVs
& $py audit_tools\56_constrained_lp_comparison.py
& $py audit_tools\80_ppo_training_v8.py --stage all
& $py audit_tools\81_ppo_v8_report.py
& $py audit_tools\90_demo_end_to_end.py         # feasible / partial / infeasible scenarios
```

---

## 4. Running in Google Colab

Colab is not required; the project runs locally. If you do use it:

```python
import os
os.environ["GOALPILOT_PROJECT_ROOT"] = "/content/drive/MyDrive/GoalPilot_AI_Completed"
!pip install -q "gymnasium>=1.0,<2.0" "stable-baselines3>=2.4,<3.0"
%run GoalPilot_AI_Completed/evaluation/run_all.py
```

`goalpilot_paths.py` resolves the root via `$GOALPILOT_PROJECT_ROOT` → explicit argument →
walk-up detection → Colab mount, so the same code runs in both places. Colab execution has
**never been run from this host**; readiness is structural only.

---

## 5. Using the environment

```python
import sys
sys.path += ["simulation/05_simulation_runs/rl_prototype", "evaluation"]

import pandas as pd
from goalpilot_config import GoalPilotConfig
from goalpilot_env import GoalPilotEnv

profiles = pd.read_csv("simulation/05_simulation_runs/rl_prototype/rl_sample_financial_profiles.csv")
goals    = pd.read_csv("simulation/05_simulation_runs/rl_prototype/rl_sample_goals.csv")
market   = pd.read_csv("simulation/05_simulation_runs/rl_prototype/rl_market_credit_validated.csv")

env = GoalPilotEnv(profiles, goals, market, config=GoalPilotConfig())
obs, info = env.reset(options={"user_id": "USER_00001"})
obs, reward, terminated, truncated, info = env.step(env.action_space.sample())

print(info["budget_audit"])        # per-month cash-flow audit
print(info["reward_components"])   # the reward, decomposed
print(env.net_worth, env.earmarked_goal_funding)
```

### 5.1 Configurations

| Preset | Action mode | Accounting | Goal credit | Target basis | Use for |
|---|---|---|---|---|---|
| `archived()` | magnitude | legacy | face value | nominal | reproducing the 2026-10-10 results exactly |
| `GoalPilotConfig()` (default) | magnitude | **ledger** | face value | nominal | archived behaviour with a correct balance sheet |
| `corrected_accounting()` | magnitude | ledger | face value | nominal | same, explicit |
| `lp_parity()` | magnitude | ledger | face value | **inflated 3 %** + 6-month reserve | comparing RL against the LP on one basis |
| `recommended()` | **share** | ledger | **market-weighted** | inflated 3 % | the training/evaluation basis used in v8 |
| `with_reallocation()` | share | ledger | market-weighted | inflated 3 % | the R-13 fix (opt-in) |
| `with_action_mix()` | **mix** | ledger | market-weighted | inflated 3 % | observing the requested savings/investment mix |

`recommended()` changes goal-funding semantics, so it **invalidates the archived PPO checkpoint**.
The archived checkpoint's only valid preset is `archived()`.

### 5.2 Explainability

```python
import goalpilot_explain as ge

def savings_only(env):
    import numpy as np
    a = np.zeros(env.action_space.shape, dtype=np.float32); a[:, 0] = 1.0; return a

ex = ge.explain(env, "USER_00001", savings_only,
                sensitivity=ge.sensitivity(profiles, goals, market, "USER_00001",
                                           GoalPilotConfig.recommended(), savings_only,
                                           [ge.Variant("capacity x0.5", capacity_multiplier=0.5)]))
print(ge.render_markdown(ex))
```

Every number comes from the simulator; general principles come from `goalpilot_knowledge` and are
marked uncited. See `docs/EXPLAINABILITY.md`.

---

## 6. Reading the results

| Question | Look at |
|---|---|
| Did anything break vs the archive? | `outputs/evaluation/archive_verification.json` |
| Which policy funds goals best? | `outputs/evaluation/final_validation_v7/constrained_lp_summary_v1.csv` |
| Is the large simulation data internally consistent? | `outputs/audit/large_csv_validation_v1/large_csv_validation_report.md` |
| How did the PPO training and held-out evaluation go? | `outputs/reward_design/v8/PPO_TRAINING_AND_EVALUATION.md` |
| Feasible / partial / infeasible worked examples | `outputs/demo/*.md` |
| Why was the original PPO weak? | `docs/audit/AUDIT_REPORT.md` §F-02, F-03, F-10 |

### Headline numbers (16 fresh test users, `recommended()`, v7 cohort)

| policy | mean weighted achievement | fully funded | by deadline | cap overflow | net worth |
|---|---:|---:|---:|---:|---:|
| RL `archived_v1` seed7 | 0.5908 | 0.4813 | 0.1146 | 388,382 | 2,748,925 |
| `investment-only` | 0.5800 | 0.4656 | 0.1427 | 1,479,048 | 2,751,777 |
| `uniform savings` | 0.5584 | 0.4531 | 0.1427 | 0 | 2,363,890 |
| `existing_LP_unconstrained` | 0.4928 | 0.3771 | **0.1688** | 1,438,590 | 2,680,083 |
| `constrained_LP` | 0.2452 | 0.2323 | 0.1531 | **0** | 2,606,859 |
| `urgency` | 0.4051 | 0.0625 | **0.0000** | 0 | 2,363,890 |

The *unconstrained* LP's 0.4928 is achieved by a plan the environment cannot execute (it plans
13,736.66/month of investment, of which only 2,023.56 is accepted and 10,130.92 is relabelled as
savings). Requiring the LP to respect capacity costs it −0.2476 achievement.

### Phase-H PPO training, held-out evaluation (v8, 16 fresh test users)

6 validation-selected PPO policies (2 reward versions × seeds 7/17/27, 50k timesteps each):

| arm | achievement | fully funded | by deadline | net worth |
|---|---:|---:|---:|---:|
| `investment-only` | **0.5800** | 0.4656 | 0.1427 | **2,751,777** |
| `uniform savings` | 0.5584 | 0.4531 | 0.1427 | 2,363,890 |
| **RL `archived_v1`** | 0.4842 | 0.3674 | 0.1083 | 2,659,502 |
| **RL `candidate_a`** | 0.4398 | 0.3059 | 0.0892 | 2,633,770 |
| `constrained_LP` | 0.2452 | 0.2323 | **0.1531** | 2,606,859 |

**RL does not beat the simple rules here** (a simple investment rule is ahead by 0.0957 with a
paired interval that excludes zero). RL *does* beat the constrained LP (+0.2390, significant) but
not on deadline success. Report: `outputs/reward_design/v8/PPO_TRAINING_AND_EVALUATION.md`;
details in `docs/final/EVALUATION_AND_RESULTS.md` §6.

---

## 7. Testing

```powershell
& $py -m pytest -q                     # RL environment suite (the parity test dominates the runtime)
& $py -m pytest -q -k "not parity"     # the fast subset
```

**Verified counts on this host:** `174 passed in 599.33s` for the RL suite (164 at the v7
baseline + 10 new capture) and `26 passed in 1.94s` for the LP suite — **200 tests, 0 failures,
0 errors, 0 skips**.

The suite includes `tests/test_goalpilot_env_parity.py`, which rolls out 100 users × 5 policies ×
142 months twice and compares every reward to **1e-12** — the guarantee that no existing
behaviour changed. The LP optimizer has its own 26 tests under
`GoalPilot_MultiGoal_Extension/`. Raw console output of every run performed is in
`outputs/evaluation/pytest_*.txt`.

---

## 8. Reproducibility notes

- All randomness is seeded. `GoalPilotConfig.seed` defaults to 2026; experiments use seeds
  7 / 17 / 27.
- Every generated artefact carries the configuration that produced it (`*_config_*.json`).
- `archive/goalpilot_env_archived_20261010.py` is the pre-audit environment, byte-identical
  (SHA-256 `FDFE6D9D5280E20C1C69A9180FBDF326F7D3B9D353BCE4DAA13065F7C4A9FEFD`).
- Archived result CSVs are never overwritten; new results are written to versioned folders.
- `outputs/reward_design/v1`…`v8` and `outputs/evaluation/final_validation_v1`…`v8` record the
  whole experimental history.

---

## 9. What is still open

1. **The reward function is unchanged.** F-03 (the risk penalty dominates, with no terminal-value
   offset) and F-07 (component scaling) are diagnosed and quantified but not fixed. Fixing them
   needs a retrain under a *selected* reward version.
2. **No reward version has been selected.** The fresh-split paired difference between
   `candidate_a` and `archived_v1` was +0.0069 (CI [−0.0268, +0.0444], p = 0.72) — not
   significant. Raw reward values are never compared across versions.
3. **RL is not the best arm.** A simple investment rule beats both trained RL arms on goal
   achievement (0.5800 vs 0.4842/0.4398); RL beats the constrained LP on achievement but not on
   deadline success. Where a paired bootstrap interval spans zero the arms are reported as
   indistinguishable — see `docs/final/EVALUATION_AND_RESULTS.md` §6.
4. **The application is single-goal LP only** — no multi-goal planning and no RL inference in the
   web app.
5. **`residual_carried` (R-01b)** is asserted but never exercised by the real data.
6. **Colab was never executed** from this host.
7. `monthly_surplus` in the population CSV **excludes EMI** (finding B-1); the RL environment nets
   it out. Do not join the two naively.
