"""Phase G — PPO training readiness and smoke test.

Executes the seven-step smoke test required before any substantial training run:

    1. construct the environment under the recommended configuration
    2. gymnasium ``check_env``
    3. reset and step through a complete episode
    4. verify finite observations and rewards
    5. load the archived checkpoint **in archived mode** and predict
    6. train a very small new PPO under the recommended configuration
    7. verify the new model predicts actions and completes an evaluation episode

It also writes the reproducible experiment configuration
(``training_logs/experiments/experiment_config_v1.json``) containing every field the brief
requires: environment configuration, reward version, action semantics, training/held-out
user ids, seeds, PPO hyper-parameters, total timesteps, episode length, evaluation
frequency, checkpoint locations, dependency versions and evaluation metrics.

Nothing here starts a substantial run. ``SMOKE_TIMESTEPS`` is deliberately tiny.

Colab-compatible: the project root is resolved through ``goalpilot_paths``, which falls back
to a Colab mount only when no local root exists.
"""
from __future__ import annotations

import json
import platform
import sys
from pathlib import Path

ROOT_HINT = Path(__file__).resolve().parents[1]
if str(ROOT_HINT) not in sys.path:
    sys.path.insert(0, str(ROOT_HINT))

from goalpilot_paths import ProjectPaths  # noqa: E402

paths = ProjectPaths.resolve()
paths.add_to_sys_path()
paths.ensure_output_dirs()

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from gymnasium.utils.env_checker import check_env  # noqa: E402

import goalpilot_env  # noqa: E402
from goalpilot_config import GoalPilotConfig  # noqa: E402

SMOKE_TIMESTEPS = 2048
SMOKE_SEED = 7
EXPERIMENT_DIR = paths.root / "training_logs" / "experiments"
EXPERIMENT_DIR.mkdir(parents=True, exist_ok=True)
OUT_DIR = paths.root / "outputs" / "evaluation" / "final_validation_v1"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def load_data():
    profiles = pd.read_csv(paths.rl_profiles_csv)
    goals = pd.read_csv(paths.rl_goals_csv)
    market = pd.read_csv(paths.rl_market_csv)
    split = pd.read_csv(paths.rl_split_csv)
    return profiles, goals, market, split


def user_ids(split, column: str) -> list[str]:
    for candidate in (column, "split", "set", "subset", "is_test"):
        if candidate in split.columns:
            break
    else:
        raise KeyError(f"none of the expected split columns exist: {list(split.columns)}")
    if candidate == column:
        return split.loc[split[candidate].astype(str).str.lower() == "test",
                         "user_id"].astype(str).tolist()
    return split.loc[split[candidate].astype(bool), "user_id"].astype(str).tolist()


def make_env(config, user_ids_):
    return goalpilot_env.GoalPilotEnv(
        profiles=profiles, goals=goals, market=market,
        user_ids=user_ids_, config=config,
    )


def roll(env, uid, policy):
    env.reset(options={"user_id": uid})
    rewards, months = [], 0
    while True:
        action = np.zeros(env.action_space.shape, dtype=np.float32)
        action[:, 0], action[:, 1], action[:, 2] = policy
        obs, reward, term, trunc, info = env.step(action)
        assert np.isfinite(obs).all(), "non-finite observation"
        assert np.isfinite(reward), "non-finite reward"
        rewards.append(float(reward))
        months += 1
        if term or trunc:
            break
    return rewards, months, info


profiles, goals, market, split = load_data()
test_users = user_ids(split, "split")
if not test_users:
    raise RuntimeError("no held-out users found in the split file")

results: dict[str, object] = {
    "python": sys.version.split()[0],
    "platform": platform.platform(),
    "test_users": test_users,
}

# ---- versions -----------------------------------------------------------------------------
versions = {"python": sys.version.split()[0]}
for name in ("numpy", "pandas", "gymnasium", "stable_baselines3", "torch"):
    try:
        module = __import__(name)
        versions[name] = getattr(module, "__version__", "unknown")
    except Exception as exc:  # pragma: no cover
        versions[name] = f"unavailable: {exc}"
results["dependency_versions"] = versions

# ---- step 1-4: recommended configuration ---------------------------------------------------
rec_cfg = GoalPilotConfig.recommended()
env = make_env(rec_cfg, test_users)

# ---- step 2: check_env ---------------------------------------------------------------------
check_env(env, warn=True, skip_render_check=True)
results["step2_check_env"] = "passed"

# ---- step 3-4: a full episode --------------------------------------------------------------
rewards, months_run, final_info = roll(env, test_users[0], (1.0, 0.0, 0.0))
results["step3_episode"] = {
    "user": test_users[0],
    "months": months_run,
    "episode_length_expected": int(env.max_steps),
    "total_reward": float(np.sum(rewards)),
    "finite_rewards": bool(np.isfinite(rewards).all()),
    "final_net_worth": float(final_info["net_worth"]),
}

# ---- step 5: archived checkpoint under archived semantics ----------------------------------
archived_cfg = GoalPilotConfig.archived()
arch_env = make_env(archived_cfg, test_users)
step5: dict[str, object] = {"model_path": str(paths.ppo_best_model)}
try:
    from stable_baselines3 import PPO

    model = PPO.load(str(paths.ppo_best_model))
    obs, _ = arch_env.reset(options={"user_id": test_users[0]})
    action, _ = model.predict(obs, deterministic=True)
    step5["loaded"] = True
    step5["action_shape"] = list(np.asarray(action).shape)
    step5["action_finite"] = bool(np.isfinite(np.asarray(action)).all())
    obs, _ = arch_env.reset(options={"user_id": test_users[0]})
    rewards5, done = [], False
    while not done:
        action, _ = model.predict(obs, deterministic=True)
        obs, reward, term, trunc, model_info = arch_env.step(action)
        rewards5.append(float(reward))
        done = bool(term or trunc)
    step5["episode_months"] = len(rewards5)
    step5["episode_reward"] = float(np.sum(rewards5))
    step5["final_net_worth"] = float(model_info["net_worth"])
except FileNotFoundError as exc:
    step5["loaded"] = False
    step5["error"] = str(exc)
results["step5_archived_checkpoint"] = step5

# ---- step 6: a very small new PPO under the recommended configuration ----------------------
from stable_baselines3 import PPO  # noqa: E402
from stable_baselines3.common.monitor import Monitor  # noqa: E402

train_env = Monitor(make_env(rec_cfg, test_users))
smoke_model = PPO(
    "MlpPolicy",
    train_env,
    n_steps=256,
    batch_size=64,
    n_epochs=4,
    gamma=0.99,
    learning_rate=3e-4,
    policy_kwargs=dict(net_arch=[128, 128]),
    seed=SMOKE_SEED,
    verbose=0,
)
smoke_model.learn(total_timesteps=SMOKE_TIMESTEPS, progress_bar=False)
smoke_path = EXPERIMENT_DIR / "smoke" / "ppo_smoke.zip"
smoke_model.save(str(smoke_path))
results["step6_smoke_training"] = {
    "timesteps": SMOKE_TIMESTEPS,
    "saved_to": str(smoke_path),
    "saved": smoke_path.is_file(),
}

# ---- step 7: the new model must predict and complete an evaluation episode ------------------
eval_env = make_env(rec_cfg, test_users)
obs, _ = eval_env.reset(options={"user_id": test_users[0]})
action, _ = smoke_model.predict(obs, deterministic=True)
new_rewards, done = [], False
while not done:
    action, _ = smoke_model.predict(obs, deterministic=True)
    obs, reward, term, trunc, info = eval_env.step(action)
    new_rewards.append(float(reward))
    done = bool(term or trunc)
results["step7_new_model_evaluation"] = {
    "action_shape": list(np.asarray(action).shape),
    "action_finite": bool(np.isfinite(np.asarray(action)).all()),
    "episode_months": len(new_rewards),
    "episode_reward": float(np.sum(new_rewards)),
    "final_net_worth": float(info["net_worth"]),
    "mean_funding_ratio": float(
        np.mean(np.minimum(eval_env.goal_balances, eval_env.goal_targets)
                / np.maximum(eval_env.goal_targets, 1e-9))
    ),
}

# ---- the reproducible experiment configuration ---------------------------------------------
experiment = {
    "experiment_id": "goalpilot_ppo_v1",
    "status": "SMOKE ONLY - substantial training NOT started",
    "env_config": rec_cfg.to_dict(),
    "env_config_preset": "GoalPilotConfig.recommended()",
    "reward_version": "archived_v1 (unchanged)",
    "action_semantics": rec_cfg.action_mode,
    "goal_credit_semantics": rec_cfg.goal_credit_mode,
    "accounting_mode": rec_cfg.accounting_mode,
    "target_basis": rec_cfg.target_basis,
    "train_user_ids": [u for u in profiles["user_id"].astype(str) if u not in test_users],
    "heldout_user_ids": test_users,
    "seeds": {"env_seed": rec_cfg.seed, "smoke_seed": SMOKE_SEED, "archived_seed": 42},
    "ppo_hyperparameters": {
        "policy": "MlpPolicy",
        "n_steps": 256,
        "batch_size": 64,
        "n_epochs": 4,
        "gamma": 0.99,
        "learning_rate": 3e-4,
        "net_arch": [128, 128],
        "smoke_timesteps": SMOKE_TIMESTEPS,
        "proposed_full_timesteps": 100000,
    },
    "total_timesteps_smoke": SMOKE_TIMESTEPS,
    "episode_length_months": int(env.max_steps),
    "evaluation_frequency_steps": 1420,
    "checkpoints": {
        "archived": str(paths.ppo_best_model),
        "smoke": str(smoke_path),
        "proposed_output_dir": str(EXPERIMENT_DIR / "goalpilot_ppo_v1"),
    },
    "dependency_versions": versions,
    "evaluation_metrics": [
        "weighted_goal_achievement", "pct_goals_fully_funded",
        "pct_goals_met_by_deadline", "goal_level_shortfall",
        "final_liquid_cash", "final_portfolio_value", "outstanding_loan_balance",
        "net_worth", "investment_gain", "downside_exposure",
        "total_loan_principal", "total_interest_paid", "budget_violations",
    ],
    "compatibility": {
        "archived_checkpoint_valid_only_with": "GoalPilotConfig.archived()",
        "new_checkpoint_requires": "GoalPilotConfig.recommended() (share + market_weighted)",
    },
}
config_path = EXPERIMENT_DIR / "experiment_config_v1.json"
config_path.write_text(json.dumps(experiment, indent=2), encoding="utf-8")
results["experiment_config_path"] = str(config_path)

report_path = OUT_DIR / "ppo_smoke_test.json"
report_path.write_text(json.dumps(results, indent=2), encoding="utf-8")

print(json.dumps({
    "check_env": results["step2_check_env"],
    "episode_months": results["step3_episode"]["months"],
    "archived_loaded": step5.get("loaded"),
    "archived_episode_reward": step5.get("episode_reward"),
    "smoke_saved": results["step6_smoke_training"]["saved"],
    "new_model_episode_reward": results["step7_new_model_evaluation"]["episode_reward"],
    "config": str(config_path),
    "report": str(report_path),
}, indent=2))
