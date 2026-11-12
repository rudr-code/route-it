"""FastAPI router for multi-algorithm benchmarking and scalability analysis."""

from __future__ import annotations

import logging
import time
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.database import DeliveryDatabase, get_db
from api.store import ProblemStore, get_store
from solver.benchmark import (
    AlgorithmBenchmarkResult,
    BenchmarkSuiteResult,
    run_algorithm_benchmark,
    run_scalability_analysis,
)
from solver.models import Customer, Depot, Problem, Vehicle

router = APIRouter(prefix="/benchmarks", tags=["Algorithm Benchmarks"])
logger = logging.getLogger("routeit_benchmark_api")

# Pre-seeded authentic 30-customer Vadodara scenario for benchmarking
VADODARA_BENCHMARK_DEPOT = Depot(
    id="depot",
    name="Vadodara Sayajigunj Central Depot",
    lat=22.3072,
    lon=73.1812,
    ready_time=25200.0,
    due_time=64800.0,
    service_time=0.0,
)

VADODARA_BENCHMARK_VEHICLES = [
    Vehicle(id="V_1", capacity=80.0, shift_start=25200.0, shift_end=64800.0, cost_per_distance=15.0, fixed_cost=250.0),
    Vehicle(id="V_2", capacity=80.0, shift_start=25200.0, shift_end=64800.0, cost_per_distance=15.0, fixed_cost=250.0),
    Vehicle(id="V_3", capacity=80.0, shift_start=25200.0, shift_end=64800.0, cost_per_distance=15.0, fixed_cost=250.0),
    Vehicle(id="V_4", capacity=80.0, shift_start=25200.0, shift_end=64800.0, cost_per_distance=15.0, fixed_cost=250.0),
]

_VADODARA_LOCATIONS = [
    ("c_1", "Alkapuri West Hub", 22.3125, 73.1785, 12.0, 28800.0, 43200.0, 1),
    ("c_2", "Akota Circle Hub", 22.2980, 73.1650, 15.0, 28800.0, 46800.0, 2),
    ("c_3", "Fatehgunj Medical Drop", 22.3250, 73.1900, 8.0, 32400.0, 50400.0, 3),
    ("c_4", "Gotri High-Street", 22.3150, 73.1420, 18.0, 32400.0, 54000.0, 1),
    ("c_5", "Manjalpur Retail", 22.2680, 73.1950, 20.0, 36000.0, 57600.0, 1),
    ("c_6", "Karelibaug North Hub", 22.3320, 73.2050, 14.0, 28800.0, 43200.0, 2),
    ("c_7", "Vasna Road Complex", 22.2890, 73.1480, 10.0, 36000.0, 54000.0, 1),
    ("c_8", "Sayajigunj Station Parcel", 22.3100, 73.1830, 16.0, 28800.0, 39600.0, 3),
    ("c_9", "Waghodia Road Logistics", 22.3010, 73.2350, 22.0, 32400.0, 57600.0, 1),
    ("c_10", "Subhanpura Commercial", 22.3210, 73.1610, 11.0, 36000.0, 50400.0, 1),
    ("c_11", "Makarpura Industrial", 22.2450, 73.1980, 25.0, 28800.0, 61200.0, 2),
    ("c_12", "Sama Savli Point", 22.3480, 73.2080, 13.0, 32400.0, 54000.0, 1),
    ("c_13", "Harni Airport Cargo", 22.3350, 73.2280, 19.0, 28800.0, 46800.0, 3),
    ("c_14", "Atladara Express Center", 22.2740, 73.1530, 12.0, 36000.0, 57600.0, 1),
    ("c_15", "Tandalja Commercial", 22.2850, 73.1600, 14.0, 32400.0, 50400.0, 1),
    ("c_16", "Ellora Park Market", 22.3180, 73.1690, 9.0, 28800.0, 43200.0, 2),
    ("c_17", "Chhani Canal Depot", 22.3610, 73.1850, 17.0, 36000.0, 57600.0, 1),
    ("c_18", "Gorwa Chemical Belt", 22.3380, 73.1550, 15.0, 32400.0, 54000.0, 1),
    ("c_19", "Nizampura Junction", 22.3340, 73.1800, 11.0, 28800.0, 46800.0, 2),
    ("c_20", "Pratapnagar Railway Store", 22.2870, 73.2090, 18.0, 36000.0, 61200.0, 1),
]

def get_default_benchmark_problem() -> Problem:
    """Build standardized 20-node benchmark problem instance in Vadodara."""
    customers = [
        Customer(
            id=cid,
            name=cname,
            lat=clat,
            lon=clon,
            demand=cdemand,
            ready_time=cready,
            due_time=cdue,
            service_time=600.0,
            priority=cpri,
        )
        for cid, cname, clat, clon, cdemand, cready, cdue, cpri in _VADODARA_LOCATIONS
    ]
    prob = Problem(
        id="vadodara_benchmark_20",
        depot=VADODARA_BENCHMARK_DEPOT,
        customers=customers,
        vehicles=VADODARA_BENCHMARK_VEHICLES,
        coordinate_system="geographic",
    )
    prob.compute_euclidean_matrices()
    return prob


class BenchmarkRunRequest(BaseModel):
    problem_id: str | None = None
    algorithms: list[str] = Field(
        default=["qpso", "pso", "ga", "dijkstra", "ortools"],
        description="Algorithms to compare: qpso, pso, ga, dijkstra, ortools",
    )
    num_particles_or_pop: int = Field(25, ge=5, le=100)
    max_iters_or_gen: int = Field(35, ge=5, le=200)
    seed: int = 42


# In-memory benchmark cache
_cached_latest_benchmark: BenchmarkSuiteResult | None = None
_cached_scalability: list[dict[str, Any]] | None = None


@router.post("/run", response_model=BenchmarkSuiteResult)
def run_benchmark(
    req: BenchmarkRunRequest,
    store: ProblemStore = Depends(get_store),
) -> BenchmarkSuiteResult:
    """Execute head-to-head benchmarking between QPSO, PSO, GA, Dijkstra, and OR-Tools."""
    global _cached_latest_benchmark
    prob: Problem | None = None
    if req.problem_id:
        prob = store.get_problem(req.problem_id)
    if prob is None:
        prob = get_default_benchmark_problem()

    res = run_algorithm_benchmark(
        problem=prob,
        algorithms=req.algorithms,
        num_particles_or_pop=req.num_particles_or_pop,
        max_iters_or_gen=req.max_iters_or_gen,
        seed=req.seed,
    )
    _cached_latest_benchmark = res
    return res


@router.get("/latest", response_model=BenchmarkSuiteResult)
def get_latest_benchmark() -> BenchmarkSuiteResult:
    """Retrieve the most recent benchmark run or generate default."""
    global _cached_latest_benchmark
    if _cached_latest_benchmark is None:
        prob = get_default_benchmark_problem()
        _cached_latest_benchmark = run_algorithm_benchmark(
            problem=prob,
            algorithms=["qpso", "pso", "ga", "dijkstra", "ortools"],
            num_particles_or_pop=20,
            max_iters_or_gen=25,
            seed=42,
        )
    return _cached_latest_benchmark


@router.get("/scalability")
def get_scalability_analysis() -> list[dict[str, Any]]:
    """Retrieve runtime latency and solution cost scaling across 10, 25, 50, and 100 delivery points."""
    global _cached_scalability
    if _cached_scalability is None:
        _cached_scalability = run_scalability_analysis(node_sizes=[10, 25, 50, 100], seed=42)
    return _cached_scalability
