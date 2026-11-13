"""Unified route schedule and time-window evaluation module for Route.it.

Enforces SIH 2026 TD-CVRPTW specification:
- Service start: B_i = max(A_i, ready_time_i)
- Service completion: D_i = B_i + service_time_i
- Departure time: D_i
- Waiting time: max(0, ready_time_i - A_i)
- Hard window: Infeasible if completion D_i > due_time_i
- Soft window: Feasible, lateness L_i = max(0, D_i - due_time_i),
  SLA Penalty = (L_i / 60.0) * rate(priority)
- Boundary is service COMPLETION, not arrival.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Sequence

# Default SLA penalty rates per minute
DEFAULT_SLA_RATES_PER_MIN = {
    "critical": 10.0,   # Priority >= 3
    "standard": 5.0,    # Priority == 2
    "flexible": 2.0,    # Priority <= 1
}


def get_priority_level(priority: int) -> str:
    """Map integer priority (1..5) to SLA category name."""
    if priority >= 3:
        return "critical"
    if priority == 2:
        return "standard"
    return "flexible"


@dataclass
class StopSchedule:
    """Timeline metrics for a single visited stop in a route."""

    stop_id: str
    arrival_time: float
    service_start_time: float
    completion_time: float
    departure_time: float
    wait_time: float
    lateness: float
    is_hard_violation: bool
    sla_penalty: float
    window_type: str = "hard"
    priority: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "stop_id": self.stop_id,
            "arrival_time": round(self.arrival_time, 2),
            "service_start_time": round(self.service_start_time, 2),
            "completion_time": round(self.completion_time, 2),
            "departure_time": round(self.departure_time, 2),
            "wait_time": round(self.wait_time, 2),
            "lateness": round(self.lateness, 2),
            "is_hard_violation": self.is_hard_violation,
            "sla_penalty": round(self.sla_penalty, 2),
            "window_type": self.window_type,
            "priority": self.priority,
        }


@dataclass
class RouteSchedule:
    """Complete schedule evaluation for a single vehicle route."""

    vehicle_id: str
    stops: list[StopSchedule]
    departure_from_depot: float
    depot_return_arrival: float
    total_travel_time: float
    total_distance: float
    total_duration: float
    total_wait_time: float
    total_service_time: float
    total_lateness: float
    total_sla_penalty: float
    hard_time_violations: list[str] = field(default_factory=list)
    is_time_feasible: bool = True


def evaluate_stop_timing(
    prev_departure: float,
    travel_time: float,
    ready_time: float,
    due_time: float,
    service_time: float,
    time_window_type: str = "hard",
    priority: int = 1,
    tolerance: float = 1e-4,
    sla_rates_per_min: dict[str, float] | None = None,
    stop_id: str = "",
) -> StopSchedule:
    """Calculate arrival, service start, completion, lateness, and SLA penalty for a stop."""
    sla_rates = sla_rates_per_min or DEFAULT_SLA_RATES_PER_MIN
    arrival = prev_departure + travel_time
    service_start = max(arrival, ready_time)
    wait_time = max(0.0, ready_time - arrival)
    completion = service_start + service_time
    departure = completion

    lateness = max(0.0, completion - due_time)
    is_hard = (time_window_type.lower() == "hard")

    is_hard_violation = False
    sla_penalty = 0.0

    if lateness > tolerance:
        if is_hard:
            is_hard_violation = True
        else:
            cat = get_priority_level(priority)
            rate_per_min = sla_rates.get(cat, 5.0)
            lateness_mins = lateness / 60.0
            sla_penalty = lateness_mins * rate_per_min

    return StopSchedule(
        stop_id=stop_id,
        arrival_time=arrival,
        service_start_time=service_start,
        completion_time=completion,
        departure_time=departure,
        wait_time=wait_time,
        lateness=lateness,
        is_hard_violation=is_hard_violation,
        sla_penalty=sla_penalty,
        window_type="hard" if is_hard else "soft",
        priority=priority,
    )
