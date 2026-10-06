from fastapi import APIRouter, HTTPException, Query, status
from typing import List, Dict, Any, Optional
from ..schemas.financial_profile import FinancialProfileSchema, RiskProfileEnum
from ..schemas.goal import SingleGoalSchema, GoalPriorityEnum
from ..schemas.optimization_request import OptimizationRequest
from ..schemas.optimization_response import OptimizationResponse
from ..services.financial_service import financial_service
from ..services.optimization_service import optimization_service
from ..utils.logger import logger

router = APIRouter(prefix="/api/benchmarks", tags=["Benchmarks"])

@router.get("", summary="Get List of Synthetic Research Benchmarks")
def list_benchmark_users(limit: int = Query(default=25, ge=1, le=100)):
    """Returns sample benchmark users from the 10,000 synthetic population."""
    try:
        users = financial_service.get_benchmark_users(limit=limit)
        return {
            "total_available": 10000,
            "returned_count": len(users),
            "users": users
        }
    except Exception as e:
        logger.error(f"Error fetching benchmark list: {e}")
        return {"total_available": 0, "returned_count": 0, "users": []}

@router.get("/{user_id}", summary="Get Specific Benchmark User Record")
def get_benchmark_user(user_id: str):
    """Retrieves original research parameters and notebook LP results for a user."""
    rec = financial_service.get_benchmark_user(user_id=user_id)
    if not rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Benchmark user '{user_id}' not found in research dataset."
        )
    return rec

@router.post("/run/{user_id}", response_model=OptimizationResponse, summary="Execute Live Optimization on Benchmark User")
def run_benchmark_user_live(user_id: str):
    """
    Loads benchmark profile from research dataset and runs live optimization adapter,
    allowing direct side-by-side validation against notebook results.
    """
    rec = financial_service.get_benchmark_user(user_id=user_id)
    if not rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Benchmark user '{user_id}' not found."
        )

    # Map risk profile
    r_str = str(rec.get("risk_profile", "moderate")).lower()
    if "aggr" in r_str:
        r_enum = RiskProfileEnum.AGGRESSIVE
    elif "cons" in r_str:
        r_enum = RiskProfileEnum.CONSERVATIVE
    else:
        r_enum = RiskProfileEnum.MODERATE

    profile = FinancialProfileSchema(
        monthly_income=float(rec.get("monthly_income", 50000.0)),
        monthly_expenditure=float(rec.get("monthly_expenditure", 30000.0)),
        monthly_emi=float(rec.get("monthly_emi", 0.0)),
        initial_savings=float(rec.get("initial_savings", 50000.0)),
        initial_investment=float(rec.get("initial_investment", 0.0)),
        risk_profile=r_enum
    )

    goal = SingleGoalSchema(
        goal_name=f"Benchmark Goal ({user_id})",
        target_amount=float(rec.get("target_amount", 100000.0)),
        goal_horizon_months=int(rec.get("goal_horizon_months", 36)),
        priority=GoalPriorityEnum.IMPORTANT,
        purpose=f"Empirical benchmark case from Step 5X dataset ({user_id})"
    )

    req = OptimizationRequest(
        user_id=user_id,
        financial_profile=profile,
        goal=goal
    )

    return optimization_service.run_optimization(req)
