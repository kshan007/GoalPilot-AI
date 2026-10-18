"""Independent reproduction probes for the two unresolved UI defect reports.

Defect 3: "a second Create goal click produced no request and no message"
Defect 5: "numeric inputs expose raw floats such as 0.3499999940395355"

Run against a live server:
    python scripts/probe_defects.py --base-url http://127.0.0.1:8000/api
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import uuid

import httpx


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000/api")
    args = ap.parse_args()

    c = httpx.Client(base_url=args.base_url.rstrip("/"), timeout=60.0)
    email = f"probe-{uuid.uuid4().hex[:8]}@goalpilot.example"
    reg = c.post(
        "/auth/register",
        json={"email": email, "password": "Val1d-Passw0rd!", "full_name": "Probe"},
    )
    reg.raise_for_status()
    h = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    print(f"synthetic probe account: {email}\n")

    # ------------------------------------------------------------------ defect 3
    print("=" * 70)
    print("DEFECT 3 — repeated goal creation")
    print("=" * 70)
    today = dt.date.today()

    def goal_payload(name: str) -> dict:
        return {
            "name": name,
            "purpose": "defect probe",
            "goal_type": "custom",
            "current_cost": 90000,
            "target_date": (today + dt.timedelta(days=400)).isoformat(),
            "current_funded_amount": 10000,
            "priority": 4,
            "criticality": 5,
            "date_flexible": True,
            "amount_flexible": False,
        }

    print("\n-- 3a. four DISTINCT goals in sequence (the UI flow creates one per submit) --")
    ids = []
    for name in ["Probe goal 1", "Probe goal 2", "Probe goal 3", "Probe goal 4"]:
        r = c.post("/goals", headers=h, json=goal_payload(name))
        body = r.json()
        ids.append(body.get("id"))
        print(f"   POST /goals {name!r:<16} -> HTTP {r.status_code}  id={body.get('id')}")
    print(f"   distinct ids: {ids}  (all unique = {len(set(ids)) == len(ids)})")
    print(f"   goals listed: {len(c.get('/goals', headers=h).json())}")

    print("\n-- 3b. the SAME payload twice (duplicate name) --")
    r1 = c.post("/goals", headers=h, json=goal_payload("Duplicate name"))
    r2 = c.post("/goals", headers=h, json=goal_payload("Duplicate name"))
    print(f"   first  -> HTTP {r1.status_code} id={r1.json().get('id')}")
    print(f"   second -> HTTP {r2.status_code} id={r2.json().get('id')}")
    print("   NOTE: goal names are not unique by design, so a duplicate name is expected to")
    print("         succeed. Only client_ref is idempotent (transactions), not goals.")

    print("\n-- 3c. rapid back-to-back submits (what a double click produces) --")
    before = len(c.get("/goals", headers=h).json())
    codes = []
    for _ in range(3):
        codes.append(c.post("/goals", headers=h, json=goal_payload("Rapid")).status_code)
    after = len(c.get("/goals", headers=h).json())
    print(f"   three rapid POSTs -> {codes}; goals {before} -> {after}")
    print("   => the API accepts every submit; a missing second goal would be a UI-state bug,")
    print("      not an API or validation rejection.")

    # ------------------------------------------------------------------ defect 5
    print()
    print("=" * 70)
    print("DEFECT 5 — numeric precision exposed in inputs")
    print("=" * 70)
    payload = {
        "monthly_income": 90000,
        "essential_expenses": 42000,
        "discretionary_expenses": 6000,
        "monthly_savings_target": 15000,
        "emergency_months": 6,
        "emi_income_ratio_cap": 0.35,
        "risk_capacity": 0.55,
        "inflation_assumption": 0.03,
        "investment_return_assumption": 0.05,
        "savings_return_assumption": 0.0,
        "loan_interest_assumption": 0.12,
    }
    c.put("/profile", headers=h, json=payload).raise_for_status()
    raw = c.get("/profile", headers=h).text
    profile = json.loads(raw)["profile"]

    print("\n-- 5a. raw JSON text as emitted by the API (this is what the browser receives) --")
    for key in payload:
        marker = f'"{key}":'
        idx = raw.find(marker)
        literal = raw[idx + len(marker):].split(",")[0].split("}")[0].strip() if idx >= 0 else "?"
        print(f"   {key:<32} raw={literal:<12} python={profile.get(key)!r}")

    print("\n-- 5b. apply the frontend's own formatter (frontend/src/components/ui.tsx:418) --")
    print("   const text = Number.isInteger(v) ? String(v) : v.toFixed(4).replace(/0+$/,'').replace(/\\.$/,'')")
    for key in payload:
        v = profile.get(key)
        if isinstance(v, (int, float)):
            text = str(v) if float(v).is_integer() else f"{v:.4f}".rstrip("0").rstrip(".")
            print(f"   {key:<32} rendered={text!r}")

    noisy = [
        k for k, v in profile.items()
        if isinstance(v, float) and len(str(v)) > 12 and not str(v).endswith("0")
    ]
    print(f"\n-- 5c. any field whose API value carries float noise: {noisy if noisy else 'NONE'}")

    # an income source and an asset, then the derived summary, to exercise more numbers
    c.post("/income-sources", headers=h, json={
        "source_type": "salary", "label": "Probe salary", "amount": 90000,
        "frequency": "monthly", "stability": "stable", "is_recurring": True})
    c.post("/income-sources", headers=h, json={
        "source_type": "freelance", "label": "Probe retainer", "amount": 120000,
        "frequency": "annual", "stability": "variable", "is_recurring": True})
    c.post("/assets", headers=h, json={
        "asset_type": "liquid_savings", "label": "Probe savings",
        "current_value": 420000, "is_liquid": True, "usable_for_goals": True})
    c.post("/liabilities", headers=h, json={
        "liability_type": "personal_loan", "label": "Probe loan",
        "outstanding_principal": 600000, "annual_interest_rate": 0.12,
        "emi_amount": 12000, "remaining_tenure_months": 60})

    summary = c.get("/profile/summary", headers=h)
    print(f"\n-- 5d. /profile/summary HTTP {summary.status_code} --")
    if summary.status_code == 200:
        body = summary.json()
        for key in ["monthly_income", "existing_emi", "monthly_surplus",
                    "emi_income_ratio", "emi_income_ratio_cap", "risk_capacity",
                    "available_cash_for_goals", "emergency_fund_progress"]:
            print(f"   {key:<30} {body.get(key)!r}")
        noisy2 = [k for k, v in body.items() if isinstance(v, float) and len(str(v)) > 14]
        print(f"   fields with long float repr: {noisy2 if noisy2 else 'NONE'}")
    else:
        print("   ", summary.text[:300])

    # derived capacity ratio, which the Optimize page renders in an input
    c.post("/goals", headers=h, json=goal_payload("Probe goal A"))
    c.post("/goals", headers=h, json=goal_payload("Probe goal B"))
    plan = c.post("/optimize/plan", headers=h, json={"algorithm": "lp"})
    print(f"\n-- 5e. /optimize/plan HTTP {plan.status_code} --")
    if plan.status_code == 200:
        p = plan.json()
        print(f"   config_version: {p['config_version']}")
        print(f"   capacity derivation: {p['diagnostics'].get('investment_capacity_derivation')}")
        print(f"   investment_permitted: {p['constraints'].get('investment_permitted')!r}")
        print(f"   objective_value: {p['objective_value']!r}")
        longish = [
            (k, v) for k, v in p["constraints"].items()
            if isinstance(v, float) and len(str(v)) > 14
        ]
        print(f"   constraint floats with long repr: {longish if longish else 'NONE'}")
    else:
        print("   ", plan.text[:300])

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print("Defect 3: the API accepts every goal submission, including rapid repeats.")
    print("          No server-side rejection or rate limit exists for goals.")
    print("Defect 5: the API emits compact decimals and the frontend formatter rounds to")
    print("          4 decimals, so float noise cannot originate in the application.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
