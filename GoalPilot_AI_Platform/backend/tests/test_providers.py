"""Provider-layer tests.

Every external call is replaced with a recorded fixture or a monkeypatched function, so the
suite is deterministic and never depends on a live site. The live behaviour was verified
separately and is recorded in docs/FINAL_VALIDATION_STATUS.md.
"""
from __future__ import annotations

import datetime as dt

import pytest

from app.providers import amfi, loans, mfapi, small_savings
from app.providers.base import (
    CATEGORY_SCENARIO,
    OFFICIAL_LIVE,
    OFFICIAL_SNAPSHOT,
    NormalizedInvestment,
    ProviderOutcome,
    ProviderRegistry,
    TTLCache,
    callable_provider,
    utcnow,
)

AMFI_FIXTURE = """Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;Scheme Name;Plan;Option;Net Asset Value;Date
 
Open Ended Schemes(Equity Scheme - Small Cap Fund)
 
Acme Mutual Fund
 
111;INF1;-;Acme Small Cap Fund;Direct Plan;Growth Option;45.6789;16-Oct-2026
112;INF2;-;Acme Small Cap Fund;Regular Plan;Growth Option;43.2100;16-Oct-2026
113;INF3;-;Acme Small Cap Fund;Direct Plan;IDCW Option;12.0000;16-Oct-2026
 
Open Ended Schemes(Debt Scheme - Liquid Fund)
 
Beta Mutual Fund
 
221;INF4;-;Beta Liquid Fund;Direct Plan;Growth;1234.5678;16-Oct-2026
222;INF5;-;Beta Liquid Fund;Direct Plan;Growth;not-a-number;16-Oct-2026
"""


# ------------------------------------------------------------------------------- AMFI
def test_amfi_keeps_only_direct_growth_and_parses_nav():
    records = amfi.parse_nav_all(AMFI_FIXTURE)
    assert len(records) == 2
    by_id = {r.product_id: r for r in records}
    assert "112" not in by_id, "regular plan must be excluded"
    assert "113" not in by_id, "IDCW option must be excluded"
    assert by_id["111"].nav == pytest.approx(45.6789)
    assert by_id["221"].nav == pytest.approx(1234.5678)
    assert all(r.provider == amfi.PROVIDER_NAME for r in records)
    assert all(r.data_quality == OFFICIAL_LIVE for r in records)
    assert by_id["111"].issuer == "Acme Mutual Fund"
    assert by_id["111"].effective_date == "2026-10-16"


def test_amfi_classification_assigns_risk_by_category():
    records = {r.product_id: r for r in amfi.parse_nav_all(AMFI_FIXTURE)}
    small_cap = records["111"]
    liquid = records["221"]
    assert small_cap.category == "equity_mf"
    assert small_cap.sub_category == "Small cap"
    assert small_cap.risk_level == "very_high"
    assert small_cap.risk_score > liquid.risk_score
    assert liquid.category == "debt_mf"
    assert liquid.risk_level == "low"
    assert liquid.liquidity == "t_plus_1"


def test_amfi_does_not_invent_expense_ratio_or_minimum():
    record = amfi.parse_nav_all(AMFI_FIXTURE)[0]
    assert record.expense_ratio is None
    assert record.min_investment is None
    assert record.historical_returns == []
    assert any("does not publish expense ratio" in n for n in record.notes)


def test_amfi_disabled_by_configuration(monkeypatch):
    monkeypatch.setenv("GOALPILOT_ENABLE_LIVE_PROVIDERS", "false")
    from app.config import reset_settings_cache, get_settings

    reset_settings_cache()
    try:
        outcome = amfi.fetch()
    finally:
        reset_settings_cache()
    assert outcome.status == "disabled"
    assert outcome.records == []


def test_category_scenarios_are_labelled_and_not_products():
    records = amfi.category_scenarios("unit-test reason")
    assert records
    assert all(r.data_quality == CATEGORY_SCENARIO for r in records)
    assert all(r.nav is None and r.published_rate is None for r in records)
    for record in records:
        assert any("NOT a named product" in note for note in record.notes)
        assert any("unavailable" in note for note in record.notes)


# ------------------------------------------------------------------------------ mfapi
def _series(points: list[tuple[str, float]]) -> list[dict[str, str]]:
    return [{"date": d, "nav": str(v)} for d, v in points]


def test_trailing_returns_compute_cagr_over_the_stated_period():
    series = _series(
        [
            ("16-10-2026", 121.0),
            ("16-10-2025", 110.0),   # exactly 1 year earlier
            ("16-10-2023", 90.0),    # 3 years earlier
            ("16-10-2021", 70.0),    # 5 years earlier
        ]
    )
    returns = {r["window"]: r for r in mfapi.compute_trailing_returns(series)}
    assert returns["1y"]["cagr"] == pytest.approx(0.10, abs=1e-6)
    assert returns["3y"]["period_start"] == "2023-10-16"
    assert returns["3y"]["period_end"] == "2026-10-16"
    assert returns["5y"]["cagr"] > 0
    for row in returns.values():
        assert row["basis"].startswith("annualised CAGR")
        assert row["source"] == mfapi.PROVIDER_NAME


def test_trailing_returns_omit_windows_the_series_cannot_reach():
    series = _series([("16-10-2026", 121.0), ("16-10-2025", 110.0)])
    windows = {r["window"] for r in mfapi.compute_trailing_returns(series)}
    assert windows == {"1y"}, "3y and 5y must be omitted rather than extrapolated"


def test_trailing_returns_reject_short_series():
    assert mfapi.compute_trailing_returns([{"date": "16-10-2026", "nav": "12"}]) == []


def test_mfapi_enrichment_failure_is_not_fatal(monkeypatch):
    record = amfi.parse_nav_all(AMFI_FIXTURE)[0]

    def boom(_code):
        raise RuntimeError("mirror down")

    monkeypatch.setattr(mfapi, "fetch_history", boom)
    monkeypatch.setenv("GOALPILOT_ENABLE_MFAPI_HISTORY", "true")
    monkeypatch.setenv("GOALPILOT_ENABLE_LIVE_PROVIDERS", "true")
    from app.config import reset_settings_cache

    reset_settings_cache()
    try:
        result = mfapi.enrich([record], limit=1)
    finally:
        reset_settings_cache()
    assert result["enriched"] == 0
    assert result["failures"]
    assert record.historical_returns == [], "a failure must not fabricate a return"


# ------------------------------------------------------------------------------ loans
LOAN_HTML = """
<html><head>
<meta name="description" content="Get an instant personal loan up to Rs 20 Lakh at an 11% p.a. interest rate">
</head><body><p>Apply online. Interest rates starting at 10.25% p.a. for salaried applicants.</p>
</body></html>
"""


def test_extract_published_rate_prefers_an_explicit_starting_at_sentence():
    # Documented priority: a "starting at" sentence beats a looser "at X% interest rate" phrase,
    # because it is the lender's own unambiguous statement of its floor rate.
    rate, quoted = loans.extract_published_rate(LOAN_HTML)
    assert rate == pytest.approx(0.1025)
    assert "10.25%" in quoted


def test_extract_published_rate_reads_description_metadata():
    meta_only = (
        '<html><head><meta property="og:description" content="up to Rs 20 Lakh at an 11% '
        'p.a. interest rate"></head><body><div id="app"></div></body></html>'
    )
    rate, quoted = loans.extract_published_rate(meta_only)
    assert rate == pytest.approx(0.11)
    assert "11%" in quoted


def test_extract_published_rate_rejects_implausible_values():
    html = '<html><head><meta name="description" content="starting at 45% p.a."></head></html>'
    rate, quoted = loans.extract_published_rate(html)
    assert rate is None and quoted is None


def test_extract_max_amount_units():
    assert loans.extract_max_amount(LOAN_HTML) == pytest.approx(2_000_000)
    crore = '<meta name="description" content="loan up to Rs 1.5 crore">'
    assert loans.extract_max_amount(crore) == pytest.approx(15_000_000)


def test_loan_snapshot_is_labelled_and_never_a_personal_offer():
    records = loans.snapshot_records("unit test")
    assert records
    for record in records:
        assert record.data_quality == OFFICIAL_SNAPSHOT
        assert record.is_personalised_offer is False
        assert record.rate_basis == "advertised_from_rate"
        assert any("not a personalised offer" in n.lower() for n in record.notes)


def test_loan_provider_falls_back_to_snapshot_when_every_page_fails(monkeypatch):
    monkeypatch.setenv("GOALPILOT_ENABLE_LIVE_PROVIDERS", "true")
    from app.config import reset_settings_cache

    reset_settings_cache()

    def boom(*_a, **_k):
        raise RuntimeError("blocked")

    monkeypatch.setattr(loans, "get_text", boom)
    try:
        outcome = loans.fetch()
    finally:
        reset_settings_cache()
    assert outcome.status == "ok"
    assert outcome.data_quality == OFFICIAL_SNAPSHOT
    assert "snapshot" in (outcome.reason or "").lower()
    assert all(r.data_quality == OFFICIAL_SNAPSHOT for r in outcome.records)


def test_walr_benchmark_reports_a_rate_and_a_caveat():
    outcome = loans.walr_benchmark()
    if outcome.status != "ok":  # dataset absent on some checkouts
        pytest.skip("WALR dataset not available")
    record = outcome.records[0]
    assert 0.0 < record["rate"] < 0.5
    assert "not the rate available to any individual" in outcome.metadata["caveat"]


# ------------------------------------------------------------------------ small savings
def test_small_savings_reference_is_source_annotated():
    payload = small_savings.load_reference()
    records = small_savings.to_records(payload)
    assert records
    for record in records:
        assert record.data_quality == OFFICIAL_SNAPSHOT
        assert record.published_rate is not None
        assert record.effective_date == payload["effective_from"]
        assert any("Notified rate for" in n for n in record.notes)
    verification = payload["verification"]
    assert verification["official_page_reachable_from_this_host"] is False
    assert "NSC" in " ".join(verification["cross_check_note"].split())


def test_small_savings_omits_unverified_schemes():
    ids = {r.product_id for r in small_savings.to_records(small_savings.load_reference())}
    assert {"govt_ppf", "govt_ssy", "govt_scss"} <= ids
    assert not any("nsc" in i or "kvp" in i for i in ids)


# ------------------------------------------------------------------------- registry
def _ok_provider():
    return ProviderOutcome(
        provider="good",
        kind="investment",
        status="ok",
        records=[
            NormalizedInvestment(
                provider="good",
                product_id="p1",
                name="Good product",
                category="debt_mf",
                retrieved_at=utcnow().isoformat(),
                data_quality=OFFICIAL_LIVE,
            )
        ],
        data_quality=OFFICIAL_LIVE,
    )


def test_registry_isolates_a_failing_provider():
    registry = ProviderRegistry(cache=TTLCache(0))

    def bad():
        raise RuntimeError("provider exploded")

    registry.register(callable_provider("bad", "investment", "http://x", OFFICIAL_LIVE, bad))
    registry.register(callable_provider("good", "investment", "http://y", OFFICIAL_LIVE, _ok_provider))
    outcomes = {o.provider: o for o in registry.run(kind="investment")}
    assert outcomes["bad"].status == "unavailable"
    assert "provider exploded" in (outcomes["bad"].reason or "")
    assert outcomes["good"].status == "ok"
    assert outcomes["good"].count == 1


def test_registry_caches_successful_outcomes():
    calls = {"n": 0}

    def counted():
        calls["n"] += 1
        return _ok_provider()

    registry = ProviderRegistry(cache=TTLCache(600))
    registry.register(callable_provider("good", "investment", "http://y", OFFICIAL_LIVE, counted))
    registry.run(kind="investment")
    registry.run(kind="investment")
    assert calls["n"] == 1

    registry.clear()
    registry.register(callable_provider("good", "investment", "http://y", OFFICIAL_LIVE, counted))
    registry.run(kind="investment")
    assert calls["n"] == 2


def test_registry_does_not_cache_failures():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        raise RuntimeError("no")

    registry = ProviderRegistry(cache=TTLCache(600))
    registry.register(callable_provider("flaky", "loan", "http://z", OFFICIAL_LIVE, flaky))
    registry.run(kind="loan")
    registry.run(kind="loan")
    assert calls["n"] == 2


# ------------------------------------------------------------------------ freshness
def test_freshness_marks_old_snapshots_stale():
    record = NormalizedInvestment(
        provider="x",
        product_id="1",
        name="Old",
        category="debt_mf",
        data_quality=OFFICIAL_SNAPSHOT,
        retrieved_at=(utcnow() - dt.timedelta(days=400)).isoformat(timespec="seconds"),
    )
    assert record.freshness() == "stale"


def test_freshness_handles_missing_timestamp_without_guessing():
    record = NormalizedInvestment(provider="x", product_id="1", name="No stamp", category="debt_mf")
    assert record.freshness() == "unknown"
    assert record.completeness() < 1.0
