import importlib
import sys

mods = ["numpy", "pandas", "scipy", "sklearn", "statsmodels", "matplotlib", "seaborn",
        "plotly", "gymnasium", "stable_baselines3", "sb3_contrib", "torch", "tensorboard",
        "pytest", "nbformat", "nbconvert", "pulp"]
print("python==" + sys.version.split()[0])
for m in mods:
    try:
        mod = importlib.import_module(m)
        print(f"{m}=={getattr(mod, '__version__', 'unknown')}")
    except Exception as exc:  # noqa: BLE001
        print(f"{m}==UNAVAILABLE ({type(exc).__name__})")
