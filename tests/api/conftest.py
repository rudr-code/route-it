"""Pytest fixtures for Route.it API test suite."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.store import InMemoryProblemStore, set_store
from solver.models import Customer, Depot, Problem, Vehicle


@pytest.fixture(autouse=True)
def reset_store_per_test() -> None:
    """Ensure a clean, isolated in-memory store for every test."""
    store = InMemoryProblemStore()
    set_store(store)
    yield
    store.clear()


@pytest.fixture
def client() -> TestClient:
    """FastAPI TestClient instance."""
    return TestClient(app)


@pytest.fixture
def sample_problem_payload() -> dict:
    """Standard sample problem payload with 4 customers."""
    return {
        "id": "test_city_4",
        "depot": {
            "id": "depot",
            "lat": 0.0,
            "lon": 0.0,
            "ready_time": 0.0,
            "due_time": 1000.0,
            "service_time": 0.0,
        },
        "customers": [
            {
                "id": "c1",
                "lat": 10.0,
                "lon": 0.0,
                "demand": 5.0,
                "ready_time": 0.0,
                "due_time": 500.0,
                "service_time": 10.0,
                "priority": 1,
            },
            {
                "id": "c2",
                "lat": 20.0,
                "lon": 0.0,
                "demand": 5.0,
                "ready_time": 0.0,
                "due_time": 500.0,
                "service_time": 10.0,
                "priority": 1,
            },
            {
                "id": "c3",
                "lat": 0.0,
                "lon": 10.0,
                "demand": 5.0,
                "ready_time": 0.0,
                "due_time": 500.0,
                "service_time": 10.0,
                "priority": 1,
            },
            {
                "id": "c4",
                "lat": 0.0,
                "lon": 20.0,
                "demand": 5.0,
                "ready_time": 0.0,
                "due_time": 500.0,
                "service_time": 10.0,
                "priority": 2,
            },
        ],
        "vehicles": [
            {
                "id": "v1",
                "capacity": 15.0,
                "shift_start": 0.0,
                "shift_end": 1000.0,
            },
            {
                "id": "v2",
                "capacity": 15.0,
                "shift_start": 0.0,
                "shift_end": 1000.0,
            },
        ],
    }
