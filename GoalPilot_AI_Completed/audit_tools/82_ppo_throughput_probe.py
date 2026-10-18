"""Measure PPO throughput on this host for a small number of torch thread settings.

The v8 training budget is justified by measured throughput, so measure it rather than assume.
Does not train a real model: it runs a few thousand PPO steps per setting and reports steps/s.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from goalpilot_paths import ProjectPaths  # noqa: E402

paths = ProjectPaths.resolve()
paths.add_to_sys_path()

import pandas as pd  # noqa: E402
import torch  # noqa: E402

import goalpilot_env  # noqa: E402
from goalpilot_config import GoalPilotConfig  # noqa: E402
from stable_baselines3 import PPO  # noqa: E402
from stable_baselines3.common.monitor import Monitor  # noqa: E402

profiles = pd.read_csv(paths.rl_profiles_csv)
goals = pd.read_csv(paths.rl_goals_csv)
market = pd.read_csv(paths.rl_market_csv)
train_users = profiles["user_id"].astype(str).head(48).tolist()

STEPS = 4096
SETTINGS = [1, 2, 4, 8, 16]

results = []
for threads in SETTINGS:
    torch.set_num_threads(threads)
    env = Monitor(goalpilot_env.GoalPilotEnv(
        profiles=profiles, goals=goals, market=market, user_ids=train_users,
        config=GoalPilotConfig.recommended().replace(seed=7)))
    model = PPO("MlpPolicy", env, n_steps=256, batch_size=64, n_epochs=4, gamma=0.99,
                learning_rate=3e-4, policy_kwargs=dict(net_arch=[128, 128]), seed=7, verbose=0)
    t0 = time.time()
    model.learn(total_timesteps=STEPS, progress_bar=False)
    dt = time.time() - t0
    env.close()
    results.append({"torch_threads": threads, "steps": STEPS, "seconds": round(dt, 2),
                    "steps_per_second": round(STEPS / dt, 1)})
    print(results[-1], flush=True)

best = max(results, key=lambda r: r["steps_per_second"])
out = {"cpu_logical": torch.get_num_threads(), "results": results, "best": best,
       "seconds_per_50k_at_best": round(50_000 / best["steps_per_second"], 1)}
(ROOT / "outputs" / "audit" / "ppo_throughput_probe.json").parent.mkdir(parents=True, exist_ok=True)
(ROOT / "outputs" / "audit" / "ppo_throughput_probe.json").write_text(
    json.dumps(out, indent=2), encoding="utf-8")
print(json.dumps(out, indent=2))
