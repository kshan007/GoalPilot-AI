# Remaining Work

> **Superseding addendum — 2026-10-18.** The status line below is the historical 2026-10-17 record.
> Current verified evidence: **268 backend tests**, **8/8 browser tests** (fresh database),
> `npm run build` clean. Per-goal `risk_constraint` remains unenforced and the live Gemini path was
> not re-exercised. See `outputs/GOALPILOT_AUDIT_REPORT.md` §13.

Status as of 2026-10-17, after closing the last two items. One item is implemented but could not be
measured, because the Gemini quota ran out mid-verification; that is stated as such rather than
presented as a result.

**Acceptance criterion** — a user can enter a realistic profile, manage multiple goals, protect a
savings buffer, compare sourced investment and loan options, obtain a constraint-checked plan, and
receive a structured explanation, with recalculation when circumstances change.
**Status: met.** Evidence: 247 backend tests, 5/5 browser tests, 46/46 acceptance checks, one live
Gemini generation (before quota exhaustion), 19 screenshots.

---

## Closed

| # | Item | Resolution |
|---|---|---|
| 1 | CORS headers on unhandled 500s | Outer catch-all middleware; 3 tests including a no-leak check |
| 2 | No edit control for income sources | Edit/Cancel on the income table |
| 3 | Ambiguous allocation columns | `From cash now` / `Already set aside`, with tooltips |
| 4 | LP objective vs scoring metric | **Closed by disclosure.** `/optimize/compare` now returns `objective_disagreement` (which arm wins on achievement vs on deadline completion) and `decision_basis` (the LP-anchored rule). Two tests assert both are present and that every non-selected arm carries a reason |
| 5 | RL/hybrid evaluation on the corrected environment | Re-run, reproducible; checkpoint intentionally not retrained |
| 6 | PostgreSQL dependency | Removed — SQLite is the supported target, migrations verified on fresh and existing databases |
| 7 | Browser tests | Playwright suite, 5/5 in 45 s |
| 8 | Gemini latency | **Implemented, unmeasured** — thinking is disabled by default (`GOALPILOT_GEMINI_THINKING_BUDGET=0`) and the client drops the field and retries if a model rejects it. Quota was exhausted before the change could be timed, so no before/after number is claimed |

## Open

| # | Item | Why |
|---|---|---|
| 9 | Re-measure generation latency | Needs a fresh quota window. The deterministic fallback covers the gap meanwhile, and `LLM` status reports `quota_exceeded` honestly |
| 10 | PostgreSQL | Optional and untested by choice; nothing depends on it |

## Known model-name churn (important for deployment)

* `gemini-2.5-flash-lite` → **404**, "no longer available to new users", Google points to
  `gemini-3.5-flash-lite`. Any earlier advice naming the 2.5 lite model was wrong and has been fixed.
* `gemini-3.5-flash-lite` → **400 INVALID_ARGUMENT** when the thinking field was present; the client
  now removes the field and retries, so the failure no longer blocks the request.
* `gemini-2.5-flash` → the verified working model, and still the configured default.

## Verification commands

```bash
cd backend && python -m pytest -q            # 247 passing
cd .. && python scripts/e2e_acceptance.py    # 46/46
python scripts/evaluate_algorithms.py        # reproducible sweep
cd frontend && npm run build                 # tsc + vite
cd frontend && npx playwright test           # 5/5 (servers running)
```
