"""Phase 2 — audit the statistical validity of the published reward comparison.

Flaw under audit
----------------
`audit_tools/34_reward_experiment_report.py` bootstrapped over the **60 (user, seed) rows** as
if they were 60 independent observations. They are not: the same 20 held-out users are observed
three times each (seeds 7, 17, 27). That is pseudo-replication, and it makes the confidence
intervals too narrow.

This script recomputes every comparison with three defensible methods and reports how the
conclusions change:

* **A. as published**        - naive bootstrap over 60 (user, seed) rows (kept for comparison)
* **B. cluster bootstrap**   - resample the 20 *users* with replacement, keeping all of each
                              resampled user's seeds (correct uncertainty, n = 20 clusters)
* **C. user-mean paired t**  - average each user across seeds, then a paired t-test on n = 20

It also repeats all three on the **feasibility-eligible** subset, because Phase 1 established
that 6 of the 20 held-out users have a zero discretionary budget and cannot fund any goal under
any action. Eligibility is defined by an ex-ante constraint (`monthly_surplus > 0`), never by
outcomes, so this is pre-specified stratification rather than cherry-picking.

No existing artefact is modified; corrected results are written under `outputs/reward_design/v2/`.
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
from scipy import stats  # noqa: E402

EXP_DIR = ROOT / "training_logs" / "experiments" / "reward_experiment_v1"
OUT_DIR = ROOT / "outputs" / "reward_design" / "v2"
OUT_DIR.mkdir(parents=True, exist_ok=True)

N_BOOT = 20000
BOOT_SEED = 20261011

# metric -> does a higher value favour the policy?
DIRECTION = {
    "weighted_goal_achievement": True, "pct_goals_fully_funded": True,
    "pct_goals_met_by_deadline": True, "net_worth": True,
    "total_interest_paid": False, "total_loan_principal": False,
    "goal_level_shortfall": False,
}
PAIRS = [("archived_v1", "candidate_a"), ("archived_v1", "candidate_b"),
         ("candidate_a", "candidate_b")]


def load() -> pd.DataFrame:
    detail = pd.concat(
        [pd.read_csv(p) for p in sorted((EXP_DIR / "eval").glob("metrics_*.csv"))],
        ignore_index=True)
    return detail[detail["reward_version"] != "archived_checkpoint_reference"].copy()


def eligible_users() -> set:
    details = pd.read_csv(OUT_DIR / "low_risk_user_details.csv")
    return set(details.loc[details["monthly_surplus"] > 0.0, "user_id"].astype(str))


def naive_bootstrap(diff: np.ndarray, n=N_BOOT, seed=BOOT_SEED):
    """The published method: every (user, seed) row treated as independent."""
    rng = np.random.default_rng(seed)
    means = diff[rng.integers(0, diff.size, size=(n, diff.size))].mean(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def cluster_bootstrap(frame: pd.DataFrame, n=N_BOOT, seed=BOOT_SEED):
    """Resample users, keeping all of a user's seeds together."""
    users = frame["user_id"].unique()
    per_user = {u: frame.loc[frame["user_id"] == u, "diff"].to_numpy() for u in users}
    rng = np.random.default_rng(seed)
    means = np.empty(n)
    for i in range(n):
        draw = rng.integers(0, len(users), size=len(users))
        pooled = np.concatenate([per_user[users[j]] for j in draw])
        means[i] = pooled.mean()
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def user_mean_bootstrap(diff: np.ndarray, n=N_BOOT, seed=BOOT_SEED):
    """Resample the per-user mean differences."""
    rng = np.random.default_rng(seed)
    means = diff[rng.integers(0, diff.size, size=(n, diff.size))].mean(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def analyse(detail: pd.DataFrame, subset_users, label: str) -> pd.DataFrame:
    block = detail[detail["user_id"].isin(subset_users)]
    rows = []
    for a, b in PAIRS:
        left = block[block["reward_version"] == a]
        right = block[block["reward_version"] == b]
        for metric in DIRECTION:
            merged = left.merge(right, on=["user_id", "seed"], suffixes=("_a", "_b"))
            if merged.empty:
                continue
            merged = merged.assign(diff=merged[f"{metric}_b"] - merged[f"{metric}_a"])
            merged = merged.dropna(subset=["diff"])
            if merged.empty:
                continue
            naive_lo, naive_hi = naive_bootstrap(merged["diff"].to_numpy())
            clus_lo, clus_hi = cluster_bootstrap(merged)
            user_means = merged.groupby("user_id")["diff"].mean()
            um_lo, um_hi = user_mean_bootstrap(user_means.to_numpy())
            t_stat, p_val = stats.ttest_rel(
                merged.pivot_table(index="user_id", columns="seed",
                                   values=f"{metric}_b").mean(axis=1),
                merged.pivot_table(index="user_id", columns="seed",
                                   values=f"{metric}_a").mean(axis=1),
            )
            higher_better = DIRECTION[metric]
            def verdict(lo, hi):
                if not (np.isfinite(lo) and np.isfinite(hi)):
                    return "inconclusive"
                if lo > 0:
                    return "favours_b" if higher_better else "favours_a"
                if hi < 0:
                    return "favours_a" if higher_better else "favours_b"
                return "inconclusive"
            rows.append({
                "analysis_population": label,
                "version_a": a, "version_b": b, "metric": metric,
                "independent_users": int(user_means.size),
                "observations": int(len(merged)),
                "seed_variability_sd": float(
                    merged.groupby("seed")["diff"].mean().std(ddof=1))
                if merged["seed"].nunique() > 1 else 0.0,
                "mean_diff_b_minus_a": float(merged["diff"].mean()),
                "user_mean_of_diff": float(user_means.mean()),
                # A: as published
                "naive_ci95_low": naive_lo, "naive_ci95_high": naive_hi,
                "naive_verdict": verdict(naive_lo, naive_hi),
                # B: cluster bootstrap (correct for repeated measures)
                "cluster_ci95_low": clus_lo, "cluster_ci95_high": clus_hi,
                "cluster_verdict": verdict(clus_lo, clus_hi),
                # C: user-mean paired t-test
                "user_mean_ci95_low": um_lo, "user_mean_ci95_high": um_hi,
                "paired_t_stat": float(t_stat), "paired_t_pvalue": float(p_val),
                "user_mean_verdict": verdict(um_lo, um_hi),
                "ci_width_ratio_cluster_over_naive": (
                    float((clus_hi - clus_lo) / (naive_hi - naive_lo))
                    if (naive_hi - naive_lo) > 0 else float("nan")),
                "verdicts_agree": bool(
                    verdict(naive_lo, naive_hi) == verdict(clus_lo, clus_hi)
                    == verdict(um_lo, um_hi)),
            })
    return pd.DataFrame(rows)


def main() -> None:
    detail = load()
    all_users = set(detail["user_id"].unique())
    eligible = eligible_users() & all_users
    excluded = sorted(all_users - eligible)

    out = pd.concat([
        analyse(detail, all_users, f"all held-out users (n={len(all_users)})"),
        analyse(detail, eligible, f"feasibility-eligible users, surplus>0 (n={len(eligible)})"),
    ], ignore_index=True)
    out.to_csv(OUT_DIR / "statistical_audit_paired_corrected_v1.csv", index=False)

    flip = out[~out["verdicts_agree"]]
    digest = {
        "held_out_users": len(all_users),
        "feasibility_eligible_users": len(eligible),
        "excluded_zero_surplus_users": excluded,
        "independent_sample_size_per_arm": len(all_users),
        "observations_if_pseudo_replicated": int(len(detail) / detail["reward_version"].nunique()),
        "seed_variability_note": (
            "seeds are repeated measures on the same users; they reduce estimation noise but "
            "do not increase the independent sample size beyond the 20 held-out users"
        ),
        "conclusions_that_flip_between_methods": flip[[
            "analysis_population", "version_a", "version_b", "metric",
            "naive_verdict", "cluster_verdict", "user_mean_verdict",
            "ci_width_ratio_cluster_over_naive"]].to_dict("records"),
        "n_flipped": int(len(flip)),
        "ci_width_ratio_summary": {
            "median": float(out["ci_width_ratio_cluster_over_naive"].median()),
            "max": float(out["ci_width_ratio_cluster_over_naive"].max()),
        },
    }
    (OUT_DIR / "statistical_audit_summary_v1.json").write_text(
        json.dumps(digest, indent=2, default=str), encoding="utf-8")
    print(json.dumps(digest, indent=2, default=str))


if __name__ == "__main__":
    main()
