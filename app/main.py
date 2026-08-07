"""FleetPulse — real-time event monitoring with a grounded LLM copilot and a
tool-using ops agent. Demo domain: IoT device fleet."""

from fastapi import FastAPI

from app.config import get_settings


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

    @application.get("/healthz", tags=["ops"])
    def healthz() -> dict[str, str]:
        """Liveness: the process is up."""
        return {"status": "ok"}

    @application.get("/readyz", tags=["ops"])
    def readyz() -> dict[str, str]:
        """Readiness: dependencies are reachable.

        Phase 1 wires a real database connectivity check here; until then
        readiness equals liveness.
        """
        return {"status": "ready"}

    return application


app = create_app()
