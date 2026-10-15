"""Unit tests for Route.it Cost Oracle, Traffic Adapters, and Caching Subsystem.

Verifies:
1. Abstract and Euclidean cost oracle logic.
2. InMemoryLRUCache and SQLiteCache behavior, time bucketing, and hit/miss metrics.
3. TrafficAdapter hierarchy (TimeOfDayProfileAdapter, SimulatedEventAdapter, ProviderAdapter).
4. Time-dependent sequential route evaluation where stop arrival depends on previous departure.
5. ValhallaOracle chunking and error handling with a mocked HTTP client (no network in regular unit tests).
6. Optional integration test marked with @pytest.mark.integration.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
import urllib.error
import pytest

from routing.cost_oracle import (
    CacheStats,
    CostCache,
    CostOracle,
    EuclideanOracle,
    InMemoryLRUCache,
    Location,
    MatrixResult,
    ProviderAdapter,
    RouteTimeline,
    SimulatedEventAdapter,
    SimulatedIncident,
    SQLiteCache,
    StopTimeline,
    TimeOfDayProfileAdapter,
    TrafficAdapter,
    ValhallaOracle,
    decode_polyline,
    encode_polyline,
    to_location,
)
from solver.models import Customer, Depot


# ---------------------------------------------------------------------------
# 1. Location Coercion Tests
# ---------------------------------------------------------------------------

def test_to_location_from_various_inputs() -> None:
    """Verify to_location parses Location, Depot, Customer, dict, and tuple."""
    loc1 = Location(id="loc1", lat=22.3, lon=73.2)
    assert to_location(loc1) == loc1

    depot = Depot(id="depot_0", lat=22.3108, lon=73.1811)
    loc_depot = to_location(depot)
    assert loc_depot.id == "depot_0"
    assert loc_depot.lat == pytest.approx(22.3108)
    assert loc_depot.lon == pytest.approx(73.1811)

    customer = Customer(
        id="c1",
        lat=22.3129,
        lon=73.1906,
        demand=5.0,
        ready_time=0.0,
        due_time=100.0,
        service_time=10.0,
    )
    loc_cust = to_location(customer)
    assert loc_cust.id == "c1"
    assert loc_cust.lat == pytest.approx(22.3129)

    dict_loc = to_location({"id": "d1", "lat": 22.0, "lon": 73.0})
    assert dict_loc.id == "d1"

    tuple_loc = to_location(("t1", 22.1, 73.1))
    assert tuple_loc.id == "t1"

    with pytest.raises(TypeError):
        to_location(12345)


# ---------------------------------------------------------------------------
# 2. Euclidean Oracle Tests
# ---------------------------------------------------------------------------

def test_euclidean_oracle_planar_and_haversine() -> None:
    """Verify distance and duration calculation under planar and haversine modes."""
    # Haversine in Vadodara (~1 km between station and Sayaji Baug)
    p1 = Location(id="stn", lat=22.3108, lon=73.1811)
    p2 = Location(id="park", lat=22.3129, lon=73.1906)

    oracle = EuclideanOracle(base_speed_mps=10.0, use_haversine=True)
    dist = oracle.distance(p1, p2)
    assert 900.0 < dist < 1200.0  # Approx 1 km

    time_sec = oracle.travel_time(p1, p2, depart_time=0.0)
    assert time_sec == pytest.approx(dist / 10.0)

    # Self distance is 0
    assert oracle.distance(p1, p1) == 0.0
    assert oracle.travel_time(p1, p1) == 0.0


def test_euclidean_oracle_matrix_generation() -> None:
    """Verify EuclideanOracle matrix computes correct NxN matrices and unpacks."""
    points = [
        Location(id="p0", lat=22.310, lon=73.180),
        Location(id="p1", lat=22.320, lon=73.180),
        Location(id="p2", lat=22.310, lon=73.190),
    ]
    oracle = EuclideanOracle(base_speed_mps=10.0)
    result = oracle.matrix(points, depart_time=0.0)

    assert len(result.durations) == 3
    assert len(result.distances) == 3

    # Check zero diagonal
    for i in range(3):
        assert result.durations[i][i] == 0.0
        assert result.distances[i][i] == 0.0

    # Symmetry
    assert result.distances[0][1] == pytest.approx(result.distances[1][0])
    assert result.durations[0][2] == pytest.approx(result.durations[2][0])

    # Unpack support
    durs, dists = oracle.matrix(points)
    assert durs == result.durations
    assert dists == result.distances


# ---------------------------------------------------------------------------
# 3. Caching Subsystem Tests
# ---------------------------------------------------------------------------

def test_in_memory_lru_cache() -> None:
    """Verify LRU cache stores, retrieves, respects max size, and tracks stats."""
    cache = InMemoryLRUCache(max_size=3, bucket_size_seconds=900.0)

    # Time bucket check: 0s -> 0, 899s -> 0, 901s -> 1
    assert cache.get_time_bucket(0.0) == 0
    assert cache.get_time_bucket(899.9) == 0
    assert cache.get_time_bucket(900.0) == 1

    # Insert items
    cache.set("a", "b", 0, 100.0, 1000.0)
    cache.set("b", "c", 0, 200.0, 2000.0)
    cache.set("c", "d", 0, 300.0, 3000.0)

    # Lookup hit
    res = cache.get("a", "b", 0)
    assert res == (100.0, 1000.0)
    assert cache.stats.hits == 1

    # Lookup miss (wrong time bucket or unknown pair)
    assert cache.get("a", "b", 1) is None
    assert cache.get("x", "y", 0) is None
    assert cache.stats.misses == 2
    assert cache.stats.hit_ratio == pytest.approx(1 / 3)

    # Eviction test: Add 4th item, oldest ("b", "c") should be evicted because ("a", "b") was recently accessed
    cache.set("d", "e", 0, 400.0, 4000.0)
    assert cache.get("b", "c", 0) is None  # Evicted
    assert cache.get("a", "b", 0) == (100.0, 1000.0)  # Preserved

    cache.clear()
    assert cache.stats.hits == 0
    assert cache.stats.misses == 0
    assert cache.get("a", "b", 0) is None


def test_sqlite_cache() -> None:
    """Verify SQLiteCache persistence and lookup semantics."""
    cache = SQLiteCache(db_path=":memory:", bucket_size_seconds=600.0)

    cache.set("orig1", "dest1", 5, 45.0, 500.0)
    assert cache.get("orig1", "dest1", 5) == (45.0, 500.0)
    assert cache.stats.hits == 1

    # Miss
    assert cache.get("orig1", "dest1", 6) is None
    assert cache.stats.misses == 1

    # Overwrite / update
    cache.set("orig1", "dest1", 5, 55.0, 500.0)
    assert cache.get("orig1", "dest1", 5) == (55.0, 500.0)

    cache.clear()
    assert cache.get("orig1", "dest1", 5) is None


# ---------------------------------------------------------------------------
# 4. Traffic Adapters Tests
# ---------------------------------------------------------------------------

def test_time_of_day_profile_adapter() -> None:
    """Verify simulated time-of-day speed multipliers (Ichoua et al. 2003 model)."""
    adapter = TimeOfDayProfileAdapter()
    p1 = Location(id="p1", lat=22.3, lon=73.2)
    p2 = Location(id="p2", lat=22.4, lon=73.3)

    # 02:00 AM (night) -> 1.15
    night_time = 2 * 3600.0
    assert adapter.get_speed_multiplier(p1, p2, night_time) == pytest.approx(1.15)

    # 08:30 AM (morning rush) -> 0.65
    rush_am = 8.5 * 3600.0
    assert adapter.get_speed_multiplier(p1, p2, rush_am) == pytest.approx(0.65)

    # 17:00 PM (evening rush) -> 0.60
    rush_pm = 17 * 3600.0
    assert adapter.get_speed_multiplier(p1, p2, rush_pm) == pytest.approx(0.60)

    # Custom profile validation
    with pytest.raises(ValueError):
        TimeOfDayProfileAdapter({25: 1.0})
    with pytest.raises(ValueError):
        TimeOfDayProfileAdapter({10: -0.5})


def test_simulated_event_adapter_slowdown_and_blockage() -> None:
    """Verify runtime incident injection with slowdowns and blockages."""
    event_adapter = SimulatedEventAdapter()
    p1 = Location(id="orig", lat=22.310, lon=73.180)
    p2 = Location(id="dest", lat=22.320, lon=73.180)

    # Normal time-of-day multiplier at 12:00 PM is 0.90
    noon = 12 * 3600.0
    assert event_adapter.get_speed_multiplier(p1, p2, noon) == pytest.approx(0.90)

    # Add 80% slowdown incident (multiplier 0.2) between 11:30 and 13:00 on this OD pair
    incident = SimulatedIncident(
        event_id="inc_01",
        speed_multiplier=0.2,
        start_time=11.5 * 3600.0,
        end_time=13.0 * 3600.0,
        origin_id="orig",
        dest_id="dest",
        description="Pothole repair on MG Road",
    )
    event_adapter.add_incident(incident)

    # Within incident window -> multiplier drops to 0.2
    assert event_adapter.get_speed_multiplier(p1, p2, noon) == pytest.approx(0.20)

    # Non-matching pair -> unaffected
    p3 = Location(id="other", lat=22.350, lon=73.200)
    assert event_adapter.get_speed_multiplier(p1, p3, noon) == pytest.approx(0.90)

    # After incident end (14:00 PM) -> returns to normal midday
    assert event_adapter.get_speed_multiplier(p1, p2, 14.0 * 3600.0) == pytest.approx(0.90)

    # Test full blockage (multiplier 0.0)
    blockage = SimulatedIncident(
        event_id="inc_block",
        speed_multiplier=0.0,
        start_time=noon,
        end_time=noon + 1800.0,
        origin_id="orig",
        dest_id="dest",
    )
    event_adapter.add_incident(blockage)
    assert event_adapter.get_speed_multiplier(p1, p2, noon + 60.0) == 0.0

    # Under oracle, blockage yields infinite travel time
    oracle = EuclideanOracle(traffic_adapter=event_adapter)
    assert oracle.travel_time(p1, p2, depart_time=noon + 60.0) == float("inf")

    # Remove incident
    event_adapter.remove_incident("inc_block")
    assert oracle.travel_time(p1, p2, depart_time=noon + 60.0) < float("inf")


def test_provider_adapter_stub() -> None:
    """Verify ProviderAdapter logs notice and raises if unintegrated."""
    stub = ProviderAdapter(provider_name="tomtom")
    p1 = Location(id="p1", lat=22.0, lon=73.0)
    p2 = Location(id="p2", lat=22.1, lon=73.1)

    # Without api key -> returns 1.0 baseline
    assert stub.get_speed_multiplier(p1, p2, 0.0) == 1.0

    # With api key -> raises NotImplementedError documenting live connection requirement
    live_stub = ProviderAdapter(provider_name="google_routes", api_key="secret_key")
    with pytest.raises(NotImplementedError):
        live_stub.get_speed_multiplier(p1, p2, 0.0)


# ---------------------------------------------------------------------------
# 5. Time-Dependent Route Evaluation Tests
# ---------------------------------------------------------------------------

def test_evaluate_route_sequential_arrival_chain() -> None:
    """Verify that arrival at stop k depends on actual departure from stop k-1."""
    # 3 stops: depot (0.0, 0.0), stop 1 (1.0, 0.0), stop 2 (2.0, 0.0)
    stops = [
        Location(id="depot", lat=0.0, lon=0.0),
        Location(id="stop1", lat=1.0, lon=0.0),
        Location(id="stop2", lat=2.0, lon=0.0),
    ]
    # Speed 1.0 unit/s -> 1 unit = 1 sec travel time per leg
    oracle = EuclideanOracle(base_speed_mps=1.0, use_haversine=False)


    service_times = [0.0, 5.0, 10.0]  # depot: 0, stop1: 5s, stop2: 10s
    ready_times = [0.0, 3.0, 0.0]     # stop1 ready at t=3s

    # Start at t=0.0
    timeline = oracle.evaluate_route(
        stops,
        start_time=0.0,
        service_times=service_times,
        ready_times=ready_times,
    )

    assert len(timeline.stops) == 3

    # Depot: departs at 0.0
    st0 = timeline.stops[0]
    assert st0.arrival_time == 0.0
    assert st0.departure_time == 0.0

    # Stop 1: leg time is 1.0s. Arrives at 1.0s.
    # Ready time is 3.0s -> wait time is 2.0s!
    # Service starts at 3.0s, takes 5.0s -> Departs at 8.0s!
    st1 = timeline.stops[1]
    assert st1.travel_time_from_prev == pytest.approx(1.0)
    assert st1.arrival_time == pytest.approx(1.0)
    assert st1.wait_time == pytest.approx(2.0)
    assert st1.service_start_time == pytest.approx(3.0)
    assert st1.departure_time == pytest.approx(8.0)

    # Stop 2: leg time is 1.0s. Departs stop 1 at 8.0s -> Arrives at 9.0s!
    # Service takes 10.0s -> Departs at 19.0s.
    st2 = timeline.stops[2]
    assert st2.arrival_time == pytest.approx(9.0)
    assert st2.departure_time == pytest.approx(19.0)

    assert timeline.total_travel_time == pytest.approx(2.0)
    assert timeline.total_duration == pytest.approx(19.0)
    assert timeline.total_wait_time == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# 6. Valhalla Oracle Tests (Mocked Network & Chunking)
# ---------------------------------------------------------------------------

def test_valhalla_oracle_single_query_mocked() -> None:
    """Verify ValhallaOracle single OD query parses time and distance properly."""
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = json.dumps({
        "sources_to_targets": [
            [{"time": 150.0, "distance": 2.5}]  # 2.5 km -> 2500 m
        ]
    }).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    p1 = Location(id="s1", lat=22.31, lon=73.18)
    p2 = Location(id="s2", lat=22.32, lon=73.19)

    oracle = ValhallaOracle(base_url="http://localhost:8002")

    with patch("urllib.request.urlopen", return_value=mock_resp):
        time_sec = oracle.travel_time(p1, p2)
        dist_m = oracle.distance(p1, p2)

    assert time_sec == 150.0
    assert dist_m == 2500.0


def test_valhalla_oracle_chunked_matrix() -> None:
    """Verify ValhallaOracle breaks 4x4 matrix into 2x2 blocks when chunk_size=2."""
    points = [
        Location(id=f"loc_{i}", lat=22.30 + i * 0.01, lon=73.18 + i * 0.01)
        for i in range(4)
    ]

    cache = InMemoryLRUCache()
    oracle = ValhallaOracle(
        base_url="http://localhost:8002",
        chunk_size=2,  # Forces 4 submatrix queries: (0..1, 0..1), (0..1, 2..3), (2..3, 0..1), (2..3, 2..3)
        cache=cache,
    )

    def mock_urlopen(req, timeout):
        payload = json.loads(req.data.decode("utf-8"))
        num_src = len(payload["sources"])
        num_tgt = len(payload["targets"])
        assert num_src <= 2
        assert num_tgt <= 2

        # Return mock block matrix
        block = []
        for s in payload["sources"]:
            row = []
            for t in payload["targets"]:
                row.append({"time": 60.0, "distance": 1.0})
            block.append(row)

        resp = MagicMock()
        resp.status = 200
        resp.read.return_value = json.dumps({"sources_to_targets": block}).encode("utf-8")
        resp.__enter__.return_value = resp
        return resp

    with patch("urllib.request.urlopen", side_effect=mock_urlopen) as mock_call:
        res = oracle.matrix(points, depart_time=100.0)
        # Should have made 4 calls (2 chunks for src x 2 chunks for tgt)
        assert mock_call.call_count == 4

    assert len(res.durations) == 4
    assert len(res.distances) == 4

    # Diagonal is zero
    for i in range(4):
        assert res.durations[i][i] == 0.0
        assert res.distances[i][i] == 0.0

    # Off-diagonal
    assert res.durations[0][1] == 60.0
    assert res.distances[0][1] == 1000.0  # 1.0 km -> 1000 m

    # Second call with the same depart_time should be 100% cache hits (no urlopen calls)
    with patch("urllib.request.urlopen") as mock_second_call:
        res2 = oracle.matrix(points, depart_time=100.0)
        assert mock_second_call.call_count == 0
        assert res2.durations == res.durations


def test_valhalla_oracle_connection_error() -> None:
    """Verify ValhallaOracle raises ConnectionError when server is unreachable."""
    oracle = ValhallaOracle(base_url="http://127.0.0.1:59999", timeout=0.1)
    p1 = Location(id="s1", lat=22.3, lon=73.1)
    p2 = Location(id="s2", lat=22.4, lon=73.2)

    with pytest.raises(ConnectionError) as exc_info:
        oracle.travel_time(p1, p2)

    assert "Failed to query Valhalla matrix endpoint" in str(exc_info.value)


def test_polyline_encode_decode_roundtrip() -> None:
    """Verify polyline encoding and decoding round-trip preserves precision."""
    original = [(22.3108, 73.1811), (22.3129, 73.1906), (22.3250, 73.2010)]
    encoded = encode_polyline(original, precision=1e6)
    decoded = decode_polyline(encoded, precision=1e6)
    assert len(decoded) == len(original)
    for (lat1, lon1), (lat2, lon2) in zip(original, decoded):
        assert lat1 == pytest.approx(lat2, abs=1e-5)
        assert lon1 == pytest.approx(lon2, abs=1e-5)


def test_valhalla_oracle_route_mocked() -> None:
    """Verify ValhallaOracle.route parses trip geometry and returns GeoJSON coordinates."""
    coords = [(22.3108, 73.1811), (22.3120, 73.1850), (22.3129, 73.1906)]
    shape = encode_polyline(coords, precision=1e6)
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = json.dumps({
        "trip": {
            "summary": {"length": 1.2, "time": 180.0},
            "legs": [{"shape": shape}],
        }
    }).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    oracle = ValhallaOracle(base_url="http://localhost:8002")
    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = oracle.route([Location(id="s", lat=coords[0][0], lon=coords[0][1]),
                           Location(id="t", lat=coords[-1][0], lon=coords[-1][1])])

    assert res["distance_km"] == 1.2
    assert res["time_sec"] == 180.0
    assert len(res["coordinates"]) == 3
    # In GeoJSON: [longitude, latitude]
    assert res["coordinates"][0][0] == pytest.approx(73.1811, abs=1e-5)
    assert res["coordinates"][0][1] == pytest.approx(22.3108, abs=1e-5)


# ---------------------------------------------------------------------------
# 7. Optional Integration Test
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_valhalla_live_docker_integration() -> None:
    """Optional live integration test against running Valhalla Docker instance."""
    import urllib.request

    status_url = "http://localhost:8002/status"
    try:
        req = urllib.request.Request(status_url)
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            if resp.status != 200:
                pytest.skip("Valhalla Docker instance not responding with 200")
    except Exception:
        pytest.skip("Local Valhalla service is offline (Docker container not running)")

    # If reached, Valhalla is running live: test real matrix
    p1 = Location(id="stn", lat=22.3108, lon=73.1811)
    p2 = Location(id="park", lat=22.3129, lon=73.1906)

    oracle = ValhallaOracle(base_url="http://localhost:8002")
    tt = oracle.travel_time(p1, p2)
    dist = oracle.distance(p1, p2)

    assert 60.0 < tt < 600.0
    assert 500.0 < dist < 3000.0
