"""P2 — fresh-split confirmation of `candidate_a` versus `archived_v1`.

Why a new split
---------------
The 20 users used throughout the first experiment were also the users on which `candidate_a`
was *chosen*. That is test-set model selection (declared in
`outputs/reward_design/v2/LOW_RISK_AND_STATISTICAL_DIAGNOSTIC.md` §2.4). To confirm the
advantage without that contamination this script builds a **fresh** user-level split and leaves
its test partition untouched until the final evaluation.

Split construction (documented, deterministic, recorded)
    100 users
      minus 20  the previously used held-out users -> **excluded entirely** (contaminated)
      =     80  re-partitioned, seeded, into
              train 48 / validation 16 / test 16
    No user appears in more than one partition, and no previously-used user appears at all.
    Model selection uses the *validation* partition only; the test partition is evaluated once.

Training
    `GoalPilotConfig.recommended().replace(reward_version=...)`, 50,000 timesteps, identical
    hyper-parameters, matched seeds 7/17/27, identical 48 training users, for **both** arms.
    No checkpoint is reused for either arm.

Statistics
    User-level paired differences with a **user-clustered** bootstrap (resampling users, keeping
    all of a user's seeds together) plus a user-mean paired t-test. Repeated rolls of the same
    user are never treated as independent observations.

Nothing in the environment is modified. Writes to
`training_logs/experiments/fresh_split_v1/` and `outputs/reward_design/v3/`.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from goalpilot_paths import ProjectPaths  # noqa: E402

paths = ProjectPaths.resolve()
paths.add_to_sys_path()

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats  # noqa: E402

import goalpilot_env  # noqa: E402
from goalpilot_config import (  # noqa: E402
    REWARD_VERSION_A,
    REWARD_VERSION_ARCHIVED,
    GoalPilotConfig,
)
from stable_baselines3 import PPO  # noqa: E402
from stable_baselines3.common.monitor import Monitor  # noqa: E402

# reuse the verified evaluator from the first experiment (read-only import, no side effects
# beyond reading the shared CSVs)
_spec = importlib.util.spec_from_file_location(
    "reward_exp33", ROOT / "audit_tools" / "33_reward_experiment.py")
exp33 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(exp33)

EXP_DIR = paths.root / "training_logs" / "experiments" / "fresh_split_v1"
OUT_DIR = paths.root / "outputs" / "reward_design" / "v3"
EXP_DIR.mkdir(parents=True, exist_ok=True)
OUT_DIR.mkdir(parents=True, exist_ok=True)

SPLIT_SEED = 20261011
SPLIT_PATH = EXP_DIR / "fresh_split_v1.csv"
SPLIT_DOC = EXP_DIR / "fresh_split_v1_manifest.json"

VERSIONS = {REWARD_VERSION_A: "candidate_a", REWARD_VERSION_ARCHIVED: "archived_v1"}
SEEDS = [7, 17, 27]
TIMESTEPS = 50000
N_BOOT = 20000
BOOT_SEED = 20261011

PPO_HYPERPARAMS = {
    "policy": "MlpPolicy", "n_steps": 256, "batch_size": 64, "n_epochs": 4, "gamma": 0.99,
    "learning_rate": 3e-4, "policy_kwargs": {"net_arch": [128, 128]},
}

METRICS = [
    "weighted_goal_achievement", "pct_goals_fully_funded", "pct_goals_met_by_deadline",
    "goal_level_shortfall", "final_liquid_cash", "final_portfolio_value", "net_worth",
    "outstanding_loan_balance", "total_loan_principal", "total_interest_paid",
    "investment_gain", "downside_exposure", "affordability_violations",
]
# metric -> higher is better
DIRECTION = {
    "weighted_goal_achievement": True, "pct_goals_fully_funded": True,
    "pct_goals_met_by_deadline": True, "goal_level_shortfall": False,
    "final_liquid_cash": True, "final_portfolio_value": True, "net_worth": True,
    "outstanding_loan_balance": False, "total_loan_principal": False,
    "total_interest_paid": False, "investment_gain": True, "downside_exposure": False,
    "affordability_violations": False,
}

profiles = pd.read_csv(paths.rl_profiles_csv)
goals = pd.read_csv(paths.rl_goals_csv)
market = pd.read_csv(paths.rl_market_csv)
old_split = pd.read_csv(paths.rl_split_csv)
_old_col = next(c for c in ("split", "set", "subset", "is_test") if c in old_split.columns)


# ------------------------------------------------------------------------ 1. the split -----

def build_split() -> dict:
    all_users = sorted(profiles["user_id"].astype(str).unique())
    contaminated = sorted(old_split.loc[
        old_split[_old_col].astype(str).str.lower() == "test", "user_id"].astype(str).unique())
    remaining = sorted(set(all_users) - set(contaminated))

    rng = np.random.default_rng(SPLIT_SEED)
    perm = rng.permutation(len(remaining))
    shuffled = [remaining[i] for i in perm]
    n_train, n_val = 48, 16
    parts = {
        "train": shuffled[:n_train],
        "validation": shuffled[n_train:n_train + n_val],
        "test": shuffled[n_train + n_val:],
        "excluded_contaminated": contaminated,
    }
    # no leakage
    sets = {k: set(v) for k, v in parts.items()}
    assert not (sets["train"] & sets["validation"]), "train/validation overlap"
    assert not (sets["train"] & sets["test"]), "train/test overlap"
    assert not (sets["validation"] & sets["test"]), "validation/test overlap"
    assert not (sets["test"] & sets["excluded_contaminated"]), "test/reused-user overlap"
    assert sum(len(v) for v in parts.values()) == len(all_users), "users lost or duplicated"

    frame = pd.DataFrame([
        {"user_id": uid, "fresh_split": part}
        for part, users in parts.items() for uid in users
    ]).sort_values(["fresh_split", "user_id"])
    frame.to_csv(SPLIT_PATH, index=False)

    manifest = {
        "split_version": "fresh_split_v1",
        "generator": "numpy.random.default_rng(20261011).permutation on the sorted user list",
        "total_users": len(all_users),
        "counts": {k: len(v) for k, v in parts.items()},
        "excluded_users": contaminated,
        "exclusion_reason": ("these 20 users were the evaluation set of reward_experiment_v1 and "
                             "were used to choose candidate_a; keeping them would leak selection"),
        "train_users": parts["train"],
        "validation_users": parts["validation"],
        "test_users": parts["test"],
        "no_leakage_checks": "passed (programmatic assertions, see build_split)",
        "file": str(SPLIT_PATH),
    }
    SPLIT_DOC.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def load_split() -> dict:
    if not SPLIT_DOC.is_file():
        return build_split()
    return json.loads(SPLIT_DOC.read_text(encoding="utf-8"))


# ----------------------------------------------------------------------- 2. training -------

def make_env(config, user_ids):
    return goalpilot_env.GoalPilotEnv(
        profiles=profiles, goals=goals, market=market,
        user_ids=user_ids, config=config,
    )


def train_one(version: str, label: str, seed: int, train_users: list[str]) -> dict:
    config = GoalPilotConfig.recommended().replace(reward_version=version, seed=seed)
    log_dir = EXP_DIR / label
    log_dir.mkdir(parents=True, exist_ok=True)
    env = Monitor(make_env(config, train_users),
                  filename=str(log_dir / f"monitor_{label}_seed{seed}"))
    model = PPO(env=env, seed=seed, verbose=0, **PPO_HYPERPARAMS)
    started = time.time()
    model.learn(total_timesteps=TIMESTEPS, progress_bar=False)
    elapsed = time.time() - started
    checkpoint = log_dir / f"ppo_{label}_seed{seed}.zip"
    model.save(str(checkpoint))
    returns = list(env.get_episode_rewards())
    lengths = list(env.get_episode_lengths())
    pd.DataFrame({"episode_return": returns, "episode_length": lengths}).to_csv(
        log_dir / f"training_episodes_{label}_seed{seed}.csv", index=False)
    env.close()
    record = {
        "reward_version": label, "seed": seed, "timesteps": TIMESTEPS,
        "train_users": len(train_users), "seconds": elapsed,
        "steps_per_second": TIMESTEPS / elapsed if elapsed else float("nan"),
        "episodes_completed": len(returns),
        "mean_train_episode_return": float(np.mean(returns)) if returns else float("nan"),
        "checkpoint": str(checkpoint), "checkpoint_saved": checkpoint.is_file(),
    }
    (log_dir / f"run_{label}_seed{seed}.json").write_text(
        json.dumps(record, indent=2), encoding="utf-8")
    return record


# -------------------------------------------------------------- 3. statistics (clustered) ---

def cluster_bootstrap(frame: pd.DataFrame, n=N_BOOT, seed=BOOT_SEED):
    users = frame["user_id"].unique()
    per_user = {u: frame.loc[frame["user_id"] == u, "diff"].to_numpy() for u in users}
    rng = np.random.default_rng(seed)
    means = np.empty(n)
    for i in range(n):
        draw = rng.integers(0, len(users), size=len(users))
        means[i] = np.concatenate([per_user[users[j]] for j in draw]).mean()
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def naive_bootstrap(diff: np.ndarray, n=N_BOOT, seed=BOOT_SEED):
    rng = np.random.default_rng(seed)
    means = diff[rng.integers(0, diff.size, size=(n, diff.size))].mean(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def verdict(lo, hi, higher_better, a, b):
    if not (np.isfinite(lo) and np.isfinite(hi)):
        return "inconclusive"
    if lo > 0:
        return f"favours_{b}" if higher_better else f"favours_{a}"
    if hi < 0:
        return f"favours_{a}" if higher_better else f"favours_{b}"
    return "inconclusive"


def analyse(detail: pd.DataFrame, users: list[str], population: str) -> pd.DataFrame:
    block = detail[detail["user_id"].isin(users)]
    rows = []
    available = [m for m in METRICS if m in block.columns]
    for metric in available:
        left = block[block["reward_version"] == "archived_v1"]
        right = block[block["reward_version"] == "candidate_a"]
        merged = left.merge(right, on=["user_id", "seed"], suffixes=("_a", "_b")).dropna(
            subset=[f"{metric}_a", f"{metric}_b"])
        if merged.empty:
            continue
        merged = merged.assign(diff=merged[f"{metric}_b"] - merged[f"{metric}_a"])
        naive = naive_bootstrap(merged["diff"].to_numpy())
        clus = cluster_bootstrap(merged)
        pivot_b = merged.pivot_table(index="user_id", columns="seed", values=f"{metric}_b")
        pivot_a = merged.pivot_table(index="user_id", columns="seed", values=f"{metric}_a")
        t, p = stats.ttest_rel(pivot_b.mean(axis=1), pivot_a.mean(axis=1))
        user_means = merged.groupby("user_id")["diff"].mean()
        rows.append({
            "population": population, "metric": metric,
            "independent_users": int(user_means.size),
            "observations": int(len(merged)),
            "mean_diff_candidate_a_minus_archived": float(merged["diff"].mean()),
            "user_mean_of_diff": float(user_means.mean()),
            "sd_across_seed_means": float(merged.groupby("seed")["diff"].mean().std(ddof=1)),
            "sd_across_users": float(user_means.std(ddof=1)),
            "naive_ci95_low": naive[0], "naive_ci95_high": naive[1],
            "cluster_ci95_low": clus[0], "cluster_ci95_high": clus[1],
            "paired_t_stat": float(t), "paired_t_pvalue": float(p),
            "verdict_naive": verdict(naive[0], naive[1], DIRECTION[metric],
                                     "archived_v1", "candidate_a"),
            "verdict_clustered": verdict(clus[0], clus[1], DIRECTION[metric],
                                         "archived_v1", "candidate_a"),
            "verdict_paired_t": ("favours_candidate_a"
                                 if (p < 0.05 and DIRECTION[metric] and user_means.mean() > 0)
                                 or (p < 0.05 and not DIRECTION[metric] and user_means.mean() < 0)
                                 else ("favours_archived_v1"
                                       if (p < 0.05 and DIRECTION[metric]
                                           and user_means.mean() < 0)
                                       or (p < 0.05 and not DIRECTION[metric]
                                           and user_means.mean() > 0)
                                       else "inconclusive")),
        })
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=["split", "train", "eval", "all"], default="all")
    parser.add_argument("--versions", type=str, default="")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    manifest = load_split() if args.stage in ("train", "eval", "all") else build_split()
    train_users = manifest["train_users"]
    val_users = manifest["validation_users"]
    test_users = manifest["test_users"]
    if args.stage == "split":
        print(json.dumps({"counts": manifest["counts"],
                          "test_users": test_users}, indent=2))
        return

    selected = dict(VERSIONS)
    if args.versions:
        wanted = {v.strip() for v in args.versions.split(",")}
        selected = {k: v for k, v in VERSIONS.items() if v in wanted}

    if args.stage in ("train", "all"):
        print(f"[train] {len(selected)} versions x {len(SEEDS)} seeds x {TIMESTEPS} steps "
              f"on {len(train_users)} fresh train users")
        for version, label in selected.items():
            for seed in SEEDS:
                rec = EXP_DIR / label / f"run_{label}_seed{seed}.json"
                ckpt = EXP_DIR / label / f"ppo_{label}_seed{seed}.zip"
                if not args.force and rec.is_file() and ckpt.is_file():
                    row = json.loads(rec.read_text(encoding="utf-8"))
                    print(f"      {label} seed={seed}: reused existing checkpoint")
                else:
                    row = train_one(version, label, seed, train_users)
                    print(f"      {label} seed={seed}: {row['steps_per_second']:.0f} steps/s, "
                          f"{row['episodes_completed']} episodes, saved={row['checkpoint_saved']}")

    if args.stage in ("eval", "all"):
        records = [json.loads(p.read_text(encoding="utf-8"))
                   for p in sorted(EXP_DIR.glob("*/run_*.json"))]
        print(f"[eval] {len(records)} checkpoints, {len(test_users)} fresh test users")
        rows = []
        for rec in records:
            model = PPO.load(rec["checkpoint"])
            rows += exp33.evaluate(model, rec["reward_version"], rec["seed"], test_users,
                                   VERSIONS_INV[rec["reward_version"]])
        detail = pd.DataFrame(rows)
        # The shared evaluator reports the three affordability/invariant counters separately;
        # combine them into the single "affordability violations" metric the brief asks for.
        detail["affordability_violations"] = (
            detail["cash_floor_months"] + detail["reserve_breach_months"]
            + detail["interest_shortfall_months"]
        ).astype(float)
        detail.to_csv(OUT_DIR / "fresh_split_metrics_v1.csv", index=False)

        surplus = {}
        for uid in test_users:
            p = profiles.loc[profiles["user_id"].astype(str) == uid].iloc[0]
            surplus[uid] = (float(p["monthly_income"]) - float(p["monthly_expenditure"])
                            - float(p["monthly_emi"]))
        eligible = [u for u in test_users if surplus[u] > 0.0]
        excluded = [u for u in test_users if surplus[u] <= 0.0]

        paired = pd.concat([
            analyse(detail, test_users, f"all fresh test users (n={len(test_users)})"),
            analyse(detail, eligible,
                    f"feasibility-eligible fresh test users (n={len(eligible)})"),
        ], ignore_index=True)
        paired.to_csv(OUT_DIR / "fresh_split_paired_v1.csv", index=False)

        per_seed = detail.groupby(["reward_version", "seed"])[METRICS].mean().reset_index()
        per_seed.to_csv(OUT_DIR / "fresh_split_per_seed_v1.csv", index=False)

        headline = ["weighted_goal_achievement", "pct_goals_fully_funded",
                    "pct_goals_met_by_deadline"]
        digest = {
            "split": "fresh_split_v1",
            "train_users": len(train_users), "validation_users": len(val_users),
            "fresh_test_users": len(test_users),
            "feasibility_eligible_test_users": len(eligible),
            "excluded_zero_surplus_test_users": excluded,
            "validation_partition_used_for_selection": False,
            "arms": {v: len(SEEDS) for v in VERSIONS.values()},
            "timesteps_per_arm": TIMESTEPS,
            "per_seed_headline": per_seed[["reward_version", "seed"] + headline]
            .round(4).to_dict("records"),
            "affordability_violations_total": int(detail["affordability_violations"].sum())
            if "affordability_violations" in detail else None,
            "headline_paired": paired[paired["metric"].isin(headline)][[
                "population", "metric", "independent_users", "mean_diff_candidate_a_minus_archived",
                "cluster_ci95_low", "cluster_ci95_high", "paired_t_pvalue",
                "verdict_naive", "verdict_clustered", "verdict_paired_t"]].round(4)
            .to_dict("records"),
        }
        (OUT_DIR / "fresh_split_summary_v1.json").write_text(
            json.dumps(digest, indent=2, default=str), encoding="utf-8")
        print(json.dumps(digest, indent=2, default=str))


VERSIONS_INV = {label: version for version, label in VERSIONS.items()}


if __name__ == "__main__":
    main()
