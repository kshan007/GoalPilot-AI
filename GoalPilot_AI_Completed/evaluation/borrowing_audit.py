"""Borrowing audit (audit findings F-05, F-07).

The archive reported that PPO "generates borrowing" without establishing whether the
borrowing was useful, costly, or an artefact of the ledger. This script answers that
question on the held-out users by comparing a savings-only plan against the same plan
with a maximum loan request, and by attributing every rupee.

Per user it reports
-------------------
* loan principal originated, final balance, interest actually paid, EMI-months
* change in goal funding caused by borrowing
* change in net worth caused by borrowing
* the "cost of a funded rupee": extra interest per extra rupee of goal funding
* a verdict

It also flags ledger violations: in a correct ledger, taking a loan must be net-zero on
net worth at origination, so any *increase* in net worth from borrowing alone is a
bookkeeping error rather than a financial result.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

from goalpilot_config import GoalPilotConfig
from goalpilot_paths import ProjectPaths
from policy_evaluation import PolicySpec, rollout
import goalpilot_env

SAVINGS_ONLY = PolicySpec("Savings only", 1.0, 0.0, 0.0)
SAVINGS_AND_LOAN = PolicySpec("Savings + loan", 0.5, 0.0, 1.0)
SAVINGS_ONLY_MAX_LOAN = PolicySpec("Savings only + max loan", 1.0, 0.0, 1.0)

# A controlled pair: identical on every channel except the loan request. In "magnitude"
# action mode any savings weight at or above the saturation point allocates the same total
# budget, so (1.0, 0, 1.0) and (0.5, 0, 1.0) are the *same* savings policy — which is why
# the isolating comparison below uses (0.5, 0, 0) against (0.5, 0, 1.0).
HALF_SAVINGS = PolicySpec("Half savings", 0.5, 0.0, 0.0)


def build_frame(detail_savings: pd.DataFrame, detail_loan: pd.DataFrame,
                settings: tuple[PolicySpec, PolicySpec]) -> pd.DataFrame:
    a_name, b_name = settings[0].name, settings[1].name
    a = detail_savings.loc[detail_savings["policy"] == a_name].set_index("user_id")
    b = detail_loan.loc[detail_loan["policy"] == b_name].set_index("user_id")
    joined = a.join(b, lsuffix="_no_loan", rsuffix="_loan", how="inner")

    out = pd.DataFrame(index=joined.index)
    out["funding_ratio_no_loan"] = joined["goal_funding_ratio_no_loan"]
    out["funding_ratio_with_loan"] = joined["goal_funding_ratio_loan"]
    out["funding_delta"] = out["funding_ratio_with_loan"] - out["funding_ratio_no_loan"]
    out["goal_funding_amount_delta"] = (
        joined["goal_funding_amount_loan"] - joined["goal_funding_amount_no_loan"]
    )
    out["loan_principal"] = joined["total_new_loan_principal_loan"]
    out["final_loan_balance"] = joined["final_loan_balance_loan"]
    out["interest_paid"] = joined["total_interest_paid_loan"]
    out["net_worth_no_loan"] = joined["net_worth_ledger_no_loan"]
    out["net_worth_with_loan"] = joined["net_worth_ledger_loan"]
    out["net_worth_delta"] = out["net_worth_with_loan"] - out["net_worth_no_loan"]
    out["reward_delta"] = joined["total_reward_loan"] - joined["total_reward_no_loan"]

    def cost_per_funded_rupee(row):
        extra = row["goal_funding_amount_delta"]
        if extra <= 1e-6:
            return np.nan
        return row["interest_paid"] / extra

    out["interest_per_extra_funded_rupee"] = out.apply(cost_per_funded_rupee, axis=1)

    def verdict(row):
        if row["loan_principal"] <= 1e-6:
            return "no loan taken"
        if row["funding_delta"] > 1e-9:
            return "helps funding"
        if row["funding_delta"] < -1e-9:
            return "hurts funding"
        return "funding neutral"

    out["verdict"] = out.apply(verdict, axis=1)
    return out.reset_index()


def summarise(frame: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame([{
        "users": int(len(frame)),
        "users_with_loan": int((frame["loan_principal"] > 1e-6).sum()),
        "mean_loan_principal": float(frame["loan_principal"].mean()),
        "total_loan_principal": float(frame["loan_principal"].sum()),
        "total_interest_paid": float(frame["interest_paid"].sum()),
        "mean_funding_ratio_no_loan": float(frame["funding_ratio_no_loan"].mean()),
        "mean_funding_ratio_with_loan": float(frame["funding_ratio_with_loan"].mean()),
        "mean_funding_delta": float(frame["funding_delta"].mean()),
        "mean_net_worth_delta": float(frame["net_worth_delta"].mean()),
        "mean_reward_delta": float(frame["reward_delta"].mean()),
        "helps_funding": int((frame["verdict"] == "helps funding").sum()),
        "hurts_funding": int((frame["verdict"] == "hurts funding").sum()),
        "funding_neutral": int((frame["verdict"] == "funding neutral").sum()),
        "median_interest_per_extra_funded_rupee": float(
            frame["interest_per_extra_funded_rupee"].median(skipna=True)
        ) if frame["interest_per_extra_funded_rupee"].notna().any() else float("nan"),
    }])


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=None)
    parser.add_argument("--config", default="corrected_accounting",
                        choices=["archived", "corrected_accounting", "lp_parity", "recommended"])
    parser.add_argument("--split", default="test", choices=["all", "train", "test"])
    parser.add_argument("--tag", default=None)
    args = parser.parse_args(argv)

    paths = ProjectPaths.resolve(args.project_root).ensure_output_dirs().add_to_sys_path()
    config = getattr(GoalPilotConfig, args.config)()

    profiles = pd.read_csv(paths.rl_profiles_csv)
    goals = pd.read_csv(paths.rl_goals_csv)
    market = pd.read_csv(paths.rl_market_csv)
    split = pd.read_csv(paths.rl_split_csv)

    if args.split == "all":
        user_ids = profiles["user_id"].astype(str).tolist()
    else:
        wanted = set(split.loc[split["split"] == args.split, "user_id"].astype(str))
        user_ids = [u for u in profiles["user_id"].astype(str) if u in wanted]
        profiles = profiles[profiles["user_id"].astype(str).isin(wanted)].copy()
        goals = goals[goals["user_id"].astype(str).isin(wanted)].copy()

    env = goalpilot_env.GoalPilotEnv(
        profiles=profiles, goals=goals, market=market,
        user_ids=user_ids, config=config,
    )

    records = []
    for uid in user_ids:
        for policy in (SAVINGS_ONLY, HALF_SAVINGS, SAVINGS_AND_LOAN,
                       SAVINGS_ONLY_MAX_LOAN):
            records.append(rollout(env, uid, policy=policy))
    detail = pd.DataFrame(records)

    frames = {}
    frames["savings_vs_savings_and_loan"] = build_frame(
        detail, detail, (SAVINGS_ONLY, SAVINGS_AND_LOAN))
    # Isolating comparison: the two policies differ ONLY in the loan request, so every
    # difference is attributable to borrowing.
    frames["half_savings_vs_half_savings_and_loan"] = build_frame(
        detail, detail, (HALF_SAVINGS, SAVINGS_AND_LOAN))

    tag = args.tag or f"{args.config}_{args.split}"
    summary_rows = []
    for key, frame in frames.items():
        path = paths.evaluation_out / f"borrowing_audit_{key}_{tag}.csv"
        frame.to_csv(path, index=False)
        summary = summarise(frame)
        summary.insert(0, "comparison", key)
        summary_rows.append(summary)
        print(f"=== Borrowing audit: {key} (config={args.config}, split={args.split}) ===")
        print(frame[["user_id", "loan_principal", "interest_paid", "funding_ratio_no_loan",
                     "funding_ratio_with_loan", "funding_delta", "net_worth_delta",
                     "interest_per_extra_funded_rupee", "verdict"]]
              .round(4).to_string(index=False))
        print()
        print(summary.round(4).to_string(index=False))
        print(f"wrote {path}\n")

    summary_df = pd.concat(summary_rows, ignore_index=True)
    summary_path = paths.evaluation_out / f"borrowing_audit_summary_{tag}.csv"
    summary_df.to_csv(summary_path, index=False)
    print(f"wrote {summary_path}")

    # ledger sanity: with a correct ledger, borrowing alone must not create net worth
    max_nw_delta = float(
        frames["half_savings_vs_half_savings_and_loan"]["net_worth_delta"].max()
    )
    print(f"\nmax net-worth change attributable to borrowing alone: {max_nw_delta:,.2f}")
    if config.accounting_mode == "legacy":
        print("NOTE: accounting_mode='legacy' inflates this figure (finding F-04).")
    (paths.evaluation_out / f"borrowing_audit_meta_{tag}.json").write_text(
        json.dumps({"config": config.to_dict(), "split": args.split,
                    "max_net_worth_delta_from_borrowing": max_nw_delta}, indent=2),
        encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
