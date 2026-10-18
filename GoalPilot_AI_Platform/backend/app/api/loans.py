"""Loan discovery and financing analysis endpoints.

This module is deliberately separate from the optimiser. The optimiser may propose a loan as a
funding mechanism; this module answers "what do published products cost, and can the household
carry one?" — and neither path can originate, approve or execute a loan.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.deps import current_user
from app.db import get_db
from app.models import User
from app.providers import registry
from app.providers.base import RATE_CLASS_LABELS
from app.schemas.common import ApiModel
from app.services import loan_analysis
from app.services.planner import load_cashflow

router = APIRouter(prefix="/loans", tags=["loans"])


class QuoteInput(ApiModel):
    label: str = Field(default="", max_length=120)
    lender: str | None = Field(default=None, max_length=120)
    principal: float = Field(gt=0, le=100_000_000)
    annual_rate: float = Field(ge=0, le=1)
    tenure_months: int = Field(ge=1, le=600)
    rate_type: str = Field(default="fixed", pattern="^(fixed|floating|hybrid|unknown)$")
    processing_fee_pct: float | None = Field(default=None, ge=0, le=0.2)
    processing_fee_flat: float = Field(default=0, ge=0)
    other_fees: float = Field(default=0, ge=0)
    goal_gap: float | None = Field(default=None, ge=0)
    months_remaining: int | None = Field(default=None, ge=0, le=600)
    include_schedule: bool = False
    #: Set true only when the entered rate is an offer actually made to this user. Otherwise
    #: the analysis is labelled an estimated scenario.
    offer_is_personal: bool = False


class CompareRequest(ApiModel):
    quotes: list[QuoteInput] = Field(min_length=1, max_length=10)


@router.get("/discover")
def discover(
    principal: float = Query(default=500_000, gt=0, le=100_000_000),
    tenure_months: int = Query(default=48, ge=1, le=600),
    category: list[str] | None = Query(default=None),
    scenario_rate: float | None = Query(
        default=None,
        ge=0.0,
        le=0.5,
        description=(
            "Rate for categories with no published product. Labelled as an estimated scenario; "
            "never reported as a published or personalised rate."
        ),
    ),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    cashflow = load_cashflow(db, user.id)
    return loan_analysis.discover(
        cashflow=cashflow,
        principal=principal,
        tenure_months=tenure_months,
        categories=category,
        scenario_rate=scenario_rate,
    )


@router.post("/analyse")
def analyse(payload: QuoteInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    cashflow = load_cashflow(db, user.id)
    return loan_analysis.quote_from_inputs(payload.model_dump(), cashflow)


@router.post("/compare")
def compare(payload: CompareRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    cashflow = load_cashflow(db, user.id)
    rows = loan_analysis.compare_quotes([q.model_dump() for q in payload.quotes], cashflow)
    return {
        "quotes": rows,
        "ranking_rule": (
            "Ranked by total cost of credit (interest + fees entered), not by headline rate. A "
            "lower advertised rate with a large fee can cost more."
        ),
        "affordability_context": {
            "available_goal_budget": round(cashflow.available_goal_budget, 2),
            "protected_buffer": round(cashflow.protected_buffer, 2),
        },
        "disclosure": loan_analysis.DISCLOSURE,
    }


@router.get("/providers")
def providers():
    settings = get_settings()
    return {
        "providers": registry.status_table(),
        "live_retrieval_enabled": settings.enable_live_providers,
        "supported_categories": ["personal", "education", "home", "vehicle", "secured", "other"],
        "integration_status": (
            "Published lender pages are read live where the page can be parsed; otherwise the "
            "bundled published-rate snapshot is served and labelled. No authorised loan "
            "aggregator API is integrated, and no personalised offer is claimed."
        ),
        "rate_classes": RATE_CLASS_LABELS,
        "credential_free": True,
        "credential_note": (
            "Every loan feature — discovery, EMI and total repayment, affordability, "
            "floating-rate sensitivity, save-versus-borrow — runs with no external API "
            "credentials. The only optional credential in the platform is GEMINI_API_KEY, used "
            "for prose, not for lending data."
        ),
    }


@router.get("/methodology")
def methodology():
    return {
        "emi": "P x r x (1+r)^n / ((1+r)^n - 1), r = annual rate / 12, end-of-month payments",
        "apr": "IRR over net proceeds and the EMI stream, annualised as (1+i)^12 - 1",
        "affordability_checks": [
            "EMI within the remaining EMI-to-income ceiling",
            "EMI within the available goal budget (after the protected buffer)",
            "EMI within half of that budget",
            "protected buffer still funded",
            "emergency fund at least 50% of the guideline",
            "no existing monthly deficit",
        ],
        "sensitivity": "EMI and total interest recomputed at +0, +100, +200 and +300 basis points",
        "hard_rules": [
            "Loan proceeds are never treated as income.",
            "An advertised rate is never presented as a personalised offer.",
            "Eligibility is never asserted.",
            "Borrowing is never recommended merely because it makes a goal achievable now.",
        ],
    }
