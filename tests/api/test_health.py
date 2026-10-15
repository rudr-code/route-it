"""Unit tests for /health endpoint."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_endpoint(client: TestClient) -> None:
    """Verify /health returns 200 with operational metrics."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "healthy"
    assert "version" in data
    assert data["uptime_seconds"] >= 0.0
    assert isinstance(data["valhalla_connected"], bool)
    assert data["active_problems_count"] == 0
    assert data["active_ws_connections"] == 0
