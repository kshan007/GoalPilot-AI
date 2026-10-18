"""Diagnose the two anomalies found by 70_large_csv_validation.py.

A1: 601,744 / 1,430,000 rows have monthly_surplus != income - expenditure - emi
A3: 2 / 1,430,000 rows have portfolio_value != prev * (1 + portfolio_return)

Reads the base simulation file in chunks and reports:
  - whether monthly_surplus is constant per user, and whether monthly_emi varies per user
  - the joint pattern of (surplus identity fails?) x (emi != 0)
  - worked examples of failing rows
  - the exact (user, period) of the A3 failures with prev/expected/actual
  - a correct user count

Outputs: outputs/audit/large_csv_validation_v1/anomaly_diagnosis.json
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from goalpilot_paths import ProjectPaths  # noqa: E402

paths = ProjectPaths.resolve()
BASE_CSV = paths.simulation / "05_simulation_runs" / "monthly_financial_simulation_base.csv"
OUT = paths.root / "outputs" / "audit" / "large_csv_validation_v1"
OUT.mkdir(parents=True, exist_ok=True)

CHUNKSIZE = 250_000

surplus_nunique: dict[str, int] = {}
emi_nunique: dict[str, int] = {}
surplus_first: dict[str, float] = {}
emi_zero_rows = 0
emi_nonzero_rows = 0
fail_rows_total = 0
fail_rows_alt = 0
fail_with_emi_zero = 0
fail_with_emi_nonzero = 0
examples: list[dict] = []
# pattern: fail_flag x emi_zero_flag
pattern = Counter()

prev_pv: dict[str, float] = {}
a3_failures: list[dict] = []
all_users: set[str] = set()

for chunk in pd.read_csv(BASE_CSV, chunksize=CHUNKSIZE, low_memory=False):
    uid = chunk["user_id"].astype(str)
    inc = chunk["monthly_income"].to_numpy(dtype=float)
    exp = chunk["monthly_expenditure"].to_numpy(dtype=float)
    emi = chunk["monthly_emi"].to_numpy(dtype=float)
    surp = chunk["monthly_surplus"].to_numpy(dtype=float)
    pl = chunk["portfolio_value"].to_numpy(dtype=float)
    pr = chunk["portfolio_return"].to_numpy(dtype=float)
    ini = chunk["initial_investment"].to_numpy(dtype=float)
    periods = chunk["period"].astype(str).to_numpy()
    uids = uid.to_numpy()

    all_users.update(uids.tolist())

    expected = inc - exp - emi
    allowed = 1e-6 + 1e-6 * np.abs(expected)
    fail = np.abs(surp - expected) > allowed
    fail_rows_total += int(fail.sum())

    # alternative hypothesis: surplus == income - expenditure (EMI excluded)
    alt = inc - exp
    fail_alt = np.abs(surp - alt) > (1e-6 + 1e-6 * np.abs(alt))
    fail_rows_alt += int(fail_alt.sum())
    emi_zero = emi == 0.0
    emi_zero_rows += int(emi_zero.sum())
    emi_nonzero_rows += int((~emi_zero).sum())
    fail_with_emi_zero += int((fail & emi_zero).sum())
    fail_with_emi_nonzero += int((fail & ~emi_zero).sum())
    for f, z in zip(fail.tolist(), emi_zero.tolist()):
        pattern[(bool(f), bool(z))] += 1

    if len(examples) < 6:
        for i in np.where(fail)[0][:6 - len(examples)]:
            examples.append({
                "user_id": uids[i], "period": periods[i],
                "monthly_income": float(inc[i]), "monthly_expenditure": float(exp[i]),
                "monthly_emi": float(emi[i]), "monthly_surplus": float(surp[i]),
                "income_minus_exp_minus_emi": float(expected[i]),
                "deviation": float(surp[i] - expected[i]),
            })

    g = pd.DataFrame({"u": uids, "s": surp, "e": emi}).groupby("u", sort=False).agg(
        s_n=("s", "nunique"), e_n=("e", "nunique"), s0=("s", "first"))
    for u, row in g.iterrows():
        surplus_nunique[u] = max(surplus_nunique.get(u, 0), int(row["s_n"]))
        emi_nunique[u] = max(emi_nunique.get(u, 0), int(row["e_n"]))
        surplus_first.setdefault(u, float(row["s0"]))

    # A3
    same = uids[1:] == uids[:-1]
    exp_pv = np.empty(len(chunk))
    exp_pv[1:] = np.where(same, pl[:-1] * (1.0 + pr[1:]), np.nan)
    first_idx = np.where(np.concatenate(([True], ~same)))[0]
    for i in first_idx:
        u = uids[i]
        anchor = prev_pv.get(u, ini[i])
        exp_pv[i] = anchor * (1.0 + pr[i])
    good = np.isfinite(exp_pv)
    dev = np.abs(pl - exp_pv)
    bad = good & (dev > 1e-6 + 1e-6 * np.abs(exp_pv))
    for i in np.where(bad)[0]:
        a3_failures.append({
            "user_id": uids[i], "period": periods[i],
            "prev_value": (float(pl[i - 1]) if i > 0 and same[i - 1]
                           else float(prev_pv.get(uids[i], ini[i]))),
            "portfolio_return": float(pr[i]),
            "expected": float(exp_pv[i]), "actual": float(pl[i]),
        })
    for i in range(len(chunk)):
        prev_pv[uids[i]] = float(pl[i])

result = {
    "rows": int(emi_zero_rows + emi_nonzero_rows),
    "n_users": len(all_users),
    "A1": {
        "fail_rows": fail_rows_total,
        "fail_rows_alt_surplus_eq_income_minus_expenditure": fail_rows_alt,
        "fail_fraction": fail_rows_total / max(1, emi_zero_rows + emi_nonzero_rows),
        "fail_with_emi_zero": fail_with_emi_zero,
        "fail_with_emi_nonzero": fail_with_emi_nonzero,
        "pattern_fail_x_emi_zero": {f"fail={k[0]},emi_zero={k[1]}": v
                                    for k, v in sorted(pattern.items())},
        "users_with_nonconstant_surplus": int(sum(1 for v in surplus_nunique.values() if v > 1)),
        "users_with_nonconstant_emi": int(sum(1 for v in emi_nunique.values() if v > 1)),
        "users_total": len(surplus_nunique),
        "examples": examples,
    },
    "A3": {"n_failures": len(a3_failures), "failures": a3_failures},
}
(OUT / "anomaly_diagnosis.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result, indent=2))
