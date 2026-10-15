"""Health check utility for local Valhalla Docker instance.

Verifies:
1. HTTP connectivity and status check via GET /status
2. Live route calculation via POST /route in Vadodara
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any, Sequence
import urllib.error
import urllib.request


def check_valhalla_health(base_url: str = "http://localhost:8002", timeout: float = 5.0) -> dict[str, Any]:
    """Test connectivity, status, and route query against a Valhalla endpoint.

    Args:
        base_url: Base HTTP URL of the Valhalla service.
        timeout: Socket timeout in seconds.

    Returns:
        Dictionary containing health status, version, and latency metrics.
    """
    clean_url = base_url.rstrip("/")
    status_url = f"{clean_url}/status"
    route_url = f"{clean_url}/route"

    report: dict[str, Any] = {
        "url": clean_url,
        "healthy": False,
        "status_code": None,
        "version": None,
        "tileset_last_modified": None,
        "status_latency_ms": None,
        "route_latency_ms": None,
        "sample_route_km": None,
        "sample_route_sec": None,
        "error": None,
    }

    # 1. Check GET /status
    try:
        t0 = time.perf_counter()
        req = urllib.request.Request(status_url, headers={"User-Agent": "RouteIt-Healthcheck"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            status_latency = (time.perf_counter() - t0) * 1000.0
            report["status_code"] = response.status
            report["status_latency_ms"] = round(status_latency, 2)
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                report["version"] = data.get("version")
                report["tileset_last_modified"] = data.get("tileset_last_modified")
            else:
                report["error"] = f"GET /status returned HTTP {response.status}"
                return report
    except Exception as exc:  # noqa: BLE001
        report["error"] = f"Failed to connect to {status_url}: {exc}"
        return report

    # 2. Check POST /route with Vadodara coordinates (Junction to Sayaji Baug)
    route_payload = {
        "locations": [
            {"lat": 22.3108, "lon": 73.1811, "type": "break"},
            {"lat": 22.3129, "lon": 73.1906, "type": "break"},
        ],
        "costing": "auto",
        "directions_options": {"units": "kilometers"},
    }

    try:
        t0 = time.perf_counter()
        payload_bytes = json.dumps(route_payload).encode("utf-8")
        req = urllib.request.Request(
            route_url,
            data=payload_bytes,
            headers={"Content-Type": "application/json", "User-Agent": "RouteIt-Healthcheck"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            route_latency = (time.perf_counter() - t0) * 1000.0
            report["route_latency_ms"] = round(route_latency, 2)
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                trip = data.get("trip", {})
                summary = trip.get("summary", {})
                report["sample_route_km"] = summary.get("length")
                report["sample_route_sec"] = summary.get("time")
                report["healthy"] = True
            else:
                report["error"] = f"POST /route returned HTTP {response.status}"
    except Exception as exc:  # noqa: BLE001
        report["error"] = f"Failed to query {route_url}: {exc}"

    return report


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Verify health and response latency of local Valhalla Docker instance."
    )
    parser.add_argument(
        "--url",
        "-u",
        type=str,
        default="http://localhost:8002",
        help="Valhalla service URL (default: http://localhost:8002)",
    )
    parser.add_argument(
        "--timeout",
        "-t",
        type=float,
        default=5.0,
        help="Request timeout in seconds (default: 5.0)",
    )
    args = parser.parse_args(argv)

    print(f"Checking Valhalla health at {args.url} (timeout: {args.timeout}s)...")
    res = check_valhalla_health(args.url, timeout=args.timeout)

    print("-" * 50)
    if res["healthy"]:
        print("Status:           HEALTHY (ONLINE)")
        print(f"Version:          {res['version']}")
        print(f"Status Latency:   {res['status_latency_ms']} ms")
        print(f"Route Latency:    {res['route_latency_ms']} ms")
        print(f"Sample Route:     {res['sample_route_km']} km in {res['sample_route_sec']} s")
        print("-" * 50)
        return 0
    else:
        print("Status:           UNHEALTHY (OFFLINE / ERROR)")
        print(f"Error:            {res['error']}")
        print("-" * 50)
        print("Hint: Ensure the Valhalla container is started via 'docker compose up -d' in /routing")
        print("      and vadodara.osm.pbf is placed in routing/custom_files/.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
