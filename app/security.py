from fastapi import HTTPException, Request

from app.config import get_settings


def require_api_key(request: Request) -> None:
    expected = get_settings().fleetpulse_api_key
    if expected and request.headers.get("X-API-Key") != expected:
        raise HTTPException(status_code=401, detail="invalid or missing API key")
