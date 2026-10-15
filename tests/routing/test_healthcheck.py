"""Unit tests for Valhalla health check utility in routing/healthcheck.py."""

from unittest.mock import MagicMock, patch
import pytest

from routing.healthcheck import check_valhalla_health, main


def test_healthcheck_offline_service() -> None:
    """Verify healthcheck handles unreachable server gracefully."""
    # Port 59999 should not have a service listening
    report = check_valhalla_health(base_url="http://127.0.0.1:59999", timeout=0.5)

    assert report["healthy"] is False
    assert report["error"] is not None
    assert "Failed to connect" in report["error"]


def test_healthcheck_mocked_healthy_service() -> None:
    """Verify healthcheck parsing on successful /status and /route responses."""
    mock_status_resp = MagicMock()
    mock_status_resp.status = 200
    mock_status_resp.read.return_value = b'{"version": "3.4.0", "tileset_last_modified": 1700000000}'
    mock_status_resp.__enter__.return_value = mock_status_resp

    mock_route_resp = MagicMock()
    mock_route_resp.status = 200
    mock_route_resp.read.return_value = b'{"trip": {"summary": {"length": 2.45, "time": 320}}}'
    mock_route_resp.__enter__.return_value = mock_route_resp

    with patch("urllib.request.urlopen", side_effect=[mock_status_resp, mock_route_resp]):
        report = check_valhalla_health("http://localhost:8002", timeout=1.0)

    assert report["healthy"] is True
    assert report["version"] == "3.4.0"
    assert report["tileset_last_modified"] == 1700000000
    assert report["sample_route_km"] == 2.45
    assert report["sample_route_sec"] == 320
    assert report["status_latency_ms"] is not None
    assert report["route_latency_ms"] is not None


def test_healthcheck_cli_exit_code_offline() -> None:
    """Verify CLI returns code 1 when Valhalla is offline."""
    exit_code = main(["--url", "http://127.0.0.1:59999", "--timeout", "0.5"])
    assert exit_code == 1


def test_healthcheck_cli_exit_code_healthy() -> None:
    """Verify CLI returns code 0 when Valhalla is online."""
    mock_status_resp = MagicMock()
    mock_status_resp.status = 200
    mock_status_resp.read.return_value = b'{"version": "3.4.0", "tileset_last_modified": 1700000000}'
    mock_status_resp.__enter__.return_value = mock_status_resp

    mock_route_resp = MagicMock()
    mock_route_resp.status = 200
    mock_route_resp.read.return_value = b'{"trip": {"summary": {"length": 2.45, "time": 320}}}'
    mock_route_resp.__enter__.return_value = mock_route_resp

    with patch("urllib.request.urlopen", side_effect=[mock_status_resp, mock_route_resp]):
        exit_code = main(["--url", "http://localhost:8002", "--timeout", "1.0"])

    assert exit_code == 0
