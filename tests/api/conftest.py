"""Pytest fixtures for Route.it API test suite."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from collections.abc import Generator

from api.main import app
from api.store import InMemoryProblemStore, set_store
from solver.models import Customer, Depot, Problem, Vehicle
from solver.qpso import QPSOConfig, solve_qpso


@pytest.fixture(scope="session", autouse=True)
def prewarm_numba_jit() -> None:
    """Pre-warm Numba JIT once per test session so optimization runs don't incur first-call compilation delays."""
    depot = Depot(id="depot", lat=0.0, lon=0.0, ready_time=0.0, due_time=1000.0)
    customers = [
        Customer(id="c1", lat=1.0, lon=0.0, demand=1.0, ready_time=0.0, due_time=100.0, service_time=5.0),
        Customer(id="c2", lat=2.0, lon=0.0, demand=1.0, ready_time=0.0, due_time=100.0, service_time=5.0),
    ]
    vehicles = [Vehicle(id="v1", capacity=10.0, shift_start=0.0, shift_end=1000.0)]
    prob = Problem(id="warmup_prob", depot=depot, customers=customers, vehicles=vehicles)
    prob.compute_euclidean_matrices()
    solve_qpso(prob, QPSOConfig(num_particles=5, max_iters=2, seed=42))


@pytest.fixture(autouse=True)
def reset_store_per_test() -> None:
    """Ensure a clean, isolated in-memory store for every test."""
    store = InMemoryProblemStore()
    set_store(store)
    yield
    store.clear()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """FastAPI TestClient instance with lifespan management for WebSocket event loop capture."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def sample_problem_payload() -> dict:
    """Standard sample problem payload with 4 customers in Vadodara."""
    return {
        "id": "test_city_4",
        "depot": {
            "id": "depot",
            "lat": 22.3072,
            "lon": 73.1812,
            "ready_time": 0.0,
            "due_time": 28800.0,
            "service_time": 0.0,
        },
        "customers": [
            {
                "id": "c1",
                "lat": 22.3150,
                "lon": 73.1850,
                "demand": 5.0,
                "ready_time": 0.0,
                "due_time": 14400.0,
                "service_time": 300.0,
                "priority": 1,
            },
            {
                "id": "c2",
                "lat": 22.3200,
                "lon": 73.1900,
                "demand": 5.0,
                "ready_time": 0.0,
                "due_time": 14400.0,
                "service_time": 300.0,
                "priority": 1,
            },
            {
                "id": "c3",
                "lat": 22.3000,
                "lon": 73.1750,
                "demand": 5.0,
                "ready_time": 0.0,
                "due_time": 14400.0,
                "service_time": 300.0,
                "priority": 1,
            },
            {
                "id": "c4",
                "lat": 22.2950,
                "lon": 73.1700,
                "demand": 5.0,
                "ready_time": 0.0,
                "due_time": 14400.0,
                "service_time": 300.0,
                "priority": 2,
            },
        ],
        "vehicles": [
            {
                "id": "v1",
                "capacity": 15.0,
                "shift_start": 0.0,
                "shift_end": 28800.0,
            },
            {
                "id": "v2",
                "capacity": 15.0,
                "shift_start": 0.0,
                "shift_end": 28800.0,
            },
        ],
    }
