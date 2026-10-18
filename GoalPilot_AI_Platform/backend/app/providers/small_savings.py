"""Government small-savings schemes, from a curated, source-annotated reference file.

The Department of Economic Affairs notifies these rates quarterly. Its site could not be
retrieved from the build host (the TLS chain is not trusted by the host store, and TLS
verification is deliberately **not** disabled), so the platform ships a curated snapshot and
states exactly what it is:

* the notified **rate** and the **quarter** it applies to,
* the official publisher and the official URL,
* the fact that the official page could not be fetched, and the cross-check that was used,
* that the file must be re-verified before each demonstration.

Only schemes whose rate was verified are present. Nothing is inferred, and no scheme that was
not verified is included.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.providers.base import (
    OFFICIAL_SNAPSHOT,
    NormalizedInvestment,
    ProviderOutcome,
    iso,
    utcnow,
)

PROVIDER_NAME = "govt_small_savings"
REFERENCE_FILE = Path(__file__).with_name("reference") / "small_savings.json"
SOURCE_URL = "https://dea.gov.in/"


def load_reference(path: Path | None = None) -> dict:
    target = path or REFERENCE_FILE
    return json.loads(target.read_text(encoding="utf-8"))


def to_records(payload: dict, *, retrieved_at=None) -> list[NormalizedInvestment]:
    retrieved_at = retrieved_at or utcnow()
    verification = payload.get("verification", {})
    effective_from = payload.get("effective_from")
    effective_to = payload.get("effective_to")
    records: list[NormalizedInvestment] = []

    for row in payload.get("products", []):
        notes = list(row.get("notes", []))
        notes.append(
            f"Notified rate for {payload.get('quarter', 'the stated quarter')} "
            f"({effective_from} to {effective_to}). Rates are reviewed quarterly."
        )
        if verification.get("cross_check_note"):
            notes.append(
                "Provenance: " + str(verification["cross_check_note"])[:400]
            )
        records.append(
            NormalizedInvestment(
                provider=PROVIDER_NAME,
                product_id=row["product_id"],
                name=row["name"],
                category=row.get("category", "govt_scheme"),
                sub_category=row.get("sub_category", ""),
                issuer=row.get("issuer"),
                source_url=SOURCE_URL,
                provider_identifier=row["product_id"],
                retrieved_at=iso(retrieved_at),
                effective_date=effective_from,
                data_quality=OFFICIAL_SNAPSHOT,
                is_current_observation=False,
                published_rate=row.get("published_rate"),
                rate_basis=row.get("rate_basis"),
                min_investment=row.get("min_investment"),
                lock_in_months=row.get("lock_in_months"),
                liquidity=row.get("liquidity", "unknown"),
                risk_level=row.get("risk_level", "low"),
                risk_score=row.get("risk_score"),
                tax_note=row.get("tax_note"),
                eligibility=list(row.get("eligibility", [])),
                notes=notes,
            )
        )
    return records


def fetch() -> ProviderOutcome:
    payload = load_reference()
    records = to_records(payload)
    if not records:
        return ProviderOutcome(
            provider=PROVIDER_NAME,
            kind="investment",
            status="unavailable",
            source_url=SOURCE_URL,
            data_quality=OFFICIAL_SNAPSHOT,
            reason="The bundled small-savings reference file contains no products.",
        )
    verification = payload.get("verification", {})
    return ProviderOutcome(
        provider=PROVIDER_NAME,
        kind="investment",
        status="ok",
        records=records,
        data_quality=OFFICIAL_SNAPSHOT,
        source_url=SOURCE_URL,
        retrieved_at=records[0].retrieved_at,
        metadata={
            "quarter": payload.get("quarter"),
            "effective_from": payload.get("effective_from"),
            "effective_to": payload.get("effective_to"),
            "curated_at": payload.get("curated_at"),
            "official_publisher": verification.get("official_publisher"),
            "live_refresh_available": False,
            "live_refresh_reason": verification.get("official_page_note"),
            "maintenance": verification.get("maintenance"),
            "included_schemes": [r.product_id for r in records],
            "excluded_unverified": ["NSC", "KVP", "Post Office Time Deposit"],
        },
    )
