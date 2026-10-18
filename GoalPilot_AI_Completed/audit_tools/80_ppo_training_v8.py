"""Phase H — controlled PPO training under `recommended()` and held-out evaluation.

Stage 1 (smoke, already evidenced elsewhere): the environment passes `check_env`, the action
semantics and ledger invariants are pinned by the 164-test suite, and the v1 validity gate
showed the reward version does not change the state trajectory. This script therefore starts
the substantial run.

Design
------
Configuration : `GoalPilotConfig.recommended()`  (action_mode=share, accounting=ledger,
                goal_credit=market_weighted, target_basis=inflated, emergency_months=6).
Reward version: BOTH `archived_v1` and `candidate_a`, kept as separate arms. No reward
                coefficient is changed; the archived reward is never overwritten.
Seeds         : 7, 17, 27  (matched across arms)
Budget        : 100,000 timesteps per run (2x the previous 50k runs; justified by the 50k
                smoke results and the measured ~420--590 steps/s CPU throughput).
Selection     : `EvalCallback` on the 16 **validation** users; the best-validation checkpoint
                is the one evaluated. The test partition is never used for selection.
Evaluation    : 16 fresh test users (uncontaminated; the 20 previously-used users are excluded),
                identical goals/market/config for every arm, with baselines and the
                capacity-constrained LP on the SAME users.

Nothing existing is modified; all artefacts go to versioned folders.
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
sys.path.insert(0, str(paths.root / "GoalPilot_MultiGoal_Extension"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import goalpilot_env  # noqa: E402
from goalpilot_config import (  # noqa: E402
    REWARD_VERSION_A,
    REWARD_VERSION_ARCHIVED,
    GoalPilotConfig,
)
from stable_baselines3 import PPO  # noqa: E402
from stable_baselines3.common.callbacks import EvalCallback  # noqa: E402
from stable_baselines3.common.monitor import Monitor  # noqa: E402

VERSIONS = {REWARD_VERSION_ARCHIVED: "archived_v1", REWARD_VERSION_A: "candidate_a"}
SEEDS = [7, 17, 27]

# Budget decision (documented, not arbitrary).
# The host enforces a 15-minute background command limit and is CPU-only. Measured solo
# throughput is ~420-590 steps/s, i.e. ~2 minutes per 50k run. A 100k budget was attempted
# first and could not complete 6 runs inside the limit, so the budget was set to
# **50,000 timesteps per run** - which also matches the v1/v3 runs exactly and therefore keeps
# the v8 results directly comparable with them. All 6 runs are still trained; nothing is
# truncated or hand-picked.
TIMESTEPS = 50_000
EVAL_FREQ = 25_000
EVAL_EPISODES = 8
N_BOOT = 20_000
BOOT_SEED = 20261011

# Measured on this host by audit_tools/82_ppo_throughput_probe.py (4,096 PPO steps per setting,
# outputs/audit/ppo_throughput_probe.json):
#   1 thread 145.7 steps/s · 2 threads 114.6 · 4 threads 112.9 · 8 threads 96.0 · 16 threads 87.4
# A tiny MLP loses far more to intra-op parallelism than it gains, so single-threaded is fastest.
try:
    import torch

    torch.set_num_threads(1)
except Exception:  # pragma: no cover  # noqa: BLE001
    pass

PPO_HYPERPARAMS = {"policy": "MlpPolicy", "n_steps": 256, "batch_size": 64, "n_epochs": 4,
                   "gamma": 0.99, "learning_rate": 3e-4,
                   "policy_kwargs": {"net_arch": [128, 128]}}

EXP_DIR = paths.root / "training_logs" / "experiments" / "ppo_recommended_v1"
OUT_DIR = paths.root / "outputs" / "evaluation" / "final_validation_v8"
REPORT_DIR = paths.root / "outputs" / "reward_design" / "v8"
for d in (EXP_DIR, OUT_DIR, REPORT_DIR):
    d.mkdir(parents=True, exist_ok=True)

SPLIT_DOC = paths.root / "training_logs" / "experiments" / "fresh_split_v1" / "fresh_split_v1_manifest.json"

METRICS = ["weighted_goal_achievement", "pct_goals_fully_funded", "pct_goals_met_by_deadline",
           "goal_level_shortfall", "savings_contribution", "investment_contribution",
           "investment_cap_overflow", "capacity_violation_months", "final_liquid_cash",
           "final_portfolio_value", "net_worth", "outstanding_loan_balance",
           "total_loan_principal", "total_interest_paid", "investment_gain",
           "downside_exposure", "affordability_violations"]
HIGHER_BETTER = {"weighted_goal_achievement": True, "pct_goals_fully_funded": True,
                 "pct_goals_met_by_deadline": True, "goal_level_shortfall": False,
                 "savings_contribution": True, "investment_contribution": True,
                 "investment_cap_overflow": False, "capacity_violation_months": False,
                 "final_liquid_cash": True, "final_portfolio_value": True, "net_worth": True,
                 "outstanding_loan_balance": False, "total_loan_principal": False,
                 "total_interest_paid": False, "investment_gain": True,
                 "downside_exposure": False, "affordability_violations": False}

profiles = pd.read_csv(paths.rl_profiles_csv)
goals = pd.read_csv(paths.rl_goals_csv)
market = pd.read_csv(paths.rl_market_csv)
manifest = json.loads(SPLIT_DOC.read_text(encoding="utf-8"))
TRAIN_USERS = manifest["train_users"]
VAL_USERS = manifest["validation_users"]
TEST_USERS = manifest["test_users"]

# load 56 for the constrained-LP plan builder and rule policies (read-only)
_spec = importlib.util.spec_from_file_location(
    "clp56", ROOT / "audit_tools" / "56_constrained_lp_comparison.py")
clp56 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(clp56)


def make_env(config, user_ids):
    return goalpilot_env.GoalPilotEnv(profiles=profiles, goals=goals, market=market,
                                      user_ids=user_ids, config=config)


def config_for(version: str, seed: int = 2026) -> GoalPilotConfig:
    return GoalPilotConfig.recommended().replace(reward_version=version, seed=seed)


# ------------------------------------------------------------------ evaluate (one contract) --
def evaluate(env, uid, action_provider) -> dict:
    """One evaluator used by every arm so metrics are directly comparable."""
    obs, _ = env.reset(options={"user_id": uid})
    n = len(env.user_goals)
    targets = env.goal_targets.astype(float)[:n]
    deadlines = env.goal_deadlines[:n].astype(int)
    seen = np.zeros(n, dtype=bool)
    met = np.zeros(n, dtype=bool)
    savings = invest = overflow = cap_viol = downside = 0.0
    floor_months = interest_shortfall_months = reserve_breach = 0
    max_resid = 0.0
    while True:
        action = action_provider(env, obs)
        obs, _, term, trunc, info = env.step(action)
        month = int(env.month_index)
        ratio_now = env.goal_balances[:n] / np.maximum(targets, 1e-9)
        for j in range(n):
            if deadlines[j] == month and not seen[j]:
                seen[j] = True
                met[j] = ratio_now[j] >= 1.0 - 1e-9
        ba = info["budget_audit"]
        savings += float(ba["savings_contribution"])
        invest += float(ba["investment_contribution"])
        overflow += float(ba["invest_overflow"])
        max_resid = max(max_resid, abs(float(ba["budget_check"])))
        if ba["cash_floor_active"]:
            floor_months += 1
        if float(info["ledger"]["cash"]) + 1e-6 < float(info["restricted_cash"]):
            reserve_breach += 1
        if ba["interest_shortfall"] > 1e-9:
            interest_shortfall_months += 1
        ch = float(info["portfolio_market_change"])
        if ch < 0.0:
            downside += -ch
        if term or trunc:
            break

    priority = env.user_goals["priority"].astype(float).to_numpy()[:n]
    funded = env.goal_balances.astype(float)[:n]
    ratio = np.minimum(funded, targets) / np.maximum(targets, 1e-9)
    surplus = (float(env.profile_map[uid]["monthly_income"])
               - float(env.profile_map[uid]["monthly_expenditure"])
               - float(env.profile_map[uid]["monthly_emi"]))
    return {
        "user_id": uid,
        "feasible_cohort": "surplus>0" if surplus > 0 else "zero-surplus",
        "investable_surplus": surplus,
        "weighted_goal_achievement": float(np.sum(priority * ratio) / max(priority.sum(), 1e-9)),
        "pct_goals_fully_funded": float(np.mean(ratio >= 1.0 - 1e-9)),
        "pct_goals_met_by_deadline": float(np.mean(met[seen])) if seen.any() else np.nan,
        "goal_level_shortfall": float(np.sum(np.maximum(0.0, targets - funded))),
        "savings_contribution": savings,
        "investment_contribution": invest,
        "investment_cap_overflow": overflow,
        "capacity_violation_months": 0.0,
        "final_liquid_cash": float(env.cash),
        "final_portfolio_value": float(env.portfolio),
        "net_worth": float(env.net_worth),
        "outstanding_loan_balance": float(env.loan_balance),
        "total_loan_principal": float(env.cumulative_loan_principal),
        "total_interest_paid": float(env.total_interest_paid),
        "investment_gain": float(env.total_investment_gain),
        "downside_exposure": downside,
        "affordability_violations": float(floor_months + reserve_breach
                                          + interest_shortfall_months),
        "max_budget_check_residual": max_resid,
    }


# ------------------------------------------------------------------------------ training ----
def train_one(version: str, label: str, seed: int) -> dict:
    cfg = config_for(version, seed)
    log_dir = EXP_DIR / label / f"seed{seed}"
    log_dir.mkdir(parents=True, exist_ok=True)
    best_dir = log_dir / "best"
    best_dir.mkdir(parents=True, exist_ok=True)
    train_env = Monitor(make_env(cfg, TRAIN_USERS),
                        filename=str(log_dir / f"monitor_{label}_seed{seed}"))
    val_env = Monitor(make_env(cfg, VAL_USERS))
    callback = EvalCallback(val_env, best_model_save_path=str(best_dir),
                            log_path=str(log_dir / "eval"), eval_freq=EVAL_FREQ,
                            n_eval_episodes=EVAL_EPISODES, deterministic=True, verbose=0)
    model = PPO(env=train_env, seed=seed, verbose=0, **PPO_HYPERPARAMS)
    t0 = time.time()
    model.learn(total_timesteps=TIMESTEPS, progress_bar=False, callback=callback)
    elapsed = time.time() - t0
    final_ckpt = log_dir / f"ppo_{label}_seed{seed}_final.zip"
    model.save(str(final_ckpt))
    returns = list(train_env.get_episode_rewards())
    record = {
        "reward_version": label, "seed": seed, "timesteps": TIMESTEPS,
        "config_preset": "recommended", "train_users": len(TRAIN_USERS),
        "validation_users": len(VAL_USERS), "seconds": elapsed,
        "steps_per_second": TIMESTEPS / elapsed if elapsed else float("nan"),
        "episodes_completed": len(returns),
        "mean_train_episode_return": float(np.mean(returns)) if returns else float("nan"),
        "best_validation_checkpoint": str(best_dir / "best_model.zip"),
        "best_validation_exists": (best_dir / "best_model.zip").is_file(),
        "final_checkpoint": str(final_ckpt),
    }
    (log_dir / f"run_{label}_seed{seed}.json").write_text(json.dumps(record, indent=2),
                                                          encoding="utf-8")
    train_env.close()
    val_env.close()
    return record


# ------------------------------------------------------------------------------ baselines ---
def lp_action_provider(uid: str):
    plan = clp56.plan_for(uid, "constrained_LP")
    action = plan["action"]
    return lambda env, obs: action


def rule_action_provider(policy: str):
    return lambda env, obs: clp56.rule_action(env, policy)


def model_action_provider(model):
    return lambda env, obs: model.predict(obs, deterministic=True)[0]


# ---------------------------------------------------------------------------- statistics ----
def bootstrap_ci(values, n=N_BOOT, seed=BOOT_SEED):
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    if v.size == 0:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    means = v[rng.integers(0, v.size, size=(n, v.size))].mean(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["train", "eval", "all"], default="all")
    ap.add_argument("--versions", type=str, default="",
                    help="comma-separated labels to train (default: all)")
    ap.add_argument("--seeds", type=str, default="",
                    help="comma-separated seeds to train (default: all)")
    ap.add_argument("--max-runs", type=int, default=0,
                    help="stop after this many newly trained runs in this invocation (0 = no limit)")
    args = ap.parse_args()

    if args.stage in ("train", "all"):
        versions = dict(VERSIONS)
        if args.versions:
            wanted = {v.strip() for v in args.versions.split(",")}
            versions = {k: v for k, v in VERSIONS.items() if v in wanted}
        seeds = [int(s) for s in args.seeds.split(",")] if args.seeds else list(SEEDS)
        print(f"[train] {len(versions)} reward versions x {len(seeds)} seeds x {TIMESTEPS} "
              f"steps on {len(TRAIN_USERS)} train users; selection on {len(VAL_USERS)} val users")
        trained = 0
        for version, label in versions.items():
            for seed in seeds:
                rec_path = EXP_DIR / label / f"seed{seed}" / f"run_{label}_seed{seed}.json"
                best = EXP_DIR / label / f"seed{seed}" / "best" / "best_model.zip"
                if rec_path.is_file() and best.is_file():
                    print(f"      {label} seed={seed}: reused")
                    continue
                if args.max_runs and trained >= args.max_runs:
                    print(f"      stopping: --max-runs={args.max_runs} reached")
                    return
                rec = train_one(version, label, seed)
                trained += 1
                print(f"      {label} seed={seed}: {rec['steps_per_second']:.0f} steps/s, "
                      f"{rec['episodes_completed']} episodes, best={rec['best_validation_exists']}",
                      flush=True)

    if args.stage in ("eval", "all"):
        rows: list[dict] = []
        env = make_env(config_for(REWARD_VERSION_ARCHIVED), TEST_USERS)

        # fixed baselines
        for policy in ("uniform savings", "investment-only", "mixed allocation",
                       "need-proportional savings", "urgency"):
            for uid in TEST_USERS:
                rows.append({"arm": policy, "seed": -1,
                             **evaluate(env, uid, rule_action_provider(policy))})
        # capacity-constrained LP
        for uid in TEST_USERS:
            rows.append({"arm": "constrained_LP", "seed": -1,
                         **evaluate(env, uid, lp_action_provider(uid))})
        # trained RL (validation-selected best checkpoint per version/seed)
        for version, label in VERSIONS.items():
            for seed in SEEDS:
                best = EXP_DIR / label / f"seed{seed}" / "best" / "best_model.zip"
                if not best.is_file():
                    print(f"      [warn] missing checkpoint {best}")
                    continue
                model = PPO.load(str(best))
                env_rl = make_env(config_for(version), TEST_USERS)
                for uid in TEST_USERS:
                    rows.append({"arm": f"RL {label}", "seed": seed,
                                 **evaluate(env_rl, uid, model_action_provider(model))})

        detail = pd.DataFrame(rows)
        detail.to_csv(OUT_DIR / "ppo_v8_detail.csv", index=False)

        summary = []
        for (arm, seed), block in detail.groupby(["arm", "seed"]):
            row = {"arm": arm, "seed": seed, "users": len(block)}
            for m in METRICS:
                v = block[m].astype(float).to_numpy()
                lo, hi = bootstrap_ci(v)
                row[f"{m}_mean"] = float(np.nanmean(v))
                row[f"{m}_sd"] = float(np.nanstd(v, ddof=1)) if v.size > 1 else 0.0
                row[f"{m}_ci95_low"] = lo
                row[f"{m}_ci95_high"] = hi
            summary.append(row)
        pd.DataFrame(summary).to_csv(OUT_DIR / "ppo_v8_summary.csv", index=False)

        # across-seed aggregation for RL arms
        across = []
        for arm in ["RL archived_v1", "RL candidate_a"]:
            block = detail[detail["arm"] == arm]
            if block.empty:
                continue
            row = {"arm": arm, "seeds": block["seed"].nunique(), "users": len(TEST_USERS)}
            per_seed = block.groupby("seed")[METRICS].mean()
            for m in METRICS:
                row[f"{m}_mean"] = float(per_seed[m].mean())
                row[f"{m}_sd_across_seeds"] = float(per_seed[m].std(ddof=1)) \
                    if len(per_seed) > 1 else 0.0
            across.append(row)
        pd.DataFrame(across).to_csv(OUT_DIR / "ppo_v8_across_seeds.csv", index=False)

        # paired: each RL arm (mean over seeds per user) minus each baseline
        paired = []
        user_arm = detail.groupby(["arm", "user_id"])[METRICS].mean().reset_index()
        baselines = [a for a in detail["arm"].unique() if not a.startswith("RL ")]
        for rl in [a for a in detail["arm"].unique() if a.startswith("RL ")]:
            rl_block = user_arm[user_arm["arm"] == rl].set_index("user_id")
            for base in baselines:
                b_block = user_arm[user_arm["arm"] == base].set_index("user_id")
                common = rl_block.index.intersection(b_block.index)
                for m in METRICS:
                    d = (rl_block.loc[common, m].to_numpy(dtype=float)
                         - b_block.loc[common, m].to_numpy(dtype=float))
                    lo, hi = bootstrap_ci(d)
                    improved = int((d > 0).sum())
                    worsened = int((d < 0).sum())
                    if not (np.isfinite(lo) and np.isfinite(hi)):
                        verdict = "inconclusive"
                    elif lo > 0:
                        verdict = f"{rl} higher"
                    elif hi < 0:
                        verdict = f"{base} higher"
                    else:
                        verdict = "inconclusive"
                    paired.append({"rl_arm": rl, "baseline": base, "metric": m,
                                   "users": len(common), "mean_diff": float(np.mean(d)),
                                   "ci95_low": lo, "ci95_high": hi,
                                   "improved": improved, "worsened": worsened,
                                   "verdict": verdict})
        pd.DataFrame(paired).to_csv(OUT_DIR / "ppo_v8_paired.csv", index=False)

        digest = {
            "config_preset": "recommended",
            "reward_versions": list(VERSIONS.values()),
            "seeds": SEEDS, "timesteps_per_run": TIMESTEPS,
            "train_users": len(TRAIN_USERS), "validation_users": len(VAL_USERS),
            "heldout_test_users": len(TEST_USERS),
            "feasibility_eligible_test_users":
                int((detail[detail["arm"] == "uniform savings"]["investable_surplus"] > 0).sum()),
            "arms": sorted(detail["arm"].unique().tolist()),
            "total_affordability_violations": int(detail["affordability_violations"].sum()),
            "max_budget_residual": float(detail["max_budget_check_residual"].max()),
            "per_arm_mean_achievement": detail.groupby("arm")["weighted_goal_achievement"]
            .mean().round(4).to_dict(),
            "per_arm_mean_net_worth": detail.groupby("arm")["net_worth"].mean().round(2)
            .to_dict(),
        }
        (OUT_DIR / "ppo_v8_digest.json").write_text(json.dumps(digest, indent=2, default=str),
                                                    encoding="utf-8")
        print(json.dumps(digest, indent=2, default=str))


if __name__ == "__main__":
    main()
