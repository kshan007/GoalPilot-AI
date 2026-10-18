"""Loan discovery and financing analysis.

Everything numeric here is deterministic and reproducible: EMI, total repayment, total
interest, an IRR-based APR, the effect on the monthly budget and a rate-shock sensitivity.
The module never treats loan proceeds as income, never decides eligibility and never
recommends borrowing merely because it makes a goal affordable today.
"""
from __future__ import annotations

import datetime as dt
import math
from typing import Any, Iterable

from app.config import get_settings
from app.providers import loans as loan_provider
from app.providers import registry
from app.providers.base import (
    ESTIMATED_SCENARIO,
    HISTORICAL_BENCHMARK,
    PERSONALISED_OFFER,
    PUBLISHED_LENDER_RATE,
    RATE_CLASS_LABELS,
    NormalizedLoan,
    iso,
    utcnow,
)
from app.services.cashflow import CashFlow

DISCLOSURE = (
    "Loan information is published product information, not an offer, not an approval and not "
    "a personalised rate. Eligibility is never asserted. Borrowing increases total cost "
    "through interest and creates a fixed obligation; the platform does not originate, approve "
    "or execute any loan."
)

MAX_SAFE_EMI_SHARE_OF_SURPLUS = 0.5   # a new EMI may not consume more than half the surplus
MIN_EMERGENCY_PROGRESS_FOR_NEW_DEBT = 0.5


# --------------------------------------------------------------------------------------
# core maths
# --------------------------------------------------------------------------------------
def monthly_rate(annual_rate: float) -> float:
    return float(annual_rate) / 12.0


def emi(principal: float, annual_rate: float, months: int) -> float:
    """Equated monthly instalment (end-of-month payments)."""
    principal = float(principal)
    months = int(months)
    if principal <= 0 or months <= 0:
        return 0.0
    r = monthly_rate(annual_rate)
    if abs(r) < 1e-12:
        return principal / months
    factor = (1 + r) ** months
    return principal * r * factor / (factor - 1)


def total_repayment(principal: float, annual_rate: float, months: int) -> float:
    return emi(principal, annual_rate, months) * max(0, int(months))


def amortisation(principal: float, annual_rate: float, months: int) -> list[dict[str, float]]:
    """Month-by-month split. Returned in full so the UI can show the schedule."""
    payment = emi(principal, annual_rate, months)
    r = monthly_rate(annual_rate)
    balance = float(principal)
    rows: list[dict[str, float]] = []
    for month in range(1, int(months) + 1):
        interest = balance * r
        principal_part = payment - interest
        if month == int(months):
            principal_part = balance
            payment_actual = balance + interest
        else:
            payment_actual = payment
        balance = max(0.0, balance - principal_part)
        rows.append(
            {
                "month": month,
                "payment": round(payment_actual, 2),
                "interest": round(interest, 2),
                "principal": round(principal_part, 2),
                "balance": round(balance, 2),
            }
        )
    return rows


def apr(principal: float, annual_rate: float, months: int, upfront_fees: float = 0.0) -> float | None:
    """Effective annual cost including upfront fees, solved by bisection on the monthly IRR.

    ``net_proceeds = EMI x annuity(i, n)``; we solve for ``i`` and annualise it. With zero fees
    the result equals the nominal rate, which is a useful self-check (tested).
    """
    principal = float(principal)
    months = int(months)
    if principal <= 0 or months <= 0:
        return None
    net = principal - max(0.0, float(upfront_fees))
    if net <= 0:
        return None
    payment = emi(principal, annual_rate, months)

    def pv(rate: float) -> float:
        if abs(rate) < 1e-12:
            return payment * months
        return payment * (1 - (1 + rate) ** -months) / rate

    low, high = 0.0, 1.0  # 0% .. 100% per month
    if pv(low) < net:  # impossible: payments never repay the net proceeds
        return None
    if pv(high) > net:  # need a higher rate than 100%/month: pathological input
        return None
    for _ in range(200):
        mid = (low + high) / 2
        if pv(mid) > net:
            low = mid
        else:
            high = mid
    monthly = (low + high) / 2
    return (1 + monthly) ** 12 - 1


# --------------------------------------------------------------------------------------
# affordability
# --------------------------------------------------------------------------------------
def affordability(proposed_emi: float, cashflow: CashFlow, *, existing_new_emi: float = 0.0) -> dict[str, Any]:
    """Can the household carry this EMI without breaking the buffer or the EMI ceiling?"""
    budget = float(cashflow.available_goal_budget)
    total_new = float(proposed_emi) + float(existing_new_emi)
    remaining_after_emi = budget - total_new

    emi_headroom = max(
        0.0,
        cashflow.monthly_income * cashflow.emi_income_ratio_cap
        - cashflow.existing_emi
        - existing_new_emi,
    )
    checks = {
        "emi_within_income_ceiling": total_new <= emi_headroom + 1e-6,
        "emi_within_goal_budget": total_new <= budget + 1e-6,
        "emi_within_half_of_budget": total_new <= MAX_SAFE_EMI_SHARE_OF_SURPLUS * budget + 1e-6,
        "protected_buffer_preserved": cashflow.protected_buffer <= max(0.0, cashflow.monthly_surplus) + 1e-6,
        "emergency_fund_adequate": cashflow.emergency_fund_progress >= MIN_EMERGENCY_PROGRESS_FOR_NEW_DEBT,
        "no_existing_deficit": cashflow.monthly_surplus > 0,
    }
    blocking = [name for name, ok in checks.items() if not ok and name in {
        "emi_within_income_ceiling", "no_existing_deficit", "emi_within_goal_budget",
    }]
    cautions = [name for name, ok in checks.items() if not ok and name not in set(blocking)]

    if blocking:
        verdict = "not_affordable"
    elif cautions:
        verdict = "affordable_with_caution"
    else:
        verdict = "affordable"

    return {
        "proposed_emi": round(total_new, 2),
        "available_goal_budget": round(budget, 2),
        "goal_budget_after_emi": round(remaining_after_emi, 2),
        "emi_headroom_under_income_ceiling": round(emi_headroom, 2),
        "emi_share_of_income": round(total_new / cashflow.monthly_income, 4) if cashflow.monthly_income else None,
        "checks": checks,
        "blocking_checks": blocking,
        "cautions": cautions,
        "verdict": verdict,
        "notes": [
            "The EMI is paid from the money left after the protected savings buffer, never from "
            "the buffer itself.",
            "The income ceiling is the user's own configured EMI-to-income cap; it is not a "
            "lender's underwriting rule.",
        ],
    }


def rate_sensitivity(principal: float, annual_rate: float, months: int) -> dict[str, Any]:
    base = emi(principal, annual_rate, months)
    rows = []
    for bump in (0.0, 0.01, 0.02, 0.03):
        shocked = emi(principal, annual_rate + bump, months)
        rows.append(
            {
                "rate": round(annual_rate + bump, 6),
                "rate_bump_bp": int(round(bump * 10_000)),
                "emi": round(shocked, 2),
                "emi_increase": round(shocked - base, 2),
                "total_interest": round(shocked * months - principal, 2),
            }
        )
    return {
        "base_rate": round(annual_rate, 6),
        "rows": rows,
        "note": (
            "A floating-rate loan reprices with the benchmark. These rows show the arithmetic "
            "effect of a rate rise, not a forecast that rates will rise."
        ),
    }


# --------------------------------------------------------------------------------------
# alternatives
# --------------------------------------------------------------------------------------
def alternatives(
    *,
    gap: float,
    monthly_capacity: float,
    months_remaining: int,
    annual_rate: float,
    tenure_months: int,
    total_interest: float,
) -> list[dict[str, Any]]:
    """Compare borrowing against saving, waiting, shrinking the target or reallocating."""
    out: list[dict[str, Any]] = []
    monthly_capacity = max(0.0, float(monthly_capacity))

    if monthly_capacity > 0 and gap > 0:
        months_to_save = math.ceil(gap / monthly_capacity)
        out.append(
            {
                "option": "save_instead",
                "description": (
                    f"Save {monthly_capacity:,.0f}/month instead of borrowing: the full "
                    f"{gap:,.0f} is reached in about {months_to_save} months, with no interest."
                ),
                "months_needed": months_to_save,
                "interest_cost_avoided": round(total_interest, 2),
                "affordable": months_to_save <= max(months_remaining, 0) if months_remaining else None,
            }
        )
        if months_remaining and months_to_save > months_remaining:
            out.append(
                {
                    "option": "extend_deadline",
                    "description": (
                        f"The goal would need about {months_to_save - months_remaining} more "
                        f"months than the current deadline if it is funded from savings alone."
                    ),
                    "extra_months": months_to_save - months_remaining,
                    "affordable": True,
                }
            )
    elif monthly_capacity <= 0:
        out.append(
            {
                "option": "no_capacity",
                "description": (
                    "There is no monthly capacity to save towards this gap, and borrowing "
                    "would create an obligation the budget cannot service."
                ),
                "affordable": False,
            }
        )

    if months_remaining and monthly_capacity > 0:
        achievable = monthly_capacity * months_remaining
        if achievable < gap:
            out.append(
                {
                    "option": "reduce_target",
                    "description": (
                        f"Reducing the target by {gap - achievable:,.0f} would make it reachable "
                        f"by the deadline on the current capacity."
                    ),
                    "achievable_amount": round(achievable, 2),
                    "shortfall_if_unchanged": round(gap - achievable, 2),
                    "affordable": True,
                }
            )

    out.append(
        {
            "option": "reallocate_existing",
            "description": (
                "Reallocating existing earmarked goal balances could close part of the gap "
                "without new debt, at the cost of delaying the goal the money came from."
            ),
            "affordable": None,
            "note": "Not modelled automatically: it requires the user's decision on priorities.",
        }
    )
    out.append(
        {
            "option": "borrow",
            "description": (
                f"Borrowing at {annual_rate:.2%} over {tenure_months} months costs "
                f"{total_interest:,.0f} in interest and fixes the payment for the tenure "
                "(before any rate reset on a floating product)."
            ),
            "interest_cost": round(total_interest, 2),
            "affordable": None,
            "note": "Only viable if the affordability verdict says so.",
        }
    )
    return out


# --------------------------------------------------------------------------------------
# quote analysis
# --------------------------------------------------------------------------------------
def analyse_quote(
    *,
    principal: float,
    annual_rate: float,
    tenure_months: int,
    cashflow: CashFlow,
    processing_fee_pct: float | None = None,
    processing_fee_flat: float = 0.0,
    other_fees: float = 0.0,
    rate_type: str = "fixed",
    gap: float | None = None,
    months_remaining: int | None = None,
    include_schedule: bool = False,
    offer_is_personal: bool = False,
    offer_source: str | None = None,
) -> dict[str, Any]:
    payment = emi(principal, annual_rate, tenure_months)
    total = payment * tenure_months
    interest = total - principal
    fee_from_pct = principal * (processing_fee_pct or 0.0)
    upfront = fee_from_pct + float(processing_fee_flat or 0.0) + float(other_fees or 0.0)
    effective_apr = apr(principal, annual_rate, tenure_months, upfront)

    result = {
        "generated_at": iso(utcnow()),
        "input": {
            "principal": round(principal, 2),
            "annual_rate": round(annual_rate, 6),
            "tenure_months": int(tenure_months),
            "rate_type": rate_type,
            "processing_fee_pct": processing_fee_pct,
            "processing_fee_flat": round(float(processing_fee_flat or 0), 2),
            "other_fees": round(float(other_fees or 0), 2),
        },
        "repayment": {
            "monthly_emi": round(payment, 2),
            "total_repayment": round(total, 2),
            "total_interest": round(interest, 2),
            "total_fees": round(upfront, 2),
            "total_cost_of_credit": round(interest + upfront, 2),
            "nominal_annual_rate": round(annual_rate, 6),
            "apr_including_fees": round(effective_apr, 6) if effective_apr is not None else None,
            "apr_note": (
                "APR is an IRR over the actual cash flows (net proceeds today, EMIs for the "
                "tenure) and therefore includes the upfront fees entered. It is not the "
                "lender's advertised APR."
            ),
        },
        "affordability": affordability(payment, cashflow),
        "rate_sensitivity": rate_sensitivity(principal, annual_rate, tenure_months),
        "alternatives": alternatives(
            gap=gap if gap is not None else principal,
            monthly_capacity=cashflow.available_goal_budget,
            months_remaining=months_remaining or tenure_months,
            annual_rate=annual_rate,
            tenure_months=tenure_months,
            total_interest=interest,
        ),
        "rate_class": PERSONALISED_OFFER if offer_is_personal else ESTIMATED_SCENARIO,
        "rate_class_label": RATE_CLASS_LABELS[
            PERSONALISED_OFFER if offer_is_personal else ESTIMATED_SCENARIO
        ],
        "offer_source": offer_source,
        "proceeds_are_not_income": True,
        "disclosure": DISCLOSURE,
    }
    if include_schedule:
        result["schedule"] = amortisation(principal, annual_rate, tenure_months)
    return result


# --------------------------------------------------------------------------------------
# discovery
# --------------------------------------------------------------------------------------
#: Categories the product promises to cover. When a lender product is missing for one of them
#: the response says so and offers a labelled scenario rather than silence or a fabrication.
DEFAULT_SCENARIO_CATEGORIES = ("personal", "education", "secured")


def resolve_scenario_rate(explicit: float | None, cashflow: CashFlow) -> tuple[float, str]:
    """Pick the rate for a category scenario and say exactly where it came from.

    Order: an explicit per-request value, then the user's own configured loan assumption, then
    the deployment default. Every branch is explicit; none of them pretends to be a lender rate.
    """
    if explicit is not None and 0.0 < float(explicit) < 0.5:
        return float(explicit), "request_scenario_rate"
    profile_rate = getattr(cashflow, "loan_interest_assumption", None)
    if profile_rate and 0.0 < float(profile_rate) < 0.5:
        return float(profile_rate), "user_profile_loan_interest_assumption"
    configured = float(getattr(get_settings(), "default_loan_scenario_rate", 0.12) or 0.12)
    if 0.0 < configured < 0.5:
        return configured, "deployment_default"
    return 0.12, "platform_fallback"


def build_category_scenario(
    *,
    category: str,
    principal: float,
    tenure_months: int,
    rate: float,
    rate_source: str,
    cashflow: CashFlow,
) -> dict[str, Any]:
    """A described assumption, not a product.

    ``published_rate`` is deliberately ``None``: nothing here was published by a lender, and a
    consumer that reads ``published_rate`` must not be able to mistake this for a quote.
    """
    payment = emi(principal, rate, tenure_months)
    total = payment * tenure_months
    return {
        "product_id": f"scenario_{category}",
        "lender": "Category scenario (no published product available)",
        "product_name": f"{category.title()} loan — estimated scenario",
        "category": category,
        "published_rate": None,
        "scenario_rate": round(float(rate), 6),
        "rate_basis": "modelling_assumption",
        "rate_class": ESTIMATED_SCENARIO,
        "rate_class_label": RATE_CLASS_LABELS[ESTIMATED_SCENARIO],
        "configurable": True,
        "assumption_source": rate_source,
        "data_quality": "category_scenario",
        "source_url": "",
        "retrieved_at": iso(utcnow()),
        "effective_date": None,
        "is_personalised_offer": False,
        "indicative": {
            "assumed_principal": round(principal, 2),
            "assumed_tenure_months": int(tenure_months),
            "monthly_emi": round(payment, 2),
            "total_repayment": round(total, 2),
            "total_interest": round(total - principal, 2),
            "apr_including_known_fees": None,
            "basis": (
                f"Computed from an explicitly labelled assumption of {rate:.2%} "
                f"({rate_source}), not from a published rate. Change the assumption to see a "
                "different scenario."
            ),
        },
        "affordability": affordability(payment, cashflow),
        "suitability_notes": [
            "No published product for this category was available from the integrated sources, "
            "so this row is a scenario and must not be read as a market rate.",
            "Only interest cost is modelled; fees, insurance and eligibility are unknown for "
            "this category.",
        ],
    }


def discover(
    *,
    cashflow: CashFlow,
    principal: float = 500_000.0,
    tenure_months: int = 48,
    categories: list[str] | None = None,
    include_schedule: bool = False,
    scenario_rate: float | None = None,
) -> dict[str, Any]:
    outcomes = registry.loan_outcomes()
    provider_rows = [o.as_dict() for o in outcomes]
    records: list[NormalizedLoan] = []
    benchmarks: list[dict[str, Any]] = []

    for outcome in outcomes:
        if outcome.provider == loan_provider.PROVIDER_NAME and outcome.records:
            records.extend(outcome.records)  # type: ignore[arg-type]
        elif outcome.provider == loan_provider.WALR_PROVIDER and outcome.records:
            benchmarks.extend(outcome.records)  # type: ignore[arg-type]

    if categories:
        wanted = {c.strip().lower() for c in categories if c.strip()}
        records = [r for r in records if r.category.lower() in wanted]

    options: list[dict[str, Any]] = []
    for record in records:
        rate = record.published_rate
        option = record.as_dict()
        option["rate_class_label"] = RATE_CLASS_LABELS.get(record.rate_class, "")
        option.setdefault("scenario_rate", None)
        option.setdefault("configurable", False)
        if rate is None:
            option["indicative"] = None
            option["suitability_notes"] = [
                "No published rate was captured for this product, so no repayment figure can "
                "be computed. It is listed for information only."
            ]
            options.append(option)
            continue
        payment = emi(principal, rate, tenure_months)
        fee_pct = record.processing_fee_pct or 0.0
        upfront = principal * fee_pct + (record.processing_fee_flat or 0.0)
        option["indicative"] = {
            "assumed_principal": round(principal, 2),
            "assumed_tenure_months": int(tenure_months),
            "monthly_emi": round(payment, 2),
            "total_repayment": round(payment * tenure_months, 2),
            "total_interest": round(payment * tenure_months - principal, 2),
            "apr_including_known_fees": (
                round(apr(principal, rate, tenure_months, upfront), 6)
                if apr(principal, rate, tenure_months, upfront) is not None
                else None
            ),
            "basis": (
                "Computed from the product's published minimum rate and the principal/tenure "
                "you supplied. The lender's actual offer will differ."
            ),
        }
        option["affordability"] = affordability(payment, cashflow)
        option["suitability_notes"] = _loan_notes(record, payment, cashflow)
        options.append(option)

    options.sort(
        key=lambda item: (
            item.get("indicative", {}).get("total_interest", float("inf"))
            if item.get("indicative")
            else float("inf")
        )
    )

    # ---- category coverage: name the gap, then quote an assumption ---------------------
    covered = {item["category"] for item in options}
    requested = list(dict.fromkeys(categories or list(DEFAULT_SCENARIO_CATEGORIES)))
    rate, rate_source = resolve_scenario_rate(scenario_rate, cashflow)
    scenarios = [
        build_category_scenario(
            category=category,
            principal=principal,
            tenure_months=tenure_months,
            rate=rate,
            rate_source=rate_source,
            cashflow=cashflow,
        )
        for category in requested
        if category not in covered
    ]
    coverage = {
        "requested_categories": requested,
        "covered_by_published_products": sorted(covered & set(requested)),
        "scenario_only": [s["category"] for s in scenarios],
        "unavailable": [s["category"] for s in scenarios],
        "note": (
            "Categories listed as scenario_only have no published product in the integrated "
            "sources. They are shown as a labelled assumption so the gap is visible; the "
            "platform does not fill it with an invented product."
        ),
    }

    missing: list[str] = []
    if scenarios:
        missing.append(
            "No published lender product was available for: "
            + ", ".join(s["category"] for s in scenarios)
            + f". Those rows are estimated scenarios at {rate:.2%} "
            f"({rate_source}), not market rates."
        )
    if not options:
        missing.append(
            "No lender product could be retrieved or read from the bundled reference. No loan "
            "option is shown rather than an invented one."
        )
    if not benchmarks:
        missing.append("The RBI WALR benchmark dataset was not available.")
    if all(not item.get("indicative") for item in options) and options:
        missing.append("Published rates were unavailable, so no repayment figures are computed.")

    return {
        "generated_at": iso(utcnow()),
        "assumed_principal": round(principal, 2),
        "assumed_tenure_months": int(tenure_months),
        "providers": provider_rows,
        "options": options,
        "option_count": len(options),
        "scenarios": scenarios,
        "scenario_count": len(scenarios),
        "category_coverage": coverage,
        "benchmarks": benchmarks,
        "rate_classes": RATE_CLASS_LABELS,
        "affordability_context": {
            "available_goal_budget": round(cashflow.available_goal_budget, 2),
            "protected_buffer": round(cashflow.protected_buffer, 2),
            "existing_emi": round(cashflow.existing_emi, 2),
            "emi_income_ratio_cap": cashflow.emi_income_ratio_cap,
            "emergency_fund_progress": round(cashflow.emergency_fund_progress, 4),
        },
        "missing_information": missing,
        "disclosure": DISCLOSURE,
        "not_advice": True,
        "does_not_originate_loans": True,
    }


def _loan_notes(record: NormalizedLoan, payment: float, cashflow: CashFlow) -> list[str]:
    notes = [
        f"Published rate {record.published_rate:.2%} is an advertisement "
        f"({record.rate_basis}); the lender's offer depends on its own assessment.",
    ]
    if record.rate_type == "floating":
        notes.append(
            "This is a floating-rate product: the EMI shown assumes today's rate and will "
            "change if the benchmark moves. See the rate-sensitivity table on the analysis tab."
        )
    if cashflow.emergency_fund_progress < MIN_EMERGENCY_PROGRESS_FOR_NEW_DEBT:
        notes.append(
            f"The emergency fund covers {cashflow.emergency_fund_progress:.0%} of the "
            "guideline. Taking on new fixed obligations before it is funded is risky."
        )
    budget = cashflow.available_goal_budget
    if budget <= 0:
        notes.append(
            "There is no available goal budget after the protected buffer, so any new EMI "
            "would have to come from essential spending or the buffer."
        )
    elif payment > 0.5 * budget:
        notes.append(
            f"The EMI is {payment / budget:.0%} of the available goal budget, which would "
            "crowd out goal contributions."
        )
    return notes


def quote_from_inputs(payload: dict[str, Any], cashflow: CashFlow) -> dict[str, Any]:
    """Normalise a user-supplied offer (from any lender) into the same analysis shape."""
    return analyse_quote(
        principal=float(payload["principal"]),
        annual_rate=float(payload["annual_rate"]),
        tenure_months=int(payload["tenure_months"]),
        cashflow=cashflow,
        processing_fee_pct=payload.get("processing_fee_pct"),
        processing_fee_flat=float(payload.get("processing_fee_flat") or 0.0),
        other_fees=float(payload.get("other_fees") or 0.0),
        rate_type=str(payload.get("rate_type") or "fixed"),
        gap=payload.get("goal_gap"),
        months_remaining=payload.get("months_remaining"),
        include_schedule=bool(payload.get("include_schedule")),
        offer_is_personal=bool(payload.get("offer_is_personal")),
        offer_source=payload.get("lender") or payload.get("label") or None,
    )


def compare_quotes(quotes: Iterable[dict[str, Any]], cashflow: CashFlow) -> list[dict[str, Any]]:
    """Rank several offers by total cost of credit (fees included), not by headline rate."""
    rows = []
    for quote in quotes:
        analysis = quote_from_inputs(quote, cashflow)
        rows.append(
            {
                "label": quote.get("label") or f"{quote.get('lender', 'Offer')}",
                "lender": quote.get("lender"),
                "input": analysis["input"],
                "monthly_emi": analysis["repayment"]["monthly_emi"],
                "total_cost_of_credit": analysis["repayment"]["total_cost_of_credit"],
                "apr_including_fees": analysis["repayment"]["apr_including_fees"],
                "affordability_verdict": analysis["affordability"]["verdict"],
            }
        )
    rows.sort(key=lambda r: r["total_cost_of_credit"])
    for index, row in enumerate(rows, start=1):
        row["rank_by_total_cost"] = index
    return rows
