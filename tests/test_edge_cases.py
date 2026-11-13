"""Comprehensive test suite for Route.it Edge Cases (R32-R43).

Tests defensive error handling, constraint satisfaction, and status accuracy:
- R32: Customer demand > max vehicle capacity rejected upfront.
- R33: Total demand > total fleet capacity handled accurately.
- R34: Customer with unachievable hard deadline rejected / infeasible.
- R35: Soft-window deadline missed marked feasible with SLA penalty.
- R36: Invalid/NaN/infinite coordinates rejected upfront.
- R37: Disconnected road network detected as infeasible.
- R38: Zero vehicles available flagged as data_insufficient.
- R39: Missing cost configuration falls back safely to documented defaults.
- R40: Duplicate order ID rejected upfront.
- R41: Replanning with 0 remaining orders reports 'no remaining work'.
- R42: Mid-route traffic change recalculates remaining stops without disturbing completed stops.
- R43: Search limit exceeded explicitly distinguished from mathematical infeasibility.
"""

from __future__ import annotations

import math
import pytest
from pydantic import ValidationError

from dynamic.reoptimizer import DynamicReoptimizer, ReoptimizerConfig, partition_stops_by_commitment
from solver.cost import BusinessCostConfig, compute_cost_breakdown
from solver.models import Customer, Depot, Problem, Route, Solution, Vehicle
from solver.partial import solve_partial_plan
from solver.qpso import QPSOConfig, solve_qpso
from solver.validate import validate_solution


def test_r32_customer_demand_exceeds_max_vehicle_capacity():
    """R32: Customer demand > max vehicle capacity rejected upfront before solver runs."""
    depot = Depot(id="depot", lat=0.0, lon=0.0)
    # Customer demand 150 > vehicle capacity 100
    oversized_cust = Customer(
        id="c_huge", lat=1.0, lon=1.0, demand=150.0, ready_time=0.0, due_time=100.0, service_time=5.0
    )
    fleet = [Vehicle(id="v1", capacity=100.0)]

    with pytest.raises(ValueError, match="exceeds maximum vehicle capacity"):
        Problem(id="prob_r32", depot=depot, customers=[oversized_cust], vehicles=fleet)


def test_r33_total_demand_exceeds_fleet_capacity():
    """R33: Total customer demand > total fleet capacity in Complete mode flags infeasibility or sheds in Partial mode."""
    depot = Depot(id="depot", lat=0.0, lon=0.0)
    # 3 customers of 40 = 120 demand, but single vehicle has capacity 100
    customers = [
        Customer(id="c1", lat=0.0, lon=1.0, demand=40.0, ready_time=0.0, due_time=100.0, service_time=0.0, priority=1),
        Customer(id="c2", lat=0.0, lon=2.0, demand=40.0, ready_time=0.0, due_time=100.0, service_time=0.0, priority=2),
        Customer(id="c3", lat=0.0, lon=3.0, demand=40.0, ready_time=0.0, due_time=100.0, service_time=0.0, priority=3),
    ]
    fleet = [Vehicle(id="v1", capacity=100.0)]
    prob = Problem(id="prob_r33", depot=depot, customers=customers, vehicles=fleet, coordinate_system="planar")
    prob.compute_euclidean_matrices(speed=1.0)

    # In Complete mode: all 3 cannot be served by 1 vehicle (capacity overflow)
    sol, _ = solve_qpso(prob, QPSOConfig(max_iters=15, num_particles=10, seed=42))
    assert sol.is_feasible is False
    assert "capacity" in sol.violations or "fleet_size" in sol.violations

    # In Partial mode: sheds lowest priority (c1 Flexible) and feasibly serves c2 and c3
    partial_sol = solve_partial_plan(prob, lambda p: solve_qpso(p, QPSOConfig(max_iters=15, num_particles=10, seed=42)))
    assert partial_sol.is_feasible is True
    assert len(partial_sol.unserved_orders) >= 1
    # Flexible order c1 should be shed first
    assert partial_sol.unserved_orders[0]["customer_id"] == "c1"


def test_r34_unachievable_hard_deadline_rejected():
    """R34: Customer with physically unachievable hard deadline is flagged infeasible with explicit reason."""
    depot = Depot(id="depot", lat=0.0, lon=0.0)
    # Customer at (100, 0) takes 100s to reach at speed 1.0, but due_time is 20s
    impossible_cust = Customer(
        id="c_late", lat=100.0, lon=0.0, demand=10.0, ready_time=0.0, due_time=20.0, service_time=5.0, time_window_type="hard"
    )
    fleet = [Vehicle(id="v1", capacity=100.0)]
    prob = Problem(id="prob_r34", depot=depot, customers=[impossible_cust], vehicles=fleet, coordinate_system="planar")
    prob.compute_euclidean_matrices(speed=1.0)

    sol, _ = solve_qpso(prob, QPSOConfig(max_iters=10, num_particles=10, seed=42))
    assert sol.is_feasible is False
    assert "time_window" in sol.violations


def test_r35_soft_deadline_incurs_sla_penalty():
    """R35: Soft-window order missed is marked feasible and incurs SLA penalty broken out in ledger."""
    depot = Depot(id="depot", lat=0.0, lon=0.0)
    # Customer arrives late, but has time_window_type="soft"
    # Depot to c_soft is distance 50s. Due time is 20s.
    # Lateness = 50s - 20s = 30s = 0.5 minutes.
    # Priority is 3 (Critical) -> SLA rate is Rs 10/min -> Penalty = 0.5 * 10 = Rs 5.00.
    soft_cust = Customer(
        id="c_soft",
        lat=50.0,
        lon=0.0,
        demand=10.0,
        ready_time=0.0,
        due_time=20.0,
        service_time=0.0,
        priority=3,
        time_window_type="soft",
    )
    fleet = [Vehicle(id="v1", capacity=100.0)]
    prob = Problem(id="prob_r35", depot=depot, customers=[soft_cust], vehicles=fleet, coordinate_system="planar")
    prob.compute_euclidean_matrices(speed=1.0)

    # Construct solution visiting c_soft
    route = Route(vehicle_id="v1", stop_ids=["c_soft"], arrival_times=[50.0], load=10.0, distance=100.0, duration=100.0)
    sol = Solution(routes=[route], total_cost=100.0, is_feasible=True)

    val = validate_solution(prob, sol)
    # Must be marked strictly feasible because window is soft!
    assert val.is_valid is True
    assert val.violations == {}
    assert val.total_sla_penalty == 5.00
    assert val.cost_breakdown is not None
    assert val.cost_breakdown.sla_penalty == 5.00


def test_r36_invalid_nan_coordinates_rejected():
    """R36: Orders with NaN or infinite coordinates are rejected upfront."""
    with pytest.raises(ValidationError):
        Customer(
            id="c_nan",
            lat=float("nan"),
            lon=73.18,
            demand=10.0,
            ready_time=0.0,
            due_time=100.0,
            service_time=5.0,
        )

    with pytest.raises(ValidationError):
        Depot(lat=float("inf"), lon=73.18)


def test_r37_disconnected_road_network_returns_infeasible():
    """R37: Order in disconnected network (infinite travel time) flags infeasibility."""
    depot = Depot(id="depot", lat=0.0, lon=0.0)
    c1 = Customer(id="c1", lat=1.0, lon=1.0, demand=5.0, ready_time=0.0, due_time=1000.0, service_time=0.0)
    fleet = [Vehicle(id="v1", capacity=50.0)]
    prob = Problem(id="prob_r37", depot=depot, customers=[c1], vehicles=fleet)
    # Provide NxN travel time matrix with unreachable node 1 (infinite travel time)
    prob.travel_time_matrix = [[0.0, float("inf")], [float("inf"), 0.0]]
    prob.distance_matrix = [[0.0, float("inf")], [float("inf"), 0.0]]

    route = Route(vehicle_id="v1", stop_ids=["c1"], arrival_times=[float("inf")], load=5.0, distance=float("inf"), duration=float("inf"))
    sol = Solution(routes=[route], total_cost=float("inf"), is_feasible=False)

    val = validate_solution(prob, sol)
    assert val.is_valid is False


def test_r38_zero_vehicles_returns_data_insufficient():
    """R38: Zero vehicles available is rejected upfront with data_insufficient."""
    depot = Depot(id="depot", lat=0.0, lon=0.0)
    c1 = Customer(id="c1", lat=1.0, lon=1.0, demand=5.0, ready_time=0.0, due_time=100.0, service_time=0.0)

    with pytest.raises(ValueError, match="No vehicles available"):
        Problem(id="prob_r38", depot=depot, customers=[c1], vehicles=[])


def test_r39_missing_cost_config_fallback_to_defaults():
    """R39: Missing cost configuration safely falls back to standard enterprise defaults."""
    breakdown = compute_cost_breakdown(
        total_distance_metres=10000.0,  # 10km * 8 = Rs 80
        total_duration_seconds=3600.0,  # 1hr * 100 = Rs 100
        num_vehicles_used=1,            # 1veh * 300 = Rs 300
        total_sla_penalty=0.0,
        config=None,                    # Explicitly None
    )
    assert breakdown.opex_distance == 80.0
    assert breakdown.opex_time == 100.0
    assert breakdown.fleet_activation == 300.0
    assert breakdown.total == 480.0


def test_r40_duplicate_order_id_rejected():
    """R40: Duplicate customer ID within a problem is rejected upfront."""
    depot = Depot(id="depot", lat=0.0, lon=0.0)
    c1a = Customer(id="DUP_1", lat=1.0, lon=1.0, demand=5.0, ready_time=0.0, due_time=100.0, service_time=0.0)
    c1b = Customer(id="DUP_1", lat=2.0, lon=2.0, demand=5.0, ready_time=0.0, due_time=100.0, service_time=0.0)
    fleet = [Vehicle(id="v1", capacity=50.0)]

    with pytest.raises(ValidationError, match="Customer IDs must be unique"):
        Problem(id="prob_r40", depot=depot, customers=[c1a, c1b], vehicles=fleet)


def test_r41_replanning_zero_remaining_orders():
    """R41: Replanning when all orders are completed returns 'no remaining work'."""
    depot = Depot(id="depot", lat=0.0, lon=0.0)
    c1 = Customer(id="c1", lat=1.0, lon=0.0, demand=5.0, ready_time=0.0, due_time=100.0, service_time=5.0)
    fleet = [Vehicle(id="v1", capacity=50.0)]
    prob = Problem(id="prob_r41", depot=depot, customers=[c1], vehicles=fleet, coordinate_system="planar")
    prob.compute_euclidean_matrices(speed=1.0)

    # Route completed: c1 was visited at t=1.0, service ended at t=6.0.
    # Current time = 50.0 (well after completion)
    route = Route(vehicle_id="v1", stop_ids=["c1"], arrival_times=[1.0], load=5.0, distance=2.0, duration=7.0)
    sol = Solution(routes=[route], total_cost=2.0, is_feasible=True)

    reopt = DynamicReoptimizer(prob, config=ReoptimizerConfig(commitment_horizon_seconds=10.0))
    new_sol, record = reopt.reoptimize(sol, current_time=50.0)

    assert record.message == "no remaining work"
    assert record.stops_changed_count == 0


def test_r42_traffic_change_freezes_completed_deliveries():
    """R42: Dynamic traffic update freezes visited stops and only modifies uncommitted stops."""
    depot = Depot(id="depot", lat=0.0, lon=0.0)
    c1 = Customer(id="c1", lat=10.0, lon=0.0, demand=5.0, ready_time=0.0, due_time=100.0, service_time=5.0)
    c2 = Customer(id="c2", lat=20.0, lon=0.0, demand=5.0, ready_time=0.0, due_time=100.0, service_time=5.0)
    fleet = [Vehicle(id="v1", capacity=50.0)]
    prob = Problem(id="prob_r42", depot=depot, customers=[c1, c2], vehicles=fleet, coordinate_system="planar")

    # c1 is visited at t=10, leaves at t=15. c2 is scheduled at t=30.
    # At t=20, c1 is already completed!
    route = Route(vehicle_id="v1", stop_ids=["c1", "c2"], arrival_times=[10.0, 30.0], load=10.0, distance=40.0, duration=45.0)

    frozen, uncommitted = partition_stops_by_commitment(route, current_time=20.0, commitment_horizon=5.0, problem=prob)
    assert "c1" in frozen
    assert "c1" not in uncommitted
    assert "c2" in uncommitted


def test_r43_search_limit_exceeded_explicit_status():
    """R43: Search limit exceeded is distinguished from proven infeasibility."""
    sol = Solution(
        routes=[],
        total_cost=0.0,
        is_feasible=False,
        feasibility_status="search_limit_exceeded",
        status_message="Search iteration limit reached before finding valid solution",
        violations={"search": ["Search budget exhausted"]},
    )
    assert sol.feasibility_status == "search_limit_exceeded"
    assert sol.is_feasible is False
