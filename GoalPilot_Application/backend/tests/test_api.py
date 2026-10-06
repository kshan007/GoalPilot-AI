from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["app_name"] == "GoalPilot Application"
    assert "goalpilot_ai_source" in data

def test_optimize_endpoint_success():
    payload = {
        "user_id": "USER_TEST",
        "financial_profile": {
            "monthly_income": 80000.0,
            "monthly_expenditure": 40000.0,
            "monthly_emi": 0.0,
            "initial_savings": 100000.0,
            "initial_investment": 20000.0,
            "risk_profile": "moderate"
        },
        "goal": {
            "goal_name": "Car Purchase",
            "target_amount": 400000.0,
            "goal_horizon_months": 24,
            "priority": "important",
            "purpose": "Personal mobility"
        }
    }
    response = client.post("/api/optimize", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["optimal_success", "optimal_shortfall"]
    assert "metrics" in data
    assert "monthly_schedule" in data
    assert len(data["monthly_schedule"]) == 24
    assert data["metrics"]["target_amount"] == 400000.0

def test_optimize_endpoint_validation_error():
    payload = {
        "user_id": "USER_TEST",
        "financial_profile": {
            "monthly_income": -100.0,  # invalid
            "monthly_expenditure": 40000.0
        },
        "goal": {
            "goal_name": "Invalid",
            "target_amount": 100000.0,
            "goal_horizon_months": 12
        }
    }
    response = client.post("/api/optimize", json=payload)
    assert response.status_code == 422

def test_benchmarks_list_endpoint():
    response = client.get("/api/benchmarks?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert "users" in data
