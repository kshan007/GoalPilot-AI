# Change 1 (LP encoding for `mix`) and Change 2 (explicit investment-overflow policy)

**Date:** 2026-10-11 · **Version:** v5 (v1–v4 untouched)
**New source:** `goalpilot_lp_encoder.py`; additions to `goalpilot_env.py`, `goalpilot_config.py`
**Tests:** `tests/test_goalpilot_lp_encoder.py`, `tests/test_goalpilot_env_overflow_policy.py`
**Experiment:** `audit_tools/54_overflow_and_lp_encoding_comparison.py`
**No PPO training was run, and no reward version was selected.**

---

## 1. Design notes

### 1.1 Change 1 — why an encoder, and what it must not do

The LP optimizer emits **absolute rupees** per goal. The `mix`/`share` action weights are
**scale-free**: only the ratio of the savings-weight sum to the investment-weight sum carries
information, and within each channel only the relative weights matter. Pasting rupees into the
weights therefore destroys exactly the information that separates "allocates 100% of the budget"
from "allocates 60%".

`goalpilot_lp_encoder` converts a plan into (i) an explicit total investment fraction,
(ii) within-savings distribution weights, (iii) within-investment distribution weights, and
(iv) an explicit report of the plan's originally unallocated budget. It never renormalises the
LP's intended amounts away, and the LP optimizer itself is untouched.

### 1.2 A latent bug this exposed in every previous LP figure

`GoalPilotEnv.step` begins with `action = np.clip(action, 0, 1)`. Every earlier LP arm in this
project encoded the plan by assigning **rupee amounts** directly into the action vector, and
those amounts are of order 1e4 — so **every weight was clipped to 1.0**. The result was not the
LP's plan at all: the within-channel distribution silently became *uniform* and the investment
fraction became a *count* ratio rather than a rupee ratio.

The new encoder emits weights in [0, 1] by construction (rescaled so the peak weight is exactly
1.0), so the plan is now expressed faithfully. **All previously published LP fixed-policy figures
were produced with the clipped encoding** and should be read as "LP plan, uniformly weighted"
rather than "LP plan". I have not retro-run the older harnesses; this is flagged, not silently
corrected.

### 1.3 Change 2 — the overflow policy, and why a third sentinel is required

The requested setting has two modes, but **the historical behaviour is mode-dependent**:
`share` returns the excess to the savings channel, `mix` leaves it unallocated. Any concrete
default would therefore silently change one of the two existing mappings. The setting is
consequently:

| Value | Behaviour |
|---|---|
| **`legacy` (default)** | exactly the historical behaviour — mode-dependent, so nothing published changes |
| `retain_as_cash` | the excess stays liquid and is **never** credited to a goal |
| `redirect_to_savings` | the excess is reallocated as **savings** to goals with remaining need, in proportion to that need; whatever no goal can absorb stays as cash |

Redirected money is added to the **savings channel only** (never to investments), is credited
under the savings conventions, and is capped by the per-goal remaining need. Every quantity is
recorded separately on `budget_audit`: `invest_requested`, `invest_actual`, `invest_overflow`,
`overflow_redirected_to_savings`, `overflow_retained_as_cash`.

### 1.4 A second finding: the legacy redirect suppresses investment

The `share` redirect inflates the total the budget guard reconciles, so the guard re-scales
**both** channels — and the investment channel shrinks with it. Measured on `investment-only`
across 16 users: actual investment rises from **386,883** (legacy) to **496,041** (`retain_as_cash`),
a **+28%** increase from simply not redirecting. The historical note that "no budget is lost"
under the redirect is therefore not quite right. Pinned by
`test_retain_as_cash_stops_the_share_mode_redirect`, including the case where capacity is so
small that the guard never binds and the two agree exactly.

---

## 2. Configuration changes

| Item | Change |
|---|---|
| `ACTION_MODE_MIX` | already existed (R-12 work) — unchanged, kept as the reference |
| `INVESTMENT_OVERFLOW_LEGACY` / `_RETAIN_AS_CASH` / `_REDIRECT_TO_SAVINGS` | new constants + `INVESTMENT_OVERFLOW_POLICIES` |
| `investment_overflow_policy` | new field, default `legacy` |
| `GoalPilotConfig.with_investment_overflow(policy)` | new preset; pinned to differ from `recommended()` in exactly one field |
| `_settle_investment_overflow` | new env helper; the single place the policy is applied |
| `budget_audit` | five new fields (§1.3) |

**Nothing else changed.** `archived()`, `corrected_accounting()`, `lp_parity()`, `recommended()`,
`with_reallocation()` and `with_action_mix()` retain `investment_overflow_policy="legacy"`, and
`action_mode` defaults remain `magnitude`. No existing checkpoint or published result is
affected.

---

## 3. Test results

```
tests/test_goalpilot_lp_encoder.py           13 tests
tests/test_goalpilot_env_overflow_policy.py  16 tests
                                             ─────────
                                             29 passed in 6.55s

Full RL suite: 153 passed in 194.31s (0:03:14)   # 124 previous + 29 new
```

Coverage against the required areas:

| Required | Tests |
|---|---|
| LP encode/decode parity | round trip at `A = plan_total` split into **float64 exactness (1e-12)** and the **float32 action bound (1e-6)**; the real LP optimizer's own columns reproduced |
| Zero-savings / zero-investment / zero-total / fully allocated | four dedicated tests plus the partial- and over-budget cases |
| Investment-cap enforcement | `invest_actual <= invest_requested`, capacity ceiling asserted under both modes |
| Both overflow modes | `retain_as_cash` and `redirect_to_savings` behaviour, plus `mix`-legacy ≡ `retain_as_cash` |
| No eligible goals / fully saturated goals | helper with zero need **and** an env run with every goal pre-saturated |
| Budget conservation | identity asserted every month under both modes × 3 policies |
| No double allocation | `redirected + retained == overflow` and `invest_actual <= invest_requested` |
| Deterministic behaviour | byte-identical repeated rollouts |
| Accounting invariants | `net_worth_change == expected`, memo bound `<= cash + portfolio` |
| Affordability | `interest_shortfall == 0` under both modes |
| Unchanged legacy parity | the historical `share` formula reproduced to **0.0 absolute** by an independent computation; archived parity re-verified in §6 |
| Zero-investment controls unchanged | §5.4, bit-identical across all seven arms |

### 3.1 Two corrections the tests forced

1. **The encoder's tolerance had to be stated in two parts.** My first version claimed 1e-9
   end-to-end and failed at 1.9e-8. The cause: the environment's action `Box` is **float32**, so
   a weight that actually reaches the environment cannot reproduce a plan better than ~1e-7
   relative. The encoder now returns `action_float64` (exact, 1e-12) alongside `action` (float32,
   1e-6), so **encoding error and representation error are reported separately** — which is what
   the brief asks for when it asks deviations to be attributed.
2. **The `retain_as_cash` investment assertion was wrong in both directions.** I first asserted
   investment would be unchanged; it is *higher* (the guard mechanism, §1.4). I then asserted
   *strictly* higher; on one user it is exactly equal because capacity is too small for the guard
   to bind. It now asserts "never lower, strictly higher wherever the guard binds, and at least
   one such user must exist" — which is the actual mechanism.

---

## 4. Fixed-policy experiment

Seven arms, 16 fresh test users, one market path, six policies, **`affordability_violations = 0`
in all 42 arm × policy cells**.

Arms: **A** reference (`share` + legacy) · **B** `mix` + legacy · **C** `share` + `retain_as_cash`
· **D** `share` + `redirect_to_savings` · **E** `mix` + `redirect_to_savings` · **D2/E2** the same
with R-13 on.

### 4.1 LP arm, encoded for `mix`

| Arm | achievement | actual investment | savings | overflow | redirected | retained as cash | idle frac | net worth | interest |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A reference (`share`, legacy) | **0.4928** | 287,345 | 981,803 | 1,438,590 | 1,438,590 | 0 | 0.3751 | 2,680,083 | 7,484 |
| B `mix` + legacy | 0.2143 | 327,690 | 0 | 1,425,363 | 0 | 1,425,363 | 0.7623 | 2,722,287 | 11,564 |
| C `share` + retain_as_cash | 0.2143 | 327,690 | 0 | 1,425,363 | 0 | 1,425,363 | 0.7623 | 2,722,287 | 11,564 |
| D `share` + redirect | 0.3353 | 321,054 | 1,414,216 | 1,431,308 | 1,414,607 | 16,701 | 0.2181 | 2,721,977 | 9,664 |
| E `mix` + redirect | 0.3353 | 321,054 | 1,414,216 | 1,431,308 | 1,414,607 | 16,701 | 0.2181 | 2,721,977 | 9,664 |
| D2 `share` + redirect + R-13 | 0.3278 | 455,042 | 1,564,284 | 1,441,696 | 1,427,982 | 13,714 | 0.1307 | 2,767,032 | 6,609 |
| E2 `mix` + redirect + R-13 | 0.3278 | 455,042 | 1,564,284 | 1,441,696 | 1,427,982 | 13,714 | 0.1307 | 2,767,032 | 6,609 |

Observations:

- **B ≡ C exactly** (every column): with `mix`, the legacy behaviour *already is* retention, so
  `retain_as_cash` is a no-op there. Confirmed by the B/C identity across all six policies.
- **D ≡ E exactly**: once the overflow is explicitly redirected, the two action mappings agree
  completely for these policies — the redirect removes the only difference between them.
- **`redirect_to_savings` nearly restores the reference for the LP arm** (0.3353 vs 0.4928) but
  not fully, because the reference distributes the excess by the *savings weights* while the new
  policy distributes it by *remaining need*. Both are defensible; they are different allocations,
  and the difference is now explicit rather than implicit.
- **R-13 lowers achievement slightly here (0.3353 → 0.3278) while cutting idle budget from 0.218
  to 0.131.** Reallocating released budget is not automatically better for goal attainment.
- **Retention increases investment** (287,345 → 327,690 for the LP; 386,883 → 496,041 for
  `investment-only`) via the guard mechanism of §1.4, and increases net worth — while reducing
  goal funding. A genuine trade-off: more wealth, fewer credited goals.

### 4.2 The zero-investment controls are **bit-identical across all seven arms**

| Policy | overflow in every arm | achievement in every arm |
|---|---:|---:|
| `uniform savings` | **0** | **0.5584482398057189** |
| `need-proportional savings` | **0** | **0.3210604791957656** |
| `urgency` | **0** | **0.40510963403969824** |

These policies never request investment, so no policy can ever apply to them, and the outcomes
are identical to the last digit in all seven arms. This is the requested confirmation, and it is
also the strongest evidence that the change touches only the overflow mechanism. (Note
`uniform savings` rises to 0.5951 in the two R-13 arms — that is the **R-13** effect, not the
overflow policy, and it appears only where R-13 is enabled.)

### 4.3 `investment-only` and `mixed allocation` for reference

| Arm | investment-only | mixed allocation | actual investment (inv-only) | retained as cash (inv-only) |
|---|---:|---:|---:|---:|
| A reference | 0.5800 | 0.5800 | 386,883 | 0 |
| B `mix` + legacy | 0.3761 | 0.5281 | 496,041 | 1,479,048 |
| C `share` + retain | 0.3761 | 0.5281 | 496,041 | 1,479,048 |
| D `share` + redirect | 0.5469 | 0.5822 | 482,704 | 25,973 |
| E `mix` + redirect | 0.5469 | 0.5822 | 482,704 | 25,973 |
| D2 + R-13 | 0.5327 | **0.5941** | 554,618 | 15,561 |
| E2 + R-13 | 0.5327 | **0.5941** | 554,618 | 15,561 |

`investment-only` and `mixed allocation` are **identical under A** (the R-12 degeneracy) and
**distinct under every other arm** — the R-12 fix and the overflow policy together make the mix
observable, as intended.

---

## 5. Interpretation — what these numbers do and do not say

- **They do not show that any option improves policy performance.** `redirect_to_savings` raises
  measured achievement relative to retention *for the same set of actions*, but that is the
  definition of the accounting option; it is not evidence that a learned policy would do better.
  Fixed policies cannot show policy-level improvement, and the brief says so.
- **`retain_as_cash` is the stricter, more honest accounting**: money that cannot be invested is
  not counted as goal funding. It lowers goal achievement and raises measured wealth and actual
  investment.
- **No choice is made here.** All three policies remain available; `legacy` remains the default
  and reproduces every published number.
- **No reward version is selected, and PPO was not trained.**

---

## 6. Limitations

1. **Archived parity is verified intact.** After both changes the full RL suite reported
   **153 passed in 194.31s** (124 previous + 29 new), with `test_goalpilot_env_parity.py`
   (100 users x 5 policies x 142 months, reward to 1e-12) among them; the LP suite remains
   26 passed. Console: `outputs/reward_design/v5/pytest_full_after_change1_change2.txt`.
   Test inventory: **153 RL + 26 LP = 179 tests, 0 failures, 0 errors, 0 skips.** The default
   `legacy` path and every existing preset are unchanged by construction and pinned by test.
2. **The LP arm's encoded result (0.4928) differs from the earlier naive-encoding figure (0.4955)
   by 0.0027.** I attribute this to the float32 action representation and the encoder's peak
   normalisation, but §1.2 also means the two are *not* the same encoding at all (the earlier one
   was clipped to uniform weights), so the two numbers are not directly comparable. I have **not**
   fully attributed the difference and am not claiming a cause.
3. **Previously published LP fixed-policy figures used the clipped encoding** (§1.2) and should be
   re-run before being quoted alongside these.
4. **`redirect_to_savings` vs the legacy `share` redirect distribute differently** (remaining need
   vs savings weights). Both are documented; neither is asserted to be superior.
5. **R-13's interaction is unchanged**: it reallocates `released_by_goal_cap` only, so the
   investment-cap overflow is retained even when R-13 is on (visible as the small non-zero
   `retained as cash` in D2/E2). Whether R-13 should also absorb it remains an open question.
6. **Fixed policies only.** Nothing here is evidence about a trained policy, and no checkpoint is
   compatible with `mix` (§8 of `R12_ACTION_SPACE_DESIGN.md`).

---

## 7. Reproducing

```powershell
$py = "C:\Users\sudha\AppData\Local\Programs\Python\Python313\python.exe"
Set-Location S:\fyp\GoalPilot_AI_Completed

& $py -m pytest tests\test_goalpilot_lp_encoder.py tests\test_goalpilot_env_overflow_policy.py -q
& $py audit_tools\54_overflow_and_lp_encoding_comparison.py     # the §4 tables
& $py -m pytest -q                                              # full suite, archived parity
```
