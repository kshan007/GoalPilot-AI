"""Phase 3 — assess whether 50,000 timesteps is sufficient, from the existing runs only.

Reads the per-episode training logs of the nine completed runs (archive: `training_logs/
experiments/reward_experiment_v1/*/training_episodes_*.csv`) and reports:

* learning-curve shape: first-50 vs last-50 episode return, and the linear slope over the last
  100 episodes with its standard error
* seed variability of the final return
* measured throughput, from which the wall-clock of a 150k / 300k budget experiment is
  extrapolated

No training is started. Outputs go to `outputs/reward_design/v2/`.
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

EXP_DIR = ROOT / "training_logs" / "experiments" / "reward_experiment_v1"
OUT_DIR = ROOT / "outputs" / "reward_design" / "v2"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def slope_with_se(y: np.ndarray) -> tuple[float, float]:
    x = np.arange(len(y), dtype=float)
    if len(y) < 3:
        return float("nan"), float("nan")
    design = np.column_stack([np.ones_like(x), x])
    beta, *_ = np.linalg.lstsq(design, y, rcond=None)
    resid = y - design @ beta
    dof = max(1, len(y) - 2)
    sigma2 = float(resid @ resid) / dof
    cov = sigma2 * np.linalg.inv(design.T @ design)
    return float(beta[1]), float(np.sqrt(cov[1, 1]))


def main() -> None:
    rows, curves = [], {}
    for path in sorted(EXP_DIR.glob("*/training_episodes_*.csv")):
        label = path.stem.replace("training_episodes_", "")
        version, seed = label.rsplit("_seed", 1)
        frame = pd.read_csv(path)
        returns = frame["episode_return"].to_numpy(dtype=float)
        n = len(returns)
        if n < 60:
            continue
        tail = returns[-100:]
        slope, se = slope_with_se(tail)
        rows.append({
            "reward_version": version, "seed": int(seed), "episodes": n,
            "implied_timesteps": n * 142,
            "first50_mean": float(returns[:50].mean()),
            "last50_mean": float(returns[-50:].mean()),
            "best_episode": float(returns.max()),
            "final_episode": float(returns[-1]),
            "tail100_slope_per_episode": slope,
            "tail100_slope_se": se,
            "tail100_slope_t": float(slope / se) if se > 0 else float("nan"),
            "still_improving": bool(se > 0 and slope / se > 2.0),
            "residual_sd_tail": float(np.std(tail, ddof=1)),
        })
        curves[label] = returns
    per_run = pd.DataFrame(rows).sort_values(["reward_version", "seed"])
    per_run.to_csv(OUT_DIR / "learning_curve_per_run_v1.csv", index=False)

    summary = []
    for version, block in per_run.groupby("reward_version"):
        summary.append({
            "reward_version": version,
            "seeds": int(len(block)),
            "mean_first50": float(block["first50_mean"].mean()),
            "mean_last50": float(block["last50_mean"].mean()),
            "seed_sd_of_last50": float(block["last50_mean"].std(ddof=1)),
            "mean_tail_slope": float(block["tail100_slope_per_episode"].mean()),
            "max_abs_slope_t": float(block["tail100_slope_t"].abs().max()),
            "runs_still_improving": int(block["still_improving"].sum()),
            "mean_residual_sd_tail": float(block["residual_sd_tail"].mean()),
        })
    summary_df = pd.DataFrame(summary)
    summary_df.to_csv(OUT_DIR / "learning_curve_summary_v1.csv", index=False)

    # throughput from the recorded per-run timings, where available
    records = [json.loads(p.read_text(encoding="utf-8"))
               for p in sorted(EXP_DIR.glob("*/run_*.json"))]
    speeds = [r["steps_per_second"] for r in records
              if r.get("steps_per_second") and np.isfinite(r["steps_per_second"])]
    measured_speed = float(np.mean(speeds)) if speeds else 550.0

    budgets = [50000, 150000, 300000]
    extrapolation = {
        str(b): {
            "seconds_per_run": b / measured_speed,
            "minutes_per_run": b / measured_speed / 60.0,
            "minutes_for_3_seeds": 3 * b / measured_speed / 60.0,
        }
        for b in budgets
    }
    digest = {
        "measured_steps_per_second": measured_speed,
        "runs_measured": len(speeds),
        "per_version_summary": summary,
        "extrapolated_wall_clock": extrapolation,
        "note": (
            "Extrapolation assumes constant throughput; PPO cost per timestep grows only "
            "with the number of gradient updates, which is linear in timesteps here, so this "
            "is a fair estimate on this host. No GPU is available."
        ),
    }
    (OUT_DIR / "learning_curve_audit_v1.json").write_text(
        json.dumps(digest, indent=2, default=str), encoding="utf-8")
    print(json.dumps(digest, indent=2, default=str))


if __name__ == "__main__":
    main()
