"""Route.it Routing & Cost Oracle Package.

Provides road network integration via Valhalla client, distance/travel-time matrix
calculations, persistent cache, and time-dependent traffic profiles.
"""

from routing.cost_oracle import (
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

__version__ = "0.1.0"

__all__ = [
    "CostCache",
    "CostOracle",
    "EuclideanOracle",
    "InMemoryLRUCache",
    "Location",
    "MatrixResult",
    "ProviderAdapter",
    "RouteTimeline",
    "SimulatedEventAdapter",
    "SimulatedIncident",
    "SQLiteCache",
    "StopTimeline",
    "TimeOfDayProfileAdapter",
    "TrafficAdapter",
    "ValhallaOracle",
    "decode_polyline",
    "encode_polyline",
    "to_location",
]


