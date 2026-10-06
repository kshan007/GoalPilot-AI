"""
Financial Service for profile calculation and benchmark utilities.
"""

from typing import Dict, Any, List, Optional
from ..schemas.financial_profile import (
    FinancialProfileSchema,
    DerivedFinancialSummary,
    FinancialSituationEnum
)
from ..schemas.goal import SingleGoalSchema, GoalDerivedSummary, GoalHorizonTypeEnum
from ..integration.data_loader import data_loader
from ..utils.logger import logger

class FinancialService:
    def __init__(self):
        self.data_loader = data_loader

    def compute_financial_summary(self, profile: FinancialProfileSchema) -> DerivedFinancialSummary:
        annual_inc = profile.monthly_income * 12.0
        annual_exp = profile.monthly_expenditure * 12.0
        surplus = profile.monthly_income - profile.monthly_expenditure - profile.monthly_emi
        sav_ratio = profile.initial_savings / annual_inc if annual_inc > 0 else 0.0
        debt_ratio = profile.monthly_emi / profile.monthly_income if profile.monthly_income > 0 else 0.0

        if surplus < 0 or (sav_ratio < 0.1 and debt_ratio > 0.4):
            situation = FinancialSituationEnum.FINANCIAL_STRESS
        elif surplus < profile.monthly_income * 0.15:
            situation = FinancialSituationEnum.VULNERABLE
        elif sav_ratio > 0.5 and surplus > profile.monthly_income * 0.35:
            situation = FinancialSituationEnum.AFFLUENT
        else:
            situation = FinancialSituationEnum.MODERATE_SAVING

        rec_emergency = profile.monthly_expenditure * 6.0
        cov_months = (profile.initial_savings / profile.monthly_expenditure) if profile.monthly_expenditure > 0 else 0.0

        return DerivedFinancialSummary(
            baseline_monthly_surplus=round(surplus, 2),
            is_surplus_positive=bool(surplus > 0),
            annual_income=round(annual_inc, 2),
            annual_expenditure=round(annual_exp, 2),
            savings_to_income_ratio=round(sav_ratio, 4),
            debt_service_ratio=round(debt_ratio, 4),
            financial_situation=situation,
            recommended_emergency_fund_target=round(rec_emergency, 2),
            emergency_fund_coverage_months=round(cov_months, 1)
        )

    def compute_goal_summary(self, goal: SingleGoalSchema, profile: FinancialProfileSchema) -> GoalDerivedSummary:
        h = goal.goal_horizon_months
        if h <= 24:
            h_type = GoalHorizonTypeEnum.SHORT_TERM
        elif h <= 60:
            h_type = GoalHorizonTypeEnum.MEDIUM_TERM
        else:
            h_type = GoalHorizonTypeEnum.LONG_TERM

        annual_inc = profile.monthly_income * 12.0
        t_to_inc = goal.target_amount / annual_inc if annual_inc > 0 else 0.0
        t_to_sav = (goal.target_amount / profile.initial_savings) if profile.initial_savings > 0 else 0.0
        req_flat = goal.target_amount / h if h > 0 else goal.target_amount

        return GoalDerivedSummary(
            goal_name=goal.goal_name,
            target_amount=round(goal.target_amount, 2),
            goal_horizon_months=h,
            goal_horizon_type=h_type,
            target_to_annual_income_ratio=round(t_to_inc, 4),
            target_to_savings_ratio=round(t_to_sav, 4),
            required_monthly_savings_flat=round(req_flat, 2)
        )

    def get_benchmark_users(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self.data_loader.get_benchmark_user_list(limit=limit)

    def get_benchmark_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        return self.data_loader.get_benchmark_user_record(user_id=user_id)

financial_service = FinancialService()
