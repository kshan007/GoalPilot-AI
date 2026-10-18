# Deployment

Local and single-host deployment. PostgreSQL is the intended production target; SQLite is the
supported local/demo database and the one this build was validated against.

---

## 1. Prerequisites

| Component | Version used |
|---|---|
| Python | 3.13 |
| Node | 22.x (build used 22.23.2) |
| Database | SQLite (local) or PostgreSQL 15+ |
| OS | Windows 10/11 validated; Linux should work but was not exercised |

## 2. Install

```bash
cd S:\fyp\GoalPilot_AI_Platform\backend
python -m pip install -r requirements.txt

cd ..\frontend
npm ci
```

## 3. Configuration

```bash
cd S:\fyp\GoalPilot_AI_Platform
copy .env.example .env        # then edit
```

Minimum for a local run:

```
SECRET_KEY=<at least 32 random characters>
DATABASE_URL=sqlite:///./goalpilot.db
GOALPILOT_ENV=local
```

Optional: `GEMINI_API_KEY` (enables model-written prose), `GOALPILOT_ENABLE_LIVE_PROVIDERS=false`
(offline mode), `GOALPILOT_SCENARIO_LOAN_RATE`.

Never commit `.env`. It is ignored by `.gitignore`; `.env.example` contains placeholders only.

## 4. Database

SQLite: the schema is created at startup, and the additive `recommendation_runs` table is added to
an existing database automatically. No data is dropped.

PostgreSQL:

```bash
cd backend
alembic upgrade head
```

The revision `b1f7c2a94d10` is additive only (one new table, two indexes). Downgrade removes just
that table.

## 5. Run

```bash
# API
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# Frontend (development)
cd frontend
npm run dev
```

Single-process mode (API serves the built frontend):

```bash
cd frontend && npm run build
cd ..\backend
set GOALPILOT_SERVE_FRONTEND=true
python -m uvicorn app.main:app --port 8000
```

## 6. Verify a deployment

```bash
cd backend
python -m pytest -q                       # expect all passing (236 collected)

cd ..
python scripts/e2e_acceptance.py          # expect 46/46
python scripts/evaluate_algorithms.py     # regenerates outputs/algorithm_evaluation.json

cd frontend
npm run build                             # tsc + vite
```

Health check: `GET /api/health` returns component statuses including `llm_configured`,
`investment_discovery` and `loan_discovery_and_analysis`.

## 7. External sources

| Mode | Configuration | Behaviour |
|---|---|---|
| Online (default) | `GOALPILOT_ENABLE_LIVE_PROVIDERS=true` | AMFI, NSE and lender pages fetched with a 12 s timeout; cached 6 h; per-provider failure isolated |
| Offline | `=false` | Bundled snapshots and labelled scenarios; every feature still works |
| NAV history | `GOALPILOT_ENABLE_MFAPI_HISTORY=true/false` | Optional; `unofficial_mirror` labelling applies either way |

No provider credential is required. The only secret is the Gemini key, and it is optional.

## 8. Security checklist

- [x] `SECRET_KEY` from the environment; startup fails on a default key outside `local`
- [x] bcrypt password hashing; configurable cost
- [x] JWT bearer auth on every user-owned route
- [x] Server-side ownership checks on all reads and writes; cross-user isolation tested
- [x] Rate limiting on auth and optimise endpoints
- [x] No secrets, tokens or user financial data in logs
- [x] Errors return structured envelopes without stack traces
- [x] `GEMINI_API_KEY` never reaches the client
- [x] External content treated as untrusted input; parsed defensively with size limits
- [x] No endpoint executes a notebook, a trade, a transfer or a loan

## 9. Operating limits

| Limit | Value | Reason |
|---|---|---|
| Provider HTTP timeout | 12 s | a dead source must not hang a request |
| Provider response size | 8 MB | AMFI is ~1.5 MB; anything far larger is a fault |
| Provider cache | 6 h | avoids hammering public sources |
| Gemini timeout | 45 s | bound on user-visible latency |
| NAV history enrichment | 6 schemes per request | keeps discovery responsive |

## 10. Backups and recovery

Back up the SQLite file (or the Postgres database) before any schema change. The platform stores
user financial records, so treat the database as sensitive: restrict file permissions and do not
copy it into the repository.

## 11. Known deployment gaps

* PostgreSQL was not exercised in this build; only the Alembic revision was authored.
* No container image or process supervisor is provided.
* Behind a reverse proxy, set the frontend's `VITE_API_BASE_URL` and allow the origin in CORS
  (`ALLOWED_ORIGINS`).

---

## 8. SQLite is the supported database (2026-10-17)

`DATABASE_URL` now defaults to `sqlite:///./goalpilot.db`. A fresh clone runs with no database
server, no credentials and no setup step — previously the default pointed at PostgreSQL, so a
clean checkout reported `healthy` and then returned 500 on every data endpoint.

### Verified on this host

| Scenario | Command | Result |
|---|---|---|
| Fresh database | `alembic upgrade head` | 22 tables created, head `b1f7c2a94d10`, `recommendation_runs` present |
| Existing database (created by `create_all`) | `alembic stamp head` then `alembic upgrade head` | Baselines cleanly; 3 users and 2 goals preserved |
| Application default | start with `DATABASE_URL` unset | `sqlite:///./goalpilot.db`, reported `database.reachable: true, dialect: sqlite` |

### Backups

SQLite is a single file. For a consistent hot copy use `sqlite3 goalpilot.db ".backup backup.db"`
rather than copying the file while the server is running.

### PostgreSQL

Still supported by configuration and by the Alembic revision (which is additive), but it is
**optional and untested**. Nothing in the application or the acceptance criteria depends on it.

### Foreign keys

SQLite disables foreign keys per connection by default; the engine enables them on every
connection, because the schema relies on `ON DELETE CASCADE`.
