"""Alerts read endpoint: filters over severity, device, and open/resolved state."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.db import DbSession
from app.models import Alert
from app.schemas import AlertRead

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertRead])
def list_alerts(
    db: DbSession,
    severity: str | None = None,
    device_id: uuid.UUID | None = None,
    is_open: Annotated[bool | None, Query(alias="open")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Alert]:
    stmt = select(Alert).order_by(Alert.ts.desc()).limit(limit).offset(offset)
    if severity is not None:
        stmt = stmt.where(Alert.severity == severity)
    if device_id is not None:
        stmt = stmt.where(Alert.device_id == device_id)
    if is_open is True:
        stmt = stmt.where(Alert.resolved_at.is_(None))
    elif is_open is False:
        stmt = stmt.where(Alert.resolved_at.is_not(None))
    return list(db.scalars(stmt).all())
