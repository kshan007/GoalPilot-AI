"""Algorithm-selection service.

All eligible arms are scored on **the same inputs**: the same user, the same goals, the same
initial resources, the same monthly market path, the same assumption set, and the same
no-new-borrowing roll-out basis. Each arm's static allocation is encoded into the identical
action contract so the comparison is like-for-like.

Decision rule (stated before the results are seen, so it cannot be reverse-engineered onto
the winner):

1. Only arms that are available *and* pass plan validation are candidates.
2. The LP stays the default. Another arm is recommended **only** if it beats the LP's
   weighted goal achievement by at least ``MIN_ACHIEVEMENT_GAIN`` **and** is not worse than
   the LP on deadline success by more than ``DEADLINE_TOLERANCE``.
3. Ties go to the LP, because the LP's plan is auditable constraint-by-constraint and the
   research evaluation found no arm with a statistically robust advantage.
4. If no arm improves on the LP, or the evidence is insufficient, the response says so
   explicitly rather than promoting the most sophisticated model.
"""
from __future__ import annotations

import time
from typing import Any

from app.engines import hybrid_engine, lp_engine, research_loader, rl_engine
from app.engines.common import (
    ALGORITHM_HYBRID,
    ALGORITHM_LP,
    ALGORITHM_RL,
    ALGORITHM_RULE,
    METRIC_DEFINITIONS,
)
from app.engines.rl_engine import RL_GOAL_SLOTS, encode_plan_for_env, make_env, rollout
from app.services.cashflow import CashFlow

MIN_ACHIEVEMENT_GAIN = 0.02
DEADLINE_TOLERANCE = 0.02

SELECTOR_VERSION = "selector@v1"

RESEARCH_REFERENCE_NOTE = (
    "Authoritative held-out comparison (16 fresh test users) recorded by the research "
    "evaluation: the best arm was a simple investment rule at 0.5800 weighted achievement; "
    "the best trained RL arm was 0.4842 (paired difference -0.0957, CI [-0.1423, -0.0497], "
    "excludes zero); the capacity-constrained LP was 0.2452 on achievement but had the best "
    "deadline success (0.1531). Source: research outputs/evaluation/final_validation_v8."
)


def _trajectory_metrics(
    *,
    goals: list[Any],
    cashflow: CashFlow,
    months_lookup: dict[int, int],
    allocations: list[dict[str, Any]],
    capacity_ratio: float,
    label: str,
) -> dict[str, Any] | None:
    if not goals or len(goals) > RL_GOAL_SLOTS or not allocations:
        return None
    profile = rl_engine.build_profile_row(
        cashflow, investment_capacity_ratio=capacity_ratio, risk_score=cashflow.risk_capacity
    )
    goal_frame = rl_engine.build_goal_frame(goals, months_lookup, profile["user_id"].iloc[0])
    try:
        env = make_env(profile=profile, goals=goal_frame, market=research_loader.market_frame())
    except Exception:
        return None
    # Map the plan onto the environment's own slots by goal id. The environment sorts goals by
    # horizon, so passing the allocations positionally would fund the wrong goals whenever the
    # plan's order differs (it is loaded by priority).
    action = encode_plan_for_env(env, allocations)

    def provider(_env, _month: int) -> Any:
        return action

    try:
        outcome = rollout(env=env, action_provider=provider, label=label)
    except Exception:
        return None
    return outcome.metrics


def _rule_baseline_action(goals: list[Any]) -> Any:
    return rl_engine.baseline_uniform_savings(goals)


def _rule_metrics(
    *,
    goals: list[Any],
    cashflow: CashFlow,
    months_lookup: dict[int, int],
    capacity_ratio: float,
) -> dict[str, Any] | None:
    if not goals or len(goals) > RL_GOAL_SLOTS:
        return None
    profile = rl_engine.build_profile_row(
        cashflow, investment_capacity_ratio=capacity_ratio, risk_score=cashflow.risk_capacity
    )
    goal_frame = rl_engine.build_goal_frame(goals, months_lookup, profile["user_id"].iloc[0])
    try:
        env = make_env(profile=profile, goals=goal_frame, market=research_loader.market_frame())
    except Exception:
        return None
    action = _rule_baseline_action(goals)

    def provider(_env, _month: int) -> Any:
        return action

    try:
        outcome = rollout(env=env, action_provider=provider, label="rule_uniform_savings")
    except Exception:
        return None
    return outcome.metrics


def compare(
    *,
    goals: list[Any],
    cashflow: CashFlow,
    months_lookup: dict[int, int],
    checkpoint_path: str | None = None,
    include_rule_baseline: bool = True,
    include_hybrid: bool = True,
) -> dict[str, Any]:
    """Run every arm and produce the selection decision."""
    started = time.perf_counter()
    capacity_ratio, derivation = lp_engine.derive_investment_capacity_ratio(
        risk_capacity=cashflow.risk_capacity,
        liquidity_requirement=getattr(cashflow, "liquidity_requirement", "medium"),
        loss_ability=getattr(cashflow, "loss_ability", "moderate"),
    )

    arms: list[dict[str, Any]] = []
    notes: list[str] = []

    # ---- LP ---------------------------------------------------------------------------
    # Solved on the monthly-flow basis so the LP is measured on exactly the capability the
    # shared trajectory contract can express. The unrestricted plan (which also deploys
    # existing savings) is produced by /optimize/plan.
    lp_result = lp_engine.solve(
        goals=goals, cashflow=cashflow, constrained=True, flow_only=True
    )
    lp_metrics = (
        _trajectory_metrics(
            goals=goals,
            cashflow=cashflow,
            months_lookup=months_lookup,
            allocations=lp_result.allocations,
            capacity_ratio=capacity_ratio,
            label="lp_plan",
        )
        if lp_result.feasible
        else None
    )
    arms.append(
        {
            "algorithm": ALGORITHM_LP,
            "label": lp_result.label,
            "status": lp_result.status,
            "feasible": lp_result.feasible,
            "available": True,
            "metrics": lp_metrics or _static_metrics(lp_result),
            "metric_basis": "trajectory" if lp_metrics else "static_plan",
            "runtime_ms": lp_result.runtime_ms,
            "model_version": lp_result.model_version,
            "warnings": lp_result.warnings,
            "fallback_reason": lp_result.fallback_reason,
        }
    )

    # ---- RL ---------------------------------------------------------------------------
    rl_result = rl_engine.solve(
        goals=goals, cashflow=cashflow, months_lookup=months_lookup, checkpoint_path=checkpoint_path
    )
    arms.append(
        {
            "algorithm": ALGORITHM_RL,
            "label": rl_result.label,
            "status": rl_result.status,
            "feasible": rl_result.feasible,
            "available": rl_result.status == "optimal",
            "metrics": rl_result.summary if rl_result.status == "optimal" else {},
            "metric_basis": "trajectory",
            "runtime_ms": rl_result.runtime_ms,
            "model_version": rl_result.model_version,
            "warnings": rl_result.warnings,
            "fallback_reason": rl_result.fallback_reason,
        }
    )

    # ---- hybrid -----------------------------------------------------------------------
    hybrid_result = None
    if include_hybrid:
        hybrid_result = hybrid_engine.solve(
            goals=goals,
            cashflow=cashflow,
            months_lookup=months_lookup,
            checkpoint_path=checkpoint_path,
            flow_only=True,
        )
        # The hybrid's `summary` is the LP's own static arithmetic. Its rollout metrics live in
        # diagnostics, and those are the only figures comparable with the LP/RL arms. Reporting
        # the static summary under `metric_basis="trajectory"` compared a projection with a
        # simulation and made the hybrid look better on achievement while scoring 0% deadline
        # success because it had no deadline metric at all.
        hybrid_diagnostics = hybrid_result.diagnostics or {}
        hybrid_evaluation = hybrid_diagnostics.get("evaluation") or {}
        hybrid_metrics = None
        if hybrid_evaluation.get("evaluated"):
            hybrid_metrics = hybrid_diagnostics.get("evaluation_metrics") or None
        arms.append(
            {
                "algorithm": ALGORITHM_HYBRID,
                "label": hybrid_result.label,
                "status": hybrid_result.status,
                "feasible": hybrid_result.feasible,
                "available": hybrid_result.status == "optimal",
                "metrics": hybrid_metrics or (
                    _static_metrics(hybrid_result) if hybrid_result.status == "optimal" else {}
                ),
                "metric_basis": "trajectory" if hybrid_metrics else "static_plan",
                "runtime_ms": hybrid_result.runtime_ms,
                "model_version": hybrid_result.model_version,
                "warnings": hybrid_result.warnings,
                "fallback_reason": hybrid_result.fallback_reason,
            }
        )
        if hybrid_result.status == "optimal" and not hybrid_metrics:
            notes.append(
                "The hybrid plan could not be replayed on the shared trajectory (its evaluation "
                "was not available), so it is reported on a static-plan basis and is not ranked "
                "against the trajectory arms."
            )

    # ---- rule baseline ----------------------------------------------------------------
    if include_rule_baseline:
        rule_metrics = _rule_metrics(
            goals=goals, cashflow=cashflow, months_lookup=months_lookup,
            capacity_ratio=capacity_ratio,
        )
        if rule_metrics:
            arms.append(
                {
                    "algorithm": ALGORITHM_RULE,
                    "label": "Uniform savings rule",
                    "status": "optimal",
                    "feasible": True,
                    "available": True,
                    "metrics": rule_metrics,
                    "metric_basis": "trajectory",
                    "runtime_ms": 0,
                    "model_version": "uniform_savings@v1",
                    "warnings": ["A deliberately simple control: equal savings weight per goal."],
                    "fallback_reason": None,
                }
            )

    # ---- decision ---------------------------------------------------------------------
    candidates = [a for a in arms if a["available"] and a["feasible"]]
    lp_arm = next((a for a in arms if a["algorithm"] == ALGORITHM_LP), None)

    if not candidates:
        recommendation = ALGORITHM_LP
        reason = (
            "No arm produced a valid plan for this input. The LP is named as the intended "
            "default by policy, and its diagnostics are reported above."
        )
        sufficient_evidence = False
    elif lp_arm is None or lp_arm not in candidates:
        best = max(candidates, key=lambda a: _achievement(a))
        recommendation = best["algorithm"]
        reason = (
            "The LP plan failed validation, so the best remaining validated arm is named. "
            "This is a fallback, not an endorsement."
        )
        sufficient_evidence = False
    else:
        lp_achievement = _achievement(lp_arm)
        lp_deadline = _deadline(lp_arm)
        better: list[dict[str, Any]] = []
        for arm in candidates:
            if arm["algorithm"] == ALGORITHM_LP:
                continue
            # Never rank across metric bases: a static projection is not comparable with a
            # replay, and pretending otherwise was a real comparability defect.
            if arm["metric_basis"] != lp_arm["metric_basis"]:
                continue
            if (
                _achievement(arm) >= lp_achievement + MIN_ACHIEVEMENT_GAIN
                and _deadline(arm) >= lp_deadline - DEADLINE_TOLERANCE
            ):
                better.append(arm)
        if better:
            best = max(better, key=lambda a: (_achievement(a), _deadline(a)))
            recommendation = best["algorithm"]
            reason = (
                f"{best['label']} beats the LP by {_achievement(best) - lp_achievement:+.4f} "
                f"weighted achievement without giving up more than "
                f"{DEADLINE_TOLERANCE:.2f} of deadline success."
            )
            sufficient_evidence = True
        else:
            recommendation = ALGORITHM_LP
            reason = (
                "No alternative arm beat the LP by the required margin while holding deadline "
                "success, so the LP plan is recommended. The LP is fully constrained, "
                "auditable and reproducible; it is also the arm the research evaluation found "
                "to have the best deadline performance."
            )
            sufficient_evidence = False

    not_selected = []
    for arm in arms:
        if arm["algorithm"] == recommendation:
            continue
        not_selected.append(
            {
                "algorithm": arm["algorithm"],
                "label": arm["label"],
                "reason": _why_not(arm, lp_arm, recommendation),
            }
        )

    if any(a["algorithm"] == ALGORITHM_RL and a["status"] == "unavailable" for a in arms):
        notes.append(
            "The RL arm was unavailable for this plan and was not evaluated; no RL metric is "
            "reported. Reason: "
            + str(next(a["fallback_reason"] for a in arms
                       if a["algorithm"] == ALGORITHM_RL and a["status"] == "unavailable"))
        )
    if any(a["metric_basis"] == "static_plan" for a in arms):
        notes.append(
            "At least one arm could only be scored from its static plan because the trajectory "
            "basis (a single shared action contract) is limited to "
            f"{RL_GOAL_SLOTS} goals. Arms with different bases are not ranked against each other."
        )
    notes.append(
        "Financing is disabled inside every roll-out so all arms are measured on a "
        "no-new-borrowing basis. Financing capacity is reported separately per arm."
    )
    notes.append(
        "All arms are scored on a monthly-contribution basis: the shared action contract "
        "carries only monthly savings/investment/loan magnitudes and has no mechanism for "
        "allocating existing savings to a goal, so the LP and hybrid arms are re-solved with "
        "the existing cash and asset pools excluded. The recommended plan on the planning "
        "page does use existing savings."
    )
    notes.append(RESEARCH_REFERENCE_NOTE)
    notes.append(
        f"Investment capacity ratio used for every arm: {capacity_ratio:.4f} ({derivation})."
    )

    # Attach a single, fixed comparison vocabulary to every arm. The raw `metrics` block stays
    # because each engine reports extra diagnostics, but the table below is what the UI shows:
    # the same keys, measured the same way, for every arm.
    lp_basis = (lp_arm or {}).get("metric_basis", "trajectory")
    for arm in arms:
        arm["ranked"] = bool(
            arm.get("available")
            and arm.get("feasible")
            and arm.get("metric_basis") == lp_basis
            and arm.get("status") not in ("unavailable", "failed", "infeasible")
        )
        arm["metrics_comparable"] = _comparable(arm.get("metrics") or {})

    # Two metrics, two possible winners. Reporting the disagreement is the honest alternative to
    # silently picking a weighting: "spread contributions thinly" and "complete the top goals"
    # are different objectives, and a reader is entitled to see when they disagree.
    scored = [
        a for a in arms
        if a.get("status") not in ("unavailable", "failed") and a.get("metric_basis") == lp_basis
    ]
    by_achievement = max(scored, key=_achievement, default=None)
    by_deadline = max(scored, key=_deadline, default=None)
    disagreement_present = bool(
        by_achievement
        and by_deadline
        and by_achievement["algorithm"] != by_deadline["algorithm"]
    )
    objective_disagreement = {
        "present": disagreement_present,
        "by_weighted_achievement": by_achievement["algorithm"] if by_achievement else None,
        "by_deadline_completion": by_deadline["algorithm"] if by_deadline else None,
        "note": (
            "Weighted goal achievement rewards progress spread across goals; deadline completion "
            "rewards finishing goals on time. When these disagree, the LP-anchored decision rule "
            "decides, and the reason is in recommendation_reason."
            if disagreement_present
            else "Both metrics select the same arm on this input."
        ),
    }

    return {
        "selector_version": SELECTOR_VERSION,
        "recommended_algorithm": recommendation,
        "objective_disagreement": objective_disagreement,
        "decision_basis": (
            "LP-anchored: a challenger replaces the LP only if it gains at least "
            f"{MIN_ACHIEVEMENT_GAIN} weighted achievement without losing more than "
            f"{DEADLINE_TOLERANCE} deadline success."
        ),
        "recommendation_reason": reason,
        "sufficient_evidence_for_change": sufficient_evidence,
        "decision_rule": {
            "min_achievement_gain": MIN_ACHIEVEMENT_GAIN,
            "deadline_tolerance": DEADLINE_TOLERANCE,
            "default": ALGORITHM_LP,
        },
        "arms": arms,
        "not_selected": not_selected,
        "metric_definitions": METRIC_DEFINITIONS,
        "notes": notes,
        "capacity_ratio": capacity_ratio,
        "capacity_derivation": derivation,
        "runtime_ms": int((time.perf_counter() - started) * 1000),
        "research_reference": research_loader.evaluation_summary(),
    }


def _achievement(arm: dict[str, Any]) -> float:
    return float((arm.get("metrics") or {}).get("weighted_goal_achievement", 0.0) or 0.0)


def _deadline(arm: dict[str, Any]) -> float:
    metrics = arm.get("metrics") or {}
    return float(
        metrics.get("pct_goals_met_by_deadline", metrics.get("weighted_deadline_achievement", 0.0))
        or 0.0
    )


def _static_metrics(result: Any) -> dict[str, Any]:
    summary = result.summary or {}
    return {
        "weighted_goal_achievement": float(summary.get("weighted_goal_achievement", 0.0) or 0.0),
        "total_shortfall": float(summary.get("total_shortfall", 0.0) or 0.0),
        "monthly_contribution_planned": float(
            summary.get("monthly_contributions_allocated", 0.0) or 0.0
        ),
        # Kept for backwards compatibility with stored comparison runs. It is the *planned*
        # figure, not a credited average; `metric_basis` says so.
        "monthly_savings_contribution": float(
            summary.get("monthly_savings_allocated", summary.get("monthly_contributions_allocated", 0.0))
            or 0.0
        ),
        "monthly_investment_contribution": float(
            summary.get("monthly_investment_allocated", 0.0) or 0.0
        ),
        "basis_note": "Static LP plan metrics (no trajectory available for this goal count).",
    }


#: The single vocabulary used by the comparison table. Anything missing from an arm is
#: reported as absent, never as zero.
COMPARABLE_METRICS = (
    "weighted_goal_achievement",
    "pct_goals_met_by_deadline",
    "total_shortfall",
    "monthly_contribution_planned",
    "monthly_contribution_credited_avg",
    "monthly_savings_credited_avg",
    "monthly_investment_credited_avg",
    "unallocated_budget_total",
    "final_cash",
    "final_unearmarked_cash",
    "earmarked_goal_funding",
    "final_portfolio",
    "final_liabilities",
    "net_worth",
    "months_simulated",
)


def _comparable(metrics: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in COMPARABLE_METRICS:
        value = metrics.get(key)
        if value is None and key == "monthly_contribution_planned":
            # Static plans call it monthly_savings_allocated.
            value = metrics.get("monthly_savings_allocated")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            out[key] = round(float(value), 6)
    return out


def _why_not(arm: dict[str, Any], lp_arm: dict[str, Any] | None, recommended: str) -> str:
    if not arm["available"]:
        return (
            f"Not available: {arm.get('fallback_reason') or arm['status']}. No metric is "
            "reported because nothing was evaluated."
        )
    if not arm["feasible"]:
        return "The plan failed constraint validation, so it cannot be recommended."
    if arm["algorithm"] == recommended:
        return "Selected."
    if lp_arm is None:
        return "The LP baseline was not available for comparison."
    gap = _achievement(arm) - _achievement(lp_arm)
    if arm["metric_basis"] != lp_arm["metric_basis"]:
        return (
            "Scored on a different basis from the LP arm, so it is reported for information "
            "only and not ranked."
        )
    if gap < 0:
        return (
            f"Lower weighted goal achievement than the LP ({gap:+.4f}) on the same scenario, "
            "so the LP remains the dependable baseline."
        )
    if gap < MIN_ACHIEVEMENT_GAIN:
        return (
            f"The advantage over the LP ({gap:+.4f}) is inside the "
            f"{MIN_ACHIEVEMENT_GAIN:.2f} materiality margin and is not a demonstrated "
            "improvement."
        )
    return "Beats the LP on achievement but gives up too much deadline success."
