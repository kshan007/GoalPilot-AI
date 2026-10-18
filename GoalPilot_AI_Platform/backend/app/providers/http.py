"""Minimal HTTP client used by the providers.

One place for the timeout, the user agent, response-size limits and error normalisation, so a
provider cannot accidentally hang a request or accept an unbounded body. TLS verification is
**never** disabled: a source whose certificate chain this host cannot validate is reported as
unavailable (with the reason) rather than fetched insecurely.
"""
from __future__ import annotations

import json
from typing import Any

import httpx

from app.config import get_settings

USER_AGENT = (
    "GoalPilotAI/1.0 (academic research prototype; contact: project maintainer) "
    "Python-httpx"
)

#: 8 MB is comfortably above the AMFI NAVAll file (~1.5 MB) and far below anything that could
#: exhaust memory in a request handler.
MAX_BYTES = 8 * 1024 * 1024


class ProviderUnavailable(RuntimeError):
    """The source could not be reached, or answered with something unusable."""


def _timeout() -> float:
    return float(get_settings().provider_http_timeout_seconds)


def get_text(url: str, *, timeout: float | None = None, headers: dict[str, str] | None = None) -> str:
    request_headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/plain,text/html,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-IN,en;q=0.9",
    }
    if headers:
        request_headers.update(headers)
    try:
        response = httpx.get(
            url,
            timeout=timeout or _timeout(),
            follow_redirects=True,
            headers=request_headers,
        )
    except httpx.HTTPError as exc:
        raise ProviderUnavailable(f"{type(exc).__name__}: {exc}") from exc

    if response.status_code >= 400:
        raise ProviderUnavailable(f"HTTP {response.status_code} from {url}")
    body = response.content
    if len(body) > MAX_BYTES:
        raise ProviderUnavailable(f"Response from {url} exceeded {MAX_BYTES} bytes")
    return body.decode(response.encoding or "utf-8", errors="replace")


def get_json(url: str, *, timeout: float | None = None, headers: dict[str, str] | None = None) -> Any:
    text = get_text(url, timeout=timeout, headers=headers)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProviderUnavailable(f"Response from {url} was not valid JSON") from exc
