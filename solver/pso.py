"""Classical Particle Swarm Optimization (PSO) baseline for CVRPTW.

Serves as an empirical baseline to compare against the quantum-inspired QPSO solver.
Uses the identical continuous random-key encoding in [0, 1]^n and time-aware Prins Split evaluation.
"""

from __future__ import annotations

import math
import time
from typing import Any, Callable
import numpy as np
from pydantic import BaseModel, Field

from solver.models import Problem, Solution
from solver.repair import repair_solution_time_windows
from solver.split import _split_cost_numba, prins_split
from solver.tensor import CostTensor, precompute_cost_tensor
from solver.validate import validate_solution


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
    allow_extra_vehicles: bool = Field(False, description="Allow generating more routes than available fleet")

    # Driver duty limit and time window constraints
    max_duty_duration: float | None = Field(None, description="Max allowed shift duration per route")
    hard_time_windows: bool = Field(False, description="Strictly forbid time window violations during search")
    hard_duty_limit: bool = Field(False, description="Strictly forbid duty limit violations")

    # Priority customer configuration
    enforce_priority_early_service: bool = Field(
        False, description="Enforce early service window for priority customers"
    )
    priority_early_ratio: float = Field(0.5, description="Fraction of window for priority early service")

    # Adaptive penalty mechanism
    adaptive_penalty: bool = Field(True, description="Dynamically tune constraint penalty weights")
    penalty_alpha_init: float = Field(100.0, description="Initial capacity penalty weight")
    penalty_beta_init: float = Field(100.0, description="Initial time-window penalty weight")
    penalty_gamma_init: float = Field(100.0, description="Initial duty-limit penalty weight")
    adapt_freq: int = Field(5, description="Frequency (iterations) for adaptive penalty update")

    # Post-processing repair
    apply_tw_repair: bool = Field(True, description="Apply time-window repair operator on best solution")


def solve_pso(
    problem: Problem,
    config: PSOConfig | None = None,
    cost_oracle: Any | None = None,
    callback: Callable[[int, float], None] | None = None,
) -> tuple[Solution, list[float]]:
    """Execute classical PSO to optimize vehicle routes.

    Args:
        problem: Fully initialized Problem instance.
        config: PSOConfig options. If None, default settings are used.
        cost_oracle: Optional CostOracle for road network or traffic evaluation.
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

    # Precompute time-bucketed CostTensor from CostOracle or problem
    cost_tensor = precompute_cost_tensor(problem, cost_oracle=cost_oracle)
    cost_data = cost_tensor.travel_time_tensor
    dist_mat = cost_tensor.distance_matrix

    num_nodes = n + 1
    demands = np.zeros(num_nodes, dtype=np.float64)
    services = np.zeros(num_nodes, dtype=np.float64)
    ready_times = np.zeros(num_nodes, dtype=np.float64)
    due_times = np.full(num_nodes, 1e12, dtype=np.float64)
    priority_factors = np.ones(num_nodes, dtype=np.float64)

    services[0] = problem.depot.service_time
    ready_times[0] = problem.depot.ready_time
    due_times[0] = problem.depot.due_time

    for idx, c in enumerate(problem.customers, start=1):
        demands[idx] = c.demand
        services[idx] = c.service_time
        ready_times[idx] = c.ready_time
        due_times[idx] = c.due_time
        priority_factors[idx] = 1.0 + (c.priority - 1) * 2.0

        if config.enforce_priority_early_service and c.priority > 1:
            early_due = c.ready_time + config.priority_early_ratio * (c.due_time - c.ready_time)
            due_times[idx] = early_due

    capacity = problem.vehicles[0].capacity if problem.vehicles else 100.0
    limit_v = config.max_vehicles if config.max_vehicles is not None else (len(problem.vehicles) if (problem.vehicles and not config.allow_extra_vehicles) else -1)

    max_duty = -1.0
    if config.max_duty_duration is not None:
        max_duty = config.max_duty_duration
    elif problem.vehicles:
        v0 = problem.vehicles[0]
        if math.isfinite(v0.shift_end) and math.isfinite(v0.shift_start):
            diff = v0.shift_end - v0.shift_start
            if diff > 0:
                max_duty = diff

    cur_alpha = config.penalty_alpha_init
    cur_beta = config.penalty_beta_init
    cur_gamma = config.penalty_gamma_init

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

    def evaluate_particle_cost(keys: np.ndarray) -> float:
        tour = np.argsort(keys) + 1
        return _split_cost_numba(
            tour,
            cost_data,
            demands,
            capacity,
            limit_v,
            t_start=cost_tensor.t_start,
            bucket_size=cost_tensor.bucket_size,
            service_times=services,
            ready_times=ready_times,
            due_times=due_times,
            depot_due_time=problem.depot.due_time,
            priority_factors=priority_factors,
            max_duty=max_duty,
            alpha=cur_alpha,
            beta=cur_beta,
            gamma=cur_gamma,
            hard_time_windows=config.hard_time_windows,
            hard_duty_limit=config.hard_duty_limit,
        )

    # Initial evaluation
    for i in range(M):
        cost = evaluate_particle_cost(X[i])
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

            cost = evaluate_particle_cost(X[i])

            # Update personal best
            if cost < pbest_costs[i]:
                pbest_costs[i] = cost
                P[i] = np.copy(X[i])

                # Update global best
                if cost < gbest_cost:
                    gbest_cost = cost
                    gbest_x = np.copy(X[i])

        # Adaptive Penalty Update based on Swarm Feasibility Ratio
        if config.adaptive_penalty and (t + 1) % config.adapt_freq == 0:
            sample_size = min(15, M)
            feas_count = 0
            for s_idx in range(sample_size):
                p_tour = np.argsort(X[s_idx]) + 1
                _, _, is_f, _ = prins_split(
                    problem,
                    p_tour,
                    max_vehicles=config.max_vehicles,
                    cost_oracle=cost_oracle,
                    cost_tensor=cost_tensor,
                    max_duty_duration=config.max_duty_duration,
                    hard_time_windows=config.hard_time_windows,
                    hard_duty_limit=config.hard_duty_limit,
                    enforce_priority_early_service=config.enforce_priority_early_service,
                    priority_early_ratio=config.priority_early_ratio,
                    alpha=cur_alpha,
                    beta=cur_beta,
                    gamma=cur_gamma,
                )
                if is_f:
                    feas_count += 1

            feas_ratio = feas_count / sample_size
            if feas_ratio < 0.20:
                cur_alpha = min(10000.0, cur_alpha * 1.25)
                cur_beta = min(10000.0, cur_beta * 1.25)
                cur_gamma = min(10000.0, cur_gamma * 1.25)
            elif feas_ratio > 0.45:
                cur_alpha = max(1.0, cur_alpha / 1.25)
                cur_beta = max(1.0, cur_beta / 1.25)
                cur_gamma = max(1.0, cur_gamma / 1.25)

        cost_history.append(float(gbest_cost))
        if callback is not None:
            callback(t + 1, float(gbest_cost))

    elapsed_time = time.perf_counter() - start_time

    # 3. Final route assembly using full prins_split
    best_tour = np.argsort(gbest_x) + 1
    total_cost, routes, is_feasible, violations = prins_split(
        problem,
        best_tour,
        max_vehicles=config.max_vehicles,
        allow_extra_vehicles=config.allow_extra_vehicles,
        cost_oracle=cost_oracle,
        cost_tensor=cost_tensor,
        max_duty_duration=config.max_duty_duration,
        hard_time_windows=config.hard_time_windows,
        hard_duty_limit=config.hard_duty_limit,
        enforce_priority_early_service=config.enforce_priority_early_service,
        priority_early_ratio=config.priority_early_ratio,
        alpha=cur_alpha,
        beta=cur_beta,
        gamma=cur_gamma,
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

    # 4. Apply Time-Window Repair Operator if solution has residual time-window violations
    if config.apply_tw_repair and (not is_feasible or "time_window" in violations):
        solution = repair_solution_time_windows(
            problem, solution, cost_oracle=cost_oracle, max_passes=50
        )

    # 5. Independent validation stamp
    val_report = validate_solution(
        problem,
        solution,
        cost_oracle=cost_oracle,
        max_vehicles=config.max_vehicles,
        max_duty_duration=config.max_duty_duration,
        hard_duty_limit=config.hard_duty_limit,
        enforce_priority_early_service=config.enforce_priority_early_service,
        priority_early_ratio=config.priority_early_ratio,
    )
    solution.is_feasible = val_report.is_valid
    solution.violations = val_report.violations
    if solution.is_feasible:
        solution.total_cost = val_report.recomputed_cost

    return solution, cost_history
