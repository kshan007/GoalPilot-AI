"""Health, assumptions and the educational knowledge layer."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.engines import research_loader
from app.engines.common import ALGORITHM_LABELS
from app.services.cashflow import ESSENTIAL_CATEGORIES
from app.services.forecasting import METHOD_VERSION, PERSONALISED_METHODS
from app.services.scenarios import list_presets

router = APIRouter(tags=["meta"])

DISCLAIMER = (
    "GoalPilot AI is an academic research and decision-support prototype. It does not provide "
    "personalised or regulated financial advice, it does not guarantee any return, and it does "
    "not execute trades, move money or originate loans. Every rate, return and projection shown "
    "is an assumption or a synthetic value, clearly labelled as such."
)

# Educational layer. These are general principles derived from the project's own knowledge
# module and its documented concepts. They are NOT quotations from NISM or any other
# institution: no verified copy of any NISM publication exists in this repository, so no
# citation is claimed. Any course-stated rate, tax rule or eligibility condition is treated
# as potentially outdated and is not restated as current fact.
EDUCATION = [
    {
        "topic": "Budgeting",
        "principle": "Separate essential spending from discretionary spending, then plan the "
                     "surplus rather than the income.",
        "source": "General principle (uncited). No verified publication is held in this "
                  "repository.",
    },
    {
        "topic": "Emergency fund",
        "principle": "Hold a liquidity buffer before committing money to long-horizon, "
                     "less-liquid goals. Six months of essential expenses is a common planning "
                     "guideline, not a universal requirement.",
        "source": "General principle (uncited).",
    },
    {
        "topic": "Goal prioritisation",
        "principle": "Rank goals by consequence and timing. A short-horizon goal usually needs "
                     "lower-volatility funding than a distant one.",
        "source": "General principle (uncited).",
    },
    {
        "topic": "Inflation",
        "principle": "A future goal costs more than it does today. The planner compounds the "
                     "current cost at an explicit inflation assumption that the user can change.",
        "source": "General principle (uncited). Historical CPI is used as data, never as a "
                  "forecast.",
    },
    {
        "topic": "Investment risk",
        "principle": "Risk capacity (ability to withstand a loss) is not the same as risk "
                     "appetite. The platform records both and never infers one from the other.",
        "source": "General principle (uncited).",
    },
    {
        "topic": "Diversification",
        "principle": "Spreading exposure reduces the impact of any single holding, but it does "
                     "not remove market risk.",
        "source": "General principle (uncited).",
    },
    {
        "topic": "Borrowing",
        "principle": "Financing increases total cost through interest and creates a fixed "
                     "obligation. The platform only considers it where the resulting EMI fits "
                     "the configured share of income, and never merely to make a goal appear "
                     "funded.",
        "source": "General principle (uncited).",
    },
    {
        "topic": "Liabilities",
        "principle": "A loan EMI already contains both principal and interest. The monthly "
                     "obligation is the EMI; the outstanding principal is a balance-sheet "
                     "figure. Adding them together double-counts.",
        "source": "General principle (uncited). This is the platform's own accounting rule.",
    },
]


@router.get("/health")
def health(db: Session = Depends(get_db)):
    settings = get_settings()
    research = research_loader.status()

    # A health check that cannot fail is not a health check. This previously reported
    # `status: healthy` and `database: true` while every DB-backed endpoint was returning 500
    # because the configured Postgres credentials were wrong — the most misleading state an
    # operator can be shown. The probe below actually opens a connection.
    database_ok = True
    database_error: str | None = None
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - any failure means "not usable"
        database_ok = False
        database_error = f"{type(exc).__name__}: {str(exc)[:200]}"

    return {
        "status": "healthy" if database_ok else "degraded",
        "database": {
            "reachable": database_ok,
            "dialect": settings.database_url.split(":", 1)[0],
            "error": database_error,
        },
        "app_name": settings.app_name,
        "version": settings.api_version,
        "environment": settings.environment,
        "research_source": research.as_dict(),
        "supported_features": {
            "multi_goal_optimization": True,
            "reinforcement_learning": research.modules.get("goalpilot_env", False),
            "hybrid_optimization": research.modules.get("goalpilot_env", False),
            "adaptive_forecasting": True,
            "authentication": True,
            "database": database_ok,
            "scenario_simulation": True,
            "protected_savings_buffer": True,
            "investment_discovery": True,
            "loan_discovery_and_analysis": True,
            "structured_recommendations": True,
            "llm_configured": bool(settings.gemini_configured),
            "solver": "scipy.optimize.linprog(highs)",
        },
        "disclaimer": DISCLAIMER,
    }


@router.get("/meta/assumptions")
def assumptions():
    settings = get_settings()
    return {
        "defaults": {
            "annual_inflation": settings.default_annual_inflation,
            "investment_return": settings.default_investment_return,
            "savings_return": settings.default_savings_return,
            "loan_annual_rate": settings.default_loan_annual_rate,
            "loan_tenure_months": settings.default_loan_tenure_months,
            "emergency_months": settings.default_emergency_months,
            "emi_income_ratio_cap": settings.default_emi_income_ratio_cap,
        },
        "note": (
            "These are assumptions, not facts. They are editable per user and per plan request, "
            "and every plan reports the values it actually used."
        ),
        "provenance_rules": [
            "actual      = recorded by the user as a real transaction",
            "estimated   = produced by the forecast component, with its method recorded",
            "projected   = produced by the planner using the stated assumptions",
            "historical  = observed data (NIFTY 50, RBI series, HCES) used for calibration only, "
            "never as a guaranteed forward return",
            "synthetic   = generated research data, labelled wherever it appears",
        ],
        "cashflow_definition": {
            "income": "sum of active income sources normalised to a monthly equivalent",
            "essential_expenses": "recorded essential spending",
            "discretionary_expenses": "recorded discretionary spending",
            "existing_emi": "sum of liability EMI amounts (principal is never added)",
            "monthly_surplus": "income - essential - discretionary - existing_emi",
            "available_cash_for_goals": (
                "liquid assets - (emergency_months x essential) - goal earmarks"
            ),
        },
        "essential_categories": sorted(ESSENTIAL_CATEGORIES),
        "scenario_presets": list_presets(),
        "algorithm_labels": ALGORITHM_LABELS,
        "forecast": {
            "method_version": METHOD_VERSION,
            "personalised_methods": list(PERSONALISED_METHODS),
            "requires_backtest_improvement": True,
            "cross_user_training": False,
        },
    }


@router.get("/meta/education")
def education():
    return {
        "items": EDUCATION,
        "citation_policy": (
            "The project holds no verified copy of any NISM publication and no citation. These "
            "principles are therefore presented as uncited general educational content. "
            "Course-stated rates, tax rules and eligibility conditions are not restated as "
            "current fact."
        ),
        "separation_note": (
            "This educational layer is text only. It never feeds numbers into the optimiser and "
            "cannot override a financial constraint."
        ),
    }


@router.get("/meta/data-provenance")
def data_provenance():
    settings = get_settings()
    research = research_loader.status()
    return {
        "research_available": research.available,
        "research_root": research.root,
        "datasets": [
            {
                "name": "NIFTY 50 monthly market path",
                "kind": "historical",
                "rows": 142,
                "period": "2015-03 onward",
                "used_for": "scenario analysis and the RL environment's monthly market return",
                "caveat": "Historical observations, not a guaranteed forward return.",
            },
            {
                "name": "RBI weighted-average lending rate series",
                "kind": "historical",
                "used_for": "loan-cost calibration in the research environment",
                "caveat": "A weighted average is not the rate available to any individual "
                          "borrower.",
            },
            {
                "name": "RBI Consumer Price Index series",
                "kind": "historical",
                "used_for": "historical inflation calibration",
                "caveat": "Historical CPI is not used as a forward inflation forecast; the "
                          "inflation assumption is an explicit parameter.",
            },
            {
                "name": "HCES 2023-24",
                "kind": "historical",
                "used_for": "household expenditure structure in the synthetic population",
                "caveat": "Aggregate survey data.",
            },
            {
                "name": "Synthetic multi-goal population",
                "kind": "synthetic",
                "rows": 10_000,
                "goal_rows": 39_932,
                "used_for": "benchmarks only",
                "caveat": "Generated data. Not real people.",
            },
        ],
        "note": (
            "The application never loads the full research dataset at runtime. It uses the "
            "validated model artefacts and a single 142-row market path."
        ),
    }
