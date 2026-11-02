"""Independent solution validator for Route.it CVRPTW solver.

Performs a clean-room verification of all constraints and recomputes exact route costs:
1. Customer coverage (every customer visited exactly once, no missing, no duplicates).
2. Vehicle capacity limits (route total demand <= vehicle capacity).
3. Stop time windows (arrival time <= customer due time, accounting for travel, wait, and service).
4. Depot time windows (vehicle returns before depot due time).
5. Driver duty limits (total shift duration <= maximum shift limit).
6. Fleet size limit (number of used routes <= available vehicles).
7. Independent cost recomputation (distance and duration computed from scratch).
"""

from __future__ import annotations

import math
from typing import Any, Sequence
from pydantic import BaseModel, Field

from solver.models import Customer, Depot, Problem, Route, Solution


class ValidationResult(BaseModel):
    """Structured report of independent solution validation."""

    is_valid: bool = Field(..., description="True if and only if ALL constraints are strictly satisfied")
    violations: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Detailed violation messages grouped by category",
    )
    recomputed_cost: float = Field(..., description="Recomputed total routing cost (distance)")
    recomputed_distance: float = Field(..., description="Total cumulative distance across all routes")
    recomputed_duration: float = Field(..., description="Total operational duration across all routes")
    total_waiting_time: float = Field(0.0, description="Cumulative waiting time before time window openings")
    total_service_time: float = Field(0.0, description="Cumulative service time across all customer visits")
    max_route_duration: float = Field(0.0, description="Longest duration among all routes")
    num_routes_used: int = Field(..., description="Number of routes in the solution")
    customer_count: int = Field(..., description="Total customers serviced")


def _get_travel_cost(
    p1: tuple[float, float],
    p2: tuple[float, float],
    matrix: list[list[float]] | None,
    idx1: int,
    idx2: int,
    cost_oracle: Any | None,
    loc1: Any | None,
    loc2: Any | None,
    depart_time: float,
) -> tuple[float, float]:
    """Helper to obtain (travel_time, distance) between two stops."""
    if cost_oracle is not None and loc1 is not None and loc2 is not None:
        tt = float(cost_oracle.travel_time(loc1, loc2, depart_time=depart_time))
        dist = float(cost_oracle.distance(loc1, loc2))
        return tt, dist

    if matrix is not None:
        tt = float(matrix[idx1][idx2])
        dist = float(matrix[idx1][idx2])
        return tt, dist

    # Planar Euclidean fallback
    dist = math.hypot(p1[0] - p2[0], p1[1] - p2[1])
    return dist, dist


def validate_solution(
    problem: Problem,
    solution: Solution,
    cost_oracle: Any | None = None,
    tolerance: float = 1e-4,
    max_vehicles: int | None = None,
    max_duty_duration: float | None = None,
    hard_duty_limit: bool = True,
    enforce_priority_early_service: bool = False,
    priority_early_ratio: float = 0.5,
) -> ValidationResult:
    """Independently validate a Solution against a Problem instance from scratch.

    Args:
        problem: The Problem definition.
        solution: The Solution to validate.
        cost_oracle: Optional CostOracle for road network or dynamic traffic times.
        tolerance: Numerical tolerance for floating-point comparisons.
        max_vehicles: Optional limit on the number of vehicle routes.
        max_duty_duration: Maximum allowed duration for any single route.
        hard_duty_limit: Whether exceeding max_duty_duration invalidates the solution.
        enforce_priority_early_service: Whether priority customers must be served in earlier window.
        priority_early_ratio: Fraction of window for priority early service (e.g. 0.5 = first 50%).

    Returns:
        ValidationResult with complete status, violations dictionary, and recomputed metrics.
    """
    violations: dict[str, list[str]] = {}

    expected_customer_ids = {c.id for c in problem.customers}
    customer_map: dict[str, Customer] = {c.id: c for c in problem.customers}
    customer_idx_map: dict[str, int] = {c.id: idx for idx, c in enumerate(problem.customers, start=1)}

    # Prepare locations for CostOracle if present
    loc_depot = None
    loc_custs: dict[str, Any] = {}
    if cost_oracle is not None:
        from routing.cost_oracle import Location
        loc_depot = Location(id=problem.depot.id, lat=problem.depot.lat, lon=problem.depot.lon)
        for c in problem.customers:
            loc_custs[c.id] = Location(id=c.id, lat=c.lat, lon=c.lon)

    # 1. Customer Coverage Checks
    visited_ids: list[str] = []
    for r_idx, route in enumerate(solution.routes):
        for cid in route.stop_ids:
            visited_ids.append(cid)

    visited_set = set(visited_ids)
    missing_ids = expected_customer_ids - visited_set
    if missing_ids:
        violations.setdefault("customer_coverage", []).append(
            f"Missing {len(missing_ids)} customer(s): {sorted(list(missing_ids))[:10]}"
        )

    if len(visited_ids) != len(visited_set):
        from collections import Counter
        counts = Counter(visited_ids)
        dups = [cid for cid, count in counts.items() if count > 1]
        violations.setdefault("customer_coverage", []).append(
            f"Duplicate visits to customer(s): {dups[:10]}"
        )

    unknown_ids = visited_set - expected_customer_ids
    if unknown_ids:
        violations.setdefault("customer_coverage", []).append(
            f"Unknown customer ID(s) visited: {sorted(list(unknown_ids))[:10]}"
        )

    # 2. Fleet Size Limit & Registered Vehicle ID Check
    if problem.vehicles:
        known_veh_ids = {v.id for v in problem.vehicles}
        for r_idx, route in enumerate(solution.routes):
            if route.vehicle_id not in known_veh_ids:
                violations.setdefault("fleet_size", []).append(
                    f"Route {r_idx + 1} assigned vehicle '{route.vehicle_id}' which does not exist in problem.vehicles"
                )
        eff_max = max_vehicles if max_vehicles is not None else len(problem.vehicles)
        if len(solution.routes) > eff_max:
            violations.setdefault("fleet_size", []).append(
                f"Solution uses {len(solution.routes)} routes, exceeding available fleet size of {eff_max}"
            )
    elif max_vehicles is not None and len(solution.routes) > max_vehicles:
        violations.setdefault("fleet_size", []).append(
            f"Solution uses {len(solution.routes)} routes, exceeding max limit of {max_vehicles}"
        )

    # 3. Route-by-Route Simulation & Checks
    total_dist = 0.0
    total_duration = 0.0
    total_waiting = 0.0
    total_service = 0.0
    max_route_dur = 0.0

    depot_pt = (problem.depot.lat, problem.depot.lon)

    for r_idx, route in enumerate(solution.routes):
        veh_id = route.vehicle_id
        # Determine capacity for assigned vehicle
        matched_veh = next((v for v in problem.vehicles if v.id == veh_id), None)
        veh_cap = matched_veh.capacity if matched_veh else (problem.vehicles[0].capacity if problem.vehicles else 100.0)

        # Max duty limit check
        route_max_duty = max_duty_duration
        if route_max_duty is None and matched_veh and math.isfinite(matched_veh.shift_end) and math.isfinite(matched_veh.shift_start):
            shift_diff = matched_veh.shift_end - matched_veh.shift_start
            if shift_diff > 0:
                route_max_duty = shift_diff

        # Capacity check
        recomputed_load = 0.0
        for cid in route.stop_ids:
            if cid in customer_map:
                recomputed_load += customer_map[cid].demand

        if recomputed_load > veh_cap + tolerance:
            violations.setdefault("capacity", []).append(
                f"Route {r_idx+1} (vehicle {veh_id}): total load {recomputed_load:.2f} exceeds capacity {veh_cap:.2f}"
            )

        # Timeline simulation
        curr_time = problem.depot.ready_time
        prev_pt = depot_pt
        prev_idx = 0
        prev_loc = loc_depot
        route_dist = 0.0

        for stop_seq, cid in enumerate(route.stop_ids):
            if cid not in customer_map:
                continue
            cust = customer_map[cid]
            cust_idx = customer_idx_map[cid]
            cust_pt = (cust.lat, cust.lon)
            cust_loc = loc_custs.get(cid)

            # Travel to customer
            tt, d = _get_travel_cost(
                prev_pt, cust_pt, problem.travel_time_matrix, prev_idx, cust_idx,
                cost_oracle, prev_loc, cust_loc, curr_time
            )
            route_dist += d
            arrival_time = curr_time + tt

            # Time window verification
            if arrival_time > cust.due_time + tolerance:
                lateness = arrival_time - cust.due_time
                violations.setdefault("time_window", []).append(
                    f"Route {r_idx+1} stop {stop_seq+1} ({cid}): arrived at {arrival_time:.2f} > due {cust.due_time:.2f} (late by {lateness:.2f}s)"
                )

            # Priority early service check
            if enforce_priority_early_service and cust.priority > 1:
                early_due = cust.ready_time + priority_early_ratio * (cust.due_time - cust.ready_time)
                if arrival_time > early_due + tolerance:
                    violations.setdefault("priority_early_service", []).append(
                        f"Priority customer {cid} arrived at {arrival_time:.2f} > early deadline {early_due:.2f}"
                    )

            # Waiting & service
            wait = max(0.0, cust.ready_time - arrival_time)
            total_waiting += wait
            service_start = max(arrival_time, cust.ready_time)
            total_service += cust.service_time
            curr_time = service_start + cust.service_time

            prev_pt = cust_pt
            prev_idx = cust_idx
            prev_loc = cust_loc

        # Return to depot
        tt, d = _get_travel_cost(
            prev_pt, depot_pt, problem.travel_time_matrix, prev_idx, 0,
            cost_oracle, prev_loc, loc_depot, curr_time
        )
        route_dist += d
        depot_arrival = curr_time + tt
        total_dist += route_dist

        # Depot operational window check
        if depot_arrival > problem.depot.due_time + tolerance:
            lateness = depot_arrival - problem.depot.due_time
            violations.setdefault("depot_due_time", []).append(
                f"Route {r_idx+1} (vehicle {veh_id}): returned to depot at {depot_arrival:.2f} > depot due {problem.depot.due_time:.2f} (late by {lateness:.2f}s)"
            )

        route_duration = depot_arrival - problem.depot.ready_time
        total_duration += route_duration
        if route_duration > max_route_dur:
            max_route_dur = route_duration

        # Driver duty limit check
        if route_max_duty is not None and route_duration > route_max_duty + tolerance:
            msg = f"Route {r_idx+1} (vehicle {veh_id}): duration {route_duration:.2f}s exceeds max duty limit {route_max_duty:.2f}s"
            if hard_duty_limit:
                violations.setdefault("driver_duty_limit", []).append(msg)

    is_valid = len(violations) == 0

    return ValidationResult(
        is_valid=is_valid,
        violations=violations,
        recomputed_cost=round(total_dist, 4),
        recomputed_distance=round(total_dist, 4),
        recomputed_duration=round(total_duration, 4),
        total_waiting_time=round(total_waiting, 4),
        total_service_time=round(total_service, 4),
        max_route_duration=round(max_route_dur, 4),
        num_routes_used=len(solution.routes),
        customer_count=len(visited_ids),
    )
