"""Aggregate the controlled reward experiment: seed dispersion, paired comparisons, profiles.

Reads `outputs/reward_design/v1/trained_policy_metrics_{smoke,full}_v1.csv` and the archived
reference file, and writes:

* `reward_version_totals_full_v1.csv`   - per (version, seed) means
* `reward_version_dispersion_full_v1.csv` - mean-of-seeds, SD across seeds, per metric
* `reward_version_paired_full_v1.csv`    - paired on (user_id, seed), bootstrap CI
* `reward_version_by_profile_full_v1.csv` - risk group and goal-horizon breakdown
* a compact stdout digest

No winner is selected here: that is a judgement call documented in the report. Only financial
outcomes are aggregated; total reward is reported so its mismatch with outcomes is visible.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

OUT_DIR = ROOT / "outputs" / "reward_design" / "v1"
BOOTSTRAP = 4000
BOOTSTRAP_SEED = 20261011

METRICS = [
    "weighted_goal_achievement", "mean_funding_ratio", "pct_goals_fully_funded",
    "pct_goals_met_by_deadline", "goal_level_shortfall", "funding_vs_nominal_targets",
    "funding_vs_inflated_targets", "final_liquid_cash", "final_portfolio_value",
    "outstanding_loan_balance", "net_worth", "total_loan_principal", "total_interest_paid",
    "investment_gain", "downside_exposure", "budget_violations", "cash_floor_months",
    "reserve_breach_months", "interest_shortfall_months", "env_reward_total",
]

# Direction of "better" for the recommendation logic; None = descriptive only.
HIGHER_IS_BETTER = {
    "weighted_goal_achievement": True, "mean_funding_ratio": True,
    "pct_goals_fully_funded": True, "pct_goals_met_by_deadline": True,
    "goal_level_shortfall": False, "funding_vs_nominal_targets": True,
    "funding_vs_inflated_targets": True, "net_worth": True, "total_interest_paid": False,
    "total_loan_principal": False, "outstanding_loan_balance": False,
    "downside_exposure": False, "budget_violations": False, "cash_floor_months": False,
    "reserve_breach_months": False, "interest_shortfall_months": False,
}


def bootstrap_ci(values, n=BOOTSTRAP, seed=BOOTSTRAP_SEED):
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if values.size == 0:
        return (np.nan, np.nan)
    rng = np.random.default_rng(seed)
    means = values[rng.integers(0, values.size, size=(n, values.size))].mean(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def main() -> None:
    suffix = sys.argv[1] if len(sys.argv) > 1 else "full"
    detail = pd.read_csv(OUT_DIR / f"trained_policy_metrics_{suffix}_v1.csv")
    detail = detail[detail["reward_version"] != "archived_checkpoint_reference"]
    ref_path = OUT_DIR / f"archived_checkpoint_reference_{suffix}_v1.csv"
    reference = pd.read_csv(ref_path) if ref_path.is_file() else pd.DataFrame()

    versions = sorted(detail["reward_version"].unique())

    # ---- per (version, seed) -----------------------------------------------------------------
    per_seed = detail.groupby(["reward_version", "seed"], sort=True)[METRICS].mean().reset_index()
    per_seed.to_csv(OUT_DIR / f"reward_version_per_seed_{suffix}_v1.csv", index=False)

    # ---- dispersion: mean of seed means, SD across seeds --------------------------------------
    rows = []
    for version in versions:
        block = per_seed[per_seed["reward_version"] == version]
        for metric in METRICS:
            values = block[metric].astype(float).to_numpy()
            pooled = detail.loc[detail["reward_version"] == version, metric].astype(float).to_numpy()
            rows.append({
                "reward_version": version, "metric": metric, "n_seeds": len(values),
                "mean_of_seed_means": float(np.mean(values)),
                "sd_across_seeds": float(np.std(values, ddof=1)) if len(values) > 1 else 0.0,
                "min_seed_mean": float(np.min(values)), "max_seed_mean": float(np.max(values)),
                "pooled_mean": float(np.mean(pooled)),
                "pooled_sd_across_user_seed": float(np.std(pooled, ddof=1)),
                "ci95_low": bootstrap_ci(pooled)[0], "ci95_high": bootstrap_ci(pooled)[1],
                "higher_is_better": HIGHER_IS_BETTER.get(metric),
            })
    dispersion = pd.DataFrame(rows)
    dispersion.to_csv(OUT_DIR / f"reward_version_dispersion_{suffix}_v1.csv", index=False)

    # ---- paired comparisons between versions, paired on (user_id, seed) ------------------------
    paired_rows = []
    for i, a in enumerate(versions):
        for b in versions[i + 1:]:
            left = detail[detail["reward_version"] == a].set_index(["user_id", "seed"])
            right = detail[detail["reward_version"] == b].set_index(["user_id", "seed"])
            common = left.index.intersection(right.index)
            for metric in METRICS:
                diff = (right.loc[common, metric] - left.loc[common, metric]).astype(float).to_numpy()
                lo, hi = bootstrap_ci(diff)
                paired_rows.append({
                    "version_a": a, "version_b": b, "metric": metric, "n_pairs": len(common),
                    "mean_diff_b_minus_a": float(np.nanmean(diff)),
                    "median_diff_b_minus_a": float(np.nanmedian(diff)),
                    "ci95_low": lo, "ci95_high": hi,
                    "significant": bool(np.isfinite(lo) and np.isfinite(hi) and (lo > 0 or hi < 0)),
                    "favours": ("b" if (HIGHER_IS_BETTER.get(metric) is True and lo > 0)
                                or (HIGHER_IS_BETTER.get(metric) is False and hi < 0)
                                else ("a" if (HIGHER_IS_BETTER.get(metric) is True and hi < 0)
                                      or (HIGHER_IS_BETTER.get(metric) is False and lo > 0)
                                      else "inconclusive")),
                })
    paired = pd.DataFrame(paired_rows)
    paired.to_csv(OUT_DIR / f"reward_version_paired_{suffix}_v1.csv", index=False)

    # ---- by profile ---------------------------------------------------------------------------
    detail = detail.copy()
    detail["risk_group"] = pd.cut(detail["risk_score"], bins=[-0.01, 0.33, 0.66, 1.01],
                                  labels=["low", "mid", "high"])
    detail["horizon_group"] = pd.cut(detail["max_goal_horizon_months"], bins=[0, 36, 84, 10000],
                                     labels=["short<=3y", "medium<=7y", "long>7y"])
    by_profile = detail.groupby(["reward_version", "risk_group", "horizon_group"], observed=True)[
        ["weighted_goal_achievement", "net_worth", "pct_goals_met_by_deadline",
         "total_interest_paid", "outstanding_loan_balance"]].mean().reset_index()
    by_profile.to_csv(OUT_DIR / f"reward_version_by_profile_{suffix}_v1.csv", index=False)

    # ---- digest ------------------------------------------------------------------------------
    headline = ["weighted_goal_achievement", "pct_goals_fully_funded",
                "pct_goals_met_by_deadline", "goal_level_shortfall", "net_worth",
                "final_liquid_cash", "final_portfolio_value", "outstanding_loan_balance",
                "total_loan_principal", "total_interest_paid", "downside_exposure",
                "budget_violations", "env_reward_total"]
    digest = {}
    for version in versions:
        block = per_seed[per_seed["reward_version"] == version]
        digest[version] = {
            metric: {
                "mean_of_seed_means": float(block[metric].mean()),
                "sd_across_seeds": float(block[metric].std(ddof=1)) if len(block) > 1 else 0.0,
            }
            for metric in headline
        }
    archived_ref = {}
    if not reference.empty:
        archived_ref = {m: float(reference[m].mean()) for m in headline if m in reference.columns}

    violations = int(detail[[
        "budget_violations", "cash_floor_months", "reserve_breach_months",
        "interest_shortfall_months"]].to_numpy().sum())

    print(json.dumps({
        "versions": versions,
        "seeds": sorted(detail["seed"].unique().tolist()),
        "rows": len(detail),
        "total_invariant_violations": violations,
        "by_version_mean_of_seed_means": digest,
        "archived_checkpoint_reference": archived_ref,
        "paired_file": str(OUT_DIR / f"reward_version_paired_{suffix}_v1.csv"),
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
