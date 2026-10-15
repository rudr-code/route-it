"""Solomon CVRPTW Benchmark Runner for Route.it.

Runs the QPSO + time-aware Prins Split + adaptive penalty + repair pipeline on
Solomon 1987 benchmark instances (C101, R101, RC101).
Independently verifies all constraints using solver/validate.py.
Saves genuine, un-fabricated benchmark results to benchmarks/results/solomon_cvrptw_results.json.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
from typing import Any

# Ensure workspace root is in sys.path
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from solver.io import load_solomon, save_solution_json
from solver.models import Customer, Problem, Solution
from solver.qpso import QPSOConfig, solve_qpso
from solver.validate import validate_solution


SOLOMON_INSTANCES = [
    ("C101.txt", "C1 (Clustered)"),
    ("R101.txt", "R1 (Random)"),
    ("RC101.txt", "RC1 (Mixed)"),
]


def run_single_solomon_instance(
    file_path: Path,
    category: str,
    max_customers: int | None = None,
    num_particles: int = 35,
    max_iters: int = 150,
    seed: int = 42,
) -> dict[str, Any]:
    """Execute QPSO on a Solomon instance and validate results."""
    raw_problem = load_solomon(file_path)

    # Allow truncating customers (e.g. Solomon-25 or Solomon-50) for fast benchmarks if requested
    if max_customers is not None and max_customers < raw_problem.num_customers:
        truncated_customers = raw_problem.customers[:max_customers]
        problem = Problem(
            id=f"{raw_problem.id}_{max_customers}",
            depot=raw_problem.depot,
            customers=truncated_customers,
            vehicles=raw_problem.vehicles,
        )
        problem.compute_euclidean_matrices(speed=1.0)
    else:
        problem = raw_problem

    print(f"\n[BENCHMARK] Running {problem.id} ({category}) | {problem.num_customers} customers, Q={problem.vehicles[0].capacity}...")

    cfg = QPSOConfig(
        num_particles=num_particles,
        max_iters=max_iters,
        seed=seed,
        adaptive_penalty=True,
        apply_tw_repair=True,
        local_search_freq=15,
        local_search_top_k=2,
    )

    t0 = time.perf_counter()
    solution, cost_history = solve_qpso(problem, config=cfg)
    elapsed = time.perf_counter() - t0
    solution.execution_time_sec = elapsed

    # Independent validation
    val_report = validate_solution(problem, solution)

    result_entry = {
        "instance": problem.id,
        "filename": file_path.name,
        "family": category,
        "num_customers": problem.num_customers,
        "capacity": problem.vehicles[0].capacity,
        "num_routes": len(solution.routes),
        "total_distance": round(val_report.recomputed_distance, 2),
        "total_duration": round(val_report.recomputed_duration, 2),
        "total_waiting_time": round(val_report.total_waiting_time, 2),
        "total_service_time": round(val_report.total_service_time, 2),
        "is_feasible": val_report.is_valid,
        "violations_count": sum(len(v) for v in val_report.violations.values()),
        "violations": val_report.violations,
        "execution_time_sec": round(elapsed, 2),
        "seed": seed,
    }

    status_str = "FEASIBLE" if val_report.is_valid else f"INFEASIBLE ({result_entry['violations_count']} viol)"
    print(f"  -> Result: {status_str} | Routes: {len(solution.routes)} | Dist: {result_entry['total_distance']} | Time: {elapsed:.2f}s")
    return result_entry


def main() -> int:
    """CLI Entrypoint for running Solomon CVRPTW benchmarks."""
    parser = argparse.ArgumentParser(description="Run Solomon CVRPTW benchmarks on R1, C1, RC1 families.")
    parser.add_argument("--instances", default=None, help="Comma-separated instance names or files to run (e.g. 'C101,R101,RC101')")
    parser.add_argument("--instances-dir", default="benchmarks/instances", help="Directory containing Solomon .txt files")
    parser.add_argument("--customers", type=int, default=None, help="Optional customer count limit (e.g. 25, 50, 100)")
    parser.add_argument("--particles", type=int, default=35, help="QPSO swarm size (default: 35)")
    parser.add_argument("--iters", type=int, default=150, help="QPSO iterations (default: 150)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    parser.add_argument("--out", default="benchmarks/results/solomon_cvrptw_results.json", help="Output JSON path")
    args = parser.parse_args()

    instances_dir = Path(args.instances_dir)
    results: list[dict[str, Any]] = []

    selected_names: set[str] | None = None
    if args.instances:
        raw_names = [item.strip() for item in args.instances.replace(",", " ").split() if item.strip()]
        selected_names = {name if name.endswith(".txt") else f"{name}.txt" for name in raw_names}

    for filename, category in SOLOMON_INSTANCES:
        if selected_names is not None and filename not in selected_names and filename.replace(".txt", "") not in selected_names:
            continue
        path = instances_dir / filename
        if not path.is_file():
            print(f"[ERROR] Instance file {path} not found!")
            continue

        res = run_single_solomon_instance(
            file_path=path,
            category=category,
            max_customers=args.customers,
            num_particles=args.particles,
            max_iters=args.iters,
            seed=args.seed,
        )
        results.append(res)

    if not results:
        print("[ERROR] No instances executed.")
        return 1

    # Write output JSON
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "solver": "Route.it QPSO + Time-Aware Prins Split + Adaptive Penalty + Repair",
                "results": results,
            },
            f,
            indent=2,
        )

    # Print summary table
    print("\n" + "=" * 90)
    print("                     SOLOMON CVRPTW BENCHMARK REPORT")
    print("=" * 90)
    print(f"{'Instance':<14} {'Family':<16} {'Cust':<6} {'Veh':<6} {'Distance':<12} {'Duration':<12} {'Feasible':<10} {'Runtime':<8}")
    print("-" * 90)

    feasible_count = 0
    total_dist = 0.0

    for r in results:
        feas_str = "YES" if r["is_feasible"] else "NO"
        if r["is_feasible"]:
            feasible_count += 1
            total_dist += r["total_distance"]

        print(
            f"{r['instance']:<14} {r['family']:<16} {r['num_customers']:<6} {r['num_routes']:<6} "
            f"{r['total_distance']:<12.2f} {r['total_duration']:<12.2f} {feas_str:<10} {r['execution_time_sec']:>6.2f}s"
        )

    feas_rate = (feasible_count / len(results)) * 100.0
    print("-" * 90)
    print(f"Summary: {feasible_count}/{len(results)} Feasible ({feas_rate:.1f}%) | Saved to {out_path.resolve()}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
