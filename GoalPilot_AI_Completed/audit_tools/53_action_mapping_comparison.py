"""Fixed-policy comparison of the `share` mapping against the new `mix` mapping.

Same users, same market path, same goal definitions, same everything except
`action_mode`. RL arms are deliberately **excluded**: the action semantics change what an action
means, so no existing checkpoint is compatible (see the design doc, section 8).

Sequences are generated from the simulator's own remaining-need signal, which is a diagnostic
reference, not a deployable policy - it reads the exact remaining need with no uncertainty.

Writes `outputs/evaluation/final_validation_v4/action_mapping_*.csv`.
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

OUT_DIR = paths.root / "outputs" / "evaluation" / "final_validation_v4"
OUT_DIR.mkdir(parents=True, exist_ok=True)

profiles = pd.read_csv(paths.rl_profiles_csv)
goals = pd.read_csv(paths.rl_goals_csv)
market = pd.read_csv(paths.rl_market_csv)
FRESH_TEST = json.loads(
    (paths.root / "training_logs" / "experiments" / "fresh_split_v1"
     / "fresh_split_v1_manifest.json").read_text(encoding="utf-8"))["test_users"]

POLICIES = ["uniform savings", "uniform investment", "uniform 50/50",
            "need-proportional savings", "need-proportional investment",
            "need-proportional both", "urgency", "LP plan"]


def lp_plans(users):
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
            emi_income_ratio_cap=0.35, risk_capacity=float(p["risk_score"]))
        res = optimize_multi_goal(
            g, state, annual_inflation=0.03, savings_return=0.0, investment_return=0.05,
            investment_risk_score=0.4, loan_annual_rate=0.12, loan_tenure_months=60,
            max_loan_per_goal=150000.0)
        slot = {gid: i for i, gid in enumerate(g["goal_id"].astype(str))}
        sav, inv, loan_slot, best = np.zeros(5), np.zeros(5), -1, 0.0
        if res["status"] == "optimal" and not res["allocations"].empty:
            for _, row in res["allocations"].iterrows():
                i = slot.get(str(row["goal_id"]))
                if i is None or i >= 5:
                    continue
                sav[i] = max(0.0, float(row["monthly_savings_contribution"]))
                inv[i] = max(0.0, float(row["monthly_investment_contribution"]))
                if float(row["loan_principal"]) > best:
                    best, loan_slot = float(row["loan_principal"]), i
        out[uid] = {"savings": sav, "invest": inv, "loan_slot": loan_slot}
    return out


def action_for(env, policy, plan):
    n = len(env.user_goals)
    a = np.zeros(env.action_space.shape, dtype=np.float32)
    need = np.maximum(0.0, env.goal_targets - env.goal_balances)[:n]
    total = float(need.sum())
    if policy == "uniform savings":
        a[:n, 0] = 1.0
    elif policy == "uniform investment":
        a[:n, 1] = 1.0
    elif policy == "uniform 50/50":
        a[:n, 0], a[:n, 1] = 0.5, 0.5
    elif policy == "need-proportional savings" and total > 0:
        a[:n, 0] = need / total
    elif policy == "need-proportional investment" and total > 0:
        a[:n, 1] = need / total
    elif policy == "need-proportional both" and total > 0:
        a[:n, 0], a[:n, 1] = need / total, need / total
    elif policy == "urgency" and total > 0:
        months = np.maximum(1, env.goal_deadlines[:n] - env.month_index)
        a[int(np.argmax(need / months)), 0] = 1.0
    elif policy == "LP plan" and plan is not None:
        a[:n, 0] = plan["savings"][:n]
        a[:n, 1] = plan["invest"][:n]
        if plan["loan_slot"] >= 0:
            a[int(plan["loan_slot"]), 2] = 1.0
    return a


def run(env, uid, policy, plan) -> dict:
    obs, _ = env.reset(options={"user_id": uid})
    n = len(env.user_goals)
    targets = env.goal_targets.astype(float)[:n]
    deadlines = env.goal_deadlines[:n].astype(int)
    met = np.zeros(n, dtype=bool)
    seen = np.zeros(n, dtype=bool)
    savings = invest = idle = inv_cap_idle = budget = 0.0
    downside = 0.0
    violations = 0
    while True:
        obs, _, term, trunc, info = env.step(action_for(env, policy, plan))
        just = int(env.month_index)
        ratio = env.goal_balances[:n] / np.maximum(targets, 1e-9)
        for j in range(n):
            if deadlines[j] == just:
                seen[j] = True
                met[j] = ratio[j] >= 1.0 - 1e-9
        ba = info["budget_audit"]
        savings += ba["savings_contribution"]
        invest += ba["investment_contribution"]
        idle += ba["unallocated_surplus"]
        inv_cap_idle += ba["unallocated_from_investment_cap"]
        budget += ba["discretionary_budget"]
        downside += min(0.0, float(info["investment_gain"]))
        violations += int(bool(ba["cash_floor_active"])) + int(ba["interest_shortfall"] > 1e-9)
        if term or trunc:
            break
    funded = env.goal_balances[:n]
    r = np.minimum(funded, targets) / np.maximum(targets, 1e-9)
    pri = env.user_goals["priority"].astype(float).to_numpy()[:n]
    return {
        "user_id": uid, "policy": policy,
        "savings_amount": savings, "investment_amount": invest,
        "budget_total": budget,
        "idle_fraction": idle / max(budget, 1e-9),
        "idle_from_investment_cap": inv_cap_idle,
        "weighted_goal_achievement": float(np.sum(pri * r) / np.sum(pri)),
        "pct_goals_fully_funded": float(np.mean(r >= 1.0 - 1e-9)),
        "pct_goals_met_by_deadline": float(met.sum() / seen.sum()) if seen.any() else np.nan,
        "goal_level_shortfall": float(np.sum(np.maximum(0.0, targets - funded))),
        "net_worth": float(env.net_worth),
        "borrowing": float(env.cumulative_loan_principal),
        "interest_paid": float(env.total_interest_paid),
        "risk_downside_exposure": downside,
        "affordability_violations": float(violations),
    }


def main() -> None:
    plans = lp_plans(FRESH_TEST)
    rows = []
    for label, cfg in (("share", GoalPilotConfig.recommended()),
                       ("mix", GoalPilotConfig.with_action_mix())):
        env = goalpilot_env.GoalPilotEnv(profiles=profiles, goals=goals, market=market,
                                         user_ids=FRESH_TEST, config=cfg)
        for policy in POLICIES:
            for uid in FRESH_TEST:
                r = run(env, uid, policy, plans.get(uid))
                r["action_mode"] = label
                rows.append(r)
        env.close()

    detail = pd.DataFrame(rows)
    detail.to_csv(OUT_DIR / "action_mapping_metrics_v1.csv", index=False)
    metrics = ["savings_amount", "investment_amount", "idle_fraction",
               "idle_from_investment_cap", "weighted_goal_achievement",
               "pct_goals_fully_funded", "pct_goals_met_by_deadline",
               "goal_level_shortfall", "net_worth", "borrowing", "interest_paid",
               "risk_downside_exposure", "affordability_violations"]
    summary = detail.groupby(["action_mode", "policy"])[metrics].mean().reset_index()
    summary.to_csv(OUT_DIR / "action_mapping_summary_v1.csv", index=False)

    # paired per user: does the mapping change the allocation at all?
    deltas = []
    for policy in POLICIES:
        a = detail[(detail["action_mode"] == "share") & (detail["policy"] == policy)
                   ].set_index("user_id")
        b = detail[(detail["action_mode"] == "mix") & (detail["policy"] == policy)
                   ].set_index("user_id")
        common = a.index.intersection(b.index)
        inv_moved = (b.loc[common, "investment_amount"]
                     - a.loc[common, "investment_amount"]).abs() > 1e-6
        sav_moved = (b.loc[common, "savings_amount"]
                     - a.loc[common, "savings_amount"]).abs() > 1e-6
        ach = b.loc[common, "weighted_goal_achievement"] - a.loc[common,
                                                                 "weighted_goal_achievement"]
        deltas.append({
            "policy": policy, "users": len(common),
            "users_with_different_investment": int(inv_moved.sum()),
            "users_with_different_savings": int(sav_moved.sum()),
            "achievement_share": float(a.loc[common, "weighted_goal_achievement"].mean()),
            "achievement_mix": float(b.loc[common, "weighted_goal_achievement"].mean()),
            "delta_achievement": float(ach.mean()),
            "users_improved": int((ach > 1e-9).sum()),
            "users_worsened": int((ach < -1e-9).sum()),
            "idle_share": float(a.loc[common, "idle_fraction"].mean()),
            "idle_mix": float(b.loc[common, "idle_fraction"].mean()),
        })
    deltas_df = pd.DataFrame(deltas)
    deltas_df.to_csv(OUT_DIR / "action_mapping_deltas_v1.csv", index=False)

    print(json.dumps({
        "fresh_test_users": len(FRESH_TEST),
        "total_affordability_violations": float(detail["affordability_violations"].sum()),
        "summary": summary.round(4).to_dict("records"),
        "deltas": deltas_df.round(4).to_dict("records"),
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
