"""Local Search Engine for CVRPTW.

Implements:
- Intra-route 2-Opt
- Inter-route Relocate (Insertion)
- Inter-route Swap
- First-improvement search strategy
- Neighbour-list pruning for rapid neighborhood exploration
- Continuous random-key write-back for memetic swarm integration
"""

from __future__ import annotations

from typing import Sequence
import numpy as np


def build_neighbour_list(dist_matrix: np.ndarray, k_nearest: int = 15) -> np.ndarray:
    """Precompute the k nearest customer neighbours for each node.

    Args:
        dist_matrix: (n+1) x (n+1) distance matrix where 0 is depot.
        k_nearest: Number of nearest neighbours to store per customer.

    Returns:
        (n+1) x k array of nearest customer indices (1-based).
    """
    n = dist_matrix.shape[0] - 1
    k = min(k_nearest, max(1, n - 1))
    neighbours = np.zeros((n + 1, k), dtype=np.int64)

    for i in range(1, n + 1):
        # Exclude depot (0) and self (i)
        dists = dist_matrix[i, 1:].copy()
        dists[i - 1] = 1e12  # mask self
        # argsort + 1 gives 1-based customer indices
        closest = np.argsort(dists)[:k] + 1
        neighbours[i] = closest

    return neighbours


def route_cost(route: Sequence[int], dist_matrix: np.ndarray) -> float:
    """Compute total distance of a route starting and ending at depot (0)."""
    if not route:
        return 0.0
    cost = dist_matrix[0, route[0]]
    for idx in range(len(route) - 1):
        cost += dist_matrix[route[idx], route[idx + 1]]
    cost += dist_matrix[route[-1], 0]
    return float(cost)


def total_routes_cost(routes: list[list[int]], dist_matrix: np.ndarray) -> float:
    """Compute total distance across all vehicle routes."""
    return sum(route_cost(r, dist_matrix) for r in routes)


def intra_route_2opt(route: list[int], dist_matrix: np.ndarray) -> bool:
    """Apply intra-route 2-opt using first-improvement.

    Returns True if an improving 2-opt inversion was executed.
    """
    p = len(route)
    if p < 3:
        return False

    for i in range(p - 1):
        c_prev = 0 if i == 0 else route[i - 1]
        c_i = route[i]

        for j in range(i + 1, p):
            c_j = route[j]
            c_next = 0 if j == p - 1 else route[j + 1]

            # In symmetric TSP/VRP, delta is:
            # - dist(c_prev, c_i) - dist(c_j, c_next) + dist(c_prev, c_j) + dist(c_i, c_next)
            delta = (
                dist_matrix[c_prev, c_j]
                + dist_matrix[c_i, c_next]
                - dist_matrix[c_prev, c_i]
                - dist_matrix[c_j, c_next]
            )

            if delta < -1e-7:
                route[i : j + 1] = route[i : j + 1][::-1]
                return True

    return False


def inter_route_relocate(
    routes: list[list[int]],
    loads: list[float],
    dist_matrix: np.ndarray,
    demands: np.ndarray,
    capacity: float,
    neighbour_set: dict[int, set[int]] | None = None,
) -> bool:
    """Apply inter-route relocate (single customer insertion) using first-improvement.

    Returns True if an improving customer relocation was executed.
    """
    num_routes = len(routes)
    if num_routes < 2:
        return False

    for r1 in range(num_routes):
        route1 = routes[r1]
        p1 = len(route1)
        if p1 <= 1:
            continue

        for i in range(p1):
            u = route1[i]
            d_u = demands[u]

            u_prev = 0 if i == 0 else route1[i - 1]
            u_next = 0 if i == p1 - 1 else route1[i + 1]

            # Cost change for removing u from route 1
            delta_remove = (
                dist_matrix[u_prev, u_next]
                - dist_matrix[u_prev, u]
                - dist_matrix[u, u_next]
            )

            for r2 in range(num_routes):
                if r1 == r2:
                    continue

                # Capacity check
                if loads[r2] + d_u > capacity:
                    continue

                route2 = routes[r2]
                p2 = len(route2)

                # Prune with neighbour set if provided
                if neighbour_set is not None:
                    u_nb = neighbour_set.get(u)
                    if u_nb is not None and not any(node in u_nb for node in route2):
                        continue

                # Try inserting u before first, between, or after last
                for j in range(-1, p2):
                    v_prev = 0 if j == -1 else route2[j]
                    v_next = 0 if j == p2 - 1 else route2[j + 1]

                    delta_insert = (
                        dist_matrix[v_prev, u]
                        + dist_matrix[u, v_next]
                        - dist_matrix[v_prev, v_next]
                    )

                    total_delta = delta_remove + delta_insert
                    if total_delta < -1e-7:
                        # Execute relocation
                        route1.pop(i)
                        route2.insert(j + 1, u)
                        loads[r1] -= d_u
                        loads[r2] += d_u
                        return True

    return False


def inter_route_swap(
    routes: list[list[int]],
    loads: list[float],
    dist_matrix: np.ndarray,
    demands: np.ndarray,
    capacity: float,
    neighbour_set: dict[int, set[int]] | None = None,
) -> bool:
    """Apply inter-route swap (exchange two customers) using first-improvement.

    Returns True if an improving customer swap was executed.
    """
    num_routes = len(routes)
    if num_routes < 2:
        return False

    for r1 in range(num_routes):
        route1 = routes[r1]
        p1 = len(route1)
        if p1 == 0:
            continue

        for i in range(p1):
            u = route1[i]
            d_u = demands[u]

            u_prev = 0 if i == 0 else route1[i - 1]
            u_next = 0 if i == p1 - 1 else route1[i + 1]

            for r2 in range(r1 + 1, num_routes):
                route2 = routes[r2]
                p2 = len(route2)
                if p2 == 0:
                    continue

                for j in range(p2):
                    v = route2[j]
                    d_v = demands[v]

                    # Joint capacity feasibility check
                    if loads[r1] - d_u + d_v > capacity:
                        continue
                    if loads[r2] - d_v + d_u > capacity:
                        continue

                    # Prune with neighbour list if provided
                    if neighbour_set is not None:
                        u_nb = neighbour_set.get(u)
                        if u_nb is not None and v not in u_nb:
                            continue

                    v_prev = 0 if j == 0 else route2[j - 1]
                    v_next = 0 if j == p2 - 1 else route2[j + 1]

                    delta1 = (
                        dist_matrix[u_prev, v]
                        + dist_matrix[v, u_next]
                        - dist_matrix[u_prev, u]
                        - dist_matrix[u, u_next]
                    )
                    delta2 = (
                        dist_matrix[v_prev, u]
                        + dist_matrix[u, v_next]
                        - dist_matrix[v_prev, v]
                        - dist_matrix[v, v_next]
                    )

                    total_delta = delta1 + delta2
                    if total_delta < -1e-7:
                        # Execute swap
                        route1[i] = v
                        route2[j] = u
                        loads[r1] = loads[r1] - d_u + d_v
                        loads[r2] = loads[r2] - d_v + d_u
                        return True

    return False


def run_local_search(
    routes: list[list[int]],
    dist_matrix: np.ndarray,
    demands: np.ndarray,
    capacity: float,
    neighbour_matrix: np.ndarray | None = None,
    max_passes: int = 50,
) -> tuple[list[list[int]], float]:
    """Execute composite local search (2-opt, relocate, swap) until local minimum.

    Args:
        routes: List of routes, each a list of 1-based customer indices.
        dist_matrix: (n+1) x (n+1) distance matrix.
        demands: 1D array of customer demands.
        capacity: Vehicle capacity limit.
        neighbour_matrix: Optional precomputed nearest neighbors.
        max_passes: Maximum iterations through all neighborhood operators.

    Returns:
        (improved_routes, total_cost)
    """
    # Deep copy routes so original caller is not mutated unexpectedly
    routes_copy = [list(r) for r in routes if r]
    loads = [float(sum(demands[c] for c in r)) for r in routes_copy]

    neighbour_set: dict[int, set[int]] | None = None
    if neighbour_matrix is not None:
        neighbour_set = {
            i: set(neighbour_matrix[i]) for i in range(1, neighbour_matrix.shape[0])
        }

    for _ in range(max_passes):
        improved = False

        # 1. Intra-route 2-Opt on each route
        for r in routes_copy:
            if intra_route_2opt(r, dist_matrix):
                improved = True
                break

        if improved:
            continue

        # 2. Inter-route Relocate
        if inter_route_relocate(
            routes_copy, loads, dist_matrix, demands, capacity, neighbour_set
        ):
            # Clean up empty routes
            routes_copy = [r for r in routes_copy if r]
            loads = [float(sum(demands[c] for c in r)) for r in routes_copy]
            improved = True
            continue

        # 3. Inter-route Swap
        if inter_route_swap(
            routes_copy, loads, dist_matrix, demands, capacity, neighbour_set
        ):
            improved = True
            continue

        # If no operator found an improvement, local optimum reached
        if not improved:
            break

    # Clean empty routes
    routes_copy = [r for r in routes_copy if r]
    total_cost = total_routes_cost(routes_copy, dist_matrix)
    return routes_copy, total_cost


def flatten_routes(routes: list[list[int]]) -> list[int]:
    """Concatenate customer routes into a giant tour permutation (1-based indices)."""
    flat: list[int] = []
    for r in routes:
        flat.extend(r)
    return flat


def project_tour_to_keys(old_keys: np.ndarray, improved_tour: Sequence[int]) -> np.ndarray:
    """Write back an improved customer permutation into continuous random keys.

    Preserves the exact values and distribution of old_keys while ensuring
    that np.argsort(new_keys) + 1 yields improved_tour precisely.

    Args:
        old_keys: 1D float array of particle keys in [0, 1].
        improved_tour: Sequence of 1-based customer indices in visiting order.

    Returns:
        1D float array of updated keys.
    """
    sorted_keys = np.sort(old_keys)
    new_keys = np.empty_like(old_keys)

    for rank, cust_id in enumerate(improved_tour):
        # cust_id is 1-based, index in keys is cust_id - 1
        new_keys[cust_id - 1] = sorted_keys[rank]

    return new_keys
