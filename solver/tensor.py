"""Time-bucketed travel-time tensor precomputation for Route.it CVRPTW solver.

Bridges the high-level CostOracle (ValhallaOracle, EuclideanOracle, TrafficAdapter)
to high-performance Numba-accelerated split routines by precomputing a 3D
travel-time tensor across discrete time periods.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import TYPE_CHECKING
import numpy as np

if TYPE_CHECKING:
    from routing.cost_oracle import CostOracle
    from solver.models import Problem


@dataclass
class CostTensor:
    """Precomputed time-bucketed travel-time tensor and distance matrix for a Problem."""

    travel_time_tensor: np.ndarray  # shape (B, N+1, N+1) float64
    distance_matrix: np.ndarray      # shape (N+1, N+1) float64
    t_start: float = 0.0
    bucket_size: float = 900.0
    num_buckets: int = 1

    @property
    def is_time_dependent(self) -> bool:
        """Whether tensor has multiple time buckets."""
        return self.num_buckets > 1


def precompute_cost_tensor(
    problem: Problem,
    cost_oracle: CostOracle | None = None,
    bucket_size_seconds: float = 900.0,
    num_buckets: int | None = None,
) -> CostTensor:
    """Precompute travel-time tensor and distance matrix for all nodes in a Problem.

    Node 0 is the depot, nodes 1..N are the customers.

    Args:
        problem: CVRPTW Problem instance.
        cost_oracle: Optional CostOracle (e.g. ValhallaOracle, EuclideanOracle).
                     If None, builds from problem.distance_matrix or Euclidean coordinates.
        bucket_size_seconds: Time interval per bucket in seconds (default: 15 min = 900s).
        num_buckets: Optional explicit number of buckets B.

    Returns:
        CostTensor with 3D travel_time_tensor and 2D distance_matrix.
    """
    from routing.cost_oracle import EuclideanOracle, Location

    # Construct ordered stop list: 0 is depot, 1..N are customers
    depot_loc = Location(id=problem.depot.id, lat=problem.depot.lat, lon=problem.depot.lon)
    cust_locs = [Location(id=c.id, lat=c.lat, lon=c.lon) for c in problem.customers]
    all_stops = [depot_loc] + cust_locs
    s = len(all_stops)

    # Fast path 1: No cost_oracle given, but problem already has precomputed Euclidean matrices
    if cost_oracle is None:
        if problem.distance_matrix is not None:
            dist_mat = np.asarray(problem.distance_matrix, dtype=np.float64)
            time_mat = (
                np.asarray(problem.travel_time_matrix, dtype=np.float64)
                if problem.travel_time_matrix is not None
                else dist_mat
            )
            tensor = time_mat.reshape((1, s, s))
            return CostTensor(
                travel_time_tensor=tensor,
                distance_matrix=dist_mat,
                t_start=problem.depot.ready_time,
                bucket_size=bucket_size_seconds,
                num_buckets=1,
            )

        # Build default oracle respecting problem.coordinate_system
        cost_oracle = EuclideanOracle(
            coordinate_system=problem.coordinate_system,
            base_speed_mps=8.333 if problem.coordinate_system == "geographic" else 1.0,
            planar_scale=1.0,
        )

    # Fast path 2: CostOracle is stationary (no dynamic traffic adapter)
    if cost_oracle.traffic_adapter is None:
        res = cost_oracle.matrix(all_stops, depart_time=problem.depot.ready_time)
        durs = np.asarray(res.durations, dtype=np.float64)
        dists = np.asarray(res.distances, dtype=np.float64)
        tensor = durs.reshape((1, s, s))

        # Synchronize problem distance matrix if absent
        if problem.distance_matrix is None:
            problem.distance_matrix = dists.tolist()
            problem.travel_time_matrix = durs.tolist()

        return CostTensor(
            travel_time_tensor=tensor,
            distance_matrix=dists,
            t_start=problem.depot.ready_time,
            bucket_size=bucket_size_seconds,
            num_buckets=1,
        )

    # Path 3: Time-dependent CostOracle (with TrafficAdapter)
    t_min = float(problem.depot.ready_time)
    t_max = (
        float(problem.depot.due_time)
        if math.isfinite(problem.depot.due_time) and problem.depot.due_time > t_min
        else t_min + 86400.0  # 24h default horizon
    )

    if num_buckets is not None:
        b_count = max(1, num_buckets)
    else:
        b_count = max(1, min(96, int(math.ceil((t_max - t_min) / bucket_size_seconds))))

    tensor = np.zeros((b_count, s, s), dtype=np.float64)
    dists = np.zeros((s, s), dtype=np.float64)

    for b in range(b_count):
        t_b = t_min + (b + 0.5) * bucket_size_seconds
        res = cost_oracle.matrix(all_stops, depart_time=t_b)
        tensor[b, :, :] = np.asarray(res.durations, dtype=np.float64)
        if b == 0:
            dists[:, :] = np.asarray(res.distances, dtype=np.float64)

    if problem.distance_matrix is None:
        problem.distance_matrix = dists.tolist()
        problem.travel_time_matrix = tensor[0].tolist()

    return CostTensor(
        travel_time_tensor=tensor,
        distance_matrix=dists,
        t_start=t_min,
        bucket_size=bucket_size_seconds,
        num_buckets=b_count,
    )
