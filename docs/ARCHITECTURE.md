# Route.it Architecture Design

## SIH 2026 Problem Statement: SIH26137
**Quantum-Inspired Intelligent Traffic Route Optimization Using Metaheuristic Optimization**

Route.it solves the Capacitated Vehicle Routing Problem with Time Windows (CVRPTW) under time-dependent travel conditions, featuring dynamic re-routing when traffic events occur.

## Key Principles
1. **Classical Algorithm**: Employs Quantum-behaved Particle Swarm Optimization (QPSO, Sun, Feng & Xu 2004) executed purely on classical CPU architectures.
2. **Decomposition**: QPSO explores permutations via continuous random keys; the Prins Split algorithm segments the giant tour into optimal feasible vehicle routes.
3. **Dynamic Re-optimization**: A 3-tiered repair mechanism triggered only when cost variation $\Delta F > \theta$.
4. **Integrity**: Every benchmark number reflects measured, reproducible experimental runs.
