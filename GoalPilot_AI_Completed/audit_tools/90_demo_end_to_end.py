"""Phase M10/M11 - reproducible end-to-end demo across feasible / partial / infeasible users.

Selects one user of each kind by an explicit deterministic rule, executes the
capacity-constrained LP plan through the environment, and writes a grounded explanation
(`goalpilot_explain`) for each.

Classification (deterministic)
    surplus   = monthly_income - monthly_expenditure - monthly_emi
    ceiling   = surplus * max(goal horizon in months)      # gross cash flow available over the
                                                            # longest goal's horizon
    target    = sum over goals of current_cost * 1.03**(months/12)   # inflated targets
    infeasible : surplus <= 0
    feasible   : surplus > 0 and ceiling >= target
    partial    : surplus > 0 and ceiling <  target

Outputs
    outputs/demo/<class>_<user_id>.md      the rendered explanation
    outputs/demo/demo_summary.json         the classification + headline numbers
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from goalpilot_paths import ProjectPaths  # noqa: E402

paths = ProjectPaths.resolve()
paths.add_to_sys_path()
sys.path.insert(0, str(paths.root / "GoalPilot_MultiGoal_Extension"))

import goalpilot_env  # noqa: E402
import goalpilot_explain as ge  # noqa: E402
from goalpilot_config import GoalPilotConfig  # noqa: E402

OUT = paths.root / "outputs" / "demo"
OUT.mkdir(parents=True, exist_ok=True)

profiles = pd.read_csv(paths.rl_profiles_csv)
goals = pd.read_csv(paths.rl_goals_csv)
market = pd.read_csv(paths.rl_market_csv)

_spec = importlib.util.spec_from_file_location(
    "clp56", ROOT / "audit_tools" / "56_constrained_lp_comparison.py")
clp56 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(clp56)

CONFIG = GoalPilotConfig.recommended()
INFLATION = 0.03


def classify() -> dict[str, list[str]]:
    buckets = {"feasible": [], "partial": [], "infeasible": []}
    for uid in sorted(profiles["user_id"].astype(str).unique()):
        p = profiles.loc[profiles["user_id"].astype(str) == uid].iloc[0]
        g = goals.loc[goals["user_id"].astype(str) == uid]
        surplus = (float(p["monthly_income"]) - float(p["monthly_expenditure"])
                   - float(p["monthly_emi"]))
        months = int(g["time_horizon_months"].max()) if len(g) else 0
        target = float(np.sum(g["current_cost"].to_numpy(dtype=float)
                              * (1.0 + INFLATION) ** (g["time_horizon_months"].to_numpy(dtype=float) / 12.0)))
        if surplus <= 0:
            buckets["infeasible"].append(uid)
        elif surplus * max(months, 1) >= target:
            buckets["feasible"].append(uid)
        else:
            buckets["partial"].append(uid)
    return buckets


def main() -> None:
    buckets = classify()
    picks = {k: (v[0] if v else None) for k, v in buckets.items()}

    summary = {"config_preset": "recommended", "buckets": {k: len(v) for k, v in buckets.items()},
               "selected": picks, "scenarios": []}

    for kind, uid in picks.items():
        if uid is None:
            continue
        env = goalpilot_env.GoalPilotEnv(profiles=profiles, goals=goals, market=market,
                                        user_ids=[uid], config=CONFIG)
        plan = clp56.plan_for(uid, "constrained_LP")
        static_action = plan["action"]

        def action_fn(env_, _a=static_action):
            return _a

        variants = [ge.Variant("capacity x0.5", capacity_multiplier=0.5),
                    ge.Variant("market path x0.5", nifty_multiplier=0.5)]
        sens = ge.sensitivity(profiles, goals, market, uid, CONFIG, action_fn, variants)
        ex = ge.explain(env, uid, action_fn, sensitivity=sens)

        md = ge.render_markdown(ex)
        (OUT / f"{kind}_{uid}.md").write_text(md, encoding="utf-8")

        f = ex["facts"]
        summary["scenarios"].append({
            "kind": kind, "user_id": uid,
            "investable_surplus": f["profile"]["investable_surplus"],
            "n_goals": f["totals"]["n_goals"],
            "total_target": f["totals"]["total_target"],
            "total_funded": f["totals"]["total_funded"],
            "total_shortfall": f["totals"]["total_shortfall"],
            "weighted_achievement": f["totals"]["weighted_achievement"],
            "net_worth": f["balance_sheet"]["net_worth"],
            "sensitivity_note": ex["sections"]["sensitivity"][0][:160],
            "file": str(OUT / f"{kind}_{uid}.md"),
        })

    (OUT / "demo_summary.json").write_text(json.dumps(summary, indent=2, default=str),
                                           encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
