"""Corrected LP comparison using `goalpilot_lp_encoder`, plus attribution of the old LP figures.

Clipped LP arms found by inspection (`a[:n, 0] = plan["savings"]`, absolute rupees):
    evaluation/final_validation_evaluation.py:154-156
    evaluation/fair_comparison_harness_v2.py:125-126
    audit_tools/50_strategy_space_diagnosis.py:97-98
    audit_tools/51_reallocation_impact.py:100-101
    audit_tools/52_fair_baselines.py:127-128
    audit_tools/53_action_mapping_comparison.py:103-104
`audit_tools/54_*.py` already uses the encoder.

Part A  attribute the difference between the old LP figure and the encoded one, by decomposing
        the encoding into its two candidate causes instead of assuming float32 rounding.
Part B  the corrected comparison: rules + LP (corrected) + LP (historical encoding) + the
        fresh-split RL checkpoints, all under one compatible configuration.
Part C  the LP under each overflow policy, so `legacy` / `retain_as_cash` / `redirect_to_savings`
        are evaluated separately and neither is declared better.

Writes `outputs/evaluation/final_validation_v6/`. Nothing existing is overwritten.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from goalpilot_paths import ProjectPaths  # noqa: E402

paths = ProjectPaths.resolve()
paths.add_to_sys_path()
sys.path.insert(0, str(paths.root / "GoalPilot_MultiGoal_Extension"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import goalpilot_env  # noqa: E402
from goalpilot_config import (  # noqa: E402
    ACTION_MODE_SHARE,
    INVESTMENT_OVERFLOW_LEGACY,
    INVESTMENT_OVERFLOW_REDIRECT_TO_SAVINGS,
    INVESTMENT_OVERFLOW_RETAIN_AS_CASH,
    GoalPilotConfig,
)
from goalpilot_lp_encoder import decode_mix_action, encode_lp_plan_for_mix  # noqa: E402

OUT_DIR = paths.root / "outputs" / "evaluation" / "final_validation_v6"
OUT_DIR.mkdir(parents=True, exist_ok=True)

profiles = pd.read_csv(paths.rl_profiles_csv)
goals = pd.read_csv(paths.rl_goals_csv)
market = pd.read_csv(paths.rl_market_csv)
FRESH_TEST = json.loads(
    (paths.root / "training_logs" / "experiments" / "fresh_split_v1"
     / "fresh_split_v1_manifest.json").read_text(encoding="utf-8"))["test_users"]
RL_CKPT = paths.root / "training_logs" / "experiments" / "fresh_split_v1"

RULES = ["uniform savings", "need-proportional savings", "investment-only",
         "mixed allocation", "urgency"]
RL_ARMS = [("candidate_a", s) for s in (7, 17, 27)] + [("archived_v1", s) for s in (7, 17, 27)]
METRICS = ["goal_achievement", "pct_goals_fully_funded", "pct_goals_met_by_deadline",
           "shortfall", "final_cash", "final_portfolio", "net_worth", "debt_outstanding",
           "interest_paid", "investment_cap_overflow", "overflow_retained_as_cash",
           "idle_fraction", "affordability_violations"]


def lp_plan_arrays(uid: str):
    """Solve the LP under the parity assumptions; return per-goal rupee arrays."""
    from src.multi_goal_optimizer import FinancialState, optimize_multi_goal
    p = profiles.loc[profiles["user_id"].astype(str) == uid].iloc[0]
    g = goals.loc[goals["user_id"].astype(str) == uid].copy()
    state = FinancialState(
        monthly_income=float(p["monthly_income"]),
        essential_expenses=float(p["monthly_expenditure"]),
        existing_emi=float(p["monthly_emi"]),
        liquid_savings=float(p["initial_savings"]),
        existing_investments=float(p["initial_investment"]),
        usable_existing_investments=0.0, emergency_months=6.0,
        emi_income_ratio_cap=0.35, risk_capacity=float(p["risk_score"]))
    res = optimize_multi_goal(
        g, state, annual_inflation=0.03, savings_return=0.0, investment_return=0.05,
        investment_risk_score=0.4, loan_annual_rate=0.12, loan_tenure_months=60,
        max_loan_per_goal=150000.0)
    if res["status"] != "optimal" or res["allocations"].empty:
        return None
    alloc = res["allocations"]
    slot = {gid: i for i, gid in enumerate(g["goal_id"].astype(str))}
    sav, inv = np.zeros(5), np.zeros(5)
    best, loan_slot = 0.0, -1
    for _, row in alloc.iterrows():
        i = slot.get(str(row["goal_id"]))
        if i is None or i >= 5:
            continue
        sav[i] = max(0.0, float(row["monthly_savings_contribution"]))
        inv[i] = max(0.0, float(row["monthly_investment_contribution"]))
        if float(row["loan_principal"]) > best:
            best, loan_slot = float(row["loan_principal"]), i
    enc = encode_lp_plan_for_mix(sav, inv, n_slots=5)
    return {"savings": sav, "invest": inv, "encoded": enc, "loan_slot": loan_slot,
            "plan_total": enc["plan_total"], "investment_fraction": enc["investment_fraction"]}


ENCODINGS = ["historical_rupees_clipped", "uniformised_ones", "encoder", "encoder_scaled_1000"]


def lp_action(env, plan, encoding: str) -> np.ndarray:
    n = len(env.user_goals)
    a = np.zeros(env.action_space.shape, dtype=np.float32)
    if plan is None:
        return a
    if encoding == "historical_rupees_clipped":
        # exactly what the v1-v4 harnesses did: absolute rupees into a Box[0, 1] action
        a[:n, 0] = plan["savings"][:n]
        a[:n, 1] = plan["invest"][:n]
    elif encoding == "uniformised_ones":
        # the effect clipping is hypothesised to have: any positive amount becomes 1.0
        a[:n, 0] = (plan["savings"][:n] > 0.0).astype(np.float32)
        a[:n, 1] = (plan["invest"][:n] > 0.0).astype(np.float32)
    elif encoding == "encoder":
        a[:n, :2] = plan["encoded"]["action"][:n, :2]
    elif encoding == "encoder_scaled_1000":
        a[:n, :2] = np.minimum(plan["encoded"]["action_float64"][:n, :2] * 1000.0, 1.0)
    if plan["loan_slot"] >= 0:
        a[int(plan["loan_slot"]), 2] = 1.0
    return a


def rule_action(env, policy) -> np.ndarray:
    n = len(env.user_goals)
    a = np.zeros(env.action_space.shape, dtype=np.float32)
    need = np.maximum(0.0, env.goal_targets - env.goal_balances)[:n]
    total = float(need.sum())
    if policy == "uniform savings":
        a[:n, 0] = 1.0
    elif policy == "need-proportional savings" and total > 0:
        a[:n, 0] = need / total
    elif policy == "investment-only":
        a[:n, 1] = 1.0
    elif policy == "mixed allocation":
        a[:n, 0], a[:n, 1] = 0.5, 0.5
    elif policy == "urgency" and total > 0:
        months = np.maximum(1, env.goal_deadlines[:n] - env.month_index)
        a[int(np.argmax(need / months)), 0] = 1.0
    return a


def run(env, uid, *, plan=None, encoding=None, policy=None, model=None) -> dict:
    obs, _ = env.reset(options={"user_id": uid})
    n = len(env.user_goals)
    targets = env.goal_targets.astype(float)[:n]
    deadlines = env.goal_deadlines[:n].astype(int)
    met = np.zeros(n, dtype=bool)
    seen = np.zeros(n, dtype=bool)
    idle = overflow = retained = budget = violations = 0.0
    while True:
        if model is not None:
            action, _ = model.predict(obs, deterministic=True)
        elif encoding is not None:
            action = lp_action(env, plan, encoding)
        else:
            action = rule_action(env, policy)
        obs, _, term, trunc, info = env.step(action)
        just = int(env.month_index)
        ratio = env.goal_balances[:n] / np.maximum(targets, 1e-9)
        for j in range(n):
            if deadlines[j] == just:
                seen[j] = True
                met[j] = ratio[j] >= 1.0 - 1e-9
        ba = info["budget_audit"]
        idle += ba["unallocated_surplus"]
        overflow += ba["invest_overflow"]
        retained += ba["overflow_retained_as_cash"]
        budget += ba["discretionary_budget"]
        violations += int(bool(ba["cash_floor_active"])) + int(ba["interest_shortfall"] > 1e-9)
        if term or trunc:
            break
    funded = env.goal_balances[:n]
    r = np.minimum(funded, targets) / np.maximum(targets, 1e-9)
    pri = env.user_goals["priority"].astype(float).to_numpy()[:n]
    return {
        "user_id": uid,
        "goal_achievement": float(np.sum(pri * r) / np.sum(pri)),
        "pct_goals_fully_funded": float(np.mean(r >= 1.0 - 1e-9)),
        "pct_goals_met_by_deadline": float(met.sum() / seen.sum()) if seen.any() else np.nan,
        "shortfall": float(np.sum(np.maximum(0.0, targets - funded))),
        "final_cash": float(env.cash), "final_portfolio": float(env.portfolio),
        "net_worth": float(env.net_worth), "debt_outstanding": float(env.loan_balance),
        "interest_paid": float(env.total_interest_paid),
        "investment_cap_overflow": overflow, "overflow_retained_as_cash": retained,
        "idle_fraction": idle / max(budget, 1e-9),
        "affordability_violations": float(violations),
    }


def main() -> None:
    plans = {uid: lp_plan_arrays(uid) for uid in FRESH_TEST}

    # ---- encode/decode parity, validated BEFORE any capacity constraint ------------------
    parity = []
    for uid, plan in plans.items():
        if plan is None:
            parity.append({"user_id": uid, "status": "no_optimal_plan"})
            continue
        dec = decode_mix_action(plan["encoded"]["action_float64"], plan["plan_total"], n_slots=5)
        sav_ref = plan["savings"]
        inv_ref = plan["invest"]
        denom = max(float(np.abs(sav_ref).sum() + np.abs(inv_ref).sum()), 1e-9)
        err = (float(np.abs(dec["savings_per_goal"][:5] - sav_ref).sum())
               + float(np.abs(dec["investments_per_goal"][:5] - inv_ref).sum())) / denom
        parity.append({
            "user_id": uid, "status": "ok", "plan_total": plan["plan_total"],
            "investment_fraction": plan["investment_fraction"],
            "max_rel_encode_decode_error": err,
            "reproduces_within_1e-9": bool(err < 1e-9),
        })
    parity_df = pd.DataFrame(parity)
    parity_df.to_csv(OUT_DIR / "lp_encoded_parity_v1.csv", index=False)
    ok = parity_df[parity_df["status"] == "ok"]
    worst = float(ok["max_rel_encode_decode_error"].max()) if len(ok) else float("nan")

    # ---- Part A: attribution of the old LP figure ---------------------------------------
    cfg = GoalPilotConfig.recommended()
    attribution = []
    for encoding in ENCODINGS:
        env = goalpilot_env.GoalPilotEnv(profiles=profiles, goals=goals, market=market,
                                         user_ids=FRESH_TEST, config=cfg)
        rows = [run(env, uid, plan=plans.get(uid), encoding=encoding) for uid in FRESH_TEST]
        env.close()
        frame = pd.DataFrame(rows)
        attribution.append({
            "encoding": encoding,
            "mean_goal_achievement": float(frame["goal_achievement"].mean()),
            "mean_idle_fraction": float(frame["idle_fraction"].mean()),
            "mean_retained_as_cash": float(frame["overflow_retained_as_cash"].mean()),
            "mean_actual_investment_capped_overflow": float(
                frame["investment_cap_overflow"].mean()),
        })
    attribution_df = pd.DataFrame(attribution)
    attribution_df.to_csv(OUT_DIR / "lp_encoding_attribution_v1.csv", index=False)

    # ---- Part B: the corrected comparison, all arms on one configuration -----------------
    assert cfg.action_mode == ACTION_MODE_SHARE, "rules were measured under share semantics"
    rows = []
    env = goalpilot_env.GoalPilotEnv(profiles=profiles, goals=goals, market=market,
                                     user_ids=FRESH_TEST, config=cfg)
    for policy in RULES:
        for uid in FRESH_TEST:
            r = run(env, uid, policy=policy)
            r.update(policy=policy, arm="rule", compatible=True)
            rows.append(r)
    for encoding in ("encoder", "historical_rupees_clipped"):
        for uid in FRESH_TEST:
            r = run(env, uid, plan=plans.get(uid), encoding=encoding)
            r.update(policy=f"LP ({encoding})", arm="LP", compatible=True)
            rows.append(r)
    env.close()

    from stable_baselines3 import PPO
    for arm_name, seed in RL_ARMS:
        ckpt = RL_CKPT / arm_name / f"ppo_{arm_name}_seed{seed}.zip"
        if not ckpt.is_file():
            continue
        # compatibility guard: these checkpoints were trained under share + legacy only
        assert cfg.action_mode == ACTION_MODE_SHARE
        assert cfg.investment_overflow_policy == INVESTMENT_OVERFLOW_LEGACY
        model = PPO.load(str(ckpt))
        env = goalpilot_env.GoalPilotEnv(profiles=profiles, goals=goals, market=market,
                                         user_ids=FRESH_TEST, config=cfg)
        for uid in FRESH_TEST:
            r = run(env, uid, model=model)
            r.update(policy=f"RL {arm_name} seed{seed}", arm="RL", compatible=True)
            rows.append(r)
        env.close()

    detail = pd.DataFrame(rows)
    detail.to_csv(OUT_DIR / "corrected_lp_comparison_detail_v1.csv", index=False)
    summary = detail.groupby(["arm", "policy"])[METRICS].mean().reset_index()
    summary.to_csv(OUT_DIR / "corrected_lp_comparison_summary_v1.csv", index=False)

    # ---- Part C: the LP under each overflow policy, separately ---------------------------
    arms_c = [
        ("share_legacy", GoalPilotConfig.recommended()),
        ("share_retain_as_cash", GoalPilotConfig.with_investment_overflow(
            INVESTMENT_OVERFLOW_RETAIN_AS_CASH)),
        ("share_redirect_to_savings", GoalPilotConfig.with_investment_overflow(
            INVESTMENT_OVERFLOW_REDIRECT_TO_SAVINGS)),
        ("mix_legacy", GoalPilotConfig.with_action_mix()),
        ("mix_retain_as_cash", GoalPilotConfig.with_action_mix().replace(
            investment_overflow_policy=INVESTMENT_OVERFLOW_RETAIN_AS_CASH)),
        ("mix_redirect_to_savings", GoalPilotConfig.with_action_mix().replace(
            investment_overflow_policy=INVESTMENT_OVERFLOW_REDIRECT_TO_SAVINGS)),
    ]
    rows_c = []
    for label, arm_cfg in arms_c:
        env = goalpilot_env.GoalPilotEnv(profiles=profiles, goals=goals, market=market,
                                         user_ids=FRESH_TEST, config=arm_cfg)
        for uid in FRESH_TEST:
            r = run(env, uid, plan=plans.get(uid), encoding="encoder")
            r.update(arm=label, action_mode=arm_cfg.action_mode,
                     overflow_policy=arm_cfg.investment_overflow_policy)
            rows_c.append(r)
        env.close()
    lp_overflow = pd.DataFrame(rows_c)
    lp_overflow.to_csv(OUT_DIR / "lp_overflow_modes_v1.csv", index=False)
    lp_overflow_summary = lp_overflow.groupby(["arm", "action_mode", "overflow_policy"])[
        METRICS].mean().reset_index()
    lp_overflow_summary.to_csv(OUT_DIR / "lp_overflow_modes_summary_v1.csv", index=False)

    print(json.dumps({
        "fresh_test_users": len(FRESH_TEST),
        "lp_plans_decoded": int(len(ok)),
        "worst_encode_decode_rel_error": worst,
        "all_within_tolerance": bool(worst < 1e-9) if ok is not None and len(ok) else False,
        "attribution": attribution_df.round(4).to_dict("records"),
        "summary": summary.round(4).to_dict("records"),
        "lp_overflow": lp_overflow_summary.round(4).to_dict("records"),
        "total_affordability_violations": float(detail["affordability_violations"].sum()
                                                + lp_overflow["affordability_violations"].sum()),
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
