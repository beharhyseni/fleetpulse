"""Agent eval harness. Costs real tokens; run deliberately via `make eval`.

Each scenario seeds a fresh known anomaly, runs the agent, and scores the
findings against ground truth: did it name the right device, identify the
right cause, and invent nothing?
"""

import argparse
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete

from app.db import get_sessionmaker
from app.models import AgentRun, Alert, Device, MaintenanceTicket, Telemetry
from app.services.agent import investigate


@dataclass
class Scenario:
    name: str
    question: str
    seed: "callable"
    expect_device: str
    expect_any: list[str]  # at least one must appear in findings
    forbid: list[str] = field(default_factory=list)  # must NOT appear


def _wipe(db) -> None:
    for table in (MaintenanceTicket, AgentRun, Alert, Telemetry, Device):
        db.execute(delete(table))
    db.commit()


def _mk_device(db, name: str, site: str, last_seen_min_ago: int = 0) -> Device:
    dev = Device(
        name=name,
        site=site,
        last_seen_at=datetime.now(UTC) - timedelta(minutes=last_seen_min_ago),
    )
    db.add(dev)
    db.flush()
    return dev


def _readings(
    db, dev: Device, hours: int, battery=lambda i: 80.0, temp=lambda i: 21.0, rssi=lambda i: -70
) -> None:
    now = datetime.now(UTC)
    rows = [
        Telemetry(
            device_id=dev.id,
            ts=now - timedelta(minutes=10 * i),
            battery_pct=battery(i),
            temp_c=temp(i),
            signal_rssi=rssi(i),
        )
        for i in range(hours * 6)
    ]
    db.add_all(rows)
    db.commit()


# ---- scenario seeders: each paints one unambiguous root cause ----


def seed_battery_drain(db) -> None:
    dev = _mk_device(db, "ev-batt", "zurich-east")
    _readings(db, dev, 24, battery=lambda i: min(95.0, 4.0 + i * 0.65))
    db.add(
        Alert(
            device_id=dev.id,
            ts=datetime.now(UTC) - timedelta(hours=6),
            severity="high",
            type_="battery_low",
            message="battery at 14.9% (threshold 15%)",
        )
    )
    db.commit()


def seed_overheat(db) -> None:
    dev = _mk_device(db, "ev-hot", "lakeside")
    _readings(db, dev, 24, temp=lambda i: 82.0 if i < 12 else 22.0)
    db.add(
        Alert(
            device_id=dev.id,
            ts=datetime.now(UTC) - timedelta(hours=2),
            severity="critical",
            type_="temp_high",
            message="temperature 82.0C (threshold 70C)",
        )
    )
    db.commit()


def seed_silent_rssi(db) -> None:
    dev = _mk_device(db, "ev-quiet", "zurich-west", last_seen_min_ago=180)
    now = datetime.now(UTC)
    rows = [
        Telemetry(
            device_id=dev.id,
            ts=now - timedelta(minutes=180 + 10 * i),
            battery_pct=85.0,
            temp_c=21.0,
            signal_rssi=-70 - (0 if i > 6 else (7 - i) * 6),
        )
        for i in range(24)
    ]
    db.add_all(rows)
    db.commit()


def seed_healthy_fleet(db) -> None:
    for n in ("ev-ok-1", "ev-ok-2", "ev-ok-3"):
        _readings(db, _mk_device(db, n, "zurich-east"), 12)


def seed_silent_healthy_radio(db) -> None:
    dev = _mk_device(db, "ev-gone", "lakeside", last_seen_min_ago=240)
    now = datetime.now(UTC)
    rows = [
        Telemetry(
            device_id=dev.id,
            ts=now - timedelta(minutes=240 + 10 * i),
            battery_pct=90.0,
            temp_c=20.0,
            signal_rssi=-62,
        )
        for i in range(24)
    ]
    db.add_all(rows)
    db.commit()


def seed_two_problems(db) -> None:
    seed_battery_drain(db)
    hot = _mk_device(db, "ev-hot2", "lakeside")
    _readings(db, hot, 24, temp=lambda i: 85.0 if i < 6 else 23.0)
    db.add(
        Alert(
            device_id=hot.id,
            ts=datetime.now(UTC) - timedelta(hours=1),
            severity="critical",
            type_="temp_high",
            message="temperature 85.0C (threshold 70C)",
        )
    )
    db.commit()


def seed_resolved_only(db) -> None:
    dev = _mk_device(db, "ev-fixed", "zurich-east")
    _readings(db, dev, 24)
    db.add(
        Alert(
            device_id=dev.id,
            ts=datetime.now(UTC) - timedelta(hours=20),
            severity="high",
            type_="battery_low",
            message="battery at 12% (threshold 15%)",
            resolved_at=datetime.now(UTC) - timedelta(hours=18),
        )
    )
    db.commit()


def seed_weak_signal_no_gap(db) -> None:
    dev = _mk_device(db, "ev-weak", "zurich-west")
    _readings(db, dev, 24, rssi=lambda i: -108)


SCENARIOS = [
    Scenario(
        "battery_drain",
        "why is ev-batt alerting?",
        seed_battery_drain,
        "ev-batt",
        ["battery", "drain", "charg"],
        forbid=["overheat"],
    ),
    Scenario(
        "overheat",
        "investigate the temperature alert",
        seed_overheat,
        "ev-hot",
        ["temp", "heat", "cool", "vent"],
    ),
    Scenario(
        "silent_rssi",
        "why did ev-quiet go silent?",
        seed_silent_rssi,
        "ev-quiet",
        ["silent", "rssi", "signal", "connect", "antenna", "carrier"],
    ),
    Scenario(
        "healthy",
        "anything wrong with the fleet?",
        seed_healthy_fleet,
        "",
        ["no open alert", "healthy", "no issue", "all clear", "nominal"],
        forbid=["ev-batt", "ev-hot", "critical"],
    ),
    Scenario(
        "silent_healthy_radio",
        "why did ev-gone stop reporting?",
        seed_silent_healthy_radio,
        "ev-gone",
        ["power", "outage", "silent", "offline"],
    ),
    Scenario("two_problems", "triage the fleet briefly", seed_two_problems, "ev-batt", ["ev-hot2"]),
    Scenario(
        "resolved_only",
        "any active incidents?",
        seed_resolved_only,
        "",
        ["no open", "resolved", "no active", "clear"],
        forbid=["dispatch immediately"],
    ),
    Scenario(
        "weak_signal",
        "assess connectivity health",
        seed_weak_signal_no_gap,
        "ev-weak",
        ["-108", "weak", "signal", "rssi"],
    ),
]


def score(sc: Scenario, findings: str) -> tuple[bool, str]:
    low = findings.lower()
    if sc.expect_device and sc.expect_device not in low:
        return False, f"missing device {sc.expect_device}"
    if not any(k.lower() in low for k in sc.expect_any):
        return False, f"none of {sc.expect_any} present"
    for bad in sc.forbid:
        if bad.lower() in low:
            return False, f"forbidden term present: {bad}"
    for ghost in ("gw-0", "device-x"):
        if ghost in low:
            return False, f"invented device reference: {ghost}"
    return True, "ok"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="run a single scenario by name")
    args = parser.parse_args()

    maker = get_sessionmaker()
    results, total_in, total_out = [], 0, 0

    for sc in SCENARIOS:
        if args.only and sc.name != args.only:
            continue
        with maker() as db:
            _wipe(db)
            sc.seed(db)
            out = investigate(db, sc.question)
            ok, why = score(sc, out["findings"])
            usage = out["usage"]
            total_in += usage["input_tokens"]
            total_out += usage["output_tokens"]
            results.append((sc.name, ok, why, usage))
            mark = "PASS" if ok else "FAIL"
            print(
                f"{mark:4} {sc.name:22} iters={usage['iterations']} "
                f"in={usage['input_tokens']} out={usage['output_tokens']}  {why}"
            )

    passed = sum(1 for _, ok, _, _ in results if ok)
    print(f"\n{passed}/{len(results)} passed  " f"tokens: {total_in} in / {total_out} out")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
