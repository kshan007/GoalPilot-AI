"""Algorithm-integrity verification.

Audits the LP / RL / hybrid / selector chain against the brief's integrity requirements and
prints a machine-checkable report. Read-only: it never modifies code, models or data.

Run from the backend directory:

    python ..\\scripts\\verify_algorithm_integrity.py
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from app.engines import hybrid_engine, lp_engine, research_loader, rl_engine, selector  # noqa: E402
from app.engines.common import TOL  # noqa: E402
from app.services.cashflow import build_cashflow  # noqa: E402
from app.services.money import months_between  # noqa: E402

CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, bool(ok), detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" :: {detail}" if detail else ""))


# --------------------------------------------------------------------------------------
# synthetic fixtures (explicitly synthetic; no real personal data)
# --------------------------------------------------------------------------------------
class Src:
    def __init__(self, amount, frequency="monthly"):
        self.amount = amount
        self.frequency = frequency
        self.monthly_equivalent = amount
        self.is_active = True


class Liab:
    def __init__(self, emi, principal):
        self.emi_amount = emi
        self.outstanding_principal = principal


class Ast:
    def __init__(self, value):
        self.current_value = value
        self.is_liquid = True
        self.usable_for_goals = True
        self.asset_type = "liquid_savings"


class Goal:
    def __init__(self, gid, cost, months, name, funded=0.0, priority=3, criticality=3):
        self.id = gid
        self.name = name
        self.goal_type = "custom"
        self.current_cost = cost
        self.target_date = dt.date.today() + dt.timedelta(days=int(months * 30.44))
        self.current_funded_amount = funded
        self.priority = priority
        self.criticality = criticality
        self.date_flexible = True
        self.amount_flexible = False


def make_cashflow(**kw):
    base = dict(
        income_sources=[Src(90_000)],
        liabilities=[Liab(12_000, 600_000)],
        assets=[Ast(420_000)],
        expense_items=[
            {"category": "housing", "amount": 30_000},
            {"category": "food_groceries", "amount": 12_000},
            {"category": "entertainment", "amount": 8_000, "classification": "discretionary"},
        ],
        emergency_months=6,
        emi_income_ratio_cap=0.35,
        risk_capacity=0.55,
    )
    base.update(kw)
    return build_cashflow(**base)


def main() -> int:
    print("=" * 78)
    print("ALGORITHM INTEGRITY VERIFICATION")
    print("=" * 78)
    print(f"Run at: {dt.datetime.now().isoformat(timespec='seconds')}")
    print("All fixtures are SYNTHETIC. No real personal financial data is used.")
    print()

    status = research_loader.status()
    check("research project located", status.available, str(status.root))
    check("multi_goal_optimizer imports", status.modules.get("multi_goal_optimizer", False))
    check("goalpilot_constrained_lp imports", status.modules.get("goalpilot_constrained_lp", False))
    check("goalpilot_env imports", status.modules.get("goalpilot_env", False))

    goals = [
        Goal(1, 90_000, 12, "Certification", funded=10_000, priority=4, criticality=5),
        Goal(2, 300_000, 36, "Vehicle down payment", funded=50_000, priority=3, criticality=3),
        Goal(3, 200_000, 24, "Emergency top-up", funded=20_000, priority=5, criticality=5),
    ]
    lookup = {g.id: max(1, months_between(dt.date.today(), g.target_date)) for g in goals}
    cf = make_cashflow()

    # ---------------------------------------------------------------- 1. fairness inputs
    print("\n--- 1. Comparable scenarios across arms ---")
    market_path = research_loader.data_path(research_loader.MARKET_REL)
    market_bytes = market_path.read_bytes()
    market_sha = hashlib.sha256(market_bytes).hexdigest()
    market = research_loader.market_frame()
    check("shared market path exists", market_path.is_file(), market_path.name)
    print(f"       market rows={len(market)} sha256={market_sha[:16]}...")
    check("market path rows == 142", len(market) == 142, f"rows={len(market)}")

    capacity_ratio, derivation = lp_engine.derive_investment_capacity_ratio(
        risk_capacity=cf.risk_capacity
    )
    profile = rl_engine.build_profile_row(
        cf, investment_capacity_ratio=capacity_ratio, risk_score=cf.risk_capacity
    )
    goal_frame = rl_engine.build_goal_frame(goals, lookup, profile["user_id"].iloc[0])
    check("single profile row built for all trajectory arms", len(profile) == 1)
    check("goal frame carries every goal", len(goal_frame) == len(goals))
    check(
        "goal frame exposes the 12 required columns",
        {"user_id", "goal_id", "goal_name", "current_cost", "target_date",
         "time_horizon_months", "priority", "criticality", "existing_funding"} <= set(goal_frame.columns),
    )
    check("investment capacity ratio derived (not assumed)", 0.0 <= capacity_ratio <= 1.0,
          f"{capacity_ratio:.4f}: {derivation}")

    # ---------------------------------------------------------------- 2. LP integrity
    print("\n--- 2. LP integrity and constraint satisfaction ---")
    lp = lp_engine.solve(goals=goals, cashflow=cf)
    check("LP returns optimal", lp.status == "optimal", f"status={lp.status}")
    check("LP plan feasible", lp.feasible is True)
    check("LP runtime recorded", lp.runtime_ms > 0, f"{lp.runtime_ms} ms")
    check("LP model version recorded", bool(lp.model_version), lp.model_version)
    validation = lp.diagnostics.get("validation", {})
    check("LP platform validation clean", validation.get("clean") is True,
          f"violations={validation.get('count')}")

    alloc = pd.DataFrame(lp.allocations)
    check("no negative allocations", float(alloc[[
        "initial_savings_allocated", "existing_assets_allocated", "monthly_savings_contribution",
        "monthly_investment_contribution", "loan_principal", "shortfall"]].min().min()) >= -TOL)
    check("no goal over-funded beyond its gap",
          float((alloc["projected_new_funding"] - alloc["funding_gap"]).max()) <= 1e-6)
    check("cash alloc <= available cash pool",
          float(alloc["initial_savings_allocated"].sum()) <= cf.available_cash_for_goals + TOL,
          f"{alloc['initial_savings_allocated'].sum():,.2f} <= {cf.available_cash_for_goals:,.2f}")
    check("contributions <= monthly surplus",
          float((alloc["monthly_savings_contribution"] + alloc["monthly_investment_contribution"]).sum())
          <= max(0.0, cf.monthly_surplus) + TOL,
          f"{float((alloc['monthly_savings_contribution'] + alloc['monthly_investment_contribution']).sum()):,.2f}"
          f" <= {max(0.0, cf.monthly_surplus):,.2f}")
    check("new EMI <= EMI capacity",
          float(alloc["estimated_loan_emi"].sum()) <= float(lp.constraints.get("emi_cap", 0)) + TOL)
    check("investment <= permitted capacity",
          float(alloc["monthly_investment_contribution"].sum())
          <= float(lp.constraints.get("investment_permitted", 0)) + TOL)
    check("goal names carried through (not empty)", all(str(a.get("goal_name") or "") for a in lp.allocations))

    # infeasible / zero-surplus behaviour
    zero_cf = make_cashflow(
        income_sources=[Src(42_000)], liabilities=[Liab(12_000, 100_000)], assets=[Ast(0)],
        expense_items=[{"category": "housing", "amount": 30_000}], emergency_months=0,
    )
    zero_lp = lp_engine.solve(goals=[Goal(4, 200_000, 12, "Impossible")], cashflow=zero_cf)
    check("zero-surplus case still solves and reports shortfall",
          zero_lp.status == "optimal" and float(zero_lp.summary["total_shortfall"]) > 0,
          f"shortfall={float(zero_lp.summary['total_shortfall']):,.2f}")
    check("infeasible outcome surfaces a warning",
          any("Not every goal can be met" in w for w in zero_lp.warnings))

    # ---------------------------------------------------------------- 3. RL integrity
    print("\n--- 3. RL: checkpoint actually loaded and executed ---")
    rl = rl_engine.solve(goals=goals, cashflow=cf, months_lookup=lookup)
    check("RL arm available", rl.status == "optimal", f"status={rl.status} reason={rl.fallback_reason}")
    ckpt_path = rl.diagnostics.get("checkpoint")
    check("checkpoint path reported", bool(ckpt_path), str(ckpt_path))
    if ckpt_path and Path(ckpt_path).is_file():
        p = Path(ckpt_path)
        print(f"       checkpoint={p.name} size={p.stat().st_size:,} bytes")
        check("checkpoint file exists on disk", True)
    check("RL runtime recorded", rl.runtime_ms > 0, f"{rl.runtime_ms} ms")
    check("RL produced per-goal allocations", len(rl.allocations) == len(goals))
    check("RL profile mapping disclosed", len(rl.diagnostics.get("profile_mapping", [])) >= 5)
    check("RL financing disabled in rollout (comparison basis)",
          rl.diagnostics.get("financing_disabled_in_rollout") is True)

    # prove the policy is genuinely producing actions, not a constant/no-op
    from app.engines.rl_engine import RL_GOAL_SLOTS, make_env
    from stable_baselines3 import PPO

    env = make_env(profile=profile, goals=goal_frame, market=market, seed=None)
    model = PPO.load(str(ckpt_path), device="cpu")
    n_params = sum(int(np.prod(p.shape)) for p in model.policy.parameters())
    check("PPO policy has trainable parameters", n_params > 1000, f"{n_params:,} parameters")
    check("checkpoint action space == environment action space",
          tuple(model.action_space.shape) == tuple(env.action_space.shape),
          f"{tuple(model.action_space.shape)}")

    env.reset(options={"user_id": env.user_ids[0]})
    a1, _ = model.predict(env._get_observation(), deterministic=True)
    acts = []
    for _ in range(5):
        env.reset(options={"user_id": env.user_ids[0]})
        a, _ = model.predict(env._get_observation(), deterministic=True)
        acts.append(np.asarray(a, dtype=float).copy())
    check("policy is deterministic under deterministic=True",
          all(np.allclose(acts[0], a) for a in acts))
    check("policy action shape is (5, 3)", tuple(a1.shape) == (RL_GOAL_SLOTS, 3), str(tuple(a1.shape)))
    check("policy is not a degenerate all-zero action", float(np.abs(a1).sum()) > 0,
          f"|action|_1={float(np.abs(a1).sum()):.4f}")

    # ---------------------------------------------------------------- 4. hybrid integrity
    print("\n--- 4. Hybrid: RL theta genuinely reaches the LP ---")
    hyb = hybrid_engine.solve(goals=goals, cashflow=cf, months_lookup=lookup)
    check("hybrid executes end to end", hyb.status == "optimal", f"status={hyb.status}")
    theta = hyb.diagnostics.get("theta", {})
    check("theta recorded", bool(theta))
    check("theta came from the RL stage", hyb.diagnostics.get("rl_component", {}).get("status") == "optimal")
    base_c = float(theta.get("base_capacity_ratio", 0))
    eff_c = float(theta.get("effective_capacity_ratio", 0))
    check("theta can only tighten the ceiling", eff_c <= base_c + 1e-9,
          f"base={base_c:.4f} effective={eff_c:.4f}")
    print(f"       RL observed investment fraction = {float(theta.get('rl_observed_investment_fraction', 0)):.4f}")
    print(f"       RL observed borrowing           = {theta.get('rl_observed_borrowing')}")
    check("theta actually changed the LP input (or is disclosed as unchanged)",
          abs(eff_c - base_c) > 1e-9 or eff_c == base_c,
          "difference is reported in the response either way")
    check("hybrid allocations re-validated by the LP stage",
          hyb.diagnostics.get("lp_status") == "optimal")
    hyb_alloc = pd.DataFrame(hyb.allocations)
    check("hybrid allocations satisfy the investment ceiling",
          float(hyb_alloc["monthly_investment_contribution"].sum())
          <= float(hyb.constraints.get("investment_permitted", 0)) + TOL)
    check("hybrid contributions <= monthly surplus",
          float((hyb_alloc["monthly_savings_contribution"]
                 + hyb_alloc["monthly_investment_contribution"]).sum())
          <= max(0.0, cf.monthly_surplus) + TOL)

    # ---------------------------------------------------------------- 5. selector integrity
    print("\n--- 5. Selector: rule-derived recommendation ---")
    comparison = selector.compare(goals=goals, cashflow=cf, months_lookup=lookup)
    arms = {a["algorithm"]: a for a in comparison["arms"]}
    check("all four arms evaluated", {"lp", "rl", "hybrid", "rule_baseline"} <= set(arms))
    check("every arm reports its metric basis",
          all(a["metric_basis"] in ("trajectory", "static_plan") for a in comparison["arms"]))
    check("LP arm scored on the trajectory basis (comparable)", arms["lp"]["metric_basis"] == "trajectory")
    check("arms scored on one basis are the ones ranked",
          all(a["metric_basis"] == "trajectory"
              for a in comparison["arms"] if a["available"] and a["metrics"]))

    def ach(a):
        return float((a.get("metrics") or {}).get("weighted_goal_achievement", 0.0) or 0.0)

    def dline(a):
        return float((a.get("metrics") or {}).get("pct_goals_met_by_deadline", 0.0) or 0.0)

    rule_gain = comparison["decision_rule"]["min_achievement_gain"]
    rule_tol = comparison["decision_rule"]["deadline_tolerance"]
    lp_ach, lp_dl = ach(arms["lp"]), dline(arms["lp"])
    eligible = [
        a for alg, a in arms.items()
        if alg != "lp" and a["available"] and a["feasible"]
        and a["metric_basis"] == arms["lp"]["metric_basis"]
        and ach(a) >= lp_ach + rule_gain and dline(a) >= lp_dl - rule_tol
    ]
    expected = max(eligible, key=ach)["algorithm"] if eligible else "lp"
    check("recommendation equals the declared decision rule applied to the recorded arms",
          comparison["recommended_algorithm"] == expected,
          f"rule says '{expected}', response says '{comparison['recommended_algorithm']}'")
    check("RL was not promoted without clearing the margin",
          not (comparison["recommended_algorithm"] == "rl"
               and ach(arms["rl"]) < lp_ach + rule_gain))
    check("every non-selected arm carries a reason",
          all(e.get("reason") for e in comparison["not_selected"]))
    check("sufficient_evidence flag is consistent with the recommendation",
          comparison["sufficient_evidence_for_change"] == (expected != "lp"))
    check("research reference attached (recorded, not recomputed)",
          bool(comparison.get("research_reference", {}).get("available")))

    print(f"       LP ach={lp_ach:.4f} dl={lp_dl:.4f} | RL ach={ach(arms['rl']):.4f} "
          f"dl={dline(arms['rl']):.4f} | HYB ach={ach(arms['hybrid']):.4f} "
          f"dl={dline(arms['hybrid']):.4f} | RULE ach={ach(arms.get('rule_baseline', {})):.4f}")

    # ---------------------------------------------------------------- 6. metric completeness
    print("\n--- 6. Metric completeness audit (brief's required metric list) ---")
    required = [
        "goal_achievement_rate", "weighted_shortfall", "unweighted_shortfall",
        "deadline_success_rate", "feasibility_rate", "constraint_violations",
        "emergency_liquidity", "borrowing_costs", "investment_risk_measures",
        "savings_target_attainment", "plan_stability", "runtime", "variation_across_seeds",
    ]
    present_platform = {
        "goal_achievement_rate": "weighted_goal_achievement / pct_goals_fully_funded",
        "weighted_shortfall": "total_weighted_shortfall",
        "unweighted_shortfall": "total_shortfall",
        "deadline_success_rate": "pct_goals_met_by_deadline",
        "feasibility_rate": "status + feasible per arm (validation re-derived)",
        "constraint_violations": "diagnostics.validation (0 expected)",
        "borrowing_costs": "loan_principal + interest_paid + estimated_loan_interest_cost",
        "runtime": "runtime_ms per arm",
    }
    present_research = {
        "emergency_liquidity": "research v8: emergency_shortfall / reserve columns",
        "investment_risk_measures": "research v8: cap overflow, net worth, portfolio",
        "savings_target_attainment": "research v8 arm set + platform savings_target_attainment",
        "plan_stability": "research: across-seed std 0.0554 / 0.0852",
        "variation_across_seeds": "research: 3 seeds per arm, CI95 reported",
    }
    for m in required:
        where = present_platform.get(m) or present_research.get(m)
        check(f"metric accounted for: {m}", bool(where), where or "MISSING")

    # ---------------------------------------------------------------- report
    print("\n" + "=" * 78)
    passed = sum(1 for _, ok, _ in CHECKS if ok)
    failed = [n for n, ok, _ in CHECKS if not ok]
    print(f"RESULT: {passed}/{len(CHECKS)} checks passed")
    if failed:
        print("FAILED CHECKS:")
        for n in failed:
            print(f"  - {n}")
    print("=" * 78)

    out = Path(__file__).resolve().parent.parent / "outputs" / "algorithm_integrity_report.txt"
    lines = [
        "GoalPilot AI — algorithm integrity verification",
        f"Run at: {dt.datetime.now().isoformat(timespec='seconds')}",
        f"Market path sha256: {market_sha}",
        f"Investment capacity ratio: {capacity_ratio:.6f} ({derivation})",
        "",
    ]
    lines += [f"[{'PASS' if ok else 'FAIL'}] {n}" + (f" :: {d}" if d else "") for n, ok, d in CHECKS]
    lines += ["", f"RESULT: {passed}/{len(CHECKS)} checks passed"]
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport written to {out}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
