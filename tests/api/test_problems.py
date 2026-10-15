"""Unit tests for Problem CRUD endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_create_and_get_problem(client: TestClient, sample_problem_payload: dict) -> None:
    """Verify problem creation, bounding box calculation, and retrieval."""
    # 1. Create problem
    resp = client.post("/problems", json=sample_problem_payload)
    assert resp.status_code == 201
    created = resp.json()
    assert created["id"] == "test_city_4"
    assert created["num_customers"] == 4
    assert created["num_vehicles"] == 2
    assert created["bbox"] == {
        "min_lat": 22.295,
        "min_lon": 73.17,
        "max_lat": 22.32,
        "max_lon": 73.19,
    }

    # 2. Get problem by ID
    get_resp = client.get("/problems/test_city_4")
    assert get_resp.status_code == 200
    prob_data = get_resp.json()
    assert prob_data["id"] == "test_city_4"
    assert len(prob_data["customers"]) == 4

    # 3. Duplicate creation conflict
    dup_resp = client.post("/problems", json=sample_problem_payload)
    assert dup_resp.status_code == 409


def test_list_and_delete_problem(client: TestClient, sample_problem_payload: dict) -> None:
    """Verify listing problems and deletion."""
    client.post("/problems", json=sample_problem_payload)

    # List
    list_resp = client.get("/problems")
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert len(items) == 1
    assert items[0]["id"] == "test_city_4"

    # Delete
    del_resp = client.delete("/problems/test_city_4")
    assert del_resp.status_code == 204

    # Confirm deletion
    get_resp = client.get("/problems/test_city_4")
    assert get_resp.status_code == 404


def test_problem_not_found(client: TestClient) -> None:
    """Verify 404 for unknown problem."""
    resp = client.get("/problems/nonexistent_problem_xyz")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()
