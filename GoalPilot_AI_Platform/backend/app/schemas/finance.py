"""Financial-profile, goal and monthly-workflow schemas."""
from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from app.schemas.common import ApiModel

Frequency = Literal["monthly", "annual", "quarterly", "weekly", "one_time"]
AssetType = Literal["liquid_savings", "emergency_savings", "investment", "fixed_deposit", "other"]
LiabilityType = Literal[
    "home_loan", "vehicle_loan", "personal_loan", "education_loan", "credit_card", "other"
]
GoalType = Literal[
    "education", "higher_studies", "vehicle", "home", "wedding", "retirement",
    "travel", "emergency", "custom",
]
GoalStatus = Literal["active", "paused", "completed", "archived"]
TxnKind = Literal["income", "expense"]
TxnStatus = Literal["estimated", "actual"]
TxnClass = Literal["essential", "discretionary", "income"]
RiskLevel = Literal["low", "moderate", "high"]
LiquidityLevel = Literal["low", "medium", "high"]

PERIOD_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"


# --------------------------------------------------------------------------------------
# preferences
# --------------------------------------------------------------------------------------
class PreferencesIn(ApiModel):
    currency: str = Field(default="INR", max_length=8)
    locale: str = Field(default="en-IN", max_length=16)
    risk_tolerance: RiskLevel = "moderate"
    loss_ability: RiskLevel = "moderate"
    liquidity_requirement: LiquidityLevel = "medium"
    assumptions: dict[str, float] = Field(default_factory=dict)


class PreferencesOut(ApiModel):
    currency: str
    locale: str
    risk_tolerance: str
    loss_ability: str
    liquidity_requirement: str
    assumptions: dict[str, Any] = Field(default_factory=dict)
    onboarding_step: int
    onboarding_completed: bool


# --------------------------------------------------------------------------------------
# financial profile
# --------------------------------------------------------------------------------------
class ProfileIn(ApiModel):
    monthly_income: float = Field(ge=0)
    essential_expenses: float = Field(ge=0)
    discretionary_expenses: float = Field(ge=0)
    monthly_savings_target: float = Field(default=0, ge=0)
    savings_target_is_mandatory: bool = False
    preferred_cash_buffer: float = Field(default=0, ge=0)
    willing_to_adjust_discretionary: bool = True
    emergency_months: float = Field(default=6, ge=0, le=36)
    emi_income_ratio_cap: float = Field(default=0.35, gt=0, le=1)
    risk_capacity: float = Field(default=0.5, ge=0, le=1)
    inflation_assumption: float = Field(default=0.03, gt=-1, lt=1)
    investment_return_assumption: float = Field(default=0.05, gt=-1, lt=1)
    savings_return_assumption: float = Field(default=0.0, gt=-1, lt=1)
    loan_interest_assumption: float = Field(default=0.12, gt=-1, lt=1)

    # NOTE: no cross-field "income must be positive when expenses are recorded" rule here.
    # ``monthly_income`` on the profile is only a convenience aggregate — the income sources are
    # the source of truth for the planner (see ``cashflow.build_cashflow``), and they are
    # recorded in a *different* onboarding step. Rejecting the save for a value the planner
    # never reads made the savings-preferences step unsavable for every new user. The presence
    # of income is enforced where it actually matters: ``load_cashflow``/``build_cashflow``
    # refuse to produce a summary or plan with zero income.


class ProfileOut(ApiModel):
    id: int
    monthly_income: float
    essential_expenses: float
    discretionary_expenses: float
    monthly_savings_target: float
    savings_target_is_mandatory: bool
    preferred_cash_buffer: float
    willing_to_adjust_discretionary: bool
    emergency_months: float
    emi_income_ratio_cap: float
    risk_capacity: float
    inflation_assumption: float
    investment_return_assumption: float
    savings_return_assumption: float
    loan_interest_assumption: float


class CashFlowOut(ApiModel):
    monthly_income: float
    essential_expenses: float
    discretionary_expenses: float
    existing_emi: float
    monthly_surplus: float
    liquid_savings: float
    emergency_savings: float = 0.0
    total_assets: float
    usable_existing_investments: float
    non_liquid_assets: float
    outstanding_debt: float
    emergency_months: float
    emergency_fund_target: float
    emergency_fund_gap: float
    emergency_fund_progress: float
    emi_income_ratio: float
    emi_income_ratio_cap: float
    risk_capacity: float
    liquidity_requirement: str = "medium"
    loss_ability: str = "moderate"
    savings_target: float
    savings_target_is_mandatory: bool = False
    savings_target_attainment: float
    preferred_cash_buffer: float = 0.0
    protected_buffer: float = 0.0
    buffer_deficit: float = 0.0
    buffer_sustained: bool = True
    available_goal_budget: float = 0.0
    surplus_basis: str = "projected"
    earmarked_goal_funding: float
    available_cash_for_goals: float
    expense_basis: str = "profile"
    expense_categories_used: int = 0
    loan_payment_lines_skipped: int = 0
    is_deficit: bool
    situation_tier: str
    warnings: list[str] = Field(default_factory=list)


class OnboardingState(ApiModel):
    step: int
    completed: bool
    income_count: int
    asset_count: int
    liability_count: int
    goal_count: int
    has_profile: bool
    next_step_hint: str


class OnboardingUpdate(ApiModel):
    step: int = Field(ge=0, le=20)


# --------------------------------------------------------------------------------------
# income / assets / liabilities
# --------------------------------------------------------------------------------------
class IncomeSourceIn(ApiModel):
    source_type: Literal["salary", "freelance", "business", "rental", "other"]
    label: str = Field(default="", max_length=120)
    amount: float = Field(gt=0)
    frequency: Frequency = "monthly"
    stability: Literal["stable", "variable", "uncertain"] = "stable"
    is_recurring: bool = True
    expected_day: int | None = Field(default=None, ge=1, le=31)
    is_active: bool = True


class IncomeSourceOut(IncomeSourceIn):
    id: int
    monthly_equivalent: float
    annual_equivalent: float


class AssetIn(ApiModel):
    asset_type: AssetType
    label: str = Field(default="", max_length=120)
    current_value: float = Field(ge=0)
    is_liquid: bool = True
    usable_for_goals: bool = True
    annual_return: float = Field(default=0.0, gt=-1, lt=1)
    risk_score: float = Field(default=0.2, ge=0, le=1)
    earmarked_goal_id: int | None = None


class AssetOut(AssetIn):
    id: int


class LiabilityIn(ApiModel):
    liability_type: LiabilityType
    label: str = Field(default="", max_length=120)
    outstanding_principal: float = Field(ge=0)
    annual_interest_rate: float = Field(default=0.0, ge=0, lt=1)
    emi_amount: float = Field(default=0, ge=0)
    remaining_tenure_months: int = Field(default=0, ge=0, le=600)

    @model_validator(mode="after")
    def _emi_present(self) -> "LiabilityIn":
        if self.outstanding_principal > 0 and self.emi_amount == 0 and self.remaining_tenure_months > 0:
            raise ValueError(
                "An EMI amount is required for an outstanding balance with a remaining "
                "tenure. The EMI is the cash-flow obligation; principal alone is not used in "
                "the monthly surplus."
            )
        return self


class LiabilityOut(LiabilityIn):
    id: int
    total_interest_if_held_to_tenure: float
    total_repayment_if_held_to_tenure: float


# --------------------------------------------------------------------------------------
# goals
# --------------------------------------------------------------------------------------
class GoalIn(ApiModel):
    name: str = Field(min_length=1, max_length=160)
    purpose: str = Field(default="", max_length=400)
    goal_type: GoalType = "custom"
    current_cost: float = Field(gt=0)
    target_date: dt.date
    current_funded_amount: float = Field(default=0, ge=0)
    priority: int = Field(default=3, ge=1, le=5)
    criticality: int = Field(default=3, ge=1, le=5)
    date_flexible: bool = False
    amount_flexible: bool = False
    liquidity_requirement: LiquidityLevel = "medium"
    risk_constraint: float = Field(default=0.5, ge=0, le=1)
    status: GoalStatus = "active"

    @field_validator("target_date")
    @classmethod
    def _future(cls, v: dt.date) -> dt.date:
        if v < dt.date.today():
            raise ValueError("Target date must be today or in the future.")
        return v


class GoalUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    purpose: str | None = Field(default=None, max_length=400)
    goal_type: GoalType | None = None
    current_cost: float | None = Field(default=None, gt=0)
    target_date: dt.date | None = None
    current_funded_amount: float | None = Field(default=None, ge=0)
    priority: int | None = Field(default=None, ge=1, le=5)
    criticality: int | None = Field(default=None, ge=1, le=5)
    date_flexible: bool | None = None
    amount_flexible: bool | None = None
    liquidity_requirement: LiquidityLevel | None = None
    risk_constraint: float | None = Field(default=None, ge=0, le=1)
    status: GoalStatus | None = None

    @field_validator("target_date")
    @classmethod
    def _future(cls, v: dt.date | None) -> dt.date | None:
        # Creation rejected a past date but editing did not, so a goal could be moved into the
        # past and then contribute a one-month horizon to the planner.
        if v is not None and v < dt.date.today():
            raise ValueError("Target date must be today or in the future.")
        return v


class GoalOut(ApiModel):
    id: int
    name: str
    purpose: str
    goal_type: str
    current_cost: float
    target_date: dt.date
    current_funded_amount: float
    priority: int
    criticality: int
    date_flexible: bool
    amount_flexible: bool
    liquidity_requirement: str
    risk_constraint: float
    status: str
    created_at: dt.datetime


class GoalProjectionOut(ApiModel):
    goal_ref: str
    goal_id: int | None
    name: str
    goal_type: str
    priority: int
    criticality: int
    target_date: str
    months_remaining: int
    current_cost: float
    future_target: float
    existing_funding: float
    remaining_gap: float
    required_monthly_contribution: float
    goal_budget: float = 0.0
    planned_monthly_contribution: float | None
    projected_funding: float | None
    projected_shortfall: float | None
    achievement_ratio: float | None
    feasibility: str
    date_flexible: bool
    amount_flexible: bool
    inflation_assumption: float
    investment_return_assumption: float
    uncertainty: str
    notes: list[str] = Field(default_factory=list)


class ContributionIn(ApiModel):
    amount: float = Field(gt=0)
    contribution_date: dt.date
    source: Literal["manual", "plan", "transfer", "other"] = "manual"
    note: str = Field(default="", max_length=240)


class ContributionOut(ContributionIn):
    id: int
    goal_id: int
    created_at: dt.datetime


# --------------------------------------------------------------------------------------
# monthly workflow
# --------------------------------------------------------------------------------------
class TransactionIn(ApiModel):
    kind: TxnKind
    category: str = Field(default="other", max_length=48)
    label: str = Field(default="", max_length=160)
    amount: float = Field(gt=0)
    txn_date: dt.date
    classification: TxnClass | None = None
    status: TxnStatus = "actual"
    is_recurring: bool = False
    goal_id: int | None = None
    note: str = Field(default="", max_length=240)
    client_ref: str | None = Field(default=None, max_length=64)


class TransactionUpdate(ApiModel):
    category: str | None = Field(default=None, max_length=48)
    label: str | None = Field(default=None, max_length=160)
    amount: float | None = Field(default=None, gt=0)
    txn_date: dt.date | None = None
    classification: TxnClass | None = None
    status: TxnStatus | None = None
    is_recurring: bool | None = None
    note: str | None = Field(default=None, max_length=240)


class TransactionOut(ApiModel):
    id: int
    kind: str
    category: str
    label: str
    amount: float
    txn_date: dt.date
    classification: str
    status: str
    is_recurring: bool
    goal_id: int | None
    note: str


class CategoryForecastOut(ApiModel):
    category: str
    amount: float
    method: str
    method_version: str
    history_months_used: int
    observations_used: int
    is_provisional: bool
    data_quality: str
    note: str = ""


class MonthOut(ApiModel):
    period: str
    status: str
    total_income_expected: float
    total_income_actual: float
    total_expense_estimated: float
    total_expense_actual: float
    surplus_projected: float
    surplus_actual: float
    reconciled_at: dt.datetime | None = None
    transaction_count: int = 0


class MonthDetailOut(ApiModel):
    month: MonthOut
    transactions: list[TransactionOut] = Field(default_factory=list)
    categories: dict[str, dict[str, float]] = Field(default_factory=dict)
    forecast: dict[str, Any] | None = None
    reconciliation: dict[str, Any] | None = None


class EstimateRequest(ApiModel):
    """Generate category-level estimates for a month.

    ``category_estimates`` are the user's own guesses; ``recurring`` marks categories that
    are known fixed obligations. Both are optional — an absent value is simply not used and
    nothing is invented.
    """

    category_estimates: dict[str, float] = Field(default_factory=dict)
    recurring_categories: dict[str, float] = Field(default_factory=dict)
    persist: bool = True


class ReconcileRequest(ApiModel):
    """Reconcile estimates against actuals. Estimates are never overwritten."""

    mark_actuals: bool = True
    update_future_forecast: bool = True


class BudgetIn(ApiModel):
    category: str = Field(min_length=1, max_length=48)
    monthly_limit: float = Field(gt=0)
    classification: Literal["essential", "discretionary"] = "discretionary"
    is_active: bool = True


class BudgetOut(BudgetIn):
    id: int
