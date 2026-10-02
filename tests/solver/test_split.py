"""Unit tests for Prins Split algorithm in solver/split.py."""

import numpy as np
from pathlib import Path
import pytest

from solver.io import load_cvrplib
from solver.models import Customer, Depot, Problem, Vehicle
from solver.split import prins_split


def test_prins_split_hand_crafted() -> None:
    """Test Prins Split on a 4-customer hand-checkable instance.

    Depot at (0, 0).
    Cust 1: (1, 0), demand 4.
    Cust 2: (2, 0), demand 6.  Route [1, 2] load=10, cost = 1 + 1 + 2 = 4.0
    Cust 3: (0, 1), demand 5.
    Cust 4: (0, 2), demand 5.  Route [3, 4] load=10, cost = 1 + 1 + 2 = 4.0
    Capacity Q = 10.0.
    Optimal split of tour [1, 2, 3, 4] must yield exactly 2 routes with total cost 8.0.
    """
    depot = Depot(id="depot", lat=0.0, lon=0.0)
    customers = [
        Customer(id="1", lat=0.0, lon=1.0, demand=4.0, ready_time=0.0, due_time=100.0, service_time=0.0),
        Customer(id="2", lat=0.0, lon=2.0, demand=6.0, ready_time=0.0, due_time=100.0, service_time=0.0),
        Customer(id="3", lat=1.0, lon=0.0, demand=5.0, ready_time=0.0, due_time=100.0, service_time=0.0),
        Customer(id="4", lat=2.0, lon=0.0, demand=5.0, ready_time=0.0, due_time=100.0, service_time=0.0),
    ]
    vehicles = [Vehicle(id=f"V_{i+1}", capacity=10.0) for i in range(4)]
    problem = Problem(id="toy_split", depot=depot, customers=customers, vehicles=vehicles)
    problem.compute_euclidean_matrices()

    tour = [1, 2, 3, 4]
    cost, routes, is_feasible, violations = prins_split(problem, tour)

    assert is_feasible is True
    assert violations == {}
    assert len(routes) == 2
    assert pytest.approx(cost, rel=1e-5) == 8.0

    assert routes[0].stop_ids == ["1", "2"]
    assert pytest.approx(routes[0].load, rel=1e-5) == 10.0
    assert pytest.approx(routes[0].distance, rel=1e-5) == 4.0

    assert routes[1].stop_ids == ["3", "4"]
    assert pytest.approx(routes[1].load, rel=1e-5) == 10.0
    assert pytest.approx(routes[1].distance, rel=1e-5) == 4.0


def test_prins_split_customer_coverage_and_capacity_on_cvrp() -> None:
    """Test that Prins Split on A-n32-k5 visits every customer exactly once and obeys capacity."""
    problem = load_cvrplib(Path("benchmarks/instances/A-n32-k5.vrp"))
    n = problem.num_customers

    # Generate a random tour
    rng = np.random.default_rng(123)
    tour = rng.permutation(np.arange(1, n + 1))

    cost, routes, is_feasible, violations = prins_split(problem, tour)

    assert is_feasible is True
    assert violations == {}
    assert cost > 0.0

    visited_stops = []
    for route in routes:
        assert route.load <= problem.vehicles[0].capacity, f"Route {route.vehicle_id} exceeded capacity"
        visited_stops.extend(route.stop_ids)

    # Every customer visited exactly once
    expected_ids = {c.id for c in problem.customers}
    assert set(visited_stops) == expected_ids
    assert len(visited_stops) == n


def test_prins_split_max_vehicles_constraint() -> None:
    """Test that Prins Split detects and flags max-route-count violations when unachievable."""
    depot = Depot(id="depot", lat=0.0, lon=0.0)
    customers = [
        Customer(id="1", lat=0.0, lon=1.0, demand=6.0, ready_time=0.0, due_time=100.0, service_time=0.0),
        Customer(id="2", lat=0.0, lon=2.0, demand=6.0, ready_time=0.0, due_time=100.0, service_time=0.0),
    ]
    # Capacity is 10.0, so both customers cannot fit in 1 vehicle (6 + 6 = 12 > 10)
    vehicles = [Vehicle(id="V_1", capacity=10.0)]
    problem = Problem(id="toy_cap", depot=depot, customers=customers, vehicles=vehicles)
    problem.compute_euclidean_matrices()

    tour = [1, 2]
    # Enforce max_vehicles = 1
    cost, routes, is_feasible, violations = prins_split(problem, tour, max_vehicles=1)

    assert is_feasible is False
    assert "max_vehicles" in violations
    assert len(routes) == 2  # Partitioned into 2 routes because 1 is impossible
