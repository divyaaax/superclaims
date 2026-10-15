"""Tests for Health Check Endpoint."""

from unittest.mock import patch
from fastapi.testclient import TestClient


def test_health_check_endpoint(client: TestClient):
    """Test standard GET /health endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "service" in data
    assert "version" in data
    assert "llm_configured" in data
    assert "llm_model" in data


def test_health_check_llm_configured_status(client: TestClient):
    """Test health check accurately reports LLM configuration state."""
    with patch("app.main.get_llm_service") as mock_get_svc:
        mock_svc = mock_get_svc.return_value
        mock_svc.is_configured.return_value = True

        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["llm_configured"] is True

        mock_svc.is_configured.return_value = False
        response2 = client.get("/health")
        assert response2.status_code == 200
        assert response2.json()["llm_configured"] is False
