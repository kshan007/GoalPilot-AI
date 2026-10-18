"""Runtime configuration.

Every value is environment-driven so the same code runs locally, in tests and in a deployment.
No secret is ever hard-coded. See ``.env.example`` for the documented set.
"""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

# --------------------------------------------------------------------------------------
# .env loading
# --------------------------------------------------------------------------------------
# The application previously read only the process environment, so a correctly filled
# `backend/.env` was silently ignored and the LLM path looked unconfigured. Load it here, once,
# without overriding variables that the process (or a container) already set — deployment
# environment must win over the file. Tests set GOALPILOT_SKIP_DOTENV=1 so the suite stays
# hermetic and cannot pick up a developer's real key.
if not os.getenv("GOALPILOT_SKIP_DOTENV"):
    try:
        from dotenv import load_dotenv

        _here = Path(__file__).resolve().parent          # backend/app
        for _candidate in (_here.parent / ".env", _here.parent.parent / ".env"):
            if _candidate.is_file():
                load_dotenv(_candidate, override=False)
    except ImportError:  # python-dotenv is optional; the environment still works
        pass


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


def _resolve_research_path() -> Path | None:
    """Locate the read-only research project.

    Order: ``GOALPILOT_RESEARCH_PATH`` -> walk up from this file looking for
    ``GoalPilot_AI_Completed`` -> sibling of the platform root.
    """
    explicit = os.getenv("GOALPILOT_RESEARCH_PATH")
    if explicit:
        p = Path(explicit)
        return p if p.exists() else None

    candidates: list[Path] = []
    here = Path(__file__).resolve()
    for parent in list(here.parents)[:8]:
        candidates.append(parent / "GoalPilot_AI_Completed")
        candidates.append(parent.parent / "GoalPilot_AI_Completed")
    for c in candidates:
        if c.is_dir():
            return c
    return None


@dataclass
class Settings:
    # --- identity -------------------------------------------------------------------
    app_name: str = "GoalPilot AI Platform"
    api_version: str = "1.0.0"
    environment: str = field(default_factory=lambda: os.getenv("GOALPILOT_ENV", "development"))

    # --- database -------------------------------------------------------------------
    # PostgreSQL 17 is the intended production target. The driver is psycopg2 because
    # `psycopg[binary]` is not importable on the development host (no libpq available);
    # switch the prefix to `postgresql+psycopg://` only after installing psycopg[binary].
    #
    # Set DATABASE_URL to `sqlite:///./goalpilot.db` for a zero-setup local run or tests.
    database_url: str = field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL",
            # SQLite is the supported target: a fresh clone runs with no database server, no
            # credentials and no setup step. Defaulting to PostgreSQL previously meant a clean
            # checkout started "healthy" and then returned 500 on every data endpoint.
            "sqlite:///./goalpilot.db",
        )
    )

    # --- auth -----------------------------------------------------------------------
    secret_key: str = field(default_factory=lambda: os.getenv("SECRET_KEY", ""))
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = field(
        default_factory=lambda: _env_int("ACCESS_TOKEN_TTL_MINUTES", 60 * 12)
    )
    reset_token_ttl_minutes: int = field(
        default_factory=lambda: _env_int("RESET_TOKEN_TTL_MINUTES", 30)
    )
    # Dev convenience only: when true the reset token is returned in the API response. It
    # defaults to off in production: returning a live reset token to an unauthenticated caller
    # would let anyone who knows an email address take over the account.
    expose_reset_token: bool = field(
        default_factory=lambda: _env_bool(
            "EXPOSE_RESET_TOKEN",
            os.getenv("GOALPILOT_ENV", "development").strip().lower() != "production",
        )
    )
    bcrypt_rounds: int = field(default_factory=lambda: _env_int("BCRYPT_ROUNDS", 12))

    # --- transport ------------------------------------------------------------------
    cors_origins: list[str] = field(
        default_factory=lambda: _env_list(
            "CORS_ORIGINS", ["http://localhost:5173", "http://127.0.0.1:5173"]
        )
    )
    rate_limit_auth_per_minute: int = field(
        default_factory=lambda: _env_int("RATE_LIMIT_AUTH_PER_MINUTE", 30)
    )
    rate_limit_optimize_per_minute: int = field(
        default_factory=lambda: _env_int("RATE_LIMIT_OPTIMIZE_PER_MINUTE", 30)
    )

    # --- research / models ----------------------------------------------------------
    research_path: Path | None = field(default_factory=_resolve_research_path)
    # The checkpoint the RL arm uses. Any checkpoint in the registry can be selected
    # explicitly; this is the default.
    default_rl_checkpoint: str = field(
        default_factory=lambda: os.getenv(
            "GOALPILOT_RL_CHECKPOINT",
            "training_logs/experiments/ppo_recommended_v1/archived_v1/seed7/best/best_model.zip",
        )
    )
    enable_rl: bool = field(default_factory=lambda: _env_bool("GOALPILOT_ENABLE_RL", True))

    # --- financial assumption defaults (assumptions, NOT facts) ----------------------
    default_annual_inflation: float = 0.03
    default_investment_return: float = 0.05
    default_savings_return: float = 0.0
    default_loan_annual_rate: float = 0.12
    default_loan_tenure_months: int = 60
    default_emergency_months: float = 6.0
    default_emi_income_ratio_cap: float = 0.35

    # --- behaviour ------------------------------------------------------------------
    forecast_min_history_months: int = field(
        default_factory=lambda: _env_int("FORECAST_MIN_HISTORY_MONTHS", 3)
    )
    max_comparison_users: int = 16

    # --- external data providers ------------------------------------------------------
    #: Live HTTP retrieval of public product/NAV pages. Off makes every provider serve its
    #: bundled, source-annotated snapshot instead — the app still works, fully labelled.
    enable_live_providers: bool = field(
        default_factory=lambda: _env_bool("GOALPILOT_ENABLE_LIVE_PROVIDERS", True)
    )
    provider_http_timeout_seconds: float = field(
        default_factory=lambda: _env_int("PROVIDER_HTTP_TIMEOUT_SECONDS", 12)
    )
    provider_cache_ttl_seconds: int = field(
        default_factory=lambda: _env_int("PROVIDER_CACHE_TTL_SECONDS", 6 * 3600)
    )
    #: AMFI's scheme-count is ~2000; a shortlist keeps the discovery payload usable.
    investment_shortlist_per_category: int = field(
        default_factory=lambda: _env_int("INVESTMENT_SHORTLIST_PER_CATEGORY", 2)
    )
    #: The optional free NAV-history mirror (api.mfapi.in). It is NOT an AMFI service.
    enable_mfapi_history: bool = field(
        default_factory=lambda: _env_bool("GOALPILOT_ENABLE_MFAPI_HISTORY", True)
    )
    #: Rate used for a loan-category scenario when no published product exists for that
    #: category. It is an explicit, configurable assumption — never presented as a lender rate.
    #: Overridable per request; falls back to the user's own loan interest assumption first.
    default_loan_scenario_rate: float = field(
        default_factory=lambda: _env_float("GOALPILOT_SCENARIO_LOAN_RATE", 0.12)
    )

    # --- LLM (Gemini only) ------------------------------------------------------------
    #: Read from the environment. Never logged, never returned to the client, never committed.
    gemini_api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    gemini_model: str = field(
        default_factory=lambda: os.getenv("GOALPILOT_GEMINI_MODEL", "gemini-2.5-flash")
    )
    gemini_timeout_seconds: float = field(
        default_factory=lambda: _env_int("GOALPILOT_GEMINI_TIMEOUT_SECONDS", 45)
    )
    #: Gemini 2.5 models spend thinking tokens by default, which dominated the 20-30 s latency
    #: measured on this task. 0 disables thinking; set higher if explanation quality drops.
    gemini_thinking_budget: int = field(
        default_factory=lambda: _env_int("GOALPILOT_GEMINI_THINKING_BUDGET", 0)
    )
    gemini_max_output_tokens: int = field(
        default_factory=lambda: _env_int("GOALPILOT_GEMINI_MAX_OUTPUT_TOKENS", 3072)
    )
    llm_enabled: bool = field(default_factory=lambda: _env_bool("GOALPILOT_ENABLE_LLM", True))

    @property
    def gemini_configured(self) -> bool:
        return bool(self.gemini_api_key) and self.llm_enabled

    def __post_init__(self) -> None:
        if not self.secret_key:
            if self.environment == "production":
                raise RuntimeError(
                    "SECRET_KEY must be set in production. Refusing to start with an "
                    "ephemeral development key."
                )
            # Development/test: generate an ephemeral key so nothing is committed.
            self.secret_key = secrets.token_urlsafe(48)

        # A live password-reset token returned to an unauthenticated caller is an account
        # takeover, so production refuses to start with the demonstration flag on rather than
        # trusting a comment in the template.
        if self.environment == "production" and self.expose_reset_token:
            raise RuntimeError(
                "EXPOSE_RESET_TOKEN must be false in production: returning a reset token to an "
                "unauthenticated caller allows account takeover."
            )

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def research_available(self) -> bool:
        return self.research_path is not None and self.research_path.is_dir()

    def rl_checkpoint_path(self, relative: str | None = None) -> Path | None:
        if self.research_path is None:
            return None
        rel = relative or self.default_rl_checkpoint
        candidate = (self.research_path / rel).resolve()
        try:
            candidate.relative_to(self.research_path.resolve())
        except ValueError:
            return None  # path escape attempt
        return candidate if candidate.is_file() else None


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings_cache() -> None:
    """Used by tests that need to re-read the environment."""
    global _settings
    _settings = None
