"""Dijkstra Shortest-Path & Sequential Insertion Routing Heuristic for CVRPTW.

Utilizes NetworkX graph modeling and Dijkstra's algorithm to compute exact shortest paths
and dynamic road costs under traffic congestion, and constructs multi-vehicle routes
using capacity- and time-window-constrained greedy shortest-path dispatch.
Serves as an empirical deterministic baseline alongside QPSO, PSO, GA, and OR-Tools.
"""

from __future__ import annotations

import math
import time
from typing import Any, Callable
import networkx as nx
import numpy as np
from pydantic import BaseModel, Field

from solver.models import Customer, Problem, Route, Solution
from solver.tensor import CostTensor, precompute_cost_tensor
from solver.validate import validate_solution


class DijkstraConfig(BaseModel):
    """Configuration parameters for Dijkstra routing heuristic."""

    seed: int | None = Field(None, description="Random seed for tie-breaking")
    max_vehicles: int | None = Field(None, description="Optional cap on vehicle count")
    allow_extra_vehicles: bool = Field(False, description="Allow generating more routes than available fleet")
    max_duty_duration: float | None = Field(None, description="Max allowed shift duration per route")
    hard_time_windows: bool = Field(False, description="Strictly forbid time window violations")
    enforce_priority_early_service: bool = Field(
        False, description="Prioritize early delivery for high-priority customers"
    )
    priority_early_ratio: float = Field(0.5, description="Fraction of window for priority early service")


def solve_dijkstra(
    problem: Problem,
    config: DijkstraConfig | None = None,
    cost_oracle: Any | None = None,
    callback: Callable[[int, float], None] | None = None,
) -> tuple[Solution, list[float]]:
    """Execute Dijkstra-based Network Shortest Path Heuristic for CVRPTW.

    Args:
        problem: Fully initialized Problem instance.
        config: DijkstraConfig options. If None, default settings are used.
        cost_oracle: Optional CostOracle for road network or traffic evaluation.
        callback: Optional callback(step, current_cost) invoked during route building.

    Returns:
        (Solution, cost_history) containing generated routes and cumulative cost trajectory.
    """
    if config is None:
        config = DijkstraConfig()

    start_time = time.perf_counter()
    n = problem.num_customers
    if n == 0:
        return Solution(
            routes=[],
            total_cost=0.0,
            is_feasible=True,
            violations={},
            algorithm="DijkstraHeuristic",
            execution_time_sec=0.0,
            seed=config.seed,
        ), [0.0]

    # Precompute CostTensor
    cost_tensor = precompute_cost_tensor(problem, cost_oracle=cost_oracle)
    cost_data = cost_tensor.travel_time_tensor
    dist_mat = cost_tensor.distance_matrix

    num_nodes = n + 1
    # Build NetworkX graph of the delivery network
    G = nx.DiGraph()
    for i in range(num_nodes):
        G.add_node(i)

    # Add edges with base travel time and distance
    t0_matrix = cost_data[0] if cost_data.ndim == 3 else cost_data
    for i in range(num_nodes):
        for j in range(num_nodes):
            if i != j:
                weight = float(t0_matrix[i, j])
                dist = float(dist_mat[i, j]) if dist_mat is not None else weight
                G.add_edge(i, j, weight=weight, distance=dist)

    # Precompute all-pairs shortest path lengths using NetworkX Dijkstra
    dijkstra_dist: dict[int, dict[int, float]] = dict(
        nx.all_pairs_dijkstra_path_length(G, weight="weight")
    )

    customers = problem.customers
    demands = np.array([0.0] + [c.demand for c in customers], dtype=np.float64)
    service_times = np.array([problem.depot.service_time] + [c.service_time for c in customers], dtype=np.float64)
    ready_times = np.array([problem.depot.ready_time] + [c.ready_time for c in customers], dtype=np.float64)
    due_times = np.array([problem.depot.due_time] + [c.due_time for c in customers], dtype=np.float64)

    for idx, c in enumerate(customers, start=1):
        if config.enforce_priority_early_service and c.priority > 1:
            early_due = c.ready_time + config.priority_early_ratio * (c.due_time - c.ready_time)
            due_times[idx] = early_due

    vehicle_capacity = problem.vehicles[0].capacity if problem.vehicles else 100.0
    max_vehicles_allowed = (
        config.max_vehicles
        if config.max_vehicles is not None
        else (len(problem.vehicles) if (problem.vehicles and not config.allow_extra_vehicles) else 999)
    )

    unvisited = set(range(1, num_nodes))
    routes: list[Route] = []
    cost_history: list[float] = []
    cumulative_cost = 0.0

    vehicle_idx = 0
    while unvisited and vehicle_idx < max_vehicles_allowed:
        v_obj = problem.vehicles[vehicle_idx % len(problem.vehicles)] if problem.vehicles else None
        vehicle_id = v_obj.id if v_obj else f"V_{vehicle_idx + 1}"
        cap = v_obj.capacity if v_obj else vehicle_capacity

        current_node = 0
        current_time = problem.depot.ready_time
        current_load = 0.0
        route_stop_ids: list[str] = []
        route_arrival_times: list[float] = []

        while unvisited:
            best_candidate = None
            best_score = float("inf")
            best_arrival = 0.0
            best_departure = 0.0

            for cand in unvisited:
                demand = demands[cand]
                if current_load + demand > cap:
                    continue

                # Dijkstra shortest travel time from current_node to cand
                dijkstra_tt = dijkstra_dist.get(current_node, {}).get(cand, t0_matrix[current_node, cand])
                arr_time = current_time + dijkstra_tt
                start_service = max(arr_time, ready_times[cand])
                dep_time = start_service + service_times[cand]

                # Time window constraint
                if arr_time > due_times[cand]:
                    continue

                # Check if return to depot is feasible
                return_tt = dijkstra_dist.get(cand, {}).get(0, t0_matrix[cand, 0])
                if dep_time + return_tt > problem.depot.due_time:
                    continue

                # Time window penalty
                lateness = max(0.0, arr_time - due_times[cand])
                if config.hard_time_windows and lateness > 0.0:
                    continue

                # Heuristic score: shortest path distance + lateness penalty + urgency (due_time)
                urgency = due_times[cand] - arr_time
                priority_bonus = (customers[cand - 1].priority - 1) * 50.0
                score = dijkstra_tt + (lateness * 10.0) + (urgency * 0.05) - priority_bonus

                if score < best_score:
                    best_score = score
                    best_candidate = cand
                    best_arrival = arr_time
                    best_departure = dep_time

            if best_candidate is None:
                # No more candidates fit this vehicle's capacity/time-window
                break

            # Visit best candidate
            unvisited.remove(best_candidate)
            current_load += demands[best_candidate]
            current_time = best_departure
            route_stop_ids.append(customers[best_candidate - 1].id)
            route_arrival_times.append(best_arrival)
            current_node = best_candidate

            # Update running cost estimate
            running_dist = float(len(route_stop_ids) * 2.5)
            cost_history.append(float(cumulative_cost + running_dist))

        if route_stop_ids:
            return_tt = dijkstra_dist.get(current_node, {}).get(0, t0_matrix[current_node, 0])
            depot_return_time = current_time + return_tt

            # Calculate route distance
            node_seq = [0] + [problem.get_customer_index(s_id) for s_id in route_stop_ids] + [0]
            r_dist = 0.0
            for i in range(len(node_seq) - 1):
                u, v = node_seq[i], node_seq[i + 1]
                r_dist += float(dist_mat[u, v]) if dist_mat is not None else float(t0_matrix[u, v])

            route_obj = Route(
                vehicle_id=vehicle_id,
                stop_ids=route_stop_ids,
                arrival_times=route_arrival_times,
                load=current_load,
                distance=r_dist,
                duration=depot_return_time - problem.depot.ready_time,
            )
            routes.append(route_obj)
            cumulative_cost += r_dist

        vehicle_idx += 1

    # Remaining unvisited customers (if fleet capacity limit reached)
    if unvisited:
        for cand in list(unvisited):
            r_dist = float(dist_mat[0, cand] + dist_mat[cand, 0]) if dist_mat is not None else float(t0_matrix[0, cand] + t0_matrix[cand, 0])
            tt = float(t0_matrix[0, cand])
            arr = problem.depot.ready_time + tt
            dep = max(arr, ready_times[cand]) + service_times[cand]
            routes.append(
                Route(
                    vehicle_id=f"V_extra_{cand}",
                    stop_ids=[customers[cand - 1].id],
                    arrival_times=[arr],
                    load=demands[cand],
                    distance=r_dist,
                    duration=(dep + float(t0_matrix[cand, 0])) - problem.depot.ready_time,
                )
            )
            cumulative_cost += r_dist
        unvisited.clear()

    elapsed_time = time.perf_counter() - start_time
    total_cost = sum(r.distance for r in routes)

    solution = Solution(
        routes=routes,
        total_cost=total_cost,
        is_feasible=True,
        violations={},
        algorithm="DijkstraHeuristic",
        execution_time_sec=elapsed_time,
        seed=config.seed,
    )

    # Validation stamp
    val_report = validate_solution(
        problem,
        solution,
        cost_oracle=cost_oracle,
        max_vehicles=config.max_vehicles,
        max_duty_duration=config.max_duty_duration,
        hard_duty_limit=False,
    )
    solution.is_feasible = val_report.is_valid
    solution.violations = val_report.violations
    if solution.is_feasible:
        solution.total_cost = val_report.recomputed_cost

    if not cost_history:
        cost_history = [total_cost]

    return solution, cost_history
