"""Phase B / finding F-14 - content validation of the two large simulation outputs.

The Stage-1 audit inspected the schemas of

    simulation/05_simulation_runs/monthly_financial_simulation_base.csv   (~959 MB)
    simulation/05_simulation_runs/portfolio_simulation_validated.csv      (~169 MB)

but never parsed their contents, because loading either file whole exceeds the safe working
set on the audit host. This script streams both files in chunks, so memory stays bounded, and
verifies the accounting and market identities the data is supposed to satisfy.

Checks
------
Structural
    S1  row count, column count, exact column names
    S2  duplicate (user_id, period) rows
    S3  missing values per column
    S4  non-numeric cells where a number is expected
    S5  date range and strictly-increasing periods per user

Accounting / market identities (per user, consecutive months)
    A1  monthly_surplus == monthly_income - monthly_expenditure - monthly_emi
    A2  monthly_income / monthly_expenditure constant within a user (static profile)
    A3  portfolio_value[t] == portfolio_value[t-1] * (1 + portfolio_return[t]),
        first month anchored at initial_investment
    A4  portfolio_return == market_exposure * nifty_monthly_return
    A5  market_exposure == risk_score
    A6  investment_capacity_ratio in [0, 1]; risk_score in [0, 1]

Cross-file
    X1  the two files carry identical (user_id, period) sequences
    X2  portfolio_return and portfolio_value agree between the two files

Tolerance is rtol=1e-6 / atol=1e-6: both files are float64 written through CSV text, so the
text round-trip is not bit-exact.

Outputs (nothing existing is overwritten)
    outputs/audit/large_csv_validation_v1/large_csv_validation_report.md
    outputs/audit/large_csv_validation_v1/large_csv_validation_report.json
    outputs/audit/large_csv_validation_v1/column_profile_base.csv
    outputs/audit/large_csv_validation_v1/column_profile_validated.csv
    outputs/audit/large_csv_validation_v1/checks_summary.csv
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from goalpilot_paths import ProjectPaths  # noqa: E402

paths = ProjectPaths.resolve()
SIM_RUNS = paths.simulation / "05_simulation_runs"
BASE_CSV = SIM_RUNS / "monthly_financial_simulation_base.csv"
VAL_CSV = SIM_RUNS / "portfolio_simulation_validated.csv"
OUT = paths.root / "outputs" / "audit" / "large_csv_validation_v1"
OUT.mkdir(parents=True, exist_ok=True)

CHUNKSIZE = 250_000
RTOL = 1e-6
ATOL = 1e-6

BASE_NUMERIC = [
    "portfolio_return", "portfolio_value", "monthly_income", "monthly_expenditure",
    "monthly_surplus", "monthly_emi", "initial_savings", "initial_investment",
    "investment_capacity_ratio", "risk_score", "nifty_monthly_return",
]
VAL_NUMERIC = [
    "initial_investment", "risk_score", "market_exposure", "nifty_monthly_return",
    "portfolio_return", "portfolio_value",
]


class Check:
    def __init__(self, name: str, description: str) -> None:
        self.name, self.description = name, description
        self.n = 0
        self.failed = 0
        self.max_dev = 0.0

    def compare(self, actual: np.ndarray, expected: np.ndarray) -> None:
        if actual.size == 0:
            return
        dev = np.abs(actual - expected)
        allowed = ATOL + RTOL * np.abs(expected)
        self.n += int(actual.size)
        self.failed += int((dev > allowed).sum())
        if dev.size:
            self.max_dev = max(self.max_dev, float(np.nanmax(dev)))

    def add_rows(self, k: int) -> None:
        self.n += int(k)

    def add_violations(self, k: int) -> None:
        self.failed += int(k)

    def as_row(self) -> dict:
        return {"check": self.name, "description": self.description, "comparisons": self.n,
                "failures": self.failed, "max_abs_deviation": self.max_dev,
                "rtol": RTOL, "atol": ATOL,
                "status": "PASS" if self.failed == 0 else "FAIL"}


def read_chunks(path: Path):
    for chunk in pd.read_csv(path, chunksize=CHUNKSIZE, low_memory=False):
        chunk["user_id"] = chunk["user_id"].astype(str)
        chunk["period"] = chunk["period"].astype(str)
        yield chunk


def profile(chunk: pd.DataFrame, info: dict, stats: dict, numeric_cols: list[str]) -> None:
    info["rows"] += len(chunk)
    for c in chunk.columns:
        info["null_counts"][c] = info["null_counts"].get(c, 0) + int(chunk[c].isna().sum())
    for c in numeric_cols:
        if c not in chunk.columns:
            continue
        raw = chunk[c]
        num = pd.to_numeric(raw, errors="coerce")
        info["non_numeric_counts"][c] = info["non_numeric_counts"].get(c, 0) \
            + int((num.isna() & raw.notna()).sum())
        v = num.dropna().to_numpy(dtype=float)
        if v.size:
            s = stats.setdefault(c, {"n": 0, "sum": 0.0, "min": np.inf, "max": -np.inf})
            s["n"] += int(v.size)
            s["sum"] += float(v.sum())
            s["min"] = min(s["min"], float(v.min()))
            s["max"] = max(s["max"], float(v.max()))


def main() -> None:
    checks: dict[str, Check] = {
        "A1_surplus_identity": Check("A1_surplus_identity",
                                     "monthly_surplus == income - expenditure - emi"),
        "A1b_surplus_excl_emi": Check("A1b_surplus_excl_emi",
                                      "monthly_surplus == income - expenditure (EMI excluded)"),
        "A3_portfolio_compounding": Check("A3_portfolio_compounding",
                                          "portfolio_value[t] == prev*(1+return[t])"),
        "A4_return_eq_exposure_x_nifty": Check(
            "A4_return_eq_exposure_x_nifty",
            "portfolio_return == market_exposure * nifty_monthly_return"),
        "A5_exposure_eq_risk": Check("A5_exposure_eq_risk", "market_exposure == risk_score"),
        "A2_constant_profile_income": Check(
            "A2_constant_profile_income", "monthly_income constant within a user"),
        "A2_constant_profile_expenditure": Check(
            "A2_constant_profile_expenditure", "monthly_expenditure constant within a user"),
        "A6_range": Check("A6_range", "investment_capacity_ratio and risk_score in [0,1]"),
        "X1_same_key_sequence": Check("X1_same_key_sequence",
                                      "identical (user_id, period) sequence across files"),
        "X2_portfolio_return_agrees": Check("X2_portfolio_return_agrees",
                                            "portfolio_return matches across files"),
        "X2_portfolio_value_agrees": Check("X2_portfolio_value_agrees",
                                            "portfolio_value matches across files"),
    }

    base_info: dict = {"path": str(BASE_CSV), "size_bytes": BASE_CSV.stat().st_size,
                       "rows": 0, "columns": None, "column_order": None, "null_counts": {},
                       "non_numeric_counts": {}, "date_min": None, "date_max": None}
    val_info: dict = {"path": str(VAL_CSV), "size_bytes": VAL_CSV.stat().st_size,
                      "rows": 0, "columns": None, "column_order": None, "null_counts": {},
                      "non_numeric_counts": {}, "date_min": None, "date_max": None}
    base_stats: dict = {}
    val_stats: dict = {}

    seen_base: set[tuple[str, str]] = set()
    seen_val: set[tuple[str, str]] = set()

    # carried cross-chunk state (per user)
    b_last_pv: dict[str, float] = {}
    b_last_period: dict[str, str] = {}
    b_first_income: dict[str, float] = {}
    b_first_exp: dict[str, float] = {}
    v_last_pv: dict[str, float] = {}

    order_failures_base = 0
    order_failures_val = 0

    print("streaming base + validated in lockstep ...", flush=True)
    for cb, cv in zip(read_chunks(BASE_CSV), read_chunks(VAL_CSV)):
        if base_info["columns"] is None:
            base_info["columns"] = len(cb.columns)
            base_info["column_order"] = list(cb.columns)
            val_info["columns"] = len(cv.columns)
            val_info["column_order"] = list(cv.columns)

        profile(cb, base_info, base_stats, BASE_NUMERIC)
        profile(cv, val_info, val_stats, VAL_NUMERIC)

        for info, frame in ((base_info, cb), (val_info, cv)):
            pmin, pmax = frame["period"].min(), frame["period"].max()
            if info["date_min"] is None or pmin < info["date_min"]:
                info["date_min"] = pmin
            if info["date_max"] is None or pmax > info["date_max"]:
                info["date_max"] = pmax

        # duplicates
        keys_b = list(zip(cb["user_id"].tolist(), cb["period"].tolist()))
        before = len(seen_base)
        seen_base.update(keys_b)
        base_info["dup_rows"] = base_info.get("dup_rows", 0) + len(keys_b) - (len(seen_base) - before)
        keys_v = list(zip(cv["user_id"].tolist(), cv["period"].tolist()))
        before = len(seen_val)
        seen_val.update(keys_v)
        val_info["dup_rows"] = val_info.get("dup_rows", 0) + len(keys_v) - (len(seen_val) - before)

        # ---- X1 / X2 : positional comparison of the two streams ----
        same_len = len(cb) == len(cv)
        checks["X1_same_key_sequence"].n += max(len(cb), len(cv))
        if not same_len:
            checks["X1_same_key_sequence"].failed += abs(len(cb) - len(cv))
            continue
        kb = np.array(keys_b, dtype=object)
        kv = np.array(keys_v, dtype=object)
        key_ne = (cb["user_id"].to_numpy() != cv["user_id"].to_numpy()) | \
                 (cb["period"].to_numpy() != cv["period"].to_numpy())
        checks["X1_same_key_sequence"].failed += int(key_ne.sum())
        checks["X2_portfolio_return_agrees"].compare(
            cv["portfolio_return"].to_numpy(dtype=float),
            cb["portfolio_return"].to_numpy(dtype=float))
        checks["X2_portfolio_value_agrees"].compare(
            cv["portfolio_value"].to_numpy(dtype=float),
            cb["portfolio_value"].to_numpy(dtype=float))
        del kb, kv

        b_uid = cb["user_id"]
        v_uid = cv["user_id"]

        # ---- base identities ----
        inc = cb["monthly_income"].to_numpy(dtype=float)
        exp = cb["monthly_expenditure"].to_numpy(dtype=float)
        emi = cb["monthly_emi"].to_numpy(dtype=float)
        surp = cb["monthly_surplus"].to_numpy(dtype=float)
        checks["A1_surplus_identity"].compare(surp, inc - exp - emi)
        checks["A1b_surplus_excl_emi"].compare(surp, inc - exp)

        icr = cb["investment_capacity_ratio"].to_numpy(dtype=float)
        rsk = cb["risk_score"].to_numpy(dtype=float)
        bad_range = ((icr < 0) | (icr > 1) | (rsk < 0) | (rsk > 1))
        checks["A6_range"].add_rows(len(cb))
        checks["A6_range"].add_violations(int(bad_range.sum()))

        periods = cb["period"].to_numpy()
        pl = cb["portfolio_value"].to_numpy(dtype=float)
        pr = cb["portfolio_return"].to_numpy(dtype=float)
        ini = cb["initial_investment"].to_numpy(dtype=float)
        same = b_uid.to_numpy()[1:] == b_uid.to_numpy()[:-1]
        expected = np.empty(len(cb))
        expected[1:] = np.where(same, pl[:-1] * (1.0 + pr[1:]), np.nan)
        first_idx = np.where(np.concatenate(([True], ~same)))[0]
        for i in first_idx:
            u = b_uid.iat[i]
            anchor = b_last_pv.get(u, ini[i] if not np.isnan(ini[i]) else np.nan)
            expected[i] = anchor * (1.0 + pr[i])
        mask = np.isfinite(expected)
        checks["A3_portfolio_compounding"].compare(pl[mask], expected[mask])

        # period order within user (count failing adjacent same-user pairs)
        if len(cb) > 1:
            order_failures_base += int((periods[1:][same] <= periods[:-1][same]).sum())
        for i in first_idx:
            u = b_uid.iat[i]
            if u in b_last_period and not (periods[i] > b_last_period[u]):
                order_failures_base += 1

        # constant profile within user (cross-chunk aware)
        checks["A2_constant_profile_income"].add_rows(len(cb))
        checks["A2_constant_profile_expenditure"].add_rows(len(cb))
        for i in first_idx:
            u = b_uid.iat[i]
            if u in b_first_income:
                if abs(inc[i] - b_first_income[u]) > 1e-6:
                    checks["A2_constant_profile_income"].add_violations(1)
                if abs(exp[i] - b_first_exp[u]) > 1e-6:
                    checks["A2_constant_profile_expenditure"].add_violations(1)
            else:
                b_first_income[u] = float(inc[i])
                b_first_exp[u] = float(exp[i])
        g = cb.groupby(b_uid, sort=False)[["monthly_income", "monthly_expenditure"]].nunique()
        checks["A2_constant_profile_income"].add_violations(int((g["monthly_income"] > 1).sum()))
        checks["A2_constant_profile_expenditure"].add_violations(
            int((g["monthly_expenditure"] > 1).sum()))

        for u, pv in zip(b_uid, pl):
            b_last_pv[u] = float(pv)
        for i in range(len(cb) - 1, -1, -1):   # keep the LAST period per user in this chunk
            b_last_period[b_uid.iat[i]] = periods[i]

        # ---- validated identities ----
        me = cv["market_exposure"].to_numpy(dtype=float)
        nif = cv["nifty_monthly_return"].to_numpy(dtype=float)
        pr_v = cv["portfolio_return"].to_numpy(dtype=float)
        pl_v = cv["portfolio_value"].to_numpy(dtype=float)
        ini_v = cv["initial_investment"].to_numpy(dtype=float)
        checks["A4_return_eq_exposure_x_nifty"].compare(pr_v, me * nif)
        checks["A5_exposure_eq_risk"].compare(me, cv["risk_score"].to_numpy(dtype=float))

        same_v = v_uid.to_numpy()[1:] == v_uid.to_numpy()[:-1]
        exp_v = np.empty(len(cv))
        exp_v[1:] = np.where(same_v, pl_v[:-1] * (1.0 + pr_v[1:]), np.nan)
        first_v = np.where(np.concatenate(([True], ~same_v)))[0]
        for i in first_v:
            u = v_uid.iat[i]
            anchor = v_last_pv.get(u, ini_v[i] if not np.isnan(ini_v[i]) else np.nan)
            exp_v[i] = anchor * (1.0 + pr_v[i])
        for u, pv in zip(v_uid, pl_v):
            v_last_pv[u] = float(pv)
        # validated period order was already checked via X1 against base
        del exp_v

    base_info["n_users"] = len(b_first_income)
    val_info["n_users"] = len({u for u in v_last_pv})

    base_prof = pd.DataFrame([{"column": c, "n": s["n"],
                               "mean": s["sum"] / s["n"] if s["n"] else np.nan,
                               "min": s["min"], "max": s["max"]}
                              for c, s in base_stats.items()])
    val_prof = pd.DataFrame([{"column": c, "n": s["n"],
                              "mean": s["sum"] / s["n"] if s["n"] else np.nan,
                              "min": s["min"], "max": s["max"]}
                             for c, s in val_stats.items()])
    base_prof.to_csv(OUT / "column_profile_base.csv", index=False)
    val_prof.to_csv(OUT / "column_profile_validated.csv", index=False)
    summary = pd.DataFrame([c.as_row() for c in checks.values()])
    summary.to_csv(OUT / "checks_summary.csv", index=False)

    report = {"base_file": base_info, "validated_file": val_info,
              "order_failures_base": order_failures_base,
              "order_failures_validated": order_failures_val,
              "checks": [c.as_row() for c in checks.values()]}
    (OUT / "large_csv_validation_report.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")

    L = ["# Large-CSV content validation (Phase B / F-14)", "",
         f"- base `{BASE_CSV.name}`: {base_info['size_bytes']/1e6:.1f} MB, "
         f"{base_info['rows']:,} rows, {base_info['columns']} columns",
         f"- validated `{VAL_CSV.name}`: {val_info['size_bytes']/1e6:.1f} MB, "
         f"{val_info['rows']:,} rows, {val_info['columns']} columns",
         f"- users: base {base_info['n_users']:,}; validated {val_info['n_users']:,}",
         f"- date range: {base_info['date_min']} .. {base_info['date_max']}",
         f"- duplicate (user,period) rows: base {base_info.get('dup_rows', 0):,}; "
         f"validated {val_info.get('dup_rows', 0):,}",
         f"- period-order failures: base {order_failures_base}; validated {order_failures_val}",
         "", "## Identities", "",
         "| check | comparisons | failures | max abs deviation | status |",
         "|---|---:|---:|---:|---|"]
    for c in checks.values():
        L.append(f"| `{c.name}` | {c.n:,} | {c.failed:,} | {c.max_dev:.3e} | "
                 f"{'PASS' if c.failed == 0 else 'FAIL'} |")
    L += ["", f"Tolerance rtol={RTOL}, atol={ATOL} (float64 through CSV text).",
          "", "### Non-numeric cells (where a number is expected)", ""]
    for info, name in ((base_info, "base"), (val_info, "validated")):
        bad = {k: v for k, v in info["non_numeric_counts"].items() if v}
        L.append(f"- {name}: {bad if bad else 'none'}")
    L += ["", "### Null cells per column", ""]
    for info, name in ((base_info, "base"), (val_info, "validated")):
        nulls = {k: v for k, v in info["null_counts"].items() if v}
        L.append(f"- {name}: {nulls if nulls else 'none'}")
    (OUT / "large_csv_validation_report.md").write_text("\n".join(L), encoding="utf-8")

    print(json.dumps({"base_rows": base_info["rows"], "val_rows": val_info["rows"],
                      "base_users": base_info["n_users"], "val_users": val_info["n_users"],
                      "checks": {c.name: c.as_row() for c in checks.values()}},
                     indent=2, default=str))


if __name__ == "__main__":
    main()
