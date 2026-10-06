from .health import router as health_router
from .optimization import router as optimization_router
from .benchmark import router as benchmark_router

__all__ = ["health_router", "optimization_router", "benchmark_router"]
