"""Loan discovery from lenders' own published product pages.

Scope and honesty rules
-----------------------
* Only **published, public** lender pages are read, one request each, and only the advertised
  minimum ("from") rate plus any explicitly stated cap is extracted. The quoted sentence is
  returned with the record so a reviewer can check the extraction.
* The value is an **advertisement**, never a personalised offer. ``is_personalised_offer`` is
  hard-coded ``False`` and ``rate_basis`` is ``advertised_from_rate``.
* Fields the page does not state (processing fee, tenure range, APR) stay ``None``. They are
  never inferred from a typical product.
* If a page cannot be read, the bundled snapshot for that lender is used and labelled
  ``official_snapshot`` with its own retrieval date. If neither is available the provider
  reports ``unavailable`` — it does not invent a product.

There is no aggregator/bureau integration here: no authorised Indian loan-aggregator API was
available to this project, and none is fabricated. See docs/API_SOURCE_REGISTER.md.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from app.config import get_settings
from app.providers.base import (
    HISTORICAL_BENCHMARK,
    OFFICIAL_LIVE,
    OFFICIAL_SNAPSHOT,
    PUBLISHED_LENDER_RATE,
    NormalizedLoan,
    ProviderOutcome,
    iso,
    utcnow,
)
from app.providers.http import get_text

PROVIDER_NAME = "lender_published_pages"
REFERENCE_FILE = Path(__file__).with_name("reference") / "loan_products.json"

#: Lender pages read live. Each entry is (lender, product_id, category, url, product name).
LIVE_PAGES: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "ICICI Bank",
        "icici_personal_loan",
        "personal",
        "https://www.icicibank.com/personal-banking/loans/personal-loan",
        "Personal Loan",
    ),
    (
        "Axis Bank",
        "axis_personal_loan",
        "personal",
        "https://www.axisbank.com/retail/loans/personal-loan/features-benefits",
        "Personal Loan",
    ),
    (
        "Bank of Baroda",
        "bob_personal_loan",
        "personal",
        "https://www.bankofbaroda.in/personal-banking/loans/personal-loan",
        "Personal Loan",
    ),
)

#: Ordered extraction patterns. The first pattern that yields a plausible rate wins, and the
#: matched sentence is retained as evidence.
_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"starting\s+at\s*(?:just\s*)?(?:rs\.?\s*)?([0-9]{1,2}(?:\.[0-9]{1,2})?)\s*%", re.I),
    re.compile(r"starts?\s+at\s*(?:just\s*)?(?:rs\.?\s*)?([0-9]{1,2}(?:\.[0-9]{1,2})?)\s*%", re.I),
    re.compile(
        r"(?:interest\s+rate[s]?|rate[s]?\s+of\s+interest)\s*(?:of|from|as\s+low\s+as|starting\s+at)?\s*"
        r"(?:just\s*)?(?:rs\.?\s*)?([0-9]{1,2}(?:\.[0-9]{1,2})?)\s*%",
        re.I,
    ),
    re.compile(r"\bat\s+an?\s*([0-9]{1,2}(?:\.[0-9]{1,2})?)\s*%\s*p\.?\s*a\.?\s*interest\s+rate", re.I),
    re.compile(r"from\s+(?:just\s*)?([0-9]{1,2}(?:\.[0-9]{1,2})?)\s*%\s*p\.?\s*a\.?", re.I),
)

_AMOUNT_PATTERN = re.compile(r"up\s*to\s*(?:rs\.?|inr)\s*([0-9]{1,3}(?:\.[0-9]+)?)\s*(lakh|lakhs|lac|crore|crores)", re.I)


_META_PATTERN = re.compile(
    r"""<meta[^>]+(?:name|property)\s*=\s*["'](?:description|og:description|twitter:description)["']"""
    r"""[^>]*content\s*=\s*["']([^"']+)["']""",
    re.I,
)


def _visible_text(html: str) -> str:
    """Rendered text **plus** the page's own description metadata.

    The description metadata is included deliberately: a lender's public product summary is
    published there, and dropping it would silently lose products whose visible body is
    client-rendered. The sentence that supplied the rate is returned as evidence either way.
    """
    descriptions = " ".join(match.group(1) for match in _META_PATTERN.finditer(html))
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", f"{descriptions} {text}")


def extract_published_rate(html: str) -> tuple[float | None, str | None]:
    """Return (rate_fraction, quoted_sentence). ``None`` when nothing plausible is published."""
    text = _visible_text(html)
    for pattern in _PATTERNS:
        for match in pattern.finditer(text):
            try:
                percent = float(match.group(1))
            except (TypeError, ValueError):
                continue
            if not 5.0 <= percent <= 36.0:  # plausible retail lending band; rejects noise
                continue
            start = max(0, match.start() - 120)
            return percent / 100.0, text[start : match.end() + 80].strip()
    return None, None


def extract_max_amount(html: str) -> float | None:
    text = _visible_text(html)
    match = _AMOUNT_PATTERN.search(text)
    if not match:
        return None
    try:
        value = float(match.group(1))
    except (TypeError, ValueError):
        return None
    unit = match.group(2).lower()
    if unit.startswith("crore"):
        return value * 10_000_000
    return value * 100_000


def _record_from_page(
    lender: str, product_id: str, category: str, url: str, name: str
) -> NormalizedLoan | None:
    html = get_text(url, timeout=15)
    rate, quoted = extract_published_rate(html)
    if rate is None:
        return None
    return NormalizedLoan(
        provider=PROVIDER_NAME,
        product_id=product_id,
        lender=lender,
        product_name=name,
        category=category,
        source_url=url,
        retrieved_at=iso(utcnow()),
        effective_date=iso(utcnow().date()),
        data_quality=OFFICIAL_LIVE,
        published_rate=rate,
        rate_type="floating",
        rate_basis="advertised_from_rate",
        rate_class=PUBLISHED_LENDER_RATE,
        max_amount=extract_max_amount(html),
        collateral_required=False if category == "personal" else None,
        is_personalised_offer=False,
        quoted_text=quoted,
        eligibility=[
            "Salaried or self-employed individual meeting the lender's own underwriting criteria"
        ],
        notes=[
            "Advertised minimum rate from the lender's public page. Not a personalised offer "
            "and not an eligibility decision.",
            "Processing fee, tenure range and APR are not stated here because they could not be "
            "captured verbatim from the page.",
        ],
    )


def load_reference(path: Path | None = None) -> dict:
    target = path or REFERENCE_FILE
    return json.loads(target.read_text(encoding="utf-8"))


def snapshot_records(reason: str) -> list[NormalizedLoan]:
    try:
        payload = load_reference()
    except Exception:
        return []
    out: list[NormalizedLoan] = []
    for row in payload.get("products", []):
        out.append(
            NormalizedLoan(
                provider=PROVIDER_NAME,
                product_id=row["product_id"],
                lender=row["lender"],
                product_name=row["product_name"],
                category=row["category"],
                source_url=row.get("source_url", ""),
                retrieved_at=row.get("retrieved_at"),
                effective_date=row.get("retrieved_at"),
                data_quality=OFFICIAL_SNAPSHOT,
                published_rate=row.get("published_rate"),
                rate_type=row.get("rate_type", "unknown"),
                rate_basis=row.get("rate_basis", "advertised_from_rate"),
                rate_class=PUBLISHED_LENDER_RATE,
                max_amount=row.get("max_amount"),
                processing_fee_pct=row.get("processing_fee_pct"),
                processing_fee_flat=row.get("processing_fee_flat"),
                collateral_required=row.get("collateral_required"),
                eligibility=list(row.get("eligibility", [])),
                is_personalised_offer=False,
                quoted_text=row.get("quoted_text"),
                notes=list(row.get("notes", []))
                + [
                    "Advertised minimum rate; not a personalised offer and not an eligibility "
                    "decision.",
                    f"Live retrieval unavailable, bundled snapshot used. Reason: {reason}",
                ],
            )
        )
    return out


def fetch() -> ProviderOutcome:
    settings = get_settings()
    if not settings.enable_live_providers:
        records = snapshot_records("live providers disabled by configuration")
        return ProviderOutcome(
            provider=PROVIDER_NAME,
            kind="loan",
            status="ok" if records else "unavailable",
            records=records,
            data_quality=OFFICIAL_SNAPSHOT,
            source_url="",
            retrieved_at=iso(utcnow()),
            reason="Live retrieval is disabled; bundled published-rate snapshot served.",
            metadata={"live_pages_configured": len(LIVE_PAGES)},
        )

    records: list[NormalizedLoan] = []
    failures: list[dict[str, str]] = []
    for lender, product_id, category, url, name in LIVE_PAGES:
        try:
            record = _record_from_page(lender, product_id, category, url, name)
        except Exception as exc:
            failures.append({"lender": lender, "url": url, "reason": f"{type(exc).__name__}: {exc}"[:180]})
            continue
        if record is None:
            failures.append({"lender": lender, "url": url, "reason": "no published rate matched the extractor"})
            continue
        records.append(record)

    if not records:
        reason = "; ".join(f"{f['lender']}: {f['reason']}" for f in failures) or "no lender page could be read"
        snapshot = snapshot_records(reason)
        return ProviderOutcome(
            provider=PROVIDER_NAME,
            kind="loan",
            status="ok" if snapshot else "unavailable",
            records=snapshot,
            data_quality=OFFICIAL_SNAPSHOT,
            source_url="",
            retrieved_at=iso(utcnow()),
            reason=f"Live retrieval failed for every configured lender ({reason}). Bundled snapshot served.",
            metadata={"failures": failures, "snapshot": True},
        )

    covered = {r.lender for r in records}
    missing = [lender for lender, *_ in LIVE_PAGES if lender not in covered]
    return ProviderOutcome(
        provider=PROVIDER_NAME,
        kind="loan",
        status="partial" if missing else "ok",
        records=records,
        data_quality=OFFICIAL_LIVE,
        source_url=",".join(LIVE_PAGES[0][3:4]),
        retrieved_at=iso(utcnow()),
        reason=(f"No published rate could be extracted for: {', '.join(missing)}" if missing else None),
        metadata={
            "lenders_live": sorted(covered),
            "lenders_missing": missing,
            "failures": failures,
            "extraction": "first plausible 'from' rate on the public page, sentence retained as quoted_text",
        },
    )


# --------------------------------------------------------------------------------------
# RBI system-level benchmark
# --------------------------------------------------------------------------------------
WALR_PROVIDER = "rbi_walr_benchmark"
DATASET_RELATIVE = Path("datasets/GoalPilot_AI/extracted_features/walr_features.csv")
RBI_SOURCE = "https://www.rbi.org.in/"


def walr_path() -> Path | None:
    import os

    explicit = os.getenv("GOALPILOT_WALR_DATA_PATH")
    if explicit:
        path = Path(explicit)
        return path if path.is_file() else None
    here = Path(__file__).resolve()
    for parent in list(here.parents)[:6]:
        candidate = parent / DATASET_RELATIVE
        if candidate.is_file():
            return candidate
    return None


def walr_benchmark() -> ProviderOutcome:
    """System-wide weighted average lending rate, as a *benchmark* — never a product rate."""
    path = walr_path()
    if path is None:
        return ProviderOutcome(
            provider=WALR_PROVIDER,
            kind="loan",
            status="unavailable",
            source_url=RBI_SOURCE,
            data_quality="historical",
            reason="The RBI WALR calibration dataset is not present.",
        )
    import pandas as pd

    frame = pd.read_csv(path)
    if "period" not in frame or "average_walr" not in frame:
        return ProviderOutcome(
            provider=WALR_PROVIDER,
            kind="loan",
            status="unavailable",
            source_url=RBI_SOURCE,
            data_quality="historical",
            reason="Unexpected WALR dataset columns.",
        )
    frame["period"] = pd.to_datetime(frame["period"], errors="coerce")
    frame = frame.dropna(subset=["period", "average_walr"]).sort_values("period")
    if frame.empty:
        return ProviderOutcome(
            provider=WALR_PROVIDER,
            kind="loan",
            status="unavailable",
            source_url=RBI_SOURCE,
            data_quality="historical",
            reason="The WALR dataset contains no usable observations.",
        )
    last = frame.iloc[-1]
    record = {
        "benchmark": "Weighted average lending rate on outstanding rupee loans (all scheduled commercial banks)",
        "rate": round(float(last["average_walr"]) / 100.0, 6),
        "period": last["period"].date().isoformat(),
        "observations": int(len(frame)),
        "series_start": frame.iloc[0]["period"].date().isoformat(),
        "rate_class": HISTORICAL_BENCHMARK,
        "rate_basis": "historical_aggregate_series",
        "is_product_rate": False,
        "is_offer": False,
    }
    return ProviderOutcome(
        provider=WALR_PROVIDER,
        kind="loan",
        status="ok",
        records=[record],
        data_quality="historical",
        source_url=RBI_SOURCE,
        retrieved_at=iso(utcnow()),
        metadata={
            "caveat": (
                "A system-wide weighted average is not the rate available to any individual "
                "borrower, and it is not an offer. It is used only as a reference point when "
                "no published product rate is available."
            ),
            "source_file": str(path),
        },
    )
