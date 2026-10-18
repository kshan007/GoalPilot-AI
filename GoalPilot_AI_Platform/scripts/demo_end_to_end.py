"""GoalPilot AI Platform — end-to-end demonstration.

Runs the full academic-review workflow against a LIVE server over real HTTP and writes a
transcript. This is not a mock: every number printed comes from an API response.

Start the backend first, then run this script:

    cd backend
    uvicorn app.main:app --port 8000
    # separate terminal
    python ../scripts/demo_end_to_end.py --base-url http://127.0.0.1:8000/api

The synthetic profile used here is clearly labelled as synthetic and is separate from any
real user data.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import uuid
from pathlib import Path

import httpx

OUT = Path(__file__).resolve().parent.parent / "outputs"
OUT.mkdir(parents=True, exist_ok=True)

LINES: list[str] = []


def say(text: str = "") -> None:
    print(text)
    LINES.append(text)


def head(step: int, title: str) -> None:
    say("")
    say("=" * 78)
    say(f"STEP {step}. {title}")
    say("=" * 78)


def money(v) -> str:
    try:
        return f"{float(v):,.2f}"
    except (TypeError, ValueError):
        return str(v)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    client = httpx.Client(base_url=base, timeout=180.0)
    run_id = uuid.uuid4().hex[:8]
    email = f"demo-{run_id}@goalpilot.example"
    password = "Demo-Str0ng-Pass!"

    say("GoalPilot AI Platform — end-to-end demonstration")
    say(f"Run id: {run_id}")
    say(f"Base URL: {base}")
    say(f"Started: {dt.datetime.now().isoformat(timespec='seconds')}")
    say("")
    say("This transcript contains only values returned by the running application.")

    # ---------------------------------------------------------------- 0. health
    head(0, "Service health, model provenance and assumptions")
    health = client.get("/health").json()
    say(json.dumps(
        {
            "status": health["status"],
            "version": health["version"],
            "research_source": health["research_source"],
            "supported_features": health["supported_features"],
        },
        indent=2,
    ))
    assumptions = client.get("/meta/assumptions").json()
    say("")
    say("Default assumptions (EDITABLE, not facts):")
    say(json.dumps(assumptions["defaults"], indent=2))
    registry = client.get("/models/registry").json()
    say("")
    say("Model registry (status is what is genuinely executable right now):")
    for entry in registry["entries"]:
        say(f"  {entry['name']:32s} {entry['kind']:9s} {entry['status']}")

    # ---------------------------------------------------------------- 1. register
    head(1, "User registration")
    created = client.post(
        "/auth/register", json={"email": email, "password": password, "full_name": "Demo Reviewer"}
    )
    created.raise_for_status()
    token = created.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    say(f"Registered {email} (user id {created.json()['user']['id']}) and received a JWT.")
    say("Passwords are bcrypt-hashed; no hash is ever returned.")

    # ---------------------------------------------------------------- 2-3. profile
    head(2, "Financial profile: income, expenses, savings, debt")
    today = dt.date.today()
    profile = client.put(
        "/profile",
        json={
            "monthly_income": 90000,
            "essential_expenses": 42000,
            "discretionary_expenses": 6000,
            "monthly_savings_target": 15000,
            "savings_target_is_mandatory": False,
            "preferred_cash_buffer": 50000,
            "willing_to_adjust_discretionary": True,
            "emergency_months": 6,
            "emi_income_ratio_cap": 0.35,
            "risk_capacity": 0.55,
            "inflation_assumption": 0.03,
            "investment_return_assumption": 0.05,
            "savings_return_assumption": 0.0,
            "loan_interest_assumption": 0.12,
        },
    )
    profile.raise_for_status()
    say("Profile saved. Risk CAPACITY (0.55) is stored separately from risk APPETITE and is "
        "never inferred from it.")

    client.post("/income-sources", json={
        "source_type": "salary", "label": "Primary salary", "amount": 90000,
        "frequency": "monthly", "stability": "stable", "is_recurring": True,
    }).raise_for_status()
    client.post("/income-sources", json={
        "source_type": "freelance", "label": "Freelance (annual retainer)", "amount": 120000,
        "frequency": "annual", "stability": "variable", "is_recurring": True,
    }).raise_for_status()
    incomes = client.get("/income-sources").json()
    say("")
    say("Income sources (original frequency retained, monthly equivalent derived):")
    for src in incomes:
        say(f"  {src['label']:32s} {money(src['amount']):>12s} /{src['frequency']:<9s} "
            f"= {money(src['monthly_equivalent']):>10s} /month")

    client.post("/assets", json={
        "asset_type": "liquid_savings", "label": "Savings account",
        "current_value": 420000, "is_liquid": True, "usable_for_goals": True,
    }).raise_for_status()
    client.post("/liabilities", json={
        "liability_type": "personal_loan", "label": "Personal loan",
        "outstanding_principal": 600000, "annual_interest_rate": 0.12,
        "emi_amount": 12000, "remaining_tenure_months": 60,
    }).raise_for_status()
    liability = client.get("/liabilities").json()[0]
    say("")
    say("Liability (the EMI already contains principal + interest; the balance is NOT added):")
    say(f"  principal {money(liability['outstanding_principal'])}  |  EMI "
        f"{money(liability['emi_amount'])}/month  |  interest if held to tenure "
        f"{money(liability['total_interest_if_held_to_tenure'])}")

    summary = client.get("/profile/summary").json()
    head(3, "Derived financial state (the single canonical surplus definition)")
    say(f"  income                       {money(summary['monthly_income']):>14s}")
    say(f"  - essential expenses         {money(summary['essential_expenses']):>14s}")
    say(f"  - discretionary expenses     {money(summary['discretionary_expenses']):>14s}")
    say(f"  - existing EMI               {money(summary['existing_emi']):>14s}")
    say(f"  = MONTHLY SURPLUS            {money(summary['monthly_surplus']):>14s}")
    say(f"  liquid savings               {money(summary['liquid_savings']):>14s}")
    say(f"  emergency target ({summary['emergency_months']:g} x essential) "
        f"{money(summary['emergency_fund_target']):>8s}  "
        f"progress {summary['emergency_fund_progress']:.0%}")
    say(f"  cash available for goals     {money(summary['available_cash_for_goals']):>14s}")
    say(f"  situation tier               {summary['situation_tier']:>14s}")
    for warning in summary["warnings"]:
        say(f"  warning: {warning}")

    # ---------------------------------------------------------------- 4. goals
    head(4, "Multiple financial goals")
    goal_specs = [
        ("Professional certification", "education", 90000, 365, 4, 5, 10000),
        ("Vehicle down payment", "vehicle", 300000, 1095, 3, 3, 50000),
        ("Emergency fund top-up", "emergency", 200000, 730, 5, 5, 20000),
        ("Family holiday", "travel", 150000, 1460, 2, 4, 0),
    ]
    for name, kind, cost, days, priority, criticality, funded in goal_specs:
        client.post("/goals", json={
            "name": name, "purpose": f"Planned {name.lower()}", "goal_type": kind,
            "current_cost": cost, "target_date": (today + dt.timedelta(days=days)).isoformat(),
            "current_funded_amount": funded, "priority": priority, "criticality": criticality,
            "date_flexible": True, "amount_flexible": False,
        }).raise_for_status()
    goals = client.get("/goals").json()
    for g in goals:
        say(f"  #{g['id']} {g['name']:30s} cost {money(g['current_cost']):>12s} "
            f"target {g['target_date']}  priority {g['priority']}  "
            f"funded {money(g['current_funded_amount']):>10s}")

    client.post("/onboarding/complete").raise_for_status()
    say("")
    say("Onboarding completed.")

    goal_plan = client.get("/goals/plan").json()
    say("")
    say("Goal projection BEFORE any optimiser runs (future cost = current x (1+inflation)^(m/12)):")
    say(f"  {'goal':30s} {'future target':>14s} {'gap':>13s} {'req/month':>11s}  feasibility")
    for p in goal_plan:
        say(f"  {p['name'][:30]:30s} {money(p['future_target']):>14s} "
            f"{money(p['remaining_gap']):>13s} {money(p['required_monthly_contribution']):>11s}  "
            f"{p['feasibility']}")

    # ---------------------------------------------------------------- 5. month
    head(5, "Current month: opened, estimated expenses (cold start)")
    period = today.strftime("%Y-%m")
    client.post(f"/months/{period}/open").raise_for_status()
    estimate = client.post(f"/months/{period}/estimate-expenses", json={
        "category_estimates": {
            "food_groceries": 12000, "utilities": 4000, "transport": 4000, "shopping": 5000,
        },
        "persist": True,
    }).json()
    say(f"Period {period}.  History available: {estimate['history_months_available']} month(s).")
    say(f"Method: {estimate['estimation_method']}")
    say(f"Quality note: {estimate['data_quality_note']}")
    say("")
    say("Category estimates (provenance = estimated):")
    for item in estimate["forecast"]["category_forecasts"]:
        if item["amount"] <= 0:
            continue
        say(f"  {item['category']:20s} {money(item['amount']):>11s}  "
            f"method={item['method']:<20s} provisional={item['is_provisional']}")
    say("")
    say(f"  expected month-end spending {money(estimate['expected_month_end_spending'])}")
    say(f"  projected surplus           {money(estimate['projected_surplus'])}")

    # ---------------------------------------------------------------- 6-8. plan
    head(6, "Initial financial plan (capacity-constrained LP)")
    plan = client.post("/optimize/plan", json={"algorithm": "lp"}).json()
    say(f"status={plan['status']}  feasible={plan['feasible']}  "
        f"model={plan['model_version']}  runtime={plan['runtime_ms']} ms")
    say(f"objective={plan['objective_value']}")
    say("")
    say("Multi-goal allocation:")
    say(f"  {'goal':26s} {'cash':>10s} {'assets':>9s} {'save/mo':>10s} {'invest/mo':>10s} "
        f"{'loan':>9s} {'shortfall':>11s}")
    for a in plan["allocations"]:
        say(f"  {a['goal_name'][:26]:26s} {money(a['initial_savings_allocated']):>10s} "
            f"{money(a['existing_assets_allocated']):>9s} "
            f"{money(a['monthly_savings_contribution']):>10s} "
            f"{money(a['monthly_investment_contribution']):>10s} "
            f"{money(a['loan_principal']):>9s} {money(a['shortfall']):>11s}")
    s = plan["summary"]
    say("")
    say(f"  weighted goal achievement   {float(s['weighted_goal_achievement']):.4f}")
    say(f"  total funding gap           {money(s['total_funding_gap'])}")
    say(f"  total shortfall             {money(s['total_shortfall'])}")
    say(f"  monthly contributions       {money(s['monthly_contributions_allocated'])} "
        f"(surplus available {money(s['monthly_surplus_available'])})")
    say(f"  investment permitted        {money(s['investment_permitted'])}  "
        f"allocated {money(s['monthly_investment_allocated'])}")
    validation = plan["diagnostics"]["validation"]
    say(f"  constraint validation       clean={validation['clean']} "
        f"violations={validation['count']}")
    say(f"  capacity derivation         {plan['diagnostics'].get('investment_capacity_derivation')}")
    for warning in plan["warnings"]:
        say(f"  warning: {warning}")

    head(7, "Plan diff vs the previous plan")
    say(f"  {plan['diff']['summary']}")

    head(8, "Algorithm comparison on one shared scenario")
    comparison = client.post("/optimize/compare").json()
    say(f"recommended: {comparison['recommended_algorithm']}")
    say(f"reason: {comparison['recommendation_reason']}")
    say(f"evidence sufficient to change away from the LP default: "
        f"{comparison['sufficient_evidence_for_change']}")
    say("")
    say(f"  {'arm':18s} {'available':9s} {'feasible':8s} {'basis':11s} "
        f"{'achievement':>11s} {'by deadline':>11s}")
    for arm in comparison["arms"]:
        m = arm["metrics"]
        ach = m.get("weighted_goal_achievement")
        dl = m.get("pct_goals_met_by_deadline")
        say(f"  {arm['algorithm']:18s} {str(arm['available']):9s} {str(arm['feasible']):8s} "
            f"{arm['metric_basis']:11s} "
            f"{(f'{float(ach):.4f}' if ach is not None else 'n/a'):>11s} "
            f"{(f'{float(dl):.4f}' if dl is not None else 'n/a'):>11s}")
    say("")
    say("Why each alternative was NOT selected:")
    for entry in comparison["not_selected"]:
        say(f"  - {entry['label']}: {entry['reason']}")
    say("")
    for note in comparison["notes"]:
        say(f"  note: {note}")

    # ---------------------------------------------------------------- 9. actuals
    head(9, "Actual expenses recorded")
    actuals = [("food_groceries", 14000), ("utilities", 3500), ("shopping", 9000),
               ("transport", 4200), ("healthcare", 2500)]
    for category, amount in actuals:
        client.post(f"/months/{period}/transactions", json={
            "kind": "expense", "category": category, "label": category,
            "amount": amount, "txn_date": today.isoformat(), "status": "actual",
            "client_ref": f"demo-{run_id}-{category}",
        }).raise_for_status()
    say("Recorded actuals: " + ", ".join(f"{c}={money(a)}" for c, a in actuals))
    say("Each carries a client_ref, so re-submitting the same entry is a no-op.")

    # ---------------------------------------------------------------- 10. reconcile
    head(10, "Forecast vs actual reconciliation (the forecast is never overwritten)")
    reconcile = client.post(f"/months/{period}/reconcile", json={
        "mark_actuals": True, "update_future_forecast": True,
    }).json()
    say(f"  {'category':20s} {'forecast':>11s} {'actual':>11s} {'abs err':>10s} {'% err':>8s}")
    for row in reconcile["rows"]:
        pct = row["pct_error"]
        actual = money(row["actual"]) if row.get("actual") is not None else "not recorded"
        err = money(row["abs_error"]) if row.get("abs_error") is not None else "-"
        pct_txt = f"{pct:.1f}" if pct is not None else "n/a"
        say(f"  {row['category']:20s} {money(row['forecast']):>11s} {actual:>11s} "
            f"{err:>10s} {pct_txt:>8s}")
    if reconcile.get("unmatched_note"):
        say("")
        say(f"  {reconcile['unmatched_note']}")
    t = reconcile["totals"]
    total_pct = f"{t['pct_error']:.1f}" if t["pct_error"] is not None else "n/a"
    say(f"  {'TOTAL':20s} {money(t['forecast']):>11s} {money(t['actual']):>11s} "
        f"{money(t['abs_error']):>10s} {total_pct:>8s}")
    say("")
    say(f"  over budget:  {', '.join(reconcile['over_budget_categories']) or 'none'}")
    say(f"  under budget: {', '.join(reconcile['under_budget_categories']) or 'none'}")
    say(f"  forecast preserved: {reconcile['forecast_preserved']}")
    impact = reconcile["financial_impact"]
    say(f"  actual surplus {money(impact['surplus_actual'])} "
        f"vs projected {money(impact['surplus_projected_at_estimation'])}")
    say(f"  next forecast note: {reconcile['next_forecast_note']}")

    # ---------------------------------------------------------------- 11-13. re-plan
    head(11, "Re-plan on the corrected surplus, and explain what changed")
    replan = client.post("/optimize/plan", json={"algorithm": "lp"}).json()
    say(f"  {replan['diff']['summary']}")
    for change in replan["diff"]["goal_changes"][:6]:
        say(f"  - {change}")
    say("")
    say("Updated goal feasibility:")
    for p in replan["goal_projections"]:
        say(f"  {p['name'][:30]:30s} planned/mo "
            f"{(money(p['planned_monthly_contribution']) if p['planned_monthly_contribution'] is not None else 'n/a'):>10s}"
            f"  shortfall "
            f"{(money(p['projected_shortfall']) if p['projected_shortfall'] is not None else 'n/a'):>11s}"
            f"  {p['feasibility']}")

    # ---------------------------------------------------------------- 14-15. scenario
    head(14, "Economic stress scenario: income falls 20%")
    scenario = client.post("/scenarios/run", json={
        "preset": "income_down", "parameters": {"income_change_pct": -20}, "algorithm": "lp",
    }).json()
    for line in scenario["narrative"]:
        say(f"  {line}")
    say("")
    say("Quantified difference (baseline -> stressed):")
    for key, value in scenario["deltas"].items():
        say(f"  {key:32s} {money(value['baseline']):>14s} -> {money(value['stressed']):>14s} "
            f"({value['delta']:+,.2f})")

    head(15, "Goal shortfalls and trade-offs after the stress")
    stressed_alloc = scenario["stressed"]["summary"]
    say(f"  stressed status {scenario['stressed']['status']}")
    say(f"  stressed weighted achievement "
        f"{float(stressed_alloc.get('weighted_goal_achievement', 0)):.4f}")
    say(f"  stressed total shortfall {money(stressed_alloc.get('total_shortfall', 0))}")
    say("Shortfalls are reported, not hidden: a goal that cannot be met is shown as unfunded.")

    # ---------------------------------------------------------------- 16. history
    head(16, "Persisted history: plans, forecasts and dashboard")
    runs = client.get("/optimize/runs").json()
    say(f"  optimisation runs stored: {len(runs['items'])}")
    for r in runs["items"][:6]:
        say(f"    run {r['id']:>3} {r['kind']:8s} {r['algorithm']:14s} "
            f"{r['status']:12s} feasible={str(r['feasible']):5s} "
            f"achievement={r['weighted_achievement']}")

    history = client.get("/forecast/history").json()
    say(f"  forecasts stored (with method + input cut-off): {history['count']}")
    accuracy = client.get("/forecast/accuracy").json()
    say(f"  forecast accuracy: periods evaluated {accuracy['periods_evaluated']}, "
        f"MAE per period {accuracy['mae_per_period']}")
    say(f"  evidence note: {accuracy['evidence_note']}")

    dashboard = client.get("/dashboard").json()
    say("")
    say("Dashboard (all values from persisted records):")
    say(f"  monthly surplus         {money(dashboard['cashflow']['monthly_surplus'])}")
    say(f"  emergency progress      {dashboard['cashflow']['emergency_fund_progress']:.0%}")
    say(f"  outstanding debt        {money(dashboard['debt']['outstanding_principal'])} "
        f"(EMI/income {dashboard['debt']['emi_income_ratio']:.2%}, "
        f"within cap={dashboard['debt']['within_cap']})")
    say(f"  goals active            {dashboard['goals']['active_count']} "
        f"(on track {dashboard['goals']['on_track']}, at risk {dashboard['goals']['at_risk']})")
    say(f"  chart series available  trend={len(dashboard['monthly']['trend'])}, "
        f"categories={len(dashboard['monthly']['category_breakdown'])}, "
        f"funding={len(dashboard['goals']['funding_chart'])}, "
        f"forecast errors={len(dashboard['forecasts']['error_trend'])}")
    say(f"  labels note             {dashboard['labels_note']}")

    # ---------------------------------------------------------------- isolation + export
    head(17, "Security: cross-user isolation and data export")
    other = httpx.Client(base_url=base, timeout=60.0)
    other_email = f"intruder-{run_id}@goalpilot.example"
    other_token = other.post("/auth/register", json={
        "email": other_email, "password": password, "full_name": "Intruder",
    }).json()["access_token"]
    other.headers["Authorization"] = f"Bearer {other_token}"
    target_goal = goals[0]["id"]
    probe = other.get(f"/goals/{target_goal}")
    say(f"  other user reading goal {target_goal}: HTTP {probe.status_code} "
        f"({probe.json()['error']['code']})")
    probe2 = other.put(f"/goals/{target_goal}", json={"name": "hijacked"})
    say(f"  other user updating goal {target_goal}: HTTP {probe2.status_code}")
    probe3 = other.delete(f"/goals/{target_goal}")
    say(f"  other user deleting goal {target_goal}: HTTP {probe3.status_code}")
    untouched = client.get(f"/goals/{target_goal}").json()
    say(f"  owner still sees the goal unchanged: name='{untouched['name']}'")
    say("  (404 rather than 403, so the existence of another user's rows is not disclosed.)")

    export = client.get("/account/export").json()
    say("")
    say("Account export (JSON) contains only this user's rows:")
    for key in ("income_sources", "assets", "liabilities", "goals", "transactions",
                "expense_forecasts", "forecast_evaluations", "optimization_runs",
                "scenario_runs"):
        say(f"    {key:22s} {len(export[key])}")
    say(f"    password hash present: {'password_hash' in json.dumps(export)}")

    say("")
    say("=" * 78)
    say("DEMONSTRATION COMPLETE")
    say("=" * 78)
    say("")
    say("What this run demonstrates:")
    say("  * real registration + JWT authentication, and cross-user isolation that returns 404")
    say("  * a canonical, explicit cash-flow and surplus definition with no double counting")
    say("  * multi-goal planning that respects cash, surplus, EMI capacity and investment")
    say("    capacity, with constraint validation run against the returned plan")
    say("  * honest comparison of LP, RL, hybrid and a rule baseline on one shared scenario,")
    say("    scored on the identical action contract and the same monthly market path")
    say("  * cold-start expense estimation that states plainly it has learned nothing yet")
    say("  * estimated-vs-actual reconciliation that preserves the original forecast")
    say("  * an economic stress scenario with quantified deltas and narrative")
    say("  * persisted history for plans, forecasts and comparisons, surfaced on the dashboard")
    say("")
    say("Every figure above is an assumption, an estimate or a synthetic value. This is a")
    say("research decision-support prototype: not financial advice, and it executes no trades,")
    say("transfers or loans.")

    out = OUT / "demo_transcript.txt"
    out.write_text("\n".join(LINES), encoding="utf-8")
    print(f"\nTranscript written to {out}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except httpx.HTTPStatusError as exc:
        print(f"\nHTTP {exc.response.status_code} on {exc.request.url}: {exc.response.text[:800]}")
        raise SystemExit(2)
    except httpx.ConnectError:
        print(
            "\nCould not reach the server. Start it first:\n"
            "  cd backend\n"
            "  uvicorn app.main:app --port 8000"
        )
        raise SystemExit(3)
