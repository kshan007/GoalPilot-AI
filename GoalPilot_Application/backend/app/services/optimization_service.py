"""
Optimization Service orchestration layer.
"""

from typing import Optional
from ..schemas.optimization_request import OptimizationRequest
from ..schemas.optimization_response import OptimizationResponse
from ..integration.optimization_adapter import optimization_adapter
from ..utils.logger import logger

class OptimizationService:
    def __init__(self):
        self.optimizer = optimization_adapter

    def run_optimization(self, request: OptimizationRequest) -> OptimizationResponse:
        logger.info(
            f"Processing optimization request for user={request.user_id}, "
            f"target=₹{request.goal.target_amount:,.2f}, horizon={request.goal.goal_horizon_months}m"
        )
        return self.optimizer.optimize(
            profile=request.financial_profile,
            goal=request.goal,
            user_id=request.user_id
        )

optimization_service = OptimizationService()
