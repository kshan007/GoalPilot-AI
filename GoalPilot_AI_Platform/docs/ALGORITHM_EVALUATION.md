# Algorithm Evaluation

Evidence produced by `scripts/evaluate_algorithms.py` on 2026-10-17. Raw output:
`outputs/algorithm_evaluation.json`.

No model was trained or modified. All four arms loaded their existing artefacts and ran through
the real comparison service (`POST /api/optimize/compare`) on identical inputs per household.

---

## 1. Method

Five synthetic households spanning the cases that actually discriminate between algorithms:

| Case | Income | Essential | Disc. | EMI | Requested buffer | Goals |
|---|---|---|---|---|---|---|
| `deficit_household` | 45,000 | 38,000 | 9,000 | 4,000 | 2,000 | 1 |
| `thin_surplus_three_goals` | 70,000 | 42,000 | 8,000 | 0 | 8,000 | 3 |
| `comfortable_surplus_four_goals` | 250,000 | 70,000 | 25,000 | 12,000 | 30,000 | 4 |
| `mandatory_buffer_above_capacity` | 80,000 | 40,000 | 10,000 | 6,000 | 30,000 (mandatory) | 2 |
| `single_urgent_goal` | 120,000 | 45,000 | 10,000 | 0 | 15,000 | 1 |

All monetary figures are INR per month. Every arm received the same goals, target dates,
priorities, starting resources, economic assumptions and planning horizon. Arms: `lp`,
`rl`, `hybrid`, `rule_baseline`.

Metrics are the ones the comparison service computes: weighted goal achievement, total and
weighted shortfall, weighted deadline achievement, feasibility, runtime. They are **not**
recomputed by this script, so the document reports the application's own numbers.

---

## 2. Results

`achievement / shortfall` per case:

| Case | Goal budget | Buffer sustained | Selected | LP | RL | Hybrid | Rule |
|---|---|---|---|---|---|---|---|
| deficit_household | 0 | no | lp | 0.000 / 156,415 | 0.000 / 156,415 | 0.000 / 156,415 | 0.000 / 156,415 |
| thin_surplus_three_goals | 12,000 | yes | **rule_baseline** | 0.276 / 1,969,886 | 0.585 / 1,420,370 | 0.276 / 1,969,886 | **0.747 / 864,863** |
| comfortable_surplus_four_goals | 113,000 | yes | **rule_baseline** | 0.892 / 1,261,440 | 0.800 / 2,308,164 | 0.892 / 1,261,440 | **1.000 / 0** |
| mandatory_buffer_above_capacity | 0 | no | lp | 0.000 / 1,153,549 | 0.000 / 1,153,549 | 0.000 / 1,153,549 | 0.000 / 1,153,549 |
| single_urgent_goal | 50,000 | yes | lp | 1.000 / 0 | 1.000 / 0 | 1.000 / 0 | 1.000 / 0 |

Aggregate across the five cases:

| Arm | Mean weighted achievement | Mean total shortfall | Mean deadline achievement | Mean runtime |
|---|---|---|---|---|
| rule_baseline | **0.5494** | **434,965** | **0.3452** | 0 ms |
| rl | 0.4770 | 1,007,700 | 0.3024 | 2,189 ms |
| lp | 0.4337 | 908,258 | 0.3248 | 126 ms |
| hybrid | 0.4337 | 908,258 | 0.3251 | 311 ms |

Selector choices across the sweep: **LP 3, rule_baseline 2**.

---

## 3. What this actually shows

**3.1 The rule baseline currently beats the LP on this metric.** This contradicts the earlier
in-house narrative that the LP is the strongest arm. On a per-goal weighted-achievement metric,
greedy priority-ordered allocation outperforms the LP on two of the three funded cases, and ties
it on the third.

The likely cause is a metric/objective mismatch rather than a solver defect. The LP's objective
spreads the budget to maximise a weighted, discounted objective across goals; achievement is
measured per goal and averaged, which rewards *concentrating* money until individual goals are
completed. On a thin surplus the LP therefore spreads, and no single goal completes. Both
behaviours are defensible; they optimise different things. The honest conclusion is that the LP
objective and the evaluation metric are not aligned, and one of them must change before either
can be called "best".

**3.2 The hybrid is informationally real but numerically inert here.** Hybrid and LP produce
identical achievement to four decimal places; the shortfall differs by 0.03 rupees. The RL's
proposed split does reach the LP — the integration test asserts that the parameters change — but
the binding constraint in all five cases is the monthly budget, not the investment cap the RL
adjusts. So "the hybrid materially affects the solution" is **false for this sweep**, and saying
otherwise would be exactly the kind of claim the brief forbids.

**3.3 RL alone is not a candidate for promotion.** It gains slightly on mean achievement
(0.477 vs 0.434) while nearly doubling total shortfall and *lowering* deadline achievement, at
roughly 17× the LP's runtime. Higher achievement with worse shortfall is internally consistent
(the two metrics weight goals differently) but it is not evidence of a better planner.

**3.4 Degenerate cases behave correctly.** When the goal budget is zero the arms agree at zero
achievement and identical shortfall, and the buffer is flagged `sustained = false`. No arm
invents capacity. That is the correct outcome, not a failure.

---

## 4. Selection policy

The selector scores available arms per user and picks by weighted achievement, then deadline
achievement, then speed. It is not hard-coded to LP, which is why it returned `rule_baseline`
twice here.

**Resolution (2026-10-17).** The selector is LP-anchored: an arm replaces the LP only by beating it
on weighted achievement by a fixed margin while giving up no more than a fixed tolerance of deadline
success. The rule baseline's two wins are therefore not an artefact of ranking — on those cases it
cleared both gates. The LP objective is left unchanged (it is research code, imported read-only), and
the tension is **disclosed rather than hidden**: both metrics are reported here, and
`/optimize/compare` returns every arm's metrics plus a reason for each arm that was not selected.
Re-weighting the objective remains a research decision, with this document as its evidence base.

This does **not** justify promoting RL or the hybrid, because neither beat the baseline on the same
inputs. It does mean the top model task is aligning the objective with what the product rewards, not
training a better policy.

## 5. Limitations of this evaluation

* Five households is a smoke-level sweep, not a statistical benchmark. No confidence intervals
  are claimed.
* Scenarios are static one-shot allocations, not month-by-month adaptation under shocks. The
  adaptive path is covered functionally (see `FINAL_VALIDATION_STATUS.md`) but not scored here.
* The PPO checkpoint predates the protected-buffer change to the environment, so RL and hybrid
  numbers reflect a policy trained on a slightly different input definition.
* Synthetic households exercise the code paths; they say nothing about real Indian households.
* Stability across seeds was not measured; the sweep is single-seed.
