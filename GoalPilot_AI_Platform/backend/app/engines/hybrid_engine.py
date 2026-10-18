"""LP + RL hybrid.

Division of responsibility (explicit, tested, and impossible to blur):

    RL  proposes θ  = the monthly savings-vs-investment split actually realised by the
                      trained policy.
    LP  computes the constrained allocation under θ and stays the allocator of record,
        including any loan the plan's own assumptions permit.
    SIM evaluates the resulting plan on the same monthly path as every other arm, replaying
        that plan's loan through the environment's borrowing channel.

Why the split is safe
---------------------
θ can only *lower* the investment capacity ceiling, which is an upper bound and therefore
cannot violate a constraint. Financing is **not** taken from the policy: the shared
evaluation rollout forces the borrowing channel off so arms are compared on one basis, so a
policy could never be seen borrowing and using that signal silently removed financing from
every hybrid plan. Financing now follows the plan's assumptions, subject to the same EMI
ceiling and loan limits as the LP arm. The hybrid therefore still **cannot** weaken a
financial safety constraint to make a plan appear feasible — a plan that fails validation is
rejected and the LP-only plan is returned with an explicit reason.

If the RL stage is unavailable, the hybrid returns a transparent LP-only fallback and says
so. It never fabricates an RL contribution.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, asdict
from typing import Any

import numpy as np

from app.engines import lp_engine, research_loader, rl_engine
from app.engines.common import ALGORITHM_HYBRID, ALGORITHM_LABELS, ArmResult
from app.engines.rl_engine import (
    RL_GOAL_SLOTS,
    encode_plan_for_env,
    env_goal_order,
    make_env,
    rollout,
)
from app.services.cashflow import CashFlow

HYBRID_MODEL_VERSION = "hybrid_rl_thetagover_lp@v1"

#: Blend factor for the RL-proposed split. 1.0 = take the policy's split at face value.
DEFAULT_BLEND = 1.0


@dataclass
class HybridTheta:
    rl_observed_investment_fraction: float
    rl_observed_borrowing: bool
    rl_savings_per_month: float
    rl_investment_per_month: float
    base_capacity_ratio: float
    effective_capacity_ratio: float
    allow_financing: bool
    blend: float
    fallback: str | None = None
    #: The policy's uncensored request, before the environment applies the capacity cap.
    rl_requested_investment_fraction: float = 0.0
    #: "policy_requested_mix" or "realized_credit_fallback" — which input set the ceiling.
    theta_source: str = "policy_requested_mix"
    #: The LP's own savings/investment split, filled in after the LP stage.
    lp_realized_investment_fraction: float = 0.0
    lp_investment_permitted: float = 0.0
    capacity_binding: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def derive_theta(rl_result: ArmResult, *, base_capacity_ratio: float,
                 blend: float = DEFAULT_BLEND, allow_financing: bool = True) -> HybridTheta:
    """Read θ out of the RL trajectory. No θ is invented when the RL arm failed.

    θ is the **investment-capacity ceiling** implied by the policy's *requested* monthly
    savings/investment mix. It is not a mandated allocation: the LP remains the allocator and
    may invest less when cash savings is the cheaper way to fund a goal over its horizon.

    Using the *requested* mix matters. The environment caps investment at
    ``surplus x capacity_ratio`` and (in share mode) relabels the excess as savings, so the
    realised investment fraction can never exceed the ceiling it is being used to set. Reading
    the censored figure would make the hybrid tighten its own cap twice and, in the observed
    case, collapse investment capacity to zero even though the policy asked to invest.

    Financing is taken from the plan's own assumptions, **not** from the policy's borrowing
    channel. The shared evaluation rollout zeroes that channel so every arm is compared on the
    same no-new-borrowing basis, which meant the policy could never be seen borrowing — and
    ``allow_financing = borrowing`` therefore removed financing from every hybrid plan. A loan
    inside the EMI ceiling was structurally unreachable.
    """
    summary = rl_result.summary or {}
    savings = float(summary.get("monthly_savings_contribution", 0.0) or 0.0)
    investment = float(summary.get("monthly_investment_contribution", 0.0) or 0.0)
    total = savings + investment
    observed_fraction = (investment / total) if total > 1e-9 else 0.0
    borrowing = float(summary.get("loan_principal", 0.0) or 0.0) > 1e-6

    requested = summary.get("requested_investment_fraction")
    if isinstance(requested, (int, float)):
        requested_fraction = max(0.0, min(1.0, float(requested)))
        theta_source = "policy_requested_mix"
    else:
        # Older/other callers may not carry the requested mix. Fall back, but say so.
        requested_fraction = observed_fraction
        theta_source = "realized_credit_fallback"

    # blended ceiling: blend=1.0 adopts the policy's request, blend=0.0 ignores it
    effective = max(0.0, min(base_capacity_ratio, base_capacity_ratio * (1 - blend)
                            + requested_fraction * blend))
    return HybridTheta(
        rl_observed_investment_fraction=observed_fraction,
        rl_observed_borrowing=borrowing,
        rl_savings_per_month=savings,
        rl_investment_per_month=investment,
        base_capacity_ratio=base_capacity_ratio,
        effective_capacity_ratio=effective,
        allow_financing=allow_financing,
        blend=blend,
        rl_requested_investment_fraction=requested_fraction,
        theta_source=theta_source,
    )


def solve(
    *,
    goals: list[Any],
    cashflow: CashFlow,
    months_lookup: dict[int, int],
    base_assumptions: lp_engine.LpAssumptions | None = None,
    checkpoint_path: str | None = None,
    blend: float = DEFAULT_BLEND,
    flow_only: bool = False,
) -> ArmResult:
    """RL → θ → LP → simulator evaluation.

    ``flow_only`` propagates to the LP so the hybrid can be scored on the same
    monthly-flow basis as the other arms (see ``lp_engine.solve``).
    """
    started = time.perf_counter()
    assumptions = base_assumptions or lp_engine.LpAssumptions()

    capacity_ratio, derivation = lp_engine.derive_investment_capacity_ratio(
        risk_capacity=cashflow.risk_capacity,
        liquidity_requirement=getattr(cashflow, "liquidity_requirement", "medium"),
        loss_ability=getattr(cashflow, "loss_ability", "moderate"),
    )

    # ---- 1. RL proposes ---------------------------------------------------------------
    rl_result = rl_engine.solve(
        goals=goals,
        cashflow=cashflow,
        months_lookup=months_lookup,
        checkpoint_path=checkpoint_path,
    )

    fallback_reason: str | None = None
    theta: HybridTheta
    if rl_result.status != "optimal":
        fallback_reason = rl_result.fallback_reason or f"rl_status_{rl_result.status}"
        theta = HybridTheta(
            rl_observed_investment_fraction=0.0,
            rl_observed_borrowing=False,
            rl_savings_per_month=0.0,
            rl_investment_per_month=0.0,
            base_capacity_ratio=capacity_ratio,
            effective_capacity_ratio=capacity_ratio,
            allow_financing=bool(assumptions.allow_financing),
            blend=blend,
            fallback=fallback_reason,
        )
    else:
        theta = derive_theta(
            rl_result,
            base_capacity_ratio=capacity_ratio,
            blend=blend,
            allow_financing=bool(assumptions.allow_financing),
        )

    # ---- 2. LP solves under θ ---------------------------------------------------------
    lp_assumptions = lp_engine.LpAssumptions(
        **{
            **assumptions.as_dict(),
            "investment_capacity_ratio": theta.effective_capacity_ratio,
            "allow_financing": theta.allow_financing,
            "max_loan_per_goal": assumptions.max_loan_per_goal if theta.allow_financing else 0.0,
            "max_new_loan": assumptions.max_new_loan if theta.allow_financing else 0.0,
        }
    )
    lp_result = lp_engine.solve(
        goals=goals,
        cashflow=cashflow,
        assumptions=lp_assumptions,
        constrained=True,
        flow_only=flow_only,
    )

    warnings: list[str] = []
    if fallback_reason:
        warnings.append(
            "The RL stage could not contribute, so the hybrid fell back to the plain LP plan. "
            f"Reason: {fallback_reason}."
        )
    if not lp_result.feasible:
        # Never present an invalid hybrid plan. Report it as infeasible and hand back the
        # LP-only result so the caller still has an actionable plan.
        return ArmResult(
            algorithm=ALGORITHM_HYBRID,
            status="infeasible",
            feasible=False,
            allocations=lp_result.allocations,
            summary=lp_result.summary,
            constraints=lp_result.constraints,
            diagnostics={
                "theta": theta.as_dict(),
                "lp_status": lp_result.status,
                "lp_diagnostics": lp_result.diagnostics,
                "fallback": "lp_only_plan_returned",
            },
            runtime_ms=int((time.perf_counter() - started) * 1000),
            model_version=HYBRID_MODEL_VERSION,
            config_version=f"blend={blend};capacity={theta.effective_capacity_ratio:.4f}",
            warnings=warnings
            + ["The constrained allocation failed validation; the LP-only plan is returned."],
            fallback_reason="hybrid_allocation_invalid",
            label=ALGORITHM_LABELS[ALGORITHM_HYBRID],
        )

    # ---- 2b. what the LP actually did with the ceiling ---------------------------------
    lp_investment = sum(
        float(row.get("monthly_investment_contribution") or 0)
        for row in lp_result.allocations or []
    )
    lp_contributions = sum(
        float(row.get("monthly_savings_contribution") or 0)
        + float(row.get("monthly_investment_contribution") or 0)
        for row in lp_result.allocations or []
    )
    permitted = float(lp_result.constraints.get("investment_permitted", 0.0) or 0.0)
    theta.lp_realized_investment_fraction = (
        lp_investment / lp_contributions if lp_contributions > 1e-9 else 0.0
    )
    theta.lp_investment_permitted = permitted
    theta.capacity_binding = permitted > 1e-6 and lp_investment >= permitted - max(1.0, 1e-6 * permitted)

    # ---- 3. evaluate the hybrid plan on the shared path -------------------------------
    evaluation = _evaluate_plan(
        goals=goals,
        cashflow=cashflow,
        months_lookup=months_lookup,
        allocations=lp_result.allocations,
        capacity_ratio=theta.effective_capacity_ratio,
    )

    loan_in_plan = sum(float(row.get("loan_principal") or 0) for row in lp_result.allocations or [])
    warnings.extend(
        [
            "The RL stage proposed an investment-capacity ceiling from the policy's requested "
            "savings/investment mix; the LP computed the allocation and remains the allocator of "
            "record. Financing follows the plan's own assumptions, because the shared rollout "
            "cannot observe a policy borrowing.",
            "θ can only lower the investment ceiling, so the hybrid cannot relax a financial "
            "safety constraint.",
            f"Base investment capacity {theta.base_capacity_ratio:.4f} → effective "
            f"{theta.effective_capacity_ratio:.4f} (the policy requested a monthly investment "
            f"fraction of {theta.rl_requested_investment_fraction:.4f}; the realised, "
            f"post-cap fraction was {theta.rl_observed_investment_fraction:.4f}).",
            "The summary is this plan's own arithmetic. The shared simulator allocates the whole "
            "monthly budget to goals before it considers a new EMI, so it cannot replay a plan "
            "that contributes and borrows in the same month; its metrics are kept in diagnostics "
            "for comparison only.",
        ]
    )
    if permitted > 1e-6 and lp_investment <= 1e-6:
        warnings.append(
            "The LP allocated no investment even though the ceiling allowed "
            f"{permitted:,.0f}/month: over these goal horizons, saving in cash was the cheaper "
            "way to reach the targets once the risk cost was priced in. The ceiling is a limit, "
            "not a target, so this is the LP's own decision rather than a missing constraint."
        )
    if not theta.allow_financing:
        warnings.append(
            "Financing is switched off in this plan's assumptions, so the LP could not consider "
            "a loan. Enable 'Allow financing' to let it weigh one within your EMI ceiling."
        )

    return ArmResult(
        algorithm=ALGORITHM_HYBRID,
        status="optimal",
        feasible=True,
        allocations=lp_result.allocations,
        # The plan is the allocator of record; the rollout is a comparison harness that cannot
        # represent this plan's financing (see the warning above), so it is not the summary.
        summary=lp_result.summary,
        constraints=lp_result.constraints,
        diagnostics={
            "theta": theta.as_dict(),
            "capacity_derivation": derivation,
            "lp_status": lp_result.status,
            "lp_objective": lp_result.objective_value,
            # The rollout metrics are stored alongside the evaluation flags. Without them the
            # selector had no comparable figures and silently fell back to the LP's static
            # summary while still labelling the arm a trajectory.
            "evaluation": evaluation.get("diagnostics", {}),
            "evaluation_metrics": evaluation.get("metrics", {}),
            "rl_component": {
                "status": rl_result.status,
                "model_version": rl_result.model_version,
                "summary": rl_result.summary,
            },
            "fallback": fallback_reason,
        },
        objective_value=lp_result.objective_value,
        runtime_ms=int((time.perf_counter() - started) * 1000),
        model_version=HYBRID_MODEL_VERSION,
        config_version=f"blend={blend};capacity={theta.effective_capacity_ratio:.4f}",
        warnings=warnings,
        fallback_reason=fallback_reason,
        label=ALGORITHM_LABELS[ALGORITHM_HYBRID],
    )


def _evaluate_plan(
    *,
    goals: list[Any],
    cashflow: CashFlow,
    months_lookup: dict[int, int],
    allocations: list[dict[str, Any]],
    capacity_ratio: float,
) -> dict[str, Any]:
    """Roll the LP-produced allocation through the same simulator the RL arm uses."""
    if not goals or len(goals) > RL_GOAL_SLOTS or not allocations:
        return {"metrics": {}, "diagnostics": {"evaluated": False, "reason": "not_evaluable"}}

    profile = rl_engine.build_profile_row(
        cashflow, investment_capacity_ratio=capacity_ratio, risk_score=cashflow.risk_capacity
    )
    goal_frame = rl_engine.build_goal_frame(goals, months_lookup, profile["user_id"].iloc[0])
    try:
        env = make_env(profile=profile, goals=goal_frame, market=research_loader.market_frame())
    except Exception as exc:
        return {"metrics": {}, "diagnostics": {"evaluated": False, "reason": str(exc)}}

    # Encode in the environment's own slot order (goals sorted by horizon), never in the
    # order the caller happened to load them in.
    action = encode_plan_for_env(env, allocations)
    slot_order = env_goal_order(env)

    # Replay the plan's own loan. The environment's borrowing channel takes an EMI fraction of
    # the goal's EMI budget, so the plan's EMI is expressed on that same scale. Evaluating a plan
    # that borrows while telling the simulator it does not made a fully funded plan report a
    # shortfall of its own loan amount.
    emi_budget = max(
        0.0, cashflow.monthly_income * cashflow.emi_income_ratio_cap - cashflow.existing_emi
    )
    borrowing = None
    if emi_budget > 0:
        by_ref = {
            str(a.get("goal_ref") or a.get("goal_id")): float(a.get("estimated_loan_emi") or 0.0)
            for a in allocations
        }
        fractions = np.array(
            [by_ref.get(ref, 0.0) / emi_budget for ref in slot_order],
            dtype=np.float32,
        )
        borrowing = np.clip(fractions, 0.0, 1.0) if fractions.any() else None

    def provider(_env, _month: int) -> np.ndarray:
        return action

    try:
        outcome = rollout(
            env=env,
            action_provider=provider,
            label="hybrid_lp_plan",
            borrowing_fractions=borrowing,
        )
    except Exception as exc:
        return {"metrics": {}, "diagnostics": {"evaluated": False, "reason": str(exc)}}
    return {
        "metrics": outcome.metrics,
        "diagnostics": {
            "evaluated": True,
            "borrowing_replayed": borrowing is not None,
            "env_slot_order": slot_order,
            "per_goal": outcome.per_goal,
            **outcome.diagnostics,
        },
    }


def evaluate_static_plan(
    *,
    goals: list[Any],
    cashflow: CashFlow,
    months_lookup: dict[int, int],
    allocations: list[dict[str, Any]],
    capacity_ratio: float,
    label: str,
) -> dict[str, Any]:
    """Public wrapper so the selector can score an LP-only plan on the same basis."""
    return _evaluate_plan(
        goals=goals,
        cashflow=cashflow,
        months_lookup=months_lookup,
        allocations=allocations,
        capacity_ratio=capacity_ratio,
    )
