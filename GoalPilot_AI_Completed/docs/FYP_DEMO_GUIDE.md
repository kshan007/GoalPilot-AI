# FYP Demonstration Guide — GoalPilot AI

A scripted walk-through for a final-year project review. Ten minutes of command and
discussion, plus a longer 25-minute version with the audit deep-dive.

**Prerequisite:** the environment from `README.md` §2. Use the full interpreter path.

```powershell
$py = "C:\Users\sudha\AppData\Local\Programs\Python\Python313\python.exe"
Set-Location S:\fyp\GoalPilot_AI_Completed
```

---

## Opening framing (30 seconds, no command)

> GoalPilot AI plans multiple financial goals at once — a vehicle in 17 months, a
> retirement corpus in 123 months — from a household's real cash flow. It has two
> decision engines: a **linear-programming optimizer** that solves the whole plan
> statically, and a **reinforcement-learning agent** that makes the decision month by
> month. This project's contribution is the audit that established whether the two engines
> can be compared at all — and they could not, until now.Three defects made the comparison
> meaningless, and all three are fixed and tested.

---

## Act 1 · Inventory and provenance (1 min)

```powershell
& $py audit_tools\02_inventory.py
```

**Say:** 552 files, 4.8 GB in the workspace. The duplicate report shows 3.1 GB is redundant —
the same 959 MB simulation CSV exists three times, because the archive was downloaded three
times over. `GoalPilot_AI/` is the complete project; `GoalPilot_AI_old/` is superseded.

## Act 2 · Which notebook is authoritative? (1 min)

```powershell
& $py audit_tools\01_notebook_compare.py
```

**Say:** the standalone `GoalPilot_RL_PreCheck.ipynb` and the copy inside the project folder
are **byte-identical** — same 144 cells, same 271,463 source characters, same outputs. There
is no version conflict, so nothing needed overwriting. The `identical_source = True` line is
the answer.

That notebook is not a clean analysis — it is a *patcher*. Cells 0–88 rewrite
`goalpilot_env.py` in place; that is where the nine `.bak` files came from.

## Act 3 · The headline defect, measured (2 min)

```powershell
& $py audit_tools\10_diag_env.py
```

**Point at these two blocks:**

```
=== H1: Savings-only vs Mixed allocation goal funding ===
users where |mixed - savings| <= 1e-12 : 100 / 100
max abs difference                       : 1.665e-16
median |portfolio difference|            : 237,955.72
```

**Say:** the savings-only and mixed-allocation baselines produce *mathematically identical*
goal funding — for every one of 100 users, to 16 decimal places. Yet their portfolios differ
by ₹238,000. So the mix changes wealth but cannot change goal funding. That is not a policy
result; it is a property of the environment, and it means an entire column of the original
comparison table carried zero information.

Then:

```
=== H2: savings action magnitude vs goal funding ===
Flat 0.25 savings   mean_funded = 1,150,004.96   unallocated = 847,540
Flat 0.50 savings   mean_funded = 1,220,790.18
Flat 0.75 savings   mean_funded = 1,220,790.18
Savings only        mean_funded = 1,220,790.18
```

**Say:** 0.25, 0.50, 0.75 and 1.00 are **indistinguishable** above 0.5. The action is a
magnitude, and the budget normaliser can only scale *down*. So the reward has no gradient
above the saturation point — and below it, a policy silently underfunds. The hand-coded
baselines emit exactly 1.0 and therefore always capture the full budget; a Gaussian policy
cannot learn to.

## Act 4 · The balance-sheet defect (1.5 min)

```powershell
& $py evaluation\policy_evaluation.py --project-root . --config archived --split test --include-ppo --tag demo_archived
```

Open `outputs/evaluation/policy_summary_demo_archived.csv` and compare
`mean_net_worth_ledger` with `mean_net_worth_archived_aggregate`.

**Say:** for savings-only the honest net worth is ₹1,302,720; the aggregate the archive
reported is ₹2,447,267 — nearly double. The reason is that contributions accumulated in
`cash` **and** in `goal_balances`, and investments were counted in `portfolio` **and** in
`goal_balances`. Loans made it worse: proceeds credited a goal but never reached an account,
and EMI payments never left one. So borrowing reduced reported net worth by the full
outstanding principal with no offsetting asset.

**Show the fix:**

```
max net-worth change attributable to borrowing alone: 0.00
```

That is the ledger being correct: taking a loan is asset-up, liability-up — net zero.

## Act 5 · What actually drives the reward (2 min)

```powershell
& $py evaluation\reward_decomposition.py --project-root . --config archived --split test --include-ppo --tag demo
```

Read `outputs/evaluation/reward_decomposition_summary_demo.csv`:

| policy | total reward | progress | deadline shortfall | loan | risk |
|---|---:|---:|---:|---:|---:|
| Savings only | −171.56 | **+44.48** | −188.66 | 0 | −27.38 |
| Investments only | −422.96 | +41.13 | −193.65 | 0 | **−270.44** |
| PPO | −236.22 | **+29.99** | −200.78 | **−15.94** | −49.50 |

**Say three things:**

1. The best policy earns **+44 reward for goal progress** against **−189 of deadline
   penalties**. The positive signal is a rounding error next to the penalties.
2. Investing multiplies the risk penalty **tenfold** (−270 vs −27) and there is *no reward
   for terminal portfolio value*. The reward therefore teaches the agent not to invest.
3. PPO earns the **least** progress reward of any policy — it genuinely underfunds — and pays
   the largest loan penalty. So PPO's weakness is real but the comparison that produced it
   was not fair.

**State clearly:** the reward function was **not changed**. Diagnostics came first, as
required.

## Act 6 · Was the borrowing useful? (1.5 min)

```powershell
& $py evaluation\borrowing_audit.py --project-root . --config corrected_accounting --split test --tag demo
```

Read `outputs/evaluation/borrowing_audit_summary_demo.csv`:

- 11 of 20 held-out users borrow; total principal ₹1,183,966; total interest ₹256,912
- **5 users: borrowing helps funding. 5 users: it hurts. 1 neutral.**
- median cost: **₹0.29 of interest per extra rupee of goal funding**
- mean net worth effect: **−₹12,719** — the interest, and nothing else

**Say:** borrowing is not irrational; it is a genuine trade-off, and now it is priced
correctly instead of looking free in the reward and catastrophic in the accounts.

## Act 7 · Proof nothing broke (1.5 min)

```powershell
& $py evaluation\verify_against_archive.py --project-root .
```

```
[PASS] rl_baseline_policy_comparison.csv        : 4800 field-comparisons, 0 mismatch
[PASS] rl_policy_diagnostic_summary.csv         :   16 field-comparisons, 0 mismatch
[PASS] rl_heldout_policy_comparison_detail.csv  :  700 field-comparisons, 0 mismatch
[PASS] rl_heldout_policy_comparison_summary.csv :   25 field-comparisons, 0 mismatch
OVERALL: PASS
```

**Say:** the environment was rewritten. Every archived number still reproduces exactly —
5,541 field comparisons, zero mismatches. The old behaviour is one config flag away
(`GoalPilotConfig.archived()`), so the archive stays reproducible while the default is fixed.

## 8 · Tests (1 min)

```powershell
& $py -m pytest -q
```

**Say:** 64 new tests where the RL environment previously had **zero**. They include a
100-user × 5-policy × 142-month parity test, budget and net-worth identities checked every
month, the degeneracy pinned on the record, and the fixes pinned as behaviour.

```powershell
Set-Location GoalPilot_MultiGoal_Extension; & $py -m pytest -q; Set-Location ..
```

26 more tests, unchanged — the LP optimizer was preserved.

---

## Extended version (25 minutes) — the audit deep-dive

### E1 · Show the evidence trail

`docs/audit/AUDIT_REPORT.md` — open §4 and walk F-01 → F-06. Each finding names the file and
line, or the CSV and column, that proves it.

### E2 · Show the two "Mixed allocation" definitions

`docs/audit/AUDIT_REPORT.md` §F-01 and `evaluation/verify_against_archive.py` lines 45–56.

**Say:** the archive's own 100-user tables used a 0.25/0.25 mixed policy while its held-out
tables used 0.50/0.50. Under magnitude semantics those are different policies. A comparison
that conflates them is wrong — which is exactly why the verifier keeps two alias maps.

### E3 · Show the LP/RL target mismatch

```powershell
& $py -m pytest tests/test_lp_rl_target_parity.py -q
```

**Say:** the LP inflated goal targets by 3 % per year; the RL environment used nominal costs —
up to an 80 % gap on a 240-month goal — and the two were tabulated side by side. `lp_parity()`
now puts both on one basis, and the test asserts they agree.

### E4 · Show the degeneracy proof

```powershell
& $py -m pytest tests/test_goalpilot_env_modes.py -q -k degeneracy
```

Two tests: one asserts the degeneracy still exists under face-value crediting (so it can
never regress silently), the other asserts it is **broken** once contributions compound at
their own rates.

### E5 · Show what the action-mode fix buys

```powershell
& $py -m pytest tests/test_goalpilot_env_modes.py -q -k "share_mode or plateau"
```

In share mode, actions 0.25 / 0.50 / 0.75 / 1.00 produce identical funding — the handicap is
gone.

### E6 · Show the cost of legacy accounting on borrowing

```powershell
& $py evaluation\borrowing_audit.py --project-root . --config archived --split test --tag demo_legacy
```

Legacy reports a mean net-worth cost of **−₹65,949** against the true **−₹12,719** — a 5.2×
overstatement, entirely because proceeds never entered an account.

### E7 · Colab readiness

Open `GoalPilot_RL_PreCheck_portable.ipynb`. Show the bootstrap cell. **Say:** the archived
notebook had `/content/drive/MyDrive/...` in ~40 places and would only run in Colab; 114
cells are now path-resolved, and the 14 cells that rewrote the environment in place are
disabled with their source preserved, because running them today would destroy the fix.

---

## Anticipated questions

**"Why didn't you just retrain PPO?"**
Because the audit showed the comparison was structurally unfair *and* the reward was
mis-specified. Training on that reward would have tuned the agent to avoid investing. The
instruction was diagnostics before any reward change, and that is what was delivered.

**"Is the LP wrong too?"**
No. The LP already excluded earmarked funding from the cash pool and already separated
savings from investment valuation. F-06 was about the *basis* being different on the two
sides, not about the LP being incorrect. Its 26 tests pass unchanged.

**"Did you change the reward?"**
No. `test_goalpilot_env_parity.py` compares reward to 1e-12 across 100 users × 5 policies ×
142 months. Only *reporting* was added.

**"What is the single most important fix?"**
`action_mode="share"`. It is the one change that removes an unfair handicap from every
policy at once — and it is why the next training run can be meaningful.

**"What would you do next?"**
Retrain with `recommended()`, more than 50 k timesteps and `n_envs > 1`; add a terminal
net-worth term to replace the unbounded monthly risk penalty; then re-run
`evaluation/run_all.py` and compare.

---

## One-slide summary

| | Before | After |
|---|---|---|
| RL environment tests | 0 | 64 (plus the LP's original 26) |
| Archived results reproducible | — | yes, 5,541 field comparisons, 0 mismatches |
| Ledger | contributions counted twice; loans unrecorded | balanced, verified every month |
| Savings vs mixed goal funding | identical (a bug) | identical (documented) or genuinely different (`growth_weighted`) |
| Action semantics | magnitude; no gradient above 0.5 | magnitude (archived) **or** share (full budget) |
| LP vs RL target basis | different, compared anyway | one config flag; parity tested |
| Reward | 4 terms, never measured | decomposed per month, per policy |
| Borrowing | "PPO borrows, needs examination" | 5 help / 5 hurt / 1 neutral; ₹0.29 interest per funded rupee |
| Paths | Colab-only, hard-coded | local, Colab, or env var |
