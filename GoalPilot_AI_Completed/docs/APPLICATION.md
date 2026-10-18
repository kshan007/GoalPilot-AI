# Application status and verified startup (Phase J)

**Date:** 2026-10-11
**Location:** `S:\fyp\GoalPilot_Application` (companion to the research system)
**Verified on this host** with Python 3.13.7 and the project's installed dependencies.

---

## 1. What the application actually is

A small full-stack prototype that exposes **single-goal** LP optimisation to a user. It is *not*
a second research backend and it does not duplicate the RL system.

| layer | stack | key files |
|---|---|---|
| Backend | FastAPI + Pydantic v2 + `scipy.optimize.linprog(method="highs")` | `backend/app/main.py`, `api/{health,optimization,benchmark}.py`, `schemas/*.py`, `integration/*.py`, `services/*.py` |
| Frontend | Vite + React (JSX), prebuilt `dist/` present | `frontend/src/{App.jsx,components/*.jsx}`, `frontend/vite.config.js` |
| Tests | pytest + httpx | `backend/tests/{test_api,test_optimizer,test_validation}.py` |

**Endpoints (verified live):**

| method + path | purpose |
|---|---|
| `GET /api/health` | health + research-dataset connectivity |
| `POST /api/optimize` | single-goal LP optimisation |
| `POST /api/derive-profile` | surplus / situation tier / emergency-fund metrics |
| `GET /api/benchmarks` | research benchmark population |
| `POST /api/benchmarks/run/{user_id}` | live optimisation on a research case |
| `GET /docs`, `GET /redoc` | OpenAPI UI |

The backend locates the research artefacts through `backend/app/config.py`
(`GOALPILOT_AI_PATH` env var, else a search for `GoalPilot_AI`); no path is hard-coded to a
machine.

## 2. Verified evidence (this pass)

### 2.1 Backend test suite

```powershell
$py = "C:\Users\sudha\AppData\Local\Programs\Python\Python313\python.exe"
Set-Location S:\fyp\GoalPilot_Application\backend
& $py -m pytest tests -q
```

```
...............                                                          [100%]
15 passed in 71.24s
```

### 2.2 Live end-to-end run

The server was started with `uvicorn app.main:app --port 8011` and exercised with real HTTP
requests, then stopped:

```
GET  /api/health   -> {"status":"healthy","app_name":"GoalPilot Application","version":"1.0.0",
                       "goalpilot_ai_source":{"path":"S:\\fyp\\GoalPilot_AI",
                       "directory_exists":true,"cpi_calibration_loaded":true,
                       "benchmark_dataset_loaded":true},
                       "supported_features":{"single_goal_optimization":true,
                       "multi_goal_optimization":false,"reinforcement_learning":false,
                       "solver":"scipy.optimize.linprog(highs)"}}
POST /api/optimize -> status "optimal_shortfall" (surplus below target; max cash allocated)
                      explanation.nism_guidance_notes -> 4 notes
GET  /api/benchmarks -> 200 OK
```

`/api/optimize` returns `metrics.{optimized_goal_funding, optimized_shortfall,
funding_percentage, is_goal_achieved, …}`, a `monthly_schedule`, an `explanation` block,
`warnings` and `assumptions`.

## 3. Scope honesty

The app's own health payload declares `multi_goal_optimization: false` and
`reinforcement_learning: false`. That is accurate: multi-goal planning, the constrained LP and
the PPO policies live in the research system and are **not** exposed through the web app. The
brief says to integrate the application "to the extent required by the actual project scope" and
not to build a second backend, so this gap is documented rather than papered over.

## 4. Startup instructions (verified)

```powershell
$py = "C:\Users\sudha\AppData\Local\Programs\Python\Python313\python.exe"

# backend
Set-Location S:\fyp\GoalPilot_Application\backend
& $py -m pip install -r requirements.txt
$env:GOALPILOT_AI_PATH = "S:\fyp\GoalPilot_AI"     # optional; auto-detected otherwise
& $py -m uvicorn app.main:app --port 8000          # http://127.0.0.1:8000/docs

# frontend (separate terminal)
Set-Location S:\fyp\GoalPilot_Application\frontend
npm install
npm run dev                                         # http://localhost:5173
```

`backend/.env.example` documents the environment variables. **No secret is committed**; the
committed `backend/.env` contains no credentials.

## 5. Corrected in this pass — citation honesty

`backend/app/integration/optimization_adapter.py` previously produced three guidance strings,
the first prefixed `"NISM Guidance: …"`. The project has **no verified copy of any NISM
publication and no citation**, so the prefix asserted a source that does not exist in the
repository. This was corrected:

- the prefix is now `"General principle: …"`;
- the surplus and horizon notes are unchanged in substance;
- a fourth note was added: *"Disclaimer: these are general educational principles shown by the
  GoalPilot prototype. They are not quotations from NISM or any other institution, and they are
  not personalised financial advice."*

The response field is still named `nism_guidance_notes` for API compatibility with the shipped
frontend; the field name is a legacy contract, not a claim about the content. The React heading
"NISM Investor Guidance & Financial Best Practices" was changed to "Investor Guidance &
Financial Best Practices".

Re-verified after the change: `15 passed`. The live `/api/optimize` response now returns the
relabelled notes.

## 6. Limitations

1. Single-goal only. No multi-goal, no RL inference, no saved-plan history in the app.
2. No database and no authentication; the app is a stateless request/response prototype.
3. The frontend ships a prebuilt `dist/`; `npm run build` was not re-run in this pass.
4. The LP optimiser in the app is the *unconstrained* single-goal model. It therefore inherits
   the capacity gap described in `docs/final/EVALUATION_AND_RESULTS.md` §3 — the app's
   single-goal plan is not capacity-constrained the way the v7 research benchmark is.
