"""Structured recommendation endpoints (Gemini explanation + deterministic fallback)."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.deps import current_user, enforce_optimize_rate_limit
from app.core.errors import NotFoundError, ValidationFailure
from app.db import get_db
from app.llm import gemini_client
from app.models import RecommendationRun, User
from app.schemas.recommendations import AskRequest, RecommendationRequest
from app.services import recommendations as service

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.get("/status")
def status():
    settings = get_settings()
    return {
        "llm": gemini_client.status(),
        "fallback_available": True,
        "fallback_note": (
            "When Gemini is not configured, quota-limited or returns ungrounded text, the "
            "recommendation is built entirely from deterministic calculation services. The "
            "response says which one produced it in its 'llm' block."
        ),
        "schema_version": service.SCHEMA_VERSION,
        "model_config": {
            "env_var": "GEMINI_API_KEY",
            "model_env_var": "GOALPILOT_GEMINI_MODEL",
            "current_model": settings.gemini_model,
            "enabled": settings.llm_enabled,
        },
    }


@router.post("/generate", dependencies=[Depends(enforce_optimize_rate_limit)])
def generate(
    payload: RecommendationRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return service.build(
        db,
        user,
        include_investments=payload.include_investments,
        include_loans=payload.include_loans,
        include_history=payload.include_history,
        loan_principal=payload.loan_principal,
        loan_tenure_months=payload.loan_tenure_months,
        persist=payload.persist,
    )


@router.get("/latest")
def latest(user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = db.execute(
        select(RecommendationRun)
        .where(RecommendationRun.user_id == user.id)
        .order_by(RecommendationRun.created_at.desc(), RecommendationRun.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError("No recommendation has been generated yet.")
    payload = json.loads(row.payload_json or "{}")
    payload["run_id"] = row.id
    payload["stored_status"] = row.status
    payload["stored_model"] = row.model_name
    # Recommendations stored before the terms existed keep working: amounts, rates and durations
    # are reconstructed from the payload's own figures, never invented.
    return service.enrich_terms(payload)


@router.get("/history")
def history(
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(RecommendationRun)
        .where(RecommendationRun.user_id == user.id)
        .order_by(RecommendationRun.created_at.desc(), RecommendationRun.id.desc())
        .limit(limit)
    ).scalars().all()
    return {
        "items": [
            {
                "id": r.id,
                "optimization_run_id": r.optimization_run_id,
                "provider": r.provider,
                "model_name": r.model_name,
                "status": r.status,
                "fallback_used": r.fallback_used,
                "schema_version": r.schema_version,
                "runtime_ms": r.runtime_ms,
                "created_at": r.created_at,
            }
            for r in rows
        ],
        "limit": limit,
    }


@router.get("/{run_id}")
def read(run_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = db.execute(
        select(RecommendationRun).where(
            RecommendationRun.id == run_id, RecommendationRun.user_id == user.id
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError(f"Recommendation {run_id} was not found")
    payload = json.loads(row.payload_json or "{}")
    payload["run_id"] = row.id
    payload["stored_status"] = row.status
    payload["stored_model"] = row.model_name
    # Recommendations stored before the terms existed keep working: amounts, rates and durations
    # are reconstructed from the payload's own figures, never invented.
    return service.enrich_terms(payload)


@router.post("/ask")
def ask(payload: AskRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if payload.recommendation_id is not None:
        row = db.execute(
            select(RecommendationRun).where(
                RecommendationRun.id == payload.recommendation_id,
                RecommendationRun.user_id == user.id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise NotFoundError(f"Recommendation {payload.recommendation_id} was not found")
    else:
        row = db.execute(
            select(RecommendationRun)
            .where(RecommendationRun.user_id == user.id)
            .order_by(RecommendationRun.created_at.desc(), RecommendationRun.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        if row is None:
            raise ValidationFailure(
                "Generate a recommendation first; questions are answered only from a stored, "
                "computed plan rather than from general knowledge."
            )
    stored = json.loads(row.payload_json or "{}")
    result = service.answer_question(stored, payload.question)
    return {
        "answer": result["answer"],
        "grounded_on": result["grounded_on"],
        "llm": result["llm"],
        "disclaimer": service.DISCLAIMER,
    }
