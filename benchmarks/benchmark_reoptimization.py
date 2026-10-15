"""Benchmark runner comparing Tiered Re-optimizer against Full-Restart Baseline.

Evaluates performance across dynamic incidents:
- Mild Edge Congestion (Do Nothing)
- Moderate Corridor Congestion (Tier 1 Path Repair)
- Severe Localized Slowdown (Tier 2 Local Repair)
- Road Blockage (Tier 3 QPSO Warm Start)

Measures exact wall-clock latencies, stability penalties, and solution quality.
Exports genuine measured results to benchmarks/results/reoptimization_benchmark.csv.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
import sys
import time
from typing import Any

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from dynamic.events import EdgeCongestion, RoadBlockage, VehicleDelay
from dynamic.reoptimizer import (
    DynamicReoptimizer,
    ReoptimizationTier,
    ReoptimizerConfig,
    calculate_stability_penalty,
    full_restart_baseline,
    partition_stops_by_commitment,
)
from routing.cost_oracle import EuclideanOracle, SimulatedEventAdapter, TimeOfDayProfileAdapter
from solver.io import load_solomon
from solver.models import Customer, Problem
from solver.qpso import QPSOConfig, solve_qpso
from solver.validate import validate_solution


def run_reoptimization_benchmarks(
    instance_name: str = "C101.txt",
    num_customers: int = 25,
    out_csv: Path | str = "benchmarks/results/reoptimization_benchmark.csv",
    seed: int = 42,
) -> int:
    """Run dynamic re-optimization benchmark comparing Tiered Re-optimizer to Full Restart."""
    inst_path = Path("benchmarks/instances") / instance_name
    if not inst_path.is_file():
        print(f"[ERROR] Instance file {inst_path} not found!")
        return 1

    print(f"\n[BENCHMARK] Loading {instance_name} (customers: {num_customers})...")
    raw_problem = load_solomon(inst_path)

    if num_customers < raw_problem.num_customers:
        problem = Problem(
            id=f"{raw_problem.id}_{num_customers}",
            depot=raw_problem.depot,
            customers=raw_problem.customers[:num_customers],
            vehicles=raw_problem.vehicles,
        )
        problem.compute_euclidean_matrices(speed=1.0)
    else:
        problem = raw_problem

    # Initialize traffic adapter & oracle
    flat_profile = {h: 1.0 for h in range(24)}
    adapter = SimulatedEventAdapter(base_adapter=TimeOfDayProfileAdapter(flat_profile))
    oracle = EuclideanOracle(base_speed_mps=1.0, use_haversine=False, traffic_adapter=adapter)

    # Initial solution
    print("  -> Solving initial static plan with QPSO...")
    init_config = QPSOConfig(num_particles=25, max_iters=40, seed=seed, apply_tw_repair=True)
    initial_solution, _ = solve_qpso(problem, config=init_config, cost_oracle=oracle)
    print(f"  -> Initial Plan: {len(initial_solution.routes)} routes, Dist: {initial_solution.total_cost:.2f}")

    reopt_config = ReoptimizerConfig(
        theta=0.001,
        theta_absolute=2.0,
        commitment_horizon_seconds=0.0,
        tier3_max_iters=30,
        tier3_particles=25,
        seed=seed,
    )
    reoptimizer = DynamicReoptimizer(problem, cost_oracle=oracle, config=reopt_config)

    # Target the primary multi-stop route in the initial plan
    target_r = max(initial_solution.routes, key=lambda r: len(r.stop_ids))
    s0 = target_r.stop_ids[0]
    s1 = target_r.stop_ids[1] if len(target_r.stop_ids) > 1 else s0
    s_last = target_r.stop_ids[-1]

    # Gather multi-route edges to simulate major cluster closure
    multi_routes = [r for r in initial_solution.routes if len(r.stop_ids) >= 2]
    multi_edges: list[tuple[str, str]] = []
    for r in multi_routes[:3]:
        multi_edges.append((r.stop_ids[0], r.stop_ids[1]))
        if len(r.stop_ids) >= 3:
            multi_edges.append((r.stop_ids[1], r.stop_ids[2]))

    test_events = [
        (
            "Mild Congestion (Delta F <= Theta)",
            EdgeCongestion(
                event_id="evt_mild_cong",
                trigger_time=0.0,
                duration=500.0,
                origin_id=problem.depot.id,
                dest_id=s0,
                multiplier=1.005,  # 0.5% slowdown -> within tolerance
                description="Minor traffic delay on depot exit",
            ),
            0.0,
        ),
        (
            "Corridor Congestion (Tier 1 Path Repair)",
            EdgeCongestion(
                event_id="evt_mod_cong",
                trigger_time=0.0,
                duration=2000.0,
                origin_id=s_last,
                dest_id=problem.depot.id,
                multiplier=1.8,  # 1.8x travel time slowdown on return corridor
                description="Moderate bottleneck on depot return corridor",
            ),
            0.0,
        ),
        (
            "Localized Edge Blockage (Tier 2 Local Repair)",
            RoadBlockage(
                event_id="evt_road_block",
                trigger_time=0.0,
                duration=2000.0,
                origin_id=s0,
                dest_id=s1,
                description="Localized obstruction between consecutive stops",
            ),
            0.0,
        ),
        (
            "Multi-Route Closure (Tier 3 Warm Start)",
            RoadBlockage(
                event_id="evt_corridor_closure",
                trigger_time=0.0,
                duration=2000.0,
                edge_set=multi_edges,
                description="Multi-corridor cluster closure requiring global warm start",
            ),
            0.0,
        ),
    ]

    current_plan = initial_solution
    csv_rows: list[dict[str, Any]] = []

    print("\n" + "=" * 105)
    print(f"{'Event Description':<32} {'Tier':<22} {'T_reopt (ms)':<14} {'T_restart (ms)':<15} {'Speedup':<10} {'Feas':<6}")
    print("=" * 105)

    for desc, event, current_sim_time in test_events:
        # Setup scenario-specific traffic adapter & oracle
        adapter = SimulatedEventAdapter(base_adapter=TimeOfDayProfileAdapter(flat_profile))
        oracle = EuclideanOracle(base_speed_mps=1.0, use_haversine=False, traffic_adapter=adapter)
        reoptimizer = DynamicReoptimizer(problem, cost_oracle=oracle, config=reopt_config)

        # Apply scenario event to traffic adapter
        if hasattr(event, "to_simulated_incidents"):
            for inc in event.to_simulated_incidents():
                adapter.add_incident(inc)

        # 1. Run Tiered Re-optimizer
        reopt_sol, record = reoptimizer.reoptimize(initial_solution, current_time=current_sim_time, event=event)

        # 2. Run Full-Restart Baseline
        restart_sol, restart_ms = full_restart_baseline(
            problem=problem,
            current_solution=initial_solution,
            cost_oracle=oracle,
            current_time=current_sim_time,
            commitment_horizon=reopt_config.commitment_horizon_seconds,
            seed=seed,
            max_iters=100,
            particles=30,
        )

        # Calculate stability penalty of restart vs initial plan
        all_unc: set[str] = set()
        for r in initial_solution.routes:
            _, unc = partition_stops_by_commitment(r, current_sim_time, reopt_config.commitment_horizon_seconds, problem)
            all_unc.update(unc)

        restart_stab, restart_changed = calculate_stability_penalty(initial_solution, restart_sol, all_unc, reopt_config)
        restart_val = validate_solution(problem, restart_sol, cost_oracle=oracle)

        speedup = restart_ms / max(0.001, record.wall_clock_time_ms)
        feas_str = "YES" if record.is_feasible else "NO"

        print(
            f"{desc:<32} {record.tier_selected.value:<22} {record.wall_clock_time_ms:>10.2f} ms "
            f"{restart_ms:>11.2f} ms {speedup:>8.1f}x {feas_str:<6}"
        )

        csv_rows.append(
            {
                "event_id": event.event_id,
                "event_description": desc,
                "timestamp": current_sim_time,
                "tiered_tier": record.tier_selected.value,
                "tiered_latency_ms": record.wall_clock_time_ms,
                "tiered_cost_after": record.cost_after,
                "tiered_delta_f": record.delta_f,
                "tiered_stability_penalty": record.stability_penalty,
                "tiered_stops_changed": record.stops_changed_count,
                "tiered_feasible": record.is_feasible,
                "restart_latency_ms": round(restart_ms, 2),
                "restart_cost_after": round(restart_sol.total_cost, 2),
                "restart_stability_penalty": round(restart_stab, 2),
                "restart_stops_changed": len(restart_changed),
                "restart_feasible": restart_val.is_valid,
                "speedup_factor": round(speedup, 2),
            }
        )

    # Write CSV
    out_file = Path(out_csv)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with out_file.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(csv_rows[0].keys()))
        writer.writeheader()
        writer.writerows(csv_rows)

    print("-" * 105)
    print(f"[SUCCESS] Genuine re-optimization benchmark results written to: {out_file.resolve()}\n")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Dynamic Re-optimizer Benchmark against Full Restart.")
    parser.add_argument("--instance", default="C101.txt", help="Solomon instance file")
    parser.add_argument("--customers", type=int, default=25, help="Customer count (default: 25)")
    parser.add_argument("--out", default="benchmarks/results/reoptimization_benchmark.csv", help="Output CSV path")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    return run_reoptimization_benchmarks(
        instance_name=args.instance,
        num_customers=args.customers,
        out_csv=args.out,
        seed=args.seed,
    )


if __name__ == "__main__":
    sys.exit(main())
