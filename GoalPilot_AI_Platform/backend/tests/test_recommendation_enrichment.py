"""Stored recommendations must still state amount, rate and duration after a schema change."""
from __future__ import annotations

import datetime as dt

from app.services.loan_analysis import emi as emi_for
from app.services.recommendations import enrich_terms


def _legacy_payload() -> dict:
    return {
        "assumptions": {"loan_annual_rate": 0.12, "loan_tenure_months": 12, "investment_return": 0.05},
        "recommended_plan": {
            "new_loan_principal_total": 75_178.16,
            "new_loan_emi_total": 1_672.30,
            "monthly_investment_total": 2_000.0,
        },
        "goal_recommendations": [
            {"target_date": (dt.date.today() + dt.timedelta(days=365)).isoformat()}
        ],
        "loan_options": [
            # EMI consistent with 5,00,000 x 48 months at 9.99%: basis can be proven.
            {
                "lender": "ICICI Bank",
                "published_rate": 0.0999,
                "indicative_emi": emi_for(500_000, 0.0999, 48),
                "total_interest": 108_587.0,
            },
            # EMI that matches no such basis: leave it blank rather than guess.
            {
                "lender": "Mystery Bank",
                "published_rate": 0.11,
                "indicative_emi": 9_999.0,
                "total_interest": 1.0,
            },
        ],
    }


def test_enrichment_rebuilds_plan_loan_terms():
    enriched = enrich_terms(_legacy_payload())
    terms = enriched["loan_terms"]
    assert terms["principal"] == 75_178.16
    assert terms["annual_rate"] == 0.12
    # The stored assumptions say 12 months, but the stored EMI can only come from 60.
    assert terms["tenure_months"] == 60
    assert terms["monthly_emi"] == 1_672.30
    assert terms["total_interest"] > 20_000
    assert "no loan is arranged" in terms["basis"]


def test_enrichment_rebuilds_investment_terms():
    terms = enrich_terms(_legacy_payload())["investment_terms"]
    assert terms["monthly_amount"] == 2_000.0
    assert terms["horizon_months"] >= 12
    assert terms["assumed_annual_return"] == 0.05
    assert terms["projected_value"] > terms["monthly_amount"] * terms["horizon_months"] * 0.9


def test_enrichment_only_asserts_a_loan_basis_it_can_prove():
    options = enrich_terms(_legacy_payload())["loan_options"]
    proven, unproven = options
    assert proven["principal"] == 500_000.0
    assert proven["tenure_months"] == 48
    assert unproven.get("principal") is None
    assert unproven.get("tenure_months") is None


def test_enrichment_leaves_modern_payloads_untouched():
    modern = {
        "loan_terms": {"principal": 1.0, "tenure_months": 12},
        "investment_terms": {"monthly_amount": 1.0, "horizon_months": 1},
        "loan_options": [{"lender": "X", "principal": 10.0, "tenure_months": 3}],
    }
    assert enrich_terms(modern) == modern


