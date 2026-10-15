"""Unit tests for dynamic incident injection and re-optimization endpoints."""

from __future__ import annotations

import time
from fastapi.testclient import TestClient


def _solve_problem_sync(client: TestClient, problem_id: str) -> None:
    """Helper to launch solve and wait for completion."""
    solve_resp = client.post(
        f"/problems/{problem_id}/solve",
        json={"num_particles": 15, "max_iters": 20, "seed": 42},
    )
    job_id = solve_resp.json()["job_id"]
    for _ in range(600):  # Poll up to 30.0s (600 * 0.05s)
        time.sleep(0.05)
        st = client.get(f"/problems/{problem_id}/jobs/{job_id}").json()["status"]
        if st in ("completed", "failed"):
            break


def test_inject_event_without_solution_errors(client: TestClient, sample_problem_payload: dict) -> None:
    """Verify 400 when attempting to inject an event into an unsolved problem."""
    client.post("/problems", json=sample_problem_payload)
    event_payload = {
        "event_type": "edge_congestion",
        "trigger_time": 0.0,
        "duration": 500.0,
        "origin_id": "depot",
        "dest_id": "c1",
        "multiplier": 2.0,
    }
    resp = client.post("/problems/test_city_4/events", json=event_payload)
    assert resp.status_code == 400
    assert "not been solved" in resp.json()["detail"].lower()


def test_inject_traffic_event_reoptimization(client: TestClient, sample_problem_payload: dict) -> None:
    """Verify dynamic incident injection triggers tiered re-optimizer and logs audit record."""
    client.post("/problems", json=sample_problem_payload)
    _solve_problem_sync(client, "test_city_4")

    # Inject edge congestion
    event_payload = {
        "event_id": "api_test_cong",
        "event_type": "edge_congestion",
        "trigger_time": 0.0,
        "duration": 600.0,
        "origin_id": "depot",
        "dest_id": "c1",
        "multiplier": 2.0,
        "description": "API Test Congestion on Depot Exit",
    }
    resp = client.post("/problems/test_city_4/events", json=event_payload)
    assert resp.status_code == 200
    reopt_data = resp.json()

    assert reopt_data["event_id"] == "api_test_cong"
    assert reopt_data["tier_selected"] in (
        "DO_NOTHING",
        "TIER_1_PATH_REPAIR",
        "TIER_2_LOCAL_REPAIR",
        "TIER_3_QPSO_WARM_START",
    )
    assert reopt_data["wall_clock_time_ms"] > 0.0
    assert "solution" in reopt_data
    assert reopt_data["solution"]["is_feasible"] is True

    # Audit history endpoint
    hist_resp = client.get("/problems/test_city_4/events")
    assert hist_resp.status_code == 200
    records = hist_resp.json()
    assert len(records) == 1
    assert records[0]["event_id"] == "api_test_cong"
