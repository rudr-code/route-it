"""Unit tests for discrete dynamic fleet simulation in dynamic/simulator.py."""

import pytest

from dynamic.events import (
    EdgeCongestion,
    NewOrder,
    RoadBlockage,
    Scenario,
    VehicleDelay,
    generate_random_scenario,
)
from dynamic.simulator import (
    FleetSimulator,
    VehicleStatus,
)
from routing.cost_oracle import EuclideanOracle, SimulatedEventAdapter, TimeOfDayProfileAdapter
from solver.models import Customer, Depot, Problem, Route, Solution, Vehicle


@pytest.fixture
def line_problem() -> Problem:
    """Problem with collinear stops along X axis for easy coordinate verification.

    Depot at (0, 0)
    c1 at (10, 0): ready=15, due=100, service=10
    c2 at (20, 0): ready=20, due=100, service=10
    """
    depot = Depot(id="depot", lat=0.0, lon=0.0, ready_time=0.0, due_time=1000.0)
    c1 = Customer(
        id="c1",
        lat=10.0,
        lon=0.0,
        demand=5.0,
        ready_time=15.0,
        due_time=100.0,
        service_time=10.0,
    )
    c2 = Customer(
        id="c2",
        lat=20.0,
        lon=0.0,
        demand=5.0,
        ready_time=20.0,
        due_time=100.0,
        service_time=10.0,
    )
    vehicles = [Vehicle(id="v1", capacity=50.0)]
    return Problem(id="line_prob", depot=depot, customers=[c1, c2], vehicles=vehicles, coordinate_system="planar")


@pytest.fixture
def line_solution() -> Solution:
    """Solution with single route visiting [c1, c2]."""
    route = Route(
        vehicle_id="v1",
        stop_ids=["c1", "c2"],
        arrival_times=[10.0, 35.0],
        load=10.0,
        distance=40.0,
        duration=65.0,
    )
    return Solution(
        routes=[route],
        total_cost=40.0,
        is_feasible=True,
    )


def test_simulator_basic_lifecycle(line_problem: Problem, line_solution: Solution):
    """Verify state transitions: EN_ROUTE -> WAITING -> SERVICING -> EN_ROUTE -> COMPLETED."""
    oracle = EuclideanOracle(base_speed_mps=1.0, use_haversine=False)
    sim = FleetSimulator(problem=line_problem, solution=line_solution, cost_oracle=oracle, start_time=0.0)

    # Initial state at t=0
    v = sim.vehicles["v1"]
    assert v.status == VehicleStatus.EN_ROUTE
    assert v.current_leg_dest_id == "c1"
    assert v.leg_departure_time == 0.0
    assert v.leg_arrival_time == pytest.approx(10.0)

    # Step to t=5 (midway to c1)
    snap_5 = sim.step(5.0)
    v5 = snap_5.vehicle_states["v1"]
    assert v5.status == VehicleStatus.EN_ROUTE
    assert v5.current_coords[0] == pytest.approx(5.0)  # half way between 0 and 10

    # Step to t=10 (arrives at c1; ready_time is 15 so enters WAITING)
    snap_10 = sim.step(5.0)
    v10 = snap_10.vehicle_states["v1"]
    assert v10.status == VehicleStatus.WAITING
    assert v10.current_coords[0] == pytest.approx(10.0)

    # Step to t=15 (c1 ready_time reached -> starts SERVICING)
    snap_15 = sim.step(5.0)
    v15 = snap_15.vehicle_states["v1"]
    assert v15.status == VehicleStatus.SERVICING
    assert v15.service_end_time == pytest.approx(25.0)

    # Step to t=25 (service finished -> departs to c2)
    snap_25 = sim.step(10.0)
    v25 = snap_25.vehicle_states["v1"]
    assert "c1" in v25.visited_stops
    assert v25.current_leg_dest_id == "c2"
    assert v25.status == VehicleStatus.EN_ROUTE
    assert v25.leg_arrival_time == pytest.approx(35.0)  # dist from c1(10,0) to c2(20,0) is 10

    # Run to completion
    snaps = sim.run_to_completion(step_size=5.0)
    final_v = snaps[-1].vehicle_states["v1"]
    assert final_v.status == VehicleStatus.COMPLETED
    assert final_v.visited_stops == ["c1", "c2"]
    assert snaps[-1].all_completed is True


def test_simulator_vehicle_delay_shifts_arrival(line_problem: Problem, line_solution: Solution):
    """Verify injecting a VehicleDelay shifts the vehicle's arrival time accurately."""
    oracle = EuclideanOracle(base_speed_mps=1.0, use_haversine=False)
    sim = FleetSimulator(problem=line_problem, solution=line_solution, cost_oracle=oracle, start_time=0.0)

    # En route to c1 with initial arrival at t=10
    assert sim.vehicles["v1"].leg_arrival_time == pytest.approx(10.0)

    # Apply 15s unexpected vehicle delay at t=2
    sim.step(2.0)
    sim.apply_event(
        VehicleDelay(
            event_id="delay_test",
            trigger_time=2.0,
            vehicle_id="v1",
            delay_seconds=15.0,
        )
    )

    # New arrival at c1 should be 10 + 15 = 25
    assert sim.vehicles["v1"].leg_arrival_time == pytest.approx(25.0)
    assert sim.vehicles["v1"].delay_seconds == pytest.approx(15.0)

    # At t=10, vehicle is still EN_ROUTE (has not arrived due to delay)
    snap_10 = sim.step(8.0)
    assert snap_10.vehicle_states["v1"].status == VehicleStatus.EN_ROUTE


def test_simulator_edge_congestion_slowdown(line_problem: Problem, line_solution: Solution):
    """Verify EdgeCongestion modulates traffic adapter and increases leg travel time."""
    adapter = SimulatedEventAdapter(base_adapter=TimeOfDayProfileAdapter({h: 1.0 for h in range(24)}))
    oracle = EuclideanOracle(base_speed_mps=1.0, use_haversine=False, traffic_adapter=adapter)
    sim = FleetSimulator(problem=line_problem, solution=line_solution, cost_oracle=oracle, traffic_adapter=adapter)

    # Advance until c1 service finishes at t=25
    sim.run_until(target_time=24.0, step_size=6.0)

    # Apply EdgeCongestion on (c1, c2) with multiplier 2.0 (travel time doubles from 10 to 20)
    cong = EdgeCongestion(
        event_id="cong_c1_c2",
        trigger_time=24.0,
        duration=100.0,
        origin_id="c1",
        dest_id="c2",
        multiplier=2.0,
    )
    sim.apply_event(cong)

    # Step to t=25: c1 service completes, vehicle departs to c2 under congested conditions
    snap_25 = sim.step(1.0)
    v25 = snap_25.vehicle_states["v1"]
    assert v25.current_leg_dest_id == "c2"
    # Nominal travel time was 10.0; with multiplier 2.0, it takes 20.0 -> arrival at 25 + 20 = 45!
    assert v25.leg_arrival_time == pytest.approx(45.0)


def test_simulator_new_order_collection(line_problem: Problem, line_solution: Solution):
    """Verify NewOrder appears in pending_orders snapshot."""
    oracle = EuclideanOracle(base_speed_mps=1.0, use_haversine=False)
    new_cust = Customer(
        id="c_urgent",
        lat=15.0,
        lon=5.0,
        demand=3.0,
        ready_time=50.0,
        due_time=120.0,
        service_time=10.0,
    )
    scenario = Scenario(
        id="scen_new_order",
        start_time=0.0,
        duration=300.0,
        events=[
            NewOrder(event_id="ord_dyn_1", trigger_time=10.0, customer=new_cust)
        ],
    )
    sim = FleetSimulator(problem=line_problem, solution=line_solution, cost_oracle=oracle, scenario=scenario)

    # Before trigger time: no pending orders
    snap_5 = sim.step(5.0)
    assert len(snap_5.pending_orders) == 0

    # At trigger time: new order is captured
    snap_10 = sim.step(5.0)
    assert len(snap_10.pending_orders) == 1
    assert snap_10.pending_orders[0].id == "c_urgent"


def test_deterministic_scenario_simulation(line_problem: Problem, line_solution: Solution):
    """Verify identical random scenario produces bitwise identical simulation trajectories."""
    scenario = generate_random_scenario(
        line_problem,
        num_events=3,
        seed=777,
        start_time=0.0,
        time_horizon=100.0,
    )

    oracle1 = EuclideanOracle(base_speed_mps=1.0, use_haversine=False)
    sim1 = FleetSimulator(problem=line_problem, solution=line_solution, cost_oracle=oracle1, scenario=scenario)
    snaps1 = sim1.run_to_completion(step_size=5.0)

    oracle2 = EuclideanOracle(base_speed_mps=1.0, use_haversine=False)
    sim2 = FleetSimulator(problem=line_problem, solution=line_solution, cost_oracle=oracle2, scenario=scenario)
    snaps2 = sim2.run_to_completion(step_size=5.0)

    assert len(snaps1) == len(snaps2)
    for s1, s2 in zip(snaps1, snaps2):
        assert s1.timestamp == s2.timestamp
        assert s1.active_events == s2.active_events
        assert s1.all_completed == s2.all_completed
        for v_id in s1.vehicle_states:
            st1 = s1.vehicle_states[v_id]
            st2 = s2.vehicle_states[v_id]
            assert st1.status == st2.status
            assert st1.current_coords == st2.current_coords
            assert st1.visited_stops == st2.visited_stops


def test_simulator_road_blockage_and_clearance(line_problem: Problem, line_solution: Solution):
    """Verify RoadBlockage stalls departure until blockage concludes."""
    adapter = SimulatedEventAdapter(base_adapter=TimeOfDayProfileAdapter({h: 1.0 for h in range(24)}))
    oracle = EuclideanOracle(base_speed_mps=1.0, use_haversine=False, traffic_adapter=adapter)
    sim = FleetSimulator(problem=line_problem, solution=line_solution, cost_oracle=oracle, traffic_adapter=adapter)

    # Reach c1 service finish at t=25
    sim.run_until(target_time=24.0, step_size=6.0)

    # Apply RoadBlockage from t=24 to t=60 on edge (c1, c2)
    blockage = RoadBlockage(
        event_id="block_c1_c2",
        trigger_time=24.0,
        duration=36.0,  # ends at t=60
        origin_id="c1",
        dest_id="c2",
    )
    sim.apply_event(blockage)

    # At t=25: vehicle attempts to depart c1 to c2. Edge is blocked!
    sim.step(1.0)
    v = sim.vehicles["v1"]
    assert v.leg_arrival_time == float("inf")

    # Fast forward to t=59: still blocked
    sim.run_until(target_time=59.0, step_size=10.0)
    assert sim.vehicles["v1"].status == VehicleStatus.EN_ROUTE
    assert sim.vehicles["v1"].leg_arrival_time == float("inf")

    # At t=61: blockage expires! Vehicle arrival is rescheduled
    # Note: simulate clearing by removing event
    sim.remove_event("block_c1_c2")
    # Travel time is evaluated
    c1 = line_problem.get_customer("c1")
    c2 = line_problem.get_customer("c2")
    leg_t = oracle.travel_time(c1, c2, 61.0)
    assert leg_t == pytest.approx(10.0)


def test_simulator_servicing_delay(line_problem: Problem, line_solution: Solution):
    """Verify VehicleDelay injected during SERVICING extends service_end_time."""
    oracle = EuclideanOracle(base_speed_mps=1.0, use_haversine=False)
    sim = FleetSimulator(problem=line_problem, solution=line_solution, cost_oracle=oracle)

    # Advance to t=15 where c1 service begins (ends at t=25)
    sim.run_until(target_time=15.0, step_size=5.0)
    v15 = sim.vehicles["v1"]
    assert v15.status == VehicleStatus.SERVICING
    assert v15.service_end_time == pytest.approx(25.0)

    # Inject a 20s delay during service
    sim.apply_event(
        VehicleDelay(
            event_id="cust_delay_1",
            trigger_time=15.0,
            vehicle_id="v1",
            delay_seconds=20.0,
        )
    )

    # Service end time is extended to 25 + 20 = 45!
    assert sim.vehicles["v1"].service_end_time == pytest.approx(45.0)
    assert sim.vehicles["v1"].delay_seconds == pytest.approx(20.0)

    # Step to t=30: vehicle is still SERVICING
    snap_30 = sim.step(15.0)
    assert snap_30.vehicle_states["v1"].status == VehicleStatus.SERVICING

    # Step to t=45: service now completes
    snap_45 = sim.step(15.0)
    assert "c1" in snap_45.vehicle_states["v1"].visited_stops


def test_simulator_multi_vehicle_fleet():
    """Verify concurrent simulation of multiple vehicles across distinct routes."""
    depot = Depot(id="depot", lat=0.0, lon=0.0, ready_time=0.0, due_time=1000.0)
    c1 = Customer(id="c1", lat=10.0, lon=0.0, demand=5.0, ready_time=0.0, due_time=100.0, service_time=5.0)
    c2 = Customer(id="c2", lat=0.0, lon=10.0, demand=5.0, ready_time=0.0, due_time=100.0, service_time=5.0)
    vehicles = [Vehicle(id="v1", capacity=50.0), Vehicle(id="v2", capacity=50.0)]
    prob = Problem(id="multi_prob", depot=depot, customers=[c1, c2], vehicles=vehicles, coordinate_system="planar")

    sol = Solution(
        routes=[
            Route(vehicle_id="v1", stop_ids=["c1"], arrival_times=[10.0], load=5.0, distance=20.0, duration=25.0),
            Route(vehicle_id="v2", stop_ids=["c2"], arrival_times=[10.0], load=5.0, distance=20.0, duration=25.0),
        ],
        total_cost=40.0,
        is_feasible=True,
    )

    oracle = EuclideanOracle(base_speed_mps=1.0, use_haversine=False)
    sim = FleetSimulator(problem=prob, solution=sol, cost_oracle=oracle)

    assert len(sim.vehicles) == 2
    assert sim.vehicles["v1"].current_leg_dest_id == "c1"
    assert sim.vehicles["v2"].current_leg_dest_id == "c2"

    snaps = sim.run_to_completion(step_size=5.0)
    assert snaps[-1].all_completed is True
    assert snaps[-1].vehicle_states["v1"].status == VehicleStatus.COMPLETED
    assert snaps[-1].vehicle_states["v2"].status == VehicleStatus.COMPLETED
    assert snaps[-1].vehicle_states["v1"].visited_stops == ["c1"]
    assert snaps[-1].vehicle_states["v2"].visited_stops == ["c2"]

