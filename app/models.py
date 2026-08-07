import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    site: Mapped[str] = mapped_column(String(120), index=True)
    hw_model: Mapped[str | None] = mapped_column(String(120))
    firmware: Mapped[str | None] = mapped_column(String(60))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Telemetry(Base):
    __tablename__ = "telemetry"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    device_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"))
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    battery_pct: Mapped[float] = mapped_column(Float)
    temp_c: Mapped[float] = mapped_column(Float)
    signal_rssi: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))

    __table_args__ = (Index("ix_telemetry_device_ts", "device_id", "ts"),)


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    device_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"))
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    severity: Mapped[str] = mapped_column(String(20))
    type_: Mapped[str] = mapped_column("type", String(60))
    message: Mapped[str] = mapped_column(String(240))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index(
            "ix_alerts_device_type_open",
            "device_id",
            "type",
            unique=True,
            postgresql_where=text("resolved_at IS NULL"),
        ),
    )
