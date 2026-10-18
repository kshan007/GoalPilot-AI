import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pandas as pd
import pytest
from src.multi_goal_optimizer import FinancialState, monthly_emi_per_rupee, optimize_multi_goal, prepare_goals
from src.providers import EconomicScenario, InvestmentCandidate, LoanOffer, SavingsProduct

@pytest.fixture
def state():
    return FinancialState(monthly_income=75000,essential_expenses=42000,existing_emi=4000,liquid_savings=350000,emergency_months=6,emi_income_ratio_cap=.35,risk_capacity=.55)
@pytest.fixture
def goals():
    return pd.DataFrame([
        {"goal_id":"G1","goal_name":"A","current_cost":90000,"target_date":"2027-10-10","time_horizon_months":12,"priority":4,"criticality":5,"existing_funding":10000},
        {"goal_id":"G2","goal_name":"B","current_cost":300000,"target_date":"2029-10-10","time_horizon_months":36,"priority":3,"criticality":3,"existing_funding":50000},
        {"goal_id":"G3","goal_name":"C","current_cost":900000,"target_date":"2033-10-10","time_horizon_months":84,"priority":5,"criticality":4,"existing_funding":100000},
    ])
def test_derive_goals(goals):
    d=prepare_goals(goals,annual_inflation=.03)
    assert (d.future_goal_cost >= d.current_cost).all()
    assert (d.funding_gap >= 0).all()
    assert (d.required_monthly_contribution >= 0).all()
def test_multi_goal_feasible_and_limits(goals,state):
    r=optimize_multi_goal(goals,state,investment_return=.05,investment_risk_score=.4,max_loan_per_goal=150000)
    assert r['status']=='optimal'
    a=r['allocations']; s=r['summary']
    assert len(a)==3
    assert (a[['initial_savings_allocated','monthly_savings_contribution','monthly_investment_contribution','loan_principal','shortfall']]>=-1e-6).all().all()
    assert s['monthly_surplus_respected']
    assert s['emi_cap_respected']
    assert s['emergency_fund_preserved']
    assert (a.loan_principal <= 150000+1e-6).all()
def test_high_risk_investment_prohibited(goals,state):
    r=optimize_multi_goal(goals,state,investment_risk_score=.9,max_loan_per_goal=0)
    assert r['status']=='optimal'
    assert abs(r['allocations'].monthly_investment_contribution.sum()) < 1e-6
def test_duplicate_goal_ids_rejected(goals):
    goals.loc[1,'goal_id']='G1'
    with pytest.raises(ValueError): prepare_goals(goals)
def test_negative_amount_rejected(goals):
    goals.loc[0,'current_cost']=-1
    with pytest.raises(ValueError): prepare_goals(goals)
def test_empty_surplus_still_returns_shortfall(goals):
    s=FinancialState(monthly_income=20000,essential_expenses=25000,liquid_savings=0,risk_capacity=.2)
    r=optimize_multi_goal(goals,s,max_loan_per_goal=0)
    assert r['status']=='optimal'
    assert r['allocations'].shortfall.sum()>0


def test_discretionary_expenses_reduce_monthly_surplus(goals):
    s=FinancialState(monthly_income=50000,essential_expenses=20000,discretionary_expenses=7000,existing_emi=3000,liquid_savings=0,risk_capacity=.4)
    r=optimize_multi_goal(goals,s,max_loan_per_goal=0,investment_risk_score=.9)
    assert r["status"] == "optimal"
    assert r["summary"]["monthly_surplus_available"] == pytest.approx(20000)
    assert r["summary"]["monthly_contributions_allocated"] <= 20000 + 1e-6


def test_existing_assets_are_used_only_when_explicitly_usable(goals):
    s=FinancialState(monthly_income=30000,essential_expenses=29000,liquid_savings=0,existing_investments=200000,usable_existing_investments=50000,risk_capacity=.5)
    r=optimize_multi_goal(goals,s,max_loan_per_goal=0,investment_risk_score=.9,existing_asset_return=0)
    assert r["status"] == "optimal"
    assert r["summary"]["existing_assets_allocated"] <= 50000 + 1e-6
    assert r["summary"]["existing_assets_respected"]


def test_usable_existing_assets_cannot_exceed_total():
    s=FinancialState(monthly_income=30000,essential_expenses=10000,existing_investments=100,usable_existing_investments=101)
    with pytest.raises(ValueError):
        s.validate()


def test_goal_already_funded_has_zero_gap():
    goals = pd.DataFrame([{
        "goal_id":"DONE","goal_name":"Already funded","current_cost":1000,
        "target_date":"2027-01-01","time_horizon_months":12,
        "priority":5,"criticality":5,"existing_funding":2000
    }])
    state = FinancialState(monthly_income=10000, essential_expenses=5000, liquid_savings=0)
    result = optimize_multi_goal(goals, state, annual_inflation=0, max_loan_per_goal=0)
    assert result["status"] == "optimal"
    assert result["allocations"].iloc[0]["funding_gap"] == pytest.approx(0)
    assert result["allocations"].iloc[0]["achievement_ratio"] == pytest.approx(1)


def test_invalid_loan_rate_rejected():
    with pytest.raises(ValueError):
        monthly_emi_per_rupee(-.01, 12)


def test_zero_interest_loan_emi():
    assert monthly_emi_per_rupee(0, 10) == pytest.approx(.1)


def test_provider_options_are_selected_and_reported(goals, state):
    investments = [
        InvestmentCandidate("debt","Debt","debt","fixture","offline",.035,.2,6),
        InvestmentCandidate("equity","Equity","equity","fixture","offline",.07,.8,36),
    ]
    loans = [LoanOffer("loan","Synthetic","Personal","fixture","synthetic",.09,24,50000)]
    savings = [SavingsProduct("save","Deposit","deposit","fixture","synthetic",.04,12)]
    scenario = EconomicScenario("test","fixture","offline",.02,.01,.06,.11)
    result = optimize_multi_goal(
        goals, state,
        investment_candidates=investments,
        loan_offers=loans,
        savings_products=savings,
        economic_scenario=scenario,
    )
    assert result["status"] == "optimal"
    selected = result["summary"]["selected_options"]
    assert selected["investment_candidate"]["candidate_id"] == "debt"
    assert selected["loan_offer"]["offer_id"] == "loan"
    assert selected["savings_product"]["product_id"] == "save"
    assert selected["economic_scenario"]["name"] == "test"


def test_illiquid_high_risk_candidate_excluded_for_short_goal(goals, state):
    investments = [
        InvestmentCandidate("long","Long equity","equity","fixture","offline",.2,.4,60),
        InvestmentCandidate("short","Short debt","debt","fixture","offline",.03,.1,6),
    ]
    result = optimize_multi_goal(goals, state, investment_candidates=investments, max_loan_per_goal=0)
    assert result["status"] == "optimal"
    assert result["summary"]["selected_options"]["investment_candidate"]["candidate_id"] == "short"


def test_existing_goal_funding_is_not_double_counted_in_cash_pool():
    from src.multi_goal_optimizer import FinancialState, optimize_multi_goal
    goals = pd.DataFrame([{
        "goal_id":"G1", "goal_name":"Goal", "current_cost":1000,
        "target_date":"2027-01-01", "time_horizon_months":12,
        "priority":3, "criticality":3, "existing_funding":200
    }])
    state = FinancialState(monthly_income=10000, essential_expenses=1000,
                           liquid_savings=10000, emergency_months=1, risk_capacity=0.5)
    result = optimize_multi_goal(goals, state, annual_inflation=0.0)
    assert result["status"] == "optimal"
    # 10,000 savings - 1,000 emergency reserve - 200 already earmarked = 8,800 available.
    assert result["summary"]["available_cash_above_emergency_reserve"] == pytest.approx(8800)
    assert result["summary"]["earmarked_existing_goal_funding_excluded_from_cash_pool"] == pytest.approx(200)

def test_emergency_fund_status_distinguishes_existing_deficit_from_optimizer_use():
    state = FinancialState(monthly_income=10000, essential_expenses=3000,
                           liquid_savings=1000, emergency_months=6, risk_capacity=0.2)
    goals = pd.DataFrame([{
        "goal_id":"G1", "goal_name":"Goal", "current_cost":10000,
        "target_date":"2027-01-01", "time_horizon_months":12,
        "priority":3, "criticality":3, "existing_funding":0
    }])
    result = optimize_multi_goal(goals, state, max_loan_per_goal=0)
    assert result["status"] == "optimal"
    assert result["summary"]["emergency_fund_preserved"] is True
    assert result["summary"]["emergency_fund_was_below_target_at_start"] is True
    assert not result["summary"]["emergency_fund_target_met_after_allocation"]


def test_combined_monthly_commitment_never_exceeds_surplus():
    """New loan EMIs and goal contributions must share one cash-flow budget."""
    state = FinancialState(
        monthly_income=20000,
        essential_expenses=18000,
        discretionary_expenses=0,
        existing_emi=0,
        liquid_savings=0,
        existing_investments=0,
        usable_existing_investments=0,
        emergency_months=6,
        emi_income_ratio_cap=0.35,
        risk_capacity=0.3,
    )
    goals = pd.DataFrame([{
        "goal_id": "STRESS_1",
        "goal_name": "Urgent goal",
        "current_cost": 200000,
        "target_date": "2026-11-10",
        "time_horizon_months": 1,
        "priority": 5,
        "criticality": 5,
        "existing_funding": 0,
    }])

    result = optimize_multi_goal(
        goals,
        state,
        annual_inflation=0,
        savings_return=0,
        investment_return=0,
        investment_risk_score=0,
        loan_annual_rate=0.12,
        loan_tenure_months=60,
        max_loan_per_goal=150000,
    )

    assert result["status"] == "optimal"
    summary = result["summary"]
    contributions = summary["monthly_contributions_allocated"]
    new_emi = summary["new_total_emi"]
    surplus = summary["monthly_surplus_available"]

    assert summary["combined_monthly_cashflow_respected"]
    assert contributions + new_emi <= surplus + 1e-5
    assert summary["emi_cap_respected"]
