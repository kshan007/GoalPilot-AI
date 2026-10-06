from fastapi import APIRouter, HTTPException, status
from ..schemas.optimization_request import OptimizationRequest
from ..schemas.optimization_response import OptimizationResponse
from ..schemas.financial_profile import FinancialProfileSchema, DerivedFinancialSummary
from ..services.optimization_service import optimization_service
from ..services.financial_service import financial_service
from ..utils.logger import logger

router = APIRouter(prefix="/api", tags=["Optimization"])

@router.post(
    "/optimize",
    response_model=OptimizationResponse,
    summary="Run GoalPilot Single-Goal Optimization",
    description="Executes GoalPilot AI's Linear Program optimization to determine the optimal monthly funding plan for a single financial goal."
)
def run_single_goal_optimization(request: OptimizationRequest):
    try:
        response = optimization_service.run_optimization(request)
        return response
    except ValueError as ve:
        logger.warning(f"Validation error in optimization request: {ve}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(ve)
        )
    except Exception as e:
        logger.error(f"Unexpected error in optimization service: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GoalPilot optimization engine encountered an unexpected error. Please verify input parameters."
        )

@router.post(
    "/derive-profile",
    response_model=DerivedFinancialSummary,
    summary="Calculate Derived Financial Metrics",
    description="Computes baseline surplus, financial situation tier, and emergency fund recommendations without running full optimization."
)
def derive_financial_profile(profile: FinancialProfileSchema):
    try:
        return financial_service.compute_financial_summary(profile)
    except Exception as e:
        logger.error(f"Error computing derived profile: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
