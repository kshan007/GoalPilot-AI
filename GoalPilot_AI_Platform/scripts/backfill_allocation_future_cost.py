"""Repair stored plan allocations whose ``future_goal_cost`` was written as zero.

Before the LP/hybrid allocation rows carried the goal's cost basis, every LP and hybrid run
persisted ``future_goal_cost = 0`` while the same row held a non-zero ``funding_gap`` — the
Allocation table on the Optimise screen then showed a funding gap larger than the goal's own
future cost. The engine fix stops new runs from doing this; this script repairs the history.

It is deliberately conservative and repeatable:

* dry run by default — nothing is written unless ``--apply`` is passed;
* only rows with ``future_goal_cost == 0`` and ``funding_gap > 0`` are considered;
* the value is recomputed from the linked goal (``current_cost``, ``target_date``) using the
  annual inflation recorded on that run, measured from the run's own date — never from today;
* rows whose goal is missing, or whose run has no recorded inflation, are reported and skipped;
* a JSON backup of every affected row is written before any UPDATE.

Usage, from the repository root::

    python scripts/backfill_allocation_future_cost.py           # dry run
    python scripts/backfill_allocation_future_cost.py --apply    # write the repair
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from sqlalchemy import select  # noqa: E402

from app.db import session_scope  # noqa: E402
from app.models import FinancialProfile, Goal, GoalAllocation, OptimizationRun  # noqa: E402
from app.services.money import months_between, round_money  # noqa: E402

DEFAULT_INFLATION_KEY = "annual_inflation"


def _inflation_for(run: OptimizationRun, fallback: float | None) -> float | None:
    try:
        assumptions = json.loads(run.assumptions_json or "{}")
    except json.JSONDecodeError:
        assumptions = {}
    value = assumptions.get(DEFAULT_INFLATION_KEY)
    if isinstance(value, (int, float)):
        return float(value)
    return fallback


def _run_date(run: OptimizationRun) -> dt.date:
    stamp = getattr(run, "created_at", None)
    if isinstance(stamp, dt.datetime):
        return stamp.date()
    if isinstance(stamp, dt.date):
        return stamp
    return dt.date.today()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the repair (default: dry run)")
    parser.add_argument(
        "--backup",
        default="outputs/inspection/allocation_backfill_backup.json",
        help="where to write the pre-change row snapshot",
    )
    args = parser.parse_args()

    with session_scope() as db:
        rows = db.execute(
            select(GoalAllocation)
            .where(GoalAllocation.future_goal_cost == 0)
            .where(GoalAllocation.funding_gap > 0)
            .order_by(GoalAllocation.optimization_run_id, GoalAllocation.id)
        ).scalars().all()

        if not rows:
            print("No allocation rows need repair.")
            return 0

        profiles: dict[int, FinancialProfile | None] = {}
        runs: dict[int, OptimizationRun] = {}
        goals: dict[int, Goal | None] = {}
        changes: list[dict] = []
        skipped: list[str] = []

        for allocation in rows:
            run = runs.get(allocation.optimization_run_id)
            if run is None:
                run = db.get(OptimizationRun, allocation.optimization_run_id)
                runs[allocation.optimization_run_id] = run
            if run is None:
                skipped.append(f"allocation {allocation.id}: run missing")
                continue

            if allocation.goal_id is None:
                skipped.append(
                    f"allocation {allocation.id} (run #{run.id}): no linked goal to derive the cost"
                )
                continue

            if allocation.goal_id not in goals:
                goals[allocation.goal_id] = db.get(Goal, allocation.goal_id)
            goal = goals[allocation.goal_id]
            if goal is None:
                skipped.append(
                    f"allocation {allocation.id} (run #{run.id}): goal {allocation.goal_id} deleted"
                )
                continue

            if run.user_id not in profiles:
                profiles[run.user_id] = db.execute(
                    select(FinancialProfile).where(FinancialProfile.user_id == run.user_id)
                ).scalar_one_or_none()
            profile = profiles[run.user_id]
            fallback = (
                float(profile.inflation_assumption)
                if profile is not None and profile.inflation_assumption is not None
                else None
            )
            inflation = _inflation_for(run, fallback)
            if inflation is None:
                skipped.append(
                    f"allocation {allocation.id} (run #{run.id}): no inflation assumption recorded"
                )
                continue

            months = max(1, months_between(_run_date(run), goal.target_date))
            derived = float(goal.current_cost) * (1 + inflation) ** (months / 12)
            if derived <= 0:
                skipped.append(
                    f"allocation {allocation.id} (run #{run.id}): derived cost is not positive"
                )
                continue

            changes.append(
                {
                    "allocation_id": allocation.id,
                    "run_id": run.id,
                    "goal_id": goal.id,
                    "goal_name": allocation.goal_name or goal.name,
                    "before": {
                        "future_goal_cost": float(allocation.future_goal_cost),
                        "funding_gap": float(allocation.funding_gap),
                    },
                    "after": {"future_goal_cost": float(round_money(derived))},
                    "basis": {
                        "current_cost": float(goal.current_cost),
                        "target_date": goal.target_date.isoformat(),
                        "months_from_run_date": months,
                        "annual_inflation": inflation,
                        "run_date": _run_date(run).isoformat(),
                    },
                }
            )

        if not changes:
            print("Nothing derivable to repair.")
            for line in skipped:
                print("  skipped:", line)
            return 1

        print(f"{len(changes)} row(s) can be repaired; {len(skipped)} skipped.")
        for change in changes:
            print(
                f"  run #{change['run_id']} allocation {change['allocation_id']} "
                f"{change['goal_name']!r}: future_goal_cost "
                f"{change['before']['future_goal_cost']:,.2f} -> {change['after']['future_goal_cost']:,.2f} "
                f"(gap {change['before']['funding_gap']:,.2f}; "
                f"{change['basis']['current_cost']:,.0f} inflated {change['basis']['annual_inflation']:.2%} "
                f"over {change['basis']['months_from_run_date']} months)"
            )
        for line in skipped:
            print("  skipped:", line)

        if not args.apply:
            print("\nDry run only. Re-run with --apply to write these changes.")
            return 0

        backup_path = Path(args.backup)
        if not backup_path.is_absolute():
            backup_path = Path(__file__).resolve().parent.parent / backup_path
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        backup_path.write_text(
            json.dumps(
                {
                    "written_at": dt.datetime.now().isoformat(timespec="seconds"),
                    "changes": changes,
                    "skipped": skipped,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\nBackup written to {backup_path}")

        for change in changes:
            allocation = db.get(GoalAllocation, change["allocation_id"])
            if allocation is None:
                continue
            allocation.future_goal_cost = round_money(change["after"]["future_goal_cost"])

        print(f"Applied {len(changes)} update(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
