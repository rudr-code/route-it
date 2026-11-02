"""Unit tests for async optimization solve jobs and GeoJSON solution endpoints."""

from __future__ import annotations

import time
import pytest
from fastapi.testclient import TestClient

from routing.cost_oracle import EuclideanOracle
from solver.models import Customer, Depot, Problem, Vehicle
from solver.qpso import QPSOConfig, solve_qpso


def test_solution_not_found_before_solve(client: TestClient, sample_problem_payload: dict) -> None:
    """Verify 404 when querying solution before problem has been solved."""
    client.post("/problems", json=sample_problem_payload)
    resp = client.get("/problems/test_city_4/solution")
    assert resp.status_code == 404
    assert "no solution available" in resp.json()["detail"].lower()


def test_solve_async_job_and_poll_solution(client: TestClient, sample_problem_payload: dict) -> None:
    """Verify async QPSO solve execution, job polling, and GeoJSON solution extraction."""
    client.post("/problems", json=sample_problem_payload)

    # 1. Trigger async solve job
    solve_req = {
        "num_particles": 15,
        "max_iters": 20,
        "cost_oracle_type": "euclidean",
        "seed": 42,
        "apply_tw_repair": True,
    }
    solve_resp = client.post("/problems/test_city_4/solve", json=solve_req)
    assert solve_resp.status_code == 202
    job_data = solve_resp.json()
    job_id = job_data["job_id"]
    assert job_data["problem_id"] == "test_city_4"
    assert job_data["status"] in ("pending", "running", "completed")

    # 2. Poll job status until completed
    max_wait_seconds = 30.0
    start_poll = time.time()
    final_status = job_data["status"]

    while final_status not in ("completed", "failed") and (time.time() - start_poll) < max_wait_seconds:
        time.sleep(0.05)
        poll_resp = client.get(f"/problems/test_city_4/jobs/{job_id}")
        assert poll_resp.status_code == 200
        final_status = poll_resp.json()["status"]

    assert final_status == "completed"

    # 3. Retrieve solution & GeoJSON
    sol_resp = client.get("/problems/test_city_4/solution?sim_time=0.0")
    assert sol_resp.status_code == 200
    sol_data = sol_resp.json()

    assert sol_data["problem_id"] == "test_city_4"
    assert sol_data["total_cost"] > 0.0
    assert sol_data["is_feasible"] is True
    assert len(sol_data["routes"]) >= 1

    # 4. Verify GeoJSON structure
    geojson = sol_data["geojson"]
    assert geojson["type"] == "FeatureCollection"
    features = geojson["features"]
    assert len(features) > 1

    route_features = [f for f in features if f["properties"].get("feature_type") == "route"]
    assert len(route_features) >= 1
    for rf in route_features:
        assert rf["geometry"]["type"] == "LineString"
        assert len(rf["geometry"]["coordinates"]) >= 3  # Depot -> stop -> Depot
        assert "vehicle_id" in rf["properties"]
        assert "color" in rf["properties"]

    stop_features = [f for f in features if f["properties"].get("feature_type") == "customer"]
    assert len(stop_features) == 4
    for sf in stop_features:
        assert sf["geometry"]["type"] == "Point"
        assert sf["properties"]["id"] in ["c1", "c2", "c3", "c4"]
        assert "arrival_time" in sf["properties"]


def test_planar_coordinates_with_explicit_planar_oracle() -> None:
    """Verify that planar Cartesian coordinates remain fully supported and feasible with use_haversine=False."""
    depot = Depot(id="depot", lat=0.0, lon=0.0, ready_time=0.0, due_time=1000.0)
    customers = [
        Customer(id="c1", lat=10.0, lon=0.0, demand=5.0, ready_time=0.0, due_time=500.0, service_time=10.0),
        Customer(id="c2", lat=20.0, lon=0.0, demand=5.0, ready_time=0.0, due_time=500.0, service_time=10.0),
        Customer(id="c3", lat=0.0, lon=10.0, demand=5.0, ready_time=0.0, due_time=500.0, service_time=10.0),
        Customer(id="c4", lat=0.0, lon=20.0, demand=5.0, ready_time=0.0, due_time=500.0, service_time=10.0),
    ]
    vehicles = [
        Vehicle(id="v1", capacity=15.0, shift_start=0.0, shift_end=1000.0),
        Vehicle(id="v2", capacity=15.0, shift_start=0.0, shift_end=1000.0),
    ]
    problem = Problem(id="planar_toy", depot=depot, customers=customers, vehicles=vehicles, coordinate_system="planar")
    problem.compute_euclidean_matrices(speed=1.0)

    oracle = EuclideanOracle(base_speed_mps=1.0, use_haversine=False)
    solution, _ = solve_qpso(problem, QPSOConfig(num_particles=15, max_iters=20, seed=42), cost_oracle=oracle)

    assert solution.is_feasible is True
    assert solution.violations == {}
    assert solution.total_cost == pytest.approx(80.0, rel=1e-3)

