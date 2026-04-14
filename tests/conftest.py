"""
conftest.py - Shared fixtures for DevForgeAI test suite.

All tests use a synchronous httpx.Client pointed at the live backend.
Set environment variables to override defaults:
  DEVFORGEAI_URL  (default: auto-detect healthy localhost backend, preferring http://localhost:19001)
  DEVFORGEAI_KEY  (default: modelmesh_local_dev_key)
"""

import os
import pytest
import httpx

def _resolve_base_url() -> str:
    explicit = os.getenv("DEVFORGEAI_URL")
    if explicit:
        return explicit

    candidates = [
        "http://localhost:19001",
        "http://127.0.0.1:19001",
        "http://localhost:19000",
        "http://127.0.0.1:19000",
    ]

    for base_url in candidates:
        try:
            response = httpx.get(f"{base_url}/v1/health", timeout=2.0)
            if response.is_success:
                return base_url
        except httpx.HTTPError:
            continue

    return "http://localhost:19001"


BASE_URL = _resolve_base_url()
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
