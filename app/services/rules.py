import uuid
from collections.abc import Sequence
from typing import NamedTuple

from sqlalchemy import select, tuple_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models import Alert, Telemetry

BATTERY_LOW_PCT = 15.0  # strictly below fires; exactly 15.0 is healthy
TEMP_HIGH_C = 70.0  # strictly above fires; exactly 70.0 is healthy


class AlertCandidate(NamedTuple):
    severity: str
    type_: str
    message: str


def evaluate_reading(reading: Telemetry) -> list[AlertCandidate]:
    """Pure rule evaluation for one reading; no database, trivially testable."""
    candidates: list[AlertCandidate] = []
    if reading.battery_pct < BATTERY_LOW_PCT:
        candidates.append(
            AlertCandidate(
                "high",
                "battery_low",
                f"battery at {reading.battery_pct:.1f}% (threshold {BATTERY_LOW_PCT:.0f}%)",
            )
        )
    if reading.temp_c > TEMP_HIGH_C:
        candidates.append(
            AlertCandidate(
                "critical",
                "temp_high",
                f"temperature at {reading.temp_c:.1f}C (threshold {TEMP_HIGH_C:.0f}C)",
            )
        )
    return candidates


def apply_rules(db: Session, readings: Sequence[Telemetry]) -> int:
    """Evaluate alert rules for freshly ingested readings; returns alerts created.

    Runs inside the caller's transaction and never commits: the batch's
    readings, liveness updates, and alerts land (or vanish) together.
    """

    pending: dict[tuple[uuid.UUID, str], dict[str, object]] = {}
    for reading in readings:
        for cand in evaluate_reading(reading):
            key = (reading.device_id, cand.type_)
            if key not in pending:
                pending[key] = {
                    "device_id": reading.device_id,
                    "ts": reading.ts,
                    "severity": cand.severity,
                    "type": cand.type_,  # database column name is "type"
                    "message": cand.message,
                }
    if not pending:
        return 0

    open_pairs = {
        (row[0], row[1])
        for row in db.execute(
            select(Alert.device_id, Alert.type_).where(
                Alert.resolved_at.is_(None),
                tuple_(Alert.device_id, Alert.type_).in_(list(pending)),
            )
        ).all()
    }
    to_insert = [row for key, row in pending.items() if key not in open_pairs]
    if not to_insert:
        return 0

    stmt = (
        pg_insert(Alert)
        .values(to_insert)
        .on_conflict_do_nothing(
            index_elements=[Alert.device_id, Alert.type_],
            index_where=Alert.resolved_at.is_(None),
        )
        .returning(Alert.id)
    )
    return len(db.execute(stmt).all())
