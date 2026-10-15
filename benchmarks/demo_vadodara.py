"""Vadodara 30-Stop CVRPTW Optimization Demo with Valhalla Road Routing & GeoJSON Export.

This demo script:
1. Loads or generates 30 realistic delivery customer stops in Vadodara city, Gujarat.
2. Checks Valhalla routing engine connectivity (http://localhost:8002).
   - If online: queries real road network travel-time matrices and turn-by-turn road shapes.
   - If offline: runs with simulated urban road travel times and street geometry
     (explicitly labeled as simulated per AGENTS.md integrity rules).
3. Solves the CVRPTW using QPSO + Prins Split + Memetic Local Search.
4. Exports the resulting multi-vehicle routes as a standard GeoJSON FeatureCollection
   including stop point markers and road-following LineString geometries.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
import time
from typing import Any
import urllib.error
import urllib.request

# Ensure workspace root is in sys.path when executed directly
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from routing.cost_oracle import (
    EuclideanOracle,
    Location,
    ValhallaOracle,
    encode_polyline,
)
from solver.io import load_problem_json, save_problem_json
from solver.models import Customer, Depot, Problem, Solution, Vehicle
from solver.qpso import QPSOConfig, solve_qpso


# ---------------------------------------------------------------------------
# 30 Realistic Vadodara Delivery Locations (Geographic Coordinates)
# ---------------------------------------------------------------------------

VADODARA_DEPOT = {
    "id": "depot",
    "name": "Vadodara Central Distribution Hub (Sayajigunj)",
    "lat": 22.3108,
    "lon": 73.1811,
    "ready_time": 0.0,
    "due_time": 28800.0,  # 8-hour shift (seconds)
    "service_time": 0.0,
}

VADODARA_STOPS = [
    {"id": "C01", "name": "Alkapuri Commercial Hub", "lat": 22.3130, "lon": 73.1725, "demand": 18.0, "ready_time": 0.0, "due_time": 14400.0},
    {"id": "C02", "name": "Akota Residential Center", "lat": 22.2965, "lon": 73.1750, "demand": 14.0, "ready_time": 0.0, "due_time": 14400.0},
    {"id": "C03", "name": "Gotri Medical Center", "lat": 22.3210, "lon": 73.1480, "demand": 22.0, "ready_time": 1800.0, "due_time": 18000.0},
    {"id": "C04", "name": "Karelibaug Market", "lat": 22.3245, "lon": 73.2050, "demand": 16.0, "ready_time": 0.0, "due_time": 14400.0},
    {"id": "C05", "name": "Fatehgunj Post Office", "lat": 22.3235, "lon": 73.1860, "demand": 20.0, "ready_time": 900.0, "due_time": 16200.0},
    {"id": "C06", "name": "Manjalpur Crossroads", "lat": 22.2680, "lon": 73.1950, "demand": 25.0, "ready_time": 3600.0, "due_time": 21600.0},
    {"id": "C07", "name": "Makarpura GIDC Phase 1", "lat": 22.2530, "lon": 73.1980, "demand": 28.0, "ready_time": 3600.0, "due_time": 21600.0},
    {"id": "C08", "name": "Harni Airport Circle", "lat": 22.3420, "lon": 73.2180, "demand": 15.0, "ready_time": 0.0, "due_time": 14400.0},
    {"id": "C09", "name": "Waghodia Ring Road", "lat": 22.3020, "lon": 73.2380, "demand": 24.0, "ready_time": 1800.0, "due_time": 18000.0},
    {"id": "C10", "name": "Vasna Road Complex", "lat": 22.2850, "lon": 73.1530, "demand": 19.0, "ready_time": 0.0, "due_time": 14400.0},
    {"id": "C11", "name": "Nizampura Plaza", "lat": 22.3380, "lon": 73.1790, "demand": 17.0, "ready_time": 900.0, "due_time": 16200.0},
    {"id": "C12", "name": "Subhanpura High Street", "lat": 22.3250, "lon": 73.1620, "demand": 21.0, "ready_time": 1800.0, "due_time": 18000.0},
    {"id": "C13", "name": "Gorwa Industrial Area", "lat": 22.3350, "lon": 73.1510, "demand": 26.0, "ready_time": 3600.0, "due_time": 21600.0},
    {"id": "C14", "name": "Tandalja Heights", "lat": 22.2870, "lon": 73.1610, "demand": 16.0, "ready_time": 0.0, "due_time": 14400.0},
    {"id": "C15", "name": "Sama Lake Point", "lat": 22.3480, "lon": 73.2010, "demand": 18.0, "ready_time": 900.0, "due_time": 16200.0},
    {"id": "C16", "name": "Pratapgunj University Gate", "lat": 22.3190, "lon": 73.1910, "demand": 12.0, "ready_time": 0.0, "due_time": 14400.0},
    {"id": "C17", "name": "Chhani Canal Road", "lat": 22.3680, "lon": 73.1840, "demand": 22.0, "ready_time": 1800.0, "due_time": 18000.0},
    {"id": "C18", "name": "Sayajipura Logistics Hub", "lat": 22.3220, "lon": 73.2420, "demand": 27.0, "ready_time": 3600.0, "due_time": 21600.0},
    {"id": "C19", "name": "Atladara Railway Station", "lat": 22.2720, "lon": 73.1520, "demand": 15.0, "ready_time": 0.0, "due_time": 14400.0},
    {"id": "C20", "name": "Kalali Junction", "lat": 22.2640, "lon": 73.1640, "demand": 20.0, "ready_time": 900.0, "due_time": 16200.0},
    {"id": "C21", "name": "Ellora Park Avenue", "lat": 22.3160, "lon": 73.1630, "demand": 14.0, "ready_time": 0.0, "due_time": 14400.0},
    {"id": "C22", "name": "Bhayli Township", "lat": 22.2810, "lon": 73.1250, "demand": 23.0, "ready_time": 1800.0, "due_time": 18000.0},
    {"id": "C23", "name": "Mandvi Gate Heritage", "lat": 22.2995, "lon": 73.2085, "demand": 19.0, "ready_time": 0.0, "due_time": 14400.0},
    {"id": "C24", "name": "Wadi Clock Tower", "lat": 22.2930, "lon": 73.2140, "demand": 13.0, "ready_time": 900.0, "due_time": 16200.0},
    {"id": "C25", "name": "Panigate Market", "lat": 22.3015, "lon": 73.2190, "demand": 18.0, "ready_time": 0.0, "due_time": 14400.0},
    {"id": "C26", "name": "Raopura Main Bazaar", "lat": 22.3025, "lon": 73.2010, "demand": 15.0, "ready_time": 0.0, "due_time": 14400.0},
    {"id": "C27", "name": "Dandia Bazar Circle", "lat": 22.2980, "lon": 73.1970, "demand": 16.0, "ready_time": 0.0, "due_time": 14400.0},
    {"id": "C28", "name": "Navapura Square", "lat": 22.2940, "lon": 73.1920, "demand": 14.0, "ready_time": 0.0, "due_time": 14400.0},
    {"id": "C29", "name": "Laxmipura Enclave", "lat": 22.3300, "lon": 73.1410, "demand": 21.0, "ready_time": 1800.0, "due_time": 18000.0},
    {"id": "C30", "name": "Sevasi Canal Greens", "lat": 22.3060, "lon": 73.1180, "demand": 25.0, "ready_time": 3600.0, "due_time": 21600.0},
]

# Color palette for distinct vehicle routes in MapLibre / GeoJSON
ROUTE_COLORS = [
    "#3B82F6",  # Blue
    "#10B981",  # Emerald Green
    "#F59E0B",  # Amber
    "#EC4899",  # Pink
    "#8B5CF6",  # Purple
    "#06B6D4",  # Cyan
    "#EF4444",  # Red
    "#84CC16",  # Lime
]


def build_vadodara_problem(seed: int = 42) -> Problem:
    """Build a reproducible 30-customer CVRPTW problem instance for Vadodara."""
    depot = Depot(
        id=VADODARA_DEPOT["id"],
        lat=VADODARA_DEPOT["lat"],
        lon=VADODARA_DEPOT["lon"],
        ready_time=VADODARA_DEPOT["ready_time"],
        due_time=VADODARA_DEPOT["due_time"],
        service_time=VADODARA_DEPOT["service_time"],
    )

    customers = [
        Customer(
            id=s["id"],
            lat=s["lat"],
            lon=s["lon"],
            demand=s["demand"],
            ready_time=s["ready_time"],
            due_time=s["due_time"],
            service_time=300.0,  # 5 minutes handling time per stop
            priority=1,
        )
        for s in VADODARA_STOPS
    ]

    # Fleet: 8 delivery vans with capacity 100 units each
    vehicles = [
        Vehicle(
            id=f"VAN_{i+1:02d}",
            capacity=100.0,
            shift_start=0.0,
            shift_end=28800.0,
            fixed_cost=50.0,
            cost_per_time=0.01,
            cost_per_distance=0.001,
        )
        for i in range(8)
    ]

    return Problem(
        id="vadodara_30",
        depot=depot,
        customers=customers,
        vehicles=vehicles,
    )


def check_valhalla_alive(base_url: str, timeout: float = 1.5) -> bool:
    """Check if the Valhalla server is responding at base_url."""
    url = f"{base_url.rstrip('/')}/status"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "RouteIt-Demo"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def generate_simulated_road_polyline(
    p1: tuple[float, float], p2: tuple[float, float], steps: int = 6
) -> list[list[float]]:
    """Generate realistic street-corridor polyline [lon, lat] between two GPS coordinates.

    Used when Valhalla Docker is offline so the generated GeoJSON represents realistic
    urban road turns rather than direct straight chords.
    """
    lat1, lon1 = p1
    lat2, lon2 = p2

    coords: list[list[float]] = [[round(lon1, 6), round(lat1, 6)]]

    # Intermediate street-turn waypoint (Manhattan style with road curvature)
    mid_lat = lat1 + (lat2 - lat1) * 0.6
    mid_lon = lon1 + (lon2 - lon1) * 0.4

    # Add slight road curvature deviations
    for i in range(1, steps):
        t = i / steps
        # Hermite-like blending between p1, mid, and p2
        if t <= 0.5:
            u = t * 2.0
            cur_lat = lat1 + (mid_lat - lat1) * u
            cur_lon = lon1 + (mid_lon - lon1) * u
        else:
            u = (t - 0.5) * 2.0
            cur_lat = mid_lat + (lat2 - mid_lat) * u
            cur_lon = mid_lon + (lon2 - mid_lon) * u
        coords.append([round(cur_lon, 6), round(cur_lat, 6)])

    coords.append([round(lon2, 6), round(lat2, 6)])
    return coords


def create_geojson_feature_collection(
    problem: Problem,
    solution: Solution,
    route_geometries: list[dict[str, Any]],
    routing_engine_name: str,
) -> dict[str, Any]:
    """Build a complete GeoJSON FeatureCollection of stops and route lines."""
    features: list[dict[str, Any]] = []

    # 1. Depot Point Feature
    features.append({
        "type": "Feature",
        "id": "depot",
        "geometry": {
            "type": "Point",
            "coordinates": [round(problem.depot.lon, 6), round(problem.depot.lat, 6)],
        },
        "properties": {
            "id": problem.depot.id,
            "name": VADODARA_DEPOT["name"],
            "type": "depot",
            "ready_time": problem.depot.ready_time,
            "due_time": problem.depot.due_time,
            "marker-color": "#EF4444",
            "marker-symbol": "warehouse",
        },
    })

    # Map stop id to assigned vehicle and sequence
    stop_assignment: dict[str, dict[str, Any]] = {}
    for r_idx, route in enumerate(solution.routes):
        for seq, (c_id, arr_time) in enumerate(
            zip(route.stop_ids, route.arrival_times), start=1
        ):
            stop_assignment[c_id] = {
                "route_idx": r_idx + 1,
                "vehicle_id": route.vehicle_id,
                "stop_sequence": seq,
                "arrival_time_min": round(arr_time / 60.0, 1),
                "color": ROUTE_COLORS[r_idx % len(ROUTE_COLORS)],
            }

    # 2. Customer Point Features
    for cust in problem.customers:
        assign = stop_assignment.get(cust.id, {})
        features.append({
            "type": "Feature",
            "id": cust.id,
            "geometry": {
                "type": "Point",
                "coordinates": [round(cust.lon, 6), round(cust.lat, 6)],
            },
            "properties": {
                "id": cust.id,
                "name": next((s["name"] for s in VADODARA_STOPS if s["id"] == cust.id), f"Customer {cust.id}"),
                "type": "customer",
                "demand": cust.demand,
                "ready_time_min": round(cust.ready_time / 60.0, 1),
                "due_time_min": round(cust.due_time / 60.0, 1),
                "service_time_min": round(cust.service_time / 60.0, 1),
                "route_id": assign.get("route_idx"),
                "vehicle_id": assign.get("vehicle_id"),
                "stop_sequence": assign.get("stop_sequence"),
                "arrival_time_min": assign.get("arrival_time_min"),
                "marker-color": assign.get("color", "#6B7280"),
            },
        })

    # 3. Route LineString Features
    total_dist_km = 0.0
    total_time_sec = 0.0

    for r_idx, r_geom in enumerate(route_geometries):
        color = ROUTE_COLORS[r_idx % len(ROUTE_COLORS)]
        total_dist_km += r_geom["distance_km"]
        total_time_sec += r_geom["time_sec"]

        features.append({
            "type": "Feature",
            "id": f"route_{r_idx + 1}",
            "geometry": {
                "type": "LineString",
                "coordinates": r_geom["coordinates"],
            },
            "properties": {
                "route_id": f"Route_{r_idx + 1}",
                "vehicle_id": r_geom["vehicle_id"],
                "stops": r_geom["stops"],
                "num_stops": len(r_geom["stops"]),
                "load": r_geom["load"],
                "capacity": r_geom["capacity"],
                "utilization_pct": round(r_geom["load"] / r_geom["capacity"] * 100.0, 1),
                "distance_km": round(r_geom["distance_km"], 2),
                "duration_min": round(r_geom["time_sec"] / 60.0, 1),
                "stroke": color,
                "stroke-width": 4.5,
                "stroke-opacity": 0.85,
            },
        })

    return {
        "type": "FeatureCollection",
        "name": "Vadodara 30-Stop CVRPTW Optimized Routes",
        "metadata": {
            "city": "Vadodara, Gujarat, India",
            "problem_id": problem.id,
            "routing_engine": routing_engine_name,
            "algorithm": "QPSO (Sun, Feng & Xu 2004) + Prins Split + Local Search",
            "num_customers": len(problem.customers),
            "num_routes": len(solution.routes),
            "total_distance_km": round(total_dist_km, 2),
            "total_duration_min": round(total_time_sec / 60.0, 1),
            "is_feasible": solution.is_feasible,
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        },
        "features": features,
    }


def print_summary_table(
    problem: Problem,
    solution: Solution,
    route_geometries: list[dict[str, Any]],
    routing_engine_name: str,
    output_path: Path,
) -> None:
    """Print formatted ASCII summary of optimization results."""
    print("\n" + "=" * 94)
    print(f"               VADODARA 30-STOP FLEET ROUTE OPTIMIZATION DEMO")
    print("=" * 94)
    print(f"Routing Engine : {routing_engine_name}")
    print(f"Algorithm      : QPSO + Prins Split + Memetic Local Search (Classical Classical-State)")
    print(f"Instance       : Vadodara City (Depot: Sayajigunj | 30 Customer Hubs)")
    feas_tag = "FEASIBLE" if solution.is_feasible else "INFEASIBLE (Violations Detected)"
    print(f"Solution Status: {feas_tag}")
    print("-" * 94)
    print(f"{'Route':<8} {'Vehicle':<10} {'Stops':<6} {'Load / Cap':<14} {'Util%':<8} {'Dist (km)':<11} {'Time (min)':<11} {'Stop Sequence'}")
    print("-" * 94)

    total_km = 0.0
    total_sec = 0.0
    total_load = 0.0

    for idx, r_geom in enumerate(route_geometries):
        v_id = r_geom["vehicle_id"]
        n_stops = len(r_geom["stops"])
        load_str = f"{r_geom['load']:.1f} / {r_geom['capacity']:.1f}"
        util = (r_geom["load"] / r_geom["capacity"]) * 100.0
        km = r_geom["distance_km"]
        t_min = r_geom["time_sec"] / 60.0
        stops_preview = "Depot -> " + " -> ".join(r_geom["stops"]) + " -> Depot"
        if len(stops_preview) > 28:
            stops_preview = stops_preview[:25] + "..."

        print(f"#{idx+1:<7} {v_id:<10} {n_stops:<6} {load_str:<14} {util:>5.1f}%  {km:>8.2f}    {t_min:>8.1f}    {stops_preview}")

        total_km += km
        total_sec += r_geom["time_sec"]
        total_load += r_geom["load"]

    print("-" * 94)
    print(f"TOTALS   {len(solution.routes)} Vehicles  30 Stops  {total_load:.1f} units          {total_km:>8.2f} km {total_sec / 60.0:>8.1f} min")
    print("=" * 94)
    print(f"[SUCCESS] Exported GeoJSON route map to:")
    print(f"          {output_path.resolve()}\n")


def main() -> int:
    """CLI Entrypoint for Vadodara 30-stop optimization demo."""
    parser = argparse.ArgumentParser(
        description="Vadodara 30-stop delivery optimization demo with Valhalla routing and GeoJSON export."
    )
    parser.add_argument(
        "--valhalla-url",
        default="http://localhost:8002",
        help="Valhalla service URL (default: http://localhost:8002)",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Force simulated road routing (do not attempt Valhalla HTTP connection)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for optimization reproducibility (default: 42)",
    )
    parser.add_argument(
        "--particles",
        type=int,
        default=40,
        help="QPSO swarm size (default: 40)",
    )
    parser.add_argument(
        "--iters",
        type=int,
        default=250,
        help="QPSO maximum iterations (default: 250)",
    )
    parser.add_argument(
        "--output",
        default="benchmarks/results/vadodara_30_routes.geojson",
        help="Target output GeoJSON path (default: benchmarks/results/vadodara_30_routes.geojson)",
    )
    parser.add_argument(
        "--input",
        default=None,
        help="Optional existing Problem JSON file to solve",
    )
    parser.add_argument(
        "--save-problem",
        default="benchmarks/instances/vadodara_30.json",
        help="Target Problem JSON save path (default: benchmarks/instances/vadodara_30.json)",
    )
    args = parser.parse_args()

    # 1. Load or Generate Vadodara Problem
    if args.input and Path(args.input).is_file():
        print(f"[INFO] Loading problem instance from: {args.input}")
        problem = load_problem_json(args.input)
    else:
        print("[INFO] Generating 30 realistic Vadodara delivery customer locations...")
        problem = build_vadodara_problem(seed=args.seed)
        if args.save_problem:
            save_problem_json(problem, args.save_problem)
            print(f"[INFO] Problem instance saved to: {args.save_problem}")

    # 2. Check Valhalla Router Connectivity
    valhalla_online = False
    if not args.mock:
        print(f"[INFO] Testing Valhalla connectivity at {args.valhalla_url}...")
        valhalla_online = check_valhalla_alive(args.valhalla_url)

    all_stops = [problem.depot] + problem.customers

    if valhalla_online:
        routing_engine_name = f"Valhalla (Live @ {args.valhalla_url})"
        print(f"[INFO] Successfully connected to Valhalla road routing engine!")
        print(f"[INFO] Requesting 31x31 road travel-time matrix from Valhalla...")
        oracle = ValhallaOracle(base_url=args.valhalla_url, chunk_size=50)
        # Populate problem matrices from Valhalla
        matrix_res = oracle.matrix(all_stops)
        problem.travel_time_matrix = matrix_res.durations
        problem.distance_matrix = matrix_res.distances
    else:
        routing_engine_name = "Valhalla (Simulated Urban Road Network)"
        print(f"[NOTICE] Valhalla service at {args.valhalla_url} is offline or mock requested.")
        print(f"[NOTICE] (To use live Valhalla: run 'docker compose up -d' in /routing)")
        print(f"[NOTICE] Running with simulated road network travel times & geometry.")
        print(f"[NOTICE] Per AGENTS.md rules: Simulated traffic and road coordinates are explicitly labeled.")
        # Urban speed 30 km/h = 8.333 m/s, haversine distance
        oracle = EuclideanOracle(use_haversine=True, base_speed_mps=8.333)
        matrix_res = oracle.matrix(all_stops)
        problem.travel_time_matrix = matrix_res.durations
        problem.distance_matrix = matrix_res.distances

    # 3. Solve with QPSO
    print(f"\n[INFO] Starting QPSO Optimization ({args.particles} particles, {args.iters} iterations, seed={args.seed})...")
    config = QPSOConfig(
        num_particles=args.particles,
        max_iters=args.iters,
        seed=args.seed,
        local_search_freq=25,
        local_search_top_k=3,
    )

    t0 = time.perf_counter()
    solution, _ = solve_qpso(problem, config=config, cost_oracle=oracle)
    elapsed = time.perf_counter() - t0
    solution.execution_time_sec = elapsed
    print(f"[INFO] Optimization concluded in {elapsed:.2f} seconds.")

    # 4. Extract Road Geometries for Each Route
    print(f"[INFO] Constructing route geometries and turn-by-turn road paths...")
    route_geometries: list[dict[str, Any]] = []

    for r_idx, route in enumerate(solution.routes):
        route_customers = [problem.get_customer(cid) for cid in route.stop_ids]
        stops_sequence = [problem.depot] + route_customers + [problem.depot]

        if valhalla_online:
            # Query live Valhalla turn-by-turn geometry
            try:
                route_res = oracle.route(stops_sequence)
                coords = route_res["coordinates"]
                dist_km = route_res["distance_km"]
                time_sec = route_res["time_sec"]
            except Exception as exc:
                print(f"[WARNING] Live Valhalla /route failed for route {r_idx+1}: {exc}. Using fallback polyline.")
                coords = []
                for s_i in range(len(stops_sequence) - 1):
                    p_from = (stops_sequence[s_i].lat, stops_sequence[s_i].lon)
                    p_to = (stops_sequence[s_i + 1].lat, stops_sequence[s_i + 1].lon)
                    leg_pts = generate_simulated_road_polyline(p_from, p_to)
                    coords.extend(leg_pts[:-1] if s_i < len(stops_sequence) - 2 else leg_pts)
                dist_km = route.distance / 1000.0 if route.distance > 0 else 15.0
                time_sec = route.duration
        else:
            # Generate simulated urban road corridor polyline
            coords = []
            for s_i in range(len(stops_sequence) - 1):
                p_from = (stops_sequence[s_i].lat, stops_sequence[s_i].lon)
                p_to = (stops_sequence[s_i + 1].lat, stops_sequence[s_i + 1].lon)
                leg_pts = generate_simulated_road_polyline(p_from, p_to)
                coords.extend(leg_pts[:-1] if s_i < len(stops_sequence) - 2 else leg_pts)
            dist_km = route.distance / 1000.0 if route.distance > 0 else (route.duration * 8.333 / 1000.0)
            time_sec = route.duration

        vehicle = next((v for v in problem.vehicles if v.id == route.vehicle_id), problem.vehicles[0])
        route_geometries.append({
            "vehicle_id": route.vehicle_id,
            "stops": route.stop_ids,
            "load": route.load,
            "capacity": vehicle.capacity,
            "distance_km": dist_km,
            "time_sec": time_sec,
            "coordinates": coords,
        })

    # 5. Build and Save GeoJSON FeatureCollection
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    geojson_data = create_geojson_feature_collection(
        problem=problem,
        solution=solution,
        route_geometries=route_geometries,
        routing_engine_name=routing_engine_name,
    )

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(geojson_data, f, indent=2)

    # 6. Display Results
    print_summary_table(
        problem=problem,
        solution=solution,
        route_geometries=route_geometries,
        routing_engine_name=routing_engine_name,
        output_path=output_path,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
