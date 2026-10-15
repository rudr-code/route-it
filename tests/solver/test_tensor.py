"""Unit tests for solver CostTensor and CostOracle integration.

Verifies:
1. Precomputing stationary vs time-dependent travel-time tensors.
2. Exact numerical equivalence between 2D distance matrix and 3D tensor (B=1) in Numba.
3. Multi-bucket time-dependent tensor evaluation with TimeOfDayProfileAdapter.
4. QPSO and PSO execution when provided with an explicit CostOracle.
"""

from __future__ import annotations

from pathlib import Path
import numpy as np
import pytest

from routing.cost_oracle import (
    EuclideanOracle,
    Location,
    TimeOfDayProfileAdapter,
)
from solver.io import load_cvrplib
from solver.models import Customer, Depot, Problem, Vehicle
from solver.pso import PSOConfig, solve_pso
from solver.qpso import QPSOConfig, solve_qpso
from solver.split import _split_cost_numba, prins_split
from solver.tensor import CostTensor, precompute_cost_tensor


@pytest.fixture
def small_problem() -> Problem:
    """A small hand-crafted CVRPTW problem with 4 customers in Vadodara coordinates."""
    depot = Depot(id="depot", lat=22.3108, lon=73.1811, ready_time=0.0, due_time=36000.0)
    customers = [
        Customer(
            id="c1", lat=22.3129, lon=73.1906, demand=4.0, ready_time=0.0, due_time=10000.0, service_time=300.0
        ),
        Customer(
            id="c2", lat=22.2936, lon=73.1915, demand=6.0, ready_time=0.0, due_time=10000.0, service_time=300.0
        ),
        Customer(
            id="c3", lat=22.3200, lon=73.1700, demand=5.0, ready_time=0.0, due_time=10000.0, service_time=300.0
        ),
        Customer(
            id="c4", lat=22.3050, lon=73.2000, demand=3.0, ready_time=0.0, due_time=10000.0, service_time=300.0
        ),
    ]
    vehicles = [
        Vehicle(id="v1", capacity=10.0, shift_start=0.0, shift_end=36000.0),
        Vehicle(id="v2", capacity=10.0, shift_start=0.0, shift_end=36000.0),
    ]
    problem = Problem(id="small_vadodara", depot=depot, customers=customers, vehicles=vehicles)
    problem.compute_euclidean_matrices()
    return problem


def test_tensor_numerical_equivalence_with_2d_matrix(small_problem: Problem) -> None:
    """Verify that _split_cost_numba on 2D matrix vs 3D tensor (B=1) yields identical cost."""
    dist_mat = np.asarray(small_problem.distance_matrix, dtype=np.float64)
    demands = np.array([0.0, 4.0, 6.0, 5.0, 3.0], dtype=np.float64)
    tour = np.array([1, 2, 3, 4], dtype=np.int64)
    capacity = 10.0

    cost_2d = _split_cost_numba(tour, dist_mat, demands, capacity, max_vehicles=-1)

    # Convert to 3D tensor with B=1
    tensor_3d = dist_mat.reshape((1, 5, 5))
    cost_3d = _split_cost_numba(tour, tensor_3d, demands, capacity, max_vehicles=-1)

    assert cost_2d == pytest.approx(cost_3d, abs=1e-12)


def test_precompute_cost_tensor_stationary(small_problem: Problem) -> None:
    """Verify stationary CostTensor has num_buckets=1 and matching distance matrix."""
    oracle = EuclideanOracle(use_haversine=True, base_speed_mps=10.0)
    tensor = precompute_cost_tensor(small_problem, cost_oracle=oracle)

    assert tensor.num_buckets == 1
    assert tensor.travel_time_tensor.shape == (1, 5, 5)
    assert tensor.distance_matrix.shape == (5, 5)
    assert not tensor.is_time_dependent


def test_precompute_cost_tensor_time_dependent(small_problem: Problem) -> None:
    """Verify time-dependent CostTensor builds multiple buckets with distinct rush-hour costs."""
    adapter = TimeOfDayProfileAdapter()
    oracle = EuclideanOracle(traffic_adapter=adapter, use_haversine=True, base_speed_mps=10.0)

    # 10 hours horizon (0 to 36000s) with 3600s (1h) buckets -> 10 buckets
    tensor = precompute_cost_tensor(
        small_problem, cost_oracle=oracle, bucket_size_seconds=3600.0, num_buckets=10
    )

    assert tensor.num_buckets == 10
    assert tensor.travel_time_tensor.shape == (10, 5, 5)
    assert tensor.is_time_dependent

    # Compare off-peak (hour 0) vs rush peak (hour 8)
    # Hour 8 speed factor is 0.65 (slower -> higher travel time)
    # Hour 0 speed factor is 1.15 (faster -> lower travel time)
    dur_night = tensor.travel_time_tensor[0, 0, 1]
    dur_rush = tensor.travel_time_tensor[8, 0, 1]
    assert dur_rush > dur_night * 1.5


def test_qpso_with_explicit_cost_oracle(small_problem: Problem) -> None:
    """Verify solve_qpso executes with an explicit CostOracle and returns valid routes."""
    oracle = EuclideanOracle(use_haversine=True, base_speed_mps=10.0)
    cfg = QPSOConfig(num_particles=10, max_iters=15, seed=42)

    solution, history = solve_qpso(small_problem, config=cfg, cost_oracle=oracle)

    assert solution.is_feasible is True
    assert solution.total_cost > 0.0
    assert len(solution.routes) >= 2
    assert len(history) == 16


def test_pso_with_explicit_cost_oracle(small_problem: Problem) -> None:
    """Verify solve_pso executes with an explicit CostOracle."""
    oracle = EuclideanOracle(use_haversine=True, base_speed_mps=10.0)
    cfg = PSOConfig(num_particles=10, max_iters=15, seed=42)

    solution, history = solve_pso(small_problem, config=cfg, cost_oracle=oracle)

    assert solution.is_feasible is True
    assert solution.total_cost > 0.0
    assert len(solution.routes) >= 2
