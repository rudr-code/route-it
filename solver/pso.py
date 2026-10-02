"""Classical Particle Swarm Optimization (PSO) baseline for CVRPTW.

Serves as an empirical baseline to compare against the quantum-inspired QPSO solver.
Uses the identical continuous random-key encoding in [0, 1]^n and Prins Split evaluation.
"""

from __future__ import annotations

import time
from typing import Any, Callable
import numpy as np
from pydantic import BaseModel, Field

from solver.models import Problem, Solution
from solver.split import _split_cost_numba, prins_split


class PSOConfig(BaseModel):
    """Configuration parameters for the classical PSO baseline solver."""

    num_particles: int = Field(40, ge=2, description="Swarm size (M)")
    max_iters: int = Field(500, ge=1, description="Maximum iterations (T)")
    inertia_weight: float = Field(0.7298, description="Inertia weight (w)")
    c1: float = Field(1.49618, description="Cognitive acceleration coefficient (c1)")
    c2: float = Field(1.49618, description="Social acceleration coefficient (c2)")
    v_max: float = Field(0.2, gt=0.0, description="Maximum velocity boundary")
    seed: int | None = Field(None, description="Random seed for reproducibility")
    max_vehicles: int | None = Field(None, description="Optional cap on vehicle count")


def solve_pso(
    problem: Problem,
    config: PSOConfig | None = None,
    callback: Callable[[int, float], None] | None = None,
) -> tuple[Solution, list[float]]:
    """Execute classical PSO to optimize vehicle routes.

    Args:
        problem: Fully initialized Problem instance.
        config: PSOConfig options. If None, default settings are used.
        callback: Optional callback(iteration, gbest_cost) invoked at each step.

    Returns:
        (Solution, cost_history) where cost_history records gbest cost per iteration.
    """
    if config is None:
        config = PSOConfig()

    start_time = time.perf_counter()
    rng = np.random.default_rng(config.seed)

    n = problem.num_customers
    if n == 0:
        return Solution(
            routes=[],
            total_cost=0.0,
            is_feasible=True,
            violations={},
            algorithm="PSO",
            execution_time_sec=0.0,
            seed=config.seed,
        ), [0.0]

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
    w = config.inertia_weight
    c1 = config.c1
    c2 = config.c2
    v_max = config.v_max

    # 1. Initialize positions in [0, 1]^n and velocities in [-v_max, v_max]^n
    X = rng.uniform(0.0, 1.0, size=(M, n))
    V = rng.uniform(-v_max, v_max, size=(M, n))

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

    # 2. Main PSO iteration loop
    for t in range(T):
        for i in range(M):
            r1 = rng.uniform(0.0, 1.0, size=n)
            r2 = rng.uniform(0.0, 1.0, size=n)

            # Classical velocity update
            V[i] = w * V[i] + c1 * r1 * (P[i] - X[i]) + c2 * r2 * (gbest_x - X[i])
            V[i] = np.clip(V[i], -v_max, v_max)

            # Position update
            X[i] = np.clip(X[i] + V[i], 0.0, 1.0)

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

        cost_history.append(float(gbest_cost))
        if callback is not None:
            callback(t + 1, float(gbest_cost))

    elapsed_time = time.perf_counter() - start_time

    # 3. Final route assembly using full prins_split
    best_tour = np.argsort(gbest_x) + 1
    total_cost, routes, is_feasible, violations = prins_split(
        problem, best_tour, max_vehicles=config.max_vehicles
    )

    solution = Solution(
        routes=routes,
        total_cost=total_cost,
        is_feasible=is_feasible,
        violations=violations,
        algorithm="PSO",
        execution_time_sec=elapsed_time,
        seed=config.seed,
    )

    return solution, cost_history
