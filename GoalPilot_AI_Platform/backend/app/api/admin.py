"""Administrative oversight: platform metrics, run history, accounts, health and audit.

Every route here requires an account with ``is_admin``. The dependency re-reads the flag from the
database on each call, so revoking access takes effect immediately rather than at token expiry.

Deliberate boundaries:

* User financial data is *not* browsable here. Runs expose allocations and solver diagnostics,
  which is what an operator needs to explain a plan; income, assets, liabilities and transactions
  are never returned.
* Values are either measured from stored rows or reported as unavailable. Nothing is estimated to
  make a dashboard look complete.
* Actions that change state are audited with the actor, the target and the before/after values.
"""
from __future__ import annotations

import datetime as dt
import json
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import Field
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.api import meta as meta_api
from app.core.deps import require_admin
from app.core.errors import ValidationFailure
from app.db import get_db
from app.engines import research_loader, rl_engine
from app.models import AdminAuditLog, GoalAllocation, OptimizationRun, User
from app.schemas.common import ApiModel

router = APIRouter(prefix="/admin", tags=["admin"])

FAILED_STATUSES = ("failed", "error", "unavailable", "invalid_plan")


class AdminUserPatch(ApiModel):
    is_admin: bool | None = None
    is_active: bool | None = None


def _audit(
    db: Session,
    actor: User,
    action: str,
    *,
    target_type: str = "",
    target_id: str | int = "",
    details: dict[str, Any] | None = None,
) -> None:
    db.add(
        AdminAuditLog(
            actor_id=actor.id,
            actor_email=actor.email,
            action=action,
            target_type=target_type,
            target_id=str(target_id),
            details_json=json.dumps(details or {}, default=str),
        )
    )


def _page(page: int, page_size: int) -> tuple[int, int]:
    page = max(1, page)
    page_size = min(100, max(1, page_size))
    return (page - 1) * page_size, page_size


def _iso(value: dt.datetime | None) -> str | None:
    return value.isoformat() if value else None


def _seconds_since(value: dt.datetime) -> float:
    """Age of a stored timestamp, whether the database hands it back naive or aware."""
    now = dt.datetime.now(dt.timezone.utc) if value.tzinfo else dt.datetime.utcnow()
    return (now - value).total_seconds()


def _audit_row(row: AdminAuditLog) -> dict[str, Any]:
    try:
        details = json.loads(row.details_json or "{}")
    except json.JSONDecodeError:
        details = {}
    return {
        "id": row.id,
        "created_at": _iso(row.created_at),
        "actor_email": row.actor_email,
        "action": row.action,
        "target_type": row.target_type,
        "target_id": row.target_id,
        "details": details,
    }


@router.get("/overview")
def overview(db: Session = Depends(get_db), admin: User = Depends(require_admin)) -> dict[str, Any]:
    """Counts and recent activity, measured from stored rows only."""
    now = dt.datetime.now(dt.timezone.utc)
    week_ago = now - dt.timedelta(days=7)

    def count(stmt) -> int:
        return int(db.scalar(stmt) or 0)

    users_total = count(select(func.count(User.id)))
    users_active = count(select(func.count(User.id)).where(User.is_active.is_(True)))
    users_admins = count(select(func.count(User.id)).where(User.is_admin.is_(True)))
    users_new = count(select(func.count(User.id)).where(User.created_at >= week_ago))

    runs_total = count(select(func.count(OptimizationRun.id)))
    runs_week = count(
        select(func.count(OptimizationRun.id)).where(OptimizationRun.created_at >= week_ago)
    )

    by_status = {
        str(status): int(total)
        for status, total in db.execute(
            select(OptimizationRun.status, func.count(OptimizationRun.id)).group_by(
                OptimizationRun.status
            )
        )
    }
    by_algorithm = {
        str(algo): int(total)
        for algo, total in db.execute(
            select(OptimizationRun.algorithm, func.count(OptimizationRun.id)).group_by(
                OptimizationRun.algorithm
            )
        )
    }
    by_kind = {
        str(kind): int(total)
        for kind, total in db.execute(
            select(OptimizationRun.kind, func.count(OptimizationRun.id)).group_by(
                OptimizationRun.kind
            )
        )
    }
    avg_runtime = {
        str(algo): round(float(ms or 0), 1)
        for algo, ms in db.execute(
            select(OptimizationRun.algorithm, func.avg(OptimizationRun.runtime_ms)).group_by(
                OptimizationRun.algorithm
            )
        )
    }

    failures = int(
        db.scalar(
            select(func.count(OptimizationRun.id)).where(
                OptimizationRun.status.in_(FAILED_STATUSES)
            )
        )
        or 0
    )

    since = (now - dt.timedelta(days=13)).date().isoformat()
    daily = {str(day): int(total) for day, total in db.execute(
        select(func.date(OptimizationRun.created_at), func.count(OptimizationRun.id))
        .where(OptimizationRun.created_at >= now - dt.timedelta(days=14))
        .group_by(func.date(OptimizationRun.created_at))
    )}
    activity = []
    for offset in range(13, -1, -1):
        day = (now - dt.timedelta(days=offset)).date().isoformat()
        activity.append({"date": day, "runs": daily.get(day, 0)})

    recent_failures = [
        {
            "id": run.id,
            "created_at": _iso(run.created_at),
            "algorithm": run.algorithm,
            "status": run.status,
            "runtime_ms": run.runtime_ms,
            "warnings": _warnings(run),
        }
        for run in db.execute(
            select(OptimizationRun)
            .where(OptimizationRun.status.in_(FAILED_STATUSES))
            .order_by(OptimizationRun.created_at.desc())
            .limit(5)
        ).scalars()
    ]

    recent_audit = [
        _audit_row(row)
        for row in db.execute(
            select(AdminAuditLog).order_by(AdminAuditLog.created_at.desc()).limit(8)
        ).scalars()
    ]

    research = research_loader.status()
    rl = rl_engine.readiness()
    models = [
        {
            "name": "constrained_lp",
            "kind": "lp",
            "status": "ready" if research.available else "unavailable",
        },
        {
            "name": "ppo_recommended_v1",
            "kind": "rl",
            "status": "ready" if rl.get("available") else "unavailable",
            "detail": rl.get("reason") or rl.get("checkpoint"),
        },
        {
            "name": "lp_rl_hybrid",
            "kind": "hybrid",
            "status": "ready" if research.available and rl.get("available") else "degraded",
        },
    ]

    datasets = meta_api.data_provenance()["datasets"]
    return {
        "generated_at": _iso(now),
        "users": {
            "total": users_total,
            "active": users_active,
            "admins": users_admins,
            "new_last_7_days": users_new,
        },
        "runs": {
            "total": runs_total,
            "last_7_days": runs_week,
            "failed": failures,
            "by_status": by_status,
            "by_algorithm": by_algorithm,
            "by_kind": by_kind,
            "avg_runtime_ms_by_algorithm": avg_runtime,
        },
        "activity": activity,
        "recent_failures": recent_failures,
        "recent_audit": recent_audit,
        "models": models,
        "data_sources": [
            {
                "name": item["name"],
                "kind": item["kind"],
                "used_for": item["used_for"],
                "caveat": item["caveat"],
            }
            for item in datasets
        ],
    }


def _warnings(run: OptimizationRun) -> list[str]:
    try:
        parsed = json.loads(run.warnings_json or "[]")
        return [str(item) for item in parsed][:5] if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        return []


@router.get("/runs")
def runs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    algorithm: str | None = None,
    status: str | None = None,
    kind: str | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> dict[str, Any]:
    offset, limit = _page(page, page_size)
    stmt = select(OptimizationRun, User.email).join(User, User.id == OptimizationRun.user_id)
    if algorithm:
        stmt = stmt.where(OptimizationRun.algorithm == algorithm)
    if status:
        stmt = stmt.where(OptimizationRun.status == status)
    if kind:
        stmt = stmt.where(OptimizationRun.kind == kind)
    if search:
        needle = search.strip()
        clauses = [User.email.ilike(f"%{needle}%")]
        if needle.isdigit():
            clauses.append(OptimizationRun.id == int(needle))
        stmt = stmt.where(or_(*clauses))

    total = int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = db.execute(
        stmt.order_by(OptimizationRun.created_at.desc()).offset(offset).limit(limit)
    ).all()

    return {
        "items": [
            {
                "id": run.id,
                "created_at": _iso(run.created_at),
                "user_email": email,
                "algorithm": run.algorithm,
                "kind": run.kind,
                "status": run.status,
                "feasible": run.feasible,
                "runtime_ms": run.runtime_ms,
                "weighted_achievement": float(run.weighted_achievement or 0),
                "total_shortfall": float(run.total_shortfall or 0),
                "model_version": run.model_version,
            }
            for run, email in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, (total + page_size - 1) // page_size),
    }


@router.get("/runs/{run_id}")
def run_detail(
    run_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> dict[str, Any]:
    row = db.execute(
        select(OptimizationRun, User.email)
        .join(User, User.id == OptimizationRun.user_id)
        .where(OptimizationRun.id == run_id)
    ).first()
    if row is None:
        raise ValidationFailure("That run does not exist.")
    run, email = row

    # Inspecting an individual run is a diagnostic workflow, so it is recorded. The payload still
    # excludes the user's profile, income, assets, liabilities and transactions.
    #
    # A view within a minute of the previous one by the same administrator is not a second action:
    # React's development double-mount fetches the detail twice, which produced duplicate rows.
    previous = db.execute(
        select(AdminAuditLog)
        .where(
            AdminAuditLog.actor_id == admin.id,
            AdminAuditLog.action == "run.inspect",
            AdminAuditLog.target_id == str(run.id),
        )
        .order_by(AdminAuditLog.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if previous is None or _seconds_since(previous.created_at) > 60:
        _audit(db, admin, "run.inspect", target_type="optimization_run", target_id=run.id)
        db.commit()

    try:
        payload = json.loads(run.result_json or "{}")
    except json.JSONDecodeError:
        payload = {}

    allocations = [
        {
            "goal_ref": a.goal_ref,
            "goal_name": a.goal_name,
            "future_goal_cost": float(a.future_goal_cost or 0),
            "funding_gap": float(a.funding_gap or 0),
            "monthly_savings_contribution": float(a.monthly_savings_contribution or 0),
            "monthly_investment_contribution": float(a.monthly_investment_contribution or 0),
            "loan_principal": float(a.loan_principal or 0),
            "estimated_loan_emi": float(a.estimated_loan_emi or 0),
            "projected_new_funding": float(a.projected_new_funding or 0),
            "shortfall": float(a.shortfall or 0),
            "achievement_ratio": float(a.achievement_ratio or 0),
        }
        for a in db.execute(
            select(GoalAllocation).where(GoalAllocation.optimization_run_id == run.id)
        ).scalars()
    ]

    return {
        "id": run.id,
        "created_at": _iso(run.created_at),
        "user_email": email,
        "algorithm": run.algorithm,
        "kind": run.kind,
        "status": run.status,
        "feasible": run.feasible,
        "runtime_ms": run.runtime_ms,
        "objective_value": float(run.objective_value) if run.objective_value is not None else None,
        "weighted_achievement": (
            float(run.weighted_achievement) if run.weighted_achievement is not None else None
        ),
        "total_shortfall": float(run.total_shortfall) if run.total_shortfall is not None else None,
        "model_version": run.model_version,
        "config_version": run.config_version,
        "label": payload.get("label", ""),
        "summary": payload.get("summary", {}),
        "constraints": payload.get("constraints", {}),
        "diagnostics": payload.get("diagnostics", {}),
        "alternatives": payload.get("alternatives", []),
        "warnings": _warnings(run),
        "allocations": allocations,
        "assumptions": json.loads(run.assumptions_json or "{}"),
    }


@router.get("/users")
def users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    search: str | None = None,
    role: str | None = Query(default=None, pattern="^(admin|user)$"),
    status: str | None = Query(default=None, pattern="^(active|inactive)$"),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> dict[str, Any]:
    offset, limit = _page(page, page_size)
    runs_count = (
        select(OptimizationRun.user_id, func.count(OptimizationRun.id).label("runs"))
        .group_by(OptimizationRun.user_id)
        .subquery()
    )
    stmt = (
        select(User, func.coalesce(runs_count.c.runs, 0))
        .outerjoin(runs_count, runs_count.c.user_id == User.id)
    )
    if search:
        needle = f"%{search.strip()}%"
        stmt = stmt.where(or_(User.email.ilike(needle), User.full_name.ilike(needle)))
    if role == "admin":
        stmt = stmt.where(User.is_admin.is_(True))
    elif role == "user":
        stmt = stmt.where(User.is_admin.is_(False))
    if status == "active":
        stmt = stmt.where(User.is_active.is_(True))
    elif status == "inactive":
        stmt = stmt.where(User.is_active.is_(False))

    total = int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = db.execute(stmt.order_by(User.created_at.desc()).offset(offset).limit(limit)).all()

    return {
        "items": [
            {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "is_active": user.is_active,
                "is_admin": user.is_admin,
                "created_at": _iso(user.created_at),
                "last_login_at": _iso(user.last_login_at),
                "runs": int(runs),
            }
            for user, runs in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, (total + page_size - 1) // page_size),
    }


@router.patch("/users/{user_id}")
def update_user(
    user_id: int,
    payload: AdminUserPatch,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> dict[str, Any]:
    target = db.get(User, user_id)
    if target is None:
        raise ValidationFailure("That account does not exist.")
    if payload.is_admin is None and payload.is_active is None:
        raise ValidationFailure("Nothing to change.")

    # An administrator cannot remove their own access: a single mis-click would lock the only
    # operator out of the area with no route back in.
    if target.id == admin.id:
        raise ValidationFailure("You cannot change your own role or status.")

    if target.is_admin and payload.is_admin is False:
        remaining = int(
            db.scalar(
                select(func.count(User.id)).where(User.is_admin.is_(True), User.id != target.id)
            )
            or 0
        )
        if remaining == 0:
            raise ValidationFailure("At least one administrator must remain.")

    before = {"is_admin": bool(target.is_admin), "is_active": bool(target.is_active)}
    if payload.is_admin is not None:
        target.is_admin = payload.is_admin
    if payload.is_active is not None:
        target.is_active = payload.is_active
    if not target.is_admin and not target.is_active:
        pass  # deactivating a demoted account is a normal, allowed outcome

    _audit(
        db,
        admin,
        "user.update",
        target_type="user",
        target_id=target.id,
        details={
            "before": before,
            "after": {"is_admin": bool(target.is_admin), "is_active": bool(target.is_active)},
        },
    )
    db.commit()
    db.refresh(target)

    return {
        "id": target.id,
        "email": target.email,
        "full_name": target.full_name,
        "is_admin": bool(target.is_admin),
        "is_active": bool(target.is_active),
    }


@router.get("/audit")
def audit_log(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    action: str | None = None,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> dict[str, Any]:
    offset, limit = _page(page, page_size)
    stmt = select(AdminAuditLog)
    if action:
        stmt = stmt.where(AdminAuditLog.action == action)
    total = int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = db.execute(
        stmt.order_by(AdminAuditLog.created_at.desc()).offset(offset).limit(limit)
    ).scalars()
    return {
        "items": [_audit_row(row) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, (total + page_size - 1) // page_size),
    }


@router.get("/health")
def health(db: Session = Depends(get_db), admin: User = Depends(require_admin)) -> dict[str, Any]:
    database_ok = True
    database_error = None
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        database_ok = False
        database_error = f"{type(exc).__name__}: {str(exc)[:200]}"

    research = research_loader.status()
    rl = rl_engine.readiness()
    failures = int(
        db.scalar(
            select(func.count(OptimizationRun.id)).where(
                OptimizationRun.status.in_(FAILED_STATUSES)
            )
        )
        or 0
    )
    last_failure = db.execute(
        select(OptimizationRun)
        .where(OptimizationRun.status.in_(FAILED_STATUSES))
        .order_by(OptimizationRun.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    return {
        "database": {"reachable": database_ok, "error": database_error},
        "research": research.as_dict(),
        "models": {
            "lp": {"available": research.available, "module": "goalpilot_constrained_lp"},
            "rl": rl,
            "hybrid": {"available": research.available and bool(rl.get("available"))},
        },
        "optimization": {
            "failed_runs": failures,
            "last_failure_at": _iso(last_failure.created_at) if last_failure else None,
            "last_failure_id": last_failure.id if last_failure else None,
        },
        "data_sources": meta_api.data_provenance()["datasets"],
        "assumptions": meta_api.assumptions()["defaults"],
    }


@router.get("/data")
def data_and_assumptions(admin: User = Depends(require_admin)) -> dict[str, Any]:
    """Sources and default assumptions, with the same provenance the API publishes elsewhere.

    Defaults are read-only here on purpose: they live in the deployment configuration, and letting
    a web request rewrite them would silently change what future plans assume. Per-plan overrides
    are validated by the optimizer and reported in each run's assumptions.
    """
    provenance = meta_api.data_provenance()
    assumptions = meta_api.assumptions()
    return {
        "datasets": provenance["datasets"],
        "note": provenance["note"],
        "research_available": provenance["research_available"],
        "defaults": assumptions["defaults"],
        "assumption_note": assumptions["note"],
        "provenance_rules": assumptions["provenance_rules"],
        "editing": {
            "supported": False,
            "reason": (
                "Defaults come from deployment configuration. Changing them from the web app would "
                "alter what every future plan assumes without a review, so edits are made in "
                "configuration and audited by change history. Per-plan assumptions stay editable "
                "where the optimizer validates them."
            ),
        },
    }
