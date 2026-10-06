# GoalPilot Application - Optimization Integration Notes

This document provides technical integration specifications for coupling the user-facing web application with the existing GoalPilot AI simulation and optimization engines.

---

## 1. Integration Layer Architecture

To preserve `GoalPilot_AI/` as an untouched source of truth, an adapter architecture is implemented within `GoalPilot_Application/backend/app/integration/`:

```
FastAPI Router (/api/optimize)
          │
          ▼
   OptimizationService
          │
          ▼
   SingleGoalOptimizationAdapter ◄─── (Implements DecisionEngineInterface)
   ┌──────┴─────────────────────────────────┐
   │                                        │
   ▼                                        ▼
SimulationAdapter                      LPOptimizer
(Loads economic inflation path         (Constructs & solves linprog
 & evolves dynamic cash flows)          Highs LP per Step 5T)
```

---

## 2. Decision Engine Interface (Future Extensibility)

```python
from abc import ABC, abstractmethod
from typing import Dict, Any

class DecisionEngineInterface(ABC):
    """
    Abstract interface for financial decision engines.
    Allows seamless future substitution with Multi-Goal LP or RL Decision Engines.
    """
    @abstractmethod
    def optimize_goal(self, profile_data: Dict[str, Any], goal_data: Dict[str, Any]) -> Dict[str, Any]:
        pass
```

The current implementation is `SingleGoalOptimizationAdapter(DecisionEngineInterface)`.

---

## 3. Mathematical LP Formulation Details

The optimization follows the exact mathematically validated formulation from **Step 5T** of `GoalPilot_Optimization (2).ipynb`:

```python
from scipy.optimize import linprog
import numpy as np

def solve_single_goal_lp(horizon: int, target_amount: float, positive_cash_flows: np.ndarray):
    """
    Solves:
        min D
        s.t. sum(G_t) + D = target_amount
             0 <= G_t <= positive_cash_flows[t]
             D >= 0
    """
    # Decision vector: [G_1, G_2, ..., G_H, D]
    c = np.zeros(horizon + 1)
    c[-1] = 1.0  # minimize D

    # Bounds: (0, P_t) for G_t, (0, None) for D
    bounds = [(0.0, float(p)) for p in positive_cash_flows]
    bounds.append((0.0, None))

    # Equality constraint: sum(G_t) + D = target_amount
    A_eq = np.zeros((1, horizon + 1))
    A_eq[0, :horizon] = 1.0
    A_eq[0, horizon] = 1.0
    b_eq = np.array([float(target_amount)])

    # Highs solver call
    solution = linprog(
        c=c,
        A_eq=A_eq,
        b_eq=b_eq,
        bounds=bounds,
        method="highs"
    )

    return solution
```

---

## 4. Analytical Equivalence and Invariant Checks

For every optimization run, the adapter validates:
1. **Analytical Funding Identity**:
   $$\text{Expected Funding} = \min\left(\text{Target}, \sum_{t=1}^H P_t\right)$$
2. **Analytical Shortfall Identity**:
   $$\text{Expected Shortfall} = \max\left(\text{Target} - \sum_{t=1}^H P_t, 0\right)$$
3. **Optimality Residual Check**:
   $$|\text{Optimized Funding} - \text{Expected Funding}| \le 10^{-6}$$
   $$|\text{Optimized Shortfall} - \text{Expected Shortfall}| \le 10^{-6}$$
4. **Feasibility Residual Check**:
   $$|\text{Optimized Funding} + D^* - \text{Target}| \le 10^{-6}$$
   $$0 \le G_t^* \le P_t + 10^{-6} \quad \forall t$$

---

## 5. Handling Infeasible & Deficit Conditions

- If a user has negative surplus ($\sum P_t = 0$), the LP naturally sets $G_t^* = 0$ and $D^* = \text{Target}$.
- The application reports status `"unfunded_deficit"` or `"deficit_infeasible"` with explicit, constructive financial feedback.
- If the solver fails numerical convergence (rare), the application returns a structured error without crashing or exposing raw stack traces.
