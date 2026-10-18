"""GoalPilot AI multi-goal LP prototype.

This module is an auditable extension prototype, not regulated financial advice.
It uses scipy.optimize.linprog and explicit user-supplied assumptions.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict, replace
from typing import Any
import math
import pandas as pd
from scipy.optimize import linprog
try:
    from .providers import (
        EconomicScenario,
        InvestmentCandidate,
        LoanOffer,
        SavingsProduct,
        select_investment_candidate,
        select_loan_offer,
        select_savings_product,
    )
except ImportError:  # allow running scripts with src/ on PYTHONPATH
    from providers import (
        EconomicScenario,
        InvestmentCandidate,
        LoanOffer,
        SavingsProduct,
        select_investment_candidate,
        select_loan_offer,
        select_savings_product,
    )

REQUIRED_GOAL_COLUMNS = {
    "goal_id", "goal_name", "current_cost", "target_date", "time_horizon_months",
    "priority", "criticality", "existing_funding"
}

@dataclass
class FinancialState:
    monthly_income: float
    essential_expenses: float
    discretionary_expenses: float = 0.0
    existing_emi: float = 0.0
    liquid_savings: float = 0.0
    existing_investments: float = 0.0
    usable_existing_investments: float = 0.0
    emergency_months: float = 6.0
    emi_income_ratio_cap: float = 0.35
    risk_capacity: float = 0.5  # normalized 0..1; explicit user/profile input

    def validate(self):
        for k, v in asdict(self).items():
            if not isinstance(v, (int, float)) or not math.isfinite(v):
                raise ValueError(f"{k} must be a finite number")
            if k != "risk_capacity" and v < 0:
                raise ValueError(f"{k} cannot be negative")
        if self.monthly_income <= 0:
            raise ValueError("monthly_income must be > 0")
        if self.usable_existing_investments > self.existing_investments + 1e-9:
            raise ValueError("usable_existing_investments cannot exceed existing_investments")
        if self.risk_capacity > 1 or self.emi_income_ratio_cap > 1:
            raise ValueError("risk_capacity and emi_income_ratio_cap must be <= 1")


def monthly_emi_per_rupee(annual_rate: float, tenure_months: int) -> float:
    """Monthly payment per rupee principal, with annual nominal rate / 12."""
    if tenure_months <= 0 or annual_rate < 0:
        raise ValueError("tenure_months must be positive and annual_rate nonnegative")
    r = annual_rate / 12.0
    if r == 0:
        return 1.0 / tenure_months
    return r * (1 + r) ** tenure_months / ((1 + r) ** tenure_months - 1)


def fv_monthly_contribution_factor(annual_return: float, months: int) -> float:
    """Future value at deadline of a month-end contribution of 1 each month."""
    if months <= 0 or annual_return <= -1:
        raise ValueError("months must be positive and annual_return > -100%")
    r = (1 + annual_return) ** (1 / 12) - 1
    if abs(r) < 1e-12:
        return float(months)
    return ((1 + r) ** months - 1) / r


def prepare_goals(goals: pd.DataFrame, annual_inflation: float = 0.03) -> pd.DataFrame:
    missing = REQUIRED_GOAL_COLUMNS - set(goals.columns)
    if missing:
        raise ValueError(f"Missing goal columns: {sorted(missing)}")
    g = goals.copy()
    if g.empty:
        raise ValueError("At least one goal is required")
    if g.goal_id.astype(str).duplicated().any():
        raise ValueError("goal_id must be unique")
    for c in ["current_cost", "time_horizon_months", "priority", "criticality", "existing_funding"]:
        g[c] = pd.to_numeric(g[c], errors="raise")
        if (g[c] < 0).any():
            raise ValueError(f"{c} cannot be negative")
    if (g.time_horizon_months < 1).any():
        raise ValueError("time_horizon_months must be at least 1")
    if annual_inflation <= -1:
        raise ValueError("annual_inflation must be > -100%")
    g["future_goal_cost"] = g.current_cost * (1 + annual_inflation) ** (g.time_horizon_months / 12)
    g["funding_gap"] = (g.future_goal_cost - g.existing_funding).clip(lower=0)
    # Transparent, normalized score. Priority and criticality are assumed user-entered on 1..5.
    # Shorter horizon raises urgency; capped at a factor of 2 to avoid dominating user priority.
    horizon_urgency = (12 / g.time_horizon_months).clip(upper=2.0)
    g["goal_priority_score"] = g.priority.clip(lower=1, upper=5) * g.criticality.clip(lower=1, upper=5) * (1 + horizon_urgency) / 2
    g["required_monthly_contribution"] = g.funding_gap / g.time_horizon_months
    g["target_date"] = pd.to_datetime(g.target_date, errors="raise").dt.strftime("%Y-%m-%d")
    return g


def optimize_multi_goal(
    goals: pd.DataFrame,
    state: FinancialState,
    *,
    annual_inflation: float = 0.03,
    savings_return: float = 0.0,
    investment_return: float = 0.05,
    investment_risk_score: float = 0.4,
    loan_annual_rate: float = 0.12,
    loan_tenure_months: int = 60,
    max_loan_per_goal: float = 150000.0,
    existing_asset_return: float = 0.0,
    existing_asset_risk_score: float = 0.2,
    investment_candidates: list[InvestmentCandidate | dict[str, Any]] | None = None,
    loan_offers: list[LoanOffer | dict[str, Any]] | None = None,
    savings_products: list[SavingsProduct | dict[str, Any]] | None = None,
    economic_scenario: EconomicScenario | dict[str, Any] | None = None,
    shortfall_penalty: float = 1.0,
    loan_cost_penalty: float = 0.02,
    risk_penalty: float = 0.0002,
) -> dict[str, Any]:
    """Solve one LP across all goals. Monetary values are in the same currency units.

    Variables per goal: initial savings allocated, monthly savings contribution,
    monthly investment contribution, loan principal, and remaining shortfall.
    Returns/interest are assumptions, not forecasts or guarantees.
    """
    state.validate()
    scenario_label = "explicit_parameters"
    if economic_scenario is not None:
        if isinstance(economic_scenario, dict):
            economic_scenario = EconomicScenario.from_mapping(economic_scenario)
        annual_inflation = economic_scenario.annual_inflation
        investment_return = economic_scenario.investment_return
        savings_return = economic_scenario.savings_return
        loan_annual_rate = economic_scenario.loan_annual_rate
        scenario_label = economic_scenario.name
    savings_product = select_savings_product(savings_products)
    if savings_product is not None:
        savings_return = savings_product.annual_return
    investment_candidate = select_investment_candidate(
        investment_candidates,
        risk_capacity=state.risk_capacity,
        min_horizon_months=int(pd.to_numeric(goals["time_horizon_months"], errors="coerce").min()) if "time_horizon_months" in goals else 1,
    )
    if investment_candidate is not None:
        investment_return = investment_candidate.expected_annual_return
        investment_risk_score = investment_candidate.risk_score
    loan_offer = select_loan_offer(loan_offers)
    if loan_offer is not None:
        loan_annual_rate = loan_offer.annual_interest_rate
        loan_tenure_months = loan_offer.tenure_months
        max_loan_per_goal = min(max_loan_per_goal, loan_offer.max_principal)
    if not 0 <= investment_risk_score <= 1:
        raise ValueError("investment_risk_score must be between 0 and 1")
    if not 0 <= existing_asset_risk_score <= 1:
        raise ValueError("existing_asset_risk_score must be between 0 and 1")
    if not 0 <= state.risk_capacity <= 1:
        raise ValueError("risk_capacity must be between 0 and 1")
    if min(shortfall_penalty, loan_cost_penalty, risk_penalty) < 0:
        raise ValueError("penalties must be nonnegative")
    g = prepare_goals(goals, annual_inflation)
    n = len(g)
    # x indices: [cash0_i, asset0_i, save_m_i, invest_m_i, loan_i, shortfall_i] per goal.
    def ix(j, kind): return 6*j + {"cash":0,"asset":1,"save":2,"invest":3,"loan":4,"short":5}[kind]
    nv = 6*n
    c = [0.0]*nv
    bounds = [(0, None)]*nv
    A_ub, b_ub, A_eq, b_eq = [], [], [], []
    # Existing goal funding is assumed to be earmarked within the reported liquid-savings
    # balance. Remove it from the shared cash pool so it is not counted twice.
    earmarked_goal_funding = float(g.existing_funding.sum())
    available_cash = max(0.0, state.liquid_savings - state.emergency_months * state.essential_expenses - earmarked_goal_funding)
    usable_existing_assets = float(state.usable_existing_investments)
    monthly_surplus = max(0.0, state.monthly_income - state.essential_expenses - state.discretionary_expenses - state.existing_emi)
    emi_cap = max(0.0, state.monthly_income * state.emi_income_ratio_cap - state.existing_emi)
    emi_factor = monthly_emi_per_rupee(loan_annual_rate, loan_tenure_months)
    total_weight = float(g.goal_priority_score.sum()) or 1.0
    goal_factors=[]
    for j, row in g.reset_index(drop=True).iterrows():
        months = int(row.time_horizon_months)
        sf = fv_monthly_contribution_factor(savings_return, months)
        inv_factor = fv_monthly_contribution_factor(investment_return, months)
        asset_factor = (1 + existing_asset_return) ** (months / 12)
        goal_factors.append((sf, inv_factor))
        weight = float(row.goal_priority_score) / total_weight
        # Primary objective minimizes weighted shortfall; secondary penalties are expressed
        # as transparent rupee-equivalent costs and should be calibrated for deployment.
        c[ix(j,"short")] = shortfall_penalty * weight
        c[ix(j,"loan")] = loan_cost_penalty * max(0.0, loan_annual_rate) * loan_tenure_months / 12
        c[ix(j,"asset")] = 0.001 + risk_penalty * existing_asset_risk_score
        # Small resource-use cost breaks ties and favours efficient future value;
        # the investment option receives an additional transparent risk penalty.
        c[ix(j,"save")] = 0.001
        c[ix(j,"invest")] = 0.001 + risk_penalty * investment_risk_score
        bounds[ix(j,"cash")] = (0, None)
        if existing_asset_risk_score > state.risk_capacity:
            bounds[ix(j,"asset")] = (0, 0)
        else:
            bounds[ix(j,"asset")] = (0, None)
        bounds[ix(j,"save")] = (0, None)
        # Risk mismatch: if risk exceeds user's capacity, prohibit the risky investment option.
        if investment_risk_score > state.risk_capacity:
            bounds[ix(j,"invest")] = (0, 0)
        else:
            bounds[ix(j,"invest")] = (0, None)
        bounds[ix(j,"loan")] = (0, min(max_loan_per_goal, float(row.funding_gap)))
        bounds[ix(j,"short")] = (0, float(row.funding_gap))
        # Goal accounting: current allocated cash + projected monthly contributions + loan + shortfall = gap.
        eq = [0.0]*nv
        eq[ix(j,"cash")] = 1.0
        eq[ix(j,"asset")] = asset_factor
        eq[ix(j,"save")] = sf
        eq[ix(j,"invest")] = inv_factor
        eq[ix(j,"loan")] = 1.0
        eq[ix(j,"short")] = 1.0
        A_eq.append(eq); b_eq.append(float(row.funding_gap))
    # One shared pool of existing cash, surplus and EMI capacity; no double-counting.
    row=[0.0]*nv
    for j in range(n): row[ix(j,"cash")]=1
    A_ub.append(row); b_ub.append(available_cash)
    row=[0.0]*nv
    for j in range(n): row[ix(j,"asset")]=1
    A_ub.append(row); b_ub.append(usable_existing_assets)
    row=[0.0]*nv
    for j in range(n):
        row[ix(j,"save")]=1; row[ix(j,"invest")]=1
    A_ub.append(row); b_ub.append(monthly_surplus)
    row=[0.0]*nv
    for j in range(n): row[ix(j,"loan")]=emi_factor
    A_ub.append(row); b_ub.append(emi_cap)

    # Combined affordability constraint:
    # monthly contributions + new loan EMIs must fit within monthly surplus.
    row=[0.0]*nv
    for j in range(n):
        row[ix(j,"save")]=1.0
        row[ix(j,"invest")]=1.0
        row[ix(j,"loan")]=emi_factor
    A_ub.append(row); b_ub.append(monthly_surplus)

    result=linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq, bounds=bounds, method="highs")
    if not result.success:
        return {"status":"infeasible_or_solver_error", "solver_message":result.message, "goals":g, "allocations":pd.DataFrame(), "summary":{}, "constraints":{}}
    records=[]
    for j,row in g.reset_index(drop=True).iterrows():
        cash=float(result.x[ix(j,"cash")]); asset=float(result.x[ix(j,"asset")]); save=float(result.x[ix(j,"save")]); inv=float(result.x[ix(j,"invest")]); loan=float(result.x[ix(j,"loan")]); short=float(result.x[ix(j,"short")])
        sf,inf=goal_factors[j]
        asset_factor = (1 + existing_asset_return) ** (int(row.time_horizon_months) / 12)
        projected=cash+asset*asset_factor+save*sf+inv*inf+loan
        emi=loan*emi_factor
        records.append({"goal_id":row.goal_id,"goal_name":row.goal_name,"future_goal_cost":row.future_goal_cost,"existing_funding":row.existing_funding,"funding_gap":row.funding_gap,"goal_priority_score":row.goal_priority_score,"initial_savings_allocated":cash,"existing_assets_allocated":asset,"monthly_savings_contribution":save,"monthly_investment_contribution":inv,"loan_principal":loan,"estimated_loan_emi":emi,"estimated_loan_total_repayment":emi*loan_tenure_months,"estimated_loan_interest_cost":max(0,emi*loan_tenure_months-loan),"projected_new_funding":projected,"shortfall":short,"achievement_ratio":min(1.0,projected/row.funding_gap) if row.funding_gap else 1.0,"time_horizon_months":int(row.time_horizon_months)})
    allocations=pd.DataFrame(records)
    total_emi=float(allocations.estimated_loan_emi.sum())
    summary={"status":"optimal","objective_value":float(result.fun),"goal_count":n,"total_future_goal_cost":float(g.future_goal_cost.sum()),"total_funding_gap":float(g.funding_gap.sum()),"total_projected_new_funding":float(allocations.projected_new_funding.sum()),"total_shortfall":float(allocations.shortfall.sum()),"weighted_goal_achievement":float((allocations.achievement_ratio*g.goal_priority_score.to_numpy()).sum()/total_weight),"available_cash_above_emergency_reserve":available_cash,"earmarked_existing_goal_funding_excluded_from_cash_pool":earmarked_goal_funding,"cash_allocated":float(allocations.initial_savings_allocated.sum()),"usable_existing_assets_available":usable_existing_assets,"existing_assets_allocated":float(allocations.existing_assets_allocated.sum()),"existing_assets_retained_or_illiquid":float(state.existing_investments-allocations.existing_assets_allocated.sum()),"monthly_surplus_available":monthly_surplus,"monthly_contributions_allocated":float((allocations.monthly_savings_contribution+allocations.monthly_investment_contribution).sum()),"emi_capacity":emi_cap,"new_total_emi":total_emi,"risk_capacity":state.risk_capacity,"investment_risk_score":investment_risk_score,"existing_asset_risk_score":existing_asset_risk_score,"emergency_fund_target":state.emergency_months*state.essential_expenses,"emergency_fund_preserved":float(allocations.initial_savings_allocated.sum()) <= available_cash+1e-5,"emergency_fund_target_met_after_allocation":state.liquid_savings-allocations.initial_savings_allocated.sum() >= state.emergency_months*state.essential_expenses-1e-6,"emergency_fund_was_below_target_at_start":state.liquid_savings < state.emergency_months*state.essential_expenses-1e-6,"monthly_surplus_respected":float((allocations.monthly_savings_contribution+allocations.monthly_investment_contribution).sum())<=monthly_surplus+1e-5,"combined_monthly_cashflow_respected":float((allocations.monthly_savings_contribution+allocations.monthly_investment_contribution).sum()+total_emi)<=monthly_surplus+1e-5,"existing_assets_respected":float(allocations.existing_assets_allocated.sum())<=usable_existing_assets+1e-5,"emi_cap_respected":total_emi<=emi_cap+1e-5,"loan_cost_total":float(allocations.estimated_loan_interest_cost.sum()),"selected_options":{"savings_product": savings_product.to_dict() if savings_product else None,"investment_candidate": investment_candidate.to_dict() if investment_candidate else None,"loan_offer": loan_offer.to_dict() if loan_offer else None,"economic_scenario": economic_scenario.to_dict() if economic_scenario else {"name": scenario_label, "source":"function parameters"}},"assumptions":{"annual_inflation":annual_inflation,"savings_return":savings_return,"investment_return":investment_return,"existing_asset_return":existing_asset_return,"loan_annual_rate":loan_annual_rate,"loan_tenure_months":loan_tenure_months,"max_loan_per_goal":max_loan_per_goal,"investment_risk_score":investment_risk_score,"note":"Rates and eligibility limits are scenario assumptions, not recommendations or guarantees."}}
    return {"status":"optimal","solver_message":result.message,"goals":g,"allocations":allocations,"summary":summary,"constraints":{"monthly_surplus":monthly_surplus,"available_cash":available_cash,"emi_capacity":emi_cap}}


def strategy_comparison(goals: pd.DataFrame, state: FinancialState, **kwargs) -> pd.DataFrame:
    """Run comparable baseline and optimized strategy cases."""
    base = dict(kwargs)
    existing_asset_state = replace(
        state,
        usable_existing_investments=max(state.usable_existing_investments, min(state.existing_investments, state.existing_investments * 0.25)),
    )
    cases = [
        ("Baseline/rule-based", state, {**base, "investment_risk_score": 1.0, "max_loan_per_goal": 0.0, "shortfall_penalty": base.get("shortfall_penalty", 1.0)}),
        ("Savings only", {**base, "investment_risk_score": 1.0, "max_loan_per_goal": 0.0}),
        ("Savings + investment", state, {**base, "max_loan_per_goal": 0.0}),
        ("Combined savings + investment + loan", state, {**base}),
        ("Existing-asset-aware", existing_asset_state, {**base, "max_loan_per_goal": 0.0}),
        ("Optimized LP", state, {**base}),
    ]
    rows=[]
    for item in cases:
        if len(item) == 2:
            name, opts = item
            case_state = state
        else:
            name, case_state, opts = item
        res=optimize_multi_goal(goals,case_state,**opts)
        s=res.get("summary",{})
        rows.append({"strategy":name,"status":res["status"],"weighted_goal_achievement":s.get("weighted_goal_achievement"),"projected_new_funding":s.get("total_projected_new_funding"),"loan_cost":s.get("loan_cost_total"),"shortfall":s.get("total_shortfall"),"monthly_contributions":s.get("monthly_contributions_allocated"),"new_emi":s.get("new_total_emi"),"existing_assets_allocated":s.get("existing_assets_allocated")})
    return pd.DataFrame(rows)
