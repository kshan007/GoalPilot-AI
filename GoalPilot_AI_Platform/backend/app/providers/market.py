"""Market context: NIFTY 50 history (local, provenance-tagged) and a live index quote.

Two deliberately separate things:

* **History** comes from the project's own research dataset
  (``datasets/GoalPilot_AI/extracted_features/nifty_monthly_features.csv``), which is derived
  from NIFTY 50 daily closes. It is reported with its exact observation period, the
  annualisation convention used, and is labelled ``historical``. Historical volatility is a
  description of the past; it is **not** an expected return and the platform never feeds it
  into a projection as one.
* **The live quote** comes from the public NSE ``allIndices`` endpoint. It is one number at
  one instant. If NSE is unreachable the provider reports ``unavailable`` and the app uses
  the last historical close, clearly labelled.
"""
from __future__ import annotations

import datetime as dt
import math
from pathlib import Path

from app.config import get_settings
from app.providers.base import HISTORICAL, OFFICIAL_LIVE, ProviderOutcome, iso, utcnow
from app.providers.http import get_json

NSE_ALL_INDICES = "https://www.nseindia.com/api/allIndices"
NSE_SOURCE = "https://www.nseindia.com/"
DATASET_RELATIVE = Path("datasets/GoalPilot_AI/extracted_features/nifty_monthly_features.csv")


def dataset_path() -> Path | None:
    explicit = __import__("os").getenv("GOALPILOT_MARKET_DATA_PATH")
    if explicit:
        path = Path(explicit)
        return path if path.is_file() else None
    here = Path(__file__).resolve()
    for parent in list(here.parents)[:6]:
        candidate = parent / DATASET_RELATIVE
        if candidate.is_file():
            return candidate
    return None


def _cagr(start: float, end: float, days: float) -> float | None:
    if start <= 0 or days <= 0:
        return None
    return (end / start) ** (365.0 / days) - 1.0


def historical_stats() -> dict[str, object]:
    """Descriptive statistics of the NIFTY 50 monthly close series."""
    path = dataset_path()
    if path is None:
        return {"available": False, "reason": "market_dataset_not_found"}

    import pandas as pd

    frame = pd.read_csv(path)
    if "period" not in frame or "nifty_close" not in frame:
        return {"available": False, "reason": "market_dataset_unexpected_columns"}
    frame["period"] = pd.to_datetime(frame["period"], errors="coerce")
    frame = frame.dropna(subset=["period", "nifty_close"]).sort_values("period")
    if len(frame) < 13:
        return {"available": False, "reason": "market_dataset_too_short"}

    closes = frame["nifty_close"].astype(float).to_numpy()
    dates = frame["period"].dt.date.tolist()
    monthly_returns = [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes))]
    mean = sum(monthly_returns) / len(monthly_returns)
    variance = sum((r - mean) ** 2 for r in monthly_returns) / max(1, len(monthly_returns) - 1)
    volatility = math.sqrt(variance) * math.sqrt(12.0)

    peak = closes[0]
    max_drawdown = 0.0
    for value in closes:
        peak = max(peak, value)
        max_drawdown = min(max_drawdown, value / peak - 1.0)

    trailing: dict[str, object] = {}
    last_date, last_close = dates[-1], closes[-1]
    for label, years in (("1y", 1), ("3y", 3), ("5y", 5)):
        target = last_date.replace(year=last_date.year - years)
        earlier = [(d, c) for d, c in zip(dates, closes) if d <= target]
        if not earlier:
            continue
        start_date, start_close = earlier[-1]
        days = (last_date - start_date).days
        trailing[label] = {
            "cagr": _cagr(start_close, last_close, days),
            "period_start": start_date.isoformat(),
            "period_end": last_date.isoformat(),
        }

    return {
        "available": True,
        "observations": len(closes),
        "frequency": "monthly close",
        "period_start": dates[0].isoformat(),
        "period_end": dates[-1].isoformat(),
        "last_close": round(float(last_close), 2),
        "cagr_full_period": _cagr(closes[0], last_close, (dates[-1] - dates[0]).days),
        "annualised_volatility": round(volatility, 6),
        "max_drawdown": round(max_drawdown, 6),
        "best_month": round(max(monthly_returns), 6),
        "worst_month": round(min(monthly_returns), 6),
        "trailing": trailing,
        "annualisation": "CAGR from month-end closes; volatility = stdev(monthly returns) x sqrt(12)",
        "source_file": str(path),
        "caveat": (
            "Observed history. Not a forecast, not an expected return, and not a guaranteed "
            "outcome. Index returns exclude dividends and costs unless stated."
        ),
    }


def live_quote() -> ProviderOutcome:
    retrieved = utcnow()
    try:
        payload = get_json(
            NSE_ALL_INDICES,
            timeout=10,
            headers={"Referer": "https://www.nseindia.com/market-data/live-market-indices"},
        )
    except Exception as exc:
        return ProviderOutcome(
            provider="nse_index",
            kind="economic",
            status="unavailable",
            data_quality=OFFICIAL_LIVE,
            source_url=NSE_SOURCE,
            retrieved_at=iso(retrieved),
            reason=f"{type(exc).__name__}: {exc}"[:250],
        )

    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return ProviderOutcome(
            provider="nse_index",
            kind="economic",
            status="unavailable",
            data_quality=OFFICIAL_LIVE,
            source_url=NSE_SOURCE,
            retrieved_at=iso(retrieved),
            reason="Unexpected NSE payload shape",
        )

    match = None
    for row in rows:
        if isinstance(row, dict) and str(row.get("index", "")).upper() == "NIFTY 50":
            match = row
            break
    if match is None:
        return ProviderOutcome(
            provider="nse_index",
            kind="economic",
            status="unavailable",
            data_quality=OFFICIAL_LIVE,
            source_url=NSE_SOURCE,
            retrieved_at=iso(retrieved),
            reason="NIFTY 50 was not present in the NSE index feed",
        )

    record = {
        "index": "NIFTY 50",
        "last": match.get("last"),
        "previous_close": match.get("previousClose"),
        "percent_change": match.get("percentChange"),
        "as_of": match.get("lastUpdateTime") or iso(retrieved),
    }
    return ProviderOutcome(
        provider="nse_index",
        kind="economic",
        status="ok",
        records=[record],
        data_quality=OFFICIAL_LIVE,
        source_url=NSE_SOURCE,
        retrieved_at=iso(retrieved),
        metadata={
            "note": (
                "A single index level at a single instant, retrieved from NSE's public market "
                "page feed. Redistribution may be subject to NSE terms."
            )
        },
    )


def context() -> dict[str, object]:
    """Market context bundle: history always, live quote if it is reachable."""
    settings = get_settings()
    history = historical_stats()
    live = live_quote() if settings.enable_live_providers else ProviderOutcome(
        provider="nse_index",
        kind="economic",
        status="disabled",
        source_url=NSE_SOURCE,
        reason="Live providers are disabled by configuration.",
    )
    return {
        "historical": history,
        "live": live.as_dict(),
        "data_quality": HISTORICAL,
        "note": (
            "Historical index statistics and a live index level are market context. Neither is "
            "used as a guaranteed forward return."
        ),
    }
