from fastapi.testclient import TestClient
import pytest
from api.database import DeliveryDatabase, get_db
from api.main import app

@pytest.fixture()
def client(tmp_path):
    test_db = DeliveryDatabase(db_path=str(tmp_path / "test.db"))
    app.dependency_overrides[get_db] = lambda: test_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

def test_delivery_workflow(client):
    res = client.post("/delivery/auth/login", json={"username": "admin", "password": "admin123"})
    assert res.status_code == 200
