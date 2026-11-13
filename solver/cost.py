"""Business cost configuration and ledger evaluation for Route.it (R9, R21-R27).

Implements SIH 2026 Financial Objective Model:
J = C_OPEX + C_Fleet + C_SLA
- C_OPEX = sum(d_k * r_d) + sum(t_k * r_t)
  d_k: distance in km, r_d: rate per km (default Rs 8.0/km)
  t_k: paid operating duration in hours, r_t: rate per hour (default Rs 100.0/hr)
- C_Fleet = sum(y_k * F_k)
  y_k: 1 if vehicle k is mobilized, F_k: vehicle activation cost (default Rs 300.0/veh)
- C_SLA = sum(p_i * L_i)
  p_i: SLA penalty rate per minute by priority tier (Critical: 10, Standard: 5, Flexible: 2)
  L_i: lateness in minutes = max(0, D_i - b_i) / 60.0
"""

from __future__ import annotations

from typing import Any, Sequence
from pydantic import BaseModel, Field

from solver.models import CostBreakdown, Customer, Problem, Route, Solution


class BusinessCostConfig(BaseModel):
    """User-configurable enterprise business cost parameters (R9, R21, AC-10)."""

    cost_per_km: float = Field(8.0, ge=0.0, description="INR cost per kilometer traveled (r_d)")
    cost_per_hour: float = Field(100.0, ge=0.0, description="INR paid operational cost per driver hour (r_t)")
    vehicle_activation_cost: float = Field(300.0, ge=0.0, description="INR fixed mobilization fee per vehicle (F_k)")
    sla_penalty_per_min: dict[str, float] = Field(
        default_factory=lambda: {
            "critical": 10.0,
            "standard": 5.0,
            "flexible": 2.0,
        },
        description="INR penalty per minute of delivery delay by customer priority tier",
    )


def compute_cost_breakdown(
    total_distance_metres: float,
    total_duration_seconds: float,
    num_vehicles_used: int,
    total_sla_penalty: float = 0.0,
    config: BusinessCostConfig | None = None,
) -> CostBreakdown:
    """Compute exact financial ledger breakdown from physical metrics.

    Args:
        total_distance_metres: Cumulative fleet distance across all routes in metres.
        total_duration_seconds: Cumulative paid duration across all routes in seconds.
        num_vehicles_used: Total number of active vehicles mobilized.
        total_sla_penalty: Precomputed SLA penalty from soft-window customer delays.
        config: Enterprise cost configuration (defaults to standard SIH rates).

    Returns:
        CostBreakdown with itemized OPEX distance, OPEX time, activation, SLA penalty, and total.
    """
    cfg = config or BusinessCostConfig()

    distance_km = total_distance_metres / 1000.0
    duration_hours = total_duration_seconds / 3600.0

    opex_distance = round(distance_km * cfg.cost_per_km, 2)
    opex_time = round(duration_hours * cfg.cost_per_hour, 2)
    fleet_activation = round(num_vehicles_used * cfg.vehicle_activation_cost, 2)
    sla_pen = round(total_sla_penalty, 2)

    total = round(opex_distance + opex_time + fleet_activation + sla_pen, 2)

    return CostBreakdown(
        opex_distance=opex_distance,
        opex_time=opex_time,
        fleet_activation=fleet_activation,
        sla_penalty=sla_pen,
        total=total,
    )
