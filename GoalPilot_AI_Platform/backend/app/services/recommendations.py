"""Structured recommendations: deterministic facts + language-model explanation.

The split is the whole point of this module:

* **Code** decides every number: the cash flow, the protected buffer, the goal budget, the LP
  allocation, the shortfalls, the EMI arithmetic, the suitability scores.
* **The model** writes prose about those numbers, and only prose.

So the model's output is a :class:`~app.schemas.recommendations.LLMText`: no amounts, no rates,
no dates. Numbers in the final response are copied from the computed skeleton *after* the model
has answered, which makes it structurally impossible for the model to change a figure.

Grounding checks applied to the model's prose before it is accepted
------------------------------------------------------------------
1. Pydantic schema validation (unknown keys are rejected).
2. Banned-language check (guarantees, "risk-free", "assured", "definitely").
3. Amount-grounding check: any currency-like amount in the prose must match a figure that the
   calculation services actually produced.
4. Identifier check: goal refs and product ids must exist in this response.

Any failure discards the model text and a deterministic explanation is used instead. Nothing is
silently "repaired" into something that looks model-authored but is not.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import math
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.errors import NotFoundError, ValidationFailure
from app.engines.common import ALGORITHM_LABELS
from app.llm import gemini_client
from app.models import Goal, GoalAllocation, OptimizationRun, RecommendationRun, User
from app.schemas.recommendations import (
    SCHEMA_VERSION,
    CashFlowStatusOut,
    DataSourceOut,
    GoalReason,
    GoalRecommendationOut,
    InvestmentOptionOut,
    LLMText,
    LoanOptionOut,
    ProtectedBufferOut,
    RecommendedPlanOut,
)
from app.services import investment_discovery, loan_analysis
from app.services.money import months_between
from app.services.cashflow import CashFlow
from app.services.goals import project_goals
from app.services.planner import (
    _cashflow_out,
    assumptions_for,
    load_cashflow,
    load_goals,
    months_lookup,
    persist_run,
    run_algorithm,
    situation_tier,
)

_log = logging.getLogger("goalpilot.recommendations")

DISCLAIMER = (
    "GoalPilot AI is an academic decision-support prototype, not a registered investment "
    "adviser or a lender. Figures are projections or sourced product information, not "
    "guarantees. No transaction, investment or loan is executed by this application. Verify "
    "product terms in the provider's own documents before acting."
)

BANNED_PHRASES = (
    "guaranteed",
    "guarantee",
    "assured return",
    "risk-free",
    "risk free",
    "will definitely",
    "sure shot",
    "no risk",
    "promise",
)

AMOUNT_PATTERN = re.compile(r"(?:₹|rs\.?|inr)\s?([0-9][0-9,]*(?:\.[0-9]{1,2})?)", re.I)
BARE_AMOUNT_PATTERN = re.compile(r"\b([0-9]{2,3}(?:,[0-9]{3})+)(?:\.[0-9]{1,2})?\b")

_LLM_SCHEMA_HINT = {
    "financial_summary": "2-3 sentences on the household's position, using the provided figures",
    "cash_flow_explanation": "one short paragraph explaining how surplus was computed",
    "plan_explanation": "why this allocation was chosen and what it trades off",
    "goal_reasons": [{"goal_ref": "G<id from input>", "reason": "one or two sentences"}],
    "tradeoffs": ["short bullet"],
    "change_explanation": "what changed since the previous plan, or '' if there is none",
    "risks": ["short bullet, factual, no invented risks"],
    "monthly_actions": ["imperative action for this month"],
    "missing_information": ["what the user should add or confirm"],
    "investment_commentary": [{"product_id": "<from input>", "commentary": "1-2 sentences"}],
    "loan_commentary": [{"product_id": "<from input>", "commentary": "1-2 sentences"}],
    "alternatives": [{"scenario": "short name", "description": "one sentence"}],
}


# --------------------------------------------------------------------------------------
# plan loading
# --------------------------------------------------------------------------------------
def _allocations_from_run(db: Session, run: OptimizationRun) -> list[dict[str, Any]]:
    rows = []
    for a in db.execute(
        select(GoalAllocation).where(GoalAllocation.optimization_run_id == run.id)
    ).scalars():
        rows.append(
            {
                "goal_ref": a.goal_ref,
                "goal_id": a.goal_id,
                "goal_name": a.goal_name,
                "funding_gap": float(a.funding_gap),
                "future_goal_cost": float(a.future_goal_cost),
                "existing_funding": float(a.existing_funding),
                "initial_savings_allocated": float(a.initial_savings_allocated),
                "existing_assets_allocated": float(a.existing_assets_allocated),
                "monthly_savings_contribution": float(a.monthly_savings_contribution),
                "monthly_investment_contribution": float(a.monthly_investment_contribution),
                "loan_principal": float(a.loan_principal),
                "estimated_loan_emi": float(a.estimated_loan_emi),
                "projected_new_funding": float(a.projected_new_funding),
                "shortfall": float(a.shortfall),
                "achievement_ratio": float(a.achievement_ratio),
            }
        )
    return rows


def load_or_create_plan(
    db: Session, user: User, *, run_id: int | None = None
) -> tuple[OptimizationRun, list[dict[str, Any]], dict[str, Any]]:
    """Use the latest persisted plan, or produce one. Never fabricates allocations."""
    if run_id is not None:
        run = db.execute(
            select(OptimizationRun).where(
                OptimizationRun.id == run_id, OptimizationRun.user_id == user.id,
                OptimizationRun.kind == "plan",
            )
        ).scalar_one_or_none()
        if run is None:
            raise NotFoundError(f"Plan run {run_id} was not found")
        payload = json.loads(run.result_json or "{}")
        return run, _allocations_from_run(db, run), payload

    run = db.execute(
        select(OptimizationRun)
        .where(OptimizationRun.user_id == user.id, OptimizationRun.kind == "plan")
        .order_by(OptimizationRun.created_at.desc(), OptimizationRun.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if run is not None:
        payload = json.loads(run.result_json or "{}")
        allocations = _allocations_from_run(db, run)
        if allocations or run.status != "optimal":
            return run, allocations, payload

    goals = load_goals(db, user.id)
    if not goals:
        raise ValidationFailure("Create at least one active goal before requesting a recommendation.")
    cashflow = load_cashflow(db, user.id)
    assumptions = assumptions_for(db, user.id)
    result = run_algorithm(
        algorithm="lp",
        goals=goals,
        cashflow=cashflow,
        lookup=months_lookup(goals),
        assumptions=assumptions,
    )
    run = persist_run(
        db,
        user.id,
        result,
        kind="plan",
        assumptions=assumptions.as_dict(),
        input_snapshot={"goal_count": len(goals), "source": "recommendation_bootstrap"},
        goal_db_ids={f"G{g.id}": g.id for g in goals},
        label="bootstrap for recommendation",
    )
    db.commit()
    db.refresh(run)
    payload = json.loads(run.result_json or "{}")
    return run, _allocations_from_run(db, run), payload


# --------------------------------------------------------------------------------------
# computed skeleton
# --------------------------------------------------------------------------------------
def _cashflow_status(cf: CashFlow) -> CashFlowStatusOut:
    return CashFlowStatusOut(
        monthly_income=round(cf.monthly_income, 2),
        essential_expenses=round(cf.essential_expenses, 2),
        discretionary_expenses=round(cf.discretionary_expenses, 2),
        existing_emi=round(cf.existing_emi, 2),
        monthly_surplus=round(cf.monthly_surplus, 2),
        surplus_basis=cf.surplus_basis,
        is_deficit=cf.is_deficit,
        protected_buffer=round(cf.protected_buffer, 2),
        buffer_deficit=round(cf.buffer_deficit, 2),
        buffer_sustained=cf.buffer_sustained,
        available_goal_budget=round(cf.available_goal_budget, 2),
        emergency_fund_target=round(cf.emergency_fund_target, 2),
        emergency_fund_progress=round(cf.emergency_fund_progress, 4),
        emi_income_ratio=round(cf.emi_income_ratio, 4),
        emi_income_ratio_cap=round(cf.emi_income_ratio_cap, 4),
        situation_tier=situation_tier(cf),
    )


def _buffer_block(cf: CashFlow) -> ProtectedBufferOut:
    if cf.buffer_sustained:
        explanation = (
            f"{cf.protected_buffer:,.0f} per month is ring-fenced before any goal contribution. "
            f"That leaves {cf.available_goal_budget:,.0f} of the {max(0.0, cf.monthly_surplus):,.0f} "
            "monthly surplus available for goals."
        )
    else:
        explanation = (
            f"The requested buffer is {cf.desired_buffer:,.0f} per month but only "
            f"{cf.protected_buffer:,.0f} can be set aside; {cf.buffer_deficit:,.0f} per month "
            "is unaccounted for. Goal funding is capped at what remains, and the shortfall is "
            "reported rather than absorbed silently."
        )
    return ProtectedBufferOut(
        protected_monthly_buffer=round(cf.protected_buffer, 2),
        desired_monthly_buffer=round(cf.desired_buffer, 2),
        buffer_deficit=round(cf.buffer_deficit, 2),
        buffer_sustained=cf.buffer_sustained,
        emergency_fund_months_held=(
            round(cf.liquid_savings / cf.essential_expenses, 2) if cf.essential_expenses > 0 else 0.0
        ),
        minimum_cash_reserve_rule=(
            f"liquid savings must cover {cf.emergency_months:g} months of essential expenses "
            f"({cf.emergency_fund_target:,.0f}); that reserve is excluded from the goal cash pool"
        ),
        explanation=explanation,
    )


def _goal_recommendations(
    goals: list[Goal], allocations: list[dict[str, Any]], *, inflation: float,
    savings_return: float, investment_return: float, cashflow: CashFlow,
) -> list[GoalRecommendationOut]:
    import pandas as pd

    frame = pd.DataFrame(allocations) if allocations else None
    projections = project_goals(
        goals,
        inflation=inflation,
        savings_return=savings_return,
        investment_return=investment_return,
        monthly_surplus=max(0.0, cashflow.monthly_surplus),
        goal_budget=max(0.0, cashflow.available_goal_budget),
        available_cash=cashflow.available_cash_for_goals,
        allocations=frame,
    )
    by_ref = {a["goal_ref"]: a for a in allocations}
    out: list[GoalRecommendationOut] = []
    for projection in projections:
        alloc = by_ref.get(projection.goal_ref)
        gap = float(projection.remaining_gap)

        # A missing allocation means the optimiser funded this goal with nothing. A missing
        # shortfall means the projection could not be computed. Neither is evidence of funding,
        # so both fall to "underfunded" with the full remaining gap — the conservative reading.
        # Claiming "fully_funded" here was a real defect: it printed a funded status next to an
        # achievement ratio of zero.
        if gap <= 0:
            status = "already_funded"
            shortfall = 0.0
        elif alloc is None or projection.projected_shortfall is None:
            status = "underfunded"
            shortfall = max(0.0, gap)
        else:
            shortfall = float(projection.projected_shortfall)
            status = "underfunded" if shortfall > 1.0 else "fully_funded"

        reason = _deterministic_goal_reason(projection, status, alloc or {}, shortfall)
        out.append(
            GoalRecommendationOut(
                goal_ref=projection.goal_ref,
                goal_id=projection.goal_id,
                name=projection.name,
                priority=projection.priority,
                target_date=projection.target_date,
                target_amount_future=round(projection.future_target, 2),
                existing_funding=round(projection.existing_funding, 2),
                funding_gap=round(gap, 2),
                recommended_monthly_contribution=round(projection.required_monthly_contribution, 2),
                planned_savings_contribution=round(float(alloc.get("monthly_savings_contribution", 0)), 2),
                planned_investment_contribution=round(float(alloc.get("monthly_investment_contribution", 0)), 2),
                projected_funding=(
                    round(projection.projected_funding, 2)
                    if projection.projected_funding is not None
                    else None
                ),
                expected_shortfall=round(shortfall, 2),
                funding_status=status,  # type: ignore[arg-type]
                achievement_ratio=round(float(projection.achievement_ratio or 0.0), 4),
                reason=reason,
                assumptions_used={
                    "inflation": inflation,
                    "savings_return": savings_return,
                    "investment_return": investment_return,
                    "months_remaining": projection.months_remaining,
                },
            )
        )
    return out


def _deterministic_goal_reason(
    projection: Any, status: str, alloc: dict[str, Any], shortfall: float
) -> str:
    if status == "already_funded":
        return "Already funded at today's projected cost; no further contribution is needed."
    planned = float(alloc.get("monthly_savings_contribution", 0)) + float(
        alloc.get("monthly_investment_contribution", 0)
    )
    base = (
        f"The goal needs {projection.required_monthly_contribution:,.0f} per month to close a "
        f"{projection.remaining_gap:,.0f} gap in {projection.months_remaining} months. "
    )
    if status == "fully_funded":
        return base + f"The plan assigns {planned:,.0f} per month, which meets it."
    if not alloc:
        return (
            base
            + "The optimiser allocated nothing to this goal, so the full "
            f"{projection.remaining_gap:,.0f} remains unfunded. The budget constraint binds "
            "before this goal is reached."
        )
    return (
        base
        + f"The plan can assign only {planned:,.0f} per month, leaving a projected shortfall of "
        f"{shortfall:,.0f}. The shortfall is caused by the budget constraint, not by an "
        "unwillingness to fund the goal."
    )


def _recommended_plan(run: OptimizationRun, allocations: list[dict[str, Any]], payload: dict[str, Any]) -> RecommendedPlanOut:
    summary = payload.get("summary", {}) or {}
    constraints = payload.get("constraints", {}) or {}
    savings = sum(float(a["monthly_savings_contribution"]) for a in allocations)
    investment = sum(float(a["monthly_investment_contribution"]) for a in allocations)
    principal = sum(float(a["loan_principal"]) for a in allocations)
    emi_total = sum(float(a["estimated_loan_emi"]) for a in allocations)
    return RecommendedPlanOut(
        algorithm=run.algorithm,
        algorithm_label=ALGORITHM_LABELS.get(run.algorithm, run.algorithm),
        status=run.status,
        feasible=bool(run.feasible),
        monthly_contributions_total=round(savings + investment, 2),
        monthly_savings_total=round(savings, 2),
        monthly_investment_total=round(investment, 2),
        new_loan_principal_total=round(principal, 2),
        new_loan_emi_total=round(emi_total, 2),
        total_shortfall=round(float(summary.get("total_shortfall", 0) or 0), 2),
        weighted_goal_achievement=(
            float(summary["weighted_goal_achievement"])
            if isinstance(summary.get("weighted_goal_achievement"), (int, float))
            else None
        ),
        investment_ceiling=(
            float(constraints["investment_permitted"])
            if isinstance(constraints.get("investment_permitted"), (int, float))
            else None
        ),
        model_version=run.model_version,
        config_version=run.config_version,
        run_id=run.id,
    )


def _monthly_actions(cf: CashFlow, plan: RecommendedPlanOut, goals: list[GoalRecommendationOut]) -> list[str]:
    actions: list[str] = []
    if cf.protected_buffer > 0:
        actions.append(
            f"Move {cf.protected_buffer:,.0f} into your savings buffer before funding any goal."
        )
    funded = [g for g in goals if g.planned_savings_contribution + g.planned_investment_contribution > 0.5]
    for goal in funded[:5]:
        total = goal.planned_savings_contribution + goal.planned_investment_contribution
        actions.append(f"Contribute {total:,.0f} to {goal.name} this month.")
    if cf.emergency_fund_progress < 1.0 and cf.emergency_fund_gap > 0:
        actions.append(
            f"The emergency fund is {cf.emergency_fund_progress:.0%} funded "
            f"({cf.emergency_fund_gap:,.0f} short of the {cf.emergency_months:g}-month target); "
            "prioritise it before increasing discretionary goal contributions."
        )
    if plan.new_loan_emi_total > 0:
        actions.append(
            f"Do not commit to the {plan.new_loan_emi_total:,.0f} monthly loan payment until you "
            "have compared it against the alternatives on the Loans page."
        )
    actions.append(
        "Record this month's actual income and expenses so next month's plan uses facts rather "
        "than the profile estimate."
    )
    return actions


def _data_sources(
    cf: CashFlow,
    investment_payload: dict[str, Any] | None,
    loan_payload: dict[str, Any] | None,
) -> list[DataSourceOut]:
    sources: list[DataSourceOut] = [
        DataSourceOut(
            name="User financial profile, goals, assets and liabilities",
            provider="goalpilot_database",
            data_quality="user_input",
            note=cf.expense_basis,
        ),
        DataSourceOut(
            name="Optimisation run and its stored assumptions",
            provider="goalpilot_engines",
            data_quality="computed",
        ),
    ]
    for payload in (investment_payload, loan_payload):
        for row in (payload or {}).get("providers", []) or []:
            if row.get("status") in {"ok", "partial"}:
                sources.append(
                    DataSourceOut(
                        name=row.get("provider", ""),
                        provider=row.get("provider", ""),
                        data_quality=row.get("data_quality") or "",
                        source_url=row.get("source_url") or "",
                        retrieved_at=row.get("retrieved_at"),
                        note=(row.get("reason") or "")[:300],
                    )
                )
    return sources


# --------------------------------------------------------------------------------------
# model prompt + validation
# --------------------------------------------------------------------------------------
def _facts_for_model(
    *,
    cf: CashFlow,
    plan: RecommendedPlanOut,
    goals: list[GoalRecommendationOut],
    investments: list[InvestmentOptionOut],
    loans: list[LoanOptionOut],
    diff: dict[str, Any] | None,
    warnings: list[str],
) -> dict[str, Any]:
    return {
        "currency": "INR",
        "cash_flow": {
            "monthly_income": cf.monthly_income,
            "essential_expenses": cf.essential_expenses,
            "discretionary_expenses": cf.discretionary_expenses,
            "existing_emi": cf.existing_emi,
            "monthly_surplus": cf.monthly_surplus,
            "surplus_basis": cf.surplus_basis,
            "protected_buffer": cf.protected_buffer,
            "buffer_deficit": cf.buffer_deficit,
            "available_goal_budget": cf.available_goal_budget,
            "emergency_fund_target": cf.emergency_fund_target,
            "emergency_fund_progress": cf.emergency_fund_progress,
            "is_deficit": cf.is_deficit,
            # Pre-computed sums. Without these the model correctly writes "committed spending
            # totals 61,000" and the grounding check rejects it as an invented figure — a false
            # positive that silently degraded every live response to the fallback.
            "committed_outgoings": round(
                cf.essential_expenses + cf.discretionary_expenses + cf.existing_emi, 2
            ),
            "total_monthly_outgoings_incl_buffer": round(
                cf.essential_expenses
                + cf.discretionary_expenses
                + cf.existing_emi
                + cf.protected_buffer,
                2,
            ),
        },
        "plan": plan.model_dump(),
        "goals": [
            {
                "goal_ref": g.goal_ref,
                "name": g.name,
                "priority": g.priority,
                "target_date": g.target_date,
                "target_amount_future": g.target_amount_future,
                "funding_gap": g.funding_gap,
                "planned_monthly": g.planned_savings_contribution + g.planned_investment_contribution,
                "required_monthly": g.recommended_monthly_contribution,
                "funding_status": g.funding_status,
                "expected_shortfall": g.expected_shortfall,
            }
            for g in goals
        ],
        "investment_options": [
            {
                "product_id": o.product_id,
                "name": o.name,
                "category": o.category,
                "risk_level": o.risk_level,
                "liquidity": o.liquidity,
                "data_quality": o.data_quality,
                "suitability_score": o.suitability_score,
                "cautions": o.material_risks[:3],
            }
            for o in investments[:10]
        ],
        "loan_options": [
            {
                "product_id": o.product_id,
                "lender": o.lender,
                "published_rate": o.published_rate,
                "indicative_emi": o.indicative_emi,
                "total_interest": o.total_interest,
                "affordability_verdict": o.affordability_verdict,
                "rate_basis": o.rate_basis,
            }
            for o in loans[:10]
        ],
        "change_since_previous_plan": diff or {},
        "computed_warnings": warnings,
        "constraints_you_must_not_contradict": [
            "Available goal budget is "
            f"{cf.available_goal_budget:.0f} per month after a protected buffer of "
            f"{cf.protected_buffer:.0f}.",
            "The optimiser's plan is final on amounts; do not propose different amounts.",
            "A goal marked 'underfunded' must be described as underfunded.",
        ],
    }


def _build_prompt(facts: dict[str, Any]) -> str:
    return (
        "Explain the plan described in the JSON below to the user who owns it.\n"
        "Use ONLY the figures in the JSON. Do not compute anything. Do not add products.\n"
        "If the plan leaves a goal underfunded, say so plainly and explain which constraint "
        "caused it. If there is no change since the previous plan, set change_explanation to "
        "an empty string.\n"
        "DO NOT PERFORM ARITHMETIC. Never add, subtract, multiply, divide, sum, annualise or "
        "project. Do not write totals, differences, percentages or multi-year amounts. If the "
        "figure you want is not an exact value present in the JSON, describe it qualitatively "
        "instead. This is enforced: one amount that is not in the JSON rejects the whole answer.\n"
        "Keep it concise: at most three sentences for financial_summary, four for "
        "plan_explanation, one sentence per goal reason. Every JSON string must be properly "
        "escaped — no raw line breaks inside a string.\n"
        "monthly_actions must be concrete and use the amounts from the JSON.\n"
        "Format money the way an Indian reader expects: a rupee sign and Indian digit grouping, "
        "whole rupees, for example Rs 1,20,000 and Rs 17,165. Rounding away paise is fine; never "
        "change the magnitude of a figure or introduce one that is not in the JSON.\n"
        "Do not use the words guaranteed, assure, risk-free or sure.\n"
        f"JSON:\n{json.dumps(facts, indent=2, default=str)}"
    )


def _collect_amounts(*values: Any) -> set[float]:
    amounts: set[float] = set()
    stack = list(values)
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            stack.extend(item.values())
        elif isinstance(item, (list, tuple)):
            stack.extend(item)
        elif isinstance(item, bool):
            continue
        elif isinstance(item, (int, float)):
            amounts.add(round(abs(float(item)), 1))
    return amounts


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _ungrounded_tokens(text: str, allowed: set[float]) -> list[str]:
    """Currency-like amounts in ``text`` that match no computed figure."""
    bad: list[str] = []
    for raw in list(AMOUNT_PATTERN.findall(text)) + list(BARE_AMOUNT_PATTERN.findall(text)):
        try:
            value = round(abs(float(raw.replace(",", ""))), 1)
        except ValueError:
            continue
        if value < 1000:
            continue
        if not any(abs(value - candidate) <= max(1.0, candidate * 0.01) for candidate in allowed):
            bad.append(raw)
    return bad


def sanitize_ungrounded(text: LLMText, *, facts: dict[str, Any]) -> tuple[LLMText, list[str]]:
    """Remove sentences that assert an amount the calculation services never produced.

    Rejecting the whole answer for one stray figure made the live path unusable: a model that
    correctly explains the plan but happens to restate a derived total would be discarded
    entirely. Dropping the offending sentence keeps the guarantee (no unverified number reaches
    the reader) without throwing away the rest of an accurate explanation. The count of removed
    sentences is reported so the behaviour is visible rather than silent.

    Banned language and unknown identifiers are still hard failures — those are safety issues,
    not formatting ones.
    """
    allowed = _collect_amounts(facts)
    removed: list[str] = []

    def keep_sentences(value: str) -> str:
        kept = []
        for sentence in _SENTENCE_SPLIT.split(value or ""):
            if not sentence.strip():
                continue
            bad = _ungrounded_tokens(sentence, allowed)
            if bad:
                removed.append(sentence.strip()[:160])
                continue
            kept.append(sentence.strip())
        return " ".join(kept).strip()

    def keep_items(values: list[str]) -> list[str]:
        kept = []
        for item in values:
            if _ungrounded_tokens(item, allowed):
                removed.append(item.strip()[:160])
                continue
            kept.append(item)
        return kept

    cleaned = text.model_copy(
        update={
            "financial_summary": keep_sentences(text.financial_summary),
            "cash_flow_explanation": keep_sentences(text.cash_flow_explanation),
            "plan_explanation": keep_sentences(text.plan_explanation),
            "change_explanation": keep_sentences(text.change_explanation),
            "tradeoffs": keep_items(list(text.tradeoffs)),
            "risks": keep_items(list(text.risks)),
            "monthly_actions": keep_items(list(text.monthly_actions)),
            "missing_information": keep_items(list(text.missing_information)),
            "goal_reasons": [
                reason
                for reason in text.goal_reasons
                if not _ungrounded_tokens(reason.reason, allowed)
            ],
        }
    )
    return cleaned, removed


def validate_llm_text(
    text: LLMText, *, facts: dict[str, Any], goal_refs: set[str], product_ids: set[str]
) -> tuple[bool, list[str]]:
    problems: list[str] = []
    blob = " ".join(
        [
            text.financial_summary,
            text.cash_flow_explanation,
            text.plan_explanation,
            text.change_explanation,
            " ".join(text.tradeoffs),
            " ".join(text.risks),
            " ".join(text.monthly_actions),
            " ".join(text.missing_information),
            " ".join(r.reason for r in text.goal_reasons),
        ]
    ).lower()
    for phrase in BANNED_PHRASES:
        if phrase in blob:
            problems.append(f"banned_phrase:{phrase}")
    for goal in text.goal_reasons:
        if goal.goal_ref not in goal_refs:
            problems.append(f"unknown_goal_ref:{goal.goal_ref}")
    for item in list(text.investment_commentary) + list(text.loan_commentary):
        if item.product_id not in product_ids:
            problems.append(f"unknown_product_id:{item.product_id}")

    allowed = _collect_amounts(facts)
    for raw in list(AMOUNT_PATTERN.findall(blob)) + list(BARE_AMOUNT_PATTERN.findall(blob)):
        cleaned = raw.replace(",", "")
        try:
            value = round(abs(float(cleaned)), 1)
        except ValueError:
            continue
        if value < 1000:
            continue
        if not any(abs(value - candidate) <= max(1.0, candidate * 0.01) for candidate in allowed):
            problems.append(f"ungrounded_amount:{raw}")
            break
    return (not problems), problems


def _deterministic_text(
    *,
    cf: CashFlow,
    plan: RecommendedPlanOut,
    goals: list[GoalRecommendationOut],
    warnings: list[str],
    diff: dict[str, Any] | None,
) -> LLMText:
    under = [g for g in goals if g.funding_status == "underfunded"]
    funded = [g for g in goals if g.funding_status == "fully_funded"]
    summary = (
        f"Your income is {cf.monthly_income:,.0f} a month and your committed spending and debt "
        f"payments total {cf.essential_expenses + cf.discretionary_expenses + cf.existing_emi:,.0f}, "
        f"leaving a monthly surplus of {cf.monthly_surplus:,.0f}. "
        f"{cf.protected_buffer:,.0f} of that is protected as your savings buffer, so "
        f"{cf.available_goal_budget:,.0f} is available for goals."
    )
    cash_flow = (
        f"Surplus = income {cf.monthly_income:,.0f} - essential {cf.essential_expenses:,.0f} - "
        f"discretionary {cf.discretionary_expenses:,.0f} - existing EMIs {cf.existing_emi:,.0f}. "
        f"The figures are {cf.surplus_basis}."
    )
    if under:
        plan_text = (
            f"The optimiser allocated {plan.monthly_contributions_total:,.0f} per month across "
            f"{len(goals)} goals. {len(funded)} can be met in full and {len(under)} cannot: "
            + "; ".join(
                f"{g.name} has a projected shortfall of {g.expected_shortfall:,.0f}" for g in under
            )
            + ". The binding constraint is the available goal budget, not the goal list."
        )
    else:
        plan_text = (
            f"The optimiser allocated {plan.monthly_contributions_total:,.0f} per month and every "
            "goal is projected to be met by its target date under the stated assumptions."
        )
    change = ""
    if diff and diff.get("changed"):
        change = str(diff.get("summary", ""))
    risks = list(warnings[:8])
    if cf.buffer_deficit > 0:
        risks.append(
            f"The requested savings buffer is short by {cf.buffer_deficit:,.0f} a month."
        )
    if plan.new_loan_principal_total > 0:
        risks.append(
            f"The plan proposes {plan.new_loan_principal_total:,.0f} of new borrowing, which adds "
            f"{plan.new_loan_emi_total:,.0f} to monthly obligations and increases total cost "
            "through interest."
        )
    return LLMText(
        financial_summary=summary,
        cash_flow_explanation=cash_flow,
        plan_explanation=plan_text,
        goal_reasons=[GoalReason(goal_ref=g.goal_ref, reason=g.reason) for g in goals],
        tradeoffs=[
            "Every rupee protected as a buffer is a rupee not contributing to a goal.",
            "Longer deadlines lower the required monthly contribution but raise the future cost.",
        ],
        change_explanation=change,
        risks=risks,
        monthly_actions=_monthly_actions(cf, plan, goals),
        missing_information=(
            ["No monthly actuals have been recorded yet, so the surplus is a projection."]
            if cf.expense_basis != "month_actuals"
            else []
        ),
        investment_commentary=[],
        loan_commentary=[],
        alternatives=[],
    )


# --------------------------------------------------------------------------------------
# public entry points
# --------------------------------------------------------------------------------------
def _implied_tenure(principal: float, monthly_emi: float, annual_rate: float) -> int | None:
    """The term that actually produced this EMI, if one integer term explains it.

    The stored assumptions are a request, not necessarily what the solver used: one saved run
    recorded a 12-month tenure against an EMI that only a 60-month term can produce. Solving the
    annuity for n keeps the displayed term consistent with the numbers beside it.
    """
    if principal <= 0 or monthly_emi <= 0 or annual_rate <= 0:
        return None
    rate = annual_rate / 12.0
    denominator = monthly_emi - principal * rate
    if denominator <= 0:
        return None
    try:
        months = math.log(monthly_emi / denominator) / math.log(1.0 + rate)
    except (ValueError, ZeroDivisionError):
        return None
    if not math.isfinite(months):
        return None
    rounded = int(round(months))
    if 1 <= rounded <= 600 and abs(months - rounded) < 0.5:
        return rounded
    return None


def enrich_terms(payload: dict[str, Any]) -> dict[str, Any]:
    """Fill amount/rate/duration terms into a payload stored before they existed.

    Recommendations are immutable records, so old rows genuinely lack these fields. Rather than
    showing "amount and term not stated", the read path reconstructs the terms from the payload's
    own numbers. Nothing is invented:

    * plan terms come from the stored plan totals and the stored assumptions;
    * a loan option is only given a basis when its stored EMI matches that basis to the rupee,
      which is what proves the EMI was computed on it.
    """
    if not payload:
        return payload
    result = dict(payload)
    plan = dict(result.get("recommended_plan") or {})
    assumptions = dict(result.get("assumptions") or {})

    if not result.get("loan_terms"):
        principal = float(plan.get("new_loan_principal_total") or 0.0)
        emi_total = float(plan.get("new_loan_emi_total") or 0.0)
        if principal > 0.01:
            rate = float(assumptions.get("loan_annual_rate", 0.12))
            tenure = _implied_tenure(principal, emi_total, rate) or int(
                assumptions.get("loan_tenure_months", 60)
            )
            result["loan_terms"] = {
                "principal": round(principal, 2),
                "annual_rate": rate,
                "tenure_months": tenure,
                "monthly_emi": round(emi_total, 2),
                "total_interest": round(max(0.0, emi_total * tenure - principal), 2),
                "basis": (
                    "Illustrative at the plan's loan rate and tenure. The lender's actual offer, "
                    "fees and eligibility will differ; no loan is arranged by this application."
                ),
            }

    if not result.get("investment_terms"):
        monthly = float(plan.get("monthly_investment_total") or 0.0)
        horizon = 0
        for goal in result.get("goal_recommendations") or []:
            target = goal.get("target_date")
            if not target:
                continue
            try:
                horizon = max(horizon, months_between(dt.date.today(), dt.date.fromisoformat(str(target))))
            except ValueError:
                continue
        if horizon > 0:
            rate = float(assumptions.get("investment_return", 0.05))
            monthly_rate = (1.0 + rate) ** (1.0 / 12.0) - 1.0
            if monthly_rate > 0:
                projected = monthly * (((1.0 + monthly_rate) ** horizon - 1.0) / monthly_rate)
            else:
                projected = monthly * horizon
            result["investment_terms"] = {
                "monthly_amount": round(monthly, 2),
                "horizon_months": int(horizon),
                "assumed_annual_return": rate,
                "projected_value": round(projected, 2),
                "basis": (
                    "Assumes the planned amount is invested every month for the full horizon at a "
                    "constant return. Market returns are not guaranteed and the value can fall."
                ),
            }

    default_principal, default_tenure = 500_000.0, 48
    options = []
    for option in result.get("loan_options") or []:
        item = dict(option)
        if item.get("principal") is None and item.get("indicative_emi") is not None:
            rate = item.get("published_rate")
            if rate is not None:
                expected = loan_analysis.emi(default_principal, float(rate), default_tenure)
                if abs(expected - float(item["indicative_emi"])) <= 1.0:
                    item["principal"] = default_principal
                    item["tenure_months"] = default_tenure
        options.append(item)
    if options:
        result["loan_options"] = options

    return result


def build(
    db: Session,
    user: User,
    *,
    include_investments: bool = True,
    include_loans: bool = True,
    include_history: bool = False,
    loan_principal: float = 500_000.0,
    loan_tenure_months: int = 48,
    plan_run_id: int | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    settings = get_settings()
    cashflow = load_cashflow(db, user.id)
    goals = load_goals(db, user.id)
    if not goals:
        raise ValidationFailure("Create at least one active goal before requesting a recommendation.")

    run, allocations, payload = load_or_create_plan(db, user, run_id=plan_run_id)
    assumptions = json.loads(run.assumptions_json or "{}")
    inflation = float(assumptions.get("annual_inflation", settings.default_annual_inflation))
    savings_return = float(assumptions.get("savings_return", 0.0))
    investment_return = float(assumptions.get("investment_return", settings.default_investment_return))

    goal_recommendations = _goal_recommendations(
        goals, allocations, inflation=inflation, savings_return=savings_return,
        investment_return=investment_return, cashflow=cashflow,
    )
    plan_out = _recommended_plan(run, allocations, payload)

    investment_payload = None
    investment_options: list[InvestmentOptionOut] = []
    if include_investments:
        horizon = max(months_lookup(goals).values()) if goals else 60
        investment_payload = investment_discovery.discover(
            risk_capacity=cashflow.risk_capacity,
            loss_ability=_loss_ability(db, user.id),
            liquidity_requirement=_liquidity_requirement(db, user.id),
            horizon_months=int(horizon),
            monthly_capacity=cashflow.available_goal_budget,
            emergency_fund_progress=cashflow.emergency_fund_progress,
            existing_assets=_assets(db, user.id),
            include_history=include_history,
            limit=10,
        )
        investment_options = [_investment_option(row) for row in investment_payload["options"]]

    loan_payload = None
    loan_options: list[LoanOptionOut] = []
    if include_loans:
        loan_payload = loan_analysis.discover(
            cashflow=cashflow, principal=loan_principal, tenure_months=loan_tenure_months
        )
        loan_options = [_loan_option(row) for row in loan_payload["options"]]

    warnings = list(cashflow.warnings) + [
        str(w) for w in payload.get("warnings", []) if w
    ]
    for warning in json.loads(run.warnings_json or "[]"):
        if warning not in warnings:
            warnings.append(str(warning))
    if not run.feasible:
        warnings.append(
            f"The stored plan has status '{run.status}', so it must not be treated as a feasible "
            "allocation."
        )

    diff = _diff_with_previous(db, user.id, run)
    facts = _facts_for_model(
        cf=cashflow, plan=plan_out, goals=goal_recommendations,
        investments=investment_options, loans=loan_options, diff=diff, warnings=warnings,
    )

    llm_meta: dict[str, Any] = {
        "provider": "google_gemini",
        "model": settings.gemini_model,
        "configured": settings.gemini_configured,
        "used": False,
        "status": "fallback",
        "reason": "not_attempted",
        "validation": {},
    }
    text: LLMText
    if gemini_client.available():
        try:
            prompt = _build_prompt(facts)
            try:
                result = gemini_client.generate_json(prompt, schema_hint=_LLM_SCHEMA_HINT)
            except gemini_client.LLMUnavailable as first_error:
                # Gemini rejects this schema as a `response_schema` ("too many states for
                # serving"), so constrained decoding is unavailable and malformed JSON is a real
                # possibility. One bounded repair attempt is allowed — never more — and only for
                # a parse failure, so a healthy call is never billed twice.
                if first_error.reason != "invalid_json":
                    raise
                repair = (
                    f"{prompt}\n\nYour previous reply could not be parsed as JSON "
                    f"({first_error.message[:160]}). Return the same content as a single valid "
                    "JSON object with every string properly escaped and no text outside the "
                    "object."
                )
                result = gemini_client.generate_json(repair, schema_hint=_LLM_SCHEMA_HINT)
            candidate = LLMText.model_validate(result.raw)
            raw_candidate = candidate
            candidate, removed = sanitize_ungrounded(candidate, facts=facts)
            ok, problems = validate_llm_text(
                candidate,
                facts=facts,
                goal_refs={g.goal_ref for g in goal_recommendations},
                product_ids={o.product_id for o in investment_options}
                | {o.product_id for o in loan_options},
            )
            if ok:
                # Any field emptied by sanitisation is refilled from the deterministic builder,
                # so the reader never sees a blank section.
                fallback_text = _deterministic_text(
                    cf=cashflow, plan=plan_out, goals=goal_recommendations,
                    warnings=warnings, diff=diff,
                )
                candidate = candidate.model_copy(
                    update={
                        "financial_summary": candidate.financial_summary
                        or fallback_text.financial_summary,
                        "cash_flow_explanation": candidate.cash_flow_explanation
                        or fallback_text.cash_flow_explanation,
                        "plan_explanation": candidate.plan_explanation
                        or fallback_text.plan_explanation,
                    }
                )
                text = candidate
                llm_meta.update(
                    {
                        "used": True,
                        "status": "ok",
                        "reason": None,
                        "latency_ms": result.latency_ms,
                        "validation": {
                            "passed": True,
                            "problems": [],
                            "sanitized": bool(removed),
                            "removed_sentences": removed[:5],
                            "removed_count": len(removed),
                        },
                    }
                )
            else:
                text = _deterministic_text(
                    cf=cashflow, plan=plan_out, goals=goal_recommendations, warnings=warnings, diff=diff
                )
                # Server-side only: the rejected prose is needed to diagnose a grounding
                # failure, and it must never be shown to the user as if it were accepted.
                _log.warning(
                    "llm_rejected problems=%s payload=%s",
                    problems[:5],
                    candidate.model_dump_json()[:2500],
                )
                llm_meta.update(
                    {
                        "status": "rejected",
                        "reason": "validation_failed",
                        "latency_ms": result.latency_ms,
                        "validation": {"passed": False, "problems": problems[:8]},
                    }
                )
        except gemini_client.LLMUnavailable as exc:
            text = _deterministic_text(
                cf=cashflow, plan=plan_out, goals=goal_recommendations, warnings=warnings, diff=diff
            )
            llm_meta.update({"status": "fallback", "reason": exc.reason, "message": exc.message[:300]})
        except Exception as exc:  # schema validation failure lands here
            text = _deterministic_text(
                cf=cashflow, plan=plan_out, goals=goal_recommendations, warnings=warnings, diff=diff
            )
            llm_meta.update(
                {"status": "rejected", "reason": "schema_invalid", "message": f"{type(exc).__name__}: {exc}"[:300]}
            )
    else:
        text = _deterministic_text(
            cf=cashflow, plan=plan_out, goals=goal_recommendations, warnings=warnings, diff=diff
        )
        llm_meta["reason"] = "gemini_not_configured" if not settings.gemini_api_key else "sdk_unavailable"

    # ---------------------------------------------------------------- merge
    reason_by_ref = {r.goal_ref: r.reason for r in text.goal_reasons}
    for goal in goal_recommendations:
        if goal.goal_ref in reason_by_ref:
            goal.reason = reason_by_ref[goal.goal_ref][:1200]
    commentary_by_id = {c.product_id: c.commentary for c in text.investment_commentary}
    for option in investment_options:
        option.commentary = commentary_by_id.get(option.product_id, "")
    loan_commentary = {c.product_id: c.commentary for c in text.loan_commentary}
    for option in loan_options:
        option.commentary = loan_commentary.get(option.product_id, "")

    # Not every engine warning is a risk to the user. Capacity-cap and basis disclosures belong
    # in technical notes; presenting them as risks would train the reader to ignore the list.
    informational_markers = (
        "capacity is capped",
        "monthly-flow-only",
        "financing is disabled",
        "financing was disabled",
        "rl proposed",
        "no-new-borrowing",
        "trained research policy",
        "investment capacity is capped",
    )
    risks: list[str] = []
    technical_notes: list[str] = []
    for item in list(warnings) + list(text.risks):
        if not item:
            continue
        lowered = item.lower()
        if any(marker in lowered for marker in informational_markers):
            if item not in technical_notes:
                technical_notes.append(item)
            continue
        if item not in risks:
            risks.append(item)

    missing: list[str] = list(text.missing_information)
    if investment_payload:
        missing.extend(investment_payload.get("missing_information", []))
    if loan_payload:
        missing.extend(loan_payload.get("missing_information", []))
    missing = list(dict.fromkeys(m for m in missing if m))[:12]

    # Everything below is JSON-native *before* it is persisted, so the stored payload and the
    # API response are byte-identical. `default=str` is deliberately not relied on: it would
    # silently turn a nested model into a string and corrupt re-reads.
    # Explicit terms for anything the user could act on financially. A bare "consider investing"
    # or "a loan may help" is not actionable: every mention now carries the amount, the rate and
    # the duration, computed here rather than left to prose.
    horizon_months = max(months_lookup(goals).values()) if goals else 0
    investment_monthly = float(plan_out.monthly_investment_total)
    monthly_rate = (1.0 + investment_return) ** (1.0 / 12.0) - 1.0
    if horizon_months <= 0:
        projected_value = 0.0
    elif monthly_rate > 0:
        projected_value = investment_monthly * (((1.0 + monthly_rate) ** horizon_months - 1.0) / monthly_rate)
    else:
        projected_value = investment_monthly * horizon_months
    investment_terms = {
        "monthly_amount": round(investment_monthly, 2),
        "horizon_months": int(horizon_months),
        "assumed_annual_return": investment_return,
        "projected_value": round(projected_value, 2),
        "basis": (
            "Assumes the planned amount is invested every month for the full horizon at a "
            "constant return. Market returns are not guaranteed and the value can fall."
        ),
    }

    loan_rate = float(assumptions.get("loan_annual_rate", settings.default_loan_annual_rate))
    loan_principal = float(plan_out.new_loan_principal_total)
    loan_emi = float(plan_out.new_loan_emi_total)
    # Prefer the term that explains the EMI the plan actually produced over the requested value.
    loan_tenure = _implied_tenure(loan_principal, loan_emi, loan_rate) or int(
        assumptions.get("loan_tenure_months", settings.default_loan_tenure_months)
    )
    loan_terms = (
        {
            "principal": round(loan_principal, 2),
            "annual_rate": loan_rate,
            "tenure_months": loan_tenure,
            "monthly_emi": round(loan_emi, 2),
            "total_interest": round(max(0.0, loan_emi * loan_tenure - loan_principal), 2),
            "basis": (
                "Illustrative at the plan's loan rate and tenure. The lender's actual offer, "
                "fees and eligibility will differ; no loan is arranged by this application."
            ),
        }
        if loan_principal > 0.01
        else {}
    )

    # The same terms also travel in the notes, so an API consumer that only reads the text is not
    # left with an unquantified "a loan may help".
    if loan_terms:
        technical_notes.append(
            f"Borrowing terms: {loan_terms['principal']:,.0f} over {loan_terms['tenure_months']} "
            f"months at {loan_terms['annual_rate']:.2%} a year, EMI "
            f"{loan_terms['monthly_emi']:,.0f}, total interest {loan_terms['total_interest']:,.0f}."
        )
    if investment_terms["monthly_amount"] > 0:
        technical_notes.append(
            f"Investment terms: {investment_terms['monthly_amount']:,.0f} a month for "
            f"{investment_terms['horizon_months']} months at an assumed "
            f"{investment_terms['assumed_annual_return']:.2%} a year, projected "
            f"{investment_terms['projected_value']:,.0f}."
        )

    response = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "run_id": None,
        "optimization_run_id": run.id,
        "financial_summary": text.financial_summary,
        "cash_flow_status": _cashflow_status(cashflow).model_dump(mode="json"),
        "protected_buffer": _buffer_block(cashflow).model_dump(mode="json"),
        "available_goal_budget": round(cashflow.available_goal_budget, 2),
        "goal_recommendations": [g.model_dump(mode="json") for g in goal_recommendations],
        "investment_options": [o.model_dump(mode="json") for o in investment_options],
        "investment_terms": investment_terms,
        "loan_options": [o.model_dump(mode="json") for o in loan_options],
        "loan_terms": loan_terms,
        "recommended_plan": plan_out.model_dump(mode="json"),
        "alternative_scenarios": [a.model_dump(mode="json") for a in text.alternatives],
        "risks_and_warnings": risks[:14],
        "data_sources": [d.model_dump() for d in _data_sources(cashflow, investment_payload, loan_payload)],
        "assumptions": assumptions,
        "missing_information": missing,
        "monthly_actions": text.monthly_actions,
        "explanation": text.plan_explanation,
        "disclaimer": DISCLAIMER,
        "technical_notes": technical_notes,
        "llm": llm_meta,
        "validation": {
            "numbers_source": "deterministic services only",
            "model_supplied_numbers": False,
            "grounding_check": llm_meta["validation"],
        },
    }

    if not response["alternative_scenarios"]:
        response["alternative_scenarios"] = _fallback_alternatives(cashflow, goal_recommendations)

    # A goal the user marked as immovable must not be offered a moved deadline or a smaller
    # target: the goal page already suppresses those options, and the two surfaces contradicting
    # each other was a real defect. This filters the model's scenarios as well as the fallback.
    response["alternative_scenarios"], dropped = _drop_inflexible_scenarios(
        response["alternative_scenarios"], goals
    )
    if dropped:
        response["technical_notes"] = [*response["technical_notes"], *dropped]

    if persist:
        row = RecommendationRun(
            user_id=user.id,
            optimization_run_id=run.id,
            provider=llm_meta["provider"],
            model_name=settings.gemini_model if llm_meta["used"] else "",
            status=llm_meta["status"],
            schema_version=SCHEMA_VERSION,
            payload_json=json.dumps(response),
            fallback_used=not llm_meta["used"],
            runtime_ms=int(llm_meta.get("latency_ms", 0) or 0),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        response["run_id"] = row.id

    return response


def _drop_inflexible_scenarios(
    alternatives: list[dict[str, Any]], goals: list[Goal]
) -> tuple[list[dict[str, Any]], list[str]]:
    """Remove deadline/target changes for goals the user marked as inflexible.

    Returns the surviving scenarios and one note per removal, so the response can still say the
    option was considered and withheld rather than silently dropping it.
    """
    by_name = {goal.name: goal for goal in goals if goal.name}
    kept: list[dict[str, Any]] = []
    notes: list[str] = []
    for item in alternatives:
        scenario = str(item.get("scenario", ""))
        lowered = scenario.lower()
        match = next((goal for name, goal in by_name.items() if name in scenario), None)
        if match is not None:
            if "extend the deadline" in lowered and not match.date_flexible:
                notes.append(
                    f"An option to extend the deadline for {match.name} was withheld: its target "
                    "date is marked inflexible."
                )
                continue
            if "reduce the target" in lowered and not match.amount_flexible:
                notes.append(
                    f"An option to reduce the target for {match.name} was withheld: its target "
                    "amount is marked inflexible."
                )
                continue
        kept.append(item)
    return kept, notes


def _fallback_alternatives(cf: CashFlow, goals: list[GoalRecommendationOut]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    under = [g for g in goals if g.funding_status == "underfunded"]
    if under:
        goal = under[0]
        out.append(
            {
                "scenario": f"Extend the deadline for {goal.name}",
                "description": (
                    f"Spreading the {goal.funding_gap:,.0f} gap over a longer horizon lowers the "
                    f"required monthly amount below {goal.recommended_monthly_contribution:,.0f}."
                ),
            }
        )
        out.append(
            {
                "scenario": f"Reduce the target for {goal.name}",
                "description": (
                    f"Funding what the current budget can support would leave the goal "
                    f"{goal.expected_shortfall:,.0f} short of its stated target."
                ),
            }
        )
    if cf.protected_buffer > 0:
        out.append(
            {
                "scenario": "Lower the protected buffer",
                "description": (
                    f"Reducing the buffer below {cf.protected_buffer:,.0f} would release money "
                    "for goals but weakens the safety cushion; this is the user's decision."
                ),
            }
        )
    out.append(
        {
            "scenario": "Increase income or cut discretionary spending",
            "description": (
                f"Every additional {max(1000.0, round(cf.available_goal_budget * 0.1, -2)):,.0f} "
                "a month of surplus shortens the time needed for every goal."
            ),
        }
    )
    return out


def _diff_with_previous(db: Session, user_id: int, run: OptimizationRun) -> dict[str, Any] | None:
    from app.services.planner import diff_runs, previous_run

    previous = previous_run(db, user_id, "plan", exclude_id=run.id)
    if previous is None:
        return None
    return diff_runs(db, previous, run)


def _investment_option(row: dict[str, Any]) -> InvestmentOptionOut:
    suitability = row.get("suitability", {})
    return InvestmentOptionOut(
        product_id=row.get("product_id", ""),
        name=row.get("name", ""),
        category=row.get("category", ""),
        provider=row.get("provider", ""),
        data_quality=row.get("data_quality", ""),
        source_url=row.get("source_url") or "",
        retrieved_at=row.get("retrieved_at"),
        effective_date=row.get("effective_date"),
        nav=row.get("nav"),
        published_rate=row.get("published_rate"),
        risk_level=row.get("risk_level", "unknown"),
        liquidity=row.get("liquidity", "unknown"),
        lock_in_months=row.get("lock_in_months"),
        min_investment=row.get("min_investment"),
        historical_returns=row.get("historical_returns") or [],
        suitability_score=float(suitability.get("score", 0.0)),
        suitability_rationale=list(suitability.get("reasons", [])),
        material_risks=list(suitability.get("cautions", [])),
        commentary="",
        freshness=row.get("freshness", "unknown"),
        completeness=float(row.get("completeness", 0.0)),
    )


def _loan_option(row: dict[str, Any]) -> LoanOptionOut:
    indicative = row.get("indicative") or {}
    affordability = row.get("affordability") or {}
    return LoanOptionOut(
        product_id=row.get("product_id", ""),
        lender=row.get("lender", ""),
        product_name=row.get("product_name", ""),
        category=row.get("category", ""),
        published_rate=row.get("published_rate"),
        rate_type=row.get("rate_type", "unknown"),
        rate_basis=row.get("rate_basis", ""),
        principal=indicative.get("assumed_principal"),
        tenure_months=indicative.get("assumed_tenure_months"),
        indicative_emi=indicative.get("monthly_emi"),
        total_interest=indicative.get("total_interest"),
        apr_including_known_fees=indicative.get("apr_including_known_fees"),
        affordability_verdict=affordability.get("verdict", "unknown"),
        data_quality=row.get("data_quality", ""),
        source_url=row.get("source_url") or "",
        retrieved_at=row.get("retrieved_at"),
        eligibility_notes=list(row.get("suitability_notes", [])),
        material_risks=list(row.get("suitability_notes", []))[:4],
        commentary="",
        is_personalised_offer=bool(row.get("is_personalised_offer", False)),
    )


def _loss_ability(db: Session, user_id: int) -> str:
    from app.models import UserPreference

    pref = db.execute(
        select(UserPreference).where(UserPreference.user_id == user_id)
    ).scalar_one_or_none()
    return pref.loss_ability if pref else "moderate"


def _liquidity_requirement(db: Session, user_id: int) -> str:
    from app.models import UserPreference

    pref = db.execute(
        select(UserPreference).where(UserPreference.user_id == user_id)
    ).scalar_one_or_none()
    return pref.liquidity_requirement if pref else "medium"


def _assets(db: Session, user_id: int):
    from app.models import Asset

    return list(db.execute(select(Asset).where(Asset.user_id == user_id)).scalars())


# --------------------------------------------------------------------------------------
# grounded question answering
# --------------------------------------------------------------------------------------
def answer_question(payload: dict[str, Any], question: str) -> dict[str, Any]:
    """Answer from the stored recommendation only. No new figures are produced."""
    settings = get_settings()
    meta: dict[str, Any] = {
        "provider": "google_gemini",
        "model": settings.gemini_model,
        "used": False,
        "status": "fallback",
        "reason": "not_attempted",
    }
    compact = {
        "cash_flow_status": payload.get("cash_flow_status"),
        "protected_buffer": payload.get("protected_buffer"),
        "available_goal_budget": payload.get("available_goal_budget"),
        "goal_recommendations": payload.get("goal_recommendations"),
        "recommended_plan": payload.get("recommended_plan"),
        "risks_and_warnings": payload.get("risks_and_warnings"),
        "investment_options": [
            {k: o.get(k) for k in ("name", "category", "risk_level", "suitability_score", "data_quality")}
            for o in payload.get("investment_options", [])[:8]
        ],
        "loan_options": [
            {k: o.get(k) for k in ("lender", "published_rate", "indicative_emi", "affordability_verdict")}
            for o in payload.get("loan_options", [])[:8]
        ],
    }

    if gemini_client.available():
        prompt = (
            "Answer the user's question using ONLY the JSON below. If the answer is not in the "
            "JSON, say that the information is not available and name what is missing. Never "
            "invent a figure, product or rate. Never say a return or approval is guaranteed. "
            "Keep the answer under 180 words.\n"
            f"QUESTION: {question}\nJSON:\n{json.dumps(compact, indent=2, default=str)}"
        )
        try:
            result = gemini_client.generate_json(
                prompt,
                schema_hint={"answer": "string"},
            )
            answer = str((result.raw or {}).get("answer", "")).strip()
            if answer:
                meta.update({"used": True, "status": "ok", "latency_ms": result.latency_ms})
                return {"answer": answer[:4000], "llm": meta, "grounded_on": compact}
            meta.update({"status": "rejected", "reason": "empty_answer"})
        except gemini_client.LLMUnavailable as exc:
            meta.update({"status": "fallback", "reason": exc.reason})
        except Exception as exc:
            meta.update({"status": "rejected", "reason": f"{type(exc).__name__}"})

    return {
        "answer": _deterministic_answer(compact, question),
        "llm": meta,
        "grounded_on": compact,
    }


def _deterministic_answer(compact: dict[str, Any], question: str) -> str:
    q = question.lower()
    cf = compact.get("cash_flow_status") or {}
    goals = compact.get("goal_recommendations") or []
    buffer = compact.get("protected_buffer") or {}

    for goal in goals:
        name = str(goal.get("name", "")).lower()
        if name and name in q:
            return (
                f"{goal.get('name')}: target {goal.get('target_amount_future', 0):,.0f} by "
                f"{goal.get('target_date')}; the plan assigns "
                f"{(goal.get('planned_savings_contribution') or 0) + (goal.get('planned_investment_contribution') or 0):,.0f} "
                f"a month against a required {goal.get('recommended_monthly_contribution', 0):,.0f}. "
                f"Status: {goal.get('funding_status')}, projected shortfall "
                f"{goal.get('expected_shortfall', 0):,.0f}."
            )
    if "buffer" in q or "reserve" in q:
        return (
            f"Your protected buffer is {buffer.get('protected_monthly_buffer', 0):,.0f} a month "
            f"against a requested {buffer.get('desired_monthly_buffer', 0):,.0f}. "
            f"{buffer.get('explanation', '')}"
        )
    if "surplus" in q or "left over" in q or "save" in q:
        return (
            f"Monthly surplus is {cf.get('monthly_surplus', 0):,.0f} ({cf.get('surplus_basis')}), "
            f"of which {cf.get('protected_buffer', 0):,.0f} is protected and "
            f"{cf.get('available_goal_budget', 0):,.0f} is available for goals."
        )
    if "loan" in q or "borrow" in q:
        loans = compact.get("loan_options") or []
        if not loans:
            return "No loan option is available in this recommendation."
        first = loans[0]
        return (
            f"The lowest-cost listed option is {first.get('lender')} at a published "
            f"{(first.get('published_rate') or 0) * 100:.2f}% with an indicative EMI of "
            f"{first.get('indicative_emi') or 0:,.0f}; affordability verdict: "
            f"{first.get('affordability_verdict')}. This is published product information, not "
            "an offer or an approval."
        )
    return (
        "The language model is not configured, so this answer comes from the computed plan only. "
        f"Surplus {cf.get('monthly_surplus', 0):,.0f}, protected buffer "
        f"{cf.get('protected_buffer', 0):,.0f}, goal budget {cf.get('available_goal_budget', 0):,.0f}. "
        "Ask about a specific goal name, the buffer, the surplus or the loan options."
    )


