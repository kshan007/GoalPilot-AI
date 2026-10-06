"""
GoalPilot Single-Goal Optimization Adapter.
Directly implements the mathematical formulation from GoalPilot AI Step 5T.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
import numpy as np
import pandas as pd
from scipy.optimize import linprog

from ..schemas.financial_profile import FinancialProfileSchema
from ..schemas.goal import SingleGoalSchema
from ..schemas.optimization_response import (
    OptimizationStatusEnum,
    MonthlyAllocationItem,
    OptimizationResultMetrics,
    ModelExplanation,
    OptimizationResponse
)
from .simulation_adapter import simulation_adapter
from ..utils.logger import logger

class DecisionEngineInterface(ABC):
    """
    Abstract interface for GoalPilot decision engines.
    Ensures modularity for future multi-goal or RL extensions.
    """
    @abstractmethod
    def optimize(
        self,
        profile: FinancialProfileSchema,
        goal: SingleGoalSchema,
        user_id: Optional[str] = None
    ) -> OptimizationResponse:
        pass

class SingleGoalOptimizationAdapter(DecisionEngineInterface):
    """
    Adapter executing the exact Step 5T Linear Program from GoalPilot AI.
    Objective: minimize D
    Subject to:
        sum(G_t) + D = Target
        0 <= G_t <= P_t
        D >= 0
    """

    def __init__(self):
        self.sim_adapter = simulation_adapter

    def optimize(
        self,
        profile: FinancialProfileSchema,
        goal: SingleGoalSchema,
        user_id: Optional[str] = None
    ) -> OptimizationResponse:
        horizon = goal.goal_horizon_months
        target = float(goal.target_amount)
        uid = user_id or "USER_CUSTOM"

        # 1. Run dynamic longitudinal simulation to get monthly cash flow P_t
        sim_records, P = self.sim_adapter.simulate_monthly_cash_flows(
            profile=profile,
            goal=goal,
            user_id=uid
        )

        total_pos_cash = float(np.sum(P))
        expected_funding = min(target, total_pos_cash)
        expected_shortfall = max(target - total_pos_cash, 0.0)

        # 2. Check for severe deficit / zero cash-flow condition
        if total_pos_cash <= 0.0:
            logger.warning(f"User {uid} has zero total positive cash flow across horizon {horizon} months.")
            # Construct deficit response
            monthly_items = []
            for r in sim_records:
                monthly_items.append(MonthlyAllocationItem(
                    month_index=r["month_index"],
                    period=r["period"],
                    inflation_factor=r["inflation_factor"],
                    income_dynamic=r["income_dynamic"],
                    expenditure_dynamic=r["expenditure_dynamic"],
                    monthly_surplus_dynamic=r["monthly_surplus_dynamic"],
                    positive_cash_flow=0.0,
                    optimized_goal_funding=0.0,
                    residual_cash=0.0,
                    cumulative_goal_funding=0.0
                ))

            metrics = OptimizationResultMetrics(
                solver_method="highs",
                solver_status="deficit_infeasible_zero_capacity",
                target_amount=target,
                goal_horizon_months=horizon,
                total_positive_cash_flow=0.0,
                optimized_goal_funding=0.0,
                optimized_shortfall=target,
                funding_percentage=0.0,
                is_goal_achieved=False,
                objective_value_shortfall=target,
                analytical_optimal_funding=0.0,
                optimality_error=0.0,
                target_accounting_error=0.0,
                mean_monthly_goal_funding=0.0,
                mean_monthly_residual_cash=0.0
            )

            warnings = [
                "Monthly expenditures and EMI obligations equal or exceed dynamic household income.",
                "Available cash surplus for goal funding is currently ₹0.",
                "Consider reducing non-essential expenses or extending the goal horizon."
            ]

            explanation = self._build_explanation(
                profile=profile,
                goal=goal,
                metrics=metrics,
                status=OptimizationStatusEnum.DEFICIT_INFEASIBLE
            )

            return OptimizationResponse(
                status=OptimizationStatusEnum.DEFICIT_INFEASIBLE,
                message="Goal cannot be funded due to lack of positive monthly cash surplus.",
                user_id=uid,
                is_benchmark_case=(uid.startswith("USER_") and uid != "USER_CUSTOM"),
                financial_summary=self._derive_financial_summary(profile),
                goal_summary=self._derive_goal_summary(goal, profile),
                metrics=metrics,
                monthly_schedule=monthly_items,
                explanation=explanation,
                warnings=warnings,
                assumptions=self._get_model_assumptions()
            )

        # 3. Formulate and solve the LP (Scipy HiGHS Solver per Step 5T)
        # Decision vector: [G_1, G_2, ..., G_H, D]
        c = np.zeros(horizon + 1)
        c[-1] = 1.0  # minimize D

        bounds = [(0.0, float(p)) for p in P]
        bounds.append((0.0, None))  # D >= 0

        A_eq = np.zeros((1, horizon + 1))
        A_eq[0, :horizon] = 1.0
        A_eq[0, horizon] = 1.0
        b_eq = np.array([target])

        # Highs solver call
        solution = linprog(
            c=c,
            A_eq=A_eq,
            b_eq=b_eq,
            bounds=bounds,
            method="highs"
        )

        if not solution.success:
            logger.error(f"Highs LP solver returned failure status: {solution.message}")
            raise RuntimeError(f"LP optimization failed: {solution.message}")

        # 4. Extract solution variables
        G = solution.x[:horizon]
        D = float(solution.x[-1])
        optimized_funding = float(np.sum(G))

        # Precision adjustments
        if abs(D) < 1e-6:
            D = 0.0
        if abs(optimized_funding - target) < 1e-6:
            optimized_funding = target

        funding_percentage = min(100.0, (optimized_funding / target) * 100.0) if target > 0 else 0.0
        is_achieved = bool(optimized_funding >= target - 1e-6)

        target_error = float(optimized_funding + D - target)
        optimality_error = float(abs(optimized_funding - expected_funding))

        # 5. Build monthly schedule
        monthly_items: List[MonthlyAllocationItem] = []
        cum_funding = 0.0
        residual_cash_list = []

        for t in range(horizon):
            g_t = float(G[t])
            cum_funding += g_t
            p_t = float(P[t])
            r_t = max(0.0, p_t - g_t)
            residual_cash_list.append(r_t)

            sim_rec = sim_records[t]
            monthly_items.append(MonthlyAllocationItem(
                month_index=t + 1,
                period=sim_rec["period"],
                inflation_factor=sim_rec["inflation_factor"],
                income_dynamic=sim_rec["income_dynamic"],
                expenditure_dynamic=sim_rec["expenditure_dynamic"],
                monthly_surplus_dynamic=sim_rec["monthly_surplus_dynamic"],
                positive_cash_flow=p_t,
                optimized_goal_funding=round(g_t, 2),
                residual_cash=round(r_t, 2),
                cumulative_goal_funding=round(cum_funding, 2)
            ))

        mean_monthly_funding = float(np.mean(G)) if horizon > 0 else 0.0
        mean_monthly_residual = float(np.mean(residual_cash_list)) if horizon > 0 else 0.0

        metrics = OptimizationResultMetrics(
            solver_method="highs",
            solver_status=str(solution.message),
            target_amount=round(target, 2),
            goal_horizon_months=horizon,
            total_positive_cash_flow=round(total_pos_cash, 2),
            optimized_goal_funding=round(optimized_funding, 2),
            optimized_shortfall=round(D, 2),
            funding_percentage=round(funding_percentage, 2),
            is_goal_achieved=is_achieved,
            objective_value_shortfall=round(D, 2),
            analytical_optimal_funding=round(expected_funding, 2),
            optimality_error=round(optimality_error, 8),
            target_accounting_error=round(target_error, 8),
            mean_monthly_goal_funding=round(mean_monthly_funding, 2),
            mean_monthly_residual_cash=round(mean_monthly_residual, 2)
        )

        # 6. Status & Warnings
        warnings = []
        if is_achieved:
            status = OptimizationStatusEnum.OPTIMAL_SUCCESS
            status_msg = f"Optimal plan determined: 100% of the ₹{target:,.0f} goal can be successfully funded."
        else:
            status = OptimizationStatusEnum.OPTIMAL_SHORTFALL
            status_msg = f"Optimal plan determined: ₹{optimized_funding:,.0f} ({funding_percentage:.1f}%) funded with ₹{D:,.0f} projected shortfall."
            warnings.append(f"Cumulative available surplus across {horizon} months (₹{total_pos_cash:,.0f}) is lower than the target (₹{target:,.0f}).")
            warnings.append("To bridge the shortfall, consider increasing monthly income, curtailing discretionary spend, or extending the goal deadline.")

        if profile.monthly_emi > 0 and (profile.monthly_emi / profile.monthly_income) > 0.40:
            warnings.append(f"Debt-to-income ratio is high ({(profile.monthly_emi/profile.monthly_income)*100:.1f}%). EMI payments limit monthly goal capacity.")

        explanation = self._build_explanation(
            profile=profile,
            goal=goal,
            metrics=metrics,
            status=status
        )

        return OptimizationResponse(
            status=status,
            message=status_msg,
            user_id=uid,
            is_benchmark_case=(uid.startswith("USER_") and uid != "USER_CUSTOM"),
            financial_summary=self._derive_financial_summary(profile),
            goal_summary=self._derive_goal_summary(goal, profile),
            metrics=metrics,
            monthly_schedule=monthly_items,
            explanation=explanation,
            warnings=warnings,
            assumptions=self._get_model_assumptions()
        )

    def _derive_financial_summary(self, profile: FinancialProfileSchema):
        from ..schemas.financial_profile import DerivedFinancialSummary, FinancialSituationEnum
        annual_inc = profile.monthly_income * 12.0
        annual_exp = profile.monthly_expenditure * 12.0
        baseline_surplus = profile.monthly_income - profile.monthly_expenditure - profile.monthly_emi
        sav_ratio = profile.initial_savings / annual_inc if annual_inc > 0 else 0.0
        debt_ratio = profile.monthly_emi / profile.monthly_income if profile.monthly_income > 0 else 0.0

        # Classify financial situation matching GoalPilot AI synthetic demographics
        if baseline_surplus < 0 or (sav_ratio < 0.1 and debt_ratio > 0.4):
            situation = FinancialSituationEnum.FINANCIAL_STRESS
        elif baseline_surplus < profile.monthly_income * 0.15:
            situation = FinancialSituationEnum.VULNERABLE
        elif sav_ratio > 0.5 and baseline_surplus > profile.monthly_income * 0.35:
            situation = FinancialSituationEnum.AFFLUENT
        else:
            situation = FinancialSituationEnum.MODERATE_SAVING

        rec_emergency = profile.monthly_expenditure * 6.0
        cov_months = (profile.initial_savings / profile.monthly_expenditure) if profile.monthly_expenditure > 0 else 0.0

        return DerivedFinancialSummary(
            baseline_monthly_surplus=round(baseline_surplus, 2),
            is_surplus_positive=bool(baseline_surplus > 0),
            annual_income=round(annual_inc, 2),
            annual_expenditure=round(annual_exp, 2),
            savings_to_income_ratio=round(sav_ratio, 4),
            debt_service_ratio=round(debt_ratio, 4),
            financial_situation=situation,
            recommended_emergency_fund_target=round(rec_emergency, 2),
            emergency_fund_coverage_months=round(cov_months, 1)
        )

    def _derive_goal_summary(self, goal: SingleGoalSchema, profile: FinancialProfileSchema):
        from ..schemas.goal import GoalDerivedSummary, GoalHorizonTypeEnum
        h = goal.goal_horizon_months
        if h <= 24:
            h_type = GoalHorizonTypeEnum.SHORT_TERM
        elif h <= 60:
            h_type = GoalHorizonTypeEnum.MEDIUM_TERM
        else:
            h_type = GoalHorizonTypeEnum.LONG_TERM

        annual_inc = profile.monthly_income * 12.0
        t_to_inc = goal.target_amount / annual_inc if annual_inc > 0 else 0.0
        t_to_sav = (goal.target_amount / profile.initial_savings) if profile.initial_savings > 0 else 0.0
        req_flat = goal.target_amount / h if h > 0 else goal.target_amount

        return GoalDerivedSummary(
            goal_name=goal.goal_name,
            target_amount=round(goal.target_amount, 2),
            goal_horizon_months=h,
            goal_horizon_type=h_type,
            target_to_annual_income_ratio=round(t_to_inc, 4),
            target_to_savings_ratio=round(t_to_sav, 4),
            required_monthly_savings_flat=round(req_flat, 2)
        )

    def _build_explanation(
        self,
        profile: FinancialProfileSchema,
        goal: SingleGoalSchema,
        metrics: OptimizationResultMetrics,
        status: OptimizationStatusEnum
    ) -> ModelExplanation:
        if status == OptimizationStatusEnum.OPTIMAL_SUCCESS:
            summary = (
                f"GoalPilot's Linear Programming solver established that your dynamic monthly surplus capacity "
                f"(totaling ₹{metrics.total_positive_cash_flow:,.0f} over {metrics.goal_horizon_months} months) "
                f"fully covers the ₹{metrics.target_amount:,.0f} goal requirement."
            )
        elif status == OptimizationStatusEnum.OPTIMAL_SHORTFALL:
            summary = (
                f"GoalPilot allocated 100% of available positive monthly surplus (₹{metrics.total_positive_cash_flow:,.0f}) "
                f"towards your goal, fulfilling ₹{metrics.optimized_goal_funding:,.0f} ({metrics.funding_percentage:.1f}%). "
                f"An unavoidable shortfall of ₹{metrics.optimized_shortfall:,.0f} remains under current cash constraints."
            )
        else:
            summary = (
                "GoalPilot detected that current living expenses and fixed loan commitments absorb all monthly income, "
                "yielding ₹0 available positive cash flow for goal accumulation."
            )

        key_drivers = [
            f"Gross monthly income: ₹{profile.monthly_income:,.0f} adjusted dynamically for CPI inflation.",
            f"Living expenditure commitments: ₹{profile.monthly_expenditure:,.0f}/mo expanding with inflation.",
            f"Fixed debt obligations (EMI): ₹{profile.monthly_emi:,.0f}/mo prioritized before surplus calculation.",
            f"Cumulative positive surplus over {goal.goal_horizon_months} months: ₹{metrics.total_positive_cash_flow:,.0f}.",
            f"Single-goal target: ₹{goal.target_amount:,.0f} across {goal.goal_horizon_months} months."
        ]

        constraints_active = [
            "Monthly Non-Negative Cash Flow Upper Bound: 0 <= G_t <= PositiveCashFlow_t",
            "Target Accounting Conservation: Sum(G_t) + D = TargetAmount",
            "Shortfall Non-Negativity: D >= 0",
            "No unbacked debt financing permitted for goal funding."
        ]

        sim_role = (
            "GoalPilot's simulation layer computes inflation-adjusted income and expenditure trajectories across your "
            f"{goal.goal_horizon_months}-month horizon using calibrated Indian CPI empirical data. The resulting dynamic cash flow "
            "serves as the strict feasibility boundary for the LP optimizer."
        )

        nism_notes = [
            "NISM Guidance: A healthy financial foundation requires establishing an emergency fund of 3 to 6 months of essential expenses before locking surplus into long-term capital goals.",
            "Surplus Rule: Investable surplus is rigorously defined as Net Income minus Non-discretionary Living Costs minus Debt EMIs.",
            "Horizon Matching: Goals under 24 months should prioritize capital preservation over speculative equity market volatility."
        ]

        future_notice = (
            "CURRENT VERSION: Single-goal linear programming optimization based on empirical cash-flow constraints. "
            "FUTURE VERSION: Multiple goal prioritization, cross-goal trade-offs, and Reinforcement Learning (RL) sequential policies."
        )

        return ModelExplanation(
            title="GoalPilot Optimization Analysis",
            summary=summary,
            key_drivers=key_drivers,
            constraints_active=constraints_active,
            simulation_role=sim_role,
            nism_guidance_notes=nism_notes,
            future_capabilities_notice=future_notice
        )

    def _get_model_assumptions(self) -> List[str]:
        return [
            "Single Financial Goal: Optimization is formulated for one explicit financial target over a fixed discrete monthly horizon.",
            "Cash Flow Bounded: Monthly goal allocations are strictly bounded by available post-expense, post-EMI surplus.",
            "Inflation Co-Movement: Income and expenditures evolve according to empirical CPI inflation calibration series.",
            "No Synthetic Debt Levering: Discretionary goal funding cannot be financed by taking on synthetic high-interest loans.",
            "Highs Simplex/Interior LP Solver: Optimization is mathematically guaranteed to find the global minimum shortfall."
        ]

optimization_adapter = SingleGoalOptimizationAdapter()
