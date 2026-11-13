"""Tests for the Enterprise Financial Cost Model (R9, R21-R27, AC-10)."""

import pytest

from solver.cost import BusinessCostConfig, compute_cost_breakdown
from solver.models import Customer, Depot, Problem, Route, Solution, Vehicle
from solver.validate import validate_solution


def test_hand_computed_cost_ledger_ac10():
    """Verify hand-computed cost ledger against AC-10 specification.

    Specification example:
    - Distance: 50.0 km @ Rs 8/km = Rs 400.00
    - Duration: 3.0 hours (10,800s) @ Rs 100/hr = Rs 300.00
    - Fleet: 2 active vehicles @ Rs 300/veh = Rs 600.00
    - SLA Penalty: 15 min Critical delay @ Rs 10/min = Rs 150.00
    - Total: 400 + 300 + 600 + 150 = Rs 1450.00
    Tolerance: within 0.01 INR.
    """
    config = BusinessCostConfig(
        cost_per_km=8.0,
        cost_per_hour=100.0,
        vehicle_activation_cost=300.0,
        sla_penalty_per_min={"critical": 10.0, "standard": 5.0, "flexible": 2.0},
    )

    breakdown = compute_cost_breakdown(
        total_distance_metres=50000.0,
        total_duration_seconds=10800.0,
        num_vehicles_used=2,
        total_sla_penalty=150.0,
        config=config,
    )

    assert pytest.approx(breakdown.opex_distance, abs=0.01) == 400.00
    assert pytest.approx(breakdown.opex_time, abs=0.01) == 300.00
    assert pytest.approx(breakdown.fleet_activation, abs=0.01) == 600.00
    assert pytest.approx(breakdown.sla_penalty, abs=0.01) == 150.00
    assert pytest.approx(breakdown.total, abs=0.01) == 1450.00


def test_cost_breakdown_with_custom_enterprise_rates():
    """Verify that custom rates override default constants accurately."""
    custom_cfg = BusinessCostConfig(
        cost_per_km=12.5,
        cost_per_hour=150.0,
        vehicle_activation_cost=500.0,
        sla_penalty_per_min={"critical": 25.0, "standard": 10.0, "flexible": 5.0},
    )

    # 100 km, 4 hours, 3 vehicles, 20 mins flexible lateness (20 * 5 = Rs 100)
    breakdown = compute_cost_breakdown(
        total_distance_metres=100000.0,
        total_duration_seconds=14400.0,
        num_vehicles_used=3,
        total_sla_penalty=100.0,
        config=custom_cfg,
    )

    assert breakdown.opex_distance == 1250.00  # 100 * 12.5
    assert breakdown.opex_time == 600.00       # 4 * 150.0
    assert breakdown.fleet_activation == 1500.00 # 3 * 500.0
    assert breakdown.sla_penalty == 100.00
    assert breakdown.total == 3450.00
