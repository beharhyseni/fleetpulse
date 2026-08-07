"""Pydantic schemas: the API contract, separate from the storage model."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

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
