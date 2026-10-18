# Model Readiness

What is loaded, what was verified in this pass, and what must not be claimed.

Readiness levels used here:

* **R1 — Runs**: the artefact loads and produces output on a real user state.
* **R2 — Constrained**: output passes the financial safety validation.
* **R3 — Evaluated**: measured against other arms on shared inputs.
* **R4 — Trusted for default use**: R3 plus a demonstrated advantage.

---

## 1. LP optimiser

| Field | Value |
|---|---|
| Artefact | Research implementation, imported read-only from `GoalPilot_AI_Completed` |
| Solver | `scipy.optimize.linprog(method="highs")` |
| Readiness | **R4** for feasibility and accounting; **R3** for objective quality |
| Verified | 21 unit tests; runs on all five evaluation households; always feasible |
| Runtime | ~126 ms mean |
| Known issue | Its objective and the evaluation metric disagree: the metric rewards concentration, the objective spreads. See `ALGORITHM_EVALUATION.md` §3.1 |

Feasibility and constraint accounting are trustworthy. Optimality *relative to the product's
scoring metric* is not yet established, which is why R4 is claimed for safety, not for quality.

## 2. PPO policy

| Field | Value |
|---|---|
| Checkpoint | `training_logs/experiments/ppo_recommended_v1/archived_v1/seed7/best/best_model.zip` |
| Framework | Stable-Baselines3 PPO + Gymnasium |
| Readiness | **R2** |
| Verified | Loads, observation/action spaces match, produces valid bounded actions, reproducible under a fixed seed; 2,189 ms mean |
| Evaluation | Mean achievement 0.477 vs LP 0.434, but shortfall 1,007,700 vs 908,258 and worse deadline achievement |
| Caveat | Trained before the protected-buffer change altered the environment's expenditure input, so its evaluation is **stale** |
| Decision | Not promoted. No retraining performed: the checkpoint is preserved untouched, and retraining without authorisation would discard a research artefact |

## 3. Hybrid

| Field | Value |
|---|---|
| Readiness | **R2** |
| Verified | RL parameters demonstrably reach the LP (asserted); invalid output falls back to LP; runs on every household |
| Evaluation | Identical achievement to LP to four decimals; budget binds before the RL-adjusted parameters |
| Decision | Kept as an available arm, not the default. The claim "hybrid improves outcomes" is **not** supported |

## 4. Rule baseline

| Field | Value |
|---|---|
| Readiness | **R3** |
| Evaluation | Best mean achievement (0.549) and lowest shortfall (435,000) on the sweep; selected by the selector in 2 of 5 cases |
| Caveat | A greedy priority heuristic; its strength may be an artefact of the metric (see §3.1 of the evaluation) |

## 5. Gemini (explanation layer)

| Field | Value |
|---|---|
| Readiness | **R3** — verified live on 2026-10-17 |
| Verified | Schema validation, banned-language rejection, amount-grounding rejection, timeout and quota fallbacks — 21 tests |
| Live result | `gemini-2.5-flash`, `used: true`, `status: ok`, schema-valid, every quoted figure matched the computed plan; latency 26.6 s |
| Live findings | (1) Gemini rejects this schema as `response_schema` ("too many states for serving"), so JSON mode + validation + one bounded repair call is used; (2) the model restated a correct derived total absent from the facts, so pre-computed sums were added and unverified sentences are now dropped instead of the whole answer |
| Safety property | The model cannot change a number; it returns prose only, and amounts are copied from deterministic services afterwards |

## 6. Retraining policy

1. Retrain only when a specific deficiency is demonstrated and recorded.
2. Never overwrite a checkpoint; new versions go to a new directory and the path is configurable.
3. A retrained policy must pass the same constraint tests and then the cross-profile sweep before
   it can be selected.
4. User data collected at runtime is never used for training automatically.

## 7. What must not be claimed

* That RL or the hybrid improves outcomes. It does not, on the current evidence.
* That the LP is optimal in the sense the product scores. It is feasible, safe and accountable.
* That any model predicts returns, eligibility or approval.
* That the language model has been exercised against the live service.

---

## 7. Latency, quota and model-name churn (2026-10-17)

The model's *capability* readiness is unchanged (R3). Its *operational* readiness has two caveats
that belong next to the readiness level:

* **Quota.** Free-tier quota for `gemini-2.5-flash` was exhausted during verification. The
  application degrades to the deterministic explanation and reports `quota_exceeded`; it does not
  fail or fabricate. A production deployment needs a paid quota or a cached explanation policy.
* **Latency.** 22–27 s per generation on the observed runs, consistent with default thinking.
  Thinking is now disabled by configuration and the client tolerates a model that rejects the
  field, but the improvement is **unmeasured** — see `FINAL_VALIDATION_STATUS.md` §11.

This does not change the safety property: the model still returns prose only, and every number is
copied from deterministic services.
