"""Generate reproducible synthetic multi-goal inputs from GoalPilot's 10k simulated profiles.
All added goals and priorities are synthetic assumptions, not user-reported data.
"""
from pathlib import Path
import json, sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
OUT = ROOT / 'outputs'
SEED = 20261010

sys.path.insert(0, str(ROOT / 'src'))
from simulation_adapter import financial_state_from_simulation_row
from multi_goal_optimizer import optimize_multi_goal

GOAL_TYPES = [
    # type, display name, cost as multiple of monthly income, horizon range, priority range, criticality range
    ('emergency_buffer', 'Emergency buffer', 1.5, 6, 18, 5, 5, 5, 5),
    ('education', 'Education / upskilling', 2.0, 6, 48, 3, 5, 3, 5),
    ('vehicle', 'Vehicle purchase', 5.0, 12, 60, 2, 5, 2, 4),
    ('home_deposit', 'Home down payment', 24.0, 36, 180, 3, 5, 4, 5),
    ('wedding', 'Family event', 8.0, 12, 72, 2, 5, 2, 4),
    ('travel', 'Travel fund', 1.5, 6, 36, 1, 3, 1, 2),
    ('retirement', 'Retirement corpus milestone', 60.0, 60, 240, 3, 5, 4, 5),
    ('business', 'Business / career transition', 12.0, 24, 120, 2, 5, 3, 5),
]

def generate():
    rng = np.random.default_rng(SEED)
    profiles = pd.read_csv(DATA / 'final_optimisation_input.csv')
    rows=[]
    for _, p in profiles.iterrows():
        uid = str(p['user_id'])
        income = max(float(p['final_monthly_income']), 1.0)
        savings = max(float(p['final_savings_balance']), 0.0)
        # Keep one legacy simulated goal for continuity with the original dataset.
        months = max(1, int(p['goal_horizon_months']))
        rows.append({
            'user_id': uid, 'goal_id': f'{uid}_LEGACY', 'goal_name': 'Legacy simulated goal',
            'goal_type': 'legacy_simulated_goal', 'current_cost': max(float(p['target_amount']), 0.0),
            'target_date': (pd.Timestamp('2026-10-10') + pd.DateOffset(months=months)).strftime('%Y-%m-%d'),
            'time_horizon_months': months, 'priority': 3.0, 'criticality': 3.0,
            'existing_funding': 0.0, 'goal_data_origin': 'existing_single_goal_simulation',
            'synthetic_assumption_version': 'v1_seed_20261010'
        })
        # Each user receives 2-4 additional goals, selected without replacement.
        n_extra = int(rng.integers(2, 5))
        chosen = rng.choice(len(GOAL_TYPES), size=n_extra, replace=False)
        for idx in chosen:
            (gtype, name, income_multiple, lo, hi, plo, phi, clo, chi) = GOAL_TYPES[int(idx)]
            horizon = int(rng.integers(lo, hi + 1))
            # Lognormal multiplier creates moderate variation without unbounded outliers.
            variation = float(np.clip(rng.lognormal(mean=0.0, sigma=0.25), 0.55, 1.8))
            cost = income * income_multiple * variation
            # Existing goal funding is a synthetic earmark, capped by both the goal cost
            # and a small portion of liquid savings so it is not implicitly unlimited.
            earmark_budget = savings * float(rng.uniform(0.0, 0.04))
            existing = min(cost * float(rng.uniform(0.0, 0.12)), earmark_budget)
            rows.append({
                'user_id': uid, 'goal_id': f'{uid}_{gtype.upper()}', 'goal_name': name,
                'goal_type': gtype, 'current_cost': round(cost, 2),
                'target_date': (pd.Timestamp('2026-10-10') + pd.DateOffset(months=horizon)).strftime('%Y-%m-%d'),
                'time_horizon_months': horizon,
                'priority': int(rng.integers(plo, phi + 1)),
                'criticality': int(rng.integers(clo, chi + 1)),
                'existing_funding': round(existing, 2),
                'goal_data_origin': 'synthetic_generated_goal',
                'synthetic_assumption_version': 'v1_seed_20261010'
            })
    goals = pd.DataFrame(rows)
    # Financial profiles are included separately, not repeated in every goal row.
    profiles.to_csv(DATA / 'multigoal_financial_profiles.csv', index=False)
    goals.to_csv(DATA / 'synthetic_multigoal_input.csv', index=False)
    counts = goals.groupby('user_id').size()
    summary = {
        'dataset_type': 'synthetic multi-goal input derived from existing synthetic GoalPilot financial profiles',
        'random_seed': SEED,
        'reference_date_for_generated_deadlines': '2026-10-10',
        'users': int(profiles.user_id.nunique()),
        'goals': int(len(goals)),
        'goals_per_user_min': int(counts.min()), 'goals_per_user_max': int(counts.max()),
        'goals_per_user_mean': float(counts.mean()),
        'legacy_goal_rows': int((goals.goal_data_origin == 'existing_single_goal_simulation').sum()),
        'synthetic_goal_rows': int((goals.goal_data_origin == 'synthetic_generated_goal').sum()),
        'goal_types': {str(k): int(v) for k,v in goals.goal_type.value_counts().items()},
        'assumptions': [
            'each user retains the existing single simulated goal',
            'each user receives 2-4 extra goals sampled without replacement from 8 goal types',
            'goal costs are based on monthly income multiplied by type-specific factors and a clipped lognormal variation',
            'priorities and criticalities are generated integers within type-specific ranges',
            'generated earmarked funding is capped at 4% of reported liquid savings per goal and 12% of goal cost',
            'deadlines are relative to 2026-10-10; this is a synthetic reference date, not a live user deadline',
            'all new goals, their costs, dates, priorities, criticalities, and earmarks are synthetic; do not treat as user facts'
        ]
    }
    (OUT / 'synthetic_multigoal_dataset_summary.json').write_text(json.dumps(summary, indent=2))
    return profiles, goals, summary

def run_optimization(profiles, goals, max_users=1000):
    profiles = profiles.head(max_users).copy()
    allocs=[]; summaries=[]; failures=[]
    grouped = {uid: g.drop(columns=['user_id','goal_type','goal_data_origin','synthetic_assumption_version'])
               for uid,g in goals.groupby('user_id', sort=False)}
    provenance = {uid: {str(r.goal_id): (r.goal_type, r.goal_data_origin)
                        for r in g[['goal_id','goal_type','goal_data_origin']].itertuples(index=False)}
                  for uid,g in goals.groupby('user_id', sort=False)}
    for i, (_, p) in enumerate(profiles.iterrows(), start=1):
        try:
            uid, state = financial_state_from_simulation_row(p)
            g = grouped[uid]
            res = optimize_multi_goal(g, state)
            if res['status'] != 'optimal':
                failures.append({'user_id':uid, 'status':res['status'], 'message':res.get('solver_message','')})
                continue
            a=res['allocations'].copy(); a.insert(0,'user_id',uid)
            # Attach generated/legacy provenance to every allocation row.
            prov=provenance[uid]
            a['goal_type'] = a['goal_id'].astype(str).map(lambda x: prov[x][0])
            a['goal_data_origin'] = a['goal_id'].astype(str).map(lambda x: prov[x][1])
            allocs.append(a)
            s=dict(res['summary']); s['user_id']=uid; s['goals_with_shortfall']=int((res['allocations'].shortfall > 0.01).sum())
            s['all_goals_fully_funded']=bool((res['allocations'].shortfall <= 0.01).all())
            summaries.append(s)
        except Exception as e:
            failures.append({'user_id':str(p.get('user_id','unknown')), 'status':'exception', 'message':repr(e)})
        if i % 100 == 0:
            print(f'Processed {i:,}/{len(profiles):,} users; solved={len(summaries):,}; failures={len(failures):,}', flush=True)
    allocation_df = pd.concat(allocs, ignore_index=True) if allocs else pd.DataFrame()
    summary_df = pd.DataFrame(summaries)
    suffix = f'sample{len(profiles)}'
    allocation_df.to_csv(OUT / f'synthetic_multigoal_optimization_allocations_{suffix}.csv', index=False)
    summary_df.to_csv(OUT / f'synthetic_multigoal_optimization_user_summary_{suffix}.csv', index=False)
    pd.DataFrame(failures).to_csv(OUT / f'synthetic_multigoal_optimization_failures_{suffix}.csv', index=False)
    result = {
        'users_attempted': int(len(profiles)), 'users_solved_optimal': int(len(summary_df)),
        'users_failed': int(len(failures)), 'goal_allocations_written': int(len(allocation_df)),
        'goal_rows_with_shortfall': int((allocation_df.shortfall > 0.01).sum()) if len(allocation_df) else None,
        'goal_rows_fully_funded': int((allocation_df.shortfall <= 0.01).sum()) if len(allocation_df) else None,
        'users_all_goals_fully_funded': int(summary_df.all_goals_fully_funded.sum()) if len(summary_df) else None,
        'mean_weighted_goal_achievement': float(summary_df.weighted_goal_achievement.mean()) if len(summary_df) else None,
        'median_weighted_goal_achievement': float(summary_df.weighted_goal_achievement.median()) if len(summary_df) else None,
        'mean_total_shortfall_in_currency_units': float(summary_df.total_shortfall.mean()) if len(summary_df) else None,
        'total_monthly_contributions_allocated': float(summary_df.monthly_contributions_allocated.sum()) if len(summary_df) else None,
        'total_new_emi_monthly': float(summary_df.new_total_emi.sum()) if len(summary_df) else None,
        'all_allocation_constraints_respected': bool(summary_df.monthly_surplus_respected.all() and summary_df.emi_cap_respected.all() and summary_df.emergency_fund_preserved.all()) if len(summary_df) else False,
        'users_whose_starting_savings_were_below_emergency_target': int(summary_df.emergency_fund_was_below_target_at_start.sum()) if len(summary_df) else None,
        'users_whose_emergency_target_was_met_after_allocation': int(summary_df.emergency_fund_target_met_after_allocation.sum()) if len(summary_df) else None,
        'note': 'Optimization outcomes are conditional on synthetic generated goals and prototype assumptions; weighted achievement is not a probability of success.'
    }
    (OUT / f'synthetic_multigoal_optimization_summary_{suffix}.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return result

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Generate the full synthetic multi-goal dataset and optionally optimize a sample of users.')
    parser.add_argument('--max-users', type=int, default=1000, help='Number of users to optimize (default: 1000; dataset generation always covers all users).')
    parser.add_argument('--generate-only', action='store_true', help='Generate datasets but skip optimization.')
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    profiles, goals, summary = generate()
    print(json.dumps({k:summary[k] for k in ['users','goals','goals_per_user_min','goals_per_user_max','goals_per_user_mean','synthetic_goal_rows']}, indent=2))
    if not args.generate_only:
        run_optimization(profiles, goals, max_users=max(1, min(args.max_users, len(profiles))))
