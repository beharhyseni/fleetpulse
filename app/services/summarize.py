import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from anthropic import Anthropic
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Alert, Device, Telemetry

MODEL = "claude-sonnet-4-6"
WINDOW_HOURS = 24
SILENT_AFTER_MIN = 120

SYSTEM_PROMPT = (
    "You are the incident summarizer for FleetPulse, an IoT fleet monitor. "
    "Use ONLY the JSON provided by the user. Never invent devices, numbers, or causes "
    "that are not in the data. Cite device names and alert ids, e.g. (alert #12). "
    "Output: (1) a one-line fleet headline; (2) one short paragraph per open incident: "
    "what happened, the evidence, a cautious likely cause, and the next check to run; "
    "(3) mention silent devices if any. If there are no open alerts and no silent "
    "devices, reply with a single all-clear sentence."
)


def build_incident_context(db: Session) -> dict[str, Any]:
    now = datetime.now(UTC)
    since = now - timedelta(hours=WINDOW_HOURS)

    # 1) open alerts + their devices, one JOIN
    rows = db.execute(
        select(Alert, Device)
        .join(Device, Alert.device_id == Device.id)
        .where(Alert.resolved_at.is_(None))
        .order_by(Alert.ts.desc())
        .limit(20)
    ).all()

    open_alerts = [
        {
            "id": a.id,
            "type": a.type_,
            "severity": a.severity,
            "device": d.name,
            "message": a.message,
            "created_at": a.ts,
        }
        for a, d in rows
    ]
    affected: dict[uuid.UUID, Device] = {d.id: d for _, d in rows}
    device_ids = list(affected.keys())

    # 2) per-device aggregates, one GROUP BY
    stats_by_id: dict[uuid.UUID, Any] = {}
    if device_ids:
        stats_rows = db.execute(
            select(
                Telemetry.device_id,
                func.count(Telemetry.id),
                func.min(Telemetry.battery_pct),
                func.max(Telemetry.temp_c),
            )
            .where(Telemetry.device_id.in_(device_ids), Telemetry.ts >= since)
            .group_by(Telemetry.device_id)
        ).all()
        stats_by_id = {r[0]: r for r in stats_rows}

    # 3) latest reading per device, one DISTINCT ON (PostgreSQL)
    latest_by_id: dict[uuid.UUID, Telemetry] = {}
    if device_ids:
        latest_rows = db.scalars(
            select(Telemetry)
            .where(Telemetry.device_id.in_(device_ids))
            .order_by(Telemetry.device_id, Telemetry.ts.desc())
            .distinct(Telemetry.device_id)
        ).all()
        latest_by_id = {t.device_id: t for t in latest_rows}

    devices: dict[str, dict[str, Any]] = {}
    for dev_id, dev in affected.items():
        s = stats_by_id.get(dev_id)
        t = latest_by_id.get(dev_id)
        devices[dev.name] = {
            "site": dev.site,
            "last_seen": dev.last_seen_at,
            "readings_24h": s[1] if s else 0,
            "battery_min_24h": s[2] if s else None,
            "temp_max_24h": s[3] if s else None,
            "latest": None
            if t is None
            else {
                "ts": t.ts,
                "battery": t.battery_pct,
                "temp_c": t.temp_c,
            },
        }

    # 4) silent devices + 5) fleet count
    cutoff = now - timedelta(minutes=SILENT_AFTER_MIN)
    silent = db.scalars(select(Device).where(Device.last_seen_at < cutoff)).all()

    return {
        "generated_at": now,
        "open_alerts": open_alerts,
        "devices": devices,
        "silent_devices": [
            {"name": d.name, "site": d.site, "last_seen": d.last_seen_at} for d in silent
        ],
        "fleet": {"total_devices": db.scalar(select(func.count(Device.id)))},
    }


def _call_claude(context: dict[str, Any]) -> str:
    client = Anthropic(api_key=get_settings().anthropic_api_key)
    resp = client.messages.create(
        model=MODEL,
        max_tokens=700,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": json.dumps(context, default=str)}],
    )
    return "".join(b.text for b in resp.content if b.type == "text")


def summarize_incidents(db: Session) -> dict[str, Any]:
    context = build_incident_context(db)
    return {
        "generated_at": context["generated_at"],
        "model": MODEL,
        "summary": _call_claude(context),
        "alerts_open": len(context["open_alerts"]),
        "devices_affected": len(context["devices"]),
        "silent_devices": len(context["silent_devices"]),
    }
