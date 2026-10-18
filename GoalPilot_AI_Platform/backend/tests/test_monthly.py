"""Monthly workflow: opening, entry, estimation, reconciliation, preservation, duplicates."""
from __future__ import annotations

import datetime as dt

from tests.conftest import seed_profile_and_goal

PERIOD = dt.date.today().strftime("%Y-%m")


def _open(client, headers, period=PERIOD):
    response = client.post(f"/api/months/{period}/open", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_open_month_seeds_recurring_income_and_loan_payments(client, registered):
    seed_profile_and_goal(registered)
    detail = _open(client, registered["headers"])
    assert detail["month"]["period"] == PERIOD
    labels = {(t["kind"], t["category"]) for t in detail["transactions"]}
    assert ("income", "income") in labels
    assert ("expense", "loan_payments") in labels
    # the seeds are estimated, not actual
    assert all(t["status"] == "estimated" for t in detail["transactions"])


def test_open_month_is_idempotent(client, registered):
    seed_profile_and_goal(registered)
    first = _open(client, registered["headers"])
    second = _open(client, registered["headers"])
    assert len(first["transactions"]) == len(second["transactions"])


def test_months_must_be_opened_first(client, registered):
    seed_profile_and_goal(registered)
    assert client.get("/api/months/2029-01", headers=registered["headers"]).status_code == 422


def test_invalid_period_format_is_rejected(client, registered):
    seed_profile_and_goal(registered)
    assert client.post("/api/months/2029-1/open", headers=registered["headers"]).status_code == 422


def test_record_income_and_expense_updates_totals(client, registered):
    seed_profile_and_goal(registered)
    _open(client, registered["headers"])

    expense = client.post(
        f"/api/months/{PERIOD}/transactions",
        headers=registered["headers"],
        json={
            "kind": "expense", "category": "food_groceries", "label": "Groceries",
            "amount": 12_000, "txn_date": dt.date.today().isoformat(), "status": "actual",
        },
    )
    assert expense.status_code == 201, expense.text
    assert expense.json()["classification"] == "essential"

    discretionary = client.post(
        f"/api/months/{PERIOD}/transactions",
        headers=registered["headers"],
        json={
            "kind": "expense", "category": "entertainment", "label": "Cinema",
            "amount": 2_000, "txn_date": dt.date.today().isoformat(), "status": "actual",
        },
    )
    assert discretionary.json()["classification"] == "discretionary"

    income = client.post(
        f"/api/months/{PERIOD}/transactions",
        headers=registered["headers"],
        json={
            "kind": "income", "category": "income", "label": "Freelance",
            "amount": 15_000, "txn_date": dt.date.today().isoformat(), "status": "actual",
        },
    )
    assert income.status_code == 201

    detail = client.get(f"/api/months/{PERIOD}", headers=registered["headers"]).json()
    assert detail["month"]["total_expense_actual"] == 14_000.0
    assert detail["month"]["total_income_actual"] == 15_000.0
    assert detail["categories"]["food_groceries"]["actual"] == 12_000.0


def test_duplicate_submission_is_a_no_op(client, registered):
    seed_profile_and_goal(registered)
    _open(client, registered["headers"])
    payload = {
        "kind": "expense", "category": "utilities", "label": "Electricity",
        "amount": 3_000, "txn_date": dt.date.today().isoformat(), "status": "actual",
        "client_ref": "utility-bill-2026-01",
    }
    first = client.post(f"/api/months/{PERIOD}/transactions", headers=registered["headers"], json=payload)
    second = client.post(f"/api/months/{PERIOD}/transactions", headers=registered["headers"], json=payload)
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["id"] == second.json()["id"]

    detail = client.get(f"/api/months/{PERIOD}", headers=registered["headers"]).json()
    utilities = [t for t in detail["transactions"] if t["category"] == "utilities"]
    assert len(utilities) == 1


def test_edit_and_delete_transaction(client, registered):
    seed_profile_and_goal(registered)
    _open(client, registered["headers"])
    created = client.post(
        f"/api/months/{PERIOD}/transactions",
        headers=registered["headers"],
        json={
            "kind": "expense", "category": "travel", "label": "Trip",
            "amount": 8_000, "txn_date": dt.date.today().isoformat(), "status": "actual",
        },
    ).json()

    updated = client.put(
        f"/api/months/{PERIOD}/transactions/{created['id']}",
        headers=registered["headers"],
        json={"amount": 5_000},
    )
    assert updated.status_code == 200
    assert updated.json()["amount"] == 5_000.0

    assert client.delete(
        f"/api/months/{PERIOD}/transactions/{created['id']}", headers=registered["headers"]
    ).status_code == 200
    detail = client.get(f"/api/months/{PERIOD}", headers=registered["headers"]).json()
    assert all(t["id"] != created["id"] for t in detail["transactions"])


def test_estimate_expenses_cold_start_is_provisional(client, registered):
    seed_profile_and_goal(registered)
    _open(client, registered["headers"])
    response = client.post(
        f"/api/months/{PERIOD}/estimate-expenses",
        headers=registered["headers"],
        json={
            "category_estimates": {"food_groceries": 12_000, "transport": 4_000},
            "persist": True,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["history_months_available"] == 0
    assert body["personalised"] is False
    assert "Cold-start" in body["estimation_method"]
    assert "has not learned" in body["data_quality_note"]

    by_category = {c["category"]: c for c in body["forecast"]["category_forecasts"]}
    assert by_category["food_groceries"]["amount"] == 12_000
    assert by_category["food_groceries"]["method"] == "baseline_estimate"
    # the loan payment comes from the user's own declared EMI, not from a guess
    assert by_category["loan_payments"]["amount"] == 12_000
    assert by_category["loan_payments"]["method"] == "baseline_recurring"


def test_estimate_is_persisted_and_carries_its_method_and_cutoff(client, registered):
    seed_profile_and_goal(registered)
    _open(client, registered["headers"])
    client.post(
        f"/api/months/{PERIOD}/estimate-expenses",
        headers=registered["headers"],
        json={"category_estimates": {"food_groceries": 11_000}, "persist": True},
    )
    detail = client.get(f"/api/months/{PERIOD}", headers=registered["headers"]).json()
    assert detail["forecast"] is not None
    assert detail["forecast"]["method_version"] == "v1"
    entry = next(c for c in detail["forecast"]["categories"] if c["category"] == "food_groceries")
    assert entry["input_cutoff"]
    assert entry["history_months_used"] == 0


def test_reconciliation_preserves_the_forecast(client, registered):
    seed_profile_and_goal(registered)
    _open(client, registered["headers"])
    client.post(
        f"/api/months/{PERIOD}/estimate-expenses",
        headers=registered["headers"],
        json={"category_estimates": {"food_groceries": 10_000}, "persist": True},
    )
    # actual comes in 20% over
    client.post(
        f"/api/months/{PERIOD}/transactions",
        headers=registered["headers"],
        json={
            "kind": "expense", "category": "food_groceries", "label": "Groceries",
            "amount": 12_000, "txn_date": dt.date.today().isoformat(), "status": "actual",
        },
    )
    reconcile = client.post(
        f"/api/months/{PERIOD}/reconcile",
        headers=registered["headers"],
        json={"mark_actuals": True, "update_future_forecast": True},
    )
    assert reconcile.status_code == 200, reconcile.text
    body = reconcile.json()
    assert body["forecast_preserved"] is True

    row = next(r for r in body["rows"] if r["category"] == "food_groceries")
    assert row["forecast"] == 10_000.0
    assert row["actual"] == 12_000.0
    assert row["abs_error"] == 2_000.0
    assert row["pct_error"] == 20.0
    assert "food_groceries" in body["over_budget_categories"]

    # the stored forecast is unchanged, and the actual lives beside it
    detail = client.get(f"/api/months/{PERIOD}", headers=registered["headers"]).json()
    stored = next(c for c in detail["forecast"]["categories"] if c["category"] == "food_groceries")
    assert stored["amount"] == 10_000.0
    assert detail["month"]["status"] == "reconciled"
    assert detail["reconciliation"]["rows"]


def test_reconciliation_is_idempotent(client, registered):
    seed_profile_and_goal(registered)
    _open(client, registered["headers"])
    client.post(
        f"/api/months/{PERIOD}/estimate-expenses",
        headers=registered["headers"],
        json={"category_estimates": {"housing": 20_000}, "persist": True},
    )
    client.post(
        f"/api/months/{PERIOD}/transactions",
        headers=registered["headers"],
        json={
            "kind": "expense", "category": "housing", "label": "Rent",
            "amount": 22_000, "txn_date": dt.date.today().isoformat(), "status": "actual",
        },
    )
    first = client.post(f"/api/months/{PERIOD}/reconcile", headers=registered["headers"], json={})
    second = client.post(f"/api/months/{PERIOD}/reconcile", headers=registered["headers"], json={})
    assert first.json()["evaluations_created"] > 0
    assert second.json()["evaluations_created"] == 0  # no duplicate evaluation rows


def test_reconciliation_does_not_invent_an_error_for_unrecorded_categories(client, registered):
    """A forecast with no actual has no error. Reporting 100% would be a false claim."""
    seed_profile_and_goal(registered)
    _open(client, registered["headers"])
    client.post(
        f"/api/months/{PERIOD}/estimate-expenses",
        headers=registered["headers"],
        json={"category_estimates": {"food_groceries": 10_000, "shopping": 5_000}, "persist": True},
    )
    # record an actual for only ONE of the two estimated categories
    client.post(
        f"/api/months/{PERIOD}/transactions",
        headers=registered["headers"],
        json={
            "kind": "expense", "category": "food_groceries", "label": "Groceries",
            "amount": 12_000, "txn_date": dt.date.today().isoformat(), "status": "actual",
        },
    )
    body = client.post(
        f"/api/months/{PERIOD}/reconcile", headers=registered["headers"], json={}
    ).json()

    shopping = next(r for r in body["rows"] if r["category"] == "shopping")
    assert shopping["actual_recorded"] is False
    assert shopping["actual"] is None
    assert shopping["pct_error"] is None
    assert "shopping" in body["unmatched_categories"]
    assert body["unmatched_note"]
    assert body["totals"]["categories_compared"] == 1
    # a seeded loan payment has no actual either, so it must not appear as over/under budget
    assert "loan_payments" not in body["over_budget_categories"]
    assert "loan_payments" not in body["under_budget_categories"]

    groceries = next(r for r in body["rows"] if r["category"] == "food_groceries")
    assert groceries["actual"] == 12_000.0
    assert groceries["pct_error"] == 20.0


def test_reconcile_without_a_forecast_is_rejected(client, registered):
    seed_profile_and_goal(registered)
    _open(client, registered["headers"])
    response = client.post(f"/api/months/{PERIOD}/reconcile", headers=registered["headers"], json={})
    assert response.status_code == 422


def test_budgets_and_persistent_overspend(client, registered):
    seed_profile_and_goal(registered)
    _open(client, registered["headers"])  # the current month must exist for the status call

    created = client.post(
        "/api/budgets",
        headers=registered["headers"],
        json={"category": "food_groceries", "monthly_limit": 10_000, "classification": "essential"},
    )
    assert created.status_code == 201
    duplicate = client.post(
        "/api/budgets",
        headers=registered["headers"],
        json={"category": "food_groceries", "monthly_limit": 9_000},
    )
    assert duplicate.status_code == 409

    # three consecutive months over budget
    for offset in (3, 2, 1):
        month = dt.date.today().replace(day=1) - dt.timedelta(days=1)
        for _ in range(offset - 1):
            month = month.replace(day=1) - dt.timedelta(days=1)
        period = month.strftime("%Y-%m")
        client.post(f"/api/months/{period}/open", headers=registered["headers"])
        client.post(
            f"/api/months/{period}/transactions",
            headers=registered["headers"],
            json={
                "kind": "expense", "category": "food_groceries", "label": "Groceries",
                "amount": 13_000, "txn_date": month.isoformat(), "status": "actual",
            },
        )

    status = client.get(
        f"/api/months/{PERIOD}/budget-status", headers=registered["headers"]
    ).json()
    assert status["budgets"][0]["monthly_limit"] == 10_000.0
    flagged = {f["category"] for f in status["persistent_overspend"]}
    assert "food_groceries" in flagged
    recurring = {r["category"] for r in status["recurring_categories"]}
    assert "food_groceries" in recurring


def test_budget_crud_and_isolation(client, registered, second_user):
    seed_profile_and_goal(registered)
    seed_profile_and_goal(second_user)
    created = client.post(
        "/api/budgets",
        headers=registered["headers"],
        json={"category": "travel", "monthly_limit": 5_000},
    ).json()

    assert client.put(
        f"/api/budgets/{created['id']}", headers=second_user["headers"],
        json={"category": "travel", "monthly_limit": 1},
    ).status_code == 404

    updated = client.put(
        f"/api/budgets/{created['id']}", headers=registered["headers"],
        json={"category": "travel", "monthly_limit": 7_500, "classification": "discretionary"},
    )
    assert updated.json()["monthly_limit"] == 7_500.0
    assert client.delete(
        f"/api/budgets/{created['id']}", headers=registered["headers"]
    ).status_code == 200
