"""Gemini access, isolated behind one function.

Rules enforced here
-------------------
* The API key is read from ``GEMINI_API_KEY`` only. It is never logged, never returned, and
  never written to a response.
* The model name is configurable (``GOALPILOT_GEMINI_MODEL``) so a quota or model-retirement
  change does not require a code change.
* Every failure mode (no key, import failure, timeout, quota, blocked response, invalid JSON)
  becomes :class:`LLMUnavailable` with a short machine-readable ``reason``. The caller always
  has a deterministic fallback, so the application never depends on the model being up.
* Structured output is requested with ``response_mime_type='application/json'`` and is then
  validated against a Pydantic schema by the caller. The model is never trusted to police its
  own output shape.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from app.config import get_settings

logger = logging.getLogger("goalpilot.llm")

#: Process-wide capability memory: once a model rejects `thinking_config`, stop sending it.
_STATE: dict[str, bool | None] = {"thinking_supported": None}


class LLMUnavailable(RuntimeError):
    def __init__(self, reason: str, message: str = "") -> None:
        super().__init__(message or reason)
        self.reason = reason
        self.message = message or reason


@dataclass
class LLMResult:
    text: str
    model: str
    latency_ms: int
    raw: dict[str, Any] | None = None


SYSTEM_INSTRUCTION = (
    "You are the explanation layer of an academic financial-planning prototype used in India. "
    "You never calculate anything. Every amount, rate, date and identifier you need is provided "
    "in the JSON input, and you must copy those values exactly if you refer to them. "
    "You must not invent products, rates, returns, eligibility, tax rules or market data. "
    "You must not describe any projection as guaranteed, assured, safe or risk-free. "
    "You must not recommend executing a transaction, applying for a loan, or buying a product. "
    "You must not contradict the optimiser: if the input says a goal is underfunded, say so. "
    "Write plain, direct Indian English for a non-specialist reader. "
    "Return ONLY a JSON object matching the requested schema."
)


def available() -> bool:
    settings = get_settings()
    if not settings.gemini_configured:
        return False
    try:
        import google.genai  # noqa: F401
    except Exception:
        return False
    return True


def status() -> dict[str, Any]:
    settings = get_settings()
    try:
        import google.genai  # noqa: F401

        sdk = True
    except Exception:
        sdk = False
    return {
        "provider": "google_gemini",
        "configured": bool(settings.gemini_api_key),
        "enabled": settings.llm_enabled,
        "sdk_installed": sdk,
        "model": settings.gemini_model,
        "available": available(),
        "key_env_var": "GEMINI_API_KEY",
        "fallback": "deterministic_explanation",
    }


def generate_json(
    prompt: str,
    *,
    schema_hint: dict[str, Any] | None = None,
    response_schema: Any | None = None,
) -> LLMResult:
    """Ask Gemini for one JSON object. Raises :class:`LLMUnavailable` on any failure."""
    settings = get_settings()
    if not settings.llm_enabled:
        raise LLMUnavailable("llm_disabled", "GOALPILOT_ENABLE_LLM is false.")
    if not settings.gemini_api_key:
        raise LLMUnavailable(
            "missing_api_key", "GEMINI_API_KEY is not set in the backend environment."
        )

    try:
        from google import genai
        from google.genai import types
    except Exception as exc:  # pragma: no cover - depends on the host
        raise LLMUnavailable("sdk_unavailable", f"google-genai is not importable: {exc}") from exc

    import time

    contents = prompt
    if schema_hint is not None:
        contents = (
            f"{prompt}\n\nReturn a JSON object with exactly this shape "
            f"(no extra keys, no markdown):\n{json.dumps(schema_hint, indent=2)}"
        )

    started = time.perf_counter()
    try:
        client = genai.Client(
            api_key=settings.gemini_api_key,
            http_options=types.HttpOptions(timeout=int(settings.gemini_timeout_seconds * 1000)),
        )
        # `response_schema` is what actually guarantees parseable output. JSON mime type alone
        # proved insufficient in practice: the first live call returned an unescaped quote and
        # was rejected as invalid JSON. Passing the Pydantic model makes the constraint part of
        # the request rather than a hope about the response.
        config_kwargs: dict[str, Any] = {
            "system_instruction": SYSTEM_INSTRUCTION,
            "response_mime_type": "application/json",
            "temperature": 0.1,
            "max_output_tokens": settings.gemini_max_output_tokens,
        }
        # Gemini 2.5 spends thinking tokens by default, and on this task that dominated latency
        # (22-27 s per generation). Thinking is configurable rather than hard-coded: the field is
        # only passed when the installed SDK knows it, so an older SDK keeps working.
        thinking_config = getattr(types, "ThinkingConfig", None)
        if (
            thinking_config is not None
            and settings.gemini_thinking_budget >= 0
            and _STATE["thinking_supported"] is not False
        ):
            config_kwargs["thinking_config"] = thinking_config(
                thinking_budget=settings.gemini_thinking_budget
            )

        try:
            response = client.models.generate_content(
                model=settings.gemini_model,
                contents=contents,
                config=types.GenerateContentConfig(**config_kwargs),
            )
        except Exception as exc:  # noqa: BLE001 - narrowed below
            # Model families differ on whether the thinking field is accepted. Rather than pin a
            # default that may 400 on some model, drop the field once, remember that it is
            # unsupported, and retry this single call. A rejected parameter is not a failed task.
            if "thinking_config" not in config_kwargs or "INVALID_ARGUMENT" not in str(exc):
                raise
            _STATE["thinking_supported"] = False
            config_kwargs.pop("thinking_config")
            logger.warning("thinking_config rejected by the model; retrying without it")
            response = client.models.generate_content(
                model=settings.gemini_model,
                contents=contents,
                config=types.GenerateContentConfig(**config_kwargs),
            )
        sanitized = gemini_response_schema(response_schema)
        if sanitized is not None:
            config.response_schema = sanitized
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=contents,
            config=config,
        )
    except Exception as exc:
        message = str(exc)
        lowered = message.lower()
        if "quota" in lowered or "429" in lowered or "resource_exhausted" in lowered:
            raise LLMUnavailable("quota_exceeded", message[:300]) from exc
        if "timeout" in lowered or "deadline" in lowered:
            raise LLMUnavailable("timeout", message[:300]) from exc
        if "api key" in lowered or "permission" in lowered or "401" in lowered or "403" in lowered:
            raise LLMUnavailable("invalid_api_key", message[:300]) from exc
        raise LLMUnavailable("request_failed", f"{type(exc).__name__}: {message[:300]}") from exc

    latency_ms = int((time.perf_counter() - started) * 1000)
    text = getattr(response, "text", None)
    if not text:
        raise LLMUnavailable(
            "empty_response",
            "The model returned no text (it may have been blocked by a safety filter).",
        )

    cleaned = _strip_fences(text)
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        # The head of the response is included because "invalid JSON" alone is undebuggable and
        # this text contains generated prose, never credentials.
        raise LLMUnavailable(
            "invalid_json",
            f"The model did not return valid JSON: {exc}. Head={cleaned[:240]!r}",
        ) from exc
    if not isinstance(payload, dict):
        raise LLMUnavailable("invalid_json", "The model returned JSON that is not an object.")

    return LLMResult(text=cleaned, model=settings.gemini_model, latency_ms=latency_ms, raw=payload)


#: Keywords Pydantic emits that Gemini's `response_schema` rejects outright.
_UNSUPPORTED_SCHEMA_KEYS = {
    "additionalProperties",
    "title",
    "$schema",
    "default",
    "examples",
    "discriminator",
    "format",
}
_ALLOWED_FORMATS = {"int32", "int64", "float", "double"}


def gemini_response_schema(schema: Any) -> dict[str, Any] | None:
    """Convert a Pydantic model (or plain schema) into something Gemini accepts.

    Gemini rejects `additionalProperties`, `title`, `format` and friends with a 400. Passing the
    raw `model_json_schema()` therefore failed on the first live call, even though the schema was
    valid JSON Schema. This flattens `$ref`/`$defs` and removes the unsupported keywords.
    """
    if schema is None:
        return None
    if isinstance(schema, dict):
        raw = schema
    elif hasattr(schema, "model_json_schema"):
        raw = schema.model_json_schema()
    else:
        return None

    defs = raw.get("$defs", {})

    def walk(node: Any, depth: int = 0) -> Any:
        if depth > 12:
            return {}
        if isinstance(node, list):
            return [walk(item, depth + 1) for item in node]
        if not isinstance(node, dict):
            return node

        if "$ref" in node:
            target = defs.get(str(node["$ref"]).split("/")[-1], {})
            merged = walk(target, depth + 1)
            for key, value in node.items():
                if key != "$ref" and key not in _UNSUPPORTED_SCHEMA_KEYS:
                    merged[key] = walk(value, depth + 1)
            return merged

        out: dict[str, Any] = {}
        for key, value in node.items():
            if key in _UNSUPPORTED_SCHEMA_KEYS:
                if key == "format" and value in _ALLOWED_FORMATS:
                    out[key] = value
                continue
            if key == "$defs":
                continue
            out[key] = walk(value, depth + 1)

        if "anyOf" in out:
            options = [
                option
                for option in out["anyOf"]
                if not (isinstance(option, dict) and option.get("type") == "null")
            ]
            if len(options) == 1:
                rest = {k: v for k, v in out.items() if k != "anyOf"}
                merged = dict(options[0])
                merged.update(rest)
                merged["nullable"] = True
                out = merged
        return out

    sanitized = walk(raw)
    return sanitized if isinstance(sanitized, dict) else None


def _strip_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[1] if "\n" in stripped else stripped
        if stripped.endswith("```"):
            stripped = stripped[:-3]
    return stripped.strip()
