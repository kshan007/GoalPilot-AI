"""Phase 1 — diagnose the 0.0000-achievement low-risk cohort.

Read-only against every existing artefact. Produces:

* `low_risk_cohorts.csv`            - how the cohort is defined and how many independent users
* `low_risk_user_details.csv`       - per-user budgets, goals and feasibility arithmetic
* `low_risk_action_trace.csv`       - month-by-month trace for representative users
* `low_risk_feasibility_test.csv`   - the decisive test: trained policies vs an aggressive
                                      reference under the same environment
* `low_risk_diagnosis_summary.json` - the digest

The key discriminator is the **feasibility test**. If a maximally aggressive action also
achieves ~0 for these users, the zero is imposed by the environment (budget / goal scale), not
produced by weak learning. If the aggressive action achieves materially more while all trained
policies achieve 0, the cause is a policy or observation-design failure. The script reports
which of the two it observed rather than assuming either.
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

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import goalpilot_env  # noqa: E402
from goalpilot_config import (  # noqa: E402
    REWARD_VERSION_A,
    REWARD_VERSION_ARCHIVED,
    REWARD_VERSION_B,
    GoalPilotConfig,
)
from stable_baselines3 import PPO  # noqa: E402

EXP_DIR = paths.root / "training_logs" / "experiments" / "reward_experiment_v1"
OUT_DIR = paths.root / "outputs" / "reward_design" / "v2"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# The cohort boundaries used by audit_tools/34_reward_experiment_report.py. They are this
# audit's own binning, NOT a definition that exists anywhere in the project.
COHORT_BINS = [-0.01, 0.33, 0.66, 1.01]
COHORT_LABELS = ["low", "mid", "high"]

profiles = pd.read_csv(paths.rl_profiles_csv)
goals = pd.read_csv(paths.rl_goals_csv)
market = pd.read_csv(paths.rl_market_csv)
split = pd.read_csv(paths.rl_split_csv)
_split_col = next(c for c in ("split", "set", "subset", "is_test") if c in split.columns)
TEST_USERS = split.loc[split[_split_col].astype(str).str.lower() == "test",
                       "user_id"].astype(str).tolist()


def make_env(config, user_ids):
    return goalpilot_env.GoalPilotEnv(
        profiles=profiles, goals=goals, market=market,
        user_ids=user_ids, config=config,
    )


def cohort_of(risk_score: float) -> str:
    for lo, hi, label in zip(COHORT_BINS[:-1], COHORT_BINS[1:], COHORT_LABELS):
        if lo < risk_score <= hi:
            return label
    return "unknown"


# ------------------------------------------------------------------ 1. cohort definition ---

def cohort_table() -> pd.DataFrame:
    """Cohorts must be derived from the *data*, not from a label stored in a metrics file."""
    held = profiles.loc[profiles["user_id"].astype(str).isin(TEST_USERS)].copy()
    # cross-check against the label the published aggregation used
    published = pd.concat(
        [pd.read_csv(p) for p in sorted((EXP_DIR / "eval").glob("metrics_*.csv"))],
        ignore_index=True)
    published = published.drop_duplicates("user_id")[["user_id", "risk_score"]]
    held = held.merge(published, on="user_id", how="left", suffixes=("", "_published"))

    held["cohort"] = held["risk_score"].map(cohort_of)
    if "risk_score_published" in held:
        disagree = int((held["risk_score"] != held["risk_score_published"]).sum())
    else:
        disagree = -1

    rows = []
    for cohort, block in held.groupby("cohort"):
        goal_counts = goals.loc[
            goals["user_id"].astype(str).isin(block["user_id"].astype(str))
        ].groupby("user_id").size()
        rows.append({
            "cohort": cohort,
            "independent_users": int(len(block)),
            "risk_score_min": float(block["risk_score"].min()),
            "risk_score_max": float(block["risk_score"].max()),
            "risk_score_mean": float(block["risk_score"].mean()),
            "mean_monthly_income": float(block["monthly_income"].mean()),
            "mean_monthly_expenditure": float(block["monthly_expenditure"].mean()),
            "mean_monthly_emi": float(block["monthly_emi"].mean()),
            "mean_surplus": float(
                (block["monthly_income"] - block["monthly_expenditure"]
                 - block["monthly_emi"]).mean()),
            "mean_initial_savings": float(block["initial_savings"].mean()),
            "mean_initial_investment": float(block["initial_investment"].mean()),
            "mean_investment_capacity_ratio": float(
                block["investment_capacity_ratio"].mean()),
            "mean_goals_per_user": float(goal_counts.reindex(
                block["user_id"].astype(str)).mean()),
        })
    table = pd.DataFrame(rows).sort_values("cohort")
    table.attrs["published_label_disagreements"] = disagree
    return table


# ------------------------------------------------------------- 2. per-user feasibility ----

def user_details() -> pd.DataFrame:
    rows = []
    for uid in TEST_USERS:
        p = profiles.loc[profiles["user_id"].astype(str) == uid].iloc[0]
        g = goals.loc[goals["user_id"].astype(str) == uid]
        env = make_env(GoalPilotConfig.recommended(), [uid])
        env.reset(options={"user_id": uid})
        surplus = max(0.0, float(p["monthly_income"]) - float(p["monthly_expenditure"])
                      - float(p["monthly_emi"]))
        months = int(env.max_steps)
        targets = env.goal_targets.astype(float)
        nominal = g["current_cost"].astype(float).to_numpy()
        rows.append({
            "user_id": uid,
            "cohort": cohort_of(float(p["risk_score"])),
            "risk_score": float(p["risk_score"]),
            "investment_capacity_ratio": float(p["investment_capacity_ratio"]),
            "monthly_income": float(p["monthly_income"]),
            "monthly_expenditure": float(p["monthly_expenditure"]),
            "monthly_emi": float(p["monthly_emi"]),
            "monthly_surplus": surplus,
            "initial_savings": float(p["initial_savings"]),
            "initial_investment": float(p["initial_investment"]),
            "n_goals": int(len(g)),
            "sum_nominal_target": float(np.sum(nominal)),
            "sum_inflated_target": float(np.sum(targets)),
            "earliest_deadline_months": int(env.goal_deadlines.min()),
            "latest_deadline_months": int(env.goal_deadlines.max()),
            "episode_months": months,
            # maximum the household could ever commit if it saved 100% of surplus for the
            # whole episode and also used all liquid savings
            "max_achievable_from_surplus": surplus * months,
            "max_achievable_incl_savings": surplus * months + float(p["initial_savings"]),
            "target_over_surplus_capacity": float(np.sum(targets)) / max(surplus * months, 1.0),
            "surplus_is_zero": bool(surplus <= 1e-9),
            "reserve_consumes_all_savings": bool(
                float(env.restricted_cash) >= float(p["initial_savings"]) - 1e-9),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- 3. action trace --------

def trace(uid: str, config, model, label: str) -> pd.DataFrame:
    from goalpilot_config import ACTION_MODE_SHARE  # local import for clarity
    env = make_env(config, [uid])
    obs, _ = env.reset(options={"user_id": uid})
    rows = []
    while True:
        if model is not None:
            action, _ = model.predict(obs, deterministic=True)
        else:
            action = np.ones(env.action_space.shape, dtype=np.float32)
        obs, reward, term, trunc, info = env.step(action)
        ba = info["budget_audit"]
        n = len(env.user_goals)
        rows.append({
            "policy": label, "month": int(ba["month"]),
            "action_savings_mean": float(np.mean(np.asarray(action)[:n, 0])),
            "action_invest_mean": float(np.mean(np.asarray(action)[:n, 1])),
            "action_loan_max": float(np.max(np.asarray(action)[:n, 2])),
            "obs_max_abs": float(np.max(np.abs(np.asarray(obs)))),
            "surplus": float(ba["surplus"]),
            "discretionary_budget": float(ba["discretionary_budget"]),
            "savings_contribution": float(ba["savings_contribution"]),
            "investment_contribution": float(ba["investment_contribution"]),
            "unallocated_surplus": float(ba["unallocated_surplus"]),
            "new_loan_principal": float(info["new_loan_principal"]),
            "goal_balances_total": float(info["ledger"]["goal_balances_total"]),
            "cash": float(info["ledger"]["cash"]),
            "net_worth": float(info["net_worth"]),
            "reward": float(reward),
            "action_mode": config.action_mode,
        })
        if term or trunc:
            break
    return pd.DataFrame(rows)


# ------------------------------------------------------- 4. the decisive feasibility test --

def feasibility_test() -> pd.DataFrame:
    """Trained policies vs aggressive references, on the same users and environment."""
    rec = GoalPilotConfig.recommended()
    low = [r["user_id"] for r in user_details().to_dict("records") if r["cohort"] == "low"]
    if not low:
        return pd.DataFrame()
    mid_high = [r["user_id"] for r in user_details().to_dict("records")
                if r["cohort"] in ("mid", "high")]

    def score(config, model, user_ids, label, aggressive):
        env = make_env(config, user_ids)
        out = []
        for uid in user_ids:
            obs, _ = env.reset(options={"user_id": uid})
            while True:
                if aggressive:
                    action = np.ones(env.action_space.shape, dtype=np.float32)
                    if label.endswith("savings-only"):
                        action[:, 1] = 0.0
                else:
                    action, _ = model.predict(obs, deterministic=True)
                obs, reward, term, trunc, info = env.step(action)
                if term or trunc:
                    break
            n = len(env.user_goals)
            target = env.goal_targets.astype(float)[:n]
            funded = env.goal_balances.astype(float)[:n]
            priority = env.user_goals["priority"].astype(float).to_numpy()
            ratio = np.minimum(funded, target) / np.maximum(target, 1e-9)
            out.append({
                "policy": label, "cohort": cohort_of(float(
                    env.profile_map[uid]["risk_score"])), "user_id": uid,
                "weighted_achievement": float(np.sum(priority * ratio) / np.sum(priority)),
                "pct_fully_funded": float(np.mean(ratio >= 1.0 - 1e-9)),
                "funded_total": float(np.sum(funded)),
                "target_total": float(np.sum(target)),
                "net_worth": float(env.net_worth),
                "loan_principal": float(env.cumulative_loan_principal),
                "interest_paid": float(env.total_interest_paid),
            })
        return out

    rows = []
    policies = [
        ("archived_v1", REWARD_VERSION_ARCHIVED, "archived_v1_seed7"),
        ("candidate_a", REWARD_VERSION_A, "candidate_a_seed7"),
        ("candidate_b", REWARD_VERSION_B, "candidate_b_seed7"),
    ]
    for label, version, ckpt in policies:
        model = PPO.load(str(EXP_DIR / version / f"ppo_{ckpt.rsplit('_seed', 1)[0]}_seed7.zip"))
        rows += score(rec.replace(reward_version=version), model, low, f"{label} (trained)", False)
    # aggressive references: the strongest action the share semantics allow
    rows += score(rec, None, low, "AGGRESSIVE all-channels savings-only", True)
    rows += score(rec, None, low, "AGGRESSIVE all-channels mixed+loan", True)
    # and the same aggressive references on the other cohorts, for contrast
    rows += score(rec, None, mid_high, "AGGRESSIVE all-channels savings-only (mid/high)", True)
    return pd.DataFrame(rows)


def main() -> None:
    cohorts = cohort_table()
    cohorts.to_csv(OUT_DIR / "low_risk_cohorts.csv", index=False)

    details = user_details()
    details.to_csv(OUT_DIR / "low_risk_user_details.csv", index=False)

    low_users = details.loc[details["cohort"] == "low", "user_id"].tolist()
    mid_users = details.loc[details["cohort"] == "mid", "user_id"].tolist()

    traces = []
    for uid in low_users[:2]:
        traces.append(trace(uid, GoalPilotConfig.recommended().replace(
            reward_version=REWARD_VERSION_A),
            PPO.load(str(EXP_DIR / REWARD_VERSION_A / "ppo_candidate_a_seed7.zip")),
            "candidate_a trained"))
        traces.append(trace(uid, GoalPilotConfig.recommended().replace(
            reward_version=REWARD_VERSION_A), None, "AGGRESSIVE mixed+loan"))
    if mid_users:
        traces.append(trace(mid_users[0], GoalPilotConfig.recommended().replace(
            reward_version=REWARD_VERSION_A),
            PPO.load(str(EXP_DIR / REWARD_VERSION_A / "ppo_candidate_a_seed7.zip")),
            "candidate_a trained (mid cohort, for contrast)"))
    trace_df = pd.concat(traces, ignore_index=True)
    trace_df.to_csv(OUT_DIR / "low_risk_action_trace.csv", index=False)

    feas = feasibility_test()
    feas.to_csv(OUT_DIR / "low_risk_feasibility_test.csv", index=False)

    summary = {
        "cohort_binning_used": {"bins": COHORT_BINS, "labels": COHORT_LABELS,
                                "provenance": "this audit's own binning, not a project definition"},
        "published_label_disagreements": cohorts.attrs.get("published_label_disagreements"),
        "cohort_counts": cohorts.set_index("cohort")["independent_users"].to_dict(),
        "low_risk_user_ids": low_users,
        "low_risk_feasibility": {
            row["user_id"]: {
                "monthly_surplus": row["monthly_surplus"],
                "surplus_is_zero": row["surplus_is_zero"],
                "investment_capacity_ratio": row["investment_capacity_ratio"],
                "sum_inflated_target": row["sum_inflated_target"],
                "max_achievable_from_surplus": row["max_achievable_from_surplus"],
                "target_over_surplus_capacity": row["target_over_surplus_capacity"],
                "reserve_consumes_all_savings": row["reserve_consumes_all_savings"],
            }
            for row in details.to_dict("records") if row["cohort"] == "low"
        },
        "feasibility_test_means": (
            feas.groupby(["policy", "cohort"])[
                ["weighted_achievement", "funded_total", "net_worth", "loan_principal"]
            ].mean().reset_index().to_dict("records") if not feas.empty else []
        ),
    }
    (OUT_DIR / "low_risk_diagnosis_summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8")

    print(json.dumps({
        "cohorts": cohorts.to_dict("records"),
        "low_risk_users": low_users,
        "low_risk_surplus": details.loc[details["cohort"] == "low",
                                       ["user_id", "monthly_surplus", "sum_inflated_target",
                                        "max_achievable_from_surplus",
                                        "target_over_surplus_capacity",
                                        "investment_capacity_ratio"]].to_dict("records"),
        "feasibility_test_means": summary["feasibility_test_means"],
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
