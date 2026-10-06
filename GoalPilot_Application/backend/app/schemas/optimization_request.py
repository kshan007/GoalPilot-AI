from typing import Optional
from pydantic import BaseModel, Field
from .financial_profile import FinancialProfileSchema
from .goal import SingleGoalSchema

class OptimizationRequest(BaseModel):
    user_id: Optional[str] = Field(
        default="USER_CUSTOM",
        description="Optional user identifier (or synthetic benchmark ID like USER_00001)"
    )
    financial_profile: FinancialProfileSchema = Field(
        ...,
        description="The user's core financial profile parameters"
    )
    goal: SingleGoalSchema = Field(
        ...,
        description="The user's single financial goal"
    )

class BenchmarkLookupRequest(BaseModel):
    user_id: str = Field(
        ...,
        description="Synthetic user ID from GoalPilot_AI research dataset (e.g., USER_00001)",
        examples=["USER_00001"]
    )
