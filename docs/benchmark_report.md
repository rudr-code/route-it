# Route.it — Measured Benchmark Report

All figures below come directly from reproducible benchmark artifacts stored in `benchmarks/results/`.

## 1. Memetic Local Search Ablation (`benchmarks/results/a_n32_k5_ls_comparison.json`)
Instance: `A-n32-k5` (31 customers, 5 vehicles, capacity $Q=100$, seed `42`, 30 particles, 100 iterations).

| Solver Configuration | Total Cost | Feasible | Vehicles Used | Runtime (s) | Improvement vs Pure QPSO |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Pure QPSO** | 1351.60 | Yes | 5 | 0.165s | — |
| **Memetic QPSO + Local Search (2-opt / Relocate / Swap)** | 872.43 | Yes | 5 | 0.151s | **+35.45%** |

## 2. Solomon CVRPTW Benchmark Suite (`benchmarks/results/solomon_cvrptw_results.json`)
Evaluated on 25-customer Solomon instances across Clustered (`C101`), Random (`R101`), and Mixed (`RC101`) families (`seed=42`).

| Instance | Family | Customers | Capacity | Routes | Distance | Duration | Waiting Time | Feasible |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **C101_25** | C1 (Clustered) | 25 | 200.0 | 10 | 427.53 | 6542.26 | 3864.73 | Yes (0 violations) |
| **R101_25** | R1 (Random) | 25 | 200.0 | 18 | 1042.42 | 2565.86 | 1273.45 | Yes (0 violations) |
| **RC101_25** | RC1 (Mixed) | 25 | 200.0 | 9 | 870.72 | 1610.74 | 490.03 | Yes (0 violations) |

## 3. Dynamic Tiered Re-Optimization vs Full Restart (`benchmarks/results/reoptimization_benchmark.csv`)

| Dynamic Incident | Selected Tier | Tiered Latency (ms) | Full Restart Latency (ms) | Speedup | Stops Changed (Tiered vs Restart) | Feasible |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **Mild Congestion ($\Delta F \le 	heta$)** | `DO_NOTHING` | 0.45 ms | 425.95 ms | **950.8x** | 0 vs 21 | Yes |
| **Corridor Congestion** | `TIER_1_PATH_REPAIR` | 1.64 ms | 441.15 ms | **269.3x** | 0 vs 22 | Yes |
| **Localized Edge Blockage** | `TIER_2_LOCAL_REPAIR` | 659.04 ms | 402.90 ms | 0.61x | **2 vs 21** (90% fewer disruptions) | Yes |
| **Multi-Route Closure** | `TIER_3_QPSO_WARM_START` | 969.30 ms | 450.18 ms | 0.46x | **21 vs 25** | Yes |

## 4. Canonical Vadodara 30-Stop Urban Delivery Scenario (`benchmarks/results/vadodara_30_routes.geojson`)
- **Instance**: `benchmarks/instances/vadodara_30.json` (30 stops, 235 total demand units, 6 vehicles with capacity 80 units).
- **Solution**: **4 active vehicles**, **75.05 km** total distance, **100% feasible** (0 capacity or time-window violations).
