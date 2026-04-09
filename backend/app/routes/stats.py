"""Stats endpoints."""

from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.database import get_db
from app.schemas import CostSummary, UsageSummary, DailyCostEntry, DailyCostSummary, DailyCostResponse
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
        )
    )
