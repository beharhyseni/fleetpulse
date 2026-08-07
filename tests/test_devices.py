from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Device


def test_create_and_get_device(client: TestClient) -> None:
    created = client.post("/devices", json={"name": "gw-001", "site": "zurich-west"})
    assert created.status_code == 201
    body = created.json()
    assert body["name"] == "gw-001"
    assert body["status"] == "offline"  # never seen yet

    fetched = client.get(f"/devices/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["site"] == "zurich-west"


def test_duplicate_name_is_409(client: TestClient) -> None:
    assert client.post("/devices", json={"name": "gw-dup", "site": "a"}).status_code == 201
    assert client.post("/devices", json={"name": "gw-dup", "site": "b"}).status_code == 409


def test_missing_device_is_404(client: TestClient) -> None:
    assert client.get("/devices/00000000-0000-0000-0000-000000000000").status_code == 404


def test_list_filters_by_site(client: TestClient) -> None:
    client.post("/devices", json={"name": "a-1", "site": "alpha"})
    client.post("/devices", json={"name": "b-1", "site": "beta"})
    names = [d["name"] for d in client.get("/devices", params={"site": "alpha"}).json()]
    assert names == ["a-1"]


def test_status_derivation(client: TestClient, db_session: Session) -> None:
    fresh = Device(name="fresh", site="s", last_seen_at=datetime.now(UTC))
    stale = Device(name="stale", site="s", last_seen_at=datetime.now(UTC) - timedelta(minutes=30))
    gone = Device(name="gone", site="s", last_seen_at=datetime.now(UTC) - timedelta(hours=3))
    db_session.add_all([fresh, stale, gone])
    db_session.commit()

    by_name = {d["name"]: d["status"] for d in client.get("/devices").json()}
    assert by_name == {"fresh": "online", "stale": "stale", "gone": "offline"}
