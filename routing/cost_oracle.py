"""Route.it Cost Oracle and Traffic Engine.

INTEGRITY / SIMULATION NOTICE:
------------------------------
Unless an authentic commercial or enterprise traffic provider adapter
(such as TomTom Routing API, Google Maps Platform, or HERE Traffic) is explicitly
configured, ALL traffic dynamics, speed profiles, and event slowdowns in this module
are SIMULATED (based on the time-of-day profile models of Ichoua et al. 2003
or synthetic runtime incident injections).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import OrderedDict
from dataclasses import dataclass, field
import json
import logging
import math
import os
import sqlite3
import threading
import time
from typing import Any, Callable, Literal, Sequence
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Location & Domain Data Structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Location:
    """Geographic or planar location representation."""

    id: str
    lat: float
    lon: float


def to_location(loc: Any) -> Location:
    """Coerce various location-like inputs into a canonical Location.

    Supports:
    - Location instances
    - Objects with .id, .lat, .lon attributes (e.g., solver.models.Depot, Customer)
    - Dicts: {"id": str, "lat": float, "lon": float}
    - Tuples: (id, lat, lon)
    """
    if isinstance(loc, Location):
        return loc
    if hasattr(loc, "id") and hasattr(loc, "lat") and hasattr(loc, "lon"):
        return Location(id=str(loc.id), lat=float(loc.lat), lon=float(loc.lon))
    if isinstance(loc, dict):
        return Location(
            id=str(loc.get("id", f"loc_{loc['lat']}_{loc['lon']}")),
            lat=float(loc["lat"]),
            lon=float(loc["lon"]),
        )
    if isinstance(loc, (tuple, list)) and len(loc) == 3:
        return Location(id=str(loc[0]), lat=float(loc[1]), lon=float(loc[2]))
    raise TypeError(f"Cannot coerce {type(loc)} to Location: {loc!r}")


@dataclass
class MatrixResult:
    """Distance and duration matrices for a set of points."""

    durations: list[list[float]]  # [N][N] in seconds
    distances: list[list[float]]  # [N][N] in metres

    def __iter__(self):
        """Allow tuple unpacking: durations, distances = result."""
        return iter((self.durations, self.distances))


@dataclass
class StopTimeline:
    """Timeline metrics for a single visited stop in a route."""

    stop_id: str
    arrival_time: float
    service_start_time: float
    departure_time: float
    wait_time: float
    travel_time_from_prev: float
    distance_from_prev: float
    lateness: float


@dataclass
class RouteTimeline:
    """Complete time-dependent evaluation of a multi-stop vehicle route."""

    stops: list[StopTimeline]
    total_travel_time: float
    total_distance: float
    total_duration: float
    total_wait_time: float
    total_lateness: float


# ---------------------------------------------------------------------------
# Caching Subsystem
# ---------------------------------------------------------------------------

@dataclass
class CacheStats:
    """Hit and miss statistics for cost caches."""

    hits: int = 0
    misses: int = 0

    @property
    def total_lookups(self) -> int:
        return self.hits + self.misses

    @property
    def hit_ratio(self) -> float:
        if self.total_lookups == 0:
            return 0.0
        return self.hits / self.total_lookups


class CostCache(ABC):
    """Abstract interface for travel-time and distance caching."""

    def __init__(self, bucket_size_seconds: float = 900.0) -> None:
        """Initialize cache.

        Args:
            bucket_size_seconds: Duration of time bucket in seconds (default: 15 min = 900s).
        """
        if bucket_size_seconds <= 0:
            raise ValueError("bucket_size_seconds must be positive")
        self.bucket_size_seconds = float(bucket_size_seconds)
        self.stats = CacheStats()

    def get_time_bucket(self, depart_time: float) -> int:
        """Map continuous departure timestamp to an integer bucket index."""
        return int(math.floor(depart_time / self.bucket_size_seconds))

    @abstractmethod
    def get(
        self, origin_id: str, dest_id: str, time_bucket: int
    ) -> tuple[float, float] | None:
        """Retrieve (duration_seconds, distance_metres) from cache."""
        ...

    @abstractmethod
    def set(
        self,
        origin_id: str,
        dest_id: str,
        time_bucket: int,
        duration: float,
        distance: float,
    ) -> None:
        """Store (duration_seconds, distance_metres) in cache."""
        ...

    @abstractmethod
    def clear(self) -> None:
        """Clear all cached entries and reset statistics."""
        ...


class InMemoryLRUCache(CostCache):
    """In-memory Least Recently Used (LRU) cost cache with hit/miss tracking."""

    def __init__(
        self,
        max_size: int = 50_000,
        bucket_size_seconds: float = 900.0,
    ) -> None:
        super().__init__(bucket_size_seconds=bucket_size_seconds)
        self.max_size = max_size
        self._store: OrderedDict[tuple[str, str, int], tuple[float, float]] = OrderedDict()

    def get(
        self, origin_id: str, dest_id: str, time_bucket: int
    ) -> tuple[float, float] | None:
        key = (origin_id, dest_id, time_bucket)
        if key in self._store:
            self._store.move_to_end(key)
            self.stats.hits += 1
            return self._store[key]
        self.stats.misses += 1
        return None

    def set(
        self,
        origin_id: str,
        dest_id: str,
        time_bucket: int,
        duration: float,
        distance: float,
    ) -> None:
        key = (origin_id, dest_id, time_bucket)
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = (float(duration), float(distance))
        if len(self._store) > self.max_size:
            self._store.popitem(last=False)

    def clear(self) -> None:
        self._store.clear()
        self.stats.hits = 0
        self.stats.misses = 0


class SQLiteCache(CostCache):
    """Persistent or in-memory SQLite-backed cost cache."""

    def __init__(
        self,
        db_path: str = ":memory:",
        bucket_size_seconds: float = 900.0,
    ) -> None:
        super().__init__(bucket_size_seconds=bucket_size_seconds)
        self.db_path = db_path
        self._conn = sqlite3.connect(self.db_path)
        self._create_table()

    def _create_table(self) -> None:
        with self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cost_cache (
                    origin_id TEXT NOT NULL,
                    dest_id TEXT NOT NULL,
                    time_bucket INTEGER NOT NULL,
                    duration REAL NOT NULL,
                    distance REAL NOT NULL,
                    PRIMARY KEY (origin_id, dest_id, time_bucket)
                )
                """
            )

    def get(
        self, origin_id: str, dest_id: str, time_bucket: int
    ) -> tuple[float, float] | None:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT duration, distance FROM cost_cache
            WHERE origin_id = ? AND dest_id = ? AND time_bucket = ?
            """,
            (origin_id, dest_id, time_bucket),
        )
        row = cursor.fetchone()
        if row is not None:
            self.stats.hits += 1
            return (float(row[0]), float(row[1]))
        self.stats.misses += 1
        return None

    def set(
        self,
        origin_id: str,
        dest_id: str,
        time_bucket: int,
        duration: float,
        distance: float,
    ) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO cost_cache
                (origin_id, dest_id, time_bucket, duration, distance)
                VALUES (?, ?, ?, ?, ?)
                """,
                (origin_id, dest_id, time_bucket, float(duration), float(distance)),
            )

    def clear(self) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM cost_cache")
        self.stats.hits = 0
        self.stats.misses = 0


# ---------------------------------------------------------------------------
# Traffic Adapters (Simulated & Provider Stubs)
# ---------------------------------------------------------------------------

class TrafficAdapter(ABC):
    """Abstract interface for time-dependent traffic conditions.

    NOTICE: All sub-classes except authenticated ProviderAdapters generate
    SIMULATED traffic conditions.
    """

    @abstractmethod
    def get_speed_multiplier(
        self, origin: Location, dest: Location, depart_time: float
    ) -> float:
        """Return speed factor for a trip starting at depart_time.

        Multiplier semantics:
        - 1.0: Free-flow baseline speed.
        - 0.5: Half speed (travel time doubles).
        - 1.2: 20% faster than baseline (e.g. night).
        - 0.0: Full road blockage (travel time is infinite).

        Actual Travel Time = Baseline Travel Time / Speed Multiplier
        """
        ...


class TimeOfDayProfileAdapter(TrafficAdapter):
    """Simulated time-of-day speed multiplier profile.

    Based on the standard time-dependent VRP formulation of
    Ichoua, Gendreau & Potvin (2003): "A parallel tabu search heuristic for
    the dynamic and time-dependent vehicle routing problem with time windows".

    Default profile (seconds mapped to 24h day):
    - 00:00 - 06:00: 1.15 (light night traffic)
    - 06:00 - 08:00: 1.00 (standard morning flow)
    - 08:00 - 10:00: 0.65 (morning rush peak congestion)
    - 10:00 - 16:00: 0.90 (steady midday business flow)
    - 16:00 - 19:30: 0.60 (evening rush hour severe congestion)
    - 19:30 - 22:00: 0.85 (evening recovery)
    - 22:00 - 24:00: 1.10 (night flow)
    """

    DEFAULT_HOURLY_PROFILE: dict[int, float] = {
        0: 1.15, 1: 1.15, 2: 1.15, 3: 1.15, 4: 1.15, 5: 1.15,
        6: 1.00, 7: 1.00,
        8: 0.65, 9: 0.65,
        10: 0.90, 11: 0.90, 12: 0.90, 13: 0.90, 14: 0.90, 15: 0.90,
        16: 0.60, 17: 0.60, 18: 0.60, 19: 0.70,
        20: 0.85, 21: 0.85,
        22: 1.10, 23: 1.10,
    }

    def __init__(self, hourly_profile: dict[int, float] | None = None) -> None:
        """Initialize profile adapter.

        Args:
            hourly_profile: Optional dict mapping hour (0..23) to positive speed multiplier.
        """
        self.profile = (
            dict(hourly_profile) if hourly_profile is not None else dict(self.DEFAULT_HOURLY_PROFILE)
        )
        for h, v in self.profile.items():
            if not (0 <= h <= 23):
                raise ValueError(f"Invalid hour {h}; must be 0..23")
            if v <= 0:
                raise ValueError(f"Speed multiplier for hour {h} must be positive, got {v}")

    def get_speed_multiplier(
        self, origin: Location, dest: Location, depart_time: float
    ) -> float:
        """Retrieve simulated speed multiplier according to departure hour."""
        if not math.isfinite(depart_time):
            return 1.0
        day_seconds = depart_time % 86400.0
        hour = int(day_seconds // 3600)
        return self.profile.get(hour, 1.0)


@dataclass
class SimulatedIncident:
    """Dynamic traffic incident description."""

    event_id: str
    speed_multiplier: float  # e.g., 0.2 for 80% slowdown, 0.0 for blockage
    start_time: float
    end_time: float
    origin_id: str | None = None
    dest_id: str | None = None
    center_lat: float | None = None
    center_lon: float | None = None
    radius_meters: float | None = None
    description: str = ""


class SimulatedEventAdapter(TrafficAdapter):
    """Simulated runtime traffic event injector.

    Allows runtime injection of accidents, roadworks, and full corridor blockages
    for testing dynamic route re-planning.
    """

    def __init__(self, base_adapter: TrafficAdapter | None = None) -> None:
        """Initialize event adapter.

        Args:
            base_adapter: Underlying traffic adapter to modulate (default: TimeOfDayProfileAdapter).
        """
        self.base_adapter = base_adapter or TimeOfDayProfileAdapter()
        self._incidents: dict[str, SimulatedIncident] = {}

    def add_incident(self, incident: SimulatedIncident) -> None:
        """Register a runtime traffic incident."""
        if incident.speed_multiplier < 0.0:
            raise ValueError("speed_multiplier cannot be negative")
        if incident.start_time > incident.end_time:
            raise ValueError("incident start_time cannot exceed end_time")
        self._incidents[incident.event_id] = incident

    def remove_incident(self, event_id: str) -> None:
        """Remove an incident by ID."""
        self._incidents.pop(event_id, None)

    def clear_incidents(self) -> None:
        """Clear all active incidents."""
        self._incidents.clear()

    @property
    def active_incidents(self) -> list[SimulatedIncident]:
        return list(self._incidents.values())

    def _haversine_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Planar or haversine distance in metres."""
        r = 6371000.0  # Earth radius in metres
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlam = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2.0) ** 2
        return 2.0 * r * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

    def get_speed_multiplier(
        self, origin: Location, dest: Location, depart_time: float
    ) -> float:
        """Calculate combined speed multiplier including all active incidents."""
        base_multiplier = self.base_adapter.get_speed_multiplier(origin, dest, depart_time)
        effective_multiplier = base_multiplier

        for inc in self._incidents.values():
            if not (inc.start_time <= depart_time <= inc.end_time):
                continue

            applies = False
            # Check Origin-Destination match
            if inc.origin_id is not None or inc.dest_id is not None:
                matches_orig = inc.origin_id is None or inc.origin_id == origin.id
                matches_dest = inc.dest_id is None or inc.dest_id == dest.id
                if matches_orig and matches_dest:
                    applies = True

            # Check Geographic Radius match
            if inc.center_lat is not None and inc.center_lon is not None and inc.radius_meters is not None:
                dist_orig = self._haversine_distance(origin.lat, origin.lon, inc.center_lat, inc.center_lon)
                dist_dest = self._haversine_distance(dest.lat, dest.lon, inc.center_lat, inc.center_lon)
                if dist_orig <= inc.radius_meters or dist_dest <= inc.radius_meters:
                    applies = True

            if applies:
                if inc.speed_multiplier == 0.0:
                    return 0.0  # Total blockage
                effective_multiplier = min(effective_multiplier, inc.speed_multiplier)

        return effective_multiplier


class ProviderAdapter(TrafficAdapter):
    """Stub documentation adapter for authentic external traffic APIs.

    INTEGRITY NOTICE:
    This adapter serves as a defined hook for external commercial traffic APIs
    (e.g., TomTom Flow & Incidents, Google Distance Matrix with departure_time=now,
    HERE Real-Time Traffic).

    Without a valid commercial provider subscription, network credentials, and
    polling ingestion pipeline, Route.it operates in SIMULATED traffic mode.
    """

    def __init__(self, provider_name: str = "generic_provider", api_key: str | None = None) -> None:
        self.provider_name = provider_name
        self.api_key = api_key
        if not api_key:
            logger.warning(
                "ProviderAdapter [%s] initialized without API key. "
                "Operating under simulated baseline multiplier (1.0).",
                provider_name,
            )

    def get_speed_multiplier(
        self, origin: Location, dest: Location, depart_time: float
    ) -> float:
        """Hook for querying live traffic provider.

        When unconfigured, logs a notice and returns 1.0.
        """
        if not self.api_key:
            return 1.0

        raise NotImplementedError(
            f"ProviderAdapter [{self.provider_name}] requires customer-supplied "
            f"API integration code and authenticated endpoint access."
        )


# ---------------------------------------------------------------------------
# Cost Oracle Base Class
# ---------------------------------------------------------------------------

class CostOracle(ABC):
    """Abstract base class for distance and travel-time estimation."""

    def __init__(
        self,
        cache: CostCache | None = None,
        traffic_adapter: TrafficAdapter | None = None,
    ) -> None:
        self.cache = cache
        self.traffic_adapter = traffic_adapter

    @abstractmethod
    def _query_base_cost(self, origin: Location, dest: Location) -> tuple[float, float]:
        """Compute base (travel_time_sec, distance_m) without traffic adjustments."""
        ...

    def distance(self, origin: Any, dest: Any) -> float:
        """Return distance in metres between origin and dest."""
        orig_loc = to_location(origin)
        dest_loc = to_location(dest)
        if orig_loc.id == dest_loc.id:
            return 0.0

        if self.cache is not None:
            cached = self.cache.get(orig_loc.id, dest_loc.id, time_bucket=0)
            if cached is not None:
                return cached[1]

        _, dist = self._query_base_cost(orig_loc, dest_loc)
        return dist

    def travel_time(self, origin: Any, dest: Any, depart_time: float = 0.0) -> float:
        """Return estimated travel time in seconds between origin and dest departing at depart_time.

        Accounts for time-dependent traffic conditions and cache lookups.
        """
        orig_loc = to_location(origin)
        dest_loc = to_location(dest)
        if orig_loc.id == dest_loc.id:
            return 0.0

        time_bucket = self.cache.get_time_bucket(depart_time) if self.cache is not None else 0

        # Check Cache
        if self.cache is not None:
            cached = self.cache.get(orig_loc.id, dest_loc.id, time_bucket)
            if cached is not None:
                return cached[0]

        # Base Cost
        base_duration, base_distance = self._query_base_cost(orig_loc, dest_loc)

        # Traffic Factor
        if self.traffic_adapter is not None:
            speed_factor = self.traffic_adapter.get_speed_multiplier(orig_loc, dest_loc, depart_time)
            if speed_factor <= 0.0:
                adjusted_duration = float("inf")
            else:
                adjusted_duration = base_duration / speed_factor
        else:
            adjusted_duration = base_duration

        # Populate Cache
        if self.cache is not None:
            self.cache.set(orig_loc.id, dest_loc.id, time_bucket, adjusted_duration, base_distance)

        return adjusted_duration

    @abstractmethod
    def matrix(
        self, points: Sequence[Any], depart_time: float = 0.0
    ) -> MatrixResult:
        """Compute duration (seconds) and distance (metres) matrices for points."""
        ...

    def evaluate_route(
        self,
        stops: Sequence[Any],
        start_time: float = 0.0,
        service_times: Sequence[float] | None = None,
        ready_times: Sequence[float] | None = None,
        due_times: Sequence[float] | None = None,
    ) -> RouteTimeline:
        """Perform sequential time-dependent evaluation of a vehicle route.

        CRITICAL EVALUATION RULE:
        Arrival time at stop k is strictly computed from the actual departure time
        of the previous stop k-1:
            arrival_k = departure_{k-1} + travel_time(stop_{k-1}, stop_k, depart_time=departure_{k-1})
        """
        norm_stops = [to_location(s) for s in stops]
        n = len(norm_stops)
        if n == 0:
            return RouteTimeline(
                stops=[],
                total_travel_time=0.0,
                total_distance=0.0,
                total_duration=0.0,
                total_wait_time=0.0,
                total_lateness=0.0,
            )

        s_times = list(service_times) if service_times is not None else [0.0] * n
        r_times = list(ready_times) if ready_times is not None else [0.0] * n
        d_times = list(due_times) if due_times is not None else [float("inf")] * n

        stop_timelines: list[StopTimeline] = []
        total_travel_time = 0.0
        total_distance = 0.0
        total_wait_time = 0.0
        total_lateness = 0.0

        # Initial stop (Depot or route origin)
        cur_arr = start_time
        cur_start = max(cur_arr, r_times[0])
        cur_wait = cur_start - cur_arr
        cur_late = max(0.0, cur_arr - d_times[0])
        cur_dep = cur_start + s_times[0]

        total_wait_time += cur_wait
        total_lateness += cur_late

        stop_timelines.append(
            StopTimeline(
                stop_id=norm_stops[0].id,
                arrival_time=cur_arr,
                service_start_time=cur_start,
                departure_time=cur_dep,
                wait_time=cur_wait,
                travel_time_from_prev=0.0,
                distance_from_prev=0.0,
                lateness=cur_late,
            )
        )

        prev_dep = cur_dep

        # Subsequent stops
        for i in range(1, n):
            leg_dist = self.distance(norm_stops[i - 1], norm_stops[i])
            leg_time = self.travel_time(norm_stops[i - 1], norm_stops[i], depart_time=prev_dep)

            cur_arr = prev_dep + leg_time
            cur_start = max(cur_arr, r_times[i])
            cur_wait = cur_start - cur_arr
            cur_late = max(0.0, cur_arr - d_times[i])
            cur_dep = cur_start + s_times[i]

            total_travel_time += leg_time
            total_distance += leg_dist
            total_wait_time += cur_wait
            total_lateness += cur_late

            stop_timelines.append(
                StopTimeline(
                    stop_id=norm_stops[i].id,
                    arrival_time=cur_arr,
                    service_start_time=cur_start,
                    departure_time=cur_dep,
                    wait_time=cur_wait,
                    travel_time_from_prev=leg_time,
                    distance_from_prev=leg_dist,
                    lateness=cur_late,
                )
            )

            prev_dep = cur_dep

        total_duration = prev_dep - start_time

        return RouteTimeline(
            stops=stop_timelines,
            total_travel_time=total_travel_time,
            total_distance=total_distance,
            total_duration=total_duration,
            total_wait_time=total_wait_time,
            total_lateness=total_lateness,
        )


# ---------------------------------------------------------------------------
# Euclidean Oracle (Benchmarking & Unit Testing)
# ---------------------------------------------------------------------------

def decode_polyline(encoded: str, precision: float = 1e6) -> list[tuple[float, float]]:
    """Decode a Google / Valhalla encoded polyline into a list of (lat, lon) coordinates."""
    coordinates: list[tuple[float, float]] = []
    idx = 0
    length = len(encoded)
    lat = 0
    lon = 0

    while idx < length:
        shift = 0
        result = 0
        while True:
            if idx >= length:
                break
            b = ord(encoded[idx]) - 63
            idx += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        dlat = ~(result >> 1) if (result & 1) else (result >> 1)
        lat += dlat

        shift = 0
        result = 0
        while True:
            if idx >= length:
                break
            b = ord(encoded[idx]) - 63
            idx += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        dlon = ~(result >> 1) if (result & 1) else (result >> 1)
        lon += dlon

        coordinates.append((lat / precision, lon / precision))

    return coordinates


def encode_polyline(
    coordinates: Sequence[tuple[float, float]], precision: float = 1e6
) -> str:
    """Encode a sequence of (lat, lon) coordinates into a Google / Valhalla polyline string."""
    output: list[str] = []
    prev_lat = 0
    prev_lon = 0

    for lat, lon in coordinates:
        curr_lat = int(round(lat * precision))
        curr_lon = int(round(lon * precision))
        dlat = curr_lat - prev_lat
        dlon = curr_lon - prev_lon
        prev_lat = curr_lat
        prev_lon = curr_lon

        for val in (dlat, dlon):
            val = ~(val << 1) if val < 0 else (val << 1)
            while val >= 0x20:
                output.append(chr((0x20 | (val & 0x1F)) + 63))
                val >>= 5
            output.append(chr(val + 63))

    return "".join(output)


class EuclideanOracle(CostOracle):
    """Euclidean & planar/haversine oracle for fast tests and benchmarks."""

    def __init__(
        self,
        base_speed_mps: float | None = None,
        cache: CostCache | None = None,
        traffic_adapter: TrafficAdapter | None = None,
        use_haversine: bool | None = None,
        planar_scale: float = 1.0,
        coordinate_system: Literal["geographic", "planar"] | None = None,
    ) -> None:
        """Initialize Euclidean oracle.

        Args:
            base_speed_mps: Base vehicle speed (default 8.333 m/s for geographic, 1.0 for planar).
            cache: Optional cost cache.
            traffic_adapter: Optional traffic adapter.
            use_haversine: Deprecated alias for coordinate_system == 'geographic'.
            planar_scale: Scaling factor for planar Euclidean distance (default: 1.0).
            coordinate_system: 'geographic' (Haversine distance in metres) or 'planar' (Euclidean hypot).
        """
        super().__init__(cache=cache, traffic_adapter=traffic_adapter)
        if coordinate_system is not None:
            self.coordinate_system: Literal["geographic", "planar"] = coordinate_system
        elif use_haversine is not None:
            self.coordinate_system = "geographic" if use_haversine else "planar"
        else:
            self.coordinate_system = "geographic"

        self.planar_scale = float(planar_scale)
        if base_speed_mps is None:
            self.base_speed_mps = 8.333 if self.coordinate_system == "geographic" else 1.0
        else:
            if base_speed_mps <= 0.0:
                raise ValueError("base_speed_mps must be positive")
            self.base_speed_mps = float(base_speed_mps)

    @property
    def use_haversine(self) -> bool:
        return self.coordinate_system == "geographic"

    def _query_base_cost(self, origin: Location, dest: Location) -> tuple[float, float]:
        if origin.id == dest.id:
            return 0.0, 0.0

        if self.coordinate_system == "geographic":
            # Haversine distance in metres
            r = 6371000.0
            phi1, phi2 = math.radians(origin.lat), math.radians(dest.lat)
            dphi = math.radians(dest.lat - origin.lat)
            dlam = math.radians(dest.lon - origin.lon)
            a = (
                math.sin(dphi / 2.0) ** 2
                + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2.0) ** 2
            )
            dist_m = 2.0 * r * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
            speed = self.base_speed_mps if self.base_speed_mps > 1.0 else 8.333
            duration_sec = dist_m / speed
            return duration_sec, dist_m
        else:
            # Planar Euclidean distance
            dist = math.hypot(origin.lat - dest.lat, origin.lon - dest.lon) * self.planar_scale
            duration_sec = dist / self.base_speed_mps
            return duration_sec, dist

    def matrix(
        self, points: Sequence[Any], depart_time: float = 0.0
    ) -> MatrixResult:
        """Compute all-pairs duration and distance matrices."""
        norm_points = [to_location(p) for p in points]
        n = len(norm_points)
        durations = [[0.0] * n for _ in range(n)]
        distances = [[0.0] * n for _ in range(n)]

        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                d = self.distance(norm_points[i], norm_points[j])
                t = self.travel_time(norm_points[i], norm_points[j], depart_time=depart_time)
                distances[i][j] = d
                durations[i][j] = t

        return MatrixResult(durations=durations, distances=distances)


# ---------------------------------------------------------------------------
# Valhalla Oracle (Public OSM / Local Docker Routing Engine with Chunking & Fallback)
# ---------------------------------------------------------------------------

DEFAULT_VALHALLA_URL = os.environ.get("VALHALLA_URL", "http://127.0.0.1:8002")

# Module-level thread-safe in-memory cache and polite rate limiter for Valhalla
_VALHALLA_PAIR_CACHE: dict[tuple[float, float, float, float, str], tuple[float, float]] = {}
_VALHALLA_ROUTE_CACHE: dict[tuple[tuple[float, float], ...], dict[str, Any]] = {}
_LAST_VALHALLA_REQ_TIME: float = 0.0
_VALHALLA_LOCK = threading.Lock()


def _rate_limit_valhalla(min_interval: float = 0.5) -> None:
    """Ensure at least min_interval seconds between outbound Valhalla requests."""
    global _LAST_VALHALLA_REQ_TIME
    with _VALHALLA_LOCK:
        now = time.time()
        elapsed = now - _LAST_VALHALLA_REQ_TIME
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        _LAST_VALHALLA_REQ_TIME = time.time()


class ValhallaOracle(CostOracle):
    """Road network oracle backed by Valhalla (supports public OpenStreetMap server or local Docker)."""

    def __init__(
        self,
        base_url: str | None = None,
        costing: str = "auto",
        chunk_size: int = 10,
        timeout: float = 8.0,
        cache: CostCache | None = None,
        traffic_adapter: TrafficAdapter | None = None,
    ) -> None:
        """Initialize Valhalla cost oracle.

        Args:
            base_url: Valhalla endpoint URL (default: VALHALLA_URL env or http://127.0.0.1:8002).
            costing: Routing costing model (default: "auto").
            chunk_size: Maximum sources/targets per subquery (clamped to <=10 for public server compliance).
            timeout: HTTP socket timeout in seconds (default: 8.0).
            cache: Optional CostCache backend.
            traffic_adapter: Optional traffic adapter.
        """
        super().__init__(cache=cache, traffic_adapter=traffic_adapter)
        chosen_url = base_url if (base_url and base_url.strip()) else DEFAULT_VALHALLA_URL
        self.base_url = chosen_url.rstrip("/")
        self.costing = costing
        # Public Valhalla enforces max 100 locations per sources_to_targets (10 x 10 = 100)
        self.chunk_size = max(1, min(chunk_size, 10))
        self.timeout = timeout
        self.fallback_active = False
        self.fallback_reason: str | None = None

    def _haversine(self, origin: Location, dest: Location) -> tuple[float, float]:
        """Compute geographic Haversine distance (m) and urban duration (s)."""
        r = 6371000.0
        phi1, phi2 = math.radians(origin.lat), math.radians(dest.lat)
        dphi = math.radians(dest.lat - origin.lat)
        dlam = math.radians(dest.lon - origin.lon)
        a = (
            math.sin(dphi / 2.0) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2.0) ** 2
        )
        dist_m = 2.0 * r * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
        duration_sec = dist_m / 8.333  # ~30 km/h average urban speed
        return duration_sec, dist_m

    def _http_post(self, endpoint: str, payload: dict[str, Any], retries: int = 2) -> dict[str, Any]:
        """Send POST request to Valhalla with polite rate limiting and backoff."""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data_bytes,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Route.it-SIH2026",
                "Accept": "application/json",
            },
            method="POST",
        )

        last_err: Exception | None = None
        for attempt in range(retries + 1):
            _rate_limit_valhalla(0.5)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    if resp.status == 200:
                        body = resp.read().decode("utf-8")
                        return json.loads(body)
                    raise RuntimeError(f"Valhalla returned HTTP status {resp.status}")
            except urllib.error.HTTPError as exc:
                last_err = exc
                if exc.code == 429 and attempt < retries:
                    time.sleep(1.0 * (attempt + 1))
                    continue
                raise
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_err = exc
                if attempt < retries:
                    time.sleep(1.0 * (attempt + 1))
                    continue
                raise

        raise ConnectionError(f"Valhalla request to {url} failed: {last_err}") from last_err

    def _query_sources_to_targets(
        self, sources: list[Location], targets: list[Location]
    ) -> list[list[dict[str, Any]]]:
        """Execute /sources_to_targets with in-memory caching and graceful Haversine fallback."""
        # 1. Check if all pairs are in in-memory cache
        all_cached = True
        cached_rows: list[list[dict[str, Any]]] = []
        for s in sources:
            row_items: list[dict[str, Any]] = []
            for t in targets:
                if s.lat == t.lat and s.lon == t.lon:
                    row_items.append({"time": 0.0, "distance": 0.0})
                    continue
                key = (round(s.lat, 5), round(s.lon, 5), round(t.lat, 5), round(t.lon, 5), self.costing)
                if key in _VALHALLA_PAIR_CACHE:
                    time_s, dist_m = _VALHALLA_PAIR_CACHE[key]
                    row_items.append({"time": time_s, "distance": dist_m / 1000.0})
                else:
                    all_cached = False
                    break
            if not all_cached:
                break
            cached_rows.append(row_items)

        if all_cached:
            return cached_rows

        # 2. If fallback already active, avoid hammering unavailable server
        if self.fallback_active:
            fallback_rows: list[list[dict[str, Any]]] = []
            for s in sources:
                r_list: list[dict[str, Any]] = []
                for t in targets:
                    if s.lat == t.lat and s.lon == t.lon:
                        r_list.append({"time": 0.0, "distance": 0.0})
                    else:
                        dur_s, dist_m = self._haversine(s, t)
                        r_list.append({"time": dur_s, "distance": dist_m / 1000.0})
                fallback_rows.append(r_list)
            return fallback_rows

        payload = {
            "sources": [{"lat": s.lat, "lon": s.lon} for s in sources],
            "targets": [{"lat": t.lat, "lon": t.lon} for t in targets],
            "costing": self.costing,
            "units": "kilometers",
        }

        try:
            res = self._http_post("sources_to_targets", payload, retries=2)
            raw = res.get("sources_to_targets", [])
            for r_idx, row in enumerate(raw):
                s = sources[r_idx]
                for c_idx, col in enumerate(row):
                    t = targets[c_idx]
                    key = (round(s.lat, 5), round(s.lon, 5), round(t.lat, 5), round(t.lon, 5), self.costing)
                    _VALHALLA_PAIR_CACHE[key] = (float(col.get("time", 0.0)), float(col.get("distance", 0.0)) * 1000.0)
            return raw
        except Exception as exc:
            self.fallback_active = True
            self.fallback_reason = f"Valhalla unavailable ({exc}). Using simulated Haversine road model."
            logger.warning(
                "Valhalla /sources_to_targets failed (%s); seamlessly falling back to simulated Haversine distance.",
                exc,
            )
            fallback_rows = []
            for s in sources:
                r_list = []
                for t in targets:
                    if s.lat == t.lat and s.lon == t.lon:
                        r_list.append({"time": 0.0, "distance": 0.0})
                    else:
                        dur_s, dist_m = self._haversine(s, t)
                        r_list.append({"time": dur_s, "distance": dist_m / 1000.0})
                fallback_rows.append(r_list)
            return fallback_rows

    def _query_base_cost(self, origin: Location, dest: Location) -> tuple[float, float]:
        """Fetch base time (s) and distance (m) for a single OD pair."""
        res = self._query_sources_to_targets([origin], [dest])
        if not res or not res[0]:
            return self._haversine(origin, dest)
        entry = res[0][0]
        dur_sec = float(entry.get("time", 0.0))
        dist_m = float(entry.get("distance", 0.0)) * 1000.0
        return dur_sec, dist_m

    def matrix(
        self, points: Sequence[Any], depart_time: float = 0.0
    ) -> MatrixResult:
        """Compute full N x N matrix in chunks respecting Valhalla limits."""
        norm_points = [to_location(p) for p in points]
        n = len(norm_points)
        durations = [[0.0] * n for _ in range(n)]
        distances = [[0.0] * n for _ in range(n)]

        if n <= 1:
            return MatrixResult(durations=durations, distances=distances)

        time_bucket = self.cache.get_time_bucket(depart_time) if self.cache is not None else 0

        # Query in chunks of size (chunk_size x chunk_size)
        for i in range(0, n, self.chunk_size):
            src_chunk = norm_points[i : i + self.chunk_size]
            for j in range(0, n, self.chunk_size):
                tgt_chunk = norm_points[j : j + self.chunk_size]

                # Check if all pairs in this chunk are already cached in self.cache
                all_cached = True
                chunk_durs: list[list[float]] = []
                chunk_dists: list[list[float]] = []

                if self.cache is not None:
                    for r_idx, s in enumerate(src_chunk):
                        row_durs: list[float] = []
                        row_dists: list[float] = []
                        for c_idx, t in enumerate(tgt_chunk):
                            if s.id == t.id:
                                row_durs.append(0.0)
                                row_dists.append(0.0)
                                continue
                            cached = self.cache.get(s.id, t.id, time_bucket)
                            if cached is not None:
                                row_durs.append(cached[0])
                                row_dists.append(cached[1])
                            else:
                                all_cached = False
                                break
                        if not all_cached:
                            break
                        chunk_durs.append(row_durs)
                        chunk_dists.append(row_dists)

                if all_cached and self.cache is not None:
                    for r_idx in range(len(src_chunk)):
                        for c_idx in range(len(tgt_chunk)):
                            durations[i + r_idx][j + c_idx] = chunk_durs[r_idx][c_idx]
                            distances[i + r_idx][j + c_idx] = chunk_dists[r_idx][c_idx]
                    continue

                # Query Valhalla for this submatrix
                raw_matrix = self._query_sources_to_targets(src_chunk, tgt_chunk)

                for r_idx, row in enumerate(raw_matrix):
                    s_loc = src_chunk[r_idx]
                    for c_idx, col in enumerate(row):
                        t_loc = tgt_chunk[c_idx]
                        if s_loc.id == t_loc.id:
                            durations[i + r_idx][j + c_idx] = 0.0
                            distances[i + r_idx][j + c_idx] = 0.0
                            continue

                        base_time = float(col.get("time", 0.0))
                        base_dist = float(col.get("distance", 0.0)) * 1000.0

                        # Apply Traffic Multiplier
                        if self.traffic_adapter is not None:
                            speed_factor = self.traffic_adapter.get_speed_multiplier(
                                s_loc, t_loc, depart_time
                            )
                            adj_time = base_time / speed_factor if speed_factor > 0.0 else float("inf")
                        else:
                            adj_time = base_time

                        durations[i + r_idx][j + c_idx] = adj_time
                        distances[i + r_idx][j + c_idx] = base_dist

                        # Store in cache
                        if self.cache is not None:
                            self.cache.set(s_loc.id, t_loc.id, time_bucket, adj_time, base_dist)

        return MatrixResult(durations=durations, distances=distances)

    def route(
        self,
        locations: Sequence[Any],
        costing: str | None = None,
        directions_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Compute full turn-by-turn route with decoded geometry for a sequence of stops.

        Respects the public Valhalla limit of at most 10 waypoints per request by chunking
        overlapping subsegments of 8 waypoints and stitching the polyline coordinates.
        Falls back seamlessly to straight-line Haversine coordinates if unavailable.
        """
        norm_locs = [to_location(loc) for loc in locations]
        if not norm_locs:
            return {"trip": {}, "coordinates": [], "distance_km": 0.0, "time_sec": 0.0}

        if len(norm_locs) == 1:
            return {
                "trip": {},
                "coordinates": [[round(norm_locs[0].lon, 6), round(norm_locs[0].lat, 6)]],
                "distance_km": 0.0,
                "time_sec": 0.0,
            }

        # Check in-memory route cache
        route_key = tuple((round(l.lat, 5), round(l.lon, 5)) for l in norm_locs)
        if route_key in _VALHALLA_ROUTE_CACHE:
            return _VALHALLA_ROUTE_CACHE[route_key]

        # If fallback active, return straight-line coordinates
        if self.fallback_active:
            return self._fallback_route(norm_locs)

        # Chunk into overlapping windows of at most 8 stops (public Valhalla limit is 10)
        sub_windows: list[list[Location]] = []
        idx = 0
        while idx < len(norm_locs):
            end = min(idx + 8, len(norm_locs))
            sub_windows.append(norm_locs[idx:end])
            if end >= len(norm_locs):
                break
            idx = end - 1  # 1-stop overlap for seamless polyline connection

        stitched_coords: list[list[float]] = []
        total_dist_km = 0.0
        total_time_sec = 0.0
        last_trip: dict[str, Any] = {}

        try:
            for w_idx, win in enumerate(sub_windows):
                payload = {
                    "locations": [{"lat": loc.lat, "lon": loc.lon, "type": "break"} for loc in win],
                    "costing": costing or self.costing,
                    "directions_options": directions_options or {"units": "kilometers"},
                }
                res = self._http_post("route", payload, retries=2)
                trip = res.get("trip", {})
                last_trip = trip
                summary = trip.get("summary", {})
                total_dist_km += float(summary.get("length", 0.0))
                total_time_sec += float(summary.get("time", 0.0))

                legs = trip.get("legs", [])
                sub_coords: list[list[float]] = []
                for leg in legs:
                    shape = leg.get("shape", "")
                    if shape:
                        decoded = decode_polyline(shape, precision=1e6)
                        for lat, lon in decoded:
                            sub_coords.append([round(lon, 6), round(lat, 6)])

                if not sub_coords:
                    # Fallback to win coords if shapes empty
                    sub_coords = [[round(loc.lon, 6), round(loc.lat, 6)] for loc in win]

                if w_idx == 0:
                    stitched_coords.extend(sub_coords)
                else:
                    # Omit first coordinate to avoid duplicate point at stitch seam
                    stitched_coords.extend(sub_coords[1:])

            result = {
                "trip": last_trip,
                "coordinates": stitched_coords,
                "distance_km": round(total_dist_km, 3),
                "time_sec": round(total_time_sec, 1),
            }
            _VALHALLA_ROUTE_CACHE[route_key] = result
            return result
        except Exception as exc:
            self.fallback_active = True
            self.fallback_reason = f"Valhalla /route failed ({exc}). Using simulated road geometries."
            logger.warning(
                "Valhalla /route failed (%s); seamlessly falling back to straight-line geometries.", exc
            )
            return self._fallback_route(norm_locs)

    def _fallback_route(self, norm_locs: list[Location]) -> dict[str, Any]:
        """Generate straight-line GeoJSON geometry and Haversine times as fallback."""
        coords: list[list[float]] = []
        total_dist_km = 0.0
        total_time_sec = 0.0
        for i, loc in enumerate(norm_locs):
            coords.append([round(loc.lon, 6), round(loc.lat, 6)])
            if i > 0:
                dur_s, dist_m = self._haversine(norm_locs[i - 1], loc)
                total_dist_km += dist_m / 1000.0
                total_time_sec += dur_s
        return {
            "trip": {"summary": {"length": round(total_dist_km, 3), "time": round(total_time_sec, 1)}},
            "coordinates": coords,
            "distance_km": round(total_dist_km, 3),
            "time_sec": round(total_time_sec, 1),
            "fallback": True,
        }


