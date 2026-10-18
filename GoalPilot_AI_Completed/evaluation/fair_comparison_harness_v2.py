"""Phase 4 — common evaluation harness for savings-only / investment-only / rule-based / LP / RL.

Compared with `evaluation/final_validation_evaluation.py` (v1), this harness adds the **trained
RL policies** as a first-class arm and reports every strategy on **one** configuration, so that
accounting, goal targets, crediting, reserve policy, market path and user cohort are identical
across arms. Unavoidable differences are documented in `HARNESS_NOTES.md`, not hidden.

Strategies
    Savings only              - constant action, savings channel
    Investments only          - constant action, investment channel
    Rule-based urgency        - transparent rule: the whole budget to the goal with the largest
                                remaining need per remaining month
    LP optimizer plan         - the existing scipy/HiGHS optimizer's one-shot plan, mapped onto
                                the environment's monthly share weights
    RL candidate_a (3 seeds)  - the trained PPO checkpoints from reward_experiment_v1
    RL archived_v1 (3 seeds)  - same, for the historical reward

Reported metrics match the brief: weighted goal achievement, fully funded goals, deadline
success, shortfall, cash reserves, portfolio value, net worth, debt, interest, risk exposure and
affordability violations, cohort-wise, with user-level bootstrap uncertainty.

Writes to `outputs/evaluation/final_validation_v2/`. No existing artefact is touched.
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
from goalpilot_config import REWARD_VERSION_A, REWARD_VERSION_ARCHIVED, GoalPilotConfig  # noqa: E402
from stable_baselines3 import PPO  # noqa: E402

EXP_DIR = paths.root / "training_logs" / "experiments" / "reward_experiment_v1"
OUT_DIR = paths.root / "outputs" / "evaluation" / "final_validation_v2"
OUT_DIR.mkdir(parents=True, exist_ok=True)

N_BOOT = 10000
BOOT_SEED = 20261011

profiles = pd.read_csv(paths.rl_profiles_csv)
goals = pd.read_csv(paths.rl_goals_csv)
market = pd.read_csv(paths.rl_market_csv)
split = pd.read_csv(paths.rl_split_csv)
_split_col = next(c for c in ("split", "set", "subset", "is_test") if c in split.columns)
TEST_USERS = split.loc[split[_split_col].astype(str).str.lower() == "test",
                       "user_id"].astype(str).tolist()

CONFIG = GoalPilotConfig.recommended()


def make_env(user_ids):
    return goalpilot_env.GoalPilotEnv(
        profiles=profiles, goals=goals, market=market,
        user_ids=user_ids, config=CONFIG,
    )


def lp_plans() -> dict:
    from src.multi_goal_optimizer import FinancialState, optimize_multi_goal
    out = {}
    for uid in TEST_USERS:
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
        savings = np.zeros(5)
        invest = np.zeros(5)
        loan_slot = -1
        if res["status"] == "optimal" and not res["allocations"].empty:
            best_loan = 0.0
            for _, row in res["allocations"].iterrows():
                i = slot.get(str(row["goal_id"]))
                if i is None or i >= 5:
                    continue
                savings[i] = max(0.0, float(row["monthly_savings_contribution"]))
                invest[i] = max(0.0, float(row["monthly_investment_contribution"]))
                if float(row["loan_principal"]) > best_loan:
                    best_loan = float(row["loan_principal"])
                    loan_slot = i
        out[uid] = {"savings": savings, "invest": invest, "loan_slot": loan_slot,
                    "status": res["status"]}
    return out


def action_for(env, uid, policy, plan):
    n = len(env.user_goals)
    a = np.zeros(env.action_space.shape, dtype=np.float32)
    if policy == "Savings only":
        a[:, 0] = 1.0
    elif policy == "Investments only":
        a[:, 1] = 1.0
    elif policy == "Rule-based urgency":
        need = np.maximum(0.0, env.goal_targets - env.goal_balances)
        months = np.maximum(1, env.goal_deadlines - env.month_index)
        if need.sum() > 0:
            a[int(np.argmax(need / months)), 0] = 1.0
    elif policy == "LP optimizer plan":
        a[:n, 0] = plan["savings"][:n]
        a[:n, 1] = plan["invest"][:n]
        if plan["loan_slot"] >= 0:
            a[int(plan["loan_slot"]), 2] = 1.0
    return a


def rollout(env, uid, policy, plan=None, model=None) -> dict:
    obs, _ = env.reset(options={"user_id": uid})
    n = len(env.user_goals)
    deadline_ratio = np.full(n, np.nan)
    downside = 0.0
    violations = 0
    max_residual = 0.0
    while True:
        if model is not None:
            action, _ = model.predict(obs, deterministic=True)
        else:
            action = action_for(env, uid, policy, plan)
        obs, reward, term, trunc, info = env.step(action)
        ch = float(info["portfolio_market_change"])
        if ch < 0.0:
            downside += -ch
        ba = info["budget_audit"]
        max_residual = max(max_residual, abs(ba["budget_check"]))
        if ba["cash_floor_active"] or ba["interest_shortfall"] > 1e-9:
            violations += 1
        if float(info["ledger"]["cash"]) + 1e-6 < float(info["restricted_cash"]):
            violations += 1
        month = int(ba["month"])
        for j in range(n):
            if month == int(env.goal_deadlines[j]) and np.isnan(deadline_ratio[j]):
                deadline_ratio[j] = float(env.goal_balances[j]) / max(
                    1.0, float(env.goal_targets[j]))
        if term or trunc:
            break

    pri = env.user_goals["priority"].astype(float).to_numpy()
    target = env.goal_targets.astype(float)[:n]
    funded = env.goal_balances.astype(float)[:n]
    ratio = np.minimum(funded, target) / np.maximum(target, 1e-9)
    surplus = max(0.0, float(env.profile_map[uid]["monthly_income"])
                  - float(env.profile_map[uid]["monthly_expenditure"])
                  - float(env.profile_map[uid]["monthly_emi"]))
    return {
        "policy": policy, "user_id": uid,
        "feasible_cohort": "surplus>0" if surplus > 0 else "zero-surplus",
        "risk_score": float(env.profile_map[uid]["risk_score"]),
        "max_goal_horizon_months": int(env.goal_deadlines.max()),
        "weighted_goal_achievement": float(np.sum(pri * ratio) / np.sum(pri)),
        "pct_goals_fully_funded": float(np.mean(ratio >= 1.0 - 1e-9)),
        "pct_goals_met_by_deadline": float(np.nanmean(deadline_ratio >= 1.0 - 1e-9))
        if not np.all(np.isnan(deadline_ratio)) else np.nan,
        "goal_level_shortfall": float(np.sum(np.maximum(0.0, target - funded))),
        "final_liquid_cash": float(env.cash),
        "final_portfolio_value": float(env.portfolio),
        "net_worth": float(env.net_worth),
        "outstanding_loan_balance": float(env.loan_balance),
        "total_loan_principal": float(env.cumulative_loan_principal),
        "total_interest_paid": float(env.total_interest_paid),
        "investment_gain": float(env.total_investment_gain),
        "risk_exposure_downside": downside,
        "affordability_violations": violations,
        "max_budget_check_residual": max_residual,
    }


def boot_ci(v, n=N_BOOT, seed=BOOT_SEED):
    v = np.asarray(v, dtype=float)
    v = v[np.isfinite(v)]
    if v.size == 0:
        return (np.nan, np.nan)
    rng = np.random.default_rng(seed)
    m = v[rng.integers(0, v.size, size=(n, v.size))].mean(axis=1)
    return float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def main() -> None:
    rows = []
    plans = lp_plans()
    env = make_env(TEST_USERS)
    for uid in TEST_USERS:
        for policy in ["Savings only", "Investments only", "Rule-based urgency"]:
            rows.append(rollout(env, uid, policy))
        rows.append(rollout(env, uid, "LP optimizer plan", plan=plans[uid]))
    for version, label in ((REWARD_VERSION_A, "RL candidate_a"),
                           (REWARD_VERSION_ARCHIVED, "RL archived_v1")):
        for seed in (7, 17, 27):
            ckpt = EXP_DIR / version / f"ppo_{label.split()[-1]}_{version}_seed{seed}.zip"
            if not ckpt.is_file():
                ckpt = EXP_DIR / version / f"ppo_{'candidate_a' if version == REWARD_VERSION_A else 'archived_v1'}_seed{seed}.zip"
            model = PPO.load(str(ckpt))
            for uid in TEST_USERS:
                row = rollout(env, uid, f"{label} seed{seed}", model=model)
                rows.append(row)
    detail = pd.DataFrame(rows)
    detail.to_csv(OUT_DIR / "fair_comparison_metrics_v1.csv", index=False)

    metrics = ["weighted_goal_achievement", "pct_goals_fully_funded",
               "pct_goals_met_by_deadline", "goal_level_shortfall", "final_liquid_cash",
               "final_portfolio_value", "net_worth", "outstanding_loan_balance",
               "total_loan_principal", "total_interest_paid", "investment_gain",
               "risk_exposure_downside", "affordability_violations"]
    summary = []
    for policy, block in detail.groupby("policy"):
        row = {"policy": policy, "users": len(block)}
        for m in metrics:
            v = block[m].astype(float).to_numpy()
            lo, hi = boot_ci(v)
            row[f"{m}_mean"] = float(np.nanmean(v))
            row[f"{m}_median"] = float(np.nanmedian(v))
            row[f"{m}_sd"] = float(np.nanstd(v, ddof=1))
            row[f"{m}_ci95_low"] = lo
            row[f"{m}_ci95_high"] = hi
        summary.append(row)
    pd.DataFrame(summary).to_csv(OUT_DIR / "fair_comparison_summary_v1.csv", index=False)

    cohorts = []
    for (policy, cohort), block in detail.groupby(["policy", "feasible_cohort"]):
        cohorts.append({
            "policy": policy, "feasible_cohort": cohort, "users": len(block),
            **{m: float(block[m].mean()) for m in metrics},
        })
    pd.DataFrame(cohorts).to_csv(OUT_DIR / "fair_comparison_by_cohort_v1.csv", index=False)

    print(json.dumps({
        "policies": sorted(detail["policy"].unique().tolist()),
        "users": len(TEST_USERS),
        "rows": len(detail),
        "total_affordability_violations": int(detail["affordability_violations"].sum()),
        "max_budget_check_residual": float(detail["max_budget_check_residual"].max()),
        "archive_status_counts": {str(k): int(v) for k, v in
                                  pd.Series([p["status"] for p in plans.values()])
                                  .value_counts().items()},
        "key_means": detail.groupby("policy")[[
            "weighted_goal_achievement", "pct_goals_fully_funded",
            "pct_goals_met_by_deadline", "net_worth", "total_interest_paid"]
        ].mean().round(4).to_dict("index"),
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
