from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, field_validator

class RiskProfileEnum(str, Enum):
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"

class FinancialSituationEnum(str, Enum):
    FINANCIAL_STRESS = "financial_stress"
    VULNERABLE = "vulnerable"
    MODERATE_SAVING = "moderate_saving"
    AFFLUENT = "affluent"

class FinancialProfileSchema(BaseModel):
    monthly_income: float = Field(
        ...,
        gt=0,
        description="Gross monthly household income in INR (₹)",
        examples=[75000.0]
    )
    monthly_expenditure: float = Field(
        ...,
        ge=0,
        description="Total essential and living expenditures per month in INR (₹)",
        examples=[40000.0]
    )
    monthly_emi: float = Field(
        default=0.0,
        ge=0,
        description="Existing fixed monthly loan installments (EMI) in INR (₹)",
        examples=[0.0]
    )
    initial_savings: float = Field(
        default=0.0,
        ge=0,
        description="Current liquid bank savings and emergency reserves in INR (₹)",
        examples=[150000.0]
    )
    initial_investment: float = Field(
        default=0.0,
        ge=0,
        description="Existing market investments (Mutual Funds, Equities, FD) in INR (₹)",
        examples=[50000.0]
    )
    risk_profile: RiskProfileEnum = Field(
        default=RiskProfileEnum.MODERATE,
        description="Investor risk tolerance profile"
    )

    @field_validator("monthly_income")
    @classmethod
    def validate_income(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Monthly income must be strictly greater than zero.")
        return float(v)

class DerivedFinancialSummary(BaseModel):
    baseline_monthly_surplus: float
    is_surplus_positive: bool
    annual_income: float
    annual_expenditure: float
    savings_to_income_ratio: float
    debt_service_ratio: float
    financial_situation: FinancialSituationEnum
    recommended_emergency_fund_target: float
    emergency_fund_coverage_months: float
