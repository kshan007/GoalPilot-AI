# Data Sources and Provenance

Per-dataset record of what the platform uses, where it came from, what was done to it, and what it
may and may not be used for. Column-level detail lives in `docs/DATA_DICTIONARY.md`.

All figures below were read from the files on 2026-10-17.

---

## 1. NIFTY 50 monthly closes

| Field | Value |
|---|---|
| Source | NSE NIFTY 50, as processed by the project's research pipeline |
| Local file | `datasets/GoalPilot_AI/extracted_features/nifty_monthly_features.csv` |
| Also present | `nifty_features.csv` (2,848 rows, daily) |
| Retrieval | In the repository; not re-downloaded in this pass |
| Observation period | 2015-01-01 → 2026-12-01, monthly, 144 rows |
| Units | Index points (close); last close 23,622.90 |
| Transformations | Month-end close selected from daily data; no interpolation |
| Missing values | Rows without a close dropped; no forward fill |
| Use | Descriptive statistics only: annualised volatility, max drawdown, trailing CAGR |
| Must not be used for | Expected returns, forecasts, or a guaranteed growth assumption |
| Caveat | Index returns exclude dividends and costs; past volatility does not predict future volatility |

## 2. RBI weighted average lending rate

| Field | Value |
|---|---|
| Source | Reserve Bank of India series, as calibrated in the research pipeline |
| Local file | `datasets/GoalPilot_AI/extracted_features/walr_features.csv` (47 rows), plus `walr_engineered_features.csv` |
| Observation period | 2014-03 → 2026-03, monthly |
| Units | Per cent per annum; latest value 9.27108% |
| Coverage | All scheduled commercial banks, outstanding rupee loans — a **system aggregate** |
| Transformations | Series aligned to month start; engineered features add lags/differences |
| Use | A historical benchmark when no published product rate is available |
| Must not be used for | Any individual borrower's rate, a current offer, or a price |
| Caveat | Lags by publication; reported with its observation month, never relabelled as current |

## 3. Consumer Price Index

| Field | Value |
|---|---|
| Local files | `cpi_features.csv`, `cpi_engineered_features.csv` (48 rows each) |
| Frequency | Monthly |
| Use | Informs the default inflation assumption and scenario ranges |
| Transformations | Aligned to the model's monthly grid; engineered lags |
| Caveat | A national index is not a household's inflation; goal-level overrides are supported |
| Must not be used for | Claiming a specific user's cost inflation |

## 4. HCES 2023–24 household expenditure

| Field | Value |
|---|---|
| Local files | `hces_features.csv`, `hces_simulation_features.csv` (227,114 rows each) |
| Use | Prior distributions for synthetic household generation and plausibility bounds |
| Transformations | Feature extraction by the research pipeline; rows retained as-is |
| Must not be used for | Presenting a specific user's spending as an official statistic, or vice versa |
| Caveat | Aggregate survey data. A user's actual expenses come only from their own records |

## 5. NISM investor-education knowledge base

| Field | Value |
|---|---|
| Artefact | NISM JSON/CSV knowledge base in the research tree |
| Use | Educational content surfaced by the knowledge endpoints |
| Provenance rule | Quoted as educational material; never merged into a calculation |

## 6. AMFI NAV file (live)

| Field | Value |
|---|---|
| Source | https://www.amfiindia.com/spages/NAVAll.txt |
| Retrieved | 2026-10-17 during this build |
| Coverage | All open/closed-ended schemes; 1,833 direct-growth records parsed |
| NAV date | 2026-10-16 |
| Transformations | Filtered to Direct + Growth; section header → category/risk mapping; invalid NAV rows dropped |
| Missing values | Expense ratio, exit load and minimum investment are **absent from the source** and stay `null` |
| Use | Named, currently priced instruments for discovery |
| Caveat | A NAV is not a return; no performance figure is derived from a single observation |

## 7. Government small-savings rates

| Field | Value |
|---|---|
| Publisher | Department of Economic Affairs, Ministry of Finance |
| Official URL | https://dea.gov.in/ |
| Retrieval | **Failed** — untrusted TLS chain on this host; verification not disabled |
| Quarter | 2026-10-01 → 2026-12-31 (Q3 FY2026-27) |
| Values encoded | PPF 7.1%, SSY 8.2%, SCSS 8.2% |
| Verification | Cross-checked against published reporting of the notification; recorded in `app/providers/reference/small_savings.json` |
| Deliberately omitted | NSC, KVP, Post Office Time Deposit — not verified, therefore not guessed |
| Use | Reference rates for sovereign schemes, with eligibility conditions |
| Caveat | Quarterly instrument; must be re-verified each quarter |

## 8. Lender published rates

| Field | Value |
|---|---|
| Sources | ICICI, Axis, Bank of Baroda public product pages |
| Retrieved | 2026-10-17, live, one GET each |
| Values | Advertised minima: 9.99%, 9.99%, 11.00% |
| Evidence | The matched sentence is retained as `quoted_text` per record |
| Missing | Processing fee, tenure range, APR — not stated verbatim, therefore `null` |
| Unavailable | SBI (404), PNB (client-rendered), HDFC (403) |
| Use | Published product information for comparison |
| Must not be used for | Personalised offers, eligibility, or an APR claim |

## 9. NAV history (optional)

| Field | Value |
|---|---|
| Source | https://api.mfapi.in — a free mirror of AMFI NAV history |
| Class | Third-party, unofficial; labelled `unofficial_mirror` on every record |
| Use | Trailing 1/3/5-year CAGR over the exact period reported |
| Fallback | No return shown; the option remains listed |
| Caveat | CAGR is a past observation, net of the scheme's own expenses, and is not a forecast |

## 10. Household and monthly data

User-entered profiles, income streams, assets, liabilities, goals, monthly actuals and
reconciliations are the only source of a user's own figures. They are never replaced by survey
data, and forecasts are labelled as forecasts until actuals are recorded.

---

## Cross-cutting rules

1. Every imported series records source, retrieval date, observation period, units, frequency and
   transformation.
2. Missing values are dropped or left `null`; nothing is imputed silently.
3. Historical series are never presented as forecasts, and forecasts are never labelled as
   observations.
4. Aggregate statistics (CPI, HCES, WALR) inform priors and scenarios; they are never presented as
   a specific household's numbers.
5. A dataset whose source is unreachable is reported as unavailable, with the reason, rather than
   substituted.
