"""Unit and integration tests for real-time WebSocket telemetry streaming."""

from __future__ import annotations

import time
from fastapi.testclient import TestClient


def test_websocket_connection_and_ping(client: TestClient) -> None:
    """Verify WebSocket handshake connection and ping-pong reply."""
    with client.websocket_connect("/ws/problems/test_prob_101") as ws:
        # 1. Handshake packet
        handshake = ws.receive_json()
        assert handshake["type"] == "connection_established"
        assert handshake["problem_id"] == "test_prob_101"

        # 2. Ping-pong
        ws.send_text("ping")
        reply = ws.receive_json()
        assert reply["type"] == "pong"


def test_websocket_streams_solve_progress_and_completion(
    client: TestClient, sample_problem_payload: dict
) -> None:
    """Verify WebSocket streams solve_started, solve_progress, and solve_completed packets."""
    client.post("/problems", json=sample_problem_payload)

    with client.websocket_connect("/ws/problems/test_city_4") as ws:
        # Handshake
        handshake = ws.receive_json()
        assert handshake["type"] == "connection_established"

        # Launch solve
        solve_resp = client.post(
            "/problems/test_city_4/solve",
            json={"num_particles": 15, "max_iters": 10, "seed": 42},
        )
        assert solve_resp.status_code == 202

        # Collect incoming stream packets
        received_types: set[str] = set()
        for _ in range(50):
            msg = ws.receive_json()
            received_types.add(msg["type"])
            if msg["type"] == "solve_completed":
                assert msg["is_feasible"] is True
                assert "solution_cost" in msg
                break

        assert "solve_started" in received_types
        assert "solve_progress" in received_types
        assert "solve_completed" in received_types


def test_websocket_streams_reoptimization_telemetry(
    client: TestClient, sample_problem_payload: dict
) -> None:
    """Verify WebSocket streams reoptimization_update telemetry upon incident injection."""
    client.post("/problems", json=sample_problem_payload)

    # Solve first
    solve_resp = client.post(
        "/problems/test_city_4/solve",
        json={"num_particles": 15, "max_iters": 10, "seed": 42},
    )
    job_id = solve_resp.json()["job_id"]
    for _ in range(600):  # Poll up to 30.0s (600 * 0.05s)
        time.sleep(0.05)
        if client.get(f"/problems/test_city_4/jobs/{job_id}").json()["status"] == "completed":
            break

    with client.websocket_connect("/ws/problems/test_city_4") as ws:
        # Handshake
        ws.receive_json()

        # Inject event
        event_payload = {
            "event_type": "edge_congestion",
            "trigger_time": 0.0,
            "duration": 500.0,
            "origin_id": "depot",
            "dest_id": "c1",
            "multiplier": 2.0,
        }
        client.post("/problems/test_city_4/events", json=event_payload)

        # Receive reoptimization_update
        reopt_msg = ws.receive_json()
        assert reopt_msg["type"] == "reoptimization_update"
        assert reopt_msg["problem_id"] == "test_city_4"
        assert "tier_selected" in reopt_msg
        assert "wall_clock_time_ms" in reopt_msg
        assert "cost_after" in reopt_msg
