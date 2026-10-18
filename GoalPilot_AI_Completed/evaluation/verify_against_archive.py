"""Verify the new shared evaluator against the archived result files.

The audit changed `goalpilot_env.py` and replaced five ad-hoc evaluation loops with one
shared evaluator (`policy_evaluation.py`). This script proves the replacement is
faithful: in `GoalPilotConfig.archived()` mode it must reproduce the archived CSVs.

It compares, field by field:

  * ``rl_baseline_policy_comparison.csv``        (100 users, Mixed = 0.25/0.25)
  * ``rl_policy_diagnostic_summary.csv``         (100 users, Mixed = 0.25/0.25)
  * ``rl_heldout_policy_comparison_summary.csv`` (20 test users, Mixed = 0.50/0.50, incl. PPO)

Non-matching rows are reported, never silently ignored.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

from goalpilot_paths import ProjectPaths

# archived column -> new column
DETAIL_MAP = {
    "goal_funding_ratio": "goal_funding_ratio",
    "final_goal_funding": "goal_funding_amount",
    "final_cash": "final_cash",
    "final_portfolio": "final_portfolio",
    "final_loan_balance": "final_loan_balance",
    "final_net_financial_wealth": "net_worth_ledger",
    "total_savings_contributions": "total_savings_contributions",
    "total_investment_contributions": "total_investment_contributions",
    "total_new_loan_principal": "total_new_loan_principal",
    "total_reward": "total_reward",
    "max_budget_excess": "max_budget_excess",
    "max_goal_overshoot": "max_goal_overshoot",
}

# Archived policy label -> new policy label, where they differ.
#
# IMPORTANT: the archive was *internally inconsistent* about "Mixed allocation".
# The 100-user tables used (0.25, 0.25); the held-out tables used (0.50, 0.50).
# A naive comparison that mapped both onto one label would silently compare the wrong
# policy — which is exactly the kind of ambiguity this verification exists to catch.
ALIASES_100_USERS = {
    "Mixed allocation": "Mixed allocation (0.25/0.25)",
    "PPO (best checkpoint)": "PPO",
}
ALIASES_HELDOUT = {
    "Mixed allocation": "Mixed allocation (0.50/0.50)",
    "PPO (best checkpoint)": "PPO",
}

SUMMARY_MAP = {
    "mean_goal_funding_ratio": "mean_goal_funding_ratio",
    "median_goal_funding_ratio": "median_goal_funding_ratio",
    "mean_final_portfolio": "mean_final_portfolio",
    "mean_final_loan_balance": "mean_final_loan_balance",
    "mean_total_reward": "mean_total_reward",
}

TOLERANCE = 1e-8


def _report(name: str, mismatches: list[str], compared: int) -> dict:
    status = "PASS" if not mismatches else "FAIL"
    print(f"[{status}] {name}: {compared} field-comparisons, "
          f"{len(mismatches)} mismatch(es)")
    for line in mismatches[:25]:
        print("        " + line)
    if len(mismatches) > 25:
        print(f"        ... and {len(mismatches) - 25} more")
    return {"check": name, "status": status, "comparisons": compared,
            "mismatches": len(mismatches), "examples": mismatches[:10]}


def compare_detail(archived_path: Path, new_path: Path, aliases: dict) -> dict:
    if not archived_path.exists():
        print(f"[SKIP] {archived_path.name} not present")
        return {"check": archived_path.name, "status": "SKIP", "comparisons": 0,
                "mismatches": 0, "examples": []}
    old = pd.read_csv(archived_path)
    new = pd.read_csv(new_path)
    old["_new_policy"] = old["policy"].map(lambda p: aliases.get(p, p))

    # Rename explicitly instead of relying on merge suffixes, so a column present in only
    # one frame keeps a deterministic name.
    old_renamed = old.rename(columns={c: f"OLD__{c}" for c in old.columns})
    old_renamed["user_id"] = old["user_id"]
    old_renamed["_new_policy"] = old["_new_policy"]

    merged = old_renamed.merge(
        new, left_on=["user_id", "_new_policy"], right_on=["user_id", "policy"],
        how="left", indicator=True,
    )
    unmatched = int((merged["_merge"] == "left_only").sum())
    mismatches: list[str] = []
    compared = 0
    if unmatched:
        missing = sorted(merged.loc[merged["_merge"] == "left_only", "_new_policy"].unique())
        mismatches.append(f"{unmatched} archived rows have no counterpart; policies={missing}")
    for old_col, new_col in DETAIL_MAP.items():
        old_key = f"OLD__{old_col}"
        if old_key not in merged.columns or new_col not in merged.columns:
            continue
        for _, row in merged.iterrows():
            if row["_merge"] != "both":
                continue
            a, b = row[old_key], row[new_col]
            if pd.isna(a) and pd.isna(b):
                continue
            compared += 1
            if not np.isclose(a, b, rtol=0, atol=TOLERANCE):
                mismatches.append(
                    f"{row['user_id']}/{row['_new_policy']} {old_col}: "
                    f"archived={a!r} new={b!r} diff={abs(a - b):.3e}"
                )
    return _report(f"{archived_path.name} vs {new_path.name}", mismatches, compared)


def compare_summary(archived_path: Path, new_path: Path, aliases: dict,
                    include: dict[str, str] | None = None) -> dict:
    if not archived_path.exists():
        print(f"[SKIP] {archived_path.name} not present")
        return {"check": archived_path.name, "status": "SKIP", "comparisons": 0,
                "mismatches": 0, "examples": []}
    old = pd.read_csv(archived_path)
    new = pd.read_csv(new_path)
    old["_new_policy"] = old["policy"].map(lambda p: aliases.get(p, p))
    mapping = include or SUMMARY_MAP

    mismatches: list[str] = []
    compared = 0
    for _, orow in old.iterrows():
        match = new.loc[new["policy"] == orow["_new_policy"]]
        if match.empty:
            mismatches.append(f"no new row for archived policy {orow['policy']!r}")
            continue
        nrow = match.iloc[0]
        for old_col, new_col in mapping.items():
            if old_col not in old.columns or new_col not in new.columns:
                continue
            a, b = orow[old_col], nrow[new_col]
            if pd.isna(a) and pd.isna(b):
                continue
            compared += 1
            if not np.isclose(a, b, rtol=0, atol=TOLERANCE):
                mismatches.append(
                    f"{orow['policy']} {old_col}: archived={a!r} new={b!r} "
                    f"diff={abs(a - b):.3e}"
                )
    return _report(f"{archived_path.name} vs {new_path.name}", mismatches, compared)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=None)
    args = parser.parse_args(argv)

    paths = ProjectPaths.resolve(args.project_root).ensure_output_dirs().add_to_sys_path()
    archive = paths.rl_prototype
    out = paths.evaluation_out

    results = [
        compare_detail(archive / "rl_baseline_policy_comparison.csv",
                       out / "policy_detail_archived_all.csv", ALIASES_100_USERS),
        compare_summary(archive / "rl_policy_diagnostic_summary.csv",
                        out / "policy_summary_archived_all.csv", ALIASES_100_USERS),
        compare_detail(archive / "rl_heldout_policy_comparison_detail.csv",
                       out / "policy_detail_archived_test.csv", ALIASES_HELDOUT),
        compare_summary(archive / "rl_heldout_policy_comparison_summary.csv",
                        out / "policy_summary_archived_test.csv", ALIASES_HELDOUT),
    ]

    report = {
        "tolerance": TOLERANCE,
        "overall": "PASS" if all(r["status"] in ("PASS", "SKIP") for r in results) else "FAIL",
        "checks": results,
    }
    report_path = out / "archive_verification.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nOVERALL: {report['overall']}")
    print(f"wrote {report_path}")
    return 0 if report["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
