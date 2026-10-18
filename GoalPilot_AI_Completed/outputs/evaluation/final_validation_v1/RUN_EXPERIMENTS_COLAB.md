# Running the experiments in Google Colab

Colab readiness was verified **structurally** (path resolver, guarded imports, explicit
interpreter-independent commands). Colab itself was **not reachable from this host**, so no
run below has been executed on Colab. That distinction is deliberate and must be preserved
in any write-up.

## 1. Why Colab

Local hardware is 16 logical cores, 16.83 GB RAM (5.61 GB free) and **no GPU**
(`torch 2.8.0+cpu`). Small experiments run locally; a substantial PPO run should use Colab.

## 2. Get the project into Colab

```python
from google.colab import drive
drive.mount('/content/drive')
# unzip the project so that a folder containing 'simulation', 'optimization' and
# 'GoalPilot_MultiGoal_Extension' exists, e.g.:
#   /content/drive/MyDrive/GoalPilot_AI_Completed
```

`goalpilot_paths.py` resolves the project root by:
1. the `GOALPILOT_ROOT` environment variable, else
2. walking up from the current file until `ROOT_MARKERS = ("simulation", "optimization", "GoalPilot_MultiGoal_Extension")` are all present, else
3. searching one level down, else
4. falling back to `/content/drive/...`.

So no path edit is required, but setting it explicitly is safest:

```python
import os
os.environ["GOALPILOT_ROOT"] = "/content/drive/MyDrive/GoalPilot_AI_Completed"
```

## 3. Install dependencies

```python
!pip -q install "gymnasium>=0.29" "stable-baselines3>=2.3" "sb3_contrib>=2.3"
```

Colab's CUDA build of PyTorch is used automatically — no local CPU-only constraint.

## 4. Run the tests

```python
%cd $GOALPILOT_ROOT
!python -m pytest -q
```

## 5. Run the smoke test before anything larger

```python
!python audit_tools/32_ppo_smoke_test.py
```

Expected: `check_env` passes, a 142-month episode runs, the archived checkpoint loads **in
archived mode** (`GoalPilotConfig.archived()` only), a 2,048-step PPO trains and predicts.
If any step fails, do not start a longer run.

## 6. Substantial training (only after the acceptance criteria pass, and only with approval)

```python
from stable_baselines3 import PPO
from stable_baselines3.common.monitor import Monitor
from goalpilot_config import GoalPilotConfig
import goalpilot_env, pandas as pd
from goalpilot_paths import ProjectPaths

paths = ProjectPaths.resolve(); paths.add_to_sys_path()
profiles = pd.read_csv(paths.rl_profiles_csv)
goals = pd.read_csv(paths.rl_goals_csv)
market = pd.read_csv(paths.rl_market_csv)
split = pd.read_csv(paths.rl_split_csv)
train_users = split.loc[split["split"] != "test", "user_id"].astype(str).tolist()

env = Monitor(goalpilot_env.GoalPilotEnv(
    profiles=profiles, goals=goals, market=market,
    user_ids=train_users, config=GoalPilotConfig.recommended()))

model = PPO("MlpPolicy", env, n_steps=256, batch_size=64, n_epochs=4, gamma=0.99,
            learning_rate=3e-4, policy_kwargs=dict(net_arch=[128, 128]), seed=7)
model.learn(total_timesteps=100_000)
model.save("training_logs/experiments/goalpilot_ppo_v1/ppo_final")
```

Use `GoalPilotConfig.recommended()` — it is `share` action semantics with `market_weighted`
goal crediting. The archived checkpoint is **not** valid under it.

## 7. Evaluate on held-out users

```python
!python evaluation/final_validation_evaluation.py
```

This evaluates eight policies on the 20 held-out users, with paired comparisons and
bootstrap confidence intervals. Add the newly trained checkpoint and re-run to slot it into
the same table.

## 8. Cost and time notes

- Local CPU smoke run (2,048 steps): seconds.
- Local full run (100k steps, no GPU): hours; Colab GPU is strongly preferred.
- Keep runs reproducible: record `seed`, `total_timesteps`, the environment configuration
  JSON, and the checkpoint path. `training_logs/experiments/experiment_config_v1.json`
  already contains every required field.
