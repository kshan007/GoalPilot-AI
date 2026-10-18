"""Single place where every external source is registered.

Adding a source means adding one ``register`` call here and nothing else: the discovery
services only ever see :class:`~app.providers.base.ProviderOutcome` objects, so a new provider
cannot change the shape of an API response.
"""
from __future__ import annotations

import threading

from app.config import get_settings
from app.providers import amfi, loans, market, small_savings
from app.providers.base import (
    OFFICIAL_LIVE,
    OFFICIAL_SNAPSHOT,
    ProviderOutcome,
    ProviderRegistry,
    TTLCache,
    callable_provider,
)

_LOCK = threading.Lock()
_REGISTRY: ProviderRegistry | None = None


def build_registry() -> ProviderRegistry:
    settings = get_settings()
    registry = ProviderRegistry(cache=TTLCache(settings.provider_cache_ttl_seconds))

    registry.register(
        callable_provider(amfi.PROVIDER_NAME, "investment", amfi.AMFI_NAV_URL, OFFICIAL_LIVE, amfi.fetch)
    )
    registry.register(
        callable_provider(
            small_savings.PROVIDER_NAME,
            "investment",
            small_savings.SOURCE_URL,
            OFFICIAL_SNAPSHOT,
            small_savings.fetch,
        )
    )
    registry.register(
        callable_provider(loans.PROVIDER_NAME, "loan", "", OFFICIAL_LIVE, loans.fetch)
    )
    registry.register(
        callable_provider(
            loans.WALR_PROVIDER, "loan", loans.RBI_SOURCE, "historical", loans.walr_benchmark
        )
    )
    registry.register(
        callable_provider("nse_index", "economic", market.NSE_SOURCE, OFFICIAL_LIVE, market.live_quote)
    )
    return registry


def get_registry() -> ProviderRegistry:
    global _REGISTRY
    with _LOCK:
        if _REGISTRY is None:
            _REGISTRY = build_registry()
        return _REGISTRY


def reset_registry() -> None:
    """Used by tests and by ``/providers/refresh``."""
    global _REGISTRY
    with _LOCK:
        if _REGISTRY is not None:
            _REGISTRY.clear()
        _REGISTRY = None


def investment_outcomes() -> list[ProviderOutcome]:
    return get_registry().run(kind="investment")


def loan_outcomes() -> list[ProviderOutcome]:
    return get_registry().run(kind="loan")


def economic_outcomes() -> list[ProviderOutcome]:
    return get_registry().run(kind="economic")


def status_table() -> list[dict]:
    """Report what each provider would do right now, without forcing a full fetch where the
    configured mode already decides the answer."""
    settings = get_settings()
    rows: list[dict] = []
    for name in get_registry().names():
        provider = get_registry().get(name)
        if provider is None:  # pragma: no cover - defensive
            continue
        if not settings.enable_live_providers and provider.data_quality == OFFICIAL_LIVE:
            rows.append(
                {
                    "provider": name,
                    "kind": provider.kind,
                    "data_quality": provider.data_quality,
                    "source_url": provider.source_url,
                    "status": "disabled",
                    "reason": "GOALPILOT_ENABLE_LIVE_PROVIDERS=false",
                }
            )
            continue
        rows.append(
            {
                "provider": name,
                "kind": provider.kind,
                "data_quality": provider.data_quality,
                "source_url": provider.source_url,
                "status": "configured",
                "reason": None,
            }
        )
    return rows
