"""Discrete Dynamic Fleet Simulation Engine for Route.it.

Simulates fleet movement along planned CVRPTW routes over time, applying
dynamic incidents (traffic congestion, road blockages, vehicle delays, new orders),
modulating the CostOracle via TrafficAdapter, and emitting time-stamped state snapshots.
"""

from __future__ import annotations

from enum import Enum
import math
from typing import Any
from pydantic import BaseModel, Field

from dynamic.events import (
    AnyDynamicEvent,
    EdgeCongestion,
    NewOrder,
    RoadBlockage,
    Scenario,
    VehicleDelay,
)
from routing.cost_oracle import (
    CostOracle,
    EuclideanOracle,
    Location,
    SimulatedEventAdapter,
    TimeOfDayProfileAdapter,
    to_location,
)
from solver.models import Customer, Depot, Problem, Route, Solution


class VehicleStatus(str, Enum):
    """Operational status of a vehicle during route execution."""

    IDLE = "IDLE"              # Waiting at depot before departure
    EN_ROUTE = "EN_ROUTE"      # Traveling along a road leg between stops
    WAITING = "WAITING"        # Arrived at customer before ready_time
    SERVICING = "SERVICING"    # Actively unloading / servicing customer
    COMPLETED = "COMPLETED"    # Completed all stops and returned to depot


class VehicleState(BaseModel):
    """Real-time operational snapshot of a single vehicle in the fleet."""

    vehicle_id: str
    route_index: int
    status: VehicleStatus
    current_coords: tuple[float, float] = Field(..., description="(lat, lon) current position")
    current_leg_origin_id: str
    current_leg_dest_id: str
    current_stop_index: int = Field(
        ...,
        description="Index of current stop in route.stop_ids (-1 before first customer, len after last)",
    )
    leg_departure_time: float
    leg_arrival_time: float
    service_start_time: float | None = None
    service_end_time: float | None = None
    current_load: float = 0.0
    visited_stops: list[str] = Field(default_factory=list)
    remaining_stops: list[str] = Field(default_factory=list)
    delay_seconds: float = 0.0


class SimulationSnapshot(BaseModel):
    """Global system snapshot emitted at a simulation clock tick."""

    timestamp: float = Field(..., description="Current simulation time in seconds")
    step: int = Field(..., description="Simulation step counter")
    vehicle_states: dict[str, VehicleState] = Field(
        ...,
        description="Current state of each vehicle keyed by vehicle_id",
    )
    active_events: list[str] = Field(
        default_factory=list,
        description="List of event IDs currently active in the traffic network",
    )
    pending_orders: list[Customer] = Field(
        default_factory=list,
        description="Unrouted on-demand dynamic customer orders",
    )
    all_completed: bool = Field(
        ...,
        description="Whether all active vehicles have finished and returned to depot",
    )


class FleetSimulator:
    """Discrete-time dynamic fleet simulator for CVRPTW executions."""

    def __init__(
        self,
        problem: Problem,
        solution: Solution,
        cost_oracle: CostOracle | None = None,
        traffic_adapter: SimulatedEventAdapter | None = None,
        scenario: Scenario | None = None,
        start_time: float = 0.0,
    ) -> None:
        """Initialize simulation environment.

        Args:
            problem: CVRPTW problem instance.
            solution: Planned multi-vehicle routing solution.
            cost_oracle: CostOracle for travel-time evaluation. Defaults to EuclideanOracle.
            traffic_adapter: SimulatedEventAdapter to apply dynamic traffic events to.
            scenario: Dynamic scenario containing scheduled events.
            start_time: Simulation starting clock in seconds (default: 0.0).
        """
        self.problem = problem
        self.solution = solution
        self.clock = float(start_time)
        self.step_count = 0
        self.scenario = scenario

        # Configure TrafficAdapter & CostOracle
        if traffic_adapter is not None:
            self.traffic_adapter = traffic_adapter
        elif cost_oracle is not None and isinstance(cost_oracle.traffic_adapter, SimulatedEventAdapter):
            self.traffic_adapter = cost_oracle.traffic_adapter
        else:
            self.traffic_adapter = SimulatedEventAdapter(
                base_adapter=TimeOfDayProfileAdapter({h: 1.0 for h in range(24)})
            )

        if cost_oracle is not None:
            self.cost_oracle = cost_oracle
            if self.cost_oracle.traffic_adapter is None:
                self.cost_oracle.traffic_adapter = self.traffic_adapter
        else:
            self.cost_oracle = EuclideanOracle(traffic_adapter=self.traffic_adapter)

        # Internal tracking
        self.active_events: dict[str, AnyDynamicEvent] = {}
        self.completed_events: set[str] = set()
        self.pending_orders: list[Customer] = []
        self.vehicle_routes: dict[str, Route] = {}
        self.vehicles: dict[str, VehicleState] = {}

        self._nodes: dict[str, Location] = {
            self.problem.depot.id: to_location(self.problem.depot)
        }
        for cust in self.problem.customers:
            self._nodes[cust.id] = to_location(cust)

        self._init_fleet()

    def _get_node(self, node_id: str) -> Location:
        """Fetch location for a given node ID."""
        if node_id in self._nodes:
            return self._nodes[node_id]
        if node_id == self.problem.depot.id:
            return to_location(self.problem.depot)
        cust = self.problem.get_customer(node_id)
        loc = to_location(cust)
        self._nodes[node_id] = loc
        return loc

    def _init_fleet(self) -> None:
        """Initialize vehicle states from planned solution routes."""
        depot_loc = (self.problem.depot.lat, self.problem.depot.lon)

        for route_idx, route in enumerate(self.solution.routes):
            v_id = route.vehicle_id
            self.vehicle_routes[v_id] = route

            if not route.stop_ids:
                # Empty route
                self.vehicles[v_id] = VehicleState(
                    vehicle_id=v_id,
                    route_index=route_idx,
                    status=VehicleStatus.COMPLETED,
                    current_coords=depot_loc,
                    current_leg_origin_id=self.problem.depot.id,
                    current_leg_dest_id=self.problem.depot.id,
                    current_stop_index=0,
                    leg_departure_time=self.clock,
                    leg_arrival_time=self.clock,
                    current_load=0.0,
                    visited_stops=[],
                    remaining_stops=[],
                )
                continue

            # First leg: Depot -> route.stop_ids[0]
            first_dest_id = route.stop_ids[0]
            first_cust = self.problem.get_customer(first_dest_id)

            # Earliest possible vehicle departure from depot
            veh_model = next((v for v in self.problem.vehicles if v.id == v_id), None)
            shift_start = veh_model.shift_start if veh_model else 0.0
            planned_depot_departure = max(self.clock, self.problem.depot.ready_time, shift_start)

            t_travel = self.cost_oracle.travel_time(
                self.problem.depot, first_cust, planned_depot_departure
            )
            planned_arrival = planned_depot_departure + t_travel

            is_idle = self.clock < planned_depot_departure
            status = VehicleStatus.IDLE if is_idle else VehicleStatus.EN_ROUTE

            self.vehicles[v_id] = VehicleState(
                vehicle_id=v_id,
                route_index=route_idx,
                status=status,
                current_coords=depot_loc,
                current_leg_origin_id=self.problem.depot.id,
                current_leg_dest_id=first_dest_id,
                current_stop_index=0,
                leg_departure_time=planned_depot_departure,
                leg_arrival_time=planned_arrival,
                current_load=0.0,
                visited_stops=[],
                remaining_stops=list(route.stop_ids),
                delay_seconds=0.0,
            )

    def apply_event(self, event: AnyDynamicEvent) -> None:
        """Dynamically apply an event to the simulation environment."""
        if event.event_id in self.active_events or event.event_id in self.completed_events:
            return

        if isinstance(event, (EdgeCongestion, RoadBlockage)):
            incidents = event.to_simulated_incidents()
            for inc in incidents:
                self.traffic_adapter.add_incident(inc)
            # If cost_oracle has cache, clear to reflect immediate traffic changes
            if getattr(self.cost_oracle, "cache", None) is not None:
                self.cost_oracle.cache.clear()
            self.active_events[event.event_id] = event

        elif isinstance(event, VehicleDelay):
            if event.vehicle_id in self.vehicles:
                v_state = self.vehicles[event.vehicle_id]
                v_state.delay_seconds += event.delay_seconds
                if v_state.status == VehicleStatus.EN_ROUTE:
                    v_state.leg_arrival_time += event.delay_seconds
                elif v_state.status == VehicleStatus.SERVICING and v_state.service_end_time is not None:
                    v_state.service_end_time += event.delay_seconds
                elif v_state.status == VehicleStatus.WAITING:
                    # Delay waiting/service start
                    v_state.leg_arrival_time += event.delay_seconds
                elif v_state.status == VehicleStatus.IDLE:
                    v_state.leg_departure_time += event.delay_seconds
                    v_state.leg_arrival_time += event.delay_seconds
            self.active_events[event.event_id] = event

        elif isinstance(event, NewOrder):
            self.pending_orders.append(event.customer)
            self._nodes[event.customer.id] = to_location(event.customer)
            self.active_events[event.event_id] = event

    def remove_event(self, event_id: str) -> None:
        """Deactivate and clean up an active event."""
        event = self.active_events.pop(event_id, None)
        if event is None:
            return

        self.completed_events.add(event_id)

        if isinstance(event, (EdgeCongestion, RoadBlockage)):
            incidents = event.to_simulated_incidents()
            for inc in incidents:
                self.traffic_adapter.remove_incident(inc.event_id)
            if getattr(self.cost_oracle, "cache", None) is not None:
                self.cost_oracle.cache.clear()

    def step(self, delta_seconds: float = 60.0) -> SimulationSnapshot:
        """Advance the simulation clock by delta_seconds and update all states.

        Args:
            delta_seconds: Amount of time in seconds to step forward.

        Returns:
            SimulationSnapshot capturing the state at the new timestamp.
        """
        if delta_seconds <= 0:
            raise ValueError("delta_seconds must be strictly positive")

        target_time = round(self.clock + delta_seconds, 6)
        self.clock = target_time
        self.step_count += 1

        # 1. Process Scenario Events
        if self.scenario is not None:
            for event in self.scenario.events:
                if event.trigger_time <= self.clock and event.event_id not in self.active_events and event.event_id not in self.completed_events:
                    self.apply_event(event)

        # Deactivate expired events
        expired_ids = [
            e_id for e_id, e in self.active_events.items()
            if e.end_time <= self.clock
        ]
        for e_id in expired_ids:
            self.remove_event(e_id)

        # 2. Advance Each Vehicle
        for v_id, v_state in self.vehicles.items():
            self._advance_vehicle(v_state)

        # 3. Build & Return Snapshot
        all_completed = all(v.status == VehicleStatus.COMPLETED for v in self.vehicles.values())
        return SimulationSnapshot(
            timestamp=self.clock,
            step=self.step_count,
            vehicle_states={k: v.model_copy() for k, v in self.vehicles.items()},
            active_events=list(self.active_events.keys()),
            pending_orders=list(self.pending_orders),
            all_completed=all_completed,
        )

    def _advance_vehicle(self, v_state: VehicleState) -> None:
        """Advance state and coordinates for a single vehicle at current clock."""
        if v_state.status == VehicleStatus.COMPLETED:
            return

        route = self.vehicle_routes[v_state.vehicle_id]

        # State: IDLE
        if v_state.status == VehicleStatus.IDLE:
            if self.clock >= v_state.leg_departure_time:
                v_state.status = VehicleStatus.EN_ROUTE

        # State: EN_ROUTE
        if v_state.status == VehicleStatus.EN_ROUTE:
            orig_loc = self._get_node(v_state.current_leg_origin_id)
            dest_loc = self._get_node(v_state.current_leg_dest_id)

            if self.clock < v_state.leg_arrival_time:
                # Interpolate coordinate position
                total_duration = max(0.001, v_state.leg_arrival_time - v_state.leg_departure_time)
                elapsed = max(0.0, self.clock - v_state.leg_departure_time)
                frac = min(1.0, elapsed / total_duration)

                cur_lat = orig_loc.lat + frac * (dest_loc.lat - orig_loc.lat)
                cur_lon = orig_loc.lon + frac * (dest_loc.lon - orig_loc.lon)
                v_state.current_coords = (round(cur_lat, 6), round(cur_lon, 6))
                return
            else:
                # Vehicle has arrived at destination stop
                v_state.current_coords = (dest_loc.lat, dest_loc.lon)

                # Check if arrived at final return to depot
                if v_state.current_leg_dest_id == self.problem.depot.id and v_state.current_stop_index >= len(route.stop_ids):
                    v_state.status = VehicleStatus.COMPLETED
                    return

                # Arrived at customer stop
                cust = self.problem.get_customer(v_state.current_leg_dest_id)
                arr_time = v_state.leg_arrival_time

                if self.clock < cust.ready_time:
                    v_state.status = VehicleStatus.WAITING
                    v_state.service_start_time = cust.ready_time
                    v_state.service_end_time = cust.ready_time + cust.service_time
                    return
                else:
                    v_state.status = VehicleStatus.SERVICING
                    srv_start = max(arr_time, cust.ready_time)
                    v_state.service_start_time = srv_start
                    v_state.service_end_time = srv_start + cust.service_time

        # State: WAITING
        if v_state.status == VehicleStatus.WAITING:
            cust = self.problem.get_customer(v_state.current_leg_dest_id)
            if self.clock >= cust.ready_time:
                v_state.status = VehicleStatus.SERVICING
                v_state.service_start_time = cust.ready_time
                v_state.service_end_time = cust.ready_time + cust.service_time

        # State: SERVICING
        if v_state.status == VehicleStatus.SERVICING:
            if v_state.service_end_time is not None and self.clock >= v_state.service_end_time:
                # Service complete! Record stop and transition
                completed_stop = v_state.current_leg_dest_id
                v_state.visited_stops.append(completed_stop)
                if completed_stop in v_state.remaining_stops:
                    v_state.remaining_stops.remove(completed_stop)

                cust = self.problem.get_customer(completed_stop)
                v_state.current_load += cust.demand

                # Plan next leg
                v_state.current_stop_index += 1
                departure_now = v_state.service_end_time

                if v_state.current_stop_index < len(route.stop_ids):
                    next_stop_id = route.stop_ids[v_state.current_stop_index]
                    next_loc = self._get_node(next_stop_id)
                else:
                    # All customer stops done -> return to depot
                    next_stop_id = self.problem.depot.id
                    next_loc = self._get_node(next_stop_id)

                cur_node = self._get_node(completed_stop)
                leg_t = self.cost_oracle.travel_time(cur_node, next_loc, departure_now)

                v_state.current_leg_origin_id = completed_stop
                v_state.current_leg_dest_id = next_stop_id
                v_state.leg_departure_time = departure_now
                v_state.leg_arrival_time = departure_now + leg_t
                v_state.service_start_time = None
                v_state.service_end_time = None

                if self.clock < v_state.leg_arrival_time:
                    v_state.status = VehicleStatus.EN_ROUTE
                    total_dur = max(0.001, v_state.leg_arrival_time - departure_now)
                    frac = min(1.0, max(0.0, self.clock - departure_now) / total_dur)
                    cur_lat = cur_node.lat + frac * (next_loc.lat - cur_node.lat)
                    cur_lon = cur_node.lon + frac * (next_loc.lon - cur_node.lon)
                    v_state.current_coords = (round(cur_lat, 6), round(cur_lon, 6))
                else:
                    # Fast step caught arrival directly
                    if next_stop_id == self.problem.depot.id:
                        v_state.status = VehicleStatus.COMPLETED
                        v_state.current_coords = (next_loc.lat, next_loc.lon)
                    else:
                        v_state.status = VehicleStatus.EN_ROUTE
                        self._advance_vehicle(v_state)

    def run_until(self, target_time: float, step_size: float = 60.0) -> list[SimulationSnapshot]:
        """Run simulation stepping forward until clock reaches target_time."""
        snapshots: list[SimulationSnapshot] = []
        while self.clock < target_time:
            delta = min(step_size, target_time - self.clock)
            snapshots.append(self.step(delta))
        return snapshots

    def run_to_completion(
        self, step_size: float = 60.0, max_steps: int = 10000
    ) -> list[SimulationSnapshot]:
        """Run simulation until all vehicles complete routes or max_steps reached."""
        snapshots: list[SimulationSnapshot] = []
        for _ in range(max_steps):
            snap = self.step(step_size)
            snapshots.append(snap)
            if snap.all_completed:
                break
        return snapshots
