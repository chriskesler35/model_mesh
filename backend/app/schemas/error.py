"""Error response schemas."""

from typing import Optional, Dict, Any
from pydantic import BaseModel


class ErrorDetail(BaseModel):
    """Error detail structure."""
    type: str  # 'invalid_request_error', 'authentication_error', 'model_error', 'rate_limit_error'
    message: str
    code: str
    details: Optional[Dict[str, Any]] = None


class ErrorResponse(BaseModel):
    """Error response wrapper."""
    error: ErrorDetail