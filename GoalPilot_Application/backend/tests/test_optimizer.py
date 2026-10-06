"""
Comprehensive unit tests for the GoalPilot Single-Goal Optimization Engine.
Tests all 10 required operational and edge scenarios.
"""

import pytest
import numpy as np
from app.schemas.financial_profile import FinancialProfileSchema, RiskProfileEnum
from app.schemas.goal import SingleGoalSchema, GoalPriorityEnum
from app.integration.optimization_adapter import optimization_adapter
from app.schemas.optimization_response import OptimizationStatusEnum

def test_case_1_normal_profile():
    """Test 1: Normal financial profile + realistic single goal."""
    profile = FinancialProfileSchema(
        monthly_income=75000.0,
        monthly_expenditure=40000.0,
        monthly_emi=0.0,
        initial_savings=150000.0,
        initial_investment=50000.0,
        risk_profile=RiskProfileEnum.MODERATE
    )
    goal = SingleGoalSchema(
        goal_name="Emergency Reserve & Vacation",
        target_amount=300000.0,
        goal_horizon_months=12,
        priority=GoalPriorityEnum.IMPORTANT
    )
    res = optimization_adapter.optimize(profile, goal)
    assert res.status == OptimizationStatusEnum.OPTIMAL_SUCCESS
    assert res.metrics.is_goal_achieved is True
    assert res.metrics.optimized_goal_funding == pytest.approx(300000.0, rel=1e-4)
    assert res.metrics.optimized_shortfall == pytest.approx(0.0, abs=1e-4)
    assert res.metrics.optimality_error < 1e-5

def test_case_2_high_income():
    """Test 2: High income profile."""
    profile = FinancialProfileSchema(
        monthly_income=250000.0,
        monthly_expenditure=60000.0,
        monthly_emi=25000.0,
        initial_savings=500000.0,
        risk_profile=RiskProfileEnum.AGGRESSIVE
    )
    goal = SingleGoalSchema(
        goal_name="Luxury Automobile",
        target_amount=1500000.0,
        goal_horizon_months=18,
        priority=GoalPriorityEnum.DISCRETIONARY
    )
    res = optimization_adapter.optimize(profile, goal)
    assert res.status == OptimizationStatusEnum.OPTIMAL_SUCCESS
    assert res.metrics.is_goal_achieved is True
    assert res.metrics.optimized_goal_funding == 1500000.0

def test_case_3_low_surplus():
    """Test 3: Low surplus profile."""
    profile = FinancialProfileSchema(
        monthly_income=45000.0,
        monthly_expenditure=41000.0,
        monthly_emi=0.0,
        initial_savings=10000.0,
        risk_profile=RiskProfileEnum.CONSERVATIVE
    )
    goal = SingleGoalSchema(
        goal_name="Laptop Purchase",
        target_amount=40000.0,
        goal_horizon_months=12
    )
    res = optimization_adapter.optimize(profile, goal)
    # Available positive surplus is around ~4k/month, total ~48k over 12m -> should achieve 40k
    assert res.metrics.optimized_goal_funding >= 40000.0
    assert res.status == OptimizationStatusEnum.OPTIMAL_SUCCESS

def test_case_4_large_goal_shortfall():
    """Test 4: Very large goal causing optimization shortfall."""
    profile = FinancialProfileSchema(
        monthly_income=60000.0,
        monthly_expenditure=35000.0,
        monthly_emi=5000.0,
        risk_profile=RiskProfileEnum.MODERATE
    )
    goal = SingleGoalSchema(
        goal_name="House Downpayment",
        target_amount=2500000.0,
        goal_horizon_months=24
    )
    res = optimization_adapter.optimize(profile, goal)
    assert res.status == OptimizationStatusEnum.OPTIMAL_SHORTFALL
    assert res.metrics.is_goal_achieved is False
    assert res.metrics.optimized_shortfall > 0
    assert res.metrics.optimized_goal_funding == pytest.approx(res.metrics.total_positive_cash_flow, rel=1e-4)

def test_case_5_short_horizon():
    """Test 5: Short goal horizon (6 months)."""
    profile = FinancialProfileSchema(
        monthly_income=80000.0,
        monthly_expenditure=40000.0
    )
    goal = SingleGoalSchema(
        goal_name="Skill Certification",
        target_amount=100000.0,
        goal_horizon_months=6
    )
    res = optimization_adapter.optimize(profile, goal)
    assert len(res.monthly_schedule) == 6
    assert res.metrics.goal_horizon_months == 6
    assert res.metrics.is_goal_achieved is True

def test_case_6_long_horizon():
    """Test 6: Long goal horizon (60 months)."""
    profile = FinancialProfileSchema(
        monthly_income=100000.0,
        monthly_expenditure=50000.0
    )
    goal = SingleGoalSchema(
        goal_name="Higher Education Fund",
        target_amount=2000000.0,
        goal_horizon_months=60
    )
    res = optimization_adapter.optimize(profile, goal)
    assert len(res.monthly_schedule) == 60
    assert res.metrics.goal_horizon_months == 60
    assert res.metrics.is_goal_achieved is True

def test_case_7_existing_savings():
    """Test 7: Profile with substantial existing savings."""
    profile = FinancialProfileSchema(
        monthly_income=70000.0,
        monthly_expenditure=35000.0,
        initial_savings=400000.0
    )
    goal = SingleGoalSchema(
        goal_name="Vehicle Purchase",
        target_amount=300000.0,
        goal_horizon_months=12
    )
    res = optimization_adapter.optimize(profile, goal)
    assert res.financial_summary.emergency_fund_coverage_months > 6.0
    assert res.status == OptimizationStatusEnum.OPTIMAL_SUCCESS

def test_case_8_existing_loan_emi():
    """Test 8: Profile with high existing loan EMI."""
    profile = FinancialProfileSchema(
        monthly_income=80000.0,
        monthly_expenditure=35000.0,
        monthly_emi=30000.0
    )
    goal = SingleGoalSchema(
        goal_name="Renovation",
        target_amount=250000.0,
        goal_horizon_months=12
    )
    res = optimization_adapter.optimize(profile, goal)
    # Surplus is only ~15k/mo, over 12 months = 180k < 250k -> shortfall
    assert res.status == OptimizationStatusEnum.OPTIMAL_SHORTFALL
    assert len(res.warnings) > 0

def test_case_9_invalid_goal_validation():
    """Test 9: Invalid goal inputs trigger validation errors."""
    with pytest.raises(Exception):
        SingleGoalSchema(
            goal_name="Invalid Goal",
            target_amount=-5000.0,
            goal_horizon_months=12
        )

    with pytest.raises(Exception):
        FinancialProfileSchema(
            monthly_income=0.0,
            monthly_expenditure=20000.0
        )

def test_case_10_infeasible_deficit():
    """Test 10: Infeasible optimization / structural deficit."""
    profile = FinancialProfileSchema(
        monthly_income=40000.0,
        monthly_expenditure=35000.0,
        monthly_emi=15000.0  # Expenses + EMI = 50k > 40k income
    )
    goal = SingleGoalSchema(
        goal_name="Vacation",
        target_amount=50000.0,
        goal_horizon_months=12
    )
    res = optimization_adapter.optimize(profile, goal)
    assert res.status == OptimizationStatusEnum.DEFICIT_INFEASIBLE
    assert res.metrics.optimized_goal_funding == 0.0
    assert res.metrics.optimized_shortfall == 50000.0
    assert res.metrics.total_positive_cash_flow == 0.0
