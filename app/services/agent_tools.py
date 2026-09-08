import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Alert, Device, MaintenanceTicket, Telemetry
from app.services.summarize import SILENT_AFTER_MIN

RUNBOOK_DIR = Path("docs/runbooks")

TOOLS: list[dict[str, Any]] = [
    {
        "name": "get_fleet_stats",
        "description": (
            "Fleet-wide health for the last N hours: totals, open alerts, "
            "silent devices, worst battery and temperature."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"window_hours": {"type": "integer", "default": 24}},
        },
    },
    {
        "name": "list_alerts",
        "description": (
            "Open alerts, newest first, optionally filtered by severity or device name."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "severity": {"type": "string"},
                "device": {"type": "string"},
                "window_hours": {"type": "integer", "default": 24},
            },
        },
    },
    {
        "name": "get_device_telemetry",
        "description": (
            "One device by name: aggregates over the window plus the last 10 raw readings."
        ),
        "input_schema": {
            "type": "object",
            "required": ["device"],
            "properties": {
                "device": {"type": "string"},
                "window_hours": {"type": "integer", "default": 24},
            },
        },
    },
    {
        "name": "search_runbooks",
        "description": (
            "Keyword search over operations runbooks. Returns the top matching excerpts."
        ),
        "input_schema": {
            "type": "object",
            "required": ["query"],
            "properties": {"query": {"type": "string"}},
        },
    },
    {
        "name": "create_maintenance_ticket",
        "description": (
            "Create a maintenance ticket for a device. Writes require human "
            "approval; without it the ticket is returned as proposed."
        ),
        "input_schema": {
            "type": "object",
            "required": ["device", "severity", "summary"],
            "properties": {
                "device": {"type": "string"},
                "severity": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "critical"],
                },
                "summary": {"type": "string"},
            },
        },
    },
]


def get_fleet_stats(db: Session, window_hours: int = 24) -> dict[str, Any]:
    now = datetime.now(UTC)
    since = now - timedelta(hours=window_hours)
    total = db.scalar(select(func.count(Device.id))) or 0
    open_alerts = db.scalar(select(func.count(Alert.id)).where(Alert.resolved_at.is_(None))) or 0
    cutoff = now - timedelta(minutes=SILENT_AFTER_MIN)
    silent = db.scalars(select(Device.name).where(Device.last_seen_at < cutoff).limit(10)).all()
    worst_batt = db.execute(
        select(Device.name, Telemetry.battery_pct)
        .join(Device, Telemetry.device_id == Device.id)
        .where(Telemetry.ts >= since)
        .order_by(Telemetry.battery_pct.asc())
        .limit(1)
    ).first()
    worst_temp = db.execute(
        select(Device.name, Telemetry.temp_c)
        .join(Device, Telemetry.device_id == Device.id)
        .where(Telemetry.ts >= since)
        .order_by(Telemetry.temp_c.desc())
        .limit(1)
    ).first()
    return {
        "total_devices": total,
        "open_alerts": open_alerts,
        "silent_devices": list(silent),
        "worst_battery": None
        if worst_batt is None
        else {"device": worst_batt[0], "battery_pct": worst_batt[1]},
        "max_temp": None
        if worst_temp is None
        else {"device": worst_temp[0], "temp_c": worst_temp[1]},
        "window_hours": window_hours,
    }


def list_alerts(
    db: Session, severity: str | None = None, device: str | None = None, window_hours: int = 24
) -> list[dict[str, Any]]:
    since = datetime.now(UTC) - timedelta(hours=window_hours)
    q = (
        select(Alert, Device.name)
        .join(Device, Alert.device_id == Device.id)
        .where(Alert.resolved_at.is_(None), Alert.ts >= since)
        .order_by(Alert.ts.desc())
        .limit(20)
    )
    if severity:
        q = q.where(Alert.severity == severity)
    if device:
        q = q.where(Device.name == device)
    return [
        {
            "id": a.id,
            "device": name,
            "type": a.type_,
            "severity": a.severity,
            "message": a.message,
            "ts": a.ts,
        }
        for a, name in db.execute(q).all()
    ]


def get_device_telemetry(db: Session, device: str, window_hours: int = 24) -> dict[str, Any]:
    dev = db.scalars(select(Device).where(Device.name == device)).first()
    if dev is None:
        return {"error": f"unknown device {device}"}
    since = datetime.now(UTC) - timedelta(hours=window_hours)
    stats = db.execute(
        select(
            func.count(Telemetry.id), func.min(Telemetry.battery_pct), func.max(Telemetry.temp_c)
        ).where(Telemetry.device_id == dev.id, Telemetry.ts >= since)
    ).one()
    samples = db.scalars(
        select(Telemetry)
        .where(Telemetry.device_id == dev.id)
        .order_by(Telemetry.ts.desc())
        .limit(10)
    ).all()
    return {
        "device": dev.name,
        "site": dev.site,
        "last_seen": dev.last_seen_at,
        "readings_in_window": stats[0],
        "battery_min": stats[1],
        "temp_max": stats[2],
        "recent": [
            {
                "ts": t.ts,
                "battery_pct": t.battery_pct,
                "temp_c": t.temp_c,
                "signal_rssi": t.signal_rssi,
            }
            for t in samples
        ],
    }


def search_runbooks(db: Session, query: str) -> list[dict[str, Any]]:
    terms = [w for w in re.findall(r"\w+", query.lower()) if len(w) > 2]
    results: list[dict[str, Any]] = []
    for path in sorted(RUNBOOK_DIR.glob("*.md")):
        text = path.read_text()
        low = text.lower()
        score = sum(low.count(t) for t in terms)
        if score:
            results.append({"runbook": path.name, "score": score, "excerpt": text[:400]})
    results.sort(key=lambda r: int(r["score"]), reverse=True)
    return results[:3] or [{"note": "no runbook matched"}]


def _create_ticket(
    db: Session,
    approve_writes: bool,
    device: str,
    severity: str,
    summary: str,
    run_id: int | None = None,
) -> dict[str, Any]:
    dev = db.scalars(select(Device).where(Device.name == device)).first()
    if dev is None:
        return {"error": f"unknown device {device}"}
    if not approve_writes:
        return {"status": "proposed", "device": device, "severity": severity, "summary": summary}
    ticket = MaintenanceTicket(
        device_id=dev.id,
        severity=severity,
        summary=summary,
        created_by_run=run_id,
        created_at=datetime.now(UTC),
    )
    db.add(ticket)
    db.flush()
    return {"status": "created", "ticket_id": ticket.id, "device": device}


READ_TOOLS: dict[str, Callable[..., Any]] = {
    "get_fleet_stats": get_fleet_stats,
    "list_alerts": list_alerts,
    "get_device_telemetry": get_device_telemetry,
    "search_runbooks": search_runbooks,
}


def run_tool(
    db: Session, name: str, args: dict[str, Any], approve_writes: bool, run_id: int | None = None
) -> Any:
    try:
        if name == "create_maintenance_ticket":
            return _create_ticket(db, approve_writes, run_id=run_id, **args)
        if name in READ_TOOLS:
            return READ_TOOLS[name](db, **args)
        return {"error": f"unknown tool {name}"}
    except Exception as exc:  # errors are results, never crashes
        return {"error": str(exc)}
