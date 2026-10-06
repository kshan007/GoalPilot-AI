# GoalPilot Application

> **Intelligent Single-Goal Financial Optimization & Longitudinal Planning Platform**  
> Educational prototype exposing the core research findings and Linear Programming optimization engine of the GoalPilot AI project.

---

## 1. Overview

**GoalPilot Application** is a full-stack financial decision-support tool built to interface with the **GoalPilot AI** research framework. It provides an intuitive, high-grade fintech user interface on top of the mathematically validated **Single-Goal Linear Programming Optimization Engine**.

### Core Value Proposition
- Translates personal financial profiles and single-goal targets into dynamic macroeconomic trajectories.
- Solves for the optimal monthly goal funding schedule using the empirical CPI-calibrated simulation model.
- Strictly minimizes goal shortfall subject to monthly available cash-flow constraints.
- Provides deep explainability, constraint diagnostics, and NISM investor-education guidance.

---

## 2. Current vs. Future Capabilities

### Current Version (v1.0.0)
- **Single Financial Goal Optimization**: Formulates and solves a discrete monthly Linear Program for exactly one financial target over a horizon of up to 144 months.
- **Empirical Macroeconomic Simulation**: Dynamically adjusts income and essential living expenditures using calibrated Indian CPI inflation schedules.
- **Decision Engine Interface**: Modular architecture decoupling user inputs, simulation layers, and solver engines.
- **Benchmark Research Parity**: Includes direct validation tools to replicate results from the 10,000-user synthetic dataset.

### Future Extensibility
- **Multiple Financial Goals**: Concurrent goal scheduling, cross-goal trade-offs, and multi-objective Pareto frontiers.
- **Reinforcement Learning (RL)**: Closed-loop sequential decision-making adapting to real-time market shocks and cash-flow surprises.
- **Dynamic Portfolio Optimization**: Active asset allocation rebalancing across equity, debt, and cash instruments.

---

## 3. Architecture

```
Parent/
├── GoalPilot_AI/                        # Research & modeling source of truth (Read-Only)
│   ├── simulation/                      # Macroeconomic calibrations & longitudinal runs
│   └── optimization/                    # Master LP datasets & summaries
│
└── GoalPilot_Application/               # User-Facing Full-Stack Product
    ├── backend/                         # FastAPI, Pydantic, Scipy HiGHS Engine
    │   ├── app/
    │   │   ├── api/                     # Health, Optimization, and Benchmark endpoints
    │   │   ├── schemas/                 # Pydantic v2 data contracts
    │   │   ├── services/                # Orchestration logic
    │   │   └── integration/             # GoalPilot AI Simulation & LP Adapters
    │   └── tests/                       # 15+ comprehensive unit & validation tests
    └── frontend/                        # Modern Fintech Web Application (Vite + React)
```

---

## 4. Setup & Running Locally

### Prerequisites
- Python 3.10+ (Python 3.11 / 3.12 / 3.13 supported)
- Node.js 18+ and npm

### Backend Setup
```bash
cd GoalPilot_Application/backend

# Install dependencies
pip install -r requirements.txt

# Run test suite
pytest tests/ -v

# Start FastAPI server (runs at http://localhost:8000)
uvicorn app.main:app --reload --port 8000
```

### Frontend Setup
```bash
cd GoalPilot_Application/frontend

# Install frontend dependencies
npm install

# Start development server (runs at http://localhost:5173)
npm run dev
```

---

## 5. API Reference

- `GET /api/health`: Health status and connectivity with GoalPilot_AI datasets.
- `POST /api/optimize`: Runs the single-goal LP optimization given financial profile and goal parameters.
- `POST /api/derive-profile`: Computes baseline surplus and emergency fund metrics.
- `GET /api/benchmarks`: Returns sample records from the 10,000 synthetic population.
- `POST /api/benchmarks/run/{user_id}`: Runs live optimization on a research benchmark case.

---

## 6. Regulatory & Educational Disclaimer

> **Disclaimer**: GoalPilot is an academic research and decision-support prototype. It does not constitute personalized, regulated financial advice, wealth management recommendations, or investment return guarantees. All projections and allocations are educational decision simulations.
