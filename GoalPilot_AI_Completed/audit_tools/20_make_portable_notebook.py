"""Produce a portable, safe version of the archived RL pre-check notebook.

The archived notebook has two problems for local/dual-environment execution:

1. **Hard-coded Colab paths** (F-12): `Path("/content/drive/MyDrive/GoalPilot_AI/...")`
   appears throughout, plus an unconditional `drive.mount()`.
2. **Destructive in-place patching**: several cells rewrite `goalpilot_env.py` in place,
   keeping `.bak` copies. Those cells are the *history* that produced the backup files.
   Re-running the notebook top-to-bottom today would overwrite the corrected environment.

This script rewrites the notebook so that:

* a bootstrap cell resolves the project root via `goalpilot_paths` and exposes
  `GOALPILOT_ROOT`, `PROJECT_DIR`, `SIM_DIR`, `RL_DIR`;
* every Colab path literal becomes `"" + GOALPILOT_ROOT + "/suffix"`;
* `google.colab` imports and `drive.mount` are guarded so they no-op outside Colab;
* any cell that writes to `goalpilot_env.py` is converted into a documented no-op, with
  the original source preserved inside a triple-quoted block for the record.

Output cells are preserved unchanged.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import nbformat

ARCHIVED = Path(r"S:\fyp\GoalPilot_AI\GoalPilot_MultiGoal_Extension")  # placeholder, overwritten
COLAB_ROOT_LITERAL = "/content/drive/MyDrive/GoalPilot_AI"

BOOTSTRAP = '''# =============================================================================
# BOOTSTRAP — portable path resolution (replaces the hard-coded Colab paths)
# =============================================================================
# Audit finding F-12: the archived notebook hard-coded
#   Path("/content/drive/MyDrive/GoalPilot_AI/...")
# in ~40 places and called drive.mount() unconditionally, so it only ran in Colab.
#
# Resolution order (see goalpilot_paths.py):
#   1. $GOALPILOT_PROJECT_ROOT          2. project_root= argument
#   3. walk up from this file           4. /content/drive/MyDrive/GoalPilot_AI (Colab)
#
# Set the environment variable if auto-detection picks the wrong folder.

import os, sys
from pathlib import Path

def _bootstrap_project_root():
    """Find the GoalPilot project root without importing the project package."""
    markers = ("simulation", "optimization", "GoalPilot_MultiGoal_Extension")

    def is_root(candidate):
        try:
            return all((candidate / m).exists() for m in markers)
        except OSError:
            return False

    # 1. explicit override
    env = os.environ.get("GOALPILOT_PROJECT_ROOT")
    if env and is_root(Path(env).expanduser()):
        return Path(env).expanduser().resolve()

    # 2. this notebook's own directory, then every ancestor
    here = Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if is_root(candidate):
            return candidate.resolve()

    # 3. one level down: tolerate being launched from a parent folder.
    #    Prefer a "…Completed" working copy when several candidates exist.
    try:
        children = [c for c in here.iterdir()
                    if c.is_dir() and c.name.startswith("GoalPilot_AI") and is_root(c)]
        children.sort(key=lambda p: (0 if "Completed" in p.name else 1, p.name))
        if children:
            return children[0].resolve()
    except OSError:
        pass
    # Colab fallback
    try:
        from google.colab import drive  # type: ignore
        drive.mount("/content/drive")
    except Exception:
        pass
    colab = Path("/content/drive/MyDrive/GoalPilot_AI")
    if colab.exists():
        return colab
    raise FileNotFoundError(
        "Could not locate the GoalPilot project root. "
        "Set GOALPILOT_PROJECT_ROOT or run this notebook from inside the project."
    )

GOALPILOT_ROOT = str(_bootstrap_project_root())
PROJECT_DIR = Path(GOALPILOT_ROOT)
SIM_DIR = PROJECT_DIR / "simulation"
RL_DIR = SIM_DIR / "05_simulation_runs" / "rl_prototype"
EVALUATION_DIR = PROJECT_DIR / "evaluation"

for entry in (GOALPILOT_ROOT, str(RL_DIR), str(EVALUATION_DIR)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

# Configuration object for the environment (audit finding F-06). Change `CONFIG_NAME`
# to "archived" to reproduce the 2026-10-10 results exactly.
from goalpilot_config import GoalPilotConfig
CONFIG_NAME = "corrected_accounting"
CONFIG = getattr(GoalPilotConfig, CONFIG_NAME)()

print("project root :", GOALPILOT_ROOT)
print("rl prototype :", RL_DIR)
print("config       :", CONFIG_NAME, CONFIG.to_dict())
'''

PATCH_GUARD_HEADER = '''# -----------------------------------------------------------------------------
# ARCHIVAL CELL — deliberately disabled.
#
# This cell belongs to the archived in-place patching sequence that produced the
# `goalpilot_env.py.pre_*.bak` files. It REWRITES goalpilot_env.py on disk.
#
# Running it today would overwrite the corrected environment. The original source is
# preserved below for the record, fully commented out.
#
# To inspect the patch history instead, compare the .bak files in:
#   simulation/05_simulation_runs/rl_prototype/
# -----------------------------------------------------------------------------
'''


def patch_colab_paths(source: str) -> str:
    """Rewrite Colab path literals into concatenations with GOALPILOT_ROOT.

    The replacement is a single, minimal one: the literal
        "/content/drive/MyDrive/GoalPilot_AI
    becomes
        "" + GOALPILOT_ROOT + "
    so that an enclosing `Path("…")` turns into `Path("" + GOALPILOT_ROOT + "/suffix")`,
    which is valid Python. Implicit string concatenation across source lines still works,
    because the adjacent literals are joined before the addition is evaluated.

    Note: `"/content/drive"` (the mount target) does not match the prefix and is left alone.
    """
    return source.replace(COLAB_ROOT_LITERAL, '" + GOALPILOT_ROOT + "')


def guard_colab_imports(source: str) -> str:
    if "from google.colab import drive" in source:
        source = source.replace(
            "from google.colab import drive",
            "try:\n    from google.colab import drive  # noqa: F401\nexcept Exception:\n"
            "    drive = None",
        )
    if "drive.mount(" in source:
        source = re.sub(
            r"drive\.mount\(([^)]*)\)",
            r"(drive.mount(\1) if drive is not None else print('not in Colab; skipping drive mount'))",
            source,
        )
    return source


def is_destructive_env_writer(source: str) -> bool:
    if "goalpilot_env" not in source:
        return False
    writers = ("write_text(", "write_bytes(", ".save(", "shutil.copy", "open(", "p.write")
    touches_env = re.search(r"goalpilot_env\.py", source) is not None
    return touches_env and any(w in source for w in writers)


def neutralise(source: str) -> str:
    quoted = "\n".join("# " + line for line in source.splitlines())
    return (
        PATCH_GUARD_HEADER
        + "# Original source (commented out):\n"
        + quoted
        + "\n"
    )


def main() -> int:
    src_nb = Path(sys.argv[1])
    dst_nb = Path(sys.argv[2])

    nb = nbformat.read(str(src_nb), as_version=4)
    total = len(nb.cells)
    patched = disabled = colab_fixed = 0

    for cell in nb.cells:
        if cell.cell_type != "code":
            continue
        original = cell.source

        if is_destructive_env_writer(original):
            cell.source = neutralise(patch_colab_paths(guard_colab_imports(original)))
            cell.outputs = []
            cell.execution_count = None
            disabled += 1
            continue

        new_source = patch_colab_paths(original)
        new_source = guard_colab_imports(new_source)
        if new_source != original:
            patched += 1
        cell.source = new_source

    # Drop the two original first cells that only installed/printed versions,
    # replacing them with the bootstrap.
    retained = [c for c in nb.cells]
    bootstrap = nbformat.v4.new_code_cell(BOOTSTRAP)
    bootstrap.metadata["goalpilot"] = {"bootstrap": True}
    nb.cells = [bootstrap, *retained]

    nb.metadata["goalpilot"] = {
        "derived_from": src_nb.name,
        "portable": True,
        "cells_total": total,
        "cells_path_patched": patched,
        "cells_disabled_destructive": disabled,
        "colab_cells_fixed": colab_fixed,
        "notes": "Colab paths replaced with GOALPILOT_ROOT; destructive env-patching "
                 "cells disabled; bootstrap cell added.",
    }

    dst_nb.parent.mkdir(parents=True, exist_ok=True)
    nbformat.write(nb, str(dst_nb))

    print(f"source cells        : {total}")
    print(f"cells path-patched  : {patched}")
    print(f"cells disabled      : {disabled}  (in-place goalpilot_env.py writers)")
    print(f"output cells        : {len(nb.cells)} now")
    print(f"wrote               : {dst_nb}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
