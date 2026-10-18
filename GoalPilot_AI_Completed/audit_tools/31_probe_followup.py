"""Follow-up probe: attribute the episode reconciliation gap, and isolate whether
share mode can originate a loan under face-value crediting (no goal cap binding).
Read-only with respect to the project source.
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

profiles = pd.read_csv(paths.rl_profiles_csv)
goals = pd.read_csv(paths.rl_goals_csv)
market = pd.read_csv(paths.rl_market_csv)
split = pd.read_csv(paths.rl_split_csv)
test_users = [u for u in profiles["user_id"].astype(str)
              if u in set(split.loc[split["split"] == "test", "user_id"].astype(str))]

ledger = pd.read_csv(OUT / "D1_D4_D5_ledger_by_policy.csv")
events = pd.read_csv(OUT / "D1_loan_amortisation_events.csv")
written = events[events["silently_written_off"]] if len(events) else events

# ---- attribute the reconciliation residual to write-offs, per config ---------------
attrib = []
for cfg, grp in ledger.groupby("config"):
    w = written[written["tag"] == cfg] if len(written) else written
    attrib.append({
        "config": cfg,
        "max_abs_episode_recon_residual": float(grp["episode_recon_residual"].abs().max()),
        "sum_writeoff_residual": float(w["residual_unamortised"].sum()) if len(w) else 0.0,
        "n_writeoffs": int(len(w)),
        "sum_residual_all_events": float(events[events["tag"] == cfg]["residual_unamortised"].sum())
        if len(events) else 0.0,
    })
attrib_df = pd.DataFrame(attrib)
attrib_df.to_csv(OUT / "D5_recon_attribution.csv", index=False)
print("=== reconciliation attribution ===")
print(attrib_df.to_string(index=False))

# ---- D2b: share + FACE VALUE, savings-only positive action, can a loan originate? --
d2b = []
for mode in ("magnitude", "share"):
    for credit in ("face_value", "growth_weighted"):
        cfg = (GoalPilotConfig.lp_parity()
               .replace(action_mode=mode, goal_credit_mode=credit))
        env = goalpilot_env.GoalPilotEnv(profiles=profiles, goals=goals, market=market,
                                         user_ids=test_users, config=cfg)
        for pol_name, pol in (("Savings+loan (0.5,0,1)", (0.5, 0.0, 1.0)),
                              ("Loan only (0,0,1)", (0.0, 0.0, 1.0))):
            months_with_loan = 0
            total_loan = 0.0
            for uid in test_users:
                env.reset(options={"user_id": uid})
                while True:
                    a = np.zeros(env.action_space.shape, dtype=np.float32)
                    a[:, 0], a[:, 1], a[:, 2] = pol
                    _, _, term, trunc, info = env.step(a)
                    if info["new_loan_principal"] > 1e-6:
                        months_with_loan += 1
                        total_loan += float(info["new_loan_principal"])
                    if term or trunc:
                        break
            d2b.append({"action_mode": mode, "goal_credit": credit, "policy": pol_name,
                        "months_with_loan": months_with_loan, "total_loan": total_loan})
d2b_df = pd.DataFrame(d2b)
d2b_df.to_csv(OUT / "D2b_share_face_value_borrowing.csv", index=False)
print("\n=== D2b share x credit-mode borrowing (20 users) ===")
print(d2b_df.to_string(index=False))

# ---- D6: is the emergency reserve represented on the balance sheet? ----------------
probe = []
for cfg_name, cfg in (("lp_parity", GoalPilotConfig.lp_parity()),
                      ("recommended", GoalPilotConfig.recommended())):
    env = goalpilot_env.GoalPilotEnv(profiles=profiles, goals=goals, market=market,
                                     user_ids=test_users, config=cfg)
    for uid in test_users[:5]:
        env.reset(options={"user_id": uid})
        p = env.profile_map[uid]
        initial_savings = float(p["initial_savings"])
        earmark = float(env.goal_balances.sum())
        reserve = float(env.emergency_reserve)
        probe.append({
            "config": cfg_name, "user_id": uid,
            "initial_savings": initial_savings,
            "emergency_reserve": reserve,
            "earmarked": earmark,
            "cash_at_reset": float(env.cash),
            "portfolio_at_reset": float(env.portfolio),
            "initial_net_worth": float(env.initial_net_worth),
            "on_balance_sheet": float(env.cash) + float(env.portfolio),
            "reserve_off_balance_sheet": initial_savings - (float(env.cash) + float(env.portfolio)),
        })
probe_df = pd.DataFrame(probe)
probe_df.to_csv(OUT / "D6_emergency_reserve_balance_sheet.csv", index=False)
print("\n=== D6 emergency reserve on/off balance sheet ===")
print(probe_df.to_string(index=False))

summary = {"recon_attribution": attrib, "d2b_borrowing": d2b,
           "d6_reserve": probe_df.to_dict("records")}
(OUT / "probe_followup_summary.json").write_text(
    json.dumps(summary, indent=2, default=str), encoding="utf-8")
print(f"\nwrote follow-up outputs to {OUT}")
