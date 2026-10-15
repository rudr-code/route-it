"""Unit tests for independent solution validator in solver/validate.py."""

from __future__ import annotations

import pytest

from solver.models import Customer, Depot, Problem, Route, Solution, Vehicle
from solver.validate import ValidationResult, validate_solution


@pytest.fixture
def sample_problem() -> Problem:
    """Fixture with depot and 3 customers with explicit time windows and demands."""
    depot = Depot(id="depot", lat=0.0, lon=0.0, ready_time=0.0, due_time=100.0, service_time=0.0)
    customers = [
        Customer(id="c1", lat=10.0, lon=0.0, demand=20.0, ready_time=10.0, due_time=30.0, service_time=5.0, priority=1),
        Customer(id="c2", lat=20.0, lon=0.0, demand=30.0, ready_time=25.0, due_time=50.0, service_time=5.0, priority=2),
        Customer(id="c3", lat=30.0, lon=0.0, demand=25.0, ready_time=35.0, due_time=70.0, service_time=5.0, priority=1),
    ]
    vehicles = [
        Vehicle(id="v1", capacity=100.0, shift_start=0.0, shift_end=80.0),
        Vehicle(id="v2", capacity=100.0, shift_start=0.0, shift_end=80.0),
    ]
    problem = Problem(id="sample", depot=depot, customers=customers, vehicles=vehicles)
    problem.compute_euclidean_matrices(speed=1.0)
    return problem


def test_validator_feasible_solution(sample_problem: Problem) -> None:
    """Verify that a strictly valid solution produces is_valid=True with matching costs."""
    # Route: depot -> c1 -> c2 -> c3 -> depot
    # c1: arr=10, wait=0, start=10, serv=5, dep=15
    # c2: arr=25, wait=0, start=25, serv=5, dep=30
    # c3: arr=40, wait=0, start=40, serv=5, dep=45
    # depot: arr=75 <= 100
    route = Route(
        vehicle_id="v1",
        stop_ids=["c1", "c2", "c3"],
        arrival_times=[10.0, 25.0, 40.0],
        load=75.0,
        distance=60.0,
        duration=75.0,
    )
    solution = Solution(routes=[route], total_cost=60.0, is_feasible=True)

    res = validate_solution(sample_problem, solution)
    assert res.is_valid is True
    assert len(res.violations) == 0
    assert res.recomputed_cost == 60.0
    assert res.recomputed_distance == 60.0
    assert res.recomputed_duration == 75.0
    assert res.total_service_time == 15.0
    assert res.total_waiting_time == 0.0
    assert res.customer_count == 3


def test_validator_catches_missing_customer(sample_problem: Problem) -> None:
    """Verify detection of omitted customer."""
    route = Route(
        vehicle_id="v1",
        stop_ids=["c1", "c2"],  # c3 is missing
        arrival_times=[10.0, 25.0],
        load=50.0,
        distance=40.0,
        duration=50.0,
    )
    solution = Solution(routes=[route], total_cost=40.0, is_feasible=False)

    res = validate_solution(sample_problem, solution)
    assert res.is_valid is False
    assert "customer_coverage" in res.violations
    assert "Missing 1 customer" in res.violations["customer_coverage"][0]


def test_validator_catches_duplicate_customer(sample_problem: Problem) -> None:
    """Verify detection of duplicate customer visit."""
    route1 = Route(vehicle_id="v1", stop_ids=["c1", "c2"], arrival_times=[10.0, 25.0], load=50.0, distance=40.0, duration=50.0)
    route2 = Route(vehicle_id="v2", stop_ids=["c2", "c3"], arrival_times=[20.0, 30.0], load=55.0, distance=60.0, duration=65.0)
    solution = Solution(routes=[route1, route2], total_cost=100.0, is_feasible=False)

    res = validate_solution(sample_problem, solution)
    assert res.is_valid is False
    assert "customer_coverage" in res.violations
    assert "Duplicate" in res.violations["customer_coverage"][0]


def test_validator_catches_capacity_overload(sample_problem: Problem) -> None:
    """Verify detection of vehicle capacity breach."""
    # Shrink vehicle capacity to 50
    sample_problem.vehicles[0].capacity = 50.0
    route = Route(
        vehicle_id="v1",
        stop_ids=["c1", "c2", "c3"],  # total load = 75 > 50
        arrival_times=[10.0, 25.0, 40.0],
        load=75.0,
        distance=60.0,
        duration=75.0,
    )
    solution = Solution(routes=[route], total_cost=60.0, is_feasible=False)

    res = validate_solution(sample_problem, solution)
    assert res.is_valid is False
    assert "capacity" in res.violations
    assert "exceeds capacity" in res.violations["capacity"][0]


def test_validator_catches_time_window_violation(sample_problem: Problem) -> None:
    """Verify detection of late arrival at a customer."""
    # Reverse customer order: c3 -> c2 -> c1
    # c3: arr=30 (ready=35, due=70) -> wait 5s, start 35, dep 40
    # c2: arr=40 + 10 = 50 <= 50 -> dep 55
    # c1: arr=55 + 10 = 65 > due 30! (Late by 35s)
    route = Route(
        vehicle_id="v1",
        stop_ids=["c3", "c2", "c1"],
        arrival_times=[30.0, 50.0, 65.0],
        load=75.0,
        distance=60.0,
        duration=75.0,
    )
    solution = Solution(routes=[route], total_cost=60.0, is_feasible=False)

    res = validate_solution(sample_problem, solution)
    assert res.is_valid is False
    assert "time_window" in res.violations
    assert "c1" in res.violations["time_window"][0]


def test_validator_catches_depot_closing_violation(sample_problem: Problem) -> None:
    """Verify detection of late return to depot."""
    sample_problem.depot.due_time = 70.0  # Return takes 75s
    route = Route(
        vehicle_id="v1",
        stop_ids=["c1", "c2", "c3"],
        arrival_times=[10.0, 25.0, 40.0],
        load=75.0,
        distance=60.0,
        duration=75.0,
    )
    solution = Solution(routes=[route], total_cost=60.0, is_feasible=False)

    res = validate_solution(sample_problem, solution)
    assert res.is_valid is False
    assert "depot_due_time" in res.violations


def test_validator_catches_duty_limit_exceeded(sample_problem: Problem) -> None:
    """Verify detection of driver duty limit breach."""
    route = Route(
        vehicle_id="v1",
        stop_ids=["c1", "c2", "c3"],
        arrival_times=[10.0, 25.0, 40.0],
        load=75.0,
        distance=60.0,
        duration=75.0,
    )
    solution = Solution(routes=[route], total_cost=60.0, is_feasible=True)

    # Max duty limit 60.0s < route duration 75.0s
    res = validate_solution(sample_problem, solution, max_duty_duration=60.0, hard_duty_limit=True)
    assert res.is_valid is False
    assert "driver_duty_limit" in res.violations


def test_validator_catches_priority_early_service_violation(sample_problem: Problem) -> None:
    """Verify detection of priority customer serviced late in window."""
    # c2 has priority=2, ready=25, due=50.
    # Early cutoff (ratio 0.5) is 25 + 0.5 * 25 = 37.5.
    # Arrival at c2 in route below:
    # c1: arr=10, dep=15.
    # c3: arr=15 + 20 = 35 (ready=35, dep=40).
    # c2: arr=40 + 10 = 50. Arrived at 50 > 37.5 early deadline!
    route = Route(
        vehicle_id="v1",
        stop_ids=["c1", "c3", "c2"],
        arrival_times=[10.0, 35.0, 50.0],
        load=75.0,
        distance=80.0,
        duration=75.0,
    )
    solution = Solution(routes=[route], total_cost=80.0, is_feasible=True)

    res = validate_solution(
        sample_problem, solution, enforce_priority_early_service=True, priority_early_ratio=0.5
    )
    assert res.is_valid is False
    assert "priority_early_service" in res.violations
    assert "c2" in res.violations["priority_early_service"][0]
