"""Prometheus metrics endpoint and helpers."""

from fastapi import APIRouter, Response

try:
    from prometheus_client import (
        Counter,
        Histogram,
        Gauge,
        generate_latest,
        CONTENT_TYPE_LATEST,
    )

    request_count = Counter(
        "devforgeai_request_total",
        "Total requests",
        ["method", "endpoint", "status"],
    )
    request_latency = Histogram(
        "devforgeai_request_latency_seconds",
        "Request latency",
        ["method", "endpoint"],
    )
    token_usage = Counter(
        "devforgeai_token_usage_total",
        "Total tokens",
        ["direction", "model"],
    )
    model_errors = Counter(
        "devforgeai_model_errors_total",
        "Model errors",
        ["model", "error_type"],
    )
    active_pipelines = Gauge(
        "devforgeai_active_pipelines",
        "Active pipelines",
    )

    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False
    request_count = None
    request_latency = None
    token_usage = None
    model_errors = None
    active_pipelines = None

router = APIRouter(tags=["metrics"])


def track_request(method: str, endpoint: str, status: int) -> None:
    """Record a request in the request_count counter."""
    if _PROMETHEUS_AVAILABLE:
        request_count.labels(method=method, endpoint=endpoint, status=str(status)).inc()


def track_tokens(direction: str, model: str, count: int = 1) -> None:
    """Record token usage."""
    if _PROMETHEUS_AVAILABLE:
        token_usage.labels(direction=direction, model=model).inc(count)


def track_model_error(model: str, error_type: str) -> None:
    """Record a model error."""
    if _PROMETHEUS_AVAILABLE:
        model_errors.labels(model=model, error_type=error_type).inc()


def set_active_pipelines(count: int) -> None:
    """Set the active pipelines gauge."""
    if _PROMETHEUS_AVAILABLE:
        active_pipelines.set(count)


@router.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    if not _PROMETHEUS_AVAILABLE:
        return Response(
            content="# prometheus_client not installed\n",
            media_type="text/plain",
        )
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
