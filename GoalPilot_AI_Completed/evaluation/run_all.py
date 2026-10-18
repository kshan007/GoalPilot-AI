"""One-command reproduction of every evaluation artefact.

    python evaluation/run_all.py --project-root .

Sequence
--------
1. verify the reworked environment reproduces the archived results exactly
2. policy evaluation, archived configuration — all users and held-out users
3. policy evaluation, corrected ledger
4. policy evaluation, LP-parity basis
5. action-mode comparison (magnitude vs share) — the F-02 fix
6. reward decomposition
7. borrowing audit, corrected ledger and legacy accounting
8. plots

Everything is written under ``outputs/evaluation`` and ``outputs/plots``. The script
never writes into the archived result folders.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path
from typing import Sequence

import pandas as pd

from goalpilot_config import GoalPilotConfig
from goalpilot_paths import ProjectPaths
from policy_evaluation import BASELINE_POLICIES, PolicySpec, evaluate, summarise
import goalpilot_env

HERE = Path(__file__).resolve().parent


def _run(script: str, *args: str) -> int:
    command = [sys.executable, str(HERE / script), *args]
    print(f"\n$ {' '.join(command[1:])}")
    started = time.time()
    result = subprocess.run(command, cwd=str(HERE.parent))
    print(f"  exit={result.returncode}  ({time.time() - started:.1f}s)")
    return result.returncode


def action_mode_comparison(paths: ProjectPaths, split: str) -> pd.DataFrame:
    """Compare funding under magnitude vs share semantics for a set of fixed policies."""
    profiles = pd.read_csv(paths.rl_profiles_csv)
    goals = pd.read_csv(paths.rl_goals_csv)
    market = pd.read_csv(paths.rl_market_csv)
    split_df = pd.read_csv(paths.rl_split_csv)

    if split == "all":
        user_ids = profiles["user_id"].astype(str).tolist()
    else:
        wanted = set(split_df.loc[split_df["split"] == split, "user_id"].astype(str))
        user_ids = [u for u in profiles["user_id"].astype(str) if u in wanted]
        profiles = profiles[profiles["user_id"].astype(str).isin(wanted)].copy()
        goals = goals[goals["user_id"].astype(str).isin(wanted)].copy()

    policies = (
        PolicySpec("Flat 0.25 savings", 0.25, 0.0, 0.0),
        PolicySpec("Flat 0.50 savings", 0.50, 0.0, 0.0),
        PolicySpec("Flat 0.75 savings", 0.75, 0.0, 0.0),
        PolicySpec("Savings only", 1.00, 0.0, 0.0),
        PolicySpec("Mixed allocation (0.50/0.50)", 0.50, 0.50, 0.0),
    )

    frames = []
    for mode in ("magnitude", "share"):
        config = GoalPilotConfig.lp_parity().replace(action_mode=mode)
        detail = evaluate(profiles, goals, market, user_ids, config, policies)
        summary = summarise(detail)
        summary.insert(0, "action_mode", mode)
        frames.append(summary)
    combined = pd.concat(frames, ignore_index=True)
    out = paths.evaluation_out / "action_mode_comparison.csv"
    combined.to_csv(out, index=False)
    print("\n=== Action-mode comparison ===")
    print(combined[["action_mode", "policy", "mean_goal_funding_ratio",
                    "mean_unallocated_surplus"]].round(4).to_string(index=False))
    print(f"wrote {out}")
    return combined


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=None)
    parser.add_argument("--skip-archive-verification", action="store_true")
    parser.add_argument("--include-ppo", action="store_true", default=True)
    parser.add_argument("--no-ppo", dest="include_ppo", action="store_false")
    args = parser.parse_args(argv)

    paths = ProjectPaths.resolve(args.project_root).ensure_output_dirs().add_to_sys_path()
    print(paths.describe())
    failures: list[str] = []
    ppo_flag = ["--include-ppo"] if args.include_ppo else []

    if not args.skip_archive_verification:
        if _run("verify_against_archive.py", "--project-root", str(paths.root)) != 0:
            failures.append("archive verification")

    for config in ("archived", "corrected_accounting", "lp_parity"):
        for split in ("all", "test"):
            code = _run("policy_evaluation.py", "--project-root", str(paths.root),
                        "--config", config, "--split", split, *ppo_flag,
                        "--tag", f"{config}_{split}")
            if code != 0:
                failures.append(f"policy_evaluation {config}/{split}")

    action_mode_comparison(paths, "test")

    for config in ("archived", "lp_parity"):
        if _run("reward_decomposition.py", "--project-root", str(paths.root),
                "--config", config, "--split", "test", *ppo_flag,
                "--tag", f"{config}_test") != 0:
            failures.append(f"reward_decomposition {config}")

    for config in ("corrected_accounting", "archived"):
        if _run("borrowing_audit.py", "--project-root", str(paths.root),
                "--config", config, "--split", "test",
                "--tag", f"{config}_test") != 0:
            failures.append(f"borrowing_audit {config}")

    if _run("make_plots.py", "--project-root", str(paths.root)) != 0:
        failures.append("make_plots")

    print("\n" + "=" * 70)
    if failures:
        print("COMPLETED WITH FAILURES: " + ", ".join(failures))
        return 1
    print("ALL EVALUATION STAGES COMPLETED")
    print(f"artefacts: {paths.evaluation_out}")
    print(f"plots    : {paths.plots_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
