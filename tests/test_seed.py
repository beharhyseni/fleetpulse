import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Alert, Device, Telemetry
from app.seed import SeedError, seed


def test_seed_populates_and_fires_anomalies(db_session: Session) -> None:
    n_devices, n_readings, n_alerts = seed(db_session, devices=4, hours=3, rng_seed=1)
    assert n_devices == 4
    assert n_readings == db_session.scalar(select(func.count(Telemetry.id)))
    assert n_alerts >= 2  # battery death + temp spike
    types = {a.type_ for a in db_session.scalars(select(Alert)).all()}
    assert {"battery_low", "temp_high"} <= types
    silent = db_session.scalars(select(Device).where(Device.name == "gw-003")).one()
    talkative = db_session.scalars(select(Device).where(Device.name == "gw-004")).one()
    assert silent.last_seen_at is not None and talkative.last_seen_at is not None
    assert silent.last_seen_at < talkative.last_seen_at


def test_seed_refuses_nonempty_without_reset(db_session: Session) -> None:
    seed(db_session, devices=3, hours=1, rng_seed=1)
    with pytest.raises(SeedError):
        seed(db_session, devices=3, hours=1, rng_seed=1)
    n_devices, _, _ = seed(db_session, devices=3, hours=1, rng_seed=1, reset=True)
    assert n_devices == 3
