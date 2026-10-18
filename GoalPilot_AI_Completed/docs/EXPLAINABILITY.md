# Explainability and financial knowledge layer (Phase I)

**Date:** 2026-10-11
**New modules:** `simulation/05_simulation_runs/rl_prototype/goalpilot_knowledge.py`,
`simulation/05_simulation_runs/rl_prototype/goalpilot_explain.py`
**New tests:** `tests/test_goalpilot_explain.py` (10)
**No existing behaviour changed.** The new modules import the environment read-only.

---

## 1. What existed before this pass

A repository-wide search for `NISM`, `investor education`, `knowledge base`, `retrieval`,
`explainab*`, `RAG` across `S:\fyp\GoalPilot_AI_Completed` returned **no** knowledge base, **no**
retrieval or RAG module and **no** explainability module. The research system reported numbers;
it did not explain them.

The companion web application (`S:\fyp\GoalPilot_Application`) did contain a list of guidance
strings under the name `nism_guidance_notes`, rendered in the UI as "NISM Investor Guidance".
Those strings were written by the project and carried **no citation**. Asserting a named source
without one is exactly what the brief forbids, so they were relabelled in this pass (see
`docs/APPLICATION.md` §5).

## 2. What this pass adds

Two small, dependency-light modules that turn a *finished* rollout into an auditable
explanation.

### 2.1 `goalpilot_knowledge.py` — the knowledge layer

Ten general financial principles (emergency reserve, horizon/volatility, inflation, debt
service, return uncertainty, investable capacity, prioritisation, compounding, earmarking vs
ownership, periodic review). Each entry carries:

- `id`, `topic`, `keywords`, `text`
- `status = "uncited_general_principle"`

The status field is deliberate. The project has **no verified copy of any external
investor-education publication**, so no entry is attributed to NISM or anyone else. Recording
the absence of a source is more honest than inventing one.

`KnowledgeBase.retrieve(query, k)` is a deterministic keyword/topic retriever. An unrecognised
query returns an **empty list** rather than a best guess, so a caller can acknowledge that the
knowledge base does not cover the question.

### 2.2 `goalpilot_explain.py` — the explanation engine

| function | what it does |
|---|---|
| `rollout(env, action_fn, uid)` | runs one episode and records the full monthly ledger (budget, allocations, capacity events, cash, portfolio, net worth) |
| `build_facts(env, res)` | derives **every** number the explanation may use, from recorded state only |
| `explain(env, uid, action_fn, kb=…, sensitivity=…)` | returns the structured explanation (facts + 7 narrative sections + grounding record) |
| `sensitivity(profiles, goals, market, uid, config, action_fn, variants)` | deterministic what-if re-runs under a perturbed market-return or investment-capacity assumption |
| `render_markdown(explanation)` | human-readable rendering |

## 3. The five layers, kept apart

The brief requires that these never be conflated. The engine enforces the separation
structurally:

| layer | where it lives | how the explanation marks it |
|---|---|---|
| Financial calculations | `goalpilot_env` state | every number in `facts`, tagged `numbers_are: "computed, not forecast"` |
| Optimisation decisions (LP) | the executed action sequence | `why_this_allocation` narrates the *executed* allocation, not a claimed optimum |
| RL policy decisions | the executed action sequence | identical treatment — the explanation describes what was executed |
| General financial education | `goalpilot_knowledge` | `grounding.principles`, each with `status: uncited_general_principle` |
| Assumptions / uncertain forecasts | `sensitivity` + `what_could_change_the_result` | labelled "what-if re-runs … not forecasts" |

## 4. What every recommendation explains

`explain()` returns seven sections, all generated from the facts:

1. `goals_and_constraints` — goal count, combined inflated target, income, essential expenses,
   existing EMI, investable surplus, declared risk profile, and the capacity ratio **explicitly
   labelled an affordability ceiling, not a validated risk-suitability measure**.
2. `why_this_allocation` — how much of the surplus was executed as savings vs investment, how
   often the investment ceiling bound, how much request was refused, and how much budget the
   per-goal caps released (finding R-13).
3. `why_others_received_less` — the lowest-funded goals with their priority, deadline, funded
   amount and shortfall, plus the goals that did reach target.
4. `expected_shortfalls_and_deadline_risk` — total shortfall, and whether the profile is
   **structurally infeasible** (≤ 0 investable surplus), in which case it states plainly that no
   policy — LP, rule-based or RL — can fund the goals from cash flow.
5. `role_of_savings_returns_and_borrowing` — loan principal and interest paid (interest is a
   certain cost), final balance sheet, realised investment gain, and the explicit warning that
   earmarked goal funding is a memo total that must never be added to net worth.
6. `sensitivity` — deterministic what-if results (see below).
7. `what_could_change_the_result` — the four assumption families that move the answer.

## 5. Sensitivity

`sensitivity()` perturbs **one** named assumption at a time and holds goals, deadlines, reserves
and the policy fixed, so the reported differences are attributable to that assumption alone:

- `capacity_multiplier` — scales the user's `investment_capacity_ratio` (clipped to [0, 1]).
- `nifty_multiplier` — scales the monthly `nifty_monthly_return` path.

Measured behaviour (asserted in tests): with capacity × 0 the executed investment is exactly 0
and the shortfall does not decrease; with a halved market path the investment channel still
executes but earns less. Runs are byte-deterministic: the same variant list produces an
identical result object.

## 6. Evidence

```powershell
$py = "C:\Users\sudha\AppData\Local\Programs\Python\Python313\python.exe"
Set-Location S:\fyp\GoalPilot_AI_Completed
& $py -m pytest tests\test_goalpilot_explain.py -q
# 10 passed
```

The tests protect: retrieval relevance and harmless failure on unknown queries; that every
principle is marked uncited; that `facts` match the simulator's own goal/target/net-worth arrays
to 1e-12; that the budget identity holds and there are zero affordability violations during a
lineaged rollout; that all seven sections are non-empty; that the rendered text contains no
guarantee language (`guarantee`, `will earn`, `risk-free`, `assured return`); that a
zero-surplus user is reported as structurally infeasible; and that sensitivity is deterministic.

## 7. Limitations

1. The knowledge base is ten general principles, uncited and deliberately generic. It is a
   teaching layer, not a literature review.
2. There is **no retrieval-augmented generation** over external documents, because no such
   corpus is available in this project. Retrieval is keyword matching over the shipped entries.
3. Sensitivity covers two assumption families (market path, capacity). Income/expense shocks and
   goal-deadline shifts are described but not swept.
4. Explanations describe a *single* executed strategy. Comparing two strategies side by side is
   left to the evaluation harness (`docs/final/EVALUATION_AND_RESULTS.md`).
5. The engine explains what the simulator did; it does not certify that the simulator's
   assumptions are financially optimal.
