"""
Data loader for GoalPilot_AI research datasets and calibration files.
Accesses GoalPilot_AI as a read-only source of truth.
"""

import os
from pathlib import Path
from typing import Optional, Dict, Any, List
import pandas as pd
import numpy as np

from ..config import settings
from ..utils.logger import logger

class DataLoader:
    """Read-only loader for GoalPilot_AI data and calibrated models."""

    def __init__(self, base_path: Optional[Path] = None):
        self.base_path = base_path or settings.get_goalpilot_ai_dir()
        self._cpi_calibration: Optional[pd.DataFrame] = None
        self._economic_environment: Optional[pd.DataFrame] = None
        self._benchmark_lp_dataset: Optional[pd.DataFrame] = None
        self._benchmark_monthly_simulation: Optional[pd.DataFrame] = None
        logger.info(f"DataLoader initialized with base path: {self.base_path}")

    def get_cpi_calibration(self) -> pd.DataFrame:
        """Loads historical CPI calibration table."""
        if self._cpi_calibration is None:
            paths = [
                self.base_path / "simulation" / "01_input_data" / "cpi_historical_calibration.csv",
                self.base_path.parent / "datasets" / "GoalPilot_AI" / "final_simulation_inputs" / "cpi_historical_calibration.csv",
            ]
            for p in paths:
                if p.exists():
                    logger.info(f"Loading CPI calibration from: {p}")
                    self._cpi_calibration = pd.read_csv(p)
                    break

            if self._cpi_calibration is None:
                logger.warning("CPI calibration file not found. Generating default empirical inflation schedule.")
                # Construct standard 144-month CPI table if file missing
                dates = pd.date_range(start="2015-01-01", periods=144, freq="MS")
                df = pd.DataFrame({
                    "period": dates.strftime("%Y-%m-%d"),
                    "monthly_inflation_rate": 0.004,
                    "cumulative_inflation_factor": np.cumprod(np.repeat(1.004, 144))
                })
                self._cpi_calibration = df

        return self._cpi_calibration

    def get_economic_environment(self) -> pd.DataFrame:
        """Loads economic environment containing inflation and market series."""
        if self._economic_environment is None:
            p = self.base_path / "simulation" / "04_economic_environment" / "economic_environment.csv"
            if p.exists():
                logger.info(f"Loading economic environment from: {p}")
                self._economic_environment = pd.read_csv(p)
            else:
                logger.warning(f"Economic environment not found at {p}")
                self._economic_environment = pd.DataFrame()
        return self._economic_environment

    def get_benchmark_master_lp_dataset(self) -> Optional[pd.DataFrame]:
        """Loads the final consolidated 10,000-user LP dataset from Step 5X."""
        if self._benchmark_lp_dataset is None:
            p = self.base_path / "optimization" / "final_outputs" / "GoalPilot_AI_final_LP_optimization_dataset.csv"
            if p.exists():
                logger.info(f"Loading benchmark LP dataset from: {p}")
                self._benchmark_lp_dataset = pd.read_csv(p)
            else:
                logger.warning(f"Benchmark LP dataset not found at {p}")
        return self._benchmark_lp_dataset

    def get_benchmark_user_record(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves user baseline record from benchmark dataset."""
        df = self.get_benchmark_master_lp_dataset()
        if df is not None and "user_id" in df.columns:
            match = df[df["user_id"] == user_id]
            if len(match) > 0:
                return match.iloc[0].to_dict()
        return None

    def get_benchmark_user_list(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Returns a list of synthetic users for demo / benchmark testing."""
        df = self.get_benchmark_master_lp_dataset()
        if df is not None and not df.empty:
            cols = [
                "user_id", "monthly_income", "monthly_expenditure", "monthly_emi",
                "initial_savings", "financial_situation", "risk_profile",
                "goal_horizon_months", "target_amount", "optimized_goal_funding",
                "optimized_shortfall", "optimized_success"
            ]
            avail_cols = [c for c in cols if c in df.columns]
            sample = df[avail_cols].head(limit)
            return sample.to_dict(orient="records")
        return []

# Singleton instance
data_loader = DataLoader()
