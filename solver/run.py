"""Command line interface runner for Route.it solvers (QPSO and baseline PSO).

Usage example:
    python -m solver.run --instance benchmarks/instances/A-n32-k5.vrp --seed 1 --particles 40 --iters 500 --out result.json
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Sequence

# Ensure project root is in sys.path when executed directly
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from solver.io import load_cvrplib, load_solomon, save_solution_json
from solver.models import Problem, Solution
from solver.ortools_baseline import ORToolsConfig, solve_ortools
from solver.pso import PSOConfig, solve_pso
from solver.qpso import QPSOConfig, solve_qpso


def load_instance(path_str: str | Path) -> Problem:
    """Load a problem instance based on file extension (.vrp or .txt)."""
    p = Path(path_str)
    if not p.is_file():
        raise FileNotFoundError(f"Instance file not found: {p}")

    suffix = p.suffix.lower()
    if suffix == ".vrp":
        return load_cvrplib(p)
    elif suffix == ".txt":
        return load_solomon(p)
    else:
        raise ValueError(f"Unsupported file format '{suffix}'. Expected .vrp or .txt")


def run_solver(
    instance_path: str | Path,
    solver_name: str = "qpso",
    seed: int = 1,
    particles: int = 40,
    iters: int = 500,
    alpha_max: float = 1.0,
    alpha_min: float = 0.5,
    max_vehicles: int | None = None,
    ls_freq: int = 20,
    ls_top_k: int = 3,
    no_ls: bool = False,
    time_limit_sec: float = 10.0,
    out_path: str | Path | None = None,
    verbose: bool = True,
) -> Solution:
    """Load instance, execute selected solver, and optionally persist solution."""
    if verbose:
        print(f"Loading instance: {instance_path}")

    problem = load_instance(instance_path)

    if verbose:
        print(
            f"Loaded '{problem.id}' with {problem.num_customers} customers, "
            f"{problem.num_vehicles} vehicles, capacity {problem.vehicles[0].capacity:.1f}"
        )

    def progress_callback(iteration: int, gbest_cost: float) -> None:
        if verbose and (iteration % 50 == 0 or iteration == iters or iteration == 1):
            print(f"  [Iter {iteration:4d}/{iters:4d}] Current Best Cost: {gbest_cost:10.2f}")

    if solver_name.lower() == "qpso":
        actual_ls_freq = 0 if no_ls else ls_freq
        if verbose:
            mode_str = "Memetic QPSO+LS" if actual_ls_freq > 0 else "Pure QPSO"
            print(
                f"Running {mode_str} (particles={particles}, iters={iters}, seed={seed}, "
                f"alpha=[{alpha_max}, {alpha_min}], ls_freq={actual_ls_freq}, ls_top_k={ls_top_k})..."
            )
        cfg = QPSOConfig(
            num_particles=particles,
            max_iters=iters,
            alpha_max=alpha_max,
            alpha_min=alpha_min,
            seed=seed,
            max_vehicles=max_vehicles,
            local_search_freq=actual_ls_freq,
            local_search_top_k=ls_top_k,
        )
        solution, _ = solve_qpso(problem, cfg, callback=progress_callback)
    elif solver_name.lower() == "pso":
        if verbose:
            print(f"Running Baseline PSO (particles={particles}, iters={iters}, seed={seed})...")
        pso_cfg = PSOConfig(
            num_particles=particles,
            max_iters=iters,
            seed=seed,
            max_vehicles=max_vehicles,
        )
        solution, _ = solve_pso(problem, pso_cfg, callback=progress_callback)
    elif solver_name.lower() == "ortools":
        if verbose:
            print(f"Running Google OR-Tools Baseline (time_limit={time_limit_sec:.1f}s)...")
        ortools_cfg = ORToolsConfig(time_limit_sec=time_limit_sec)
        solution = solve_ortools(problem, ortools_cfg)
    else:
        raise ValueError(f"Unknown solver '{solver_name}'. Choose 'qpso', 'pso', or 'ortools'.")

    if verbose:
        print("\n" + "=" * 50)
        print(f"Algorithm:       {solution.algorithm}")
        print(f"Total Cost:      {solution.total_cost:.2f}")
        print(f"Feasible:        {solution.is_feasible}")
        print(f"Routes:          {len(solution.routes)}")
        print(f"Execution Time:  {solution.execution_time_sec:.3f} s")
        if solution.violations:
            print(f"Violations:      {solution.violations}")
        print("=" * 50)

    if out_path:
        save_solution_json(solution, out_path)
        if verbose:
            print(f"Solution saved to {out_path}")

    return solution


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Route.it Solver CLI Runner (QPSO & Baseline PSO)."
    )
    parser.add_argument(
        "--instance",
        "-i",
        type=str,
        required=True,
        help="Path to problem instance (.vrp or .txt)",
    )
    parser.add_argument(
        "--solver",
        "-s",
        type=str,
        default="qpso",
        choices=["qpso", "pso", "ortools"],
        help="Optimization algorithm to run (default: qpso)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=1,
        help="Random seed for reproducible results (default: 1)",
    )
    parser.add_argument(
        "--particles",
        "-p",
        type=int,
        default=40,
        help="Swarm size / number of particles (default: 40)",
    )
    parser.add_argument(
        "--iters",
        type=int,
        default=500,
        help="Maximum optimization iterations (default: 500)",
    )
    parser.add_argument(
        "--time-limit",
        "-t",
        type=float,
        default=10.0,
        help="Time limit in seconds (primarily for OR-Tools, default: 10.0)",
    )
    parser.add_argument(
        "--alpha-max",
        type=float,
        default=1.0,
        help="QPSO initial alpha coefficient (default: 1.0)",
    )
    parser.add_argument(
        "--alpha-min",
        type=float,
        default=0.5,
        help="QPSO final alpha coefficient (default: 0.5)",
    )
    parser.add_argument(
        "--max-vehicles",
        type=int,
        default=None,
        help="Optional maximum number of vehicle routes allowed",
    )
    parser.add_argument(
        "--ls-freq",
        type=int,
        default=20,
        help="Apply local search every m iterations (default: 20, 0 to disable)",
    )
    parser.add_argument(
        "--ls-top-k",
        type=int,
        default=3,
        help="Number of top particles refined with local search (default: 3)",
    )
    parser.add_argument(
        "--no-ls",
        action="store_true",
        help="Disable memetic local search entirely",
    )
    parser.add_argument(
        "--out",
        "-o",
        type=str,
        default=None,
        help="Path to output JSON file to save the final solution",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress console progress output",
    )

    args = parser.parse_args(argv)

    try:
        run_solver(
            instance_path=args.instance,
            solver_name=args.solver,
            seed=args.seed,
            particles=args.particles,
            iters=args.iters,
            alpha_max=args.alpha_max,
            alpha_min=args.alpha_min,
            max_vehicles=args.max_vehicles,
            ls_freq=args.ls_freq,
            ls_top_k=args.ls_top_k,
            no_ls=args.no_ls,
            time_limit_sec=args.time_limit,
            out_path=args.out,
            verbose=not args.quiet,
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"Error running solver: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
