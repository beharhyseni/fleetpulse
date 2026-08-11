"""FleetPulse — real-time event monitoring with a grounded LLM copilot and a
tool-using ops agent. Demo domain: IoT device fleet."""

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import get_settings
from app.db import DbSession
from app.routers import alerts, devices, telemetry


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description=(
            "Real-time event monitoring with a grounded LLM copilot and a "
            "tool-using ops agent; demo domain: IoT device fleet."
        ),
    )
    application.include_router(devices.router)
    application.include_router(telemetry.router)
    application.include_router(alerts.router)

    @application.get("/healthz", tags=["ops"])
    def healthz() -> dict[str, str]:
        """Liveness: the process is up."""
        return {"status": "ok"}

    @application.get("/readyz", tags=["ops"])
    def readyz(db: DbSession) -> JSONResponse:
        """Readiness: the database answers SELECT 1."""
        try:
            db.execute(text("SELECT 1"))
        except Exception:
            return JSONResponse(status_code=503, content={"status": "unavailable"})
        return JSONResponse(content={"status": "ready"})

    return application


app = create_app()
