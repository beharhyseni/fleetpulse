"""Pydantic schemas: the API contract, separate from the storage model."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, computed_field

DeviceStatus = Literal["online", "stale", "offline"]

STALE_AFTER = timedelta(minutes=15)
OFFLINE_AFTER = timedelta(minutes=60)


def derive_status(last_seen_at: datetime | None, now: datetime | None = None) -> DeviceStatus:
    """online < 15 min, stale 15-60 min, offline beyond (or never seen)."""
    if last_seen_at is None:
        return "offline"
    now = now or datetime.now(UTC)
    age = now - last_seen_at
    if age < STALE_AFTER:
        return "online"
    if age < OFFLINE_AFTER:
        return "stale"
    return "offline"


class DeviceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    site: str = Field(min_length=1, max_length=120)
    hw_model: str | None = None
    firmware: str | None = None


class DeviceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    site: str
    hw_model: str | None
    firmware: str | None
    last_seen_at: datetime | None
    created_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def status(self) -> DeviceStatus:
        return derive_status(self.last_seen_at)


class TelemetryIn(BaseModel):
    device_id: uuid.UUID
    ts: AwareDatetime
    battery_pct: float = Field(ge=0, le=100)
    temp_c: float = Field(ge=-90, le=150)
    signal_rssi: int
    payload: dict[str, Any] = Field(default_factory=dict)


TelemetryBatch = Annotated[list[TelemetryIn], Field(min_length=1)]


class IngestResult(BaseModel):
    ingested: int
    alerts_created: int


class TelemetryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    device_id: uuid.UUID
    ts: datetime
    battery_pct: float
    temp_c: float
    signal_rssi: int
    payload: dict[str, Any]


class AlertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    device_id: uuid.UUID
    ts: datetime
    severity: str
    type_: str = Field(serialization_alias="type")
    message: str
    resolved_at: datetime | None


class SummaryOut(BaseModel):
    generated_at: AwareDatetime
    model: str
    summary: str
    alerts_open: int
    devices_affected: int
    silent_devices: int
