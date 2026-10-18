# GoalPilot AI Platform

Individual personal financial planning and research decision-support, built around **validated
financial models**.

Multi-goal optimisation over a capacity-constrained LP, a **trained PPO policy** and a **genuine
RL-then-LP hybrid**; adaptive monthly expense forecasting with walk-forward backtesting;
estimated-versus-actual reconciliation; scenario simulation; real authentication, a real
database and per-user data isolation.

> **Research decision-support prototype. Not financial advice.** Every rate and return is an
> explicit, editable assumption. No trades, transfers or loans are ever executed, and no
> regulatory authorisation is claimed.

---

## 1. Provenance: what was reused, what was built

The prior repository contained a **research/model system** and a **single-goal prototype app**.
This platform is a third artefact built around the first; nothing in the research tree was
modified.

|                            |                                                                                                                                                                                                                                                                                                                                                          |
| -------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Reused unchanged** | `multi_goal_optimizer.py` (`optimize_multi_goal`, `prepare_goals`, `FinancialState`), `goalpilot_constrained_lp.py` (`solve_constrained_lp`), `goalpilot_env.py` (`GoalPilotEnv`), `goalpilot_config.py` (`GoalPilotConfig`), `goalpilot_lp_encoder.py`, and the **28 PPO checkpoints** under `training_logs/experiments/` |
| **Built new**        | PostgreSQL/SQLite schema + Alembic, JWT auth, financial profile + onboarding, monthly workflow with estimated-vs-actual reconciliation, the adaptive forecaster, the LP/RL/hybrid/selector **service layer**, scenario simulation, the dashboard, and the entire frontend                                                                          |
| **Audited verdicts** | LP **Ready** · RL environment **Ready** · RL inference adapter **built** (it did not exist) · Hybrid **built** (no executable hybrid existed before) · Forecaster **built** · Colab **Unavailable** (never run from this host)                                                                                  |

Full detail: [`docs/PROJECT_AUDIT.md`](docs/PROJECT_AUDIT.md),
[`docs/MODEL_READINESS.md`](docs/MODEL_READINESS.md).

### The honest result, up front

On the research project's own held-out cohort (16 fresh test users):

| arm                                | goal achievement |      by deadline |
| ---------------------------------- | ---------------: | ---------------: |
| `investment-only` (simple rule)  | **0.5800** |           0.1427 |
| `uniform savings`                |           0.5584 |           0.1427 |
| **RL `archived_v1`** (PPO) |           0.4842 |           0.1083 |
| **`constrained_LP`**       |           0.2452 | **0.1531** |

**RL does not beat a simple investment rule** (paired difference −0.0957, CI [−0.1423, −0.0497],
excludes zero). RL *does* beat the constrained LP on achievement (+0.2390) but **not** on
deadline success. The LP is therefore the platform's default arm: it is the only arm with
essentially zero investment-capacity overflow, the best deadline performance, and a fully
auditable, deterministic plan. The hybrid is implemented and runnable but **no superiority is
claimed for it**.

Details: [`docs/ALGORITHM_EVALUATION.md`](docs/ALGORITHM_EVALUATION.md).

---

## 2. Requirements

|          |                                                                                           |
| -------- | ----------------------------------------------------------------------------------------- |
| Python   | **3.13.7** (the version every result here was produced with)                        |
| Node.js  | 18+ (verified on v22.23.2, npm 10.9.8)                                                    |
| Database | **SQLite** — the supported target, zero setup. PostgreSQL is optional and untested |
| Hardware | Any CPU. `torch` CPU-only is sufficient. No GPU needed.                                 |

> On this machine bare `python` is a **different, empty** interpreter. Use the full path:
>
> ```powershell
> $py = "C:\Users\sudha\AppData\Local\Programs\Python\Python313\python.exe"
> ```

---

## 3. Install

```powershell
$py = "C:\Users\sudha\AppData\Local\Programs\Python\Python313\python.exe"

Set-Location S:\fyp\GoalPilot_AI_Platform\backend
& $py -m pip install -r requirements.txt

Set-Location ..\frontend
npm install
```

---

## 4. Configure

```powershell
Set-Location S:\fyp\GoalPilot_AI_Platform
Copy-Item .env.example .env      # then edit
```

Every variable is documented in [`.env.example`](.env.example). The essentials:

| Variable                    | Default                                         | Notes                                                                                                               |
| --------------------------- | ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| `DATABASE_URL`            | `sqlite:///./goalpilot.db`                    | optional; a PostgreSQL URL is also accepted                                                                         |
| `SECRET_KEY`              | *(empty)*                                     | **required in production**; the app refuses to start without it                                               |
| `EXPOSE_RESET_TOKEN`      | `true` in development, `false` in production  | Dev only — returns the reset token so the flow is demonstrable. Defaults to `false` when `GOALPILOT_ENV=production` |
| `GOALPILOT_ENABLE_RL`     | `true`                                        | `false` disables the RL and hybrid arms; they then report `unavailable` and the comparison falls back to the LP |
| `GOALPILOT_RESEARCH_PATH` | auto-detected                                   | absolute path to `GoalPilot_AI_Completed`                                                                         |
| `CORS_ORIGINS`            | `http://localhost:5173,http://127.0.0.1:5173` | explicit allow-list                                                                                                 |

No secret is committed. Only `.env.example` files are in the repository.

---

## 5. Migrate

```powershell
Set-Location S:\fyp\GoalPilot_AI_Platform\backend
& $py -m alembic upgrade head          # apply
& $py -m alembic current               # show the applied revision

# Optional PostgreSQL DDL preview without connecting:
& $py -m alembic upgrade head --sql > ..\outputs\migration_postgres.sql
```

Verified: **21 tables**, **53 `NUMERIC` money/rate columns**, **29 foreign keys**, **24
`ON DELETE CASCADE`** rules; `downgrade base` reverts cleanly.

On SQLite the schema is created at startup, so Alembic is optional for the quick path.

> **SQLite is the supported database.** A fresh clone runs with no server and no credentials:
> migrations were verified on both a fresh file and an existing database. PostgreSQL stays
> optional and untested. See
> [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) §5 for the exact blocker and the two-line fix.

---

## 6. Load the models

Nothing to do. The platform imports the research modules in-process and loads the checkpoint on
demand. No research model is retrained at startup, and torch is imported **lazily** — the LP
path never pays for it.

```powershell
# locate the research project and confirm every model module imports
Set-Location S:\fyp\GoalPilot_AI_Platform\backend
& $py -c "from app.engines import research_loader; import json; print(json.dumps(research_loader.status().as_dict(), indent=2))"
```

Set `GOALPILOT_RESEARCH_PATH` if auto-detection fails.

---

## 7. Test

```powershell
Set-Location S:\fyp\GoalPilot_AI_Platform\backend
& $py -m pytest -q                                   # 268 tests (2026-10-18)
& $py -m pytest -q -m "not slow"                     # skip the RL/hybrid tests
& $py -m pytest -q --junitxml=..\outputs\audit\release_junit.xml
```

**Current verified result (2026-10-18, release pass): `268 tests, 0 failures, 0 errors, 0 skipped` (35.8 s).**
Browser acceptance: **8/8 Playwright tests passed (19.9 s)** against a fresh SQLite database.
Raw artefacts: `outputs/audit/release_junit.xml`, `outputs/audit/release_pytest.txt`,
`outputs/audit/release_playwright3.txt`.

The table below is the historical suite shape from 2026-10-14, when the suite held 137 tests. It is
kept for provenance; the current total is 268 and includes `test_audit_regressions` (14) plus the
suites added since.

| suite (historical, 2026-10-14) | tests |
| ----------------------- | ----: |
| `test_financial_calc` |    27 |
| `test_lp_engine`      |    21 |
| `test_forecasting`    |    16 |
| `test_monthly`        |    15 |
| `test_selector`       |    14 |
| `test_auth`           |    12 |
| `test_scenarios`      |    12 |
| `test_api_e2e`        |    11 |
| `test_isolation`      |     9 |

The research suites (200 tests) also still pass against the imported modules, including the
archived-parity guarantee (100 users × 5 policies × 142 months, rewards equal to **1e-12**).

---

## 8. Run

```powershell
# terminal 1 — API
Set-Location S:\fyp\GoalPilot_AI_Platform\backend
$env:DATABASE_URL = "sqlite:///./goalpilot.db"
& $py -m uvicorn app.main:app --reload --port 8000
#   OpenAPI  http://127.0.0.1:8000/docs
#   ReDoc    http://127.0.0.1:8000/redoc

# terminal 2 — UI
Set-Location S:\fyp\GoalPilot_AI_Platform\frontend
npm run dev
#   http://localhost:5173   (Vite proxies /api to 127.0.0.1:8000)
```

Then:

```powershell
# verify the model integration without the UI
& $py ..\scripts\smoke_engines.py

# run the full academic demonstration and capture a transcript
& $py ..\scripts\demo_end_to_end.py --base-url http://127.0.0.1:8000/api
```

Single-origin production build:

```powershell
Set-Location S:\fyp\GoalPilot_AI_Platform\frontend ; npm run build
Set-Location ..\backend
$env:GOALPILOT_ENV="production"; $env:GOALPILOT_SERVE_FRONTEND="true"; $env:EXPOSE_RESET_TOKEN="false"
$env:SECRET_KEY = (& $py -c "import secrets;print(secrets.token_urlsafe(48))")
& $py -m uvicorn app.main:app --port 8000 --workers 1     # UI at /app
```

See [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) for why `--workers 1` and the full hardening
checklist.

---

## 9. What the application does

### Public

Landing page, login, registration, password recovery, password reset, privacy and disclaimer.
Real authentication: bcrypt hashes, signed JWTs, a rotating token version that revokes every
session on sign-out or password change, single-use time-limited reset tokens stored only as
hashes.

### Authenticated

| Page                       | Purpose                                                                                                                                                                        |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Dashboard                  | liquid savings, income, actual vs expected expenses, projected surplus, goal funding, emergency-fund progress, debt, provenance labelling                                      |
| Onboarding                 | multi-step wizard with saved progress: income, savings/assets, liabilities, savings preferences, risk and planning preferences                                                 |
| Financial profile          | income normalisation, assets, liabilities, savings and risk parameters                                                                                                         |
| Assets / Liabilities       | asset and debt management, with the EMI-not-principal rule stated in the UI                                                                                                    |
| Monthly finances           | open the month, record income and expenses, estimates, actuals, duplicate protection                                                                                           |
| Reconciliation             | category-wise forecast vs actual, over/under budget, unmatched categories, forecast preserved                                                                                  |
| Budgets                    | category limits, budget status, persistent-overspend and recurring-expense detection                                                                                           |
| Goals / Goal detail        | create, edit, pause, complete, archive; projections, feasibility, realistic alternatives, contributions                                                                        |
| Optimisation workspace     | pick an algorithm (unavailable ones disabled with the reason), edit assumptions, run, review allocations, constraint diagnostics, validation and the diff vs the previous plan |
| Algorithm comparison       | LP vs RL vs hybrid vs rule baseline on one shared scenario, with the decision rule, every not-selected reason and the recorded research reference                              |
| Scenario simulation        | eight stress presets with quantified deltas and a narrative                                                                                                                    |
| Forecast history / Reports | method and cut-off per stored forecast, accuracy, backtest, run history                                                                                                        |
| Settings / Account         | preferences and assumption defaults; JSON export and guarded account deletion                                                                                                  |

Every data page implements explicit loading, error (with retry), empty and success states. No
fabricated metrics: an arm that did not run reports no numbers.

---

## 10. Architecture

```
frontend/  React 18 + TypeScript + Vite + Tailwind + Recharts      24 routes
backend/
  app/api/        auth · profile · goals · monthly · optimization · scenarios · dashboard · meta
  app/core/       security (JWT, bcrypt) · deps (ownership) · ratelimit · errors
  app/services/   cashflow · goals · forecasting · scenarios · planner
  app/engines/    research_loader · lp_engine · rl_engine · hybrid_engine · selector
  app/schemas/    Pydantic v2 contracts
  alembic/        the single migration
GoalPilot_AI_Completed/   read-only research source of truth
```

Why this shape: the models are Python, so a separate optimisation service would add a process
and a serialisation boundary around code that already works in-process. PostgreSQL with SQLite
fallback gives production durability without a mandatory server for local work. Full rationale
and the complete API contract: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

### Service interfaces

* **LP** — validated financial state + goals → solver status, feasibility, goal-wise allocation,
  monthly contributions, initial-savings and investment allocation, financing, shortfalls,
  objective, constraint diagnostics, assumptions, runtime, model/config version.
* **RL** — a loaded, versioned policy → the trajectory it actually produced, its metrics, the
  version, the feasibility status, and the profile-mapping disclosure. No confidence value is
  invented for a model that does not produce one.
* **Hybrid** — RL proposes θ (investment fraction, financing), LP allocates under θ and remains
  the allocator of record, the simulator evaluates. θ can only tighten.
* **Selector** — a declared decision rule, validated plans only, an explicit fallback to the LP,
  and a written reason for every arm that was not chosen.

---

## 11. Documentation

| Document                                                          | Contents                                                                               |
| ----------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| [`docs/PROJECT_AUDIT.md`](docs/PROJECT_AUDIT.md)                 | full inventory, mathematical formulations, 15 findings, what was reused vs built       |
| [`docs/MODEL_READINESS.md`](docs/MODEL_READINESS.md)             | per-model readiness gate with evidence, and the progression decision                   |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)                   | stack rationale, component diagram, schema, complete API contract, security boundaries |
| [`docs/ALGORITHM_DESIGN.md`](docs/ALGORITHM_DESIGN.md)           | LP formulation, RL bridge, hybrid θ, forecaster, selection rule, comparison basis     |
| [`docs/ALGORITHM_EVALUATION.md`](docs/ALGORITHM_EVALUATION.md)   | research held-out results, live platform comparison, 137-test breakdown, known gaps    |
| [`docs/DATA_DICTIONARY.md`](docs/DATA_DICTIONARY.md)             | every table, every computed field, provenance labels, quality rules, versions          |
| [`docs/DEMO_GUIDE.md`](docs/DEMO_GUIDE.md)                       | step-by-step panel demonstration and likely questions with answers                     |
| [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)                       | setup, SQLite migrations, optional PostgreSQL, operations, hardening checklist         |
| [`docs/FRONTEND_BUILD_REPORT.md`](docs/FRONTEND_BUILD_REPORT.md) | the frontend build output and file inventory                                           |

Evidence artefacts: `outputs/demo_transcript.txt`, `outputs/junit_backend.xml`,
`outputs/pytest_full_backend.txt`, `outputs/migration_postgres.sql`.

---

## 12. Known limitations

Stated plainly, not hidden.

1. **RL is not the best arm.** It does not beat a simple investment rule on the research cohort.
   It is implemented, evaluated and reported honestly, and it is not the default.
2. **The hybrid shows no demonstrated improvement.** It executes and its θ genuinely changes the
   LP plan, but on every scenario tested it tied the LP. No superiority is claimed.
3. **The comparison basis is limited in two disclosed ways.** The shared action contract has no
   mechanism to allocate existing savings to a goal (so the LP and hybrid are re-solved with
   those pools excluded), and the loan dimension is zeroed for every arm because the
   environment permits one active loan while the LP proposes one per goal. Both are returned in
   the response's `notes`.
4. **The checkpoints have 5 action slots.** A user with more than 5 goals gets an explicit
   `goal_slot_limit` refusal and the LP plan. Nothing is padded or truncated.
5. **The reward-function defects diagnosed by the research audit are not fixed** (risk-penalty
   dominance, component scaling). Fixing them requires a retrain under a *selected* reward
   version, and no evidence selects one (fresh-split difference +0.0069, p = 0.72).
6. **SQLite is the supported target** — migrations verified on a fresh and an existing database.
   PostgreSQL remains optional and untested; nothing in the acceptance criteria depends on it.
7. **Browser automation requires both servers to be running.** The committed Playwright suite is
   the browser-level check (`cd frontend && npx playwright test`); it passed 8/8 on 2026-10-18
   against a fresh database. It is not part of `pytest`, so a backend-only run does not execute it.
8. **The rate limiter is in-process**, so it needs a shared store before running multiple
   workers.
9. **The first RL request costs ~20–30 s** while torch imports. The LP path is ~60 ms and never
   touches torch.
10. **No cross-user learning in the forecaster.** No consent mechanism exists, so per-user
    isolation is enforced instead.
11. **Colab execution remains unverified** — it was never run from this host.
12. **The educational layer is uncited.** No verified NISM publication exists in the repository,
    so its content is presented as general principles, explicitly not as quotations, and any
    course-stated rate or rule is not restated as current fact.

---

## 13. Licence and use

Academic research prototype. Not a regulated advisory service. Do not use it to make real
financial decisions without independent professional advice.

---

## Final status (2026-10-18)

| Check                                                 | Result                                                                   |
| ----------------------------------------------------- | ------------------------------------------------------------------------ |
| Backend test suite                                    | **268 tests, all passing** (35.8 s, exit 0)                              |
| Browser acceptance (Playwright)                       | **8 / 8 passed** (19.9 s), fresh SQLite database                         |
| End-to-end acceptance (`scripts/e2e_acceptance.py`) | 46 / 46 checks — last run 2026-10-17, not re-run in this pass             |
| Algorithm sweep (`scripts/evaluate_algorithms.py`)  | 5 households x 4 arms; raw data in `outputs/algorithm_evaluation.json` |
| Frontend production build                             | `tsc` clean, Vite build succeeded                                      |
| Live sources verified                                 | AMFI NAV file, NSE index, mfapi history, ICICI/Axis/BoB published rates  |

### New capabilities

* **Protected savings buffer** — `max(savings target, cash reserve)` is ring-fenced before any
  goal contribution, reported as `protected_buffer`, with `buffer_deficit` when it cannot be met.
* **Investment discovery** — AMFI direct-growth schemes (live), government small-savings reference,
  optional NAV history; suitability scoring with reasons and cautions; labelled category scenarios
  when a source is unavailable.
* **Loan discovery and analysis** — published lender rates, RBI benchmark, EMI/amortisation/APR,
  affordability checks, floating-rate sensitivity, save-versus-borrow, and four explicit rate
  classes (`historical_benchmark`, `published_lender_rate`, `estimated_scenario`,
  `personalised_offer`).
* **Structured recommendations** — deterministic numbers plus model-written prose only, with
  grounding checks and a deterministic fallback.

### Documentation map

| Document                                    | Contents                                              |
| ------------------------------------------- | ----------------------------------------------------- |
| `docs/FINAL_SYSTEM_AUDIT.md`              | Component-by-component audit, defects found and fixed |
| `docs/FINAL_VALIDATION_STATUS.md`         | What was executed, with results, and what was not     |
| `docs/ALGORITHM_DESIGN.md`                | Cash-flow definition, LP, RL, hybrid, selector        |
| `docs/ALGORITHM_EVALUATION.md`            | 5-household sweep with measured results               |
| `docs/MODEL_READINESS.md`                 | Readiness level per model and retraining policy       |
| `docs/API_SOURCE_REGISTER.md`             | Every source, licence, status and fallback            |
| `docs/DATA_SOURCES_AND_PROVENANCE.md`     | Per-dataset provenance and permitted use              |
| `docs/FINANCIAL_ASSUMPTIONS.md`           | Every assumption and its override                     |
| `docs/INVESTMENT_AND_LOAN_INTEGRATION.md` | Rate classes, sources, formulas, limitations          |
| `docs/LLM_RECOMMENDATION_SCHEMA.md`       | Model contract, validation, fallback                  |
| `docs/DEMO_GUIDE.md`                      | 12-minute reproducible demonstration                  |
| `docs/DEPLOYMENT.md`                      | Install, configure, migrate, run, verify              |

### Quick start

```bash
cd backend && python -m pip install -r requirements.txt
python -m uvicorn app.main:app --port 8000
cd ../frontend && npm ci && npm run dev
```

### Not verified

Browser acceptance is a committed Playwright suite (`cd frontend && npx playwright test`):
**8/8 in 19.9 s on 2026-10-18**, including plan generation and a what-if scenario. No RL/hybrid
retraining was performed. The live Gemini call was verified on 2026-10-17
(`gemini-2.5-flash`, `used: true`); the 2026-10-18 release pass ran with the LLM disabled and did
not re-exercise it. See `docs/FINAL_VALIDATION_STATUS.md` and
`outputs/GOALPILOT_AUDIT_REPORT.md`.
