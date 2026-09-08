from fastapi.testclient import TestClient

from app.config import get_settings


def test_request_id_minted_and_echoed(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.headers.get("X-Request-ID")
    r2 = client.get("/healthz", headers={"X-Request-ID": "abc123"})
    assert r2.headers["X-Request-ID"] == "abc123"


def test_error_shape_on_404(client: TestClient) -> None:
    r = client.get("/devices/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == 404
    assert body["error"]["request_id"]


def test_metrics_endpoint(client: TestClient) -> None:
    client.get("/healthz")
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "http_requests_total" in r.text


def test_incidents_api_key_gate(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "fleetpulse_api_key", "sekret")
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "test-key")
    assert client.get("/incidents/summary").status_code == 401


def test_metrics_use_route_template_not_raw_path(client: TestClient) -> None:
    client.get("/devices/00000000-0000-0000-0000-000000000000")
    client.get("/nonsense")
    text = client.get("/metrics").text
    assert 'path="/devices/{device_id}"' in text
    assert 'path="unmatched"' in text
    assert "00000000-0000" not in text
