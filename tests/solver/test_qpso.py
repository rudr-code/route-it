"""Unit tests for QPSO, PSO baseline, and CLI runner."""

from pathlib import Path
import pytest

from solver.io import load_cvrplib, load_solution_json
from solver.pso import PSOConfig, solve_pso
from solver.qpso import QPSOConfig, solve_qpso
from solver.run import main


@pytest.fixture
def a_n32_instance() -> Path:
    """Fixture providing path to reference instance A-n32-k5.vrp."""
    p = Path("benchmarks/instances/A-n32-k5.vrp")
    assert p.is_file(), f"Benchmark instance {p} must exist"
    return p


def test_qpso_determinism_with_fixed_seed(a_n32_instance: Path) -> None:
    """Verify that QPSO produces identical trajectories and solutions with a fixed random seed."""
    problem = load_cvrplib(a_n32_instance)
    cfg = QPSOConfig(num_particles=15, max_iters=25, seed=42)

    sol1, hist1 = solve_qpso(problem, cfg)
    sol2, hist2 = solve_qpso(problem, cfg)

    assert pytest.approx(sol1.total_cost, rel=1e-5) == sol2.total_cost
    assert hist1 == hist2
    assert len(sol1.routes) == len(sol2.routes)

    for r1, r2 in zip(sol1.routes, sol2.routes, strict=True):
        assert r1.stop_ids == r2.stop_ids
        assert pytest.approx(r1.load, rel=1e-5) == r2.load
        assert pytest.approx(r1.distance, rel=1e-5) == r2.distance


def test_qpso_cost_non_increasing_for_gbest(a_n32_instance: Path) -> None:
    """Verify that global best cost never increases across iterations."""
    problem = load_cvrplib(a_n32_instance)
    cfg = QPSOConfig(num_particles=15, max_iters=40, seed=123)

    solution, cost_history = solve_qpso(problem, cfg)

    assert len(cost_history) == cfg.max_iters + 1
    for t in range(len(cost_history) - 1):
        assert cost_history[t + 1] <= cost_history[t] + 1e-9, (
            f"gbest cost increased from {cost_history[t]} to {cost_history[t+1]} at iter {t}"
        )

    # Cost at end of run should be <= initial cost
    assert cost_history[-1] <= cost_history[0]


def test_qpso_customer_coverage_and_capacity_satisfaction(a_n32_instance: Path) -> None:
    """Verify all customers are visited once and vehicle capacities are respected."""
    problem = load_cvrplib(a_n32_instance)
    cfg = QPSOConfig(num_particles=15, max_iters=30, seed=777)

    solution, _ = solve_qpso(problem, cfg)

    assert solution.is_feasible is True
    assert solution.violations == {}
    assert solution.total_cost > 0.0

    visited_stops: list[str] = []
    capacity = problem.vehicles[0].capacity

    for route in solution.routes:
        assert route.load <= capacity, f"Route {route.vehicle_id} exceeded capacity {capacity}"
        visited_stops.extend(route.stop_ids)

    expected_ids = {c.id for c in problem.customers}
    assert set(visited_stops) == expected_ids
    assert len(visited_stops) == problem.num_customers


def test_pso_baseline_execution_and_determinism(a_n32_instance: Path) -> None:
    """Verify baseline PSO execution, feasibility, and seed determinism."""
    problem = load_cvrplib(a_n32_instance)
    cfg = PSOConfig(num_particles=15, max_iters=25, seed=999)

    sol1, hist1 = solve_pso(problem, cfg)
    sol2, hist2 = solve_pso(problem, cfg)

    assert sol1.is_feasible is True
    assert pytest.approx(sol1.total_cost, rel=1e-5) == sol2.total_cost
    assert hist1 == hist2

    # Check non-increasing cost property
    for t in range(len(hist1) - 1):
        assert hist1[t + 1] <= hist1[t] + 1e-9


def test_cli_runner_execution(a_n32_instance: Path, tmp_path: Path) -> None:
    """Verify the CLI runner execution and JSON export."""
    out_file = tmp_path / "solution.json"
    argv = [
        "--instance",
        str(a_n32_instance),
        "--solver",
        "qpso",
        "--seed",
        "1",
        "--particles",
        "10",
        "--iters",
        "15",
        "--out",
        str(out_file),
        "--quiet",
    ]

    ret = main(argv)
    assert ret == 0
    assert out_file.is_file()

    sol = load_solution_json(out_file)
    assert sol.algorithm in ("QPSO", "QPSO+LS")
    assert sol.is_feasible is True
    assert sol.seed == 1
    assert sol.total_cost > 0.0


def test_qpso_cvrptw_with_adaptive_penalty_and_priorities() -> None:
    """Verify QPSO solves CVRPTW instance respecting time windows, priorities, and duty limits."""
    from solver.models import Customer, Depot, Problem, Vehicle
    from solver.validate import validate_solution

    depot = Depot(id="depot", lat=0.0, lon=0.0, ready_time=0.0, due_time=200.0)
    customers = [
        Customer(id="C1", lat=5.0, lon=0.0, demand=10.0, ready_time=0.0, due_time=20.0, service_time=5.0, priority=2),
        Customer(id="C2", lat=15.0, lon=0.0, demand=15.0, ready_time=15.0, due_time=60.0, service_time=5.0, priority=1),
        Customer(id="C3", lat=25.0, lon=0.0, demand=15.0, ready_time=25.0, due_time=100.0, service_time=5.0, priority=1),
        Customer(id="C4", lat=0.0, lon=10.0, demand=12.0, ready_time=0.0, due_time=50.0, service_time=5.0, priority=1),
        Customer(id="C5", lat=0.0, lon=20.0, demand=18.0, ready_time=10.0, due_time=80.0, service_time=5.0, priority=2),
    ]
    vehicles = [
        Vehicle(id="V1", capacity=50.0, shift_start=0.0, shift_end=150.0),
        Vehicle(id="V2", capacity=50.0, shift_start=0.0, shift_end=150.0),
    ]
    problem = Problem(id="toy_cvrptw", depot=depot, customers=customers, vehicles=vehicles)
    problem.compute_euclidean_matrices(speed=1.0)

    cfg = QPSOConfig(
        num_particles=20,
        max_iters=35,
        seed=42,
        adaptive_penalty=True,
        enforce_priority_early_service=True,
        priority_early_ratio=0.6,
        apply_tw_repair=True,
    )

    sol, hist = solve_qpso(problem, cfg)

    assert sol.is_feasible is True
    assert len(sol.violations) == 0
    assert sol.total_cost > 0.0

    # Independent validation verification
    val = validate_solution(
        problem,
        sol,
        enforce_priority_early_service=True,
        priority_early_ratio=0.6,
    )
    assert val.is_valid is True
    assert val.customer_count == 5

