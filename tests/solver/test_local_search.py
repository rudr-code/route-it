"""Unit and benchmark tests for local search operators and memetic QPSO."""

import json
from pathlib import Path
import numpy as np
import pytest

from solver.io import load_cvrplib
from solver.local_search import (
    build_neighbour_list,
    flatten_routes,
    inter_route_relocate,
    inter_route_swap,
    intra_route_2opt,
    project_tour_to_keys,
    run_local_search,
    total_routes_cost,
)
from solver.models import Customer, Depot, Problem, Vehicle
from solver.qpso import QPSOConfig, solve_qpso
from solver.split import prins_split


def test_2opt_untangles_crossing() -> None:
    """Verify that intra-route 2-opt detects crossing edges and untangles them."""
    # Unit square: depot (0,0), 1:(0,1), 2:(1,1), 3:(1,0)
    # A crossed tour: depot -> 1 -> 3 -> 2 -> depot
    dist_mat = np.array(
        [
            [0.0, 1.0, 1.414, 1.0],
            [1.0, 0.0, 1.0, 1.414],
            [1.414, 1.0, 0.0, 1.0],
            [1.0, 1.414, 1.0, 0.0],
        ]
    )
    # Route with crossing: 1 -> 3 -> 2
    route = [1, 3, 2]
    initial_cost = dist_mat[0, 1] + dist_mat[1, 3] + dist_mat[3, 2] + dist_mat[2, 0]

    improved = intra_route_2opt(route, dist_mat)
    assert improved is True
    assert route == [1, 2, 3]

    new_cost = dist_mat[0, 1] + dist_mat[1, 2] + dist_mat[2, 3] + dist_mat[3, 0]
    assert new_cost < initial_cost


def test_inter_route_relocate_operator() -> None:
    """Verify that inter-route relocate moves a misplaced customer to a closer route."""
    # Dist matrix with 4 customers
    dist_mat = np.zeros((5, 5))
    for i in range(5):
        for j in range(5):
            dist_mat[i, j] = abs(i - j)

    # Route 1 has customers [1, 2, 4], Route 2 has [3]
    # Customer 4 is adjacent to 3 in index space
    routes = [[1, 2, 4], [3]]
    loads = [30.0, 10.0]
    demands = np.array([0.0, 10.0, 10.0, 10.0, 10.0])
    capacity = 50.0

    initial_cost = total_routes_cost(routes, dist_mat)
    improved = inter_route_relocate(routes, loads, dist_mat, demands, capacity)

    assert improved is True
    new_cost = total_routes_cost(routes, dist_mat)
    assert new_cost <= initial_cost


def test_inter_route_swap_operator() -> None:
    """Verify that inter-route swap exchanges customers when beneficial."""
    # Depot 0 at center (0,0)
    # Cluster A on left: (-10, 0), Cluster B on right: (10, 0)
    # Node 1: (-10, 1), Node 2: (10, 1)
    # Node 3: (-10, -1), Node 4: (10, -1)
    coords = [(0, 0), (-10, 1), (10, 1), (-10, -1), (10, -1)]
    dist_mat = np.zeros((5, 5))
    for i in range(5):
        for j in range(5):
            dist_mat[i, j] = np.hypot(coords[i][0] - coords[j][0], coords[i][1] - coords[j][1])

    # Misplaced: Route 1 has Left (1) and Right (4); Route 2 has Right (2) and Left (3)
    routes = [[1, 4], [2, 3]]
    loads = [20.0, 20.0]
    demands = np.array([0.0, 10.0, 10.0, 10.0, 10.0])
    capacity = 30.0

    initial_cost = total_routes_cost(routes, dist_mat)
    improved = inter_route_swap(routes, loads, dist_mat, demands, capacity)

    assert improved is True
    new_cost = total_routes_cost(routes, dist_mat)
    assert new_cost < initial_cost


def test_project_tour_to_keys() -> None:
    """Verify that projecting an improved tour to random keys yields exact argsort reconstruction."""
    old_keys = np.array([0.8, 0.2, 0.9, 0.1, 0.5])
    # Original argsort + 1: [4, 2, 5, 1, 3]
    improved_tour = [2, 1, 4, 3, 5]

    new_keys = project_tour_to_keys(old_keys, improved_tour)

    # Decoded permutation must match improved_tour exactly
    decoded = list(np.argsort(new_keys) + 1)
    assert decoded == improved_tour
    # The sorted values of new_keys must equal sorted old_keys
    np.testing.assert_allclose(np.sort(new_keys), np.sort(old_keys))


def test_local_search_never_worsens_cost_and_preserves_feasibility() -> None:
    """Verify on A-n32-k5 that composite local search never worsens cost and maintains capacity."""
    problem = load_cvrplib(Path("benchmarks/instances/A-n32-k5.vrp"))
    dist_mat = np.asarray(problem.distance_matrix, dtype=np.float64)
    demands = np.zeros(problem.num_customers + 1, dtype=np.float64)
    for idx, c in enumerate(problem.customers, start=1):
        demands[idx] = c.demand

    capacity = problem.vehicles[0].capacity
    nb_mat = build_neighbour_list(dist_mat, k_nearest=15)

    rng = np.random.default_rng(999)
    # Test on 3 diverse random tours
    for _ in range(3):
        tour = rng.permutation(np.arange(1, problem.num_customers + 1))
        cost, routes_obj, is_feas, _ = prins_split(problem, tour, allow_extra_vehicles=True)
        assert is_feas is True

        route_indices = [
            [problem.get_customer_index(sid) for sid in r.stop_ids]
            for r in routes_obj
        ]
        initial_cost = total_routes_cost(route_indices, dist_mat)

        opt_routes, opt_cost = run_local_search(
            route_indices, dist_mat, demands, capacity, neighbour_matrix=nb_mat
        )

        assert opt_cost <= initial_cost + 1e-7, f"Cost worsened: {initial_cost} -> {opt_cost}"

        # Verify all customers still present exactly once
        flat = flatten_routes(opt_routes)
        assert len(flat) == problem.num_customers
        assert set(flat) == set(range(1, problem.num_customers + 1))

        # Verify capacities respected
        for r in opt_routes:
            load = sum(demands[c] for c in r)
            assert load <= capacity + 1e-7


def test_qpso_plus_ls_benchmark_comparison(tmp_path: Path) -> None:
    """Benchmark test comparing Pure QPSO vs Memetic QPSO+LS on A-n32-k5.

    Results are genuinely measured and saved to tmp_path during test runs to ensure
    real verified records in benchmarks/results/ are never overwritten by tests.
    """
    problem = load_cvrplib(Path("benchmarks/instances/A-n32-k5.vrp"))
    fixed_seed = 42
    particles = 30
    iters = 100

    # 1. Pure QPSO (local search disabled)
    cfg_pure = QPSOConfig(
        num_particles=particles,
        max_iters=iters,
        seed=fixed_seed,
        local_search_freq=0,
    )
    sol_pure, hist_pure = solve_qpso(problem, cfg_pure)

    # 2. Memetic QPSO+LS (local search enabled every 20 iters for top 3 particles)
    cfg_memetic = QPSOConfig(
        num_particles=particles,
        max_iters=iters,
        seed=fixed_seed,
        local_search_freq=20,
        local_search_top_k=3,
        use_neighbour_list=True,
    )
    sol_memetic, hist_memetic = solve_qpso(problem, cfg_memetic)

    # Assertions
    assert sol_pure.is_feasible is True
    assert sol_memetic.is_feasible is True
    assert sol_memetic.total_cost <= sol_pure.total_cost, (
        f"Memetic QPSO cost ({sol_memetic.total_cost:.2f}) was worse than Pure QPSO ({sol_pure.total_cost:.2f})"
    )

    # Save benchmark results to tmp_path so real benchmarks/results files are never overwritten
    out_file = tmp_path / "a_n32_k5_ls_comparison.json"

    data = {
        "instance": "A-n32-k5",
        "seed": fixed_seed,
        "particles": particles,
        "iterations": iters,
        "pure_qpso": {
            "cost": float(sol_pure.total_cost),
            "feasible": sol_pure.is_feasible,
            "routes": len(sol_pure.routes),
            "time_sec": float(sol_pure.execution_time_sec),
        },
        "memetic_qpso_ls": {
            "cost": float(sol_memetic.total_cost),
            "feasible": sol_memetic.is_feasible,
            "routes": len(sol_memetic.routes),
            "time_sec": float(sol_memetic.execution_time_sec),
        },
        "improvement_pct": float((sol_pure.total_cost - sol_memetic.total_cost) / sol_pure.total_cost * 100.0),
    }

    with out_file.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    assert out_file.is_file()
