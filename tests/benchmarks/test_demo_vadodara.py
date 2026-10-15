"""Unit tests for Vadodara 30-stop delivery demo script and GeoJSON generation.

Verifies:
1. Generation and validation of the 30-stop Vadodara CVRPTW problem instance.
2. End-to-end execution of demo_vadodara in mock / simulated mode.
3. GeoJSON FeatureCollection structure, stop points, and route line geometries.
4. Execution through the live Valhalla code path using a mocked HTTP service.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from benchmarks.demo_vadodara import (
    build_vadodara_problem,
    check_valhalla_alive,
    generate_simulated_road_polyline,
    main as demo_main,
)
from routing.cost_oracle import Location, encode_polyline


def test_build_vadodara_problem_structure() -> None:
    """Verify Vadodara problem instance has correct depot, customer count, and fleet capacity."""
    problem = build_vadodara_problem(seed=42)

    assert problem.id == "vadodara_30"
    assert problem.depot.id == "depot"
    # Vadodara city coordinates
    assert 22.20 <= problem.depot.lat <= 22.40
    assert 73.10 <= problem.depot.lon <= 73.30

    assert len(problem.customers) == 30
    assert len(problem.vehicles) == 8

    # Verify unique IDs
    cust_ids = [c.id for c in problem.customers]
    assert len(cust_ids) == len(set(cust_ids))

    # All customers must lie within Vadodara municipal boundaries
    for c in problem.customers:
        assert 22.24 <= c.lat <= 22.38
        assert 73.11 <= c.lon <= 73.25
        assert c.demand > 0.0
        assert c.ready_time <= c.due_time


def test_generate_simulated_road_polyline() -> None:
    """Verify simulated road polyline generates intermediate waypoints between GPS points."""
    p1 = (22.3108, 73.1811)
    p2 = (22.3245, 73.2050)

    polyline = generate_simulated_road_polyline(p1, p2, steps=6)

    # Should have start point, 5 intermediate points, and end point = 7 points
    assert len(polyline) == 7
    # First point: [lon1, lat1]
    assert polyline[0][0] == pytest.approx(p1[1], abs=1e-5)
    assert polyline[0][1] == pytest.approx(p1[0], abs=1e-5)
    # Last point: [lon2, lat2]
    assert polyline[-1][0] == pytest.approx(p2[1], abs=1e-5)
    assert polyline[-1][1] == pytest.approx(p2[0], abs=1e-5)


def test_demo_main_execution_simulated_mode(tmp_path: Path) -> None:
    """Verify demo_vadodara runs end-to-end and outputs valid GeoJSON in simulated mode."""
    geojson_out = tmp_path / "vadodara_test_routes.geojson"
    problem_out = tmp_path / "vadodara_test_problem.json"

    test_args = [
        "demo_vadodara.py",
        "--mock",
        "--particles", "10",
        "--iters", "15",
        "--seed", "42",
        "--output", str(geojson_out),
        "--save-problem", str(problem_out),
    ]

    with patch("sys.argv", test_args):
        ret_code = demo_main()

    assert ret_code == 0
    assert problem_out.is_file()
    assert geojson_out.is_file()

    # Validate output GeoJSON
    with geojson_out.open("r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["type"] == "FeatureCollection"
    assert data["metadata"]["city"] == "Vadodara, Gujarat, India"
    assert data["metadata"]["num_customers"] == 30
    assert data["metadata"]["is_feasible"] is True

    # Check features
    features = data["features"]
    points = [f for f in features if f["geometry"]["type"] == "Point"]
    linestrings = [f for f in features if f["geometry"]["type"] == "LineString"]

    # 1 depot + 30 customers = 31 points
    assert len(points) == 31
    assert len(linestrings) >= 1

    # Check depot point
    depot_feat = next(f for f in points if f["properties"]["type"] == "depot")
    assert depot_feat["properties"]["name"] is not None

    # Check a LineString feature
    first_route = linestrings[0]
    assert "route_id" in first_route["properties"]
    assert "load" in first_route["properties"]
    assert "distance_km" in first_route["properties"]
    assert len(first_route["geometry"]["coordinates"]) >= 2


def test_demo_main_execution_mocked_valhalla_live_mode(tmp_path: Path) -> None:
    """Verify demo_vadodara routes through live Valhalla codepath when service responds."""
    geojson_out = tmp_path / "vadodara_valhalla_routes.geojson"
    problem_out = tmp_path / "vadodara_valhalla_problem.json"

    # Mock matrix response (31 x 31 stops)
    mock_matrix = []
    for _ in range(31):
        row = []
        for _ in range(31):
            row.append({"time": 300.0, "distance": 3.5})
        mock_matrix.append(row)

    mock_matrix_resp = MagicMock()
    mock_matrix_resp.status = 200
    mock_matrix_resp.read.return_value = json.dumps({"sources_to_targets": mock_matrix}).encode("utf-8")
    mock_matrix_resp.__enter__.return_value = mock_matrix_resp

    # Mock route response
    shape = encode_polyline([(22.3108, 73.1811), (22.3150, 73.1850), (22.3200, 73.1900)])
    mock_route_resp = MagicMock()
    mock_route_resp.status = 200
    mock_route_resp.read.return_value = json.dumps({
        "trip": {
            "summary": {"length": 5.2, "time": 450.0},
            "legs": [{"shape": shape}],
        }
    }).encode("utf-8")
    mock_route_resp.__enter__.return_value = mock_route_resp

    test_args = [
        "demo_vadodara.py",
        "--valhalla-url", "http://localhost:8002",
        "--particles", "10",
        "--iters", "10",
        "--seed", "42",
        "--output", str(geojson_out),
        "--save-problem", str(problem_out),
    ]

    def custom_urlopen(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "/status" in url:
            resp = MagicMock()
            resp.status = 200
            resp.__enter__.return_value = resp
            return resp
        elif "/sources_to_targets" in url:
            return mock_matrix_resp
        elif "/route" in url:
            return mock_route_resp
        return MagicMock(status=200)

    with patch("benchmarks.demo_vadodara.check_valhalla_alive", return_value=True), \
         patch("urllib.request.urlopen", side_effect=custom_urlopen), \
         patch("sys.argv", test_args):
        ret_code = demo_main()

    assert ret_code == 0
    assert geojson_out.is_file()

    with geojson_out.open("r", encoding="utf-8") as f:
        data = json.load(f)

    assert "Valhalla (Live @" in data["metadata"]["routing_engine"]
