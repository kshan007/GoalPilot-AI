"""P4 - fair baseline set: rules, LP and RL on one footing.

Replaces the defective `Rule-based urgency` baseline as the reference, keeping it in the table
for the record. Everything runs on the **fresh** test users (the uncontaminated partition from
`fresh_split_v1`), under one configuration, over one market path, with the full metric list and
a user-level bootstrap CI on achievement.

Two environment blocks:
    recommended()          - flag off; this is what every RL checkpoint was trained under
    with_reallocation()    - the opt-in R-13 fix; deterministic arms only, since no RL checkpoint
                             exists for it yet. Labelled, never mixed into the first block.

Writes `outputs/evaluation/final_validation_v3/fair_baselines_*.csv`.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from goalpilot_paths import ProjectPaths  # noqa: E402

paths = ProjectPaths.resolve()
paths.add_to_sys_path()
sys.path.insert(0, str(paths.root / "GoalPilot_MultiGoal_Extension"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import goalpilot_env  # noqa: E402
from goalpilot_config import GoalPilotConfig  # noqa: E402

_spec = importlib.util.spec_from_file_location("exp60", ROOT / "audit_tools" / "60_fresh_split_experiment.py")
exp60 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(exp60)

OUT_DIR = paths.root / "outputs" / "evaluation" / "final_validation_v3"
OUT_DIR.mkdir(parents=True, exist_ok=True)

profiles = pd.read_csv(paths.rl_profiles_csv)
goals = pd.read_csv(paths.rl_goals_csv)
market = pd.read_csv(paths.rl_market_csv)
FRESH_TEST = json.loads(
    (paths.root / "training_logs" / "experiments" / "fresh_split_v1"
     / "fresh_split_v1_manifest.json").read_text(encoding="utf-8"))["test_users"]

RULE_POLICIES = [
    "Rule: uniform savings", "Rule: uniform investment", "Rule: uniform 50/50",
    "Rule: need-proportional savings", "Rule: need-proportional investment",
    "Rule: need-proportional both", "Rule: urgency (known-defective)",
    "LP optimizer plan",
]
RL_LABELS = ["candidate_a", "archived_v1"]
RL_SEEDS = [7, 17, 27]


def surplus_of(uid: str) -> float:
    p = profiles.loc[profiles["user_id"].astype(str) == uid].iloc[0]
    return (float(p["monthly_income"]) - float(p["monthly_expenditure"])
            - float(p["monthly_emi"]))


ELIGIBLE = [u for u in FRESH_TEST if surplus_of(u) > 0.0]


def lp_plans(users) -> dict:
    from src.multi_goal_optimizer import FinancialState, optimize_multi_goal
    out = {}
    for uid in users:
        p = profiles.loc[profiles["user_id"].astype(str) == uid].iloc[0]
        g = goals.loc[goals["user_id"].astype(str) == uid].copy()
        state = FinancialState(
            monthly_income=float(p["monthly_income"]),
            essential_expenses=float(p["monthly_expenditure"]),
            existing_emi=float(p["monthly_emi"]),
            liquid_savings=float(p["initial_savings"]),
            existing_investments=float(p["initial_investment"]),
            usable_existing_investments=0.0, emergency_months=6.0,
            emi_income_ratio_cap=0.35, risk_capacity=float(p["risk_score"]),
        )
        res = optimize_multi_goal(
            g, state, annual_inflation=0.03, savings_return=0.0, investment_return=0.05,
            investment_risk_score=0.4, loan_annual_rate=0.12, loan_tenure_months=60,
            max_loan_per_goal=150000.0,
        )
        slot = {gid: i for i, gid in enumerate(g["goal_id"].astype(str))}
        savings, invest, loan_slot, best = np.zeros(5), np.zeros(5), -1, 0.0
        if res["status"] == "optimal" and not res["allocations"].empty:
            for _, row in res["allocations"].iterrows():
                i = slot.get(str(row["goal_id"]))
                if i is None or i >= 5:
                    continue
                savings[i] = max(0.0, float(row["monthly_savings_contribution"]))
                invest[i] = max(0.0, float(row["monthly_investment_contribution"]))
                if float(row["loan_principal"]) > best:
                    best, loan_slot = float(row["loan_principal"]), i
        out[uid] = {"savings": savings, "invest": invest, "loan_slot": loan_slot}
    return out


def rule_action(env, policy: str, plan) -> np.ndarray:
    n = len(env.user_goals)
    a = np.zeros(env.action_space.shape, dtype=np.float32)
    need = np.maximum(0.0, env.goal_targets - env.goal_balances)[:n]
    total = float(need.sum())
    if policy == "Rule: uniform savings":
        a[:n, 0] = 1.0
    elif policy == "Rule: uniform investment":
        a[:n, 1] = 1.0
    elif policy == "Rule: uniform 50/50":
        a[:n, 0], a[:n, 1] = 0.5, 0.5
    elif policy == "Rule: need-proportional savings" and total > 0:
        a[:n, 0] = need / total
    elif policy == "Rule: need-proportional investment" and total > 0:
        a[:n, 1] = need / total
    elif policy == "Rule: need-proportional both" and total > 0:
        a[:n, 0], a[:n, 1] = need / total, need / total
    elif policy == "Rule: urgency (known-defective)" and total > 0:
        months = np.maximum(1, env.goal_deadlines[:n] - env.month_index)
        a[int(np.argmax(need / months)), 0] = 1.0
    elif policy == "LP optimizer plan" and plan is not None:
        a[:n, 0] = plan["savings"][:n]
        a[:n, 1] = plan["invest"][:n]
        if plan["loan_slot"] >= 0:
            a[int(plan["loan_slot"]), 2] = 1.0
    return a


def rollout(env, uid, policy, plan, model) -> dict:
    obs, _ = env.reset(options={"user_id": uid})
    n = len(env.user_goals)
    target_full = env.goal_targets.astype(float)[:n]
    deadlines = env.goal_deadlines[:n].astype(int)
    met = np.zeros(n, dtype=bool)
    seen = np.zeros(n, dtype=bool)
    downside = 0.0
    violations = 0
    while True:
        if model is not None:
            action, _ = model.predict(obs, deterministic=True)
        else:
            action = rule_action(env, policy, plan)
        obs, _, term, trunc, info = env.step(action)
        just = int(env.month_index)          # 1-based month just completed
        ratio_now = env.goal_balances[:n] / np.maximum(target_full, 1e-9)
        for j in range(n):
            if deadlines[j] == just:
                seen[j] = True
                met[j] = ratio_now[j] >= 1.0 - 1e-9
        ba = info["budget_audit"]
        downside += min(0.0, float(info["investment_gain"]))
        violations += int(bool(ba["cash_floor_active"])) + int(ba["interest_shortfall"] > 1e-9)
        if term or trunc:
            break
    funded = env.goal_balances[:n]
    ratio = np.minimum(funded, target_full) / np.maximum(target_full, 1e-9)
    pri = env.user_goals["priority"].astype(float).to_numpy()[:n]
    return {
        "user_id": uid, "policy": policy,
        "weighted_goal_achievement": float(np.sum(pri * ratio) / np.sum(pri)),
        "pct_goals_fully_funded": float(np.mean(ratio >= 1.0 - 1e-9)),
        "pct_goals_met_by_deadline": (float(met.sum() / seen.sum()) if seen.any() else np.nan),
        "goal_level_shortfall": float(np.sum(np.maximum(0.0, target_full - funded))),
        "final_liquid_cash": float(env.cash), "final_portfolio_value": float(env.portfolio),
        "net_worth": float(env.net_worth),
        "outstanding_loan_balance": float(env.loan_balance),
        "total_loan_principal": float(env.cumulative_loan_principal),
        "total_interest_paid": float(env.total_interest_paid),
        "investment_gain": float(env.total_investment_gain),
        "downside_exposure": float(downside),
        "affordability_violations": float(violations),
    }


def boot_ci(values: np.ndarray, n=10000, seed=20261011):
    rng = np.random.default_rng(seed)
    draws = values[rng.integers(0, values.size, size=(n, values.size))].mean(axis=1)
    return float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))


def main() -> None:
    plans = lp_plans(FRESH_TEST)
    rows = []
    for label, cfg, use_rl in (
        ("flag_off_recommended", GoalPilotConfig.recommended(), True),
        ("flag_on_with_reallocation", GoalPilotConfig.with_reallocation(), False),
    ):
        env = goalpilot_env.GoalPilotEnv(profiles=profiles, goals=goals, market=market,
                                         user_ids=FRESH_TEST, config=cfg)
        for policy in RULE_POLICIES:
            for uid in FRESH_TEST:
                r = rollout(env, uid, policy, plans.get(uid), None)
                r["config"] = label
                rows.append(r)
        if use_rl:
            for arm in RL_LABELS:
                for seed in RL_SEEDS:
                    from stable_baselines3 import PPO
                    ckpt = (paths.root / "training_logs" / "experiments" / "fresh_split_v1"
                            / arm / f"ppo_{arm}_seed{seed}.zip")
                    model = PPO.load(str(ckpt))
                    for uid in FRESH_TEST:
                        r = rollout(env, uid, f"RL {arm} seed{seed}", None, model)
                        r["config"] = label
                        rows.append(r)
        env.close()

    detail = pd.DataFrame(rows)
    detail["feasibility_cohort"] = np.where(
        detail["user_id"].isin(ELIGIBLE), "surplus>0", "zero surplus")
    detail.to_csv(OUT_DIR / "fair_baselines_metrics_v1.csv", index=False)

    metrics = ["weighted_goal_achievement", "pct_goals_fully_funded",
               "pct_goals_met_by_deadline", "goal_level_shortfall", "final_liquid_cash",
               "final_portfolio_value", "net_worth", "outstanding_loan_balance",
               "total_loan_principal", "total_interest_paid", "investment_gain",
               "downside_exposure", "affordability_violations"]
    summary = (detail.groupby(["config", "policy"])[metrics].mean().reset_index())
    ci = []
    for (cfg, pol), grp in detail.groupby(["config", "policy"]):
        sub = grp[grp["user_id"].isin(ELIGIBLE)]["weighted_goal_achievement"].to_numpy()
        lo, hi = boot_ci(sub)
        ci.append({"config": cfg, "policy": pol, "eligible_users": int(sub.size),
                   "achievement_mean": float(sub.mean()),
                   "ci95_low": lo, "ci95_high": hi, "sd_across_users": float(sub.std(ddof=1))})
    summary.to_csv(OUT_DIR / "fair_baselines_summary_v1.csv", index=False)
    pd.DataFrame(ci).to_csv(OUT_DIR / "fair_baselines_uncertainty_v1.csv", index=False)
    cohort = detail.groupby(["config", "policy", "feasibility_cohort"])[
        ["weighted_goal_achievement", "goal_level_shortfall", "net_worth"]].mean().reset_index()
    cohort.to_csv(OUT_DIR / "fair_baselines_by_cohort_v1.csv", index=False)

    ranked = (summary[summary["config"] == "flag_off_recommended"]
              .sort_values("weighted_goal_achievement", ascending=False))
    print(json.dumps({
        "fresh_test_users": len(FRESH_TEST), "eligibility_eligible": len(ELIGIBLE),
        "total_affordability_violations": float(detail["affordability_violations"].sum()),
        "ranking_flag_off": ranked[["policy", "weighted_goal_achievement",
                                    "pct_goals_fully_funded", "pct_goals_met_by_deadline",
                                    "net_worth", "downside_exposure",
                                    "total_interest_paid"]].round(4).to_dict("records"),
        "uncertainty_eligible": pd.DataFrame(ci).round(4).to_dict("records"),
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
