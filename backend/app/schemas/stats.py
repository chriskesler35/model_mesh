"""Stats schemas."""

from typing import Dict, List, Optional
from pydantic import BaseModel
from datetime import datetime


class CostSummary(BaseModel):
    """Cost summary."""
    total_cost: float
    by_model: Dict[str, float]
    by_provider: Dict[str, float]
    period_start: datetime
    period_end: datetime


class UsageSummary(BaseModel):
    """Usage summary."""
    total_input_tokens: int
    total_output_tokens: int
    total_requests: int
    success_rate: float
    by_model: Dict[str, Dict[str, int]]
    by_provider: Dict[str, Dict[str, int]]
    period_start: datetime
    period_end: datetime


class ModelPerformanceMetrics(BaseModel):
    """Per-model performance metrics."""
    model_name: str
    display_name: Optional[str] = None
    total_requests: int
    avg_latency_ms: float
    p95_latency_ms: float
    success_rate: float
    avg_tokens_per_request: float
    total_cost: float


class ModelPerformanceHighlights(BaseModel):
    """Highlight badges for best-performing models."""
    cheapest: Optional[str] = None
    fastest: Optional[str] = None
    most_reliable: Optional[str] = None


class ModelPerformanceSummary(BaseModel):
    """Full model performance response."""
    models: List[ModelPerformanceMetrics]
    highlights: ModelPerformanceHighlights
    period_start: datetime
    period_end: datetime