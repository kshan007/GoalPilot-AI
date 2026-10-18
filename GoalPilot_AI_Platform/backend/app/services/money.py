"""Monetary units, rounding and income normalisation.

Rounding rule for the whole platform: money is rounded **half-up to 2 decimals** at the
persistence boundary only. All internal arithmetic is float64 so the model behaviour
matches the research implementation exactly (the research LP arithmetic is float64 and
the parity tests depend on that).
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from app.core.errors import ValidationFailure

CENT = Decimal("0.01")

#: Frequency -> number of occurrences per month. One-off income has no monthly equivalent.
FREQUENCY_PER_MONTH: dict[str, float] = {
    "monthly": 1.0,
    "annual": 1.0 / 12.0,
    "quarterly": 1.0 / 3.0,
    "weekly": 52.0 / 12.0,
    "one_time": 0.0,
}


def to_decimal(value: float | int | str | Decimal) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def round_money(value: float | int | str | Decimal) -> Decimal:
    """Round half-up to 2 decimals — the storage/display rule."""
    return to_decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def money_float(value: Decimal | float | int | None) -> float:
    return float(value) if value is not None else 0.0


def money_str(value: Decimal | float | int | None) -> str:
    """Serialise money as a fixed 2-dp string so the API never emits 0.30000000000004."""
    return str(round_money(value or 0))


def normalise_monthly(amount: float | Decimal, frequency: str) -> float:
    """Convert a stated amount in ``frequency`` units into a monthly equivalent.

    The original frequency is retained by the caller; this is only the normalised value
    used by the planner.
    """
    key = (frequency or "monthly").strip().lower()
    if key not in FREQUENCY_PER_MONTH:
        raise ValidationFailure(
            f"Unsupported income frequency '{frequency}'",
            details={"allowed": sorted(FREQUENCY_PER_MONTH)},
        )
    return float(amount) * FREQUENCY_PER_MONTH[key]


def normalise_annual(amount: float | Decimal, frequency: str) -> float:
    key = (frequency or "monthly").strip().lower()
    if key not in FREQUENCY_PER_MONTH:
        raise ValidationFailure(f"Unsupported frequency '{frequency}'")
    per_month = FREQUENCY_PER_MONTH[key]
    if per_month == 0.0:
        return 0.0
    return float(amount) / per_month * 12.0


def months_between(start, end) -> int:
    """Whole months from ``start`` to ``end``, floored at 0."""
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day < start.day:
        months -= 1
    return max(0, months)
