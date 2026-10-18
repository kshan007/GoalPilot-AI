from pathlib import Path
import json
import pandas as pd
from src.multi_goal_optimizer import FinancialState, optimize_multi_goal, strategy_comparison
BASE=Path(__file__).resolve().parent
state_data=json.loads((BASE/'data/sample_financial_state.json').read_text())
state=FinancialState(**{k:v for k,v in state_data.items() if k!='user_id' and k!='source_note'})
goals=pd.read_csv(BASE/'data/sample_goals.csv')
kwargs=dict(annual_inflation=0.03,savings_return=0.0,investment_return=0.05,investment_risk_score=0.4,loan_annual_rate=0.12,loan_tenure_months=60,max_loan_per_goal=150000)
result=optimize_multi_goal(goals,state,**kwargs)
out=BASE/'outputs'; out.mkdir(exist_ok=True)
result['goals'].to_csv(out/'derived_goals.csv',index=False)
result['allocations'].to_csv(out/'multi_goal_allocations.csv',index=False)
(out/'optimization_summary.json').write_text(json.dumps({'status':result['status'],'solver_message':result.get('solver_message'),'summary':result.get('summary',{}),'constraints':result.get('constraints',{})},indent=2,default=lambda x: x.item() if hasattr(x,'item') else str(x)))
comparison=strategy_comparison(goals,state,**kwargs)
comparison.to_csv(out/'strategy_comparison.csv',index=False)
scenario_rows=[]
for scenario, changes in [("Baseline",{}),("Higher inflation",{"annual_inflation":0.06}),("Lower market returns",{"investment_return":0.01}),("Higher loan rate",{"loan_annual_rate":0.16})]:
    scenario_kwargs={**kwargs,**changes}
    sr=optimize_multi_goal(goals,state,**scenario_kwargs)
    sm=sr.get('summary',{})
    scenario_rows.append({"scenario":scenario,"status":sr['status'],"total_funding_gap":sm.get('total_funding_gap'),"weighted_goal_achievement":sm.get('weighted_goal_achievement'),"total_shortfall":sm.get('total_shortfall'),"monthly_contributions":sm.get('monthly_contributions_allocated'),"loan_cost":sm.get('loan_cost_total')})
pd.DataFrame(scenario_rows).to_csv(out/'economic_scenario_comparison.csv',index=False)
print('Status:',result['status'])
print(json.dumps(result.get('summary',{}),indent=2,default=lambda x: x.item() if hasattr(x,'item') else str(x)))
print('\nAllocations:\n',result['allocations'].to_string(index=False))
print('\nStrategies:\n',comparison.to_string(index=False))
