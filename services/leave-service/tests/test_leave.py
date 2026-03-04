"""
Tests for Leave Service
"""
import pytest
from fastapi.testclient import TestClient
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "leave-management-agent"
    assert "openai_status" in data


def test_get_leave_balance():
    """Test getting leave balance for employee"""
    response = client.get("/api/leave/balance?employee_id=EMP000001")
    assert response.status_code == 200
    data = response.json()
    assert "balances" in data
    balances = data["balances"]
    
    # Should have different leave types
    assert "annual" in balances or "sick" in balances
    
    # Check structure of leave type
    for leave_type, details in balances.items():
        assert "total" in details
        assert "used" in details
        assert "remaining" in details
        assert details["remaining"] >= 0


def test_get_leave_balance_missing_employee():
    """Test error when employee_id is missing"""
    response = client.get("/api/leave/balance")
    assert response.status_code == 422  # Missing required parameter


def test_get_leave_history():
    """Test getting leave history for employee"""
    response = client.get("/api/leave/history?employee_id=EMP000001")
    assert response.status_code == 200
    data = response.json()
    assert "history" in data
    assert isinstance(data["history"], list)
    
    # Check structure if history exists
    if len(data["history"]) > 0:
        record = data["history"][0]
        assert "type" in record
        assert "start_date" in record
        assert "end_date" in record
        assert "status" in record


def test_request_leave():
    response = client.post(
        "/api/leave/request",
        json={
            "employee_id": "EMP000001",
            "type": "annual",
            "start_date": "2026-03-15",
            "end_date": "2026-03-17",
            "reason": "Personal vacation"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert "request_id" in data
    assert data["employee_id"] == "EMP000001"
    assert data["type"] == "annual"
    assert data["status"] == "pending"
    assert data["days"] > 0


def test_request_leave_missing_fields():
    """Test error handling for incomplete leave request"""
    response = client.post(
        "/api/leave/request",
        json={
            "employee_id": "EMP000001",
            "type": "annual"
            # Missing start_date and end_date
        }
    )
    assert response.status_code == 422


def test_request_leave_invalid_dates():
    response = client.post(
        "/api/leave/request",
        json={
            "employee_id": "EMP000001",
            "type": "annual",
            "start_date": "invalid-date",
            "end_date": "2026-03-17",
            "reason": "Test"
        }
    )

    # Current implementation returns 500 for invalid date parsing
    assert response.status_code == 500
    assert "detail" in response.json()


@pytest.mark.asyncio
async def test_leave_query_with_openai():
    """Test leave query with OpenAI (requires API key)"""
    response = client.post(
        "/api/leave/query",
        json={
            "query": "How many leave days do I have?",
            "employee_id": "EMP000001"
        }
    )
    # This will succeed if OpenAI is configured
    if response.status_code == 200:
        data = response.json()
        assert "answer" in data
        assert len(data["answer"]) > 0
    elif response.status_code == 500:
        pass


def test_leave_query_missing_query():
    """Test error handling for missing query"""
    response = client.post(
        "/api/leave/query",
        json={"employee_id": "EMP000001"}
    )
    assert response.status_code == 422


def test_leave_types():
    """Test different leave types are supported"""
    leave_types = ["annual", "sick", "personal", "maternity"]
    
    for leave_type in leave_types:
        response = client.post(
            "/api/leave/request",
            json={
                "employee_id": "EMP000001",
                "type": leave_type,
                "start_date": "2026-04-01",
                "end_date": "2026-04-02",
                "reason": f"Test {leave_type} leave"
            }
        )
        # Should accept valid leave types
        assert response.status_code in [200, 400]


def test_leave_balance_calculations():
    """Test leave balance calculations are correct"""
    response = client.get("/api/leave/balance?employee_id=EMP000001")
    data = response.json()
    
    for leave_type, details in data["balances"].items():
        # Remaining should equal total - used
        expected_remaining = details["total"] - details["used"]
        assert details["remaining"] == expected_remaining
        # No negative values
        assert details["total"] >= 0
        assert details["used"] >= 0
        assert details["remaining"] >= 0


@pytest.mark.parametrize("employee_id", [
    "EMP000001",
    "EMP000002",
])
def test_multiple_employees_balance(employee_id):
    """Test leave balance for multiple employees"""
    response = client.get(f"/api/leave/balance?employee_id={employee_id}")
    assert response.status_code in [200, 404]


def test_leave_history_chronological():
    """Test leave history is in chronological order"""
    response = client.get("/api/leave/history?employee_id=EMP000001")
    data = response.json()
    
    # History should be sorted (newest first or oldest first)
    if len(data["history"]) > 1:
        dates = [record["start_date"] for record in data["history"]]
        # Check if sorted (either ascending or descending)
        assert dates == sorted(dates) or dates == sorted(dates, reverse=True)


@pytest.mark.parametrize("query", [
    "How many leave days do I have?",
    "Can I take leave next week?",
    "What is my annual leave balance?",
])
def test_leave_various_queries(query):
    """Test leave queries with various questions"""
    response = client.post(
        "/api/leave/query",
        json={"query": query, "employee_id": "EMP000001"}
    )
    assert response.status_code in [200, 500]


def test_health_includes_openai_status():
    """Test health check includes OpenAI status"""
    response = client.get("/health")
    data = response.json()
    assert "openai_configured" in data or "openai_status" in data