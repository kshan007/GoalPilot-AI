import pandas as pd
import pytest
from src.simulation_adapter import financial_state_from_simulation_row, legacy_goal_to_goal_row


def test_maps_simulation_profile_without_treating_portfolio_as_cash():
    row = {
        "user_id": "USER_1", "final_monthly_income": 50000,
        "final_monthly_expenditure": 30000, "final_monthly_emi": 2000,
        "final_savings_balance": 100000, "final_portfolio_value": 45000,
        "risk_profile": "moderate"
    }
    user_id, state = financial_state_from_simulation_row(row)
    assert user_id == "USER_1"
    assert state.monthly_income == 50000
    assert state.liquid_savings == 100000
    assert state.existing_investments == 45000
    assert state.risk_capacity == 0.5


def test_unknown_risk_profile_requires_override():
    row = {"user_id":"U", "final_monthly_income":50000,
           "final_monthly_expenditure":30000, "final_monthly_emi":0,
           "final_savings_balance":100000, "risk_profile":"unknown"}
    with pytest.raises(ValueError, match="Unknown risk_profile"):
        financial_state_from_simulation_row(row)


def test_legacy_goal_mapping_is_explicit_and_bounded():
    result = legacy_goal_to_goal_row({"user_id":"U1", "target_amount":100000,
                                      "goal_horizon_months":24,
                                      "goal_horizon_funding_actual":120000},
                                     target_date="2028-01-01")
    assert result["existing_funding"] == 0  # historical funding must not be double-counted
    assert result["time_horizon_months"] == 24
    assert result["target_date"] == "2028-01-01"


def test_rejects_missing_profile_columns():
    with pytest.raises(ValueError, match="missing required columns"):
        financial_state_from_simulation_row({"user_id":"U"})
