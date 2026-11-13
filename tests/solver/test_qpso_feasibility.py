"""Automated feasibility and constraint verification tests for QPSO."""

import pytest
from api.routes.benchmark import get_default_benchmark_problem
from solver.qpso import QPSOConfig, solve_qpso, warmup_qpso


@pytest.fixture(scope="session", autouse=True)
def run_warmup():
    """Ensure JIT kernels are compiled before running assertions."""
    warmup_qpso()


@pytest.mark.parametrize("seed", [42, 999, 2024, 314, 888])
def test_qpso_feasibility_across_seeds(seed: int):
    """Assert QPSO produces strictly feasible solutions on benchmark instance."""
    problem = get_default_benchmark_problem()
    config = QPSOConfig(num_particles=30, max_iters=40, seed=seed)

    solution, cost_history = solve_qpso(problem, config)

    # 1. Feasibility & Violations
    assert solution.is_feasible is True, f"Seed {seed} marked infeasible: {solution.violations}"
    assert len(solution.violations) == 0, f"Seed {seed} reported violations: {solution.violations}"

    # 2. Fleet Limit
    assert len(solution.routes) <= len(problem.vehicles), (
        f"Seed {seed} used {len(solution.routes)} routes, exceeding available fleet size {len(problem.vehicles)}"
    )

    # 3. Customer Coverage: visited exactly once
    expected_cids = {c.id for c in problem.customers}
    visited_cids = [cid for r in solution.routes for cid in r.stop_ids]
    assert len(visited_cids) == len(expected_cids), (
        f"Seed {seed}: Expected {len(expected_cids)} customers, but visited {len(visited_cids)}"
    )
    assert set(visited_cids) == expected_cids, (
        f"Seed {seed}: Customer coverage mismatch: missing={expected_cids - set(visited_cids)}"
    )

    # 4. Vehicle Capacity
    customer_map = {c.id: c for c in problem.customers}
    max_cap = problem.vehicles[0].capacity
    for r_idx, r in enumerate(solution.routes):
        load = sum(customer_map[cid].demand for cid in r.stop_ids)
        assert load <= max_cap + 1e-4, (
            f"Seed {seed} Route {r_idx + 1}: load {load} exceeds vehicle capacity {max_cap}"
        )

    # 5. Stop Time Windows
    for r_idx, r in enumerate(solution.routes):
        for stop_idx, (cid, arr_time) in enumerate(zip(r.stop_ids, r.arrival_times)):
            cust = customer_map[cid]
            assert arr_time <= cust.due_time + 1e-4, (
                f"Seed {seed} Route {r_idx + 1} stop {stop_idx + 1} ({cid}): "
                f"arrival {arr_time:.2f} > due time {cust.due_time:.2f}"
            )

    # 6. Convergence
    assert len(cost_history) > 0
    assert cost_history[-1] <= cost_history[0], "Cost history should not degrade from initial best"
