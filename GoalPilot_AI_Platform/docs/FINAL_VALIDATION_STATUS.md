# Final Validation Status

What was executed, on what, with what result. Anything not executed is listed as not executed.

Host: Windows, Python 3.13 (`C:\Users\sudha\AppData\Local\Programs\Python\Python313\python.exe`),
Node 22.23.2 / npm 10.9.8. Date: 2026-10-17.

> **Superseding addendum — release pass, 2026-10-18.** The counts and browser statements in the
> body below are the historical record of the 2026-10-17 pass and are preserved as such. Current
> verified results: **268 backend tests, 0 failures / 0 errors / 0 skipped** (35.8 s, exit 0);
> **8/8 Playwright browser tests** (19.9 s) against a fresh SQLite database, including plan
> generation and a what-if scenario; `npm run build` clean. The live Gemini path was **not**
> re-exercised (LLM disabled for determinism). See `outputs/GOALPILOT_AUDIT_REPORT.md` §13.

---

## 1. Test suite

```bash
cd S:\fyp\GoalPilot_AI_Platform\backend
python -m pytest -q
```

| Metric | Value |
|---|---|
| Tests collected | **242** |
| Result | **All passing** (no failures, no errors; exit code 0) |
| Baseline before this pass | 137 passing |

| File | Tests | Covers |
|---|---|---|
| `test_api_e2e.py` | 11 | journey-level API behaviour |
| `test_auth.py` | 12 | registration, login, reset, token handling |
| `test_buffer.py` | 11 | protected buffer, deficit, goal budget, LP/RL wiring |
| `test_financial_calc.py` | 27 | cash flow, inflation, EMI, shortfalls, reconciliation |
| `test_forecasting.py` | 16 | rolling estimates, cold start, accuracy |
| `test_investment_discovery.py` | 13 | suitability rules, provenance, scenarios, API |
| `test_isolation.py` | 9 | cross-user data isolation |
| `test_loans.py` | 31 | EMI, APR, amortisation, affordability, sensitivity, rate classes, scenarios, API |
| `test_lp_engine.py` | 21 | multi-goal, deficits, infeasibility, numerical edges |
| `test_monthly.py` | 15 | month lifecycle, actuals, budget status |
| `test_providers.py` | 23 | AMFI parse, history CAGR, lender extraction, registry isolation, freshness |
| `test_recommendations.py` | 21 | grounding, banned language, mocked model, fallback, persistence, isolation |
| `test_scenarios.py` | 12 | preset and custom shocks |
| `test_selector.py` | 14 | arm comparison and selection |

## 2. End-to-end acceptance walk-through

```bash
cd S:\fyp\GoalPilot_AI_Platform
python scripts/e2e_acceptance.py
```

**46 / 46 checks passed.** It drives the real API on a throwaway SQLite database and asserts, in
order: registration and identity; profile, income stream, assets, liabilities; three goals;
feasibility projections; LP plan funding more than one goal at once; the plan staying inside the
post-buffer goal budget; algorithm comparison with at least three arms; investment discovery with
provenance on every option; loan discovery with a rate class on every row and a historical
benchmark present; a loan analysis whose APR exceeds the nominal rate once fees are added;
rate-shock sensitivity; a structured recommendation matching the contract with no short goal
labelled funded; persistence without type corruption; an income shock that reduces the goal budget
while the buffer survives; replanning plus a recorded diff; a regenerated recommendation that
differs; and cross-user isolation.

## 3. Frontend build

```bash
cd S:\fyp\GoalPilot_AI_Platform\frontend
npm run build
```

`tsc` completed with no type errors and Vite produced `dist/` in 19.77 s
(`index-*.js` 769 kB / 207 kB gzip, `index-*.css` 22.9 kB). One pre-existing warning remains:
a single chunk exceeds 500 kB. It is a bundling note, not a failure, and was not addressed because
cosmetic work was explicitly de-prioritised.

## 4. Live source verification performed

| Source | Method | Result |
|---|---|---|
| AMFI `NAVAll.txt` | fetched once, parsed | **1,833** direct-growth records; NAV date 2026-10-16 |
| NSE `allIndices` | fetched once | NIFTY 50 level returned |
| api.mfapi.in | fetched for a scheme | NAV series returned; trailing CAGR computed |
| ICICI Bank, Axis Bank, Bank of Baroda | fetched once each | advertised rate extracted with the quoted sentence |
| SBI, PNB, HDFC | fetched once each | 404 / no rate in HTML / 403 — recorded as unavailable |
| DEA small savings | fetched | TLS chain untrusted on this host; **not** bypassed |
| RBI WALR, NIFTY history | read from repository datasets | latest observations reported with dates |

## 5. Not executed

| Item | Why | Consequence |
|---|---|---|
| Live Gemini generation | Executed 2026-10-17 | — | **Verified Live** (`gemini-2.5-flash`) |
| Browser automation (Playwright/Chrome) | not run in this pass | No screenshot evidence for the three new pages; their API contracts and the production build are verified |
| PostgreSQL migration run | SQLite is the agreed local target | Alembic revision written but only SQLite was exercised |
| RL/hybrid retraining | deliberately not done — no authorisation, and the existing checkpoint must not be overwritten | Model quality claims for RL/hybrid remain those of the original research evaluation, now stale with respect to the buffer fix |
| Load/performance testing | out of scope | LP solve and provider fetches are cached but not benchmarked under concurrency |

## 6. Known residual risks

1. **Stale model evaluation.** The PPO checkpoint was trained before the buffer change altered the
   environment's expenditure input. Inference still runs and the hybrid still passes its
   information-flow tests, but the "RL/hybrid does not beat LP" conclusion should be re-derived.
2. **Advertised rates are minima.** Any EMI shown for a published product is arithmetic on the
   lender's floor rate, not a quote.
3. **Coverage gap.** Only personal-loan products have published rates; other categories are
   explicitly labelled scenarios.
4. **Small-savings rates are a curated snapshot.** They are quarterly; `effective_from` is surfaced
   in the API and must be re-verified each quarter.
5. **Scenarios are synthetic.** The stochastic scenarios exercise the models; they are not
   predictions about any household.

---

## 7. Addendum — browser validation (2026-10-17)

A real Chrome session against `http://localhost:5173` with the API on SQLite. Screenshots:
`outputs/browser-validation4/` (18 files).

| Step | Result |
|---|---|
| 1 Registration → authenticated dashboard | PASS |
| 2 Profile saved, all eight values re-read | PASS |
| 3 Income source, liquid asset, liability recorded and displayed | PASS |
| 4 Two goals created with dates and priorities | PASS |
| 5 LP plan on `/optimize` | PASS |
| 6 `/investments` — 12 named schemes with NAVs, provider table showing `amfi_nav ok 1833 official live` | PASS |
| 7 `/loans` — 3 published products (9.99%, 9.99%, 11.00%), amber scenario block, offer analysis with APR 11.61%, four sensitivity rows, three alternatives | PASS |
| 8 `/recommendations` — summary, buffer block, goal table, grounded answer | PASS |
| 9 Income 120000 → 90000 and re-plan | **NOT RUN** (no Edit control on income rows; API path used instead, see §2 of the E2E script) |

Confirmed in the browser:

* The protected buffer was visible in three places at **₹15,000**, and the UI showed both
  `preferred_cash_buffer 8000` and `protected_buffer 15000` with `buffer_deficit 0`.
* No published lender rate was ever presented as a personalised offer; the offer analysis is
  labelled `estimated scenario` with an explicit non-offer disclaimer.
* No error banner appeared after the API was restarted on SQLite.

Defects found and their status are recorded in `FINAL_SYSTEM_AUDIT.md` §5 (D8–D12). The
contradiction between `/optimize` and `/recommendations` was real, was caused by a broken
allocation join (D8), and is fixed; the fix is covered by `tests/test_goal_projections.py`.

Remaining UI issues, all recorded rather than hidden: no income edit control (D12); the
onboarding counter renders "Step of" with the numbers missing; and the allocation table labels
`INITIAL SAVINGS` separately from `EXISTING FUNDING`, which reads as a contradiction unless the
reader knows the first is cash allocated now and the second is previously earmarked money.

### Local-run default

The API defaults to PostgreSQL when `DATABASE_URL` is unset, and a fresh machine has no matching
database — which is what produced the initial 500s. Set `DATABASE_URL=sqlite:///./goalpilot_demo.db`
for local runs. This is now the documented local configuration in `DEPLOYMENT.md`.

---

## 9. SQLite verification (2026-10-17)

Executed after making SQLite the default, to confirm the choice is safe rather than merely
convenient.

```bash
cd backend
DATABASE_URL=sqlite:///./_fresh_test.db python -m alembic upgrade head
```

| Check | Result |
|---|---|
| Fresh migration | `903315a72db4` → `b1f7c2a94d10` applied cleanly on an empty file |
| Tables created | 22, including `recommendation_runs` and `alembic_version` |
| Existing database | `alembic stamp head` then `upgrade head` succeeded; 3 users and 2 goals preserved |
| Application with no `DATABASE_URL` | resolves to `sqlite:///./goalpilot.db`, `dialect=sqlite`, `reachable=true` |
| Foreign keys | enabled per connection by the engine (SQLite defaults them off) |

Temporary test databases were deleted after the run. The demo database was not modified beyond
the additive `recommendation_runs` table.

---

## 10. Browser suite (Playwright, 2026-10-17)

```bash
cd frontend
npx playwright test
```

**Result: 5 passed (45.2 s).** The suite expects the API on `127.0.0.1:8000` and the dev server on
`localhost:5173`; both URLs are overridable with `API_URL` and `UI_URL`.

| Test | Claim it verifies |
|---|---|
| signs in and leaves the login screen | Real auth against the running API, not a mocked session |
| investment discovery renders sourced options and its provenance | `/investments` renders options **and** the source/freshness and missing-information sections |
| loan comparison shows a benchmark, published rates and labelled scenarios | `/loans` shows the historical benchmark, published-rate cards and the offer analyser |
| generating a recommendation resolves into visible text | A generation completes and renders a body containing the buffer, within 150 s |
| the plan persists across a page reload | Goals reload from the database, not from memory |

Seeding is done through the API so the browser is only used for what a browser can prove: routing,
render, form submission and a slow call resolving into visible output.

### Fault found and fixed during this pass

The first run failed the persistence test because it sampled `body` text immediately after
navigation, capturing the "Loading your goals..." placeholder. That was a defect **in the test**, not
the application: the fix waits for the goal row before sampling. Recorded here rather than quietly
retried, because "the test was wrong" and "the app was wrong" are different findings.

---

## 11. Gemini quota, model naming and latency (2026-10-17)

Four findings, in the order they appeared. Only the first is a passing result; the rest are
limitations recorded rather than papered over.

| Finding | Evidence | Consequence |
|---|---|---|
| Quota exhaustion degrades correctly | `gemini-2.5-flash` returned 429 after the verification runs; the response was HTTP 200 with `status: fallback`, `reason: quota_exceeded`, and the deterministic explanation | The failure mode the brief requires was observed in the wild, not just unit-tested |
| `gemini-2.5-flash-lite` is retired | 404: "no longer available to new users … use models/gemini-3.5-flash-lite" | Earlier advice naming this model was wrong; corrected in `REMAINING_WORK.md` and here |
| `gemini-3.5-flash-lite` rejects the thinking field | 400 INVALID_ARGUMENT with `thinking_config` present | The client now drops the field, remembers the capability, and retries once — a rejected optional parameter does not fail the request |
| Latency is dominated by thinking tokens | 22.2 s, 26.6 s and 26.6 s on three runs before the change; Gemini 2.5 enables thinking by default | Thinking is now disabled by default. **Not re-measured**: quota was exhausted before the change could be timed, so no before/after figure is claimed |

Configuration added: `GOALPILOT_GEMINI_THINKING_BUDGET` (default 0), `GOALPILOT_GEMINI_MAX_OUTPUT_TOKENS`
(default 3072), `GOALPILOT_GEMINI_TIMEOUT_SECONDS` (default 45). The configured default model remains
`gemini-2.5-flash`, the only one verified end to end on this host.
