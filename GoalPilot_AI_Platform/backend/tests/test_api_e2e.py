"""End-to-end workflow: the demonstration path a review panel would follow."""
from __future__ import annotations

import datetime as dt

from tests.conftest import seed_profile_and_goal

PERIOD = dt.date.today().strftime("%Y-%m")


def test_full_onboarding_to_reconciled_plan(client, registered):
    headers = registered["headers"]

    # 1. health and provenance
    health = client.get("/api/health").json()
    assert health["status"] == "healthy"
    assert health["supported_features"]["multi_goal_optimization"] is True

    # 2. onboarding is incomplete to begin with
    state = client.get("/api/onboarding", headers=headers).json()
    assert state["completed"] is False
    assert state["has_profile"] is False

    # 3. profile, income, assets, liabilities, goals
    seeded = seed_profile_and_goal(registered, goals=3)
    assert len(seeded["goals"]) == 3

    profile = client.get("/api/profile", headers=headers).json()
    assert profile["profile"]["monthly_income"] == 90_000.0

    summary = client.get("/api/profile/summary", headers=headers).json()
    assert summary["monthly_income"] == 90_000.0
    assert summary["existing_emi"] == 12_000.0
    # 90,000 income - 42,000 essential - 6,000 discretionary - 12,000 EMI = 30,000
    assert summary["monthly_surplus"] == 30_000.0
    assert summary["situation_tier"] in (
        "strong", "moderate_saving", "thin_buffer", "thin_surplus", "debt_stressed", "deficit"
    )

    # 4. onboarding completes once the minimum data exists
    done = client.post("/api/onboarding/complete", headers=headers)
    assert done.status_code == 200
    assert client.get("/api/onboarding", headers=headers).json()["completed"] is True

    # 5. per-goal projection before any plan exists
    plan_view = client.get("/api/goals/plan", headers=headers).json()
    assert len(plan_view) == 3
    assert all(p["future_target"] >= p["current_cost"] for p in plan_view)
    assert all(p["planned_monthly_contribution"] is None for p in plan_view)

    # 6. open the current month and estimate expenses
    opened = client.post(f"/api/months/{PERIOD}/open", headers=headers)
    assert opened.status_code == 200
    estimate = client.post(
        f"/api/months/{PERIOD}/estimate-expenses",
        headers=headers,
        json={
            "category_estimates": {
                "food_groceries": 12_000, "utilities": 4_000,
                "transport": 4_000, "shopping": 5_000,
            },
            "persist": True,
        },
    )
    assert estimate.status_code == 200
    assert estimate.json()["history_months_available"] == 0
    assert "Cold-start" in estimate.json()["estimation_method"]
    assert estimate.json()["projected_surplus"] is not None

    # 7. generate the multi-goal plan
    plan = client.post("/api/optimize/plan", headers=headers, json={"algorithm": "lp"})
    assert plan.status_code == 200, plan.text
    body = plan.json()
    assert body["feasible"] is True
    assert len(body["allocations"]) == 3
    assert body["cashflow"]["monthly_surplus"] == 30_000.0
    assert body["diff"]["previous_run_id"] is None  # first plan
    assert body["assumptions"]["annual_inflation"] == 0.03

    # the allocation obeys the monthly surplus
    total_contributions = sum(
        a["monthly_savings_contribution"] + a["monthly_investment_contribution"]
        for a in body["allocations"]
    )
    assert total_contributions <= body["cashflow"]["monthly_surplus"] + 1e-4

    # 8. record actuals and reconcile
    for category, amount in (("food_groceries", 14_000), ("utilities", 3_500), ("shopping", 9_000)):
        created = client.post(
            f"/api/months/{PERIOD}/transactions",
            headers=headers,
            json={
                "kind": "expense", "category": category, "label": category,
                "amount": amount, "txn_date": dt.date.today().isoformat(), "status": "actual",
            },
        )
        assert created.status_code == 201, created.text

    reconcile = client.post(
        f"/api/months/{PERIOD}/reconcile", headers=headers,
        json={"mark_actuals": True, "update_future_forecast": True},
    )
    assert reconcile.status_code == 200, reconcile.text
    body = reconcile.json()
    assert body["forecast_preserved"] is True
    assert "shopping" in body["over_budget_categories"]  # 9000 vs 5000 estimated
    assert body["financial_impact"]["surplus_actual"] is not None

    # 9. re-plan on the corrected actuals: the diff must explain the change
    replan = client.post("/api/optimize/plan", headers=headers, json={"algorithm": "lp"})
    assert replan.status_code == 200
    assert replan.json()["diff"]["previous_run_id"] is not None
    assert replan.json()["diff"]["summary"]

    # 10. scenario stress
    scenario = client.post(
        "/api/scenarios/run", headers=headers,
        json={"preset": "income_down", "parameters": {"income_change_pct": -20}, "algorithm": "lp"},
    )
    assert scenario.status_code == 200, scenario.text
    deltas = scenario.json()["deltas"]
    assert "monthly_surplus" in deltas
    assert deltas["monthly_surplus"]["delta"] < 0

    # 11. dashboard reflects real persisted data
    dashboard = client.get("/api/dashboard", headers=headers).json()
    assert dashboard["goals"]["active_count"] == 3
    assert dashboard["monthly"]["current_period"] == PERIOD
    assert dashboard["monthly"]["current"] is not None
    assert dashboard["monthly"]["trend"]
    assert dashboard["monthly"]["category_breakdown"]
    assert dashboard["optimization"]["last_plan"] is not None
    assert dashboard["forecasts"]["error_trend"]
    assert dashboard["labels_note"]

    # 12. run history is preserved
    runs = client.get("/api/optimize/runs", headers=headers).json()
    assert len(runs["items"]) >= 3  # plan, plan, scenario baseline + stressed
    assert all(r["model_version"] for r in runs["items"])


def test_reconciled_actuals_feed_the_next_plan_and_the_basis_is_disclosed(client, registered):
    """The plan must follow recorded actuals, and must say that it did."""
    headers = registered["headers"]
    seed_profile_and_goal(registered, goals=2)

    first = client.post("/api/optimize/plan", headers=headers, json={"algorithm": "lp"}).json()
    assert first["cashflow"]["expense_basis"] == "profile"
    baseline_surplus = first["cashflow"]["monthly_surplus"]

    # record actuals that differ from the stated profile figures
    client.post(f"/api/months/{PERIOD}/open", headers=headers)
    for category, amount in (
        ("food_groceries", 18_000), ("utilities", 5_000),
        ("transport", 6_000), ("shopping", 9_000),
    ):
        client.post(
            f"/api/months/{PERIOD}/transactions",
            headers=headers,
            json={
                "kind": "expense", "category": category, "label": category,
                "amount": amount, "txn_date": dt.date.today().isoformat(), "status": "actual",
            },
        )

    second = client.post("/api/optimize/plan", headers=headers, json={"algorithm": "lp"}).json()
    assert second["cashflow"]["expense_basis"] == "month_actuals"
    assert second["cashflow"]["expense_categories_used"] == 4
    # 18,000 + 5,000 + 6,000 essential and 9,000 discretionary, EMI unchanged
    assert second["cashflow"]["essential_expenses"] == 29_000.0
    assert second["cashflow"]["discretionary_expenses"] == 9_000.0
    # 90,000 - 29,000 - 9,000 - 12,000 = 40,000
    assert second["cashflow"]["monthly_surplus"] == 40_000.0
    assert second["cashflow"]["monthly_surplus"] != baseline_surplus
    # the change is disclosed as a warning, not hidden
    assert any("recorded actual transactions" in w for w in second["cashflow"]["warnings"])
    # and the plan diff explains what moved
    assert second["diff"]["previous_run_id"] is not None


def test_emi_is_not_double_counted_when_planning_from_month_transactions(client, registered):
    """The seeded loan-payment line and the liability EMI must not both hit the surplus."""
    headers = registered["headers"]
    seed_profile_and_goal(registered, goals=1)
    client.post(f"/api/months/{PERIOD}/open", headers=headers)
    # the open call seeded a loan_payments line from the liability; mark it actual
    txns = client.get(f"/api/months/{PERIOD}/transactions", headers=headers).json()
    loan_lines = [t for t in txns if t["category"] == "loan_payments"]
    assert loan_lines, "the month should have a seeded loan payment line"
    client.put(
        f"/api/months/{PERIOD}/transactions/{loan_lines[0]['id']}",
        headers=headers,
        json={"status": "actual"},
    )
    client.post(
        f"/api/months/{PERIOD}/transactions",
        headers=headers,
        json={
            "kind": "expense", "category": "housing", "label": "Rent",
            "amount": 30_000, "txn_date": dt.date.today().isoformat(), "status": "actual",
        },
    )
    plan = client.post("/api/optimize/plan", headers=headers, json={"algorithm": "lp"}).json()
    cf = plan["cashflow"]
    assert cf["loan_payment_lines_skipped"] >= 1
    # EMI counted once only: 90,000 - 30,000 essential - 0 discretionary - 12,000 EMI = 48,000
    assert cf["essential_expenses"] == 30_000.0
    assert cf["existing_emi"] == 12_000.0
    assert cf["monthly_surplus"] == 48_000.0
    assert any("double-count" in w for w in cf["warnings"])


def test_comparison_endpoint_returns_a_decision_with_reasons(client, registered):
    seed_profile_and_goal(registered, goals=2)
    response = client.post("/api/optimize/compare", headers=registered["headers"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["recommended_algorithm"] in {"lp", "rl", "hybrid", "rule_baseline"}
    assert body["recommendation_reason"]
    assert body["arms"]
    assert body["notes"]
    assert body["decision_rule"]["default"] == "lp"
    # an arm that is not available must not carry fabricated metrics
    for arm in body["arms"]:
        if not arm["available"]:
            assert arm["metrics"] == {}
            assert arm["fallback_reason"]


def test_plan_is_refused_without_a_profile(client, registered):
    response = client.post(
        "/api/optimize/plan", headers=registered["headers"], json={"algorithm": "lp"}
    )
    assert response.status_code == 422
    assert "profile" in response.json()["error"]["message"].lower()


def test_plan_is_refused_without_goals(client, registered):
    headers = registered["headers"]
    client.put(
        "/api/profile",
        headers=headers,
        json={"monthly_income": 90_000, "essential_expenses": 40_000, "discretionary_expenses": 5_000},
    )
    client.post(
        "/api/income-sources", headers=headers,
        json={"source_type": "salary", "amount": 90_000, "frequency": "monthly"},
    )
    response = client.post("/api/optimize/plan", headers=headers, json={"algorithm": "lp"})
    assert response.status_code == 422
    assert "goal" in response.json()["error"]["message"].lower()


def test_unknown_algorithm_and_unknown_assumptions_are_rejected(client, registered):
    seed_profile_and_goal(registered)
    bad_algorithm = client.post(
        "/api/optimize/plan", headers=registered["headers"], json={"algorithm": "magic"}
    )
    assert bad_algorithm.status_code == 422

    bad_assumption = client.post(
        "/api/optimize/plan",
        headers=registered["headers"],
        json={"algorithm": "lp", "assumptions": {"annual_inflation": 0.03, "not_a_field": 1}},
    )
    assert bad_assumption.status_code == 422


def test_error_envelope_is_uniform(client):
    response = client.get("/api/goals/999999")
    assert response.status_code == 401
    body = response.json()
    assert set(body.keys()) == {"error"}
    assert {"code", "message", "details"} <= set(body["error"].keys())


def test_meta_endpoints_expose_assumptions_and_provenance(client):
    assumptions = client.get("/api/meta/assumptions").json()
    assert assumptions["defaults"]["annual_inflation"] == 0.03
    assert assumptions["cashflow_definition"]["monthly_surplus"]
    assert len(assumptions["provenance_rules"]) >= 5

    provenance = client.get("/api/meta/data-provenance").json()
    kinds = {d["kind"] for d in provenance["datasets"]}
    assert "historical" in kinds and "synthetic" in kinds

    education = client.get("/api/meta/education").json()
    assert education["items"]
    assert "No verified" in education["citation_policy"] or "no citation" in education["citation_policy"].lower()
    assert "never feeds numbers" in education["separation_note"]


def test_model_registry_reports_true_status(admin):
    registry = admin["client"].get("/api/models/registry", headers=admin["headers"]).json()
    entries = {e["name"]: e for e in registry["entries"]}
    assert "constrained_lp" in entries
    assert "ppo_recommended_v1" in entries
    assert entries["ppo_recommended_v1"]["metadata"]["research_metrics"][
        "weighted_goal_achievement"
    ] == 0.4842
    assert entries["constrained_lp"]["metadata"]["research_metrics"][
        "weighted_goal_achievement"
    ] == 0.2452


def test_checkpoints_are_listed_from_the_research_tree(admin):
    response = admin["client"].get("/api/models/checkpoints", headers=admin["headers"]).json()
    if response["available"]:
        assert response["count"] >= 1
        assert all(item["path"].endswith(".zip") for item in response["items"])
