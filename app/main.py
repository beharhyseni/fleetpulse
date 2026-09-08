"""FleetPulse — real-time event monitoring with a grounded LLM copilot and a
tool-using ops agent. Demo domain: IoT device fleet."""

from fastapi import FastAPI, Request
from fastapi import Response as FastAPIResponse
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import get_settings
from app.db import DbSession
from app.observability import (
    CONTENT_TYPE_LATEST,
    generate_latest,
    request_context_middleware,
    setup_logging,
)
from app.routers import agent, alerts, devices, incidents, telemetry


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging()
    application = FastAPI(
        title=settings.app_name,
        version="0.5.0",
        description=(
            "Real-time event monitoring with a grounded LLM copilot and a "
            "tool-using ops agent; demo domain: IoT device fleet."
        ),
    )
    application.middleware("http")(request_context_middleware)

    application.include_router(devices.router)
    application.include_router(telemetry.router)
    application.include_router(alerts.router)
    application.include_router(incidents.router)
    application.include_router(agent.router)

    @application.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.status_code,
                    "message": str(exc.detail),
                    "request_id": getattr(request.state, "request_id", None),
                }
            },
        )

    @application.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": 422,
                    "message": "validation error",
                    "details": exc.errors(),
                    "request_id": getattr(request.state, "request_id", None),
                }
            },
        )

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

    @application.get("/metrics", include_in_schema=False, tags=["ops"])
    def metrics() -> FastAPIResponse:
        """Prometheus scrape target."""
        return FastAPIResponse(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return application


app = create_app()
