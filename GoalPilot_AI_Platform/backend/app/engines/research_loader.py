"""Read-only bridge to the GoalPilot AI research project.

Nothing in the research tree is ever written to. This module only:

* locates ``GoalPilot_AI_Completed`` (env var -> walk-up -> sibling),
* puts the two directories the research modules import from onto ``sys.path``,
* imports the model modules lazily and caches them,
* exposes the shared data artefacts (market path, benchmark population, checkpoints).

Lazy import matters: importing ``goalpilot_env`` pulls in torch via stable-baselines3
downstream, and no request should pay that cost unless it is actually an RL request.
"""
from __future__ import annotations

import importlib
import json
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

from app.config import get_settings

_LOCK = threading.Lock()
_CACHE: dict[str, Any] = {}

# Relative to the research root.
MULTIGOAL_SRC_REL = Path("GoalPilot_MultiGoal_Extension")
RL_PROTOTYPE_REL = Path("simulation/05_simulation_runs/rl_prototype")
MARKET_REL = RL_PROTOTYPE_REL / "rl_market_credit_validated.csv"
SAMPLE_PROFILES_REL = RL_PROTOTYPE_REL / "rl_sample_financial_profiles.csv"
SAMPLE_GOALS_REL = RL_PROTOTYPE_REL / "rl_sample_goals.csv"
SPLIT_REL = RL_PROTOTYPE_REL / "rl_train_test_user_split.csv"
POPULATION_REL = Path("GoalPilot_MultiGoal_Extension/data/multigoal_financial_profiles.csv")
POPULATION_GOALS_REL = Path("GoalPilot_MultiGoal_Extension/data/synthetic_multigoal_input.csv")
SAMPLE_STATE_REL = Path("GoalPilot_MultiGoal_Extension/data/sample_financial_state.json")
SAMPLE_GOALS_CSV_REL = Path("GoalPilot_MultiGoal_Extension/data/sample_goals.csv")
CPI_REL = Path("GoalPilot_MultiGoal_Extension/data/cpi_historical_calibration.csv")
EXPERIMENTS_REL = Path("training_logs/experiments")
V8_SUMMARY_REL = Path("outputs/evaluation/final_validation_v8/ppo_v8_summary.csv")
V7_SUMMARY_REL = Path("outputs/evaluation/final_validation_v7/constrained_lp_summary_v1.csv")


class ResearchUnavailable(RuntimeError):
    """Raised when the research tree cannot be reached or a module will not import."""


def research_root() -> Path:
    settings = get_settings()
    root = settings.research_path
    if root is None or not root.is_dir():
        raise ResearchUnavailable(
            "The GoalPilot AI research project could not be located. Set "
            "GOALPILOT_RESEARCH_PATH to the GoalPilot_AI_Completed directory."
        )
    return root


def is_available() -> bool:
    try:
        research_root()
        return True
    except ResearchUnavailable:
        return False


def data_path(relative: Path) -> Path:
    root = research_root()
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:  # pragma: no cover - defensive
        raise ResearchUnavailable(f"Path escapes the research root: {relative}") from exc
    return candidate


def _ensure_import_paths() -> None:
    root = research_root()
    for rel in (MULTIGOAL_SRC_REL, RL_PROTOTYPE_REL):
        directory = str((root / rel).resolve())
        if directory not in sys.path:
            sys.path.insert(0, directory)


def load_module(key: str, module_name: str) -> ModuleType:
    """Import (once) and cache a research module by name."""
    with _LOCK:
        if key in _CACHE:
            return _CACHE[key]
        _ensure_import_paths()
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:  # pragma: no cover - environment dependent
            raise ResearchUnavailable(
                f"Could not import research module '{module_name}': {exc}"
            ) from exc
        # `goalpilot_constrained_lp` does `from src.multi_goal_optimizer import ...`,
        # so a bare `multi_goal_optimizer` import can land as a second, distinct module
        # object. Re-bind it to the package-qualified one so isinstance/dataclass checks
        # never see two copies of FinancialState.
        if module_name == "goalpilot_constrained_lp":
            try:
                canonical = importlib.import_module("src.multi_goal_optimizer")
                sys.modules.setdefault("multi_goal_optimizer", canonical)
            except Exception:  # pragma: no cover
                pass
        _CACHE[key] = module
        return module


# --------------------------------------------------------------------------------------
# model modules
# --------------------------------------------------------------------------------------
def optimizer_module() -> ModuleType:
    """`multi_goal_optimizer`: optimize_multi_goal, prepare_goals, FinancialState, ...

    Imported as ``src.multi_goal_optimizer`` — that is the only name it is importable under,
    because ``goalpilot_constrained_lp`` does ``from src.multi_goal_optimizer import ...``.
    Using one import name guarantees a single module object, so ``FinancialState`` passed
    into the constrained solver is always the very class it validates.
    """
    module = load_module("mgo", "src.multi_goal_optimizer")
    sys.modules.setdefault("multi_goal_optimizer", module)
    return module


def constrained_lp_module() -> ModuleType:
    return load_module("clp", "goalpilot_constrained_lp")


def config_module() -> ModuleType:
    return load_module("gpc", "goalpilot_config")


def env_module() -> ModuleType:
    return load_module("gpe", "goalpilot_env")


def knowledge_module() -> ModuleType:
    return load_module("gpk", "goalpilot_knowledge")


# --------------------------------------------------------------------------------------
# data
# --------------------------------------------------------------------------------------
def market_frame():
    """The shared monthly market/credit path used by every arm."""
    import pandas as pd

    return pd.read_csv(data_path(MARKET_REL))


def benchmark_profiles(limit: int | None = None):
    import pandas as pd

    df = pd.read_csv(data_path(SAMPLE_PROFILES_REL))
    return df.head(limit) if limit else df


def benchmark_goals(limit_users: int | None = None):
    import pandas as pd

    df = pd.read_csv(data_path(SAMPLE_GOALS_REL))
    if limit_users is None:
        return df
    keep = df["user_id"].drop_duplicates().head(limit_users).tolist()
    return df[df["user_id"].isin(keep)]


def benchmark_split():
    import pandas as pd

    return pd.read_csv(data_path(SPLIT_REL))


def sample_financial_state() -> dict[str, Any]:
    return json.loads(data_path(SAMPLE_STATE_REL).read_text(encoding="utf-8"))


def sample_goals_frame():
    import pandas as pd

    return pd.read_csv(data_path(SAMPLE_GOALS_CSV_REL))


def cpi_calibration():
    import pandas as pd

    return pd.read_csv(data_path(CPI_REL))


def population_profiles(limit: int | None = None):
    import pandas as pd

    df = pd.read_csv(data_path(POPULATION_REL))
    return df.head(limit) if limit else df


def population_goals(limit_users: int | None = None):
    import pandas as pd

    df = pd.read_csv(data_path(POPULATION_GOALS_REL))
    if limit_users is None:
        return df
    keep = df["user_id"].drop_duplicates().head(limit_users).tolist()
    return df[df["user_id"].isin(keep)]


def list_checkpoints() -> list[dict[str, Any]]:
    """Every PPO checkpoint in the research tree, with its family and seed."""
    try:
        root = data_path(EXPERIMENTS_REL)
    except ResearchUnavailable:
        return []
    if not root.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*.zip")):
        rel = path.relative_to(research_root()).as_posix()
        parts = path.relative_to(root).parts
        out.append(
            {
                "path": rel,
                "file": path.name,
                "family": parts[0] if parts else "",
                "variant": parts[1] if len(parts) > 1 else "",
                "seed": _seed_from_name(path.name),
                "size_bytes": path.stat().st_size,
            }
        )
    return out


def _seed_from_name(name: str) -> int | None:
    for token in name.replace("-", "_").split("_"):
        if token.isdigit():
            return int(token)
    return None


def evaluation_summary() -> dict[str, Any]:
    """The recorded v8/v7 held-out results, read from the research CSVs. These are the
    numbers the platform reports as *research* results — never re-derived by the app."""
    import pandas as pd

    out: dict[str, Any] = {"available": False}
    try:
        v8 = data_path(V8_SUMMARY_REL)
        if v8.is_file():
            out["v8"] = pd.read_csv(v8).to_dict(orient="records")
            out["available"] = True
        v7 = data_path(V7_SUMMARY_REL)
        if v7.is_file():
            out["v7"] = pd.read_csv(v7).to_dict(orient="records")
            out["available"] = True
    except ResearchUnavailable:
        return {"available": False}
    return out


def clear_cache() -> None:
    with _LOCK:
        _CACHE.clear()


@dataclass
class ResearchStatus:
    available: bool
    root: str | None
    modules: dict[str, bool]
    checkpoint_count: int
    message: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "root": self.root,
            "modules": self.modules,
            "checkpoint_count": self.checkpoint_count,
            "message": self.message,
        }


def status() -> ResearchStatus:
    try:
        root = research_root()
    except ResearchUnavailable as exc:
        return ResearchStatus(False, None, {}, 0, str(exc))
    modules: dict[str, bool] = {}
    for key, name in (
        ("multi_goal_optimizer", "src.multi_goal_optimizer"),
        ("goalpilot_constrained_lp", "goalpilot_constrained_lp"),
        ("goalpilot_config", "goalpilot_config"),
        ("goalpilot_env", "goalpilot_env"),
    ):
        try:
            load_module(f"probe_{key}", name)
            modules[key] = True
        except ResearchUnavailable:
            modules[key] = False
    return ResearchStatus(True, str(root), modules, len(list_checkpoints()))
