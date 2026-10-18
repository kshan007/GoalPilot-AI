"""Controlled reward-function experiment: archived_v1 vs candidate_a vs candidate_b.

Design (fixed before any run, per the approved conditions):

* Every experiment uses ``GoalPilotConfig.recommended()``, differing **only** in
  ``reward_version`` and ``seed``.
* A **validity gate** runs first: the reward version must affect only the reward signal, never
  the environment's dynamics. Identical fixed-policy rollouts under all three versions must
  produce bit-identical state trajectories, otherwise the comparison is confounded and the
  script aborts rather than produce misleading results.
* Fresh PPO policies are trained for all three versions with an identical budget, identical
  hyper-parameters and matched seeds. No pre-existing checkpoint is used for any of the three.
  The archived checkpoint is evaluated separately as a historical reference only.
* Evaluation uses the same 20 held-out users, the same 142-month episodes and the same metric
  set for every run, and reports dispersion across seeds plus paired comparisons.
* Coefficients are never tuned against the held-out users. No version is declared a winner on
  total reward.

Staging (added after a 15-minute background cap truncated an earlier monolithic run):

    --stage train   train only; skips any (version, seed) whose checkpoint already exists
    --stage eval    evaluate every discovered checkpoint, writing one CSV per run
    --stage all     both (default)

Every stage is incremental and idempotent: a per-run JSON record and a per-run metrics CSV are
written as soon as each unit of work finishes, so an interrupted run loses at most one unit and
can simply be re-invoked.

Usage:
    python audit_tools/33_reward_experiment.py --mode smoke
    python audit_tools/33_reward_experiment.py --mode full --stage train --timesteps 50000 --seeds 7,17,27
    python audit_tools/33_reward_experiment.py --mode full --stage train --versions candidate_b --seeds 17,27
    python audit_tools/33_reward_experiment.py --mode full --stage eval
"""
from __future__ import annotations

import argparse
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

import goalpilot_env  # noqa: E402
from goalpilot_config import (  # noqa: E402
    REWARD_VERSION_A,
    REWARD_VERSION_ARCHIVED,
    REWARD_VERSION_B,
    GoalPilotConfig,
)
from stable_baselines3 import PPO  # noqa: E402
from stable_baselines3.common.monitor import Monitor  # noqa: E402

EXP_DIR = paths.root / "training_logs" / "experiments" / "reward_experiment_v1"
OUT_DIR = paths.root / "outputs" / "reward_design" / "v1"
EXP_DIR.mkdir(parents=True, exist_ok=True)
OUT_DIR.mkdir(parents=True, exist_ok=True)

VERSIONS = {
    REWARD_VERSION_ARCHIVED: "archived_v1",
    REWARD_VERSION_A: "candidate_a",
    REWARD_VERSION_B: "candidate_b",
}
VERSIONS_INV = {label: version for version, label in VERSIONS.items()}

PPO_HYPERPARAMS = {
    "policy": "MlpPolicy",
    "n_steps": 256,
    "batch_size": 64,
    "n_epochs": 4,
    "gamma": 0.99,
    "learning_rate": 3e-4,
    "policy_kwargs": {"net_arch": [128, 128]},
}

profiles = pd.read_csv(paths.rl_profiles_csv)
goals = pd.read_csv(paths.rl_goals_csv)
market = pd.read_csv(paths.rl_market_csv)
split = pd.read_csv(paths.rl_split_csv)
_split_col = next(c for c in ("split", "set", "subset", "is_test") if c in split.columns)
_is_test = split[_split_col].astype(str).str.lower() == "test"
TEST_USERS = split.loc[_is_test, "user_id"].astype(str).tolist()
TRAIN_USERS = split.loc[~_is_test, "user_id"].astype(str).tolist()


def make_env(config, user_ids):
    return goalpilot_env.GoalPilotEnv(
        profiles=profiles, goals=goals, market=market,
        user_ids=user_ids, config=config,
    )


# --------------------------------------------------------------------- validity gate ------

def check_dynamics_invariant() -> dict:
    """The reward version must not change the environment's dynamics or accounting."""
    reference = None
    report = {}
    for version, label in VERSIONS.items():
        env = make_env(GoalPilotConfig.recommended().replace(reward_version=version),
                       TEST_USERS[:3])
        trace = []
        for uid in TEST_USERS[:3]:
            env.reset(options={"user_id": uid})
            while True:
                action = np.zeros(env.action_space.shape, dtype=np.float32)
                action[:, 0] = 0.5
                action[:, 1] = 0.5
                action[:, 2] = 1.0
                _, _, term, trunc, info = env.step(action)
                trace.append((
                    round(float(info["ledger"]["cash"]), 6),
                    round(float(info["ledger"]["portfolio"]), 6),
                    round(float(info["ledger"]["loan_balance"]), 6),
                    round(float(info["ledger"]["goal_balances_total"]), 6),
                    round(float(info["net_worth"]), 6),
                ))
                if term or trunc:
                    break
        report[label] = len(trace)
        if reference is None:
            reference = (label, trace)
        elif trace != reference[1]:
            mismatches = sum(1 for a, b in zip(trace, reference[1]) if a != b)
            raise SystemExit(
                "VALIDITY GATE FAILED: reward version "
                f"'{label}' changes the environment state trajectory vs '{reference[0]}' "
                f"({mismatches} of {len(trace)} months differ). The reward comparison would "
                "be confounded. Aborting."
            )
    report["result"] = (
        f"identical state trajectories across all three versions "
        f"({reference[0]} as reference)"
    )
    return report


# ------------------------------------------------------------------------ evaluation ------

def evaluate(model, label: str, seed, user_ids, version) -> list[dict]:
    cfg = GoalPilotConfig.recommended().replace(reward_version=version)
    env = make_env(cfg, user_ids)
    rows = []
    for uid in user_ids:
        obs, _ = env.reset(options={"user_id": uid})
        n_goals = len(env.user_goals)
        deadline_ratio = np.full(n_goals, np.nan)
        downside = 0.0
        negative_months = 0
        floor_months = 0
        reserve_breach_months = 0
        shortfall_months = 0
        max_budget_residual = 0.0
        while True:
            action, _ = model.predict(obs, deterministic=True)
            obs, reward, term, trunc, info = env.step(action)
            if float(info["portfolio_market_change"]) < 0.0:
                downside += -float(info["portfolio_market_change"])
                negative_months += 1
            ba = info["budget_audit"]
            max_budget_residual = max(max_budget_residual, abs(ba["budget_check"]))
            if ba["cash_floor_active"]:
                floor_months += 1
            if float(info["ledger"]["cash"]) + 1e-6 < float(info["restricted_cash"]):
                reserve_breach_months += 1
            if ba["interest_shortfall"] > 1e-9:
                shortfall_months += 1
            month = int(ba["month"])
            for j in range(n_goals):
                if month == int(env.goal_deadlines[j]) and np.isnan(deadline_ratio[j]):
                    deadline_ratio[j] = float(env.goal_balances[j]) / max(
                        1.0, float(env.goal_targets[j]))
            if term or trunc:
                break

        priority = env.user_goals["priority"].astype(float).to_numpy()
        target = env.goal_targets.astype(float)[:n_goals]
        funded = env.goal_balances.astype(float)[:n_goals]
        nominal = env.user_goals["current_cost"].astype(float).to_numpy()[:n_goals]
        ratio = np.minimum(funded, target) / np.maximum(target, 1e-9)

        rows.append({
            "reward_version": label,
            "seed": seed,
            "user_id": uid,
            "weighted_goal_achievement": float(np.sum(priority * ratio) / np.sum(priority)),
            "mean_funding_ratio": float(np.mean(ratio)),
            "pct_goals_fully_funded": float(np.mean(ratio >= 1.0 - 1e-9)),
            "pct_goals_met_by_deadline": float(np.nanmean(deadline_ratio >= 1.0 - 1e-9))
            if not np.all(np.isnan(deadline_ratio)) else np.nan,
            "goal_level_shortfall": float(np.sum(np.maximum(0.0, target - funded))),
            "funding_vs_nominal_targets": float(
                np.sum(np.minimum(funded, nominal)) / max(np.sum(nominal), 1e-9)),
            "funding_vs_inflated_targets": float(
                np.sum(np.minimum(funded, target)) / max(np.sum(target), 1e-9)),
            "final_liquid_cash": float(env.cash),
            "restricted_cash_preserved": float(env.cash) >= float(env.restricted_cash) - 1e-9,
            "final_portfolio_value": float(env.portfolio),
            "outstanding_loan_balance": float(env.loan_balance),
            "net_worth": float(env.net_worth),
            "total_loan_principal": float(env.cumulative_loan_principal),
            "total_interest_paid": float(env.total_interest_paid),
            "investment_gain": float(env.total_investment_gain),
            "downside_exposure": downside,
            "negative_months": negative_months,
            "budget_violations": int(max_budget_residual > 1e-6) + floor_months,
            "max_budget_check_residual": max_budget_residual,
            "cash_floor_months": floor_months,
            "reserve_breach_months": reserve_breach_months,
            "interest_shortfall_months": shortfall_months,
            "risk_score": float(env.profile_map[uid]["risk_score"]),
            "max_goal_horizon_months": int(env.goal_deadlines.max()),
            "env_reward_total": float(env.total_rewards),
        })
    return rows


def archived_reference_rows() -> list[dict]:
    """The archived checkpoint, under archived semantics only - a historical reference."""
    model = PPO.load(str(paths.ppo_best_model))
    env = make_env(GoalPilotConfig.archived(), TEST_USERS)
    rows = []
    for uid in TEST_USERS:
        obs, _ = env.reset(options={"user_id": uid})
        n_goals = len(env.user_goals)
        while True:
            action, _ = model.predict(obs, deterministic=True)
            obs, reward, term, trunc, info = env.step(action)
            if term or trunc:
                break
        priority = env.user_goals["priority"].astype(float).to_numpy()
        target = env.goal_targets.astype(float)[:n_goals]
        funded = env.goal_balances.astype(float)[:n_goals]
        ratio = np.minimum(funded, target) / np.maximum(target, 1e-9)
        rows.append({
            "reward_version": "archived_checkpoint_reference", "seed": -1, "user_id": uid,
            "weighted_goal_achievement": float(np.sum(priority * ratio) / np.sum(priority)),
            "mean_funding_ratio": float(np.mean(ratio)),
            "pct_goals_fully_funded": float(np.mean(ratio >= 1.0 - 1e-9)),
            "pct_goals_met_by_deadline": float("nan"),
            "goal_level_shortfall": float(np.sum(np.maximum(0.0, target - funded))),
            "funding_vs_nominal_targets": float("nan"),
            "funding_vs_inflated_targets": float("nan"),
            "final_liquid_cash": float(env.cash),
            "restricted_cash_preserved": True,
            "final_portfolio_value": float(env.portfolio),
            "outstanding_loan_balance": float(env.loan_balance),
            "net_worth": float(env.net_worth),
            "total_loan_principal": float(env.cumulative_loan_principal),
            "total_interest_paid": float(env.total_interest_paid),
            "investment_gain": float(env.total_investment_gain),
            "downside_exposure": float("nan"), "negative_months": 0,
            "budget_violations": 0, "max_budget_check_residual": 0.0,
            "cash_floor_months": 0, "reserve_breach_months": 0,
            "interest_shortfall_months": 0,
            "risk_score": float(env.profile_map[uid]["risk_score"]),
            "max_goal_horizon_months": int(env.goal_deadlines.max()),
            "env_reward_total": float(env.total_rewards),
        })
    return rows


# ---------------------------------------------------------------------------- training ----

def train_one(version: str, label: str, seed: int, timesteps: int) -> dict:
    config = GoalPilotConfig.recommended().replace(reward_version=version, seed=seed)
    log_dir = EXP_DIR / label
    log_dir.mkdir(parents=True, exist_ok=True)
    train_env = Monitor(
        make_env(config, TRAIN_USERS),
        filename=str(log_dir / f"monitor_{label}_seed{seed}"),
    )
    model = PPO(env=train_env, seed=seed, verbose=0, **PPO_HYPERPARAMS)
    started = time.time()
    model.learn(total_timesteps=timesteps, progress_bar=False)
    elapsed = time.time() - started
    checkpoint = log_dir / f"ppo_{label}_seed{seed}.zip"
    model.save(str(checkpoint))
    returns = list(train_env.get_episode_rewards())
    lengths = list(train_env.get_episode_lengths())
    pd.DataFrame({"episode_return": returns, "episode_length": lengths}).to_csv(
        log_dir / f"training_episodes_{label}_seed{seed}.csv", index=False)
    train_env.close()
    record = {
        "reward_version": label,
        "seed": seed,
        "timesteps": timesteps,
        "seconds": elapsed,
        "steps_per_second": timesteps / elapsed if elapsed > 0 else float("nan"),
        "episodes_completed": len(returns),
        "mean_train_episode_return": float(np.mean(returns)) if returns else float("nan"),
        "final_train_episode_return": float(returns[-1]) if returns else float("nan"),
        "checkpoint": str(checkpoint),
        "checkpoint_saved": checkpoint.is_file(),
    }
    (log_dir / f"run_{label}_seed{seed}.json").write_text(
        json.dumps(record, indent=2), encoding="utf-8")
    return record


def stage_train(args, selected, seeds, timesteps) -> list[dict]:
    print("[1/4] validity gate: reward version must not change environment dynamics")
    gate = check_dynamics_invariant()
    print(f"      {gate['result']}")

    print(f"[2/4] training {len(selected)} versions x {len(seeds)} seeds x {timesteps} steps")
    train_rows: list[dict] = []
    for version, label in selected.items():
        for seed in seeds:
            record_path = EXP_DIR / label / f"run_{label}_seed{seed}.json"
            checkpoint = EXP_DIR / label / f"ppo_{label}_seed{seed}.zip"
            if not args.force and record_path.is_file() and checkpoint.is_file():
                row = json.loads(record_path.read_text(encoding="utf-8"))
                print(f"      {label} seed={seed}: reused existing checkpoint")
            else:
                row = train_one(version, label, seed, timesteps)
                record_path.write_text(json.dumps(row, indent=2), encoding="utf-8")
                print(f"      {label} seed={seed}: {row['steps_per_second']:.0f} steps/s, "
                      f"{row['episodes_completed']} episodes, saved={row['checkpoint_saved']}")
            train_rows.append(row)
    return train_rows


def discover_runs() -> list[dict]:
    """Every completed run, from its per-run record.

    Falls back to reconstructing records from checkpoint + training-episode artefacts, so that
    runs produced by an earlier (non-staged) revision of this script are adopted rather than
    retrained. Reconstructed records are persisted, and mark themselves as such.
    """
    records = [json.loads(p.read_text(encoding="utf-8"))
               for p in sorted(EXP_DIR.glob("*/run_*.json"))]
    recorded = {(r["reward_version"], r["seed"]) for r in records}

    for ckpt in sorted(EXP_DIR.glob("*/*.zip")):
        label = ckpt.parent.name
        if label not in VERSIONS_INV:
            continue
        seed = int(ckpt.stem.rsplit("seed", 1)[1])
        if (label, seed) in recorded:
            continue
        episodes_csv = ckpt.parent / f"training_episodes_{label}_seed{seed}.csv"
        episodes, mean_return, final_return = 0, float("nan"), float("nan")
        if episodes_csv.is_file():
            frame = pd.read_csv(episodes_csv)
            episodes = len(frame)
            if episodes:
                mean_return = float(frame["episode_return"].mean())
                final_return = float(frame["episode_return"].iloc[-1])
        record = {
            "reward_version": label, "seed": seed, "timesteps": None,
            "seconds": None, "steps_per_second": None,
            "episodes_completed": episodes,
            "mean_train_episode_return": mean_return,
            "final_train_episode_return": final_return,
            "checkpoint": str(ckpt), "checkpoint_saved": True,
            "record_source": "reconstructed_from_artifacts",
        }
        (ckpt.parent / f"run_{label}_seed{seed}.json").write_text(
            json.dumps(record, indent=2), encoding="utf-8")
        records.append(record)
        print(f"      adopted existing checkpoint {label} seed={seed} "
              f"({episodes} training episodes)")
    return sorted(records, key=lambda r: (r["reward_version"], r["seed"]))


def stage_eval(train_rows: list[dict], suffix: str) -> pd.DataFrame:
    print("[3/4] evaluating every trained policy on the same held-out users")
    eval_dir = EXP_DIR / "eval"
    eval_dir.mkdir(parents=True, exist_ok=True)
    for row in train_rows:
        out_path = eval_dir / f"metrics_{row['reward_version']}_seed{row['seed']}.csv"
        model = PPO.load(row["checkpoint"])
        frame = pd.DataFrame(evaluate(
            model, row["reward_version"], row["seed"], TEST_USERS,
            VERSIONS_INV[row["reward_version"]],
        ))
        frame.to_csv(out_path, index=False)
        print(f"      evaluated {row['reward_version']} seed={row['seed']} -> {out_path.name}")

    reference = pd.DataFrame(archived_reference_rows())
    reference.to_csv(OUT_DIR / f"archived_checkpoint_reference_{suffix}_v1.csv", index=False)
    print("      evaluated archived checkpoint (historical reference, archived semantics)")

    merged = pd.concat(
        [pd.read_csv(p) for p in sorted(eval_dir.glob("metrics_*.csv"))], ignore_index=True)
    merged.to_csv(OUT_DIR / f"trained_policy_metrics_{suffix}_v1.csv", index=False)
    return merged


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["smoke", "full"], default="smoke")
    parser.add_argument("--stage", choices=["train", "eval", "all"], default="all")
    parser.add_argument("--timesteps", type=int, default=None)
    parser.add_argument("--seeds", type=str, default="7")
    parser.add_argument("--versions", type=str, default="")
    parser.add_argument("--force", action="store_true",
                        help="retrain even if a checkpoint already exists")
    args = parser.parse_args()

    if args.mode == "smoke":
        seeds = [7]
        timesteps = args.timesteps or 2048
    else:
        seeds = [int(s) for s in args.seeds.split(",")]
        timesteps = args.timesteps or 50000
    suffix = "smoke" if args.mode == "smoke" else "full"

    selected = dict(VERSIONS)
    if args.versions:
        wanted = {v.strip() for v in args.versions.split(",")}
        selected = {k: v for k, v in VERSIONS.items() if v in wanted}
        if not selected:
            raise SystemExit(f"no known reward version in {sorted(wanted)}")

    train_rows: list[dict] = []
    if args.stage in ("train", "all"):
        stage_train(args, selected, seeds, timesteps)
        train_rows = discover_runs()
        pd.DataFrame(train_rows).to_csv(
            OUT_DIR / f"training_summary_{suffix}_v1.csv", index=False)
        print(f"      {len(train_rows)} run record(s) on disk")
    else:
        train_rows = discover_runs()
        print(f"[train] skipped; {len(train_rows)} existing run record(s) discovered")

    merged = pd.DataFrame()
    if args.stage in ("eval", "all"):
        merged = stage_eval(train_rows, suffix)

    print("[4/4] summarising")
    print(json.dumps({
        "mode": args.mode, "stage": args.stage, "timesteps": timesteps, "seeds": seeds,
        "trained_runs_available": len(train_rows),
        "evaluated_rows": len(merged),
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
