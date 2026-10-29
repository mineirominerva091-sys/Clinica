import pytest

from app import create_app
from app.models import Call, db


@pytest.fixture()
def client(tmp_path):
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret",
        "ADMIN_PASSWORD": "admin",
        "TV_TOKEN": "tv-token",
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'test.db'}",
    })
    with app.test_client() as test_client:
        test_client.post("/login", data={"password": "admin"})
        yield test_client
    with app.app_context():
        db.drop_all()


def test_queue_lifecycle_and_tv_status(client):
    response = client.post("/api/patients", json={"patient_name": "Ana", "registration": "1", "room": "Consultório 1"})
    assert response.status_code == 201
    call_id = response.json["item"]["id"]

    assert client.post("/api/calls/next").status_code == 200
    status = client.get("/api/tv/status?token=tv-token")
    assert status.status_code == 200
    assert status.json["current"]["patient_name"] == "Ana"
    first_event = status.json["current"]["event_token"]

    assert client.post(f"/api/calls/{call_id}/recall").status_code == 200
    recalled = client.get("/api/tv/status")
    assert recalled.status_code == 200
    assert recalled.json["current"]["event_token"] != first_event

    assert client.post(f"/api/calls/{call_id}/finish").status_code == 200
    assert client.get("/api/tv/status").json["current"] is None


def test_cannot_call_cancelled_or_finish_twice(client):
    response = client.post("/api/patients", json={"patient_name": "Bruno", "registration": "2", "room": "Consultório 2"})
    call_id = response.json["item"]["id"]
    assert client.post(f"/api/calls/{call_id}/cancel").status_code == 200
    assert client.post(f"/api/calls/{call_id}/call").status_code == 409
    assert client.post(f"/api/calls/{call_id}/finish").status_code == 409


def test_only_one_active_call(client):
    client.post("/api/patients", json={"patient_name": "Ana", "registration": "1", "room": "A"})
    client.post("/api/patients", json={"patient_name": "Bia", "registration": "2", "room": "B"})
    assert client.post("/api/calls/next").status_code == 200
    assert client.post("/api/calls/next").status_code == 200
    with client.application.app_context():
        assert db.session.query(Call).filter_by(status="chamado").count() == 1
