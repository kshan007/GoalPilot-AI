"""Generate the evaluation figures for the report and the FYP demonstration.

All figures are written as PNG into `outputs/plots/`. Uses the non-interactive Agg
backend so it runs headless on a build machine.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from goalpilot_paths import ProjectPaths

COMPONENTS = ("incremental_progress", "deadline_shortfall_penalty",
              "loan_penalty", "risk_penalty")
COLOURS = {
    "incremental_progress": "#2f7d32",
    "deadline_shortfall_penalty": "#c62828",
    "loan_penalty": "#ef6c00",
    "risk_penalty": "#6a1b9a",
}
DPI = 140


def _save(fig, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {path.name}")


def plot_funding_by_policy(summary: pd.DataFrame, path: Path, title: str) -> None:
    order = summary.sort_values("mean_goal_funding_ratio", ascending=True)
    fig, ax = plt.subplots(figsize=(9, 0.5 * len(order) + 2))
    colours = ["#1565c0" if "PPO" not in p else "#c62828" for p in order["policy"]]
    ax.barh(order["policy"], order["mean_goal_funding_ratio"], color=colours)
    for y, value in enumerate(order["mean_goal_funding_ratio"]):
        ax.text(value + 0.002, y, f"{value:.4f}", va="center", fontsize=9)
    ax.set_xlabel("Mean goal funding ratio")
    ax.set_title(title)
    ax.set_xlim(0, max(0.01, order["mean_goal_funding_ratio"].max() * 1.18))
    ax.grid(axis="x", alpha=0.3)
    _save(fig, path)


def plot_reward_components(summary: pd.DataFrame, path: Path, title: str) -> None:
    fig, ax = plt.subplots(figsize=(10, 5))
    policies = summary["policy"].tolist()
    x = np.arange(len(policies))
    bottom_pos = np.zeros(len(policies))
    bottom_neg = np.zeros(len(policies))

    for name in COMPONENTS:
        col = f"{name}__sum"
        if col not in summary.columns:
            continue
        values = summary[col].to_numpy()
        pos = np.where(values > 0, values, 0.0)
        neg = np.where(values < 0, values, 0.0)
        ax.bar(x, pos, bottom=bottom_pos, color=COLOURS[name], label=name)
        ax.bar(x, neg, bottom=bottom_neg, color=COLOURS[name])
        bottom_pos += pos
        bottom_neg += neg

    ax.plot(x, summary["total_reward_sum"], "ko-", markersize=5,
            label="total reward")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(policies, rotation=25, ha="right", fontsize=9)
    ax.set_ylabel("Reward summed over all user-months")
    ax.set_title(title)
    ax.legend(fontsize=8, ncol=2)
    ax.grid(axis="y", alpha=0.3)
    _save(fig, path)


def plot_borrowing(frame: pd.DataFrame, path: Path, title: str) -> None:
    loaned = frame[frame["loan_principal"] > 1e-6]
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    ax = axes[0]
    ax.scatter(loaned["loan_principal"], loaned["funding_delta"] * 100,
               c=np.where(loaned["funding_delta"] > 0, "#2f7d32", "#c62828"), s=48)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xlabel("Loan principal originated (₹)")
    ax.set_ylabel("Change in goal funding ratio (percentage points)")
    ax.set_title("Does borrowing fund goals?")
    ax.grid(alpha=0.3)

    ax = axes[1]
    ax.scatter(loaned["interest_paid"], loaned["net_worth_delta"],
               c="#1565c0", s=48)
    ax.set_xlabel("Interest paid (₹)")
    ax.set_ylabel("Change in net worth (₹)")
    ax.set_title("What does borrowing cost?")
    ax.grid(alpha=0.3)

    for ax in axes:
        pass
    fig.suptitle(title)
    _save(fig, path)


def plot_net_worth_double_count(summary: pd.DataFrame, path: Path, title: str) -> None:
    policies = summary["policy"].tolist()
    x = np.arange(len(policies))
    width = 0.38
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(x - width / 2, summary["mean_net_worth_ledger"], width,
           label="ledger net worth (correct)", color="#2f7d32")
    ax.bar(x + width / 2, summary["mean_net_worth_archived_aggregate"], width,
           label="archived aggregate (double counts)", color="#c62828", alpha=0.75)
    ax.set_xticks(x)
    ax.set_xticklabels(policies, rotation=25, ha="right", fontsize=9)
    ax.set_ylabel("Mean final net worth (₹)")
    ax.set_title(title)
    ax.legend(fontsize=9)
    ax.grid(axis="y", alpha=0.3)
    _save(fig, path)


def plot_action_mode_comparison(comparison: pd.DataFrame, path: Path, title: str) -> None:
    fig, ax = plt.subplots(figsize=(9, 5))
    policies = sorted(comparison["policy"].unique())
    x = np.arange(len(policies))
    width = 0.38
    for offset, (mode, colour) in enumerate((("magnitude", "#c62828"), ("share", "#2f7d32"))):
        subset = comparison[comparison["action_mode"] == mode].set_index("policy")
        values = [float(subset.loc[p, "mean_goal_funding_ratio"])
                  if p in subset.index else np.nan for p in policies]
        ax.bar(x + (offset - 0.5) * width, values, width, label=mode, color=colour)
    ax.set_xticks(x)
    ax.set_xticklabels(policies, rotation=20, ha="right", fontsize=9)
    ax.set_ylabel("Mean goal funding ratio")
    ax.set_title(title)
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    _save(fig, path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=None)
    args = parser.parse_args(argv)

    paths = ProjectPaths.resolve(args.project_root).ensure_output_dirs()
    out = paths.evaluation_out
    plots = paths.plots_out
    plots.mkdir(parents=True, exist_ok=True)

    def load(name: str) -> pd.DataFrame | None:
        p = out / name
        return pd.read_csv(p) if p.exists() else None

    print("generating plots...")

    summary_all = load("policy_summary_archived_all.csv")
    if summary_all is not None:
        plot_funding_by_policy(
            summary_all, plots / "01_funding_ratio_by_policy_archived_all.png",
            "Goal funding by policy — archived configuration, all 100 users")

    summary_test = load("policy_summary_archived_test.csv")
    if summary_test is not None:
        plot_funding_by_policy(
            summary_test, plots / "02_funding_ratio_by_policy_archived_test.png",
            "Goal funding by policy — archived configuration, 20 held-out users")
        plot_net_worth_double_count(
            summary_test, plots / "03_net_worth_double_count.png",
            "Archived net worth aggregate vs corrected ledger (finding F-04)")

    reward = load("reward_decomposition_summary_archived_test.csv")
    if reward is not None:
        plot_reward_components(
            reward, plots / "04_reward_components.png",
            "Reward decomposition by policy — 20 held-out users x 142 months")

    borrow = load("borrowing_audit_half_savings_vs_half_savings_and_loan_corrected_test.csv")
    if borrow is not None:
        plot_borrowing(
            borrow, plots / "05_borrowing_audit.png",
            "Borrowing audit — identical plan with and without a loan request")

    mode_cmp = load("action_mode_comparison.csv")
    if mode_cmp is not None:
        plot_action_mode_comparison(
            mode_cmp, plots / "06_action_mode_comparison.png",
            "Action semantics: magnitude (archived) vs share (fix for F-02)")

    print(f"plots written to {plots}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
