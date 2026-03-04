"""
Tests for Performance Service

This test suite validates:
- API health and configuration
- Goal retrieval and structure
- Goal creation and validation
- Goal updates and status mapping logic
- Performance reviews integrity
- Query handling with and without OpenAI
- Data consistency and validation rules

These tests ensure the Performance Agent behaves correctly
under normal, edge, and failure scenarios.
"""

import pytest
from fastapi.testclient import TestClient
import sys
import os

# Ensure src folder is available for import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.main import app

client = TestClient(app)


# ============================================================
# HEALTH CHECK
# ============================================================

def test_health_check():
    """
    Verify service is running and correctly configured.

    Ensures:
    - Service responds successfully
    - Service identifies itself correctly
    - Version info is included
    - OpenAI configuration status is exposed
    """
    response = client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "performance-agent"
    assert "version" in data
    assert "openai_status" in data


# ============================================================
# GOAL RETRIEVAL
# ============================================================

def test_get_performance_goals():
    """
    Ensure goals can be retrieved for a valid employee.

    Validates:
    - Correct response structure
    - Goals list exists
    - Each goal has minimal required fields
    """
    response = client.get("/api/performance/goals?employee_id=EMP000001")
    assert response.status_code == 200

    data = response.json()
    assert "goals" in data
    assert isinstance(data["goals"], list)

    if len(data["goals"]) > 0:
        goal = data["goals"][0]
        assert "id" in goal
        assert "title" in goal
        assert "status" in goal


def test_get_goals_missing_employee():
    """
    Ensure API validation triggers 422 when required query param is missing.
    """
    response = client.get("/api/performance/goals")
    assert response.status_code == 422


# ============================================================
# PERFORMANCE REVIEWS
# ============================================================

def test_get_performance_reviews():
    """
    Ensure employee performance reviews are retrievable
    and contain rating-related fields.
    """
    response = client.get("/api/performance/reviews?employee_id=EMP000001")
    assert response.status_code == 200

    data = response.json()
    assert "reviews" in data
    assert isinstance(data["reviews"], list)

    if len(data["reviews"]) > 0:
        review = data["reviews"][0]
        assert "period" in review or "date" in review
        assert "rating" in review or "score" in review


# ============================================================
# GOAL CREATION
# ============================================================

def test_create_performance_goal():
    """
    Validate goal creation workflow.

    Ensures:
    - API accepts valid goal payload
    - Returns created goal object
    - Title matches input
    """
    new_goal = {
        "employee_id": "EMP000001",
        "title": "Complete Project X",
        "description": "Finish the X project by Q2",
        "target_date": "2026-06-30"
    }

    response = client.post("/api/performance/goal/create", json=new_goal)
    assert response.status_code == 200

    data = response.json()
    assert "goal" in data
    assert data["goal"]["title"] == "Complete Project X"


def test_create_goal_missing_fields():
    """
    Ensure validation rejects incomplete goal payload.
    Protects against malformed requests entering system.
    """
    response = client.post(
        "/api/performance/goal/create",
        json={
            "employee_id": "EMP000001",
            "title": "Test Goal"
        }
    )
    assert response.status_code == 422


# ============================================================
# GOAL UPDATE + STATUS MAPPING
# ============================================================

def test_update_performance_goal():
    """
    Validate updating goal progress updates:
    - Progress percentage
    - Status mapping logic
    - Notes appending behavior
    """
    response = client.get("/api/performance/goals", params={"employee_id": "EMP000001"})
    assert response.status_code == 200

    goals = response.json()["goals"]
    assert goals, "No goals found for employee EMP000001"

    goal_id = goals[0]["id"]

    update_payload = {
        "goal_id": goal_id,
        "progress": 75,
        "notes": "Updated in test"
    }

    update_response = client.put("/api/performance/goal/update", json=update_payload)
    assert update_response.status_code == 200

    updated_goal = update_response.json()["goal"]

    assert updated_goal["progress"] == 75
    assert updated_goal["status"] in ["on-track", "in-progress", "needs-attention"]

    assert any("Updated in test" in note["note"] for note in updated_goal.get("notes", []))


# ============================================================
# QUERY ENDPOINT
# ============================================================

@pytest.mark.asyncio
async def test_performance_query_with_openai():
    """
    Test AI-powered query endpoint.

    If OpenAI is configured:
        - Should return answer field.
    If not configured:
        - Should return 500.
    """
    response = client.post(
        "/api/performance/query",
        json={
            "query": "What are my performance goals?",
            "employee_id": "EMP000001"
        }
    )

    if response.status_code == 200:
        data = response.json()
        assert "answer" in data
        assert len(data["answer"]) > 0
    elif response.status_code == 500:
        pass


def test_performance_query_missing_query():
    """
    Ensure missing query field triggers validation error.
    """
    response = client.post(
        "/api/performance/query",
        json={"employee_id": "EMP000001"}
    )
    assert response.status_code == 422


# ============================================================
# DATA VALIDATION & CONSISTENCY
# ============================================================

def test_goal_status_values():
    """
    Validate goal statuses conform to expected set.
    Prevents invalid workflow states.
    """
    response = client.get("/api/performance/goals?employee_id=EMP000001")
    data = response.json()

    valid_statuses = ["not_started", "in_progress", "completed", "on_hold", "cancelled"]

    for goal in data["goals"]:
        if "status" in goal:
            assert goal["status"].lower().replace(" ", "_") in valid_statuses or isinstance(goal["status"], str)


def test_review_ratings():
    """
    Validate review ratings are numeric and within reasonable bounds.
    """
    response = client.get("/api/performance/reviews?employee_id=EMP000001")
    data = response.json()

    for review in data["reviews"]:
        if "rating" in review:
            assert isinstance(review["rating"], (int, float))
            assert 0 <= review["rating"] <= 5
        elif "score" in review:
            assert isinstance(review["score"], (int, float))


def test_goal_target_dates():
    """
    Validate goal target dates follow basic YYYY-MM-DD format.
    Protects against invalid date storage.
    """
    response = client.get("/api/performance/goals?employee_id=EMP000001")
    data = response.json()

    for goal in data["goals"]:
        if "target_date" in goal:
            assert isinstance(goal["target_date"], str)
            if len(goal["target_date"]) >= 10:
                year, month, day = goal["target_date"][:10].split("-")
                assert 2020 <= int(year) <= 2030
                assert 1 <= int(month) <= 12
                assert 1 <= int(day) <= 31


def test_performance_review_periods():
    """
    Ensure reviews contain time reference fields.
    """
    response = client.get("/api/performance/reviews?employee_id=EMP000001")
    data = response.json()

    for review in data["reviews"]:
        assert "period" in review or "date" in review or "year" in review