"""Stats endpoints."""

import math
import calendar
from datetime import datetime, timedelta
from typing import Dict, List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.database import get_db
from app.schemas import CostSummary, UsageSummary, DailyCostEntry, DailyCostSummary, DailyCostResponse
from app.schemas import CostSummary, UsageSummary, ModelPerformanceSummary
from app.schemas.stats import ModelPerformanceMetrics, ModelPerformanceHighlights
from app.schemas.stats import CostForecast, BudgetUpdate
from app.middleware.auth import verify_api_key

router = APIRouter(prefix="/v1/stats", tags=["stats"], dependencies=[Depends(verify_api_key)])


def _normalize_uuid(val: str) -> str:
    """Strip hyphens from UUID for consistent comparison."""
    return val.replace("-", "") if val else ""


@router.get("/costs", response_model=CostSummary)
async def get_costs(
    days: int = Query(7, ge=1, le=30),
    db: AsyncSession = Depends(get_db)
):
    """Get cost summary for the last N days."""
    start_date = datetime.utcnow() - timedelta(days=days)

    # Total cost
    result = await db.execute(
        text("SELECT COALESCE(SUM(estimated_cost), 0) FROM request_logs WHERE created_at >= :start"),
        {"start": start_date}
    )
    total_cost = float(result.scalar() or 0)

    # Cost by model — use REPLACE to normalize UUIDs for JOIN
    result = await db.execute(text("""
        SELECT m.model_id, COALESCE(SUM(r.estimated_cost), 0) as cost
        FROM request_logs r
        JOIN models m ON REPLACE(r.model_id, '-', '') = REPLACE(m.id, '-', '')
        WHERE r.created_at >= :start
        GROUP BY m.model_id
        ORDER BY cost DESC
    """), {"start": start_date})
    by_model = {row[0]: round(float(row[1]), 6) for row in result.fetchall()}

    # Cost by provider
    result = await db.execute(text("""
        SELECT p.name, COALESCE(SUM(r.estimated_cost), 0) as cost
        FROM request_logs r
        JOIN models m ON REPLACE(r.model_id, '-', '') = REPLACE(m.id, '-', '')
        JOIN providers p ON REPLACE(m.provider_id, '-', '') = REPLACE(p.id, '-', '')
        WHERE r.created_at >= :start
        GROUP BY p.name
        ORDER BY cost DESC
    """), {"start": start_date})
    by_provider = {row[0]: round(float(row[1]), 6) for row in result.fetchall()}

    return CostSummary(
        total_cost=round(total_cost, 6),
        by_model=by_model,
        by_provider=by_provider,
        period_start=start_date,
        period_end=datetime.utcnow()
    )


@router.get("/usage", response_model=UsageSummary)
async def get_usage(
    days: int = Query(7, ge=1, le=30),
    db: AsyncSession = Depends(get_db)
):
    """Get usage summary for the last N days."""
    start_date = datetime.utcnow() - timedelta(days=days)

    # Totals
    result = await db.execute(text("""
        SELECT
            COALESCE(SUM(input_tokens), 0),
            COALESCE(SUM(output_tokens), 0),
            COUNT(*),
            SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END)
        FROM request_logs
        WHERE created_at >= :start
    """), {"start": start_date})
    row = result.fetchone()
    total_input = int(row[0])
    total_output = int(row[1])
    total_requests = int(row[2])
    successful = int(row[3] or 0)
    success_rate = successful / total_requests if total_requests > 0 else 1.0

    # Usage by model
    result = await db.execute(text("""
        SELECT m.model_id,
               COALESCE(SUM(r.input_tokens), 0),
               COALESCE(SUM(r.output_tokens), 0),
               COUNT(*)
        FROM request_logs r
        JOIN models m ON REPLACE(r.model_id, '-', '') = REPLACE(m.id, '-', '')
        WHERE r.created_at >= :start
        GROUP BY m.model_id
        ORDER BY COUNT(*) DESC
    """), {"start": start_date})
    by_model = {}
    for row in result.fetchall():
        by_model[row[0]] = {
            "input_tokens": int(row[1]),
            "output_tokens": int(row[2]),
            "requests": int(row[3])
        }

    # Usage by provider
    result = await db.execute(text("""
        SELECT p.name,
               COALESCE(SUM(r.input_tokens), 0),
               COALESCE(SUM(r.output_tokens), 0),
               COUNT(*)
        FROM request_logs r
        JOIN models m ON REPLACE(r.model_id, '-', '') = REPLACE(m.id, '-', '')
        JOIN providers p ON REPLACE(m.provider_id, '-', '') = REPLACE(p.id, '-', '')
        WHERE r.created_at >= :start
        GROUP BY p.name
        ORDER BY COUNT(*) DESC
    """), {"start": start_date})
    by_provider = {}
    for row in result.fetchall():
        by_provider[row[0]] = {
            "input_tokens": int(row[1]),
            "output_tokens": int(row[2]),
            "requests": int(row[3])
        }

    return UsageSummary(
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        total_requests=total_requests,
        success_rate=round(success_rate, 4),
        by_model=by_model,
        by_provider=by_provider,
        period_start=start_date,
        period_end=datetime.utcnow()
    )


@router.get("/costs/daily", response_model=DailyCostResponse)
async def get_daily_costs(
    days: int = Query(default=7, ge=1, le=90),
    db: AsyncSession = Depends(get_db)
):
    """Return daily cost breakdown for the last N days."""
    now = datetime.utcnow()
    current_start = now - timedelta(days=days)
    prior_start = current_start - timedelta(days=days)

    # Daily breakdown for the current period
    result = await db.execute(text("""
        SELECT
            DATE(created_at) as day,
            COALESCE(SUM(estimated_cost), 0) as total_cost,
            COUNT(*) as total_requests,
            COALESCE(SUM(input_tokens), 0) as input_tokens,
            COALESCE(SUM(output_tokens), 0) as output_tokens
        FROM request_logs
        WHERE created_at >= :start
        GROUP BY DATE(created_at)
        ORDER BY day ASC
    """), {"start": current_start})

    rows = result.fetchall()
    daily = [
        DailyCostEntry(
            date=str(row[0]),
            total_cost=round(float(row[1]), 6),
            total_requests=int(row[2]),
            input_tokens=int(row[3]),
            output_tokens=int(row[4]),
        )
        for row in rows
    ]

    # Current period total
    current_total = sum(entry.total_cost for entry in daily)

    # Prior period total for change calculation
    result = await db.execute(
        text("SELECT COALESCE(SUM(estimated_cost), 0) FROM request_logs WHERE created_at >= :start AND created_at < :end"),
        {"start": prior_start, "end": current_start}
    )
    prior_total = float(result.scalar() or 0)

    # Calculate percentage change
    change_pct = None
    if prior_total > 0:
        change_pct = round(((current_total - prior_total) / prior_total) * 100, 1)

    daily_average = round(current_total / days, 6) if days > 0 else 0

    return DailyCostResponse(
        daily=daily,
        summary=DailyCostSummary(
            total_cost=round(current_total, 6),
            daily_average=daily_average,
            change_pct=change_pct,
        ),
    )


def _percentile(sorted_values: List[float], p: float) -> float:
    """Compute the p-th percentile from a sorted list of values (0-100 scale)."""
    if not sorted_values:
        return 0.0
    k = (p / 100.0) * (len(sorted_values) - 1)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_values[int(k)]
    return sorted_values[f] * (c - k) + sorted_values[c] * (k - f)


@router.get("/models/performance", response_model=ModelPerformanceSummary)
async def get_model_performance(
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db)
):
    """Per-model performance metrics with highlights."""
    start_date = datetime.utcnow() - timedelta(days=days)

    # Aggregate metrics per model (SQLite-compatible: no PERCENTILE_CONT)
    result = await db.execute(text("""
        SELECT
            m.model_id,
            m.display_name,
            COUNT(*) as total_requests,
            AVG(r.latency_ms) as avg_latency_ms,
            CASE WHEN COUNT(*) > 0
                THEN CAST(SUM(CASE WHEN r.success = 1 THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*) * 100
                ELSE 0 END as success_rate,
            AVG(COALESCE(r.input_tokens, 0) + COALESCE(r.output_tokens, 0)) as avg_tokens_per_request,
            COALESCE(SUM(r.estimated_cost), 0) as total_cost
        FROM request_logs r
        JOIN models m ON REPLACE(r.model_id, '-', '') = REPLACE(m.id, '-', '')
        WHERE r.created_at >= :start
        GROUP BY m.model_id, m.display_name
        ORDER BY total_requests DESC
    """), {"start": start_date})
    aggregate_rows = result.fetchall()

    # Collect per-model latency arrays for P95 calculation
    latency_result = await db.execute(text("""
        SELECT m.model_id, r.latency_ms
        FROM request_logs r
        JOIN models m ON REPLACE(r.model_id, '-', '') = REPLACE(m.id, '-', '')
        WHERE r.created_at >= :start AND r.latency_ms IS NOT NULL
        ORDER BY m.model_id, r.latency_ms
    """), {"start": start_date})
    latency_rows = latency_result.fetchall()

    # Group latencies by model
    latencies_by_model: Dict[str, List[float]] = {}
    for row in latency_rows:
        model_id = row[0]
        latencies_by_model.setdefault(model_id, []).append(float(row[1]))

    # Build model metrics list
    models: List[ModelPerformanceMetrics] = []
    for row in aggregate_rows:
        model_name = row[0] or "unknown"
        display_name = row[1]
        total_reqs = int(row[2])
        avg_lat = round(float(row[3] or 0), 1)
        s_rate = round(float(row[4] or 0), 1)
        avg_tokens = round(float(row[5] or 0), 0)
        t_cost = round(float(row[6] or 0), 6)

        sorted_lats = latencies_by_model.get(model_name, [])
        p95_lat = round(_percentile(sorted_lats, 95), 1)

        models.append(ModelPerformanceMetrics(
            model_name=model_name,
            display_name=display_name,
            total_requests=total_reqs,
            avg_latency_ms=avg_lat,
            p95_latency_ms=p95_lat,
            success_rate=s_rate,
            avg_tokens_per_request=avg_tokens,
            total_cost=t_cost,
        ))

    # Compute highlights (only from models with at least 1 request)
    highlights = ModelPerformanceHighlights()
    if models:
        fastest = min(models, key=lambda m: m.avg_latency_ms)
        highlights.fastest = fastest.display_name or fastest.model_name

        cheapest = min(models, key=lambda m: (m.total_cost / m.total_requests) if m.total_requests > 0 else float('inf'))
        highlights.cheapest = cheapest.display_name or cheapest.model_name

        most_reliable = max(models, key=lambda m: m.success_rate)
        highlights.most_reliable = most_reliable.display_name or most_reliable.model_name

    return ModelPerformanceSummary(
        models=models,
        highlights=highlights,
        period_start=start_date,
        period_end=datetime.utcnow(),
    )


@router.get("/agents")
async def get_agent_metrics(
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db)
):
    """Per-agent efficiency metrics aggregated from pipeline phase runs."""
    start_date = datetime.utcnow() - timedelta(days=days)

    result = await db.execute(text("""
        SELECT
            agent_role,
            COUNT(*) as total_runs,
            SUM(CASE WHEN status IN ('approved', 'completed') THEN 1 ELSE 0 END) as success_count,
            AVG(COALESCE(input_tokens, 0) + COALESCE(output_tokens, 0)) as avg_tokens,
            AVG(
                CASE WHEN started_at IS NOT NULL AND completed_at IS NOT NULL
                THEN (julianday(completed_at) - julianday(started_at)) * 86400000
                ELSE NULL END
            ) as avg_duration_ms,
            SUM(retry_count) as total_retries
        FROM workbench_phase_runs
        WHERE created_at >= :start
        GROUP BY agent_role
        ORDER BY total_runs DESC
    """), {"start": start_date})

    rows = result.fetchall()
    agents = []
    for row in rows:
        total_runs = int(row[1])
        success_count = int(row[2])
        total_retries = int(row[5] or 0)
        agents.append({
            "agent_role": row[0],
            "total_runs": total_runs,
            "success_rate": round(success_count / total_runs, 4) if total_runs > 0 else 0.0,
            "avg_tokens": round(float(row[3] or 0), 0),
            "avg_duration_ms": round(float(row[4] or 0), 1),
            "retry_rate": round(total_retries / total_runs, 4) if total_runs > 0 else 0.0,
        })

    return agents


# In-memory budget store (single-user local app)
_budget_limit: float | None = None


@router.get("/costs/forecast", response_model=CostForecast)
async def get_cost_forecast(
    db: AsyncSession = Depends(get_db)
):
    """Calculate projected monthly cost based on current usage rate."""
    global _budget_limit
    now = datetime.utcnow()
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    days_elapsed = max((now - month_start).days, 1)  # at least 1 to avoid div/0
    days_remaining = days_in_month - days_elapsed

    # Total cost for current month
    result = await db.execute(
        text("SELECT COALESCE(SUM(estimated_cost), 0) FROM request_logs WHERE created_at >= :start"),
        {"start": month_start}
    )
    actual_cost = float(result.scalar() or 0)

    daily_average = actual_cost / days_elapsed
    projected_cost = daily_average * days_in_month

    over_budget = False
    if _budget_limit is not None and _budget_limit > 0:
        over_budget = projected_cost > _budget_limit

    return CostForecast(
        actual_cost=round(actual_cost, 6),
        projected_cost=round(projected_cost, 6),
        daily_average=round(daily_average, 6),
        days_elapsed=days_elapsed,
        days_remaining=days_remaining,
        days_in_month=days_in_month,
        budget_limit=_budget_limit,
        over_budget=over_budget,
    )


@router.patch("/budget")
async def set_budget(body: BudgetUpdate):
    """Set or update the monthly budget threshold."""
    global _budget_limit
    _budget_limit = body.budget_limit
    return {"budget_limit": _budget_limit}


@router.get("/budget")
async def get_budget():
    """Get the current budget threshold."""
    return {"budget_limit": _budget_limit}
