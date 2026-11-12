"""Comprehensive Local Deployment Verification Suite for Route.it.
Tests unified production server on a custom PORT environment variable.
Verifies:
1. /health endpoint
2. GET / (SPA index.html loads)
3. Deep-link refresh (e.g. /admin, /driver) via SPA fallback
4. API delivery locations endpoints (list, add, delete)
5. QPSO batch optimize call with 5 customer delivery stops
6. WebSocket telemetry connection (handshake + ping/pong)
"""

import os
import sys
import time
import json
import socket
import threading
import urllib.request
import urllib.error

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

TEST_PORT = int(os.environ.get("VERIFY_PORT", "8050"))
BASE_URL = f"http://127.0.0.1:{TEST_PORT}"
RESULTS = {}

def log_test(name: str, passed: bool, detail: str = ""):
    RESULTS[name] = {"passed": passed, "detail": detail}
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] {name} - {detail}")

def http_get(path: str):
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "RouteIt-Verifier/1.0"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        return resp.status, resp.read().decode("utf-8")

def http_post(path: str, data: dict, timeout: int = 25):
    url = f"{BASE_URL}{path}"
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "RouteIt-Verifier/1.0"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))

def http_delete(path: str):
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "RouteIt-Verifier/1.0"},
        method="DELETE"
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return resp.status, resp.read().decode("utf-8")

def run_tests():
    print(f"\n--- Starting Deployment Verification on port {TEST_PORT} ---")

    # 1. Health Endpoint
    try:
        status, body = http_get("/health")
        data = json.loads(body)
        if status == 200 and data.get("status") == "healthy":
            log_test("1. /health endpoint", True, f"Status 200, uptime={data.get('uptime_seconds')}s, version={data.get('version')}")
        else:
            log_test("1. /health endpoint", False, f"Unexpected body: {body}")
    except Exception as e:
        log_test("1. /health endpoint", False, str(e))

    # 2. GET / (SPA index loads)
    try:
        status, body = http_get("/")
        if status == 200 and ("Route.it" in body or "<div id=\"root\">" in body):
            log_test("2. GET / (SPA Root)", True, "Status 200, HTML contains Route.it SPA bundle root")
        else:
            log_test("2. GET / (SPA Root)", False, f"Status {status}, preview: {body[:120]}")
    except Exception as e:
        log_test("2. GET / (SPA Root)", False, str(e))

    # 3. Deep-link refresh (e.g. /admin or /portal) via SPA fallback
    try:
        status, body = http_get("/admin/delivery-locations")
        if status == 200 and ("<div id=\"root\">" in body or "Route.it" in body):
            log_test("3. Deep-link SPA Fallback (/admin/delivery-locations)", True, "Status 200, successfully serves index.html for client route")
        else:
            log_test("3. Deep-link SPA Fallback (/admin/delivery-locations)", False, f"Status {status}, preview: {body[:120]}")
    except Exception as e:
        log_test("3. Deep-link SPA Fallback (/admin/delivery-locations)", False, str(e))

    # 4. API delivery locations endpoints (list, add, delete)
    created_id = None
    try:
        # 4a. List locations
        status, body = http_get("/delivery/locations")
        locs = json.loads(body)
        if status == 200 and isinstance(locs, list) and len(locs) >= 6:
            log_test("4a. GET /delivery/locations (List & Auto-seed)", True, f"Status 200, retrieved {len(locs)} stops (auto-seeded data verified)")
        else:
            log_test("4a. GET /delivery/locations (List & Auto-seed)", False, f"Status {status}, count={len(locs) if isinstance(locs, list) else 0}")

        # 4b. Add location
        new_stop = {
            "customer_name": "Test Deployment Store",
            "customer_phone": "+91-9988776655",
            "customer_email": "test@deploy.routeit.in",
            "address": "Opposite Railway Station, Sayajigunj, Vadodara",
            "lat": 22.3115,
            "lon": 73.1802,
            "demand": 12.0,
            "priority": 2,
            "ready_time": 28800.0,
            "due_time": 50400.0,
            "service_time": 600.0
        }
        status, res = http_post("/delivery/locations", new_stop)
        if status == 201 and "id" in res:
            created_id = res["id"]
            log_test("4b. POST /delivery/locations (Create stop)", True, f"Status 201, created {created_id} at ({res['lat']}, {res['lon']})")
        else:
            log_test("4b. POST /delivery/locations (Create stop)", False, f"Status {status}, res={res}")

        # 4c. Delete location
        if created_id:
            del_status, _ = http_delete(f"/delivery/locations/{created_id}")
            if del_status in (200, 204):
                log_test("4c. DELETE /delivery/locations (Remove stop)", True, f"Status {del_status}, successfully deleted {created_id}")
            else:
                log_test("4c. DELETE /delivery/locations (Remove stop)", False, f"Status {del_status}")
    except Exception as e:
        log_test("4. API Delivery Locations CRUD", False, str(e))

    # 5. QPSO Batch Optimize with 5 stops
    try:
        # Fetch current locations and vehicles
        _, locs_body = http_get("/delivery/locations")
        _, vehs_body = http_get("/delivery/vehicles")
        locs = json.loads(locs_body)
        vehs = json.loads(vehs_body)

        target_loc_ids = [l["id"] for l in locs[:5]]
        target_veh_ids = [v["id"] for v in vehs[:2]]

        opt_payload = {
            "name": "Local Verification Wave",
            "location_ids": target_loc_ids,
            "vehicle_ids": target_veh_ids,
            "num_particles": 10,
            "max_iters": 15,
            "seed": 42,
        }
        status, opt_res = http_post("/delivery/batches/optimize", opt_payload, timeout=90)
        if status in (200, 201) and "batch_id" in opt_res and len(opt_res.get("dispatch_jobs", [])) > 0:
            dist_km = opt_res.get("total_distance_m", 0) / 1000.0
            log_test(
                "5. QPSO Batch Optimization (5 stops)",
                True,
                f"Batch {opt_res['batch_id']}: Created {len(opt_res['dispatch_jobs'])} jobs, distance={dist_km:.2f} km, stops={opt_res.get('num_stops')}"
            )
        else:
            log_test("5. QPSO Batch Optimization (5 stops)", False, f"Status {status}, res={opt_res}")
    except Exception as e:
        log_test("5. QPSO Batch Optimization (5 stops)", False, str(e))

    # 6. WebSocket Connection Test
    try:
        import asyncio
        import websockets

        async def test_ws():
            ws_url = f"ws://127.0.0.1:{TEST_PORT}/ws/problems/test_prob_01"
            async with websockets.connect(ws_url, close_timeout=3) as ws:
                # Wait for welcome message
                raw_welcome = await asyncio.wait_for(ws.recv(), timeout=3)
                welcome = json.loads(raw_welcome)
                if welcome.get("type") != "connection_established":
                    return False, f"Unexpected welcome: {welcome}"

                # Send ping
                await ws.send("ping")
                raw_pong = await asyncio.wait_for(ws.recv(), timeout=3)
                pong = json.loads(raw_pong)
                if pong.get("type") != "pong":
                    return False, f"Unexpected pong: {pong}"

                return True, "Handshake established & ping/pong verified over WebSocket"

        ws_ok, ws_detail = asyncio.run(test_ws())
        log_test("6. WebSocket Telemetry Stream (/ws/problems/{id})", ws_ok, ws_detail)
    except Exception as e:
        log_test("6. WebSocket Telemetry Stream (/ws/problems/{id})", False, str(e))

    print("\n--- Summary ---")
    all_passed = all(r["passed"] for r in RESULTS.values())
    print(f"Overall Result: {'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}\n")
    return all_passed

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
