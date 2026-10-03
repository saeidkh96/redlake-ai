from __future__ import annotations

from time import perf_counter
from uuid import uuid4

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import request_id_context

HTTP_REQUESTS = Counter(
    "redlake_http_requests_total",
    "HTTP requests served by RedLake AI.",
    ["method", "route", "status_code"],
)
HTTP_LATENCY = Histogram(
    "redlake_http_request_duration_seconds",
    "HTTP request latency in seconds.",
    ["method", "route"],
)
INGESTION_RUNS = Counter(
    "redlake_ingestion_runs_total",
    "Completed ingestion runs by outcome and input format.",
    ["status", "source_format"],
)


class RequestContextMiddleware:
    """ASGI middleware that adds request IDs without BaseHTTPMiddleware buffering issues."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope["headers"]}
        request_id = headers.get(b"x-request-id", b"").decode() or str(uuid4())
        token = request_id_context.set(request_id)
        started_at = perf_counter()
        status_code = 500

        async def send_with_context(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                response_headers = list(message.get("headers", []))
                response_headers.append((b"x-request-id", request_id.encode()))
                message = {**message, "headers": response_headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_context)
        finally:
            route = scope.get("route")
            route_path = getattr(route, "path", scope["path"])
            HTTP_REQUESTS.labels(scope["method"], route_path, str(status_code)).inc()
            HTTP_LATENCY.labels(scope["method"], route_path).observe(perf_counter() - started_at)
            request_id_context.reset(token)


def metrics_response() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
