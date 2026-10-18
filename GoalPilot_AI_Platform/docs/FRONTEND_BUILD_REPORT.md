# GoalPilot AI Platform — frontend build report

Target directory: `S:\fyp\GoalPilot_AI_Platform\frontend` (nothing outside it was created or modified).

## Commands run

```
npm install --no-audit --no-fund
npm run build
```

`npm install` output (tail):

```
npm warn deprecated recharts@2.15.4: 1.x and 2.x branches are no longer active. Bump to Recharts v3 to receive latest features and bugfixes.

added 174 packages in 52s
```

First `npm run build` attempt failed with one TypeScript error, which was fixed:

```
src/pages/Optimize.tsx(493,42): error TS18047: 'plan.diff' is possibly 'null'.
```

Fix: the plan diff is now read once into a local binding (`planDiff`, `diffGoalChanges`,
`diffColumnKeys`) so TypeScript keeps the null-narrowing inside the `map` callbacks.

## Final `npm run build` output (exact, verbatim)

```
> goalpilot-ai-frontend@1.0.0 build
> tsc && vite build

vite v5.4.21 building for production...
transforming...
✓ 865 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                 0.58 kB │ gzip:   0.36 kB
dist/assets/index-VBWqcz5r.css 20.77 kB │ gzip:   4.37 kB
dist/assets/index-CXn9CorS.js 734.28 kB │ gzip: 199.85 kB
✓ built in 30.23s
stderr:

(!) Some chunks are larger than 500 kB after minification. Consider:
- Using dynamic import() to code-split the application
- Use build.rollupOptions.output.manualChunks to improve chunking: https://rollupjs.org/configuration-options/#output-manualchunks
- Adjust chunk size limit for this warning via build.chunkSizeWarningLimit.
```

Build status: **succeeded, exit code 0, zero TypeScript errors.** The only message on stderr is Vite's
informational chunk-size warning (recharts + react in one vendor chunk); it is not an error.

Artifacts produced: `dist/index.html`, `dist/assets/index-VBWqcz5r.css`, `dist/assets/index-CXn9CorS.js`.

## Files created (all under `S:\fyp\GoalPilot_AI_Platform\frontend`)

Config / root:
- `package.json`, `package-lock.json`, `tsconfig.json`, `tsconfig.node.json`, `vite.config.ts`
- `index.html`, `postcss.config.js`, `tailwind.config.js`, `.env.example`

API layer:
- `src/api/types.ts` — interfaces for every response shape in the contract
- `src/api/client.ts` — typed fetch wrapper, `ApiError` (code/message/details), bearer token from
  `localStorage["gp_token"]`, 401 clears the token and redirects to `/login`, plus typed functions for
  every endpoint (auth, profile, preferences, onboarding, income, assets, liabilities, goals, monthly,
  transactions, estimations, reconciliation, budgets, forecast, optimisation, scenarios, dashboard,
  models, account, meta) and a `downloadJson` helper

Auth:
- `src/auth/AuthContext.tsx` — `{user, token, loading, login, register, logout, refresh}`; restores the
  session with `GET /auth/me` on mount and holds `loading` true throughout
- `src/auth/ProtectedRoute.tsx` — loading state while resolving, redirect to `/login`, otherwise outlet

Shared UI:
- `src/components/ui.tsx` — Card, PageHeader, Button, Field, TextInput, SelectInput, Checkbox,
  LoadingState, ErrorState (with Retry), EmptyState, InlineNotice, Badge, Provenance, StatCard,
  KeyValueTable, WarningList, JsonBlock/flatten
- `src/components/Layout.tsx` — collapsible sidebar app shell, mobile drawer, header, research banner footer
- `src/components/PublicLayout.tsx` — public nav + footer with Terms/Privacy/Disclaimer links
- `src/components/Charts.tsx` — recharts wrappers (income vs expense, category breakdown, savings trend,
  goal funding, forecast error, comparison bars), each rendering an empty state when its array is empty
- `src/lib/format.ts` — `formatMoney` (2 decimals + thousands separators) and other formatters
- `src/lib/useAsync.ts` — loading/error/retry data hook and an action runner

Routing:
- `src/App.tsx`, `src/main.tsx`, `src/index.css`, `src/vite-env.d.ts`

Pages (`src/pages/`):
- Public: `Landing.tsx`, `Login.tsx`, `Register.tsx`, `ForgotPassword.tsx`, `ResetPassword.tsx`,
  `Privacy.tsx`, `NotFound.tsx`
- Protected: `Onboarding.tsx`, `Dashboard.tsx`, `Profile.tsx`, `Monthly.tsx`, `Reconciliation.tsx`,
  `Budgets.tsx`, `Assets.tsx`, `Liabilities.tsx`, `Goals.tsx`, `GoalDetail.tsx`, `Optimize.tsx`,
  `Compare.tsx`, `Scenarios.tsx`, `ForecastHistory.tsx`, `Reports.tsx`, `Settings.tsx`, `Account.tsx`

## Requirement notes

- Routes implemented exactly as specified; public routes are outside `ProtectedRoute`, protected routes
  are nested inside it under the app shell layout.
- `/optimize` reads `GET /optimize/algorithms`, disables options where `ready` is false, shows the
  `reason`, edits the required assumptions, runs `POST /optimize/plan`, and renders the allocation
  table, projections, constraint diagnostics, validation/summary, warnings and the plain-language diff.
- `/compare` shows per-arm label, status, available, feasible, metric basis, metrics, warnings and, for
  unavailable arms, the `fallback_reason` plus an explicit statement that no metric exists because
  nothing ran. It also shows `recommendation_reason`, `not_selected` reasons, `decision_rule`, `notes`
  and `research_reference`, and never implies RL is superior.
- `/monthly` drives open → transactions (add/edit/delete) → estimate-expenses (method, data-quality and
  provisional flags shown) → actuals → reconcile, and labels every value actual / estimated / projected.
- `/onboarding` is a 7-step wizard persisted with `PUT /onboarding {step}` on every step change and
  restored with `GET /onboarding` on load, ending in a profile summary and `POST /onboarding/complete`.
- `/settings` edits preferences and assumption defaults, with the required note that risk tolerance and
  loss ability are stored separately and neither is inferred from the other.
- `/account` downloads the `GET /account/export` JSON and requires typing `DELETE` before the
  `DELETE /account?confirm=DELETE` call.
- `/reports` shows goal progress, `GET /forecast/accuracy` history and `GET /optimize/runs` history.
- Every data page implements loading, error (API `message` + Retry), empty and success states. No sample
  financial data is presented as real; the only illustrative table is on the landing page and is labelled
  "Illustrative example - not real results".
- Responsive from 375 px up; collapsible sidebar; single accent colour; no emoji in UI copy.
- Authenticated app footer banner: "Research decision-support prototype. Not financial advice. No
  trades, transfers or loans are executed."

## Pages not completed

None. All pages listed in the brief are implemented and the production build succeeds.

## Caveat on verification depth

The backend at `http://127.0.0.1:8000` was **not running** during this task (connection refused on
`GET /health`), so responses were typed from the backend source under
`S:\fyp\GoalPilot_AI_Platform\backend\app` rather than from live calls. The build itself was executed and
verified. Runtime behaviour against a live backend has not been exercised.
