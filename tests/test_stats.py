"""
test_stats.py - Tests for /v1/stats/* endpoints.

Covers: costs and usage summaries.
"""

import pytest


class TestStats:
    """Tests for stats/analytics endpoints."""

    def test_get_costs_default(self, client):
        """GET /v1/stats/costs returns cost summary (default 7 days)."""
        r = client.get("/v1/stats/costs")
        assert r.status_code == 200
        data = r.json()
        assert "total_cost" in data
        assert "by_model" in data
        assert "by_provider" in data
        assert "period_start" in data
        assert "period_end" in data
        assert isinstance(data["total_cost"], (int, float))

    def test_get_costs_custom_period(self, client):
        """GET /v1/stats/costs?days=30 returns 30-day summary."""
        r = client.get("/v1/stats/costs", params={"days": 30})
        assert r.status_code == 200
        data = r.json()
        assert "total_cost" in data

    def test_get_costs_one_day(self, client):
        """GET /v1/stats/costs?days=1 returns today's costs."""
        r = client.get("/v1/stats/costs", params={"days": 1})
        assert r.status_code == 200

    def test_get_usage_default(self, client):
        """GET /v1/stats/usage returns usage summary (default 7 days)."""
        r = client.get("/v1/stats/usage")
        assert r.status_code == 200
        data = r.json()
        assert "total_input_tokens" in data
        assert "total_output_tokens" in data
        assert "total_requests" in data
        assert "success_rate" in data
        assert "by_model" in data
        assert "by_provider" in data
        assert isinstance(data["total_requests"], int)

    def test_get_usage_custom_period(self, client):
        """GET /v1/stats/usage?days=14 returns 14-day usage."""
        r = client.get("/v1/stats/usage", params={"days": 14})
        assert r.status_code == 200

    def test_success_rate_valid_range(self, client):
        """Success rate should be between 0 and 100 (or 0 and 1)."""
        r = client.get("/v1/stats/usage")
        assert r.status_code == 200
        rate = r.json()["success_rate"]
        assert 0 <= rate <= 100 or 0.0 <= rate <= 1.0

    def test_by_model_structure(self, client):
        """by_model should be a dict with token counts."""
        r = client.get("/v1/stats/usage")
        assert r.status_code == 200
        by_model = r.json()["by_model"]
        assert isinstance(by_model, dict)
        for model_name, stats in by_model.items():
            assert isinstance(stats, dict)
            assert "input_tokens" in stats or "requests" in stats

    def test_by_provider_structure(self, client):
        """by_provider should be a dict with token counts."""
        r = client.get("/v1/stats/usage")
        assert r.status_code == 200
        by_provider = r.json()["by_provider"]
        assert isinstance(by_provider, dict)
