"""P1 — why does a constant `Investments only` action beat every RL policy?

Read-only mechanism diagnosis on the existing artefacts. Three questions:

1. **What do the RL policies actually emit?** Action distributions per channel per checkpoint —
   mean, SD, and the fraction of near-zero / near-one outputs. A policy that emits small or
   saturated actions explains a lot on its own.
2. **Where does the monthly budget go?** For each strategy, the split between money actually
   allocated, money released by the per-goal cap (finding R-08, observed as
   `unallocated_surplus`), and money left idle. Finding R-08 predicts that any policy which lets
   the cap bind wastes budget that a re-allocating planner would not.
3. **How much credited goal funding is *market revaluation* rather than contribution?** Under
   `market_weighted` an invested rupee keeps earning, so an investment-heavy policy can fund
   more rupees in total. That is real wealth growth, not an accounting artefact, but it is the
   mechanism that puts `Investments only` ahead, and it should be measured rather than assumed.

Reference policies locate the ceiling: `Need-proportional *` requests exactly each goal's
remaining need (so the per-goal cap should never bind), which separates "the policy asked badly"
from "the environment caps what any policy can do".

Writes to `outputs/evaluation/final_validation_v2/`.
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
CONFIG = GoalPilotConfig.recommended()

profiles = pd.read_csv(paths.rl_profiles_csv)
goals = pd.read_csv(paths.rl_goals_csv)
market = pd.read_csv(paths.rl_market_csv)
split = pd.read_csv(paths.rl_split_csv)
_split_col = next(c for c in ("split", "set", "subset", "is_test") if c in split.columns)
TEST_USERS = split.loc[split[_split_col].astype(str).str.lower() == "test",
                       "user_id"].astype(str).tolist()


def feasible_users() -> list[str]:
    out = []
    for uid in TEST_USERS:
        p = profiles.loc[profiles["user_id"].astype(str) == uid].iloc[0]
        if float(p["monthly_income"]) - float(p["monthly_expenditure"]) - float(p["monthly_emi"]) > 0:
            out.append(uid)
    return out


def make_env(user_ids):
    return goalpilot_env.GoalPilotEnv(
        profiles=profiles, goals=goals, market=market,
        user_ids=user_ids, config=CONFIG,
    )


def action_for(env, policy, plan=None, model=None, obs=None):
    n = len(env.user_goals)
    a = np.zeros(env.action_space.shape, dtype=np.float32)
    if model is not None:
        a, _ = model.predict(obs, deterministic=True)
        return np.asarray(a, dtype=np.float32)

    need = np.maximum(0.0, env.goal_targets - env.goal_balances)
    share = need / max(float(need.sum()), 1e-9)

    if policy == "Savings only":
        a[:, 0] = 1.0
    elif policy == "Investments only":
        a[:, 1] = 1.0
    elif policy == "Mixed (0.50/0.50)":
        a[:, 0], a[:, 1] = 0.5, 0.5
    elif policy == "Rule-based urgency":
        if need.sum() > 0:
            months = np.maximum(1, env.goal_deadlines - env.month_index)
            a[int(np.argmax(need / months)), 0] = 1.0
    elif policy == "LP optimizer plan" and plan is not None:
        a[:n, 0] = plan["savings"][:n]
        a[:n, 1] = plan["invest"][:n]
        if plan["loan_slot"] >= 0:
            a[int(plan["loan_slot"]), 2] = 1.0
    elif policy == "Need-proportional savings":
        a[:n, 0] = share
    elif policy == "Need-proportional invest":
        a[:n, 1] = share
    elif policy == "Need-proportional both":
        a[:n, 0], a[:n, 1] = share, share
    elif policy == "AGGRESSIVE all channels":
        a[:, :] = 1.0
    return a


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


def rollout(env, uid, policy, plan=None, model=None, collect_actions=False):
    obs, _ = env.reset(options={"user_id": uid})
    n = len(env.user_goals)
    acc = dict(months=0, budget=0.0, savings=0.0, invest=0.0, idle=0.0, invested_total=0.0,
               guard_min=1.0, loan=0.0, interest=0.0)
    actions = []
    while True:
        a = action_for(env, policy, plan=plan, model=model, obs=obs)
        if collect_actions:
            actions.append(np.asarray(a)[:n, :].copy())
        obs, reward, term, trunc, info = env.step(a)
        ba = info["budget_audit"]
        acc["months"] += 1
        acc["budget"] += float(ba["discretionary_budget"])
        acc["savings"] += float(ba["savings_contribution"])
        acc["invest"] += float(ba["investment_contribution"])
        acc["idle"] += float(ba["unallocated_surplus"])
        acc["invested_total"] += float(info["investment_contribution"])
        acc["guard_min"] = min(acc["guard_min"], float(ba["guard_scale"]))
        acc["loan"] += float(info["new_loan_principal"])
        acc["interest"] += float(ba["interest_paid_cash"])
        if term or trunc:
            break

    pri = env.user_goals["priority"].astype(float).to_numpy()
    target = env.goal_targets.astype(float)[:n]
    funded = env.goal_balances.astype(float)[:n]
    ratio = np.minimum(funded, target) / np.maximum(target, 1e-9)
    row = {
        "policy": policy, "user_id": uid,
        "weighted_achievement": float(np.sum(pri * ratio) / np.sum(pri)),
        "pct_goals_fully_funded": float(np.mean(ratio >= 1.0 - 1e-9)),
        "funded_total": float(np.sum(funded)),
        "target_total": float(np.sum(target)),
        "net_worth": float(env.net_worth),
        "portfolio": float(env.portfolio),
        "cash": float(env.cash),
        "loan_principal": float(env.cumulative_loan_principal),
        "interest_paid": float(env.total_interest_paid),
        "investment_gain": float(env.total_investment_gain),
        "market_value_earmarked": float(env.goal_market_value.sum(dtype="float64")),
        "budget_total": acc["budget"],
        "savings_contribution_total": acc["savings"],
        "investment_contribution_total": acc["invest"],
        "idle_surplus_total": acc["idle"],
        "allocated_fraction": (acc["savings"] + acc["invest"]) / max(acc["budget"], 1e-9),
        "idle_fraction": acc["idle"] / max(acc["budget"], 1e-9),
        "guard_scale_min": acc["guard_min"],
        "months": acc["months"],
    }
    return row, actions


def main() -> None:
    users = feasible_users()
    env = make_env(users)
    plans = lp_plans()

    static = ["Savings only", "Investments only", "Mixed (0.50/0.50)", "Rule-based urgency",
              "LP optimizer plan", "Need-proportional savings", "Need-proportional invest",
              "Need-proportional both", "AGGRESSIVE all channels"]
    rl = []
    for version, label in ((REWARD_VERSION_A, "candidate_a"),
                           (REWARD_VERSION_ARCHIVED, "archived_v1")):
        for seed in (7, 17, 27):
            ckpt = EXP_DIR / version / f"ppo_{label}_seed{seed}.zip"
            rl.append((f"RL {label} seed{seed}", PPO.load(str(ckpt))))

    rows, action_rows = [], []
    for uid in users:
        for policy in static:
            row, _ = rollout(env, uid, policy, plan=plans.get(uid))
            rows.append(row)
        for name, model in rl:
            row, acts = rollout(env, uid, name, model=model, collect_actions=True)
            rows.append(row)
            for a in acts:
                for slot in range(a.shape[0]):
                    for ch, cname in enumerate(("savings", "invest", "loan")):
                        action_rows.append({"policy": name, "user_id": uid, "slot": slot,
                                            "channel": cname, "value": float(a[slot, ch])})
    detail = pd.DataFrame(rows)
    detail.to_csv(OUT_DIR / "strategy_space_diagnosis.csv", index=False)

    acts = pd.DataFrame(action_rows)
    acts.to_csv(OUT_DIR / "rl_action_distributions_raw.csv", index=False)
    dist = (acts.groupby(["policy", "channel"])["value"]
            .agg(mean="mean", sd="std",
                 frac_below_0p05=lambda s: float((s < 0.05).mean()),
                 frac_above_0p95=lambda s: float((s > 0.95).mean()),
                 n="size").reset_index())
    dist.to_csv(OUT_DIR / "rl_action_distributions.csv", index=False)

    summary = (detail.groupby("policy")[[
        "weighted_achievement", "pct_goals_fully_funded", "funded_total", "net_worth",
        "portfolio", "cash", "loan_principal", "interest_paid", "investment_gain",
        "market_value_earmarked", "allocated_fraction", "idle_fraction", "guard_scale_min"]
    ].mean().reset_index().sort_values("weighted_achievement", ascending=False))
    summary.to_csv(OUT_DIR / "strategy_space_summary.csv", index=False)

    print(json.dumps({
        "feasible_users": len(users),
        "ranking": summary[["policy", "weighted_achievement", "pct_goals_fully_funded",
                            "allocated_fraction", "idle_fraction",
                            "market_value_earmarked", "net_worth"]]
        .round(4).to_dict("records"),
        "rl_action_distributions": dist.round(4).to_dict("records"),
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
