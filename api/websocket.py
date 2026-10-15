"""Real-time WebSocket connection manager for Route.it API.

Maintains subscriber pools per problem_id and broadcasts live solver telemetry
(iterations, best cost) and dynamic re-optimization updates.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages active WebSocket connections grouped by problem_id."""

    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Capture the running FastAPI event loop for sync-to-async scheduling."""
        self._loop = loop

    async def connect(self, problem_id: str, websocket: WebSocket) -> None:
        """Accept incoming connection and subscribe to problem updates."""
        await websocket.accept()
        self._connections.setdefault(problem_id, []).append(websocket)
        logger.debug(f"[WS] Client connected to problem {problem_id} (active: {len(self._connections[problem_id])})")

    def disconnect(self, problem_id: str, websocket: WebSocket) -> None:
        """Unsubscribe connection from problem updates."""
        if problem_id in self._connections:
            if websocket in self._connections[problem_id]:
                self._connections[problem_id].remove(websocket)
            if not self._connections[problem_id]:
                del self._connections[problem_id]
        logger.debug(f"[WS] Client disconnected from problem {problem_id}")

    async def broadcast(self, problem_id: str, message: dict[str, Any]) -> None:
        """Broadcast JSON payload to all active clients subscribed to problem_id."""
        subscribers = list(self._connections.get(problem_id, []))
        if not subscribers:
            return

        dead_connections: list[WebSocket] = []
        for ws in subscribers:
            try:
                await ws.send_json(message)
            except Exception as e:
                logger.warning(f"[WS] Failed sending to client on problem {problem_id}: {e}")
                dead_connections.append(ws)

        for ws in dead_connections:
            self.disconnect(problem_id, ws)

    def broadcast_sync(self, problem_id: str, message: dict[str, Any]) -> None:
        """Thread-safe synchronization broadcast helper for background workers."""
        if self._loop is not None and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self.broadcast(problem_id, message), self._loop)
        else:
            try:
                loop = asyncio.get_running_loop()
                asyncio.run_coroutine_threadsafe(self.broadcast(problem_id, message), loop)
            except RuntimeError:
                pass

    def get_total_connections_count(self) -> int:
        """Return total active WebSocket clients across all problems."""
        return sum(len(conns) for conns in self._connections.values())


# Global manager instance
manager = ConnectionManager()
