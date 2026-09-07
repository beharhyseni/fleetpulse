from fastapi import APIRouter, HTTPException

from app.config import get_settings
from app.db import DbSession
from app.schemas import SummaryOut
from app.services.summarize import summarize_incidents

router = APIRouter(prefix="/incidents", tags=["incidents"])


@router.get("/summary", response_model=SummaryOut)
def incident_summary(db: DbSession) -> SummaryOut:
    if not get_settings().anthropic_api_key:
        raise HTTPException(status_code=503, detail="summarizer not configured")
    return SummaryOut(**summarize_incidents(db))
