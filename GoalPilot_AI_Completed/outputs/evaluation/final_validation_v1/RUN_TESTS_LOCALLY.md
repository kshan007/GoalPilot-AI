# Running the tests locally

## 0. Interpreter — this matters

Two Python installations exist on this host:

| | Path | State |
|---|---|---|
| A | `…\Accio\pre-install\…\python\python.exe` (3.12.2) | **Empty.** Bare `python` resolves here. No numpy/pandas/torch |
| B | `C:\Users\sudha\AppData\Local\Programs\Python\Python313\python.exe` (3.13.7) | **Populated.** Use this one |

Always invoke interpreter **B** explicitly.

## 1. Dependencies

```powershell
$py = "C:\Users\sudha\AppData\Local\Programs\Python\Python313\python.exe"
& $py -m pip install "gymnasium>=0.29" "stable-baselines3>=2.3" "sb3_contrib>=2.3" pulp
```

Resolved versions on this host: `numpy 2.2.3`, `pandas 2.3.1`, `scipy 1.16.0`,
`gymnasium 1.4.0`, `stable_baselines3 2.9.0`, `sb3_contrib 2.9.0`, `torch 2.8.0+cpu`,
`pytest 9.1.1`. No GPU; training is CPU-bound.

## 2. RL suite (project root)

```powershell
Set-Location S:\fyp\GoalPilot_AI_Completed
& $py -m pytest -q
```

`pytest.ini` sets `pythonpath` and `testpaths`, so no environment variables are needed.
The suite includes `test_goalpilot_env_parity.py`, which rolls **100 users x 5 policies x
142 months** against the archived environment module and compares reward to 1e-12 — it is
slow (~2.5 min) and is the guard that archived behaviour still reproduces.

## 3. LP suite (extension)

```powershell
Set-Location S:\fyp\GoalPilot_AI_Completed\GoalPilot_MultiGoal_Extension
& $py -m pytest -q
```

## 4. Ledger and semantics tests only (fast)

```powershell
Set-Location S:\fyp\GoalPilot_AI_Completed
& $py -m pytest tests\test_goalpilot_env_ledger_integrity.py tests\test_goalpilot_env_semantics.py -q
```

## 5. Evaluation pipeline

```powershell
Set-Location S:\fyp\GoalPilot_AI_Completed
& $py evaluation\final_validation_evaluation.py
```

Writes Phases D/E/H outputs into `outputs/evaluation/final_validation_v1/` and
`outputs/reward_design/v1/`. It does **not** overwrite the pre-existing
`outputs/evaluation/*.csv` files, which are kept as the pre-fix record.

## 6. PPO readiness smoke test

```powershell
& $py audit_tools\32_ppo_smoke_test.py
```

Runs `check_env`, a full 142-month episode, loads the archived checkpoint **in archived
mode**, trains a 2,048-step smoke PPO under the recommended configuration, saves it to
`training_logs/experiments/smoke/`, and writes the reproducible experiment configuration.

## 7. Archived-parity verification against the archived CSVs

```powershell
& $py evaluation\verify_against_archive.py --project-root .
```

## 8. Troubleshooting

| Symptom | Cause |
|---|---|
| `ModuleNotFoundError: No module named 'goalpilot_config'` | The wrong interpreter, or running from outside the project root. Use the full path to interpreter B |
| `ModuleNotFoundError: No module named 'src.multi_goal_optimizer'` | The LP tests need `GoalPilot_MultiGoal_Extension` on `sys.path`; `pytest.ini` handles this for tests, and `evaluation/final_validation_evaluation.py` inserts it itself |
| A test hangs for ~2.5 minutes | Expected: `test_goalpilot_env_parity.py` |
| `TypeError: PPO.__init__() got an unexpected keyword argument 'net_arch'` | `net_arch` belongs in `policy_kwargs=dict(net_arch=[128,128])`, not as a direct PPO argument |
