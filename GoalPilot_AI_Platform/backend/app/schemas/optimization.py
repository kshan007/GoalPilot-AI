"""Optimisation, comparison, scenario and dashboard schemas."""
from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import Field

from app.schemas.common import ApiModel

Algorithm = Literal["lp", "rl", "hybrid", "rule_baseline", "lp_unconstrained"]


PERIOD_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"


class AssumptionsIn(ApiModel):
    annual_inflation: float = Field(default=0.03, gt=-1, lt=1)
    investment_return: float = Field(default=0.05, gt=-1, lt=1)
    savings_return: float = Field(default=0.0, gt=-1, lt=1)
    loan_annual_rate: float = Field(default=0.12, gt=-1, lt=1)
    loan_tenure_months: int = Field(default=60, ge=1, le=600)
    max_loan_per_goal: float = Field(default=150_000, ge=0)
    max_new_loan: float = Field(default=150_000, ge=0)
    investment_capacity_ratio: float | None = Field(default=None, ge=0, le=1)
    emergency_months: float | None = Field(default=None, ge=0, le=36)
    allow_financing: bool = True
    enforce_investment_capacity: bool = True


class PlanRequest(ApiModel):
    algorithm: Algorithm = "lp"
    assumptions: AssumptionsIn | None = None
    rl_checkpoint: str | None = None
    label: str = Field(default="", max_length=120)
    #: Which month's recorded ACTUAL expenses should drive the cash flow. Omit to let the
    #: platform pick the most recent month that has actuals.
    period: str | None = Field(default=None, pattern=PERIOD_PATTERN)


class PlanDiffOut(ApiModel):
    previous_run_id: int | None = None
    changed: bool = False
    summary: str = ""
    goal_changes: list[dict[str, Any]] = Field(default_factory=list)
    totals: dict[str, Any] = Field(default_factory=dict)


class GoalAllocationOut(ApiModel):
    goal_ref: str
    goal_id: int | None = None
    goal_name: str = ""
    funding_gap: float = 0.0
    future_goal_cost: float = 0.0
    initial_savings_allocated: float = 0.0
    existing_assets_allocated: float = 0.0
    monthly_savings_contribution: float = 0.0
    monthly_investment_contribution: float = 0.0
    loan_principal: float = 0.0
    estimated_loan_emi: float = 0.0
    shortfall: float = 0.0
    achievement_ratio: float = 0.0
    projected_new_funding: float = 0.0
    target: float | None = None
    funded: float | None = None


class PlanResponse(ApiModel):
    run_id: int
    algorithm: str
    algorithm_label: str
    status: str
    feasible: bool
    objective_value: float | None = None
    #: What the objective measures, in words. The value is a penalty score, not a cash amount,
    #: and the UI must be able to say so without hard-coding the explanation.
    objective_definition: str | None = None
    #: Financial readiness (emergency fund, buffer, debt service), deliberately separate from
    #: `goals_funded`. A plan can fund every goal and still be fragile.
    readiness: dict[str, Any] = Field(default_factory=dict)
    runtime_ms: int
    model_version: str
    config_version: str
    assumptions: dict[str, Any] = Field(default_factory=dict)
    summary: dict[str, Any] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    #: One-change-at-a-time re-solves of this plan's own constraints (later deadline, smaller
    #: target, financing on). Reported only — nothing is applied to the user's goals.
    alternatives: list[dict[str, Any]] = Field(default_factory=list)
    #: ``feasible`` means the plan satisfies every hard constraint. These say whether the goals are
    #: actually affordable by their deadlines, which is a different statement.
    goals_funded: bool = False
    unfunded_goals: list[str] = Field(default_factory=list)
    total_shortfall: float = 0.0
    allocations: list[GoalAllocationOut] = Field(default_factory=list)
    goal_projections: list[dict[str, Any]] = Field(default_factory=list)
    cashflow: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    fallback_reason: str | None = None
    diff: PlanDiffOut | None = None
    created_at: dt.datetime


class ComparisonArmOut(ApiModel):
    algorithm: str
    label: str
    status: str
    feasible: bool
    available: bool
    metric_basis: str
    metrics: dict[str, Any] = Field(default_factory=dict)
    #: The same metrics, same keys, same units, for every arm — the only block the UI should
    #: compare across arms. `metrics` keeps each engine's raw output for diagnostics.
    metrics_comparable: dict[str, Any] = Field(default_factory=dict)
    #: True only when this arm is scored on the same basis as the reference arm. An unranked
    #: arm is reported, never ranked.
    ranked: bool = False
    runtime_ms: int
    model_version: str
    warnings: list[str] = Field(default_factory=list)
    fallback_reason: str | None = None


class ComparisonResponse(ApiModel):
    run_id: int
    selector_version: str = ""
    recommended_algorithm: str
    recommendation_reason: str
    sufficient_evidence_for_change: bool
    decision_rule: dict[str, Any] = Field(default_factory=dict)
    #: Where the two outcome metrics disagree. Without this the selection looks arbitrary to a
    #: reader who is scoring on the other metric.
    objective_disagreement: dict[str, Any] = Field(default_factory=dict)
    decision_basis: str | None = None
    arms: list[ComparisonArmOut] = Field(default_factory=list)
    not_selected: list[dict[str, Any]] = Field(default_factory=list)
    #: What each comparison metric means, measured how, in what unit.
    metric_definitions: dict[str, str] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    capacity_ratio: float
    capacity_derivation: str
    runtime_ms: int
    research_reference: dict[str, Any] = Field(default_factory=dict)
    created_at: dt.datetime


class ScenarioRunRequest(ApiModel):
    preset: str = Field(default="expenses_up")
    parameters: dict[str, float] = Field(default_factory=dict)
    algorithm: Algorithm = "lp"
    name: str = Field(default="", max_length=160)


class ScenarioPresetOut(ApiModel):
    preset: str
    name: str
    description: str
    parameters: dict[str, float]
    assumption_note: str


class ScenarioRunOut(ApiModel):
    id: int
    preset: str
    name: str
    parameters: dict[str, Any]
    baseline: dict[str, Any]
    stressed: dict[str, Any]
    deltas: dict[str, Any]
    narrative: list[str]
    created_at: dt.datetime


class DashboardResponse(ApiModel):
    as_of: str
    cashflow: dict[str, Any]
    goals: dict[str, Any]
    monthly: dict[str, Any]
    forecasts: dict[str, Any]
    debt: dict[str, Any]
    optimization: dict[str, Any]
    labels_note: str


class ModelRegistryEntry(ApiModel):
    name: str
    version: str
    kind: str
    status: str
    artifact_path: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    evaluated_at: dt.datetime | None = None


class AlgorithmAvailability(ApiModel):
    algorithm: str
    label: str
    ready: bool
    status: str
    reason: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)
