"""Measure what the opt-in R-13 fix changes, on the same users and policies.

Runs each strategy twice - under `GoalPilotConfig.recommended()` (flag off, the published
behaviour) and under `GoalPilotConfig.with_reallocation()` (flag on) - so the effect of
reallocating cap-released budget is isolated. Nothing else differs between the two runs.

Writes `outputs/evaluation/final_validation_v2/reallocation_impact.csv`.
"""
from __future__ import annotations

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

OUT_DIR = paths.root / "outputs" / "evaluation" / "final_validation_v2"
OUT_DIR.mkdir(parents=True, exist_ok=True)

profiles = pd.read_csv(paths.rl_profiles_csv)
goals = pd.read_csv(paths.rl_goals_csv)
market = pd.read_csv(paths.rl_market_csv)
split = pd.read_csv(paths.rl_split_csv)
_col = next(c for c in ("split", "set", "subset", "is_test") if c in split.columns)
old_test = split.loc[split[_col].astype(str).str.lower() == "test", "user_id"].astype(str).tolist()


def eligible() -> list[str]:
    out = []
    for uid in old_test:
        p = profiles.loc[profiles["user_id"].astype(str) == uid].iloc[0]
        if float(p["monthly_income"]) - float(p["monthly_expenditure"]) - float(p["monthly_emi"]) > 0:
            out.append(uid)
    return out


def lp_plans() -> dict:
    from src.multi_goal_optimizer import FinancialState, optimize_multi_goal
    out = {}
    for uid in old_test:
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


def act(env, policy, plan):
    n = len(env.user_goals)
    a = np.zeros(env.action_space.shape, dtype=np.float32)
    need = np.maximum(0.0, env.goal_targets - env.goal_balances)
    if policy == "Savings only":
        a[:, 0] = 1.0
    elif policy == "Investments only":
        a[:, 1] = 1.0
    elif policy == "Mixed (0.50/0.50)":
        a[:, 0], a[:, 1] = 0.5, 0.5
    elif policy == "Rule-based urgency" and need.sum() > 0:
        months = np.maximum(1, env.goal_deadlines - env.month_index)
        a[int(np.argmax(need / months)), 0] = 1.0
    elif policy == "LP optimizer plan" and plan is not None:
        a[:n, 0] = plan["savings"][:n]
        a[:n, 1] = plan["invest"][:n]
        if plan["loan_slot"] >= 0:
            a[int(plan["loan_slot"]), 2] = 1.0
    return a


def main() -> None:
    users = eligible()
    plans = lp_plans()
    policies = ["Savings only", "Investments only", "Mixed (0.50/0.50)", "Rule-based urgency",
                "LP optimizer plan"]
    rows = []
    for label, cfg in (("flag_off_recommended", GoalPilotConfig.recommended()),
                       ("flag_on_with_reallocation", GoalPilotConfig.with_reallocation())):
        env = goalpilot_env.GoalPilotEnv(profiles=profiles, goals=goals, market=market,
                                         user_ids=users, config=cfg)
        for uid in users:
            for policy in policies:
                obs, _ = env.reset(options={"user_id": uid})
                budget = alloc = idle = moved = 0.0
                while True:
                    a = act(env, policy, plans.get(uid))
                    obs, _, term, trunc, info = env.step(a)
                    ba = info["budget_audit"]
                    budget += ba["discretionary_budget"]
                    alloc += ba["savings_contribution"] + ba["investment_contribution"]
                    idle += ba["unallocated_surplus"]
                    moved += ba["reallocated_from_cap"]
                    if term or trunc:
                        break
                n = len(env.user_goals)
                pri = env.user_goals["priority"].astype(float).to_numpy()
                target = env.goal_targets.astype(float)[:n]
                funded = env.goal_balances.astype(float)[:n]
                ratio = np.minimum(funded, target) / np.maximum(target, 1e-9)
                rows.append({
                    "config": label, "policy": policy, "user_id": uid,
                    "weighted_achievement": float(np.sum(pri * ratio) / np.sum(pri)),
                    "pct_goals_fully_funded": float(np.mean(ratio >= 1.0 - 1e-9)),
                    "pct_goals_met_by_deadline": float("nan"),
                    "funded_total": float(np.sum(funded)),
                    "target_total": float(np.sum(target)),
                    "idle_fraction": idle / max(budget, 1e-9),
                    "allocated_fraction": alloc / max(budget, 1e-9),
                    "reallocated_total": moved,
                    "net_worth": float(env.net_worth),
                    "interest_paid": float(env.total_interest_paid),
                    "loan_principal": float(env.cumulative_loan_principal),
                    "portfolio": float(env.portfolio),
                })
    detail = pd.DataFrame(rows)
    detail.to_csv(OUT_DIR / "reallocation_impact.csv", index=False)
    summary = detail.groupby(["config", "policy"])[[
        "weighted_achievement", "pct_goals_fully_funded", "funded_total", "idle_fraction",
        "allocated_fraction", "reallocated_total", "net_worth", "interest_paid",
        "loan_principal", "portfolio"]].mean().reset_index()
    summary.to_csv(OUT_DIR / "reallocation_impact_summary.csv", index=False)

    # paired deltas per policy, on identical users
    deltas = []
    for policy in policies:
        off = detail[(detail["config"] == "flag_off_recommended")
                     & (detail["policy"] == policy)].set_index("user_id")
        on = detail[(detail["config"] == "flag_on_with_reallocation")
                    & (detail["policy"] == policy)].set_index("user_id")
        common = off.index.intersection(on.index)
        d = (on.loc[common, "weighted_achievement"] - off.loc[common, "weighted_achievement"])
        deltas.append({
            "policy": policy, "users": len(common),
            "achievement_flag_off": float(off.loc[common, "weighted_achievement"].mean()),
            "achievement_flag_on": float(on.loc[common, "weighted_achievement"].mean()),
            "delta_achievement": float(d.mean()),
            "idle_flag_off": float(off.loc[common, "idle_fraction"].mean()),
            "idle_flag_on": float(on.loc[common, "idle_fraction"].mean()),
            "users_improved": int((d > 1e-9).sum()),
            "users_worsened": int((d < -1e-9).sum()),
        })
    pd.DataFrame(deltas).to_csv(OUT_DIR / "reallocation_impact_deltas.csv", index=False)
    print(json.dumps({"eligible_users": len(users),
                      "deltas": deltas}, indent=2, default=str))


if __name__ == "__main__":
    main()
