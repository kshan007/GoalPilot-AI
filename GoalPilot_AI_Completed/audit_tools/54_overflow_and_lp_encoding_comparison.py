"""Fixed-policy comparison: LP encoding for `mix`, and the two investment-overflow modes.

Arms (all on the same fresh test users, same goal definitions, same market path):

    A  reference              share + legacy overflow  (= every published result)
    B  mix                    mix + legacy overflow    (== mix + retain_as_cash, pinned)
    C  share + retain_as_cash
    D  share + redirect_to_savings
    E  mix   + redirect_to_savings
    D2 share + redirect_to_savings + R-13
    E2 mix   + redirect_to_savings + R-13

The LP arm uses the new `goalpilot_lp_encoder` instead of pasting absolute rupees into the
weights, and the implied scale (`available_budget / plan_total`) is recorded per user so the
structural deviation of a partially-allocating plan is visible rather than hidden.

Writes `outputs/evaluation/final_validation_v5/`.
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
from goalpilot_config import (  # noqa: E402
    INVESTMENT_OVERFLOW_REDIRECT_TO_SAVINGS,
    INVESTMENT_OVERFLOW_RETAIN_AS_CASH,
    GoalPilotConfig,
)
from goalpilot_lp_encoder import encode_lp_plan_for_mix  # noqa: E402

OUT_DIR = paths.root / "outputs" / "evaluation" / "final_validation_v5"
OUT_DIR.mkdir(parents=True, exist_ok=True)

profiles = pd.read_csv(paths.rl_profiles_csv)
goals = pd.read_csv(paths.rl_goals_csv)
market = pd.read_csv(paths.rl_market_csv)
FRESH_TEST = json.loads(
    (paths.root / "training_logs" / "experiments" / "fresh_split_v1"
     / "fresh_split_v1_manifest.json").read_text(encoding="utf-8"))["test_users"]

POLICIES = ["uniform savings", "need-proportional savings", "investment-only",
            "mixed allocation", "urgency", "LP (encoded for mix)"]

WSHARE = GoalPilotConfig.recommended()
WMIX = GoalPilotConfig.with_action_mix()
ARMS = [
    ("A_reference_share_legacy", WSHARE),
    ("B_mix_legacy", WMIX),
    ("C_share_retain_as_cash", WSHARE.replace(
        investment_overflow_policy=INVESTMENT_OVERFLOW_RETAIN_AS_CASH)),
    ("D_share_redirect_to_savings", WSHARE.replace(
        investment_overflow_policy=INVESTMENT_OVERFLOW_REDIRECT_TO_SAVINGS)),
    ("E_mix_redirect_to_savings", WMIX.replace(
        investment_overflow_policy=INVESTMENT_OVERFLOW_REDIRECT_TO_SAVINGS)),
    ("D2_share_redirect_R13", WSHARE.replace(
        investment_overflow_policy=INVESTMENT_OVERFLOW_REDIRECT_TO_SAVINGS,
        reallocate_capped_budget=True)),
    ("E2_mix_redirect_R13", WMIX.replace(
        investment_overflow_policy=INVESTMENT_OVERFLOW_REDIRECT_TO_SAVINGS,
        reallocate_capped_budget=True)),
]


def lp_plan(uid: str):
    from src.multi_goal_optimizer import FinancialState, optimize_multi_goal
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
    if res["status"] != "optimal" or res["allocations"].empty:
        return None
    alloc = res["allocations"]
    sav = np.zeros(5)
    inv = np.zeros(5)
    slot = {gid: i for i, gid in enumerate(g["goal_id"].astype(str))}
    for _, row in alloc.iterrows():
        i = slot.get(str(row["goal_id"]))
        if i is None or i >= 5:
            continue
        sav[i] = max(0.0, float(row["monthly_savings_contribution"]))
        inv[i] = max(0.0, float(row["monthly_investment_contribution"]))
    enc = encode_lp_plan_for_mix(sav, inv, n_slots=5)
    loan_slot = -1
    if "loan_principal" in alloc.columns:
        best = 0.0
        for _, row in alloc.iterrows():
            i = slot.get(str(row["goal_id"]))
            if i is not None and i < 5 and float(row["loan_principal"]) > best:
                best, loan_slot = float(row["loan_principal"]), i
    return {"action": enc["action"], "encoded": enc, "loan_slot": loan_slot}


def action_for(env, policy, plan):
    n = len(env.user_goals)
    a = np.zeros(env.action_space.shape, dtype=np.float32)
    need = np.maximum(0.0, env.goal_targets - env.goal_balances)[:n]
    total = float(need.sum())
    if policy == "uniform savings":
        a[:n, 0] = 1.0
    elif policy == "need-proportional savings" and total > 0:
        a[:n, 0] = need / total
    elif policy == "investment-only":
        a[:n, 1] = 1.0
    elif policy == "mixed allocation":
        a[:n, 0], a[:n, 1] = 0.5, 0.5
    elif policy == "urgency" and total > 0:
        months = np.maximum(1, env.goal_deadlines[:n] - env.month_index)
        a[int(np.argmax(need / months)), 0] = 1.0
    elif policy == "LP (encoded for mix)" and plan is not None:
        a = plan["action"].copy()
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
    savings = invest = idle = overflow = redirected = retained = budget = 0.0
    violations = 0
    while True:
        action = action_for(env, policy, plan)
        obs, _, term, trunc, info = env.step(action)
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
        overflow += ba["invest_overflow"]
        redirected += ba["overflow_redirected_to_savings"]
        retained += ba["overflow_retained_as_cash"]
        budget += ba["discretionary_budget"]
        violations += int(bool(ba["cash_floor_active"])) + int(ba["interest_shortfall"] > 1e-9)
        if term or trunc:
            break
    funded = env.goal_balances[:n]
    r = np.minimum(funded, targets) / np.maximum(targets, 1e-9)
    pri = env.user_goals["priority"].astype(float).to_numpy()[:n]
    return {
        "user_id": uid, "policy": policy,
        "goal_achievement": float(np.sum(pri * r) / np.sum(pri)),
        "pct_goals_fully_funded": float(np.mean(r >= 1.0 - 1e-9)),
        "pct_goals_met_by_deadline": float(met.sum() / seen.sum()) if seen.any() else np.nan,
        "shortfall": float(np.sum(np.maximum(0.0, targets - funded))),
        "actual_investment": invest, "savings_contributions": savings,
        "investment_cap_overflow": overflow, "overflow_redirected": redirected,
        "overflow_retained_as_cash": retained,
        "idle_fraction": idle / max(budget, 1e-9),
        "net_worth": float(env.net_worth),
        "debt_outstanding": float(env.loan_balance),
        "interest_paid": float(env.total_interest_paid),
        "affordability_violations": float(violations),
    }


def main() -> None:
    plans = {uid: lp_plan(uid) for uid in FRESH_TEST}
    rows = []
    for label, cfg in ARMS:
        env = goalpilot_env.GoalPilotEnv(profiles=profiles, goals=goals, market=market,
                                         user_ids=FRESH_TEST, config=cfg)
        for policy in POLICIES:
            for uid in FRESH_TEST:
                rec = run(env, uid, policy, plans.get(uid))
                rec["arm"] = label
                rec["action_mode"] = cfg.action_mode
                rec["overflow_policy"] = cfg.investment_overflow_policy
                rec["reallocate"] = cfg.reallocate_capped_budget
                rows.append(rec)
        env.close()

    detail = pd.DataFrame(rows)
    detail.to_csv(OUT_DIR / "overflow_and_lp_metrics_v1.csv", index=False)
    metrics = ["goal_achievement", "pct_goals_fully_funded", "pct_goals_met_by_deadline",
               "shortfall", "actual_investment", "savings_contributions",
               "investment_cap_overflow", "overflow_redirected",
               "overflow_retained_as_cash", "idle_fraction", "net_worth",
               "debt_outstanding", "interest_paid", "affordability_violations"]
    summary = detail.groupby(["arm", "policy"])[metrics].mean().reset_index()
    summary.to_csv(OUT_DIR / "overflow_and_lp_summary_v1.csv", index=False)

    # LP encode/decode deviation, reported separately (never hidden)
    lp_dev = []
    for uid, plan in plans.items():
        if plan is None:
            lp_dev.append({"user_id": uid, "status": "no_optimal_plan"})
            continue
        enc = plan["encoded"]
        lp_dev.append({
            "user_id": uid, "status": "ok",
            "plan_total": enc["plan_total"],
            "plan_savings_total": enc["savings_total"],
            "plan_investment_total": enc["investment_total"],
            "investment_fraction": enc["investment_fraction"],
            "has_savings": enc["has_savings"],
            "has_investment": enc["has_investment"],
            "is_degenerate": enc["is_degenerate"],
            "capacity_ratio": float(profiles.loc[profiles["user_id"].astype(str) == uid,
                                                 "investment_capacity_ratio"].iloc[0]),
        })
    pd.DataFrame(lp_dev).to_csv(OUT_DIR / "lp_encoding_deviation_v1.csv", index=False)

    headline = ["goal_achievement", "actual_investment", "savings_contributions",
                "investment_cap_overflow", "overflow_retained_as_cash", "idle_fraction",
                "net_worth", "interest_paid"]
    print(json.dumps({
        "fresh_test_users": len(FRESH_TEST),
        "total_affordability_violations": float(detail["affordability_violations"].sum()),
        "arms": {a: len(ARMS) for a in [x[0] for x in ARMS]},
        "summary": summary.round(3).to_dict("records"),
        "headline": summary[["arm", "policy"] + headline].round(4).to_dict("records"),
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
