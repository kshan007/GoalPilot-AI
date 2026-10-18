
# Investment and Loan Integration

How GoalPilot AI sources, labels and analyses investment and borrowing information.
The governing rule is that **four different claims are never allowed to look alike**: a
historical benchmark, a published lender rate, a modelling assumption, and a personal offer.

---

## 1. The four rate classes

Every borrowing cost carries a `rate_class`, and every response also returns the full legend in
`rate_classes` so a client cannot render one class as another.

| `rate_class`            | What it is                                                                          | Where it comes from                                                                                               | May be called a "rate you can get"?                      |
| ------------------------- | ----------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------- |
| `historical_benchmark`  | RBI weighted average lending rate on outstanding rupee loans — an aggregate series | `datasets/GoalPilot_AI/extracted_features/walr_features.csv` (RBI source)                                       | **No.** It is a system average, not a product      |
| `published_lender_rate` | Advertised minimum ("from") rate on a lender's own public product page              | ICICI / Axis / BoB public pages, live or bundled snapshot                                                         | Only as "advertised from", never as an offer             |
| `estimated_scenario`    | A configurable assumption used when no published product exists for a category      | `GOALPILOT_SCENARIO_LOAN_RATE`, a per-request `scenario_rate`, or the user's own `loan_interest_assumption` | **No.** It is explicitly a scenario                |
| `personalised_offer`    | A rate actually quoted to this user                                                 | Only the user, entering their own offer                                                                           | Only as their quote — the platform never obtains offers |

Two structural guarantees back this up:

* A scenario record has `published_rate = null` and carries its value in `scenario_rate`. Code
  that reads `published_rate` therefore cannot pick up a scenario by accident.
* `is_personalised_offer` is `false` on every sourced record and only becomes `true` on the
  analysis path when the user marks their own input with `offer_is_personal: true`.

---

## 2. Sources and their honest status

| Source                   | Series / content                                              | Access                                                            | Status                                                                                     | Fallback                                                     |
| ------------------------ | ------------------------------------------------------------- | ----------------------------------------------------------------- | ------------------------------------------------------------------------------------------ | ------------------------------------------------------------ |
| RBI (WALR)               | Weighted average lending rate, all scheduled commercial banks | Local calibration dataset already in the research tree            | **Verified Download** (historical series, latest observation reported with its date) | Provider reports `unavailable`; no benchmark shown         |
| ICICI Bank               | Personal loan, advertised from 9.99%                          | Public product page, one GET                                      | **Verified Live** on 2026-10-17                                                      | Bundled snapshot, `official_snapshot`                      |
| Axis Bank                | Personal loan, advertised from 9.99%                          | Public product page, one GET                                      | **Verified Live** on 2026-10-17                                                      | Bundled snapshot, `official_snapshot`                      |
| Bank of Baroda           | Personal loan, advertised from 11.00%                         | Public product page (rate in the page's own description metadata) | **Verified Live** on 2026-10-17                                                      | Bundled snapshot, `official_snapshot`                      |
| SBI                      | —                                                            | Rates page returns 404 on the current domain                      | **Unavailable**                                                                      | Omitted, not guessed                                         |
| PNB                      | —                                                            | Rate is client-rendered; no rate in the served HTML               | **Unavailable**                                                                      | Omitted, not guessed                                         |
| HDFC                     | —                                                            | Edge blocks non-browser clients (403)                             | **Unavailable**                                                                      | Omitted, not guessed                                         |
| Loan aggregator / bureau | —                                                            | No authorised API available to this project                       | **Not integrated by design**                                                         | Provider interface exists for a future authorised connection |

`docs/API_SOURCE_REGISTER.md` records the same set with endpoints, licences and rate limits.

Nothing above is described as an API unless it is one. The lender integration is a **permitted
retrieval of a public disclosure**, cached for `PROVIDER_CACHE_TTL_SECONDS` (default 6 hours),
and every record keeps `retrieved_at`, the `quoted_text` that supplied the rate, and
`source_url`.

### Freshness

`freshness` is computed from `retrieved_at` against a per-class threshold (24 h for live
retrieval, 5 days for snapshots, 48 h for the NAV mirror). Old data is shown as `stale` rather
than presented as current. A snapshot never silently becomes a live rate.

---

## 3. What is computed locally, with no credentials

All of this runs offline and is unit-tested:

| Capability                 | Formula / rule                                                                                                                                                                   | Test                                                                                               |
| -------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| EMI                        | `P·r·(1+r)^n / ((1+r)^n − 1)`, `r = annual/12`                                                                                                                            | `test_emi_matches_the_standard_formula`                                                          |
| Total repayment / interest | `EMI × n`, minus principal                                                                                                                                                    | `test_total_repayment_is_emi_times_tenure`                                                       |
| Amortisation               | Full month-by-month split, closing balance zero                                                                                                                                  | `test_amortisation_is_internally_consistent`                                                     |
| APR                        | IRR on net proceeds and the EMI stream, annualised `(1+i)^12 − 1`; equals the **effective** rate when fees are zero                                                     | `test_apr_equals_the_effective_annual_rate_when_there_are_no_fees`                               |
| Affordability              | EMI vs the user's EMI-to-income ceiling, vs the goal budget **after** the protected buffer, vs half that budget, buffer intact, emergency fund ≥ 50%, no existing deficit | `test_emi_above_goal_budget_is_blocked`, `test_thin_emergency_fund_is_a_caution_not_a_blocker` |
| Floating-rate sensitivity  | EMI and total interest at +0/+100/+200/+300 bp                                                                                                                                   | `test_rate_sensitivity_increases_monotonically`                                                  |
| Save vs borrow             | Months to fund from capacity, deadline extension needed, interest avoided, reduced target                                                                                        | `test_alternatives_quantify_saving_instead_and_extension`                                        |
| Quote comparison           | Ranked by **total cost of credit** (interest + fees), not headline rate                                                                                                    | `test_compare_quotes_ranks_by_total_cost_not_headline_rate`                                      |

Hard rules enforced in code: loan proceeds are never treated as income
(`proceeds_are_not_income: true`), eligibility is never asserted, and borrowing is never
recommended merely because it makes a goal affordable now.

---

## 4. Missing categories

Only personal-loan products have published rates in the integrated sources. Education, secured,
home and vehicle loans are therefore **not** represented by invented products.

When a category has no published product, the response:

1. lists it in `category_coverage.scenario_only` and `category_coverage.unavailable`;
2. adds a row to `missing_information` naming the gap and the assumption used;
3. offers a `scenarios[]` entry with `rate_class = estimated_scenario`,
   `published_rate = null`, `configurable = true`, and an `assumption_source`.

The scenario rate resolves in this order, and the chosen source is always reported:

1. `?scenario_rate=` on the request (analyst or user override)
2. the user's own `loan_interest_assumption` from their profile
3. `GOALPILOT_SCENARIO_LOAN_RATE` (deployment default, 12%)
4. a hard 12% fallback, labelled `platform_fallback`

Changing the assumption changes the EMI, so a scenario is inspectable rather than opaque:
`test_scenario_rate_is_configurable_and_changes_the_emi`.

---

## 5. Investment discovery (summary)

Same provenance machinery, different sources: AMFI's public daily NAV file (official, live,
current NAV only — no expense ratio or minimum investment is invented), a curated government
small-savings reference (only the three rates that were verified; NSC and KVP are deliberately
absent), and an optional free NAV-history mirror for trailing returns, labelled
`unofficial_mirror`.

Suitability is an additive penalty model over the user's stated risk capacity, horizon,
liquidity need and concentration; the full scoring table is served at
`GET /api/investments/methodology`. Equal scores are reported as a tie, not a ranking.

---

## 6. Endpoints

| Method | Path                             | Purpose                                                                                                                 |
| ------ | -------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| GET    | `/api/loans/discover`          | Published products + benchmarks + labelled scenarios; `principal`, `tenure_months`, `category`, `scenario_rate` |
| POST   | `/api/loans/analyse`           | Full analysis of one quote (EMI, APR, affordability, sensitivity, alternatives, optional schedule)                      |
| POST   | `/api/loans/compare`           | Rank several quotes by total cost of credit                                                                             |
| GET    | `/api/loans/providers`         | Configuration status + four-class legend + credential-free statement                                                    |
| GET    | `/api/loans/methodology`       | Formulas and hard rules                                                                                                 |
| GET    | `/api/investments/discover`    | Ranked, suitability-scored options with provenance                                                                      |
| GET    | `/api/investments/methodology` | Scoring table and provenance classes                                                                                    |
| POST   | `/api/investments/refresh`     | Clear the provider cache                                                                                                |

---

## 7. Known limitations

* Lender rates are **advertised minima**; the rate a given user receives depends on underwriting.
* Processing fees, tenure ranges and APRs are `null` where the page did not state them
  verbatim. They are not estimated.
* Only three lenders are covered, all for personal loans; this is a coverage gap, not a claim of
  market coverage.
* The RBI series is a system aggregate and lags by publication; its observation date is always
  reported.
* No aggregator, bureau or lender API is integrated, and none is claimed.
