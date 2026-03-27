"""Middleware package."""

from app.middleware.auth import verify_api_key

__all__ = ["verify_api_key"]