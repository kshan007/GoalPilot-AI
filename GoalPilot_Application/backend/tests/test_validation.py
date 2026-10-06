"""
Validation test script:
Directly compares the live GoalPilot Application optimization output against the
ground truth research results stored in GoalPilot_AI_final_LP_optimization_dataset.csv.
"""

import pytest
import pandas as pd
import numpy as np
from app.integration.data_loader import data_loader
from app.integration.optimization_adapter import optimization_adapter
from app.schemas.financial_profile import FinancialProfileSchema, RiskProfileEnum
from app.schemas.goal import SingleGoalSchema

def test_validation_against_notebook_dataset():
    """
    Validates that the Application's LP optimizer reproduces exact results
    from the GoalPilot_AI Step 5T / Step 5X dataset for representative users.
    """
    master_df = data_loader.get_benchmark_master_lp_dataset()
    if master_df is None or master_df.empty:
        pytest.skip("Benchmark master dataset not available.")

    # Select representative users across different situations
    test_uids = ["USER_00001", "USER_00002", "USER_00003", "USER_00004", "USER_00005"]

    for uid in test_uids:
        user_rows = master_df[master_df["user_id"] == uid]
        if len(user_rows) == 0:
            continue
        row = user_rows.iloc[0]

        r_str = str(row.get("risk_profile", "moderate")).lower()
        r_enum = RiskProfileEnum.AGGRESSIVE if "aggr" in r_str else (RiskProfileEnum.CONSERVATIVE if "cons" in r_str else RiskProfileEnum.MODERATE)

        profile = FinancialProfileSchema(
            monthly_income=float(row["monthly_income"]),
            monthly_expenditure=float(row["monthly_expenditure"]),
            monthly_emi=float(row["monthly_emi"]),
            initial_savings=float(row["initial_savings"]),
            initial_investment=float(row["initial_investment"]),
            risk_profile=r_enum
        )

        goal = SingleGoalSchema(
            goal_name=f"Benchmark {uid}",
            target_amount=float(row["target_amount"]),
            goal_horizon_months=int(row["goal_horizon_months"])
        )

        res = optimization_adapter.optimize(profile, goal, user_id=uid)

        expected_funding = float(row["optimized_goal_funding"])
        expected_shortfall = float(row["optimized_shortfall"])
        expected_success = bool(row["optimized_success"])

        # Check numerical agreement
        assert res.metrics.optimized_goal_funding == pytest.approx(expected_funding, abs=1e-2), (
            f"Funding mismatch for {uid}: Got {res.metrics.optimized_goal_funding}, Expected {expected_funding}"
        )
        assert res.metrics.optimized_shortfall == pytest.approx(expected_shortfall, abs=1e-2), (
            f"Shortfall mismatch for {uid}: Got {res.metrics.optimized_shortfall}, Expected {expected_shortfall}"
        )
        assert res.metrics.is_goal_achieved == expected_success, (
            f"Success mismatch for {uid}: Got {res.metrics.is_goal_achieved}, Expected {expected_success}"
        )
