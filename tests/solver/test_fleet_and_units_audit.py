"""Tests to reproduce and verify fixes for:
A) Fleet size enforcement as a hard limit in Split and Validator.
B) Unit contract consistency.
C) Explicit coordinate_system ("geographic" vs "planar") without auto-detect.
"""

from __future__ import annotations

import math
import pytest
from solver.models import Customer, Depot, Problem, Route, Solution, Vehicle
from solver.split import prins_split
from solver.validate import validate_solution
from routing.cost_oracle import EuclideanOracle, Location


# ---------------------------------------------------------------------------
# Issue A: Fleet Size as a Hard Limit
# ---------------------------------------------------------------------------

def test_split_enforces_fleet_size_hard_limit_when_not_allowed_extra() -> None:
    """Split must respect max vehicles from problem.vehicles by default.
    
    If demands require 3 routes but only 2 vehicles are in problem.vehicles,
    it must report is_feasible=False and include a fleet_size violation.
    """
    depot = Depot(id="depot", lat=0.0, lon=0.0, ready_time=0.0, due_time=1000.0)
    # 3 customers, each with demand 60. Vehicle capacity 100.
    # Therefore, 3 routes are strictly required!
    customers = [
        Customer(id=f"c{i+1}", lat=float(i+1), lon=0.0, demand=60.0, ready_time=0.0, due_time=1000.0, service_time=5.0)
        for i in range(3)
    ]
    # Only 2 vehicles available in the fleet
    vehicles = [
        Vehicle(id="V1", capacity=100.0),
        Vehicle(id="V2", capacity=100.0),
    ]
    problem = Problem(id="fleet_test", depot=depot, customers=customers, vehicles=vehicles, coordinate_system="planar")
    problem.compute_euclidean_matrices(speed=1.0)

    # Tour visiting customers 1, 2, 3
    tour = [1, 2, 3]

    # Default allow_extra_vehicles=False:
    cost, routes, is_feasible, violations = prins_split(
        problem, tour, allow_extra_vehicles=False
    )

    # Must be marked infeasible because 3 routes > 2 vehicles!
    assert is_feasible is False
    assert "fleet_size" in violations or "max_vehicles" in violations
    fleet_viols = violations.get("fleet_size", []) + violations.get("max_vehicles", [])
    assert any("2" in v for v in fleet_viols)


def test_split_allows_extra_vehicles_when_flag_is_true() -> None:
    """When allow_extra_vehicles=True, split can generate extra routes."""
    depot = Depot(id="depot", lat=0.0, lon=0.0, ready_time=0.0, due_time=1000.0)
    customers = [
        Customer(id=f"c{i+1}", lat=float(i+1), lon=0.0, demand=60.0, ready_time=0.0, due_time=1000.0, service_time=5.0)
        for i in range(3)
    ]
    vehicles = [
        Vehicle(id="V1", capacity=100.0),
        Vehicle(id="V2", capacity=100.0),
    ]
    problem = Problem(id="fleet_test", depot=depot, customers=customers, vehicles=vehicles, coordinate_system="planar")
    problem.compute_euclidean_matrices(speed=1.0)

    tour = [1, 2, 3]
    cost, routes, is_feasible, violations = prins_split(
        problem, tour, allow_extra_vehicles=True
    )

    assert len(routes) == 3
    assert is_feasible is True
    assert "fleet_size" not in violations
    assert "max_vehicles" not in violations


def test_validator_flags_unregistered_vehicle_id() -> None:
    """Validator must flag any route whose vehicle_id is not in problem.vehicles."""
    depot = Depot(id="depot", lat=0.0, lon=0.0)
    customers = [Customer(id="c1", lat=1.0, lon=0.0, demand=10.0, ready_time=0.0, due_time=100.0, service_time=1.0)]
    vehicles = [Vehicle(id="V1", capacity=50.0)]
    problem = Problem(id="val_test", depot=depot, customers=customers, vehicles=vehicles, coordinate_system="planar")
    problem.compute_euclidean_matrices()

    # Solution assigns route to synthetic vehicle "V_EXTRA" not in problem.vehicles
    sol = Solution(
        routes=[Route(vehicle_id="V_EXTRA", stop_ids=["c1"], arrival_times=[1.0], load=10.0, distance=2.0, duration=3.0)],
        total_cost=2.0,
        is_feasible=True,
    )

    res = validate_solution(problem, sol)
    assert res.is_valid is False
    assert "fleet_size" in res.violations
    assert any("V_EXTRA" in msg for msg in res.violations["fleet_size"])


# ---------------------------------------------------------------------------
# Issue C: Coordinate System ("geographic" vs "planar")
# ---------------------------------------------------------------------------

def test_problem_coordinate_system_field() -> None:
    """Problem must have coordinate_system field defaulting to 'geographic'."""
    depot = Depot(id="depot", lat=22.3, lon=73.18)
    customers = [Customer(id="c1", lat=22.31, lon=73.19, demand=10.0, ready_time=0.0, due_time=100.0, service_time=1.0)]
    vehicles = [Vehicle(id="v1", capacity=100.0)]
    p_default = Problem(id="p1", depot=depot, customers=customers, vehicles=vehicles)
    assert p_default.coordinate_system == "geographic"

    p_planar = Problem(id="p2", depot=depot, customers=customers, vehicles=vehicles, coordinate_system="planar")
    assert p_planar.coordinate_system == "planar"


def test_euclidean_oracle_no_autodetect() -> None:
    """EuclideanOracle must use explicit coordinate_system instead of auto-detecting.
    
    If coordinates are in [-90, 90] but coordinate_system='planar', it must compute
    planar hypot distance, NOT earth-curvature Haversine distance.
    """
    p1 = Location(id="loc1", lat=10.0, lon=20.0)
    p2 = Location(id="loc2", lat=13.0, lon=24.0)

    # 3-4-5 triangle in degrees: hypot(3, 4) = 5.0
    oracle_planar = EuclideanOracle(coordinate_system="planar", base_speed_mps=1.0)
    dist_planar = oracle_planar.distance(p1, p2)
    assert dist_planar == pytest.approx(5.0, abs=1e-5)

    oracle_geo = EuclideanOracle(coordinate_system="geographic", base_speed_mps=1.0)
    dist_geo = oracle_geo.distance(p1, p2)
    # 5 degrees on Earth is over 500,000 metres!
    assert dist_geo > 500_000.0
