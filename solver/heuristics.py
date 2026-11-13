"""Constructive Heuristics for CVRPTW.

Provides domain-specific constructive initialization for swarm intelligence solvers:
1. Clarke-Wright Savings Heuristic (capacity and distance optimized)
2. Nearest Neighbor Heuristic with capacity tracking
3. Polar Angle (Sweep) Heuristic around depot
4. Earliest Deadline First (EDF) Time-Window Heuristic
"""

from __future__ import annotations

import math
from typing import Sequence
import numpy as np

from solver.models import Customer, Problem


def clarke_wright_savings_tour(problem: Problem) -> list[int]:
    """Construct a giant tour permutation using Clarke-Wright Savings algorithm.

    1-based customer indices are returned (1 to n).
    """
    n = problem.num_customers
    if n == 0:
        return []
    if n == 1:
        return [1]

    dist = problem.distance_matrix
    if dist is None:
        problem.compute_euclidean_matrices()
        dist = problem.distance_matrix

    capacity = problem.vehicles[0].capacity if problem.vehicles else 100.0

    # Compute savings s_ij = d(0, i) + d(0, j) - d(i, j)
    savings: list[tuple[float, int, int]] = []
    for i in range(1, n + 1):
        for j in range(i + 1, n + 1):
            s = float(dist[0, i] + dist[0, j] - dist[i, j])
            savings.append((s, i, j))

    savings.sort(reverse=True, key=lambda x: x[0])

    routes: list[list[int]] = [[i] for i in range(1, n + 1)]
    cust_to_route: dict[int, list[int]] = {i: routes[i - 1] for i in range(1, n + 1)}

    for _, i, j in savings:
        r_i = cust_to_route[i]
        r_j = cust_to_route[j]
        if r_i is r_j:
            continue

        load_i = sum(problem.customers[c - 1].demand for c in r_i)
        load_j = sum(problem.customers[c - 1].demand for c in r_j)

        if load_i + load_j <= capacity:
            # Check endpoint configurations
            if r_i[-1] == i and r_j[0] == j:
                merged = r_i + r_j
            elif r_j[-1] == j and r_i[0] == i:
                merged = r_j + r_i
            elif r_i[0] == i and r_j[0] == j:
                merged = r_i[::-1] + r_j
            elif r_i[-1] == i and r_j[-1] == j:
                merged = r_i + r_j[::-1]
            else:
                continue

            # Update route references
            routes.remove(r_i)
            routes.remove(r_j)
            routes.append(merged)
            for c in merged:
                cust_to_route[c] = merged

    # Concatenate routes into a single giant tour permutation
    tour: list[int] = []
    for r in routes:
        tour.extend(r)

    return tour


def nearest_neighbor_tour(problem: Problem) -> list[int]:
    """Construct a giant tour using Nearest Neighbor heuristic with capacity resets."""
    n = problem.num_customers
    if n <= 1:
        return list(range(1, n + 1))

    dist = problem.distance_matrix
    if dist is None:
        problem.compute_euclidean_matrices()
        dist = problem.distance_matrix

    capacity = problem.vehicles[0].capacity if problem.vehicles else 100.0
    unvisited = set(range(1, n + 1))
    tour: list[int] = []

    while unvisited:
        curr = 0  # Start at depot
        curr_load = 0.0

        while unvisited:
            best_next = None
            best_dist = 1e12

            for cand in unvisited:
                d_c = problem.customers[cand - 1].demand
                if curr_load + d_c <= capacity:
                    d = float(dist[curr, cand])
                    if d < best_dist:
                        best_dist = d
                        best_next = cand

            if best_next is None:
                # No unvisited customer fits in current vehicle capacity; return to depot
                break

            tour.append(best_next)
            unvisited.remove(best_next)
            curr_load += problem.customers[best_next - 1].demand
            curr = best_next

    return tour


def sweep_tour(problem: Problem) -> list[int]:
    """Construct a giant tour by sweeping polar angles around the depot."""
    n = problem.num_customers
    if n <= 1:
        return list(range(1, n + 1))

    d_lat = problem.depot.lat
    d_lon = problem.depot.lon

    angles: list[tuple[float, int]] = []
    for idx, c in enumerate(problem.customers, start=1):
        # Calculate angle theta relative to depot
        dy = c.lat - d_lat
        dx = c.lon - d_lon
        theta = math.atan2(dy, dx)
        angles.append((theta, idx))

    angles.sort(key=lambda x: x[0])
    return [idx for _, idx in angles]


def time_window_tour(problem: Problem) -> list[int]:
    """Construct a giant tour sorted by customer due times (Earliest Deadline First)."""
    n = problem.num_customers
    if n <= 1:
        return list(range(1, n + 1))

    cust_due: list[tuple[float, int]] = []
    for idx, c in enumerate(problem.customers, start=1):
        cust_due.append((c.due_time, idx))

    cust_due.sort(key=lambda x: x[0])
    return [idx for _, idx in cust_due]


def tour_to_keys(tour: Sequence[int], n: int) -> np.ndarray:
    """Project a 1-based customer permutation into continuous keys in [0, 1]^n.

    Guarantees np.argsort(keys) + 1 == tour.
    """
    keys = np.zeros(n, dtype=np.float64)
    step = 1.0 / (n + 1)
    for rank, cust_id in enumerate(tour):
        # cust_id is 1-based, index is cust_id - 1
        keys[cust_id - 1] = (rank + 1) * step
    return keys


def generate_heuristic_tours(problem: Problem) -> list[list[int]]:
    """Generate a diverse ensemble of high-quality heuristic tours."""
    n = problem.num_customers
    if n <= 1:
        return [list(range(1, n + 1))]

    tours: list[list[int]] = []

    # 1. Clarke-Wright
    try:
        t_cw = clarke_wright_savings_tour(problem)
        if len(t_cw) == n:
            tours.append(t_cw)
    except Exception:
        pass

    # 2. Polar Sweep
    try:
        t_sw = sweep_tour(problem)
        if len(t_sw) == n:
            tours.append(t_sw)
    except Exception:
        pass

    # 3. Nearest Neighbor
    try:
        t_nn = nearest_neighbor_tour(problem)
        if len(t_nn) == n:
            tours.append(t_nn)
    except Exception:
        pass

    # 4. Due Time (EDF)
    try:
        t_tw = time_window_tour(problem)
        if len(t_tw) == n:
            tours.append(t_tw)
    except Exception:
        pass

    if not tours:
        tours.append(list(range(1, n + 1)))

    return tours
