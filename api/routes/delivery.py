from __future__ import annotations
import json, time
from typing import Any, Literal
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from api.database import ALLOWED_TRANSITIONS, DeliveryDatabase, get_db
from api.geojson import ROUTE_PALETTE, solution_to_geojson
from api.models import DynamicEventCreate
from api.security import (
    create_access_token,
    decrypt_customer_otp_for_portal,
    generate_tracking_token,
    get_current_user,
    hash_password,
    verify_password,
)
from api.store import ProblemStore, get_store
from api.websocket import manager
from dynamic.reoptimizer import DynamicReoptimizer, ReoptimizerConfig
from routing.cost_oracle import EuclideanOracle, SimulatedEventAdapter, TimeOfDayProfileAdapter
from solver.cost import BusinessCostConfig, compute_cost_breakdown
from solver.models import Customer, Depot, Problem, Vehicle
from solver.partial import solve_partial_plan
from solver.qpso import QPSOConfig, solve_qpso

router = APIRouter(prefix="/delivery", tags=["Delivery Management System"])

VADODARA_HUB = Depot(
    id="depot",
    name="Vadodara Central Distribution Hub (Sayajigunj)",
    lat=22.3072,
    lon=73.1812,
    ready_time=25200.0,
    due_time=64800.0,
    service_time=0.0,
)

class LoginRequest(BaseModel):
    username: str
    password: str

class RegisterDriverRequest(BaseModel):
    username: str
    password: str = "driver123"
    full_name: str
    phone: str
    license_number: str
    assigned_vehicle_id: str | None = None

class LocationCreateRequest(BaseModel):
    customer_name: str
    customer_phone: str
    customer_email: str = ""
    address: str
    lat: float
    lon: float
    demand: float = Field(..., ge=0.1)
    priority: int = Field(1, ge=1, le=5)
    ready_time: float = 28800.0
    due_time: float = 54000.0
    service_time: float = 600.0
    delivery_instructions: str = ""
    time_window_type: Literal["hard", "soft"] = "hard"

class VehicleCreateRequest(BaseModel):
    id: str | None = None
    registration_number: str
    name: str
    capacity: float = Field(..., gt=0.0)
    status: Literal["AVAILABLE", "IN_USE", "MAINTENANCE"] = "AVAILABLE"
    assigned_driver_id: str | None = None
    cost_per_km: float = 15.0
    fixed_cost: float = 250.0

class BatchCreateOptimizeRequest(BaseModel):
    name: str = "Vadodara Morning Wave"
    location_ids: list[str] = Field(..., min_length=1)
    vehicle_ids: list[str] = Field(..., min_length=1)
    num_particles: int = Field(25, ge=5, le=150)
    max_iters: int = Field(50, ge=5, le=500)
    seed: int = 42
    planning_mode: Literal["complete", "partial"] = "complete"
    optimization_profile: Literal["cost_focused", "balanced", "driver_productivity"] = "cost_focused"
    fleet_mode: Literal["auto", "target"] = "auto"
    target_fleet_size: int | None = None
    depot_return: bool = True
    cost_per_km: float = 8.0
    cost_per_hour: float = 100.0
    vehicle_activation_cost: float = 300.0

class AssignDriverRequest(BaseModel):
    driver_id: str

class DriverProgressRequest(BaseModel):
    status: Literal["IN_TRANSIT", "ARRIVED"]
    current_lat: float | None = None
    current_lon: float | None = None

class OTPVerifyRequest(BaseModel):
    otp_code: str = Field(..., min_length=6, max_length=6)
    driver_id: str | None = None

class FailedDeliveryRequest(BaseModel):
    reason: str = Field(..., min_length=3)
    driver_id: str | None = None

@router.post("/auth/login")
def login(req: LoginRequest, db: DeliveryDatabase = Depends(get_db)) -> dict[str, Any]:
    cur = db._conn.cursor()
    cur.execute("SELECT * FROM users WHERE username = ?", (req.username.strip(),))
    user = cur.fetchone()
    if user is None or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    driver_id = None
    driver_profile = None
    if user["role"] == "DRIVER":
        cur.execute("SELECT * FROM drivers WHERE user_id = ?", (user["id"],))
        drv = cur.fetchone()
        if drv:
            driver_id = drv["id"]
            driver_profile = dict(drv)

    token = create_access_token(user_id=user["id"], username=user["username"], role=user["role"], driver_id=driver_id)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"],
            "full_name": user["full_name"],
            "phone": user["phone"],
            "driver_id": driver_id,
            "driver_profile": driver_profile,
        },
    }

@router.get("/auth/me")
def get_me(user: dict[str, Any] = Depends(get_current_user), db: DeliveryDatabase = Depends(get_db)) -> dict[str, Any]:
    cur = db._conn.cursor()
    cur.execute("SELECT id, username, role, full_name, phone, email FROM users WHERE id = ?", (user["sub"],))
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    res = dict(row)
    if user.get("driver_id"):
        cur.execute("SELECT * FROM drivers WHERE id = ?", (user["driver_id"],))
        drv = cur.fetchone()
        res["driver_profile"] = dict(drv) if drv else None
    return res

@router.get("/admin/overview")
def get_admin_overview(db: DeliveryDatabase = Depends(get_db)) -> dict[str, Any]:
    cur = db._conn.cursor()
    cur.execute("SELECT COUNT(*) as c FROM delivery_batches")
    total_batches = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) as c FROM deliveries")
    total_deliveries = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) as c FROM deliveries WHERE status IN ('CREATED', 'OPTIMIZED', 'PENDING_DISPATCH', 'ASSIGNED')")
    pending_deliveries = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) as c FROM deliveries WHERE status IN ('ACCEPTED', 'IN_TRANSIT', 'ARRIVED')")
    active_deliveries = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) as c FROM deliveries WHERE status = 'DELIVERED'")
    completed_deliveries = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) as c FROM deliveries WHERE status IN ('NOT_DELIVERED', 'RETURNED_TO_HUB')")
    failed_deliveries = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) as c FROM vehicles WHERE status = 'AVAILABLE'")
    available_vehicles = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) as c FROM vehicles")
    total_vehicles = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) as c FROM drivers")
    active_drivers = cur.fetchone()["c"]
    cur.execute("SELECT COALESCE(SUM(total_distance_m), 0.0) as dist FROM delivery_batches")
    agg = cur.fetchone()
    total_dist_km = round(float(agg["dist"]) / 1000.0, 2)
    est_cost_inr = round(total_dist_km * 15.0 + total_batches * 250.0, 2)
    return {
        "total_batches": total_batches,
        "total_deliveries": total_deliveries,
        "pending_deliveries": pending_deliveries,
        "active_deliveries": active_deliveries,
        "completed_deliveries": completed_deliveries,
        "failed_deliveries": failed_deliveries,
        "available_vehicles": available_vehicles,
        "total_vehicles": total_vehicles,
        "active_drivers": active_drivers,
        "total_optimized_distance_km": total_dist_km,
        "estimated_operating_cost_inr": est_cost_inr,
    }

@router.get("/locations")
def list_locations(db: DeliveryDatabase = Depends(get_db)) -> list[dict[str, Any]]:
    cur = db._conn.cursor()
    cur.execute("SELECT * FROM delivery_locations ORDER BY created_at DESC, id ASC")
    return [dict(r) for r in cur.fetchall()]

@router.post("/locations", status_code=status.HTTP_201_CREATED)
def create_location(req: LocationCreateRequest, db: DeliveryDatabase = Depends(get_db)) -> dict[str, Any]:
    if req.ready_time > req.due_time:
        raise HTTPException(status_code=400, detail="ready_time cannot exceed due_time")
    loc_id = f"LOC_{uuid4().hex[:6].upper()}"
    now = time.time()
    with db._lock, db._conn:
        db._conn.execute(
            '''
            INSERT INTO delivery_locations
            (id, customer_name, customer_phone, customer_email, address, lat, lon, demand, priority, ready_time, due_time, service_time, is_batched, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
            ''',
            (loc_id, req.customer_name, req.customer_phone, req.customer_email, req.address, req.lat, req.lon, req.demand, req.priority, req.ready_time, req.due_time, req.service_time, now),
        )
    db.log_history("ADMIN", "admin", "LOCATION_CREATED", f"Created delivery location {loc_id} ({req.customer_name})")
    cur = db._conn.cursor()
    cur.execute("SELECT * FROM delivery_locations WHERE id = ?", (loc_id,))
    return dict(cur.fetchone())

@router.put("/locations/{loc_id}")
def update_location(loc_id: str, req: LocationCreateRequest, db: DeliveryDatabase = Depends(get_db)) -> dict[str, Any]:
    cur = db._conn.cursor()
    cur.execute("SELECT * FROM delivery_locations WHERE id = ?", (loc_id,))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="Location not found")
    with db._lock, db._conn:
        db._conn.execute(
            '''
            UPDATE delivery_locations
            SET customer_name=?, customer_phone=?, customer_email=?, address=?, lat=?, lon=?, demand=?, priority=?, ready_time=?, due_time=?, service_time=?
            WHERE id=?
            ''',
            (req.customer_name, req.customer_phone, req.customer_email, req.address, req.lat, req.lon, req.demand, req.priority, req.ready_time, req.due_time, req.service_time, loc_id),
        )
    cur.execute("SELECT * FROM delivery_locations WHERE id = ?", (loc_id,))
    return dict(cur.fetchone())

@router.delete("/locations/{loc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_location(loc_id: str, db: DeliveryDatabase = Depends(get_db)) -> None:
    with db._lock, db._conn:
        db._conn.execute("DELETE FROM delivery_locations WHERE id = ?", (loc_id,))

@router.get("/vehicles")
def list_vehicles(db: DeliveryDatabase = Depends(get_db)) -> list[dict[str, Any]]:
    cur = db._conn.cursor()
    cur.execute("SELECT * FROM vehicles ORDER BY id ASC")
    return [dict(r) for r in cur.fetchall()]

@router.post("/vehicles", status_code=status.HTTP_201_CREATED)
def create_vehicle(req: VehicleCreateRequest, db: DeliveryDatabase = Depends(get_db)) -> dict[str, Any]:
    v_id = req.id or f"V_{uuid4().hex[:4].upper()}"
    now = time.time()
    try:
        with db._lock, db._conn:
            db._conn.execute(
                '''
                INSERT INTO vehicles (id, registration_number, name, capacity, status, assigned_driver_id, cost_per_km, fixed_cost, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (v_id, req.registration_number.strip(), req.name, req.capacity, req.status, req.assigned_driver_id, req.cost_per_km, req.fixed_cost, now),
            )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not create vehicle: {exc}") from exc
    cur = db._conn.cursor()
    cur.execute("SELECT * FROM vehicles WHERE id = ?", (v_id,))
    return dict(cur.fetchone())

@router.put("/vehicles/{vehicle_id}")
def update_vehicle(vehicle_id: str, req: VehicleCreateRequest, db: DeliveryDatabase = Depends(get_db)) -> dict[str, Any]:
    with db._lock, db._conn:
        db._conn.execute(
            '''
            UPDATE vehicles
            SET registration_number=?, name=?, capacity=?, status=?, assigned_driver_id=?, cost_per_km=?, fixed_cost=?
            WHERE id=?
            ''',
            (req.registration_number, req.name, req.capacity, req.status, req.assigned_driver_id, req.cost_per_km, req.fixed_cost, vehicle_id),
        )
    cur = db._conn.cursor()
    cur.execute("SELECT * FROM vehicles WHERE id = ?", (vehicle_id,))
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    return dict(row)

@router.get("/drivers")
def list_drivers(db: DeliveryDatabase = Depends(get_db)) -> list[dict[str, Any]]:
    cur = db._conn.cursor()
    cur.execute("SELECT * FROM drivers ORDER BY id ASC")
    return [dict(r) for r in cur.fetchall()]

@router.post("/drivers", status_code=status.HTTP_201_CREATED)
def register_driver(req: RegisterDriverRequest, db: DeliveryDatabase = Depends(get_db)) -> dict[str, Any]:
    now = time.time()
    u_id = f"usr_{uuid4().hex[:8]}"
    d_id = f"drv_{uuid4().hex[:6]}"
    try:
        with db._lock, db._conn:
            db._conn.execute(
                "INSERT INTO users (id, username, password_hash, role, full_name, phone, email, created_at) VALUES (?, ?, ?, 'DRIVER', ?, ?, ?, ?)",
                (u_id, req.username.strip(), hash_password(req.password), req.full_name, req.phone, f"{req.username}@routeit.in", now),
            )
            db._conn.execute(
                "INSERT INTO drivers (id, user_id, full_name, phone, license_number, status, assigned_vehicle_id, created_at) VALUES (?, ?, ?, ?, ?, 'AVAILABLE', ?, ?)",
                (d_id, u_id, req.full_name, req.phone, req.license_number, req.assigned_vehicle_id, now),
            )
            if req.assigned_vehicle_id:
                db._conn.execute("UPDATE vehicles SET assigned_driver_id = ? WHERE id = ?", (d_id, req.assigned_vehicle_id))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Driver registration failed: {exc}") from exc
    cur = db._conn.cursor()
    cur.execute("SELECT * FROM drivers WHERE id = ?", (d_id,))
    return dict(cur.fetchone())

@router.post("/batches/optimize", status_code=status.HTTP_201_CREATED)
def create_and_optimize_batch(
    req: BatchCreateOptimizeRequest,
    db: DeliveryDatabase = Depends(get_db),
    store: ProblemStore = Depends(get_store),
) -> dict[str, Any]:
    cur = db._conn.cursor()
    q_locs = ",".join("?" for _ in req.location_ids)
    cur.execute(f"SELECT * FROM delivery_locations WHERE id IN ({q_locs})", req.location_ids)
    loc_rows = [dict(r) for r in cur.fetchall()]
    if not loc_rows:
        raise HTTPException(status_code=400, detail="No valid delivery locations found")

    q_vehs = ",".join("?" for _ in req.vehicle_ids)
    cur.execute(f"SELECT * FROM vehicles WHERE id IN ({q_vehs})", req.vehicle_ids)
    veh_rows = [dict(r) for r in cur.fetchall()]
    if not veh_rows:
        raise HTTPException(status_code=400, detail="No valid vehicles found")

    total_demand = sum(float(l["demand"]) for l in loc_rows)
    total_capacity = sum(float(v["capacity"]) for v in veh_rows)
    max_single_cap = max(float(v["capacity"]) for v in veh_rows)

    if total_demand > total_capacity and req.planning_mode != "partial":
        raise HTTPException(
            status_code=400,
            detail=f"Capacity exceeded: demand ({total_demand:.1f}) > fleet capacity ({total_capacity:.1f}). Enable Partial Plan mode to shed orders by priority.",
        )
    for l in loc_rows:
        if float(l["demand"]) > max_single_cap and req.planning_mode != "partial":
            raise HTTPException(
                status_code=400,
                detail=f"Location {l['id']} demand exceeds max vehicle capacity ({max_single_cap}).",
            )

    batch_id = f"BATCH_{uuid4().hex[:6].upper()}"
    problem_id = f"prob_{batch_id.lower()}"

    solver_customers = [
        Customer(
            id=l["id"],
            name=l["customer_name"],
            lat=float(l["lat"]),
            lon=float(l["lon"]),
            demand=float(l["demand"]),
            ready_time=float(l["ready_time"]),
            due_time=float(l["due_time"]),
            service_time=float(l["service_time"]),
            priority=int(l["priority"]),
            delivery_instructions=l.get("delivery_instructions"),
            time_window_type=l.get("time_window_type", "hard"),
        )
        for l in loc_rows
    ]
    solver_vehicles = [
        Vehicle(
            id=v["id"],
            capacity=float(v["capacity"]),
            shift_start=float(v["shift_start"]),
            shift_end=float(v["shift_end"]),
            fixed_cost=float(v["fixed_cost"]),
            cost_per_distance=float(v["cost_per_km"]) / 1000.0,
            cost_per_time=0.01,
            return_to_depot=req.depot_return,
        )
        for v in veh_rows
    ]

    problem = Problem(
        id=problem_id,
        depot=VADODARA_HUB,
        customers=solver_customers,
        vehicles=solver_vehicles,
        coordinate_system="geographic",
        planning_mode=req.planning_mode,
        optimization_profile=req.optimization_profile,
        fleet_mode=req.fleet_mode,
        target_fleet_size=req.target_fleet_size,
        return_to_depot=req.depot_return,
    )
    problem.compute_euclidean_matrices(speed=8.333)

    traffic_adapter = SimulatedEventAdapter(base_adapter=TimeOfDayProfileAdapter({h: 1.0 for h in range(24)}))
    oracle = EuclideanOracle(base_speed_mps=8.333, coordinate_system="geographic", traffic_adapter=traffic_adapter)
    qpso_cfg = QPSOConfig(num_particles=req.num_particles, max_iters=req.max_iters, seed=req.seed, apply_tw_repair=True)

    if req.planning_mode == "partial":
        solution = solve_partial_plan(problem, lambda p: solve_qpso(p, config=qpso_cfg, cost_oracle=oracle))
    else:
        solution, _ = solve_qpso(problem, config=qpso_cfg, cost_oracle=oracle)

    cost_cfg = BusinessCostConfig(
        cost_per_km=req.cost_per_km,
        cost_per_hour=req.cost_per_hour,
        vehicle_activation_cost=req.vehicle_activation_cost,
    )
    solution.cost_breakdown = compute_cost_breakdown(
        total_distance_metres=sum(r.distance for r in solution.routes),
        total_duration_seconds=sum(r.duration for r in solution.routes),
        num_vehicles_used=len(solution.routes),
        total_sla_penalty=solution.total_sla_penalty,
        config=cost_cfg,
    )

    geojson_data = solution_to_geojson(problem, solution, cost_oracle=oracle)

    store.save_problem(problem)
    store.save_oracle(problem_id, oracle)
    store.save_solution(problem_id, solution)

    now = time.time()
    active_routes = [r for r in solution.routes if r.stop_ids]
    total_dist_m = sum(r.distance for r in active_routes)
    total_dur_sec = sum(r.duration for r in active_routes)

    loc_by_id = {l["id"]: l for l in loc_rows}
    veh_by_id = {v["id"]: v for v in veh_rows}
    created_jobs: list[dict[str, Any]] = []
    created_deliveries: list[dict[str, Any]] = []

    with db._lock, db._conn:
        db._conn.execute(
            '''
            INSERT INTO delivery_batches
            (id, name, problem_id, status, total_distance_m, total_duration_sec, total_cost, num_vehicles_used, num_stops, geojson_str, created_at, optimized_at)
            VALUES (?, ?, ?, 'PENDING_DISPATCH', ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (batch_id, req.name, problem_id, round(total_dist_m, 2), round(total_dur_sec, 2), round(solution.total_cost, 2), len(active_routes), len(loc_rows), json.dumps(geojson_data), now, now),
        )
        for r_idx, route in enumerate(active_routes):
            v_id = route.vehicle_id if route.vehicle_id in veh_by_id else veh_rows[r_idx % len(veh_rows)]["id"]
            v_info = veh_by_id[v_id]
            drv_id = v_info.get("assigned_driver_id")
            job_id = f"JOB_{batch_id}_{v_id}"
            color = ROUTE_PALETTE[r_idx % len(ROUTE_PALETTE)]
            est_cost = round((route.distance / 1000.0) * float(v_info["cost_per_km"]) + float(v_info["fixed_cost"]), 2)
            initial_job_status = "ASSIGNED" if drv_id else "PENDING_DISPATCH"

            db._conn.execute(
                '''
                INSERT INTO dispatch_jobs
                (id, batch_id, vehicle_id, driver_id, status, stop_count, total_load, vehicle_capacity, planned_distance_m, planned_duration_sec, estimated_cost_inr, route_color, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (job_id, batch_id, v_id, drv_id, initial_job_status, len(route.stop_ids), round(route.load, 2), float(v_info["capacity"]), round(route.distance, 2), round(route.duration, 2), est_cost, color, now),
            )
            for seq_idx, (stop_id, arr_time) in enumerate(zip(route.stop_ids, route.arrival_times), start=1):
                loc = loc_by_id[stop_id]
                deliv_id = f"DEL_{batch_id}_{stop_id}"
                trk_token = generate_tracking_token()
                db._conn.execute(
                    '''
                    INSERT INTO deliveries
                    (id, batch_id, dispatch_job_id, location_id, customer_name, customer_phone, address, lat, lon, demand, priority, ready_time, due_time, service_time, vehicle_id, driver_id, stop_sequence, eta_seconds, status, tracking_token, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''',
                    (deliv_id, batch_id, job_id, stop_id, loc["customer_name"], loc["customer_phone"], loc["address"], float(loc["lat"]), float(loc["lon"]), float(loc["demand"]), int(loc["priority"]), float(loc["ready_time"]), float(loc["due_time"]), float(loc["service_time"]), v_id, drv_id, seq_idx, round(arr_time, 1), initial_job_status, trk_token, now),
                )
                db.create_or_refresh_otp(deliv_id)
                created_deliveries.append({
                    "id": deliv_id, "location_id": stop_id, "customer_name": loc["customer_name"],
                    "vehicle_id": v_id, "driver_id": drv_id, "stop_sequence": seq_idx,
                    "eta_seconds": round(arr_time, 1), "status": initial_job_status, "tracking_token": trk_token,
                })
            created_jobs.append({
                "id": job_id, "batch_id": batch_id, "vehicle_id": v_id, "driver_id": drv_id,
                "status": initial_job_status, "stop_count": len(route.stop_ids),
                "total_load": round(route.load, 2), "vehicle_capacity": float(v_info["capacity"]),
                "planned_distance_m": round(route.distance, 2), "planned_duration_sec": round(route.duration, 2),
                "estimated_cost_inr": est_cost, "route_color": color,
            })

    db.log_history("ADMIN", "admin", "BATCH_OPTIMIZED_QPSO", f"Batch {batch_id} optimized via QPSO + Prins Split.", batch_id=batch_id, old_status="CREATED", new_status="PENDING_DISPATCH")
    return {
        "batch_id": batch_id,
        "problem_id": problem_id,
        "name": req.name,
        "status": "PENDING_DISPATCH",
        "total_distance_m": round(total_dist_m, 2),
        "total_duration_sec": round(total_dur_sec, 2),
        "total_cost": round(solution.total_cost, 2),
        "is_feasible": solution.is_feasible,
        "feasibility_status": getattr(solution, "feasibility_status", "feasible" if solution.is_feasible else "infeasible"),
        "status_message": getattr(solution, "status_message", "Plan is fully feasible"),
        "cost_breakdown": solution.cost_breakdown.model_dump() if solution.cost_breakdown else None,
        "unserved_orders": getattr(solution, "unserved_orders", []),
        "fleet_utilization_pct": getattr(solution, "fleet_utilization_pct", 0.0),
        "num_routes": len(active_routes),
        "dispatch_jobs": created_jobs,
        "deliveries": created_deliveries,
        "geojson": geojson_data,
    }

@router.get("/batches")
def list_batches(db: DeliveryDatabase = Depends(get_db)) -> list[dict[str, Any]]:
    cur = db._conn.cursor()
    cur.execute("SELECT id, name, problem_id, status, total_distance_m, total_duration_sec, total_cost, num_vehicles_used, num_stops, created_at, optimized_at FROM delivery_batches ORDER BY created_at DESC")
    return [dict(r) for r in cur.fetchall()]

@router.get("/batches/{batch_id}")
def get_batch_details(batch_id: str, db: DeliveryDatabase = Depends(get_db)) -> dict[str, Any]:
    cur = db._conn.cursor()
    cur.execute("SELECT * FROM delivery_batches WHERE id = ?", (batch_id,))
    b = cur.fetchone()
    if not b:
        raise HTTPException(status_code=404, detail="Batch not found")
    res = dict(b)
    res["geojson"] = json.loads(res.pop("geojson_str", "{}") or "{}")
    cur.execute("SELECT * FROM dispatch_jobs WHERE batch_id = ? ORDER BY vehicle_id ASC", (batch_id,))
    res["dispatch_jobs"] = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT * FROM deliveries WHERE batch_id = ? ORDER BY vehicle_id ASC, stop_sequence ASC", (batch_id,))
    res["deliveries"] = [dict(r) for r in cur.fetchall()]
    return res

@router.get("/dispatch/jobs")
def list_dispatch_jobs(driver_id: str | None = None, db: DeliveryDatabase = Depends(get_db)) -> list[dict[str, Any]]:
    cur = db._conn.cursor()
    if driver_id:
        cur.execute("SELECT * FROM dispatch_jobs WHERE driver_id = ? OR status IN ('PENDING_DISPATCH', 'ASSIGNED') ORDER BY created_at DESC", (driver_id,))
    else:
        cur.execute("SELECT * FROM dispatch_jobs ORDER BY created_at DESC")
    jobs = [dict(r) for r in cur.fetchall()]
    for j in jobs:
        cur.execute(
            "SELECT id, location_id, customer_name, customer_phone, address, lat, lon, demand, priority, ready_time, due_time, service_time, stop_sequence, eta_seconds, status, tracking_token, failure_reason, hub_verified FROM deliveries WHERE dispatch_job_id = ? ORDER BY stop_sequence ASC",
            (j["id"],),
        )
        j["stops"] = [dict(s) for s in cur.fetchall()]
    return jobs

@router.post("/dispatch/jobs/{job_id}/assign")
def assign_driver_to_job(job_id: str, req: AssignDriverRequest, db: DeliveryDatabase = Depends(get_db)) -> dict[str, Any]:
    now = time.time()
    with db._lock, db._conn:
        cur = db._conn.cursor()
        cur.execute("SELECT * FROM dispatch_jobs WHERE id = ?", (job_id,))
        job = cur.fetchone()
        if not job:
            raise HTTPException(status_code=404, detail="Dispatch job not found")
        db._conn.execute("UPDATE dispatch_jobs SET driver_id = ?, status = 'ASSIGNED' WHERE id = ?", (req.driver_id, job_id))
        db._conn.execute("UPDATE deliveries SET driver_id = ?, status = 'ASSIGNED', updated_at = ? WHERE dispatch_job_id = ?", (req.driver_id, now, job_id))
        db._conn.execute("UPDATE vehicles SET assigned_driver_id = ? WHERE id = ?", (req.driver_id, job["vehicle_id"]))
    cur = db._conn.cursor()
    cur.execute("SELECT * FROM dispatch_jobs WHERE id = ?", (job_id,))
    return dict(cur.fetchone())

@router.post("/dispatch/jobs/{job_id}/cancel")
def cancel_dispatch_job(job_id: str, db: DeliveryDatabase = Depends(get_db)) -> dict[str, Any]:
    with db._lock, db._conn:
        db._conn.execute("UPDATE dispatch_jobs SET status = 'CREATED', driver_id = NULL WHERE id = ?", (job_id,))
        db._conn.execute("UPDATE deliveries SET status = 'CREATED', driver_id = NULL WHERE dispatch_job_id = ?", (job_id,))
    cur = db._conn.cursor()
    cur.execute("SELECT * FROM dispatch_jobs WHERE id = ?", (job_id,))
    return dict(cur.fetchone())

@router.post("/driver/jobs/{job_id}/accept")
def driver_accept_job(job_id: str, driver_id: str, db: DeliveryDatabase = Depends(get_db)) -> dict[str, Any]:
    now = time.time()
    with db._lock:
        cur = db._conn.cursor()
        cur.execute("SELECT * FROM dispatch_jobs WHERE id = ?", (job_id,))
        job = cur.fetchone()
        if not job:
            raise HTTPException(status_code=404, detail="Dispatch job not found")
        if job["status"] not in ("PENDING_DISPATCH", "ASSIGNED"):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Job {job_id} already accepted.")
        if job["driver_id"] and job["driver_id"] != driver_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Job assigned to {job['driver_id']}.")

        cur.execute(
            "UPDATE dispatch_jobs SET status = 'ACCEPTED', driver_id = ?, accepted_at = ? WHERE id = ? AND status IN ('PENDING_DISPATCH', 'ASSIGNED')",
            (driver_id, now, job_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Concurrent acceptance conflict")

        db._conn.execute("UPDATE deliveries SET status = 'ACCEPTED', driver_id = ?, updated_at = ? WHERE dispatch_job_id = ?", (driver_id, now, job_id))
        db._conn.execute("UPDATE vehicles SET status = 'IN_USE', current_batch_id = ?, assigned_driver_id = ? WHERE id = ?", (job["batch_id"], driver_id, job["vehicle_id"]))
        db._conn.execute("UPDATE drivers SET status = 'ON_TRIP', assigned_vehicle_id = ? WHERE id = ?", (job["vehicle_id"], driver_id))
        db._conn.commit()

    db.log_history("DRIVER", driver_id, "JOB_ACCEPTED", f"Driver {driver_id} accepted job {job_id}.", batch_id=job["batch_id"], old_status=job["status"], new_status="ACCEPTED")
    cur = db._conn.cursor()
    cur.execute("SELECT * FROM dispatch_jobs WHERE id = ?", (job_id,))
    accepted_job = dict(cur.fetchone())
    cur.execute("SELECT id, location_id, customer_name, customer_phone, address, lat, lon, demand, priority, stop_sequence, eta_seconds, status, tracking_token FROM deliveries WHERE dispatch_job_id = ? ORDER BY stop_sequence ASC", (job_id,))
    accepted_job["stops"] = [
        {**dict(s), "google_maps_url": f"https://www.google.com/maps/dir/?api=1&destination={s['lat']},{s['lon']}&travelmode=driving"}
        for s in cur.fetchall()
    ]
    accepted_job["central_hub"] = {
        "stop_number": 0, "name": VADODARA_HUB.name, "lat": VADODARA_HUB.lat, "lon": VADODARA_HUB.lon,
        "google_maps_url": f"https://www.google.com/maps/dir/?api=1&destination={VADODARA_HUB.lat},{VADODARA_HUB.lon}&travelmode=driving",
    }
    return accepted_job

@router.post("/deliveries/{delivery_id}/progress")
def update_delivery_progress(delivery_id: str, req: DriverProgressRequest, db: DeliveryDatabase = Depends(get_db)) -> dict[str, Any]:
    now = time.time()
    with db._lock, db._conn:
        cur = db._conn.cursor()
        cur.execute("SELECT * FROM deliveries WHERE id = ?", (delivery_id,))
        deliv = cur.fetchone()
        if not deliv:
            raise HTTPException(status_code=404, detail="Delivery not found")
        old_status = deliv["status"]
        if req.status not in ALLOWED_TRANSITIONS.get(old_status, set()) and old_status != req.status:
            raise HTTPException(status_code=400, detail=f"Invalid transition {old_status} -> {req.status}")
        db._conn.execute("UPDATE deliveries SET status = ?, updated_at = ? WHERE id = ?", (req.status, now, delivery_id))
        if deliv["dispatch_job_id"]:
            db._conn.execute("UPDATE dispatch_jobs SET status = 'IN_TRANSIT' WHERE id = ? AND status = 'ACCEPTED'", (deliv["dispatch_job_id"],))
    db.log_history("DRIVER", deliv["driver_id"] or "driver", "DELIVERY_STATUS_UPDATED", f"Transitioned {old_status} -> {req.status}", delivery_id=delivery_id, batch_id=deliv["batch_id"], old_status=old_status, new_status=req.status)
    manager.broadcast_sync(deliv["batch_id"], {"type": "delivery_status_update", "delivery_id": delivery_id, "batch_id": deliv["batch_id"], "status": req.status})
    cur = db._conn.cursor()
    cur.execute("SELECT * FROM deliveries WHERE id = ?", (delivery_id,))
    return dict(cur.fetchone())

@router.post("/deliveries/{delivery_id}/verify-otp")
def verify_delivery_otp(delivery_id: str, req: OTPVerifyRequest, db: DeliveryDatabase = Depends(get_db)) -> dict[str, Any]:
    cur = db._conn.cursor()
    cur.execute("SELECT driver_id, batch_id FROM deliveries WHERE id = ?", (delivery_id,))
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Delivery not found")
    driver_id = req.driver_id or row["driver_id"] or "drv_01"
    ok, msg, updated = db.verify_delivery_otp_atomic(delivery_id, driver_id, req.otp_code)
    if not ok or updated is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    manager.broadcast_sync(row["batch_id"], {"type": "delivery_verified", "delivery_id": delivery_id, "batch_id": row["batch_id"], "status": "DELIVERED"})
    return {"verified": True, "message": msg, "delivery": {"id": updated["id"], "status": updated["status"], "delivered_at": updated["delivered_at"], "customer_name": updated["customer_name"]}}

@router.post("/deliveries/{delivery_id}/fail")
def mark_delivery_failed(delivery_id: str, req: FailedDeliveryRequest, db: DeliveryDatabase = Depends(get_db)) -> dict[str, Any]:
    now = time.time()
    with db._lock, db._conn:
        cur = db._conn.cursor()
        cur.execute("SELECT * FROM deliveries WHERE id = ?", (delivery_id,))
        deliv = cur.fetchone()
        if not deliv:
            raise HTTPException(status_code=404, detail="Delivery not found")
        if deliv["status"] == "DELIVERED":
            raise HTTPException(status_code=400, detail="Cannot fail an already DELIVERED package")
        old_status = deliv["status"]
        db._conn.execute("UPDATE deliveries SET status = 'NOT_DELIVERED', failure_reason = ?, hub_verified = 0, updated_at = ? WHERE id = ?", (req.reason.strip(), now, delivery_id))
    db.log_history("DRIVER", req.driver_id or deliv["driver_id"] or "drv_01", "DELIVERY_FAILED_RETURN_QUEUED", f"Reason: {req.reason.strip()}", delivery_id=delivery_id, batch_id=deliv["batch_id"], old_status=old_status, new_status="NOT_DELIVERED")
    cur = db._conn.cursor()
    cur.execute("SELECT * FROM deliveries WHERE id = ?", (delivery_id,))
    return dict(cur.fetchone())

@router.post("/deliveries/{delivery_id}/return-to-hub")
def verify_return_to_hub(delivery_id: str, db: DeliveryDatabase = Depends(get_db)) -> dict[str, Any]:
    now = time.time()
    with db._lock, db._conn:
        cur = db._conn.cursor()
        cur.execute("SELECT * FROM deliveries WHERE id = ?", (delivery_id,))
        deliv = cur.fetchone()
        if not deliv:
            raise HTTPException(status_code=404, detail="Delivery not found")
        db._conn.execute("UPDATE deliveries SET status = 'RETURNED_TO_HUB', hub_verified = 1, hub_verified_at = ?, updated_at = ? WHERE id = ?", (now, now, delivery_id))
    db.log_history("ADMIN", "admin", "RETURN_TO_HUB_VERIFIED", f"Verified returned package {delivery_id}.", delivery_id=delivery_id, batch_id=deliv["batch_id"], old_status="NOT_DELIVERED", new_status="RETURNED_TO_HUB")
    cur = db._conn.cursor()
    cur.execute("SELECT * FROM deliveries WHERE id = ?", (delivery_id,))
    return dict(cur.fetchone())

@router.get("/track/{tracking_token}")
def track_delivery_public(tracking_token: str, db: DeliveryDatabase = Depends(get_db)) -> dict[str, Any]:
    cur = db._conn.cursor()
    cur.execute("SELECT * FROM deliveries WHERE tracking_token = ? OR id = ?", (tracking_token, tracking_token))
    deliv = cur.fetchone()
    if not deliv:
        raise HTTPException(status_code=404, detail="Invalid tracking token or delivery ID")
    if deliv["id"] == tracking_token and deliv["tracking_token"] != tracking_token:
        raise HTTPException(status_code=403, detail="Secure tracking token required")

    cur.execute(
        "SELECT COUNT(*) as rem FROM deliveries WHERE dispatch_job_id = ? AND stop_sequence < ? AND status NOT IN ('DELIVERED', 'NOT_DELIVERED', 'RETURNED_TO_HUB')",
        (deliv["dispatch_job_id"], deliv["stop_sequence"]),
    )
    remaining_stops = cur.fetchone()["rem"]

    driver_info = None
    if deliv["driver_id"]:
        cur.execute("SELECT full_name, phone, current_lat, current_lon FROM drivers WHERE id = ?", (deliv["driver_id"],))
        drv = cur.fetchone()
        if drv:
            driver_info = {"name": drv["full_name"], "phone": drv["phone"], "last_lat": drv["current_lat"], "last_lon": drv["current_lon"]}

    vehicle_info = None
    if deliv["vehicle_id"]:
        cur.execute("SELECT registration_number, name FROM vehicles WHERE id = ?", (deliv["vehicle_id"],))
        veh = cur.fetchone()
        if veh:
            vehicle_info = {"registration_number": veh["registration_number"], "name": veh["name"]}

    otp_for_customer: str | None = None
    if deliv["status"] in ("ACCEPTED", "IN_TRANSIT", "ARRIVED"):
        cur.execute("SELECT portal_cipher, is_used FROM delivery_otps WHERE delivery_id = ?", (deliv["id"],))
        otp_row = cur.fetchone()
        if otp_row and not otp_row["is_used"]:
            otp_for_customer = decrypt_customer_otp_for_portal(deliv["id"], otp_row["portal_cipher"])

    return {
        "delivery_id": deliv["id"], "batch_id": deliv["batch_id"], "customer_name": deliv["customer_name"],
        "address": deliv["address"], "status": deliv["status"], "stop_sequence": deliv["stop_sequence"],
        "remaining_stops_ahead": remaining_stops, "eta_seconds": deliv["eta_seconds"],
        "driver": driver_info, "vehicle": vehicle_info, "otp_code": otp_for_customer,
        "failure_reason": deliv["failure_reason"], "delivered_at": deliv["delivered_at"], "updated_at": deliv["updated_at"],
    }

@router.post("/batches/{batch_id}/incidents")
def inject_batch_incident(
    batch_id: str,
    event_req: DynamicEventCreate,
    db: DeliveryDatabase = Depends(get_db),
    store: ProblemStore = Depends(get_store),
) -> dict[str, Any]:
    cur = db._conn.cursor()
    cur.execute("SELECT * FROM delivery_batches WHERE id = ?", (batch_id,))
    batch = cur.fetchone()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    problem_id = batch["problem_id"]
    problem = store.get_problem(problem_id)
    current_solution = store.get_solution(problem_id)
    if problem is None or current_solution is None:
        raise HTTPException(status_code=400, detail="Active solver state not found for batch")

    cur.execute("SELECT location_id, status, eta_seconds FROM deliveries WHERE batch_id = ?", (batch_id,))
    deliv_rows = [dict(r) for r in cur.fetchall()]
    completed_etas = [float(r["eta_seconds"]) + 900.0 for r in deliv_rows if r["status"] in ("DELIVERED", "NOT_DELIVERED", "RETURNED_TO_HUB", "ARRIVED")]
    effective_time = max([event_req.trigger_time, 25200.0] + completed_etas)

    domain_event = event_req.to_domain_event()
    oracle = store.get_oracle(problem_id)
    if oracle is None or not isinstance(oracle.traffic_adapter, SimulatedEventAdapter):
        traffic_adapter = SimulatedEventAdapter(base_adapter=TimeOfDayProfileAdapter({h: 1.0 for h in range(24)}))
        oracle = EuclideanOracle(base_speed_mps=8.333, coordinate_system="geographic", traffic_adapter=traffic_adapter)
        store.save_oracle(problem_id, oracle)

    if hasattr(domain_event, "to_simulated_incidents"):
        for inc in domain_event.to_simulated_incidents():
            oracle.traffic_adapter.add_incident(inc)

    reopt_config = ReoptimizerConfig(theta=0.01, theta_absolute=2.0, commitment_horizon_seconds=300.0, seed=42)
    reoptimizer = DynamicReoptimizer(problem, cost_oracle=oracle, config=reopt_config)
    reopt_solution, record = reoptimizer.reoptimize(current_solution=current_solution, current_time=effective_time, event=domain_event)

    store.save_solution(problem_id, reopt_solution)
    store.add_event_record(problem_id, record)
    geojson_data = solution_to_geojson(problem, reopt_solution, cost_oracle=oracle, current_time=effective_time)

    now = time.time()
    with db._lock, db._conn:
        db._conn.execute("UPDATE delivery_batches SET total_cost = ?, geojson_str = ? WHERE id = ?", (round(reopt_solution.total_cost, 2), json.dumps(geojson_data), batch_id))
        for route in reopt_solution.routes:
            for seq_idx, (stop_id, arr_time) in enumerate(zip(route.stop_ids, route.arrival_times), start=1):
                db._conn.execute(
                    "UPDATE deliveries SET stop_sequence = ?, eta_seconds = ?, updated_at = ? WHERE batch_id = ? AND location_id = ? AND status NOT IN ('DELIVERED', 'NOT_DELIVERED', 'RETURNED_TO_HUB')",
                    (seq_idx, round(arr_time, 1), now, batch_id, stop_id),
                )

    db.log_history("ADMIN", "admin", f"DYNAMIC_REOPT_{record.tier_selected.value}", f"Incident handled via {record.tier_selected.value}.", batch_id=batch_id)
    return {
        "type": "reoptimization_update", "batch_id": batch_id, "problem_id": problem_id,
        "event_id": record.event_id, "tier_selected": record.tier_selected.value,
        "wall_clock_time_ms": record.wall_clock_time_ms, "cost_before": record.cost_before,
        "cost_after": record.cost_after, "delta_f": record.delta_f,
        "stops_changed_count": record.stops_changed_count, "stops_changed": record.stops_changed,
        "is_feasible": record.is_feasible, "message": record.message, "geojson": geojson_data,
    }

@router.get("/history")
def get_delivery_history(db: DeliveryDatabase = Depends(get_db)) -> list[dict[str, Any]]:
    cur = db._conn.cursor()
    cur.execute("SELECT * FROM delivery_history ORDER BY timestamp DESC LIMIT 200")
    return [dict(r) for r in cur.fetchall()]
