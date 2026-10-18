# Demo Guide

A repeatable walk-through for a reviewer or examiner. Roughly 12 minutes.

---

## 0. Start the stack

```bash
cd S:\fyp\GoalPilot_AI_Platform\backend
python -m uvicorn app.main:app --port 8000

# second terminal
cd S:\fyp\GoalPilot_AI_Platform\frontend
npm run dev
```

Open http://localhost:5173. API docs at http://127.0.0.1:8000/docs.

Before the demo, run the acceptance script once — it proves the flow works on your machine:

```bash
cd S:\fyp\GoalPilot_AI_Platform
python scripts/e2e_acceptance.py      # expect: 46/46 checks passed
```

---

## 1. Register and onboard (1 min)

Register any email/password, then complete the profile.

| Field | Value to enter |
|---|---|
| Monthly income | 1,20,000 |
| Essential expenses | 45,000 |
| Discretionary | 10,000 |
| Monthly savings target | 15,000 |
| Preferred cash buffer | 8,000 |
| Emergency months | 6 |
| EMI-to-income cap | 35% |
| Risk capacity | 0.55 |

Add a salary income stream of 1,20,000, a liquid savings asset of 3,00,000, and an existing
personal loan with a 6,000 EMI.

**Point at:** the summary shows a 59,000 surplus, a **15,000 protected buffer**, and a
**44,000 goal budget**. The buffer is the product's central promise; it is charged before any goal.

## 2. Create three goals (1 min)

| Goal | Cost | Target | Priority |
|---|---|---|---|
| Child education | 12,00,000 | ~6 years | 5 |
| Car down payment | 4,00,000 | ~2.5 years | 3 |
| Home renovation | 6,00,000 | ~4 years | 4 |

**Point at:** each goal shows an inflation-adjusted future cost, a funding gap, and the monthly
contribution it would need on its own.

## 3. Generate the plan (1 min)

Optimise → **LP**. 

**Point at:** more than one goal funded simultaneously; total contributions ≤ 44,000; the
constraint panel showing `protected_buffer`, `gross_monthly_surplus`, and the post-buffer
`monthly_surplus`. This is the proof that the buffer is not reallocated to goals.

## 4. Compare algorithms (1 min)

Compare → four arms on identical inputs.

**Point at:** the selected arm, and be candid: on the current evaluation sweep the rule baseline
beats the LP on weighted achievement (see `ALGORITHM_EVALUATION.md` §3.1), and the hybrid matches
LP because the budget binds first. Use this to show the platform reports unwelcome results.

## 5. Investments (2 min)

Investments page → optionally tick "include NAV history", then Refresh.

**Point at:** real AMFI schemes with a NAV and its date; the provenance badge per row; the
"trailing returns" block with its exact period when history is enabled; suitability reasons and
cautions. If AMFI is unreachable, the page shows *category scenarios* — labelled as assumptions,
with no NAV or rate.

## 6. Loans (2 min)

Loans page → principal 5,00,000, tenure 48 months.

**Point at:** three published lender rates, each tagged `published lender rate`; the RBI
benchmark tagged `historical benchmark`; the **amber block** of categories with no published
product, tagged `estimated scenario`, with `published_rate = null`. Change "Scenario rate %" to
14 and recalculate — the scenario EMIs change, the published rates do not.

Then "Analyse an offer you have": 10.5%, 1% fee → EMI, total interest, **APR above the nominal
rate**, the +100/+200/+300 bp sensitivity table, and save-versus-borrow alternatives.

## 7. Recommendation (2 min)

Recommendations → Generate.

**Point at:** the banner stating whether a model wrote the prose or the deterministic fallback
did; the summary; the buffer block; the goal table with statuses and shortfalls; "Do this month";
risks; sources and missing information. Ask "What is my buffer?" — the answer is computed, not
invented.

## 8. Change the circumstances (2 min)

Edit the **salary income stream** to 90,000 (not the profile's income field — the recorded stream
is authoritative when one exists). Re-run the plan, then regenerate the recommendation.

**Point at:** the goal budget falls from 44,000 to 14,000, the buffer stays at 15,000, contributions
fall, and the new recommendation differs from the previous one. This is the adaptive requirement,
demonstrated rather than described.

## 9. Failure behaviour worth showing

* Stop the backend → the UI shows an explicit error state, not stale numbers.
* Set `GOALPILOT_ENABLE_LIVE_PROVIDERS=false` and restart → investment discovery still works,
  labelled as scenarios; nothing crashes.
* Ask a question the plan cannot answer → the assistant says the information is not available.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Investments` returns 409/422 | no financial profile | complete the profile first |
| All investment rows are "Category scenario" | AMFI unreachable or live providers disabled | expected; check the provider table at the bottom of the page |
| Recommendation `llm.status = fallback` | no `GEMINI_API_KEY` | expected; prose is deterministic and still complete |
| Loan page shows only personal loans | only three lenders are integrated | documented limitation, not a bug |
| `npm run dev` port busy | 5173 in use | `npm run dev -- --port 5174` |
