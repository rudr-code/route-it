"""Dynamic Route Re-optimizer with Tiered Escalation for Route.it.

Features:
- Impact Check: Evaluates cost delta (delta F) and critical road blockages.
- Stability Penalty: Freezes visited and committed stops, penalizing route flip-flopping.
- Tier 1 Path Repair: Re-evaluates timeline maintaining stop sequences.
- Tier 2 Local Repair: Targeted relocate and swap operators on affected uncommitted stops.
- Tier 3 QPSO Warm Start: Swarm seeded around previous keys with reduced iterations and elevated alpha.
- Escalation Logic: Ascends tiers by severity; accepts result only if feasible and superior to do-nothing.
- Audit Logging: Accurate wall-clock timing, cost delta, and stop mutation tracking.
- Full-Restart Baseline: Standard cold-start benchmark comparator.
"""

from __future__ import annotations

import copy
from enum import Enum
import logging
import math
import time
from typing import Any, Sequence
import numpy as np
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

from dynamic.events import AnyDynamicEvent
from routing.cost_oracle import CostOracle, Location, to_location
from solver.local_search import project_tour_to_keys
from solver.models import Customer, Depot, Problem, Route, Solution, Vehicle
from solver.qpso import QPSOConfig, solve_qpso
from solver.validate import ValidationResult, validate_solution


class ReoptimizationTier(str, Enum):
    """Categorization of re-optimization tiers."""

    DO_NOTHING = "DO_NOTHING"
    TIER_1_PATH_REPAIR = "TIER_1_PATH_REPAIR"
    TIER_2_LOCAL_REPAIR = "TIER_2_LOCAL_REPAIR"
    TIER_3_QPSO_WARM_START = "TIER_3_QPSO_WARM_START"
    FALLBACK = "FALLBACK"


class ReoptimizerConfig(BaseModel):
    """Configuration settings for dynamic route re-optimization."""

    theta: float = Field(0.05, ge=0.0, description="Relative cost delta threshold to trigger re-planning (e.g. 5%)")
    theta_absolute: float = Field(15.0, ge=0.0, description="Absolute cost delta threshold in seconds/distance")
    commitment_horizon_seconds: float = Field(300.0, ge=0.0, description="Horizon within which imminent stops are frozen")
    lambda_veh: float = Field(50.0, ge=0.0, description="Stability penalty per customer moved to a different vehicle")
    lambda_order: float = Field(10.0, ge=0.0, description="Stability penalty per customer order inversion on same vehicle")

    # Tier 3 QPSO Warm Start settings
    tier3_max_iters: int = Field(40, ge=5, description="Reduced iteration budget for warm-start swarm")
    tier3_particles: int = Field(30, ge=5, description="Swarm size for warm-start swarm")
    tier3_alpha_max: float = Field(1.2, gt=0.0, description="Elevated initial alpha for exploratory jumping")
    tier3_alpha_min: float = Field(0.4, gt=0.0, description="Final alpha for convergence")
    tier3_seed_fraction: float = Field(0.6, ge=0.1, le=1.0, description="Fraction of swarm seeded around previous keys")
    seed: int = Field(42, description="Random seed for reproducible re-optimization")


class ReoptimizationRecord(BaseModel):
    """Audit log entry capturing performance and outcome of a dynamic re-plan."""

    event_id: str = Field(..., description="Triggering event identifier or label")
    timestamp: float = Field(..., description="Simulation timestamp in seconds")
    tier_selected: ReoptimizationTier = Field(..., description="Executed re-optimization tier")
    wall_clock_time_ms: float = Field(..., description="Measured execution duration in milliseconds")
    cost_before: float = Field(..., description="Plan cost under new conditions prior to re-optimization")
    cost_after: float = Field(..., description="Final plan cost after re-optimization")
    delta_f: float = Field(..., description="Raw cost delta: cost_after - cost_before")
    stability_penalty: float = Field(0.0, description="Calculated penalty for stop reassignment and reordering")
    stops_changed_count: int = Field(0, description="Number of customer stops whose vehicle or order changed")
    stops_changed: list[str] = Field(default_factory=list, description="IDs of customer stops changed")
    is_feasible: bool = Field(..., description="Whether final solution satisfies all operational constraints")
    message: str = Field("", description="Summary description of re-optimization decision")


def partition_stops_by_commitment(
    route: Route,
    current_time: float,
    commitment_horizon: float,
    problem: Problem,
) -> tuple[list[str], list[str]]:
    """Partition a route's stops into frozen prefix stops and uncommitted suffix stops.

    - Visited stops (arrival + service <= current_time) are FROZEN.
    - Imminent stops (arrival - current_time <= commitment_horizon) are COMMITTED / FROZEN.
    - Remaining stops are UNCOMMITTED (eligible for re-planning).

    Args:
        route: Assigned vehicle route.
        current_time: Current simulation timestamp.
        commitment_horizon: Window in seconds defining driver commitment.
        problem: Problem instance.

    Returns:
        (frozen_stops, uncommitted_stops)
    """
    frozen: list[str] = []
    uncommitted: list[str] = []

    for idx, sid in enumerate(route.stop_ids):
        arr = route.arrival_times[idx] if idx < len(route.arrival_times) else 0.0
        cust = problem.get_customer(sid)

        # Stop is completed
        if arr + cust.service_time <= current_time:
            frozen.append(sid)
        # Stop is currently active or within commitment horizon
        elif arr - current_time <= commitment_horizon:
            frozen.append(sid)
        else:
            uncommitted.append(sid)

    return frozen, uncommitted


def calculate_stability_penalty(
    old_solution: Solution,
    new_solution: Solution,
    uncommitted_stops: set[str],
    config: ReoptimizerConfig,
) -> tuple[float, list[str]]:
    """Calculate the stability penalty for modifying uncommitted stops versus the previous plan.

    Penalizes:
    - Moving an uncommitted stop to a different vehicle (lambda_veh)
    - Inverting the relative order between two uncommitted stops on the same vehicle (lambda_order)

    Args:
        old_solution: Baseline solution prior to re-planning.
        new_solution: Proposed re-optimized solution.
        uncommitted_stops: Set of customer stop IDs that were eligible for re-planning.
        config: Reoptimizer configuration.

    Returns:
        (total_penalty, list_of_changed_stop_ids)
    """
    if not uncommitted_stops:
        return 0.0, []

    # Map customer ID to (vehicle_id, position) in old solution
    old_map: dict[str, tuple[str, int]] = {}
    for r in old_solution.routes:
        for pos, sid in enumerate(r.stop_ids):
            if sid in uncommitted_stops:
                old_map[sid] = (r.vehicle_id, pos)

    # Map customer ID to (vehicle_id, position) in new solution
    new_map: dict[str, tuple[str, int]] = {}
    for r in new_solution.routes:
        for pos, sid in enumerate(r.stop_ids):
            if sid in uncommitted_stops:
                new_map[sid] = (r.vehicle_id, pos)

    changed_stops: list[str] = []
    reassigned_count = 0
    inversion_count = 0

    # 1. Check vehicle reassignment
    for sid in uncommitted_stops:
        old_v = old_map.get(sid, (None, 0))[0]
        new_v = new_map.get(sid, (None, 0))[0]
        if old_v != new_v:
            reassigned_count += 1
            changed_stops.append(sid)

    # 2. Check relative order inversions on the same vehicle
    for r in new_solution.routes:
        v_stops = [sid for sid in r.stop_ids if sid in uncommitted_stops and old_map.get(sid, (None, 0))[0] == r.vehicle_id]
        n_v = len(v_stops)
        for i in range(n_v):
            for j in range(i + 1, n_v):
                s_i, s_j = v_stops[i], v_stops[j]
                old_pos_i = old_map[s_i][1]
                old_pos_j = old_map[s_j][1]
                # If order flipped
                if old_pos_i > old_pos_j:
                    inversion_count += 1
                    if s_i not in changed_stops:
                        changed_stops.append(s_i)
                    if s_j not in changed_stops:
                        changed_stops.append(s_j)

    penalty = config.lambda_veh * reassigned_count + config.lambda_order * inversion_count
    return penalty, changed_stops


def evaluate_solution_under_oracle(
    solution: Solution,
    problem: Problem,
    cost_oracle: CostOracle,
    current_time: float = 0.0,
) -> tuple[float, bool, bool]:
    """Evaluate a solution under the given CostOracle.

    Returns:
        (total_cost, has_blockage, has_tw_violation)
    """
    total_cost = 0.0
    has_blockage = False
    has_tw_viol = False

    depot_loc = to_location(problem.depot)

    for r in solution.routes:
        if not r.stop_ids:
            continue

        veh = next((v for v in problem.vehicles if v.id == r.vehicle_id), None)
        if veh is None:
            logger.warning(
                "Route vehicle_id '%s' not found in problem.vehicles; falling back to unit costs (c_dist=1.0, c_time=1.0)",
                r.vehicle_id,
            )
            c_dist = 1.0
            c_time = 1.0
        else:
            c_dist = veh.cost_per_distance
            c_time = veh.cost_per_time

        curr_time = max(current_time, problem.depot.ready_time)
        prev_loc = depot_loc
        route_dist = 0.0

        for sid in r.stop_ids:
            cust = problem.get_customer(sid)
            c_loc = to_location(cust)

            if not math.isfinite(curr_time):
                tt = float("inf")
                dist = 0.0
            else:
                tt = cost_oracle.travel_time(prev_loc, c_loc, depart_time=curr_time)
                dist = cost_oracle.distance(prev_loc, c_loc)

            if not math.isfinite(tt):
                has_blockage = True
                tt = 1e9  # Large finite number for cost accounting

            arr_time = curr_time + tt
            route_dist += dist

            if arr_time > cust.due_time:
                has_tw_viol = True
                total_cost += (arr_time - cust.due_time) * 100.0

            curr_time = (max(arr_time, cust.ready_time) + cust.service_time) if math.isfinite(arr_time) else float("inf")
            prev_loc = c_loc

        # Return to depot
        if math.isfinite(curr_time):
            tt_back = cost_oracle.travel_time(prev_loc, depot_loc, depart_time=curr_time)
            dist_back = cost_oracle.distance(prev_loc, depot_loc)
            route_dist += dist_back
            if not math.isfinite(tt_back):
                has_blockage = True
                route_dur = 1e7
            else:
                route_dur = (curr_time + tt_back) - max(current_time, problem.depot.ready_time)
        else:
            has_blockage = True
            route_dur = 1e7

        total_cost += route_dist * c_dist + route_dur * c_time

    if has_blockage:
        total_cost += 1e7

    return total_cost, has_blockage, has_tw_viol


class DynamicReoptimizer:
    """Tiered dynamic re-optimizer for Route.it fleet routing."""

    def __init__(
        self,
        problem: Problem,
        cost_oracle: CostOracle | None = None,
        config: ReoptimizerConfig | None = None,
    ) -> None:
        """Initialize re-optimizer.

        Args:
            problem: Global CVRPTW problem instance.
            cost_oracle: CostOracle representing active road and traffic network.
            config: Configuration parameters.
        """
        from routing.cost_oracle import EuclideanOracle

        self.problem = problem
        self.cost_oracle = cost_oracle or EuclideanOracle(
            coordinate_system=problem.coordinate_system,
            base_speed_mps=8.333 if problem.coordinate_system == "geographic" else 1.0,
        )
        self.config = config or ReoptimizerConfig()
        self.audit_log: list[ReoptimizationRecord] = []

    def _calc_route_cost(self, r: Route) -> float:
        """Calculate route cost with explicit warning if vehicle ID is not in problem.vehicles."""
        veh = next((v for v in self.problem.vehicles if v.id == r.vehicle_id), None) if self.problem.vehicles else None
        if veh is None:
            logger.warning(
                "Route vehicle_id '%s' not found in problem.vehicles; falling back to unit costs (c_dist=1.0, c_time=1.0)",
                r.vehicle_id,
            )
            c_dist = 1.0
            c_time = 1.0
        else:
            c_dist = veh.cost_per_distance
            c_time = veh.cost_per_time
        return r.distance * c_dist + r.duration * c_time

    def check_impact(
        self,
        current_solution: Solution,
        current_time: float = 0.0,
    ) -> tuple[bool, str, float, bool]:
        """Check whether the new traffic conditions require re-planning.

        Re-plans only if:
        1. A critical edge on a remaining planned route is blocked (travel_time == inf), OR
        2. A time-window violation occurs, OR
        3. Delta F > theta * cost_before and Delta F > theta_absolute.

        Returns:
            (should_replan, reason, delta_f, is_blocked)
        """
        cost_under_new, is_blocked, has_tw_viol = evaluate_solution_under_oracle(
            current_solution, self.problem, self.cost_oracle, current_time
        )
        cost_before = sum(self._calc_route_cost(r) for r in current_solution.routes)
        if cost_before <= 0.0:
            cost_before = current_solution.total_cost
        delta_f = cost_under_new - cost_before

        if is_blocked:
            return True, "Critical planned corridor is blocked", delta_f, True

        if has_tw_viol:
            return True, f"Time-window breach under new traffic (delta_F={delta_f:.1f})", delta_f, False

        rel_delta = delta_f / max(1.0, cost_before)
        if delta_f > self.config.theta_absolute and rel_delta > self.config.theta:
            return (
                True,
                f"Significant traffic delay: delta_F={delta_f:.1f} ({rel_delta * 100:.1f}% > {self.config.theta * 100:.1f}%)",
                delta_f,
                False,
            )

        return (
            False,
            f"Traffic impact within tolerance: delta_F={delta_f:.1f} ({rel_delta * 100:.1f}% <= {self.config.theta * 100:.1f}%)",
            delta_f,
            False,
        )

    def reoptimize(
        self,
        current_solution: Solution,
        current_time: float = 0.0,
        event: AnyDynamicEvent | None = None,
    ) -> tuple[Solution, ReoptimizationRecord]:
        """Execute tiered re-optimization triggered by a dynamic traffic event.

        Ascends through:
        - Tier 1: Path Repair (re-route segment, keep stop sequence)
        - Tier 2: Local Repair (relocate/swap only affected stops/routes)
        - Tier 3: QPSO Warm Start (swarm seeded around previous solution keys)
        - Fallback: Best feasible solution or do-nothing plan.

        Args:
            current_solution: Current active fleet solution.
            current_time: Simulation timestamp.
            event: Optional triggering event.

        Returns:
            (reoptimized_solution, audit_record)
        """
        start_wall_clock = time.perf_counter()
        event_id = event.event_id if event is not None else f"evt_t{current_time:.0f}"

        # 1. Impact Assessment
        should_replan, reason, delta_f, is_blocked = self.check_impact(
            current_solution, current_time
        )

        cost_before = current_solution.total_cost

        # Determine uncommitted stops across all routes
        all_uncommitted: set[str] = set()
        frozen_by_vehicle: dict[str, list[str]] = {}
        uncommitted_by_vehicle: dict[str, list[str]] = {}

        for r in current_solution.routes:
            frz, unc = partition_stops_by_commitment(
                r, current_time, self.config.commitment_horizon_seconds, self.problem
            )
            frozen_by_vehicle[r.vehicle_id] = frz
            uncommitted_by_vehicle[r.vehicle_id] = unc
            all_uncommitted.update(unc)

        if not should_replan or not all_uncommitted:
            # Do Nothing: Keep current plan
            elapsed_ms = (time.perf_counter() - start_wall_clock) * 1000.0
            rec = ReoptimizationRecord(
                event_id=event_id,
                timestamp=current_time,
                tier_selected=ReoptimizationTier.DO_NOTHING,
                wall_clock_time_ms=round(elapsed_ms, 3),
                cost_before=round(cost_before, 2),
                cost_after=round(cost_before, 2),
                delta_f=round(delta_f, 2),
                stability_penalty=0.0,
                stops_changed_count=0,
                stops_changed=[],
                is_feasible=current_solution.is_feasible,
                message=reason,
            )
            self.audit_log.append(rec)
            return current_solution, rec

        # Evaluate do-nothing baseline under new conditions
        cost_do_nothing, dn_blocked, dn_tw_viol = evaluate_solution_under_oracle(
            current_solution, self.problem, self.cost_oracle, current_time
        )
        cost_do_nothing = round(cost_do_nothing, 2)
        best_objective = cost_do_nothing if not dn_blocked and not dn_tw_viol else float("inf")
        best_solution = current_solution
        chosen_tier = ReoptimizationTier.FALLBACK
        stops_changed_best: list[str] = []
        stability_pen_best = 0.0

        # -------------------------------------------------------------------
        # TIER 1: Path Repair (Keep stop sequence, update timeline via router)
        # -------------------------------------------------------------------
        t1_sol = self._tier_1_path_repair(current_solution, current_time)
        t1_report = validate_solution(self.problem, t1_sol, cost_oracle=self.cost_oracle)

        if t1_report.is_valid:
            t1_stab, t1_changed = calculate_stability_penalty(
                current_solution, t1_sol, all_uncommitted, self.config
            )
            t1_total_obj = t1_sol.total_cost + t1_stab
            if t1_total_obj <= best_objective + 0.05:
                best_objective = t1_total_obj
                best_solution = t1_sol
                chosen_tier = ReoptimizationTier.TIER_1_PATH_REPAIR
                stops_changed_best = t1_changed
                stability_pen_best = t1_stab

        # If Tier 1 resolved the issue satisfactorily and did not encounter blockages, accept Tier 1
        if chosen_tier == ReoptimizationTier.TIER_1_PATH_REPAIR and not is_blocked:
            elapsed_ms = (time.perf_counter() - start_wall_clock) * 1000.0
            rec = ReoptimizationRecord(
                event_id=event_id,
                timestamp=current_time,
                tier_selected=chosen_tier,
                wall_clock_time_ms=round(elapsed_ms, 3),
                cost_before=round(cost_before, 2),
                cost_after=round(best_solution.total_cost, 2),
                delta_f=round(best_solution.total_cost - cost_before, 2),
                stability_penalty=round(stability_pen_best, 2),
                stops_changed_count=len(stops_changed_best),
                stops_changed=stops_changed_best,
                is_feasible=True,
                message="Accepted Tier 1 Path Repair (preserved stop sequence)",
            )
            self.audit_log.append(rec)
            return best_solution, rec

        # -------------------------------------------------------------------
        # TIER 2: Local Repair (Relocate/swap on affected uncommitted stops)
        # -------------------------------------------------------------------
        t2_sol = self._tier_2_local_repair(
            current_solution, frozen_by_vehicle, uncommitted_by_vehicle, current_time
        )
        t2_report = validate_solution(self.problem, t2_sol, cost_oracle=self.cost_oracle)

        if t2_report.is_valid:
            t2_stab, t2_changed = calculate_stability_penalty(
                current_solution, t2_sol, all_uncommitted, self.config
            )
            t2_total_obj = t2_sol.total_cost + t2_stab
            if t2_total_obj < best_objective:
                best_objective = t2_total_obj
                best_solution = t2_sol
                chosen_tier = ReoptimizationTier.TIER_2_LOCAL_REPAIR
                stops_changed_best = t2_changed
                stability_pen_best = t2_stab

        # If Tier 2 resolved the issue, accept Tier 2
        if chosen_tier == ReoptimizationTier.TIER_2_LOCAL_REPAIR:
            elapsed_ms = (time.perf_counter() - start_wall_clock) * 1000.0
            rec = ReoptimizationRecord(
                event_id=event_id,
                timestamp=current_time,
                tier_selected=chosen_tier,
                wall_clock_time_ms=round(elapsed_ms, 3),
                cost_before=round(cost_before, 2),
                cost_after=round(best_solution.total_cost, 2),
                delta_f=round(best_solution.total_cost - cost_before, 2),
                stability_penalty=round(stability_pen_best, 2),
                stops_changed_count=len(stops_changed_best),
                stops_changed=stops_changed_best,
                is_feasible=True,
                message="Accepted Tier 2 Local Repair (relocate/swap on affected routes)",
            )
            self.audit_log.append(rec)
            return best_solution, rec

        # -------------------------------------------------------------------
        # TIER 3: QPSO Warm Start (Swarm seeded around previous keys)
        # -------------------------------------------------------------------
        t3_sol = self._tier_3_qpso_warm_start(
            current_solution, frozen_by_vehicle, uncommitted_by_vehicle, current_time
        )
        t3_report = validate_solution(self.problem, t3_sol, cost_oracle=self.cost_oracle)

        if t3_report.is_valid:
            t3_stab, t3_changed = calculate_stability_penalty(
                current_solution, t3_sol, all_uncommitted, self.config
            )
            t3_total_obj = t3_sol.total_cost + t3_stab
            if t3_total_obj < best_objective:
                best_objective = t3_total_obj
                best_solution = t3_sol
                chosen_tier = ReoptimizationTier.TIER_3_QPSO_WARM_START
                stops_changed_best = t3_changed
                stability_pen_best = t3_stab

        # -------------------------------------------------------------------
        # Fallback / Final Evaluation
        # -------------------------------------------------------------------
        elapsed_ms = (time.perf_counter() - start_wall_clock) * 1000.0
        final_val = validate_solution(self.problem, best_solution, cost_oracle=self.cost_oracle)

        rec = ReoptimizationRecord(
            event_id=event_id,
            timestamp=current_time,
            tier_selected=chosen_tier,
            wall_clock_time_ms=round(elapsed_ms, 3),
            cost_before=round(cost_before, 2),
            cost_after=round(best_solution.total_cost, 2),
            delta_f=round(best_solution.total_cost - cost_before, 2),
            stability_penalty=round(stability_pen_best, 2),
            stops_changed_count=len(stops_changed_best),
            stops_changed=stops_changed_best,
            is_feasible=final_val.is_valid,
            message=(
                f"Accepted {chosen_tier.value} with cost {best_solution.total_cost:.2f}"
                if final_val.is_valid
                else "No feasible plan found across all tiers; fallback plan returned"
            ),
        )
        self.audit_log.append(rec)
        return best_solution, rec

    def _tier_1_path_repair(self, solution: Solution, current_time: float) -> Solution:
        """Tier 1: Retain stop sequences and update timeline using router/oracle."""
        rebuilt_routes: list[Route] = []
        depot_loc = to_location(self.problem.depot)

        for r in solution.routes:
            if not r.stop_ids:
                rebuilt_routes.append(r.model_copy())
                continue

            curr_time = max(current_time, self.problem.depot.ready_time)
            prev_loc = depot_loc
            arrival_times: list[float] = []
            route_dist = 0.0

            for sid in r.stop_ids:
                cust = self.problem.get_customer(sid)
                c_loc = to_location(cust)
                if not math.isfinite(curr_time):
                    tt = float("inf")
                    dist = 0.0
                else:
                    tt = self.cost_oracle.travel_time(prev_loc, c_loc, depart_time=curr_time)
                    dist = self.cost_oracle.distance(prev_loc, c_loc)

                route_dist += dist
                arr = curr_time + tt
                arrival_times.append(arr)
                curr_time = (max(arr, cust.ready_time) + cust.service_time) if math.isfinite(arr) else float("inf")
                prev_loc = c_loc

            # Return to depot
            if math.isfinite(curr_time):
                route_dist += self.cost_oracle.distance(prev_loc, depot_loc)
                tt_depot = self.cost_oracle.travel_time(prev_loc, depot_loc, depart_time=curr_time)
                total_duration = (curr_time + tt_depot) - max(current_time, self.problem.depot.ready_time)
            else:
                total_duration = float("inf")

            rebuilt_routes.append(
                Route(
                    vehicle_id=r.vehicle_id,
                    stop_ids=list(r.stop_ids),
                    arrival_times=arrival_times,
                    load=r.load,
                    distance=round(route_dist, 2),
                    duration=round(total_duration, 2),
                )
            )

        tot_cost = sum(self._calc_route_cost(r) for r in rebuilt_routes)
        return Solution(
            routes=rebuilt_routes,
            total_cost=round(tot_cost, 2),
            is_feasible=True,
            violations={},
            algorithm="Tier1_PathRepair",
            execution_time_sec=0.0,
            seed=self.config.seed,
        )

    def _tier_2_local_repair(
        self,
        solution: Solution,
        frozen: dict[str, list[str]],
        uncommitted: dict[str, list[str]],
        current_time: float,
    ) -> Solution:
        """Tier 2: Relocate and swap operations focused strictly on uncommitted stops."""
        routes_dict: dict[str, list[str]] = {
            r.vehicle_id: list(r.stop_ids) for r in solution.routes
        }

        # Build flat list of uncommitted stops
        uncommitted_stops_list: list[str] = []
        for stops in uncommitted.values():
            uncommitted_stops_list.extend(stops)

        # Try relocating each uncommitted stop into alternative positions / routes
        best_sol = solution
        best_cost = evaluate_solution_under_oracle(solution, self.problem, self.cost_oracle, current_time)[0]

        for sid in uncommitted_stops_list:
            # Locate current vehicle holding sid
            cur_v = next((v for v, r in routes_dict.items() if sid in r), None)
            if cur_v is None:
                continue

            cur_route = routes_dict[cur_v]
            cur_frozen_len = len(frozen.get(cur_v, []))
            if sid not in cur_route:
                continue
            cur_idx = cur_route.index(sid)
            if cur_idx < cur_frozen_len:
                continue  # Committed stop, cannot move

            best_move_dict: dict[str, list[str]] | None = None
            best_move_sol: Solution | None = None
            best_move_cost = best_cost

            # 1. Try Intra-route relocate
            for target_pos in range(cur_frozen_len, len(cur_route)):
                if target_pos == cur_idx:
                    continue
                cand_route = list(cur_route)
                cand_route.remove(sid)
                cand_route.insert(target_pos, sid)

                cand_routes_dict = dict(routes_dict)
                cand_routes_dict[cur_v] = cand_route

                cand_sol = self._build_solution_from_dict(cand_routes_dict, current_time)
                rep = validate_solution(self.problem, cand_sol, cost_oracle=self.cost_oracle)
                if rep.is_valid and cand_sol.total_cost < best_move_cost:
                    best_move_cost = cand_sol.total_cost
                    best_move_sol = cand_sol
                    best_move_dict = cand_routes_dict

            # 2. Try Inter-route relocate to another vehicle
            for tgt_v, tgt_route in routes_dict.items():
                if tgt_v == cur_v:
                    continue
                tgt_frozen_len = len(frozen.get(tgt_v, []))

                for target_pos in range(tgt_frozen_len, len(tgt_route) + 1):
                    cand_src = list(cur_route)
                    cand_src.remove(sid)
                    cand_tgt = list(tgt_route)
                    cand_tgt.insert(target_pos, sid)

                    cand_routes_dict = dict(routes_dict)
                    cand_routes_dict[cur_v] = cand_src
                    cand_routes_dict[tgt_v] = cand_tgt

                    cand_sol = self._build_solution_from_dict(cand_routes_dict, current_time)
                    rep = validate_solution(self.problem, cand_sol, cost_oracle=self.cost_oracle)
                    if rep.is_valid and cand_sol.total_cost < best_move_cost:
                        best_move_cost = cand_sol.total_cost
                        best_move_sol = cand_sol
                        best_move_dict = cand_routes_dict

            if best_move_dict is not None and best_move_sol is not None:
                routes_dict = best_move_dict
                best_cost = best_move_cost
                best_sol = best_move_sol

        return best_sol

    def _tier_3_qpso_warm_start(
        self,
        solution: Solution,
        frozen: dict[str, list[str]],
        uncommitted: dict[str, list[str]],
        current_time: float,
    ) -> Solution:
        """Tier 3: Swarm metaheuristic seeded around previous solution keys with reduced iterations."""
        all_uncommitted_stops: list[str] = []
        for unc in uncommitted.values():
            all_uncommitted_stops.extend(unc)

        if not all_uncommitted_stops:
            return solution

        # Construct sub-problem for uncommitted stops
        uncommitted_customers = [self.problem.get_customer(sid) for sid in all_uncommitted_stops]
        sub_problem = Problem(
            id=f"{self.problem.id}_uncommitted",
            depot=self.problem.depot,
            customers=uncommitted_customers,
            vehicles=self.problem.vehicles,
            coordinate_system=self.problem.coordinate_system,
        )

        n_unc = len(uncommitted_customers)
        # Project previous order to continuous keys
        prev_tour = list(range(1, n_unc + 1))
        old_keys = np.linspace(0.1, 0.9, n_unc)
        seed_keys = project_tour_to_keys(old_keys, prev_tour)

        qpso_config = QPSOConfig(
            num_particles=self.config.tier3_particles,
            max_iters=self.config.tier3_max_iters,
            alpha_max=self.config.tier3_alpha_max,
            alpha_min=self.config.tier3_alpha_min,
            seed=self.config.seed,
            apply_tw_repair=True,
        )

        sub_sol, _ = solve_qpso(
            problem=sub_problem,
            config=qpso_config,
            cost_oracle=self.cost_oracle,
            seed_keys=seed_keys,
            seed_fraction=self.config.tier3_seed_fraction,
        )

        # Re-attach frozen prefix stops to the newly re-routed uncommitted stops
        combined_routes_dict: dict[str, list[str]] = {v_id: list(frz) for v_id, frz in frozen.items()}

        for r in sub_sol.routes:
            if r.vehicle_id in combined_routes_dict:
                combined_routes_dict[r.vehicle_id].extend(r.stop_ids)
            else:
                # Assign to vehicle with smallest load
                min_v = min(combined_routes_dict.keys(), key=lambda v: len(combined_routes_dict[v]))
                combined_routes_dict[min_v].extend(r.stop_ids)

        return self._build_solution_from_dict(combined_routes_dict, current_time)

    def _build_solution_from_dict(
        self,
        routes_dict: dict[str, list[str]],
        current_time: float,
    ) -> Solution:
        """Helper to construct a Solution and compute timelines from a vehicle -> stop_ids mapping."""
        depot_loc = to_location(self.problem.depot)
        routes: list[Route] = []

        for v_id, stop_ids in routes_dict.items():
            if not stop_ids:
                routes.append(
                    Route(
                        vehicle_id=v_id,
                        stop_ids=[],
                        arrival_times=[],
                        load=0.0,
                        distance=0.0,
                        duration=0.0,
                    )
                )
                continue

            curr_time = max(current_time, self.problem.depot.ready_time)
            prev_loc = depot_loc
            arrival_times: list[float] = []
            route_dist = 0.0
            route_load = 0.0

            for sid in stop_ids:
                cust = self.problem.get_customer(sid)
                route_load += cust.demand
                c_loc = to_location(cust)

                if not math.isfinite(curr_time):
                    tt = float("inf")
                    dist = 0.0
                else:
                    tt = self.cost_oracle.travel_time(prev_loc, c_loc, depart_time=curr_time)
                    dist = self.cost_oracle.distance(prev_loc, c_loc)

                route_dist += dist
                arr = curr_time + tt
                arrival_times.append(arr)
                curr_time = (max(arr, cust.ready_time) + cust.service_time) if math.isfinite(arr) else float("inf")
                prev_loc = c_loc

            if math.isfinite(curr_time):
                route_dist += self.cost_oracle.distance(prev_loc, depot_loc)
                tt_depot = self.cost_oracle.travel_time(prev_loc, depot_loc, depart_time=curr_time)
                total_duration = (curr_time + tt_depot) - max(current_time, self.problem.depot.ready_time)
            else:
                total_duration = float("inf")

            routes.append(
                Route(
                    vehicle_id=v_id,
                    stop_ids=list(stop_ids),
                    arrival_times=arrival_times,
                    load=route_load,
                    distance=round(route_dist, 2),
                    duration=round(total_duration, 2),
                )
            )

        total_cost = sum(self._calc_route_cost(r) for r in routes)
        return Solution(
            routes=routes,
            total_cost=round(total_cost, 2),
            is_feasible=True,
            violations={},
            algorithm="DynamicReoptimizer",
            execution_time_sec=0.0,
            seed=self.config.seed,
        )


def full_restart_baseline(
    problem: Problem,
    current_solution: Solution,
    cost_oracle: CostOracle,
    current_time: float = 0.0,
    commitment_horizon: float = 300.0,
    seed: int = 42,
    max_iters: int = 150,
    particles: int = 35,
) -> tuple[Solution, float]:
    """Execute a full-restart baseline re-plan for uncommitted stops from cold scratch.

    Used as the scientific benchmark comparator against the tiered re-optimizer.

    Args:
        problem: Complete problem instance.
        current_solution: Current active solution.
        cost_oracle: CostOracle representing new conditions.
        current_time: Current simulation timestamp.
        commitment_horizon: Commitment window for freezing.
        seed: Random seed.
        max_iters: Iteration budget for cold start (standard 150).
        particles: Particle swarm size (standard 35).

    Returns:
        (restarted_solution, wall_clock_time_ms)
    """
    start = time.perf_counter()

    frozen: dict[str, list[str]] = {}
    uncommitted: list[str] = []

    for r in current_solution.routes:
        frz, unc = partition_stops_by_commitment(r, current_time, commitment_horizon, problem)
        frozen[r.vehicle_id] = frz
        uncommitted.extend(unc)

    if not uncommitted:
        elapsed = (time.perf_counter() - start) * 1000.0
        return current_solution, elapsed

    uncommitted_customers = [problem.get_customer(sid) for sid in uncommitted]
    sub_problem = Problem(
        id=f"{problem.id}_restart",
        depot=problem.depot,
        customers=uncommitted_customers,
        vehicles=problem.vehicles,
        coordinate_system=problem.coordinate_system,
    )

    cold_config = QPSOConfig(
        num_particles=particles,
        max_iters=max_iters,
        seed=seed,
        alpha_max=1.0,
        alpha_min=0.5,
        apply_tw_repair=True,
    )

    sub_sol, _ = solve_qpso(
        problem=sub_problem,
        config=cold_config,
        cost_oracle=cost_oracle,
    )

    # Stitch frozen prefixes with cold-started suffixes
    routes_dict: dict[str, list[str]] = {v_id: list(frz) for v_id, frz in frozen.items()}
    for r in sub_sol.routes:
        if r.vehicle_id in routes_dict:
            routes_dict[r.vehicle_id].extend(r.stop_ids)
        else:
            min_v = min(routes_dict.keys(), key=lambda v: len(routes_dict[v]))
            routes_dict[min_v].extend(r.stop_ids)

    reoptimizer = DynamicReoptimizer(problem, cost_oracle)
    final_sol = reoptimizer._build_solution_from_dict(routes_dict, current_time)
    elapsed = (time.perf_counter() - start) * 1000.0
    return final_sol, elapsed
