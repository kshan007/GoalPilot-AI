"""Baseline diagnostics for the GoalPilot RL prototype environment.

Read-only with respect to the original project: this script imports the original
`goalpilot_env.py` and writes its outputs to the audit workspace only.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ORIG_ENV = Path(
    r"S:\fyp\GoalPilot_AI\simulation\05_simulation_runs\rl_prototype\goalpilot_env.py"
)
RUN_DIR = ORIG_ENV.parent
OUT = Path(r"S:\fyp\_audit\diag_baseline")
OUT.mkdir(parents=True, exist_ok=True)


def load_env_module(path: Path, name: str = "orig_goalpilot_env"):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def run_episode(env, policy, n_goals, action_shape, const=None, loan_const=0.0):
    env.reset(options={"user_id": policy_user})
    return None


POLICIES = {
    "No action": (0.0, 0.0, 0.0),
    "Savings only": (1.0, 0.0, 0.0),
    "Investments only": (0.0, 1.0, 0.0),
    "Mixed allocation": (0.5, 0.5, 0.0),
    "Loan request only": (0.0, 0.0, 1.0),
    "Flat 0.25 savings": (0.25, 0.0, 0.0),
    "Flat 0.50 savings": (0.50, 0.0, 0.0),
    "Flat 0.75 savings": (0.75, 0.0, 0.0),
}

policy_user = None


def main():
    envmod = load_env_module(ORIG_ENV)
    profiles = pd.read_csv(RUN_DIR / "rl_sample_financial_profiles.csv")
    goals = pd.read_csv(RUN_DIR / "rl_sample_goals.csv")
    market = pd.read_csv(RUN_DIR / "rl_market_credit_validated.csv")
    split = pd.read_csv(RUN_DIR / "rl_train_test_user_split.csv")

    user_ids = profiles["user_id"].astype(str).tolist()
    goal_counts = goals.groupby("user_id").size()
    icr = profiles.set_index("user_id")["investment_capacity_ratio"]

    env = envmod.GoalPilotEnv(profiles=profiles, goals=goals, market=market,
                              user_ids=user_ids, seed=2026)
    print(f"action_space={env.action_space.shape} obs_space={env.observation_space.shape} "
          f"max_goals={env.max_goals} max_steps={env.max_steps}")

    rows = []
    ledger = []
    for uid in user_ids:
        for pname, (a_sav, a_inv, a_loan) in POLICIES.items():
            env.reset(options={"user_id": uid})
            init_funding = float(env.goal_balances.sum())
            init_cash = float(env.cash)
            init_port = float(env.portfolio)
            tot_reward = 0.0
            tot_sav = tot_inv = tot_loan = tot_emi = 0.0
            tot_unalloc = 0.0
            max_excess = 0.0
            while True:
                action = np.zeros(env.action_space.shape, dtype=np.float32)
                action[:, 0] = a_sav
                action[:, 1] = a_inv
                action[:, 2] = a_loan
                obs, reward, term, trunc, info = env.step(action)
                tot_reward += float(reward)
                tot_sav += float(info["savings_contribution"])
                tot_inv += float(info["investment_contribution"])
                tot_loan += float(info["new_loan_principal"])
                tot_emi += float(info["active_loan_emi"])
                # Unallocated surplus = surplus - contributions - loan commitment
                tot_unalloc += max(
                    0.0,
                    float(info["monthly_surplus"])
                    - float(info["savings_contribution"])
                    - float(info["investment_contribution"])
                    - float(info["new_loan_emi"]),
                )
                max_excess = max(
                    max_excess,
                    float(info["combined_monthly_commitment"]) - float(info["monthly_surplus"]),
                )
                if term or trunc:
                    break

            targets = np.asarray(env.goal_targets, dtype=float)
            balances = np.asarray(env.goal_balances, dtype=float)
            funded = float(np.minimum(balances, targets).sum())
            rows.append({
                "user_id": uid,
                "policy": pname,
                "n_goals": int(goal_counts.get(uid, 0)),
                "investment_capacity_ratio": float(icr.get(uid, np.nan)),
                "initial_goal_funding": init_funding,
                "init_cash": init_cash,
                "init_portfolio": init_port,
                "funded_sum": funded,
                "target_sum": float(targets.sum()),
                "goal_funding_ratio": funded / max(float(targets.sum()), 1.0),
                "final_cash": float(env.cash),
                "final_portfolio": float(env.portfolio),
                "final_loan_balance": float(env.loan_balance),
                "net_worth_cash_plus_portfolio_minus_loan":
                    float(env.cash) + float(env.portfolio) - float(env.loan_balance),
                "total_savings_contributions": tot_sav,
                "total_investment_contributions": tot_inv,
                "total_new_loan_principal": tot_loan,
                "total_active_loan_emi_sum": tot_emi,
                "total_unallocated_surplus": tot_unalloc,
                "total_reward": tot_reward,
                "max_budget_excess": max_excess,
            })

    df = pd.DataFrame(rows)
    df.to_csv(OUT / "baseline_policy_all_users.csv", index=False)

    print("\n=== POLICY SUMMARY (100 users each) ===")
    summ = df.groupby("policy").agg(
        users=("user_id", "nunique"),
        mean_funding_ratio=("goal_funding_ratio", "mean"),
        mean_funded=("funded_sum", "mean"),
        mean_final_cash=("final_cash", "mean"),
        mean_final_portfolio=("final_portfolio", "mean"),
        mean_final_loan=("final_loan_balance", "mean"),
        mean_new_loan_principal=("total_new_loan_principal", "mean"),
        mean_unallocated=("total_unallocated_surplus", "mean"),
        mean_reward=("total_reward", "mean"),
        max_budget_excess=("max_budget_excess", "max"),
    ).reset_index()
    print(summ.round(4).to_string(index=False))
    summ.to_csv(OUT / "baseline_policy_summary.csv", index=False)

    # ---- H1: savings-only == mixed allocation (degeneracy)
    print("\n=== H1: Savings-only vs Mixed allocation goal funding ===")
    w = df.pivot(index="user_id", columns="policy", values="goal_funding_ratio")
    d = (w["Mixed allocation"] - w["Savings only"]).abs()
    print(f"users where |mixed - savings| <= 1e-12 : {(d <= 1e-12).sum()} / {len(d)}")
    print(f"max abs difference                       : {d.max():.3e}")
    exact = df.pivot(index="user_id", columns="policy", values="funded_sum")
    de = (exact["Mixed allocation"] - exact["Savings only"]).abs()
    print(f"max abs funded_sum difference            : {de.max():.3e}")
    print(f"median funded_sum difference             : {de.median():.3e}")
    # portfolio DOES differ
    pf = df.pivot(index="user_id", columns="policy", values="final_portfolio")
    dp = (pf["Mixed allocation"] - pf["Savings only"]).abs()
    print(f"median |portfolio difference|            : {dp.median():,.2f} (so mix only changes wealth)")

    # ---- H2: action magnitude -> budget utilisation
    print("\n=== H2: savings action magnitude vs goal funding (budget utilisation) ===")
    sub = df[df["policy"].isin(["Flat 0.25 savings", "Flat 0.50 savings",
                                "Flat 0.75 savings", "Savings only"])]
    s2 = sub.groupby("policy").agg(
        mean_funded=("funded_sum", "mean"),
        mean_unallocated=("total_unallocated_surplus", "mean"),
        mean_funding_ratio=("goal_funding_ratio", "mean"),
    ).round(2)
    print(s2.to_string())

    # ---- H3: accounting identity
    print("\n=== H3: accounting reconstruction (Savings only, first 5 users) ===")
    chk = []
    for uid in user_ids[:5]:
        r = df[(df.user_id == uid) & (df.policy == "Savings only")].iloc[0]
        p = profiles[profiles.user_id == uid].iloc[0]
        g = goals[goals.user_id == uid]
        earmark = float(g["existing_funding"].sum())
        initial_savings = float(p["initial_savings"])
        scale = min(1.0, initial_savings / earmark) if earmark > 0 else 1.0
        reconc_earmark = earmark * scale
        expected_cash = max(0.0, initial_savings - reconc_earmark) + r["total_savings_contributions"]
        chk.append({
            "user_id": uid,
            "env_final_cash": r["final_cash"],
            "reconstructed_cash": expected_cash,
            "match": abs(r["final_cash"] - expected_cash) < 1e-6,
            "goal_balances": r["funded_sum"],
            "contributions": r["total_savings_contributions"],
            "cash_contains_contribs": abs(
                r["final_cash"] - (max(0.0, initial_savings - reconc_earmark) + r["total_savings_contributions"])
            ) < 1e-6,
        })
    chkdf = pd.DataFrame(chk)
    print(chkdf.round(2).to_string(index=False))
    print("\nNOTE: goal_balances ALSO contain the same contributions -> "
          "cash + portfolio + goal_balances double counts.")

    # ---- H4: n_goals effect on degeneracy
    print("\n=== H4: degeneracy vs goal count / investment capacity ===")
    dd = df.pivot(index="user_id", columns="policy",
                  values="goal_funding_ratio").reset_index()
    dd = dd.merge(profiles[["user_id", "investment_capacity_ratio"]], on="user_id", how="left")
    dd["diff"] = (dd["Mixed allocation"] - dd["Savings only"]).abs()
    dd["n_goals"] = dd["user_id"].map(goal_counts).astype(int)
    dd["threshold"] = 2.0 / (1.0 + dd["investment_capacity_ratio"])
    dd["identity_expected"] = dd["n_goals"] >= dd["threshold"]
    print("goal count vs exact match:")
    print(pd.crosstab(dd["n_goals"], dd["diff"] <= 1e-12).to_string())
    print("\ntheoretical identity (n >= 2/(1+ICR)) vs observed exact match:")
    print(pd.crosstab(dd["identity_expected"], dd["diff"] <= 1e-12).to_string())
    dd.to_csv(OUT / "degeneracy_by_user.csv", index=False)

    with open(OUT / "diagnostic_summary.json", "w", encoding="utf-8") as f:
        json.dump({
            "env_module": str(ORIG_ENV),
            "n_users": len(user_ids),
            "action_shape": list(env.action_space.shape),
            "obs_shape": list(env.observation_space.shape),
            "max_goals": int(env.max_goals),
            "max_steps": int(env.max_steps),
            "h1_users_exact_match": int((d <= 1e-12).sum()),
            "h1_max_abs_diff": float(d.max()),
            "h2": s2.to_dict(),
        }, f, indent=2)
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
