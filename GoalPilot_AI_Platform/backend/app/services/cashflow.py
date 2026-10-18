"""Cash-flow builder and the audited surplus definition.

Why this module is explicit
---------------------------
The research audit found (finding F-06 / B-1) that ``monthly_surplus`` in the synthetic
population CSV **excludes EMI**, while the RL environment nets it out. Joining the two
naively double-counts loan payments. This module defines the single canonical surplus the
platform uses, and every consumer asks for it here.

Definitions (all monthly, all in ₹):

    income            = Σ income_source.monthly_equivalent            (active sources only)
    essential         = Σ essential expense transactions/budget lines
    discretionary     = Σ discretionary expense transactions/budget lines
    existing_emi      = Σ liability.emi_amount                        (the payment, which already
                                                                       contains principal+interest)
    surplus           = income − essential − discretionary − existing_emi

A negative surplus is a **deficit** and is returned as a negative number. It is never
clamped to zero here — clamping is a modelling choice made by the LP, not a fact about the
household, and hiding it would misreport the user's position.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

from app.core.errors import ValidationFailure

#: Expense categories treated as essential unless the user overrides them.
ESSENTIAL_CATEGORIES = frozenset(
    {
        "housing",
        "food_groceries",
        "utilities",
        "transport",
        "education",
        "healthcare",
        "insurance",
        "family",
        "loan_payments",
    }
)


@dataclass
class CashFlow:
    monthly_income: float = 0.0
    essential_expenses: float = 0.0
    discretionary_expenses: float = 0.0
    existing_emi: float = 0.0
    monthly_surplus: float = 0.0

    liquid_savings: float = 0.0
    emergency_savings: float = 0.0
    total_assets: float = 0.0
    usable_existing_investments: float = 0.0
    non_liquid_assets: float = 0.0

    outstanding_debt: float = 0.0
    emergency_months: float = 6.0
    emergency_fund_target: float = 0.0
    emergency_fund_gap: float = 0.0
    emergency_fund_progress: float = 0.0

    emi_income_ratio: float = 0.0
    emi_income_ratio_cap: float = 0.35
    risk_capacity: float = 0.5
    #: Declared preferences used by the investment-capacity derivation. They were stored but
    #: never reached the solver, which then defaulted to "medium"/"moderate" while claiming to
    #: derive the ceiling from the user's risk profile.
    liquidity_requirement: str = "medium"
    loss_ability: str = "moderate"

    savings_target: float = 0.0
    savings_target_is_mandatory: bool = False
    savings_target_attainment: float = 0.0

    # ---- the protected savings buffer, kept separate from goal funding ------------------
    #: The user's stated minimum monthly cash reserve (``preferred_cash_buffer``).
    preferred_cash_buffer: float = 0.0
    #: The single ring-fenced amount this month: ``max(monthly_savings_target, preferred
    #: buffer)``. Taking the maximum — never the sum — is what stops the savings target, the
    #: cash reserve and the emergency fund from being counted as three separate outflows.
    protected_buffer: float = 0.0
    #: desired_buffer - protected_buffer. Non-zero only when the buffer cannot be sustained.
    buffer_deficit: float = 0.0
    buffer_sustained: bool = True
    #: max(0, monthly_surplus) - protected_buffer. The only money the optimiser may allocate
    #: to goals. This is the number the LP's budget constraint is built from.
    available_goal_budget: float = 0.0
    #: "actual" when the expense split came from recorded transactions, else "projected".
    surplus_basis: str = "projected"

    earmarked_goal_funding: float = 0.0
    available_cash_for_goals: float = 0.0

    #: Which source the essential/discretionary split came from: "profile" (the user's stated
    #: monthly figures) or "month_actuals" (recorded transactions for a specific month).
    expense_basis: str = "profile"
    expense_categories_used: int = 0
    #: Number of `loan_payments` lines deliberately ignored because the EMI is already counted.
    loan_payment_lines_skipped: int = 0

    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def is_deficit(self) -> bool:
        return self.monthly_surplus < 0

    @property
    def desired_buffer(self) -> float:
        return max(self.savings_target, self.preferred_cash_buffer)

    def readiness(self) -> dict[str, Any]:
        """Financial readiness, reported separately from goal feasibility.

        A plan can fund every goal and still leave the household without an emergency reserve.
        Those are two different statements and the UI must not let one stand in for the other:
        the former is about the optimiser's arithmetic, the latter about resilience to a shock.
        """
        flags: list[str] = []
        if self.is_deficit:
            flags.append("deficit")
        if self.emi_income_ratio > self.emi_income_ratio_cap:
            flags.append("debt_stressed")
        if self.emergency_fund_gap > 0:
            flags.append("emergency_fund_incomplete")
        if self.buffer_deficit > 0:
            flags.append("buffer_shortfall")
        if not flags:
            flags.append("ready")

        # `deficit` is the most severe, then debt service, then the reserve, then the buffer.
        for status in ("deficit", "debt_stressed", "emergency_fund_incomplete", "buffer_shortfall"):
            if status in flags:
                break
        else:
            status = "ready"

        return {
            "status": status,
            "flags": flags,
            "goal_feasibility_is_separate": True,
            "note": (
                "Goal feasibility says whether the plan reaches each goal by its deadline. "
                "Readiness says whether the household could absorb a shock. A plan can be "
                "fully funded and still be financially fragile."
            ),
            "emergency_fund": {
                "target": round(self.emergency_fund_target, 2),
                "target_months": self.emergency_months,
                "current": round(self.liquid_savings, 2),
                "gap": round(self.emergency_fund_gap, 2),
                "progress": round(self.emergency_fund_progress, 6),
            },
            "protected_buffer": {
                "requested": round(self.desired_buffer, 2),
                "protected": round(self.protected_buffer, 2),
                "deficit": round(self.buffer_deficit, 2),
                "sustained": self.buffer_sustained,
            },
            "debt": {
                "existing_emi": round(self.existing_emi, 2),
                "outstanding_principal": round(self.outstanding_debt, 2),
                "emi_income_ratio": round(self.emi_income_ratio, 6),
                "emi_income_ratio_cap": self.emi_income_ratio_cap,
                "headroom": round(
                    max(0.0, self.monthly_income * self.emi_income_ratio_cap - self.existing_emi),
                    2,
                ),
            },
            "cash": {
                "available_goal_budget": round(self.available_goal_budget, 2),
                "available_cash_for_goals": round(self.available_cash_for_goals, 2),
                "requested_buffer_is_mandatory": self.savings_target_is_mandatory,
            },
            "warnings": list(self.warnings),
        }

    def solver_discretionary(self) -> float:
        """Discretionary spending *as the optimiser must see it*.

        The research LP derives its own budget as ``income - essential - discretionary -
        existing_emi``. Adding the protected buffer to the discretionary line is the one
        non-invasive way to make that budget equal :attr:`available_goal_budget` without
        touching the research solver, without shrinking the emergency-fund target (which is
        built from *essential* expenses) and without changing the EMI ceiling (which is built
        from *income*). The distortion is bounded and disclosed: the LP's own
        ``monthly_surplus`` is the goal budget, and every response reports
        ``gross_monthly_surplus`` and ``protected_buffer`` separately.
        """
        return max(0.0, self.discretionary_expenses + self.protected_buffer)


def classification_for(category: str, explicit: str | None = None) -> str:
    """Essence/discretion is the user's call, but a sensible default exists."""
    if explicit in ("essential", "discretionary", "income"):
        return explicit
    return "essential" if (category or "").lower() in ESSENTIAL_CATEGORIES else "discretionary"


def build_cashflow(
    *,
    income_sources: list[Any],
    liabilities: list[Any],
    assets: list[Any],
    profile: Any | None = None,
    expense_items: list[dict] | None = None,
    earmarked_goal_funding: float | None = None,
    emergency_months: float | None = None,
    emi_income_ratio_cap: float | None = None,
    risk_capacity: float | None = None,
    savings_target: float | None = None,
    preferred_cash_buffer: float | None = None,
    liquidity_requirement: str | None = None,
    loss_ability: str | None = None,
) -> CashFlow:
    """Assemble the canonical financial state.

    ``expense_items`` is a list of ``{"category", "amount", "classification"}`` — the
    caller decides whether these come from actual transactions, estimates, or budgets.
    Passing ``expense_items`` overrides the profile's essential/discretionary split.
    """
    cf = CashFlow()

    # ---- income --------------------------------------------------------------------
    for src in income_sources:
        if getattr(src, "is_active", True) is False:
            continue
        monthly = getattr(src, "monthly_equivalent", None)
        if monthly is None:
            from app.services.money import normalise_monthly

            monthly = normalise_monthly(src.amount, src.frequency)
        cf.monthly_income += float(monthly)

    # ---- expenses ------------------------------------------------------------------
    if expense_items is not None:
        for item in expense_items:
            category = (item.get("category") or "").lower()
            # DOUBLE-COUNT GUARD. Loan payments are represented by ``existing_emi``, which is
            # added from the liabilities below. A `loan_payments` expense line is the same
            # money viewed as a transaction, so counting both would charge the EMI twice — the
            # exact error the audit flagged in the synthetic population (finding F-06/B-1).
            if category == "loan_payments":
                cf.loan_payment_lines_skipped += 1
                continue
            amount = float(item.get("amount") or 0)
            cls = classification_for(item.get("category", ""), item.get("classification"))
            if cls == "income":
                continue
            if cls == "discretionary":
                cf.discretionary_expenses += amount
            else:
                cf.essential_expenses += amount
    elif profile is not None:
        cf.essential_expenses = float(getattr(profile, "essential_expenses", 0) or 0)
        cf.discretionary_expenses = float(getattr(profile, "discretionary_expenses", 0) or 0)

    if expense_items is not None:
        cf.expense_basis = "month_actuals"
        cf.expense_categories_used = len(
            {
                (item.get("category") or "")
                for item in expense_items
                if (item.get("category") or "").lower() != "loan_payments"
            }
        )

    # ---- debt ----------------------------------------------------------------------
    # The cash-flow impact of a liability is its EMI (principal AND interest are already
    # inside the EMI). The outstanding principal is a balance-sheet figure only and is
    # never added to the EMI — that would be the double-count the brief warns about.
    for liab in liabilities:
        cf.existing_emi += float(getattr(liab, "emi_amount", 0) or 0)
        cf.outstanding_debt += float(getattr(liab, "outstanding_principal", 0) or 0)

    cf.monthly_surplus = (
        cf.monthly_income - cf.essential_expenses - cf.discretionary_expenses - cf.existing_emi
    )

    # ---- assets --------------------------------------------------------------------
    from app.models import ASSET_TYPES  # noqa: F401  (documents the allowed set)

    for asset in assets:
        value = float(getattr(asset, "current_value", 0) or 0)
        cf.total_assets += value
        if getattr(asset, "is_liquid", True):
            cf.liquid_savings += value
        else:
            cf.non_liquid_assets += value
        if getattr(asset, "asset_type", "") == "emergency_savings":
            cf.emergency_savings += value
        if getattr(asset, "usable_for_goals", True) and getattr(asset, "is_liquid", True):
            cf.usable_existing_investments += value

    # Emergency savings sit inside liquid savings; do not count them twice in the goal pool.
    cf.liquid_savings = max(0.0, cf.liquid_savings)

    # ---- policy parameters ---------------------------------------------------------
    if profile is not None:
        emergency_months = emergency_months if emergency_months is not None else float(
            getattr(profile, "emergency_months", 6) or 6
        )
        emi_income_ratio_cap = emi_income_ratio_cap if emi_income_ratio_cap is not None else float(
            getattr(profile, "emi_income_ratio_cap", 0.35) or 0.35
        )
        risk_capacity = risk_capacity if risk_capacity is not None else float(
            getattr(profile, "risk_capacity", 0.5) or 0.5
        )
        savings_target = savings_target if savings_target is not None else float(
            getattr(profile, "monthly_savings_target", 0) or 0
        )
        preferred_cash_buffer = (
            preferred_cash_buffer
            if preferred_cash_buffer is not None
            else float(getattr(profile, "preferred_cash_buffer", 0) or 0)
        )
        cf.savings_target_is_mandatory = bool(
            getattr(profile, "savings_target_is_mandatory", False)
        )

    cf.emergency_months = float(emergency_months if emergency_months is not None else 6.0)
    cf.emi_income_ratio_cap = float(
        emi_income_ratio_cap if emi_income_ratio_cap is not None else 0.35
    )
    cf.risk_capacity = float(risk_capacity if risk_capacity is not None else 0.5)
    cf.savings_target = float(savings_target or 0)
    cf.liquidity_requirement = str(liquidity_requirement or "medium").lower()
    cf.loss_ability = str(loss_ability or "moderate").lower()

    # ---- emergency fund ------------------------------------------------------------
    cf.emergency_fund_target = cf.emergency_months * cf.essential_expenses
    cf.emergency_fund_gap = max(0.0, cf.emergency_fund_target - cf.liquid_savings)
    cf.emergency_fund_progress = (
        min(1.0, cf.liquid_savings / cf.emergency_fund_target)
        if cf.emergency_fund_target > 0
        else 1.0
    )

    # ---- ratios --------------------------------------------------------------------
    if cf.monthly_income > 0:
        cf.emi_income_ratio = cf.existing_emi / cf.monthly_income
    cf.savings_target_attainment = (
        min(1.0, max(0.0, cf.monthly_surplus) / cf.savings_target)
        if cf.savings_target > 0
        else (1.0 if cf.monthly_surplus >= 0 else 0.0)
    )

    # ---- protected savings buffer (Phase C requirement) --------------------------------
    # The savings target and the preferred cash reserve both describe money the user wants to
    # *retain*, so the buffer is their MAXIMUM, not their sum. Summing them would invent a
    # monthly obligation the user never asked for and would then "explain" a shortfall that is
    # an artefact of the model. The emergency fund is a *stock* target, not a monthly flow, so
    # it is never added either — it is already excluded from the goal cash pool below.
    cf.preferred_cash_buffer = max(0.0, float(preferred_cash_buffer or 0))
    desired_buffer = max(cf.savings_target, cf.preferred_cash_buffer)
    positive_surplus = max(0.0, cf.monthly_surplus)

    sustainable = min(desired_buffer, positive_surplus)

    if cf.savings_target_is_mandatory:
        # A mandatory buffer is honoured even when it exceeds the surplus: the shortfall is
        # then a fact about the household, and reporting it is more useful than quietly
        # reducing the amount the user said must be set aside.
        cf.protected_buffer = desired_buffer
    else:
        cf.protected_buffer = sustainable

    # The deficit is measured against what the surplus can actually support, not against our
    # own (possibly reduced) figure. Otherwise a mandatory buffer that cannot be funded from
    # this month's surplus would report a deficit of zero and look sustainable.
    cf.buffer_deficit = max(0.0, desired_buffer - sustainable)
    cf.buffer_sustained = cf.buffer_deficit <= 0.005
    cf.available_goal_budget = max(0.0, positive_surplus - cf.protected_buffer)
    cf.surplus_basis = "actual" if cf.expense_basis == "month_actuals" else "projected"

    # ---- goal pool -----------------------------------------------------------------
    # Money already earmarked to a goal is removed from the shared pool exactly once, so
    # a goal's `existing_funding` is never counted both as goal funding and as free cash.
    cf.earmarked_goal_funding = float(
        earmarked_goal_funding
        if earmarked_goal_funding is not None
        else 0.0
    )
    reserve = cf.emergency_fund_target
    cf.available_cash_for_goals = max(
        0.0, cf.liquid_savings - reserve - cf.earmarked_goal_funding
    )

    # ---- warnings (transparency, never silent) --------------------------------------
    if cf.is_deficit:
        cf.warnings.append(
            f"Monthly cash flow is a deficit of {abs(cf.monthly_surplus):,.0f}: "
            "essential and debt obligations exceed income."
        )
    if cf.emi_income_ratio > cf.emi_income_ratio_cap:
        cf.warnings.append(
            f"EMI obligations are {cf.emi_income_ratio:.0%} of income, above the configured "
            f"{cf.emi_income_ratio_cap:.0%} ceiling. New borrowing is not affordable."
        )
    if cf.emergency_fund_gap > 0 and cf.emergency_months > 0:
        cf.warnings.append(
            f"Emergency fund is {cf.emergency_fund_progress:.0%} of the "
            f"{cf.emergency_months:g}-month guideline (a planning guideline, not a universal "
            "requirement)."
        )
    if cf.emergency_months == 0:
        cf.warnings.append(
            "Emergency-fund reserve is set to 0 months. No liquidity buffer is being held."
        )
    if cf.loan_payment_lines_skipped:
        cf.warnings.append(
            f"{cf.loan_payment_lines_skipped} 'loan_payments' expense line(s) were excluded "
            "because the EMI obligation is already counted from the liabilities; including "
            "both would double-count the loan payment."
        )
    if cf.expense_basis == "month_actuals":
        cf.warnings.append(
            f"Essential and discretionary spending came from {cf.expense_categories_used} "
            "category(ies) of recorded actual transactions rather than from the stated profile "
            "figures. If some categories were not recorded, the surplus may be overstated."
        )

    if cf.buffer_deficit > 0.005:
        if cf.savings_target_is_mandatory:
            cf.warnings.append(
                f"The mandatory buffer of {desired_buffer:,.0f} exceeds the "
                f"{positive_surplus:,.0f} monthly surplus by {cf.buffer_deficit:,.0f}. The plan "
                f"protects the full {cf.protected_buffer:,.0f} as required, so "
                f"{cf.buffer_deficit:,.0f} must come from existing cash or spending cuts, and "
                f"{cf.available_goal_budget:,.0f} remains for goals."
            )
        else:
            cf.warnings.append(
                f"The requested monthly savings buffer of {desired_buffer:,.0f} cannot be met: "
                f"only {cf.protected_buffer:,.0f} of the {positive_surplus:,.0f} monthly surplus "
                f"is available, leaving a {cf.buffer_deficit:,.0f} monthly gap. The plan protects "
                f"{cf.protected_buffer:,.0f} and allocates {cf.available_goal_budget:,.0f} to "
                "goals; it does not silently reduce the buffer without saying so."
            )
    # A sustained buffer is not a warning: it is reported in the buffer block of every
    # response. Only an unmeetable request is surfaced as a warning.
    if cf.emergency_fund_gap > 0 and cf.protected_buffer <= 0 and cf.available_goal_budget > 0:
        cf.warnings.append(
            f"No monthly savings buffer was requested while the emergency fund is "
            f"{cf.emergency_fund_progress:.0%} funded. Consider protecting roughly "
            f"{min(cf.emergency_fund_gap / 12, 0.2 * cf.available_goal_budget):,.0f} per month "
            "towards it before increasing goal contributions."
        )

    if cf.monthly_income <= 0:
        raise ValidationFailure(
            "Monthly income is zero. Add at least one active income source before planning."
        )

    return cf
