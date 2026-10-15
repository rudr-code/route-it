"""Unit tests for time-window repair operator in solver/repair.py."""

from __future__ import annotations

import pytest

from solver.models import Customer, Depot, Problem, Route, Solution, Vehicle
from solver.repair import repair_solution_time_windows
from solver.validate import validate_solution


@pytest.fixture
def problem_with_tight_window() -> Problem:
    """Problem where visiting order determines time window feasibility."""
    depot = Depot(id="depot", lat=0.0, lon=0.0, ready_time=0.0, due_time=200.0)
    # C1 is close with early deadline: dist 5, ready 0, due 15, serv 5
    # C2 is at dist 15, ready 0, due 50, serv 5
    # C3 is at dist 25, ready 0, due 80, serv 5
    customers = [
        Customer(id="C1", lat=5.0, lon=0.0, demand=10.0, ready_time=0.0, due_time=15.0, service_time=5.0),
        Customer(id="C2", lat=15.0, lon=0.0, demand=10.0, ready_time=0.0, due_time=50.0, service_time=5.0),
        Customer(id="C3", lat=25.0, lon=0.0, demand=10.0, ready_time=0.0, due_time=80.0, service_time=5.0),
    ]
    vehicles = [Vehicle(id="V1", capacity=50.0)]
    problem = Problem(id="repair_toy", depot=depot, customers=customers, vehicles=vehicles)
    problem.compute_euclidean_matrices(speed=1.0)
    return problem


def test_repair_operator_fixes_inverted_order(problem_with_tight_window: Problem) -> None:
    """Verify that repair operator reorders C3 -> C2 -> C1 into C1 -> C2 -> C3 to eliminate late arrival."""
    # Intentional late visiting order: C3 -> C2 -> C1
    # Dep -> C3 (arr=25, dep=30) -> C2 (arr=40, dep=45) -> C1 (arr=55 > due 15!)
    late_route = Route(
        vehicle_id="V1",
        stop_ids=["C3", "C2", "C1"],
        arrival_times=[25.0, 40.0, 55.0],
        load=30.0,
        distance=60.0,
        duration=60.0,
    )
    unrepaired_sol = Solution(
        routes=[late_route],
        total_cost=60.0,
        is_feasible=False,
        violations={"time_window": ["C1 late"]},
    )

    repaired_sol = repair_solution_time_windows(problem_with_tight_window, unrepaired_sol)

    assert repaired_sol.is_feasible is True
    assert len(repaired_sol.violations) == 0

    # The customer C1 must now be serviced first (before its tight deadline)
    r = repaired_sol.routes[0]
    assert r.stop_ids[0] == "C1"

    val = validate_solution(problem_with_tight_window, repaired_sol)
    assert val.is_valid is True


def test_repair_operator_noop_on_feasible_solution(problem_with_tight_window: Problem) -> None:
    """Verify repair operator returns unchanged solution when already feasible."""
    feasible_route = Route(
        vehicle_id="V1",
        stop_ids=["C1", "C2", "C3"],
        arrival_times=[5.0, 20.0, 35.0],
        load=30.0,
        distance=50.0,
        duration=65.0,
    )
    sol = Solution(routes=[feasible_route], total_cost=50.0, is_feasible=True)

    repaired = repair_solution_time_windows(problem_with_tight_window, sol)
    assert repaired.is_feasible is True
    assert repaired.routes[0].stop_ids == ["C1", "C2", "C3"]
