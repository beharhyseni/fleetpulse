from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Alert, Device, Telemetry
from app.services.rules import apply_rules


def _device(db: Session, name: str) -> Device:
    device = Device(name=name, site="test-site")
    db.add(device)
    db.flush()
    return device


def _reading(
    db: Session,
    device: Device,
    *,
    battery: float = 80.0,
    temp: float = 21.0,
    ts: datetime | None = None,
) -> Telemetry:
    row = Telemetry(
        device_id=device.id,
        ts=ts or datetime.now(UTC),
        battery_pct=battery,
        temp_c=temp,
        signal_rssi=-70,
    )
    db.add(row)
    db.flush()
    return row


def test_battery_low_fires_with_correct_fields(db_session: Session) -> None:
    device = _device(db_session, "r1")
    reading = _reading(db_session, device, battery=12.0)
    assert apply_rules(db_session, [reading]) == 1
    alert = db_session.scalars(select(Alert)).one()
    assert alert.device_id == device.id
    assert alert.severity == "high"
    assert alert.type_ == "battery_low"
    assert alert.ts == reading.ts
    assert alert.resolved_at is None
    assert "12.0%" in alert.message


def test_temp_high_fires_critical(db_session: Session) -> None:
    device = _device(db_session, "r2")
    reading = _reading(db_session, device, temp=75.0)
    assert apply_rules(db_session, [reading]) == 1
    alert = db_session.scalars(select(Alert)).one()
    assert (alert.severity, alert.type_) == ("critical", "temp_high")


def test_healthy_reading_creates_nothing(db_session: Session) -> None:
    device = _device(db_session, "r3")
    reading = _reading(db_session, device)
    assert apply_rules(db_session, [reading]) == 0
    assert db_session.scalars(select(Alert)).all() == []


def test_same_condition_twice_in_one_batch_is_one_alert(db_session: Session) -> None:
    device = _device(db_session, "r4")
    readings = [
        _reading(db_session, device, battery=10.0),
        _reading(db_session, device, battery=9.0, ts=datetime.now(UTC) + timedelta(minutes=10)),
    ]
    assert apply_rules(db_session, readings) == 1
    assert len(db_session.scalars(select(Alert)).all()) == 1


def test_condition_persisting_into_next_batch_creates_nothing(db_session: Session) -> None:
    device = _device(db_session, "r5")
    assert apply_rules(db_session, [_reading(db_session, device, battery=10.0)]) == 1
    assert apply_rules(db_session, [_reading(db_session, device, battery=9.0)]) == 0
    assert len(db_session.scalars(select(Alert)).all()) == 1


def test_resolved_alert_allows_a_new_one(db_session: Session) -> None:
    device = _device(db_session, "r6")
    assert apply_rules(db_session, [_reading(db_session, device, battery=10.0)]) == 1
    alert = db_session.scalars(select(Alert)).one()
    alert.resolved_at = datetime.now(UTC)
    db_session.flush()
    assert apply_rules(db_session, [_reading(db_session, device, battery=8.0)]) == 1
    assert len(db_session.scalars(select(Alert)).all()) == 2


def test_exact_boundary_values_are_healthy(db_session: Session) -> None:
    device = _device(db_session, "r7")
    reading = _reading(db_session, device, battery=15.0, temp=70.0)
    assert apply_rules(db_session, [reading]) == 0


def test_one_reading_can_trigger_both_rules(db_session: Session) -> None:
    device = _device(db_session, "r8")
    reading = _reading(db_session, device, battery=10.0, temp=80.0)
    assert apply_rules(db_session, [reading]) == 2
    types = {a.type_ for a in db_session.scalars(select(Alert)).all()}
    assert types == {"battery_low", "temp_high"}
