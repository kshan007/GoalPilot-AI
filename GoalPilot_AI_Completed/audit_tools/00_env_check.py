"""Environment + dependency availability probe for GoalPilot AI."""
import importlib
import platform
import shutil
import subprocess
import sys

def main():
    print("=" * 72)
    print("ENVIRONMENT")
    print("=" * 72)
    print(f"python          : {sys.version.split()[0]}")
    print(f"executable      : {sys.executable}")
    print(f"platform        : {platform.platform()}")
    print(f"processor       : {platform.processor()}")
    print(f"machine         : {platform.machine()}")
    print(f"cpu_count       : {__import__('os').cpu_count()}")
    try:
        import psutil
        vm = psutil.virtual_memory()
        print(f"ram_total_gb    : {vm.total/1e9:.2f}")
        print(f"ram_avail_gb    : {vm.available/1e9:.2f}")
    except Exception as e:
        print(f"ram             : psutil unavailable ({type(e).__name__})")

    # GPU
    try:
        import torch
        print(f"cuda_available  : {torch.cuda.is_available()}")
        print(f"cuda_device_cnt : {torch.cuda.device_count()}")
        if torch.cuda.is_available():
            print(f"cuda_device     : {torch.cuda.get_device_name(0)}")
        print(f"mps_available   : {getattr(torch.backends, 'mps', None) and torch.backends.mps.is_available()}")
    except Exception as e:
        print(f"torch           : FAILED {type(e).__name__}: {e}")

    mods = [
        "numpy", "pandas", "scipy", "sklearn", "statsmodels",
        "matplotlib", "seaborn", "plotly",
        "gymnasium", "gym", "stable_baselines3", "sb3_contrib",
        "torch", "tensorboard", "pulp", "cvxpy", "pyomo",
        "yaml", "tqdm", "pytest", "nbformat", "nbconvert",
        "jupyter_client", "jupyter_core", "ipykernel", "psutil",
    ]
    print()
    print("=" * 72)
    print("DEPENDENCIES")
    print("=" * 72)
    missing = []
    for m in mods:
        try:
            mod = importlib.import_module(m)
            ver = getattr(mod, "__version__", "?")
            print(f"OK    {m:20s} {ver}")
        except Exception as e:
            missing.append(m)
            print(f"MISS  {m:20s} {type(e).__name__}: {str(e)[:60]}")

    print()
    print("=" * 72)
    print("MISSING SUMMARY")
    print("=" * 72)
    print("missing:", ", ".join(missing) if missing else "(none)")
    for exe in ["git", "pip", "jupyter", "python"]:
        print(f"exe {exe:10s}: {shutil.which(exe)}")

if __name__ == "__main__":
    main()
