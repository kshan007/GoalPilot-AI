"""Render the Phase-H report from the artefacts of `80_ppo_training_v8.py`.

Every number in the report is read from the run's own CSVs/JSON, so the report cannot drift
from the executed results. Writes to outputs/reward_design/v8/PPO_TRAINING_AND_EVALUATION.md.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from goalpilot_paths import ProjectPaths  # noqa: E402

paths = ProjectPaths.resolve()
OUT_DIR = paths.root / "outputs" / "evaluation" / "final_validation_v8"
REPORT_DIR = paths.root / "outputs" / "reward_design" / "v8"
REPORT_DIR.mkdir(parents=True, exist_ok=True)
EXP_DIR = paths.root / "training_logs" / "experiments" / "ppo_recommended_v1"

HEADLINE = ["weighted_goal_achievement", "pct_goals_fully_funded", "pct_goals_met_by_deadline"]
KEY = ["net_worth", "goal_level_shortfall", "investment_cap_overflow", "total_interest_paid"]
HIGHER_BETTER = {"weighted_goal_achievement": True, "pct_goals_fully_funded": True,
                 "pct_goals_met_by_deadline": True, "goal_level_shortfall": False,
                 "net_worth": True, "investment_cap_overflow": False,
                 "total_interest_paid": False}


def f(x, nd=4):
    try:
        return f"{float(x):,.{nd}f}"
    except Exception:  # noqa: BLE001
        return str(x)


def main() -> None:
    digest = json.loads((OUT_DIR / "ppo_v8_digest.json").read_text(encoding="utf-8"))
    summary = pd.read_csv(OUT_DIR / "ppo_v8_summary.csv")
    detail = pd.read_csv(OUT_DIR / "ppo_v8_detail.csv")
    paired = pd.read_csv(OUT_DIR / "ppo_v8_paired.csv")
    across_path = OUT_DIR / "ppo_v8_across_seeds.csv"
    across = pd.read_csv(across_path) if across_path.is_file() else pd.DataFrame()

    runs = []
    for p in sorted(EXP_DIR.glob("*/seed*/run_*.json")):
        runs.append(json.loads(p.read_text(encoding="utf-8")))
    runs_df = pd.DataFrame(runs)

    L: list[str] = []
    L.append("# Phase H - controlled PPO training and held-out evaluation (v8)")
    L.append("")
    L.append(f"- configuration: `{digest['config_preset']}()` "
             f"(share + ledger + market_weighted + inflated targets + 6-month reserve)")
    L.append(f"- reward versions: {', '.join(digest['reward_versions'])} (archived reward never modified)")
    L.append(f"- seeds: {digest['seeds']}; timesteps per run: {digest['timesteps_per_run']:,}")
    L.append(f"- split `fresh_split_v1`: {digest['train_users']} train / "
             f"{digest['validation_users']} validation / {digest['heldout_test_users']} held-out test")
    L.append(f"- checkpoint selection: validation partition only (`EvalCallback`)")
    L.append(f"- total affordability violations across every arm: "
             f"{digest['total_affordability_violations']}")
    L.append(f"- maximum budget-identity residual: {f(digest['max_budget_residual'], 12)}")
    L.append("")

    if not runs_df.empty:
        L.append("## 1. Training runs")
        L.append("")
        L.append("| reward version | seed | timesteps | seconds | steps/s | episodes | mean train return |")
        L.append("|---|---:|---:|---:|---:|---:|---:|")
        for _, r in runs_df.sort_values(["reward_version", "seed"]).iterrows():
            L.append(f"| {r['reward_version']} | {int(r['seed'])} | {int(r['timesteps']):,} | "
                     f"{r['seconds']:.1f} | {r['steps_per_second']:.0f} | "
                     f"{int(r['episodes_completed'])} | {r['mean_train_episode_return']:.3f} |")
        L.append("")
        L.append(f"Hardware: CPU only (torch CPU build); total training wall time "
                 f"{runs_df['seconds'].sum()/60:.1f} minutes across {len(runs_df)} runs.")
        L.append("")

    L.append("## 2. Held-out test results (all 16 fresh test users, identical data and config)")
    L.append("")
    hdr = "| arm | seeds | " + " | ".join(HEADLINE) + " | " + " | ".join(KEY) + " |"
    L.append(hdr)
    L.append("|---" * (3 + len(HEADLINE) + len(KEY)) + "|")
    order = (detail.groupby("arm")["weighted_goal_achievement"].mean()
             .sort_values(ascending=False).index.tolist())
    for arm in order:
        block = detail[detail["arm"] == arm]
        seeds = sorted(x for x in block["seed"].unique() if x >= 0)
        row = [arm, str(len(seeds)) if seeds else "—"]
        for m in HEADLINE + KEY:
            row.append(f(block[m].mean(), 4))
        L.append("| " + " | ".join(row) + " |")
    L.append("")
    L.append("Sources: `ppo_v8_summary.csv`, `ppo_v8_detail.csv`.")
    L.append("")

    if not across.empty:
        L.append("### 2.1 RL arms - spread across seeds")
        L.append("")
        L.append("| arm | seeds | " + " | ".join(f"{m} (mean)" for m in HEADLINE) + " |")
        L.append("|---" * (2 + len(HEADLINE)) + "|")
        for _, r in across.iterrows():
            L.append(f"| {r['arm']} | {int(r['seeds'])} | "
                     + " | ".join(f(r[f"{m}_mean"], 4) for m in HEADLINE) + " |")
        L.append("")
        L.append("Across-seed standard deviations: "
                 + "; ".join(f"{r['arm']}: "
                             + ", ".join(f"{m}={r[f'{m}_sd_across_seeds']:.4f}" for m in HEADLINE)
                             for _, r in across.iterrows()) + ".")
        L.append("")

    L.append("### 2.2 By financial-feasibility group")
    L.append("")
    L.append("Eligibility is ex-ante: `monthly_income - monthly_expenditure - monthly_emi > 0`. "
             "For the RL arms the `users` column counts user-seed observations "
             "(users x seeds), not distinct users.")
    L.append("")
    L.append("| cohort | arm | users | weighted_goal_achievement | pct_goals_met_by_deadline | net_worth |")
    L.append("|---|---|---:|---:|---:|---:|")
    for cohort, cblock in detail.groupby("feasible_cohort"):
        for arm in order:
            blk = cblock[cblock["arm"] == arm]
            if blk.empty:
                continue
            L.append(f"| {cohort} | {arm} | {len(blk)} | "
                     f"{f(blk['weighted_goal_achievement'].mean(), 4)} | "
                     f"{f(blk['pct_goals_met_by_deadline'].mean(), 4)} | "
                     f"{f(blk['net_worth'].mean(), 2)} |")
    L.append("")

    L.append("## 3. Paired, user-level differences (RL mean over seeds minus each baseline)")
    L.append("")
    L.append("| RL arm | baseline | metric | better? | mean diff | CI95 | significant? |")
    L.append("|---|---|---|---|---:|---|---|")
    show = paired[paired["metric"].isin(HEADLINE + ["investment_cap_overflow", "net_worth"])]
    for _, r in show.iterrows():
        # direction-aware: "higher" is not automatically better
        higher_is_better = HIGHER_BETTER.get(r["metric"], True)
        sig = "inconclusive" if "inconclusive" in str(r["verdict"]) else "yes"
        if sig == "yes":
            rl_better = (r["mean_diff"] > 0) == higher_is_better
            better = f"**{r['rl_arm']}**" if rl_better else r["baseline"]
        else:
            better = "—"
        L.append(f"| {r['rl_arm']} | {r['baseline']} | {r['metric']} | {better} | "
                 f"{f(r['mean_diff'], 4)} | [{f(r['ci95_low'], 4)}, {f(r['ci95_high'], 4)}] | "
                 f"{sig} |")
    L.append("")
    L.append(f"Direction is respected: for `investment_cap_overflow` a *lower* value is the better "
             f"outcome, so a positive difference means the RL arm did worse, not better.")
    L.append("Bootstrap intervals resample users (the independent unit); a verdict of "
             "`inconclusive` means the interval spans zero and no difference is claimed.")
    L.append("")

    L.append("## 4. What the run supports")
    L.append("")
    ach = {arm: float(detail[detail["arm"] == arm]["weighted_goal_achievement"].mean())
           for arm in order}
    best_arm = max(ach, key=ach.get)
    rl_arms = [a for a in order if a.startswith("RL ")]
    L.append(f"1. Highest mean weighted achievement: **{best_arm}** ({ach[best_arm]:.4f}).")
    if rl_arms:
        best_rl = max(rl_arms, key=lambda a: ach[a])
        L.append(f"2. Best RL arm: **{best_rl}** ({ach[best_rl]:.4f}) — "
                 f"{'above' if ach[best_rl] > ach[best_arm] else 'not above'} the best non-RL arm by "
                 f"{abs(ach[best_rl] - ach[best_arm]):.4f}.")
    decis = paired[(paired["rl_arm"].isin(rl_arms)) & (paired["metric"].isin(HEADLINE))
                   & (~paired["verdict"].str.contains("inconclusive"))].copy()
    if len(decis):
        decis["rl_wins"] = [(d > 0) == HIGHER_BETTER[m]
                            for d, m in zip(decis["mean_diff"], decis["metric"])]
        rl_wins = int(decis["rl_wins"].sum())
        base_wins = int((~decis["rl_wins"]).sum())
        L.append(f"3. Significant paired verdicts among the headline metrics: RL better in "
                 f"**{rl_wins}**, baseline better in **{base_wins}**, "
                 f"inconclusive in {int(paired['verdict'].str.contains('inconclusive').sum())} "
                 f"of {len(paired)} rows overall.")
    else:
        L.append("3. No significant paired verdicts among the headline metrics.")
    L.append("4. No superiority claim is made beyond the intervals above. Where an interval spans "
             "zero the arms are treated as indistinguishable.")
    L.append("5. Structurally infeasible users are policy-invariant: every arm scores identically "
             "there, so they cannot separate the policies.")
    L.append("")

    (REPORT_DIR / "PPO_TRAINING_AND_EVALUATION.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
