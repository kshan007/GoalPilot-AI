"""Monthly finances: months, transactions, estimates, reconciliation, budgets, forecasts."""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import current_user, owned_or_404
from app.core.errors import ConflictError, ValidationFailure
from app.db import get_db
from app.models import (
    DEFAULT_EXPENSE_CATEGORIES,
    Budget,
    ExpenseForecast,
    ForecastEvaluation,
    MonthlyRecord,
    Transaction,
    User,
)
from app.schemas.common import MessageResponse
from app.schemas.finance import (
    BudgetIn,
    BudgetOut,
    EstimateRequest,
    MonthDetailOut,
    MonthOut,
    ReconcileRequest,
    TransactionIn,
    TransactionOut,
    TransactionUpdate,
)
from app.services.cashflow import classification_for
from app.services.forecasting import (
    METHOD_VERSION,
    MonthObservation,
    backtest,
    detect_persistent_overspend,
    detect_recurring,
    forecast_month,
    next_period,
    previous_periods,
)
from app.services.money import money_float, round_money
from app.services.planner import load_income_sources, load_liabilities

router = APIRouter(tags=["monthly"])


# --------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------
def _get_month(db: Session, user_id: int, period: str) -> MonthlyRecord:
    row = db.execute(
        select(MonthlyRecord).where(
            MonthlyRecord.user_id == user_id, MonthlyRecord.period == period
        )
    ).scalar_one_or_none()
    if row is None:
        raise ValidationFailure(
            f"The month {period} has not been opened yet. Open it first.",
            details={"period": period},
        )
    return row


def _month_out(db: Session, month: MonthlyRecord) -> MonthOut:
    count = len(
        db.execute(
            select(Transaction.id).where(Transaction.month_id == month.id)
        ).scalars().all()
    )
    return MonthOut(
        period=month.period,
        status=month.status,
        total_income_expected=money_float(month.total_income_expected),
        total_income_actual=money_float(month.total_income_actual),
        total_expense_estimated=money_float(month.total_expense_estimated),
        total_expense_actual=money_float(month.total_expense_actual),
        surplus_projected=money_float(month.surplus_projected),
        surplus_actual=money_float(month.surplus_actual),
        reconciled_at=month.reconciled_at,
        transaction_count=count,
    )


def _txn_out(txn: Transaction) -> TransactionOut:
    return TransactionOut(
        id=txn.id,
        kind=txn.kind,
        category=txn.category,
        label=txn.label,
        amount=money_float(txn.amount),
        txn_date=txn.txn_date,
        classification=txn.classification,
        status=txn.status,
        is_recurring=txn.is_recurring,
        goal_id=txn.goal_id,
        note=txn.note,
    )


def _recompute_month(db: Session, month: MonthlyRecord) -> None:
    txns = db.execute(select(Transaction).where(Transaction.month_id == month.id)).scalars().all()
    income_expected = income_actual = expense_est = expense_act = 0.0
    for t in txns:
        amount = float(t.amount)
        if t.kind == "income":
            if t.status == "estimated":
                income_expected += amount
            else:
                income_actual += amount
        else:
            if t.status == "estimated":
                expense_est += amount
            else:
                expense_act += amount
    month.total_income_expected = round_money(income_expected)
    month.total_income_actual = round_money(income_actual)
    month.total_expense_estimated = round_money(expense_est)
    month.total_expense_actual = round_money(expense_act)
    month.surplus_projected = round_money(income_expected + income_actual - expense_est - expense_act)
    month.surplus_actual = round_money(income_actual - expense_act)
    if month.status != "reconciled":
        month.status = "estimated" if (expense_est or income_expected) else "open"


def _observations(db: Session, user_id: int, before_period: str) -> list[MonthObservation]:
    """Actual-only expense observations strictly before ``before_period``."""
    rows = db.execute(
        select(Transaction).where(
            Transaction.user_id == user_id,
            Transaction.kind == "expense",
            Transaction.status == "actual",
            Transaction.period < before_period,
        )
    ).scalars().all()
    return [MonthObservation(period=r.period, category=r.category, amount=float(r.amount)) for r in rows]


def _actual_by_category(db: Session, user_id: int, period: str) -> dict[str, float]:
    """Total recorded expense per category, actual rows preferred over estimates."""
    amounts, _ = _actuals_with_provenance(db, user_id, period)
    return amounts


def _actuals_with_provenance(
    db: Session, user_id: int, period: str
) -> tuple[dict[str, float], set[str]]:
    """Per-category actual totals **and** the set of categories that have a real actual.

    The distinction matters for reconciliation: a category with a forecast and no recorded
    actual has *no error* — there is simply nothing to compare against. Reporting that as a
    100% forecast error would be a false statement about the forecast.
    """
    rows = db.execute(
        select(Transaction).where(
            Transaction.user_id == user_id,
            Transaction.kind == "expense",
            Transaction.period == period,
        )
    ).scalars().all()
    actual_rows = [r for r in rows if r.status == "actual"]
    has_actual = {r.category for r in actual_rows}
    out: dict[str, float] = {}
    for r in actual_rows:
        out[r.category] = out.get(r.category, 0.0) + float(r.amount)
    return out, has_actual


def _budget_map(db: Session, user_id: int) -> dict[str, float]:
    rows = db.execute(
        select(Budget).where(Budget.user_id == user_id, Budget.is_active.is_(True))
    ).scalars().all()
    return {r.category: float(r.monthly_limit) for r in rows}


# --------------------------------------------------------------------------------------
# months
# --------------------------------------------------------------------------------------
@router.get("/months", response_model=list[MonthOut])
def list_months(
    limit: int = Query(default=24, ge=1, le=120),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(MonthlyRecord)
        .where(MonthlyRecord.user_id == user.id)
        .order_by(MonthlyRecord.period.desc())
        .limit(limit)
    ).scalars()
    return [_month_out(db, r) for r in rows]


@router.post("/months/{period}/open", response_model=MonthDetailOut)
def open_month(period: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Open (or re-open) a month and seed expected income and recurring obligations.

    Seeding is idempotent: a recurring line is only created if an identical one does not
    already exist for the period.
    """
    if len(period) != 7 or period[4] != "-":
        raise ValidationFailure("Period must be in YYYY-MM format.")

    month = db.execute(
        select(MonthlyRecord).where(
            MonthlyRecord.user_id == user.id, MonthlyRecord.period == period
        )
    ).scalar_one_or_none()
    created = month is None
    if month is None:
        month = MonthlyRecord(user_id=user.id, period=period, status="open")
        db.add(month)
        db.flush()

    existing = db.execute(select(Transaction).where(Transaction.month_id == month.id)).scalars().all()
    keys = {(t.kind, t.category, t.label) for t in existing}

    income = load_income_sources(db, user.id)
    for src in income:
        if not src.is_recurring:
            continue
        key = ("income", "income", src.label or src.source_type)
        if key in keys:
            continue
        db.add(
            Transaction(
                user_id=user.id,
                month_id=month.id,
                period=period,
                kind="income",
                category="income",
                label=src.label or src.source_type,
                amount=round_money(src.monthly_equivalent),
                txn_date=dt.date(int(period[:4]), int(period[5:7]), 1),
                classification="income",
                status="estimated",
                is_recurring=True,
            )
        )

    liabilities = load_liabilities(db, user.id)
    for liab in liabilities:
        if float(liab.emi_amount) <= 0:
            continue
        key = ("expense", "loan_payments", liab.label or liab.liability_type)
        if key in keys:
            continue
        db.add(
            Transaction(
                user_id=user.id,
                month_id=month.id,
                period=period,
                kind="expense",
                category="loan_payments",
                label=liab.label or liab.liability_type,
                amount=round_money(liab.emi_amount),
                txn_date=dt.date(int(period[:4]), int(period[5:7]), 1),
                classification="essential",
                status="estimated",
                is_recurring=True,
            )
        )

    # carry forward last month's recurring non-loan expenses
    prev = previous_periods(period, 1)[0]
    prev_month = db.execute(
        select(MonthlyRecord).where(
            MonthlyRecord.user_id == user.id, MonthlyRecord.period == prev
        )
    ).scalar_one_or_none()
    if prev_month is not None:
        prev_rows = db.execute(
            select(Transaction).where(
                Transaction.month_id == prev_month.id,
                Transaction.kind == "expense",
                Transaction.is_recurring.is_(True),
            )
        ).scalars().all()
        for row in prev_rows:
            key = ("expense", row.category, row.label)
            if key in keys or row.category == "loan_payments":
                continue
            db.add(
                Transaction(
                    user_id=user.id,
                    month_id=month.id,
                    period=period,
                    kind="expense",
                    category=row.category,
                    label=row.label,
                    amount=row.amount,
                    txn_date=dt.date(int(period[:4]), int(period[5:7]), 1),
                    classification=row.classification,
                    status="estimated",
                    is_recurring=True,
                )
            )

    db.flush()
    _recompute_month(db, month)
    db.commit()
    db.refresh(month)
    return _month_detail(db, month)


@router.get("/months/{period}", response_model=MonthDetailOut)
def read_month(period: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    month = _get_month(db, user.id, period)
    return _month_detail(db, month)


def _month_detail(db: Session, month: MonthlyRecord) -> MonthDetailOut:
    txns = db.execute(
        select(Transaction).where(Transaction.month_id == month.id).order_by(Transaction.id)
    ).scalars().all()
    categories: dict[str, dict[str, float]] = {}
    for t in txns:
        if t.kind != "expense":
            continue
        slot = categories.setdefault(
            t.category, {"actual": 0.0, "estimated": 0.0, "budget": 0.0}
        )
        slot["actual" if t.status == "actual" else "estimated"] += float(t.amount)
    budgets = _budget_map(db, month.user_id)
    for category, slot in categories.items():
        slot["budget"] = budgets.get(category, 0.0)

    forecasts = db.execute(
        select(ExpenseForecast).where(ExpenseForecast.month_id == month.id)
    ).scalars().all()
    forecast_block = None
    if forecasts:
        forecast_block = {
            "generated_at": max(f.created_at for f in forecasts).isoformat(),
            "method_version": forecasts[0].method_version,
            "total": round(sum(float(f.forecast_amount) for f in forecasts), 2),
            "is_provisional": all(f.is_provisional for f in forecasts),
            "categories": [
                {
                    "category": f.category,
                    "amount": money_float(f.forecast_amount),
                    "method": f.method,
                    "history_months_used": f.history_months_used,
                    "is_provisional": f.is_provisional,
                    "data_quality": f.data_quality,
                    "input_cutoff": f.input_cutoff.isoformat(),
                }
                for f in sorted(forecasts, key=lambda x: x.category)
            ],
        }

    evaluations = db.execute(
        select(ForecastEvaluation).where(ForecastEvaluation.period == month.period,
                                        ForecastEvaluation.user_id == month.user_id)
    ).scalars().all()
    reconciliation = None
    if evaluations:
        rows = [
            {
                "category": e.category,
                "forecast": money_float(e.forecast_amount),
                "actual": money_float(e.actual_amount),
                "abs_error": money_float(e.abs_error),
                "pct_error": float(e.pct_error) if e.pct_error is not None else None,
                "actual_recorded": True,
                "over_budget": float(e.actual_amount) > float(e.forecast_amount),
            }
            for e in sorted(evaluations, key=lambda x: x.category)
        ]
        total_forecast = sum(r["forecast"] for r in rows)
        total_actual = sum(r["actual"] for r in rows)
        reconciliation = {
            "evaluated_at": max(e.evaluated_at for e in evaluations).isoformat(),
            "rows": rows,
            "totals": {
                "forecast": round(total_forecast, 2),
                "actual": round(total_actual, 2),
                "abs_error": round(sum(r["abs_error"] for r in rows), 2),
                "pct_error": (
                    round((total_actual - total_forecast) / total_forecast * 100, 2)
                    if total_forecast
                    else None
                ),
            },
            "over_budget_categories": [r["category"] for r in rows if r["over_budget"]],
            "under_budget_categories": [r["category"] for r in rows if not r["over_budget"]],
        }

    return MonthDetailOut(
        month=_month_out(db, month),
        transactions=[_txn_out(t) for t in txns],
        categories=categories,
        forecast=forecast_block,
        reconciliation=reconciliation,
    )


# --------------------------------------------------------------------------------------
# transactions
# --------------------------------------------------------------------------------------
@router.get("/months/{period}/transactions", response_model=list[TransactionOut])
def list_transactions(
    period: str,
    kind: str | None = Query(default=None, pattern="^(income|expense)$"),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    month = _get_month(db, user.id, period)
    stmt = select(Transaction).where(Transaction.month_id == month.id)
    if kind:
        stmt = stmt.where(Transaction.kind == kind)
    rows = db.execute(stmt.order_by(Transaction.id)).scalars().all()
    return [_txn_out(t) for t in rows]


@router.post("/months/{period}/transactions", response_model=TransactionOut, status_code=201)
def create_transaction(
    period: str,
    payload: TransactionIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    month = _get_month(db, user.id, period)
    if payload.client_ref:
        # Duplicate-submission protection: the same client reference is a no-op.
        dup = db.execute(
            select(Transaction).where(
                Transaction.user_id == user.id, Transaction.client_ref == payload.client_ref
            )
        ).scalar_one_or_none()
        if dup is not None:
            return _txn_out(dup)

    classification = payload.classification or (
        "income" if payload.kind == "income" else classification_for(payload.category, None)
    )
    txn = Transaction(
        user_id=user.id,
        month_id=month.id,
        period=period,
        kind=payload.kind,
        category=payload.category or ("income" if payload.kind == "income" else "other"),
        label=payload.label,
        amount=round_money(payload.amount),
        txn_date=payload.txn_date,
        classification=classification,
        status=payload.status,
        is_recurring=payload.is_recurring,
        goal_id=payload.goal_id,
        note=payload.note,
        client_ref=payload.client_ref,
    )
    db.add(txn)
    db.flush()
    _recompute_month(db, month)
    db.commit()
    db.refresh(txn)
    return _txn_out(txn)


@router.put("/months/{period}/transactions/{txn_id}", response_model=TransactionOut)
def update_transaction(
    period: str,
    txn_id: int,
    payload: TransactionUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    month = _get_month(db, user.id, period)
    txn = owned_or_404(db, Transaction, user, txn_id)
    if txn.month_id != month.id:
        raise ValidationFailure("This transaction does not belong to that month.")
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        if value is not None:
            setattr(txn, key, round_money(value) if key == "amount" else value)
    _recompute_month(db, month)
    db.commit()
    db.refresh(txn)
    return _txn_out(txn)


@router.delete("/months/{period}/transactions/{txn_id}", response_model=MessageResponse)
def delete_transaction(
    period: str,
    txn_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    month = _get_month(db, user.id, period)
    txn = owned_or_404(db, Transaction, user, txn_id)
    if txn.month_id != month.id:
        raise ValidationFailure("This transaction does not belong to that month.")
    db.delete(txn)
    db.flush()
    _recompute_month(db, month)
    db.commit()
    return MessageResponse(message="Transaction removed.")


# --------------------------------------------------------------------------------------
# estimation
# --------------------------------------------------------------------------------------
@router.post("/months/{period}/estimate-expenses")
def estimate_expenses(
    period: str,
    payload: EstimateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Generate category-level estimates for a month and persist them as forecasts.

    Cold start uses the user's own declared recurring obligations and estimates. Once
    enough actual months exist, a personalised method is used **only** where a walk-forward
    backtest shows it beats the baseline.
    """
    month = _get_month(db, user.id, period)
    history = _observations(db, user.id, period)

    recurring = dict(payload.recurring_categories)
    liabilities = load_liabilities(db, user.id)
    loan_total = sum(float(l.emi_amount) for l in liabilities)
    if loan_total > 0:
        recurring.setdefault("loan_payments", loan_total)

    categories = sorted(
        set(DEFAULT_EXPENSE_CATEGORIES)
        | set(payload.category_estimates)
        | set(recurring)
        | {obs.category for obs in history}
    )
    result = forecast_month(
        history,
        period=period,
        categories=categories,
        recurring_amounts=recurring,
        category_estimates=payload.category_estimates,
    )

    persisted = 0
    if payload.persist:
        for item in result.category_forecasts:
            existing = db.execute(
                select(ExpenseForecast).where(
                    ExpenseForecast.month_id == month.id,
                    ExpenseForecast.category == item.category,
                    ExpenseForecast.method_version == METHOD_VERSION,
                )
            ).scalar_one_or_none()
            if existing is not None:
                # A forecast already exists for this month+category+version. Never overwrite it:
                # history must stay reproducible. Replace only if it was provisional and no
                # actual has been recorded yet.
                if not existing.is_provisional:
                    raise ConflictError(
                        f"A committed forecast already exists for '{item.category}' in {period}.",
                        details={"category": item.category, "period": period},
                    )
                existing.forecast_amount = round_money(item.amount)
                existing.method = item.method
                existing.input_cutoff = dt.datetime.now(dt.timezone.utc)
                existing.history_months_used = item.history_months_used
                existing.is_provisional = item.is_provisional
                existing.data_quality = item.data_quality
            else:
                db.add(
                    ExpenseForecast(
                        user_id=user.id,
                        month_id=month.id,
                        period=period,
                        category=item.category,
                        forecast_amount=round_money(item.amount),
                        method=item.method,
                        method_version=METHOD_VERSION,
                        input_cutoff=dt.datetime.now(dt.timezone.utc),
                        history_months_used=item.history_months_used,
                        is_provisional=item.is_provisional,
                        data_quality=item.data_quality,
                    )
                )
                persisted += 1
        db.flush()
        _recompute_month(db, month)
        if month.status == "open":
            month.status = "estimated"
        db.commit()

    expected_surplus = float(month.total_income_expected) + float(month.total_income_actual) - (
        result.total_forecast + float(month.total_expense_actual)
    )
    return {
        "period": period,
        "forecast": result.as_dict(),
        "persisted_count": persisted,
        "expected_month_end_spending": round(result.total_forecast, 2),
        "projected_surplus": round(expected_surplus, 2),
        "history_months_available": result.months_of_history,
        "personalised": result.personalised,
        "estimation_method": (
            "Personalised (per-category method chosen by walk-forward backtest)"
            if result.personalised
            else "Cold-start baseline (recurring obligations and user estimates only)"
        ),
        "data_quality_note": (
            "Provisional: no actual expense history exists yet. The system has not learned "
            "from data it does not have."
            if result.months_of_history == 0
            else f"Based on {result.months_of_history} month(s) of actual expenses."
        ),
    }


# --------------------------------------------------------------------------------------
# reconciliation
# --------------------------------------------------------------------------------------
@router.get("/months/{period}/reconciliation")
def read_reconciliation(
    period: str, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    month = _get_month(db, user.id, period)
    detail = _month_detail(db, month)
    if detail.reconciliation is None:
        return {
            "period": period,
            "reconciled": False,
            "message": (
                "This month has not been reconciled yet. Generate estimates, record actual "
                "expenses, then reconcile."
            ),
            "category_actuals": _actual_by_category(db, user.id, period),
        }
    return {"period": period, "reconciled": True, **detail.reconciliation}


@router.post("/months/{period}/reconcile")
def reconcile_month(
    period: str,
    payload: ReconcileRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Reconcile estimates against actuals.

    The original forecast is preserved: an evaluation row is appended next to it and the
    forecast row itself is never overwritten with the actual value.
    """
    month = _get_month(db, user.id, period)
    forecasts = db.execute(
        select(ExpenseForecast).where(ExpenseForecast.month_id == month.id)
    ).scalars().all()
    if not forecasts:
        raise ValidationFailure(
            "There is no forecast for this month to reconcile against. Generate estimates first."
        )

    actuals, has_actual = _actuals_with_provenance(db, user.id, period)
    created = 0
    unmatched: list[str] = []
    rows: list[dict] = []
    for f in forecasts:
        forecast_amount = float(f.forecast_amount)
        if f.category not in has_actual:
            # No actual was recorded for this category, so there is nothing to compare. The
            # forecast is neither right nor wrong and is reported as unmatched, not as an error.
            unmatched.append(f.category)
            rows.append(
                {
                    "category": f.category,
                    "forecast": round(forecast_amount, 2),
                    "actual": None,
                    "abs_error": None,
                    "pct_error": None,
                    "actual_recorded": False,
                }
            )
            continue

        actual = float(actuals.get(f.category, 0.0))
        abs_error = abs(actual - forecast_amount)
        pct_error = (abs_error / forecast_amount * 100.0) if forecast_amount else None

        existing = db.execute(
            select(ForecastEvaluation).where(ForecastEvaluation.forecast_id == f.id)
        ).scalar_one_or_none()
        if existing is None:
            db.add(
                ForecastEvaluation(
                    user_id=user.id,
                    forecast_id=f.id,
                    period=period,
                    category=f.category,
                    forecast_amount=f.forecast_amount,
                    actual_amount=round_money(actual),
                    abs_error=round_money(abs_error),
                    pct_error=round(pct_error, 4) if pct_error is not None else None,
                )
            )
            created += 1
        rows.append(
            {
                "category": f.category,
                "forecast": round(forecast_amount, 2),
                "actual": round(actual, 2),
                "abs_error": round(abs_error, 2),
                "pct_error": round(pct_error, 2) if pct_error is not None else None,
                "actual_recorded": True,
            }
        )

    db.flush()
    _recompute_month(db, month)
    month.status = "reconciled"
    month.reconciled_at = dt.datetime.now(dt.timezone.utc)

    # available savings after the actual month
    income_actual = float(month.total_income_actual)
    expense_actual = float(month.total_expense_actual)
    surplus_actual = income_actual - expense_actual

    future_note = None
    if payload.update_future_forecast:
        following = next_period(period)
        if following:
            future_note = (
                f"The stored history now includes {period}. The next forecast for "
                f"{following} will use this month's actuals; the {period} forecast itself is "
                "retained unchanged."
            )
    db.commit()

    # Totals cover only the categories that actually have an actual to compare against.
    matched = [r for r in rows if r["actual_recorded"]]
    total_forecast = sum(r["forecast"] for r in matched)
    total_actual = sum(r["actual"] for r in matched)
    return {
        "period": period,
        "evaluations_created": created,
        "rows": rows,
        "totals": {
            "forecast": round(total_forecast, 2),
            "actual": round(total_actual, 2),
            "abs_error": round(abs(total_actual - total_forecast), 2),
            "pct_error": (
                round((total_actual - total_forecast) / total_forecast * 100, 2)
                if total_forecast
                else None
            ),
            "categories_compared": len(matched),
            "categories_without_actual": len(unmatched),
        },
        "unmatched_categories": unmatched,
        "unmatched_note": (
            f"{len(unmatched)} categor(y/ies) have a forecast but no recorded actual, so no "
            "error can be computed for them. They are excluded from the totals rather than "
            "counted as a 100% miss."
            if unmatched
            else None
        ),
        "over_budget_categories": [r["category"] for r in matched if r["actual"] > r["forecast"]],
        "under_budget_categories": [r["category"] for r in matched if r["actual"] <= r["forecast"]],
        "financial_impact": {
            "income_actual": round(income_actual, 2),
            "expense_actual": round(expense_actual, 2),
            "surplus_actual": round(surplus_actual, 2),
            "surplus_projected_at_estimation": money_float(month.surplus_projected),
            "note": (
                "Goal feasibility is recalculated from the actual surplus whenever a new plan "
                "is generated; run the optimiser to see the updated allocation."
            ),
        },
        "forecast_preserved": True,
        "next_forecast_note": future_note,
    }


@router.get("/months/{period}/budget-status")
def budget_status(period: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    month = _get_month(db, user.id, period)
    budgets = _budget_map(db, user.id)
    actuals = _actual_by_category(db, user.id, period)
    history = _observations(db, user.id, period)
    status = []
    for category, limit in sorted(budgets.items()):
        spent = actuals.get(category, 0.0)
        status.append(
            {
                "category": category,
                "monthly_limit": round(limit, 2),
                "spent": round(spent, 2),
                "remaining": round(limit - spent, 2),
                "utilisation": round(spent / limit, 4) if limit else None,
                "over_budget": spent > limit,
            }
        )
    return {
        "period": period,
        "budgets": status,
        "persistent_overspend": detect_persistent_overspend(history, budgets),
        "recurring_categories": detect_recurring(history),
    }


# --------------------------------------------------------------------------------------
# budgets
# --------------------------------------------------------------------------------------
@router.get("/budgets", response_model=list[BudgetOut])
def list_budgets(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(
        select(Budget).where(Budget.user_id == user.id).order_by(Budget.category)
    ).scalars()
    return [
        BudgetOut(
            id=r.id,
            category=r.category,
            monthly_limit=money_float(r.monthly_limit),
            classification=r.classification,
            is_active=r.is_active,
        )
        for r in rows
    ]


@router.post("/budgets", response_model=BudgetOut, status_code=201)
def create_budget(payload: BudgetIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    existing = db.execute(
        select(Budget).where(Budget.user_id == user.id, Budget.category == payload.category)
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError(f"A budget for '{payload.category}' already exists.")
    row = Budget(
        user_id=user.id,
        category=payload.category,
        monthly_limit=round_money(payload.monthly_limit),
        classification=payload.classification,
        is_active=payload.is_active,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return BudgetOut(
        id=row.id,
        category=row.category,
        monthly_limit=money_float(row.monthly_limit),
        classification=row.classification,
        is_active=row.is_active,
    )


@router.put("/budgets/{budget_id}", response_model=BudgetOut)
def update_budget(
    budget_id: int,
    payload: BudgetIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    row = owned_or_404(db, Budget, user, budget_id)
    row.category = payload.category
    row.monthly_limit = round_money(payload.monthly_limit)
    row.classification = payload.classification
    row.is_active = payload.is_active
    db.commit()
    db.refresh(row)
    return BudgetOut(
        id=row.id,
        category=row.category,
        monthly_limit=money_float(row.monthly_limit),
        classification=row.classification,
        is_active=row.is_active,
    )


@router.delete("/budgets/{budget_id}", response_model=MessageResponse)
def delete_budget(
    budget_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    row = owned_or_404(db, Budget, user, budget_id)
    db.delete(row)
    db.commit()
    return MessageResponse(message="Budget removed.")


# --------------------------------------------------------------------------------------
# forecast history / accuracy
# --------------------------------------------------------------------------------------
@router.get("/forecast/history")
def forecast_history(
    limit: int = Query(default=60, ge=1, le=500),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(ExpenseForecast)
        .where(ExpenseForecast.user_id == user.id)
        .order_by(ExpenseForecast.period.desc(), ExpenseForecast.category)
        .limit(limit)
    ).scalars().all()
    return {
        "count": len(rows),
        "forecasts": [
            {
                "period": r.period,
                "category": r.category,
                "amount": money_float(r.forecast_amount),
                "method": r.method,
                "method_version": r.method_version,
                "history_months_used": r.history_months_used,
                "is_provisional": r.is_provisional,
                "data_quality": r.data_quality,
                "input_cutoff": r.input_cutoff.isoformat(),
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ],
        "note": (
            "Every forecast is stored with the method, version, input cut-off and the number of "
            "history months it used. Forecasts are never overwritten by their actual outcome."
        ),
    }


@router.get("/forecast/accuracy")
def forecast_accuracy(user: User = Depends(current_user), db: Session = Depends(get_db)):
    evaluations = db.execute(
        select(ForecastEvaluation)
        .where(ForecastEvaluation.user_id == user.id)
        .order_by(ForecastEvaluation.period)
    ).scalars().all()
    history = _observations(db, user.id, "9999-12")

    by_period: dict[str, dict[str, float]] = {}
    for e in evaluations:
        slot = by_period.setdefault(e.period, {"forecast": 0.0, "actual": 0.0, "abs_error": 0.0})
        slot["forecast"] += float(e.forecast_amount)
        slot["actual"] += float(e.actual_amount)
        slot["abs_error"] += float(e.abs_error)

    periods = [
        {
            "period": period,
            "forecast": round(v["forecast"], 2),
            "actual": round(v["actual"], 2),
            "abs_error": round(v["abs_error"], 2),
            "pct_error": (
                round(v["abs_error"] / v["forecast"] * 100, 2) if v["forecast"] else None
            ),
        }
        for period, v in sorted(by_period.items())
    ]
    mae = (
        round(sum(p["abs_error"] for p in periods) / len(periods), 2) if periods else None
    )
    return {
        "periods_evaluated": len(periods),
        "periods": periods,
        "mae_per_period": mae,
        "walk_forward_backtest": backtest(history),
        "evidence_note": (
            "Forecast accuracy is only reported for months that have been reconciled. With "
            "fewer than four reconciled months the comparison is not meaningful, and that is "
            "stated rather than hidden."
            if len(periods) < 4
            else "Walk-forward backtest compares the chosen method against a simple "
            "historical-mean baseline on this user's own months."
        ),
    }
