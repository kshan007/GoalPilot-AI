"""SQLAlchemy 2.0 schema.

Ownership rule: every user-owned table carries ``user_id`` with a foreign key to
``users.id`` and ``ON DELETE CASCADE``. The API never loads a user-owned row by
primary key alone; it always adds ``user_id == current_user.id``.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

Money = Numeric(18, 2)
Rate = Numeric(9, 6)


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class TimestampMixin:
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


# --------------------------------------------------------------------------------------
# identity
# --------------------------------------------------------------------------------------
class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    #: Administrative access is a property of the account, never of the token: every admin
    #: request is re-checked against this flag, so revoking it takes effect immediately.
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_login_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    token_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    preferences: Mapped["UserPreference"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    profile: Mapped["FinancialProfile"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    income_sources: Mapped[list["IncomeSource"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    assets: Mapped[list["Asset"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    liabilities: Mapped[list["Liability"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    goals: Mapped[list["Goal"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    months: Mapped[list["MonthlyRecord"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    budgets: Mapped[list["Budget"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class UserPreference(Base, TimestampMixin):
    """Settings, risk/planning preferences and onboarding progress."""

    __tablename__ = "user_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    currency: Mapped[str] = mapped_column(String(8), default="INR", nullable=False)
    locale: Mapped[str] = mapped_column(String(16), default="en-IN", nullable=False)

    # Risk & planning preferences. Risk *tolerance* and *ability to withstand losses*
    # are stored separately on purpose: capacity is never inferred from appetite alone.
    risk_tolerance: Mapped[str] = mapped_column(String(16), default="moderate", nullable=False)
    loss_ability: Mapped[str] = mapped_column(String(16), default="moderate", nullable=False)
    liquidity_requirement: Mapped[str] = mapped_column(String(16), default="medium", nullable=False)

    onboarding_step: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    assumptions_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)

    user: Mapped[User] = relationship(back_populates="preferences")


class FinancialProfile(Base, TimestampMixin):
    __tablename__ = "financial_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )

    monthly_income: Mapped[Decimal] = mapped_column(Money, default=0, nullable=False)
    essential_expenses: Mapped[Decimal] = mapped_column(Money, default=0, nullable=False)
    discretionary_expenses: Mapped[Decimal] = mapped_column(Money, default=0, nullable=False)

    # A *desired* savings target is not the same thing as available surplus; both are stored.
    monthly_savings_target: Mapped[Decimal] = mapped_column(Money, default=0, nullable=False)
    savings_target_is_mandatory: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    preferred_cash_buffer: Mapped[Decimal] = mapped_column(Money, default=0, nullable=False)
    willing_to_adjust_discretionary: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )

    emergency_months: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=6, nullable=False)
    emi_income_ratio_cap: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0.35"), nullable=False)
    # Explicit normalised 0..1 risk capacity. Never derived from risk_tolerance.
    risk_capacity: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0.5"), nullable=False)

    inflation_assumption: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0.03"), nullable=False)
    investment_return_assumption: Mapped[Decimal] = mapped_column(
        Rate, default=Decimal("0.05"), nullable=False
    )
    savings_return_assumption: Mapped[Decimal] = mapped_column(
        Rate, default=Decimal("0.00"), nullable=False
    )
    loan_interest_assumption: Mapped[Decimal] = mapped_column(
        Rate, default=Decimal("0.12"), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="profile")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    detail_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    ip: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


# --------------------------------------------------------------------------------------
# onboarding entities
# --------------------------------------------------------------------------------------
INCOME_FREQUENCIES = ("monthly", "annual", "quarterly", "weekly", "one_time")


class IncomeSource(Base, TimestampMixin):
    __tablename__ = "income_sources"
    __table_args__ = (Index("ix_income_user_type", "user_id", "source_type"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)  # salary|freelance|...
    label: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    # ``amount`` is the amount *as stated* in ``frequency``; ``monthly_equivalent`` is the
    # normalised value the planner uses. The original frequency is retained.
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    frequency: Mapped[str] = mapped_column(String(16), default="monthly", nullable=False)
    monthly_equivalent: Mapped[Decimal] = mapped_column(Money, nullable=False)
    stability: Mapped[str] = mapped_column(String(16), default="stable", nullable=False)
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    expected_day: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    user: Mapped[User] = relationship(back_populates="income_sources")


ASSET_TYPES = ("liquid_savings", "emergency_savings", "investment", "fixed_deposit", "other")


class Asset(Base, TimestampMixin):
    __tablename__ = "assets"
    __table_args__ = (Index("ix_assets_user_type", "user_id", "asset_type"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    asset_type: Mapped[str] = mapped_column(String(32), nullable=False)
    label: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    current_value: Mapped[Decimal] = mapped_column(Money, nullable=False)
    # Total assets != available cash. ``is_liquid`` marks what can actually be spent.
    is_liquid: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    usable_for_goals: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    annual_return: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0"), nullable=False)
    risk_score: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0.2"), nullable=False)
    earmarked_goal_id: Mapped[int | None] = mapped_column(
        ForeignKey("goals.id", ondelete="SET NULL"), index=True
    )

    user: Mapped[User] = relationship(back_populates="assets")


LIABILITY_TYPES = (
    "home_loan", "vehicle_loan", "personal_loan", "education_loan",
    "credit_card", "other",
)


class Liability(Base, TimestampMixin):
    """Debt.

    ``outstanding_principal`` is the balance; ``emi_amount`` is the monthly payment.
    Principal repayment and EMI are **not** added together anywhere: the EMI already
    contains both interest and principal, so the cash-flow impact of a liability is the
    EMI. The principal is used only for balance-sheet reporting.
    """

    __tablename__ = "liabilities"
    __table_args__ = (Index("ix_liabilities_user_type", "user_id", "liability_type"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    liability_type: Mapped[str] = mapped_column(String(32), nullable=False)
    label: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    outstanding_principal: Mapped[Decimal] = mapped_column(Money, nullable=False)
    annual_interest_rate: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0"), nullable=False)
    emi_amount: Mapped[Decimal] = mapped_column(Money, default=0, nullable=False)
    remaining_tenure_months: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    user: Mapped[User] = relationship(back_populates="liabilities")


# --------------------------------------------------------------------------------------
# goals
# --------------------------------------------------------------------------------------
GOAL_TYPES = (
    "education", "higher_studies", "vehicle", "home", "wedding", "retirement",
    "travel", "emergency", "custom",
)
GOAL_STATUSES = ("active", "paused", "completed", "archived")


class Goal(Base, TimestampMixin):
    __tablename__ = "goals"
    __table_args__ = (Index("ix_goals_user_status", "user_id", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    purpose: Mapped[str] = mapped_column(String(400), default="", nullable=False)
    goal_type: Mapped[str] = mapped_column(String(32), default="custom", nullable=False)

    current_cost: Mapped[Decimal] = mapped_column(Money, nullable=False)
    target_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    current_funded_amount: Mapped[Decimal] = mapped_column(Money, default=0, nullable=False)

    priority: Mapped[int] = mapped_column(Integer, default=3, nullable=False)      # 1..5
    criticality: Mapped[int] = mapped_column(Integer, default=3, nullable=False)   # 1..5
    date_flexible: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    amount_flexible: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    liquidity_requirement: Mapped[str] = mapped_column(String(16), default="medium", nullable=False)
    risk_constraint: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0.5"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)

    user: Mapped[User] = relationship(back_populates="goals")
    contributions: Mapped[list["GoalContribution"]] = relationship(
        back_populates="goal", cascade="all, delete-orphan"
    )


class GoalContribution(Base):
    __tablename__ = "goal_contributions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    goal_id: Mapped[int] = mapped_column(
        ForeignKey("goals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    contribution_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)
    note: Mapped[str] = mapped_column(String(240), default="", nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)

    goal: Mapped[Goal] = relationship(back_populates="contributions")


# --------------------------------------------------------------------------------------
# monthly workflow
# --------------------------------------------------------------------------------------
MONTH_STATUSES = ("open", "estimated", "reconciled")
TXN_KINDS = ("income", "expense")
TXN_STATUSES = ("estimated", "actual")
TXN_CLASSES = ("essential", "discretionary", "income")

DEFAULT_EXPENSE_CATEGORIES = (
    "housing", "food_groceries", "utilities", "transport", "education", "healthcare",
    "insurance", "family", "loan_payments", "shopping", "entertainment", "travel",
    "subscriptions", "other",
)


class MonthlyRecord(Base, TimestampMixin):
    __tablename__ = "monthly_records"
    __table_args__ = (UniqueConstraint("user_id", "period", name="uq_month_user_period"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    period: Mapped[str] = mapped_column(String(7), nullable=False)  # YYYY-MM
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False)

    total_income_expected: Mapped[Decimal] = mapped_column(Money, default=0, nullable=False)
    total_income_actual: Mapped[Decimal] = mapped_column(Money, default=0, nullable=False)
    total_expense_estimated: Mapped[Decimal] = mapped_column(Money, default=0, nullable=False)
    total_expense_actual: Mapped[Decimal] = mapped_column(Money, default=0, nullable=False)

    surplus_projected: Mapped[Decimal] = mapped_column(Money, default=0, nullable=False)
    surplus_actual: Mapped[Decimal] = mapped_column(Money, default=0, nullable=False)

    reconciled_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="months")
    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="month", cascade="all, delete-orphan"
    )
    forecasts: Mapped[list["ExpenseForecast"]] = relationship(
        back_populates="month", cascade="all, delete-orphan"
    )


class Transaction(Base, TimestampMixin):
    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_txn_month_kind", "month_id", "kind"),
        Index("ix_txn_user_period", "user_id", "period"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    month_id: Mapped[int] = mapped_column(
        ForeignKey("monthly_records.id", ondelete="CASCADE"), nullable=False, index=True
    )
    period: Mapped[str] = mapped_column(String(7), nullable=False)
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    category: Mapped[str] = mapped_column(String(48), default="other", nullable=False)
    label: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    txn_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    classification: Mapped[str] = mapped_column(String(16), default="essential", nullable=False)
    status: Mapped[str] = mapped_column(String(12), default="actual", nullable=False)
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    goal_id: Mapped[int | None] = mapped_column(ForeignKey("goals.id", ondelete="SET NULL"))
    note: Mapped[str] = mapped_column(String(240), default="", nullable=False)
    # Idempotency key supplied by the client; makes duplicate submission a no-op.
    client_ref: Mapped[str | None] = mapped_column(String(64), index=True)

    month: Mapped[MonthlyRecord] = relationship(back_populates="transactions")


class Budget(Base, TimestampMixin):
    __tablename__ = "budgets"
    __table_args__ = (UniqueConstraint("user_id", "category", name="uq_budget_user_category"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String(48), nullable=False)
    monthly_limit: Mapped[Decimal] = mapped_column(Money, nullable=False)
    classification: Mapped[str] = mapped_column(String(16), default="discretionary", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    user: Mapped[User] = relationship(back_populates="budgets")


class ExpenseForecast(Base):
    """A forecast is immutable once written. Reconciliation attaches the actual to it;
    the original value is never overwritten."""

    __tablename__ = "expense_forecasts"
    __table_args__ = (UniqueConstraint("month_id", "category", "method_version",
                                      name="uq_forecast_month_cat_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    month_id: Mapped[int] = mapped_column(
        ForeignKey("monthly_records.id", ondelete="CASCADE"), nullable=False, index=True
    )
    period: Mapped[str] = mapped_column(String(7), nullable=False)
    category: Mapped[str] = mapped_column(String(48), nullable=False)
    forecast_amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    method: Mapped[str] = mapped_column(String(32), nullable=False)          # baseline|ewma|rolling
    method_version: Mapped[str] = mapped_column(String(16), nullable=False)  # v1
    input_cutoff: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    history_months_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_provisional: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    data_quality: Mapped[str] = mapped_column(String(16), default="provisional", nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)

    month: Mapped["MonthlyRecord"] = relationship(back_populates="forecasts")


class ForecastEvaluation(Base):
    __tablename__ = "forecast_evaluations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    forecast_id: Mapped[int] = mapped_column(
        ForeignKey("expense_forecasts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    period: Mapped[str] = mapped_column(String(7), nullable=False)
    category: Mapped[str] = mapped_column(String(48), nullable=False)
    forecast_amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    actual_amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    abs_error: Mapped[Decimal] = mapped_column(Money, nullable=False)
    pct_error: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    evaluated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


# --------------------------------------------------------------------------------------
# optimisation / scenarios / model registry
# --------------------------------------------------------------------------------------
class OptimizationRun(Base, TimestampMixin):
    __tablename__ = "optimization_runs"
    __table_args__ = (Index("ix_runs_user_created", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(16), default="plan", nullable=False)  # plan|compare
    algorithm: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    feasible: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    assumptions_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    input_snapshot_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    result_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)

    objective_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    weighted_achievement: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    total_shortfall: Mapped[Decimal | None] = mapped_column(Money)
    runtime_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    config_version: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    warnings_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)

    allocations: Mapped[list["GoalAllocation"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class GoalAllocation(Base):
    __tablename__ = "goal_allocations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    optimization_run_id: Mapped[int] = mapped_column(
        ForeignKey("optimization_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    goal_id: Mapped[int | None] = mapped_column(ForeignKey("goals.id", ondelete="SET NULL"))
    goal_ref: Mapped[str] = mapped_column(String(64), nullable=False)  # solver-side goal id
    goal_name: Mapped[str] = mapped_column(String(160), default="", nullable=False)

    future_goal_cost: Mapped[Decimal] = mapped_column(Money, default=0, nullable=False)
    existing_funding: Mapped[Decimal] = mapped_column(Money, default=0, nullable=False)
    funding_gap: Mapped[Decimal] = mapped_column(Money, default=0, nullable=False)
    initial_savings_allocated: Mapped[Decimal] = mapped_column(Money, default=0, nullable=False)
    existing_assets_allocated: Mapped[Decimal] = mapped_column(Money, default=0, nullable=False)
    monthly_savings_contribution: Mapped[Decimal] = mapped_column(Money, default=0, nullable=False)
    monthly_investment_contribution: Mapped[Decimal] = mapped_column(Money, default=0, nullable=False)
    loan_principal: Mapped[Decimal] = mapped_column(Money, default=0, nullable=False)
    estimated_loan_emi: Mapped[Decimal] = mapped_column(Money, default=0, nullable=False)
    estimated_loan_interest_cost: Mapped[Decimal] = mapped_column(Money, default=0, nullable=False)
    projected_new_funding: Mapped[Decimal] = mapped_column(Money, default=0, nullable=False)
    shortfall: Mapped[Decimal] = mapped_column(Money, default=0, nullable=False)
    achievement_ratio: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=0, nullable=False)

    run: Mapped[OptimizationRun] = relationship(back_populates="allocations")


class AdminAuditLog(Base, TimestampMixin):
    """One administrative action, recorded without any financial payload or secret.

    Deliberately append-only from the API's point of view: there is no update or delete route, so
    the record of who changed a role or inspected a run cannot be rewritten through the app.
    """

    __tablename__ = "admin_audit_logs"
    __table_args__ = (Index("ix_admin_audit_created", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    actor_email: Mapped[str] = mapped_column(String(320), default="", nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    details_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)


class Scenario(Base, TimestampMixin):
    __tablename__ = "scenarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    preset: Mapped[str] = mapped_column(String(48), nullable=False)
    parameters_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)


class ScenarioRun(Base):
    __tablename__ = "scenario_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scenario_id: Mapped[int | None] = mapped_column(ForeignKey("scenarios.id", ondelete="CASCADE"))
    baseline_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("optimization_runs.id", ondelete="SET NULL")
    )
    stressed_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("optimization_runs.id", ondelete="SET NULL")
    )
    result_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    deltas_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class RecommendationRun(Base, TimestampMixin):
    """A persisted structured recommendation.

    The payload is stored verbatim so the exact explanation a user saw can be re-read later,
    together with the optimisation run it was derived from and whether the language model or
    the deterministic fallback produced the prose.
    """

    __tablename__ = "recommendation_runs"
    __table_args__ = (Index("ix_recommendations_user_created", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    optimization_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("optimization_runs.id", ondelete="SET NULL")
    )
    provider: Mapped[str] = mapped_column(String(48), default="google_gemini", nullable=False)
    model_name: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="fallback", nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    fallback_used: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    runtime_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class ModelVersion(Base, TimestampMixin):
    __tablename__ = "model_versions"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_model_name_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)  # lp|rl|hybrid|forecast
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    artifact_path: Mapped[str] = mapped_column(String(400), default="", nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    evaluated_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


__all__ = [
    "Base", "User", "PasswordResetToken", "UserPreference", "FinancialProfile", "AuditEvent",
    "IncomeSource", "Asset", "Liability", "Goal", "GoalContribution", "MonthlyRecord",
    "Transaction", "Budget", "ExpenseForecast", "ForecastEvaluation", "OptimizationRun",
    "GoalAllocation", "Scenario", "ScenarioRun", "ModelVersion", "RecommendationRun",
    "AdminAuditLog",
    "DEFAULT_EXPENSE_CATEGORIES", "INCOME_FREQUENCIES", "ASSET_TYPES", "LIABILITY_TYPES",
    "GOAL_TYPES", "GOAL_STATUSES", "MONTH_STATUSES", "TXN_KINDS", "TXN_STATUSES",
    "TXN_CLASSES", "utcnow", "func",
]
