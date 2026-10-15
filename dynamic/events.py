"""Dynamic Traffic and Fleet Event Models for Route.it.

Defines event types (EdgeCongestion, RoadBlockage, VehicleDelay, NewOrder),
JSON scenario serialization/deserialization, conversion to SimulatedIncident
for CostOracle TrafficAdapters, and deterministic seeded scenario generation.
"""

from __future__ import annotations

import json
from pathlib import Path
import random
from typing import Annotated, Any, Literal, Union
from pydantic import BaseModel, Field, model_validator

from routing.cost_oracle import SimulatedIncident
from solver.models import Customer, Problem


class DynamicEvent(BaseModel):
    """Base class for all dynamic events occurring in a route execution scenario."""

    event_id: str = Field(..., description="Unique event identifier")
    event_type: str = Field(..., description="Discriminator identifying the event type")
    trigger_time: float = Field(..., ge=0.0, description="Timestamp in seconds when the event occurs")
    duration: float = Field(0.0, ge=0.0, description="Duration in seconds the event remains active")
    description: str = Field("", description="Human-readable description of the incident")

    @property
    def end_time(self) -> float:
        """Timestamp in seconds when the event concludes."""
        return self.trigger_time + self.duration


class EdgeCongestion(DynamicEvent):
    """Congestion on a road edge, corridor, or geographic zone slowing traffic."""

    event_type: Literal["edge_congestion"] = "edge_congestion"
    multiplier: float = Field(
        2.0,
        gt=1.0,
        description="Factor increasing travel time (e.g. 2.0 = travel time doubles, speed halves)",
    )
    origin_id: str | None = Field(None, description="Starting stop ID of affected edge")
    dest_id: str | None = Field(None, description="Ending stop ID of affected edge")
    edge_set: list[tuple[str, str]] | None = Field(
        None,
        description="Optional list of (origin_id, dest_id) pairs affected",
    )
    center_lat: float | None = Field(None, description="Center latitude of congestion zone")
    center_lon: float | None = Field(None, description="Center longitude of congestion zone")
    radius_meters: float | None = Field(None, ge=0.0, description="Radius in metres of affected zone")

    @model_validator(mode="after")
    def validate_spatial_scope(self) -> EdgeCongestion:
        """Ensure at least one spatial scoping parameter is provided."""
        has_od = self.origin_id is not None or self.dest_id is not None
        has_edges = bool(self.edge_set)
        has_geo = (
            self.center_lat is not None
            and self.center_lon is not None
            and self.radius_meters is not None
        )
        if not (has_od or has_edges or has_geo):
            raise ValueError(
                f"EdgeCongestion {self.event_id} must specify origin_id/dest_id, edge_set, or geographic radius"
            )
        return self

    def to_simulated_incidents(self) -> list[SimulatedIncident]:
        """Convert into SimulatedIncident objects for SimulatedEventAdapter."""
        speed_mult = 1.0 / self.multiplier
        incidents: list[SimulatedIncident] = []

        if self.edge_set:
            for idx, (orig, dest) in enumerate(self.edge_set):
                incidents.append(
                    SimulatedIncident(
                        event_id=f"{self.event_id}_edge_{idx}",
                        speed_multiplier=speed_mult,
                        start_time=self.trigger_time,
                        end_time=self.end_time,
                        origin_id=orig,
                        dest_id=dest,
                        description=f"{self.description} [Edge {orig}->{dest}]",
                    )
                )

        if self.origin_id is not None or self.dest_id is not None or self.radius_meters is not None:
            incidents.append(
                SimulatedIncident(
                    event_id=self.event_id,
                    speed_multiplier=speed_mult,
                    start_time=self.trigger_time,
                    end_time=self.end_time,
                    origin_id=self.origin_id,
                    dest_id=self.dest_id,
                    center_lat=self.center_lat,
                    center_lon=self.center_lon,
                    radius_meters=self.radius_meters,
                    description=self.description,
                )
            )

        return incidents


class RoadBlockage(DynamicEvent):
    """Complete obstruction or closure of a road segment or corridor."""

    event_type: Literal["road_blockage"] = "road_blockage"
    origin_id: str | None = Field(None, description="Starting stop ID of blocked corridor")
    dest_id: str | None = Field(None, description="Ending stop ID of blocked corridor")
    edge_set: list[tuple[str, str]] | None = Field(
        None,
        description="Optional list of (origin_id, dest_id) pairs blocked",
    )
    center_lat: float | None = Field(None, description="Center latitude of closed zone")
    center_lon: float | None = Field(None, description="Center longitude of closed zone")
    radius_meters: float | None = Field(None, ge=0.0, description="Radius in metres of closed zone")

    @model_validator(mode="after")
    def validate_spatial_scope(self) -> RoadBlockage:
        """Ensure at least one spatial scoping parameter is provided."""
        has_od = self.origin_id is not None or self.dest_id is not None
        has_edges = bool(self.edge_set)
        has_geo = (
            self.center_lat is not None
            and self.center_lon is not None
            and self.radius_meters is not None
        )
        if not (has_od or has_edges or has_geo):
            raise ValueError(
                f"RoadBlockage {self.event_id} must specify origin_id/dest_id, edge_set, or geographic radius"
            )
        return self

    def to_simulated_incidents(self) -> list[SimulatedIncident]:
        """Convert into SimulatedIncident objects with speed_multiplier=0.0."""
        incidents: list[SimulatedIncident] = []

        if self.edge_set:
            for idx, (orig, dest) in enumerate(self.edge_set):
                incidents.append(
                    SimulatedIncident(
                        event_id=f"{self.event_id}_edge_{idx}",
                        speed_multiplier=0.0,
                        start_time=self.trigger_time,
                        end_time=self.end_time,
                        origin_id=orig,
                        dest_id=dest,
                        description=f"{self.description} [Blocked {orig}->{dest}]",
                    )
                )

        if self.origin_id is not None or self.dest_id is not None or self.radius_meters is not None:
            incidents.append(
                SimulatedIncident(
                    event_id=self.event_id,
                    speed_multiplier=0.0,
                    start_time=self.trigger_time,
                    end_time=self.end_time,
                    origin_id=self.origin_id,
                    dest_id=self.dest_id,
                    center_lat=self.center_lat,
                    center_lon=self.center_lon,
                    radius_meters=self.radius_meters,
                    description=self.description,
                )
            )

        return incidents


class VehicleDelay(DynamicEvent):
    """Sudden delay experienced by a specific vehicle (breakdown, inspection, dwell)."""

    event_type: Literal["vehicle_delay"] = "vehicle_delay"
    vehicle_id: str = Field(..., description="ID of the affected vehicle")
    delay_seconds: float = Field(..., gt=0.0, description="Additional delay incurred in seconds")
    stop_id: str | None = Field(None, description="Optional stop ID where delay occurred")

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        # For VehicleDelay, duration defaults to delay_seconds
        if self.duration == 0.0:
            self.duration = self.delay_seconds


class NewOrder(DynamicEvent):
    """Dynamic on-demand customer order appearing during execution."""

    event_type: Literal["new_order"] = "new_order"
    customer: Customer = Field(..., description="New customer stop specification")


# Discriminated union of all supported dynamic event types
AnyDynamicEvent = Annotated[
    Union[EdgeCongestion, RoadBlockage, VehicleDelay, NewOrder],
    Field(discriminator="event_type"),
]


class Scenario(BaseModel):
    """Complete dynamic scenario containing scheduled events over a time horizon."""

    id: str = Field(..., description="Unique scenario identifier")
    name: str = Field("Route.it Scenario", description="Scenario display name")
    start_time: float = Field(0.0, ge=0.0, description="Simulation start time in seconds")
    duration: float = Field(86400.0, gt=0.0, description="Scenario horizon duration in seconds")
    events: list[AnyDynamicEvent] = Field(default_factory=list, description="Scheduled events")

    @property
    def end_time(self) -> float:
        """Scenario conclusion timestamp."""
        return self.start_time + self.duration

    def to_json(self, indent: int = 2) -> str:
        """Serialize scenario to formatted JSON string."""
        return self.model_dump_json(indent=indent)

    def save(self, path: Path | str) -> None:
        """Write scenario to JSON file."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def from_json(cls, json_str: str) -> Scenario:
        """Load scenario from JSON string."""
        return cls.model_validate_json(json_str)

    @classmethod
    def load(cls, path: Path | str) -> Scenario:
        """Read and parse scenario from JSON file."""
        content = Path(path).read_text(encoding="utf-8")
        return cls.from_json(content)


def generate_random_scenario(
    problem: Problem,
    num_events: int = 5,
    event_types: list[str] | None = None,
    seed: int = 42,
    start_time: float = 0.0,
    time_horizon: float = 3600.0,
) -> Scenario:
    """Deterministically generate a repeatable dynamic scenario for a problem.

    Uses an explicit seed to guarantee reproducibility.

    Args:
        problem: Problem instance providing customers, depot, and vehicles.
        num_events: Total number of dynamic events to generate.
        event_types: Subset of ["edge_congestion", "road_blockage", "vehicle_delay", "new_order"].
        seed: Random seed for reproducibility.
        start_time: Simulation start time in seconds.
        time_horizon: Time window across which events are scheduled.

    Returns:
        Fully populated, deterministic Scenario.
    """
    if num_events <= 0:
        return Scenario(
            id=f"scenario_{problem.id}_empty",
            name=f"Empty Scenario for {problem.id}",
            start_time=start_time,
            duration=time_horizon,
            events=[],
        )

    allowed_types = event_types or [
        "edge_congestion",
        "road_blockage",
        "vehicle_delay",
        "new_order",
    ]
    rng = random.Random(seed)

    all_node_ids = [problem.depot.id] + [c.id for c in problem.customers]
    events: list[AnyDynamicEvent] = []

    for i in range(num_events):
        event_id = f"evt_{i + 1:03d}"
        chosen_type = rng.choice(allowed_types)
        # Schedule event between start_time + 10% horizon and 85% horizon
        trigger_time = round(start_time + rng.uniform(0.10, 0.85) * time_horizon, 1)
        duration = round(rng.uniform(300.0, min(1800.0, time_horizon * 0.4)), 1)

        if chosen_type == "edge_congestion":
            orig = rng.choice(all_node_ids)
            dest_candidates = [nid for nid in all_node_ids if nid != orig]
            dest = rng.choice(dest_candidates)
            multiplier = round(rng.uniform(1.5, 3.5), 2)
            events.append(
                EdgeCongestion(
                    event_id=event_id,
                    trigger_time=trigger_time,
                    duration=duration,
                    origin_id=orig,
                    dest_id=dest,
                    multiplier=multiplier,
                    description=f"Traffic slowdown {multiplier}x between {orig} and {dest}",
                )
            )

        elif chosen_type == "road_blockage":
            orig = rng.choice(all_node_ids)
            dest_candidates = [nid for nid in all_node_ids if nid != orig]
            dest = rng.choice(dest_candidates)
            events.append(
                RoadBlockage(
                    event_id=event_id,
                    trigger_time=trigger_time,
                    duration=duration,
                    origin_id=orig,
                    dest_id=dest,
                    description=f"Road blockage between {orig} and {dest}",
                )
            )

        elif chosen_type == "vehicle_delay":
            veh = rng.choice(problem.vehicles)
            delay_sec = round(rng.uniform(120.0, 600.0), 1)
            target_stop = rng.choice([c.id for c in problem.customers])
            events.append(
                VehicleDelay(
                    event_id=event_id,
                    trigger_time=trigger_time,
                    vehicle_id=veh.id,
                    delay_seconds=delay_sec,
                    stop_id=target_stop,
                    description=f"Vehicle {veh.id} delayed by {delay_sec}s at stop {target_stop}",
                )
            )

        elif chosen_type == "new_order":
            # Generate a new customer nearby the existing customers
            ref_cust = rng.choice(problem.customers)
            # Jitter coordinates slightly
            lat_jitter = rng.uniform(-0.015, 0.015)
            lon_jitter = rng.uniform(-0.015, 0.015)
            avg_demand = sum(c.demand for c in problem.customers) / len(problem.customers)
            new_cust = Customer(
                id=f"cust_dynamic_{i + 1}",
                lat=round(ref_cust.lat + lat_jitter, 6),
                lon=round(ref_cust.lon + lon_jitter, 6),
                demand=round(rng.uniform(0.5 * avg_demand, 1.2 * avg_demand), 1),
                ready_time=trigger_time + rng.uniform(60.0, 300.0),
                due_time=trigger_time + rng.uniform(1200.0, 2400.0),
                service_time=ref_cust.service_time,
                priority=rng.choice([1, 1, 2, 3]),
            )
            events.append(
                NewOrder(
                    event_id=event_id,
                    trigger_time=trigger_time,
                    duration=0.0,
                    customer=new_cust,
                    description=f"New urgent on-demand order {new_cust.id} (demand: {new_cust.demand})",
                )
            )

    # Sort events by trigger_time
    events.sort(key=lambda e: e.trigger_time)

    return Scenario(
        id=f"scenario_{problem.id}_seed{seed}",
        name=f"Deterministic Scenario for {problem.id} (seed={seed})",
        start_time=start_time,
        duration=time_horizon,
        events=events,
    )
