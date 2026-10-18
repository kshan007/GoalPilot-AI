"""Optional trailing-return enrichment from a free NAV-history mirror.

Why this module is separate and optional
----------------------------------------
AMFI's public NAV file gives only the *latest* NAV, so it cannot support "trailing 1/3/5-year
return" without a historical series. This module reads history from ``https://api.mfapi.in``,
a free, key-less community service that mirrors the AMFI NAV history.

It is labelled ``unofficial_mirror`` everywhere it is used and is disabled by
``GOALPILOT_ENABLE_MFAPI_HISTORY=false``. It is never presented as an AMFI statement, and a
failure here degrades the investment options (no returns) without failing discovery.
"""
from __future__ import annotations

import datetime as dt

from app.config import get_settings
from app.providers.base import NormalizedInvestment, iso, utcnow
from app.providers.http import ProviderUnavailable, get_json

BASE_URL = "https://api.mfapi.in/mf"
PROVIDER_NAME = "mfapi_history"
SOURCE_URL = "https://www.mfapi.in/"
ATTRIBUTION = (
    "Historical NAV via api.mfapi.in, an unofficial mirror of AMFI NAV history. "
    "Not an AMFI publication. Past returns are not a forecast."
)

#: Windows we report, in days, with the tolerance allowed on the actual start date.
WINDOWS = (("1y", 365, 45), ("3y", 1095, 60), ("5y", 1825, 90))


def _parse_date(value: str) -> dt.date | None:
    try:
        return dt.datetime.strptime(value, "%d-%m-%Y").date()
    except (ValueError, TypeError):
        return None


def _to_float(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def compute_trailing_returns(series: list[dict[str, object]]) -> list[dict[str, object]]:
    """Trailing CAGR over an explicit, reported period.

    ``series`` is mfapi's ``[{"date": "DD-MM-YYYY", "nav": "..."}]``, newest first.
    A window is reported only when the series actually reaches back far enough; otherwise it
    is omitted rather than extrapolated.
    """
    points: list[tuple[dt.date, float]] = []
    for row in series or []:
        day = _parse_date(str(row.get("date", "")))
        nav = _to_float(row.get("nav"))
        if day is None or nav is None or nav <= 0:
            continue
        points.append((day, nav))
    if len(points) < 2:
        return []
    points.sort(key=lambda item: item[0])
    end_date, end_nav = points[-1]

    out: list[dict[str, object]] = []
    for label, days, tolerance in WINDOWS:
        target = end_date - dt.timedelta(days=days)
        candidates = [p for p in points if p[0] <= target]
        if not candidates:
            continue
        start_date, start_nav = candidates[-1]
        actual_days = (end_date - start_date).days
        if abs(actual_days - days) > tolerance or start_nav <= 0:
            continue
        cagr = (end_nav / start_nav) ** (365.0 / actual_days) - 1.0
        out.append(
            {
                "window": label,
                "cagr": round(cagr, 6),
                "period_start": start_date.isoformat(),
                "period_end": end_date.isoformat(),
                "days": actual_days,
                "basis": "annualised CAGR of published NAV, net of the scheme's own expenses",
                "source": PROVIDER_NAME,
            }
        )
    return out


def fetch_history(scheme_code: str, *, timeout: float = 6.0) -> dict[str, object]:
    payload = get_json(f"{BASE_URL}/{scheme_code}", timeout=timeout)
    if not isinstance(payload, dict):
        raise ProviderUnavailable("Unexpected payload shape from the NAV history mirror")
    data = payload.get("data")
    if not isinstance(data, list) or not data:
        raise ProviderUnavailable("The NAV history mirror returned no series for this scheme")
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    return {
        "returns": compute_trailing_returns(data),
        "meta": {
            "fund_house": meta.get("fund_house"),
            "scheme_category": meta.get("scheme_category"),
            "scheme_type": meta.get("scheme_type"),
        },
        "retrieved_at": iso(utcnow()),
        "source_url": f"{BASE_URL}/{scheme_code}",
        "attribution": ATTRIBUTION,
    }


def enrich(records: list[NormalizedInvestment], *, limit: int = 6) -> dict[str, object]:
    """Attach trailing returns to at most ``limit`` records. Never raises."""
    settings = get_settings()
    if not settings.enable_mfapi_history or not settings.enable_live_providers:
        return {"enabled": False, "enriched": 0, "reason": "disabled_by_configuration"}

    enriched = 0
    failures: list[dict[str, str]] = []
    for record in records[:limit]:
        try:
            result = fetch_history(record.product_id)
        except Exception as exc:  # a mirror failure must never break discovery
            failures.append({"product_id": record.product_id, "reason": f"{type(exc).__name__}: {exc}"[:200]})
            continue
        returns = result.get("returns") or []
        if not returns:
            continue
        record.historical_returns = list(returns)  # type: ignore[arg-type]
        record.notes.append(ATTRIBUTION)
        enriched += 1

    return {
        "enabled": True,
        "enriched": enriched,
        "attempted": min(len(records), limit),
        "failures": failures,
        "source": SOURCE_URL,
        "data_quality": "unofficial_mirror",
        "attribution": ATTRIBUTION,
    }
