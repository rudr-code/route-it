"""WebSocket endpoint for real-time telemetry and dynamic re-optimization streaming."""

from __future__ import annotations

import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.websocket import manager

router = APIRouter(tags=["WebSocket Stream"])
logger = logging.getLogger(__name__)


@router.websocket("/ws/problems/{problem_id}")
async def websocket_problem_stream(websocket: WebSocket, problem_id: str) -> None:
    """Stream live solver iteration progress and real-time re-optimization telemetry.

    Clients connect to `/ws/problems/{problem_id}` and receive:
    - `solve_progress`: iteration, gbest_cost, elapsed_ms
    - `solve_completed`: final cost, feasibility, routes count
    - `reoptimization_update`: tier used, wall-clock time, cost delta, changed stops
    """
    await manager.connect(problem_id, websocket)

    # Handshake welcome packet
    await websocket.send_json(
        {
            "type": "connection_established",
            "problem_id": problem_id,
            "message": "Connected to Route.it live telemetry stream",
        }
    )

    try:
        while True:
            # Keepalive / ping-pong handling from client
            data = await websocket.receive_text()
            if data.lower() == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        manager.disconnect(problem_id, websocket)
        logger.debug(f"[WS] Disconnected: problem={problem_id}")
    except Exception as exc:
        manager.disconnect(problem_id, websocket)
        logger.warning(f"[WS] Connection closed with error: {exc}")
