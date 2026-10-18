# Fresh-split confirmation: does `candidate_a`'s advantage reproduce?

**Date:** 2026-10-11 · **Stage:** P2 · **Script:** `audit_tools/60_fresh_split_experiment.py`
**Outputs:** `training_logs/experiments/fresh_split_v1/`, `outputs/reward_design/v3/`
**Interpreter:** `C:\Users\sudha\AppData\Local\Programs\Python\Python313\python.exe` (3.13.7)

---

## Decision

> **`candidate_a`'s advantage is NOT reproducible.** On users that played no part in choosing it,
> `candidate_a` and `archived_v1` are statistically indistinguishable on weighted goal
> achievement (+0.0069, clustered 95% CI [−0.0268, +0.0444], paired t p = 0.72) and on the
> percentage of goals fully funded (−0.0184, CI [−0.0556, +0.0201], p = 0.37). The large
> advantages reported at v1 (+0.0821 and +0.1050, both with intervals excluding zero) do not
> survive.
>
> **`candidate_a` should not be promoted.** It remains an unproven experimental design. The
> package default is unchanged (`archived_v1`), and neither version should be described as
> better than the other on goal attainment.

The single weak, method-dependent signal — deadline success — is recorded below as a hypothesis
for a properly powered pre-registered study, **not** as a result.

---

## 1. What was done

### 1.1 The fresh split

| Partition | Users | Role |
|---|---:|---|
| train | **48** | the only users either arm ever trains on |
| validation | **16** | reserved for model selection |
| **fresh test** | **16** | untouched until the single final evaluation |
| **excluded — contaminated** | **20** | the users used throughout v1 *and* used to choose `candidate_a` |

Generator: `numpy.random.default_rng(20261011).permutation` over the sorted user list, after
removing the 20 contaminated users. Recorded in
`fresh_split_v1_manifest.json` and `fresh_split_v1.csv`.

**Leakage checks passed as programmatic assertions** (the script aborts if any fails): no overlap
between train / validation / test; no previously used user in any fresh partition; all 100 users
accounted for exactly once. **The validation partition was not used at all**, because no
hyper-parameter or variant selection was performed — the two reward versions were fixed before
this stage, so selection risk is zero by construction.

Fresh test users: `USER_00088, _87, _62, _39, _24, _64, _85, _29, _79, _66, _75, _15, _48, _30,
_82, _55` — none appear in the original evaluation set.

### 1.2 Training

Both arms, from scratch, identical in every respect except `reward_version`:

| Element | Value |
|---|---|
| Configuration | `GoalPilotConfig.recommended().replace(reward_version=...)` |
| Training users | the same 48 fresh train users for both arms |
| Seeds | 7, 17, 27 — matched |
| Timesteps | 50,000 each (353 episodes each, verified in the logs) |
| Hyper-parameters | `MlpPolicy`, `n_steps=256`, `batch_size=64`, `n_epochs=4`, `gamma=0.99`, `lr=3e-4`, `net_arch=[128,128]` |
| Checkpoints | 6 new, none reused for either arm |

## 2. Results

### 2.1 Per-seed headline results (16 fresh test users)

| Arm | Seed | Weighted achievement | % fully funded | % by deadline |
|---|---:|---:|---:|---:|
| `archived_v1` | 7 | **0.5908** | **0.4812** | 0.1042 |
| `archived_v1` | 17 | 0.5265 | 0.4198 | 0.0938 |
| `archived_v1` | 27 | 0.4399 | 0.3177 | 0.1062 |
| `candidate_a` | 7 | 0.4895 | 0.3792 | 0.1344 |
| `candidate_a` | 17 | 0.5299 | 0.4073 | 0.1062 |
| `candidate_a` | 27 | **0.5586** | 0.3771 | **0.1375** |

| Arm | Mean achievement | **SD across seeds** |
|---|---:|---:|
| `archived_v1` | 0.5191 | **0.0757** |
| `candidate_a` | 0.5260 | **0.0347** |

**The between-arm difference (+0.0069) is eleven times smaller than `archived_v1`'s own seed
variability (0.0757).** The best `archived_v1` seed (0.5908) beats every `candidate_a` seed
except one; the ordering of the arms reverses depending on which seed you pick.

### 2.2 Paired comparisons — user-clustered bootstrap and user-mean paired t-test

Paired on `(user_id, seed)`; clustered bootstrap resamples **users**, keeping each user's three
seeds together, so repeated rolls are never treated as independent. n = 16 users (14 eligible).

| Population | Metric | Mean diff (candidate_a − archived_v1) | Clustered CI95 | Paired t p | Naive verdict | Clustered verdict | t-test verdict |
|---|---|---:|---|---:|---|---|---|
| all (n=16) | weighted achievement | **+0.0069** | [−0.0268, +0.0444] | 0.7154 | inconclusive | **inconclusive** | inconclusive |
| all (n=16) | % fully funded | **−0.0184** | [−0.0556, +0.0201] | 0.3723 | inconclusive | **inconclusive** | inconclusive |
| all (n=16) | % by deadline | +0.0247 | **[+0.0010, +0.0483]** | 0.0650 | inconclusive | *favours candidate_a* | inconclusive |
| eligible (n=14) | weighted achievement | +0.0079 | [−0.0300, +0.0501] | 0.7173 | inconclusive | inconclusive | inconclusive |
| eligible (n=14) | % fully funded | −0.0210 | [−0.0635, +0.0230] | 0.3748 | inconclusive | inconclusive | inconclusive |
| eligible (n=14) | % by deadline | +0.0282 | **[+0.0024, +0.0540]** | 0.0645 | inconclusive | *favours candidate_a* | inconclusive |

Every other metric in the brief — shortfall, net worth, cash, portfolio, principal borrowed,
interest paid, remaining debt, risk, affordability violations — is **inconclusive in both
populations**. Full table: `fresh_split_paired_v1.csv`.

### 2.3 Side by side with the original experiment

| Metric | v1, original 20 users **used for selection** | v3, fresh 16 users **never used** |
|---|---|---|
| Weighted achievement | +0.0821, CI [0.041, 0.126], p = 0.0016 ✅ | **+0.0069, CI [−0.027, 0.044], p = 0.72** ❌ |
| % fully funded | +0.1050, CI [0.050, 0.164] ✅ | **−0.0184, CI [−0.056, 0.020]** ❌ (sign reversed) |
| % by deadline | +0.0486, CI [0.007, 0.096] ✅ | +0.0247, CI [0.001, 0.048], p = 0.065 ⚠️ (halved) |

**This is a textbook winner's-curse pattern**: the estimate obtained on the set used to select
the winner was roughly an order of magnitude larger than the unbiased estimate, and one component
changed sign. The v1 result was not a fabrication — the computation was correct — but it was
computed on a set that had already been used to pick the winner, which is exactly the
contamination this stage was designed to remove.

**A second caution the fresh split exposes:** the overall achievement level differs sharply
between cohorts (`archived_v1` 0.3202 on the old test set vs 0.5191 here). Twenty users are not
enough to characterise the population, so effect sizes from either split should be treated as
cohort-specific.

## 3. The one weak signal, recorded as a hypothesis

Deadline success favours `candidate_a` by about +0.025 and the clustered CI just excludes zero —
but the paired t-test does not (p = 0.065), and the naive method that was wrong before also says
inconclusive. With 16 users and 3 seeds, and with one of three methods disagreeing, this is
**not** evidence. Given that the graduated shortfall term in `candidate_a` is *designed* to
signal deadlines earlier, it is a plausible hypothesis worth testing properly. That requires a
pre-registered study on a larger fresh cohort, not a re-reading of these numbers.

## 4. Exclusions and limitations

**Exclusions (ex-ante, by `monthly_surplus > 0`):** `USER_00087`, `USER_00082` — 2 of 16 fresh
test users have a zero discretionary budget and cannot fund a goal under any action (established
in Phase 1). Results are reported for **both** the full 16 and the eligible 14; no exclusion is
outcome-based.

**Limitations:**

1. **16 users and 3 seeds is a small sample.** It is large enough to reject a +0.08 effect but
   cannot resolve a +0.01 one.
2. **50,000 timesteps.** Both arms plateaued in the v1 experiment; this compares learning signals
   at one budget, not converged policies.
3. **`archived_v1`'s seed variance (0.0757) is itself large**, which is why the arms are hard to
   separate. That variance is an under-studied property of the reward.
4. **One environment.** The R-12 degeneracy and R-13 budget destruction found in P1 bound both
   arms equally and compress the range of achievable behaviour. Neither was modified.
5. **`candidate_a`'s lower seed SD (0.0347 vs 0.0757) is suggestive of better stability** but is
   estimated from 3 seeds; it is a hypothesis, not a finding.
6. **Nothing here validates `candidate_b`** on a fresh split; it was not part of P2.

## 5. Consequences for the plan

- **P3 (the 50k/150k/300k budget comparison) is now further de-prioritised.** The effect it
  would chase (+0.007) is an order of magnitude smaller than the seed noise and than the
  strategy-space gap found in P1 (RL trails simple baselines by ≈0.039). Spending ≈38 minutes of
  compute to refine a difference smaller than the measurement noise is not justified.
- **P1a/P1b (the environment defects R-13 and R-12) become the clear priority.** They are the
  only identified effects that are large, mechanical and reproducible.
- **No reward version should be promoted** on the present evidence. `archived_v1` remains the
  default; `candidate_a` remains available and experimental.

## 6. Reproducing

```powershell
$py = "C:\Users\sudha\AppData\Local\Programs\Python\Python313\python.exe"
Set-Location S:\fyp\GoalPilot_AI_Completed

# 1. build and document the split (deterministic, seed 20261011)
& $py audit_tools\60_fresh_split_experiment.py --stage split

# 2. train both arms from scratch: 2 versions x 3 matched seeds x 50,000 steps
& $py audit_tools\60_fresh_split_experiment.py --stage train --versions candidate_a
& $py audit_tools\60_fresh_split_experiment.py --stage train --versions archived_v1

# 3. evaluate on the 16 fresh test users with user-clustered statistics
& $py audit_tools\60_fresh_split_experiment.py --stage eval
```

`--stage train` is idempotent and resumable; `--force` retrains a single arm. Raw console output:
`outputs/reward_design/v3/{split,train_candidate_a,train_archived_v1,eval}_console.txt`.
