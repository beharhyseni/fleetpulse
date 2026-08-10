import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models import Device, Telemetry
from app.schemas import TelemetryIn
from app.services.rules import apply_rules


class UnknownDevicesError(Exception):
    def __init__(self, ids: set[uuid.UUID]) -> None:
        self.ids = sorted(ids)
        super().__init__(f"unknown device ids: {', '.join(str(i) for i in self.ids)}")


def ingest_batch(db: Session, readings: Sequence[TelemetryIn]) -> tuple[int, int]:
    batch_ids = {r.device_id for r in readings}
    known = set(db.scalars(select(Device.id).where(Device.id.in_(batch_ids))).all())
    unknown = batch_ids - known
    if unknown:
        raise UnknownDevicesError(unknown)
    rows = [Telemetry(**r.model_dump()) for r in readings]
    db.add_all(rows)
    db.flush()

    max_ts_by_device: dict[uuid.UUID, datetime] = {}
    for r in readings:
        prev = max_ts_by_device.get(r.device_id)
        if prev is None or r.ts > prev:
            max_ts_by_device[r.device_id] = r.ts
    for device_id, max_ts in max_ts_by_device.items():
        db.execute(
            update(Device)
            .where(Device.id == device_id)
            .values(last_seen_at=func.greatest(Device.last_seen_at, max_ts))
        )

    created = apply_rules(db, rows)
    db.commit()
    return len(rows), created
