# Route.it — Judge Q&A Reference (SIH 2026 PS SIH26137)

### 1. "Does 'Quantum-Inspired' require quantum hardware or Qiskit?"
No. Quantum-behaved Particle Swarm Optimization (**QPSO**, Sun, Feng & Xu 2004) is a **100% classical metaheuristic** executed on standard CPUs with Numba JIT compilation. Instead of classical velocity vectors, particles sample positions around a local attractor $p_i$ and the global mean best position (*mbest*) using a Laplace/double-exponential potential well distribution. This eliminates velocity clamping and reduces tuning to a single contraction-expansion parameter $\alpha$.

### 2. "Why separate QPSO from Prins Split instead of encoding vehicles directly in particles?"
Direct vehicle encoding creates invalid or unbalanced partitions under swarm perturbation. By encoding only a continuous random-key giant tour ($N$ floats in $[0, 1]$) and using **Prins (2004) Split** as an exact shortest-path DAG decoder over route segments, every particle maps to a valid segmentation respecting vehicle capacity $Q$, fleet size limits, and customer time windows $[e_i, l_i]$.

### 3. "How do you prevent drivers from getting completely new routes every time a minor delay occurs?"
Our `DynamicReoptimizer` enforces two safeguards:
1. **Commitment Horizon**: Stops already visited or arriving within `commitment_horizon_seconds` are frozen (`committed`).
2. **Impact Check ($\Delta F > \theta$) & Stability Penalty**: Re-planning is skipped (`DO_NOTHING`) if relative cost degradation is within tolerance $\theta$. Candidate repairs are scored with a stability penalty per reassigned stop, Escalating from **Tier 1 (Path Repair)** $\to$ **Tier 2 (Local Search Repair)** $\to$ **Tier 3 (QPSO Warm Start)** only when necessary.

### 4. "What happens if Valhalla or external traffic APIs go offline during operations?"
`CostOracle` degrades gracefully to `EuclideanOracle` with geodesic Haversine distance (at urban speed $8.333\text{ m/s} = 30\text{ km/h}$ for geographic coordinates) and `SimulatedEventAdapter`. Per our strict integrity rules, the dashboard and CLI explicitly label simulated routing rather than claiming live traffic.
