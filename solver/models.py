"""Domain models for Route.it CVRPTW solver.

Defines Pydantic v2 data models for Problem components (Depot, Customer, Vehicle, Problem)
and Solution components (Route, Solution).
"""

from __future__ import annotations

import math
from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator, model_validator


class Depot(BaseModel):
    """Depot location and operational window."""

    id: str = "depot"
    lat: float = Field(..., description="Latitude or Y-coordinate")
    lon: float = Field(..., description="Longitude or X-coordinate")
    ready_time: float = Field(0.0, ge=0.0, description="Depot opening time in seconds")
    due_time: float = Field(float("inf"), description="Depot closing time in seconds")
    service_time: float = Field(0.0, ge=0.0, description="Depot handling / turnaround time in seconds")

    @field_validator("due_time", mode="before")
    @classmethod
    def validate_due_time(cls, v: Any) -> float:
        """Handle null/None from JSON and ensure due time is strictly non-negative."""
        if v is None:
            return float("inf")
        val = float(v)
        if val < 0:
            raise ValueError("due_time must be non-negative")
        return val


class Customer(BaseModel):
    """Customer stop representing delivery demand and time window."""

    id: str = Field(..., description="Unique customer identifier")
    lat: float = Field(..., description="Latitude or Y-coordinate")
    lon: float = Field(..., description="Longitude or X-coordinate")
    demand: float = Field(..., ge=0.0, description="Units of capacity required")
    ready_time: float = Field(..., ge=0.0, description="Earliest service start time in seconds (e_i)")
    due_time: float = Field(..., description="Latest service start time in seconds (l_i)")
    service_time: float = Field(..., ge=0.0, description="Duration to service stop in seconds (s_i)")
    priority: int = Field(1, ge=1, description="Customer priority score (higher = higher priority)")

    @field_validator("due_time", mode="before")
    @classmethod
    def validate_customer_due_time(cls, v: Any) -> float:
        """Handle null/None from JSON as unconstrained infinity."""
        if v is None:
            return float("inf")
        return float(v)

    @model_validator(mode="after")
    def validate_time_window(self) -> Customer:
        """Validate that ready_time does not exceed due_time."""
        if self.ready_time > self.due_time:
            raise ValueError(
                f"Customer {self.id}: ready_time ({self.ready_time}) cannot exceed due_time ({self.due_time})"
            )
        return self


class Vehicle(BaseModel):
    """Vehicle profile and shift specifications."""

    id: str = Field(..., description="Unique vehicle identifier")
    capacity: float = Field(..., gt=0.0, description="Max load capacity (Q)")
    shift_start: float = Field(0.0, ge=0.0, description="Shift start time in seconds")
    shift_end: float = Field(float("inf"), description="Shift conclusion time in seconds")
    fixed_cost: float = Field(0.0, ge=0.0, description="Fixed mobilization cost")
    cost_per_time: float = Field(1.0, ge=0.0, description="Operational cost per unit time (seconds)")
    cost_per_distance: float = Field(1.0, ge=0.0, description="Operational cost per unit distance (metres)")

    @field_validator("shift_end", mode="before")
    @classmethod
    def validate_shift_end(cls, v: Any) -> float:
        """Handle null/None from JSON as unconstrained infinity."""
        if v is None:
            return float("inf")
        return float(v)

    @model_validator(mode="after")
    def validate_shift(self) -> Vehicle:
        """Validate shift interval."""
        if self.shift_start > self.shift_end:
            raise ValueError(
                f"Vehicle {self.id}: shift_start ({self.shift_start}) cannot exceed shift_end ({self.shift_end})"
            )
        return self


class Problem(BaseModel):
    """Complete problem instance specification for CVRPTW."""

    id: str = Field(..., description="Problem or instance identifier")
    depot: Depot = Field(..., description="Central distribution depot")
    customers: list[Customer] = Field(..., description="List of customers to service")
    vehicles: list[Vehicle] = Field(..., description="Available vehicle fleet")
    coordinate_system: Literal["geographic", "planar"] = Field(
        "geographic",
        description="Coordinate reference system: 'geographic' (WGS84 lat/lon in degrees) or 'planar' (Cartesian x/y)",
    )
    travel_time_matrix: list[list[float]] | None = Field(
        None,
        description="NxN travel time matrix index 0=depot, 1..N=customers",
    )
    distance_matrix: list[list[float]] | None = Field(
        None,
        description="NxN distance matrix index 0=depot, 1..N=customers",
    )

    @field_validator("customers")
    @classmethod
    def validate_unique_customer_ids(cls, customers: list[Customer]) -> list[Customer]:
        """Ensure all customer IDs are distinct."""
        ids = [c.id for c in customers]
        if len(ids) != len(set(ids)):
            raise ValueError("Customer IDs must be unique within a Problem")
        return customers

    @field_validator("vehicles")
    @classmethod
    def validate_unique_vehicle_ids(cls, vehicles: list[Vehicle]) -> list[Vehicle]:
        """Ensure all vehicle IDs are distinct."""
        ids = [v.id for v in vehicles]
        if len(ids) != len(set(ids)):
            raise ValueError("Vehicle IDs must be unique within a Problem")
        return vehicles

    @property
    def num_customers(self) -> int:
        """Return total number of customers."""
        return len(self.customers)

    @property
    def num_vehicles(self) -> int:
        """Return total number of vehicles."""
        return len(self.vehicles)

    def get_customer(self, customer_id: str) -> Customer:
        """Fetch customer by ID."""
        for c in self.customers:
            if c.id == customer_id:
                return c
        raise KeyError(f"Customer {customer_id} not found in problem")

    def get_customer_index(self, customer_id: str) -> int:
        """Fetch 1-based index (0 is depot) of customer."""
        for idx, c in enumerate(self.customers, start=1):
            if c.id == customer_id:
                return idx
        raise KeyError(f"Customer {customer_id} not found in problem")

    def compute_euclidean_matrices(self, speed: float = 1.0) -> None:
        """Compute Euclidean distance and travel-time matrices based on coordinates.

        Node 0 is the depot, followed by customers 1..N.

        Args:
            speed: Uniform travel speed (distance units per time unit). Defaults to 1.0.
        """
        if speed <= 0:
            raise ValueError("Speed must be positive")

        nodes = [(self.depot.lat, self.depot.lon)] + [(c.lat, c.lon) for c in self.customers]
        n = len(nodes)

        dist_mat: list[list[float]] = [[0.0] * n for _ in range(n)]
        time_mat: list[list[float]] = [[0.0] * n for _ in range(n)]

        for i in range(n):
            lat_i, lon_i = nodes[i]
            for j in range(i + 1, n):
                lat_j, lon_j = nodes[j]
                if self.coordinate_system == "geographic":
                    # Haversine distance in metres
                    r = 6371000.0
                    phi1, phi2 = math.radians(lat_i), math.radians(lat_j)
                    dphi = math.radians(lat_j - lat_i)
                    dlam = math.radians(lon_j - lon_i)
                    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2.0) ** 2
                    d = 2.0 * r * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
                else:
                    d = math.hypot(lat_i - lat_j, lon_i - lon_j)
                dist_mat[i][j] = dist_mat[j][i] = d
                t = d / speed
                time_mat[i][j] = time_mat[j][i] = t

        self.distance_matrix = dist_mat
        self.travel_time_matrix = time_mat


class Route(BaseModel):
    """Assigned vehicle route representing stop sequence and timeline."""

    vehicle_id: str = Field(..., description="ID of assigned vehicle")
    stop_ids: list[str] = Field(..., description="Sequence of customer stop IDs visited")
    arrival_times: list[float] = Field(
        ...,
        description="Arrival times in seconds at each customer stop in stop_ids",
    )
    load: float = Field(..., ge=0.0, description="Total demand serviced on this route")
    distance: float = Field(0.0, ge=0.0, description="Total distance traveled in metres")
    duration: float = Field(0.0, ge=0.0, description="Total route duration including service in seconds")


class Solution(BaseModel):
    """Complete multi-route solution with feasibility and performance metrics."""

    routes: list[Route] = Field(..., description="Collection of vehicle routes")
    total_cost: float = Field(..., description="Objective function value (distance / duration / penalties)")
    is_feasible: bool = Field(..., description="Whether solution satisfies all constraints")
    violations: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Constraint violations categorized by type (e.g. capacity, time_window)",
    )
    algorithm: str = Field("QPSO", description="Algorithm that produced this solution")
    execution_time_sec: float = Field(0.0, ge=0.0, description="Execution runtime in seconds")
    seed: int | None = Field(None, description="Random seed used for reproduction")
