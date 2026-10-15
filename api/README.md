# Route.it Backend API & WebSocket Service

High-performance REST API and real-time WebSocket service bridging the classical Quantum-behaved Particle Swarm Optimization (QPSO) engine, the Valhalla road routing engine, the dynamic traffic event system, and the React + MapLibre GL frontend dashboard.

---

## 1. Interactive OpenAPI Documentation

When the API service is running locally, interactive API documentation is auto-generated at:
- **Swagger UI (Interactive API Explorer)**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc (API Specification Reference)**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **OpenAPI Schema (JSON)**: [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json)

---

## 2. Quickstart

### Starting the API Server
```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```
The server will start on port `8000` with hot-reloading enabled.

---

## 3. API Endpoints Overview

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/health` | Service uptime, readiness, and connectivity health check. |
| `POST` | `/problems` | Create and store a new CVRPTW problem instance. |
| `GET` | `/problems` | List all stored problem instances with bounding boxes. |
| `GET` | `/problems/{id}` | Retrieve problem specifications and stop coordinates. |
| `DELETE`| `/problems/{id}` | Delete a problem and all associated solutions/jobs. |
| `POST` | `/problems/{id}/solve` | Launch asynchronous QPSO optimization job. |
| `GET` | `/problems/{id}/jobs/{job_id}` | Query status and progress of an optimization job. |
| `GET` | `/problems/{id}/solution` | Fetch active solution, ETAs, and MapLibre GeoJSON. |
| `POST` | `/problems/{id}/events` | Inject traffic incident and trigger tiered re-optimizer. |
| `GET` | `/problems/{id}/events` | Retrieve chronological audit log of all re-optimizations. |
| `WS` | `/ws/problems/{id}` | Real-time WebSocket stream for solve progress and re-optimization. |

---

## 4. End-to-End Workflow & cURL Examples

### 4.1 Health Check
```bash
curl -X GET "http://localhost:8000/health"
```

### 4.2 Create a Problem Instance
```bash
curl -X POST "http://localhost:8000/problems" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "vadodara_demo",
    "depot": {
      "id": "depot",
      "lat": 22.3072,
      "lon": 73.1812,
      "ready_time": 0.0,
      "due_time": 36000.0,
      "service_time": 0.0
    },
    "customers": [
      {
        "id": "cust_1",
        "lat": 22.3120,
        "lon": 73.1750,
        "demand": 15.0,
        "ready_time": 600.0,
        "due_time": 3600.0,
        "service_time": 180.0,
        "priority": 2
      },
      {
        "id": "cust_2",
        "lat": 22.2980,
        "lon": 73.1920,
        "demand": 20.0,
        "ready_time": 1200.0,
        "due_time": 4800.0,
        "service_time": 240.0,
        "priority": 1
      }
    ]
  }'
```

### 4.3 Trigger Asynchronous Solving
```bash
curl -X POST "http://localhost:8000/problems/vadodara_demo/solve" \
  -H "Content-Type: application/json" \
  -d '{
    "num_particles": 25,
    "max_iters": 50,
    "cost_oracle_type": "euclidean",
    "apply_tw_repair": true,
    "seed": 42
  }'
```
Response:
```json
{
  "job_id": "job_a1b2c3d4",
  "problem_id": "vadodara_demo",
  "status": "pending",
  "progress_iteration": 0,
  "max_iters": 50,
  "current_cost": 0.0,
  "created_at": 1712180000.0
}
```

### 4.4 Retrieve Solution & MapLibre GeoJSON
```bash
curl -X GET "http://localhost:8000/problems/vadodara_demo/solution"
```
Response contains:
- `routes`: Vehicle routes, stop sequences, arrival times, durations.
- `geojson`: RFC 7946 GeoJSON `FeatureCollection` with styled LineStrings and Point markers ready for MapLibre GL `map.addSource('routes', ...)` rendering.

### 4.5 Inject Dynamic Traffic Event
```bash
curl -X POST "http://localhost:8000/problems/vadodara_demo/events" \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "edge_congestion",
    "trigger_time": 300.0,
    "duration": 1800.0,
    "origin_id": "depot",
    "dest_id": "cust_1",
    "multiplier": 2.5,
    "description": "Heavy traffic jam on RC Dutt Road"
  }'
```
Response:
```json
{
  "event_id": "evt_edge_congestion_1712180000",
  "tier_selected": "TIER_1_PATH_REPAIR",
  "wall_clock_time_ms": 1.84,
  "cost_before": 1240.5,
  "cost_after": 1310.2,
  "delta_f": 69.7,
  "stability_penalty": 0.0,
  "stops_changed_count": 0,
  "stops_changed": [],
  "is_feasible": true,
  "message": "Accepted Tier 1 Path Repair (preserved stop sequence)",
  "solution": { ... }
}
```

---

## 5. WebSocket Telemetry Protocol (`/ws/problems/{id}`)

Connect to `ws://localhost:8000/ws/problems/{id}` to receive real-time streams:

### 1. Solve Progress Broadcast
```json
{
  "type": "solve_progress",
  "problem_id": "vadodara_demo",
  "job_id": "job_a1b2c3d4",
  "iteration": 35,
  "max_iters": 50,
  "gbest_cost": 1240.5,
  "elapsed_ms": 182.4
}
```

### 2. Solve Completed Broadcast
```json
{
  "type": "solve_completed",
  "problem_id": "vadodara_demo",
  "job_id": "job_a1b2c3d4",
  "solution_cost": 1240.5,
  "is_feasible": true,
  "routes_count": 2,
  "execution_time_sec": 0.245
}
```

### 3. Dynamic Re-optimization Broadcast
```json
{
  "type": "reoptimization_update",
  "problem_id": "vadodara_demo",
  "event_id": "evt_road_block_01",
  "tier_selected": "TIER_2_LOCAL_REPAIR",
  "wall_clock_time_ms": 48.2,
  "cost_before": 1240.5,
  "cost_after": 1285.0,
  "delta_f": 44.5,
  "stability_penalty": 100.0,
  "stops_changed_count": 1,
  "stops_changed": ["cust_2"],
  "is_feasible": true,
  "message": "Accepted Tier 2 Local Repair (relocate/swap on affected routes)"
}
```
