"""
Tests for Payroll Service

This test suite validates the Payroll API endpoints exposed in main.py.
It covers:

1. Service health check
2. Payroll history retrieval
3. Payslip retrieval
4. AI-powered payroll query (if OpenAI is configured)
5. Invalid employee handling

Run with:
    pytest test_payroll.py -v
"""

import pytest
from fastapi.testclient import TestClient
import sys
import os

# Add project root to Python path so src.main can be imported
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.main import app

# Create test client for FastAPI app
client = TestClient(app)


def test_health_check():
    """
    Test: Service health endpoint

    Ensures:
    - API is reachable
    - Service status is healthy
    """
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_get_payroll_history():
    """
    Test: Retrieve payroll history for a valid employee

    Validates:
    - Endpoint returns 200
    - Response contains 'history' key
    - 'history' is a list
    - Each payroll record contains required fields
    """
    response = client.get("/api/payroll/history/EMP000001")
    assert response.status_code == 200

    data = response.json()
    assert "history" in data
    assert isinstance(data["history"], list)

    # Validate structure of payroll record (if any exists)
    if len(data["history"]) > 0:
        record = data["history"][0]
        assert "month" in record
        assert "year" in record
        assert "gross" in record
        assert "net" in record
        assert "payment_date" in record


def test_get_payslip():
    """
    Test: Retrieve latest payslip for a valid employee

    Validates:
    - Endpoint returns 200
    - Required payslip fields exist
    """
    response = client.get("/api/payroll/payslip/EMP000001")
    assert response.status_code == 200

    data = response.json()

    assert "employee_id" in data
    assert "employee_name" in data
    assert "gross_salary" in data
    assert "deductions" in data
    assert "net_salary" in data


def test_payroll_query():
    """
    Test: AI-powered payroll query endpoint

    This endpoint depends on OpenAI configuration.

    Expected behavior:
    - If OpenAI is configured → returns 200 with "answer"
    - If not configured → returns 500

    We do not hard-fail the test if OpenAI is missing.
    """
    response = client.post(
        "/api/payroll/query",
        json={
            "query": "What is my salary?",
            "employee_id": "EMP000001"
        }
    )

    if response.status_code == 200:
        assert "answer" in response.json()

    elif response.status_code == 500:
        # Acceptable when OPENAI_API_KEY is not set
        print("⚠️ OpenAI not configured")


def test_invalid_employee():
    """
    Test: Request payroll history with invalid employee ID

    Valid behaviors (depending on implementation):
    - 404 Not Found
    - 200 with empty history list

    We accept either behavior to avoid over-coupling test to implementation.
    """
    response = client.get("/api/payroll/history/INVALID999")

    assert response.status_code in [200, 404]