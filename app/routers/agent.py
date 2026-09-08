from fastapi import APIRouter, Depends, HTTPException

from app.config import get_settings
from app.db import DbSession
from app.schemas import AgentRunOut, InvestigateIn
from app.security import require_api_key
from app.services.agent import investigate

router = APIRouter(prefix="/agent", tags=["agent"], dependencies=[Depends(require_api_key)])


@router.post("/investigate", response_model=AgentRunOut)
def agent_investigate(body: InvestigateIn, db: DbSession) -> AgentRunOut:
    if not get_settings().anthropic_api_key:
        raise HTTPException(status_code=503, detail="agent not configured")
    return AgentRunOut(**investigate(db, body.question, body.approve_writes))
