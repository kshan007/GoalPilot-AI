"""Phases D, E and H — reward decomposition, LP/RL comparability, fair policy evaluation.

Run:  python evaluation/final_validation_evaluation.py

Phase D  decomposes the reward for every fixed policy under each reward version, verifying
         numerically that the components sum to the environment reward.
Phase E  evaluates the *same* held-out users under all four configuration presets and reports
         goal funding against BOTH nominal and inflation-adjusted targets, so that no RL-vs-LP
         claim rests on an incomparable denominator.
Phase H  evaluates eight policies - including the LP optimizer's plan and the archived PPO
         checkpoint - on a consistent cohort, with dispersion, bootstrap confidence intervals
         and paired comparisons against a common reference.

Everything is written to versioned directories; no historical output is overwritten.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT_HINT = Path(__file__).resolve().parents[1]
if str(ROOT_HINT) not in sys.path:
    sys.path.insert(0, str(ROOT_HINT))

from goalpilot_paths import ProjectPaths  # noqa: E402

paths = ProjectPaths.resolve()
paths.add_to_sys_path()

sys.path.insert(0, str(paths.root / "GoalPilot_MultiGoal_Extension"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import goalpilot_env  # noqa: E402
from goalpilot_config import (  # noqa: E402
    REWARD_VERSION_A,
    REWARD_VERSION_B,
    GoalPilotConfig,
)

EVAL_OUT = paths.root / "outputs" / "evaluation" / "final_validation_v1"
REWARD_OUT = paths.root / "outputs" / "reward_design" / "v1"
EVAL_OUT.mkdir(parents=True, exist_ok=True)
REWARD_OUT.mkdir(parents=True, exist_ok=True)

BOOTSTRAP = 2000
BOOTSTRAP_SEED = 20261011

profiles = pd.read_csv(paths.rl_profiles_csv)
goals = pd.read_csv(paths.rl_goals_csv)
market = pd.read_csv(paths.rl_market_csv)
split = pd.read_csv(paths.rl_split_csv)
split_col = next(c for c in ("split", "set", "subset", "is_test") if c in split.columns)
TEST_USERS = split.loc[split[split_col].astype(str).str.lower() == "test",
                       "user_id"].astype(str).tolist()
TRAIN_USERS = split.loc[split[split_col].astype(str).str.lower() != "test",
                        "user_id"].astype(str).tolist()

FIXED_POLICIES = {
    "No action": (0.0, 0.0, 0.0),
    "Savings only": (1.0, 0.0, 0.0),
    "Investments only": (0.0, 1.0, 0.0),
    "Mixed (0.50/0.50)": (0.5, 0.5, 0.0),
    "Savings + loan": (0.5, 0.0, 1.0),
}
PRESETS = {
    "archived": GoalPilotConfig.archived,
    "corrected_accounting": GoalPilotConfig.corrected_accounting,
    "lp_parity": GoalPilotConfig.lp_parity,
    "recommended": GoalPilotConfig.recommended,
}


def make_env(config, user_ids):
    return goalpilot_env.GoalPilotEnv(
        profiles=profiles, goals=goals, market=market,
        user_ids=user_ids, config=config,
    )


# --------------------------------------------------------------------------- LP plan -----

def lp_plan_for(uid: str) -> tuple[dict, dict]:
    """Solve the LP for one user under the parity assumptions and map its plan to weights."""
    from src.multi_goal_optimizer import FinancialState, optimize_multi_goal

    profile = profiles.loc[profiles["user_id"].astype(str) == uid].iloc[0]
    user_goals = goals.loc[goals["user_id"].astype(str) == uid].copy()
    state = FinancialState(
        monthly_income=float(profile["monthly_income"]),
        essential_expenses=float(profile["monthly_expenditure"]),
        existing_emi=float(profile["monthly_emi"]),
        liquid_savings=float(profile["initial_savings"]),
        existing_investments=float(profile["initial_investment"]),
        usable_existing_investments=0.0,
        emergency_months=6.0,
        emi_income_ratio_cap=0.35,
        risk_capacity=float(profile["risk_score"]),
    )
    result = optimize_multi_goal(
        user_goals, state,
        annual_inflation=0.03, savings_return=0.0, investment_return=0.05,
        investment_risk_score=0.4, loan_annual_rate=0.12, loan_tenure_months=60,
        max_loan_per_goal=150000.0,
    )
    if result["status"] != "optimal" or result["allocations"].empty:
        return {"savings": np.zeros(5), "invest": np.zeros(5), "loan_idx": -1}, {
            "status": result["status"]}

    alloc = result["allocations"].copy()
    order = user_goals.assign(_i=np.arange(len(user_goals))).sort_values(
        "time_horizon_months")["_i"].to_numpy()
    by_goal = {gid: i for i, gid in enumerate(user_goals["goal_id"].astype(str))}
    savings = np.zeros(5)
    invest = np.zeros(5)
    for _, row in alloc.iterrows():
        idx = by_goal.get(str(row["goal_id"]))
        if idx is None or idx >= 5:
            continue
        savings[idx] = max(0.0, float(row["monthly_savings_contribution"]))
        invest[idx] = max(0.0, float(row["monthly_investment_contribution"]))
    loans = alloc["loan_principal"].astype(float).to_numpy()
    slot_for_loan = [by_goal.get(str(g)) for g in alloc["goal_id"].astype(str)]
    loan_idx = int(np.argmax(loans)) if loans.size and loans.max() > 0 else -1
    loan_slot = slot_for_loan[loan_idx] if loan_idx >= 0 else -1
    if loan_slot is not None and loan_slot >= 5:
        loan_slot = -1
    del order
    return {"savings": savings, "invest": invest, "loan_idx": loan_slot}, {
        "status": result["status"],
        "weighted_goal_achievement": float(result["summary"].get("weighted_goal_achievement", np.nan)),
        "loan_principal_total": float(loans.sum()) if loans.size else 0.0,
    }


# ------------------------------------------------------------------------ rollout --------

def role_policy(env, uid, plan, policy_name, weights):
    """Action for this month: fixed weights, urgency rule, or the LP plan."""
    action = np.zeros(env.action_space.shape, dtype=np.float32)
    n = len(env.user_goals)
    if policy_name == "Rule-based urgency (savings)":
        remaining = np.maximum(0.0, env.goal_targets - env.goal_balances)
        months_left = np.maximum(1, env.goal_deadlines - env.month_index)
        urgency = remaining / months_left
        if remaining.sum() <= 0.0:
            return action
        return_action = action
        j = int(np.argmax(urgency))
        return_action[j, 0] = 1.0
        return return_action
    if policy_name == "LP optimizer plan":
        action[:n, 0] = plan["savings"][:n]
        action[:n, 1] = plan["invest"][:n]
        if plan["loan_idx"] is not None and plan["loan_idx"] >= 0:
            action[int(plan["loan_idx"]), 2] = 1.0
        return action
    action[:, 0], action[:, 1], action[:, 2] = weights
    return action


def rollout(env, uid, policy_name, weights=(0.0, 0.0, 0.0), model=None, plan=None):
    obs, info0 = env.reset(options={"user_id": uid})
    n_goals = len(env.user_goals)
    deadline_ratio = np.full(n_goals, np.nan)
    downside = 0.0
    negative_months = 0
    violations = 0
    components = {
        "incremental_progress": 0.0, "deadline_shortfall_penalty": 0.0,
        "loan_penalty": 0.0, "risk_penalty": 0.0, "wealth_delta": 0.0,
        "terminal_net_worth": 0.0, "terminal_goal_achievement": 0.0,
    }
    reward_sum = 0.0
    max_component_residual = 0.0
    previous_month_index = -1
    while True:
        if model is not None:
            action, _ = model.predict(obs, deterministic=True)
        else:
            action = role_policy(env, uid, plan, policy_name, weights)
        obs, reward, term, trunc, info = env.step(action)
        reward_sum += float(reward)
        for key in components:
            components[key] += float(info["reward_components"].get(key, 0.0))
        max_component_residual = max(
            max_component_residual,
            abs(sum(info["reward_components"].values()) - float(reward)),
        )
        change = float(info["portfolio_market_change"])
        if change < 0.0:
            downside += -change
            negative_months += 1
        ba = info["budget_audit"]
        if abs(ba["budget_check"]) > 1e-6 or ba["cash_floor_active"]:
            violations += 1
        month = int(ba["month"])
        for j in range(n_goals):
            if month == int(env.goal_deadlines[j]) and np.isnan(deadline_ratio[j]):
                target = max(1.0, float(env.goal_targets[j]))
                deadline_ratio[j] = float(env.goal_balances[j]) / target
        previous_month_index = month
        if term or trunc:
            break

    priority = env.user_goals["priority"].astype(float).to_numpy()
    nominal = env.user_goals["current_cost"].astype(float).to_numpy()[:n_goals]
    target = env.goal_targets.astype(float)[:n_goals]
    funded = env.goal_balances.astype(float)[:n_goals]
    ratio = np.minimum(funded, target) / np.maximum(target, 1e-9)

    row = {
        "policy": policy_name,
        "user_id": uid,
        "n_goals": n_goals,
        "months": previous_month_index + 1,
        "total_reward": reward_sum,
        "max_component_residual": max_component_residual,
        "weighted_goal_achievement": float(np.sum(priority * ratio) / np.sum(priority)),
        "mean_funding_ratio": float(np.mean(ratio)),
        "pct_goals_fully_funded": float(np.mean(ratio >= 1.0 - 1e-9)),
        "pct_goals_met_by_deadline": float(np.nanmean(deadline_ratio >= 1.0 - 1e-9))
        if not np.all(np.isnan(deadline_ratio)) else np.nan,
        "goal_level_shortfall": float(np.sum(np.maximum(0.0, target - funded))),
        "funding_vs_nominal_targets": float(
            np.sum(np.minimum(funded, nominal)) / max(np.sum(nominal), 1e-9)),
        "funding_vs_inflated_targets": float(
            np.sum(np.minimum(funded, target)) / max(np.sum(target), 1e-9)),
        "final_liquid_cash": float(info["ledger"]["cash"]),
        "final_portfolio_value": float(info["ledger"]["portfolio"]),
        "outstanding_loan_balance": float(info["ledger"]["loan_balance"]),
        "net_worth": float(info["ledger"]["net_worth"]),
        "investment_gain": float(env.total_investment_gain),
        "downside_exposure": downside,
        "negative_months": negative_months,
        "total_loan_principal": float(env.cumulative_loan_principal),
        "total_interest_paid": float(env.total_interest_paid),
        "budget_violations": violations,
        "risk_score": float(env.profile_map[uid]["risk_score"]),
        "max_goal_horizon_months": int(env.goal_deadlines.max()),
    }
    row.update({f"rc_{k}": v for k, v in components.items()})
    return row


def run_block(rows, config, label, user_ids, include_lp=False, include_ppo=False):
    env = make_env(config, user_ids)
    plans = {}
    if include_lp:
        for uid in user_ids:
            plans[uid], _ = lp_plan_for(uid)
    model = None
    if include_ppo:
        from stable_baselines3 import PPO

        model = PPO.load(str(paths.ppo_best_model))
    for uid in user_ids:
        for name, weights in FIXED_POLICIES.items():
            row = rollout(env, uid, name, weights=weights)
            row["config"] = label
            rows.append(row)
        row = rollout(env, uid, "Rule-based urgency (savings)")
        row["config"] = label
        rows.append(row)
        if include_lp:
            row = rollout(env, uid, "LP optimizer plan", plan=plans[uid])
            row["config"] = label
            rows.append(row)
        if include_ppo:
            row = rollout(env, uid, "Archived PPO", model=model)
            row["config"] = label
            rows.append(row)
    return rows


def summarise(detail: pd.DataFrame) -> pd.DataFrame:
    metrics = [
        "total_reward", "weighted_goal_achievement", "mean_funding_ratio",
        "pct_goals_fully_funded", "pct_goals_met_by_deadline", "goal_level_shortfall",
        "funding_vs_nominal_targets", "funding_vs_inflated_targets",
        "final_liquid_cash", "final_portfolio_value", "outstanding_loan_balance",
        "net_worth", "investment_gain", "downside_exposure", "total_loan_principal",
        "total_interest_paid", "budget_violations", "max_component_residual",
    ]
    out = []
    for (config, policy), group in detail.groupby(["config", "policy"], sort=False):
        row = {"config": config, "policy": policy, "users": len(group)}
        for metric in metrics:
            values = group[metric].astype(float).to_numpy()
            row[f"{metric}_mean"] = float(np.nanmean(values))
            row[f"{metric}_median"] = float(np.nanmedian(values))
            row[f"{metric}_std"] = float(np.nanstd(values, ddof=1)) if len(values) > 1 else 0.0
        out.append(row)
    return pd.DataFrame(out)


def bootstrap_ci(values, n=BOOTSTRAP, seed=BOOTSTRAP_SEED):
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if values.size == 0:
        return (np.nan, np.nan)
    rng = np.random.default_rng(seed)
    means = values[rng.integers(0, values.size, size=(n, values.size))].mean(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def paired_comparisons(detail: pd.DataFrame, reference="Savings only") -> pd.DataFrame:
    rows = []
    for config in detail["config"].unique():
        block = detail[detail["config"] == config]
        ref = block[block["policy"] == reference].set_index("user_id")
        for policy in block["policy"].unique():
            if policy == reference:
                continue
            other = block[block["policy"] == policy].set_index("user_id")
            common = ref.index.intersection(other.index)
            for metric in ("weighted_goal_achievement", "net_worth",
                           "funding_vs_inflated_targets"):
                diff = (other.loc[common, metric] - ref.loc[common, metric]).astype(float).to_numpy()
                lo, hi = bootstrap_ci(diff)
                rows.append({
                    "config": config, "policy": policy, "reference": reference,
                    "metric": metric, "n_pairs": len(common),
                    "mean_paired_difference": float(np.mean(diff)),
                    "median_paired_difference": float(np.median(diff)),
                    "ci95_low": lo, "ci95_high": hi,
                    "significantly_different": bool(lo > 0.0 or hi < 0.0),
                })
    return pd.DataFrame(rows)


def main() -> dict:
    detail_rows: list[dict] = []

    # ---- Phase E + H: every preset, all fixed policies, plus LP and the archived PPO ----
    run_block(detail_rows, PRESETS["archived"](), "archived", TEST_USERS, include_ppo=True)
    run_block(detail_rows, PRESETS["corrected_accounting"](), "corrected_accounting",
              TEST_USERS)
    run_block(detail_rows, PRESETS["lp_parity"](), "lp_parity", TEST_USERS, include_lp=True)
    run_block(detail_rows, PRESETS["recommended"](), "recommended", TEST_USERS, include_lp=True)
    detail = pd.DataFrame(detail_rows)
    detail.to_csv(EVAL_OUT / "policy_metrics_v1.csv", index=False)
    summary = summarise(detail)
    summary.to_csv(EVAL_OUT / "policy_summary_v1.csv", index=False)

    # ---- Phase D: reward decomposition and candidate-reward comparison ------------------
    reward_rows: list[dict] = []
    for version, label in ((REWARD_VERSION_A, "candidate_a"), (REWARD_VERSION_B, "candidate_b")):
        cfg = PRESETS["recommended"]().replace(reward_version=version)
        env = make_env(cfg, TEST_USERS)
        for uid in TEST_USERS:
            for name, weights in FIXED_POLICIES.items():
                row = rollout(env, uid, name, weights=weights)
                row["reward_version"] = label
                reward_rows.append(row)
    baseline_rows = []
    env = make_env(PRESETS["recommended"](), TEST_USERS)
    for uid in TEST_USERS:
        for name, weights in FIXED_POLICIES.items():
            row = rollout(env, uid, name, weights=weights)
            row["reward_version"] = "archived_v1"
            baseline_rows.append(row)
    reward_detail = pd.DataFrame(baseline_rows + reward_rows)
    reward_detail.to_csv(REWARD_OUT / "reward_detail_by_policy_v1.csv", index=False)

    component_cols = [c for c in reward_detail.columns if c.startswith("rc_")]
    reward_summary = (
        reward_detail.groupby(["reward_version", "policy"], sort=False)[
            ["total_reward", "max_component_residual"] + component_cols
        ].mean().reset_index()
    )
    reward_summary.to_csv(REWARD_OUT / "reward_version_comparison_v1.csv", index=False)
    outcome_cols = ["weighted_goal_achievement", "pct_goals_fully_funded",
                    "pct_goals_met_by_deadline", "net_worth", "total_interest_paid",
                    "total_loan_principal", "downside_exposure"]
    (reward_detail.groupby(["reward_version", "policy"], sort=False)[outcome_cols]
     .mean().reset_index()
     .to_csv(REWARD_OUT / "reward_version_outcomes_v1.csv", index=False))

    # ---- Phase E: explicit comparability table -----------------------------------------
    comparability = summary[[
        "config", "policy", "users",
        "funding_vs_nominal_targets_mean", "funding_vs_inflated_targets_mean",
        "weighted_goal_achievement_mean", "net_worth_mean",
        "outstanding_loan_balance_mean", "total_interest_paid_mean",
    ]].copy()
    comparability.to_csv(EVAL_OUT / "lp_rl_comparability_v1.csv", index=False)

    # ---- Phase H: dispersion, CIs and paired comparisons -------------------------------
    dispersion_rows = []
    for (config, policy), group in detail.groupby(["config", "policy"], sort=False):
        for metric in ("weighted_goal_achievement", "net_worth", "funding_vs_inflated_targets"):
            values = group[metric].astype(float).to_numpy()
            lo, hi = bootstrap_ci(values)
            dispersion_rows.append({
                "config": config, "policy": policy, "metric": metric, "users": len(values),
                "mean": float(np.mean(values)), "median": float(np.median(values)),
                "std": float(np.std(values, ddof=1)) if len(values) > 1 else 0.0,
                "p10": float(np.percentile(values, 10)), "p90": float(np.percentile(values, 90)),
                "ci95_low": lo, "ci95_high": hi,
            })
    dispersion = pd.DataFrame(dispersion_rows)
    dispersion.to_csv(EVAL_OUT / "policy_dispersion_v1.csv", index=False)
    paired = paired_comparisons(detail)
    paired.to_csv(EVAL_OUT / "paired_comparisons_v1.csv", index=False)

    # ---- risk groups and goal horizons --------------------------------------------------
    detail["risk_group"] = pd.cut(detail["risk_score"], bins=[-0.01, 0.33, 0.66, 1.01],
                                  labels=["low", "mid", "high"])
    detail["horizon_group"] = pd.cut(detail["max_goal_horizon_months"],
                                     bins=[0, 36, 84, 10000],
                                     labels=["short<=3y", "medium<=7y", "long>7y"])
    by_risk = (detail.groupby(["config", "policy", "risk_group"], observed=True)[
        ["weighted_goal_achievement", "net_worth"]].mean().reset_index())
    by_risk.to_csv(EVAL_OUT / "policy_by_risk_group_v1.csv", index=False)
    by_horizon = (detail.groupby(["config", "policy", "horizon_group"], observed=True)[
        ["weighted_goal_achievement", "net_worth"]].mean().reset_index())
    by_horizon.to_csv(EVAL_OUT / "policy_by_goal_horizon_v1.csv", index=False)

    a = paired[(paired["policy"] == "LP optimizer plan")]
    summary_json = {
        "configs": list(PRESETS),
        "heldout_users": len(TEST_USERS),
        "train_users": len(TRAIN_USERS),
        "reward_versions_evaluated": ["archived_v1", "candidate_a", "candidate_b"],
        "max_component_residual": float(detail["max_component_residual"].max()),
        "budget_violations_total": int(detail["budget_violations"].sum()),
        "lp_vs_savings_only": a.to_dict("records"),
        "note": (
            "The LP column is the optimizer's one-shot plan mapped onto the environment's "
            "monthly share weights; the environment still enforces its own EMI cap and "
            "max_new_loan, so the LP plan can be truncated. The archived PPO checkpoint is "
            "only valid under archived semantics and is reported only for the archived preset."
        ),
    }
    del a
    (EVAL_OUT / "evaluation_summary_v1.json").write_text(
        json.dumps(summary_json, indent=2, default=str), encoding="utf-8")
    return summary_json


if __name__ == "__main__":
    result = main()
    print(json.dumps({
        "users": result["heldout_users"],
        "max_component_residual": result["max_component_residual"],
        "budget_violations_total": result["budget_violations_total"],
        "configs": result["configs"],
    }, indent=2))
