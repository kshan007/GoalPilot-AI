"""Environment-agnostic path resolution for GoalPilot AI (finding F-12).

The archived notebook hard-coded `Path("/content/drive/MyDrive/GoalPilot_AI/…")` in roughly
forty places and called `drive.mount()` unconditionally, so the project could only run in
Google Colab.

This module resolves the project root in this order:

1. `GOALPILOT_PROJECT_ROOT` environment variable, if set.
2. An explicit `--project-root` / `project_root=` argument.
3. Local auto-detection: walk up from this file looking for a directory that contains
   the marker files below. Works for a plain checkout on any OS.
4. Colab fallback: `/content/drive/MyDrive/GoalPilot_AI`, mounting Drive only if it exists
   and is not already mounted.

Usage
-----
    from goalpilot_paths import ProjectPaths
    paths = ProjectPaths.resolve()          # or ProjectPaths.resolve("/some/root")
    paths.rl_prototype, paths.evaluation_out, paths.audit_out

    import goalpilot_env as ge
    ge.GoalPilotEnv(profiles, goals, market)   # data paths come from paths.rl_prototype
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

# A directory is treated as the project root when every one of these exists.
ROOT_MARKERS: tuple[str, ...] = (
    "simulation",
    "optimization",
    "GoalPilot_MultiGoal_Extension",
)

COLAB_ROOT = Path("/content/drive/MyDrive/GoalPilot_AI")
ENV_VAR = "GOALPILOT_PROJECT_ROOT"


def _has_markers(candidate: Path) -> bool:
    try:
        return all((candidate / m).exists() for m in ROOT_MARKERS)
    except OSError:
        return False


def _walk_up(start: Path) -> Iterable[Path]:
    current = start.resolve()
    for parent in [current, *current.parents]:
        yield parent


def detect_project_root(start: Path | None = None) -> Path | None:
    """Return the first ancestor of `start` that looks like the GoalPilot project root."""
    start = start or Path(__file__).resolve().parent
    for candidate in _walk_up(start):
        if _has_markers(candidate):
            return candidate
    return None


def _try_mount_colab() -> None:
    """Mount Google Drive when running in Colab. No-op everywhere else."""
    try:
        from google.colab import drive  # type: ignore
    except Exception:
        return
    if Path("/content/drive/MyDrive").exists():
        return
    try:
        drive.mount("/content/drive")
    except Exception:
        return


@dataclass(frozen=True)
class ProjectPaths:
    """Resolved filesystem locations used across the project."""

    root: Path
    source: str = "unknown"

    # ---- construction ----------------------------------------------------------------

    @classmethod
    def resolve(cls, project_root: str | Path | None = None,
                *, allow_colab: bool = True) -> "ProjectPaths":
        root: Path | None = None
        source = "argument"


        def _normalise(candidate: Path | None, label: str) -> tuple[Path | None, str]:
            """Accept either the root itself or any directory inside it."""
            if candidate is None:
                return None, label
            candidate = Path(candidate).expanduser()
            try:
                candidate = candidate.resolve()
            except OSError:
                return candidate, label
            if _has_markers(candidate):
                return candidate, label
            ancestor = detect_project_root(candidate)
            if ancestor is not None:
                return ancestor, f"{label} (found by walking up)"
            return candidate, label          # kept so the validation below reports it

        if project_root is not None:
            root, source = _normalise(Path(project_root), "argument")
        else:
            env_value = os.environ.get(ENV_VAR)
            if env_value:
                root, source = _normalise(Path(env_value), f"${ENV_VAR}")
            else:
                detected = detect_project_root()
                if detected is not None:
                    root, source = detected, "auto-detect"

        if root is None and allow_colab:
            _try_mount_colab()
            if COLAB_ROOT.exists() and _has_markers(COLAB_ROOT):
                root, source = COLAB_ROOT, "colab"

        if root is None:
            raise FileNotFoundError(
                "Could not resolve the GoalPilot project root.\n"
                f"  Set the {ENV_VAR} environment variable, or pass project_root=..., "
                "or run from inside the project directory.\n"
                f"  Looked for a directory containing {', '.join(ROOT_MARKERS)}."
            )

        root = root.resolve()
        if not root.exists():
            raise FileNotFoundError(
                f"Resolved project root does not exist: {root} (source: {source})"
            )
        if not _has_markers(root):
            missing = [m for m in ROOT_MARKERS if not (root / m).exists()]
            raise FileNotFoundError(
                f"{root} (source: {source}) is not a GoalPilot project root; "
                f"missing: {', '.join(missing)}"
            )

        return cls(root=root, source=source)

    # ---- derived locations -----------------------------------------------------------

    @property
    def simulation(self) -> Path:
        return self.root / "simulation"

    @property
    def optimization(self) -> Path:
        return self.root / "optimization"

    @property
    def extension(self) -> Path:
        return self.root / "GoalPilot_MultiGoal_Extension"

    @property
    def rl_prototype(self) -> Path:
        return self.simulation / "05_simulation_runs" / "rl_prototype"

    @property
    def models(self) -> Path:
        return self.rl_prototype / "models"

    @property
    def training_logs(self) -> Path:
        return self.rl_prototype / "training_logs"

    # ---- new, versioned output areas --------------------------------------------------

    @property
    def outputs(self) -> Path:
        return self.root / "outputs"

    @property
    def evaluation_out(self) -> Path:
        return self.outputs / "evaluation"

    @property
    def audit_out(self) -> Path:
        return self.outputs / "audit"

    @property
    def plots_out(self) -> Path:
        return self.outputs / "plots"

    @property
    def audit_tools(self) -> Path:
        return self.root / "audit_tools"

    # ---- data files used by the RL prototype -----------------------------------------

    @property
    def rl_profiles_csv(self) -> Path:
        return self.rl_prototype / "rl_sample_financial_profiles.csv"

    @property
    def rl_goals_csv(self) -> Path:
        return self.rl_prototype / "rl_sample_goals.csv"

    @property
    def rl_market_csv(self) -> Path:
        return self.rl_prototype / "rl_market_credit_validated.csv"

    @property
    def rl_split_csv(self) -> Path:
        return self.rl_prototype / "rl_train_test_user_split.csv"

    @property
    def ppo_best_model(self) -> Path:
        return self.models / "best_ppo" / "best_model.zip"

    @property
    def ppo_final_model(self) -> Path:
        return self.models / "goalpilot_ppo_50000.zip"

    # ---- helpers ---------------------------------------------------------------------

    def ensure_output_dirs(self) -> "ProjectPaths":
        for directory in (self.outputs, self.evaluation_out, self.audit_out, self.plots_out):
            directory.mkdir(parents=True, exist_ok=True)
        return self

    def add_to_sys_path(self) -> "ProjectPaths":
        """Make `goalpilot_env`, `goalpilot_config`, `goalpilot_paths` importable."""
        for candidate in (self.root, self.rl_prototype):
            entry = str(candidate)
            if entry not in sys.path:
                sys.path.insert(0, entry)
        return self

    def describe(self) -> str:
        return (
            f"GoalPilotPaths(root={self.root}, source={self.source}, "
            f"rl_prototype={self.rl_prototype})"
        )


if __name__ == "__main__":
    p = ProjectPaths.resolve().ensure_output_dirs()
    print(p.describe())
    for name in ("simulation", "optimization", "extension", "rl_prototype", "models",
                 "evaluation_out", "plots_out"):
        print(f"  {name:16s} exists={getattr(p, name).exists()}  {getattr(p, name)}")
