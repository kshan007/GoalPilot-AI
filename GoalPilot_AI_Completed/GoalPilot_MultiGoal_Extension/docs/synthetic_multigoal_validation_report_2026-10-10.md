# Synthetic Multi-Goal Dataset and LP Validation

## Dataset created
- Financial profiles: 10,000 rows copied from the supplied GoalPilot simulation input.
- Multi-goal records: 39,932 rows across 10,000 users.
- Goals per user: 3–5; mean 3.9932.
- Goal records retained from the legacy single-goal simulation: 10,000.
- Additional generated goal records: 29,932.
- Random seed: `20261010`.
- Reference date used to generate target dates: `2026-10-10`.

## What is synthetic
The original simulation already contains one simulated goal per user. The additional goals, types, costs, deadlines, priorities, criticalities, and earmarked funding values are generated assumptions. They are not collected from real people and must not be represented as user-reported facts.

Eight additional goal types are available: emergency buffer, education/upskilling, vehicle purchase, home down payment, family event, travel fund, retirement corpus milestone, and business/career transition. Each user receives two to four extra types without replacement. Costs are based on monthly income times a type-specific factor and a clipped lognormal multiplier. Priorities and criticalities are sampled from type-specific integer ranges. Existing funding is synthetic and capped by a small percentage of liquid savings and goal cost.

## LP validation run
- Scope: first 1,000 users in source row order, not all 10,000 users.
- LP solves with optimal status: 1,000 / 1,000.
- Failures: 0.
- Allocation rows written: 4,031.
- Goal rows fully funded in the model: 2,691.
- Goal rows with positive shortfall: 1,340.
- Users for whom every generated goal was fully funded: 465 / 1,000.
- Mean weighted goal achievement: 0.8268.
- Median weighted goal achievement: 0.9653.
- Mean sum of goal shortfalls per user: 3,568,137.67 currency units.
- All allocation constraints (monthly contribution, EMI cap, and cash above reserve) respected in this sample: yes.

These figures are exploratory model outputs conditional on the synthetic goals and prototype assumptions. Weighted achievement is not a probability of success. The very large mean shortfall is affected by long-horizon/high-cost synthetic goals, including retirement milestones, and should be interpreted as a stress test of resource scarcity rather than a population estimate.

## Emergency fund reporting clarification
The LP cannot spend liquid savings below the emergency reserve target. If the starting savings balance is already below the target, the model can preserve that balance but cannot make the reserve target true without a separate reserve-building decision variable. In the 1,000-user sample, 173 users started below their emergency reserve target; 827 had the target met after the allocation.

## Files
- `data/synthetic_multigoal_input.csv`: all 39,932 goal records.
- `data/multigoal_financial_profiles.csv`: 10,000 financial profile rows.
- `outputs/synthetic_multigoal_dataset_summary.json`: dataset counts and assumptions.
- `outputs/synthetic_multigoal_optimization_allocations_sample1000.csv`: goal-level LP allocations for sample.
- `outputs/synthetic_multigoal_optimization_user_summary_sample1000.csv`: user-level summary for sample.
- `outputs/synthetic_multigoal_optimization_summary_sample1000.json`: aggregate sample results.
- `generate_multigoal_dataset.py`: reproducible generator and optimizer runner.

## Reproduce
```bash
python -m pip install pandas numpy scipy pytest
python generate_multigoal_dataset.py --generate-only
python generate_multigoal_dataset.py --max-users 1000
python -m pytest -q
```
To test more users, increase `--max-users`; a full 10,000-user LP run is not claimed by this validation report.
