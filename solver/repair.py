"""Time-window repair operator for Route.it CVRPTW solver.

Performs targeted local search repair to eliminate or minimize time-window violations
in multi-route solutions using intra/inter-route relocate and swap operators.
"""

from __future__ import annotations

import copy
import math
from typing import Any
from solver.models import Customer, Problem, Route, Solution
from solver.validate import validate_solution


def _simulate_route_timeline(
    problem: Problem,
    stop_ids: list[str],
    customer_map: dict[str, Customer],
    customer_idx_map: dict[str, int],
    cost_oracle: Any | None,
    loc_depot: Any | None,
    loc_custs: dict[str, Any],
) -> tuple[float, float, float, list[float]]:
    """Simulate route timeline returning (total_distance, total_duration, lateness_violation, arrival_times)."""
    if not stop_ids:
        return 0.0, 0.0, 0.0, []

    curr_time = problem.depot.ready_time
    prev_idx = 0
    prev_loc = loc_depot
    prev_pt = (problem.depot.lat, problem.depot.lon)
    route_dist = 0.0
    tw_viol = 0.0
    arrival_times: list[float] = []

    matrix = problem.travel_time_matrix
    dist_matrix = problem.distance_matrix

    for cid in stop_ids:
        cust = customer_map[cid]
        c_idx = customer_idx_map[cid]
        c_pt = (cust.lat, cust.lon)
        c_loc = loc_custs.get(cid)

        if cost_oracle is not None and prev_loc is not None and c_loc is not None:
            tt = float(cost_oracle.travel_time(prev_loc, c_loc, depart_time=curr_time))
            d = float(cost_oracle.distance(prev_loc, c_loc))
        elif matrix is not None:
            tt = float(matrix[prev_idx][c_idx])
            d = float(dist_matrix[prev_idx][c_idx]) if dist_matrix is not None else tt
        else:
            d = math.hypot(prev_pt[0] - c_pt[0], prev_pt[1] - c_pt[1])
            tt = d

        route_dist += d
        arr = curr_time + tt
        arrival_times.append(arr)

        if arr > cust.due_time:
            lateness = arr - cust.due_time
            p_fac = 1.0 + (cust.priority - 1) * 2.0
            tw_viol += lateness * p_fac

        start_serv = max(arr, cust.ready_time)
        curr_time = start_serv + cust.service_time
        prev_idx = c_idx
        prev_loc = c_loc
        prev_pt = c_pt

    # Return to depot
    depot_pt = (problem.depot.lat, problem.depot.lon)
    if cost_oracle is not None and prev_loc is not None and loc_depot is not None:
        tt = float(cost_oracle.travel_time(prev_loc, loc_depot, depart_time=curr_time))
        d = float(cost_oracle.distance(prev_loc, loc_depot))
    elif matrix is not None:
        tt = float(matrix[prev_idx][0])
        d = float(dist_matrix[prev_idx][0]) if dist_matrix is not None else tt
    else:
        d = math.hypot(prev_pt[0] - depot_pt[0], prev_pt[1] - depot_pt[1])
        tt = d

    route_dist += d
    depot_arr = curr_time + tt
    if depot_arr > problem.depot.due_time:
        tw_viol += (depot_arr - problem.depot.due_time)

    duration = depot_arr - problem.depot.ready_time
    return route_dist, duration, tw_viol, arrival_times


def repair_solution_time_windows(
    problem: Problem,
    solution: Solution,
    cost_oracle: Any | None = None,
    max_passes: int = 50,
) -> Solution:
    """Repair time-window violations in a Solution using relocate, swap, and reordering.

    Args:
        problem: Problem instance.
        solution: Starting solution (which may be infeasible due to time windows).
        cost_oracle: Optional CostOracle for dynamic or road network routing.
        max_passes: Maximum optimization passes over late customers.

    Returns:
        Repaired Solution (with updated routes, cost, and feasibility status).
    """
    if solution.is_feasible and not solution.violations:
        return solution

    customer_map: dict[str, Customer] = {c.id: c for c in problem.customers}
    customer_idx_map: dict[str, int] = {c.id: idx for idx, c in enumerate(problem.customers, start=1)}

    loc_depot = None
    loc_custs: dict[str, Any] = {}
    if cost_oracle is not None:
        from routing.cost_oracle import Location
        loc_depot = Location(id=problem.depot.id, lat=problem.depot.lat, lon=problem.depot.lon)
        for c in problem.customers:
            loc_custs[c.id] = Location(id=c.id, lat=c.lat, lon=c.lon)

    # Work on a mutable copy of stop sequences per route
    route_stops: list[list[str]] = [list(r.stop_ids) for r in solution.routes]
    vehicle_ids: list[str] = [r.vehicle_id for r in solution.routes]
    capacities: list[float] = [
        next((v.capacity for v in problem.vehicles if v.id == vid), problem.vehicles[0].capacity if problem.vehicles else 100.0)
        for vid in vehicle_ids
    ]

    def eval_route(s_ids: list[str]) -> tuple[float, float, float, list[float]]:
        return _simulate_route_timeline(
            problem, s_ids, customer_map, customer_idx_map, cost_oracle, loc_depot, loc_custs
        )

    # Initial state
    current_metrics = [eval_route(s) for s in route_stops]
    total_tw_viol = sum(m[2] for m in current_metrics)

    if total_tw_viol <= 1e-4:
        return solution

    improved = True
    passes = 0

    while improved and passes < max_passes and total_tw_viol > 1e-4:
        improved = False
        passes += 1

        # Scan each route
        for r_idx in range(len(route_stops)):
            stops = route_stops[r_idx]
            if not stops:
                continue

            r_dist, r_dur, r_viol, arr_times = current_metrics[r_idx]
            if r_viol <= 1e-4:
                continue

            # Identify late customers in this route
            for pos in range(len(stops)):
                cid = stops[pos]
                cust = customer_map[cid]
                if arr_times[pos] <= cust.due_time:
                    continue  # not late

                # Strategy 1: Intra-route Relocate (Move late customer earlier in same route)
                for new_pos in range(pos):
                    cand_stops = list(stops)
                    cand_stops.pop(pos)
                    cand_stops.insert(new_pos, cid)

                    c_dist, c_dur, c_viol, c_arrs = eval_route(cand_stops)
                    if c_viol < r_viol - 1e-4:
                        route_stops[r_idx] = cand_stops
                        current_metrics[r_idx] = (c_dist, c_dur, c_viol, c_arrs)
                        total_tw_viol = sum(m[2] for m in current_metrics)
                        improved = True
                        break

                if improved:
                    break

                # Strategy 2: Inter-route Relocate (Move late customer to another route)
                demand = cust.demand
                for other_idx in range(len(route_stops)):
                    if other_idx == r_idx:
                        continue

                    # Check capacity of target route
                    other_load = sum(customer_map[c].demand for c in route_stops[other_idx])
                    if other_load + demand > capacities[other_idx]:
                        continue

                    # Try inserting cid at each position in other route
                    best_cand_other = None
                    best_other_viol = current_metrics[other_idx][2]
                    best_pos = -1

                    for ins_pos in range(len(route_stops[other_idx]) + 1):
                        cand_other = list(route_stops[other_idx])
                        cand_other.insert(ins_pos, cid)
                        o_dist, o_dur, o_viol, o_arrs = eval_route(cand_other)

                        # We evaluate net change in both routes
                        cand_src = list(stops)
                        cand_src.pop(pos)
                        s_dist, s_dur, s_viol, s_arrs = eval_route(cand_src)

                        net_change = (s_viol + o_viol) - (r_viol + current_metrics[other_idx][2])
                        if net_change < -1e-4:
                            # Accepted move!
                            route_stops[r_idx] = cand_src
                            route_stops[other_idx] = cand_other
                            current_metrics[r_idx] = (s_dist, s_dur, s_viol, s_arrs)
                            current_metrics[other_idx] = (o_dist, o_dur, o_viol, o_arrs)
                            total_tw_viol = sum(m[2] for m in current_metrics)
                            improved = True
                            break

                    if improved:
                        break

                if improved:
                    break

                # Strategy 3: Intra-route Swap (Swap with an earlier stop)
                for swap_pos in range(pos):
                    cand_stops = list(stops)
                    cand_stops[pos], cand_stops[swap_pos] = cand_stops[swap_pos], cand_stops[pos]
                    c_dist, c_dur, c_viol, c_arrs = eval_route(cand_stops)
                    if c_viol < r_viol - 1e-4:
                        route_stops[r_idx] = cand_stops
                        current_metrics[r_idx] = (c_dist, c_dur, c_viol, c_arrs)
                        total_tw_viol = sum(m[2] for m in current_metrics)
                        improved = True
                        break

                if improved:
                    break

            if improved:
                break

    # Build final Route objects from repaired sequences
    repaired_routes: list[Route] = []
    total_cost = 0.0

    for r_idx, stops in enumerate(route_stops):
        if not stops:
            continue
        dist, dur, viol, arrs = eval_route(stops)
        load = sum(customer_map[c].demand for c in stops)
        total_cost += dist
        repaired_routes.append(
            Route(
                vehicle_id=vehicle_ids[r_idx],
                stop_ids=stops,
                arrival_times=arrs,
                load=load,
                distance=dist,
                duration=dur,
            )
        )

    # Re-validate with independent validator
    tentative_sol = Solution(
        routes=repaired_routes,
        total_cost=total_cost,
        is_feasible=(total_tw_viol <= 1e-4),
        algorithm=solution.algorithm + " + TW-Repair",
        execution_time_sec=solution.execution_time_sec,
        seed=solution.seed,
    )

    val = validate_solution(problem, tentative_sol, cost_oracle=cost_oracle)
    tentative_sol.is_feasible = val.is_valid
    tentative_sol.violations = val.violations
    tentative_sol.total_cost = val.recomputed_cost

    return tentative_sol


def consolidate_fleet(
    problem: Problem,
    solution: Solution,
    max_vehicles: int,
    cost_oracle: Any | None = None,
) -> Solution:
    """Consolidate routes when the number of routes exceeds available vehicles.

    Greedily eliminates excess routes by inserting stops into retained routes
    subject to vehicle capacity and time window constraints.
    """
    if len(solution.routes) <= max_vehicles:
        return solution

    customer_map: dict[str, Customer] = {c.id: c for c in problem.customers}
    customer_idx_map: dict[str, int] = {c.id: idx for idx, c in enumerate(problem.customers, start=1)}
    cap = problem.vehicles[0].capacity if problem.vehicles else 100.0

    loc_depot = None
    loc_custs: dict[str, Any] = {}
    if cost_oracle is not None:
        from routing.cost_oracle import Location
        loc_depot = Location(id=problem.depot.id, lat=problem.depot.lat, lon=problem.depot.lon)
        for c in problem.customers:
            loc_custs[c.id] = Location(id=c.id, lat=c.lat, lon=c.lon)

    route_stops: list[list[str]] = [list(r.stop_ids) for r in solution.routes if r.stop_ids]

    while len(route_stops) > max_vehicles:
        # Sort routes by cumulative load ascending (try smallest route first)
        route_stops.sort(key=lambda s: sum(customer_map[c].demand for c in s))
        eliminated = False

        for donor_idx in range(len(route_stops)):
            donor = route_stops[donor_idx]
            targets = [list(r) for idx, r in enumerate(route_stops) if idx != donor_idx]

            # Try to place all donor customers feasibly into remaining routes
            cand_targets = [list(r) for r in targets]
            placed_all = True

            for cid in donor:
                cdem = customer_map[cid].demand
                best_t = None
                best_pos = None
                best_cost = 1e12

                for t_idx, tr in enumerate(cand_targets):
                    t_load = sum(customer_map[c].demand for c in tr)
                    if t_load + cdem > cap:
                        continue
                    for pos in range(len(tr) + 1):
                        cand_r = list(tr)
                        cand_r.insert(pos, cid)
                        d, dur, viol, _ = _simulate_route_timeline(
                            problem, cand_r, customer_map, customer_idx_map, cost_oracle, loc_depot, loc_custs
                        )
                        if viol <= 1e-4:
                            cost = d + dur * 0.1
                            if cost < best_cost:
                                best_cost = cost
                                best_t = t_idx
                                best_pos = pos

                if best_t is not None:
                    cand_targets[best_t].insert(best_pos, cid)
                else:
                    placed_all = False
                    break

            if placed_all:
                route_stops = cand_targets
                eliminated = True
                break

        if not eliminated:
            # Fallback best-effort insertion to strictly satisfy vehicle count limit
            donor = route_stops.pop(0)
            for cid in donor:
                cdem = customer_map[cid].demand
                best_t = 0
                best_pos = 0
                best_cost = 1e12
                for t_idx, tr in enumerate(route_stops):
                    t_load = sum(customer_map[c].demand for c in tr)
                    for pos in range(len(tr) + 1):
                        cand_r = list(tr)
                        cand_r.insert(pos, cid)
                        d, dur, viol, _ = _simulate_route_timeline(
                            problem, cand_r, customer_map, customer_idx_map, cost_oracle, loc_depot, loc_custs
                        )
                        cap_pen = max(0.0, (t_load + cdem) - cap) * 1000.0
                        tw_pen = viol * 100.0
                        score = d + cap_pen + tw_pen
                        if score < best_cost:
                            best_cost = score
                            best_t = t_idx
                            best_pos = pos
                route_stops[best_t].insert(best_pos, cid)

    # Reconstruct Route objects
    repaired_routes: list[Route] = []
    tot_cost = 0.0
    for idx, stops in enumerate(route_stops):
        vid = problem.vehicles[idx].id if idx < len(problem.vehicles) else f"V_{idx+1}"
        d, dur, viol, arrs = _simulate_route_timeline(
            problem, stops, customer_map, customer_idx_map, cost_oracle, loc_depot, loc_custs
        )
        load = sum(customer_map[c].demand for c in stops)
        tot_cost += d
        repaired_routes.append(
            Route(vehicle_id=vid, stop_ids=stops, arrival_times=arrs, load=load, distance=d, duration=dur)
        )

    return Solution(
        routes=repaired_routes,
        total_cost=tot_cost,
        is_feasible=True,
        algorithm=solution.algorithm + " + FleetConsolidate",
        execution_time_sec=solution.execution_time_sec,
        seed=solution.seed,
    )


def repair_solution(
    problem: Problem,
    solution: Solution,
    max_vehicles: int | None = None,
    cost_oracle: Any | None = None,
    max_passes: int = 50,
) -> Solution:
    """End-to-end repair operator: consolidates fleet count and repairs time window lateness.

    Guarantees:
    - Exactly max_vehicles routes used (or fewer)
    - All customers visited exactly once
    - Minimizes or eliminates time window and capacity violations
    """
    eff_max = max_vehicles if max_vehicles is not None else (len(problem.vehicles) if problem.vehicles else None)

    # 1. Fleet consolidation if route count exceeds vehicle limit
    if eff_max is not None and len(solution.routes) > eff_max:
        solution = consolidate_fleet(problem, solution, eff_max, cost_oracle=cost_oracle)

    # 2. Time-window repair to eliminate or minimize lateness
    solution = repair_solution_time_windows(problem, solution, cost_oracle=cost_oracle, max_passes=max_passes)

    # 3. Independent validation stamp
    val = validate_solution(problem, solution, cost_oracle=cost_oracle, max_vehicles=eff_max)
    solution.is_feasible = val.is_valid
    solution.violations = val.violations
    if solution.is_feasible:
        solution.total_cost = val.recomputed_cost

    return solution

