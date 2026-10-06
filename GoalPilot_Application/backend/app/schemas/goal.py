from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, field_validator

class GoalPriorityEnum(str, Enum):
    ESSENTIAL = "essential"
    IMPORTANT = "important"
    DISCRETIONARY = "discretionary"

class GoalHorizonTypeEnum(str, Enum):
    SHORT_TERM = "short_term"     # <= 24 months
    MEDIUM_TERM = "medium_term"   # 25 - 60 months
    LONG_TERM = "long_term"       # > 60 months

class SingleGoalSchema(BaseModel):
    goal_name: str = Field(
        default="Primary Financial Goal",
        min_length=1,
        max_length=100,
        description="Descriptive name of the single financial target",
        examples=["Buy a Car"]
    )
    target_amount: float = Field(
        ...,
        gt=0,
        description="Target monetary funding required in INR (₹)",
        examples=[600000.0]
    )
    goal_horizon_months: int = Field(
        ...,
        ge=1,
        le=144,
        description="Goal horizon in months (1 to 144 months)",
        examples=[36]
    )
    target_date: Optional[str] = Field(
        default=None,
        description="Target date string (YYYY-MM-DD), optional if horizon is provided"
    )
    priority: GoalPriorityEnum = Field(
        default=GoalPriorityEnum.IMPORTANT,
        description="Priority tier of this goal"
    )
    purpose: Optional[str] = Field(
        default="",
        description="Optional qualitative purpose or notes"
    )

    @field_validator("target_amount")
    @classmethod
    def validate_target(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Target amount must be strictly greater than zero.")
        return float(v)

    @field_validator("goal_horizon_months")
    @classmethod
    def validate_horizon(cls, v: int) -> int:
        if v < 1 or v > 144:
            raise ValueError("Goal horizon must be between 1 and 144 months.")
        return int(v)

class GoalDerivedSummary(BaseModel):
    goal_name: str
    target_amount: float
    goal_horizon_months: int
    goal_horizon_type: GoalHorizonTypeEnum
    target_to_annual_income_ratio: float
    target_to_savings_ratio: float
    required_monthly_savings_flat: float
