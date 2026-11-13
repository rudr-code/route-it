import sys
import os
import json
import time

sys.path.insert(0, r"D:\SIH_2026_Antigravity_Fixed\SIH 2026 Antigravity")
from api.routes.benchmark import get_default_benchmark_problem
from solver.benchmark import run_algorithm_benchmark, run_scalability_analysis
from solver.qpso import warmup_qpso

def main():
    print("Pre-warming JIT kernels...")
    warmup_qpso()
    print("Warmup complete. Running authentic 5-algorithm benchmark suite...")

    prob = get_default_benchmark_problem()
    t0 = time.time()
    suite = run_algorithm_benchmark(prob, num_particles_or_pop=30, max_iters_or_gen=40, seed=42)
    print(f"Benchmark suite completed in {time.time() - t0:.2f}s")
    for r in suite.results:
        print(f"  {r.algorithm:10s} -> Feasible: {str(r.is_feasible):5s} | Vehicles: {r.num_vehicles_used} | Dist: {r.total_distance_km:5.1f} km | Cost: Rs {r.operational_cost_inr:7.2f} | Time: {r.execution_time_ms:6.1f} ms | Violations: {r.violations}")

    print("\nRunning scalability analysis (10, 25, 50, 100 nodes)...")
    t0 = time.time()
    scalability = run_scalability_analysis(node_sizes=[10, 25, 50, 100], seed=42)
    print(f"Scalability analysis completed in {time.time() - t0:.2f}s")
    for pt in scalability:
        print(f"  Nodes: {pt['num_nodes']:3d} | QPSO: {pt.get('qpso_ms', 0):6.1f}ms ({pt.get('qpso_dist_km', 0)}km) | OR-Tools: {pt.get('ortools_ms', 0):6.1f}ms ({pt.get('ortools_dist_km', 0)}km)")

    output_data = {
        "metadata": {
            "precomputed": True,
            "date": "2026-11-13",
            "machine": "Antigravity Deployment Environment (FastAPI + Numba JIT + QPSO+LS)",
            "description": "Authentic empirical run on Vadodara 20-stop instance. All algorithms strictly evaluated with uniform CVRPTW feasibility validator.",
        },
        "latest": suite.model_dump(),
        "scalability": scalability,
    }

    out_file = r"D:\SIH_2026_Antigravity_Fixed\SIH 2026 Antigravity\benchmarks\precomputed_benchmark.json"
    with open(out_file, "w") as f:
        json.dump(output_data, f, indent=2)

    print(f"\nSuccessfully wrote updated benchmark suite to {out_file}")

if __name__ == "__main__":
    main()
