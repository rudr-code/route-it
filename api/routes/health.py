"""Health check and service status endpoints."""

from __future__ import annotations

import time
import urllib.request
from fastapi import APIRouter, Depends

from api import __version__
from api.models import HealthResponse
from api.store import ProblemStore, get_store
from api.websocket import manager

router = APIRouter(tags=["Health"])

START_TIME = time.time()


def _check_valhalla_connection(url: str = "http://localhost:8002/status") -> bool:
    """Non-blocking check of Valhalla Docker container health."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "RouteIt-HealthCheck"})
        with urllib.request.urlopen(req, timeout=0.4) as resp:
            return resp.status == 200
    except Exception:
        return False


@router.get("/health", response_model=HealthResponse, summary="System Health & Readiness")
def get_health(store: ProblemStore = Depends(get_store)) -> HealthResponse:
    """Check Route.it API operational health, uptime, and connected services."""
    uptime = time.time() - START_TIME
    valhalla_ok = _check_valhalla_connection()
    problems_count = len(store.list_problems())
    ws_count = manager.get_total_connections_count()

    return HealthResponse(
        status="healthy",
        version=__version__,
        uptime_seconds=round(uptime, 2),
        valhalla_connected=valhalla_ok,
        active_problems_count=problems_count,
        active_ws_connections=ws_count,
    )
