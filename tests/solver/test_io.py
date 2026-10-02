"""Unit tests for Route.it dataset loaders and serializers in solver/io.py."""

from pathlib import Path
import pytest

from solver.io import (
    load_cvrplib,
    load_problem_json,
    load_solution_json,
    load_solomon,
    save_problem_json,
    save_solution_json,
)
from solver.models import Customer, Depot, Problem, Route, Solution, Vehicle


def test_load_solomon_hand_made_instance(tmp_path: Path) -> None:
    """Test parsing a minimal synthetic Solomon instance file."""
    content = """C101_TINY
VEHICLE
NUMBER     CAPACITY
   2         50.0

CUSTOMER
CUST NO.  XCOORD.   YCOORD.    DEMAND   READY TIME  DUE DATE   SERVICE TIME
    0        0.0       0.0       0.0          0.0     500.0            0.0
    1       10.0      10.0      15.0         10.0     100.0           10.0
    2       20.0      20.0      20.0         50.0     150.0           15.0
"""
    file_path = tmp_path / "tiny_solomon.txt"
    file_path.write_text(content, encoding="utf-8")

    problem = load_solomon(file_path)

    assert problem.id == "C101_TINY"
    assert problem.depot.lat == 0.0
    assert problem.depot.lon == 0.0
    assert problem.depot.due_time == 500.0
    assert problem.num_customers == 2
    assert problem.num_vehicles == 2
    assert problem.vehicles[0].capacity == 50.0

    cust1 = problem.get_customer("1")
    assert cust1.demand == 15.0
    assert cust1.ready_time == 10.0
    assert cust1.due_time == 100.0
    assert cust1.service_time == 10.0

    # Ensure Euclidean matrices were computed
    assert problem.distance_matrix is not None
    assert problem.travel_time_matrix is not None
    assert len(problem.distance_matrix) == 3


def test_load_cvrplib_real_instance() -> None:
    """Test loading the real reference CVRPLIB instance A-n32-k5.vrp."""
    vrp_path = Path("benchmarks/instances/A-n32-k5.vrp")
    assert vrp_path.is_file(), f"Reference instance not found at {vrp_path}"

    problem = load_cvrplib(vrp_path)

    assert "A-n32-k5" in problem.id
    # Dimension 32 means 1 depot + 31 customers
    assert problem.num_customers == 31
    assert problem.num_vehicles == 5
    assert problem.vehicles[0].capacity == 100.0

    # Verify depot
    assert problem.depot.lat == 76.0  # Node 1 coords: x=82, y=76
    assert problem.depot.lon == 82.0

    # Verify customer 2 demand = 19, coords: x=96, y=44
    cust2 = problem.get_customer("2")
    assert cust2.demand == 19.0
    assert cust2.lat == 44.0
    assert cust2.lon == 96.0

    # Check total demand matches Augerat benchmark specs (sum of demands across nodes 2..32 = 415)
    total_demand = sum(c.demand for c in problem.customers)
    assert total_demand == 415.0

    # Ensure distance matrix computed
    assert problem.distance_matrix is not None
    assert len(problem.distance_matrix) == 32


def test_problem_json_roundtrip(tmp_path: Path) -> None:
    """Test saving Problem to JSON and reloading it."""
    depot = Depot(lat=10.0, lon=20.0)
    c1 = Customer(id="C1", lat=12.0, lon=22.0, demand=5.0, ready_time=0.0, due_time=100.0, service_time=10.0)
    v1 = Vehicle(id="V1", capacity=30.0)
    original_problem = Problem(id="roundtrip_prob", depot=depot, customers=[c1], vehicles=[v1])
    original_problem.compute_euclidean_matrices()

    json_file = tmp_path / "problem.json"
    save_problem_json(original_problem, json_file)

    loaded_problem = load_problem_json(json_file)
    assert loaded_problem.id == original_problem.id
    assert loaded_problem.depot.lat == 10.0
    assert loaded_problem.num_customers == 1
    assert loaded_problem.distance_matrix is not None
    assert loaded_problem.distance_matrix[0][1] == original_problem.distance_matrix[0][1]


def test_solution_json_roundtrip(tmp_path: Path) -> None:
    """Test saving Solution to JSON and reloading it."""
    route = Route(
        vehicle_id="V1",
        stop_ids=["C1"],
        arrival_times=[15.0],
        load=10.0,
        distance=25.0,
        duration=30.0,
    )
    original_solution = Solution(
        routes=[route],
        total_cost=25.0,
        is_feasible=True,
        violations={},
        algorithm="QPSO",
        execution_time_sec=0.045,
        seed=1234,
    )

    json_file = tmp_path / "solution.json"
    save_solution_json(original_solution, json_file)

    loaded_solution = load_solution_json(json_file)
    assert loaded_solution.total_cost == 25.0
    assert loaded_solution.is_feasible is True
    assert loaded_solution.seed == 1234
    assert len(loaded_solution.routes) == 1
    assert loaded_solution.routes[0].stop_ids == ["C1"]
