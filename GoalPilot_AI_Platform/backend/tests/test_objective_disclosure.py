"""The comparison must say which objective it optimised, and where the objectives disagree.

Two metrics can name different winners — achievement rewards spreading progress, deadline
completion rewards finishing goals. Reporting the disagreement is the alternative to silently
choosing a weighting on the user's behalf.
"""
from __future__ import annotations

from tests.conftest import seed_profile_and_goal


def test_compare_exposes_objective_disagreement_and_decision_basis(registered):
    seed_profile_and_goal(registered, goals=2)

    response = registered["client"].post(
        "/api/optimize/compare", headers=registered["headers"]
    )
    assert response.status_code == 200, response.text
    body = response.json()

    disagreement = body["objective_disagreement"]
    assert set(disagreement) >= {
        "present",
        "by_weighted_achievement",
        "by_deadline_completion",
        "note",
    }
    assert isinstance(disagreement["present"], bool)
    assert disagreement["note"]

    # The rule is stated in the response, not only in the docs.
    assert body["decision_basis"].startswith("LP-anchored")
    assert "weighted achievement" in body["decision_basis"]

    # Whatever was recommended must be one of the arms that actually scored.
    algorithms = {arm["algorithm"] for arm in body["arms"]}
    assert body["recommended_algorithm"] in algorithms


def test_every_arm_that_lost_carries_a_reason(registered):
    seed_profile_and_goal(registered, goals=2)

    body = registered["client"].post(
        "/api/optimize/compare", headers=registered["headers"]
    ).json()

    reasons = body["not_selected"]
    assert reasons, "a comparison must explain the arms it did not choose"
    for entry in reasons:
        assert entry.get("algorithm")
        assert entry.get("reason"), "a non-selected arm without a reason is not auditable"
