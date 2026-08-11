"""Demo-data seeder: drives the REAL ingest pipeline so rules fire and
last_seen_at advances exactly as in production.

Injected anomalies (deterministic via --rng-seed):
  device 1: battery death   -- declines 90% -> 5%, crossing the 15% rule
  device 2: temperature spike -- >70C for the final two hours
  device 3: goes silent     -- no readings in the final two hours
"""

import argparse
import random
import sys
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db import get_sessionmaker
from app.models import Device
from app.schemas import TelemetryIn
from app.services.ingest import ingest_batch

SITES = ["zurich-west", "zurich-east", "lakeside"]
STEP = timedelta(minutes=10)
SILENT_GAP = timedelta(hours=2)


class SeedError(RuntimeError):
    pass


def seed(
    db: Session, *, devices: int = 25, hours: int = 72, rng_seed: int = 42, reset: bool = False
) -> tuple[int, int, int]:
    """Populate the database; returns (devices, readings, alerts_created)."""
    if devices < 3:
        raise SeedError("need at least 3 devices to place the three anomalies")
    existing = db.scalar(select(func.count(Device.id))) or 0
    if existing and not reset:
        raise SeedError(f"database already has {existing} devices; rerun with --reset")
    if existing:
        db.execute(delete(Device))  # telemetry and alerts follow via ON DELETE CASCADE
        db.commit()

    rng = random.Random(rng_seed)
    now = datetime.now(UTC)
    start = now - timedelta(hours=hours)

    fleet = [
        Device(name=f"gw-{i:03d}", site=SITES[i % len(SITES)], hw_model="FP-100", firmware="1.4.2")
        for i in range(1, devices + 1)
    ]
    db.add_all(fleet)
    db.commit()
    battery_dev, temp_dev, silent_dev = fleet[0], fleet[1], fleet[2]

    total_readings = 0
    total_alerts = 0
    steps = int(timedelta(hours=hours) / STEP)
    for device in fleet:
        battery = rng.uniform(70.0, 100.0)
        readings: list[TelemetryIn] = []
        for i in range(steps + 1):
            ts = start + i * STEP
            if device is silent_dev and ts > now - SILENT_GAP:
                break  # the silent device simply stops talking
            if device is battery_dev:
                battery = 90.0 - (85.0 * i / steps)  # linear death: 90% -> 5%
            else:
                battery = max(5.0, battery - rng.uniform(0.0, 0.05))
            temp = rng.uniform(18.0, 26.0)
            if device is temp_dev and ts > now - timedelta(hours=2):
                temp = rng.uniform(74.0, 85.0)  # the spike
            readings.append(
                TelemetryIn(
                    device_id=device.id,
                    ts=ts,
                    battery_pct=round(battery, 1),
                    temp_c=round(temp, 1),
                    signal_rssi=rng.randint(-95, -55),
                )
            )
        if readings:
            ingested, created = ingest_batch(db, readings)
            total_readings += ingested
            total_alerts += created
    return len(fleet), total_readings, total_alerts


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--devices", type=int, default=25)
    parser.add_argument("--hours", type=int, default=72)
    parser.add_argument("--rng-seed", type=int, default=42)
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args(argv)

    db = get_sessionmaker()()
    try:
        n_devices, n_readings, n_alerts = seed(
            db, devices=args.devices, hours=args.hours, rng_seed=args.rng_seed, reset=args.reset
        )
    except SeedError as exc:
        print(f"seed refused: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    finally:
        db.close()
    print(
        f"seeded {n_devices} devices, {n_readings} readings, {n_alerts} alerts "
        f"(anomalies: gw-001 battery death, gw-002 temp spike, gw-003 silent)"
    )


if __name__ == "__main__":
    main()
