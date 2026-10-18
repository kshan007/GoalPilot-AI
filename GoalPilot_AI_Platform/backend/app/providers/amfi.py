"""AMFI mutual-fund discovery.

Source: **Association of Mutual Funds in India**, public daily NAV file
``https://www.amfiindia.com/spages/NAVAll.txt``. Public, no authentication, no API key.
It is a plain ``;``-delimited file of every open/close-ended scheme with its latest NAV.

What this file does and does not give us
---------------------------------------
* It gives the scheme's **current NAV**, its plan (Direct/Regular), its option
  (Growth/IDCW), its AMFI scheme code and the NAV date.
* It gives **no** expense ratio, no minimum investment, no historical series and no
  performance figure. Those fields are returned as ``None``; nothing is estimated in their
  place. Trailing returns are added only by :mod:`app.providers.mfapi` when the operator
  enables that optional history mirror, and are labelled as such.
"""
from __future__ import annotations

import datetime as dt

from app.providers.base import (
    OFFICIAL_LIVE,
    OFFICIAL_SNAPSHOT,
    NormalizedInvestment,
    ProviderOutcome,
    iso,
    utcnow,
)
from app.providers.http import get_text

AMFI_NAV_URL = "https://www.amfiindia.com/spages/NAVAll.txt"
PROVIDER_NAME = "amfi_nav"

#: Category classification driven by the AMFI section header. ``(normalised_category,
#: sub_category, risk_level, risk_score, lock_in_months, liquidity)``.
_RULES: tuple[tuple[tuple[str, ...], str, str, str, float, int, str], ...] = (
    (("overnight",), "debt_mf", "Overnight", "low", 0.05, 0, "t_plus_1"),
    (("liquid",), "debt_mf", "Liquid", "low", 0.10, 0, "t_plus_1"),
    (("money market",), "debt_mf", "Money market", "low", 0.10, 0, "t_plus_1"),
    (("ultra short",), "debt_mf", "Ultra-short duration", "low", 0.15, 0, "daily"),
    (("low duration", "short duration", "short term"), "debt_mf", "Short duration", "low", 0.20, 0, "daily"),
    (("banking and psu", "banking & psu"), "debt_mf", "Banking & PSU", "low", 0.22, 0, "daily"),
    (("corporate bond",), "debt_mf", "Corporate bond", "low", 0.22, 0, "daily"),
    (("credit risk",), "debt_mf", "Credit risk", "moderate", 0.35, 0, "daily"),
    (("gilt",), "debt_mf", "Gilt", "low", 0.22, 0, "daily"),
    (("dynamic bond", "long duration", "medium duration", "medium to long",
      "medium term", "long term", "dynamic term", "ultra short to short term",
      "10-year constant maturity", "floating interest"), "debt_mf", "Duration", "moderate",
     0.30, 0, "daily"),
    (("income/debt oriented", "income"), "debt_mf", "Income / debt oriented", "low", 0.25, 0, "daily"),
    (("arbitrage",), "hybrid_mf", "Arbitrage", "low", 0.15, 0, "daily"),
    (("conservative hybrid",), "hybrid_mf", "Conservative hybrid", "moderate", 0.28, 0, "daily"),
    (("equity savings",), "hybrid_mf", "Equity savings", "moderate", 0.32, 0, "daily"),
    (("balanced hybrid",), "hybrid_mf", "Balanced hybrid", "moderate", 0.45, 0, "daily"),
    (("aggressive hybrid", "balanced advantage", "dynamic asset allocation"), "hybrid_mf",
     "Aggressive hybrid / BAF", "high", 0.50, 0, "daily"),
    (("multi asset",), "hybrid_mf", "Multi-asset", "moderate", 0.45, 0, "daily"),
    (("index funds - equity", "other scheme - index funds", "index funds"), "index_fund",
     "Equity index", "high", 0.55, 0, "daily"),
    (("index funds - debt",), "index_fund", "Debt index", "low", 0.20, 0, "daily"),
    (("index funds - hybrid",), "index_fund", "Hybrid index", "moderate", 0.40, 0, "daily"),
    (("equity etf", "other  etfs", "other etf"), "etf", "Equity ETF", "high", 0.55, 0, "daily"),
    (("debt etf",), "etf", "Debt ETF", "low", 0.20, 0, "daily"),
    (("gold etf",), "etf", "Gold ETF", "moderate", 0.50, 0, "daily"),
    (("silver etf",), "etf", "Silver ETF", "high", 0.65, 0, "daily"),
    (("hybrid etf",), "etf", "Hybrid ETF", "moderate", 0.40, 0, "daily"),
    (("etfs investing overseas",), "etf", "Overseas ETF", "high", 0.65, 0, "daily"),
    (("elss",), "equity_mf", "ELSS (tax saver)", "high", 0.60, 36, "lock_in"),
    (("large cap",), "equity_mf", "Large cap", "moderate", 0.50, 0, "daily"),
    (("large & mid cap", "large and mid cap"), "equity_mf", "Large & mid cap", "high", 0.55, 0, "daily"),
    (("flexi cap", "multi cap"), "equity_mf", "Flexi / multi cap", "high", 0.58, 0, "daily"),
    (("focused", "value fund", "dividend yield", "contra"), "equity_mf", "Focused / value",
     "high", 0.55, 0, "daily"),
    (("mid cap",), "equity_mf", "Mid cap", "high", 0.68, 0, "daily"),
    (("small cap",), "equity_mf", "Small cap", "very_high", 0.78, 0, "daily"),
    (("sectoral", "thematic"), "equity_mf", "Sectoral / thematic", "very_high", 0.80, 0, "daily"),
    (("children",), "solution_oriented", "Children's fund", "high", 0.50, 60, "lock_in"),
    (("retirement",), "solution_oriented", "Retirement fund", "moderate", 0.45, 60, "lock_in"),
    (("life cycle",), "solution_oriented", "Life-cycle fund", "moderate", 0.45, 60, "lock_in"),
    (("fund of funds", "fof"), "fund_of_funds", "Fund of funds", "moderate", 0.45, 0, "daily"),
    (("fixed term plan",), "debt_mf", "Fixed term plan", "low", 0.22, 0, "lock_in"),
)

_FALLBACK = ("other", "Other scheme", "unknown", 0.5, 0, "unknown")


def _classify(section: str) -> tuple[str, str, str, float, int, str]:
    text = (section or "").lower()
    for keywords, category, sub, risk, score, lock_in, liquidity in _RULES:
        if any(keyword in text for keyword in keywords):
            return category, sub, risk, score, lock_in, liquidity
    return _FALLBACK  # type: ignore[return-value]


def parse_nav_all(text: str, *, retrieved_at: dt.datetime | None = None) -> list[NormalizedInvestment]:
    """Parse the AMFI NAVAll file into direct-plan growth records.

    Only ``Direct Plan`` + ``Growth`` rows are kept: regular plans embed distributor
    commission in the expense ratio, and IDCW rows are not comparable units of account. The
    filter is disclosed in the response metadata rather than silently applied.
    """
    retrieved_at = retrieved_at or utcnow()
    section = ""
    amc = ""
    records: list[NormalizedInvestment] = []

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if ";" not in line:
            lowered = line.lower()
            if lowered.startswith(("open ended", "close ended", "interval fund")) and "(" in line:
                section = line
                continue
            if line.lower().startswith("scheme code"):
                continue
            # Any other non-delimited line is the current AMC / fund-house name.
            amc = line
            continue

        parts = [p.strip() for p in line.split(";")]
        if len(parts) < 8:
            continue
        code, _isin_growth, _isin_reinvest, name, plan, option, nav_text, date_text = parts[:8]
        if code.lower() == "scheme code":
            continue
        if "direct" not in plan.lower():
            continue
        if "growth" not in option.lower():
            continue
        try:
            nav = float(nav_text)
        except (TypeError, ValueError):
            continue
        if nav <= 0:
            continue

        category, sub_category, risk_level, risk_score, lock_in, liquidity = _classify(section)
        effective = _parse_amfi_date(date_text)
        records.append(
            NormalizedInvestment(
                provider=PROVIDER_NAME,
                product_id=code,
                provider_identifier=code,
                name=f"{name} - Direct Plan - Growth",
                category=category,
                sub_category=sub_category,
                issuer=amc or None,
                source_url=AMFI_NAV_URL,
                retrieved_at=iso(retrieved_at),
                effective_date=iso(effective),
                data_quality=OFFICIAL_LIVE,
                is_current_observation=True,
                nav=nav,
                lock_in_months=lock_in,
                liquidity=liquidity,
                risk_level=risk_level,
                risk_score=risk_score,
                eligibility=["Open to resident Indian investors subject to the scheme's SID"],
                notes=[
                    "NAV only. AMFI's public file does not publish expense ratio, minimum "
                    "investment, exit load or historical performance.",
                ],
            )
        )
    return records


def _parse_amfi_date(value: str) -> dt.date | None:
    for fmt in ("%d-%b-%Y", "%d-%b-%y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(value.strip(), fmt).date()
        except (ValueError, AttributeError):
            continue
    return None


def fetch() -> ProviderOutcome:
    from app.config import get_settings

    retrieved_at = utcnow()
    if not get_settings().enable_live_providers:
        return ProviderOutcome(
            provider=PROVIDER_NAME,
            kind="investment",
            status="disabled",
            source_url=AMFI_NAV_URL,
            data_quality=OFFICIAL_LIVE,
            retrieved_at=iso(retrieved_at),
            reason="GOALPILOT_ENABLE_LIVE_PROVIDERS=false; category scenarios are used instead.",
        )
    text = get_text(AMFI_NAV_URL, timeout=20)
    records = parse_nav_all(text, retrieved_at=retrieved_at)
    if not records:
        return ProviderOutcome(
            provider=PROVIDER_NAME,
            kind="investment",
            status="partial",
            source_url=AMFI_NAV_URL,
            data_quality=OFFICIAL_LIVE,
            retrieved_at=iso(retrieved_at),
            reason="The AMFI file was retrieved but contained no direct-growth rows.",
        )
    dates = sorted({r.effective_date for r in records if r.effective_date})
    return ProviderOutcome(
        provider=PROVIDER_NAME,
        kind="investment",
        status="ok",
        records=records,
        data_quality=OFFICIAL_LIVE,
        source_url=AMFI_NAV_URL,
        retrieved_at=iso(retrieved_at),
        metadata={
            "total_schemes_in_file": text.count("\n"),
            "direct_growth_records": len(records),
            "nav_date": dates[-1] if dates else None,
            "filter": "Direct Plan + Growth Option only",
            "attribution": "Source: Association of Mutual Funds in India (AMFI) public NAV file",
        },
    )


# --------------------------------------------------------------------------------------
# bundled snapshot
# --------------------------------------------------------------------------------------
#: A tiny, clearly-labelled snapshot used when AMFI cannot be reached. It is *not* a product
#: list — it exists so the discovery page can still explain categories and so the UI never
#: shows an empty error where an explanation is available.
SNAPSHOT_CATEGORIES = (
    ("debt_mf", "Liquid / overnight", "low", 0.10, 0, "t_plus_1"),
    ("debt_mf", "Short duration", "low", 0.20, 0, "daily"),
    ("govt_scheme", "Government small savings", "low", 0.10, 0, "at_maturity"),
    ("hybrid_mf", "Balanced hybrid", "moderate", 0.45, 0, "daily"),
    ("index_fund", "Equity index", "high", 0.55, 0, "daily"),
    ("equity_mf", "Large cap", "moderate", 0.50, 0, "daily"),
    ("equity_mf", "Mid cap", "high", 0.68, 0, "daily"),
    ("equity_mf", "Small cap", "very_high", 0.78, 0, "daily"),
    ("etf", "Gold ETF", "moderate", 0.50, 0, "daily"),
)


def category_scenarios(reason: str) -> list[NormalizedInvestment]:
    """Category-level, explicitly hypothetical options used when AMFI is unreachable."""
    from app.providers.base import CATEGORY_SCENARIO

    stamp = iso(utcnow())
    out = []
    for index, (category, sub, risk, score, lock_in, liquidity) in enumerate(SNAPSHOT_CATEGORIES):
        out.append(
            NormalizedInvestment(
                provider=PROVIDER_NAME,
                product_id=f"scenario-{index:02d}",
                name=f"Category scenario: {sub}",
                category=category,
                sub_category=sub,
                source_url=AMFI_NAV_URL,
                retrieved_at=stamp,
                data_quality=CATEGORY_SCENARIO,
                is_current_observation=False,
                lock_in_months=lock_in,
                liquidity=liquidity,
                risk_level=risk,
                risk_score=score,
                notes=[
                    "Category-level modelling scenario only. This is NOT a named product, "
                    "NOT a current rate and NOT a recommendation.",
                    f"Live AMFI retrieval was unavailable: {reason}",
                ],
            )
        )
    return out
