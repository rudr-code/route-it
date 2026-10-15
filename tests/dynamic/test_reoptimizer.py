"""Unit tests for Dynamic Route Re-optimizer in dynamic/reoptimizer.py."""

import pytest

from dynamic.events import EdgeCongestion, RoadBlockage, VehicleDelay
from dynamic.reoptimizer import (
    DynamicReoptimizer,
    ReoptimizationTier,
    ReoptimizerConfig,
    calculate_stability_penalty,
    full_restart_baseline,
    partition_stops_by_commitment,
)
from routing.cost_oracle import EuclideanOracle, SimulatedEventAdapter, TimeOfDayProfileAdapter
from solver.models import Customer, Depot, Problem, Route, Solution, Vehicle
from solver.validate import validate_solution


@pytest.fixture
def test_fleet_problem() -> Problem:
    """Problem with 4 customers and 2 vehicles for testing re-optimization tiers."""
    depot = Depot(id="depot", lat=0.0, lon=0.0, ready_time=0.0, due_time=1000.0)
    c1 = Customer(id="c1", lat=10.0, lon=0.0, demand=5.0, ready_time=10.0, due_time=100.0, service_time=10.0)
    c2 = Customer(id="c2", lat=20.0, lon=0.0, demand=5.0, ready_time=20.0, due_time=100.0, service_time=10.0)
    c3 = Customer(id="c3", lat=0.0, lon=10.0, demand=5.0, ready_time=10.0, due_time=100.0, service_time=10.0)
    c4 = Customer(id="c4", lat=0.0, lon=20.0, demand=5.0, ready_time=20.0, due_time=100.0, service_time=10.0)
    vehicles = [Vehicle(id="v1", capacity=30.0), Vehicle(id="v2", capacity=30.0)]
    return Problem(id="reopt_prob", depot=depot, customers=[c1, c2, c3, c4], vehicles=vehicles)


@pytest.fixture
def initial_fleet_solution() -> Solution:
    """Initial solution: v1 -> [c1, c2], v2 -> [c3, c4]."""
    r1 = Route(
        vehicle_id="v1",
        stop_ids=["c1", "c2"],
        arrival_times=[10.0, 30.0],
        load=10.0,
        distance=40.0,
        duration=60.0,
    )
    r2 = Route(
        vehicle_id="v2",
        stop_ids=["c3", "c4"],
        arrival_times=[10.0, 30.0],
        load=10.0,
        distance=40.0,
        duration=60.0,
    )
    return Solution(
        routes=[r1, r2],
        total_cost=200.0,
        is_feasible=True,
    )


def test_partition_stops_by_commitment(test_fleet_problem: Problem):
    """Verify partition into frozen vs uncommitted based on simulation time and commitment window."""
    r1 = Route(
        vehicle_id="v1",
        stop_ids=["c1", "c2"],
        arrival_times=[10.0, 50.0],
        load=10.0,
        distance=40.0,
        duration=70.0,
    )
    # At t=25: c1 completed (10 + 10 = 20 <= 25) -> frozen
    # c2 arrives at 50, with commitment_horizon=15 (50 - 25 = 25 > 15) -> uncommitted
    frozen, uncommitted = partition_stops_by_commitment(
        r1, current_time=25.0, commitment_horizon=15.0, problem=test_fleet_problem
    )
    assert frozen == ["c1"]
    assert uncommitted == ["c2"]

    # At t=25 with larger commitment_horizon=30 (50 - 25 = 25 <= 30) -> c2 committed/frozen
    frozen2, uncommitted2 = partition_stops_by_commitment(
        r1, current_time=25.0, commitment_horizon=30.0, problem=test_fleet_problem
    )
    assert frozen2 == ["c1", "c2"]
    assert uncommitted2 == []


def test_stability_penalty_computation(test_fleet_problem: Problem, initial_fleet_solution: Solution):
    """Verify stability penalty penalizes reassignment and order inversions."""
    config = ReoptimizerConfig(lambda_veh=50.0, lambda_order=10.0)

    # 1. No changes
    pen0, changed0 = calculate_stability_penalty(
        initial_fleet_solution, initial_fleet_solution, {"c1", "c2", "c3", "c4"}, config
    )
    assert pen0 == 0.0
    assert changed0 == []

    # 2. Move c2 to v2: v1 -> [c1], v2 -> [c3, c4, c2]
    sol_reassigned = Solution(
        routes=[
            Route(vehicle_id="v1", stop_ids=["c1"], arrival_times=[10.0], load=5.0, distance=20.0, duration=30.0),
            Route(vehicle_id="v2", stop_ids=["c3", "c4", "c2"], arrival_times=[10.0, 30.0, 60.0], load=15.0, distance=70.0, duration=80.0),
        ],
        total_cost=90.0,
        is_feasible=True,
    )
    pen1, changed1 = calculate_stability_penalty(
        initial_fleet_solution, sol_reassigned, {"c1", "c2", "c3", "c4"}, config
    )
    assert pen1 == 50.0  # 1 reassigned * 50.0
    assert "c2" in changed1

    # 3. Invert order on v1: v1 -> [c2, c1], v2 -> [c3, c4]
    sol_inverted = Solution(
        routes=[
            Route(vehicle_id="v1", stop_ids=["c2", "c1"], arrival_times=[20.0, 40.0], load=10.0, distance=50.0, duration=60.0),
            Route(vehicle_id="v2", stop_ids=["c3", "c4"], arrival_times=[10.0, 30.0], load=10.0, distance=40.0, duration=50.0),
        ],
        total_cost=90.0,
        is_feasible=True,
    )
    pen2, changed2 = calculate_stability_penalty(
        initial_fleet_solution, sol_inverted, {"c1", "c2"}, config
    )
    assert pen2 == 10.0  # 1 inversion * 10.0
    assert "c1" in changed2 and "c2" in changed2


def test_impact_check_tolerance_and_blockage(test_fleet_problem: Problem, initial_fleet_solution: Solution):
    """Verify impact check triggers only when threshold theta is exceeded or edge is blocked."""
    adapter = SimulatedEventAdapter(base_adapter=TimeOfDayProfileAdapter({h: 1.0 for h in range(24)}))
    oracle = EuclideanOracle(base_speed_mps=1.0, use_haversine=False, traffic_adapter=adapter)
    reoptimizer = DynamicReoptimizer(
        test_fleet_problem,
        cost_oracle=oracle,
        config=ReoptimizerConfig(theta=0.10, theta_absolute=5.0),
    )

    # Free flow -> Should NOT replan
    should_replan, reason, delta_f, is_blocked = reoptimizer.check_impact(initial_fleet_solution, current_time=0.0)
    assert should_replan is False
    assert is_blocked is False

    # Minor slowdown (multiplier 1.05) -> Should NOT replan
    mild_cong = EdgeCongestion(
        event_id="cong_mild",
        trigger_time=0.0,
        duration=100.0,
        origin_id="c1",
        dest_id="c2",
        multiplier=1.05,
    )
    for inc in mild_cong.to_simulated_incidents():
        adapter.add_incident(inc)

    should_replan_mild, _, delta_f_mild, _ = reoptimizer.check_impact(initial_fleet_solution, current_time=0.0)
    assert should_replan_mild is False

    # Complete road blockage on edge (c1, c2) -> MUST replan immediately
    adapter.clear_incidents()
    block = RoadBlockage(
        event_id="block_c1_c2",
        trigger_time=0.0,
        duration=100.0,
        origin_id="c1",
        dest_id="c2",
    )
    for inc in block.to_simulated_incidents():
        adapter.add_incident(inc)

    should_replan_block, reason_block, _, is_blocked = reoptimizer.check_impact(initial_fleet_solution, current_time=0.0)
    assert should_replan_block is True
    assert is_blocked is True
    assert "blocked" in reason_block.lower()


def test_tier_1_path_repair_acceptance(test_fleet_problem: Problem, initial_fleet_solution: Solution):
    """Verify Tier 1 Path Repair updates schedule while keeping customer sequence intact."""
    adapter = SimulatedEventAdapter(base_adapter=TimeOfDayProfileAdapter({h: 1.0 for h in range(24)}))
    oracle = EuclideanOracle(base_speed_mps=1.0, use_haversine=False, traffic_adapter=adapter)

    # Moderate congestion on depot->c1 that doesn't breach due_time
    cong = EdgeCongestion(
        event_id="cong_depot_c1",
        trigger_time=0.0,
        duration=100.0,
        origin_id="depot",
        dest_id="c1",
        multiplier=2.0,  # travel time doubles from 10 to 20
    )
    for inc in cong.to_simulated_incidents():
        adapter.add_incident(inc)

    reoptimizer = DynamicReoptimizer(
        test_fleet_problem,
        cost_oracle=oracle,
        config=ReoptimizerConfig(theta=0.01, theta_absolute=2.0, commitment_horizon_seconds=0.0),
    )

    reopt_sol, record = reoptimizer.reoptimize(initial_fleet_solution, current_time=0.0, event=cong)
    assert record.tier_selected == ReoptimizationTier.TIER_1_PATH_REPAIR
    assert record.is_feasible is True
    # Stop sequence must be unchanged
    assert reopt_sol.routes[0].stop_ids == ["c1", "c2"]
    assert reopt_sol.routes[1].stop_ids == ["c3", "c4"]
    # Arrival at c1 adjusted to 20.0
    assert reopt_sol.routes[0].arrival_times[0] == pytest.approx(20.0)


def test_tier_2_local_repair_relocate(test_fleet_problem: Problem, initial_fleet_solution: Solution):
    """Verify Tier 2 Local Repair relocates a congested customer to an uncongested vehicle."""
    adapter = SimulatedEventAdapter(base_adapter=TimeOfDayProfileAdapter({h: 1.0 for h in range(24)}))
    oracle = EuclideanOracle(base_speed_mps=1.0, use_haversine=False, traffic_adapter=adapter)

    # Block edge (c1, c2) on v1's route so v1 cannot go from c1 to c2
    block = RoadBlockage(
        event_id="block_c1_c2",
        trigger_time=0.0,
        duration=100.0,
        origin_id="c1",
        dest_id="c2",
    )
    for inc in block.to_simulated_incidents():
        adapter.add_incident(inc)

    reoptimizer = DynamicReoptimizer(
        test_fleet_problem,
        cost_oracle=oracle,
        config=ReoptimizerConfig(theta=0.01, theta_absolute=2.0, commitment_horizon_seconds=0.0),
    )

    reopt_sol, record = reoptimizer.reoptimize(initial_fleet_solution, current_time=0.0, event=block)
    # Tier 1 fails because edge is blocked -> Tier 2 or 3 succeeds
    assert record.tier_selected in (ReoptimizationTier.TIER_2_LOCAL_REPAIR, ReoptimizationTier.TIER_3_QPSO_WARM_START)
    assert record.is_feasible is True

    # Customer c2 was moved away from c1
    r1 = next(r for r in reopt_sol.routes if r.vehicle_id == "v1")
    # Route 1 should not contain c1 followed by c2
    if "c1" in r1.stop_ids and "c2" in r1.stop_ids:
        idx1 = r1.stop_ids.index("c1")
        idx2 = r1.stop_ids.index("c2")
        assert idx2 != idx1 + 1


def test_full_restart_baseline_comparison(test_fleet_problem: Problem, initial_fleet_solution: Solution):
    """Verify full restart baseline produces a feasible solution and can be compared with tiered re-optimizer."""
    adapter = SimulatedEventAdapter(base_adapter=TimeOfDayProfileAdapter({h: 1.0 for h in range(24)}))
    oracle = EuclideanOracle(base_speed_mps=1.0, use_haversine=False, traffic_adapter=adapter)

    cong = EdgeCongestion(
        event_id="cong_test",
        trigger_time=0.0,
        duration=100.0,
        origin_id="c1",
        dest_id="c2",
        multiplier=1.8,
    )
    for inc in cong.to_simulated_incidents():
        adapter.add_incident(inc)

    reoptimizer = DynamicReoptimizer(test_fleet_problem, cost_oracle=oracle)
    tiered_sol, tiered_rec = reoptimizer.reoptimize(initial_fleet_solution, current_time=0.0, event=cong)

    restart_sol, restart_ms = full_restart_baseline(
        problem=test_fleet_problem,
        current_solution=initial_fleet_solution,
        cost_oracle=oracle,
        current_time=0.0,
        max_iters=30,
        particles=15,
    )

    val_tiered = validate_solution(test_fleet_problem, tiered_sol, cost_oracle=oracle)
    val_restart = validate_solution(test_fleet_problem, restart_sol, cost_oracle=oracle)

    assert val_tiered.is_valid is True
    assert val_restart.is_valid is True
    # Tiered should have logged real wall-clock execution time > 0
    assert tiered_rec.wall_clock_time_ms > 0.0
    assert restart_ms > 0.0
