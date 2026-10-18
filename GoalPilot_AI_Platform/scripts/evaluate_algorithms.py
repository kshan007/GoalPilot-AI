"""Cross-profile comparison of every planning arm, on identical inputs.

This is the evidence behind `docs/ALGORITHM_EVALUATION.md`. It does **not** train anything: it
loads the existing checkpoints, runs the real comparison service for several synthetic
households, and aggregates the per-arm metrics the service already computes.

    python scripts/evaluate_algorithms.py

Writes `outputs/algorithm_evaluation.json` and prints a summary table.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import statistics
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="goalpilot-eval-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(TMP / 'eval.db').as_posix()}"
os.environ["GOALPILOT_ENV"] = "test"
os.environ["SECRET_KEY"] = "eval-secret-key-0123456789-abcdefghijklmnop"
os.environ["BCRYPT_ROUNDS"] = "4"
os.environ["RATE_LIMIT_AUTH_PER_MINUTE"] = "0"
os.environ["RATE_LIMIT_OPTIMIZE_PER_MINUTE"] = "0"
os.environ.setdefault("GOALPILOT_ENABLE_LIVE_PROVIDERS", "false")
os.environ.setdefault("GOALPILOT_ENABLE_MFAPI_HISTORY", "false")
os.environ.setdefault("GOALPILOT_ENABLE_LLM", "false")

sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

#: Five households chosen to span the failure modes that matter: a deficit, a thin surplus, a
#: comfortable surplus, a large mandatory buffer, and a single urgent goal.
CASES = [
    {
        "name": "deficit_household",
        "income": 45_000, "essential": 38_000, "discretionary": 9_000, "emi": 4_000,
        "buffer": 2_000, "mandatory": False, "risk": 0.25,
        "goals": [("Emergency cushion", 150_000, 540, 5)],
    },
    {
        "name": "thin_surplus_three_goals",
        "income": 70_000, "essential": 42_000, "discretionary": 8_000, "emi": 0,
        "buffer": 8_000, "mandatory": False, "risk": 0.4,
        "goals": [
            ("Child education", 1_200_000, 2200, 5),
            ("Car", 500_000, 900, 3),
            ("Holiday", 200_000, 400, 2),
        ],
    },
    {
        "name": "comfortable_surplus_four_goals",
        "income": 250_000, "essential": 70_000, "discretionary": 25_000, "emi": 12_000,
        "buffer": 30_000, "mandatory": False, "risk": 0.6,
        "goals": [
            ("Home down payment", 3_000_000, 2600, 5),
            ("Child education", 2_000_000, 4000, 4),
            ("Retirement bridge", 1_500_000, 5000, 5),
            ("Vehicle", 900_000, 1200, 2),
        ],
    },
    {
        "name": "mandatory_buffer_above_capacity",
        "income": 80_000, "essential": 40_000, "discretionary": 10_000, "emi": 6_000,
        "buffer": 30_000, "mandatory": True, "risk": 0.45,
        "goals": [
            ("Wedding", 800_000, 700, 4),
            ("Travel", 300_000, 365, 2),
        ],
    },
    {
        "name": "single_urgent_goal",
        "income": 120_000, "essential": 45_000, "discretionary": 10_000, "emi": 0,
        "buffer": 15_000, "mandatory": False, "risk": 0.35,
        "goals": [("Medical reserve", 400_000, 180, 5)],
    },
]

#: Metrics worth aggregating, by the substring of the key the service uses.
INTERESTING = (
    "achievement", "shortfall", "feasib", "violation", "buffer", "liquid",
    "emi", "debt", "runtime", "score", "objective", "cost",
)


def _numeric_metrics(arm: dict) -> dict[str, float]:
    """Scalar metrics from the arm envelope *and* its nested ``metrics`` block.

    The comparison service returns outcome metrics under ``metrics`` and status/feasibility on
    the envelope, so both are read; reading only the envelope silently produced a table of NaNs.
    """
    out: dict[str, float] = {}
    for source in (arm, arm.get("metrics") or {}):
        for key, value in source.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            lowered = key.lower()
            if any(token in lowered for token in INTERESTING):
                out[key] = float(value)
    if isinstance(arm.get("feasible"), bool):
        out["feasible"] = 1.0 if arm["feasible"] else 0.0
    return out


def main() -> int:
    today = dt.date.today()
    results: list[dict] = []
    with TestClient(app) as client:
        for index, case in enumerate(CASES):
            email = f"eval{index}@example.com"
            reg = client.post(
                "/api/auth/register",
                json={"email": email, "password": "Str0ng-Passw0rd!", "full_name": case["name"]},
            )
            if reg.status_code != 200:
                print(f"skip {case['name']}: register failed {reg.text[:120]}")
                continue
            auth = {"Authorization": f"Bearer {reg.json()['access_token']}"}
            client.put(
                "/api/profile",
                headers=auth,
                json={
                    "monthly_income": case["income"],
                    "essential_expenses": case["essential"],
                    "discretionary_expenses": case["discretionary"],
                    "monthly_savings_target": case["buffer"],
                    "preferred_cash_buffer": case["buffer"],
                    "savings_target_is_mandatory": case["mandatory"],
                    "emergency_months": 6,
                    "emi_income_ratio_cap": 0.35,
                    "risk_capacity": case["risk"],
                    "inflation_assumption": 0.03,
                    "investment_return_assumption": 0.05,
                    "savings_return_assumption": 0.0,
                    "loan_interest_assumption": 0.11,
                },
            )
            client.post(
                "/api/income-sources",
                headers=auth,
                json={
                    "source_type": "salary", "label": "Salary",
                    "amount": case["income"], "frequency": "monthly",
                },
            )
            if case["emi"]:
                client.post(
                    "/api/liabilities",
                    headers=auth,
                    json={
                        "liability_type": "personal_loan", "label": "Existing EMI",
                        "outstanding_principal": case["emi"] * 30,
                        "annual_interest_rate": 0.12, "emi_amount": case["emi"],
                        "remaining_tenure_months": 30,
                    },
                )
            for name, cost, days, priority in case["goals"]:
                client.post(
                    "/api/goals",
                    headers=auth,
                    json={
                        "name": name, "purpose": "", "goal_type": "custom",
                        "current_cost": cost,
                        "target_date": (today + dt.timedelta(days=days)).isoformat(),
                        "current_funded_amount": 20_000, "priority": priority,
                        "criticality": 3, "date_flexible": True, "amount_flexible": True,
                    },
                )
            comparison = client.post("/api/optimize/compare", headers=auth)
            if comparison.status_code != 200:
                print(f"skip {case['name']}: compare failed {comparison.text[:160]}")
                continue
            body = comparison.json()
            summary = client.get("/api/profile/summary", headers=auth).json()
            arms = []
            for arm in body.get("arms", []):
                arms.append(
                    {
                        "algorithm": arm.get("algorithm"),
                        "available": arm.get("available", True),
                        "status": arm.get("status"),
                        "metrics": _numeric_metrics(arm),
                    }
                )
            results.append(
                {
                    "case": case["name"],
                    "inputs": {
                        "income": case["income"],
                        "essential": case["essential"],
                        "discretionary": case["discretionary"],
                        "existing_emi": case["emi"],
                        "requested_buffer": case["buffer"],
                        "mandatory": case["mandatory"],
                        "goals": len(case["goals"]),
                    },
                    "derived": {
                        "monthly_surplus": summary["monthly_surplus"],
                        "protected_buffer": summary["protected_buffer"],
                        "available_goal_budget": summary["available_goal_budget"],
                        "buffer_sustained": summary["buffer_sustained"],
                    },
                    "selected_algorithm": body.get("recommended_algorithm")
                    or body.get("selected_algorithm"),
                    "arms": arms,
                }
            )
            print(f"evaluated {case['name']}: {len(arms)} arms")

    # ---------------------------------------------------------------- aggregate
    by_arm: dict[str, list[dict[str, float]]] = {}
    availability: dict[str, int] = {}
    for row in results:
        for arm in row["arms"]:
            name = str(arm["algorithm"])
            if arm["available"]:
                availability[name] = availability.get(name, 0) + 1
                by_arm.setdefault(name, []).append(arm["metrics"])

    aggregate: dict[str, dict[str, float | int]] = {}
    for name, metric_rows in by_arm.items():
        keys = set().union(*[set(row) for row in metric_rows]) if metric_rows else set()
        entry: dict[str, float | int] = {"cases_available": len(metric_rows)}
        for key in sorted(keys):
            values = [row[key] for row in metric_rows if key in row]
            if values:
                entry[key] = round(statistics.fmean(values), 6)
        aggregate[name] = entry

    selections: dict[str, int] = {}
    for row in results:
        selected = row.get("selected_algorithm")
        if selected:
            selections[str(selected)] = selections.get(str(selected), 0) + 1

    payload = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "note": (
            "In-app comparison on identical inputs per household. Existing checkpoints were loaded, "
            "not retrained. Metrics are the ones the comparison service computes; no external "
            "benchmark was downloaded."
        ),
        "cases": results,
        "aggregate_by_arm": aggregate,
        "availability_by_arm": availability,
        "selector_choices": selections,
        "caveat": (
            "Five synthetic households is a smoke-level sweep, not a statistically meaningful "
            "benchmark. The PPO checkpoint predates the protected-buffer change to the "
            "environment, so RL and hybrid results reflect inference with a stale policy."
        ),
    }

    out = ROOT / "outputs" / "algorithm_evaluation.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print("\narm                     cases  achievement  shortfall  feasible")
    for name, entry in sorted(aggregate.items()):
        print(
            f"{name:<22} {entry.get('cases_available', 0):>5}  "
            f"{entry.get('weighted_goal_achievement', float('nan')):>11.4f}  "
            f"{entry.get('total_shortfall', float('nan')):>9.0f}  "
            f"{entry.get('feasible', float('nan')):>8}"
        )
    print(f"\nselector choices: {selections}")
    print(f"written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
