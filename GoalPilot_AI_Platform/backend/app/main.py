"""GoalPilot AI Platform — FastAPI application.

Run locally:

    uvicorn app.main:app --reload --port 8000

OpenAPI is served at /docs and /redoc.
"""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.responses import JSONResponse

from app.api import (
    admin,
    auth,
    dashboard,
    goals,
    investments,
    loans,
    meta,
    monthly,
    optimization,
    profile,
    recommendations,
    scenarios,
)
from app.config import get_settings
from app.core.errors import register_error_handlers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
# Model-serving libraries are chatty; the application's own logs stay readable.
for noisy in ("tensorflow", "absl", "matplotlib", "urllib3", "asyncio", "h5py"):
    logging.getLogger(noisy).setLevel(logging.ERROR)

logger = logging.getLogger("goalpilot")

settings = get_settings()

DESCRIPTION = """
Individual personal financial planning and research decision-support.

**Multi-goal optimisation** over the capacity-constrained LP, a trained PPO policy and a
genuine RL-then-LP hybrid; **adaptive expense forecasting** with walk-forward backtesting;
**monthly estimated-vs-actual reconciliation**; and **scenario simulation**.

Not financial advice. No model here guarantees an outcome, and no trades, transfers or loans
are ever executed.
"""

app = FastAPI(
    title=settings.app_name,
    version=settings.api_version,
    description=DESCRIPTION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

register_error_handlers(app)

API_PREFIX = "/api"

@app.middleware("http")
async def catch_unhandled_errors(request: Request, call_next):
    """Return a JSON error the browser can actually read.

    ``CORSMiddleware`` is registered *inside* Starlette's ``ServerErrorMiddleware``, so an
    exception that escapes the router never passes through it: the browser sees
    ``net::ERR_FAILED`` and the UI reports a network outage for what is really a server fault.
    This middleware sits outside CORS and therefore adds the CORS headers itself.
    """
    try:
        return await call_next(request)
    except Exception as exc:  # noqa: BLE001 - last line of defence
        logging.getLogger("goalpilot.api").exception(
            "unhandled_error path=%s", request.url.path
        )
        from app.config import get_settings

        origin = request.headers.get("origin")
        allowed = get_settings().cors_origins
        headers = {"Vary": "Origin"}
        if origin and (origin in allowed or "*" in allowed):
            headers["Access-Control-Allow-Origin"] = origin
            headers["Access-Control-Allow-Credentials"] = "true"
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": (
                        "An unexpected server error occurred. The request was not applied and "
                        "no data was changed."
                    ),
                    "detail": type(exc).__name__,
                }
            },
            headers=headers,
        )


for router_module in (
    auth,
    profile,
    goals,
    monthly,
    optimization,
    investments,
    loans,
    recommendations,
    scenarios,
    dashboard,
    meta,
    admin,
):
    app.include_router(router_module.router, prefix=API_PREFIX)


@app.on_event("startup")
def _startup() -> None:
    # Alembic is the supported migration path. On SQLite (the test/zero-setup path) there is
    # no migration state to protect, so the schema is created directly.
    url = settings.database_url
    if url.startswith("sqlite"):
        from app.db import create_all

        try:
            create_all()
            logger.info("SQLite schema ensured")
        except Exception as exc:  # pragma: no cover
            logger.error("Could not create the SQLite schema: %s", exc)
    logger.info("GoalPilot AI Platform %s started (%s)", settings.api_version, settings.environment)
    if settings.research_available:
        logger.info("Research project located at %s", settings.research_path)
    else:
        logger.warning(
            "Research project not located. The LP/RL arms will report 'unavailable' rather "
            "than fabricate results. Set GOALPILOT_RESEARCH_PATH to fix this."
        )


@app.get("/", include_in_schema=False)
def root():
    return {
        "name": settings.app_name,
        "version": settings.api_version,
        "docs": "/docs",
        "openapi": "/openapi.json",
        "api_prefix": API_PREFIX,
    }


if os.getenv("GOALPILOT_SERVE_FRONTEND", "false").strip().lower() in {"1", "true", "yes", "on"}:
    # Optional single-origin deployment: serve the built frontend from the same process.
    from pathlib import Path

    from fastapi.staticfiles import StaticFiles

    dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if dist.is_dir():
        app.mount("/app", StaticFiles(directory=str(dist), html=True), name="frontend")

