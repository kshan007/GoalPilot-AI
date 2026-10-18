"""Configuration and path-resolution tests (audit findings F-06, F-12)."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from goalpilot_config import (
    ACTION_MODE_MAGNITUDE,
    ACTION_MODE_SHARE,
    ACCOUNTING_MODE_LEGACY,
    ACCOUNTING_MODE_LEDGER,
    GOAL_CREDIT_FACE_VALUE,
    GOAL_CREDIT_GROWTH_WEIGHTED,
    GOAL_CREDIT_MARKET_WEIGHTED,
    GoalPilotConfig,
)
from goalpilot_paths import ENV_VAR, ProjectPaths, detect_project_root


# ------------------------------------------------------------------ config ------------

def test_defaults_preserve_archived_behaviour_except_accounting():
    cfg = GoalPilotConfig()
    assert cfg.action_mode == ACTION_MODE_MAGNITUDE
    assert cfg.goal_credit_mode == GOAL_CREDIT_FACE_VALUE
    assert cfg.target_basis == "nominal"
    assert cfg.emergency_months == 0.0
    # the single deliberate default change: the ledger is now balanced
    assert cfg.accounting_mode == ACCOUNTING_MODE_LEDGER


def test_archived_preset_is_fully_archived():
    cfg = GoalPilotConfig.archived()
    assert cfg.accounting_mode == ACCOUNTING_MODE_LEGACY
    assert cfg.action_mode == ACTION_MODE_MAGNITUDE
    assert cfg.goal_credit_mode == GOAL_CREDIT_FACE_VALUE
    assert cfg.n_goal_slots == 5


def test_lp_parity_preset_matches_the_lp_assumptions():
    cfg = GoalPilotConfig.lp_parity()
    assert cfg.target_basis == "inflated"
    assert cfg.annual_inflation == 0.03
    assert cfg.emergency_months == 6.0
    assert cfg.investment_return_assumption == 0.05
    assert cfg.accounting_mode == ACCOUNTING_MODE_LEDGER


def test_recommended_preset_uses_the_new_mechanisms():
    """The recommended preset credits goals from *realised* revaluation only (finding R-03).

    This assertion was updated deliberately when ``market_weighted`` replaced
    ``growth_weighted`` as the recommended credit mode: booking a projected return as goal
    funding contradicts audit requirement C2. ``growth_weighted`` remains selectable and is
    still exercised by ``test_goalpilot_env_modes.py``.
    """
    cfg = GoalPilotConfig.recommended()
    assert cfg.action_mode == ACTION_MODE_SHARE
    assert cfg.goal_credit_mode == GOAL_CREDIT_MARKET_WEIGHTED
    assert cfg.target_basis == "inflated"
    # the projected-return mode is still available for LP-parity experiments
    assert GoalPilotConfig.lp_parity().replace(
        goal_credit_mode=GOAL_CREDIT_GROWTH_WEIGHTED
    ).goal_credit_mode == GOAL_CREDIT_GROWTH_WEIGHTED


@pytest.mark.parametrize("field,value", [
    ("target_basis", "bogus"),
    ("action_mode", "bogus"),
    ("accounting_mode", "bogus"),
    ("goal_credit_mode", "bogus"),
    ("emergency_months", -1.0),
    ("emi_income_ratio_cap", 0.0),
    ("emi_income_ratio_cap", 1.5),
    ("loan_tenure_months", 0),
    ("max_new_loan", -1.0),
    ("annual_inflation", -1.0),
    ("n_goal_slots", 0),
])
def test_invalid_configuration_is_rejected(field, value):
    with pytest.raises(ValueError):
        GoalPilotConfig(**{field: value})


def test_config_round_trips_through_json():
    cfg = GoalPilotConfig.recommended()
    payload = json.loads(json.dumps(cfg.to_dict()))
    assert payload == cfg.to_dict()
    assert payload["action_mode"] == ACTION_MODE_SHARE


def test_replace_is_non_mutating():
    base = GoalPilotConfig()
    derived = base.replace(action_mode=ACTION_MODE_SHARE)
    assert base.action_mode == ACTION_MODE_MAGNITUDE
    assert derived.action_mode == ACTION_MODE_SHARE


# ------------------------------------------------------------------- paths ------------

def test_project_root_auto_detected(project_root):
    detected = detect_project_root(Path(project_root) / "tests")
    assert detected == Path(project_root).resolve()


def test_paths_resolve_from_a_nested_directory(project_root, monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)
    paths = ProjectPaths.resolve(Path(project_root) / "tests")
    assert paths.root == Path(project_root).resolve()
    assert paths.rl_prototype.is_dir()


def test_env_var_overrides_detection(project_root, monkeypatch):
    monkeypatch.setenv(ENV_VAR, str(project_root))
    paths = ProjectPaths.resolve()
    assert paths.root == Path(project_root).resolve()
    assert paths.source == f"${ENV_VAR}"


def test_expected_paths_exist(project_root):
    paths = ProjectPaths.resolve(project_root)
    assert paths.rl_profiles_csv.is_file()
    assert paths.rl_goals_csv.is_file()
    assert paths.rl_market_csv.is_file()
    assert paths.rl_split_csv.is_file()
    assert paths.ppo_best_model.is_file()
    assert paths.extension.is_dir()


def test_no_hard_coded_colab_path_in_resolved_paths(project_root):
    """.resolve() must never fall back to /content/drive when a local root exists."""
    paths = ProjectPaths.resolve(project_root)
    assert "/content/drive" not in str(paths.root)


def test_missing_root_raises(monkeypatch, tmp_path):
    monkeypatch.setenv(ENV_VAR, str(tmp_path / "definitely-not-here"))
    with pytest.raises(FileNotFoundError):
        ProjectPaths.resolve(allow_colab=False)


def test_ensure_output_dirs_and_sys_path(project_root):
    paths = ProjectPaths.resolve(project_root).ensure_output_dirs()
    assert paths.evaluation_out.is_dir()
    assert paths.plots_out.is_dir()
    import sys
    paths.add_to_sys_path()
    assert str(paths.rl_prototype) in sys.path
