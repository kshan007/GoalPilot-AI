"""
Simulation adapter that connects user profile inputs with the GoalPilot AI
longitudinal macroeconomic simulation framework.
"""

from typing import Dict, Any, List, Optional, Tuple
import pandas as pd
import numpy as np

from .data_loader import data_loader
from ..schemas.financial_profile import FinancialProfileSchema
from ..schemas.goal import SingleGoalSchema
from ..utils.logger import logger

class SimulationAdapter:
    """
    Adapter for generating dynamic monthly cash flows under GoalPilot AI's
    calibrated macroeconomic environment.
    """

    def __init__(self):
        self.data_loader = data_loader
        self._monthly_base_df: Optional[pd.DataFrame] = None

    def _get_benchmark_monthly_df(self) -> Optional[pd.DataFrame]:
        if self._monthly_base_df is None:
            p = self.data_loader.base_path / "simulation" / "05_simulation_runs" / "monthly_financial_simulation_base.csv"
            if p.exists():
                logger.info(f"Loading monthly benchmark simulation from {p}")
                # Load only required columns to be fast and memory efficient
                cols = [
                    "user_id", "period", "cumulative_inflation_factor",
                    "monthly_income_dynamic", "monthly_expenditure_dynamic",
                    "monthly_emi", "monthly_surplus_dynamic", "positive_cash_flow"
                ]
                self._monthly_base_df = pd.read_csv(p, usecols=lambda c: c in cols)
        return self._monthly_base_df

    def simulate_monthly_cash_flows(
        self,
        profile: FinancialProfileSchema,
        goal: SingleGoalSchema,
        user_id: Optional[str] = None
    ) -> Tuple[List[Dict[str, Any]], np.ndarray]:
        """
        Generates dynamic monthly cash flow trajectory for the goal horizon H.

        Returns:
            (monthly_records, positive_cash_flow_array)
        """
        horizon = goal.goal_horizon_months

        # If user_id is a known benchmark user and matches exactly, we can check for exact benchmark data
        if user_id and user_id.startswith("USER_") and user_id != "USER_CUSTOM":
            b_df = self._get_benchmark_monthly_df()
            if b_df is not None and "user_id" in b_df.columns:
                u_rows = b_df[b_df["user_id"] == user_id].copy()
                if len(u_rows) >= horizon:
                    logger.info(f"Using exact benchmark monthly simulation trajectory for {user_id}")
                    u_rows = u_rows.sort_values("period").head(horizon).reset_index(drop=True)
                    records = []
                    p_array = []
                    for idx, row in u_rows.iterrows():
                        rec = {
                            "month_index": int(idx + 1),
                            "period": str(row.get("period", f"Month-{idx+1}")),
                            "inflation_factor": float(row.get("cumulative_inflation_factor", 1.0)),
                            "income_dynamic": float(row.get("monthly_income_dynamic", profile.monthly_income)),
                            "expenditure_dynamic": float(row.get("monthly_expenditure_dynamic", profile.monthly_expenditure)),
                            "monthly_surplus_dynamic": float(row.get("monthly_surplus_dynamic", 0.0)),
                            "positive_cash_flow": float(row.get("positive_cash_flow", 0.0)),
                        }
                        records.append(rec)
                        p_array.append(rec["positive_cash_flow"])
                    return records, np.array(p_array, dtype=float)

        # Dynamic simulation for custom user input:
        # Load empirical CPI inflation calibration factors from GoalPilot_AI
        cpi_df = self.data_loader.get_cpi_calibration()
        
        # Extract cumulative inflation factor series
        if "cumulative_inflation_factor" in cpi_df.columns and len(cpi_df) >= horizon:
            factors = cpi_df["cumulative_inflation_factor"].iloc[:horizon].to_numpy(dtype=float)
            periods = cpi_df["period"].iloc[:horizon].astype(str).tolist() if "period" in cpi_df.columns else [f"Month-{i+1}" for i in range(horizon)]
        else:
            # Fallback empirical average annual inflation ~ 4.8% -> ~0.4% monthly
            factors = np.cumprod(np.repeat(1.004, horizon))
            periods = [f"Month-{i+1}" for i in range(horizon)]

        # Apply GoalPilot AI dynamic evolution formulas (Section 13 of simulation notebook):
        # 1. Income evolves with cumulative inflation
        # 2. Expenditure evolves with cumulative inflation
        # 3. Monthly EMI is fixed
        # 4. Surplus = Dynamic Income - Dynamic Expenditure - EMI
        # 5. PositiveCashFlow = max(0, Surplus)

        records = []
        p_array = []

        for t in range(horizon):
            inf_factor = float(factors[t])
            inc_dyn = float(profile.monthly_income * inf_factor)
            exp_dyn = float(profile.monthly_expenditure * inf_factor)
            emi_val = float(profile.monthly_emi)
            surplus_dyn = inc_dyn - exp_dyn - emi_val
            pos_cash = max(0.0, surplus_dyn)

            rec = {
                "month_index": t + 1,
                "period": periods[t] if t < len(periods) else f"Month-{t+1}",
                "inflation_factor": round(inf_factor, 6),
                "income_dynamic": round(inc_dyn, 2),
                "expenditure_dynamic": round(exp_dyn, 2),
                "monthly_surplus_dynamic": round(surplus_dyn, 2),
                "positive_cash_flow": round(pos_cash, 2),
            }
            records.append(rec)
            p_array.append(pos_cash)

        return records, np.array(p_array, dtype=float)

simulation_adapter = SimulationAdapter()
