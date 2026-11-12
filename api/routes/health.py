"""Health check and service status endpoints."""

from __future__ import annotations

import os
import time
import urllib.request
from fastapi import APIRouter, Depends

from api import __version__
from api.models import HealthResponse
from api.store import ProblemStore, get_store
from api.websocket import manager

router = APIRouter(tags=["Health"])

START_TIME = time.time()


_VALHALLA_HEALTH_CACHE: tuple[float, bool] = (0.0, False)


def _check_valhalla_connection(url: str | None = None) -> bool:
    """Non-blocking cached check of Valhalla health (cached for 25s for high throughput)."""
    global _VALHALLA_HEALTH_CACHE
    now = time.time()
    last_time, last_status = _VALHALLA_HEALTH_CACHE
    if now - last_time < 25.0:
        return last_status

    if not url:
        base = os.environ.get("VALHALLA_URL", "http://127.0.0.1:8002").rstrip("/")
        url = f"{base}/status"

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Route.it-SIH2026", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            ok = resp.status == 200
            _VALHALLA_HEALTH_CACHE = (now, ok)
            return ok
    except Exception:
        _VALHALLA_HEALTH_CACHE = (now, False)
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
