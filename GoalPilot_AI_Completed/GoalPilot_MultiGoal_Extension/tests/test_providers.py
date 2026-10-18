import json
from pathlib import Path

import pytest

from src.providers import (
    EconomicScenario,
    InvestmentCandidate,
    LoanOffer,
    SavingsProduct,
    select_investment_candidate,
    select_loan_offer,
    select_savings_product,
)


def test_offline_fixture_schema_loads():
    path = Path(__file__).resolve().parents[1] / "data" / "offline_funding_options.json"
    data = json.loads(path.read_text())
    investments = [InvestmentCandidate.from_mapping(x) for x in data["investment_candidates"]]
    loans = [LoanOffer.from_mapping(x) for x in data["loan_offers"]]
    savings = [SavingsProduct.from_mapping(x) for x in data["savings_products"]]
    scenarios = [EconomicScenario.from_mapping(x) for x in data["economic_scenarios"]]
    for group in [investments, loans, savings, scenarios]:
        for item in group:
            item.validate()
    assert {x.assumption_label for x in loans}
    assert all("fixture" in x.provenance or "synthetic" in x.provenance for x in loans)


def test_select_investment_respects_risk_and_horizon():
    candidates = [
        {"candidate_id":"too_long","name":"Long","asset_class":"equity","source":"fixture","provenance":"offline","expected_annual_return":.20,"risk_score":.4,"min_horizon_months":60},
        {"candidate_id":"too_risky","name":"Risky","asset_class":"equity","source":"fixture","provenance":"offline","expected_annual_return":.30,"risk_score":.9,"min_horizon_months":12},
        {"candidate_id":"ok","name":"OK","asset_class":"debt","source":"fixture","provenance":"offline","expected_annual_return":.04,"risk_score":.2,"min_horizon_months":12},
    ]
    selected = select_investment_candidate(candidates, risk_capacity=.5, min_horizon_months=24)
    assert selected.candidate_id == "ok"


def test_select_loan_prefers_lower_total_cost():
    offers = [
        LoanOffer("a","A","loan","fixture","synthetic",.12,60,100000),
        LoanOffer("b","B","loan","fixture","synthetic",.10,24,50000),
    ]
    assert select_loan_offer(offers).offer_id == "b"


def test_select_savings_prefers_return_then_lock_in():
    products = [
        SavingsProduct("cash","Cash","cash","fixture","offline",0,0),
        SavingsProduct("rd","RD","deposit","fixture","synthetic",.04,12),
    ]
    assert select_savings_product(products).product_id == "rd"


def test_malformed_provider_record_fails_fast():
    with pytest.raises(KeyError):
        InvestmentCandidate.from_mapping({"candidate_id":"bad"})
