# Test execution report — real console output

**Date:** 2026-10-11
**Interpreter:** `C:\Users\sudha\AppData\Local\Programs\Python\Python313\python.exe` (3.13.7)
**Working copy:** `S:\fyp\GoalPilot_AI_Completed`

Every command below was actually executed. Nothing here is projected. Where a run failed, the
failure and its resolution are shown rather than hidden. Raw console logs are preserved
verbatim next to this file in `outputs/evaluation/final_validation_v1/`.

---

## 1. Final results

| Suite | Result | Wall time | Log |
|---|---|---:|---|
| RL suite (project root) | **93 passed** | 279.97 s | `pytest_full_suite_final.txt` |
| LP suite (`GoalPilot_MultiGoal_Extension`) | **26 passed** | 3.07 s | `pytest_lp_suite_final.txt` |

```
$ python -m pytest -q                 # project root

........................................................................ [ 77%]
.....................                                                    [100%]
93 passed in 279.97s (0:04:39)
```

```
$ cd GoalPilot_MultiGoal_Extension
$ python -m pytest -q

..........................                                               [100%]
26 passed in 3.07s
```

**0 failures, 0 errors, 0 skips.** No environment variables were set, so `pytest.ini` alone
makes the project self-contained.

## 2. Composition of the 93 RL tests

| Module | Tests | Purpose |
|---|---:|---|
| `test_goalpilot_env_parity.py` | 3 | **Archived parity:** 100 users x 5 policies x 142 months against the archived module, reward to 1e-12 |
| `test_goalpilot_env_accounting.py` | 7 | Ledger vs legacy double counting (F-04/F-05) |
| `test_goalpilot_env_modes.py` | 8 | Saturation plateau, share mode, growth weighting, inflated targets |
| `test_goalpilot_env_lifecycle.py` | 18 | `check_env`, spaces, determinism, reward decomposition, invariants, checkpoint load |
| `test_goalpilot_config_paths.py` | 24 | Config validation, presets, path resolution |
| `test_lp_rl_target_parity.py` | 4 | LP/RL target-basis parity |
| `test_goalpilot_env_ledger_integrity.py` | 11 | **New** — R-01, R-04, R-05, R-06 |
| `test_goalpilot_env_semantics.py` | 18 | **New** — Phase C, R-02, R-03, R-11 |
| **Total** | **93** | |

Plus 26 pre-existing LP tests in `GoalPilot_MultiGoal_Extension/tests/`.

## 3. Intermediate runs during this work

| Run | Command | Result |
|---|---|---|
| Baseline (pre-fix) | `pytest -q` | `64 passed in 183.13s` |
| Baseline (pre-fix) | LP suite | `26 passed in 1.73s` |
| New ledger module | `pytest tests\test_goalpilot_env_ledger_integrity.py -q` | `11 passed in 12.28s` |
| After Stage 2 fixes | `pytest -q` | `75 passed in 410.40s (0:06:50)` |
| Phase C batch 1 | `semantics + accounting + modes + config` | `51 passed, 6 failed` (see §4.2) |
| Phase C batch 2 | `semantics + accounting + ledger` | `36 passed in 80.91s` |
| Post-fix targeted | `lifecycle + semantics` | `36 passed in 28.43s` |
| Full suite, first attempt | `pytest -q` | `1 failed, 92 passed in 482.28s` (see §4.3) |
| **Full suite, final** | `pytest -q` | **`93 passed in 279.97s`** |

## 4. Failures encountered, and how each was resolved

### 4.1 `TypeError: PPO.__init__() got an unexpected keyword argument 'net_arch'`

The Phase G smoke script passed `net_arch=[128, 128]` directly to `PPO`. In Stable-Baselines3
it belongs inside `policy_kwargs`. Fixed in `audit_tools/32_ppo_smoke_test.py`; the smoke test
then passed all seven steps. **This was a bug in my new tooling, not in the project.**

### 4.2 Six self-inflicted assertion errors in my own new test module

Phase C batch 1 reported `51 passed, 6 failed`, all in
`tests/test_goalpilot_env_semantics.py`. In every case the *code* was right and **my assertion
was wrong**:

| Wrong assertion | Why it was wrong | Corrected to |
|---|---|---|
| `unallocated_surplus == 0` every month in share mode | Once a per-goal cap releases money it becomes unallocated surplus — expected behaviour (finding R-08), not a defect | the budget identity `savings + investment + unallocated == discretionary_budget` |
| `total_investment_gain == 0` for a user with zero investment capacity | The household's **pre-existing** portfolio keeps earning regardless of new capacity (observed ₹76,488.98) | `cumulative_investment_contributions == 0` |
| `cash + restricted_cash == initial_savings` | `restricted_cash` is a disclosure **inside** `cash`, never added to it (observed 2 x ₹178,733.65) | `cash == initial_savings` and `cash >= restricted_cash` |

### 4.3 `test_reward_components_sum_to_reward` — the one failure that was real

The first full-suite run after the Phase D work reported:

```
1 failed, 92 passed in 482.28s (0:08:02)

FAILED tests/test_goalpilot_env_lifecycle.py::test_reward_components_sum_to_reward
AssertionError: assert {'deadline_sh...t_worth', ...} == {'deadline_sh...risk_penalty'}
  Extra items in the left set:
  'wealth_delta'
  'terminal_net_worth'
  'terminal_goal_achievement'
```

The test asserts that `info["reward_components"]` contains **exactly** the four archived keys.
Adding three candidate keys unconditionally broke that.

**Resolution: the source was fixed, not the test.** This test pins the archived audit surface
and is meaningful, so the candidate keys are now added only when a candidate reward version is
selected:

```python
if self.config.reward_version != REWARD_VERSION_ARCHIVED:
    reward_components.update({...})   # candidate-only terms
```

With `archived_v1` (the default) the components dict is bit-identical to the historical one,
so the test passes unchanged. This was verified directly (`36 passed in 28.43s`, §3) before the
final full-suite run. **No test was weakened, deleted, or skipped anywhere in this work.**

The only test assertion that was *changed* is
`test_goalpilot_config_paths.py::test_recommended_preset_uses_the_new_mechanisms`, which now
expects `GOAL_CREDIT_MARKET_WEIGHTED` instead of `GOAL_CREDIT_GROWTH_WEIGHTED`. That is a
deliberate specification change — booking a projected return as goal funding contradicts
requirement C2 — and the assertion was made **stronger**, not weaker: it now also pins that
`growth_weighted` remains selectable for LP-parity work.

## 5. Non-test commands executed

| Command | Result |
|---|---|
| `audit_tools\32_ppo_smoke_test.py` | `check_env` passed; 142-month episode; archived checkpoint loaded (reward −12.421); 2,048-step PPO trained and saved; new model completed an episode (reward −11.632) |
| `evaluation\final_validation_evaluation.py` | 4 presets x up to 8 policies x 20 held-out users x 142 months, plus 3 reward versions; `max_component_residual = 8.88e-16`; **0** budget violations |
| `evaluation\make_final_reports.py` | Rendered `POLICY_COMPARISON_REPORT.md` and `VALIDATION_REPORT.md` from the CSV evidence |

## 6. Not executed — stated explicitly

| Item | Status |
|---|---|
| Substantial PPO training | **Never started.** Only the 2,048-step smoke checkpoint exists |
| Training under `candidate_a` / `candidate_b` | Not run |
| Google Colab | **Not reachable from this host.** Colab readiness verified structurally only |
| `evaluation/run_all.py` re-run | Deliberately not run: it would regenerate the pre-fix CSVs in `outputs/evaluation/`, which are preserved as the historical record |
| Content validation of the 959 MB and 169 MB simulation CSVs | Not done — schema-inspected only |
