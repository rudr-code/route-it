# Route.it - Assumptions & Design Decisions Needing Stakeholder Confirmation

This document records all baseline assumptions, sensible defaults, and architectural trade-offs adopted in Route.it (SIH 2026, Problem Statement SIH26137). Where competition guidelines or requirement documents left operational numbers or behaviors unspecified, the project implements conservative, verifiable defaults that can be adjusted via API and UI parameters without code changes.

---

## 1. Enterprise Business Cost Parameters (R9, R21, AC-10)

### Unspecified Requirement Gap
The competition requirements specify that total fleet cost $J = C_{\text{OPEX}} + C_{\text{Fleet}} + C_{\text{SLA}}$ must be configurable and must not be hardcoded, but do not fix mandated national statutory or enterprise cost rates.

### Implemented Baseline Defaults
- **Distance OPEX Rate ($r_d$)**: ₹8.00 per kilometre (₹0.008 per metre).
- **Time OPEX Rate ($r_t$)**: ₹100.00 per hour (₹0.0278 per second). Paid operating time begins at vehicle depot dispatch and covers transit, customer service, waiting, and depot return. Depot waiting prior to initial dispatch is not charged (R22).
- **Vehicle Activation Fee ($F_k$)**: ₹300.00 per vehicle per operational shift.
- **SLA Lateness Penalty Rates ($p_i$)**:
  - **Critical Priority (Level 3+)**: ₹10.00 per minute of lateness.
  - **Standard Priority (Level 2)**: ₹5.00 per minute of lateness.
  - **Flexible Priority (Level 1)**: ₹2.00 per minute of lateness.

### Hand-Computed Verification (AC-10)
For a 2-vehicle dispatch covering 50.0 km total travel distance, 3.0 hours total duration, and 15 minutes of SLA lateness on a Critical order:
$$\begin{aligned}
C_{\text{distance}} &= 50 \times 8.00 = ₹400.00 \\
C_{\text{time}} &= 3 \times 100.00 = ₹300.00 \\
C_{\text{activation}} &= 2 \times 300.00 = ₹600.00 \\
C_{\text{SLA}} &= 15 \times 10.00 = ₹150.00 \\
\mathbf{Total} &= \mathbf{₹1,450.00}
\end{aligned}$$
*Status*: Fully implemented in `solver/cost.py:BusinessCostConfig`, exposed in `api/models.py:SolveRequest`, rendered dynamically in `AdminPortal.tsx`, and verified by `tests/test_cost_model.py` and `tests/test_acceptance.py::test_AC_10`.

---

## 2. Time-Window Boundary Semantics (R14, AC-03)

### Unspecified Requirement Gap
Academic literature (Solomon 1987 VRPTW benchmarks) defines feasible customer arrival at service start ($A_i \le b_i$), whereas enterprise courier SLAs define delivery completion before the customer closes ($D_i = \max(A_i, a_i) + s_i \le b_i$).

### Implemented Baseline Defaults
- **Planar Benchmark Instances (`coordinate_system="planar"`)**: Default to `"start"` boundary ($A_i \le b_i$) so that Solomon C101/R101/RC101 benchmarks remain mathematically authentic and reproducible against published operational research baselines.
- **Geographic / Live Instances (`coordinate_system="geographic"`)**: Default to `"completion"` boundary ($D_i \le b_i$).
- **Explicit Override**: Any problem or solve request can explicitly specify `time_window_boundary: "completion" | "start"` to override the coordinate-system default.

---

## 3. Planning Modes & Unserved Orders Policy (R19, AC-02, AC-09)

### Implemented Baseline Defaults
- **Complete Plan Mode (`planning_mode="complete"`)**: All customer orders are mandatory. If capacity, fleet size, or hard time windows cannot satisfy every order, the solution is explicitly classified as `infeasible` with itemized violation causes.
- **Partial Plan Mode (`planning_mode="partial"`)**: If complete service is physically impossible, the engine automatically sheds unserviceable orders in strict priority order:
  1. *Flexible Orders* (priority $\le 1$) shed first.
  2. *Standard Orders* (priority $= 2$) shed second.
  3. *Critical Orders* (priority $\ge 3$) are preserved to the maximum extent.
  - *Tie-breaker*: Orders with higher demand-to-depot-distance ratio are shed first to maximize remaining fleet efficiency.
- **Diagnostics**: Every unserved order is returned with a machine-readable root cause (`"fleet_capacity_exhausted"`, `"time_window_tightness"`) and actionable dispatcher recommendations.

---

## 4. Depot Return Policy (R6, R16, AC-07)

### Implemented Baseline Defaults
- Supported at both the Problem level (`problem.return_to_depot`) and individual Vehicle level (`vehicle.return_to_depot`).
- When `return_to_depot=True` (default for closed distribution routes), the final leg from the last customer back to the depot is included in route distance, travel duration, cost, and depot operating window validation.
- When `return_to_depot=False` (open VRP mode, e.g., third-party gig couriers ending at their last delivery), the return leg is excluded from distance, time, and cost calculations.

---

## 5. Mapping & Geocoding Provider Deviation (DEV-01)

### Documented Deviation
- **Requirement mention**: Mapbox API / Google Maps.
- **Implemented Solution**: OpenStreetMap tiles, MapLibre GL JS, Valhalla open-source routing engine, and OpenStreetMap Nominatim reverse geocoding.
- **Justification**:
  1. Strict adherence to **Zero Paid Services / No API Keys** mandate.
  2. Eliminates quota lockouts, rate limiting, and vendor billing lock-in.
  3. Provides identical turn-by-turn routing, polyline geometry, and reverse-geocoding functionality without compromising privacy or autonomy.

---

## 6. Postponed Features (P1 - P8)

As instructed by competition scope guidelines, the following advanced capabilities are deliberately marked **Postponed** and are **NOT** implemented or claimed in the MVP:
- **P1**: Driver working hours regulations (maximum continuous driving hours).
- **P2**: Mandatory driver rest breaks and meal stops.
- **P3**: Multiple drivers per vehicle (team driving).
- **P4**: Heterogeneous vehicle fleets with specialized compartments (e.g., dual-temperature frozen/chilled).
- **P5**: Multi-depot operations with inter-depot linehaul transfers.
- **P6**: Live external commercial traffic telemetry feeds (simulated Ichoua-style speed adapter provided instead).
- **P7**: Mobile hardware telemetry / physical driver GPS smartphone app tracking.
- **P8**: Regulatory compliance checks (HazMat routing, low-emission zone restrictions).

---

## 7. Algorithm Positioning & Academic Honesty (AC-12)

### Algorithmic Reality
- **Algorithm**: Quantum-behaved Particle Swarm Optimization (QPSO) combined with Prins (2004) DAG split and targeted local-search repair.
- **Execution Environment**: Runs exclusively on classical x86/x64 hardware using standard Python and Numba JIT.
- **Scientific Honesty**: QPSO is a **classical metaheuristic** inspired by quantum delta-potential well wave functions ($\psi(x)$). It **does NOT** utilize physical quantum processors (QPUs), quantum annealing, or gate-based quantum circuits, and achieves **no physical quantum advantage**. Claims of "quantum speedup" are strictly rejected in all project documentation and user interfaces.
