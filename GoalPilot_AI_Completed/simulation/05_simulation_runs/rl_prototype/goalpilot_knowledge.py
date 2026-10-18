"""Grounded investor-education knowledge layer (Phase I).

Why this file is separate from the environment
----------------------------------------------
The FYP brief asks for "the existing NISM investor-education knowledge base and any current
retrieval or recommendation modules". A repository-wide search (see
``docs/EXPLAINABILITY.md`` §1) found **no** such knowledge base, no retrieval module and no
explainability module anywhere in the project. This file therefore *adds* a small, explicitly
labelled teaching layer rather than pretending one already existed.

What this layer is NOT
----------------------
- It is **not** a quotation of, or a citation to, NISM or any other body. Nothing here is
  attributed to an external source, because the project has no verified copy of any such source
  and fabricating a citation is worse than omitting one.
- It is **not** personalised advice and makes **no** promise about returns.

Each entry is a *general financial principle*, compiled for this project, with an explicit
``status`` field recording that it is uncited. The explanatory engine
(:mod:`goalpilot_explain`) attaches these principles to statements about a user's *computed*
results, and always keeps the two apart: facts come from the simulation, principles come from
here, and the two are never merged into a claim about an outcome.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

# A single, explicit marker used wherever an entry has no verified external source.
UNCITED = "uncited_general_principle"

PRINCIPLES: list[dict] = [
    {
        "id": "emergency_fund",
        "topic": "emergency reserve",
        "keywords": ["emergency", "reserve", "buffer", "liquidity", "contingency"],
        "text": "A commonly recommended starting point is to hold several months of essential "
                "expenses in a liquid, low-risk form before committing money to longer-term "
                "goals. The exact number of months depends on income stability and dependants.",
        "status": UNCITED,
    },
    {
        "id": "goal_horizon_risk",
        "topic": "horizon and volatility",
        "keywords": ["horizon", "short term", "volatility", "risk", "equity", "market"],
        "text": "The shorter the horizon before the money is needed, the less a plan should "
                "depend on volatile assets, because there is less time to recover from a "
                "market decline. Long horizons can tolerate more volatility than short ones.",
        "status": UNCITED,
    },
    {
        "id": "inflation_erodes",
        "topic": "inflation",
        "keywords": ["inflation", "real", "cost", "purchasing power", "nominal"],
        "text": "Goal costs usually rise with inflation, so a target expressed in today's money "
                "is normally below the amount that will actually be needed later. A plan that "
                "ignores inflation understates the target.",
        "status": UNCITED,
    },
    {
        "id": "debt_service_first",
        "topic": "debt and affordability",
        "keywords": ["debt", "loan", "emi", "interest", "borrow", "affordability"],
        "text": "Scheduled loan repayments reduce the cash flow available for goals, and "
                "interest is a certain cost whereas investment returns are uncertain. "
                "Borrowing to fund a goal converts an uncertain return into a fixed cost.",
        "status": UNCITED,
    },
    {
        "id": "returns_uncertain",
        "topic": "historical returns",
        "keywords": ["returns", "historical", "guarantee", "past performance", "nifty"],
        "text": "Past market returns are observations of what happened, not promises about what "
                "will happen. A plan that depends on a specific return being achieved is "
                "fragile to that assumption being wrong.",
        "status": UNCITED,
    },
    {
        "id": "capacity_affordability",
        "topic": "investable surplus",
        "keywords": ["capacity", "surplus", "affordable", "how much", "invest"],
        "text": "The amount that can prudently be invested is bounded by income left after "
                "essential spending, existing debt service and a reserve. Capacity is an "
                "affordability limit, not a statement about risk appetite.",
        "status": UNCITED,
    },
    {
        "id": "prioritisation",
        "topic": "conflicting goals",
        "keywords": ["priority", "conflict", "trade-off", "order", "essential"],
        "text": "When goals cannot all be funded, a common approach is to protect essential and "
                "near-term commitments first and to treat discretionary, long-dated goals as "
                "flexible, accepting that their amount or timing may need to change.",
        "status": UNCITED,
    },
    {
        "id": "compounding_time",
        "topic": "compounding",
        "keywords": ["compound", "long term", "time", "growth", "wealth"],
        "text": "Money left invested for longer has more opportunity to compound, so a long-"
                "dated goal generally needs a smaller monthly contribution than a near-term "
                "goal of the same size.",
        "status": UNCITED,
    },
    {
        "id": "separate_money",
        "topic": "earmarking versus ownership",
        "keywords": ["earmark", "balance", "net worth", "double count", "goal balance"],
        "text": "Money earmarked to a goal is not a separate asset; it is part of the same "
                "wealth and must not be counted twice. Progress toward goals and total wealth "
                "are different measures and should be reported separately.",
        "status": UNCITED,
    },
    {
        "id": "review_periodically",
        "topic": "review",
        "keywords": ["review", "monitor", "assumption", "change", "replan"],
        "text": "A plan is only as good as its assumptions. Income, expenses, rates and market "
                "conditions change, so a plan is normally revisited periodically rather than "
                "fixed once.",
        "status": UNCITED,
    },
]


@dataclass(frozen=True)
class Principle:
    id: str
    topic: str
    text: str
    status: str
    keywords: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


class KnowledgeBase:
    """Tiny, dependency-free, deterministic keyword retriever over :data:`PRINCIPLES`."""

    def __init__(self, principles: list[dict] | None = None) -> None:
        self._items = [Principle(id=p["id"], topic=p["topic"], text=p["text"],
                                 status=p["status"], keywords=tuple(p["keywords"]))
                       for p in (principles if principles is not None else PRINCIPLES)]

    def all(self) -> list[Principle]:
        return list(self._items)

    def get(self, principle_id: str) -> Principle | None:
        for p in self._items:
            if p.id == principle_id:
                return p
        return None

    def retrieve(self, query: str, k: int = 3) -> list[Principle]:
        """Return up to ``k`` principles, ranked by keyword/topic overlap with ``query``.

        Deterministic: ties are broken by the declaration order in :data:`PRINCIPLES`.
        An unrecognised query returns an empty list rather than a guess, so callers can
        acknowledge that the knowledge base does not cover the question.
        """
        q = (query or "").lower()
        if not q.strip():
            return []
        scored: list[tuple[int, int, Principle]] = []
        for idx, p in enumerate(self._items):
            score = 0
            if p.topic.lower() in q:
                score += 3
            for kw in p.keywords:
                if kw in q:
                    score += 2
            if p.id.replace("_", " ") in q:
                score += 2
            if score:
                scored.append((score, idx, p))
        scored.sort(key=lambda t: (-t[0], t[1]))
        return [p for _, _, p in scored[:max(0, k)]]


DEFAULT_KB = KnowledgeBase()


if __name__ == "__main__":
    kb = DEFAULT_KB
    for probe in ("emergency fund", "loan interest cost", "unknown topic xyz"):
        hits = kb.retrieve(probe)
        print(f"{probe!r:32s} -> {[h.id for h in hits]}")
