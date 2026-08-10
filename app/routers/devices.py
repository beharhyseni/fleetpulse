import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db import DbSession
from app.models import Device
from app.schemas import DeviceCreate, DeviceRead

router = APIRouter(prefix="/devices", tags=["devices"])


@router.post("", response_model=DeviceRead, status_code=status.HTTP_201_CREATED)
def create_device(payload: DeviceCreate, db: DbSession) -> Device:
    device = Device(**payload.model_dump())
    db.add(device)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"device name {payload.name!r} already exists",
        ) from exc
    db.refresh(device)
    return device


@router.get("", response_model=list[DeviceRead])
def list_devices(
    db: DbSession,
    site: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Device]:
    stmt = select(Device).order_by(Device.created_at.desc()).limit(limit).offset(offset)
    if site is not None:
        stmt = stmt.where(Device.site == site)
    return list(db.scalars(stmt).all())


@router.get("/{device_id}", response_model=DeviceRead)
def get_device(device_id: uuid.UUID, db: DbSession) -> Device:
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="device not found")
    return device
