"""Genetic Algorithm (GA) baseline for CVRPTW.

Implements a Genetic Algorithm with continuous random-key chromosome representation,
Order/Uniform Crossover (OX), Inversion/Gaussian mutation, Tournament Selection,
Elitism, and polynomial-time Prins Split partitioning.
Serves as an empirical baseline to compare against QPSO and PSO.
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


class GAConfig(BaseModel):
    """Configuration parameters for Genetic Algorithm solver."""

    population_size: int = Field(40, ge=4, description="Population size (P)")
    max_generations: int = Field(200, ge=1, description="Maximum generations (G)")
    crossover_rate: float = Field(0.85, ge=0.0, le=1.0, description="Crossover probability (Pc)")
    mutation_rate: float = Field(0.20, ge=0.0, le=1.0, description="Mutation probability (Pm)")
    tournament_size: int = Field(3, ge=2, description="Tournament selection group size (k)")
    elitism_count: int = Field(2, ge=1, description="Number of elite chromosomes preserved")
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


def solve_ga(
    problem: Problem,
    config: GAConfig | None = None,
    cost_oracle: Any | None = None,
    callback: Callable[[int, float], None] | None = None,
) -> tuple[Solution, list[float]]:
    """Execute Genetic Algorithm to optimize vehicle routes.

    Args:
        problem: Fully initialized Problem instance.
        config: GAConfig options. If None, default settings are used.
        cost_oracle: Optional CostOracle for road network or traffic evaluation.
        callback: Optional callback(generation, best_cost) invoked at each step.

    Returns:
        (Solution, cost_history) where cost_history records best cost per generation.
    """
    if config is None:
        config = GAConfig()

    start_time = time.perf_counter()
    rng = np.random.default_rng(config.seed)

    n = problem.num_customers
    if n == 0:
        return Solution(
            routes=[],
            total_cost=0.0,
            is_feasible=True,
            violations={},
            algorithm="GeneticAlgorithm",
            execution_time_sec=0.0,
            seed=config.seed,
        ), [0.0]

    # Precompute CostTensor
    cost_tensor = precompute_cost_tensor(problem, cost_oracle=cost_oracle)
    cost_data = cost_tensor.travel_time_tensor

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
    limit_v = (
        config.max_vehicles
        if config.max_vehicles is not None
        else (len(problem.vehicles) if (problem.vehicles and not config.allow_extra_vehicles) else -1)
    )

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

    pop_size = config.population_size
    max_gen = config.max_generations
    k_tourn = config.tournament_size
    n_elite = min(config.elitism_count, pop_size // 2)

    # 1. Initialize random-key chromosomes in [0, 1]^n
    population = rng.uniform(0.0, 1.0, size=(pop_size, n))
    fitness_values = np.full(pop_size, np.inf, dtype=np.float64)

    def evaluate_chromosome(keys: np.ndarray) -> float:
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
    for i in range(pop_size):
        fitness_values[i] = evaluate_chromosome(population[i])

    best_idx = int(np.argmin(fitness_values))
    gbest_x = np.copy(population[best_idx])
    gbest_cost = float(fitness_values[best_idx])

    cost_history: list[float] = [gbest_cost]

    # Tournament selection helper
    def tournament_select() -> int:
        candidates = rng.choice(pop_size, size=k_tourn, replace=False)
        best_cand = candidates[0]
        best_fit = fitness_values[best_cand]
        for c in candidates[1:]:
            if fitness_values[c] < best_fit:
                best_cand = c
                best_fit = fitness_values[c]
        return int(best_cand)

    # 2. Evolution generations
    for gen in range(max_gen):
        # Sort current population for elitism
        sorted_indices = np.argsort(fitness_values)
        new_population = np.zeros_like(population)

        # Preserve elites
        for e in range(n_elite):
            new_population[e] = np.copy(population[sorted_indices[e]])

        # Generate remainder through selection, crossover, and mutation
        idx = n_elite
        while idx < pop_size:
            p1_idx = tournament_select()
            p2_idx = tournament_select()
            p1 = population[p1_idx]
            p2 = population[p2_idx]

            # Crossover (Simulated Binary / Arithmetic Blend + Mask)
            c1 = np.copy(p1)
            c2 = np.copy(p2)
            if rng.random() < config.crossover_rate:
                # Uniform crossover mask
                mask = rng.random(n) < 0.5
                c1 = np.where(mask, p1, p2)
                c2 = np.where(mask, p2, p1)

                # Order blend mutation factor
                if n > 2 and rng.random() < 0.5:
                    cut1, cut2 = sorted(rng.choice(n, size=2, replace=False))
                    # Invert key segment
                    c1[cut1:cut2] = c1[cut1:cut2][::-1]

            # Mutation
            for child in (c1, c2):
                if idx < pop_size:
                    if rng.random() < config.mutation_rate:
                        # Random swap & Gaussian perturb
                        swap_i, swap_j = rng.choice(n, size=2, replace=False)
                        child[swap_i], child[swap_j] = child[swap_j], child[swap_i]
                        # Slight jitter
                        noise = rng.normal(0.0, 0.05, size=n)
                        child = np.clip(child + noise, 0.0, 1.0)

                    new_population[idx] = child
                    idx += 1

        population = new_population

        # Evaluate new generation (elites already evaluated)
        feas_count = 0
        for i in range(pop_size):
            if i >= n_elite:
                fitness_values[i] = evaluate_chromosome(population[i])

            if fitness_values[i] < gbest_cost:
                gbest_cost = float(fitness_values[i])
                gbest_x = np.copy(population[i])

            # Feasibility proxy: penalty weight check
            if fitness_values[i] < 5000.0:
                feas_count += 1

        # Adaptive penalty update
        if config.adaptive_penalty and (gen + 1) % config.adapt_freq == 0:
            feas_ratio = feas_count / pop_size
            if feas_ratio < 0.15:
                cur_alpha = min(10000.0, cur_alpha * 1.3)
                cur_beta = min(10000.0, cur_beta * 1.3)
                cur_gamma = min(10000.0, cur_gamma * 1.3)
            elif feas_ratio > 0.45:
                cur_alpha = max(1.0, cur_alpha / 1.25)
                cur_beta = max(1.0, cur_beta / 1.25)
                cur_gamma = max(1.0, cur_gamma / 1.25)

        cost_history.append(float(gbest_cost))
        if callback is not None:
            callback(gen + 1, float(gbest_cost))

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
        algorithm="GeneticAlgorithm",
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
