"""Middleware to track request count and latency via Prometheus metrics."""

import time
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class MetricsMiddleware(BaseHTTPMiddleware):
    """Records request_count and request_latency for every request (except /metrics)."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path == "/metrics":
            return await call_next(request)

        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start

        try:
            from app.routes.metrics import request_count, request_latency, _PROMETHEUS_AVAILABLE

            if _PROMETHEUS_AVAILABLE:
                method = request.method
                endpoint = request.url.path
                status = str(response.status_code)
                request_count.labels(method=method, endpoint=endpoint, status=status).inc()
                request_latency.labels(method=method, endpoint=endpoint).observe(duration)
        except Exception:
            pass

        return response
