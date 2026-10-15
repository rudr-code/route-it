"""Dynamic traffic incident injection and re-optimization endpoints."""

from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, HTTPException, status

from api.geojson import solution_to_geojson
from api.models import (
    DynamicEventCreate,
    EventInjectResponse,
    SolutionResponse,
)
from api.store import ProblemStore, get_store
from api.websocket import manager
from dynamic.reoptimizer import (
    DynamicReoptimizer,
    ReoptimizationRecord,
    ReoptimizerConfig,
)
from routing.cost_oracle import (
    EuclideanOracle,
    SimulatedEventAdapter,
    TimeOfDayProfileAdapter,
)

router = APIRouter(prefix="/problems", tags=["Dynamic Events & Re-optimization"])
logger = logging.getLogger(__name__)


@router.post("/{problem_id}/events", response_model=EventInjectResponse, summary="Inject Traffic Event & Trigger Re-optimizer")
def inject_event(
    problem_id: str,
    event_req: DynamicEventCreate,
    store: ProblemStore = Depends(get_store),
) -> EventInjectResponse:
    """Inject a dynamic traffic incident (congestion, blockage, delay) into an active problem.

    Executes tiered dynamic re-optimization:
    - Tier 1: Path Repair (preserves stop sequence, re-computes timeline)
    - Tier 2: Local Repair (relocate/swap affected uncommitted stops)
    - Tier 3: QPSO Warm Start (swarm re-seeded around previous keys)
    Broadcasts real-time telemetry to all subscribed WebSocket clients.
    """
    problem = store.get_problem(problem_id)
    if problem is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Problem '{problem_id}' not found",
        )

    current_solution = store.get_solution(problem_id)
    if current_solution is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Problem '{problem_id}' has not been solved yet. Please trigger /solve before injecting events.",
        )

    # 1. Convert to domain event
    domain_event = event_req.to_domain_event()

    # 2. Retrieve or initialize CostOracle with SimulatedEventAdapter
    oracle = store.get_oracle(problem_id)
    if oracle is None or not isinstance(oracle.traffic_adapter, SimulatedEventAdapter):
        traffic_adapter = SimulatedEventAdapter(
            base_adapter=TimeOfDayProfileAdapter({h: 1.0 for h in range(24)})
        )
        oracle = EuclideanOracle(base_speed_mps=1.0, traffic_adapter=traffic_adapter)
        store.save_oracle(problem_id, oracle)

    # 3. Apply event incidents to traffic adapter
    if hasattr(domain_event, "to_simulated_incidents"):
        for inc in domain_event.to_simulated_incidents():
            oracle.traffic_adapter.add_incident(inc)

    # 4. Execute Tiered Dynamic Re-optimizer
    reopt_config = ReoptimizerConfig(
        theta=0.01,
        theta_absolute=2.0,
        commitment_horizon_seconds=60.0,
        seed=42,
    )
    reoptimizer = DynamicReoptimizer(problem, cost_oracle=oracle, config=reopt_config)

    reopt_solution, record = reoptimizer.reoptimize(
        current_solution=current_solution,
        current_time=event_req.trigger_time,
        event=domain_event,
    )

    # 5. Persist updated solution & record
    store.save_solution(problem_id, reopt_solution)
    store.add_event_record(problem_id, record)

    # 6. Broadcast reoptimization update to WebSocket subscribers
    manager.broadcast_sync(
        problem_id,
        {
            "type": "reoptimization_update",
            "problem_id": problem_id,
            "event_id": record.event_id,
            "tier_selected": record.tier_selected.value,
            "wall_clock_time_ms": record.wall_clock_time_ms,
            "cost_before": record.cost_before,
            "cost_after": record.cost_after,
            "delta_f": record.delta_f,
            "stability_penalty": record.stability_penalty,
            "stops_changed_count": record.stops_changed_count,
            "stops_changed": record.stops_changed,
            "is_feasible": record.is_feasible,
            "message": record.message,
        },
    )

    # 7. Generate updated GeoJSON payload
    geojson_data = solution_to_geojson(
        problem, reopt_solution, cost_oracle=oracle, current_time=event_req.trigger_time
    )
    solution_resp = SolutionResponse(
        problem_id=problem_id,
        total_cost=round(reopt_solution.total_cost, 2),
        is_feasible=reopt_solution.is_feasible,
        violations=reopt_solution.violations,
        num_routes=len(reopt_solution.routes),
        routes=reopt_solution.routes,
        geojson=geojson_data,
        algorithm=reopt_solution.algorithm,
        execution_time_sec=round(reopt_solution.execution_time_sec, 3),
    )

    return EventInjectResponse(
        event_id=record.event_id,
        tier_selected=record.tier_selected.value,
        wall_clock_time_ms=record.wall_clock_time_ms,
        cost_before=record.cost_before,
        cost_after=record.cost_after,
        delta_f=record.delta_f,
        stability_penalty=record.stability_penalty,
        stops_changed_count=record.stops_changed_count,
        stops_changed=record.stops_changed,
        is_feasible=record.is_feasible,
        message=record.message,
        solution=solution_resp,
    )


@router.get("/{problem_id}/events", response_model=list[dict], summary="Get Event Audit History")
def get_event_audit_history(
    problem_id: str,
    store: ProblemStore = Depends(get_store),
) -> list[dict]:
    """Retrieve the chronological audit history of all events and re-optimizations for a problem."""
    problem = store.get_problem(problem_id)
    if problem is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Problem '{problem_id}' not found",
        )
    records = store.get_event_records(problem_id)
    return [r.model_dump() for r in records]
