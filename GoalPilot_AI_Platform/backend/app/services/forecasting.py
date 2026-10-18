"""Adaptive monthly expense forecasting.

Genuine, testable, and deliberately simple. Leakage is prevented structurally: every
prediction for period *P* is computed from a series that has been truncated to periods
strictly before *P*, and the cut-off is recorded on the returned object.

Methods (v1)
-----------
``baseline_recurring``   the user's declared recurring obligations (rent, EMIs, subscriptions)
``baseline_estimate``    the user's own estimate for the category
``rolling_mean_3``       mean of the last up-to-3 actual months
``ewma_0.5``             exponentially weighted mean, alpha = 0.5
``recurring_median``     median of the last up-to-6 actual months, when the category looks
                         recurring (present in >= 3 of the last 6 months and CV <= 0.25)

Selection
---------
A personalised method is only used when it beats the cold-start baseline on a **walk-forward
backtest** of the user's own history, and only when at least ``min_history_months`` months of
actuals exist. Otherwise the baseline is used and the forecast is marked ``provisional``.
More sophisticated models are intentionally absent: none has been shown to improve on these
baselines on any available data.

Cross-user learning: none. The brief requires per-user isolation, and no consent mechanism
for shared training exists, so nothing here ever mixes users' transaction data.
"""
from __future__ import annotations

import datetime as dt
import statistics
from dataclasses import dataclass, asdict, field
from typing import Any, Iterable

METHOD_VERSION = "v1"

BASELINE_RECURRING = "baseline_recurring"
BASELINE_ESTIMATE = "baseline_estimate"
ROLLING_MEAN_3 = "rolling_mean_3"
EWMA_05 = "ewma_0.5"
RECURRING_MEDIAN = "recurring_median"

PERSONALISED_METHODS = (ROLLING_MEAN_3, EWMA_05, RECURRING_MEDIAN)


@dataclass(frozen=True)
class MonthObservation:
    period: str  # YYYY-MM
    category: str
    amount: float


@dataclass
class CategoryForecast:
    category: str
    amount: float
    method: str
    method_version: str
    history_months_used: int
    observations_used: int
    is_provisional: bool
    data_quality: str  # provisional | low | fair | good
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ForecastResult:
    period: str
    input_cutoff: str
    category_forecasts: list[CategoryForecast] = field(default_factory=list)
    total_forecast: float = 0.0
    min_history_months: int = 3
    months_of_history: int = 0
    personalised: bool = False
    backtest: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["category_forecasts"] = [c.as_dict() for c in self.category_forecasts]
        return data


# --------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------
def period_to_index(period: str) -> int:
    """Monotonic month index: ``year * 12 + (month - 1)``."""
    year, month = period.split("-")
    return int(year) * 12 + (int(month) - 1)


def index_to_period(index: int) -> str:
    return f"{index // 12:04d}-{(index % 12) + 1:02d}"


def previous_periods(period: str, count: int) -> list[str]:
    idx = period_to_index(period)
    return [index_to_period(idx - offset) for offset in range(count, 0, -1)]


def next_period(period: str) -> str:
    return index_to_period(period_to_index(period) + 1)


def _series_by_category(
    history: Iterable[MonthObservation], cutoff_exclusive: str
) -> dict[str, list[tuple[str, float]]]:
    """Category -> [(period, amount)] for periods **strictly before** ``cutoff_exclusive``."""
    cutoff_idx = period_to_index(cutoff_exclusive)
    buckets: dict[str, list[tuple[str, float]]] = {}
    for obs in history:
        if period_to_index(obs.period) >= cutoff_idx:
            continue  # leakage guard
        buckets.setdefault(obs.category, []).append((obs.period, float(obs.amount)))
    for cat in buckets:
        buckets[cat].sort(key=lambda t: t[0])
    return buckets


def _rolling_mean(values: list[float], n: int = 3) -> float:
    window = values[-n:]
    return sum(window) / len(window) if window else 0.0


def _ewma(values: list[float], alpha: float = 0.5) -> float:
    if not values:
        return 0.0
    acc = values[0]
    for value in values[1:]:
        acc = alpha * value + (1 - alpha) * acc
    return acc


def _median(values: list[float]) -> float:
    return float(statistics.median(values)) if values else 0.0


def _looks_recurring(pairs: list[tuple[str, float]]) -> bool:
    """Present in >= 3 of the last 6 months and reasonably stable (CV <= 0.25)."""
    recent = pairs[-6:]
    if len(recent) < 3:
        return False
    values = [v for _, v in recent]
    if any(v <= 0 for v in values):
        return False
    mean = sum(values) / len(values)
    if mean <= 0:
        return False
    try:
        sd = statistics.pstdev(values)
    except statistics.StatisticsError:
        return False
    return (sd / mean) <= 0.25


def _predict_with(method: str, pairs: list[tuple[str, float]]) -> float:
    values = [v for _, v in pairs]
    if not values:
        return 0.0
    if method == ROLLING_MEAN_3:
        return _rolling_mean(values, 3)
    if method == EWMA_05:
        return _ewma(values, 0.5)
    if method == RECURRING_MEDIAN:
        return _median([v for _, v in pairs[-6:]])
    raise ValueError(f"unknown method {method}")


def _backtest_category(pairs: list[tuple[str, float]], min_train: int = 2) -> dict[str, float]:
    """Walk-forward MAE per method using only prior observations.

    Returns ``{method: mae}`` for every personalised method that produced >= 1 prediction.
    """
    errors: dict[str, list[float]] = {m: [] for m in PERSONALISED_METHODS}
    for i in range(min_train, len(pairs)):
        train = pairs[:i]
        actual = pairs[i][1]
        for method in PERSONALISED_METHODS:
            if method == RECURRING_MEDIAN and not _looks_recurring(train):
                continue
            pred = _predict_with(method, train)
            errors[method].append(abs(pred - actual))
    return {m: sum(e) / len(e) for m, e in errors.items() if e}


def _baseline_mae(pairs: list[tuple[str, float]], baseline_value: float | None) -> float | None:
    """MAE of a constant baseline (recurring obligation or user estimate)."""
    if baseline_value is None or len(pairs) < 3:
        return None
    errs = [abs(baseline_value - v) for _, v in pairs[1:]]
    return sum(errs) / len(errs) if errs else None


# --------------------------------------------------------------------------------------
# main entry points
# --------------------------------------------------------------------------------------
def forecast_month(
    history: list[MonthObservation],
    *,
    period: str,
    categories: list[str],
    recurring_amounts: dict[str, float] | None = None,
    category_estimates: dict[str, float] | None = None,
    min_history_months: int = 3,
    today: dt.date | None = None,
) -> ForecastResult:
    """Forecast every category for ``period``.

    ``recurring_amounts`` are the user's declared recurring obligations (highest-trust cold
    start); ``category_estimates`` are the user's own estimates (second). Neither is
    fabricated — an absent value is simply not used.
    """
    recurring_amounts = recurring_amounts or {}
    category_estimates = category_estimates or {}
    cutoff = period  # exclusive

    series = _series_by_category(history, cutoff)
    months_of_history = max((len(v) for v in series.values()), default=0)
    personalised_allowed = months_of_history >= min_history_months

    result = ForecastResult(
        period=period,
        input_cutoff=dt.datetime.now(dt.timezone.utc).isoformat(),
        min_history_months=min_history_months,
        months_of_history=months_of_history,
    )

    selection_log: dict[str, Any] = {}
    for category in categories:
        pairs = series.get(category, [])
        recurring = recurring_amounts.get(category)
        estimate = category_estimates.get(category)

        chosen_method = BASELINE_RECURRING if recurring is not None else BASELINE_ESTIMATE
        chosen_value = float(recurring if recurring is not None else (estimate or 0.0))
        history_used = 0
        note = ""

        if not pairs:
            note = (
                "Declared recurring obligation."
                if recurring is not None
                else "User estimate; no history exists yet."
            )
            if recurring is None and estimate is None:
                chosen_method = BASELINE_ESTIMATE
                chosen_value = 0.0
                note = "No history, no declared obligation and no estimate: zero assumed."
        elif not personalised_allowed:
            option_a = _predict_with(ROLLING_MEAN_3, pairs)
            option_b = _predict_with(EWMA_05, pairs)
            chosen_value = option_a
            chosen_method = ROLLING_MEAN_3
            history_used = len(pairs)
            note = (
                f"Only {len(pairs)} month(s) of actuals; using a simple mean until "
                f"{min_history_months} months exist. EWMA would have given {option_b:,.0f}."
            )
        else:
            bt = _backtest_category(pairs)
            base_mae = _baseline_mae(pairs, recurring if recurring is not None else estimate)
            best_method, best_mae = None, None
            for method, mae in sorted(bt.items()):
                if best_mae is None or mae < best_mae - 1e-9:
                    best_method, best_mae = method, mae
            selection_log[category] = {
                "backtest_mae": {k: round(v, 4) for k, v in bt.items()},
                "baseline_mae": round(base_mae, 4) if base_mae is not None else None,
                "chosen": None,
            }
            # A personalised method must actually beat the baseline to be used.
            if (
                best_method is not None
                and best_mae is not None
                and (base_mae is None or best_mae < base_mae - 1e-9)
            ):
                chosen_method = best_method
                chosen_value = _predict_with(best_method, pairs)
                history_used = len(pairs)
                note = (
                    f"Backtest MAE {best_mae:,.0f} beats the baseline"
                    + (f" ({base_mae:,.0f})" if base_mae is not None else "")
                    + f" over {len(pairs)} months."
                )
                selection_log[category]["chosen"] = best_method
            else:
                chosen_method = (
                    BASELINE_RECURRING if recurring is not None else BASELINE_ESTIMATE
                )
                chosen_value = float(
                    recurring if recurring is not None else (estimate or _predict_with(ROLLING_MEAN_3, pairs))
                )
                history_used = len(pairs)
                note = (
                    "No personalised method beat the baseline on backtest; keeping the "
                    "baseline value."
                )
                selection_log[category]["chosen"] = chosen_method

        quality = _quality(len(pairs), min_history_months)
        is_provisional = quality == "provisional"
        result.category_forecasts.append(
            CategoryForecast(
                category=category,
                amount=max(0.0, chosen_value),
                method=chosen_method,
                method_version=METHOD_VERSION,
                history_months_used=len(pairs),
                observations_used=len(pairs),
                is_provisional=is_provisional,
                data_quality=quality,
                note=note,
            )
        )
        result.total_forecast += max(0.0, chosen_value)

    # "Personalised" means a method selected on *evidence* — i.e. a backtest-winning method.
    # A rolling mean used only because history is still short is data-driven but not
    # evidence-selected, so it does not count.
    result.personalised = personalised_allowed and any(
        c.method in PERSONALISED_METHODS for c in result.category_forecasts
    )
    result.backtest = selection_log
    if months_of_history == 0:
        result.warnings.append(
            "No actual expense history exists, so every figure is provisional and comes from "
            "the user's own recurring obligations and estimates."
        )
    elif not personalised_allowed:
        result.warnings.append(
            f"Only {months_of_history} month(s) of actuals; personalised methods are held back "
            f"until {min_history_months} months exist."
        )
    if result.personalised:
        result.warnings.append(
            "Personalised estimates are based on this user's own recorded months only."
        )
    return result


def _quality(observations: int, min_history: int) -> str:
    if observations == 0:
        return "provisional"
    if observations < min_history:
        return "low"
    if observations < min_history * 2:
        return "fair"
    return "good"


def detect_persistent_overspend(
    history: list[MonthObservation],
    budgets: dict[str, float],
    *,
    consecutive_months: int = 3,
    tolerance: float = 0.10,
) -> list[dict[str, Any]]:
    """Flag categories where actual spend exceeded budget for N consecutive months.

    Requires explicit evidence: fewer than N consecutive over-budget months produces
    nothing, and a single spike is never called persistent.
    """
    flagged: list[dict[str, Any]] = []
    by_category: dict[str, list[tuple[str, float]]] = {}
    for obs in history:
        by_category.setdefault(obs.category, []).append((obs.period, float(obs.amount)))
    for category, pairs in by_category.items():
        limit = budgets.get(category)
        if not limit or limit <= 0:
            continue
        pairs.sort(key=lambda t: t[0])
        streak: list[str] = []
        best: list[str] = []
        for period, amount in pairs:
            if amount > limit * (1 + tolerance):
                streak.append(period)
                if len(streak) > len(best):
                    best = list(streak)
            else:
                streak = []
        if len(best) >= consecutive_months:
            flagged.append(
                {
                    "category": category,
                    "consecutive_months": len(best),
                    "periods": best,
                    "monthly_limit": limit,
                    "detail": (
                        f"{category} exceeded its {limit:,.0f} budget by more than "
                        f"{tolerance:.0%} for {len(best)} consecutive months."
                    ),
                }
            )
    return flagged


def detect_recurring(history: list[MonthObservation]) -> list[dict[str, Any]]:
    """Categories that look recurring, with the evidence."""
    by_category: dict[str, list[tuple[str, float]]] = {}
    for obs in history:
        by_category.setdefault(obs.category, []).append((obs.period, float(obs.amount)))
    out: list[dict[str, Any]] = []
    for category, pairs in by_category.items():
        pairs.sort(key=lambda t: t[0])
        if _looks_recurring(pairs):
            values = [v for _, v in pairs[-6:]]
            mean = sum(values) / len(values)
            sd = statistics.pstdev(values)
            out.append(
                {
                    "category": category,
                    "months_observed": len(pairs),
                    "typical_amount": round(mean, 2),
                    "coefficient_of_variation": round(sd / mean, 4),
                    "detail": (
                        f"Appears in {len(pairs[-6:])} of the last 6 months at a stable amount "
                        f"(CV {sd / mean:.2f})."
                    ),
                }
            )
    return out


def backtest(
    history: list[MonthObservation],
    *,
    min_history_months: int = 3,
) -> dict[str, Any]:
    """Walk-forward evaluation of the forecaster against the cold-start baseline.

    Returns per-period absolute errors for the chosen method and the naive baseline so the
    accuracy endpoint can report whether personalisation is actually helping.
    """
    periods = sorted({obs.period for obs in history})
    if len(periods) < min_history_months + 1:
        return {
            "periods_evaluated": 0,
            "method_mae": None,
            "baseline_mae": None,
            "improvement": None,
            "detail": (
                f"Needs at least {min_history_months + 1} months of actuals to backtest; "
                f"there are {len(periods)}."
            ),
        }

    method_errors: list[float] = []
    baseline_errors: list[float] = []
    detail_rows: list[dict[str, Any]] = []

    for target in periods[min_history_months:]:
        prior = [o for o in history if o.period < target]
        actual_by_cat: dict[str, float] = {}
        for obs in history:
            if obs.period == target:
                actual_by_cat[obs.category] = actual_by_cat.get(obs.category, 0.0) + obs.amount
        if not actual_by_cat:
            continue
        result = forecast_month(
            prior,
            period=target,
            categories=sorted(actual_by_cat),
            min_history_months=min_history_months,
        )
        pred_by_cat = {c.category: c.amount for c in result.category_forecasts}
        for category, actual in actual_by_cat.items():
            method_errors.append(abs(pred_by_cat.get(category, 0.0) - actual))
            # Naive baseline: the mean of everything seen before the target.
            prior_vals = [o.amount for o in prior if o.category == category]
            if prior_vals:
                baseline_errors.append(abs(sum(prior_vals) / len(prior_vals) - actual))
        detail_rows.append({"period": target, "categories": len(actual_by_cat)})

    method_mae = sum(method_errors) / len(method_errors) if method_errors else None
    baseline_mae = sum(baseline_errors) / len(baseline_errors) if baseline_errors else None
    improvement = (
        (baseline_mae - method_mae) / baseline_mae
        if method_mae is not None and baseline_mae not in (None, 0)
        else None
    )
    return {
        "periods_evaluated": len(detail_rows),
        "method_mae": round(method_mae, 2) if method_mae is not None else None,
        "baseline_mae": round(baseline_mae, 2) if baseline_mae is not None else None,
        "improvement": round(improvement, 4) if improvement is not None else None,
        "detail": detail_rows,
    }
