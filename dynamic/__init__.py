"""Route.it Dynamic Re-optimization & Simulation Layer.

Features traffic event simulation, dynamic scenario generation, fleet movement simulation,
delta-cost impact assessment (stability penalty), and tiered repair mechanisms (Tier 1-3).
"""

from dynamic.events import (
    AnyDynamicEvent,
    DynamicEvent,
    EdgeCongestion,
    NewOrder,
    RoadBlockage,
    Scenario,
    VehicleDelay,
    generate_random_scenario,
)
from dynamic.reoptimizer import (
    DynamicReoptimizer,
    ReoptimizationRecord,
    ReoptimizationTier,
    ReoptimizerConfig,
    calculate_stability_penalty,
    full_restart_baseline,
    partition_stops_by_commitment,
)
from dynamic.simulator import (
    FleetSimulator,
    SimulationSnapshot,
    VehicleState,
    VehicleStatus,
)

__version__ = "0.1.0"

__all__ = [
    "AnyDynamicEvent",
    "DynamicEvent",
    "DynamicReoptimizer",
    "EdgeCongestion",
    "FleetSimulator",
    "NewOrder",
    "ReoptimizationRecord",
    "ReoptimizationTier",
    "ReoptimizerConfig",
    "RoadBlockage",
    "Scenario",
    "SimulationSnapshot",
    "VehicleDelay",
    "VehicleState",
    "VehicleStatus",
    "calculate_stability_penalty",
    "full_restart_baseline",
    "generate_random_scenario",
    "partition_stops_by_commitment",
]
