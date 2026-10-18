# Corrected LP comparison — with `goalpilot_lp_encoder`

**Date:** 2026-10-11 · **Version:** v6 (v1–v5 untouched)
**Script:** `audit_tools/55_corrected_lp_comparison.py`
**Data:** `outputs/evaluation/final_validation_v6/`
**No PPO training. No reward change. No reward version selected. No previous output modified.**

---

## 1. Inventory of the clipped LP arms

Every LP arm that passed **absolute rupee** allocations into the `Box[0, 1]` action interface,
found by inspecting the v1–v4 harnesses:

| File | Lines | Version | Status |
|---|---|---|---|
| `evaluation/final_validation_evaluation.py` | 122–123 build, **154–156 use** | v1 (Phases D/E/H) | **clipped** |
| `evaluation/fair_comparison_harness_v2.py` | 102, **125–126** | v2 | **clipped** |
| `audit_tools/50_strategy_space_diagnosis.py` | 139, **97–98** | v2 (P1 diagnosis) | **clipped** |
| `audit_tools/51_reallocation_impact.py` | 78, **100–101** | v3 (R-13 impact) | **clipped** |
| `audit_tools/52_fair_baselines.py` | 98, **127–128** | v3 (P4 baselines) | **clipped** |
| `audit_tools/53_action_mapping_comparison.py` | 74, **103–104** | v4 | **clipped** |
| `audit_tools/54_overflow_and_lp_encoding_comparison.py` | 105 | v5 | ✅ already encoded |

The mechanism: `GoalPilotEnv.step` starts with `action = np.clip(action, 0, 1)` and the LP's
amounts are of order 1e4, so **every weight clipped to exactly 1.0** — the plan became uniformly
weighted and its investment fraction became a *count* ratio. These files are **left untouched**;
they are the historical record.

---

## 2. Encode/decode parity, validated before any capacity constraint

For all 16 fresh test users the encoder's output was decoded back to rupees at
`available_budget = plan_total`, **before** investment-cap constraints:

| Quantity | Result |
|---|---|
| Plans decoded | **16 / 16** |
| Worst relative encode/decode error | **0.0 (exactly zero)** |
| All within the documented 1e-9 tolerance | **true** |

Data: `lp_encoded_parity_v1.csv`. The capacity deviation is a *separate* quantity, reported in
§4 as `investment_cap_overflow` — never conflated with encoding error.

---

## 3. The 0.4928 vs 0.4955 difference — **cause established**

Rather than assume float32 rounding, the encoding was decomposed into its candidate causes by
running four variants on the same users under the same configuration
(`lp_encoding_attribution_v1.csv`):

| Encoding variant | goal achievement | idle fraction | cap overflow |
|---|---:|---:|---:|
| `historical_rupees_clipped` (what v1–v4 did) | **0.4954770198717099** | 0.37134663420807235 | 1,438,794.4878923388 |
| `uniformised_ones` (any positive amount → 1.0) | **0.4954770198717099** | 0.37134663420807235 | 1,438,794.4878923388 |
| `encoder` (faithful, rupee-proportional) | **0.492784548939265** | 0.3751029742810681 | 1,438,590.1672445145 |
| `encoder_scaled_1000` (encoder × 1000, then clipped) | **0.4954770198717099** | 0.37134663420807235 | 1,438,794.4878923388 |

**Conclusions, each from an identity rather than an inference:**

1. **`historical_rupees_clipped` ≡ `uniformised_ones` exactly**, to all printed digits, on all
   four columns. The clipping distortion **is** uniformisation — nothing else.
2. **`encoder_scaled_1000` ≡ `historical_rupees_clipped` exactly.** Constant rescaling does not
   change the outcome, so **neither float32 precision nor the encoder's peak normalisation can be
   the cause** — they are ruled out by an identity, not by argument. (Note `encoder × 1000`
   clips back to ones, which is why it lands on the same figure.)
3. The remaining −0.0027 is the difference between a **uniformly weighted** plan and the LP's
   **rupee-proportional** plan: the old figure scored a plan the LP never proposed.

**So the old 0.4955 is not a precision artefact.** It is the achievement of the uniformised plan.
The corrected value for the LP's actual plan is **0.4928**.

**A nuance worth keeping:** `pct_goals_fully_funded` (0.377083) and `pct_goals_met_by_deadline`
(0.168750) are **identical** under both encodings. The clipping changed the *depth* of funding and
the shortfall (8,689,991 → 8,713,979), not which goals completed. So the historical LP
*ranking* statements are only mildly affected, while the LP's *levels* were the uniformised plan's.

---

## 4. Corrected comparison — 16 fresh test users, `share` + `legacy`

All arms on one configuration, one market path, one set of goal definitions. **0 affordability
violations in every arm.** `investment_cap_overflow` is the LP's plan exceeding capacity — the
capacity deviation, reported separately from encoding error.

| Policy | achievement | fully funded | by deadline | shortfall | cash | portfolio | net worth | debt | interest | cap overflow | idle |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| RL `archived_v1` seed7 | **0.5908** | 0.4813 | 0.1146 | 8,589,238 | 1,871,494 | 887,609 | 2,748,925 | 10,178 | 8,716 | 388,382 | 0.2308 |
| `investment-only` | 0.5800 | 0.4656 | 0.1427 | 8,567,394 | 1,857,177 | 894,600 | 2,751,777 | 0 | 0 | 1,479,048 | 0.2459 |
| `mixed allocation` | 0.5800 | 0.4656 | 0.1427 | 8,567,394 | 1,857,177 | 894,600 | 2,751,777 | 0 | 0 | 439,156 | 0.2459 |
| RL `candidate_a` seed27 | 0.5586 | 0.3771 | 0.1479 | 8,564,773 | 1,891,464 | 830,966 | 2,709,946 | 12,484 | 7,224 | 1,435,191 | 0.2297 |
| `uniform savings` | 0.5584 | 0.4531 | 0.1427 | 8,783,226 | 2,244,060 | 119,829 | 2,363,890 | 0 | 0 | 0 | 0.2289 |
| RL `candidate_a` seed17 | 0.5299 | 0.4073 | 0.0938 | 9,046,328 | 1,928,989 | 761,789 | 2,653,332 | 37,446 | 39,269 | 288,491 | 0.4804 |
| RL `archived_v1` seed17 | 0.5265 | 0.4198 | 0.1198 | 8,871,280 | 1,971,740 | 715,290 | 2,677,197 | 9,834 | 16,541 | 895,567 | 0.3886 |
| **LP (`historical`, clipped)** | 0.4955 | 0.3771 | **0.1687** | 8,689,991 | 1,942,006 | 752,247 | 2,688,699 | 5,554 | 7,424 | 1,438,794 | 0.3713 |
| **LP (encoder, corrected)** | **0.4928** | 0.3771 | **0.1687** | 8,713,979 | 1,954,785 | 730,851 | 2,680,083 | 5,554 | 7,484 | 1,438,590 | 0.3751 |
| RL `candidate_a` seed7 | 0.4895 | 0.3792 | 0.1510 | 8,925,404 | 1,999,508 | 681,776 | 2,669,111 | 12,173 | 15,711 | 524,127 | 0.3875 |
| RL `archived_v1` seed27 | 0.4399 | 0.3177 | 0.1115 | 8,836,320 | 1,966,226 | 712,691 | 2,661,715 | 17,201 | 19,860 | 1,217,413 | 0.2677 |
| `urgency` | 0.4051 | 0.0625 | **0.0000** | 8,125,197 | 2,244,060 | 119,829 | 2,363,890 | 0 | 0 | 0 | 0.0088 |
| `need-proportional savings` | 0.3211 | 0.0625 | **0.0000** | 8,125,197 | 2,244,060 | 119,829 | 2,363,890 | 0 | 0 | 0 | 0.0088 |

**The LP has the best deadline success of any arm (0.1687)** — above `investment-only` (0.1427)
and above every RL seed — while ranking lower on the level of funding. That is a real, defensible
strength of the LP plan and it was already true before the correction.

**The single most important comparability finding:** the LP's plan requests **1.44 M of investment
that the environment's capacity limit cannot accept**. Under `share`+`legacy` that demand is
silently relabelled as savings, which is *why* the LP scores well at all. The LP and the
environment disagree structurally about how much investing is possible; no encoding choice can fix
that, and any LP-vs-RL comparison must state it. `investment-only` shows the same pattern
(1.48 M of cap overflow).

### 4.1 RL compatibility (step 4)

The six fresh-split checkpoints were trained under `share` + `legacy` and are evaluated **only**
under `recommended()`, i.e. exactly their training semantics. The script asserts
`action_mode == share` **and** `investment_overflow_policy == legacy` before loading any
checkpoint, so an old policy can never be silently reinterpreted under `mix`. No checkpoint was
evaluated under `mix`, and none would be compatible with it.

---

## 5. Overflow policies evaluated separately (step 8)

LP arm, corrected encoder, 16 fresh users. `legacy` remains the **default** and is unchanged.

| Arm | achievement | fully funded | by deadline | net worth | interest | overflow | retained as cash | idle |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `share` + **legacy** (default) | **0.4928** | 0.3771 | 0.1687 | 2,680,083 | 7,484 | 1,438,590 | 0 | 0.3751 |
| `share` + `retain_as_cash` | 0.2143 | 0.1917 | 0.1115 | 2,722,287 | 11,564 | 1,425,363 | 1,425,363 | 0.7623 |
| `share` + `redirect_to_savings` | 0.3353 | 0.2125 | 0.0990 | 2,721,977 | 9,664 | 1,431,308 | 16,701 | 0.2181 |
| `mix` + legacy | 0.2143 | 0.1917 | 0.1115 | 2,722,287 | 11,564 | 1,425,363 | 1,425,363 | 0.7623 |
| `mix` + `retain_as_cash` | 0.2143 | 0.1917 | 0.1115 | 2,722,287 | 11,564 | 1,425,363 | 1,425,363 | 0.7623 |
| `mix` + `redirect_to_savings` | 0.3353 | 0.2125 | 0.0990 | 2,721,977 | 9,664 | 1,431,308 | 16,701 | 0.2181 |

Two clean results:

1. **Each explicit policy is completely mode-independent**: `share`+`retain` ≡ `mix`+`retain` and
   `share`+`redirect` ≡ `mix`+`redirect`, every column. Once the overflow policy is stated
   explicitly, the action mode no longer matters for this arm.
2. **`legacy` is the best of the three for LP goal achievement (0.4928 > 0.3353 > 0.2143)** — the
   opposite of what a "more explicit is better" reading would suggest. The reason is distribution:
   the legacy redirect spreads the excess by the LP's **own savings weights**, whereas
   `redirect_to_savings` spreads it by **remaining need**, reaching goals the LP did not select.

**Neither explicit policy is declared better.** `retain_as_cash` is the stricter accounting
(wealth 2.72 M, goal funding 0.2143); `redirect_to_savings` funds more goals (0.3353) with a
slightly worse deadline rate; `legacy` funds the most (0.4928) while hiding where the money went.
That is a trade-off between *result* and *auditability*, and it is a judgement for the project, not
a fact these numbers settle.

---

## 6. Mapping of historical claims

| # | Historical claim (as published) | Verdict |
|---|---|---|
| 1 | v4: "LP plan scores 0.4955 under `share`" | **Corrected** → **0.4928** with the faithful encoder. §3 shows 0.4955 was the *uniformised* plan |
| 2 | v4: "LP plan collapses to 0.2215 under `mix`" | **Corrected** → **0.2143** (same clipped encoding; same qualitative collapse) |
| 3 | v5: "LP 0.4928 (share), 0.2143 (mix-legacy), 0.3353 (redirect)" | **Unchanged** — already used the encoder |
| 4 | v5: "the legacy `share` redirect suppresses investment via the guard" | **Unchanged** — mechanism and the +28% figure are independent of the LP encoding |
| 5 | v3 P4: "LP plan 0.5663 on the fresh cohort" | **Corrected** → 0.4928. The old figure used the clipped encoding |
| 6 | v2 P1: "LP 0.6113; ceiling ≈ 0.6350" (old 20-user cohort) | **No longer comparable** — different cohort *and* clipped encoding. Do not quote against v6 numbers |
| 7 | v2 fair harness: "LP 0.4279; `Investments only` 0.4313 > LP" | **No longer comparable** — old cohort. On the fresh cohort the ordering is `investment-only` 0.5800 > LP 0.4928, which *agrees in direction* but on different users |
| 8 | v2: "no RL policy beats `Investments only` or the LP" | **Corrected** — on the fresh cohort, RL `archived_v1` seed7 (0.5908) beats both `investment-only` (0.5800) and the LP (0.4928). The earlier negative result did not generalise |
| 9 | v2/v4: "`Investments only` ≡ `Mixed` byte-identically (R-12)" | **Unchanged** — reconfirmed here (both 0.5800, every column identical) |
| 10 | v3/v4: "the two bad baselines never invest and score 0.0000 deadline success" | **Unchanged** — `urgency` and `need-proportional savings` both 0.0000 |
| 11 | v1: "LP funding vs inflated targets is −0.0673 below savings-only under `lp_parity`, +0.0398 under `recommended`" | **No longer comparable** — old cohort, `magnitude`/clipped basis, and the paired CIs were computed with the superseded pseudo-replication method |
| 12 | v1–v4: "the LP plan can be truncated by the environment's own caps" (stated as a caveat) | **Corrected in magnitude** — the caveat was right but understated: the LP over-requests investment by **1.44 M per cohort**, not a marginal truncation |

---

## 7. Unavoidable differences (step 3)

Matched across all arms in §4: identical users (the 16 fresh test users), identical goal
definitions and targets, identical market path, identical accounting, identical credit mode
(`market_weighted`), identical reserve policy, one configuration (`recommended()` = `share` +
`legacy`).

Unavoidable, and stated rather than hidden:

1. **The LP is deterministic and one-shot**; it plans once against its own budget assumption and
   its plan is replayed monthly, while the environment's available budget varies month to month.
   The RL arms and the rules act every month on the observed state.
2. **The LP's loan assumption differs**: a fixed 12% annual rate and a 60-month tenure, whereas
   the environment uses the monthly `walr_monthly` path and its own `max_new_loan` cap.
3. **The LP plans investment far beyond the users' capacity** (§4) — 1.44 M of unavoidable
   overflow, which the environment then treats differently depending on the overflow policy. This
   is the single largest source of incomparability between the LP and every other arm.
4. **The rule-based baselines are mine**, not from the literature, and two of them
   (`urgency`, `need-proportional savings`) are demonstrably poor designs.
5. **The RL arms are stochastic policies trained on a different partition** (the fresh *train*
   users); they are evaluated deterministically on the fresh test users.

---

## 8. Limitations

1. **16 users.** CIs of roughly ±0.09 mean the arms in §4 are largely indistinguishable; the
   ordering is reported for completeness, not as a ranking.
2. **The corrected LP values are only 0.0027 below the historical ones.** The correction matters
   much more for *what the number means* than for its size — but the *magnitude* of the LP's
   capacity over-request (1.44 M) is the material finding.
3. **Fixed policies only, and one budget.** Nothing here is evidence about a trained policy.
4. **The LP's own assumptions were not changed** and its optimizer is untouched.
5. **`retain_as_cash` and `redirect_to_savings` are evaluated, not adopted.** `legacy` remains the
   default.

---

## 9. Reproducing

```powershell
$py = "C:\Users\sudha\AppData\Local\Programs\Python\Python313\python.exe"
Set-Location S:\fyp\GoalPilot_AI_Completed

& $py -m pytest tests\test_goalpilot_lp_encoder.py tests\test_goalpilot_env_overflow_policy.py `
        tests\test_goalpilot_env_parity.py -q      # encoder, overflow, archived parity
& $py audit_tools\55_corrected_lp_comparison.py     # sections 2-5
```

Executed result of the first command:

```
32 passed in 124.72s (0:02:04)
```

= 13 LP-encoder tests + 16 overflow-policy tests + 3 archived-parity tests. **Archived parity
is intact**, so the encoder and the overflow policy are confirmed not to have altered any
archived behaviour. Console: `outputs/reward_design/v6/pytest_corrected_lp_phase.txt`. The full
suite stood at **153 passed** with these sources unchanged (`pytest_full_after_change1_change2.txt`).
