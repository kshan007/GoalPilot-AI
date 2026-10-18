# LLM Recommendation Schema

The contract between the language model and the application, and the checks that make the model's
output safe to show.

`SCHEMA_VERSION = "recommendation@1.0"` (returned in every response).

---

## 1. Division of labour

| Layer | Produces | Trusted for |
|---|---|---|
| Deterministic services | cash flow, buffer, goal budget, allocations, shortfalls, EMI, APR, suitability, provenance | **All numbers** |
| Gemini | prose: summaries, reasons, risks, actions, commentary | **Language only** |

The model is asked for `LLMText` and nothing else. It never sees a licence to compute: the prompt
states that every amount is in the input, must be copied exactly if referenced, and that nothing
may be invented.

## 2. What the model may return (`LLMText`)

```jsonc
{
  "financial_summary": "string, <=2000 chars",
  "cash_flow_explanation": "string, <=1500",
  "plan_explanation": "string, <=2500",
  "goal_reasons": [{ "goal_ref": "G12", "reason": "string, <=1200" }],
  "tradeoffs": ["string"],
  "change_explanation": "string",
  "risks": ["string"],
  "monthly_actions": ["string"],
  "missing_information": ["string"],
  "investment_commentary": [{ "product_id": "12345", "commentary": "string, <=800" }],
  "loan_commentary": [{ "product_id": "icici_personal_loan", "commentary": "string" }],
  "alternatives": [{ "scenario": "string", "description": "string" }]
}
```

`extra="forbid"`: an unknown key fails validation. There is no numeric field anywhere in this
schema, which is what makes "the model cannot change a figure" a structural property rather than
a promise.

## 3. Validation pipeline

| # | Check | On failure |
|---|---|---|
| 1 | JSON parses and is an object | `invalid_json` → fallback |
| 2 | Pydantic validates against `LLMText` | `schema_invalid` → fallback |
| 3 | No banned language (`guaranteed`, `assure`, `risk-free`, `sure shot`, `promise`, …) | `validation_failed` → **entire** response discarded |
| 4 | Every `goal_ref` exists in this response | id dropped / rejected |
| 5 | Every `product_id` exists in this response | id dropped / rejected |
| 6 | Any currency-like amount ≥ 1,000 in prose must match a computed figure within 1% | offending **sentence** dropped, rest kept, removals recorded |
| 7 | Timeouts, quota, missing key, blocked response | mapped reason → fallback |

Two different failures get two different responses. A **safety** failure (guarantee language, unknown identifier) rejects the whole answer, because a partially-rewritten model output is indistinguishable from one that never said it. A **grounding** failure (one unverified amount) drops only the offending sentence: the guarantee still holds, and a mostly-correct explanation is not discarded. Every removal is reported in `llm.validation`.

## 4. The final response (`RecommendationResponse`)

Required top-level fields, all present whether or not a model was used:

`financial_summary`, `cash_flow_status`, `protected_buffer`, `available_goal_budget`,
`goal_recommendations`, `investment_options`, `loan_options`, `recommended_plan`,
`alternative_scenarios`, `risks_and_warnings`, `data_sources`, `assumptions`,
`missing_information`, `monthly_actions`, `explanation`, `disclaimer`, plus `llm`, `validation`,
`technical_notes`, `schema_version`, `generated_at`, `run_id`.

Per goal: `goal_ref`, `goal_id`, `name`, `priority`, `target_date`, `target_amount_future`,
`existing_funding`, `funding_gap`, `recommended_monthly_contribution`,
`planned_savings_contribution`, `planned_investment_contribution`, `projected_funding`,
`expected_shortfall`, `funding_status`, `achievement_ratio`, `reason`, `assumptions_used`.

Per investment: source, freshness, `data_quality`, suitability score and rationale, material risks,
commentary, completeness.
Per loan: lender, published rate, `rate_class`, indicative EMI and interest, affordability verdict,
eligibility notes, source, retrieval date.

## 5. Fallback

When no model is available the response is still complete. `llm.status` is `fallback` with a
machine-readable `reason` (`gemini_not_configured`, `missing_api_key`, `timeout`, `quota_exceeded`,
`sdk_unavailable`, `empty_response`), and the prose comes from a deterministic builder that reads
the same computed values. The reader can always tell which produced the text.

## 6. Grounded Q&A

`POST /api/recommendations/ask` answers only from a stored recommendation. The model receives the
computed plan and is instructed to say "not available" when the answer is absent. The deterministic
responder covers buffer, surplus, per-goal status and loan options, and is what runs without a key.

## 7. What the model is forbidden to do

* Invent market data, rates, products or tax rules.
* Override a constraint or contradict the optimiser.
* Describe a projection as guaranteed, assured, safe or risk-free.
* Claim eligibility or approval for any product.
* Execute, recommend executing, or imply execution of a transaction.
* Hide a material risk or an underfunded goal.

## 8. Configuration

| Variable | Purpose |
|---|---|
| `GEMINI_API_KEY` | server-side only; never sent to the client, never logged |
| `GOALPILOT_GEMINI_MODEL` | model name (default `gemini-2.5-flash`) |
| `GOALPILOT_ENABLE_LLM` | `false` forces the deterministic path |
| `GEMINI_TIMEOUT_SECONDS` | request timeout (default 45 s) |

One call per generation, no automatic retry that could double-bill. Structured output requested
with `response_mime_type="application/json"` and validated server-side — the model is not trusted
to police its own shape.
