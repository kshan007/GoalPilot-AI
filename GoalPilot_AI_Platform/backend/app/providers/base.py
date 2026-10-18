"""Provider abstraction for externally sourced investment and loan information.

Design rules (enforced by the types, not by convention):

* A provider **never** returns a value it did not get from somewhere. Every record carries
  ``data_quality``, ``source_url``, ``retrieved_at`` and — where the source publishes one — an
  ``effective_date``. A missing field stays ``None``; nothing is filled in.
* A provider failure is isolated. :class:`ProviderRegistry` catches per-provider exceptions
  and returns a :class:`ProviderOutcome` with ``status="unavailable"`` plus the reason, so a
  dead external source can never take down the financial profile, goals, LP or RL planning.
* Provenance classes are distinct and never interchangeable:

  ``official_live``      fetched from the official source during this request
  ``official_snapshot``  bundled copy of an official publication, with its as-of date
  ``historical``         observed history (e.g. an index level series), never a forecast
  ``unofficial_mirror``  a third-party mirror of official data (only for NAV history)
  ``category_scenario``  a labelled modelling assumption, not a product and not a quote
"""
from __future__ import annotations

import datetime as dt
import threading
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Iterable, Protocol, runtime_checkable


# --------------------------------------------------------------------------------------
# provenance vocabulary
# --------------------------------------------------------------------------------------
OFFICIAL_LIVE = "official_live"
OFFICIAL_SNAPSHOT = "official_snapshot"
HISTORICAL = "historical"
UNOFFICIAL_MIRROR = "unofficial_mirror"
CATEGORY_SCENARIO = "category_scenario"

DATA_QUALITY_LABELS = {
    OFFICIAL_LIVE: "Official source, retrieved live for this response",
    OFFICIAL_SNAPSHOT: "Bundled copy of an official publication (see effective date)",
    HISTORICAL: "Observed historical data; not a forecast",
    UNOFFICIAL_MIRROR: "Third-party mirror of official NAV history",
    CATEGORY_SCENARIO: "Labelled modelling assumption, not a product quote",
}

#: The four claims a borrowing cost can make. A response must say which one it is making.
HISTORICAL_BENCHMARK = "historical_benchmark"
PUBLISHED_LENDER_RATE = "published_lender_rate"
ESTIMATED_SCENARIO = "estimated_scenario"
PERSONALISED_OFFER = "personalised_offer"

RATE_CLASSES = (
    HISTORICAL_BENCHMARK,
    PUBLISHED_LENDER_RATE,
    ESTIMATED_SCENARIO,
    PERSONALISED_OFFER,
)

RATE_CLASS_LABELS = {
    HISTORICAL_BENCHMARK: (
        "Historical system benchmark (aggregate series). Not a product, not an offer, and not "
        "the rate available to any particular borrower."
    ),
    PUBLISHED_LENDER_RATE: (
        "Rate published by the lender on its own product page. Advertised minimum; not a "
        "personalised offer and not an eligibility decision."
    ),
    ESTIMATED_SCENARIO: (
        "Modelling assumption used for illustration because no published product was available "
        "for this category. Configurable; not a market quote."
    ),
    PERSONALISED_OFFER: (
        "Rate quoted to this user by a lender. Only present when the user supplied it; the "
        "platform does not obtain offers on the user's behalf."
    ),
}

#: Freshness thresholds, in hours, used to flag stale records.
FRESHNESS_HOURS = {"official_live": 24, "official_snapshot": 24 * 120, "historical": 24 * 365,
                   "unofficial_mirror": 48, "category_scenario": 24 * 365}


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _parse_timestamp(value: str | None) -> dt.datetime | None:
    """Parse an ISO timestamp, coercing naive values (including date-only strings) to UTC.

    Sources publish either a full timestamp or just a date. Comparing a naive datetime with an
    aware "now" raises, so the coercion happens here once instead of in every caller.
    """
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed


def iso(value: dt.datetime | dt.date | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value.astimezone(dt.timezone.utc).isoformat(timespec="seconds")
    return value.isoformat()


# --------------------------------------------------------------------------------------
# normalised records
# --------------------------------------------------------------------------------------
@dataclass
class NormalizedInvestment:
    """One investment instrument, as the source describes it."""

    provider: str
    product_id: str
    name: str
    category: str                      # normalised: equity_mf | debt_mf | hybrid_mf | ...
    sub_category: str = ""
    issuer: str | None = None
    source_url: str = ""
    provider_identifier: str | None = None
    retrieved_at: str | None = None
    effective_date: str | None = None  # the source's own as-of date (e.g. NAV date)
    data_quality: str = OFFICIAL_SNAPSHOT
    is_current_observation: bool = False

    nav: float | None = None
    published_rate: float | None = None
    rate_basis: str | None = None
    min_investment: float | None = None
    min_sip: float | None = None
    lock_in_months: int | None = None
    liquidity: str = "unknown"         # daily | t_plus_1 | lock_in | at_maturity | unknown
    risk_level: str = "unknown"        # low | moderate | high | very_high | unknown
    risk_score: float | None = None    # 0..1, derived from the category (documented)
    expense_ratio: float | None = None
    exit_load: str | None = None
    tax_note: str | None = None
    eligibility: list[str] = field(default_factory=list)
    historical_returns: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def completeness(self) -> float:
        fields = (
            self.nav if self.nav is not None else self.published_rate,
            self.min_investment,
            self.lock_in_months,
            self.risk_level if self.risk_level != "unknown" else None,
            self.effective_date,
            self.source_url or None,
        )
        return round(sum(1 for f in fields if f not in (None, "")) / len(fields), 3)

    def freshness(self) -> str:
        """fresh | stale | unknown — measured against the record's own retrieved_at."""
        when = _parse_timestamp(self.retrieved_at)
        if when is None:
            return "unknown"
        age_hours = (utcnow() - when).total_seconds() / 3600
        return "fresh" if age_hours <= FRESHNESS_HOURS.get(self.data_quality, 24) else "stale"

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["completeness"] = self.completeness()
        data["freshness"] = self.freshness()
        data["data_quality_label"] = DATA_QUALITY_LABELS.get(self.data_quality, self.data_quality)
        return data


@dataclass
class NormalizedLoan:
    """One borrowing product as *published*. Never a personalised offer."""

    provider: str
    product_id: str
    lender: str
    product_name: str
    category: str                      # personal | education | home | vehicle | secured | other
    source_url: str = ""
    retrieved_at: str | None = None
    effective_date: str | None = None
    data_quality: str = OFFICIAL_SNAPSHOT

    published_rate: float | None = None          # annual, as a fraction (0.0999)
    rate_type: str = "unknown"                   # fixed | floating | hybrid | unknown
    rate_basis: str = "advertised_from_rate"     # what the number actually means
    #: One of :data:`RATE_CLASSES`. This is the field a consumer must branch on: a published
    #: lender rate, a historical system benchmark, a modelling assumption and a personal offer
    #: are four different claims and are never interchangeable.
    rate_class: str = "published_lender_rate"
    apr_estimate: float | None = None
    processing_fee_pct: float | None = None
    processing_fee_flat: float | None = None
    other_fees: list[dict[str, Any]] = field(default_factory=list)
    min_tenure_months: int | None = None
    max_tenure_months: int | None = None
    min_amount: float | None = None
    max_amount: float | None = None
    collateral_required: bool | None = None
    eligibility: list[str] = field(default_factory=list)
    prepayment_terms: str | None = None
    is_personalised_offer: bool = False
    quoted_text: str | None = None
    notes: list[str] = field(default_factory=list)

    def completeness(self) -> float:
        fields = (
            self.published_rate,
            self.max_amount,
            self.max_tenure_months,
            self.processing_fee_pct if self.processing_fee_pct is not None else self.processing_fee_flat,
            self.rate_type if self.rate_type != "unknown" else None,
            self.source_url or None,
        )
        return round(sum(1 for f in fields if f not in (None, "")) / len(fields), 3)

    def freshness(self) -> str:
        when = _parse_timestamp(self.retrieved_at)
        if when is None:
            return "unknown"
        age_hours = (utcnow() - when).total_seconds() / 3600
        return "fresh" if age_hours <= FRESHNESS_HOURS.get(self.data_quality, 24) else "stale"

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["completeness"] = self.completeness()
        data["freshness"] = self.freshness()
        data["data_quality_label"] = DATA_QUALITY_LABELS.get(self.data_quality, self.data_quality)
        return data


# --------------------------------------------------------------------------------------
# provider protocol + outcomes
# --------------------------------------------------------------------------------------
@dataclass
class ProviderOutcome:
    provider: str
    kind: str                                   # investment | loan | economic
    status: str                                 # ok | partial | unavailable | disabled
    records: list[Any] = field(default_factory=list)
    data_quality: str | None = None
    source_url: str = ""
    retrieved_at: str | None = None
    reason: str | None = None
    runtime_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def count(self) -> int:
        return len(self.records)

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "kind": self.kind,
            "status": self.status,
            "count": self.count,
            "data_quality": self.data_quality,
            "data_quality_label": DATA_QUALITY_LABELS.get(self.data_quality or "", None),
            "source_url": self.source_url,
            "retrieved_at": self.retrieved_at,
            "reason": self.reason,
            "runtime_ms": self.runtime_ms,
            "metadata": self.metadata,
        }


@runtime_checkable
class Provider(Protocol):
    name: str
    kind: str
    source_url: str
    data_quality: str

    def fetch(self) -> ProviderOutcome:  # pragma: no cover - protocol
        ...


# --------------------------------------------------------------------------------------
# in-process TTL cache
# --------------------------------------------------------------------------------------
class TTLCache:
    """Small thread-safe TTL cache.

    Caching is per-process and deliberately not persisted: a cached external payload is not
    user data, and writing it to the database would create a second, staler source of truth.
    The original ``retrieved_at`` is preserved on every record, so a cache hit is still
    reported with the time the data was actually fetched.
    """

    def __init__(self, ttl_seconds: int = 6 * 3600) -> None:
        self._ttl = max(0, int(ttl_seconds))
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        if self._ttl == 0:
            return None
        with self._lock:
            hit = self._store.get(key)
            if hit is None:
                return None
            stored_at, value = hit
            if time.time() - stored_at > self._ttl:
                self._store.pop(key, None)
                return None
            return value

    def put(self, key: str, value: Any) -> None:
        if self._ttl == 0:
            return
        with self._lock:
            self._store[key] = (time.time(), value)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


# --------------------------------------------------------------------------------------
# registry
# --------------------------------------------------------------------------------------
class ProviderRegistry:
    """Runs providers in isolation and returns one outcome per provider."""

    def __init__(self, cache: TTLCache | None = None) -> None:
        self._providers: dict[str, Provider] = {}
        self.cache = cache or TTLCache()

    def register(self, provider: Provider) -> None:
        self._providers[provider.name] = provider

    def clear(self) -> None:
        self._providers.clear()
        self.cache.clear()

    def names(self, kind: str | None = None) -> list[str]:
        return sorted(
            name for name, p in self._providers.items() if kind is None or p.kind == kind
        )

    def get(self, name: str) -> Provider | None:
        return self._providers.get(name)

    def run(
        self,
        kind: str | None = None,
        *,
        only: Iterable[str] | None = None,
    ) -> list[ProviderOutcome]:
        wanted = set(only) if only is not None else None
        outcomes: list[ProviderOutcome] = []
        for name, provider in sorted(self._providers.items()):
            if kind is not None and provider.kind != kind:
                continue
            if wanted is not None and name not in wanted:
                continue
            outcomes.append(self._run_one(provider))
        return outcomes

    def _run_one(self, provider: Provider) -> ProviderOutcome:
        cached = self.cache.get(provider.name)
        if isinstance(cached, ProviderOutcome):
            return cached
        started = time.perf_counter()
        try:
            outcome = provider.fetch()
        except Exception as exc:  # a provider must never take the request down
            outcome = ProviderOutcome(
                provider=provider.name,
                kind=provider.kind,
                status="unavailable",
                source_url=provider.source_url,
                data_quality=provider.data_quality,
                reason=f"{type(exc).__name__}: {str(exc)[:300]}",
            )
        outcome.runtime_ms = int((time.perf_counter() - started) * 1000)
        if outcome.status in {"ok", "partial"}:
            self.cache.put(provider.name, outcome)
        return outcome


def callable_provider(
    name: str,
    kind: str,
    source_url: str,
    data_quality: str,
    fn: Callable[[], ProviderOutcome],
) -> Provider:
    """Wrap a plain function as a provider (used by the built-in implementations)."""

    class _Fn:
        pass

    obj = _Fn()
    obj.name = name          # type: ignore[attr-defined]
    obj.kind = kind          # type: ignore[attr-defined]
    obj.source_url = source_url  # type: ignore[attr-defined]
    obj.data_quality = data_quality  # type: ignore[attr-defined]
    obj.fetch = fn           # type: ignore[attr-defined]
    return obj  # type: ignore[return-value]
