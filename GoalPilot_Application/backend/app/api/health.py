from fastapi import APIRouter
from datetime import datetime, timezone
from ..config import settings
from ..integration.data_loader import data_loader

router = APIRouter(prefix="/api", tags=["Health"])

@router.get("/health")
def health_check():
    """Health check endpoint confirming API and GoalPilot_AI data connectivity."""
    ai_dir = settings.get_goalpilot_ai_dir()
    ai_connected = ai_dir.exists()
    cpi_df = data_loader.get_cpi_calibration()
    benchmark_df = data_loader.get_benchmark_master_lp_dataset()

    return {
        "status": "healthy",
        "app_name": "GoalPilot Application",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "goalpilot_ai_source": {
            "path": str(ai_dir),
            "directory_exists": ai_connected,
            "cpi_calibration_loaded": cpi_df is not None and len(cpi_df) > 0,
            "benchmark_dataset_loaded": benchmark_df is not None and len(benchmark_df) > 0
        },
        "supported_features": {
            "single_goal_optimization": True,
            "multi_goal_optimization": False,
            "reinforcement_learning": False,
            "solver": "scipy.optimize.linprog(highs)"
        }
    }
