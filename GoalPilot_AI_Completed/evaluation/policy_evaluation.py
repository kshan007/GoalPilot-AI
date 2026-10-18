"""Shared policy evaluator for GoalPilot (audit findings F-08, F-11, F-04).

Why a shared module
-------------------
The archived notebook re-implemented the evaluation loop in five separate cells. One of
them (cell 141) computed the budget metric as

    budget_excess = savings + investments + combined_monthly_commitment - surplus

which adds savings and investments **twice**, because ``combined_monthly_commitment``
already contains them (F-08). It also produced a "long horizon" table that silently
omitted PPO (F-11). Both problems disappear once there is a single evaluator.

Metrics reported
----------------
``goal_funding_ratio``      sum(min(balance, target)) / sum(target)
``net_worth_ledger``        cash + portfolio - loan_balance   (correct)
``net_worth_archived``      the archived aggregate cash + goal_balances + portfolio - loan;
                            kept only to *show* the double count (F-04)
``max_budget_excess``       combined_monthly_commitment - monthly_surplus  (no double count)
``budget_violation_count``  number of months where that exceeds a 1 paise tolerance
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

from goalpilot_config import GoalPilotConfig
from goalpilot_paths import ProjectPaths
import goalpilot_env

BUDGET_TOLERANCE = 0.01          # one paisa


@dataclass(frozen=True)
class PolicySpec:
    """A fixed action policy. PPO is handled separately (it is state-dependent)."""

    name: str
    savings: float
    investment: float
    loan: float

    def action(self, action_shape) -> np.ndarray:
        action = np.zeros(action_shape, dtype=np.float32)
        action[:, 0] = self.savings
        action[:, 1] = self.investment
        action[:, 2] = self.loan
        return action


# NOTE ON VARIANTS
# The archived notebook used *two* different definitions of "Mixed allocation":
#   cells ~119-121 (rl_policy_diagnostic_summary.csv) used (0.25, 0.25)
#   cells ~139-143 (rl_heldout_policy_comparison_*.csv) used (0.50, 0.50)
# In "magnitude" action mode those are genuinely different policies, because (0.25, 0.25)
# sums to less than the monthly budget and therefore under-allocates (F-02). Both are kept
# here, explicitly labelled, so archived tables can be matched without ambiguity.
BASELINE_POLICIES: tuple[PolicySpec, ...] = (
    PolicySpec("No action", 0.0, 0.0, 0.0),
    PolicySpec("Savings only", 1.0, 0.0, 0.0),
    PolicySpec("Investments only", 0.0, 1.0, 0.0),
    PolicySpec("Mixed allocation (0.50/0.50)", 0.5, 0.5, 0.0),
    PolicySpec("Mixed allocation (0.25/0.25)", 0.25, 0.25, 0.0),
    PolicySpec("Savings + loan", 0.5, 0.0, 1.0),
)


def _evaluate_archive_aggregate(env) -> float:
    """The archived `cash + goal_balances` style aggregate, for showing the double count."""
    return float(env.cash) + env.earmarked_goal_funding + float(env.portfolio) - float(env.loan_balance)


def rollout(env, user_id: str, policy: PolicySpec | None = None, model=None,
            deterministic: bool = True) -> dict:
    """Run one episode and return its metrics.

    Exactly one of `policy` or `model` must be supplied.
    """
    if (policy is None) == (model is None):
        raise ValueError("supply exactly one of policy= or model=")

    obs, _ = env.reset(options={"user_id": user_id})
    targets = np.asarray(env.goal_targets, dtype=float)

    total_reward = 0.0
    max_budget_excess = 0.0
    budget_violations = 0
    max_goal_overshoot = 0.0
    min_cash = float(env.cash)
    reward_totals: dict[str, float] = {}
    months = 0

    while True:
        if model is not None:
            action, _ = model.predict(obs, deterministic=deterministic)
            action = np.asarray(action, dtype=np.float32)
        else:
            action = policy.action(env.action_space.shape)

        obs, reward, terminated, truncated, info = env.step(action)

        total_reward += float(reward)
        months += 1
        for key, value in info["reward_components"].items():
            reward_totals[key] = reward_totals.get(key, 0.0) + float(value)

        # ---- corrected budget metric: combined_monthly_commitment ALREADY contains the
        # ---- savings and investment contributions, so they must not be added again.
        excess = float(info["combined_monthly_commitment"]) - float(info["monthly_surplus"])
        max_budget_excess = max(max_budget_excess, excess)
        if excess > BUDGET_TOLERANCE:
            budget_violations += 1

        balances = np.asarray(info["goal_balances"], dtype=float)
        max_goal_overshoot = max(max_goal_overshoot, float(np.max(balances - targets)))
        min_cash = min(min_cash, float(env.cash))

        if terminated or truncated:
            break

    balances = np.asarray(env.goal_balances, dtype=float)
    funded = float(np.minimum(balances, targets).sum())
    record = {
        "user_id": user_id,
        "policy": policy.name if policy is not None else "PPO",
        "months": months,
        "goal_target_amount": float(targets.sum()),
        "goal_funding_amount": funded,
        "goal_funding_ratio": funded / max(float(targets.sum()), 1.0),
        "final_cash": float(env.cash),
        "final_portfolio": float(env.portfolio),
        "final_loan_balance": float(env.loan_balance),
        "final_earmarked_goal_funding": env.earmarked_goal_funding,
        "net_worth_ledger": float(env.net_worth),
        "net_worth_archived_aggregate": _evaluate_archive_aggregate(env),
        "total_savings_contributions": float(env.cumulative_savings_contributions),
        "total_investment_contributions": float(env.cumulative_investment_contributions),
        "total_new_loan_principal": float(env.cumulative_loan_principal),
        "total_interest_paid": float(env.total_interest_paid),
        "total_unallocated_surplus": float(env.total_unallocated_surplus),
        "total_investment_gain": float(env.total_investment_gain),
        "total_reward": total_reward,
        "max_budget_excess": max_budget_excess,
        "budget_violation_months": budget_violations,
        "max_goal_overshoot": max_goal_overshoot,
        "min_cash_balance": min_cash,
    }
    for key in ("incremental_progress", "deadline_shortfall_penalty",
                "loan_penalty", "risk_penalty"):
        record[f"reward__{key}"] = reward_totals.get(key, 0.0)
    return record


def evaluate(profiles, goals, market, user_ids: Sequence[str],
             config: GoalPilotConfig,
             policies: Iterable[PolicySpec] = BASELINE_POLICIES,
             model=None, deterministic: bool = True) -> pd.DataFrame:
    """Evaluate every policy (plus PPO when `model` is given) on every user."""
    user_ids = [str(u) for u in user_ids]
    env = goalpilot_env.GoalPilotEnv(
        profiles=profiles, goals=goals, market=market,
        user_ids=user_ids, config=config,
    )
    records: list[dict] = []
    for spec in policies:
        for uid in user_ids:
            records.append(rollout(env, uid, policy=spec))
    if model is not None:
        for uid in user_ids:
            records.append(rollout(env, uid, model=model, deterministic=deterministic))
    return pd.DataFrame(records)


AGGREGATIONS = {
    "users": ("user_id", "nunique"),
    "mean_goal_funding_ratio": ("goal_funding_ratio", "mean"),
    "median_goal_funding_ratio": ("goal_funding_ratio", "median"),
    "mean_goal_funding_amount": ("goal_funding_amount", "mean"),
    "mean_net_worth_ledger": ("net_worth_ledger", "mean"),
    "mean_net_worth_archived_aggregate": ("net_worth_archived_aggregate", "mean"),
    "mean_final_cash": ("final_cash", "mean"),
    "mean_final_portfolio": ("final_portfolio", "mean"),
    "mean_final_loan_balance": ("final_loan_balance", "mean"),
    "mean_new_loan_principal": ("total_new_loan_principal", "mean"),
    "mean_interest_paid": ("total_interest_paid", "mean"),
    "mean_unallocated_surplus": ("total_unallocated_surplus", "mean"),
    "mean_total_reward": ("total_reward", "mean"),
    "max_budget_excess": ("max_budget_excess", "max"),
    "total_budget_violation_months": ("budget_violation_months", "sum"),
    "max_goal_overshoot": ("max_goal_overshoot", "max"),
}


def summarise(detail: pd.DataFrame) -> pd.DataFrame:
    return (
        detail.groupby("policy", sort=False)
        .agg(**AGGREGATIONS)
        .reset_index()
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=None)
    parser.add_argument("--config", default="archived",
                        choices=["archived", "corrected_accounting", "lp_parity", "recommended"])
    parser.add_argument("--split", default="all", choices=["all", "train", "test"])
    parser.add_argument("--include-ppo", action="store_true")
    parser.add_argument("--tag", default=None, help="suffix for the output file names")
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
        if not paths.ppo_best_model.exists():
            raise FileNotFoundError(f"checkpoint not found: {paths.ppo_best_model}")
        model = PPO.load(str(paths.ppo_best_model))

    detail = evaluate(profiles, goals, market, user_ids, config,
                      BASELINE_POLICIES, model=model)
    summary = summarise(detail)

    tag = args.tag or f"{args.config}_{args.split}"
    detail_path = paths.evaluation_out / f"policy_detail_{tag}.csv"
    summary_path = paths.evaluation_out / f"policy_summary_{tag}.csv"
    detail.to_csv(detail_path, index=False)
    summary.to_csv(summary_path, index=False)

    config_path = paths.evaluation_out / f"policy_config_{tag}.json"
    config_path.write_text(
        json.dumps({"config": config.to_dict(), "split": args.split,
                    "users": len(user_ids), "include_ppo": args.include_ppo},
                   indent=2),
        encoding="utf-8",
    )

    pd.set_option("display.width", 200)
    print(f"=== Policy evaluation ({args.config}, split={args.split}, "
          f"{len(user_ids)} users) ===")
    print(summary.round(4).to_string(index=False))
    print(f"\nwrote:\n  {detail_path}\n  {summary_path}\n  {config_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
