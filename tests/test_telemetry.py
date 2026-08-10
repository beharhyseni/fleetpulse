import uuid
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Device, Telemetry


def _device(client: TestClient, name: str, site: str = "zh") -> str:
    created = client.post("/devices", json={"name": name, "site": site})
    assert created.status_code == 201
    return str(created.json()["id"])


def _reading(device_id: str, ts: str, **overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "device_id": device_id,
        "ts": ts,
        "battery_pct": 80.0,
        "temp_c": 21.0,
        "signal_rssi": -70,
    }
    base.update(overrides)
    return base


def test_ingest_happy_path(client: TestClient, db_session: Session) -> None:
    did = _device(client, "gw-b1")
    response = client.post(
        "/telemetry",
        json=[
            _reading(did, "2026-08-08T18:00:00Z"),
            _reading(did, "2026-08-08T18:10:00Z", battery_pct=79.5),
        ],
    )
    assert response.status_code == 201
    assert response.json() == {"ingested": 2, "alerts_created": 0}
    rows = db_session.scalars(select(Telemetry)).all()
    assert len(rows) == 2


def test_last_seen_advances_to_max_per_device(client: TestClient, db_session: Session) -> None:
    d1, d2 = _device(client, "gw-b2a"), _device(client, "gw-b2b")
    client.post(
        "/telemetry",
        json=[
            _reading(d1, "2026-08-08T18:00:00Z"),
            _reading(d2, "2026-08-08T18:20:00Z"),
            _reading(d1, "2026-08-08T18:30:00Z"),  # d1's max, out of order in the batch
        ],
    )

    db_session.expire_all()
    seen1 = db_session.get(Device, uuid.UUID(d1)).last_seen_at  # type: ignore[union-attr]
    seen2 = db_session.get(Device, uuid.UUID(d2)).last_seen_at  # type: ignore[union-attr]
    assert seen1 == datetime(2026, 8, 8, 18, 30, tzinfo=UTC)
    assert seen2 == datetime(2026, 8, 8, 18, 20, tzinfo=UTC)


def test_replay_batch_does_not_regress_last_seen(client: TestClient, db_session: Session) -> None:
    did = _device(client, "gw-b3")
    client.post("/telemetry", json=[_reading(did, "2026-08-08T18:00:00Z")])
    client.post("/telemetry", json=[_reading(did, "2026-08-08T09:00:00Z")])  # historical replay
    db_session.expire_all()
    seen = db_session.get(Device, uuid.UUID(did)).last_seen_at  # type: ignore[union-attr]
    assert seen == datetime(2026, 8, 8, 18, 0, tzinfo=UTC)


def test_unknown_devices_404_names_ids(client: TestClient) -> None:
    ghost = "00000000-0000-0000-0000-000000000001"
    response = client.post("/telemetry", json=[_reading(ghost, "2026-08-08T18:00:00Z")])
    assert response.status_code == 404
    assert ghost in response.json()["detail"]


def test_empty_batch_is_422(client: TestClient) -> None:
    assert client.post("/telemetry", json=[]).status_code == 422


def test_naive_timestamp_is_422(client: TestClient) -> None:
    did = _device(client, "gw-b6")
    response = client.post("/telemetry", json=[_reading(did, "2026-08-08T18:00:00")])
    assert response.status_code == 422


def test_omitted_payload_lands_as_empty_dict(client: TestClient, db_session: Session) -> None:
    did = _device(client, "gw-b7")
    client.post("/telemetry", json=[_reading(did, "2026-08-08T18:00:00Z")])
    row = db_session.scalars(select(Telemetry)).one()
    assert row.payload == {}
