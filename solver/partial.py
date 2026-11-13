"""Partial Plan mode and unserved orders management for Route.it (R19).

When complete coverage is physically infeasible (capacity limits, fleet shortage, tight windows),
Partial Plan mode salvages the highest-value feasible plan by shedding orders in strict priority:
1. Flexible orders (priority <= 1) shed first.
2. Standard orders (priority == 2) shed second.
3. Critical orders (priority >= 3) preserved to the absolute maximum extent.
Tie-break: highest demand-to-distance ratio from depot (shed most inefficient stops first).

Each unserved order includes root cause diagnostics and actionable dispatcher recommendations.
"""

from __future__ import annotations

import math
from typing import Any, Callable, Sequence

from solver.models import Customer, Problem, Route, Solution
from solver.validate import validate_solution


def generate_unserved_order_diagnostic(
    problem: Problem,
    customer: Customer,
    reason_code: str = "time_window_tightness",
) -> dict[str, Any]:
    """Generate diagnostic details and recommendations for an unserved order."""
    depot_dist = math.hypot(customer.lat - problem.depot.lat, customer.lon - problem.depot.lon)
    if problem.coordinate_system == "geographic":
        depot_dist = depot_dist * 111000.0  # Approx metres

    recommendations = []
    if customer.priority >= 3:
        recommendations.append("Assign dedicated express vehicle from backup fleet")
        recommendations.append("Relax hard delivery window by 30-60 minutes with customer consent")
    elif customer.priority == 2:
        recommendations.append("Reschedule delivery to next shift or afternoon dispatch window")
        recommendations.append("Offer customer next-day scheduled slot with discount voucher")
    else:
        recommendations.append("Consolidate with tomorrow's regional batch delivery")
        recommendations.append("Redirect to nearest secure parcel pickup locker")

    return {
        "customer_id": customer.id,
        "name": customer.name or f"Order {customer.id}",
        "priority": customer.priority,
        "priority_level": customer.priority_level,
        "demand": customer.demand,
        "ready_time": customer.ready_time,
        "due_time": customer.due_time,
        "service_time": customer.service_time,
        "distance_from_depot_metres": round(depot_dist, 2),
        "reason": reason_code,
        "recommendations": recommendations,
    }


def solve_partial_plan(
    problem: Problem,
    solve_fn: Callable[[Problem], tuple[Solution, list[float]]],
    max_shed_iterations: int = 15,
) -> Solution:
    """Execute Partial Plan mode to find the maximal feasible customer subset.

    Args:
        problem: Complete Problem instance.
        solve_fn: Callable that takes Problem and returns (Solution, cost_history).
        max_shed_iterations: Maximum customer shedding passes.

    Returns:
        Solution containing feasible routes for served orders, plus an itemized list of unserved orders.
    """
    # 1. Attempt complete solve first
    initial_sol, _ = solve_fn(problem)
    if initial_sol.is_feasible and len(initial_sol.violations) == 0:
        return initial_sol

    # 2. Sort customers to determine shedding candidate order:
    # Key: (priority_score, -efficiency_ratio)
    # Lower priority score (Flexible=1, Standard=2, Critical=3+) sheds FIRST.
    # For equal priority, higher demand / distance sheds first (most resource-heavy).
    def shedding_key(c: Customer) -> tuple[int, float]:
        dist = math.hypot(c.lat - problem.depot.lat, c.lon - problem.depot.lon) + 1e-4
        efficiency = c.demand / dist
        return (c.priority, -efficiency)

    candidates = sorted(problem.customers, key=shedding_key)
    unserved_records: list[dict[str, Any]] = []
    active_customers = list(problem.customers)

    for step in range(min(max_shed_iterations, len(candidates) - 1)):
        # Select next victim to shed
        victim = candidates[step]
        reason = "time_window_tightness"
        # Check if total demand was exceeding fleet capacity
        total_fleet_cap = sum(v.capacity for v in problem.vehicles)
        curr_demand = sum(c.demand for c in active_customers)
        if curr_demand > total_fleet_cap:
            reason = "fleet_capacity_exhausted"

        unserved_records.append(generate_unserved_order_diagnostic(problem, victim, reason_code=reason))
        active_customers = [c for c in active_customers if c.id != victim.id]

        # Form reduced problem
        reduced_prob = Problem(
            id=f"{problem.id}_partial_{step+1}",
            depot=problem.depot,
            customers=active_customers,
            vehicles=problem.vehicles,
            coordinate_system=problem.coordinate_system,
            time_window_boundary=problem.time_window_boundary,
            return_to_depot=problem.return_to_depot,
            planning_mode="partial",
        )
        if problem.travel_time_matrix is not None:
            # Recompute Euclidean matrices or let solver build them
            reduced_prob.compute_euclidean_matrices(speed=1.0)

        sub_sol, _ = solve_fn(reduced_prob)
        if sub_sol.is_feasible and len(sub_sol.violations) == 0:
            # Successfully found feasible subset
            # Compute fleet utilization
            served_demand = sum(c.demand for c in active_customers)
            mobilized_cap = sum(problem.vehicles[i].capacity for i in range(min(len(sub_sol.routes), len(problem.vehicles))))
            util_pct = round((served_demand / mobilized_cap * 100.0), 2) if mobilized_cap > 0 else 0.0

            sub_sol.unserved_orders = unserved_records
            sub_sol.fleet_utilization_pct = util_pct
            sub_sol.feasibility_status = "feasible"
            sub_sol.status_message = (
                f"Partial plan generated: {len(active_customers)} served, {len(unserved_records)} unserved order(s) shed by priority"
            )
            return sub_sol

    # Fallback: if even shedding doesn't resolve (e.g. impossible single critical stop)
    initial_sol.unserved_orders = unserved_records
    initial_sol.feasibility_status = "infeasible"
    initial_sol.status_message = f"Infeasible: could not satisfy constraints even after shedding {len(unserved_records)} order(s)"
    return initial_sol
