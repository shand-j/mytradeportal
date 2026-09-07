"""HTTP middleware: request IDs and structured access logs.

Every request gets an ``X-Request-ID`` (propagated from the caller when
present, otherwise a fresh UUID4). The ID is bound to the structlog context
for the whole request lifecycle so downstream log events (LLM calls, audit
lines, errors) automatically carry ``request_id``, and it is echoed back on
the response so support can correlate client reports with server logs.

Each completed request emits one ``http_request`` event (INFO) with method,
path, status, duration and tenant; 5xx responses and unhandled exceptions log
at ERROR instead. ``/health`` and ``/ready`` are demoted to DEBUG so probes
do not drown out real traffic.
"""

import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger("api.http")

# Probe endpoints: logged at DEBUG rather than INFO to keep noise down.
_QUIET_PATHS = frozenset({"/health", "/ready"})

# Cap propagated request IDs so a malicious/buggy caller cannot inject
# unbounded strings into every log line of the request.
_MAX_REQUEST_ID_LENGTH = 64


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Bind a request ID to the log context and emit one access log per request."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get("x-request-id", "")[:_MAX_REQUEST_ID_LENGTH]
        if not request_id:
            request_id = str(uuid.uuid4())

        # Reset the context (contextvars are per-task, but be explicit) and
        # bind the fields every downstream log event should carry.
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        # Tenant is taken from the header only — no DB lookups on the hot path.
        tenant_id = request.headers.get("X-Tenant-ID")

        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            logger.error(
                "http_request_failed",
                method=request.method,
                path=request.url.path,
                duration_ms=duration_ms,
                tenant_id=tenant_id,
                exc_info=True,
            )
            # Re-raise: FastAPI's ServerErrorMiddleware turns this into a
            # plain 500 without leaking a stack trace to the client.
            raise

        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        if request.url.path in _QUIET_PATHS:
            log = logger.debug
        elif response.status_code >= 500:
            log = logger.error
        else:
            log = logger.info
        log(
            "http_request",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
            tenant_id=tenant_id,
        )

        response.headers["X-Request-ID"] = request_id
        return response
