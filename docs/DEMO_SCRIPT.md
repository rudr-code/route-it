# Route.it — 3-Minute Live Demo Script (SIH 2026 PS SIH26137)

## Pre-Demo Checklist
1. Start the FastAPI backend:
   ```bash
   uvicorn api.main:app --host 0.0.0.0 --port 8000
   ```
2. Start the React + MapLibre dashboard:
   ```bash
   cd dashboard && npm run dev
   ```
3. (Optional CLI proof): Run `make demo` (`python -m benchmarks.demo_vadodara --mock`).

## Timed Walkthrough (3:00 Total)

### 0:00 – 0:45 | Problem Framing & Scenario Loading
- Click **Load Vadodara (30 stops)** in the left panel.
- Highlight the 30 real delivery stops across Vadodara (Alkapuri, Sayajiganj, Manjalpur, Makarpura, etc.) around the Central Distribution Hub (`22.3072°N, 73.1812°E`), with priority medical/essential stops marked with `⚡` (`C03 Sayajiganj`, `C10 Akota`).
- Point out the honest traffic status badge in the right panel (`🟡 Traffic: simulated` when Valhalla Docker is offline, or `🟢 Traffic: live [Valhalla]` when online).

### 0:45 – 1:45 | Classical QPSO + Prins Split + Memetic Local Search
- Keep default settings (`Particles: 25`, `Iterations: 60`, `Seed: 42`) and click **Solve**.
- Watch the live WebSocket convergence curve in the bottom-left panel stream `gbest_cost` per iteration.
- Explain the two-stage architecture:
  1. **Classical QPSO (Sun, Feng & Xu 2004)** searches continuous random-key space with a single contraction-expansion parameter $\alpha$ (linearly annealed $1.0 \to 0.5$).
  2. **Time-Aware Prins Split** segments each giant tour into optimal capacity- and time-window-feasible vehicle routes in $O(N \cdot B)$ via Numba JIT, refined by 2-opt, relocate, and swap local search.

### 1:45 – 3:00 | Dynamic Traffic Incident & 3-Tier Re-Optimization
- Click **🚦 Congestion** or **🚧 Blockage** in the top map toolbar and click along an active route corridor on the map.
- Show the **Tier Banner** that appears at the bottom of the map:
  - **Impact Check**: Only triggers replanning when $\Delta F > \theta$, incorporating a route-stability penalty so drivers aren't needlessly disrupted.
  - **Tier 1 (Path Repair)**: Re-evaluates ETAs along existing stop sequences in `< 2 ms`.
  - **Tier 2 (Local Repair)**: Relocates/swaps uncommitted stops across nearby routes.
  - **Tier 3 (QPSO Warm Start)**: Re-seeds the quantum-behaved swarm around the current giant-tour keys for major multi-corridor closures.
- Click **📸 Show Before / 🔄 Show After** in the right panel to compare pre-event dashed routes against repaired routes.
