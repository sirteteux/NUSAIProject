"""
Comprehensive Tests for Recruitment Service
"""

import pytest
from fastapi.testclient import TestClient
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.main import app

client = TestClient(app)


# =========================
# HEALTH CHECK
# =========================

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "recruitment-agent"
    assert data["version"] == "1.0.0"
    assert data["openai_status"] in ["configured", "missing"]


# =========================
# JOB OPENINGS LIST
# =========================

def test_get_all_openings():
    response = client.get("/api/recruitment/openings")
    assert response.status_code == 200

    data = response.json()
    assert "openings" in data
    assert "total" in data
    assert isinstance(data["openings"], list)
    assert data["total"] == len(data["openings"])
    assert len(data["openings"]) > 0


def test_openings_structure():
    response = client.get("/api/recruitment/openings")
    data = response.json()

    required_fields = [
        "id", "title", "department", "location",
        "type", "experience", "skills",
        "description", "posted", "status",
        "salary_range"
    ]

    for job in data["openings"]:
        for field in required_fields:
            assert field in job
            assert job[field] is not None


# =========================
# FILTERING
# =========================

def test_filter_by_department():
    response = client.get("/api/recruitment/openings?department=Engineering")
    assert response.status_code == 200

    data = response.json()
    for job in data["openings"]:
        assert job["department"] == "Engineering"


def test_filter_by_location():
    response = client.get("/api/recruitment/openings?location=Remote")
    assert response.status_code == 200

    data = response.json()
    for job in data["openings"]:
        assert "Remote" in job["location"]


def test_filter_by_department_case_insensitive():
    response = client.get("/api/recruitment/openings?department=engineering")
    assert response.status_code == 200

    data = response.json()
    for job in data["openings"]:
        assert job["department"].lower() == "engineering"


# =========================
# SINGLE JOB
# =========================

def test_get_job_by_id():
    all_jobs = client.get("/api/recruitment/openings").json()

    job_id = all_jobs["openings"][0]["id"]

    response = client.get(f"/api/recruitment/opening/{job_id}")
    assert response.status_code == 200

    job = response.json()
    assert job["id"] == job_id
    assert "title" in job
    assert "description" in job


def test_get_job_not_found():
    response = client.get("/api/recruitment/opening/99999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found"


# =========================
# STATUS VALUES
# =========================

def test_job_status_values():
    valid_status = ["open", "closed", "pending", "filled"]

    response = client.get("/api/recruitment/openings")
    data = response.json()

    for job in data["openings"]:
        assert job["status"] in valid_status


# =========================
# QUERY ENDPOINT
# =========================

def test_query_without_openai():
    response = client.post(
        "/api/recruitment/query",
        json={"query": "What jobs are open?"}
    )

    assert response.status_code in [200, 500]

    if response.status_code == 200:
        data = response.json()
        assert "answer" in data
        assert "data" in data
        assert "open_positions" in data["data"]
    else:
        # Don't expect exact message — OpenAI may raise different errors
        data = response.json()
        assert "detail" in data
        assert isinstance(data["detail"], str)


def test_query_with_context_string():
    """
    Context must be STRING (as per your model)
    """
    response = client.post(
        "/api/recruitment/query",
        json={
            "query": "Any engineering roles?",
            "context": "Candidate has 5 years backend experience"
        }
    )

    assert response.status_code in [200, 500]


def test_query_validation_error():
    """
    Missing query should return 422
    """
    response = client.post(
        "/api/recruitment/query",
        json={}
    )
    assert response.status_code == 422


# =========================
# DATA CONSISTENCY
# =========================

def test_total_matches_openings_length():
    response = client.get("/api/recruitment/openings")
    data = response.json()
    assert data["total"] == len(data["openings"])


def test_skills_are_list():
    response = client.get("/api/recruitment/openings")
    data = response.json()

    for job in data["openings"]:
        assert isinstance(job["skills"], list)


def test_posted_date_format():
    response = client.get("/api/recruitment/openings")
    data = response.json()

    for job in data["openings"]:
        # basic ISO date check
        assert len(job["posted"]) == 10
        assert job["posted"].count("-") == 2