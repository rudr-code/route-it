"""Unit tests for dynamic events and scenario models in dynamic/events.py."""

from pathlib import Path
import pytest
from pydantic import ValidationError

from dynamic.events import (
    EdgeCongestion,
    NewOrder,
    RoadBlockage,
    Scenario,
    VehicleDelay,
    generate_random_scenario,
)
from routing.cost_oracle import Location, SimulatedEventAdapter, TimeOfDayProfileAdapter
from solver.models import Customer, Depot, Problem, Vehicle


@pytest.fixture
def sample_problem() -> Problem:
    """Provide a standard toy problem for scenario tests."""
    depot = Depot(id="depot", lat=22.30, lon=73.18, ready_time=0.0, due_time=10000.0)
    customers = [
        Customer(
            id=f"c{i}",
            lat=22.30 + 0.01 * i,
            lon=73.18 + 0.01 * i,
            demand=10.0,
            ready_time=100.0 * i,
            due_time=500.0 + 100.0 * i,
            service_time=50.0,
        )
        for i in range(1, 5)
    ]
    vehicles = [Vehicle(id="v1", capacity=100.0), Vehicle(id="v2", capacity=100.0)]
    return Problem(id="toy_test_prob", depot=depot, customers=customers, vehicles=vehicles)


def test_edge_congestion_validation_and_incidents():
    """Verify EdgeCongestion model validation and incident conversion."""
    # Must fail if no spatial scope provided
    with pytest.raises(ValidationError):
        EdgeCongestion(event_id="bad_cong", trigger_time=100.0, duration=300.0, multiplier=2.0)

    # Valid with origin_id and dest_id
    cong = EdgeCongestion(
        event_id="cong_1",
        trigger_time=100.0,
        duration=600.0,
        multiplier=2.5,
        origin_id="c1",
        dest_id="c2",
        description="Heavy bottleneck",
    )
    assert cong.end_time == 700.0
    incidents = cong.to_simulated_incidents()
    assert len(incidents) == 1
    assert incidents[0].event_id == "cong_1"
    assert incidents[0].speed_multiplier == pytest.approx(1.0 / 2.5)
    assert incidents[0].start_time == 100.0
    assert incidents[0].end_time == 700.0
    assert incidents[0].origin_id == "c1"
    assert incidents[0].dest_id == "c2"

    # Edge set conversion
    cong_multi = EdgeCongestion(
        event_id="cong_multi",
        trigger_time=200.0,
        duration=400.0,
        multiplier=2.0,
        edge_set=[("depot", "c1"), ("c1", "c2")],
    )
    inc_multi = cong_multi.to_simulated_incidents()
    assert len(inc_multi) == 2
    assert inc_multi[0].origin_id == "depot"
    assert inc_multi[0].dest_id == "c1"
    assert inc_multi[1].origin_id == "c1"
    assert inc_multi[1].dest_id == "c2"


def test_road_blockage_validation_and_incidents():
    """Verify RoadBlockage creates incidents with speed_multiplier=0.0."""
    with pytest.raises(ValidationError):
        RoadBlockage(event_id="bad_block", trigger_time=50.0, duration=100.0)

    block = RoadBlockage(
        event_id="block_sayaji",
        trigger_time=500.0,
        duration=1200.0,
        center_lat=22.31,
        center_lon=73.19,
        radius_meters=500.0,
        description="Sinkhole",
    )
    assert block.end_time == 1700.0
    incs = block.to_simulated_incidents()
    assert len(incs) == 1
    assert incs[0].speed_multiplier == 0.0
    assert incs[0].radius_meters == 500.0


def test_vehicle_delay_model():
    """Verify VehicleDelay attributes and default duration behavior."""
    delay = VehicleDelay(
        event_id="delay_v1",
        trigger_time=350.0,
        vehicle_id="v1",
        delay_seconds=180.0,
        stop_id="c2",
    )
    assert delay.delay_seconds == 180.0
    assert delay.duration == 180.0
    assert delay.end_time == 530.0


def test_new_order_model():
    """Verify NewOrder dynamic customer model."""
    new_cust = Customer(
        id="c_urg",
        lat=22.32,
        lon=73.20,
        demand=5.0,
        ready_time=400.0,
        due_time=900.0,
        service_time=30.0,
        priority=3,
    )
    order = NewOrder(event_id="order_1", trigger_time=300.0, customer=new_cust)
    assert order.customer.id == "c_urg"
    assert order.customer.priority == 3
    assert order.trigger_time == 300.0


def test_scenario_json_roundtrip(tmp_path: Path):
    """Test scenario serialization and file persistence."""
    events = [
        EdgeCongestion(
            event_id="e1",
            trigger_time=100.0,
            duration=300.0,
            multiplier=2.0,
            origin_id="depot",
            dest_id="c1",
        ),
        RoadBlockage(
            event_id="e2",
            trigger_time=400.0,
            duration=600.0,
            origin_id="c1",
            dest_id="c2",
        ),
        VehicleDelay(
            event_id="e3",
            trigger_time=250.0,
            vehicle_id="v1",
            delay_seconds=120.0,
        ),
        NewOrder(
            event_id="e4",
            trigger_time=300.0,
            customer=Customer(
                id="c_dyn",
                lat=22.31,
                lon=73.19,
                demand=8.0,
                ready_time=350.0,
                due_time=1000.0,
                service_time=40.0,
            ),
        ),
    ]

    scenario = Scenario(
        id="test_scen_1",
        name="Validation Scenario",
        start_time=0.0,
        duration=3600.0,
        events=events,
    )

    # Save to disk
    file_path = tmp_path / "scenario_test.json"
    scenario.save(file_path)
    assert file_path.is_file()

    # Load from disk
    loaded = Scenario.load(file_path)
    assert loaded.id == "test_scen_1"
    assert len(loaded.events) == 4
    assert loaded.events[0].event_type == "edge_congestion"
    assert loaded.events[1].event_type == "road_blockage"
    assert loaded.events[2].event_type == "vehicle_delay"
    assert loaded.events[3].event_type == "new_order"
    assert loaded.events[0].multiplier == 2.0


def test_traffic_adapter_incident_modulation():
    """Verify applying EdgeCongestion to SimulatedEventAdapter changes speed multiplier."""
    base_adapter = TimeOfDayProfileAdapter({0: 1.0})  # 1.0 constant
    adapter = SimulatedEventAdapter(base_adapter=base_adapter)

    loc1 = Location(id="c1", lat=22.30, lon=73.18)
    loc2 = Location(id="c2", lat=22.31, lon=73.19)

    # Free flow before incident
    assert adapter.get_speed_multiplier(loc1, loc2, depart_time=50.0) == 1.0

    # Add EdgeCongestion with multiplier 2.0 (speed 0.5) from t=100 to t=500
    cong = EdgeCongestion(
        event_id="cong_test",
        trigger_time=100.0,
        duration=400.0,
        multiplier=2.0,
        origin_id="c1",
        dest_id="c2",
    )
    for inc in cong.to_simulated_incidents():
        adapter.add_incident(inc)

    # During event: speed should be halved (0.5)
    assert adapter.get_speed_multiplier(loc1, loc2, depart_time=250.0) == pytest.approx(0.5)
    # Different unblocked edge should remain free flow (1.0)
    loc3 = Location(id="c3", lat=22.32, lon=73.20)
    assert adapter.get_speed_multiplier(loc1, loc3, depart_time=250.0) == 1.0

    # After removal: returns to free flow
    for inc in cong.to_simulated_incidents():
        adapter.remove_incident(inc.event_id)
    assert adapter.get_speed_multiplier(loc1, loc2, depart_time=250.0) == 1.0


def test_deterministic_scenario_generator(sample_problem: Problem):
    """Verify generate_random_scenario reproducibility and output structure."""
    scen_a = generate_random_scenario(sample_problem, num_events=6, seed=123)
    scen_b = generate_random_scenario(sample_problem, num_events=6, seed=123)
    scen_c = generate_random_scenario(sample_problem, num_events=6, seed=999)

    # Determinism with same seed
    assert len(scen_a.events) == 6
    assert scen_a.to_json() == scen_b.to_json()

    # Different seeds yield different schedules
    assert scen_a.to_json() != scen_c.to_json()

    # Events must be chronologically ordered
    trigger_times = [e.trigger_time for e in scen_a.events]
    assert trigger_times == sorted(trigger_times)
