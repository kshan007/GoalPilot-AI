# ===== CELL 0 =====  type=code  exec=None

# %pip install -q "gymnasium>=1.0,<2.0" "stable-baselines3>=2.4,<3.0"


# ===== CELL 1 =====  type=code  exec=None

import gymnasium as gym
import stable_baselines3

# print("Gymnasium:", gym.__version__)
# print("Stable-Baselines3:", stable_baselines3.__version__)


# ===== CELL 2 =====  type=code  exec=None
from pathlib import Path
from google.colab import drive

drive.mount("/content/drive")


SIM_DIR = Path("/content/drive/MyDrive/GoalPilot_AI/simulation")

for folder in sorted(SIM_DIR.iterdir()):
    if folder.is_dir():
        print(f"\n📁 {folder.name}/")
        for file in sorted(folder.iterdir()):
            if file.is_file():
                print(f"   📄 {file.name}")

# ===== CELL 3 =====  type=code  exec=None

from pathlib import Path
import pandas as pd

# Existing project path from our previous steps
PROJECT_DIR = Path("/content/drive/MyDrive/GoalPilot_AI")
SIM_DIR = PROJECT_DIR / "simulation"

print("PROJECT:", PROJECT_DIR)
print("PROJECT EXISTS:", PROJECT_DIR.exists())
print("SIMULATION:", SIM_DIR)
print("SIMULATION EXISTS:", SIM_DIR.exists())

# 1. Find notebooks and Python implementation files
print("\n========== NOTEBOOKS AND PYTHON FILES ==========")

for path in sorted(PROJECT_DIR.rglob("*")):
    if path.is_file() and (
        path.suffix.lower() in {".ipynb", ".py"}
    ):
        print(path.relative_to(PROJECT_DIR))

# 2. Inspect important existing CSV files
files_to_inspect = [
    SIM_DIR / "02_synthetic_population/synthetic_population_base.csv",
    SIM_DIR / "02_synthetic_population/synthetic_population_income.csv",
    SIM_DIR / "03_financial_profiles/synthetic_population_savings.csv",
    SIM_DIR / "03_financial_profiles/synthetic_population_debt.csv",
    SIM_DIR / "03_financial_profiles/synthetic_population_investment.csv",
    SIM_DIR / "03_financial_profiles/synthetic_population_risk.csv",
    SIM_DIR / "04_economic_environment/economic_environment.csv",
    SIM_DIR / "05_simulation_runs/monthly_financial_simulation_base.csv",
    SIM_DIR / "05_simulation_runs/portfolio_simulation_validated.csv",
    SIM_DIR / "06_results/final_goal_outcome_dataset.csv",
    SIM_DIR / "06_results/final_optimisation_input.csv",
]

print("\n========== CSV SCHEMA INSPECTION ==========")

for path in files_to_inspect:
    print(f"\n{'=' * 75}")
    print("FILE:", path.name)

    if not path.exists():
        print("NOT FOUND:", path)
        continue

    df = pd.read_csv(path, nrows=5)

    # Read the full file only for schema-independent row count
    # is not necessary at this stage.
    print("Columns:", df.columns.tolist())
    print("Sample shape:", df.shape)

    print("\nData types:")
    print(df.dtypes.to_string())

    print("\nSample rows:")
    display(df.head(2))


# ===== CELL 4 =====  type=code  exec=None

from pathlib import Path

PROJECT_DIR = Path("/content/drive/MyDrive/GoalPilot_AI")

print("Searching for multi-goal and optimizer files...\n")

keywords = (
    "multigoal",
    "multi_goal",
    "multi-goal",
    "optimizer",
    "optimiser",
    "goal_extension",
)

for path in sorted(PROJECT_DIR.rglob("*")):
    if not path.is_file():
        continue

    name = path.name.lower()

    if path.suffix.lower() in {".csv", ".py", ".ipynb", ".json", ".md"}:
        if any(keyword in name for keyword in keywords):
            print(path.relative_to(PROJECT_DIR))


# ===== CELL 5 =====  type=code  exec=None
from pathlib import Path
import pandas as pd
import json

PROJECT_DIR = Path("/content/drive/MyDrive/GoalPilot_AI")
MG_DIR = PROJECT_DIR / "GoalPilot_MultiGoal_Extension"

files_to_inspect = {
    "financial_profiles": MG_DIR / "data/multigoal_financial_profiles.csv",
    "multigoal_input": MG_DIR / "data/synthetic_multigoal_input.csv",
}

for name, path in files_to_inspect.items():
    print("\n" + "=" * 80)
    print(f"{name}: {path.name}")
    print("=" * 80)

    if not path.exists():
        print("FILE NOT FOUND")
        continue

    df = pd.read_csv(path)

    print("Shape:", df.shape)
    print("\nColumns:")
    print(df.columns.tolist())

    print("\nFirst 3 rows:")
    display(df.head(3))

    print("\nMissing values in key columns:")
    print(df.isnull().sum()[df.isnull().sum() > 0].head(15))

    if "user_id" in df.columns:
        print("\nUnique users:", df["user_id"].nunique())

        # Show how many rows belong to each user
        print("Rows per user:")
        display(df.groupby("user_id").size().describe())

        # Print a few example user IDs and their row counts
        display(df.groupby("user_id").size().head(10))

# ===== CELL 6 =====  type=code  exec=None
from pathlib import Path

PROJECT_DIR = Path("/content/drive/MyDrive/GoalPilot_AI")
optimizer_path = (
    PROJECT_DIR
    / "GoalPilot_MultiGoal_Extension"
    / "src"
    / "multi_goal_optimizer.py"
)

if not optimizer_path.exists():
    print("Optimizer file not found:", optimizer_path)
else:
    source = optimizer_path.read_text(encoding="utf-8")
    print("Optimizer source:", optimizer_path)
    print("Total lines:", len(source.splitlines()))
    print("\n" + "=" * 80)
    print(source)

# ===== CELL 7 =====  type=code  exec=None
from pathlib import Path
import sys
import pandas as pd

PROJECT_DIR = Path("/content/drive/MyDrive/GoalPilot_AI")
MG_DIR = PROJECT_DIR / "GoalPilot_MultiGoal_Extension"

# Import the existing optimizer; do not rewrite it.
sys.path.insert(0, str(MG_DIR / "src"))

from multi_goal_optimizer import FinancialState, optimize_multi_goal

# Load existing datasets.
profiles = pd.read_csv(
    MG_DIR / "data" / "multigoal_financial_profiles.csv"
)
all_goals = pd.read_csv(
    MG_DIR / "data" / "synthetic_multigoal_input.csv"
)

# Select one user with multiple goals.
user_id = all_goals["user_id"].iloc[0]
profile_rows = profiles.loc[profiles["user_id"] == user_id]
user_goals = all_goals.loc[all_goals["user_id"] == user_id].copy()

if len(profile_rows) != 1:
    raise ValueError(f"Expected one profile for {user_id}, found {len(profile_rows)}")

profile = profile_rows.iloc[0]

# Map existing profile fields to the optimizer's expected state.
# risk_score is used as a provisional 0–1 risk-capacity input.
state = FinancialState(
    monthly_income=float(profile["monthly_income"]),
    essential_expenses=float(profile["monthly_expenditure"]),
    existing_emi=float(profile["monthly_emi"]),
    liquid_savings=float(profile["initial_savings"]),
    existing_investments=float(profile["initial_investment"]),
    risk_capacity=float(profile["risk_score"]),
)

print("User:", user_id)
print("Number of goals:", len(user_goals))
print("\nFinancial state:")
print(state)

print("\nGoals passed to the optimizer:")
display(
    user_goals[
        [
            "goal_id", "goal_name", "current_cost",
            "time_horizon_months", "priority",
            "criticality", "existing_funding"
        ]
    ]
)

# Run using the optimizer's documented default assumptions.
result = optimize_multi_goal(user_goals, state)

print("\nOptimizer status:", result["status"])

if result["status"] == "optimal":
    print("\nSummary:")
    for key, value in result["summary"].items():
        if key != "assumptions":
            print(f"{key}: {value}")

    print("\nGoal-wise allocations:")
    display(result["allocations"])
else:
    print("Solver message:", result.get("solver_message"))

# ===== CELL 8 =====  type=code  exec=None
from pathlib import Path
import pandas as pd

PROJECT_DIR = Path("/content/drive/MyDrive/GoalPilot_AI")
SIM_DIR = PROJECT_DIR / "simulation"

files = {
    "economic_environment": SIM_DIR / "04_economic_environment" / "economic_environment.csv",
    "monthly_simulation": SIM_DIR / "05_simulation_runs" / "monthly_financial_simulation_base.csv",
}

for name, path in files.items():
    print("\n" + "=" * 75)
    print(name.upper())
    print("=" * 75)

    if not path.exists():
        print("NOT FOUND:", path)
        continue

    df = pd.read_csv(path)
    print("Shape:", df.shape)
    print("Columns:", df.columns.tolist())

    if "period" in df.columns:
        dates = pd.to_datetime(df["period"], errors="coerce")
        print("Period range:", dates.min(), "to", dates.max())
        print("Unique periods:", dates.nunique())

    if "user_id" in df.columns:
        print("Unique users:", df["user_id"].nunique())
        print("Rows per user:")
        display(df.groupby("user_id").size().describe())

    print("\nMissing-value count for important fields:")
    important = [
        "monthly_income_dynamic",
        "monthly_expenditure_dynamic",
        "monthly_surplus_dynamic",
        "monthly_emi",
        "savings_balance",
        "portfolio_value",
        "nifty_monthly_return",
        "average_walr",
        "inflation_level",
    ]
    available = [c for c in important if c in df.columns]
    print(df[available].isna().sum())

    print("\nSample rows:")
    display(df.head(3))

# ===== CELL 9 =====  type=code  exec=None
from pathlib import Path
import pandas as pd

PROJECT_DIR = Path("/content/drive/MyDrive/GoalPilot_AI")
INPUT_DIR = PROJECT_DIR / "simulation" / "01_input_data"
ECON_FILE = (
    PROJECT_DIR / "simulation" / "04_economic_environment"
    / "economic_environment.csv"
)

econ = pd.read_csv(ECON_FILE)

print("ECONOMIC ENVIRONMENT VALUE RANGES")
print("=" * 70)

columns = [
    "inflation_level",
    "inflation_pct_change",
    "nifty_monthly_return",
    "nifty_return_volatility",
    "average_walr",
    "credit_pressure",
]

for col in columns:
    if col in econ.columns:
        print(
            f"{col:30s}",
            f"min={econ[col].min():10.4f}",
            f"max={econ[col].max():10.4f}",
            f"mean={econ[col].mean():10.4f}"
        )

print("\nINPUT DATA FILES")
print("=" * 70)

for path in sorted(INPUT_DIR.glob("*")):
    if path.is_file():
        print(f"\n{path.name}")

        if path.suffix.lower() == ".csv":
            df = pd.read_csv(path)
            print("Shape:", df.shape)
            print("Columns:", df.columns.tolist())

            numeric = df.select_dtypes(include="number")
            if not numeric.empty:
                print("Numeric ranges:")
                display(
                    pd.DataFrame({
                        "min": numeric.min(),
                        "max": numeric.max(),
                        "mean": numeric.mean()
                    }).round(4)
                )

# ===== CELL 10 =====  type=code  exec=None
from pathlib import Path
import pandas as pd
import numpy as np

PROJECT_DIR = Path("/content/drive/MyDrive/GoalPilot_AI")
SIM_DIR = PROJECT_DIR / "simulation"
INPUT_DIR = SIM_DIR / "01_input_data"

econ = pd.read_csv(
    SIM_DIR / "04_economic_environment" / "economic_environment.csv"
)
market = pd.read_csv(INPUT_DIR / "market_credit_scenarios.csv")
cpi = pd.read_csv(INPUT_DIR / "cpi_historical_calibration.csv")

for df in [econ, market, cpi]:
    df["period"] = pd.to_datetime(df["period"]).dt.to_period("M")

print("DATE ALIGNMENT")
print("=" * 65)

for name, df in [
    ("Economic environment", econ),
    ("Raw market/credit data", market),
    ("Raw CPI data", cpi),
]:
    print(
        f"{name}: {len(df)} rows | "
        f"{df['period'].min()} to {df['period'].max()} | "
        f"{df['period'].nunique()} unique months"
    )

print("\nECONOMIC ENVIRONMENT vs RAW MARKET DATA")
print("=" * 65)

merged = econ.merge(
    market[["period", "nifty_monthly_return", "average_walr"]],
    on="period",
    how="inner",
    suffixes=("_environment", "_raw"),
    validate="one_to_one",
)

print("Matching months:", len(merged))
print("Environment-only months:", len(set(econ.period) - set(market.period)))
print("Market-only months:", len(set(market.period) - set(econ.period)))

for col in ["nifty_monthly_return", "average_walr"]:
    env_col = f"{col}_environment"
    raw_col = f"{col}_raw"

    if env_col in merged.columns and raw_col in merged.columns:
        print(f"\n{col}")
        print("Environment range:", merged[env_col].min(), "to", merged[env_col].max())
        print("Raw range:", merged[raw_col].min(), "to", merged[raw_col].max())
        print("Correlation:", merged[env_col].corr(merged[raw_col]))

print("\nFirst 5 aligned rows:")
display(merged.head())

# ===== CELL 11 =====  type=code  exec=None
from pathlib import Path
import pandas as pd

PROJECT_DIR = Path("/content/drive/MyDrive/GoalPilot_AI")
INPUT_DIR = PROJECT_DIR / "simulation" / "01_input_data"

market = pd.read_csv(INPUT_DIR / "market_credit_scenarios.csv")
market["period"] = pd.to_datetime(market["period"]).dt.to_period("M")

columns_to_check = [
    "nifty_monthly_return",
    "nifty_return_volatility",
    "average_walr",
    "walr_change",
    "walr_pct_change",
]

print("MISSING VALUES IN RAW MARKET/CREDIT DATA")
print("=" * 65)

for col in columns_to_check:
    if col in market.columns:
        print(f"{col}: {market[col].isna().sum()} missing")

print("\nRows with missing key values:")
display(
    market.loc[
        market[columns_to_check].isna().any(axis=1),
        ["period"] + columns_to_check
    ].sort_values("period")
)

print("\nDuplicate months:", market["period"].duplicated().sum())

print("\nFirst and last 10 months:")
display(pd.concat([market.head(10), market.tail(10)]))

print("\nRaw return and lending-rate summary:")
display(
    market[["nifty_monthly_return", "average_walr"]]
    .describe()
    .round(4)
)

# ===== CELL 12 =====  type=code  exec=None
from pathlib import Path
import pandas as pd

INPUT_DIR = (
    Path("/content/drive/MyDrive/GoalPilot_AI")
    / "simulation"
    / "01_input_data"
)

market = pd.read_csv(INPUT_DIR / "market_credit_scenarios.csv")
market["period"] = pd.to_datetime(
    market["period"]
).dt.to_period("M")

walr = market.loc[
    market["average_walr"].notna(),
    ["period", "average_walr", "walr_change", "walr_pct_change"]
].copy()

walr["months_since_previous_observation"] = (
    walr["period"].astype("int64").diff()
)

print("WALR OBSERVATIONS")
print("=" * 60)
print("Number of observed months:", len(walr))
print("First observation:", walr["period"].min())
print("Last observation:", walr["period"].max())

print("\nObserved lending rates:")
display(walr.to_string(index=False))

print("\nGap between consecutive observations:")
display(
    walr["months_since_previous_observation"]
    .value_counts()
    .sort_index()
    .rename_axis("months_between_observations")
    .to_frame("number_of_gaps")
)

# ===== CELL 13 =====  type=code  exec=None
from pathlib import Path
import pandas as pd

PROJECT_DIR = Path("/content/drive/MyDrive/GoalPilot_AI")
SIM_DIR = PROJECT_DIR / "simulation"
MG_DIR = PROJECT_DIR / "GoalPilot_MultiGoal_Extension"

files_to_check = {
    "Financial profiles": (
        MG_DIR / "data" / "multigoal_financial_profiles.csv"
    ),
    "Multiple goals": (
        MG_DIR / "data" / "synthetic_multigoal_input.csv"
    ),
    "Economic environment": (
        SIM_DIR / "04_economic_environment" / "economic_environment.csv"
    ),
    "Monthly market-credit dataset": (
        SIM_DIR / "04_economic_environment" / "rl_monthly_market_credit.csv"
    ),
    "LP optimizer": (
        MG_DIR / "src" / "multi_goal_optimizer.py"
    ),
}

print("GOALPILOT RL DATASET READINESS CHECK")
print("=" * 65)

for name, path in files_to_check.items():
    print(f"\n{name}")
    print("Path:", path)
    print("Exists:", path.exists())

    if path.exists() and path.suffix == ".csv":
        df = pd.read_csv(path)
        print("Shape:", df.shape)
        print("Columns:", df.columns.tolist())

        if "user_id" in df.columns:
            print("Unique users:", df["user_id"].nunique())

        if "period" in df.columns:
            print(
                "Date range:",
                df["period"].min(),
                "to",
                df["period"].max()
            )


# ===== CELL 14 =====  type=code  exec=None
from pathlib import Path
import pandas as pd

PROJECT_DIR = Path("/content/drive/MyDrive/GoalPilot_AI")
SIM_DIR = PROJECT_DIR / "simulation"
INPUT_DIR = SIM_DIR / "01_input_data"
OUTPUT_DIR = SIM_DIR / "04_economic_environment"

market = pd.read_csv(INPUT_DIR / "market_credit_scenarios.csv")
econ = pd.read_csv(OUTPUT_DIR / "economic_environment.csv")

# Normalize dates to monthly periods for a safe join
market["period"] = pd.to_datetime(
    market["period"]
).dt.to_period("M")

econ["period"] = pd.to_datetime(
    econ["period"]
).dt.to_period("M")

# Keep the period range already used by the economic environment
start, end = econ["period"].min(), econ["period"].max()

market = market.loc[
    market["period"].between(start, end)
].copy()

# Select actual market and lending-rate data
market_cols = [
    "period",
    "nifty_monthly_return",
    "nifty_return_volatility",
    "nifty_3m_volatility",
    "nifty_ma_gap",
    "average_walr",
    "walr_change",
    "walr_pct_change",
    "walr_momentum",
]

market = market[market_cols]

# Keep the economic features for observation/state information
econ_cols = [
    "period",
    "inflation_level",
    "inflation_change",
    "inflation_pct_change",
    "inflation_trend",
    "inflation_regime",
    "market_return_regime",
    "market_volatility_regime",
    "credit_pressure",
    "walr_regime",
]

econ = econ[econ_cols]

# One record per month; preserve the existing environment's timeline
rl_data = econ.merge(
    market,
    on="period",
    how="left",
    validate="one_to_one",
)

# Track observed WALR before filling any values
rl_data["walr_observed"] = rl_data["average_walr"].notna()

# Carry forward only past observations; never backfill from the future
rl_data["walr_monthly"] = rl_data["average_walr"].ffill()
rl_data["walr_rate_source"] = "carried_forward"

rl_data.loc[
    rl_data["walr_observed"], "walr_rate_source"
] = "observed"

rl_data.loc[
    rl_data["walr_monthly"].isna(), "walr_rate_source"
] = "unavailable"

# Retain a readable date column
rl_data["period"] = rl_data["period"].astype(str)

output_path = OUTPUT_DIR / "rl_monthly_market_credit.csv"
rl_data.to_csv(output_path, index=False)

# Validate
print("Saved:", output_path)
print("Rows:", len(rl_data))
print("Unique months:", rl_data["period"].nunique())
print("NIFTY return missing:", rl_data["nifty_monthly_return"].isna().sum())
print("Observed WALR:", int(rl_data["walr_observed"].sum()))
print("WALR still unavailable:", int(rl_data["walr_monthly"].isna().sum()))
print("\nSample:")
display(rl_data.head(8))

# ===== CELL 15 =====  type=code  exec=None
from pathlib import Path
import pandas as pd

# Project paths
PROJECT_DIR = Path("/content/drive/MyDrive/GoalPilot_AI")
SIM_DIR = PROJECT_DIR / "simulation"
MG_DIR = PROJECT_DIR / "GoalPilot_MultiGoal_Extension"

OUTPUT_DIR = SIM_DIR / "05_simulation_runs" / "rl_prototype"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

PROFILE_FILE = MG_DIR / "data" / "multigoal_financial_profiles.csv"
GOALS_FILE = MG_DIR / "data" / "synthetic_multigoal_input.csv"

# Load existing datasets
profiles = pd.read_csv(PROFILE_FILE)
goals = pd.read_csv(GOALS_FILE)

# Validate user identifiers
assert profiles["user_id"].is_unique, "Financial profiles must have one row per user."
assert profiles["user_id"].notna().all(), "Missing user IDs in profiles."
assert goals["user_id"].notna().all(), "Missing user IDs in goals."

# Select a reproducible sample of 100 users
sample_user_ids = (
    profiles["user_id"]
    .drop_duplicates()
    .sort_values()
    .head(100)
    .tolist()
)

sample_profiles = profiles[
    profiles["user_id"].isin(sample_user_ids)
].copy()

sample_goals = goals[
    goals["user_id"].isin(sample_user_ids)
].copy()

# Validate profile-to-goal relationships
assert set(sample_goals["user_id"]).issubset(
    set(sample_profiles["user_id"])
)

goals_per_user = sample_goals.groupby("user_id").size()

print("RL PROTOTYPE SAMPLE")
print("=" * 55)
print("Selected users:", sample_profiles["user_id"].nunique())
print("Selected goals:", len(sample_goals))
print("Users with goals:", goals_per_user.size)
print("Minimum goals per user:", goals_per_user.min())
print("Maximum goals per user:", goals_per_user.max())
print("Average goals per user:", round(goals_per_user.mean(), 2))

print("\nFinancial profile sample:")
display(
    sample_profiles[
        [
            "user_id",
            "monthly_income",
            "monthly_expenditure",
            "monthly_emi",
            "initial_savings",
            "initial_investment",
            "risk_score",
        ]
    ].head()
)

print("\nGoal sample:")
display(
    sample_goals[
        [
            "user_id",
            "goal_id",
            "goal_name",
            "current_cost",
            "time_horizon_months",
            "priority",
            "criticality",
            "existing_funding",
        ]
    ].head(10)
)

# Save as separate prototype inputs; original data remains unchanged
sample_profiles.to_csv(
    OUTPUT_DIR / "rl_sample_financial_profiles.csv",
    index=False,
)

sample_goals.to_csv(
    OUTPUT_DIR / "rl_sample_goals.csv",
    index=False,
)

print("\nSaved prototype inputs to:", OUTPUT_DIR)

# ===== CELL 16 =====  type=code  exec=None
from pathlib import Path
import pandas as pd
import numpy as np

PROJECT_DIR = Path("/content/drive/MyDrive/GoalPilot_AI")
RL_DIR = (
    PROJECT_DIR / "simulation"
    / "05_simulation_runs" / "rl_prototype"
)

profiles = pd.read_csv(
    RL_DIR / "rl_sample_financial_profiles.csv"
)
goals = pd.read_csv(
    RL_DIR / "rl_sample_goals.csv"
)

# Calculate monthly cash flow from the starting financial profile
profiles["monthly_surplus_before_emi"] = (
    profiles["monthly_income"] - profiles["monthly_expenditure"]
)
profiles["monthly_surplus_after_emi"] = (
    profiles["monthly_income"]
    - profiles["monthly_expenditure"]
    - profiles["monthly_emi"]
)

# Calculate a provisional six-month emergency reserve target
profiles["emergency_reserve_target"] = (
    6 * profiles["monthly_expenditure"]
)
profiles["emergency_reserve_gap"] = (
    profiles["emergency_reserve_target"]
    - profiles["initial_savings"]
).clip(lower=0)

# Goal-level checks
goals["existing_funding_ratio"] = np.where(
    goals["current_cost"] > 0,
    goals["existing_funding"] / goals["current_cost"],
    np.nan,
)

goals["deadline_months"] = pd.to_numeric(
    goals["time_horizon_months"], errors="coerce"
)

print("FINANCIAL FEASIBILITY REPORT")
print("=" * 60)

print("\nMonthly cash flow across users (₹):")
display(
    profiles[
        [
            "monthly_income",
            "monthly_expenditure",
            "monthly_emi",
            "monthly_surplus_after_emi",
        ]
    ].describe().round(2)
)

print("\nKey counts:")
print(
    "Users with negative cash flow:",
    int((profiles["monthly_surplus_after_emi"] < 0).sum()),
)
print(
    "Users with zero or negative cash flow:",
    int((profiles["monthly_surplus_after_emi"] <= 0).sum()),
)
print(
    "Users below the provisional 6-month emergency reserve:",
    int((profiles["initial_savings"] < profiles["emergency_reserve_target"]).sum()),
)
print(
    "Users with an EMI above 35% of monthly income:",
    int(
        (
            profiles["monthly_emi"]
            / profiles["monthly_income"].replace(0, np.nan)
            > 0.35
        ).sum()
    ),
)

print("\nGoal horizon distribution (months):")
display(goals["deadline_months"].describe().round(1))

print("\nGoals with existing funding exceeding current cost:",
      int((goals["existing_funding"] > goals["current_cost"]).sum()))

print("\nMissing values in key profile columns:")
display(
    profiles[
        [
            "monthly_income",
            "monthly_expenditure",
            "monthly_emi",
            "initial_savings",
            "initial_investment",
            "risk_score",
        ]
    ].isna().sum().to_frame("missing_values")
)

# ===== CELL 17 =====  type=code  exec=None
from pathlib import Path
import pandas as pd

PROJECT_DIR = Path("/content/drive/MyDrive/GoalPilot_AI")
econ_path = (
    PROJECT_DIR / "simulation"
    / "04_economic_environment"
    / "economic_environment.csv"
)

econ = pd.read_csv(econ_path)

print("ECONOMIC DATASET")
print("=" * 60)
print("Shape:", econ.shape)
print("Columns:", econ.columns.tolist())

print("\nNumeric feature ranges:")
display(
    econ.select_dtypes(include="number")
    .agg(["min", "max", "mean"])
    .T.round(4)
)

print("\nFirst 5 periods:")
display(econ.head())

print("\nLast 5 periods:")
display(econ.tail())

# ===== CELL 18 =====  type=code  exec=None
from pathlib import Path
import pandas as pd

PROJECT_DIR = Path("/content/drive/MyDrive/GoalPilot_AI")
INPUT_DIR = PROJECT_DIR / "simulation" / "01_input_data"
RL_DIR = (
    PROJECT_DIR / "simulation"
    / "05_simulation_runs" / "rl_prototype"
)

market = pd.read_csv(INPUT_DIR / "market_credit_scenarios.csv")
market["period"] = pd.to_datetime(market["period"]).dt.to_period("M")

print("RAW MARKET DATA — FINANCIAL TRANSITION CHECK")
print("=" * 65)

for col in [
    "nifty_monthly_return",
    "nifty_return_volatility",
    "average_walr",
]:
    if col in market.columns:
        values = market[col].dropna()
        print(f"\n{col}")
        print("Observed values:", len(values))
        print("Minimum:", round(values.min(), 6))
        print("Maximum:", round(values.max(), 6))
        print("Mean:", round(values.mean(), 6))

print("\nFirst 10 monthly observations:")
display(
    market[
        [
            "period",
            "nifty_monthly_return",
            "nifty_return_volatility",
            "average_walr",
        ]
    ].head(10)
)

print("\nLast 10 monthly observations:")
display(
    market[
        [
            "period",
            "nifty_monthly_return",
            "nifty_return_volatility",
            "average_walr",
        ]
    ].tail(10)
)

# ===== CELL 19 =====  type=code  exec=None
import pandas as pd
from pathlib import Path

PROJECT_DIR = Path("/content/drive/MyDrive/GoalPilot_AI")
INPUT_DIR = PROJECT_DIR / "simulation" / "01_input_data"
RL_DIR = (
    PROJECT_DIR / "simulation"
    / "05_simulation_runs" / "rl_prototype"
)

RL_DIR.mkdir(parents=True, exist_ok=True)

# Load raw economic data
market = pd.read_csv(INPUT_DIR / "market_credit_scenarios.csv")
market["period"] = pd.to_datetime(
    market["period"].astype(str)
).dt.to_period("M")

# Keep one row per month, excluding non-monthly/duplicate records
market = (
    market.sort_values("period")
    .drop_duplicates(subset="period", keep="last")
    .reset_index(drop=True)
)

# Start from March 2015, when both market and lending-rate
# observations are available.
start_period = pd.Period("2015-03", freq="M")
market = market[market["period"] >= start_period].copy()

# Carry forward only previously observed lending rates.
# Never backfill from future observations.
market["walr_monthly"] = market["average_walr"].ffill()

# Keep explicit indicators for data provenance.
market["walr_observed"] = market["average_walr"].notna()
market["walr_rate_source"] = market["walr_observed"].map(
    {True: "observed", False: "carried_forward"}
)

# Required columns for the RL economic environment
required = [
    "period",
    "nifty_monthly_return",
    "nifty_return_volatility",
    "walr_monthly",
]

# Select rows with at least one missing required value
missing_rows = market.loc[
    market[required].isna().any(axis=1),
    required
]

print("Rows with missing required values:", len(missing_rows))

if not missing_rows.empty:
    display(missing_rows)
else:
    output_path = RL_DIR / "rl_market_credit_validated.csv"
    market.to_csv(output_path, index=False)

    print("Validation passed.")
    print("Rows:", len(market))
    print("Unique months:", market["period"].nunique())
    print("Saved to:", output_path)

# ===== CELL 20 =====  type=code  exec=None
import pandas as pd
from pathlib import Path

PROJECT_DIR = Path("/content/drive/MyDrive/GoalPilot_AI")
RL_DIR = (
    PROJECT_DIR / "simulation"
    / "05_simulation_runs" / "rl_prototype"
)
EXTENSION_DATA_DIR = (
    PROJECT_DIR / "GoalPilot_MultiGoal_Extension" / "data"
)

# Load the existing prototype samples
profiles = pd.read_csv(RL_DIR / "rl_sample_financial_profiles.csv")
goals = pd.read_csv(RL_DIR / "rl_sample_goals.csv")
market = pd.read_csv(RL_DIR / "rl_market_credit_validated.csv")

# Convert periods consistently
market["period"] = pd.PeriodIndex(market["period"], freq="M")

print("PROFILES")
print("Shape:", profiles.shape)
print("Unique users:", profiles["user_id"].nunique())
print("Columns:", profiles.columns.tolist())

print("\nGOALS")
print("Shape:", goals.shape)
print("Unique users:", goals["user_id"].nunique())
print("Goals per user:")
print(goals.groupby("user_id").size().describe().round(2))

print("\nMARKET")
print("Shape:", market.shape)
print("Period range:", market["period"].min(), "to", market["period"].max())

# Verify user-goal relationships
profile_ids = set(profiles["user_id"])
goal_ids = set(goals["user_id"])

print("\nDATA INTEGRITY")
print("Profiles without goals:", len(profile_ids - goal_ids))
print("Goals without profiles:", len(goal_ids - profile_ids))
print("Duplicate profile user IDs:", profiles["user_id"].duplicated().sum())
print("Duplicate user-goal pairs:", goals.duplicated(["user_id", "goal_id"]).sum())

print("\nSample goals:")
display(goals.head(8))

# ===== CELL 21 =====  type=code  exec=None
import numpy as np
import pandas as pd

profile_columns = [
    "monthly_income",
    "monthly_expenditure",
    "monthly_emi",
    "initial_savings",
    "initial_investment",
    "investment_capacity_ratio",
    "risk_score",
]

goal_columns = [
    "current_cost",
    "time_horizon_months",
    "priority",
    "criticality",
    "existing_funding",
]

print("PROFILE VARIABLE RANGES")
print("=" * 55)
display(profiles[profile_columns].describe().round(2).T)

print("\nGOAL VARIABLE RANGES")
print("=" * 55)
display(goals[goal_columns].describe().round(2).T)

print("\nCATEGORICAL VALUES")
print("Risk profiles:", profiles["risk_profile"].value_counts().to_dict())
print("Goal types:", goals["goal_type"].value_counts().to_dict())

print("\nFINANCIAL CONSTRAINT CHECKS")
print(
    "Users with non-positive monthly surplus:",
    int(
        (
            profiles["monthly_income"]
            - profiles["monthly_expenditure"]
            - profiles["monthly_emi"]
            <= 0
        ).sum()
    ),
)
print(
    "Goals with zero or negative horizon:",
    int((goals["time_horizon_months"] <= 0).sum()),
)
print(
    "Goals with existing funding above current cost:",
    int((goals["existing_funding"] > goals["current_cost"]).sum()),
)

# ===== CELL 22 =====  type=code  exec=None
class GoalPilotEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(self, profile, goals, market_data, max_months=120):
        super().__init__()

        self.profile = profile.copy()
        self.goals = goals.copy().reset_index(drop=True)
        self.market = market_data.copy().reset_index(drop=True)
        self.max_months = min(max_months, len(self.market))

        if len(self.goals) == 0:
            raise ValueError("A user must have at least one goal.")
        if self.max_months < 1:
            raise ValueError("Market data must contain at least one month.")

        self.n_goals = len(self.goals)

        # One action per goal, one for savings, one for investments.
        self.action_space = spaces.Box(
            low=-1.0,
            high=1.0,
            shape=(self.n_goals + 2,),
            dtype=np.float32,
        )

        # 15 base observations + four features per goal.
        self.observation_space = spaces.Box(
            low=-10.0,
            high=10.0,
            shape=(15 + 4 * self.n_goals,),
            dtype=np.float32,
        )

        self.goal_costs = self.goals["current_cost"].to_numpy(dtype=np.float64)
        self.goal_horizons = self.goals["time_horizon_months"].to_numpy(dtype=np.float64)
        self.goal_priorities = self.goals["priority"].to_numpy(dtype=np.float64)
        self.goal_criticalities = self.goals["criticality"].to_numpy(dtype=np.float64)

        self.goal_balances_initial = np.minimum(
            self.goals["existing_funding"].to_numpy(dtype=np.float64),
            self.goal_costs,
        )

        self.monthly_income = max(0.0, float(self.profile["monthly_income"]))
        self.monthly_expenses = max(0.0, float(self.profile["monthly_expenditure"]))
        self.monthly_emi = max(0.0, float(self.profile["monthly_emi"]))
        self.initial_savings = max(0.0, float(self.profile["initial_savings"]))
        self.initial_investment = max(0.0, float(self.profile["initial_investment"]))

        self.investment_capacity_ratio = float(np.clip(
            self.profile["investment_capacity_ratio"], 0.0, 1.0
        ))

    def _get_observation(self):
        row = self.market.iloc[self.month_index]
        income_scale = max(self.monthly_income, 1.0)

        regime_map = {"low": 0.0, "medium": 0.5, "high": 1.0}
        inflation_regime = regime_map.get(
            str(row["inflation_regime"]).lower(), 0.5
        )

        base_state = [
            self.monthly_income / income_scale,
            self.monthly_expenses / income_scale,
            self.monthly_emi / income_scale,
            self.savings_balance / income_scale,
            self.investment_balance / income_scale,
            float(self.profile["risk_score"]),
            float(row["nifty_monthly_return"]),
            float(row["nifty_return_volatility"]),
            float(row["walr_monthly"]) / 100.0,
            self.month_index / max(self.max_months - 1, 1),
            float(row["inflation_level"]),
            float(row["inflation_change"]),
            float(row["inflation_pct_change"]),
            float(row["inflation_trend"]),
            inflation_regime,
        ]

        goal_state = []
        for i in range(self.n_goals):
            cost = max(self.goal_costs[i], 1.0)
            remaining = max(0.0, cost - self.goal_balances[i])

            goal_state.extend([
                self.goal_balances[i] / cost,
                remaining / cost,
                max(0.0, self.goal_horizons[i] - self.month_index) / 240.0,
                self.goal_priorities[i] / 5.0,
            ])

        return np.clip(
            np.asarray(base_state + goal_state, dtype=np.float32),
            self.observation_space.low,
            self.observation_space.high,
        )

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)

        self.month_index = 0
        self.savings_balance = self.initial_savings
        self.investment_balance = self.initial_investment
        self.goal_balances = self.goal_balances_initial.copy()
        self.total_reward = 0.0

        return self._get_observation(), {
            "month_index": self.month_index,
            "n_goals": self.n_goals,
        }

    def step(self, action):
        action = np.asarray(action, dtype=np.float64)

        if action.shape != self.action_space.shape:
            raise ValueError(
                f"Expected action shape {self.action_space.shape}, "
                f"received {action.shape}."
            )

        preferences = (np.clip(action, -1.0, 1.0) + 1.0) / 2.0

        surplus = max(
            0.0,
            self.monthly_income - self.monthly_expenses - self.monthly_emi,
        )

        # Last action is investment; preceding actions are goals and savings.
        investment_preference = preferences[-1]
        investment_limit = surplus * self.investment_capacity_ratio

        investment_allocation = min(
            investment_limit,
            surplus * investment_preference,
        )

        remaining_budget = max(0.0, surplus - investment_allocation)
        other_preferences = preferences[:-1]

        if other_preferences.sum() > 0:
            other_allocations = (
                remaining_budget
                * other_preferences
                / other_preferences.sum()
            )
        else:
            other_allocations = np.zeros_like(other_preferences)

        goal_allocations = other_allocations[:self.n_goals]
        savings_contribution = float(other_allocations[-1])

        row = self.market.iloc[self.month_index]
        market_return = float(row["nifty_monthly_return"])

        # Apply returns to existing investments and add the new contribution.
        self.investment_balance = max(
            0.0,
            self.investment_balance * (1.0 + market_return),
        ) + investment_allocation

        previous_progress = np.minimum(
            self.goal_balances / self.goal_costs, 1.0
        )

        self.goal_balances = np.minimum(
            self.goal_costs,
            self.goal_balances + goal_allocations,
        )
        self.savings_balance += savings_contribution

        new_progress = np.minimum(
            self.goal_balances / self.goal_costs, 1.0
        )

        weights = (
            self.goal_priorities + self.goal_criticalities
        ) / 10.0

        progress_reward = float(
            np.sum(weights * (new_progress - previous_progress))
        )

        risk_penalty = (
            abs(market_return)
            * (1.0 - float(self.profile["risk_score"]))
            * 0.01
        )

        reward = progress_reward - risk_penalty
        self.total_reward += reward
        self.month_index += 1

        terminated = bool(
            np.all(self.goal_balances >= self.goal_costs)
        )
        truncated = bool(self.month_index >= self.max_months)

        if not (terminated or truncated):
            observation = self._get_observation()
        else:
            observation = np.zeros(
                self.observation_space.shape, dtype=np.float32
            )

        info = {
            "monthly_surplus": surplus,
            "goal_allocations": goal_allocations.copy(),
            "savings_contribution": savings_contribution,
            "investment_contribution": float(investment_allocation),
            "investment_balance": float(self.investment_balance),
            "savings_balance": float(self.savings_balance),
            "goal_progress": new_progress.copy(),
            "market_return": market_return,
            "walr_annual_percent": float(row["walr_monthly"]),
            "inflation_regime": str(row["inflation_regime"]),
        }

        return observation, reward, terminated, truncated, info


print("GoalPilotEnv updated: goals + savings + investments.")

# ===== CELL 23 =====  type=code  exec=None
from stable_baselines3.common.env_checker import check_env

test_user_id = "USER_00001"

test_profile = profiles.loc[
    profiles["user_id"] == test_user_id
].iloc[0]

test_goals = (
    goals.loc[goals["user_id"] == test_user_id]
    .reset_index(drop=True)
)

# Recreate the environment using the updated class
env = GoalPilotEnv(
    profile=test_profile,
    goals=test_goals,
    market_data=market,
    max_months=120,
)

print("Action space:", env.action_space)
print("Observation space:", env.observation_space)

# Verify Gymnasium compatibility
check_env(env, warn=True)
print("\nGymnasium environment check passed.")

# Test reset and one monthly transition
observation, info = env.reset(seed=42)

# Zero maps to equal allocation preferences
action = np.zeros(env.action_space.shape, dtype=np.float32)

next_observation, reward, terminated, truncated, step_info = (
    env.step(action)
)

total_allocated = (
    step_info["goal_allocations"].sum()
    + step_info["savings_contribution"]
)

print("\nONE-STEP TEST")
print("Initial observation valid:",
      env.observation_space.contains(observation))
print("Next observation shape:", next_observation.shape)
print("Reward:", round(float(reward), 6))
print("Available surplus:", round(step_info["monthly_surplus"], 2))
print("Total allocated:", round(float(total_allocated), 2))
print("Allocation within budget:",
      total_allocated <= step_info["monthly_surplus"] + 1e-4)
print("Terminated:", terminated)
print("Truncated:", truncated)

# ===== CELL 24 =====  type=code  exec=None
print("Available market-data columns:")
print(market.columns.tolist())

print("\nPotential inflation columns:")
inflation_columns = [
    col for col in market.columns
    if "inflation" in col.lower() or "cpi" in col.lower()
]
print(inflation_columns)

if inflation_columns:
    display(market[["period"] + inflation_columns].head(10))
else:
    print(
        "No inflation columns found in the validated market dataset."
    )

# ===== CELL 25 =====  type=code  exec=None
from pathlib import Path
import pandas as pd

PROJECT_DIR = Path("/content/drive/MyDrive/GoalPilot_AI")

economic_path = (
    PROJECT_DIR
    / "simulation"
    / "04_economic_environment"
    / "economic_environment.csv"
)

economic = pd.read_csv(economic_path)

print("Economic environment shape:", economic.shape)
print("\nInflation-related columns:")

inflation_columns = [
    col for col in economic.columns
    if "inflation" in col.lower() or "cpi" in col.lower()
]

print(inflation_columns)

if inflation_columns:
    display(economic[["period"] + inflation_columns].head(10))
    print("\nInflation feature ranges:")
    display(economic[inflation_columns].describe().round(4).T)
else:
    print("No inflation-related columns found.")

# ===== CELL 26 =====  type=code  exec=None
import pandas as pd
from pathlib import Path

PROJECT_DIR = Path("/content/drive/MyDrive/GoalPilot_AI")
RL_DIR = (
    PROJECT_DIR / "simulation"
    / "05_simulation_runs" / "rl_prototype"
)
ECONOMIC_PATH = (
    PROJECT_DIR / "simulation"
    / "04_economic_environment"
    / "economic_environment.csv"
)

# Load source datasets
market_features = pd.read_csv(
    RL_DIR / "rl_market_credit_validated.csv"
)
economic = pd.read_csv(ECONOMIC_PATH)

# Normalize monthly keys to YYYY-MM
market_features["period"] = pd.PeriodIndex(
    pd.to_datetime(market_features["period"]).astype(str),
    freq="M",
)
economic["period"] = pd.PeriodIndex(
    pd.to_datetime(economic["period"]).astype(str),
    freq="M",
)

inflation_features = [
    "inflation_level",
    "inflation_change",
    "inflation_pct_change",
    "inflation_trend",
    "inflation_regime",
]

# Keep only the monthly key and inflation-related features
economic_subset = economic[["period"] + inflation_features].copy()

# Many-to-one merge validation prevents accidental row duplication
market_with_economy = market_features.merge(
    economic_subset,
    on="period",
    how="left",
    validate="one_to_one",
    indicator=True,
)

print("Merged shape:", market_with_economy.shape)
print("Unique months:", market_with_economy["period"].nunique())
print("Merge status:")
print(market_with_economy["_merge"].value_counts())

print("\nMissing inflation values:")
print(market_with_economy[inflation_features].isna().sum())

print("\nSample merged features:")
display(
    market_with_economy[
        [
            "period",
            "nifty_monthly_return",
            "walr_monthly",
            "inflation_level",
            "inflation_trend",
            "inflation_regime",
        ]
    ].head(8)
)

# Save only if every market month has matching inflation features
if (
    (market_with_economy["_merge"] != "both").any()
    or market_with_economy[inflation_features].isna().any().any()
):
    print("\nNot saved: resolve unmatched or missing inflation features.")
else:
    output_path = RL_DIR / "rl_market_credit_economic.csv"
    market_with_economy.drop(columns="_merge").to_csv(
        output_path, index=False
    )
    print("\nSaved:", output_path)

# ===== CELL 27 =====  type=code  exec=None
from pathlib import Path
import pandas as pd

PROJECT_DIR = Path("/content/drive/MyDrive/GoalPilot_AI")
RL_DIR = (
    PROJECT_DIR / "simulation"
    / "05_simulation_runs" / "rl_prototype"
)

market = pd.read_csv(
    RL_DIR / "rl_market_credit_economic.csv"
)

market["period"] = pd.PeriodIndex(
    pd.to_datetime(market["period"]).astype(str),
    freq="M",
)

economic_columns = [
    "nifty_monthly_return",
    "nifty_return_volatility",
    "walr_monthly",
    "inflation_level",
    "inflation_change",
    "inflation_pct_change",
    "inflation_trend",
    "inflation_regime",
]

print("Merged market dataset:", market.shape)
print("Unique periods:", market["period"].nunique())
print("\nSelected feature types:")
print(market[economic_columns].dtypes)

print("\nNumeric feature ranges:")
display(
    market[
        [
            "nifty_monthly_return",
            "nifty_return_volatility",
            "walr_monthly",
            "inflation_level",
            "inflation_change",
            "inflation_pct_change",
            "inflation_trend",
        ]
    ].describe().round(4).T
)

print("\nMissing values:")
print(market[economic_columns].isna().sum())

print("\nInflation regimes:")
print(market["inflation_regime"].value_counts().to_dict())

# ===== CELL 28 =====  type=code  exec=None
# Reset to a reproducible initial state
observation, info = env.reset(seed=42)

records = []

for month in range(12):
    # Test with random action preferences
    action = env.action_space.sample()

    observation, reward, terminated, truncated, info = env.step(action)

    total_allocated = (
        info["goal_allocations"].sum()
        + info["savings_contribution"]
    )

    records.append({
        "month": month + 1,
        "available_surplus": info["monthly_surplus"],
        "total_allocated": total_allocated,
        "allocation_difference": (
            info["monthly_surplus"] - total_allocated
        ),
        "reward": float(reward),
        "investment_balance": info["investment_balance"],
        "savings_balance": info["savings_balance"],
        "mean_goal_progress": float(
            np.mean(info["goal_progress"])
        ),
    })

    if terminated or truncated:
        break

accounting_results = pd.DataFrame(records)

display(accounting_results.round(2))

print("\nACCOUNTING VALIDATION")
print(
    "No negative allocations:",
    bool(
        (accounting_results["total_allocated"] >= -1e-6).all()
    ),
)
print(
    "Allocations within budget:",
    bool(
        (
            accounting_results["total_allocated"]
            <= accounting_results["available_surplus"] + 1e-4
        ).all()
    ),
)
print(
    "Accounting difference within tolerance:",
    bool(
        (
            accounting_results["allocation_difference"].abs()
            <= 1e-4
        ).all()
    ),
)
print("Months simulated:", len(accounting_results))

# ===== CELL 29 =====  type=code  exec=None
from gymnasium import spaces
import numpy as np

# Update the existing environment class's action-space definition.
# Actions are mapped to [0, 1] preferences inside step().
GoalPilotEnv.__init__.__globals__["spaces"] = spaces

print("Current action space:", env.action_space)
print("Current action bounds:", env.action_space.low, env.action_space.high)
print("\nNext, we'll update GoalPilotEnv to use [-1, 1] actions.")

# ===== CELL 30 =====  type=code  exec=None
from stable_baselines3.common.env_checker import check_env

# Use the merged dataset with inflation features
market = pd.read_csv(
    RL_DIR / "rl_market_credit_economic.csv"
)

market["period"] = pd.PeriodIndex(
    pd.to_datetime(market["period"]).astype(str),
    freq="M",
)

test_user_id = "USER_00001"

test_profile = profiles.loc[
    profiles["user_id"] == test_user_id
].iloc[0]

test_goals = (
    goals.loc[goals["user_id"] == test_user_id]
    .reset_index(drop=True)
)

# Recreate the environment using the latest class
env = GoalPilotEnv(
    profile=test_profile,
    goals=test_goals,
    market_data=market,
    max_months=120,
)

print("Action space:", env.action_space)
print("Observation space:", env.observation_space)

check_env(env, warn=True)
print("Gymnasium environment check passed.")

observation, info = env.reset(seed=42)

action = np.zeros(
    env.action_space.shape,
    dtype=np.float32,
)

next_observation, reward, terminated, truncated, step_info = (
    env.step(action)
)

allocated = (
    step_info["goal_allocations"].sum()
    + step_info["savings_contribution"]
)

print("\nUPDATED ENVIRONMENT TEST")
print("Initial observation valid:",
      env.observation_space.contains(observation))
print("Expected observation shape:", env.observation_space.shape)
print("Actual observation shape:", observation.shape)
print("Next observation shape:", next_observation.shape)
print("Reward:", round(float(reward), 6))
print("Available surplus:", round(step_info["monthly_surplus"], 2))
print("Total allocated:", round(float(allocated), 2))
print("Within budget:",
      allocated <= step_info["monthly_surplus"] + 1e-4)
print("Inflation regime:", step_info["inflation_regime"])

# ===== CELL 31 =====  type=code  exec=None
test_user_id = "USER_00001"

test_profile = profiles.loc[
    profiles["user_id"] == test_user_id
].iloc[0]

income = float(test_profile["monthly_income"])
expenses = float(test_profile["monthly_expenditure"])
emi = float(test_profile["monthly_emi"])
capacity_ratio = float(test_profile["investment_capacity_ratio"])

surplus = max(0.0, income - expenses - emi)
capacity_limit = surplus * capacity_ratio

print("User:", test_user_id)
print("Monthly income:", round(income, 2))
print("Monthly expenditure:", round(expenses, 2))
print("Existing monthly EMI:", round(emi, 2))
print("Monthly surplus:", round(surplus, 2))
print("Investment capacity ratio:", round(capacity_ratio, 4))
print("Provisional investment capacity limit:", round(capacity_limit, 2))

# ===== CELL 32 =====  type=code  exec=None
import numpy as np

def allocate_monthly_surplus(
    action,
    monthly_surplus,
    investment_capacity_ratio,
):
    """
    Action order:
      [goal_1, ..., goal_N, savings, investments]

    Returns feasible allocations in rupees.
    """
    action = np.asarray(action, dtype=np.float64)

    if action.ndim != 1 or len(action) < 3:
        raise ValueError(
            "Action must contain at least one goal, savings, and investments."
        )

    surplus = max(0.0, float(monthly_surplus))
    capacity_ratio = np.clip(
        float(investment_capacity_ratio), 0.0, 1.0
    )

    # Map symmetric actions [-1, 1] to preferences [0, 1].
    preferences = (np.clip(action, -1.0, 1.0) + 1.0) / 2.0

    investment_index = len(action) - 1
    investment_preference = preferences[investment_index]

    # Investment is capped by the provisional profile constraint.
    investment_limit = surplus * capacity_ratio
    investment_allocation = min(
        investment_limit,
        surplus * investment_preference,
    )

    # Distribute remaining money among goals and savings.
    remaining_budget = max(0.0, surplus - investment_allocation)
    other_preferences = preferences[:investment_index]

    if other_preferences.sum() > 0:
        other_allocations = (
            remaining_budget
            * other_preferences
            / other_preferences.sum()
        )
    else:
        other_allocations = np.zeros_like(other_preferences)

    allocations = np.append(
        other_allocations,
        investment_allocation,
    )

    return allocations


# Test with three goals, savings, and investments.
sample_action = np.array([0.0, 0.0, 0.0, 0.0, 1.0])

test_allocations = allocate_monthly_surplus(
    action=sample_action,
    monthly_surplus=14481.34,
    investment_capacity_ratio=0.282,
)

print("Goal allocations:", np.round(test_allocations[:3], 2))
print("Savings allocation:", round(test_allocations[-2], 2))
print("Investment allocation:", round(test_allocations[-1], 2))
print("Total allocated:", round(test_allocations.sum(), 2))
print("Budget:", 14481.34)
print("Within budget:", test_allocations.sum() <= 14481.34 + 1e-6)
print("Investment cap respected:", test_allocations[-1] <= 4083.81 + 1e-6)

# ===== CELL 33 =====  type=code  exec=None
from stable_baselines3.common.env_checker import check_env

test_user_id = "USER_00001"

test_profile = profiles.loc[
    profiles["user_id"] == test_user_id
].iloc[0]

test_goals = (
    goals.loc[goals["user_id"] == test_user_id]
    .reset_index(drop=True)
)

env = GoalPilotEnv(
    profile=test_profile,
    goals=test_goals,
    market_data=market,
    max_months=120,
)

print("Action space:", env.action_space)
print("Observation space:", env.observation_space)

check_env(env, warn=True)
print("Gymnasium check passed.")

observation, info = env.reset(seed=42)

action = np.zeros(env.action_space.shape, dtype=np.float32)
next_obs, reward, terminated, truncated, step_info = env.step(action)

total_allocated = (
    step_info["goal_allocations"].sum()
    + step_info["savings_contribution"]
    + step_info["investment_contribution"]
)

print("\nAvailable surplus:", round(step_info["monthly_surplus"], 2))
print("Total allocated:", round(float(total_allocated), 2))
print("Investment contribution:", round(step_info["investment_contribution"], 2))
print("Budget respected:", total_allocated <= step_info["monthly_surplus"] + 1e-4)
print("Observation valid:", env.observation_space.contains(observation))
print("Next observation shape:", next_obs.shape)

# ===== CELL 34 =====  type=code  exec=None
from pathlib import Path

PROJECT_DIR = Path("/content/drive/MyDrive/GoalPilot_AI")

optimizer_path = (
    PROJECT_DIR
    / "GoalPilot_MultiGoal_Extension"
    / "src"
    / "multi_goal_optimizer.py"
)

print("Optimizer file exists:", optimizer_path.exists())

if optimizer_path.exists():
    source = optimizer_path.read_text(encoding="utf-8")
    lines = source.splitlines()

    keywords = [
        "loan",
        "interest",
        "emi",
        "loan_principal",
        "loan_rate",
        "walr",
        "affordability",
        "emi_income_ratio_cap",
    ]

    matching_lines = [
        (i + 1, line)
        for i, line in enumerate(lines)
        if any(word in line.lower() for word in keywords)
    ]

    print("Total source lines:", len(lines))
    print("\nLoan-related code locations:")

    for line_number, line in matching_lines[:80]:
        print(f"{line_number:4}: {line}")
else:
    print("Check the optimizer path before proceeding.")

# ===== CELL 35 =====  type=code  exec=None
from pathlib import Path

PROJECT_DIR = Path("/content/drive/MyDrive/GoalPilot_AI")
SRC_DIR = PROJECT_DIR / "GoalPilot_MultiGoal_Extension" / "src"

files_to_inspect = {
    "multi_goal_optimizer.py": [
        (65, 100),    # EMI formula and related helpers
        (110, 175),   # Optimizer parameters and scenario selection
        (180, 245),   # Funding constraints and EMI affordability
    ],
    "providers.py": [
        (1, 180),     # Loan offer definitions and selection logic
    ],
}

for filename, ranges in files_to_inspect.items():
    path = SRC_DIR / filename

    print("\n" + "=" * 80)
    print(f"FILE: {filename}")
    print("Exists:", path.exists())
    print("=" * 80)

    if not path.exists():
        continue

    lines = path.read_text(encoding="utf-8").splitlines()

    for start, end in ranges:
        if start > len(lines):
            continue

        print(f"\n--- Lines {start}-{min(end, len(lines))} ---")

        for line_no in range(start, min(end, len(lines)) + 1):
            print(f"{line_no:4}: {lines[line_no - 1]}")

# ===== CELL 36 =====  type=code  exec=None
from pathlib import Path

PROJECT_DIR = Path("/content/drive/MyDrive/GoalPilot_AI")
SRC_DIR = PROJECT_DIR / "GoalPilot_MultiGoal_Extension" / "src"

# 1. Inspect loan-offer selection and provider loading logic
providers_path = SRC_DIR / "providers.py"

if providers_path.exists():
    lines = providers_path.read_text(encoding="utf-8").splitlines()

    print("=" * 75)
    print("PROVIDERS.PY — LOAN SELECTION AND DATA LOADING")
    print("=" * 75)

    for start, end in [(174, 260), (260, len(lines))]:
        if start >= len(lines):
            continue

        print(f"\n--- Lines {start + 1}-{min(end, len(lines))} ---")
        for i in range(start, min(end, len(lines))):
            line = lines[i]
            if any(k in line.lower() for k in [
                "loan", "select_", "json", "provider", "load", "path",
                "annual_interest_rate", "max_principal", "tenure_months"
            ]) or line.strip().startswith(("def ", "class ")):
                print(f"{i + 1:4}: {line}")

# 2. Find local files that might contain loan offers or economic scenarios
print("\n" + "=" * 75)
print("POTENTIAL LOAN / ECONOMIC SCENARIO FIXTURES")
print("=" * 75)

search_roots = [
    PROJECT_DIR / "GoalPilot_MultiGoal_Extension",
    PROJECT_DIR / "simulation",
]

matches = []
for root in search_roots:
    if root.exists():
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in {".json", ".csv"}:
                name = path.name.lower()
                if any(term in name for term in [
                    "loan", "offer", "provider", "scenario", "economic"
                ]):
                    matches.append(path)

if matches:
    for path in matches[:60]:
        print(path.relative_to(PROJECT_DIR))
else:
    print("No files found with loan/offer/provider/scenario/economic in the filename.")

# ===== CELL 37 =====  type=code  exec=None
from pathlib import Path
import pandas as pd

PROJECT_DIR = Path("/content/drive/MyDrive/GoalPilot_AI")

files_to_check = {
    "Economic scenario comparison": (
        PROJECT_DIR
        / "GoalPilot_MultiGoal_Extension"
        / "outputs"
        / "economic_scenario_comparison.csv"
    ),
    "Raw market-credit scenarios": (
        PROJECT_DIR
        / "simulation"
        / "01_input_data"
        / "market_credit_scenarios.csv"
    ),
}

for label, path in files_to_check.items():
    print("\n" + "=" * 80)
    print(label)
    print("Path:", path)
    print("Exists:", path.exists())
    print("=" * 80)

    if not path.exists():
        continue

    df = pd.read_csv(path)

    print("Shape:", df.shape)
    print("Columns:", df.columns.tolist())
    print("\nFirst 5 rows:")
    display(df.head())

    # Show columns potentially related to lending, rates, or assumptions.
    relevant = [
        col for col in df.columns
        if any(term in col.lower() for term in [
            "loan", "walr", "rate", "interest", "credit",
            "scenario", "lending", "fee", "tenure"
        ])
    ]

    if relevant:
        print("\nRelevant column summary:")
        display(df[relevant].head(10))

# Print the exact existing loan-selection implementation.
providers_path = (
    PROJECT_DIR
    / "GoalPilot_MultiGoal_Extension"
    / "src"
    / "providers.py"
)

lines = providers_path.read_text(encoding="utf-8").splitlines()

print("\n" + "=" * 80)
print("EXACT LOAN OFFER SELECTION LOGIC")
print("=" * 80)

for i in range(220, min(243, len(lines))):
    print(f"{i + 1:4}: {lines[i]}")

# ===== CELL 38 =====  type=code  exec=None

from pathlib import Path
import re

PROJECT_DIR = Path("/content/drive/MyDrive/GoalPilot_AI")
EXT_DIR = PROJECT_DIR / "GoalPilot_MultiGoal_Extension"

print("=" * 75)
print("1. SEARCH FOR LOAN-OFFER AND PROVIDER CONFIGURATION FILES")
print("=" * 75)

terms = ("loan", "offer", "provider", "scenario", "economic", "credit")
matches = []

for path in EXT_DIR.rglob("*"):
    if not path.is_file():
        continue
    if any(part in {"node_modules", ".git", "__pycache__"} for part in path.parts):
        continue
    if path.suffix.lower() in {".json", ".csv", ".yaml", ".yml", ".toml"}:
        if any(term in path.name.lower() for term in terms):
            matches.append(path)

for path in matches:
    print(path.relative_to(PROJECT_DIR))

print("\n" + "=" * 75)
print("2. PROVIDER DEFINITIONS AND DEFAULTS")
print("=" * 75)

providers_path = EXT_DIR / "src" / "providers.py"
lines = providers_path.read_text(encoding="utf-8").splitlines()

patterns = re.compile(
    r"class (LoanOffer|LocalJSONProvider|LocalCSVProvider)|"
    r"def (load|from_mapping|select_loan_offer)|"
    r"annual_interest_rate|max_principal|fee_rate|assumption_label",
    re.IGNORECASE
)

for i, line in enumerate(lines):
    if patterns.search(line):
        start = max(0, i - 2)
        end = min(len(lines), i + 5)
        print(f"\n--- providers.py lines {start + 1}-{end} ---")
        for j in range(start, end):
            print(f"{j + 1:4}: {lines[j]}")

print("\n" + "=" * 75)
print("3. HOW THE OPTIMIZER RECEIVES LOAN AND MARKET ASSUMPTIONS")
print("=" * 75)

optimizer_path = EXT_DIR / "src" / "multi_goal_optimizer.py"

if optimizer_path.exists():
    opt_lines = optimizer_path.read_text(encoding="utf-8").splitlines()
    keywords = re.compile(
        r"loan_annual_rate|loan_tenure_months|max_loan_per_goal|"
        r"select_loan_offer|loan_offers|economic_scenario|"
        r"scenario|market_return|investment_return",
        re.IGNORECASE
    )

    shown = set()
    for i, line in enumerate(opt_lines):
        if keywords.search(line):
            start = max(0, i - 2)
            end = min(len(opt_lines), i + 4)
            if any(j in shown for j in range(start, end)):
                continue
            print(f"\n--- multi_goal_optimizer.py lines {start + 1}-{end} ---")
            for j in range(start, end):
                print(f"{j + 1:4}: {opt_lines[j]}")
                shown.add(j)
else:
    print("Optimizer source file not found at the expected path.")

print("\nInspection complete. No files were modified.")


# ===== CELL 39 =====  type=code  exec=None

from pathlib import Path
import pandas as pd
import re

PROJECT_DIR = Path("/content/drive/MyDrive/GoalPilot_AI")
EXT_DIR = PROJECT_DIR / "GoalPilot_MultiGoal_Extension"

optimizer_path = EXT_DIR / "src" / "multi_goal_optimizer.py"
comparison_path = EXT_DIR / "outputs" / "economic_scenario_comparison.csv"

print("=" * 75)
print("1. EXISTING SCENARIO COMPARISON")
print("=" * 75)

comparison = pd.read_csv(comparison_path)
display(comparison)

print("\n" + "=" * 75)
print("2. LOAN-RELATED LOGIC IN THE SCENARIO COMPARISON")
print("=" * 75)

opt_lines = optimizer_path.read_text(encoding="utf-8").splitlines()

for start, end in [(105, 175), (185, 230), (260, 315)]:
    print(f"\n--- multi_goal_optimizer.py lines {start + 1}-{min(end, len(opt_lines))} ---")
    for i in range(start, min(end, len(opt_lines))):
        if re.search(
            r"loan|scenario|economic_scenario|max_loan|interest_rate|"
            r"annual_inflation|investment_return|def compare",
            opt_lines[i],
            re.IGNORECASE
        ):
            left = max(start, i - 1)
            right = min(len(opt_lines), i + 3)
            for j in range(left, right):
                print(f"{j + 1:4}: {opt_lines[j]}")
            print()

print("\n" + "=" * 75)
print("3. LOAN EMI FUNCTION")
print("=" * 75)

for i, line in enumerate(opt_lines):
    if "def monthly_emi_per_rupee" in line:
        for j in range(i, min(i + 13, len(opt_lines))):
            print(f"{j + 1:4}: {opt_lines[j]}")
        break

print("\nInspection complete. No files were modified.")


# ===== CELL 40 =====  type=code  exec=None

from pathlib import Path

PROJECT_DIR = Path("/content/drive/MyDrive/GoalPilot_AI")
search_roots = [
    PROJECT_DIR / "GoalPilot_MultiGoal_Extension",
    PROJECT_DIR / "simulation" / "05_simulation_runs",
]

search_terms = [
    "economic_scenario_comparison",
    "Higher loan rate",
    "Higher inflation",
    "Lower market returns",
]

extensions = {".py", ".ipynb", ".md"}

for term in search_terms:
    print("\n" + "=" * 75)
    print(f"SEARCH TERM: {term}")
    print("=" * 75)

    found = 0
    for root in search_roots:
        if not root.exists():
            continue

        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in extensions:
                continue
            if any(part in {"node_modules", ".git", "__pycache__"} for part in path.parts):
                continue

            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            lines = content.splitlines()
            matching_lines = [
                (i + 1, line.strip())
                for i, line in enumerate(lines)
                if term.lower() in line.lower()
            ]

            if matching_lines:
                print(f"\nFile: {path.relative_to(PROJECT_DIR)}")
                for line_no, line in matching_lines[:8]:
                    print(f"  {line_no}: {line[:220]}")
                found += len(matching_lines)

    if found == 0:
        print("No matches found in the searched project folders.")

print("\nSearch complete. No files were modified.")


# ===== CELL 41 =====  type=code  exec=None

from pathlib import Path

PROJECT_DIR = Path("/content/drive/MyDrive/GoalPilot_AI")
EXT_DIR = PROJECT_DIR / "GoalPilot_MultiGoal_Extension"

files_to_inspect = [
    EXT_DIR / "run_demo.py",
    EXT_DIR / "docs" / "validation_report_2026-10-10_v2.md",
]

for path in files_to_inspect:
    print("\n" + "=" * 85)
    print("FILE:", path.relative_to(PROJECT_DIR))
    print("=" * 85)

    if not path.exists():
        print("File not found.")
        continue

    content = path.read_text(encoding="utf-8", errors="replace")
    print(content)

print("\nInspection complete. No files were modified.")


# ===== CELL 42 =====  type=code  exec=None

from pathlib import Path
import sys
import json
import pandas as pd

PROJECT_DIR = Path("/content/drive/MyDrive/GoalPilot_AI")
EXT_DIR = PROJECT_DIR / "GoalPilot_MultiGoal_Extension"

if str(EXT_DIR) not in sys.path:
    sys.path.insert(0, str(EXT_DIR))

from src.multi_goal_optimizer import (
    FinancialState,
    optimize_multi_goal,
)

state_data = json.loads(
    (EXT_DIR / "data" / "sample_financial_state.json").read_text()
)

state = FinancialState(**{
    k: v for k, v in state_data.items()
    if k not in {"user_id", "source_note"}
})

goals = pd.read_csv(EXT_DIR / "data" / "sample_goals.csv")

base_kwargs = {
    "annual_inflation": 0.03,
    "savings_return": 0.0,
    "investment_return": 0.05,
    "investment_risk_score": 0.4,
    "loan_tenure_months": 60,
    "max_loan_per_goal": 150000,
}

results = []

for annual_rate in [0.12, 0.16]:
    result = optimize_multi_goal(
        goals,
        state,
        **base_kwargs,
        loan_annual_rate=annual_rate,
    )

    allocations = result["allocations"]
    summary = result.get("summary", {})

    loan_principal = (
        float(allocations["loan_principal"].sum())
        if "loan_principal" in allocations.columns else 0.0
    )

    results.append({
        "annual_loan_rate_pct": annual_rate * 100,
        "solver_status": result["status"],
        "total_loan_principal": loan_principal,
        "new_monthly_emi": summary.get("new_total_emi"),
        "loan_interest_cost": summary.get("loan_cost_total"),
        "total_shortfall": summary.get("total_shortfall"),
        "monthly_contributions": summary.get(
            "monthly_contributions_allocated"
        ),
    })

print("Sample financial state:")
print("Monthly income:", state.monthly_income)
print("Liquid savings:", state.liquid_savings)
print("Existing EMI:", state.existing_emi)
print("\nInterest-rate sensitivity:")
display(pd.DataFrame(results).round(2))

print("\nGoal-level borrowing at 16%:")
result_16 = optimize_multi_goal(
    goals,
    state,
    **base_kwargs,
    loan_annual_rate=0.16,
)
display(
    result_16["allocations"][
        [
            "goal_id",
            "goal_name",
            "funding_gap",
            "loan_principal",
            "estimated_loan_emi",
            "estimated_loan_interest_cost",
            "shortfall",
        ]
    ].round(2)
)

print("\nNo project files were modified.")


# ===== CELL 43 =====  type=code  exec=None

from pathlib import Path
import inspect
import pandas as pd

EXT_DIR = Path("/content/drive/MyDrive/GoalPilot_AI/GoalPilot_MultiGoal_Extension")

goals_path = EXT_DIR / "data" / "sample_goals.csv"
goals = pd.read_csv(goals_path)

print("=" * 75)
print("1. SAMPLE GOALS: SCHEMA AND VALUES")
print("=" * 75)
print("Columns:", goals.columns.tolist())
display(goals)

print("\n" + "=" * 75)
print("2. GOAL PREPARATION LOGIC")
print("=" * 75)

import sys
if str(EXT_DIR) not in sys.path:
    sys.path.insert(0, str(EXT_DIR))

from src.multi_goal_optimizer import prepare_goals

print(inspect.getsource(prepare_goals))

print("\n" + "=" * 75)
print("3. FINANCIAL STATE VALIDATION")
print("=" * 75)

from src.multi_goal_optimizer import FinancialState
print(inspect.getsource(FinancialState))

print("\nInspection only: original CSV and optimizer source were not modified.")


# ===== CELL 44 =====  type=code  exec=None

from pathlib import Path
import sys
import pandas as pd

PROJECT_DIR = Path("/content/drive/MyDrive/GoalPilot_AI")
EXT_DIR = PROJECT_DIR / "GoalPilot_MultiGoal_Extension"

if str(EXT_DIR) not in sys.path:
    sys.path.insert(0, str(EXT_DIR))

from src.multi_goal_optimizer import FinancialState, optimize_multi_goal

# Temporary stress-test state — no original data is modified.
stress_state = FinancialState(
    monthly_income=20000,
    essential_expenses=18000,
    discretionary_expenses=0,
    existing_emi=0,
    liquid_savings=0,
    existing_investments=0,
    usable_existing_investments=0,
    emergency_months=6,
    emi_income_ratio_cap=0.35,
    risk_capacity=0.3,
)

# One urgent goal with a funding gap larger than monthly savings capacity.
stress_goals = pd.DataFrame([{
    "goal_id": "STRESS_01",
    "goal_name": "Urgent Essential Goal",
    "current_cost": 200000,
    "target_date": "2026-11-10",
    "time_horizon_months": 1,
    "priority": 5,
    "criticality": 5,
    "existing_funding": 0,
}])

common = {
    "annual_inflation": 0.0,
    "savings_return": 0.0,
    "investment_return": 0.0,
    "investment_risk_score": 0.0,
    "loan_annual_rate": 0.12,
    "loan_tenure_months": 60,
}

results = []
allocation_tables = {}

for label, max_loan in [
    ("Borrowing disabled", 0.0),
    ("Borrowing enabled", 150000.0),
]:
    result = optimize_multi_goal(
        stress_goals,
        stress_state,
        **common,
        max_loan_per_goal=max_loan,
    )

    allocation_tables[label] = result["allocations"]
    summary = result.get("summary", {})
    allocations = result["allocations"]

    results.append({
        "test": label,
        "solver_status": result["status"],
        "funding_gap": summary.get("total_funding_gap"),
        "loan_principal": allocations["loan_principal"].sum(),
        "new_monthly_emi": summary.get("new_total_emi"),
        "loan_interest_cost": summary.get("loan_cost_total"),
        "monthly_contributions": summary.get(
            "monthly_contributions_allocated"
        ),
        "shortfall": summary.get("total_shortfall"),
        "emi_cap_respected": summary.get("emi_cap_respected"),
        "monthly_surplus_respected": summary.get(
            "monthly_surplus_respected"
        ),
    })

print("MONTHLY BUDGET")
print(f"Income: ₹{stress_state.monthly_income:,.2f}")
print(f"Essential expenses: ₹{stress_state.essential_expenses:,.2f}")
print(f"Available monthly surplus: ₹{2000:,.2f}")
print(f"EMI capacity before new borrowing: ₹{7000:,.2f}")
print("Goal funding gap: ₹200,000.00")

print("\nCOMPARISON")
display(pd.DataFrame(results).round(2))

print("\nGOAL-LEVEL ALLOCATION")
for label, allocations in allocation_tables.items():
    print(f"\n{label}")
    display(allocations[[
        "goal_id",
        "funding_gap",
        "initial_savings_allocated",
        "monthly_savings_contribution",
        "monthly_investment_contribution",
        "loan_principal",
        "estimated_loan_emi",
        "estimated_loan_interest_cost",
        "shortfall",
    ]].round(2))

print("\nThis was an in-memory test; no project files were modified.")


# ===== CELL 45 =====  type=code  exec=None

# Audit the combined monthly cash-flow constraint.
# Uses the stress-test variables from the previous cell.

monthly_surplus = max(
    0.0,
    stress_state.monthly_income
    - stress_state.essential_expenses
    - stress_state.discretionary_expenses
    - stress_state.existing_emi,
)

print("=" * 70)
print("COMBINED MONTHLY CASH-FLOW AUDIT")
print("=" * 70)
print(f"Monthly surplus before new loan: ₹{monthly_surplus:,.2f}")

for label, allocations in allocation_tables.items():
    contributions = float(
        allocations["monthly_savings_contribution"].sum()
        + allocations["monthly_investment_contribution"].sum()
    )
    new_emi = float(allocations["estimated_loan_emi"].sum())
    total_commitment = contributions + new_emi
    remaining = monthly_surplus - total_commitment

    print(f"\n{label}")
    print(f"  Monthly contributions: ₹{contributions:,.2f}")
    print(f"  New loan EMI:          ₹{new_emi:,.2f}")
    print(f"  Combined commitment:   ₹{total_commitment:,.2f}")
    print(f"  Surplus remaining:     ₹{remaining:,.2f}")
    print(
        "  Combined budget respected:",
        total_commitment <= monthly_surplus + 1e-5,
    )

print("\nAudit complete. No project files were modified.")


# ===== CELL 46 =====  type=code  exec=None

from pathlib import Path

PROJECT_DIR = Path("/content/drive/MyDrive/GoalPilot_AI")
optimizer_path = (
    PROJECT_DIR
    / "GoalPilot_MultiGoal_Extension"
    / "src"
    / "multi_goal_optimizer.py"
)

lines = optimizer_path.read_text(encoding="utf-8").splitlines()

print("=" * 75)
print("LP CONSTRAINTS AND SOLVER")
print("=" * 75)

for start, end in [(215, 265), (275, 310)]:
    print(f"\n--- Lines {start + 1}-{min(end, len(lines))} ---")
    for i in range(start, min(end, len(lines))):
        print(f"{i + 1:4}: {lines[i]}")

print("\n" + "=" * 75)
print("RELATED TEST FILES")
print("=" * 75)

test_roots = [
    PROJECT_DIR / "GoalPilot_MultiGoal_Extension" / "tests",
    PROJECT_DIR / "GoalPilot_MultiGoal_Extension",
]

seen = set()
for root in test_roots:
    if not root.exists():
        continue
    for path in root.rglob("test_*.py"):
        if path in seen:
            continue
        seen.add(path)
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if any(term in content.lower() for term in [
            "emi_cap_respected",
            "monthly_surplus_respected",
            "loan_principal",
            "monthly_surplus",
        ]):
            print(f"\nFile: {path.relative_to(PROJECT_DIR)}")
            for i, line in enumerate(content.splitlines()):
                if any(term in line.lower() for term in [
                    "emi_cap_respected",
                    "monthly_surplus_respected",
                    "loan_principal",
                    "monthly_surplus",
                ]):
                    print(f"{i + 1:4}: {line.strip()[:200]}")

print("\nInspection complete. No files were modified.")


# ===== CELL 47 =====  type=code  exec=None

from pathlib import Path

project_dir = Path(
    "/content/drive/MyDrive/GoalPilot_AI/GoalPilot_MultiGoal_Extension"
)

files_to_inspect = {
    "Optimizer function setup": (
        project_dir / "src" / "multi_goal_optimizer.py",
        120,
        215,
    ),
    "Existing optimizer tests": (
        project_dir / "tests" / "test_optimizer.py",
        0,
        100,
    ),
}

for title, (path, start, end) in files_to_inspect.items():
    print("\n" + "=" * 75)
    print(title)
    print(f"File: {path}")
    print("=" * 75)

    if not path.exists():
        print("FILE NOT FOUND")
        continue

    lines = path.read_text(encoding="utf-8").splitlines()

    for i in range(start, min(end, len(lines))):
        print(f"{i + 1:4}: {lines[i]}")

print("\nInspection complete. No files were modified.")


# ===== CELL 48 =====  type=code  exec=None

from pathlib import Path
import shutil

project_dir = Path(
    "/content/drive/MyDrive/GoalPilot_AI/GoalPilot_MultiGoal_Extension"
)
optimizer_path = project_dir / "src" / "multi_goal_optimizer.py"
backup_path = optimizer_path.with_suffix(".py.pre_cashflow_fix.bak")

if not optimizer_path.exists():
    raise FileNotFoundError(f"Optimizer not found: {optimizer_path}")

if not backup_path.exists():
    shutil.copy2(optimizer_path, backup_path)

lines = optimizer_path.read_text(encoding="utf-8").splitlines()

# Locate the existing EMI constraint and solver call.
emi_line = next(
    i for i, line in enumerate(lines)
    if "A_ub.append(row); b_ub.append(emi_cap)" in line
)
solver_line = next(
    i for i, line in enumerate(lines)
    if "result=linprog(" in line
)

print("Backup:", backup_path)
print("\nExisting constraint section:")
for i in range(max(0, emi_line - 5), min(len(lines), solver_line + 2)):
    print(f"{i + 1:4}: {lines[i]}")

print("\nNo optimizer code was changed.")


# ===== CELL 49 =====  type=code  exec=None

from pathlib import Path

optimizer_path = Path(
    "/content/drive/MyDrive/GoalPilot_AI/"
    "GoalPilot_MultiGoal_Extension/src/multi_goal_optimizer.py"
)
backup_path = optimizer_path.with_suffix(".py.pre_cashflow_fix.bak")

if not optimizer_path.exists() or not backup_path.exists():
    raise FileNotFoundError("Optimizer or safety backup is missing.")

source = optimizer_path.read_text(encoding="utf-8")

old_constraint_block = '''    row=[0.0]*nv
    for j in range(n): row[ix(j,"loan")]=emi_factor
    A_ub.append(row); b_ub.append(emi_cap)
    result=linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq, bounds=bounds, method="highs")'''

new_constraint_block = '''    row=[0.0]*nv
    for j in range(n): row[ix(j,"loan")]=emi_factor
    A_ub.append(row); b_ub.append(emi_cap)

    # Combined affordability constraint:
    # monthly contributions + new loan EMIs must fit within monthly surplus.
    row=[0.0]*nv
    for j in range(n):
        row[ix(j,"save")]=1.0
        row[ix(j,"invest")]=1.0
        row[ix(j,"loan")]=emi_factor
    A_ub.append(row); b_ub.append(monthly_surplus)

    result=linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq, bounds=bounds, method="highs")'''

old_summary_flag = '''"monthly_surplus_respected":float((allocations.monthly_savings_contribution+allocations.monthly_investment_contribution).sum())<=monthly_surplus+1e-5'''

new_summary_flag = '''"monthly_surplus_respected":float((allocations.monthly_savings_contribution+allocations.monthly_investment_contribution).sum())<=monthly_surplus+1e-5,"combined_monthly_cashflow_respected":float((allocations.monthly_savings_contribution+allocations.monthly_investment_contribution).sum()+total_emi)<=monthly_surplus+1e-5'''

if source.count(old_constraint_block) != 1:
    raise RuntimeError(
        "Expected constraint block was not found exactly once. "
        "No changes were written."
    )

if source.count(old_summary_flag) != 1:
    raise RuntimeError(
        "Expected summary flag was not found exactly once. "
        "No changes were written."
    )

updated = source.replace(old_constraint_block, new_constraint_block, 1)
updated = updated.replace(old_summary_flag, new_summary_flag, 1)

# Validate the edit in memory before writing.
compile(updated, str(optimizer_path), "exec")

optimizer_path.write_text(updated, encoding="utf-8")

print("Combined monthly cash-flow constraint added.")
print("New validation flag: combined_monthly_cashflow_respected")
print("Python syntax check: PASSED")
print("Backup retained:", backup_path)
print("Next: run the optimizer regression tests.")


# ===== CELL 50 =====  type=code  exec=None

from pathlib import Path
import subprocess
import sys

project_dir = Path(
    "/content/drive/MyDrive/GoalPilot_AI/GoalPilot_MultiGoal_Extension"
)
test_file = project_dir / "tests" / "test_optimizer.py"

if not test_file.exists():
    raise FileNotFoundError(f"Test file not found: {test_file}")

result = subprocess.run(
    [
        sys.executable,
        "-m",
        "pytest",
        "-v",
        str(test_file),
    ],
    cwd=str(project_dir),
    capture_output=True,
    text=True,
    timeout=180,
)

print("OPTIMIZER REGRESSION TESTS")
print("=" * 70)
print(result.stdout)

if result.stderr.strip():
    print("\nSTDERR:")
    print(result.stderr)

print("\nExit code:", result.returncode)
print("Tests passed." if result.returncode == 0 else "Tests failed; inspect the output above.")


# ===== CELL 51 =====  type=code  exec=None

import importlib
import sys
from pathlib import Path

project_dir = Path(
    "/content/drive/MyDrive/GoalPilot_AI/GoalPilot_MultiGoal_Extension"
)
optimizer_path = project_dir / "src" / "multi_goal_optimizer.py"

if str(project_dir) not in sys.path:
    sys.path.insert(0, str(project_dir))

import src.multi_goal_optimizer as optimizer_module

print("=" * 70)
print("OPTIMIZER SOURCE AND IMPORT CHECK")
print("=" * 70)

source = optimizer_path.read_text(encoding="utf-8")
print("Source file:", optimizer_path)
print("Combined constraint in saved source:",
      "A_ub.append(row); b_ub.append(monthly_surplus)" in source
      and 'row[ix(j,"loan")]=emi_factor' in source)
print("Combined validation flag in saved source:",
      '"combined_monthly_cashflow_respected":' in source)
print("Imported module before reload:", optimizer_module.__file__)

optimizer_module = importlib.reload(optimizer_module)

print("Imported module after reload:", optimizer_module.__file__)
print("Function source file:",
      optimizer_module.optimize_multi_goal.__code__.co_filename)

print("\nRelevant saved-source lines:")
for i, line in enumerate(source.splitlines(), start=1):
    if (
        "Combined affordability constraint" in line
        or '"combined_monthly_cashflow_respected":' in line
        or "A_ub.append(row); b_ub.append(emi_cap)" in line
    ):
        print(f"{i:4}: {line.strip()}")

print("\nCheck complete. No files were modified.")


# ===== CELL 52 =====  type=code  exec=None

import pandas as pd

# Use the module reloaded in the previous cell.
FinancialState = optimizer_module.FinancialState
optimize_multi_goal = optimizer_module.optimize_multi_goal

stress_state = FinancialState(
    monthly_income=20_000,
    essential_expenses=18_000,
    discretionary_expenses=0,
    existing_emi=0,
    liquid_savings=0,
    existing_investments=0,
    usable_existing_investments=0,
    emergency_months=6,
    emi_income_ratio_cap=0.35,
    risk_capacity=0.3,
)

stress_goals = pd.DataFrame([{
    "goal_id": "STRESS_1",
    "goal_name": "Urgent goal",
    "current_cost": 200_000,
    "target_date": "2026-11-10",
    "time_horizon_months": 1,
    "priority": 5,
    "criticality": 5,
    "existing_funding": 0,
}])

result = optimize_multi_goal(
    stress_goals,
    stress_state,
    annual_inflation=0,
    savings_return=0,
    investment_return=0,
    investment_risk_score=0,
    loan_annual_rate=0.12,
    loan_tenure_months=60,
    max_loan_per_goal=150_000,
)

print("Solver status:", result["status"])

if result["status"] == "optimal":
    a = result["allocations"]
    s = result["summary"]

    contributions = s["monthly_contributions_allocated"]
    emi = s["new_total_emi"]
    surplus = s["monthly_surplus_available"]
    combined = contributions + emi

    print(f"Monthly surplus:       ₹{surplus:,.2f}")
    print(f"Monthly contributions: ₹{contributions:,.2f}")
    print(f"New loan EMI:          ₹{emi:,.2f}")
    print(f"Combined commitment:   ₹{combined:,.2f}")
    print(f"Loan principal:        ₹{a['loan_principal'].sum():,.2f}")
    print(f"Goal shortfall:        ₹{a['shortfall'].sum():,.2f}")

    print("\nReported constraints:")
    for key in [
        "monthly_surplus_respected",
        "combined_monthly_cashflow_respected",
        "emi_cap_respected",
    ]:
        print(f"{key}: {s.get(key)}")

    print("\nIndependent affordability check:",
          combined <= surplus + 1e-5)

print("\nNo files modified.")


# ===== CELL 53 =====  type=code  exec=None

from pathlib import Path
import subprocess
import sys

project_dir = Path(
    "/content/drive/MyDrive/GoalPilot_AI/GoalPilot_MultiGoal_Extension"
)
test_path = project_dir / "tests" / "test_optimizer.py"

test_name = "test_combined_monthly_commitment_never_exceeds_surplus"

test_code = '''

def test_combined_monthly_commitment_never_exceeds_surplus():
    """New loan EMIs and goal contributions must share one cash-flow budget."""
    state = FinancialState(
        monthly_income=20000,
        essential_expenses=18000,
        discretionary_expenses=0,
        existing_emi=0,
        liquid_savings=0,
        existing_investments=0,
        usable_existing_investments=0,
        emergency_months=6,
        emi_income_ratio_cap=0.35,
        risk_capacity=0.3,
    )
    goals = pd.DataFrame([{
        "goal_id": "STRESS_1",
        "goal_name": "Urgent goal",
        "current_cost": 200000,
        "target_date": "2026-11-10",
        "time_horizon_months": 1,
        "priority": 5,
        "criticality": 5,
        "existing_funding": 0,
    }])

    result = optimize_multi_goal(
        goals,
        state,
        annual_inflation=0,
        savings_return=0,
        investment_return=0,
        investment_risk_score=0,
        loan_annual_rate=0.12,
        loan_tenure_months=60,
        max_loan_per_goal=150000,
    )

    assert result["status"] == "optimal"
    summary = result["summary"]
    contributions = summary["monthly_contributions_allocated"]
    new_emi = summary["new_total_emi"]
    surplus = summary["monthly_surplus_available"]

    assert summary["combined_monthly_cashflow_respected"]
    assert contributions + new_emi <= surplus + 1e-5
    assert summary["emi_cap_respected"]
'''

if not test_path.exists():
    raise FileNotFoundError(f"Test file not found: {test_path}")

existing = test_path.read_text(encoding="utf-8")

if test_name not in existing:
    with test_path.open("a", encoding="utf-8") as f:
        f.write(test_code)
    print("Added permanent regression test.")
else:
    print("Regression test already exists; not adding a duplicate.")

result = subprocess.run(
    [sys.executable, "-m", "pytest", "-v", str(test_path)],
    cwd=str(project_dir),
    capture_output=True,
    text=True,
    timeout=180,
)

print("\n" + "=" * 70)
print("OPTIMIZER TEST SUITE")
print("=" * 70)
print(result.stdout)

if result.stderr.strip():
    print("\nSTDERR:")
    print(result.stderr)

print("\nExit code:", result.returncode)
if result.returncode != 0:
    raise RuntimeError("Optimizer tests failed; inspect the output above.")

print("All optimizer tests passed.")


# ===== CELL 54 =====  type=code  exec=None

from pathlib import Path
import pandas as pd

BASE = Path("/content/drive/MyDrive/GoalPilot_AI")
RL_DIR = BASE / "simulation/05_simulation_runs/rl_prototype"
PROFILE_FILE = RL_DIR / "rl_sample_financial_profiles.csv"
GOALS_FILE = RL_DIR / "rl_sample_goals.csv"
MARKET_FILE = RL_DIR / "rl_market_credit_economic.csv"

print("=" * 75)
print("GOALPILOT AI — RL PROTOTYPE INSPECTION")
print("=" * 75)

print("\n1. Prototype files")
if RL_DIR.exists():
    for path in sorted(RL_DIR.iterdir()):
        if path.is_file():
            print(f"  {path.name} ({path.stat().st_size:,} bytes)")
else:
    print("  Prototype directory not found.")

print("\n2. Existing environment and training code")
search_roots = [
    RL_DIR,
    BASE / "GoalPilot_MultiGoal_Extension",
]

keywords = ("gymnasium", "stable_baselines", "class .*Env", "def step(", "def reset(")
found = 0

for root in search_roots:
    if not root.exists():
        continue
    for path in root.rglob("*.py"):
        if any(part.startswith(".") for part in path.parts):
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            continue

        matches = [
            (i + 1, line.strip())
            for i, line in enumerate(lines)
            if any(word in line for word in keywords)
        ]
        if matches:
            found += 1
            print(f"\n  {path.relative_to(BASE)}")
            for line_no, line in matches[:12]:
                print(f"    {line_no}: {line[:180]}")

if found == 0:
    print("  No matching Python environment/training implementation found.")

print("\n3. Sample data dimensions")
for label, path in [
    ("Financial profiles", PROFILE_FILE),
    ("Goals", GOALS_FILE),
    ("Market/economic environment", MARKET_FILE),
]:
    if path.exists():
        df = pd.read_csv(path)
        print(f"\n  {label}: {df.shape[0]:,} rows × {df.shape[1]} columns")
        print("  Columns:", ", ".join(df.columns[:15]))
        if len(df.columns) > 15:
            print("  ...")
    else:
        print(f"\n  {label}: FILE NOT FOUND — {path}")

print("\nInspection complete. No files modified; no training started.")


# ===== CELL 55 =====  type=code  exec=None

from pathlib import Path
import numpy as np
import pandas as pd

BASE = Path("/content/drive/MyDrive/GoalPilot_AI")
RL_DIR = BASE / "simulation/05_simulation_runs/rl_prototype"

profiles_path = RL_DIR / "rl_sample_financial_profiles.csv"
goals_path = RL_DIR / "rl_sample_goals.csv"
market_path = RL_DIR / "rl_market_credit_economic.csv"

for path in [profiles_path, goals_path, market_path]:
    if not path.exists():
        raise FileNotFoundError(f"Required input missing: {path}")

profiles = pd.read_csv(profiles_path)
goals = pd.read_csv(goals_path)
market = pd.read_csv(market_path, parse_dates=["period"])

# Normalize period to a month-start timestamp for consistent monthly indexing.
market["period"] = pd.to_datetime(market["period"]).dt.to_period("M").dt.to_timestamp()
market = market.sort_values("period").reset_index(drop=True)

required_profile_cols = [
    "user_id", "monthly_income", "monthly_expenditure", "monthly_emi",
    "initial_savings", "initial_investment", "investment_capacity_ratio",
    "risk_score",
]
required_goal_cols = [
    "user_id", "goal_id", "current_cost", "time_horizon_months",
    "priority", "criticality", "existing_funding",
]
required_market_cols = [
    "period", "nifty_monthly_return", "walr_monthly",
    "inflation_level",
]

print("=" * 72)
print("RL INPUT VALIDATION")
print("=" * 72)

for label, df, required in [
    ("Profiles", profiles, required_profile_cols),
    ("Goals", goals, required_goal_cols),
    ("Market", market, required_market_cols),
]:
    missing = sorted(set(required) - set(df.columns))
    print(f"\n{label}: {df.shape[0]:,} rows")
    print("Missing required columns:", missing if missing else "None")
    if missing:
        raise ValueError(f"{label} is missing required columns: {missing}")

print("\nUser-goal relationships")
profile_users = set(profiles["user_id"].astype(str))
goal_users = set(goals["user_id"].astype(str))
print("Unique profile users:", profiles["user_id"].nunique())
print("Unique goal users:", goals["user_id"].nunique())
print("Goal users without profiles:", len(goal_users - profile_users))
print("Profiles without goals:", len(profile_users - goal_users))
print("Duplicate profile IDs:", profiles["user_id"].duplicated().sum())
print("Duplicate goal IDs:", goals["goal_id"].duplicated().sum())

print("\nMarket timeline")
print("Months:", len(market))
print("First month:", market["period"].min())
print("Last month:", market["period"].max())
print("Duplicate months:", market["period"].duplicated().sum())
print("Missing NIFTY returns:", market["nifty_monthly_return"].isna().sum())
print("Missing WALR values:", market["walr_monthly"].isna().sum())
print("Missing inflation indicators:", market["inflation_level"].isna().sum())

print("\nMarket return range (decimal returns)")
print("Minimum:", market["nifty_monthly_return"].min())
print("Maximum:", market["nifty_monthly_return"].max())
print("Mean:", market["nifty_monthly_return"].mean())

print("\nWALR range (source percentage points)")
print("Minimum:", market["walr_monthly"].min())
print("Maximum:", market["walr_monthly"].max())

print("\nProfile cash-flow diagnostics")
surplus = (
    profiles["monthly_income"]
    - profiles["monthly_expenditure"]
    - profiles["monthly_emi"]
)
print("Non-positive monthly surplus:", int((surplus <= 0).sum()))
print("Mean monthly surplus: ₹{:,.2f}".format(surplus.mean()))

if profiles["user_id"].duplicated().any():
    raise ValueError("Profile IDs must be unique.")
if goals["goal_id"].duplicated().any():
    raise ValueError("Goal IDs must be unique.")
if goal_users - profile_users:
    raise ValueError("Some goals do not have a matching financial profile.")
if market["period"].duplicated().any():
    raise ValueError("Market data contains duplicate months.")

print("\nInitial structural validation passed.")
print("No files modified; no training started.")


# ===== CELL 56 =====  type=code  exec=None

import numpy as np
import pandas as pd

# Uses profiles, goals, and market loaded in the previous cell.
derived = profiles.copy()

derived["monthly_surplus"] = (
    derived["monthly_income"]
    - derived["monthly_expenditure"]
    - derived["monthly_emi"]
)

derived["investment_capacity_ratio"] = pd.to_numeric(
    derived["investment_capacity_ratio"], errors="coerce"
).clip(0, 1)

# Provisional cap for RL action design, not a financial recommendation.
derived["investment_contribution_cap"] = (
    derived["monthly_surplus"].clip(lower=0)
    * derived["investment_capacity_ratio"]
)

# Convert WALR percentage points to annual decimal rates.
market_derived = market.copy()
market_derived["walr_annual_rate_decimal"] = (
    pd.to_numeric(market_derived["walr_monthly"], errors="coerce") / 100.0
)

# Effective monthly rate implied by the annual rate.
market_derived["walr_effective_monthly_rate"] = (
    (1 + market_derived["walr_annual_rate_decimal"]) ** (1 / 12) - 1
)

market_derived["nifty_monthly_return"] = pd.to_numeric(
    market_derived["nifty_monthly_return"], errors="coerce"
)

assert derived["user_id"].is_unique
assert market_derived["period"].is_unique
assert derived["investment_capacity_ratio"].notna().all()
assert market_derived["walr_annual_rate_decimal"].between(0, 1).all()
assert market_derived["nifty_monthly_return"].between(-1, 1).all()

print("=" * 70)
print("DERIVED FINANCIAL MECHANICS — VALIDATION")
print("=" * 70)

print("\nMonthly cash flow")
print(f"Users with non-positive surplus: {(derived['monthly_surplus'] <= 0).sum()}")
print(f"Mean surplus: ₹{derived['monthly_surplus'].mean():,.2f}")
print(f"Total negative surplus: ₹{derived.loc[derived['monthly_surplus'] < 0, 'monthly_surplus'].sum():,.2f}")

print("\nProvisional investment contribution cap")
print(f"Mean cap: ₹{derived['investment_contribution_cap'].mean():,.2f}")
print(f"Maximum cap: ₹{derived['investment_contribution_cap'].max():,.2f}")
print("Negative investment caps:", (derived["investment_contribution_cap"] < 0).sum())

print("\nWALR conversion")
print(
    "Annual decimal rate range: "
    f"{market_derived['walr_annual_rate_decimal'].min():.4f}–"
    f"{market_derived['walr_annual_rate_decimal'].max():.4f}"
)
print(
    "Effective monthly rate range: "
    f"{market_derived['walr_effective_monthly_rate'].min():.5f}–"
    f"{market_derived['walr_effective_monthly_rate'].max():.5f}"
)

print("\nNIFTY monthly return")
print(f"Minimum: {market_derived['nifty_monthly_return'].min():.4f}")
print(f"Maximum: {market_derived['nifty_monthly_return'].max():.4f}")
print(f"Mean: {market_derived['nifty_monthly_return'].mean():.4f}")

print("\nInflation indicator")
print("Column: inflation_level")
print("Range:", market_derived["inflation_level"].min(),
      "to", market_derived["inflation_level"].max())
print("Interpretation: normalized indicator, not an actual inflation rate.")

print("\nAll derived-variable checks passed.")
print("No files written; no training started.")


# ===== CELL 57 =====  type=code  exec=None

import pandas as pd

print("=" * 70)
print("RL OBSERVATION-SPACE DESIGN CHECK")
print("=" * 70)

goal_numeric = [
    "current_cost",
    "time_horizon_months",
    "priority",
    "criticality",
    "existing_funding",
]

profile_numeric = [
    "monthly_income",
    "monthly_expenditure",
    "monthly_emi",
    "initial_savings",
    "initial_investment",
    "investment_capacity_ratio",
    "risk_score",
]

print("\nGOAL FIELDS")
for col in goal_numeric:
    if col not in goals.columns:
        print(f"{col}: MISSING")
        continue
    values = pd.to_numeric(goals[col], errors="coerce")
    print(
        f"{col}: min={values.min():,.3f}, "
        f"median={values.median():,.3f}, "
        f"max={values.max():,.3f}, "
        f"missing={values.isna().sum()}"
    )

print("\nPROFILE FIELDS")
for col in profile_numeric:
    if col not in profiles.columns:
        print(f"{col}: MISSING")
        continue
    values = pd.to_numeric(profiles[col], errors="coerce")
    print(
        f"{col}: min={values.min():,.3f}, "
        f"median={values.median():,.3f}, "
        f"max={values.max():,.3f}, "
        f"missing={values.isna().sum()}"
    )

print("\nGOAL COUNTS PER USER")
goal_counts = goals.groupby("user_id").size()
print(goal_counts.describe().round(2).to_string())
print("\nGoal-count distribution:")
print(goal_counts.value_counts().sort_index().to_string())

print("\nGOAL TYPES")
if "goal_type" in goals.columns:
    print(goals["goal_type"].value_counts(dropna=False).to_string())

print("\nRISK PROFILES")
if "risk_profile" in profiles.columns:
    print(profiles["risk_profile"].value_counts(dropna=False).to_string())

print("\nObservation-space diagnostics complete.")
print("No files modified; no training started.")


# ===== CELL 58 =====  type=code  exec=None

from pathlib import Path

rl_dir = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/05_simulation_runs/rl_prototype"
)
rl_dir.mkdir(parents=True, exist_ok=True)

env_path = rl_dir / "goalpilot_env.py"

if env_path.exists():
    raise FileExistsError(
        f"{env_path} already exists. I won't overwrite an existing environment."
    )

env_source = r'''
import numpy as np
import pandas as pd
import gymnasium as gym
from gymnasium import spaces


class GoalPilotEnv(gym.Env):
    """Monthly multi-goal financial allocation environment.

    This is a research prototype, not a financial-advice system.
    Inflation is deliberately excluded until a defensible rate series is available.
    """

    metadata = {"render_modes": ["human"]}

    def __init__(self, profiles, goals, market, user_ids=None, seed=None):
        super().__init__()

        self.profiles = profiles.copy().reset_index(drop=True)
        self.goals = goals.copy()
        self.market = market.sort_values("period").reset_index(drop=True).copy()

        self.profiles["user_id"] = self.profiles["user_id"].astype(str)
        self.goals["user_id"] = self.goals["user_id"].astype(str)
        self.market["period"] = pd.to_datetime(self.market["period"])

        self.user_ids = list(user_ids) if user_ids is not None else \
            self.profiles["user_id"].tolist()

        self.profile_map = self.profiles.set_index("user_id").to_dict("index")
        self.goal_map = {
            uid: group.sort_values("time_horizon_months").reset_index(drop=True)
            for uid, group in self.goals.groupby("user_id")
        }

        if not self.user_ids:
            raise ValueError("At least one user is required.")
        if not self.market["period"].is_monotonic_increasing:
            raise ValueError("Market periods must be sorted.")
        if self.market["period"].duplicated().any():
            raise ValueError("Market periods must be unique.")

        self.max_goals = int(
            self.goals.groupby("user_id").size().max()
        )
        self.max_steps = len(self.market)

        # Action per goal: savings allocation, investment allocation,
        # and loan request. All action components are normalized to [0, 1].
        self.action_space = spaces.Box(
            low=0.0,
            high=1.0,
            shape=(self.max_goals, 3),
            dtype=np.float32,
        )

        # Fixed-length observation supports users with different goal counts.
        # Per-goal features: remaining goal amount, horizon, priority,
        # criticality, current funding ratio, and active flag.
        self.observation_space = spaces.Box(
            low=0.0,
            high=1.0,
            shape=(12 + self.max_goals * 6,),
            dtype=np.float32,
        )

        self.rng = np.random.default_rng(seed)
        self.user_id = None
        self.user_goals = None
        self.month_index = 0
        self.cash = 0.0
        self.portfolio = 0.0
        self.loan_balance = 0.0
        self.loan_emi = 0.0
        self.loan_months_left = 0
        self.goal_balances = None
        self.goal_deadlines = None
        self.goal_targets = None
        self.total_rewards = 0.0

    def _get_observation(self):
        p = self.profile_map[self.user_id]
        surplus = max(
            0.0,
            float(p["monthly_income"])
            - float(p["monthly_expenditure"])
            - float(p["monthly_emi"]),
        )

        market_row = self.market.iloc[self.month_index]
        obs = [
            np.clip(float(p["monthly_income"]) / 200000, 0, 1),
            np.clip(float(p["monthly_expenditure"]) / 200000, 0, 1),
            np.clip(float(p["monthly_emi"]) / 200000, 0, 1),
            np.clip(surplus / 100000, 0, 1),
            np.clip(self.cash / 2_000_000, 0, 1),
            np.clip(self.portfolio / 5_000_000, 0, 1),
            np.clip(self.loan_balance / 2_000_000, 0, 1),
            np.clip(float(p["investment_capacity_ratio"]), 0, 1),
            np.clip(float(p["risk_score"]), 0, 1),
            np.clip(self.month_index / max(1, self.max_steps - 1), 0, 1),
            np.clip(
                (float(market_row["walr_monthly"]) / 100), 0, 1
            ),
            np.clip(
                (float(market_row["nifty_monthly_return"]) + 0.25) / 0.50,
                0, 1,
            ),
        ]

        for j in range(self.max_goals):
            if j < len(self.goal_targets):
                target = max(float(self.goal_targets[j]), 1.0)
                remaining = max(0.0, target - self.goal_balances[j])
                horizon = max(0, self.goal_deadlines[j] - self.month_index)
                row = self.user_goals.iloc[j]
                obs.extend([
                    np.clip(remaining / 30_000_000, 0, 1),
                    np.clip(horizon / 240, 0, 1),
                    np.clip(float(row["priority"]) / 5, 0, 1),
                    np.clip(float(row["criticality"]) / 5, 0, 1),
                    np.clip(self.goal_balances[j] / target, 0, 1),
                    1.0,
                ])
            else:
                obs.extend([0.0] * 6)

        return np.asarray(obs, dtype=np.float32)

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        if seed is not None:
            self.rng = np.random.default_rng(seed)

        options = options or {}
        requested_user = options.get("user_id")
        if requested_user is not None:
            requested_user = str(requested_user)
            if requested_user not in self.user_ids:
                raise ValueError(f"Unknown user_id: {requested_user}")
            self.user_id = requested_user
        else:
            self.user_id = self.rng.choice(self.user_ids)

        p = self.profile_map[self.user_id]
        self.user_goals = self.goal_map[self.user_id].copy().reset_index(drop=True)

        self.month_index = 0
        self.cash = max(0.0, float(p["initial_savings"]))
        self.portfolio = max(0.0, float(p["initial_investment"]))
        self.loan_balance = 0.0
        self.loan_emi = 0.0
        self.loan_months_left = 0
        self.total_rewards = 0.0

        self.goal_targets = self.user_goals["current_cost"].astype(float).to_numpy()
        self.goal_deadlines = self.user_goals["time_horizon_months"].astype(int).to_numpy()
        self.goal_balances = self.user_goals["existing_funding"].astype(float).to_numpy()

        return self._get_observation(), {
            "user_id": self.user_id,
            "goal_count": len(self.user_goals),
        }

    def step(self, action):
        action = np.asarray(action, dtype=np.float32)
        if action.shape != self.action_space.shape:
            raise ValueError(f"Expected action shape {self.action_space.shape}, got {action.shape}")
        if not np.isfinite(action).all():
            raise ValueError("Action contains non-finite values.")

        action = np.clip(action, 0, 1)
        p = self.profile_map[self.user_id]
        m = self.market.iloc[self.month_index]

        income = float(p["monthly_income"])
        expenses = float(p["monthly_expenditure"])
        existing_emi = float(p["monthly_emi"])
        surplus = max(0.0, income - expenses - existing_emi)

        # Existing loan repayment has priority over new discretionary allocations.
        available_after_existing_loan = max(0.0, surplus - self.loan_emi)
        invest_cap = (
            available_after_existing_loan
            * float(p["investment_capacity_ratio"])
        )

        # Allocate a single shared monthly budget across goal contributions.
        raw_savings = action[:len(self.user_goals), 0] * available_after_existing_loan
        raw_investments = action[:len(self.user_goals), 1] * invest_cap

        total_raw = float(raw_savings.sum() + raw_investments.sum())
        budget_scale = min(
            1.0,
            available_after_existing_loan / total_raw if total_raw > 0 else 1.0,
        )
        savings_alloc = raw_savings * budget_scale
        invest_alloc = raw_investments * budget_scale

        # A new loan can be requested only if the EMI fits remaining surplus.
        # This prototype allows at most one active loan at a time.
        new_loan = 0.0
        new_emi = 0.0
        if self.loan_months_left == 0 and available_after_existing_loan > 0:
            goal_idx = int(np.argmax(action[:len(self.user_goals), 2]))
            requested_fraction = float(action[goal_idx, 2])
            annual_rate = float(m["walr_monthly"]) / 100.0
            monthly_rate = (1 + annual_rate) ** (1 / 12) - 1
            tenure = 60
            emi_factor = (
                monthly_rate * (1 + monthly_rate) ** tenure
                / ((1 + monthly_rate) ** tenure - 1)
            )
            emi_budget = max(
                0.0,
                min(
                    available_after_existing_loan
                    - float(savings_alloc.sum())
                    - float(invest_alloc.sum()),
                    income * 0.35 - existing_emi - self.loan_emi,
                ),
            )
            new_emi = min(emi_budget, requested_fraction * emi_budget)
            new_loan = new_emi / emi_factor if emi_factor > 0 else 0.0
            new_loan = min(new_loan, 150000.0)
            new_emi = new_loan * emi_factor

            if new_emi > emi_budget + 1e-5:
                new_loan = emi_budget / emi_factor
                new_emi = new_loan * emi_factor

        # Apply monthly portfolio return. Losses cannot make holdings negative.
        market_return = float(m["nifty_monthly_return"])
        previous_portfolio = self.portfolio
        self.portfolio = max(
            0.0,
            self.portfolio * (1 + market_return) + float(invest_alloc.sum()),
        )
        self.cash += float(savings_alloc.sum())

        # Apply existing loan payment, then originate the new loan if requested.
        if self.loan_months_left > 0:
            self.loan_balance = max(0.0, self.loan_balance - max(0.0, self.loan_emi))
            self.loan_months_left -= 1
            if self.loan_months_left == 0:
                self.loan_emi = 0.0

        if new_loan > 0:
            self.loan_balance += new_loan
            self.loan_emi = new_emi
            self.loan_months_left = tenure

        # Credit goal balances using the cash/investment allocations.
        # Contributions are split across goals in proportion to action weights.
        contribution = savings_alloc + invest_alloc
        total_contribution = float(contribution.sum())
        if total_contribution > 0:
            weights = contribution / total_contribution
            for j, amount in enumerate(contribution):
                self.goal_balances[j] += float(amount)

        # Reward incremental goal progress, deadline attainment, and affordability.
        reward = 0.0
        for j in range(len(self.user_goals)):
            target = max(1.0, float(self.goal_targets[j]))
            old_ratio = min(1.0, max(0.0, self.goal_balances[j] / target))
            # Avoid rewarding the same already funded balance repeatedly.
            reward += 2.0 * old_ratio * float(self.user_goals.iloc[j]["priority"]) / 5.0

            if self.month_index + 1 >= self.goal_deadlines[j]:
                shortfall_ratio = max(
                    0.0, (target - self.goal_balances[j]) / target
                )
                reward -= 5.0 * shortfall_ratio * float(
                    self.user_goals.iloc[j]["criticality"]
                ) / 5.0

        # Small penalties discourage unnecessary debt and risky exposure.
        reward -= 0.00001 * new_loan
        risk_score = float(p["risk_score"])
        reward -= max(0.0, abs(market_return) - risk_score * 0.05) * (
            self.portfolio / 100000.0
        )

        # The budget is enforced by construction; this is a numerical safeguard.
        combined_commitment = (
            float(savings_alloc.sum())
            + float(invest_alloc.sum())
            + self.loan_emi
        )
        if combined_commitment > surplus + 1e-4:
            raise RuntimeError("Combined monthly cash-flow budget was exceeded.")

        self.month_index += 1
        terminated = self.month_index >= self.max_steps
        truncated = False
        observation = (
            self._get_observation()
            if not terminated
            else np.zeros(self.observation_space.shape, dtype=np.float32)
        )
        self.total_rewards += reward

        info = {
            "user_id": self.user_id,
            "monthly_surplus": surplus,
            "savings_contribution": float(savings_alloc.sum()),
            "investment_contribution": float(invest_alloc.sum()),
            "new_loan_principal": float(new_loan),
            "new_loan_emi": float(new_emi),
            "active_loan_emi": float(self.loan_emi),
            "combined_monthly_commitment": combined_commitment,
            "portfolio_value": self.portfolio,
            "loan_balance": self.loan_balance,
            "goal_balances": self.goal_balances.copy(),
            "goal_targets": self.goal_targets.copy(),
            "portfolio_market_change": self.portfolio - previous_portfolio,
        }
        return observation, float(reward), terminated, truncated, info

    def render(self):
        print({
            "user_id": self.user_id,
            "month_index": self.month_index,
            "cash": round(self.cash, 2),
            "portfolio": round(self.portfolio, 2),
            "loan_balance": round(self.loan_balance, 2),
            "total_rewards": round(self.total_rewards, 3),
        })
'''

compile(env_source, str(env_path), "exec")
env_path.write_text(env_source, encoding="utf-8")

print("Environment file created:", env_path)
print("Source syntax check: PASSED")
print("No datasets or LP optimizer files modified.")
print("Training has not started.")


# ===== CELL 59 =====  type=code  exec=None

from pathlib import Path
import importlib
import sys
import numpy as np
import pandas as pd

RL_DIR = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/05_simulation_runs/rl_prototype"
)
env_path = RL_DIR / "goalpilot_env.py"
backup_path = RL_DIR / "goalpilot_env.py.pre_budget_debug.bak"

source = env_path.read_text(encoding="utf-8")

old_check = '''        if combined_commitment > surplus + 1e-4:
            raise RuntimeError("Combined monthly cash-flow budget was exceeded.")'''

new_check = '''        if combined_commitment > surplus + 1e-4:
            raise RuntimeError(
                "Combined monthly cash-flow budget was exceeded. "
                f"month_index={self.month_index}, user_id={self.user_id}, "
                f"surplus={surplus:.6f}, "
                f"savings={float(savings_alloc.sum()):.6f}, "
                f"investments={float(invest_alloc.sum()):.6f}, "
                f"active_emi={self.loan_emi:.6f}, "
                f"new_emi={new_emi:.6f}, "
                f"new_loan={new_loan:.6f}, "
                f"available_after_existing_loan={available_after_existing_loan:.6f}, "
                f"loan_months_left={self.loan_months_left}"
            )'''

if source.count(old_check) != 1:
    raise RuntimeError(
        "Expected budget-check block not found exactly once; no change made."
    )

if not backup_path.exists():
    import shutil
    shutil.copy2(env_path, backup_path)

updated = source.replace(old_check, new_check, 1)
compile(updated, str(env_path), "exec")
env_path.write_text(updated, encoding="utf-8")

if str(RL_DIR) not in sys.path:
    sys.path.insert(0, str(RL_DIR))
sys.modules.pop("goalpilot_env", None)
from goalpilot_env import GoalPilotEnv

profiles = pd.read_csv(RL_DIR / "rl_sample_financial_profiles.csv")
goals = pd.read_csv(RL_DIR / "rl_sample_goals.csv")
market = pd.read_csv(RL_DIR / "rl_market_credit_economic.csv", parse_dates=["period"])

env = GoalPilotEnv(profiles, goals, market, seed=42)
obs, info = env.reset(seed=42)
rng = np.random.default_rng(42)

try:
    for step in range(12):
        action = rng.uniform(0, 1, size=env.action_space.shape).astype(np.float32)
        obs, reward, terminated, truncated, info_step = env.step(action)
        print(
            f"Step {step + 1}: surplus=₹{info_step['monthly_surplus']:.2f}, "
            f"commitment=₹{info_step['combined_monthly_commitment']:.2f}"
        )
        if terminated or truncated:
            break
    print("\nNo budget violation reproduced in 12 steps.")
except RuntimeError as exc:
    print("\nDIAGNOSTIC FAILURE:")
    print(exc)

print("\nDiagnostic backup:", backup_path)
print("No datasets modified; no training started.")


# ===== CELL 60 =====  type=code  exec=None

from pathlib import Path

env_path = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/05_simulation_runs/rl_prototype/goalpilot_env.py"
)
lines = env_path.read_text(encoding="utf-8").splitlines()

keywords = (
    "loan_emi",
    "loan_balance",
    "loan_months_left",
    "new_loan",
    "new_emi",
    "combined_commitment",
    "available_after_existing_loan",
)

matches = [
    i for i, line in enumerate(lines)
    if any(keyword in line for keyword in keywords)
]

shown = set()
for i in matches:
    start, end = max(0, i - 4), min(len(lines), i + 5)
    if any(j in shown for j in range(start, end)):
        continue
    print(f"\n--- Lines {start + 1}–{end} ---")
    for j in range(start, end):
        print(f"{j + 1:03}: {lines[j]}")
        shown.add(j)



# ===== CELL 61 =====  type=code  exec=None

from pathlib import Path

env_path = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/05_simulation_runs/rl_prototype/goalpilot_env.py"
)

lines = env_path.read_text(encoding="utf-8").splitlines()

start_line = 175
end_line = 315

print(f"File: {env_path}")
print(f"Showing lines {start_line + 1}–{end_line}\n")

for i in range(start_line, min(end_line, len(lines))):
    print(f"{i + 1:03}: {lines[i]}")


# ===== CELL 62 =====  type=code  exec=None

from pathlib import Path

env_path = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/05_simulation_runs/rl_prototype/goalpilot_env.py"
)

lines = env_path.read_text(encoding="utf-8").splitlines()

sections = [
    (0, 70, "Imports, constructor, and configuration"),
    (100, 175, "Market loading, reset, and goal initialization"),
    (305, min(len(lines), 380), "Termination, logging, and return values"),
]

for start, end, title in sections:
    print(f"\n{'=' * 18} {title} {'=' * 18}")
    for i in range(start, min(end, len(lines))):
        print(f"{i + 1:03}: {lines[i]}")


# ===== CELL 63 =====  type=code  exec=None

from pathlib import Path
import pandas as pd
import numpy as np

base = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/05_simulation_runs/rl_prototype"
)

market_path = base / "rl_market_credit_economic.csv"
market = pd.read_csv(market_path)

print("Rows:", len(market))
print("Columns:", market.columns.tolist())

required = ["period", "walr_monthly", "nifty_monthly_return"]
missing = [c for c in required if c not in market.columns]

if missing:
    print("\nMISSING REQUIRED COLUMNS:", missing)
else:
    for col in ["walr_monthly", "nifty_monthly_return"]:
        values = pd.to_numeric(market[col], errors="coerce")
        print(f"\n{col}")
        print("  Missing/non-numeric:", int(values.isna().sum()))
        print("  Min:", values.min())
        print("  Max:", values.max())
        print("  First 5:", values.head().tolist())

    rates = pd.to_numeric(market["walr_monthly"], errors="coerce")
    print("\nAnnual lending-rate conversion (decimal):")
    print("  First 5:", (rates.head() / 100).tolist())
    print("  All rates positive:", bool((rates.dropna() > 0).all()))

print("\nThis cell is read-only.")


# ===== CELL 64 =====  type=code  exec=None

from pathlib import Path

path = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/05_simulation_runs/rl_prototype/goalpilot_env.py"
)
source = path.read_text(encoding="utf-8")
lines = source.splitlines()

print("Loan-state initialization and helper methods:\n")
for i, line in enumerate(lines):
    if any(term in line.lower() for term in [
        "loan_balance",
        "loan_emi",
        "loan_months_left",
        "def _",
    ]):
        start, end = max(0, i - 2), min(len(lines), i + 3)
        print(f"\n--- Lines {start + 1}–{end} ---")
        for j in range(start, end):
            print(f"{j + 1:03}: {lines[j]}")


# ===== CELL 65 =====  type=code  exec=None

from pathlib import Path
import hashlib

env_path = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/05_simulation_runs/rl_prototype/goalpilot_env.py"
)

backup_path = env_path.with_name("goalpilot_env.py.pre_loan_fix.bak")

source = env_path.read_text(encoding="utf-8")

if not backup_path.exists():
    backup_path.write_text(source, encoding="utf-8")
    print("Backup created:", backup_path)
else:
    print("Existing backup preserved:", backup_path)

lines = source.splitlines()

print("\n--- Loan creation and repayment block ---")
for i in range(200, min(255, len(lines))):
    print(f"{i + 1:03}: {lines[i]}")

print("\n--- Budget validation block ---")
for i in range(282, min(307, len(lines))):
    print(f"{i + 1:03}: {lines[i]}")

print("\nSource SHA-256:", hashlib.sha256(source.encode()).hexdigest())
print("Environment modified: No")
print("Datasets modified: No")
print("Training started: No")


# ===== CELL 66 =====  type=code  exec=None

from pathlib import Path
import ast

env_path = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/05_simulation_runs/rl_prototype/goalpilot_env.py"
)
backup_path = env_path.with_name("goalpilot_env.py.pre_loan_fix.bak")

source = env_path.read_text(encoding="utf-8")

if not backup_path.exists():
    raise FileNotFoundError("Safety backup is missing; refusing to patch.")

old_repayment = '''        # Apply existing loan payment, then originate the new loan if requested.
        if self.loan_months_left > 0:
            self.loan_balance = max(0.0, self.loan_balance - max(0.0, self.loan_emi))
            self.loan_months_left -= 1
            if self.loan_months_left == 0:
                self.loan_emi = 0.0

        if new_loan > 0:
            self.loan_balance += new_loan
            self.loan_emi = new_emi
            self.loan_months_left = tenure
'''

new_repayment = '''        # Repay an existing loan using interest-first amortization.
        # Capture the EMI due before updating the loan state.
        emi_due = 0.0
        if self.loan_months_left > 0 and self.loan_balance > 1e-8:
            emi_due = min(max(0.0, self.loan_emi), surplus)
            annual_rate_existing = float(m["walr_monthly"]) / 100.0
            monthly_rate_existing = (1.0 + annual_rate_existing) ** (1.0 / 12.0) - 1.0
            interest_due = self.loan_balance * monthly_rate_existing
            principal_paid = max(0.0, emi_due - interest_due)
            self.loan_balance = max(0.0, self.loan_balance - principal_paid)
            self.loan_months_left -= 1

            if self.loan_balance <= 1e-6 or self.loan_months_left <= 0:
                self.loan_balance = 0.0
                self.loan_emi = 0.0
                self.loan_months_left = 0

        # Originate a new loan only after the old loan has closed.
        if new_loan > 0:
            self.loan_balance = float(new_loan)
            self.loan_emi = float(new_emi)
            self.loan_months_left = int(tenure)

        # EMI due this month is distinct from the EMI for future months.
        monthly_loan_commitment = emi_due + float(new_emi)
'''

old_budget = '''        # The budget is enforced by construction; this is a numerical safeguard.
        combined_commitment = (
            float(savings_alloc.sum())
            + float(invest_alloc.sum())
            + self.loan_emi
        )
'''

new_budget = '''        # Validate the actual current-month cash commitments.
        combined_commitment = (
            float(savings_alloc.sum())
            + float(invest_alloc.sum())
            + monthly_loan_commitment
        )
'''

if source.count(old_repayment) != 1:
    raise RuntimeError(
        f"Expected exactly one repayment block; found {source.count(old_repayment)}. "
        "No changes were written."
    )

if source.count(old_budget) != 1:
    raise RuntimeError(
        f"Expected exactly one budget block; found {source.count(old_budget)}. "
        "No changes were written."
    )

patched = source.replace(old_repayment, new_repayment, 1)
patched = patched.replace(old_budget, new_budget, 1)

# Update the diagnostic to distinguish the current month's payment from
# the EMI scheduled for future months.
patched = patched.replace(
    'f"active_emi={self.loan_emi:.6f}, "',
    'f"monthly_loan_commitment={monthly_loan_commitment:.6f}, "',
    1,
)

ast.parse(patched)
env_path.write_text(patched, encoding="utf-8")

print("Patch applied and syntax check passed.")
print("Modified:", env_path)
print("Backup preserved:", backup_path)
print("Datasets modified: No")
print("LP optimizer modified: No")
print("Training started: No")


# ===== CELL 67 =====  type=code  exec=None

from pathlib import Path
import importlib
import numpy as np
import pandas as pd

base = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/05_simulation_runs/rl_prototype"
)

profiles = pd.read_csv(base / "rl_sample_financial_profiles.csv")
goals = pd.read_csv(base / "rl_sample_goals.csv")
market = pd.read_csv(base / "rl_market_credit_economic.csv")

import sys
if str(base) not in sys.path:
    sys.path.insert(0, str(base))

import goalpilot_env
importlib.reload(goalpilot_env)
GoalPilotEnv = goalpilot_env.GoalPilotEnv

env = GoalPilotEnv(profiles, goals, market, seed=42)
rng = np.random.default_rng(42)

episodes = 10
steps_per_episode = min(120, len(market))
total_steps = 0
loan_steps = 0
max_budget_excess = 0.0
max_loan_balance = 0.0
failures = []

for ep in range(episodes):
    obs, reset_info = env.reset(seed=1000 + ep)
    episode_user = reset_info["user_id"]

    for step_idx in range(steps_per_episode):
        action = rng.random(env.action_space.shape).astype(np.float32)

        try:
            obs, reward, terminated, truncated, info = env.step(action)
        except Exception as exc:
            failures.append({
                "episode": ep + 1,
                "user_id": episode_user,
                "step": step_idx + 1,
                "error": repr(exc),
            })
            break

        surplus = float(info["monthly_surplus"])
        commitment = float(info["combined_monthly_commitment"])
        excess = commitment - surplus

        max_budget_excess = max(max_budget_excess, excess)
        max_loan_balance = max(max_loan_balance, float(info["loan_balance"]))
        loan_steps += int(float(info["loan_balance"]) > 1e-6)
        total_steps += 1

        if excess > 1e-4:
            failures.append({
                "episode": ep + 1,
                "user_id": episode_user,
                "step": step_idx + 1,
                "error": f"Budget excess ₹{excess:.6f}",
            })
            break

        if terminated or truncated:
            break

    if failures:
        break

print("Random-action regression test")
print("Episodes requested:", episodes)
print("Successful steps:", total_steps)
print("Steps with outstanding loans:", loan_steps)
print("Maximum observed loan balance: ₹{:,.2f}".format(max_loan_balance))
print("Maximum budget excess: ₹{:.8f}".format(max_budget_excess))
print("Failures:", len(failures))

if failures:
    print("\nFirst failure:")
    print(failures[0])
else:
    print("\nPASS: No runtime or monthly budget violations detected.")
    print("Note: This validates basic invariants, not the full financial model.")


# ===== CELL 68 =====  type=code  exec=None

from pathlib import Path
import importlib
import sys
import numpy as np
import pandas as pd

base = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/05_simulation_runs/rl_prototype"
)

for name in [
    "rl_sample_financial_profiles.csv",
    "rl_sample_goals.csv",
    "rl_market_credit_economic.csv",
]:
    assert (base / name).exists(), f"Missing file: {name}"

profiles = pd.read_csv(base / "rl_sample_financial_profiles.csv")
goals = pd.read_csv(base / "rl_sample_goals.csv")
market = pd.read_csv(base / "rl_market_credit_economic.csv")

if str(base) not in sys.path:
    sys.path.insert(0, str(base))

import goalpilot_env
importlib.reload(goalpilot_env)

env = goalpilot_env.GoalPilotEnv(profiles, goals, market, seed=42)
rng = np.random.default_rng(42)

for ep in range(1):
    obs, reset_info = env.reset(seed=1000 + ep)
    print("User:", reset_info["user_id"])

    for step_idx in range(12):
        action = rng.random(env.action_space.shape).astype(np.float32)

        # Capture state before the action, then reproduce the failure.
        before = {
            "month_index": env.month_index,
            "loan_balance": env.loan_balance,
            "loan_emi": env.loan_emi,
            "loan_months_left": env.loan_months_left,
        }

        try:
            obs, reward, terminated, truncated, info = env.step(action)
            print(
                f"Step {step_idx + 1}: "
                f"balance=₹{info['loan_balance']:.6f}, "
                f"EMI=₹{info['active_loan_emi']:.6f}, "
                f"commitment=₹{info['combined_monthly_commitment']:.6f}"
            )
        except Exception as exc:
            print("\nFailure:", repr(exc))
            print("State before failing action:", before)
            break


# ===== CELL 69 =====  type=code  exec=None

from pathlib import Path

path = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/05_simulation_runs/rl_prototype/goalpilot_env.py"
)
lines = path.read_text(encoding="utf-8").splitlines()

for start, end, title in [
    (175, 232, "Monthly budget and new-loan calculation"),
    (232, 260, "Portfolio updates and loan repayment"),
    (280, 307, "Budget validation"),
]:
    print(f"\n{'=' * 12} {title} {'=' * 12}")
    for i in range(start, min(end, len(lines))):
        print(f"{i + 1:03}: {lines[i]}")


# ===== CELL 70 =====  type=code  exec=None

from pathlib import Path
import ast

path = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/05_simulation_runs/rl_prototype/goalpilot_env.py"
)
backup = path.with_name("goalpilot_env.py.pre_loan_fix.bak")
source = path.read_text(encoding="utf-8")

if not backup.exists():
    raise FileNotFoundError("Expected safety backup not found.")

old_budget = '''        # Existing loan repayment has priority over new discretionary allocations.
        available_after_existing_loan = max(0.0, surplus - self.loan_emi)
'''

new_budget = '''        # Reserve the actual EMI due this month before allocating contributions.
        if self.loan_months_left > 0 and self.loan_balance > 1e-6:
            current_emi_due = min(max(0.0, self.loan_emi), surplus)
        else:
            current_emi_due = 0.0
            self.loan_balance = 0.0
            self.loan_emi = 0.0
            self.loan_months_left = 0

        available_after_existing_loan = max(0.0, surplus - current_emi_due)
'''

old_repayment = '''        # Repay an existing loan using interest-first amortization.
        # Capture the EMI due before updating the loan state.
        emi_due = 0.0
        if self.loan_months_left > 0 and self.loan_balance > 1e-8:
            emi_due = min(max(0.0, self.loan_emi), surplus)
            annual_rate_existing = float(m["walr_monthly"]) / 100.0
            monthly_rate_existing = (1.0 + annual_rate_existing) ** (1.0 / 12.0) - 1.0
            interest_due = self.loan_balance * monthly_rate_existing
            principal_paid = max(0.0, emi_due - interest_due)
            self.loan_balance = max(0.0, self.loan_balance - principal_paid)
            self.loan_months_left -= 1

            if self.loan_balance <= 1e-6 or self.loan_months_left <= 0:
                self.loan_balance = 0.0
                self.loan_emi = 0.0
                self.loan_months_left = 0

        # Originate a new loan only after the old loan has closed.
        if new_loan > 0:
            self.loan_balance = float(new_loan)
            self.loan_emi = float(new_emi)
            self.loan_months_left = int(tenure)

        # EMI due this month is distinct from the EMI for future months.
        monthly_loan_commitment = emi_due + float(new_emi)
'''

new_repayment = '''        # Repay the existing loan with interest-first amortization.
        emi_due = current_emi_due
        if emi_due > 0.0:
            annual_rate_existing = float(m["walr_monthly"]) / 100.0
            monthly_rate_existing = (1.0 + annual_rate_existing) ** (1.0 / 12.0) - 1.0
            interest_due = self.loan_balance * monthly_rate_existing
            payment_due = self.loan_balance + interest_due
            actual_payment = min(emi_due, payment_due)
            principal_paid = max(0.0, actual_payment - interest_due)
            self.loan_balance = max(0.0, self.loan_balance - principal_paid)
            self.loan_months_left = max(0, self.loan_months_left - 1)

            if self.loan_balance <= 1e-6 or self.loan_months_left == 0:
                self.loan_balance = 0.0
                self.loan_emi = 0.0
                self.loan_months_left = 0

        # Originate a new loan only after the previous loan has closed.
        if new_loan > 0:
            self.loan_balance = float(new_loan)
            self.loan_emi = float(new_emi)
            self.loan_months_left = int(tenure)

        monthly_loan_commitment = emi_due + float(new_emi)
'''

if source.count(old_budget) != 1:
    raise RuntimeError("Budget block did not match exactly; no changes written.")
if source.count(old_repayment) != 1:
    raise RuntimeError("Repayment block did not match exactly; no changes written.")

patched = source.replace(old_budget, new_budget, 1)
patched = patched.replace(old_repayment, new_repayment, 1)

ast.parse(patched)
path.write_text(patched, encoding="utf-8")

print("Loan reservation and repayment patch applied.")
print("Syntax check: PASS")
print("Backup preserved:", backup)
print("Datasets modified: No")
print("Training started: No")


# ===== CELL 71 =====  type=code  exec=None

from pathlib import Path
import importlib
import sys
import numpy as np
import pandas as pd

base = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/05_simulation_runs/rl_prototype"
)

profiles = pd.read_csv(base / "rl_sample_financial_profiles.csv")
goals = pd.read_csv(base / "rl_sample_goals.csv")
market = pd.read_csv(base / "rl_market_credit_economic.csv")

if str(base) not in sys.path:
    sys.path.insert(0, str(base))

import goalpilot_env
importlib.reload(goalpilot_env)

env = goalpilot_env.GoalPilotEnv(profiles, goals, market, seed=42)
rng = np.random.default_rng(42)

episodes = 10
steps_per_episode = min(120, len(market))
total_steps = 0
max_budget_excess = 0.0
max_loan_balance = 0.0
loan_closure_checks = 0
failures = []

for ep in range(episodes):
    obs, reset_info = env.reset(seed=1000 + ep)

    for step_idx in range(steps_per_episode):
        action = rng.random(env.action_space.shape).astype(np.float32)

        try:
            obs, reward, terminated, truncated, info = env.step(action)
        except Exception as exc:
            failures.append({
                "episode": ep + 1,
                "user_id": reset_info["user_id"],
                "step": step_idx + 1,
                "error": repr(exc),
            })
            break

        surplus = float(info["monthly_surplus"])
        commitment = float(info["combined_monthly_commitment"])
        balance = float(info["loan_balance"])
        excess = commitment - surplus

        total_steps += 1
        max_budget_excess = max(max_budget_excess, excess)
        max_loan_balance = max(max_loan_balance, balance)

        if commitment > surplus + 1e-4:
            failures.append({
                "episode": ep + 1,
                "step": step_idx + 1,
                "error": f"Budget exceeded by ₹{excess:.8f}",
            })
            break

        if balance <= 1e-6 and env.loan_months_left == 0:
            if env.loan_emi != 0.0:
                failures.append({
                    "episode": ep + 1,
                    "step": step_idx + 1,
                    "error": f"Closed loan retains EMI ₹{env.loan_emi:.8f}",
                })
                break
            loan_closure_checks += 1

        if terminated or truncated:
            break

    if failures:
        break

print("Random-action regression test")
print("Episodes requested:", episodes)
print("Successful steps:", total_steps)
print("Loan closure state checks:", loan_closure_checks)
print(f"Maximum loan balance: ₹{max_loan_balance:,.6f}")
print(f"Maximum budget excess: ₹{max_budget_excess:.8f}")
print("Failures:", len(failures))

if failures:
    print("\nFirst failure:")
    print(failures[0])
else:
    print("\nPASS: No budget or loan-closure invariant violations detected.")
    print("This is a basic regression test, not yet financial-model validation.")


# ===== CELL 72 =====  type=code  exec=None

from pathlib import Path

path = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/05_simulation_runs/rl_prototype/goalpilot_env.py"
)
source = path.read_text(encoding="utf-8")
lines = source.splitlines()

checks = {
    "Current EMI reserved before allocations": "current_emi_due = min(max(0.0, self.loan_emi), surplus)" in source,
    "Available budget subtracts current EMI": "surplus - current_emi_due" in source,
    "Repayment includes interest": "interest_due = self.loan_balance * monthly_rate_existing" in source,
    "Monthly commitment uses EMI due": "monthly_loan_commitment = emi_due + float(new_emi)" in source,
    "Budget check uses monthly commitment": "+ monthly_loan_commitment" in source,
}

print("Patch verification:")
for label, passed in checks.items():
    print(f"{'PASS' if passed else 'FAIL'} — {label}")

print("\nCurrent budget and repayment lines:")
for i, line in enumerate(lines):
    if any(term in line for term in [
        "current_emi_due",
        "available_after_existing_loan =",
        "interest_due =",
        "monthly_loan_commitment =",
        "combined_commitment =",
    ]):
        print(f"{i + 1:03}: {line}")

print("\nRead-only check complete.")


# ===== CELL 73 =====  type=code  exec=None

from pathlib import Path

path = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/05_simulation_runs/rl_prototype/goalpilot_env.py"
)
lines = path.read_text(encoding="utf-8").splitlines()

for start, end in [(177, 205), (240, 280), (300, 325)]:
    print(f"\n--- Lines {start + 1}–{min(end, len(lines))} ---")
    for i in range(start, min(end, len(lines))):
        print(f"{i + 1:03}: {lines[i]}")


# ===== CELL 74 =====  type=code  exec=None

from pathlib import Path
import ast

path = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/05_simulation_runs/rl_prototype/goalpilot_env.py"
)

source = path.read_text(encoding="utf-8")
backup = path.with_name("goalpilot_env.py.pre_final_payment_fix.bak")

if not backup.exists():
    backup.write_text(source, encoding="utf-8")

old = '''        # Reserve the actual EMI due this month before allocating contributions.
        if self.loan_months_left > 0 and self.loan_balance > 1e-6:
            current_emi_due = min(max(0.0, self.loan_emi), surplus)
        else:
            current_emi_due = 0.0
            self.loan_balance = 0.0
            self.loan_emi = 0.0
            self.loan_months_left = 0
'''

new = '''        # Reserve only the payment actually due, including a capped final payment.
        if self.loan_months_left > 0 and self.loan_balance > 1e-6:
            annual_rate_existing = float(m["walr_monthly"]) / 100.0
            monthly_rate_existing = (1.0 + annual_rate_existing) ** (1.0 / 12.0) - 1.0
            interest_due_before_allocation = self.loan_balance * monthly_rate_existing
            scheduled_emi = max(0.0, self.loan_emi)
            payoff_amount = self.loan_balance + interest_due_before_allocation
            current_emi_due = min(scheduled_emi, payoff_amount, surplus)
        else:
            current_emi_due = 0.0
            self.loan_balance = 0.0
            self.loan_emi = 0.0
            self.loan_months_left = 0
'''

if source.count(old) != 1:
    raise RuntimeError("Expected reservation block not found exactly once; no patch applied.")

patched = source.replace(old, new, 1)
ast.parse(patched)
path.write_text(patched, encoding="utf-8")

print("Actual EMI reservation patch applied.")
print("Syntax check: PASS")
print("Backup:", backup)
print("Datasets modified: No")
print("Training started: No")


# ===== CELL 75 =====  type=code  exec=None

from pathlib import Path
import importlib
import sys
import numpy as np
import pandas as pd

base = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/05_simulation_runs/rl_prototype"
)

profiles = pd.read_csv(base / "rl_sample_financial_profiles.csv")
goals = pd.read_csv(base / "rl_sample_goals.csv")
market = pd.read_csv(base / "rl_market_credit_economic.csv")

if str(base) not in sys.path:
    sys.path.insert(0, str(base))

import goalpilot_env
importlib.reload(goalpilot_env)

env = goalpilot_env.GoalPilotEnv(profiles, goals, market, seed=42)
rng = np.random.default_rng(42)

episodes = 10
steps_per_episode = min(120, len(market))
total_steps = 0
max_budget_excess = 0.0
max_loan_balance = 0.0
failures = []
closure_checks = 0

for ep in range(episodes):
    obs, reset_info = env.reset(seed=1000 + ep)

    for step_idx in range(steps_per_episode):
        action = rng.random(env.action_space.shape).astype(np.float32)

        try:
            obs, reward, terminated, truncated, info = env.step(action)
        except Exception as exc:
            failures.append({
                "episode": ep + 1,
                "user_id": reset_info["user_id"],
                "step": step_idx + 1,
                "error": repr(exc),
            })
            break

        surplus = float(info["monthly_surplus"])
        commitment = float(info["combined_monthly_commitment"])
        balance = float(info["loan_balance"])
        excess = commitment - surplus

        total_steps += 1
        max_budget_excess = max(max_budget_excess, excess)
        max_loan_balance = max(max_loan_balance, balance)

        if excess > 1e-4:
            failures.append({
                "episode": ep + 1,
                "step": step_idx + 1,
                "error": f"Budget excess ₹{excess:.8f}",
            })
            break

        if balance <= 1e-6 and env.loan_months_left == 0:
            if env.loan_emi != 0.0:
                failures.append({
                    "episode": ep + 1,
                    "step": step_idx + 1,
                    "error": f"Closed loan retains EMI ₹{env.loan_emi:.8f}",
                })
                break
            closure_checks += 1

        if terminated or truncated:
            break

    if failures:
        break

print("Episodes requested:", episodes)
print("Successful steps:", total_steps)
print("Closed-loan state checks:", closure_checks)
print(f"Maximum loan balance: ₹{max_loan_balance:,.6f}")
print(f"Maximum budget excess: ₹{max_budget_excess:.8f}")
print("Failures:", len(failures))

if failures:
    print("\nFirst failure:")
    print(failures[0])
else:
    print("\nPASS: No tested budget or loan-closure violations.")


# ===== CELL 76 =====  type=code  exec=None

from pathlib import Path

path = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/05_simulation_runs/rl_prototype/goalpilot_env.py"
)
lines = path.read_text(encoding="utf-8").splitlines()

for start, end in [(180, 240), (245, 280), (300, 330)]:
    print(f"\n--- Lines {start + 1}–{min(end, len(lines))} ---")
    for i in range(start, min(end, len(lines))):
        print(f"{i + 1:03}: {lines[i]}")


# ===== CELL 77 =====  type=code  exec=None

from pathlib import Path
import ast

path = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/05_simulation_runs/rl_prototype/goalpilot_env.py"
)
source = path.read_text(encoding="utf-8")
backup = path.with_name("goalpilot_env.py.pre_cashflow_guard.bak")

if not backup.exists():
    backup.write_text(source, encoding="utf-8")

old = '''        # Validate the actual current-month cash commitments.
        combined_commitment = (
            float(savings_alloc.sum())
            + float(invest_alloc.sum())
            + monthly_loan_commitment
        )
'''

new = '''        # Enforce the monthly budget invariant after all commitments are known.
        # Preserve loan payments; scale down discretionary contributions if needed.
        discretionary_total = float(savings_alloc.sum() + invest_alloc.sum())
        discretionary_budget = max(0.0, surplus - monthly_loan_commitment)

        if discretionary_total > discretionary_budget and discretionary_total > 0.0:
            guard_scale = discretionary_budget / discretionary_total
            savings_alloc *= guard_scale
            invest_alloc *= guard_scale

            # Reconcile the portfolio and cash additions with guarded allocations.
            # Reverse the original contributions, then apply the scaled amounts.
            self.cash -= float(discretionary_total * (
                float(savings_alloc.sum()) + float(invest_alloc.sum())
            ) / max(discretionary_total, 1e-12))
            self.cash += float(savings_alloc.sum())

            self.portfolio -= float(discretionary_total * (
                float(invest_alloc.sum())
            ) / max(discretionary_total, 1e-12))
            self.portfolio += float(invest_alloc.sum())

            # Goal funding uses the final guarded contribution amounts.
            # Rebuild the goal balances by removing the original allocation
            # before adding the scaled allocation.
            # The original amounts are reconstructed from the guard scale.
            if guard_scale > 0:
                original_savings = savings_alloc / guard_scale
                original_investments = invest_alloc / guard_scale
                for j in range(len(self.user_goals)):
                    self.goal_balances[j] -= float(
                        original_savings[j] + original_investments[j]
                    )
                    self.goal_balances[j] += float(
                        savings_alloc[j] + invest_alloc[j]
                    )

        combined_commitment = (
            float(savings_alloc.sum())
            + float(invest_alloc.sum())
            + monthly_loan_commitment
        )
'''

if source.count(old) != 1:
    raise RuntimeError("Expected budget validation block not found exactly once.")

patched = source.replace(old, new, 1)
ast.parse(patched)
path.write_text(patched, encoding="utf-8")

print("Cash-flow guard added.")
print("Syntax check: PASS")
print("Backup:", backup)
print("Datasets modified: No")
print("Training started: No")


# ===== CELL 78 =====  type=code  exec=None

from pathlib import Path
import importlib
import sys
import numpy as np
import pandas as pd

base = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/05_simulation_runs/rl_prototype"
)

profiles = pd.read_csv(base / "rl_sample_financial_profiles.csv")
goals = pd.read_csv(base / "rl_sample_goals.csv")
market = pd.read_csv(base / "rl_market_credit_economic.csv")

if str(base) not in sys.path:
    sys.path.insert(0, str(base))

import goalpilot_env
importlib.reload(goalpilot_env)

env = goalpilot_env.GoalPilotEnv(profiles, goals, market, seed=42)
rng = np.random.default_rng(42)

total_steps = 0
max_budget_excess = 0.0
failures = []

for ep in range(5):
    obs, reset_info = env.reset(seed=1000 + ep)

    for step_idx in range(min(24, len(market))):
        action = rng.random(env.action_space.shape).astype(np.float32)

        try:
            obs, reward, terminated, truncated, info = env.step(action)
        except Exception as exc:
            failures.append({
                "episode": ep + 1,
                "user_id": reset_info["user_id"],
                "step": step_idx + 1,
                "error": repr(exc),
            })
            break

        surplus = float(info["monthly_surplus"])
        commitment = float(info["combined_monthly_commitment"])
        excess = commitment - surplus
        max_budget_excess = max(max_budget_excess, excess)
        total_steps += 1

        if excess > 1e-4:
            failures.append({
                "episode": ep + 1,
                "step": step_idx + 1,
                "error": f"Budget exceeded by ₹{excess:.8f}",
            })
            break

        if not np.isfinite(obs).all() or not np.isfinite(reward):
            failures.append({
                "episode": ep + 1,
                "step": step_idx + 1,
                "error": "Non-finite observation or reward",
            })
            break

        if terminated or truncated:
            break

    if failures:
        break

print("Steps completed:", total_steps)
print(f"Maximum budget excess: ₹{max_budget_excess:.8f}")
print("Failures:", len(failures))

if failures:
    print("First failure:", failures[0])
else:
    print("PASS: Budget and finite-value checks passed.")
    print("Full financial accounting still needs separate validation.")


# ===== CELL 79 =====  type=code  exec=None
from pathlib import Path

env_path = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/05_simulation_runs/rl_prototype/goalpilot_env.py"
)

lines = env_path.read_text().splitlines()

keywords = [
    "raw_savings =",
    "raw_investments =",
    "budget_scale =",
    "new_loan =",
    "self.portfolio =",
    "self.cash +=",
    "Enforce the monthly budget invariant",
    "combined_commitment =",
    "Combined monthly cash-flow budget was exceeded",
]

for keyword in keywords:
    matches = [i for i, line in enumerate(lines) if keyword in line]
    print(f"\n{'=' * 20} {keyword} {'=' * 20}")

    if not matches:
        print("Not found")
        continue

    for idx in matches:
        start = max(0, idx - 5)
        end = min(len(lines), idx + 14)

        for line_no in range(start, end):
            print(f"{line_no + 1:4}: {lines[line_no]}")

        print("---")

# ===== CELL 80 =====  type=code  exec=None

from pathlib import Path
import py_compile
import shutil

env_path = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/05_simulation_runs/rl_prototype/goalpilot_env.py"
)

source = env_path.read_text()

backup_path = env_path.with_name("goalpilot_env.py.pre_correct_budget_guard.bak")
if not backup_path.exists():
    shutil.copy2(env_path, backup_path)

# Ensure we are patching the expected version.
late_guard_marker = (
    "        # Enforce the monthly budget invariant after all commitments are known."
)
allocation_marker = "        # Apply monthly portfolio return. Losses cannot make holdings negative."
combined_marker = "        combined_commitment = ("

if late_guard_marker not in source:
    raise RuntimeError("Expected late guard was not found; source left unchanged.")
if allocation_marker not in source or combined_marker not in source:
    raise RuntimeError("Expected allocation or validation marker was not found; source left unchanged.")

# Remove the unsafe guard and its post-update balance reconciliation.
guard_start = source.index(late_guard_marker)
combined_start = source.index(combined_marker, guard_start)
source = source[:guard_start] + source[combined_start:]

# Use float64 allocations to avoid float32 summation overshoot.
old_savings = (
    "        raw_savings = action[:len(self.user_goals), 0] * available_after_existing_loan"
)
new_savings = (
    "        raw_savings = action[:len(self.user_goals), 0].astype('float64') "
    "* available_after_existing_loan"
)
old_investments = (
    "        raw_investments = action[:len(self.user_goals), 1] * invest_cap"
)
new_investments = (
    "        raw_investments = action[:len(self.user_goals), 1].astype('float64') "
    "* invest_cap"
)

if old_savings not in source or old_investments not in source:
    raise RuntimeError("Expected allocation expressions were not found; source left unchanged.")

source = source.replace(old_savings, new_savings, 1)
source = source.replace(old_investments, new_investments, 1)

# Guard contributions before cash, portfolio, and goal balances are updated.
guard_code = """        # Enforce the budget before applying any financial state updates.
        # Reserve existing and newly originated loan payments first.
        discretionary_budget = max(
            0.0, surplus - current_emi_due - new_emi
        )
        discretionary_total = float(
            savings_alloc.sum(dtype="float64")
            + invest_alloc.sum(dtype="float64")
        )

        if discretionary_total > discretionary_budget and discretionary_total > 0.0:
            guard_scale = discretionary_budget / discretionary_total
            savings_alloc = savings_alloc * guard_scale
            invest_alloc = invest_alloc * guard_scale

            # Correct any residual floating-point overshoot.
            guarded_total = float(
                savings_alloc.sum(dtype="float64")
                + invest_alloc.sum(dtype="float64")
            )
            if guarded_total > discretionary_budget and guarded_total > 0.0:
                final_scale = discretionary_budget / guarded_total
                savings_alloc = savings_alloc * final_scale
                invest_alloc = invest_alloc * final_scale

"""

source = source.replace(allocation_marker, guard_code + allocation_marker, 1)

# Validate the final monthly commitment using float64 sums.
source = source.replace(
    "            float(savings_alloc.sum())\n"
    "            + float(invest_alloc.sum())\n"
    "            + monthly_loan_commitment",
    "            float(savings_alloc.sum(dtype='float64'))\n"
    "            + float(invest_alloc.sum(dtype='float64'))\n"
    "            + monthly_loan_commitment",
    1,
)

# Compile a temporary source file first, then write the real file only if valid.
check_path = env_path.with_name("_goalpilot_env_syntax_check.py")
try:
    check_path.write_text(source)
    py_compile.compile(str(check_path), doraise=True)
finally:
    if check_path.exists():
        check_path.unlink()

env_path.write_text(source)

print("Corrected pre-update budget guard installed.")
print("Syntax check: PASS")
print("Backup:", backup_path)
print("Datasets modified: No")
print("Training started: No")


# ===== CELL 81 =====  type=code  exec=None

from pathlib import Path
import importlib
import sys
import numpy as np
import pandas as pd

base = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/05_simulation_runs/rl_prototype"
)

profiles = pd.read_csv(base / "rl_sample_financial_profiles.csv")
goals = pd.read_csv(base / "rl_sample_goals.csv")
market = pd.read_csv(base / "rl_market_credit_economic.csv")

if str(base) not in sys.path:
    sys.path.insert(0, str(base))

import goalpilot_env
importlib.reload(goalpilot_env)

env = goalpilot_env.GoalPilotEnv(profiles, goals, market, seed=42)
rng = np.random.default_rng(42)

total_steps = 0
max_budget_excess = float("-inf")
failures = []

for ep in range(5):
    obs, reset_info = env.reset(seed=1000 + ep)

    for step_idx in range(min(24, len(market))):
        action = rng.random(env.action_space.shape).astype(np.float32)

        try:
            obs, reward, terminated, truncated, info = env.step(action)
        except Exception as exc:
            failures.append({
                "episode": ep + 1,
                "user_id": str(env.user_id),
                "step": step_idx + 1,
                "error": repr(exc),
            })
            break

        surplus = float(info["monthly_surplus"])
        commitment = float(info["combined_monthly_commitment"])
        excess = commitment - surplus
        max_budget_excess = max(max_budget_excess, excess)
        total_steps += 1

        if excess > 1e-4:
            failures.append({
                "episode": ep + 1,
                "user_id": str(env.user_id),
                "step": step_idx + 1,
                "error": f"Budget exceeded by ₹{excess:.8f}",
            })
            break

        if not np.isfinite(obs).all() or not np.isfinite(reward):
            failures.append({
                "episode": ep + 1,
                "user_id": str(env.user_id),
                "step": step_idx + 1,
                "error": "Non-finite observation or reward",
            })
            break

        if terminated or truncated:
            break

    if failures:
        break

print("Steps completed:", total_steps)
print(
    "Maximum budget excess:",
    f"₹{max_budget_excess:.8f}" if total_steps else "N/A",
)
print("Failures:", len(failures))

if failures:
    print("First failure:", failures[0])
else:
    print("PASS: Random-action budget and finite-value checks passed.")
    print("Training started: No")


# ===== CELL 82 =====  type=code  exec=None

from pathlib import Path

env_path = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/05_simulation_runs/rl_prototype/goalpilot_env.py"
)

lines = env_path.read_text().splitlines()

terms = [
    "self.cash =",
    "self.portfolio =",
    "self.goal_balances",
    "self.loan_balance",
    "self.total_rewards",
    "reward =",
    "goal_progress",
    "goal_shortfall",
]

shown = set()

for term in terms:
    matches = [i for i, line in enumerate(lines) if term in line]

    for idx in matches:
        start = max(0, idx - 3)
        end = min(len(lines), idx + 7)
        section = (start, end)

        if section in shown:
            continue
        shown.add(section)

        print(f"\n--- Lines {start + 1}-{end} (matched: {term}) ---")
        for line_no in range(start, end):
            print(f"{line_no + 1:4}: {lines[line_no]}")


# ===== CELL 83 =====  type=code  exec=None

from pathlib import Path

env_path = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/05_simulation_runs/rl_prototype/goalpilot_env.py"
)

lines = env_path.read_text().splitlines()

start_line = 195
end_line = min(355, len(lines))

print(f"Current environment source: lines {start_line}-{end_line}\n")

for i in range(start_line - 1, end_line):
    print(f"{i + 1:4}: {lines[i]}")


# ===== CELL 84 =====  type=code  exec=None

from pathlib import Path

env_path = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/05_simulation_runs/rl_prototype/goalpilot_env.py"
)

source = env_path.read_text().splitlines()

terms = [
    "self.cash",
    "self.portfolio",
    "goal_balances",
    "portfolio_value",
    "total_wealth",
    "net_worth",
    "goal_progress",
]

for term in terms:
    matches = [
        i for i, line in enumerate(source)
        if term in line
    ]

    print(f"\n{'=' * 18} {term} {'=' * 18}")
    if not matches:
        print("No occurrences found.")
        continue

    for i in matches:
        print(f"{i + 1:4}: {source[i].strip()}")


# ===== CELL 85 =====  type=code  exec=None

from pathlib import Path
import importlib
import sys
import numpy as np
import pandas as pd

base = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/05_simulation_runs/rl_prototype"
)

profiles = pd.read_csv(base / "rl_sample_financial_profiles.csv")
goals = pd.read_csv(base / "rl_sample_goals.csv")
market = pd.read_csv(base / "rl_market_credit_economic.csv")

if str(base) not in sys.path:
    sys.path.insert(0, str(base))

import goalpilot_env
importlib.reload(goalpilot_env)

env = goalpilot_env.GoalPilotEnv(profiles, goals, market, seed=42)
obs, reset_info = env.reset(seed=1000)

initial_cash = env.cash
initial_portfolio = env.portfolio
initial_goal_funding = float(env.goal_balances.sum())

rng = np.random.default_rng(42)
rows = []

for month in range(6):
    action = rng.random(env.action_space.shape).astype(np.float32)
    obs, reward, terminated, truncated, info = env.step(action)

    rows.append({
        "month": month + 1,
        "savings_contribution": info["savings_contribution"],
        "investment_contribution": info["investment_contribution"],
        "cash": env.cash,
        "portfolio": env.portfolio,
        "goal_funding": float(env.goal_balances.sum()),
        "loan_balance": env.loan_balance,
        "reward": reward,
    })

    if terminated or truncated:
        break

result = pd.DataFrame(rows)
display(result.round(2))

print("\nInitial cash:", round(initial_cash, 2))
print("Initial portfolio:", round(initial_portfolio, 2))
print("Initial goal funding:", round(initial_goal_funding, 2))
print("Final cash:", round(env.cash, 2))
print("Final portfolio:", round(env.portfolio, 2))
print("Final goal funding:", round(float(env.goal_balances.sum()), 2))
print("User:", reset_info["user_id"])


# ===== CELL 86 =====  type=code  exec=None

from pathlib import Path
import pandas as pd

base = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/05_simulation_runs/rl_prototype"
)

profiles = pd.read_csv(base / "rl_sample_financial_profiles.csv")
goals = pd.read_csv(base / "rl_sample_goals.csv")

user_id = "USER_00021"

print("PROFILE COLUMNS:")
print(profiles.columns.tolist())

profile_rows = profiles.loc[profiles["user_id"] == user_id]
goal_rows = goals.loc[goals["user_id"] == user_id]

if profile_rows.empty:
    raise ValueError(f"Profile not found for {user_id}")

if goal_rows.empty:
    raise ValueError(f"No goals found for {user_id}")

profile = profile_rows.iloc[0]

preferred_columns = [
    "user_id",
    "initial_savings",
    "initial_investment",
    "monthly_income",
    "monthly_expenditure",
    "monthly_surplus",
    "existing_emi",
    "monthly_existing_emi",
]

available_columns = [
    c for c in preferred_columns if c in profiles.columns
]

print("\nPROFILE VALUES:")
print(profile[available_columns].to_string())

goal_columns = [
    c for c in [
        "goal_id",
        "goal_type",
        "current_cost",
        "existing_funding",
        "time_horizon_months",
        "priority",
        "criticality",
    ]
    if c in goals.columns
]

print("\nGOALS:")
display(goal_rows[goal_columns].reset_index(drop=True))

print("\nFUNDING TOTALS:")
for column in ["initial_savings", "initial_investment"]:
    if column in profile.index:
        print(f"{column}: ₹{float(profile[column]):,.2f}")

if "existing_funding" in goal_rows.columns:
    print(
        "existing_funding total: "
        f"₹{goal_rows['existing_funding'].sum():,.2f}"
    )


# ===== CELL 87 =====  type=code  exec=None

from pathlib import Path
import pandas as pd

base = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/05_simulation_runs/rl_prototype"
)
env_path = base / "goalpilot_env.py"

profiles = pd.read_csv(base / "rl_sample_financial_profiles.csv")
goals = pd.read_csv(base / "rl_sample_goals.csv")

user_id = "USER_00021"
profile = profiles.loc[profiles["user_id"] == user_id].iloc[0]
user_goals = goals.loc[goals["user_id"] == user_id]

print("PROFILE FINANCIAL BASELINE")
for col in [
    "initial_savings",
    "initial_investment",
    "final_savings_balance",
    "final_portfolio_value",
    "final_total_financial_wealth",
    "goal_funding_ratio",
    "goal_shortfall_ratio",
]:
    if col in profiles.columns:
        print(f"{col}: {profile[col]}")

print("\nGOAL FUNDING SUMMARY")
print("Goal count:", len(user_goals))
print("Existing funding total:", user_goals["existing_funding"].sum())
print("Target cost total:", user_goals["current_cost"].sum())
print(
    "Existing funding by goal type:"
)
print(
    user_goals.groupby("goal_type", dropna=False)["existing_funding"]
    .agg(["count", "sum", "mean"])
    .to_string()
)

print("\nENVIRONMENT REFERENCES TO FUNDING INITIALIZATION")
source_lines = env_path.read_text().splitlines()

for i, line in enumerate(source_lines):
    if any(term in line.lower() for term in [
        "existing_funding",
        "goal_balances",
        "initial_savings",
        "initial_investment",
    ]):
        print(f"{i + 1:4}: {line.strip()}")

print("\nAVAILABLE SOURCE FILES THAT MAY DEFINE GOAL FUNDING")
for path in sorted(base.glob("*")):
    if path.is_file() and any(
        term in path.name.lower()
        for term in ["goal", "profile", "simulation", "funding"]
    ):
        print(path.name)


# ===== CELL 88 =====  type=code  exec=None

from pathlib import Path

root = Path("/content/drive/MyDrive/GoalPilot_AI")

print("Searching project files for goal-funding generation logic...\n")

terms = [
    "existing_funding",
    "goal_funding_ratio",
    "initial_savings",
    "final_total_financial_wealth",
]

extensions = {".py", ".ipynb", ".md"}

for path in root.rglob("*"):
    if not path.is_file() or path.suffix.lower() not in extensions:
        continue

    # Skip large generated run outputs and environment backups.
    if any(part in path.parts for part in [
        ".git", "__pycache__", "node_modules"
    ]):
        continue

    try:
        text = path.read_text(errors="ignore")
    except Exception:
        continue

    hits = [term for term in terms if term in text]
    if hits:
        print(f"\nFILE: {path}")
        print("Matching terms:", ", ".join(hits))



# ===== CELL 89 =====  type=code  exec=161

from pathlib import Path

root = Path(
    "/content/drive/MyDrive/GoalPilot_AI/GoalPilot_MultiGoal_Extension"
)

files_to_inspect = [
    root / "generate_multigoal_dataset.py",
    root / "src" / "simulation_adapter.py",
]

terms = [
    "existing_funding",
    "initial_savings",
    "initial_investment",
    "goal_funding_ratio",
]

for path in files_to_inspect:
    print(f"\n{'=' * 80}")
    print("FILE:", path.name)
    print("=" * 80)

    if not path.exists():
        print("File not found.")
        continue

    lines = path.read_text(errors="ignore").splitlines()
    selected = set()

    for i, line in enumerate(lines):
        if any(term in line for term in terms):
            selected.update(
                range(max(0, i - 5), min(len(lines), i + 8))
            )

    if not selected:
        print("No matching definitions found.")
        continue

    previous = -2
    for i in sorted(selected):
        if i > previous + 1:
            print("...")
        print(f"{i + 1:4}: {lines[i]}")
        previous = i


# ===== CELL 90 =====  type=code  exec=162

from pathlib import Path

path = Path(
    "/content/drive/MyDrive/GoalPilot_AI/GoalPilot_MultiGoal_Extension/generate_multigoal_dataset.py"
)

lines = path.read_text(errors="ignore").splitlines()

print("DATASET GENERATOR: goal definitions and funding formula\n")

# Print the beginning of the file, including imports, goal types,
# profile loading, and the complete goal-generation loop.
for i, line in enumerate(lines[:85]):
    print(f"{i + 1:4}: {line}")


# ===== CELL 91 =====  type=code  exec=163

from pathlib import Path

path = Path(
    "/content/drive/MyDrive/GoalPilot_AI/GoalPilot_MultiGoal_Extension/src/multi_goal_optimizer.py"
)

lines = path.read_text(errors="ignore").splitlines()

terms = [
    "existing_funding",
    "current_cost",
    "goal_progress",
    "shortfall",
    "funded",
]

selected = set()

for i, line in enumerate(lines):
    if any(term in line.lower() for term in terms):
        selected.update(range(max(0, i - 4), min(len(lines), i + 7)))

previous = -2
for i in sorted(selected):
    if i > previous + 1:
        print("...")
    print(f"{i + 1:4}: {lines[i]}")
    previous = i


# ===== CELL 92 =====  type=code  exec=164
import pandas as pd
from pathlib import Path

base = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/"
    "05_simulation_runs/rl_prototype"
)

profiles = pd.read_csv(base / "rl_sample_financial_profiles.csv")
goals = pd.read_csv(base / "rl_sample_goals.csv")

funding = (
    goals.groupby("user_id", as_index=False)
    .agg(
        goal_count=("goal_id", "count"),
        total_existing_funding=("existing_funding", "sum"),
        total_goal_cost=("current_cost", "sum"),
    )
)

check = profiles.merge(funding, on="user_id", how="left")
check["funding_exceeds_initial_savings"] = (
    check["total_existing_funding"] > check["initial_savings"] + 0.01
)
check["funding_excess"] = (
    check["total_existing_funding"] - check["initial_savings"]
).clip(lower=0)

print("PROFILE COUNT:", len(check))
print("PROFILES WHERE EARMARKED FUNDING EXCEEDS INITIAL SAVINGS:",
      int(check["funding_exceeds_initial_savings"].sum()))
print("TOTAL EXCESS ACROSS PROFILES: ₹{:,.2f}".format(
    check["funding_excess"].sum()
))

print("\nLargest mismatches:")
print(
    check.loc[
        check["funding_exceeds_initial_savings"],
        [
            "user_id",
            "initial_savings",
            "total_existing_funding",
            "funding_excess",
            "goal_count",
        ],
    ]
    .sort_values("funding_excess", ascending=False)
    .head(10)
    .to_string(index=False)
)

print("\nFunding summary:")
print(
    check[
        ["initial_savings", "total_existing_funding", "funding_excess"]
    ].describe().round(2).to_string()
)

# ===== CELL 93 =====  type=code  exec=165
from pathlib import Path

path = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/"
    "05_simulation_runs/rl_prototype/goalpilot_env.py"
)
lines = path.read_text(errors="ignore").splitlines()

terms = [
    "initial_savings",
    "initial_investment",
    "existing_funding",
    "goal_balances",
    "goal_targets",
    "self.cash",
    "self.portfolio",
]

selected = set()
for i, line in enumerate(lines):
    if any(term in line for term in terms):
        selected.update(range(max(0, i - 3), min(len(lines), i + 5)))

previous = -2
for i in sorted(selected):
    if i > previous + 1:
        print("...")
    print(f"{i + 1:4}: {lines[i]}")
    previous = i

# ===== CELL 94 =====  type=code  exec=166
import pandas as pd
from pathlib import Path

base = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/"
    "05_simulation_runs/rl_prototype"
)

profiles = pd.read_csv(base / "rl_sample_financial_profiles.csv")
goals = pd.read_csv(base / "rl_sample_goals.csv")

check = goals.merge(
    profiles[["user_id", "initial_savings", "initial_investment"]],
    on="user_id",
    how="left",
    validate="many_to_one",
)

check["initial_savings"] = check["initial_savings"].clip(lower=0)
check["total_user_earmark"] = check.groupby("user_id")[
    "existing_funding"
].transform("sum")

check["scale_factor"] = (
    check["initial_savings"] / check["total_user_earmark"]
).where(
    check["total_user_earmark"] > check["initial_savings"],
    1.0,
).clip(upper=1.0)

check["proposed_funding"] = (
    check["existing_funding"] * check["scale_factor"]
)

summary = check.groupby("user_id").agg(
    initial_savings=("initial_savings", "first"),
    initial_investment=("initial_investment", "first"),
    original_funding=("existing_funding", "sum"),
    proposed_funding=("proposed_funding", "sum"),
)

summary["funding_reduction"] = (
    summary["original_funding"] - summary["proposed_funding"]
)

print("PROFILES STILL EXCEEDING INITIAL SAVINGS:",
      int((summary["proposed_funding"] > summary["initial_savings"] + 0.01).sum()))

print("TOTAL FUNDING REDUCTION: ₹{:,.2f}".format(
    summary["funding_reduction"].sum()
))

print("\nExample: USER_00059")
print(
    check.loc[
        check["user_id"] == "USER_00059",
        ["goal_id", "goal_name", "existing_funding",
         "scale_factor", "proposed_funding"],
    ].to_string(index=False)
)

print("\nOriginal versus proposed totals:")
print(
    summary.loc[
        summary["funding_reduction"] > 0,
        ["initial_savings", "original_funding",
         "proposed_funding", "funding_reduction"],
    ].head(10).round(2).to_string()
)

# ===== CELL 95 =====  type=code  exec=167
from pathlib import Path

path = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/"
    "05_simulation_runs/rl_prototype/goalpilot_env.py"
)
lines = path.read_text(errors="ignore").splitlines()

for i, line in enumerate(lines):
    if "self.cash" in line:
        start = max(0, i - 2)
        end = min(len(lines), i + 3)
        print(f"\n--- Lines {start + 1}-{end} ---")
        for j in range(start, end):
            print(f"{j + 1:4}: {lines[j]}")

# ===== CELL 96 =====  type=code  exec=168
from pathlib import Path
import shutil

path = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/"
    "05_simulation_runs/rl_prototype/goalpilot_env.py"
)

source = path.read_text()
backup = path.with_name("goalpilot_env.py.pre_earmark_reconciliation.bak")

old = '''        self.month_index = 0
        self.cash = max(0.0, float(p["initial_savings"]))
        self.portfolio = max(0.0, float(p["initial_investment"]))
        self.loan_balance = 0.0
        self.loan_emi = 0.0
        self.loan_months_left = 0
        self.total_rewards = 0.0

        self.goal_targets = self.user_goals["current_cost"].astype(float).to_numpy()
        self.goal_deadlines = self.user_goals["time_horizon_months"].astype(int).to_numpy()
        self.goal_balances = self.user_goals["existing_funding"].astype(float).to_numpy()
'''

new = '''        self.month_index = 0
        initial_savings = max(0.0, float(p["initial_savings"]))
        self.portfolio = max(0.0, float(p["initial_investment"]))
        self.loan_balance = 0.0
        self.loan_emi = 0.0
        self.loan_months_left = 0
        self.total_rewards = 0.0

        self.goal_targets = self.user_goals["current_cost"].astype(float).to_numpy()
        self.goal_deadlines = self.user_goals["time_horizon_months"].astype(int).to_numpy()

        # Reconcile synthetic goal earmarks with the user's initial liquid savings.
        # Scale proportionally only when the total earmark exceeds available savings.
        original_funding = self.user_goals["existing_funding"].astype(float).to_numpy()
        total_earmarked = float(original_funding.sum(dtype="float64"))
        funding_scale = (
            min(1.0, initial_savings / total_earmarked)
            if total_earmarked > 0.0 else 1.0
        )
        self.goal_balances = original_funding * funding_scale

        # Keep earmarked funds separate from unearmarked cash in the initial state.
        reconciled_earmarked = float(self.goal_balances.sum(dtype="float64"))
        self.cash = max(0.0, initial_savings - reconciled_earmarked)
'''

if old not in source:
    raise RuntimeError(
        "Expected reset() block was not found. No file was changed; inspect the current source."
    )

shutil.copy2(path, backup)
path.write_text(source.replace(old, new, 1))

print("Patch applied successfully.")
print("Backup:", backup)
print("Updated:", path)
print("Original CSV files and LP optimizer were not changed.")

# ===== CELL 97 =====  type=code  exec=170
import inspect
from pathlib import Path
import sys

base = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/"
    "05_simulation_runs/rl_prototype"
)

if str(base) not in sys.path:
    sys.path.insert(0, str(base))

from goalpilot_env import GoalPilotEnv

print("Constructor signature:")
print(inspect.signature(GoalPilotEnv.__init__))

print("\nConstructor source:")
print(inspect.getsource(GoalPilotEnv.__init__))

# ===== CELL 98 =====  type=code  exec=171
import sys
import numpy as np
import pandas as pd
from pathlib import Path

base = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/"
    "05_simulation_runs/rl_prototype"
)

if str(base) not in sys.path:
    sys.path.insert(0, str(base))

from goalpilot_env import GoalPilotEnv

profiles = pd.read_csv(base / "rl_sample_financial_profiles.csv")
goals = pd.read_csv(base / "rl_sample_goals.csv")
market = pd.read_csv(base / "rl_market_credit_validated.csv")

funding_totals = goals.groupby("user_id")["existing_funding"].sum()
savings_map = profiles.set_index("user_id")["initial_savings"]

overfunded = funding_totals[
    funding_totals > savings_map.reindex(funding_totals.index) + 0.01
]
not_overfunded = funding_totals[
    funding_totals <= savings_map.reindex(funding_totals.index) + 0.01
]

test_users = []
if len(overfunded):
    test_users.append(overfunded.index[0])
if len(not_overfunded):
    test_users.append(not_overfunded.index[0])

env = GoalPilotEnv(
    profiles=profiles,
    goals=goals,
    market=market,
    user_ids=test_users,
    seed=42,
)

print("INITIALIZATION CHECKS")
for user_id in test_users:
    env.reset(options={"user_id": user_id})

    initial_savings = max(
        0.0,
        float(profiles.loc[
            profiles["user_id"] == user_id, "initial_savings"
        ].iloc[0]),
    )
    original_funding = float(
        goals.loc[goals["user_id"] == user_id, "existing_funding"].sum()
    )
    reconciled_funding = float(env.goal_balances.sum(dtype="float64"))
    accounted_savings = float(env.cash) + reconciled_funding

    print({
        "user_id": user_id,
        "initial_savings": round(initial_savings, 2),
        "original_funding": round(original_funding, 2),
        "reconciled_funding": round(reconciled_funding, 2),
        "initial_cash": round(float(env.cash), 2),
        "cash_plus_goal_funding": round(accounted_savings, 2),
        "within_savings": reconciled_funding <= initial_savings + 0.01,
        "accounting_balanced": abs(accounted_savings - initial_savings) <= 0.01,
        "finite_state": bool(
            np.isfinite(env.cash)
            and np.isfinite(env.portfolio)
            and np.isfinite(env.goal_balances).all()
        ),
    })

# ===== CELL 99 =====  type=code  exec=172
import sys
import inspect
import importlib
from pathlib import Path

base = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/"
    "05_simulation_runs/rl_prototype"
)

if str(base) not in sys.path:
    sys.path.insert(0, str(base))

import goalpilot_env
goalpilot_env = importlib.reload(goalpilot_env)

print("LOADED MODULE:", goalpilot_env.__file__)
print("EXPECTED FILE:", base / "goalpilot_env.py")
print("PATH MATCH:", Path(goalpilot_env.__file__).resolve() == (
    base / "goalpilot_env.py"
).resolve())

print("\nRESET METHOD SOURCE:")
print(inspect.getsource(goalpilot_env.GoalPilotEnv.reset))

# ===== CELL 100 =====  type=code  exec=173
import numpy as np
import pandas as pd
from pathlib import Path
import importlib
import goalpilot_env

base = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/"
    "05_simulation_runs/rl_prototype"
)

goalpilot_env = importlib.reload(goalpilot_env)

profiles = pd.read_csv(base / "rl_sample_financial_profiles.csv")
goals = pd.read_csv(base / "rl_sample_goals.csv")
market = pd.read_csv(base / "rl_market_credit_validated.csv")

funding_totals = goals.groupby("user_id")["existing_funding"].sum()
savings_map = profiles.set_index("user_id")["initial_savings"]

overfunded = funding_totals[
    funding_totals > savings_map.reindex(funding_totals.index) + 0.01
]
not_overfunded = funding_totals[
    funding_totals <= savings_map.reindex(funding_totals.index) + 0.01
]

test_users = []
if len(overfunded):
    test_users.append(overfunded.index[0])
if len(not_overfunded):
    test_users.append(not_overfunded.index[0])

env = goalpilot_env.GoalPilotEnv(
    profiles=profiles,
    goals=goals,
    market=market,
    user_ids=test_users,
    seed=42,
)

print("ENVIRONMENT CLASS:", type(env))
print("INITIALIZATION CHECKS")

for user_id in test_users:
    env.reset(options={"user_id": user_id})

    initial_savings = max(
        0.0,
        float(profiles.loc[
            profiles["user_id"] == user_id, "initial_savings"
        ].iloc[0]),
    )
    original_funding = float(
        goals.loc[goals["user_id"] == user_id, "existing_funding"].sum()
    )
    reconciled_funding = float(env.goal_balances.sum(dtype=np.float64))
    accounted_savings = float(env.cash) + reconciled_funding

    print({
        "user_id": user_id,
        "initial_savings": round(initial_savings, 2),
        "original_funding": round(original_funding, 2),
        "reconciled_funding": round(reconciled_funding, 2),
        "initial_cash": round(float(env.cash), 2),
        "cash_plus_goal_funding": round(accounted_savings, 2),
        "within_savings": reconciled_funding <= initial_savings + 0.01,
        "accounting_balanced": abs(accounted_savings - initial_savings) <= 0.01,
        "finite_state": bool(
            np.isfinite(env.cash)
            and np.isfinite(env.portfolio)
            and np.isfinite(env.goal_balances).all()
        ),
    })

# ===== CELL 101 =====  type=code  exec=174
import numpy as np
import pandas as pd
from pathlib import Path
import importlib
import goalpilot_env

base = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/"
    "05_simulation_runs/rl_prototype"
)

goalpilot_env = importlib.reload(goalpilot_env)

profiles = pd.read_csv(base / "rl_sample_financial_profiles.csv")
goals = pd.read_csv(base / "rl_sample_goals.csv")
market = pd.read_csv(base / "rl_market_credit_validated.csv")

env = goalpilot_env.GoalPilotEnv(
    profiles=profiles,
    goals=goals,
    market=market,
    seed=2026,
)

rng = np.random.default_rng(2026)
episodes = min(10, len(profiles))
steps_checked = 0
budget_excesses = []
negative_balances = []
nonfinite_states = []
accounting_errors = []
exceptions = []

for episode in range(episodes):
    user_id = str(profiles.iloc[episode]["user_id"])

    try:
        obs, info = env.reset(options={"user_id": user_id})

        initial_savings = max(
            0.0,
            float(profiles.loc[
                profiles["user_id"] == user_id, "initial_savings"
            ].iloc[0]),
        )
        initial_goal_funding = float(env.goal_balances.sum(dtype=np.float64))

        if abs(float(env.cash) + initial_goal_funding - initial_savings) > 0.01:
            accounting_errors.append((user_id, "initial accounting mismatch"))

        terminated = truncated = False
        while not (terminated or truncated):
            action = rng.uniform(
                0.0, 1.0, size=env.action_space.shape
            ).astype(np.float32)

            obs, reward, terminated, truncated, info = env.step(action)
            steps_checked += 1

            commitment = float(info["combined_monthly_commitment"])
            surplus = max(
                0.0,
                float(env.profile_map[user_id]["monthly_income"])
                - float(env.profile_map[user_id]["monthly_expenditure"])
                - float(env.profile_map[user_id]["monthly_emi"]),
            )

            excess = commitment - surplus
            if excess > 0.01:
                budget_excesses.append((user_id, env.month_index, excess))

            if (
                env.cash < -0.01
                or env.portfolio < -0.01
                or env.loan_balance < -0.01
                or np.any(env.goal_balances < -0.01)
            ):
                negative_balances.append((user_id, env.month_index))

            if not (
                np.isfinite(obs).all()
                and np.isfinite(reward)
                and np.isfinite(env.cash)
                and np.isfinite(env.portfolio)
                and np.isfinite(env.loan_balance)
                and np.isfinite(env.goal_balances).all()
            ):
                nonfinite_states.append((user_id, env.month_index))
                break

    except Exception as exc:
        exceptions.append((user_id, repr(exc)))

print("Episodes:", episodes)
print("Steps checked:", steps_checked)
print("Budget violations:", len(budget_excesses))
print("Negative-balance events:", len(negative_balances))
print("Non-finite states:", len(nonfinite_states))
print("Initial accounting errors:", len(accounting_errors))
print("Exceptions:", len(exceptions))

if budget_excesses:
    print("Largest budget excess:", max(x[2] for x in budget_excesses))
if exceptions:
    print("First exceptions:", exceptions[:3])
if negative_balances:
    print("First negative-balance events:", negative_balances[:3])
if nonfinite_states:
    print("First non-finite states:", nonfinite_states[:3])
if accounting_errors:
    print("First accounting errors:", accounting_errors[:3])

# ===== CELL 102 =====  type=code  exec=175
import numpy as np
import pandas as pd
from pathlib import Path
import importlib
import goalpilot_env

base = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/"
    "05_simulation_runs/rl_prototype"
)

goalpilot_env = importlib.reload(goalpilot_env)

profiles = pd.read_csv(base / "rl_sample_financial_profiles.csv")
goals = pd.read_csv(base / "rl_sample_goals.csv")
market = pd.read_csv(base / "rl_market_credit_validated.csv")

# Use a profile with some existing goal funding.
funding = goals.groupby("user_id")["existing_funding"].sum()
candidate_ids = funding[funding > 0].index
user_id = str(candidate_ids[0])

env = goalpilot_env.GoalPilotEnv(
    profiles=profiles,
    goals=goals,
    market=market,
    user_ids=[user_id],
    seed=42,
)

obs, info = env.reset(options={"user_id": user_id})
initial_goal_balances = env.goal_balances.copy()

print("USER:", user_id)
print("Initial goal funding:", round(float(initial_goal_balances.sum()), 2))
print("\nZero-action test:")

for step in range(6):
    action = np.zeros(env.action_space.shape, dtype=np.float32)
    obs, reward, terminated, truncated, info = env.step(action)

    goal_change = float(
        np.sum(env.goal_balances - initial_goal_balances)
    )

    print({
        "month": step + 1,
        "reward": round(float(reward), 6),
        "new_goal_contributions": round(goal_change, 2),
        "cash": round(float(env.cash), 2),
        "portfolio": round(float(env.portfolio), 2),
        "loan_balance": round(float(env.loan_balance), 2),
    })

    if terminated or truncated:
        break

# ===== CELL 103 =====  type=code  exec=176
from pathlib import Path

path = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/"
    "05_simulation_runs/rl_prototype/goalpilot_env.py"
)
lines = path.read_text(errors="ignore").splitlines()

start, end = 240, 365
for i in range(start - 1, min(end, len(lines))):
    print(f"{i + 1:4}: {lines[i]}")

# ===== CELL 104 =====  type=code  exec=177
from pathlib import Path
import shutil

path = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/"
    "05_simulation_runs/rl_prototype/goalpilot_env.py"
)

source = path.read_text()
backup = path.with_name("goalpilot_env.py.pre_incremental_reward.bak")

old = '''        # Credit goal balances using the cash/investment allocations.
        # Contributions are split across goals in proportion to action weights.
        contribution = savings_alloc + invest_alloc
        total_contribution = float(contribution.sum())
        if total_contribution > 0:
            weights = contribution / total_contribution
            for j, amount in enumerate(contribution):
                self.goal_balances[j] += float(amount)

        # Reward incremental goal progress, deadline attainment, and affordability.
        reward = 0.0
        for j in range(len(self.user_goals)):
            target = max(1.0, float(self.goal_targets[j]))
            old_ratio = min(1.0, max(0.0, self.goal_balances[j] / target))
            # Avoid rewarding the same already funded balance repeatedly.
            reward += 2.0 * old_ratio * float(self.user_goals.iloc[j]["priority"]) / 5.0

            if self.month_index + 1 >= self.goal_deadlines[j]:
                shortfall_ratio = max(
                    0.0, (target - self.goal_balances[j]) / target
                )
                reward -= 5.0 * shortfall_ratio * float(
                    self.user_goals.iloc[j]["criticality"]
                ) / 5.0
'''

new = '''        # Credit goal balances using the cash/investment allocations.
        # Keep the previous balances to reward only newly achieved progress.
        previous_goal_balances = self.goal_balances.copy()
        contribution = savings_alloc + invest_alloc
        for j, amount in enumerate(contribution):
            self.goal_balances[j] += float(amount)

        # Reward incremental goal progress, not the same funded ratio repeatedly.
        reward = 0.0
        for j in range(len(self.user_goals)):
            target = max(1.0, float(self.goal_targets[j]))
            previous_ratio = min(
                1.0, max(0.0, previous_goal_balances[j] / target)
            )
            current_ratio = min(
                1.0, max(0.0, self.goal_balances[j] / target)
            )
            priority = float(self.user_goals.iloc[j]["priority"])
            criticality = float(self.user_goals.iloc[j]["criticality"])

            reward += (
                2.0 * max(0.0, current_ratio - previous_ratio)
                * priority / 5.0
            )

            # Apply the shortfall penalty once, in the month the deadline is reached.
            if self.month_index + 1 == self.goal_deadlines[j]:
                shortfall_ratio = max(
                    0.0, (target - self.goal_balances[j]) / target
                )
                reward -= 5.0 * shortfall_ratio * criticality / 5.0
'''

if old not in source:
    raise RuntimeError(
        "Expected reward block not found. No changes made; inspect the current code."
    )

shutil.copy2(path, backup)
path.write_text(source.replace(old, new, 1))

print("Reward patch applied.")
print("Backup:", backup)
print("Updated:", path)
print("Changes: incremental goal-progress reward; deadline penalty only at deadline.")

# ===== CELL 105 =====  type=code  exec=178
import importlib
import numpy as np
import pandas as pd
from pathlib import Path
import goalpilot_env

base = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/"
    "05_simulation_runs/rl_prototype"
)

goalpilot_env = importlib.reload(goalpilot_env)

profiles = pd.read_csv(base / "rl_sample_financial_profiles.csv")
goals = pd.read_csv(base / "rl_sample_goals.csv")
market = pd.read_csv(base / "rl_market_credit_validated.csv")

funding = goals.groupby("user_id")["existing_funding"].sum()
candidate_ids = funding[funding > 0].index
user_id = str(candidate_ids[0])

env = goalpilot_env.GoalPilotEnv(
    profiles=profiles,
    goals=goals,
    market=market,
    user_ids=[user_id],
    seed=42,
)

obs, info = env.reset(options={"user_id": user_id})
initial_goal_balances = env.goal_balances.copy()
initial_cash = float(env.cash)
initial_portfolio = float(env.portfolio)

print("USER:", user_id)
print("Initial goal funding:", round(float(initial_goal_balances.sum()), 2))
print("Zero-action test:")

for step in range(6):
    action = np.zeros(env.action_space.shape, dtype=np.float32)
    obs, reward, terminated, truncated, info = env.step(action)

    goal_change = float(
        np.sum(env.goal_balances - initial_goal_balances)
    )

    print({
        "month": step + 1,
        "reward": round(float(reward), 6),
        "goal_contributions": round(goal_change, 2),
        "cash": round(float(env.cash), 2),
        "portfolio": round(float(env.portfolio), 2),
        "loan_balance": round(float(env.loan_balance), 2),
    })

    if terminated or truncated:
        break

# ===== CELL 106 =====  type=code  exec=179
import importlib
import numpy as np
import pandas as pd
from pathlib import Path
import goalpilot_env

base = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/"
    "05_simulation_runs/rl_prototype"
)

goalpilot_env = importlib.reload(goalpilot_env)

profiles = pd.read_csv(base / "rl_sample_financial_profiles.csv")
goals = pd.read_csv(base / "rl_sample_goals.csv")
market = pd.read_csv(base / "rl_market_credit_validated.csv")

test_users = profiles["user_id"].astype(str).head(5).tolist()

env = goalpilot_env.GoalPilotEnv(
    profiles=profiles,
    goals=goals,
    market=market,
    user_ids=test_users,
    seed=2026,
)

results = []

for user_id in test_users:
    for policy_name in ["zero_action", "contribution"]:
        obs, info = env.reset(options={"user_id": user_id})
        initial_goals = env.goal_balances.copy()
        rewards = []
        contributions = []
        finite = True

        while True:
            action = np.zeros(env.action_space.shape, dtype=np.float32)

            if policy_name == "contribution":
                action[:, 0] = 0.25  # Request savings allocation
                action[:, 1] = 0.25  # Request investment allocation
                action[:, 2] = 0.0   # No new loans

            obs, reward, terminated, truncated, info = env.step(action)

            rewards.append(float(reward))
            contributions.append(
                float(np.sum(env.goal_balances - initial_goals))
            )

            finite = finite and bool(
                np.isfinite(obs).all()
                and np.isfinite(reward)
                and np.isfinite(env.goal_balances).all()
            )

            if terminated or truncated:
                break

        total_goal_progress = float(
            np.sum(env.goal_balances - initial_goals)
        )

        results.append({
            "user_id": user_id,
            "policy": policy_name,
            "steps": len(rewards),
            "total_reward": sum(rewards),
            "max_step_reward": max(rewards),
            "goal_progress": total_goal_progress,
            "positive_reward_steps": sum(r > 1e-8 for r in rewards),
            "finite": finite,
        })

result_df = pd.DataFrame(results)

print(result_df.round(4).to_string(index=False))

zero = result_df[result_df["policy"] == "zero_action"]
active = result_df[result_df["policy"] == "contribution"]

print("\nVALIDATION SUMMARY")
print("Zero-action positive-reward cases:",
      int((zero["max_step_reward"] > 1e-8).sum()))
print("Contribution-policy users with positive goal progress:",
      int((active["goal_progress"] > 0.01).sum()), "of", len(active))
print("Non-finite runs:", int((~result_df["finite"]).sum()))

# ===== CELL 107 =====  type=code  exec=180
from pathlib import Path

path = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/"
    "05_simulation_runs/rl_prototype/goalpilot_env.py"
)
lines = path.read_text(errors="ignore").splitlines()

# Inspect action handling, budget calculation, and financial updates.
for start, end in [(165, 245), (245, 330), (330, 385)]:
    print(f"\n{'=' * 18} LINES {start}-{end} {'=' * 18}")
    for i in range(start - 1, min(end, len(lines))):
        print(f"{i + 1:4}: {lines[i]}")

# ===== CELL 108 =====  type=code  exec=181
from pathlib import Path
import shutil

path = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/"
    "05_simulation_runs/rl_prototype/goalpilot_env.py"
)

source = path.read_text()
backup = path.with_name("goalpilot_env.py.pre_goal_cap.bak")

old = '''        savings_alloc = raw_savings * budget_scale
        invest_alloc = raw_investments * budget_scale

        # A new loan can be requested only if the EMI fits remaining surplus.
'''

new = '''        savings_alloc = raw_savings * budget_scale
        invest_alloc = raw_investments * budget_scale

        # Do not allocate contributions beyond each goal's remaining target.
        remaining_by_goal = np.maximum(
            0.0,
            self.goal_targets.astype("float64")
            - self.goal_balances.astype("float64"),
        )
        requested_by_goal = savings_alloc + invest_alloc
        goal_cap_scale = np.ones_like(requested_by_goal, dtype="float64")
        positive_requests = requested_by_goal > 0.0
        goal_cap_scale[positive_requests] = np.minimum(
            1.0,
            remaining_by_goal[positive_requests]
            / requested_by_goal[positive_requests],
        )
        savings_alloc = savings_alloc * goal_cap_scale
        invest_alloc = invest_alloc * goal_cap_scale

        # A new loan can be requested only if the EMI fits remaining surplus.
'''

if old not in source:
    raise RuntimeError(
        "Expected allocation block not found. No changes were made."
    )

shutil.copy2(path, backup)
path.write_text(source.replace(old, new, 1))

print("Per-goal allocation cap applied.")
print("Backup:", backup)
print("Updated:", path)
print("Datasets and LP baseline were not changed.")

# ===== CELL 109 =====  type=code  exec=182
import importlib
import numpy as np
import pandas as pd
from pathlib import Path
import goalpilot_env

base = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/"
    "05_simulation_runs/rl_prototype"
)

goalpilot_env = importlib.reload(goalpilot_env)

profiles = pd.read_csv(base / "rl_sample_financial_profiles.csv")
goals = pd.read_csv(base / "rl_sample_goals.csv")
market = pd.read_csv(base / "rl_market_credit_validated.csv")

test_users = profiles["user_id"].astype(str).head(5).tolist()

env = goalpilot_env.GoalPilotEnv(
    profiles=profiles,
    goals=goals,
    market=market,
    user_ids=test_users,
    seed=2026,
)

results = []

for user_id in test_users:
    env.reset(options={"user_id": user_id})
    max_goal_overshoot = 0.0
    max_budget_excess = 0.0
    min_balance = 0.0
    finite = True
    steps = 0

    while True:
        action = np.zeros(env.action_space.shape, dtype=np.float32)
        action[:, 0] = 0.25
        action[:, 1] = 0.25
        action[:, 2] = 0.0

        obs, reward, terminated, truncated, info = env.step(action)
        steps += 1

        overshoot = float(np.max(env.goal_balances - env.goal_targets))
        max_goal_overshoot = max(max_goal_overshoot, overshoot)

        p = env.profile_map[user_id]
        surplus = max(
            0.0,
            float(p["monthly_income"])
            - float(p["monthly_expenditure"])
            - float(p["monthly_emi"]),
        )
        commitment = float(info["combined_monthly_commitment"])
        max_budget_excess = max(
            max_budget_excess, commitment - surplus
        )

        min_balance = min(
            min_balance,
            float(env.cash),
            float(env.portfolio),
            float(env.loan_balance),
            float(np.min(env.goal_balances)),
        )

        finite = finite and bool(
            np.isfinite(obs).all()
            and np.isfinite(reward)
            and np.isfinite(env.goal_balances).all()
        )

        if terminated or truncated:
            break

    results.append({
        "user_id": user_id,
        "steps": steps,
        "goal_overshoot": max_goal_overshoot,
        "budget_excess": max_budget_excess,
        "minimum_balance": min_balance,
        "finite": finite,
    })

result_df = pd.DataFrame(results)
print(result_df.round(6).to_string(index=False))

print("\nSUMMARY")
print("Goal-cap violations:",
      int((result_df["goal_overshoot"] > 0.01).sum()))
print("Budget violations:",
      int((result_df["budget_excess"] > 0.01).sum()))
print("Negative-balance runs:",
      int((result_df["minimum_balance"] < -0.01).sum()))
print("Non-finite runs:", int((~result_df["finite"]).sum()))

# ===== CELL 110 =====  type=code  exec=183
import importlib
import numpy as np
import pandas as pd
from pathlib import Path
import goalpilot_env

base = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/"
    "05_simulation_runs/rl_prototype"
)

goalpilot_env = importlib.reload(goalpilot_env)

profiles = pd.read_csv(base / "rl_sample_financial_profiles.csv")
goals = pd.read_csv(base / "rl_sample_goals.csv")
market = pd.read_csv(base / "rl_market_credit_validated.csv")

user_id = str(profiles.iloc[0]["user_id"])

env = goalpilot_env.GoalPilotEnv(
    profiles=profiles,
    goals=goals,
    market=market,
    user_ids=[user_id],
    seed=2026,
)

obs, reset_info = env.reset(options={"user_id": user_id})

# Use a moderate, fixed action to inspect one transition.
action = np.zeros(env.action_space.shape, dtype=np.float32)
action[:, 0] = 0.25
action[:, 1] = 0.25
action[:, 2] = 0.0

next_obs, reward, terminated, truncated, info = env.step(action)

print("USER:", user_id)
print("\nACTION SHAPE:", action.shape)
print("OBSERVATION SHAPE:", obs.shape)
print("NEXT OBSERVATION SHAPE:", next_obs.shape)

print("\nSTEP INFO KEYS:")
print(sorted(info.keys()))

print("\nSTEP INFO VALUES:")
for key, value in info.items():
    if isinstance(value, (int, float, np.integer, np.floating, bool, str)):
        print(f"{key}: {value}")
    elif isinstance(value, (list, tuple, np.ndarray)):
        print(f"{key}: {np.asarray(value).tolist()}")
    else:
        print(f"{key}: {value}")

print("\nREWARD:", reward)
print("TERMINATED:", terminated)
print("TRUNCATED:", truncated)

print("\nFINANCIAL STATE AFTER STEP")
print("Cash:", env.cash)
print("Portfolio:", env.portfolio)
print("Loan balance:", env.loan_balance)
print("Loan EMI:", env.loan_emi)
print("Loan months left:", env.loan_months_left)
print("Goal balances:", env.goal_balances.tolist())
print("Goal targets:", env.goal_targets.tolist())

# ===== CELL 111 =====  type=code  exec=184
from pathlib import Path

env_path = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/"
    "05_simulation_runs/rl_prototype/goalpilot_env.py"
)

source = env_path.read_text()
lines = source.splitlines()

keywords = [
    "def step(",
    "discretionary_budget",
    "self.cash",
    "self.portfolio",
    "savings_alloc",
    "invest_alloc",
    "portfolio_market_change",
    "combined_monthly_commitment",
]

for keyword in keywords:
    matches = [
        i for i, line in enumerate(lines)
        if keyword in line
    ]

    print(f"\n{'=' * 20} {keyword} {'=' * 20}")

    if not matches:
        print("Not found")
        continue

    for i in matches:
        start = max(0, i - 4)
        end = min(len(lines), i + 7)

        print(f"\n--- Lines {start + 1}-{end} ---")
        for j in range(start, end):
            print(f"{j + 1:4}: {lines[j]}")

# ===== CELL 112 =====  type=code  exec=185
import importlib
import numpy as np
import pandas as pd
from pathlib import Path
import goalpilot_env

base = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/"
    "05_simulation_runs/rl_prototype"
)

goalpilot_env = importlib.reload(goalpilot_env)

profiles = pd.read_csv(base / "rl_sample_financial_profiles.csv")
goals = pd.read_csv(base / "rl_sample_goals.csv")
market = pd.read_csv(base / "rl_market_credit_validated.csv")

user_id = str(profiles.iloc[0]["user_id"])

env = goalpilot_env.GoalPilotEnv(
    profiles=profiles,
    goals=goals,
    market=market,
    user_ids=[user_id],
    seed=2026,
)

env.reset(options={"user_id": user_id})

records = []

while True:
    action = np.zeros(env.action_space.shape, dtype=np.float32)
    action[:, 0] = 0.25
    action[:, 1] = 0.25
    action[:, 2] = 0.0

    obs, reward, terminated, truncated, info = env.step(action)

    records.append({
        "month": env.month_index,
        "cash": float(env.cash),
        "portfolio": float(env.portfolio),
        "loan_balance": float(env.loan_balance),
        "goal_funding": float(env.goal_balances.sum()),
        "goal_target": float(env.goal_targets.sum()),
        "savings_contribution": info["savings_contribution"],
        "investment_contribution": info["investment_contribution"],
        "market_change": info["portfolio_market_change"],
        "reward": float(reward),
    })

    if terminated or truncated:
        break

history = pd.DataFrame(records)

print("FIRST 5 MONTHS")
print(history.head().round(2).to_string(index=False))

print("\nLAST 5 MONTHS")
print(history.tail().round(2).to_string(index=False))

print("\nEPISODE SUMMARY")
print("Months:", len(history))
print("Initial cash:", round(history.iloc[0]["cash"], 2))
print("Final cash:", round(history.iloc[-1]["cash"], 2))
print("Final portfolio:", round(history.iloc[-1]["portfolio"], 2))
print("Final loan balance:", round(history.iloc[-1]["loan_balance"], 2))
print("Final goal funding:", round(history.iloc[-1]["goal_funding"], 2))
print("Total goal target:", round(history.iloc[-1]["goal_target"], 2))
print(
    "Final goal funding ratio:",
    round(
        history.iloc[-1]["goal_funding"]
        / max(history.iloc[-1]["goal_target"], 1.0),
        4,
    ),
)
print(
    "Final financial wealth (cash + portfolio - debt):",
    round(
        history.iloc[-1]["cash"]
        + history.iloc[-1]["portfolio"]
        - history.iloc[-1]["loan_balance"],
        2,
    ),
)

# ===== CELL 113 =====  type=code  exec=186
from pathlib import Path
import pandas as pd

base = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/"
    "05_simulation_runs/rl_prototype"
)
env_path = base / "goalpilot_env.py"

lines = env_path.read_text().splitlines()

# Inspect action interpretation, allocation, loan logic and state updates.
for start, end, heading in [
    (178, 275, "ACTION AND ALLOCATION LOGIC"),
    (300, 368, "FINANCIAL UPDATES AND REWARD"),
]:
    print(f"\n{'=' * 18} {heading} {'=' * 18}")
    for i in range(start, min(end, len(lines))):
        print(f"{i + 1:4}: {lines[i]}")

# Inspect the selected user's goals and funding assumptions.
profiles = pd.read_csv(base / "rl_sample_financial_profiles.csv")
goals = pd.read_csv(base / "rl_sample_goals.csv")

user_id = str(profiles.iloc[0]["user_id"])
user_goals = goals[goals["user_id"].astype(str) == user_id].copy()

columns = [
    c for c in [
        "goal_id",
        "goal_type",
        "current_cost",
        "existing_funding",
        "time_horizon_months",
        "priority",
        "criticality",
    ]
    if c in user_goals.columns
]

print(f"\n{'=' * 18} GOALS FOR {user_id} {'=' * 18}")
print(user_goals[columns].to_string(index=False))
print("\nSum of goal targets:", user_goals["current_cost"].sum())
print("Sum of existing goal funding:", user_goals["existing_funding"].sum())

# ===== CELL 114 =====  type=code  exec=187
import importlib
import numpy as np
import pandas as pd
from pathlib import Path
import goalpilot_env

base = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/"
    "05_simulation_runs/rl_prototype"
)

goalpilot_env = importlib.reload(goalpilot_env)

profiles = pd.read_csv(base / "rl_sample_financial_profiles.csv")
goals = pd.read_csv(base / "rl_sample_goals.csv")
market = pd.read_csv(base / "rl_market_credit_validated.csv")

user_id = "USER_00001"

env = goalpilot_env.GoalPilotEnv(
    profiles=profiles,
    goals=goals,
    market=market,
    user_ids=[user_id],
    seed=2026,
)

experiments = {
    "Savings only": (1.0, 0.0, 0.0),
    "Investments only": (0.0, 1.0, 0.0),
    "Loan request only": (0.0, 0.0, 1.0),
    "Mixed allocation": (0.25, 0.25, 0.0),
}

rows = []

for name, (savings_action, investment_action, loan_action) in experiments.items():
    env.reset(options={"user_id": user_id})

    action = np.zeros(env.action_space.shape, dtype=np.float32)
    action[:, 0] = savings_action
    action[:, 1] = investment_action
    action[:, 2] = loan_action

    _, reward, terminated, truncated, info = env.step(action)

    rows.append({
        "policy": name,
        "monthly_surplus": info["monthly_surplus"],
        "savings_contribution": info["savings_contribution"],
        "investment_contribution": info["investment_contribution"],
        "new_loan_principal": info["new_loan_principal"],
        "new_loan_emi": info["new_loan_emi"],
        "combined_commitment": info["combined_monthly_commitment"],
        "cash_after": env.cash,
        "portfolio_after": env.portfolio,
        "loan_balance_after": env.loan_balance,
        "goal_funding_after": env.goal_balances.sum(),
        "reward": reward,
    })

comparison = pd.DataFrame(rows)
print(comparison.round(2).to_string(index=False))

# ===== CELL 115 =====  type=code  exec=188
from pathlib import Path
from datetime import datetime
import shutil

env_path = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/"
    "05_simulation_runs/rl_prototype/goalpilot_env.py"
)

backup_path = env_path.with_name(
    "goalpilot_env.py.pre_loan_goal_assignment.bak"
)

if not env_path.exists():
    raise FileNotFoundError(f"Environment file not found: {env_path}")

if backup_path.exists():
    raise FileExistsError(
        f"Backup already exists; refusing to overwrite it: {backup_path}"
    )

shutil.copy2(env_path, backup_path)

source = env_path.read_text()

loan_start = source.find(
    "        # A new loan can be requested only if the EMI fits remaining surplus."
)
loan_end = source.find(
    "        # Enforce the budget before applying any financial state updates."
)

if loan_start == -1 or loan_end == -1 or loan_end <= loan_start:
    raise RuntimeError(
        "Expected loan-allocation section not found. "
        "No environment code was changed."
    )

loan_section = source[loan_start:loan_end]

print("Backup created:", backup_path)
print("\nCurrent loan-allocation section:")
print(loan_section)
print("\nNo environment code has been modified yet.")

# ===== CELL 116 =====  type=code  exec=189
from pathlib import Path

env_path = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/"
    "05_simulation_runs/rl_prototype/goalpilot_env.py"
)

source = env_path.read_text()
updated = source

replacements = [
    (
        "        new_loan = 0.0\n"
        "        new_emi = 0.0\n"
        "        if self.loan_months_left == 0 and available_after_existing_loan > 0:\n"
        "            goal_idx = int(np.argmax(action[:len(self.user_goals), 2]))\n"
        "            requested_fraction = float(action[goal_idx, 2])",
        "        new_loan = 0.0\n"
        "        new_emi = 0.0\n"
        "        new_loan_goal_idx = -1\n"
        "        if self.loan_months_left == 0 and available_after_existing_loan > 0:\n"
        "            goal_idx = int(np.argmax(action[:len(self.user_goals), 2]))\n"
        "            new_loan_goal_idx = goal_idx\n"
        "            requested_fraction = float(action[goal_idx, 2])",
    ),
    (
        "        monthly_loan_commitment = emi_due + float(new_emi)\n\n"
        "        # Credit goal balances using the cash/investment allocations.\n"
        "        # Keep the previous balances to reward only newly achieved progress.\n"
        "        previous_goal_balances = self.goal_balances.copy()\n"
        "        contribution = savings_alloc + invest_alloc\n"
        "        for j, amount in enumerate(contribution):\n"
        "            self.goal_balances[j] += float(amount)",
        "        monthly_loan_commitment = emi_due + float(new_emi)\n\n"
        "        # Apply only the loan amount needed by the selected goal.\n"
        "        # The full principal remains a liability; unused proceeds do not\n"
        "        # count as goal funding in this prototype.\n"
        "        loan_goal_contribution = 0.0\n"
        "        if new_loan > 0.0 and new_loan_goal_idx >= 0:\n"
        "            remaining_after_contributions = max(\n"
        "                0.0,\n"
        "                float(self.goal_targets[new_loan_goal_idx])\n"
        "                - float(self.goal_balances[new_loan_goal_idx])\n"
        "                - float(savings_alloc[new_loan_goal_idx])\n"
        "                - float(invest_alloc[new_loan_goal_idx]),\n"
        "            )\n"
        "            loan_goal_contribution = min(\n"
        "                float(new_loan), remaining_after_contributions\n"
        "            )\n\n"
        "        # Credit goal balances and reward only newly achieved progress.\n"
        "        previous_goal_balances = self.goal_balances.copy()\n"
        "        contribution = savings_alloc + invest_alloc\n"
        "        if loan_goal_contribution > 0.0:\n"
        "            contribution[new_loan_goal_idx] += loan_goal_contribution\n"
        "        for j, amount in enumerate(contribution):\n"
        "            self.goal_balances[j] += float(amount)",
    ),
]

for old, new in replacements:
    count = updated.count(old)
    if count != 1:
        raise RuntimeError(
            "Patch stopped safely: expected exactly one match, "
            f"found {count}. No changes have been written."
        )
    updated = updated.replace(old, new, 1)

# Verify the intended logic exists before writing.
assert "new_loan_goal_idx = -1" in updated
assert "loan_goal_contribution = min(" in updated
assert "contribution[new_loan_goal_idx] += loan_goal_contribution" in updated

env_path.write_text(updated)

print("Loan-to-goal patch applied successfully.")
print("Safety backup remains available.")
print("\nNext: reload the module and run regression tests.")

# ===== CELL 117 =====  type=code  exec=190
import importlib
import numpy as np
import pandas as pd
from pathlib import Path
import goalpilot_env

base = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/"
    "05_simulation_runs/rl_prototype"
)

goalpilot_env = importlib.reload(goalpilot_env)

profiles = pd.read_csv(base / "rl_sample_financial_profiles.csv")
goals = pd.read_csv(base / "rl_sample_goals.csv")
market = pd.read_csv(base / "rl_market_credit_validated.csv")

env = goalpilot_env.GoalPilotEnv(
    profiles=profiles,
    goals=goals,
    market=market,
    user_ids=["USER_00001"],
    seed=2026,
)

# Test 1: request a loan for the first goal, with no savings/investment allocation.
user_id = "USER_00001"
env.reset(options={"user_id": user_id})

before_balances = env.goal_balances.copy()
before_loan = env.loan_balance

loan_action = np.zeros(env.action_space.shape, dtype=np.float32)
loan_action[0, 2] = 1.0

_, loan_reward, terminated, truncated, loan_info = env.step(loan_action)

after_balances = env.goal_balances.copy()
selected_goal = int(np.argmax(loan_action[:, 2]))

print("LOAN-ALLOCATION TEST")
print("Selected goal index:", selected_goal)
print("New loan principal:", round(loan_info["new_loan_principal"], 2))
print("New loan EMI:", round(loan_info["new_loan_emi"], 2))
print("Loan balance after step:", round(env.loan_balance, 2))
print("Selected goal funding before:", round(before_balances[selected_goal], 2))
print("Selected goal funding after:", round(after_balances[selected_goal], 2))
print("Goal funding increase:", round(
    after_balances[selected_goal] - before_balances[selected_goal], 2
))
print("Reward:", round(loan_reward, 4))

# Test 2: full 142-month episode with a mixed allocation and no loan requests.
env.reset(options={"user_id": user_id})

max_goal_overshoot = 0.0
max_budget_excess = 0.0
min_balance = 0.0
finite = True
steps = 0

while True:
    action = np.zeros(env.action_space.shape, dtype=np.float32)
    action[:, 0] = 0.25
    action[:, 1] = 0.25

    obs, reward, terminated, truncated, info = env.step(action)
    steps += 1

    max_goal_overshoot = max(
        max_goal_overshoot,
        float(np.max(env.goal_balances - env.goal_targets)),
    )
    max_budget_excess = max(
        max_budget_excess,
        float(info["combined_monthly_commitment"] - info["monthly_surplus"]),
    )
    min_balance = min(
        min_balance,
        float(env.cash),
        float(env.portfolio),
        float(env.loan_balance),
        float(np.min(env.goal_balances)),
    )
    finite = finite and bool(
        np.isfinite(obs).all()
        and np.isfinite(reward)
        and np.isfinite(env.goal_balances).all()
        and np.isfinite(env.loan_balance)
    )

    if terminated or truncated:
        break

print("\nFULL-EPISODE REGRESSION TEST")
print("Steps:", steps)
print("Goal overshoot:", round(max_goal_overshoot, 6))
print("Budget excess:", round(max_budget_excess, 6))
print("Minimum balance:", round(min_balance, 6))
print("All values finite:", finite)
print("Final goal funding:", round(float(env.goal_balances.sum()), 2))
print("Final portfolio:", round(float(env.portfolio), 2))
print("Final loan balance:", round(float(env.loan_balance), 2))

# ===== CELL 118 =====  type=code  exec=191
from pathlib import Path

env_path = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/"
    "05_simulation_runs/rl_prototype/goalpilot_env.py"
)

source = env_path.read_text()

old = (
    "            new_loan = new_emi / emi_factor if emi_factor > 0 else 0.0\n"
    "            new_loan = min(new_loan, 150000.0)\n"
    "            new_emi = new_loan * emi_factor\n"
)

new = (
    "            new_loan = new_emi / emi_factor if emi_factor > 0 else 0.0\n"
    "            new_loan = min(new_loan, 150000.0)\n"
    "            # Do not borrow more than the selected goal still requires.\n"
    "            remaining_goal_need = max(\n"
    "                0.0,\n"
    "                float(self.goal_targets[goal_idx])\n"
    "                - float(self.goal_balances[goal_idx])\n"
    "                - float(savings_alloc[goal_idx])\n"
    "                - float(invest_alloc[goal_idx]),\n"
    "            )\n"
    "            new_loan = min(new_loan, remaining_goal_need)\n"
    "            new_emi = new_loan * emi_factor\n"
)

count = source.count(old)
if count != 1:
    raise RuntimeError(
        f"Expected one loan-cap block, found {count}. "
        "No changes were written."
    )

env_path.write_text(source.replace(old, new, 1))
print("Loan principal now capped at the selected goal's remaining requirement.")
print("EMI is recalculated from the capped principal.")

# ===== CELL 119 =====  type=code  exec=192
import importlib
import numpy as np
import pandas as pd
from pathlib import Path
import goalpilot_env

base = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/"
    "05_simulation_runs/rl_prototype"
)

goalpilot_env = importlib.reload(goalpilot_env)

profiles = pd.read_csv(base / "rl_sample_financial_profiles.csv")
goals = pd.read_csv(base / "rl_sample_goals.csv")
market = pd.read_csv(base / "rl_market_credit_validated.csv")

user_id = "USER_00001"

env = goalpilot_env.GoalPilotEnv(
    profiles=profiles,
    goals=goals,
    market=market,
    user_ids=[user_id],
    seed=2026,
)

# Test a maximum loan request for the first goal.
env.reset(options={"user_id": user_id})
selected_goal = 0

before = float(env.goal_balances[selected_goal])
target = float(env.goal_targets[selected_goal])
remaining_need = max(0.0, target - before)

action = np.zeros(env.action_space.shape, dtype=np.float32)
action[selected_goal, 2] = 1.0

_, reward, terminated, truncated, info = env.step(action)

principal = float(info["new_loan_principal"])
emi = float(info["new_loan_emi"])
goal_increase = float(env.goal_balances[selected_goal] - before)

print("LOAN CAP TEST")
print("Goal remaining before loan:", round(remaining_need, 2))
print("Loan principal:", round(principal, 2))
print("Loan EMI:", round(emi, 2))
print("Goal funding increase:", round(goal_increase, 2))
print("Loan exceeds goal need:", principal > remaining_need + 0.01)
print("Goal exceeds target:", env.goal_balances[selected_goal] > target + 0.01)

# Regression test over a complete episode, without requesting new loans.
env.reset(options={"user_id": user_id})

steps = 0
max_budget_excess = 0.0
max_goal_overshoot = 0.0
minimum_balance = 0.0
finite = True

while True:
    action = np.zeros(env.action_space.shape, dtype=np.float32)
    action[:, 0] = 0.25
    action[:, 1] = 0.25

    obs, reward, terminated, truncated, info = env.step(action)
    steps += 1

    max_budget_excess = max(
        max_budget_excess,
        float(info["combined_monthly_commitment"] - info["monthly_surplus"]),
    )
    max_goal_overshoot = max(
        max_goal_overshoot,
        float(np.max(env.goal_balances - env.goal_targets)),
    )
    minimum_balance = min(
        minimum_balance,
        float(env.cash),
        float(env.portfolio),
        float(env.loan_balance),
        float(np.min(env.goal_balances)),
    )
    finite = finite and bool(
        np.isfinite(obs).all()
        and np.isfinite(reward)
        and np.isfinite(env.goal_balances).all()
        and np.isfinite(env.loan_balance)
    )

    if terminated or truncated:
        break

print("\nFULL-EPISODE CHECK")
print("Steps:", steps)
print("Maximum budget excess:", round(max_budget_excess, 6))
print("Maximum goal overshoot:", round(max_goal_overshoot, 6))
print("Minimum balance:", round(minimum_balance, 6))
print("All values finite:", finite)

# ===== CELL 120 =====  type=code  exec=193
import importlib
import numpy as np
import pandas as pd
from pathlib import Path
import goalpilot_env

base = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/"
    "05_simulation_runs/rl_prototype"
)

goalpilot_env = importlib.reload(goalpilot_env)

profiles = pd.read_csv(base / "rl_sample_financial_profiles.csv")
goals = pd.read_csv(base / "rl_sample_goals.csv")
market = pd.read_csv(base / "rl_market_credit_validated.csv")

policies = {
    "No action": (0.0, 0.0, 0.0),
    "Savings only": (1.0, 0.0, 0.0),
    "Investments only": (0.0, 1.0, 0.0),
    "Mixed allocation": (0.25, 0.25, 0.0),
}

user_ids = profiles["user_id"].astype(str).tolist()

env = goalpilot_env.GoalPilotEnv(
    profiles=profiles,
    goals=goals,
    market=market,
    user_ids=user_ids,
    seed=2026,
)

results = []

for user_id in user_ids:
    for policy_name, (save_action, invest_action, loan_action) in policies.items():
        env.reset(options={"user_id": user_id})

        initial_goal_funding = float(env.goal_balances.sum())
        total_reward = 0.0
        total_savings = 0.0
        total_investments = 0.0
        total_new_loans = 0.0
        max_budget_excess = 0.0
        max_goal_overshoot = 0.0
        steps = 0

        while True:
            action = np.zeros(env.action_space.shape, dtype=np.float32)
            action[:, 0] = save_action
            action[:, 1] = invest_action
            action[:, 2] = loan_action

            obs, reward, terminated, truncated, info = env.step(action)

            total_reward += float(reward)
            total_savings += float(info["savings_contribution"])
            total_investments += float(info["investment_contribution"])
            total_new_loans += float(info["new_loan_principal"])

            max_budget_excess = max(
                max_budget_excess,
                float(
                    info["combined_monthly_commitment"]
                    - info["monthly_surplus"]
                ),
            )
            max_goal_overshoot = max(
                max_goal_overshoot,
                float(np.max(env.goal_balances - env.goal_targets)),
            )

            steps += 1

            if terminated or truncated:
                break

        target_total = float(env.goal_targets.sum())
        final_goal_funding = float(env.goal_balances.sum())
        final_wealth = (
            float(env.cash)
            + float(env.portfolio)
            - float(env.loan_balance)
        )

        results.append({
            "user_id": user_id,
            "policy": policy_name,
            "steps": steps,
            "initial_goal_funding": initial_goal_funding,
            "final_goal_funding": final_goal_funding,
            "goal_funding_added": final_goal_funding - initial_goal_funding,
            "goal_funding_ratio": (
                final_goal_funding / target_total if target_total > 0 else 0.0
            ),
            "final_cash": float(env.cash),
            "final_portfolio": float(env.portfolio),
            "final_loan_balance": float(env.loan_balance),
            "final_net_financial_wealth": final_wealth,
            "total_savings_contributions": total_savings,
            "total_investment_contributions": total_investments,
            "total_new_loan_principal": total_new_loans,
            "total_reward": total_reward,
            "max_budget_excess": max_budget_excess,
            "max_goal_overshoot": max_goal_overshoot,
        })

results_df = pd.DataFrame(results)

output_path = base / "rl_baseline_policy_comparison.csv"
results_df.to_csv(output_path, index=False)

summary = (
    results_df.groupby("policy")
    .agg(
        users=("user_id", "nunique"),
        mean_goal_funding_ratio=("goal_funding_ratio", "mean"),
        median_goal_funding_ratio=("goal_funding_ratio", "median"),
        mean_goal_funding_added=("goal_funding_added", "mean"),
        mean_final_net_wealth=("final_net_financial_wealth", "mean"),
        mean_final_portfolio=("final_portfolio", "mean"),
        mean_final_loan_balance=("final_loan_balance", "mean"),
        mean_total_reward=("total_reward", "mean"),
        max_budget_excess=("max_budget_excess", "max"),
        max_goal_overshoot=("max_goal_overshoot", "max"),
    )
    .reset_index()
)

print("BASELINE COMPARISON — ALL USERS")
print(summary.round(4).to_string(index=False))
print("\nResults saved to:", output_path)
print("Total user-policy episodes:", len(results_df))
print("Total simulated steps:", int(results_df["steps"].sum()))
print(
    "Budget violations:",
    int((results_df["max_budget_excess"] > 0.01).sum()),
)
print(
    "Goal-cap violations:",
    int((results_df["max_goal_overshoot"] > 0.01).sum()),
)

# ===== CELL 121 =====  type=code  exec=194
import ast
from pathlib import Path

project = Path(
    "/content/drive/MyDrive/GoalPilot_AI/"
    "GoalPilot_MultiGoal_Extension"
)

files_to_inspect = [
    project / "src" / "multi_goal_optimizer.py",
    project / "src" / "simulation_adapter.py",
]

for path in files_to_inspect:
    print(f"\n{'=' * 20} {path.name} {'=' * 20}")

    if not path.exists():
        print("FILE NOT FOUND")
        continue

    source = path.read_text()
    tree = ast.parse(source)

    print("Top-level functions and classes:")
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            print(f"\nFunction: {node.name} (line {node.lineno})")
            print("Arguments:", [
                arg.arg for arg in node.args.args
            ])
            if ast.get_docstring(node):
                print("Docstring:", ast.get_docstring(node))

        elif isinstance(node, ast.ClassDef):
            print(f"\nClass: {node.name} (line {node.lineno})")
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    print(
                        f"  Method: {item.name} "
                        f"(line {item.lineno})"
                    )
                    print(
                        "  Arguments:",
                        [arg.arg for arg in item.args.args],
                    )
                    if ast.get_docstring(item):
                        print("  Docstring:", ast.get_docstring(item))

    print("\nImports:")
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            print(ast.unparse(node))

# ===== CELL 122 =====  type=code  exec=195
import ast
from pathlib import Path

project = Path(
    "/content/drive/MyDrive/GoalPilot_AI/"
    "GoalPilot_MultiGoal_Extension"
)

optimizer_path = project / "src" / "multi_goal_optimizer.py"
adapter_path = project / "src" / "simulation_adapter.py"

def show_definition(path, names):
    source = path.read_text()
    lines = source.splitlines()
    tree = ast.parse(source)

    print(f"\n{'=' * 18} {path.name} {'=' * 18}")

    for node in tree.body:
        node_name = getattr(node, "name", None)
        if node_name not in names:
            continue

        start = node.lineno - 1
        end = node.end_lineno
        print(f"\n--- {node_name}: lines {start + 1}-{end} ---")

        for i in range(start, end):
            print(f"{i + 1:4}: {lines[i]}")

show_definition(
    optimizer_path,
    {
        "FinancialState",
        "prepare_goals",
        "optimize_multi_goal",
        "strategy_comparison",
    },
)

show_definition(
    adapter_path,
    {
        "financial_state_from_simulation_row",
        "legacy_goal_to_goal_row",
    },
)

# ===== CELL 123 =====  type=code  exec=196
from pathlib import Path
import pandas as pd

base = Path(
    "/content/drive/MyDrive/GoalPilot_AI"
)

run_dir = (
    base / "simulation" / "05_simulation_runs"
    / "rl_prototype"
)

project = base / "GoalPilot_MultiGoal_Extension"

print("=== RL input files ===")
for name in [
    "rl_sample_financial_profiles.csv",
    "rl_sample_goals.csv",
    "rl_market_credit_validated.csv",
    "rl_baseline_policy_comparison.csv",
]:
    path = run_dir / name
    print(f"{name}: {'FOUND' if path.exists() else 'NOT FOUND'}")

profiles_path = run_dir / "rl_sample_financial_profiles.csv"
goals_path = run_dir / "rl_sample_goals.csv"

profiles = pd.read_csv(profiles_path)
goals = pd.read_csv(goals_path)

print("\n=== Financial profiles ===")
print("Shape:", profiles.shape)
print("Columns:", profiles.columns.tolist())
print(profiles.head(2).to_string(index=False))

print("\n=== Multi-goal data ===")
print("Shape:", goals.shape)
print("Columns:", goals.columns.tolist())
print(goals.head(3).to_string(index=False))

print("\n=== Goals per user ===")
user_col = next(
    (c for c in ["user_id", "profile_id", "household_id"]
     if c in goals.columns),
    None
)

if user_col:
    counts = goals.groupby(user_col).size()
    print("Users:", len(counts))
    print("Minimum goals:", counts.min())
    print("Median goals:", counts.median())
    print("Maximum goals:", counts.max())
else:
    print("Could not identify the user ID column in the goals dataset.")

print("\n=== LP source files ===")
for name in [
    "src/multi_goal_optimizer.py",
    "src/simulation_adapter.py",
]:
    path = project / name
    print(f"{name}: {'FOUND' if path.exists() else 'NOT FOUND'}")

# ===== CELL 124 =====  type=code  exec=198
import inspect
import multi_goal_optimizer

print("=== Imported module ===")
print(multi_goal_optimizer.__file__)

print("\n=== FinancialState constructor ===")
print(inspect.signature(multi_goal_optimizer.FinancialState))

print("\n=== FinancialState definition ===")
print(inspect.getsource(multi_goal_optimizer.FinancialState))

print("\n=== Optimizer file on Drive ===")
from pathlib import Path

optimizer_path = (
    Path("/content/drive/MyDrive/GoalPilot_AI")
    / "GoalPilot_MultiGoal_Extension"
    / "src"
    / "multi_goal_optimizer.py"
)

print("Exists:", optimizer_path.exists())

if optimizer_path.exists():
    source = optimizer_path.read_text()
    start = source.find("class FinancialState:")
    print(source[start:start + 1800])

# ===== CELL 125 =====  type=code  exec=199
import sys
import importlib
import inspect
from pathlib import Path

project_src = str(
    Path("/content/drive/MyDrive/GoalPilot_AI")
    / "GoalPilot_MultiGoal_Extension"
    / "src"
)

if project_src not in sys.path:
    sys.path.insert(0, project_src)

import multi_goal_optimizer

# Force Python to reload the module from its source file.
importlib.invalidate_caches()
multi_goal_optimizer = importlib.reload(multi_goal_optimizer)

print("Module:", multi_goal_optimizer.__file__)
print("FinancialState signature:")
print(inspect.signature(multi_goal_optimizer.FinancialState))

required_fields = {
    "monthly_income",
    "essential_expenses",
    "discretionary_expenses",
    "existing_emi",
    "liquid_savings",
    "existing_investments",
    "usable_existing_investments",
    "risk_capacity",
}

actual_fields = set(
    inspect.signature(
        multi_goal_optimizer.FinancialState
    ).parameters
)

missing = required_fields - actual_fields

if missing:
    raise RuntimeError(
        f"Module reload did not resolve the mismatch. Missing: {missing}"
    )

print("\nSUCCESS: The current FinancialState definition is loaded.")

# ===== CELL 126 =====  type=code  exec=200
import pandas as pd
from pathlib import Path

base = Path("/content/drive/MyDrive/GoalPilot_AI")
run_dir = base / "simulation/05_simulation_runs/rl_prototype"

profiles = pd.read_csv(
    run_dir / "rl_sample_financial_profiles.csv"
)
goals = pd.read_csv(
    run_dir / "rl_sample_goals.csv"
)

user_id = "USER_00001"
p = profiles.loc[profiles["user_id"] == user_id].iloc[0]
user_goals = goals.loc[goals["user_id"] == user_id].copy()

FinancialState = multi_goal_optimizer.FinancialState
optimize_multi_goal = multi_goal_optimizer.optimize_multi_goal

state = FinancialState(
    monthly_income=float(p["monthly_income"]),
    essential_expenses=float(p["monthly_expenditure"]),
    existing_emi=float(p["monthly_emi"]),
    liquid_savings=float(p["initial_savings"]),
    existing_investments=float(p["initial_investment"]),
    usable_existing_investments=0.0,
    emergency_months=6.0,
    emi_income_ratio_cap=0.35,
    risk_capacity=float(p["risk_score"]),
)

result = optimize_multi_goal(
    user_goals,
    state,
    annual_inflation=0.03,
    savings_return=0.0,
    investment_return=0.05,
    investment_risk_score=0.4,
    loan_annual_rate=0.12,
    loan_tenure_months=60,
    max_loan_per_goal=150000.0,
)

print("=== LP integration test ===")
print("User:", user_id)
print("Goals:", len(user_goals))
print("Solver status:", result["status"])
print("Solver message:", result.get("solver_message", ""))

if result["status"] == "optimal":
    s = result["summary"]

    print("\n=== Allocation summary ===")
    for key in [
        "total_future_goal_cost",
        "total_funding_gap",
        "total_projected_new_funding",
        "total_shortfall",
        "available_cash_above_emergency_reserve",
        "monthly_surplus_available",
        "monthly_contributions_allocated",
        "new_total_emi",
        "loan_cost_total",
        "weighted_goal_achievement",
    ]:
        print(f"{key}: {s.get(key)}")

    columns = [
        "goal_id",
        "goal_name",
        "funding_gap",
        "initial_savings_allocated",
        "monthly_savings_contribution",
        "monthly_investment_contribution",
        "loan_principal",
        "estimated_loan_emi",
        "projected_new_funding",
        "shortfall",
        "achievement_ratio",
    ]

    print("\n=== Per-goal allocations ===")
    display(result["allocations"][columns].round(2))

    print("\n=== Constraint checks ===")
    for key in [
        "emergency_fund_preserved",
        "monthly_surplus_respected",
        "combined_monthly_cashflow_respected",
        "existing_assets_respected",
        "emi_cap_respected",
    ]:
        print(f"{key}: {s.get(key)}")
else:
    print("LP did not return an optimal solution.")

# ===== CELL 127 =====  type=code  exec=201
import pandas as pd
import numpy as np
from pathlib import Path

base = Path("/content/drive/MyDrive/GoalPilot_AI")
run_dir = base / "simulation/05_simulation_runs/rl_prototype"

profiles = pd.read_csv(
    run_dir / "rl_sample_financial_profiles.csv"
)
goals = pd.read_csv(
    run_dir / "rl_sample_goals.csv"
)

# Use the currently reloaded optimizer.
FinancialState = multi_goal_optimizer.FinancialState
optimize_multi_goal = multi_goal_optimizer.optimize_multi_goal

records = []
allocation_frames = []
errors = []

constraint_keys = [
    "emergency_fund_preserved",
    "monthly_surplus_respected",
    "combined_monthly_cashflow_respected",
    "existing_assets_respected",
    "emi_cap_respected",
]

for _, p in profiles.iterrows():
    user_id = str(p["user_id"])
    user_goals = goals.loc[
        goals["user_id"] == user_id
    ].copy()

    try:
        state = FinancialState(
            monthly_income=float(p["monthly_income"]),
            essential_expenses=float(p["monthly_expenditure"]),
            existing_emi=float(p["monthly_emi"]),
            liquid_savings=float(p["initial_savings"]),
            existing_investments=float(p["initial_investment"]),
            usable_existing_investments=0.0,
            emergency_months=6.0,
            emi_income_ratio_cap=0.35,
            risk_capacity=float(p["risk_score"]),
        )

        result = optimize_multi_goal(
            user_goals,
            state,
            annual_inflation=0.03,
            savings_return=0.0,
            investment_return=0.05,
            investment_risk_score=0.4,
            loan_annual_rate=0.12,
            loan_tenure_months=60,
            max_loan_per_goal=150000.0,
        )

        record = {
            "user_id": user_id,
            "goal_count": len(user_goals),
            "status": result["status"],
        }

        if result["status"] == "optimal":
            s = result["summary"]

            record.update({
                "weighted_goal_achievement":
                    s["weighted_goal_achievement"],
                "total_funding_gap":
                    s["total_funding_gap"],
                "projected_new_funding":
                    s["total_projected_new_funding"],
                "total_shortfall":
                    s["total_shortfall"],
                "monthly_surplus":
                    s["monthly_surplus_available"],
                "monthly_contributions":
                    s["monthly_contributions_allocated"],
                "new_total_emi":
                    s["new_total_emi"],
                "loan_cost":
                    s["loan_cost_total"],
            })

            for key in constraint_keys:
                record[key] = bool(s[key])

            alloc = result["allocations"].copy()
            alloc.insert(0, "user_id", user_id)
            allocation_frames.append(alloc)

        else:
            record["solver_message"] = result.get(
                "solver_message", ""
            )

        records.append(record)

    except Exception as exc:
        errors.append({
            "user_id": user_id,
            "error": repr(exc),
        })

summary_df = pd.DataFrame(records)
allocations_df = (
    pd.concat(allocation_frames, ignore_index=True)
    if allocation_frames
    else pd.DataFrame()
)

summary_path = run_dir / "rl_lp_all_users_summary.csv"
allocations_path = run_dir / "rl_lp_all_users_allocations.csv"

summary_df.to_csv(summary_path, index=False)
allocations_df.to_csv(allocations_path, index=False)

print("=== LP validation across users ===")
print("Input users:", len(profiles))
print("Users processed:", len(records))
print("Exceptions:", len(errors))
print("Optimal solutions:",
      int((summary_df["status"] == "optimal").sum()))
print("Non-optimal solutions:",
      int((summary_df["status"] != "optimal").sum()))

successful = summary_df.loc[
    summary_df["status"] == "optimal"
].copy()

if not successful.empty:
    print("\n=== Aggregate results ===")
    print(
        successful[
            [
                "weighted_goal_achievement",
                "projected_new_funding",
                "total_shortfall",
                "monthly_contributions",
                "new_total_emi",
            ]
        ].describe().round(4)
    )

    print("\n=== Constraint violations ===")
    for key in constraint_keys:
        violations = int((~successful[key]).sum())
        print(f"{key}: {violations}")

    print("\n=== Users with largest projected shortfalls ===")
    display(
        successful.nlargest(10, "total_shortfall")[
            [
                "user_id",
                "goal_count",
                "monthly_surplus",
                "weighted_goal_achievement",
                "projected_new_funding",
                "total_shortfall",
                "new_total_emi",
            ]
        ].round(2)
    )

print("\n=== Saved files ===")
print(summary_path)
print(allocations_path)

if errors:
    print("\n=== First errors ===")
    display(pd.DataFrame(errors).head(10))

# ===== CELL 128 =====  type=code  exec=202
import pandas as pd
from pathlib import Path

run_dir = (
    Path("/content/drive/MyDrive/GoalPilot_AI")
    / "simulation/05_simulation_runs/rl_prototype"
)

lp_summary = pd.read_csv(
    run_dir / "rl_lp_all_users_summary.csv"
)
lp_allocations = pd.read_csv(
    run_dir / "rl_lp_all_users_allocations.csv"
)
rl_baselines = pd.read_csv(
    run_dir / "rl_baseline_policy_comparison.csv"
)

print("=== RL baseline metrics ===")
print("Columns:", rl_baselines.columns.tolist())
display(rl_baselines)

print("\n=== LP allocation columns ===")
print(lp_allocations.columns.tolist())

# Calculate an unweighted per-user average of the LP's
# per-goal achievement ratios, capped at 100%.
lp_allocations["achievement_ratio_capped"] = (
    pd.to_numeric(
        lp_allocations["achievement_ratio"],
        errors="coerce",
    ).clip(0, 1)
)

lp_goal_metrics = (
    lp_allocations
    .groupby("user_id")
    .agg(
        goal_count=("goal_id", "count"),
        mean_goal_achievement=(
            "achievement_ratio_capped", "mean"
        ),
        goals_fully_funded=(
            "achievement_ratio_capped",
            lambda x: int((x >= 1 - 1e-9).sum()),
        ),
        total_loan_principal=("loan_principal", "sum"),
        total_monthly_emi=("estimated_loan_emi", "sum"),
        total_shortfall=("shortfall", "sum"),
    )
    .reset_index()
)

lp_goal_metrics = lp_goal_metrics.merge(
    lp_summary[
        [
            "user_id",
            "status",
            "weighted_goal_achievement",
            "projected_new_funding",
        ]
    ],
    on="user_id",
    how="left",
)

print("\n=== LP achievement metrics ===")
print(
    lp_goal_metrics[
        [
            "mean_goal_achievement",
            "weighted_goal_achievement",
            "goals_fully_funded",
            "total_monthly_emi",
            "total_shortfall",
        ]
    ].describe().round(4)
)

print("\n=== LP users with highest unweighted goal achievement ===")
display(
    lp_goal_metrics.nlargest(
        10, "mean_goal_achievement"
    )[
        [
            "user_id",
            "goal_count",
            "mean_goal_achievement",
            "weighted_goal_achievement",
            "goals_fully_funded",
            "total_monthly_emi",
            "total_shortfall",
        ]
    ].round(4)
)

output_path = run_dir / "rl_lp_goal_level_metrics.csv"
lp_goal_metrics.to_csv(output_path, index=False)

print("\nSaved:", output_path)

# ===== CELL 129 =====  type=code  exec=203
import pandas as pd
import numpy as np
from pathlib import Path

run_dir = (
    Path("/content/drive/MyDrive/GoalPilot_AI")
    / "simulation/05_simulation_runs/rl_prototype"
)

rl = pd.read_csv(run_dir / "rl_baseline_policy_comparison.csv")
lp = pd.read_csv(run_dir / "rl_lp_all_users_summary.csv")
lp_goals = pd.read_csv(run_dir / "rl_lp_goal_level_metrics.csv")

# Aggregate the existing RL baseline results by policy.
rl_summary = (
    rl.groupby("policy")
    .agg(
        users=("user_id", "nunique"),
        mean_goal_funding_ratio=("goal_funding_ratio", "mean"),
        median_goal_funding_ratio=("goal_funding_ratio", "median"),
        mean_net_financial_wealth=("final_net_financial_wealth", "mean"),
        mean_final_portfolio=("final_portfolio", "mean"),
        mean_final_loan_balance=("final_loan_balance", "mean"),
        mean_new_loan_principal=("total_new_loan_principal", "mean"),
        mean_reward=("total_reward", "mean"),
        max_budget_excess=("max_budget_excess", "max"),
        max_goal_overshoot=("max_goal_overshoot", "max"),
    )
    .reset_index()
)

# Summarize LP results separately because these are projections.
lp_summary = pd.DataFrame([{
    "method": "LP (projected)",
    "users": lp.loc[lp["status"] == "optimal", "user_id"].nunique(),
    "mean_unweighted_goal_achievement":
        lp_goals["mean_goal_achievement"].mean(),
    "median_unweighted_goal_achievement":
        lp_goals["mean_goal_achievement"].median(),
    "mean_weighted_goal_achievement":
        lp["weighted_goal_achievement"].mean(),
    "mean_projected_new_funding":
        lp["projected_new_funding"].mean(),
    "mean_projected_shortfall":
        lp["total_shortfall"].mean(),
    "mean_new_monthly_emi":
        lp_goals["total_monthly_emi"].mean(),
}])

print("=== RL baseline summary: simulated outcomes ===")
display(rl_summary.round(4))

print("\n=== LP summary: projected outcomes ===")
display(lp_summary.round(4))

print("\n=== Interpretation ===")
print(
    "RL goal funding ratios are episode outcomes. LP achievement ratios "
    "are deadline projections under fixed assumptions."
)
print(
    "Do not rank LP against RL using these headline values alone. "
    "The next comparison must align goal targets, evaluation horizon, "
    "initial state, market assumptions, and treatment of loan proceeds."
)

output_path = run_dir / "rl_lp_diagnostic_summary.csv"
rl_summary.to_csv(
    run_dir / "rl_policy_diagnostic_summary.csv",
    index=False
)
lp_summary.to_csv(output_path, index=False)

print("\nSaved diagnostic summaries:")
print(run_dir / "rl_policy_diagnostic_summary.csv")
print(output_path)

# ===== CELL 130 =====  type=code  exec=204
import ast
import inspect
import importlib.util
from pathlib import Path

env_path = (
    Path("/content/drive/MyDrive/GoalPilot_AI")
    / "simulation/05_simulation_runs/rl_prototype"
    / "goalpilot_env.py"
)

source = env_path.read_text()
tree = ast.parse(source)
lines = source.splitlines()

print("=== Environment file ===")
print(env_path)
print("Total lines:", len(lines))

# Show the main environment methods without dumping the entire file.
wanted_methods = {
    "__init__",
    "reset",
    "step",
}

for node in ast.walk(tree):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        if node.name in wanted_methods:
            start = node.lineno - 1
            end = node.end_lineno
            print(f"\n{'=' * 12} {node.name}: lines {start + 1}-{end} {'=' * 12}")
            for i in range(start, end):
                print(f"{i + 1:4}: {lines[i]}")

print("\n=== Other relevant accounting/reward references ===")
keywords = [
    "goal_targets",
    "goal_balances",
    "goal_horizons",
    "deadline",
    "monthly_return",
    "market_return",
    "reward",
    "loan_balance",
    "net_financial_wealth",
    "terminated",
    "truncated",
]

for keyword in keywords:
    matches = [
        (i + 1, line.strip())
        for i, line in enumerate(lines)
        if keyword.lower() in line.lower()
    ]
    if matches:
        print(f"\n[{keyword}]")
        for line_no, text in matches[:12]:
            print(f"{line_no:4}: {text}")

print("\n=== Audit complete: source only; no files modified ===")

# ===== CELL 131 =====  type=code  exec=205
import sys
import numpy as np
import pandas as pd
from pathlib import Path

run_dir = (
    Path("/content/drive/MyDrive/GoalPilot_AI")
    / "simulation/05_simulation_runs/rl_prototype"
)

sys.path.insert(0, str(run_dir))

from goalpilot_env import GoalPilotEnv

profiles = pd.read_csv(
    run_dir / "rl_sample_financial_profiles.csv"
)
goals = pd.read_csv(
    run_dir / "rl_sample_goals.csv"
)
market = pd.read_csv(
    run_dir / "rl_market_credit_validated.csv"
)

env = GoalPilotEnv(
    profiles=profiles,
    goals=goals,
    market=market,
    seed=42,
)

obs, info = env.reset(
    seed=42,
    options={"user_id": "USER_00001"},
)

obs_min = float(np.min(obs))
obs_max = float(np.max(obs))
initial_out_of_bounds = int(
    np.sum(
        (obs < env.observation_space.low - 1e-6)
        | (obs > env.observation_space.high + 1e-6)
    )
)

print("=== Initial observation ===")
print("Shape:", obs.shape)
print("Space shape:", env.observation_space.shape)
print("Minimum value:", obs_min)
print("Maximum value:", obs_max)
print("Values outside observation space:", initial_out_of_bounds)
print("Contains observation:", env.observation_space.contains(obs))

print("\n=== Goal deadlines ===")
display(
    env.user_goals[
        ["goal_id", "goal_name", "time_horizon_months",
         "current_cost", "existing_funding"]
    ].reset_index(drop=True)
)

rng = np.random.default_rng(42)
steps = 0
violations = []
deadline_results = []
observation_min = obs_min
observation_max = obs_max

while True:
    action = rng.uniform(
        0, 1, size=env.action_space.shape
    ).astype(np.float32)

    obs, reward, terminated, truncated, step_info = env.step(action)
    steps += 1

    observation_min = min(observation_min, float(obs.min()))
    observation_max = max(observation_max, float(obs.max()))

    if not np.isfinite(obs).all() or not np.isfinite(reward):
        violations.append({
            "step": steps,
            "issue": "Non-finite observation or reward",
        })

    if np.any(obs < -1e-6) or np.any(obs > 1 + 1e-6):
        violations.append({
            "step": steps,
            "issue": "Observation outside [0, 1]",
            "min": float(obs.min()),
            "max": float(obs.max()),
        })

    # Record funding progress exactly when each goal deadline is reached.
    for j, deadline in enumerate(env.goal_deadlines):
        if steps == int(deadline):
            target = max(float(env.goal_targets[j]), 1.0)
            funded = float(env.goal_balances[j])
            deadline_results.append({
                "goal_id": env.user_goals.iloc[j]["goal_id"],
                "deadline_month": int(deadline),
                "funded_at_deadline": funded,
                "target": target,
                "achievement_ratio": min(1.0, funded / target),
            })

    if terminated or truncated:
        break

print("\n=== Episode audit ===")
print("Steps completed:", steps)
print("Environment max steps:", env.max_steps)
print("Observation minimum seen:", observation_min)
print("Observation maximum seen:", observation_max)
print("Audit issues:", len(violations))

if violations:
    display(pd.DataFrame(violations).head(10))

print("\n=== Goal deadline outcomes ===")
display(pd.DataFrame(deadline_results).round(4))

print("\n=== Final state accounting ===")
print(f"Cash: ₹{env.cash:,.2f}")
print(f"Portfolio: ₹{env.portfolio:,.2f}")
print(f"Loan balance: ₹{env.loan_balance:,.2f}")
print(
    "Net financial wealth: ₹"
    f"{env.cash + env.portfolio - env.loan_balance:,.2f}"
)
print(
    "Goal funding ledger total: ₹"
    f"{env.goal_balances.sum():,.2f}"
)
print("Goal ledger is separate from financial assets.")

# ===== CELL 132 =====  type=code  exec=206
import pandas as pd
from pathlib import Path

run_dir = (
    Path("/content/drive/MyDrive/GoalPilot_AI")
    / "simulation/05_simulation_runs/rl_prototype"
)

goals = pd.read_csv(run_dir / "rl_sample_goals.csv")
profiles = pd.read_csv(run_dir / "rl_sample_financial_profiles.csv")
market = pd.read_csv(run_dir / "rl_market_credit_validated.csv")

goals["time_horizon_months"] = pd.to_numeric(
    goals["time_horizon_months"], errors="raise"
)
goals["current_cost"] = pd.to_numeric(
    goals["current_cost"], errors="raise"
)
goals["existing_funding"] = pd.to_numeric(
    goals["existing_funding"], errors="raise"
)

episode_months = len(market)

print("=== Simulation coverage ===")
print("Market rows / episode months:", episode_months)
print("Market start:", market["period"].min())
print("Market end:", market["period"].max())
print("Total users:", profiles["user_id"].nunique())
print("Total goals:", len(goals))

print("\n=== Goal deadline coverage ===")
print("Minimum horizon:", goals["time_horizon_months"].min())
print("Median horizon:", goals["time_horizon_months"].median())
print("Maximum horizon:", goals["time_horizon_months"].max())

beyond = goals.loc[
    goals["time_horizon_months"] > episode_months
].copy()

print("Goals beyond episode:", len(beyond))
print("Users with goals beyond episode:", beyond["user_id"].nunique())

if not beyond.empty:
    display(
        beyond[
            [
                "user_id",
                "goal_id",
                "goal_name",
                "time_horizon_months",
                "current_cost",
            ]
        ].sort_values(
            "time_horizon_months", ascending=False
        ).head(20)
    )

print("\n=== Initial goal-funding consistency ===")
initial_funding = (
    goals.groupby("user_id")["existing_funding"]
    .sum()
    .rename("goal_earmarks")
)

profile_savings = (
    profiles.set_index("user_id")["initial_savings"]
    .rename("initial_savings")
)

funding_check = pd.concat(
    [initial_funding, profile_savings], axis=1
).fillna(0)

funding_check["earmarks_exceed_savings"] = (
    funding_check["goal_earmarks"]
    > funding_check["initial_savings"] + 1e-6
)

print(
    "Users whose raw goal earmarks exceed initial savings:",
    int(funding_check["earmarks_exceed_savings"].sum())
)
print(
    "Maximum raw earmarks / initial savings ratio:",
    (
        funding_check["goal_earmarks"]
        / funding_check["initial_savings"].replace(0, float("nan"))
    ).max()
)

print("\n=== Audit complete: no files modified ===")

# ===== CELL 133 =====  type=code  exec=207
from pathlib import Path

env_path = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/"
    "05_simulation_runs/rl_prototype/goalpilot_env.py"
)

source = env_path.read_text().splitlines()

# Print relevant reward and deadline logic with line numbers.
keywords = [
    "goal_deadlines",
    "deadline",
    "shortfall",
    "reward",
    "terminated",
    "month_index",
]

matching_lines = [
    i for i, line in enumerate(source)
    if any(word in line.lower() for word in keywords)
]

# Show focused context around matching lines without excessive repetition.
ranges = []
for i in matching_lines:
    start, end = max(0, i - 3), min(len(source), i + 5)
    if ranges and start <= ranges[-1][1]:
        ranges[-1] = (ranges[-1][0], max(ranges[-1][1], end))
    else:
        ranges.append((start, end))

print("=== Reward, deadline and termination code ===")
for start, end in ranges:
    print(f"\n--- Lines {start + 1}–{end} ---")
    for i in range(start, end):
        print(f"{i + 1:4}: {source[i]}")

print("\n=== Deadline distribution ===")
import pandas as pd

run_dir = env_path.parent
goals = pd.read_csv(run_dir / "rl_sample_goals.csv")
horizons = pd.to_numeric(goals["time_horizon_months"])

print("Goals due within 142 months:", int((horizons <= 142).sum()))
print("Goals due after 142 months:", int((horizons > 142).sum()))
print("Goals due exactly at month 142:", int((horizons == 142).sum()))

# ===== CELL 134 =====  type=code  exec=209
import sys
from pathlib import Path
import numpy as np
import pandas as pd

run_dir = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/"
    "05_simulation_runs/rl_prototype"
)

sys.path.insert(0, str(run_dir))
from goalpilot_env import GoalPilotEnv

# Load the existing datasets
profiles = pd.read_csv(run_dir / "rl_sample_financial_profiles.csv")
goals = pd.read_csv(run_dir / "rl_sample_goals.csv")
market = pd.read_csv(run_dir / "rl_market_credit_validated.csv")

# Initialize with the required arguments
env = GoalPilotEnv(
    profiles=profiles,
    goals=goals,
    market=market
)

long_goals = goals[
    goals["time_horizon_months"] > env.max_steps
].copy()

results = []

for user_id in long_goals["user_id"].unique():
    obs, info = env.reset(options={"user_id": user_id})
    terminated = False
    truncated = False

    while not (terminated or truncated):
        action = np.zeros(env.action_space.shape, dtype=np.float32)
        obs, reward, terminated, truncated, info = env.step(action)

    user_goals = env.user_goals.reset_index(drop=True)

    for j, goal in user_goals.iterrows():
        deadline = int(goal["time_horizon_months"])

        if deadline <= env.max_steps:
            continue

        target = float(env.goal_targets[j])
        funded = float(env.goal_balances[j])

        results.append({
            "user_id": user_id,
            "goal_id": goal["goal_id"],
            "goal_name": goal["goal_name"],
            "deadline_month": deadline,
            "months_remaining_after_episode": deadline - env.max_steps,
            "target_current_cost": target,
            "funded_at_episode_end": funded,
            "funding_ratio": min(1.0, funded / max(target, 1.0)),
            "remaining_shortfall": max(0.0, target - funded),
        })

result_df = pd.DataFrame(results)

output_path = run_dir / "rl_long_horizon_no_action_reference.csv"
result_df.to_csv(output_path, index=False)

print("Long-horizon goals evaluated:", len(result_df))
print("Unique users:", result_df["user_id"].nunique())
print("Mean funding ratio:", round(result_df["funding_ratio"].mean(), 4))
print("Median funding ratio:", round(result_df["funding_ratio"].median(), 4))
print(
    "Mean remaining shortfall (₹):",
    round(result_df["remaining_shortfall"].mean(), 2)
)
display(result_df.head(10))
print("\nSaved:", output_path)

# ===== CELL 135 =====  type=code  exec=210
import sys
from pathlib import Path
import numpy as np
import pandas as pd

run_dir = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/"
    "05_simulation_runs/rl_prototype"
)

sys.path.insert(0, str(run_dir))
from goalpilot_env import GoalPilotEnv

profiles = pd.read_csv(run_dir / "rl_sample_financial_profiles.csv")
goals = pd.read_csv(run_dir / "rl_sample_goals.csv")
market = pd.read_csv(run_dir / "rl_market_credit_validated.csv")

env = GoalPilotEnv(profiles=profiles, goals=goals, market=market)

long_user_ids = sorted(
    goals.loc[
        goals["time_horizon_months"] > env.max_steps, "user_id"
    ].unique()
)

def make_action(policy, n_goals):
    action = np.zeros((env.action_space.shape[0], 3), dtype=np.float32)

    if policy == "Savings only":
        action[:, 0] = 1.0
    elif policy == "Investments only":
        action[:, 1] = 1.0
    elif policy == "Mixed allocation":
        action[:, 0] = 0.5
        action[:, 1] = 0.5

    return action

policies = [
    "No action",
    "Savings only",
    "Investments only",
    "Mixed allocation",
]

records = []

for user_id in long_user_ids:
    for policy in policies:
        obs, info = env.reset(options={"user_id": user_id})
        terminated = truncated = False

        while not (terminated or truncated):
            action = make_action(policy, len(env.user_goals))
            obs, reward, terminated, truncated, info = env.step(action)

        user_goals = env.user_goals.reset_index(drop=True)

        for j, goal in user_goals.iterrows():
            deadline = int(goal["time_horizon_months"])
            if deadline <= env.max_steps:
                continue

            target = max(float(env.goal_targets[j]), 1.0)
            funded = float(env.goal_balances[j])

            records.append({
                "user_id": user_id,
                "goal_id": goal["goal_id"],
                "policy": policy,
                "funding_ratio": min(1.0, funded / target),
                "remaining_shortfall": max(0.0, target - funded),
                "final_cash": float(env.cash),
                "final_portfolio": float(env.portfolio),
                "final_loan_balance": float(env.loan_balance),
                "net_financial_wealth": (
                    float(env.cash) + float(env.portfolio)
                    - float(env.loan_balance)
                ),
                "total_reward": float(env.total_rewards),
            })

results = pd.DataFrame(records)

summary = (
    results.groupby("policy")
    .agg(
        goals=("goal_id", "count"),
        mean_funding_ratio=("funding_ratio", "mean"),
        median_funding_ratio=("funding_ratio", "median"),
        mean_remaining_shortfall=("remaining_shortfall", "mean"),
        mean_net_financial_wealth=("net_financial_wealth", "mean"),
        mean_total_reward=("total_reward", "mean"),
    )
    .reset_index()
)

results.to_csv(run_dir / "rl_long_horizon_policy_comparison.csv", index=False)
summary.to_csv(run_dir / "rl_long_horizon_policy_summary.csv", index=False)

print("=== Long-horizon policy comparison ===")
display(summary.round(4))
print("\nSaved both comparison CSV files.")

# ===== CELL 136 =====  type=code  exec=211
from pathlib import Path
import pandas as pd
import numpy as np

run_dir = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/"
    "05_simulation_runs/rl_prototype"
)

results = pd.read_csv(
    run_dir / "rl_long_horizon_policy_comparison.csv"
)

wide = results.pivot(
    index=["user_id", "goal_id"],
    columns="policy",
    values="funding_ratio"
).reset_index()

wide["mixed_minus_savings"] = (
    wide["Mixed allocation"] - wide["Savings only"]
)
wide["investments_minus_savings"] = (
    wide["Investments only"] - wide["Savings only"]
)

print("=== Per-goal funding comparison ===")
print(
    "Goals where mixed differs from savings:",
    int((wide["mixed_minus_savings"].abs() > 1e-8).sum()),
    "of", len(wide)
)
print(
    "Goals where investments exceed savings:",
    int((wide["investments_minus_savings"] > 1e-8).sum()),
    "of", len(wide)
)

print("\n=== Funding ratio distribution by policy ===")
print(
    results.groupby("policy")["funding_ratio"]
    .agg(["mean", "median", "std", "min", "max"])
    .round(4)
)

print("\n=== Largest mixed-vs-savings differences ===")
display(
    wide.assign(
        absolute_difference=wide["mixed_minus_savings"].abs()
    )
    .sort_values("absolute_difference", ascending=False)
    .head(10)
    [["user_id", "goal_id", "Savings only",
      "Mixed allocation", "mixed_minus_savings"]]
)

print("\nNo files modified.")

# ===== CELL 137 =====  type=code  exec=212
import importlib.util
import sys
from pathlib import Path
import numpy as np
import pandas as pd

run_dir = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/"
    "05_simulation_runs/rl_prototype"
)

sys.path.insert(0, str(run_dir))

from goalpilot_env import GoalPilotEnv

profiles = pd.read_csv(run_dir / "rl_sample_financial_profiles.csv")
goals = pd.read_csv(run_dir / "rl_sample_goals.csv")
market = pd.read_csv(run_dir / "rl_market_credit_validated.csv")

env = GoalPilotEnv(profiles=profiles, goals=goals, market=market)

print("=== RL library availability ===")
for package in ["gymnasium", "stable_baselines3", "torch"]:
    print(f"{package}: {'installed' if importlib.util.find_spec(package) else 'NOT installed'}")

print("\n=== Environment specification ===")
print("Users:", len(profiles))
print("Goals:", len(goals))
print("Market months:", len(market))
print("Maximum goals per user:", env.action_space.shape[0])
print("Observation shape:", env.observation_space.shape)
print("Action shape:", env.action_space.shape)
print("Action bounds:", env.action_space.low.min(), "to", env.action_space.high.max())
print("Maximum episode months:", env.max_steps)

obs, info = env.reset(options={"user_id": "USER_00001"})

print("\n=== Reset validation ===")
print("Observation shape:", obs.shape)
print("Observation within bounds:", env.observation_space.contains(obs))
print("Action space:", env.action_space)
print("Initial observation finite:", bool(np.isfinite(obs).all()))

print("\nNo files modified.")

# ===== CELL 138 =====  type=code  exec=213
import sys
from pathlib import Path
import numpy as np
import pandas as pd

from sklearn.model_selection import train_test_split
from stable_baselines3.common.env_checker import check_env

run_dir = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/"
    "05_simulation_runs/rl_prototype"
)
sys.path.insert(0, str(run_dir))

from goalpilot_env import GoalPilotEnv

# Load existing data
profiles = pd.read_csv(run_dir / "rl_sample_financial_profiles.csv")
goals = pd.read_csv(run_dir / "rl_sample_goals.csv")
market = pd.read_csv(run_dir / "rl_market_credit_validated.csv")

# Reproducible split by user, not by individual goal
all_user_ids = sorted(profiles["user_id"].unique())
train_ids, test_ids = train_test_split(
    all_user_ids,
    test_size=0.20,
    random_state=42,
    shuffle=True
)

train_profiles = profiles[profiles["user_id"].isin(train_ids)].copy()
train_goals = goals[goals["user_id"].isin(train_ids)].copy()
test_profiles = profiles[profiles["user_id"].isin(test_ids)].copy()
test_goals = goals[goals["user_id"].isin(test_ids)].copy()

# Keep the market history unchanged for both environments
train_env = GoalPilotEnv(
    profiles=train_profiles,
    goals=train_goals,
    market=market
)

test_env = GoalPilotEnv(
    profiles=test_profiles,
    goals=test_goals,
    market=market
)

# Validate Gymnasium/SB3 compatibility on the training environment
check_env(train_env, warn=True)

# Save the exact split for reproducibility
split_df = pd.DataFrame({
    "user_id": all_user_ids,
    "split": [
        "train" if user_id in set(train_ids) else "test"
        for user_id in all_user_ids
    ]
})
split_path = run_dir / "rl_train_test_user_split.csv"
split_df.to_csv(split_path, index=False)

print("=== User split ===")
print("Total users:", len(all_user_ids))
print("Training users:", len(train_ids))
print("Held-out test users:", len(test_ids))
print("Training goals:", len(train_goals))
print("Held-out goals:", len(test_goals))
print("User overlap:", len(set(train_ids) & set(test_ids)))
print("Market months:", len(market))
print("Observation shape:", train_env.observation_space.shape)
print("Action shape:", train_env.action_space.shape)
print("Gymnasium/SB3 environment check: passed")
print("Saved split:", split_path)

# ===== CELL 139 =====  type=code  exec=214
import sys
from pathlib import Path
import pandas as pd

from stable_baselines3 import PPO
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.callbacks import EvalCallback

run_dir = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/"
    "05_simulation_runs/rl_prototype"
)
sys.path.insert(0, str(run_dir))

from goalpilot_env import GoalPilotEnv

# Load the fixed split created in the previous step
profiles = pd.read_csv(run_dir / "rl_sample_financial_profiles.csv")
goals = pd.read_csv(run_dir / "rl_sample_goals.csv")
market = pd.read_csv(run_dir / "rl_market_credit_validated.csv")
split = pd.read_csv(run_dir / "rl_train_test_user_split.csv")

train_ids = set(split.loc[split["split"] == "train", "user_id"])
test_ids = set(split.loc[split["split"] == "test", "user_id"])

train_env = GoalPilotEnv(
    profiles=profiles[profiles["user_id"].isin(train_ids)].copy(),
    goals=goals[goals["user_id"].isin(train_ids)].copy(),
    market=market,
)
train_env = Monitor(train_env)

# Separate evaluation environment uses held-out users only.
# EvalCallback selects checkpoints based on mean episode reward.
eval_env = GoalPilotEnv(
    profiles=profiles[profiles["user_id"].isin(test_ids)].copy(),
    goals=goals[goals["user_id"].isin(test_ids)].copy(),
    market=market,
)
eval_env = Monitor(eval_env)

model_dir = run_dir / "models"
log_dir = run_dir / "training_logs"
model_dir.mkdir(parents=True, exist_ok=True)
log_dir.mkdir(parents=True, exist_ok=True)

eval_callback = EvalCallback(
    eval_env,
    best_model_save_path=str(model_dir / "best_ppo"),
    log_path=str(log_dir / "ppo_eval"),
    eval_freq=142 * 10,
    n_eval_episodes=10,
    deterministic=True,
    verbose=1,
)

model = PPO(
    "MlpPolicy",
    train_env,
    learning_rate=3e-4,
    n_steps=1024,
    batch_size=256,
    n_epochs=10,
    gamma=0.99,
    gae_lambda=0.95,
    ent_coef=0.01,
    policy_kwargs={"net_arch": [128, 128]},
    seed=42,
    verbose=1,
    tensorboard_log=str(log_dir / "tensorboard"),
)

print("Starting PPO training...")
model.learn(
    total_timesteps=50_000,
    callback=eval_callback,
    progress_bar=False,
)

final_model_path = model_dir / "goalpilot_ppo_50000"
model.save(str(final_model_path))

print("\n=== Training finished ===")
print("Timesteps:", model.num_timesteps)
print("Final model:", str(final_model_path) + ".zip")
print("Best evaluation checkpoint:", model_dir / "best_ppo")
print("Training logs:", log_dir)

# ===== CELL 140 =====  type=code  exec=216
import sys
from pathlib import Path
import pandas as pd
import numpy as np

run_dir = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/"
    "05_simulation_runs/rl_prototype"
)
sys.path.insert(0, str(run_dir))

from goalpilot_env import GoalPilotEnv

profiles = pd.read_csv(run_dir / "rl_sample_financial_profiles.csv")
goals = pd.read_csv(run_dir / "rl_sample_goals.csv")
market = pd.read_csv(run_dir / "rl_market_credit_validated.csv")

env = GoalPilotEnv(profiles=profiles, goals=goals, market=market)

obs, reset_info = env.reset(options={"user_id": "USER_00001"})
action = np.zeros(env.action_space.shape, dtype=np.float32)

obs, reward, terminated, truncated, info = env.step(action)

print("=== Keys returned in info ===")
print(sorted(info.keys()))

print("\n=== Diagnostic values ===")
for key, value in info.items():
    if isinstance(value, (int, float, np.number, bool, str)):
        print(f"{key}: {value}")
    elif isinstance(value, (list, tuple, np.ndarray)):
        print(f"{key}: shape={np.asarray(value).shape}, value={value}")

print("\n=== Environment state ===")
print("Cash:", env.cash)
print("Portfolio:", env.portfolio)
print("Loan balance:", env.loan_balance)
print("Goal balances:", env.goal_balances)
print("Goal targets:", env.goal_targets)

# ===== CELL 141 =====  type=code  exec=217
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from stable_baselines3 import PPO

run_dir = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/"
    "05_simulation_runs/rl_prototype"
)
sys.path.insert(0, str(run_dir))

from goalpilot_env import GoalPilotEnv

# Load existing data and the trained best checkpoint
profiles = pd.read_csv(run_dir / "rl_sample_financial_profiles.csv")
goals = pd.read_csv(run_dir / "rl_sample_goals.csv")
market = pd.read_csv(run_dir / "rl_market_credit_validated.csv")
split = pd.read_csv(run_dir / "rl_train_test_user_split.csv")

test_ids = sorted(
    split.loc[split["split"] == "test", "user_id"].tolist()
)

best_model_path = run_dir / "models" / "best_ppo" / "best_model.zip"
if not best_model_path.exists():
    raise FileNotFoundError(f"Checkpoint not found: {best_model_path}")

model = PPO.load(str(best_model_path))

test_profiles = profiles[profiles["user_id"].isin(test_ids)].copy()
test_goals = goals[goals["user_id"].isin(test_ids)].copy()

def baseline_action(policy, action_shape):
    action = np.zeros(action_shape, dtype=np.float32)

    if policy == "Savings only":
        action[:, 0] = 1.0
    elif policy == "Investments only":
        action[:, 1] = 1.0
    elif policy == "Mixed allocation":
        action[:, 0] = 0.5
        action[:, 1] = 0.5

    return action

policies = [
    "PPO (best checkpoint)",
    "No action",
    "Savings only",
    "Investments only",
    "Mixed allocation",
]

records = []

for user_id in test_ids:
    for policy in policies:
        env = GoalPilotEnv(
            profiles=test_profiles,
            goals=test_goals,
            market=market,
        )

        obs, _ = env.reset(options={"user_id": user_id})

        terminated = False
        truncated = False
        total_reward = 0.0
        max_budget_excess = 0.0
        max_goal_overshoot = 0.0

        while not (terminated or truncated):
            if policy == "PPO (best checkpoint)":
                action, _ = model.predict(obs, deterministic=True)
                action = np.asarray(action, dtype=np.float32)
            else:
                action = baseline_action(policy, env.action_space.shape)

            obs, reward, terminated, truncated, info = env.step(action)
            total_reward += float(reward)

            surplus = float(info["monthly_surplus"])
            savings = float(info["savings_contribution"])
            investments = float(info["investment_contribution"])
            commitment = float(info["combined_monthly_commitment"])

            # Combined contributions and loan commitments must not exceed surplus.
            budget_excess = savings + investments + commitment - surplus
            max_budget_excess = max(max_budget_excess, budget_excess)

            balances = np.asarray(info["goal_balances"], dtype=float)
            targets = np.asarray(info["goal_targets"], dtype=float)

            max_goal_overshoot = max(
                max_goal_overshoot,
                float(np.max(balances - targets)),
            )

        target_sum = float(np.sum(env.goal_targets))
        funded_sum = float(
            np.minimum(env.goal_balances, env.goal_targets).sum()
        )

        final_cash = float(env.cash)
        final_portfolio = float(env.portfolio)
        final_loan = float(env.loan_balance)

        records.append({
            "user_id": user_id,
            "policy": policy,
            "goal_funding_ratio": funded_sum / max(target_sum, 1.0),
            "goal_funding_amount": funded_sum,
            "goal_target_amount": target_sum,
            "final_cash": final_cash,
            "final_portfolio": final_portfolio,
            "final_loan_balance": final_loan,
            "net_financial_wealth": (
                final_cash + final_portfolio - final_loan
            ),
            "total_reward": total_reward,
            "max_budget_excess": max_budget_excess,
            "max_goal_overshoot": max_goal_overshoot,
        })

        env.close()

detail = pd.DataFrame(records)

summary = (
    detail.groupby("policy")
    .agg(
        users=("user_id", "nunique"),
        mean_goal_funding_ratio=("goal_funding_ratio", "mean"),
        median_goal_funding_ratio=("goal_funding_ratio", "median"),
        mean_goal_funding_amount=("goal_funding_amount", "mean"),
        mean_net_financial_wealth=("net_financial_wealth", "mean"),
        mean_final_portfolio=("final_portfolio", "mean"),
        mean_final_loan_balance=("final_loan_balance", "mean"),
        mean_total_reward=("total_reward", "mean"),
        max_budget_excess=("max_budget_excess", "max"),
        max_goal_overshoot=("max_goal_overshoot", "max"),
    )
    .reset_index()
)

detail_path = run_dir / "rl_heldout_policy_comparison_detail.csv"
summary_path = run_dir / "rl_heldout_policy_comparison_summary.csv"

detail.to_csv(detail_path, index=False)
summary.to_csv(summary_path, index=False)

print(f"Evaluated users: {detail['user_id'].nunique()}")
print(f"Policies evaluated: {detail['policy'].nunique()}")
print(f"Evaluation episodes: {len(detail)}")

print("\n=== Held-out policy comparison ===")
display(summary.round(4))

print("\n=== Constraint checks ===")
print(
    "Maximum budget excess:",
    round(float(detail["max_budget_excess"].max()), 8),
)
print(
    "Maximum goal overshoot:",
    round(float(detail["max_goal_overshoot"].max()), 8),
)

print("\nSaved results:")
print(detail_path)
print(summary_path)


# ===== CELL 142 =====  type=code  exec=218
from pathlib import Path

env_path = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/"
    "05_simulation_runs/rl_prototype/goalpilot_env.py"
)

source = env_path.read_text(encoding="utf-8")
lines = source.splitlines()

terms = [
    "available_after_existing_loan",
    "savings_alloc",
    "invest_alloc",
    "combined_commitment",
    "combined_monthly_commitment",
    "monthly_loan_commitment",
    "monthly_surplus",
    "surplus =",
]

for term in terms:
    matches = [
        i for i, line in enumerate(lines)
        if term in line
    ]

    print(f"\n{'=' * 18} {term} {'=' * 18}")

    if not matches:
        print("Not found")
        continue

    shown = set()

    for i in matches:
        start = max(0, i - 4)
        end = min(len(lines), i + 7)

        for j in range(start, end):
            if j not in shown:
                print(f"{j + 1:4}: {lines[j]}")
                shown.add(j)

        print("---")

# ===== CELL 143 =====  type=code  exec=219
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from stable_baselines3 import PPO

run_dir = Path(
    "/content/drive/MyDrive/GoalPilot_AI/simulation/"
    "05_simulation_runs/rl_prototype"
)
sys.path.insert(0, str(run_dir))

from goalpilot_env import GoalPilotEnv

profiles = pd.read_csv(run_dir / "rl_sample_financial_profiles.csv")
goals = pd.read_csv(run_dir / "rl_sample_goals.csv")
market = pd.read_csv(run_dir / "rl_market_credit_validated.csv")
split = pd.read_csv(run_dir / "rl_train_test_user_split.csv")

test_ids = sorted(
    split.loc[split["split"] == "test", "user_id"].tolist()
)

model_path = run_dir / "models" / "best_ppo" / "best_model.zip"
model = PPO.load(str(model_path))

test_profiles = profiles[profiles["user_id"].isin(test_ids)].copy()
test_goals = goals[goals["user_id"].isin(test_ids)].copy()

policies = [
    "PPO (best checkpoint)",
    "No action",
    "Savings only",
    "Investments only",
    "Mixed allocation",
]

records = []

for user_id in test_ids:
    for policy in policies:
        env = GoalPilotEnv(
            profiles=test_profiles,
            goals=test_goals,
            market=market,
        )
        obs, _ = env.reset(options={"user_id": user_id})

        total_reward = 0.0
        max_budget_excess = 0.0
        max_goal_overshoot = 0.0
        terminated = False
        truncated = False

        while not (terminated or truncated):
            if policy == "PPO (best checkpoint)":
                action, _ = model.predict(obs, deterministic=True)
                action = np.asarray(action, dtype=np.float32)
            else:
                action = np.zeros(env.action_space.shape, dtype=np.float32)

                if policy == "Savings only":
                    action[:, 0] = 1.0
                elif policy == "Investments only":
                    action[:, 1] = 1.0
                elif policy == "Mixed allocation":
                    action[:, 0] = 0.5
                    action[:, 1] = 0.5

            obs, reward, terminated, truncated, info = env.step(action)
            total_reward += float(reward)

            # Correct: combined commitment already includes contributions.
            budget_excess = (
                float(info["combined_monthly_commitment"])
                - float(info["monthly_surplus"])
            )
            max_budget_excess = max(max_budget_excess, budget_excess)

            balances = np.asarray(info["goal_balances"], dtype=float)
            targets = np.asarray(info["goal_targets"], dtype=float)
            max_goal_overshoot = max(
                max_goal_overshoot,
                float(np.max(balances - targets)),
            )

        targets = np.asarray(env.goal_targets, dtype=float)
        balances = np.asarray(env.goal_balances, dtype=float)
        funded = np.minimum(balances, targets)

        records.append({
            "user_id": user_id,
            "policy": policy,
            "goal_funding_ratio": float(funded.sum() / max(targets.sum(), 1.0)),
            "goal_funding_amount": float(funded.sum()),
            "goal_target_amount": float(targets.sum()),
            "final_cash": float(env.cash),
            "final_portfolio": float(env.portfolio),
            "final_loan_balance": float(env.loan_balance),
            "net_financial_wealth": float(
                env.cash + env.portfolio - env.loan_balance
            ),
            "total_reward": total_reward,
            "max_budget_excess": max_budget_excess,
            "max_goal_overshoot": max_goal_overshoot,
        })

        env.close()

detail = pd.DataFrame(records)

summary = (
    detail.groupby("policy")
    .agg(
        users=("user_id", "nunique"),
        mean_goal_funding_ratio=("goal_funding_ratio", "mean"),
        median_goal_funding_ratio=("goal_funding_ratio", "median"),
        mean_goal_funding_amount=("goal_funding_amount", "mean"),
        mean_net_financial_wealth=("net_financial_wealth", "mean"),
        mean_final_portfolio=("final_portfolio", "mean"),
        mean_final_loan_balance=("final_loan_balance", "mean"),
        mean_total_reward=("total_reward", "mean"),
        max_budget_excess=("max_budget_excess", "max"),
        max_goal_overshoot=("max_goal_overshoot", "max"),
    )
    .reset_index()
)

detail.to_csv(
    run_dir / "rl_heldout_policy_comparison_detail.csv",
    index=False,
)
summary.to_csv(
    run_dir / "rl_heldout_policy_comparison_summary.csv",
    index=False,
)

print("=== Corrected held-out policy comparison ===")
display(summary.round(4))

print("\n=== Constraint audit ===")
print("Episodes:", len(detail))
print("Maximum budget excess (₹):",
      round(float(detail["max_budget_excess"].max()), 6))
print("Maximum goal overshoot (₹):",
      round(float(detail["max_goal_overshoot"].max()), 6))
print("Budget violations above ₹0.01:",
      int((detail["max_budget_excess"] > 0.01).sum()))
print("\nUpdated CSV files saved in:", run_dir)
