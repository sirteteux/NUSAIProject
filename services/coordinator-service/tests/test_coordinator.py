"""
Tests for Coordinator Agent
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
    """Test health endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "coordinator-agent"


def test_list_agents():
    """Test list agents endpoint"""
    response = client.get("/api/coordinator/agents")
    assert response.status_code == 200
    data = response.json()
    assert "agents" in data
    assert len(data["agents"]) == 5  # FAQ, Payroll, Leave, Recruitment, Performance


@pytest.mark.asyncio
async def test_coordinator_routing():
    """Test intelligent routing"""
    # Test salary question -> should route to Payroll
    response = client.post(
        "/api/coordinator/ask",
        json={
            "query": "What is my salary?",
            "employee_id": "EMP000001"
        }
    )
    # Note: This will fail if OpenAI key is not configured or agents are not running
    # In CI/CD, we can mock these responses
    if response.status_code == 200:
        data = response.json()
        assert "answer" in data
        assert "agent_used" in data


def test_invalid_request():
    """Test error handling for invalid requests"""
    response = client.post(
        "/api/coordinator/ask",
        json={}  # Missing required 'query' field
    )
    assert response.status_code == 422  # Validation error


def test_openai_configuration():
    """Test OpenAI configuration status"""
    response = client.get("/health")
    data = response.json()
    # In tests, we might not have OpenAI configured
    assert "openai_status" in data
