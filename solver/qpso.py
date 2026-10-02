"""Quantum-behaved Particle Swarm Optimization (QPSO) for CVRPTW.

Implements classical QPSO (Sun, Feng & Xu, 2004) over a continuous random-key space.
Each particle is a vector in [0, 1]^n, decoded into a giant tour via argsort,
and evaluated using the Prins Split algorithm.
Supports memetic local search integration (2-opt, relocate, swap) with random-key write-back.
"""

from __future__ import annotations

import time
from typing import Callable
import numpy as np
from pydantic import BaseModel, Field

from solver.local_search import (
    build_neighbour_list,
    flatten_routes,
    project_tour_to_keys,
    run_local_search,
)
from solver.models import Problem, Solution
from solver.split import _split_cost_numba, prins_split


class QPSOConfig(BaseModel):
    """Configuration parameters for the QPSO solver."""

    num_particles: int = Field(40, ge=2, description="Swarm size (M)")
    max_iters: int = Field(500, ge=1, description="Maximum iterations (T)")
    alpha_max: float = Field(1.0, gt=0.0, description="Initial contraction-expansion coefficient")
    alpha_min: float = Field(0.5, gt=0.0, description="Final contraction-expansion coefficient")
    seed: int | None = Field(None, description="Random seed for reproducible execution")
    max_vehicles: int | None = Field(None, description="Optional cap on vehicle count")

    # Memetic local search settings
    local_search_freq: int = Field(
        20,
        description="Apply local search every m iterations (<=0 to disable)",
    )
    local_search_top_k: int = Field(
        3,
        ge=1,
        description="Number of top particles to refine with local search",
    )
    use_neighbour_list: bool = Field(
        True,
        description="Whether to use nearest-neighbour list pruning in local search",
    )
    k_nearest: int = Field(15, ge=2, description="Number of nearest neighbours per customer")


def solve_qpso(
    problem: Problem,
    config: QPSOConfig | None = None,
    callback: Callable[[int, float], None] | None = None,
) -> tuple[Solution, list[float]]:
    """Execute QPSO to optimize vehicle routes for a given CVRPTW problem instance.

    Args:
        problem: Fully initialized Problem instance.
        config: QPSOConfig options. If None, default settings are used.
        callback: Optional callback(iteration, gbest_cost) invoked at each step.

    Returns:
        (Solution, cost_history) where cost_history records gbest cost per iteration.
    """
    if config is None:
        config = QPSOConfig()

    start_time = time.perf_counter()
    rng = np.random.default_rng(config.seed)

    n = problem.num_customers
    if n == 0:
        return Solution(
            routes=[],
            total_cost=0.0,
            is_feasible=True,
            violations={},
            algorithm="QPSO",
            execution_time_sec=0.0,
            seed=config.seed,
        ), [0.0]

    # Precompute Euclidean / routing matrices if not already prepared
    if problem.distance_matrix is None:
        problem.compute_euclidean_matrices()

    dist_mat = np.asarray(problem.distance_matrix, dtype=np.float64)
    demands = np.zeros(n + 1, dtype=np.float64)
    for idx, c in enumerate(problem.customers, start=1):
        demands[idx] = c.demand

    capacity = problem.vehicles[0].capacity if problem.vehicles else 100.0
    limit_v = config.max_vehicles if config.max_vehicles is not None else -1

    M = config.num_particles
    T = config.max_iters

    # Precompute neighbour list if local search is enabled
    neighbour_mat = (
        build_neighbour_list(dist_mat, config.k_nearest)
        if (config.local_search_freq > 0 and config.use_neighbour_list)
        else None
    )

    # 1. Initialize particle positions uniformly in [0, 1]^n
    X = rng.uniform(0.0, 1.0, size=(M, n))

    # Personal best positions and costs
    P = np.copy(X)
    pbest_costs = np.full(M, np.inf, dtype=np.float64)

    gbest_x = np.copy(X[0])
    gbest_cost = np.inf

    # Initial evaluation
    for i in range(M):
        tour = np.argsort(X[i]) + 1
        cost = _split_cost_numba(tour, dist_mat, demands, capacity, limit_v)
        pbest_costs[i] = cost
        if cost < gbest_cost:
            gbest_cost = cost
            gbest_x = np.copy(X[i])

    cost_history: list[float] = [float(gbest_cost)]

    # 2. Main QPSO iteration loop
    for t in range(T):
        # Linearly anneal alpha from alpha_max down to alpha_min
        alpha = config.alpha_max - (t / T) * (config.alpha_max - config.alpha_min)

        # Center of gravity: mean best position across all particles
        mbest = np.mean(P, axis=0)

        for i in range(M):
            # Stochastic local attractor p_id = phi * pbest_id + (1 - phi) * gbest_d
            phi = rng.uniform(0.0, 1.0, size=n)
            p = phi * P[i] + (1.0 - phi) * gbest_x

            # Quantum delta-potential well wave function update
            u = rng.uniform(1e-10, 1.0, size=n)
            sign = np.where(rng.random(size=n) < 0.5, 1.0, -1.0)
            step = alpha * np.abs(mbest - X[i]) * np.log(1.0 / u)
            X[i] = p + sign * step

            # Clamp keys to [0, 1]
            X[i] = np.clip(X[i], 0.0, 1.0)

            # Evaluate cost
            tour = np.argsort(X[i]) + 1
            cost = _split_cost_numba(tour, dist_mat, demands, capacity, limit_v)

            # Update personal best
            if cost < pbest_costs[i]:
                pbest_costs[i] = cost
                P[i] = np.copy(X[i])

                # Update global best
                if cost < gbest_cost:
                    gbest_cost = cost
                    gbest_x = np.copy(X[i])

        # 3. Memetic Step: Local Search on top k particles every m iterations
        if config.local_search_freq > 0 and (t + 1) % config.local_search_freq == 0:
            top_k_indices = np.argsort(pbest_costs)[: config.local_search_top_k]

            for idx in top_k_indices:
                p_tour = np.argsort(P[idx]) + 1
                _, current_routes, is_feas, _ = prins_split(
                    problem, p_tour, max_vehicles=config.max_vehicles
                )
                if not is_feas:
                    continue

                route_indices = [
                    [problem.get_customer_index(sid) for sid in r.stop_ids]
                    for r in current_routes
                ]

                improved_routes, ls_cost = run_local_search(
                    route_indices, dist_mat, demands, capacity, neighbour_mat
                )

                if ls_cost < pbest_costs[idx] - 1e-7:
                    improved_tour = flatten_routes(improved_routes)
                    new_keys = project_tour_to_keys(P[idx], improved_tour)
                    P[idx] = new_keys
                    X[idx] = np.copy(new_keys)
                    pbest_costs[idx] = ls_cost

                    if ls_cost < gbest_cost:
                        gbest_cost = ls_cost
                        gbest_x = np.copy(new_keys)

        cost_history.append(float(gbest_cost))
        if callback is not None:
            callback(t + 1, float(gbest_cost))

    # 4. Final refinement on global best
    best_tour = np.argsort(gbest_x) + 1
    total_cost, routes, is_feasible, violations = prins_split(
        problem, best_tour, max_vehicles=config.max_vehicles
    )

    if config.local_search_freq > 0 and is_feasible:
        route_indices = [
            [problem.get_customer_index(sid) for sid in r.stop_ids]
            for r in routes
        ]
        improved_routes, final_ls_cost = run_local_search(
            route_indices, dist_mat, demands, capacity, neighbour_mat
        )
        if final_ls_cost < total_cost - 1e-7:
            improved_tour = flatten_routes(improved_routes)
            total_cost, routes, is_feasible, violations = prins_split(
                problem, improved_tour, max_vehicles=config.max_vehicles
            )

    elapsed_time = time.perf_counter() - start_time

    solution = Solution(
        routes=routes,
        total_cost=total_cost,
        is_feasible=is_feasible,
        violations=violations,
        algorithm="QPSO+LS" if config.local_search_freq > 0 else "QPSO",
        execution_time_sec=elapsed_time,
        seed=config.seed,
    )

    return solution, cost_history
