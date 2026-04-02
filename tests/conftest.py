"""
conftest.py - Shared fixtures for DevForgeAI test suite.

All tests use a synchronous httpx.Client pointed at the live backend.
Set environment variables to override defaults:
  DEVFORGEAI_URL  (default: http://localhost:19000)
  DEVFORGEAI_KEY  (default: modelmesh_local_dev_key)
"""

import os
import pytest
import httpx

BASE_URL = os.getenv("DEVFORGEAI_URL", "http://localhost:19000")
API_KEY = os.getenv("DEVFORGEAI_KEY", "modelmesh_local_dev_key")


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "slow: marks tests that call an LLM (deselect with -m 'not slow')")
    config.addinivalue_line("markers", "destructive: marks tests that modify significant state")


@pytest.fixture(scope="session")
def base_url() -> str:
    """Return the base URL of the running DevForgeAI backend."""
    return BASE_URL


@pytest.fixture(scope="session")
def api_headers() -> dict:
    """Return auth headers for all API calls."""
    return {"Authorization": f"Bearer {API_KEY}"}


@pytest.fixture(scope="session")
def client(base_url, api_headers) -> httpx.Client:
    """
    Session-scoped synchronous httpx client with auth headers pre-configured.
    Shared across the entire test run for efficiency.
    """
    with httpx.Client(base_url=base_url, headers=api_headers, timeout=30.0) as c:
        yield c


@pytest.fixture(scope="function")
def fresh_client(base_url, api_headers) -> httpx.Client:
    """
    Function-scoped httpx client — use when a test needs an isolated connection.
    """
    with httpx.Client(base_url=base_url, headers=api_headers, timeout=30.0) as c:
        yield c
