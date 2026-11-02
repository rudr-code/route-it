"""Unit tests for Route.it domain models in solver/models.py."""

import pytest
from pydantic import ValidationError

from solver.models import Customer, Depot, Problem, Route, Solution, Vehicle


def test_depot_creation() -> None:
    """Test valid depot initialization and default properties."""
    depot = Depot(id="main_depot", lat=12.9716, lon=77.5946, ready_time=0.0, due_time=1000.0)
    assert depot.id == "main_depot"
    assert depot.lat == 12.9716
    assert depot.lon == 77.5946
    assert depot.ready_time == 0.0
    assert depot.due_time == 1000.0
    assert depot.service_time == 0.0


def test_depot_negative_due_time() -> None:
    """Test depot rejects negative due time."""
    with pytest.raises(ValidationError):
        Depot(lat=0.0, lon=0.0, due_time=-10.0)


def test_customer_creation_and_time_window_validation() -> None:
    """Test customer creation and rejection of invalid time windows."""
    cust = Customer(
        id="C1",
        lat=12.95,
        lon=77.60,
        demand=15.0,
        ready_time=10.0,
        due_time=50.0,
        service_time=5.0,
        priority=2,
    )
    assert cust.id == "C1"
    assert cust.priority == 2
    assert cust.demand == 15.0

    # Inverted time window: ready_time > due_time
    with pytest.raises(ValidationError, match="cannot exceed due_time"):
        Customer(
            id="C2",
            lat=12.95,
            lon=77.60,
            demand=10.0,
            ready_time=60.0,
            due_time=50.0,
            service_time=5.0,
        )


def test_vehicle_creation_and_constraints() -> None:
    """Test vehicle creation and capacity / shift constraint validation."""
    v = Vehicle(id="V1", capacity=100.0, shift_start=0.0, shift_end=480.0)
    assert v.capacity == 100.0
    assert v.shift_end == 480.0

    # Non-positive capacity
    with pytest.raises(ValidationError):
        Vehicle(id="V2", capacity=0.0)

    # Inverted shift window
    with pytest.raises(ValidationError, match="cannot exceed shift_end"):
        Vehicle(id="V3", capacity=50.0, shift_start=500.0, shift_end=200.0)


def test_problem_uniqueness_and_lookups() -> None:
    """Test Problem instance validation for unique IDs and lookup helpers."""
    depot = Depot(lat=0.0, lon=0.0)
    c1 = Customer(id="1", lat=3.0, lon=4.0, demand=10.0, ready_time=0.0, due_time=100.0, service_time=5.0)
    c2 = Customer(id="2", lat=6.0, lon=8.0, demand=20.0, ready_time=0.0, due_time=100.0, service_time=5.0)
    v1 = Vehicle(id="V1", capacity=50.0)

    prob = Problem(id="toy_prob", depot=depot, customers=[c1, c2], vehicles=[v1])
    assert prob.num_customers == 2
    assert prob.num_vehicles == 1
    assert prob.get_customer("1").demand == 10.0
    assert prob.get_customer_index("1") == 1
    assert prob.get_customer_index("2") == 2

    with pytest.raises(KeyError):
        prob.get_customer("999")

    # Duplicate customer IDs should be rejected
    with pytest.raises(ValidationError, match="Customer IDs must be unique"):
        Problem(id="dup", depot=depot, customers=[c1, c1], vehicles=[v1])


def test_problem_euclidean_matrices() -> None:
    """Test calculation of Euclidean distance and travel-time matrices."""
    depot = Depot(lat=0.0, lon=0.0)
    # 3-4-5 right triangle from depot (0,0) to customer (3,4)
    c1 = Customer(id="1", lat=3.0, lon=4.0, demand=10.0, ready_time=0.0, due_time=100.0, service_time=0.0)
    v1 = Vehicle(id="V1", capacity=50.0)

    prob = Problem(id="geom_prob", depot=depot, customers=[c1], vehicles=[v1], coordinate_system="planar")
    assert prob.distance_matrix is None

    prob.compute_euclidean_matrices(speed=2.0)
    assert prob.distance_matrix is not None
    assert prob.travel_time_matrix is not None

    # Distance depot (0) to c1 (1) is 5.0
    assert pytest.approx(prob.distance_matrix[0][1], rel=1e-5) == 5.0
    assert pytest.approx(prob.distance_matrix[1][0], rel=1e-5) == 5.0
    # Travel time with speed=2.0 is 5.0 / 2.0 = 2.5
    assert pytest.approx(prob.travel_time_matrix[0][1], rel=1e-5) == 2.5


def test_route_and_solution_creation() -> None:
    """Test Route and Solution model serialization."""
    route1 = Route(
        vehicle_id="V1",
        stop_ids=["1", "2"],
        arrival_times=[10.0, 25.0],
        load=30.0,
        distance=15.0,
        duration=35.0,
    )
    solution = Solution(
        routes=[route1],
        total_cost=50.0,
        is_feasible=True,
        violations={},
        algorithm="QPSO",
        execution_time_sec=0.123,
        seed=42,
    )
    assert solution.is_feasible is True
    assert len(solution.routes) == 1
    assert solution.routes[0].load == 30.0

    # Verify JSON serialization & deserialization
    json_str = solution.model_dump_json()
    reloaded = Solution.model_validate_json(json_str)
    assert reloaded.total_cost == 50.0
    assert reloaded.routes[0].stop_ids == ["1", "2"]
