"""Reward-component decomposition (audit finding F-07).

The archive defined four reward terms but never measured their relative size. This script
does, for every policy, and writes a per-month breakdown.

The reward FUNCTION IS UNCHANGED. Only reporting was added, which is why this diagnostic
could be produced before any decision about how to fix the reward.

Components
----------
incremental_progress        +2.0 * clip(ratio gain) * priority/5, per goal per month
deadline_shortfall_penalty  -5.0 * shortfall_ratio * criticality/5, only in a goal's deadline month
loan_penalty                -1e-5 * new loan principal
risk_penalty                -max(0, |market return| - risk_score*0.05) * portfolio/100000
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

from goalpilot_config import GoalPilotConfig
from goalpilot_paths import ProjectPaths
from policy_evaluation import BASELINE_POLICIES, PolicySpec
import goalpilot_env

COMPONENTS = (
    "incremental_progress",
    "deadline_shortfall_penalty",
    "loan_penalty",
    "risk_penalty",
)


def decompose(env, user_id: str, policy: PolicySpec | None = None, model=None) -> list[dict]:
    obs, _ = env.reset(options={"user_id": user_id})
    rows = []
    while True:
        if model is not None:
            action, _ = model.predict(obs, deterministic=True)
            action = np.asarray(action, dtype=np.float32)
        else:
            action = policy.action(env.action_space.shape)

        obs, reward, terminated, truncated, info = env.step(action)
        parts = info["reward_components"]
        row = {
            "user_id": user_id,
            "policy": policy.name if policy is not None else "PPO",
            "month": info["budget_audit"]["month"],
            "reward": float(reward),
            "portfolio": float(env.portfolio),
            "net_worth": float(env.net_worth),
            "goal_funding_ratio": env.funding_ratio(),
            "savings_contribution": float(info["savings_contribution"]),
            "investment_contribution": float(info["investment_contribution"]),
            "unallocated_surplus": float(info["unallocated_surplus"]),
            "loan_balance": float(env.loan_balance),
        }
        for name in COMPONENTS:
            row[name] = float(parts[name])
        row["component_sum"] = sum(float(parts[name]) for name in COMPONENTS)
        row["residual"] = row["reward"] - row["component_sum"]
        rows.append(row)
        if terminated or truncated:
            break
    return rows


def summarise(df: pd.DataFrame) -> pd.DataFrame:
    records = []
    for policy, group in df.groupby("policy", sort=False):
        total_reward = float(group["reward"].sum())
        record = {
            "policy": policy,
            "months": int(len(group)),
            "episodes": int(group[["user_id"]].drop_duplicates().shape[0]),
            "total_reward_sum": total_reward,
            "mean_reward_per_month": float(group["reward"].mean()),
            "max_abs_component_residual": float(group["residual"].abs().max()),
        }
        for name in COMPONENTS:
            series = group[name]
            record[f"{name}__sum"] = float(series.sum())
            record[f"{name}__months_active"] = int((series.abs() > 1e-12).sum())
            record[f"{name}__share_of_abs_total"] = (
                float(series.abs().sum() / group["reward"].abs().sum())
                if group["reward"].abs().sum() > 0 else 0.0
            )
        records.append(record)
    out = pd.DataFrame(records)
    out["dominant_component"] = out[
        [f"{n}__share_of_abs_total" for n in COMPONENTS]
    ].idxmax(axis=1).str.replace("__share_of_abs_total", "", regex=False)
    return out


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=None)
    parser.add_argument("--config", default="archived",
                        choices=["archived", "corrected_accounting", "lp_parity", "recommended"])
    parser.add_argument("--split", default="test", choices=["all", "train", "test"])
    parser.add_argument("--include-ppo", action="store_true")
    parser.add_argument("--tag", default=None)
    args = parser.parse_args(argv)

    paths = ProjectPaths.resolve(args.project_root).ensure_output_dirs().add_to_sys_path()
    config = getattr(GoalPilotConfig, args.config)()

    profiles = pd.read_csv(paths.rl_profiles_csv)
    goals = pd.read_csv(paths.rl_goals_csv)
    market = pd.read_csv(paths.rl_market_csv)
    split = pd.read_csv(paths.rl_split_csv)

    if args.split == "all":
        user_ids = profiles["user_id"].astype(str).tolist()
    else:
        wanted = set(split.loc[split["split"] == args.split, "user_id"].astype(str))
        user_ids = [u for u in profiles["user_id"].astype(str) if u in wanted]
        profiles = profiles[profiles["user_id"].astype(str).isin(wanted)].copy()
        goals = goals[goals["user_id"].astype(str).isin(wanted)].copy()

    model = None
    if args.include_ppo:
        from stable_baselines3 import PPO
        model = PPO.load(str(paths.ppo_best_model))

    env = goalpilot_env.GoalPilotEnv(
        profiles=profiles, goals=goals, market=market,
        user_ids=user_ids, config=config,
    )

    rows: list[dict] = []
    for policy in BASELINE_POLICIES:
        for uid in user_ids:
            rows.extend(decompose(env, uid, policy=policy))
    if model is not None:
        for uid in user_ids:
            rows.extend(decompose(env, uid, model=model))

    detail = pd.DataFrame(rows)
    summary = summarise(detail)

    tag = args.tag or f"{args.config}_{args.split}"
    detail_path = paths.evaluation_out / f"reward_decomposition_detail_{tag}.csv"
    summary_path = paths.evaluation_out / f"reward_decomposition_summary_{tag}.csv"
    detail.to_csv(detail_path, index=False)
    summary.to_csv(summary_path, index=False)

    pd.set_option("display.width", 240)
    cols = (["policy", "months", "total_reward_sum", "mean_reward_per_month",
             "dominant_component", "max_abs_component_residual"]
            + [f"{n}__sum" for n in COMPONENTS])
    print(f"=== Reward decomposition ({args.config}, split={args.split}) ===")
    print(summary[cols].round(4).to_string(index=False))

    worst = float(detail["residual"].abs().max())
    print(f"\nmax |reward - sum(components)| = {worst:.3e}  (must be ~0)")
    print(f"wrote:\n  {detail_path}\n  {summary_path}")

    (paths.evaluation_out / f"reward_decomposition_meta_{tag}.json").write_text(
        json.dumps({"config": config.to_dict(), "split": args.split,
                    "max_component_residual": worst}, indent=2), encoding="utf-8")
    return 0 if worst < 1e-9 else 1


if __name__ == "__main__":
    raise SystemExit(main())
