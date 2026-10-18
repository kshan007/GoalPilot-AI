# Large-CSV content validation (Phase B / F-14)

- base `monthly_financial_simulation_base.csv`: 959.3 MB, 1,430,000 rows, 46 columns
- validated `portfolio_simulation_validated.csv`: 169.1 MB, 1,430,000 rows, 9 columns
- users: base 10,000; validated 10,000
- date range: 2015-02-01 .. 2026-12-01
- duplicate (user,period) rows: base 0; validated 0
- period-order failures: base 0; validated 0

## Identities

| check | comparisons | failures | max abs deviation | status |
|---|---:|---:|---:|---|
| `A1_surplus_identity` | 1,430,000 | 601,744 | 1.398e+05 | FAIL |
| `A1b_surplus_excl_emi` | 1,430,000 | 0 | 9.459e-11 | PASS |
| `A3_portfolio_compounding` | 1,430,000 | 0 | 5.588e-09 | PASS |
| `A4_return_eq_exposure_x_nifty` | 1,430,000 | 0 | 9.999e-17 | PASS |
| `A5_exposure_eq_risk` | 1,430,000 | 0 | 0.000e+00 | PASS |
| `A2_constant_profile_income` | 1,430,000 | 0 | 0.000e+00 | PASS |
| `A2_constant_profile_expenditure` | 1,430,000 | 0 | 0.000e+00 | PASS |
| `A6_range` | 1,430,000 | 0 | 0.000e+00 | PASS |
| `X1_same_key_sequence` | 1,430,000 | 0 | 0.000e+00 | PASS |
| `X2_portfolio_return_agrees` | 1,430,000 | 0 | 0.000e+00 | PASS |
| `X2_portfolio_value_agrees` | 1,430,000 | 0 | 0.000e+00 | PASS |

Tolerance rtol=1e-06, atol=1e-06 (float64 through CSV text).

### Non-numeric cells (where a number is expected)

- base: none
- validated: none

### Null cells per column

- base: none
- validated: none