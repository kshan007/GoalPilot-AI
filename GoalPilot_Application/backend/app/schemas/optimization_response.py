from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from .financial_profile import FinancialProfileSchema, DerivedFinancialSummary
from .goal import SingleGoalSchema, GoalDerivedSummary

class OptimizationStatusEnum(str, Enum):
    OPTIMAL_SUCCESS = "optimal_success"        # Goal fully funded (shortfall = 0)
    OPTIMAL_SHORTFALL = "optimal_shortfall"    # Max cash allocated, but shortfall > 0
    DEFICIT_INFEASIBLE = "deficit_infeasible"  # Cash flow negative/zero, no allocation possible
    SOLVER_ERROR = "solver_error"              # Numerical/solver exception

class MonthlyAllocationItem(BaseModel):
    month_index: int
    period: str
    inflation_factor: float
    income_dynamic: float
    expenditure_dynamic: float
    monthly_surplus_dynamic: float
    positive_cash_flow: float
    optimized_goal_funding: float
    residual_cash: float
    cumulative_goal_funding: float

class OptimizationResultMetrics(BaseModel):
    solver_method: str = "highs"
    solver_status: str
    target_amount: float
    goal_horizon_months: int
    total_positive_cash_flow: float
    optimized_goal_funding: float
    optimized_shortfall: float
    funding_percentage: float
    is_goal_achieved: bool
    objective_value_shortfall: float
    analytical_optimal_funding: float
    optimality_error: float
    target_accounting_error: float
    mean_monthly_goal_funding: float
    mean_monthly_residual_cash: float

class ModelExplanation(BaseModel):
    title: str
    summary: str
    key_drivers: List[str]
    constraints_active: List[str]
    simulation_role: str
    nism_guidance_notes: List[str]
    future_capabilities_notice: str

class OptimizationResponse(BaseModel):
    status: OptimizationStatusEnum
    message: str
    user_id: str
    is_benchmark_case: bool = False
    financial_summary: DerivedFinancialSummary
    goal_summary: GoalDerivedSummary
    metrics: OptimizationResultMetrics
    monthly_schedule: List[MonthlyAllocationItem]
    explanation: ModelExplanation
    warnings: List[str]
    assumptions: List[str]
