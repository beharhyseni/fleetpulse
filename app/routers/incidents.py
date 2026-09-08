from fastapi import APIRouter, Depends, HTTPException, Request

from app.config import get_settings
from app.db import DbSession
from app.schemas import SummaryOut
from app.services.summarize import summarize_incidents


def require_api_key(request: Request) -> None:
    expected = get_settings().fleetpulse_api_key
    if expected and request.headers.get("X-API-Key") != expected:
        raise HTTPException(status_code=401, detail="invalid or missing API key")


router = APIRouter(prefix="/incidents", tags=["incidents"], dependencies=[Depends(require_api_key)])


@router.get("/summary", response_model=SummaryOut)
def incident_summary(db: DbSession) -> SummaryOut:
    if not get_settings().anthropic_api_key:
        raise HTTPException(status_code=503, detail="summarizer not configured")
    return SummaryOut(**summarize_incidents(db))
