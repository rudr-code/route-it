# Route.it Architecture Design

## SIH 2026 Problem Statement: SIH26137
**Quantum-Inspired Intelligent Traffic Route Optimization Using Metaheuristic Optimization**

Route.it solves the Capacitated Vehicle Routing Problem with Time Windows (CVRPTW) under time-dependent travel conditions, featuring dynamic re-routing when traffic events occur.

## Key Principles
1. **Classical Algorithm**: Employs Quantum-behaved Particle Swarm Optimization (QPSO, Sun, Feng & Xu 2004) executed purely on classical CPU architectures.
2. **Decomposition**: QPSO explores permutations via continuous random keys; the Prins Split algorithm segments the giant tour into optimal feasible vehicle routes.
3. **Dynamic Re-optimization**: A 3-tiered repair mechanism triggered only when cost variation $\Delta F > \theta$.
4. **Integrity**: Every benchmark number reflects measured, reproducible experimental runs.

## Unit Contract & Physical Standards

Route.it enforces a strict SI unit contract across domain models, API schemas, solver state, and telemetry:

| Dimension | Standard Unit | Symbol | Semantics & Range |
| :--- | :--- | :---: | :--- |
| **Distance** | Metres | $m$ | Cumulative travel distance along road edges or geodesic arcs (`Route.distance`). |
| **Time & Duration** | Seconds | $s$ | Cumulative durations and timestamps measured from operational start-of-day (`ready_time`, `due_time`, `service_time`, `arrival_times`, `shift_start`, `shift_end`, `duration`). |
| **Speed** | Metres per second | $m/s$ | Base vehicle travel speed. Default urban speed: $8.333\ m/s$ ($30\ km/h$). |
| **Capacity / Demand** | Dimensionless / Units | - | Demand items or mass units required per customer vs vehicle payload capacity (`demand`, `capacity`, `load`). |
| **Cost** | Currency / Cost units | - | Evaluated as $\text{cost} = \text{distance} \times c_{\text{dist}} + \text{duration} \times c_{\text{time}} + \text{fixed\_cost}$. |

*Frontend Convention*: The user dashboard displays user-facing units ($km$ and $h$/$m$ clock times) by converting directly from SI base units ($km = m / 1000$, $\text{time} = \lfloor s / 60 \rfloor$), with zero heuristic guessing.

## Coordinate Reference Systems

`Problem` and `SolveRequest` explicitly declare their spatial reference system via `coordinate_system`:
- **`geographic`** (Default): WGS84 GPS latitude and longitude in decimal degrees (e.g. Vadodara: $22.3072^\circ\text{N}, 73.1812^\circ\text{E}$). The `CostOracle` computes geodesic distances in metres via the Haversine formula (or road network distance via Valhalla).
- **`planar`**: Euclidean Cartesian plane coordinates $(x, y)$ used by classic benchmarks (e.g. Solomon 1987, CVRPLIB-X). Distances are computed via Euclidean hypotenuse $\sqrt{\Delta x^2 + \Delta y^2}$ with no auto-detection or spherical projection.
