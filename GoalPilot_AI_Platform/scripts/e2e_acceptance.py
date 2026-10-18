"""End-to-end acceptance walk-through against the real API, on a throwaway SQLite database.

Run from the repository root:

    python scripts/e2e_acceptance.py

It exercises the acceptance criterion directly: a realistic profile, several goals, a protected
savings buffer, sourced investment and loan options, a constraint-checked plan, a structured
explanation, and a recalculation after the household's income falls.

Exit code 0 means every step passed. Providers stay offline unless GOALPILOT_E2E_LIVE=1 is set,
so the result is reproducible.

Note on the income shock: the authoritative income is the recorded income stream, not the
`monthly_income` field on the profile (that field is only a fallback when no stream exists). The
shock below therefore edits the income source — changing the profile field alone correctly has
no effect.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="goalpilot-e2e-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(TMP / 'e2e.db').as_posix()}"
os.environ["GOALPILOT_ENV"] = "test"
os.environ["SECRET_KEY"] = "e2e-secret-key-0123456789-abcdefghijklmnop"
os.environ["BCRYPT_ROUNDS"] = "4"
os.environ["RATE_LIMIT_AUTH_PER_MINUTE"] = "0"
os.environ["RATE_LIMIT_OPTIMIZE_PER_MINUTE"] = "0"
os.environ.setdefault("GOALPILOT_ENABLE_LIVE_PROVIDERS", "false")
os.environ.setdefault("GOALPILOT_ENABLE_MFAPI_HISTORY", "false")
os.environ.setdefault("GOALPILOT_ENABLE_LLM", "false")
os.environ.pop("GEMINI_API_KEY", None)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

RESULTS: list[tuple[bool, str, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    RESULTS.append((bool(condition), name, detail))
    suffix = f"  [{detail}]" if detail and not condition else ""
    print(f"{'PASS' if condition else 'FAIL'}  {name}{suffix}")


PROFILE = {
    "monthly_income": 120000,
    "essential_expenses": 45000,
    "discretionary_expenses": 10000,
    "monthly_savings_target": 15000,
    "preferred_cash_buffer": 8000,
    "emergency_months": 6,
    "emi_income_ratio_cap": 0.35,
    "risk_capacity": 0.55,
    "inflation_assumption": 0.03,
    "investment_return_assumption": 0.05,
    "savings_return_assumption": 0.0,
    "loan_interest_assumption": 0.11,
}


def main() -> int:
    today = dt.date.today()
    with TestClient(app) as client:
        # 1 ---------------------------------------------------------------- registration
        reg = client.post(
            "/api/auth/register",
            json={"email": "e2e@example.com", "password": "Str0ng-Passw0rd!", "full_name": "E2E User"},
        )
        check("registration", reg.status_code == 200, reg.text[:200])
        auth = {"Authorization": f"Bearer {reg.json()['access_token']}"}
        check("login/identity", client.get("/api/auth/me", headers=auth).status_code == 200)

        # 2 ------------------------------------------------------- profile and buffer
        profile = client.put("/api/profile", headers=auth, json=PROFILE)
        check("financial profile saved", profile.status_code == 200, profile.text[:200])

        income = client.post(
            "/api/income-sources",
            headers=auth,
            json={"source_type": "salary", "label": "Salary", "amount": 120000, "frequency": "monthly"},
        )
        check("income stream recorded", income.status_code == 201, income.text[:200])
        income_id = income.json().get("id") if income.status_code == 201 else None

        client.post(
            "/api/assets",
            headers=auth,
            json={
                "asset_type": "liquid_savings",
                "label": "Savings",
                "current_value": 300000,
                "is_liquid": True,
                "usable_for_goals": True,
            },
        )
        liability = client.post(
            "/api/liabilities",
            headers=auth,
            json={
                "liability_type": "personal_loan",
                "label": "Existing PL",
                "outstanding_principal": 200000,
                "annual_interest_rate": 0.12,
                "emi_amount": 6000,
                "remaining_tenure_months": 40,
            },
        )
        check("liability recorded", liability.status_code == 201, liability.text[:200])

        summary = client.get("/api/profile/summary", headers=auth).json()
        check(
            "buffer is protected and separated from the goal budget",
            summary["protected_buffer"] == 15000
            and summary["available_goal_budget"] == summary["monthly_surplus"] - 15000,
            json.dumps({k: summary[k] for k in ("monthly_surplus", "protected_buffer", "available_goal_budget")}),
        )

        # 3 ------------------------------------------------------------ multiple goals
        goal_ids = []
        for name, cost, days, pri in (
            ("Child education", 1_200_000, 2200, 5),
            ("Car down payment", 400_000, 900, 3),
            ("Home renovation", 600_000, 1500, 4),
        ):
            created = client.post(
                "/api/goals",
                headers=auth,
                json={
                    "name": name,
                    "purpose": "",
                    "goal_type": "custom",
                    "current_cost": cost,
                    "target_date": (today + dt.timedelta(days=days)).isoformat(),
                    "current_funded_amount": 25000,
                    "priority": pri,
                    "criticality": 3,
                    "date_flexible": True,
                    "amount_flexible": True,
                },
            )
            check(f"goal created: {name}", created.status_code == 201, created.text[:160])
            if created.status_code == 201:
                goal_ids.append(created.json()["id"])
        check("three goals exist", len(goal_ids) == 3)

        projections = client.get("/api/goals/plan", headers=auth)
        check(
            "goal feasibility projections",
            projections.status_code == 200 and len(projections.json()) == 3,
            projections.text[:200],
        )

        # 4 ------------------------------------------------------ multi-goal allocation
        plan = client.post("/api/optimize/plan", headers=auth, json={"algorithm": "lp"})
        check("LP plan generated", plan.status_code == 200, plan.text[:200])
        body = plan.json() if plan.status_code == 200 else {}
        allocations = body.get("allocations", [])
        funded = [
            a
            for a in allocations
            if a["monthly_savings_contribution"] + a["monthly_investment_contribution"] > 0.5
        ]
        total = sum(
            a["monthly_savings_contribution"] + a["monthly_investment_contribution"] for a in allocations
        )
        check("more than one goal is funded simultaneously", len(funded) >= 2, f"funded={len(funded)}")
        check(
            "plan stays inside the goal budget after the buffer",
            total <= summary["available_goal_budget"] + 1.0,
            f"total={total} budget={summary['available_goal_budget']}",
        )
        check(
            "plan exposes the buffer in its constraints",
            body.get("constraints", {}).get("protected_buffer") == 15000,
            str(body.get("constraints", {}).get("protected_buffer")),
        )

        # 5 ------------------------------------------------------ algorithm comparison
        comparison = client.post("/api/optimize/compare", headers=auth)
        check("algorithm comparison runs", comparison.status_code == 200, comparison.text[:200])
        if comparison.status_code == 200:
            arms = {arm["algorithm"]: arm for arm in comparison.json().get("arms", [])}
            check("at least three arms were evaluated", len(arms) >= 3, str(list(arms)))
            check("LP remains available as an arm", "lp" in arms, str(list(arms)))

        # 6 -------------------------------------------------------- investments
        investments = client.get("/api/investments/discover?limit=8", headers=auth)
        check("investment discovery", investments.status_code == 200, investments.text[:200])
        if investments.status_code == 200:
            payload = investments.json()
            check("investment options returned", len(payload["options"]) > 0)
            check(
                "every option carries provenance",
                all(o["data_quality"] and "freshness" in o for o in payload["options"]),
            )
            check(
                "no scenario pretends to be a product",
                all(o["nav"] is None for o in payload["options"] if o["data_quality"] == "category_scenario"),
            )

        # 7 --------------------------------------------------------------- loans
        loans = client.get("/api/loans/discover?principal=500000&tenure_months=48", headers=auth)
        check("loan discovery", loans.status_code == 200, loans.text[:200])
        if loans.status_code == 200:
            loan_body = loans.json()
            check(
                "published products or labelled scenarios present",
                bool(loan_body["options"] or loan_body["scenarios"]),
            )
            check(
                "every loan row states its rate class",
                all("rate_class" in row for row in loan_body["options"] + loan_body["scenarios"]),
            )
            check("historical benchmark reported", len(loan_body["benchmarks"]) >= 1)

        analysis = client.post(
            "/api/loans/analyse",
            headers=auth,
            json={
                "principal": 500000,
                "annual_rate": 0.105,
                "tenure_months": 48,
                "processing_fee_pct": 0.01,
                "rate_type": "floating",
                "include_schedule": True,
            },
        )
        check("loan analysis", analysis.status_code == 200, analysis.text[:200])
        if analysis.status_code == 200:
            analysed = analysis.json()
            check(
                "APR exceeds the nominal rate once fees are included",
                analysed["repayment"]["apr_including_fees"] > 0.105,
            )
            check("rate-shock sensitivity computed", len(analysed["rate_sensitivity"]["rows"]) == 4)
            check("save-versus-borrow alternatives offered", len(analysed["alternatives"]) >= 3)

        # 8 ------------------------------------------------- structured explanation
        rec = client.post("/api/recommendations/generate", headers=auth, json={})
        check("recommendation generated", rec.status_code == 200, rec.text[:300])
        recommendation = rec.json() if rec.status_code == 200 else {}
        required = {
            "financial_summary",
            "cash_flow_status",
            "protected_buffer",
            "available_goal_budget",
            "goal_recommendations",
            "investment_options",
            "loan_options",
            "recommended_plan",
            "alternative_scenarios",
            "risks_and_warnings",
            "data_sources",
            "assumptions",
            "missing_information",
            "monthly_actions",
            "explanation",
            "disclaimer",
        }
        check("response matches the structured contract", required <= set(recommendation))
        check(
            "explanation states whether a model was used",
            isinstance(recommendation.get("llm"), dict) and "used" in recommendation.get("llm", {}),
        )
        check(
            "no goal is claimed funded while short",
            all(
                g["expected_shortfall"] <= 1.0
                for g in recommendation.get("goal_recommendations", [])
                if g["funding_status"] == "fully_funded"
            ),
        )

        latest = client.get("/api/recommendations/latest", headers=auth)
        check("recommendation persisted", latest.status_code == 200)
        if latest.status_code == 200:
            check(
                "persisted payload is not type-corrupted",
                isinstance(latest.json()["cash_flow_status"], dict),
            )

        # 9 ------------------------------------------ changed circumstances -> replan
        before_budget = summary["available_goal_budget"]
        if income_id is not None:
            shock = client.put(
                f"/api/income-sources/{income_id}",
                headers=auth,
                json={
                    "source_type": "salary",
                    "label": "Salary",
                    "amount": 90000,
                    "frequency": "monthly",
                },
            )
            check("income shock applied to the income stream", shock.status_code == 200, shock.text[:200])
        after = client.get("/api/profile/summary", headers=auth).json()
        after_budget = after["available_goal_budget"]
        check("income shock reduces the goal budget", after_budget < before_budget, f"{before_budget} -> {after_budget}")
        check(
            "the buffer survives the shock",
            after["protected_buffer"] == 15000,
            str(after["protected_buffer"]),
        )

        replan = client.post("/api/optimize/plan", headers=auth, json={"algorithm": "lp"})
        check("replanning after the shock succeeds", replan.status_code == 200, replan.text[:200])
        if replan.status_code == 200:
            new_body = replan.json()
            new_total = sum(
                a["monthly_savings_contribution"] + a["monthly_investment_contribution"]
                for a in new_body["allocations"]
            )
            check("replanned total contribution falls with the income", new_total < total + 1e-6, f"{total} -> {new_total}")
            check("replan records a diff against the previous plan", new_body.get("diff") is not None)

        rec2 = client.post("/api/recommendations/generate", headers=auth, json={})
        check("recommendation regenerates on the new state", rec2.status_code == 200, rec2.text[:200])
        if rec2.status_code == 200 and recommendation:
            check(
                "the revised plan is not a copy of the old one",
                rec2.json()["available_goal_budget"] != recommendation["available_goal_budget"],
                f"{recommendation['available_goal_budget']} -> {rec2.json()['available_goal_budget']}",
            )

        # 10 ------------------------------------------------------------ isolation
        other = client.post(
            "/api/auth/register",
            json={"email": "e2e-other@example.com", "password": "Str0ng-Passw0rd!", "full_name": "Other"},
        )
        other_auth = {"Authorization": f"Bearer {other.json()['access_token']}"}
        leak = client.get(f"/api/recommendations/{recommendation.get('run_id')}", headers=other_auth)
        check("another user cannot read this recommendation", leak.status_code in (403, 404), str(leak.status_code))
        leak2 = client.get("/api/goals", headers=other_auth)
        check("another user sees no goals", leak2.status_code == 200 and leak2.json() == [], leak2.text[:120])

    failed = [name for ok, name, _ in RESULTS if not ok]
    print("\n" + "=" * 78)
    print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    if failed:
        print("FAILED: " + "; ".join(failed))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
