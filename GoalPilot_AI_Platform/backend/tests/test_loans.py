"""Loan arithmetic, affordability rules and the loan API."""
from __future__ import annotations

import pytest

from app.providers import loans
from app.services import loan_analysis as la
from app.services.cashflow import CashFlow


def _cashflow(**kwargs) -> CashFlow:
    base = dict(
        monthly_income=120_000.0,
        essential_expenses=45_000.0,
        discretionary_expenses=10_000.0,
        existing_emi=6_000.0,
        monthly_surplus=59_000.0,
        liquid_savings=300_000.0,
        emergency_months=6.0,
        emergency_fund_target=270_000.0,
        emergency_fund_progress=1.0,
        emi_income_ratio=0.05,
        emi_income_ratio_cap=0.35,
        risk_capacity=0.55,
    )
    base.update(kwargs)
    cf = CashFlow(**base)
    cf.protected_buffer = base.get("protected_buffer", 15_000.0)
    cf.available_goal_budget = base.get("available_goal_budget", 44_000.0)
    cf.buffer_deficit = 0.0
    cf.buffer_sustained = True
    cf.surplus_basis = "actual"
    return cf


# ------------------------------------------------------------------------- arithmetic
def test_emi_matches_the_standard_formula():
    # 100,000 at 12% over 12 months = 8,884.88 (standard amortising loan).
    assert la.emi(100_000, 0.12, 12) == pytest.approx(8884.88, abs=0.01)


def test_emi_handles_zero_rate_and_zero_principal():
    assert la.emi(120_000, 0.0, 12) == pytest.approx(10_000)
    assert la.emi(0, 0.12, 12) == 0.0
    assert la.emi(100_000, 0.12, 0) == 0.0


def test_total_repayment_is_emi_times_tenure():
    payment = la.emi(500_000, 0.11, 48)
    assert la.total_repayment(500_000, 0.11, 48) == pytest.approx(payment * 48)


def test_amortisation_is_internally_consistent():
    rows = la.amortisation(200_000, 0.12, 24)
    assert len(rows) == 24
    assert rows[-1]["balance"] == pytest.approx(0, abs=0.01)
    assert sum(r["principal"] for r in rows) == pytest.approx(200_000, abs=1.0)
    assert sum(r["interest"] for r in rows) > 0
    # interest must fall over time on an amortising loan
    assert rows[0]["interest"] > rows[-1]["interest"]


def test_apr_equals_the_effective_annual_rate_when_there_are_no_fees():
    # With zero fees the APR must equal the *effective* annualised monthly rate, i.e.
    # (1 + 0.11/12)^12 - 1 = 11.5719%, not the 11% nominal rate. The two are different by
    # definition and the platform reports the effective figure as the APR.
    expected = (1 + 0.11 / 12) ** 12 - 1
    assert la.apr(500_000, 0.11, 48, 0.0) == pytest.approx(expected, abs=1e-6)


def test_apr_rises_with_upfront_fees():
    with_fee = la.apr(500_000, 0.11, 48, 10_000)
    assert with_fee is not None
    assert with_fee > 0.11


def test_apr_rejects_impossible_inputs():
    assert la.apr(0, 0.11, 48) is None
    assert la.apr(100_000, 0.11, 48, 200_000) is None


# ---------------------------------------------------------------------- affordability
def test_affordable_loan_passes_every_check():
    result = la.affordability(12_000, _cashflow())
    assert result["verdict"] == "affordable"
    assert result["blocking_checks"] == []


def test_emi_above_goal_budget_is_blocked():
    result = la.affordability(60_000, _cashflow())
    assert result["verdict"] == "not_affordable"
    assert "emi_within_goal_budget" in result["blocking_checks"]
    assert result["goal_budget_after_emi"] < 0


def test_deficit_household_cannot_take_new_debt():
    cf = _cashflow(monthly_surplus=-5_000.0, available_goal_budget=0.0, protected_buffer=0.0)
    result = la.affordability(5_000, cf)
    assert result["verdict"] == "not_affordable"
    assert "no_existing_deficit" in result["blocking_checks"]


def test_thin_emergency_fund_is_a_caution_not_a_blocker():
    cf = _cashflow(emergency_fund_progress=0.2)
    result = la.affordability(10_000, cf)
    assert "emergency_fund_adequate" in result["cautions"]
    assert result["verdict"] == "affordable_with_caution"


def test_emi_ceiling_uses_the_users_own_cap():
    cf = _cashflow(emi_income_ratio_cap=0.05)  # 6,000 cap, already used by the existing EMI
    result = la.affordability(5_000, cf)
    assert "emi_within_income_ceiling" in result["blocking_checks"]


# ---------------------------------------------------------------------- sensitivity
def test_rate_sensitivity_increases_monotonically():
    rows = la.rate_sensitivity(500_000, 0.11, 48)["rows"]
    emis = [row["emi"] for row in rows]
    assert emis == sorted(emis)
    assert rows[0]["rate_bump_bp"] == 0
    assert rows[-1]["rate_bump_bp"] == 300
    assert "not a forecast" in la.rate_sensitivity(500_000, 0.11, 48)["note"]


# ---------------------------------------------------------------------- alternatives
def test_alternatives_quantify_saving_instead_and_extension():
    options = la.alternatives(
        gap=600_000, monthly_capacity=20_000, months_remaining=24,
        annual_rate=0.11, tenure_months=48, total_interest=118_000,
    )
    names = {o["option"] for o in options}
    assert {"save_instead", "extend_deadline", "borrow"} <= names
    save = next(o for o in options if o["option"] == "save_instead")
    assert save["months_needed"] == 30
    assert save["interest_cost_avoided"] == pytest.approx(118_000, rel=1e-6)


def test_alternatives_when_there_is_no_capacity():
    options = la.alternatives(
        gap=100_000, monthly_capacity=0, months_remaining=12,
        annual_rate=0.11, tenure_months=48, total_interest=20_000,
    )
    assert any(o["option"] == "no_capacity" and o["affordable"] is False for o in options)


# ------------------------------------------------------------------------- analysis
def test_analyse_quote_reports_cost_of_credit_and_apr():
    result = la.analyse_quote(
        principal=500_000, annual_rate=0.11, tenure_months=48, cashflow=_cashflow(),
        processing_fee_pct=0.02, processing_fee_flat=1_000, include_schedule=True,
    )
    repayment = result["repayment"]
    assert repayment["monthly_emi"] > 0
    assert repayment["total_interest"] > 0
    assert repayment["total_fees"] == pytest.approx(11_000)
    assert repayment["total_cost_of_credit"] == pytest.approx(
        repayment["total_interest"] + repayment["total_fees"]
    )
    assert repayment["apr_including_fees"] > 0.11
    assert result["proceeds_are_not_income"] is True
    assert len(result["schedule"]) == 48


def test_analyse_quote_never_claims_eligibility():
    result = la.analyse_quote(
        principal=200_000, annual_rate=0.12, tenure_months=24, cashflow=_cashflow()
    )
    assert "eligibility" not in result["repayment"]
    assert "approval" in result["disclosure"].lower()


def test_compare_quotes_ranks_by_total_cost_not_headline_rate():
    quotes = [
        {"label": "Low rate, high fee", "principal": 500_000, "annual_rate": 0.099,
         "tenure_months": 48, "processing_fee_pct": 0.04},
        {"label": "Higher rate, no fee", "principal": 500_000, "annual_rate": 0.108,
         "tenure_months": 48, "processing_fee_pct": 0.0},
    ]
    rows = la.compare_quotes(quotes, _cashflow())
    assert rows[0]["rank_by_total_cost"] == 1
    assert rows[0]["total_cost_of_credit"] <= rows[1]["total_cost_of_credit"]
    assert rows[0]["label"] == "Higher rate, no fee"


def test_discover_builds_indicative_repayments_from_published_rates():
    payload = la.discover(cashflow=_cashflow(), principal=500_000, tenure_months=48)
    assert payload["options"]
    for option in payload["options"]:
        if option.get("published_rate") is None:
            assert option["indicative"] is None
            continue
        assert option["indicative"]["monthly_emi"] > 0
        assert option["indicative"]["total_interest"] > 0
        assert option["affordability"]["verdict"] in {
            "affordable", "affordable_with_caution", "not_affordable"
        }
    assert payload["does_not_originate_loans"] is True
    assert payload["not_advice"] is True


# ---------------------------------------------------------------- rate classification
def test_four_rate_classes_are_distinct_and_labelled():
    from app.providers.base import RATE_CLASSES, RATE_CLASS_LABELS

    assert set(RATE_CLASSES) == {
        "historical_benchmark",
        "published_lender_rate",
        "estimated_scenario",
        "personalised_offer",
    }
    assert set(RATE_CLASS_LABELS) == set(RATE_CLASSES)
    assert all(RATE_CLASS_LABELS.values())


def test_bundled_lender_products_are_published_rates():
    for record in loans.snapshot_records("unit test"):
        assert record.rate_class == "published_lender_rate"
        assert record.is_personalised_offer is False


def test_walr_is_flagged_as_a_benchmark_not_a_product():
    outcome = loans.walr_benchmark()
    if outcome.status != "ok":
        pytest.skip("WALR dataset not available")
    record = outcome.records[0]
    assert record["rate_class"] == "historical_benchmark"
    assert record["is_product_rate"] is False
    assert record["is_offer"] is False


def test_missing_category_yields_a_labelled_scenario_not_a_product():
    payload = la.discover(
        cashflow=_cashflow(), principal=500_000, tenure_months=48, categories=["education"]
    )
    assert payload["options"] == []
    assert payload["scenario_count"] == 1
    scenario = payload["scenarios"][0]
    assert scenario["category"] == "education"
    # The anti-fabrication guarantee: a scenario has NO published rate.
    assert scenario["published_rate"] is None
    assert scenario["rate_class"] == "estimated_scenario"
    assert scenario["configurable"] is True
    assert scenario["data_quality"] == "category_scenario"
    assert scenario["indicative"]["monthly_emi"] > 0
    assert payload["category_coverage"]["scenario_only"] == ["education"]
    assert any("estimated scenarios" in m for m in payload["missing_information"])


def test_scenario_rate_is_configurable_and_changes_the_emi():
    cheap = la.discover(cashflow=_cashflow(), categories=["education"], scenario_rate=0.10)
    dear = la.discover(cashflow=_cashflow(), categories=["education"], scenario_rate=0.16)
    assert cheap["scenarios"][0]["scenario_rate"] == pytest.approx(0.10)
    assert dear["scenarios"][0]["scenario_rate"] == pytest.approx(0.16)
    assert (
        dear["scenarios"][0]["indicative"]["monthly_emi"]
        > cheap["scenarios"][0]["indicative"]["monthly_emi"]
    )
    assert cheap["scenarios"][0]["assumption_source"] == "request_scenario_rate"


def test_no_scenario_when_a_published_product_covers_the_category():
    payload = la.discover(cashflow=_cashflow(), categories=["personal"])
    assert payload["option_count"] >= 1
    assert payload["scenarios"] == []
    assert payload["category_coverage"]["covered_by_published_products"] == ["personal"]


def test_analyse_quote_labels_the_rate_class():
    neutral = la.analyse_quote(
        principal=300_000, annual_rate=0.11, tenure_months=36, cashflow=_cashflow()
    )
    assert neutral["rate_class"] == "estimated_scenario"
    personal = la.analyse_quote(
        principal=300_000,
        annual_rate=0.11,
        tenure_months=36,
        cashflow=_cashflow(),
        offer_is_personal=True,
        offer_source="ICICI Bank",
    )
    assert personal["rate_class"] == "personalised_offer"
    assert personal["offer_source"] == "ICICI Bank"


# ------------------------------------------------------------------------------- API
def test_loan_endpoints_require_authentication(client):
    assert client.get("/api/loans/discover").status_code == 401


def test_loan_discover_endpoint(registered):
    from tests.conftest import seed_profile_and_goal

    seed_profile_and_goal(registered, goals=2)
    response = registered["client"].get(
        "/api/loans/discover?principal=400000&tenure_months=36", headers=registered["headers"]
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["assumed_principal"] == 400_000
    assert payload["assumed_tenure_months"] == 36
    assert payload["benchmarks"], "the RBI benchmark should be reported when available"


def test_loan_discover_endpoint_returns_a_configurable_scenario(registered):
    from tests.conftest import seed_profile_and_goal

    seed_profile_and_goal(registered, goals=1)
    response = registered["client"].get(
        "/api/loans/discover?category=education&scenario_rate=0.14",
        headers=registered["headers"],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["scenario_count"] == 1
    scenario = body["scenarios"][0]
    assert scenario["scenario_rate"] == pytest.approx(0.14)
    assert scenario["published_rate"] is None
    assert scenario["rate_class"] == "estimated_scenario"
    assert set(body["rate_classes"]) == {
        "historical_benchmark",
        "published_lender_rate",
        "estimated_scenario",
        "personalised_offer",
    }


def test_loan_analyse_endpoint(registered):
    from tests.conftest import seed_profile_and_goal

    seed_profile_and_goal(registered, goals=1)
    response = registered["client"].post(
        "/api/loans/analyse",
        headers=registered["headers"],
        json={
            "principal": 300_000, "annual_rate": 0.105, "tenure_months": 36,
            "rate_type": "floating", "processing_fee_pct": 0.01, "include_schedule": True,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["repayment"]["apr_including_fees"] > 0.105
    assert body["rate_sensitivity"]["rows"]
    assert len(body["schedule"]) == 36


def test_loan_compare_endpoint(registered):
    from tests.conftest import seed_profile_and_goal

    seed_profile_and_goal(registered, goals=1)
    response = registered["client"].post(
        "/api/loans/compare",
        headers=registered["headers"],
        json={
            "quotes": [
                {"label": "A", "principal": 200_000, "annual_rate": 0.11, "tenure_months": 24},
                {"label": "B", "principal": 200_000, "annual_rate": 0.12, "tenure_months": 24,
                 "processing_fee_flat": 5000},
            ]
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert [q["rank_by_total_cost"] for q in body["quotes"]] == [1, 2]
    assert body["quotes"][0]["label"] == "A"
