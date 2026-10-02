"""Prins Split algorithm for CVRPTW.

Partitions a continuous random-key giant tour into optimal feasible vehicle
routes using a shortest-path-on-DAG formulation (Prins, 2004).
Includes Numba JIT acceleration with pure NumPy fallback.
"""

from __future__ import annotations

from typing import Any, Sequence
import numpy as np

# Optional Numba JIT acceleration
try:
    from numba import njit  # type: ignore
    HAS_NUMBA = True
except ImportError:
    HAS_NUMBA = False

    def njit(*args: Any, **kwargs: Any) -> Any:  # type: ignore
        """Fallback no-op decorator when numba is not installed."""
        def decorator(func: Any) -> Any:
            return func
        return decorator

from solver.models import Customer, Problem, Route


@njit(fastmath=True)
def _split_cost_numba(
    tour: np.ndarray,
    dist_matrix: np.ndarray,
    demands: np.ndarray,
    capacity: float,
    max_vehicles: int = -1,
    overflow_penalty: float = 10000.0,
) -> float:
    """Numba-accelerated evaluation of the optimal split cost for a giant tour.

    Args:
        tour: 1D integer array containing 1-based customer indices in visiting order.
        dist_matrix: 2D float array of distances where 0 is depot, 1..n are customers.
        demands: 1D float array where demands[0]=0, demands[k]=demand of customer k.
        capacity: Maximum vehicle capacity Q.
        max_vehicles: Max number of vehicles allowed (-1 for unconstrained).
        overflow_penalty: Cost penalty per vehicle exceeding max_vehicles.

    Returns:
        Optimal total routing distance (including depot returns).
    """
    n = len(tour)
    if n == 0:
        return 0.0

    if max_vehicles <= 0:
        # Unconstrained vehicle count: 1D Bellman-Ford DAG shortest path
        V = np.full(n + 1, 1e12, dtype=np.float64)
        V[0] = 0.0

        for i in range(n):
            if V[i] >= 1e12:
                continue
            load = 0.0
            cost = 0.0

            for j in range(i + 1, n + 1):
                cust = tour[j - 1]
                load += demands[cust]
                if load > capacity:
                    break

                if j == i + 1:
                    cost = dist_matrix[0, cust] + dist_matrix[cust, 0]
                else:
                    prev = tour[j - 2]
                    cost = cost - dist_matrix[prev, 0] + dist_matrix[prev, cust] + dist_matrix[cust, 0]

                cand = V[i] + cost
                if cand < V[j]:
                    V[j] = cand

        return V[n]

    # Constrained vehicle count: 2D DP table V[j, v]
    K = max_vehicles
    V_mat = np.full((n + 1, K + 1), 1e12, dtype=np.float64)
    V_mat[0, 0] = 0.0

    for v in range(1, K + 1):
        for i in range(n):
            if V_mat[i, v - 1] >= 1e12:
                continue
            load = 0.0
            cost = 0.0

            for j in range(i + 1, n + 1):
                cust = tour[j - 1]
                load += demands[cust]
                if load > capacity:
                    break

                if j == i + 1:
                    cost = dist_matrix[0, cust] + dist_matrix[cust, 0]
                else:
                    prev = tour[j - 2]
                    cost = cost - dist_matrix[prev, 0] + dist_matrix[prev, cust] + dist_matrix[cust, 0]

                cand = V_mat[i, v - 1] + cost
                if cand < V_mat[j, v]:
                    V_mat[j, v] = cand

    # Check best feasible cost using <= K vehicles
    min_cost = 1e12
    for v in range(1, K + 1):
        if V_mat[n, v] < min_cost:
            min_cost = V_mat[n, v]

    if min_cost < 1e12:
        return min_cost

    # If infeasible with K vehicles, fall back to unconstrained + overflow penalty
    unconstrained_cost = _split_cost_numba(tour, dist_matrix, demands, capacity, max_vehicles=-1)
    return unconstrained_cost + overflow_penalty


@njit
def _split_dag_with_pred(
    tour: np.ndarray,
    dist_matrix: np.ndarray,
    demands: np.ndarray,
    capacity: float,
    max_vehicles: int = -1,
) -> tuple[float, np.ndarray, int]:
    """Execute Prins Split returning shortest path cost, predecessor array, and best vehicle count.

    Returns:
        (total_cost, pred_array, best_v)
    """
    n = len(tour)
    if n == 0:
        return 0.0, np.full(1, -1, dtype=np.int64), 0

    if max_vehicles <= 0:
        V = np.full(n + 1, 1e12, dtype=np.float64)
        pred = np.full(n + 1, -1, dtype=np.int64)
        V[0] = 0.0

        for i in range(n):
            if V[i] >= 1e12:
                continue
            load = 0.0
            cost = 0.0

            for j in range(i + 1, n + 1):
                cust = tour[j - 1]
                load += demands[cust]
                if load > capacity:
                    break

                if j == i + 1:
                    cost = dist_matrix[0, cust] + dist_matrix[cust, 0]
                else:
                    prev = tour[j - 2]
                    cost = cost - dist_matrix[prev, 0] + dist_matrix[prev, cust] + dist_matrix[cust, 0]

                cand = V[i] + cost
                if cand < V[j]:
                    V[j] = cand
                    pred[j] = i

        return V[n], pred, 0

    # Constrained vehicle count
    K = max_vehicles
    V_mat = np.full((n + 1, K + 1), 1e12, dtype=np.float64)
    pred_mat = np.full((n + 1, K + 1), -1, dtype=np.int64)
    V_mat[0, 0] = 0.0

    for v in range(1, K + 1):
        for i in range(n):
            if V_mat[i, v - 1] >= 1e12:
                continue
            load = 0.0
            cost = 0.0

            for j in range(i + 1, n + 1):
                cust = tour[j - 1]
                load += demands[cust]
                if load > capacity:
                    break

                if j == i + 1:
                    cost = dist_matrix[0, cust] + dist_matrix[cust, 0]
                else:
                    prev = tour[j - 2]
                    cost = cost - dist_matrix[prev, 0] + dist_matrix[prev, cust] + dist_matrix[cust, 0]

                cand = V_mat[i, v - 1] + cost
                if cand < V_mat[j, v]:
                    V_mat[j, v] = cand
                    pred_mat[j, v] = i

    best_v = 1
    best_cost = 1e12
    for v in range(1, K + 1):
        if V_mat[n, v] < best_cost:
            best_cost = V_mat[n, v]
            best_v = v

    if best_cost < 1e12:
        return best_cost, pred_mat[:, best_v], best_v

    # Fall back to unconstrained
    cost_unc, pred_unc, _ = _split_dag_with_pred(tour, dist_matrix, demands, capacity, max_vehicles=-1)
    return cost_unc, pred_unc, -1


def prins_split(
    problem: Problem,
    tour: Sequence[int] | np.ndarray,
    max_vehicles: int | None = None,
) -> tuple[float, list[Route], bool, dict[str, list[str]]]:
    """Partition a giant tour into feasible vehicle routes adhering to capacity and time windows.

    Args:
        problem: Problem instance with depot, customers, and precomputed matrices.
        tour: Sequence of 1-based customer indices (e.g. 1 to n).
        max_vehicles: Optional limit on the number of vehicle routes.

    Returns:
        (total_cost, routes, is_feasible, violations_dict)
    """
    tour_arr = np.asarray(tour, dtype=np.int64)
    n = len(tour_arr)
    if n == 0:
        return 0.0, [], True, {}

    if problem.distance_matrix is None:
        problem.compute_euclidean_matrices()

    dist_mat = np.asarray(problem.distance_matrix, dtype=np.float64)
    time_mat = (
        np.asarray(problem.travel_time_matrix, dtype=np.float64)
        if problem.travel_time_matrix is not None
        else dist_mat
    )

    # Demands array: index 0 is depot (demand 0.0), 1..n are customers
    demands = np.zeros(problem.num_customers + 1, dtype=np.float64)
    for idx, c in enumerate(problem.customers, start=1):
        demands[idx] = c.demand

    capacity = problem.vehicles[0].capacity if problem.vehicles else 100.0
    limit_v = max_vehicles if max_vehicles is not None else -1

    cost, pred, best_v = _split_dag_with_pred(tour_arr, dist_mat, demands, capacity, limit_v)

    # Backtrack route segments from pred array
    segments: list[list[int]] = []
    curr = n
    while curr > 0:
        p = int(pred[curr])
        if p < 0 or p >= curr:
            # If backtracking failed due to overflow, break
            break
        # Customers from p to curr - 1
        seg = [int(tour_arr[k]) for k in range(p, curr)]
        segments.append(seg)
        curr = p

    segments.reverse()

    routes: list[Route] = []
    violations: dict[str, list[str]] = {}
    is_feasible = True

    if max_vehicles is not None and len(segments) > max_vehicles:
        is_feasible = False
        violations.setdefault("max_vehicles", []).append(
            f"Required {len(segments)} routes, exceeding max limit of {max_vehicles}"
        )

    # Build Route objects with time window simulation
    vehicle_pool = problem.vehicles
    for r_idx, seg in enumerate(segments):
        veh_id = vehicle_pool[r_idx].id if r_idx < len(vehicle_pool) else f"V_{r_idx + 1}"
        stop_ids: list[str] = []
        arrival_times: list[float] = []
        route_load = 0.0
        route_dist = 0.0

        current_time = problem.depot.ready_time
        prev_node = 0

        for cust_idx in seg:
            cust = problem.customers[cust_idx - 1]
            stop_ids.append(cust.id)
            route_load += cust.demand

            leg_dist = dist_mat[prev_node, cust_idx]
            leg_time = time_mat[prev_node, cust_idx]
            route_dist += leg_dist

            arrival = current_time + leg_time
            arrival_times.append(arrival)

            # Time window verification
            if arrival > cust.due_time:
                is_feasible = False
                violations.setdefault("time_window", []).append(
                    f"Stop {cust.id} reached at {arrival:.2f}, due time {cust.due_time:.2f}"
                )

            start_service = max(arrival, cust.ready_time)
            current_time = start_service + cust.service_time
            prev_node = cust_idx

        # Return to depot
        leg_dist = dist_mat[prev_node, 0]
        leg_time = time_mat[prev_node, 0]
        route_dist += leg_dist
        final_depot_arrival = current_time + leg_time

        if final_depot_arrival > problem.depot.due_time:
            is_feasible = False
            violations.setdefault("depot_due_time", []).append(
                f"Vehicle {veh_id} returned at {final_depot_arrival:.2f} > {problem.depot.due_time:.2f}"
            )

        if route_load > capacity:
            is_feasible = False
            violations.setdefault("capacity", []).append(
                f"Vehicle {veh_id} load {route_load:.1f} > capacity {capacity:.1f}"
            )

        duration = final_depot_arrival - problem.depot.ready_time
        routes.append(
            Route(
                vehicle_id=veh_id,
                stop_ids=stop_ids,
                arrival_times=arrival_times,
                load=route_load,
                distance=route_dist,
                duration=duration,
            )
        )

    # Recalculate total cost as sum of route distances
    total_cost = sum(r.distance for r in routes)
    return total_cost, routes, is_feasible, violations
