from dataclasses import dataclass, field
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AgentRun, MaintenanceTicket
from app.services.agent import investigate
from app.services.agent_tools import run_tool, search_runbooks


@dataclass
class FakeBlock:
    type: str
    text: str = ""
    name: str = ""
    input: dict[str, Any] = field(default_factory=dict)
    id: str = "toolu_1"


@dataclass
class FakeUsage:
    input_tokens: int = 100
    output_tokens: int = 50


@dataclass
class FakeResp:
    content: list[FakeBlock]
    stop_reason: str
    usage: FakeUsage = field(default_factory=FakeUsage)


class FakeClient:
    def __init__(self, script: list[FakeResp]):
        self._script = script
        self.messages = self

    def create(self, **kwargs: Any) -> FakeResp:
        return self._script.pop(0) if len(self._script) > 1 else self._script[0]


def _device(client: TestClient, name: str) -> str:
    return str(client.post("/devices", json={"name": name, "site": "zh"}).json()["id"])


def test_search_runbooks_finds_battery(db_session: Session) -> None:
    hits = search_runbooks(db_session, "battery drain low")
    assert hits[0]["runbook"] == "battery.md"


def test_write_gate_proposed_vs_created(client: TestClient, db_session: Session) -> None:
    _device(client, "agw-1")
    out = run_tool(
        db_session,
        "create_maintenance_ticket",
        {"device": "agw-1", "severity": "high", "summary": "x"},
        approve_writes=False,
    )
    assert out["status"] == "proposed"
    assert db_session.scalars(select(MaintenanceTicket)).first() is None
    out = run_tool(
        db_session,
        "create_maintenance_ticket",
        {"device": "agw-1", "severity": "high", "summary": "x"},
        approve_writes=True,
    )
    assert out["status"] == "created"
    assert db_session.scalars(select(MaintenanceTicket)).first() is not None


def test_unknown_tool_is_error_result(db_session: Session) -> None:
    out = run_tool(db_session, "launch_missiles", {}, approve_writes=True)
    assert "error" in out


def test_loop_completes_and_persists(client: TestClient, db_session: Session, monkeypatch) -> None:
    _device(client, "agw-2")
    script = [
        FakeResp(
            content=[
                FakeBlock(type="tool_use", name="get_fleet_stats", input={"window_hours": 24})
            ],
            stop_reason="tool_use",
        ),
        FakeResp(
            content=[FakeBlock(type="text", text="All clear, evidence: 1 device.")],
            stop_reason="end_turn",
        ),
    ]
    monkeypatch.setattr("app.services.agent._get_client", lambda: FakeClient(script))
    out = investigate(db_session, "how is the fleet?")
    assert out["status"] == "completed"
    assert out["usage"]["iterations"] == 1
    assert out["trace"][0]["tool"] == "get_fleet_stats"
    run = db_session.get(AgentRun, out["run_id"])
    assert run is not None and run.findings.startswith("All clear")


def test_loop_caps_at_eight(db_session: Session, monkeypatch) -> None:
    forever = [
        FakeResp(
            content=[FakeBlock(type="tool_use", name="get_fleet_stats", input={})],
            stop_reason="tool_use",
        )
    ]
    monkeypatch.setattr("app.services.agent._get_client", lambda: FakeClient(forever))
    out = investigate(db_session, "loop forever please")
    assert out["status"] == "capped"
    assert out["usage"]["iterations"] == 8


def test_endpoint_shape(client: TestClient, db_session: Session, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "test-key")
    script = [FakeResp(content=[FakeBlock(type="text", text="done")], stop_reason="end_turn")]
    monkeypatch.setattr("app.services.agent._get_client", lambda: FakeClient(script))
    r = client.post("/agent/investigate", json={"question": "status of the fleet?"})
    assert r.status_code == 200
    body = r.json()
    assert {"run_id", "status", "findings", "actions", "trace", "usage"} <= body.keys()
