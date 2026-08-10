from fastapi import APIRouter, HTTPException, status

from app.db import DbSession
from app.schemas import IngestResult, TelemetryBatch
from app.services.ingest import UnknownDevicesError, ingest_batch

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


@router.post("", response_model=IngestResult, status_code=status.HTTP_201_CREATED)
def ingest(readings: TelemetryBatch, db: DbSession) -> IngestResult:
    try:
        ingested, alerts_created = ingest_batch(db, readings)
    except UnknownDevicesError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return IngestResult(ingested=ingested, alerts_created=alerts_created)
