"""GeoJSON FeatureCollection builder for Route.it API and MapLibre GL Dashboard.

Converts CVRPTW Problem and Solution into standard RFC 7946 GeoJSON
containing LineString routes with vehicle metrics and Point stops with ETAs.
"""

from __future__ import annotations

from typing import Any
from routing.cost_oracle import CostOracle, ValhallaOracle
from solver.models import Customer, Depot, Problem, Route, Solution

# Curated palette for multi-vehicle visualization on dark / light MapLibre GL canvases
ROUTE_PALETTE = [
    "#3B82F6",  # Blue
    "#10B981",  # Emerald
    "#F59E0B",  # Amber
    "#EF4444",  # Rose
    "#8B5CF6",  # Violet
    "#EC4899",  # Pink
    "#06B6D4",  # Cyan
    "#84CC16",  # Lime
    "#F97316",  # Orange
    "#6366F1",  # Indigo
]


def solution_to_geojson(
    problem: Problem,
    solution: Solution,
    cost_oracle: CostOracle | None = None,
    current_time: float = 0.0,
) -> dict[str, Any]:
    """Generate a standard GeoJSON FeatureCollection for a routing solution.

    Args:
        problem: Problem instance with depot and customer coordinates.
        solution: Solution containing vehicle routes and arrival times.
        cost_oracle: Optional CostOracle for road-following geometries (Valhalla).
        current_time: Simulation timestamp to flag visited vs upcoming stops.

    Returns:
        GeoJSON FeatureCollection dict.
    """
    features: list[dict[str, Any]] = []

    # Map customers by ID
    cust_map: dict[str, Customer] = {c.id: c for c in problem.customers}

    # Stop service tracker: customer_id -> (vehicle_id, arrival_time)
    service_info: dict[str, tuple[str, float]] = {}

    # 1. Build Route LineString Features
    for r_idx, route in enumerate(solution.routes):
        if not route.stop_ids:
            continue

        color = ROUTE_PALETTE[r_idx % len(ROUTE_PALETTE)]

        # Collect sequence of waypoints: Depot -> stops... -> Depot
        waypoints: list[tuple[float, float]] = [(problem.depot.lat, problem.depot.lon)]
        for sid in route.stop_ids:
            c = cust_map.get(sid)
            if c is not None:
                waypoints.append((c.lat, c.lon))
        waypoints.append((problem.depot.lat, problem.depot.lon))

        coords: list[list[float]] = []

        # Attempt high-fidelity road polyline from Valhalla if available
        if isinstance(cost_oracle, ValhallaOracle):
            try:
                # Query route segments
                valhalla_coords: list[list[float]] = []
                for i in range(len(waypoints) - 1):
                    orig_pt = waypoints[i]
                    dest_pt = waypoints[i + 1]
                    res = cost_oracle.route(orig_pt, dest_pt)
                    if res.shape:
                        for lat, lon in res.shape:
                            valhalla_coords.append([round(lon, 6), round(lat, 6)])
                    else:
                        valhalla_coords.append([round(orig_pt[1], 6), round(orig_pt[0], 6)])
                        valhalla_coords.append([round(dest_pt[1], 6), round(dest_pt[0], 6)])
                coords = valhalla_coords
            except Exception:
                coords = [[round(lon, 6), round(lat, 6)] for lat, lon in waypoints]
        else:
            # Planar / Euclidean straight segment coordinates [lon, lat]
            coords = [[round(lon, 6), round(lat, 6)] for lat, lon in waypoints]

        features.append(
            {
                "type": "Feature",
                "id": f"route_{route.vehicle_id}",
                "geometry": {
                    "type": "LineString",
                    "coordinates": coords,
                },
                "properties": {
                    "feature_type": "route",
                    "vehicle_id": route.vehicle_id,
                    "route_index": r_idx,
                    "stop_ids": route.stop_ids,
                    "stop_count": len(route.stop_ids),
                    "arrival_times": route.arrival_times,
                    "load": route.load,
                    "distance_m": route.distance,
                    "duration_sec": route.duration,
                    "color": color,
                },
            }
        )

        for sid, arr in zip(route.stop_ids, route.arrival_times):
            service_info[sid] = (route.vehicle_id, arr)

    # 2. Build Depot Point Feature
    features.append(
        {
            "type": "Feature",
            "id": "depot",
            "geometry": {
                "type": "Point",
                "coordinates": [round(problem.depot.lon, 6), round(problem.depot.lat, 6)],
            },
            "properties": {
                "feature_type": "depot",
                "id": problem.depot.id,
                "name": "Central Depot",
                "ready_time": problem.depot.ready_time,
                "due_time": problem.depot.due_time,
                "service_time": problem.depot.service_time,
            },
        }
    )

    # 3. Build Customer Stop Point Features
    for cust in problem.customers:
        assigned_v, arr_time = service_info.get(cust.id, ("unassigned", 0.0))
        is_visited = current_time >= (arr_time + cust.service_time) if assigned_v != "unassigned" else False
        is_imminent = (arr_time - current_time) >= 0 and (arr_time - current_time) <= 300.0

        features.append(
            {
                "type": "Feature",
                "id": f"stop_{cust.id}",
                "geometry": {
                    "type": "Point",
                    "coordinates": [round(cust.lon, 6), round(cust.lat, 6)],
                },
                "properties": {
                    "feature_type": "customer",
                    "id": cust.id,
                    "demand": cust.demand,
                    "ready_time": cust.ready_time,
                    "due_time": cust.due_time,
                    "service_time": cust.service_time,
                    "priority": cust.priority,
                    "vehicle_id": assigned_v,
                    "arrival_time": round(arr_time, 2) if assigned_v != "unassigned" else None,
                    "is_visited": is_visited,
                    "is_imminent": is_imminent,
                },
            }
        )

    return {
        "type": "FeatureCollection",
        "features": features,
    }
