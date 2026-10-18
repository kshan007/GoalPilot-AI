"""LP arm.

Reuses the research implementation **verbatim**:

* ``GoalPilot_MultiGoal_Extension/src/multi_goal_optimizer.py`` — ``FinancialState``,
  ``prepare_goals``, ``optimize_multi_goal``
* ``…/rl_prototype/goalpilot_constrained_lp.py`` — ``solve_constrained_lp``

The default arm is the **capacity-constrained** solver. The audit showed (finding F-04)
that the unconstrained solver's headline advantage came from planning investment the
executing environment can never accept, so it is offered only as an explicitly-labelled
research comparison and never as the recommended plan.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, asdict
from typing import Any

import pandas as pd

from app.core.errors import ValidationFailure
from app.engines import research_loader
from app.engines.common import (
    ALGORITHM_LP,
    ALGORITHM_LABELS,
    OBJECTIVE_DEFINITION,
    ArmResult,
    validate_plan,
    violation_summary,
)
from app.services.cashflow import CashFlow
from app.services.goals import goal_frame

LP_MODEL_VERSION = "constrained_lp@research-2026-10-11"
LP_UNCONSTRAINED_MODEL_VERSION = "multi_goal_lp@research-2026-10-10"


@dataclass
class LpAssumptions:
    """Every number the LP consumes. All are assumptions, never facts."""

    annual_inflation: float = 0.03
    savings_return: float = 0.0
    investment_return: float = 0.05
    investment_risk_score: float = 0.4
    loan_annual_rate: float = 0.12
    loan_tenure_months: int = 60
    max_loan_per_goal: float = 150_000.0
    max_new_loan: float = 150_000.0
    investment_capacity_ratio: float | None = None
    existing_asset_return: float = 0.0
    existing_asset_risk_score: float = 0.2
    shortfall_penalty: float = 1.0
    loan_cost_penalty: float = 0.02
    risk_penalty: float = 0.0002
    enforce_investment_capacity: bool = True
    enforce_single_loan_limit: bool = True
    allow_financing: bool = True

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_overrides(cls, overrides: dict[str, Any] | None) -> "LpAssumptions":
        base = cls()
        if not overrides:
            return base
        allowed = set(base.as_dict())
        unknown = sorted(set(overrides) - allowed)
        if unknown:
            raise ValidationFailure(
                "Unknown assumption(s) supplied", details={"unknown": unknown, "allowed": sorted(allowed)}
            )
        for key, value in overrides.items():
            if value is None:
                continue
            setattr(base, key, value)
        return base


def derive_investment_capacity_ratio(
    *,
    risk_capacity: float,
    liquidity_requirement: str = "medium",
    loss_ability: str = "moderate",
) -> tuple[float, str]:
    """Derive the executable-investment ceiling from the user's own declared preferences.

    The research population carries a synthetic per-household ``investment_capacity_ratio``
    in 0..0.4988. An application user has no such column, so the platform derives one from
    preferences it actually stores and **discloses the derivation**. Risk *appetite*
    (``risk_tolerance``) is deliberately not an input: the audit finding F-14 requires
    capacity to be estimated separately from appetite.
    """
    liquidity_factor = {"high": 0.5, "medium": 0.75, "low": 1.0}.get(
        (liquidity_requirement or "medium").lower(), 0.75
    )
    loss_cap = {"low": 0.30, "moderate": 0.60, "high": 1.0}.get(
        (loss_ability or "moderate").lower(), 0.60
    )
    ratio = max(0.0, min(1.0, float(risk_capacity))) * liquidity_factor
    ratio = min(ratio, loss_cap)
    derivation = (
        f"risk_capacity {risk_capacity:.2f} x liquidity factor {liquidity_factor:.2f} "
        f"(requirement={liquidity_requirement}), capped by loss-ability ceiling {loss_cap:.2f}"
    )
    return round(ratio, 6), derivation


def build_financial_state(cashflow: CashFlow, *, existing_investments: float | None = None):
    """Map the platform's cash-flow object onto the research ``FinancialState``."""
    optimizer = research_loader.optimizer_module()
    invested = float(
        existing_investments if existing_investments is not None else cashflow.usable_existing_investments
    )
    return optimizer.FinancialState(
        monthly_income=max(0.0, cashflow.monthly_income),
        essential_expenses=max(0.0, cashflow.essential_expenses),
        # The user's protected buffer is charged here, not to essential expenses, so the
        # emergency-fund target and the EMI ceiling keep their correct bases. See
        # CashFlow.solver_discretionary() for the full rationale.
        discretionary_expenses=max(0.0, cashflow.solver_discretionary()),
        existing_emi=max(0.0, cashflow.existing_emi),
        liquid_savings=max(0.0, cashflow.liquid_savings),
        existing_investments=max(0.0, invested),
        usable_existing_investments=max(0.0, cashflow.usable_existing_investments),
        emergency_months=float(cashflow.emergency_months),
        emi_income_ratio_cap=float(cashflow.emi_income_ratio_cap),
        risk_capacity=float(cashflow.risk_capacity),
    )


def solve(
    *,
    goals: list[Any],
    cashflow: CashFlow,
    assumptions: LpAssumptions | None = None,
    constrained: bool = True,
    existing_investments: float | None = None,
    flow_only: bool = False,
) -> ArmResult:
    """Build the LP inputs, solve, validate and return a uniform result.

    ``flow_only`` zeroes the existing cash and asset pools so the plan is built from monthly
    contributions alone. It exists because the shared RL action contract carries only
    monthly savings/investment/loan magnitudes — it has **no** mechanism for allocating
    existing savings to a goal (the environment draws goal funding from surplus only). An
    arm comparison therefore has to be run on the monthly-flow basis, or the LP would be
    scored on a capability its competitors cannot express. The unrestricted plan is what
    ``flow_only=False`` returns and is what the application actually recommends.
    """
    assumptions = assumptions or LpAssumptions()
    warnings: list[str] = []
    started = time.perf_counter()

    if flow_only:
        warnings.append(
            "Monthly-flow-only basis: existing cash and assets are excluded so this arm is "
            "measured on the same capability as the trajectory arms."
        )

    if not goals:
        return ArmResult(
            algorithm=ALGORITHM_LP,
            status="infeasible",
            feasible=False,
            warnings=["No active goals were supplied, so there is nothing to allocate."],
            label=ALGORITHM_LABELS[ALGORITHM_LP],
        )

    if not research_loader.is_available():
        return ArmResult(
            algorithm=ALGORITHM_LP,
            status="unavailable",
            feasible=False,
            warnings=["The research project could not be located."],
            fallback_reason="research_unavailable",
            label=ALGORITHM_LABELS[ALGORITHM_LP],
        )

    capacity_ratio = assumptions.investment_capacity_ratio
    derivation = None
    if capacity_ratio is None:
        # Pass the user's own liquidity requirement and loss ability. They were previously
        # defaulted to "medium"/"moderate" here even though the profile stores both, so the
        # ceiling ignored the declared risk profile it claimed to derive from.
        capacity_ratio, derivation = derive_investment_capacity_ratio(
            risk_capacity=cashflow.risk_capacity,
            liquidity_requirement=getattr(cashflow, "liquidity_requirement", "medium"),
            loss_ability=getattr(cashflow, "loss_ability", "moderate"),
        )
    if not assumptions.allow_financing:
        assumptions = LpAssumptions(**{**assumptions.as_dict(), "max_loan_per_goal": 0.0, "max_new_loan": 0.0})
        warnings.append("Financing is disabled for this plan: no loan principal is proposed.")

    frame = goal_frame(goals, assumptions.annual_inflation)
    state = build_financial_state(cashflow, existing_investments=existing_investments)
    if flow_only:
        state.liquid_savings = 0.0
        state.existing_investments = 0.0
        state.usable_existing_investments = 0.0

    try:
        state.validate()
    except ValueError as exc:
        return ArmResult(
            algorithm=ALGORITHM_LP,
            status="invalid_input",
            feasible=False,
            warnings=[str(exc)],
            runtime_ms=int((time.perf_counter() - started) * 1000),
            label=ALGORITHM_LABELS[ALGORITHM_LP],
        )

    # The research modules require the goal frame to expose funding_gap/priority score, so
    # preparation happens here exactly as the LP itself would do it.
    optimizer = research_loader.optimizer_module()
    try:
        prepared = optimizer.prepare_goals(frame.drop(columns=["db_goal_id"]), assumptions.annual_inflation)
    except ValueError as exc:
        return ArmResult(
            algorithm=ALGORITHM_LP,
            status="invalid_input",
            feasible=False,
            warnings=[f"Goal data rejected by the LP: {exc}"],
            runtime_ms=int((time.perf_counter() - started) * 1000),
            label=ALGORITHM_LABELS[ALGORITHM_LP],
        )
    prepared = prepared.reset_index(drop=True)
    prepared["db_goal_id"] = frame["db_goal_id"].to_numpy()

    try:
        if constrained:
            module = research_loader.constrained_lp_module()
            solution = module.solve_constrained_lp(
                prepared,
                state,
                annual_inflation=assumptions.annual_inflation,
                savings_return=assumptions.savings_return,
                investment_return=assumptions.investment_return,
                investment_risk_score=assumptions.investment_risk_score,
                loan_annual_rate=assumptions.loan_annual_rate,
                loan_tenure_months=assumptions.loan_tenure_months,
                max_loan_per_goal=assumptions.max_loan_per_goal,
                max_new_loan=assumptions.max_new_loan,
                investment_capacity_ratio=capacity_ratio,
                existing_asset_return=assumptions.existing_asset_return,
                existing_asset_risk_score=assumptions.existing_asset_risk_score,
                shortfall_penalty=assumptions.shortfall_penalty,
                loan_cost_penalty=assumptions.loan_cost_penalty,
                risk_penalty=assumptions.risk_penalty,
                enforce_investment_capacity=assumptions.enforce_investment_capacity,
                enforce_single_loan_limit=assumptions.enforce_single_loan_limit,
            )
            model_version = LP_MODEL_VERSION
        else:
            solution = optimizer.optimize_multi_goal(
                prepared.drop(columns=["db_goal_id"]),
                state,
                annual_inflation=assumptions.annual_inflation,
                savings_return=assumptions.savings_return,
                investment_return=assumptions.investment_return,
                investment_risk_score=assumptions.investment_risk_score,
                loan_annual_rate=assumptions.loan_annual_rate,
                loan_tenure_months=assumptions.loan_tenure_months,
                max_loan_per_goal=assumptions.max_loan_per_goal,
                existing_asset_return=assumptions.existing_asset_return,
                existing_asset_risk_score=assumptions.existing_asset_risk_score,
                shortfall_penalty=assumptions.shortfall_penalty,
                loan_cost_penalty=assumptions.loan_cost_penalty,
                risk_penalty=assumptions.risk_penalty,
            )
            model_version = LP_UNCONSTRAINED_MODEL_VERSION
            warnings.append(
                "This is the unconstrained research LP. It does not respect the executable "
                "investment capacity and is shown for comparison only."
            )
    except Exception as exc:  # solver blew up — never fake a plan
        return ArmResult(
            algorithm=ALGORITHM_LP,
            status="error",
            feasible=False,
            warnings=[f"The LP solver raised an error: {type(exc).__name__}"],
            diagnostics={"error": str(exc)},
            runtime_ms=int((time.perf_counter() - started) * 1000),
            model_version=capacity_ratio and LP_MODEL_VERSION or LP_MODEL_VERSION,
            label=ALGORITHM_LABELS[ALGORITHM_LP],
        )

    runtime_ms = int((time.perf_counter() - started) * 1000)

    if solution.get("status") != "optimal":
        return ArmResult(
            algorithm=ALGORITHM_LP,
            status="infeasible",
            feasible=False,
            warnings=[
                "The solver reported no feasible allocation for these goals, resources and "
                "constraints.",
                str(solution.get("solver_message", ""))[:400],
            ],
            diagnostics={"solver_message": solution.get("solver_message", "")},
            runtime_ms=runtime_ms,
            model_version=model_version,
            label=ALGORITHM_LABELS[ALGORITHM_LP],
        )

    alloc: pd.DataFrame = solution["allocations"].copy()
    alloc["db_goal_id"] = prepared["db_goal_id"].to_numpy()
    # The constrained solver returns `goal_id` only; carry the human-readable name and the DB
    # primary key through so plan diffs and the UI never show an empty goal label.
    alloc["goal_name"] = prepared["goal_name"].to_numpy()
    if "funding_gap" not in alloc and "funding_gap" in prepared:
        alloc["funding_gap"] = prepared["funding_gap"].to_numpy()
    # ``solve_constrained_lp`` emits the allocation vectors but not the goal's cost basis, so
    # the plan carried ``future_goal_cost = 0`` while its own funding gap was non-zero. The
    # prepared frame is the authority for both figures; carry them through positionally in the
    # same way as ``db_goal_id`` and ``goal_name`` (the solver preserves row order).
    for column in ("future_goal_cost", "existing_funding"):
        if column in prepared.columns and column not in alloc.columns:
            alloc[column] = prepared[column].to_numpy()
    constraints = dict(solution.get("constraints", {}))
    summary = dict(solution.get("summary", {}))
    # One vocabulary for the comparison table. `monthly_contributions_allocated` is the plan's
    # instruction for this month; it is not the same quantity as the simulator's average
    # credited contribution, and the two are named differently on purpose.
    summary.setdefault(
        "monthly_contribution_planned", summary.get("monthly_contributions_allocated", 0.0)
    )
    summary.setdefault("monthly_savings_planned", summary.get("monthly_savings_allocated", 0.0))
    summary.setdefault(
        "monthly_investment_planned", summary.get("monthly_investment_allocated", 0.0)
    )
    # Disclose the buffer split. `monthly_surplus` inside the constraint block is the
    # solver-visible goal budget (surplus net of the protected buffer); the gross surplus the
    # household actually has is reported alongside it so nothing is hidden by the mapping.
    constraints["gross_monthly_surplus"] = round(float(cashflow.monthly_surplus), 2)
    constraints["protected_buffer"] = round(float(cashflow.protected_buffer), 2)
    constraints["available_goal_budget"] = round(float(cashflow.available_goal_budget), 2)
    constraints["surplus_basis"] = cashflow.surplus_basis

    # The constraint block is the authority on the pool sizes; re-derive the same values
    # from the cash flow when a key is missing so validation is never skipped silently.
    monthly_surplus = float(constraints.get("monthly_surplus", max(0.0, cashflow.monthly_surplus)))
    emi_cap = float(
        constraints.get(
            "emi_cap", max(0.0, cashflow.monthly_income * cashflow.emi_income_ratio_cap - cashflow.existing_emi)
        )
    )
    available_cash = float(
        constraints.get("available_cash", cashflow.available_cash_for_goals)
    )
    usable_assets = float(
        constraints.get("usable_existing_assets", cashflow.usable_existing_investments)
    )
    investment_permitted = constraints.get("investment_permitted")

    violations = validate_plan(
        alloc,
        constraints,
        monthly_surplus=monthly_surplus,
        emi_cap=emi_cap,
        available_cash=available_cash,
        usable_existing_assets=usable_assets,
        investment_permitted=float(investment_permitted) if investment_permitted is not None else None,
    )
    feasible = not violations

    if not feasible:
        warnings.append(
            "The solver returned an allocation that fails platform validation; it is reported "
            "as infeasible rather than presented as a plan."
        )
    if capacity_ratio is not None and assumptions.enforce_investment_capacity:
        warnings.append(
            "Investment capacity is capped so the plan is executable: "
            f"ratio {capacity_ratio:.4f}" + (f" ({derivation})" if derivation else "")
        )
    if float(summary.get("total_shortfall", 0.0)) > 1e-6:
        warnings.append(
            f"Not every goal can be met: {float(summary['total_shortfall']):,.0f} of funding gap "
            "remains across the goal set."
        )

    # A corner solution is mathematically valid but looks like a bug unless it is explained.
    if len(alloc) > 1:
        def _monthly(row) -> float:
            return float(row.get("monthly_savings_contribution", 0) or 0) + float(
                row.get("monthly_investment_contribution", 0) or 0
            )

        unfunded = [
            str(row.get("goal_name") or row.get("goal_id"))
            for _, row in alloc.iterrows()
            if _monthly(row) <= 1e-6 and float(row.get("funding_gap", 0) or 0) > 1.0
        ]
        funded = [row for _, row in alloc.iterrows() if _monthly(row) > 1e-6]
        if unfunded and funded:
            warnings.append(
                "This plan directs no monthly money to "
                + ", ".join(unfunded)
                + " because the objective minimises the priority-weighted shortfall, and the "
                "remaining budget reduces it most by concentrating on "
                + str(funded[0].get("goal_name") or funded[0].get("goal_id"))
                + ". That is a consequence of the stated priorities, not a missing allocation: "
                "changing a goal's priority changes the split."
            )

    return ArmResult(
        algorithm=ALGORITHM_LP,
        status="optimal" if feasible else "invalid_plan",
        feasible=feasible,
        allocations=alloc.round(2).to_dict(orient="records"),
        summary={k: _jsonable(v) for k, v in summary.items()},
        constraints={k: _jsonable(v) for k, v in constraints.items()},
        diagnostics={
            "validation": violation_summary(violations),
            "investment_capacity_derivation": derivation,
            "objective_definition": OBJECTIVE_DEFINITION,
            "solver_message": str(solution.get("solver_message", ""))[:400],
        },
        objective_value=float(solution.get("objective", float("nan"))) if solution.get("objective") == solution.get("objective") else None,
        runtime_ms=runtime_ms,
        model_version=model_version,
        config_version=(
            f"constrained={constrained};capacity={capacity_ratio:.4f};"
            f"inflation={assumptions.annual_inflation};invest={assumptions.investment_return};"
            f"loan={assumptions.loan_annual_rate}"
        ),
        warnings=warnings,
        label=ALGORITHM_LABELS[ALGORITHM_LP],
    )


def _jsonable(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:  # pragma: no cover
            pass
    return str(value)
