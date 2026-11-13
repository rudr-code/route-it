"""Quantum-behaved Particle Swarm Optimization (QPSO) for CVRPTW.

Implements classical QPSO (Sun, Feng & Xu, 2004) over a continuous random-key space.
Each particle is a vector in [0, 1]^n, decoded into a giant tour via argsort,
and evaluated using the time-aware Prins Split algorithm.
Supports adaptive penalties, memetic local search, driver duty limits,
priority customer window scaling, and time-window repair operators.
"""

from __future__ import annotations

import math
import time
from typing import Any, Callable
import numpy as np
from pydantic import BaseModel, Field

from solver.heuristics import generate_heuristic_tours, tour_to_keys
from solver.local_search import (
    build_neighbour_list,
    flatten_routes,
    project_tour_to_keys,
    run_local_search,
)
from solver.models import Problem, Solution
from solver.repair import repair_solution, repair_solution_time_windows
from solver.split import _split_cost_numba, prins_split
from solver.tensor import CostTensor, precompute_cost_tensor
from solver.validate import validate_solution


class QPSOConfig(BaseModel):
    """Configuration parameters for the QPSO solver."""

    num_particles: int = Field(40, ge=2, description="Swarm size (M)")
    max_iters: int = Field(500, ge=1, description="Maximum iterations (T)")
    alpha_max: float = Field(1.0, gt=0.0, description="Initial contraction-expansion coefficient")
    alpha_min: float = Field(0.5, gt=0.0, description="Final contraction-expansion coefficient")
    seed: int | None = Field(None, description="Random seed for reproducible execution")
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
    cost_oracle: Any | None = None,
    callback: Callable[[int, float], None] | None = None,
    seed_keys: np.ndarray | None = None,
    seed_fraction: float = 0.5,
) -> tuple[Solution, list[float]]:
    """Execute QPSO to optimize vehicle routes for a given CVRPTW problem instance.

    Args:
        problem: Fully initialized Problem instance.
        config: QPSOConfig options. If None, default settings are used.
        cost_oracle: Optional CostOracle for road network or traffic evaluation.
        callback: Optional callback(iteration, gbest_cost) invoked at each step.
        seed_keys: Optional initial continuous keys array of size n to warm-start the swarm.
        seed_fraction: Fraction of swarm particles initialized around seed_keys (default: 0.5).

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

    is_comp = getattr(problem, "effective_time_window_boundary", getattr(problem, "time_window_boundary", "completion")) == "completion"
    for idx, c in enumerate(problem.customers, start=1):
        demands[idx] = c.demand
        services[idx] = c.service_time
        ready_times[idx] = c.ready_time
        base_due = (c.due_time - c.service_time) if is_comp else c.due_time
        due_times[idx] = max(c.ready_time, base_due)
        priority_factors[idx] = 1.0 + (c.priority - 1) * 2.0

        if config.enforce_priority_early_service and c.priority > 1:
            early_due = c.ready_time + config.priority_early_ratio * (c.due_time - c.ready_time)
            eff_early = (early_due - c.service_time) if is_comp else early_due
            due_times[idx] = max(c.ready_time, eff_early)

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

    # Adaptive penalty parameters
    cur_alpha = config.penalty_alpha_init
    cur_beta = config.penalty_beta_init
    cur_gamma = config.penalty_gamma_init

    M = config.num_particles
    T = config.max_iters

    # Precompute neighbour list if local search is enabled
    neighbour_mat = (
        build_neighbour_list(dist_mat, config.k_nearest)
        if (config.local_search_freq > 0 and config.use_neighbour_list)
        else None
    )

    # 1. Constructive Swarm Initialization
    # Seed initial particles with domain heuristics (Clarke-Wright, Sweep, Nearest-Neighbor, EDF)
    # so the quantum swarm starts in feasible, high-packing 4-vehicle territory rather than random noise.
    heur_tours = generate_heuristic_tours(problem)
    X = np.empty((M, n), dtype=np.float64)

    # Place clean heuristic permutations into initial particles
    num_heur = min(M, len(heur_tours))
    for h_idx in range(num_heur):
        X[h_idx] = tour_to_keys(heur_tours[h_idx], n)

    # Seed perturbed variants around top heuristic tours (Clarke-Wright & Sweep)
    num_seeded = min(M, max(num_heur, int(M * seed_fraction)))
    for i in range(num_heur, num_seeded):
        base_h = heur_tours[(i - num_heur) % num_heur]
        base_keys = tour_to_keys(base_h, n)
        noise = rng.normal(0.0, 0.03, size=n)
        X[i] = np.clip(base_keys + noise, 0.001, 0.999)

    # If caller provided explicit seed_keys, honour on first particle
    if seed_keys is not None and len(seed_keys) == n:
        X[0] = np.clip(seed_keys, 0.001, 0.999)

    # Fill remaining particles with uniform random keys for global exploration
    for i in range(num_seeded, M):
        X[i] = rng.uniform(0.001, 0.999, size=n)

    # Personal best positions and costs
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
    stagnation_counter = 0
    prev_gbest_cost = float(gbest_cost)

    # 2. Main QPSO iteration loop
    # In quantum-behaved PSO (Sun et al., 2004), each particle is bound to a delta potential well
    # centered at the stochastic local attractor p. The wave function obeys Schrödinger's equation,
    # yielding double-exponential probability distribution for coordinates, enabling quantum tunneling
    # through local sub-optimal barriers without classical velocity divergence.
    for t in range(T):
        # Linearly anneal contraction-expansion parameter alpha (beta) from alpha_max down to alpha_min
        ce_alpha = config.alpha_max - (t / T) * (config.alpha_max - config.alpha_min)

        # Center of gravity: mean best position across all particles (mbest)
        mbest = np.mean(P, axis=0)

        for i in range(M):
            # Stochastic local attractor between personal best and global best
            phi = rng.uniform(0.0, 1.0, size=n)
            p = phi * P[i] + (1.0 - phi) * gbest_x

            # Quantum delta-potential well wave function collapse: step = alpha * |mbest - X| * ln(1/u)
            u = rng.uniform(1e-8, 1.0, size=n)
            sign = np.where(rng.random(size=n) < 0.5, 1.0, -1.0)
            step = ce_alpha * np.abs(mbest - X[i]) * np.log(1.0 / u)
            X[i] = p + sign * step

            # Clamp continuous keys safely inside (0, 1)
            X[i] = np.clip(X[i], 0.001, 0.999)

            cost = evaluate_particle_cost(X[i])

            if cost < pbest_costs[i]:
                pbest_costs[i] = cost
                P[i] = np.copy(X[i])

                if cost < gbest_cost:
                    gbest_cost = cost
                    gbest_x = np.copy(X[i])

        # Stagnation detection & diverse re-seeding: if gbest stalled for 8 iterations, revitalize swarm
        if gbest_cost < prev_gbest_cost - 1e-4:
            stagnation_counter = 0
            prev_gbest_cost = float(gbest_cost)
        else:
            stagnation_counter += 1
            if stagnation_counter >= 8:
                # Re-seed the bottom 60% particles
                worst_indices = np.argsort(pbest_costs)[int(M * 0.4):]
                for idx in worst_indices:
                    if rng.random() < 0.5:
                        noise = rng.normal(0.0, 0.05, size=n)
                        X[idx] = np.clip(gbest_x + noise, 0.001, 0.999)
                    else:
                        rand_h = heur_tours[rng.integers(0, len(heur_tours))]
                        rand_k = tour_to_keys(rand_h, n)
                        noise = rng.normal(0.0, 0.06, size=n)
                        X[idx] = np.clip(rand_k + noise, 0.001, 0.999)
                    pbest_costs[idx] = evaluate_particle_cost(X[idx])
                    P[idx] = np.copy(X[idx])
                stagnation_counter = 0

        # Fast Adaptive Penalty Update based on Swarm Feasibility Ratio (evaluated in microseconds via numba)
        if config.adaptive_penalty and (t + 1) % config.adapt_freq == 0:
            sample_size = min(5, M)
            feas_count = 0
            for s_idx in range(sample_size):
                p_tour = np.argsort(X[s_idx]) + 1
                c_test = _split_cost_numba(
                    p_tour,
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
                if c_test < 1e11:
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

        # 3. Memetic Step: Local Search on global best every m iterations
        if config.local_search_freq > 0 and (t + 1) % config.local_search_freq == 0:
            p_tour = np.argsort(gbest_x) + 1
            _, current_routes, is_feas, _ = prins_split(
                problem,
                p_tour,
                max_vehicles=limit_v,
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
            if is_feas and len(current_routes) <= (limit_v if limit_v > 0 else 999):
                route_indices = [
                    [problem.get_customer_index(sid) for sid in r.stop_ids]
                    for r in current_routes
                ]
                improved_routes, ls_cost = run_local_search(
                    route_indices, dist_mat, demands, capacity, neighbour_mat
                )
                if ls_cost < gbest_cost - 1e-4:
                    improved_tour = flatten_routes(improved_routes)
                    new_keys = project_tour_to_keys(gbest_x, improved_tour)
                    gbest_x = new_keys
                    gbest_cost = ls_cost

        cost_history.append(float(gbest_cost))
        if callback is not None:
            callback(t + 1, float(gbest_cost))

    # 4. Final Solution Construction from Global Best
    best_tour = np.argsort(gbest_x) + 1
    total_cost, routes, is_feasible, violations = prins_split(
        problem,
        best_tour,
        max_vehicles=limit_v,
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

    # 5. Local Search refinement if feasible
    if config.local_search_freq > 0 and is_feasible and len(routes) <= (limit_v if limit_v > 0 else 999):
        route_indices = [
            [problem.get_customer_index(sid) for sid in r.stop_ids]
            for r in routes
        ]
        improved_routes, final_ls_cost = run_local_search(
            route_indices, dist_mat, demands, capacity, neighbour_mat
        )
        if final_ls_cost < total_cost - 1e-4:
            improved_tour = flatten_routes(improved_routes)
            total_cost, routes, is_feasible, violations = prins_split(
                problem,
                improved_tour,
                max_vehicles=limit_v,
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

    # 6. Apply End-to-End Fleet Consolidation & Time-Window Repair Operator
    if config.apply_tw_repair:
        solution = repair_solution(
            problem,
            solution,
            max_vehicles=limit_v if limit_v > 0 else None,
            cost_oracle=cost_oracle,
            max_passes=50,
        )

    # 7. Independent validation stamp
    val_report = validate_solution(
        problem,
        solution,
        cost_oracle=cost_oracle,
        max_vehicles=limit_v if limit_v > 0 else None,
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


def warmup_qpso() -> None:
    """Pre-warm JIT kernels on server initialization so the first solve runs in milliseconds."""
    from solver.models import Customer, Depot, Problem, Vehicle
    depot = Depot(id="depot", lat=22.30, lon=73.18, ready_time=0.0, due_time=100000.0, service_time=0.0)
    customers = [
        Customer(id="c1", lat=22.31, lon=73.18, demand=10.0, ready_time=0.0, due_time=100000.0, service_time=10.0),
        Customer(id="c2", lat=22.32, lon=73.19, demand=10.0, ready_time=0.0, due_time=100000.0, service_time=10.0),
        Customer(id="c3", lat=22.30, lon=73.20, demand=10.0, ready_time=0.0, due_time=100000.0, service_time=10.0),
    ]
    vehicles = [Vehicle(id="v1", capacity=50.0, shift_start=0.0, shift_end=100000.0)]
    prob = Problem(id="warmup", depot=depot, customers=customers, vehicles=vehicles)
    prob.compute_euclidean_matrices()
    solve_qpso(prob, QPSOConfig(num_particles=2, max_iters=2, seed=42))

