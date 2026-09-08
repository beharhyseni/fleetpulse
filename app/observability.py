import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

logger = logging.getLogger("fleetpulse")

HTTP_REQUESTS = Counter("http_requests_total", "HTTP requests", ["method", "path", "status"])

HTTP_LATENCY = Histogram("http_request_duration_seconds", "Request duration", ["method", "path"])

__all__ = [
    "CONTENT_TYPE_LATEST",
    "generate_latest",
    "request_context_middleware",
    "setup_logging",
]


def setup_logging() -> None:
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def _path_label(request: Request) -> str:
    """Metric label: the route template after routing ran, else a constant.

    Read only AFTER call_next: the router populates scope["route"] during
    dispatch. Templates ("/devices/{device_id}") keep label cardinality
    bounded; unmatched paths collapse to one label instead of minting one
    per garbage URL.
    """
    route = request.scope.get("route")
    return getattr(route, "path", "unmatched")


def _log_and_record(
    rid: str, method: str, raw_path: str, path_label: str, status: int, elapsed: float
) -> None:
    logger.info(
        json.dumps(
            {
                "request_id": rid,
                "method": method,
                "path": raw_path,
                "status": status,
                "duration_ms": round(elapsed * 1000, 1),
            }
        )
    )
    HTTP_REQUESTS.labels(method, path_label, str(status)).inc()
    HTTP_LATENCY.labels(method, path_label).observe(elapsed)


async def request_context_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
    request.state.request_id = rid
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        _log_and_record(
            rid,
            request.method,
            request.url.path,
            _path_label(request),
            500,
            time.perf_counter() - start,
        )
        raise
    response.headers["X-Request-ID"] = rid
    _log_and_record(
        rid,
        request.method,
        request.url.path,
        _path_label(request),
        response.status_code,
        time.perf_counter() - start,
    )
    return response
