"""Smoke-test the multi-goal LP against one real row from the supplied simulation archive.

The financial profile comes from the simulation output; goals remain explicitly synthetic
because the supplied simulation contains only one goal record per user.
"""
from pathlib import Path
import argparse, zipfile, json, sys
import pandas as pd
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from multi_goal_optimizer import optimize_multi_goal
from simulation_adapter import financial_state_from_simulation_row

p = argparse.ArgumentParser()
p.add_argument('--simulation-zip', required=True, help='Path to simulation-...zip')
p.add_argument('--user-id', default=None, help='Optional simulation user_id; defaults to first row')
p.add_argument('--output-dir', default=str(ROOT / 'outputs'))
a = p.parse_args()
member = 'simulation/06_results/final_optimisation_input.csv'
with zipfile.ZipFile(a.simulation_zip) as z:
    df = pd.read_csv(z.open(member))
if a.user_id:
    match = df.loc[df.user_id.astype(str) == str(a.user_id)]
    if match.empty:
        raise SystemExit(f'user_id not found: {a.user_id}')
    row = match.iloc[0]
else:
    row = df.iloc[0]
user_id, state = financial_state_from_simulation_row(row)
goals = pd.read_csv(ROOT / 'data' / 'sample_goals.csv')
result = optimize_multi_goal(goals, state)
out = Path(a.output_dir); out.mkdir(parents=True, exist_ok=True)
if result['status'] != 'optimal':
    raise SystemExit(f"Solver did not return optimal: {result.get('solver_message')}")
result['allocations'].to_csv(out / 'simulation_integration_smoke_allocations.csv', index=False)
summary = dict(result['summary'])
summary.update({
    'integration_test': 'simulation_financial_profile_plus_synthetic_three_goals',
    'simulation_user_id': user_id,
    'goal_data_status': 'synthetic demonstration goals; not user-reported goals',
    'risk_capacity_mapping': 'risk_profile conservative=0.25, moderate=0.50, aggressive=0.75; configurable proxy',
    'limitations': [
        'one financial profile row only; not a full 10,000-user rerun',
        'simulation provides one legacy goal per user, not genuine multi-goal records',
        'existing investments are mapped but not allocated by the current LP',
        'goal target dates, priorities, criticalities and current goal-specific funding require actual inputs'
    ]
})
(out / 'simulation_integration_smoke_summary.json').write_text(json.dumps(summary, indent=2, default=lambda x: x.item() if hasattr(x, 'item') else str(x)))
print(json.dumps(summary, indent=2, default=lambda x: x.item() if hasattr(x, 'item') else str(x)))
print('Wrote:', out / 'simulation_integration_smoke_allocations.csv')
print('Wrote:', out / 'simulation_integration_smoke_summary.json')
