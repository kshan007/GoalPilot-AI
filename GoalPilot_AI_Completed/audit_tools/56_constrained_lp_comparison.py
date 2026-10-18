"""Phase 3 - constrained LP vs existing LP vs rules vs RL, on matched users and market.

Arms
    existing LP (unconstrained, unchanged optimizer)   - encoded with the corrected encoder
    constrained LP (capacity + single-loan)            - benchmark
    constrained LP (capacity only)                     - isolates the capacity constraint
    rules: uniform savings, need-proportional savings, investment-only, mixed, urgency
    RL: the six fresh-split checkpoints, only under their training semantics (share + legacy)

Reports the full fresh-test population and, separately, the feasibility-eligible and
structurally-infeasible cohorts (eligibility is ex-ante: `income - expenditure - emi > 0`).
Also compares each LP plan's *planned* monthly amounts with the *executed* episode totals, so
optimisation and execution differences are distinguishable.

Writes `outputs/evaluation/final_validation_v7/`.
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
    ACTION_MODE_SHARE,
    INVESTMENT_OVERFLOW_LEGACY,
    GoalPilotConfig,
)
from goalpilot_constrained_lp import solve_constrained_lp  # noqa: E402
from goalpilot_lp_encoder import encode_lp_plan_for_mix  # noqa: E402

OUT_DIR = paths.root / "outputs" / "evaluation" / "final_validation_v7"
OUT_DIR.mkdir(parents=True, exist_ok=True)

profiles = pd.read_csv(paths.rl_profiles_csv)
goals = pd.read_csv(paths.rl_goals_csv)
market = pd.read_csv(paths.rl_market_csv)
FRESH_TEST = json.loads(
    (paths.root / "training_logs" / "experiments" / "fresh_split_v1"
     / "fresh_split_v1_manifest.json").read_text(encoding="utf-8"))["test_users"]
RL_CKPT = paths.root / "training_logs" / "experiments" / "fresh_split_v1"

RULES = ["uniform savings", "need-proportional savings", "investment-only",
         "mixed allocation", "urgency"]
RL_ARMS = [("candidate_a", s) for s in (7, 17, 27)] + [("archived_v1", s) for s in (7, 17, 27)]
LP_ARMS = ["existing_LP_unconstrained", "constrained_LP", "constrained_LP_capacity_only"]

LP_KWARGS = dict(annual_inflation=0.03, savings_return=0.0, investment_return=0.05,
                 investment_risk_score=0.4, loan_annual_rate=0.12, loan_tenure_months=60,
                 max_loan_per_goal=150000.0)

METRICS = ["goal_achievement", "pct_goals_fully_funded", "pct_goals_met_by_deadline",
           "shortfall", "savings_contribution", "investment_contribution",
           "investment_cap_overflow", "overflow_retained_as_cash", "capacity_violation_months",
           "net_worth", "debt_outstanding", "interest_paid", "affordability_violations"]


def state_and_goals(uid: str):
    from src.multi_goal_optimizer import FinancialState
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
    return g, state, float(p["investment_capacity_ratio"]), p


def plan_for(uid: str, arm: str) -> dict:
    from src.multi_goal_optimizer import optimize_multi_goal
    g, state, ratio, p = state_and_goals(uid)
    if arm == "existing_LP_unconstrained":
        res = optimize_multi_goal(g, state, **LP_KWARGS)
        planned_invest_permitted = None
    elif arm == "constrained_LP":
        res = solve_constrained_lp(g, state, investment_capacity_ratio=ratio,
                                   max_new_loan=150000.0,
                                   enforce_investment_capacity=True,
                                   enforce_single_loan_limit=True, **LP_KWARGS)
        planned_invest_permitted = res["constraints"]["investment_permitted"]
    elif arm == "constrained_LP_capacity_only":
        res = solve_constrained_lp(g, state, investment_capacity_ratio=ratio,
                                   max_new_loan=150000.0,
                                   enforce_investment_capacity=True,
                                   enforce_single_loan_limit=False, **LP_KWARGS)
        planned_invest_permitted = res["constraints"]["investment_permitted"]
    else:
        raise ValueError(arm)
    if res["status"] != "optimal" or res["allocations"].empty:
        return {"status": res["status"], "action": np.zeros((5, 3), dtype=np.float32),
                "planned_savings": 0.0, "planned_investment": 0.0}
    a = res["allocations"]
    n = min(5, len(a))
    sav = np.zeros(5)
    inv = np.zeros(5)
    sav[:n] = a["monthly_savings_contribution"].to_numpy(dtype=float)[:n]
    inv[:n] = a["monthly_investment_contribution"].to_numpy(dtype=float)[:n]
    enc = encode_lp_plan_for_mix(sav, inv, n_slots=5)
    action = enc["action"].copy()
    loan_slot = int(np.argmax(a["loan_principal"].to_numpy(dtype=float)[:n]))
    if float(a["loan_principal"].to_numpy(dtype=float)[loan_slot]) > 0.0:
        action[loan_slot, 2] = 1.0
    return {
        "status": "optimal", "action": action,
        "planned_savings": float(sav.sum()), "planned_investment": float(inv.sum()),
        "planned_investment_permitted": planned_invest_permitted,
        "plan_total": enc["plan_total"], "investment_fraction": enc["investment_fraction"],
    }


def rule_action(env, policy) -> np.ndarray:
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
    return a


def run(env, uid, *, action=None, policy=None, model=None, ratio=0.0) -> dict:
    obs, _ = env.reset(options={"user_id": uid})
    n = len(env.user_goals)
    targets = env.goal_targets.astype(float)[:n]
    deadlines = env.goal_deadlines[:n].astype(int)
    met = np.zeros(n, dtype=bool)
    seen = np.zeros(n, dtype=bool)
    savings = invest = overflow = retained = idle = budget = violations = cap_viol = 0.0
    while True:
        if model is not None:
            act, _ = model.predict(obs, deterministic=True)
        elif action is not None:
            act = action
        else:
            act = rule_action(env, policy)
        obs, _, term, trunc, info = env.step(act)
        just = int(env.month_index)
        r = env.goal_balances[:n] / np.maximum(targets, 1e-9)
        for j in range(n):
            if deadlines[j] == just:
                seen[j] = True
                met[j] = r[j] >= 1.0 - 1e-9
        ba = info["budget_audit"]
        savings += ba["savings_contribution"]
        invest += ba["investment_contribution"]
        overflow += ba["invest_overflow"]
        retained += ba["overflow_retained_as_cash"]
        idle += ba["unallocated_surplus"]
        budget += ba["discretionary_budget"]
        ceiling = ratio * (ba["discretionary_budget"] + ba["env_loan_emi_paid"]
                           + float(info["active_loan_emi"])) + 1e-6
        if ba["investment_contribution"] > ceiling:
            cap_viol += 1
        violations += int(bool(ba["cash_floor_active"])) + int(ba["interest_shortfall"] > 1e-9)
        if term or trunc:
            break
    funded = env.goal_balances[:n]
    r = np.minimum(funded, targets) / np.maximum(targets, 1e-9)
    pri = env.user_goals["priority"].astype(float).to_numpy()[:n]
    return {
        "user_id": uid,
        "goal_achievement": float(np.sum(pri * r) / np.sum(pri)),
        "pct_goals_fully_funded": float(np.mean(r >= 1.0 - 1e-9)),
        "pct_goals_met_by_deadline": float(met.sum() / seen.sum()) if seen.any() else np.nan,
        "shortfall": float(np.sum(np.maximum(0.0, targets - funded))),
        "savings_contribution": savings, "investment_contribution": invest,
        "investment_cap_overflow": overflow, "overflow_retained_as_cash": retained,
        "capacity_violation_months": cap_viol, "idle_fraction": idle / max(budget, 1e-9),
        "net_worth": float(env.net_worth), "debt_outstanding": float(env.loan_balance),
        "interest_paid": float(env.total_interest_paid),
        "affordability_violations": float(violations),
    }


def boot_ci(values: np.ndarray, n=10000, seed=20261011):
    values = np.asarray(values, dtype=float)
    rng = np.random.default_rng(seed)
    draws = values[rng.integers(0, values.size, size=(n, values.size))].mean(axis=1)
    return float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))


def main() -> None:
    cfg = GoalPilotConfig.recommended()
    assert cfg.action_mode == ACTION_MODE_SHARE
    assert cfg.investment_overflow_policy == INVESTMENT_OVERFLOW_LEGACY

    plans = {arm: {uid: plan_for(uid, arm) for uid in FRESH_TEST} for arm in LP_ARMS}
    ratios = {uid: float(profiles.loc[profiles["user_id"].astype(str) == uid,
                                      "investment_capacity_ratio"].iloc[0])
              for uid in FRESH_TEST}

    rows = []
    env = goalpilot_env.GoalPilotEnv(profiles=profiles, goals=goals, market=market,
                                     user_ids=FRESH_TEST, config=cfg)
    for arm in LP_ARMS:
        for uid in FRESH_TEST:
            plan = plans[arm][uid]
            rec = run(env, uid, action=plan["action"], ratio=ratios[uid])
            rec.update(policy=arm, arm="LP",
                       planned_savings=plan.get("planned_savings", float("nan")),
                       planned_investment=plan.get("planned_investment", float("nan")),
                       planned_investment_permitted=plan.get(
                           "planned_investment_permitted", float("nan")))
            rows.append(rec)
    for policy in RULES:
        for uid in FRESH_TEST:
            rec = run(env, uid, policy=policy, ratio=ratios[uid])
            rec.update(policy=policy, arm="rule", planned_savings=float("nan"),
                       planned_investment=float("nan"),
                       planned_investment_permitted=float("nan"))
            rows.append(rec)
    env.close()

    from stable_baselines3 import PPO
    for arm_name, seed in RL_ARMS:
        ckpt = RL_CKPT / arm_name / f"ppo_{arm_name}_seed{seed}.zip"
        if not ckpt.is_file():
            continue
        assert cfg.action_mode == ACTION_MODE_SHARE
        assert cfg.investment_overflow_policy == INVESTMENT_OVERFLOW_LEGACY
        model = PPO.load(str(ckpt))
        env = goalpilot_env.GoalPilotEnv(profiles=profiles, goals=goals, market=market,
                                         user_ids=FRESH_TEST, config=cfg)
        for uid in FRESH_TEST:
            rec = run(env, uid, model=model, ratio=ratios[uid])
            rec.update(policy=f"RL {arm_name} seed{seed}", arm="RL",
                       planned_savings=float("nan"), planned_investment=float("nan"),
                       planned_investment_permitted=float("nan"))
            rows.append(rec)
        env.close()

    detail = pd.DataFrame(rows)
    detail["surplus"] = detail["user_id"].map(
        {uid: float(profiles.loc[profiles["user_id"].astype(str) == uid, "monthly_income"].iloc[0])
         - float(profiles.loc[profiles["user_id"].astype(str) == uid,
                             "monthly_expenditure"].iloc[0])
         - float(profiles.loc[profiles["user_id"].astype(str) == uid, "monthly_emi"].iloc[0])
         for uid in FRESH_TEST})
    detail["cohort"] = np.where(detail["surplus"] > 0, "feasible", "structurally_infeasible")
    detail.to_csv(OUT_DIR / "constrained_lp_detail_v1.csv", index=False)

    summaries = []
    for cohort, frame in [("full_population", detail),
                          ("feasible", detail[detail["cohort"] == "feasible"]),
                          ("structurally_infeasible",
                           detail[detail["cohort"] == "structurally_infeasible"])]:
        s = frame.groupby(["arm", "policy"])[METRICS + ["planned_savings",
                                                       "planned_investment"]].mean().reset_index()
        s.insert(0, "cohort", cohort)
        s["users"] = frame.groupby(["arm", "policy"]).size().to_numpy()
        summaries.append(s)
    summary = pd.concat(summaries, ignore_index=True)
    summary.to_csv(OUT_DIR / "constrained_lp_summary_v1.csv", index=False)

    # paired per-user differences: constrained LP minus existing LP
    paired = []
    for metric in METRICS:
        base = detail[detail["policy"] == "existing_LP_unconstrained"].set_index("user_id")
        cap = detail[detail["policy"] == "constrained_LP"].set_index("user_id")
        common = base.index.intersection(cap.index)
        diff = (cap.loc[common, metric] - base.loc[common, metric]).to_numpy(dtype=float)
        diff = diff[np.isfinite(diff)]
        if diff.size == 0:
            continue
        lo, hi = boot_ci(diff)
        paired.append({
            "metric": metric, "independent_users": int(diff.size),
            "mean_diff": float(diff.mean()), "sd_across_users": float(diff.std(ddof=1)),
            "ci95_low": lo, "ci95_high": hi,
            "users_improved": int((diff > 1e-9).sum()),
            "users_worsened": int((diff < -1e-9).sum()),
            "verdict": ("inconclusive" if lo <= 0 <= hi
                        else ("constrained_LP_higher" if lo > 0 else "existing_LP_higher")),
        })
    paired_df = pd.DataFrame(paired)
    paired_df.to_csv(OUT_DIR / "constrained_lp_paired_v1.csv", index=False)

    # planned vs executed, per LP arm
    plan_vs_exec = []
    for arm in LP_ARMS:
        sub = detail[detail["policy"] == arm]
        plan_vs_exec.append({
            "arm": arm,
            "planned_savings_monthly": float(sub["planned_savings"].mean()),
            "planned_investment_monthly": float(sub["planned_investment"].mean()),
            "planned_investment_permitted": float(
                sub["planned_investment_permitted"].dropna().mean())
            if sub["planned_investment_permitted"].notna().any() else float("nan"),
            "executed_investment_per_month": float(sub["investment_contribution"].mean() / 142.0),
            "executed_savings_per_month": float(sub["savings_contribution"].mean() / 142.0),
            "executed_overflow_per_month": float(sub["investment_cap_overflow"].mean() / 142.0),
            "capacity_violation_months": float(sub["capacity_violation_months"].mean()),
        })
    pd.DataFrame(plan_vs_exec).to_csv(OUT_DIR / "constrained_lp_plan_vs_executed_v1.csv",
                                      index=False)

    print(json.dumps({
        "fresh_test_users": len(FRESH_TEST),
        "feasible_users": int((detail.drop_duplicates("user_id")["cohort"] == "feasible").sum()),
        "total_affordability_violations": float(detail["affordability_violations"].sum()),
        "total_capacity_violation_months": float(detail["capacity_violation_months"].sum()),
        "plan_vs_executed": plan_vs_exec,
        "paired_constrained_vs_existing": paired,
        "summary_full": summary[summary["cohort"] == "full_population"].round(4).to_dict("records"),
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
