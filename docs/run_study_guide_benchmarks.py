import json
import time
import sys
from api.routes.benchmark import get_default_benchmark_problem
from solver.benchmark import run_algorithm_benchmark, run_scalability_analysis
from benchmarks.demo_vadodara import build_vadodara_problem
from solver.qpso import solve_qpso, QPSOConfig

def run():
    print("=====================================================================")
    print("1. RUNNING REAL MULTI-ALGORITHM BENCHMARK (20 VADODARA STOPS)")
    print("=====================================================================")
    prob20 = get_default_benchmark_problem()
    
    t0 = time.time()
    res20 = run_algorithm_benchmark(
        problem=prob20,
        algorithms=["qpso", "pso", "ga", "dijkstra", "ortools"],
        num_particles_or_pop=25,
        max_iters_or_gen=35,
        seed=42,
    )
    t_bench = time.time() - t0
    print(f"Benchmark finished in {t_bench:.2f}s. Winner: {res20.best_algorithm}")
    
    print("\nRESULTS TABLE (20 STOPS):")
    header = f"{'Algorithm':<22} | {'Feasible':<8} | {'Vehicles':<8} | {'Dist (km)':<10} | {'Duration (min)':<14} | {'Cost (INR)':<11} | {'Solve Time (ms)':<15}"
    print(header)
    print("-" * len(header))
    
    rows_data = []
    for r in res20.results:
        row_str = f"{r.display_name:<22} | {str(r.is_feasible):<8} | {r.num_vehicles_used:<8} | {r.total_distance_km:<10.2f} | {r.total_duration_min:<14.1f} | {r.operational_cost_inr:<11.2f} | {r.execution_time_ms:<15.1f}"
        print(row_str)
        rows_data.append(r.model_dump())

    print("\n=====================================================================")
    print("2. RUNNING NUMBA JIT COLD VS WARM TIMING TEST (30 VADODARA STOPS)")
    print("=====================================================================")
    prob30 = build_vadodara_problem()
    cfg = QPSOConfig(num_particles=25, max_iters=60, seed=42)
    
    # Cold solve (includes JIT compilation)
    t_start = time.time()
    sol_cold, _ = solve_qpso(prob30, config=cfg)
    t_cold = time.time() - t_start
    print(f"Cold run (with Numba JIT compiling): {t_cold:.3f}s, feasible={sol_cold.is_feasible}, total_cost={sol_cold.total_cost:.1f}")
    
    # Warm solve (compiled machine code already cached)
    t_start = time.time()
    sol_warm, _ = solve_qpso(prob30, config=cfg)
    t_warm = time.time() - t_start
    print(f"Warm run (Numba JIT cache active):   {t_warm:.3f}s, feasible={sol_warm.is_feasible}, total_cost={sol_warm.total_cost:.1f}")
    speedup = t_cold / t_warm if t_warm > 0 else 1.0
    print(f"JIT warmup speedup ratio:            {speedup:.2f}x faster on subsequent runs")

    print("\n=====================================================================")
    print("3. RUNNING SCALABILITY ANALYSIS (10, 25, 50, 100 STOPS)")
    print("=====================================================================")
    t_scale_start = time.time()
    scalability_results = run_scalability_analysis(node_sizes=[10, 25, 50, 100], seed=42)
    print(f"Scalability test finished in {time.time() - t_scale_start:.2f}s")
    
    s_header = f"{'Nodes':<7} | {'QPSO Time (ms)':<15} | {'OR-Tools Time (ms)':<18} | {'GA Time (ms)':<13} | {'QPSO Dist (km)':<15} | {'OR-Tools Dist (km)':<18}"
    print(s_header)
    print("-" * len(s_header))
    for s in scalability_results:
        print(f"{s['num_nodes']:<7} | {s['qpso_ms']:<15.1f} | {s['ortools_ms']:<18.1f} | {s['ga_ms']:<13.1f} | {s['qpso_dist_km']:<15.2f} | {s['ortools_dist_km']:<18.2f}")

    # Save to JSON
    output_payload = {
        "benchmark_20_stops": {
            "execution_time_sec": t_bench,
            "best_algorithm": res20.best_algorithm,
            "results": rows_data,
        },
        "numba_jit_analysis": {
            "cold_run_sec": round(t_cold, 4),
            "warm_run_sec": round(t_warm, 4),
            "speedup_ratio": round(speedup, 2),
            "total_cost": round(sol_cold.total_cost, 2),
        },
        "scalability_analysis": scalability_results,
    }
    
    with open("docs/study_guide/benchmark_data.json", "w", encoding="utf-8") as f:
        json.dump(output_payload, f, indent=2)
    print("\nSaved benchmark data to docs/study_guide/benchmark_data.json")

if __name__ == "__main__":
    run()
