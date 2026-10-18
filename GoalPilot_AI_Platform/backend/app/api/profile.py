"""Financial profile, onboarding progress, income, assets and liabilities."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import current_user, owned_or_404
from app.core.errors import ValidationFailure
from app.db import get_db
from app.models import Asset, FinancialProfile, Goal, IncomeSource, Liability, User, UserPreference
from app.schemas.common import MessageResponse
from app.schemas.finance import (
    AssetIn,
    AssetOut,
    CashFlowOut,
    IncomeSourceIn,
    IncomeSourceOut,
    LiabilityIn,
    LiabilityOut,
    OnboardingState,
    OnboardingUpdate,
    PreferencesIn,
    PreferencesOut,
    ProfileIn,
    ProfileOut,
)
from app.services.money import money_float, normalise_annual, normalise_monthly, round_money
from app.services.planner import (
    get_preferences,
    get_profile_or_none,
    load_cashflow,
    load_income_sources,
    situation_tier,
)

router = APIRouter(tags=["profile"])


# --------------------------------------------------------------------------------------
# preferences
# --------------------------------------------------------------------------------------
@router.get("/settings/preferences", response_model=PreferencesOut)
def read_preferences(user: User = Depends(current_user), db: Session = Depends(get_db)):
    pref = get_preferences(db, user.id)
    db.commit()
    return PreferencesOut(
        currency=pref.currency,
        locale=pref.locale,
        risk_tolerance=pref.risk_tolerance,
        loss_ability=pref.loss_ability,
        liquidity_requirement=pref.liquidity_requirement,
        assumptions=json.loads(pref.assumptions_json or "{}"),
        onboarding_step=pref.onboarding_step,
        onboarding_completed=pref.onboarding_completed,
    )


@router.put("/settings/preferences", response_model=PreferencesOut)
def update_preferences(
    payload: PreferencesIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    pref = get_preferences(db, user.id)
    pref.currency = payload.currency
    pref.locale = payload.locale
    pref.risk_tolerance = payload.risk_tolerance
    pref.loss_ability = payload.loss_ability
    pref.liquidity_requirement = payload.liquidity_requirement
    pref.assumptions_json = json.dumps(payload.assumptions)
    db.commit()
    db.refresh(pref)
    return PreferencesOut(
        currency=pref.currency,
        locale=pref.locale,
        risk_tolerance=pref.risk_tolerance,
        loss_ability=pref.loss_ability,
        liquidity_requirement=pref.liquidity_requirement,
        assumptions=json.loads(pref.assumptions_json or "{}"),
        onboarding_step=pref.onboarding_step,
        onboarding_completed=pref.onboarding_completed,
    )


# --------------------------------------------------------------------------------------
# profile
# --------------------------------------------------------------------------------------
def _profile_out(profile: FinancialProfile) -> ProfileOut:
    return ProfileOut(
        id=profile.id,
        monthly_income=money_float(profile.monthly_income),
        essential_expenses=money_float(profile.essential_expenses),
        discretionary_expenses=money_float(profile.discretionary_expenses),
        monthly_savings_target=money_float(profile.monthly_savings_target),
        savings_target_is_mandatory=profile.savings_target_is_mandatory,
        preferred_cash_buffer=money_float(profile.preferred_cash_buffer),
        willing_to_adjust_discretionary=profile.willing_to_adjust_discretionary,
        emergency_months=float(profile.emergency_months),
        emi_income_ratio_cap=float(profile.emi_income_ratio_cap),
        risk_capacity=float(profile.risk_capacity),
        inflation_assumption=float(profile.inflation_assumption),
        investment_return_assumption=float(profile.investment_return_assumption),
        savings_return_assumption=float(profile.savings_return_assumption),
        loan_interest_assumption=float(profile.loan_interest_assumption),
    )


@router.get("/profile")
def read_profile(user: User = Depends(current_user), db: Session = Depends(get_db)):
    profile = get_profile_or_none(db, user.id)
    if profile is None:
        return {"profile": None, "summary": None}
    return {"profile": _profile_out(profile), "summary": _summary(db, user)}


@router.put("/profile", response_model=ProfileOut)
def upsert_profile(
    payload: ProfileIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    profile = get_profile_or_none(db, user.id)
    if profile is None:
        profile = FinancialProfile(user_id=user.id)
        db.add(profile)
    # ``monthly_income`` here is only a convenience aggregate: the planner builds income from the
    # income sources (see ``cashflow.build_cashflow``). Onboarding records income sources in an
    # earlier step and has no income field of its own, so it legitimately submits 0 — fill the
    # aggregate from the sources rather than storing a figure that contradicts them.
    monthly_income = round_money(payload.monthly_income)
    if monthly_income <= 0:
        sources = load_income_sources(db, user.id)
        derived = sum(float(source.monthly_equivalent or 0) for source in sources)
        if derived > 0:
            monthly_income = round_money(derived)
    profile.monthly_income = monthly_income
    profile.essential_expenses = round_money(payload.essential_expenses)
    profile.discretionary_expenses = round_money(payload.discretionary_expenses)
    profile.monthly_savings_target = round_money(payload.monthly_savings_target)
    profile.savings_target_is_mandatory = payload.savings_target_is_mandatory
    profile.preferred_cash_buffer = round_money(payload.preferred_cash_buffer)
    profile.willing_to_adjust_discretionary = payload.willing_to_adjust_discretionary
    profile.emergency_months = payload.emergency_months
    profile.emi_income_ratio_cap = payload.emi_income_ratio_cap
    profile.risk_capacity = payload.risk_capacity
    profile.inflation_assumption = payload.inflation_assumption
    profile.investment_return_assumption = payload.investment_return_assumption
    profile.savings_return_assumption = payload.savings_return_assumption
    profile.loan_interest_assumption = payload.loan_interest_assumption
    db.commit()
    db.refresh(profile)
    return _profile_out(profile)


def _summary(db: Session, user: User) -> dict:
    try:
        cf = load_cashflow(db, user.id)
    except ValidationFailure:
        return None
    data = cf.as_dict()
    data["is_deficit"] = cf.is_deficit
    data["situation_tier"] = situation_tier(cf)
    return data


@router.get("/profile/summary", response_model=CashFlowOut)
def profile_summary(user: User = Depends(current_user), db: Session = Depends(get_db)):
    summary = _summary(db, user)
    if summary is None:
        raise ValidationFailure(
            "A financial profile and at least one income source are required before a summary "
            "can be derived."
        )
    return CashFlowOut(**summary)


# --------------------------------------------------------------------------------------
# onboarding
# --------------------------------------------------------------------------------------
@router.get("/onboarding", response_model=OnboardingState)
def read_onboarding(user: User = Depends(current_user), db: Session = Depends(get_db)):
    pref = get_preferences(db, user.id)
    db.commit()
    income = db.execute(
        select(IncomeSource).where(IncomeSource.user_id == user.id)
    ).scalars().all()
    assets = db.execute(select(Asset).where(Asset.user_id == user.id)).scalars().all()
    liabilities = db.execute(select(Liability).where(Liability.user_id == user.id)).scalars().all()
    goals = db.execute(select(Goal).where(Goal.user_id == user.id)).scalars().all()
    has_profile = get_profile_or_none(db, user.id) is not None

    if not has_profile or not income:
        hint = "Add your financial profile and at least one income source."
    elif not goals:
        hint = "Create at least one financial goal so the optimiser has something to solve."
    elif not pref.onboarding_completed:
        hint = "Review the summary and complete onboarding."
    else:
        hint = "Onboarding is complete. Open the monthly workspace to record this month."
    return OnboardingState(
        step=pref.onboarding_step,
        completed=pref.onboarding_completed,
        income_count=len(income),
        asset_count=len(assets),
        liability_count=len(liabilities),
        goal_count=len(goals),
        has_profile=has_profile,
        next_step_hint=hint,
    )


@router.put("/onboarding", response_model=OnboardingState)
def update_onboarding(
    payload: OnboardingUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    pref = get_preferences(db, user.id)
    pref.onboarding_step = payload.step
    db.commit()
    return read_onboarding(user=user, db=db)


@router.post("/onboarding/complete", response_model=MessageResponse)
def complete_onboarding(user: User = Depends(current_user), db: Session = Depends(get_db)):
    pref = get_preferences(db, user.id)
    if get_profile_or_none(db, user.id) is None:
        raise ValidationFailure("Save a financial profile before completing onboarding.")
    income = db.execute(
        select(IncomeSource).where(IncomeSource.user_id == user.id)
    ).scalars().all()
    if not income:
        raise ValidationFailure("Add at least one income source before completing onboarding.")
    goals = db.execute(select(Goal).where(Goal.user_id == user.id)).scalars().all()
    pref.onboarding_completed = True
    db.commit()
    if not goals:
        return MessageResponse(
            message="Onboarding complete. Add at least one goal to generate a financial plan."
        )
    return MessageResponse(message="Onboarding complete.")


# --------------------------------------------------------------------------------------
# income sources
# --------------------------------------------------------------------------------------
def _income_out(src: IncomeSource) -> IncomeSourceOut:
    monthly = float(src.monthly_equivalent)
    return IncomeSourceOut(
        id=src.id,
        source_type=src.source_type,
        label=src.label,
        amount=money_float(src.amount),
        frequency=src.frequency,
        stability=src.stability,
        is_recurring=src.is_recurring,
        expected_day=src.expected_day,
        is_active=src.is_active,
        monthly_equivalent=round(monthly, 2),
        annual_equivalent=round(monthly * 12, 2),
    )


@router.get("/income-sources", response_model=list[IncomeSourceOut])
def list_income(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(
        select(IncomeSource).where(IncomeSource.user_id == user.id).order_by(IncomeSource.id)
    ).scalars()
    return [_income_out(r) for r in rows]


@router.post("/income-sources", response_model=IncomeSourceOut, status_code=201)
def create_income(
    payload: IncomeSourceIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    monthly = normalise_monthly(payload.amount, payload.frequency)
    src = IncomeSource(
        user_id=user.id,
        source_type=payload.source_type,
        label=payload.label,
        amount=round_money(payload.amount),
        frequency=payload.frequency,
        monthly_equivalent=round_money(monthly),
        stability=payload.stability,
        is_recurring=payload.is_recurring,
        expected_day=payload.expected_day,
        is_active=payload.is_active,
    )
    db.add(src)
    db.commit()
    db.refresh(src)
    if src.frequency != "monthly":
        _sync_profile_income(db, user.id)
    return _income_out(src)


@router.put("/income-sources/{income_id}", response_model=IncomeSourceOut)
def update_income(
    income_id: int,
    payload: IncomeSourceIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    src = owned_or_404(db, IncomeSource, user, income_id)
    src.source_type = payload.source_type
    src.label = payload.label
    src.amount = round_money(payload.amount)
    src.frequency = payload.frequency
    src.monthly_equivalent = round_money(normalise_monthly(payload.amount, payload.frequency))
    src.stability = payload.stability
    src.is_recurring = payload.is_recurring
    src.expected_day = payload.expected_day
    src.is_active = payload.is_active
    db.commit()
    db.refresh(src)
    _sync_profile_income(db, user.id)
    return _income_out(src)


@router.delete("/income-sources/{income_id}", response_model=MessageResponse)
def delete_income(
    income_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    src = owned_or_404(db, IncomeSource, user, income_id)
    db.delete(src)
    db.commit()
    _sync_profile_income(db, user.id)
    return MessageResponse(message="Income source removed.")


def _sync_profile_income(db: Session, user_id: int) -> None:
    """Keep the profile's headline income in step with the normalised income sources.

    The profile value is a convenience aggregate; the income sources are the source of
    truth for the planner.
    """
    profile = get_profile_or_none(db, user_id)
    if profile is None:
        return
    rows = db.execute(
        select(IncomeSource).where(
            IncomeSource.user_id == user_id, IncomeSource.is_active.is_(True)
        )
    ).scalars().all()
    if not rows:
        return
    total = sum(float(r.monthly_equivalent) for r in rows)
    profile.monthly_income = round_money(total)
    db.commit()


# --------------------------------------------------------------------------------------
# assets
# --------------------------------------------------------------------------------------
@router.get("/assets", response_model=list[AssetOut])
def list_assets(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(Asset).where(Asset.user_id == user.id).order_by(Asset.id)).scalars()
    return [AssetOut(**{**_asset_dict(r)}) for r in rows]


def _asset_dict(row: Asset) -> dict:
    return {
        "id": row.id,
        "asset_type": row.asset_type,
        "label": row.label,
        "current_value": money_float(row.current_value),
        "is_liquid": row.is_liquid,
        "usable_for_goals": row.usable_for_goals,
        "annual_return": float(row.annual_return),
        "risk_score": float(row.risk_score),
        "earmarked_goal_id": row.earmarked_goal_id,
    }


@router.post("/assets", response_model=AssetOut, status_code=201)
def create_asset(
    payload: AssetIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if payload.earmarked_goal_id is not None:
        owned_or_404(db, Goal, user, payload.earmarked_goal_id)
    row = Asset(
        user_id=user.id,
        asset_type=payload.asset_type,
        label=payload.label,
        current_value=round_money(payload.current_value),
        is_liquid=payload.is_liquid,
        usable_for_goals=payload.usable_for_goals,
        annual_return=payload.annual_return,
        risk_score=payload.risk_score,
        earmarked_goal_id=payload.earmarked_goal_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return AssetOut(**_asset_dict(row))


@router.put("/assets/{asset_id}", response_model=AssetOut)
def update_asset(
    asset_id: int,
    payload: AssetIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    row = owned_or_404(db, Asset, user, asset_id)
    if payload.earmarked_goal_id is not None:
        owned_or_404(db, Goal, user, payload.earmarked_goal_id)
    row.asset_type = payload.asset_type
    row.label = payload.label
    row.current_value = round_money(payload.current_value)
    row.is_liquid = payload.is_liquid
    row.usable_for_goals = payload.usable_for_goals
    row.annual_return = payload.annual_return
    row.risk_score = payload.risk_score
    row.earmarked_goal_id = payload.earmarked_goal_id
    db.commit()
    db.refresh(row)
    return AssetOut(**_asset_dict(row))


@router.delete("/assets/{asset_id}", response_model=MessageResponse)
def delete_asset(
    asset_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    row = owned_or_404(db, Asset, user, asset_id)
    db.delete(row)
    db.commit()
    return MessageResponse(message="Asset removed.")


# --------------------------------------------------------------------------------------
# liabilities
# --------------------------------------------------------------------------------------
def _liability_dict(row: Liability) -> dict:
    principal = float(row.outstanding_principal)
    emi = float(row.emi_amount)
    tenure = int(row.remaining_tenure_months)
    total_repayment = emi * tenure if tenure else 0.0
    return {
        "id": row.id,
        "liability_type": row.liability_type,
        "label": row.label,
        "outstanding_principal": principal,
        "annual_interest_rate": float(row.annual_interest_rate),
        "emi_amount": emi,
        "remaining_tenure_months": tenure,
        # Reported for transparency. The EMI already contains principal + interest, so this
        # is never added to the monthly obligation.
        "total_repayment_if_held_to_tenure": round(total_repayment, 2),
        "total_interest_if_held_to_tenure": round(max(0.0, total_repayment - principal), 2),
    }


@router.get("/liabilities", response_model=list[LiabilityOut])
def list_liabilities(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(
        select(Liability).where(Liability.user_id == user.id).order_by(Liability.id)
    ).scalars()
    return [LiabilityOut(**_liability_dict(r)) for r in rows]


@router.post("/liabilities", response_model=LiabilityOut, status_code=201)
def create_liability(
    payload: LiabilityIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    row = Liability(
        user_id=user.id,
        liability_type=payload.liability_type,
        label=payload.label,
        outstanding_principal=round_money(payload.outstanding_principal),
        annual_interest_rate=payload.annual_interest_rate,
        emi_amount=round_money(payload.emi_amount),
        remaining_tenure_months=payload.remaining_tenure_months,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return LiabilityOut(**_liability_dict(row))


@router.put("/liabilities/{liability_id}", response_model=LiabilityOut)
def update_liability(
    liability_id: int,
    payload: LiabilityIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    row = owned_or_404(db, Liability, user, liability_id)
    row.liability_type = payload.liability_type
    row.label = payload.label
    row.outstanding_principal = round_money(payload.outstanding_principal)
    row.annual_interest_rate = payload.annual_interest_rate
    row.emi_amount = round_money(payload.emi_amount)
    row.remaining_tenure_months = payload.remaining_tenure_months
    db.commit()
    db.refresh(row)
    return LiabilityOut(**_liability_dict(row))


@router.delete("/liabilities/{liability_id}", response_model=MessageResponse)
def delete_liability(
    liability_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    row = owned_or_404(db, Liability, user, liability_id)
    db.delete(row)
    db.commit()
    return MessageResponse(message="Liability removed.")
