"""Forecasting: cold start, personalisation on evidence, leakage, backtesting, isolation."""
from __future__ import annotations

import datetime as dt

import pytest

from app.services.forecasting import (
    BASELINE_ESTIMATE,
    BASELINE_RECURRING,
    EWMA_05,
    METHOD_VERSION,
    MonthObservation,
    RECURRING_MEDIAN,
    ROLLING_MEAN_3,
    backtest,
    detect_persistent_overspend,
    detect_recurring,
    forecast_month,
    index_to_period,
    next_period,
    period_to_index,
    previous_periods,
)

PERIOD = "2026-06"


def obs(period, category, amount):
    return MonthObservation(period=period, category=category, amount=amount)


def test_period_arithmetic_handles_year_boundaries():
    assert period_to_index("2026-12") + 1 == period_to_index("2027-01")
    assert index_to_period(period_to_index("2026-12")) == "2026-12"
    assert index_to_period(period_to_index("2026-01")) == "2026-01"
    assert previous_periods("2026-01", 2) == ["2025-11", "2025-12"]
    assert next_period("2026-12") == "2027-01"


def test_cold_start_uses_declared_values_only():
    result = forecast_month(
        [],
        period=PERIOD,
        categories=["food_groceries", "housing"],
        recurring_amounts={"housing": 20_000},
        category_estimates={"food_groceries": 9_500},
    )
    by_cat = {c.category: c for c in result.category_forecasts}
    assert by_cat["housing"].amount == 20_000
    assert by_cat["housing"].method == BASELINE_RECURRING
    assert by_cat["housing"].is_provisional is True
    assert by_cat["food_groceries"].amount == 9_500
    assert by_cat["food_groceries"].method == BASELINE_ESTIMATE
    assert result.personalised is False
    assert result.months_of_history == 0
    assert result.warnings


def test_no_history_and_no_estimate_yields_zero_not_a_guess():
    result = forecast_month([], period=PERIOD, categories=["shopping"])
    item = result.category_forecasts[0]
    assert item.amount == 0.0
    assert "No history" in item.note


def test_below_minimum_history_stays_on_a_simple_mean():
    history = [obs("2026-04", "food_groceries", 10_000), obs("2026-05", "food_groceries", 12_000)]
    result = forecast_month(
        history, period=PERIOD, categories=["food_groceries"], min_history_months=3
    )
    item = result.category_forecasts[0]
    assert item.method == ROLLING_MEAN_3
    assert item.amount == pytest.approx(11_000)
    # it is derived from real actuals, so it is not a cold-start guess — but the quality is
    # flagged as low and no personalised method was allowed yet
    assert item.is_provisional is False
    assert item.data_quality == "low"
    assert result.personalised is False
    assert any("held back" in w for w in result.warnings)


def test_enough_history_personalises_and_reports_evidence():
    history = [
        obs("2025-12", "food_groceries", 10_000),
        obs("2026-01", "food_groceries", 11_500),
        obs("2026-02", "food_groceries", 12_500),
        obs("2026-03", "food_groceries", 13_000),
        obs("2026-04", "food_groceries", 14_000),
        obs("2026-05", "food_groceries", 15_000),
    ]
    result = forecast_month(
        history, period=PERIOD, categories=["food_groceries"], min_history_months=3
    )
    item = result.category_forecasts[0]
    assert item.method in (ROLLING_MEAN_3, EWMA_05, RECURRING_MEDIAN)
    assert item.history_months_used == 6
    assert item.data_quality in ("fair", "good")
    assert "Backtest MAE" in item.note
    assert result.personalised is True


def test_forecast_ignores_periods_at_or_after_the_cutoff():
    """Leakage guard: a future actual must not influence the forecast for that period."""
    base = [
        obs("2026-04", "travel", 4_000),
        obs("2026-05", "travel", 4_200),
    ]
    clean = forecast_month(base, period=PERIOD, categories=["travel"], min_history_months=3)
    leaked = forecast_month(
        base + [obs(PERIOD, "travel", 900_000), obs("2026-07", "travel", 900_000)],
        period=PERIOD,
        categories=["travel"],
        min_history_months=3,
    )
    clean_item = clean.category_forecasts[0]
    leaked_item = leaked.category_forecasts[0]
    assert clean_item.amount == leaked_item.amount
    assert leaked_item.history_months_used == 2
    assert leaked.months_of_history == 2


def test_personalisation_requires_beating_the_baseline():
    """A flat series is already predicted perfectly by the declared value."""
    history = [obs(f"2026-0{m}", "subscriptions", 500) for m in range(1, 7)]
    result = forecast_month(
        history,
        period=PERIOD,
        categories=["subscriptions"],
        recurring_amounts={"subscriptions": 500},
        min_history_months=3,
    )
    item = result.category_forecasts[0]
    assert item.method == BASELINE_RECURRING
    assert item.amount == 500


def test_recurring_detection_needs_stability_and_presence():
    stable = [obs(f"2026-0{m}", "subscriptions", 1_000) for m in range(1, 7)]
    erratic = [
        obs("2026-01", "shopping", 500),
        obs("2026-02", "shopping", 9_000),
        obs("2026-03", "shopping", 200),
        obs("2026-04", "shopping", 12_000),
    ]
    found = {r["category"] for r in detect_recurring(stable + erratic)}
    assert "subscriptions" in found
    assert "shopping" not in found


def test_recurring_detection_needs_at_least_three_months():
    sparse = [obs("2026-04", "insurance", 2_000), obs("2026-05", "insurance", 2_000)]
    assert detect_recurring(sparse) == []


def test_persistent_overspend_requires_consecutive_evidence():
    budgets = {"food_groceries": 10_000, "travel": 5_000}
    three_in_a_row = [
        obs("2026-01", "food_groceries", 12_000),
        obs("2026-02", "food_groceries", 12_500),
        obs("2026-03", "food_groceries", 13_500),
    ]
    only_two = [
        obs("2026-01", "travel", 9_000),
        obs("2026-02", "travel", 9_000),
    ]
    flagged = {
        f["category"]
        for f in detect_persistent_overspend(three_in_a_row + only_two, budgets)
    }
    assert "food_groceries" in flagged
    assert "travel" not in flagged  # only two months, and then it stops

    broken_streak = [
        obs("2026-01", "travel", 9_000),
        obs("2026-02", "travel", 1_000),  # within budget: the streak breaks
        obs("2026-03", "travel", 9_000),
        obs("2026-04", "travel", 9_000),
    ]
    assert "travel" not in {
        f["category"] for f in detect_persistent_overspend(broken_streak, budgets)
    }


def test_persistent_overspend_without_a_budget_is_not_reported():
    history = [obs(f"2026-0{m}", "shopping", 50_000) for m in range(1, 5)]
    assert detect_persistent_overspend(history, {}) == []


def test_backtest_reports_insufficient_history_honestly():
    result = backtest([obs("2026-05", "travel", 1_000)])
    assert result["periods_evaluated"] == 0
    assert result["method_mae"] is None
    assert "Needs at least" in result["detail"]


def test_backtest_walks_forward_without_looking_ahead():
    history = [
        obs("2025-12", "food_groceries", 10_000),
        obs("2026-01", "food_groceries", 11_000),
        obs("2026-02", "food_groceries", 12_000),
        obs("2026-03", "food_groceries", 13_000),
        obs("2026-04", "food_groceries", 14_000),
    ]
    result = backtest(history, min_history_months=3)
    assert result["periods_evaluated"] >= 1
    assert result["method_mae"] is not None
    assert result["baseline_mae"] is not None
    assert result["improvement"] is not None


def test_method_version_is_recorded():
    result = forecast_month([], period=PERIOD, categories=["other"],
                            category_estimates={"other": 100})
    assert result.category_forecasts[0].method_version == METHOD_VERSION


def test_forecast_is_per_user_via_the_api(client, registered, second_user):
    """Two users with different histories get different forecasts from the same endpoint."""
    from tests.conftest import seed_profile_and_goal

    seed_profile_and_goal(registered)
    seed_profile_and_goal(second_user)
    period = dt.date.today().strftime("%Y-%m")

    for user, amount in ((registered, 20_000), (second_user, 3_000)):
        client.post(f"/api/months/{period}/open", headers=user["headers"])
        client.post(
            f"/api/months/{period}/estimate-expenses",
            headers=user["headers"],
            json={"category_estimates": {"shopping": amount}, "persist": True},
        )

    mine = client.get(f"/api/months/{period}", headers=registered["headers"]).json()
    theirs = client.get(f"/api/months/{period}", headers=second_user["headers"]).json()
    mine_shopping = next(c for c in mine["forecast"]["categories"] if c["category"] == "shopping")
    theirs_shopping = next(
        c for c in theirs["forecast"]["categories"] if c["category"] == "shopping"
    )
    assert mine_shopping["amount"] == 20_000
    assert theirs_shopping["amount"] == 3_000


def test_forecast_history_and_accuracy_endpoints(client, registered):
    from tests.conftest import seed_profile_and_goal

    seed_profile_and_goal(registered)
    period = dt.date.today().strftime("%Y-%m")
    client.post(f"/api/months/{period}/open", headers=registered["headers"])
    client.post(
        f"/api/months/{period}/estimate-expenses",
        headers=registered["headers"],
        json={"category_estimates": {"food_groceries": 10_000}, "persist": True},
    )
    client.post(
        f"/api/months/{period}/transactions",
        headers=registered["headers"],
        json={
            "kind": "expense", "category": "food_groceries", "label": "Groceries",
            "amount": 12_000, "txn_date": dt.date.today().isoformat(), "status": "actual",
        },
    )
    client.post(f"/api/months/{period}/reconcile", headers=registered["headers"], json={})

    history = client.get("/api/forecast/history", headers=registered["headers"]).json()
    assert history["count"] > 0
    assert all("input_cutoff" in f for f in history["forecasts"])

    accuracy = client.get("/api/forecast/accuracy", headers=registered["headers"]).json()
    assert accuracy["periods_evaluated"] == 1
    assert accuracy["mae_per_period"] is not None
    assert "not meaningful" in accuracy["evidence_note"]
