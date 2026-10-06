"""
GoalPilot Application - FastAPI Backend Server
Exposes the single-goal financial optimization and simulation pipeline.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

from .config import settings
from .api.health import router as health_router
from .api.optimization import router as optimization_router
from .api.benchmark import router as benchmark_router
from .utils.logger import logger

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 60)
    logger.info("  GOALPILOT APPLICATION API - BACKEND INITIALIZED")
    logger.info("  Single-Goal Optimization Engine: ACTIVE")
    logger.info(f"  GoalPilot_AI Research Path: {settings.get_goalpilot_ai_dir()}")
    logger.info("=" * 60)
    yield
    logger.info("GoalPilot Application Backend Shutting Down.")

app = FastAPI(
    title="GoalPilot Application API",
    description="Backend service exposing the GoalPilot AI Single-Goal Optimization and Longitudinal Simulation framework.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configure CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS if settings.CORS_ORIGINS else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routers
app.include_router(health_router)
app.include_router(optimization_router)
app.include_router(benchmark_router)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global error handler caught: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "An internal server error occurred while processing your financial optimization request.",
            "error_type": type(exc).__name__
        }
    )

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG
    )
