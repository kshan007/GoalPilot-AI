"""Read-only defect probe for the GoalPilot final RL validation (Phase A/B).

This script does NOT modify the environment. It instruments the *existing* public
surface (``info``, ``env`` attributes) to establish, with recorded numbers, whether
the following suspected defects are real:

  D1  A residual loan balance is silently written off when the tenure expires.
  D2  ``action_mode="share"`` structurally prevents loan origination.
  D3  ``goal_credit_mode="growth_weighted"`` credits *projected* future returns as
      realised goal assets while the real NIFTY portfolio is credited separately.
  D4  Unallocated surplus is / is not represented in an actual asset account.
  D5  The net-worth reconciliation residual over a whole episode.

Outputs land in ``outputs/audit/final_validation_v1/`` (new, versioned; nothing
historical is overwritten).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from goalpilot_paths import ProjectPaths  # noqa: E402

paths = ProjectPaths.resolve().ensure_output_dirs().add_to_sys_path()
from goalpilot_config import GoalPilotConfig  # noqa: E402
import goalpilot_env  # noqa: E402

OUT = paths.audit_out / "final_validation_v1"
OUT.mkdir(parents=True, exist_ok=True)

profiles = pd.read_csv(paths.rl_profiles_csv)
goals = pd.read_csv(paths.rl_goals_csv)
market = pd.read_csv(paths.rl_market_csv)
split = pd.read_csv(paths.rl_split_csv)
test_users = [u for u in profiles["user_id"].astype(str)
              if u in set(split.loc[split["split"] == "test", "user_id"].astype(str))]
print(f"users: all={len(profiles)} test={len(test_users)} months={len(market)}")

POLICIES = {
    "No action": (0.0, 0.0, 0.0),
    "Savings only": (1.0, 0.0, 0.0),
    "Investments only": (0.0, 1.0, 0.0),
    "Mixed 0.50/0.50": (0.5, 0.5, 0.0),
    "Loan request only": (0.0, 0.0, 1.0),
    "Savings + loan": (0.5, 0.0, 1.0),
    "Savings only + max loan": (1.0, 0.0, 1.0),
}


def make_env(config, user_ids):
    return goalpilot_env.GoalPilotEnv(
        profiles=profiles, goals=goals, market=market,
        user_ids=user_ids, config=config,
    )


def run(env, uid, policy, tag):
    """Roll one episode, recording every loan-write-off event and ledger totals."""
    s, i, loan = policy
    env.reset(options={"user_id": uid})
    nw_start = env.net_worth
    events = []
    months = []
    while True:
        prev_balance = float(env.loan_balance)
        prev_months_left = int(env.loan_months_left)
        action = np.zeros(env.action_space.shape, dtype=np.float32)
        action[:, 0], action[:, 1], action[:, 2] = s, i, loan
        obs, reward, term, trunc, info = env.step(action)
        ba = info["budget_audit"]
        interest = float(info["interest_paid"])
        paid = float(ba["env_loan_emi_paid"])
        months_left_after = int(env.loan_months_left)
        balance_after = float(env.loan_balance)
        # residual that the amortisation could not retire this month
        residual = max(0.0, prev_balance + interest - paid)
        if prev_months_left > 0 and residual > 1e-6:
            written_off = prev_months_left - 1 == 0 and balance_after == 0.0
            events.append({
                "user_id": uid, "tag": tag, "policy": f"{policy}",
                "month": int(ba["month"]),
                "balance_before": prev_balance,
                "interest_due": interest,
                "emi_paid": paid,
                "residual_unamortised": residual,
                "months_left_before": prev_months_left,
                "months_left_after": months_left_after,
                "balance_after": balance_after,
                "silently_written_off": bool(written_off),
            })
        months.append({
            "month": int(ba["month"]),
            "expected_nw_change": float(ba["expected_net_worth_change"]),
            "actual_nw_change": float(ba["net_worth_change"]),
            "unallocated_surplus": float(info["unallocated_surplus"]),
            "savings": float(info["savings_contribution"]),
            "invest": float(info["investment_contribution"]),
            "cash": float(info["cash"]),
            "portfolio": float(env.portfolio),
            "loan_balance": balance_after,
            "new_loan": float(info["new_loan_principal"]),
            "net_worth": float(env.net_worth),
        })
        if term or trunc:
            break
    df = pd.DataFrame(months)
    recon_residual = float((df["actual_nw_change"] - df["expected_nw_change"]).sum())
    return {
        "events": events,
        "detail": df,
        "nw_start": nw_start,
        "nw_end": float(env.net_worth),
        "recon_residual": recon_residual,
        "total_interest": float(env.total_interest_paid),
        "total_loan_principal": float(env.cumulative_loan_principal),
        "final_loan_balance": float(env.loan_balance),
        "total_unallocated": float(env.total_unallocated_surplus),
    }


# ---------------------------------------------------------------- D1 / D4 / D5 ------
all_events = []
ledger_rows = []
detail_frames = {}

for cfg_name, cfg in (("corrected_accounting", GoalPilotConfig.corrected_accounting()),
                      ("archived", GoalPilotConfig.archived()),
                      ("lp_parity", GoalPilotConfig.lp_parity()),
                      ("recommended", GoalPilotConfig.recommended())):
    env = make_env(cfg, test_users)
    for pname, pol in POLICIES.items():
        for uid in test_users:
            r = run(env, uid, pol, cfg_name)
            all_events.extend(r["events"])
            ledger_rows.append({
                "config": cfg_name, "policy": pname, "user_id": uid,
                "nw_start": r["nw_start"], "nw_end": r["nw_end"],
                "episode_recon_residual": r["recon_residual"],
                "total_interest": r["total_interest"],
                "total_loan_principal": r["total_loan_principal"],
                "final_loan_balance": r["final_loan_balance"],
                "total_unallocated": r["total_unallocated"],
                "writeoff_events": sum(e["silently_written_off"] for e in r["events"]),
                "max_residual": max([e["residual_unamortised"] for e in r["events"]] or [0.0]),
            })
            if cfg_name == "corrected_accounting" and pname == "Savings + loan":
                detail_frames[uid] = r["detail"]
    print(f"[{cfg_name}] done")

events_df = pd.DataFrame(all_events)
ledger_df = pd.DataFrame(ledger_rows)
events_df.to_csv(OUT / "D1_loan_amortisation_events.csv", index=False)
ledger_df.to_csv(OUT / "D1_D4_D5_ledger_by_policy.csv", index=False)

written = events_df[events_df["silently_written_off"]] if not events_df.empty else events_df
d1 = {
    "episodes_with_any_unamortised_residual": int((ledger_df["max_residual"] > 1e-6).sum()),
    "episodes_with_silent_writeoff": int((ledger_df["writeoff_events"] > 0).sum()),
    "episodes_total": int(len(ledger_df)),
    "writeoff_events_total": int(ledger_df["writeoff_events"].sum()),
    "max_residual_written_off": float(ledger_df["writeoff_events"].clip(lower=0).pipe(
        lambda s: s * 0).sum() + (written["residual_unamortised"].max() if len(written) else 0.0)),
    "sum_residual_written_off": float(written["residual_unamortised"].sum()) if len(written) else 0.0,
}
if len(written):
    d1["example_writeoff"] = written.sort_values("residual_unamortised", ascending=False).head(1).to_dict("records")[0]

# ---------------------------------------------------------------- D5 reconciliation --
d5 = {
    "max_abs_episode_recon_residual": float(ledger_df["episode_recon_residual"].abs().max()),
    "episodes_beyond_1e-6": int((ledger_df["episode_recon_residual"].abs() > 1e-6).sum()),
    "by_config": ledger_df.groupby("config")["episode_recon_residual"].apply(
        lambda s: float(s.abs().max())).to_dict(),
}

# ---------------------------------------------------------------- D2 share vs borrow --
d2_rows = []
for mode in ("magnitude", "share"):
    cfg = GoalPilotConfig.recommended().replace(action_mode=mode)
    env = make_env(cfg, test_users)
    for pol_name, pol in (("Savings + loan", (0.5, 0.0, 1.0)),
                          ("Savings only + max loan", (1.0, 0.0, 1.0)),
                          ("Loan request only", (0.0, 0.0, 1.0))):
        for uid in test_users:
            r = run(env, uid, pol, f"{mode}_{pol_name}")
            df = r["detail"]
            d2_rows.append({
                "action_mode": mode, "policy": pol_name, "user_id": uid,
                "months_with_loan_origination": int((df["new_loan"] > 1e-6).sum()),
                "total_new_loan": float(df["new_loan"].sum()),
                "final_funding_ratio": float(np.minimum(env.goal_balances, env.goal_targets).sum()
                                             / max(env.goal_targets.sum(), 1.0)),
            })
d2_df = pd.DataFrame(d2_rows)
d2_df.to_csv(OUT / "D2_share_mode_borrowing.csv", index=False)
d2 = {
    "mean_months_with_origination": {
        f"{a}|{b}": v for (a, b), v in d2_df.groupby(["action_mode", "policy"])[
            "months_with_loan_origination"].mean().items()},
    "users_originating_any_loan": {
        f"{a}|{b}": int(v) for (a, b), v in d2_df[d2_df["total_new_loan"] > 1e-6].groupby(
            ["action_mode", "policy"])["user_id"].nunique().items()},
}

# ---------------------------------------------------------------- D3 credit double count
d3_rows = []
for cfg_name, cfg in (("archived_face_value", GoalPilotConfig.archived()),
                      ("recommended_growth_weighted", GoalPilotConfig.recommended())):
    env = make_env(cfg, test_users)
    for uid in test_users:
        r = run(env, uid, (0.5, 0.5, 0.0), cfg_name)
        df = r["detail"]
        contributed = float(df["savings"].sum() + df["invest"].sum())
        # goal credit actually booked == sum of goal_balances at the end minus the earmark
        env.reset(options={"user_id": uid})
        while True:
            a = np.zeros(env.action_space.shape, dtype=np.float32)
            a[:, 0], a[:, 1] = 0.5, 0.5
            _, _, term, trunc, info = env.step(a)
            if term or trunc:
                break
        credited = float(env.goal_balances.sum() - (info.get("goal_balances", env.goal_balances)).sum() * 0)
        d3_rows.append({
            "config": cfg_name, "user_id": uid,
            "rupees_actually_contributed": contributed,
            "goal_funding_booked_total": float(env.goal_balances.sum()),
            "goal_funding_capped_at_target": float(np.minimum(env.goal_balances, env.goal_targets).sum()),
            "actual_portfolio_market_value": float(env.portfolio),
            "actual_investment_gain": float(env.total_investment_gain),
            "funding_ratio": float(np.minimum(env.goal_balances, env.goal_targets).sum()
                                   / max(env.goal_targets.sum(), 1.0)),
        })
d3_df = pd.DataFrame(d3_rows)
d3_df.to_csv(OUT / "D3_goal_credit_semantics.csv", index=False)
d3 = {c: {k: float(v) for k, v in sub.items()} for c, sub in
      d3_df.groupby("config")[["rupees_actually_contributed", "goal_funding_booked_total",
                               "actual_portfolio_market_value", "funding_ratio"]].mean().to_dict("index").items()}

summary = {"D1_residual_writeoff": d1, "D2_share_mode_borrowing": d2,
           "D3_goal_credit": d3, "D5_reconciliation": d5,
           "config_used": GoalPilotConfig.recommended().to_dict()}
(OUT / "probe_summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

print("\n=== D1 residual loan write-off ===")
print(json.dumps(d1, indent=2, default=str)[:2000])
print("\n=== D2 share-mode borrowing ===")
print(json.dumps(d2, indent=2, default=str))
print("\n=== D3 goal-credit semantics (means) ===")
print(json.dumps(d3, indent=2, default=str))
print("\n=== D5 reconciliation ===")
print(json.dumps(d5, indent=2, default=str))
print(f"\nwrote probe outputs to {OUT}")
