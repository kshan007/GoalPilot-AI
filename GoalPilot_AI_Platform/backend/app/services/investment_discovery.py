"""Investment discovery: normalise, filter, score and explain.

This module is deliberately **independent of the optimiser**. The LP allocates between
abstract asset classes ("savings" and "investment"); this module answers a different
question: *which actual instruments could a user consider, and why are they or aren't they
suitable?* Nothing here feeds a number into the LP, and no LP output is presented as a product
recommendation.

Ranking is a transparent, additive penalty model over the user's own stated constraints. It is
not a risk-profiling instrument, it does not predict returns, and a high score is not a
recommendation to buy.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Iterable

from app.config import get_settings
from app.providers import amfi, mfapi, registry
from app.providers.base import NormalizedInvestment, ProviderOutcome, iso, utcnow

DISCLOSURE = (
    "Investment options are sourced product information, not advice or an offer. Historical "
    "returns, where shown, are past observations over the exact period stated and are not a "
    "forecast or a guarantee. Category scores measure fit against the constraints this "
    "application records; they are not a suitability assessment by a registered adviser."
)

RISK_WORDS = {"low": 0.15, "moderate": 0.45, "high": 0.65, "very_high": 0.8, "unknown": 0.5}


# --------------------------------------------------------------------------------------
# user context
# --------------------------------------------------------------------------------------
def user_context(
    *,
    risk_capacity: float,
    loss_ability: str,
    liquidity_requirement: str,
    horizon_months: int,
    monthly_capacity: float,
    emergency_fund_progress: float,
    existing_assets: Iterable[Any] = (),
) -> dict[str, Any]:
    buckets = {"cash": 0.0, "market": 0.0, "debt": 0.0}
    total = 0.0
    for asset in existing_assets:
        value = float(getattr(asset, "current_value", 0) or 0)
        kind = str(getattr(asset, "asset_type", "") or "")
        total += value
        if kind in {"liquid_savings", "emergency_savings"}:
            buckets["cash"] += value
        elif kind == "fixed_deposit":
            buckets["debt"] += value
        elif kind == "investment":
            buckets["market"] += value
    shares = {k: (round(v / total, 3) if total > 0 else 0.0) for k, v in buckets.items()}
    return {
        "risk_capacity": round(float(risk_capacity), 4),
        "loss_ability": loss_ability,
        "liquidity_requirement": liquidity_requirement,
        "horizon_months": int(horizon_months),
        "monthly_contribution_capacity": round(float(monthly_capacity), 2),
        "emergency_fund_progress": round(float(emergency_fund_progress), 4),
        "existing_asset_total": round(total, 2),
        "existing_bucket_shares": shares,
        "notes": [
            "risk_capacity is the user's declared ability to bear a loss, stored separately "
            "from risk appetite.",
            "horizon_months is the longest remaining goal deadline, used as the planning "
            "horizon for suitability.",
        ],
    }


# --------------------------------------------------------------------------------------
# suitability
# --------------------------------------------------------------------------------------
def score_option(record: NormalizedInvestment, ctx: dict[str, Any]) -> dict[str, Any]:
    capacity = float(ctx["risk_capacity"])
    horizon = int(ctx["horizon_months"])
    liquidity_need = str(ctx["liquidity_requirement"])
    risk = record.risk_score if record.risk_score is not None else RISK_WORDS.get(record.risk_level, 0.5)

    reasons: list[str] = []
    cautions: list[str] = []
    score = 1.0

    # --- risk vs capacity -------------------------------------------------------------
    if risk <= capacity:
        reasons.append(
            f"Risk level '{record.risk_level}' (score {risk:.2f}) is within the declared "
            f"capacity of {capacity:.2f}."
        )
    else:
        gap = risk - capacity
        score -= 0.45 * gap
        cautions.append(
            f"Risk score {risk:.2f} exceeds the declared risk capacity {capacity:.2f} by "
            f"{gap:.2f}; a loss of this size would be hard to absorb."
        )

    # --- horizon vs volatility -------------------------------------------------------
    horizon_penalty = 0.0
    if horizon < 36:
        horizon_penalty = max(0.0, risk - 0.25)
    elif horizon < 60:
        horizon_penalty = max(0.0, risk - 0.40)
    if horizon_penalty > 0:
        score -= 0.25 * horizon_penalty
        cautions.append(
            f"A {horizon}-month horizon leaves little time to recover a drawdown in a "
            f"risk-score-{risk:.2f} instrument."
        )
    else:
        reasons.append(f"The {horizon}-month horizon is long enough for this risk level.")

    # --- liquidity -------------------------------------------------------------------
    if record.liquidity == "lock_in":
        penalty = 1.0 if liquidity_need == "high" else 0.5 if liquidity_need == "medium" else 0.2
        score -= 0.15 * penalty
        cautions.append(
            f"Money is locked in for {record.lock_in_months or 'an unspecified period'} months, "
            f"which conflicts with a '{liquidity_need}' liquidity requirement."
            if liquidity_need == "high"
            else f"Lock-in of {record.lock_in_months or 'unspecified'} months; accessible only "
            "after that period."
        )
    elif record.liquidity in {"daily", "t_plus_1"}:
        reasons.append("Redeemable on a daily/T+1 basis, so it can serve as a liquidity layer.")

    if record.lock_in_months and record.lock_in_months > horizon:
        score -= 0.10
        cautions.append(
            f"The lock-in ({record.lock_in_months} months) is longer than the planning horizon "
            f"({horizon} months), so this cannot fund the goal on time."
        )

    # --- eligibility -----------------------------------------------------------------
    eligibility_status = "established"
    constrained = {"govt_ssy", "govt_scss"}
    if record.product_id in constrained:
        eligibility_status = "not_established"
        score -= 0.15
        cautions.append(
            "This scheme has an eligibility condition (age or beneficiary) that the financial "
            "profile does not record. Eligibility has NOT been established; verify it before "
            "considering the product at all."
        )

    # --- concentration ---------------------------------------------------------------
    category = record.category
    shares = ctx.get("existing_bucket_shares", {})
    if category in {"equity_mf", "index_fund", "etf"} and shares.get("market", 0) > 0.6:
        score -= 0.05
        cautions.append(
            f"{shares['market']:.0%} of existing assets is already in market-linked holdings; "
            "adding more increases concentration."
        )
    if category == "govt_scheme" and shares.get("debt", 0) > 0.6:
        score -= 0.05
        cautions.append("Existing assets are already concentrated in fixed-income products.")

    score = max(0.0, min(1.0, score))
    if not record.historical_returns:
        cautions.append(
            "No trailing return is shown because no usable NAV history was retrieved. The "
            "absence of a return series is not evidence of a low return."
        )
    if record.data_quality in {"category_scenario", "official_snapshot"}:
        cautions.append(
            "Data quality is "
            f"'{record.data_quality}'. Treat the values as reference information with the "
            "stated effective date, not as a live quote."
        )

    return {
        "score": round(score, 4),
        "risk_score_used": round(risk, 4),
        "eligibility_status": eligibility_status,
        "reasons": reasons,
        "cautions": cautions,
    }


# --------------------------------------------------------------------------------------
# shortlist
# --------------------------------------------------------------------------------------
def _diversified_shortlist(
    records: list[NormalizedInvestment], *, per_category: int
) -> list[NormalizedInvestment]:
    """Deterministic, diversified sample.

    Selection is by AMFI scheme code within each category — a stable, arbitrary ordering. It is
    explicitly **not** a performance ranking, because AMFI's file carries no performance.
    """
    grouped: dict[str, list[NormalizedInvestment]] = {}
    for record in records:
        grouped.setdefault(record.category, []).append(record)
    shortlist: list[NormalizedInvestment] = []
    for category in sorted(grouped):
        ordered = sorted(grouped[category], key=lambda r: (len(r.product_id), r.product_id))
        shortlist.extend(ordered[:per_category])
    return shortlist


def discover(
    *,
    risk_capacity: float,
    loss_ability: str = "moderate",
    liquidity_requirement: str = "medium",
    horizon_months: int = 60,
    monthly_capacity: float = 0.0,
    emergency_fund_progress: float = 0.0,
    existing_assets: Iterable[Any] = (),
    categories: list[str] | None = None,
    include_history: bool = False,
    limit: int = 24,
) -> dict[str, Any]:
    settings = get_settings()
    ctx = user_context(
        risk_capacity=risk_capacity,
        loss_ability=loss_ability,
        liquidity_requirement=liquidity_requirement,
        horizon_months=horizon_months,
        monthly_capacity=monthly_capacity,
        emergency_fund_progress=emergency_fund_progress,
        existing_assets=existing_assets,
    )

    outcomes = registry.investment_outcomes()
    all_records: list[NormalizedInvestment] = []
    provider_rows: list[dict[str, Any]] = []
    scenario_used = False

    for outcome in outcomes:
        provider_rows.append(outcome.as_dict())
        if outcome.status in {"ok", "partial"} and outcome.records:
            all_records.extend(outcome.records)  # type: ignore[arg-type]
        elif outcome.provider == amfi.PROVIDER_NAME:
            fallback = amfi.category_scenarios(outcome.reason or outcome.status)
            all_records.extend(fallback)
            scenario_used = True

    # Explicitly labelled category scenarios are always added for asset classes that no live
    # provider covers, so the page explains categories even when every feed is down.
    covered_categories = {r.category for r in all_records}
    for scenario in amfi.category_scenarios("category coverage gap"):
        if scenario.category not in covered_categories:
            all_records.append(scenario)
            scenario_used = True

    if categories:
        wanted = {c.strip().lower() for c in categories if c.strip()}
        all_records = [r for r in all_records if r.category.lower() in wanted]

    investment_outcomes = [o for o in outcomes if o.kind == "investment"]
    mf_records = [r for r in all_records if r.provider == amfi.PROVIDER_NAME]
    shortlisted_mf = _diversified_shortlist(
        mf_records, per_category=max(1, settings.investment_shortlist_per_category)
    )
    other = [r for r in all_records if r.provider != amfi.PROVIDER_NAME]
    shortlist = shortlisted_mf + other

    history_meta: dict[str, Any] = {"enabled": False, "reason": "not_requested"}
    if include_history and shortlisted_mf:
        history_meta = mfapi.enrich(shortlisted_mf, limit=6)
        shortlist = shortlisted_mf + other

    scored: list[dict[str, Any]] = []
    for record in shortlist:
        suitability = score_option(record, ctx)
        payload = record.as_dict()
        payload["suitability"] = suitability
        scored.append(payload)

    scored.sort(key=lambda item: (-item["suitability"]["score"], -item["completeness"], item["name"]))
    matched_count = len(scored)

    # Round-robin across categories when trimming to `limit`, so a page never shows eight
    # variants of the same asset class. Order within a category is still by suitability.
    if limit and len(scored) > limit:
        buckets: dict[str, list[dict[str, Any]]] = {}
        for item in scored:
            buckets.setdefault(item["category"], []).append(item)
        order = sorted(buckets, key=lambda c: (-buckets[c][0]["suitability"]["score"], c))
        selected: list[dict[str, Any]] = []
        depth = 0
        while len(selected) < limit:
            progressed = False
            for category in order:
                if depth < len(buckets[category]) and len(selected) < limit:
                    selected.append(buckets[category][depth])
                    progressed = True
            if not progressed:
                break
            depth += 1
        scored = selected

    for index, item in enumerate(scored, start=1):
        item["rank"] = index

    top_scores = [item["suitability"]["score"] for item in scored]
    tied = len(top_scores) > 1 and top_scores[0] == top_scores[1]
    tie_note = (
        "Several options share the same score: once every stated constraint is satisfied the "
        "model has no further basis to separate them, so equal scores are a tie, not a ranking."
        if tied
        else ""
    )

    missing: list[str] = []
    if not outcome_ok(outcomes, amfi.PROVIDER_NAME):
        missing.append(
            "Live AMFI NAV retrieval failed; category scenarios are shown instead of named "
            "schemes."
        )
    if scenario_used:
        missing.append(
            "Some rows are category-level scenarios (data_quality='category_scenario'). They "
            "are not products and have no current rate or NAV."
        )
    if not any(item.get("historical_returns") for item in scored):
        missing.append(
            "No trailing performance is available. Enable GOALPILOT_ENABLE_MFAPI_HISTORY to "
            "attach NAV-history returns (unofficial mirror), or consult the scheme's own "
            "disclosure document."
        )
    if not any(item.get("expense_ratio") for item in scored):
        missing.append(
            "Expense ratios, exit loads and minimum investment amounts are not published in "
            "the sources used here and are therefore blank, not estimated."
        )

    return {
        "generated_at": iso(utcnow()),
        "as_of_date": dt.date.today().isoformat(),
        "user_context": ctx,
        "providers": provider_rows,
        "market_context": market_block(),
        "options": scored,
        "option_count": len(scored),
        "options_matched": matched_count,
        "tie_note": tie_note,
        "total_candidates_considered": len(shortlist),
        "category_scenarios_used": scenario_used,
        "history_enrichment": history_meta,
        "missing_information": missing,
        "selection_rule": (
            "Direct-plan growth schemes only, up to "
            f"{settings.investment_shortlist_per_category} per SEBI category, ordered by AMFI "
            "scheme code (a stable arbitrary order). Ranking then applies the suitability "
            "penalties described in /meta/investment-methodology."
        ),
        "disclosure": DISCLOSURE,
        "not_advice": True,
    }


def outcome_ok(outcomes: list[ProviderOutcome], name: str) -> bool:
    for outcome in outcomes:
        if outcome.provider == name:
            return outcome.status in {"ok", "partial"} and bool(outcome.records)
    return False


def market_block() -> dict[str, Any]:
    from app.providers import market

    settings = get_settings()
    history = market.historical_stats()
    live = (
        [o.as_dict() for o in registry.economic_outcomes()]
        if settings.enable_live_providers
        else [{"provider": "nse_index", "status": "disabled"}]
    )
    return {"historical": history, "live": live}


def providers_status() -> list[dict[str, Any]]:
    return registry.status_table()
