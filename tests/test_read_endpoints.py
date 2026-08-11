import uuid
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Alert


def _device(client: TestClient, name: str) -> str:
    return str(client.post("/devices", json={"name": name, "site": "zh"}).json()["id"])


def _post(client: TestClient, did: str, ts: str, **over: object) -> None:
    body: dict[str, object] = {
        "device_id": did,
        "ts": ts,
        "battery_pct": 80,
        "temp_c": 21,
        "signal_rssi": -70,
    }
    body.update(over)
    assert client.post("/telemetry", json=[body]).status_code == 201


def test_window_query_filters_and_orders(client: TestClient) -> None:
    did = _device(client, "d1")
    for ts in ("2026-08-09T08:00:00Z", "2026-08-09T10:00:00Z", "2026-08-09T12:00:00Z"):
        _post(client, did, ts)
    rows = client.get(
        f"/devices/{did}/telemetry",
        params={"from": "2026-08-09T09:00:00Z", "to": "2026-08-09T11:00:00Z"},
    ).json()
    assert [r["ts"] for r in rows] == ["2026-08-09T10:00:00Z"]
    all_rows = client.get(f"/devices/{did}/telemetry").json()
    assert [r["ts"] for r in all_rows] == [
        "2026-08-09T12:00:00Z",
        "2026-08-09T10:00:00Z",
        "2026-08-09T08:00:00Z",
    ]


def test_window_query_ghost_device_404(client: TestClient) -> None:
    assert client.get(f"/devices/{uuid.uuid4()}/telemetry").status_code == 404


def test_window_query_limit(client: TestClient) -> None:
    did = _device(client, "d3")
    for hour in (8, 9, 10):
        _post(client, did, f"2026-08-09T{hour:02d}:00:00Z")
    assert len(client.get(f"/devices/{did}/telemetry", params={"limit": 2}).json()) == 2


def test_alerts_filters(client: TestClient, db_session: Session) -> None:
    did = _device(client, "d4")
    _post(client, did, "2026-08-09T08:00:00Z", battery_pct=10)  # -> battery_low (high)
    _post(client, did, "2026-08-09T08:10:00Z", temp_c=80)  # -> temp_high (critical)
    other = _device(client, "d5")
    _post(client, other, "2026-08-09T08:20:00Z", battery_pct=9)

    assert len(client.get("/alerts").json()) == 3
    crit = client.get("/alerts", params={"severity": "critical"}).json()
    assert [a["type"] for a in crit] == ["temp_high"]
    assert len(client.get("/alerts", params={"device_id": did}).json()) == 2

    alert = db_session.scalars(select(Alert).where(Alert.device_id == uuid.UUID(other))).one()
    alert.resolved_at = datetime.now(UTC)
    db_session.flush()
    assert len(client.get("/alerts", params={"open": "true"}).json()) == 2
    assert len(client.get("/alerts", params={"open": "false"}).json()) == 1


def test_alert_json_uses_clean_type_key(client: TestClient) -> None:
    did = _device(client, "d6")
    _post(client, did, "2026-08-09T08:00:00Z", battery_pct=5)
    body = client.get("/alerts").json()[0]
    assert "type" in body and "type_" not in body
