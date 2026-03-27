"""Stats schemas."""

from typing import Dict
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