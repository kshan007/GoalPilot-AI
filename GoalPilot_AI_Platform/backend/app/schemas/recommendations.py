"""Structured recommendation contract.

Two layers, deliberately separated:

1. :class:`LLMText` — the **only** thing the language model is allowed to return. Prose and
   identifiers. No amounts, no rates, no dates. If the model emits numbers they are ignored.
2. :class:`RecommendationResponse` — the full object returned by the API. Every numeric field
   in it is produced by deterministic code; the prose fields come from layer 1, or from a
   deterministic fallback when no model is available.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import Field, field_validator

from app.schemas.common import ApiModel

SCHEMA_VERSION = "recommendation@1.0"


class GoalReason(ApiModel):
    goal_ref: str = Field(max_length=64)
    reason: str = Field(max_length=1200)


class OptionCommentary(ApiModel):
    product_id: str = Field(max_length=64)
    commentary: str = Field(max_length=800)


class AlternativeScenario(ApiModel):
    scenario: str = Field(max_length=120)
    description: str = Field(max_length=800)


class LLMText(ApiModel):
    """The language-only contract. Enforced with ``extra="forbid"``."""

    financial_summary: str = Field(max_length=2000)
    cash_flow_explanation: str = Field(max_length=1500)
    plan_explanation: str = Field(max_length=2500)
    goal_reasons: list[GoalReason] = Field(default_factory=list, max_length=20)
    tradeoffs: list[str] = Field(default_factory=list, max_length=12)
    change_explanation: str = Field(default="", max_length=1500)
    risks: list[str] = Field(default_factory=list, max_length=12)
    monthly_actions: list[str] = Field(default_factory=list, max_length=12)
    missing_information: list[str] = Field(default_factory=list, max_length=12)
    investment_commentary: list[OptionCommentary] = Field(default_factory=list, max_length=20)
    loan_commentary: list[OptionCommentary] = Field(default_factory=list, max_length=20)
    alternatives: list[AlternativeScenario] = Field(default_factory=list, max_length=8)

    @field_validator("goal_reasons", "tradeoffs", "risks", "monthly_actions", mode="before")
    @classmethod
    def _coerce_none(cls, value: Any) -> Any:
        return value or []


class CashFlowStatusOut(ApiModel):
    monthly_income: float
    essential_expenses: float
    discretionary_expenses: float
    existing_emi: float
    monthly_surplus: float
    surplus_basis: str
    is_deficit: bool
    protected_buffer: float
    buffer_deficit: float
    buffer_sustained: bool
    available_goal_budget: float
    emergency_fund_target: float
    emergency_fund_progress: float
    emi_income_ratio: float
    emi_income_ratio_cap: float
    situation_tier: str


class ProtectedBufferOut(ApiModel):
    protected_monthly_buffer: float
    desired_monthly_buffer: float
    buffer_deficit: float
    buffer_sustained: bool
    emergency_fund_months_held: float
    minimum_cash_reserve_rule: str
    explanation: str


class GoalRecommendationOut(ApiModel):
    goal_ref: str
    goal_id: int | None = None
    name: str
    priority: int
    target_date: str
    target_amount_future: float
    existing_funding: float
    funding_gap: float
    recommended_monthly_contribution: float
    planned_savings_contribution: float
    planned_investment_contribution: float
    projected_funding: float | None = None
    expected_shortfall: float
    funding_status: Literal["fully_funded", "underfunded", "already_funded"]
    achievement_ratio: float
    reason: str
    assumptions_used: dict[str, Any] = Field(default_factory=dict)


class InvestmentOptionOut(ApiModel):
    product_id: str
    name: str
    category: str
    provider: str
    data_quality: str
    source_url: str = ""
    retrieved_at: str | None = None
    effective_date: str | None = None
    nav: float | None = None
    published_rate: float | None = None
    risk_level: str = "unknown"
    liquidity: str = "unknown"
    lock_in_months: int | None = None
    min_investment: float | None = None
    historical_returns: list[dict[str, Any]] = Field(default_factory=list)
    suitability_score: float = 0.0
    suitability_rationale: list[str] = Field(default_factory=list)
    material_risks: list[str] = Field(default_factory=list)
    commentary: str = ""
    freshness: str = "unknown"
    completeness: float = 0.0


class LoanOptionOut(ApiModel):
    product_id: str
    lender: str
    product_name: str
    category: str
    published_rate: float | None = None
    rate_type: str = "unknown"
    rate_basis: str = ""
    #: The basis the EMI was computed on. Without these the page could say "EMI 12,879" without
    #: saying for how much or for how long.
    principal: float | None = None
    tenure_months: int | None = None
    indicative_emi: float | None = None
    total_interest: float | None = None
    apr_including_known_fees: float | None = None
    affordability_verdict: str = "unknown"
    data_quality: str = ""
    source_url: str = ""
    retrieved_at: str | None = None
    eligibility_notes: list[str] = Field(default_factory=list)
    material_risks: list[str] = Field(default_factory=list)
    commentary: str = ""
    is_personalised_offer: bool = False


class RecommendedPlanOut(ApiModel):
    algorithm: str
    algorithm_label: str
    status: str
    feasible: bool
    monthly_contributions_total: float
    monthly_savings_total: float
    monthly_investment_total: float
    new_loan_principal_total: float
    new_loan_emi_total: float
    total_shortfall: float
    weighted_goal_achievement: float | None = None
    investment_ceiling: float | None = None
    model_version: str
    config_version: str
    run_id: int | None = None


class DataSourceOut(ApiModel):
    name: str
    provider: str
    data_quality: str
    source_url: str = ""
    retrieved_at: str | None = None
    effective_date: str | None = None
    note: str = ""


class RecommendationResponse(ApiModel):
    schema_version: str = SCHEMA_VERSION
    generated_at: dt.datetime
    run_id: int | None = None
    optimization_run_id: int | None = None

    financial_summary: str
    cash_flow_status: CashFlowStatusOut
    protected_buffer: ProtectedBufferOut
    available_goal_budget: float

    goal_recommendations: list[GoalRecommendationOut] = Field(default_factory=list)
    investment_options: list[InvestmentOptionOut] = Field(default_factory=list)
    #: Amount / horizon / assumed return / projected value for the investment sleeve.
    investment_terms: dict[str, Any] = Field(default_factory=dict)
    loan_options: list[LoanOptionOut] = Field(default_factory=list)
    #: Principal / rate / tenure / EMI / total interest for the plan's borrowing.
    loan_terms: dict[str, Any] = Field(default_factory=dict)
    recommended_plan: RecommendedPlanOut
    alternative_scenarios: list[AlternativeScenario] = Field(default_factory=list)
    risks_and_warnings: list[str] = Field(default_factory=list)
    data_sources: list[DataSourceOut] = Field(default_factory=list)
    assumptions: dict[str, Any] = Field(default_factory=dict)
    missing_information: list[str] = Field(default_factory=list)
    monthly_actions: list[str] = Field(default_factory=list)
    explanation: str
    disclaimer: str
    #: Engine/config disclosures that are not risks (capacity caps, basis notes, RL fallbacks).
    technical_notes: list[str] = Field(default_factory=list)

    llm: dict[str, Any] = Field(default_factory=dict)
    validation: dict[str, Any] = Field(default_factory=dict)


class RecommendationRequest(ApiModel):
    """What the caller may control. All fields are optional: the defaults come from the stored
    profile, goals and the latest plan."""

    include_investments: bool = True
    include_loans: bool = True
    include_history: bool = False
    loan_principal: float = Field(default=500_000, ge=0)
    loan_tenure_months: int = Field(default=48, ge=1, le=600)
    persist: bool = True


class AskRequest(ApiModel):
    question: str = Field(min_length=3, max_length=600)
    recommendation_id: int | None = None


class AskResponse(ApiModel):
    answer: str
    grounded_on: dict[str, Any] = Field(default_factory=dict)
    llm: dict[str, Any] = Field(default_factory=dict)
    disclaimer: str
