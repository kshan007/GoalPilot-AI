# Final System Audit

Component-by-component inspection of GoalPilot AI at `S:\fyp\GoalPilot_AI_Platform`.
"Exists" is not "runs", and "runs" is not "validated" — the three are separated in every row.

Evidence was produced by executing the code on this host on 2026-10-17. The research tree
(`GoalPilot_AI_Completed`), datasets, notebooks and checkpoints were read only.

> **Superseding addendum — 2026-10-18.** This document is the historical 2026-10-17 audit and is
> preserved as such. Two statements in it are no longer current: browser end-to-end **was** run in
> the release pass (8/8 Playwright), and D10 (unhandled 500s bypassing CORS) **is fixed** by the
> catch-all middleware in `app/main.py`. Current status and counts:
> `outputs/GOALPILOT_AUDIT_REPORT.md` §13.

Status: **Verified** · **Partially Verified** · **Missing** · **Defective** · **Blocked**

---

## 1. Application and domain services

| # | Component / location | Existing implementation | Evidence it executes | Correctness and limitations | Status | Required action | Tests |
|---|---|---|---|---|---|---|---|
| 1 | Auth — `app/api/auth.py`, `app/core/security.py` | JWT bearer, bcrypt, rate-limited login, reset flow | `tests/test_auth.py` (12) | Tokens validated server-side; ownership enforced per query | Verified | None | 12 pass |
| 2 | Profiles & onboarding — `app/api/profile.py` | Profile CRUD, derived summary, onboarding state | `tests/test_api_e2e.py` (11) | `monthly_income` is a fallback only; a recorded income stream wins (found during E2E, now documented) | Verified | Documented in E2E header | E2E step 4 |
| 3 | Income / assets / liabilities | CRUD with ownership | `tests/test_isolation.py` (9) | Cross-user access blocked | Verified | None | 9 pass |
| 4 | Goals — `app/api/goals.py`, `services/goals.py` | CRUD, projections, required contribution, feasibility | `tests/test_financial_calc.py` (27) | Feasibility is arithmetic, not advice; goals are independent of allocation | Verified | None | 27 pass |
| 5 | Cash flow & **protected buffer** — `services/cashflow.py` | Surplus, emergency fund, savings target | `tests/test_buffer.py` (11) | Was **defective**: `preferred_cash_buffer` was stored and never used. Now `protected_buffer = max(target, reserve)`, `available_goal_budget = surplus − buffer` | **Repaired → Verified** | None | 11 pass |
| 6 | Monthly workspace — `app/api/monthly.py`, `services/forecasting.py` | Month open/close, actuals vs estimates, rolling forecast | `tests/test_monthly.py` (15), `test_forecasting.py` (16) | New users get labelled provisional estimates, not a fabricated pattern | Verified | None | 31 pass |
| 7 | LP optimiser — `engines/lp_engine.py` + research `multi_goal_optimizer.py` | SciPy HiGHS, multi-goal, per-goal inflation and dates, loans, liquidity | `tests/test_lp_engine.py` (21) | True multi-goal with priorities. Linear, single-period; no scenario tree | Verified | None | 21 pass |
| 8 | RL inference — `engines/rl_engine.py`, PPO checkpoint | Loads checkpoint, builds a one-row profile frame, bounded action | Runs inside compare/plan; assertion on observation shape | Checkpoint was trained before the buffer change, so its *evaluation* is stale even though inference is correct | **Partially Verified** | Re-evaluate on the corrected state; retrain only with authorisation | compare tests (14) |
| 9 | Hybrid — `engines/hybrid_engine.py` | RL proposes the savings/investment split; LP re-solves with it | Hybrid arm in `test_selector.py` (14) | RL output materially changes LP parameters; invalid output falls back to LP | Partially Verified (same stale-evaluation caveat) | Re-evaluate | 14 pass |
| 10 | Selector — `engines/selector.py` | Scores arms on identical inputs; LP is default | `test_selector.py` | LP is selected; RL/hybrid not promoted | Verified | None | 14 pass |
| 11 | Scenarios — `app/api/scenarios.py` | Preset + custom shocks, persisted runs | `tests/test_scenarios.py` (12) | Shocks are counterfactuals, labelled as such | Verified | None | 12 pass |

## 2. New capabilities added in this pass

| # | Component / location | Implementation | Evidence | Limitations | Status | Tests |
|---|---|---|---|---|---|---|
| 12 | Provider framework — `app/providers/` | Normalised records, five provenance classes, per-provider isolation, TTL cache, HTTP with size/timeout limits | `tests/test_providers.py` (23) | Cache is in-process; no persistence of external payloads by design | Verified | 23 |
| 13 | Investment discovery — `providers/amfi.py`, `services/investment_discovery.py`, `api/investments.py` | AMFI NAV parse (1,833 direct-growth records live), govt small-savings reference, optional NAV history, suitability scoring, category diversity | `test_investment_discovery.py` (13); live AMFI fetch printed 1,833 records | No expense ratio, exit load or minimum investment — AMFI does not publish them, so they are `null` | Verified | 13 |
| 14 | Loan discovery & analysis — `providers/loans.py`, `services/loan_analysis.py`, `api/loans.py` | EMI, amortisation, IRR APR, affordability checks, rate sensitivity, save-vs-borrow, four rate classes, labelled category scenarios | `test_loans.py` (31); 3 lenders verified live | Advertised minima only; no aggregator; no fees where unpublished | Verified | 31 |
| 15 | Economic data & provenance — `providers/market.py`, `providers/loans.py` (WALR) | NIFTY history + live level; RBI WALR benchmark | Local datasets read; NSE live verified | DEA small-savings page blocked (TLS chain untrusted, verification not disabled) | Partially Verified | covered in 23 |
| 16 | Structured recommendations — `app/llm/gemini_client.py`, `services/recommendations.py`, `api/recommendations.py`, `RecommendationRun` | Deterministic skeleton + prose-only `LLMText`, grounding checks, deterministic fallback, persistence | `test_recommendations.py` (21), E2E steps 8–9 (46/46) | Live Gemini path untested: no key in this environment | **Partially Verified** | 21 |
| 17 | Frontend — `pages/Investments.tsx`, `Loans.tsx`, `Recommendations.tsx`, `api/market.ts` | Three new pages wired to the API; typed client; nav + routes | `npm run build` → `tsc` clean, Vite built in 19.77 s | Browser end-to-end not run in this pass; pages verified by compilation and API contract only | Partially Verified | build |
| 18 | Database — `models.py`, alembic `b1f7c2a94d10` | Additive `recommendation_runs` table | Suite creates it; SQLite `create_all` on startup | SQLite only; Postgres path not exercised | Verified (SQLite) | all |

## 3. Defects found and fixed in this pass

| ID | Defect | Consequence | Fix |
|---|---|---|---|
| D1 | `preferred_cash_buffer` persisted but never read by cash flow or either optimiser | The product's central promise — protecting a buffer — was silently absent; all surplus could be allocated to goals | Buffer computed and charged to both arms |
| D2 | Buffer deficit measured against the already-reduced buffer | A mandatory buffer larger than the surplus reported `deficit = 0`, i.e. "sustainable" | Deficit measured against sustainable capacity; separate warning text |
| D3 | Nested Pydantic models persisted through `json.dumps(default=str)` | Stored payloads contained stringified models; re-reads were corrupted | Response built JSON-native before persistence |
| D4 | Naive date-only timestamps compared with an aware "now" | `freshness()` raised on date-only sources | Single coercion helper |
| D5 | Goal labelled `fully_funded` when it had no allocation and no projection | A goal with a 201,658 gap and 0% achievement displayed as funded | Missing allocation or projection ⇒ `underfunded` |
| D6 | Lender rates living only in description metadata were discarded | Bank of Baroda silently disappeared from discovery | Metadata included in the extractable text, evidence retained |
| D7 | AMFI section headers not matched (e.g. "Medium Term Fund") | Funds misclassified as "other", weakening risk scoring | Rule table extended |

## 4. Genuinely missing or unverified

| Item | Status | Why | What is needed |
|---|---|---|---|
| Live Gemini call | **Verified Live** 2026-10-17 | `gemini-2.5-flash`, `used: true`, schema-valid, figures consistent | Monitor quota; latency 20–30 s |
| Browser-driven E2E (Playwright) | Missing | Not run in this pass | Run against a live server; API-level E2E passes 46/46 |
| RL/hybrid re-evaluation on corrected state | Outstanding | Checkpoint predates the buffer fix | Authorisation to re-run evaluation (preferred) or retrain |
| Postgres deployment | Blocked | SQLite is the agreed local target | Credentials + a migration run |
| Education/secured/home/vehicle published products | Missing by data availability | No verified public source integrated | An authorised aggregator API or manual curation |
| NSC / KVP / Post Office TD rates | Deliberately absent | Not verified | Re-verify against the official notification |
| Documentation set (`MODEL_READINESS`, `ALGORITHM_DESIGN`, `ALGORITHM_EVALUATION`, `DATA_SOURCES_AND_PROVENANCE`, `FINANCIAL_ASSUMPTIONS`, `LLM_RECOMMENDATION_SCHEMA`, `DEMO_GUIDE`, `DEPLOYMENT`) | **Written** | — | Authored from executed results, including the algorithm sweep | None |

---

## 5. Addendum — defects found by browser validation (2026-10-17)

A real Chrome session walked the journey and found a contradiction between two screens. Root
cause analysis produced four further defects.

| ID | Defect | Consequence | Status |
|---|---|---|---|
| D8 | `project_goals` indexed the allocation frame by `goal_id` but looked goals up by `"G<id>"` — the join never matched | Every goal was reported as unplanned even when the optimiser had allocated money. `/optimize` said "shortfall 0, achievement 100%" while `/recommendations` said "2 goals cannot be met, shortfall 14,32,863" | **Fixed** (both keys indexed; `None` checks instead of `or` on a Series) |
| D9 | `/api/health` returned `status: healthy` and `database: true` while every DB endpoint was failing | The most misleading state an operator can see; it sent the browser session chasing a network fault | **Fixed** (real `SELECT 1` probe; `status: degraded` + dialect + error) |
| D10 | Unhandled 500 responses bypass the CORS middleware (Starlette's `ServerErrorMiddleware` sits outside it) | Browser reports `net::ERR_FAILED`, and the UI says "Could not reach the API. Check that the backend is running" — a server error disguised as a network outage | **Open** (recorded; needs a catch-all middleware that adds CORS headers) |
| D11 | `future_goal_cost` persisted as 0 when the LP row used a different key | Allocation table showed "FUTURE COST ₹0.00" beside a funding gap of ₹14,32,862 | **Fixed** (fallback key chain) |
| D12 | Onboarding income rows offer only Delete, no Edit | Changing income requires delete + re-add; the adaptive re-plan demo is awkward through the UI | **Open** (use the API, or delete and re-add) |

Verification after the fixes: the same browser account now returns
`total_shortfall 0`, `achievement 1.0`, and both goals `fully_funded` with matching shortfalls of
zero — consistent with the optimiser and with each other. Full suite re-run: 239 passing,
including three new regression tests for the join.
