"""RL arm — genuine inference with a trained PPO checkpoint.

This is the piece that did **not** exist before: the research environment consumes
population DataFrames, so an application user had no way in. Here an application user's
persisted profile and goals are mapped onto the environment's schema, the policy is rolled
out on the shared monthly market path, and the trajectory is summarised into the same
metric vocabulary the LP arm uses.

Loaded checkpoint families (all trained under ``GoalPilotConfig.recommended()``):
``training_logs/experiments/ppo_recommended_v1/{archived_v1,candidate_a}/seed{7,17,27}/best/best_model.zip``.

Honesty rules enforced here
---------------------------
* A checkpoint is only used with the configuration it was trained under. The loader
  refuses a mismatch instead of reinterpreting a policy.
* The environment's per-goal action slots are pinned to 5 (the trained width). A user with
  more than 5 goals cannot be served by these checkpoints; the arm returns
  ``status="unavailable"`` with ``fallback_reason="goal_slot_limit"`` and the caller falls
  back to the LP. It never pads, truncates or silently drops a goal.
* Trajectory comparisons are run on a **no-new-borrowing basis**: the loan action dimension
  is zero for every arm, because the environment permits a single active loan while the LP
  proposes one per goal, so no exact mapping exists. Financing is reported separately from
  each arm's static output. This is disclosed in every comparison response.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
import pandas as pd

from app.config import get_settings
from app.core.errors import ValidationFailure
from app.engines import research_loader
from app.engines.common import (
    ALGORITHM_LABELS,
    ALGORITHM_RL,
    ArmResult,
    violation_summary,
)
from app.services.cashflow import CashFlow

#: The trained action width. A checkpoint built with n_goal_slots=5 cannot accept another.
RL_GOAL_SLOTS = 5

RL_MODEL_VERSION = "ppo_recommended_v1@recommended"


@dataclass
class RolloutOutcome:
    metrics: dict[str, Any]
    per_goal: list[dict[str, Any]]
    diagnostics: dict[str, Any]
    violations: list[dict[str, Any]]


def build_profile_row(
    cashflow: CashFlow,
    *,
    investment_capacity_ratio: float,
    risk_score: float,
    user_key: str = "APP_USER_0001",
) -> pd.DataFrame:
    """Map the platform cash-flow object onto the 38-column population schema.

    Only the columns the environment actually reads are populated; the rest are present as
    ``NaN`` so the frame shape matches and nothing is invented. The mapping is recorded in
    the response (see :func:`mapping_notes`).
    """
    columns = [
        "user_id", "monthly_income", "monthly_expenditure", "monthly_emi",
        "initial_savings", "initial_investment", "investment_capacity_ratio", "risk_score",
    ]
    row = {
        "user_id": user_key,
        "monthly_income": float(max(0.0, cashflow.monthly_income)),
        # `monthly_expenditure` is total spending; the environment nets EMI out separately.
        # Discretionary as the environment must see it: real discretionary spending plus the
        # protected buffer, so the policy's available surplus excludes money the user has
        # ring-fenced. The research environment computes surplus as
        # income - expenditure - emi, and never looks at the buffer itself.
        "monthly_expenditure": float(
            max(0.0, cashflow.essential_expenses + cashflow.solver_discretionary())
        ),
        "monthly_emi": float(max(0.0, cashflow.existing_emi)),
        "initial_savings": float(max(0.0, cashflow.liquid_savings)),
        "initial_investment": float(max(0.0, cashflow.usable_existing_investments)),
        "investment_capacity_ratio": float(investment_capacity_ratio),
        "risk_score": float(risk_score),
    }
    return pd.DataFrame([row], columns=columns)


def mapping_notes(cashflow: CashFlow, investment_capacity_ratio: float) -> list[str]:
    return [
        f"monthly_expenditure = essential {cashflow.essential_expenses:,.0f} + "
        f"discretionary {cashflow.discretionary_expenses:,.0f} + protected buffer "
        f"{cashflow.protected_buffer:,.0f}",
        f"monthly_emi = {cashflow.existing_emi:,.0f} (EMI only; principal is never added)",
        f"initial_savings = liquid assets {cashflow.liquid_savings:,.0f}",
        f"initial_investment = usable existing assets {cashflow.usable_existing_investments:,.0f}",
        f"investment_capacity_ratio = {investment_capacity_ratio:.4f} (derived, see lp_engine)",
        f"risk_score = declared risk capacity {cashflow.risk_capacity:.2f}",
    ]


def build_goal_frame(goals: list[Any], months_lookup: dict[int, int], user_key: str) -> pd.DataFrame:
    rows = []
    for goal in goals:
        rows.append(
            {
                "user_id": user_key,
                "goal_id": f"G{goal.id}",
                "goal_name": goal.name,
                "goal_type": goal.goal_type,
                "current_cost": float(goal.current_cost),
                "target_date": goal.target_date.isoformat(),
                "time_horizon_months": int(months_lookup[goal.id]),
                "priority": float(goal.priority),
                "criticality": float(goal.criticality),
                "existing_funding": float(goal.current_funded_amount),
            }
        )
    return pd.DataFrame(rows)


def _weighted_priority_scores(goal_frame: pd.DataFrame) -> np.ndarray:
    months = goal_frame["time_horizon_months"].astype(float).to_numpy()
    horizon_urgency = np.minimum(12.0 / np.maximum(months, 1.0), 2.0)
    scores = (
        np.clip(goal_frame["priority"].astype(float).to_numpy(), 1, 5)
        * np.clip(goal_frame["criticality"].astype(float).to_numpy(), 1, 5)
        * (1 + horizon_urgency)
        / 2
    )
    return scores


def make_env(
    *,
    profile: pd.DataFrame,
    goals: pd.DataFrame,
    market: pd.DataFrame,
    config_preset: str = "recommended",
    seed: int | None = None,
):
    """Instantiate the research environment. Never mutates the research modules."""
    env_module = research_loader.env_module()
    config_module = research_loader.config_module()
    preset = getattr(config_module.GoalPilotConfig, config_preset)()
    preset = preset.replace(n_goal_slots=RL_GOAL_SLOTS)
    return env_module.GoalPilotEnv(
        profile, goals, market, user_ids=profile["user_id"].tolist(), seed=seed, config=preset
    )


def rollout(
    *,
    env,
    action_provider: Callable[[Any, int], np.ndarray],
    label: str,
    max_months: int | None = None,
    borrowing_fractions: np.ndarray | None = None,
) -> RolloutOutcome:
    """Run one full episode, recording per-goal deadline outcomes.

    ``action_provider(env, month_index) -> action`` is called every month, so both a learned
    policy and a static encoded plan can be run through the identical path.

    ``borrowing_fractions`` replays a plan that actually borrows: entry *i* is goal *i*'s EMI as a
    fraction of its EMI budget, which is exactly the environment's own borrowing channel. Passing
    nothing keeps the historical no-new-borrowing basis used to compare arms. Replaying a plan
    that contains a loan without telling the simulator about it understated that plan's result.
    """
    obs, info = env.reset(options={"user_id": env.user_ids[0]})
    n_goals = len(env.user_goals)
    deadlines = np.asarray(env.goal_deadlines, dtype=int)
    targets = np.asarray(env.goal_targets, dtype=float)
    funded_at_deadline = np.zeros(n_goals, dtype=float)
    deadline_recorded = np.zeros(n_goals, dtype=bool)

    months = 0
    total_reward = 0.0
    violations: list[dict[str, Any]] = []
    last_audit: dict[str, Any] = dict(info)

    # The plan is evaluated to the *last goal deadline*, not to the end of the historical market
    # path. Running all 142 market months let a goal due in one month accumulate a decade of
    # surplus and report itself as fully funded, which contradicted its own deadline result.
    last_deadline = int(deadlines.max()) if n_goals else 0
    if max_months is not None:
        limit = max_months
    elif last_deadline > 0:
        limit = min(len(env.market), last_deadline)
    else:
        limit = len(env.market)

    # Per-goal credit, tracked from the balance the environment actually moved. The action's own
    # savings/investment weights split each month's credit between the two channels; under the
    # default face-value credit mode a balance change is contribution, not market gain.
    previous_balances = np.asarray(env.goal_balances, dtype=float).copy()
    savings_credited = np.zeros(n_goals, dtype=float)
    investment_credited = np.zeros(n_goals, dtype=float)
    # The policy's *requested* mix, before the environment caps investment at the capacity
    # ratio. The capped figure cannot serve as a preference signal: it is censored by the very
    # ceiling it would be used to set, so a policy that asked to invest 60% would be read as
    # having asked for the cap instead. These two totals are the uncensored request.
    requested_savings_total = 0.0
    requested_investment_total = 0.0
    invest_requested_total = 0.0
    invest_actual_total = 0.0

    terminated = truncated = False
    while months < limit and not (terminated or truncated):
        action = action_provider(env, months)
        action = np.asarray(action, dtype=np.float32).copy()
        action[:, 2] = 0.0
        if borrowing_fractions is not None:
            fractions = np.asarray(borrowing_fractions, dtype=np.float32).ravel()
            usable = min(n_goals, fractions.size)
            action[:usable, 2] = np.clip(fractions[:usable], 0.0, 1.0)
        raw_savings = np.asarray(action[:n_goals, 0], dtype=float)
        raw_investment = np.asarray(action[:n_goals, 1], dtype=float)
        requested_savings_total += float(raw_savings.sum())
        requested_investment_total += float(raw_investment.sum())
        obs, reward, terminated, truncated, info = env.step(action)
        total_reward += float(reward)
        months += 1
        audit = info.get("budget_audit") if isinstance(info, dict) else None
        if isinstance(audit, dict):
            invest_requested_total += float(audit.get("invest_requested", 0.0) or 0.0)
            invest_actual_total += float(audit.get("investment_contribution", 0.0) or 0.0)

        balances = np.asarray(env.goal_balances, dtype=float)
        credited = np.maximum(0.0, balances - previous_balances)
        previous_balances = balances
        if credited.any():
            weight_total = raw_savings + raw_investment
            investment_share = np.divide(
                raw_investment,
                weight_total,
                out=np.zeros_like(raw_investment),
                where=weight_total > 1e-9,
            )
            investment_credited += credited * investment_share
            savings_credited += credited * (1.0 - investment_share)
        # record any goal that reaches its deadline this month
        due = deadlines == months
        newly = due & ~deadline_recorded
        if newly.any():
            funded_at_deadline[newly] = np.asarray(env.goal_balances, dtype=float)[newly]
            deadline_recorded[newly] = True
        audit = info.get("budget_audit") if isinstance(info, dict) else None
        if isinstance(audit, dict):
            last_audit = audit
            for key, value in audit.items():
                if isinstance(value, (int, float)) and key.endswith(("_residual", "_slack")):
                    if float(value) < -1e-6:
                        violations.append(
                            {
                                "code": "budget_identity",
                                "detail": f"month {months}: {key} = {float(value):.6f}",
                                "amount": float(value),
                            }
                        )
    # goals with deadlines beyond the horizon keep their final balance
    leftover = ~deadline_recorded
    if leftover.any():
        funded_at_deadline[leftover] = np.asarray(env.goal_balances, dtype=float)[leftover]

    final_funded = np.asarray(env.goal_balances, dtype=float)
    scores = _weighted_priority_scores(env.user_goals.reset_index(drop=True))
    total_score = float(scores.sum()) or 1.0

    achievement = np.minimum(final_funded, targets) / np.maximum(targets, 1e-9)
    by_deadline = np.minimum(funded_at_deadline, targets) / np.maximum(targets, 1e-9)
    shortfall = np.maximum(0.0, targets - final_funded)

    per_goal = []
    report = env.goal_level_report()
    for i, row in report.iterrows():
        per_goal.append(
            {
                "goal_ref": str(row["goal_id"]),
                "goal_name": str(row["goal_name"]),
                "target": float(row["target"]),
                # The plan's per-goal figures are on a deadline basis: a goal is met by its
                # target date or it is not. The horizon-end balance is kept separately because
                # the rollout runs far past short-dated goals, and reporting it as "funded" made
                # an unmet goal look fully funded in the allocation table.
                "funded": float(funded_at_deadline[i]),
                "funded_at_horizon": float(row["funded"]),
                "funding_ratio": float(by_deadline[i]),
                "deadline_month": int(row["deadline_month"]),
                "funded_at_deadline": float(funded_at_deadline[i]),
                "deadline_ratio": float(by_deadline[i]),
                "shortfall": float(max(0.0, float(row["target"]) - funded_at_deadline[i])),
                "shortfall_at_horizon": float(shortfall[i]),
                "achievement_ratio": float(by_deadline[i]),
                # The plan's allocation view is the same vocabulary the LP arm uses, so an RL
                # row no longer shows a zero gap and zero contributions next to visible funding.
                "funding_gap": float(
                    max(0.0, float(row["target"]) - float(env.user_goals.iloc[i]["existing_funding"]))
                ),
                # Average credited over the months this goal was actually being funded (up to
                # its deadline), not over the whole episode. Dividing an 18-month goal's
                # contributions by an 84-month horizon understated it by a factor of ~5.
                "monthly_savings_contribution": float(
                    savings_credited[i] / max(1, min(months, int(row["deadline_month"])))
                ),
                "monthly_investment_contribution": float(
                    investment_credited[i] / max(1, min(months, int(row["deadline_month"])))
                ),
                "months_credited": int(max(1, min(months, int(row["deadline_month"])))),
            }
        )

    # Deadline basis is the headline: a goal is met by its target date or it is not, and this is
    # the basis the allocation table and the LP arm use. The horizon-end view is kept alongside
    # (``*_at_horizon``) for research comparison, instead of being the number users see.
    deadline_shortfall = np.maximum(0.0, targets - funded_at_deadline)
    earmarked = float(env.earmarked_goal_funding)
    requested_total = requested_savings_total + requested_investment_total
    monthly_savings_credited = float(env.cumulative_savings_contributions / max(1, months))
    monthly_investment_credited = float(env.cumulative_investment_contributions / max(1, months))
    metrics = {
        "months_simulated": months,
        "weighted_goal_achievement": float((by_deadline * scores).sum() / total_score),
        "weighted_deadline_achievement": float((by_deadline * scores).sum() / total_score),
        "pct_goals_fully_funded": float((by_deadline >= 1 - 1e-6).mean()) if n_goals else 0.0,
        "pct_goals_met_by_deadline": float((by_deadline >= 1 - 1e-6).mean()) if n_goals else 0.0,
        "total_weighted_shortfall": float((deadline_shortfall * scores).sum() / total_score),
        "total_shortfall": float(deadline_shortfall.sum()),
        "weighted_goal_achievement_at_horizon": float((achievement * scores).sum() / total_score),
        "total_shortfall_at_horizon": float(shortfall.sum()),
        # --- contribution metrics -------------------------------------------------------
        # These are *credited* averages: total money the simulator actually moved into the
        # goal accounts, divided by the months simulated. They are not the plan's monthly
        # contribution instruction, and the two differ whenever a goal reaches its cap early
        # or the policy leaves budget unallocated. Both are labelled in `metric_definitions`.
        "monthly_savings_contribution": monthly_savings_credited,
        "monthly_investment_contribution": monthly_investment_credited,
        "monthly_savings_credited_avg": monthly_savings_credited,
        "monthly_investment_credited_avg": monthly_investment_credited,
        "monthly_contribution_credited_avg": monthly_savings_credited + monthly_investment_credited,
        "monthly_contribution_requested_avg": requested_total / max(1, months),
        "requested_investment_fraction": (
            requested_investment_total / requested_total if requested_total > 1e-9 else 0.0
        ),
        "invest_requested_total": float(invest_requested_total),
        "invest_actual_total": float(invest_actual_total),
        "loan_principal": float(env.cumulative_loan_principal),
        "interest_paid": float(env.total_interest_paid),
        "unallocated_budget_total": float(env.total_unallocated_surplus),
        # --- balance-sheet reconciliation ------------------------------------------------
        # In ledger accounting the goal balances are a *memo* subset of cash + portfolio, so
        # they are not added to net worth. `final_cash` therefore contains money already
        # earmarked to goals; `final_unearmarked_cash` is what is genuinely uncommitted.
        "final_cash": float(env.cash),
        "earmarked_goal_funding": earmarked,
        "final_unearmarked_cash": float(max(0.0, float(env.cash) - earmarked)),
        "final_portfolio": float(env.portfolio),
        "final_loan_balance": float(env.loan_balance),
        "final_liabilities": float(env.loan_balance),
        "net_worth": float(env.net_worth),
        "net_worth_gain": float(env.net_worth - env.initial_net_worth),
        "accounting_mode": str(env.config.accounting_mode),
        "total_reward": float(total_reward),
    }
    diagnostics = {
        "label": label,
        "action_mode": env.config.action_mode,
        "accounting_mode": env.config.accounting_mode,
        "goal_credit_mode": env.config.goal_credit_mode,
        "target_basis": env.config.target_basis,
        "annual_inflation": env.config.annual_inflation,
        "emergency_months": env.config.emergency_months,
        "n_goal_slots": env.max_goals,
        "goal_count": n_goals,
        "final_budget_audit": last_audit,
        "financing_disabled_in_rollout": True,
    }
    return RolloutOutcome(metrics, per_goal, diagnostics, violations)


def encode_plan_action(
    *,
    savings_per_goal: list[float],
    investments_per_goal: list[float],
    n_slots: int = RL_GOAL_SLOTS,
) -> np.ndarray:
    """Encode an absolute-rupee plan into the environment's scale-free action contract.

    Reuses the research ``goalpilot_lp_encoder`` so the LP and the RL policy are scored on
    the identical action contract — which is the whole point of the comparison.

    .. warning::
       The action is **positional**. The environment sorts each user's goals by
       ``time_horizon_months`` when it builds ``goal_map``, so a caller that passes
       allocations in the database/UI order will fund the wrong goal. Use
       :func:`encode_plan_for_env`, which maps by goal id to the environment's own slot
       order, for any plan that is replayed through the simulator.
    """
    encoder = research_loader.load_module("lpenc", "goalpilot_lp_encoder")
    encoded = encoder.encode_lp_plan_for_mix(
        np.asarray(savings_per_goal, dtype=float),
        np.asarray(investments_per_goal, dtype=float),
        n_slots=n_slots,
    )
    return encoded["action"]


def env_goal_order(env) -> list[str]:
    """The environment's per-goal slot order, by goal id.

    ``GoalPilotEnv`` sorts a user's goals by ``time_horizon_months`` before assigning action
    slots. Reading that order back is the only safe way to map a plan onto the slots: two
    goals with the same horizon cannot be distinguished positionally, and the research sort
    is not guaranteed stable.
    """
    frame = env.goal_map[env.user_ids[0]]
    return [str(value) for value in frame["goal_id"].tolist()]


def encode_plan_for_env(env, allocations: list[dict[str, Any]]) -> np.ndarray:
    """Encode a plan into the action contract **in the environment's own slot order**.

    The previous implementation assumed the allocation list was already in slot order. It is
    not: goals are loaded by priority (descending) while the environment orders them by
    horizon (ascending), so a plan that funded a 7-year goal could be replayed as if it
    funded an 18-month goal. That goal is then capped once it is funded, the rest of the
    budget becomes unallocated, and the arm is scored on a plan it never proposed.
    """
    order = env_goal_order(env)
    by_ref: dict[str, dict[str, Any]] = {}
    for row in allocations or []:
        for key in (row.get("goal_ref"), row.get("goal_id"), row.get("db_goal_id")):
            if key is not None:
                by_ref[str(key)] = row
    savings: list[float] = []
    investments: list[float] = []
    for ref in order:
        row = by_ref.get(ref)
        if row is None:
            # A goal the plan has no row for contributes nothing; it is not silently mapped
            # onto another goal's money.
            savings.append(0.0)
            investments.append(0.0)
            continue
        savings.append(float(row.get("monthly_savings_contribution", 0.0) or 0.0))
        investments.append(float(row.get("monthly_investment_contribution", 0.0) or 0.0))
    return encode_plan_action(
        savings_per_goal=savings,
        investments_per_goal=investments,
        n_slots=RL_GOAL_SLOTS,
    )


def solve(
    *,
    goals: list[Any],
    cashflow: CashFlow,
    months_lookup: dict[int, int],
    checkpoint_path: str | None = None,
    config_preset: str = "recommended",
    seed: int | None = None,
) -> ArmResult:
    """Load the trained policy and roll it out for this user."""
    started = time.perf_counter()

    if not research_loader.is_available():
        return _unavailable("research_unavailable", "The research project could not be located.")

    if not goals:
        return ArmResult(
            algorithm=ALGORITHM_RL,
            status="infeasible",
            feasible=False,
            warnings=["No active goals were supplied."],
            label=ALGORITHM_LABELS[ALGORITHM_RL],
        )

    if len(goals) > RL_GOAL_SLOTS:
        return _unavailable(
            "goal_slot_limit",
            f"The trained policies have {RL_GOAL_SLOTS} per-goal action slots but this plan "
            f"has {len(goals)} goals. The policy cannot represent this goal set, so the LP "
            "plan is used instead.",
        )

    from app.engines.lp_engine import derive_investment_capacity_ratio

    capacity_ratio, derivation = derive_investment_capacity_ratio(
        risk_capacity=cashflow.risk_capacity,
        liquidity_requirement=getattr(cashflow, "liquidity_requirement", "medium"),
        loss_ability=getattr(cashflow, "loss_ability", "moderate"),
    )
    profile = build_profile_row(
        cashflow, investment_capacity_ratio=capacity_ratio, risk_score=cashflow.risk_capacity
    )
    goal_frame = build_goal_frame(goals, months_lookup, profile["user_id"].iloc[0])

    try:
        market = research_loader.market_frame()
        env = make_env(profile=profile, goals=goal_frame, market=market,
                       config_preset=config_preset, seed=seed)
    except Exception as exc:
        return _unavailable("env_build_failed", f"Could not build the RL environment: {exc}")

    # --- load the policy -----------------------------------------------------------------
    settings_relative = checkpoint_path or None
    ckpt = get_settings().rl_checkpoint_path(settings_relative)
    if ckpt is None:
        return _unavailable(
            "checkpoint_missing",
            f"No PPO checkpoint found at '{settings_relative or get_settings().default_rl_checkpoint}'.",
        )
    if not get_settings().enable_rl:
        return _unavailable("rl_disabled", "RL inference is disabled by configuration.")

    try:
        from stable_baselines3 import PPO

        model = PPO.load(str(ckpt), device="cpu")
    except Exception as exc:
        return _unavailable("checkpoint_load_failed", f"Could not load the PPO checkpoint: {exc}")

    # Guard: never run a policy under semantics it was not trained with.
    if env.config.action_mode != "share":
        return _unavailable(
            "semantics_mismatch",
            f"Checkpoint expects share-mode actions but the environment is in "
            f"'{env.config.action_mode}' mode.",
        )
    observed_shape = tuple(env.action_space.shape)
    policy_shape = tuple(model.action_space.shape)
    if observed_shape != policy_shape:
        return _unavailable(
            "action_space_mismatch",
            f"Checkpoint action space {policy_shape} does not match the environment {observed_shape}.",
        )

    def provider(_env, _month: int) -> np.ndarray:
        action, _ = model.predict(_env._get_observation(), deterministic=True)
        return np.asarray(action, dtype=np.float32)

    try:
        outcome = rollout(env=env, action_provider=provider, label="rl_policy")
    except Exception as exc:
        return ArmResult(
            algorithm=ALGORITHM_RL,
            status="error",
            feasible=False,
            warnings=[f"The rollout failed: {type(exc).__name__}"],
            diagnostics={"error": str(exc)},
            runtime_ms=int((time.perf_counter() - started) * 1000),
            model_version=RL_MODEL_VERSION,
            label=ALGORITHM_LABELS[ALGORITHM_RL],
        )

    warnings = [
        "This is a trained research policy replaying the historical market path. It is not a "
        "forecast and it does not guarantee any outcome.",
        "The research evaluation found that this policy family does not beat a simple "
        "investment rule on goal achievement (0.4842 vs 0.5800 on the held-out cohort). "
        "See the algorithm comparison page.",
        "Financing was disabled in the rollout so every arm is measured on the same basis "
        "(no new borrowing).",
        f"Investment capacity ratio {capacity_ratio:.4f} ({derivation}).",
    ]
    violations = outcome.violations
    feasible = not violations

    warnings = list(warnings)
    deadline_shortfall = float(outcome.metrics.get("total_shortfall", 0.0) or 0.0)
    if deadline_shortfall > 1.0:
        warnings.append(
            "New borrowing is switched off in this arm's replay so every algorithm is compared on "
            "the same basis, so the allocation shows no loan even where one would fit your EMI "
            "ceiling. The alternatives table prices a loan for these goals."
        )

    return ArmResult(
        algorithm=ALGORITHM_RL,
        status="optimal" if feasible else "invalid_plan",
        feasible=feasible,
        allocations=outcome.per_goal,
        summary=outcome.metrics,
        constraints={
            "monthly_surplus": float(max(0.0, cashflow.monthly_surplus)),
            "investment_capacity_ratio": capacity_ratio,
            "available_cash": cashflow.available_cash_for_goals,
        },
        diagnostics={
            **outcome.diagnostics,
            "checkpoint": str(ckpt),
            "profile_mapping": mapping_notes(cashflow, capacity_ratio),
            "validation": violation_summary(violations),
        },
        objective_value=float(outcome.metrics.get("total_reward", 0.0)),
        runtime_ms=int((time.perf_counter() - started) * 1000),
        model_version=RL_MODEL_VERSION,
        config_version=f"{config_preset};slots={RL_GOAL_SLOTS};no_borrowing",
        warnings=warnings,
        label=ALGORITHM_LABELS[ALGORITHM_RL],
    )


def _unavailable(reason: str, message: str) -> ArmResult:
    return ArmResult(
        algorithm=ALGORITHM_RL,
        status="unavailable",
        feasible=False,
        warnings=[message],
        fallback_reason=reason,
        model_version=RL_MODEL_VERSION,
        label=ALGORITHM_LABELS[ALGORITHM_RL],
    )


def list_available_checkpoints() -> list[dict[str, Any]]:
    return research_loader.list_checkpoints()


def readiness() -> dict[str, Any]:
    settings = get_settings()
    if not research_loader.is_available():
        return {"available": False, "reason": "research_unavailable"}
    try:
        env_module = research_loader.env_module()  # noqa: F401
        config_module = research_loader.config_module()  # noqa: F401
    except Exception as exc:
        return {"available": False, "reason": f"import_failed: {exc}"}
    try:
        import stable_baselines3  # noqa: F401
    except Exception as exc:
        return {"available": False, "reason": f"stable_baselines3_unavailable: {exc}"}
    checkpoint = settings.rl_checkpoint_path()
    return {
        "available": checkpoint is not None and settings.enable_rl,
        "enabled": settings.enable_rl,
        "checkpoint": str(checkpoint) if checkpoint else None,
        "goal_slots": RL_GOAL_SLOTS,
        "preset": "recommended",
        "checkpoint_count": len(list_available_checkpoints()),
        "reason": None if checkpoint else "checkpoint_missing",
    }


def baseline_uniform_savings(goals: list[Any]) -> np.ndarray:
    """Equal savings weight on every slot, no investment, no borrowing.

    A deliberately simple rule so the comparison always has an interpretable floor.
    """
    action = np.zeros((RL_GOAL_SLOTS, 3), dtype=np.float32)
    n = min(len(goals), RL_GOAL_SLOTS)
    if n:
        action[:n, 0] = 1.0
    return action
