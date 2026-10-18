"""Smoke-test the model integration layer without the web app.

Run from the backend directory:

    python ..\\scripts\\smoke_engines.py

Uses a synthetic profile clearly marked as synthetic. Exits non-zero on failure.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from dataclasses import dataclass
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from app.engines import hybrid_engine, lp_engine, research_loader, rl_engine, selector  # noqa: E402
from app.services.cashflow import build_cashflow  # noqa: E402
from app.services.goals import project_goals  # noqa: E402
from app.services.money import months_between  # noqa: E402


@dataclass
class StubGoal:
    id: int
    name: str
    goal_type: str
    current_cost: float
    target_date: dt.date
    current_funded_amount: float
    priority: int
    criticality: int
    date_flexible: bool = True
    amount_flexible: bool = False


@dataclass
class StubIncome:
    amount: float
    frequency: str = "monthly"
    monthly_equivalent: float = 0.0
    is_active: bool = True


@dataclass
class StubLiability:
    emi_amount: float
    outstanding_principal: float


@dataclass
class StubAsset:
    current_value: float
    asset_type: str = "liquid_savings"
    is_liquid: bool = True
    usable_for_goals: bool = True


def main() -> int:
    print("=== research status ===")
    status = research_loader.status()
    print(json.dumps(status.as_dict(), indent=2, default=str))

    today = dt.date.today()
    goals = [
        StubGoal(1, "Professional certification", "education", 90_000, today + dt.timedelta(days=365), 10_000, 4, 5),
        StubGoal(2, "Vehicle down payment", "vehicle", 300_000, today + dt.timedelta(days=1095), 50_000, 3, 3),
        StubGoal(3, "Emergency fund top-up", "emergency", 200_000, today + dt.timedelta(days=730), 20_000, 5, 5),
    ]
    income = [StubIncome(amount=90_000, monthly_equivalent=90_000)]
    liabilities = [StubLiability(emi_amount=12_000, outstanding_principal=600_000)]
    assets = [StubAsset(current_value=420_000)]

    cf = build_cashflow(
        income_sources=income,
        liabilities=liabilities,
        assets=assets,
        expense_items=[
            {"category": "housing", "amount": 22_000},
            {"category": "food_groceries", "amount": 12_000},
            {"category": "utilities", "amount": 4_000},
            {"category": "transport", "amount": 4_000},
            {"category": "entertainment", "amount": 6_000, "classification": "discretionary"},
        ],
        emergency_months=6,
        emi_income_ratio_cap=0.35,
        risk_capacity=0.55,
        savings_target=15_000,
    )
    print("\n=== cash flow ===")
    print(json.dumps({k: round(v, 2) if isinstance(v, float) else v
                      for k, v in cf.as_dict().items() if k != "warnings"}, indent=2))
    print("warnings:", cf.warnings)

    print("\n=== goal projections (no plan yet) ===")
    projections = project_goals(
        goals,
        inflation=0.03,
        savings_return=0.0,
        investment_return=0.05,
        monthly_surplus=cf.monthly_surplus,
        available_cash=cf.available_cash_for_goals,
    )
    for p in projections:
        print(f"  {p.name:28s} gap={p.remaining_gap:12,.0f} required/mo={p.required_monthly_contribution:10,.0f} "
              f"feasibility={p.feasibility}")

    months_lookup = {g.id: max(1, months_between(today, g.target_date)) for g in goals}

    print("\n=== LP (capacity-constrained) ===")
    lp = lp_engine.solve(goals=goals, cashflow=cf)
    print("status:", lp.status, "feasible:", lp.feasible, "runtime_ms:", lp.runtime_ms)
    print("model_version:", lp.model_version)
    print("summary:", json.dumps(lp.summary, indent=2, default=str)[:1200])
    print("validation:", json.dumps(lp.diagnostics.get("validation"), indent=2, default=str))
    for w in lp.warnings:
        print("  warn:", w)

    print("\n=== RL (PPO checkpoint) ===")
    rl = rl_engine.solve(goals=goals, cashflow=cf, months_lookup=months_lookup)
    print("status:", rl.status, "feasible:", rl.feasible, "runtime_ms:", rl.runtime_ms)
    print("fallback_reason:", rl.fallback_reason)
    print("metrics:", json.dumps(rl.summary, indent=2, default=str)[:1200])

    print("\n=== HYBRID ===")
    hyb = hybrid_engine.solve(goals=goals, cashflow=cf, months_lookup=months_lookup)
    print("status:", hyb.status, "feasible:", hyb.feasible, "runtime_ms:", hyb.runtime_ms)
    print("theta:", json.dumps(hyb.diagnostics.get("theta"), indent=2, default=str))
    print("metrics:", json.dumps(hyb.summary, indent=2, default=str)[:900])

    print("\n=== SELECTOR ===")
    comparison = selector.compare(goals=goals, cashflow=cf, months_lookup=months_lookup)
    print("recommended:", comparison["recommended_algorithm"])
    print("reason:", comparison["recommendation_reason"])
    print("sufficient_evidence:", comparison["sufficient_evidence_for_change"])
    for arm in comparison["arms"]:
        m = arm.get("metrics") or {}
        print(f"  {arm['algorithm']:16s} status={arm['status']:12s} basis={arm['metric_basis']:12s} "
              f"ach={float(m.get('weighted_goal_achievement', 0)):.4f} "
              f"deadline={float(m.get('pct_goals_met_by_deadline', 0)):.4f}")
    for n in comparison["notes"]:
        print("  note:", n)

    print("\nSMOKE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
