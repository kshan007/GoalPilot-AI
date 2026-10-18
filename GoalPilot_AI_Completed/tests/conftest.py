"""Shared pytest fixtures for the GoalPilot AI test suite."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RL_DIR = PROJECT_ROOT / "simulation" / "05_simulation_runs" / "rl_prototype"

for entry in (str(PROJECT_ROOT), str(RL_DIR)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

ARCHIVED_ENV = PROJECT_ROOT / "archive" / "goalpilot_env_archived_20261010.py"


def _load_module_from_path(path: Path, name: str):
    """Load a module from an arbitrary path, including non-`.py` extensions."""
    from importlib.machinery import SourceFileLoader

    loader = SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def project_root() -> Path:
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def rl_dir() -> Path:
    return RL_DIR


@pytest.fixture(scope="session")
def archived_env_module():
    """The environment exactly as it shipped on 2026-10-10 (backup copy)."""
    if not ARCHIVED_ENV.exists():
        pytest.skip(f"archived environment backup not present: {ARCHIVED_ENV}")
    return _load_module_from_path(ARCHIVED_ENV, "archived_goalpilot_env")


@pytest.fixture(scope="session")
def rl_data(rl_dir):
    profiles = pd.read_csv(rl_dir / "rl_sample_financial_profiles.csv")
    goals = pd.read_csv(rl_dir / "rl_sample_goals.csv")
    market = pd.read_csv(rl_dir / "rl_market_credit_validated.csv")
    split = pd.read_csv(rl_dir / "rl_train_test_user_split.csv")
    return {"profiles": profiles, "goals": goals, "market": market, "split": split}


@pytest.fixture(scope="session")
def all_user_ids(rl_data):
    return rl_data["profiles"]["user_id"].astype(str).tolist()


@pytest.fixture(scope="session")
def small_slice(rl_data):
    """A 6-user slice: keeps the fast tests genuinely fast."""
    ids = rl_data["profiles"]["user_id"].astype(str).head(6).tolist()
    return {
        "profiles": rl_data["profiles"][rl_data["profiles"]["user_id"].isin(ids)].copy(),
        "goals": rl_data["goals"][rl_data["goals"]["user_id"].isin(ids)].copy(),
        "market": rl_data["market"].copy(),
        "user_ids": ids,
    }
