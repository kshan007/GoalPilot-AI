"""Investment discovery endpoints.

Discovery is available as soon as a financial profile exists: it does not depend on a plan
having been run, and it does not require an income source, because a user may legitimately want
to look at instruments before their cash flow is complete.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.deps import current_user
from app.core.errors import ValidationFailure
from app.db import get_db
from app.models import User, UserPreference
from app.providers import registry
from app.services import investment_discovery
from app.services.cashflow import build_cashflow
from app.services.planner import (
    get_profile_or_none,
    load_assets,
    load_income_sources,
    load_liabilities,
)

router = APIRouter(prefix="/investments", tags=["investments"])


def _context(db: Session, user: User) -> dict:
    profile = get_profile_or_none(db, user.id)
    if profile is None:
        raise ValidationFailure(
            "Save a financial profile before exploring investment options: risk capacity and "
            "liquidity needs come from that profile."
        )
    pref = db.execute(
        __import__("sqlalchemy").select(UserPreference).where(UserPreference.user_id == user.id)
    ).scalar_one_or_none()
    return {
        "profile": profile,
        "risk_capacity": float(profile.risk_capacity or 0.5),
        "loss_ability": pref.loss_ability if pref else "moderate",
        "liquidity_requirement": pref.liquidity_requirement if pref else "medium",
    }


def _cashflow_block(db: Session, user: User):
    """Best-effort cash flow; discovery still works when it cannot be built."""
    try:
        return build_cashflow(
            income_sources=load_income_sources(db, user.id),
            liabilities=load_liabilities(db, user.id),
            assets=load_assets(db, user.id),
            profile=get_profile_or_none(db, user.id),
        )
    except Exception:
        return None


@router.get("/discover")
def discover(
    horizon_months: int = Query(default=60, ge=1, le=480),
    category: list[str] | None = Query(default=None),
    include_history: bool = Query(default=False),
    limit: int = Query(default=24, ge=1, le=60),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    ctx = _context(db, user)
    cashflow = _cashflow_block(db, user)
    payload = investment_discovery.discover(
        risk_capacity=ctx["risk_capacity"],
        loss_ability=ctx["loss_ability"],
        liquidity_requirement=ctx["liquidity_requirement"],
        horizon_months=horizon_months,
        monthly_capacity=cashflow.available_goal_budget if cashflow else 0.0,
        emergency_fund_progress=cashflow.emergency_fund_progress if cashflow else 0.0,
        existing_assets=load_assets(db, user.id),
        categories=category,
        include_history=include_history,
        limit=limit,
    )
    payload["cash_flow_available"] = cashflow is not None
    if cashflow is not None:
        payload["affordability_context"] = {
            "available_goal_budget": round(cashflow.available_goal_budget, 2),
            "protected_buffer": round(cashflow.protected_buffer, 2),
            "monthly_surplus": round(cashflow.monthly_surplus, 2),
        }
    return payload


@router.get("/providers")
def providers():
    settings = get_settings()
    return {
        "providers": registry.status_table(),
        "live_retrieval_enabled": settings.enable_live_providers,
        "cache_ttl_seconds": settings.provider_cache_ttl_seconds,
        "history_mirror_enabled": settings.enable_mfapi_history,
        "note": (
            "A provider is only reported as returning data after it has actually answered. "
            "Statuses here describe configuration, not a successful fetch."
        ),
    }


@router.post("/refresh")
def refresh(user: User = Depends(current_user)):
    registry.reset_registry()
    return {
        "ok": True,
        "message": (
            "Provider cache cleared. The next discovery request will re-fetch from the live "
            "sources that are enabled."
        ),
    }


@router.get("/methodology")
def methodology():
    settings = get_settings()
    return {
        "selection_rule": (
            "Direct-plan growth schemes only; up to "
            f"{settings.investment_shortlist_per_category} per SEBI category, ordered by AMFI "
            "scheme code. That ordering is arbitrary and is NOT a performance ranking."
        ),
        "scoring": {
            "start": 1.0,
            "risk_above_capacity": "-0.45 x (risk_score - risk_capacity)",
            "short_horizon_penalty": "-0.25 x max(0, risk_score - 0.25) under 36 months; "
            "-0.25 x max(0, risk_score - 0.40) under 60 months",
            "lock_in_vs_liquidity": "-0.15 x (1.0 high need / 0.5 medium / 0.2 low)",
            "lock_in_beyond_horizon": "-0.10",
            "eligibility_not_established": "-0.15",
            "concentration": "-0.05 when the relevant existing bucket already exceeds 60%",
            "clamp": "0.0 to 1.0",
        },
        "what_the_score_is_not": (
            "It is not a risk-profiling instrument, not a return forecast, and not a "
            "recommendation to buy. It measures fit against the constraints this application "
            "records, and nothing else."
        ),
        "returns_policy": (
            "Trailing returns are shown only when a NAV history is available, always with the "
            "exact period and the CAGR convention. Past returns are never presented as expected "
            "future returns."
        ),
        "provenance_classes": [
            "official_live — fetched from the official source for this response",
            "official_snapshot — bundled copy of an official publication with its as-of date",
            "historical — observed history, not a forecast",
            "unofficial_mirror — third-party mirror of official NAV history",
            "category_scenario — a labelled modelling assumption, not a product",
        ],
    }
