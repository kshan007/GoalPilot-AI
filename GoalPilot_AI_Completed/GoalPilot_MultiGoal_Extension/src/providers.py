"""Offline-safe funding-option providers for the GoalPilot optimizer.

The provider layer keeps data provenance outside the LP solver. Live public
fetchers can be added later, but tests and demos use deterministic local
fixtures so the optimizer remains reproducible without network access.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import csv
import json
from pathlib import Path
from typing import Any, Iterable, Protocol


@dataclass(frozen=True)
class InvestmentCandidate:
    candidate_id: str
    name: str
    asset_class: str
    source: str
    provenance: str
    expected_annual_return: float
    risk_score: float
    min_horizon_months: int = 1
    liquidity_days: int = 0
    observation_date: str = ""
    assumption_label: str = "offline_fixture"

    @classmethod
    def from_mapping(cls, row: dict[str, Any]) -> "InvestmentCandidate":
        return cls(
            candidate_id=str(row["candidate_id"]),
            name=str(row["name"]),
            asset_class=str(row["asset_class"]),
            source=str(row["source"]),
            provenance=str(row.get("provenance", "unknown")),
            expected_annual_return=float(row["expected_annual_return"]),
            risk_score=float(row["risk_score"]),
            min_horizon_months=int(row.get("min_horizon_months", 1)),
            liquidity_days=int(row.get("liquidity_days", 0)),
            observation_date=str(row.get("observation_date", "")),
            assumption_label=str(row.get("assumption_label", "offline_fixture")),
        )

    def validate(self) -> None:
        if not self.candidate_id or not self.name:
            raise ValueError("investment candidate requires candidate_id and name")
        if self.expected_annual_return <= -1:
            raise ValueError("expected_annual_return must be greater than -100%")
        if not 0 <= self.risk_score <= 1:
            raise ValueError("risk_score must be between 0 and 1")
        if self.min_horizon_months < 1 or self.liquidity_days < 0:
            raise ValueError("investment horizon/liquidity fields are invalid")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LoanOffer:
    offer_id: str
    lender: str
    product: str
    source: str
    provenance: str
    annual_interest_rate: float
    tenure_months: int
    max_principal: float
    fee_rate: float = 0.0
    assumption_label: str = "synthetic_fixture_not_lender_quote"

    @classmethod
    def from_mapping(cls, row: dict[str, Any]) -> "LoanOffer":
        return cls(
            offer_id=str(row["offer_id"]),
            lender=str(row["lender"]),
            product=str(row["product"]),
            source=str(row["source"]),
            provenance=str(row.get("provenance", "unknown")),
            annual_interest_rate=float(row["annual_interest_rate"]),
            tenure_months=int(row["tenure_months"]),
            max_principal=float(row["max_principal"]),
            fee_rate=float(row.get("fee_rate", 0.0)),
            assumption_label=str(row.get("assumption_label", "synthetic_fixture_not_lender_quote")),
        )

    def validate(self) -> None:
        if self.annual_interest_rate < 0:
            raise ValueError("loan annual_interest_rate cannot be negative")
        if self.tenure_months <= 0 or self.max_principal < 0:
            raise ValueError("loan tenure/max_principal fields are invalid")
        if self.fee_rate < 0:
            raise ValueError("loan fee_rate cannot be negative")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SavingsProduct:
    product_id: str
    name: str
    product_type: str
    source: str
    provenance: str
    annual_return: float
    lock_in_months: int = 0
    assumption_label: str = "offline_fixture"

    @classmethod
    def from_mapping(cls, row: dict[str, Any]) -> "SavingsProduct":
        return cls(
            product_id=str(row["product_id"]),
            name=str(row["name"]),
            product_type=str(row["product_type"]),
            source=str(row["source"]),
            provenance=str(row.get("provenance", "unknown")),
            annual_return=float(row["annual_return"]),
            lock_in_months=int(row.get("lock_in_months", 0)),
            assumption_label=str(row.get("assumption_label", "offline_fixture")),
        )

    def validate(self) -> None:
        if self.annual_return <= -1:
            raise ValueError("annual_return must be greater than -100%")
        if self.lock_in_months < 0:
            raise ValueError("lock_in_months cannot be negative")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EconomicScenario:
    name: str
    source: str
    provenance: str
    annual_inflation: float
    savings_return: float
    investment_return: float
    loan_annual_rate: float
    observation_date: str = ""
    assumption_label: str = "offline_fixture"

    @classmethod
    def from_mapping(cls, row: dict[str, Any]) -> "EconomicScenario":
        return cls(
            name=str(row["name"]),
            source=str(row["source"]),
            provenance=str(row.get("provenance", "unknown")),
            annual_inflation=float(row["annual_inflation"]),
            savings_return=float(row["savings_return"]),
            investment_return=float(row["investment_return"]),
            loan_annual_rate=float(row["loan_annual_rate"]),
            observation_date=str(row.get("observation_date", "")),
            assumption_label=str(row.get("assumption_label", "offline_fixture")),
        )

    def validate(self) -> None:
        for name, value in [
            ("annual_inflation", self.annual_inflation),
            ("savings_return", self.savings_return),
            ("investment_return", self.investment_return),
            ("loan_annual_rate", self.loan_annual_rate),
        ]:
            if value <= -1:
                raise ValueError(f"{name} must be greater than -100%")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Provider(Protocol):
    def load(self) -> list[Any]:
        ...


class LocalJSONProvider:
    def __init__(self, path: str | Path, factory):
        self.path = Path(path)
        self.factory = factory

    def load(self) -> list[Any]:
        data = json.loads(self.path.read_text())
        rows = data if isinstance(data, list) else data.get("records", [])
        return _build_records(rows, self.factory)


class LocalCSVProvider:
    def __init__(self, path: str | Path, factory):
        self.path = Path(path)
        self.factory = factory

    def load(self) -> list[Any]:
        with self.path.open(newline="") as fh:
            return _build_records(csv.DictReader(fh), self.factory)


def _build_records(rows: Iterable[dict[str, Any]], factory) -> list[Any]:
    records = []
    for row in rows:
        item = factory(dict(row))
        item.validate()
        records.append(item)
    return records


def _coerce(items: list[Any] | None, factory) -> list[Any]:
    if not items:
        return []
    out = []
    for item in items:
        if isinstance(item, dict):
            item = factory(item)
        item.validate()
        out.append(item)
    return out


def select_investment_candidate(
    candidates: list[InvestmentCandidate | dict[str, Any]] | None,
    *,
    risk_capacity: float,
    min_horizon_months: int,
) -> InvestmentCandidate | None:
    valid = [
        c for c in _coerce(candidates, InvestmentCandidate.from_mapping)
        if c.risk_score <= risk_capacity and c.min_horizon_months <= min_horizon_months
    ]
    if not valid:
        return None
    return max(valid, key=lambda c: (c.expected_annual_return, -c.risk_score, -c.liquidity_days))


def select_loan_offer(offers: list[LoanOffer | dict[str, Any]] | None) -> LoanOffer | None:
    valid = _coerce(offers, LoanOffer.from_mapping)
    if not valid:
        return None
    return min(valid, key=lambda o: (o.annual_interest_rate + o.fee_rate, o.tenure_months))


def select_savings_product(products: list[SavingsProduct | dict[str, Any]] | None) -> SavingsProduct | None:
    valid = _coerce(products, SavingsProduct.from_mapping)
    if not valid:
        return None
    return max(valid, key=lambda p: (p.annual_return, -p.lock_in_months))
