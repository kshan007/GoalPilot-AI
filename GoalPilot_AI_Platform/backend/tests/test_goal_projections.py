"""Regression tests for the allocation-to-goal join.

A real defect lived here: `project_goals` indexed the allocation frame by `goal_id` but looked
goals up by `f"G{id}"`, so the lookup never matched. Every goal then reported `planned = None`
and no shortfall, while the optimiser had in fact allocated money — and the recommendation layer,
reading "no allocation", called every goal underfunded. Both readings were wrong.
"""
from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pandas as pd
import pytest

from app.services.goals import project_goals


def _goal(goal_id: int, cost: float, days: int = 1825, priority: int = 3) -> SimpleNamespace:
    return SimpleNamespace(
        id=goal_id,
        name=f"Goal {goal_id}",
        current_cost=cost,
        current_funded_amount=0.0,
        target_date=dt.date.today() + dt.timedelta(days=days),
        priority=priority,
        criticality=3,
        goal_type="custom",
        date_flexible=True,
        amount_flexible=True,
    )


def _frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _run(goals, frame):
    return project_goals(
        goals,
        inflation=0.0,
        savings_return=0.0,
        investment_return=0.0,
        monthly_surplus=20000.0,
        available_cash=0.0,
        allocations=frame,
    )


def test_allocation_matches_when_frame_carries_numeric_goal_id():
    goals = [_goal(1, 100_000), _goal(2, 200_000)]
    frame = _frame(
        [
            {
                "goal_id": 1,
                "goal_ref": "G1",
                "monthly_savings_contribution": 5000.0,
                "monthly_investment_contribution": 0.0,
                "projected_new_funding": 100_000.0,
                "shortfall": 0.0,
                "achievement_ratio": 1.0,
            },
            {
                "goal_id": 2,
                "goal_ref": "G2",
                "monthly_savings_contribution": 3000.0,
                "monthly_investment_contribution": 0.0,
                "projected_new_funding": 120_000.0,
                "shortfall": 80_000.0,
                "achievement_ratio": 0.6,
            },
        ]
    )
    rows = {row.goal_id: row for row in _run(goals, frame)}

    assert rows[1].projected_shortfall == pytest.approx(0.0)
    assert rows[1].achievement_ratio == pytest.approx(1.0)
    assert rows[1].projected_funding == pytest.approx(100_000.0)
    assert rows[2].projected_shortfall == pytest.approx(80_000.0)
    assert rows[2].achievement_ratio == pytest.approx(0.6)


def test_allocation_matches_when_frame_carries_only_goal_ref():
    goals = [_goal(7, 150_000)]
    frame = _frame(
        [
            {
                "goal_ref": "G7",
                "monthly_savings_contribution": 2500.0,
                "monthly_investment_contribution": 0.0,
                "projected_new_funding": 150_000.0,
                "shortfall": 0.0,
                "achievement_ratio": 1.0,
            }
        ]
    )
    rows = _run(goals, frame)
    assert rows[0].projected_shortfall == pytest.approx(0.0)
    assert rows[0].achievement_ratio == pytest.approx(1.0)


def test_unallocated_goal_is_reported_as_unplanned_not_as_funded():
    goals = [_goal(1, 100_000), _goal(2, 250_000)]
    frame = _frame(
        [
            {
                "goal_id": 1,
                "goal_ref": "G1",
                "monthly_savings_contribution": 5000.0,
                "monthly_investment_contribution": 0.0,
                "projected_new_funding": 100_000.0,
                "shortfall": 0.0,
                "achievement_ratio": 1.0,
            }
        ]
    )
    rows = {row.goal_id: row for row in _run(goals, frame)}

    # `project_goals` answers "could this goal be afforded on the available surplus?" — a
    # hypothetical. Without an allocation there is no planned funding and no achieved ratio, so
    # the two plan-derived fields stay None even though the hypothetical shortfall may be zero.
    # The recommendation layer therefore must not read projected_shortfall as a plan outcome.
    # rows is keyed by goal_id, so rows[2] is the goal that received no allocation.
    assert rows[1].projected_funding is not None, "the allocated goal must carry plan funding"
    assert rows[2].projected_funding is None
    assert rows[2].achievement_ratio is None
