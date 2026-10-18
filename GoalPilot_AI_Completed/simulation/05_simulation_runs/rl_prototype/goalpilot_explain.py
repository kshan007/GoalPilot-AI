"""Explainable recommendation engine (Phase I).

The system has three layers that must never be conflated:

1. **Financial calculations** - produced by the simulator (:mod:`goalpilot_env`). Every rupee
   figure in an explanation comes from here.
2. **Optimisation / policy decisions** - the LP plan or the RL action sequence that was executed.
3. **General financial education** - the uncited principles in :mod:`goalpilot_knowledge`.

This module builds an explanation *strictly* from (1) plus the identity of (2), and attaches
(3) only as clearly-labelled general principle, never as a personalised guarantee. It never
reads a future return, a future goal requirement or any simulator outcome that was not
available at the decision date: the explanation is produced *after* a rollout, from the
recorded per-month ledger.

Public API
----------
``rollout(env, action_fn, uid)``
    Execute ``action_fn`` for one user and record the full monthly ledger.
``explain(env, uid, action_fn, kb=...)``
    Return a structured explanation dict (facts, why, shortfalls, sensitivity hooks, risks).
``sensitivity(profiles, goals, market, uid, config, action_fn, variants)``
    Deterministic what-if re-runs under perturbed market-return or investment-capacity
    assumptions, reported as changes against the unperturbed baseline.
``render_markdown(explanation)``
    Human-readable rendering of an explanation dict.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable

import numpy as np
import pandas as pd

from goalpilot_knowledge import DEFAULT_KB, KnowledgeBase

ActionFn = Callable[[object], np.ndarray]


# ----------------------------------------------------------------------------------------
# rollout
# ----------------------------------------------------------------------------------------
@dataclass
class RolloutResult:
    user_id: str
    months: int
    monthly: list[dict] = field(default_factory=list)
    total_reward: float = 0.0
    capacity_binding_months: int = 0
    max_budget_residual: float = 0.0
    affordability_violations: int = 0
    goal_balances: np.ndarray | None = None
    goal_targets: np.ndarray | None = None
    goal_deadlines: np.ndarray | None = None
    final: dict = field(default_factory=dict)


def rollout(env, action_fn: ActionFn, uid: str) -> RolloutResult:
    """Run one episode for ``uid`` and record the per-month ledger."""
    env.reset(options={"user_id": uid})
    res = RolloutResult(user_id=uid, months=0)
    while True:
        action = action_fn(env)
        obs, reward, term, trunc, info = env.step(action)
        ba = info["budget_audit"]
        cap_bind = bool(ba.get("invest_overflow", 0.0) > 1e-9
                        or ba.get("unallocated_from_investment_cap", 0.0) > 1e-9)
        res.capacity_binding_months += int(cap_bind)
        res.max_budget_residual = max(res.max_budget_residual, abs(float(ba["budget_check"])))
        if ba.get("cash_floor_active") or ba.get("interest_shortfall", 0.0) > 1e-9:
            res.affordability_violations += 1
        res.monthly.append({
            "month": int(ba["month"]),
            "income": float(ba["income"]),
            "expenses": float(ba["expenses"]),
            "existing_emi": float(ba["profile_existing_emi"]),
            "surplus": float(ba["surplus"]),
            "discretionary_budget": float(ba["discretionary_budget"]),
            "savings_contribution": float(ba["savings_contribution"]),
            "investment_contribution": float(ba["investment_contribution"]),
            "invest_requested": float(ba.get("invest_requested", 0.0)),
            "invest_actual": float(ba.get("invest_actual", 0.0)),
            "invest_overflow": float(ba.get("invest_overflow", 0.0)),
            "unallocated_surplus": float(ba.get("unallocated_surplus", 0.0)),
            "released_by_goal_cap": float(ba.get("released_by_goal_cap", 0.0)),
            "interest_paid_cash": float(ba.get("interest_paid_cash", 0.0)),
            "new_loan_principal": float(info.get("new_loan_principal", 0.0)),
            "reward": float(reward),
            "cash": float(info["ledger"]["cash"]),
            "portfolio": float(info["portfolio_value"]),
            "net_worth": float(info["net_worth"]),
            "restricted_cash": float(info.get("restricted_cash", 0.0)),
        })
        res.total_reward += float(reward)
        res.months += 1
        if term or trunc:
            break
    res.goal_balances = np.asarray(env.goal_balances, dtype=float).copy()
    res.goal_targets = np.asarray(env.goal_targets, dtype=float).copy()
    res.goal_deadlines = np.asarray(env.goal_deadlines, dtype=float).copy()
    res.final = {
        "cash": float(env.cash),
        "portfolio": float(env.portfolio),
        "loan_balance": float(env.loan_balance),
        "net_worth": float(env.net_worth),
        "earmarked_goal_funding": float(env.earmarked_goal_funding),
        "cumulative_loan_principal": float(env.cumulative_loan_principal),
        "total_interest_paid": float(env.total_interest_paid),
        "total_investment_gain": float(env.total_investment_gain),
        "total_unallocated_surplus": float(env.total_unallocated_surplus),
    }
    return res


# ----------------------------------------------------------------------------------------
# facts
# ----------------------------------------------------------------------------------------
def build_facts(env, res: RolloutResult) -> dict:
    """Every number the explanation is allowed to use, derived from recorded state."""
    uid = res.user_id
    prof = env.profile_map[uid]
    goals = env.user_goals
    n = len(goals)
    target = res.goal_targets[:n]
    funded = res.goal_balances[:n]
    ratio = np.minimum(funded, target) / np.maximum(target, 1e-9)
    pri = goals["priority"].astype(float).to_numpy()[:n]
    weighted = float(np.sum(pri * ratio) / max(pri.sum(), 1e-9))
    deadline_month = res.goal_deadlines[:n]

    goal_rows = []
    for j in range(n):
        goal_rows.append({
            "goal_id": str(goals["goal_id"].iat[j]),
            "goal_name": str(goals["goal_name"].iat[j]),
            "priority": float(pri[j]),
            "deadline_month": int(deadline_month[j]),
            "target": float(target[j]),
            "funded": float(funded[j]),
            "shortfall": float(max(0.0, target[j] - funded[j])),
            "funding_ratio": float(ratio[j]),
        })

    monthly = pd.DataFrame(res.monthly)
    facts = {
        "user_id": uid,
        "profile": {
            "monthly_income": float(prof["monthly_income"]),
            "essential_expenses": float(prof["monthly_expenditure"]),
            "existing_emi": float(prof["monthly_emi"]),
            "investable_surplus": float(prof["monthly_income"] - prof["monthly_expenditure"]
                                        - prof["monthly_emi"]),
            "initial_savings": float(prof["initial_savings"]),
            "initial_investment": float(prof["initial_investment"]),
            "investment_capacity_ratio": float(prof["investment_capacity_ratio"]),
            "risk_score": float(prof["risk_score"]),
            "risk_profile": str(prof["risk_profile"]),
            "financial_situation": str(prof.get("financial_situation", "")),
        },
        "goals": goal_rows,
        "totals": {
            "n_goals": n,
            "total_target": float(target.sum()),
            "total_funded": float(np.minimum(funded, target).sum()),
            "total_shortfall": float(np.maximum(0.0, target - funded).sum()),
            "weighted_achievement": weighted,
            "pct_goals_fully_funded": float(np.mean(ratio >= 1.0 - 1e-9)),
        },
        "execution": {
            "months": res.months,
            "total_savings_contribution": float(monthly["savings_contribution"].sum()),
            "total_investment_contribution": float(monthly["investment_contribution"].sum()),
            "total_invest_requested": float(monthly["invest_requested"].sum()),
            "total_invest_executed": float(monthly["invest_actual"].sum()),
            "total_invest_overflow": float(monthly["invest_overflow"].sum()),
            "capacity_binding_months": int(res.capacity_binding_months),
            "total_unallocated": float(monthly["unallocated_surplus"].sum()),
            "released_by_goal_cap": float(monthly["released_by_goal_cap"].sum()),
            "max_budget_residual": float(res.max_budget_residual),
            "affordability_violations": int(res.affordability_violations),
        },
        "balance_sheet": dict(res.final),
        "borrowing": {
            "cumulative_loan_principal": float(res.final["cumulative_loan_principal"]),
            "total_interest_paid": float(res.final["total_interest_paid"]),
            "loan_balance": float(res.final["loan_balance"]),
        },
    }
    return facts


# ----------------------------------------------------------------------------------------
# explanation
# ----------------------------------------------------------------------------------------
def _why_this_allocation(facts: dict) -> list[str]:
    out: list[str] = []
    ex = facts["execution"]
    tot = facts["totals"]
    cap = facts["profile"]["investment_capacity_ratio"]
    surplus = facts["profile"]["investable_surplus"]

    out.append(
        f"The plan could allocate from a monthly investable surplus of "
        f"{surplus:,.0f}; across {ex['months']} months it executed "
        f"{ex['total_savings_contribution']:,.0f} of savings and "
        f"{ex['total_invest_executed']:,.0f} of investment contributions.")
    if ex["capacity_binding_months"] > 0:
        out.append(
            f"The investment-ceiling was binding in {ex['capacity_binding_months']} of "
            f"{ex['months']} months: of {ex['total_invest_requested']:,.0f} requested, "
            f"{ex['total_invest_overflow']:,.0f} could not be invested and was handled by the "
            f"configured overflow policy. The ceiling is "
            f"{cap:.4f} x the surplus available after loan commitments.")
    else:
        out.append(
            f"The investment ceiling ({cap:.4f} of available surplus) never bound, so no "
            f"requested investment was refused by the capacity rule.")
    if ex["total_unallocated"] > 1e-6:
        out.append(
            f"{ex['total_unallocated']:,.0f} of surplus was left unallocated over the horizon.")
    if ex["released_by_goal_cap"] > 1e-6:
        out.append(
            f"{ex['released_by_goal_cap']:,.0f} of budget was released by per-goal caps once a "
            f"goal reached its target. In this configuration that released budget is not "
            f"reallocated to goals that still have need (finding R-13), so it is the same money "
            f"reported above as unallocated surplus - the two figures are not additive.")
    out.append(
        f"Contributions were directed to goals in priority order until each goal's remaining "
        f"need was met; the weighted achievement across all goals is "
        f"{tot['weighted_achievement']:.4f}, i.e. "
        f"{100 * tot['weighted_achievement']:.1f}% of the priority-weighted target.")
    return out


def _why_others_less(facts: dict) -> list[str]:
    out: list[str] = []
    goals = sorted(facts["goals"], key=lambda g: g["funding_ratio"])
    under = [g for g in goals if g["funding_ratio"] < 1.0 - 1e-9]
    if not under:
        return ["Every goal reached its target, so no goal had to be funded less than another."]
    for g in under[:3]:
        out.append(
            f"`{g['goal_name']}` ({g['goal_id']}) received "
            f"{100 * g['funding_ratio']:.1f}% of its inflated target "
            f"({g['funded']:,.0f} of {g['target']:,.0f}; shortfall {g['shortfall']:,.0f}). "
            f"It has priority {g['priority']:.0f} and a deadline in month "
            f"{g['deadline_month']}, so it competes for the same finite monthly surplus as the "
            f"higher-priority or nearer goals.")
    met = [g for g in facts["goals"] if g["funding_ratio"] >= 1.0 - 1e-9]
    if met:
        out.append(
            f"Goals that reached their target: "
            f"{', '.join('`' + g['goal_name'] + '`' for g in met[:5])}"
            f"{' …' if len(met) > 5 else ''}.")
    out.append(
        "Priority and deadline ordering, not the savings/investment mix alone, is what decides "
        "which goals are filled first; a goal funded less than another is a trade-off against "
        "the same monthly budget, not a modelling error.")
    return out


def _explain_shortfalls(facts: dict) -> list[str]:
    out: list[str] = []
    tot = facts["totals"]
    if tot["total_shortfall"] <= 1e-6:
        return ["No goal shortfall: every goal was fully funded within the horizon."]
    out.append(
        f"Total shortfall across goals is {tot['total_shortfall']:,.0f} "
        f"({100 * (1 - tot['weighted_achievement']):.1f}% of the priority-weighted target).")
    feasi = facts["profile"]["investable_surplus"]
    if feasi <= 0:
        out.append(
            f"The profile is structurally infeasible: after essential expenses "
            f"({facts['profile']['essential_expenses']:,.0f}) and existing loan service "
            f"({facts['profile']['existing_emi']:,.0f}) it has no positive investable surplus "
            f"({feasi:,.0f}). No allocation policy - LP, rule-based or RL - can fund these "
            f"goals from cash flow; the shortfall is a capacity fact, not a policy failure.")
    else:
        out.append(
            f"A positive surplus of {feasi:,.0f}/month exists, so the shortfall reflects the "
            f"goals being large relative to available cash flow and the horizon, not the "
            f"absence of surplus.")
    return out


def _risk_and_borrowing(facts: dict) -> list[str]:
    out: list[str] = []
    b = facts["borrowing"]
    bs = facts["balance_sheet"]
    if b["cumulative_loan_principal"] > 1e-6:
        out.append(
            f"The plan originated {b['cumulative_loan_principal']:,.0f} of loan principal and "
            f"paid {b['total_interest_paid']:,.0f} of cash interest. Interest is a certain "
            f"cost; it is only worth taking if it brings forward funding that would otherwise "
            f"miss a deadline.")
    else:
        out.append("No new borrowing was used, so no interest cost was incurred.")
    out.append(
        f"Final balance sheet: cash {bs['cash']:,.0f} (including restricted emergency cash "
        f"held inside the cash balance), portfolio {bs['portfolio']:,.0f}, loan balance "
        f"{bs['loan_balance']:,.0f}, net worth {bs['net_worth']:,.0f}.")
    out.append(
        f"Investment gain realised over the horizon: {bs['total_investment_gain']:,.0f}. "
        f"This is a realised path outcome, not a forecast.")
    out.append(
        f"Earmarked goal funding is {bs['earmarked_goal_funding']:,.0f}. This is a *memo* total "
        f"- a subset of assets already counted in net worth - and must never be added to net "
        f"worth (that was finding F-04).")
    return out


def _sensitivity_statements(facts: dict, sensitivity: dict | None) -> list[str]:
    if not sensitivity:
        return ["No sensitivity scenarios were run for this explanation."]
    out = []
    base = sensitivity["baseline"]["weighted_achievement"]
    for v in sensitivity["variants"]:
        d = v["weighted_achievement"] - base
        out.append(
            f"Under `{v['name']}` the weighted achievement becomes "
            f"{v['weighted_achievement']:.4f} (change {d:+.4f} vs the "
            f"{base:.4f} baseline); shortfall "
            f"{v['total_shortfall'] - sensitivity['baseline']['total_shortfall']:+,.0f}.")
    out.append("These are deterministic what-if re-runs under changed assumptions, not "
               "forecasts, and they show the recommendation is conditional on them.")
    return out


def explain(env, uid: str, action_fn: ActionFn, *, kb: KnowledgeBase = DEFAULT_KB,
            sensitivity: dict | None = None, principles_k: int = 3) -> dict:
    """Produce a structured, grounded explanation for one executed rollout."""
    res = rollout(env, action_fn, uid)
    facts = build_facts(env, res)

    queries = ["emergency reserve", "goal horizon risk volatility",
               "inflation goal cost", "debt loan interest emi affordability",
               "investment capacity surplus", "conflicting goal priority trade-off",
               "historical returns not guaranteed", "earmark net worth double count"]
    cited: list[dict] = []
    seen: set[str] = set()
    for q in queries:
        for p in kb.retrieve(q, k=1):
            if p.id not in seen:
                seen.add(p.id)
                cited.append({"id": p.id, "topic": p.topic, "text": p.text,
                              "status": p.status})

    explanation = {
        "user_id": uid,
        "facts": facts,
        "sections": {
            "goals_and_constraints": [
                f"{facts['totals']['n_goals']} goals with a combined inflated target of "
                f"{facts['totals']['total_target']:,.0f}.",
                f"Monthly income {facts['profile']['monthly_income']:,.0f}, essential "
                f"expenses {facts['profile']['essential_expenses']:,.0f}, existing loan "
                f"service {facts['profile']['existing_emi']:,.0f}, leaving an investable "
                f"surplus of {facts['profile']['investable_surplus']:,.0f}.",
                f"Declared risk profile `{facts['profile']['risk_profile']}` "
                f"(score {facts['profile']['risk_score']:.2f}) and an investment-capacity "
                f"ratio of {facts['profile']['investment_capacity_ratio']:.4f}. The capacity "
                f"ratio is an affordability ceiling in the simulator, not a validated "
                f"risk-suitability measure.",
            ],
            "why_this_allocation": _why_this_allocation(facts),
            "why_others_received_less": _why_others_less(facts),
            "expected_shortfalls_and_deadline_risk": _explain_shortfalls(facts),
            "role_of_savings_returns_and_borrowing": _risk_and_borrowing(facts),
            "sensitivity": _sensitivity_statements(facts, sensitivity),
            "what_could_change_the_result": [
                "A change in realised market returns, because goal funding here is credited "
                "from realised portfolio revaluation, not a projected return.",
                "A change in the investment-capacity assumption, which bounds how much of the "
                "surplus can be invested at all.",
                "A change in income, essential expenses or existing debt service, which moves "
                "the investable surplus and therefore every allocation.",
                "A change in goal amounts, deadlines or priorities, which reorders the "
                "trade-off among goals.",
            ],
        },
        "grounding": {
            "source": "simulated state (goalpilot_env), recorded per month",
            "numbers_are": "computed, not forecast",
            "principles": cited,
            "principles_note": ("General, uncited financial principles compiled for this "
                                "project. They are not quotations from NISM or any other body "
                                "and are not personalised advice."),
        },
    }
    return explanation


# ----------------------------------------------------------------------------------------
# sensitivity
# ----------------------------------------------------------------------------------------
@dataclass
class Variant:
    name: str
    capacity_multiplier: float = 1.0
    nifty_multiplier: float = 1.0


def sensitivity(profiles, goals, market, uid: str, config, action_fn: ActionFn,
                variants: Iterable[Variant]) -> dict:
    """Deterministic what-if re-runs under perturbed capacity / market-return assumptions.

    Only the named assumption is perturbed; goals, deadlines, reserves and the policy are held
    fixed, so the reported differences are attributable to that assumption alone.
    """
    import goalpilot_env  # local import so the module stays importable without the env

    def run(prof_df, mkt_df) -> dict:
        env = goalpilot_env.GoalPilotEnv(profiles=prof_df, goals=goals, market=mkt_df,
                                        user_ids=[uid], config=config)
        res = rollout(env, action_fn, uid)
        f = build_facts(env, res)
        return {"weighted_achievement": f["totals"]["weighted_achievement"],
                "total_shortfall": f["totals"]["total_shortfall"],
                "pct_goals_fully_funded": f["totals"]["pct_goals_fully_funded"],
                "net_worth": f["balance_sheet"]["net_worth"],
                "total_invest_executed": f["execution"]["total_invest_executed"],
                "capacity_binding_months": f["execution"]["capacity_binding_months"]}

    baseline = run(profiles, market)
    out = []
    for v in variants:
        prof_df = profiles.copy()
        if v.capacity_multiplier != 1.0:
            mask = prof_df["user_id"].astype(str) == uid
            prof_df.loc[mask, "investment_capacity_ratio"] = (
                prof_df.loc[mask, "investment_capacity_ratio"].astype(float)
                * v.capacity_multiplier).clip(lower=0.0, upper=1.0)
        mkt_df = market.copy()
        if v.nifty_multiplier != 1.0:
            mkt_df["nifty_monthly_return"] = (mkt_df["nifty_monthly_return"].astype(float)
                                              * v.nifty_multiplier)
        r = run(prof_df, mkt_df)
        r["name"] = v.name
        out.append(r)
    return {"baseline": baseline, "variants": out}


# ----------------------------------------------------------------------------------------
# rendering
# ----------------------------------------------------------------------------------------
def render_markdown(explanation: dict) -> str:
    f = explanation["facts"]
    L = [f"# Explanation - {explanation['user_id']}", "",
         f"_Source: {explanation['grounding']['source']}; numbers are "
         f"{explanation['grounding']['numbers_are']}._", ""]
    titles = {
        "goals_and_constraints": "Goals and constraints",
        "why_this_allocation": "Why this allocation",
        "why_others_received_less": "Why other goals received less",
        "expected_shortfalls_and_deadline_risk": "Expected shortfalls and deadline risk",
        "role_of_savings_returns_and_borrowing": "Savings, returns and borrowing",
        "sensitivity": "Sensitivity to assumptions",
        "what_could_change_the_result": "What could change the result",
    }
    for key, title in titles.items():
        L.append(f"## {title}")
        for s in explanation["sections"][key]:
            L.append(f"- {s}")
        L.append("")
    L.append("## General principles referenced")
    L.append("")
    for p in explanation["grounding"]["principles"]:
        L.append(f"- **{p['topic']}** ({p['id']}, {p['status']}): {p['text']}")
    L += ["", f"_{explanation['grounding']['principles_note']}_", ""]
    L.append("## Goal detail")
    L.append("")
    L.append("| goal | priority | deadline (mo) | target | funded | ratio | shortfall |")
    L.append("|---|---:|---:|---:|---:|---:|---:|")
    for g in f["goals"]:
        L.append(f"| {g['goal_name']} | {g['priority']:.0f} | {g['deadline_month']} | "
                 f"{g['target']:,.0f} | {g['funded']:,.0f} | {100*g['funding_ratio']:.1f}% | "
                 f"{g['shortfall']:,.0f} |")
    return "\n".join(L)
