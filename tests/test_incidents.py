from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import get_settings
from app.services.summarize import build_incident_context


def _device(client: TestClient, name: str) -> str:
    return str(client.post("/devices", json={"name": name, "site": "zh"}).json()["id"])


def _seed_open_alert(client: TestClient) -> str:
    did = _device(client, "inc-gw-1")
    ts = datetime.now(UTC).isoformat()
    body = {
        "device_id": did,
        "ts": ts,
        "battery_pct": 5,  # < 15 -> rules engine opens battery_low
        "temp_c": 21,
        "signal_rssi": -70,
    }
    assert client.post("/telemetry", json=[body]).status_code == 201
    return did


def test_summary_503_without_key(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "")
    assert client.get("/incidents/summary").status_code == 503


def test_summary_ok_mocked(client: TestClient, monkeypatch) -> None:
    _seed_open_alert(client)
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "test-key")
    monkeypatch.setattr("app.services.summarize._call_claude", lambda ctx: "MOCK SUMMARY")
    r = client.get("/incidents/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["summary"] == "MOCK SUMMARY"
    assert body["alerts_open"] >= 1
    assert body["devices_affected"] >= 1


def test_context_builder_shape(client: TestClient, db_session: Session) -> None:
    _seed_open_alert(client)
    ctx = build_incident_context(db_session)
    assert {"open_alerts", "devices", "silent_devices", "fleet"} <= ctx.keys()
    assert ctx["fleet"]["total_devices"] >= 1
    assert ctx["open_alerts"][0]["type"] == "battery_low"
    assert ctx["open_alerts"][0]["device"] == "inc-gw-1"
